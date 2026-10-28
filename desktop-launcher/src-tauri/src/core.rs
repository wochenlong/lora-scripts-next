use crate::model::{self, Catalog, Journal, Layout, Phase, Registry, Release, ReleaseReceipt};
use crate::runtime_view;
use anyhow::{anyhow, bail, Context, Result};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs::{self, File},
    io::{BufRead, BufReader, Read},
    net::TcpListener,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

pub type Logger = Arc<dyn Fn(String) + Send + Sync>;
const REQUIRED: &[&str] = &[
    "gui.py",
    "requirements.txt",
    "VERSION",
    "frontend/dist/index.html",
];

#[derive(Serialize)]
pub struct Check {
    name: String,
    ok: bool,
    detail: String,
}
#[derive(Serialize)]
pub struct Report {
    root: String,
    uv: bool,
    python: bool,
    source: bool,
    environment: bool,
    frontend: bool,
    running: bool,
    healthy: bool,
    version: Option<String>,
    port: Option<u16>,
    checks: Vec<Check>,
    logs: Vec<String>,
    current_release: Option<String>,
    previous_known_good: Option<String>,
    profile_path: String,
    versions: Vec<VersionView>,
    interrupted: Vec<String>,
}
#[derive(Serialize)]
pub struct VersionView {
    id: String,
    channel: String,
    version: String,
    commit: String,
    download_bytes: u64,
    source_bytes: u64,
    installed: bool,
    source_ok: bool,
    environment_ok: bool,
    current: bool,
    known_good: bool,
}

pub struct Engine {
    pub default_root: PathBuf,
    running: Option<Running>,
    logger: Logger,
    catalog: Catalog,
}

struct Running {
    child: Child,
    root: PathBuf,
    port: u16,
    _job: Job,
    // Fields drop in declaration order: close the process group before releasing the workspace lock.
    _lease: File,
}

impl Drop for Running {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        // Closing the Job Object terminates only children assigned to this launcher.
    }
}

#[cfg(windows)]
struct Job(windows_sys::Win32::Foundation::HANDLE);
#[cfg(windows)]
unsafe impl Send for Job {}
#[cfg(windows)]
impl Job {
    fn contains(&self, pid: u32) -> bool {
        use windows_sys::Win32::{
            Foundation::CloseHandle,
            System::{
                JobObjects::IsProcessInJob,
                Threading::{OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION},
            },
        };
        unsafe {
            let process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
            if process.is_null() {
                return false;
            }
            let mut member = 0;
            let success = IsProcessInJob(process, self.0, &mut member);
            CloseHandle(process);
            success != 0 && member != 0
        }
    }
    fn attach(child: &Child) -> Result<Self> {
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::{Foundation::CloseHandle, System::JobObjects::*};
        unsafe {
            let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if handle.is_null() {
                bail!("创建受管进程 Job Object 失败");
            }
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                &info as *const _ as _,
                std::mem::size_of_val(&info) as u32,
            ) == 0
                || AssignProcessToJobObject(handle, child.as_raw_handle() as _) == 0
            {
                CloseHandle(handle);
                bail!("绑定受管进程失败，已拒绝无归属运行");
            }
            Ok(Self(handle))
        }
    }
}
#[cfg(windows)]
impl Drop for Job {
    fn drop(&mut self) {
        unsafe {
            windows_sys::Win32::Foundation::CloseHandle(self.0);
        }
    }
}
#[cfg(not(windows))]
struct Job;
#[cfg(not(windows))]
impl Job {
    fn attach(_: &Child) -> Result<Self> {
        Ok(Self)
    }
}

fn hidden(command: &mut Command) -> &mut Command {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    command
}
fn stamp() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}
fn source(layout: &Layout) -> PathBuf {
    layout.app.clone()
}
fn env_python(layout: &Layout) -> PathBuf {
    layout.environment.join("Scripts/python.exe")
}
fn uv(root: &Path) -> PathBuf {
    root.join("tools/uv.exe")
}
fn digest(path: &Path) -> Result<String> {
    let mut f = File::open(path)?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 65536];
    loop {
        let n = f.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        hash.update(&buffer[..n]);
    }
    Ok(format!("{:x}", hash.finalize()))
}

fn download(root: &Path, url: &str, name: &str, expected: &str, log: &Logger) -> Result<PathBuf> {
    let target = root.join("cache").join(name);
    if target.is_file() && digest(&target)? == expected {
        log(format!("已校验缓存：{name}"));
        return Ok(target);
    }
    log(format!("下载 {url}"));
    let partial = target.with_extension(format!("{}.part", stamp()));
    let mut response = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(600))
        .build()?
        .get(url)
        .send()?
        .error_for_status()?;
    if response.content_length().unwrap_or(0) > model::MAX_DOWNLOAD_BYTES {
        bail!("资产超出启动器下载上限");
    }
    let mut output = File::create(&partial)?;
    let bytes = std::io::copy(
        &mut response.by_ref().take(model::MAX_DOWNLOAD_BYTES + 1),
        &mut output,
    )?;
    output.sync_all()?;
    if bytes > model::MAX_DOWNLOAD_BYTES || digest(&partial)? != expected {
        bail!(
            "下载文件校验失败，未执行或替换任何现有程序；可重试。临时文件: {}",
            partial.display()
        );
    }
    if target.exists() {
        fs::rename(
            &target,
            target.with_extension(format!("{}.invalid", stamp())),
        )?;
    }
    fs::rename(partial, &target)?;
    log(format!("下载完成并通过 SHA256，{} 字节", bytes));
    Ok(target)
}

