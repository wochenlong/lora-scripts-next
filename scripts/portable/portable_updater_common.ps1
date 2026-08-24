# Shared helpers for portable Git / Release updaters.
$script:PortableUpdaterRepo = "wochenlong/lora-scripts-next"
$script:PortableUpdaterBranch = "main"

function Initialize-PortableUpdaterConsole {
    try { cmd /c "chcp 65001 >nul" 2>$null | Out-Null } catch {}
    if ($Host.Name -eq "ConsoleHost") {
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
    }
}

function Ensure-PortablePs1Utf8Bom {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not $Path.EndsWith(".ps1", [System.StringComparison]::OrdinalIgnoreCase)) { return }
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) { return }
    $text = [System.IO.File]::ReadAllText($Path, (New-Object System.Text.UTF8Encoding $false))
    [System.IO.File]::WriteAllText($Path, $text, (New-Object System.Text.UTF8Encoding $true))
}

function Get-PortableUpdaterManifest {
    @(
        @{ Src = "build-scripts/templates/Update-Next-Trainer.bat"; Dest = "Update-Next-Trainer.bat" },
        @{ Src = "build-scripts/templates/Update-Next-Trainer-Release.bat"; Dest = "Update-Next-Trainer-Release.bat" },
        @{ Src = "build-scripts/templates/Fix-Portable-Bats.bat"; Dest = "Fix-Portable-Bats.bat" },
        @{ Src = "scripts/portable/update_from_release.ps1"; Dest = "Next-Trainer/scripts/portable/update_from_release.ps1" },
        @{ Src = "scripts/portable/bootstrap_portable_updaters.ps1"; Dest = "Next-Trainer/scripts/portable/bootstrap_portable_updaters.ps1" },
        @{ Src = "scripts/portable/show_portable_update_status.ps1"; Dest = "Next-Trainer/scripts/portable/show_portable_update_status.ps1" },
        @{ Src = "scripts/portable/portable_updater_common.ps1"; Dest = "Next-Trainer/scripts/portable/portable_updater_common.ps1" },
        @{ Src = "scripts/portable/sync_portable_root_launchers.bat"; Dest = "Next-Trainer/scripts/portable/sync_portable_root_launchers.bat" },
        @{ Src = "scripts/portable/UPDATER_VERSION"; Dest = "Next-Trainer/scripts/portable/UPDATER_VERSION" },
        @{ Src = "build-scripts/templates/Update-Next-Trainer.bat"; Dest = "Next-Trainer/scripts/portable/templates/Update-Next-Trainer.bat" },
        @{ Src = "build-scripts/templates/Update-Next-Trainer-Release.bat"; Dest = "Next-Trainer/scripts/portable/templates/Update-Next-Trainer-Release.bat" }
    )
}

function Get-RawGitHubUrls([string]$RelativePath) {
    $rel = $RelativePath -replace '\\', '/'
    $base = "https://raw.githubusercontent.com/$($script:PortableUpdaterRepo)/$($script:PortableUpdaterBranch)/$rel"
    @(
        $base,
        "https://ghfast.top/$base",
        "https://mirror.ghproxy.com/$base"
    )
}

function Invoke-PortableRawDownload {
    param(
        [string]$RelativePath,
        [string]$Destination
    )
    $curl = Get-Command curl -ErrorAction SilentlyContinue
    if (-not $curl) {
        throw "curl not found"
    }
    $dir = Split-Path $Destination -Parent
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    if (Test-Path $Destination) { Remove-Item $Destination -Force }
    $lastError = ""
    foreach ($url in (Get-RawGitHubUrls $RelativePath)) {
        & curl.exe -fsSL --retry 2 --retry-delay 1 -o $Destination $url 2>$null
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $Destination) -and ((Get-Item -LiteralPath $Destination).Length -gt 0)) {
            Ensure-PortablePs1Utf8Bom -Path $Destination
            return $true
        }
        $lastError = "curl exit $LASTEXITCODE for $url"
    }
    throw "Download failed for $RelativePath ($lastError)"
}

function Get-RemoteTextFromMain {
    param([string]$RelativePath)
    $temp = Join-Path ([System.IO.Path]::GetTempPath()) ("next-trainer-updater-" + [guid]::NewGuid().ToString("n") + ".txt")
    try {
        Invoke-PortableRawDownload -RelativePath $RelativePath -Destination $temp | Out-Null
        return ((Get-Content $temp -TotalCount 1 -ErrorAction Stop) -join "").Trim()
    } catch {
        return ""
    } finally {
        if (Test-Path $temp) { Remove-Item $temp -Force -ErrorAction SilentlyContinue }
    }
}

function Get-RemoteMainProductVersion {
    Get-RemoteTextFromMain "VERSION"
}

function Get-RemoteUpdaterVersionOnline {
    Get-RemoteTextFromMain "scripts/portable/UPDATER_VERSION"
}

