//! 固定壳内worker和发布锁；GUI损坏时仍用已验证基础Python，禁止回退到GUI解释器。
use super::{artifact_downloads::ArtifactDownloads, managed_child, Logger};
use crate::{
    model::{self, Layout, Release, WorkspaceMutation},
    operations::{CancelToken, OperationHandle, OperationPhase},
};
use anyhow::{bail, Context, Result};
use fs2::FileExt;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};

include!(concat!(env!("OUT_DIR"), "/engine_assets.rs"));
pub(crate) fn embedded_lock(engine: &str) -> Option<&'static [u8]> {
    ENGINE_LOCKS
        .iter()
        .find(|(id, _)| *id == engine)
        .map(|(_, bytes)| *bytes)
}
macro_rules! worker_file {
    ($name:literal) => {
        (
            $name,
            include_bytes!(concat!("../../../", $name)).as_slice(),
        )
    };
}
const FILES: &[(&str, &[u8])] = &[
    worker_file!("mikazuki/__init__.py"),
    worker_file!("mikazuki/launcher/__init__.py"),
    worker_file!("mikazuki/launcher/runtime.py"),
    worker_file!("mikazuki/launcher/recipes.py"),
    worker_file!("mikazuki/launcher/control.py"),
    worker_file!("mikazuki/launcher/bindings.py"),
    worker_file!("mikazuki/launcher/worker.py"),
    worker_file!("mikazuki/launcher/smoke.py"),
    worker_file!("mikazuki/engines/kohya/manifest.py"),
    worker_file!("mikazuki/engines/kohya/environment.py"),
    worker_file!("mikazuki/engines/kohya/settings.py"),
    worker_file!("mikazuki/engines/anima_fast/manifest.py"),
    worker_file!("mikazuki/engines/anima_fast/environment.py"),
    worker_file!("mikazuki/engines/anima_fast/settings.py"),
    worker_file!("mikazuki/engines/ai_toolkit/manifest.py"),
    worker_file!("mikazuki/engines/ai_toolkit/environment.py"),
    worker_file!("mikazuki/engines/ai_toolkit/settings.py"),
    worker_file!("mikazuki/engines/diffsynth/manifest.py"),
    worker_file!("mikazuki/engines/diffsynth/environment.py"),
    worker_file!("mikazuki/engines/diffsynth/settings.py"),
    worker_file!("config/anima_fast_environment/anima-constraints-cu132.txt"),
    worker_file!("config/anima_fast_environment/anima-overrides-cu132.txt"),
    worker_file!("mikazuki/launcher/requirements/ai-toolkit-base.txt"),
    worker_file!("mikazuki/launcher/requirements/diffsynth-base.txt"),
];

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn fixed_file(layout: &Layout, path: &Path, bytes: &[u8]) -> Result<()> {
    layout.guard_path(path)?;
    // 查询可与安装同时释放同一固定工具；只串行不可变缓存发布，不锁引擎状态。
    let _publish = cache_lease(
        layout,
        &layout.root.join(".launcher-tool-cache-lock"),
        &CancelToken::new(),
    )?;
    if path.exists() {
        if !fs::metadata(path)?.is_file() || fs::read(path)? != bytes {
            bail!("壳内控制文件已变化，拒绝执行：{}", path.display());
        }
    } else {
        layout.ensure_dir(path.parent().context("控制文件缺少父目录")?)?;
        let mut output = OpenOptions::new().write(true).create_new(true).open(path)?;
        output.write_all(bytes)?;
        output.sync_all()?;
    }
    Ok(())
}
fn cache_lease(layout: &Layout, path: &Path, cancel: &CancelToken) -> Result<File> {
    layout.guard_path(path)?;
    layout.ensure_dir(path.parent().context("缓存锁缺少父目录")?)?;
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)?;
    loop {
        cancel.check()?;
        match FileExt::try_lock_exclusive(&file) {
            Ok(()) => return Ok(file),
            Err(error) if error.kind() == fs2::lock_contended_error().kind() => {
                thread::sleep(Duration::from_millis(20));
            }
            Err(error) => return Err(error).context("无法锁定固定资产缓存"),
        }
    }
}
fn engine_id(id: &str) -> Result<()> {
    if !matches!(id, "kohya" | "anima-fast" | "ai-toolkit" | "diffsynth") {
        bail!("未知训练引擎");
    }
    Ok(())
}
fn prepare_worker(layout: &Layout) -> Result<PathBuf> {
    let mut identity = Sha256::new();
    for (name, bytes) in FILES {
        identity.update(name.as_bytes());
        identity.update(Sha256::digest(bytes));
    }
    let directory = layout
        .root
        .join("tools/launcher-worker")
        .join(format!("{:x}", identity.finalize()));
    for (name, bytes) in FILES {
        fixed_file(layout, &directory.join(name), bytes)?;
    }
    Ok(directory.join("mikazuki/launcher/worker.py"))
}
fn lock(layout: &Layout, engine: &str) -> Result<(PathBuf, String)> {
    engine_id(engine)?;
    let (_, bytes) = ENGINE_LOCKS
        .iter()
        .find(|(name, _)| *name == engine)
        .context("此构建尚未封装该引擎的平台资产锁，不能执行安装/修复")?;
    let sha = hash(bytes);
    let path = layout
        .root
        .join("tools/engine-locks")
        .join(format!("{engine}-{sha}.json"));
    fixed_file(layout, &path, bytes)?;
    Ok((path, sha))
}
fn request(layout: &Layout, release: &Release, engine: &str, action: &str) -> Result<Value> {
    engine_id(engine)?;
    let mut value = json!({"schema_version":1,"root":layout.root,"release_id":release.id,"engine_id":engine,"profile_id":layout.profile.file_name().and_then(|s|s.to_str()).context("缺少资料标识")?,"action":action});
    if !matches!(
        action,
        "inspect_readonly"
            | "capabilities"
            | "recipe"
            | "recover"
            | "probe_execute"
            | "availability"
    ) {
        let (path, sha) = lock(layout, engine)?;
        value["lock_path"] = json!(path);
        value["lock_sha256"] = json!(sha);
    }
    Ok(value)
}
fn execute(
    python: &Path,
    worker: &Path,
    root: &Path,
    input: &Value,
    cancel: &CancelToken,
    log: &Logger,
) -> Result<Value> {
    cancel.check()?;
    let mut command = Command::new(python);
    command
        .args(["-I", "-B", "-S"])
        .arg(worker)
        .current_dir(root)
        .env_remove("PYTHONPATH")
        .env_remove("PYTHONHOME")
        .env("PYTHONNOUSERSITE", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    let (mut child, job) = managed_child::spawn(&mut command)?;
    let mut stdin = child.stdin.take().context("独立worker缺少输入管道")?;
    let mut encoded = serde_json::to_vec(input)?;
    encoded.push(b'\n');
    if let Err(error) = stdin.write_all(&encoded) {
        drop(stdin);
        drop(job);
        let _ = child.wait();
        return Err(error.into());
    }
    drop(stdin);
    let stdout = child.stdout.take().context("独立worker缺少输出管道")?;
    let stderr = child.stderr.take().context("独立worker缺少错误管道")?;
    let output = thread::spawn(move || {
        let mut bytes = Vec::new();
        stdout
            .take(4 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)
            .map(|_| bytes)
    });
    let errors = thread::spawn(move || {
        let mut bytes = Vec::new();
        stderr
            .take(1024 * 1024 + 1)
            .read_to_end(&mut bytes)
            .map(|_| bytes)
    });
    let started = Instant::now();
    let status = (|| -> Result<_> {
        loop {
            cancel.check()?;
            if started.elapsed() > Duration::from_secs(1800) {
                bail!("独立引擎操作超时，保留事务供恢复");
            }
            if let Some(status) = child.try_wait()? {
                return Ok(status);
            }
            thread::sleep(Duration::from_millis(40));
        }
    })();
    drop(job);
    let _ = child.kill();
    let _ = child.wait();
    let bytes = output
        .join()
        .map_err(|_| anyhow::anyhow!("worker输出线程异常"))??;
    let error_bytes = errors
        .join()
        .map_err(|_| anyhow::anyhow!("worker日志线程异常"))??;
    if !error_bytes.is_empty() {
        log(String::from_utf8_lossy(&error_bytes).into_owned());
    }
    let status = status?;
    if bytes.len() > 4 * 1024 * 1024 {
        bail!("worker输出超过4MiB");
    }
    let reply: Value = serde_json::from_slice(&bytes).context("独立worker没有返回单一JSON结果")?;
    if reply["schema_version"] != 1 || reply["ok"] != true || !status.success() {
        bail!("引擎操作失败：{}", reply.get("error").unwrap_or(&reply));
    }
    Ok(reply["result"].clone())
}
pub(super) fn query(
    root: &Path,
    release: &Release,
    engine: &str,
    action: &str,
    rebuild: bool,
    log: &Logger,
) -> Result<Value> {
    if !matches!(
        action,
        "capabilities" | "recipe" | "inspect_readonly" | "plan_install" | "plan_repair"
    ) {
        bail!("此接口只接受诊断和计划动作");
    }
    let layout = Layout::new(root, &release.id)?;
    let marker = layout.root.join(".launcher-workspace");
    layout.guard_path(&marker)?;
    if fs::read_to_string(marker)? != model::WORKSPACE_MARKER {
        bail!("只可检查正式启动器工作区");
    }
    super::assert_regular_ready(root)?;
    let python = crate::python_integrity::verify(&layout)?;
    // 只释放内容寻址的固定工具缓存，不取得引擎或工作区变更租约。
    let worker = prepare_worker(&layout)?;
    let mut input = request(&layout, release, engine, action)?;
    input["rebuild"] = json!(rebuild);
    execute(&python, &worker, root, &input, &CancelToken::new(), log)
}
/// 同一交付二进制内的固定微型夹具，必须先在空沙盒显式打开绑定本EXE的测试会话。
pub(super) fn fixture_smoke(root: &Path, release: &Release, log: &Logger) -> Result<Value> {
    let ctx = WorkspaceMutation::acquire(root, &release.id)?;
    super::assert_regular_ready(root)?;
    if crate::signed_catalog::status(root)?["fixture_session"] != true {
        bail!("普通工作区不允许运行测试夹具，请先在全新隔离根打开固定测试会话");
    }
    let python = crate::python_integrity::verify(ctx.layout())?;
    let worker = prepare_worker(ctx.layout())?.with_file_name("smoke.py");
    let unique = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_nanos();
    let parent = root.join("fixture-runs");
    ctx.layout().ensure_dir(&parent)?;
    let fixture = parent.join(format!("engine-smoke-{unique}-{}", std::process::id()));
    ctx.layout().guard_path(&fixture)?;
    if fixture.exists() {
        bail!("夹具根必须是新的独立子目录");
    }
    let input = json!({"schema_version":1,"action":"engine-fixture-v1","root":fixture});
    // 与正常引擎使用同一个Job、stdio、超时、隔离解释器和固定内容释放器。
    execute(&python, &worker, root, &input, &CancelToken::new(), log)
}
pub(super) fn apply(
    root: &Path,
    release: &Release,
    engine: &str,
    action: &str,
    reviewed: Option<&Value>,
    operation: &OperationHandle,
    log: &Logger,
) -> Result<()> {
    if !matches!(action, "repair_apply" | "probe_execute" | "recover") {
        bail!("未知引擎变更动作");
    }
    let ctx = WorkspaceMutation::acquire_shared(root, &release.id)?;
    super::assert_regular_ready(root)?;
    let python = crate::python_integrity::verify(ctx.layout())?;
    let worker = prepare_worker(ctx.layout())?;
    let mut input = request(ctx.layout(), release, engine, action)?;
    let availability = request(ctx.layout(), release, engine, "availability")?;
    let activity = execute(
        &python,
        &worker,
        root,
        &availability,
        &operation.cancel_token(),
        log,
    )?;
    if activity["busy"] == true {
        bail!(
            "{}",
            activity["message"]
                .as_str()
                .unwrap_or("目标引擎正在训练或执行安装/修复，请稍后重试")
        );
    }
    operation.persist(&ctx)?;
    if action == "repair_apply" {
        let plan = reviewed.context("请先审查引擎安装/修复计划")?;
        if plan["engine_id"] != engine || plan["release_id"] != release.id {
            bail!("计划不属于当前引擎/发布");
        }
        input["plan"] = plan.clone();
        input["plan_sha256"] = plan["plan_sha256"].clone();
        let assets = plan["assets"].as_array().context("引擎计划缺少资产清单")?;
        // 只接受内置可信锁中的资产，拒绝UI提交新的URL、命令或哈希。
        let (lock_path, _) = lock(ctx.layout(), engine)?;
        let trusted: Value = serde_json::from_slice(&fs::read(lock_path)?)?;
        let mut allowed = trusted["wheels"]
            .as_array()
            .context("引擎锁缺少依赖闭包")?
            .clone();
        for item in [&trusted["python"]["archive"], &trusted["source"]["archive"]] {
            if item.is_object() {
                allowed.push(item.clone());
            }
        }
        allowed.push(if trusted["uv"]["archive"].is_object() {
            trusted["uv"]["archive"].clone()
        } else {
            trusted["uv"].clone()
        });
        if assets.iter().any(|asset| !allowed.contains(asset)) {
            bail!("计划包含未获内置锁授权的资产");
        }
        let cap = assets.iter().try_fold(0u64, |sum, item| {
            sum.checked_add(item["bytes"].as_u64().context("资产大小无效")?)
                .context("下载大小溢出")
        })?;
        if cap > 64 * 1024 * 1024 * 1024 {
            bail!("单引擎资产超过64GiB上限");
        }
        let mut downloads = ArtifactDownloads::new();
        let fetched = (|| -> Result<()> {
            operation.publish(OperationPhase::Downloading, "准备已锁定的独立引擎资产")?;
            for asset in assets {
                let name = asset["filename"].as_str().context("缺少资产文件名")?;
                model::validate_component(name)?;
                let sha = asset["sha256"].as_str().context("缺少资产摘要")?;
                model::validate_component(sha)?;
                // 不同引擎可共用依赖；同哈希的续传文件和发布动作只允许一个写者。
                let _asset = cache_lease(
                    ctx.layout(),
                    &root
                        .join("cache/engine-asset-locks")
                        .join(format!("{sha}.lock")),
                    &operation.cancel_token(),
                )?;
                let target = ctx
                    .layout()
                    .root
                    .join("cache/engine-assets")
                    .join(sha)
                    .join(name);
                ctx.layout().guard_path(&target)?;
                let bytes = asset["bytes"].as_u64().context("缺少资产大小")?;
                if target.is_file()
                    && fs::metadata(&target)?.len() == bytes
                    && super::digest(&target)? == sha
                {
                    continue;
                }
                if let Some((_, embedded)) = ENGINE_WHEELS
                    .iter()
                    .find(|(filename, content)| *filename == name && hash(content) == sha)
                {
                    fixed_file(ctx.layout(), &target, embedded)?;
                } else {
                    let cached = downloads.download(
                        &ctx,
                        asset["url"].as_str().context("缺少资产URL")?,
                        name,
                        sha,
                        bytes,
                        &operation.cancel_token(),
                    )?;
                    ctx.layout()
                        .ensure_dir(target.parent().context("缺少资产父目录")?)?;
                    if target.exists() {
                        bail!("引擎缓存已有不同内容，请保留现场并诊断");
                    }
                    fs::copy(cached, &target)?;
                    if super::digest(&target)? != sha {
                        bail!("引擎缓存复制校验失败");
                    }
                }
            }
            Ok(())
        })();

        fetched?;
    }
    operation.publish(
        OperationPhase::Executing,
        "在独立解释器和事务中执行引擎操作",
    )?;
    operation.persist(&ctx)?;
    // 生命周期共享门贯穿下载和worker；Python另取目标引擎锁并重新核验计划。
    let result = execute(
        &python,
        &worker,
        root,
        &input,
        &operation.cancel_token(),
        log,
    )?;
    // worker 已释放独立引擎租约；短事务内重读并同步已选组合的权威代次。
    // 新安装的引擎不会被隐式选入资料组合，旧健康组合仍保留原身份。
    let _state = ctx.state_lease()?;
    crate::data_import::sync_current_engine(&ctx, &release.id, engine)?;
    log(serde_json::to_string(&result)?);
    Ok(())
}
pub(super) fn context(layout: &Layout, release: &Release) -> Result<String> {
    let mut catalog = serde_json::Map::new();
    for (id, _) in ENGINE_LOCKS {
        let (path, sha) = lock(layout, id)?;
        catalog.insert((*id).into(), json!({"lock_path":path,"sha256":sha}));
    }
    serde_json::to_string(&json!({"schema_version":1,"root":layout.root,"release_id":release.id,"profile_id":layout.profile.file_name().and_then(|s|s.to_str()),"engine_catalog":catalog})).map_err(Into::into)
}
