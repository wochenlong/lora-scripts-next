//! 查询线程的可选扫描观察器；不缓存或省略原有完整性校验。
use crate::operations::CancelToken;
use crate::query_tasks::{QueryObserver, QueryProgress, QueryStage};
use anyhow::{Context, Result};
use std::{
    cell::RefCell,
    fmt,
    fs::File,
    io::Read,
    path::Path,
    time::{Duration, Instant},
};

const PROGRESS_INTERVAL: Duration = Duration::from_millis(100);
const MAX_CONTROL_RECORD_BYTES: usize = 32 * 1024 * 1024;
const READ_BLOCK_BYTES: usize = 65_536;
struct Observation {
    observer: QueryObserver,
    stage: Option<QueryStage>,
    files: u64,
    bytes: u64,
    last_publish: Option<Instant>,
}
thread_local! {
    static CURRENT: RefCell<Option<Observation>> = const { RefCell::new(None) };
}
struct Restore(Option<Observation>);
impl Drop for Restore {
    fn drop(&mut self) {
        // closure在任何出口（包括恐慌展开）都不能把observer泄漏给线程池下一任务。
        let previous = self.0.take();
        let _ = CURRENT.try_with(|slot| {
            *slot.borrow_mut() = previous;
        });
    }
}

/// 嵌套作用域独立累计，返回后恢复外层observer/计数/限频时间。
pub(crate) fn with<T>(observer: &QueryObserver, work: impl FnOnce() -> Result<T>) -> Result<T> {
    observer.check()?;
    let previous = CURRENT.with(|slot| {
        slot.replace(Some(Observation {
            observer: observer.clone(),
            stage: None,
            files: 0,
            bytes: 0,
            last_publish: None,
        }))
    });
    let _restore = Restore(previous);
    let value = work()?;
    publish(true)?;
    Ok(value)
}

pub(crate) fn observer() -> Option<QueryObserver> {
    CURRENT.with(|slot| slot.borrow().as_ref().map(|value| value.observer.clone()))
}
pub(crate) fn check() -> Result<()> {
    if let Some(observer) = observer() {
        observer.check()?;
    }
    Ok(())
}
fn message(stage: QueryStage) -> &'static str {
    match stage {
        QueryStage::Python => "正在核对基础 Python",
        QueryStage::Source => "正在核对源码文件",
        QueryStage::Environment => "正在核对实例文件",
        QueryStage::ExtraFiles => "正在核对资料与目录",
        QueryStage::Receipt => "正在核对事务与绑定记录",
        QueryStage::Tools => "正在核对固定工具",
        _ => "正在执行完整性检查",
    }
}
fn publish(force: bool) -> Result<()> {
    CURRENT.with(|slot| -> Result<()> {
        let mut current = slot.borrow_mut();
        let Some(value) = current.as_mut() else {
            return Ok(());
        };
        value.observer.check()?;
        let Some(stage) = value.stage else {
            return Ok(());
        };
        let now = Instant::now();
        if force
            || value
                .last_publish
                .is_none_or(|last| now.saturating_duration_since(last) >= PROGRESS_INTERVAL)
        {
            value.observer.progress(
                stage,
                QueryProgress {
                    files: Some(value.files),
                    bytes: Some(value.bytes),
                    total_files: None,
                    total_bytes: None,
                    message: message(stage).into(),
                },
            )?;
            value.last_publish = Some(now);
        }
        Ok(())
    })
}

/// 每次调用都检查同一权威取消/绝对deadline；仅进度发布限频。
/// 文件/字节为当前RAII作用域实际完成的读取/哈希累计量，不是百分比或磁盘吞吐。
pub(crate) fn checkpoint(stage: QueryStage, files_delta: u64, bytes_delta: u64) -> Result<()> {
    CURRENT.with(|slot| -> Result<()> {
        let mut current = slot.borrow_mut();
        let Some(value) = current.as_mut() else {
            return Ok(());
        };
        value.observer.check()?;
        value.files = value
            .files
            .checked_add(files_delta)
            .context("扫描文件计数溢出")?;
        value.bytes = value
            .bytes
            .checked_add(bytes_delta)
            .context("扫描字节计数溢出")?;
        value.stage = Some(stage);
        Ok(())
    })?;
    // 首帧和作用域结束可立即发布，其他更新（含阶段切换）不超过10Hz。
    publish(false)
}

