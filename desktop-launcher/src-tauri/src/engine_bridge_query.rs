use crate::query_tasks::{
    CleanupProof, QueryError, QueryHandle, QueryObserver, QueryProgress, QueryScope, QueryStage,
    ReaderCleanup, WorkerIdentity,
};
use std::{
    io,
    process::{Child, ChildStderr, ChildStdin, ChildStdout, ExitStatus},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc::{self, Receiver, SyncSender, TrySendError},
        Arc, Mutex,
    },
    thread::JoinHandle,
};

const QUERY_INPUT_LIMIT: usize = 64 * 1024;
const QUERY_RESULT_LIMIT: usize = 4 * 1024 * 1024;
const QUERY_PROGRESS_LIMIT: usize = 16 * 1024;
const QUERY_STDERR_LIMIT: usize = 1024 * 1024;
const QUERY_OUTPUT_LIMIT: usize = 16 * 1024 * 1024;
const QUERY_FRAME_LIMIT: usize = 8192;
static NEXT_QUERY_TEMP: AtomicU64 = AtomicU64::new(0);

/// 后端实际收取资源时生成的审计值；不接受IPC输入，也不替代CleanupProof。
#[derive(Clone, Debug, serde::Serialize)]
pub(super) struct QueryCleanupObservation {
    pub worker: Option<WorkerIdentity>,
    pub child_waited: bool,
    pub job_active_processes: u32,
    pub stdin_closed: bool,
    pub stdout_reader_joined: bool,
    pub stderr_reader_joined: bool,
}

pub(super) struct ManagedQueryOutcome {
    pub result: Result<Value>,
    pub cleanup: Option<CleanupProof>,
    /// 未证明回收时，调用者必须保留 owner 并继续 reap，不能释放查询执行槽。
    pub pending: Option<PendingManagedQuery>,
    pub cleanup_observation: Option<QueryCleanupObservation>,
}
impl ManagedQueryOutcome {
    fn not_started(result: Result<Value>) -> Self {
        Self {
            result,
            cleanup: Some(CleanupProof::no_worker_started()),
            pending: None,
            cleanup_observation: None,
        }
    }
}

/// 只在本次后台执行者中移动；不接受 IPC 构造的回收事实。
pub(super) struct PendingManagedQuery {
    child: Child,
    job: Option<super::Job>,
    never_resumed: bool,
    identity: Option<WorkerIdentity>,
    input: Option<ChildStdin>,
    output: Option<ChildStdout>,
    errors: Option<ChildStderr>,
    writer: Option<JoinHandle<io::Result<()>>>,
    stdout_reader: Option<JoinHandle<io::Result<()>>>,
    stderr_reader: Option<JoinHandle<io::Result<()>>>,
    stop_io: Arc<AtomicBool>,
    io_error: Arc<Mutex<Option<String>>>,
    child_waited: bool,
    termination_requested: bool,
    stdin_closed: bool,
    stdout_joined: bool,
    stderr_joined: bool,
    output_backpressure: Arc<AtomicBool>,
    cleanup_observation: Option<QueryCleanupObservation>,
}

impl PendingManagedQuery {
    fn new(mut child: Child, job: Option<super::Job>, never_resumed: bool) -> Self {
        let input = child.stdin.take();
        let output = child.stdout.take();
        let errors = child.stderr.take();
        let stdin_closed = input.is_none();
        let stdout_joined = output.is_none();
        let stderr_joined = errors.is_none();
        Self {
            child,
            job,
            never_resumed,
            identity: None,
            input,
            output,
            errors,
            writer: None,
            stdout_reader: None,
            stderr_reader: None,
            stop_io: Arc::new(AtomicBool::new(false)),
            io_error: Arc::new(Mutex::new(None)),
            child_waited: false,
            termination_requested: false,
            stdin_closed,
            stdout_joined,
            stderr_joined,
            output_backpressure: Arc::new(AtomicBool::new(false)),
            cleanup_observation: None,
        }
    }

