//! 固定 GUI 源码及捆绑前端分项修复；不执行 Python，也不修改环境实例。
use crate::{
    model::{
        self, EnvironmentBinding, Layout, Registry, Release, ReleaseReceipt, WorkspaceMutation,
    },
    operations::{
        CancelToken, Cancelled, OperationError, OperationHandle, OperationPhase, OperationStatus,
    },
    recipe::GuiRecipe,
};
use anyhow::{bail, Context, Result};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::{self, File},
    io::{Read, Write},
    path::{Path, PathBuf},
    sync::atomic::{AtomicU64, Ordering},
};

const MAX_FILE: u64 = 1024 * 1024 * 1024;
const MAX_TREE: u64 = 4 * MAX_FILE;
const MAX_NODES: usize = 50_000;
static NEXT: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Serialize)]
struct Diagnosis {
    schema_version: u32,
    component: &'static str,
    release_id: String,
    source_commit: String,
    replacement_root: PathBuf,
    replacement_mode: &'static str,
    expected_source_files: Vec<PathBuf>,
    generated_files: Vec<PathBuf>,
    source_integrity_error: Option<String>,
    environment_binding: Option<EnvironmentBinding>,
    protected_sha256: String,
    boundary: &'static str,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case")]
enum Node {
    Missing,
    Directory,
    File { bytes: u64, sha256: String },
    PythonAlias { target: PathBuf },
}
#[derive(Debug, Serialize, PartialEq, Eq)]
struct Protection {
    root_absolute: PathBuf,
    release_id: String,
    bytes: u64,
    entries: BTreeMap<PathBuf, Node>,
    profiles: crate::instances::ProfilesSummary,
}

struct Scanner<'a> {
    layout: &'a Layout,
    cancel: Option<&'a CancelToken>,
    entries: BTreeMap<PathBuf, Node>,
    bytes: u64,
}
impl Scanner<'_> {
    fn walk(&mut self, path: &Path) -> Result<()> {
        if path == self.layout.release_dir {
            return Ok(());
        }
        if let Some(cancel) = self.cancel {
            cancel.check()?;
        }
        let relative = path.strip_prefix(&self.layout.root)?.to_path_buf();
        let alias = self
            .layout
            .root
            .join("python/3.10.19/cpython-3.10-windows-x86_64-none");
        let node = if path == alias {
            self.layout
                .guard_path(alias.parent().context("Python 别名缺少父目录")?)?;
            let target = self
                .layout
                .root
                .join("python/3.10.19/cpython-3.10.19-windows-x86_64-none");
            self.layout.guard_path(&target)?;
            #[cfg(windows)]
            {
                if !junction::exists(&alias)?
                    || junction::get_target(&alias)?.canonicalize()? != target.canonicalize()?
                    || !target.is_dir()
                {
                    bail!("源码修复保护树包含未知 Python 联接，原文件保留");
                }
                Node::PythonAlias {
                    target: target.strip_prefix(&self.layout.root)?.into(),
                }
            }
            #[cfg(not(windows))]
            bail!("Python minor junction 只允许在 Windows 使用")
        } else {
            self.layout.guard_path(path)?;
            match fs::symlink_metadata(path) {
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => Node::Missing,
                Err(error) => return Err(error.into()),
                Ok(metadata) if metadata.is_dir() => Node::Directory,
                Ok(metadata) if metadata.is_file() && metadata.len() <= MAX_FILE => {
                    let mut input = File::open(path)?.take(MAX_FILE + 1);
                    let mut hash = Sha256::new();
                    let mut bytes = 0u64;
                    let mut buffer = [0; 65_536];
                    loop {
                        if let Some(cancel) = self.cancel {
                            cancel.check()?;
                        }
                        let count = input.read(&mut buffer)?;
                        if count == 0 {
                            break;
                        }
                        bytes += count as u64;
                        if bytes > MAX_FILE {
                            bail!("源码修复保护文件超过 1GiB，保留现场");
                        }
                        hash.update(&buffer[..count]);
                    }
                    self.bytes = self.bytes.checked_add(bytes).context("保护树长度溢出")?;
                    if bytes != metadata.len() || self.bytes > MAX_TREE {
                        bail!("源码修复保护树读取期间变化或总量超过 4GiB，保留现场");
                    }
                    self.layout.guard_path(path)?;
                    Node::File {
                        bytes,
                        sha256: format!("{:x}", hash.finalize()),
                    }
                }
                Ok(_) => bail!(
                    "源码修复保护树含非普通或超过 1GiB 的文件：{}",
                    path.display()
                ),
            }
        };
        let is_directory = node == Node::Directory;
        if self.entries.insert(relative, node).is_some() || self.entries.len() > MAX_NODES {
            bail!("源码修复保护树路径重复或超过 50000 项，保留现场");
        }
        if is_directory {
            for item in fs::read_dir(path)? {
                self.walk(&item?.path())?;
            }
        }
        Ok(())
    }
}

