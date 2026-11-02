//! CR-020 R0 小夹具直接调用生产保护扫描/引擎所有权校验，不读取真实训练环境。
use super::*;
use serde_json::{json, Value};

struct Fixture {
    root: PathBuf,
    parent: PathBuf,
    ctx: Option<WorkspaceMutation>,
    release: Release,
}
impl Fixture {
    fn new() -> Self {
        let parent = PathBuf::from(std::env::var_os("NEXT_TRAINER_RELIABILITY_FIXTURES").unwrap());
        let root = parent.join(format!(
            "rp05-{}-{}-{}",
            std::process::id(),
            super::super::stamp(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let release = model::Catalog::embedded().unwrap().releases()[0].clone();
        let ctx = WorkspaceMutation::acquire(&root, &release.id).unwrap();
        ctx.layout().ensure_dir(&ctx.layout().environment).unwrap();
        fs::write(
            ctx.layout().environment.join("small.dll"),
            b"complete protected content",
        )
        .unwrap();
        Self {
            root,
            parent,
            ctx: Some(ctx),
            release,
        }
    }
    fn layout(&self) -> &Layout {
        self.ctx.as_ref().unwrap().layout()
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        self.ctx.take();
        let root = self.root.canonicalize().unwrap();
        let parent = self.parent.canonicalize().unwrap();
        assert_eq!(root.parent(), Some(parent.as_path()));
        assert!(self
            .root
            .file_name()
            .unwrap()
            .to_string_lossy()
            .starts_with("rp05-"));
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
fn production_capture_hashes_complete_content_and_detects_extra_same_size_mtime_and_junction() {
    let f = Fixture::new();
    let layout = f.layout();
    let path = layout.environment.join("small.dll");
    let original = fs::read(&path).unwrap();
    let before = capture(layout, None).unwrap();
    let relative = path.strip_prefix(&f.root).unwrap().to_path_buf();
    assert_eq!(
        before.entries[&relative],
        Node::File {
            bytes: original.len() as u64,
            sha256: sha(&original)
        }
    );
    let mtime = fs::metadata(&path).unwrap().modified().unwrap();
    let mut changed = original.clone();
    *changed.last_mut().unwrap() ^= 1; // 尾字节变化，证明不是只抽头部或仅元数据。
    fs::write(&path, &changed).unwrap();
    File::options()
        .write(true)
        .open(&path)
        .unwrap()
        .set_times(fs::FileTimes::new().set_modified(mtime))
        .unwrap();
    assert_eq!(fs::metadata(&path).unwrap().modified().unwrap(), mtime);
    let changed_protection = capture(layout, None).unwrap();
    assert_ne!(changed_protection, before);
    assert_eq!(
        changed_protection.entries[&relative],
        Node::File {
            bytes: changed.len() as u64,
            sha256: sha(&changed)
        }
    );
    fs::write(&path, &original).unwrap();
    assert_eq!(capture(layout, None).unwrap(), before);
    let extra = layout.environment.join("extra-unlisted.txt");
    fs::write(&extra, b"extra file").unwrap();
    assert_ne!(capture(layout, None).unwrap(), before);
    fs::remove_file(&extra).unwrap();
    assert_eq!(capture(layout, None).unwrap(), before);

    let outside = f.root.join("link-target");
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join("keep.txt"), b"outside unchanged").unwrap();
    let link = layout.environment.join("untrusted-junction");
    junction::create(&outside, &link).unwrap();
    let junction_error = format!("{:#}", capture(layout, None).unwrap_err());
    assert!(
        junction_error.contains("重解析") || junction_error.contains("符号链接"),
        "{junction_error}"
    );
    junction::delete(&link).unwrap();
    // junction::delete 仅移除重解析信息，Windows 上仍留下空挂载目录。
    use std::os::windows::fs::MetadataExt;
    assert_eq!(
        fs::symlink_metadata(&link).unwrap().file_attributes() & 0x400,
        0
    );
    fs::remove_dir(&link).unwrap();
    assert_eq!(
        fs::read(outside.join("keep.txt")).unwrap(),
        b"outside unchanged"
    );
    assert_eq!(capture(layout, None).unwrap(), before);
    emit(
        "production-content-protection",
        json!({
            "classification": "existing_protection_behavior", "production_capture_called": true,
            "complete_file_sha256": sha(&original), "tail_byte_changed_sha256": sha(&changed),
            "same_length": original.len() == changed.len(), "mtime_restored": true,
            "same_size_mtime_change_detected": true, "extra_file_detected": true,
            "junction_rejected": true, "junction_error": junction_error, "junction_target_unchanged": true,
            "restored_protection_equals_before": true, "fixture_root": f.root,
        }),
    );
}

#[test]
#[ignore = "CR-020 R0 专属小夹具/证据根，由限时探针脚本显式调用"]
fn production_engine_control_digest_rejects_receipt_owner_changes_and_exposes_capture_gap() {
    let f = Fixture::new();
    let layout = f.layout();
    let id = "t0123456789abcde";
    let engine = "kohya";
    let lock_raw = crate::core::embedded_engine_lock(engine).unwrap();
    let lock: Value = serde_json::from_slice(lock_raw).unwrap();
    let lock_sha = sha(lock_raw);
    let mut python_files = lock["python"]["files"].as_object().unwrap().clone();
    python_files.retain(|name, _| {
        !name.ends_with(".pyc") && !name.split(['/', '\\']).any(|part| part == "__pycache__")
    });
    let receipt = json!({
        "schema_version": 1, "release_id": f.release.id, "engine_id": engine,
        "instance_id": id, "generation": 1, "recipe_sha256": lock["recipe_sha256"],
        "lock_sha256": lock_sha, "files": {"source": lock["source"]["files"], "environment": {}},
        "base_python_files": python_files,
    });
    let receipt_bytes = serde_json::to_vec(&receipt).unwrap();
    let owner = f
        .root
        .join("state/engines")
        .join(&f.release.id)
        .join(engine);
    let receipt_path = owner.join("instances").join(id).join("1.json");
    layout.ensure_dir(receipt_path.parent().unwrap()).unwrap();
    layout.ensure_dir(&f.root.join("e").join(id)).unwrap();
    fs::write(
        f.root.join("e").join(id).join("engine.dll"),
        b"tiny engine payload",
    )
    .unwrap();
    fs::write(&receipt_path, &receipt_bytes).unwrap();
    let state = json!({
        "schema_version": 1, "release_id": f.release.id, "engine_id": engine, "instance_id": id,
        "recipe_sha256": lock["recipe_sha256"], "lock_sha256": lock_sha,
        "python_version": lock["python"]["version"], "environment_root": f.root.join("e").join(id),
        "source_root": f.root.join("s").join(id), "python_root": f.root.join("p").join(id),
        "generation": 1, "validated_generation": 1, "dirty": false,
        "status": "ready", "pending": null, "receipt_relative": format!("instances/{id}/1.json"),
        "receipt_sha256": sha(&receipt_bytes),
    });
    let state_bytes = serde_json::to_vec(&state).unwrap();
    fs::write(owner.join("state.json"), &state_bytes).unwrap();
    let baseline_digest = crate::instances::engine_control_digest(layout).unwrap();
    let baseline_capture = capture(layout, None).unwrap();
    let mut errors = Vec::new();
    for (field, bad_value) in [
        ("instance_id", json!("t111111111111111")),
        ("release_id", json!("dev-wrong")),
        ("generation", json!(2)),
        ("engine_id", json!("diffsynth")),
    ] {
        let mut bad = receipt.clone();
        bad[field] = bad_value;
        fs::write(&receipt_path, serde_json::to_vec(&bad).unwrap()).unwrap();
        let error = format!(
            "{:#}",
            crate::instances::engine_control_digest(layout).unwrap_err()
        );
        assert!(error.contains("receipt"), "{field}: {error}");
        // 当前源码 capture 不含 state/engines；该缺口须由正式组合保护在后续接入弥补。
        assert_eq!(capture(layout, None).unwrap(), baseline_capture);
        errors
            .push(json!({"field": field, "error": error, "source_capture_alone_unchanged": true}));
    }
    fs::write(&receipt_path, &receipt_bytes).unwrap();
    assert_eq!(
        crate::instances::engine_control_digest(layout).unwrap(),
        baseline_digest
    );
    let mut wrong_state = state.clone();
    wrong_state["environment_root"] = json!(f.root.join("e").join("t111111111111111"));
    fs::write(
        owner.join("state.json"),
        serde_json::to_vec(&wrong_state).unwrap(),
    )
    .unwrap();
    let state_error = format!(
        "{:#}",
        crate::instances::engine_control_digest(layout).unwrap_err()
    );
    assert!(state_error.contains("所有权"), "{state_error}");
    fs::write(owner.join("state.json"), &state_bytes).unwrap();
    assert_eq!(
        crate::instances::engine_control_digest(layout).unwrap(),
        baseline_digest
    );
    emit(
        "production-receipt-ownership",
        json!({
            "classification": "existing_guard_plus_integration_gap", "entry": "instances::engine_control_digest",
            "valid_fixture_accepted": true, "baseline_digest": baseline_digest, "receipt_mutations": errors,
            "state_owner_change_rejected": true, "state_owner_error": state_error,
            "source_capture_alone_protects_engine_control_records": false,
            "required_followup": "combine bounded owner/receipt digest with non-target file protection before excluding engine payload",
            "restored_digest_equals_before": true, "fixture_root": f.root,
        }),
    );
}
