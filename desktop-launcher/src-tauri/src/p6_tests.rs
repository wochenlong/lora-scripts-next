//! P6真实回环网络、Job、跨进程中断恢复与租约争用；全部使用独立合成根。
use super::*;
use crate::model::WorkspaceMutation;
use crate::operations::{OperationKind, OperationManager};
use crate::recovery;
use std::io::Write;
use std::sync::mpsc;

#[path = "reliability_r0_core_probes.rs"]
mod reliability_r0_core_probes;

fn root(label: &str) -> PathBuf {
    let base = std::env::var_os("NEXT_TRAINER_P6_TEST_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let path = base.join(format!(
        "P6 中文 {label}-{}-{}",
        std::process::id(),
        stamp()
    ));
    fs::create_dir_all(&path).unwrap();
    path
}
fn release() -> String {
    format!("dev-{}", "a".repeat(40))
}
fn wait_file(path: &Path) {
    let started = Instant::now();
    while !path.is_file() {
        assert!(
            started.elapsed() < Duration::from_secs(10),
            "检查点超时: {}",
            path.display()
        );
        thread::sleep(Duration::from_millis(10));
    }
}
fn command(root: &Path, role: &str) -> Command {
    let mut command = Command::new(std::env::current_exe().unwrap());
    hidden(&mut command)
        .args([
            "--exact",
            "core::p6_tests::process_helper",
            "--ignored",
            "--nocapture",
        ])
        .env("NEXT_TRAINER_P6_CHILD_ROOT", root)
        .env("NEXT_TRAINER_P6_CHILD_ROLE", role);
    command
}
fn wait_child(child: &mut Child) -> std::process::ExitStatus {
    let started = Instant::now();
    loop {
        if let Some(status) = child.try_wait().unwrap() {
            return status;
        }
        if started.elapsed() > Duration::from_secs(10) {
            let _ = child.kill();
            let _ = child.wait();
            panic!("P6 helper未在10秒内结束");
        }
        thread::sleep(Duration::from_millis(10));
    }
}
fn validator(path: &Path) -> Result<()> {
    if fs::read(path)? != b"original package\n" {
        bail!("合成包语义验证失败");
    }
    Ok(())
}
fn fixture(root: &Path) -> (PathBuf, Vec<PathBuf>) {
    let ctx = WorkspaceMutation::acquire(root, &release()).unwrap();
    let target = PathBuf::from("staging/p6-synthetic/demo/package.py");
    fs::create_dir_all(root.join(target.parent().unwrap())).unwrap();
    fs::write(root.join(&target), b"original package\n").unwrap();
    let journal = PathBuf::from(format!("state/journal-{}.json", release()));
    Journal::new(&release()).unwrap().store(root).unwrap();
    let preserved = vec![
        PathBuf::from("profiles/default/profile.json"),
        PathBuf::from("staging/p6-synthetic/demo/other.py"),
        journal,
    ];
    fs::write(root.join(&preserved[1]), b"other unchanged\n").unwrap();
    recovery::initialize_synthetic(&ctx, "demo", &target, &preserved).unwrap();
    (target, preserved)
}

#[test]
fn stalled_http_cancel_does_not_wait_for_engine_or_body() {
    for headers_sent in [false, true] {
        let root = root(if headers_sent {
            "stalled-body"
        } else {
            "stalled-headers"
        });
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let address = listener.local_addr().unwrap();
        listener.set_nonblocking(true).unwrap();
        let (ready_tx, ready_rx) = mpsc::channel();
        let server = thread::spawn(move || {
            let deadline = Instant::now();
            let (mut socket, _) = loop {
                match listener.accept() {
                    Ok(pair) => break pair,
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                        assert!(deadline.elapsed() < Duration::from_secs(10));
                        thread::sleep(Duration::from_millis(10));
                    }
                    Err(e) => panic!("{e}"),
                }
            };
            // Windows accept继承监听socket的nonblocking；夹具用带超时的阻塞读确认关闭。
            socket.set_nonblocking(false).unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            let mut request = [0; 8192];
            let _ = socket.read(&mut request).unwrap();
            if headers_sent {
                socket
                    .write_all(
                        b"HTTP/1.1 200 OK\r\nContent-Length: 20000\r\nConnection: close\r\n\r\nx",
                    )
                    .unwrap();
                socket.flush().unwrap();
            }
            ready_tx.send(()).unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(3)))
                .unwrap();
            // 必须真正关闭连接；仅设置布尔值或返回但遗留读取线程不算通过。
            match socket.read(&mut request) {
                Ok(0) => {}
                Err(error)
                    if matches!(
                        error.kind(),
                        std::io::ErrorKind::ConnectionReset | std::io::ErrorKind::ConnectionAborted
                    ) => {}
                other => panic!("取消未关闭socket：{other:?}"),
            }
        });
        let manager = OperationManager::default();
        let operation = manager
            .start("download-p6", OperationKind::Download)
            .unwrap();
        let cancel = operation.cancel_token();
        let worker_root = root.clone();
        let engine_lock = Arc::new(Mutex::new(()));
        let worker_lock = engine_lock.clone();
        let worker = thread::spawn(move || {
            let _long_engine_lock = worker_lock.lock().unwrap();
            let ctx = WorkspaceMutation::acquire(&worker_root, &release()).unwrap();
            let client = reqwest::Client::builder()
                .no_proxy()
                .timeout(Duration::from_secs(30))
                .build()
                .unwrap();
            download_controlled(
                &ctx,
                client,
                &format!("http://{address}/asset"),
                "asset.bin",
                &"0".repeat(64),
                100000,
                &cancel,
            )
        });
        ready_rx.recv_timeout(Duration::from_secs(5)).unwrap();
        let started = Instant::now();
        manager.snapshot("download-p6").unwrap();
        manager.cancel("download-p6").unwrap();
        assert!(started.elapsed() < Duration::from_millis(200));
        assert!(worker.join().unwrap().is_err());
        assert!(started.elapsed() < Duration::from_secs(2));
        assert!(!root.join("cache/asset.bin").exists());
        server.join().unwrap();
        println!(
            "P6 stalled_headers={}: cancel_and_close_ms={}",
            !headers_sent,
            started.elapsed().as_millis()
        );
    }
}

