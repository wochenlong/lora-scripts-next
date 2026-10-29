use super::super::{add_record, encoded, hash, intent_path, load_intent, Candidate, Plan, Record};
use super::*;
use crate::{
    gui_registration_integrity::TrustedEnvironment,
    model::{Catalog, WorkspaceMutation},
    recipe::GuiRecipe,
};
use std::{
    fs,
    sync::atomic::{AtomicU64, Ordering},
};
static NEXT_TEST: AtomicU64 = AtomicU64::new(0);
struct Fixture {
    root: PathBuf,
    release: Release,
    ctx: WorkspaceMutation,
}
impl Fixture {
    fn new() -> Self {
        let root = std::env::temp_dir().join(format!(
            "nt-registration-records-{}-{}-{}",
            std::process::id(),
            model::now(),
            NEXT_TEST.fetch_add(1, Ordering::Relaxed)
        ));
        let release = Catalog::embedded()
            .unwrap()
            .releases()
            .iter()
            .find(|r| r.commit == GuiRecipe::embedded().unwrap().source_commit)
            .unwrap()
            .clone();
        let ctx = WorkspaceMutation::acquire(&root, &release.id).unwrap();
        Self { root, release, ctx }
    }
    fn layout(&self) -> &Layout {
        self.ctx.layout()
    }
    fn intent(&self) -> Intent {
        let plan = Plan {
            schema_version: 1,
            release_id: self.release.id.clone(),
            root_absolute: self.root.clone(),
            registry: None,
            receipt: None,
            candidate: Candidate {
                id: "g1111111111111111".into(),
                storage_version: 1,
                state: None,
                generation: 0,
                status: "missing_state".into(),
            },
            proof: TrustedEnvironment {
                environment: self.root.join("e/g1111111111111111"),
                recipe_sha256: super::super::RECIPE_SHA.into(),
                trusted_index_sha256: "a".repeat(64),
                files: 0,
                bytes: 0,
                closure_sha256: "b".repeat(64),
            },
        };
        Intent {
            schema_version: 1,
            transaction: format!(
                "gui-registration-test-{}",
                NEXT_TEST.fetch_add(1, Ordering::Relaxed)
            ),
            release_id: self.release.id.clone(),
            root_absolute: self.root.clone(),
            status: "committing".into(),
            plan_sha256: hash(&serde_json::to_vec(&plan).unwrap()),
            plan,
            records: vec![],
        }
    }
    fn record(&self, intent: &mut Intent, relative: &str, old: Option<&[u8]>, new: &[u8]) {
        let target = self.root.join(relative);
        if let Some(old) = old {
            fs::create_dir_all(target.parent().unwrap()).unwrap();
            fs::write(&target, old).unwrap();
        }
        add_record(
            self.layout(),
            &intent.transaction,
            &mut intent.records,
            relative.into(),
            old.map(Vec::from),
            new.into(),
        )
        .unwrap();
    }
    fn allowed(intent: &Intent) -> BTreeSet<PathBuf> {
        intent.records.iter().map(|r| r.relative.clone()).collect()
    }
    fn candidate(&self, intent: &Intent) -> instances::InstanceState {
        fs::create_dir_all(&intent.plan.proof.environment).unwrap();
        instances::registration_candidate(
            &self.ctx,
            &intent.plan.candidate.id,
            1,
            &intent.transaction,
            GuiRecipe::embedded().unwrap().id(),
            super::super::RECIPE_SHA,
            0,
            &intent.plan.proof,
            &CancelToken::new(),
        )
        .unwrap()
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        if self.root.parent() == Some(std::env::temp_dir().as_path())
            && self
                .root
                .file_name()
                .unwrap()
                .to_string_lossy()
                .starts_with("nt-registration-records-")
        {
            let _ = fs::remove_dir_all(&self.root);
        }
    }
}

