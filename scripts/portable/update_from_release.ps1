# Sync portable Next-Trainer from the latest GitHub Release 7z (keeps user data).
param(
    [Parameter(Mandatory = $true)]
    [string]$PortableRoot,
    [switch]$DryRun,
    [string]$Tag = "",
    [string]$AssetName = ""
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "portable_updater_common.ps1")
Initialize-PortableUpdaterConsole

function Write-Step([string]$Message) {
    Write-Host $Message
}

function Resolve-SevenZip {
    $cmd = Get-Command 7z -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "${env:ProgramFiles}\7-Zip\7z.exe",
        "${env:ProgramFiles(x86)}\7-Zip\7z.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    return $null
}

function Invoke-Download([string]$Url, [string]$Destination) {
    $curl = Get-Command curl -ErrorAction SilentlyContinue
    if (-not $curl) {
        throw "curl not found. Install curl or use Git update (Update-Next-Trainer.bat)."
    }
    if (Test-Path $Destination) { Remove-Item $Destination -Force }
    & curl.exe -fL --retry 3 --retry-delay 2 -o $Destination $Url
    if ($LASTEXITCODE -ne 0) {
        throw "Download failed: $Url"
    }
}

function Get-ReleaseSyncState([string]$TrainerDir) {
    $path = Join-Path $TrainerDir "config\.portable_release_sync.json"
    if (-not (Test-Path $path)) { return $null }
    try {
        return Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Set-ReleaseSyncState([string]$TrainerDir, [object]$Asset) {
    $path = Join-Path $TrainerDir "config\.portable_release_sync.json"
    $dir = Split-Path $path -Parent
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $payload = @{
        asset_id = "$($Asset.id)"
        asset_name = "$($Asset.name)"
        asset_updated_at = "$($Asset.updated_at)"
        synced_at = (Get-Date).ToUniversalTime().ToString("o")
    }
    $payload | ConvertTo-Json | Set-Content $path -Encoding UTF8
}

function Read-PortableBuild([string]$TrainerDir) {
    Read-LocalPortableBuild $TrainerDir
}

function Get-ReleaseAsset {
    param(
        [string]$Repository,
        [string]$TagName = "",
        [string]$PreferredAssetName = ""
    )
    $headers = @{ "User-Agent" = "Next-Trainer-Portable-Updater" }
    $githubToken = if ($env:GITHUB_TOKEN) { $env:GITHUB_TOKEN } else { $env:GH_TOKEN }
    if ($githubToken) {
        $headers["Authorization"] = "Bearer $githubToken"
    }
    if ($TagName) {
        $uri = "https://api.github.com/repos/$Repository/releases/tags/$TagName"
    } else {
        $uri = "https://api.github.com/repos/$Repository/releases/latest"
    }
    $release = Invoke-RestMethod -Uri $uri -Headers $headers
    # Prefer Next Trainer archive names; keep legacy SD-Trainer-* for older releases.
    $assets = @(
        $release.assets | Where-Object {
            $_.name -like "Next-Trainer-v*.7z" -or $_.name -like "SD-Trainer-v*.7z"
        }
    )
    if ($PreferredAssetName) {
        $match = $assets | Where-Object { $_.name -eq $PreferredAssetName } | Select-Object -First 1
        if ($match) { return $match }
    }
    $preferred = @($assets | Where-Object { $_.name -like "Next-Trainer-v*.7z" })
    $pool = if ($preferred.Count -gt 0) { $preferred } else { $assets }
    $asset = $pool | Sort-Object { $_.name } -Descending | Select-Object -First 1
    if (-not $asset) {
        throw "No Next-Trainer-v*.7z (or legacy SD-Trainer-v*.7z) asset found in release $($release.tag_name)."
    }
    return $asset
}

$PortableRoot = Normalize-PortableRootPath $PortableRoot
$PortableRoot = (Resolve-Path -LiteralPath $PortableRoot).Path.TrimEnd('\')
$TrainerDir = Join-Path $PortableRoot "Next-Trainer"
if (-not (Test-Path (Join-Path $TrainerDir "gui.py"))) {
    throw "Next-Trainer not found under: $PortableRoot"
}

$repo = "wochenlong/lora-scripts-next"
$asset = Get-ReleaseAsset -Repository $repo -TagName $Tag -PreferredAssetName $AssetName
$currentVersion = Read-LocalProductVersion $TrainerDir
$currentBuild = Read-PortableBuild $TrainerDir
$updaterVersion = Read-LocalUpdaterVersion $TrainerDir
$scriptPath = $MyInvocation.MyCommand.Path
Write-PortableUpdateStatusBanner -PortableRoot $PortableRoot -UpdaterLabel "Release (PowerShell)" -UpdaterFile $scriptPath

$releaseTag = $asset.name -replace '\.7z$','' -replace '^Next-Trainer-v','v' -replace '^SD-Trainer-v','v'
$syncState = Get-ReleaseSyncState $TrainerDir

Write-Step "--- Target Release / 目标 Release ---"
Write-Step "Release tag / 发布标签: $releaseTag"
Write-Step "Release asset updated / 资产更新时间: $($asset.updated_at)"
if ($syncState -and $syncState.asset_id -eq ([string]$asset.id) -and $syncState.asset_updated_at -eq ([string]$asset.updated_at)) {
    Write-Step 'Release asset unchanged since last sync - will re-download and merge anyway.'
}
Write-Step "Asset URL: $($asset.browser_download_url)"

if ($DryRun) {
    $sevenZip = Resolve-SevenZip
    if ($sevenZip) {
        Write-Step "DryRun: 7-Zip found at $sevenZip"
    } else {
        Write-Step "DryRun: 7-Zip NOT FOUND"
    }
    Write-Step "DryRun: release metadata reachable."
    return
}

$sevenZip = Resolve-SevenZip
if (-not $sevenZip) {
    throw "7-Zip not found. Install 7-Zip or add 7z.exe to PATH."
}

$cacheDir = Join-Path $PortableRoot "update\.cache"
New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null
$archivePath = Join-Path $cacheDir $asset.name
$extractDir = Join-Path $cacheDir ("extract-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
$stagingRoot = Join-Path $extractDir "package"

$mirrors = @(
    $asset.browser_download_url,
    "https://ghfast.top/$($asset.browser_download_url)",
    "https://mirror.ghproxy.com/$($asset.browser_download_url)"
)

Write-Step ""
Write-Step "Downloading / 下载整合包..."
$downloaded = $false
foreach ($url in $mirrors) {
    Write-Step "  Try: $url"
    try {
        Invoke-Download -Url $url -Destination $archivePath
        $downloaded = $true
        Write-Step "  OK"
        break
    } catch {
        Write-Step "  Failed: $($_.Exception.Message)"
    }
}
if (-not $downloaded) {
    throw "All download mirrors failed."
}

Write-Step ""
Write-Step "Extracting / 解压..."
New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null
& $sevenZip x $archivePath "-o$stagingRoot" -y | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "7z extract failed."
}

$stagingTrainer = Join-Path $stagingRoot "Next-Trainer"
if (-not (Test-Path (Join-Path $stagingTrainer "gui.py"))) {
    # Some archives may unpack with a single top folder.
    $nested = Get-ChildItem $stagingRoot -Directory | Select-Object -First 1
    if ($nested -and (Test-Path (Join-Path $nested.FullName "Next-Trainer\gui.py"))) {
        $stagingRoot = $nested.FullName
        $stagingTrainer = Join-Path $stagingRoot "Next-Trainer"
    } else {
        throw "Extracted package missing Next-Trainer\gui.py"
    }
}

Write-Step ""
Write-Step "Merging Next-Trainer / 合并项目文件（保留用户数据）..."
$robocopyArgs = @(
    $stagingTrainer,
    $TrainerDir,
    "/E", "/IS", "/IT", "/R:2", "/W:2", "/NFL", "/NDL", "/NJH", "/NJS", "/NC", "/NS",
    "/XD", "extensions", ".cache", "__pycache__", "node_modules", ".vscode", ".cursor",
    "/XD", "config", "sd-models", "output", "logs", "train",
    "/XF", (Join-Path $stagingTrainer "assets\config.json")
)
& robocopy @robocopyArgs | Out-Null
if ($LASTEXITCODE -ge 8) {
    throw "robocopy failed with exit code $LASTEXITCODE"
}

$stagingGit = Join-Path $stagingTrainer ".git"
$destGit = Join-Path $TrainerDir ".git"
if (Test-Path $stagingGit) {
    if (Test-Path $destGit) {
        Remove-Item $destGit -Recurse -Force
    }
    Copy-Item $stagingGit $destGit -Recurse -Force
    Write-Step "Synced Next-Trainer\.git from Release package"
} else {
    Write-Step "WARNING: Release package missing Next-Trainer\.git (Git update will not work)"
}

Write-Step ""
Write-Step "Refreshing root launchers / 刷新根目录启动脚本..."
$rootFiles = @(
    "run_gui.bat",
    "run_gui_portable.bat",
    "Update-Next-Trainer.bat",
    "Update-Next-Trainer-Release.bat",
    "Download-Anima-Model.bat",
    "install_xformers.bat"
)
foreach ($name in $rootFiles) {
    $src = Join-Path $stagingRoot $name
    if (Test-Path $src) {
        $dest = Join-Path $PortableRoot $name
        if ($name -like "*.bat") {
            Write-PortableBatchFile -Source $src -Destination $dest
        } else {
            Copy-Item $src -Destination $dest -Force
        }
        Write-Step "  Updated: $name"
    }
}

Write-Step "Repairing .bat line endings (CRLF) / 修复 bat 换行..."
Repair-PortableBatchFilesInTree -Root $PortableRoot

if (Test-Path (Join-Path $stagingRoot "update")) {
    $destUpdate = Join-Path $PortableRoot "update"
    New-Item -ItemType Directory -Path $destUpdate -Force | Out-Null
    Copy-Item (Join-Path $stagingRoot "update\*") $destUpdate -Recurse -Force
}

$newVersion = ""
if (Test-Path (Join-Path $stagingTrainer "VERSION")) {
    $newVersion = (Get-Content (Join-Path $stagingTrainer "VERSION") -TotalCount 1).Trim()
}
$newBuild = Read-PortableBuild $stagingTrainer
Set-ReleaseSyncState -TrainerDir $TrainerDir -Asset $asset

Write-Step ""
Write-Step "========================================"
Write-Step "  Done / 更新完成"
Write-Step "========================================"
Write-Step "  Updater script version / 更新脚本版本: $updaterVersion"
if ($newVersion) {
    Write-Step "  New VERSION / 新版本: $newVersion"
}
if ($newBuild) {
    Write-Step "  New PORTABLE_BUILD / 新构建: $newBuild"
}
if ($currentVersion -and $newVersion -and $currentVersion -ne $newVersion) {
    Write-Step "  VERSION changed / 版本变化: $currentVersion -> $newVersion"
}
if ($currentBuild -and $newBuild -and $currentBuild -ne $newBuild) {
    Write-Step "  PORTABLE_BUILD changed / 构建变化: $currentBuild -> $newBuild"
}
if ($newVersion -and $currentVersion -and $newVersion -eq $currentVersion -and $newBuild -and $newBuild -ne $currentBuild) {
    Write-Step ""
    Write-Step "Same VERSION but newer build synced (hotfix republish)."
    Write-Step 'Same VERSION hotfix republish synced.'
}
Write-Step ""
Write-Step 'Preserved / user data kept:'
Write-Step '  Next-Trainer\sd-models\  Next-Trainer\output\  Next-Trainer\logs\  Next-Trainer\train\'
Write-Step '  Next-Trainer\config\  Next-Trainer\assets\config.json'
Write-Step '  huggingface\  tagger-models\  (portable root)'
Write-Step '  Next-Trainer\extensions\  (Anima Fast plugin, if installed)'
Write-Step ""
if ($newVersion -and $currentVersion -and ($newVersion -ne $currentVersion -or ($newBuild -and $newBuild -ne $currentBuild))) {
    Write-Step 'If WebUI fails to start, run update\update_dependencies.bat'
    Write-Step 'WebUI startup failed? Run update\update_dependencies.bat to sync deps.'
}

exit 0
