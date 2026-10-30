//! 制品HTTP正文预算；不是TCP/TLS或任意子进程网络计量。
//!
//! 写调用只准在传入 begin 的同一 WorkspaceMutation 仍存活时使用。
//! Session 可 Clone 以传入受控异步任务；上层必须 abort 并 await/drain 所有
//! 任务后才释放 lease。本模块不再次 acquire，也不把 Layout 当成独立租约。
//! ReadCredit 不可 Clone；丢弃它绝不返还已持久预留。finish 或下次
//! begin 持真实 lease 后，将无法结算的预留一次转为 uncertain 扣账。
use crate::model::{self, Layout, WorkspaceMutation};
use anyhow::{bail, Context, Result};
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex, OnceLock,
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

pub const READ_QUANTUM: usize = 65_536;
pub const MEASUREMENT: &str = "http_body_delivered_v1";
const SCHEMA: u32 = 1;
const MAX_RECORD: u64 = 65_536;
const MAX_RECEIPTS: usize = 10_000;
const LEDGER_NAME: &str = "download-budget.json";
const ENROLLMENT_NAME: &str = "download-budget-enrollment.json";
static NEXT: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct DownloadPolicy {
    // 字段必须存在：null表示关闭累计上限；旧版数字上限按原值读取。
    #[serde(deserialize_with = "Deserialize::deserialize")]
    pub root_cap_body_bytes: Option<u64>,
}

