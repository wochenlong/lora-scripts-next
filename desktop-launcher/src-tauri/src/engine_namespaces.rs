//! GUI仅验证引擎命名空间所有权和有界控制记录，不扫描或授信Torch环境内容。
use crate::model::{self, Layout};
use anyhow::{bail, Context, Result};
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Path, PathBuf},
};
const MAX_RECORD: u64 = 32 * 1024 * 1024;
const MAX_TOTAL: u64 = 128 * 1024 * 1024;
const MAX_INSTANCES: usize = 128;
const ENGINES: &[&str] = &["kohya", "anima-fast", "ai-toolkit", "diffsynth"];
#[derive(Serialize)]
pub(super) struct Snapshot {
    pub(super) excluded: BTreeSet<PathBuf>,
    controls: BTreeMap<PathBuf, String>,
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn short_id(id: &str) -> bool {
    id.len() == 16
        && id.starts_with('t')
        && id[1..]
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn read(
    layout: &Layout,
    path: &Path,
    total: &mut u64,
    records: &mut BTreeMap<PathBuf, String>,
) -> Result<Value> {
    layout.guard_path(path)?;
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_file() || metadata.len() > MAX_RECORD {
        bail!("引擎所有权记录不是限额普通文件");
    }
    *total = total
        .checked_add(metadata.len())
        .context("引擎控制预算溢出")?;
    if *total > MAX_TOTAL {
        bail!("引擎控制记录超过128MiB预算");
    }
    let bytes = fs::read(path)?;
    if bytes.len() as u64 != metadata.len() {
        bail!("引擎控制记录读取期间变化");
    }
    records.insert(path.strip_prefix(&layout.root)?.into(), hash(&bytes));
    Ok(serde_json::from_slice(&bytes)?)
}
fn children(layout: &Layout, path: &Path) -> Result<Vec<PathBuf>> {
    layout.guard_path(path)?;
    if !path.exists() {
        return Ok(vec![]);
    }
    if !fs::symlink_metadata(path)?.is_dir() {
        bail!("引擎命名空间必须为目录");
    }
    let mut values = Vec::new();
    for entry in fs::read_dir(path)? {
        let path = entry?.path();
        layout.guard_path(&path)?;
        values.push(path);
        if values.len() > MAX_INSTANCES {
            bail!("引擎命名空间超过128项预算");
        }
    }
    Ok(values)
}
fn state_identity(
    layout: &Layout,
    owner: &Path,
    release: &str,
    engine: &str,
    state: &Value,
    lock: &Value,
    lock_sha: &str,
) -> Result<()> {
    let id = state["instance_id"].as_str().context("引擎实例身份缺失")?;
    if !short_id(id)
        || state["schema_version"] != 1
        || state["release_id"] != release
        || state["engine_id"] != engine
        || state["recipe_sha256"] != lock["recipe_sha256"]
        || state["lock_sha256"] != lock_sha
        || state["python_version"] != lock["python"]["version"]
        || state["environment_root"] != layout.root.join("e").join(id).to_string_lossy().as_ref()
        || state["source_root"] != layout.root.join("s").join(id).to_string_lossy().as_ref()
        || state["python_root"] != layout.root.join("p").join(id).to_string_lossy().as_ref()
        || state["generation"].as_u64().is_none_or(|n| n == 0)
        || state["validated_generation"]
            .as_u64()
            .is_none_or(|n| n > state["generation"].as_u64().unwrap_or(0))
        || state["dirty"].as_bool().is_none()
    {
        bail!(
            "引擎state与编译资产锁/短路径所有权不符：{}",
            owner.display()
        );
    }
    Ok(())
}
fn receipt_identity(
    value: &Value,
    release: &str,
    engine: &str,
    id: &str,
    generation: u64,
    lock: &Value,
    lock_sha: &str,
) -> Result<()> {
    // 与 Python control._prepare_python 的收据合同一致：官方归档仍逐文件
    // 验真，但解释器会重建派生字节码，运行收据只承诺原始解释器/库文件。
    let python_files = lock["python"]["files"]
        .as_object()
        .context("编译锁缺少基础 Python 文件清单")?
        .iter()
        .filter(|(name, _)| {
            !name.ends_with(".pyc") && !name.split(['/', '\\']).any(|part| part == "__pycache__")
        })
        .map(|(name, entry)| (name.clone(), entry.clone()))
        .collect::<serde_json::Map<String, Value>>();
    if value["schema_version"] != 1
        || value["release_id"] != release
        || value["engine_id"] != engine
        || value["instance_id"] != id
        || value["generation"] != generation
        || value["recipe_sha256"] != lock["recipe_sha256"]
        || value["lock_sha256"] != lock_sha
        || value["files"]["source"] != lock["source"]["files"]
        || value["base_python_files"] != Value::Object(python_files)
        || !value["files"]["environment"].is_object()
    {
        bail!("引擎receipt未绑定编译锁/源码/Python及独立generation");
    }
    Ok(())
}
/// 未完成首次安装只证明分配t命名空间，不证明环境健康或可执行。
fn pending_owner(
    layout: &Layout,
    owner: &Path,
    state: &Value,
    lock: &Value,
    lock_sha: &str,
    total: &mut u64,
    records: &mut BTreeMap<PathBuf, String>,
) -> Result<()> {
    let pending = state["pending"]
        .as_str()
        .context("引擎缺少成功receipt及持久分配意图")?;
    let path = layout.root.join(pending);
    let operations = owner.join("operations");
    if !path.starts_with(&operations)
        || path.components().count() != operations.components().count() + 1
        || path
            .file_name()
            .and_then(|n| n.to_str())
            .is_none_or(|n| !n.starts_with("op-"))
        || state["dirty"] != true
    {
        bail!("未完成引擎命名空间缺少固定操作意图");
    }
    let mut plan = read(layout, &path.join("plan.json"), total, records)?;
    let sha = plan
        .as_object_mut()
        .context("引擎计划不是对象")?
        .remove("plan_sha256")
        .context("计划摘要缺失")?;
    let roots = serde_json::json!([
        layout
            .root
            .join("e")
            .join(state["instance_id"].as_str().unwrap()),
        layout
            .root
            .join("s")
            .join(state["instance_id"].as_str().unwrap()),
        layout
            .root
            .join("p")
            .join(state["instance_id"].as_str().unwrap()),
        owner
    ]);
    if sha != hash(&serde_json::to_vec(&plan)?)
        || plan["schema_version"] != 1
        || plan["engine_id"] != state["engine_id"]
        || plan["release_id"] != state["release_id"]
        || plan["instance_id"] != state["instance_id"]
        || plan["recipe_sha256"] != lock["recipe_sha256"]
        || plan["lock_sha256"] != lock_sha
        || plan["write_roots"] != roots
        || plan["profile_writes"] != serde_json::json!([])
        || plan["main_env_fallback"] != false
        || !matches!(plan["kind"].as_str(), Some("install" | "repair"))
    {
        bail!("引擎分配意图与固定命名空间/编译锁不符");
    }
    Ok(())
}

/// 正式重建恢复旧绑定后会保留失败新实例。这里只证明原件分配所有权，
/// 不扫描候选内容，也不将其登记为ready或授予执行资格。
/// 最小兼容只接受当前绑定仍精确等于该次old-binding的情况。
fn recovered_candidate_owner(
    layout: &Layout,
    owner: &Path,
    state: &Value,
    compiled: (&Value, &str),
    id: &str,
    total: &mut u64,
    records: &mut BTreeMap<PathBuf, String>,
) -> Result<bool> {
    let (lock, lock_sha) = compiled;
    let current = state["instance_id"]
        .as_str()
        .context("当前引擎实例身份缺失")?;
    if state["status"] != "ready"
        || state["dirty"] != false
        || state.get("pending") != Some(&Value::Null)
        || id == current
    {
        return Ok(false);
    }
    let release = state["release_id"].as_str().context("当前引擎发布缺失")?;
    let engine = state["engine_id"].as_str().context("当前引擎类型缺失")?;
    let mut found = false;
    for operation in children(layout, &owner.join("operations"))? {
        let name = operation
            .file_name()
            .and_then(|v| v.to_str())
            .context("恢复操作名称不是UTF8")?;
        if !name.strip_prefix("op-").is_some_and(|suffix| {
            suffix.len() == 32
                && suffix
                    .bytes()
                    .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
        }) || !fs::symlink_metadata(&operation)?.is_dir()
        {
            bail!("恢复候选来源含未知操作目录");
        }
        let mut plan = read(layout, &operation.join("plan.json"), total, records)?;
        if !plan.is_object() {
            bail!("恢复候选来源计划不是对象");
        }
        if plan["instance_id"] != id {
            continue;
        }
        if found {
            bail!("恢复候选被多个历史操作重复声明");
        }
        let claimed = plan
            .as_object_mut()
            .unwrap()
            .remove("plan_sha256")
            .context("恢复候选计划摘要缺失")?;
        let roots = serde_json::json!([
            layout.root.join("e").join(id),
            layout.root.join("s").join(id),
            layout.root.join("p").join(id),
            owner,
        ]);
        let profile = state["profile_id"]
            .as_str()
            .context("当前引擎资料身份缺失")?;
        model::validate_component(profile)?;
        if claimed != hash(&serde_json::to_vec(&plan)?)
            || plan["schema_version"] != 1
            || plan["kind"] != "install"
            || plan["rebuild"] != true
            || plan["release_id"] != release
            || plan["engine_id"] != engine
            || plan["profile_id"] != profile
            || plan["recipe_sha256"] != lock["recipe_sha256"]
            || plan["lock_sha256"] != lock_sha
            || plan["write_roots"] != roots
            || plan["profile_writes"] != serde_json::json!([])
            || plan["main_env_fallback"] != false
        {
            bail!("恢复候选计划与固定根/编译锁或原文摘要不符");
        }
        let old = read(layout, &operation.join("old-binding.json"), total, records)?;
        state_identity(layout, owner, release, engine, &old, lock, lock_sha)?;
        let generation = old["generation"].as_u64().context("旧绑定代次缺失")?;
        if old != *state
            || generation == 0
            || old["validated_generation"] != generation
            || plan["expected_generation"] != generation
            || plan["prior_state_sha256"] != hash(&serde_json::to_vec(&old)?)
        {
            bail!("恢复候选旧绑定未与计划和当前已恢复绑定闭合");
        }
        // 独立验证当前receipt，不依赖wanted中当前ID的先后顺序或存在性。
        let relative = format!("instances/{current}/{generation}.json");
        if state["receipt_relative"] != relative {
            bail!("恢复候选当前绑定receipt路径不符");
        }
        let receipt_path = owner.join(&relative);
        let receipt = read(layout, &receipt_path, total, records)?;
        receipt_identity(
            &receipt, release, engine, current, generation, lock, lock_sha,
        )?;
        if state["receipt_sha256"] != records[receipt_path.strip_prefix(&layout.root)?] {
            bail!("恢复候选当前绑定receipt原文摘要不符");
        }
        let recovery = read(layout, &operation.join("recovery.json"), total, records)?;
        if recovery.as_object().is_none_or(|v| v.len() != 2)
            || recovery["status"] != "restored_binding"
            || recovery["generation"] != generation
        {
            bail!("恢复候选缺少精确的旧绑定恢复记录");
        }
        for namespace in ["e", "s", "p"] {
            let path = layout.root.join(namespace).join(id);
            layout.guard_path(&path)?;
            match fs::symlink_metadata(&path) {
                Ok(meta) if meta.is_dir() => {}
                // 中断可以先于s/p创建；存在的原件仍须是精确的普通目录。
                Err(error) if error.kind() == std::io::ErrorKind::NotFound && namespace != "e" => {}
                Err(error) => return Err(error.into()),
                _ => bail!("恢复候选短路径不是普通目录"),
            }
        }
        found = true;
    }
    Ok(found)
}

pub(super) fn capture(layout: &Layout) -> Result<Snapshot> {
    let mut controls = BTreeMap::new();
    let mut total = 0;
    let mut wanted = BTreeSet::new();
    let mut aliases = BTreeSet::new();
    for path in children(layout, &layout.root.join("e"))? {
        let id = path
            .file_name()
            .and_then(|s| s.to_str())
            .context("环境路径不是UTF8")?;
        if !aliases.insert(id.to_lowercase()) {
            bail!("环境含大小写别名");
        }
        if id.to_ascii_lowercase().starts_with('t') {
            if !short_id(id) || !fs::symlink_metadata(&path)?.is_dir() {
                bail!("未知引擎环境短路径");
            }
            wanted.insert(id.to_owned());
        }
    }
    let mut owners: BTreeMap<String, PathBuf> = BTreeMap::new();
    for release_dir in children(layout, &layout.root.join("state").join("engines"))? {
        let release = release_dir
            .file_name()
            .and_then(|s| s.to_str())
            .context("引擎发布路径不是UTF8")?;
        model::validate_release_id(release)?;
        for owner in children(layout, &release_dir)? {
            let engine = owner
                .file_name()
                .and_then(|s| s.to_str())
                .context("引擎路径不是UTF8")?;
            if !ENGINES.contains(&engine) {
                bail!("未知引擎控制命名空间");
            }
            let raw = crate::core::embedded_engine_lock(engine).context("引擎未有编译资产锁")?;
            let lock: Value = serde_json::from_slice(raw)?;
            let lock_sha = hash(raw);
            let state_path = owner.join("state.json");
            if !state_path.exists() {
                continue;
            }
            let state = read(layout, &state_path, &mut total, &mut controls)?;
            state_identity(layout, &owner, release, engine, &state, &lock, &lock_sha)?;
            for id in &wanted {
                let folder = owner.join("instances").join(id);
                let mut candidates = children(layout, &folder)?;
                candidates.sort_by_key(|p| {
                    p.file_stem()
                        .and_then(|n| n.to_str())
                        .and_then(|n| n.parse::<u64>().ok())
                        .unwrap_or(0)
                });
                let current = state["instance_id"] == id.as_str();
                if let Some(path) = candidates.last() {
                    if path.extension().is_none_or(|e| e != "json") {
                        bail!("引擎receipt命名未知");
                    }
                    let generation = path
                        .file_stem()
                        .and_then(|n| n.to_str())
                        .context("receipt代次缺失")?
                        .parse::<u64>()?;
                    if generation == 0 {
                        bail!("引擎receipt代次无效");
                    }
                    let receipt = read(layout, path, &mut total, &mut controls)?;
                    receipt_identity(&receipt, release, engine, id, generation, &lock, &lock_sha)?;
                    if current && state["dirty"] == false {
                        let relative = format!("instances/{id}/{generation}.json");
                        if state["status"] != "ready"
                            || !state["pending"].is_null()
                            || state["generation"] != generation
                            || state["validated_generation"] != generation
                            || state["receipt_relative"] != relative
                            || state["receipt_sha256"]
                                != controls[path.strip_prefix(&layout.root)?]
                        {
                            bail!("引擎当前state与已验证receipt断联");
                        }
                    } else if current {
                        pending_owner(
                            layout,
                            &owner,
                            &state,
                            &lock,
                            &lock_sha,
                            &mut total,
                            &mut controls,
                        )?;
                    }
                } else if current {
                    pending_owner(
                        layout,
                        &owner,
                        &state,
                        &lock,
                        &lock_sha,
                        &mut total,
                        &mut controls,
                    )?;
                } else if !recovered_candidate_owner(
                    layout,
                    &owner,
                    &state,
                    (&lock, &lock_sha),
                    id,
                    &mut total,
                    &mut controls,
                )? {
                    continue;
                }
                if owners.insert(id.clone(), owner.clone()).is_some() {
                    bail!("引擎短ID被多个所有者同时声明");
                }
            }
        }
    }
    if owners.keys().cloned().collect::<BTreeSet<_>>() != wanted {
        bail!("未知t环境缺少匹配的编译锁/独立receipt或持久分配意图");
    }
    Ok(Snapshot {
        excluded: wanted.into_iter().map(PathBuf::from).collect(),
        controls,
    })
}
pub(super) fn digest(layout: &Layout) -> Result<String> {
    Ok(hash(&serde_json::to_vec(&capture(layout)?)?))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT: AtomicU64 = AtomicU64::new(0);
    const CURRENT: &str = "t111111111111111";
    const CANDIDATE: &str = "t222222222222222";

    struct RecoveredFixture {
        layout: Layout,
        owner: PathBuf,
        operation: PathBuf,
    }

    fn write_json(path: &Path, value: &Value) {
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        let mut raw = serde_json::to_vec_pretty(value).unwrap();
        raw.push(b'\n');
        fs::write(path, raw).unwrap();
    }

    fn resign_plan(plan: &mut Value) {
        plan.as_object_mut().unwrap().remove("plan_sha256");
        plan["plan_sha256"] = json!(hash(&serde_json::to_vec(plan).unwrap()));
    }

    impl RecoveredFixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "nt-recovered-owner-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            assert!(!root.exists());
            fs::create_dir(&root).unwrap();
            fs::write(root.join("test-owner"), b"recovered-owner").unwrap();
            let release = format!("dev-{}", "a".repeat(40));
            let layout = Layout::new(&root, &release).unwrap();
            // Match Python RuntimeLayout.state_root's component-by-component
            // spelling, including the separators in serialized plan roots.
            let owner = root
                .join("state")
                .join("engines")
                .join(&release)
                .join("kohya");
            let operation = owner
                .join("operations")
                .join(format!("op-{}", "3".repeat(32)));
            let value = Self {
                layout,
                owner,
                operation,
            };
            value.write_owner("kohya", CURRENT);
            for namespace in ["e", "s", "p"] {
                fs::create_dir_all(value.layout.root.join(namespace).join(CANDIDATE)).unwrap();
            }
            value
        }

        fn write_owner(&self, engine: &str, current: &str) {
            let raw = crate::core::embedded_engine_lock(engine).unwrap();
            let lock: Value = serde_json::from_slice(raw).unwrap();
            let lock_sha = hash(raw);
            let release = format!("dev-{}", "a".repeat(40));
            let owner = self
                .layout
                .root
                .join("state")
                .join("engines")
                .join(&release)
                .join(engine);
            let operation = owner
                .join("operations")
                .join(format!("op-{}", "3".repeat(32)));
            let python_files = lock["python"]["files"]
                .as_object()
                .unwrap()
                .iter()
                .filter(|(name, _)| {
                    !name.ends_with(".pyc") && !name.split('/').any(|part| part == "__pycache__")
                })
                .map(|(name, value)| (name.clone(), value.clone()))
                .collect::<serde_json::Map<String, Value>>();
            let receipt = json!({
                "schema_version":1,"release_id":release,"engine_id":engine,"profile_id":"default",
                "instance_id":current,"generation":2,"recipe_sha256":lock["recipe_sha256"],"lock_sha256":lock_sha,
                "files":{"source":lock["source"]["files"],"environment":{}},"base_python_files":python_files,
                "import":"not_checked","gpu":"skip + CR-004","training":"skip + CR-004"
            });
            let relative = format!("instances/{current}/2.json");
            let receipt_path = owner.join(&relative);
            write_json(&receipt_path, &receipt);
            let state = json!({
                "schema_version":1,"release_id":release,"engine_id":engine,"profile_id":"default",
                "instance_id":current,"generation":2,"validated_generation":2,"dirty":false,"pending":null,"status":"ready",
                "recipe_sha256":lock["recipe_sha256"],"lock_sha256":lock_sha,"python_version":lock["python"]["version"],
                "environment_root":self.layout.root.join("e").join(current),"source_root":self.layout.root.join("s").join(current),
                "python_root":self.layout.root.join("p").join(current),"receipt_relative":relative,
                "receipt_sha256":hash(&fs::read(receipt_path).unwrap())
            });
            write_json(&owner.join("state.json"), &state);
            write_json(&operation.join("old-binding.json"), &state);
            let mut plan = json!({
                "schema_version":1,"release_id":release,"engine_id":engine,"profile_id":"default",
                "kind":"install","rebuild":true,"instance_id":CANDIDATE,"expected_generation":2,
                "recipe_sha256":lock["recipe_sha256"],"lock_sha256":lock_sha,
                "prior_state_sha256":hash(&serde_json::to_vec(&state).unwrap()),
                "write_roots":[self.layout.root.join("e").join(CANDIDATE),self.layout.root.join("s").join(CANDIDATE),self.layout.root.join("p").join(CANDIDATE),owner],
                "profile_writes":[],"main_env_fallback":false,"assets":[],"missing_assets":[],"download_bytes":0,
                "packages":[],"source_paths":[],"issues":[],"status":"ready"
            });
            resign_plan(&mut plan);
            write_json(&operation.join("plan.json"), &plan);
            write_json(
                &operation.join("recovery.json"),
                &json!({"status":"restored_binding","generation":2}),
            );
            fs::create_dir_all(self.layout.root.join("e").join(current)).unwrap();
        }

        fn plan(&self) -> Value {
            serde_json::from_slice(&fs::read(self.operation.join("plan.json")).unwrap()).unwrap()
        }
    }