    fn fault(&self) -> Result<()> {
        let fault = self
            .io_error
            .lock()
            .map_err(|_| anyhow::anyhow!("查询管道状态锁异常"))?;
        if let Some(message) = fault.as_ref() {
            bail!("{message}");
        }
        Ok(())
    }

    fn poll_readers(&mut self) {
        fn collect(
            slot: &mut Option<JoinHandle<io::Result<()>>>,
            done: &mut bool,
            fault: &Arc<Mutex<Option<String>>>,
        ) {
            if slot.as_ref().is_some_and(JoinHandle::is_finished) {
                let joined = slot.take().expect("已检查线程存在").join();
                *done = true;
                let error = match joined {
                    Ok(Ok(())) => None,
                    Ok(Err(error)) => Some(format!("查询管道读写失败：{error}")),
                    Err(_) => Some("查询管道线程异常".into()),
                };
                if let Some(error) = error {
                    if let Ok(mut stored) = fault.lock() {
                        stored.get_or_insert(error);
                    }
                }
            }
        }
        collect(&mut self.writer, &mut self.stdin_closed, &self.io_error);
        collect(
            &mut self.stdout_reader,
            &mut self.stdout_joined,
            &self.io_error,
        );
        collect(
            &mut self.stderr_reader,
            &mut self.stderr_joined,
            &self.io_error,
        );
    }

    /// 每次只尝试非阻塞收取，所有 Job/Child/reader 的所有权保留在本对象中。
    pub(super) fn reap(&mut self) -> Result<Option<CleanupProof>> {
        self.stop_io.store(true, Ordering::Release);
        if !self.termination_requested {
            if let Some(job) = self.job.as_ref() {
                job.terminate()?;
            } else if self.never_resumed && self.child.try_wait()?.is_none() {
                self.child
                    .kill()
                    .context("回收尚未运行的挂起查询进程失败")?;
            } else if self.never_resumed { /* 已退出，后续仍实际wait。 */
            } else {
                bail!("查询进程缺少 Job，无法证明回收");
            }
            self.termination_requested = true;
        }
        // 线程没有接走的 pipe 由 owner 实际关闭；已接走的必须等 thread join。
        if self.input.take().is_some() {
            self.stdin_closed = true;
        }
        if self.output.take().is_some() {
            self.stdout_joined = true;
        }
        if self.errors.take().is_some() {
            self.stderr_joined = true;
        }
        if !self.child_waited && self.child.try_wait()?.is_some() {
            self.child.wait().context("等待查询 Child 退出失败")?;
            self.child_waited = true;
        }
        self.poll_readers();
        let active = match self.job.as_ref() {
            Some(job) => job.active_processes()?,
            None if self.never_resumed => 0,
            None => bail!("查询进程缺少 Job 归属"),
        };
        if !self.child_waited
            || active != 0
            || !self.stdin_closed
            || !self.stdout_joined
            || !self.stderr_joined
        {
            return Ok(None);
        }
        self.cleanup_observation = Some(QueryCleanupObservation {
            worker: self.identity.clone(),
            child_waited: self.child_waited,
            job_active_processes: active,
            stdin_closed: self.stdin_closed,
            stdout_reader_joined: self.stdout_joined,
            stderr_reader_joined: self.stderr_joined,
        });
        let identity = match self.identity.clone() {
            Some(identity) => identity,
            None if self.never_resumed => return Ok(Some(CleanupProof::no_worker_started())),
            None => bail!("查询进程身份尚未确认，保留回收现场"),
        };
        Ok(Some(CleanupProof::reaped(
            identity,
            true,
            active,
            ReaderCleanup {
                stdin_closed: self.stdin_closed,
                stdout_reader_joined: self.stdout_joined,
                stderr_reader_joined: self.stderr_joined,
            },
        )?))
    }

    pub(super) fn cleanup_observation(&self) -> Option<QueryCleanupObservation> {
        self.cleanup_observation.clone()
    }

