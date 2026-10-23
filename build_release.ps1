param(
    [string]$Version = "v1.6.0",
    [string]$PythonExecutable = "python",
    [string]$ReleaseDirectory = "release",
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppName = "EAB"
$DisplayName = "Epic7 Assist Bot"
$ReleaseRoot = [System.IO.Path]::GetFullPath((Join-Path $ProjectRoot $ReleaseDirectory))
$DistRoot = Join-Path $ProjectRoot "dist"
$BuildRoot = Join-Path $ProjectRoot "build"
$NormalizedVersion = if ($Version.StartsWith("v")) { $Version } else { "v$Version" }
$NumericVersion = if ($NormalizedVersion.StartsWith("v")) { $NormalizedVersion.Substring(1) } else { $NormalizedVersion }
$CoreVersion = ($NumericVersion -split '-', 2)[0]
$CoreParts = @($CoreVersion.Split('.') | ForEach-Object { [int]$_ })
while ($CoreParts.Count -lt 3) { $CoreParts += 0 }
$PreReleaseBuild = 0
if ($NumericVersion -match '-(?:alpha|beta|rc)[.-]?(\d+)$') {
    $PreReleaseBuild = [int]$Matches[1]
}
$FileVersionTuple = "$($CoreParts[0]), $($CoreParts[1]), $($CoreParts[2]), $PreReleaseBuild"
if ($NormalizedVersion -notmatch '^v\d+\.\d+\.\d+(-(alpha|beta|rc)[.-]?\d+)?$') {
    throw "Invalid release version: $Version"
}
foreach ($PackagePrefix in @("EAB")) {
    foreach ($Suffix in @(".zip", ".zip.sha256.txt")) {
        $ExistingArtifact = Join-Path $ReleaseRoot "$PackagePrefix-$NormalizedVersion$Suffix"
        if (Test-Path -LiteralPath $ExistingArtifact) {
            throw "Release artifact already exists; choose another output folder: $ExistingArtifact"
        }
    }
}

Set-Location $ProjectRoot

Write-Host "== $DisplayName (EAB) release build =="
Write-Host "Version: $NormalizedVersion"
Write-Host ""

if (-not (Test-Path "main.py")) {
    throw "main.py was not found. Run this script from the project root."
}

Write-Host "Checking Python..."
& $PythonExecutable --version

if (-not $SkipDependencyInstall) {
    Write-Host "Installing Python dependencies..."
    & $PythonExecutable -m pip install -r requirements.txt pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
}

Write-Host "Checking executable icon..."
$IconPath = Join-Path $ProjectRoot "assets\icons\app_icon_multi_size.ico"
if (-not (Test-Path $IconPath)) {
    throw "Executable icon was not found: $IconPath"
}

Write-Host "Generating Windows version metadata..."
@"
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=($FileVersionTuple),
    prodvers=($FileVersionTuple),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [
          StringStruct(u'CompanyName', u'pelierze'),
          StringStruct(u'FileDescription', u'$DisplayName (EAB)'),
          StringStruct(u'FileVersion', u'$NumericVersion'),
          StringStruct(u'InternalName', u'EAB'),
          StringStruct(u'OriginalFilename', u'EAB.exe'),
          StringStruct(u'ProductName', u'$DisplayName'),
          StringStruct(u'ProductVersion', u'$NumericVersion'),
        ]
      )
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"@ | Set-Content -Path (Join-Path $ProjectRoot "file_version_info.txt") -Encoding ASCII

New-Item -ItemType Directory -Path $ReleaseRoot -Force | Out-Null

Write-Host "Building Windows app with PyInstaller..."
& $PythonExecutable -m PyInstaller `
    --noconfirm `
    --distpath $DistRoot `
    --workpath $BuildRoot `
    EAB.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$BuiltDir = Join-Path $DistRoot $AppName
if (-not (Test-Path $BuiltDir)) {
    throw "Build failed: $BuiltDir was not created."
}
if (-not (Test-Path (Join-Path $BuiltDir "EAB-Updater.exe"))) {
    throw "Automatic updater executable is missing from the build."
}

Write-Host "Validating and creating EAB release package..."
& $PythonExecutable -m build_support.release_packages --source $BuiltDir --output $ReleaseRoot --version $NormalizedVersion
if ($LASTEXITCODE -ne 0) {
    throw "Release package generation failed."
}

Write-Host ""
Write-Host "Upload the EAB zip and its .sha256.txt file to GitHub Releases:"
Write-Host "  https://github.com/pelierze/EAB/releases/new"