    impl Drop for RecoveredFixture {
        fn drop(&mut self) {
            if fs::read(self.layout.root.join("test-owner"))
                .ok()
                .as_deref()
                == Some(b"recovered-owner")
            {
                let _ = fs::remove_dir_all(&self.layout.root);
            }
        }
    }

    #[test]
    fn recovered_candidate_owner_preserves_production_rebuild_residue_without_scanning_or_promoting_it(
    ) {
        let f = RecoveredFixture::new();
        let payload = f
            .layout
            .root
            .join("e")
            .join(CANDIDATE)
            .join("not-a-valid-environment.bin");
        fs::write(&payload, b"preserve opaque interrupted bytes").unwrap();
        let before_state = fs::read(f.owner.join("state.json")).unwrap();
        let snapshot = capture(&f.layout).unwrap();
        assert_eq!(
            snapshot.excluded,
            BTreeSet::from([PathBuf::from(CURRENT), PathBuf::from(CANDIDATE)])
        );
        for name in ["plan.json", "old-binding.json", "recovery.json"] {
            let path = f.operation.join(name);
            assert_eq!(
                snapshot.controls[path.strip_prefix(&f.layout.root).unwrap()],
                hash(&fs::read(path).unwrap())
            );
        }
        assert!(!snapshot
            .controls
            .contains_key(payload.strip_prefix(&f.layout.root).unwrap()));
        assert_eq!(
            fs::read(&payload).unwrap(),
            b"preserve opaque interrupted bytes"
        );
        assert_eq!(fs::read(f.owner.join("state.json")).unwrap(), before_state);
        assert!(!f.owner.join("instances").join(CANDIDATE).exists());
        let before = digest(&f.layout).unwrap();
        let path = f.operation.join("recovery.json");
        let mut raw = fs::read(&path).unwrap();
        raw.push(b' '); // 同一合法语义的原文字节变化也必须进入保护摘要。
        fs::write(path, raw).unwrap();
        assert_ne!(before, digest(&f.layout).unwrap());
    }

