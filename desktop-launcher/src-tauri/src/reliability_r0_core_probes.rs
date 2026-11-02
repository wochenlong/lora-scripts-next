//! CR-020 R0 离线小夹具；复现基线缺陷并验证精确豁免的函数原型，不修生产逻辑。
use super::*;
use serde_json::{json, Value};

struct Fixture {
    root: PathBuf,
    parent: PathBuf,
    release: Release,
}

impl Fixture {
    fn new() -> Self {
        let parent = PathBuf::from(
            std::env::var_os("NEXT_TRAINER_RELIABILITY_FIXTURES")
                .expect("R0 探针必须由已标记专属夹具根启动"),
        );
        let root = parent.join(format!("rp01-{}-{}", std::process::id(), stamp()));
        let catalog = Catalog::embedded().unwrap();
        assert!(catalog.releases().len() >= 2, "自阻挡来自多发布守卫循环");
        let release = catalog.releases()[0].clone();
        let ctx = WorkspaceMutation::acquire(&root, &release.id).unwrap();
        Registry::default().store(&root).unwrap();
        drop(ctx);
        Self {
            root,
            parent,
            release,
        }
    }

    fn pending(&self, transaction: &str) -> PathBuf {
        #[derive(Serialize)]
        struct Plan {
            schema_version: u32,
            root_absolute: PathBuf,
            release_id: String,
            registry: Identity,
            boundary_sha256: String,
            old_binding: Option<model::EnvironmentBinding>,
            missing_wheels: Vec<String>,
            estimated_network_bytes: u64,
        }
        #[derive(Serialize)]
        struct Identity {
            bytes: u64,
            sha256: String,
        }

        let ctx = WorkspaceMutation::acquire(&self.root, &self.release.id).unwrap();
        let old = fs::read(self.root.join("state/registry.json")).unwrap();
        let boundary = instances::rebuild_observe_boundary(
            ctx.layout(),
            &crate::operations::CancelToken::new(),
        )
        .unwrap();
        let plan = Plan {
            schema_version: 1,
            root_absolute: self.root.clone(),
            release_id: self.release.id.clone(),
            registry: Identity {
                bytes: old.len() as u64,
                sha256: sha(&old),
            },
            boundary_sha256: instances::rebuild_boundary_sha(&boundary).unwrap(),
            old_binding: None,
            missing_wheels: vec![],
            estimated_network_bytes: 0,
        };
        let plan_value = serde_json::to_value(&plan).unwrap();
        let intent = json!({
            "schema_version": 1, "transaction": transaction,
            "root_absolute": self.root, "release_id": self.release.id,
            "candidate_id": "g0123456789abcdef", "status": "creating",
            "plan": plan_value, "plan_sha256": sha(&serde_json::to_vec(&plan).unwrap()),
            "boundary_sha256": plan.boundary_sha256, "old_registry": plan.registry,
            "candidate_state": null, "candidate_tree_sha256": null, "proof": null,
            "new_registry": null, "preservation_file": null, "preservation_sha256": null,
            "terminal_status": null, "failure": null,
        });
        let backup = self.root.join("backups").join(transaction);
        model::write_gui_transaction_bytes(
            &self.root,
            transaction,
            &backup.join("registry-old.json"),
            &old,
        )
        .unwrap();
        model::write_gui_transaction_bytes(
            &self.root,
            transaction,
            &backup.join("boundary.json"),
            &serde_json::to_vec(&boundary).unwrap(),
        )
        .unwrap();
        let path = self
            .root
            .join("state/gui-rebuild")
            .join(format!("{transaction}.json"));
        model::write_gui_transaction_json(&self.root, transaction, &path, &intent).unwrap();
        // 正式 history 会先反序列化、完整 validate，再向调用者暴露 pending。
        let history = gui_rebuild::history(&self.root, &self.release).unwrap();
        assert!(history["pending_transactions"]
            .as_array()
            .unwrap()
            .iter()
            .any(|v| v["transaction"] == transaction));
        path
    }

