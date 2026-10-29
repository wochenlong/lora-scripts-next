//! 精确挂载为download_budget::fault_tests；helper filter也使用此路径。
//! 仅读写独立测试根；无HTTP/socket/Cargo命令，真实强杀仅限父测试创建的helper。
use super::*;
use std::{
    process::{Child, Command, Stdio},
    thread,
    time::Instant,
};

struct Fixture {
    root: PathBuf,
}
impl Fixture {
    fn new(label: &str) -> Self {
        let base = std::env::var_os("NEXT_TRAINER_P6_TEST_ROOT")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir);
        let root = base.join(format!(
            "nt-budget-{label}-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        assert!(!root.exists());
        fs::create_dir_all(&root).unwrap();
        Self { root }
    }
    fn mutation(&self) -> WorkspaceMutation {
        WorkspaceMutation::acquire(&self.root, &format!("dev-{}", "a".repeat(40))).unwrap()
    }
}
// 失败现场保留，不自动递归删除。
fn policy() -> DownloadPolicy {
    DownloadPolicy {
        root_cap_body_bytes: 1_000_000,
    }
}
fn limits() -> OperationLimits {
    OperationLimits {
        max_charged_body_bytes: 200_000,
        max_requests: 8,
        max_retries: 1,
        max_redirects: 2,
        max_elapsed_ms: 10_000,
    }
}
fn asset() -> AssetIdentity {
    AssetIdentity {
        sha256: "c".repeat(64),
        url_sha256: "d".repeat(64),
        authority: "example.test:443".into(),
    }
}
fn wait_file(path: &Path, child: &mut Child) {
    let start = Instant::now();
    while !path.is_file() {
        assert!(child.try_wait().unwrap().is_none(), "helper提前结束");
        if start.elapsed() > Duration::from_secs(10) {
            let _ = child.kill();
            let _ = child.wait();
            panic!("下载预算helper检查点超时");
        }
        thread::sleep(Duration::from_millis(10));
    }
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Checkpoint {
    root: PathBuf,
    role: String,
    checkpoint: String,
    pid: u32,
}

fn role_checkpoint(role: &str) -> Option<&'static str> {
    match role {
        "reserved" => Some("reserved"),
        "init-pending" => Some("enrollment_pending"),
        "init-genesis" => Some("genesis_persisted"),
        "init-active" => Some("enrollment_active"),
        "receipt-written" => Some("receipt_persisted"),
        _ => None,
    }
}

/// 仅测试构建调用。父进程env不变；只有精确helper ROOT/ROLE命中后才阻塞。
pub(super) fn checkpoint(layout: &Layout, phase: &str) -> Result<()> {
    let Some(root) = std::env::var_os("NEXT_TRAINER_BUDGET_CHILD_ROOT") else {
        return Ok(());
    };
    if Path::new(&root) != layout.root.as_path() {
        return Ok(());
    }
    let role = std::env::var("NEXT_TRAINER_BUDGET_CHILD_ROLE")?;
    if role_checkpoint(&role) != Some(phase) {
        return Ok(());
    }
    assert_child_root(&layout.root);
    let ready = layout.root.join("checkpoint-ready.json");
    layout.guard_path(&ready)?;
    assert!(!ready.exists(), "helper检查点只能提交一次");
    // 原子提交避免父进程观察到已创建却尚未写完的ready文件。
    model::write_json_atomic(
        &ready,
        &Checkpoint {
            root: layout.root.clone(),
            role,
            checkpoint: phase.into(),
            pid: std::process::id(),
        },
    )?;
    loop {
        thread::sleep(Duration::from_millis(20));
    }
}

fn assert_child_root(root: &Path) {
    assert!(root.is_absolute());
    assert!(root
        .file_name()
        .unwrap()
        .to_string_lossy()
        .starts_with("nt-budget-kill-"));
}

struct Helper {
    child: Child,
    root: PathBuf,
    role: String,
}

impl Helper {
    fn spawn(fixture: &Fixture, role: &str) -> Self {
        assert_child_root(&fixture.root);
        assert!(role_checkpoint(role).is_some());
        let mut command = Command::new(std::env::current_exe().unwrap());
        command
            .args([
                "--exact",
                "download_budget::fault_tests::budget_process_helper",
                "--ignored",
                "--nocapture",
            ])
            .env("NEXT_TRAINER_BUDGET_CHILD_ROOT", &fixture.root)
            .env("NEXT_TRAINER_BUDGET_CHILD_ROLE", role)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        Self {
            child: command.spawn().unwrap(),
            root: fixture.root.clone(),
            role: role.into(),
        }
    }