#[test]
fn controlled_transfer_requires_complete_hash_before_publication() {
    for correct_hash in [true, false] {
        let root = root("verified-transfer");
        let ctx = WorkspaceMutation::acquire(&root, &release()).unwrap();
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let address = listener.local_addr().unwrap();
        let server = thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            let mut request = [0u8; 8192];
            assert!(socket.read(&mut request).unwrap() > 0);
            socket
                .write_all(
                    b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello",
                )
                .unwrap();
        });
        let expected = if correct_hash {
            format!("{:x}", Sha256::digest(b"hello"))
        } else {
            "0".repeat(64)
        };
        let client = reqwest::Client::builder()
            .no_proxy()
            .timeout(Duration::from_secs(5))
            .build()
            .unwrap();
        let token = crate::operations::CancelToken::new();
        let result = download_controlled(
            &ctx,
            client,
            &format!("http://{address}/asset"),
            "asset.bin",
            &expected,
            10,
            &token,
        );
        assert_eq!(result.is_ok(), correct_hash);
        assert_eq!(root.join("cache/asset.bin").exists(), correct_hash);
        if correct_hash {
            assert_eq!(fs::read(result.unwrap()).unwrap(), b"hello");
        }
        server.join().unwrap();
    }
}

#[test]
fn killed_controller_recovers_in_another_process_and_preserves_v1() {
    let root = root("crash-recovery");
    let (target, preserved) = fixture(&root);
    let before: Vec<_> = preserved
        .iter()
        .map(|p| fs::read(root.join(p)).unwrap())
        .collect();
    let mut controller = command(&root, "mutate").spawn().unwrap();
    wait_file(&root.join("run/changed-ready"));
    assert_eq!(
        fs::read(root.join(&target)).unwrap(),
        b"changed before commit\n"
    );
    controller.kill().unwrap();
    controller.wait().unwrap();
    let layout = Layout::new(&root, &release()).unwrap();
    let interrupted = recovery::load(&layout, "demo").unwrap();
    assert!(interrupted.dirty);
    assert!(recovery::assert_usable(&interrupted).is_err());
    let mut process = command(&root, "recover").spawn().unwrap();
    assert!(wait_child(&mut process).success());
    let restored = recovery::load(&layout, "demo").unwrap();
    assert!(!restored.dirty);
    recovery::assert_usable(&restored).unwrap();
    validator(&root.join(target)).unwrap();
    for (path, original) in preserved.iter().zip(before) {
        assert_eq!(fs::read(root.join(path)).unwrap(), original);
    }
    println!(
        "P6 kill-controller -> independent-process recover: {}",
        root.display()
    );
}

#[test]
fn other_process_cannot_take_workspace_lease() {
    let root = root("lease-contention");
    let _mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let mut contender = command(&root, "lease-denied").spawn().unwrap();
    assert!(wait_child(&mut contender).success());
    assert!(root.join("run/lease-rejected").exists());
}

#[test]
fn controlled_failure_preserves_stderr_reason_and_logs() {
    let root = root("controlled-failure");
    let _mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let lines = Arc::new(Mutex::new(Vec::new()));
    let captured = lines.clone();
    let log: Logger = Arc::new(move |line| captured.lock().unwrap().push(line));
    let error = execute_controlled(
        command(&root, "controlled-failure"),
        &log,
        &crate::operations::CancelToken::new(),
    )
    .unwrap_err();
    assert!(error
        .downcast_ref::<crate::operations::Cancelled>()
        .is_none());
    let detail = format!("{error:#}");
    assert!(detail.contains("子任务失败"));
    assert!(detail.contains("[stderr]"));
    assert!(detail.contains("ModuleNotFoundError: No module named pip"));
    assert!(lines
        .lock()
        .unwrap()
        .iter()
        .any(|line| line.contains("ModuleNotFoundError: No module named pip")));
}

#[test]
fn controlled_large_output_is_bounded_utf8_and_failed_state_is_readable() {
    let root = root("controlled-large-output");
    let mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let manager = OperationManager::default();
    let operation = manager
        .start("controlled-large-failure", OperationKind::Execute)
        .unwrap();
    operation.persist(&mutation).unwrap();
    let longest = Arc::new(Mutex::new(0));
    let observed = longest.clone();
    let log: Logger = Arc::new(move |line| {
        let mut longest = observed.lock().unwrap();
        *longest = (*longest).max(line.len());
    });
    let error = execute_controlled(
        command(&root, "controlled-large-failure"),
        &log,
        &operation.cancel_token(),
    )
    .unwrap_err();
    let detail = format!("{error:#}");
    let detail_path = root.join("run/controlled-failure-detail.txt");
    fs::write(&detail_path, &detail).unwrap();
    println!("受控大输出失败详情已保存：{}", detail_path.display());
    assert!(detail.contains("输出已截断"));
    assert!(detail.contains("ModuleNotFoundError: No module named pip"));
    assert!(!detail.contains('\u{fffd}'), "合法UTF-8输出不能因裁剪损坏");
    assert!(!detail.contains("fake-private-value"));
    assert!(serde_json::to_vec(&detail).unwrap().len() < 50 * 1024);
    assert!(*longest.lock().unwrap() < 3 * CONTROLLED_LINE_LIMIT + 128);
    operation
        .finish_and_persist(
            &mutation,
            crate::operations::OperationStatus::Failed,
            Some(crate::operations::OperationError {
                code: "controlled_probe_failed".into(),
                message: detail,
            }),
        )
        .unwrap();
    let records = crate::operations::load_snapshots(mutation.layout()).unwrap();
    let persisted = records
        .iter()
        .find(|snapshot| snapshot.id == "controlled-large-failure")
        .unwrap();
    assert_eq!(persisted.status, crate::operations::OperationStatus::Failed);
    assert!(persisted
        .error
        .as_ref()
        .unwrap()
        .message
        .contains("ModuleNotFoundError: No module named pip"));
}

#[test]
fn controlled_stderr_warning_does_not_turn_success_into_failure() {
    let root = root("controlled-success-warning");
    let _mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let log: Logger = Arc::new(|_| {});
    execute_controlled(
        command(&root, "controlled-success-warning"),
        &log,
        &crate::operations::CancelToken::new(),
    )
    .unwrap();
}

#[test]
fn controlled_output_tail_reserves_its_bounded_capacity_for_stderr() {
    let mut tail = ControlledOutputTail::default();
    tail.append(false, &vec![b'x'; 100_000]);
    assert!(tail.stdout.len() + tail.stderr.len() <= CONTROLLED_OUTPUT_LIMIT);
    tail.append(true, &vec![b'y'; 100_000]);
    tail.append(false, &vec![b'z'; 100_000]);
    assert!(tail.stdout.len() + tail.stderr.len() <= CONTROLLED_OUTPUT_LIMIT);
    assert!(tail.stdout.is_empty());
    assert!(tail.truncated);
}

