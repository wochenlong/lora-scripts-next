use crate::instances;
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

#[path = "installation_snapshot.rs"]
mod installation_snapshot;
#[path = "lifecycle.rs"]
mod lifecycle;
pub use installation_snapshot::{read as installation_snapshot, InstallationSnapshot};
#[path = "managed_child.rs"]
mod managed_child;
pub use lifecycle::{Lifecycle, RuntimeSnapshot};

#[path = "artifact_downloads.rs"]
mod artifact_downloads;
#[path = "controlled_download.rs"]
mod controlled_download;
#[path = "engine_bridge.rs"]
mod engine_bridge;
#[path = "engine_query_runtime.rs"]
mod engine_query_runtime;
pub(crate) use engine_query_runtime::run as run_engine_query;

#[path = "base_python_repair.rs"]
mod base_python_repair;
#[path = "gui_binding_switch.rs"]
mod gui_binding_switch;
#[path = "gui_entry_probe.rs"]
mod gui_entry_probe;
#[path = "gui_install.rs"]
mod gui_install;
#[path = "gui_rebuild.rs"]
mod gui_rebuild;
#[path = "gui_recovery.rs"]
mod gui_recovery;
#[path = "gui_registration.rs"]
mod gui_registration;
#[path = "gui_repair.rs"]
mod gui_repair;
#[path = "gui_source_repair.rs"]
mod gui_source_repair;
#[path = "legacy_environment_repair.rs"]
mod legacy_environment_repair;
#[path = "legacy_install_recovery.rs"]
mod legacy_install_recovery;

#[path = "safe_extract.rs"]
mod safe_extract;

#[cfg(all(test, windows))]
#[path = "p6_tests.rs"]
mod p6_tests;

#[cfg(test)]
#[path = "reliability_r1_commit_tests.rs"]
mod r1_commit_boundary_tests;

pub type Logger = Arc<dyn Fn(String) + Send + Sync>;
type ServiceLoggerFactory = Arc<dyn Fn(&Path, &str) -> Logger + Send + Sync>;
pub(crate) fn embedded_engine_lock(engine: &str) -> Option<&'static [u8]> {
    engine_bridge::embedded_lock(engine)
}

fn assert_registration_ready(root: &Path, except_release: Option<&str>) -> Result<()> {
    for release in Catalog::embedded()?.releases() {
        if Some(release.id.as_str()) != except_release {
            gui_registration::assert_ready(root, release)?;
        }
    }
    Ok(())
}

fn assert_regular_ready(root: &Path) -> Result<()> {
    assert_regular_ready_with_cancel(root, None)
}

fn assert_regular_ready_with_cancel(
    root: &Path,
    cancel: Option<&crate::operations::CancelToken>,
) -> Result<()> {
    assert_regular_ready_except_legacy_environment_repair(root, None, cancel)
}

fn assert_regular_ready_for_legacy_environment_repair(
    root: &Path,
    transaction: &str,
    cancel: &crate::operations::CancelToken,
) -> Result<()> {
    assert_regular_ready_except_legacy_environment_repair(root, Some(transaction), Some(cancel))
}

fn assert_regular_ready_except_legacy_environment_repair(
    root: &Path,
    transaction: Option<&str>,
    cancel: Option<&crate::operations::CancelToken>,
) -> Result<()> {
    assert_regular_ready_with_recovery(root, transaction, None, cancel)
}

fn assert_regular_ready_for_gui_recovery(
    root: &Path,
    release: &Release,
    cancel: &crate::operations::CancelToken,
) -> Result<()> {
    assert_regular_ready_with_recovery(root, None, Some(release), Some(cancel))
}

fn assert_regular_ready_with_recovery(
    root: &Path,
    transaction: Option<&str>,
    repair_release: Option<&Release>,
    cancel: Option<&crate::operations::CancelToken>,
) -> Result<()> {
    crate::scan_observation::check()?;
    if let Some(cancel) = cancel {
        cancel.check()?;
    }
    crate::data_import::assert_binding_ready(root)?;
    crate::shell_update_protocol::assert_ready(root)?;
    base_python_repair::assert_ready(root)?;
    legacy_environment_repair::assert_ready_except(root, transaction, cancel)?;
    match repair_release {
        Some(release) => gui_repair::assert_worker_reap_ready_for_recovery(root, release)?,
        None => gui_repair::assert_worker_reap_ready(root)?,
    }
    assert_registration_ready(root, None)?;
    for release in Catalog::embedded()?.releases() {
        gui_rebuild::assert_ready_with_cancel(root, release, cancel)?;
        gui_binding_switch::assert_ready_with_cancel(root, release, cancel)?;
    }
    let result = crate::instances::assert_no_preserved_pending(root);
    crate::scan_observation::check()?;
    if let Some(cancel) = cancel {
        cancel.check()?;
    }
    result
}

fn complete_gui_lifecycle_success(
    ctx: &model::WorkspaceMutation,
    release_id: &str,
    cancel: &crate::operations::CancelToken,
) -> Result<()> {
    // 幂等恢复也必须与最后到达的取消竞争；控制JSON/绑定代次同步属于短收尾，
    // 不得在已返回Accepted后仍将本次操作报告成功。实际收尾时限另由原生实测。
    cancel.enter_commit()?;
    crate::data_import::sync_current_environment(ctx, release_id)
}

fn finish_gui_lifecycle_result(
    ctx: &model::WorkspaceMutation,
    operation: &crate::operations::OperationHandle,
    result: Result<()>,
) -> Result<()> {
    use crate::operations::{Cancelled, OperationError, OperationStatus};
    let (status, error) = match &result {
        Ok(()) => (OperationStatus::Succeeded, None),
        Err(error)
            if error
                .downcast_ref::<ControlledProcessReapFailed>()
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
                code: "gui_lifecycle_failed".into(),
                message: format!("{error:#}"),
            }),
        ),
    };
    match operation.finish_and_persist(ctx, status, error) {
        Ok(()) => result,
        Err(persist) => match result {
            Err(failure)
                if failure
                    .downcast_ref::<ControlledProcessReapFailed>()
                    .is_some() =>
            {
                Err(failure.context(format!(
                    "操作终态未能保存；原排空失败与事务现场保持：{persist:#}"
                )))
            }
            _ => Err(persist),
        },
    }
}
const REQUIRED: &[&str] = &[
    "gui.py",
    "requirements.txt",
    "VERSION",
    "frontend/dist/index.html",
];

#[derive(Clone, Serialize)]
pub struct Check {
    name: String,
    ok: bool,
    detail: String,
}
#[derive(Clone, Serialize)]
pub struct Report {
    root: String,
    uv: bool,
    python: bool,
    source: bool,
    environment: bool,
    frontend: bool,
    pub(crate) running: bool,
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
#[derive(Clone, Serialize)]
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
    managed_recipe: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    legacy_recovery: Option<legacy_install_recovery::LegacyRecoveryCandidate>,
    #[serde(skip_serializing_if = "Option::is_none")]
    legacy_environment_repair: Option<String>,
    #[serde(flatten)]
    support: ReleaseSupport,
}

#[derive(Clone, Copy, Serialize)]
struct ReleaseSupport {
    source_supported: bool,
    maintenance_supported: bool,
    install_supported: bool,
}

// 配方的通用名称只说明安装类型，不能证明本包提供了该提交的修复材料。
fn release_support(release: &Release, recipe: &crate::recipe::GuiRecipe) -> ReleaseSupport {
    let managed = release.environment_recipe == "gui-cp310-win-x64-v1";
    let source_supported = !managed || crate::source_integrity::supports(release);
    let maintenance_supported = managed
        && source_supported
        && release.commit == recipe.source_commit
        && release.python == recipe.python.version
        && release.uv == recipe.tool_uv
        && recipe.matches_environment_recipe(&release.environment_recipe);
    ReleaseSupport {
        source_supported,
        maintenance_supported,
        install_supported: !managed || maintenance_supported,
    }
}

pub struct Engine {
    pub default_root: PathBuf,
    pub lifecycle: Arc<Lifecycle>,
    assessment: Option<Report>,
    logger: Logger,
    service_logger: Option<ServiceLoggerFactory>,
    catalog: Catalog,
}

struct Running {
    child: Child,
    port: u16,
    _job: Job,
    // Fields drop in declaration order: close the process group before releasing the workspace lock.
    _lease: Arc<File>,
    _service_lease: Option<File>,
}

