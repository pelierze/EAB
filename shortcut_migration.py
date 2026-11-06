"""Replace only the invoked legacy shortcut, using Windows' startup metadata."""
import hashlib
import ctypes
from ctypes import wintypes
import uuid
import os
from pathlib import Path
import subprocess

from windows_shortcuts import read_shortcut, write_shortcut, desktop_folder


class StartupInfo(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('lpReserved', wintypes.LPWSTR),
                ('lpDesktop', wintypes.LPWSTR), ('lpTitle', wintypes.LPWSTR),
                *[(name, wintypes.DWORD) for name in
                  ('dwX', 'dwY', 'dwXSize', 'dwYSize', 'dwXCountChars',
                   'dwYCountChars', 'dwFillAttribute', 'dwFlags')],
                ('wShowWindow', wintypes.WORD), ('cbReserved2', wintypes.WORD),
                ('lpReserved2', ctypes.c_void_p), ('hStdInput', wintypes.HANDLE),
                ('hStdOutput', wintypes.HANDLE), ('hStdError', wintypes.HANDLE)]


def invoked_shortcut():
    if os.name != 'nt':
        return None
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetStartupInfoW.argtypes = [ctypes.POINTER(StartupInfo)]
    kernel.GetStartupInfoW.restype = None
    info = StartupInfo()
    info.cb = ctypes.sizeof(info)
    kernel.GetStartupInfoW(ctypes.byref(info))
    if info.dwFlags & 0x800 and info.lpTitle:  # STARTF_TITLEISLINKNAME
        candidate = Path(info.lpTitle)
        if candidate.is_absolute() and candidate.suffix.lower() == '.lnk':
            return candidate
    return None


def _same_path(left, right):
    if not left or not right:
        return False
    return os.path.normcase(os.path.abspath(os.path.expandvars(str(left)))) == os.path.normcase(os.path.abspath(str(right)))


def migrate_shortcut(target, arguments, invoked=None, desktop=None):
    """Migrate only the verified invoked link, using Windows Shell Link APIs."""
    target = Path(target).resolve()
    if not target.is_file():
        raise RuntimeError('EAB.exe is missing')
    legacy = target.parent / 'SecretShopBot-E7.exe'
    destination = Path(desktop if desktop is not None else desktop_folder())
    arguments = subprocess.list2cmdline(arguments)
    old_path = old_hash = None
    if invoked is not None:
        candidate = Path(invoked)
        if candidate.is_absolute() and candidate.suffix.lower() == '.lnk' and candidate.is_file():
            old = read_shortcut(candidate)
            if _same_path(old['target'], legacy):
                old_path = candidate.resolve()
                old_hash = hashlib.sha256(old_path.read_bytes()).digest()
                arguments = old['arguments']
                destination = old_path.parent
    if not destination.is_dir():
        raise RuntimeError('Shortcut destination is unavailable')
    new_path = None
    for index in range(1, 101):
        candidate = destination / ('EAB.lnk' if index == 1 else f'EAB ({index}).lnk')
        if candidate.exists():
            existing = read_shortcut(candidate)
            if (_same_path(existing['target'], target) and existing['arguments'] == arguments
                    and _same_path(existing['directory'], target.parent)):
                new_path = candidate
                break
            continue
        temporary = destination / ('.eab-' + uuid.uuid4().hex + '.lnk')
        try:
            write_shortcut(temporary, target, arguments, target.parent)
            temporary.rename(candidate)
            new_path = candidate
        finally:
            temporary.unlink(missing_ok=True)
        break
    if new_path is None:
        raise RuntimeError('No available EAB shortcut name')
    verified = read_shortcut(new_path)
    if not _same_path(verified['target'], target) or verified['arguments'] != arguments:
        raise RuntimeError('EAB shortcut verification failed')
    removed = False
    if old_path and old_path != new_path and old_path.is_file():
        current = read_shortcut(old_path)
        if (_same_path(current['target'], legacy)
                and hashlib.sha256(old_path.read_bytes()).digest() == old_hash):
            old_path.unlink()
            removed = True
    return {'shortcut': str(new_path), 'removed_old': removed}