#[test]
fn cancel_child_reaps_owned_descendant_and_preserves_unrelated_process() {
    let root = root("job-cancel");
    let _mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let mut unrelated = command(&root, "unrelated").spawn().unwrap();
    wait_file(&root.join("run/unrelated-ready"));
    let manager = OperationManager::default();
    let operation = manager.start("execute-p6", OperationKind::Execute).unwrap();
    let token = operation.cancel_token();
    let cmd = command(&root, "slow");
    let callback_root = root.clone();
    let log: Logger = Arc::new(move |line| {
        if line.starts_with("受管子进程已绑定Job：") {
            fs::write(callback_root.join("run/job-attached"), line).unwrap();
        } else if line.starts_with("受管Job已排空：") {
            fs::write(callback_root.join("run/job-reaped"), line).unwrap();
        }
    });
    let worker = thread::spawn(move || execute_controlled(cmd, &log, &token));
    wait_file(&root.join("run/descendant-ready"));
    let descendant: u32 = fs::read_to_string(root.join("run/descendant-ready"))
        .unwrap()
        .parse()
        .unwrap();
    // 在取消前固定本代进程 handle；不能在返回后再按 PID 打开/等待补证明。
    let descendant = HeldProcess::open(descendant);
    let started = Instant::now();
    manager.cancel("execute-p6").unwrap();
    let error = worker.join().unwrap().unwrap_err();
    assert!(error
        .downcast_ref::<crate::operations::Cancelled>()
        .is_some());
    assert!(started.elapsed() < Duration::from_secs(2));
    descendant.assert_exited_now();
    assert!(fs::read_to_string(root.join("run/job-reaped"))
        .unwrap()
        .contains("active=0"));
    assert!(unrelated.try_wait().unwrap().is_none());
    fs::write(root.join("run/unrelated-stop"), b"stop").unwrap();
    assert!(wait_child(&mut unrelated).success());
    println!(
        "P6 Job cancel ms={}, unrelated helper survived",
        started.elapsed().as_millis()
    );
}

struct HeldProcess(windows_sys::Win32::Foundation::HANDLE);

impl HeldProcess {
    fn open(pid: u32) -> Self {
        let handle = unsafe {
            windows_sys::Win32::System::Threading::OpenProcess(
                windows_sys::Win32::System::Threading::PROCESS_SYNCHRONIZE
                    | windows_sys::Win32::System::Threading::PROCESS_TERMINATE,
                0,
                pid,
            )
        };
        assert!(!handle.is_null(), "必须在受测进程仍运行时取得本代 handle");
        Self(handle)
    }

    fn assert_exited_now(&self) {
        assert_eq!(
            unsafe { windows_sys::Win32::System::Threading::WaitForSingleObject(self.0, 0) },
            windows_sys::Win32::Foundation::WAIT_OBJECT_0,
            "executor 返回时本代后代必须已经退出，不允许追加宽限等待"
        );
    }

    fn wait_exited(&self) {
        assert_eq!(
            unsafe { windows_sys::Win32::System::Threading::WaitForSingleObject(self.0, 5000) },
            windows_sys::Win32::Foundation::WAIT_OBJECT_0,
            "本案已持有的精确进程handle未在5秒内退出"
        );
    }

    fn assert_running_now(&self) {
        assert_eq!(
            unsafe { windows_sys::Win32::System::Threading::WaitForSingleObject(self.0, 0) },
            windows_sys::Win32::Foundation::WAIT_TIMEOUT,
        );
    }

    fn terminate_owned_fixture(&self) {
        assert_ne!(
            unsafe { windows_sys::Win32::System::Threading::TerminateProcess(self.0, 77) },
            0,
            "只能通过测试提前持有的本代handle回收合成悬挂进程"
        );
        self.wait_exited();
    }
}

impl Drop for HeldProcess {
    fn drop(&mut self) {
        unsafe {
            windows_sys::Win32::Foundation::CloseHandle(self.0);
        }
    }
}

#[test]
fn controlled_success_reaps_descendant_without_inherited_pipes() {
    let root = root("job-parent-success");
    let _mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let callback_root = root.clone();
    let log: Logger = Arc::new(move |line| {
        if line.starts_with("受管Job已排空：") {
            fs::write(callback_root.join("run/job-reaped"), line).unwrap();
        }
    });
    let cmd = command(&root, "parent-success-descendant");
    let worker = thread::spawn(move || {
        execute_controlled(cmd, &log, &crate::operations::CancelToken::new())
    });
    wait_file(&root.join("run/descendant-ready"));
    let pid = fs::read_to_string(root.join("run/descendant-ready"))
        .unwrap()
        .parse()
        .unwrap();
    let descendant = HeldProcess::open(pid);
    fs::write(root.join("run/allow-parent-exit"), b"exit0").unwrap();
    worker.join().unwrap().unwrap();
    descendant.assert_exited_now();
    assert!(fs::read_to_string(root.join("run/job-reaped"))
        .unwrap()
        .contains("active=0"));
}

#[test]
fn reap_failure_has_priority_over_cancel_without_cancelled_source() {
    // 私有收尾接缝故障注入，只证明类型/优先级，不冒称真实 OS 排空失败。
    let error = controlled_reap_result(
        Err(crate::operations::Cancelled.into()),
        Err(anyhow!("synthetic QueryInformationJobObject failure")),
        true,
    )
    .unwrap_err();
    let failure = error.downcast_ref::<ControlledProcessReapFailed>().unwrap();
    assert_eq!(failure.code, "worker_reap_failed");
    assert!(failure.cancel_requested);
    assert!(error
        .downcast_ref::<crate::operations::Cancelled>()
        .is_none());
    assert!(format!("{error:#}").contains("synthetic"));
}