impl Running {
    fn terminate(&mut self) -> Result<()> {
        self._job.terminate_and_wait()?;
        let _ = self.child.kill();
        self.child.wait().context("等待受管训练器退出失败")?;
        Ok(())
    }
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

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum NamedJobReap {
    Drained,
    Destroyed,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub(super) struct ControlledHostIdentity {
    pub pid: u32,
    pub creation_time: u64,
}

#[cfg(windows)]
fn controlled_host_creation(handle: windows_sys::Win32::Foundation::HANDLE) -> Result<u64> {
    use windows_sys::Win32::{Foundation::FILETIME, System::Threading::GetProcessTimes};
    let mut created: FILETIME = unsafe { std::mem::zeroed() };
    let mut exited: FILETIME = unsafe { std::mem::zeroed() };
    let mut kernel: FILETIME = unsafe { std::mem::zeroed() };
    let mut user: FILETIME = unsafe { std::mem::zeroed() };
    if unsafe { GetProcessTimes(handle, &mut created, &mut exited, &mut kernel, &mut user) } == 0 {
        return Err(std::io::Error::last_os_error()).context("读取受管宿主进程代次失败");
    }
    let creation_time =
        (u64::from(created.dwHighDateTime) << 32) | u64::from(created.dwLowDateTime);
    if creation_time == 0 {
        bail!("受管宿主进程代次无效");
    }
    Ok(creation_time)
}

fn current_controlled_host_identity() -> Result<ControlledHostIdentity> {
    #[cfg(windows)]
    {
        let handle = unsafe { windows_sys::Win32::System::Threading::GetCurrentProcess() };
        Ok(ControlledHostIdentity {
            pid: std::process::id(),
            creation_time: controlled_host_creation(handle)?,
        })
    }
    #[cfg(not(windows))]
    {
        bail!("受管宿主代次当前仅支持 Windows");
    }
}

/// 只证明保存的宿主代次已退出，绝不代替随后对每个命名 Job 的排空证明。
fn assert_controlled_host_exited(identity: &ControlledHostIdentity) -> Result<()> {
    #[cfg(windows)]
    {
        use windows_sys::Win32::{
            Foundation::{
                CloseHandle, GetLastError, ERROR_INVALID_PARAMETER, WAIT_OBJECT_0, WAIT_TIMEOUT,
            },
            System::Threading::{
                OpenProcess, WaitForSingleObject, PROCESS_QUERY_LIMITED_INFORMATION,
                PROCESS_SYNCHRONIZE,
            },
        };
        let result = (|| {
            if identity.pid == 0 || identity.creation_time == 0 {
                bail!("持久受管宿主身份无效");
            }
            if identity == &current_controlled_host_identity()? {
                bail!("排空失败需要旧宿主退出后由新宿主恢复");
            }
            let handle = unsafe {
                OpenProcess(
                    PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SYNCHRONIZE,
                    0,
                    identity.pid,
                )
            };
            if handle.is_null() {
                let error = unsafe { GetLastError() };
                if error == ERROR_INVALID_PARAMETER {
                    // 这是已验证为非零的历史PID不存在；不据此判断其worker/Job。
                    return Ok(());
                }
                return Err(std::io::Error::from_raw_os_error(error as i32))
                    .context("打开旧受管宿主失败，不能证明其退出");
            }
            struct Handle(windows_sys::Win32::Foundation::HANDLE);
            impl Drop for Handle {
                fn drop(&mut self) {
                    unsafe {
                        CloseHandle(self.0);
                    }
                }
            }
            let handle = Handle(handle);
            if controlled_host_creation(handle.0)? != identity.creation_time {
                return Ok(()); // PID已指向新代，保存的旧宿主代次已退出。
            }
            match unsafe { WaitForSingleObject(handle.0, 0) } {
                WAIT_OBJECT_0 => Ok(()),
                WAIT_TIMEOUT => bail!("旧受管宿主同代仍运行，禁止清除reader排空失败屏障"),
                _ => Err(std::io::Error::last_os_error()).context("读取旧受管宿主退出信号失败"),
            }
        })();
        result.map_err(|error: anyhow::Error| {
            let mut failure = ControlledProcessReapFailed::new(format!("{error:#}"), false);
            failure.requires_new_host = true;
            failure.into()
        })
    }
    #[cfg(not(windows))]
    {
        let _ = identity;
        bail!("受管宿主代次当前仅支持 Windows");
    }
}

#[cfg(windows)]
impl Job {
    const LEGACY_REPAIR_PREFIX: &'static str = "Local\\NextTrainerLegacyRepair-";

    fn current_session_id() -> Result<u32> {
        let mut session = 0;
        if unsafe {
            windows_sys::Win32::System::RemoteDesktop::ProcessIdToSessionId(
                std::process::id(),
                &mut session,
            )
        } == 0
        {
            return Err(std::io::Error::last_os_error()).context("读取环境修复 Job 会话失败");
        }
        Ok(session)
    }

    fn generate_legacy_repair_name() -> Result<String> {
        use ring::rand::{SecureRandom, SystemRandom};
        let mut nonce = [0u8; 32];
        SystemRandom::new()
            .fill(&mut nonce)
            .map_err(|_| anyhow::anyhow!("生成环境修复 Job 随机身份失败"))?;
        Ok(format!(
            "{}{}",
            Self::LEGACY_REPAIR_PREFIX,
            nonce
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect::<String>()
        ))
    }

    fn validate_legacy_repair_name(name: &str) -> Result<()> {
        let suffix = name
            .strip_prefix(Self::LEGACY_REPAIR_PREFIX)
            .context("环境修复 Job 命名空间不匹配")?;
        if suffix.len() != 64
            || !suffix
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            bail!("环境修复 Job 身份必须为32字节随机小写十六进制值");
        }
        Ok(())
    }

    /// 调用方必须先持久化 launching，再创建并只为一个命令使用此 Job。
    /// 默认 SECURITY_ATTRIBUTES 使 handle 不可继承；不允许打开碰撞对象。
    fn create_named(name: &str) -> Result<Self> {
        use windows_sys::Win32::{
            Foundation::{GetLastError, SetLastError, ERROR_ALREADY_EXISTS},
            System::JobObjects::CreateJobObjectW,
        };
        Self::validate_legacy_repair_name(name)?;
        let name: Vec<u16> = name.encode_utf16().chain(std::iter::once(0)).collect();
        unsafe {
            SetLastError(0);
        }
        let handle = unsafe { CreateJobObjectW(std::ptr::null(), name.as_ptr()) };
        let error = unsafe { GetLastError() };
        if handle.is_null() {
            return Err(std::io::Error::from_raw_os_error(error as i32))
                .context("创建环境修复命名 Job 失败");
        }
        let job = Self(handle);
        if error == ERROR_ALREADY_EXISTS {
            drop(job);
            bail!("环境修复命名 Job 已存在，拒绝复用或接管");
        }
        job.set_kill_on_close()?;
        Ok(job)
    }

    /// None 只表示 ERROR_FILE_NOT_FOUND。调用方仍须核可信 intent 的 attached
    /// 回执；launching 的无对象不能证明 CreateProcess→Assign 窗口没有悬挂进程。
    fn reopen_named(name: &str) -> Result<Option<Self>> {
        use windows_sys::Win32::{
            Foundation::{GetLastError, ERROR_FILE_NOT_FOUND},
            System::JobObjects::OpenJobObjectW,
        };
        Self::validate_legacy_repair_name(name)?;
        let name: Vec<u16> = name.encode_utf16().chain(std::iter::once(0)).collect();
        // JOB_OBJECT_QUERY | JOB_OBJECT_TERMINATE；恢复不能再向旧 Job 分配进程。
        let handle = unsafe { OpenJobObjectW(0x0004 | 0x0008, 0, name.as_ptr()) };
        if !handle.is_null() {
            return Ok(Some(Self(handle)));
        }
        let error = unsafe { GetLastError() };
        if error == ERROR_FILE_NOT_FOUND {
            return Ok(None);
        }
        Err(std::io::Error::from_raw_os_error(error as i32))
            .context("重开环境修复命名 Job 失败，不能证明进程排空")
    }

    /// 可信 intent 与 ownership 的校验由事务层完成；本层统一把 Windows
    /// 生命周期证明与有歧义的 launching/跨会话状态区分，绝不新建同名空 Job。
    fn reap_named_attached(name: &str, session_id: u32, attached: bool) -> Result<NamedJobReap> {
        let result = (|| {
            Self::validate_legacy_repair_name(name)?;
            if !attached || session_id != Self::current_session_id()? {
                bail!("命名 Job 未持久证明 attached-before-resume 或 Windows 会话不同");
            }
            match Self::reopen_named(name)? {
                Some(job) => {
                    job.terminate_and_wait()?;
                    Ok(NamedJobReap::Drained)
                }
                // Job 只有最后 handle 关闭且关联进程全退出后才销毁；这里的
                // None 仅来自精确 ERROR_FILE_NOT_FOUND，权限错误绝不归此分支。
                None => Ok(NamedJobReap::Destroyed),
            }
        })();
        result.map_err(|error: anyhow::Error| {
            ControlledProcessReapFailed::new(format!("{error:#}"), false).into()
        })
    }

    fn set_kill_on_close(&self) -> Result<()> {
        use windows_sys::Win32::System::JobObjects::*;
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = unsafe { std::mem::zeroed() };
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if unsafe {
            SetInformationJobObject(
                self.0,
                JobObjectExtendedLimitInformation,
                &info as *const _ as _,
                std::mem::size_of_val(&info) as u32,
            )
        } == 0
        {
            return Err(std::io::Error::last_os_error()).context("配置受管 Job 关闭回收失败");
        }
        Ok(())
    }

    fn assign(&self, child: &Child) -> Result<()> {
        use std::os::windows::io::AsRawHandle;
        if unsafe {
            windows_sys::Win32::System::JobObjects::AssignProcessToJobObject(
                self.0,
                child.as_raw_handle() as _,
            )
        } == 0
        {
            return Err(std::io::Error::last_os_error())
                .context("绑定受管进程失败，已拒绝无归属运行");
        }
        Ok(())
    }

    fn active_processes(&self) -> Result<u32> {
        use windows_sys::Win32::System::JobObjects::*;
        unsafe {
            let mut info: JOBOBJECT_BASIC_ACCOUNTING_INFORMATION = std::mem::zeroed();
            if QueryInformationJobObject(
                self.0,
                JobObjectBasicAccountingInformation,
                &mut info as *mut _ as _,
                std::mem::size_of_val(&info) as u32,
                std::ptr::null_mut(),
            ) == 0
            {
                return Err(std::io::Error::last_os_error()).context("读取检查 Job 活动进程失败");
            }
            Ok(info.ActiveProcesses)
        }
    }
    fn terminate(&self) -> Result<()> {
        unsafe {
            if windows_sys::Win32::System::JobObjects::TerminateJobObject(self.0, 1) == 0 {
                return Err(std::io::Error::last_os_error()).context("终止检查 Job 失败");
            }
        }
        Ok(())
    }
    fn terminate_and_wait(&self) -> Result<()> {
        self.terminate_and_wait_until(Instant::now() + Duration::from_secs(5))
    }
    fn terminate_and_wait_until(&self, deadline: Instant) -> Result<()> {
        use windows_sys::Win32::System::JobObjects::*;
        unsafe {
            if TerminateJobObject(self.0, 1) == 0 {
                return Err(std::io::Error::last_os_error()).context("终止本次受管 Job 失败");
            }
            loop {
                let mut info: JOBOBJECT_BASIC_ACCOUNTING_INFORMATION = std::mem::zeroed();
                if QueryInformationJobObject(
                    self.0,
                    JobObjectBasicAccountingInformation,
                    &mut info as *mut _ as _,
                    std::mem::size_of_val(&info) as u32,
                    std::ptr::null_mut(),
                ) == 0
                {
                    return Err(std::io::Error::last_os_error())
                        .context("读取受管 Job 活动进程失败");
                }
                if info.ActiveProcesses == 0 {
                    return Ok(());
                }
                if Instant::now() >= deadline {
                    bail!("受管进程组尚未排空，保留运行归属和工作区租约");
                }
                thread::sleep(Duration::from_millis(10));
            }
        }
    }
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
        let handle = unsafe {
            windows_sys::Win32::System::JobObjects::CreateJobObjectW(
                std::ptr::null(),
                std::ptr::null(),
            )
        };
        if handle.is_null() {
            bail!("创建受管进程 Job Object 失败");
        }
        let job = Self(handle);
        job.set_kill_on_close()?;
        job.assign(child)?;
        Ok(job)
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
    fn current_session_id() -> Result<u32> {
        bail!("命名 Job 环境修复当前仅支持 Windows")
    }
    fn generate_legacy_repair_name() -> Result<String> {
        bail!("命名 Job 环境修复当前仅支持 Windows")
    }
    fn validate_legacy_repair_name(_: &str) -> Result<()> {
        bail!("命名 Job 环境修复当前仅支持 Windows")
    }
    fn create_named(_: &str) -> Result<Self> {
        bail!("命名 Job 环境修复当前仅支持 Windows")
    }
    fn reopen_named(_: &str) -> Result<Option<Self>> {
        bail!("命名 Job 环境修复当前仅支持 Windows")
    }
    fn reap_named_attached(_: &str, _: u32, _: bool) -> Result<NamedJobReap> {
        bail!("命名 Job 环境修复当前仅支持 Windows")
    }
    fn active_processes(&self) -> Result<u32> {
        Ok(0)
    }
    fn terminate(&self) -> Result<()> {
        Ok(())
    }
    fn terminate_and_wait(&self) -> Result<()> {
        Ok(())
    }
    fn terminate_and_wait_until(&self, _: Instant) -> Result<()> {
        Ok(())
    }
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
    digest_with_cancel(path, None)
}
fn digest_controlled(path: &Path, cancel: &crate::operations::CancelToken) -> Result<String> {
    digest_with_cancel(path, Some(cancel))
}
fn digest_with_cancel(
    path: &Path,
    cancel: Option<&crate::operations::CancelToken>,
) -> Result<String> {
    crate::scan_observation::checkpoint(crate::query_tasks::QueryStage::Environment, 0, 0)?;
    if let Some(cancel) = cancel {
        cancel.check()?;
    }
    let mut f = File::open(path)?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 65536];
    loop {
        crate::scan_observation::checkpoint(crate::query_tasks::QueryStage::Environment, 0, 0)?;
        if let Some(cancel) = cancel {
            cancel.check()?;
        }
        let n = f.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        hash.update(&buffer[..n]);
        crate::scan_observation::checkpoint(
            crate::query_tasks::QueryStage::Environment,
            0,
            n as u64,
        )?;
        if let Some(cancel) = cancel {
            cancel.check()?;
        }
    }
    crate::scan_observation::checkpoint(crate::query_tasks::QueryStage::Environment, 1, 0)?;
    Ok(format!("{:x}", hash.finalize()))
}

fn download(
    ctx: &model::WorkspaceMutation,
    url: &str,
    name: &str,
    expected: &str,
    exact_bytes: u64,
    log: &Logger,
) -> Result<PathBuf> {
    if exact_bytes > model::MAX_DOWNLOAD_BYTES {
        bail!("资产超出启动器下载上限");
    }
    let mut downloads = artifact_downloads::ArtifactDownloads::new();
    log(format!("获取并校验固定资产：{name}"));
    downloads.download(
        ctx,
        url,
        name,
        expected,
        exact_bytes,
        &crate::operations::CancelToken::new(),
    )
}

/// P6 机制入口：异步网络读取运行于独立任务，取消会 abort 并等待任务析构，
/// 因而响应头或正文永久停滞时也不等待阻塞 read。客户端由调用方配置网络策略。
/// 仅 worker 在任务结束、取消重核与完整摘要通过后才发布缓存。
#[cfg(test)] // P6 先验证机制，下一切片接正式操作 IPC。
fn download_controlled(
    mutation: &model::WorkspaceMutation,
    client: reqwest::Client,
    url: &str,
    name: &str,
    expected: &str,
    limit: u64,
    cancel: &crate::operations::CancelToken,
) -> Result<PathBuf> {
    use std::io::Write;
    cancel.check()?;
    model::validate_component(name)?;
    let layout = mutation.layout();
    let target = layout.root.join("cache").join(name);
    layout.guard_path(&target)?;
    let partial = target.with_extension(format!("{}.part", stamp()));
    layout.guard_path(&partial)?;
    let mut output = File::options()
        .write(true)
        .create_new(true)
        .open(&partial)?;
    let url = url.to_owned();
    let task = tauri::async_runtime::spawn(async move {
        let mut response = client.get(url).send().await?.error_for_status()?;
        if response.content_length().unwrap_or(0) > limit {
            bail!("资产超出本操作限额");
        }
        let mut written = 0u64;
        while let Some(chunk) = response.chunk().await? {
            written = written
                .checked_add(chunk.len() as u64)
                .context("下载计量溢出")?;
            if written > limit {
                bail!("资产超出本操作限额，保留partial");
            }
            output.write_all(&chunk)?;
        }
        output.sync_all()?;
        Ok::<_, anyhow::Error>(written)
    });
    loop {
        if cancel.is_cancel_requested() {
            task.abort();
            // 等待已停止的任务释放 socket 和文件，不把后台孤儿读线程当作取消。
            let _ = tauri::async_runtime::block_on(task);
            cancel.check()?;
            unreachable!("取消标记只能由false变为true");
        }
        if task.inner().is_finished() {
            tauri::async_runtime::block_on(task)??;
            break;
        }
        thread::sleep(Duration::from_millis(20));
    }
    cancel.check()?;
    if digest(&partial)? != expected {
        bail!("下载摘要不符；partial保留，目标未发布");
    }
    layout.guard_path(&target)?;
    if target.exists() {
        bail!("缓存目标已存在；P6机制入口拒绝覆盖");
    }
    cancel.check()?;
    fs::rename(&partial, &target)?;
    Ok(target)
}

fn extract(zip_path: &Path, destination: &Path, strip_root: bool) -> Result<()> {
    safe_extract::extract(zip_path, destination, strip_root, None)
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
    verify_source_with_cancel(layout, release, None)
}
fn verify_source_controlled(
    layout: &Layout,
    release: &Release,
    cancel: &crate::operations::CancelToken,
) -> Result<()> {
    verify_source_with_cancel(layout, release, Some(cancel))
}
fn verify_source_with_cancel(
    layout: &Layout,
    release: &Release,
    cancel: Option<&crate::operations::CancelToken>,
) -> Result<()> {
    crate::scan_observation::check()?;
    if let Some(cancel) = cancel {
        cancel.check()?;
    }
    layout.guard_path(&layout.app)?;
    let receipt = ReleaseReceipt::load(&layout.release_dir)?;
    if receipt.release != *release {
        bail!("本地发布清单不匹配");
    }
    if release.environment_recipe == "gui-cp310-win-x64-v1" {
        return match cancel {
            Some(cancel) => crate::source_integrity::verify_controlled(layout, release, cancel),
            None => crate::source_integrity::verify(layout, release),
        };
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
        let actual = digest_with_cancel(&dir.join(p), cancel);
        // 取消及查询期限必须先于“损坏”结论返回，不能被旧的ok()吞掉。
        crate::scan_observation::check()?;
        if let Some(cancel) = cancel {
            cancel.check()?;
        }
        if actual.ok().as_deref() != Some(expected.as_str()) {
            bail!("源码文件缺失或改变：{rel}");
        }
    }
    Ok(())
}

