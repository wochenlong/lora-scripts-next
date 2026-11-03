//! 仅验证并收尾既有历史安装事务；不安装、下载、重建、切换版本或修改健康登记。
//! 调用者持有 acquire_existing 的独占租约；本模块只改精确原 journal 和操作记录。
use crate::{
    model::{self, Journal, Layout, Phase, Registry, Release, WorkspaceMutation},
    operations::{CancelReceipt, CancelToken, OperationHandle, OperationPhase},
};
use anyhow::{bail, Context, Result};
use serde::Serialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fmt,
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

const TIMEOUT: Duration = Duration::from_secs(360);
const MAX_RECORD: usize = 32 * 1024 * 1024;
const MAX_TOTAL: usize = 64 * 1024 * 1024;
const MAX_RECORDS: usize = 256;

#[derive(Clone, Serialize)]
pub(crate) struct LegacyRecoveryCandidate {
    pub phase: Phase,
    pub journal_sha256: String,
}

fn legacy(release: &Release) -> bool {
    release.python == "3.10.19"
        && release.environment_recipe
            == format!(
                "gui-requirements-{}-python-{}-v1",
                release.commit, release.python
            )
}

fn hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn read(
    layout: &Layout,
    path: &Path,
    maximum: usize,
    cancel: &CancelToken,
) -> Result<Option<Vec<u8>>> {
    cancel.check()?;
    layout.guard_path(path)?;
    let metadata = match fs::symlink_metadata(path) {
        Ok(value) => value,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error.into()),
    };
    if !metadata.is_file() || metadata.len() > maximum as u64 {
        bail!("历史安装事务元数据不是受限普通文件：{}", path.display());
    }
    let mut input = File::open(path)?.take(maximum as u64 + 1);
    let mut raw = Vec::new();
    let mut block = [0; 65_536];
    loop {
        cancel.check()?;
        let count = input.read(&mut block)?;
        cancel.check()?;
        if count == 0 {
            break;
        }
        if count > maximum - raw.len() {
            bail!("历史安装事务元数据读取超限");
        }
        raw.extend_from_slice(&block[..count]);
    }
    Ok(Some(raw))
}

fn required(layout: &Layout, path: &Path, maximum: usize, cancel: &CancelToken) -> Result<Vec<u8>> {
    read(layout, path, maximum, cancel)?
        .with_context(|| format!("历史安装事务必要记录缺失：{}", path.display()))
}

fn journal_path(layout: &Layout, release: &Release) -> PathBuf {
    layout
        .root
        .join("state")
        .join(format!("journal-{}.json", release.id))
}

fn decode_journal(path: &Path, raw: &[u8]) -> Result<Journal> {
    let journal: Journal = serde_json::from_slice(raw)?;
    model::validate_release_id(&journal.release_id)?;
    if journal.schema_version != 1
        || path.file_name().and_then(|name| name.to_str())
            != Some(format!("journal-{}.json", journal.release_id).as_str())
    {
        bail!("历史安装 journal 的schema、文件名或发布身份不匹配");
    }
    Ok(journal)
}

/// 只读小记录；候选表示存在可显式复验的事务，不证明环境健康，也不放行启动。
pub(crate) fn candidate(root: &Path, release: &Release) -> Result<Option<LegacyRecoveryCandidate>> {
    candidate_controlled(root, release, &CancelToken::new())
}

fn candidate_controlled(
    root: &Path,
    release: &Release,
    cancel: &CancelToken,
) -> Result<Option<LegacyRecoveryCandidate>> {
    release.validate()?;
    if !legacy(release) {
        return Ok(None);
    }
    let layout = Layout::new(root, &release.id)?;
    let path = journal_path(&layout, release);
    let Some(raw) = read(&layout, &path, 65_536, cancel)? else {
        return Ok(None);
    };
    let journal = decode_journal(&path, &raw)?;
    if journal.release_id != release.id {
        bail!("历史安装事务不属于所选发布");
    }
    if journal.phase == Phase::Committed {
        return Ok(None);
    }
    let registry: Registry = serde_json::from_slice(&required(
        &layout,
        &root.join("state/registry.json"),
        MAX_RECORD,
        cancel,
    )?)?;
    registry.validate()?;
    if !registry
        .installed
        .iter()
        .any(|record| record.release_id == release.id && record.gui.is_none())
    {
        bail!("历史安装事务缺少匹配的既有非实例登记");
    }
    Ok(Some(LegacyRecoveryCandidate {
        phase: journal.phase,
        journal_sha256: hash(&raw),
    }))
}

