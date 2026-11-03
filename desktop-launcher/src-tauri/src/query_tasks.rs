//! 只读查询任务：纯内存受理、后台身份解析、最终身份单飞和有界订阅。
//! 不取得 WorkspaceMutation，不读写安装控制文件，不执行进程/磁盘 I/O。
//! 集成方必须每 <=100ms 调用 tick，并在真实 Job/reader 回收后提交 CleanupProof。
use crate::operations::CancelToken;
use serde::Serialize;
use serde_json::Value;
use std::{
    collections::{BTreeMap, VecDeque},
    fmt,
    io::{self, Write},
    sync::{Arc, Mutex, MutexGuard},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

const SCHEMA_VERSION: u32 = 1;
const MESSAGE_LIMIT: usize = 4 * 1024;
const PROGRESS_INTERVAL: Duration = Duration::from_millis(100);
const HEARTBEAT_INTERVAL: Duration = Duration::from_millis(900);

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub(crate) struct QueryError {
    pub code: String,
    pub message: String,
}
impl QueryError {
    pub(crate) fn new(code: &str, message: impl AsRef<str>) -> Self {
        let code = if !code.is_empty()
            && code.len() <= 96
            && code
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
        {
            code.to_owned()
        } else {
            "query_error".into()
        };
        Self {
            code,
            message: short_message(message.as_ref()),
        }
    }
}
impl fmt::Display for QueryError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}
impl std::error::Error for QueryError {}
type Result<T> = std::result::Result<T, QueryError>;

fn short_message(message: &str) -> String {
    let mut value = crate::network_policy::redact(message);
    if value.len() > MESSAGE_LIMIT {
        let mut limit = MESSAGE_LIMIT;
        while !value.is_char_boundary(limit) {
            limit -= 1;
        }
        value.truncate(limit);
    }
    value
}
fn unix_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_millis().min(u64::MAX as u128) as u64)
        .unwrap_or(0)
}
fn valid_digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}

/// 在 IPC 请求入口创建，传过队列/身份解析，不在 join 或 worker 启动时重置。
#[derive(Clone, Copy, Debug)]
pub(crate) struct QueryClock {
    started: Instant,
    deadline: Instant,
    started_at_ms: u64,
    deadline_at_ms: u64,
}
impl QueryClock {
    pub(crate) fn start(timeout: Duration) -> Result<Self> {
        let started = Instant::now();
        if timeout.is_zero() || timeout > Duration::from_secs(1800) {
            return Err(QueryError::new(
                "query_timeout_invalid",
                "检查期限必须在0至1800秒之间",
            ));
        }
        let deadline = started
            .checked_add(timeout)
            .ok_or_else(|| QueryError::new("query_timeout_invalid", "检查期限溢出"))?;
        let started_at_ms = unix_ms();
        Ok(Self {
            started,
            deadline,
            started_at_ms,
            deadline_at_ms: started_at_ms.saturating_add(timeout.as_millis() as u64),
        })
    }
    fn include_earlier(&mut self, other: Self) {
        if other.started < self.started {
            self.started = other.started;
            self.started_at_ms = other.started_at_ms;
        }
        if other.deadline < self.deadline {
            self.deadline = other.deadline;
            self.deadline_at_ms = other.deadline_at_ms;
        }
    }
}

