//! 内置锁定GUI配方：获取所有资产后仅离线执行，在最终实例路径验证后切换绑定。
use crate::{
    instances,
    model::{self, Layout, Registry, Release, ReleaseReceipt, WorkspaceMutation},
    operations::{Cancelled, OperationError, OperationHandle, OperationPhase, OperationStatus},
    recipe::GuiRecipe,
};
use anyhow::{bail, Context, Result};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File},
    io::Write,
    path::{Path, PathBuf},
    process::Command,
};

mod bundled {
    include!(concat!(env!("OUT_DIR"), "/bundled_assets.rs"));
}

fn phase(
    operation: &OperationHandle,
    ctx: &WorkspaceMutation,
    phase: OperationPhase,
    message: &str,
) -> Result<()> {
    operation.cancel_token().check()?;
    operation.publish(phase, message)?;
    operation.persist(ctx)
}

pub(super) fn command(root: &Path, recipe: &GuiRecipe) -> Command {
    let mut command = Command::new(super::uv(root));
    // 只在本子进程清除外来配置；网络仅由Rust下载器负责，uv始终offline。
    for (key, _) in std::env::vars_os() {
        let key_text = key.to_string_lossy().to_ascii_uppercase();
        if key_text.starts_with("UV_")
            || key_text.starts_with("PIP_")
            || key_text.starts_with("PYTHON")
            || ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"].contains(&key_text.as_str())
        {
            command.env_remove(key);
        }
    }
    command
        .args(["--no-config", "--offline"])
        .env("UV_PYTHON_DOWNLOADS", "never")
        .env("UV_CACHE_DIR", root.join("cache/locked-uv"))
        .env(
            "UV_PYTHON_INSTALL_DIR",
            root.join("python").join(&recipe.python.version),
        )
        .env("UV_NO_PROGRESS", "1")
        .env("PYTHONDONTWRITEBYTECODE", "1");
    command
}

pub(super) fn download(
    ctx: &WorkspaceMutation,
    recipe: &GuiRecipe,
    operation: &OperationHandle,
    url: &str,
    name: &str,
    sha: &str,
    bytes: u64,
) -> Result<PathBuf> {
    let mut downloads = super::artifact_downloads::ArtifactDownloads::new();
    download_in(
        ctx,
        recipe,
        operation,
        &mut downloads,
        url,
        name,
        sha,
        bytes,
    )
}

#[allow(clippy::too_many_arguments)] // 固定资产身份与同操作下载入口显式传递。
fn download_in(
    ctx: &WorkspaceMutation,
    recipe: &GuiRecipe,
    operation: &OperationHandle,
    downloads: &mut super::artifact_downloads::ArtifactDownloads,
    url: &str,
    name: &str,
    sha: &str,
    bytes: u64,
) -> Result<PathBuf> {
    if bytes > recipe.budget.max_asset_bytes {
        bail!("资产超过固定配方限额");
    }
    downloads.download(ctx, url, name, sha, bytes, &operation.cancel_token())
}

fn write_new(layout: &Layout, path: &Path, bytes: &[u8]) -> Result<()> {
    layout.guard_path(path)?;
    let mut file = File::options().write(true).create_new(true).open(path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}

pub(super) fn bundled_frontend(recipe: &GuiRecipe) -> Result<&'static [u8]> {
    if bundled::FRONTEND.len() as u64 != recipe.frontend.bytes
        || format!("{:x}", Sha256::digest(bundled::FRONTEND)) != recipe.frontend.sha256
    {
        bail!("本启动器未包含匹配的GUI候选前端，请使用完整开发包");
    }
    Ok(bundled::FRONTEND)
}

pub(super) fn install(
    root: &Path,
    release: &Release,
    operation: &OperationHandle,
    log: &super::Logger,
) -> Result<()> {
    let recipe = GuiRecipe::embedded()?;
    if release.commit != recipe.source_commit
        || !recipe.matches_environment_recipe(&release.environment_recipe)
    {
        bail!("该版本没有匹配的固定GUI配方");
    }
    preflight_environment_path(root)?;
    let ctx = WorkspaceMutation::acquire(root, &release.id)?;
    super::assert_regular_ready(root)?;
    operation.persist(&ctx)?;
    let mut downloads = super::artifact_downloads::ArtifactDownloads::new();
    let result = super::gui_recovery::recover_source(&ctx, release)
        .and_then(|()| install_inner(&ctx, release, &recipe, operation, log, &mut downloads))
        .and_then(|()| crate::data_import::sync_current_environment(&ctx, &release.id));

    let (status, error) = match &result {
        Ok(()) => (OperationStatus::Succeeded, None),
        Err(error) if error.downcast_ref::<Cancelled>().is_some() => {
            (OperationStatus::Cancelled, None)
        }
        Err(error) => (
            OperationStatus::Failed,
            Some(OperationError {
                code: "gui_install_failed".into(),
                message: format!("{error:#}"),
            }),
        ),
    };
    operation.finish_and_persist(&ctx, status, error)?;
    result
}