fn uv_command(root: &Path, release: &Release) -> Result<Command> {
    let mut command = Command::new(uv(root));
    crate::network_policy::current_or_root(root)?.apply_command(&mut command);
    command
        .env(
            "UV_PYTHON_INSTALL_DIR",
            root.join("python").join(&release.python),
        )
        .env("UV_CACHE_DIR", root.join("cache/uv"))
        .env("UV_NO_CONFIG", "1")
        // 历史未锁配方只能使用既有本地缓存；所有在线制品必须先经受控下载器。
        .env("UV_OFFLINE", "1")
        .env("UV_PYTHON_DOWNLOADS", "never")
        .env("UV_PYTHON_BIN_DIR", root.join("tools"))
        .env("UV_NO_PROGRESS", "1");
    hidden(&mut command);
    Ok(command)
}
fn managed_python(root: &Path, release: &Release) -> Result<PathBuf> {
    let layout = Layout::new(root, &release.id)?;
    if release.environment_recipe == "gui-cp310-win-x64-v1" {
        return crate::python_integrity::verify(&layout);
    }
    layout.guard_path(&uv(root))?;
    layout.guard_path(&root.join("python").join(&release.python))?;
    if digest(&uv(root)).ok().as_deref() != Some(release.uv.exe_sha256.as_str()) {
        bail!("自管 uv 缺失或校验失败，请重新准备基础工具");
    }
    let out = uv_command(root, release)?
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
                "-B",
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
    check_environment_with_cancel(layout, release, None, None)
}
fn check_environment_controlled(
    layout: &Layout,
    release: &Release,
    cancel: &crate::operations::CancelToken,
    log: &Logger,
) -> Result<()> {
    check_environment_with_cancel(layout, release, Some(cancel), Some(log))
}
fn check_environment_with_cancel(
    layout: &Layout,
    release: &Release,
    cancel: Option<&crate::operations::CancelToken>,
    log: Option<&Logger>,
) -> Result<()> {
    crate::scan_observation::check()?;
    if let Some(cancel) = cancel {
        cancel.check()?;
    }
    assert_regular_ready(&layout.root)?;
    // 版本列表也检查未安装的历史发布，先拒绝缺失环境，避免反复扫描整套基础 Python。
    // 已安装环境仍执行下面全部可信闭包、绑定、配置及运行检查。
    layout.guard_path(&layout.environment)?;
    layout.guard_path(&env_python(layout))?;
    if !layout.environment.is_dir() || !env_python(layout).is_file() {
        bail!("主程序环境尚未安装或解释器缺失，请安装或修复此版本");
    }
    if release.environment_recipe == "gui-cp310-win-x64-v1" {
        match cancel {
            Some(cancel) => crate::python_integrity::verify_controlled(layout, cancel)?,
            None => crate::python_integrity::verify(layout)?,
        };
    }
    if let Some(binding) = Registry::load(&layout.root)?.gui_binding(&release.id) {
        let instance = crate::instances::load(layout, &binding.instance_id)?;
        if instance.recipe_id() != binding.recipe_id
            || instance.storage_version() != binding.storage_version
            || instance.generation() != binding.generation
            || instance.recipe_sha256() != binding.recipe_sha256
        {
            bail!("环境绑定generation或配方与实例不一致，请重新诊断");
        }
        match cancel {
            Some(cancel) => crate::instances::assert_usable_controlled(&instance, cancel)?,
            None => crate::instances::assert_usable(&instance)?,
        }
    }
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
    let mut probe = Command::new(env_python(layout));
    hidden(&mut probe)
        .args(["-I", "-B", "-c", script])
        .arg(managed)
        .arg(&release.python);
    if let Some(cancel) = cancel {
        let log = log.context("受控环境检查缺少日志接收器")?;
        return execute_controlled(probe, log, cancel);
    }
    let result = probe.output()?;
    if !result.status.success() {
        bail!("{}", String::from_utf8_lossy(&result.stderr));
    }
    Ok(())
}
fn execute(mut command: Command, log: &Logger) -> Result<()> {
    log(format!("执行 {:?}", command.get_program()));
    command.stdout(Stdio::piped()).stderr(Stdio::piped());
    let (mut child, job) = managed_child::spawn(&mut command)?;
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
    drop(job);
    for t in threads {
        let _ = t.join();
    }
    if !status.success() {
        bail!("子任务失败（{status}），请检查日志后重试");
    }
    Ok(())
}

const CONTROLLED_OUTPUT_LIMIT: usize = 64 * 1024;
const CONTROLLED_LINE_LIMIT: usize = 8 * 1024;
// OperationSnapshot整体最多64KiB；为JSON转义、错误头和其他字段预留空间。
const CONTROLLED_ERROR_JSON_LIMIT: usize = 48 * 1024;

#[derive(Default)]
struct ControlledOutputTail {
    stdout: Vec<u8>,
    stderr: Vec<u8>,
    truncated: bool,
}

impl ControlledOutputTail {
    fn append_bounded(target: &mut Vec<u8>, bytes: &[u8], limit: usize) -> bool {
        let discarded = target
            .len()
            .saturating_add(bytes.len())
            .saturating_sub(limit);
        if bytes.len() >= limit {
            target.clear();
            target.extend_from_slice(&bytes[bytes.len() - limit..]);
        } else {
            target.drain(..discarded);
            target.extend_from_slice(bytes);
        }
        discarded != 0
    }

    fn append(&mut self, stderr: bool, bytes: &[u8]) {
        if stderr {
            self.truncated |=
                Self::append_bounded(&mut self.stderr, bytes, CONTROLLED_OUTPUT_LIMIT);
            let remaining = CONTROLLED_OUTPUT_LIMIT - self.stderr.len();
            if self.stdout.len() > remaining {
                let discarded = self.stdout.len() - remaining;
                self.stdout.drain(..discarded);
                self.truncated = true;
            }
        } else {
            self.truncated |= Self::append_bounded(
                &mut self.stdout,
                bytes,
                CONTROLLED_OUTPUT_LIMIT - self.stderr.len(),
            );
        }
    }

    fn text(bytes: &[u8]) -> String {
        // 环形尾部可能从UTF-8续字节开始；去掉该字符残片后再解码。
        let start = bytes
            .iter()
            .position(|value| value & 0xc0 != 0x80)
            .unwrap_or(bytes.len());
        String::from_utf8_lossy(&bytes[start..]).into_owned()
    }

    fn failure_detail(&self) -> String {
        let mut detail = String::new();
        if !self.stdout.is_empty() {
            detail.push_str("[stdout]\n");
            detail.push_str(&crate::log_store::redact_bounded_tail(&Self::text(
                &self.stdout,
            )));
        }
        if !self.stderr.is_empty() {
            // stderr放在末尾，最终持久化裁剪优先保留真正的错误原因。
            detail.push_str("\n[stderr]\n");
            detail.push_str(&crate::log_store::redact_bounded_tail(&Self::text(
                &self.stderr,
            )));
        }
        let boundaries: Vec<_> = detail
            .char_indices()
            .map(|(index, _)| index)
            .chain(std::iter::once(detail.len()))
            .collect();
        let mut low = 0;
        let mut high = boundaries.len() - 1;
        while low < high {
            let middle = low + (high - low) / 2;
            let bytes = serde_json::to_vec(&detail[boundaries[middle]..])
                .expect("字符串JSON序列化不会失败")
                .len();
            if bytes > CONTROLLED_ERROR_JSON_LIMIT {
                low = middle + 1;
            } else {
                high = middle;
            }
        }
        let start = boundaries[low];
        let marker = if self.truncated || start != 0 {
            "[输出已截断，仅保留有界尾部]\n"
        } else {
            ""
        };
        format!("{marker}{}", &detail[start..])
    }
}

fn read_controlled_pipe(
    mut pipe: Box<dyn Read + Send>,
    stderr: bool,
    log: Logger,
    tail: Arc<Mutex<ControlledOutputTail>>,
    stop: Arc<std::sync::atomic::AtomicBool>,
) -> Result<()> {
    let mut block = [0; CONTROLLED_LINE_LIMIT];
    let mut line = Vec::with_capacity(CONTROLLED_LINE_LIMIT);
    let mut truncated = false;
    let emit = |line: &[u8], truncated: bool| {
        let line = line.strip_suffix(b"\r").unwrap_or(line);
        let line = match std::str::from_utf8(line) {
            Err(error) if truncated && error.error_len().is_none() => &line[..error.valid_up_to()],
            _ => line,
        };
        let text = String::from_utf8_lossy(line);
        let marker = if truncated {
            "[单行输出已截断] "
        } else {
            ""
        };
        log(crate::log_store::redact(&format!("{marker}{text}")));
    };
    loop {
        if stop.load(std::sync::atomic::Ordering::Acquire) {
            break;
        }
        let read = match pipe.read(&mut block) {
            Ok(0) => break,
            Ok(read) => read,
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(error) => {
                log(format!("读取子进程输出失败：{error}"));
                return Err(error).context("受管输出读取失败");
            }
        };
        tail.lock().unwrap().append(stderr, &block[..read]);
        for &value in &block[..read] {
            if value == b'\n' {
                emit(&line, truncated);
                line.clear();
                truncated = false;
            } else if line.len() < CONTROLLED_LINE_LIMIT {
                line.push(value);
            } else {
                truncated = true;
            }
        }
    }
    if !line.is_empty() || truncated {
        emit(&line, truncated);
    }
    Ok(())
}

/// 排空失败是独立安全错误，不能把原 Cancelled 链入 source 而让调用方误报取消。
#[derive(Debug)]
pub(super) struct ControlledProcessReapFailed {
    pub code: &'static str,
    pub cancel_requested: bool,
    pub requires_new_host: bool,
    reason: String,
}

impl ControlledProcessReapFailed {
    fn new(reason: String, cancel_requested: bool) -> Self {
        Self {
            code: "worker_reap_failed",
            cancel_requested,
            requires_new_host: false,
            reason,
        }
    }
}

impl std::fmt::Display for ControlledProcessReapFailed {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            formatter,
            "{}：{}；cancel_requested={}；requires_new_host={}；尚未证明完整回收，保留事务现场",
            self.code, self.reason, self.cancel_requested, self.requires_new_host
        )
    }
}
impl std::error::Error for ControlledProcessReapFailed {}

fn controlled_reap_result(
    result: Result<std::process::ExitStatus>,
    reaped: Result<()>,
    cancel_requested: bool,
) -> Result<std::process::ExitStatus> {
    if let Err(error) = reaped {
        let mut failure = ControlledProcessReapFailed::new(format!("{error:#}"), cancel_requested);
        failure.requires_new_host = error
            .downcast_ref::<ControlledReaderReapFailed>()
            .is_some_and(|error| error.unjoined);
        return Err(failure.into());
    }
    result
}

#[derive(Debug)]
struct ControlledReaderReapFailed {
    message: String,
    unjoined: bool,
    read_os_errors: Vec<Option<i32>>,
}
impl std::fmt::Display for ControlledReaderReapFailed {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}
impl std::error::Error for ControlledReaderReapFailed {}

fn wait_controlled_child(child: &mut Child, timeout: Duration) -> Result<()> {
    wait_controlled_child_until(child, Instant::now() + timeout)
}

fn wait_controlled_child_until(child: &mut Child, deadline: Instant) -> Result<()> {
    loop {
        match child.try_wait() {
            Ok(Some(_)) => {
                child.wait().context("回收受管 Child handle 失败")?;
                return Ok(());
            }
            Ok(None) if Instant::now() < deadline => thread::sleep(Duration::from_millis(10)),
            Ok(None) => bail!("受管 Child 未在有界收尾内退出：pid={}", child.id()),
            Err(error) => return Err(error).context("查询受管 Child 退出状态失败"),
        }
    }
}

struct ControlledReader {
    worker: thread::JoinHandle<Result<()>>,
    // Rust的Windows ChildStdout/ChildStderr使用overlapped I/O，必须按pipe取消。
    // 独立持有duplicate直到join之后，避免reader先drop导致裸handle被系统复用。
    #[cfg(windows)]
    pipe: Option<std::os::windows::io::OwnedHandle>,
}

impl From<thread::JoinHandle<Result<()>>> for ControlledReader {
    fn from(worker: thread::JoinHandle<Result<()>>) -> Self {
        Self {
            worker,
            #[cfg(windows)]
            pipe: None,
        }
    }
}

impl ControlledReader {
    fn is_finished(&self) -> bool {
        self.worker.is_finished()
    }

    fn request_io_cancel(&self) -> Option<i32> {
        #[cfg(windows)]
        {
            use std::os::windows::io::AsRawHandle;
            // ERROR_NOT_FOUND只说明当前没有pending I/O；read可能尚未提交。
            // 调用方会在既有deadline内重复取消，并以实际join为完成证明。
            let error = self.pipe.as_ref().and_then(|pipe| {
                (unsafe {
                    windows_sys::Win32::System::IO::CancelIoEx(
                        pipe.as_raw_handle() as _,
                        std::ptr::null(),
                    )
                } == 0)
                    .then(|| std::io::Error::last_os_error().raw_os_error())
                    .flatten()
            });
            // 非pipe的同步线程仍沿用同步取消；不能用它替代overlapped取消。
            unsafe {
                windows_sys::Win32::System::IO::CancelSynchronousIo(
                    self.worker.as_raw_handle() as _
                );
            }
            error
        }
        #[cfg(not(windows))]
        None
    }
}

