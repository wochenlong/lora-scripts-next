//! 登记/重建事务的真实GUI入口探测。前置：整个环境已按固定可信索引完成静态与实际验证。
//! 这里只运行固定源码的普通目录副本，所有资料/状态/日志均属于本次事务，不登记生产健康。
use crate::{
    model::{self, Release, WorkspaceMutation},
    operations::CancelToken,
};
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::{self, File},
    io::{Read, Write},
    net::{SocketAddr, TcpListener, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, ExitStatus, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

const ENTRY: &str = "import pathlib,runpy,sys; root=sys.argv.pop(1); sys.path.insert(0,root); sys.argv[0]=str(pathlib.Path(root)/'gui.py'); runpy.run_path(sys.argv[0],run_name='__main__')";
const MAX_HTTP_BYTES: u64 = 16 * 1024 * 1024;

/// 本次验证自己持有的拒绝代理；仅回403、不建立任何上游连接，不等同系统防火墙。
pub(super) struct OfflineProxy {
    address: String,
    stop: Arc<AtomicBool>,
    worker: Option<thread::JoinHandle<()>>,
}
impl OfflineProxy {
    pub(super) fn start() -> Result<Self> {
        let listener = TcpListener::bind(("127.0.0.1", 0))?;
        listener.set_nonblocking(true)?;
        let address = format!("http://{}", listener.local_addr()?);
        let stop = Arc::new(AtomicBool::new(false));
        let worker_stop = stop.clone();
        let worker = thread::spawn(move || {
            while !worker_stop.load(Ordering::Relaxed) {
                match listener.accept() {
                    Ok((mut connection, _)) => {
                        let _ = connection.set_nonblocking(false);
                        let _ = connection.set_read_timeout(Some(Duration::from_millis(150)));
                        let _ = connection.set_write_timeout(Some(Duration::from_millis(150)));
                        let started = Instant::now();
                        let mut headers = Vec::new();
                        let mut buffer = [0; 1024];
                        while headers.len() < 8192 && started.elapsed() < Duration::from_millis(200)
                        {
                            match connection.read(&mut buffer) {
                                Ok(0) | Err(_) => break,
                                Ok(count) => {
                                    headers.extend_from_slice(&buffer[..count]);
                                    if headers.windows(4).any(|part| part == b"\r\n\r\n") {
                                        break;
                                    }
                                }
                            }
                        }
                        let _ = connection.write_all(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n");
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        thread::sleep(Duration::from_millis(10))
                    }
                    Err(_) => break,
                }
            }
        });
        Ok(Self {
            address,
            stop,
            worker: Some(worker),
        })
    }
    fn settings(&self) -> crate::network_policy::Settings {
        crate::network_policy::Settings {
            mode: Some("manual".into()),
            http_proxy: Some(self.address.clone()),
            https_proxy: Some(self.address.clone()),
            no_proxy: Some("localhost,127.0.0.1,::1".into()),
            explicit_nulls: Default::default(),
        }
    }
    pub(super) fn apply_command(&self, command: &mut Command) -> Result<()> {
        // 同时覆盖SDK环境与应用的original环境快照，禁止从继承环境恢复真实代理。
        let removals: Vec<_> = std::env::vars_os()
            .map(|(key, _)| key)
            .chain(command.get_envs().map(|(key, _)| key.to_os_string()))
            .filter(|key| {
                matches!(
                    key.to_string_lossy().to_ascii_lowercase().as_str(),
                    "http_proxy" | "https_proxy" | "all_proxy" | "no_proxy"
                )
            })
            .collect();
        for key in removals {
            command.env_remove(key);
        }
        let mut values = BTreeMap::new();
        for key in [
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        ] {
            command.env(key, &self.address);
            values.insert(key, self.address.as_str());
        }
        for key in ["NO_PROXY", "no_proxy"] {
            command.env(key, "localhost,127.0.0.1,::1");
            values.insert(key, "localhost,127.0.0.1,::1");
        }
        command.env(
            crate::network_policy::ORIGINAL_PROXY_ENV,
            serde_json::to_string(&values)?,
        );
        Ok(())
    }
}
impl Drop for OfflineProxy {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Relaxed);
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct GuiProbeReceipt {
    pub schema_version: u32,
    pub release_id: String,
    pub version: String,
    pub environment: PathBuf,
    pub transaction: String,
    pub workspace: PathBuf,
    pub profile: PathBuf,
    pub state: PathBuf,
    pub pid: u32,
    pub port: u16,
    pub listener_owned: bool,
    pub version_api_success: bool,
    pub homepage_sha256: String,
    pub asset_path: String,
    pub asset_sha256: String,
    pub started_at_ms: u64,
    pub finished_at_ms: u64,
    pub termination_requested: bool,
    pub exit_code: Option<i32>,
    pub child_exited: bool,
    pub listener_gone: bool,
}

struct ProbeProcess {
    child: Child,
    job: Option<super::Job>,
}
impl ProbeProcess {
    fn stop(&mut self) -> Result<ExitStatus> {
        // Windows Job关闭回收本次子孙进程；不枚举/终止其它监听者。
        drop(self.job.take());
        let _ = self.child.kill();
        self.child.wait().context("等待本次GUI探测进程退出失败")
    }
}
impl Drop for ProbeProcess {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}

fn now_ms() -> Result<u64> {
    u64::try_from(SystemTime::now().duration_since(UNIX_EPOCH)?.as_millis())
        .context("入口探测时间超限")
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn read_static(path: &Path) -> Result<Vec<u8>> {
    let metadata = fs::symlink_metadata(path)?;
    if !metadata.is_file() || metadata.len() == 0 || metadata.len() > MAX_HTTP_BYTES {
        bail!("可信静态资源不是16MiB内的普通文件");
    }
    let mut bytes = Vec::new();
    File::open(path)?
        .take(MAX_HTTP_BYTES + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 != metadata.len() {
        bail!("静态资源读取期间长度变化");
    }
    Ok(bytes)
}

/// 仅选取当前首页实际引用的assets下JS/CSS，不接受外部URL、query或路径跳转。
fn asset_from_index(index: &str) -> Result<String> {
    for prefix in ["src=\"", "src='", "href=\"", "href='"] {
        let quote = prefix.chars().last().unwrap();
        for suffix in index.split(prefix).skip(1) {
            let Some((raw, _)) = suffix.split_once(quote) else {
                continue;
            };
            let relative = raw.strip_prefix('/').unwrap_or(raw);
            if !relative.starts_with("assets/")
                || !(relative.ends_with(".js") || relative.ends_with(".css"))
                || !relative
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || b"/._-".contains(&byte))
            {
                continue;
            }
            if relative
                .split('/')
                .any(|part| matches!(part, "" | "." | ".."))
            {
                continue;
            }
            return Ok(relative.into());
        }
    }
    bail!("当前可信前端首页未引用可验证的本地JS/CSS制品")
}

fn get_exact(
    client: &reqwest::blocking::Client,
    port: u16,
    relative: &str,
    expected: &[u8],
) -> Result<String> {
    if expected.is_empty() || expected.len() as u64 > MAX_HTTP_BYTES {
        bail!("入口探测HTTP制品长度无效或超限");
    }
    let response = client
        .get(format!("http://127.0.0.1:{port}/{relative}"))
        .header(reqwest::header::ACCEPT_ENCODING, "identity")
        .send()?;
    if response.status() != reqwest::StatusCode::OK {
        bail!("入口探测首页/资源HTTP状态不是200");
    }
    let mut delivered = Vec::new();
    response
        .take(expected.len() as u64 + 1)
        .read_to_end(&mut delivered)?;
    if delivered != expected {
        bail!("入口探测首页/资源与当前固定实体内容不符");
    }
    Ok(hash(&delivered))
}

fn listener_disappeared(port: u16) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    matches!(TcpStream::connect_timeout(&address, Duration::from_millis(150)), Err(error) if error.kind() == std::io::ErrorKind::ConnectionRefused)
}

fn private_command(
    executable: &Path,
    view: &crate::runtime_view::ProbeView,
    port: u16,
    network: &OfflineProxy,
) -> Result<Command> {
    let config = view.workspace.join("network.local.json");
    model::write_json_atomic(&config, &network.settings())?;
    let temp = view.workspace.join("temp");
    fs::create_dir(&temp)?;
    let mut command = Command::new(executable);
    command.env_clear();
    for name in [
        "SystemRoot",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "SYSTEMDRIVE",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
    ] {
        if let Some(value) = std::env::var_os(name) {
            command.env(name, value);
        }
    }
    // 保留系统动态库搜索路径，GUI解释器目录排首；不继承Python/应用配置变量。
    let mut paths = vec![executable
        .parent()
        .context("GUI解释器没有父目录")?
        .to_path_buf()];
    if let Some(path) = std::env::var_os("PATH") {
        paths.extend(std::env::split_paths(&path));
    }
    command.env("PATH", std::env::join_paths(paths)?);
    network.apply_command(&mut command)?;
    command
        .current_dir(&view.run)
        .args(["-I", "-B", "-c", ENTRY])
        .arg(&view.run)
        .args([
            "--host",
            "127.0.0.1",
            "--port",
            &port.to_string(),
            "--skip-prepare-environment",
            "--skip-prepare-onnxruntime",
            "--disable-tensorboard",
            "--disable-train-monitor",
            "--no-open-browser",
            "--disable-auto-mirror",
            "--port-conflict",
            "error",
        ])
        .env("NEXT_TRAINER_DATA_ROOT", &view.profile)
        .env("NEXT_TRAINER_STATE_ROOT", &view.state)
        .env("NEXT_TRAINER_NETWORK_CONFIG", config)
        .env("PYTHONUTF8", "1")
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("MIKAZUKI_HUB_BACKEND", "huggingface")
        .env("MIKAZUKI_OPEN_BROWSER", "0")
        .env("HF_HUB_OFFLINE", "1")
        .env("TRANSFORMERS_OFFLINE", "1")
        .env("HF_HUB_DISABLE_TELEMETRY", "1")
        .env("UV_OFFLINE", "1")
        .env("UV_PYTHON_DOWNLOADS", "never")
        .env("PIP_NO_INDEX", "1");
    for name in [
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "XDG_CACHE_HOME",
        "HF_HOME",
        "MODELSCOPE_CACHE",
        "TORCH_HOME",
    ] {
        command.env(name, &temp);
    }
    command
        .stdout(Stdio::from(File::create(
            view.workspace.join("stdout.log"),
        )?))
        .stderr(Stdio::from(File::create(
            view.workspace.join("stderr.log"),
        )?));
    Ok(command)
}

/// 只供可信登记/重建事务调用；不替代完整venv静态验证，不写Registry/生产profile/健康。
pub(super) fn probe(
    ctx: &WorkspaceMutation,
    release: &Release,
    environment: &Path,
    transaction: &str,
    log: &super::Logger,
    cancel: &CancelToken,
) -> Result<GuiProbeReceipt> {
    cancel.check()?;
    if !cfg!(windows) {
        bail!("GUI入口探测需要Windows Job与监听PID归属验证");
    }
    let layout = ctx.layout();
    layout.guard_path(environment)?;
    crate::source_integrity::verify(layout, release)?; // 缺release.json时也直接核固定实体。
    let network = OfflineProxy::start()?;
    let view = crate::runtime_view::prepare_probe(layout, transaction)?;
    let mut copied = layout.clone();
    copied.app = view.run.clone();
    crate::source_integrity::verify(&copied, release)?;
    let index_path = view.run.join("frontend/dist/index.html");
    let index = read_static(&index_path)?;
    let asset_path = asset_from_index(std::str::from_utf8(&index)?)?;
    let asset = read_static(&view.run.join("frontend/dist").join(&asset_path))?;
    cancel.check()?;
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    let port = listener.local_addr()?.port();
    drop(listener); // 固定源码--port-conflict error；抢占则监听Job校验不通过。
    let executable = environment.join("Scripts/python.exe");
    layout.guard_path(&executable)?;
    let mut command = private_command(&executable, &view, port, &network)?;
    let started_at_ms = now_ms()?;
    let (child, job) = super::managed_child::spawn(&mut command)?;
    let mut process = ProbeProcess {
        child,
        job: Some(job),
    };
    let pid = process.child.id();
    log(format!(
        "GUI独立入口探测 PID={pid}，端口{port}；事务证据 {}",
        view.workspace.display()
    ));
    let result = (|| -> Result<(String, String)> {
        let client = reqwest::blocking::Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(2))
            .build()?;
        let start = Instant::now();
        while start.elapsed() < Duration::from_secs(180) {
            cancel.check()?;
            if let Some(status) = process.child.try_wait()? {
                bail!("GUI入口探测提前退出：{status}；请查看事务stdout/stderr日志");
            }
            if super::owns_listener(port, process.job.as_ref().context("入口探测Job已关闭")?)
            {
                if let Ok(version) = super::health(port) {
                    if version != release.version {
                        bail!("GUI入口版本与固定发布不符：{version}");
                    }
                    let homepage = get_exact(&client, port, "", &index)?;
                    cancel.check()?;
                    let static_hash = get_exact(&client, port, &asset_path, &asset)?;
                    if !super::owns_listener(
                        port,
                        process.job.as_ref().context("入口探测Job已关闭")?,
                    ) {
                        bail!("GUI入口HTTP检查后监听归属已改变");
                    }
                    cancel.check()?;
                    if start.elapsed() >= Duration::from_secs(180) {
                        bail!("GUI入口探测超时");
                    }
                    return Ok((homepage, static_hash));
                }
            }
            thread::sleep(Duration::from_millis(100));
        }
        bail!("GUI独立入口探测超时")
    })();
    // 所有成功/失败/取消路径先回收本次Job，再等root child；绝不遗留后台入口。
    let stopped = process.stop();
    let stop_start = Instant::now();
    let mut listener_gone = listener_disappeared(port);
    while !listener_gone && stop_start.elapsed() < Duration::from_secs(5) {
        thread::sleep(Duration::from_millis(100));
        listener_gone = listener_disappeared(port);
    }
    let status = stopped.context("GUI入口探测子进程未能确认回收")?;
    if !listener_gone {
        bail!("GUI探测结束后端口仍有监听，拒绝提交验证结果；未终止任何其它进程");
    }
    let (homepage_sha256, asset_sha256) = result?;
    cancel.check()?;
    let receipt = GuiProbeReceipt {
        schema_version: 1,
        release_id: release.id.clone(),
        version: release.version.clone(),
        environment: environment.into(),
        transaction: transaction.into(),
        workspace: view.workspace.clone(),
        profile: view.profile,
        state: view.state,
        pid,
        port,
        listener_owned: true,
        version_api_success: true,
        homepage_sha256,
        asset_path,
        asset_sha256,
        started_at_ms,
        finished_at_ms: now_ms()?,
        termination_requested: true,
        exit_code: status.code(),
        child_exited: true,
        listener_gone,
    };
    model::write_json_atomic(&view.workspace.join("probe-receipt.json"), &receipt)?;
    log(format!(
        "GUI独立入口与当前静态资源验证通过，本次Job已回收：{}",
        view.workspace.display()
    ));
    Ok(receipt)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn selects_current_local_asset_and_refuses_external_and_traversal_references() {
        assert_eq!(
            asset_from_index("<script src=\"/assets/index-real.js\"></script>").unwrap(),
            "assets/index-real.js"
        );
        assert_eq!(
            asset_from_index("<link href='assets/app.css'>").unwrap(),
            "assets/app.css"
        );
        for html in [
            "<script src=\"https://external.test/assets/app.js\">",
            "<script src=\"/assets/../app.js\">",
            "<script src=\"/assets/%2e%2e/app.js\">",
            "<script src=\"/assets/app.js?token=x\">",
        ] {
            assert!(asset_from_index(html).is_err());
        }
    }

    #[test]
    fn owned_proxy_rejects_external_http_and_connect_without_upstream_and_freezes_child_env() {
        let proxy = OfflineProxy::start().unwrap();
        let client = reqwest::blocking::Client::builder()
            .no_proxy()
            .proxy(reqwest::Proxy::all(&proxy.address).unwrap())
            .timeout(Duration::from_secs(2))
            .build()
            .unwrap();
        let response = client.get("http://probe.invalid/blocked").send().unwrap();
        assert_eq!(response.status(), reqwest::StatusCode::FORBIDDEN);
        assert!(client.get("https://probe.invalid/blocked").send().is_err());
        let mut command = Command::new("unused-static-test");
        proxy.apply_command(&mut command).unwrap();
        let variables: BTreeMap<_, _> = command
            .get_envs()
            .filter_map(|(key, value)| {
                value.map(|value| {
                    (
                        key.to_string_lossy().to_ascii_lowercase(),
                        value.to_string_lossy().into_owned(),
                    )
                })
            })
            .collect();
        for key in ["http_proxy", "https_proxy", "all_proxy"] {
            assert_eq!(variables[key], proxy.address);
        }
        assert_eq!(variables["no_proxy"], "localhost,127.0.0.1,::1");
        let settings = proxy.settings();
        assert_eq!(settings.mode.as_deref(), Some("manual"));
        assert_eq!(settings.http_proxy.as_deref(), Some(proxy.address.as_str()));
        assert_eq!(
            settings.https_proxy.as_deref(),
            Some(proxy.address.as_str())
        );
        let original: BTreeMap<String, String> = serde_json::from_str(
            &variables[&crate::network_policy::ORIGINAL_PROXY_ENV.to_ascii_lowercase()],
        )
        .unwrap();
        assert_eq!(original["ALL_PROXY"], proxy.address);
        assert_eq!(original["all_proxy"], proxy.address);
    }
}
