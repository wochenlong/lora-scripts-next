//! 显式GUI重建：新最终路径、旧绑定最后切换；失败候选精确封存，旧pending继续可恢复。
use crate::{
    gui_registration_integrity::{self, TrustedEnvironment},
    instances::{self, RebuildBoundary},
    model::{self, EnvironmentBinding, Layout, Registry, Release, WorkspaceMutation},
    operations::CancelToken,
    recipe::GuiRecipe,
};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};
static NEXT: AtomicU64 = AtomicU64::new(0);
pub(crate) fn verified_history(
    layout: &Layout,
    release: &Release,
    transaction: &str,
) -> Result<Vec<u8>> {
    let bytes = read(layout, &intent_path(layout, transaction)?)?;
    let intent: Intent = serde_json::from_slice(&bytes)?;
    validate(layout, release, &intent)?;
    if intent.status != "committed"
        || intent.terminal_status.as_deref() != Some("committed")
        || intent.plan.old_binding.is_none()
    {
        bail!("该重建记录没有可回退的旧绑定");
    }
    let desired_id = intent
        .new_registry
        .as_ref()
        .context("重建history缺少newregistry")?;
    let desired: Registry =
        serde_json::from_slice(&saved(layout, &intent, "registry-new.json", desired_id)?)?;
    desired.validate()?;
    let mut expected: Registry = serde_json::from_slice(&saved(
        layout,
        &intent,
        "registry-old.json",
        &intent.old_registry,
    )?)?;
    let proof = intent.proof.as_ref().context("重建history缺少可信证明")?;
    if proof.environment
        != model::environment_path(&layout.root, &release.id, &intent.candidate_id, 1)?
        || proof.recipe_sha256 != RECIPE_SHA
        || proof.trusted_index_sha256 != gui_registration_integrity::trusted_index_sha256()
    {
        bail!("重建history可信身份不符");
    }
    expected.schema_version = expected.schema_version.max(2);
    expected.record_installed(release)?;
    expected.bind_gui(
        &release.id,
        EnvironmentBinding {
            instance_id: intent.candidate_id.clone(),
            storage_version: 1,
            recipe_id: GuiRecipe::embedded()?.id().into(),
            recipe_sha256: RECIPE_SHA.into(),
            generation: 1,
        },
    )?;
    if desired != expected {
        bail!("重建history语义不符");
    }
    Ok(bytes)
}
pub(crate) fn rollback_preview(
    root: &Path,
    release: &Release,
    history_transaction: &str,
) -> Result<Value> {
    super::gui_binding_switch::preview(root, release, history_transaction)
}
pub(crate) fn rollback(
    ctx: &WorkspaceMutation,
    release: &Release,
    history_transaction: &str,
    expected: &str,
    cancel: &CancelToken,
    validator: impl Fn(&Path) -> Result<()>,
    entry_probe: impl Fn(&Path, &str) -> Result<()>,
) -> Result<Value> {
    super::gui_binding_switch::execute(
        ctx,
        release,
        history_transaction,
        expected,
        cancel,
        validator,
        entry_probe,
    )
}
pub(crate) fn recover_rollback(
    ctx: &WorkspaceMutation,
    release: &Release,
    cancel: &CancelToken,
    validator: impl Fn(&Path) -> Result<()>,
    entry_probe: impl Fn(&Path, &str) -> Result<()>,
) -> Result<Value> {
    super::gui_binding_switch::recover(ctx, release, cancel, validator, entry_probe)
}
pub(crate) fn preserved_pending(root: &Path, release: &Release) -> Result<Value> {
    let pending: Vec<_> = instances::preserved_pending(root)?
        .into_iter()
        .filter(|v| v["release_id"].as_str() == Some(&release.id))
        .collect();
    Ok(
        json!({"status":if pending.is_empty(){"ready"}else{"preserved_pending"},"instances":pending}),
    )
}
const RECIPE_SHA: &str = "8be2a44b43a8caee1df2c80212897e2edb382ce5dcc78c49fbc34b1cc416d090";
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Identity {
    bytes: u64,
    sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Plan {
    schema_version: u32,
    root_absolute: PathBuf,
    release_id: String,
    registry: Identity,
    boundary_sha256: String,
    old_binding: Option<EnvironmentBinding>,
    missing_wheels: Vec<String>,
    estimated_network_bytes: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Intent {
    schema_version: u32,
    transaction: String,
    root_absolute: PathBuf,
    release_id: String,
    candidate_id: String,
    status: String,
    plan: Plan,
    plan_sha256: String,
    boundary_sha256: String,
    old_registry: Identity,
    candidate_state: Option<Identity>,
    candidate_tree_sha256: Option<String>,
    proof: Option<TrustedEnvironment>,
    new_registry: Option<Identity>,
    preservation_file: Option<String>,
    preservation_sha256: Option<String>,
    terminal_status: Option<String>,
    failure: Option<String>,
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn identity(bytes: &[u8]) -> Identity {
    Identity {
        bytes: bytes.len() as u64,
        sha256: hash(bytes),
    }
}
fn encode<T: Serialize>(value: &T) -> Result<Vec<u8>> {
    let mut bytes = serde_json::to_vec_pretty(value)?;
    bytes.push(b'\n');
    Ok(bytes)
}
fn read(layout: &Layout, path: &Path) -> Result<Vec<u8>> {
    layout.guard_path(path)?;
    let meta = fs::symlink_metadata(path)?;
    if !meta.is_file() || meta.len() > 32 * 1024 * 1024 {
        bail!("重建状态只接受限额普通文件");
    }
    let bytes = fs::read(path)?;
    if bytes.len() as u64 != meta.len() {
        bail!("重建状态读取变化");
    }
    Ok(bytes)
}
fn intent_path(layout: &Layout, transaction: &str) -> Result<PathBuf> {
    model::validate_component(transaction)?;
    let path = layout
        .root
        .join("state/gui-rebuild")
        .join(format!("{transaction}.json"));
    layout.guard_path(&path)?;
    Ok(path)
}
fn snapshot(layout: &Layout, transaction: &str, name: &str, bytes: &[u8]) -> Result<()> {
    model::validate_component(name)?;
    let path = layout.root.join("backups").join(transaction).join(name);
    if path.exists() {
        if read(layout, &path)? != bytes {
            bail!("重建快照重名内容不同");
        }
        Ok(())
    } else {
        model::write_gui_transaction_bytes(&layout.root, transaction, &path, bytes)
    }
}
fn saved(layout: &Layout, intent: &Intent, name: &str, expected: &Identity) -> Result<Vec<u8>> {
    let bytes = read(
        layout,
        &layout
            .root
            .join("backups")
            .join(&intent.transaction)
            .join(name),
    )?;
    if identity(&bytes) != *expected {
        bail!("重建快照身份不符");
    }
    Ok(bytes)
}
fn store(layout: &Layout, intent: &Intent) -> Result<()> {
    model::write_gui_transaction_json(
        &layout.root,
        &intent.transaction,
        &intent_path(layout, &intent.transaction)?,
        intent,
    )
}
fn validate(layout: &Layout, release: &Release, intent: &Intent) -> Result<()> {
    model::validate_component(&intent.transaction)?;
    model::validate_environment_storage(&intent.candidate_id, 1)?;
    if intent.schema_version != 1
        || !intent.transaction.starts_with("gui-rebuild-")
        || intent.root_absolute != layout.root
        || intent.release_id != release.id
        || layout
            .release_dir
            .file_name()
            .and_then(|name| name.to_str())
            != Some(release.id.as_str())
        || intent.plan.schema_version != 1
        || intent.plan.root_absolute != layout.root
        || intent.plan.release_id != release.id
        || intent.plan_sha256 != hash(&serde_json::to_vec(&intent.plan)?)
        || intent.boundary_sha256 != intent.plan.boundary_sha256
        || intent.old_registry != intent.plan.registry
        || !matches!(
            intent.status.as_str(),
            "creating" | "building" | "validating" | "committing" | "committed" | "orphaned"
        )
    {
        bail!("重建事务身份或schema不符");
    }
    let old: Registry = serde_json::from_slice(&saved(
        layout,
        intent,
        "registry-old.json",
        &intent.old_registry,
    )?)?;
    old.validate()?;
    old.assert_base_python_ready()?;
    if old.gui_binding(&release.id) != intent.plan.old_binding.as_ref() {
        bail!("重建原binding与快照断联");
    }
    let boundary: RebuildBoundary = serde_json::from_slice(&read(
        layout,
        &layout
            .root
            .join("backups")
            .join(&intent.transaction)
            .join("boundary.json"),
    )?)?;
    if instances::rebuild_boundary_sha(&boundary)? != intent.boundary_sha256 {
        bail!("重建边界快照损坏");
    }
    Ok(())
}
fn all(layout: &Layout) -> Result<Vec<Intent>> {
    let base = layout.root.join("state/gui-rebuild");
    layout.guard_path(&base)?;
    let mut intents = Vec::new();
    if base.exists() {
        for entry in fs::read_dir(base)? {
            let path = entry?.path();
            layout.guard_path(&path)?;
            if path.extension().is_none_or(|e| e != "json") {
                bail!("重建事务容器含未知文件");
            }
            let intent: Intent = serde_json::from_slice(&read(layout, &path)?)?;
            if path
                .file_stem()
                .is_none_or(|s| s != intent.transaction.as_str())
            {
                bail!("重建事务文件名不匹配");
            }
            intents.push(intent);
        }
    }
    Ok(intents)
}
pub(crate) fn assert_ready(root: &Path, release: &Release) -> Result<()> {
    let layout = Layout::new(root, &release.id)?;
    for intent in all(&layout)? {
        let owner = crate::model::Catalog::embedded()?
            .release(&intent.release_id)?
            .clone();
        validate(&Layout::new(root, &owner.id)?, &owner, &intent)?;
        if !matches!(intent.status.as_str(), "committed" | "orphaned") {
            bail!("GUI重建事务{}待恢复", intent.transaction);
        }
    }
    Ok(())
}
/// 只读历史供界面明确选择；执行时仍需完整复验目标。
pub(crate) fn history(root: &Path, release: &Release) -> Result<Value> {
    let layout = Layout::new(root, &release.id)?;
    let current = Registry::load(root)?.gui_binding(&release.id).cloned();
    let mut records = Vec::new();
    let mut pending = Vec::new();
    for intent in all(&layout)? {
        if intent.release_id != release.id {
            continue;
        }
        validate(&layout, release, &intent)?;
        if !matches!(intent.status.as_str(), "committed" | "orphaned") {
            pending.push(
                json!({"kind":"rebuild","transaction":intent.transaction,"status":intent.status}),
            );
        }
        let rollback_available = intent.plan.old_binding.as_ref().is_some_and(|target| {
            if current.as_ref() == Some(target)
                || verified_history(&layout, release, &intent.transaction).is_err()
            {
                return false;
            }
            instances::load(&layout, &target.instance_id).is_ok_and(|state| {
                !state.dirty()
                    && state.storage_version() == target.storage_version
                    && state.generation() == target.generation
                    && state.recipe_id() == target.recipe_id
                    && state.recipe_sha256() == target.recipe_sha256
            })
        });
        records.push(json!({"transaction":intent.transaction,"status":intent.status,"candidate_id":intent.candidate_id,"old_instance_id":intent.plan.old_binding.as_ref().map(|b| &b.instance_id),"rollback_available":rollback_available,"failure":intent.failure}));
    }
    if let Some(value) = super::gui_binding_switch::pending(root, release)? {
        pending.push(value);
    }
    records.sort_by_key(|v| v["transaction"].as_str().unwrap_or_default().to_owned());
    let preserved = preserved_pending(root, release)?;
    Ok(
        json!({"status":if pending.is_empty(){"ready"}else{"pending"},"records":records,"pending_transactions":pending,"preserved_pending":preserved["instances"]}),
    )
}
fn plan(
    layout: &Layout,
    release: &Release,
    cancel: &CancelToken,
) -> Result<(Plan, RebuildBoundary)> {
    assert_ready(&layout.root, release)?;
    super::gui_binding_switch::assert_ready(&layout.root, release)?;
    let registry = Registry::load(&layout.root)?;
    registry.assert_base_python_ready()?;
    let recipe = GuiRecipe::embedded()?;
    if release.commit != recipe.source_commit
        || !recipe.matches_environment_recipe(&release.environment_recipe)
    {
        bail!("重建不匹配固定配方");
    }
    if crate::model::ReleaseReceipt::load(&layout.release_dir)?.release != *release {
        bail!("重建需要同发布有效receipt；请先补登记");
    }
    crate::source_integrity::verify(layout, release)?;
    crate::python_integrity::verify(layout)?;
    if crate::core::digest(&layout.root.join("tools/uv.exe"))? != recipe.tool_uv.exe_sha256 {
        bail!("uv固定工具损坏，先修复工具");
    }
    let registry_bytes = read(layout, &layout.root.join("state/registry.json"))?;
    let boundary = instances::rebuild_observe_boundary(layout, cancel)?;
    let mut missing = Vec::new();
    let mut network = 0u64;
    for wheel in &recipe.wheels {
        let path = layout.root.join("cache/wheelhouse").join(&wheel.filename);
        layout.guard_path(&path)?;
        if path.exists() {
            if !fs::symlink_metadata(&path)?.is_file()
                || fs::metadata(&path)?.len() != wheel.bytes
                || crate::core::digest(&path)? != wheel.sha256
            {
                bail!("已有wheelhouse文件损坏，不覆盖");
            }
        } else {
            missing.push(wheel.filename.clone());
            network = network.checked_add(wheel.bytes).context("预算溢出")?;
        }
    }
    Ok((
        Plan {
            schema_version: 1,
            root_absolute: layout.root.clone(),
            release_id: release.id.clone(),
            registry: identity(&registry_bytes),
            boundary_sha256: instances::rebuild_boundary_sha(&boundary)?,
            old_binding: registry.gui_binding(&release.id).cloned(),
            missing_wheels: missing,
            estimated_network_bytes: network,
        },
        boundary,
    ))
}
pub(crate) fn preview(root: &Path, release: &Release) -> Result<Value> {
    let layout = Layout::new(root, &release.id)?;
    match plan(&layout, release, &CancelToken::new()) {
        Ok((plan, _)) => Ok(
            json!({"status":"ready","plan_sha256":hash(&serde_json::to_vec(&plan)?),"plan":plan,"actions":["create_new_final_environment","offline_locked_sync","full_trusted_integrity","isolated_entry_probe","preserve_old_transactions","switch_binding_last"]}),
        ),
        Err(error) => {
            let records = history(root, release)?;
            let pending = records["pending_transactions"].clone();
            Ok(
                json!({"status":if pending.as_array().is_some_and(|p| !p.is_empty()) {"pending"} else {"blocked"},"reason":format!("{error:#}"),"pending_transactions":pending}),
            )
        }
    }
}
pub(crate) fn execute(
    ctx: &WorkspaceMutation,
    release: &Release,
    expected: &str,
    cancel: &CancelToken,
    builder: impl Fn(&Path) -> Result<()>,
    validator: impl Fn(&Path) -> Result<()>,
    entry_probe: impl Fn(&Path, &str) -> Result<()>,
) -> Result<Value> {
    let layout = ctx.layout();
    let (plan, boundary) = plan(layout, release, cancel)?;
    let plan_sha256 = hash(&serde_json::to_vec(&plan)?);
    if expected != plan_sha256 {
        bail!("重建预览已变化");
    }
    let serial = NEXT.fetch_add(1, Ordering::Relaxed);
    let transaction = format!(
        "gui-rebuild-{}-{}-{serial}",
        model::now(),
        std::process::id()
    );
    let candidate_id = format!(
        "g{:.16}",
        hash(
            format!(
                "{}:{}:{}:{serial}",
                layout.root.display(),
                release.id,
                transaction
            )
            .as_bytes()
        )
    );
    let environment = model::environment_path(&layout.root, &release.id, &candidate_id, 1)?;
    if environment.exists()
        || layout
            .root
            .join("state/instances")
            .join(format!("{candidate_id}.json"))
            .exists()
    {
        bail!("重建新候选命名冲突");
    }
    let old = read(layout, &layout.root.join("state/registry.json"))?;
    snapshot(layout, &transaction, "registry-old.json", &old)?;
    snapshot(layout, &transaction, "boundary.json", &encode(&boundary)?)?;
    let mut intent = Intent {
        schema_version: 1,
        transaction,
        root_absolute: layout.root.clone(),
        release_id: release.id.clone(),
        candidate_id,
        status: "creating".into(),
        boundary_sha256: plan.boundary_sha256.clone(),
        old_registry: plan.registry.clone(),
        plan,
        plan_sha256,
        candidate_state: None,
        candidate_tree_sha256: None,
        proof: None,
        new_registry: None,
        preservation_file: None,
        preservation_sha256: None,
        terminal_status: None,
        failure: None,
    };
    store(layout, &intent)?;
    let recipe = GuiRecipe::embedded()?;
    let outcome = (|| {
        instances::rebuild_create(
            ctx,
            &intent.candidate_id,
            recipe.id(),
            RECIPE_SHA,
            &intent.transaction,
            cancel,
        )?;
        intent.status = "building".into();
        store(layout, &intent)?;
        let engine_controls = instances::engine_control_digest(layout)?;
        builder(&environment)?;
        if instances::engine_control_digest(layout)? != engine_controls {
            bail!("GUI重建改变引擎控制记录");
        }
        intent.status = "validating".into();
        store(layout, &intent)?;
        verify_candidate(
            ctx,
            release,
            &mut intent,
            &boundary,
            cancel,
            &validator,
            &entry_probe,
        )?;
        Ok(())
    })();
    if let Err(error) = outcome {
        intent.failure = Some(format!("{error:#}"));
        // 使用新token封存partial；用户取消不能跳过旧事务保全并永久卡死旧恢复。
        prepare_commit(
            ctx,
            release,
            &mut intent,
            &boundary,
            false,
            &CancelToken::new(),
        )?;
        finish(
            ctx,
            release,
            &mut intent,
            &CancelToken::new(),
            &validator,
            &entry_probe,
        )?;
        return Err(error);
    }
    prepare_commit(ctx, release, &mut intent, &boundary, true, cancel)?;
    finish(ctx, release, &mut intent, cancel, &validator, &entry_probe)
}
fn verify_candidate(
    ctx: &WorkspaceMutation,
    release: &Release,
    intent: &mut Intent,
    boundary: &RebuildBoundary,
    cancel: &CancelToken,
    validator: &impl Fn(&Path) -> Result<()>,
    entry_probe: &impl Fn(&Path, &str) -> Result<()>,
) -> Result<()> {
    let layout = ctx.layout();
    let environment = model::environment_path(&layout.root, &release.id, &intent.candidate_id, 1)?;
    crate::source_integrity::verify(layout, release)?;
    crate::python_integrity::verify(layout)?;
    let proof = gui_registration_integrity::verify(layout, release, &environment, cancel)?;
    instances::rebuild_validate_candidate(
        ctx,
        boundary,
        &intent.candidate_id,
        &intent.transaction,
        cancel,
        |environment| {
            validator(environment)?;
            entry_probe(environment, &intent.transaction)
        },
    )?;
    intent.proof = Some(proof);
    Ok(())
}
fn prepare_commit(
    ctx: &WorkspaceMutation,
    release: &Release,
    intent: &mut Intent,
    boundary: &RebuildBoundary,
    success: bool,
    cancel: &CancelToken,
) -> Result<()> {
    let layout = ctx.layout();
    validate(layout, release, intent)?;
    instances::rebuild_check_boundary(ctx, boundary, &intent.candidate_id, cancel)?;
    if !success {
        instances::rebuild_mark_orphan(ctx, &intent.candidate_id, &intent.transaction)?;
    }
    let state = instances::load(layout, &intent.candidate_id)?;
    let state_path = layout
        .root
        .join("state/instances")
        .join(format!("{}.json", state.id()));
    intent.candidate_state = Some(identity(&read(layout, &state_path)?));
    intent.candidate_tree_sha256 = Some(instances::rebuild_candidate_tree_sha(layout, state.id())?);
    let preservation =
        instances::rebuild_preservation(ctx, &intent.transaction, boundary, state.id(), cancel)?;
    let preservation_bytes = encode(&preservation)?;
    let preservation_sha256 = hash(&preservation_bytes);
    let preservation_file = format!("preservation-{preservation_sha256}.json");
    snapshot(
        layout,
        &intent.transaction,
        &preservation_file,
        &preservation_bytes,
    )?;
    intent.preservation_file = Some(preservation_file);
    intent.preservation_sha256 = Some(preservation_sha256);
    if success {
        if state.dirty() || intent.proof.is_none() {
            bail!("未完成真实验证不能绑定重建候选");
        }
        let mut registry: Registry = serde_json::from_slice(&saved(
            layout,
            intent,
            "registry-old.json",
            &intent.old_registry,
        )?)?;
        registry.schema_version = registry.schema_version.max(2);
        registry.record_installed(release)?;
        registry.bind_gui(
            &release.id,
            EnvironmentBinding {
                instance_id: state.id().into(),
                storage_version: state.storage_version(),
                recipe_id: state.recipe_id().into(),
                recipe_sha256: state.recipe_sha256().into(),
                generation: state.generation(),
            },
        )?;
        let bytes = encode(&registry)?;
        snapshot(layout, &intent.transaction, "registry-new.json", &bytes)?;
        intent.new_registry = Some(identity(&bytes));
        intent.terminal_status = Some("committed".into());
    } else {
        intent.terminal_status = Some("orphaned".into());
    }
    intent.status = "committing".into();
    store(layout, intent)
}
fn finish(
    ctx: &WorkspaceMutation,
    release: &Release,
    intent: &mut Intent,
    cancel: &CancelToken,
    validator: &impl Fn(&Path) -> Result<()>,
    entry_probe: &impl Fn(&Path, &str) -> Result<()>,
) -> Result<Value> {
    let layout = ctx.layout();
    validate(layout, release, intent)?;
    if intent.status != "committing" {
        bail!("重建尚未持久化完整提交许可");
    }
    let boundary: RebuildBoundary = serde_json::from_slice(&read(
        layout,
        &layout
            .root
            .join("backups")
            .join(&intent.transaction)
            .join("boundary.json"),
    )?)?;
    instances::rebuild_check_boundary(ctx, &boundary, &intent.candidate_id, cancel)?;
    let state = instances::load(layout, &intent.candidate_id)?;
    let recipe = GuiRecipe::embedded()?;
    if state.release_id() != release.id
        || state.storage_version() != 1
        || state.generation() != 1
        || state.recipe_id() != recipe.id
        || state.recipe_sha256() != RECIPE_SHA
    {
        bail!("重建候选state与固定配方或初始epoch断联");
    }
    let state_bytes = read(
        layout,
        &layout
            .root
            .join("state/instances")
            .join(format!("{}.json", state.id())),
    )?;
    if Some(identity(&state_bytes)) != intent.candidate_state
        || Some(instances::rebuild_candidate_tree_sha(layout, state.id())?)
            != intent.candidate_tree_sha256
    {
        bail!("重建提交候选变化，保留gate");
    }
    let preservation = read(
        layout,
        &layout.root.join("backups").join(&intent.transaction).join(
            intent
                .preservation_file
                .as_ref()
                .context("缺少保护快照名")?,
        ),
    )?;
    if Some(hash(&preservation)) != intent.preservation_sha256 {
        bail!("重建preservation快照变化");
    }
    let target = layout.root.join("state/registry.json");
    let current = identity(&read(layout, &target)?);
    match intent.terminal_status.as_deref() {
        Some("committed") => {
            let proof = gui_registration_integrity::verify(
                layout,
                release,
                &instances::path(&state)?,
                cancel,
            )?;
            if intent.proof.as_ref() != Some(&proof) || state.dirty() {
                bail!("重建提交前固定证明不符");
            }
            instances::registration_revalidate(layout, &state, false, cancel, |environment| {
                validator(environment)?;
                entry_probe(environment, &intent.transaction)
            })?;
            let desired_id = intent
                .new_registry
                .as_ref()
                .context("重建缺少new registry")?;
            let desired = saved(layout, intent, "registry-new.json", desired_id)?;
            let registry: Registry = serde_json::from_slice(&desired)?;
            registry.validate()?;
            let mut expected: Registry = serde_json::from_slice(&saved(
                layout,
                intent,
                "registry-old.json",
                &intent.old_registry,
            )?)?;
            expected.schema_version = expected.schema_version.max(2);
            expected.record_installed(release)?;
            expected.bind_gui(
                &release.id,
                EnvironmentBinding {
                    instance_id: state.id().into(),
                    storage_version: state.storage_version(),
                    recipe_id: state.recipe_id().into(),
                    recipe_sha256: state.recipe_sha256().into(),
                    generation: state.generation(),
                },
            )?;
            let current = identity(&read(layout, &target)?);
            if Some(identity(&read(
                layout,
                &layout
                    .root
                    .join("state/instances")
                    .join(format!("{}.json", state.id())),
            )?)) != intent.candidate_state
                || Some(instances::rebuild_candidate_tree_sha(layout, state.id())?)
                    != intent.candidate_tree_sha256
            {
                bail!("真实复验后candidate变化，不提交binding");
            }
            if registry != expected || (current != intent.old_registry && current != *desired_id) {
                bail!("重建registry语义/二态不符");
            }
            if current != *desired_id {
                model::write_gui_transaction_bytes(
                    &layout.root,
                    &intent.transaction,
                    &target,
                    &desired,
                )?;
            }
        }
        Some("orphaned") => {
            if current != intent.old_registry || intent.new_registry.is_some() {
                bail!("失败封存不改旧binding/registry");
            }
        }
        _ => bail!("重建终态许可无效"),
    }
    intent.status = intent.terminal_status.clone().context("缺少终态")?;
    store(layout, intent)?;
    Ok(
        json!({"status":intent.status,"transaction":intent.transaction,"candidate_id":intent.candidate_id,"failure":intent.failure,"old_binding_preserved":intent.status=="orphaned","old_transactions_preserved":true}),
    )
}
pub(crate) fn recover(
    ctx: &WorkspaceMutation,
    release: &Release,
    transaction: &str,
    cancel: &CancelToken,
    validator: impl Fn(&Path) -> Result<()>,
    entry_probe: impl Fn(&Path, &str) -> Result<()>,
) -> Result<Value> {
    let layout = ctx.layout();
    let mut intent: Intent =
        serde_json::from_slice(&read(layout, &intent_path(layout, transaction)?)?)?;
    validate(layout, release, &intent)?;
    if matches!(intent.status.as_str(), "committed" | "orphaned") {
        return Ok(
            json!({"status":intent.status,"transaction":intent.transaction,"candidate_id":intent.candidate_id}),
        );
    }
    let boundary: RebuildBoundary = serde_json::from_slice(&read(
        layout,
        &layout
            .root
            .join("backups")
            .join(&intent.transaction)
            .join("boundary.json"),
    )?)?;
    if intent.status == "committing" {
        return finish(ctx, release, &mut intent, cancel, &validator, &entry_probe);
    }
    let recipe = GuiRecipe::embedded()?;
    instances::rebuild_create(
        ctx,
        &intent.candidate_id,
        recipe.id(),
        RECIPE_SHA,
        &intent.transaction,
        &CancelToken::new(),
    )?;
    let outcome = verify_candidate(
        ctx,
        release,
        &mut intent,
        &boundary,
        cancel,
        &validator,
        &entry_probe,
    );
    if let Err(error) = &outcome {
        intent.failure = Some(format!(
            "恢复时未通过完整验证，已精确保留为dirty orphan：{error:#}"
        ));
    }
    prepare_commit(
        ctx,
        release,
        &mut intent,
        &boundary,
        outcome.is_ok(),
        &CancelToken::new(),
    )?;
    finish(
        ctx,
        release,
        &mut intent,
        &CancelToken::new(),
        &validator,
        &entry_probe,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pending_fixture(status: &str) -> (WorkspaceMutation, Release, String, Vec<u8>) {
        let root = std::env::temp_dir().join(format!(
            "nt-rebuild-recovery-{}-{}-{}",
            std::process::id(),
            model::now(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let release = model::Catalog::embedded().unwrap().releases[0].clone();
        let ctx = WorkspaceMutation::acquire(&root, &release.id).unwrap();
        Registry::default().store(&root).unwrap();
        let layout = ctx.layout();
        let old = read(layout, &root.join("state/registry.json")).unwrap();
        let cancel = CancelToken::new();
        let boundary = instances::rebuild_observe_boundary(layout, &cancel).unwrap();
        let transaction = format!(
            "gui-rebuild-recovery-test-{}",
            NEXT.fetch_add(1, Ordering::Relaxed)
        );
        snapshot(layout, &transaction, "registry-old.json", &old).unwrap();
        snapshot(
            layout,
            &transaction,
            "boundary.json",
            &encode(&boundary).unwrap(),
        )
        .unwrap();
        let boundary_sha256 = instances::rebuild_boundary_sha(&boundary).unwrap();
        let plan = Plan {
            schema_version: 1,
            root_absolute: root.clone(),
            release_id: release.id.clone(),
            registry: identity(&old),
            boundary_sha256: boundary_sha256.clone(),
            old_binding: None,
            missing_wheels: vec![],
            estimated_network_bytes: 0,
        };
        let intent = Intent {
            schema_version: 1,
            transaction: transaction.clone(),
            root_absolute: root.clone(),
            release_id: release.id.clone(),
            candidate_id: "g0123456789abcdef".into(),
            status: status.into(),
            plan_sha256: hash(&serde_json::to_vec(&plan).unwrap()),
            old_registry: plan.registry.clone(),
            boundary_sha256,
            plan,
            candidate_state: None,
            candidate_tree_sha256: None,
            proof: None,
            new_registry: None,
            preservation_file: None,
            preservation_sha256: None,
            terminal_status: None,
            failure: None,
        };
        store(layout, &intent).unwrap();
        if status == "building" {
            let recipe = GuiRecipe::embedded().unwrap();
            instances::rebuild_create(
                &ctx,
                &intent.candidate_id,
                recipe.id(),
                RECIPE_SHA,
                &transaction,
                &cancel,
            )
            .unwrap();
            fs::write(
                root.join("e")
                    .join(&intent.candidate_id)
                    .join("partial.dll"),
                b"partial unchanged",
            )
            .unwrap();
        }
        (ctx, release, transaction, old)
    }

    #[test]
    fn interrupted_creation_and_partial_build_recover_without_reinstall_or_binding_change() {
        for status in ["creating", "building"] {
            let (ctx, release, transaction, old) = pending_fixture(status);
            let result = recover(
                &ctx,
                &release,
                &transaction,
                &CancelToken::new(),
                |_| panic!("不完整源码不能进入runtime验证"),
                |_, _| panic!("不完整源码不能进入入口探测"),
            )
            .unwrap();
            assert_eq!(result["status"], "orphaned");
            assert_eq!(
                fs::read(ctx.layout().root.join("state/registry.json")).unwrap(),
                old
            );
            assert!(instances::load(ctx.layout(), "g0123456789abcdef")
                .unwrap()
                .dirty());
            if status == "building" {
                assert_eq!(
                    fs::read(ctx.layout().root.join("e/g0123456789abcdef/partial.dll")).unwrap(),
                    b"partial unchanged"
                );
            }
            assert_ready(&ctx.layout().root, &release).unwrap();
            let root = ctx.layout().root.clone();
            drop(ctx);
            fs::remove_dir_all(root).unwrap();
        }
    }

    #[test]
    fn unknown_third_registry_refuses_orphan_commit_and_keeps_pending() {
        let (ctx, release, transaction, old) = pending_fixture("building");
        let third = b"{\"schema_version\":99}\n";
        fs::write(ctx.layout().root.join("state/registry.json"), third).unwrap();
        assert!(recover(
            &ctx,
            &release,
            &transaction,
            &CancelToken::new(),
            |_| Ok(()),
            |_, _| Ok(())
        )
        .is_err());
        assert_eq!(
            fs::read(ctx.layout().root.join("state/registry.json")).unwrap(),
            third
        );
        // 修复测试夹具的故意损坏后仍可检查原意图，产品路径不追认第三态。
        fs::write(ctx.layout().root.join("state/registry.json"), old).unwrap();
        let intent: Intent = serde_json::from_slice(
            &read(
                ctx.layout(),
                &intent_path(ctx.layout(), &transaction).unwrap(),
            )
            .unwrap(),
        )
        .unwrap();
        assert_ne!(intent.status, "committed");
        let root = ctx.layout().root.clone();
        drop(ctx);
        fs::remove_dir_all(root).unwrap();
    }
}
