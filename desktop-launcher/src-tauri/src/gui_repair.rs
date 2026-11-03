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
    process::Command,
};

const MAX_INTENT: u64 = 8 * 1024 * 1024;
const MAX_METADATA: u64 = 2 * 1024 * 1024;
const MAX_WORKER_RECORD: u64 = 64 * 1024;
const MAX_WORKERS: usize = 32;
const MAX_WORKER_RECORDS: usize = 128;

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
    pub recovery_blocker: Option<String>,
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

/// 原Intent仍是schema 1且不增加字段。侧录绑定它的完整原文字节，不能用
/// “没有失败标志”代替跨重启的worker排空证明。
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct WorkerRecord {
    schema_version: u32,
    component: String,
    intent: Intent,
    intent_sha256: String,
    workers: Vec<WorkerAttempt>,
    needs_attention: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct WorkerAttempt {
    job_name: String,
    session_id: u32,
    host_pid: u32,
    host_creation_time: u64,
    phase: WorkerPhase,
    pid: Option<u32>,
    reap_proof: Option<ReapProof>,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum WorkerPhase {
    Launching,
    Attached,
    Reaped,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum ReapProof {
    HeldJobDrained,
    AttachedJobDrained,
    AttachedJobDestroyed,
    NoWorkerStarted,
}

fn reap_failed(reason: impl Into<String>) -> anyhow::Error {
    super::ControlledProcessReapFailed::new(reason.into(), false).into()
}

fn worker_path(layout: &Layout, instance: &str) -> Result<PathBuf> {
    model::validate_component(instance)?;
    let path = layout
        .root
        .join("state/gui-repair-workers")
        .join(format!("{instance}.json"));
    layout.guard_path(&path)?;
    Ok(path)
}

fn workers_reaped(record: &WorkerRecord) -> bool {
    record.needs_attention.is_none()
        && record
            .workers
            .iter()
            .all(|worker| worker.phase == WorkerPhase::Reaped)
}

fn validate_worker_record(layout: &Layout, release: &Release, record: &WorkerRecord) -> Result<()> {
    validate_intent(layout, release, &record.intent)?;
    if record.schema_version != 1
        || record.component != "gui-package-repair-workers"
        || record.intent_sha256.len() != 64
        || !record
            .intent_sha256
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
        || record.workers.len() > MAX_WORKERS
        || record
            .needs_attention
            .as_ref()
            .is_some_and(|reason| reason.len() > 4096)
    {
        bail!("修复worker侧录schema或大小不合法，保留现场");
    }
    let mut names = BTreeSet::new();
    for worker in &record.workers {
        let nonce = worker
            .job_name
            .strip_prefix("Local\\NextTrainerLegacyRepair-")
            .context("修复worker命名空间不符")?;
        if nonce.len() != 64
            || !nonce
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            || !names.insert(&worker.job_name)
            || worker.pid == Some(0)
            || worker.host_pid == 0
            || worker.host_creation_time == 0
        {
            bail!("修复worker身份无效或重复");
        }
        match worker.phase {
            WorkerPhase::Launching if worker.pid.is_none() && worker.reap_proof.is_none() => {}
            WorkerPhase::Attached if worker.pid.is_some() && worker.reap_proof.is_none() => {}
            WorkerPhase::Reaped => match (&worker.pid, worker.reap_proof) {
                (None, Some(ReapProof::NoWorkerStarted)) => {}
                (Some(_), Some(proof)) if proof != ReapProof::NoWorkerStarted => {}
                _ => bail!("已排空worker缺少对应进程归属或证明"),
            },
            _ => bail!("修复worker阶段/归属/排空证明不一致"),
        }
    }
    Ok(())
}

fn read_worker_record(
    layout: &Layout,
    release: &Release,
    instance: &str,
) -> Result<Option<WorkerRecord>> {
    let path = worker_path(layout, instance)?;
    if !path.try_exists()? {
        return Ok(None);
    }
    let record: WorkerRecord =
        serde_json::from_str(&small_text(layout, &path, MAX_WORKER_RECORD)?)?;
    validate_worker_record(layout, release, &record)?;
    if record.intent.instance_id != instance {
        bail!("修复worker侧录文件名与实例不匹配");
    }
    Ok(Some(record))
}

fn assert_record_intent(
    layout: &Layout,
    release: &Release,
    intent: &Intent,
    record: &WorkerRecord,
) -> Result<()> {
    validate_worker_record(layout, release, record)?;
    let raw = small_text(
        layout,
        &intent_path(layout, &intent.instance_id)?,
        MAX_INTENT,
    )?;
    if record.intent != *intent || record.intent_sha256 != hash(raw.as_bytes()) {
        bail!("修复worker侧录与原intent原文不匹配，禁止清障或恢复");
    }
    Ok(())
}

fn store_worker_record(
    layout: &Layout,
    release: &Release,
    expected: Option<&WorkerRecord>,
    record: &WorkerRecord,
) -> Result<()> {
    assert_record_intent(layout, release, &record.intent, record)?;
    let bytes = serde_json::to_vec(record)?;
    if bytes.len() as u64 > MAX_WORKER_RECORD {
        bail!("修复worker侧录超限");
    }
    let path = worker_path(layout, &record.intent.instance_id)?;
    layout.ensure_dir(path.parent().context("worker侧录缺少父目录")?)?;
    if read_worker_record(layout, release, &record.intent.instance_id)?.as_ref() != expected {
        bail!("修复worker侧录已变化，拒绝覆盖或清障");
    }
    if expected.is_none() {
        let mut file = File::options().write(true).create_new(true).open(path)?;
        file.write_all(&bytes)?;
        file.sync_all()?;
        Ok(())
    } else {
        model::write_json_atomic(&path, record)
    }
}

fn ensure_worker_record(
    layout: &Layout,
    release: &Release,
    intent: &Intent,
) -> Result<WorkerRecord> {
    let previous = read_worker_record(layout, release, &intent.instance_id)?;
    if let Some(record) = &previous {
        if record.intent == *intent {
            assert_record_intent(layout, release, intent, record)?;
            return Ok(record.clone());
        }
        if !workers_reaped(record) {
            return Err(reap_failed(
                "前一次单包修复仍无完整排空证明，保留旧worker侧录",
            ));
        }
    }
    let raw = small_text(
        layout,
        &intent_path(layout, &intent.instance_id)?,
        MAX_INTENT,
    )?;
    let record = WorkerRecord {
        schema_version: 1,
        component: "gui-package-repair-workers".into(),
        intent: intent.clone(),
        intent_sha256: hash(raw.as_bytes()),
        workers: Vec::new(),
        needs_attention: None,
    };
    store_worker_record(layout, release, previous.as_ref(), &record)?;
    Ok(record)
}

fn assert_workers_reaped(
    layout: &Layout,
    release: &Release,
    intent: &Intent,
    dirty: bool,
) -> Result<()> {
    match read_worker_record(layout, release, &intent.instance_id)? {
        Some(record) => {
            assert_record_intent(layout, release, intent, &record)?;
            if !workers_reaped(&record) {
                return Err(reap_failed(
                    "单包修复worker尚未证明排空，实例保持needs_attention；须显式核验该事务归属",
                ));
            }
        }
        None if dirty => {
            return Err(reap_failed(
                "旧单包修复dirty事务没有可重开的持久Job归属，不能凭PID消失或没有失败文件恢复快照",
            ));
        }
        None => {} // 旧prepared未开始或已clean提交窗口保持原兼容边界。
    }
    Ok(())
}

/// 普通启动/修改/旧resume共用此门。恢复例外只能来自下方精确生产接缝。
pub(super) fn assert_worker_reap_ready(root: &Path) -> Result<()> {
    assert_worker_reap_ready_except(root, None)
}

/// 从正式registry和原Intent推导精确例外，不能由UI传“跳过整个release”。
/// 仅允许该侧录进入显式排空；其他侧录、坏记录和匿名dirty仍不会被放行恢复。
pub(super) fn assert_worker_reap_ready_for_recovery(root: &Path, release: &Release) -> Result<()> {
    let layout = Layout::new(root, &release.id)?;
    let registry = Registry::load(root)?;
    let binding = registry
        .gui_binding(&release.id)
        .context("不存在待恢复实例绑定")?;
    let intent = read_intent(&layout, release, &binding.instance_id)?;
    assert_worker_reap_ready_except(root, Some((&layout, release, &intent)))
}

fn assert_worker_reap_ready_except(
    root: &Path,
    own: Option<(&Layout, &Release, &Intent)>,
) -> Result<()> {
    let catalog = model::Catalog::for_workspace(root)?;
    let release = catalog.releases().first().context("工作区没有可核验发布")?;
    let layout = Layout::new(root, &release.id)?;
    let directory = root.join("state/gui-repair-workers");
    layout.guard_path(&directory)?;
    let mut count = 0usize;
    if directory.try_exists()? {
        for item in fs::read_dir(&directory)? {
            count += 1;
            if count > MAX_WORKER_RECORDS {
                bail!("单包修复worker侧录数量超限");
            }
            let path = item?.path();
            layout.guard_path(&path)?;
            if path.extension().is_none_or(|ext| ext != "json") {
                bail!("单包修复worker容器含未知记录");
            }
            let instance = path
                .file_stem()
                .and_then(|name| name.to_str())
                .context("worker侧录文件名非法")?;
            let raw: WorkerRecord =
                serde_json::from_str(&small_text(&layout, &path, MAX_WORKER_RECORD)?)?;
            let target = catalog.release(&raw.intent.release_id)?;
            let target_layout = Layout::new(root, &target.id)?;
            validate_worker_record(&target_layout, target, &raw)?;
            if raw.intent.instance_id != instance {
                bail!("worker侧录文件名与实例不匹配");
            }
            if workers_reaped(&raw) {
                continue;
            }
            if let Some((own_layout, own_release, intent)) = own {
                if raw.intent == *intent {
                    assert_record_intent(own_layout, own_release, intent, &raw)?;
                    continue;
                }
            }
            return Err(reap_failed(format!(
                "{} / {}：未完成worker排空证明，禁止启动或变更；保留needs_attention",
                target.id, instance
            )));
        }
    }
    // 旧匿名执行器没有侧录的dirty修复不能靠“目录不存在”绕过新门。
    // prepared未运行或已经clean的旧提交窗口继续保持原有语义。
    let intents = root.join("state/gui-repairs");
    layout.guard_path(&intents)?;
    if intents.try_exists()? {
        for (index, item) in fs::read_dir(&intents)?.enumerate() {
            if index >= MAX_WORKER_RECORDS {
                bail!("单包修复intent数量超限");
            }
            let path = item?.path();
            layout.guard_path(&path)?;
            if path.extension().is_none_or(|ext| ext != "json") {
                bail!("单包修复intent容器含未知记录");
            }
            let raw: Intent = serde_json::from_str(&small_text(&layout, &path, MAX_INTENT)?)?;
            let target = catalog.release(&raw.release_id)?;
            let target_layout = Layout::new(root, &target.id)?;
            if path != intent_path(&target_layout, &raw.instance_id)? {
                bail!("原修复intent路径与实例不匹配");
            }
            validate_intent(&target_layout, target, &raw)?;
            let state = instances::load(&target_layout, &raw.instance_id)?;
            if !state.dirty() {
                continue;
            }
            if let Some((_, _, intent)) = own {
                if *intent == raw {
                    continue; // 精确显式recover内部仍会拒绝无持久归属的匿名dirty。
                }
            }
            assert_workers_reaped(&target_layout, target, &raw, true)?;
        }
    }
    Ok(())
}

fn recover_workers(layout: &Layout, release: &Release, intent: &Intent, dirty: bool) -> Result<()> {
    recover_workers_with(layout, release, intent, dirty, |worker| {
        // Job只能证明后代进程排空，不能证明仍活宿主内的reader/logger线程结束。
        // 旧宿主代次确实退出后，新宿主才可解除跨重启屏障。
        super::assert_controlled_host_exited(&super::ControlledHostIdentity {
            pid: worker.host_pid,
            creation_time: worker.host_creation_time,
        })?;
        match super::Job::reap_named_attached(&worker.job_name, worker.session_id, true)? {
            super::NamedJobReap::Drained => Ok(ReapProof::AttachedJobDrained),
            super::NamedJobReap::Destroyed => Ok(ReapProof::AttachedJobDestroyed),
        }
    })
}

/// 私有合同只替换OS证明，不替换Intent/持久屏障或恢复写入门。
fn recover_workers_with(
    layout: &Layout,
    release: &Release,
    intent: &Intent,
    dirty: bool,
    prove: impl Fn(&WorkerAttempt) -> Result<ReapProof>,
) -> Result<()> {
    let Some(mut record) = read_worker_record(layout, release, &intent.instance_id)? else {
        return assert_workers_reaped(layout, release, intent, dirty);
    };
    assert_record_intent(layout, release, intent, &record)?;
    for index in 0..record.workers.len() {
        let worker = &record.workers[index];
        if worker.phase == WorkerPhase::Reaped {
            continue;
        }
        if worker.phase != WorkerPhase::Attached {
            return Err(reap_failed(
                "worker仍在launching窗口，未持久attached；即使Job不存在也不能证明排空",
            ));
        }
        let proof = prove(worker)?;
        if !matches!(
            proof,
            ReapProof::AttachedJobDrained | ReapProof::AttachedJobDestroyed
        ) {
            return Err(reap_failed("显式恢复缺少可信attached命名Job排空证明"));
        }
        let previous = record.clone();
        record.workers[index].phase = WorkerPhase::Reaped;
        record.workers[index].reap_proof = Some(proof);
        record.needs_attention = None;
        store_worker_record(layout, release, Some(&previous), &record)?;
    }
    // 排空失败可能发生在写attention后、旧worker状态已经reaped的窗口。
    // 只在全体命名worker各自有证明后清除，空记录不能替代缺失的归属。
    if !record.workers.is_empty()
        && record
            .workers
            .iter()
            .all(|worker| worker.phase == WorkerPhase::Reaped)
        && record.needs_attention.is_some()
    {
        let previous = record.clone();
        record.needs_attention = None;
        store_worker_record(layout, release, Some(&previous), &record)?;
    }
    assert_workers_reaped(layout, release, intent, dirty)
}

fn run_worker(
    layout: &Layout,
    release: &Release,
    intent: &Intent,
    command: Command,
    log: &super::Logger,
    cancel: &CancelToken,
) -> Result<()> {
    cancel.check()?;
    let mut record = ensure_worker_record(layout, release, intent)?;
    if !workers_reaped(&record) || record.workers.len() >= MAX_WORKERS {
        return Err(reap_failed("单包修复存在未排空worker或命令数已达上限"));
    }
    let name = super::Job::generate_legacy_repair_name()?;
    let session_id = super::Job::current_session_id()?;
    let host = super::current_controlled_host_identity()?;
    let previous = record.clone();
    record.workers.push(WorkerAttempt {
        job_name: name.clone(),
        session_id,
        host_pid: host.pid,
        host_creation_time: host.creation_time,
        phase: WorkerPhase::Launching,
        pid: None,
        reap_proof: None,
    });
    store_worker_record(layout, release, Some(&previous), &record)?;
    let index = record.workers.len() - 1;
    let job = super::Job::create_named(&name)
        .map_err(|error| reap_failed(format!("命名Job创建失败；launching现场保持：{error:#}")))?;
    let result = super::execute_controlled_in_job(command, log, cancel, &job, |pid| {
        let previous = record.clone();
        record.workers[index].phase = WorkerPhase::Attached;
        record.workers[index].pid = Some(pid);
        store_worker_record(layout, release, Some(&previous), &record)
    });
    if let Err(error) = &result {
        if error
            .downcast_ref::<super::ControlledProcessReapFailed>()
            .is_some()
        {
            let previous = record.clone();
            record.needs_attention =
                Some("worker_reap_failed：保留原快照，后续显式恢复必须重新证明Job排空".into());
            store_worker_record(layout, release, Some(&previous), &record).map_err(|persist| {
                reap_failed(format!(
                    "worker排空失败且屏障更新失败：{persist:#}；原launching/attached侧录保留"
                ))
            })?;
            return result;
        }
    }
    // execute_controlled_in_job合同：普通错误也必须已回收Child/reader/Job。
    // 再持本Job核active0；不能仅因父进程退出或取消回执而清障。
    if job.active_processes().map_err(|error| {
        reap_failed(format!(
            "受管执行返回后Job活动进程不可核验，保持恢复屏障：{error:#}"
        ))
    })? != 0
    {
        return Err(reap_failed(
            "受管执行返回后Job仍含活动进程；保留attached屏障",
        ));
    }
    let proof = if record.workers[index].pid.is_some() {
        ReapProof::HeldJobDrained
    } else {
        ReapProof::NoWorkerStarted
    };
    let previous = record.clone();
    record.workers[index].phase = WorkerPhase::Reaped;
    record.workers[index].reap_proof = Some(proof);
    record.needs_attention = None;
    store_worker_record(layout, release, Some(&previous), &record).map_err(|error| {
        reap_failed(format!(
            "Job已排空但证明未成功持久化，保留恢复屏障：{error:#}"
        ))
    })?;
    result
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
    let recovery_blocker = match read_worker_record(&layout, release, instance.id()) {
        Ok(Some(record)) if !workers_reaped(&record) => Some(
            "worker_reap_failed：尚无完整进程/宿主排空证明；请关闭旧启动器后从原事务显式恢复。旧匿名事务保持needs_attention".into(),
        ),
        Err(error) => Some(format!("修复worker侧录不可核验，保留现场：{error:#}")),
        _ => None,
    };
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
        recovery_pending: intent_path(&layout, instance.id())?.try_exists()?
            || recovery_blocker.is_some(),
        recovery_blocker,
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
    if let Some(error) = &diagnosis.recovery_blocker {
        bail!("{error}");
    }
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

/// 这是正式execute的prepared窗口，不由只读plan调用。预验证可能执行Python，
/// 因此必须先保存同一Intent/worker侧录；reader排空失败也不能遗失跨重启屏障。
fn prepare_intent_with_validation(
    layout: &Layout,
    release: &Release,
    intent: &Intent,
    validate: impl FnOnce() -> Result<()>,
) -> Result<()> {
    create_intent(layout, release, intent)?;
    let mut record = ensure_worker_record(layout, release, intent)?;
    if !workers_reaped(&record) {
        return Err(reap_failed("新修复不能覆盖旧worker失败或未排空侧录"));
    }
    // create_new刚成功，说明这是一次新的正式执行，而非同一命令链中的下一条。
    // 只有严格全reaped的历史才可重置，避免同代重复预验证耗尽命令数。
    if !record.workers.is_empty() {
        let previous = record.clone();
        record.workers.clear();
        store_worker_record(layout, release, Some(&previous), &record)?;
    }
    match validate() {
        Ok(()) => Ok(()), // 后续begin或prepared恢复继续使用同一Intent。
        Err(error) => {
            if error
                .downcast_ref::<super::ControlledProcessReapFailed>()
                .is_some()
            {
                return Err(error); // 不能以状态仍clean或尚未begin为由清掉屏障。
            }
            assert_workers_reaped(layout, release, intent, false)?;
            clear_intent(layout, release, intent)?;
            Err(error)
        }
    }
}

fn clear_intent(layout: &Layout, release: &Release, intent: &Intent) -> Result<()> {
    if read_intent(layout, release, &intent.instance_id)? != *intent {
        bail!("修复 intent 已改变，拒绝清除");
    }
    assert_workers_reaped(layout, release, intent, false)?;
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
    assert_workers_reaped(ctx.layout(), release, intent, false)?;
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

#[allow(clippy::too_many_arguments)]
fn validate_recorded(
    layout: &Layout,
    release: &Release,
    recipe: &GuiRecipe,
    environment: &Path,
    intent: &Intent,
    log: &super::Logger,
    cancel: &CancelToken,
) -> Result<()> {
    super::verify_source(layout, release)?;
    layout.guard_path(&super::uv(&layout.root))?;
    if super::digest(&super::uv(&layout.root))? != recipe.tool_uv.exe_sha256 {
        bail!("受管 uv 身份改变");
    }
    super::gui_install::validate_environment_with_runner(
        layout,
        recipe,
        environment,
        log,
        cancel,
        &mut |command| run_worker(layout, release, intent, command, log, cancel),
    )
}

fn reinstall(
    ctx: &WorkspaceMutation,
    release: &Release,
    recipe: &GuiRecipe,
    preview: &RepairPreview,
    intent: &Intent,
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
    run_worker(
        layout,
        release,
        intent,
        command,
        log,
        &operation.cancel_token(),
    )
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
    let result = execute_inner(ctx, release, package, plan_sha256, operation, log)
        .and_then(|()| crate::data_import::sync_current_environment(ctx, &release.id));
    finish(ctx, operation, &result)?;
    result
}

fn finish(ctx: &WorkspaceMutation, operation: &OperationHandle, result: &Result<()>) -> Result<()> {
    let (status, error) = match result {
        Ok(()) => (OperationStatus::Succeeded, None),
        Err(error)
            if error
                .downcast_ref::<super::ControlledProcessReapFailed>()
                .is_some() =>
        {
            (
                OperationStatus::Failed,
                Some(OperationError {
                    code: "worker_reap_failed".into(),
                    message: format!("{error:#}"),
                }),
            )
        }
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
    assert_worker_reap_ready(&layout.root)?;
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
    let transaction = instances::plan_controlled(
        ctx,
        &preview.instance_id,
        preview.generation,
        &preview.paths,
        &operation.cancel_token(),
    )?;
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
    prepare_intent_with_validation(layout, release, &intent, || {
        if preview.before_original_files_verified {
            validate_recorded(
                layout,
                release,
                &recipe,
                &layout.environment,
                &intent,
                log,
                &operation.cancel_token(),
            )
        } else {
            log(
                "修复前原文件存在缺坏，pip check/关键导入被静态完整性门阻止；将在修复后实测".into(),
            );
            Ok(())
        }
    })?;
    let ticket = match instances::begin_controlled(ctx, &transaction, &operation.cancel_token()) {
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
        reinstall(ctx, release, &recipe, &preview, &intent, operation, log)?;
        operation.cancel_token().check()?;
        phase(
            ctx,
            operation,
            OperationPhase::Verifying,
            "全量验证原文件、pip check、解释器归属与关键导入",
        )?;
        instances::commit_controlled(ctx, &ticket, &operation.cancel_token(), |environment| {
            validate_recorded(
                layout,
                release,
                &recipe,
                environment,
                &intent,
                log,
                &operation.cancel_token(),
            )
        })
    })();
    let clean = match attempt {
        Ok(clean) => clean,
        Err(error) => {
            if error
                .downcast_ref::<super::ControlledProcessReapFailed>()
                .is_some()
            {
                // 未证明 writer/后代排空时不能搬回快照，否则仍运行的进程可能
                // 改写已恢复的原件。dirty 与 intent 保留，交显式恢复处理。
                log("worker_reap_failed：实例保持 dirty 与 intent，不自动恢复快照".into());
                return Err(error);
            }
            assert_workers_reaped(layout, release, &intent, true)?;
            let _ = phase(
                ctx,
                operation,
                OperationPhase::Recovering,
                "还原独立快照并重新验证，尚不代表环境健康",
            );
            let recovered =
                instances::recover_controlled(ctx, &ticket, &CancelToken::new(), |environment| {
                    validate_recorded(
                        layout,
                        release,
                        &recipe,
                        environment,
                        &intent,
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
                Err(recovery)
                    if recovery.downcast_ref::<super::ControlledProcessReapFailed>().is_some() =>
                {
                    return Err(recovery.context(format!(
                        "修复失败：{error:#}；快照复验worker未排空，保持恢复屏障"
                    )));
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
    let result = recover_inner(ctx, release, operation, log)
        .and_then(|()| crate::data_import::sync_current_environment(ctx, &release.id));
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
    recover_workers(layout, release, &intent, state.dirty())?;
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
        instances::recover_controlled(ctx, &ticket, &operation.cancel_token(), |environment| {
            validate_recorded(
                layout,
                release,
                &recipe,
                environment,
                &intent,
                log,
                &CancelToken::new(),
            )
        })?
    } else {
        instances::assert_usable(&state)?;
        validate_recorded(
            layout,
            release,
            &recipe,
            &instances::path(&state)?,
            &intent,
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

    fn pending_worker(
        ctx: &WorkspaceMutation,
        release: &Release,
        intent: &Intent,
        phase: WorkerPhase,
    ) -> WorkerRecord {
        let mut record = ensure_worker_record(ctx.layout(), release, intent).unwrap();
        let previous = record.clone();
        record.workers.push(WorkerAttempt {
            job_name: format!("Local\\NextTrainerLegacyRepair-{}", "b".repeat(64)),
            session_id: 1,
            host_pid: 42,
            host_creation_time: 123,
            phase,
            pid: (phase == WorkerPhase::Attached).then_some(43),
            reap_proof: None,
        });
        record.needs_attention = Some("worker_reap_failed；合同夹具，不是实际OS排空证明".into());
        store_worker_record(ctx.layout(), release, Some(&previous), &record).unwrap();
        record
    }

    fn bound_context() -> (PathBuf, WorkspaceMutation, Release) {
        let (root, ctx, release) = context();
        let state = instances::create(
            &ctx,
            "g0000000000000002",
            "gui-cp310-win-x64-v1",
            &recipe_sha(),
        )
        .unwrap();
        fs::write(
            instances::path(&state).unwrap().join("target.py"),
            b"healthy",
        )
        .unwrap();
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
                    recipe_sha256: state.recipe_sha256().into(),
                    generation: state.generation(),
                    storage_version: state.storage_version(),
                },
            )
            .unwrap();
        registry.store(&root).unwrap();
        (root, ctx, release)
    }

    #[test]
    fn prevalidation_persists_worker_identity_before_commands_and_retains_prepared_intent() {
        let (root, ctx, release) = context();
        let original = intent(&ctx, &release);
        prepare_intent_with_validation(ctx.layout(), &release, &original, || {
            assert_eq!(
                read_intent(ctx.layout(), &release, &original.instance_id)?,
                original
            );
            let record = read_worker_record(ctx.layout(), &release, &original.instance_id)?
                .context("执行任何预验证命令前必须已有侧录")?;
            assert_record_intent(ctx.layout(), &release, &original, &record)?;
            assert!(workers_reaped(&record));
            Ok(())
        })
        .unwrap();
        assert!(intent_path(ctx.layout(), &original.instance_id)
            .unwrap()
            .exists());
        clear_intent(ctx.layout(), &release, &original).unwrap();
        drop(ctx);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn prevalidation_ordinary_error_clears_prepared_intent_only_after_reap_proof() {
        let (root, ctx, release) = context();
        let original = intent(&ctx, &release);
        let result = prepare_intent_with_validation(ctx.layout(), &release, &original, || {
            pending_worker(&ctx, &release, &original, WorkerPhase::Attached);
            // 私有合同替换OS证明；真实进程/reader回收另由executor合同验证。
            recover_workers_with(ctx.layout(), &release, &original, false, |_| {
                Ok(ReapProof::AttachedJobDrained)
            })?;
            bail!("prevalidation import failed after controlled reap")
        });
        assert!(result
            .unwrap_err()
            .to_string()
            .contains("prevalidation import failed"));
        assert!(!intent_path(ctx.layout(), &original.instance_id)
            .unwrap()
            .exists());
        let record = read_worker_record(ctx.layout(), &release, &original.instance_id)
            .unwrap()
            .unwrap();
        assert!(workers_reaped(&record));
        assert!(super::super::assert_regular_ready(&root).is_ok());
        drop(ctx);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn new_prevalidation_resets_only_fully_reaped_history_after_intent_create_new() {
        let (root, ctx, release) = context();
        let original = intent(&ctx, &release);
        create_intent(ctx.layout(), &release, &original).unwrap();
        let mut record = ensure_worker_record(ctx.layout(), &release, &original).unwrap();
        let previous = record.clone();
        for index in 0..MAX_WORKERS {
            record.workers.push(WorkerAttempt {
                job_name: format!("Local\\NextTrainerLegacyRepair-{index:064x}"),
                session_id: 1,
                host_pid: 42,
                host_creation_time: 123,
                phase: WorkerPhase::Reaped,
                pid: Some(43 + index as u32),
                reap_proof: Some(ReapProof::HeldJobDrained),
            });
        }
        store_worker_record(ctx.layout(), &release, Some(&previous), &record).unwrap();
        let original_bytes =
            fs::read(intent_path(ctx.layout(), &original.instance_id).unwrap()).unwrap();
        let sidecar = worker_path(ctx.layout(), &original.instance_id).unwrap();
        let before = fs::read(&sidecar).unwrap();
        assert!(
            prepare_intent_with_validation(ctx.layout(), &release, &original, || {
                panic!("已有Intent时不能重置历史或开始新命令")
            })
            .is_err()
        );
        assert_eq!(fs::read(&sidecar).unwrap(), before);
        assert_eq!(
            fs::read(intent_path(ctx.layout(), &original.instance_id).unwrap()).unwrap(),
            original_bytes
        );
        clear_intent(ctx.layout(), &release, &original).unwrap();
        prepare_intent_with_validation(ctx.layout(), &release, &original, || {
            let fresh = read_worker_record(ctx.layout(), &release, &original.instance_id)?.unwrap();
            assert!(fresh.workers.is_empty());
            assert!(workers_reaped(&fresh));
            assert_record_intent(ctx.layout(), &release, &original, &fresh)
        })
        .unwrap();
        clear_intent(ctx.layout(), &release, &original).unwrap();
        drop(ctx);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn new_prevalidation_preserves_unreaped_failed_and_foreign_sidecars() {
        for case in ["attached", "attention", "foreign"] {
            let (root, ctx, release) = context();
            let original = intent(&ctx, &release);
            create_intent(ctx.layout(), &release, &original).unwrap();
            let mut record = pending_worker(&ctx, &release, &original, WorkerPhase::Attached);
            let sidecar = worker_path(ctx.layout(), &original.instance_id).unwrap();
            if case != "attached" {
                let previous = record.clone();
                record.workers[0].phase = WorkerPhase::Reaped;
                record.workers[0].reap_proof = Some(ReapProof::HeldJobDrained);
                store_worker_record(ctx.layout(), &release, Some(&previous), &record).unwrap();
                if case == "foreign" {
                    record.intent.root_absolute = root.join("foreign");
                    fs::write(&sidecar, serde_json::to_vec(&record).unwrap()).unwrap();
                }
            }
            // 故障夹具模拟原Intent丢失，不能以新create_new成功抹掉残留屏障。
            fs::remove_file(intent_path(ctx.layout(), &original.instance_id).unwrap()).unwrap();
            let before = fs::read(&sidecar).unwrap();
            assert!(
                prepare_intent_with_validation(ctx.layout(), &release, &original, || {
                    panic!("活worker、失败屏障或异根身份不能被重置")
                })
                .is_err()
            );
            assert_eq!(fs::read(&sidecar).unwrap(), before);
            assert_eq!(
                read_intent(ctx.layout(), &release, &original.instance_id).unwrap(),
                original
            );
            drop(ctx);
            fs::remove_dir_all(root).unwrap();
        }
    }

    #[test]
    fn prevalidation_reap_failure_survives_clean_state_restart_and_uses_exact_core_recovery_gate() {
        let (root, ctx, release) = bound_context();
        let original = intent(&ctx, &release);
        let result = prepare_intent_with_validation(ctx.layout(), &release, &original, || {
            pending_worker(&ctx, &release, &original, WorkerPhase::Attached);
            Err(reap_failed(
                "预验证reader未回收；虽然尚未begin也必须保留屏障",
            ))
        });
        assert!(result
            .unwrap_err()
            .downcast_ref::<super::super::ControlledProcessReapFailed>()
            .is_some());
        assert!(!instances::load(ctx.layout(), &original.instance_id)
            .unwrap()
            .dirty());
        let original_bytes =
            fs::read(intent_path(ctx.layout(), &original.instance_id).unwrap()).unwrap();
        let sidecar = worker_path(ctx.layout(), &original.instance_id).unwrap();
        let worker_bytes = fs::read(&sidecar).unwrap();
        drop(ctx);
        let reopened = WorkspaceMutation::acquire_existing(&root, &release.id).unwrap();
        let blocked = super::super::assert_regular_ready(&root).unwrap_err();
        assert!(blocked
            .downcast_ref::<super::super::ControlledProcessReapFailed>()
            .is_some());
        assert!(super::super::assert_regular_ready_for_gui_recovery(
            &root,
            &release,
            &CancelToken::new()
        )
        .is_ok());
        assert!(clear_intent(reopened.layout(), &release, &original).is_err());
        let other = Intent {
            instance_id: "g0000000000000003".into(),
            ..original.clone()
        };
        create_intent(reopened.layout(), &release, &other).unwrap();
        pending_worker(&reopened, &release, &other, WorkerPhase::Attached);
        let blocked = super::super::assert_regular_ready_for_gui_recovery(
            &root,
            &release,
            &CancelToken::new(),
        )
        .unwrap_err();
        assert!(blocked
            .downcast_ref::<super::super::ControlledProcessReapFailed>()
            .is_some());
        assert_eq!(fs::read(&sidecar).unwrap(), worker_bytes);
        assert_eq!(
            fs::read(intent_path(reopened.layout(), &original.instance_id).unwrap()).unwrap(),
            original_bytes
        );
        drop(reopened);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn worker_reap_barrier_survives_restart_and_prevents_intent_clear() {
        let (root, ctx, release) = bound_context();
        let original = intent(&ctx, &release);
        create_intent(ctx.layout(), &release, &original).unwrap();
        pending_worker(&ctx, &release, &original, WorkerPhase::Attached);
        let sidecar = worker_path(ctx.layout(), &original.instance_id).unwrap();
        let before = fs::read(&sidecar).unwrap();
        let original_bytes =
            fs::read(intent_path(ctx.layout(), &original.instance_id).unwrap()).unwrap();
        drop(ctx);
        let reopened = WorkspaceMutation::acquire_existing(&root, &release.id).unwrap();
        assert!(assert_worker_reap_ready(&root).is_err());
        assert!(clear_intent(reopened.layout(), &release, &original).is_err());
        assert_eq!(fs::read(sidecar).unwrap(), before);
        assert_eq!(
            fs::read(intent_path(reopened.layout(), &original.instance_id).unwrap()).unwrap(),
            original_bytes
        );
        drop(reopened);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn anonymous_dirty_never_uses_missing_barrier_as_reap_proof() {
        let (root, ctx, release) = context();
        let original = intent(&ctx, &release);
        create_intent(ctx.layout(), &release, &original).unwrap();
        let before = fs::read(intent_path(ctx.layout(), &original.instance_id).unwrap()).unwrap();
        assert!(assert_workers_reaped(ctx.layout(), &release, &original, true).is_err());
        // 已clean与未运行prepared不被新屏障扩大限制。
        assert!(assert_workers_reaped(ctx.layout(), &release, &original, false).is_ok());
        assert!(
            recover_workers_with(ctx.layout(), &release, &original, true, |_| {
                panic!("匿名dirty没有可证明的Job，不能进入恢复证明回调")
            })
            .is_err()
        );
        assert!(!worker_path(ctx.layout(), &original.instance_id)
            .unwrap()
            .exists());
        assert_eq!(
            fs::read(intent_path(ctx.layout(), &original.instance_id).unwrap()).unwrap(),
            before
        );
        drop(ctx);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn launching_window_and_live_old_host_preserve_durable_barrier() {
        let (root, ctx, release) = context();
        let original = intent(&ctx, &release);
        create_intent(ctx.layout(), &release, &original).unwrap();
        let launching = pending_worker(&ctx, &release, &original, WorkerPhase::Launching);
        let path = worker_path(ctx.layout(), &original.instance_id).unwrap();
        let before = fs::read(&path).unwrap();
        assert!(
            recover_workers_with(ctx.layout(), &release, &original, true, |_| {
                panic!("launching即使notfound也不能进入正向证明")
            })
            .is_err()
        );
        assert_eq!(fs::read(&path).unwrap(), before);
        let mut attached = launching.clone();
        attached.workers[0].phase = WorkerPhase::Attached;
        attached.workers[0].pid = Some(43);
        store_worker_record(ctx.layout(), &release, Some(&launching), &attached).unwrap();
        let before = fs::read(&path).unwrap();
        assert!(
            recover_workers_with(ctx.layout(), &release, &original, true, |_| {
                Err(reap_failed(
                    "旧host代次仍活；不能以Job active0跳过reader屏障",
                ))
            })
            .is_err()
        );
        assert_eq!(fs::read(path).unwrap(), before);
        drop(ctx);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn attached_recovery_requires_exact_intent_and_trusted_reap_kind() {
        let (root, ctx, release) = context();
        let original = intent(&ctx, &release);
        create_intent(ctx.layout(), &release, &original).unwrap();
        pending_worker(&ctx, &release, &original, WorkerPhase::Attached);
        let path = worker_path(ctx.layout(), &original.instance_id).unwrap();
        let before = fs::read(&path).unwrap();
        assert!(
            recover_workers_with(ctx.layout(), &release, &original, true, |_| {
                Ok(ReapProof::HeldJobDrained)
            })
            .is_err()
        );
        assert_eq!(fs::read(&path).unwrap(), before);
        let original_path = intent_path(ctx.layout(), &original.instance_id).unwrap();
        let raw = fs::read(&original_path).unwrap();
        let mut changed = raw.clone();
        changed.push(b'\n'); // 即使JSON语义相同，原文SHA变化仍不能清障。
        fs::write(&original_path, changed).unwrap();
        assert!(
            recover_workers_with(ctx.layout(), &release, &original, true, |_| {
                panic!("原Intent字节变化必须在OS证明前拒绝")
            })
            .is_err()
        );
        assert_eq!(fs::read(&path).unwrap(), before);
        fs::write(&original_path, raw).unwrap();
        // 只验证持久状态机；真实Job/host证明由生产OS合同另验。
        recover_workers_with(ctx.layout(), &release, &original, true, |_| {
            Ok(ReapProof::AttachedJobDestroyed)
        })
        .unwrap();
        assert!(assert_workers_reaped(ctx.layout(), &release, &original, true).is_ok());
        let reaped = read_worker_record(ctx.layout(), &release, &original.instance_id)
            .unwrap()
            .unwrap();
        assert_eq!(
            reaped.workers[0].reap_proof,
            Some(ReapProof::AttachedJobDestroyed)
        );
        clear_intent(ctx.layout(), &release, &original).unwrap();
        assert!(worker_path(ctx.layout(), &original.instance_id)
            .unwrap()
            .exists());
        drop(ctx);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn exact_recovery_exception_does_not_bypass_another_worker_barrier() {
        let (root, ctx, release) = context();
        let own = intent(&ctx, &release);
        create_intent(ctx.layout(), &release, &own).unwrap();
        pending_worker(&ctx, &release, &own, WorkerPhase::Attached);
        let other = Intent {
            instance_id: "g0000000000000003".into(),
            ..own.clone()
        };
        create_intent(ctx.layout(), &release, &other).unwrap();
        pending_worker(&ctx, &release, &other, WorkerPhase::Attached);
        let own_before = fs::read(worker_path(ctx.layout(), &own.instance_id).unwrap()).unwrap();
        let other_before =
            fs::read(worker_path(ctx.layout(), &other.instance_id).unwrap()).unwrap();
        assert!(
            assert_worker_reap_ready_except(&root, Some((ctx.layout(), &release, &own))).is_err()
        );
        assert_eq!(
            fs::read(worker_path(ctx.layout(), &own.instance_id).unwrap()).unwrap(),
            own_before
        );
        assert_eq!(
            fs::read(worker_path(ctx.layout(), &other.instance_id).unwrap()).unwrap(),
            other_before
        );
        drop(ctx);
        fs::remove_dir_all(root).unwrap();
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
