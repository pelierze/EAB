"""Remove a successful update's own staging folder after its worker exits."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import sys
import time


def validate_workspace(workspace, target):
    raw = Path(workspace).absolute()
    workspace, target = raw.resolve(), Path(target).resolve()
    if (raw != workspace or not workspace.name.startswith('.e7-update-')
            or workspace.parent != target.parent or workspace == target
            or target.is_relative_to(workspace)):
        raise ValueError('Invalid cleanup workspace')
    if workspace.is_symlink() or workspace.is_junction():
        raise ValueError('Cleanup workspace is a link')
    result = json.loads((workspace / 'result.json').read_text(encoding='utf-8'))
    if result.get('ok') is not True:
        raise ValueError('Only successful updates can be cleaned up')
    plan = workspace / 'plan.json'
    if plan.exists() and Path(json.loads(plan.read_text(encoding='utf-8'))['target']).resolve() != target:
        raise ValueError('Cleanup target does not match update plan')
    return workspace


def wait_worker(pid, timeout=180):
    if os.name != 'nt' or pid <= 0 or pid == os.getpid():
        raise ValueError('Invalid cleanup worker')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.WaitForSingleObject.restype = ctypes.c_ulong
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x00100000, False, pid)  # Synchronize only; no memory access.
    if not handle:
        error = ctypes.get_last_error()
        if error == 87:  # The worker already exited.
            return
        raise ctypes.WinError(error)
    try:
        if kernel.WaitForSingleObject(handle, int(timeout*1000)) != 0:
            raise TimeoutError('Update worker has not exited')
    finally:
        kernel.CloseHandle(handle)


def cleanup(workspace, target, worker_pid):
    workspace = validate_workspace(workspace, target)
    wait_worker(int(worker_pid))
    for attempt in range(30):
        if not workspace.exists():
            return 0
        # Revalidate the absolute target immediately before every recursive delete.
        validate_workspace(workspace, target)
        if any(path.is_symlink() or path.is_junction() for path in workspace.rglob('*')):
            raise ValueError('Cleanup workspace contains links')
        try:
            shutil.rmtree(workspace)
            return 0
        except OSError:
            if attempt == 29:
                raise
            time.sleep(1)
    return 1


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('Expected workspace, target and worker PID')
    raise SystemExit(cleanup(*sys.argv[1:]))
