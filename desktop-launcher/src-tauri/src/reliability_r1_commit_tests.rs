//! R1 取消/提交门定向合同；真实小型控制文件，不授环境健康或原生验收。
use super::*;
use crate::operations::{
    CancelReceipt, Cancelled, OperationKind, OperationManager, OperationStatus,
};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Barrier;

static NEXT: AtomicU64 = AtomicU64::new(0);

struct Fixture {
    root: PathBuf,
    parent: PathBuf,
    release: Release,
    mutation: model::WorkspaceMutation,
}

impl Fixture {
    fn new() -> Self {
        let parent = std::env::var_os("NEXT_TRAINER_RELIABILITY_FIXTURES")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir);
        let root = parent.join(format!(
            "r1commit-{}-{}-{}",
            std::process::id(),
            model::now(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        assert!(!root.exists());
        let release = Catalog::embedded().unwrap().releases()[0].clone();
        let mutation = model::WorkspaceMutation::acquire(&root, &release.id).unwrap();
        Registry::default().store(&root).unwrap();
        fs::write(
            root.join(".codex-r1-commit-owner.json"),
            b"{\"test_only\":true}\n",
        )
        .unwrap();
        Self {
            root,
            parent,
            release,
            mutation,
        }
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        // 文件租约字段在Drop返回后才释放，Windows清理由外层自有根统一收口。
        assert_eq!(self.root.parent(), Some(self.parent.as_path()));
        assert!(self
            .root
            .file_name()
            .is_some_and(|name| name.to_string_lossy().starts_with("r1commit-")));
    }
}

#[test]
fn accepted_cancel_wins_lifecycle_success_without_registry_write() {
    let fixture = Fixture::new();
    let manager = OperationManager::default();
    let operation = manager
        .start("r1-success-cancel", OperationKind::Repair)
        .unwrap();
    let registry = fixture.root.join("state/registry.json");
    let before = fs::read(&registry).unwrap();
    assert_eq!(
        manager.cancel("r1-success-cancel").unwrap(),
        CancelReceipt::Accepted
    );
    let result = complete_gui_lifecycle_success(
        &fixture.mutation,
        &fixture.release.id,
        &operation.cancel_token(),
    );
    assert!(
        result
            .as_ref()
            .is_err_and(|error| error.downcast_ref::<Cancelled>().is_some()),
        "已接受取消后，正式生命周期成功收口必须返回Cancelled，实际={result:?}"
    );
    assert_eq!(fs::read(registry).unwrap(), before);
    let result = finish_gui_lifecycle_result(&fixture.mutation, &operation, result);
    assert!(result.unwrap_err().downcast_ref::<Cancelled>().is_some());
    assert_eq!(
        manager.snapshot("r1-success-cancel").unwrap().status,
        OperationStatus::Cancelled
    );
    assert_eq!(
        manager.cancel("r1-success-cancel").unwrap(),
        CancelReceipt::AlreadyFinished
    );
}

#[test]
fn accepted_cancel_prevents_atomic_registry_write_and_remains_requested() {
    let fixture = Fixture::new();
    let manager = OperationManager::default();
    let operation = manager
        .start("r1-write-cancel", OperationKind::Repair)
        .unwrap();
    let cancel = operation.cancel_token();
    let registry = fixture.root.join("state/registry.json");
    let before = fs::read(&registry).unwrap();
    assert_eq!(
        manager.cancel("r1-write-cancel").unwrap(),
        CancelReceipt::Accepted
    );
    assert_eq!(
        manager.cancel("r1-write-cancel").unwrap(),
        CancelReceipt::AlreadyRequested
    );
    let result = (|| -> Result<()> {
        cancel.enter_commit()?;
        model::write_gui_transaction_bytes(
            &fixture.root,
            "gui-rebuild-r1-write-cancel",
            &registry,
            b"must never be written",
        )
    })();
    assert!(result
        .as_ref()
        .unwrap_err()
        .downcast_ref::<Cancelled>()
        .is_some());
    assert_eq!(fs::read(registry).unwrap(), before);
    assert!(!fixture
        .root
        .join("backups/gui-rebuild-r1-write-cancel")
        .exists());
    assert!(cancel.check().is_err());
    assert!(cancel.enter_commit().is_err());
    assert!(finish_gui_lifecycle_result(&fixture.mutation, &operation, result).is_err());
    assert_eq!(
        manager.snapshot("r1-write-cancel").unwrap().status,
        OperationStatus::Cancelled
    );
}

#[test]
fn commit_wins_cancel_receipts_and_actual_registry_write_stays_succeeded() {
    let fixture = Fixture::new();
    let manager = OperationManager::default();
    let operation = manager
        .start("r1-write-commit", OperationKind::Repair)
        .unwrap();
    let cancel = operation.cancel_token();
    operation.persist(&fixture.mutation).unwrap();
    let registry = fixture.root.join("state/registry.json");
    // 只改变JSON空白验证真实原子字节写，不构造健康/绑定证明。
    let mut desired = fs::read(&registry).unwrap();
    desired.extend_from_slice(b" \n");
    cancel.enter_commit().unwrap();
    let event_seq = manager.snapshot("r1-write-commit").unwrap().event_seq;
    for _ in 0..2 {
        assert_eq!(
            manager.cancel("r1-write-commit").unwrap(),
            CancelReceipt::CommitInProgress
        );
    }
    assert!(!cancel.is_cancel_requested());
    assert!(cancel.check().is_ok());
    assert!(manager
        .events_since("r1-write-commit", event_seq)
        .unwrap()
        .is_empty());
    let result = model::write_gui_transaction_bytes(
        &fixture.root,
        "gui-rebuild-r1-write-commit",
        &registry,
        &desired,
    )
    .and_then(|()| complete_gui_lifecycle_success(&fixture.mutation, &fixture.release.id, &cancel));
    finish_gui_lifecycle_result(&fixture.mutation, &operation, result).unwrap();
    assert_eq!(fs::read(registry).unwrap(), desired);
    let snapshot = manager.snapshot("r1-write-commit").unwrap();
    assert_eq!(snapshot.status, OperationStatus::Succeeded);
    assert!(!snapshot.cancel_requested);
    assert_eq!(
        manager.cancel("r1-write-commit").unwrap(),
        CancelReceipt::AlreadyFinished
    );
    // 终态后也不重新开放旧token；只有Manager的终态视图返回AlreadyFinished。
    assert_eq!(cancel.request(), CancelReceipt::CommitInProgress);
    assert!(cancel.enter_commit().is_ok());
}

#[test]
fn actual_atomic_write_failure_is_failed_and_preserves_registry_and_backup() {
    let fixture = Fixture::new();
    let manager = OperationManager::default();
    let operation = manager
        .start("r1-write-failure", OperationKind::Repair)
        .unwrap();
    operation.persist(&fixture.mutation).unwrap();
    let cancel = operation.cancel_token();
    let registry = fixture.root.join("state/registry.json");
    let before = fs::read(&registry).unwrap();
    let transaction = "gui-rebuild-r1-io-failure";
    let backup = fixture.root.join("backups").join(transaction);
    fs::create_dir(&backup).unwrap();
    let evidence = backup.join("preexisting-backup.bin");
    fs::write(&evidence, b"preserve exact backup bytes").unwrap();
    // 真实文件阻挡事务临时目录，产生操作系统I/O错误；不伪造pending或健康记录。
    fs::write(backup.join("atomic-writes"), b"deliberately occupied").unwrap();
    cancel.enter_commit().unwrap();
    let result = model::write_gui_transaction_bytes(
        &fixture.root,
        transaction,
        &registry,
        b"uncommitted bytes",
    );
    assert!(result.is_err());
    assert_eq!(
        manager.cancel("r1-write-failure").unwrap(),
        CancelReceipt::CommitInProgress
    );
    assert!(finish_gui_lifecycle_result(&fixture.mutation, &operation, result).is_err());
    let snapshot = manager.snapshot("r1-write-failure").unwrap();
    assert_eq!(snapshot.status, OperationStatus::Failed);
    assert!(!snapshot.cancel_requested);
    assert_eq!(snapshot.error.unwrap().code, "gui_lifecycle_failed");
    let persisted: crate::operations::OperationSnapshot = serde_json::from_slice(
        &fs::read(fixture.root.join("state/operations/r1-write-failure.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(persisted.status, OperationStatus::Failed);
    assert!(!persisted.cancel_requested);
    assert_eq!(fs::read(registry).unwrap(), before);
    assert_eq!(fs::read(evidence).unwrap(), b"preserve exact backup bytes");
}

#[test]
fn lifecycle_success_without_registry_write_closes_cancel_before_short_sync() {
    let fixture = Fixture::new();
    let manager = OperationManager::default();
    let operation = manager
        .start("r1-success-no-write", OperationKind::Repair)
        .unwrap();
    let cancel = operation.cancel_token();
    let registry = fixture.root.join("state/registry.json");
    let before = fs::read(&registry).unwrap();
    complete_gui_lifecycle_success(&fixture.mutation, &fixture.release.id, &cancel).unwrap();
    assert_eq!(
        manager.cancel("r1-success-no-write").unwrap(),
        CancelReceipt::CommitInProgress
    );
    finish_gui_lifecycle_result(&fixture.mutation, &operation, Ok(())).unwrap();
    assert_eq!(
        manager.snapshot("r1-success-no-write").unwrap().status,
        OperationStatus::Succeeded
    );
    assert_eq!(fs::read(registry).unwrap(), before);
}

#[test]
fn simultaneous_cancel_and_commit_have_exactly_one_winner() {
    for serial in 0..16 {
        let manager = Arc::new(OperationManager::default());
        let id = format!("r1-race-{serial}");
        let operation = manager.start(&id, OperationKind::Repair).unwrap();
        let cancel = operation.cancel_token();
        let other = cancel.clone();
        let ready = Arc::new(Barrier::new(2));
        let committer_ready = ready.clone();
        let committer = thread::spawn(move || {
            committer_ready.wait();
            other.enter_commit()
        });
        ready.wait();
        let receipt = manager.cancel(&id).unwrap();
        let committed = committer.join().unwrap();
        match receipt {
            CancelReceipt::Accepted => {
                assert_eq!(committed, Err(Cancelled));
                assert!(cancel.is_cancel_requested());
                assert_eq!(
                    manager.cancel(&id).unwrap(),
                    CancelReceipt::AlreadyRequested
                );
                operation.finish(OperationStatus::Cancelled, None).unwrap();
            }
            CancelReceipt::CommitInProgress => {
                assert_eq!(committed, Ok(()));
                assert!(!cancel.is_cancel_requested());
                assert!(cancel.enter_commit().is_ok());
                operation.finish(OperationStatus::Succeeded, None).unwrap();
            }
            receipt => panic!("首次取消返回了非法竞争结果：{receipt:?}"),
        }
        assert_eq!(manager.cancel(&id).unwrap(), CancelReceipt::AlreadyFinished);
    }
}

#[test]
fn query_style_direct_request_remains_idempotent_without_commit_gate() {
    let cancel = crate::operations::CancelToken::new();
    assert_eq!(cancel.request(), CancelReceipt::Accepted);
    assert_eq!(cancel.request(), CancelReceipt::AlreadyRequested);
    assert_eq!(cancel.check(), Err(Cancelled));
    assert_eq!(cancel.enter_commit(), Err(Cancelled));
}