fn directory(layout: &Layout, path: &Path, cancel: &CancelToken) -> Result<Vec<PathBuf>> {
    cancel.check()?;
    layout.guard_path(path)?;
    if !path.exists() {
        return Ok(Vec::new());
    }
    let mut result = Vec::new();
    for entry in fs::read_dir(path)? {
        cancel.check()?;
        if result.len() >= MAX_RECORDS {
            bail!("历史安装恢复事务条目超过上限");
        }
        result.push(entry?.path());
    }
    result.sort();
    Ok(result)
}

fn terminal_gate(root: &Path, raw: &[u8], terminals: &[&str]) -> Result<()> {
    let value: Value = serde_json::from_slice(raw)?;
    if value["schema_version"] != 1 {
        bail!("其他事务schema不支持，原事务保持待恢复");
    }
    for field in ["root", "root_absolute"] {
        if let Some(value) = value.get(field) {
            if value.as_str().map(Path::new) != Some(root) {
                bail!("其他事务安装根身份不符");
            }
        }
    }
    if let Some(id) = value.get("release_id") {
        model::validate_release_id(id.as_str().context("其他事务发布身份无效")?)?;
    }
    let status = value
        .get("status")
        .or_else(|| value.get("phase"))
        .and_then(Value::as_str)
        .context("其他事务状态缺失")?;
    if !terminals.contains(&status) {
        bail!("另有未完成事务（{status}），请先恢复该事务");
    }
    Ok(())
}

#[derive(Default, PartialEq, Eq, Serialize)]
struct Controls(BTreeMap<PathBuf, Option<Vec<u8>>>);

impl Controls {
    fn add(&mut self, layout: &Layout, path: &Path, cancel: &CancelToken) -> Result<()> {
        if self.0.len() >= MAX_RECORDS {
            bail!("历史安装恢复控制记录超过上限");
        }
        self.0
            .insert(path.to_owned(), read(layout, path, MAX_RECORD, cancel)?);
        if self.0.values().flatten().map(Vec::len).sum::<usize>() > MAX_TOTAL {
            bail!("历史安装恢复控制记录总量超限");
        }
        Ok(())
    }

    fn gate(
        &mut self,
        layout: &Layout,
        path: &Path,
        terminals: &[&str],
        cancel: &CancelToken,
    ) -> Result<()> {
        self.add(layout, path, cancel)?;
        if let Some(raw) = &self.0[path] {
            terminal_gate(&layout.root, raw, terminals)?;
        }
        Ok(())
    }
}

fn controls(
    ctx: &WorkspaceMutation,
    release: &Release,
    expected_sha: &str,
    cancel: &CancelToken,
) -> Result<Controls> {
    controls_at(ctx.layout(), release, expected_sha, cancel, None)
}

/// 独立旧环境修复只读保护快照；原recover永远不用这个精确例外。
/// 只把目标pyvenv配置分列给修复的原树备份，不豁免原journal或其他事务。
pub(super) fn capture_for_environment_repair(
    layout: &Layout,
    release: &Release,
    expected_sha: &str,
    own_transaction: Option<&str>,
    cancel: &CancelToken,
) -> Result<Vec<u8>> {
    let mut value = controls_at(layout, release, expected_sha, cancel, own_transaction)?;
    value.0.remove(&layout.environment.join("pyvenv.cfg"));
    Ok(serde_json::to_vec(&value)?)
}

#[derive(Serialize)]
pub(super) struct EnvironmentRepairControlIdentity {
    bytes: usize,
    sha256: String,
}