    fn start_io(&mut self, encoded: Vec<u8>) -> Result<Receiver<QueryChunk>> {
        let (sender, receiver) = mpsc::sync_channel(16);
        let stdout = self.output.take().context("查询 worker 缺少 stdout")?;
        self.stdout_reader = match query_reader(
            stdout,
            QueryPipe::Stdout,
            sender.clone(),
            self.stop_io.clone(),
            self.io_error.clone(),
            self.output_backpressure.clone(),
        ) {
            Ok(reader) => Some(reader),
            Err(error) => {
                self.stdout_joined = true;
                return Err(error);
            }
        };
        let stderr = self.errors.take().context("查询 worker 缺少 stderr")?;
        self.stderr_reader = match query_reader(
            stderr,
            QueryPipe::Stderr,
            sender,
            self.stop_io.clone(),
            self.io_error.clone(),
            self.output_backpressure.clone(),
        ) {
            Ok(reader) => Some(reader),
            Err(error) => {
                self.stderr_joined = true;
                return Err(error);
            }
        };
        let mut stdin = self.input.take().context("查询 worker 缺少 stdin")?;
        self.writer = match thread::Builder::new()
            .name("query-stdin".into())
            .spawn(move || {
                let result = stdin.write_all(&encoded);
                drop(stdin);
                result
            }) {
            Ok(writer) => Some(writer),
            Err(error) => {
                self.stdin_closed = true;
                return Err(error).context("创建查询输入线程失败");
            }
        };
        Ok(receiver)
    }
}

impl Drop for PendingManagedQuery {
    fn drop(&mut self) {
        // 正常路径由 reap 提供证明；异常展开仅尽力阻止本 Job 继续运行，不伪造 proof。
        self.stop_io.store(true, Ordering::Release);
        if let Some(job) = self.job.as_ref() {
            let _ = job.terminate();
        } else if self.never_resumed {
            let _ = self.child.kill();
        }
    }
}

#[derive(Clone, Copy)]
enum QueryPipe {
    Stdout,
    Stderr,
}
struct QueryChunk {
    pipe: QueryPipe,
    bytes: Vec<u8>,
}

fn query_reader(
    mut pipe: impl Read + Send + 'static,
    kind: QueryPipe,
    sender: SyncSender<QueryChunk>,
    stop: Arc<AtomicBool>,
    fault: Arc<Mutex<Option<String>>>,
    backpressure: Arc<AtomicBool>,
) -> Result<JoinHandle<io::Result<()>>> {
    thread::Builder::new()
        .name("query-output".into())
        .spawn(move || {
            let result: io::Result<()> = (|| {
                let mut buffer = [0u8; 65_536];
                loop {
                    if stop.load(Ordering::Acquire) {
                        return Ok(());
                    }
                    let length = pipe.read(&mut buffer)?;
                    if length == 0 {
                        return Ok(());
                    }
                    let mut chunk = QueryChunk {
                        pipe: kind,
                        bytes: buffer[..length].to_vec(),
                    };
                    loop {
                        match sender.try_send(chunk) {
                            Ok(()) => break,
                            Err(TrySendError::Full(returned)) => {
                                backpressure.store(true, Ordering::Release);
                                if stop.load(Ordering::Acquire) {
                                    return Ok(());
                                }
                                chunk = returned;
                                thread::sleep(Duration::from_millis(2));
                            }
                            Err(TrySendError::Disconnected(_)) => return Ok(()),
                        }
                    }
                }
            })();
            if let Err(error) = &result {
                if let Ok(mut stored) = fault.lock() {
                    stored.get_or_insert_with(|| format!("查询输出读取失败：{error}"));
                }
            }
            result
        })
        .context("创建查询输出线程失败")
}