#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub(crate) enum QueryAction {
    Capabilities,
    Recipe,
    InspectReadonly,
    PlanInstall,
    PlanRepair,
    #[serde(rename = "preview_gui_rebuild")]
    GuiRebuildPreview,
    #[serde(rename = "preview_legacy_environment_repair")]
    LegacyEnvironmentRepairPreview,
}
impl QueryAction {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Capabilities => "capabilities",
            Self::Recipe => "recipe",
            Self::InspectReadonly => "inspect_readonly",
            Self::PlanInstall => "plan_install",
            Self::PlanRepair => "plan_repair",
            Self::GuiRebuildPreview => "preview_gui_rebuild",
            Self::LegacyEnvironmentRepairPreview => "preview_legacy_environment_repair",
        }
    }
}
#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(rename_all = "snake_case")]
pub(crate) enum QueryScope {
    Full,
    FilesOnly,
    Plan,
}
/// root 是有界请求值；正式路径/marker/reparse 校验在后台身份解析器完成。
#[derive(Clone, Debug, Serialize, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) struct QueryTarget {
    pub root: String,
    pub release_id: String,
    pub engine_id: String,
    pub action: QueryAction,
    pub rebuild: bool,
    pub scope: QueryScope,
}
impl QueryTarget {
    fn validate(&self) -> Result<()> {
        if self.root.is_empty()
            || self.root.len() > 8192
            || self.release_id.is_empty()
            || self.release_id.len() > 160
            || !matches!(
                self.engine_id.as_str(),
                "kohya" | "anima-fast" | "ai-toolkit" | "diffsynth" | "gui"
            )
        {
            return Err(QueryError::new(
                "query_target_invalid",
                "检查目标不完整或超过长度限制",
            ));
        }
        let gui_action = matches!(
            self.action,
            QueryAction::GuiRebuildPreview | QueryAction::LegacyEnvironmentRepairPreview
        );
        if (self.engine_id == "gui") != gui_action
            || self.engine_id == "gui"
                && (self.scope != QueryScope::Plan
                    || self.rebuild != (self.action == QueryAction::GuiRebuildPreview))
        {
            return Err(QueryError::new(
                "query_target_invalid",
                "主程序预览目标与动作不匹配",
            ));
        }
        Ok(())
    }
    fn same_operation(&self, other: &Self) -> bool {
        // 两种 root 拼写可被后端解析为同一规范根，最终身份仍须完全匹配。
        self.release_id == other.release_id
            && self.engine_id == other.engine_id
            && self.action == other.action
            && self.rebuild == other.rebuild
            && self.scope == other.scope
    }
}
/// 只接受后端正式解析结果；绝不能由前端提交此结构直接授权扫描。
#[derive(Clone, Debug, Serialize, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) struct QueryIdentity {
    pub target: QueryTarget,
    /// 后端验证的根身份（例如规范路径+卷/目录身份+marker 摘要），防根被替换。
    pub workspace_fence: String,
    pub instance_id: Option<String>,
    pub generation: Option<u64>,
    pub state_sha256: Option<String>,
    pub receipt_sha256: Option<String>,
    pub binding_sha256: Option<String>,
    pub lock_sha256: String,
    pub recipe_sha256: String,
}
impl QueryIdentity {
    fn validate_for(&self, requested: &QueryTarget) -> Result<()> {
        self.target.validate()?;
        if !self.target.same_operation(requested)
            || self.workspace_fence.is_empty()
            || self.workspace_fence.len() > 1024
            || self
                .instance_id
                .as_ref()
                .is_some_and(|id| id.is_empty() || id.len() > 96)
            || self.generation == Some(0)
            || self.instance_id.is_some() != self.generation.is_some()
            || !valid_digest(&self.lock_sha256)
            || !valid_digest(&self.recipe_sha256)
            || [
                &self.state_sha256,
                &self.receipt_sha256,
                &self.binding_sha256,
            ]
            .iter()
            .any(|value| value.as_ref().is_some_and(|sha| !valid_digest(sha)))
        {
            return Err(QueryError::new(
                "query_identity_invalid",
                "后台检查身份与请求不符",
            ));
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum QueryStatus {
    Resolving,
    Queued,
    Running,
    Cancelling,
    Succeeded,
    Cancelled,
    TimedOut,
    Failed,
    Interrupted,
    Stale,
}
impl QueryStatus {
    pub(crate) fn is_terminal(self) -> bool {
        matches!(
            self,
            Self::Succeeded
                | Self::Cancelled
                | Self::TimedOut
                | Self::Failed
                | Self::Interrupted
                | Self::Stale
        )
    }
}
#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum QueryStage {
    Identity,
    Queued,
    Python,
    Tools,
    Worker,
    Receipt,
    Environment,
    Source,
    ExtraFiles,
    Reaping,
    Complete,
}
#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum QueryValidity {
    Unresolved,
    Current,
    Stale,
}
#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum StopReason {
    UserCancel,
    Deadline,
    Shutdown,
}
#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq)]
pub(crate) struct QueryProgress {
    pub files: Option<u64>,
    pub bytes: Option<u64>,
    pub total_files: Option<u64>,
    pub total_bytes: Option<u64>,
    pub message: String,
}
#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub(crate) struct WorkerIdentity {
    pub pid: u32,
    pub creation_time: u64,
    pub job_id: String,
}
impl WorkerIdentity {
    fn validate(&self) -> Result<()> {
        if self.pid == 0
            || self.creation_time == 0
            || self.job_id.is_empty()
            || self.job_id.len() > 256
        {
            return Err(QueryError::new(
                "query_worker_identity_invalid",
                "受管worker身份不完整",
            ));
        }
        Ok(())
    }
}
/// 本任务拥有的标准输入写入器/两个输出reader必须都实际停止；不可只drop JoinHandle。
#[derive(Debug)]
pub(crate) struct ReaderCleanup {
    pub stdin_closed: bool,
    pub stdout_reader_joined: bool,
    pub stderr_reader_joined: bool,
}
/// 只能由可信后端回收器创建；不反序列化、不作为 IPC 入参。
/// 数字/布尔值须来自持有真实Child/Job/reader的执行器；本模块不代替OS回收验证。
#[derive(Debug)]
pub(crate) struct CleanupProof {
    worker: Option<WorkerIdentity>,
}
impl CleanupProof {
    pub(crate) fn no_worker_started() -> Self {
        Self { worker: None }
    }
    pub(crate) fn reaped(
        worker: WorkerIdentity,
        child_waited: bool,
        remaining_job_processes: u32,
        readers: ReaderCleanup,
    ) -> Result<Self> {
        worker.validate()?;
        if !child_waited || remaining_job_processes != 0 {
            return Err(QueryError::new(
                "query_cleanup_pending",
                "自有Child或Job尚未回收，不能结束检查",
            ));
        }
        if !readers.stdin_closed || !readers.stdout_reader_joined || !readers.stderr_reader_joined {
            return Err(QueryError::new(
                "query_readers_pending",
                "标准输入或输出reader尚未回收，不能结束检查",
            ));
        }
        Ok(Self {
            worker: Some(worker),
        })
    }
}

#[derive(Clone, Debug, Serialize)]
pub(crate) struct QuerySnapshot {
    pub schema_version: u32,
    /// 用户最初收到的稳定 ID，可为 canonical 的有界别名。
    pub task_id: String,
    pub canonical_task_id: String,
    pub target: QueryTarget,
    pub identity: Option<QueryIdentity>,
    pub status: QueryStatus,
    pub stage: QueryStage,
    pub validity: QueryValidity,
    pub cancel_requested: bool,
    pub stop_reason: Option<StopReason>,
    pub event_seq: u64,
    pub started_at_ms: u64,
    pub updated_at_ms: u64,
    pub deadline_at_ms: u64,
    pub progress: QueryProgress,
    pub worker: Option<WorkerIdentity>,
    pub worker_reaped: bool,
    pub readers_reaped: bool,
    pub result_available: bool,
    pub error: Option<QueryError>,
    pub subscriber_count: usize,
}
#[derive(Clone, Copy, Debug, Serialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum QueryEventKind {
    Accepted,
    Resolved,
    Joined,
    Progress,
    Heartbeat,
    CancelRequested,
    CleanupPending,
    Terminal,
}
#[derive(Clone, Debug, Serialize)]
pub(crate) struct QueryEvent {
    pub seq: u64,
    pub kind: QueryEventKind,
    pub status: QueryStatus,
    pub stage: QueryStage,
    pub stop_reason: Option<StopReason>,
    pub progress: QueryProgress,
}
#[derive(Clone, Debug, Serialize)]
pub(crate) struct QueryAcceptance {
    pub schema_version: u32,
    pub task_id: String,
    pub canonical_task_id: String,
    pub subscription_id: String,
    pub shared: bool,
    pub snapshot: QuerySnapshot,
}
#[derive(Debug, Serialize)]
pub(crate) struct QueryEvents {
    pub snapshot: QuerySnapshot,
    pub cursor_reset: bool,
    pub events: Vec<QueryEvent>,
}
#[derive(Debug, Serialize)]
pub(crate) struct QueryResult {
    pub snapshot: QuerySnapshot,
    pub result: Option<Value>,
}
#[derive(Clone, Copy, Debug, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum QueryCancelReceipt {
    Accepted,
    AlreadyRequested,
    AlreadyTerminal,
}

