//! Process ownership is serialized here, independently from long installation scans.
//! Snapshot reads never inspect files, import Python packages, or issue HTTP requests.
use super::{health, owns_listener, stamp, Running};
use crate::model::{EnvironmentBinding, Release};
use anyhow::{anyhow, bail, Context, Result};
use serde::Serialize;
use std::{
    collections::VecDeque,
    fs::File,
    path::Path,
    sync::{Arc, Mutex},
    thread,
    time::Duration,
};

#[derive(Clone, Debug, Serialize)]
pub struct RuntimeSnapshot {
    pub root: String,
    pub release_id: Option<String>,
    pub instance_id: Option<String>,
    pub binding_generation: Option<u64>,
    pub run_id: Option<String>,
    pub seq: u64,
    pub phase: String,
    pub pid: Option<u32>,
    pub port: Option<u16>,
    pub url: Option<String>,
    pub version: Option<String>,
    pub exit_code: Option<i32>,
    pub error: Option<String>,
    pub observed_at: u128,
}
impl RuntimeSnapshot {
    fn stopped(root: &Path, seq: u64) -> Self {
        Self {
            root: root.to_string_lossy().into(),
            release_id: None,
            instance_id: None,
            binding_generation: None,
            run_id: None,
            seq,
            phase: "stopped".into(),
            pid: None,
            port: None,
            url: None,
            version: None,
            exit_code: None,
            error: None,
            observed_at: stamp(),
        }
    }
}
type Listener = Arc<dyn Fn(RuntimeSnapshot) + Send + Sync>;
struct State {
    snapshot: RuntimeSnapshot,
    cancelled: bool,
    cancelled_requests: VecDeque<String>,
}
pub struct Lifecycle {
    state: Mutex<State>,
    process: Mutex<Option<Running>>,
    listener: Mutex<Option<Listener>>,
}
impl Lifecycle {
    pub fn new() -> Arc<Self> {
        let shared = Arc::new(Self {
            state: Mutex::new(State {
                snapshot: RuntimeSnapshot::stopped(Path::new(""), 0),
                cancelled: false,
                cancelled_requests: VecDeque::new(),
            }),
            process: Mutex::new(None),
            listener: Mutex::new(None),
        });
        // Weak ownership allows the process owner to drop with its launcher.
        let weak = Arc::downgrade(&shared);
        thread::spawn(move || loop {
            thread::sleep(Duration::from_millis(200));
            let Some(owner) = weak.upgrade() else { break };
            owner.reap();
        });
        let weak = Arc::downgrade(&shared);
        thread::spawn(move || loop {
            thread::sleep(Duration::from_secs(1));
            let Some(owner) = weak.upgrade() else { break };
            owner.observe_health();
        });
        shared
    }
    pub fn set_listener(&self, listener: Listener) {
        *self.listener.lock().unwrap_or_else(|e| e.into_inner()) = Some(listener);
    }
    fn emit(&self, snapshot: RuntimeSnapshot) {
        let listener = self
            .listener
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .clone();
        if let Some(listener) = listener {
            listener(snapshot);
        }
    }
    fn update(&self, run: &str, f: impl FnOnce(&mut State)) -> bool {
        let next = {
            let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
            if state.snapshot.run_id.as_deref() != Some(run) {
                return false;
            }
            f(&mut state);
            state.snapshot.seq += 1;
            state.snapshot.observed_at = stamp();
            state.snapshot.clone()
        };
        self.emit(next);
        true
    }
    pub fn snapshot(&self, root: &Path) -> RuntimeSnapshot {
        let state = self.state.lock().unwrap_or_else(|e| e.into_inner());
        if same_root(&state.snapshot.root, &root.to_string_lossy()) {
            state.snapshot.clone()
        } else {
            RuntimeSnapshot::stopped(root, state.snapshot.seq)
        }
    }
    pub fn current(&self) -> RuntimeSnapshot {
        self.state
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .snapshot
            .clone()
    }
    pub fn has_process(&self) -> bool {
        self.process
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .is_some()
    }
    pub fn begin(&self, root: &Path) -> Result<String> {
        self.begin_requested(root, None)
    }
    pub fn begin_requested(&self, root: &Path, requested: Option<&str>) -> Result<String> {
        if requested.is_some_and(|id| {
            id.len() < 8
                || id.len() > 128
                || !id
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || matches!(c, b'-' | b'_'))
        }) {
            bail!("运行请求ID无效");
        }
        // Always acquire process before state whenever both are needed.
        let process = self.process.lock().map_err(|_| anyhow!("受管进程锁异常"))?;
        let (snapshot, cancelled) = {
            let mut state = self.state.lock().map_err(|_| anyhow!("运行状态锁异常"))?;
            if process.is_some()
                || matches!(
                    state.snapshot.phase.as_str(),
                    "checking" | "starting" | "stopping"
                )
            {
                bail!("已有受管服务或启动/停止操作正在执行");
            }
            let seq = state.snapshot.seq + 1;
            let run = requested
                .map(str::to_owned)
                .unwrap_or_else(|| format!("run-{}-{}-{seq}", std::process::id(), stamp()));
            let cancelled = state.cancelled_requests.contains(&run);
            let mut snapshot = RuntimeSnapshot::stopped(root, seq);
            snapshot.run_id = Some(run);
            if !cancelled {
                snapshot.phase = "checking".into();
            }
            state.snapshot = snapshot.clone();
            state.cancelled = cancelled;
            (snapshot, cancelled)
        };
        drop(process);
        let run = snapshot.run_id.clone().unwrap();
        self.emit(snapshot);
        if cancelled {
            bail!("本次启动已取消");
        }
        Ok(run)
    }
    pub fn check_cancel(&self, run: &str) -> Result<()> {
        let state = self.state.lock().map_err(|_| anyhow!("运行状态锁异常"))?;
        if state.snapshot.run_id.as_deref() != Some(run) || state.cancelled {
            bail!("本次启动已取消");
        }
        Ok(())
    }
    pub(super) fn attach(
        &self,
        run: &str,
        mut process: Running,
        release: &Release,
        binding: Option<&EnvironmentBinding>,
    ) -> Result<()> {
        let mut owner = self.process.lock().map_err(|_| anyhow!("受管进程锁异常"))?;
        if owner.is_some() || self.current().run_id.as_deref() != Some(run) {
            process.terminate()?;
            bail!("本次运行身份已失效或已有受管进程");
        }
        let pid = process.child.id();
        let port = process.port;
        // Even a cancellation arriving immediately after spawn must transfer the
        // Job and lease to the owner. fail_start then drains it, or retains it
        // as stop_failed; dropping an unattached Job is not proof of drainage.
        *owner = Some(process);
        self.update(run, |state| {
            if !state.cancelled {
                state.snapshot.phase = "starting".into();
            }
            state.snapshot.pid = Some(pid);
            state.snapshot.port = Some(port);
            state.snapshot.release_id = Some(release.id.clone());
            state.snapshot.version = Some(release.version.clone());
            state.snapshot.instance_id = binding.map(|b| b.instance_id.clone());
            state.snapshot.binding_generation = binding.map(|b| b.generation);
        });
        self.check_cancel(run)
    }
    pub fn check_alive(&self, run: &str) -> Result<()> {
        let mut owner = self.process.lock().map_err(|_| anyhow!("受管进程锁异常"))?;
        self.check_cancel(run)?;
        let process = owner.as_mut().context("受管训练器已退出")?;
        if process.child.try_wait()?.is_some() {
            bail!("训练器在健康检查前退出，请检查日志后修复环境");
        }
        Ok(())
    }
    pub fn check_owned(&self, run: &str, port: u16) -> Result<()> {
        let owner = self.process.lock().map_err(|_| anyhow!("受管进程锁异常"))?;
        self.check_cancel(run)?;
        let process = owner.as_ref().context("受管训练器已退出")?;
        if process.port != port || !owns_listener(port, &process._job) {
            bail!("监听进程与受管训练器不符");
        }
        Ok(())
    }
    pub fn commit_ready(
        &self,
        run: &str,
        version: &str,
        commit: impl FnOnce(Arc<File>) -> Result<()>,
    ) -> Result<u128> {
        let mut owner = self.process.lock().map_err(|_| anyhow!("受管进程锁异常"))?;
        self.check_cancel(run)?;
        let process = owner.as_mut().context("受管进程已退出")?;
        commit(process._lease.clone())?;
        let committed = stamp();
        self.check_cancel(run)?;
        if process.child.try_wait()?.is_some() || !owns_listener(process.port, &process._job) {
            bail!("健康提交后受管进程已退出或监听归属改变");
        }
        self.update(run, |state| {
            // stop can request cancellation without waiting on process ownership.
            if !state.cancelled && state.snapshot.phase == "starting" {
                state.snapshot.phase = "ready".into();
                state.snapshot.version = Some(version.into());
                state.snapshot.url = Some(format!("http://127.0.0.1:{}", process.port));
                state.snapshot.error = None;
            }
        });
        self.check_cancel(run)?;
        Ok(committed)
    }
    pub fn request_stop(&self) {
        self.request_stop_for(None);
    }
    pub fn request_stop_for(&self, target: Option<&str>) -> bool {
        let next = {
            let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
            if let Some(target) = target {
                if target.len() > 128 {
                    return false;
                }
                if !state.cancelled_requests.iter().any(|id| id == target) {
                    if state.cancelled_requests.len() == 64 {
                        state.cancelled_requests.pop_front();
                    }
                    state.cancelled_requests.push_back(target.to_owned());
                }
                // Remember early cancellation, but never stop a different run.
                if state.snapshot.run_id.as_deref() != Some(target) {
                    return false;
                }
            }
            state.cancelled = true;
            if matches!(
                state.snapshot.phase.as_str(),
                "stopped" | "exited" | "start_failed"
            ) {
                return false;
            }
            if state.snapshot.phase == "stopping" {
                return true;
            }
            state.snapshot.phase = "stopping".into();
            state.snapshot.url = None;
            state.snapshot.seq += 1;
            state.snapshot.observed_at = stamp();
            state.snapshot.clone()
        };
        self.emit(next);
        true
    }
    pub fn stop(&self) -> Result<RuntimeSnapshot> {
        self.stop_for(None)
    }
    pub fn stop_for(&self, target: Option<&str>) -> Result<RuntimeSnapshot> {
        // Fix this request's identity before callbacks can yield. Another stop
        // may finish this run and a successor may begin while we emit stopping.
        let Some(run) = target.map(str::to_owned).or_else(|| self.current().run_id) else {
            // Absence is not a wildcard: a first run may begin immediately
            // after this snapshot, and this old request must not cancel it.
            return Ok(self.current());
        };
        if !self.request_stop_for(Some(&run)) {
            return Ok(self.current());
        }
        let mut owner = self.process.lock().map_err(|_| anyhow!("受管进程锁异常"))?;
        if self.current().run_id.as_deref() != Some(run.as_str()) {
            return Ok(self.current());
        }
        if let Some(process) = owner.as_mut() {
            if let Err(error) = process.terminate() {
                self.update(&run, |state| {
                    state.snapshot.phase = "stop_failed".into();
                    state.snapshot.error = Some(format!("{error:#}"));
                });
                return Err(error);
            }
            owner.take(); // Drop Job first, then the workspace lease, before stopped.
            self.publish_ended(&run, "stopped", None, None);
        }
        // Without a process, the start worker still owns preparation's lease.
        // It alone finalizes cancellation after the current check returns.
        Ok(self.current())
    }
    fn publish_ended(&self, run: &str, phase: &str, code: Option<i32>, error: Option<String>) {
        self.update(run, |state| {
            state.snapshot.phase = phase.into();
            state.snapshot.pid = None;
            state.snapshot.port = None;
            state.snapshot.url = None;
            state.snapshot.exit_code = code;
            state.snapshot.error = error;
        });
    }
    pub fn fail_start(&self, run: &str, error: &str) {
        // Cancelled/stale starts never clean up a successor's process.
        if self.current().run_id.as_deref() != Some(run) {
            return;
        }
        let mut owner = self.process.lock().unwrap_or_else(|e| e.into_inner());
        if self.current().run_id.as_deref() != Some(run) {
            return;
        }
        if let Some(process) = owner.as_mut() {
            if let Err(stop_error) = process.terminate() {
                self.update(run, |state| {
                    state.snapshot.phase = "stop_failed".into();
                    state.snapshot.error = Some(format!("{error}; {stop_error:#}"));
                });
                return;
            }
            owner.take();
        }
        let cancelled = self
            .state
            .lock()
            .unwrap_or_else(|e| e.into_inner())
            .cancelled;
        self.publish_ended(
            run,
            if cancelled { "stopped" } else { "start_failed" },
            None,
            (!cancelled).then(|| crate::network_policy::redact(error)),
        );
    }
    pub fn reap(&self) {
        let before = self.current();
        if !matches!(before.phase.as_str(), "ready" | "degraded") {
            return;
        }
        let Ok(mut owner) = self.process.try_lock() else {
            return;
        };
        if self.current().run_id != before.run_id {
            return;
        }
        let Some(process) = owner.as_mut() else {
            return;
        };
        if let Ok(Some(status)) = process.child.try_wait() {
            if let Err(error) = process.terminate() {
                if let Some(run) = &before.run_id {
                    self.update(run, |state| {
                        state.snapshot.phase = "stop_failed".into();
                        state.snapshot.error = Some(format!("退出后回收进程组失败：{error:#}"));
                    });
                }
                return;
            }
            owner.take();
            if let Some(run) = &before.run_id {
                self.publish_ended(
                    run,
                    "exited",
                    status.code(),
                    Some(format!("训练器服务已退出（{status}）")),
                );
            }
        }
    }
    fn observe_health(&self) {
        let before = self.current();
        if !matches!(before.phase.as_str(), "ready" | "degraded") {
            return;
        }
        let Some(port) = before.port else {
            return;
        };
        // HTTP does not hold either shared lock. Apply only to the same live run.
        let result = health(port);
        let Ok(owner) = self.process.try_lock() else {
            return;
        };
        if self.current().run_id != before.run_id {
            return;
        }
        let Some(process) = owner.as_ref() else {
            return;
        };
        let healthy = result.is_ok_and(|version| Some(version) == before.version)
            && owns_listener(port, &process._job);
        if healthy == (before.phase == "ready") {
            return;
        }
        if let Some(run) = &before.run_id {
            self.update(run, |state| {
                if !state.cancelled && matches!(state.snapshot.phase.as_str(), "ready" | "degraded")
                {
                    state.snapshot.phase = if healthy { "ready" } else { "degraded" }.into();
                    state.snapshot.url = healthy.then(|| format!("http://127.0.0.1:{port}"));
                    state.snapshot.error = (!healthy)
                        .then(|| "受管进程仍在运行，服务暂不可达或版本/端口归属改变".into());
                }
            });
        }
    }
    pub fn url(&self) -> Result<String> {
        let before = self.current();
        let run = before.run_id.context("尚未启动训练器")?;
        let port = before.port.context("尚未启动训练器")?;
        self.check_owned(&run, port)?;
        let version = health(port)?;
        if Some(version) != before.version {
            bail!("训练器健康接口版本不符");
        }
        self.check_owned(&run, port)?;
        Ok(format!("http://127.0.0.1:{port}"))
    }
}
fn same_root(a: &str, b: &str) -> bool {
    if cfg!(windows) {
        a.replace('/', "\\")
            .eq_ignore_ascii_case(&b.replace('/', "\\"))
    } else {
        a == b
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc;

    #[test]
    fn snapshot_is_available_while_process_owner_is_busy() {
        let owner = Lifecycle::new();
        let root = std::env::temp_dir().join("nt-runtime-snapshot");
        owner.begin(&root).unwrap();
        let process_guard = owner.process.lock().unwrap();
        let other = owner.clone();
        let (tx, rx) = mpsc::channel();
        thread::spawn(move || tx.send(other.snapshot(&root)).unwrap());
        let snapshot = rx
            .recv_timeout(Duration::from_millis(250))
            .expect("snapshot waited for process owner");
        assert_eq!(snapshot.phase, "checking");
        drop(process_guard);
    }

    #[test]
    fn cancellation_waits_for_preparation_and_old_run_cannot_publish_ready() {
        let owner = Lifecycle::new();
        let root = std::env::temp_dir().join("nt-runtime-cancel");
        let first = owner.begin(&root).unwrap();
        assert!(owner.begin(&root).is_err());
        assert_eq!(owner.stop().unwrap().phase, "stopping");
        assert!(owner.check_cancel(&first).is_err());
        owner.fail_start(&first, "cancelled during integrity check");
        assert_eq!(owner.current().phase, "stopped");
        let seq = owner.current().seq;
        let second = owner.begin(&root).unwrap();
        assert_ne!(first, second);
        assert!(!owner.update(&first, |state| state.snapshot.phase = "ready".into()));
        owner.fail_start(&first, "late failure");
        assert_eq!(owner.current().phase, "checking");
        assert_eq!(owner.current().run_id.as_deref(), Some(second.as_str()));
        assert!(owner.current().seq > seq);
        assert_eq!(owner.snapshot(&root.join("other")).phase, "stopped");
    }

    #[test]
    fn targeted_cancel_before_start_is_remembered_and_late_stop_cannot_cancel_successor() {
        let owner = Lifecycle::new();
        let root = std::env::temp_dir().join("nt-runtime-early-cancel");
        let cancelled = "requested-before-start";
        let initial_seq = owner.current().seq;
        owner.stop_for(Some(cancelled)).unwrap();
        assert!(owner.begin_requested(&root, Some(cancelled)).is_err());
        assert_eq!(owner.current().phase, "stopped");
        assert_eq!(owner.current().run_id.as_deref(), Some(cancelled));
        assert!(owner.current().seq > initial_seq);
        let successor = "requested-successor";
        owner.begin_requested(&root, Some(successor)).unwrap();
        owner.stop_for(Some(cancelled)).unwrap();
        assert_eq!(owner.current().run_id.as_deref(), Some(successor));
        assert_eq!(owner.current().phase, "checking");
        owner.check_cancel(successor).unwrap();
    }

    #[test]
    fn stop_without_a_run_does_not_issue_wildcard_cancellation() {
        let owner = Lifecycle::new();
        assert_eq!(owner.stop_for(None).unwrap().phase, "stopped");
        assert!(!owner.state.lock().unwrap().cancelled);
        let root = std::env::temp_dir().join("nt-runtime-first-after-stop");
        let run = owner
            .begin_requested(&root, Some("first-after-empty-stop"))
            .unwrap();
        owner.check_cancel(&run).unwrap();
        assert_eq!(owner.current().phase, "checking");
    }

    #[cfg(windows)]
    fn fixture(role: &str) -> (Arc<Lifecycle>, String, std::path::PathBuf) {
        use fs2::FileExt;
        static SERIAL: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
        let root = std::env::temp_dir().join(format!(
            "nt-runtime-job-{}-{}-{}",
            std::process::id(),
            stamp(),
            SERIAL.fetch_add(1, std::sync::atomic::Ordering::Relaxed)
        ));
        std::fs::create_dir(&root).unwrap();
        let lease = File::create(root.join("lease")).unwrap();
        lease.try_lock_exclusive().unwrap();
        let mut command = std::process::Command::new(std::env::current_exe().unwrap());
        command
            .args([
                "--exact",
                "core::lifecycle::tests::process_helper",
                "--ignored",
                "--nocapture",
            ])
            .env("NT_LIFECYCLE_TEST_ROLE", role);
        let (child, job) = super::super::managed_child::spawn(&mut command).unwrap();
        let owner = Lifecycle::new();
        let run = owner.begin(&root).unwrap();
        let catalog = crate::model::Catalog::embedded().unwrap();
        owner
            .attach(
                &run,
                Running {
                    child,
                    port: 1,
                    _job: job,
                    _lease: Arc::new(lease),
                },
                &catalog.releases()[0],
                None,
            )
            .unwrap();
        (owner, run, root)
    }

    #[cfg(windows)]
    #[test]
    fn stop_drains_owned_job_and_releases_lease_before_stopped() {
        use fs2::FileExt;
        let (owner, _, root) = fixture("wait");
        let snapshot = owner.stop().unwrap();
        assert_eq!(snapshot.phase, "stopped");
        assert!(snapshot.pid.is_none());
        assert!(!owner.has_process());
        let lease = File::options()
            .read(true)
            .write(true)
            .open(root.join("lease"))
            .unwrap();
        lease
            .try_lock_exclusive()
            .expect("stopped was published before lease release");
        drop(lease);
        std::fs::remove_file(root.join("lease")).unwrap();
        std::fs::remove_dir(root).unwrap();
    }

    #[cfg(windows)]
    #[test]
    fn watcher_publishes_unexpected_exit_without_engine_inspection() {
        use fs2::FileExt;
        let (owner, run, root) = fixture("exit");
        owner.update(&run, |state| state.snapshot.phase = "ready".into());
        let deadline = std::time::Instant::now() + Duration::from_secs(2);
        while owner.current().phase == "ready" && std::time::Instant::now() < deadline {
            thread::sleep(Duration::from_millis(10));
        }
        let snapshot = owner.current();
        assert_eq!(snapshot.phase, "exited");
        assert_eq!(snapshot.exit_code, Some(7));
        let lease = File::options()
            .read(true)
            .write(true)
            .open(root.join("lease"))
            .unwrap();
        lease.try_lock_exclusive().unwrap();
        drop(lease);
        std::fs::remove_file(root.join("lease")).unwrap();
        std::fs::remove_dir(root).unwrap();
    }
    #[cfg(windows)]
    #[test]
    #[ignore]
    fn process_helper() {
        match std::env::var("NT_LIFECYCLE_TEST_ROLE").as_deref() {
            Ok("exit") => std::process::exit(7),
            Ok("wait") => thread::sleep(Duration::from_secs(30)),
            _ => panic!("helper requires an explicit role"),
        }
    }

    #[cfg(windows)]
    #[test]
    fn cancellation_after_spawn_retains_job_until_explicit_drainage() {
        use fs2::FileExt;
        let (owner, run, root) = fixture("wait");
        // Move the freshly spawned child back out only to reproduce the exact
        // race: cancel was accepted before attach transfers ownership.
        let process = owner.process.lock().unwrap().take().unwrap();
        owner.request_stop();
        let catalog = crate::model::Catalog::embedded().unwrap();
        assert!(owner
            .attach(&run, process, &catalog.releases()[0], None)
            .is_err());
        assert!(owner.has_process());
        assert_eq!(owner.current().phase, "stopping");
        let lease = File::options()
            .read(true)
            .write(true)
            .open(root.join("lease"))
            .unwrap();
        assert!(lease.try_lock_exclusive().is_err());
        owner.fail_start(&run, "cancelled after spawn");
        assert_eq!(owner.current().phase, "stopped");
        lease.try_lock_exclusive().unwrap();
        drop(lease);
        std::fs::remove_file(root.join("lease")).unwrap();
        std::fs::remove_dir(root).unwrap();
    }
    #[cfg(windows)]
    #[test]
    fn unrelated_loopback_listener_never_becomes_openable() {
        let (owner, run, root) = fixture("wait");
        let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        owner.process.lock().unwrap().as_mut().unwrap().port = port;
        owner.update(&run, |state| {
            state.snapshot.phase = "ready".into();
            state.snapshot.port = Some(port);
            state.snapshot.url = Some(format!("http://127.0.0.1:{port}"));
        });
        assert!(owner.url().unwrap_err().to_string().contains("监听进程"));
        assert!(owner.has_process());
        owner.stop().unwrap();
        drop(listener);
        std::fs::remove_file(root.join("lease")).unwrap();
        std::fs::remove_dir(root).unwrap();
    }
    #[cfg(windows)]
    #[test]
    fn stop_request_remains_bound_when_duplicate_stop_finishes_and_successor_starts() {
        use std::sync::atomic::{AtomicBool, Ordering};
        let (owner, run, root) = fixture("wait");
        let blocked_run = run.clone();
        let block_once = AtomicBool::new(true);
        let (paused_tx, paused_rx) = mpsc::channel();
        let (resume_tx, resume_rx) = mpsc::channel();
        let resume_rx = Mutex::new(resume_rx);
        owner.set_listener(Arc::new(move |snapshot| {
            if snapshot.phase == "stopping"
                && snapshot.run_id.as_deref() == Some(blocked_run.as_str())
                && block_once.swap(false, Ordering::AcqRel)
            {
                paused_tx.send(()).unwrap();
                resume_rx
                    .lock()
                    .unwrap()
                    .recv_timeout(Duration::from_secs(5))
                    .unwrap();
            }
        }));
        let delayed_owner = owner.clone();
        let delayed_run = run.clone();
        let (finished_tx, finished_rx) = mpsc::channel();
        let delayed_stop = thread::spawn(move || {
            finished_tx
                .send(delayed_owner.stop_for(Some(&delayed_run)))
                .unwrap();
        });
        paused_rx.recv_timeout(Duration::from_secs(2)).unwrap();
        // A duplicate stop completes A while the old request is paused in its
        // event callback. Put a real, live B under the same process owner.
        assert_eq!(owner.stop_for(Some(&run)).unwrap().phase, "stopped");
        let (temporary_owner, _, successor_root) = fixture("wait");
        let process = temporary_owner.process.lock().unwrap().take().unwrap();
        let successor = "requested-after-duplicate-stop";
        owner
            .begin_requested(&successor_root, Some(successor))
            .unwrap();
        let catalog = crate::model::Catalog::embedded().unwrap();
        owner
            .attach(successor, process, &catalog.releases()[0], None)
            .unwrap();
        resume_tx.send(()).unwrap();
        finished_rx
            .recv_timeout(Duration::from_secs(2))
            .unwrap()
            .unwrap();
        delayed_stop.join().unwrap();
        assert_eq!(owner.current().run_id.as_deref(), Some(successor));
        assert_eq!(owner.current().phase, "starting");
        assert!(
            owner
                .process
                .lock()
                .unwrap()
                .as_mut()
                .unwrap()
                .child
                .try_wait()
                .unwrap()
                .is_none(),
            "old stop killed its successor"
        );
        owner.stop_for(Some(successor)).unwrap();
        drop(temporary_owner);
        for directory in [root, successor_root] {
            std::fs::remove_file(directory.join("lease")).unwrap();
            std::fs::remove_dir(directory).unwrap();
        }
    }
}