#[cfg(test)]
fn join_controlled_readers(
    threads: Vec<ControlledReader>,
    stop: &Arc<std::sync::atomic::AtomicBool>,
    allow_drain: bool,
) -> Result<()> {
    join_controlled_readers_until(
        threads,
        stop,
        allow_drain,
        Instant::now() + Duration::from_secs(2),
    )
}

fn join_controlled_readers_until(
    threads: Vec<ControlledReader>,
    stop: &Arc<std::sync::atomic::AtomicBool>,
    allow_drain: bool,
    cleanup_deadline: Instant,
) -> Result<()> {
    // 即使 Job 已 active=0，也不信任管道一定结束：异常外部 handle 或 logger
    // 阻塞不能把UI/变更租约无限占住。正常路径先给reader一秒读完有界尾部。
    if allow_drain {
        let deadline = cleanup_deadline.min(Instant::now() + Duration::from_secs(1));
        while threads.iter().any(|reader| !reader.is_finished()) && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(5));
        }
    }
    let interrupted = threads.iter().any(|reader| !reader.is_finished());
    let mut cancel_errors = vec![None; threads.len()];
    if interrupted {
        stop.store(true, std::sync::atomic::Ordering::Release);
        let deadline = cleanup_deadline.min(Instant::now() + Duration::from_secs(1));
        while threads.iter().any(|reader| !reader.is_finished()) && Instant::now() < deadline {
            for (index, reader) in threads.iter().enumerate() {
                if !reader.is_finished() {
                    cancel_errors[index] = reader.request_io_cancel();
                }
            }
            thread::sleep(Duration::from_millis(10));
        }
    }
    let mut failures = Vec::new();
    let mut unjoined = false;
    let mut read_os_errors = Vec::new();
    if interrupted && allow_drain {
        failures.push("输出未在正常收尾内结束，已请求停止同步读取".to_string());
    }
    for (index, reader) in threads.into_iter().enumerate() {
        if !reader.is_finished() {
            // 最后保险只放弃等待本次线程，不能授回收或恢复。stop 已置位，
            // 线程随后返回仍关闭自己的pipe；typed错误的持久屏障由事务层保存。
            failures.push(format!(
                "输出线程未在有界取消后退出，不能证明reader已回收；pipe_cancel_os_error={:?}",
                cancel_errors[index]
            ));
            unjoined = true;
        } else {
            match reader.worker.join() {
                Ok(Ok(())) => {}
                Ok(Err(error)) => {
                    read_os_errors.push(
                        error
                            .downcast_ref::<std::io::Error>()
                            .and_then(|e| e.raw_os_error()),
                    );
                    failures.push(format!("输出线程读取错误：{error:#}"));
                }
                Err(_) => failures.push("输出线程异常退出".to_string()),
            }
        }
    }
    if failures.is_empty() {
        Ok(())
    } else {
        Err(ControlledReaderReapFailed {
            message: failures.join("；"),
            unjoined,
            read_os_errors,
        }
        .into())
    }
}

fn combine_controlled_reap_results(first: Result<()>, second: Result<()>) -> Result<()> {
    match (first, second) {
        (Ok(()), result) | (result, Ok(())) => result,
        (Err(first), Err(second)) => {
            // 两个收尾错误都必须保留；后来的已join错误不能抹掉先前的宿主屏障。
            let unjoined = [&first, &second].iter().any(|error| {
                error
                    .downcast_ref::<ControlledReaderReapFailed>()
                    .is_some_and(|failure| failure.unjoined)
            });
            let read_os_errors = [&first, &second]
                .iter()
                .filter_map(|error| error.downcast_ref::<ControlledReaderReapFailed>())
                .flat_map(|failure| failure.read_os_errors.iter().copied())
                .collect();
            Err(ControlledReaderReapFailed {
                message: format!("{first:#}；{second:#}"),
                unjoined,
                read_os_errors,
            }
            .into())
        }
    }
}

struct ControlledLogDispatch {
    logger: Logger,
    stop: Arc<std::sync::atomic::AtomicBool>,
    dropped: Arc<std::sync::atomic::AtomicU64>,
    worker: thread::JoinHandle<Result<()>>,
}

fn controlled_log_dispatch(log: &Logger) -> ControlledLogDispatch {
    use std::sync::{atomic::Ordering, mpsc};
    // 只为本次executor输出隔离回调。固定容量/单条上界，绝不阻塞取消或Job回收。
    // stderr失败尾部由ControlledOutputTail独立保留，不依赖此可丢弃的展示队列。
    const CAPACITY: usize = 64;
    let (send, receive) = mpsc::sync_channel::<String>(CAPACITY);
    let dropped = Arc::new(std::sync::atomic::AtomicU64::new(0));
    let count = dropped.clone();
    let logger: Logger = Arc::new(move |mut line| {
        if line.len() > CONTROLLED_LINE_LIMIT {
            let mut end = CONTROLLED_LINE_LIMIT;
            while !line.is_char_boundary(end) {
                end -= 1;
            }
            line.truncate(end);
            line.push_str(" [日志正文已截断]");
        }
        if send.try_send(line).is_err() {
            let _ = count.fetch_update(Ordering::Relaxed, Ordering::Relaxed, |value| {
                Some(value.saturating_add(1))
            });
        }
    });
    let stop = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let stopped = stop.clone();
    let count = dropped.clone();
    let target = log.clone();
    let worker = thread::spawn(move || {
        let mut reported = 0;
        loop {
            if stopped.load(Ordering::Acquire) {
                return Ok(());
            }
            let line = match receive.recv_timeout(Duration::from_millis(20)) {
                Ok(line) => Some(line),
                Err(mpsc::RecvTimeoutError::Timeout) => continue,
                Err(mpsc::RecvTimeoutError::Disconnected) => None,
            };
            let total = count.load(Ordering::Relaxed);
            if total > reported {
                target(format!(
                    "[日志拥堵，累计已省略{total}条展示日志；失败详情保留独立有界尾部]"
                ));
                reported = total;
            }
            match line {
                Some(line) => target(line),
                None => return Ok(()),
            }
        }
    });
    ControlledLogDispatch {
        logger,
        stop,
        dropped,
        worker,
    }
}

/// 与Engine长锁无关的受管等待。始终仍持有 Job 时终止并确认 active=0，
/// 再等待 Child 与 reader；正常退出也不能留下没有继承 pipe 的后代。
fn execute_controlled(
    mut command: Command,
    log: &Logger,
    cancel: &crate::operations::CancelToken,
) -> Result<()> {
    cancel.check()?;
    command.stdout(Stdio::piped()).stderr(Stdio::piped());
    let (child, job) = managed_child::spawn(&mut command)?;
    execute_controlled_child(child, &job, log, cancel)
}

fn execute_controlled_in_job(
    mut command: Command,
    log: &Logger,
    cancel: &crate::operations::CancelToken,
    job: &Job,
    attached: impl FnOnce(u32) -> Result<()>,
) -> Result<()> {
    cancel.check()?;
    command.stdout(Stdio::piped()).stderr(Stdio::piped());
    let child = managed_child::spawn_in_job(&mut command, job, attached)?;
    execute_controlled_child(child, job, log, cancel)
}

fn execute_controlled_child(
    mut child: Child,
    job: &Job,
    log: &Logger,
    cancel: &crate::operations::CancelToken,
) -> Result<()> {
    let pid = child.id();
    #[cfg(windows)]
    let pipe_handles = {
        use std::os::windows::io::AsHandle;
        let handles = (|| -> Result<_> {
            Ok([
                child
                    .stdout
                    .as_ref()
                    .map(|pipe| pipe.as_handle().try_clone_to_owned())
                    .transpose()?,
                child
                    .stderr
                    .as_ref()
                    .map(|pipe| pipe.as_handle().try_clone_to_owned())
                    .transpose()?,
            ])
        })();
        match handles {
            Ok(handles) => handles,
            Err(error) => {
                // 尚未启动reader/logger；复制handle失败也须先回收已启动的子进程。
                let deadline = Instant::now() + Duration::from_secs(9);
                let reaped = combine_controlled_reap_results(
                    job.terminate_and_wait_until(deadline),
                    wait_controlled_child_until(&mut child, deadline),
                );
                return controlled_reap_result(
                    Err(error.context("保留受管pipe取消句柄失败")),
                    reaped,
                    cancel.is_cancel_requested(),
                )
                .map(|_| ());
            }
        }
    };
    let ControlledLogDispatch {
        logger: log,
        stop: logger_stop,
        dropped,
        worker: logger_worker,
    } = controlled_log_dispatch(log);
    log(format!("受管子进程已绑定Job：{}", child.id()));
    let tail = Arc::new(Mutex::new(ControlledOutputTail::default()));
    let stop = Arc::new(std::sync::atomic::AtomicBool::new(false));
    let pipes: Vec<(bool, Box<dyn Read + Send>)> = [
        child
            .stdout
            .take()
            .map(|pipe| (false, Box::new(pipe) as Box<dyn Read + Send>)),
        child
            .stderr
            .take()
            .map(|pipe| (true, Box::new(pipe) as Box<dyn Read + Send>)),
    ]
    .into_iter()
    .flatten()
    .collect();
    let threads: Vec<_> = pipes
        .into_iter()
        .map(|(stderr, pipe)| {
            let logger = log.clone();
            let tail = tail.clone();
            let stop = stop.clone();
            ControlledReader::from(thread::spawn(move || {
                read_controlled_pipe(pipe, stderr, logger, tail, stop)
            }))
        })
        .collect();
    #[cfg(windows)]
    let threads = {
        let mut handles = pipe_handles.into_iter().flatten();
        threads
            .into_iter()
            .map(|mut reader| {
                reader.pipe = handles.next();
                reader
            })
            .collect()
    };
    let result: Result<std::process::ExitStatus> = loop {
        if cancel.is_cancel_requested() {
            break Err(crate::operations::Cancelled.into());
        }
        match child.try_wait() {
            Ok(Some(status)) => break Ok(status),
            Ok(None) => thread::sleep(Duration::from_millis(20)),
            Err(error) => {
                break Err(error.into());
            }
        }
    };
    let started = Instant::now();
    // 所有回收步骤共用一个期限，预留一秒调度余量，不为每个reader/logger叠加10秒。
    let cleanup_deadline = started + Duration::from_secs(9);
    let mut reaped =
        job.terminate_and_wait_until(cleanup_deadline.min(Instant::now() + Duration::from_secs(5)));
    if reaped.is_ok() {
        log(format!(
            "受管Job已排空：pid={pid} active=0 elapsed_ms={}",
            started.elapsed().as_millis()
        ));
    } else {
        // 排空失败仍尝试回收本次父进程；不以 kill 成功替代整个 Job 的证明。
        let _ = child.kill();
    }
    let child_wait = wait_controlled_child_until(
        &mut child,
        cleanup_deadline.min(Instant::now() + Duration::from_secs(1)),
    );
    reaped = combine_controlled_reap_results(reaped, child_wait);
    let readers = join_controlled_readers_until(threads, &stop, reaped.is_ok(), cleanup_deadline);
    reaped = combine_controlled_reap_results(reaped, readers);
    if reaped.is_ok() {
        log(format!(
            "受管Child与reader已回收：pid={pid} child_wait=true readers_joined=true"
        ));
    }
    // 此时才关闭展示队列；仍活的reader只持非阻塞发送端，不能反向阻住收尾。
    // logger若卡在用户回调，整个executor仍须有界返回，并要求旧宿主退出后恢复。
    drop(log);
    let logger_reaped = join_controlled_readers_until(
        vec![logger_worker.into()],
        &logger_stop,
        reaped.is_ok(),
        cleanup_deadline,
    )
    .context(format!(
        "受管日志线程回收失败；累计省略展示日志数={}",
        dropped.load(std::sync::atomic::Ordering::Relaxed),
    ));
    reaped = combine_controlled_reap_results(reaped, logger_reaped);
    // 仅在完整回收后才保留原 Cancelled/进程错误；回收失败具有最高优先级。
    let status = controlled_reap_result(result, reaped, cancel.is_cancel_requested())?;
    cancel.check()?;
    if !status.success() {
        let detail = tail.lock().unwrap().failure_detail();
        bail!("子任务失败（{status}）\n{detail}");
    }
    Ok(())
}