    fn wait_ready(&mut self) {
        let path = self.root.join("checkpoint-ready.json");
        wait_file(&path, &mut self.child);
        let value: Checkpoint = serde_json::from_slice(&fs::read(path).unwrap()).unwrap();
        assert_eq!(value.root, self.root);
        assert_eq!(value.role, self.role);
        assert_eq!(Some(value.checkpoint.as_str()), role_checkpoint(&self.role));
        assert_eq!(value.pid, self.child.id());
    }

    fn kill_and_wait(&mut self) {
        assert!(self.child.try_wait().unwrap().is_none());
        self.child.kill().unwrap();
        assert!(!self.child.wait().unwrap().success());
    }
}

impl Drop for Helper {
    fn drop(&mut self) {
        // 父测试断言失败也只收回自己创建的helper，避免悬挂进程持lease。
        if !matches!(self.child.try_wait(), Ok(Some(_))) {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}

#[test]
#[ignore = "独立预算强杀helper，仅由父测试设置精确ROOT调用"]
fn budget_process_helper() {
    let root =
        PathBuf::from(std::env::var_os("NEXT_TRAINER_BUDGET_CHILD_ROOT").expect("父测试ROOT"));
    let role = std::env::var("NEXT_TRAINER_BUDGET_CHILD_ROLE").expect("父测试ROLE");
    assert!(role_checkpoint(&role).is_some());
    assert_child_root(&root);
    let ctx = WorkspaceMutation::acquire(&root, &format!("dev-{}", "a".repeat(40))).unwrap();
    if role.starts_with("init-") {
        // 这里只启用policy，不建立download session。三个标记窗口不可混为session。
        initialize_policy(&ctx, policy()).unwrap();
        panic!("初始化helper未命中精确checkpoint");
    }
    if role == "receipt-written" {
        let budget =
            DownloadBudget::begin(&ctx, "download-receipt-killed", None, policy(), limits())
                .unwrap();
        let (attempt, credit) = budget
            .begin_attempt(&asset(), AttemptKind::Initial, 16)
            .unwrap();
        budget.settle_read(credit, 7).unwrap();
        budget
            .finish_attempt(attempt, AttemptOutcome::Completed)
            .unwrap();
        budget.finish(DownloadOutcome::Succeeded).unwrap();
        panic!("receipt helper未命中精确checkpoint");
    }
    let budget = DownloadBudget::begin(&ctx, "download-killed", None, policy(), limits()).unwrap();
    let (_attempt, credit) = budget
        .begin_attempt(&asset(), AttemptKind::Initial, 4096)
        .unwrap();
    assert_eq!(credit.bytes(), 4096);
    let persisted = snapshot(ctx.layout()).unwrap();
    assert_eq!(persisted.reserved_body_bytes, 4096);
    // 首credit保持在作用域；父测试必须kill owned helper，不能走正常finish。
    let _credit = credit;
    checkpoint(ctx.layout(), "reserved").unwrap();
    panic!("reserved helper未命中精确checkpoint");
}

#[test]
fn killed_reserved_read_is_charged_once_after_real_lease_reacquisition() {
    let f = Fixture::new("kill");
    let mut helper = Helper::spawn(&f, "reserved");
    helper.wait_ready();
    helper.kill_and_wait();
    let ctx = f.mutation();
    let before = snapshot(ctx.layout()).unwrap();
    assert_eq!(before.reserved_body_bytes, 4096);
    assert_eq!(before.counters.uncertain_charge_bytes, 0);
    // 环境页可以显式收尾，不必为了恢复计账而发起新下载。
    reconcile(&ctx).unwrap();
    let settled = snapshot(ctx.layout()).unwrap();
    assert_eq!(settled.reserved_body_bytes, 0);
    assert_eq!(settled.counters.uncertain_charge_bytes, 4096);
    assert!(!settled.pending_reconciliation);
    let ledger_bytes = fs::read(ledger_path(ctx.layout()).unwrap()).unwrap();
    reconcile(&ctx).unwrap();
    assert_eq!(
        fs::read(ledger_path(ctx.layout()).unwrap()).unwrap(),
        ledger_bytes
    );
    let budget = DownloadBudget::begin(
        &ctx,
        "download-after-kill",
        Some("download-killed"),
        policy(),
        limits(),
    )
    .unwrap();
    let current = budget.view().unwrap();
    assert_eq!(current.reserved_body_bytes, 0);
    assert_eq!(current.counters.uncertain_charge_bytes, 4096);
    let interrupted = operation_receipt(ctx.layout(), "download-killed")
        .unwrap()
        .unwrap();
    assert_eq!(interrupted.outcome, DownloadOutcome::Interrupted);
    assert_eq!(interrupted.counters.uncertain_charge_bytes, 4096);
    budget.finish(DownloadOutcome::Succeeded).unwrap();
    drop(budget);
    let again = DownloadBudget::begin(
        &ctx,
        "download-after-second-resume",
        None,
        policy(),
        limits(),
    )
    .unwrap();
    assert_eq!(again.view().unwrap().counters.uncertain_charge_bytes, 4096);
    again.finish(DownloadOutcome::Succeeded).unwrap();
}

fn initialization_kill_window(role: &str, expect_phase: EnrollmentPhase, ledger_exists: bool) {
    let f = Fixture::new(&format!("kill-{role}"));
    let mut helper = Helper::spawn(&f, role);
    helper.wait_ready();
    let layout = Layout::new(&f.root, &format!("dev-{}", "a".repeat(40))).unwrap();
    let marker_bytes = fs::read(enrollment_path(&layout).unwrap()).unwrap();
    let marker: Enrollment = decode(&marker_bytes).unwrap();
    validate_enrollment(&layout, &marker).unwrap();
    assert_eq!(marker.phase, expect_phase);
    let before_ledger = read_bytes(&layout, &ledger_path(&layout).unwrap()).unwrap();
    assert_eq!(before_ledger.is_some(), ledger_exists);
    if let Some(bytes) = before_ledger.as_ref() {
        let persisted: Ledger = decode(bytes).unwrap();
        assert_eq!(persisted, marker.genesis);
    }
    let before = snapshot(&layout).unwrap();
    assert_eq!(before.enabled, expect_phase == EnrollmentPhase::Active);
    assert_eq!(
        before.pending_reconciliation,
        expect_phase == EnrollmentPhase::Pending
    );
    assert!(before.active_operation.is_none()); // Active启用标记不是download session。
    assert_eq!(before.counters, Counters::default());
    assert_eq!(before.reserved_body_bytes, 0);
    assert_eq!(
        fs::read(enrollment_path(&layout).unwrap()).unwrap(),
        marker_bytes
    );
    assert_eq!(
        read_bytes(&layout, &ledger_path(&layout).unwrap()).unwrap(),
        before_ledger
    );
    assert!(WorkspaceMutation::acquire(&f.root, &format!("dev-{}", "a".repeat(40))).is_err());
    helper.kill_and_wait();

    // 新ctx真实重新取得workspace lease；不恢复父进程env、不补伪造零账。
    let ctx = f.mutation();
    reconcile(&ctx).unwrap();
    let enabled: Enrollment =
        decode(&fs::read(enrollment_path(ctx.layout()).unwrap()).unwrap()).unwrap();
    assert_eq!(enabled.phase, EnrollmentPhase::Active);
    assert_eq!(enabled.genesis, marker.genesis);
    let recovered_bytes = fs::read(ledger_path(ctx.layout()).unwrap()).unwrap();
    let recovered: Ledger = decode(&recovered_bytes).unwrap();
    assert_eq!(recovered, marker.genesis);
    assert_eq!(
        receipt_count(ctx.layout(), Some(&enabled.workspace_id)).unwrap(),
        0
    );
    let after = snapshot(ctx.layout()).unwrap();
    assert!(after.enabled);
    assert!(!after.pending_reconciliation);
    assert!(after.active_operation.is_none());
    assert_eq!(
        after.root_cap_body_bytes,
        Some(policy().root_cap_body_bytes)
    );
    assert_eq!(after.counters, Counters::default());
    reconcile(&ctx).unwrap();
    assert_eq!(
        fs::read(ledger_path(ctx.layout()).unwrap()).unwrap(),
        recovered_bytes
    );
}

#[test]
fn killed_after_pending_enrollment_recovers_exact_genesis_after_lease_reacquisition() {
    initialization_kill_window("init-pending", EnrollmentPhase::Pending, false);
}

#[test]
fn killed_after_genesis_ledger_recovers_same_identity_after_lease_reacquisition() {
    initialization_kill_window("init-genesis", EnrollmentPhase::Pending, true);
}

#[test]
fn killed_after_active_enrollment_keeps_policy_without_inventing_a_download_session() {
    initialization_kill_window("init-active", EnrollmentPhase::Active, true);
}

#[test]
fn killed_after_receipt_write_replays_outbox_without_duplicate_charge_or_receipt() {
    let f = Fixture::new("kill-receipt-written");
    let mut helper = Helper::spawn(&f, "receipt-written");
    helper.wait_ready();
    let layout = Layout::new(&f.root, &format!("dev-{}", "a".repeat(40))).unwrap();
    let before: Ledger = decode(&fs::read(ledger_path(&layout).unwrap()).unwrap()).unwrap();
    assert!(before.active.is_none());
    let outbox = before
        .terminal_outbox
        .as_ref()
        .expect("父kill前必须存在outbox");
    assert_eq!(outbox.operation_id, "download-receipt-killed");
    assert_eq!(outbox.outcome, DownloadOutcome::Succeeded);
    assert_eq!(outbox.counters.observed_body_bytes, 7);
    assert_eq!(outbox.counters.uncertain_charge_bytes, 0);
    let target = receipt_directory(&layout)
        .unwrap()
        .join("download-receipt-killed.json");
    let original_receipt = fs::read(&target).expect("父kill前必须存在已落盘receipt");
    let persisted: OperationDownloadReceipt = decode(&original_receipt).unwrap();
    assert_eq!(&persisted, outbox);
    assert!(snapshot(&layout).unwrap().pending_reconciliation);
    assert!(WorkspaceMutation::acquire(&f.root, &format!("dev-{}", "a".repeat(40))).is_err());
    helper.kill_and_wait();

    let ctx = f.mutation();
    reconcile(&ctx).unwrap();
    let after_bytes = fs::read(ledger_path(ctx.layout()).unwrap()).unwrap();
    let after: Ledger = decode(&after_bytes).unwrap();
    assert!(after.active.is_none());
    assert!(after.terminal_outbox.is_none());
    assert_eq!(after.counters, before.counters);
    assert_eq!(after.generation, before.generation + 1);
    assert_eq!(fs::read(&target).unwrap(), original_receipt);
    assert_eq!(
        receipt_count(ctx.layout(), Some(&after.workspace_id)).unwrap(),
        1
    );
    let receipt = operation_receipt(ctx.layout(), "download-receipt-killed")
        .unwrap()
        .unwrap();
    assert_eq!(receipt, persisted); // 已成功receipt不可因后续进程kill改成Interrupted。
    reconcile(&ctx).unwrap();
    assert_eq!(
        fs::read(ledger_path(ctx.layout()).unwrap()).unwrap(),
        after_bytes
    );
    assert_eq!(fs::read(target).unwrap(), original_receipt);
}

#[cfg(windows)]
#[test]
fn windows_target_without_delete_sharing_rejects_real_atomic_replace_and_stops_session() {
    use std::{fs::OpenOptions, os::windows::fs::OpenOptionsExt};

    let f = Fixture::new("windows-atomic-replace");
    let ctx = f.mutation();
    let budget = DownloadBudget::begin(
        &ctx,
        "download-atomic-replace-failure",
        None,
        policy(),
        limits(),
    )
    .unwrap();
    let (attempt, credit) = budget
        .begin_attempt(&asset(), AttemptKind::Initial, 16)
        .unwrap();
    budget.settle_read(credit, 7).unwrap();
    let target = ledger_path(ctx.layout()).unwrap();
    let original = fs::read(&target).unwrap();
    // FILE_SHARE_READ|FILE_SHARE_WRITE=3，明确不授予FILE_SHARE_DELETE=4。
    // verify_committed仍可读取，直到实际MoveFileExW替换才被Windows拒绝。
    let lock = OpenOptions::new()
        .read(true)
        .share_mode(3)
        .open(&target)
        .unwrap();
    let error = budget.reserve_read(attempt, 64).unwrap_err();
    assert!(format!("{error:#}").contains("状态原子替换失败"));
    let windows_error = error
        .chain()
        .find_map(|error| error.downcast_ref::<std::io::Error>())
        .and_then(std::io::Error::raw_os_error);
    assert!(
        matches!(windows_error, Some(5 | 32)),
        "不是Windows共享/访问拒绝：{error:#}"
    );
    assert_eq!(fs::read(&target).unwrap(), original);
    let frozen = snapshot(ctx.layout()).unwrap();
    assert_eq!(frozen.counters.observed_body_bytes, 7);
    assert_eq!(frozen.counters.uncertain_charge_bytes, 0);
    assert_eq!(frozen.reserved_body_bytes, 0); // 失败的64B预留从未提交。
    assert!(budget.view().unwrap().pending_reconciliation);
    drop(lock);
    assert!(budget.reserve_read(attempt, 1).is_err());
    assert!(budget
        .finish_attempt(attempt, AttemptOutcome::Failed)
        .is_err());
    assert!(budget.finish(DownloadOutcome::Failed).is_err());
    assert_eq!(fs::read(&target).unwrap(), original);
    drop(budget);
    drop(ctx);

    let reacquired = f.mutation();
    reconcile(&reacquired).unwrap();
    let restored = snapshot(reacquired.layout()).unwrap();
    assert_eq!(restored.counters.observed_body_bytes, 7);
    assert_eq!(restored.counters.uncertain_charge_bytes, 0);
    assert_eq!(restored.counters.requests, 1);
    assert_eq!(restored.reserved_body_bytes, 0);
    assert!(!restored.pending_reconciliation);
    let receipt = operation_receipt(reacquired.layout(), "download-atomic-replace-failure")
        .unwrap()
        .unwrap();
    assert_eq!(receipt.outcome, DownloadOutcome::Interrupted);
    assert_eq!(receipt.counters.observed_body_bytes, 7);
    assert_eq!(receipt.counters.uncertain_charge_bytes, 0);
}

#[test]
fn failed_settlement_cannot_refund_persisted_credit_or_continue_reads() {
    let f = Fixture::new("settle-failure");
    let ctx = f.mutation();
    let budget =
        DownloadBudget::begin(&ctx, "download-settle-failure", None, policy(), limits()).unwrap();
    let (attempt, credit) = budget
        .begin_attempt(&asset(), AttemptKind::Initial, 64)
        .unwrap();
    let target = ledger_path(ctx.layout()).unwrap();
    let preserved = target.with_extension("saved-ledger.json");
    fs::rename(&target, &preserved).unwrap();
    // 精确已知目录阻断替换；保留原ledger字节作为真实故障现场。
    fs::create_dir(&target).unwrap();
    assert!(budget.settle_read(credit, 7).is_err());
    assert!(budget.reserve_read(attempt, 1).is_err());
    assert!(budget.finish(DownloadOutcome::Failed).is_err());
    // 测试fixture修复阻断物，只恢复原已预留账本；不改其内容。
    fs::remove_dir(&target).unwrap();
    fs::rename(&preserved, &target).unwrap();
    drop(budget);
    assert_eq!(snapshot(ctx.layout()).unwrap().reserved_body_bytes, 64);
    let recovered = DownloadBudget::begin(
        &ctx,
        "download-after-settle-failure",
        None,
        policy(),
        limits(),
    )
    .unwrap();
    assert_eq!(recovered.view().unwrap().counters.observed_body_bytes, 0);
    assert_eq!(
        recovered.view().unwrap().counters.uncertain_charge_bytes,
        64
    );
    let original = operation_receipt(ctx.layout(), "download-settle-failure")
        .unwrap()
        .unwrap();
    assert_eq!(original.counters.uncertain_charge_bytes, 64);
    recovered.finish(DownloadOutcome::Succeeded).unwrap();
}

#[test]
fn terminal_outbox_survives_receipt_failure_and_redelivers_idempotently() {
    let f = Fixture::new("outbox");
    let ctx = f.mutation();
    let budget = DownloadBudget::begin(&ctx, "download-outbox", None, policy(), limits()).unwrap();
    let (attempt, credit) = budget
        .begin_attempt(&asset(), AttemptKind::Initial, 16)
        .unwrap();
    budget.settle_read(credit, 7).unwrap();
    budget
        .finish_attempt(attempt, AttemptOutcome::Completed)
        .unwrap();
    let directory = receipt_directory(ctx.layout()).unwrap();
    fs::create_dir_all(&directory).unwrap();
    let receipt_file = directory.join("download-outbox.json");
    fs::create_dir(&receipt_file).unwrap();
    assert!(budget.finish(DownloadOutcome::Failed).is_err());
    let bytes = fs::read(ledger_path(ctx.layout()).unwrap()).unwrap();
    let pending: Ledger = decode(&bytes).unwrap();
    assert!(pending.active.is_none());
    assert_eq!(
        pending
            .terminal_outbox
            .as_ref()
            .unwrap()
            .counters
            .observed_body_bytes,
        7
    );
    fs::remove_dir(&receipt_file).unwrap();
    let receipt = budget.finish(DownloadOutcome::Failed).unwrap();
    assert_eq!(receipt.counters.observed_body_bytes, 7);
    let again = budget.finish(DownloadOutcome::Succeeded).unwrap();
    assert_eq!(receipt, again); // 后来的不同调用outcome不能篡改已完成真实结果。
    assert_eq!(
        snapshot(ctx.layout()).unwrap().counters.observed_body_bytes,
        7
    );
    assert_eq!(
        operation_receipt(ctx.layout(), "download-outbox")
            .unwrap()
            .unwrap(),
        receipt
    );
}

#[test]
fn cumulative_root_cap_survives_new_operation_and_ignores_new_initial_policy() {
    let f = Fixture::new("cross-operation-cap");
    let ctx = f.mutation();
    let budget = DownloadBudget::begin(
        &ctx,
        "first-cap-operation",
        None,
        DownloadPolicy {
            root_cap_body_bytes: 10,
        },
        limits(),
    )
    .unwrap();
    let (attempt, credit) = budget
        .begin_attempt(&asset(), AttemptKind::Initial, 6)
        .unwrap();
    budget.settle_read(credit, 6).unwrap();
    budget
        .finish_attempt(attempt, AttemptOutcome::Completed)
        .unwrap();
    budget.finish(DownloadOutcome::Succeeded).unwrap();
    drop(budget);
    let second = DownloadBudget::begin(
        &ctx,
        "second-cap-operation",
        None,
        policy(), // 只能首次启用使用，不得覆盖已启用的10B上限。
        limits(),
    )
    .unwrap();
    let (attempt, credit) = second
        .begin_attempt(&asset(), AttemptKind::Initial, 8)
        .unwrap();
    assert_eq!(credit.bytes(), 4);
    second.settle_read(credit, 4).unwrap();
    second
        .finish_attempt(attempt, AttemptOutcome::Completed)
        .unwrap();
    assert!(second
        .begin_attempt(&asset(), AttemptKind::Initial, 1)
        .is_err());
    let receipt = second.finish(DownloadOutcome::Failed).unwrap();
    assert_eq!(receipt.counters.observed_body_bytes, 4);
    assert_eq!(receipt.root_start_counters.observed_body_bytes, 6);
    assert_eq!(receipt.root_end_counters.observed_body_bytes, 10);
    assert_eq!(
        snapshot(ctx.layout()).unwrap().root_cap_body_bytes,
        Some(10)
    );
}

#[test]
fn active_enrollment_never_recreates_a_missing_ledger() {
    let f = Fixture::new("missing-ledger");
    let ctx = f.mutation();
    initialize_policy(&ctx, policy()).unwrap();
    let marker = enrollment_path(ctx.layout()).unwrap();
    let original_marker = fs::read(&marker).unwrap();
    let target = ledger_path(ctx.layout()).unwrap();
    let preserved = target.with_extension("preserved-ledger.json");
    fs::rename(&target, &preserved).unwrap();
    assert!(snapshot(ctx.layout()).is_err());
    assert!(DownloadBudget::begin(&ctx, "missing-ledger", None, policy(), limits()).is_err());
    assert!(initialize_policy(&ctx, policy()).is_err());
    assert!(!target.exists());
    assert_eq!(fs::read(marker).unwrap(), original_marker);
    assert!(preserved.is_file());
}

#[test]
fn future_ledger_schema_is_preserved_and_refuses_all_mutation() {
    let f = Fixture::new("future-schema");
    let ctx = f.mutation();
    initialize_policy(&ctx, policy()).unwrap();
    let target = ledger_path(ctx.layout()).unwrap();
    let mut future: serde_json::Value =
        serde_json::from_slice(&fs::read(&target).unwrap()).unwrap();
    future["schema_version"] = 999.into();
    let bytes = serde_json::to_vec(&future).unwrap();
    fs::write(&target, &bytes).unwrap();
    assert!(snapshot(ctx.layout()).is_err());
    assert!(DownloadBudget::begin(&ctx, "future-schema", None, policy(), limits()).is_err());
    assert!(set_policy(&ctx, 1, policy()).is_err());
    assert_eq!(fs::read(target).unwrap(), bytes);
}

#[test]
fn malformed_receipt_blocks_policy_begin_and_reconciliation_before_any_ledger_write() {
    let f = Fixture::new("invalid-receipt");
    let ctx = f.mutation();
    let budget =
        DownloadBudget::begin(&ctx, "download-valid-receipt", None, policy(), limits()).unwrap();
    budget.finish(DownloadOutcome::Succeeded).unwrap();
    drop(budget);
    let target = receipt_directory(ctx.layout())
        .unwrap()
        .join("download-valid-receipt.json");
    let original: serde_json::Value = serde_json::from_slice(&fs::read(&target).unwrap()).unwrap();
    let mut future_schema = original.clone();
    future_schema["schema_version"] = 999.into();
    let mut future_field = original;
    future_field["future_field"] = true.into();
    for invalid in [
        serde_json::to_vec(&future_schema).unwrap(),
        serde_json::to_vec(&future_field).unwrap(),
        b"{broken receipt".to_vec(),
    ] {
        fs::write(&target, &invalid).unwrap();
        let ledger_before = fs::read(ledger_path(ctx.layout()).unwrap()).unwrap();
        let marker_before = fs::read(enrollment_path(ctx.layout()).unwrap()).unwrap();
        assert!(set_policy(
            &ctx,
            1,
            DownloadPolicy {
                root_cap_body_bytes: policy().root_cap_body_bytes + 1
            }
        )
        .is_err());
        assert!(
            DownloadBudget::begin(&ctx, "download-must-not-begin", None, policy(), limits())
                .is_err()
        );
        assert!(reconcile(&ctx).is_err());
        assert_eq!(
            fs::read(ledger_path(ctx.layout()).unwrap()).unwrap(),
            ledger_before
        );
        assert_eq!(
            fs::read(enrollment_path(ctx.layout()).unwrap()).unwrap(),
            marker_before
        );
        assert_eq!(fs::read(&target).unwrap(), invalid);
    }
}