struct QueryFrames {
    task_id: String,
    scope: &'static str,
    buffer: Vec<u8>,
    stderr: Vec<u8>,
    output_bytes: usize,
    frame_count: usize,
    last_seq: u64,
    result: Option<Value>,
    stage: QueryStage,
    progress: QueryProgress,
}
impl QueryFrames {
    fn new(task_id: &str, scope: &'static str) -> Self {
        Self {
            task_id: task_id.into(),
            scope,
            buffer: Vec::new(),
            stderr: Vec::new(),
            output_bytes: 0,
            frame_count: 0,
            last_seq: 0,
            result: None,
            stage: QueryStage::Worker,
            progress: QueryProgress {
                message: "等待独立引擎检查".into(),
                ..Default::default()
            },
        }
    }
    fn push(&mut self, chunk: QueryChunk, observer: &QueryObserver) -> Result<()> {
        observer.check()?;
        match chunk.pipe {
            QueryPipe::Stderr => {
                if self.stderr.len().saturating_add(chunk.bytes.len()) > QUERY_STDERR_LIMIT {
                    bail!("查询 stderr 超过1MiB");
                }
                self.stderr.extend_from_slice(&chunk.bytes);
            }
            QueryPipe::Stdout => {
                self.output_bytes = self
                    .output_bytes
                    .checked_add(chunk.bytes.len())
                    .context("查询输出计数溢出")?;
                if self.output_bytes > QUERY_OUTPUT_LIMIT {
                    bail!("查询协议总输出超过16MiB");
                }
                for segment in chunk.bytes.split_inclusive(|byte| *byte == b'\n') {
                    observer.check()?;
                    if self.buffer.len().saturating_add(segment.len()) > QUERY_RESULT_LIMIT {
                        bail!("查询协议帧超过4MiB");
                    }
                    self.buffer.extend_from_slice(segment);
                    if segment.last() == Some(&b'\n') {
                        let bytes = std::mem::take(&mut self.buffer);
                        self.frame(&bytes, observer)?;
                    }
                }
            }
        }
        Ok(())
    }
    fn frame(&mut self, bytes: &[u8], observer: &QueryObserver) -> Result<()> {
        self.frame_count += 1;
        if self.frame_count > QUERY_FRAME_LIMIT || self.result.is_some() {
            bail!("查询协议帧过多或最终结果后仍有输出");
        }
        let value: Value = serde_json::from_slice(bytes).context("查询 worker 返回非法 JSONL")?;
        if value["schema_version"] != 1 || value["task_id"].as_str() != Some(self.task_id.as_str())
        {
            bail!("查询协议 schema 或任务身份不符");
        }
        match value["type"].as_str() {
            Some("progress") => {
                if bytes.len() > QUERY_PROGRESS_LIMIT {
                    bail!("查询进度帧超过16KiB");
                }
                let seq = value["seq"].as_u64().context("查询进度缺少序号")?;
                if seq <= self.last_seq {
                    bail!("查询进度序号未递增");
                }
                self.last_seq = seq;
                self.stage = match value["stage"].as_str() {
                    Some("worker") => QueryStage::Worker,
                    Some("python") => QueryStage::Python,
                    Some("tools") => QueryStage::Tools,
                    Some("receipt") => QueryStage::Receipt,
                    Some("environment") => QueryStage::Environment,
                    Some("source") => QueryStage::Source,
                    Some("extra_files") => QueryStage::ExtraFiles,
                    _ => bail!("查询进度阶段无效"),
                };
                fn number(value: &Value, name: &str) -> Result<Option<u64>> {
                    match value.get(name) {
                        None | Some(Value::Null) => Ok(None),
                        Some(value) => {
                            Ok(Some(value.as_u64().context("查询进度计数不是非负整数")?))
                        }
                    }
                }
                let message = value["message"].as_str().context("查询进度缺少说明")?;
                if message.len() > 4096 {
                    bail!("查询进度说明超过4KiB");
                }
                self.progress = QueryProgress {
                    files: number(&value, "files")?,
                    bytes: number(&value, "bytes")?,
                    total_files: number(&value, "total_files")?,
                    total_bytes: number(&value, "total_bytes")?,
                    message: crate::log_store::redact(message),
                };
                observer.progress(self.stage, self.progress.clone())?;
            }
            Some("result") => {
                if value["scope"].as_str() != Some(self.scope) || !value["ok"].is_boolean() {
                    bail!("查询结果 scope 或成功状态不符");
                }
                self.result = Some(value);
            }
            _ => bail!("查询协议帧类型无效"),
        }
        Ok(())
    }
    fn finish(&mut self, status: ExitStatus) -> Result<Value> {
        if !self.buffer.is_empty() {
            bail!("查询 JSONL 在完整帧前截断");
        }
        let reply = self.result.take().context("查询 worker 未返回最终结果")?;
        if !status.success() || reply["ok"] != true {
            let error = &reply["error"];
            return Err(QueryError::new(
                error["code"].as_str().unwrap_or("query_worker_failed"),
                error["message"].as_str().unwrap_or("独立查询 worker 失败"),
            )
            .into());
        }
        reply.get("result").cloned().context("查询结果缺少 result")
    }
}

