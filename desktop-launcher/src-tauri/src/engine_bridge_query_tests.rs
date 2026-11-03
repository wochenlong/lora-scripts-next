// 真实进程合同使用固定受管CPython，仅运行微型脚本，不读取安装根或引擎环境。
use super::*;
use crate::query_tasks::{
    QueryAction, QueryClock, QueryIdentity, QueryResolution, QuerySnapshot, QueryStatus,
    QueryTarget, QueryTaskManager,
};
use std::os::windows::process::ExitStatusExt;

fn contract_handle(timeout: Duration) -> (QueryTaskManager, QueryHandle, QueryIdentity) {
    let manager = QueryTaskManager::default();
    let target = QueryTarget {
        root: "F:/bridge-contract-memory-only".into(),
        release_id: "dev-bridge-contract".into(),
        engine_id: "kohya".into(),
        action: QueryAction::InspectReadonly,
        rebuild: false,
        scope: QueryScope::Full,
    };
    let identity = QueryIdentity {
        target: target.clone(),
        workspace_fence: "memory-contract-not-an-install-root".into(),
        instance_id: Some("contract-instance".into()),
        generation: Some(1),
        state_sha256: Some("1".repeat(64)),
        receipt_sha256: Some("2".repeat(64)),
        binding_sha256: Some("3".repeat(64)),
        lock_sha256: "4".repeat(64),
        recipe_sha256: "5".repeat(64),
    };
    let mut handle = manager
        .begin(target, QueryClock::start(timeout).unwrap())
        .unwrap()
        .handle;
    assert!(matches!(
        handle.resolve(identity.clone()).unwrap(),
        QueryResolution::Execute
    ));
    assert!(handle.try_start().unwrap());
    (manager, handle, identity)
}

fn progress(task: &str, sequence: u64) -> Value {
    json!({"schema_version":1,"type":"progress","task_id":task,"seq":sequence,
        "stage":"environment","files":3,"bytes":65536,"total_files":null,
        "total_bytes":null,"message":"正在核对"})
}
fn final_reply(task: &str) -> Value {
    json!({"schema_version":1,"type":"result","task_id":task,"scope":"full",
        "ok":true,"result":{"healthy":true}})
}
fn encoded(value: &Value) -> Vec<u8> {
    let mut bytes = serde_json::to_vec(value).unwrap();
    bytes.push(b'\n');
    bytes
}
fn push(frames: &mut QueryFrames, value: &Value, observer: &QueryObserver) -> Result<()> {
    frames.push(
        QueryChunk {
            pipe: QueryPipe::Stdout,
            bytes: encoded(value),
        },
        observer,
    )
}

#[test]
fn protocol_chunked_progress_final() {
    let (manager, handle, _) = contract_handle(Duration::from_secs(10));
    let observer = handle.observer();
    let mut frames = QueryFrames::new(handle.task_id(), "full");
    let bytes = [
        encoded(&progress(handle.task_id(), 1)),
        encoded(&final_reply(handle.task_id())),
    ]
    .concat();
    for part in bytes.chunks(7) {
        frames
            .push(
                QueryChunk {
                    pipe: QueryPipe::Stdout,
                    bytes: part.to_vec(),
                },
                &observer,
            )
            .unwrap();
    }
    let snapshot = manager.snapshot(handle.task_id()).unwrap();
    assert_eq!(snapshot.stage, QueryStage::Environment);
    assert_eq!(snapshot.progress.files, Some(3));
    assert_eq!(snapshot.progress.bytes, Some(65536));
    assert!(!snapshot.status.is_terminal());
    assert_eq!(
        frames.finish(ExitStatus::from_raw(0)).unwrap(),
        json!({"healthy":true})
    );
}