#[test]
fn last_unknown_third_state_refuses_all_writes_and_preserves_evidence() {
    let f = Fixture::new();
    let mut intent = f.intent();
    f.record(
        &mut intent,
        "state/registry.json",
        Some(b"old-registry"),
        b"new-registry",
    );
    f.record(
        &mut intent,
        "state/instances/g1111111111111111.json",
        Some(b"old-state"),
        b"new-state",
    );
    fs::write(
        f.root.join("state/instances/g1111111111111111.json"),
        b"third-state",
    )
    .unwrap();
    assert!(commit(
        f.layout(),
        &intent,
        &Fixture::allowed(&intent),
        &CancelToken::new()
    )
    .is_err());
    assert_eq!(
        fs::read(f.root.join("state/registry.json")).unwrap(),
        b"old-registry"
    );
    assert_eq!(
        fs::read(f.root.join("state/instances/g1111111111111111.json")).unwrap(),
        b"third-state"
    );
    assert!(f
        .root
        .join("backups")
        .join(&intent.transaction)
        .join("record-1-new.bin")
        .is_file());
}
#[test]
fn mixed_old_new_and_missing_records_resume_idempotently() {
    let f = Fixture::new();
    let mut intent = f.intent();
    f.record(
        &mut intent,
        "state/registry.json",
        Some(b"old-registry"),
        b"new-registry",
    );
    f.record(
        &mut intent,
        "state/instances/g1111111111111111.json",
        None,
        b"new-state",
    );
    let receipt = f
        .layout()
        .release_dir
        .join("release.json")
        .strip_prefix(&f.root)
        .unwrap()
        .to_string_lossy()
        .replace('\\', "/");
    f.record(&mut intent, &receipt, None, b"new-receipt");
    fs::write(f.root.join("state/registry.json"), b"new-registry").unwrap();
    commit(
        f.layout(),
        &intent,
        &Fixture::allowed(&intent),
        &CancelToken::new(),
    )
    .unwrap();
    commit(
        f.layout(),
        &intent,
        &Fixture::allowed(&intent),
        &CancelToken::new(),
    )
    .unwrap();
    assert_eq!(
        fs::read(f.root.join("state/instances/g1111111111111111.json")).unwrap(),
        b"new-state"
    );
    assert_eq!(fs::read(f.root.join(receipt)).unwrap(), b"new-receipt");
}
#[test]
fn altered_last_snapshot_refuses_first_write() {
    let f = Fixture::new();
    let mut intent = f.intent();
    f.record(
        &mut intent,
        "state/registry.json",
        Some(b"old-registry"),
        b"new-registry",
    );
    f.record(
        &mut intent,
        "state/instances/g1111111111111111.json",
        None,
        b"new-state",
    );
    fs::write(
        f.root
            .join("backups")
            .join(&intent.transaction)
            .join("record-1-new.bin"),
        b"tampered",
    )
    .unwrap();
    assert!(commit(
        f.layout(),
        &intent,
        &Fixture::allowed(&intent),
        &CancelToken::new()
    )
    .is_err());
    assert_eq!(
        fs::read(f.root.join("state/registry.json")).unwrap(),
        b"old-registry"
    );
    assert!(!f
        .root
        .join("state/instances/g1111111111111111.json")
        .exists());
}
#[test]
fn duplicate_or_unauthorized_target_never_writes() {
    let f = Fixture::new();
    let mut intent = f.intent();
    f.record(&mut intent, "state/registry.json", Some(b"old"), b"new");
    let allowed = Fixture::allowed(&intent);
    intent.records.push(intent.records[0].clone());
    assert!(commit(f.layout(), &intent, &allowed, &CancelToken::new()).is_err());
    intent.records.pop();
    intent.records[0].relative = "profiles/default/profile.json".into();
    assert!(commit(f.layout(), &intent, &allowed, &CancelToken::new()).is_err());
    assert_eq!(
        fs::read(f.root.join("state/registry.json")).unwrap(),
        b"old"
    );
}
#[test]
fn unknown_intent_schema_and_changed_plan_digest_are_rejected() {
    let f = Fixture::new();
    let mut intent = f.intent();
    f.record(&mut intent, "state/registry.json", None, b"new");
    intent.schema_version = 999;
    model::write_gui_transaction_json(
        &f.root,
        &intent.transaction,
        &intent_path(f.layout()).unwrap(),
        &intent,
    )
    .unwrap();
    assert!(load_intent(f.layout()).is_err());
    intent.schema_version = 1;
    intent.plan.candidate.generation = 123;
    model::write_gui_transaction_json(
        &f.root,
        &intent.transaction,
        &intent_path(f.layout()).unwrap(),
        &intent,
    )
    .unwrap();
    assert!(load_intent(f.layout()).is_err());
}
#[test]
fn valid_hashes_do_not_authorize_current_or_health_inheritance() {
    let f = Fixture::new();
    let mut intent = f.intent();
    let state = f.candidate(&intent);
    let mut desired = Registry {
        schema_version: 2,
        ..Registry::default()
    };
    desired.record_installed(&f.release).unwrap();
    desired
        .bind_gui(
            &f.release.id,
            EnvironmentBinding {
                instance_id: state.id().into(),
                storage_version: 1,
                recipe_id: state.recipe_id().into(),
                recipe_sha256: state.recipe_sha256().into(),
                generation: state.generation(),
            },
        )
        .unwrap();
    f.record(
        &mut intent,
        "state/registry.json",
        None,
        &encoded(&desired).unwrap(),
    );
    validate_semantics(f.layout(), &f.release, &intent, &state).unwrap();
    desired.current = Some(f.release.id.clone());
    desired.installed[0].healthy_at = Some(model::now());
    let bytes = encoded(&desired).unwrap();
    let record: &mut Record = &mut intent.records[0];
    record.new = stamp(&bytes);
    fs::write(
        f.root
            .join("backups")
            .join(&intent.transaction)
            .join(&record.new_snapshot),
        bytes,
    )
    .unwrap();
    assert!(validate_semantics(f.layout(), &f.release, &intent, &state).is_err());
    assert!(!f.root.join("state/registry.json").exists());
}
#[test]
fn trusted_hash_does_not_authorize_receipt_replacement_or_wrong_release() {
    let f = Fixture::new();
    let mut intent = f.intent();
    let state = f.candidate(&intent);
    let mut registered = Registry {
        schema_version: 2,
        ..Registry::default()
    };
    registered.record_installed(&f.release).unwrap();
    registered
        .bind_gui(
            &f.release.id,
            EnvironmentBinding {
                instance_id: state.id().into(),
                storage_version: state.storage_version(),
                recipe_id: state.recipe_id().into(),
                recipe_sha256: state.recipe_sha256().into(),
                generation: state.generation(),
            },
        )
        .unwrap();
    registered.store(&f.root).unwrap();
    intent.plan.registry = Some(stamp(
        &fs::read(f.root.join("state/registry.json")).unwrap(),
    ));
    let receipt = f
        .layout()
        .release_dir
        .join("release.json")
        .strip_prefix(&f.root)
        .unwrap()
        .to_string_lossy()
        .replace('\\', "/");
    let mut wrong = f.release.clone();
    wrong.version.push_str("-wrong");
    let bytes = encoded(&ReleaseReceipt::new(&wrong)).unwrap();
    f.record(&mut intent, &receipt, None, &bytes);
    assert!(validate_semantics(f.layout(), &f.release, &intent, &state).is_err());
    let bytes = encoded(&ReleaseReceipt::new(&f.release)).unwrap();
    let record = &mut intent.records[0];
    record.new = stamp(&bytes);
    fs::write(
        f.root
            .join("backups")
            .join(&intent.transaction)
            .join(&record.new_snapshot),
        &bytes,
    )
    .unwrap();
    validate_semantics(f.layout(), &f.release, &intent, &state).unwrap();
    intent.plan.receipt = Some(stamp(b"old-receipt"));
    assert!(validate_semantics(f.layout(), &f.release, &intent, &state).is_err());
}