#[test]
fn lifecycle_finalize_persists_reap_failure_before_cancel_and_keeps_other_results() {
    use crate::operations::{CancelReceipt, Cancelled, OperationStatus};
    let root = root("lifecycle-finalize-reap");
    let mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let manager = OperationManager::default();
    for case in [
        "reap",
        "reap-with-cancel-source",
        "cancel",
        "ordinary",
        "success",
    ] {
        let operation = manager.start(case, OperationKind::Repair).unwrap();
        let result = match case {
            "reap" | "reap-with-cancel-source" => {
                assert_eq!(manager.cancel(case).unwrap(), CancelReceipt::Accepted);
                let mut failure =
                    ControlledProcessReapFailed::new("synthetic reader stall".into(), true);
                failure.requires_new_host = true;
                let error = anyhow::Error::new(failure);
                Err(if case == "reap-with-cancel-source" {
                    error.context(Cancelled)
                } else {
                    error
                })
            }
            "cancel" => {
                assert_eq!(manager.cancel(case).unwrap(), CancelReceipt::Accepted);
                Err(Cancelled.into())
            }
            "ordinary" => Err(anyhow!("synthetic ordinary failure")),
            _ => Ok(()),
        };
        let result = finish_gui_lifecycle_result(&mutation, &operation, result);
        let snapshots = crate::operations::load_snapshots(mutation.layout()).unwrap();
        let saved = snapshots.iter().find(|value| value.id == case).unwrap();
        let mut live = manager.snapshot(case).unwrap();
        live.event_seq = 0;
        assert_eq!(*saved, live);
        match case {
            "reap" | "reap-with-cancel-source" => {
                assert!(
                    result
                        .unwrap_err()
                        .downcast_ref::<ControlledProcessReapFailed>()
                        .unwrap()
                        .requires_new_host
                );
                assert_eq!(saved.status, OperationStatus::Failed);
                assert_eq!(saved.error.as_ref().unwrap().code, "worker_reap_failed");
                assert!(saved.cancel_requested);
            }
            "cancel" => {
                assert!(result.unwrap_err().downcast_ref::<Cancelled>().is_some());
                assert_eq!(saved.status, OperationStatus::Cancelled);
                assert!(saved.error.is_none());
            }
            "ordinary" => {
                assert!(result.is_err());
                assert_eq!(saved.status, OperationStatus::Failed);
                assert_eq!(saved.error.as_ref().unwrap().code, "gui_lifecycle_failed");
            }
            _ => {
                result.unwrap();
                assert_eq!(saved.status, OperationStatus::Succeeded);
                assert!(saved.error.is_none());
            }
        }
    }
}

#[test]
fn lifecycle_finalize_persistence_failure_keeps_reap_error_and_reports_unsaved_state() {
    use crate::operations::OperationStatus;
    let root = root("lifecycle-finalize-unsaved-reap");
    let mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let manager = OperationManager::default();
    let operation = manager
        .start("unsaved-reap", OperationKind::Repair)
        .unwrap();
    operation.persist(&mutation).unwrap();
    let path = root.join("state/operations/unsaved-reap.json");
    let before = fs::read(&path).unwrap();
    // 合成未知控制文件令真实持久化门拒绝；不得把它当作写入成功。
    fs::write(root.join("state/operations/foreign.txt"), b"preserve").unwrap();
    let mut failure = ControlledProcessReapFailed::new("synthetic reader not joined".into(), true);
    failure.requires_new_host = true;
    let error =
        finish_gui_lifecycle_result(&mutation, &operation, Err(failure.into())).unwrap_err();
    assert!(
        error
            .downcast_ref::<ControlledProcessReapFailed>()
            .unwrap()
            .requires_new_host
    );
    assert!(error.to_string().contains("操作终态未能保存"));
    assert_eq!(fs::read(path).unwrap(), before);
    let live = manager.snapshot("unsaved-reap").unwrap();
    assert_eq!(live.status, OperationStatus::Failed);
    assert_eq!(
        live.error.as_ref().unwrap().code,
        "operation_state_write_failed"
    );
}

#[test]
fn controlled_reader_failure_is_not_reported_as_success_or_cancelled() {
    let stop = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let reader = thread::spawn(|| -> Result<()> { bail!("synthetic pipe read failure") });
    let readers = join_controlled_readers(vec![reader.into()], &stop, true);
    let error = controlled_reap_result(Err(crate::operations::Cancelled.into()), readers, true)
        .unwrap_err();
    assert_eq!(
        error
            .downcast_ref::<ControlledProcessReapFailed>()
            .unwrap()
            .code,
        "worker_reap_failed"
    );
    assert!(error
        .downcast_ref::<crate::operations::Cancelled>()
        .is_none());
    assert!(format!("{error:#}").contains("synthetic pipe read failure"));
    assert!(
        !error
            .downcast_ref::<ControlledProcessReapFailed>()
            .unwrap()
            .requires_new_host
    );
}

#[test]
fn controlled_reader_stall_returns_bounded_reap_failure() {
    // 私有线程收尾接缝：模拟不响应CancelSynchronousIo的回调，不声称OS故障。
    let stop = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let (release, wait) = mpsc::channel();
    let (ended, done) = mpsc::channel();
    let reader = thread::spawn(move || -> Result<()> {
        wait.recv().unwrap();
        ended.send(()).unwrap();
        Ok(())
    });
    let started = Instant::now();
    let readers = join_controlled_readers(vec![reader.into()], &stop, false);
    let elapsed = started.elapsed();
    // 先解除本案夹具，避免后面的断言失败遗留阻塞线程。
    release.send(()).unwrap();
    done.recv_timeout(Duration::from_secs(2)).unwrap();
    assert!(elapsed < Duration::from_secs(3));
    let error = controlled_reap_result(Err(crate::operations::Cancelled.into()), readers, true)
        .unwrap_err();
    assert!(error
        .downcast_ref::<ControlledProcessReapFailed>()
        .is_some());
    assert!(
        error
            .downcast_ref::<ControlledProcessReapFailed>()
            .unwrap()
            .requires_new_host
    );
    assert!(error
        .downcast_ref::<crate::operations::Cancelled>()
        .is_none());
    assert!(stop.load(std::sync::atomic::Ordering::Acquire));
}