#[test]
fn protocol_rejects_bad_identity_sequence_final() {
    let (_, handle, _) = contract_handle(Duration::from_secs(10));
    let observer = handle.observer();
    let task = handle.task_id();
    let mut bad_values = Vec::new();
    for (field, replacement) in [
        ("task_id", json!("another-task")),
        ("schema_version", json!(2)),
        ("stage", json!("unknown")),
        ("files", json!(-1)),
        ("bytes", json!(1.5)),
        ("seq", json!(0)),
    ] {
        let mut value = progress(task, 1);
        value[field] = replacement;
        bad_values.push(value);
    }
    let mut wrong_scope = final_reply(task);
    wrong_scope["scope"] = json!("files_only");
    bad_values.push(wrong_scope);
    for value in bad_values {
        assert!(
            push(&mut QueryFrames::new(task, "full"), &value, &observer).is_err(),
            "accepted {value}"
        );
    }
    let mut frames = QueryFrames::new(task, "full");
    push(&mut frames, &progress(task, 1), &observer).unwrap();
    assert!(push(&mut frames, &progress(task, 1), &observer).is_err());
    let mut frames = QueryFrames::new(task, "full");
    push(&mut frames, &final_reply(task), &observer).unwrap();
    assert!(push(&mut frames, &final_reply(task), &observer).is_err());
    let mut frames = QueryFrames::new(task, "full");
    frames
        .push(
            QueryChunk {
                pipe: QueryPipe::Stdout,
                bytes: b"{\"schema_version\":".to_vec(),
            },
            &observer,
        )
        .unwrap();
    assert!(frames.finish(ExitStatus::from_raw(0)).is_err());
    assert!(QueryFrames::new(task, "full")
        .finish(ExitStatus::from_raw(0))
        .is_err());
}

#[test]
fn protocol_output_limits() {
    let (_, handle, _) = contract_handle(Duration::from_secs(10));
    let observer = handle.observer();
    let task = handle.task_id();
    let mut frames = QueryFrames::new(task, "full");
    assert!(frames
        .push(
            QueryChunk {
                pipe: QueryPipe::Stdout,
                bytes: vec![b'x'; QUERY_RESULT_LIMIT + 1]
            },
            &observer
        )
        .is_err());
    let mut frames = QueryFrames::new(task, "full");
    assert!(frames
        .push(
            QueryChunk {
                pipe: QueryPipe::Stderr,
                bytes: vec![b'x'; QUERY_STDERR_LIMIT + 1]
            },
            &observer
        )
        .is_err());
    let mut value = progress(task, 1);
    value["message"] = json!("x".repeat(4097));
    assert!(push(&mut QueryFrames::new(task, "full"), &value, &observer).is_err());
    let mut value = progress(task, 1);
    value["padding"] = json!("x".repeat(QUERY_PROGRESS_LIMIT));
    assert!(push(&mut QueryFrames::new(task, "full"), &value, &observer).is_err());
    let mut frames = QueryFrames::new(task, "full");
    for sequence in 1..=QUERY_FRAME_LIMIT {
        push(&mut frames, &progress(task, sequence as u64), &observer).unwrap();
    }
    assert!(push(
        &mut frames,
        &progress(task, QUERY_FRAME_LIMIT as u64 + 1),
        &observer
    )
    .is_err());
}

#[test]
fn protocol_total_output_limit() {
    let (_, handle, _) = contract_handle(Duration::from_secs(60));
    let observer = handle.observer();
    let mut frames = QueryFrames::new(handle.task_id(), "full");
    let mut error = None;
    for sequence in 1..=QUERY_FRAME_LIMIT {
        let mut value = progress(handle.task_id(), sequence as u64);
        value["message"] = json!("x".repeat(4000));
        if let Err(failure) = push(&mut frames, &value, &observer) {
            error = Some(failure);
            break;
        }
    }
    assert!(format!("{:#}", error.expect("总输出必须有界拒绝")).contains("16MiB"));
}

#[test]
fn protocol_nonzero_exit_cannot_succeed() {
    let (_, handle, _) = contract_handle(Duration::from_secs(10));
    let mut frames = QueryFrames::new(handle.task_id(), "full");
    push(
        &mut frames,
        &final_reply(handle.task_id()),
        &handle.observer(),
    )
    .unwrap();
    assert!(frames.finish(ExitStatus::from_raw(3)).is_err());
}

#[test]
fn scope_contract_rejects_unsupported_combinations() {
    assert_eq!(
        query_scope("inspect_readonly", QueryScope::Full).unwrap(),
        "full"
    );
    assert_eq!(
        query_scope("inspect_readonly", QueryScope::FilesOnly).unwrap(),
        "files_only"
    );
    assert_eq!(
        query_scope("plan_repair", QueryScope::Plan).unwrap(),
        "plan"
    );
    assert!(query_scope("plan_install", QueryScope::Full).is_err());
    assert!(query_scope("recipe", QueryScope::FilesOnly).is_err());
    assert!(query_scope("apply_install", QueryScope::Plan).is_err());
}

