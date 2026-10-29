//! P6真实回环网络、Job、跨进程中断恢复与租约争用；全部使用独立合成根。
use super::*;
use crate::model::WorkspaceMutation;
use crate::operations::{OperationKind, OperationManager};
use crate::recovery;
use std::io::Write;
use std::sync::mpsc;

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
        }
    });
    let worker = thread::spawn(move || execute_controlled(cmd, &log, &token));
    wait_file(&root.join("run/descendant-ready"));
    let descendant: u32 = fs::read_to_string(root.join("run/descendant-ready"))
        .unwrap()
        .parse()
        .unwrap();
    let started = Instant::now();
    manager.cancel("execute-p6").unwrap();
    assert!(worker.join().unwrap().is_err());
    assert!(started.elapsed() < Duration::from_secs(2));
    use windows_sys::Win32::{
        Foundation::{CloseHandle, WAIT_OBJECT_0},
        System::Threading::{OpenProcess, WaitForSingleObject, PROCESS_SYNCHRONIZE},
    };
    unsafe {
        let handle = OpenProcess(PROCESS_SYNCHRONIZE, 0, descendant);
        if !handle.is_null() {
            assert_eq!(WaitForSingleObject(handle, 2000), WAIT_OBJECT_0);
            CloseHandle(handle);
        }
    }
    assert!(unrelated.try_wait().unwrap().is_none());
    fs::write(root.join("run/unrelated-stop"), b"stop").unwrap();
    assert!(wait_child(&mut unrelated).success());
    println!(
        "P6 Job cancel ms={}, unrelated helper survived",
        started.elapsed().as_millis()
    );
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