impl Engine {
    pub fn catalog_control(
        &mut self,
        root: &Path,
        action: &str,
        fixture_case: Option<&str>,
    ) -> Result<serde_json::Value> {
        match action {
            "status" => crate::signed_catalog::status(root),
            "history" => crate::signed_catalog::history(root),
            "open_fixture" | "refresh" => {
                self.reap();
                if self.lifecycle.has_process() {
                    bail!("请先停止训练器再变更清单信任");
                }
                let id = self.default_release().id.clone();
                let ctx = model::WorkspaceMutation::acquire(root, &id)?;
                assert_regular_ready(root)?;
                let result = if action == "open_fixture" {
                    crate::signed_catalog::open_fixture_session(&ctx, "signed-catalog-v1")?
                } else {
                    crate::signed_catalog::refresh(&ctx, fixture_case)?
                };
                self.catalog = Catalog::for_workspace(root)?;
                Ok(result)
            }
            _ => bail!("未知清单动作"),
        }
    }
    pub fn preview_data_import(
        &self,
        root: &Path,
        request: &crate::data_import::ImportRequest,
    ) -> Result<serde_json::Value> {
        self.catalog.release(&request.release_id)?;
        let plan = crate::data_import::preview(root, request)?;
        Ok(serde_json::to_value(plan)?)
    }
    pub fn preview_profile_binding(
        &self,
        root: &Path,
        id: &str,
        profile: &str,
        rollback: bool,
    ) -> Result<crate::data_import::BindingPlan> {
        if rollback {
            return crate::data_import::rollback_plan(root);
        }
        self.catalog.release(id)?;
        model::validate_component(profile)?;
        let registry = Registry::load(root)?;
        let gui = registry
            .gui_binding(id)
            .context("目标发布缺少已验证GUI环境")?;
        let mut ids = BTreeMap::from([("gui".into(), gui.instance_id.clone())]);
        let mut generations = BTreeMap::from([("gui".into(), gui.generation)]);
        for engine in ["kohya", "anima-fast", "ai-toolkit", "diffsynth"] {
            let path = root
                .join("state/engines")
                .join(id)
                .join(engine)
                .join("state.json");
            if path.exists() {
                Layout::new(root, id)?.guard_path(&path)?;
                let value: serde_json::Value = serde_json::from_slice(&fs::read(&path)?)?;
                if value["dirty"] == false
                    && value["status"] == "ready"
                    && value["generation"] == value["validated_generation"]
                {
                    ids.insert(
                        engine.into(),
                        value["instance_id"]
                            .as_str()
                            .context("引擎实例身份不完整")?
                            .into(),
                    );
                    generations.insert(
                        engine.into(),
                        value["generation"].as_u64().context("引擎代次不完整")?,
                    );
                }
            }
        }
        let sidecar = root.join("state/profile-bindings.json");
        Layout::new(root, id)?.guard_path(&sidecar)?;
        let generation = if sidecar.exists() {
            let value: serde_json::Value = serde_json::from_slice(&fs::read(sidecar)?)?;
            value["generation"].as_u64().context("资料组合代次无效")?
        } else {
            0
        };
        crate::data_import::preview_binding(
            root,
            &crate::data_import::BindingRequest {
                binding: crate::data_import::Binding {
                    release_id: id.into(),
                    profile_id: profile.into(),
                    profile_schema_version: model::PROFILE_SCHEMA_VERSION,
                    environment_instance_ids: ids,
                    environment_generations: generations,
                    healthy_at: None,
                },
                expected_generation: generation,
            },
        )
    }
    #[allow(clippy::too_many_arguments)]
    pub fn data_operation(
        &mut self,
        root: &Path,
        id: &str,
        action: &str,
        request: Option<&crate::data_import::ImportRequest>,
        binding: Option<&crate::data_import::BindingRequest>,
        sha: Option<&str>,
        transaction: Option<&str>,
        operation: &crate::operations::OperationHandle,
    ) -> Result<()> {
        use crate::operations::{Cancelled, OperationError, OperationPhase, OperationStatus};
        self.reap();
        if self.lifecycle.has_process() {
            bail!("请先停止训练器再变更资料组合");
        }
        let release = self.catalog.release(id)?.clone();
        let ctx = model::WorkspaceMutation::acquire(root, id)?;
        crate::shell_update_protocol::assert_ready(root)?;
        legacy_environment_repair::assert_ready(root, Some(&operation.cancel_token()))?;
        gui_repair::assert_worker_reap_ready(root)?;
        if action != "recover_binding" {
            assert_regular_ready(root)?;
        }
        operation.persist(&ctx)?;
        let cancel = operation.cancel_token();
        let result = (|| -> Result<()> {
            operation.publish(
                OperationPhase::Executing,
                "在独立事务中变更资料，保留原安装与资料",
            )?;
            match action {
                "import" => {
                    let request = request.context("缺少已审阅导入请求")?;
                    if request.release_id != id {
                        bail!("导入目标发布不符");
                    }
                    crate::data_import::execute(
                        &ctx,
                        request,
                        sha.context("缺少导入计划摘要")?,
                        &cancel,
                    )?;
                }
                "recover_import" => {
                    crate::data_import::recover(
                        &ctx,
                        transaction.context("缺少导入事务")?,
                        &cancel,
                    )?;
                }
                "binding" => {
                    let request = binding.context("缺少已审阅资料组合")?;
                    if request.binding.release_id != id {
                        bail!("资料组合发布与执行目标不符");
                    }
                    crate::signed_catalog::authorize(root, id, "activate")?;
                    crate::data_import::execute_binding(
                        &ctx,
                        request,
                        sha.context("缺少组合计划摘要")?,
                        |target, profile| {
                            let mut layout = ctx.layout().clone();
                            layout.profile = profile.to_path_buf();
                            let gui = Registry::load(root)?
                                .gui_binding(id)
                                .cloned()
                                .context("缺少GUI绑定")?;
                            if target.environment_instance_ids.get("gui") != Some(&gui.instance_id)
                            {
                                bail!("GUI绑定变化");
                            }
                            let recipe = crate::recipe::GuiRecipe::embedded()?;
                            gui_install::validate_environment(
                                &layout,
                                &recipe,
                                &layout.environment,
                                &self.logger,
                                &cancel,
                            )?;
                            let transaction = format!("gui-rebuild-profile-{}", model::now());
                            gui_entry_probe::probe_profile(
                                &ctx,
                                &release,
                                &layout.environment,
                                &transaction,
                                Some(profile),
                                &self.logger,
                                &cancel,
                            )?;
                            Ok(())
                        },
                    )?;
                }
                "recover_binding" => crate::data_import::recover_binding(
                    &ctx,
                    transaction.context("缺少资料组合事务编号")?,
                )?,
                _ => bail!("未知资料操作"),
            }
            Ok(())
        })();
        let (status, error) = match &result {
            Ok(()) => (OperationStatus::Succeeded, None),
            Err(e) if e.downcast_ref::<Cancelled>().is_some() => (OperationStatus::Cancelled, None),
            Err(e) => (
                OperationStatus::Failed,
                Some(OperationError {
                    code: "data_operation_failed".into(),
                    message: format!("{e:#}"),
                }),
            ),
        };
        operation.finish_and_persist(&ctx, status, error)?;
        result
    }
    /// 诊断与计划不依赖长操作持有的 Engine mutex。
    pub fn query_engine_readonly(
        root: &Path,
        release_id: &str,
        engine: &str,
        action: &str,
        rebuild: bool,
        log: &Logger,
    ) -> Result<serde_json::Value> {
        let catalog = Catalog::for_workspace(root)?;
        engine_bridge::query(
            root,
            catalog.release(release_id)?,
            engine,
            action,
            rebuild,
            log,
        )
    }
    pub fn engine_fixture_smoke(&mut self, root: &Path) -> Result<serde_json::Value> {
        self.reap();
        if self.lifecycle.has_process() {
            bail!("请先停止受管训练器，再执行固定沙盒冒烟");
        }
        if crate::signed_catalog::status(root)?["fixture_session"] != true {
            bail!("引擎冒烟仅允许显式签名沙盒会话");
        }
        engine_bridge::fixture_smoke(root, self.default_release(), &self.logger)
    }
    pub fn engine_operation(
        &mut self,
        root: &Path,
        id: &str,
        engine: &str,
        action: &str,
        plan: Option<&serde_json::Value>,
        operation: &crate::operations::OperationHandle,
    ) -> Result<()> {
        use crate::operations::{Cancelled, OperationError, OperationStatus};
        self.reap();
        let release = self.catalog.release(id)?.clone();
        legacy_environment_repair::assert_ready(root, Some(&operation.cancel_token()))?;
        gui_repair::assert_worker_reap_ready(root)?;
        let result = engine_bridge::apply(
            root,
            &release,
            engine,
            action,
            plan,
            operation,
            &self.logger,
        );
        let (status, error) = match &result {
            Ok(()) => (OperationStatus::Succeeded, None),
            Err(error) if error.downcast_ref::<Cancelled>().is_some() => {
                (OperationStatus::Cancelled, None)
            }
            Err(error) => (
                OperationStatus::Failed,
                Some(OperationError {
                    code: "engine_operation_failed".into(),
                    message: format!("{error:#}"),
                }),
            ),
        };
        let ctx = model::WorkspaceMutation::acquire_shared(root, id)?;
        operation.finish_and_persist(&ctx, status, error)?;
        result
    }
    pub fn preview_base_python_repair(&self, root: &Path) -> Result<serde_json::Value> {
        base_python_repair::preview(root, &self.catalog)
    }
    pub fn repair_base_python_operation(
        &mut self,
        root: &Path,
        id: &str,
        plan_sha256: Option<&str>,
        operation: &crate::operations::OperationHandle,
    ) -> Result<()> {
        let _network = crate::network_policy::task_policy(root)?;
        self.reap();
        if self.lifecycle.has_process() {
            bail!("请先停止受管训练器，再恢复基础Python组件");
        }
        self.catalog.release(id)?;
        let ctx = model::WorkspaceMutation::acquire(root, id)?;
        crate::data_import::assert_binding_ready(root)?;
        crate::shell_update_protocol::assert_ready(root)?;
        legacy_environment_repair::assert_ready(root, Some(&operation.cancel_token()))?;
        gui_repair::assert_worker_reap_ready(root)?;
        assert_registration_ready(root, None)?;
        let recipe = crate::recipe::GuiRecipe::embedded()?;
        let log = self.logger.clone();
        let mut validator = |layout: &Layout,
                             release: &Release,
                             environment: &Path,
                             cancel: &crate::operations::CancelToken|
         -> Result<()> {
            if !recipe.matches_environment_recipe(&release.environment_recipe)
                || release.commit != recipe.source_commit
            {
                bail!("受影响环境没有匹配的固定验证器，保留组件恢复门");
            }
            verify_source(layout, release)?;
            if digest(&uv(&layout.root))? != recipe.tool_uv.exe_sha256 {
                bail!("基础组件复验前uv身份检查未通过");
            }
            gui_install::validate_environment(layout, &recipe, environment, &log, cancel)
        };
        match plan_sha256 {
            Some(plan) => base_python_repair::execute(
                &ctx,
                &self.catalog,
                plan,
                operation,
                &self.logger,
                &mut validator,
            ),
            None => base_python_repair::recover(
                &ctx,
                &self.catalog,
                operation,
                &self.logger,
                &mut validator,
            ),
        }?;
        crate::data_import::sync_current_environment(&ctx, id)
    }
    pub fn preview_source_repair(&self, root: &Path, id: &str) -> Result<serde_json::Value> {
        gui_source_repair::preview(root, self.catalog.release(id)?)
    }
    pub fn preview_gui_registration(
        &self,
        root: &Path,
        id: &str,
        instance_id: Option<&str>,
    ) -> Result<serde_json::Value> {
        gui_registration::preview(root, self.catalog.release(id)?, instance_id)
    }
    pub fn restore_gui_registration_operation(
        &mut self,
        root: &Path,
        id: &str,
        reviewed: Option<(&str, &str)>,
        operation: &crate::operations::OperationHandle,
    ) -> Result<()> {
        use crate::operations::{Cancelled, OperationError, OperationPhase, OperationStatus};
        let _network = crate::network_policy::task_policy(root)?;
        self.reap();
        if self.lifecycle.has_process() {
            bail!("请先停止受管训练器，再恢复安装登记");
        }
        let release = self.catalog.release(id)?.clone();
        let ctx = model::WorkspaceMutation::acquire(root, id)?;
        crate::data_import::assert_binding_ready(root)?;
        crate::shell_update_protocol::assert_ready(root)?;
        base_python_repair::assert_ready(root)?;
        legacy_environment_repair::assert_ready(root, Some(&operation.cancel_token()))?;
        gui_repair::assert_worker_reap_ready(root)?;
        assert_registration_ready(root, Some(id))?;
        operation.persist(&ctx)?;
        let cancel = operation.cancel_token();
        let recipe = crate::recipe::GuiRecipe::embedded()?;
        let validator = |environment: &Path| {
            gui_install::validate_environment_runtime(
                ctx.layout(),
                &recipe,
                environment,
                &self.logger,
                &cancel,
            )
        };
        let entry_probe = |environment: &Path, transaction: &str| {
            let receipt = gui_entry_probe::probe(
                &ctx,
                &release,
                environment,
                transaction,
                &self.logger,
                &cancel,
            )?;
            (self.logger)(format!(
                "独立资料入口验证完成：{}",
                serde_json::to_string(&receipt)?
            ));
            Ok(())
        };
        let result = (|| {
            operation.publish(
                OperationPhase::Verifying,
                "离线核验已有环境与独立资料入口，恢复缺失登记",
            )?;
            operation.persist(&ctx)?;
            match reviewed {
                Some((instance, plan)) => gui_registration::execute(
                    &ctx,
                    &release,
                    plan,
                    Some(instance),
                    &cancel,
                    validator,
                    entry_probe,
                ),
                None => gui_registration::recover(&ctx, &release, &cancel, validator, entry_probe),
            }
        })()
        .and_then(|value| {
            crate::data_import::sync_current_environment(&ctx, id)?;
            Ok(value)
        });
        let (status, error) = match &result {
            Ok(_) => (OperationStatus::Succeeded, None),
            Err(error) if error.downcast_ref::<Cancelled>().is_some() => {
                (OperationStatus::Cancelled, None)
            }
            Err(error) => (
                OperationStatus::Failed,
                Some(OperationError {
                    code: "gui_registration_failed".into(),
                    message: format!("{error:#}"),
                }),
            ),
        };
        operation.finish_and_persist(&ctx, status, error)?;
        result.map(|_| ())
    }
    pub fn preview_gui_lifecycle(
        &self,
        root: &Path,
        id: &str,
        action: &str,
        transaction: Option<&str>,
    ) -> Result<serde_json::Value> {
        let release = self.catalog.release(id)?;
        match action {
            "rebuild" => gui_rebuild::preview(root, release),
            "rollback" => {
                gui_rebuild::rollback_preview(root, release, transaction.context("请选择重建历史")?)
            }
            "history" => gui_rebuild::history(root, release),
            "preserved" => gui_rebuild::preserved_pending(root, release),
            _ => bail!("未知实例操作"),
        }
    }
    #[allow(clippy::too_many_arguments)]
    pub fn gui_lifecycle_operation(
        &mut self,
        root: &Path,
        id: &str,
        action: &str,
        plan: Option<&str>,
        transaction: Option<&str>,
        instance: Option<&str>,
        operation: &crate::operations::OperationHandle,
    ) -> Result<()> {
        use crate::operations::OperationPhase;
        // 参数拒绝早于租约和任务持久化；未知动作不能初始化错误目录。
        match action {
            "rebuild" => {
                plan.context("缺少重建预览摘要")?;
            }
            "rollback" => {
                plan.context("缺少回退预览摘要")?;
                transaction.context("缺少重建历史")?;
            }
            "recover_rebuild" | "recover_rollback" => {
                model::validate_component(transaction.context("缺少恢复事务")?)?;
            }
            "recover_preserved" => {
                model::validate_component(instance.context("请选择保留实例")?)?;
            }
            _ => bail!("未知实例变更动作"),
        }
        let release = self.catalog.release(id)?.clone();
        let _network = crate::network_policy::task_policy(root)?;
        self.reap();
        if self.lifecycle.has_process() {
            bail!("请先停止训练器，再变更环境实例");
        }
        let ctx = if matches!(
            action,
            "recover_rebuild" | "recover_rollback" | "recover_preserved"
        ) {
            model::WorkspaceMutation::acquire_existing(root, id)?
        } else {
            model::WorkspaceMutation::acquire(root, id)?
        };
        let cancel = operation.cancel_token();
        let preflight = (|| -> Result<()> {
            crate::data_import::assert_binding_ready(root)?;
            crate::shell_update_protocol::assert_ready(root)?;
            base_python_repair::assert_ready(root)?;
            legacy_environment_repair::assert_ready(root, Some(&cancel))?;
            gui_repair::assert_worker_reap_ready(root)?;
            assert_registration_ready(root, None)?;
            if action == "recover_rebuild" {
                gui_rebuild::assert_ready_except_recovery_with_cancel(
                    root,
                    &release,
                    transaction.context("缺少重建事务")?,
                    Some(&cancel),
                )?;
            } else {
                gui_rebuild::assert_ready_with_cancel(root, &release, Some(&cancel))?;
            }
            let rollback_recovery = (action == "recover_rollback")
                .then(|| (&release, transaction.expect("恢复事务已校验")));
            gui_binding_switch::assert_all_ready_with_cancel(
                root,
                rollback_recovery,
                Some(&cancel),
            )?;
            if action != "recover_preserved" {
                instances::assert_no_preserved_pending(root)?;
            }
            cancel.check()?;
            Ok(())
        })();
        if let Err(error) = preflight {
            if error
                .downcast_ref::<crate::operations::Cancelled>()
                .is_some()
            {
                operation.persist(&ctx)?;
                return finish_gui_lifecycle_result(&ctx, operation, Err(error));
            }
            return Err(error);
        }
        operation.persist(&ctx)?;
        let recipe = crate::recipe::GuiRecipe::embedded()?;
        let validator = |environment: &Path| {
            gui_install::validate_environment_runtime(
                ctx.layout(),
                &recipe,
                environment,
                &self.logger,
                &cancel,
            )
        };
        let entry = |environment: &Path, transaction: &str| {
            gui_entry_probe::probe(
                &ctx,
                &release,
                environment,
                transaction,
                &self.logger,
                &cancel,
            )
            .map(|_| ())
        };
        let result = (|| -> Result<()> {
            operation.publish(
                OperationPhase::Executing,
                "执行已确认的实例操作，保留旧实例和资料",
            )?;
            operation.persist(&ctx)?;
            match action {
                "rebuild" => gui_rebuild::execute(
                    &ctx,
                    &release,
                    plan.context("缺少重建预览摘要")?,
                    &cancel,
                    |environment| {
                        gui_install::build_replacement(
                            &ctx,
                            &release,
                            environment,
                            operation,
                            &self.logger,
                        )
                    },
                    validator,
                    entry,
                )
                .map(|_| ()),
                "recover_rebuild" => gui_rebuild::recover(
                    &ctx,
                    &release,
                    transaction.context("缺少重建事务")?,
                    &cancel,
                    validator,
                    entry,
                )
                .map(|_| ()),
                "rollback" => gui_rebuild::rollback(
                    &ctx,
                    &release,
                    transaction.context("缺少重建历史")?,
                    plan.context("缺少回退预览摘要")?,
                    &cancel,
                    validator,
                    entry,
                )
                .map(|_| ()),
                "recover_rollback" => gui_rebuild::recover_rollback(
                    &ctx,
                    &release,
                    transaction.context("缺少回退恢复事务")?,
                    &cancel,
                    validator,
                    entry,
                )
                .map(|_| ()),
                "recover_preserved" => {
                    gui_rebuild::assert_ready_with_cancel(root, &release, Some(&cancel))?;
                    gui_binding_switch::assert_ready_with_cancel(root, &release, Some(&cancel))?;
                    instances::recover_preserved_controlled(
                        &ctx,
                        instance.context("请选择保留实例")?,
                        &cancel,
                        |environment| {
                            gui_install::validate_environment(
                                ctx.layout(),
                                &recipe,
                                environment,
                                &self.logger,
                                &cancel,
                            )?;
                            entry(
                                environment,
                                &format!(
                                    "gui-rebuild-preserved-{}",
                                    instance.context("缺少保留实例")?
                                ),
                            )
                        },
                    )
                    .map(|_| ())
                }
                _ => bail!("未知实例变更动作"),
            }
        })()
        .and_then(|()| complete_gui_lifecycle_success(&ctx, id, &cancel));
        finish_gui_lifecycle_result(&ctx, operation, result)
    }
    pub fn repair_source_operation(
        &mut self,
        root: &Path,
        id: &str,
        operation: &crate::operations::OperationHandle,
    ) -> Result<()> {
        let _network = crate::network_policy::task_policy(root)?;
        self.reap();
        if self.lifecycle.has_process() {
            bail!("请先停止受管训练器，再修复源码");
        }
        let release = self.catalog.release(id)?;
        let ctx = model::WorkspaceMutation::acquire(root, id)?;
        assert_regular_ready(root)?;
        gui_source_repair::execute(&ctx, release, operation, &self.logger)
    }
    pub fn diagnose_gui(&self, root: &Path, id: &str) -> Result<serde_json::Value> {
        Ok(serde_json::to_value(gui_repair::diagnose(
            root,
            self.catalog.release(id)?,
        )?)?)
    }
    pub fn plan_gui_repair(
        &self,
        root: &Path,
        id: &str,
        package: &str,
    ) -> Result<serde_json::Value> {
        Ok(serde_json::to_value(gui_repair::plan(
            root,
            self.catalog.release(id)?,
            package,
        )?)?)
    }
    pub fn repair_gui_operation(
        &mut self,
        root: &Path,
        id: &str,
        package: &str,
        plan_sha256: &str,
        operation: &crate::operations::OperationHandle,
    ) -> Result<()> {
        let _network = crate::network_policy::task_policy(root)?;
        self.reap();
        if self.lifecycle.has_process() {
            bail!("请先停止受管训练器，再修复环境");
        }
        let release = self.catalog.release(id)?;
        let ctx = model::WorkspaceMutation::acquire(root, id)?;
        assert_regular_ready(root)?;
        gui_repair::execute(&ctx, release, package, plan_sha256, operation, &self.logger)
    }
    pub fn recover_gui_operation(
        &mut self,
        root: &Path,
        id: &str,
        operation: &crate::operations::OperationHandle,
    ) -> Result<()> {
        let _network = crate::network_policy::task_policy(root)?;
        self.reap();
        if self.lifecycle.has_process() {
            bail!("请先停止受管训练器，再恢复环境");
        }
        let release = self.catalog.release(id)?;
        let ctx = model::WorkspaceMutation::acquire(root, id)?;
        assert_regular_ready_for_gui_recovery(root, release, &operation.cancel_token())?;
        gui_repair::recover(&ctx, release, operation, &self.logger)
    }
    pub fn install_release_operation(
        &mut self,
        root: &Path,
        id: &str,
        operation: &crate::operations::OperationHandle,
    ) -> Result<()> {
        crate::signed_catalog::authorize(root, id, "install")?;
        let _network = crate::network_policy::task_policy(root)?;
        self.reap();
        if self.lifecycle.has_process() {
            bail!("请先停止受管训练器，再修改安装目录");
        }
        let release = self.catalog.release(id)?.clone();
        assert_regular_ready(root)?;
        gui_install::install(root, &release, operation, &self.logger)
    }
    /// 只验证并完成一个既有历史安装事务，不下载、不重建、不切换版本。
    pub fn resume_legacy_install_operation(
        &mut self,
        root: &Path,
        id: &str,
        journal_sha256: &str,
        operation: &crate::operations::OperationHandle,
    ) -> Result<()> {
        crate::signed_catalog::authorize(root, id, "repair")?;
        let _network = crate::network_policy::task_policy(root)?;
        self.reap();
        if self.lifecycle.has_process() {
            bail!("请先停止受管训练器，再完成未结束的安装");
        }
        let catalog = Catalog::for_workspace(root)?;
        let release = catalog.release(id)?;
        let ctx = model::WorkspaceMutation::acquire_existing(root, id)?;
        assert_regular_ready(root)?;
        legacy_install_recovery::recover(&ctx, release, journal_sha256, operation, &self.logger)
    }
    /// 异步只读预览的正式接缝；不取得Engine互斥锁、不修改原安装事务。
    pub(crate) fn preview_legacy_environment_repair_controlled(
        root: &Path,
        id: &str,
        cancel: &crate::operations::CancelToken,
        observer: Option<&crate::query_tasks::QueryObserver>,
    ) -> Result<serde_json::Value> {
        cancel.check()?;
        crate::signed_catalog::authorize(root, id, "repair")?;
        let catalog = Catalog::for_workspace(root)?;
        let release = catalog.release(id)?;
        let original = legacy_install_recovery::candidate(root, release)?
            .context("没有可独立修复的未完成历史安装")?;
        let plan = legacy_environment_repair::plan_controlled(
            root,
            release,
            &original.journal_sha256,
            cancel,
            observer,
        )?;
        Ok(serde_json::to_value(plan)?)
    }
    pub fn repair_legacy_environment_operation(
        &mut self,
        root: &Path,
        id: &str,
        journal_sha256: &str,
        plan_sha256: &str,
        operation: &crate::operations::OperationHandle,
    ) -> Result<()> {
        crate::signed_catalog::authorize(root, id, "repair")?;
        self.reap();
        if self.lifecycle.has_process() {
            bail!("请先停止主程序，再修复其运行环境");
        }
        let catalog = Catalog::for_workspace(root)?;
        let release = catalog.release(id)?;
        let ctx = model::WorkspaceMutation::acquire_existing(root, id)?;
        let cancel = operation.cancel_token();
        assert_regular_ready_with_cancel(root, Some(&cancel))?;
        legacy_environment_repair::execute(
            &ctx,
            release,
            journal_sha256,
            plan_sha256,
            operation,
            &self.logger,
        )
    }
    pub fn recover_legacy_environment_operation(
        &mut self,
        root: &Path,
        id: &str,
        transaction: &str,
        operation: &crate::operations::OperationHandle,
    ) -> Result<()> {
        crate::signed_catalog::authorize(root, id, "repair")?;
        self.reap();
        if self.lifecycle.has_process() {
            bail!("请先停止主程序，再恢复其运行环境");
        }
        let catalog = Catalog::for_workspace(root)?;
        let release = catalog.release(id)?;
        let ctx = model::WorkspaceMutation::acquire_existing(root, id)?;
        legacy_environment_repair::recover(&ctx, release, transaction, operation, &self.logger)
    }
    /// 只预取目录中固定身份的归档；成功仅代表缓存完整，不改变安装绑定或健康状态。
    pub fn prefetch_release(
        &mut self,
        root: &Path,
        id: &str,
        operation: &crate::operations::OperationHandle,
    ) -> Result<()> {
        use crate::operations::{Cancelled, OperationError, OperationPhase, OperationStatus};
        let _network = crate::network_policy::task_policy(root)?;
        self.reap();
        if self.lifecycle.has_process() {
            bail!("请先停止受管训练器，再准备安装文件");
        }
        let release = self.catalog.release(id)?.clone();
        let mutation = model::WorkspaceMutation::acquire(root, id)?;
        assert_regular_ready(root)?;
        operation.persist(&mutation)?;
        let cancel = operation.cancel_token();
        let mut downloads = artifact_downloads::ArtifactDownloads::new();
        let result = (|| -> Result<()> {
            cancel.check()?;
            operation.publish(
                OperationPhase::Downloading,
                "正在下载并校验所选版本的安装文件",
            )?;
            operation.persist(&mutation)?;
            let name = format!("{}.zip", release.archive.sha256);
            downloads.download(
                &mutation,
                &release.archive.url,
                &name,
                &release.archive.sha256,
                release.archive.bytes,
                &cancel,
            )?;
            operation.publish(
                OperationPhase::Verifying,
                "安装文件完整校验通过，可继续安装",
            )?;
            cancel.check()?;
            Ok(())
        })();

        let (status, error) = match &result {
            Ok(()) => (OperationStatus::Succeeded, None),
            Err(error) if error.downcast_ref::<Cancelled>().is_some() => {
                (OperationStatus::Cancelled, None)
            }
            Err(error) => (
                OperationStatus::Failed,
                Some(OperationError {
                    code: "download_failed".into(),
                    message: format!("{error:#}"),
                }),
            ),
        };
        operation.finish_and_persist(&mutation, status, error)?;
        result
    }