fn controlled_blocking_logger_cancel_contract(label: &str, blocked_prefix: &'static str) {
    let root = root(label);
    let _mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let manager = OperationManager::default();
    let operation = manager
        .start("blocking-logger", OperationKind::Execute)
        .unwrap();
    let cancel = operation.cancel_token();
    let job = Job::create_named(&Job::generate_legacy_repair_name().unwrap()).unwrap();
    let (release, resumed) = mpsc::channel();
    let resumed = Mutex::new(resumed);
    let (blocked, waiting) = mpsc::channel();
    let (logger_exited, logger_done) = mpsc::channel();
    let log: Logger = Arc::new(move |line| {
        if line.starts_with(blocked_prefix) {
            blocked
                .send(unsafe { windows_sys::Win32::System::Threading::GetCurrentThreadId() })
                .unwrap();
            resumed
                .lock()
                .unwrap()
                .recv_timeout(Duration::from_secs(10))
                .unwrap();
            logger_exited.send(()).unwrap();
        }
    });
    let (attached, child_pid) = mpsc::channel();
    let (finished, outcome) = mpsc::channel();
    let cmd = command(&root, "logger-blocking-worker");
    let worker = thread::spawn(move || {
        let result = execute_controlled_in_job(cmd, &log, &cancel, &job, |pid| {
            attached.send(pid).unwrap();
            Ok(())
        });
        finished.send((result, job)).unwrap();
    });
    let child = HeldProcess::open(child_pid.recv_timeout(Duration::from_secs(5)).unwrap());
    wait_file(&root.join("run/descendant-ready"));
    let descendant = HeldProcess::open(
        fs::read_to_string(root.join("run/descendant-ready"))
            .unwrap()
            .parse()
            .unwrap(),
    );
    let logger_thread_id = waiting.recv_timeout(Duration::from_secs(5)).unwrap();
    let logger_thread = unsafe {
        windows_sys::Win32::System::Threading::OpenThread(
            windows_sys::Win32::System::Threading::THREAD_SYNCHRONIZE,
            0,
            logger_thread_id,
        )
    };
    assert!(!logger_thread.is_null());
    wait_file(&root.join("run/logger-flood-complete"));
    let started = Instant::now();
    manager.cancel("blocking-logger").unwrap();
    // 真实executor必须在Logger仍被本案卡住时返回；不可先释放回调再凑通过。
    let first = outcome.recv_timeout(Duration::from_secs(5));
    let bounded = first.is_ok();
    let elapsed = started.elapsed();
    let logger_still_blocked = logger_done.try_recv().is_err();
    release.send(()).unwrap();
    logger_done.recv_timeout(Duration::from_secs(2)).unwrap();
    let logger_thread_exited =
        unsafe { windows_sys::Win32::System::Threading::WaitForSingleObject(logger_thread, 2000) };
    unsafe {
        windows_sys::Win32::Foundation::CloseHandle(logger_thread);
    }
    let (result, job) = first
        .or_else(|_| outcome.recv_timeout(Duration::from_secs(5)))
        .unwrap();
    worker.join().unwrap();
    assert!(bounded && elapsed < Duration::from_secs(5));
    assert!(logger_still_blocked);
    assert_eq!(
        logger_thread_exited,
        windows_sys::Win32::Foundation::WAIT_OBJECT_0
    );
    assert_eq!(job.active_processes().unwrap(), 0);
    child.assert_exited_now();
    descendant.assert_exited_now();
    let error = result.unwrap_err();
    let failure = error.downcast_ref::<ControlledProcessReapFailed>().unwrap();
    assert_eq!(failure.code, "worker_reap_failed");
    assert!(failure.cancel_requested && failure.requires_new_host);
    assert!(error
        .downcast_ref::<crate::operations::Cancelled>()
        .is_none());
    let detail = format!("{error:#}");
    assert!(detail.contains("累计省略展示日志数="));
    assert!(
        !detail.contains("累计省略展示日志数=0"),
        "阻塞时的日志洪泛须有明确丢弃计数"
    );
}

#[test]
fn controlled_lifecycle_logger_block_does_not_block_cancel_or_reap() {
    controlled_blocking_logger_cancel_contract("blocking-lifecycle-log", "受管子进程已绑定Job：");
}

#[test]
fn controlled_output_logger_block_does_not_block_cancel_or_reap() {
    controlled_blocking_logger_cancel_contract("blocking-output-log", "P6_CONTROLLED_LOG_BLOCK");
}

#[test]
fn controlled_pipe_reader_cancels_blocked_sync_io_and_joins() {
    let root = root("controlled-reader-sync-io");
    let _mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let mut holder = command(&root, "pipe-holder")
        .stdout(Stdio::piped())
        .stderr(Stdio::from(
            File::create(root.join("run/pipe-holder-stderr.txt")).unwrap(),
        ))
        .spawn()
        .unwrap();
    wait_file(&root.join("run/pipe-holder-ready"));
    use std::os::windows::io::AsHandle;
    let pipe_cancel = holder
        .stdout
        .as_ref()
        .unwrap()
        .as_handle()
        .try_clone_to_owned()
        .unwrap();
    // 先读尽Rust测试宿主前缀，marker后writer等待本案stop而不再输出。
    let mut prefix = BufReader::new(holder.stdout.take().unwrap());
    loop {
        let mut line = String::new();
        assert_ne!(prefix.read_line(&mut line).unwrap(), 0);
        if line.trim() == "P6_PIPE_BLOCK_READY" {
            break;
        }
    }
    struct NotifyingReader(std::process::ChildStdout, Option<mpsc::Sender<()>>);
    impl Read for NotifyingReader {
        fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
            if let Some(started) = self.1.take() {
                started.send(()).unwrap();
            }
            self.0.read(buffer)
        }
    }
    let (started, reading) = mpsc::channel();
    let stop = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let reader_stop = stop.clone();
    let pipe = NotifyingReader(prefix.into_inner(), Some(started));
    let log: Logger = Arc::new(|_| {});
    let reader = thread::spawn(move || {
        read_controlled_pipe(
            Box::new(pipe),
            false,
            log,
            Arc::new(Mutex::new(ControlledOutputTail::default())),
            reader_stop,
        )
    });
    reading.recv_timeout(Duration::from_secs(2)).unwrap();
    let started = Instant::now();
    let readers = join_controlled_readers(
        vec![ControlledReader {
            worker: reader,
            pipe: Some(pipe_cancel),
        }],
        &stop,
        false,
    );
    let elapsed = started.elapsed();
    // writer保持运行直到取消reader已返回，证明不是writer自然关闭解开ReadFile。
    let holder_alive = holder.try_wait().unwrap().is_none();
    let stopped = stop.load(std::sync::atomic::Ordering::Acquire);
    let reader_failure = readers
        .as_ref()
        .err()
        .and_then(|error| error.downcast_ref::<ControlledReaderReapFailed>());
    let result_path = root.join("run/pipe-reader-cancel-result.json");
    let result_detail = serde_json::json!({
        "scope": "real synchronous pipe cancellation; writer has not received stop",
        "elapsed_ms": elapsed.as_secs_f64() * 1000.0,
        "writer_alive_before_stop": holder_alive,
        "stop_requested": stopped,
        "reader_result": if readers.is_ok() { "joined_ok" } else { "error" },
        "typed_reader_failure": reader_failure.is_some(),
        "unjoined": reader_failure.map(|failure| failure.unjoined),
        "read_os_errors": reader_failure.map(|failure| &failure.read_os_errors),
        "error": readers.as_ref().err().map(|error| format!("{error:#}")),
    });
    // 必须在任何语义断言前保存真实结果，不能只打印猜测的Windows错误字符串。
    durable_checkpoint(
        &result_path,
        &serde_json::to_vec_pretty(&result_detail).unwrap(),
    );
    fs::write(root.join("run/pipe-holder-stop"), b"stop").unwrap();
    let holder_status = wait_child(&mut holder);
    assert!(
        holder_status.success(),
        "pipe holder {holder_status}: {}",
        fs::read_to_string(root.join("run/pipe-holder-stderr.txt")).unwrap()
    );
    assert_eq!(
        fs::read(root.join("run/pipe-holder-stopped")).unwrap(),
        b"stop acknowledged"
    );
    assert!(holder_alive);
    assert!(elapsed < Duration::from_secs(2));
    assert!(stopped, "{}: {result_detail}", result_path.display());
    match readers {
        // ERROR_OPERATION_ABORTED可能映射Interrupted，reader回到循环顶端看到stop后正常退出。
        Ok(()) => {}
        Err(error) => {
            let failure = error
                .downcast_ref::<ControlledReaderReapFailed>()
                .unwrap_or_else(|| {
                    panic!("未知reader失败 {}: {result_detail}", result_path.display())
                });
            assert!(
                !failure.unjoined,
                "reader必须实际join {}: {result_detail}",
                result_path.display()
            );
            assert!(
                failure.read_os_errors.is_empty() || failure.read_os_errors == [Some(995)],
                "仅接受已join的ERROR_OPERATION_ABORTED，未知读取错误不能授通过: {result_detail}"
            );
            assert!(
                failure
                    .message
                    .contains("输出线程读取错误：受管输出读取失败")
                    || failure
                        .message
                        .contains("输出未在正常收尾内结束，已请求停止同步读取"),
                "未分类取消原因 {}: {result_detail}",
                result_path.display()
            );
        }
    }
}