    fn call_core(&self, transaction: &str, operation_id: &str) -> String {
        let manager = OperationManager::default();
        let operation = manager.start(operation_id, OperationKind::Repair).unwrap();
        let mut engine = Engine::new(self.root.clone(), Arc::new(|_| {}));
        let error = engine
            .gui_lifecycle_operation(
                &self.root,
                &self.release.id,
                "recover_rebuild",
                None,
                Some(transaction),
                None,
                &operation,
            )
            .unwrap_err();
        assert!(!self
            .root
            .join("state/operations")
            .join(format!("{operation_id}.json"))
            .exists());
        assert_eq!(
            manager.snapshot(operation_id).unwrap().status,
            crate::operations::OperationStatus::Running
        );
        format!("{error:#}")
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let root = self.root.canonicalize().unwrap();
        let parent = self.parent.canonicalize().unwrap();
        assert_eq!(root.parent(), Some(parent.as_path()));
        assert!(self
            .root
            .file_name()
            .unwrap()
            .to_string_lossy()
            .starts_with("rp01-"));
        assert_eq!(
            fs::read_to_string(self.root.join(".launcher-workspace")).unwrap(),
            model::WORKSPACE_MARKER
        );
        fs::remove_dir_all(&self.root).unwrap();
    }
}

fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn emit(name: &str, value: Value) {
    println!("R0 {name}: {}", serde_json::to_string(&value).unwrap());
    let base = PathBuf::from(std::env::var_os("NEXT_TRAINER_RELIABILITY_EVIDENCE").unwrap());
    fs::write(
        base.join(format!("{name}.json")),
        serde_json::to_vec_pretty(&value).unwrap(),
    )
    .unwrap();
}

#[test]
#[ignore = "CR-020 R0 专属小夹具/证据根，由限时探针脚本显式调用"]
fn baseline_core_recovery_is_blocked_by_its_own_pending_and_rejects_a_second_pending() {
    let f = Fixture::new();
    let own = "gui-rebuild-rp01-own";
    let path = f.pending(own);
    let registry_before = fs::read(f.root.join("state/registry.json")).unwrap();
    let own_before = fs::read(&path).unwrap();
    let error = f.call_core(own, "rp01-self-block");
    assert!(
        error.contains(&format!("GUI重建事务{own}待恢复")),
        "{error}"
    );
    assert_eq!(fs::read(&path).unwrap(), own_before);
    assert_eq!(
        fs::read(f.root.join("state/registry.json")).unwrap(),
        registry_before
    );
    emit(
        "baseline-self-block",
        json!({
            "classification": "product_baseline_defect_reproduced", "entry": "Engine::gui_lifecycle_operation",
            "action": "recover_rebuild", "error": error, "own_pending_validated": true,
            "registry_sha256_before": sha(&registry_before), "registry_sha256_after": sha(&fs::read(f.root.join("state/registry.json")).unwrap()),
            "intent_sha256_before": sha(&own_before), "intent_sha256_after": sha(&fs::read(&path).unwrap()),
            "operation_persisted": false, "memory_operation_status": "running", "fixture_root": f.root,
        }),
    );

    // 正式底层恢复创建完整合法 orphan；不能只改 status 伪造终态授权。
    let ctx = WorkspaceMutation::acquire(&f.root, &f.release.id).unwrap();
    let recovered = gui_rebuild::recover(
        &ctx,
        &f.release,
        own,
        &crate::operations::CancelToken::new(),
        |_| panic!("不完整小夹具不能进入 runtime 验证"),
        |_, _| panic!("不完整小夹具不能进入入口探针"),
    )
    .unwrap();
    assert_eq!(recovered["status"], "orphaned");
    drop(ctx);
    gui_rebuild::assert_ready(&f.root, &f.release).unwrap();
    let other = "gui-rebuild-rp01-second";
    let other_path = f.pending(other);
    let second_before = fs::read(&other_path).unwrap();
    let error = f.call_core(own, "rp01-second-block");
    assert!(
        error.contains(&format!("GUI重建事务{other}待恢复")),
        "{error}"
    );
    assert_eq!(fs::read(&other_path).unwrap(), second_before);
    assert_eq!(
        fs::read(f.root.join("state/registry.json")).unwrap(),
        registry_before
    );
    emit(
        "baseline-second-pending",
        json!({
            "classification": "existing_guard_behavior", "entry": "Engine::gui_lifecycle_operation",
            "same_release": true, "target": own, "other_pending": other, "error": error,
        "registry_unchanged": true, "other_intent_unchanged": true, "operation_persisted": false,
        "target_finished_by_production_lower_recover": recovered,
        }),
    );
}

