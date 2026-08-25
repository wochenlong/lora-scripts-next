#Requires -Version 5.1
<#
.SYNOPSIS
  Resume after Kohya runtime is already baked: Musubi + Root2026 + 7z.
#>
param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent),
    [string]$Version = "2.9.2-dev-full",
    [switch]$Skip7z,
    [switch]$SkipMusubi
)

$ErrorActionPreference = "Stop"
$startTime = Get-Date
$buildDir = Join-Path $ProjectRoot "build"
$portableDir = Join-Path $buildDir "Next-Trainer-Portable"
$pythonExe = Join-Path $portableDir "python_embeded\python.exe"
$sdtDir = Join-Path $portableDir "Next-Trainer"
$applyRoot = Join-Path $PSScriptRoot "apply_portable_2026_root.ps1"
$logDir = Join-Path $buildDir "portable-2026-logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$logFile = Join-Path $logDir ("resume-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date))

function Write-Log([string]$Message, [string]$Color = "Gray") {
    $line = "[{0}] {1}" -f (Get-Date -Format "HH:mm:ss"), $Message
    Write-Host $line -ForegroundColor $Color
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

if (-not (Test-Path $pythonExe)) { throw "Missing $pythonExe — run full build first" }

Write-Log "Resume portable 2026 FULL  v$Version" "Cyan"

if (-not $SkipMusubi) {
    Write-Log "[1/3] Installing Musubi (cu128)..." "Cyan"
    $installMusubi = Join-Path $sdtDir "scripts\cli\install_musubi.py"
    $musubiVendor = Join-Path $sdtDir "vendor\musubi-tuner"
    $musubiMarker = Join-Path $musubiVendor "pyproject.toml"
    if (-not (Test-Path $musubiMarker)) {
        Write-Log "  Cloning kohya-ss/musubi-tuner..." "Cyan"
        New-Item -ItemType Directory -Path (Split-Path $musubiVendor -Parent) -Force | Out-Null
        if (Test-Path $musubiVendor) { Remove-Item $musubiVendor -Recurse -Force }
        $ErrorActionPreference = "Continue"
        & git clone --depth=1 https://github.com/kohya-ss/musubi-tuner.git $musubiVendor 2>&1 | ForEach-Object {
            Write-Host $_
            Add-Content -Path $logFile -Value $_ -Encoding UTF8
        }
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $musubiMarker)) {
            throw "git clone musubi-tuner failed"
        }
        $ErrorActionPreference = "Stop"
    }
    $ErrorActionPreference = "Continue"
    & $pythonExe -s $installMusubi --project-root $sdtDir --source-root $musubiVendor --cuda-extra cu128 2>&1 | ForEach-Object {
        Write-Host $_
        Add-Content -Path $logFile -Value $_ -Encoding UTF8
    }
    $code = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($code -ne 0) { throw "install_musubi.py failed (exit $code)" }
}

Write-Log "[2/3] Applying 2026 root..." "Cyan"
& $applyRoot -PortableRoot $portableDir

$archiveName = "Next-Trainer-v${Version}-kohya-musubi.7z"
$archivePath = Join-Path $buildDir $archiveName
$7zExe = "C:\Program Files\7-Zip\7z.exe"
if (-not (Test-Path $7zExe)) {
    $found = Get-Command 7z -ErrorAction SilentlyContinue
    if ($found) { $7zExe = $found.Source } else { $7zExe = $null }
}

if (-not $Skip7z) {
    Write-Log "[3/3] Compressing solid 7z..." "Cyan"
    if (-not $7zExe) {
        Write-Log "  7-Zip missing; left at $portableDir" "Yellow"
    } else {
        if (Test-Path $archivePath) { Remove-Item $archivePath -Force }
        & $7zExe a -t7z -mx=9 -m0=LZMA2:d=64m -ms=on -mmt=on $archivePath "$portableDir\*" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "7z failed" }
        $sizeGb = [math]::Round((Get-Item $archivePath).Length / 1GB, 2)
        Write-Log "  Archive: $archivePath ($sizeGb GB)" "Green"
    }
} else {
    Write-Log "[3/3] Skip7z" "Yellow"
}

$elapsed = (Get-Date) - $startTime
Write-Log ("DONE in {0:N1} min" -f $elapsed.TotalMinutes) "Green"