fn query_scope(action: &str, scope: QueryScope) -> Result<&'static str> {
    match (action, scope) {
        ("inspect_readonly", QueryScope::Full) | ("capabilities" | "recipe", QueryScope::Full) => {
            Ok("full")
        }
        ("inspect_readonly", QueryScope::FilesOnly) => Ok("files_only"),
        ("plan_install" | "plan_repair", QueryScope::Plan) => Ok("plan"),
        _ => Err(QueryError::new("query_scope_invalid", "此检查范围不适用于目标动作").into()),
    }
}

fn fixed_file_observed(
    layout: &Layout,
    path: &Path,
    bytes: &[u8],
    observer: &QueryObserver,
) -> Result<()> {
    observer.check()?;
    layout.guard_path(path)?;
    let _publish = cache_lease_observed(
        layout,
        &layout.root.join(".launcher-tool-cache-lock"),
        observer,
    )?;
    if path.exists() {
        if !fs::metadata(path)?.is_file() {
            bail!("固定查询工具不是普通文件");
        }
        let mut input = File::open(path)?;
        let mut offset = 0usize;
        let mut buffer = [0; 65_536];
        loop {
            observer.check()?;
            let count = input.read(&mut buffer)?;
            if count == 0 {
                break;
            }
            if bytes.get(offset..offset.saturating_add(count)) != Some(&buffer[..count]) {
                bail!("壳内控制文件已变化，拒绝执行：{}", path.display());
            }
            offset += count;
        }
        if offset != bytes.len() {
            bail!("壳内控制文件长度变化");
        }
        layout.guard_path(path)?;
        return Ok(());
    }
    let parent = path.parent().context("查询工具缺少父目录")?;
    layout.ensure_dir(parent)?;
    let sequence = NEXT_QUERY_TEMP.fetch_add(1, Ordering::Relaxed);
    let temp = parent.join(format!(".query-{}-{sequence}.tmp", std::process::id()));
    layout.guard_path(&temp)?;
    let mut created = false;
    let published: Result<()> = (|| {
        let mut output = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)?;
        created = true;
        for chunk in bytes.chunks(65_536) {
            observer.check()?;
            output.write_all(chunk)?;
        }
        output.sync_all()?;
        drop(output);
        observer.check()?;
        layout.guard_path(path)?;
        if path.exists() {
            bail!("查询固定工具目标在发布前出现，保留现场");
        }
        fs::rename(&temp, path)?;
        Ok(())
    })();
    if created && temp.exists() && layout.guard_path(&temp).is_ok() {
        let _ = fs::remove_file(&temp);
    }
    published
}

fn cache_lease_observed(layout: &Layout, path: &Path, observer: &QueryObserver) -> Result<File> {
    observer.check()?;
    layout.guard_path(path)?;
    layout.ensure_dir(path.parent().context("缓存锁缺少父目录")?)?;
    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(path)?;
    let mut last = Instant::now();
    loop {
        observer.check()?;
        match FileExt::try_lock_exclusive(&file) {
            Ok(()) => return Ok(file),
            Err(error) if error.kind() == fs2::lock_contended_error().kind() => {
                if last.elapsed() >= Duration::from_millis(250) {
                    observer.progress(
                        QueryStage::Tools,
                        QueryProgress {
                            message: "等待固定工具缓存发布锁；可取消".into(),
                            ..Default::default()
                        },
                    )?;
                    last = Instant::now();
                }
                thread::sleep(Duration::from_millis(20));
            }
            Err(error) => return Err(error).context("无法锁定固定查询工具缓存"),
        }
    }
}