#[derive(Clone, Debug)]
pub(crate) struct QueryLimits {
    /// 未解析身份的短后台请求；不占已解析执行槽，否则重复请求会被容量误拒。
    pub max_resolving: usize,
    /// 已解析的不同最终身份；重复最终身份在这里合并，不额外占槽。
    pub max_active: usize,
    /// 完整准备/扫描/worker的执行槽。排队及身份解析都计入入口总deadline。
    pub max_running: usize,
    pub max_terminal: usize,
    pub max_aliases: usize,
    pub max_events: usize,
    pub max_subscribers_per_task: usize,
    pub max_subscribers: usize,
    pub max_result_bytes: usize,
    pub max_total_result_bytes: usize,
    pub subscription_ttl: Duration,
}
impl Default for QueryLimits {
    fn default() -> Self {
        Self {
            max_resolving: 32,
            max_active: 4,
            max_running: 1,
            max_terminal: 64,
            max_aliases: 128,
            max_events: 128,
            max_subscribers_per_task: 32,
            max_subscribers: 256,
            max_result_bytes: 4 * 1024 * 1024,
            max_total_result_bytes: 16 * 1024 * 1024,
            subscription_ttl: Duration::from_secs(300),
        }
    }
}
impl QueryLimits {
    fn validate(&self) -> Result<()> {
        if !(1..=64).contains(&self.max_resolving)
            || !(1..=32).contains(&self.max_active)
            || self.max_running == 0
            || self.max_running > self.max_active
            || !(1..=256).contains(&self.max_terminal)
            || !(1..=512).contains(&self.max_aliases)
            || !(1..=256).contains(&self.max_events)
            || !(1..=64).contains(&self.max_subscribers_per_task)
            || !(1..=512).contains(&self.max_subscribers)
            || self.max_result_bytes == 0
            || self.max_result_bytes > 4 * 1024 * 1024
            || self.max_total_result_bytes < self.max_result_bytes
            || self.max_total_result_bytes > 16 * 1024 * 1024
            || self.subscription_ttl.is_zero()
        {
            return Err(QueryError::new(
                "query_limits_invalid",
                "检查任务资源边界无效",
            ));
        }
        Ok(())
    }
}