#[test]
fn named_job_rejects_collision_and_invalid_names() {
    let name = Job::generate_legacy_repair_name().unwrap();
    Job::validate_legacy_repair_name(&name).unwrap();
    let job = Job::create_named(&name).unwrap();
    assert!(Job::create_named(&name).is_err());
    assert!(Job::validate_legacy_repair_name("Global\\unrelated").is_err());
    assert!(Job::validate_legacy_repair_name(&format!("{name}x")).is_err());
    let reopened = Job::reopen_named(&name).unwrap().unwrap();
    assert_eq!(reopened.active_processes().unwrap(), 0);
    drop(reopened);
    drop(job);
    assert!(Job::reopen_named(&name).unwrap().is_none());
}

#[test]
fn named_job_killed_controller_reopens_and_drains_in_another_process() {
    let root = root("named-job-crash");
    let _mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let name = Job::generate_legacy_repair_name().unwrap();
    fs::write(root.join("run/named-job-name"), &name).unwrap();
    let mut controller = command(&root, "named-controller").spawn().unwrap();
    wait_file(&root.join("run/named-attached"));
    wait_file(&root.join("run/descendant-ready"));
    let pid = fs::read_to_string(root.join("run/descendant-ready"))
        .unwrap()
        .parse()
        .unwrap();
    let descendant = HeldProcess::open(pid);
    // 额外持有精确命名 Job，确定性覆盖恢复 Open 成功分支；不允许其创建新空 Job。
    let held_job = Job::reopen_named(&name).unwrap().unwrap();
    assert!(held_job.active_processes().unwrap() >= 2);
    controller.kill().unwrap();
    controller.wait().unwrap();
    let mut recover = command(&root, "named-recover").spawn().unwrap();
    assert!(wait_child(&mut recover).success());
    descendant.assert_exited_now();
    assert_eq!(held_job.active_processes().unwrap(), 0);
    assert_eq!(
        fs::read_to_string(root.join("run/named-reaped")).unwrap(),
        "opened active=0"
    );
    drop(held_job);
    assert!(Job::reopen_named(&name).unwrap().is_none());
}

fn durable_checkpoint(path: &Path, bytes: &[u8]) {
    let pending = path.with_extension("checkpoint-tmp");
    let mut file = File::options()
        .create_new(true)
        .write(true)
        .open(&pending)
        .unwrap();
    file.write_all(bytes).unwrap();
    file.sync_all().unwrap();
    drop(file);
    fs::rename(pending, path).unwrap();
}

fn named_attached_process(root: &Path) -> HeldProcess {
    let attached = fs::read_to_string(root.join("run/named-attached")).unwrap();
    let pid = attached.split('/').nth(1).unwrap().parse().unwrap();
    HeldProcess::open(pid)
}

#[test]
fn named_job_attached_without_extra_handle_is_destroyed_after_controller_kill() {
    let root = root("named-job-no-extra-handle");
    let _mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let name = Job::generate_legacy_repair_name().unwrap();
    durable_checkpoint(&root.join("run/named-job-name"), name.as_bytes());
    let mut controller = command(&root, "named-controller").spawn().unwrap();
    wait_file(&root.join("run/named-attached"));
    wait_file(&root.join("run/descendant-ready"));
    let child = named_attached_process(&root);
    let pid = fs::read_to_string(root.join("run/descendant-ready"))
        .unwrap()
        .parse()
        .unwrap();
    let descendant = HeldProcess::open(pid);
    // 此分支从不在控制器生存时额外打开命名Job；强杀关闭唯一非继承handle。
    controller.kill().unwrap();
    controller.wait().unwrap();
    child.wait_exited();
    descendant.wait_exited();
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        match Job::reopen_named(&name).unwrap() {
            None => break,
            Some(job) => {
                assert_eq!(job.active_processes().unwrap(), 0);
                drop(job);
                assert!(Instant::now() < deadline, "已排空对象尚未销毁");
                thread::sleep(Duration::from_millis(10));
            }
        }
    }
    let mut recover = command(&root, "named-recover-destroyed").spawn().unwrap();
    assert!(wait_child(&mut recover).success());
    assert_eq!(
        fs::read_to_string(root.join("run/named-reaped")).unwrap(),
        "destroyed after attached"
    );
    child.assert_exited_now();
    descendant.assert_exited_now();
}

