"""Bound a synchronous command and its descendants, including inherited pipes."""
import math
import os
import signal
import subprocess
import time
from typing import Any


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    return True


def run_bounded(command, *, timeout: float, **kwargs: Any) -> subprocess.CompletedProcess:
    """Collect output and wait for the process tree, killing it on timeout."""
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("A finite positive timeout is required")
    deadline = time.monotonic() + timeout
    job = None
    if os.name == "nt":
        from ._windows_job import WindowsJob
        job = WindowsJob()
    try:
        child = job.start(command, kwargs) if job else subprocess.Popen(command, start_new_session=True, **kwargs)
        try:
            stdout, stderr = child.communicate(timeout=max(0, deadline - time.monotonic()))
            while job.active() if job else _group_alive(child.pid):
                left = deadline - time.monotonic()
                if left <= 0:
                    raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
                time.sleep(min(left, 0.01))
            return subprocess.CompletedProcess(command, child.returncode, stdout, stderr)
        except BaseException:
            if job:
                job.terminate()
            else:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            child.communicate(timeout=10)
            raise
    finally:
        if job:
            job.close()