/// v2只投影已完成原控制验证/事务门的原文字节，不先生成数字字节数组。
/// v1捕获入口保留原编码，持久旧修复事务仍使用其原摘要算法。
pub(super) fn capture_identities_for_environment_repair(
    layout: &Layout,
    release: &Release,
    expected_sha: &str,
    own_transaction: Option<&str>,
    cancel: &CancelToken,
) -> Result<BTreeMap<PathBuf, Option<EnvironmentRepairControlIdentity>>> {
    let mut value = controls_at(layout, release, expected_sha, cancel, own_transaction)?;
    value.0.remove(&layout.environment.join("pyvenv.cfg"));
    value
        .0
        .into_iter()
        .map(|(path, raw)| {
            cancel.check()?;
            Ok((
                path,
                raw.map(|raw| EnvironmentRepairControlIdentity {
                    bytes: raw.len(),
                    sha256: hash(&raw),
                }),
            ))
        })
        .collect()
}

fn controls_at(
    layout: &Layout,
    release: &Release,
    expected_sha: &str,
    cancel: &CancelToken,
    own_transaction: Option<&str>,
) -> Result<Controls> {
    if layout.release_dir != layout.root.join("releases").join(&release.id) {
        bail!("恢复租约与目标发布不一致");
    }
    let catalog = model::Catalog::for_workspace(&layout.root)?;
    if catalog.release(&release.id)? != release {
        bail!("历史安装目标已不匹配当前可信发布目录");
    }
    let record = candidate_controlled(&layout.root, release, cancel)?
        .context("未找到可继续的原历史安装事务")?;
    if record.journal_sha256 != expected_sha {
        bail!("历史安装事务已变化，请重新读取并确认");
    }
    if required(
        layout,
        &layout.root.join(".launcher-workspace"),
        1024,
        cancel,
    )? != model::WORKSPACE_MARKER.as_bytes()
    {
        bail!("历史安装恢复只接受正式工作区");
    }
    let receipt: model::ReleaseReceipt = serde_json::from_slice(&required(
        layout,
        &layout.release_dir.join("release.json"),
        65_536,
        cancel,
    )?)?;
    if receipt.schema_version != 1 || receipt.release != *release {
        bail!("历史安装发布凭据与可信清单不一致");
    }
    match own_transaction {
        Some(transaction) => super::assert_regular_ready_for_legacy_environment_repair(
            &layout.root,
            transaction,
            cancel,
        )?,
        None => super::assert_regular_ready_with_cancel(&layout.root, Some(cancel))?,
    }
    Registry::load(&layout.root)?.assert_base_python_ready()?;
    let mut result = Controls::default();
    for path in [
        layout.root.join(".launcher-workspace"),
        layout.root.join("state/registry.json"),
        layout.release_dir.join("release.json"),
        layout.app.join(".source-integrity.json"),
        layout.environment.join("pyvenv.cfg"),
        layout.profile.join("profile.json"),
        layout.root.join("state/profile-bindings.json"),
        layout.root.join("state/data-import-intent.json"),
    ] {
        result.add(layout, &path, cancel)?;
    }
    for relative in [
        "state/base-python-repair.json",
        "state/profile-binding-intent.json",
    ] {
        result.gate(layout, &layout.root.join(relative), &["committed"], cancel)?;
    }
    for path in directory(layout, &layout.root.join("state"), cancel)? {
        let name = path
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("");
        if name.starts_with("journal-") && path.extension().is_some_and(|ext| ext == "json") {
            result.add(layout, &path, cancel)?;
            let raw = result.0[&path].as_ref().context("journal读取期间消失")?;
            let journal = decode_journal(&path, raw)?;
            if journal.release_id == release.id {
                if hash(raw) != expected_sha || journal.phase == Phase::Committed {
                    bail!("原历史安装 journal 已变化");
                }
            } else if journal.phase != Phase::Committed {
                bail!("另一个发布仍有未完成安装事务");
            }
        } else if name.starts_with("gui-source-")
            && path.extension().is_some_and(|ext| ext == "json")
        {
            result.gate(layout, &path, &["committed", "rolled_back"], cancel)?;
        }
    }
    for (relative, terminals) in [
        ("state/gui-registration", &["committed"][..]),
        ("state/gui-binding-switch", &["committed"][..]),
        ("state/gui-rebuild", &["committed", "orphaned"][..]),
    ] {
        for path in directory(layout, &layout.root.join(relative), cancel)? {
            if path.extension().is_none_or(|ext| ext != "json") {
                bail!("其他事务容器含未知记录");
            }
            result.gate(layout, &path, terminals, cancel)?;
        }
    }
    let active = layout.root.join("updates/shell/active.json");
    result.add(layout, &active, cancel)?;
    if let Some(raw) = &result.0[&active] {
        let value: Value = serde_json::from_slice(raw)?;
        let transaction = value["transaction"].as_str().context("壳事务身份缺失")?;
        model::validate_component(transaction)?;
        if value["schema_version"] != 1
            || value["root_absolute"].as_str().map(Path::new) != Some(layout.root.as_path())
        {
            bail!("壳事务安装根或schema不符");
        }
        let intent = layout
            .root
            .join("updates/shell")
            .join(transaction)
            .join("intent.json");
        required(layout, &intent, MAX_RECORD, cancel)?;
        result.gate(
            layout,
            &intent,
            &["committed", "restored", "aborted"],
            cancel,
        )?;
    }
    cancel.check()?;
    Ok(result)
}

