//! Windows：挂起创建 → 绑定 Job → 校验唯一初始线程 → 恢复执行。
//! 非 Windows 仅保留原 spawn/attach 行为，不提供相同的执行前归属保证。

#[cfg(not(windows))]
use super::hidden;
use super::Job;
use anyhow::{Context, Result};
use std::process::{Child, Command};

/// 查询在恢复初始线程前登记身份；任何失败都将仍持有的资源交给调用者回收。
pub(super) struct QuerySpawnFailure {
    pub error: anyhow::Error,
    pub child: Option<Child>,
    pub job: Option<Job>,
    pub never_resumed: bool,
}

pub(super) fn spawn_query(
    command: &mut Command,
    attached: impl FnOnce(&Child, &Job) -> Result<()>,
) -> std::result::Result<(Child, Job), QuerySpawnFailure> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        use windows_sys::Win32::System::Threading::{CREATE_NO_WINDOW, CREATE_SUSPENDED};
        command.creation_flags(CREATE_NO_WINDOW | CREATE_SUSPENDED);
        let child = command.spawn().map_err(|error| QuerySpawnFailure {
            error: anyhow::Error::new(error).context("创建挂起查询进程失败"),
            child: None,
            job: None,
            never_resumed: true,
        })?;
        let job = match Job::attach(&child) {
            Ok(job) => job,
            Err(error) => {
                return Err(QuerySpawnFailure {
                    error,
                    child: Some(child),
                    job: None,
                    never_resumed: true,
                })
            }
        };
        if let Err(error) = attached(&child, &job) {
            return Err(QuerySpawnFailure {
                error,
                child: Some(child),
                job: Some(job),
                never_resumed: true,
            });
        }
        if let Err(error) = resume_initial_thread(&child) {
            // ResumeThread异常可代表此前已被外界恢复，不声称从未运行。
            return Err(QuerySpawnFailure {
                error,
                child: Some(child),
                job: Some(job),
                never_resumed: false,
            });
        }
        Ok((child, job))
    }
    #[cfg(not(windows))]
    {
        let _ = (command, attached);
        Err(QuerySpawnFailure {
            error: anyhow::anyhow!("完整查询 Job 回收证明当前仅支持 Windows"),
            child: None,
            job: None,
            never_resumed: true,
        })
    }
}

/// 身份来自仍持有的 Child/Job；PID 不能单独证明同一代进程。
pub(super) fn worker_identity(
    child: &Child,
    job: &Job,
) -> Result<crate::query_tasks::WorkerIdentity> {
    #[cfg(windows)]
    {
        use std::{
            os::windows::io::AsRawHandle,
            sync::atomic::{AtomicU64, Ordering},
        };
        use windows_sys::Win32::{Foundation::FILETIME, System::Threading::GetProcessTimes};
        static NEXT_JOB: AtomicU64 = AtomicU64::new(0);
        let mut created: FILETIME = unsafe { std::mem::zeroed() };
        let mut exited: FILETIME = unsafe { std::mem::zeroed() };
        let mut kernel: FILETIME = unsafe { std::mem::zeroed() };
        let mut user: FILETIME = unsafe { std::mem::zeroed() };
        if unsafe {
            GetProcessTimes(
                child.as_raw_handle() as _,
                &mut created,
                &mut exited,
                &mut kernel,
                &mut user,
            )
        } == 0
        {
            return Err(std::io::Error::last_os_error()).context("读取受管查询进程代次失败");
        }
        let creation_time =
            (u64::from(created.dwHighDateTime) << 32) | u64::from(created.dwLowDateTime);
        if creation_time == 0 || !job.contains(child.id()) {
            anyhow::bail!("受管查询进程代次或 Job 归属无效");
        }
        let sequence = NEXT_JOB.fetch_add(1, Ordering::Relaxed);
        Ok(crate::query_tasks::WorkerIdentity {
            pid: child.id(),
            creation_time,
            job_id: format!("query-job-{}-{creation_time}-{sequence}", child.id()),
        })
    }
    #[cfg(not(windows))]
    {
        let _ = (child, job);
        anyhow::bail!("完整查询 Job 回收证明当前仅支持 Windows");
    }
}