fn extract(zip_path: &Path, destination: &Path, strip_root: bool) -> Result<()> {
    let mut archive = zip::ZipArchive::new(File::open(zip_path)?)?;
    let mut total = 0u64;
    for i in 0..archive.len() {
        let mut entry = archive.by_index(i)?;
        total = total.checked_add(entry.size()).context("归档体积溢出")?;
        if total > model::MAX_EXTRACT_BYTES {
            bail!("归档解压体积超过启动器上限");
        }
        let relative = entry.enclosed_name().context("归档包含非法路径")?;
        if entry
            .unix_mode()
            .is_some_and(|mode| mode & 0o170000 == 0o120000)
        {
            bail!("启动器不接受归档符号链接");
        }
        let relative = if strip_root {
            relative.components().skip(1).collect::<PathBuf>()
        } else {
            relative
        };
        if relative.as_os_str().is_empty() {
            continue;
        }
        let target = destination.join(relative);
        if entry.is_dir() {
            fs::create_dir_all(target)?;
        } else {
            fs::create_dir_all(target.parent().context("缺少目标父目录")?)?;
            std::io::copy(&mut entry, &mut File::create(target)?)?;
        }
    }
    Ok(())
}

fn manifest(directory: &Path) -> Result<BTreeMap<String, String>> {
    fn walk(base: &Path, path: &Path, files: &mut BTreeMap<String, String>) -> Result<()> {
        for entry in fs::read_dir(path)? {
            let entry = entry?;
            if entry.file_type()?.is_dir() {
                walk(base, &entry.path(), files)?;
            } else if entry.file_type()?.is_file() {
                let p = entry.path();
                let rel = p.strip_prefix(base)?.to_string_lossy().replace('\\', "/");
                // Runtime-owned config/logs may change; tracked code and packaged frontend must match.
                if rel.ends_with(".py")
                    || rel.starts_with("frontend/dist/")
                    || REQUIRED.contains(&rel.as_str())
                {
                    files.insert(rel, digest(&p)?);
                }
            }
        }
        Ok(())
    }
    let mut files = BTreeMap::new();
    walk(directory, directory, &mut files)?;
    Ok(files)
}
fn verify_source(layout: &Layout, release: &Release) -> Result<()> {
    layout.guard_path(&layout.app)?;
    let receipt = ReleaseReceipt::load(&layout.release_dir)?;
    if receipt.release != *release {
        bail!("本地发布清单不匹配");
    }
    let dir = source(layout);
    let entries: BTreeMap<String, String> =
        serde_json::from_slice(&fs::read(dir.join(".source-integrity.json"))?)?;
    if entries.is_empty()
        || release
            .required_files
            .iter()
            .any(|p| !entries.contains_key(p))
    {
        bail!("源码完整性清单无效");
    }
    for (rel, expected) in entries {
        let p = Path::new(&rel);
        if p.is_absolute()
            || p.components()
                .any(|c| !matches!(c, std::path::Component::Normal(_)))
        {
            bail!("源码完整性清单含非法路径");
        }
        layout.guard_path(&dir.join(p))?;
        if digest(&dir.join(p)).ok().as_deref() != Some(expected.as_str()) {
            bail!("源码文件缺失或改变：{rel}");
        }
    }
    Ok(())
}

