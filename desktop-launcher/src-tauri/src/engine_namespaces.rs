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
    if value["schema_version"] != 1
        || value["release_id"] != release
        || value["engine_id"] != engine
        || value["instance_id"] != id
        || value["generation"] != generation
        || value["recipe_sha256"] != lock["recipe_sha256"]
        || value["lock_sha256"] != lock_sha
        || value["files"]["source"] != lock["source"]["files"]
        || value["base_python_files"] != lock["python"]["files"]
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
    for release_dir in children(layout, &layout.root.join("state/engines"))? {
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
                } else {
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