    pub fn new(default_root: PathBuf, logger: Logger) -> Self {
        let target = logger;
        let logger: Logger = Arc::new(move |line| target(crate::network_policy::redact(&line)));
        Self {
            default_root,
            lifecycle: Lifecycle::new(),
            assessment: None,
            logger,
            service_logger: None,
            catalog: Catalog::embedded().expect("内置发布清单必须有效"),
        }
    }
    pub fn set_service_logger(&mut self, factory: ServiceLoggerFactory) {
        self.service_logger = Some(factory);
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
    pub fn save_network_settings(
        &self,
        value: &str,
        settings: &crate::network_policy::Settings,
    ) -> Result<serde_json::Value> {
        if self.lifecycle.has_process() {
            bail!("请先停止受管训练器，再保存网络设置");
        }
        let root = self.resolve(value)?;
        let policy = crate::network_policy::resolve_current(settings)?;
        let encoded = serde_json::to_vec_pretty(settings)?;
        if encoded.len() + 1 > 64 * 1024 {
            bail!("网络设置超过64KiB，尚未写入");
        }
        let ctx = model::WorkspaceMutation::acquire(&root, &self.default_release().id)?;
        assert_regular_ready(&root)?;
        let path = crate::network_policy::settings_path(&root)?;
        ctx.layout().guard_path(&path)?;
        ctx.layout()
            .ensure_dir(path.parent().context("网络设置缺少父目录")?)?;
        model::write_json_atomic(&path, settings)?;
        Ok(serde_json::json!({ "settings": settings, "diagnostic": policy.diagnostic(None) }))
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
        if self.lifecycle.has_process() {
            bail!("请先停止受管训练器，再修改安装目录");
        }
        let layout = Layout::new(root, &release.id)?;
        let lease = layout.prepare_workspace()?;
        let mut registry = Registry::load(root)?;
        assert_regular_ready(root)?;
        if !registry.reconcile(root, &self.catalog)?.is_empty() {
            registry.store(root)?;
        }
        Ok((layout, lease))
    }
    fn mutation(&mut self, root: &Path, release: &Release) -> Result<model::WorkspaceMutation> {
        self.reap();
        if self.lifecycle.has_process() {
            bail!("请先停止受管训练器，再修改安装目录");
        }
        let ctx = model::WorkspaceMutation::acquire(root, &release.id)?;
        assert_regular_ready(root)?;
        let mut registry = Registry::load(root)?;
        if !registry.reconcile(root, &self.catalog)?.is_empty() {
            registry.store(root)?;
        }
        Ok(ctx)
    }
    fn reap(&mut self) {
        self.lifecycle.reap();
    }
    pub fn inspect(&mut self, root: &Path) -> Result<Report> {
        self.catalog = Catalog::for_workspace(root)?;
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
        let runtime = self.lifecycle.snapshot(root);
        let running = runtime.pid.is_some();
        let port = runtime.port;
        let served_version = (runtime.phase == "ready")
            .then(|| runtime.version.clone())
            .flatten();
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
        let recipe = crate::recipe::GuiRecipe::embedded()?;
        let active_release_id = release.id.clone();
        for release in self.catalog.releases() {
            let l = Layout::new(root, &release.id)?;
            // Reuse the current release's checks only within this inspection.
            // No cross-call integrity cache is trusted by start or mutation.
            let current = release.id == active_release_id;
            let source_ok = owned
                && if current {
                    src.is_ok()
                } else {
                    verify_source(&l, release).is_ok()
                };
            let environment_ok = owned
                && if current {
                    environment.is_ok()
                } else {
                    check_environment(&l, release).is_ok()
                };
            versions.push(VersionView {
                legacy_environment_repair: legacy_environment_repair::pending_transaction(
                    root, release,
                )?,
                legacy_recovery: if owned {
                    legacy_install_recovery::candidate(root, release)
                        .ok()
                        .flatten()
                } else {
                    None
                },
                support: release_support(release, &recipe),
                managed_recipe: release.environment_recipe == "gui-cp310-win-x64-v1",
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
        let mut interrupted: Vec<String> = Journal::load_all(root)?
            .into_iter()
            .filter(|j| j.phase != Phase::Committed)
            .map(|j| {
                format!(
                    "{}: {:?}；请重试相应安装或修复，当前版本指针未自动更改",
                    j.release_id, j.phase
                )
            })
            .collect();
        if let Err(error) = base_python_repair::assert_ready(root) {
            interrupted.push(format!(
                "基础Python组件恢复尚未完成，暂停变更与启动：{error:#}"
            ));
        }
        if let Err(error) = assert_registration_ready(root, None) {
            interrupted.push(format!("安装登记恢复尚未完成，暂停变更与启动：{error:#}"));
        }
        if owned {
            for release in self.catalog.releases() {
                if release.environment_recipe == "gui-cp310-win-x64-v1" {
                    interrupted.extend(gui_recovery::list_unbound(root, release)?);
                }
            }
        }
        let report = Report {
            root: root.to_string_lossy().into(),
            uv: uv_ok,
            python: python.is_ok(),
            source: src.is_ok(),
            environment: environment.is_ok(),
            frontend,
            running,
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
        };
        self.assessment = Some(report.clone());
        Ok(report)
    }
    pub fn bootstrap(&mut self, root: &Path) -> Result<Report> {
        let _network = crate::network_policy::task_policy(root)?;
        let release = self.active(root)?;
        self.bootstrap_for(root, &release)?;
        self.inspect(root)
    }
    fn bootstrap_for(&mut self, root: &Path, release: &Release) -> Result<()> {
        if release.environment_recipe == "gui-cp310-win-x64-v1" {
            bail!("该版本使用完整固定配方，请执行对应版本的受管安装");
        }
        let ctx = self.mutation(root, release)?;
        let layout = ctx.layout();
        let asset = &release.uv;
        if managed_python(root, release).is_ok() {
            return Ok(());
        }
        let archive = download(
            &ctx,
            &asset.url,
            &format!("{}.zip", asset.sha256),
            &asset.sha256,
            asset.bytes,
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
        let mut command = uv_command(root, release)?;
        command.args([
            "python",
            "install",
            &release.python,
            "--no-bin",
            "--no-registry",
        ]);
        (self.logger)("历史未锁配方仅使用uv离线缓存；缺少缓存时请选择固定配方版本安装".into());
        execute(command, &self.logger)?;
        managed_python(root, release)?;
        (self.logger)("基础工具实际检查通过".into());
        Ok(())
    }
    pub fn restore(&mut self, root: &Path) -> Result<Report> {
        let _network = crate::network_policy::task_policy(root)?;
        let release = self.active(root)?;
        self.restore_for(root, &release)?;
        self.inspect(root)
    }
    fn restore_for(&mut self, root: &Path, release: &Release) -> Result<()> {
        if release.environment_recipe == "gui-cp310-win-x64-v1" {
            bail!("该版本源码与捆绑前端须共同验证，请执行对应版本的受管安装或定点修复");
        }
        let ctx = self.mutation(root, release)?;
        let layout = ctx.layout();
        if verify_source(layout, release).is_ok() {
            let mut registry = Registry::load(root)?;
            registry.record_installed(release)?;
            registry.store(root)?;
            (self.logger)("已安装源码完整，复用当前版本；没有下载".into());
            return Ok(());
        }
        let mut journal = Journal::new(&release.id)?;
        journal.store(root)?;
        let archive = download(
            &ctx,
            &release.archive.url,
            &format!("{}.zip", release.archive.sha256),
            &release.archive.sha256,
            release.archive.bytes,
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
        verify_source(layout, release)?;
        let mut registry = Registry::load(root)?;
        registry.record_installed(release)?;
        registry.store(root)?;
        journal.phase = Phase::Committed;
        journal.store(root)?;
        (self.logger)(format!("{} 源码恢复完成；用户资料未移动", release.id));
        Ok(())
    }
    pub fn install_environment(&mut self, root: &Path) -> Result<Report> {
        let _network = crate::network_policy::task_policy(root)?;
        let release = self.active(root)?;
        self.environment_for(root, &release)?;
        self.inspect(root)
    }
    fn environment_for(&mut self, root: &Path, release: &Release) -> Result<()> {
        if release.environment_recipe == "gui-cp310-win-x64-v1"
            || Registry::load(root)?.gui_binding(&release.id).is_some()
        {
            bail!("该环境使用固定配方与实例事务；请在对应版本执行受管安装或诊断修复");
        }
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
        let mut command = uv_command(root, release)?;
        command
            .args(["venv", "--seed", "--python"])
            .arg(python)
            .arg(&layout.environment);
        execute(command, &self.logger)?;
        let mut command = uv_command(root, release)?;
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
        let _network = crate::network_policy::task_policy(root)?;
        assert_regular_ready(root)?;
        let release = self.catalog.release(id)?.clone();
        if release.environment_recipe == crate::recipe::GuiRecipe::embedded()?.id() {
            self.reap();
            if self.lifecycle.has_process() {
                bail!("请先停止受管训练器");
            }
            let manager = crate::operations::OperationManager::default();
            let operation = manager.start(
                &format!("install-{}-{}", model::now(), stamp()),
                crate::operations::OperationKind::Execute,
            )?;
            gui_install::install(root, &release, &operation, &self.logger)?;
            return self.inspect(root);
        }
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
        crate::signed_catalog::authorize(root, id, "activate")?;
        if crate::data_import::has_bindings(root)? {
            assert_regular_ready(root)?;
            if Registry::load(root)?.current.as_deref() == Some(id) {
                crate::data_import::assert_current_environment(root, id)?;
                return self.inspect(root);
            }
            let plan = crate::data_import::rollback_plan(root).context(
                "已有独立资料组合；请先在资料组合入口预览并显式选择目标发布、profile和环境实例",
            )?;
            if plan.request.binding.release_id != id {
                bail!("目标不属于上一健康完整资料组合，请先在资料组合入口显式预览并选择profile和环境实例");
            }
            return self.select_profile_plan(root, plan);
        }
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
        if crate::data_import::has_bindings(root)? {
            let plan = crate::data_import::rollback_plan(root)?;
            crate::signed_catalog::authorize(root, &plan.request.binding.release_id, "rollback")?;
            return self.select_profile_plan(root, plan);
        }
        let mut registry = Registry::load(root)?;
        let id = registry.rollback(&self.catalog)?;
        crate::signed_catalog::authorize(root, &id, "rollback")?;
        self.select_release(root, &id)
    }
    fn select_profile_plan(
        &mut self,
        root: &Path,
        plan: crate::data_import::BindingPlan,
    ) -> Result<Report> {
        let id = plan.request.binding.release_id.clone();
        let manager = crate::operations::OperationManager::default();
        let operation = manager.start(
            &format!("binding-select-{}-{}", model::now(), stamp()),
            crate::operations::OperationKind::Execute,
        )?;
        self.data_operation(
            root,
            &id,
            "binding",
            None,
            Some(&plan.request),
            Some(&plan.plan_sha256),
            None,
            &operation,
        )?;
        self.inspect(root)
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
        let run_id = self.lifecycle.begin(root)?;
        self.start_reserved(root, &run_id)
    }
    pub fn start_reserved(&mut self, root: &Path, run_id: &str) -> Result<Report> {
        let result = self.start_run(root, run_id);
        if let Err(error) = &result {
            self.lifecycle.fail_start(run_id, &format!("{error:#}"));
        }
        result
    }
    fn start_run(&mut self, root: &Path, run_id: &str) -> Result<Report> {
        self.catalog = Catalog::for_workspace(root)?;
        let _network = crate::network_policy::task_policy(root)?;
        let release = self.active(root)?;
        crate::signed_catalog::authorize(root, &release.id, "activate")?;
        let candidate = Layout::new(root, &release.id)?;
        // 选择租约后仍须完整认证源码，标识本身不授予执行权限。
        // 旧训练器没有目标锁，保留其独占保护，不能只靠新壳放开旧训练进程。
        let target_leases = fs::read_to_string(candidate.app.join("mikazuki/launcher/runtime.py"))
            .is_ok_and(|text| text.contains("ENGINE_LEASE_PROTOCOL = \"engine-leases-v1\""))
            && fs::read_to_string(candidate.app.join("mikazuki/tasks.py"))
                .is_ok_and(|text| text.contains("managed_training_lease"));
        let ctx = if target_leases {
            model::WorkspaceMutation::acquire_shared(root, &release.id)?
        } else {
            model::WorkspaceMutation::acquire(root, &release.id)?
        };
        let layout = ctx.layout().clone();
        let service_path = root.join(".launcher-service-lock");
        layout.guard_path(&service_path)?;
        let service_lease = fs::OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(service_path)?;
        fs2::FileExt::try_lock_exclusive(&service_lease)
            .context("此工作区已有训练器网页服务正在运行")?;
        {
            let _state = ctx.state_lease()?;
            let mut registry = Registry::load(root)?;
            assert_regular_ready(root)?;
            if !registry.reconcile(root, &self.catalog)?.is_empty() {
                registry.store(root)?;
            }
        }
        crate::data_import::assert_current_environment(root, &release.id)?;
        if Registry::load(root)?.current.is_none() {
            bail!("请先选择已安装版本");
        }
        self.lifecycle.check_cancel(run_id)?;
        verify_source(&layout, &release)?;
        if !target_leases {
            (self.logger)(
                "当前训练器使用旧运行协议；升级主程序后即可在服务运行时管理独立引擎".into(),
            );
        }
        self.lifecycle.check_cancel(run_id)?;
        check_environment(&layout, &release)?;
        self.lifecycle.check_cancel(run_id)?;
        runtime_view::prepare(&layout, &release)?;
        (self.logger)(format!(
            "启动 {}；用户资料 {}",
            release.id,
            layout.profile.display()
        ));
        self.lifecycle.check_cancel(run_id)?;
        let listener = TcpListener::bind(("127.0.0.1", 0))?;
        let port = listener.local_addr()?.port();
        drop(listener); // gui.py --port-conflict error fails safely if another process wins the race.
        let mut command = Command::new(env_python(&layout));
        crate::network_policy::current_or_root(root)?.apply_command(&mut command);
        command
            .current_dir(&layout.run)
            .arg("-B")
            .env("PYTHONDONTWRITEBYTECODE", "1")
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
                "NEXT_TRAINER_LAUNCHER_CONTEXT",
                engine_bridge::context(&layout, &release)?,
            )
            .env(
                "NEXT_TRAINER_NETWORK_CONFIG",
                crate::network_policy::settings_path(root)?,
            )
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
        command.stdout(Stdio::piped()).stderr(Stdio::piped());
        // Resolve fallible metadata before a live Job/lease must be transferred.
        let binding = Registry::load(root)?.gui_binding(&release.id).cloned();
        let (mut child, job) = managed_child::spawn(&mut command)?;
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
            let log = self
                .service_logger
                .as_ref()
                .map(|factory| factory(root, run_id))
                .unwrap_or_else(|| self.logger.clone());
            thread::spawn(move || {
                for line in BufReader::new(pipe).lines().map_while(Result::ok) {
                    log(format!("[训练器服务] {line}"));
                }
            });
        }
        (self.logger)(format!(
            "已创建受管进程 PID={}，等待 /api/version，端口 {port}",
            child.id()
        ));
        self.lifecycle.attach(
            run_id,
            Running {
                child,
                port,
                _lease: ctx.lease(),
                _service_lease: Some(service_lease),
                _job: job,
            },
            &release,
            binding.as_ref(),
        )?;
        let start = Instant::now();
        while start.elapsed() < Duration::from_secs(180) {
            self.lifecycle.check_cancel(run_id)?;
            self.lifecycle.check_alive(run_id)?;
            if let Ok(version) = health(port) {
                self.lifecycle.check_owned(run_id, port)?;
                if version != release.version {
                    bail!("健康接口版本不符：{version}");
                }
                let health_observed = stamp();
                // Keep process/lease ownership fixed across the health transaction.
                // stop requests remain responsive through the separate snapshot lock.
                let committed = self.lifecycle.commit_ready(run_id, &version, |lease| {
                    let ctx = model::WorkspaceMutation::from_running_lease(layout.clone(), lease);
                    let _state = ctx.state_lease()?;
                    crate::data_import::mark_healthy(&ctx, &release.id)
                })?;
                (self.logger)(format!(
                    "真实训练器就绪，版本 {version}，http://127.0.0.1:{port}；health={health_observed}ms commit={committed}ms"
                ));
                return self.start_report(root, &layout, &release);
            }
            thread::sleep(Duration::from_millis(200));
        }
        bail!("训练器健康检查超时，已停止本次受管进程，可修复后重试")
    }
    fn start_report(&self, root: &Path, layout: &Layout, release: &Release) -> Result<Report> {
        // This report describes checks already performed by this start. Inactive
        // versions keep the last explicit assessment; none are scanned here.
        let registry = Registry::load(root)?;
        let runtime = self.lifecycle.snapshot(root);
        let mut report = self
            .assessment
            .clone()
            .filter(|r| r.root == root.to_string_lossy());
        if report.is_none() {
            let recipe = crate::recipe::GuiRecipe::embedded()?;
            let versions = self
                .catalog
                .releases()
                .iter()
                .map(|r| -> Result<VersionView> {
                    let current = r.id == release.id;
                    Ok(VersionView {
                        legacy_recovery: legacy_install_recovery::candidate(root, r).ok().flatten(),
                        legacy_environment_repair: legacy_environment_repair::pending_transaction(
                            root, r,
                        )?,
                        support: release_support(r, &recipe),
                        id: r.id.clone(),
                        channel: r.channel.clone(),
                        version: r.version.clone(),
                        commit: r.commit.clone(),
                        download_bytes: r.archive.bytes,
                        source_bytes: r.archive.unpacked_bytes,
                        installed: registry.installed.iter().any(|i| i.release_id == r.id),
                        source_ok: current,
                        environment_ok: current,
                        current,
                        known_good: registry
                            .installed
                            .iter()
                            .any(|i| i.release_id == r.id && i.healthy_at.is_some()),
                        managed_recipe: r.environment_recipe == "gui-cp310-win-x64-v1",
                    })
                })
                .collect::<Result<Vec<_>>>()?;
            report = Some(Report {
                root: root.to_string_lossy().into(),
                uv: false,
                python: true,
                source: true,
                environment: true,
                frontend: true,
                running: false,
                healthy: false,
                version: Some(release.version.clone()),
                port: None,
                checks: vec![],
                logs: vec![],
                current_release: registry.current.clone(),
                previous_known_good: registry.previous_known_good.clone(),
                profile_path: layout.profile.to_string_lossy().into(),
                versions,
                interrupted: vec![],
            });
        }
        let mut report = report.unwrap();
        report.uv = digest(&uv(root)).ok().as_deref() == Some(release.uv.exe_sha256.as_str());
        report.python = true;
        report.source = true;
        report.environment = true;
        report.frontend = true;
        report.running = runtime.pid.is_some();
        report.healthy = runtime.phase == "ready";
        report.version = Some(release.version.clone());
        report.port = runtime.port;
        report.current_release = registry.current;
        report.previous_known_good = registry.previous_known_good;
        report.profile_path = layout.profile.to_string_lossy().into();
        for version in &mut report.versions {
            version.current = version.id == release.id;
            if version.current {
                version.installed = true;
                version.source_ok = true;
                version.environment_ok = true;
                version.known_good = true;
            }
        }
        report.checks = [
            "自管 Python",
            "当前版本源码",
            "主程序依赖与解释器",
            "训练器前端",
        ]
        .iter()
        .map(|name| Check {
            name: (*name).into(),
            ok: true,
            detail: "本次启动前完整性及运行检查通过".into(),
        })
        .collect();
        Ok(report)
    }
    pub fn stop(&mut self) {
        if let Err(error) = self.lifecycle.stop() {
            (self.logger)(format!("停止受管进程失败：{error:#}"));
        }
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

    #[test]
    fn version_support_distinguishes_trusted_history_from_current_maintenance() {
        let catalog = Catalog::embedded().unwrap();
        let recipe = crate::recipe::GuiRecipe::embedded().unwrap();
        let current = catalog
            .release(&format!("dev-{}", recipe.source_commit))
            .unwrap();
        let support = release_support(current, &recipe);
        assert!(
            support.source_supported && support.maintenance_supported && support.install_supported
        );

        let previous = catalog
            .release("dev-89a3b6ca63964b3bc4549b8bda67b38c4baa1a3d")
            .unwrap();
        let support = release_support(previous, &recipe);
        assert!(support.source_supported);
        assert!(!support.maintenance_supported && !support.install_supported);
        let encoded = serde_json::to_value(support).unwrap();
        assert_eq!(encoded["source_supported"], true);
        assert_eq!(encoded["maintenance_supported"], false);

        let unsupported = catalog
            .release("dev-0d095dc8cb185b4c9e4d6f4971eba26ea3a1b47e")
            .unwrap();
        let support = release_support(unsupported, &recipe);
        assert!(
            !support.source_supported
                && !support.maintenance_supported
                && !support.install_supported
        );

        let mut changed = previous.clone();
        changed.archive.sha256 = "0".repeat(64);
        assert!(!release_support(&changed, &recipe).source_supported);
    }
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

    #[test]
    fn unknown_registration_intent_blocks_normal_mutations_across_release() {
        let root = negative_test_root("registration-gate");
        let (log, _) = logger();
        let mut engine = Engine::new(root.clone(), log);
        let catalog = Catalog::embedded().unwrap();
        let release = &catalog.releases()[0];
        let intent = root
            .join("state/gui-registration")
            .join(format!("{}.json", release.id));
        fs::create_dir_all(intent.parent().unwrap()).unwrap();
        let foreign = b"{\"schema_version\":99,\"status\":\"committing\"}";
        fs::write(&intent, foreign).unwrap();
        assert!(assert_regular_ready(&root).is_err());
        let other = catalog
            .releases()
            .iter()
            .find(|item| item.id != release.id)
            .unwrap();
        assert!(engine.select_release(&root, &other.id).is_err());
        assert_eq!(fs::read(intent).unwrap(), foreign);
    }
    #[test]
    fn invalid_network_settings_do_not_prepare_or_replace_workspace() {
        let root = negative_test_root("network-settings");
        let (logger, _) = logger();
        let engine = Engine::new(root.clone(), logger);
        let invalid: crate::network_policy::Settings = serde_json::from_value(
            serde_json::json!({ "mode": "manual", "http_proxy": "socks5://user:fake-secret@localhost:1" }),
        ).unwrap();
        assert!(engine
            .save_network_settings(root.to_str().unwrap(), &invalid)
            .is_err());
        assert_eq!(fs::read_dir(&root).unwrap().count(), 0);
        let oversized: crate::network_policy::Settings = serde_json::from_value(
            serde_json::json!({ "mode": "direct", "no_proxy": "a".repeat(65_536) }),
        )
        .unwrap();
        assert!(engine
            .save_network_settings(root.to_str().unwrap(), &oversized)
            .is_err());
        assert_eq!(fs::read_dir(&root).unwrap().count(), 0);
        let direct = serde_json::from_value(serde_json::json!({ "mode": "direct" })).unwrap();
        engine
            .save_network_settings(root.to_str().unwrap(), &direct)
            .unwrap();
        let file = crate::network_policy::settings_path(&root).unwrap();
        let before = fs::read(&file).unwrap();
        assert!(engine
            .save_network_settings(root.to_str().unwrap(), &invalid)
            .is_err());
        assert_eq!(fs::read(&file).unwrap(), before);
        fs::remove_dir_all(root).unwrap();
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
    fn failed_prefetch_persists_terminal_state_despite_broken_legacy_accounting() {
        let root = negative_test_root("prefetch-terminal");
        let (log, _) = logger();
        let mut engine = Engine::new(root.clone(), log);
        let settings: crate::network_policy::Settings =
            serde_json::from_value(serde_json::json!({"mode":"direct"})).unwrap();
        engine
            .save_network_settings(root.to_str().unwrap(), &settings)
            .unwrap();
        let legacy = root.join("state/download-budget.json");
        fs::write(&legacy, b"broken legacy ledger").unwrap();
        let (url, server) = serve_once(
            "HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\n",
            b"tiny",
        );
        let release = &mut engine.catalog.releases[0];
        release.archive.url = url;
        release.archive.bytes = 4;
        release.archive.sha256 = "0".repeat(64);
        let release_id = release.id.clone();
        let manager = crate::operations::OperationManager::default();
        let operation = manager
            .start(
                "prefetch-terminal",
                crate::operations::OperationKind::Download,
            )
            .unwrap();
        let error = engine
            .prefetch_release(&root, &release_id, &operation)
            .unwrap_err();
        server.join().unwrap();
        assert!(error.to_string().contains("校验失败"));
        let layout = Layout::new(&root, &release_id).unwrap();
        let records = crate::operations::load_snapshots(&layout).unwrap();
        let saved = records
            .iter()
            .find(|item| item.id == "prefetch-terminal")
            .unwrap();
        assert_eq!(saved.status, crate::operations::OperationStatus::Failed);
        assert!(saved.error.as_ref().unwrap().message.contains("校验失败"));
        assert_eq!(fs::read(legacy).unwrap(), b"broken legacy ledger");
    }

    #[test]
    fn wrong_sha_download_keeps_partial_and_never_publishes_target() {
        let root = negative_test_root("wrong-sha");
        let catalog = Catalog::embedded().unwrap();
        let ctx = model::WorkspaceMutation::acquire(&root, &catalog.releases()[0].id).unwrap();
        let cache = root.join("cache");
        let target = cache.join("asset.zip");
        fs::write(&target, b"previous asset").unwrap();
        let (url, server) = serve_once(
            "HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\n",
            b"tiny",
        );
        let (log, _) = logger();
        let result = download(&ctx, &url, "asset.zip", &"0".repeat(64), 4, &log);
        server.join().unwrap();
        let error = result.unwrap_err().to_string();
        assert!(
            error.contains("校验失败"),
            "未到达 SHA256 拒绝路径：{error}"
        );
        assert!(!target.exists());
        // 原无效缓存被隔离，不能被失败下载覆盖或删除。
        assert!(fs::read_dir(&cache).unwrap().any(|entry| {
            let path = entry.unwrap().path();
            path.is_file() && fs::read(path).unwrap() == b"previous asset"
        }));
        let partials: Vec<_> = fs::read_dir(&cache)
            .unwrap()
            .map(|e| e.unwrap().path())
            .filter(|path| path.extension().is_some_and(|ext| ext == "part"))
            .collect();
        assert_eq!(partials.len(), 1);
        assert_eq!(fs::read(&partials[0]).unwrap(), b"tiny");
    }

    #[test]
    fn excessive_content_length_is_rejected_before_creating_partial() {
        let root = negative_test_root("content-length");
        let catalog = Catalog::embedded().unwrap();
        let ctx = model::WorkspaceMutation::acquire(&root, &catalog.releases()[0].id).unwrap();
        let cache = root.join("cache");
        let (url, server) = serve_once(
            "HTTP/1.1 200 OK\r\nContent-Length: 200000001\r\nConnection: close\r\n\r\n",
            b"",
        );
        let (log, _) = logger();
        let result = download(&ctx, &url, "oversized.zip", &"0".repeat(64), 4, &log);
        server.join().unwrap();
        let error = format!("{:#}", result.unwrap_err());
        assert!(
            error.contains("响应长度"),
            "未到达长度上限拒绝路径：{error}"
        );
        assert!(fs::read_dir(&cache).unwrap().next().is_none());
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
            error.contains("解压体积超过") || error.contains("ZIP 单文件大小或压缩比超过限额"),
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