fn uv_command(root: &Path, release: &Release) -> Command {
    let mut command = Command::new(uv(root));
    command
        .env(
            "UV_PYTHON_INSTALL_DIR",
            root.join("python").join(&release.python),
        )
        .env("UV_CACHE_DIR", root.join("cache/uv"))
        .env("UV_NO_CONFIG", "1")
        .env("UV_PYTHON_BIN_DIR", root.join("tools"))
        .env("UV_NO_PROGRESS", "1");
    hidden(&mut command);
    command
}
fn managed_python(root: &Path, release: &Release) -> Result<PathBuf> {
    let layout = Layout::new(root, &release.id)?;
    layout.guard_path(&uv(root))?;
    layout.guard_path(&root.join("python").join(&release.python))?;
    if digest(&uv(root)).ok().as_deref() != Some(release.uv.exe_sha256.as_str()) {
        bail!("自管 uv 缺失或校验失败，请重新准备基础工具");
    }
    let out = uv_command(root, release)
        .args([
            "python",
            "find",
            "--managed-python",
            "--no-python-downloads",
            "--no-project",
            &release.python,
        ])
        .output()?;
    if !out.status.success() {
        bail!("自管 Python {} 缺失或损坏", release.python);
    }
    let path = PathBuf::from(String::from_utf8(out.stdout)?.trim());
    layout.guard_path(&path)?;
    if !path
        .canonicalize()?
        .starts_with(root.join("python").join(&release.python).canonicalize()?)
    {
        bail!("解释器位于自管目录外，拒绝使用系统 Python");
    }
    let result = hidden(
        Command::new(&path)
            .args([
                "-I",
                "-c",
                "import sys; assert sys.version.split()[0] == sys.argv[1]",
            ])
            .arg(&release.python),
    )
    .status()?;
    if !result.success() {
        bail!("自管 Python 运行检查失败");
    }
    Ok(path)
}
// uv 在受管 Python 根中创建版本别名联接。只允许其最终目标仍在同一受管版本内。
fn managed_base_path(layout: &Layout, release: &Release, path: &Path) -> Result<PathBuf> {
    let managed = layout.root.join("python").join(&release.python);
    layout.guard_path(&managed)?;
    let relative = path
        .strip_prefix(&managed)
        .context("虚拟环境指向自管目录外的 Python")?;
    for component in relative.components() {
        match component {
            std::path::Component::Normal(name) => {
                model::validate_component(&name.to_string_lossy())?;
            }
            _ => bail!("环境 Python 路径包含非法跳转"),
        }
    }
    let resolved = path.canonicalize()?;
    let managed_resolved = managed.canonicalize()?;
    let inside = resolved
        .strip_prefix(&managed_resolved)
        .context("虚拟环境 Python 联接目标位于自管版本目录外")?;
    // Windows canonicalize 返回带 \\?\ 前缀的路径；映回已检查根以复用路径链保护。
    layout.guard_path(&managed.join(inside))?;
    Ok(resolved)
}
fn check_environment(layout: &Layout, release: &Release) -> Result<()> {
    layout.guard_path(&layout.environment)?;
    layout.guard_path(&env_python(layout))?;
    let config = layout.environment.join("pyvenv.cfg");
    layout.guard_path(&config)?;
    let config = fs::read_to_string(config).context("虚拟环境配置缺失")?;
    let entries: BTreeMap<_, _> = config
        .lines()
        .filter_map(|line| line.split_once('=').map(|(k, v)| (k.trim(), v.trim())))
        .collect();
    if entries.get("include-system-site-packages") != Some(&"false")
        || entries.get("version_info") != Some(&release.python.as_str())
    {
        bail!("环境 Python 版本不匹配或启用了系统依赖，请单独修复环境");
    }
    let managed = layout.root.join("python").join(&release.python);
    layout.guard_path(&managed)?;
    let base = PathBuf::from(entries.get("home").context("环境未声明自管 Python home")?);
    managed_base_path(layout, release, &base)?;
    for key in ["base-executable", "base-prefix", "base-exec-prefix"] {
        if let Some(value) = entries.get(key) {
            let path = PathBuf::from(value);
            managed_base_path(layout, release, &path)
                .with_context(|| format!("虚拟环境 {key} 路径不受信任"))?;
        }
    }
    let script = "import sys,pathlib,os; expected=pathlib.Path(sys.argv[1]).resolve(); assert sys.version.split()[0] == sys.argv[2]; assert pathlib.Path(sys.base_prefix).resolve().is_relative_to(expected); assert pathlib.Path(sys._base_executable).resolve().is_relative_to(expected); import pip,fastapi,uvicorn,toml,numpy,onnxruntime,psutil,pandas,PIL,cv2,tensorboard,rich,requests,httpx,aiohttp,websockets,multipart,modelscope,cryptography,huggingface_hub,pynvml; from importlib.metadata import version; assert version('numpy') == '1.26.4'";
    let result = hidden(
        Command::new(env_python(layout))
            .args(["-I", "-c", script])
            .arg(managed)
            .arg(&release.python),
    )
    .output()?;
    if !result.status.success() {
        bail!("{}", String::from_utf8_lossy(&result.stderr));
    }
    Ok(())
}
fn execute(mut command: Command, log: &Logger) -> Result<()> {
    log(format!("执行 {:?}", command.get_program()));
    let mut child = command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    let _job = match Job::attach(&child) {
        Ok(job) => job,
        Err(e) => {
            let _ = child.kill();
            let _ = child.wait();
            return Err(e);
        }
    };
    let threads: Vec<_> = [
        child
            .stdout
            .take()
            .map(|s| Box::new(s) as Box<dyn Read + Send>),
        child
            .stderr
            .take()
            .map(|s| Box::new(s) as Box<dyn Read + Send>),
    ]
    .into_iter()
    .flatten()
    .map(|pipe| {
        let logger = log.clone();
        thread::spawn(move || {
            for line in BufReader::new(pipe).lines().map_while(Result::ok) {
                logger(line);
            }
        })
    })
    .collect();
    let status = child.wait()?;
    for t in threads {
        let _ = t.join();
    }
    if !status.success() {
        bail!("子任务失败（{status}），请检查日志后重试");
    }
    Ok(())
}