#[test]
#[ignore = "CR-020 R0 专属小夹具/证据根，由限时探针脚本显式调用"]
fn legitimate_committing_from_production_fault_window_is_self_blocked_by_core() {
    let f = Fixture::new();
    let transaction = "gui-rebuild-rp01-committing";
    let path = f.pending(transaction);
    let registry_before = fs::read(f.root.join("state/registry.json")).unwrap();
    let ctx = WorkspaceMutation::acquire(&f.root, &f.release.id).unwrap();
    gui_rebuild::reliability_r0_rebuild_fixture::prepare_orphan_commit_boundary(
        &ctx,
        &f.release,
        transaction,
    )
    .unwrap();
    drop(ctx);
    let intent_before = fs::read(&path).unwrap();
    let intent: Value = serde_json::from_slice(&intent_before).unwrap();
    assert_eq!(intent["status"], "committing");
    assert_eq!(intent["terminal_status"], "orphaned");
    assert!(!intent["candidate_state"].is_null());
    assert!(!intent["candidate_tree_sha256"].is_null());
    assert!(!intent["preservation_sha256"].is_null());
    assert!(!intent["preservation_file"].is_null());
    gui_rebuild::history(&f.root, &f.release).unwrap();
    let error = f.call_core(transaction, "rp01-committing-self-block");
    assert!(
        error.contains(&format!("GUI重建事务{transaction}待恢复")),
        "{error}"
    );
    assert_eq!(fs::read(&path).unwrap(), intent_before);
    assert_eq!(
        fs::read(f.root.join("state/registry.json")).unwrap(),
        registry_before
    );
    emit(
        "baseline-committing-self-block",
        json!({
            "classification": "product_baseline_defect_reproduced", "entry": "Engine::gui_lifecycle_operation",
            "action": "recover_rebuild", "status": intent["status"], "terminal_status": intent["terminal_status"],
        "constructed_by": "test-only factory invokes production rebuild_create + prepare_commit(false), stops before finish",
        "fault_boundary": "simulated process interruption immediately after complete committing authority persisted",
        "real_gui_fault_injected": false, "core_error": error, "intent": intent,
            "candidate_and_preservation_produced_by_formal_transaction": true,
            "registry_sha256_before": sha(&registry_before), "registry_sha256_after": sha(&fs::read(f.root.join("state/registry.json")).unwrap()),
            "intent_sha256_before": sha(&intent_before), "intent_sha256_after": sha(&fs::read(&path).unwrap()),
            "operation_persisted": false, "no_healthy_receipt_fabricated": true,
            "fixture_root": f.root,
        }),
    );
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct PendingIdentity {
    root: PathBuf,
    release: String,
    kind: &'static str,
    transaction: String,
}

// 候选函数原型：生产接入前仍须完整 validate 所有记录；只能豁免精确目标自身。
fn assert_other_pending_ready_prototype(
    validated_pending: &[PendingIdentity],
    target: &PendingIdentity,
) -> std::result::Result<(), PendingIdentity> {
    if let Some(other) = validated_pending.iter().find(|record| *record != target) {
        return Err(other.clone());
    }
    Ok(())
}

#[test]
#[ignore = "CR-020 R0 专属证据根，由限时探针脚本显式调用"]
fn exact_self_exception_prototype_rejects_same_release_second_other_release_kind_and_root() {
    let target = PendingIdentity {
        root: PathBuf::from("F:/fixture"),
        release: "dev-one".into(),
        kind: "rebuild",
        transaction: "gui-rebuild-own".into(),
    };
    assert_other_pending_ready_prototype(&[target.clone()], &target).unwrap();
    let mut second = target.clone();
    second.transaction = "gui-rebuild-second".into();
    let mut other_release = target.clone();
    other_release.release = "dev-two".into();
    let mut other_kind = target.clone();
    other_kind.kind = "binding-switch";
    let mut other_root = target.clone();
    other_root.root = PathBuf::from("F:/different-fixture");
    for other in [second, other_release, other_kind, other_root] {
        assert_eq!(
            assert_other_pending_ready_prototype(&[target.clone(), other.clone()], &target),
            Err(other)
        );
    }
    emit(
        "exact-exception-prototype",
        json!({
            "classification": "prototype_feasible_only", "production_logic_changed": false,
            "self_only_allowed": true, "same_release_second_rejected": true,
            "other_release_rejected": true, "other_kind_rejected": true, "other_root_rejected": true,
            "required_precondition": "all records validated before exemption; root uses validated workspace identity",
        }),
    );
}
