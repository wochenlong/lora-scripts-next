#Requires -Version 5.1
<#
.SYNOPSIS
  Build Musubi / Krea2-only portable (NO full Kohya torch bake).

.DESCRIPTION
  1) lite skeleton via build_portable.ps1
  2) minimal WebUI deps in python_embeded (no training torch index)
  3) install Musubi engine (cu128)
  4) 2026 root UX + 7z
  See docs/portable-build-guide.md.
#>
param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent),
    [Parameter(Mandatory = $false)][string]$Version = "",
    [string]$TaggerCacheSource = "",
    [switch]$SkipTaggerPrefetch,
    [switch]$Skip7z,
    [switch]$SkipSkeleton,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$start = Get-Date

if (-not $Version) {
    $versionFile = Join-Path $ProjectRoot "VERSION"
    if (-not (Test-Path $versionFile)) { throw "VERSION file missing; pass -Version" }
    $Version = (Get-Content $versionFile -Raw).Trim()
}

$buildDir = Join-Path $ProjectRoot "build"
$portableDir = Join-Path $buildDir "SD-Trainer-Portable"
$pythonExe = Join-Path $portableDir "python_embeded\python.exe"
$sdtDir = Join-Path $portableDir "SD-Trainer"
$logDir = Join-Path $buildDir "portable-2026-logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logFile = Join-Path $logDir ("musubi-only-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date))

function Write-Log([string]$Message, [string]$Color = "Gray") {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Write-Host $line -ForegroundColor $Color
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

Write-Log "Musubi-only portable build v$Version" "Cyan"
Write-Log "Log: $logFile" "Cyan"

if ($SkipSkeleton) {
    Write-Log "[1/4] SkipSkeleton — reuse $portableDir" "Yellow"
    if (-not (Test-Path $pythonExe)) { throw "missing $pythonExe" }
} else {
    Write-Log "[1/4] build_portable.ps1 skeleton (-Skip7z)..." "Cyan"
    $bp = Join-Path $PSScriptRoot "build_portable.ps1"
    $bpArgs = @{
        ProjectRoot = $ProjectRoot
        Version     = $Version
        Skip7z      = $true
    }
    if ($Clean) { $bpArgs.Clean = $true }
    if ($SkipTaggerPrefetch) { $bpArgs.SkipTaggerPrefetch = $true }
    if ($TaggerCacheSource) { $bpArgs.TaggerCacheSource = $TaggerCacheSource }
    & $bp @bpArgs
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        throw "build_portable.ps1 failed: $LASTEXITCODE"
    }
    if (-not (Test-Path $pythonExe)) { throw "missing $pythonExe" }
}

Write-Log "[2/4] Minimal WebUI deps (no torch index)..." "Cyan"
$guiPkgs = @(
    "fastapi==0.95.1", "uvicorn==0.22.0", "httpx==0.24.1", "toml==0.10.2",
    "pydantic==1.10.13", "python-multipart", "aiofiles", "jinja2",
    "rich==13.7.0", "requests", "pillow", "numpy==1.26.4", "safetensors==0.4.4",
    "huggingface-hub==0.36.2", "modelscope>=1.20.0", "onnxruntime-gpu",
    "voluptuous==0.13.1", "easygui==0.98.3", "imagesize==1.4.1",
    "psutil"
)
$env:PYTHONUTF8 = "1"
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $pythonExe -s -m pip install --upgrade pip 2>&1 | ForEach-Object { Add-Content $logFile $_ -Encoding UTF8; $_ }
$pip1 = $LASTEXITCODE
& $pythonExe -s -m pip install @guiPkgs 2>&1 | ForEach-Object { Add-Content $logFile $_ -Encoding UTF8; $_ }
$pip2 = $LASTEXITCODE
$ErrorActionPreference = $prevEap
if ($pip1 -ne 0 -or $pip2 -ne 0) { throw "minimal GUI pip failed: pip=$pip1 pkgs=$pip2" }