impl Engine {
    pub fn new(default_root: PathBuf, logger: Logger) -> Self {
        Self {
            default_root,
            running: None,
            logger,
            catalog: Catalog::embedded().expect("内置发布清单必须有效"),
        }
    }
    pub fn resolve(&self, value: &str) -> Result<PathBuf> {
        let root = if value.trim().is_empty() {
            self.default_root.clone()
        } else {
            PathBuf::from(value.trim())
        };
        Layout::new(&root, &self.default_release().id)?;
        Ok(root)
    }
    fn default_release(&self) -> &Release {
        self.catalog
            .releases()
            .iter()
            .find(|r| r.channel == "dev")
            .unwrap_or(&self.catalog.releases()[0])
    }
    fn active(&self, root: &Path) -> Result<Release> {
        let registry = Registry::load(root)?;
        self.catalog
            .release(
                registry
                    .current
                    .as_deref()
                    .unwrap_or(&self.default_release().id),
            )
            .cloned()
    }
    fn mutable(&mut self, root: &Path, release: &Release) -> Result<(Layout, File)> {
        self.reap();
        if self.running.is_some() {
            bail!("请先停止受管训练器，再修改安装目录");
        }
        let layout = Layout::new(root, &release.id)?;
        let lease = layout.prepare_workspace()?;
        let mut registry = Registry::load(root)?;
        if !registry.reconcile(root, &self.catalog)?.is_empty() {
            registry.store(root)?;
        }
        Ok((layout, lease))
    }
    fn reap(&mut self) {
        if self
            .running
            .as_mut()
            .is_some_and(|r| !matches!(r.child.try_wait(), Ok(None)))
        {
            self.running.take();
        }
    }
    pub fn inspect(&mut self, root: &Path) -> Result<Report> {
        self.reap();
        let registry = Registry::load(root)?;
        let release = self.active(root)?;
        let layout = Layout::new(root, &release.id)?;
        layout.guard_path(&uv(root))?;
        layout.guard_path(&root.join("python"))?;
        let owned = fs::read_to_string(root.join(".launcher-workspace"))
            .is_ok_and(|v| v == model::WORKSPACE_MARKER);
        if owned && layout.profile.join("profile.json").exists() {
            model::Profile::load(&layout.profile.join("profile.json"))?;
        }
        let uv_ok =
            owned && digest(&uv(root)).ok().as_deref() == Some(release.uv.exe_sha256.as_str());
        let python = if uv_ok {
            managed_python(root, &release)
        } else {
            Err(anyhow!("请准备自管基础工具"))
        };
        let src = if owned {
            verify_source(&layout, &release)
        } else {
            Err(anyhow!("尚未安装训练器"))
        };
        let environment = if owned {
            check_environment(&layout, &release)
        } else {
            Err(anyhow!("尚未安装主程序环境"))
        };
        let frontend = src.is_ok() && layout.app.join("frontend/dist/index.html").is_file();
        let r = self.running.as_ref().filter(|r| r.root == root);
        let port = r.map(|r| r.port);
        let served_version = r.and_then(|r| {
            if owns_listener(r.port, &r._job) {
                health(r.port).ok()
            } else {
                None
            }
        });
        let check = |name: &str, result: &Result<()>| Check {
            name: name.into(),
            ok: result.is_ok(),
            detail: result
                .as_ref()
                .err()
                .map(|e| format!("{e:#}"))
                .unwrap_or_else(|| "实际文件及运行检查通过".into()),
        };
        let mut versions = Vec::new();
        for release in self.catalog.releases() {
            let l = Layout::new(root, &release.id)?;
            let source_ok = owned && verify_source(&l, release).is_ok();
            let environment_ok = owned && check_environment(&l, release).is_ok();
            versions.push(VersionView {
                id: release.id.clone(),
                channel: release.channel.clone(),
                version: release.version.clone(),
                commit: release.commit.clone(),
                download_bytes: release.archive.bytes,
                source_bytes: release.archive.unpacked_bytes,
                installed: owned
                    && ReleaseReceipt::load(&l.release_dir)
                        .is_ok_and(|receipt| receipt.release == *release),
                source_ok,
                environment_ok,
                current: registry.current.as_deref() == Some(&release.id),
                known_good: registry
                    .installed
                    .iter()
                    .any(|i| i.release_id == release.id && i.healthy_at.is_some()),
            });
        }
        let interrupted = Journal::load_all(root)?
            .into_iter()
            .filter(|j| j.phase != Phase::Committed)
            .map(|j| {
                format!(
                    "{}: {:?}；请重试相应安装或修复，当前版本指针未自动更改",
                    j.release_id, j.phase
                )
            })
            .collect();
        Ok(Report {
            root: root.to_string_lossy().into(),
            uv: uv_ok,
            python: python.is_ok(),
            source: src.is_ok(),
            environment: environment.is_ok(),
            frontend,
            running: r.is_some(),
            healthy: served_version.is_some(),
            version: served_version.or_else(|| {
                if src.is_ok() {
                    Some(release.version.clone())
                } else {
                    None
                }
            }),
            port,
            logs: vec![],
            current_release: registry.current,
            previous_known_good: registry.previous_known_good,
            profile_path: layout.profile.to_string_lossy().into(),
            versions,
            interrupted,
            checks: vec![
                Check {
                    name: "自管 uv".into(),
                    ok: uv_ok,
                    detail: uv(root).display().to_string(),
                },
                check("自管 Python", &python.map(|_| ())),
                check("当前版本源码", &src),
                check("主程序依赖与解释器", &environment),
                Check {
                    name: "训练器前端".into(),
                    ok: frontend,
                    detail: layout
                        .app
                        .join("frontend/dist/index.html")
                        .display()
                        .to_string(),
                },
            ],
        })
    }
    pub fn bootstrap(&mut self, root: &Path) -> Result<Report> {
        let release = self.active(root)?;
        self.bootstrap_for(root, &release)?;
        self.inspect(root)
    }
    fn bootstrap_for(&mut self, root: &Path, release: &Release) -> Result<()> {
        let (layout, _lease) = self.mutable(root, release)?;
        let asset = &release.uv;
        if managed_python(root, release).is_ok() {
            return Ok(());
        }
        let archive = download(
            root,
            &asset.url,
            &format!("{}.zip", asset.sha256),
            &asset.sha256,
            &self.logger,
        )?;
        let staging = root.join(format!("staging/uv-{}", stamp()));
        layout.ensure_dir(&staging)?;
        extract(&archive, &staging, false)?;
        let exe = staging.join("uv.exe");
        if digest(&exe)? != asset.exe_sha256 {
            bail!("uv 二进制哈希不匹配");
        }
        let dest = uv(root);
        layout.guard_path(&dest)?;
        if dest.exists() {
            fs::rename(&dest, root.join(format!("backups/uv-{}.exe", stamp())))?;
        }
        fs::copy(exe, dest)?;
        let python_root = root.join("python").join(&release.python);
        layout.ensure_dir(&python_root)?;
        if managed_python(root, release).is_err() && fs::read_dir(&python_root)?.next().is_some() {
            fs::rename(
                &python_root,
                root.join(format!("backups/python-{}-{}", release.python, stamp())),
            )?;
            layout.ensure_dir(&python_root)?;
        }
        let mut command = uv_command(root, release);
        command.args([
            "python",
            "install",
            &release.python,
            "--no-bin",
            "--no-registry",
        ]);
        execute(command, &self.logger)?;
        managed_python(root, release)?;
        (self.logger)("基础工具实际检查通过".into());
        Ok(())
    }
    pub fn restore(&mut self, root: &Path) -> Result<Report> {
        let release = self.active(root)?;
        self.restore_for(root, &release)?;
        self.inspect(root)
    }
    fn restore_for(&mut self, root: &Path, release: &Release) -> Result<()> {
        let (layout, _lease) = self.mutable(root, release)?;
        if verify_source(&layout, release).is_ok() {
            let mut registry = Registry::load(root)?;
            registry.record_installed(release)?;
            registry.store(root)?;
            (self.logger)("已安装源码完整，复用当前版本；没有下载".into());
            return Ok(());
        }
        let mut journal = Journal::new(&release.id)?;
        journal.store(root)?;
        let archive = download(
            root,
            &release.archive.url,
            &format!("{}.zip", release.archive.sha256),
            &release.archive.sha256,
            &self.logger,
        )?;
        let staging = root.join(format!("staging/{}-{}", release.id, stamp()));
        layout.ensure_dir(&staging.join("app"))?;
        extract(&archive, &staging.join("app"), true)?;
        for file in &release.required_files {
            if !staging.join("app").join(file).is_file() {
                bail!("归档缺少 {file}");
            }
        }
        if fs::read_to_string(staging.join("app/VERSION"))?.trim() != release.version {
            bail!("归档版本与安装清单不符");
        }
        model::write_json_atomic(
            &staging.join("app/.source-integrity.json"),
            &manifest(&staging.join("app"))?,
        )?;
        ReleaseReceipt::new(release).store(&staging)?;
        journal.phase = Phase::Verified;
        journal.store(root)?;
        let backup = root.join(format!("backups/source-{}-{}", release.id, stamp()));
        layout.guard_path(&layout.release_dir)?;
        if layout.release_dir.exists() {
            fs::rename(&layout.release_dir, &backup)?;
        }
        journal.phase = Phase::Committing;
        journal.store(root)?;
        if let Err(error) = fs::rename(&staging, &layout.release_dir) {
            if backup.exists() {
                let _ = fs::rename(&backup, &layout.release_dir);
            }
            return Err(error).context("发布版本失败，已尝试保留原版本");
        }
        verify_source(&layout, release)?;
        let mut registry = Registry::load(root)?;
        registry.record_installed(release)?;
        registry.store(root)?;
        journal.phase = Phase::Committed;
        journal.store(root)?;
        (self.logger)(format!("{} 源码恢复完成；用户资料未移动", release.id));
        Ok(())
    }
    pub fn install_environment(&mut self, root: &Path) -> Result<Report> {
        let release = self.active(root)?;
        self.environment_for(root, &release)?;
        self.inspect(root)
    }
    fn environment_for(&mut self, root: &Path, release: &Release) -> Result<()> {
        let (layout, _lease) = self.mutable(root, release)?;
        verify_source(&layout, release)?;
        let python = managed_python(root, release)?;
        if check_environment(&layout, release).is_ok() {
            // 可能中断于成功安装之后、日志提交之前。源码和环境都已实测，重试可完成事务。
            let mut journal = Journal::new(&release.id)?;
            journal.phase = Phase::Committed;
            journal.store(root)?;
            return Ok(());
        }
        let mut journal = Journal::new(&release.id)?;
        journal.store(root)?;
        layout.guard_path(&layout.environment)?;
        if layout.environment.exists() {
            fs::rename(
                &layout.environment,
                root.join(format!("backups/environment-{}-{}", release.id, stamp())),
            )?;
        }
        layout.ensure_dir(layout.environment.parent().context("缺少环境父路径")?)?;
        let mut command = uv_command(root, release);
        command
            .args(["venv", "--seed", "--python"])
            .arg(python)
            .arg(&layout.environment);
        execute(command, &self.logger)?;
        let mut command = uv_command(root, release);
        command
            .args(["pip", "install", "--python"])
            .arg(env_python(&layout))
            .arg("-r")
            .arg(layout.app.join("requirements.txt"));
        execute(command, &self.logger)?;
        check_environment(&layout, release).context("安装后的实际依赖导入失败")?;
        journal.phase = Phase::Committed;
        journal.store(root)?;
        Ok(())
    }
    pub fn install_release(&mut self, root: &Path, id: &str) -> Result<Report> {
        let release = self.catalog.release(id)?.clone();
        self.bootstrap_for(root, &release)?;
        self.restore_for(root, &release)?;
        self.environment_for(root, &release)?;
        let (_layout, _lease) = self.mutable(root, &release)?;
        let mut registry = Registry::load(root)?;
        if registry.current.is_none() {
            registry.activate(id)?;
            registry.store(root)?;
        }
        self.inspect(root)
    }
    pub fn select_release(&mut self, root: &Path, id: &str) -> Result<Report> {
        let release = self.catalog.release(id)?.clone();
        let (layout, _lease) = self.mutable(root, &release)?;
        verify_source(&layout, &release)?;
        check_environment(&layout, &release)?;
        managed_python(root, &release)?;
        let mut registry = Registry::load(root)?;
        registry.activate(id)?;
        registry.store(root)?;
        (self.logger)(format!("切换到 {id}；复用本地版本，没有下载"));
        self.inspect(root)
    }
    pub fn rollback_release(&mut self, root: &Path) -> Result<Report> {
        let mut registry = Registry::load(root)?;
        let id = registry.rollback(&self.catalog)?;
        self.select_release(root, &id)
    }
    pub fn remove_release(&mut self, root: &Path, id: &str) -> Result<Report> {
        let release = self.catalog.release(id)?.clone();
        let (layout, _lease) = self.mutable(root, &release)?;
        let mut registry = Registry::load(root)?;
        if registry.current.as_deref() == Some(id)
            || registry.previous_known_good.as_deref() == Some(id)
        {
            bail!("当前版本和保留的回退版本不可删除");
        }
        for (name, dir) in [
            ("source", &layout.release_dir),
            ("environment", &layout.environment),
            ("view", &layout.run),
        ] {
            layout.guard_path(dir)?;
            if dir.exists() {
                fs::rename(
                    dir,
                    root.join(format!("backups/removed-{name}-{id}-{}", stamp())),
                )?;
            }
        }
        registry.installed.retain(|i| i.release_id != id);
        registry.store(root)?;
        (self.logger)("版本文件已移到备份；用户资料和兼容状态保留".into());
        self.inspect(root)
    }
    pub fn start(&mut self, root: &Path) -> Result<Report> {
        let release = self.active(root)?;
        let (layout, lock) = self.mutable(root, &release)?;
        if Registry::load(root)?.current.is_none() {
            bail!("请先选择已安装版本");
        }
        verify_source(&layout, &release)?;
        check_environment(&layout, &release)?;
        runtime_view::prepare(&layout, &release)?;
        (self.logger)(format!(
            "启动 {}；用户资料 {}",
            release.id,
            layout.profile.display()
        ));
        let listener = TcpListener::bind(("127.0.0.1", 0))?;
        let port = listener.local_addr()?.port();
        drop(listener); // gui.py --port-conflict error fails safely if another process wins the race.
        let mut command = Command::new(env_python(&layout));
        command
            .current_dir(&layout.run)
            .arg("gui.py")
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
                "--port-conflict",
                "error",
            ])
            .env("PYTHONUTF8", "1")
            .env("PYTHONUNBUFFERED", "1")
            .env("PYTHONDONTWRITEBYTECODE", "1")
            .env("NEXT_TRAINER_DATA_ROOT", &layout.profile)
            .env(
                "NEXT_TRAINER_STATE_ROOT",
                layout.profile.join("compat").join(&release.id),
            );
        let mut paths = vec![
            env_python(&layout).parent().unwrap().to_path_buf(),
            root.join("tools"),
        ];
        if let Some(path) = std::env::var_os("PATH") {
            paths.extend(std::env::split_paths(&path));
        }
        command.env("PATH", std::env::join_paths(paths)?);
        let mut child = hidden(&mut command)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()?;
        let job = match Job::attach(&child) {
            Ok(job) => job,
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(e);
            }
        };
        for pipe in [
            child
                .stdout
                .take()
                .map(|p| Box::new(p) as Box<dyn Read + Send>),
            child
                .stderr
                .take()
                .map(|p| Box::new(p) as Box<dyn Read + Send>),
        ]
        .into_iter()
        .flatten()
        {
            let log = self.logger.clone();
            thread::spawn(move || {
                for line in BufReader::new(pipe).lines().map_while(Result::ok) {
                    log(line);
                }
            });
        }
        (self.logger)(format!(
            "已创建受管进程 PID={}，等待 /api/version，端口 {port}",
            child.id()
        ));
        self.running = Some(Running {
            child,
            root: root.to_path_buf(),
            port,
            _lease: lock,
            _job: job,
        });
        let start = Instant::now();
        while start.elapsed() < Duration::from_secs(180) {
            if self.running.as_mut().unwrap().child.try_wait()?.is_some() {
                self.running.take();
                bail!("训练器在健康检查前退出，请检查日志后修复环境");
            }
            if let Ok(version) = health(port).and_then(|v| {
                if owns_listener(port, &self.running.as_ref().unwrap()._job) {
                    Ok(v)
                } else {
                    bail!("监听进程与受管训练器不符")
                }
            }) {
                if version != release.version {
                    self.stop();
                    bail!("健康接口版本不符：{version}");
                }
                (self.logger)(format!(
                    "真实训练器就绪，版本 {version}，http://127.0.0.1:{port}"
                ));
                let mut registry = Registry::load(root)?;
                registry.mark_healthy(&release.id)?;
                registry.store(root)?;
                return self.inspect(root);
            }
            thread::sleep(Duration::from_millis(500));
        }
        self.stop();
        bail!("训练器健康检查超时，已停止本次受管进程，可修复后重试")
    }
    pub fn stop(&mut self) {
        self.running.take();
        (self.logger)("已停止本启动器管理的进程".into());
    }
    pub fn url(&mut self) -> Result<String> {
        self.reap();
        let running = self.running.as_ref().context("尚未启动训练器")?;
        if !owns_listener(running.port, &running._job) {
            bail!("监听端口不属于受管训练器");
        }
        health(running.port)?;
        Ok(format!("http://127.0.0.1:{}", running.port))
    }
}

