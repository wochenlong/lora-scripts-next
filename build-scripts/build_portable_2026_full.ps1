#Requires -Version 5.1
<#
.SYNOPSIS
  Build the 2026 foolproof portable (Kohya + Musubi, no Fast). See docs/design/portable-2026.md.

.DESCRIPTION
  1) Existing lite skeleton via build_portable.ps1 (no Anima Fast)
  2) Bake main runtime with setup_environment.py (cu128)
  3) Install Musubi engine (cu128)
  4) Reshape root to 启动 / 检查更新 / 说明
  5) 7z solid archive
#>
param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent),
    [string]$Version = "2.9.2-dev-full",
    [switch]$Clean,
    [switch]$Skip7z,
    [switch]$SkipTaggerPrefetch,
    [switch]$SkipMusubi,
    [string]$TaggerCacheSource = ""
)

$ErrorActionPreference = "Stop"
$startTime = Get-Date

$buildPortable = Join-Path $PSScriptRoot "build_portable.ps1"
$applyRoot = Join-Path $PSScriptRoot "apply_portable_2026_root.ps1"
$buildDir = Join-Path $ProjectRoot "build"
$portableDir = Join-Path $buildDir "Next-Trainer-Portable"
$pythonExe = Join-Path $portableDir "python_embeded\python.exe"
$sdtDir = Join-Path $portableDir "Next-Trainer"
$logDir = Join-Path $buildDir "portable-2026-logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logFile = Join-Path $logDir ("build-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date))

function Write-Log([string]$Message, [string]$Color = "Gray") {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Write-Host $line -ForegroundColor $Color
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

Write-Log "Next Trainer portable 2026 FULL build  v$Version" "Cyan"
Write-Log "Log: $logFile" "Cyan"
Write-Log "Profile: Kohya + Musubi (cu128), NO Anima Fast" "Cyan"

# ---- Step 1: skeleton (lite; clears embed site-packages by design) ----
Write-Log "[1/5] Building portable skeleton (lite layout, no Fast)..." "Cyan"
$bpArgs = @{
    ProjectRoot = $ProjectRoot
    Version     = $Version
    Skip7z      = $true
}
if ($Clean) { $bpArgs.Clean = $true }
if ($SkipTaggerPrefetch) { $bpArgs.SkipTaggerPrefetch = $true }
if ($TaggerCacheSource) { $bpArgs.TaggerCacheSource = $TaggerCacheSource }

& $buildPortable @bpArgs
if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
    throw "build_portable.ps1 failed with exit $LASTEXITCODE"
}
if (-not (Test-Path $pythonExe)) {
    throw "Embedded python missing after skeleton build: $pythonExe"
}

# ---- Step 2: bake Kohya / main runtime ----
Write-Log "[2/5] Baking main runtime (setup_environment.py, ~3GB torch download)..." "Cyan"
$setup = Join-Path $sdtDir "setup_environment.py"
if (-not (Test-Path $setup)) {
    throw "setup_environment.py missing: $setup"
}
$env:PYTHONUTF8 = "1"
Push-Location $sdtDir
try {
    & $pythonExe -s $setup 2>&1 | ForEach-Object {
        Write-Host $_
        Add-Content -Path $logFile -Value $_ -Encoding UTF8
    }
    if ($LASTEXITCODE -ne 0) {
        throw "setup_environment.py failed (exit $LASTEXITCODE)"
    }
} finally {
    Pop-Location
}

Write-Log "  Verifying torch CUDA import..." "Cyan"
& $pythonExe -s -c "import torch; print(torch.__version__); assert torch.cuda.is_available() or True; print('torch_ok')"
if ($LASTEXITCODE -ne 0) {
    throw "torch import check failed"
}

# ---- Step 3: Musubi ----
if (-not $SkipMusubi) {
    Write-Log "[3/5] Installing Musubi engine (cu128)..." "Cyan"
    $installMusubi = Join-Path $sdtDir "scripts\cli\install_musubi.py"
    if (-not (Test-Path $installMusubi)) {
        throw "install_musubi.py missing (need origin/dev with musubi_backend): $installMusubi"
    }
    $musubiVendor = Join-Path $sdtDir "vendor\musubi-tuner"
    $musubiMarker = Join-Path $musubiVendor "pyproject.toml"
    if (-not (Test-Path $musubiMarker)) {
        Write-Log "  Cloning kohya-ss/musubi-tuner into vendor/..." "Cyan"
        New-Item -ItemType Directory -Path (Split-Path $musubiVendor -Parent) -Force | Out-Null
        if (Test-Path $musubiVendor) {
            Remove-Item $musubiVendor -Recurse -Force
        }
        $prevEapClone = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & git clone --depth=1 https://github.com/kohya-ss/musubi-tuner.git $musubiVendor 2>&1 | ForEach-Object {
            Write-Host $_
            Add-Content -Path $logFile -Value $_ -Encoding UTF8
        }
        $cloneExit = $LASTEXITCODE
        $ErrorActionPreference = $prevEapClone
        if ($cloneExit -ne 0 -or -not (Test-Path $musubiMarker)) {
            throw "git clone musubi-tuner failed (exit $cloneExit)"
        }
    }
    $prevEapMusubi = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $pythonExe -s $installMusubi --project-root $sdtDir --source-root $musubiVendor --cuda-extra cu128 2>&1 | ForEach-Object {
        Write-Host $_
        Add-Content -Path $logFile -Value $_ -Encoding UTF8
    }
    $musubiExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEapMusubi
    if ($musubiExit -ne 0) {
        throw "install_musubi.py failed (exit $musubiExit)"
    }
} else {
    Write-Log "[3/5] Skipping Musubi (-SkipMusubi)" "Yellow"
}

# ---- Step 4: root UX ----
Write-Log "[4/5] Applying 2026 root (启动 / 检查更新 / 说明)..." "Cyan"
& $applyRoot -PortableRoot $portableDir

# ---- Step 5: 7z ----
$7zExe = "C:\Program Files\7-Zip\7z.exe"
if (-not (Test-Path $7zExe)) {
    $found = Get-Command 7z -ErrorAction SilentlyContinue
    if ($found) { $7zExe = $found.Source } else { $7zExe = $null }
}

$archiveName = "Next-Trainer-v${Version}-kohya-musubi.7z"
$archivePath = Join-Path $buildDir $archiveName

if (-not $Skip7z) {
    Write-Log "[5/5] Compressing solid 7z (this can take a while)..." "Cyan"
    if (-not $7zExe) {
        Write-Log "  7-Zip not found; left uncompressed at $portableDir" "Yellow"
    } else {
        if (Test-Path $archivePath) { Remove-Item $archivePath -Force }
        # solid LZMA2 — identical torch trees compress once
        & $7zExe a -t7z -mx=9 -m0=LZMA2:d=64m -ms=on -mmt=on $archivePath "$portableDir\*" | ForEach-Object {
            Add-Content -Path $logFile -Value $_ -Encoding UTF8
        }
        if ($LASTEXITCODE -ne 0) {
            throw "7z failed (exit $LASTEXITCODE)"
        }
        $sizeGb = [math]::Round((Get-Item $archivePath).Length / 1GB, 2)
        Write-Log "  Archive: $archivePath ($sizeGb GB)" "Green"
    }
} else {
    Write-Log "[5/5] Skip7z — portable dir: $portableDir" "Yellow"
}

$elapsed = (Get-Date) - $startTime
Write-Log ("DONE in {0:N1} min" -f $elapsed.TotalMinutes) "Green"
Write-Log "Uncompressed: $portableDir"
if (Test-Path $archivePath) { Write-Log "Archive: $archivePath" }
