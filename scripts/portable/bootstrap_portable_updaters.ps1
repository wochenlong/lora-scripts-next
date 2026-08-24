param(
    [Parameter(Mandatory = $true)]
    [string]$PortableRoot,
    [switch]$SkipDownload
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

. (Join-Path $PSScriptRoot "portable_updater_common.ps1")
Initialize-PortableUpdaterConsole

$PortableRoot = Normalize-PortableRootPath $PortableRoot
$trainerDir = Join-Path $PortableRoot "Next-Trainer"
$updated = $false

$localUpdater = (Read-LocalUpdaterVersion $trainerDir).Trim()
$remoteUpdater = (Get-RemoteUpdaterVersionOnline).Trim()
if ($localUpdater -and $localUpdater -ne "unknown") {
    if (-not $remoteUpdater) {
        Write-Host "Online updater version unavailable; keeping local v$localUpdater."
        Write-Host "无法获取线上更新脚本版本，保留本地 v$localUpdater。"
        Write-Host ""
        exit 0
    }
    try {
        if ([int]$localUpdater -gt [int]$remoteUpdater) {
            Write-Host "Local updater v$localUpdater is newer than GitHub main v$remoteUpdater; skipping bootstrap download."
            Write-Host "本地更新脚本 v$localUpdater 高于 GitHub main v$remoteUpdater，跳过在线覆盖。"
            Write-Host ""
            exit 0
        }
    } catch {
        # Non-numeric UPDATER_VERSION values fall through to hash sync.
    }
}

function Get-FileSha256([string]$Path) {
    if (-not (Test-Path $Path)) { return "" }
    return (Get-FileHash -Path $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if (-not $SkipDownload) {
    Write-Host "Checking latest updater scripts on GitHub / 检查 GitHub 最新更新脚本..."
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("next-trainer-updater-bootstrap-" + [guid]::NewGuid().ToString("n"))
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    try {
        foreach ($item in (Get-PortableUpdaterManifest)) {
            $tempFile = Join-Path $tempRoot (($item.Src -replace '[/\\]', '_'))
            try {
                Invoke-PortableRawDownload -RelativePath $item.Src -Destination $tempFile | Out-Null
            } catch {
                Write-Host "  [skip] $($item.Src) ($($_.Exception.Message))"
                continue
            }
            $dest = Join-Path $PortableRoot ($item.Dest -replace '/', '\')
            $destDir = Split-Path $dest -Parent
            if ($destDir -and -not (Test-Path $destDir)) {
                New-Item -ItemType Directory -Path $destDir -Force | Out-Null
            }
            $oldHash = Get-FileSha256 $dest
            $newHash = Get-FileSha256 $tempFile
            if ($oldHash -ne $newHash) {
                Copy-Item $tempFile $dest -Force
                Ensure-PortablePs1Utf8Bom -Path $dest
                Write-Host "  [updated] $($item.Dest)"
                $updated = $true
            }
        }
    } finally {
        if (Test-Path $tempRoot) { Remove-Item $tempRoot -Recurse -Force -ErrorAction SilentlyContinue }
    }
    if ($updated) {
        Write-Host "Updater scripts synced from GitHub main / 已从 GitHub main 同步更新脚本。"
        Write-Host ""
    } else {
        Write-Host "Updater scripts already current / 更新脚本已是最新。"
        Write-Host ""
    }
}

if ($updated) {
    exit 10
}
exit 0