#[cfg(windows)]
fn owns_listener(port: u16, job: &Job) -> bool {
    use windows_sys::Win32::{NetworkManagement::IpHelper::*, Networking::WinSock::AF_INET};
    unsafe {
        let mut size = 0u32;
        GetExtendedTcpTable(
            std::ptr::null_mut(),
            &mut size,
            0,
            AF_INET as u32,
            TCP_TABLE_OWNER_PID_LISTENER,
            0,
        );
        if size == 0 {
            return false;
        }
        let mut storage = vec![0u32; (size as usize).div_ceil(4)];
        if GetExtendedTcpTable(
            storage.as_mut_ptr() as _,
            &mut size,
            0,
            AF_INET as u32,
            TCP_TABLE_OWNER_PID_LISTENER,
            0,
        ) != 0
        {
            return false;
        }
        let table = storage.as_ptr() as *const MIB_TCPTABLE_OWNER_PID;
        let rows = std::slice::from_raw_parts(
            std::ptr::addr_of!((*table).table) as *const MIB_TCPROW_OWNER_PID,
            (*table).dwNumEntries as usize,
        );
        rows.iter().any(|row| {
            u16::from_be(row.dwLocalPort as u16) == port && job.contains(row.dwOwningPid)
        })
    }
}
#[cfg(not(windows))]
fn owns_listener(_: u16, _: &Job) -> bool {
    false
}