    #[test]
    fn recovered_candidate_owner_rejects_resigned_wrong_control_root() {
        let f = RecoveredFixture::new();
        let mut plan = f.plan();
        plan["write_roots"][3] = json!(f.owner.join("other"));
        resign_plan(&mut plan);
        write_json(&f.operation.join("plan.json"), &plan);
        assert!(capture(&f.layout).is_err());
    }

    #[test]
    fn pending_candidate_owner_accepts_producer_component_paths() {
        let f = RecoveredFixture::new();
        let mut state: Value =
            serde_json::from_slice(&fs::read(f.owner.join("state.json")).unwrap()).unwrap();
        state["instance_id"] = json!(CANDIDATE);
        state["generation"] = json!(3);
        state["validated_generation"] = json!(0);
        state["status"] = json!("pending");
        state["dirty"] = json!(true);
        state["pending"] = json!(f
            .operation
            .strip_prefix(&f.layout.root)
            .unwrap()
            .to_str()
            .unwrap()
            .replace('\\', "/"));
        for (field, namespace) in [
            ("environment_root", "e"),
            ("source_root", "s"),
            ("python_root", "p"),
        ] {
            state[field] = json!(f.layout.root.join(namespace).join(CANDIDATE));
        }
        write_json(&f.owner.join("state.json"), &state);
        let snapshot = capture(&f.layout).unwrap();
        assert!(snapshot.excluded.contains(&PathBuf::from(CANDIDATE)));
        let before = fs::read(f.owner.join("state.json")).unwrap();
        let mut plan = f.plan();
        plan["write_roots"][3] = json!(f.owner.join("other"));
        resign_plan(&mut plan);
        write_json(&f.operation.join("plan.json"), &plan);
        assert!(capture(&f.layout).is_err());
        assert_eq!(before, fs::read(f.owner.join("state.json")).unwrap());
    }