#[test]
fn named_job_launching_without_attached_refuses_despite_notfound() {
    let root = root("named-job-unattached-window");
    let _mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let name = Job::generate_legacy_repair_name().unwrap();
    durable_checkpoint(&root.join("run/named-job-name"), name.as_bytes());
    let mut controller = command(&root, "named-unattached-controller")
        .spawn()
        .unwrap();
    wait_file(&root.join("run/named-launching-child"));
    let launching = fs::read_to_string(root.join("run/named-launching-child")).unwrap();
    let pid = launching.split('/').nth(1).unwrap().parse().unwrap();
    let suspended = HeldProcess::open(pid);
    controller.kill().unwrap();
    controller.wait().unwrap();
    assert!(Job::reopen_named(&name).unwrap().is_none());
    let mut recover = command(&root, "named-recover-launching").spawn().unwrap();
    let recover_status = wait_child(&mut recover);
    // 悬挂child仍活是该歧义窗口的实物证据；拒绝不能宣称正向恢复成功。
    suspended.assert_running_now();
    suspended.terminate_owned_fixture();
    assert!(recover_status.success());
    assert!(fs::read_to_string(root.join("run/named-needs-attention"))
        .unwrap()
        .contains("worker_reap_failed"));
}

#[test]
fn named_job_session_mismatch_refuses_even_when_name_is_absent() {
    let name = Job::generate_legacy_repair_name().unwrap();
    let other_session = Job::current_session_id().unwrap().wrapping_add(1);
    let error = Job::reap_named_attached(&name, other_session, true).unwrap_err();
    assert!(error
        .downcast_ref::<ControlledProcessReapFailed>()
        .is_some());
    assert!(format!("{error:#}").contains("Windows 会话不同"));
}

#[test]
fn controlled_host_identity_rejects_live_generation_then_accepts_exit() {
    let root = root("controlled-host-generation");
    let _mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let this_host = current_controlled_host_identity().unwrap();
    let error = assert_controlled_host_exited(&this_host).unwrap_err();
    assert!(
        error
            .downcast_ref::<ControlledProcessReapFailed>()
            .unwrap()
            .requires_new_host
    );
    let mut host = command(&root, "controlled-host-wait").spawn().unwrap();
    wait_file(&root.join("run/controlled-host-identity"));
    let identity: ControlledHostIdentity =
        serde_json::from_slice(&fs::read(root.join("run/controlled-host-identity")).unwrap())
            .unwrap();
    let still_live = assert_controlled_host_exited(&identity);
    fs::write(root.join("run/controlled-host-stop"), b"stop").unwrap();
    assert!(wait_child(&mut host).success());
    assert!(still_live
        .unwrap_err()
        .downcast_ref::<ControlledProcessReapFailed>()
        .is_some());
    assert_controlled_host_exited(&identity).unwrap();
    let invalid = ControlledHostIdentity {
        pid: 0,
        creation_time: 0,
    };
    assert!(assert_controlled_host_exited(&invalid).is_err());
}

#[test]
fn named_job_attached_callback_failure_never_resumes_worker() {
    let root = root("named-job-attached-callback-failure");
    let _mutation = WorkspaceMutation::acquire(&root, &release()).unwrap();
    let name = Job::generate_legacy_repair_name().unwrap();
    let job = Job::create_named(&name).unwrap();
    let log: Logger = Arc::new(|_| {});
    let error = execute_controlled_in_job(
        command(&root, "touch-on-resume"),
        &log,
        &crate::operations::CancelToken::new(),
        &job,
        |pid| {
            assert!(job.contains(pid));
            bail!("synthetic durable attached checkpoint failure");
        },
    )
    .unwrap_err();
    assert!(format!("{error:#}").contains("synthetic durable attached checkpoint failure"));
    assert!(error
        .downcast_ref::<ControlledProcessReapFailed>()
        .is_none());
    assert_eq!(job.active_processes().unwrap(), 0);
    assert!(!root.join("run/worker-resumed").exists());
}