function Get-RemoteLatestReleaseTag {
    try {
        $headers = @{ "User-Agent" = "Next-Trainer-Portable-Updater" }
        $uri = "https://api.github.com/repos/$($script:PortableUpdaterRepo)/releases/latest"
        $release = Invoke-RestMethod -Uri $uri -Headers $headers
        $tag = [string]$release.tag_name
        if ($tag -match '^v?(?<ver>.+)$') { return $Matches['ver'] }
        return $tag.TrimStart('v')
    } catch {
        return ""
    }
}

function Normalize-PortableRootPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $Path }
    return $Path.Trim().Trim('"').TrimEnd('\', '/')
}

function Write-PortableBatchFile {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    if (-not (Test-Path $Source)) {
        throw "Batch source not found: $Source"
    }
    $dir = Split-Path $Destination -Parent
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $text = [System.IO.File]::ReadAllText($Source)
    $text = $text -replace "`r`n", "`n" -replace "`r", "`n" -replace "`n", "`r`n"
    if ($text.Length -gt 0 -and [int][char]$text[0] -eq 0xFEFF) {
        $text = $text.Substring(1)
    }
    [System.IO.File]::WriteAllText($Destination, $text, (New-Object System.Text.UTF8Encoding $false))
}

function Repair-PortableBatchFilesInTree {
    param([Parameter(Mandatory = $true)][string]$Root)
    Get-ChildItem -Path $Root -Filter "*.bat" -Recurse -File | ForEach-Object {
        Write-PortableBatchFile -Source $_.FullName -Destination $_.FullName
    }
}

function Read-LocalProductVersion([string]$TrainerDir) {
    $path = Join-Path $TrainerDir "VERSION"
    if (-not (Test-Path -LiteralPath $path)) { return "" }
    return ((Get-Content -LiteralPath $path -TotalCount 1) -join "").Trim()
}

function Read-LocalPortableBuild([string]$TrainerDir) {
    $path = Join-Path $TrainerDir "PORTABLE_BUILD"
    if (-not (Test-Path -LiteralPath $path)) { return "" }
    return ((Get-Content -LiteralPath $path -TotalCount 1) -join "").Trim()
}

function Read-LocalUpdaterVersion([string]$TrainerDir) {
    $path = Join-Path $TrainerDir "scripts/portable/UPDATER_VERSION"
    if (-not (Test-Path -LiteralPath $path)) { return "unknown" }
    return ((Get-Content -LiteralPath $path -TotalCount 1) -join "").Trim()
}

function Get-LocalGitCommit([string]$TrainerDir) {
    if (-not (Test-Path (Join-Path $TrainerDir ".git/HEAD"))) { return "" }
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    $hash = (& git -C $TrainerDir rev-parse --short HEAD 2>$null | Select-Object -First 1)
    $ErrorActionPreference = $prev
    if ($hash) { return $hash.Trim() }
    return ""
}

function Write-PortableUpdateStatusBanner {
    param(
        [string]$PortableRoot,
        [string]$UpdaterLabel = "Portable",
        [string]$UpdaterFile = ""
    )
    $PortableRoot = Normalize-PortableRootPath $PortableRoot
    $trainerDir = Join-Path $PortableRoot "Next-Trainer"
    $localVersion = Read-LocalProductVersion $trainerDir
    $localBuild = Read-LocalPortableBuild $trainerDir
    $localUpdater = Read-LocalUpdaterVersion $trainerDir
    $localGit = Get-LocalGitCommit $trainerDir

    $remoteMain = Get-RemoteMainProductVersion
    $remoteRelease = Get-RemoteLatestReleaseTag
    $remoteUpdater = Get-RemoteUpdaterVersionOnline

    Initialize-PortableUpdaterConsole
    Write-Host "--- Package status / 当前整合包 ---"
    Write-Host ("  VERSION (local / 当前): " + $(if ($localVersion) { $localVersion } else { "(missing)" }))
    if ($localBuild) { Write-Host "  PORTABLE_BUILD (local / 当前): $localBuild" }
    if ($localGit) {
        Write-Host "  Git commit (local / 当前): $localGit"
    } else {
        Write-Host "  Git commit (local / 当前): (no .git / 无 git 仓库)"
    }

    Write-Host "--- Online / 线上最新 ---"
    Write-Host ("  main branch VERSION / main 分支: " + $(if ($remoteMain) { $remoteMain } else { "(unavailable / 无法获取)" }))
    Write-Host ("  Latest Release / 最新 Release: " + $(if ($remoteRelease) { $remoteRelease } else { "(unavailable / 无法获取)" }))
    Write-Host ("  Updater script (online / 线上更新脚本): " + $(if ($remoteUpdater) { $remoteUpdater } else { "(unavailable / 无法获取)" }))

    Write-Host "--- Updater / 本地更新脚本 ---"
    Write-Host ("  Updater script (local / 当前更新脚本): $localUpdater")
    Write-Host ("  Updater kind / 更新类型: $UpdaterLabel")
    if ($UpdaterFile) { Write-Host "  Updater file / 脚本路径: $UpdaterFile" }
    Write-Host ""
}