pub(super) fn spawn(command: &mut Command) -> Result<(Child, Job)> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        use windows_sys::Win32::System::Threading::{CREATE_NO_WINDOW, CREATE_SUSPENDED};

        // hidden() 会覆盖 creation_flags，必须一次设置两项，不能在此后再调用它。
        command.creation_flags(CREATE_NO_WINDOW | CREATE_SUSPENDED);
    }
    #[cfg(not(windows))]
    hidden(command);

    let mut child = command.spawn().context("创建受管子进程失败")?;
    let job = match Job::attach(&child) {
        Ok(job) => job,
        Err(error) => {
            let _ = child.kill();
            if let Err(waited) =
                super::wait_controlled_child(&mut child, std::time::Duration::from_secs(1))
            {
                return Err(super::ControlledProcessReapFailed::new(
                    format!("子进程绑定Job失败：{error:#}；未附加Child回收失败：{waited:#}"),
                    false,
                )
                .into());
            }
            return Err(error.context("子进程绑定 Job 失败，已拒绝恢复执行"));
        }
    };

    #[cfg(windows)]
    if let Err(error) = resume_initial_thread(&child) {
        let reaped = job.terminate_and_wait();
        let _ = child.kill();
        let waited = super::wait_controlled_child(&mut child, std::time::Duration::from_secs(1));
        if reaped.is_err() || waited.is_err() {
            return Err(super::ControlledProcessReapFailed::new(
                format!(
                    "受管线程恢复失败：{error:#}；Job排空={:?}；Child回收={:?}",
                    reaped.as_ref().map_err(|error| format!("{error:#}")),
                    waited.as_ref().map_err(|error| format!("{error:#}")),
                ),
                false,
            )
            .into());
        }
        return Err(error.context("受管初始线程校验/恢复失败，已回收本次 Job"));
    }

    Ok((child, job))
}

/// 命名 Job 由调用方预创建并持久化 launching 身份。attached 必须在恢复初始
/// 线程前持久化确认；失败时不会运行该命令。launching 的崩溃窗不能据 Job
/// 不存在而推断安全，调用方须保留 needs_attention。
pub(super) fn spawn_in_job(
    command: &mut Command,
    job: &Job,
    attached: impl FnOnce(u32) -> Result<()>,
) -> Result<Child> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        use windows_sys::Win32::System::Threading::{CREATE_NO_WINDOW, CREATE_SUSPENDED};
        command.creation_flags(CREATE_NO_WINDOW | CREATE_SUSPENDED);
        let mut child = command.spawn().context("创建环境修复挂起子进程失败")?;
        let result = job
            .assign(&child)
            .and_then(|()| attached(child.id()))
            .and_then(|()| resume_initial_thread(&child));
        if let Err(error) = result {
            let reaped = job.terminate_and_wait();
            let _ = child.kill();
            let waited =
                super::wait_controlled_child(&mut child, std::time::Duration::from_secs(1));
            if reaped.is_err() || waited.is_err() {
                return Err(super::ControlledProcessReapFailed::new(
                    format!(
                        "挂起命令启动失败：{error:#}；Job排空={:?}；Child回收={:?}",
                        reaped.as_ref().map_err(|error| format!("{error:#}")),
                        waited.as_ref().map_err(|error| format!("{error:#}")),
                    ),
                    false,
                )
                .into());
            }
            return Err(error);
        }
        Ok(child)
    }
    #[cfg(not(windows))]
    {
        let _ = (command, job, attached);
        anyhow::bail!("命名 Job 环境修复当前仅支持 Windows");
    }
}

#[cfg(windows)]
struct OwnedHandle(windows_sys::Win32::Foundation::HANDLE);