fn prepare_query(
    layout: &Layout,
    release: &Release,
    engine: &str,
    action: &str,
    rebuild: bool,
    observer: &QueryObserver,
) -> Result<(PathBuf, PathBuf, Value)> {
    observer.check()?;
    let marker = layout.root.join(".launcher-workspace");
    layout.guard_path(&marker)?;
    if fs::read_to_string(marker)? != model::WORKSPACE_MARKER {
        bail!("只可检查正式启动器工作区");
    }
    crate::scan_observation::with(observer, || super::assert_regular_ready(&layout.root))?;
    observer.check()?;
    let python = crate::python_integrity::verify_observed(layout, observer)?;
    observer.progress(
        QueryStage::Tools,
        QueryProgress {
            message: "核对固定查询工具".into(),
            ..Default::default()
        },
    )?;
    let mut identity = Sha256::new();
    for (name, bytes) in FILES {
        observer.check()?;
        identity.update(name.as_bytes());
        identity.update(Sha256::digest(bytes));
    }
    let directory = layout
        .root
        .join("tools/launcher-worker")
        .join(format!("{:x}", identity.finalize()));
    for (name, bytes) in FILES {
        fixed_file_observed(layout, &directory.join(name), bytes, observer)?;
    }
    let mut input = json!({"schema_version":1,"root":layout.root,"release_id":release.id,"engine_id":engine,"profile_id":layout.profile.file_name().and_then(|s|s.to_str()).context("缺少资料标识")?,"action":action,"rebuild":rebuild});
    if matches!(action, "plan_install" | "plan_repair") {
        let bytes = embedded_lock(engine).context("当前构建缺少该引擎的平台锁")?;
        let sha = hash(bytes);
        let path = layout
            .root
            .join("tools/engine-locks")
            .join(format!("{engine}-{sha}.json"));
        fixed_file_observed(layout, &path, bytes, observer)?;
        input["lock_path"] = json!(path);
        input["lock_sha256"] = json!(sha);
    }
    observer.check()?;
    Ok((python, directory.join("mikazuki/launcher/worker.py"), input))
}

#[allow(clippy::too_many_arguments)]
pub(super) fn query_managed(
    root: &Path,
    release: &Release,
    engine: &str,
    action: &str,
    rebuild: bool,
    scope: QueryScope,
    handle: &QueryHandle,
    log: &Logger,
) -> ManagedQueryOutcome {
    let observer = handle.observer();
    let prepared: Result<_> = (|| {
        observer.check()?;
        engine_id(engine)?;
        let scope = query_scope(action, scope)?;
        let layout = Layout::new(root, &release.id)?;
        let (python, worker, mut input) =
            prepare_query(&layout, release, engine, action, rebuild, &observer)?;
        let remaining = observer
            .deadline()?
            .saturating_duration_since(Instant::now());
        observer.check()?;
        let milliseconds = remaining.as_millis().min(1_800_000) as u64;
        if milliseconds == 0 {
            return Err(QueryError::new("query_timed_out", "查询总期限已到").into());
        }
        input["query_protocol"] = json!({"version":1,"task_id":handle.task_id(),"remaining_ms":milliseconds,"progress":true,"scope":scope});
        let mut encoded = serde_json::to_vec(&input)?;
        encoded.push(b'\n');
        if encoded.len() > QUERY_INPUT_LIMIT {
            bail!("查询请求超过64KiB");
        }
        Ok((python, worker, encoded, scope))
    })();
    let (python, worker, encoded, scope) = match prepared {
        Ok(value) => value,
        Err(error) => return ManagedQueryOutcome::not_started(Err(error)),
    };
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
    run_managed_query_command(&mut command, encoded, scope, handle, log)
}