#[derive(Debug)]
struct Task {
    requested: QueryTarget,
    identity: Option<QueryIdentity>,
    clock: QueryClock,
    cancel: CancelToken,
    status: QueryStatus,
    stage: QueryStage,
    validity: QueryValidity,
    stop_reason: Option<StopReason>,
    progress: QueryProgress,
    events: VecDeque<QueryEvent>,
    seq: u64,
    updated_at_ms: u64,
    last_event: Instant,
    worker: Option<WorkerIdentity>,
    worker_reaped: bool,
    readers_reaped: bool,
    execution_claimed: bool,
    // 保存有界JSON字节而非Value树；读取时锁内仅Arc clone，锁外反序列化。
    result: Option<Arc<[u8]>>,
    result_bytes: usize,
    error: Option<QueryError>,
    finished_order: Option<u64>,
}
impl Task {
    fn record(&mut self, kind: QueryEventKind, now: Instant, limit: usize) {
        // 不受外部输入控制的有界事件序号；饱和将保持单调而不溢出。
        self.seq = self.seq.saturating_add(1);
        self.updated_at_ms = unix_ms();
        self.last_event = now;
        self.events.push_back(QueryEvent {
            seq: self.seq,
            kind,
            status: self.status,
            stage: self.stage,
            stop_reason: self.stop_reason,
            progress: self.progress.clone(),
        });
        while self.events.len() > limit {
            self.events.pop_front();
        }
    }
    fn request_stop(&mut self, reason: StopReason, now: Instant, limit: usize) {
        if self.status.is_terminal() || self.stop_reason.is_some() {
            return;
        }
        self.stop_reason = Some(reason);
        self.status = QueryStatus::Cancelling;
        // 需要 operations::CancelToken::request 的 pub(crate) 最小可见性调整。
        self.cancel.request();
        self.record(QueryEventKind::CancelRequested, now, limit);
    }
}
#[derive(Debug)]
struct Alias {
    canonical: String,
    requested: QueryTarget,
    order: u64,
}
#[derive(Debug)]
struct Subscription {
    requested_id: String,
    canonical_id: String,
    touched: Instant,
}
#[derive(Debug)]
struct State {
    nonce: String,
    sequence: u64,
    closing: bool,
    tasks: BTreeMap<String, Task>,
    aliases: BTreeMap<String, Alias>,
    by_identity: BTreeMap<QueryIdentity, String>,
    subscriptions: BTreeMap<String, Subscription>,
}
impl State {
    fn allocate(&mut self, prefix: &str) -> Result<(String, u64)> {
        self.sequence = self
            .sequence
            .checked_add(1)
            .ok_or_else(|| QueryError::new("query_id_exhausted", "检查任务ID序号耗尽"))?;
        Ok((
            format!("{prefix}-{}-{:016x}", self.nonce, self.sequence),
            self.sequence,
        ))
    }
    fn canonical(&self, id: &str) -> Result<&str> {
        if self.tasks.contains_key(id) {
            return Ok(self.tasks.get_key_value(id).expect("key checked").0);
        }
        self.aliases
            .get(id)
            .map(|alias| alias.canonical.as_str())
            .ok_or_else(|| QueryError::new("query_expired", "检查任务不存在或已从有界历史中移除"))
    }
    fn count_subscribers(&self, canonical: &str) -> usize {
        self.subscriptions
            .values()
            .filter(|s| s.canonical_id == canonical)
            .count()
    }
    fn snapshot(&self, id: &str) -> Result<QuerySnapshot> {
        let canonical = self.canonical(id)?;
        let task = self
            .tasks
            .get(canonical)
            .ok_or_else(|| QueryError::new("query_expired", "检查任务别名已过期"))?;
        let requested = self
            .aliases
            .get(id)
            .map(|a| &a.requested)
            .unwrap_or(&task.requested);
        Ok(QuerySnapshot {
            schema_version: SCHEMA_VERSION,
            task_id: id.into(),
            canonical_task_id: canonical.into(),
            target: requested.clone(),
            identity: task.identity.clone(),
            status: task.status,
            stage: task.stage,
            validity: task.validity,
            cancel_requested: task.stop_reason.is_some(),
            stop_reason: task.stop_reason,
            event_seq: task.seq,
            started_at_ms: task.clock.started_at_ms,
            updated_at_ms: task.updated_at_ms,
            deadline_at_ms: task.clock.deadline_at_ms,
            progress: task.progress.clone(),
            worker: task.worker.clone(),
            worker_reaped: task.worker_reaped,
            readers_reaped: task.readers_reaped,
            result_available: task.status == QueryStatus::Succeeded
                && task.validity == QueryValidity::Current
                && task.result.is_some(),
            error: task.error.clone(),
            subscriber_count: self.count_subscribers(canonical),
        })
    }
    fn drop_alias(&mut self, id: &str) {
        self.aliases.remove(id);
        self.subscriptions.retain(|_, s| s.requested_id != id);
    }
    fn drop_task(&mut self, id: &str) {
        self.tasks.remove(id);
        self.by_identity.retain(|_, value| value != id);
        self.aliases.retain(|_, value| value.canonical != id);
        self.subscriptions.retain(|_, s| s.canonical_id != id);
    }
    fn oldest_terminal(&self, except: Option<&str>) -> Option<String> {
        self.tasks
            .iter()
            .filter(|(id, task)| task.status.is_terminal() && except != Some(id.as_str()))
            .min_by_key(|(_, task)| task.finished_order.unwrap_or(0))
            .map(|(id, _)| id.clone())
    }
    fn oldest_terminal_alias(&self) -> Option<String> {
        self.aliases
            .iter()
            .filter(|(_, alias)| {
                self.tasks
                    .get(&alias.canonical)
                    .is_none_or(|task| task.status.is_terminal())
            })
            .min_by_key(|(_, alias)| alias.order)
            .map(|(id, _)| id.clone())
    }
    fn reserve_alias_slot(&mut self, limits: &QueryLimits) -> Result<()> {
        while self.aliases.len() >= limits.max_aliases {
            if let Some(id) = self.oldest_terminal_alias() {
                self.drop_alias(&id);
            } else {
                return Err(QueryError::new(
                    "query_alias_capacity",
                    "在途共享检查ID已达上限，请复用已有任务ID",
                ));
            }
        }
        Ok(())
    }
    fn maintain(&mut self, limits: &QueryLimits, now: Instant) {
        // 订阅租期结束只退订，不请求取消；历史驱逐不被订阅永久钉住。
        self.subscriptions
            .retain(|_, s| now.saturating_duration_since(s.touched) < limits.subscription_ttl);
        while self
            .tasks
            .values()
            .filter(|task| task.status.is_terminal())
            .count()
            > limits.max_terminal
        {
            if let Some(id) = self.oldest_terminal(None) {
                self.drop_task(&id);
            } else {
                break;
            }
        }
        while self.aliases.len() > limits.max_aliases {
            // 活动期稳定ID不能因新加入或订阅过期而消失；仅终态别名可淘汰。
            let id = self.oldest_terminal_alias();
            if let Some(id) = id {
                self.drop_alias(&id);
            } else {
                break;
            }
        }
    }
}