#[test]
fn recovery_identity_rejects_proof_a_candidate_b_before_any_execution() {
    let f = Fixture::new();
    let mut intent = f.intent();
    intent.plan.proof.trusted_index_sha256 =
        crate::gui_registration_integrity::trusted_index_sha256().into();
    intent.plan.proof.files = 1;
    intent.plan.proof.bytes = 1;
    intent.plan.proof.environment = f.root.join("e/g2222222222222222");
    assert!(validate_identity(f.layout(), &f.release, &intent)
        .unwrap_err()
        .to_string()
        .contains("断联"));
    assert!(!f.root.join("state/registry.json").exists());
}
#[test]
fn recovery_identity_rejects_unknown_plan_schema_even_with_recomputed_digest() {
    let f = Fixture::new();
    let mut intent = f.intent();
    intent.plan.schema_version = 2;
    intent.plan_sha256 = hash(&serde_json::to_vec(&intent.plan).unwrap());
    assert!(validate_identity(f.layout(), &f.release, &intent).is_err());
}
#[test]
fn new_receipt_unknown_schema_is_rejected_before_first_record_write() {
    let f = Fixture::new();
    let mut intent = f.intent();
    let state = f.candidate(&intent);
    let mut desired = Registry {
        schema_version: 2,
        ..Registry::default()
    };
    desired.record_installed(&f.release).unwrap();
    desired
        .bind_gui(
            &f.release.id,
            EnvironmentBinding {
                instance_id: state.id().into(),
                storage_version: 1,
                recipe_id: state.recipe_id().into(),
                recipe_sha256: state.recipe_sha256().into(),
                generation: state.generation(),
            },
        )
        .unwrap();
    f.record(
        &mut intent,
        "state/registry.json",
        None,
        &encoded(&desired).unwrap(),
    );
    let receipt_path = f
        .layout()
        .release_dir
        .join("release.json")
        .strip_prefix(&f.root)
        .unwrap()
        .to_string_lossy()
        .replace('\\', "/");
    let mut receipt = ReleaseReceipt::new(&f.release);
    receipt.schema_version = 999;
    f.record(
        &mut intent,
        &receipt_path,
        None,
        &encoded(&receipt).unwrap(),
    );
    assert!(validate_semantics(f.layout(), &f.release, &intent, &state).is_err());
    assert!(!f.root.join("state/registry.json").exists());
    assert!(!f.root.join(receipt_path).exists());
}