/// 产品与微型真实进程合同共用执行/回收路径；测试仅替换子进程输入脚本。
fn run_managed_query_command(
    command: &mut Command,
    encoded: Vec<u8>,
    scope: &'static str,
    handle: &QueryHandle,
    log: &Logger,
) -> ManagedQueryOutcome {
    let observer = handle.observer();
    if encoded.len() > QUERY_INPUT_LIMIT {
        return ManagedQueryOutcome::not_started(Err(anyhow::anyhow!("查询请求超过64KiB")));
    }
    if let Err(error) = observer.check() {
        return ManagedQueryOutcome::not_started(Err(error.into()));
    }
    let mut registered_identity = None;
    let spawned = managed_child::spawn_query(command, |child, job| {
        let identity = managed_child::worker_identity(child, job)?;
        handle.attach_worker(identity.clone())?;
        registered_identity = Some(identity);
        observer.check()?;
        Ok(())
    });
    let (mut owner, spawn_error) = match spawned {
        Ok((child, job)) => (PendingManagedQuery::new(child, Some(job), false), None),
        Err(failure) => match failure.child {
            Some(child) => (
                PendingManagedQuery::new(child, failure.job, failure.never_resumed),
                Some(failure.error),
            ),
            None => return ManagedQueryOutcome::not_started(Err(failure.error)),
        },
    };
    owner.identity = registered_identity;
    let mut frames = QueryFrames::new(handle.task_id(), scope);
    let result = (|| {
        if let Some(error) = spawn_error {
            return Err(error);
        }
        observer.check()?;
        let receiver = owner.start_io(encoded)?;
        let mut status = None;
        let mut heartbeat = Instant::now();
        loop {
            observer.check()?;
            while let Ok(chunk) = receiver.try_recv() {
                observer.check()?;
                frames.push(chunk, &observer)?;
            }
            owner.poll_readers();
            owner.fault()?;
            if status.is_none() {
                status = owner.child.try_wait()?;
                if status.is_some() {
                    // 父进程退出后仍持管道的本 Job 子代也须回收。
                    owner
                        .job
                        .as_ref()
                        .context("查询进程缺少 Job")?
                        .terminate()?;
                    owner.termination_requested = true;
                    owner.child.wait().context("等待查询 worker 退出失败")?;
                    owner.child_waited = true;
                }
            }
            if owner.child_waited
                && owner.stdin_closed
                && owner.stdout_joined
                && owner.stderr_joined
            {
                while let Ok(chunk) = receiver.try_recv() {
                    observer.check()?;
                    frames.push(chunk, &observer)?;
                }
                return frames.finish(status.context("查询 worker 缺少退出状态")?);
            }
            if heartbeat.elapsed() >= Duration::from_millis(500) {
                observer.progress(frames.stage, frames.progress.clone())?;
                heartbeat = Instant::now();
            }
            thread::sleep(Duration::from_millis(20));
        }
    })();
    if !frames.stderr.is_empty() {
        log(crate::log_store::redact(&String::from_utf8_lossy(
            &frames.stderr,
        )));
    }
    let _ = observer.progress(
        QueryStage::Reaping,
        QueryProgress {
            message: "正在回收本次查询进程与管道".into(),
            ..Default::default()
        },
    );
    let cleanup_started = Instant::now();
    loop {
        match owner.reap() {
            Ok(Some(proof)) => {
                let result = match (result, owner.fault()) {
                    (Ok(value), Ok(())) => Ok(value),
                    (Ok(_), Err(error)) => Err(error),
                    (Err(error), _) => Err(error),
                };
                return ManagedQueryOutcome {
                    result,
                    cleanup: Some(proof),
                    pending: None,
                    cleanup_observation: owner.cleanup_observation(),
                };
            }
            Ok(None) => {}
            Err(error) => {
                log(crate::log_store::redact(&format!(
                    "查询回收尚未确认：{error:#}"
                )));
                return ManagedQueryOutcome {
                    result: result.and(Err(error)),
                    cleanup: None,
                    pending: Some(owner),
                    cleanup_observation: None,
                };
            }
        }
        if cleanup_started.elapsed() >= Duration::from_secs(10) {
            return ManagedQueryOutcome {
                result: result.and(Err(anyhow::anyhow!(
                    "查询回收超过10秒，保留自有资源等待收尾"
                ))),
                cleanup: None,
                pending: Some(owner),
                cleanup_observation: None,
            };
        }
        thread::sleep(Duration::from_millis(10));
    }
}

#[cfg(all(test, windows))]
mod query_bridge_tests {
    include!("engine_bridge_query_tests.rs");
}
