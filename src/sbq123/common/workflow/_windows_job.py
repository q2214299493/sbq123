"""Own a Windows process tree before its first instruction can launch a descendant."""
import ctypes as ct
from ctypes import wintypes as wt
import subprocess

kernel = ct.WinDLL("kernel32", use_last_error=True)


def _api(name, result, *args):
    fn = getattr(kernel, name)
    fn.restype, fn.argtypes = result, args
    return fn


def _checked(value):
    if not value:
        raise ct.WinError(ct.get_last_error())
    return value


class _Limits(ct.Structure):
    _fields_ = [("process_time", ct.c_int64), ("job_time", ct.c_int64), ("flags", wt.DWORD),
                ("min_ws", ct.c_size_t), ("max_ws", ct.c_size_t), ("process_limit", wt.DWORD),
                ("affinity", ct.c_size_t), ("priority", wt.DWORD), ("scheduling", wt.DWORD)]


class _ExtendedLimits(ct.Structure):
    _fields_ = [("basic", _Limits), ("io_counters", ct.c_uint64 * 6),
                ("memory_limits_and_peaks", ct.c_size_t * 4)]


class _Accounting(ct.Structure):
    _fields_ = [("cpu_times", ct.c_int64 * 4), ("faults", wt.DWORD), ("total", wt.DWORD),
                ("active", wt.DWORD), ("terminated", wt.DWORD)]


class _Thread(ct.Structure):
    _fields_ = [("size", wt.DWORD), ("usage", wt.DWORD), ("tid", wt.DWORD),
                ("pid", wt.DWORD), ("priority", wt.LONG), ("delta", wt.LONG), ("flags", wt.DWORD)]


_create = _api("CreateJobObjectW", wt.HANDLE, wt.LPVOID, wt.LPCWSTR)
_close = _api("CloseHandle", wt.BOOL, wt.HANDLE)
_set = _api("SetInformationJobObject", wt.BOOL, wt.HANDLE, ct.c_int, wt.LPVOID, wt.DWORD)
_query = _api("QueryInformationJobObject", wt.BOOL, wt.HANDLE, ct.c_int, wt.LPVOID, wt.DWORD, wt.LPVOID)
_assign = _api("AssignProcessToJobObject", wt.BOOL, wt.HANDLE, wt.HANDLE)
_terminate = _api("TerminateJobObject", wt.BOOL, wt.HANDLE, wt.UINT)
_snapshot = _api("CreateToolhelp32Snapshot", wt.HANDLE, wt.DWORD, wt.DWORD)
_first = _api("Thread32First", wt.BOOL, wt.HANDLE, ct.POINTER(_Thread))
_next = _api("Thread32Next", wt.BOOL, wt.HANDLE, ct.POINTER(_Thread))
_open_thread = _api("OpenThread", wt.HANDLE, wt.DWORD, wt.BOOL, wt.DWORD)
_resume = _api("ResumeThread", wt.DWORD, wt.HANDLE)


def _resume_primary(pid):
    # Popen closes the original primary thread handle. CREATE_SUSPENDED leaves
    # exactly one thread in this process until we explicitly resume it.
    snapshot = _snapshot(0x4, 0)  # TH32CS_SNAPTHREAD
    if snapshot == wt.HANDLE(-1).value:
        raise ct.WinError(ct.get_last_error())
    try:
        thread = _Thread(size=ct.sizeof(_Thread))
        found = _first(snapshot, ct.byref(thread))
        while found:
            if thread.pid == pid:
                handle = _checked(_open_thread(0x2, False, thread.tid))  # THREAD_SUSPEND_RESUME
                try:
                    if _resume(handle) == 0xffffffff:
                        raise ct.WinError(ct.get_last_error())
                finally:
                    _close(handle)
                return
            thread.size = ct.sizeof(thread)
            found = _next(snapshot, ct.byref(thread))
        raise OSError("Suspended primary thread was not found")
    finally:
        _close(snapshot)


class WindowsJob:
    """Kernel-owned containment with kill-on-last-handle-close semantics."""

    def __init__(self):
        self.handle = _checked(_create(None, None))
        limits = _ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        try:
            _checked(_set(self.handle, 9, ct.byref(limits), ct.sizeof(limits)))
        except OSError:
            self.close()
            raise

    def start(self, command, kwargs):
        flags = kwargs.pop("creationflags", 0)
        child = subprocess.Popen(command, creationflags=flags | 0x4, **kwargs)
        try:
            _checked(_assign(self.handle, int(child._handle)))
            _resume_primary(child.pid)
        except BaseException:
            child.kill()
            child.communicate()
            raise
        return child

    def active(self):
        accounting = _Accounting()
        _checked(_query(self.handle, 1, ct.byref(accounting), ct.sizeof(accounting), None))
        return accounting.active > 0

    def terminate(self):
        _checked(_terminate(self.handle, 1))

    def close(self):
        _close(self.handle)