fn health(port: u16) -> Result<String> {
    #[derive(Deserialize)]
    struct Data {
        version: String,
    }
    #[derive(Deserialize)]
    struct Api {
        status: String,
        data: Data,
    }
    // Loopback health must never go through a configured external proxy.
    let result: Api = reqwest::blocking::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(2))
        .build()?
        .get(format!("http://127.0.0.1:{port}/api/version"))
        .send()?
        .error_for_status()?
        .json()?;
    if result.status != "success" {
        bail!("健康接口未返回 success");
    }
    Ok(result.data.version)
}

pub fn logger() -> (Logger, Arc<Mutex<Vec<String>>>) {
    let lines = Arc::new(Mutex::new(Vec::new()));
    let copy = lines.clone();
    let log: Logger = Arc::new(move |line| {
        eprintln!("{line}");
        if let Ok(mut logs) = copy.lock() {
            logs.push(line);
            if logs.len() > 500 {
                logs.remove(0);
            }
        }
    });
    (log, lines)
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;
    use std::io::Write;

    fn negative_test_root(label: &str) -> PathBuf {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "nt-negative-{label}-{}-{unique}",
            std::process::id()
        ));
        fs::create_dir(&root).unwrap();
        root
    }

    /// 只监听回环，一次请求即退出，不访问外部服务，也不分配大响应体。
    fn serve_once(header: &'static str, body: &'static [u8]) -> (String, thread::JoinHandle<()>) {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let address = listener.local_addr().unwrap();
        listener.set_nonblocking(true).unwrap();
        let worker = thread::spawn(move || {
            let started = Instant::now();
            let (mut stream, _) = loop {
                match listener.accept() {
                    Ok(stream) => break stream,
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        assert!(
                            started.elapsed() < Duration::from_secs(10),
                            "回环测试服务未收到请求"
                        );
                        thread::sleep(Duration::from_millis(10));
                    }
                    Err(error) => panic!("回环 accept 失败：{error}"),
                }
            };
            stream
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            stream
                .set_write_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            let mut request = [0_u8; 4096];
            let _ = stream.read(&mut request).unwrap();
            stream.write_all(header.as_bytes()).unwrap();
            stream.write_all(body).unwrap();
            stream.flush().unwrap();
        });
        (format!("http://{address}/asset.zip"), worker)
    }

    #[test]
    fn wrong_sha_download_keeps_partial_and_never_publishes_target() {
        let root = negative_test_root("wrong-sha");
        let cache = root.join("cache");
        fs::create_dir(&cache).unwrap();
        let target = cache.join("asset.zip");
        fs::write(&target, b"previous asset").unwrap();
        let (url, server) = serve_once(
            "HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\n",
            b"tiny",
        );
        let (log, _) = logger();
        let result = download(&root, &url, "asset.zip", &"0".repeat(64), &log);
        server.join().unwrap();
        let error = result.unwrap_err().to_string();
        assert!(
            error.contains("校验失败"),
            "未到达 SHA256 拒绝路径：{error}"
        );
        assert_eq!(fs::read(&target).unwrap(), b"previous asset");
        let partials: Vec<_> = fs::read_dir(&cache)
            .unwrap()
            .map(|e| e.unwrap().path())
            .filter(|path| path.extension().is_some_and(|ext| ext == "part"))
            .collect();
        assert_eq!(partials.len(), 1);
        assert_eq!(fs::read(&partials[0]).unwrap(), b"tiny");
        // 只删除明确创建的单文件和空目录，不递归删除计算路径。
        fs::remove_file(&partials[0]).unwrap();
        fs::remove_file(target).unwrap();
        fs::remove_dir(cache).unwrap();
        fs::remove_dir(root).unwrap();
    }

    #[test]
    fn excessive_content_length_is_rejected_before_creating_partial() {
        let root = negative_test_root("content-length");
        let cache = root.join("cache");
        fs::create_dir(&cache).unwrap();
        let (url, server) = serve_once(
            "HTTP/1.1 200 OK\r\nContent-Length: 200000001\r\nConnection: close\r\n\r\n",
            b"",
        );
        let (log, _) = logger();
        let result = download(&root, &url, "oversized.zip", &"0".repeat(64), &log);
        server.join().unwrap();
        let error = result.unwrap_err().to_string();
        assert!(
            error.contains("下载上限"),
            "未到达长度上限拒绝路径：{error}"
        );
        assert!(fs::read_dir(&cache).unwrap().next().is_none());
        fs::remove_dir(cache).unwrap();
        fs::remove_dir(root).unwrap();
    }

    #[test]
    fn excessive_zip_declared_unpacked_size_is_rejected_without_large_file() {
        let root = negative_test_root("unpacked-size");
        let path = root.join("oversized.zip");
        let file = File::create(&path).unwrap();
        let mut writer = zip::ZipWriter::new(file);
        writer
            .start_file(
                "oversized.bin",
                zip::write::SimpleFileOptions::default()
                    .compression_method(zip::CompressionMethod::Stored),
            )
            .unwrap();
        writer.write_all(b"x").unwrap();
        writer.finish().unwrap();
        let mut bytes = fs::read(&path).unwrap();
        let size = 2_000_000_001_u32.to_le_bytes();
        // ZIP32 local uncompressed-size @22、central uncompressed-size @24。
        let local = bytes.windows(4).position(|p| p == b"PK\x03\x04").unwrap();
        let central = bytes.windows(4).position(|p| p == b"PK\x01\x02").unwrap();
        bytes[local + 22..local + 26].copy_from_slice(&size);
        bytes[central + 24..central + 28].copy_from_slice(&size);
        assert!(bytes.len() < 1024, "夹具必须保持很小");
        fs::write(&path, bytes).unwrap();
        let destination = root.join("unpacked");
        let error = extract(&path, &destination, false).unwrap_err().to_string();
        assert!(
            error.contains("解压体积超过"),
            "未到达展开预算拒绝路径：{error}"
        );
        assert!(!destination.exists());
        fs::remove_file(path).unwrap();
        fs::remove_dir(root).unwrap();
    }

    #[test]
    fn uv_python_alias_must_resolve_inside_same_managed_version() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("nt-python-alias-{unique}"));
        let release = Catalog::embedded().unwrap().releases()[0].clone();
        let layout = Layout::new(&root, &release.id).unwrap();
        let managed = root.join("python").join(&release.python);
        let actual = managed.join("actual");
        fs::create_dir_all(&actual).unwrap();
        let alias = managed.join("uv-version-alias");
        junction::create(&actual, &alias).unwrap();
        assert_eq!(
            managed_base_path(&layout, &release, &alias).unwrap(),
            actual.canonicalize().unwrap()
        );
        let other = root.join("another-version");
        fs::create_dir(&other).unwrap();
        let escaped = managed.join("external-alias");
        junction::create(&other, &escaped).unwrap();
        assert!(managed_base_path(&layout, &release, &escaped).is_err());
        assert!(managed_base_path(&layout, &release, &other).is_err());
        // 保留含联接的独立测试现场，不递归删除目标。
    }
}
