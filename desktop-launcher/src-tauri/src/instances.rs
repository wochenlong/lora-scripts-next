//! 固定路径 GUI 实例事务；修改必须持有同一 workspace lease，dirty 仅由复验清除。
use crate::model::{self, Layout, WorkspaceMutation};
use crate::operations::CancelToken;
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Component, Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
    time::{Duration, Instant},
};
#[path = "engine_namespaces.rs"]
mod engine_namespaces;
pub(crate) fn engine_control_digest(layout: &Layout) -> Result<String> {
    engine_namespaces::digest(layout)
}

const MAX_FILE: u64 = 1024 * 1024 * 1024;
const MAX_TREE: u64 = 4 * MAX_FILE;
const MAX_STATE: u64 = 32 * 1024 * 1024;
const MAX_PROFILE_BYTES: u64 = 8 * 1024 * 1024 * 1024 * 1024;
const MAX_PROFILE_NODES: u64 = 1_000_000;
const MAX_PROFILE_DIRECTORY_ENTRIES: usize = 100_000;
const MAX_PROFILE_DEPTH: usize = 128;
const MAX_PROFILE_PATH_BYTES: u64 = 256 * 1024 * 1024;
static NEXT: AtomicU64 = AtomicU64::new(0);
type Tree = BTreeMap<PathBuf, Node>;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct RebuildBoundary {
    schema_version: u32,
    root_absolute: PathBuf,
    release_id: String,
    profiles: ProfilesSummary,
    components: BTreeMap<PathBuf, Tree>,
    states: BTreeMap<PathBuf, Fingerprint>,
    snapshots: BTreeMap<PathBuf, Tree>,
    pending: Vec<RebuildPendingReference>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct RebuildPendingReference {
    release_id: String,
    instance_id: String,
    generation: u64,
    state: Fingerprint,
    pending_sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct RebuildExtension {
    schema_version: u32,
    transaction: String,
    root_absolute: PathBuf,
    release_id: String,
    boundary_sha256: String,
    candidate_id: String,
    candidate_state: Fingerprint,
    candidate_tree: Tree,
    pending: Vec<RebuildPendingReference>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredRebuildPlan {
    schema_version: u32,
    root_absolute: PathBuf,
    release_id: String,
    registry: Fingerprint,
    boundary_sha256: String,
    old_binding: Option<model::EnvironmentBinding>,
    missing_wheels: Vec<String>,
    estimated_network_bytes: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct StoredRebuildIntent {
    schema_version: u32,
    transaction: String,
    root_absolute: PathBuf,
    release_id: String,
    candidate_id: String,
    status: String,
    plan: StoredRebuildPlan,
    plan_sha256: String,
    boundary_sha256: String,
    old_registry: Fingerprint,
    candidate_state: Option<Fingerprint>,
    candidate_tree_sha256: Option<String>,
    proof: Option<crate::gui_registration_integrity::TrustedEnvironment>,
    new_registry: Option<Fingerprint>,
    preservation_file: Option<String>,
    preservation_sha256: Option<String>,
    terminal_status: Option<String>,
    failure: Option<String>,
}

/// 重建前的精确边界；持久化在专属backups中，旧事务原字节保持不动。
#[cfg(test)]
pub(crate) fn rebuild_boundary(
    ctx: &WorkspaceMutation,
    cancel: &CancelToken,
) -> Result<RebuildBoundary> {
    rebuild_observe_boundary(ctx.layout(), cancel)
}
pub(crate) fn rebuild_observe_boundary(
    layout: &Layout,
    cancel: &CancelToken,
) -> Result<RebuildBoundary> {
    cancel.check()?;
    let mut components = BTreeMap::new();
    for root in [
        layout.release_dir.clone(),
        layout.root.join("tools/uv.exe"),
        layout.root.join("environments"),
        layout.root.join("e"),
        layout.root.join("state/gui-repairs"),
    ] {
        components.insert(
            root.strip_prefix(&layout.root)?.to_path_buf(),
            scan(layout, &root, &[])?,
        );
    }
    components.insert(PathBuf::from("python/3.10.19"), python_tree(layout)?);
    let mut states = BTreeMap::new();
    let mut snapshots = BTreeMap::new();
    let mut pending = Vec::new();
    let base = layout.root.join("state/instances");
    layout.guard_path(&base)?;
    if base.exists() {
        for entry in fs::read_dir(&base)? {
            cancel.check()?;
            let path = entry?.path();
            layout.guard_path(&path)?;
            if path.extension().is_none_or(|e| e != "json") {
                bail!("实例状态容器含未知文件，拒绝重建");
            }
            let id = path
                .file_stem()
                .and_then(|s| s.to_str())
                .context("实例状态非UTF8")?;
            let bytes = fs::read(&path)?;
            if bytes.len() as u64 > MAX_STATE {
                bail!("实例状态超限");
            }
            let state: InstanceState = serde_json::from_slice(&bytes)?;
            let owner = Layout::new(&layout.root, &state.release_id)?;
            validate(&owner, id, &state)?;
            let fingerprint = fingerprint(layout, &path)?;
            states.insert(
                path.strip_prefix(&layout.root)?.to_path_buf(),
                fingerprint.clone(),
            );
            if state.base_python_pending.is_some() {
                bail!("基础Python引用事务未完成，不能重建GUI");
            }
            if let Some(transaction) = &state.pending {
                check_snapshots(&owner, &state)?;
                snapshots.insert(
                    transaction.directory.clone(),
                    scan(&owner, &owner.root.join(&transaction.directory), &[])?,
                );
                // 旧事务在重建前必须仍能验证其非目标保护合同。
                protected(
                    &owner,
                    &state.verified,
                    &observe(&owner, &state, cancel)?,
                    &transaction.files,
                )?;
                pending.push(RebuildPendingReference {
                    release_id: state.release_id.clone(),
                    instance_id: id.into(),
                    generation: state.generation,
                    state: fingerprint,
                    pending_sha256: hash(&serde_json::to_vec(transaction)?),
                });
            }
        }
    }
    pending.sort_by(|a, b| a.instance_id.cmp(&b.instance_id));
    Ok(RebuildBoundary {
        schema_version: 1,
        root_absolute: layout.root.clone(),
        release_id: release(layout)?.into(),
        profiles: summarize_profiles(layout, cancel)?,
        components,
        states,
        snapshots,
        pending,
    })
}

pub(crate) fn rebuild_boundary_sha(boundary: &RebuildBoundary) -> Result<String> {
    Ok(hash(&serde_json::to_vec(boundary)?))
}
pub(crate) fn rebuild_check_boundary(
    ctx: &WorkspaceMutation,
    boundary: &RebuildBoundary,
    candidate_id: &str,
    cancel: &CancelToken,
) -> Result<()> {
    let layout = ctx.layout();
    model::validate_environment_storage(candidate_id, 1)?;
    if boundary.schema_version != 1
        || boundary.root_absolute != layout.root
        || boundary.release_id != release(layout)?
    {
        bail!("重建边界身份不符");
    }
    if summarize_profiles(layout, cancel)? != boundary.profiles {
        bail!("重建改变生产profiles");
    }
    for (relative, before) in &boundary.components {
        let mut current = if relative == Path::new("python/3.10.19") {
            python_tree(layout)?
        } else {
            scan(layout, &layout.root.join(relative), &[])?
        };
        if relative == Path::new("e") {
            let candidate = Path::new(candidate_id);
            if before.keys().any(|p| p.starts_with(candidate)) {
                bail!("重建候选原路径非空，禁止追认");
            }
            current.retain(|path, _| !path.starts_with(candidate));
            if before.is_empty() && current == Tree::from([(PathBuf::new(), Node::Directory)]) {
                current.clear();
            }
        }
        if *before != current {
            bail!("重建改变非候选保护树：{}", relative.display());
        }
    }
    let base = layout.root.join("state/instances");
    let mut states = BTreeMap::new();
    if base.exists() {
        for entry in fs::read_dir(&base)? {
            let path = entry?.path();
            layout.guard_path(&path)?;
            if path == base.join(format!("{candidate_id}.json")) {
                continue;
            }
            states.insert(
                path.strip_prefix(&layout.root)?.to_path_buf(),
                fingerprint(layout, &path)?,
            );
        }
    }
    if states != boundary.states {
        bail!("重建改变旧实例state或引入未知状态");
    }
    for (relative, before) in &boundary.snapshots {
        if scan(layout, &layout.root.join(relative), &[])? != *before {
            bail!("重建改变旧pending独立快照或manifest");
        }
    }
    Ok(())
}

pub(crate) fn rebuild_candidate_tree_sha(layout: &Layout, id: &str) -> Result<String> {
    let path = model::environment_path(&layout.root, release(layout)?, id, 1)?;
    Ok(hash(&serde_json::to_vec(&scan(layout, &path, &[])?)?))
}

pub(crate) fn rebuild_create(
    ctx: &WorkspaceMutation,
    id: &str,
    recipe_id: &str,
    recipe_sha256: &str,
    transaction: &str,
    cancel: &CancelToken,
) -> Result<InstanceState> {
    let layout = ctx.layout();
    model::validate_environment_storage(id, 1)?;
    model::validate_component(transaction)?;
    if !transaction.starts_with("gui-rebuild-") || !valid_hash(recipe_sha256) {
        bail!("重建创建许可身份不符");
    }
    let target = state_path(layout, id)?;
    if target.exists() {
        let state = load(layout, id)?;
        if state.storage_version != 1
            || state.recipe_id != recipe_id
            || state.recipe_sha256 != recipe_sha256
            || state.generation != 1
            || state.validated_generation != u64::from(!state.dirty)
            || state.pending.is_some()
            || state.base_python_pending.is_some()
        {
            bail!("重建初始state不匹配");
        }
        return Ok(state);
    }
    let environment = model::environment_path(&layout.root, release(layout)?, id, 1)?;
    if model::environment_path(&layout.root, release(layout)?, id, 0)?.exists() {
        bail!("重建候选跨命名空间冲突");
    }
    let parent = environment.parent().context("候选缺父目录")?;
    layout.ensure_dir(parent)?;
    if environment.exists() {
        if !fs::symlink_metadata(&environment)?.is_dir()
            || fs::read_dir(&environment)?.next().is_some()
        {
            bail!("缺state重建候选不是空目录，不追认");
        }
    } else {
        fs::create_dir(&environment)?;
    }
    let mut state = InstanceState {
        schema_version: 2,
        component: "gui".into(),
        instance_id: id.into(),
        storage_version: 1,
        release_id: release(layout)?.into(),
        root_absolute: layout.root.clone(),
        recipe_id: recipe_id.into(),
        recipe_sha256: recipe_sha256.into(),
        generation: 1,
        validated_generation: 0,
        dirty: true,
        ignored: vec![],
        verified: Observation {
            environment: Tree::new(),
            profiles: Tree::new(),
            profiles_summary: None,
            protected: BTreeMap::new(),
        },
        pending: None,
        base_python_pending: None,
        registration_origin: None,
    };
    state.verified = observe(layout, &state, cancel)?;
    validate(layout, id, &state)?;
    model::write_gui_transaction_bytes(
        &layout.root,
        transaction,
        &target,
        &registration_encoded(layout, &state)?,
    )?;
    Ok(state)
}

pub(crate) fn rebuild_validate_candidate(
    ctx: &WorkspaceMutation,
    boundary: &RebuildBoundary,
    id: &str,
    transaction: &str,
    cancel: &CancelToken,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    let layout = ctx.layout();
    let engine_controls = engine_control_digest(layout)?;
    let mut state = load(layout, id)?;
    if state.storage_version != 1
        || state.generation != 1
        || state.pending.is_some()
        || state.base_python_pending.is_some()
    {
        bail!("重建候选身份不符");
    }
    rebuild_check_boundary(ctx, boundary, id, cancel)?;
    let before = observe(layout, &state, cancel)?;
    validator(&path(&state)?)?;
    if observe(layout, &state, cancel)? != before
        || load(layout, id)? != state
        || engine_control_digest(layout)? != engine_controls
    {
        bail!("重建验证改变受保护内容或实例状态");
    }
    rebuild_check_boundary(ctx, boundary, id, cancel)?;
    state.dirty = false;
    state.validated_generation = state.generation;
    state.verified = before;
    model::write_gui_transaction_bytes(
        &layout.root,
        transaction,
        &state_path(layout, id)?,
        &registration_encoded(layout, &state)?,
    )?;
    Ok(state)
}
pub(crate) fn rebuild_mark_orphan(
    ctx: &WorkspaceMutation,
    id: &str,
    transaction: &str,
) -> Result<()> {
    let layout = ctx.layout();
    let mut state = load(layout, id)?;
    if state.storage_version != 1
        || state.generation != 1
        || state.pending.is_some()
        || state.base_python_pending.is_some()
    {
        bail!("非本轮新候选不能封存为orphan");
    }
    state.dirty = true;
    state.validated_generation = 0;
    model::write_gui_transaction_bytes(
        &layout.root,
        transaction,
        &state_path(layout, id)?,
        &registration_encoded(layout, &state)?,
    )
}
pub(crate) fn preserved_pending(root: &Path) -> Result<Vec<serde_json::Value>> {
    let catalog = model::Catalog::embedded()?;
    let scope = Layout::new(root, &catalog.releases.first().context("发布目录为空")?.id)?;
    let container = root.join("state/gui-rebuild");
    scope.guard_path(&container)?;
    let mut pending = Vec::new();
    if !container.exists() {
        return Ok(pending);
    }
    for entry in fs::read_dir(&container)? {
        let path = entry?.path();
        scope.guard_path(&path)?;
        let metadata = fs::symlink_metadata(&path)?;
        if path.extension().is_none_or(|e| e != "json")
            || !metadata.is_file()
            || metadata.len() > MAX_STATE
        {
            bail!("重建授权容器含未知或超限文件");
        }
        let owner_value: StoredRebuildIntent = serde_json::from_slice(&fs::read(&path)?)?;
        let layout = Layout::new(root, &owner_value.release_id)?;
        let Some((value, extension, _boundary)) = load_rebuild_extension(&layout, &path)? else {
            continue;
        };
        for reference in extension.pending {
            let owner = Layout::new(root, &reference.release_id)?;
            let state = load(&owner, &reference.instance_id)?;
            let receipt = recovery_receipt(&owner, &value.transaction, &reference)?;
            if receipt.exists() {
                let bytes = fs::read(&receipt)?;
                let recovered = registration_decode(&owner, &bytes)?;
                if recovered.id() != reference.instance_id
                    || recovered.release_id() != reference.release_id
                    || recovered.generation != reference.generation
                    || recovered.dirty
                    || recovered.pending.is_some()
                    || recovered.base_python_pending.is_some()
                {
                    bail!("旧pending恢复侧录身份不符");
                }
                if state.generation < reference.generation
                    || state.generation == reference.generation && state != recovered
                {
                    // clean提交前崩溃时旧pending仍在，继续显示待恢复；绝不凭侧录跳过它。
                    if state.pending.is_none() || state.generation != reference.generation {
                        bail!("旧pending恢复侧录与实例状态断联");
                    }
                } else {
                    continue;
                }
            }
            if let Some(transaction) = &state.pending {
                if state.generation != reference.generation
                    || fingerprint(&owner, &state_path(&owner, state.id())?)? != reference.state
                    || hash(&serde_json::to_vec(transaction)?) != reference.pending_sha256
                {
                    bail!("保留旧pending身份变化，禁止正式运行");
                }
                pending.push(serde_json::json!({"transaction":value.transaction,"release_id":reference.release_id,"instance_id":reference.instance_id,"generation":reference.generation}));
            } else {
                bail!("保留旧pending缺少精确clean恢复侧录，禁止正式运行");
            }
        }
    }
    pending.sort_by_key(|v| {
        (
            v["release_id"].as_str().unwrap_or_default().to_owned(),
            v["instance_id"].as_str().unwrap_or_default().to_owned(),
        )
    });
    pending.dedup_by(|a, b| {
        a["release_id"] == b["release_id"] && a["instance_id"] == b["instance_id"]
    });
    Ok(pending)
}
fn recovery_receipt(
    layout: &Layout,
    transaction: &str,
    reference: &RebuildPendingReference,
) -> Result<PathBuf> {
    model::validate_component(transaction)?;
    model::validate_component(&reference.instance_id)?;
    let path = layout.root.join("backups").join(transaction).join(format!(
        "recovered-{}-generation-{}.json",
        reference.instance_id, reference.generation
    ));
    layout.guard_path(&path)?;
    if path.exists()
        && (!fs::symlink_metadata(&path)?.is_file() || fs::metadata(&path)?.len() > MAX_STATE)
    {
        bail!("旧pending恢复侧录不是限额普通文件");
    }
    Ok(path)
}

/// 恢复原state前写入精确clean侧录；后续合法generation变化不重新激活已完成的旧事务。
fn record_preserved_recovery(
    layout: &Layout,
    old: &InstanceState,
    recovered: &InstanceState,
) -> Result<()> {
    let Some(pending) = &old.pending else {
        return Ok(());
    };
    let container = layout.root.join("state/gui-rebuild");
    layout.guard_path(&container)?;
    if !container.exists() {
        return Ok(());
    }
    let previous = fingerprint(layout, &state_path(layout, old.id())?)?;
    let pending_sha = hash(&serde_json::to_vec(pending)?);
    let bytes = registration_encoded(layout, recovered)?;
    for entry in fs::read_dir(container)? {
        let Some((authority, extension, _)) = load_rebuild_extension(layout, &entry?.path())?
        else {
            continue;
        };
        for reference in &extension.pending {
            if reference.instance_id == old.id()
                && reference.release_id == old.release_id
                && reference.generation == old.generation
                && reference.state == previous
                && reference.pending_sha256 == pending_sha
            {
                let path = recovery_receipt(layout, &authority.transaction, reference)?;
                if path.exists() {
                    if fs::read(&path)? != bytes {
                        bail!("恢复侧录重名但内容不同，保留dirty");
                    }
                } else {
                    model::write_gui_transaction_bytes(
                        &layout.root,
                        &authority.transaction,
                        &path,
                        &bytes,
                    )?;
                }
            }
        }
    }
    Ok(())
}
pub(crate) fn assert_no_preserved_pending(root: &Path) -> Result<()> {
    let pending = preserved_pending(root)?;
    if !pending.is_empty() {
        bail!(
            "重建已保留旧事务，正式启动/变更前须按实例ID恢复且不切当前绑定：{}",
            serde_json::to_string(&pending)?
        );
    }
    Ok(())
}

pub(crate) fn recover_preserved_controlled(
    ctx: &WorkspaceMutation,
    id: &str,
    cancel: &CancelToken,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    let layout = ctx.layout();
    let entries = preserved_pending(&layout.root)?;
    if !entries.iter().any(|v| {
        v["instance_id"].as_str() == Some(id) && v["release_id"].as_str() == release(layout).ok()
    }) {
        bail!("实例不属于已闭合重建的保留事务");
    }
    let ticket = reload_ticket(layout, id)?;
    recover_controlled(ctx, &ticket, cancel, validator)
}

pub(crate) fn rebuild_preservation(
    ctx: &WorkspaceMutation,
    transaction: &str,
    boundary: &RebuildBoundary,
    id: &str,
    cancel: &CancelToken,
) -> Result<serde_json::Value> {
    model::validate_component(transaction)?;
    if !transaction.starts_with("gui-rebuild-") {
        bail!("重建事务身份不符");
    }
    rebuild_check_boundary(ctx, boundary, id, cancel)?;
    let layout = ctx.layout();
    let candidate = load(layout, id)?;
    if candidate.storage_version != 1 {
        bail!("重建只创建新短路径实例");
    }
    let extension = RebuildExtension {
        schema_version: 1,
        transaction: transaction.into(),
        root_absolute: layout.root.clone(),
        release_id: release(layout)?.into(),
        boundary_sha256: rebuild_boundary_sha(boundary)?,
        candidate_id: id.into(),
        candidate_state: fingerprint(layout, &state_path(layout, id)?)?,
        candidate_tree: scan(layout, &path(&candidate)?, &[])?,
        pending: boundary.pending.clone(),
    };
    Ok(serde_json::to_value(extension)?)
}

fn load_rebuild_extension(
    layout: &Layout,
    path: &Path,
) -> Result<Option<(StoredRebuildIntent, RebuildExtension, RebuildBoundary)>> {
    layout.guard_path(path)?;
    if path.extension().is_none_or(|e| e != "json") || fs::metadata(path)?.len() > MAX_STATE {
        bail!("重建授权文件格式/限额无效");
    }
    let authority: StoredRebuildIntent = serde_json::from_slice(&fs::read(path)?)?;
    if authority.schema_version != 1
        || authority.plan.schema_version != 1
        || authority.root_absolute != layout.root
        || authority.plan.root_absolute != layout.root
        || authority.plan.release_id != authority.release_id
        || authority.boundary_sha256 != authority.plan.boundary_sha256
        || authority.old_registry != authority.plan.registry
        || hash(&serde_json::to_vec(&authority.plan)?) != authority.plan_sha256
    {
        bail!("重建授权完整intent/plan身份不符");
    }
    if !matches!(
        authority.status.as_str(),
        "creating" | "building" | "validating" | "committing" | "committed" | "orphaned"
    ) {
        bail!("重建授权status未知");
    }
    if !matches!(authority.status.as_str(), "committed" | "orphaned") {
        return Ok(None);
    }
    if authority.terminal_status.as_deref() != Some(authority.status.as_str()) {
        bail!("重建授权终态断联");
    }
    let transaction = &authority.transaction;
    model::validate_component(transaction)?;
    if !transaction.starts_with("gui-rebuild-")
        || path.file_stem().is_none_or(|p| p != transaction.as_str())
    {
        bail!("重建授权身份不符");
    }
    let expected_sha = authority
        .preservation_sha256
        .as_ref()
        .context("重建缺少保护SHA")?;
    let preservation_file = authority
        .preservation_file
        .as_ref()
        .context("重建缺少保护快照名")?;
    if preservation_file != &format!("preservation-{expected_sha}.json") {
        bail!("重建保护快照命名不匹配内容身份");
    }
    let extension_path = layout
        .root
        .join("backups")
        .join(transaction)
        .join(preservation_file);
    layout.guard_path(&extension_path)?;
    let bytes = fs::read(&extension_path)?;
    if hash(&bytes) != *expected_sha {
        bail!("重建精确保护侧录损坏");
    }
    let extension: RebuildExtension = serde_json::from_slice(&bytes)?;
    if extension.schema_version != 1
        || extension.transaction != *transaction
        || extension.root_absolute != layout.root
        || extension.release_id != authority.release_id
        || extension.candidate_id != authority.candidate_id
        || extension.boundary_sha256 != authority.boundary_sha256
        || authority.candidate_state.as_ref() != Some(&extension.candidate_state)
        || authority.candidate_tree_sha256.as_ref()
            != Some(&hash(&serde_json::to_vec(&extension.candidate_tree)?))
    {
        bail!("重建授权与精确保护闭包断联");
    }
    let old_path = layout
        .root
        .join("backups")
        .join(transaction)
        .join("registry-old.json");
    layout.guard_path(&old_path)?;
    if fingerprint(layout, &old_path)? != authority.old_registry {
        bail!("重建旧registry快照身份变化");
    }
    let old: model::Registry = serde_json::from_slice(&fs::read(old_path)?)?;
    old.validate()?;
    if old.gui_binding(&extension.release_id) != authority.plan.old_binding.as_ref() {
        bail!("重建旧binding与计划断联");
    }
    match authority.status.as_str() {
        "orphaned" => {
            if authority.new_registry.is_some() {
                bail!("orphan重建不能授权新binding");
            }
        }
        "committed" => {
            let proof = authority
                .proof
                .as_ref()
                .context("成功重建授权缺少完整可信证明")?;
            if proof.environment
                != model::environment_path(
                    &layout.root,
                    &extension.release_id,
                    &extension.candidate_id,
                    1,
                )?
                || proof.recipe_sha256
                    != "00ce9d78bc779f72405c84145ded75e63deca34d5b21afc51f1a78b76a0773ba"
                || proof.trusted_index_sha256
                    != crate::gui_registration_integrity::trusted_index_sha256()
            {
                bail!("成功重建proof信任根断联");
            }
            let new_path = layout
                .root
                .join("backups")
                .join(transaction)
                .join("registry-new.json");
            layout.guard_path(&new_path)?;
            if Some(fingerprint(layout, &new_path)?) != authority.new_registry {
                bail!("重建newregistry快照身份变化");
            }
            let new: model::Registry = serde_json::from_slice(&fs::read(new_path)?)?;
            new.validate()?;
            let release = model::Catalog::embedded()?
                .release(&extension.release_id)?
                .clone();
            let mut expected = old;
            expected.schema_version = expected.schema_version.max(2);
            expected.record_installed(&release)?;
            expected.bind_gui(
                &extension.release_id,
                model::EnvironmentBinding {
                    instance_id: extension.candidate_id.clone(),
                    storage_version: 1,
                    recipe_id: crate::recipe::GuiRecipe::embedded()?.id().into(),
                    recipe_sha256: proof.recipe_sha256.clone(),
                    generation: 1,
                },
            )?;
            if new != expected {
                bail!("重建newregistry语义未授权");
            }
        }
        _ => unreachable!(),
    }
    let boundary_path = layout
        .root
        .join("backups")
        .join(transaction)
        .join("boundary.json");
    layout.guard_path(&boundary_path)?;
    let boundary: RebuildBoundary = serde_json::from_slice(&fs::read(&boundary_path)?)?;
    if rebuild_boundary_sha(&boundary)? != extension.boundary_sha256
        || boundary.pending != extension.pending
    {
        bail!("重建旧保护边界损坏");
    }
    Ok(Some((authority, extension, boundary)))
}
fn project_rebuild_extensions(
    layout: &Layout,
    state: &InstanceState,
    tree: &mut Tree,
) -> Result<()> {
    let Some(pending) = &state.pending else {
        return Ok(());
    };
    let authority_root = layout.root.join("state/gui-rebuild");
    layout.guard_path(&authority_root)?;
    if !authority_root.exists() {
        return Ok(());
    }
    let state_fingerprint = fingerprint(layout, &state_path(layout, state.id())?)?;
    for entry in fs::read_dir(&authority_root)? {
        let path = entry?.path();
        layout.guard_path(&path)?;
        if path.extension().is_none_or(|e| e != "json") {
            bail!("重建授权目录含未知文件");
        }
        if fs::metadata(&path)?.len() > MAX_STATE {
            bail!("重建授权记录超限");
        }
        let Some((_authority, extension, boundary)) = load_rebuild_extension(layout, &path)? else {
            continue;
        };
        let applies = extension.pending.iter().any(|reference| {
            reference.instance_id == state.id()
                && reference.release_id == state.release_id
                && reference.generation == state.generation
                && reference.state == state_fingerprint
                && reference.pending_sha256
                    == hash(&serde_json::to_vec(pending).unwrap_or_default())
        });
        if !applies {
            continue;
        }
        model::validate_environment_storage(&extension.candidate_id, 1)?;
        if fingerprint(layout, &state_path(layout, &extension.candidate_id)?)?
            != extension.candidate_state
        {
            bail!("重建新增state变化，拒绝放宽旧pending");
        }
        let candidate_path = model::environment_path(
            &layout.root,
            &extension.release_id,
            &extension.candidate_id,
            1,
        )?;
        if scan(layout, &candidate_path, &[])? != extension.candidate_tree {
            bail!("重建新增子树变化，拒绝放宽旧pending");
        }
        let candidate = Path::new(&extension.candidate_id);
        if boundary
            .components
            .get(Path::new("e"))
            .context("重建边界缺少e")?
            .keys()
            .any(|p| p.starts_with(candidate))
        {
            bail!("重建授权原边界已含候选");
        }
        tree.retain(|path, _| !path.starts_with(candidate));
    }
    if state
        .verified
        .protected
        .get(Path::new("e"))
        .is_none_or(BTreeMap::is_empty)
        && tree == &Tree::from([(PathBuf::new(), Node::Directory)])
    {
        tree.clear();
    }
    Ok(())
}

#[cfg(test)]
mod rebuild_preservation_tests {
    use super::*;
    struct Fixture {
        ctx: WorkspaceMutation,
        state: InstanceState,
        ticket: MutationTicket,
        old_bytes: Vec<u8>,
    }
    impl Fixture {
        fn new(storage: u32, no_legacy_e: bool) -> Self {
            let root = std::env::temp_dir().join(format!(
                "nt-rebuild-preserve-{}-{}-{}",
                std::process::id(),
                model::now(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            let ctx =
                WorkspaceMutation::acquire(&root, &format!("dev-{}", "a".repeat(40))).unwrap();
            let mut state =
                create(&ctx, "g1111111111111111", "recipe-one", &"b".repeat(64)).unwrap();
            if storage == 0 {
                let old = path(&state).unwrap();
                state.storage_version = 0;
                let new = path(&state).unwrap();
                ctx.layout().ensure_dir(new.parent().unwrap()).unwrap();
                fs::rename(old, &new).unwrap();
                fs::remove_dir(root.join("e")).unwrap();
                state.verified = observe(ctx.layout(), &state, &CancelToken::new()).unwrap();
                save(ctx.layout(), &state).unwrap();
            }
            fs::write(path(&state).unwrap().join("target.py"), b"original").unwrap();
            let state = validate_new(&ctx, &state, &[], |_| Ok(())).unwrap();
            let ticket = begin(
                &ctx,
                &plan(&ctx, state.id(), state.generation(), &["target.py".into()]).unwrap(),
            )
            .unwrap();
            fs::write(path(&state).unwrap().join("target.py"), b"damaged").unwrap();
            if no_legacy_e {
                let mut old = load(ctx.layout(), state.id()).unwrap();
                old.verified.protected.remove(Path::new("e"));
                old.pending.as_mut().unwrap().tree_sha256 =
                    hash(&serde_json::to_vec(&old.verified).unwrap());
                let pending = old.pending.as_ref().unwrap();
                model::write_json_atomic(
                    &root.join(&pending.directory).join("manifest.json"),
                    pending,
                )
                .unwrap();
                save(ctx.layout(), &old).unwrap();
            }
            let ticket = if no_legacy_e {
                reload_ticket(ctx.layout(), state.id()).unwrap()
            } else {
                ticket
            };
            let old_bytes = fs::read(state_path(ctx.layout(), state.id()).unwrap()).unwrap();
            Self {
                ctx,
                state,
                ticket,
                old_bytes,
            }
        }
        fn seal(&self, status: &str) -> String {
            let tx = format!(
                "gui-rebuild-preservation-test-{}",
                NEXT.fetch_add(1, Ordering::Relaxed)
            );
            let cancel = CancelToken::new();
            let boundary = rebuild_boundary(&self.ctx, &cancel).unwrap();
            rebuild_create(
                &self.ctx,
                "g2222222222222222",
                "recipe-one",
                &"b".repeat(64),
                &tx,
                &cancel,
            )
            .unwrap();
            fs::write(
                self.ctx
                    .layout()
                    .root
                    .join("e/g2222222222222222/partial.dll"),
                b"candidate-original",
            )
            .unwrap();
            let extension =
                rebuild_preservation(&self.ctx, &tx, &boundary, "g2222222222222222", &cancel)
                    .unwrap();
            let mut bytes = serde_json::to_vec_pretty(&extension).unwrap();
            bytes.push(b'\n');
            model::write_gui_transaction_bytes(
                &self.ctx.layout().root,
                &tx,
                &self
                    .ctx
                    .layout()
                    .root
                    .join("backups")
                    .join(&tx)
                    .join(format!("preservation-{}.json", hash(&bytes))),
                &bytes,
            )
            .unwrap();
            model::write_gui_transaction_json(
                &self.ctx.layout().root,
                &tx,
                &self
                    .ctx
                    .layout()
                    .root
                    .join("backups")
                    .join(&tx)
                    .join("boundary.json"),
                &boundary,
            )
            .unwrap();
            let old = model::Registry::default();
            let mut old_bytes = serde_json::to_vec_pretty(&old).unwrap();
            old_bytes.push(b'\n');
            model::write_gui_transaction_bytes(
                &self.ctx.layout().root,
                &tx,
                &self
                    .ctx
                    .layout()
                    .root
                    .join("backups")
                    .join(&tx)
                    .join("registry-old.json"),
                &old_bytes,
            )
            .unwrap();
            let plan = StoredRebuildPlan {
                schema_version: 1,
                root_absolute: self.ctx.layout().root.clone(),
                release_id: self.state.release_id.clone(),
                registry: Fingerprint {
                    bytes: old_bytes.len() as u64,
                    sha256: hash(&old_bytes),
                },
                boundary_sha256: rebuild_boundary_sha(&boundary).unwrap(),
                old_binding: None,
                missing_wheels: vec![],
                estimated_network_bytes: 0,
            };
            let extension: RebuildExtension = serde_json::from_value(extension).unwrap();
            let authority = StoredRebuildIntent {
                schema_version: 1,
                transaction: tx.clone(),
                root_absolute: self.ctx.layout().root.clone(),
                release_id: self.state.release_id.clone(),
                candidate_id: "g2222222222222222".into(),
                status: status.into(),
                plan_sha256: hash(&serde_json::to_vec(&plan).unwrap()),
                boundary_sha256: plan.boundary_sha256.clone(),
                old_registry: plan.registry.clone(),
                plan,
                candidate_state: Some(extension.candidate_state),
                candidate_tree_sha256: Some(hash(
                    &serde_json::to_vec(&extension.candidate_tree).unwrap(),
                )),
                proof: None,
                new_registry: None,
                preservation_file: Some(format!("preservation-{}.json", hash(&bytes))),
                preservation_sha256: Some(hash(&bytes)),
                terminal_status: Some(status.into()),
                failure: Some("controlled partial".into()),
            };
            model::write_gui_transaction_json(
                &self.ctx.layout().root,
                &tx,
                &self
                    .ctx
                    .layout()
                    .root
                    .join("state/gui-rebuild")
                    .join(format!("{tx}.json")),
                &authority,
            )
            .unwrap();
            tx
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let root = &self.ctx.layout().root;
            if root.parent() == Some(std::env::temp_dir().as_path())
                && root
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with("nt-rebuild-preserve-")
            {
                let _ = fs::remove_dir_all(root);
            }
        }
    }
    #[test]
    fn compact_pending_recovers_after_success_exact_new_instance_extension() {
        let f = Fixture::new(1, false);
        f.seal("orphaned");
        assert_eq!(
            fs::read(state_path(f.ctx.layout(), f.state.id()).unwrap()).unwrap(),
            f.old_bytes
        );
        let state = recover(&f.ctx, &f.ticket, |_| Ok(())).unwrap();
        assert!(!state.dirty());
        assert_eq!(
            fs::read(path(&state).unwrap().join("target.py")).unwrap(),
            b"original"
        );
        assert!(state
            .verified
            .protected
            .get(Path::new("e"))
            .unwrap()
            .contains_key(Path::new("g2222222222222222/partial.dll")));
        assert_no_preserved_pending(&f.ctx.layout().root).unwrap();
        // 后续合法修复拥有新generation，不应重新激活已恢复的历史pending。
        let next = begin(
            &f.ctx,
            &plan(
                &f.ctx,
                state.id(),
                state.generation(),
                &["target.py".into()],
            )
            .unwrap(),
        )
        .unwrap();
        assert_no_preserved_pending(&f.ctx.layout().root).unwrap();
        recover(&f.ctx, &next, |_| Ok(())).unwrap();
        assert_no_preserved_pending(&f.ctx.layout().root).unwrap();
    }
    #[test]
    fn legacy_pending_with_absent_e_baseline_recovers_after_partial_orphan() {
        let f = Fixture::new(0, true);
        f.seal("orphaned");
        assert_eq!(
            fs::read(state_path(f.ctx.layout(), f.state.id()).unwrap()).unwrap(),
            f.old_bytes
        );
        let state = recover(&f.ctx, &f.ticket, |_| Ok(())).unwrap();
        assert!(!state.dirty());
        assert!(state.verified.protected.contains_key(Path::new("e")));
        assert!(load(f.ctx.layout(), "g2222222222222222").unwrap().dirty());
    }
    #[test]
    fn legacy_pending_with_empty_e_baseline_recovers_after_orphan() {
        let f = Fixture::new(0, false);
        f.seal("orphaned");
        assert!(recover(&f.ctx, &f.ticket, |_| Ok(())).is_ok());
    }
    #[test]
    fn changed_new_subtree_or_unknown_added_sibling_never_relaxes_old_pending() {
        let f = Fixture::new(1, false);
        f.seal("orphaned");
        fs::write(
            f.ctx.layout().root.join("e/g2222222222222222/partial.dll"),
            b"foreign",
        )
        .unwrap();
        assert!(recover(&f.ctx, &f.ticket, |_| Ok(())).is_err());
        assert_eq!(
            fs::read(state_path(f.ctx.layout(), f.state.id()).unwrap()).unwrap(),
            f.old_bytes
        );
        fs::write(
            f.ctx.layout().root.join("e/g2222222222222222/partial.dll"),
            b"candidate-original",
        )
        .unwrap();
        fs::create_dir(f.ctx.layout().root.join("e/g3333333333333333")).unwrap();
        assert!(recover(&f.ctx, &f.ticket, |_| Ok(())).is_err());
        assert_eq!(
            fs::read(path(&f.state).unwrap().join("target.py")).unwrap(),
            b"damaged"
        );
    }
    #[test]
    fn altered_preservation_or_unknown_authority_schema_is_rejected() {
        let f = Fixture::new(1, false);
        let tx = f.seal("orphaned");
        let p =
            f.ctx
                .layout()
                .root
                .join("backups")
                .join(&tx)
                .join(format!("preservation-{}.json", {
                    let p = f
                        .ctx
                        .layout()
                        .root
                        .join("state/gui-rebuild")
                        .join(format!("{tx}.json"));
                    let a: StoredRebuildIntent =
                        serde_json::from_slice(&fs::read(p).unwrap()).unwrap();
                    a.preservation_sha256.unwrap()
                }));
        let bytes = fs::read(&p).unwrap();
        fs::write(&p, b"{}").unwrap();
        assert!(recover(&f.ctx, &f.ticket, |_| Ok(())).is_err());
        fs::write(&p, bytes).unwrap();
        let p = f
            .ctx
            .layout()
            .root
            .join("state/gui-rebuild")
            .join(format!("{tx}.json"));
        let mut value: serde_json::Value = serde_json::from_slice(&fs::read(&p).unwrap()).unwrap();
        value["schema_version"] = 99.into();
        fs::write(&p, serde_json::to_vec(&value).unwrap()).unwrap();
        assert!(recover(&f.ctx, &f.ticket, |_| Ok(())).is_err());
    }
    #[test]
    fn gui_pending_recovery_projects_owned_large_engine_without_rewriting_old_baseline() {
        let f = Fixture::new(1, false);
        let root = &f.ctx.layout().root;
        let engine = "kohya";
        let id = "t0123456789abcde";
        let raw = crate::core::embedded_engine_lock(engine).unwrap();
        let lock: serde_json::Value = serde_json::from_slice(raw).unwrap();
        let owner = root
            .join("state/engines")
            .join(f.state.release_id())
            .join(engine);
        let environment = root.join("e").join(id);
        fs::create_dir(&environment).unwrap();
        let payload = File::create(environment.join("large-torch.dll")).unwrap();
        #[cfg(windows)]
        {
            use std::os::windows::io::AsRawHandle;
            #[link(name = "kernel32")]
            unsafe extern "system" {
                fn DeviceIoControl(
                    handle: *mut std::ffi::c_void,
                    code: u32,
                    input: *mut std::ffi::c_void,
                    input_bytes: u32,
                    output: *mut std::ffi::c_void,
                    output_bytes: u32,
                    returned: *mut u32,
                    overlapped: *mut std::ffi::c_void,
                ) -> i32;
            }
            let mut returned = 0;
            assert_ne!(
                unsafe {
                    DeviceIoControl(
                        payload.as_raw_handle(),
                        0x900c4,
                        std::ptr::null_mut(),
                        0,
                        std::ptr::null_mut(),
                        0,
                        &mut returned,
                        std::ptr::null_mut(),
                    )
                },
                0
            );
        }
        payload.set_len(5 * 1024 * 1024 * 1024).unwrap();
        drop(payload);
        let write_engine = |generation| {
            let receipt = serde_json::json!({"schema_version":1,"release_id":f.state.release_id(),"engine_id":engine,"profile_id":"default","instance_id":id,"generation":generation,"recipe_sha256":lock["recipe_sha256"],"lock_sha256":hash(raw),"files":{"environment":{},"source":lock["source"]["files"]},"base_python_files":lock["python"]["files"]});
            let receipt_path = owner
                .join("instances")
                .join(id)
                .join(format!("{generation}.json"));
            model::write_json_atomic(&receipt_path, &receipt).unwrap();
            let state = serde_json::json!({"schema_version":1,"release_id":f.state.release_id(),"engine_id":engine,"profile_id":"default","instance_id":id,"generation":generation,"validated_generation":generation,"recipe_sha256":lock["recipe_sha256"],"lock_sha256":hash(raw),"python_version":lock["python"]["version"],"environment_root":environment,"source_root":root.join("s").join(id),"python_root":root.join("p").join(id),"status":"ready","dirty":false,"pending":null,"receipt_relative":format!("instances/{id}/{generation}.json"),"receipt_sha256":hash(&fs::read(receipt_path).unwrap())});
            model::write_json_atomic(&owner.join("state.json"), &state).unwrap();
        };
        write_engine(1);
        let before = engine_control_digest(f.ctx.layout()).unwrap();
        assert_eq!(
            fs::read(state_path(f.ctx.layout(), f.state.id()).unwrap()).unwrap(),
            f.old_bytes
        );
        let ticket = reload_ticket(f.ctx.layout(), f.state.id()).unwrap();
        let recovered = recover(&f.ctx, &ticket, |_| Ok(())).unwrap();
        assert!(!recovered.dirty());
        assert_eq!(engine_control_digest(f.ctx.layout()).unwrap(), before);
        assert_eq!(
            fs::metadata(environment.join("large-torch.dll"))
                .unwrap()
                .len(),
            5 * 1024 * 1024 * 1024
        );
        write_engine(2);
        // 引擎在两次GUI操作之间合法修复，不使GUI基线绑定旧引擎代次。
        assert!(plan(
            &f.ctx,
            recovered.id(),
            recovered.generation(),
            &["target.py".into()]
        )
        .is_ok());
        fs::create_dir(root.join("e/t111111111111111")).unwrap();
        assert!(plan(
            &f.ctx,
            recovered.id(),
            recovered.generation(),
            &["target.py".into()]
        )
        .is_err());
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Fingerprint {
    bytes: u64,
    sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(
    tag = "kind",
    content = "fingerprint",
    rename_all = "snake_case",
    deny_unknown_fields
)]
enum Node {
    Directory,
    File(Fingerprint),
    PythonAlias(PathBuf),
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Observation {
    environment: Tree,
    profiles: Tree,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    profiles_summary: Option<ProfilesSummary>,
    protected: BTreeMap<PathBuf, Tree>,
}

/// 只读资料树的流式内容承诺；不将百万路径复制到每个32MiB实例记录。
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct ProfilesSummary {
    schema_version: u32,
    exists: bool,
    nodes: u64,
    files: u64,
    bytes: u64,
    sha256: String,
}

struct ProfileBudget<'a> {
    cancel: &'a CancelToken,
    deadline: Instant,
    max_bytes: u64,
    max_nodes: u64,
    bytes: u64,
    nodes: u64,
    files: u64,
    discovered: u64,
    path_bytes: u64,
}
impl<'a> ProfileBudget<'a> {
    fn new(cancel: &'a CancelToken) -> Self {
        Self {
            cancel,
            deadline: Instant::now() + Duration::from_secs(900),
            max_bytes: MAX_PROFILE_BYTES,
            max_nodes: MAX_PROFILE_NODES,
            bytes: 0,
            nodes: 0,
            files: 0,
            discovered: 1,
            path_bytes: 0,
        }
    }
    fn check(&self) -> Result<()> {
        self.cancel.check()?;
        if Instant::now() >= self.deadline {
            bail!("资料内容扫描超过900秒预算，未授权变更");
        }
        Ok(())
    }
    fn node(&mut self) -> Result<()> {
        self.check()?;
        self.nodes = self.nodes.checked_add(1).context("资料节点数溢出")?;
        if self.nodes > self.max_nodes {
            bail!("资料内容扫描超过节点预算");
        }
        Ok(())
    }
}

fn profile_file_digest(bytes: u64, sha256: &str) -> String {
    let mut hash = Sha256::new();
    hash.update(b"next-trainer/profile-file/v1\0");
    hash.update(bytes.to_le_bytes());
    hash.update(sha256.as_bytes());
    format!("{:x}", hash.finalize())
}
fn profile_directory_digest(children: &[(String, bool, String)]) -> String {
    let mut hash = Sha256::new();
    hash.update(b"next-trainer/profile-directory/v1\0");
    hash.update((children.len() as u64).to_le_bytes());
    for (name, directory, digest) in children {
        hash.update((name.len() as u64).to_le_bytes());
        hash.update(name.as_bytes());
        hash.update([u8::from(*directory)]);
        hash.update(digest.as_bytes());
    }
    format!("{:x}", hash.finalize())
}
fn absent_profiles() -> ProfilesSummary {
    ProfilesSummary {
        schema_version: 1,
        exists: false,
        nodes: 0,
        files: 0,
        bytes: 0,
        sha256: hash(b"next-trainer/profile-missing/v1\0"),
    }
}

fn profile_stream_file(
    layout: &Layout,
    path: &Path,
    budget: &mut ProfileBudget<'_>,
) -> Result<Fingerprint> {
    budget.check()?;
    layout.guard_path(path)?;
    let before = fs::symlink_metadata(path)?;
    if !before.is_file() {
        bail!("资料内容保护只接受普通文件");
    }
    if budget
        .bytes
        .checked_add(before.len())
        .is_none_or(|bytes| bytes > budget.max_bytes)
    {
        bail!("资料内容扫描超过独立字节预算");
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(windows)]
    {
        use std::os::windows::fs::OpenOptionsExt;
        // 扫描期间禁止新写入/删除句柄；已有写入者会导致打开失败而不是得到混合摘要。
        options.share_mode(1);
    }
    let mut input = options.open(path)?;
    let opened = input.metadata()?;
    if !opened.is_file() || opened.len() != before.len() {
        bail!("资料文件打开期间发生变化");
    }
    let mut digest = Sha256::new();
    let mut bytes = 0u64;
    let mut buffer = [0; 65_536];
    loop {
        budget.check()?;
        let count = input.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        bytes = bytes
            .checked_add(count as u64)
            .context("资料文件长度溢出")?;
        budget.bytes = budget
            .bytes
            .checked_add(count as u64)
            .context("资料树长度溢出")?;
        if bytes > opened.len() || budget.bytes > budget.max_bytes {
            bail!("资料扫描长度变化或超出独立字节预算");
        }
        digest.update(&buffer[..count]);
    }
    layout.guard_path(path)?;
    let after = fs::symlink_metadata(path)?;
    let handle_after = input.metadata()?;
    if !after.is_file()
        || bytes != opened.len()
        || after.len() != bytes
        || handle_after.len() != bytes
        || opened.modified().ok() != handle_after.modified().ok()
        || opened.modified().ok() != after.modified().ok()
    {
        bail!("资料文件扫描期间发生变化");
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if (opened.dev(), opened.ino()) != (after.dev(), after.ino()) {
            bail!("资料路径在扫描期间被替换");
        }
    }
    budget.files = budget.files.checked_add(1).context("资料文件数溢出")?;
    Ok(Fingerprint {
        bytes,
        sha256: format!("{:x}", digest.finalize()),
    })
}

fn profile_summary(
    layout: &Layout,
    base: &Path,
    budget: &mut ProfileBudget<'_>,
) -> Result<ProfilesSummary> {
    profile_scan(layout, base, budget, None)
}

/// 固定资料根的内容摘要，可供源码修复等只读保护闭包复用；每次调用有独立预算。
pub(crate) fn summarize_profiles(layout: &Layout, cancel: &CancelToken) -> Result<ProfilesSummary> {
    profile_summary(
        layout,
        &layout.root.join("profiles"),
        &mut ProfileBudget::new(cancel),
    )
}

fn profile_scan(
    layout: &Layout,
    base: &Path,
    budget: &mut ProfileBudget<'_>,
    mut legacy: Option<&mut Tree>,
) -> Result<ProfilesSummary> {
    fn walk(
        layout: &Layout,
        base: &Path,
        path: &Path,
        depth: usize,
        budget: &mut ProfileBudget<'_>,
        legacy: &mut Option<&mut Tree>,
    ) -> Result<(bool, String)> {
        budget.node()?;
        if legacy.is_none() && depth > MAX_PROFILE_DEPTH {
            bail!("资料目录深度超过128层预算");
        }
        layout.guard_path(path)?;
        let metadata = fs::symlink_metadata(path)?;
        if !metadata.is_dir() {
            if legacy.is_some() && metadata.len() > MAX_FILE {
                bail!("旧事务资料文件超出原快照合同，保留待恢复状态");
            }
            let value = profile_stream_file(layout, path, budget)?;
            let digest = profile_file_digest(value.bytes, &value.sha256);
            if let Some(tree) = legacy.as_deref_mut() {
                tree.insert(path.strip_prefix(base)?.to_owned(), Node::File(value));
            }
            return Ok((false, digest));
        }
        if let Some(tree) = legacy.as_deref_mut() {
            tree.insert(path.strip_prefix(base)?.to_owned(), Node::Directory);
        }
        fn list(
            path: &Path,
            budget: &mut ProfileBudget<'_>,
            discover: bool,
        ) -> Result<Vec<(String, PathBuf)>> {
            let mut entries = Vec::new();
            let mut aliases = BTreeSet::new();
            for entry in fs::read_dir(path)? {
                budget.check()?;
                let entry = entry?;
                let name = entry
                    .file_name()
                    .into_string()
                    .map_err(|_| anyhow::anyhow!("资料路径不是UTF-8"))?;
                model::validate_component(&name)?;
                if !aliases.insert(name.to_lowercase()) {
                    bail!("资料目录存在大小写别名");
                }
                let child = entry.path();
                if discover {
                    budget.discovered =
                        budget.discovered.checked_add(1).context("资料路径数溢出")?;
                    budget.path_bytes = budget
                        .path_bytes
                        .checked_add(
                            (child.as_os_str().as_encoded_bytes().len() + name.len()) as u64,
                        )
                        .context("资料路径长度溢出")?;
                    if budget.discovered > budget.max_nodes
                        || budget.path_bytes > MAX_PROFILE_PATH_BYTES
                    {
                        bail!("资料扫描超过独立节点或256MiB路径预算");
                    }
                }
                entries.push((name, child));
                if entries.len() > MAX_PROFILE_DIRECTORY_ENTRIES {
                    bail!("资料单目录超过10万项预算");
                }
            }
            entries.sort_by(|left, right| left.0.cmp(&right.0));
            Ok(entries)
        }
        let entries = list(path, budget, true)?;
        let mut children = Vec::with_capacity(entries.len());
        for (name, child) in &entries {
            let (directory, digest) = walk(layout, base, child, depth + 1, budget, legacy)?;
            children.push((name.clone(), directory, digest));
        }
        layout.guard_path(path)?;
        if entries != list(path, budget, false)? {
            bail!("资料目录在扫描期间增加、删除或重命名");
        }
        Ok((true, profile_directory_digest(&children)))
    }
    budget.check()?;
    layout.guard_path(base)?;
    if !base.try_exists()? {
        return Ok(absent_profiles());
    }
    if !fs::symlink_metadata(base)?.is_dir() {
        bail!("资料根不是普通目录");
    }
    let (_, sha256) = walk(layout, base, base, 0, budget, &mut legacy)?;
    Ok(ProfilesSummary {
        schema_version: 1,
        exists: true,
        nodes: budget.nodes,
        files: budget.files,
        bytes: budget.bytes,
        sha256,
    })
}

fn legacy_profile_tree(layout: &Layout, base: &Path, cancel: &CancelToken) -> Result<Tree> {
    let mut budget = ProfileBudget::new(cancel);
    budget.max_bytes = MAX_TREE;
    budget.max_nodes = 50_000;
    let mut tree = Tree::new();
    profile_scan(layout, base, &mut budget, Some(&mut tree))?;
    Ok(tree)
}

fn legacy_profiles_summary(tree: &Tree) -> Result<ProfilesSummary> {
    if tree.is_empty() {
        return Ok(absent_profiles());
    }
    if !matches!(tree.get(Path::new("")), Some(Node::Directory)) {
        bail!("旧资料树根不是目录");
    }
    let mut result = ProfilesSummary {
        schema_version: 1,
        exists: true,
        nodes: tree.len() as u64,
        files: 0,
        bytes: 0,
        sha256: String::new(),
    };
    // 按深度倒序聚合，每条路径只参与一次，旧记录不额外引入递归深度合同。
    let mut paths: Vec<_> = tree.keys().collect();
    paths.sort_by_key(|path| std::cmp::Reverse(path.components().count()));
    let mut children: BTreeMap<PathBuf, Vec<(String, bool, String)>> = BTreeMap::new();
    for path in paths {
        let (directory, digest) = match &tree[path] {
            Node::File(value) => {
                result.files += 1;
                result.bytes = result
                    .bytes
                    .checked_add(value.bytes)
                    .context("旧资料树长度溢出")?;
                (false, profile_file_digest(value.bytes, &value.sha256))
            }
            Node::Directory => {
                let mut values = children.remove(path).unwrap_or_default();
                values.sort_by(|left, right| left.0.cmp(&right.0));
                (true, profile_directory_digest(&values))
            }
            Node::PythonAlias(_) => bail!("资料合同不允许Python联接"),
        };
        if path.as_os_str().is_empty() {
            result.sha256 = digest;
        } else {
            let parent = path.parent().context("旧资料树缺少父目录")?;
            if !matches!(tree.get(parent), Some(Node::Directory)) {
                bail!("旧资料树父节点不是目录");
            }
            let name = path
                .file_name()
                .and_then(|name| name.to_str())
                .context("旧资料路径不是UTF-8")?
                .to_owned();
            children
                .entry(parent.to_owned())
                .or_default()
                .push((name, directory, digest));
        }
    }
    Ok(result)
}
fn profiles_equal(before: &Observation, after: &Observation) -> Result<bool> {
    let summarize = |value: &Observation| -> Result<ProfilesSummary> {
        value
            .profiles_summary
            .clone()
            .map(Ok)
            .unwrap_or_else(|| legacy_profiles_summary(&value.profiles))
    };
    Ok(summarize(before)? == summarize(after)?)
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Pending {
    instance_id: String,
    generation: u64,
    base_generation: u64,
    recipe_sha256: String,
    tree_sha256: String,
    directory: PathBuf,
    files: BTreeMap<PathBuf, Option<Fingerprint>>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub(crate) struct InstanceState {
    schema_version: u32,
    component: String,
    instance_id: String,
    #[serde(default, skip_serializing_if = "model::legacy_storage_version")]
    storage_version: u32,
    release_id: String,
    root_absolute: PathBuf,
    recipe_id: String,
    recipe_sha256: String,
    generation: u64,
    validated_generation: u64,
    dirty: bool,
    ignored: Vec<PathBuf>,
    verified: Observation,
    pending: Option<Pending>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    base_python_pending: Option<BasePythonPending>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    registration_origin: Option<RegistrationOrigin>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct RegistrationOrigin {
    transaction: String,
    trusted_index_sha256: String,
    independently_verified_closure_sha256: String,
    observed_at: u64,
    previous_known_generation: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct BasePythonPending {
    transaction: String,
    previous_generation: u64,
    initial_dirty: bool,
    previous_state_sha256: String,
    previous_schema_version: u32,
}
pub(crate) struct RepairPlan {
    state: InstanceState,
    paths: Vec<PathBuf>,
    diagnosed: Observation,
}
pub(crate) struct MutationTicket {
    state: InstanceState,
    engine_controls: String,
}

impl InstanceState {
    pub(crate) fn id(&self) -> &str {
        &self.instance_id
    }
    pub(crate) fn storage_version(&self) -> u32 {
        self.storage_version
    }
    pub(crate) fn release_id(&self) -> &str {
        &self.release_id
    }
    pub(crate) fn generation(&self) -> u64 {
        self.generation
    }
    pub(crate) fn dirty(&self) -> bool {
        self.dirty
    }
    pub(crate) fn recipe_id(&self) -> &str {
        &self.recipe_id
    }
    pub(crate) fn recipe_sha256(&self) -> &str {
        &self.recipe_sha256
    }
}
fn release(layout: &Layout) -> Result<&str> {
    layout
        .release_dir
        .file_name()
        .and_then(|name| name.to_str())
        .context("缺少release身份")
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn valid_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}
fn relative(path: &Path) -> Result<()> {
    if path.as_os_str().is_empty() || path.is_absolute() {
        bail!("实例路径必须为非空相对路径");
    }
    for part in path.components() {
        match part {
            Component::Normal(name) => {
                model::validate_component(name.to_str().context("路径不是UTF-8")?)?
            }
            _ => bail!("实例路径不允许跳转或盘符"),
        }
    }
    Ok(())
}
fn state_path(layout: &Layout, id: &str) -> Result<PathBuf> {
    model::validate_component(id)?;
    let path = layout
        .root
        .join("state/instances")
        .join(format!("{id}.json"));
    layout.guard_path(&path)?;
    Ok(path)
}
pub(crate) fn path(state: &InstanceState) -> Result<PathBuf> {
    let layout = Layout::new(&state.root_absolute, &state.release_id)?;
    let path = model::environment_path(
        &layout.root,
        &state.release_id,
        &state.instance_id,
        state.storage_version,
    )?;
    layout.guard_path(&path)?;
    Ok(path)
}
fn fingerprint(layout: &Layout, path: &Path) -> Result<Fingerprint> {
    layout.guard_path(path)?;
    let meta = fs::symlink_metadata(path)?;
    if !meta.is_file() || meta.len() > MAX_FILE {
        bail!("实例只接受受限普通文件");
    }
    let mut input = File::open(path)?;
    let mut digest = Sha256::new();
    let mut total = 0u64;
    let mut buffer = [0; 65536];
    loop {
        let count = input.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        total += count as u64;
        if total > MAX_FILE {
            bail!("实例文件读取超限");
        }
        digest.update(&buffer[..count]);
    }
    Ok(Fingerprint {
        bytes: total,
        sha256: format!("{:x}", digest.finalize()),
    })
}
fn ignored(paths: &[PathBuf], path: &Path) -> bool {
    paths.iter().any(|ignored| path.starts_with(ignored))
}
fn windows_key(path: &Path) -> String {
    path.to_string_lossy()
        .replace('\\', "/")
        .to_ascii_lowercase()
}
fn scan(layout: &Layout, base: &Path, ignores: &[PathBuf]) -> Result<Tree> {
    if base == layout.root.join("e") {
        let mut excluded = ignores.to_vec();
        excluded.extend(engine_namespaces::capture(layout)?.excluded);
        scan_tree(layout, base, &excluded, None)
    } else {
        scan_tree(layout, base, ignores, None)
    }
}
fn python_alias_node(layout: &Layout, alias: &Path, target: &Path) -> Result<Node> {
    layout.guard_path(alias.parent().context("Python别名缺少父目录")?)?;
    layout.guard_path(target)?;
    #[cfg(windows)]
    {
        if !junction::exists(alias)?
            || junction::get_target(alias)?.canonicalize()? != target.canonicalize()?
            || !target.is_dir()
        {
            bail!("Python minor别名未指向同根固定patch目录");
        }
        Ok(Node::PythonAlias(
            target.strip_prefix(&layout.root)?.to_path_buf(),
        ))
    }
    #[cfg(not(windows))]
    bail!("Python minor junction仅在Windows允许")
}
fn scan_tree(
    layout: &Layout,
    base: &Path,
    ignores: &[PathBuf],
    python_alias: Option<(&Path, &Path)>,
) -> Result<Tree> {
    struct Options<'a> {
        ignores: &'a [PathBuf],
        python_alias: Option<(&'a Path, &'a Path)>,
    }
    fn walk(
        layout: &Layout,
        base: &Path,
        current: &Path,
        options: &Options<'_>,
        tree: &mut Tree,
        total: &mut u64,
        aliases: &mut BTreeSet<String>,
    ) -> Result<()> {
        if let Some((alias, target)) = options.python_alias {
            if current == alias {
                tree.insert(
                    current.strip_prefix(base)?.to_path_buf(),
                    python_alias_node(layout, alias, target)?,
                );
                return Ok(());
            }
        }
        layout.guard_path(current)?;
        let rel = current.strip_prefix(base)?.to_path_buf();
        if !rel.as_os_str().is_empty() && ignored(options.ignores, &rel) {
            return Ok(());
        }
        if !aliases.insert(
            rel.to_string_lossy()
                .replace('\\', "/")
                .to_ascii_lowercase(),
        ) {
            bail!("实例树存在大小写别名");
        }
        let meta = fs::symlink_metadata(current)?;
        let node = if meta.is_dir() {
            Node::Directory
        } else {
            let digest = fingerprint(layout, current)?;
            *total = total.checked_add(digest.bytes).context("实例树长度溢出")?;
            Node::File(digest)
        };
        tree.insert(rel, node);
        if tree.len() > 50_000 || *total > MAX_TREE {
            bail!("实例树超出验证上限");
        }
        if meta.is_dir() {
            for entry in fs::read_dir(current)? {
                walk(layout, base, &entry?.path(), options, tree, total, aliases)?;
            }
        }
        Ok(())
    }
    layout.guard_path(base)?;
    let mut tree = Tree::new();
    if base.exists() {
        walk(
            layout,
            base,
            base,
            &Options {
                ignores,
                python_alias,
            },
            &mut tree,
            &mut 0,
            &mut BTreeSet::new(),
        )?;
    }
    Ok(tree)
}
fn python_tree(layout: &Layout) -> Result<Tree> {
    let python = layout.root.join("python/3.10.19");
    let alias = python.join("cpython-3.10-windows-x86_64-none");
    let target = python.join("cpython-3.10.19-windows-x86_64-none");
    scan_tree(layout, &python, &[], Some((&alias, &target)))
}
fn observe(layout: &Layout, state: &InstanceState, cancel: &CancelToken) -> Result<Observation> {
    cancel.check()?;
    let current = path(state)?;
    let mut protected = BTreeMap::new();
    for root in [&layout.release_dir, &layout.root.join("tools/uv.exe")] {
        protected.insert(
            root.strip_prefix(&layout.root)?.to_path_buf(),
            scan(layout, root, &[])?,
        );
    }
    protected.insert(PathBuf::from("python/3.10.19"), python_tree(layout)?);
    for container in ["environments", "e"] {
        let base = layout.root.join(container);
        let excluded = match state.storage_version {
            0 if container == "environments" => Some(
                current
                    .parent()
                    .context("GUI实例缺少父目录")?
                    .strip_prefix(&base)?
                    .to_path_buf(),
            ),
            1 if container == "e" => Some(current.strip_prefix(&base)?.to_path_buf()),
            _ => None,
        };
        let mut tree = scan(layout, &base, &excluded.into_iter().collect::<Vec<_>>())?;
        if container == "e" {
            project_rebuild_extensions(layout, state, &mut tree)?;
            if state.pending.is_some()
                && state
                    .verified
                    .protected
                    .get(Path::new("e"))
                    .is_none_or(BTreeMap::is_empty)
                && tree == Tree::from([(PathBuf::new(), Node::Directory)])
            {
                tree.clear();
            }
        }
        if container == "e"
            && state.storage_version == 0
            && state.pending.is_some()
            && !state.verified.protected.contains_key(Path::new("e"))
        {
            // 旧 dirty 事务不能追认过去未保护的新容器。只有 e 仍为空时才沿原合同恢复。
            if tree.keys().any(|path| !path.as_os_str().is_empty()) {
                bail!("旧实例事务未记录短路径环境保护树，且 e 已含内容；保留 dirty 与快照");
            }
        } else {
            protected.insert(PathBuf::from(container), tree);
        }
    }
    // 旧 dirty 快照仍绑定原序列化树，恢复成功前不能改写它的摘要合同。
    let (profiles, profiles_summary) =
        if state.pending.is_some() && state.verified.profiles_summary.is_none() {
            (
                legacy_profile_tree(layout, &layout.root.join("profiles"), cancel)?,
                None,
            )
        } else {
            let summary = summarize_profiles(layout, cancel)?;
            (Tree::new(), Some(summary))
        };
    cancel.check()?;
    Ok(Observation {
        environment: scan(layout, &path(state)?, &state.ignored)?,
        profiles,
        profiles_summary,
        protected,
    })
}
fn validate(layout: &Layout, id: &str, state: &InstanceState) -> Result<()> {
    if !matches!(state.schema_version, 2 | 3)
        || state.component != "gui"
        || state.instance_id != id
        || state.root_absolute != layout.root
        || state.release_id != release(layout)?
        || state.generation == 0
        || !valid_hash(&state.recipe_sha256)
    {
        bail!("实例schema或持久身份不支持，保留原记录");
    }
    model::validate_component(&state.recipe_id)?;
    if let Some(origin) = &state.registration_origin {
        model::validate_component(&origin.transaction)?;
        if state.schema_version != 3
            || !origin.transaction.starts_with("gui-registration-")
            || !valid_hash(&origin.trusted_index_sha256)
            || !valid_hash(&origin.independently_verified_closure_sha256)
            || origin.observed_at == 0
            || origin.previous_known_generation >= state.generation
        {
            bail!("登记恢复的独立验证epoch身份无效");
        }
    }
    let environment = path(state)?;
    if let Some(binding) = model::Registry::load(&layout.root)?.gui_binding(&state.release_id) {
        if binding.instance_id == state.instance_id
            && binding.storage_version != state.storage_version
        {
            bail!("实例存储版本与既有绑定不一致，拒绝重新解释环境路径");
        }
    }
    let alternate_storage = 1 - state.storage_version;
    if let Ok(alternate) = model::environment_path(
        &layout.root,
        &state.release_id,
        state.id(),
        alternate_storage,
    ) {
        if alternate.exists() {
            bail!("同一实例 ID 在另一存储命名空间已有目录，拒绝切换路径解释");
        }
    }
    layout.guard_path(&environment)?;
    for ignore in &state.ignored {
        relative(ignore)?;
        if !matches!(
            ignore.file_name().and_then(|value| value.to_str()),
            Some("__pycache__" | "logs")
        ) && ignore.extension().is_none_or(|value| value != "pyc")
        {
            bail!("忽略清单只接受显式pyc、__pycache__或logs路径");
        }
    }
    let mut roots: BTreeSet<_> = [
        layout.release_dir.strip_prefix(&layout.root)?.to_path_buf(),
        PathBuf::from("tools/uv.exe"),
        PathBuf::from("python/3.10.19"),
        PathBuf::from("environments"),
    ]
    .into_iter()
    .collect();
    if state.storage_version == 1 || state.verified.protected.contains_key(Path::new("e")) {
        roots.insert(PathBuf::from("e"));
    }
    if state
        .verified
        .protected
        .keys()
        .cloned()
        .collect::<BTreeSet<_>>()
        != roots
    {
        bail!("实例缺少固定非目标组件保护树");
    }
    for root in state.verified.protected.keys() {
        relative(root)?;
        layout.guard_path(&layout.root.join(root))?;
    }
    if let Some(summary) = &state.verified.profiles_summary {
        if !state.verified.profiles.is_empty()
            || summary.schema_version != 1
            || !valid_hash(&summary.sha256)
            || summary.nodes > MAX_PROFILE_NODES
            || summary.bytes > MAX_PROFILE_BYTES
            || summary.files == 0 && summary.bytes != 0
            || summary.files >= summary.nodes && summary.exists
            || summary.exists && summary.nodes == 0
            || !summary.exists && *summary != absent_profiles()
        {
            bail!("资料内容摘要无效或与旧资料树混用");
        }
    }
    for tree in [&state.verified.environment, &state.verified.profiles]
        .into_iter()
        .chain(state.verified.protected.values())
    {
        for (rel, node) in tree {
            if !rel.as_os_str().is_empty() {
                relative(rel)?;
            }
            if let Node::File(value) = node {
                if value.bytes > MAX_FILE || !valid_hash(&value.sha256) {
                    bail!("实例树摘要无效");
                }
            }
            if let Node::PythonAlias(target) = node {
                relative(target)?;
            }
        }
    }
    if let Some(pending) = &state.base_python_pending {
        model::validate_component(&pending.transaction)?;
        if state.schema_version != 3
            || !state.dirty
            || state.pending.is_some()
            || !pending.transaction.starts_with("base-python-")
            || !valid_hash(&pending.previous_state_sha256)
            || !matches!(pending.previous_schema_version, 2 | 3)
            || if pending.initial_dirty {
                state.generation != 1
                    || state.validated_generation != 0
                    || pending.previous_generation != 1
            } else {
                pending.previous_generation != state.validated_generation
                    || pending.previous_generation.checked_add(1) != Some(state.generation)
            }
        {
            bail!("基础Python引用事务状态无效，保持停用");
        }
        return Ok(());
    }
    match (&state.pending, state.dirty) {
        (None, true) if state.generation == 1 && state.validated_generation == 0 => {}
        (None, false) if state.generation == state.validated_generation => {}
        (Some(pending), true)
            if pending.instance_id == id
                && pending.generation == state.generation
                && pending.base_generation == state.validated_generation
                && pending.base_generation.checked_add(1) == Some(state.generation)
                && pending.recipe_sha256 == state.recipe_sha256
                && pending.tree_sha256 == hash(&serde_json::to_vec(&state.verified)?) =>
        {
            relative(&pending.directory)?;
            let prefix = Path::new("backups/gui-instances").join(id);
            if !pending.directory.starts_with(&prefix)
                || pending.directory.components().count() != prefix.components().count() + 1
                || !pending
                    .directory
                    .file_name()
                    .and_then(|name| name.to_str())
                    .is_some_and(|name| {
                        name.starts_with(&format!("generation-{}-", state.generation))
                    })
            {
                bail!("实例快照路径身份无效");
            }
            layout.guard_path(&layout.root.join(&pending.directory))?;
            validate_paths(state, &pending.files.keys().cloned().collect::<Vec<_>>())?;
            for (rel, original) in &pending.files {
                if state.verified.environment.get(rel)
                    != original
                        .as_ref()
                        .map(|value| Node::File(value.clone()))
                        .as_ref()
                {
                    bail!("快照文件与诊断树不一致");
                }
            }
        }
        _ => bail!("实例dirty/generation/事务状态不一致"),
    }
    Ok(())
}
pub(crate) fn load(layout: &Layout, id: &str) -> Result<InstanceState> {
    let target = state_path(layout, id)?;
    if fs::metadata(&target)?.len() > MAX_STATE {
        bail!("实例记录过大");
    }
    let state: InstanceState = serde_json::from_slice(&fs::read(target)?)?;
    validate(layout, id, &state)?;
    Ok(state)
}
fn save(layout: &Layout, state: &InstanceState) -> Result<()> {
    validate(layout, &state.instance_id, state)?;
    // 实际写出使用pretty JSON并追加换行；按真实编码限额才能保证重启可读。
    if serde_json::to_vec_pretty(state)?.len() as u64 + 1 > MAX_STATE {
        bail!("实例记录超过可重读上限");
    }
    model::write_json_atomic(&state_path(layout, &state.instance_id)?, state)
}
fn save_for_base(layout: &Layout, state: &InstanceState, transaction: &str) -> Result<()> {
    validate(layout, &state.instance_id, state)?;
    if serde_json::to_vec_pretty(state)?.len() as u64 + 1 > MAX_STATE {
        bail!("实例记录超过可重读上限");
    }
    model::write_base_json_atomic(
        &layout.root,
        transaction,
        &state_path(layout, &state.instance_id)?,
        state,
    )
}
#[cfg(test)]
pub(crate) fn create(
    ctx: &WorkspaceMutation,
    id: &str,
    recipe_id: &str,
    recipe_sha256: &str,
) -> Result<InstanceState> {
    create_controlled(ctx, id, recipe_id, recipe_sha256, &CancelToken::new())
}
pub(crate) fn create_controlled(
    ctx: &WorkspaceMutation,
    id: &str,
    recipe_id: &str,
    recipe_sha256: &str,
    cancel: &CancelToken,
) -> Result<InstanceState> {
    cancel.check()?;
    let layout = ctx.layout();
    let target = state_path(layout, id)?;
    if target.exists() {
        let _ = load(layout, id)?;
        bail!("实例ID已经存在，拒绝覆盖");
    }
    model::validate_component(recipe_id)?;
    if !valid_hash(recipe_sha256) {
        bail!("配方SHA256无效");
    }
    let mut state = InstanceState {
        schema_version: 2,
        component: "gui".into(),
        instance_id: id.into(),
        storage_version: 1,
        release_id: release(layout)?.into(),
        root_absolute: layout.root.clone(),
        recipe_id: recipe_id.into(),
        recipe_sha256: recipe_sha256.into(),
        generation: 1,
        validated_generation: 0,
        dirty: true,
        ignored: vec![],
        verified: Observation {
            environment: Tree::new(),
            profiles: Tree::new(),
            profiles_summary: None,
            protected: BTreeMap::new(),
        },
        pending: None,
        base_python_pending: None,
        registration_origin: None,
    };
    let environment = path(&state)?;
    if model::environment_path(&layout.root, release(layout)?, id, 0)?.exists() {
        bail!("同一实例 ID 的旧环境目录已存在，拒绝为它创建短路径别名");
    }
    let parent = environment.parent().context("实例缺少父目录")?;
    layout.ensure_dir(parent)?;
    // 原子目录创建独占短 ID；state 或物理目录任一重名都拒绝覆盖。
    fs::create_dir(&environment)?;
    state.verified = observe(layout, &state, cancel)?;
    save(layout, &state)?;
    Ok(state)
}
pub(crate) fn assert_usable(state: &InstanceState) -> Result<()> {
    let layout = Layout::new(&state.root_absolute, &state.release_id)?;
    model::Registry::load(&layout.root)?.assert_base_python_ready()?;
    let current = load(&layout, &state.instance_id)?;
    if current != *state
        || state.dirty
        || state.generation != state.validated_generation
        || state.verified.protected.get(Path::new("python/3.10.19")) != Some(&python_tree(&layout)?)
        || scan(&layout, &path(state)?, &state.ignored)? != state.verified.environment
    {
        bail!("实例dirty、过期或不匹配已验证generation，禁止使用");
    }
    Ok(())
}

/// 只从独立可信闭包证明创建新的验证epoch；不把未知当前hash当历史validated。
/// 仅返回内存候选，由GUI登记多记录事务统一持久化。
#[allow(clippy::too_many_arguments)] // 精确实例身份和独立信任根须显式绑定。
pub(crate) fn registration_candidate(
    ctx: &WorkspaceMutation,
    id: &str,
    storage_version: u32,
    transaction: &str,
    recipe_id: &str,
    recipe_sha256: &str,
    previous_known_generation: u64,
    proof: &crate::gui_registration_integrity::TrustedEnvironment,
    cancel: &CancelToken,
) -> Result<InstanceState> {
    let layout = ctx.layout();
    model::validate_environment_storage(id, storage_version)?;
    model::validate_component(transaction)?;
    model::validate_component(recipe_id)?;
    if !transaction.starts_with("gui-registration-")
        || !valid_hash(recipe_sha256)
        || proof.recipe_sha256 != recipe_sha256
        || !valid_hash(&proof.trusted_index_sha256)
        || !valid_hash(&proof.closure_sha256)
        || state_path(layout, id)?.exists()
        || model::environment_path(&layout.root, release(layout)?, id, storage_version)?
            != proof.environment
    {
        bail!("补登记候选身份不符，禁止覆盖既有实例状态");
    }
    let generation = previous_known_generation
        .checked_add(1)
        .context("验证epoch溢出")?;
    let mut state = InstanceState {
        schema_version: 3,
        component: "gui".into(),
        instance_id: id.into(),
        storage_version,
        release_id: release(layout)?.into(),
        root_absolute: layout.root.clone(),
        recipe_id: recipe_id.into(),
        recipe_sha256: recipe_sha256.into(),
        generation,
        validated_generation: generation,
        dirty: false,
        ignored: vec![],
        verified: Observation {
            environment: Tree::new(),
            profiles: Tree::new(),
            profiles_summary: None,
            protected: BTreeMap::new(),
        },
        pending: None,
        base_python_pending: None,
        registration_origin: Some(RegistrationOrigin {
            transaction: transaction.into(),
            trusted_index_sha256: proof.trusted_index_sha256.clone(),
            independently_verified_closure_sha256: proof.closure_sha256.clone(),
            observed_at: model::now(),
            previous_known_generation,
        }),
    };
    state.verified = observe(layout, &state, cancel)?;
    validate(layout, id, &state)?;
    Ok(state)
}

/// 复验前后整个只读保护闭包，供补登记事务使用；不会保存或清除dirty。
pub(crate) fn registration_revalidate(
    layout: &Layout,
    state: &InstanceState,
    candidate: bool,
    cancel: &CancelToken,
    verifier: impl FnOnce(&Path) -> Result<()>,
) -> Result<()> {
    validate(layout, state.id(), state)?;
    let engine_controls = engine_control_digest(layout)?;
    if state.dirty
        || state.pending.is_some()
        || state.base_python_pending.is_some()
        || state.generation != state.validated_generation
    {
        bail!("dirty/pending实例不能走补登记");
    }
    if !candidate {
        assert_usable(state)?;
    }
    let before = observe(layout, state, cancel)?;
    if before.environment != state.verified.environment
        || before.protected.get(Path::new("python/3.10.19"))
            != state.verified.protected.get(Path::new("python/3.10.19"))
    {
        bail!("补登记候选实体已变化");
    }
    verifier(&path(state)?)?;
    if observe(layout, state, cancel)? != before
        || engine_control_digest(layout)? != engine_controls
    {
        bail!("补登记验证改变受保护树或生产profiles");
    }
    if candidate {
        if state_path(layout, state.id())?.exists() {
            bail!("补登记期间出现了新的实例状态");
        }
    } else if load(layout, state.id())? != *state {
        bail!("补登记期间原实例状态变化");
    }
    Ok(())
}

pub(crate) fn registration_encoded(layout: &Layout, state: &InstanceState) -> Result<Vec<u8>> {
    validate(layout, state.id(), state)?;
    let mut bytes = serde_json::to_vec_pretty(state)?;
    bytes.push(b'\n');
    if bytes.len() as u64 > MAX_STATE {
        bail!("补登记实例状态超出可重读上限");
    }
    Ok(bytes)
}
pub(crate) fn registration_decode(layout: &Layout, bytes: &[u8]) -> Result<InstanceState> {
    if bytes.len() as u64 > MAX_STATE {
        bail!("补登记实例状态超限");
    }
    let state: InstanceState = serde_json::from_slice(bytes)?;
    validate(layout, state.id(), &state)?;
    Ok(state)
}
pub(crate) fn registration_project_receipt(
    layout: &Layout,
    state: &mut InstanceState,
    bytes: &[u8],
) -> Result<()> {
    if state.registration_origin.is_none() {
        bail!("只能投影独立补登记的新epoch状态");
    }
    let root = layout.release_dir.strip_prefix(&layout.root)?;
    let tree = state
        .verified
        .protected
        .get_mut(root)
        .context("缺少源码保护树")?;
    tree.insert(
        PathBuf::from("release.json"),
        Node::File(Fingerprint {
            bytes: bytes.len() as u64,
            sha256: hash(bytes),
        }),
    );
    validate(layout, state.id(), state)
}
pub(crate) fn registration_assert_origin(
    state: &InstanceState,
    transaction: &str,
    previous_generation: u64,
    proof: &crate::gui_registration_integrity::TrustedEnvironment,
) -> Result<()> {
    let origin = state
        .registration_origin
        .as_ref()
        .context("缺少独立补登记验证epoch来源")?;
    if origin.transaction != transaction
        || origin.previous_known_generation != previous_generation
        || origin.trusted_index_sha256 != proof.trusted_index_sha256
        || origin.independently_verified_closure_sha256 != proof.closure_sha256
        || state.recipe_sha256 != proof.recipe_sha256
        || path(state)? != proof.environment
        || state.generation != previous_generation.checked_add(1).context("epoch溢出")?
    {
        bail!("补登记状态与固定独立证明来源不符");
    }
    Ok(())
}
fn clean(
    layout: &Layout,
    mut state: InstanceState,
    cancel: &CancelToken,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    let old = state.clone();
    let engine_controls = engine_control_digest(layout)?;
    let before = observe(layout, &state, cancel)?;
    if !matches!(before.environment.get(Path::new("")), Some(Node::Directory)) {
        bail!("GUI实例目录缺失，保持dirty");
    }
    validator(&path(&state)?)?;
    if observe(layout, &state, cancel)? != before
        || load(layout, &state.instance_id)? != state
        || engine_control_digest(layout)? != engine_controls
    {
        bail!("验证器改变受保护树或持久实例已变化，保持dirty");
    }
    state.verified = before;
    if state.verified.profiles_summary.is_none() {
        state.verified.profiles_summary = Some(legacy_profiles_summary(&state.verified.profiles)?);
        state.verified.profiles.clear();
    }
    state.validated_generation = state.generation;
    state.dirty = false;
    state.pending = None;
    // 旧pending比较时只投影精确重建新增项；恢复完成的新基线必须覆盖实际完整树。
    state.verified = observe(layout, &state, cancel)?;
    record_preserved_recovery(layout, &old, &state)?;
    save(layout, &state)?;
    Ok(state)
}
#[cfg(test)]
pub(crate) fn validate_new(
    ctx: &WorkspaceMutation,
    state: &InstanceState,
    ignores: &[PathBuf],
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    validate_new_controlled(ctx, state, ignores, &CancelToken::new(), validator)
}
pub(crate) fn validate_new_controlled(
    ctx: &WorkspaceMutation,
    state: &InstanceState,
    ignores: &[PathBuf],
    cancel: &CancelToken,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    cancel.check()?;
    let layout = ctx.layout();
    let mut current = load(layout, state.id())?;
    if current != *state || !current.dirty || current.generation != 1 || current.pending.is_some() {
        bail!("新实例安装许可不匹配");
    }
    if !current.ignored.is_empty() && current.ignored != ignores {
        bail!("新实例已固定运行时忽略合同，不能重新豁免文件");
    }
    current.ignored = ignores.into();
    validate(layout, current.id(), &current)?;
    let observed = observe(layout, &current, cancel)?;
    if !profiles_equal(&observed, &current.verified)?
        || observed.protected != current.verified.protected
    {
        bail!("安装改变了profiles或非目标受管组件保护树");
    }
    // 忽略合同先持久化，验证失败或重启仍能恢复同一合同。
    save(layout, &current)?;
    clean(layout, current, cancel, validator)
}
fn validate_paths(state: &InstanceState, paths: &[PathBuf]) -> Result<()> {
    if paths.is_empty() || paths.len() > 20_000 {
        bail!("修复文件清单为空或超限");
    }
    let mut unique = BTreeSet::new();
    let known: BTreeMap<_, _> = state
        .verified
        .environment
        .keys()
        .map(|path| (windows_key(path), path))
        .collect();
    for rel in paths {
        relative(rel)?;
        if ignored(&state.ignored, rel) || !unique.insert(windows_key(rel)) {
            bail!("修复清单重复或落入忽略路径");
        }
        let mut current = Some(rel.as_path());
        while let Some(part) = current {
            if known
                .get(&windows_key(part))
                .is_some_and(|known| known.as_path() != part)
                || (part == rel
                    && matches!(state.verified.environment.get(part), Some(Node::Directory)))
                || (part != rel
                    && matches!(state.verified.environment.get(part), Some(Node::File(_))))
            {
                bail!("修复路径身份冲突、大小写别名或父路径不是目录");
            }
            current = part.parent();
        }
    }
    for rel in paths {
        let mut parent = rel.parent();
        while let Some(directory) = parent {
            if unique.contains(&windows_key(directory)) {
                bail!("修复清单存在父子冲突");
            }
            parent = directory.parent();
        }
    }
    Ok(())
}
#[cfg(test)]
pub(crate) fn plan(
    ctx: &WorkspaceMutation,
    id: &str,
    expected_generation: u64,
    paths: &[PathBuf],
) -> Result<RepairPlan> {
    plan_controlled(ctx, id, expected_generation, paths, &CancelToken::new())
}
pub(crate) fn plan_controlled(
    ctx: &WorkspaceMutation,
    id: &str,
    expected_generation: u64,
    paths: &[PathBuf],
    cancel: &CancelToken,
) -> Result<RepairPlan> {
    cancel.check()?;
    let state = load(ctx.layout(), id)?;
    if state.dirty
        || state.generation != state.validated_generation
        || state.generation != expected_generation
    {
        bail!("修复计划generation已过期");
    }
    let diagnosed = observe(ctx.layout(), &state, cancel)?;
    let mut facts = state.clone();
    facts.verified = diagnosed.clone();
    validate_paths(&facts, paths)?;
    // 诊断不能把闭包外已被替换的解释器/控制文件重新认作可信基线。
    // profiles 与其他组件允许在两个操作之间正常变化，本次事务从诊断时保护它们。
    let mut trusted = state.verified.clone();
    trusted.profiles = diagnosed.profiles.clone();
    trusted.profiles_summary = diagnosed.profiles_summary.clone();
    trusted.protected = diagnosed.protected.clone();
    // 基础Python由所有引用实例共享；单包修复不能接纳已变更的基础运行时。
    trusted.protected.insert(
        PathBuf::from("python/3.10.19"),
        state
            .verified
            .protected
            .get(Path::new("python/3.10.19"))
            .context("缺少基础Python基线")?
            .clone(),
    );
    let allowed = paths.iter().map(|path| (path.clone(), None)).collect();
    protected(ctx.layout(), &trusted, &diagnosed, &allowed)?;
    Ok(RepairPlan {
        state,
        paths: paths.into(),
        diagnosed,
    })
}
fn copy(
    layout: &Layout,
    source: &Path,
    destination: &Path,
    create_new: bool,
) -> Result<Fingerprint> {
    let expected = fingerprint(layout, source)?;
    layout.guard_path(destination)?;
    layout.ensure_dir(destination.parent().context("复制缺少父目录")?)?;
    // 恢复也先独立复制到新文件，不能truncate调用者可能替换成硬链接的目标。
    let output_path = if create_new {
        destination.to_path_buf()
    } else {
        layout.root.join("backups/gui-instances").join(format!(
            ".restore-{}-{}-{}.tmp",
            std::process::id(),
            model::now(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ))
    };
    layout.guard_path(&output_path)?;
    let mut input = File::open(source)?;
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&output_path)?;
    let bytes = std::io::copy(
        &mut Read::by_ref(&mut input).take(MAX_FILE + 1),
        &mut output,
    )?;
    output.sync_all()?;
    drop(output);
    if bytes != expected.bytes
        || fingerprint(layout, &output_path)? != expected
        || fingerprint(layout, source)? != expected
    {
        bail!("实例独立复制摘要不符，保持原事务状态");
    }
    if !create_new {
        layout.guard_path(destination)?;
        if destination.exists() {
            if !destination.is_file() {
                bail!("恢复目标不是普通文件，保持dirty");
            }
            fs::remove_file(destination)?;
        }
        fs::rename(&output_path, destination)?;
    }
    Ok(expected)
}
#[cfg(test)]
pub(crate) fn begin(ctx: &WorkspaceMutation, plan: &RepairPlan) -> Result<MutationTicket> {
    begin_controlled(ctx, plan, &CancelToken::new())
}
pub(crate) fn begin_controlled(
    ctx: &WorkspaceMutation,
    plan: &RepairPlan,
    cancel: &CancelToken,
) -> Result<MutationTicket> {
    cancel.check()?;
    let layout = ctx.layout();
    let engine_controls = engine_control_digest(layout)?;
    let mut state = load(layout, plan.state.id())?;
    if state != plan.state {
        bail!("诊断后持久实例已变化");
    }
    if state.dirty || observe(layout, &state, cancel)? != plan.diagnosed {
        bail!("修复诊断树已经变化，拒绝使用旧计划");
    }
    state.verified = plan.diagnosed.clone();
    validate_paths(&state, &plan.paths)?;
    let generation = state
        .generation
        .checked_add(1)
        .context("实例generation溢出")?;
    let directory = Path::new("backups/gui-instances")
        .join(state.id())
        .join(format!(
            "generation-{generation}-{}-{}",
            model::now(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
    let backup = layout.root.join(&directory);
    layout.guard_path(&backup)?;
    layout.ensure_dir(backup.parent().context("快照缺少父目录")?)?;
    fs::create_dir(&backup)?;
    let mut pending = Pending {
        instance_id: state.instance_id.clone(),
        generation,
        base_generation: state.generation,
        recipe_sha256: state.recipe_sha256.clone(),
        tree_sha256: hash(&serde_json::to_vec(&state.verified)?),
        directory,
        files: BTreeMap::new(),
    };
    let environment = path(&state)?;
    let sorted: BTreeSet<_> = plan.paths.iter().cloned().collect();
    for (index, rel) in sorted.into_iter().enumerate() {
        cancel.check()?;
        let original = match state.verified.environment.get(&rel) {
            Some(Node::File(value)) => Some(value.clone()),
            None => None,
            _ => bail!("修复目标不是普通文件"),
        };
        let snapshot = backup.join(index.to_string());
        layout.guard_path(&snapshot)?;
        if let Some(expected) = &original {
            if copy(layout, &environment.join(&rel), &snapshot, true)? != *expected {
                bail!("诊断后修复目标已变化");
            }
        } else {
            let mut marker = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(snapshot)?;
            marker.write_all(b"missing\n")?;
            marker.sync_all()?;
        }
        pending.files.insert(rel, original);
    }
    model::write_json_atomic(&backup.join("manifest.json"), &pending)?;
    if observe(layout, &state, cancel)? != state.verified || load(layout, state.id())? != plan.state
    {
        bail!("快照期间受保护内容变化，未授权修改");
    }
    state.generation = generation;
    state.dirty = true;
    state.pending = Some(pending);
    if engine_control_digest(layout)? != engine_controls {
        bail!("GUI快照期间引擎控制记录变化，未授权修改");
    }
    save(layout, &state)?;
    Ok(MutationTicket {
        state,
        engine_controls,
    })
}
fn check_snapshots(layout: &Layout, state: &InstanceState) -> Result<()> {
    let pending = state.pending.as_ref().context("实例没有待恢复事务")?;
    let backup = layout.root.join(&pending.directory);
    let manifest = backup.join("manifest.json");
    layout.guard_path(&manifest)?;
    if fs::metadata(&manifest)?.len() > MAX_STATE {
        bail!("快照清单过大");
    }
    let stored: Pending = serde_json::from_slice(&fs::read(manifest)?)?;
    if stored != *pending {
        bail!("快照清单与持久事务不一致");
    }
    for (index, original) in pending.files.values().enumerate() {
        let snapshot = backup.join(index.to_string());
        layout.guard_path(&snapshot)?;
        match original {
            Some(expected) if fingerprint(layout, &snapshot)? == *expected => {}
            None if fs::metadata(&snapshot)?.len() == 8 && fs::read(&snapshot)? == b"missing\n" => {
            }
            _ => bail!("独立快照损坏，保持dirty"),
        }
    }
    Ok(())
}
pub(crate) fn reload_ticket(layout: &Layout, id: &str) -> Result<MutationTicket> {
    let state = load(layout, id)?;
    if !state.dirty {
        bail!("实例没有dirty事务");
    }
    check_snapshots(layout, &state)?;
    Ok(MutationTicket {
        state,
        engine_controls: engine_control_digest(layout)?,
    })
}
fn checked(ctx: &WorkspaceMutation, ticket: &MutationTicket) -> Result<InstanceState> {
    let state = load(ctx.layout(), ticket.state.id())?;
    if state != ticket.state
        || !state.dirty
        || engine_control_digest(ctx.layout())? != ticket.engine_controls
    {
        bail!("事务ticket已经过期或不属于工作区");
    }
    check_snapshots(ctx.layout(), &state)?;
    Ok(state)
}
fn protected_trees_equal(
    layout: &Layout,
    before: &BTreeMap<PathBuf, Tree>,
    after: &BTreeMap<PathBuf, Tree>,
) -> Result<bool> {
    let approved = engine_namespaces::capture(layout)?.excluded;
    let project = |values: &BTreeMap<PathBuf, Tree>| {
        let mut values = values.clone();
        if let Some(tree) = values.get_mut(Path::new("e")) {
            tree.retain(|path, _| !approved.iter().any(|id| path.starts_with(id)));
            if !approved.is_empty() && *tree == Tree::from([(PathBuf::new(), Node::Directory)]) {
                tree.clear();
            }
        }
        values
    };
    Ok(project(before) == project(after))
}
fn protected(
    layout: &Layout,
    before: &Observation,
    after: &Observation,
    files: &BTreeMap<PathBuf, Option<Fingerprint>>,
) -> Result<()> {
    let mut expected = before.environment.clone();
    let mut actual = after.environment.clone();
    for rel in files.keys() {
        if matches!(actual.get(rel), Some(Node::Directory)) {
            bail!("修复目标被替换为目录");
        }
        expected.remove(rel);
        actual.remove(rel);
        let mut parent = rel.parent();
        while let Some(directory) = parent {
            if !before.environment.contains_key(directory)
                && matches!(actual.get(directory), Some(Node::Directory))
            {
                actual.remove(directory);
            }
            parent = directory.parent();
        }
    }
    if expected != actual
        || !profiles_equal(before, after)?
        || !protected_trees_equal(layout, &before.protected, &after.protected)?
    {
        bail!("修复改变了非目标文件、目录或profiles，保持dirty");
    }
    Ok(())
}
#[cfg(test)]
pub(crate) fn commit(
    ctx: &WorkspaceMutation,
    ticket: &MutationTicket,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    commit_controlled(ctx, ticket, &CancelToken::new(), validator)
}
pub(crate) fn commit_controlled(
    ctx: &WorkspaceMutation,
    ticket: &MutationTicket,
    cancel: &CancelToken,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    cancel.check()?;
    let state = checked(ctx, ticket)?;
    protected(
        ctx.layout(),
        &state.verified,
        &observe(ctx.layout(), &state, cancel)?,
        &state.pending.as_ref().context("缺少事务")?.files,
    )?;
    clean(ctx.layout(), state, cancel, validator)
}
#[cfg(test)]
pub(crate) fn recover(
    ctx: &WorkspaceMutation,
    ticket: &MutationTicket,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    recover_controlled(ctx, ticket, &CancelToken::new(), validator)
}
pub(crate) fn recover_controlled(
    ctx: &WorkspaceMutation,
    ticket: &MutationTicket,
    cancel: &CancelToken,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<InstanceState> {
    cancel.check()?;
    let layout = ctx.layout();
    let state = checked(ctx, ticket)?;
    let pending = state.pending.as_ref().context("缺少恢复快照")?;
    protected(
        layout,
        &state.verified,
        &observe(layout, &state, cancel)?,
        &pending.files,
    )?;
    let environment = path(&state)?;
    for (index, (rel, original)) in pending.files.iter().enumerate() {
        cancel.check()?;
        let target = environment.join(rel);
        layout.guard_path(&target)?;
        match original {
            Some(expected) => {
                if copy(
                    layout,
                    &layout.root.join(&pending.directory).join(index.to_string()),
                    &target,
                    false,
                )? != *expected
                {
                    bail!("恢复摘要不符，保持dirty");
                }
            }
            None => {
                if target.exists() {
                    if !target.is_file() {
                        bail!("原missing路径不是普通文件");
                    }
                    fs::remove_file(&target)?;
                }
                let mut parent = target.parent();
                while let Some(directory) = parent {
                    let rel = directory.strip_prefix(&environment)?;
                    if state.verified.environment.contains_key(rel) {
                        break;
                    }
                    layout.guard_path(directory)?;
                    if !directory.exists() {
                        parent = directory.parent();
                        continue;
                    }
                    if fs::read_dir(directory)?.next().is_some() {
                        break;
                    }
                    fs::remove_dir(directory)?;
                    parent = directory.parent();
                }
            }
        }
    }
    let restored = observe(layout, &state, cancel)?;
    if restored.environment != state.verified.environment
        || !profiles_equal(&restored, &state.verified)?
        || !protected_trees_equal(layout, &restored.protected, &state.verified.protected)?
    {
        bail!("同路径恢复未还原原树，保持dirty");
    }
    clean(layout, state, cancel, validator)
}

/// True for the unvalidated first-install orphan. A package transaction must finish first.
pub(crate) fn base_reference_initial_dirty(state: &InstanceState) -> Result<bool> {
    if state.pending.is_some() || state.base_python_pending.is_some() {
        bail!("引用实例已有待恢复事务，请先恢复原事务");
    }
    if state.dirty && !(state.generation == 1 && state.validated_generation == 0) {
        bail!("引用实例dirty来源未知");
    }
    Ok(state.dirty)
}
pub(crate) fn base_reference_sha(state: &InstanceState) -> Result<String> {
    Ok(hash(&serde_json::to_vec(state)?))
}
/// Rust-only integrity check: the damaged base is the sole admitted prior difference.
pub(crate) fn base_reference_validate_before(layout: &Layout, state: &InstanceState) -> Result<()> {
    if base_reference_initial_dirty(state)? {
        return Ok(());
    }
    if scan(layout, &path(state)?, &state.ignored)? != state.verified.environment {
        bail!("基础Python修复不能追认引用环境已有的非目标变化");
    }
    // Other managed instances can have been added since this instance's last
    // validation. Their current bytes belong to the reviewed cohort protection;
    // each clean member checks its own venv baseline. Source and uv identities
    // are independently checked by the real validator before any candidate.
    Ok(())
}
pub(crate) fn quarantine_for_base(
    layout: &Layout,
    id: &str,
    expected_sha: &str,
    transaction: &str,
) -> Result<()> {
    let mut current = load(layout, id)?;
    if current.base_python_pending.as_ref().is_some_and(|pending| {
        pending.transaction == transaction && pending.previous_state_sha256 == expected_sha
    }) {
        assert_quarantined_original(&current)?;
        return Ok(());
    }
    if base_reference_sha(&current)? != expected_sha {
        bail!("基础Python修复前实例状态已变化");
    }
    let initial_dirty = base_reference_initial_dirty(&current)?;
    let old_generation = current.generation;
    let old_schema = current.schema_version;
    current.schema_version = 3;
    if !initial_dirty {
        current.generation = old_generation
            .checked_add(1)
            .context("引用generation溢出")?;
    }
    current.dirty = true;
    current.base_python_pending = Some(BasePythonPending {
        transaction: transaction.into(),
        previous_generation: old_generation,
        initial_dirty,
        previous_state_sha256: expected_sha.into(),
        previous_schema_version: old_schema,
    });
    save_for_base(layout, &current, transaction)
}
fn assert_quarantined_original(state: &InstanceState) -> Result<()> {
    let pending = state
        .base_python_pending
        .as_ref()
        .context("引用缺少基础Python事务")?;
    let mut original = state.clone();
    original.schema_version = pending.previous_schema_version;
    original.generation = pending.previous_generation;
    original.dirty = pending.initial_dirty;
    original.base_python_pending = None;
    if base_reference_sha(&original)? != pending.previous_state_sha256 {
        bail!("停用引用记录与原始实例身份不符");
    }
    Ok(())
}
/// Builds a clean candidate without publishing it. The component gate remains active.
pub(crate) fn candidate_after_base(
    layout: &Layout,
    id: &str,
    transaction: &str,
    cancel: &CancelToken,
    validator: impl FnOnce(&Path) -> Result<()>,
) -> Result<Vec<u8>> {
    let mut state = load(layout, id)?;
    let pending = state
        .base_python_pending
        .as_ref()
        .context("引用没有基础Python事务")?
        .clone();
    assert_quarantined_original(&state)?;
    if pending.transaction != transaction {
        bail!("引用基础Python事务不匹配");
    }
    let before = observe(layout, &state, cancel)?;
    if !pending.initial_dirty {
        validator(&path(&state)?)?;
        state.validated_generation = state.generation;
        state.dirty = false;
    }
    let original = load(layout, id)?;
    if observe(layout, &original, cancel)? != before {
        bail!("基础Python复验期间引用环境或受保护组件变化");
    }
    let mut expected_state = original.clone();
    if !pending.initial_dirty {
        expected_state.validated_generation = expected_state.generation;
        expected_state.dirty = false;
    }
    if expected_state != state {
        bail!("基础Python复验期间引用持久记录变化");
    }
    // A first-install dirty orphan is only rebaselined and remains explicitly unusable.
    state.verified = before;
    state.base_python_pending = None;
    validate(layout, id, &state)?;
    let bytes = serde_json::to_vec_pretty(&state)?;
    if bytes.len() as u64 > MAX_STATE {
        bail!("引用候选记录过大");
    }
    Ok(bytes)
}
pub(crate) fn commit_after_base(
    layout: &Layout,
    id: &str,
    transaction: &str,
    bytes: &[u8],
) -> Result<()> {
    if bytes.len() as u64 > MAX_STATE {
        bail!("引用候选记录过大");
    }
    let candidate: InstanceState = serde_json::from_slice(bytes)?;
    validate(layout, id, &candidate)?;
    let current = load(layout, id)?;
    if current == candidate {
        return Ok(());
    }
    let pending = current
        .base_python_pending
        .as_ref()
        .context("引用事务已消失，拒绝覆盖")?;
    assert_quarantined_original(&current)?;
    if pending.transaction != transaction
        || candidate.id() != current.id()
        || candidate.storage_version != current.storage_version
        || candidate.release_id != current.release_id
        || candidate.recipe_id != current.recipe_id
        || candidate.recipe_sha256 != current.recipe_sha256
        || candidate.generation != current.generation
        || candidate.base_python_pending.is_some()
        || candidate.pending.is_some()
        || candidate.dirty != pending.initial_dirty
    {
        bail!("引用候选与停用事务身份不匹配");
    }
    let mut expected = current.clone();
    expected.base_python_pending = None;
    if !pending.initial_dirty {
        expected.dirty = false;
        expected.validated_generation = expected.generation;
    }
    expected.verified = candidate.verified.clone();
    if expected != candidate {
        bail!("引用候选试图改写基础Python之外的实例身份");
    }
    save_for_base(layout, &candidate, transaction)
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Fixture {
        root: PathBuf,
        ctx: WorkspaceMutation,
        state: InstanceState,
    }
    impl Fixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "nt-instance-{}-{}-{}",
                std::process::id(),
                model::now(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            let ctx =
                WorkspaceMutation::acquire(&root, &format!("dev-{}", "a".repeat(40))).unwrap();
            let base = root.join("python/3.10.19/base.dll");
            ctx.layout().ensure_dir(base.parent().unwrap()).unwrap();
            fs::write(base, b"original non-target").unwrap();
            let state = create(&ctx, "g0000000000000001", "recipe-one", &"b".repeat(64)).unwrap();
            let env = path(&state).unwrap();
            fs::create_dir(env.join("package")).unwrap();
            fs::write(env.join("package/a.py"), b"original-a").unwrap();
            fs::write(env.join("package/b.py"), b"original-b").unwrap();
            fs::write(env.join("protected.py"), b"preserved").unwrap();
            let state = validate_new(&ctx, &state, &[], |_| Ok(())).unwrap();
            Self { root, ctx, state }
        }
        fn ticket(&self) -> MutationTicket {
            begin(
                &self.ctx,
                &plan(
                    &self.ctx,
                    self.state.id(),
                    self.state.generation(),
                    &[
                        "package/a.py".into(),
                        "package/b.py".into(),
                        "new-dir/new.py".into(),
                    ],
                )
                .unwrap(),
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
                    .starts_with("nt-instance-")
            {
                let _ = fs::remove_dir_all(&self.root);
            }
        }
    }
    #[test]
    fn real_multifile_failure_recovers_original_and_missing_paths_from_disk() {
        let f = Fixture::new();
        let env = path(&f.state).unwrap();
        let ticket = f.ticket();
        fs::write(env.join("package/a.py"), b"broken-a").unwrap();
        fs::remove_file(env.join("package/b.py")).unwrap();
        fs::create_dir(env.join("new-dir")).unwrap();
        fs::write(env.join("new-dir/new.py"), b"added").unwrap();
        assert!(commit(&f.ctx, &ticket, |_| bail!("真实多文件验证失败")).is_err());
        assert!(load(f.ctx.layout(), f.state.id()).unwrap().dirty());
        assert!(assert_usable(&f.state).is_err());
        drop(ticket);
        let restored = recover(
            &f.ctx,
            &reload_ticket(f.ctx.layout(), f.state.id()).unwrap(),
            |at| {
                assert_eq!(at, env);
                assert_eq!(fs::read(at.join("package/a.py"))?, b"original-a");
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(fs::read(env.join("package/b.py")).unwrap(), b"original-b");
        assert!(!env.join("new-dir").exists());
        assert_eq!(restored.generation(), 2);
        assert_usable(&restored).unwrap();
    }
    #[test]
    fn external_changes_and_stale_generation_never_unlock_dirty() {
        let f = Fixture::new();
        assert!(plan(&f.ctx, f.state.id(), 99, &["package/a.py".into()]).is_err());
        let ticket = f.ticket();
        fs::write(path(&f.state).unwrap().join("protected.py"), b"foreign").unwrap();
        assert!(commit(&f.ctx, &ticket, |_| Ok(())).is_err());
        assert!(recover(&f.ctx, &ticket, |_| Ok(())).is_err());
        assert!(load(f.ctx.layout(), f.state.id()).unwrap().dirty());
    }
    #[test]
    fn successful_commit_detaches_snapshots_and_rejects_old_tickets() {
        let f = Fixture::new();
        let env = path(&f.state).unwrap();
        let ticket = f.ticket();
        let backup = f
            .root
            .join(&ticket.state.pending.as_ref().unwrap().directory);
        let before = fs::read(backup.join("1")).unwrap();
        fs::write(env.join("package/a.py"), b"repaired").unwrap();
        assert_eq!(fs::read(backup.join("1")).unwrap(), before);
        let state = commit(&f.ctx, &ticket, |at| {
            if fs::read(at.join("package/a.py"))? != b"repaired" {
                bail!("包未修好");
            }
            Ok(())
        })
        .unwrap();
        assert_usable(&state).unwrap();
        assert!(recover(&f.ctx, &ticket, |_| Ok(())).is_err());
        assert!(plan(
            &f.ctx,
            state.id(),
            f.state.generation(),
            &["package/a.py".into()]
        )
        .is_err());
        fs::write(env.join("package/a.py"), b"corrupt-again").unwrap();
        // 损坏目标仍允许重新诊断修复；计划后的外部变化必须拒绝执行。
        let planned = plan(
            &f.ctx,
            state.id(),
            state.generation(),
            &["package/a.py".into()],
        )
        .unwrap();
        fs::write(env.join("package/a.py"), b"changed-after-plan").unwrap();
        assert!(begin(&f.ctx, &planned).is_err());
    }
    #[test]
    fn snapshot_corruption_and_unknown_state_preserve_bytes_and_dirty() {
        let f = Fixture::new();
        let ticket = f.ticket();
        let backup = f
            .ctx
            .layout()
            .root
            .join(&ticket.state.pending.as_ref().unwrap().directory);
        fs::write(backup.join("0"), b"bad snapshot").unwrap();
        assert!(reload_ticket(f.ctx.layout(), f.state.id()).is_err());
        assert!(recover(&f.ctx, &ticket, |_| Ok(())).is_err());
        let target = state_path(f.ctx.layout(), f.state.id()).unwrap();
        let mut value = serde_json::to_value(load(f.ctx.layout(), f.state.id()).unwrap()).unwrap();
        value["schema_version"] = 999.into();
        let bytes = serde_json::to_vec(&value).unwrap();
        fs::write(&target, &bytes).unwrap();
        assert!(load(f.ctx.layout(), f.state.id()).is_err());
        assert!(create(&f.ctx, f.state.id(), "other", &"c".repeat(64)).is_err());
        assert_eq!(fs::read(target).unwrap(), bytes);
    }
    #[test]
    fn explicit_runtime_ignores_do_not_exempt_profile_or_whole_environment() {
        let f = Fixture::new();
        assert!(validate_paths(&f.state, &["../outside".into()]).is_err());
        assert!(validate_paths(&f.state, &["package".into()]).is_err());
        assert!(validate_paths(&f.state, &["PACKAGE/a.py".into()]).is_err());
        let mut invalid = f.state.clone();
        invalid.ignored = vec![PathBuf::from("package")];
        assert!(validate(f.ctx.layout(), invalid.id(), &invalid).is_err());
        let ticket = f.ticket();
        fs::write(
            f.root.join("profiles/default/profile.json"),
            b"profile changed",
        )
        .unwrap();
        assert!(recover(&f.ctx, &ticket, |_| Ok(())).is_err());
    }
    #[test]
    fn source_base_tools_and_other_instances_are_transaction_protected() {
        for relative in [
            "releases/source-placeholder.txt",
            "tools/uv.exe",
            "python/3.10.19/base.dll",
            "environments/other/instances/safe/gui/protected.py",
            "e/g0000000000000002/protected.py",
        ] {
            let f = Fixture::new();
            let protected = if relative.starts_with("releases/") {
                f.ctx.layout().app.join("gui.py")
            } else {
                f.root.join(relative)
            };
            f.ctx
                .layout()
                .ensure_dir(protected.parent().unwrap())
                .unwrap();
            fs::write(&protected, b"original non-target").unwrap();
            let ticket = f.ticket();
            fs::write(&protected, b"foreign non-target mutation").unwrap();
            assert!(commit(&f.ctx, &ticket, |_| Ok(())).is_err());
            assert!(recover(&f.ctx, &ticket, |_| Ok(())).is_err());
            assert!(load(f.ctx.layout(), f.state.id()).unwrap().dirty());
        }
    }
    #[test]
    fn normal_usable_check_does_not_scan_large_profile_model_files() {
        let f = Fixture::new();
        let model = f.root.join("profiles/default/large-model.bin");
        File::create(model).unwrap().set_len(MAX_FILE + 1).unwrap();
        assert_usable(&f.state).unwrap();
    }

    #[test]
    fn streaming_profiles_detect_same_length_and_timestamp_content_changes() {
        use std::io::{Seek, SeekFrom};
        let f = Fixture::new();
        let model = f.root.join("profiles/default/model.bin");
        fs::write(&model, vec![b'a'; 3 * 65_536 + 19]).unwrap();
        let modified = fs::metadata(&model).unwrap().modified().unwrap();
        let before = profile_summary(
            f.ctx.layout(),
            &f.root.join("profiles"),
            &mut ProfileBudget::new(&CancelToken::new()),
        )
        .unwrap();
        let ticket = f.ticket();
        let mut output = OpenOptions::new().write(true).open(&model).unwrap();
        output.seek(SeekFrom::Start(65_537)).unwrap();
        output.write_all(b"b").unwrap();
        output
            .set_times(fs::FileTimes::new().set_modified(modified))
            .unwrap();
        drop(output);
        assert_eq!(fs::metadata(&model).unwrap().modified().unwrap(), modified);
        let after = profile_summary(
            f.ctx.layout(),
            &f.root.join("profiles"),
            &mut ProfileBudget::new(&CancelToken::new()),
        )
        .unwrap();
        assert_eq!(before.bytes, after.bytes);
        assert_ne!(before.sha256, after.sha256);
        assert!(commit(&f.ctx, &ticket, |_| Ok(())).is_err());
        assert!(recover(&f.ctx, &ticket, |_| Ok(())).is_err());
        assert!(load(f.ctx.layout(), f.state.id()).unwrap().dirty());
    }

    #[test]
    fn profile_limits_are_independent_cancellable_and_fail_before_permission() {
        let f = Fixture::new();
        fs::write(
            f.root.join("profiles/default/model.bin"),
            vec![0u8; 131_073],
        )
        .unwrap();
        let cancel = CancelToken::new();
        let mut budget = ProfileBudget::new(&cancel);
        budget.max_bytes = 131_072;
        assert!(profile_summary(f.ctx.layout(), &f.root.join("profiles"), &mut budget).is_err());
        let mut budget = ProfileBudget::new(&cancel);
        budget.max_nodes = 1;
        assert!(profile_summary(f.ctx.layout(), &f.root.join("profiles"), &mut budget).is_err());
        let mut budget = ProfileBudget::new(&cancel);
        budget.deadline = Instant::now();
        assert!(profile_summary(f.ctx.layout(), &f.root.join("profiles"), &mut budget).is_err());
        let manager = crate::operations::OperationManager::default();
        let operation = manager
            .start("profiles-cancel", crate::operations::OperationKind::Repair)
            .unwrap();
        manager.cancel("profiles-cancel").unwrap();
        assert!(plan_controlled(
            &f.ctx,
            f.state.id(),
            1,
            &["package/a.py".into()],
            &operation.cancel_token()
        )
        .is_err());
        assert!(!load(f.ctx.layout(), f.state.id()).unwrap().dirty());
        assert_eq!(load(f.ctx.layout(), f.state.id()).unwrap().generation(), 1);
    }

    #[test]
    fn profile_summary_matches_legacy_tree_and_rejects_mixed_or_unknown_contracts() {
        let f = Fixture::new();
        let nested = f.root.join("profiles/default/models/empty");
        f.ctx.layout().ensure_dir(&nested).unwrap();
        fs::write(nested.parent().unwrap().join("two.bin"), b"two").unwrap();
        let tree = scan(f.ctx.layout(), &f.root.join("profiles"), &[]).unwrap();
        let summary = profile_summary(
            f.ctx.layout(),
            &f.root.join("profiles"),
            &mut ProfileBudget::new(&CancelToken::new()),
        )
        .unwrap();
        assert_eq!(summary, legacy_profiles_summary(&tree).unwrap());
        assert_ne!(summary, absent_profiles());
        let mut invalid = f.state.clone();
        invalid.verified.profiles = tree;
        assert!(validate(f.ctx.layout(), invalid.id(), &invalid).is_err());
        invalid.verified.profiles.clear();
        invalid
            .verified
            .profiles_summary
            .as_mut()
            .unwrap()
            .schema_version = 2;
        assert!(validate(f.ctx.layout(), invalid.id(), &invalid).is_err());
    }

    #[test]
    fn old_pending_profile_tree_preserves_serialized_hash_and_recovers_before_upgrade() {
        let f = Fixture::new();
        let mut ticket = f.ticket();
        ticket.state.verified.profiles =
            scan(f.ctx.layout(), &f.root.join("profiles"), &[]).unwrap();
        ticket.state.verified.profiles_summary = None;
        let old_bytes = serde_json::to_vec(&ticket.state.verified).unwrap();
        assert!(!String::from_utf8_lossy(&old_bytes).contains("profiles_summary"));
        let round_trip: Observation = serde_json::from_slice(&old_bytes).unwrap();
        assert_eq!(serde_json::to_vec(&round_trip).unwrap(), old_bytes);
        ticket.state.pending.as_mut().unwrap().tree_sha256 = hash(&old_bytes);
        let pending = ticket.state.pending.as_ref().unwrap();
        model::write_json_atomic(
            &f.root.join(&pending.directory).join("manifest.json"),
            pending,
        )
        .unwrap();
        save(f.ctx.layout(), &ticket.state).unwrap();
        fs::write(
            path(&ticket.state).unwrap().join("package/a.py"),
            b"interrupted",
        )
        .unwrap();
        let loaded = reload_ticket(f.ctx.layout(), f.state.id()).unwrap();
        assert_eq!(loaded.state.verified.profiles_summary, None);
        let restored = recover(&f.ctx, &loaded, |_| Ok(())).unwrap();
        assert!(!restored.dirty());
        assert!(restored.verified.profiles.is_empty());
        assert!(restored.verified.profiles_summary.is_some());
        assert_eq!(
            fs::read(path(&restored).unwrap().join("package/a.py")).unwrap(),
            b"original-a"
        );
    }

    #[test]
    #[ignore = "显式大模型验收：真实逐字节读取超过1GiB的资料文件"]
    fn streaming_profile_accepts_file_larger_than_snapshot_limit_without_state_growth() {
        let f = Fixture::new();
        let model = f.root.join("profiles/default/large-model.bin");
        File::create(&model).unwrap().set_len(MAX_FILE + 1).unwrap();
        assert!(fingerprint(f.ctx.layout(), &model).is_err());
        let summary = profile_summary(
            f.ctx.layout(),
            &f.root.join("profiles"),
            &mut ProfileBudget::new(&CancelToken::new()),
        )
        .unwrap();
        assert!(summary.bytes > MAX_FILE);
        assert!(serde_json::to_vec(&summary).unwrap().len() < 512);
        let planned = plan(
            &f.ctx,
            f.state.id(),
            f.state.generation(),
            &["package/a.py".into()],
        )
        .unwrap();
        assert!(planned.diagnosed.profiles.is_empty());
        assert!(serde_json::to_vec(&planned.diagnosed).unwrap().len() < 32 * 1024);
    }

    #[test]
    fn compact_storage_is_fixed_and_collisions_or_storage_reinterpretation_are_rejected() {
        let f = Fixture::new();
        assert_eq!(f.state.storage_version(), 1);
        assert_eq!(f.state.release_id(), release(f.ctx.layout()).unwrap());
        assert_eq!(path(&f.state).unwrap(), f.root.join("e/g0000000000000001"));
        assert!(f
            .state
            .verified
            .protected
            .contains_key(Path::new("environments")));
        assert!(f.state.verified.protected.contains_key(Path::new("e")));
        assert!(!f.state.verified.protected[Path::new("e")]
            .contains_key(Path::new("g0000000000000001")));
        assert!(create(&f.ctx, f.state.id(), "recipe-one", &"b".repeat(64)).is_err());
        let record = state_path(f.ctx.layout(), f.state.id()).unwrap();
        let original = fs::read(&record).unwrap();
        let other_layout = Layout::new(&f.root, &format!("dev-{}", "c".repeat(40))).unwrap();
        assert!(load(&other_layout, f.state.id()).is_err());
        assert_eq!(fs::read(&record).unwrap(), original);
        let collision = "g0000000000000002";
        f.ctx
            .layout()
            .ensure_dir(&f.root.join("e").join(collision))
            .unwrap();
        fs::write(
            f.root.join("e").join(collision).join("sentinel"),
            b"preexisting",
        )
        .unwrap();
        assert!(create(&f.ctx, collision, "recipe-one", &"b".repeat(64)).is_err());
        assert_eq!(
            fs::read(f.root.join("e").join(collision).join("sentinel")).unwrap(),
            b"preexisting"
        );
        let mut state = f.state.clone();
        state.storage_version = 0;
        fs::write(&record, serde_json::to_vec(&state).unwrap()).unwrap();
        assert!(load(f.ctx.layout(), state.id()).is_err());
        fs::write(&record, &original).unwrap();
        state = f.state.clone();
        state.storage_version = 99;
        assert!(validate(f.ctx.layout(), state.id(), &state).is_err());
        assert!(load(f.ctx.layout(), "g0000000000000003").is_err());
    }

    #[test]
    fn old_schema_two_missing_storage_field_keeps_original_path_and_can_repair() {
        let f = Fixture::new();
        let compact = path(&f.state).unwrap();
        let mut legacy = f.state.clone();
        legacy.storage_version = 0;
        let old = model::environment_path(&f.root, legacy.release_id(), legacy.id(), 0).unwrap();
        f.ctx.layout().ensure_dir(old.parent().unwrap()).unwrap();
        fs::rename(compact, &old).unwrap();
        legacy.verified = observe(f.ctx.layout(), &legacy, &CancelToken::new()).unwrap();
        legacy.verified.protected.remove(Path::new("e"));
        let record = state_path(f.ctx.layout(), legacy.id()).unwrap();
        let bytes = serde_json::to_vec(&legacy).unwrap();
        assert!(!String::from_utf8_lossy(&bytes).contains("storage_version"));
        fs::write(&record, &bytes).unwrap();
        let loaded = load(f.ctx.layout(), legacy.id()).unwrap();
        assert_eq!(loaded.storage_version(), 0);
        assert_eq!(path(&loaded).unwrap(), old);
        assert_usable(&loaded).unwrap();
        assert_eq!(fs::read(&record).unwrap(), bytes);
        let ticket = begin(
            &f.ctx,
            &plan(&f.ctx, loaded.id(), 1, &["package/a.py".into()]).unwrap(),
        )
        .unwrap();
        assert!(ticket.state.verified.protected.contains_key(Path::new("e")));
        let recovered = recover(&f.ctx, &ticket, |_| Ok(())).unwrap();
        assert_eq!(path(&recovered).unwrap(), old);
        assert_eq!(recovered.storage_version(), 0);
        assert_eq!(recovered.generation(), 2);
    }

    #[test]
    fn legacy_dirty_without_e_baseline_recovers_only_while_new_container_is_empty() {
        let f = Fixture::new();
        let compact = path(&f.state).unwrap();
        let mut legacy = f.state.clone();
        legacy.storage_version = 0;
        let old = model::environment_path(&f.root, legacy.release_id(), legacy.id(), 0).unwrap();
        f.ctx.layout().ensure_dir(old.parent().unwrap()).unwrap();
        fs::rename(compact, &old).unwrap();
        legacy.verified = observe(f.ctx.layout(), &legacy, &CancelToken::new()).unwrap();
        save(f.ctx.layout(), &legacy).unwrap();
        let mut ticket = begin(
            &f.ctx,
            &plan(&f.ctx, legacy.id(), 1, &["package/a.py".into()]).unwrap(),
        )
        .unwrap();
        ticket.state.verified.protected.remove(Path::new("e"));
        ticket.state.pending.as_mut().unwrap().tree_sha256 =
            hash(&serde_json::to_vec(&ticket.state.verified).unwrap());
        let pending = ticket.state.pending.as_ref().unwrap();
        model::write_json_atomic(
            &f.root.join(&pending.directory).join("manifest.json"),
            pending,
        )
        .unwrap();
        save(f.ctx.layout(), &ticket.state).unwrap();
        let other = f.root.join("e/g0000000000000002");
        f.ctx.layout().ensure_dir(&other).unwrap();
        fs::write(other.join("sentinel"), b"unrecorded environment").unwrap();
        assert!(recover(&f.ctx, &ticket, |_| Ok(())).is_err());
        assert!(load(f.ctx.layout(), legacy.id()).unwrap().dirty());
        fs::remove_file(other.join("sentinel")).unwrap();
        fs::remove_dir(other).unwrap();
        let recovered = recover(&f.ctx, &ticket, |_| Ok(())).unwrap();
        assert_eq!(recovered.storage_version(), 0);
        assert_eq!(path(&recovered).unwrap(), old);
    }
    #[test]
    fn plan_rejects_prior_non_target_environment_damage() {
        let f = Fixture::new();
        let env = path(&f.state).unwrap();
        fs::write(env.join("package/a.py"), b"target damage").unwrap();
        fs::write(f.root.join("profiles/default/profile.json"), b"user edit").unwrap();
        assert!(plan(
            &f.ctx,
            f.state.id(),
            f.state.generation(),
            &["package/a.py".into()]
        )
        .is_ok());
        fs::write(env.join("protected.py"), b"prior foreign replacement").unwrap();
        assert!(plan(
            &f.ctx,
            f.state.id(),
            f.state.generation(),
            &["package/a.py".into()]
        )
        .is_err());
        assert!(!load(f.ctx.layout(), f.state.id()).unwrap().dirty());
    }
    #[test]
    fn base_python_change_disables_every_reference_and_blocks_package_plan() {
        let f = Fixture::new();
        let base = f.root.join("python/3.10.19/base.dll");
        f.ctx.layout().ensure_dir(base.parent().unwrap()).unwrap();
        fs::write(base, b"modified shared runtime").unwrap();
        assert!(assert_usable(&f.state).is_err());
        assert!(plan(
            &f.ctx,
            f.state.id(),
            f.state.generation(),
            &["package/a.py".into()]
        )
        .is_err());
    }
    #[cfg(windows)]
    #[test]
    fn only_the_exact_managed_minor_junction_is_recorded_without_traversal() {
        let f = Fixture::new();
        let root = f.root.join("python/3.10.19");
        let target = root.join("cpython-3.10.19-windows-x86_64-none");
        f.ctx.layout().ensure_dir(&target).unwrap();
        fs::write(target.join("python.exe"), b"fixed python").unwrap();
        let alias = root.join("cpython-3.10-windows-x86_64-none");
        junction::create(&target, &alias).unwrap();
        let observed = observe(f.ctx.layout(), &f.state, &CancelToken::new()).unwrap();
        let tree = &observed.protected[Path::new("python/3.10.19")];
        assert!(matches!(
            tree.get(Path::new("cpython-3.10-windows-x86_64-none")),
            Some(Node::PythonAlias(_))
        ));
        assert!(!tree.contains_key(Path::new("cpython-3.10-windows-x86_64-none/python.exe")));
        junction::delete(&alias).unwrap();
        // junction::delete 只移除重解析数据，随后删除留下的空目录。
        fs::remove_dir(&alias).unwrap();
        let outside = f.root.join("outside");
        f.ctx.layout().ensure_dir(&outside).unwrap();
        junction::create(&outside, &alias).unwrap();
        assert!(observe(f.ctx.layout(), &f.state, &CancelToken::new()).is_err());
        junction::delete(alias).unwrap();
    }
}

#[cfg(test)]
mod base_repair_tests {
    use super::*;
    struct Fixture {
        ctx: WorkspaceMutation,
        state: InstanceState,
    }
    impl Fixture {
        fn new(clean: bool) -> Self {
            let root = std::env::temp_dir().join(format!(
                "nt-base-instance-{}-{}-{}",
                std::process::id(),
                model::now(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            let ctx =
                WorkspaceMutation::acquire(&root, &format!("dev-{}", "a".repeat(40))).unwrap();
            let base = root.join("python/3.10.19/base.dll");
            ctx.layout().ensure_dir(base.parent().unwrap()).unwrap();
            fs::write(base, b"old base").unwrap();
            let state = create(&ctx, "g0000000000000001", "recipe-one", &"b".repeat(64)).unwrap();
            fs::write(path(&state).unwrap().join("protected.py"), b"env unchanged").unwrap();
            let state = if clean {
                validate_new(&ctx, &state, &[], |_| Ok(())).unwrap()
            } else {
                state
            };
            Self { ctx, state }
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let root = &self.ctx.layout().root;
            if root.parent() == Some(std::env::temp_dir().as_path())
                && root
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with("nt-base-instance-")
            {
                let _ = fs::remove_dir_all(root);
            }
        }
    }
    #[test]
    fn base_candidate_commit_stays_unusable_until_global_gate_is_removed() {
        let f = Fixture::new(true);
        let layout = f.ctx.layout();
        let txn = "base-python-cohort-test";
        let original = base_reference_sha(&f.state).unwrap();
        let mut registry = model::Registry::load(&layout.root).unwrap();
        registry.schema_version = 3;
        registry.base_python_pending = Some(txn.into());
        registry.store(&layout.root).unwrap();
        quarantine_for_base(layout, f.state.id(), &original, txn).unwrap();
        let pending = load(layout, f.state.id()).unwrap();
        assert!(pending.dirty());
        assert_eq!(pending.generation(), 2);
        assert!(assert_usable(&pending).is_err());
        fs::write(layout.root.join("python/3.10.19/base.dll"), b"new base").unwrap();
        let bytes =
            candidate_after_base(layout, f.state.id(), txn, &CancelToken::new(), |_| Ok(()))
                .unwrap();
        commit_after_base(layout, f.state.id(), txn, &bytes).unwrap();
        let committed = load(layout, f.state.id()).unwrap();
        assert!(!committed.dirty());
        assert!(assert_usable(&committed).is_err());
        commit_after_base(layout, f.state.id(), txn, &bytes).unwrap();
        registry.base_python_pending = None;
        registry.store(&layout.root).unwrap();
        assert_usable(&committed).unwrap();
    }
    #[test]
    fn first_install_orphan_remains_dirty_and_does_not_invoke_validator() {
        let f = Fixture::new(false);
        let layout = f.ctx.layout();
        let txn = "base-python-orphan-test";
        quarantine_for_base(
            layout,
            f.state.id(),
            &base_reference_sha(&f.state).unwrap(),
            txn,
        )
        .unwrap();
        fs::write(layout.root.join("python/3.10.19/base.dll"), b"new base").unwrap();
        let bytes = candidate_after_base(layout, f.state.id(), txn, &CancelToken::new(), |_| {
            panic!("unvalidated orphan must remain dirty")
        })
        .unwrap();
        commit_after_base(layout, f.state.id(), txn, &bytes).unwrap();
        let result = load(layout, f.state.id()).unwrap();
        assert!(result.dirty());
        assert_eq!(result.generation(), 1);
        assert_eq!(result.validated_generation, 0);
        assert!(assert_usable(&result).is_err());
    }
    #[test]
    fn base_transaction_rejects_prior_environment_damage_and_state_reinterpretation() {
        let f = Fixture::new(true);
        let layout = f.ctx.layout();
        let txn = "base-python-tamper-test";
        fs::write(layout.root.join("python/3.10.19/base.dll"), b"damaged base").unwrap();
        base_reference_validate_before(layout, &f.state).unwrap();
        fs::write(
            path(&f.state).unwrap().join("protected.py"),
            b"prior wheel change",
        )
        .unwrap();
        assert!(base_reference_validate_before(layout, &f.state).is_err());
        let original = base_reference_sha(&f.state).unwrap();
        quarantine_for_base(layout, f.state.id(), &original, txn).unwrap();
        assert!(quarantine_for_base(layout, f.state.id(), &"d".repeat(64), txn).is_err());
        let mut tampered = load(layout, f.state.id()).unwrap();
        tampered.recipe_id = "foreign-recipe".into();
        save(layout, &tampered).unwrap();
        assert!(
            candidate_after_base(layout, f.state.id(), txn, &CancelToken::new(), |_| Ok(()))
                .is_err()
        );
        assert!(load(layout, f.state.id()).unwrap().dirty());
    }
    #[test]
    fn storage_zero_and_one_cohort_keeps_both_absolute_paths_and_blocks_partial_commit() {
        let f = Fixture::new(true);
        let layout = f.ctx.layout();
        let txn = "base-python-two-storage";
        let compact = path(&f.state).unwrap();
        let mut legacy = f.state.clone();
        legacy.instance_id = "legacy-orphan".into();
        legacy.storage_version = 0;
        let legacy_path = path(&legacy).unwrap();
        layout.ensure_dir(&legacy_path).unwrap();
        fs::write(legacy_path.join("protected.py"), b"legacy unchanged").unwrap();
        legacy.verified = observe(layout, &legacy, &CancelToken::new()).unwrap();
        save(layout, &legacy).unwrap();
        base_reference_validate_before(layout, &f.state).unwrap();
        base_reference_validate_before(layout, &legacy).unwrap();
        let before_compact = fs::read(compact.join("protected.py")).unwrap();
        let before_legacy = fs::read(legacy_path.join("protected.py")).unwrap();
        let mut registry = model::Registry::load(&layout.root).unwrap();
        registry.schema_version = 3;
        registry.base_python_pending = Some(txn.into());
        registry.store(&layout.root).unwrap();
        for state in [&f.state, &legacy] {
            quarantine_for_base(layout, state.id(), &base_reference_sha(state).unwrap(), txn)
                .unwrap();
        }
        fs::write(
            layout.root.join("python/3.10.19/base.dll"),
            b"new shared component",
        )
        .unwrap();
        let compact_candidate =
            candidate_after_base(layout, f.state.id(), txn, &CancelToken::new(), |at| {
                assert_eq!(at, compact);
                Ok(())
            })
            .unwrap();
        let legacy_candidate =
            candidate_after_base(layout, legacy.id(), txn, &CancelToken::new(), |at| {
                assert_eq!(at, legacy_path);
                Ok(())
            })
            .unwrap();
        commit_after_base(layout, f.state.id(), txn, &compact_candidate).unwrap();
        assert!(assert_usable(&load(layout, f.state.id()).unwrap()).is_err());
        assert!(load(layout, legacy.id()).unwrap().dirty());
        commit_after_base(layout, legacy.id(), txn, &legacy_candidate).unwrap();
        assert!(assert_usable(&load(layout, legacy.id()).unwrap()).is_err());
        registry.base_python_pending = None;
        registry.store(&layout.root).unwrap();
        let compact_state = load(layout, f.state.id()).unwrap();
        let legacy_state = load(layout, legacy.id()).unwrap();
        assert_usable(&compact_state).unwrap();
        assert_usable(&legacy_state).unwrap();
        assert_eq!(path(&compact_state).unwrap(), compact);
        assert_eq!(path(&legacy_state).unwrap(), legacy_path);
        assert_eq!(
            fs::read(compact.join("protected.py")).unwrap(),
            before_compact
        );
        assert_eq!(
            fs::read(legacy_path.join("protected.py")).unwrap(),
            before_legacy
        );
    }
}