fn capture(layout: &Layout, cancel: Option<&CancelToken>) -> Result<Protection> {
    let mut scanner = Scanner {
        layout,
        cancel,
        entries: BTreeMap::new(),
        bytes: 0,
    };
    for root in [
        "environments",
        "e",
        "python",
        "tools",
        "releases",
        "state/instances",
        "state/gui-repairs",
    ] {
        scanner.walk(&layout.root.join(root))?;
    }
    Ok(Protection {
        root_absolute: layout.root.clone(),
        release_id: layout
            .release_dir
            .file_name()
            .context("缺少 release 身份")?
            .to_str()
            .context("release 不是 UTF-8")?
            .into(),
        bytes: scanner.bytes,
        entries: scanner.entries,
        profiles: crate::instances::summarize_profiles(
            layout,
            cancel.unwrap_or(&CancelToken::new()),
        )?,
    })
}

fn phase(
    ctx: &WorkspaceMutation,
    operation: &OperationHandle,
    value: OperationPhase,
    text: &str,
) -> Result<()> {
    operation.cancel_token().check()?;
    operation.publish(value, text)?;
    operation.persist(ctx)
}

fn write_new(layout: &Layout, path: &Path, bytes: &[u8]) -> Result<()> {
    layout.guard_path(path)?;
    let mut file = File::options().write(true).create_new(true).open(path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}

fn diagnose(
    layout: &Layout,
    release: &Release,
    registry: &Registry,
    protected: &Protection,
) -> Result<(GuiRecipe, Diagnosis)> {
    release.validate()?;
    let recipe = GuiRecipe::embedded()?;
    let catalog = crate::source_integrity::trusted_manifest(release)?;
    if catalog.source_commit != recipe.source_commit
        || release.commit != recipe.source_commit
        || release.python != recipe.python.version
        || release.uv != recipe.tool_uv
        || !recipe.matches_environment_recipe(&release.environment_recipe)
        || recipe.frontend.sha256 != catalog.frontend_sha256
        || recipe.frontend.bytes != catalog.frontend_bytes
    {
        bail!("该发布版没有匹配的可信源码及捆绑前端修复配方");
    }
    let replacement_root = layout.release_dir.strip_prefix(&layout.root)?.to_path_buf();
    let diagnosis = Diagnosis {
        schema_version: 1,
        component: "gui-source-and-bundled-frontend",
        release_id: release.id.clone(),
        source_commit: release.commit.clone(),
        expected_source_files: catalog.files.iter().map(|file| replacement_root.join("app").join(&file.path)).collect(),
        generated_files: vec![replacement_root.join("release.json"), replacement_root.join("app/.source-integrity.json")],
        replacement_root,
        replacement_mode: "整体替换指定 release 目录；原目录按精确树摘要保存在独立 backup；旧额外文件仅在 backup 保留",
        source_integrity_error: super::verify_source(layout, release).err().map(|error| format!("{error:#}")),
        environment_binding: registry.gui_binding(&release.id).cloned(),
        protected_sha256: format!("{:x}", Sha256::digest(serde_json::to_vec(protected)?)),
        boundary: "仅恢复固定源码与捆绑前端，不证明 GUI 环境或训练引擎健康；环境绑定及 generation 保持原值，源码发布前清除目标旧健康标记",
    };
    Ok((recipe, diagnosis))
}

/// 环境页只读预览：不建立 lease、不写诊断、不恢复意图，也不改变健康标记。
pub(super) fn preview(root: &Path, release: &Release) -> Result<serde_json::Value> {
    let layout = Layout::new(root, &release.id)?;
    let registry = Registry::load(root)?;
    let protected = capture(&layout, None)?;
    let (_, diagnosis) = diagnose(&layout, release, &registry, &protected)?;
    Ok(serde_json::to_value(diagnosis)?)
}

fn invalidate_health(
    ctx: &WorkspaceMutation,
    release: &Release,
    expected: &mut Registry,
) -> Result<()> {
    let mut registry = Registry::load(&ctx.layout().root)?;
    if registry != *expected {
        bail!("源码修复期间 Registry 已改变，保留候选与原目录");
    }
    if let Some(binding) = registry.gui_binding(&release.id).cloned() {
        registry.bind_gui(&release.id, binding)?;
    } else {
        // 无绑定的旧记录也不能继承修复前的健康事实；无需升级或接管它的环境。
        if let Some(record) = registry
            .installed
            .iter_mut()
            .find(|record| record.release_id == release.id)
        {
            record.healthy_at = None;
        }
        if registry.previous_known_good.as_deref() == Some(release.id.as_str()) {
            registry.previous_known_good = None;
        }
    }
    if registry != *expected {
        registry.store(&ctx.layout().root)?;
        *expected = registry;
    }
    Ok(())
}

fn install_frontend(
    layout: &Layout,
    staging: &Path,
    inputs: &Path,
    archive: &Path,
    cancel: &CancelToken,
) -> Result<()> {
    let dist = staging.join("app/frontend/dist");
    layout.guard_path(&dist)?;
    if dist.exists() {
        let tracked = inputs.join("tracked-frontend");
        layout.guard_path(&tracked)?;
        fs::rename(&dist, tracked)?;
    }
    layout.ensure_dir(&dist)?;
    super::safe_extract::extract(archive, &dist, false, Some(cancel))
}

fn execute_inner(
    ctx: &WorkspaceMutation,
    release: &Release,
    operation: &OperationHandle,
    log: &super::Logger,
    protected: &Protection,
    registry: &mut Registry,
) -> Result<()> {
    let layout = ctx.layout();
    phase(
        ctx,
        operation,
        OperationPhase::Recovering,
        "核对已有源码发布意图，仅恢复身份明确的源码目录",
    )?;
    super::gui_recovery::recover_source(ctx, release)?;
    phase(
        ctx,
        operation,
        OperationPhase::Preparing,
        "静态诊断源码与捆绑前端替换闭包，保留现有环境实例",
    )?;
    let (recipe, diagnosis) = diagnose(layout, release, registry, protected)?;
    let suffix = format!(
        "{}-{}-{}",
        super::stamp(),
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    );
    let inputs = layout
        .root
        .join("staging")
        .join(format!("source-repair-{suffix}"));
    layout.ensure_dir(inputs.parent().context("修复输入缺少父目录")?)?;
    layout.guard_path(&inputs)?;
    fs::create_dir(&inputs)?;
    write_new(
        layout,
        &inputs.join("diagnosis.json"),
        &serde_json::to_vec_pretty(&diagnosis)?,
    )?;
    write_new(
        layout,
        &inputs.join("protected.json"),
        &serde_json::to_vec_pretty(protected)?,
    )?;
    log(format!(
        "源码修复闭包：{}，可信文件 {} 项；完整诊断：{}",
        diagnosis.replacement_root.display(),
        diagnosis.expected_source_files.len(),
        inputs.join("diagnosis.json").display()
    ));
    if diagnosis.source_integrity_error.is_none() {
        log("源码及捆绑前端已通过可信完整清单，未发生替换".into());
        return Ok(());
    }
    let frontend = super::gui_install::bundled_frontend(&recipe)?;
    if fs2::available_space(&layout.root)? < 512 * 1024 * 1024 {
        bail!("源码修复卷可用空间不足 512MiB，诊断已保留，尚未替换原目录");
    }
    phase(
        ctx,
        operation,
        OperationPhase::Downloading,
        "获取固定源码归档，前端使用本启动器内置制品",
    )?;
    let source = super::gui_install::download(
        ctx,
        &recipe,
        operation,
        &release.archive.url,
        &format!("{}.zip", release.archive.sha256),
        &release.archive.sha256,
        release.archive.bytes,
    )?;
    phase(
        ctx,
        operation,
        OperationPhase::Executing,
        "组装独立源码候选并完整替换跟踪前端，失败保留候选",
    )?;
    let staging = layout
        .root
        .join("staging")
        .join(format!("locked-source-repair-{suffix}"));
    layout.guard_path(&staging)?;
    fs::create_dir(&staging)?;
    layout.ensure_dir(&staging.join("app"))?;
    log(format!(
        "本次源码候选：{}；失败时保留该目录",
        staging.display()
    ));
    super::safe_extract::extract(
        &source,
        &staging.join("app"),
        true,
        Some(&operation.cancel_token()),
    )?;
    let frontend_archive = inputs.join("frontend.zip");
    write_new(layout, &frontend_archive, frontend)?;
    install_frontend(
        layout,
        &staging,
        &inputs,
        &frontend_archive,
        &operation.cancel_token(),
    )?;
    if super::digest(&staging.join("app/requirements.txt"))? != recipe.requirements.input_sha256
        || fs::read_to_string(staging.join("app/VERSION"))?.trim() != release.version
    {
        bail!("候选源码输入与固定配方或 release VERSION 不匹配，原目录未替换");
    }
    model::write_json_atomic(
        &staging.join("app/.source-integrity.json"),
        &super::manifest(&staging.join("app"))?,
    )?;
    ReleaseReceipt::new(release).store(&staging)?;
    phase(
        ctx,
        operation,
        OperationPhase::Verifying,
        "验证候选完整源码、捆绑前端及非目标保护树",
    )?;
    let mut candidate = layout.clone();
    candidate.release_dir = staging.clone();
    candidate.app = staging.join("app");
    super::verify_source(&candidate, release)?;
    if capture(layout, Some(&operation.cancel_token()))? != *protected {
        bail!("源码修复期间非目标组件发生变化，候选与原目录均保留");
    }
    phase(
        ctx,
        operation,
        OperationPhase::Committing,
        "提交源码发布意图；临界区结束后返回真实结果，取消可能延迟",
    )?;
    // 此后不响应取消：先清旧健康事实，再由持久 source intent 完成发布或精确回撤。
    invalidate_health(ctx, release, registry)?;
    super::gui_recovery::publish_source(ctx, release, &staging)?;
    super::verify_source(layout, release)?;
    log(
        "固定源码及捆绑前端修复完成；环境绑定与 generation 未变，启动健康状态待实际启动验证".into(),
    );
    Ok(())
}

/// 调用方须停止目标源码使用者，并在全程保持同一 workspace lease。
pub(super) fn execute(
    ctx: &WorkspaceMutation,
    release: &Release,
    operation: &OperationHandle,
    log: &super::Logger,
) -> Result<()> {
    operation.persist(ctx)?;
    let result = (|| {
        phase(
            ctx,
            operation,
            OperationPhase::Preparing,
            "建立源码修复的环境、Python、资料和其他版本保护摘要",
        )?;
        let layout = ctx.layout();
        if Layout::new(&layout.root, &release.id)?.release_dir != layout.release_dir {
            bail!("源码修复 release 与持锁布局不一致");
        }
        let mut registry = Registry::load(&layout.root)?;
        let protected = capture(layout, Some(&operation.cancel_token()))?;
        let attempted = execute_inner(ctx, release, operation, log, &protected, &mut registry);
        let unchanged = (|| {
            // 取消或提交失败也核对保护树，不能因取消跳过资料保护结论。
            if capture(layout, None)? != protected || Registry::load(&layout.root)? != registry {
                bail!("源码修复后的非目标内容或 Registry 发生变化；保留诊断、候选、意图和备份，未确认修复成功");
            }
            Ok(())
        })();
        match (attempted, unchanged) {
            (Ok(()), Ok(())) => Ok(()),
            (Err(error), Ok(())) => Err(error),
            (Ok(()), Err(error)) => Err(error),
            (Err(error), Err(protection)) => {
                Err(protection.context(format!("源码修复原始结果：{error:#}")))
            }
        }
    })();
    let (status, error) = match &result {
        Ok(()) => (OperationStatus::Succeeded, None),
        Err(error) if error.downcast_ref::<Cancelled>().is_some() => {
            (OperationStatus::Cancelled, None)
        }
        Err(error) => (
            OperationStatus::Failed,
            Some(OperationError {
                code: "gui_source_repair_failed".into(),
                message: format!("{error:#}"),
            }),
        ),
    };
    operation.finish_and_persist(ctx, status, error)?;
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        model::Catalog,
        operations::{OperationKind, OperationManager},
    };

    struct Fixture {
        root: PathBuf,
        ctx: Option<WorkspaceMutation>,
        release: Release,
    }
    impl Fixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "nt-source-repair-{}-{}-{}",
                std::process::id(),
                super::super::stamp(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            let release = Catalog::embedded()
                .unwrap()
                .releases()
                .iter()
                .find(|release| release.environment_recipe == "gui-cp310-win-x64-v1")
                .unwrap()
                .clone();
            let ctx = WorkspaceMutation::acquire(&root, &release.id).unwrap();
            ctx.layout().ensure_dir(&ctx.layout().app).unwrap();
            fs::write(ctx.layout().app.join("gui.py"), b"damaged source").unwrap();
            ctx.layout().ensure_dir(&ctx.layout().environment).unwrap();
            fs::write(
                ctx.layout().environment.join("broken.dll"),
                b"unhealthy environment",
            )
            .unwrap();
            Self {
                root,
                ctx: Some(ctx),
                release,
            }
        }
        fn ctx(&self) -> &WorkspaceMutation {
            self.ctx.as_ref().unwrap()
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            self.ctx.take();
            if self.root.parent() == Some(std::env::temp_dir().as_path())
                && self
                    .root
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with("nt-source-repair-")
            {
                let _ = fs::remove_dir_all(&self.root);
            }
        }
    }

    #[test]
    fn damaged_source_and_environment_still_have_explicit_source_only_plan() {
        let f = Fixture::new();
        let layout = f.ctx().layout();
        let protected = capture(layout, None).unwrap();
        let (_, diagnosis) = diagnose(
            layout,
            &f.release,
            &Registry::load(&f.root).unwrap(),
            &protected,
        )
        .unwrap();
        assert!(diagnosis.source_integrity_error.is_some());
        assert_eq!(
            diagnosis.expected_source_files.len(),
            crate::source_integrity::trusted_manifest(&f.release)
                .unwrap()
                .files
                .len()
        );
        assert!(diagnosis
            .expected_source_files
            .iter()
            .all(|path| path.starts_with(&diagnosis.replacement_root)));
        assert!(diagnosis
            .expected_source_files
            .iter()
            .any(|path| path.ends_with("app/frontend/dist/index.html")));
    }

    #[test]
    fn readonly_preview_does_not_create_records_or_clear_health() {
        let f = Fixture::new();
        let mut registry = Registry::load(&f.root).unwrap();
        registry.record_installed(&f.release).unwrap();
        registry.installed[0].healthy_at = Some(123);
        registry.store(&f.root).unwrap();
        let registry_bytes = fs::read(f.root.join("state/registry.json")).unwrap();
        let before = capture(f.ctx().layout(), None).unwrap();
        let source = fs::read(f.ctx().layout().app.join("gui.py")).unwrap();
        let staging = fs::read_dir(f.root.join("staging")).unwrap().count();
        let value = preview(&f.root, &f.release).unwrap();
        assert_eq!(
            value["expected_source_files"].as_array().unwrap().len(),
            crate::source_integrity::trusted_manifest(&f.release)
                .unwrap()
                .files
                .len()
        );
        assert!(value["source_integrity_error"].is_string());
        assert_eq!(
            fs::read(f.root.join("state/registry.json")).unwrap(),
            registry_bytes
        );
        assert_eq!(capture(f.ctx().layout(), None).unwrap(), before);
        assert_eq!(
            fs::read(f.ctx().layout().app.join("gui.py")).unwrap(),
            source
        );
        assert_eq!(
            fs::read_dir(f.root.join("staging")).unwrap().count(),
            staging
        );
    }

    #[test]
    fn previous_source_manifest_never_uses_the_current_repair_recipe() {
        let f = Fixture::new();
        let previous = Catalog::embedded()
            .unwrap()
            .releases
            .into_iter()
            .find(|release| release.commit == "89a3b6ca63964b3bc4549b8bda67b38c4baa1a3d")
            .unwrap();
        assert!(crate::source_integrity::supports(&previous));
        let before = capture(f.ctx().layout(), None).unwrap();
        let error = preview(&f.root, &previous).unwrap_err();
        assert!(format!("{error:#}").contains("没有匹配的可信源码及捆绑前端修复配方"));
        assert_eq!(capture(f.ctx().layout(), None).unwrap(), before);
    }

    #[test]
    fn protection_detects_environment_instance_and_other_release_changes() {
        let f = Fixture::new();
        let layout = f.ctx().layout();
        let before = capture(layout, None).unwrap();
        fs::write(layout.app.join("gui.py"), b"replacement source").unwrap();
        assert_eq!(capture(layout, None).unwrap(), before);
        fs::write(layout.environment.join("broken.dll"), b"changed dependency").unwrap();
        assert_ne!(capture(layout, None).unwrap(), before);
        fs::write(
            layout.environment.join("broken.dll"),
            b"unhealthy environment",
        )
        .unwrap();
        layout.ensure_dir(&f.root.join("state/instances")).unwrap();
        fs::write(
            f.root.join("state/instances/one.json"),
            b"generation changed",
        )
        .unwrap();
        assert_ne!(capture(layout, None).unwrap(), before);
        fs::remove_file(f.root.join("state/instances/one.json")).unwrap();
        fs::remove_dir(f.root.join("state/instances")).unwrap();
        layout.ensure_dir(&f.root.join("releases/other")).unwrap();
        fs::write(f.root.join("releases/other/asset"), b"other version").unwrap();
        assert_ne!(capture(layout, None).unwrap(), before);
    }

    #[test]
    fn clearing_source_health_preserves_exact_binding_and_generation() {
        let f = Fixture::new();
        let mut registry = Registry::load(&f.root).unwrap();
        registry.schema_version = 2;
        registry.record_installed(&f.release).unwrap();
        let binding = EnvironmentBinding {
            instance_id: "unhealthy-env".into(),
            recipe_id: "gui-cp310-win-x64-v1".into(),
            recipe_sha256: "a".repeat(64),
            generation: 7,
            storage_version: 0,
        };
        registry.bind_gui(&f.release.id, binding.clone()).unwrap();
        registry.installed[0].healthy_at = Some(123);
        registry.previous_known_good = Some(f.release.id.clone());
        registry.store(&f.root).unwrap();
        invalidate_health(f.ctx(), &f.release, &mut registry).unwrap();
        let after = Registry::load(&f.root).unwrap();
        assert_eq!(after.gui_binding(&f.release.id), Some(&binding));
        assert_eq!(after.installed[0].healthy_at, None);
        assert_eq!(after.previous_known_good, None);
    }

    #[test]
    fn frontend_assembly_keeps_tracked_files_out_of_new_dist() {
        let f = Fixture::new();
        let layout = f.ctx().layout();
        let staging = f.root.join("staging/locked-source-frontend-test");
        let inputs = f.root.join("staging/source-repair-inputs");
        layout
            .ensure_dir(&staging.join("app/frontend/dist/assets"))
            .unwrap();
        layout.ensure_dir(&inputs).unwrap();
        fs::write(
            staging.join("app/frontend/dist/assets/stale.js"),
            b"tracked stale",
        )
        .unwrap();
        let archive = inputs.join("frontend.zip");
        let mut zip = zip::ZipWriter::new(File::create(&archive).unwrap());
        zip.start_file("index.html", zip::write::SimpleFileOptions::default())
            .unwrap();
        zip.write_all(b"bundled frontend").unwrap();
        zip.finish().unwrap();
        install_frontend(layout, &staging, &inputs, &archive, &CancelToken::new()).unwrap();
        assert_eq!(
            fs::read(staging.join("app/frontend/dist/index.html")).unwrap(),
            b"bundled frontend"
        );
        assert!(!staging.join("app/frontend/dist/assets/stale.js").exists());
        assert_eq!(
            fs::read(inputs.join("tracked-frontend/assets/stale.js")).unwrap(),
            b"tracked stale"
        );
    }

    #[test]
    fn cancellation_before_work_preserves_source_and_non_target_files() {
        let f = Fixture::new();
        let before = capture(f.ctx().layout(), None).unwrap();
        let manager = OperationManager::default();
        let operation = manager
            .start("source-cancelled", OperationKind::Repair)
            .unwrap();
        manager.cancel("source-cancelled").unwrap();
        let log: super::super::Logger = std::sync::Arc::new(|_| {});
        assert!(execute(f.ctx(), &f.release, &operation, &log)
            .unwrap_err()
            .downcast_ref::<Cancelled>()
            .is_some());
        assert_eq!(
            manager.snapshot("source-cancelled").unwrap().status,
            OperationStatus::Cancelled
        );
        assert_eq!(capture(f.ctx().layout(), None).unwrap(), before);
        assert_eq!(
            fs::read(f.ctx().layout().app.join("gui.py")).unwrap(),
            b"damaged source"
        );
    }
}
