"""Keep existing shortcuts working while running the app as EAB.exe."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys


def protect_update_process_tree():
    """Let an older updater terminate both this launcher and its child on rollback."""
    class BasicLimits(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64),
                    ('PerJobUserTimeLimit', ctypes.c_int64), ('LimitFlags', wintypes.DWORD),
                    ('MinimumWorkingSetSize', ctypes.c_size_t), ('MaximumWorkingSetSize', ctypes.c_size_t),
                    ('ActiveProcessLimit', wintypes.DWORD), ('Affinity', ctypes.c_size_t),
                    ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in
                    ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
                     'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', BasicLimits), ('IoInfo', IoCounters),
                    ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetInformationJobObject.restype = wintypes.BOOL
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if (not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits))
            or not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess())):
        error = ctypes.get_last_error()
        kernel.CloseHandle(job)
        raise ctypes.WinError(error)
    # Intentionally keep this non-inheritable handle until process exit. Children
    # inherit membership, so terminating the launcher also stops the new app.
    return job


def launch(directory, arguments):
    target = Path(directory).resolve() / 'EAB.exe'
    if not target.is_file():
        raise FileNotFoundError('같은 폴더의 EAB.exe를 찾을 수 없습니다. EAB ZIP을 다시 압축 해제해 주세요.')
    updating = '--update-ready' in arguments
    if updating and os.name == 'nt':
        protect_update_process_tree()
    child = subprocess.Popen([str(target), *arguments], cwd=str(target.parent),
                             env={**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'},
                             close_fds=True)
    # Bridge updaters monitor this process during startup. Keep it alive for
    # their health check and rollback; normal shortcut launches exit immediately.
    return child.wait() if updating else 0


def main():
    directory = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
    try:
        return launch(directory, sys.argv[1:])
    except Exception as exc:
        if os.name == 'nt':
            ctypes.windll.user32.MessageBoxW(None, str(exc), 'EAB 실행 오류', 0x10)
        return 1


if __name__ == '__main__':
    sys.exit(main())