#[derive(Debug)]
struct ControlRecordLimit {
    buffered_bytes: usize,
    buffered_capacity: usize,
    incoming_bytes: usize,
}
impl fmt::Display for ControlRecordLimit {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "控制记录读取超过32MiB上限（已缓冲{}B，容量{}B，本块{}B）",
            self.buffered_bytes, self.buffered_capacity, self.incoming_bytes
        )
    }
}
impl std::error::Error for ControlRecordLimit {}

// 读取已经发生，先累计真实字节，再检查同一observer的停止原因。
// 这样取消/期限优先于超限或解析错误，末次读量也不会因取消而丢失。
fn completed_read(stage: QueryStage, count: usize, cancel: Option<&CancelToken>) -> Result<()> {
    CURRENT.with(|slot| -> Result<()> {
        if let Some(value) = slot.borrow_mut().as_mut() {
            value.bytes = value
                .bytes
                .checked_add(count as u64)
                .context("扫描字节计数溢出")?;
            value.stage = Some(stage);
        }
        Ok(())
    })?;
    check_control(cancel)?;
    publish(false)
}

// Query的权威取消/绝对期限先判定；Operation仅由显式参数传入，
// 不让旧取消状态污染后续使用新token的必需恢复、保全与资源清理。
fn check_control(cancel: Option<&CancelToken>) -> Result<()> {
    check()?;
    if let Some(cancel) = cancel {
        cancel.check()?;
    }
    Ok(())
}

fn publish_last_read_on_error() {
    CURRENT.with(|slot| {
        if let Some(value) = slot.borrow().as_ref() {
            if let Some(stage) = value.stage {
                // progress不会结束任务；停止原因与原始错误由执行者保持，发布失败不覆盖它们。
                let _ = value.observer.progress(
                    stage,
                    QueryProgress {
                        files: Some(value.files),
                        bytes: Some(value.bytes),
                        total_files: None,
                        total_bytes: None,
                        message: message(stage).into(),
                    },
                );
            }
        }
    });
}

/// 调用者继续负责原guard/普通文件/摘要规则；读取层独立限制32MiB，不能只信metadata。
pub(crate) fn read_file(path: impl AsRef<Path>, stage: QueryStage) -> Result<Vec<u8>> {
    read_file_inner(path.as_ref(), stage, None)
}

pub(crate) fn read_file_controlled(
    path: impl AsRef<Path>,
    stage: QueryStage,
    cancel: &CancelToken,
) -> Result<Vec<u8>> {
    read_file_inner(path.as_ref(), stage, Some(cancel))
}

fn read_file_inner(
    path: &Path,
    stage: QueryStage,
    cancel: Option<&CancelToken>,
) -> Result<Vec<u8>> {
    check_control(cancel)?;
    checkpoint(stage, 0, 0)?;
    let input = File::open(path);
    check_control(cancel)?;
    read_control_record_inner(input?, stage, cancel)
}

#[cfg(test)]
fn read_control_record(mut input: impl Read, stage: QueryStage) -> Result<Vec<u8>> {
    read_control_record_inner(&mut input, stage, None)
}

