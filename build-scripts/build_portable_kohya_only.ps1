#Requires -Version 5.1
<#
.SYNOPSIS
  Build Kohya-only portable (cu128 main runtime, NO Musubi).

.DESCRIPTION
  Thin wrapper around build_portable_2026_full.ps1 -SkipMusubi,
  then rename archive to Next-Trainer-v{Version}-kohya.7z.
  See docs/portable-build-guide.md.
#>
param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent),
    [Parameter(Mandatory = $false)][string]$Version = "",
    [string]$TaggerCacheSource = "",
    [switch]$SkipTaggerPrefetch,
    [switch]$Skip7z,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

if (-not $Version) {
    $versionFile = Join-Path $ProjectRoot "VERSION"
    if (-not (Test-Path $versionFile)) { throw "VERSION file missing; pass -Version" }
    $Version = (Get-Content $versionFile -Raw).Trim()
}

$full = Join-Path $PSScriptRoot "build_portable_2026_full.ps1"
if (-not (Test-Path $full)) { throw "missing $full" }

$argsHash = @{
    ProjectRoot = $ProjectRoot
    Version     = $Version
    SkipMusubi  = $true
}
if ($Clean) { $argsHash.Clean = $true }
if ($Skip7z) { $argsHash.Skip7z = $true }
if ($SkipTaggerPrefetch) { $argsHash.SkipTaggerPrefetch = $true }
if ($TaggerCacheSource) { $argsHash.TaggerCacheSource = $TaggerCacheSource }

Write-Host "Kohya-only portable build v$Version" -ForegroundColor Cyan
& $full @argsHash
if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
    throw "build_portable_2026_full.ps1 failed: $LASTEXITCODE"
}

$buildDir = Join-Path $ProjectRoot "build"
$portableDir = Join-Path $buildDir "Next-Trainer-Portable"
$sdtDir = Join-Path $portableDir "Next-Trainer"
$builtMusubiName = Join-Path $buildDir "Next-Trainer-v${Version}-kohya-musubi.7z"
$kohyaName = Join-Path $buildDir "Next-Trainer-v${Version}-kohya.7z"

if (-not $Skip7z) {
    if (Test-Path $builtMusubiName) {
        if (Test-Path $kohyaName) { Remove-Item $kohyaName -Force }
        Move-Item $builtMusubiName $kohyaName -Force
        Write-Host "Archive: $kohyaName" -ForegroundColor Green
    } elseif (-not (Test-Path $kohyaName)) {
        Write-Host "WARN: expected archive not found (Skip7z or 7z missing?)" -ForegroundColor Yellow
    }
}

if (Test-Path (Join-Path $sdtDir "PORTABLE_BUILD")) {
    $sha = (& git -C $sdtDir rev-parse HEAD).Trim()
    $meta = @(
        $sha,
        "built_at=$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))",
        "version=$Version",
        "flavor=kohya-only"
    ) -join "`n"
    [System.IO.File]::WriteAllText((Join-Path $sdtDir "PORTABLE_BUILD"), $meta + "`n")
}

$note = Join-Path $portableDir "说明.txt"
if (Test-Path $note) {
    Add-Content -Path $note -Encoding UTF8 -Value @"

【本包说明 · Kohya-only】
- 已预装 Kohya 主环境（cu128），可训 Anima / SD / SDXL / Flux 等主线。
- 未预装 Musubi；Krea2 请用 musubi 或 kohya-musubi 包，或在设置页安装 Musubi。
- 未预装 Anima Fast；需要时在设置 → 训练引擎安装。
"@
}

Write-Host "DONE kohya-only v$Version" -ForegroundColor Green