#[derive(Debug)]
struct RecoveryTimedOut;
impl fmt::Display for RecoveryTimedOut {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("历史安装验证超过360秒，原事务保留；没有下载或重建")
    }
}
impl std::error::Error for RecoveryTimedOut {}

struct Watchdog {
    deadline: Instant,
    finished: Arc<AtomicBool>,
    timed_out: Arc<AtomicBool>,
    worker: Option<JoinHandle<()>>,
}
impl Watchdog {
    fn start(cancel: CancelToken, timeout: Duration) -> Result<Self> {
        let deadline = Instant::now() + timeout;
        let finished = Arc::new(AtomicBool::new(false));
        let timed_out = Arc::new(AtomicBool::new(false));
        let done = finished.clone();
        let expired = timed_out.clone();
        let worker = thread::Builder::new()
            .name("legacy-install-deadline".into())
            .spawn(move || {
                while !done.load(Ordering::Acquire) {
                    let now = Instant::now();
                    if now >= deadline {
                        if cancel.request() == CancelReceipt::Accepted {
                            expired.store(true, Ordering::Release);
                        }
                        break;
                    }
                    thread::park_timeout(deadline - now);
                }
            })?;
        Ok(Self {
            deadline,
            finished,
            timed_out,
            worker: Some(worker),
        })
    }

    fn check(&self, cancel: &CancelToken) -> Result<()> {
        if Instant::now() >= self.deadline && cancel.request() == CancelReceipt::Accepted {
            self.timed_out.store(true, Ordering::Release);
        }
        if self.timed_out.load(Ordering::Acquire) {
            return Err(RecoveryTimedOut.into());
        }
        cancel.check()?;
        Ok(())
    }

    fn finish(&mut self) {
        self.finished.store(true, Ordering::Release);
        if let Some(worker) = self.worker.take() {
            worker.thread().unpark();
            let _ = worker.join();
        }
    }
}
impl Drop for Watchdog {
    fn drop(&mut self) {
        self.finish();
    }
}

fn progress(ctx: &WorkspaceMutation, operation: &OperationHandle, message: &str) -> Result<()> {
    operation.cancel_token().check()?;
    operation.publish(OperationPhase::Verifying, message)?;
    operation.persist(ctx)
}

/// 完整验证通过才提交既有journal；失败/取消/超时只产生本操作记录和日志。
pub(crate) fn recover(
    ctx: &WorkspaceMutation,
    release: &Release,
    expected_sha: &str,
    operation: &OperationHandle,
    log: &super::Logger,
) -> Result<()> {
    recover_with_validation(
        ctx,
        release,
        expected_sha,
        operation,
        log,
        TIMEOUT,
        |ctx, cancel| {
            let layout = ctx.layout();
            progress(ctx, operation, "正在校验完整基础Python；不会下载或重建")?;
            crate::python_integrity::verify_controlled(layout, cancel)?;
            layout.guard_path(&super::uv(&layout.root))?;
            if super::digest_controlled(&super::uv(&layout.root), cancel)? != release.uv.exe_sha256
            {
                bail!("自管uv文件摘要不匹配，原事务保持待恢复");
            }
            progress(ctx, operation, "正在校验已有主程序源码")?;
            super::verify_source_controlled(layout, release, cancel)?;
            progress(ctx, operation, "正在校验已有环境配置与实际依赖导入")?;
            super::check_environment_controlled(layout, release, cancel, log)
        },
    )
}

