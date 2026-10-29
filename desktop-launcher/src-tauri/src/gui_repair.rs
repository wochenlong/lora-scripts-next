//! 固定 GUI 配方的单包精准修复。RECORD 异常拒绝调用 uv；恢复快照不等于恢复健康。
//! intent 覆盖实例事务提交与 registry 登记之间的进程强杀窗口。
use crate::{
    instances::{self, InstanceState},
    model::{self, EnvironmentBinding, Layout, Registry, Release, WorkspaceMutation},
    operations::{
        CancelToken, Cancelled, OperationError, OperationHandle, OperationPhase, OperationStatus,
    },
    recipe::GuiRecipe,
    wheel_integrity::{self, IntegrityReport, PackageIntegrity},
};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, File},
    io::{Read, Write},
    path::{Component, Path, PathBuf},
};

const MAX_INTENT: u64 = 8 * 1024 * 1024;
const MAX_METADATA: u64 = 2 * 1024 * 1024;

#[derive(Debug, Serialize)]
pub(super) struct Diagnosis {
    pub root: PathBuf,
    pub release_id: String,
    pub instance_id: String,
    pub generation: u64,
    pub binding_generation: u64,
    pub dirty: bool,
    pub recipe_sha256: String,
    pub source_error: Option<String>,
    pub installed_metadata_error: Option<String>,
    pub recovery_pending: bool,
    pub integrity: IntegrityReport,
}