// 默认回归不隐式启动外部进程。Root显式--include-ignored并传入下列两变量后执行。
// 缺少前置则panic，不能静默skip后将其统计为通过。
fn script_command(case: &str, script: &str) -> (Command, PathBuf) {
    let python = PathBuf::from(
        std::env::var_os("NEXT_TRAINER_QUERY_TEST_PYTHON").expect("缺少固定受管Python路径"),
    );
    assert!(python.is_file(), "受管Python不存在：{}", python.display());
    let output_root = PathBuf::from(
        std::env::var_os("NEXT_TRAINER_QUERY_TEST_OUTPUT").expect("缺少本案证据输出根"),
    );
    assert!(output_root.is_absolute());
    fs::create_dir_all(&output_root).unwrap();
    let suffix = NEXT_QUERY_TEMP.fetch_add(1, Ordering::Relaxed);
    let directory = output_root.join(format!("{case}-{}-{suffix}", std::process::id()));
    fs::create_dir(&directory).unwrap();
    fs::write(directory.join("worker.py"), script).unwrap();
    let mut command = Command::new(python);
    command
        .args(["-I", "-B", "-S", "-c", script])
        .current_dir(&directory)
        .env_remove("PYTHONPATH")
        .env_remove("PYTHONHOME")
        .env("PYTHONNOUSERSITE", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    (command, directory)
}

fn request(task: &str) -> Vec<u8> {
    encoded(&json!({"task_id":task}))
}
fn test_log() -> Logger {
    Arc::new(|message| eprintln!("{message}"))
}

fn finish_real(
    mut outcome: ManagedQueryOutcome,
    manager: &QueryTaskManager,
    handle: &QueryHandle,
    identity: QueryIdentity,
    directory: &Path,
    started: Instant,
    expect_worker: bool,
) -> (QuerySnapshot, Option<Value>, Option<String>) {
    let cleanup_deadline = Instant::now() + Duration::from_secs(10);
    while outcome.cleanup.is_none() && Instant::now() < cleanup_deadline {
        let pending = outcome.pending.as_mut().expect("无回收证明必须保留owner");
        outcome.cleanup = pending.reap().unwrap();
        if outcome.cleanup.is_some() {
            outcome.cleanup_observation = pending.cleanup_observation();
        }
        if outcome.cleanup.is_none() {
            thread::sleep(Duration::from_millis(10));
        }
    }
    let result_value = outcome.result.as_ref().ok().cloned();
    let error = outcome
        .result
        .as_ref()
        .err()
        .map(|error| format!("{error:#}"));
    if expect_worker {
        let observation = outcome
            .cleanup_observation
            .as_ref()
            .expect("缺少实际OS/线程回收观察");
        assert!(observation.worker.is_some());
        assert!(observation.child_waited);
        assert_eq!(observation.job_active_processes, 0);
        assert!(observation.stdin_closed);
        assert!(observation.stdout_reader_joined);
        assert!(observation.stderr_reader_joined);
    }
    let cleanup = outcome
        .cleanup
        .take()
        .expect("真实资源回收未确认，测试不得通过");
    let result = outcome
        .result
        .map_err(|error| match error.downcast::<QueryError>() {
            Ok(error) => error,
            Err(error) => QueryError::new("bridge_contract_failed", format!("{error:#}")),
        });
    let observed = if result.is_ok() { Some(identity) } else { None };
    let snapshot = handle.finish(result, observed, cleanup).unwrap();
    fs::write(
        directory.join("result.json"),
        serde_json::to_vec_pretty(&json!({
            "schema_version":1,"snapshot":snapshot,"worker_result":result_value,
            "error":error,"elapsed_ms":started.elapsed().as_millis(),
            "actual_cleanup":outcome.cleanup_observation,
            "actual_child_wait_and_job_active_zero":snapshot.worker_reaped,
            "actual_stdin_closed_and_output_readers_joined":snapshot.readers_reaped,
            "evidence_scope":"微型真实进程；非引擎/GUI验收"
        }))
        .unwrap(),
    )
    .unwrap();
    assert_eq!(snapshot.worker.is_some(), expect_worker);
    assert!(snapshot.worker_reaped && snapshot.readers_reaped);
    assert!(snapshot.status.is_terminal());
    assert_eq!(manager.active_count().unwrap(), 0);
    (snapshot, result_value, error)
}

const PRELUDE: &str = "import sys,json,os,time\nr=json.loads(sys.stdin.buffer.readline())\n";
const RESULT: &str = "print(json.dumps({'schema_version':1,'type':'result','task_id':r['task_id'],'scope':'full','ok':True,'result':{'python':list(sys.version_info[:3])}}),flush=True)\n";

#[test]
#[ignore = "显式受管CPython与本案输出根；Root在GUI空闲时串行执行"]
fn real_worker_success_and_join() {
    let script = format!("{PRELUDE}print(json.dumps({{'schema_version':1,'type':'progress','task_id':r['task_id'],'seq':1,'stage':'environment','files':1,'bytes':17,'message':'probe'}}),flush=True)\n{RESULT}");
    let (mut command, directory) = script_command("success", &script);
    let (manager, handle, identity) = contract_handle(Duration::from_secs(10));
    let started = Instant::now();
    let outcome = run_managed_query_command(
        &mut command,
        request(handle.task_id()),
        "full",
        &handle,
        &test_log(),
    );
    let (snapshot, value, _) = finish_real(
        outcome, &manager, &handle, identity, &directory, started, true,
    );
    assert_eq!(snapshot.status, QueryStatus::Succeeded);
    assert_eq!(value.unwrap()["python"], json!([3, 10, 19]));
    assert!(started.elapsed() < Duration::from_secs(10));
}

#[test]
#[ignore = "显式受管CPython与本案输出根；不创建外部资源即可收口"]
fn cancel_before_spawn() {
    let (mut command, directory) = script_command("before-spawn", "raise SystemExit('不应运行')\n");
    let (manager, handle, identity) = contract_handle(Duration::from_secs(10));
    manager.cancel(handle.task_id()).unwrap();
    let started = Instant::now();
    let outcome = run_managed_query_command(
        &mut command,
        request(handle.task_id()),
        "full",
        &handle,
        &test_log(),
    );
    let (snapshot, _, _) = finish_real(
        outcome, &manager, &handle, identity, &directory, started, false,
    );
    assert_eq!(snapshot.status, QueryStatus::Cancelled);
}

#[test]
#[ignore = "微型真实worker；非法UTF-8后保持存活以证明错误路径回收"]
fn real_bad_frame_reaped() {
    let (mut command, directory) = script_command(
        "bad-frame",
        "import os,time\nos.write(1,b'\\xff\\n')\ntime.sleep(60)\n",
    );
    let (manager, handle, identity) = contract_handle(Duration::from_secs(10));
    let started = Instant::now();
    let outcome = run_managed_query_command(
        &mut command,
        request(handle.task_id()),
        "full",
        &handle,
        &test_log(),
    );
    let (snapshot, _, error) = finish_real(
        outcome, &manager, &handle, identity, &directory, started, true,
    );
    assert_eq!(snapshot.status, QueryStatus::Failed);
    assert!(error.unwrap().contains("JSONL"));
    assert!(started.elapsed() < Duration::from_secs(10));
}

#[test]
#[ignore = "真实管道不消费stdin，取消须终止本Job并join堵塞writer"]
fn real_stdin_blocked_cancel() {
    let (mut command, directory) = script_command("stdin-cancel", "import time\ntime.sleep(60)\n");
    let (manager, handle, identity) = contract_handle(Duration::from_secs(10));
    let cancel_manager = manager.clone();
    let task = handle.task_id().to_owned();
    let cancel = thread::spawn(move || {
        let until = Instant::now() + Duration::from_secs(5);
        while cancel_manager.snapshot(&task).unwrap().worker.is_none() {
            assert!(Instant::now() < until, "查询未登记worker");
            thread::sleep(Duration::from_millis(5));
        }
        thread::sleep(Duration::from_millis(100));
        cancel_manager.cancel(&task).unwrap();
    });
    let started = Instant::now();
    let outcome = run_managed_query_command(
        &mut command,
        vec![b'x'; QUERY_INPUT_LIMIT],
        "full",
        &handle,
        &test_log(),
    );
    cancel.join().unwrap();
    let (snapshot, _, _) = finish_real(
        outcome, &manager, &handle, identity, &directory, started, true,
    );
    assert_eq!(snapshot.status, QueryStatus::Cancelled);
    assert!(started.elapsed() < Duration::from_secs(5));
}

#[test]
#[ignore = "真实管道不消费stdin，总deadline须涵盖writer与回收"]
fn real_stdin_blocked_timeout() {
    let (mut command, directory) = script_command("stdin-timeout", "import time\ntime.sleep(60)\n");
    let (manager, handle, identity) = contract_handle(Duration::from_millis(700));
    let started = Instant::now();
    let outcome = run_managed_query_command(
        &mut command,
        vec![b'x'; QUERY_INPUT_LIMIT],
        "full",
        &handle,
        &test_log(),
    );
    let (snapshot, _, _) = finish_real(
        outcome, &manager, &handle, identity, &directory, started, true,
    );
    assert_eq!(snapshot.status, QueryStatus::TimedOut);
    assert!(started.elapsed() < Duration::from_secs(5));
}

#[test]
#[ignore = "真实子代持有stdout/stderr，父退出后须回收整个本Job"]
fn real_descendant_holds_pipe_reaped() {
    let script = format!("{PRELUDE}import subprocess\nchild=subprocess.Popen([sys.executable,'-I','-B','-S','-c','import time; time.sleep(60)'],stdout=sys.stdout,stderr=sys.stderr,creationflags=subprocess.CREATE_NO_WINDOW)\nopen('descendant-pid.txt','w').write(str(child.pid))\n{RESULT}");
    let (mut command, directory) = script_command("descendant", &script);
    let (manager, handle, identity) = contract_handle(Duration::from_secs(10));
    let started = Instant::now();
    let outcome = run_managed_query_command(
        &mut command,
        request(handle.task_id()),
        "full",
        &handle,
        &test_log(),
    );
    let (snapshot, _, _) = finish_real(
        outcome, &manager, &handle, identity, &directory, started, true,
    );
    assert_eq!(snapshot.status, QueryStatus::Succeeded);
    assert!(
        fs::read_to_string(directory.join("descendant-pid.txt"))
            .unwrap()
            .trim()
            .parse::<u32>()
            .unwrap()
            > 0
    );
    assert!(started.elapsed() < Duration::from_secs(5));
}

#[test]
#[ignore = "有界通道故意不排空；取消后reader不能永久堵在send"]
fn real_full_channel_reader_join() {
    let script = "import os,time\nfor i in range(256): os.write(1,b'x'*65536)\ntime.sleep(60)\n";
    let (mut command, directory) = script_command("full-channel", script);
    let (manager, handle, identity) = contract_handle(Duration::from_secs(10));
    let mut registered = None;
    let (child, job) = match managed_child::spawn_query(&mut command, |child, job| {
        let worker = managed_child::worker_identity(child, job)?;
        handle.attach_worker(worker.clone())?;
        registered = Some(worker);
        Ok(())
    }) {
        Ok(value) => value,
        Err(error) => panic!("启动小worker失败：{:#}", error.error),
    };
    let mut owner = PendingManagedQuery::new(child, Some(job), false);
    owner.identity = registered;
    let _receiver_kept_full = owner.start_io(Vec::new()).unwrap();
    let blocked_until = Instant::now() + Duration::from_secs(5);
    while !owner.output_backpressure.load(Ordering::Acquire) {
        assert!(Instant::now() < blocked_until, "未观察到真实通道Full");
        thread::sleep(Duration::from_millis(5));
    }
    assert!(!owner.stdout_joined);
    manager.cancel(handle.task_id()).unwrap();
    let started = Instant::now();
    let outcome = ManagedQueryOutcome {
        result: Err(QueryError::new("query_cancelled", "取消本案满通道worker").into()),
        cleanup: None,
        pending: Some(owner),
        cleanup_observation: None,
    };
    let (snapshot, _, _) = finish_real(
        outcome, &manager, &handle, identity, &directory, started, true,
    );
    assert_eq!(snapshot.status, QueryStatus::Cancelled);
    assert!(started.elapsed() < Duration::from_secs(5));
}