fn install_inner(
    ctx: &WorkspaceMutation,
    release: &Release,
    recipe: &GuiRecipe,
    operation: &OperationHandle,
    log: &super::Logger,
    downloads: &mut super::artifact_downloads::ArtifactDownloads,
) -> Result<()> {
    let layout = ctx.layout();
    let root = &layout.root;
    // 编译时捆绑的前端与recipe完全匹配，缺失时在任何大资产获取之前拒绝。
    bundled_frontend(recipe)?;
    if fs2::available_space(root)? < 3 * 1024 * 1024 * 1024 {
        bail!("安装卷可用空间不足，请至少保留3GiB后重试；已有文件保持原状");
    }
    let recipe_sha = format!(
        "{:x}",
        Sha256::digest(include_bytes!("../../catalog/gui-cp310-win-x64-v1.json"))
    );
    if let Some(binding) = Registry::load(root)?.gui_binding(&release.id) {
        let instance = instances::load(layout, &binding.instance_id)?;
        if instance.recipe_id() == recipe.id()
            && instance.recipe_sha256() == recipe_sha
            && instances::assert_usable(&instance).is_ok()
        {
            super::verify_source(layout, release)?;
            super::check_environment(layout, release)?;
            return Ok(());
        }
        bail!("已绑定环境需诊断修复；不会自动重建并覆盖原实例");
    }
    phase(
        operation,
        ctx,
        OperationPhase::Downloading,
        "获取固定源码、Python、工具与GUI依赖",
    )?;
    let source = download_in(
        ctx,
        recipe,
        operation,
        downloads,
        &release.archive.url,
        &format!("{}.zip", release.archive.sha256),
        &release.archive.sha256,
        release.archive.bytes,
    )?;
    let uv_archive = download_in(
        ctx,
        recipe,
        operation,
        downloads,
        &recipe.tool_uv.url,
        &format!("{}.zip", recipe.tool_uv.sha256),
        &recipe.tool_uv.sha256,
        recipe.tool_uv.bytes,
    )?;
    let python_archive = download_in(
        ctx,
        recipe,
        operation,
        downloads,
        &recipe.python.archive.url,
        &recipe.python.archive.filename,
        &recipe.python.archive.sha256,
        recipe.python.archive.bytes,
    )?;
    let wheelhouse = root.join("cache/wheelhouse");
    layout.ensure_dir(&wheelhouse)?;
    for (index, asset) in recipe.wheels.iter().enumerate() {
        phase(
            operation,
            ctx,
            OperationPhase::Downloading,
            &format!(
                "获取GUI依赖 {}/{}：{}",
                index + 1,
                recipe.wheels.len(),
                asset.name
            ),
        )?;
        let archive = download_in(
            ctx,
            recipe,
            operation,
            downloads,
            &asset.url,
            &asset.filename,
            &asset.sha256,
            asset.bytes,
        )?;
        let destination = wheelhouse.join(&asset.filename);
        layout.guard_path(&destination)?;
        if destination.exists() {
            if super::digest(&destination)? != asset.sha256 {
                bail!("wheelhouse文件摘要不符，原文件保留");
            }
        } else {
            fs::copy(archive, &destination)?;
        }
    }
    phase(
        operation,
        ctx,
        OperationPhase::Executing,
        "离线准备固定基础工具和Python",
    )?;
    if super::digest(&super::uv(root)).ok().as_deref() != Some(recipe.tool_uv.exe_sha256.as_str()) {
        let staging = root.join(format!("staging/locked-uv-{}", super::stamp()));
        layout.ensure_dir(&staging)?;
        super::safe_extract::extract(
            &uv_archive,
            &staging,
            false,
            Some(&operation.cancel_token()),
        )?;
        if super::digest(&staging.join("uv.exe"))? != recipe.tool_uv.exe_sha256 {
            bail!("uv可执行文件身份不符");
        }
        if super::uv(root).exists() {
            fs::rename(
                super::uv(root),
                root.join(format!("backups/uv-{}.exe", super::stamp())),
            )?;
        }
        fs::copy(staging.join("uv.exe"), super::uv(root))?;
    }
    let mirror = root.join("cache/python-mirror").join(&recipe.python.build);
    layout.ensure_dir(&mirror)?;
    let mirror_archive = mirror.join(&recipe.python.archive.filename);
    layout.guard_path(&mirror_archive)?;
    if mirror_archive.exists() {
        if super::digest(&mirror_archive)? != recipe.python.archive.sha256 {
            bail!("本地Python镜像摘要不符");
        }
    } else {
        fs::copy(&python_archive, &mirror_archive)?;
    }
    let mirror_url =
        reqwest::Url::from_directory_path(mirror.parent().context("Python镜像父目录缺失")?)
            .map_err(|_| anyhow::anyhow!("Python镜像URL不可用"))?;
    let mut python_command = command(root, recipe);
    // 显式安装允许读取已验SHA的file://镜像；--offline仍禁止网络。
    python_command.env("UV_PYTHON_DOWNLOADS", "manual");
    python_command.args([
        "python",
        "install",
        &recipe.python.version,
        "--no-bin",
        "--no-registry",
        "--mirror",
        mirror_url.as_str(),
    ]);
    super::execute_controlled(python_command, log, &operation.cancel_token())?;
    let python = super::managed_python(root, release)?;
    if super::digest(&python)? != recipe.python.exe_sha256 {
        bail!("基础Python可执行文件摘要不符");
    }

    phase(
        operation,
        ctx,
        OperationPhase::Executing,
        "准备固定版本源码与捆绑网页资源",
    )?;
    if super::verify_source(layout, release).is_err() {
        let staging = root.join(format!("staging/locked-source-{}", super::stamp()));
        layout.ensure_dir(&staging.join("app"))?;
        super::safe_extract::extract(
            &source,
            &staging.join("app"),
            true,
            Some(&operation.cancel_token()),
        )?;
        let mut frontend = std::io::Cursor::new(bundled::FRONTEND);
        let frontend_archive = staging.join("frontend.zip");
        write_new(layout, &frontend_archive, frontend.get_mut())?;
        // 原始跟踪前端先保留在本次staging内，不与新编译文件混合。
        let old = staging.join("app/frontend/dist");
        if old.exists() {
            fs::rename(&old, staging.join("tracked-frontend"))?;
        }
        layout.ensure_dir(&old)?;
        super::safe_extract::extract(
            &frontend_archive,
            &old,
            false,
            Some(&operation.cancel_token()),
        )?;
        if super::digest(&staging.join("app/requirements.txt"))? != recipe.requirements.input_sha256
            || fs::read_to_string(staging.join("app/VERSION"))?.trim() != release.version
        {
            bail!("源码输入与固定配方不符");
        }
        model::write_json_atomic(
            &staging.join("app/.source-integrity.json"),
            &super::manifest(&staging.join("app"))?,
        )?;
        ReleaseReceipt::new(release).store(&staging)?;
        let mut staged_layout = layout.clone();
        staged_layout.app = staging.join("app");
        crate::source_integrity::verify(&staged_layout, release)?;
        super::gui_recovery::publish_source(ctx, release, &staging)?;
    }
    super::verify_source(layout, release)?;
    let mut registry = Registry::load(root)?;
    registry.record_installed(release)?;
    registry.store(root)?;
    registry.upgrade_for_instances(ctx)?;
    static NEXT_INSTANCE: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let serial = NEXT_INSTANCE.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let material = format!(
        "{}:{}:{}:{}:{serial}",
        root.display(),
        release.id,
        super::stamp(),
        std::process::id()
    );
    let id = format!(
        "g{:.16}",
        format!("{:x}", Sha256::digest(material.as_bytes()))
    );
    let instance = instances::create_controlled(
        ctx,
        &id,
        recipe.id(),
        &recipe_sha,
        &operation.cancel_token(),
    )?;
    let environment = instances::path(&instance)?;
    phase(
        operation,
        ctx,
        OperationPhase::Executing,
        "在最终固定路径创建独立GUI环境",
    )?;
    let mut venv = command(root, recipe);
    venv.args(["venv", "--python"])
        .arg(&python)
        .arg(&environment);
    super::execute_controlled(venv, log, &operation.cancel_token())?;
    let lock = root.join("cache").join(&recipe.requirements.lock_filename);
    layout.guard_path(&lock)?;
    if lock.exists() {
        if super::digest(&lock)? != recipe.requirements.lock_sha256 {
            bail!("本地GUI锁被修改");
        }
    } else {
        write_new(layout, &lock, recipe.lock().as_bytes())?;
    }
    let executable = environment.join("Scripts/python.exe");
    let mut sync = command(root, recipe);
    sync.args(["pip", "sync", "--python"])
        .arg(&executable)
        .args(["--no-index", "--find-links"])
        .arg(&wheelhouse)
        .args([
            "--only-binary",
            ":all:",
            "--require-hashes",
            "--link-mode",
            "copy",
            "--strict",
        ])
        .arg(&lock);
    super::execute_controlled(sync, log, &operation.cancel_token())?;
    phase(
        operation,
        ctx,
        OperationPhase::Verifying,
        "验证固定依赖、解释器归属与关键导入",
    )?;
    let clean = instances::validate_new_controlled(
        ctx,
        &instance,
        &[],
        &operation.cancel_token(),
        |environment| {
            super::verify_source(layout, release)?;
            if super::digest(&python)? != recipe.python.exe_sha256 {
                bail!("验证期间基础Python身份改变");
            }
            validate_environment(layout, recipe, environment, log, &operation.cancel_token())
        },
    )?;
    phase(
        operation,
        ctx,
        OperationPhase::Committing,
        "保存已验证环境绑定",
    )?;
    instances::assert_usable(&clean)?;
    let mut registry = Registry::load(root)?;
    registry.bind_gui(
        &release.id,
        model::EnvironmentBinding {
            instance_id: clean.id().into(),
            recipe_id: recipe.id().into(),
            recipe_sha256: recipe_sha,
            generation: clean.generation(),
            storage_version: clean.storage_version(),
        },
    )?;
    if registry.current.is_none() {
        registry.activate(&release.id)?;
    }
    registry.store(root)?;
    Ok(())
}

