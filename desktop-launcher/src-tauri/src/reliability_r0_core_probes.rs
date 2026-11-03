//! CR-020 R1 正式 Core 恢复回归；R0 的缺陷快照保留在外部证据中。
use super::*;
use serde_json::{json, Value};
use std::sync::atomic::{AtomicU64, Ordering};

static NEXT: AtomicU64 = AtomicU64::new(0);

struct Fixture {
    root: PathBuf,
    parent: PathBuf,
    release: Release,
}

#[derive(Serialize)]
struct Identity {
    bytes: u64,
    sha256: String,
}
fn identity(bytes: &[u8]) -> Identity {
    Identity {
        bytes: bytes.len() as u64,
        sha256: sha(bytes),
    }
}
fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

impl Fixture {
    fn new() -> Self {
        let parent = std::env::var_os("NEXT_TRAINER_RELIABILITY_FIXTURES")
            .map(PathBuf::from)
            .unwrap_or_else(std::env::temp_dir);
        let root = parent.join(format!(
            "rp01-{}-{}-{}",
            std::process::id(),
            stamp(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let release = Catalog::embedded().unwrap().releases()[0].clone();
        let ctx = WorkspaceMutation::acquire(&root, &release.id).unwrap();
        Registry::default().store(&root).unwrap();
        fs::write(
            root.join("profiles/default/user_data/sentinel.txt"),
            b"user data must survive",
        )
        .unwrap();
        drop(ctx);
        Self {
            root,
            parent,
            release,
        }
    }

    fn pending_for(&self, release: &Release, transaction: &str, candidate: &str) -> PathBuf {
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
        let ctx = WorkspaceMutation::acquire_existing(&self.root, &release.id).unwrap();
        let old = fs::read(self.root.join("state/registry.json")).unwrap();
        let boundary = instances::rebuild_observe_boundary(
            ctx.layout(),
            &crate::operations::CancelToken::new(),
        )
        .unwrap();
        let plan = Plan {
            schema_version: 1,
            root_absolute: self.root.clone(),
            release_id: release.id.clone(),
            registry: identity(&old),
            boundary_sha256: instances::rebuild_boundary_sha(&boundary).unwrap(),
            old_binding: None,
            missing_wheels: vec![],
            estimated_network_bytes: 0,
        };
        let intent = json!({
            "schema_version": 1, "transaction": transaction, "root_absolute": self.root,
            "release_id": release.id, "candidate_id": candidate, "status": "creating",
            "plan": serde_json::to_value(&plan).unwrap(), "plan_sha256": sha(&serde_json::to_vec(&plan).unwrap()),
            "boundary_sha256": plan.boundary_sha256, "old_registry": plan.registry,
            "candidate_state": null, "candidate_tree_sha256": null, "proof": null, "new_registry": null,
            "preservation_file": null, "preservation_sha256": null, "terminal_status": null, "failure": null,
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
        gui_rebuild::history(&self.root, release).unwrap();
        path
    }

    fn pending(&self, transaction: &str) -> PathBuf {
        self.pending_for(&self.release, transaction, "g0123456789abcdef")
    }

    fn committing(&self, transaction: &str) -> PathBuf {
        let path = self.pending(transaction);
        let ctx = WorkspaceMutation::acquire_existing(&self.root, &self.release.id).unwrap();
        gui_rebuild::reliability_r0_rebuild_fixture::prepare_orphan_commit_boundary(
            &ctx,
            &self.release,
            transaction,
        )
        .unwrap();
        path
    }

    fn core(
        &self,
        root: &Path,
        release: &str,
        action: &str,
        transaction: Option<&str>,
        operation_id: &str,
        cancelled: bool,
    ) -> (Result<()>, crate::operations::OperationSnapshot) {
        let (result, snapshot, _) = self.core_with_checkpoint(
            root,
            release,
            action,
            transaction,
            operation_id,
            cancelled,
            None,
        );
        (result, snapshot)
    }

    #[allow(clippy::too_many_arguments)]
    fn core_with_checkpoint(
        &self,
        root: &Path,
        release: &str,
        action: &str,
        transaction: Option<&str>,
        operation_id: &str,
        cancelled: bool,
        checkpoint: Option<&'static str>,
    ) -> (
        Result<()>,
        crate::operations::OperationSnapshot,
        Option<Value>,
    ) {
        let manager = Arc::new(OperationManager::default());
        let operation = manager.start(operation_id, OperationKind::Repair).unwrap();
        if cancelled {
            manager.cancel(operation_id).unwrap();
        }
        if let Some(checkpoint) = checkpoint {
            let manager = manager.clone();
            let operation_id = operation_id.to_owned();
            gui_rebuild::reliability_r0_rebuild_fixture::arm_cancellation_checkpoint(
                transaction.unwrap(),
                checkpoint,
                move || {
                    assert_eq!(
                        manager.cancel(&operation_id).unwrap(),
                        crate::operations::CancelReceipt::Accepted
                    );
                },
            );
        }
        let mut engine = Engine::new(self.root.clone(), Arc::new(|_| {}));
        let result = engine.gui_lifecycle_operation(
            root,
            release,
            action,
            None,
            transaction,
            None,
            &operation,
        );
        let observation = checkpoint
            .map(|_| gui_rebuild::reliability_r0_rebuild_fixture::take_cancellation_checkpoint());
        (result, manager.snapshot(operation_id).unwrap(), observation)
    }

    fn recover(
        &self,
        transaction: &str,
        operation_id: &str,
    ) -> crate::operations::OperationSnapshot {
        let (result, snapshot) = self.core(
            &self.root,
            &self.release.id,
            "recover_rebuild",
            Some(transaction),
            operation_id,
            false,
        );
        result.unwrap();
        assert_eq!(
            snapshot.status,
            crate::operations::OperationStatus::Succeeded
        );
        let disk: crate::operations::OperationSnapshot = serde_json::from_slice(
            &fs::read(
                self.root
                    .join("state/operations")
                    .join(format!("{operation_id}.json")),
            )
            .unwrap(),
        )
        .unwrap();
        assert_eq!(disk.status, snapshot.status);
        snapshot
    }

    fn reject(
        &self,
        root: &Path,
        release: &str,
        action: &str,
        transaction: Option<&str>,
        operation_id: &str,
    ) -> String {
        let before = tree(&self.root);
        let wrong_root_before = if root != self.root {
            Some(tree(root))
        } else {
            None
        };
        let (result, snapshot) = self.core(root, release, action, transaction, operation_id, false);
        let error = format!("{:#}", result.unwrap_err());
        assert_eq!(tree(&self.root), before, "拒绝修改了合法工作区：{error}");
        if let Some(wrong_before) = wrong_root_before {
            assert_eq!(tree(root), wrong_before, "拒绝初始化/修改了错误根：{error}");
        }
        assert_eq!(snapshot.status, crate::operations::OperationStatus::Running);
        assert!(!root
            .join("state/operations")
            .join(format!("{operation_id}.json"))
            .exists());
        error
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        let resolved = self.root.canonicalize().unwrap();
        assert_eq!(
            resolved.parent(),
            Some(self.parent.canonicalize().unwrap().as_path())
        );
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

/// 小夹具完整树；目录和文件内容都纳入，错误根初始化也会被发现。
fn tree(root: &Path) -> BTreeMap<PathBuf, Option<String>> {
    let mut output = BTreeMap::new();
    let mut pending = vec![root.to_path_buf()];
    while let Some(path) = pending.pop() {
        match fs::symlink_metadata(&path) {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => continue,
            Err(error) => panic!("tree read: {error}"),
            Ok(meta) => {
                let relative = path.strip_prefix(root).unwrap().to_path_buf();
                if meta.is_dir() {
                    output.insert(relative, None);
                    pending.extend(fs::read_dir(&path).unwrap().map(|e| e.unwrap().path()));
                } else if relative == Path::new(".launcher-lock") {
                    // Windows 的真实 lease 禁止读取锁区；该控制文件固定为空，以元数据断言。
                    assert_eq!(meta.len(), 0);
                    output.insert(relative, Some(sha(b"")));
                } else {
                    output.insert(relative, Some(sha(&fs::read(&path).unwrap())));
                }
            }
        }
    }
    output
}

fn emit(name: &str, value: Value) {
    println!("R1 {name}: {}", serde_json::to_string(&value).unwrap());
    if let Some(base) = std::env::var_os("NEXT_TRAINER_RELIABILITY_EVIDENCE") {
        fs::write(
            PathBuf::from(base).join(format!("{name}.json")),
            serde_json::to_vec_pretty(&value).unwrap(),
        )
        .unwrap();
    }
}

#[test]
fn core_recovers_legitimate_committing_and_repeats_idempotently() {
    let f = Fixture::new();
    let transaction = "gui-rebuild-r1-committing";
    let path = f.committing(transaction);
    let before = fs::read(&path).unwrap();
    let registry = fs::read(f.root.join("state/registry.json")).unwrap();
    let operation = f.recover(transaction, "r1-committing-recovery");
    let terminal = fs::read(&path).unwrap();
    let intent: Value = serde_json::from_slice(&terminal).unwrap();
    assert_eq!(intent["status"], "orphaned");
    assert_eq!(intent["terminal_status"], "orphaned");
    assert_eq!(
        fs::read(f.root.join("state/registry.json")).unwrap(),
        registry
    );
    f.recover(transaction, "r1-committing-repeat");
    assert_eq!(fs::read(&path).unwrap(), terminal);
    assert_eq!(
        fs::read(f.root.join("state/registry.json")).unwrap(),
        registry
    );
    assert_eq!(
        fs::read(f.root.join("profiles/default/user_data/sentinel.txt")).unwrap(),
        b"user data must survive"
    );
    emit(
        "core-committing-recovery",
        json!({"entry":"Engine::gui_lifecycle_operation", "operation":operation,
        "initial_intent_sha256":sha(&before), "terminal_intent_sha256":sha(&terminal), "terminal":"orphaned",
        "registry_unchanged":true, "user_data_unchanged":true, "repeat_idempotent":true, "healthy_receipt_fabricated":false}),
    );
}

#[test]
fn core_recovers_creating_through_formal_pipeline() {
    let f = Fixture::new();
    let transaction = "gui-rebuild-r1-creating";
    let path = f.pending(transaction);
    f.recover(transaction, "r1-creating-recovery");
    let intent: Value = serde_json::from_slice(&fs::read(path).unwrap()).unwrap();
    assert_eq!(intent["status"], "orphaned");
    assert!(intent["preservation_sha256"].is_string());
}

#[test]
fn core_refuses_wrong_identity_kind_missing_marker_and_unknown_action_without_writes() {
    let f = Fixture::new();
    let transaction = "gui-rebuild-r1-identity";
    f.committing(transaction);
    let other = Catalog::embedded().unwrap().releases()[1].clone();
    let mut results = Vec::new();
    for (label, root, release, action, tx) in [
        (
            "wrong-tx",
            f.root.clone(),
            f.release.id.clone(),
            "recover_rebuild",
            Some("gui-rebuild-r1-missing"),
        ),
        (
            "wrong-release",
            f.root.clone(),
            other.id.clone(),
            "recover_rebuild",
            Some(transaction),
        ),
        (
            "wrong-kind",
            f.root.clone(),
            f.release.id.clone(),
            "recover_rollback",
            Some(transaction),
        ),
        (
            "missing-tx",
            f.root.clone(),
            f.release.id.clone(),
            "recover_rebuild",
            None,
        ),
        (
            "unknown-action",
            f.root.join("never-created"),
            f.release.id.clone(),
            "unknown-r1-action",
            Some(transaction),
        ),
        (
            "missing-root",
            f.root.join("never-created"),
            f.release.id.clone(),
            "recover_rebuild",
            Some(transaction),
        ),
    ] {
        let error = f.reject(&root, &release, action, tx, &format!("r1-{label}"));
        results.push(json!({"case":label,"error":error,"zero_writes":true}));
    }
    let wrong = f.root.join("existing-empty");
    fs::create_dir(&wrong).unwrap();
    results.push(json!({"case":"existing-empty-root","error":f.reject(&wrong,&f.release.id,"recover_rebuild",Some(transaction),"r1-empty-root"),"zero_writes":true}));
    fs::write(wrong.join(".launcher-workspace"), b"wrong marker").unwrap();
    results.push(json!({"case":"wrong-marker","error":f.reject(&wrong,&f.release.id,"recover_rebuild",Some(transaction),"r1-wrong-marker"),"zero_writes":true}));
    fs::write(wrong.join(".launcher-workspace"), model::WORKSPACE_MARKER).unwrap();
    fs::write(wrong.join(".launcher-lock"), b"").unwrap();
    results.push(json!({"case":"marker-and-lock-no-standard-directories","error":f.reject(&wrong,&f.release.id,"recover_rebuild",Some(transaction),"r1-no-directories"),"zero_writes":true}));
    f.recover(transaction, "r1-after-identity-refusals");
    emit(
        "core-identity-refusals",
        json!({"cases":results,"legal_recovery_after_refusals":true}),
    );
}

#[test]
fn core_refuses_damaged_plan_and_backup_before_persisting_operation() {
    let f = Fixture::new();
    let transaction = "gui-rebuild-r1-damage";
    let path = f.committing(transaction);
    let original = fs::read(&path).unwrap();
    let mut intent: Value = serde_json::from_slice(&original).unwrap();
    let mut results = Vec::new();
    intent["plan_sha256"] = json!("0".repeat(64));
    fs::write(&path, serde_json::to_vec(&intent).unwrap()).unwrap();
    results.push(json!({"case":"plan-digest","error":f.reject(&f.root,&f.release.id,"recover_rebuild",Some(transaction),"r1-plan-damage"),"zero_writes":true}));
    fs::write(&path, &original).unwrap();
    let intent: Value = serde_json::from_slice(&original).unwrap();
    for (index, name) in [
        "registry-old.json".to_owned(),
        "boundary.json".to_owned(),
        intent["preservation_file"].as_str().unwrap().to_owned(),
    ]
    .iter()
    .enumerate()
    {
        let backup = f.root.join("backups").join(transaction).join(name);
        let bytes = fs::read(&backup).unwrap();
        fs::write(&backup, b"corrupt backup").unwrap();
        results.push(json!({"case":name,"error":f.reject(&f.root,&f.release.id,"recover_rebuild",Some(transaction),&format!("r1-backup-damage-{index}")),"zero_writes":true}));
        fs::write(backup, bytes).unwrap();
    }
    f.recover(transaction, "r1-after-damage-refusals");
    emit(
        "core-damage-refusals",
        json!({"cases":results,"legal_recovery_after_refusals":true}),
    );
}

#[test]
fn core_refuses_missing_recovery_authority_and_profile_structure_without_initializing() {
    let f = Fixture::new();
    let tx = "gui-rebuild-r1-missing-structure";
    f.committing(tx);
    let mut cases = Vec::new();
    for (index, relative) in [
        "state/registry.json",
        "profiles/default/profile.json",
        "backups",
        "profiles/default/user_data",
        "profiles/default/library",
        "profiles/default/compat",
    ]
    .iter()
    .enumerate()
    {
        let source = f.root.join(relative);
        let saved = f.root.join(format!("r1-held-required-{index}"));
        fs::rename(&source, &saved).unwrap();
        let error = f.reject(
            &f.root,
            &f.release.id,
            "recover_rebuild",
            Some(tx),
            &format!("r1-required-{index}"),
        );
        cases.push(json!({"missing":relative,"error":error,"zero_initialization_writes":true}));
        fs::rename(saved, source).unwrap();
    }
    f.recover(tx, "r1-after-required-structure-restored");
    emit(
        "core-required-structure",
        json!({"cases":cases,"recovery_after_exact_restore":true}),
    );
}

#[test]
fn core_rejects_same_release_other_release_unknown_and_terminal_conflicts() {
    let f = Fixture::new();
    let own = "gui-rebuild-r1-conflict-target";
    f.committing(own);
    let registry = fs::read(f.root.join("state/registry.json")).unwrap();
    let mut results = Vec::new();
    for (index, release) in [
        f.release.clone(),
        Catalog::embedded().unwrap().releases()[1].clone(),
    ]
    .iter()
    .enumerate()
    {
        let tx = format!("gui-rebuild-r1-conflict-other-{index}");
        let path = f.pending_for(release, &tx, "g1111111111111111");
        let error = f.reject(
            &f.root,
            &f.release.id,
            "recover_rebuild",
            Some(own),
            &format!("r1-other-{index}"),
        );
        assert!(error.contains(&tx), "{error}");
        results.push(json!({"release":release.id,"other_tx":tx,"error":error,"zero_writes":true}));
        fs::remove_file(path).unwrap();
    }
    let unknown = f.root.join("state/gui-rebuild/unknown.json");
    fs::write(&unknown, b"{}").unwrap();
    results.push(json!({"case":"unknown-record","error":f.reject(&f.root,&f.release.id,"recover_rebuild",Some(own),"r1-unknown-record"),"zero_writes":true}));
    fs::remove_file(unknown).unwrap();
    f.recover(own, "r1-before-terminal-conflict");
    let other = "gui-rebuild-r1-terminal-other";
    let path = f.pending_for(&f.release, other, "g1111111111111111");
    let error = f.reject(
        &f.root,
        &f.release.id,
        "recover_rebuild",
        Some(own),
        "r1-terminal-conflict",
    );
    assert!(error.contains(other), "{error}");
    results.push(json!({"case":"terminal-target-other-pending","error":error,"zero_writes":true}));
    fs::remove_file(path).unwrap();
    f.recover(own, "r1-repeat-after-conflict");
    assert_eq!(
        fs::read(f.root.join("state/registry.json")).unwrap(),
        registry
    );
    emit(
        "core-conflict-refusals",
        json!({"cases":results,"terminal_still_checks_others":true}),
    );
}

#[test]
fn core_cancelled_committing_preserves_pending_then_recovers() {
    let f = Fixture::new();
    let tx = "gui-rebuild-r1-cancelled";
    let path = f.committing(tx);
    let before = fs::read(&path).unwrap();
    let registry = fs::read(f.root.join("state/registry.json")).unwrap();
    let (result, snapshot) = f.core(
        &f.root,
        &f.release.id,
        "recover_rebuild",
        Some(tx),
        "r1-cancel-before-commit",
        true,
    );
    assert!(result
        .unwrap_err()
        .downcast_ref::<crate::operations::Cancelled>()
        .is_some());
    assert_eq!(
        snapshot.status,
        crate::operations::OperationStatus::Cancelled
    );
    assert_eq!(fs::read(&path).unwrap(), before);
    assert_eq!(
        fs::read(f.root.join("state/registry.json")).unwrap(),
        registry
    );
    f.recover(tx, "r1-after-cancellation");
    emit(
        "core-cancelled-recovery",
        json!({"pending_preserved":true,"registry_preserved":true,"operation":snapshot,"subsequent_recovery_succeeded":true}),
    );
}

#[test]
fn core_precancelled_creating_building_and_validating_stay_cancelled_and_preserve_pending() {
    let mut cases = Vec::new();
    for phase in ["creating", "building", "validating"] {
        let f = Fixture::new();
        let tx = format!("gui-rebuild-r1-precancel-{phase}");
        let path = f.pending(&tx);
        if phase != "creating" {
            let ctx = WorkspaceMutation::acquire_existing(&f.root, &f.release.id).unwrap();
            gui_rebuild::reliability_r0_rebuild_fixture::prepare_incomplete_phase(
                &ctx, &f.release, &tx, phase,
            )
            .unwrap();
        }
        let intent = fs::read(&path).unwrap();
        let registry = fs::read(f.root.join("state/registry.json")).unwrap();
        let (result, operation) = f.core(
            &f.root,
            &f.release.id,
            "recover_rebuild",
            Some(&tx),
            &format!("r1-precancel-{phase}"),
            true,
        );
        assert!(result
            .unwrap_err()
            .downcast_ref::<crate::operations::Cancelled>()
            .is_some());
        assert_eq!(
            operation.status,
            crate::operations::OperationStatus::Cancelled
        );
        assert_eq!(fs::read(&path).unwrap(), intent);
        assert_eq!(
            fs::read(f.root.join("state/registry.json")).unwrap(),
            registry
        );
        f.recover(&tx, &format!("r1-resume-{phase}"));
        cases.push(json!({"phase":phase,"operation":operation,"pending_preserved":true,"registry_preserved":true,"subsequent_recovery_succeeded":true}));
    }
    emit("core-incomplete-phase-cancellation", json!({"cases":cases}));
}

#[test]
fn core_midflight_cancellation_before_authority_and_after_committing_stays_recoverable() {
    let mut cases = Vec::new();
    for (checkpoint, transaction_suffix, expected_pending, complete_authority) in [
        ("prepare_candidate_observed", "prepare", "creating", false),
        ("finish_candidate_observed", "finish", "committing", true),
    ] {
        let f = Fixture::new();
        let tx = format!("gui-rebuild-r1-mid-{transaction_suffix}");
        let path = f.pending(&tx);
        let registry = fs::read(f.root.join("state/registry.json")).unwrap();
        let profiles = tree(&f.root.join("profiles"));
        let operation_id = format!("r1-midflight-{checkpoint}");
        let (result, operation, observation) = f.core_with_checkpoint(
            &f.root,
            &f.release.id,
            "recover_rebuild",
            Some(&tx),
            &operation_id,
            false,
            Some(checkpoint),
        );
        let observation = observation.unwrap();
        assert_eq!(observation["checkpoint"], checkpoint);
        assert_eq!(observation["in_memory_status"], expected_pending);
        assert_eq!(observation["candidate_state_observed"], true);
        assert_eq!(observation["candidate_tree_observed"], true);
        assert_eq!(observation["complete_commit_authority"], complete_authority);
        assert!(result
            .unwrap_err()
            .downcast_ref::<crate::operations::Cancelled>()
            .is_some());
        assert_eq!(
            operation.status,
            crate::operations::OperationStatus::Cancelled
        );
        assert!(operation.cancel_requested);
        let disk_operation: crate::operations::OperationSnapshot = serde_json::from_slice(
            &fs::read(
                f.root
                    .join("state/operations")
                    .join(format!("{operation_id}.json")),
            )
            .unwrap(),
        )
        .unwrap();
        assert_eq!(
            disk_operation.status,
            crate::operations::OperationStatus::Cancelled
        );
        assert!(disk_operation.cancel_requested);
        let pending: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        assert_eq!(pending["status"], expected_pending);
        gui_rebuild::assert_ready_except_recovery(&f.root, &f.release, &tx).unwrap();
        assert_eq!(
            fs::read(f.root.join("state/registry.json")).unwrap(),
            registry
        );
        assert_eq!(tree(&f.root.join("profiles")), profiles);
        let resumed = f.recover(&tx, &format!("r1-resumed-{checkpoint}"));
        let terminal: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        assert_eq!(terminal["status"], "orphaned");
        assert_eq!(
            fs::read(f.root.join("state/registry.json")).unwrap(),
            registry
        );
        assert_eq!(tree(&f.root.join("profiles")), profiles);
        cases.push(json!({
            "checkpoint":observation,"cancelled_operation":disk_operation,
            "pending_after_cancel":pending["status"],"pending_authority_valid":true,
            "registry_bytes_preserved":true,"profiles_tree_preserved":true,
            "resumed_operation":resumed,"terminal_status":terminal["status"],
        }));
    }
    emit(
        "core-midflight-cancellation",
        json!({
            "cases":cases,
            "fixture_scope":"legal dirty orphan recovery; no healthy proof, GUI or real training",
        }),
    );
}

#[test]
fn core_real_other_process_lease_refuses_zero_writes_then_recovers_after_release() {
    struct OwnedChild(Child);
    impl Drop for OwnedChild {
        fn drop(&mut self) {
            if self.0.try_wait().ok().flatten().is_none() {
                let _ = self.0.kill();
                let _ = self.0.wait();
            }
        }
    }
    let f = Fixture::new();
    let tx = "gui-rebuild-r1-lease";
    f.committing(tx);
    let mut command = Command::new(std::env::current_exe().unwrap());
    hidden(&mut command)
        .args([
            "--exact",
            "core::p6_tests::reliability_r0_core_probes::workspace_lease_holder",
            "--ignored",
            "--nocapture",
        ])
        .env("NEXT_TRAINER_R1_LEASE_ROOT", &f.root)
        .env("NEXT_TRAINER_R1_LEASE_RELEASE", &f.release.id)
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    let mut child = OwnedChild(command.spawn().unwrap());
    let ready = f.root.join("run/r1-lease-ready");
    let started = Instant::now();
    while !ready.is_file() {
        assert!(started.elapsed() < Duration::from_secs(10));
        thread::sleep(Duration::from_millis(10));
    }
    let pid = child.0.id();
    let error = f.reject(
        &f.root,
        &f.release.id,
        "recover_rebuild",
        Some(tx),
        "r1-lease-refused",
    );
    fs::write(f.root.join("run/r1-lease-stop"), b"stop").unwrap();
    let started = Instant::now();
    while child.0.try_wait().unwrap().is_none() {
        if started.elapsed() > Duration::from_secs(10) {
            child.0.kill().unwrap();
            panic!("lease child did not exit");
        }
        thread::sleep(Duration::from_millis(10));
    }
    assert!(child.0.wait().unwrap().success());
    fs::remove_file(ready).unwrap();
    fs::remove_file(f.root.join("run/r1-lease-stop")).unwrap();
    f.recover(tx, "r1-lease-released");
    emit(
        "core-real-lease",
        json!({"holder_pid":pid,"error":error,"refusal_zero_writes":true,"holder_exited":true,"recovery_after_release":true}),
    );
}

#[test]
#[ignore = "R1父测试限定的真实lease子进程，仅接受专属正式小夹具"]
fn workspace_lease_holder() {
    let root = PathBuf::from(std::env::var_os("NEXT_TRAINER_R1_LEASE_ROOT").unwrap());
    let release = std::env::var("NEXT_TRAINER_R1_LEASE_RELEASE").unwrap();
    assert!(root
        .file_name()
        .unwrap()
        .to_string_lossy()
        .starts_with("rp01-"));
    let ctx = WorkspaceMutation::acquire_existing(&root, &release).unwrap();
    fs::write(
        root.join("run/r1-lease-ready"),
        std::process::id().to_string(),
    )
    .unwrap();
    let started = Instant::now();
    while !root.join("run/r1-lease-stop").is_file() {
        assert!(started.elapsed() < Duration::from_secs(15));
        thread::sleep(Duration::from_millis(10));
    }
    drop(ctx);
}

#[test]
fn rollback_exact_transaction_and_full_semantics_are_required_even_for_terminal() {
    // 仅构造必须拒绝的非授信控制记录，绝不将其当作健康环境或成功回退证据。
    #[derive(Serialize)]
    struct SwitchPlan {
        schema_version: u32,
        root_absolute: PathBuf,
        release_id: String,
        history_transaction: String,
        history_identity: Identity,
        old_registry: Identity,
        current_binding: model::EnvironmentBinding,
        target_binding: model::EnvironmentBinding,
        target_state: Identity,
        proof: crate::gui_registration_integrity::TrustedEnvironment,
    }
    let f = Fixture::new();
    let binding = |id: &str| model::EnvironmentBinding {
        instance_id: id.into(),
        storage_version: 1,
        recipe_id: crate::recipe::GuiRecipe::embedded().unwrap().id().into(),
        recipe_sha256: "00ce9d78bc779f72405c84145ded75e63deca34d5b21afc51f1a78b76a0773ba".into(),
        generation: 1,
    };
    let tx = "gui-rebuild-rollback-r1-untrusted";
    let plan = SwitchPlan {
        schema_version: 1,
        root_absolute: f.root.clone(),
        release_id: f.release.id.clone(),
        history_transaction: "gui-rebuild-r1-missing-history".into(),
        history_identity: identity(b""),
        old_registry: identity(&fs::read(f.root.join("state/registry.json")).unwrap()),
        current_binding: binding("g1111111111111111"),
        target_binding: binding("g2222222222222222"),
        target_state: identity(b""),
        proof: crate::gui_registration_integrity::TrustedEnvironment {
            environment: f.root.join("e/g2222222222222222"),
            recipe_sha256: "00ce9d78bc779f72405c84145ded75e63deca34d5b21afc51f1a78b76a0773ba"
                .into(),
            trusted_index_sha256: crate::gui_registration_integrity::trusted_index_sha256().into(),
            files: 0,
            bytes: 0,
            closure_sha256: "0".repeat(64),
        },
    };
    let mut intent = json!({"schema_version":1,"root_absolute":f.root,"release_id":f.release.id,"transaction":tx,"status":"committing","plan":serde_json::to_value(&plan).unwrap(),"plan_sha256":sha(&serde_json::to_vec(&plan).unwrap()),"new_registry":identity(b"")});
    let path = f
        .root
        .join("state/gui-binding-switch")
        .join(format!("{}.json", f.release.id));
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(&path, serde_json::to_vec(&intent).unwrap()).unwrap();
    let wrong = f.reject(
        &f.root,
        &f.release.id,
        "recover_rollback",
        Some("gui-rebuild-rollback-r1-wrong"),
        "r1-rollback-wrong-tx",
    );
    let pending = f.reject(
        &f.root,
        &f.release.id,
        "recover_rollback",
        Some(tx),
        "r1-rollback-bad-history",
    );
    intent["status"] = json!("committed");
    fs::write(&path, serde_json::to_vec(&intent).unwrap()).unwrap();
    let terminal = f.reject(
        &f.root,
        &f.release.id,
        "recover_rollback",
        Some(tx),
        "r1-rollback-terminal-history",
    );
    assert!(
        terminal.contains("终态与当前 registry 不一致"),
        "{terminal}"
    );
    emit(
        "core-rollback-semantic-refusals",
        json!({"untrusted_negative_fixture":true,"wrong_tx_error":wrong,"pending_history_error":pending,"terminal_history_error":terminal,"all_zero_writes":true,"rollback_success_claimed":false}),
    );
}

#[test]
fn core_completed_rollback_recovers_idempotently_only_with_its_new_registry() {
    // 终态控制语义小夹具：不执行安装、运行验证或回退提交，不声称合成闭包为健康证明。
    #[derive(Serialize)]
    struct HistoryPlan {
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
    struct SwitchPlan {
        schema_version: u32,
        root_absolute: PathBuf,
        release_id: String,
        history_transaction: String,
        history_identity: Identity,
        old_registry: Identity,
        current_binding: model::EnvironmentBinding,
        target_binding: model::EnvironmentBinding,
        target_state: Identity,
        proof: crate::gui_registration_integrity::TrustedEnvironment,
    }
    let f = Fixture::new();
    let ctx = WorkspaceMutation::acquire_existing(&f.root, &f.release.id).unwrap();
    let recipe = crate::recipe::GuiRecipe::embedded().unwrap();
    let recipe_sha = "00ce9d78bc779f72405c84145ded75e63deca34d5b21afc51f1a78b76a0773ba";
    let cancel = crate::operations::CancelToken::new();
    let create = |id| {
        let state =
            instances::create_controlled(&ctx, id, recipe.id(), recipe_sha, &cancel).unwrap();
        instances::validate_new_controlled(&ctx, &state, &[], &cancel, |_| Ok(())).unwrap()
    };
    let binding = |state: &instances::InstanceState| model::EnvironmentBinding {
        instance_id: state.id().into(),
        storage_version: state.storage_version(),
        recipe_id: state.recipe_id().into(),
        recipe_sha256: state.recipe_sha256().into(),
        generation: state.generation(),
    };
    let target = create("g1111111111111111");
    let mut desired = Registry {
        schema_version: 2,
        ..Registry::default()
    };
    desired.record_installed(&f.release).unwrap();
    desired.bind_gui(&f.release.id, binding(&target)).unwrap();
    desired.store(&f.root).unwrap();
    let boundary = instances::rebuild_observe_boundary(ctx.layout(), &cancel).unwrap();
    let candidate = create("g2222222222222222");
    let mut current = desired.clone();
    current
        .bind_gui(&f.release.id, binding(&candidate))
        .unwrap();
    let desired_bytes = serde_json::to_vec_pretty(&desired).unwrap();
    let current_bytes = serde_json::to_vec_pretty(&current).unwrap();
    let boundary_sha = instances::rebuild_boundary_sha(&boundary).unwrap();
    let history_tx = "gui-rebuild-r1-rb-history";
    let history_plan = HistoryPlan {
        schema_version: 1,
        root_absolute: f.root.clone(),
        release_id: f.release.id.clone(),
        registry: identity(&desired_bytes),
        boundary_sha256: boundary_sha.clone(),
        old_binding: Some(binding(&target)),
        missing_wheels: vec![],
        estimated_network_bytes: 0,
    };
    // 与正式prepare_commit使用同一实例保护侧录工序；终态控制夹具也必须有完整授权闭包。
    // 不经过安装或独立可信环境核验，因此以下记录只证明恢复入口的终态语义。
    let preservation =
        instances::rebuild_preservation(&ctx, history_tx, &boundary, candidate.id(), &cancel)
            .unwrap();
    let mut preservation_bytes = serde_json::to_vec_pretty(&preservation).unwrap();
    preservation_bytes.push(b'\n');
    let preservation_sha = sha(&preservation_bytes);
    let preservation_file = format!("preservation-{preservation_sha}.json");
    let candidate_state_bytes = fs::read(
        f.root
            .join("state/instances")
            .join(format!("{}.json", candidate.id())),
    )
    .unwrap();
    let candidate_tree_sha =
        instances::rebuild_candidate_tree_sha(ctx.layout(), candidate.id()).unwrap();
    assert_eq!(
        preservation["candidate_state"],
        serde_json::to_value(identity(&candidate_state_bytes)).unwrap()
    );
    let proof = |environment| crate::gui_registration_integrity::TrustedEnvironment {
        environment,
        recipe_sha256: recipe_sha.into(),
        trusted_index_sha256: crate::gui_registration_integrity::trusted_index_sha256().into(),
        files: 0,
        bytes: 0,
        closure_sha256: "a".repeat(64),
    };
    let history = json!({"schema_version":1,"transaction":history_tx,"root_absolute":f.root,
        "release_id":f.release.id,"candidate_id":candidate.id(),"status":"committed",
        "plan":serde_json::to_value(&history_plan).unwrap(),
        "plan_sha256":sha(&serde_json::to_vec(&history_plan).unwrap()),
        "boundary_sha256":boundary_sha,"old_registry":identity(&desired_bytes),
        "candidate_state":identity(&candidate_state_bytes),"candidate_tree_sha256":candidate_tree_sha,
        "proof":proof(instances::path(&candidate).unwrap()),
        "new_registry":identity(&current_bytes),"preservation_file":preservation_file,
        "preservation_sha256":preservation_sha,"terminal_status":"committed","failure":null});
    for (name, bytes) in [
        ("registry-old.json", desired_bytes.clone()),
        ("registry-new.json", current_bytes.clone()),
        ("boundary.json", serde_json::to_vec(&boundary).unwrap()),
    ] {
        model::write_gui_transaction_bytes(
            &f.root,
            history_tx,
            &f.root.join("backups").join(history_tx).join(name),
            &bytes,
        )
        .unwrap();
    }
    model::write_gui_transaction_bytes(
        &f.root,
        history_tx,
        &f.root
            .join("backups")
            .join(history_tx)
            .join(&preservation_file),
        &preservation_bytes,
    )
    .unwrap();
    let history_path = f
        .root
        .join("state/gui-rebuild")
        .join(format!("{history_tx}.json"));
    model::write_gui_transaction_json(&f.root, history_tx, &history_path, &history).unwrap();
    let history_bytes =
        gui_rebuild::verified_history(ctx.layout(), &f.release, history_tx).unwrap();
    let tx = "gui-rebuild-rollback-r1-done";
    let plan = SwitchPlan {
        schema_version: 1,
        root_absolute: f.root.clone(),
        release_id: f.release.id.clone(),
        history_transaction: history_tx.into(),
        history_identity: identity(&history_bytes),
        old_registry: identity(&current_bytes),
        current_binding: binding(&candidate),
        target_binding: binding(&target),
        target_state: identity(
            &fs::read(
                f.root
                    .join("state/instances")
                    .join(format!("{}.json", target.id())),
            )
            .unwrap(),
        ),
        proof: proof(instances::path(&target).unwrap()),
    };
    for (name, bytes) in [
        ("registry-old.json", current_bytes.clone()),
        ("registry-new.json", desired_bytes.clone()),
    ] {
        model::write_gui_transaction_bytes(
            &f.root,
            tx,
            &f.root.join("backups").join(tx).join(name),
            &bytes,
        )
        .unwrap();
    }
    let intent_path = f
        .root
        .join("state/gui-binding-switch")
        .join(format!("{}.json", f.release.id));
    let intent = json!({"schema_version":1,"root_absolute":f.root,"release_id":f.release.id,
        "transaction":tx,"status":"committed","plan":serde_json::to_value(&plan).unwrap(),
        "plan_sha256":sha(&serde_json::to_vec(&plan).unwrap()),"new_registry":identity(&desired_bytes)});
    model::write_gui_transaction_json(&f.root, tx, &intent_path, &intent).unwrap();
    model::write_gui_transaction_bytes(
        &f.root,
        tx,
        &f.root.join("state/registry.json"),
        &desired_bytes,
    )
    .unwrap();
    drop(ctx);
    let stable_tree = || {
        tree(&f.root)
            .into_iter()
            .filter(|(path, _)| !path.starts_with("state/operations"))
            .collect::<BTreeMap<_, _>>()
    };
    let before = stable_tree();
    let mut successes = Vec::new();
    for operation_id in ["r1-rb-terminal-first", "r1-rb-terminal-repeat"] {
        let (result, snapshot) = f.core(
            &f.root,
            &f.release.id,
            "recover_rollback",
            Some(tx),
            operation_id,
            false,
        );
        result.unwrap();
        assert_eq!(
            snapshot.status,
            crate::operations::OperationStatus::Succeeded
        );
        let disk: crate::operations::OperationSnapshot = serde_json::from_slice(
            &fs::read(
                f.root
                    .join("state/operations")
                    .join(format!("{operation_id}.json")),
            )
            .unwrap(),
        )
        .unwrap();
        assert_eq!(disk.status, snapshot.status);
        assert_eq!(stable_tree(), before, "终态恢复只能新增自身操作记录");
        assert_eq!(Registry::load(&f.root).unwrap(), desired);
        successes.push(json!({"memory":snapshot,"disk":disk}));
    }
    // 同一完整终态记录，只有当前registry回到old；必须拒绝，不能再误报rolled_back。
    model::write_gui_transaction_bytes(
        &f.root,
        tx,
        &f.root.join("state/registry.json"),
        &current_bytes,
    )
    .unwrap();
    let old_error = f.reject(
        &f.root,
        &f.release.id,
        "recover_rollback",
        Some(tx),
        "r1-rb-terminal-old-refused",
    );
    assert!(
        old_error.contains("终态与当前 registry 不一致"),
        "{old_error}"
    );
    emit(
        "core-completed-rollback-idempotence",
        json!({"entry":"Engine::gui_lifecycle_operation","transaction":tx,
            "successes":successes,"new_registry_repeat_idempotent":true,
            "old_registry_error":old_error,"old_registry_refusal_zero_writes":true,
            "profiles_and_other_instances_preserved":true,
            "scope":"complete terminal control-semantics fixture; no trusted environment/runtime or committing recovery claim",
            "healthy_environment_claimed":false,"committing_recovery_claimed":false}),
    );
}