fn complete_intent(f: &Fixture) -> (Intent, instances::InstanceState) {
    let mut intent = f.intent();
    intent.plan.proof.trusted_index_sha256 =
        crate::gui_registration_integrity::trusted_index_sha256().into();
    intent.plan.proof.files = 1;
    intent.plan.proof.bytes = 1;
    let state = f.candidate(&intent);
    let state_path = format!("state/instances/{}.json", state.id());
    f.record(
        &mut intent,
        &state_path,
        None,
        &instances::registration_encoded(f.layout(), &state).unwrap(),
    );
    let mut desired = Registry {
        schema_version: 2,
        ..Registry::default()
    };
    desired.record_installed(&f.release).unwrap();
    desired
        .bind_gui(
            &f.release.id,
            EnvironmentBinding {
                instance_id: state.id().into(),
                storage_version: 1,
                recipe_id: state.recipe_id().into(),
                recipe_sha256: state.recipe_sha256().into(),
                generation: state.generation(),
            },
        )
        .unwrap();
    f.record(
        &mut intent,
        "state/registry.json",
        None,
        &encoded(&desired).unwrap(),
    );
    let receipt_path = f
        .layout()
        .release_dir
        .join("release.json")
        .strip_prefix(&f.root)
        .unwrap()
        .to_string_lossy()
        .replace('\\', "/");
    f.record(
        &mut intent,
        &receipt_path,
        None,
        &encoded(&ReleaseReceipt::new(&f.release)).unwrap(),
    );
    (intent, state)
}
#[test]
fn complete_recovery_identity_accepts_exact_missing_old_new_windows() {
    let f = Fixture::new();
    let (intent, _) = complete_intent(&f);
    validate_identity(f.layout(), &f.release, &intent).unwrap();
    let registry = intent
        .records
        .iter()
        .find(|r| r.relative == Path::new("state/registry.json"))
        .unwrap();
    let bytes =
        super::super::saved(f.layout(), &intent, &registry.new_snapshot, &registry.new).unwrap();
    fs::write(f.root.join("state/registry.json"), bytes).unwrap();
    validate_identity(f.layout(), &f.release, &intent).unwrap();
}
#[test]
fn missing_registry_record_cannot_leave_state_or_receipt_partially_written() {
    let f = Fixture::new();
    let (mut intent, _) = complete_intent(&f);
    intent
        .records
        .retain(|r| r.relative != Path::new("state/registry.json"));
    assert!(validate_identity(f.layout(), &f.release, &intent)
        .unwrap_err()
        .to_string()
        .contains("遗漏"));
    assert!(!f.root.join("state/registry.json").exists());
    assert!(!f
        .root
        .join("state/instances/g1111111111111111.json")
        .exists());
    assert!(!f.layout().release_dir.join("release.json").exists());
}