/// 重建事务拥有最终候选目录和绑定提交；这里只构建独立候选，不改旧绑定或资料。
pub(super) fn build_replacement(
    ctx: &WorkspaceMutation,
    release: &Release,
    environment: &Path,
    operation: &OperationHandle,
    log: &super::Logger,
) -> Result<()> {
    let layout = ctx.layout();
    let root = &layout.root;
    let recipe = GuiRecipe::embedded()?;
    if release.commit != recipe.source_commit
        || !recipe.matches_environment_recipe(&release.environment_recipe)
    {
        bail!("重建目标没有匹配的固定GUI配方");
    }
    preflight_environment_path(root)?;
    layout.guard_path(environment)?;
    super::verify_source(layout, release)?;
    crate::python_integrity::verify(layout)?;
    if super::digest(&super::uv(root))? != recipe.tool_uv.exe_sha256 {
        bail!("重建工具身份不符，请先修复基础工具");
    }
    if fs::read_dir(environment)?.next().is_some() {
        bail!("重建候选目录不是空目录，拒绝覆盖已有环境");
    }
    if fs2::available_space(root)? < 2 * 1024 * 1024 * 1024 {
        bail!("重建卷可用空间不足，请至少保留2GiB；旧实例保持原状");
    }
    let wheelhouse = root.join("cache").join("wheelhouse");
    layout.ensure_dir(&wheelhouse)?;
    let mut downloads = super::artifact_downloads::ArtifactDownloads::new();
    let result = (|| {
        phase(
            operation,
            ctx,
            OperationPhase::Downloading,
            "核对重建所需固定依赖缓存",
        )?;
        for asset in &recipe.wheels {
            operation.cancel_token().check()?;
            let archive = download_in(
                ctx,
                &recipe,
                operation,
                &mut downloads,
                &asset.url,
                &asset.filename,
                &asset.sha256,
                asset.bytes,
            )?;
            let target = wheelhouse.join(&asset.filename);
            layout.guard_path(&target)?;
            if target.exists() {
                if super::digest(&target)? != asset.sha256 {
                    bail!("重建wheelhouse文件摘要不符：{}", asset.filename);
                }
            } else {
                write_new(layout, &target, &fs::read(archive)?)?;
            }
        }
        let lock = root.join("cache").join(&recipe.requirements.lock_filename);
        layout.guard_path(&lock)?;
        if lock.exists() {
            if super::digest(&lock)? != recipe.requirements.lock_sha256 {
                bail!("重建固定依赖锁被修改");
            }
        } else {
            write_new(layout, &lock, recipe.lock().as_bytes())?;
        }
        phase(
            operation,
            ctx,
            OperationPhase::Executing,
            "在新固定路径重建GUI环境，保留旧实例",
        )?;
        let python = super::managed_python(root, release)?;
        if super::digest(&python)? != recipe.python.exe_sha256 {
            bail!("重建基础Python身份不符");
        }
        let mut venv = command(root, &recipe);
        venv.args(["venv", "--python"])
            .arg(&python)
            .arg(environment);
        super::execute_controlled(venv, log, &operation.cancel_token())?;
        let mut sync = command(root, &recipe);
        sync.args(["pip", "sync", "--python"])
            .arg(environment.join("Scripts").join("python.exe"))
            .args(["--no-index", "--find-links"])
            .arg(&wheelhouse)
            .args([
                "--only-binary",
                ":all:",
                "--require-hashes",
                "--link-mode",
                "copy",
                "--strict",
            ])
            .arg(lock);
        super::execute_controlled(sync, log, &operation.cancel_token())
    })();

    result
}

