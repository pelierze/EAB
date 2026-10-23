"""Replace only the invoked legacy shortcut, using Windows' startup metadata."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess


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


SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$shell = New-Object -ComObject WScript.Shell
$target = [IO.Path]::GetFullPath($config.target)
if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw 'EAB.exe is missing' }
$legacy = Join-Path ([IO.Path]::GetDirectoryName($target)) 'SecretShopBot-E7.exe'
function Same-Path($a, $b) {
    if (-not $a -or -not $b) { return $false }
    try {
        return [String]::Equals([IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($a)),
                                [IO.Path]::GetFullPath($b), [StringComparison]::OrdinalIgnoreCase)
    } catch { return $false }
}
function Link-Hash($path) {
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return [Convert]::ToBase64String($hash.ComputeHash([IO.File]::ReadAllBytes($path))) }
    finally { $hash.Dispose() }
}
$oldPath = $null
$oldHash = $null
$arguments = $config.arguments
$destination = $config.desktop
if (-not $destination) { $destination = $shell.SpecialFolders.Item('Desktop') }
if ($config.invoked -and [IO.Path]::IsPathRooted($config.invoked) -and
    [IO.Path]::GetExtension($config.invoked) -ieq '.lnk' -and
    (Test-Path -LiteralPath $config.invoked -PathType Leaf)) {
    $old = $shell.CreateShortcut($config.invoked)
    if (Same-Path $old.TargetPath $legacy) {
        $oldPath = [IO.Path]::GetFullPath($config.invoked)
        $oldHash = Link-Hash $oldPath
        $arguments = $old.Arguments
        $destination = [IO.Path]::GetDirectoryName($oldPath)
    }
}
if (-not $destination -or -not (Test-Path -LiteralPath $destination -PathType Container)) {
    throw 'Shortcut destination is unavailable'
}
$newPath = $null
for ($index = 1; $index -le 100; $index++) {
    $name = if ($index -eq 1) { 'EAB.lnk' } else { "EAB ($index).lnk" }
    $candidate = Join-Path $destination $name
    if (Test-Path -LiteralPath $candidate) {
        $existing = $shell.CreateShortcut($candidate)
        if ((Same-Path $existing.TargetPath $target) -and $existing.Arguments -ceq $arguments -and
            (Same-Path $existing.WorkingDirectory ([IO.Path]::GetDirectoryName($target)))) {
            $newPath = $candidate
            break
        }
        continue
    }
    $temporary = Join-Path $destination ('.eab-' + [Guid]::NewGuid().ToString('N') + '.lnk')
    try {
        $shortcut = $shell.CreateShortcut($temporary)
        $shortcut.TargetPath = $target
        $shortcut.Arguments = $arguments
        $shortcut.WorkingDirectory = [IO.Path]::GetDirectoryName($target)
        $shortcut.IconLocation = $target + ',0'
        $shortcut.Description = 'Epic7 Assist Bot'
        $shortcut.Save()
        [IO.File]::Move($temporary, $candidate)
        $newPath = $candidate
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
    }
    break
}
if (-not $newPath) { throw 'No available EAB shortcut name' }
$verified = $shell.CreateShortcut($newPath)
if (-not (Same-Path $verified.TargetPath $target) -or $verified.Arguments -cne $arguments) {
    throw 'EAB shortcut verification failed'
}
$removed = $false
if ($oldPath -and -not (Same-Path $oldPath $newPath) -and
    (Test-Path -LiteralPath $oldPath -PathType Leaf)) {
    $current = $shell.CreateShortcut($oldPath)
    if ((Same-Path $current.TargetPath $legacy) -and
        (Link-Hash $oldPath) -ceq $oldHash) {
        Remove-Item -LiteralPath $oldPath -Force
        $removed = $true
    }
}
@{ shortcut = $newPath; removed_old = $removed } | ConvertTo-Json -Compress
'''


def migrate_shortcut(target, arguments, invoked=None, desktop=None):
    """Explicit desktop override is for isolated tests; launchers use Windows' desktop."""
    config = {'target': str(Path(target).resolve()),
              'arguments': subprocess.list2cmdline(arguments),
              'invoked': str(invoked) if invoked is not None else None,
              'desktop': str(desktop) if desktop is not None else None}
    data = base64.b64encode(json.dumps(config, ensure_ascii=False).encode('utf-8')).decode('ascii')
    script = "$config = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + data + "')) | ConvertFrom-Json\n" + SCRIPT
    encoded = base64.b64encode(script.encode('utf-16le')).decode('ascii')
    powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
                             '-EncodedCommand', encoded], stdin=subprocess.DEVNULL, capture_output=True,
                            encoding='utf-8', errors='replace', timeout=20,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError('바로가기 전환 실패: ' + result.stderr.strip())
    return json.loads(result.stdout)