    #[cfg(windows)]
    #[test]
    fn engine_owner_paths_match_python_pathlib_unicode_vector() {
        // Python 3 pathlib.Path, str(root / component), ensure_ascii=False.
        // Fixed producer vector includes spaces/CJK; no filesystem access.
        let expected: Value = serde_json::from_str(
            r#"["C:\\NT 审查\\中文\\e\\t222222222222222","C:\\NT 审查\\中文\\s\\t222222222222222","C:\\NT 审查\\中文\\p\\t222222222222222","C:\\NT 审查\\中文\\state\\engines\\dev-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\\kohya"]"#,
        )
        .unwrap();
        let root = Path::new(r"C:\NT 审查\中文");
        let owner = root
            .join("state")
            .join("engines")
            .join(format!("dev-{}", "a".repeat(40)))
            .join("kohya");
        assert_eq!(
            json!([
                root.join("e").join(CANDIDATE),
                root.join("s").join(CANDIDATE),
                root.join("p").join(CANDIDATE),
                owner
            ]),
            expected
        );
    }

    #[test]
    fn recovered_candidate_owner_rejects_wrong_signed_plan_identity_and_fake_recovery() {
        for field in [
            "plan_sha256",
            "lock_sha256",
            "recipe_sha256",
            "release_id",
            "engine_id",
            "profile_id",
            "write_roots",
            "kind",
            "rebuild",
            "prior_state_sha256",
            "expected_generation",
            "profile_writes",
            "main_env_fallback",
        ] {
            let f = RecoveredFixture::new();
            let mut plan = f.plan();
            match field {
                "plan_sha256" | "lock_sha256" | "recipe_sha256" | "prior_state_sha256" => {
                    plan[field] = json!("0".repeat(64))
                }
                "release_id" => plan[field] = json!(format!("dev-{}", "b".repeat(40))),
                "engine_id" => plan[field] = json!("ai-toolkit"),
                "profile_id" => plan[field] = json!("other"),
                "write_roots" => {
                    plan[field][0] = json!(f.layout.root.join("e").join("t999999999999999"))
                }
                "kind" => plan[field] = json!("repair"),
                "rebuild" => plan[field] = json!(false),
                "expected_generation" => plan[field] = json!(3),
                "profile_writes" => plan[field] = json!(["unexpected"]),
                "main_env_fallback" => plan[field] = json!(true),
                _ => unreachable!(),
            }
            if field != "plan_sha256" {
                resign_plan(&mut plan);
            }
            write_json(&f.operation.join("plan.json"), &plan);
            assert!(capture(&f.layout).is_err(), "{field}");
        }
        for recovery in [
            json!({"status":"restored","generation":2}),
            json!({"status":"restored_binding","generation":3}),
            json!({"status":"restored_binding","generation":2,"unexpected":true}),
        ] {
            let f = RecoveredFixture::new();
            write_json(&f.operation.join("recovery.json"), &recovery);
            assert!(capture(&f.layout).is_err());
        }
    }

