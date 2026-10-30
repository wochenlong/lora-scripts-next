//! Dedicated, bounded launcher logs. Paths are owned by the app, never IPC inputs.
use serde::{Deserialize, Serialize};
use std::{
    cell::RefCell,
    collections::{BTreeMap, BTreeSet, VecDeque},
    fs::{self, File, OpenOptions},
    io::{self, Read, Write},
    path::{Path, PathBuf},
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
const FILES: usize = 4;
const FILE_BYTES: u64 = 2 * 1024 * 1024;
const MEMORY_LINES: usize = 2000;
const LINE_BYTES: usize = 8 * 1024;

#[derive(Clone, Default)]
pub struct Context {
    pub root: Option<String>,
    pub run_id: Option<String>,
    pub operation_id: Option<String>,
    pub source: &'static str,
}
impl Context {
    pub fn workspace(root: &Path, source: &'static str) -> Self {
        Self {
            root: Some(root.to_string_lossy().into()),
            source,
            ..Self::default()
        }
    }
}
thread_local! { static CONTEXT: RefCell<Option<Context>> = const { RefCell::new(None) }; }
pub struct ContextGuard(Option<Context>);
impl Drop for ContextGuard {
    fn drop(&mut self) {
        CONTEXT.with(|value| *value.borrow_mut() = self.0.take());
    }
}
pub fn bind(context: Context) -> ContextGuard {
    ContextGuard(CONTEXT.with(|value| value.replace(Some(context))))
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct LogRecord {
    pub id: String,
    pub seq: u64,
    pub session_id: String,
    pub received_at: u128,
    pub line: String,
    pub root: Option<String>,
    pub run_id: Option<String>,
    pub operation_id: Option<String>,
    pub source: String,
    pub level: String,
    pub persisted: bool,
}
#[derive(Serialize)]
pub struct Session {
    pub session_id: String,
    /// Earliest retained receive time, not a fabricated session start time.
    pub started_at: u128,
    pub retained_records: usize,
}
#[derive(Serialize)]
pub struct LogPage {
    pub records: Vec<LogRecord>,
    pub has_more: bool,
    pub next_before_seq: Option<u64>,
    pub current_session_id: String,
    pub sessions: Vec<Session>,
    pub partial: bool,
    pub io_error: Option<String>,
}
struct State {
    receive_counter: u64,
    calibrated: bool,
    last_disk_seq: u64,
    memory: VecDeque<LogRecord>,
    io_error: Option<String>,
}
pub struct LogStore {
    dir: PathBuf,
    session: String,
    file_bytes: u64,
    state: Mutex<State>,
}
fn now() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}
fn error(message: impl Into<String>) -> io::Error {
    io::Error::other(message.into())
}
fn path_guard(path: &Path) -> io::Result<()> {
    match fs::symlink_metadata(path) {
        Ok(metadata) => {
            #[cfg(windows)]
            let reparse = {
                use std::os::windows::fs::MetadataExt;
                metadata.file_attributes() & 0x400 != 0
            };
            #[cfg(not(windows))]
            let reparse = false;
            if metadata.file_type().is_symlink() || reparse {
                return Err(error("日志路径包含链接，已拒绝读写"));
            }
            Ok(())
        }
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e),
    }
}
struct DiskLock(File);
impl Drop for DiskLock {
    fn drop(&mut self) {
        let _ = fs2::FileExt::unlock(&self.0);
    }
}
impl LogStore {
    pub fn open(dir: PathBuf) -> Arc<Self> {
        Self::with_limit(dir, FILE_BYTES)
    }
    fn with_limit(dir: PathBuf, file_bytes: u64) -> Arc<Self> {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos();
        Arc::new(Self {
            dir,
            file_bytes,
            session: format!("session-{}-{nonce}", std::process::id()),
            state: Mutex::new(State {
                receive_counter: 0,
                calibrated: false,
                last_disk_seq: 0,
                memory: VecDeque::new(),
                io_error: None,
            }),
        })
    }
    fn file(&self, index: usize) -> PathBuf {
        self.dir.join(format!("launcher-{index}.jsonl"))
    }
    fn disk_lock(&self) -> io::Result<DiskLock> {
        for path in self.dir.ancestors() {
            path_guard(path)?;
        }
        fs::create_dir_all(&self.dir)?;
        let path = self.dir.join(".lock");
        path_guard(&path)?;
        let file = OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(path)?;
        let deadline = Instant::now() + Duration::from_millis(10);
        loop {
            match fs2::FileExt::try_lock_exclusive(&file) {
                Ok(()) => return Ok(DiskLock(file)),
                Err(_) if Instant::now() < deadline => thread::sleep(Duration::from_millis(1)),
                Err(e) => return Err(e),
            }
        }
    }
    fn read_disk(&self) -> (Vec<LogRecord>, Option<String>) {
        let mut records = Vec::new();
        let mut problem = None;
        // Open a coherent set of bounded handles under the interprocess lock;
        // parsing happens after this lock is released, keeping append responsive.
        let handles = (|| -> io::Result<Vec<File>> {
            let _lock = self.disk_lock()?;
            let mut handles = Vec::new();
            for index in 0..FILES {
                let path = self.file(index);
                path_guard(&path)?;
                match File::open(path) {
                    Ok(file) => handles.push(file),
                    Err(e) if e.kind() == io::ErrorKind::NotFound => {}
                    Err(e) => return Err(e),
                }
            }
            Ok(handles)
        })();
        let handles = match handles {
            Ok(handles) => handles,
            Err(e) => return (records, Some(e.to_string())),
        };
        for file in handles {
            let mut bytes = Vec::new();
            if let Err(e) = file.take(self.file_bytes + 1).read_to_end(&mut bytes) {
                problem = Some(e.to_string());
                continue;
            }
            if bytes.len() as u64 > self.file_bytes {
                problem = Some("日志分片超过上限，只读取允许的字节".into());
                bytes.truncate(self.file_bytes as usize);
            }
            for raw in bytes
                .split(|byte| *byte == b'\n')
                .filter(|line| !line.is_empty())
            {
                if raw.len() > LINE_BYTES * 4 {
                    problem = Some("跳过超长日志记录".into());
                    continue;
                }
                match serde_json::from_slice::<LogRecord>(raw) {
                    Ok(mut record) => {
                        record.line = redact(&record.line);
                        records.push(record);
                    }
                    Err(_) => problem = Some("部分日志记录不完整或格式损坏，已跳过".into()),
                }
            }
        }
        (records, problem)
    }
    fn next_seq(&self, calibrated: bool, own_max: u64) -> io::Result<u64> {
        let cursor = self.dir.join(".cursor");
        path_guard(&cursor)?;
        let previous = match File::open(&cursor) {
            Ok(file) => {
                let mut value = String::new();
                file.take(64).read_to_string(&mut value)?;
                value
                    .strip_prefix("v1:")
                    .and_then(|value| value.strip_suffix('\n'))
                    .and_then(|value| value.parse::<u64>().ok())
            }
            Err(e) if e.kind() == io::ErrorKind::NotFound => None,
            Err(e) => return Err(e),
        };
        let previous = if let Some(previous) = previous.filter(|_| calibrated) {
            previous.max(own_max)
        } else {
            // Recovery is bounded to the same four fixed shards. No recursive
            // lock: the caller already owns the cross-process append lock.
            let mut maximum = 0;
            for index in 0..FILES {
                let path = self.file(index);
                path_guard(&path)?;
                let file = match File::open(path) {
                    Ok(file) => file,
                    Err(e) if e.kind() == io::ErrorKind::NotFound => continue,
                    Err(e) => return Err(e),
                };
                let mut raw = Vec::new();
                file.take(self.file_bytes).read_to_end(&mut raw)?;
                for line in raw.split(|byte| *byte == b'\n') {
                    if let Ok(record) = serde_json::from_slice::<LogRecord>(line) {
                        maximum = maximum.max(record.seq);
                    }
                }
            }
            maximum.max(previous.unwrap_or(0)).max(own_max)
        };
        let seq = previous
            .checked_add(1)
            .ok_or_else(|| error("日志序号已超过范围"))?;
        // Reserve before appending; a crash may leave a gap, never reuse a seq.
        let mut file = OpenOptions::new()
            .create(true)
            .truncate(true)
            .write(true)
            .open(cursor)?;
        file.write_all(format!("v1:{seq}\n").as_bytes())?;
        Ok(seq)
    }
    fn rotate_if_needed(&self, bytes: u64) -> io::Result<()> {
        let current = self.file(0);
        path_guard(&current)?;
        let current_len = match fs::metadata(&current) {
            Ok(v) => v.len(),
            Err(e) if e.kind() == io::ErrorKind::NotFound => 0,
            Err(e) => return Err(e),
        };
        if current_len + bytes <= self.file_bytes {
            return Ok(());
        }
        if bytes > self.file_bytes {
            return Err(error("单条日志超过分片容量"));
        }
        for index in 0..FILES {
            path_guard(&self.file(index))?;
        }
        match fs::remove_file(self.file(FILES - 1)) {
            Ok(()) => {}
            Err(e) if e.kind() == io::ErrorKind::NotFound => {}
            Err(e) => return Err(e),
        }
        for index in (0..FILES - 1).rev() {
            match fs::rename(self.file(index), self.file(index + 1)) {
                Ok(()) => {}
                Err(e) if e.kind() == io::ErrorKind::NotFound => {}
                Err(e) => return Err(e),
            }
        }
        Ok(())
    }
    pub fn record_current(&self, line: &str) -> LogRecord {
        let context = CONTEXT
            .with(|value| value.borrow().clone())
            .unwrap_or_default();
        self.record(line, &context)
    }
    pub fn record(&self, line: &str, context: &Context) -> LogRecord {
        let received_at = now();
        let line = redact(line);
        let level = if line.contains("ERROR")
            || line.contains("FATAL")
            || line.contains("Traceback")
            || line.contains("[失败]")
        {
            "ERROR"
        } else if line.contains("WARN") || line.contains("警告：") {
            "WARN"
        } else if line.contains("INFO") || line.contains("[信息]") {
            "INFO"
        } else {
            "UNKNOWN"
        };
        let mut state = self.state.lock().unwrap_or_else(|e| e.into_inner());
        state.receive_counter += 1;
        let mut record = LogRecord {
            id: format!("{}:{}", self.session, state.receive_counter),
            seq: 0,
            session_id: self.session.clone(),
            received_at,
            line,
            root: context.root.clone(),
            run_id: context.run_id.clone(),
            operation_id: context.operation_id.clone(),
            source: if context.source.is_empty() {
                "unknown"
            } else {
                context.source
            }
            .into(),
            level: level.into(),
            persisted: false,
        };
        let result = (|| -> io::Result<()> {
            let _lock = self.disk_lock()?;
            record.seq = self.next_seq(state.calibrated, state.last_disk_seq)?;
            state.calibrated = true;
            state.last_disk_seq = record.seq;
            record.persisted = true;
            let mut encoded = serde_json::to_vec(&record).map_err(|e| error(e.to_string()))?;
            encoded.push(b'\n');
            self.rotate_if_needed(encoded.len() as u64)?;
            let mut file = OpenOptions::new()
                .create(true)
                .truncate(false)
                .append(true)
                .open(self.file(0))?;
            file.write_all(&encoded)
        })();
        if let Err(e) = result {
            record.seq = 0;
            record.persisted = false;
            state.io_error = Some(e.to_string());
        }
        state.memory.push_back(record.clone());
        while state.memory.len() > MEMORY_LINES {
            state.memory.pop_front();
        }
        record
    }
    pub fn read(
        &self,
        root: Option<&str>,
        before: Option<u64>,
        limit: usize,
        session: Option<&str>,
    ) -> LogPage {
        let (mut records, disk_error) = self.read_disk();
        let (memory, local_error) = {
            let state = self.state.lock().unwrap_or_else(|e| e.into_inner());
            (state.memory.clone(), state.io_error.clone())
        };
        records.extend(memory);
        let mut seen = BTreeSet::new();
        records.retain(|record| seen.insert(record.id.clone()));
        records.retain(|record| {
            root.is_none_or(|root| {
                record
                    .root
                    .as_deref()
                    .is_none_or(|record_root| same_root(root, record_root))
            })
        });
        let mut sessions: BTreeMap<String, Session> = BTreeMap::new();
        for record in &records {
            let item = sessions
                .entry(record.session_id.clone())
                .or_insert_with(|| Session {
                    session_id: record.session_id.clone(),
                    started_at: record.received_at,
                    retained_records: 0,
                });
            item.started_at = item.started_at.min(record.received_at);
            item.retained_records += 1;
        }
        let mut sessions: Vec<_> = sessions.into_values().collect();
        sessions.sort_by_key(|session| std::cmp::Reverse(session.started_at));
        records.retain(|record| {
            session.is_none_or(|session| record.session_id == session)
                && before.is_none_or(|before| record.seq > 0 && record.seq < before)
        });
        records.sort_by_key(|record| {
            (
                if record.seq == 0 {
                    u64::MAX
                } else {
                    record.seq
                },
                record.received_at,
            )
        });
        let limit = limit.clamp(1, 500);
        let start = records.len().saturating_sub(limit);
        let excluded_max = records[..start]
            .iter()
            .filter_map(|record| (record.seq > 0).then_some(record.seq))
            .max();
        let has_more = excluded_max.is_some();
        let records: Vec<_> = records.into_iter().skip(start).collect();
        let next = if has_more {
            records
                .iter()
                .filter_map(|record| (record.seq > 0).then_some(record.seq))
                .min()
                // An unsaved-only latest page still needs a persistent cursor.
                .or_else(|| excluded_max.and_then(|seq| seq.checked_add(1)))
        } else {
            None
        };
        let io_error = disk_error.or(local_error).map(|message| redact(&message));
        LogPage {
            partial: io_error.is_some() || records.iter().any(|record| !record.persisted),
            io_error,
            records,
            has_more,
            next_before_seq: next,
            current_session_id: self.session.clone(),
            sessions,
        }
    }
}
fn same_root(a: &str, b: &str) -> bool {
    a.trim()
        .replace('\\', "/")
        .trim_end_matches('/')
        .eq_ignore_ascii_case(b.trim().replace('\\', "/").trim_end_matches('/'))
}