#[allow(clippy::too_many_arguments)] // 私有合同接缝显式传入时限和验证器；生产入口参数不扩展。
fn recover_with_validation(
    ctx: &WorkspaceMutation,
    release: &Release,
    expected_sha: &str,
    operation: &OperationHandle,
    log: &super::Logger,
    timeout: Duration,
    validate: impl FnOnce(&WorkspaceMutation, &CancelToken) -> Result<()>,
) -> Result<()> {
    let cancel = operation.cancel_token();
    let mut watchdog = Watchdog::start(cancel.clone(), timeout)?;
    let result = (|| {
        release.validate()?;
        if !legacy(release)
            || expected_sha.len() != 64
            || !expected_sha
                .bytes()
                .all(|value| value.is_ascii_digit() || (b'a'..=b'f').contains(&value))
        {
            bail!("该历史配方或journal摘要不支持安全验证收尾");
        }
        watchdog.check(&cancel)?;
        let before = controls(ctx, release, expected_sha, &cancel)?;
        progress(ctx, operation, "正在验证原历史安装事务；失败时保留原状")?;
        validate(ctx, &cancel)?;
        watchdog.check(&cancel)?;
        operation.publish(OperationPhase::Committing, "验证通过，正在完成原安装事务")?;
        operation.persist(ctx)?;
        // 所有可能耗时的进度持久化均在最后身份围栏之前。
        if controls(ctx, release, expected_sha, &cancel)? != before {
            bail!("验证期间控制记录发生变化，原事务保持待恢复");
        }
        let path = journal_path(ctx.layout(), release);
        let raw = required(ctx.layout(), &path, 65_536, &cancel)?;
        if hash(&raw) != expected_sha {
            bail!("提交前原journal摘要发生变化");
        }
        let mut journal = decode_journal(&path, &raw)?;
        watchdog.check(&cancel)?;
        cancel.enter_commit()?;
        journal.phase = Phase::Committed;
        journal.updated_at = model::now();
        // 不用Journal::new、mutable/reconcile、安装/修复入口；只替换这一份原记录。
        model::write_json_atomic(&path, &journal)?;
        log(format!(
            "历史安装原事务已完成：{}；当前版本、健康登记和用户资料未修改",
            release.id
        ));
        Ok(())
    })();
    // 等watchdog完成后再分类，避免request已接受、timeout标志尚未写入的竞态。
    watchdog.finish();
    let result = if watchdog.timed_out.load(Ordering::Acquire)
        && result.as_ref().is_err_and(|error| {
            error
                .downcast_ref::<super::ControlledProcessReapFailed>()
                .is_none()
        }) {
        // 不把Cancelled保留在错误链中，避免现有终态收口将超时误标为用户取消。
        Err(RecoveryTimedOut.into())
    } else {
        result
    };
    drop(watchdog);
    super::finish_gui_lifecycle_result(ctx, operation, result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::ReleaseReceipt;
    use crate::operations::{OperationKind, OperationManager, OperationStatus};
    use std::sync::atomic::AtomicU64;
    static NEXT: AtomicU64 = AtomicU64::new(0);

    struct Fixture {
        root: PathBuf,
        release: Release,
        ctx: WorkspaceMutation,
    }
    impl Fixture {
        fn new() -> Self {
            let release = model::Catalog::embedded()
                .unwrap()
                .releases()
                .iter()
                .find(|value| legacy(value))
                .unwrap()
                .clone();
            let root = std::env::temp_dir().join(format!(
                "nt-legacy-resume-{}-{}",
                std::process::id(),
                NEXT.fetch_add(1, Ordering::Relaxed)
            ));
            let ctx = WorkspaceMutation::acquire(&root, &release.id).unwrap();
            let mut registry = Registry::default();
            registry.record_installed(&release).unwrap();
            registry.store(&root).unwrap();
            fs::create_dir_all(&ctx.layout().release_dir).unwrap();
            ReleaseReceipt::new(&release)
                .store(&ctx.layout().release_dir)
                .unwrap();
            Journal::new(&release.id).unwrap().store(&root).unwrap();
            Self { root, release, ctx }
        }
        fn raw(&self) -> Vec<u8> {
            fs::read(journal_path(self.ctx.layout(), &self.release)).unwrap()
        }
        fn sha(&self) -> String {
            hash(&self.raw())
        }
        fn operation(&self) -> (OperationManager, OperationHandle) {
            let manager = OperationManager::default();
            let handle = manager
                .start("legacy-resume-test", OperationKind::Repair)
                .unwrap();
            (manager, handle)
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.root);
        }
    }
    fn logger() -> super::super::Logger {
        Arc::new(|_| {})
    }

    #[test]
    fn environment_repair_identity_projects_validated_raw_controls_without_byte_arrays() {
        let f = Fixture::new();
        let cancel = CancelToken::new();
        let raw =
            capture_for_environment_repair(f.ctx.layout(), &f.release, &f.sha(), None, &cancel)
                .unwrap();
        let identities = capture_identities_for_environment_repair(
            f.ctx.layout(),
            &f.release,
            &f.sha(),
            None,
            &cancel,
        )
        .unwrap();
        let original: BTreeMap<PathBuf, Option<Vec<u8>>> = serde_json::from_slice(&raw).unwrap();
        assert_eq!(identities.len(), original.len());
        assert!(!identities.contains_key(&f.ctx.layout().environment.join("pyvenv.cfg")));
        for (path, bytes) in original {
            match (bytes, &identities[&path]) {
                (None, None) => {}
                (Some(bytes), Some(identity)) => {
                    assert_eq!(identity.bytes, bytes.len());
                    assert_eq!(identity.sha256, hash(&bytes));
                }
                _ => panic!("missing/control身份未保留"),
            }
        }
        let before = serde_json::to_vec(&identities).unwrap();
        fs::create_dir_all(&f.ctx.layout().profile).unwrap();
        fs::write(
            f.ctx.layout().profile.join("profile.json"),
            br#"{"identity_contract":"changed"}"#,
        )
        .unwrap();
        let after = capture_identities_for_environment_repair(
            f.ctx.layout(),
            &f.release,
            &f.sha(),
            None,
            &cancel,
        )
        .unwrap();
        assert_ne!(before, serde_json::to_vec(&after).unwrap());
        let pending = f.root.join("state/base-python-repair.json");
        fs::write(&pending, br#"{"status":"preparing"}"#).unwrap();
        assert!(capture_identities_for_environment_repair(
            f.ctx.layout(),
            &f.release,
            &f.sha(),
            None,
            &cancel
        )
        .is_err());
        assert!(capture_for_environment_repair(
            f.ctx.layout(),
            &f.release,
            &f.sha(),
            None,
            &cancel
        )
        .is_err());
    }

    #[test]
    fn candidate_is_metadata_only_and_never_claims_health() {
        let f = Fixture::new();
        let before = f.raw();
        let value = candidate(&f.root, &f.release).unwrap().unwrap();
        assert_eq!(value.phase, Phase::Preparing);
        assert_eq!(value.journal_sha256, hash(&before));
        assert_eq!(f.raw(), before);
        assert!(!f.ctx.layout().environment.exists());
        let mut journal: Journal = serde_json::from_slice(&before).unwrap();
        journal.phase = Phase::Committed;
        model::write_json_atomic(&journal_path(f.ctx.layout(), &f.release), &journal).unwrap();
        assert!(candidate(&f.root, &f.release).unwrap().is_none());
    }

    #[test]
    fn invalid_journal_schema_identity_and_unknown_fields_are_preserved() {
        let f = Fixture::new();
        let original: Value = serde_json::from_slice(&f.raw()).unwrap();
        for (key, value) in [
            ("schema_version", Value::from(99)),
            ("release_id", Value::from("dev-wrong")),
            ("unknown", Value::from(true)),
        ] {
            let mut changed = original.clone();
            changed[key] = value;
            let path = journal_path(f.ctx.layout(), &f.release);
            model::write_json_atomic(&path, &changed).unwrap();
            let before = f.raw();
            assert!(candidate(&f.root, &f.release).is_err());
            assert_eq!(f.raw(), before);
        }
    }

    #[test]
    fn verification_failure_and_stale_confirmation_never_commit() {
        let f = Fixture::new();
        let before = f.raw();
        let registry = fs::read(f.root.join("state/registry.json")).unwrap();
        let (manager, handle) = f.operation();
        assert!(recover_with_validation(
            &f.ctx,
            &f.release,
            &f.sha(),
            &handle,
            &logger(),
            TIMEOUT,
            |_, _| bail!("validation rejected")
        )
        .is_err());
        assert_eq!(
            manager.snapshot("legacy-resume-test").unwrap().status,
            OperationStatus::Failed
        );
        assert_eq!(f.raw(), before);
        assert_eq!(
            fs::read(f.root.join("state/registry.json")).unwrap(),
            registry
        );
        let (_, handle) = f.operation();
        assert!(recover_with_validation(
            &f.ctx,
            &f.release,
            &"0".repeat(64),
            &handle,
            &logger(),
            TIMEOUT,
            |_, _| panic!("stale confirmation must not validate")
        )
        .is_err());
        assert_eq!(f.raw(), before);
    }

    #[test]
    fn production_validation_missing_python_preserves_all_install_controls() {
        let f = Fixture::new();
        let before = f.raw();
        let registry = fs::read(f.root.join("state/registry.json")).unwrap();
        let receipt = fs::read(f.ctx.layout().release_dir.join("release.json")).unwrap();
        let (manager, handle) = f.operation();
        assert!(recover(&f.ctx, &f.release, &f.sha(), &handle, &logger()).is_err());
        assert_eq!(f.raw(), before);
        assert_eq!(
            fs::read(f.root.join("state/registry.json")).unwrap(),
            registry
        );
        assert_eq!(
            fs::read(f.ctx.layout().release_dir.join("release.json")).unwrap(),
            receipt
        );
        assert_eq!(
            manager.snapshot("legacy-resume-test").unwrap().status,
            OperationStatus::Failed
        );
        assert!(!f.ctx.layout().environment.exists());
    }

    #[test]
    fn unrecognized_python_or_managed_recipe_never_offers_legacy_resume() {
        let f = Fixture::new();
        let mut release = f.release.clone();
        release.python = "3.10.18".into();
        assert!(candidate(&f.root, &release).unwrap().is_none());
        release = f.release.clone();
        release.environment_recipe = "gui-cp310-win-x64-v1".into();
        assert!(candidate(&f.root, &release).unwrap().is_none());
    }

    #[test]
    fn another_pending_journal_and_source_transaction_block_before_validation() {
        for source in [false, true] {
            let f = Fixture::new();
            let before = f.raw();
            let other_id = format!("dev-{}", "a".repeat(40));
            let path = f.root.join("state").join(if source {
                "gui-source-other.json".into()
            } else {
                format!("journal-{other_id}.json")
            });
            let value = if source {
                serde_json::json!({"schema_version":1,"root":f.root,"phase":"pending"})
            } else {
                serde_json::json!({"schema_version":1,"release_id":other_id,"phase":"preparing","updated_at":1})
            };
            model::write_json_atomic(&path, &value).unwrap();
            let other = fs::read(&path).unwrap();
            let (_, handle) = f.operation();
            assert!(recover_with_validation(
                &f.ctx,
                &f.release,
                &f.sha(),
                &handle,
                &logger(),
                TIMEOUT,
                |_, _| panic!("other pending must block")
            )
            .is_err());
            assert_eq!(f.raw(), before);
            assert_eq!(fs::read(path).unwrap(), other);
        }
    }

    #[test]
    fn commit_seam_changes_only_original_journal_phase_and_timestamp() {
        // 纯提交合同注入已验证结果，不代替真实Python/source/environment原生验收。
        let f = Fixture::new();
        let before: Journal = serde_json::from_slice(&f.raw()).unwrap();
        let registry = fs::read(f.root.join("state/registry.json")).unwrap();
        let receipt = fs::read(f.ctx.layout().release_dir.join("release.json")).unwrap();
        let (manager, handle) = f.operation();
        recover_with_validation(
            &f.ctx,
            &f.release,
            &f.sha(),
            &handle,
            &logger(),
            TIMEOUT,
            |_, _| Ok(()),
        )
        .unwrap();
        let after: Journal = serde_json::from_slice(&f.raw()).unwrap();
        assert_eq!(after.phase, Phase::Committed);
        assert_eq!(after.release_id, before.release_id);
        assert_eq!(after.schema_version, before.schema_version);
        assert_eq!(
            fs::read(f.root.join("state/registry.json")).unwrap(),
            registry
        );
        assert_eq!(
            fs::read(f.ctx.layout().release_dir.join("release.json")).unwrap(),
            receipt
        );
        assert_eq!(
            manager.snapshot("legacy-resume-test").unwrap().status,
            OperationStatus::Succeeded
        );
        assert!(candidate(&f.root, &f.release).unwrap().is_none());
    }

    #[test]
    fn user_cancel_and_deadline_are_distinct_and_watchdog_is_joined() {
        for timeout in [false, true] {
            let f = Fixture::new();
            let before = f.raw();
            let (manager, handle) = f.operation();
            let result = recover_with_validation(
                &f.ctx,
                &f.release,
                &f.sha(),
                &handle,
                &logger(),
                if timeout { Duration::ZERO } else { TIMEOUT },
                |_, cancel| {
                    cancel.request();
                    cancel.check()?;
                    Ok(())
                },
            );
            assert!(result.is_err());
            assert_eq!(f.raw(), before);
            assert_eq!(
                manager.snapshot("legacy-resume-test").unwrap().status,
                if timeout {
                    OperationStatus::Failed
                } else {
                    OperationStatus::Cancelled
                }
            );
        }
        let cancel = CancelToken::new();
        let now = Instant::now();
        drop(Watchdog::start(cancel.clone(), TIMEOUT).unwrap());
        assert!(now.elapsed() < Duration::from_secs(1));
        assert!(!cancel.is_cancel_requested());
    }

    #[test]
    fn production_watchdog_reap_failure_keeps_type_and_persisted_code() {
        let f = Fixture::new();
        let before = f.raw();
        let (manager, handle) = f.operation();
        let error = recover_with_validation(
            &f.ctx,
            &f.release,
            &f.sha(),
            &handle,
            &logger(),
            Duration::from_secs(1),
            |_, cancel| {
                // 实际watchdog在生产验证接缝运行期间请求取消，再注入排空失败。
                let deadline = Instant::now() + Duration::from_secs(5);
                while !cancel.is_cancel_requested() {
                    assert!(Instant::now() < deadline, "watchdog未按期请求取消");
                    thread::sleep(Duration::from_millis(1));
                }
                let mut failure = super::super::ControlledProcessReapFailed::new(
                    "synthetic validation reader not joined".into(),
                    true,
                );
                failure.requires_new_host = true;
                Err(failure.into())
            },
        )
        .unwrap_err();
        let failure = error
            .downcast_ref::<super::super::ControlledProcessReapFailed>()
            .unwrap();
        assert!(failure.requires_new_host && failure.cancel_requested);
        assert!(error.downcast_ref::<RecoveryTimedOut>().is_none());
        assert!(error
            .downcast_ref::<crate::operations::Cancelled>()
            .is_none());
        assert_eq!(f.raw(), before);
        let snapshots = crate::operations::load_snapshots(f.ctx.layout()).unwrap();
        let saved = snapshots
            .iter()
            .find(|value| value.id == "legacy-resume-test")
            .unwrap();
        let mut live = manager.snapshot("legacy-resume-test").unwrap();
        live.event_seq = 0;
        assert_eq!(*saved, live);
        assert_eq!(saved.status, OperationStatus::Failed);
        assert_eq!(saved.error.as_ref().unwrap().code, "worker_reap_failed");
        assert!(saved.cancel_requested);
    }

    #[test]
    fn changed_control_record_during_validation_keeps_journal_pending() {
        let f = Fixture::new();
        let before = f.raw();
        let (_, handle) = f.operation();
        assert!(recover_with_validation(
            &f.ctx,
            &f.release,
            &f.sha(),
            &handle,
            &logger(),
            TIMEOUT,
            |ctx, _| {
                // 模拟不遵守租约的外部改动，恢复不得替外部修改“回滚”或签收。
                let path = ctx.layout().root.join("state/registry.json");
                let mut value: Value = serde_json::from_slice(&fs::read(&path)?)?;
                value["installed"][0]["healthy_at"] = 1.into();
                model::write_json_atomic(&path, &value)
            }
        )
        .is_err());
        assert_eq!(f.raw(), before);
    }
}