#[test]
fn same_path_different_existing_state_bytes_are_rejected() {
    let f = Fixture::new();
    let (mut intent, state) = complete_intent(&f);
    let state_path = Path::new("state/instances").join(format!("{}.json", state.id()));
    let state_bytes = instances::registration_encoded(f.layout(), &state).unwrap();
    fs::create_dir_all(f.root.join(&state_path).parent().unwrap()).unwrap();
    fs::write(f.root.join(&state_path), &state_bytes).unwrap();
    intent.records.retain(|r| r.relative != state_path);
    intent.plan.candidate.state = Some(stamp(&state_bytes));
    intent.plan.candidate.status = "clean".into();
    intent.plan.candidate.generation = state.generation();
    validate_identity(f.layout(), &f.release, &intent).unwrap();
    let mut changed = state_bytes;
    changed.push(b' ');
    fs::write(f.root.join(state_path), changed).unwrap();
    assert!(validate_identity(f.layout(), &f.release, &intent)
        .unwrap_err()
        .to_string()
        .contains("身份变化"));
}
#[test]
fn consistent_snapshot_hashes_cannot_switch_an_existing_binding_to_other_candidate() {
    let f = Fixture::new();
    let (mut intent, state) = complete_intent(&f);
    let mut old = Registry {
        schema_version: 2,
        ..Registry::default()
    };
    old.record_installed(&f.release).unwrap();
    old.bind_gui(
        &f.release.id,
        EnvironmentBinding {
            instance_id: "g2222222222222222".into(),
            storage_version: 1,
            recipe_id: state.recipe_id().into(),
            recipe_sha256: state.recipe_sha256().into(),
            generation: 1,
        },
    )
    .unwrap();
    let old_bytes = encoded(&old).unwrap();
    let old_stamp = stamp(&old_bytes);
    let record = intent
        .records
        .iter_mut()
        .find(|r| r.relative == Path::new("state/registry.json"))
        .unwrap();
    record.old = Some(old_stamp.clone());
    record.old_snapshot = Some("bound-old-registry.bin".into());
    fs::write(
        f.root
            .join("backups")
            .join(&intent.transaction)
            .join("bound-old-registry.bin"),
        &old_bytes,
    )
    .unwrap();
    fs::write(f.root.join("state/registry.json"), old_bytes).unwrap();
    intent.plan.registry = Some(old_stamp);
    assert!(validate_identity(f.layout(), &f.release, &intent)
        .unwrap_err()
        .to_string()
        .contains("既有binding"));
    assert!(Registry::load(&f.root)
        .unwrap()
        .gui_binding(&f.release.id)
        .is_some_and(|b| b.instance_id == "g2222222222222222"));
}