/// Network policy removes URL credentials and queries; this additionally covers
/// standalone config secrets and HTTP headers before anything reaches disk.
pub fn redact(value: &str) -> String {
    fn bound(value: &str, bytes: usize) -> &str {
        let mut end = value.len().min(bytes);
        while !value.is_char_boundary(end) {
            end -= 1;
        }
        &value[..end]
    }
    let value = crate::network_policy::redact(bound(value, 64 * 1024));
    let lower = value.to_ascii_lowercase();
    let bytes = value.as_bytes();
    let keys = [
        "proxy-authorization",
        "authorization",
        "refresh_token",
        "refresh-token",
        "access_token",
        "access-token",
        "set-cookie",
        "api_key",
        "api-key",
        "apikey",
        "password",
        "passwd",
        "secret",
        "cookie",
        "token",
    ];
    let mut result = String::new();
    let mut index = 0;
    while index < value.len() {
        let boundary =
            index == 0 || !(bytes[index - 1].is_ascii_alphanumeric() || bytes[index - 1] == b'_');
        // A long unbroken ASCII line has one identifier. Scan its suffix only
        // at a boundary, rather than rescanning it for every following byte.
        let key = if boundary {
            let identifier_end = lower[index..]
                .find(|ch: char| !ch.is_ascii_alphanumeric() && !matches!(ch, '_' | '-'))
                .map(|end| index + end)
                .unwrap_or(lower.len());
            let identifier = &lower[index..identifier_end];
            let extended = identifier.ends_with("_token")
                || identifier.ends_with("_password")
                || identifier.ends_with("_secret")
                || identifier.ends_with("_api_key")
                || matches!(
                    identifier,
                    "apitoken" | "accesstoken" | "refreshtoken" | "authtoken"
                );
            if extended {
                Some(identifier)
            } else {
                keys.iter()
                    .find(|key| lower[index..].starts_with(**key))
                    .copied()
            }
        } else {
            None
        };
        if let Some(key) = key {
            let mut separator = index + key.len();
            if bytes
                .get(separator)
                .is_some_and(|c| matches!(c, b'\'' | b'"'))
            {
                separator += 1;
            }
            while bytes.get(separator).is_some_and(u8::is_ascii_whitespace) {
                separator += 1;
            }
            if bytes
                .get(separator)
                .is_some_and(|c| matches!(c, b':' | b'='))
            {
                let mut start = separator + 1;
                while bytes.get(start).is_some_and(u8::is_ascii_whitespace) {
                    start += 1;
                }
                result.push_str(&value[index..start]);
                result.push_str("[已隐藏]");
                let header = matches!(
                    key,
                    "authorization" | "proxy-authorization" | "cookie" | "set-cookie"
                );
                let mut end = start;
                if bytes.get(start).is_some_and(|c| matches!(c, b'\'' | b'"')) {
                    let quote = bytes[start];
                    end += 1;
                    while end < bytes.len() {
                        if bytes[end] == b'\\' {
                            end = (end + 2).min(bytes.len());
                        } else if bytes[end] == quote {
                            end += 1;
                            break;
                        } else {
                            end += 1;
                        }
                    }
                } else {
                    while end < bytes.len()
                        && !matches!(bytes[end], b'\n' | b'\r')
                        && (header || !matches!(bytes[end], b',' | b';' | b'}'))
                    {
                        end += 1;
                    }
                }
                index = end;
                continue;
            }
        }
        let scheme = ["bearer", "basic"].iter().find(|scheme| {
            boundary
                && lower[index..].starts_with(**scheme)
                && bytes
                    .get(index + scheme.len())
                    .is_some_and(u8::is_ascii_whitespace)
        });
        if let Some(scheme) = scheme {
            let mut end = index + scheme.len();
            while bytes.get(end).is_some_and(u8::is_ascii_whitespace) {
                end += 1;
            }
            result.push_str(&value[index..end]);
            result.push_str("[已隐藏]");
            while end < bytes.len()
                && !bytes[end].is_ascii_whitespace()
                && !matches!(bytes[end], b'"' | b'\'' | b',' | b';' | b'}')
            {
                end += 1;
            }
            index = end;
            continue;
        }
        let ch = value[index..].chars().next().unwrap();
        result.push(ch);
        index += ch.len_utf8();
    }
    if result.len() > LINE_BYTES {
        let bounded = bound(&result, LINE_BYTES - 32).to_owned();
        result = bounded + " …[日志行已截断]";
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    static SERIAL: AtomicU64 = AtomicU64::new(0);
    struct Root(PathBuf);
    impl Root {
        fn new() -> Self {
            let path = std::env::temp_dir().join(format!(
                "nt-logstore-{}-{}-{}",
                std::process::id(),
                now(),
                SERIAL.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }
    }
    impl Drop for Root {
        fn drop(&mut self) {
            // Only fixed files in this test's verified absolute temp root.
            if self.0.parent() != Some(std::env::temp_dir().as_path())
                || !self
                    .0
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .starts_with("nt-logstore-")
            {
                return;
            }
            for name in [
                "launcher-0.jsonl",
                "launcher-1.jsonl",
                "launcher-2.jsonl",
                "launcher-3.jsonl",
                ".lock",
                ".cursor",
                "blocked",
            ] {
                let _ = fs::remove_file(self.0.join(name));
            }
            let _ = fs::remove_dir(&self.0);
        }
    }
    #[test]
    fn reopen_paginates_retained_logs_and_preserves_original_context_and_time() {
        let root = Root::new();
        let store = LogStore::open(root.0.clone());
        let context = Context {
            run_id: Some("captured-old-run".into()),
            ..Context::workspace(Path::new("C:/workspace-a"), "service")
        };
        let mut written = Vec::new();
        for index in 0..12 {
            written.push(store.record(&format!("INFO row {index}"), &context));
        }
        store.record(
            "INFO other workspace",
            &Context::workspace(Path::new("C:/workspace-b"), "launcher"),
        );
        let reopened = LogStore::open(root.0.clone());
        let page = reopened.read(Some("C:\\workspace-a"), None, 5, None);
        assert!(!page.partial, "{:?}", page.io_error);
        assert_eq!(page.records.len(), 5);
        assert!(page.has_more);
        assert_eq!(page.records.first().unwrap().id, written[7].id);
        let earlier = reopened.read(Some("C:/workspace-a"), page.next_before_seq, 5, None);
        assert_eq!(earlier.records[0].id, written[2].id);
        let oldest = reopened.read(Some("C:/workspace-a"), earlier.next_before_seq, 5, None);
        assert_eq!(oldest.records.len(), 2);
        assert!(!oldest.has_more);
        assert_eq!(oldest.records[0].received_at, written[0].received_at);
        assert_eq!(oldest.records[0].run_id, written[0].run_id);
        assert_eq!(oldest.records[0].source, "service");
        let next = reopened.record("INFO new session", &context);
        assert!(next.seq > written.last().unwrap().seq);
        assert_ne!(next.session_id, written[0].session_id);
        assert_eq!(
            reopened
                .read(None, None, 500, Some(&written[0].session_id))
                .records
                .len(),
            13
        );
    }
    #[test]
    fn rotation_bounds_four_shards_and_keeps_latest_records_after_reopen() {
        let root = Root::new();
        let store = LogStore::with_limit(root.0.clone(), 1024);
        let mut last = None;
        for index in 0..40 {
            last = Some(store.record(
                &format!("INFO {index} {}", "x".repeat(140)),
                &Context::default(),
            ));
        }
        assert!(last.as_ref().unwrap().persisted);
        for index in 0..FILES {
            assert!(fs::metadata(store.file(index)).unwrap().len() <= 1024);
        }
        let reopened = LogStore::with_limit(root.0.clone(), 1024);
        let page = reopened.read(None, None, 500, None);
        assert!(!page.partial, "{:?}", page.io_error);
        assert!(page.records.len() < 40);
        assert!(!page.records.is_empty());
        assert_eq!(page.records.last().unwrap().id, last.unwrap().id);
    }
    #[test]
    fn credentials_are_absent_from_disk_and_live_records_and_long_lines_are_bounded() {
        let root = Root::new();
        let store = LogStore::open(root.0.clone());
        let lines = [
            "proxy http://alice:fake-proxy@host.test/path?token=fake-query",
            "Authorization: Basic ZmFrZS1iYXNpYw==",
            "Cookie: session=fake-cookie-one; auth=fake-cookie-two",
            "token=fake-plain, password=fake-password; HF_TOKEN=fake-hf-token",
            r#"{"api_key":"fake json secret with spaces", "refresh_token": "fake refresh token"}"#,
            "Bearer fake-standalone-bearer",
        ];
        for line in lines {
            let live = store.record(line, &Context::default());
            assert!(live.persisted);
            assert!(live.line.contains("[已隐藏]") || line.starts_with("proxy"));
        }
        let long = store.record(&"中文x".repeat(20000), &Context::default());
        assert!(long.line.len() <= LINE_BYTES);
        assert!(long.line.contains("截断"));
        let ascii = store.record(&"a".repeat(64 * 1024), &Context::default());
        assert!(ascii.line.len() <= LINE_BYTES);
        assert!(ascii.line.contains("截断"));
        let mut all = String::new();
        for index in 0..FILES {
            if let Ok(text) = fs::read_to_string(store.file(index)) {
                all.push_str(&text);
            }
        }
        for secret in [
            "fake-proxy",
            "fake-query",
            "ZmFrZS1iYXNpYw==",
            "fake-cookie-one",
            "fake-cookie-two",
            "fake-plain",
            "fake-password",
            "fake-hf-token",
            "fake json secret with spaces",
            "fake refresh token",
            "fake-standalone-bearer",
        ] {
            assert!(
                !all.contains(secret),
                "credential remained on disk: {secret}"
            );
        }
    }
    #[test]
    fn disk_failure_keeps_live_and_current_memory_with_explicit_partial_status() {
        let root = Root::new();
        let blocked = root.0.join("blocked");
        fs::write(&blocked, b"preserve").unwrap();
        let store = LogStore::open(blocked.clone());
        let record = store.record("INFO still alive token=fake-unwritten", &Context::default());
        assert!(!record.persisted);
        assert_eq!(record.seq, 0);
        assert!(!record.line.contains("fake-unwritten"));
        let page = store.read(None, None, 500, None);
        assert!(page.partial);
        assert!(page.io_error.is_some());
        assert_eq!(page.records[0].id, record.id);
        assert_eq!(fs::read(blocked).unwrap(), b"preserve");
    }
    #[test]
    fn reopened_store_never_reuses_low_or_partially_written_cursor() {
        let root = Root::new();
        let store = LogStore::open(root.0.clone());
        let first = store.record("INFO first", &Context::default());
        let second = store.record("INFO second", &Context::default());
        assert!(second.seq > first.seq);
        fs::write(root.0.join(".cursor"), b"v1:0\n").unwrap();
        let reopened = LogStore::open(root.0.clone());
        let third = reopened.record("INFO third", &Context::default());
        assert!(third.seq > second.seq);
        fs::write(root.0.join(".cursor"), b"v1:1").unwrap();
        let fourth = reopened.record("INFO fourth", &Context::default());
        assert!(fourth.seq > third.seq);
        let page = reopened.read(None, None, 500, None);
        let unique: BTreeSet<_> = page.records.iter().map(|entry| entry.seq).collect();
        assert_eq!(unique.len(), 4);
    }
    #[test]
    fn independent_stores_share_locked_seq_and_busy_disk_does_not_block_logging() {
        let root = Root::new();
        let first = LogStore::open(root.0.clone());
        let second = LogStore::open(root.0.clone());
        let a = first.record("INFO first", &Context::default());
        let b = second.record("INFO second", &Context::default());
        let c = first.record("INFO third", &Context::default());
        assert!(a.seq < b.seq && b.seq < c.seq);
        let disk_lock = first.disk_lock().unwrap();
        let started = Instant::now();
        let failed = second.record("INFO busy disk", &Context::default());
        assert!(started.elapsed() < Duration::from_millis(250));
        assert!(!failed.persisted);
        assert_eq!(failed.seq, 0);
        drop(disk_lock);
        let next = second.record("INFO disk restored", &Context::default());
        assert!(next.persisted);
        assert!(next.seq > c.seq);
    }
    #[test]
    fn unsaved_only_latest_page_still_paginates_into_persisted_history() {
        let root = Root::new();
        let store = LogStore::open(root.0.clone());
        let saved = store.record("INFO earlier saved", &Context::default());
        assert!(saved.persisted);
        let lock = store.disk_lock().unwrap();
        let unsaved = store.record("INFO latest unsaved", &Context::default());
        assert_eq!(unsaved.seq, 0);
        drop(lock);
        let latest = store.read(None, None, 1, None);
        assert_eq!(latest.records[0].id, unsaved.id);
        assert!(latest.has_more);
        assert!(latest.next_before_seq.is_some());
        let older = store.read(None, latest.next_before_seq, 1, None);
        assert_eq!(older.records.len(), 1);
        assert_eq!(older.records[0].id, saved.id);
        assert!(!older.has_more);
    }
}