#[test]
#[ignore = "P6限定子进程入口，仅由父测试以独立标记根调用"]
fn process_helper() {
    let root =
        PathBuf::from(std::env::var_os("NEXT_TRAINER_P6_CHILD_ROOT").expect("由P6父测试调用"));
    let role = std::env::var("NEXT_TRAINER_P6_CHILD_ROLE").unwrap();
    let layout = Layout::new(&root, &release()).unwrap();
    assert_eq!(
        fs::read_to_string(root.join(".launcher-workspace")).unwrap(),
        model::WORKSPACE_MARKER
    );
    if role == "controlled-failure" {
        eprintln!("ModuleNotFoundError: No module named pip");
        std::io::stderr().flush().unwrap();
        std::process::exit(19);
    }
    if role == "controlled-large-failure" {
        // 无换行UTF-8及JSON需转义的NUL共同覆盖行缓冲、尾部及持久化上限。
        let block = "模型🙂\0".repeat(1024);
        let mut stderr = std::io::stderr().lock();
        for _ in 0..128 {
            stderr.write_all(block.as_bytes()).unwrap();
        }
        stderr
            .write_all(b"\napi_key=fake-private-value\nModuleNotFoundError: No module named pip\n")
            .unwrap();
        stderr.flush().unwrap();
        drop(stderr);
        // 随后的大量stdout不能挤走已捕获的stderr根因。
        let mut stdout = std::io::stdout().lock();
        for _ in 0..128 {
            stdout.write_all(block.as_bytes()).unwrap();
        }
        stdout.flush().unwrap();
        std::process::exit(23);
    }
    if role == "controlled-success-warning" {
        eprintln!("a harmless warning on stderr");
        return;
    }
    if role == "touch-on-resume" {
        durable_checkpoint(&root.join("run/worker-resumed"), b"unexpected resume");
        return;
    }
    if role == "controlled-host-wait" {
        durable_checkpoint(
            &root.join("run/controlled-host-identity"),
            &serde_json::to_vec(&current_controlled_host_identity().unwrap()).unwrap(),
        );
        wait_file(&root.join("run/controlled-host-stop"));
        return;
    }
    if role == "parent-success-descendant" {
        let _descendant = command(&root, "descendant")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        wait_file(&root.join("run/allow-parent-exit"));
        std::process::exit(0);
    }
    if role == "named-controller" {
        let name = fs::read_to_string(root.join("run/named-job-name")).unwrap();
        let job = Job::create_named(&name).unwrap();
        let session = Job::current_session_id().unwrap();
        let log: Logger = Arc::new(|_| {});
        execute_controlled_in_job(
            command(&root, "slow"),
            &log,
            &crate::operations::CancelToken::new(),
            &job,
            |pid| {
                durable_checkpoint(
                    &root.join("run/named-attached"),
                    format!("{session}/{pid}").as_bytes(),
                );
                Ok(())
            },
        )
        .unwrap();
        return;
    }
    if role == "named-recover" || role == "named-recover-destroyed" {
        let attached = fs::read_to_string(root.join("run/named-attached")).unwrap();
        let session: u32 = attached.split('/').next().unwrap().parse().unwrap();
        assert_eq!(session, Job::current_session_id().unwrap());
        let name = fs::read_to_string(root.join("run/named-job-name")).unwrap();
        let result = Job::reap_named_attached(&name, session, true).unwrap();
        if role == "named-recover" {
            assert_eq!(result, NamedJobReap::Drained);
            durable_checkpoint(&root.join("run/named-reaped"), b"opened active=0");
        } else {
            assert_eq!(result, NamedJobReap::Destroyed);
            durable_checkpoint(&root.join("run/named-reaped"), b"destroyed after attached");
        }
        return;
    }
    if role == "named-unattached-controller" {
        use std::os::windows::process::CommandExt;
        use windows_sys::Win32::System::Threading::{CREATE_NO_WINDOW, CREATE_SUSPENDED};
        let name = fs::read_to_string(root.join("run/named-job-name")).unwrap();
        let _job = Job::create_named(&name).unwrap();
        // 仅合成测试制造CreateProcess→Assign的真实窗口，永不恢复初始线程。
        let child = command(&root, "descendant")
            .creation_flags(CREATE_NO_WINDOW | CREATE_SUSPENDED)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        durable_checkpoint(
            &root.join("run/named-launching-child"),
            format!("{}/{}", Job::current_session_id().unwrap(), child.id()).as_bytes(),
        );
        let deadline = Instant::now() + Duration::from_secs(25);
        while Instant::now() < deadline {
            thread::sleep(Duration::from_millis(20));
        }
        let mut child = child;
        let _ = child.kill();
        let _ = child.wait();
        panic!("父测试应在launching窗口强杀控制器");
    }
    if role == "named-recover-launching" {
        let launching = fs::read_to_string(root.join("run/named-launching-child")).unwrap();
        let session = launching.split('/').next().unwrap().parse().unwrap();
        let name = fs::read_to_string(root.join("run/named-job-name")).unwrap();
        let error = Job::reap_named_attached(&name, session, false).unwrap_err();
        assert!(error
            .downcast_ref::<ControlledProcessReapFailed>()
            .is_some());
        assert!(error
            .downcast_ref::<crate::operations::Cancelled>()
            .is_none());
        durable_checkpoint(
            &root.join("run/named-needs-attention"),
            format!("{error:#}").as_bytes(),
        );
        return;
    }
    if role == "pipe-holder" {
        durable_checkpoint(&root.join("run/pipe-holder-ready"), b"ready");
        println!("P6_PIPE_BLOCK_READY");
        std::io::stdout().flush().unwrap();
        wait_file(&root.join("run/pipe-holder-stop"));
        durable_checkpoint(&root.join("run/pipe-holder-stopped"), b"stop acknowledged");
        // 本案已故意关闭stdout读端；返回libtest会打印结束行并因BrokenPipe退出101。
        // 明确确认父测试stop后直接退出，不把测试宿主尾部输出当作worker失败。
        std::process::exit(0);
    }
    if role == "logger-blocking-worker" {
        let mut descendant = command(&root, "descendant")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .unwrap();
        wait_file(&root.join("run/descendant-ready"));
        println!("P6_CONTROLLED_LOG_BLOCK");
        for index in 0..512 {
            println!("P6 bounded logger flood {index}");
        }
        std::io::stdout().flush().unwrap();
        durable_checkpoint(&root.join("run/logger-flood-complete"), b"ready");
        thread::sleep(Duration::from_secs(15));
        let _ = descendant.kill();
        let _ = descendant.wait();
        panic!("本案父测试应取消并回收logger worker");
    }
    if matches!(role.as_str(), "slow" | "descendant" | "unrelated") {
        let name = if role == "slow" {
            "slow-ready"
        } else if role == "descendant" {
            "descendant-ready"
        } else {
            "unrelated-ready"
        };
        layout.guard_path(&root.join("run").join(name)).unwrap();
        fs::write(root.join("run").join(name), std::process::id().to_string()).unwrap();
        let mut descendant = if role == "slow" {
            Some(
                command(&root, "descendant")
                    .stdout(Stdio::null())
                    .stderr(Stdio::null())
                    .spawn()
                    .unwrap(),
            )
        } else {
            None
        };
        let started = Instant::now();
        while started.elapsed() < Duration::from_secs(25) {
            if role == "unrelated" && root.join("run/unrelated-stop").exists() {
                return;
            }
            thread::sleep(Duration::from_millis(20));
        }
        if let Some(ref mut child) = descendant {
            let _ = child.kill();
            let _ = child.wait();
        }
        panic!("P6进程未在限定时间回收");
    }
    if role == "lease-denied" {
        assert!(WorkspaceMutation::acquire(&root, &release()).is_err());
        fs::write(root.join("run/lease-rejected"), b"denied").unwrap();
        return;
    }
    let ctx = WorkspaceMutation::acquire(&root, &release()).unwrap();
    if role == "mutate" {
        let state = recovery::load(ctx.layout(), "demo").unwrap();
        let _ticket = recovery::begin(&ctx, "demo", "kill-window", state.generation).unwrap();
        fs::write(
            root.join("staging/p6-synthetic/demo/package.py"),
            b"changed before commit\n",
        )
        .unwrap();
        fs::write(root.join("run/changed-ready"), b"dirty persisted").unwrap();
        let started = Instant::now();
        while started.elapsed() < Duration::from_secs(25) {
            thread::sleep(Duration::from_millis(20));
        }
        panic!("父测试应已强杀此控制进程");
    } else if role == "recover" {
        recovery::recover(&ctx, "demo", validator).unwrap();
    } else {
        panic!("未知P6 helper role");
    }
}