    #[test]
    fn recovered_candidate_owner_requires_old_current_and_independently_verified_receipt() {
        for file in ["old-binding.json", "recovery.json", "plan.json"] {
            let f = RecoveredFixture::new();
            fs::remove_file(f.operation.join(file)).unwrap();
            assert!(capture(&f.layout).is_err(), "{file}");
        }
        let f = RecoveredFixture::new();
        let mut old: Value =
            serde_json::from_slice(&fs::read(f.operation.join("old-binding.json")).unwrap())
                .unwrap();
        old["generation"] = json!(3);
        write_json(&f.operation.join("old-binding.json"), &old);
        assert!(capture(&f.layout).is_err());
        let f = RecoveredFixture::new();
        let mut state: Value =
            serde_json::from_slice(&fs::read(f.owner.join("state.json")).unwrap()).unwrap();
        state.as_object_mut().unwrap().remove("pending");
        write_json(&f.owner.join("state.json"), &state);
        write_json(&f.operation.join("old-binding.json"), &state);
        let mut plan = f.plan();
        plan["prior_state_sha256"] = json!(hash(&serde_json::to_vec(&state).unwrap()));
        resign_plan(&mut plan);
        write_json(&f.operation.join("plan.json"), &plan);
        assert!(capture(&f.layout).is_err());
        let f = RecoveredFixture::new();
        // 当前e项缺失时主循环不会验证它，恢复来源helper仍必须验证其receipt。
        fs::remove_dir(f.layout.root.join("e").join(CURRENT)).unwrap();
        let receipt = f.owner.join(format!("instances/{CURRENT}/2.json"));
        let mut raw = fs::read(&receipt).unwrap();
        raw.push(b' ');
        fs::write(&receipt, raw).unwrap();
        assert!(capture(&f.layout).is_err());
    }