#[derive(Debug)]
struct Shared {
    limits: QueryLimits,
    state: Mutex<State>,
}
#[derive(Clone, Debug)]
pub(crate) struct QueryTaskManager(Arc<Shared>);
impl Default for QueryTaskManager {
    fn default() -> Self {
        Self::new(QueryLimits::default()).expect("default query limits are valid")
    }
}
impl QueryTaskManager {
    pub(crate) fn new(limits: QueryLimits) -> Result<Self> {
        limits.validate()?;
        let nonce = format!(
            "{:x}-{:x}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        );
        Ok(Self(Arc::new(Shared {
            limits,
            state: Mutex::new(State {
                nonce,
                sequence: 0,
                closing: false,
                tasks: BTreeMap::new(),
                aliases: BTreeMap::new(),
                by_identity: BTreeMap::new(),
                subscriptions: BTreeMap::new(),
            }),
        })))
    }
    fn state(&self) -> Result<MutexGuard<'_, State>> {
        self.0
            .state
            .lock()
            .map_err(|_| QueryError::new("query_state_poisoned", "检查任务状态锁异常"))
    }
    /// 无磁盘I/O、身份扫描或等待线程。调用者立即返回 acceptance，再后台 resolve。
    pub(crate) fn begin(&self, target: QueryTarget, clock: QueryClock) -> Result<QueryAdmission> {
        target.validate()?;
        let mut state = self.state()?;
        let now = Instant::now();
        state.maintain(&self.0.limits, now);
        if state.closing {
            return Err(QueryError::new(
                "query_shutting_down",
                "启动器正在退出，不再接受检查",
            ));
        }
        if state
            .tasks
            .values()
            .filter(|task| !task.status.is_terminal() && task.identity.is_none())
            .count()
            >= self.0.limits.max_resolving
        {
            return Err(QueryError::new(
                "query_resolver_capacity",
                "检查身份解析已达上限，请复用已有任务或稍后重试",
            ));
        }
        if state.subscriptions.len() >= self.0.limits.max_subscribers {
            return Err(QueryError::new(
                "query_subscriber_capacity",
                "检查订阅已达上限",
            ));
        }
        let (task_id, _) = state.allocate("query")?;
        let (subscription_id, _) = state.allocate("subscription")?;
        let cancel = CancelToken::new();
        let mut task = Task {
            requested: target,
            identity: None,
            clock,
            cancel: cancel.clone(),
            status: QueryStatus::Resolving,
            stage: QueryStage::Identity,
            validity: QueryValidity::Unresolved,
            stop_reason: None,
            progress: QueryProgress::default(),
            events: VecDeque::new(),
            seq: 0,
            updated_at_ms: unix_ms(),
            last_event: now,
            worker: None,
            worker_reaped: false,
            readers_reaped: false,
            execution_claimed: false,
            result: None,
            result_bytes: 0,
            error: None,
            finished_order: None,
        };
        task.record(QueryEventKind::Accepted, now, self.0.limits.max_events);
        if now >= clock.deadline {
            task.request_stop(StopReason::Deadline, now, self.0.limits.max_events);
        }
        state.tasks.insert(task_id.clone(), task);
        state.subscriptions.insert(
            subscription_id.clone(),
            Subscription {
                requested_id: task_id.clone(),
                canonical_id: task_id.clone(),
                touched: now,
            },
        );
        let acceptance = QueryAcceptance {
            schema_version: SCHEMA_VERSION,
            task_id: task_id.clone(),
            canonical_task_id: task_id.clone(),
            subscription_id,
            shared: false,
            snapshot: state.snapshot(&task_id)?,
        };
        Ok(QueryAdmission {
            acceptance,
            handle: QueryHandle {
                observer: QueryObserver {
                    manager: self.clone(),
                    task_id,
                    cancel,
                },
                role: Role::Resolver,
            },
        })
    }
    pub(crate) fn snapshot(&self, task_id: &str) -> Result<QuerySnapshot> {
        self.state()?.snapshot(task_id)
    }
    pub(crate) fn join(&self, task_id: &str) -> Result<QueryAcceptance> {
        let now = Instant::now();
        let mut state = self.state()?;
        state.maintain(&self.0.limits, now);
        if state.closing {
            return Err(QueryError::new(
                "query_shutting_down",
                "启动器正在退出，不再接受订阅",
            ));
        }
        let canonical = state.canonical(task_id)?.to_owned();
        if state.subscriptions.len() >= self.0.limits.max_subscribers
            || state.count_subscribers(&canonical) >= self.0.limits.max_subscribers_per_task
        {
            return Err(QueryError::new(
                "query_subscriber_capacity",
                "该检查订阅已达上限",
            ));
        }
        let (subscription_id, _) = state.allocate("subscription")?;
        state.subscriptions.insert(
            subscription_id.clone(),
            Subscription {
                requested_id: task_id.into(),
                canonical_id: canonical.clone(),
                touched: now,
            },
        );
        Ok(QueryAcceptance {
            schema_version: SCHEMA_VERSION,
            task_id: task_id.into(),
            canonical_task_id: canonical,
            subscription_id,
            shared: true,
            snapshot: state.snapshot(task_id)?,
        })
    }
    pub(crate) fn touch_subscription(&self, task_id: &str, subscription_id: &str) -> Result<()> {
        let mut state = self.state()?;
        let canonical = state.canonical(task_id)?.to_owned();
        let subscription = state
            .subscriptions
            .get_mut(subscription_id)
            .ok_or_else(|| {
                QueryError::new("query_subscription_expired", "检查订阅已过期，请重新加入")
            })?;
        if subscription.canonical_id != canonical {
            return Err(QueryError::new(
                "query_subscription_mismatch",
                "订阅不属于此检查",
            ));
        }
        subscription.touched = Instant::now();
        Ok(())
    }
    /// 重复 leave 幂等；退最后订阅也不触发取消。
    pub(crate) fn leave(&self, task_id: &str, subscription_id: &str) -> Result<bool> {
        let mut state = self.state()?;
        let canonical = state.canonical(task_id)?.to_owned();
        if let Some(subscription) = state.subscriptions.get(subscription_id) {
            if subscription.canonical_id != canonical {
                return Err(QueryError::new(
                    "query_subscription_mismatch",
                    "订阅不属于此检查",
                ));
            }
        }
        Ok(state.subscriptions.remove(subscription_id).is_some())
    }
    pub(crate) fn cancel(&self, task_id: &str) -> Result<QueryCancelReceipt> {
        let now = Instant::now();
        let mut state = self.state()?;
        let canonical = state.canonical(task_id)?.to_owned();
        let task = state.tasks.get_mut(&canonical).expect("canonical task");
        if task.status.is_terminal() {
            return Ok(QueryCancelReceipt::AlreadyTerminal);
        }
        if task.stop_reason.is_some() {
            return Ok(QueryCancelReceipt::AlreadyRequested);
        }
        if now >= task.clock.deadline {
            task.request_stop(StopReason::Deadline, now, self.0.limits.max_events);
            return Ok(QueryCancelReceipt::AlreadyRequested);
        }
        task.request_stop(StopReason::UserCancel, now, self.0.limits.max_events);
        Ok(QueryCancelReceipt::Accepted)
    }
    pub(crate) fn events_since(&self, task_id: &str, after_seq: u64) -> Result<QueryEvents> {
        let state = self.state()?;
        let canonical = state.canonical(task_id)?;
        let task = state.tasks.get(canonical).expect("canonical task");
        let reset = after_seq > task.seq
            || task
                .events
                .front()
                .is_some_and(|event| after_seq < event.seq.saturating_sub(1));
        Ok(QueryEvents {
            snapshot: state.snapshot(task_id)?,
            cursor_reset: reset,
            events: if reset {
                vec![]
            } else {
                task.events
                    .iter()
                    .filter(|event| event.seq > after_seq)
                    .cloned()
                    .collect()
            },
        })
    }
    /// 读取不延长deadline；stale/取消/失败均无可应用结果。
    pub(crate) fn result(&self, task_id: &str) -> Result<QueryResult> {
        let (snapshot, encoded) = {
            let state = self.state()?;
            let snapshot = state.snapshot(task_id)?;
            let task = state
                .tasks
                .get(&snapshot.canonical_task_id)
                .expect("canonical task");
            let encoded = if snapshot.result_available {
                task.result.clone()
            } else {
                None
            };
            (snapshot, encoded)
        };
        let result = encoded
            .map(|bytes| {
                serde_json::from_slice(bytes.as_ref())
                    .map_err(|_| QueryError::new("query_result_corrupt", "检查结果编码异常"))
            })
            .transpose()?;
        Ok(QueryResult { result, snapshot })
    }
    /// 由Runtime唯一watchdog每<=100ms调用；只请求取消/发布心跳，绝不伪造回收终态。
    pub(crate) fn tick(&self) -> Result<()> {
        self.tick_at(Instant::now())
    }
    fn tick_at(&self, now: Instant) -> Result<()> {
        let mut state = self.state()?;
        for task in state
            .tasks
            .values_mut()
            .filter(|task| !task.status.is_terminal())
        {
            if now >= task.clock.deadline {
                task.request_stop(StopReason::Deadline, now, self.0.limits.max_events);
            }
            if now.saturating_duration_since(task.last_event) >= HEARTBEAT_INTERVAL {
                task.record(QueryEventKind::Heartbeat, now, self.0.limits.max_events);
            }
        }
        state.maintain(&self.0.limits, now);
        Ok(())
    }
    pub(crate) fn request_shutdown(&self) -> Result<Vec<String>> {
        let mut state = self.state()?;
        state.closing = true;
        let now = Instant::now();
        let mut active = Vec::new();
        for (id, task) in &mut state.tasks {
            if !task.status.is_terminal() {
                task.request_stop(StopReason::Shutdown, now, self.0.limits.max_events);
                active.push(id.clone());
            }
        }
        Ok(active)
    }
    pub(crate) fn active_count(&self) -> Result<usize> {
        Ok(self
            .state()?
            .tasks
            .values()
            .filter(|task| !task.status.is_terminal())
            .count())
    }
}