#[derive(Debug, Serialize)]
pub(super) struct RepairPreview {
    pub instance_id: String,
    pub generation: u64,
    pub package: String,
    pub version: String,
    pub paths: Vec<PathBuf>,
    pub plan_sha256: String,
    pub before_original_files_verified: bool,
    pub before_runtime_check: String,
    pub boundary: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Intent {
    schema_version: u32,
    component: String,
    root_absolute: PathBuf,
    release_id: String,
    instance_id: String,
    recipe_sha256: String,
    package: String,
    version: String,
    base_generation: u64,
    next_generation: u64,
    paths: Vec<PathBuf>,
    plan_sha256: String,
}

fn recipe(release: &Release) -> Result<GuiRecipe> {
    release.validate()?;
    let recipe = GuiRecipe::embedded()?;
    if release.commit != recipe.source_commit
        || release.python != recipe.python.version
        || release.uv != recipe.tool_uv
        || !recipe.matches_environment_recipe(&release.environment_recipe)
    {
        bail!("该发布版没有完全匹配的固定 GUI 修复配方");
    }
    Ok(recipe)
}

fn recipe_sha() -> String {
    hash(include_bytes!("../../catalog/gui-cp310-win-x64-v1.json"))
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn normalized(name: &str) -> String {
    let mut result = String::new();
    for byte in name.bytes() {
        if b"-_.".contains(&byte) {
            if !result.ends_with('-') {
                result.push('-');
            }
        } else {
            result.push(byte.to_ascii_lowercase() as char);
        }
    }
    result
}
fn intent_path(layout: &Layout, instance: &str) -> Result<PathBuf> {
    model::validate_component(instance)?;
    let path = layout
        .root
        .join("state/gui-repairs")
        .join(format!("{instance}.json"));
    layout.guard_path(&path)?;
    Ok(path)
}
fn small_text(layout: &Layout, path: &Path, limit: u64) -> Result<String> {
    layout.guard_path(path)?;
    let mut input = File::open(path)?;
    if !input.metadata()?.is_file() || input.metadata()?.len() > limit {
        bail!("修复元数据不是受限普通文件");
    }
    let mut text = String::new();
    Read::by_ref(&mut input)
        .take(limit + 1)
        .read_to_string(&mut text)?;
    if text.len() as u64 > limit {
        bail!("修复元数据读取超限");
    }
    Ok(text)
}

/// 不执行 Python/uv，不创建目录、不变更状态；生成脚本的内容验证边界见 integrity.generated。
pub(super) fn diagnose(root: &Path, release: &Release) -> Result<Diagnosis> {
    let recipe = recipe(release)?;
    let layout = Layout::new(root, &release.id)?;
    let registry = Registry::load(root)?;
    let binding = registry
        .gui_binding(&release.id)
        .context("该版本尚未绑定正式 GUI 实例")?;
    let instance = instances::load(&layout, &binding.instance_id)?;
    if binding.recipe_id != recipe.id()
        || binding.storage_version != instance.storage_version()
        || binding.recipe_sha256 != recipe_sha()
        || instance.recipe_id() != recipe.id()
        || instance.recipe_sha256() != binding.recipe_sha256
        || instances::path(&instance)? != layout.environment
    {
        bail!("实例、发布版与固定配方身份不一致");
    }
    let integrity = wheel_integrity::inspect(
        &layout,
        &layout.environment,
        &recipe,
        &root.join("cache/wheelhouse"),
    )?;
    Ok(Diagnosis {
        root: root.to_path_buf(),
        release_id: release.id.clone(),
        instance_id: instance.id().into(),
        generation: instance.generation(),
        binding_generation: binding.generation,
        dirty: instance.dirty(),
        recipe_sha256: recipe_sha(),
        source_error: super::verify_source(&layout, release)
            .err()
            .map(|error| format!("{error:#}")),
        installed_metadata_error: installed_metadata(&layout, &recipe)
            .err()
            .map(|error| format!("{error:#}")),
        recovery_pending: intent_path(&layout, instance.id())?.try_exists()?,
        integrity,
    })
}

/// 元数据集合先用普通文件静态核对，避免先启动未知包环境再判断能否修复。
fn installed_metadata(layout: &Layout, recipe: &GuiRecipe) -> Result<()> {
    let site = layout.environment.join("Lib/site-packages");
    layout.guard_path(&site)?;
    let expected: BTreeMap<_, _> = recipe
        .wheels
        .iter()
        .map(|wheel| (wheel.name.clone(), wheel.version.clone()))
        .collect();
    let mut actual = BTreeMap::new();
    for item in fs::read_dir(site)? {
        let item = item?;
        let name = item.file_name().to_string_lossy().into_owned();
        if name.to_ascii_lowercase().ends_with(".egg-info") {
            bail!("发现非固定 wheel 的 egg-info 安装记录");
        }
        if !name.to_ascii_lowercase().ends_with(".dist-info") {
            continue;
        }
        layout.guard_path(&item.path())?;
        if !item.file_type()?.is_dir() {
            bail!("dist-info 不是普通目录");
        }
        let text = small_text(layout, &item.path().join("METADATA"), MAX_METADATA)?;
        let mut package = None;
        let mut version = None;
        for line in text.lines().take_while(|line| !line.is_empty()) {
            if let Some(value) = line.strip_prefix("Name: ") {
                if package.replace(normalized(value.trim())).is_some() {
                    bail!("METADATA Name 重复");
                }
            }
            if let Some(value) = line.strip_prefix("Version: ") {
                if version.replace(value.trim().to_owned()).is_some() {
                    bail!("METADATA Version 重复");
                }
            }
        }
        let name = package.context("METADATA 缺少 Name")?;
        let version = version.context("METADATA 缺少 Version")?;
        if actual.insert(name, version).is_some() {
            bail!("已安装包存在重复规范名");
        }
    }
    if actual != expected {
        bail!("已安装包集合或版本与固定锁不一致；单包修复不会接管未知包");
    }
    Ok(())
}

fn record_safe(package: &PackageIntegrity) -> bool {
    package.issues.is_empty()
        && package
            .generated
            .iter()
            .filter(|generated| generated.kind == "rewritten_record")
            .all(|generated| generated.present && !package.damaged.contains(&generated.path))
        && package
            .generated
            .iter()
            .any(|generated| generated.kind == "rewritten_record")
}

fn select(diagnosis: &Diagnosis, name: &str) -> Result<RepairPreview> {
    if diagnosis.dirty || diagnosis.generation != diagnosis.binding_generation {
        bail!("实例 dirty 或登记 generation 不一致，必须先恢复既有事务");
    }
    if diagnosis.recovery_pending {
        bail!("存在待收尾修复 intent，请先恢复");
    }
    if let Some(error) = &diagnosis.source_error {
        bail!("源码完整性未通过：{error}");
    }
    if let Some(error) = &diagnosis.installed_metadata_error {
        bail!("安装元数据未通过：{error}");
    }
    let name = normalized(name);
    let target = diagnosis
        .integrity
        .packages
        .iter()
        .find(|package| package.name == name)
        .context("目标包不在固定配方中")?;
    for package in &diagnosis.integrity.packages {
        if !package.unsupported.is_empty() {
            bail!("配方存在尚不支持内容验证的包：{}", package.name);
        }
        if package.generated.iter().any(|generated| {
            generated.kind == "optional_derived_bytecode_unverified" && generated.present
        }) {
            bail!(
                "{} 存在未验证的生成字节码，固定无 bytecode 合同拒绝执行 Python/uv",
                package.name
            );
        }
        if !record_safe(package) {
            bail!("{} 的 RECORD 集合异常，拒绝让 uv 读取后卸载", package.name);
        }
        if package.name != name && (!package.missing.is_empty() || !package.damaged.is_empty()) {
            bail!("非目标包 {} 缺失或改变，请单独诊断", package.name);
        }
    }
    let paths = wheel_integrity::package_paths(&diagnosis.integrity, &name);
    if paths.is_empty() || paths.len() > 20_000 {
        bail!("目标包修复闭包为空或超过事务上限");
    }
    let before = diagnosis.integrity.original_files_verified();
    let mut preview = RepairPreview {
        instance_id: diagnosis.instance_id.clone(),
        generation: diagnosis.generation,
        package: name,
        version: target.version.clone(),
        paths,
        plan_sha256: String::new(),
        before_original_files_verified: before,
        before_runtime_check: if before {
            "pending_under_lease"
        } else {
            "blocked_by_damaged_original_files"
        }
        .into(),
        boundary:
            "原文件内容来自可信wheel；生成入口脚本只验证路径/存在性；回退快照仍须通过全量验证"
                .into(),
    };
    preview.plan_sha256 = hash(&serde_json::to_vec(&(diagnosis, &preview))?);
    Ok(preview)
}

pub(super) fn plan(root: &Path, release: &Release, package: &str) -> Result<RepairPreview> {
    select(&diagnose(root, release)?, package)
}

fn validate_intent(layout: &Layout, release: &Release, intent: &Intent) -> Result<()> {
    if intent.schema_version != 1
        || intent.component != "gui-package-repair"
        || intent.root_absolute != layout.root
        || intent.release_id != release.id
        || intent.recipe_sha256 != recipe_sha()
        || intent.base_generation == 0
        || intent.base_generation.checked_add(1) != Some(intent.next_generation)
        || intent.paths.is_empty()
        || intent.paths.len() > 20_000
        || intent.plan_sha256.len() != 64
        || !intent
            .plan_sha256
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
    {
        bail!("修复 intent schema 或持久身份不支持，保留文件");
    }
    model::validate_component(&intent.instance_id)?;
    model::validate_component(&intent.package)?;
    let mut paths = BTreeSet::new();
    for path in &intent.paths {
        let text = path.to_str().context("intent 路径非 UTF-8")?;
        if path.as_os_str().is_empty()
            || path.is_absolute()
            || path.components().any(|component| match component {
                Component::Normal(value) => value
                    .to_str()
                    .is_none_or(|value| model::validate_component(value).is_err()),
                _ => true,
            })
            || !paths.insert(text.replace('\\', "/").to_lowercase())
        {
            bail!("修复 intent 包含非法/重复路径");
        }
    }
    Ok(())
}

fn read_intent(layout: &Layout, release: &Release, instance: &str) -> Result<Intent> {
    let intent: Intent = serde_json::from_str(&small_text(
        layout,
        &intent_path(layout, instance)?,
        MAX_INTENT,
    )?)?;
    validate_intent(layout, release, &intent)?;
    if intent.instance_id != instance {
        bail!("修复 intent 的实例身份不匹配");
    }
    Ok(intent)
}

fn create_intent(layout: &Layout, release: &Release, intent: &Intent) -> Result<()> {
    validate_intent(layout, release, intent)?;
    let path = intent_path(layout, &intent.instance_id)?;
    layout.ensure_dir(path.parent().context("intent 缺少父目录")?)?;
    let bytes = serde_json::to_vec_pretty(intent)?;
    if bytes.len() as u64 > MAX_INTENT {
        bail!("修复 intent 超限");
    }
    let mut file = File::options().write(true).create_new(true).open(path)?;
    file.write_all(&bytes)?;
    file.sync_all()?;
    Ok(())
}

fn clear_intent(layout: &Layout, release: &Release, intent: &Intent) -> Result<()> {
    if read_intent(layout, release, &intent.instance_id)? != *intent {
        bail!("修复 intent 已改变，拒绝清除");
    }
    fs::remove_file(intent_path(layout, &intent.instance_id)?)?;
    Ok(())
}

fn phase(
    ctx: &WorkspaceMutation,
    operation: &OperationHandle,
    value: OperationPhase,
    text: &str,
) -> Result<()> {
    operation.publish(value, text)?;
    operation.persist(ctx)
}

fn bind(
    ctx: &WorkspaceMutation,
    release: &Release,
    intent: &Intent,
    state: &InstanceState,
) -> Result<()> {
    if state.id() != intent.instance_id
        || state.recipe_sha256() != intent.recipe_sha256
        || state.generation() != intent.next_generation
        || state.dirty()
    {
        bail!("修复结果身份或 generation 不匹配");
    }
    instances::assert_usable(state)?;
    let mut registry = Registry::load(&ctx.layout().root)?;
    let binding = registry
        .gui_binding(&release.id)
        .context("修复期间登记绑定消失")?;
    if binding.instance_id != intent.instance_id
        || binding.recipe_sha256 != intent.recipe_sha256
        || ![intent.base_generation, intent.next_generation].contains(&binding.generation)
    {
        bail!("修复期间登记绑定已改变，保留 intent");
    }
    registry.bind_gui(
        &release.id,
        EnvironmentBinding {
            instance_id: state.id().into(),
            recipe_id: state.recipe_id().into(),
            recipe_sha256: state.recipe_sha256().into(),
            generation: state.generation(),
            storage_version: state.storage_version(),
        },
    )?;
    registry.store(&ctx.layout().root)
}

fn validate(
    layout: &Layout,
    release: &Release,
    recipe: &GuiRecipe,
    environment: &Path,
    log: &super::Logger,
    cancel: &CancelToken,
) -> Result<()> {
    super::verify_source(layout, release)?;
    layout.guard_path(&super::uv(&layout.root))?;
    if super::digest(&super::uv(&layout.root))? != recipe.tool_uv.exe_sha256 {
        bail!("受管 uv 身份改变");
    }
    super::gui_install::validate_environment(layout, recipe, environment, log, cancel)
}

fn reinstall(
    ctx: &WorkspaceMutation,
    recipe: &GuiRecipe,
    preview: &RepairPreview,
    operation: &OperationHandle,
    log: &super::Logger,
) -> Result<()> {
    let layout = ctx.layout();
    crate::python_integrity::verify(layout)?;
    layout.guard_path(&super::uv(&layout.root))?;
    if super::digest(&super::uv(&layout.root))? != recipe.tool_uv.exe_sha256 {
        bail!("重装前受管 uv 身份不符");
    }
    let asset = recipe
        .wheel(&preview.package)
        .context("目标包不在固定锁内")?;
    let directory = layout
        .root
        .join("staging/gui-repairs")
        .join(format!("{}-{}", preview.instance_id, preview.generation));
    layout.ensure_dir(&directory)?;
    let lock = directory.join(format!("{}.txt", preview.plan_sha256));
    layout.guard_path(&lock)?;
    let contents = format!(
        "{}=={} --hash=sha256:{}\n",
        asset.name, asset.version, asset.sha256
    );
    if lock.try_exists()? {
        if small_text(layout, &lock, MAX_METADATA)? != contents {
            bail!("单包修复锁发生冲突");
        }
    } else {
        let mut file = File::options().write(true).create_new(true).open(&lock)?;
        file.write_all(contents.as_bytes())?;
        file.sync_all()?;
    }
    let mut command = super::gui_install::command(&layout.root, recipe);
    command
        .args(["pip", "install", "--python"])
        .arg(layout.environment.join("Scripts/python.exe"))
        .args(["--no-index", "--find-links"])
        .arg(layout.root.join("cache/wheelhouse"))
        .args([
            "--only-binary",
            ":all:",
            "--require-hashes",
            "--no-deps",
            "--link-mode",
            "copy",
            "--reinstall-package",
        ])
        .arg(&preview.package)
        .arg("--requirements")
        .arg(lock);
    super::execute_controlled(command, log, &operation.cancel_token())
}

/// 已持有同一工作区租约；plan_sha256 必须来自当前可审计划。
pub(super) fn execute(
    ctx: &WorkspaceMutation,
    release: &Release,
    package: &str,
    plan_sha256: &str,
    operation: &OperationHandle,
    log: &super::Logger,
) -> Result<()> {
    operation.persist(ctx)?;
    let result = execute_inner(ctx, release, package, plan_sha256, operation, log);
    finish(ctx, operation, &result)?;
    result
}

fn finish(ctx: &WorkspaceMutation, operation: &OperationHandle, result: &Result<()>) -> Result<()> {
    let (status, error) = match result {
        Ok(()) => (OperationStatus::Succeeded, None),
        Err(error) if error.downcast_ref::<Cancelled>().is_some() => {
            (OperationStatus::Cancelled, None)
        }
        Err(error) => (
            OperationStatus::Failed,
            Some(OperationError {
                code: "gui_repair_failed".into(),
                message: format!("{error:#}"),
            }),
        ),
    };
    operation.finish_and_persist(ctx, status, error)
}

fn execute_inner(
    ctx: &WorkspaceMutation,
    release: &Release,
    package: &str,
    expected_sha: &str,
    operation: &OperationHandle,
    log: &super::Logger,
) -> Result<()> {
    let layout = ctx.layout();
    let recipe = recipe(release)?;
    if Layout::new(&layout.root, &release.id)?.environment != layout.environment {
        bail!("持锁布局已过期");
    }
    operation.cancel_token().check()?;
    phase(
        ctx,
        operation,
        OperationPhase::Preparing,
        "重新核对单包修复计划与全量原文件",
    )?;
    let preview = plan(&layout.root, release, package)?;
    if preview.plan_sha256 != expected_sha {
        bail!("修复计划已经变化，请重新诊断审查");
    }
    // plan 在任何 Python/uv 执行前校验非目标树仍符合已验证实例基线。
    let transaction = instances::plan(
        ctx,
        &preview.instance_id,
        preview.generation,
        &preview.paths,
    )?;
    if preview.before_original_files_verified {
        validate(
            layout,
            release,
            &recipe,
            &layout.environment,
            log,
            &operation.cancel_token(),
        )?;
    } else {
        log("修复前原文件存在缺坏，pip check/关键导入被静态完整性门阻止；将在修复后实测".into());
    }
    let intent = Intent {
        schema_version: 1,
        component: "gui-package-repair".into(),
        root_absolute: layout.root.clone(),
        release_id: release.id.clone(),
        instance_id: preview.instance_id.clone(),
        recipe_sha256: recipe_sha(),
        package: preview.package.clone(),
        version: preview.version.clone(),
        base_generation: preview.generation,
        next_generation: preview
            .generation
            .checked_add(1)
            .context("generation 溢出")?,
        paths: preview.paths.clone(),
        plan_sha256: preview.plan_sha256.clone(),
    };
    operation.cancel_token().check()?;
    create_intent(layout, release, &intent)?;
    let ticket = match instances::begin(ctx, &transaction) {
        Ok(ticket) => ticket,
        Err(error) => {
            let current = instances::load(layout, &intent.instance_id)?;
            if !current.dirty() && current.generation() == intent.base_generation {
                clear_intent(layout, release, &intent)?;
            }
            return Err(error);
        }
    };
    let attempt = (|| {
        operation.cancel_token().check()?;
        phase(
            ctx,
            operation,
            OperationPhase::Executing,
            "仅从离线 wheelhouse 重装指定包",
        )?;
        reinstall(ctx, &recipe, &preview, operation, log)?;
        operation.cancel_token().check()?;
        phase(
            ctx,
            operation,
            OperationPhase::Verifying,
            "全量验证原文件、pip check、解释器归属与关键导入",
        )?;
        instances::commit(ctx, &ticket, |environment| {
            validate(
                layout,
                release,
                &recipe,
                environment,
                log,
                &operation.cancel_token(),
            )
        })
    })();
    let clean = match attempt {
        Ok(clean) => clean,
        Err(error) => {
            let _ = phase(
                ctx,
                operation,
                OperationPhase::Recovering,
                "还原独立快照并重新验证，尚不代表环境健康",
            );
            let recovered = instances::recover(ctx, &ticket, |environment| {
                validate(
                    layout,
                    release,
                    &recipe,
                    environment,
                    log,
                    &CancelToken::new(),
                )
            });
            match recovered {
                Ok(clean) => {
                    bind(ctx, release, &intent, &clean)?;
                    clear_intent(layout, release, &intent)?;
                    return Err(error.context("单包修复失败，原快照已恢复并通过全量复验"));
                }
                Err(recovery) => bail!("修复失败：{error:#}；快照恢复/复验未通过，实例保持 dirty 与 intent：{recovery:#}"),
            }
        }
    };
    // clean 与登记之间不再响应取消；intent 允许重启后完成同一 generation 登记。
    phase(
        ctx,
        operation,
        OperationPhase::Committing,
        "登记通过验证的新 generation",
    )?;
    bind(ctx, release, &intent, &clean)?;
    clear_intent(layout, release, &intent)
}

/// 强杀/断电后的安全收尾：prepared 无变更可撤销；dirty 还原快照并全验；已clean补登记。
pub(super) fn recover(
    ctx: &WorkspaceMutation,
    release: &Release,
    operation: &OperationHandle,
    log: &super::Logger,
) -> Result<()> {
    operation.persist(ctx)?;
    let result = recover_inner(ctx, release, operation, log);
    finish(ctx, operation, &result)?;
    result
}

fn recover_inner(
    ctx: &WorkspaceMutation,
    release: &Release,
    operation: &OperationHandle,
    log: &super::Logger,
) -> Result<()> {
    let layout = ctx.layout();
    let recipe = recipe(release)?;
    let registry = Registry::load(&layout.root)?;
    let binding = registry
        .gui_binding(&release.id)
        .context("不存在待恢复实例绑定")?;
    let intent = read_intent(layout, release, &binding.instance_id)?;
    let state = instances::load(layout, &intent.instance_id)?;
    if state.recipe_sha256() != intent.recipe_sha256 {
        bail!("恢复配方身份改变");
    }
    let integrity = wheel_integrity::inspect(
        layout,
        &instances::path(&state)?,
        &recipe,
        &layout.root.join("cache/wheelhouse"),
    )?;
    let asset = recipe
        .wheel(&intent.package)
        .context("intent 包名不在固定配方")?;
    if asset.version != intent.version
        || wheel_integrity::package_paths(&integrity, &intent.package) != intent.paths
    {
        bail!("intent 文件闭包与可信 wheel 不一致，保持原记录");
    }
    phase(
        ctx,
        operation,
        OperationPhase::Recovering,
        "读取持久修复 intent 与独立事务快照",
    )?;
    if !state.dirty() && state.generation() == intent.base_generation {
        // begin 尚未持久化；只撤销 intent，不把可能已损坏的原状态宣称为健康。
        return clear_intent(layout, release, &intent);
    }
    if state.generation() != intent.next_generation {
        bail!("恢复 generation 与 intent 不一致");
    }
    let clean = if state.dirty() {
        let ticket = instances::reload_ticket(layout, state.id())?;
        instances::recover(ctx, &ticket, |environment| {
            validate(
                layout,
                release,
                &recipe,
                environment,
                log,
                &CancelToken::new(),
            )
        })?
    } else {
        instances::assert_usable(&state)?;
        validate(
            layout,
            release,
            &recipe,
            &instances::path(&state)?,
            log,
            &CancelToken::new(),
        )?;
        instances::assert_usable(&state)?;
        state
    };
    bind(ctx, release, &intent, &clean)?;
    clear_intent(layout, release, &intent)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);

    fn release() -> Release {
        model::Catalog::embedded()
            .unwrap()
            .releases()
            .iter()
            .find(|release| release.commit == GuiRecipe::embedded().unwrap().source_commit)
            .unwrap()
            .clone()
    }
    fn context() -> (PathBuf, WorkspaceMutation, Release) {
        let release = release();
        let root = std::env::temp_dir().join(format!(
            "nt-gui-repair-{}-{}-{}",
            std::process::id(),
            model::now(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        let ctx = WorkspaceMutation::acquire(&root, &release.id).unwrap();
        (root, ctx, release)
    }
    fn intent(ctx: &WorkspaceMutation, release: &Release) -> Intent {
        Intent {
            schema_version: 1,
            component: "gui-package-repair".into(),
            root_absolute: ctx.layout().root.clone(),
            release_id: release.id.clone(),
            instance_id: "g0000000000000002".into(),
            recipe_sha256: recipe_sha(),
            package: "toml".into(),
            version: "0.10.2".into(),
            base_generation: 1,
            next_generation: 2,
            paths: vec![PathBuf::from("Lib/site-packages/toml/decoder.py")],
            plan_sha256: "a".repeat(64),
        }
    }

    #[test]
    fn durable_intent_rejects_unknown_schema_identity_escape_and_overwrite() {
        let (root, ctx, release) = context();
        let original = intent(&ctx, &release);
        create_intent(ctx.layout(), &release, &original).unwrap();
        assert_eq!(
            read_intent(ctx.layout(), &release, &original.instance_id).unwrap(),
            original
        );
        assert!(create_intent(ctx.layout(), &release, &original).is_err());
        for invalid in [
            Intent {
                schema_version: 2,
                ..original.clone()
            },
            Intent {
                next_generation: 4,
                ..original.clone()
            },
            Intent {
                paths: vec![PathBuf::from("../profiles/default/profile.json")],
                ..original.clone()
            },
        ] {
            assert!(validate_intent(ctx.layout(), &release, &invalid).is_err());
        }
        let path = intent_path(ctx.layout(), &original.instance_id).unwrap();
        let mut unknown = serde_json::to_value(&original).unwrap();
        unknown["unknown_field"] = serde_json::json!(true);
        fs::write(&path, serde_json::to_vec(&unknown).unwrap()).unwrap();
        let before = fs::read(&path).unwrap();
        assert!(read_intent(ctx.layout(), &release, &original.instance_id).is_err());
        assert_eq!(fs::read(path).unwrap(), before);
        drop(ctx);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn changed_intent_cannot_be_silently_cleared() {
        let (root, ctx, release) = context();
        let original = intent(&ctx, &release);
        create_intent(ctx.layout(), &release, &original).unwrap();
        let changed = Intent {
            package: "pip".into(),
            ..original.clone()
        };
        fs::write(
            intent_path(ctx.layout(), &original.instance_id).unwrap(),
            serde_json::to_vec(&changed).unwrap(),
        )
        .unwrap();
        assert!(clear_intent(ctx.layout(), &release, &original).is_err());
        assert_eq!(
            read_intent(ctx.layout(), &release, &original.instance_id).unwrap(),
            changed
        );
        drop(ctx);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn rollback_of_damaged_snapshot_never_clears_dirty_without_real_validation() {
        let (root, ctx, _release) = context();
        let state =
            instances::create(&ctx, "g0000000000000001", "test-recipe", &"b".repeat(64)).unwrap();
        let environment = instances::path(&state).unwrap();
        fs::write(environment.join("target.py"), b"healthy").unwrap();
        let state = instances::validate_new(&ctx, &state, &[], |_| Ok(())).unwrap();
        fs::write(environment.join("target.py"), b"damaged").unwrap();
        let plan = instances::plan(
            &ctx,
            state.id(),
            state.generation(),
            &[PathBuf::from("target.py")],
        )
        .unwrap();
        let ticket = instances::begin(&ctx, &plan).unwrap();
        fs::write(environment.join("target.py"), b"partial").unwrap();
        assert!(instances::recover(&ctx, &ticket, |environment| {
            if fs::read(environment.join("target.py"))? != b"healthy" {
                bail!("trusted content still damaged");
            }
            Ok(())
        })
        .is_err());
        assert_eq!(fs::read(environment.join("target.py")).unwrap(), b"damaged");
        let dirty = instances::load(ctx.layout(), state.id()).unwrap();
        assert!(dirty.dirty());
        assert_eq!(dirty.generation(), 2);
        assert!(instances::assert_usable(&dirty).is_err());
        assert!(instances::reload_ticket(ctx.layout(), state.id()).is_ok());
        drop(ctx);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn clean_generation_binding_can_be_replayed_after_commit_window() {
        let (root, ctx, release) = context();
        let state = instances::create(
            &ctx,
            "g0000000000000002",
            "gui-cp310-win-x64-v1",
            &recipe_sha(),
        )
        .unwrap();
        let environment = instances::path(&state).unwrap();
        fs::write(environment.join("target.py"), b"healthy").unwrap();
        let state = instances::validate_new(&ctx, &state, &[], |_| Ok(())).unwrap();
        let mut registry = Registry::load(&root).unwrap();
        registry.record_installed(&release).unwrap();
        registry.store(&root).unwrap();
        registry.upgrade_for_instances(&ctx).unwrap();
        registry
            .bind_gui(
                &release.id,
                EnvironmentBinding {
                    instance_id: state.id().into(),
                    recipe_id: state.recipe_id().into(),
                    recipe_sha256: recipe_sha(),
                    generation: 1,
                    storage_version: state.storage_version(),
                },
            )
            .unwrap();
        registry.store(&root).unwrap();
        let mut intent = intent(&ctx, &release);
        intent.paths = vec![PathBuf::from("target.py")];
        create_intent(ctx.layout(), &release, &intent).unwrap();
        let ticket = instances::begin(
            &ctx,
            &instances::plan(&ctx, state.id(), 1, &intent.paths).unwrap(),
        )
        .unwrap();
        fs::write(environment.join("target.py"), b"repaired").unwrap();
        let clean = instances::commit(&ctx, &ticket, |_| Ok(())).unwrap();
        assert_eq!(
            Registry::load(&root)
                .unwrap()
                .gui_binding(&release.id)
                .unwrap()
                .generation,
            1
        );
        bind(&ctx, &release, &intent, &clean).unwrap();
        bind(&ctx, &release, &intent, &clean).unwrap();
        assert_eq!(
            Registry::load(&root)
                .unwrap()
                .gui_binding(&release.id)
                .unwrap()
                .generation,
            2
        );
        clear_intent(ctx.layout(), &release, &intent).unwrap();
        assert!(!intent_path(ctx.layout(), state.id()).unwrap().exists());
        drop(ctx);
        fs::remove_dir_all(root).unwrap();
    }
}