#[cfg(windows)]
impl Drop for OwnedHandle {
    fn drop(&mut self) {
        // 只持有已验证为非空且非 INVALID_HANDLE_VALUE 的本次 Win32 handle。
        unsafe {
            windows_sys::Win32::Foundation::CloseHandle(self.0);
        }
    }
}

#[cfg(windows)]
fn resume_initial_thread(child: &Child) -> Result<()> {
    use anyhow::bail;
    use std::{io, mem};
    use windows_sys::Win32::{
        Foundation::{GetLastError, ERROR_NO_MORE_FILES, INVALID_HANDLE_VALUE},
        System::{
            Diagnostics::ToolHelp::{
                CreateToolhelp32Snapshot, Thread32First, Thread32Next, TH32CS_SNAPTHREAD,
                THREADENTRY32,
            },
            Threading::{
                GetProcessIdOfThread, GetThreadId, OpenThread, ResumeThread,
                THREAD_QUERY_LIMITED_INFORMATION, THREAD_SUSPEND_RESUME,
            },
        },
    };

    let pid = child.id();
    if pid == 0 {
        bail!("挂起子进程 PID 无效");
    }

    // CREATE_SUSPENDED 子进程尚未执行用户代码，应且只应存在一个初始线程。
    // 必须枚举完整快照以确认唯一性，不能取到第一个就恢复。
    let raw_snapshot = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0) };
    if raw_snapshot == INVALID_HANDLE_VALUE || raw_snapshot.is_null() {
        return Err(io::Error::last_os_error()).context("获取挂起子进程线程快照失败");
    }
    let snapshot = OwnedHandle(raw_snapshot);
    let entry_size = mem::size_of::<THREADENTRY32>() as u32;
    let mut entry: THREADENTRY32 = unsafe { mem::zeroed() };
    entry.dwSize = entry_size;
    if unsafe { Thread32First(snapshot.0, &mut entry) } == 0 {
        return Err(io::Error::last_os_error()).context("读取线程快照首项失败");
    }

    let mut thread_id = None;
    loop {
        if entry.dwSize < entry_size {
            bail!("线程快照结构不完整，拒绝恢复执行");
        }
        if entry.th32OwnerProcessID == pid
            && (entry.th32ThreadID == 0 || thread_id.replace(entry.th32ThreadID).is_some())
        {
            bail!("挂起子进程未匹配唯一初始线程，拒绝恢复执行");
        }
        entry.dwSize = entry_size;
        if unsafe { Thread32Next(snapshot.0, &mut entry) } == 0 {
            let error = unsafe { GetLastError() };
            if error != ERROR_NO_MORE_FILES {
                return Err(io::Error::from_raw_os_error(error as i32)).context("枚举线程快照失败");
            }
            break;
        }
    }
    let thread_id = thread_id.context("挂起子进程没有可验证的初始线程")?;

    // 固定线程 handle 后再次核对 PID/TID，拒绝快照到 OpenThread 之间的身份变化。
    let raw_thread = unsafe {
        OpenThread(
            THREAD_SUSPEND_RESUME | THREAD_QUERY_LIMITED_INFORMATION,
            0,
            thread_id,
        )
    };
    if raw_thread.is_null() || raw_thread == INVALID_HANDLE_VALUE {
        return Err(io::Error::last_os_error()).context("打开挂起子进程初始线程失败");
    }
    let thread = OwnedHandle(raw_thread);
    if unsafe { GetProcessIdOfThread(thread.0) } != pid
        || unsafe { GetThreadId(thread.0) } != thread_id
    {
        bail!("初始线程进程/线程身份不符，拒绝恢复执行");
    }

    let previous_suspend_count = unsafe { ResumeThread(thread.0) };
    if previous_suspend_count == u32::MAX {
        return Err(io::Error::last_os_error()).context("恢复受管初始线程失败");
    }
    if previous_suspend_count != 1 {
        bail!("初始线程挂起计数异常（{previous_suspend_count}），拒绝继续运行");
    }
    Ok(())
}
