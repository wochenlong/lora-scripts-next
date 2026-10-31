"""受管训练子树监督器；只依赖标准库，保持原命令的日志和退出码。"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time


def windows_run(command):
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [("process_user_time", ctypes.c_longlong), ("job_user_time", ctypes.c_longlong),
                    ("flags", wintypes.DWORD), ("minimum_working_set", ctypes.c_size_t),
                    ("maximum_working_set", ctypes.c_size_t), ("active_process_limit", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ("read_operations", "write_operations", "other_operations", "read_bytes", "write_bytes", "other_bytes")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("basic", BasicLimits), ("io", IoCounters),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]

    class Accounting(ctypes.Structure):
        _fields_ = [(name, ctypes.c_longlong) for name in
                    ("user_time", "kernel_time", "period_user_time", "period_kernel_time")] + [
                    (name, wintypes.DWORD) for name in ("page_faults", "total_processes", "active_processes", "terminated_processes")]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                               wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryInformationJobObject.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    def require(result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())

    job = kernel.CreateJobObjectW(None, None)
    require(job)
    safe_to_close = True
    limits = ExtendedLimits()
    try:
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE；不允许 breakaway。
        require(kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        # 在启动任何训练代码前先把监督器加入 Job；后代自动继承成员身份。
        require(kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()))
        process = subprocess.Popen(command)
        safe_to_close = False
        result = process.wait()
        while True:
            accounting = Accounting()
            require(kernel.QueryInformationJobObject(job, 1, ctypes.byref(accounting), ctypes.sizeof(accounting), None))
            if accounting.active_processes <= 1:  # 只余监督器自身；包含重定向日志的孤儿 worker。
                safe_to_close = True
                return result
            time.sleep(0.05)
    finally:
        if safe_to_close:
            # 正常结束清除此标志，关闭自身 Job 句柄才不会改写原训练退出码。
            limits.basic.flags = 0
            require(kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
        # 异常/被杀时句柄关闭自动终止整个训练子树，不留下失去 lease 的 worker。
        kernel.CloseHandle(job)


def linux_run(command):
    # Linux 采用 subreaper：训练父进程退出后，孤儿后代归监督器收割。
    # Windows 分发验收使用上面的 Job；其他 Unix 平台在启动训练前明确拒绝。
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "cannot establish training subreaper")
    result = subprocess.Popen(command).wait()
    while True:
        try:
            os.wait()
        except ChildProcessError:
            return result


def main():
    command = sys.argv[1:]
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print("受管训练监督器缺少命令", file=sys.stderr, flush=True)
        return 125
    try:
        if os.name == "nt":
            return windows_run(command)
        if sys.platform.startswith("linux"):
            return linux_run(command)
        raise RuntimeError("当前受管训练子树监督仅支持 Windows 和 Linux")
    except Exception as error:
        print(f"受管训练监督失败：{error}", file=sys.stderr, flush=True)
        return 125


if __name__ == "__main__":
    raise SystemExit(main())
