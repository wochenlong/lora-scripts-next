//! P6 操作控制：取消和读取不依赖 Engine 锁；磁盘变更必须持有工作区 lease。
//! 本模块只记录操作，不管理实例 generation、dirty、快照或恢复成功事实。
use crate::model::{self, Layout, WorkspaceMutation};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, VecDeque},
    fmt, fs,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
};

pub const OPERATION_SCHEMA_VERSION: u32 = 1;
const EVENT_LIMIT: usize = 256;
const RECORD_LIMIT: u64 = 64 * 1024;

#[derive(Clone, Debug, Default)]
pub struct CancelToken(Arc<AtomicBool>);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Cancelled;

impl fmt::Display for Cancelled {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("操作已请求取消")
    }
}
impl std::error::Error for Cancelled {}

impl CancelToken {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn is_cancel_requested(&self) -> bool {
        self.0.load(Ordering::Acquire)
    }

    pub fn check(&self) -> std::result::Result<(), Cancelled> {
        if self.is_cancel_requested() {
            Err(Cancelled)
        } else {
            Ok(())
        }
    }

    fn request(&self) {
        self.0.store(true, Ordering::Release);
    }
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum OperationKind {
    Download,
    Execute,
    Repair,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum OperationPhase {
    Preparing,
    Downloading,
    Executing,
    Verifying,
    Committing,
    Recovering,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum OperationStatus {
    Running,
    Succeeded,
    Failed,
    Cancelled,
    Interrupted,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OperationError {
    pub code: String,
    pub message: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OperationSnapshot {
    pub schema_version: u32,
    pub id: String,
    pub kind: OperationKind,
    pub phase: OperationPhase,
    pub status: OperationStatus,
    pub cancel_requested: bool,
    pub event_seq: u64,
    pub started_at: u64,
    pub updated_at: u64,
    pub error: Option<OperationError>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct OperationEvent {
    pub seq: u64,
    pub phase: OperationPhase,
    pub status: OperationStatus,
    pub message: String,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CancelReceipt {
    Accepted,
    AlreadyRequested,
    AlreadyFinished,
}

#[derive(Debug)]
struct State {
    snapshot: OperationSnapshot,
    events: VecDeque<OperationEvent>,
}

impl State {
    fn record(&mut self, message: &str) -> Result<()> {
        let seq = self
            .snapshot
            .event_seq
            .checked_add(1)
            .context("操作事件序号耗尽")?;
        self.snapshot.event_seq = seq;
        self.snapshot.updated_at = model::now();
        self.events.push_back(OperationEvent {
            seq,
            phase: self.snapshot.phase,
            status: self.snapshot.status,
            message: message.into(),
        });
        if self.events.len() > EVENT_LIMIT {
            self.events.pop_front();
        }
        Ok(())
    }
}

#[derive(Debug)]
struct Shared {
    cancel: CancelToken,
    state: Mutex<State>,
}

impl Shared {
    fn snapshot(&self) -> Result<OperationSnapshot> {
        let mut snapshot = self
            .state
            .lock()
            .map_err(|_| anyhow::anyhow!("操作快照锁异常"))?
            .snapshot
            .clone();
        snapshot.cancel_requested = self.cancel.is_cancel_requested();
        Ok(snapshot)
    }
}

/// 仅管理本进程已建立的操作身份，不实现调度或替代工作区互斥锁。
#[derive(Debug, Default)]
pub struct OperationManager {
    entries: Mutex<BTreeMap<String, Arc<Shared>>>,
}

impl OperationManager {
    pub fn start(&self, id: &str, kind: OperationKind) -> Result<OperationHandle> {
        validate_id(id)?;
        let mut entries = self
            .entries
            .lock()
            .map_err(|_| anyhow::anyhow!("操作索引锁异常"))?;
        if entries.contains_key(id) {
            bail!("操作 ID 已存在，不能重用：{id}");
        }
        let started_at = model::now();
        let mut state = State {
            snapshot: OperationSnapshot {
                schema_version: OPERATION_SCHEMA_VERSION,
                id: id.into(),
                kind,
                phase: OperationPhase::Preparing,
                status: OperationStatus::Running,
                cancel_requested: false,
                event_seq: 0,
                started_at,
                updated_at: started_at,
                error: None,
            },
            events: VecDeque::new(),
        };
        state.record("操作已建立")?;
        let shared = Arc::new(Shared {
            cancel: CancelToken::new(),
            state: Mutex::new(state),
        });
        entries.insert(id.into(), shared.clone());
        Ok(OperationHandle {
            shared,
            persistence: Mutex::new(Persisted::default()),
        })
    }

    fn lookup(&self, id: &str) -> Result<Arc<Shared>> {
        self.entries
            .lock()
            .map_err(|_| anyhow::anyhow!("操作索引锁异常"))?
            .get(id)
            .cloned()
            .with_context(|| format!("操作不存在：{id}"))
    }

    pub fn snapshot(&self, id: &str) -> Result<OperationSnapshot> {
        self.lookup(id)?.snapshot()
    }

    /// 只确认请求已接受；不会等待 worker，更不表示实例已恢复或可启动。
    pub fn cancel(&self, id: &str) -> Result<CancelReceipt> {
        let shared = self.lookup(id)?;
        let mut state = shared
            .state
            .lock()
            .map_err(|_| anyhow::anyhow!("操作快照锁异常"))?;
        if state.snapshot.status != OperationStatus::Running {
            return Ok(CancelReceipt::AlreadyFinished);
        }
        if shared.cancel.is_cancel_requested() {
            return Ok(CancelReceipt::AlreadyRequested);
        }
        state.record("已接受取消请求，等待工作线程收尾")?;
        shared.cancel.request();
        state.snapshot.cancel_requested = true;
        Ok(CancelReceipt::Accepted)
    }

    /// 事件仅保留最近 256 项。游标过旧时必须重新读取快照，不能静默漏报。
    pub fn events_since(&self, id: &str, seq: u64) -> Result<Vec<OperationEvent>> {
        let shared = self.lookup(id)?;
        let state = shared
            .state
            .lock()
            .map_err(|_| anyhow::anyhow!("操作快照锁异常"))?;
        if seq > state.snapshot.event_seq {
            bail!("事件游标超过当前操作序号");
        }
        if state
            .events
            .front()
            .is_some_and(|first| seq < first.seq.saturating_sub(1))
        {
            bail!("事件游标已过期；请重新读取操作快照");
        }
        Ok(state
            .events
            .iter()
            .filter(|event| event.seq > seq)
            .cloned()
            .collect())
    }
}

#[derive(Debug, Default)]
struct Persisted {
    path: Option<PathBuf>,
    record: Option<OperationSnapshot>,
}

/// 单 worker 持有的写入口；不可 Clone。管理器只暴露读取与取消。
#[derive(Debug)]
pub struct OperationHandle {
    shared: Arc<Shared>,
    persistence: Mutex<Persisted>,
}

impl OperationHandle {
    pub fn cancel_token(&self) -> CancelToken {
        self.shared.cancel.clone()
    }

    pub fn publish(&self, phase: OperationPhase, message: &str) -> Result<()> {
        let mut state = self
            .shared
            .state
            .lock()
            .map_err(|_| anyhow::anyhow!("操作快照锁异常"))?;
        if state.snapshot.status != OperationStatus::Running {
            bail!("操作已结束，不能再改变阶段");
        }
        state.snapshot.phase = phase;
        state.record(message)
    }

    /// 提交临界区后的成功可与 cancel_requested 同时存在；终态由实际 worker 决定。
    pub fn finish(&self, status: OperationStatus, error: Option<OperationError>) -> Result<()> {
        if status == OperationStatus::Running {
            bail!("finish 必须提供终态");
        }
        if status == OperationStatus::Succeeded && error.is_some() {
            bail!("成功结果不能携带失败原因");
        }
        if status == OperationStatus::Failed && error.is_none() {
            bail!("失败结果必须提供结构化错误");
        }
        let mut state = self
            .shared
            .state
            .lock()
            .map_err(|_| anyhow::anyhow!("操作快照锁异常"))?;
        if state.snapshot.status != OperationStatus::Running {
            bail!("操作终态已确定，不能重复完成");
        }
        state.snapshot.status = status;
        state.snapshot.error = error;
        state.record("工作线程已结束；实例恢复状态须另行核验")
    }

    /// 持工作区 lease 写独立操作记录，绝不覆盖 v1 journal/registry。
    /// 序列化磁盘写锁不与快照锁共用；任何文件 I/O 期间都可读取和取消。
    pub fn persist(&self, mutation: &WorkspaceMutation) -> Result<()> {
        let mut persisted = self
            .persistence
            .lock()
            .map_err(|_| anyhow::anyhow!("操作持久化锁异常"))?;
        let snapshot = self.shared.snapshot()?;
        if serde_json::to_vec(&snapshot)?.len() as u64 > RECORD_LIMIT {
            bail!("操作记录超过64KiB，拒绝写入无法重新读取的状态");
        }
        let layout = mutation.layout();
        let directory = layout.root.join("state/operations");
        layout.guard_path(&directory)?;
        let path = directory.join(format!("{}.json", snapshot.id));
        layout.guard_path(&path)?;
        let existing = read_records(layout, &directory)?;
        match (&persisted.path, &persisted.record) {
            (None, None) if existing.contains_key(&snapshot.id) => {
                bail!("操作 ID 已有持久记录，拒绝覆盖：{}", snapshot.id);
            }
            (Some(previous_path), Some(previous_record)) => {
                if previous_path != &path {
                    bail!("同一操作不能跨工作区持久化");
                }
                if existing.get(&snapshot.id) != Some(previous_record) {
                    bail!("操作记录已改变或丢失；保留现场并拒绝覆盖");
                }
            }
            (None, None) => {}
            _ => bail!("操作持久化身份不完整"),
        }
        layout.ensure_dir(&directory)?;
        model::write_json_atomic(&path, &snapshot)?;
        persisted.path = Some(path);
        persisted.record = Some(snapshot);
        Ok(())
    }
}

fn validate_id(id: &str) -> Result<()> {
    model::validate_component(id)?;
    if id.len() > 96
        || !id
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || b"-_".contains(&byte))
    {
        bail!("操作 ID 仅接受不超过96字节的小写字母、数字、连字符和下划线");
    }
    Ok(())
}

/// 先验证整个操作记录命名空间，再创建目录或写入；未知格式不降级为空状态。
fn read_records(layout: &Layout, directory: &Path) -> Result<BTreeMap<String, OperationSnapshot>> {
    let mut records = BTreeMap::new();
    if !directory.exists() {
        return Ok(records);
    }
    layout.guard_path(directory)?;
    for entry in fs::read_dir(directory)? {
        let entry = entry?;
        let path = entry.path();
        layout.guard_path(&path)?;
        if path.extension().is_some_and(|extension| extension == "tmp") {
            continue; // 原子写失败的临时证据保留，不将它当成已提交记录。
        }
        if !entry.file_type()?.is_file()
            || path.extension().is_none_or(|extension| extension != "json")
            || fs::metadata(&path)?.len() > RECORD_LIMIT
        {
            bail!("操作记录目录包含不支持的内容：{}", path.display());
        }
        let record: OperationSnapshot = serde_json::from_slice(&fs::read(&path)?)
            .with_context(|| format!("操作记录损坏或字段不受支持：{}", path.display()))?;
        if record.schema_version != OPERATION_SCHEMA_VERSION {
            bail!(
                "operation schema {} 不受支持；保留原文件并拒绝变更",
                record.schema_version
            );
        }
        validate_id(&record.id)?;
        if path.file_stem().and_then(|stem| stem.to_str()) != Some(record.id.as_str())
            || record.event_seq == 0
        {
            bail!("操作记录身份或事件序号无效：{}", path.display());
        }
        if records.insert(record.id.clone(), record).is_some() {
            bail!("操作记录身份重复");
        }
    }
    Ok(records)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        sync::{atomic::AtomicU64, mpsc},
        thread,
        time::Duration,
    };

    static NEXT_TEST: AtomicU64 = AtomicU64::new(0);
    struct Temp(PathBuf);

    impl Temp {
        fn new() -> Self {
            let serial = NEXT_TEST.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir().join(format!(
                "next-trainer-operations-{}-{}-{serial}",
                std::process::id(),
                model::now()
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }

        fn mutation(&self) -> WorkspaceMutation {
            let catalog = model::Catalog::embedded().unwrap();
            WorkspaceMutation::acquire(&self.0, &catalog.releases[0].id).unwrap()
        }
    }

    impl Drop for Temp {
        fn drop(&mut self) {
            if self.0.is_absolute()
                && self.0.parent() == Some(std::env::temp_dir().as_path())
                && self.0.file_name().is_some_and(|name| {
                    name.to_string_lossy()
                        .starts_with("next-trainer-operations-")
                })
            {
                let _ = fs::remove_dir_all(&self.0);
            }
        }
    }

    #[test]
    fn cancel_and_read_do_not_wait_for_engine_mutex() {
        let manager = Arc::new(OperationManager::default());
        let handle = manager
            .start("p6-engine-lock", OperationKind::Execute)
            .unwrap();
        let token = handle.cancel_token();
        let engine = Arc::new(Mutex::new(()));
        let held_engine = engine.lock().unwrap();
        let worker_engine = engine.clone();
        let worker = thread::spawn(move || {
            let _engine = worker_engine.lock().unwrap();
            token.check().unwrap_err();
            handle.finish(OperationStatus::Cancelled, None).unwrap();
        });
        let reader_manager = manager.clone();
        let (send, receive) = mpsc::channel();
        let reader = thread::spawn(move || {
            let receipt = reader_manager.cancel("p6-engine-lock").unwrap();
            let snapshot = reader_manager.snapshot("p6-engine-lock").unwrap();
            let events = reader_manager.events_since("p6-engine-lock", 0).unwrap();
            send.send((receipt, snapshot, events)).unwrap();
        });
        let result = receive.recv_timeout(Duration::from_secs(2));
        drop(held_engine); // 先释放，避免断言失败时留下等待中的 worker。
        worker.join().unwrap();
        reader.join().unwrap();
        let (receipt, snapshot, events) = result.expect("取消/读取必须独立于 Engine 锁返回");
        assert_eq!(receipt, CancelReceipt::Accepted);
        assert_eq!(snapshot.status, OperationStatus::Running);
        assert!(snapshot.cancel_requested);
        assert_eq!(events.last().unwrap().seq, snapshot.event_seq);
        assert_eq!(
            manager.snapshot("p6-engine-lock").unwrap().status,
            OperationStatus::Cancelled
        );
        assert_eq!(
            manager.cancel("p6-engine-lock").unwrap(),
            CancelReceipt::AlreadyFinished
        );
    }

    #[test]
    fn persistence_wait_does_not_hold_snapshot_or_cancel_locks() {
        let temp = Temp::new();
        let mutation = temp.mutation();
        let manager = Arc::new(OperationManager::default());
        let handle = Arc::new(
            manager
                .start("p6-persist-wait", OperationKind::Repair)
                .unwrap(),
        );
        let held_persistence = handle.persistence.lock().unwrap();
        let writer_handle = handle.clone();
        let writer = thread::spawn(move || writer_handle.persist(&mutation).unwrap());
        let reader_manager = manager.clone();
        let (send, receive) = mpsc::channel();
        let reader = thread::spawn(move || {
            let receipt = reader_manager.cancel("p6-persist-wait").unwrap();
            send.send((receipt, reader_manager.snapshot("p6-persist-wait").unwrap()))
                .unwrap();
        });
        let result = receive.recv_timeout(Duration::from_secs(2));
        drop(held_persistence);
        writer.join().unwrap();
        reader.join().unwrap();
        let (receipt, snapshot) = result.expect("持久化等待不能阻止读取或取消");
        assert_eq!(receipt, CancelReceipt::Accepted);
        assert!(snapshot.cancel_requested);
    }

    #[test]
    fn event_cursor_detects_a_gap_and_terminal_state_is_immutable() {
        let manager = OperationManager::default();
        let handle = manager.start("p6-events", OperationKind::Download).unwrap();
        for _ in 0..EVENT_LIMIT {
            handle
                .publish(OperationPhase::Downloading, "读取下载块")
                .unwrap();
        }
        assert!(manager.events_since("p6-events", 0).is_err());
        let before = manager.snapshot("p6-events").unwrap();
        handle.finish(OperationStatus::Succeeded, None).unwrap();
        let events = manager.events_since("p6-events", before.event_seq).unwrap();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0].phase, OperationPhase::Downloading);
        assert_eq!(events[0].status, OperationStatus::Succeeded);
        assert!(handle.publish(OperationPhase::Recovering, "重开").is_err());
        assert!(handle
            .finish(
                OperationStatus::Failed,
                Some(OperationError {
                    code: "late_failure".into(),
                    message: "不得改写已确认终态".into(),
                })
            )
            .is_err());
    }

    #[test]
    fn cancel_receipt_is_not_completion_and_phase_is_not_status() {
        let manager = OperationManager::default();
        let handle = manager.start("p6-commit", OperationKind::Repair).unwrap();
        handle
            .publish(OperationPhase::Executing, "变更后待验证")
            .unwrap();
        handle
            .publish(OperationPhase::Verifying, "校验候选")
            .unwrap();
        handle
            .publish(OperationPhase::Committing, "提交临界区")
            .unwrap();
        assert_eq!(
            manager.cancel("p6-commit").unwrap(),
            CancelReceipt::Accepted
        );
        assert_eq!(
            manager.cancel("p6-commit").unwrap(),
            CancelReceipt::AlreadyRequested
        );
        let snapshot = manager.snapshot("p6-commit").unwrap();
        assert_eq!(snapshot.phase, OperationPhase::Committing);
        assert_eq!(snapshot.status, OperationStatus::Running);
        assert_eq!(handle.cancel_token().check(), Err(Cancelled));
        // 请求在最后取消检查点之后到达，提交已完成时可以真实报告成功。
        handle.finish(OperationStatus::Succeeded, None).unwrap();
        let snapshot = manager.snapshot("p6-commit").unwrap();
        assert!(snapshot.cancel_requested);
        assert_eq!(snapshot.status, OperationStatus::Succeeded);
        assert_eq!(snapshot.phase, OperationPhase::Committing);
        let interrupted = manager
            .start("p6-interrupted", OperationKind::Execute)
            .unwrap();
        interrupted
            .finish(OperationStatus::Interrupted, None)
            .unwrap();
        assert_eq!(
            manager.snapshot("p6-interrupted").unwrap().status,
            OperationStatus::Interrupted
        );
    }

    #[test]
    fn unknown_or_corrupt_schema_preserves_all_bytes_and_v1_journal() {
        let temp = Temp::new();
        let mutation = temp.mutation();
        let layout = mutation.layout();
        model::Journal::new(layout.release_dir.file_name().unwrap().to_str().unwrap())
            .unwrap()
            .store(&temp.0)
            .unwrap();
        let journal_path = temp.0.join("state").join(format!(
            "journal-{}.json",
            layout.release_dir.file_name().unwrap().to_str().unwrap()
        ));
        let journal_before = fs::read(&journal_path).unwrap();
        let directory = temp.0.join("state/operations");
        layout.ensure_dir(&directory).unwrap();
        let manager = OperationManager::default();
        let handle = manager.start("p6-new", OperationKind::Repair).unwrap();
        let mut record = manager.snapshot("p6-new").unwrap();
        record.id = "p6-foreign".into();
        let foreign_path = directory.join("p6-foreign.json");
        let mut unknown_version = serde_json::to_value(&record).unwrap();
        unknown_version["schema_version"] = 999.into();
        let mut unknown_field = serde_json::to_value(&record).unwrap();
        unknown_field["future_field"] = true.into();
        let cases = [
            serde_json::to_vec(&unknown_version).unwrap(),
            serde_json::to_vec(&unknown_field).unwrap(),
            b"{broken operation record".to_vec(),
        ];
        for bytes in cases {
            fs::write(&foreign_path, &bytes).unwrap();
            assert!(handle.persist(&mutation).is_err());
            assert_eq!(fs::read(&foreign_path).unwrap(), bytes);
            assert!(!directory.join("p6-new.json").exists());
            assert_eq!(fs::read(&journal_path).unwrap(), journal_before);
        }
    }

    #[test]
    fn persisted_id_cannot_be_reused_or_overwrite_changed_record() {
        let temp = Temp::new();
        let mutation = temp.mutation();
        let manager = OperationManager::default();
        let handle = manager
            .start("p6-persist", OperationKind::Download)
            .unwrap();
        handle.persist(&mutation).unwrap();
        handle
            .publish(OperationPhase::Downloading, "开始读取")
            .unwrap();
        handle.persist(&mutation).unwrap();
        let path = temp.0.join("state/operations/p6-persist.json");
        let bytes = fs::read(&path).unwrap();
        let restarted = OperationManager::default();
        let duplicate = restarted
            .start("p6-persist", OperationKind::Repair)
            .unwrap();
        assert!(duplicate.persist(&mutation).is_err());
        assert_eq!(fs::read(&path).unwrap(), bytes);
        let mut changed: OperationSnapshot = serde_json::from_slice(&bytes).unwrap();
        changed.event_seq += 1;
        let changed_bytes = serde_json::to_vec(&changed).unwrap();
        fs::write(&path, &changed_bytes).unwrap();
        assert!(handle.persist(&mutation).is_err());
        assert_eq!(fs::read(&path).unwrap(), changed_bytes);
    }

    #[test]
    fn operation_ids_refuse_paths_and_windows_case_aliases() {
        let manager = OperationManager::default();
        for id in [
            "",
            "..",
            "../outside",
            "p6/other",
            "con",
            "P6-Same",
            "p6.name",
        ] {
            assert!(manager.start(id, OperationKind::Repair).is_err(), "{id:?}");
        }
        assert!(manager.start("p6-valid_1", OperationKind::Repair).is_ok());
        assert!(manager.start("p6-valid_1", OperationKind::Repair).is_err());
    }
}