    #[test]
    fn recovered_candidate_owner_rejects_unknown_and_duplicate_allocations() {
        let f = RecoveredFixture::new();
        fs::create_dir(f.layout.root.join("e/t999999999999999")).unwrap();
        assert!(capture(&f.layout).is_err());
        let f = RecoveredFixture::new();
        let duplicate = f
            .owner
            .join("operations")
            .join(format!("op-{}", "4".repeat(32)));
        for name in ["plan.json", "old-binding.json", "recovery.json"] {
            fs::create_dir_all(&duplicate).unwrap();
            fs::copy(f.operation.join(name), duplicate.join(name)).unwrap();
        }
        assert!(capture(&f.layout).is_err());
        let f = RecoveredFixture::new();
        f.write_owner("ai-toolkit", "t555555555555555");
        assert!(capture(&f.layout).is_err());
        let f = RecoveredFixture::new();
        fs::rename(
            f.layout.root.join("e").join(CANDIDATE),
            f.layout.root.join("e/T222222222222222"),
        )
        .unwrap();
        assert!(capture(&f.layout).is_err());
    }

    #[test]
    fn recovered_candidate_owner_keeps_existing_control_budgets() {
        let f = RecoveredFixture::new();
        let state: Value =
            serde_json::from_slice(&fs::read(f.owner.join("state.json")).unwrap()).unwrap();
        let raw = crate::core::embedded_engine_lock("kohya").unwrap();
        let lock: Value = serde_json::from_slice(raw).unwrap();
        let mut total = MAX_TOTAL;
        assert!(recovered_candidate_owner(
            &f.layout,
            &f.owner,
            &state,
            (&lock, &hash(raw)),
            CANDIDATE,
            &mut total,
            &mut BTreeMap::new()
        )
        .is_err());
        let file = fs::OpenOptions::new()
            .write(true)
            .open(f.operation.join("plan.json"))
            .unwrap();
        file.set_len(MAX_RECORD + 1).unwrap();
        assert!(capture(&f.layout).is_err());
        let f = RecoveredFixture::new();
        for n in 0..128 {
            fs::create_dir_all(f.owner.join("operations").join(format!("op-{n:032x}"))).unwrap();
        }
        assert!(capture(&f.layout).is_err());
    }