Write-Log "[3/4] Install Musubi (cu128)..." "Cyan"
$installMusubi = Join-Path $sdtDir "scripts\cli\install_musubi.py"
$musubiVendor = Join-Path $sdtDir "vendor\musubi-tuner"
$musubiMarker = Join-Path $musubiVendor "pyproject.toml"
if (-not (Test-Path $musubiMarker)) {
    New-Item -ItemType Directory -Path (Split-Path $musubiVendor -Parent) -Force | Out-Null
    if (Test-Path $musubiVendor) { Remove-Item $musubiVendor -Recurse -Force }
    $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & git clone --depth=1 https://github.com/kohya-ss/musubi-tuner.git $musubiVendor 2>&1 | ForEach-Object {
        Write-Host $_; Add-Content $logFile $_ -Encoding UTF8
    }
    $ErrorActionPreference = $prev
    if (-not (Test-Path $musubiMarker)) { throw "musubi-tuner clone failed" }
}
$prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
& $pythonExe -s $installMusubi --project-root $sdtDir --source-root $musubiVendor --cuda-extra cu128 2>&1 | ForEach-Object {
    Write-Host $_; Add-Content $logFile $_ -Encoding UTF8
}
$code = $LASTEXITCODE
$ErrorActionPreference = $prev
if ($code -ne 0) { throw "install_musubi.py failed: $code" }

$musubiPy = Join-Path $sdtDir "extensions\musubi_tuner\.venv\Scripts\python.exe"
if (-not (Test-Path $musubiPy)) { throw "musubi venv python missing: $musubiPy" }
& $musubiPy -s -c "import torch; import musubi_tuner; print('musubi_torch', torch.__version__)"
if ($LASTEXITCODE -ne 0) { throw "musubi torch import failed" }

$sha = (& git -C $sdtDir rev-parse HEAD).Trim()
$meta = @(
    $sha,
    "built_at=$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))",
    "version=$Version",
    "flavor=musubi-only"
) -join "`n"
[System.IO.File]::WriteAllText((Join-Path $sdtDir "PORTABLE_BUILD"), $meta + "`n")

$applyRoot = Join-Path $PSScriptRoot "apply_portable_2026_root.ps1"
if (Test-Path $applyRoot) {
    Write-Log "Applying 2026 root..." "Cyan"
    & $applyRoot -PortableRoot $portableDir
}

$note = Join-Path $portableDir "说明.txt"
if (Test-Path $note) {
    Add-Content -Path $note -Encoding UTF8 -Value @"

【本包说明 · Musubi / Krea2-only】
- 已预装 Musubi 引擎，用于 Krea2 LoRA（extensions/musubi_tuner）。
- 未预装完整 Kohya 主环境 Torch；常规 SDXL / Flux / Anima 请用 kohya 或 kohya-musubi 包。
- 未预装 Anima Fast 与训练底模。
"@
}

$archiveName = "Next-Trainer-v${Version}-musubi.7z"
$archivePath = Join-Path $buildDir $archiveName
$7zExe = "C:\Program Files\7-Zip\7z.exe"
if (-not (Test-Path $7zExe)) {
    $found = Get-Command 7z -ErrorAction SilentlyContinue
    if ($found) { $7zExe = $found.Source } else { $7zExe = $null }
}

if (-not $Skip7z) {
    Write-Log "[4/4] Compressing $archiveName ..." "Cyan"
    if (-not $7zExe) {
        Write-Log "7-Zip not found; left at $portableDir" "Yellow"
    } else {
        if (Test-Path $archivePath) { Remove-Item $archivePath -Force }
        & $7zExe a -t7z -mx=9 -m0=LZMA2:d=64m -ms=on -mmt=on $archivePath "$portableDir\*" | ForEach-Object {
            Add-Content -Path $logFile -Value $_ -Encoding UTF8
        }
        if ($LASTEXITCODE -ne 0) { throw "7z failed: $LASTEXITCODE" }
        $sizeGb = [math]::Round((Get-Item $archivePath).Length / 1GB, 2)
        Write-Log "Archive: $archivePath ($sizeGb GB)" "Green"
    }
} else {
    Write-Log "[4/4] Skip7z — $portableDir" "Yellow"
}

Write-Log ("DONE in {0:N1} min" -f ((Get-Date) - $start).TotalMinutes) "Green"