fn read_control_record_inner(
    mut input: impl Read,
    stage: QueryStage,
    cancel: Option<&CancelToken>,
) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    let mut block = [0; READ_BLOCK_BYTES];
    let result = (|| {
        loop {
            check_control(cancel)?;
            checkpoint(stage, 0, 0)?;
            let count = match input.read(&mut block) {
                Ok(count) => count,
                Err(error) => {
                    check_control(cancel)?;
                    return Err(error.into());
                }
            };
            completed_read(stage, count, cancel)?;
            if count == 0 {
                break;
            }
            if count > MAX_CONTROL_RECORD_BYTES - bytes.len() {
                return Err(ControlRecordLimit {
                    buffered_bytes: bytes.len(),
                    buffered_capacity: bytes.capacity(),
                    incoming_bytes: count,
                }
                .into());
            }
            let next_len = bytes.len() + count;
            if next_len > bytes.capacity() {
                let capacity = bytes
                    .capacity()
                    .saturating_mul(2)
                    .max(next_len)
                    .min(MAX_CONTROL_RECORD_BYTES);
                bytes.try_reserve_exact(capacity - bytes.len())?;
            }
            bytes.extend_from_slice(&block[..count]);
        }
        check_control(cancel)?;
        checkpoint(stage, 1, 0)?;
        Ok(bytes)
    })();
    if result.is_err() {
        publish_last_read_on_error();
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::query_tasks::{
        CleanupProof, QueryAction, QueryClock, QueryError, QueryHandle, QueryIdentity,
        QueryResolution, QueryScope, QueryStatus, QueryTarget, QueryTaskManager,
    };
    use std::{
        fs::{self, OpenOptions},
        io::{self, Write},
        path::PathBuf,
        sync::{
            atomic::{AtomicU64, Ordering},
            mpsc::{self, Receiver, RecvTimeoutError, SyncSender},
        },
        thread::{self, JoinHandle},
        time::{SystemTime, UNIX_EPOCH},
    };

    static NEXT_FILE_FIXTURE: AtomicU64 = AtomicU64::new(0);
    const FILE_GATE_TIMEOUT: Duration = Duration::from_secs(30);

    struct FileFixture {
        root: PathBuf,
        canonical_root: PathBuf,
        path: PathBuf,
        marker: Vec<u8>,
    }
    impl FileFixture {
        fn new(size: usize) -> Self {
            let base = std::env::var_os("NEXT_TRAINER_SCAN_TEST_ROOT")
                .map(PathBuf::from)
                .unwrap_or_else(std::env::temp_dir);
            assert!(base.is_absolute());
            fs::create_dir_all(&base).unwrap();
            let suffix = NEXT_FILE_FIXTURE.fetch_add(1, Ordering::Relaxed);
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos();
            let root = base.join(format!(
                "next-trainer-scan-limit-{}-{nonce}-{suffix}",
                std::process::id()
            ));
            fs::create_dir(&root).unwrap();
            let marker = serde_json::to_vec(&serde_json::json!({
                "owner":"scan_observation::tests", "pid":std::process::id(),
                "root":root, "nonce":nonce.to_string(), "suffix":suffix
            }))
            .unwrap();
            fs::write(root.join(".scan-test-owner.json"), &marker).unwrap();
            fs::write(
                root.join("installation-control.json"),
                b"{\"generation\":17}",
            )
            .unwrap();
            let path = root.join("record.bin");
            let mut file = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&path)
                .unwrap();
            let block = [b'x'; READ_BLOCK_BYTES];
            let mut remaining = size;
            while remaining > 0 {
                let count = remaining.min(block.len());
                file.write_all(&block[..count]).unwrap();
                remaining -= count;
            }
            file.flush().unwrap();
            Self {
                canonical_root: root.canonicalize().unwrap(),
                root,
                path,
                marker,
            }
        }
        fn assert_control_unchanged(&self) {
            assert_eq!(
                fs::read(self.root.join(".scan-test-owner.json")).unwrap(),
                self.marker
            );
            assert_eq!(
                fs::read(self.root.join("installation-control.json")).unwrap(),
                b"{\"generation\":17}"
            );
        }
    }
    impl Drop for FileFixture {
        fn drop(&mut self) {
            // 只删除本次create_dir产生、路径与marker仍匹配的三个已知文件；不递归、不碰父根。
            if !self.root.is_absolute()
                || self.root.canonicalize().ok().as_ref() != Some(&self.canonical_root)
                || fs::symlink_metadata(&self.root).is_err()
                || fs::symlink_metadata(&self.root).is_ok_and(|m| m.file_type().is_symlink())
                || fs::read(self.root.join(".scan-test-owner.json"))
                    .ok()
                    .as_deref()
                    != Some(self.marker.as_slice())
            {
                return;
            }
            for name in [
                "record.bin",
                "installation-control.json",
                ".scan-test-owner.json",
            ] {
                let _ = fs::remove_file(self.root.join(name));
            }
            let _ = fs::remove_dir(&self.root);
        }
    }

    struct GatedFile {
        file: File,
        pause_after_reads: usize,
        reads: usize,
        actual_bytes: usize,
        gate: Option<(SyncSender<()>, Receiver<()>)>,
    }
    impl Read for GatedFile {
        fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
            if self.reads == self.pause_after_reads {
                let (notify, ready) = self.gate.take().expect("读取屏障只能执行一次");
                notify.send(()).map_err(io::Error::other)?;
                ready
                    .recv_timeout(FILE_GATE_TIMEOUT)
                    .map_err(io::Error::other)?;
            }
            let count = self.file.read(buffer)?;
            self.reads += 1;
            self.actual_bytes += count;
            Ok(count)
        }
    }
    #[derive(Clone, Copy)]
    enum GrowthStop {
        None,
        Cancel,
        Deadline,
    }
    fn growing_file(
        fixture: &FileFixture,
        pause_after_reads: usize,
        stop: GrowthStop,
        manager: &QueryTaskManager,
        task: &QueryHandle,
    ) -> (GatedFile, JoinHandle<()>) {
        let file = File::open(&fixture.path).unwrap();
        // metadata在真实读取前合规；后续增长必须由屏障发生在读取期间，不能靠sleep抢时序。
        assert_eq!(
            file.metadata().unwrap().len(),
            MAX_CONTROL_RECORD_BYTES as u64
        );
        let (notify, writing) = mpsc::sync_channel(1);
        let (written, ready) = mpsc::sync_channel(1);
        let path = fixture.path.clone();
        let manager = manager.clone();
        let task_id = task.task_id().to_owned();
        let deadline = task.deadline().unwrap();
        let writer = thread::spawn(move || {
            writing.recv_timeout(FILE_GATE_TIMEOUT).unwrap();
            let mut append = OpenOptions::new().append(true).open(path).unwrap();
            append.write_all(b"y").unwrap();
            append.flush().unwrap();
            drop(append);
            match stop {
                GrowthStop::None => {}
                GrowthStop::Cancel => {
                    manager.cancel(&task_id).unwrap();
                }
                GrowthStop::Deadline => {
                    // 等待同一个真实绝对deadline，不使用固定sleep或另造超时token。
                    let (hold, wait) = mpsc::channel::<()>();
                    let remaining = deadline.saturating_duration_since(Instant::now());
                    if !remaining.is_zero() {
                        assert!(matches!(
                            wait.recv_timeout(remaining),
                            Err(RecvTimeoutError::Timeout)
                        ));
                    }
                    drop(hold);
                }
            }
            written.send(()).unwrap();
        });
        (
            GatedFile {
                file,
                pause_after_reads,
                reads: 0,
                actual_bytes: 0,
                gate: Some((notify, ready)),
            },
            writer,
        )
    }

    fn handle(index: u64, timeout: Duration) -> (QueryTaskManager, QueryHandle) {
        let manager = QueryTaskManager::default();
        let target = QueryTarget {
            root: format!("F:/scan-memory-{index}"),
            release_id: "dev-contract".into(),
            engine_id: "kohya".into(),
            action: QueryAction::InspectReadonly,
            rebuild: false,
            scope: QueryScope::Full,
        };
        let identity = QueryIdentity {
            target: target.clone(),
            workspace_fence: format!("memory-{index}"),
            instance_id: None,
            generation: None,
            state_sha256: None,
            receipt_sha256: None,
            binding_sha256: None,
            lock_sha256: "1".repeat(64),
            recipe_sha256: "2".repeat(64),
        };
        let mut handle = manager
            .begin(target, QueryClock::start(timeout).unwrap())
            .unwrap()
            .handle;
        assert!(matches!(
            handle.resolve(identity).unwrap(),
            QueryResolution::Execute
        ));
        assert!(handle.try_start().unwrap());
        (manager, handle)
    }

    #[test]
    fn no_scope_is_noop() {
        assert!(observer().is_none());
        checkpoint(QueryStage::Source, u64::MAX, u64::MAX).unwrap();
        checkpoint(QueryStage::Source, 1, 1).unwrap();
        assert!(observer().is_none());
    }

    #[test]
    fn nested_scope_restores_outer_counts_and_observer() {
        let (outer_manager, outer) = handle(1, Duration::from_secs(10));
        let (inner_manager, inner) = handle(2, Duration::from_secs(10));
        with(&outer.observer(), || {
            checkpoint(QueryStage::Source, 1, 17)?;
            with(&inner.observer(), || checkpoint(QueryStage::Tools, 2, 23))?;
            inner_manager.cancel(inner.task_id()).unwrap();
            checkpoint(QueryStage::Source, 3, 29)?;
            Ok(())
        })
        .unwrap();
        let outer_snapshot = outer_manager.snapshot(outer.task_id()).unwrap();
        let inner_snapshot = inner_manager.snapshot(inner.task_id()).unwrap();
        assert_eq!(
            (outer_snapshot.progress.files, outer_snapshot.progress.bytes),
            (Some(4), Some(46))
        );
        assert_eq!(
            (inner_snapshot.progress.files, inner_snapshot.progress.bytes),
            (Some(2), Some(23))
        );
        assert!(observer().is_none());
    }

    #[test]
    fn error_and_panic_restore_previous_scope() {
        let (_, outer) = handle(3, Duration::from_secs(10));
        let (inner_manager, inner) = handle(4, Duration::from_secs(10));
        with(&outer.observer(), || {
            let error: Result<()> = with(&inner.observer(), || anyhow::bail!("fixture-error"));
            assert!(error.is_err());
            let panic = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                let _: Result<()> = with(&inner.observer(), || panic!("fixture-panic"));
            }));
            assert!(panic.is_err());
            inner_manager.cancel(inner.task_id()).unwrap();
            checkpoint(QueryStage::Source, 1, 11)?;
            Ok(())
        })
        .unwrap();
        assert!(observer().is_none());
    }

    #[test]
    fn same_observer_cancellation_and_deadline_propagate() {
        let (manager, task) = handle(5, Duration::from_secs(10));
        let result = with(&task.observer(), || {
            checkpoint(QueryStage::Source, 0, 65_536)?;
            manager.cancel(task.task_id()).unwrap();
            checkpoint(QueryStage::Source, 0, 65_536)
        });
        assert!(format!("{:#}", result.unwrap_err()).contains("取消"));
        let (_, task) = handle(6, Duration::from_millis(10));
        let result = with(&task.observer(), || {
            std::thread::sleep(Duration::from_millis(20));
            checkpoint(QueryStage::Receipt, 0, 0)
        });
        assert!(format!("{:#}", result.unwrap_err()).contains("期限"));
        assert!(observer().is_none());
    }

    #[test]
    fn observation_does_not_leak_to_other_threads() {
        let (manager, task) = handle(7, Duration::from_secs(10));
        with(&task.observer(), || {
            checkpoint(QueryStage::Environment, 1, 7)?;
            std::thread::spawn(|| {
                assert!(observer().is_none());
                checkpoint(QueryStage::Environment, 99, 999).unwrap();
            })
            .join()
            .unwrap();
            Ok(())
        })
        .unwrap();
        assert_eq!(
            manager.snapshot(task.task_id()).unwrap().progress.files,
            Some(1)
        );
    }

    #[test]
    fn control_record_limit_accepts_exact_and_rejects_one_extra_byte() {
        let fixture = FileFixture::new(MAX_CONTROL_RECORD_BYTES);
        let (manager, task) = handle(8, Duration::from_secs(60));
        let value = with(&task.observer(), || {
            read_file(&fixture.path, QueryStage::Receipt)
        })
        .unwrap();
        assert_eq!(value.len(), MAX_CONTROL_RECORD_BYTES);
        assert!(value.capacity() <= MAX_CONTROL_RECORD_BYTES);
        assert!(value.iter().all(|byte| *byte == b'x'));
        assert_eq!(
            manager.snapshot(task.task_id()).unwrap().progress.files,
            Some(1)
        );
        drop(value);
        OpenOptions::new()
            .append(true)
            .open(&fixture.path)
            .unwrap()
            .write_all(b"y")
            .unwrap();
        let (manager, task) = handle(9, Duration::from_secs(60));
        let error = with(&task.observer(), || {
            read_file(&fixture.path, QueryStage::Receipt)
        })
        .unwrap_err();
        let limit = error.downcast_ref::<ControlRecordLimit>().unwrap();
        assert_eq!(limit.buffered_bytes, MAX_CONTROL_RECORD_BYTES);
        assert!(limit.buffered_capacity <= MAX_CONTROL_RECORD_BYTES);
        assert_eq!(limit.incoming_bytes, 1);
        let snapshot = manager.snapshot(task.task_id()).unwrap();
        assert_eq!(
            snapshot.progress.bytes,
            Some(MAX_CONTROL_RECORD_BYTES as u64 + 1)
        );
        assert_eq!(snapshot.progress.files, Some(0));
        assert!(snapshot.worker.is_none());
        fixture.assert_control_unchanged();
        eprintln!("scan-limit exact={} rejected={} buffered={} capacity={} worker=false control_unchanged=true", MAX_CONTROL_RECORD_BYTES, MAX_CONTROL_RECORD_BYTES + 1, limit.buffered_bytes, limit.buffered_capacity);
    }

    #[test]
    fn control_record_limit_also_applies_without_observer() {
        let fixture = FileFixture::new(MAX_CONTROL_RECORD_BYTES + 1);
        assert!(observer().is_none());
        let error = read_file(&fixture.path, QueryStage::Receipt).unwrap_err();
        let limit = error.downcast_ref::<ControlRecordLimit>().unwrap();
        assert_eq!(limit.buffered_bytes, MAX_CONTROL_RECORD_BYTES);
        assert!(limit.buffered_capacity <= MAX_CONTROL_RECORD_BYTES);
        assert_eq!(limit.incoming_bytes, 1);
        fixture.assert_control_unchanged();
    }

    #[test]
    fn control_record_growth_after_metadata_is_bounded() {
        let fixture = FileFixture::new(MAX_CONTROL_RECORD_BYTES);
        let (manager, task) = handle(10, Duration::from_secs(60));
        let (mut file, writer) = growing_file(&fixture, 1, GrowthStop::None, &manager, &task);
        let result = with(&task.observer(), || {
            read_control_record(&mut file, QueryStage::Receipt)
        });
        writer.join().unwrap();
        let error = result.unwrap_err();
        let limit = error.downcast_ref::<ControlRecordLimit>().unwrap();
        assert_eq!(limit.buffered_bytes, MAX_CONTROL_RECORD_BYTES);
        assert!(limit.buffered_capacity <= MAX_CONTROL_RECORD_BYTES);
        assert_eq!(limit.incoming_bytes, 1);
        assert_eq!(file.actual_bytes, MAX_CONTROL_RECORD_BYTES + 1);
        assert_eq!(
            file.file.metadata().unwrap().len(),
            MAX_CONTROL_RECORD_BYTES as u64 + 1
        );
        let snapshot = manager.snapshot(task.task_id()).unwrap();
        assert_eq!(snapshot.progress.bytes, Some(file.actual_bytes as u64));
        assert_eq!(snapshot.progress.files, Some(0));
        assert!(snapshot.worker.is_none());
        fixture.assert_control_unchanged();
        eprintln!("scan-limit growth metadata={} actual_read={} buffered={} capacity={} worker=false control_unchanged=true", MAX_CONTROL_RECORD_BYTES, file.actual_bytes, limit.buffered_bytes, limit.buffered_capacity);
    }

    fn growth_stop_wins_over_limit(
        stop: GrowthStop,
        index: u64,
        expected: QueryStatus,
        code: &str,
    ) {
        let fixture = FileFixture::new(MAX_CONTROL_RECORD_BYTES);
        let timeout = if matches!(stop, GrowthStop::Deadline) {
            Duration::from_secs(10)
        } else {
            Duration::from_secs(60)
        };
        let (manager, task) = handle(index, timeout);
        // 已缓冲32MiB后同时追加超限字节和停止；证明停止错误优先于本块超限。
        let (mut file, writer) = growing_file(
            &fixture,
            MAX_CONTROL_RECORD_BYTES / READ_BLOCK_BYTES,
            stop,
            &manager,
            &task,
        );
        let result = with(&task.observer(), || {
            read_control_record(&mut file, QueryStage::Receipt)
        });
        writer.join().unwrap();
        let error = result.unwrap_err().downcast::<QueryError>().unwrap();
        assert_eq!(error.code, code);
        assert_eq!(file.actual_bytes, MAX_CONTROL_RECORD_BYTES + 1);
        let snapshot = manager.snapshot(task.task_id()).unwrap();
        assert_eq!(snapshot.progress.bytes, Some(file.actual_bytes as u64));
        assert_eq!(snapshot.progress.files, Some(0));
        assert!(snapshot.worker.is_none());
        let terminal = task
            .finish(Err(error), None, CleanupProof::no_worker_started())
            .unwrap();
        assert_eq!(terminal.status, expected);
        assert_eq!(terminal.progress.bytes, Some(file.actual_bytes as u64));
        assert!(terminal.worker.is_none());
        fixture.assert_control_unchanged();
        eprintln!("scan-limit stop={code} actual_read={} terminal={:?} worker=false control_unchanged=true", file.actual_bytes, terminal.status);
    }

    #[test]
    fn control_record_growth_cancel_keeps_authoritative_error_and_last_count() {
        growth_stop_wins_over_limit(
            GrowthStop::Cancel,
            11,
            QueryStatus::Cancelled,
            "query_cancelled",
        );
    }

    #[test]
    fn control_record_growth_timeout_keeps_authoritative_error_and_last_count() {
        growth_stop_wins_over_limit(
            GrowthStop::Deadline,
            12,
            QueryStatus::TimedOut,
            "query_timed_out",
        );
    }

    #[test]
    fn operation_pre_cancel_wins_before_open_without_affecting_cleanup_reads() {
        let fixture = FileFixture::new(9);
        let cancel = CancelToken::new();
        cancel.request();
        let error = read_file_controlled(
            fixture.root.join("missing-record.json"),
            QueryStage::Receipt,
            &cancel,
        )
        .unwrap_err();
        assert!(error
            .downcast_ref::<crate::operations::Cancelled>()
            .is_some());
        // 没有ambient Operation scope；必需保全仍能选择普通入口或全新token。
        assert_eq!(
            read_file(&fixture.path, QueryStage::Receipt).unwrap(),
            b"xxxxxxxxx"
        );
        assert_eq!(
            read_file_controlled(&fixture.path, QueryStage::Receipt, &CancelToken::new()).unwrap(),
            b"xxxxxxxxx"
        );
        fixture.assert_control_unchanged();
    }

    struct CancelOnCompletedFileRead {
        file: File,
        cancel: CancelToken,
        reads: usize,
        bytes: usize,
    }
    impl Read for CancelOnCompletedFileRead {
        fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
            let count = self.file.read(buffer)?;
            self.reads += 1;
            self.bytes += count;
            // 同步屏障就在真实File::read之后；不靠sleep争抢取消窗口。
            self.cancel.request();
            Ok(count)
        }
    }

    #[test]
    fn operation_cancel_at_actual_first_file_block_stops_next_read() {
        let fixture = FileFixture::new(READ_BLOCK_BYTES * 3);
        let cancel = CancelToken::new();
        let mut input = CancelOnCompletedFileRead {
            file: File::open(&fixture.path).unwrap(),
            cancel: cancel.clone(),
            reads: 0,
            bytes: 0,
        };
        let error =
            read_control_record_inner(&mut input, QueryStage::Receipt, Some(&cancel)).unwrap_err();
        assert!(error
            .downcast_ref::<crate::operations::Cancelled>()
            .is_some());
        assert_eq!(input.reads, 1);
        assert_eq!(input.bytes, READ_BLOCK_BYTES);
        fixture.assert_control_unchanged();
    }

    #[test]
    fn operation_first_block_cancel_preserves_query_count_and_query_priority() {
        let fixture = FileFixture::new(READ_BLOCK_BYTES * 2);
        let (manager, task) = handle(20, Duration::from_secs(60));
        let cancel = CancelToken::new();
        let mut input = CancelOnCompletedFileRead {
            file: File::open(&fixture.path).unwrap(),
            cancel: cancel.clone(),
            reads: 0,
            bytes: 0,
        };
        let error = with(&task.observer(), || {
            read_control_record_inner(&mut input, QueryStage::Receipt, Some(&cancel))
        })
        .unwrap_err();
        assert!(error
            .downcast_ref::<crate::operations::Cancelled>()
            .is_some());
        let snapshot = manager.snapshot(task.task_id()).unwrap();
        assert_eq!(snapshot.progress.bytes, Some(READ_BLOCK_BYTES as u64));
        assert_eq!(snapshot.progress.files, Some(0));
        assert_eq!(input.reads, 1);
        let error = with(&task.observer(), || {
            manager.cancel(task.task_id())?;
            read_file_controlled(&fixture.path, QueryStage::Receipt, &cancel)
        })
        .unwrap_err()
        .downcast::<QueryError>()
        .unwrap();
        assert_eq!(error.code, "query_cancelled");
        assert!(observer().is_none());
        fixture.assert_control_unchanged();
    }
}