fn preflight_environment_path(root: &Path) -> Result<()> {
    // 固定81wheel真实映射清单：最长原文件152 UTF-16，安装器元数据73。
    // 可选派生pyc不属于安装输出，生产无新bytecode合同独立核验。
    #[cfg(windows)]
    {
        use std::os::windows::ffi::OsStrExt;
        let env = root.join("e/g0000000000000000");
        let total = env.as_os_str().encode_wide().count() + 1 + 152;
        if total > 259 {
            bail!("安装目录过深，固定依赖最长路径将达到{total}个字符（支持上限259）；请选择更短的中文或空格目录。尚未下载或修改安装内容");
        }
    }
    Ok(())
}

pub(super) fn validate_environment(
    layout: &Layout,
    recipe: &GuiRecipe,
    environment: &Path,
    log: &super::Logger,
    cancel: &crate::operations::CancelToken,
) -> Result<()> {
    cancel.check()?;
    let root = &layout.root;
    crate::python_integrity::verify(layout)?;
    let integrity = crate::wheel_integrity::inspect(
        layout,
        environment,
        recipe,
        &root.join("cache/wheelhouse"),
    )?;
    if !integrity.original_files_verified() {
        bail!(
            "GUI依赖原始文件完整性检查失败：{}",
            serde_json::to_string(&integrity)?
        );
    }
    if integrity
        .packages
        .iter()
        .flat_map(|package| &package.generated)
        .any(|file| file.present && file.kind == "optional_derived_bytecode_unverified")
    {
        bail!("环境含未验证的派生字节码，拒绝执行；原始wheel自带文件仍按固定摘要验证");
    }
    validate_environment_runtime(layout, recipe, environment, log, cancel)
}

