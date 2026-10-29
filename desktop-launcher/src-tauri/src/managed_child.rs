//! Windows：挂起创建 → 绑定 Job → 校验唯一初始线程 → 恢复执行。
//! 非 Windows 仅保留原 spawn/attach 行为，不提供相同的执行前归属保证。

#[cfg(not(windows))]
use super::hidden;
use super::Job;
use anyhow::{Context, Result};
use std::process::{Child, Command};

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
            let _ = child.wait();
            return Err(error.context("子进程绑定 Job 失败，已拒绝恢复执行"));
        }
    };

    #[cfg(windows)]
    if let Err(error) = resume_initial_thread(&child) {
        let _ = child.kill();
        // 即使异常 suspend count 意味着线程已被外部恢复，Job 关闭仍回收其后代。
        drop(job);
        let _ = child.wait();
        return Err(error.context("受管初始线程校验/恢复失败，已回收本次 Job"));
    }

    Ok((child, job))
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