#[cfg(test)]
#[path = "download_budget_fault_tests.rs"]
mod fault_tests;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OperationLimits {
    pub max_charged_body_bytes: u64,
    pub max_requests: u32,
    pub max_retries: u32,
    pub max_redirects: u32,
    pub max_elapsed_ms: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PriorCoverage {
    /// 未发现旧制品/控制记录；不由此推断曾经的网卡流量为0。
    NoPriorArtifactEvidence,
    NotMeasured,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DownloadOutcome {
    Succeeded,
    Failed,
    Cancelled,
    Interrupted,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AttemptOutcome {
    Completed,
    Failed,
    Cancelled,
    Redirected,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AttemptKind {
    Initial,
    Retry,
    Redirect,
}

#[derive(Clone, Debug)]
pub struct AssetIdentity {
    pub sha256: String,
    /// exact URL 的SHA，不写入含token的原URL。
    pub url_sha256: String,
    pub authority: String,
}

/// 每次请求唯一身份。只是引用，不授予跨session写权。
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AttemptId(u64);

/// 不可Clone；Drop无磁盘写、无退款。必须settle或uncertain，否则保持预留。
#[derive(Debug)]
pub struct ReadCredit {
    session_id: String,
    attempt: u64,
    read_seq: u64,
    bytes: u64,
}
impl ReadCredit {
    pub fn bytes(&self) -> usize {
        self.bytes as usize
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(deny_unknown_fields)]
pub struct Counters {
    pub observed_body_bytes: u64,
    pub uncertain_charge_bytes: u64,
    pub requests: u64,
    pub retries: u64,
    pub redirects: u64,
    pub cache_hits: u64,
}
impl Counters {
    fn charged(&self) -> Result<u64> {
        self.observed_body_bytes
            .checked_add(self.uncertain_charge_bytes)
            .context("下载计账溢出")
    }
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Attempt {
    id: u64,
    asset_sha256: String,
    url_sha256: String,
    authority: String,
    read_seq: u64,
    reserved_body_bytes: u64,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Active {
    operation_id: String,
    session_id: String,
    retry_of: Option<String>,
    started_at_ms: u64,
    start_generation: u64,
    root_start_counters: Counters,
    policy_revision: u64,
    limits: OperationLimits,
    counters: Counters,
    next_attempt: u64,
    attempt: Option<Attempt>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OperationDownloadReceipt {
    pub schema_version: u32,
    pub measurement: String,
    pub workspace_id: String,
    pub operation_id: String,
    pub retry_of: Option<String>,
    pub outcome: DownloadOutcome,
    pub accounting_complete: bool,
    pub started_at_ms: u64,
    pub finished_at_ms: u64,
    pub policy_revision: u64,
    pub limits: OperationLimits,
    pub counters: Counters,
    pub start_generation: u64,
    pub end_generation: u64,
    pub root_start_counters: Counters,
    pub root_end_counters: Counters,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Ledger {
    schema_version: u32,
    measurement: String,
    workspace_id: String,
    root_absolute: PathBuf,
    generation: u64,
    coverage_started_at_ms: u64,
    coverage_prior_history: PriorCoverage,
    policy_revision: u64,
    policy: DownloadPolicy,
    counters: Counters,
    active: Option<Active>,
    terminal_outbox: Option<OperationDownloadReceipt>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
enum EnrollmentPhase {
    Pending,
    Active,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct Enrollment {
    schema_version: u32,
    root_absolute: PathBuf,
    workspace_id: String,
    phase: EnrollmentPhase,
    /// Pending时唯一可恢复genesis；Active后也保留以核身份，不用它归零。
    genesis: Ledger,
}

#[derive(Clone, Debug, Serialize)]
pub struct DownloadBudgetView {
    pub measurement: &'static str,
    pub enabled: bool,
    pub coverage_prior_history: Option<PriorCoverage>,
    pub policy_revision: Option<u64>,
    pub root_cap_body_bytes: Option<u64>,
    pub counters: Counters,
    pub reserved_body_bytes: u64,
    pub remaining_body_bytes: Option<u64>,
    pub generation: Option<u64>,
    pub active_operation: Option<String>,
    pub active_counters: Option<Counters>,
    pub operation_remaining_body_bytes: Option<u64>,
    pub pending_reconciliation: bool,
}

struct State {
    ledger: Ledger,
    /// 原字节CAS，防本机并发/外来改动被此session静默覆盖。
    committed_bytes: Vec<u8>,
    enrollment_bytes: Vec<u8>,
    poisoned: bool,
}

/// 可跨受控任务Clone，但调用者必须保留begin的workspace lease直到全部任务drain。
#[derive(Clone)]
pub struct DownloadBudget {
    layout: Layout,
    operation_id: String,
    session_id: String,
    started: Instant,
    state: Arc<Mutex<State>>,
    _live: Arc<LiveSession>,
}

static LIVE: OnceLock<Mutex<BTreeSet<PathBuf>>> = OnceLock::new();
struct LiveSession {
    root: PathBuf,
}
impl LiveSession {
    fn acquire(root: &Path) -> Result<Arc<Self>> {
        let mut roots = LIVE
            .get_or_init(Mutex::default)
            .lock()
            .map_err(|_| anyhow::anyhow!("下载session索引锁异常"))?;
        if !roots.insert(root.to_owned()) {
            bail!("同根已有活动下载预算session，禁止重复begin");
        }
        Ok(Arc::new(Self {
            root: root.to_owned(),
        }))
    }
}
impl Drop for LiveSession {
    fn drop(&mut self) {
        if let Some(roots) = LIVE.get() {
            if let Ok(mut roots) = roots.lock() {
                roots.remove(&self.root);
            }
        }
    }
}

fn now_ms() -> Result<u64> {
    let value = SystemTime::now().duration_since(UNIX_EPOCH)?.as_millis();
    u64::try_from(value).context("时钟范围溢出")
}
fn hash(value: &[u8]) -> String {
    format!("{:x}", Sha256::digest(value))
}
fn identity(root: &Path) -> Result<String> {
    let serial = NEXT.fetch_add(1, Ordering::Relaxed);
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos();
    Ok(hash(
        format!("{}|{}|{stamp}|{serial}", root.display(), std::process::id()).as_bytes(),
    ))
}
fn valid_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn operation_id(value: &str) -> Result<()> {
    model::validate_component(value)?;
    if value.is_empty()
        || value.len() > 96
        || !value
            .bytes()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || b"-_".contains(&c))
    {
        bail!("下载操作ID无效");
    }
    Ok(())
}
fn validate_policy(policy: &DownloadPolicy) -> Result<()> {
    if policy.root_cap_body_bytes == Some(0) {
        bail!("累计下载正文上限必须大于0，或关闭上限");
    }
    Ok(())
}
fn validate_limits(limits: &OperationLimits) -> Result<()> {
    if limits.max_charged_body_bytes == 0
        || limits.max_requests == 0
        || limits.max_elapsed_ms == 0
        || limits.max_elapsed_ms > 7 * 24 * 60 * 60 * 1000
        || limits.max_retries > limits.max_requests
        || limits.max_redirects > limits.max_requests
    {
        bail!("单操作下载额度/请求次数/期限无效");
    }
    Ok(())
}
fn path(layout: &Layout, name: &str) -> Result<PathBuf> {
    let value = layout.root.join("state").join(name);
    layout.guard_path(&value)?;
    Ok(value)
}
fn ledger_path(layout: &Layout) -> Result<PathBuf> {
    path(layout, LEDGER_NAME)
}
fn enrollment_path(layout: &Layout) -> Result<PathBuf> {
    path(layout, ENROLLMENT_NAME)
}
fn receipt_directory(layout: &Layout) -> Result<PathBuf> {
    let value = layout.root.join("state/download-receipts");
    layout.guard_path(&value)?;
    Ok(value)
}
fn read_bytes(layout: &Layout, value: &Path) -> Result<Option<Vec<u8>>> {
    layout.guard_path(value)?;
    let metadata = match fs::symlink_metadata(value) {
        Ok(value) => value,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error).context("读取下载计账元数据失败"),
    };
    if !metadata.is_file() || metadata.len() > MAX_RECORD {
        bail!("下载计账只接受64KiB内普通文件，原状态保留");
    }
    let mut input = File::open(value)?;
    let mut bytes = Vec::new();
    Read::by_ref(&mut input)
        .take(MAX_RECORD + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_RECORD {
        bail!("下载计账读取超限");
    }
    layout.guard_path(value)?;
    Ok(Some(bytes))
}
fn decode<T: DeserializeOwned>(bytes: &[u8]) -> Result<T> {
    serde_json::from_slice(bytes).context("下载计账损坏或schema不支持；保留原状态")
}
fn write<T: Serialize>(layout: &Layout, value: &Path, data: &T) -> Result<Vec<u8>> {
    layout.guard_path(value)?;
    let mut bytes = serde_json::to_vec_pretty(data)?;
    bytes.push(b'\n');
    if bytes.len() as u64 > MAX_RECORD {
        bail!("下载计账序列化超过64KiB");
    }
    model::write_json_atomic(value, data)?;
    if read_bytes(layout, value)?.as_deref() != Some(bytes.as_slice()) {
        bail!("下载计账写后字节核对失败");
    }
    Ok(bytes)
}
fn reserve(ledger: &Ledger) -> u64 {
    ledger
        .active
        .as_ref()
        .and_then(|a| a.attempt.as_ref())
        .map_or(0, |a| a.reserved_body_bytes)
}
fn add(value: &mut u64, amount: u64) -> Result<()> {
    *value = value.checked_add(amount).context("下载计数溢出")?;
    Ok(())
}
fn remaining(cap: u64, counters: &Counters, reserved: u64) -> Result<u64> {
    cap.checked_sub(
        counters
            .charged()?
            .checked_add(reserved)
            .context("额度加法溢出")?,
    )
    .context("下载计账超过持久额度")
}
fn root_remaining(cap: Option<u64>, counters: &Counters, reserved: u64) -> Result<Option<u64>> {
    let charged = counters
        .charged()?
        .checked_add(reserved)
        .context("额度加法溢出")?;
    cap.map(|limit| limit.checked_sub(charged).context("下载计账超过持久额度"))
        .transpose()
}
fn validate_asset(asset: &AssetIdentity) -> Result<()> {
    if !valid_hash(&asset.sha256)
        || !valid_hash(&asset.url_sha256)
        || asset.authority.is_empty()
        || asset.authority.len() > 512
        || !asset.authority.is_ascii()
        || asset
            .authority
            .bytes()
            .any(|c| c.is_ascii_whitespace() || c.is_ascii_control() || b"/@?#\\".contains(&c))
    {
        bail!("下载资产身份无效；不得在authority保存凭据或完整URL");
    }
    Ok(())
}

fn validate_counters(value: &Counters) -> Result<()> {
    value.charged()?;
    if value
        .retries
        .checked_add(value.redirects)
        .context("请求计数溢出")?
        > value.requests
    {
        bail!("重试或跳转计数大于请求数");
    }
    Ok(())
}
fn counters_sum(before: &Counters, operation: &Counters) -> Result<Counters> {
    let sum = |left: u64, right: u64| left.checked_add(right).context("下载计数合并溢出");
    Ok(Counters {
        observed_body_bytes: sum(before.observed_body_bytes, operation.observed_body_bytes)?,
        uncertain_charge_bytes: sum(
            before.uncertain_charge_bytes,
            operation.uncertain_charge_bytes,
        )?,
        requests: sum(before.requests, operation.requests)?,
        retries: sum(before.retries, operation.retries)?,
        redirects: sum(before.redirects, operation.redirects)?,
        cache_hits: sum(before.cache_hits, operation.cache_hits)?,
    })
}
fn validate_receipt(value: &OperationDownloadReceipt, workspace_id: &str) -> Result<()> {
    operation_id(&value.operation_id)?;
    if let Some(retry) = &value.retry_of {
        operation_id(retry)?;
        if retry == &value.operation_id {
            bail!("操作不能重试自身ID");
        }
    }
    validate_limits(&value.limits)?;
    validate_counters(&value.counters)?;
    validate_counters(&value.root_start_counters)?;
    validate_counters(&value.root_end_counters)?;
    if value.schema_version != SCHEMA
        || value.measurement != MEASUREMENT
        || value.workspace_id != workspace_id
        || !value.accounting_complete
        || value.policy_revision == 0
        || value.start_generation >= value.end_generation
        || value.counters.charged()? > value.limits.max_charged_body_bytes
        || value.counters.requests > u64::from(value.limits.max_requests)
        || value.counters.retries > u64::from(value.limits.max_retries)
        || value.counters.redirects > u64::from(value.limits.max_redirects)
        || counters_sum(&value.root_start_counters, &value.counters)? != value.root_end_counters
    {
        bail!("下载receipt身份或计数无效");
    }
    Ok(())
}
fn validate_ledger(layout: &Layout, value: &Ledger) -> Result<()> {
    if value.schema_version != SCHEMA
        || value.measurement != MEASUREMENT
        || value.root_absolute != layout.root
        || !valid_hash(&value.workspace_id)
        || value.generation == 0
        || value.policy_revision == 0
        || value.active.is_some() && value.terminal_outbox.is_some()
    {
        bail!("下载账本身份/schema无效，保留原状态");
    }
    validate_policy(&value.policy)?;
    validate_counters(&value.counters)?;
    root_remaining(
        value.policy.root_cap_body_bytes,
        &value.counters,
        reserve(value),
    )?;
    if let Some(active) = &value.active {
        operation_id(&active.operation_id)?;
        if let Some(retry) = &active.retry_of {
            operation_id(retry)?;
            if retry == &active.operation_id {
                bail!("操作不能重试自身ID");
            }
        }
        validate_limits(&active.limits)?;
        validate_counters(&active.counters)?;
        validate_counters(&active.root_start_counters)?;
        if !valid_hash(&active.session_id)
            || active.policy_revision != value.policy_revision
            || active.start_generation >= value.generation
            || active.next_attempt == 0
            || active.counters.requests > u64::from(active.limits.max_requests)
            || active.counters.retries > u64::from(active.limits.max_retries)
            || active.counters.redirects > u64::from(active.limits.max_redirects)
            || active.counters.requests >= active.next_attempt
            || active.counters.observed_body_bytes > value.counters.observed_body_bytes
            || active.counters.uncertain_charge_bytes > value.counters.uncertain_charge_bytes
            || active.counters.requests > value.counters.requests
            || counters_sum(&active.root_start_counters, &active.counters)? != value.counters
        {
            bail!("下载操作预算身份或计数无效");
        }
        remaining(
            active.limits.max_charged_body_bytes,
            &active.counters,
            reserve(value),
        )?;
        if let Some(attempt) = &active.attempt {
            validate_asset(&AssetIdentity {
                sha256: attempt.asset_sha256.clone(),
                url_sha256: attempt.url_sha256.clone(),
                authority: attempt.authority.clone(),
            })?;
            if attempt.id == 0
                || attempt.id >= active.next_attempt
                || attempt.read_seq == 0
                || attempt.reserved_body_bytes > READ_QUANTUM as u64
            {
                bail!("下载attempt/read预留无效");
            }
        }
    }
    if let Some(receipt) = &value.terminal_outbox {
        validate_receipt(receipt, &value.workspace_id)?;
        if receipt.end_generation > value.generation || receipt.root_end_counters != value.counters
        {
            bail!("下载terminal outbox与总账不一致");
        }
    }
    Ok(())
}
fn validate_enrollment(layout: &Layout, value: &Enrollment) -> Result<()> {
    let genesis = &value.genesis;
    validate_ledger(layout, genesis)?;
    if value.schema_version != SCHEMA
        || value.root_absolute != layout.root
        || value.workspace_id != genesis.workspace_id
        || genesis.generation != 1
        || genesis.policy_revision != 1
        || genesis.counters != Counters::default()
        || genesis.active.is_some()
        || genesis.terminal_outbox.is_some()
    {
        bail!("下载计量启用标记身份无效");
    }
    Ok(())
}
fn verify_identity(enrollment: &Enrollment, ledger: &Ledger) -> Result<()> {
    if enrollment.workspace_id != ledger.workspace_id
        || enrollment.genesis.coverage_started_at_ms != ledger.coverage_started_at_ms
        || enrollment.genesis.coverage_prior_history != ledger.coverage_prior_history
    {
        bail!("下载启用标记与账本身份不一致");
    }
    Ok(())
}

/// 只识别初始化时是否有旧制品证据，不扫描/读取制品内容。
fn prior_coverage(layout: &Layout, current_operation: &str) -> Result<PriorCoverage> {
    for name in [
        "cache",
        "releases",
        "environments",
        "e",
        "tools",
        "python",
        "staging",
        "backups",
    ] {
        let base = layout.root.join(name);
        layout.guard_path(&base)?;
        if base.try_exists()? && fs::read_dir(&base)?.next().transpose()?.is_some() {
            return Ok(PriorCoverage::NotMeasured);
        }
    }
    let state = layout.root.join("state");
    layout.guard_path(&state)?;
    if state.try_exists()? {
        for entry in fs::read_dir(&state)? {
            let entry = entry?;
            layout.guard_path(&entry.path())?;
            // 当前操作Preparing记录可先存在；不据它推断有过下载。
            if entry.file_name() == "operations" && entry.file_type()?.is_dir() {
                for child in fs::read_dir(entry.path())? {
                    let child = child?;
                    layout.guard_path(&child.path())?;
                    if child.file_name().to_str()
                        != Some(format!("{current_operation}.json").as_str())
                    {
                        return Ok(PriorCoverage::NotMeasured);
                    }
                }
            } else {
                return Ok(PriorCoverage::NotMeasured);
            }
        }
    }
    Ok(PriorCoverage::NoPriorArtifactEvidence)
}

fn receipt_count(layout: &Layout, workspace_id: Option<&str>) -> Result<usize> {
    let directory = receipt_directory(layout)?;
    if !directory.try_exists()? {
        return Ok(0);
    }
    if !fs::symlink_metadata(&directory)?.is_dir() {
        bail!("下载receipt根不是普通目录");
    }
    let mut count = 0usize;
    for entry in fs::read_dir(&directory)? {
        let entry = entry?;
        let entry_path = entry.path();
        layout.guard_path(&entry_path)?;
        if entry_path.extension().is_some_and(|value| value == "tmp") {
            continue;
        }
        if !entry.file_type()?.is_file() || entry_path.extension().is_none_or(|v| v != "json") {
            bail!("下载receipt目录包含未知内容");
        }
        count = count.checked_add(1).context("receipt计数溢出")?;
        if count > MAX_RECEIPTS {
            bail!("下载receipt超过独立数量限额");
        }
        let bytes = read_bytes(layout, &entry_path)?.context("receipt读取时丢失")?;
        let record: OperationDownloadReceipt = decode(&bytes)?;
        if entry_path.file_stem().and_then(|v| v.to_str()) != Some(record.operation_id.as_str()) {
            bail!("下载receipt文件名与操作身份不符");
        }
        validate_receipt(&record, workspace_id.unwrap_or(&record.workspace_id))?;
    }
    Ok(count)
}

fn enroll(
    layout: &Layout,
    initial_policy: &DownloadPolicy,
    current_operation: &str,
) -> Result<(Ledger, Vec<u8>, Vec<u8>)> {
    let marker_path = enrollment_path(layout)?;
    let state_path = ledger_path(layout)?;
    let marker_bytes = read_bytes(layout, &marker_path)?;
    let ledger_bytes = read_bytes(layout, &state_path)?;
    match (marker_bytes, ledger_bytes) {
        (Some(marker_bytes), ledger_bytes) => {
            let mut enrollment: Enrollment = decode(&marker_bytes)?;
            validate_enrollment(layout, &enrollment)?;
            receipt_count(layout, Some(&enrollment.workspace_id))?;
            if enrollment.phase == EnrollmentPhase::Pending {
                // Pending启用阶段不允许任何请求，只可恢复完全相同的genesis。
                let bytes = match ledger_bytes {
                    Some(bytes) => {
                        let value: Ledger = decode(&bytes)?;
                        if value != enrollment.genesis {
                            bail!("未完成启用却已有非genesis账本，拒绝归零");
                        }
                        bytes
                    }
                    None => write(layout, &state_path, &enrollment.genesis)?,
                };
                enrollment.phase = EnrollmentPhase::Active;
                let marker = write(layout, &marker_path, &enrollment)?;
                return Ok((enrollment.genesis, bytes, marker));
            }
            let bytes = ledger_bytes.context("计量已启用但下载账本丢失，拒绝静默归零")?;
            let value: Ledger = decode(&bytes)?;
            validate_ledger(layout, &value)?;
            verify_identity(&enrollment, &value)?;
            Ok((value, bytes, marker_bytes))
        }
        (None, Some(_)) => bail!("下载账本缺少对应启用标记，保留账本并拒绝接管"),
        (None, None) => {
            if receipt_count(layout, None)? != 0 {
                bail!("存在历史receipt但计账身份丢失，拒绝重新启用");
            }
            validate_policy(initial_policy)?;
            let value = Ledger {
                schema_version: SCHEMA,
                measurement: MEASUREMENT.into(),
                workspace_id: identity(&layout.root)?,
                root_absolute: layout.root.clone(),
                generation: 1,
                coverage_started_at_ms: now_ms()?,
                coverage_prior_history: prior_coverage(layout, current_operation)?,
                policy_revision: 1,
                policy: initial_policy.clone(),
                counters: Counters::default(),
                active: None,
                terminal_outbox: None,
            };
            let mut enrollment = Enrollment {
                schema_version: SCHEMA,
                root_absolute: layout.root.clone(),
                workspace_id: value.workspace_id.clone(),
                phase: EnrollmentPhase::Pending,
                genesis: value.clone(),
            };
            write(layout, &marker_path, &enrollment)?;
            #[cfg(test)]
            fault_tests::checkpoint(layout, "enrollment_pending")?;
            let bytes = write(layout, &state_path, &value)?;
            #[cfg(test)]
            fault_tests::checkpoint(layout, "genesis_persisted")?;
            enrollment.phase = EnrollmentPhase::Active;
            let marker = write(layout, &marker_path, &enrollment)?;
            #[cfg(test)]
            fault_tests::checkpoint(layout, "enrollment_active")?;
            Ok((value, bytes, marker))
        }
    }
}

fn uncertain(ledger: &mut Ledger) -> Result<()> {
    let active = ledger.active.as_mut().context("没有活动下载操作")?;
    if let Some(attempt) = &mut active.attempt {
        let amount = attempt.reserved_body_bytes;
        add(&mut ledger.counters.uncertain_charge_bytes, amount)?;
        add(&mut active.counters.uncertain_charge_bytes, amount)?;
        attempt.reserved_body_bytes = 0;
    }
    Ok(())
}
fn make_terminal(
    ledger: &mut Ledger,
    outcome: DownloadOutcome,
) -> Result<OperationDownloadReceipt> {
    uncertain(ledger)?;
    let active = ledger.active.take().context("下载操作已结束")?;
    let receipt = OperationDownloadReceipt {
        schema_version: SCHEMA,
        measurement: MEASUREMENT.into(),
        workspace_id: ledger.workspace_id.clone(),
        operation_id: active.operation_id,
        retry_of: active.retry_of,
        outcome,
        accounting_complete: true,
        started_at_ms: active.started_at_ms,
        finished_at_ms: now_ms()?,
        policy_revision: active.policy_revision,
        limits: active.limits,
        counters: active.counters,
        start_generation: active.start_generation,
        end_generation: ledger
            .generation
            .checked_add(1)
            .context("下载generation耗尽")?,
        root_start_counters: active.root_start_counters,
        root_end_counters: ledger.counters.clone(),
    };
    ledger.terminal_outbox = Some(receipt.clone());
    Ok(receipt)
}

fn verify_committed(layout: &Layout, state: &State) -> Result<()> {
    if state.poisoned {
        bail!("下载计账写入结果不确定，停止读取；释放session后持租约重新核对");
    }
    if read_bytes(layout, &ledger_path(layout)?)?.as_deref()
        != Some(state.committed_bytes.as_slice())
        || read_bytes(layout, &enrollment_path(layout)?)?.as_deref()
            != Some(state.enrollment_bytes.as_slice())
    {
        bail!("下载计账或启用标记已改变，保留原状态并停止读取");
    }
    Ok(())
}
fn commit(layout: &Layout, state: &mut State, mut next: Ledger) -> Result<()> {
    verify_committed(layout, state)?;
    next.generation = state
        .ledger
        .generation
        .checked_add(1)
        .context("下载generation耗尽")?;
    validate_ledger(layout, &next)?;
    match write(layout, &ledger_path(layout)?, &next) {
        Ok(bytes) => {
            state.ledger = next;
            state.committed_bytes = bytes;
            Ok(())
        }
        Err(error) => {
            // model原子写失败或写后核对失败都停止本session；绝不推断旧写未发生。
            state.poisoned = true;
            Err(error)
        }
    }
}
fn flush_outbox(layout: &Layout, state: &mut State) -> Result<Option<OperationDownloadReceipt>> {
    verify_committed(layout, state)?;
    let Some(receipt) = state.ledger.terminal_outbox.clone() else {
        return Ok(None);
    };
    validate_receipt(&receipt, &state.ledger.workspace_id)?;
    let directory = receipt_directory(layout)?;
    let target = directory.join(format!("{}.json", receipt.operation_id));
    layout.guard_path(&target)?;
    match read_bytes(layout, &target)? {
        Some(bytes) => {
            let existing: OperationDownloadReceipt = decode(&bytes)?;
            if existing != receipt {
                bail!("下载receipt已存在但内容不同，拒绝覆盖");
            }
        }
        None => {
            if receipt_count(layout, Some(&state.ledger.workspace_id))? >= MAX_RECEIPTS {
                bail!("下载receipt数量已满，terminal outbox保留，需显式归档");
            }
            layout.ensure_dir(&directory)?;
            write(layout, &target, &receipt)?;
        }
    }
    #[cfg(test)]
    fault_tests::checkpoint(layout, "receipt_persisted")?;
    let mut next = state.ledger.clone();
    next.terminal_outbox = None;
    commit(layout, state, next)?;
    Ok(Some(receipt))
}
fn view(ledger: &Ledger) -> Result<DownloadBudgetView> {
    let reserved = reserve(ledger);
    let active = ledger.active.as_ref();
    Ok(DownloadBudgetView {
        measurement: MEASUREMENT,
        enabled: true,
        coverage_prior_history: Some(ledger.coverage_prior_history.clone()),
        policy_revision: Some(ledger.policy_revision),
        root_cap_body_bytes: ledger.policy.root_cap_body_bytes,
        counters: ledger.counters.clone(),
        reserved_body_bytes: reserved,
        remaining_body_bytes: root_remaining(
            ledger.policy.root_cap_body_bytes,
            &ledger.counters,
            reserved,
        )?,
        generation: Some(ledger.generation),
        active_operation: active.map(|a| a.operation_id.clone()),
        active_counters: active.map(|a| a.counters.clone()),
        operation_remaining_body_bytes: active
            .map(|a| remaining(a.limits.max_charged_body_bytes, &a.counters, reserved))
            .transpose()?,
        pending_reconciliation: ledger.active.is_some() || ledger.terminal_outbox.is_some(),
    })
}

impl DownloadBudget {
    /// 仅开始一次安装/修复/预取操作；同操作所有asset复用返回session。
    /// initial_policy只在从未启用计量时使用；已有policy不得由begin静默改写。
    /// 调用者必须将ctx保留到全部session任务drain和finish之后。
    pub fn begin(
        ctx: &WorkspaceMutation,
        operation: &str,
        retry_of: Option<&str>,
        initial_policy: DownloadPolicy,
        limits: OperationLimits,
    ) -> Result<Self> {
        operation_id(operation)?;
        if let Some(retry) = retry_of {
            operation_id(retry)?;
            if retry == operation {
                bail!("重试必须使用新的operation ID");
            }
        }
        validate_limits(&limits)?;
        let layout = ctx.layout().clone();
        let live = LiveSession::acquire(&layout.root)?;
        let (ledger, committed_bytes, enrollment_bytes) =
            enroll(&layout, &initial_policy, operation)?;
        let mut state = State {
            ledger,
            committed_bytes,
            enrollment_bytes,
            poisoned: false,
        };
        // 已拿到真实workspace lease且本进程无活动session，才认领旧中断。
        if state.ledger.active.is_some() {
            let mut next = state.ledger.clone();
            make_terminal(&mut next, DownloadOutcome::Interrupted)?;
            commit(&layout, &mut state, next)?;
        }
        flush_outbox(&layout, &mut state)?;
        let directory = receipt_directory(&layout)?;
        let target = directory.join(format!("{operation}.json"));
        if read_bytes(&layout, &target)?.is_some() {
            bail!("下载operation ID已有receipt，不能重用");
        }
        if receipt_count(&layout, Some(&state.ledger.workspace_id))? >= MAX_RECEIPTS {
            bail!("下载receipt已满，不能开始新操作");
        }
        let session_id = identity(&layout.root)?;
        let mut next = state.ledger.clone();
        next.active = Some(Active {
            operation_id: operation.into(),
            session_id: session_id.clone(),
            retry_of: retry_of.map(str::to_owned),
            started_at_ms: now_ms()?,
            start_generation: next.generation,
            root_start_counters: next.counters.clone(),
            policy_revision: next.policy_revision,
            limits,
            counters: Counters::default(),
            next_attempt: 1,
            attempt: None,
        });
        commit(&layout, &mut state, next)?;
        Ok(Self {
            layout,
            operation_id: operation.into(),
            session_id,
            started: Instant::now(),
            state: Arc::new(Mutex::new(state)),
            _live: live,
        })
    }

    fn owned<'a>(&self, ledger: &'a Ledger, enforce_deadline: bool) -> Result<&'a Active> {
        let active = ledger.active.as_ref().context("下载预算session已结束")?;
        if active.operation_id != self.operation_id || active.session_id != self.session_id {
            bail!("下载预算session身份变化");
        }
        if enforce_deadline
            && self.started.elapsed() >= Duration::from_millis(active.limits.max_elapsed_ms)
        {
            bail!("下载操作总时长预算已用尽");
        }
        Ok(active)
    }

    /// 网络等待期间由调用者轮询；超时仅拒绝继续工作，不妨碍finally结算/终结。
    pub fn check_deadline(&self) -> Result<()> {
        let state = self
            .state
            .lock()
            .map_err(|_| anyhow::anyhow!("下载计账锁异常"))?;
        self.owned(&state.ledger, true)?;
        Ok(())
    }

    fn credit_size(ledger: &Ledger, requested: usize) -> Result<u64> {
        if requested == 0 {
            bail!("正文读取预留必须大于0");
        }
        let active = ledger.active.as_ref().context("没有活动下载预算")?;
        if reserve(ledger) != 0 {
            bail!("已有未结正文预留，禁止同时读取");
        }
        let mut amount = (requested.min(READ_QUANTUM) as u64).min(remaining(
            active.limits.max_charged_body_bytes,
            &active.counters,
            0,
        )?);
        if let Some(root_available) =
            root_remaining(ledger.policy.root_cap_body_bytes, &ledger.counters, 0)?
        {
            amount = amount.min(root_available);
        }
        if amount == 0 {
            bail!("download_budget_exhausted: 下载正文额度已用尽");
        }
        Ok(amount)
    }

    /// 在send之前调用。首credit用于第一次有界正文read；不能先send再计次数。
    pub fn begin_attempt(
        &self,
        asset: &AssetIdentity,
        kind: AttemptKind,
        first_read_limit: usize,
    ) -> Result<(AttemptId, ReadCredit)> {
        validate_asset(asset)?;
        let mut state = self
            .state
            .lock()
            .map_err(|_| anyhow::anyhow!("下载计账锁异常"))?;
        let active = self.owned(&state.ledger, true)?;
        if active.attempt.is_some() {
            bail!("前一个下载attempt尚未结束");
        }
        if active.counters.requests >= u64::from(active.limits.max_requests)
            || kind == AttemptKind::Retry
                && active.counters.retries >= u64::from(active.limits.max_retries)
            || kind == AttemptKind::Redirect
                && active.counters.redirects >= u64::from(active.limits.max_redirects)
        {
            bail!("下载请求/重试/跳转次数额度已用尽");
        }
        let bytes = Self::credit_size(&state.ledger, first_read_limit)?;
        let mut next = state.ledger.clone();
        add(&mut next.counters.requests, 1)?;
        if kind == AttemptKind::Retry {
            add(&mut next.counters.retries, 1)?;
        }
        if kind == AttemptKind::Redirect {
            add(&mut next.counters.redirects, 1)?;
        }
        let active = next.active.as_mut().context("没有活动下载预算")?;
        add(&mut active.counters.requests, 1)?;
        if kind == AttemptKind::Retry {
            add(&mut active.counters.retries, 1)?;
        }
        if kind == AttemptKind::Redirect {
            add(&mut active.counters.redirects, 1)?;
        }
        let id = active.next_attempt;
        add(&mut active.next_attempt, 1)?;
        active.attempt = Some(Attempt {
            id,
            asset_sha256: asset.sha256.clone(),
            url_sha256: asset.url_sha256.clone(),
            authority: asset.authority.clone(),
            read_seq: 1,
            reserved_body_bytes: bytes,
        });
        commit(&self.layout, &mut state, next)?;
        Ok((
            AttemptId(id),
            ReadCredit {
                session_id: self.session_id.clone(),
                attempt: id,
                read_seq: 1,
                bytes,
            },
        ))
    }

    pub fn reserve_read(&self, attempt: AttemptId, requested: usize) -> Result<ReadCredit> {
        let mut state = self
            .state
            .lock()
            .map_err(|_| anyhow::anyhow!("下载计账锁异常"))?;
        self.owned(&state.ledger, true)?;
        let bytes = Self::credit_size(&state.ledger, requested)?;
        let mut next = state.ledger.clone();
        let current = next
            .active
            .as_mut()
            .and_then(|a| a.attempt.as_mut())
            .context("下载attempt不存在")?;
        if current.id != attempt.0 {
            bail!("下载attempt身份变化");
        }
        add(&mut current.read_seq, 1)?;
        current.reserved_body_bytes = bytes;
        let read_seq = current.read_seq;
        commit(&self.layout, &mut state, next)?;
        Ok(ReadCredit {
            session_id: self.session_id.clone(),
            attempt: attempt.0,
            read_seq,
            bytes,
        })
    }

    fn settle(&self, credit: ReadCredit, observed: Option<usize>) -> Result<()> {
        let mut state = self
            .state
            .lock()
            .map_err(|_| anyhow::anyhow!("下载计账锁异常"))?;
        self.owned(&state.ledger, false)?;
        let mut next = state.ledger.clone();
        let active = next.active.as_mut().context("下载操作不存在")?;
        let current = active.attempt.as_mut().context("下载attempt不存在")?;
        if credit.session_id != self.session_id
            || credit.attempt != current.id
            || credit.read_seq != current.read_seq
            || credit.bytes != current.reserved_body_bytes
            || credit.bytes == 0
        {
            bail!("正文credit身份失效或已结算");
        }
        match observed {
            Some(observed) => {
                if observed as u64 > credit.bytes {
                    bail!("正文交付超出预留，下载reader违反合同");
                }
                add(&mut next.counters.observed_body_bytes, observed as u64)?;
                add(&mut active.counters.observed_body_bytes, observed as u64)?;
            }
            None => {
                add(&mut next.counters.uncertain_charge_bytes, credit.bytes)?;
                add(&mut active.counters.uncertain_charge_bytes, credit.bytes)?;
            }
        }
        current.reserved_body_bytes = 0;
        commit(&self.layout, &mut state, next)
    }
    pub fn settle_read(&self, credit: ReadCredit, observed: usize) -> Result<()> {
        self.settle(credit, Some(observed))
    }
    /// read错误/cancel无法可靠确定交付数时按整个credit扣账；reason不存任意错误文本。
    pub fn uncertain_read(&self, credit: ReadCredit) -> Result<()> {
        self.settle(credit, None)
    }

    /// 调用前必须先结算首credit（包括无正文的send错误）。有遗留credit时保守扣账。
    /// outcome只描述本attempt，不推断缓存完整性或产品操作成功。
    pub fn finish_attempt(&self, attempt: AttemptId, _outcome: AttemptOutcome) -> Result<()> {
        let mut state = self
            .state
            .lock()
            .map_err(|_| anyhow::anyhow!("下载计账锁异常"))?;
        self.owned(&state.ledger, false)?;
        if state
            .ledger
            .active
            .as_ref()
            .and_then(|a| a.attempt.as_ref())
            .map(|a| a.id)
            != Some(attempt.0)
        {
            bail!("下载attempt身份失效");
        }
        let mut next = state.ledger.clone();
        uncertain(&mut next)?;
        next.active.as_mut().context("下载操作不存在")?.attempt = None;
        commit(&self.layout, &mut state, next)
    }

    /// 已验证本地cache/bundled/file-copy可成功而不消耗正文余额、次数或预留。
    pub fn record_cache_hit(&self) -> Result<()> {
        let mut state = self
            .state
            .lock()
            .map_err(|_| anyhow::anyhow!("下载计账锁异常"))?;
        self.owned(&state.ledger, true)?;
        if state
            .ledger
            .active
            .as_ref()
            .is_some_and(|a| a.attempt.is_some())
        {
            bail!("不能在远程attempt中记录cache命中");
        }
        let mut next = state.ledger.clone();
        add(&mut next.counters.cache_hits, 1)?;
        add(
            &mut next
                .active
                .as_mut()
                .context("下载操作不存在")?
                .counters
                .cache_hits,
            1,
        )?;
        commit(&self.layout, &mut state, next)
    }

    /// 必须已停止/await所有网络reader。即使cancel/期限触发，本收尾也不会被取消跳过。
    pub fn finish(&self, outcome: DownloadOutcome) -> Result<OperationDownloadReceipt> {
        let mut state = self
            .state
            .lock()
            .map_err(|_| anyhow::anyhow!("下载计账锁异常"))?;
        verify_committed(&self.layout, &state)?;
        if state.ledger.active.is_none() {
            if let Some(pending) = &state.ledger.terminal_outbox {
                if pending.operation_id != self.operation_id {
                    bail!("terminal outbox属于其它操作");
                }
                return flush_outbox(&self.layout, &mut state)?.context("terminal outbox缺失");
            }
            let target =
                receipt_directory(&self.layout)?.join(format!("{}.json", self.operation_id));
            let value: OperationDownloadReceipt =
                decode(&read_bytes(&self.layout, &target)?.context("下载receipt缺失")?)?;
            validate_receipt(&value, &state.ledger.workspace_id)?;
            if value.operation_id != self.operation_id {
                bail!("下载receipt文件名与操作ID不符");
            }
            return Ok(value);
        }
        self.owned(&state.ledger, false)?;
        let mut next = state.ledger.clone();
        let receipt = make_terminal(&mut next, outcome)?;
        commit(&self.layout, &mut state, next)?;
        flush_outbox(&self.layout, &mut state)?;
        Ok(receipt)
    }

    /// 当前session只读快照，不进行磁盘I/O或持久reconcile。
    #[cfg(test)]
    pub fn view(&self) -> Result<DownloadBudgetView> {
        let state = self
            .state
            .lock()
            .map_err(|_| anyhow::anyhow!("下载计账锁异常"))?;
        let mut value = view(&state.ledger)?;
        value.pending_reconciliation = state.poisoned || state.ledger.terminal_outbox.is_some();
        Ok(value)
    }
}

/// 只读磁盘view；不创建目录、不取得lease、不认领其它进程，也不把pending误报已结算。
pub fn snapshot(layout: &Layout) -> Result<DownloadBudgetView> {
    let marker = read_bytes(layout, &enrollment_path(layout)?)?;
    let ledger = read_bytes(layout, &ledger_path(layout)?)?;
    match (marker, ledger) {
        (None, None) => {
            if receipt_count(layout, None)? != 0 {
                bail!("存在历史receipt但计账身份丢失");
            }
            Ok(DownloadBudgetView {
                measurement: MEASUREMENT,
                enabled: false,
                coverage_prior_history: None,
                policy_revision: None,
                root_cap_body_bytes: None,
                counters: Counters::default(),
                reserved_body_bytes: 0,
                remaining_body_bytes: None,
                generation: None,
                active_operation: None,
                active_counters: None,
                operation_remaining_body_bytes: None,
                pending_reconciliation: false,
            })
        }
        (Some(marker), ledger) => {
            let enrollment: Enrollment = decode(&marker)?;
            validate_enrollment(layout, &enrollment)?;
            let value: Ledger = match ledger {
                Some(bytes) => decode(&bytes)?,
                None if enrollment.phase == EnrollmentPhase::Pending => enrollment.genesis.clone(),
                None => bail!("计量已启用但下载账本丢失"),
            };
            validate_ledger(layout, &value)?;
            verify_identity(&enrollment, &value)?;
            if enrollment.phase == EnrollmentPhase::Pending && value != enrollment.genesis {
                bail!("计量启用未完成但账本已变化");
            }
            let mut result = view(&value)?;
            if enrollment.phase == EnrollmentPhase::Pending {
                result.enabled = false;
                result.pending_reconciliation = true;
                result.remaining_body_bytes = None;
            }
            Ok(result)
        }
        (None, Some(_)) => bail!("下载账本缺少对应启用标记"),
    }
}

/// 首次保存可选累计上限，不建立operation、不发网络。正常下载会自动初始化计账。
/// 旧根无启用痕迹可安全启用；已active根须用set_policy+expected revision。
pub fn initialize_policy(
    ctx: &WorkspaceMutation,
    policy: DownloadPolicy,
) -> Result<DownloadBudgetView> {
    validate_policy(&policy)?;
    let layout = ctx.layout();
    let _live = LiveSession::acquire(&layout.root)?;
    if let Some(bytes) = read_bytes(layout, &enrollment_path(layout)?)? {
        let enrollment: Enrollment = decode(&bytes)?;
        validate_enrollment(layout, &enrollment)?;
        if enrollment.phase == EnrollmentPhase::Active {
            bail!("下载policy已存在，请使用expected revision显式更新");
        }
        if enrollment.genesis.policy != policy {
            bail!("未完成的下载计量启用policy不同，先按原配置恢复后再修改");
        }
    }
    let (ledger, _, _) = enroll(layout, &policy, "")?;
    view(&ledger)
}

/// 已启用根的显式policy修改；调用者已停止网络任务并持真实lease，不自动reconcile。
pub fn set_policy(
    ctx: &WorkspaceMutation,
    expected_revision: u64,
    policy: DownloadPolicy,
) -> Result<()> {
    validate_policy(&policy)?;
    let layout = ctx.layout();
    let _live = LiveSession::acquire(&layout.root)?;
    let marker = read_bytes(layout, &enrollment_path(layout)?)?.context("下载计量尚未启用")?;
    let enrollment: Enrollment = decode(&marker)?;
    validate_enrollment(layout, &enrollment)?;
    receipt_count(layout, Some(&enrollment.workspace_id))?;
    if enrollment.phase != EnrollmentPhase::Active {
        bail!("下载计量启用尚未完成");
    }
    let committed = read_bytes(layout, &ledger_path(layout)?)?.context("计量账本丢失")?;
    let ledger: Ledger = decode(&committed)?;
    validate_ledger(layout, &ledger)?;
    verify_identity(&enrollment, &ledger)?;
    if ledger.active.is_some() || ledger.terminal_outbox.is_some() {
        bail!("有未收尾下载操作，先完成计账恢复");
    }
    if ledger.policy_revision != expected_revision {
        bail!("下载policy revision已变化");
    }
    root_remaining(policy.root_cap_body_bytes, &ledger.counters, 0)?;
    let mut state = State {
        ledger,
        committed_bytes: committed,
        enrollment_bytes: marker,
        poisoned: false,
    };
    let mut next = state.ledger.clone();
    next.policy = policy;
    add(&mut next.policy_revision, 1)?;
    commit(layout, &mut state, next)
}

/// 显式结清中断下载。持真实工作区租约、确认本进程无活动session后才允许调用。
/// 未结预留保守扣账；只完成outbox投递，不建立新下载，也不修改policy。
pub fn reconcile(ctx: &WorkspaceMutation) -> Result<()> {
    let layout = ctx.layout();
    let _live = LiveSession::acquire(&layout.root)?;
    let current = snapshot_with_receipt(layout)?.budget;
    current.policy_revision.context("下载计量尚未启用")?;
    let (ledger, committed_bytes, enrollment_bytes) = enroll(
        layout,
        &DownloadPolicy {
            root_cap_body_bytes: current.root_cap_body_bytes,
        },
        "",
    )?;
    let mut state = State {
        ledger,
        committed_bytes,
        enrollment_bytes,
        poisoned: false,
    };
    if state.ledger.active.is_some() {
        let mut next = state.ledger.clone();
        make_terminal(&mut next, DownloadOutcome::Interrupted)?;
        commit(layout, &mut state, next)?;
    }
    flush_outbox(layout, &mut state)?;
    Ok(())
}

/// 独立receipt只读入口，不重算总账、不认领操作。
pub fn operation_receipt(
    layout: &Layout,
    operation: &str,
) -> Result<Option<OperationDownloadReceipt>> {
    operation_id(operation)?;
    let marker = read_bytes(layout, &enrollment_path(layout)?)?.context("下载计量未启用")?;
    let enrollment: Enrollment = decode(&marker)?;
    validate_enrollment(layout, &enrollment)?;
    let target = receipt_directory(layout)?.join(format!("{operation}.json"));
    let Some(bytes) = read_bytes(layout, &target)? else {
        return Ok(None);
    };
    let receipt: OperationDownloadReceipt = decode(&bytes)?;
    validate_receipt(&receipt, &enrollment.workspace_id)?;
    if receipt.operation_id != operation {
        bail!("下载receipt文件名与操作ID不符");
    }
    Ok(Some(receipt))
}

/// 环境页只读快照；不获取Engine长锁，不恢复或清算遗留操作。
#[derive(Serialize)]
pub struct BudgetSnapshot {
    pub budget: DownloadBudgetView,
    pub latest_receipt: Option<OperationDownloadReceipt>,
}

pub fn snapshot_with_receipt(layout: &Layout) -> Result<BudgetSnapshot> {
    let budget = snapshot(layout)?;
    let mut latest: Option<OperationDownloadReceipt> = None;
    // snapshot先验证身份缺失情形。所有独立receipt均有数量和单文件大小上限。
    if let Some(marker) = read_bytes(layout, &enrollment_path(layout)?)? {
        let enrollment: Enrollment = decode(&marker)?;
        validate_enrollment(layout, &enrollment)?;
        let directory = receipt_directory(layout)?;
        if directory.try_exists()? {
            let mut count = 0usize;
            for entry in fs::read_dir(directory)? {
                let entry = entry?;
                let path = entry.path();
                layout.guard_path(&path)?;
                if path.extension().is_some_and(|ext| ext == "tmp") {
                    continue;
                }
                if !entry.file_type()?.is_file() || path.extension().is_none_or(|ext| ext != "json")
                {
                    bail!("下载receipt目录包含未知内容");
                }
                count += 1;
                if count > MAX_RECEIPTS {
                    bail!("下载receipt超过独立数量限额");
                }
                let id = path
                    .file_stem()
                    .and_then(|id| id.to_str())
                    .context("下载receipt名称无效")?;
                let record = operation_receipt(layout, id)?.context("下载receipt读取时丢失")?;
                if latest.as_ref().is_none_or(|current| {
                    (record.finished_at_ms, &record.operation_id)
                        > (current.finished_at_ms, &current.operation_id)
                }) {
                    latest = Some(record);
                }
            }
        }
    }
    Ok(BudgetSnapshot {
        budget,
        latest_receipt: latest,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ledger() -> Ledger {
        let limits = OperationLimits {
            max_charged_body_bytes: 100_000,
            max_requests: 8,
            max_retries: 1,
            max_redirects: 2,
            max_elapsed_ms: 60_000,
        };
        Ledger {
            schema_version: SCHEMA,
            measurement: MEASUREMENT.into(),
            workspace_id: "a".repeat(64),
            root_absolute: PathBuf::from("test-root-unused"),
            generation: 2,
            coverage_started_at_ms: 1,
            coverage_prior_history: PriorCoverage::NotMeasured,
            policy_revision: 1,
            policy: DownloadPolicy {
                root_cap_body_bytes: Some(200_000),
            },
            counters: Counters::default(),
            active: Some(Active {
                operation_id: "download-test".into(),
                session_id: "b".repeat(64),
                retry_of: None,
                started_at_ms: 1,
                start_generation: 1,
                root_start_counters: Counters::default(),
                policy_revision: 1,
                limits,
                counters: Counters::default(),
                next_attempt: 1,
                attempt: None,
            }),
            terminal_outbox: None,
        }
    }

    #[test]
    fn observed_uncertain_and_outstanding_credit_share_one_cap() {
        let counters = Counters {
            observed_body_bytes: 30,
            uncertain_charge_bytes: 20,
            ..Counters::default()
        };
        assert_eq!(remaining(100, &counters, 40).unwrap(), 10);
        assert!(remaining(89, &counters, 40).is_err());
        assert!(Counters {
            observed_body_bytes: u64::MAX,
            uncertain_charge_bytes: 1,
            ..Counters::default()
        }
        .charged()
        .is_err());
    }

    #[test]
    fn read_credit_is_bounded_by_both_caps_and_quantum() {
        let mut value = ledger();
        assert_eq!(
            DownloadBudget::credit_size(&value, usize::MAX).unwrap(),
            READ_QUANTUM as u64
        );
        value.policy.root_cap_body_bytes = Some(17);
        assert_eq!(DownloadBudget::credit_size(&value, 30).unwrap(), 17);
        value.active.as_mut().unwrap().limits.max_charged_body_bytes = 9;
        assert_eq!(DownloadBudget::credit_size(&value, 30).unwrap(), 9);
        value.counters.observed_body_bytes = 17;
        assert!(DownloadBudget::credit_size(&value, 1).is_err());
        value.policy.root_cap_body_bytes = None;
        assert_eq!(DownloadBudget::credit_size(&value, 30).unwrap(), 9);
        value.active.as_mut().unwrap().counters.observed_body_bytes = 9;
        assert!(DownloadBudget::credit_size(&value, 1).is_err());
    }

    #[test]
    fn optional_root_cap_reads_legacy_numbers_and_requires_an_explicit_field() {
        let old: DownloadPolicy = serde_json::from_str(r#"{"root_cap_body_bytes":10}"#).unwrap();
        assert_eq!(old.root_cap_body_bytes, Some(10));
        let unlimited: DownloadPolicy =
            serde_json::from_str(r#"{"root_cap_body_bytes":null}"#).unwrap();
        assert_eq!(unlimited.root_cap_body_bytes, None);
        assert!(serde_json::from_str::<DownloadPolicy>("{}").is_err());
        assert!(validate_policy(&DownloadPolicy {
            root_cap_body_bytes: Some(0)
        })
        .is_err());
    }

    #[test]
    fn interrupted_terminal_charges_outstanding_once_and_preserves_root_history() {
        let mut value = ledger();
        value.counters.observed_body_bytes = 10;
        let active = value.active.as_mut().unwrap();
        active.counters.observed_body_bytes = 10;
        active.counters.requests = 1;
        value.counters.requests = 1;
        active.next_attempt = 2;
        active.attempt = Some(Attempt {
            id: 1,
            asset_sha256: "c".repeat(64),
            url_sha256: "d".repeat(64),
            authority: "example.test:443".into(),
            read_seq: 1,
            reserved_body_bytes: 23,
        });
        let receipt = make_terminal(&mut value, DownloadOutcome::Interrupted).unwrap();
        assert_eq!(receipt.counters.observed_body_bytes, 10);
        assert_eq!(receipt.counters.uncertain_charge_bytes, 23);
        assert_eq!(value.counters.charged().unwrap(), 33);
        assert!(value.active.is_none());
        assert!(make_terminal(&mut value, DownloadOutcome::Interrupted).is_err());
        assert_eq!(value.counters.charged().unwrap(), 33);
        validate_receipt(&receipt, &value.workspace_id).unwrap();
    }

    #[test]
    fn ledger_and_receipt_unknown_fields_or_counter_inconsistency_are_rejected() {
        let mut value = serde_json::to_value(ledger()).unwrap();
        value
            .as_object_mut()
            .unwrap()
            .insert("future_field".into(), serde_json::json!(1));
        assert!(serde_json::from_value::<Ledger>(value).is_err());
        let mut ledger = ledger();
        let mut receipt = make_terminal(&mut ledger, DownloadOutcome::Succeeded).unwrap();
        receipt.root_end_counters.observed_body_bytes = 1;
        assert!(validate_receipt(&receipt, &ledger.workspace_id).is_err());
    }

    #[test]
    fn invalid_asset_authorities_never_accept_credentials_or_control_characters() {
        for authority in [
            "user:secret@example.test",
            "https://example.test/",
            "example.test?token=secret",
            "example.test\u{1}:443",
        ] {
            assert!(validate_asset(&AssetIdentity {
                sha256: "a".repeat(64),
                url_sha256: "b".repeat(64),
                authority: authority.into()
            })
            .is_err());
        }
    }
}