/// 调用前必须由登记/重建事务完成整个venv的固定可信索引静态核验。
/// 本函数只补实际运行验证，不能独立证明未知解释器/控制文件值得执行。
pub(super) fn validate_environment_runtime(
    layout: &Layout,
    recipe: &GuiRecipe,
    environment: &Path,
    log: &super::Logger,
    cancel: &crate::operations::CancelToken,
) -> Result<()> {
    cancel.check()?;
    let root = &layout.root;
    let fixed_python = crate::python_integrity::verify(layout)?;
    layout.guard_path(&super::uv(root))?;
    if super::digest(&super::uv(root))? != recipe.tool_uv.exe_sha256 {
        bail!("GUI实际运行验证所需uv缺失或摘要不符，拒绝执行");
    }
    layout.guard_path(environment)?;
    let offline = super::gui_entry_probe::OfflineProxy::start()?;
    let executable = environment.join("Scripts/python.exe");
    let mut check = command(root, recipe);
    check
        .args(["--no-cache", "pip", "check", "--python"])
        .arg(&executable);
    offline.apply_command(&mut check)?;
    super::execute_controlled(check, log, cancel)?;
    let mut probe = Command::new(&executable);
    probe
        .args(["-I", "-B", "-c", include_str!("gui_environment_probe.py")])
        .arg(&fixed_python)
        .arg(environment)
        .arg(serde_json::to_string(
            &recipe
                .wheels
                .iter()
                .map(|wheel| (&wheel.name, &wheel.version))
                .collect::<std::collections::BTreeMap<_, _>>(),
        )?);
    offline.apply_command(&mut probe)?;
    super::execute_controlled(probe, log, cancel)
}