#[derive(Debug)]
pub(crate) struct QueryAdmission {
    pub acceptance: QueryAcceptance,
    pub handle: QueryHandle,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Role {
    Resolver,
    Executor,
    Joined,
}
/// 可克隆进度/取消观察器没有finish/attach权限。唯一执行句柄不Clone。
#[derive(Clone, Debug)]
pub(crate) struct QueryObserver {
    manager: QueryTaskManager,
    task_id: String,
    cancel: CancelToken,
}
impl QueryObserver {
    pub(crate) fn cancel_token(&self) -> CancelToken {
        self.cancel.clone()
    }
    pub(crate) fn deadline(&self) -> Result<Instant> {
        let state = self.manager.state()?;
        state
            .tasks
            .get(&self.task_id)
            .map(|task| task.clock.deadline)
            .ok_or_else(|| {
                QueryError::new("query_not_executor", "此身份已加入共享任务，没有执行权限")
            })
    }
    pub(crate) fn check(&self) -> Result<()> {
        let mut state = self.manager.state()?;
        let task = state
            .tasks
            .get_mut(&self.task_id)
            .ok_or_else(|| QueryError::new("query_not_executor", "此身份没有执行权限"))?;
        let now = Instant::now();
        if !task.status.is_terminal() && now >= task.clock.deadline {
            task.request_stop(StopReason::Deadline, now, self.manager.0.limits.max_events);
        }
        if let Some(reason) = task.stop_reason {
            return Err(stop_error(reason));
        }
        if task.status.is_terminal() {
            return Err(QueryError::new("query_already_terminal", "检查已结束"));
        }
        Ok(())
    }
    pub(crate) fn progress(&self, stage: QueryStage, mut progress: QueryProgress) -> Result<()> {
        if stage == QueryStage::Complete {
            return Err(QueryError::new(
                "query_stage_invalid",
                "只有完成回收后才可发布检查终态",
            ));
        }
        progress.message = short_message(&progress.message);
        let mut state = self.manager.state()?;
        let now = Instant::now();
        let task = state
            .tasks
            .get_mut(&self.task_id)
            .ok_or_else(|| QueryError::new("query_not_executor", "此身份没有执行权限"))?;
        if task.status.is_terminal() {
            return Err(QueryError::new("query_already_terminal", "检查已结束"));
        }
        let stage_changed = stage != task.stage;
        task.stage = stage;
        task.progress = progress;
        if task.stop_reason.is_none() && task.identity.is_some() {
            task.status = if task.execution_claimed {
                QueryStatus::Running
            } else {
                QueryStatus::Queued
            };
        }
        if stage_changed || now.saturating_duration_since(task.last_event) >= PROGRESS_INTERVAL {
            task.record(
                QueryEventKind::Progress,
                now,
                self.manager.0.limits.max_events,
            );
        }
        Ok(())
    }
}
fn stop_error(reason: StopReason) -> QueryError {
    match reason {
        StopReason::UserCancel => {
            QueryError::new("query_cancelled", "已接受取消，等待自有工作收尾")
        }
        StopReason::Deadline => {
            QueryError::new("query_timed_out", "检查已到总期限，等待自有工作收尾")
        }
        StopReason::Shutdown => {
            QueryError::new("query_interrupted", "启动器退出，等待自有工作收尾")
        }
    }
}
#[derive(Debug)]
pub(crate) struct QueryHandle {
    observer: QueryObserver,
    role: Role,
}
#[derive(Debug)]
pub(crate) enum QueryResolution {
    /// 句柄留在调用者；取得执行槽后才允许完整准备/扫描/启动worker。
    Execute,
    /// 原ID保持为别名；解析执行者到此结束，绝不再启动第二worker。
    Joined(Box<QuerySnapshot>),
    /// 解析前已接受取消/deadline/shutdown；仅回收自身准备资源后finish。
    Stopped,
}
impl QueryHandle {
    pub(crate) fn task_id(&self) -> &str {
        &self.observer.task_id
    }
    pub(crate) fn observer(&self) -> QueryObserver {
        self.observer.clone()
    }
    pub(crate) fn cancel_token(&self) -> CancelToken {
        self.observer.cancel_token()
    }
    pub(crate) fn check(&self) -> Result<()> {
        self.observer.check()
    }
    #[cfg(test)]
    pub(crate) fn deadline(&self) -> Result<Instant> {
        self.observer.deadline()
    }
    #[cfg(test)]
    pub(crate) fn progress(&self, stage: QueryStage, progress: QueryProgress) -> Result<()> {
        self.observer.progress(stage, progress)
    }
    /// Err不消费句柄：解析/容量错误后仍须finish(Err, None, no_worker_started)。
    pub(crate) fn resolve(&mut self, identity: QueryIdentity) -> Result<QueryResolution> {
        if self.role != Role::Resolver {
            return Err(QueryError::new("query_resolved", "检查身份已解析"));
        }
        let manager = self.observer.manager.clone();
        let id = self.observer.task_id.clone();
        let mut state = manager.state()?;
        let now = Instant::now();
        let original = state
            .tasks
            .get(&id)
            .ok_or_else(|| QueryError::new("query_not_executor", "检查解析身份已失效"))?;
        identity.validate_for(&original.requested)?;
        if original.status.is_terminal() {
            return Err(QueryError::new("query_already_terminal", "检查已结束"));
        }
        let original_clock = original.clock;
        let stop = original.stop_reason;
        if stop.is_some() || now >= original_clock.deadline || state.closing {
            let task = state.tasks.get_mut(&id).expect("checked source task");
            if stop.is_none() {
                task.request_stop(
                    if now >= original_clock.deadline {
                        StopReason::Deadline
                    } else {
                        StopReason::Shutdown
                    },
                    now,
                    manager.0.limits.max_events,
                );
            }
            return Ok(QueryResolution::Stopped);
        }
        if let Some(canonical) = state.by_identity.get(&identity).cloned() {
            let canonical_active = state
                .tasks
                .get(&canonical)
                .is_some_and(|task| !task.status.is_terminal());
            if canonical_active {
                let total = state.count_subscribers(&canonical) + state.count_subscribers(&id);
                if total > manager.0.limits.max_subscribers_per_task {
                    return Err(QueryError::new(
                        "query_subscriber_capacity",
                        "共享检查订阅已达上限",
                    ));
                }
                state.reserve_alias_slot(&manager.0.limits)?;
                let (_, order) = state.allocate("alias")?;
                let original = state.tasks.remove(&id).expect("checked source task");
                state.aliases.insert(
                    id.clone(),
                    Alias {
                        canonical: canonical.clone(),
                        requested: original.requested,
                        order,
                    },
                );
                for subscription in state
                    .subscriptions
                    .values_mut()
                    .filter(|s| s.canonical_id == id)
                {
                    subscription.canonical_id.clone_from(&canonical);
                }
                let task = state.tasks.get_mut(&canonical).expect("canonical task");
                task.clock.include_earlier(original_clock);
                if now >= task.clock.deadline {
                    task.request_stop(StopReason::Deadline, now, manager.0.limits.max_events);
                }
                task.record(QueryEventKind::Joined, now, manager.0.limits.max_events);
                self.role = Role::Joined;
                state.maintain(&manager.0.limits, now);
                return Ok(QueryResolution::Joined(Box::new(state.snapshot(&id)?)));
            }
            state.by_identity.remove(&identity);
        }
        if state
            .tasks
            .values()
            .filter(|task| !task.status.is_terminal() && task.identity.is_some())
            .count()
            >= manager.0.limits.max_active
        {
            return Err(QueryError::new(
                "query_capacity",
                "不同目标检查已达在途上限，请等待现有检查结束",
            ));
        }
        let task = state.tasks.get_mut(&id).expect("source task");
        task.identity = Some(identity.clone());
        task.validity = QueryValidity::Current;
        task.status = QueryStatus::Queued;
        task.stage = QueryStage::Queued;
        task.record(QueryEventKind::Resolved, now, manager.0.limits.max_events);
        state.by_identity.insert(identity, id);
        self.role = Role::Executor;
        Ok(QueryResolution::Execute)
    }
    /// 排队只占已解析身份槽；调用者循环check/watchdog，不刷新入口deadline。
    pub(crate) fn try_start(&self) -> Result<bool> {
        if self.role != Role::Executor {
            return Err(QueryError::new(
                "query_not_executor",
                "只有最终身份执行者可取得扫描槽",
            ));
        }
        let manager = &self.observer.manager;
        let mut state = manager.state()?;
        let now = Instant::now();
        let task = state
            .tasks
            .get_mut(self.task_id())
            .ok_or_else(|| QueryError::new("query_not_executor", "检查执行身份已失效"))?;
        if task.status.is_terminal() {
            return Err(QueryError::new("query_already_terminal", "检查已结束"));
        }
        if now >= task.clock.deadline {
            task.request_stop(StopReason::Deadline, now, manager.0.limits.max_events);
        }
        if let Some(reason) = task.stop_reason {
            return Err(stop_error(reason));
        }
        if task.execution_claimed {
            return Ok(true);
        }
        if state
            .tasks
            .values()
            .filter(|task| task.execution_claimed && !task.status.is_terminal())
            .count()
            >= manager.0.limits.max_running
        {
            return Ok(false);
        }
        let task = state.tasks.get_mut(self.task_id()).expect("executor task");
        task.execution_claimed = true;
        task.status = QueryStatus::Running;
        task.record(QueryEventKind::Progress, now, manager.0.limits.max_events);
        Ok(true)
    }
    /// 调用者spawn前check，spawn后立即登记；取消竞争不拒绝登记已启动的自有资源。
    pub(crate) fn attach_worker(&self, worker: WorkerIdentity) -> Result<()> {
        worker.validate()?;
        if self.role != Role::Executor {
            return Err(QueryError::new(
                "query_not_executor",
                "解析任务不得启动worker",
            ));
        }
        let mut state = self.observer.manager.state()?;
        let task = state
            .tasks
            .get_mut(self.task_id())
            .ok_or_else(|| QueryError::new("query_not_executor", "检查执行身份已失效"))?;
        if task.status.is_terminal() || task.worker.is_some() || !task.execution_claimed {
            return Err(QueryError::new(
                "query_worker_already_attached",
                "worker已登记或检查已结束",
            ));
        }
        task.worker = Some(worker);
        task.worker_reaped = false;
        task.readers_reaped = false;
        Ok(())
    }
    /// 回收暂未确认时保留非终态，不能提前显示cancelled/failed来隐藏残留。
    pub(crate) fn cleanup_pending(&self, error: QueryError) -> Result<()> {
        let mut state = self.observer.manager.state()?;
        let task = state
            .tasks
            .get_mut(self.task_id())
            .ok_or_else(|| QueryError::new("query_not_executor", "检查执行身份已失效"))?;
        if task.status.is_terminal() {
            return Err(QueryError::new("query_already_terminal", "检查已结束"));
        }
        task.stage = QueryStage::Reaping;
        task.error = Some(error);
        task.record(
            QueryEventKind::CleanupPending,
            Instant::now(),
            self.observer.manager.0.limits.max_events,
        );
        Ok(())
    }
    /// 唯一执行者在所有reader/Job已回收后完成。成功还必须提供结束时重读的身份fence。
    pub(crate) fn finish(
        &self,
        outcome: std::result::Result<Value, QueryError>,
        observed_identity: Option<QueryIdentity>,
        cleanup: CleanupProof,
    ) -> Result<QuerySnapshot> {
        if self.role == Role::Joined {
            return Err(QueryError::new(
                "query_not_executor",
                "共享别名不得结束权威任务",
            ));
        }
        let manager = &self.observer.manager;
        // 锁外产生唯一有界编码缓冲，释放Value树；锁内只转移Arc。
        let outcome = match outcome {
            Ok(value) => encode_result(value, manager.0.limits.max_result_bytes),
            Err(error) => Err(QueryError::new(&error.code, error.message)),
        };
        let mut state = manager.state()?;
        let now = Instant::now();
        let task = state
            .tasks
            .get_mut(self.task_id())
            .ok_or_else(|| QueryError::new("query_not_executor", "检查执行身份已失效"))?;
        if task.status.is_terminal() {
            return Err(QueryError::new("query_already_terminal", "检查终态已确定"));
        }
        if task.worker != cleanup.worker {
            return Err(QueryError::new(
                "query_cleanup_mismatch",
                "回收证明不属于此任务的自有worker",
            ));
        }
        if now >= task.clock.deadline {
            task.request_stop(StopReason::Deadline, now, manager.0.limits.max_events);
        }
        let usable = task.stop_reason.is_none()
            && task.identity.is_some()
            && observed_identity == task.identity;
        let success_size = if usable {
            outcome.as_ref().map(|bytes| bytes.len()).unwrap_or(0)
        } else {
            0
        };
        while state
            .tasks
            .values()
            .map(|task| task.result_bytes)
            .sum::<usize>()
            + success_size
            > manager.0.limits.max_total_result_bytes
        {
            if let Some(oldest) = state.oldest_terminal(Some(self.task_id())) {
                state.drop_task(&oldest);
            } else {
                return Err(QueryError::new(
                    "query_result_capacity",
                    "检查结果历史达到内存上限",
                ));
            }
        }
        let (_, finished_order) = state.allocate("terminal")?;
        let task = state.tasks.get_mut(self.task_id()).expect("executor task");
        task.worker_reaped = true;
        task.readers_reaped = true;
        task.execution_claimed = false;
        task.result = None;
        task.result_bytes = 0;
        if let Some(reason) = task.stop_reason {
            task.status = match reason {
                StopReason::UserCancel => QueryStatus::Cancelled,
                StopReason::Deadline => QueryStatus::TimedOut,
                StopReason::Shutdown => QueryStatus::Interrupted,
            };
            task.error = Some(stop_error(reason));
        } else {
            match outcome {
                Ok(bytes) if usable => {
                    task.status = QueryStatus::Succeeded;
                    task.validity = QueryValidity::Current;
                    task.result_bytes = bytes.len();
                    task.result = Some(bytes);
                    task.error = None;
                }
                Ok(_) => {
                    task.status = QueryStatus::Stale;
                    task.validity = QueryValidity::Stale;
                    task.error = Some(QueryError::new(
                        "query_identity_changed",
                        "目标身份已变化，请重新检查",
                    ));
                }
                Err(error) => {
                    task.status = QueryStatus::Failed;
                    task.error = Some(error);
                }
            }
        }
        task.stage = QueryStage::Complete;
        task.finished_order = Some(finished_order);
        task.record(QueryEventKind::Terminal, now, manager.0.limits.max_events);
        let identity = task.identity.clone();
        if let Some(identity) = identity {
            if state
                .by_identity
                .get(&identity)
                .is_some_and(|id| id == self.task_id())
            {
                state.by_identity.remove(&identity);
            }
        }
        state.maintain(&manager.0.limits, now);
        state.snapshot(self.task_id())
    }
}

struct SizeWriter {
    bytes: Vec<u8>,
    limit: usize,
}
impl Write for SizeWriter {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if bytes.len() > self.limit.saturating_sub(self.bytes.len()) {
            return Err(io::Error::other("query result exceeds bound"));
        }
        self.bytes.extend_from_slice(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}
fn encode_result(value: Value, limit: usize) -> Result<Arc<[u8]>> {
    let mut writer = SizeWriter {
        bytes: Vec::new(),
        limit,
    };
    serde_json::to_writer(&mut writer, &value)
        .map_err(|_| QueryError::new("query_result_too_large", "检查结果超过允许大小"))?;
    // 去掉Vec的预留capacity；任务内只计入恰好编码长度的共享slice。
    Ok(Arc::from(writer.bytes.into_boxed_slice()))
}

#[cfg(test)]
#[path = "query_tasks_tests.rs"]
mod tests;