    #[cfg(windows)]
    #[test]
    fn recovered_candidate_owner_rejects_reparse_provenance_and_candidate_paths() {
        for provenance in [false, true] {
            let f = RecoveredFixture::new();
            let path = if provenance {
                f.operation.clone()
            } else {
                f.layout.root.join("s").join(CANDIDATE)
            };
            let saved = path.with_extension("original");
            fs::rename(&path, &saved).unwrap();
            junction::create(&saved, &path).unwrap();
            let result = capture(&f.layout);
            junction::delete(&path).unwrap();
            assert!(result.is_err());
        }
    }

    #[cfg(unix)]
    #[test]
    fn recovered_candidate_owner_rejects_linked_provenance_and_candidate_paths() {
        use std::os::unix::fs::symlink;
        for provenance in [false, true] {
            let f = RecoveredFixture::new();
            let path = if provenance {
                f.operation.join("recovery.json")
            } else {
                f.layout.root.join("s").join(CANDIDATE)
            };
            let saved = path.with_extension("original");
            fs::rename(&path, &saved).unwrap();
            symlink(&saved, &path).unwrap();
            assert!(capture(&f.layout).is_err());
        }
    }

    #[test]
    fn compiled_locks_accept_runtime_receipts_without_derived_python_bytecode() {
        for engine in ENGINES {
            let raw = crate::core::embedded_engine_lock(engine).unwrap();
            let lock: Value = serde_json::from_slice(raw).unwrap();
            let lock_sha = hash(raw);
            let mut files = lock["python"]["files"].as_object().unwrap().clone();
            // Mirror the Python worker contract independently from receipt_identity.
            files.retain(|path, _| {
                !path.ends_with(".pyc") && !path.split('/').any(|p| p == "__pycache__")
            });
            assert!(!files.is_empty());
            assert!(files.len() < lock["python"]["files"].as_object().unwrap().len());
            let receipt = json!({
                "schema_version": 1,
                "release_id": "dev-test",
                "engine_id": engine,
                "instance_id": "t0123456789abcde",
                "generation": 1,
                "recipe_sha256": lock["recipe_sha256"],
                "lock_sha256": lock_sha,
                "files": { "source": lock["source"]["files"], "environment": {} },
                "base_python_files": files,
            });
            let verify = |value: &Value| {
                receipt_identity(
                    value,
                    "dev-test",
                    engine,
                    "t0123456789abcde",
                    1,
                    &lock,
                    &lock_sha,
                )
            };
            verify(&receipt).unwrap();
            let original_path = files.keys().next().unwrap().clone();

            let mut missing = receipt.clone();
            missing["base_python_files"]
                .as_object_mut()
                .unwrap()
                .remove(&original_path);
            assert!(
                verify(&missing).is_err(),
                "{engine}: missing original accepted"
            );

            let mut changed = receipt.clone();
            changed["base_python_files"][&original_path]["sha256"] = json!("0".repeat(64));
            assert!(
                verify(&changed).is_err(),
                "{engine}: changed original accepted"
            );

            let mut extra = receipt.clone();
            extra["base_python_files"]["unexpected.py"] =
                json!({"bytes": 0, "sha256": "0".repeat(64)});
            assert!(verify(&extra).is_err(), "{engine}: extra original accepted");

            let mut wrong_generation = receipt.clone();
            wrong_generation["generation"] = json!(2);
            assert!(
                verify(&wrong_generation).is_err(),
                "{engine}: wrong generation accepted"
            );
        }
    }
}
