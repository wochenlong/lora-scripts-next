# Pre-release checks for portable update scripts (git + release).
param(
    [Parameter(Mandatory = $true)]
    [string]$PortableRoot,
    [switch]$SkipReleaseApi
)

$ErrorActionPreference = "Stop"
$PortableRoot = (Resolve-Path $PortableRoot).Path.TrimEnd('\')
$failures = @()

function Test-FileExists([string]$RelativePath, [string]$Label) {
    $full = Join-Path $PortableRoot $RelativePath
    if (-not (Test-Path $full)) {
        $script:failures += "[FAIL] $Label missing: $RelativePath"
        return $false
    }
    Write-Host ('[OK] ' + $Label)
    return $true
}

Write-Host ""
Write-Host "Portable updater verification" -ForegroundColor Cyan
Write-Host "Root: $PortableRoot"
Write-Host ""

Test-FileExists "Update-SD-Trainer.bat" "Git updater" | Out-Null
Test-FileExists "Update-SD-Trainer-Release.bat" "Release updater" | Out-Null
Test-FileExists "update\update_sd_trainer.bat" "update_sd_trainer shortcut" | Out-Null
Test-FileExists "update\update_from_release.bat" "update_from_release shortcut" | Out-Null
Test-FileExists "SD-Trainer\scripts\portable\update_from_release.ps1" "update_from_release.ps1" | Out-Null
Test-FileExists "SD-Trainer\scripts\portable\UPDATER_VERSION" "UPDATER_VERSION" | Out-Null
Test-FileExists "SD-Trainer\scripts\portable\bootstrap_portable_updaters.ps1" "bootstrap_portable_updaters.ps1" | Out-Null
Test-FileExists "SD-Trainer\scripts\portable\portable_updater_common.ps1" "portable_updater_common.ps1" | Out-Null
Test-FileExists "SD-Trainer\scripts\portable\show_portable_update_status.ps1" "show_portable_update_status.ps1" | Out-Null

$gitHead = Join-Path $PortableRoot "SD-Trainer\.git\HEAD"
if (Test-Path $gitHead) {
    Write-Host '[OK] SD-Trainer\.git\HEAD'
} else {
    $failures += "[FAIL] SD-Trainer\.git\HEAD missing (git update will not work)"
}

$gitUpdater = Join-Path $PortableRoot "Update-SD-Trainer.bat"
if (Test-Path $gitUpdater) {
    $bat = Get-Content $gitUpdater -Raw
    if ($bat -match 'Pulling latest code') {
        $failures += "[FAIL] Update-SD-Trainer.bat is legacy (git pull without .git check); replace from Release or scripts\portable\templates"
    } elseif ($bat -notmatch 'not exist "\.git\\"') {
        $failures += "[FAIL] Update-SD-Trainer.bat missing .git pre-check"
    } elseif ($bat -notmatch 'bootstrap_updater_scripts') {
        $failures += "[FAIL] Update-SD-Trainer.bat missing updater bootstrap"
    } elseif ($bat -notmatch 'show_portable_update_status') {
        $failures += "[FAIL] Update-SD-Trainer.bat missing show_portable_update_status"
    } else {
        Write-Host '[OK] Update-SD-Trainer.bat is current (not legacy pull-only)'
    }
}

$ps1 = Join-Path $PortableRoot "SD-Trainer\scripts\portable\update_from_release.ps1"
if (Test-Path $ps1) {
    $content = Get-Content $ps1 -Raw
    if ($content -notmatch "Next-Trainer-v" -and $content -notmatch "SD-Trainer-v") {
        $failures += "[FAIL] update_from_release.ps1 missing asset filter"
    }
    $requiredUserDataMarkers = @(
        "extensions",
        '"/XD", "config"',
        "sd-models",
        "output",
        "logs",
        "train",
        "assets\config.json"
    )
    $missingUserDataMarkers = @(
        $requiredUserDataMarkers | Where-Object { -not $content.Contains($_) }
    )
    if ($missingUserDataMarkers.Count -eq 0) {
        Write-Host '[OK] update_from_release.ps1 user-data exclusions'
    } else {
        $failures += "[FAIL] update_from_release.ps1 missing user-data exclusions: $($missingUserDataMarkers -join ', ')"
    }
    if ($content -match '/XO') {
        $failures += "[FAIL] update_from_release.ps1 must not use /XO (breaks same-version republish)"
    } else {
        Write-Host '[OK] update_from_release.ps1 no /XO (same-version republish safe)'
    }
    if ($content -notmatch '/IS') {
        $failures += "[FAIL] update_from_release.ps1 missing /IS force sync"
    }
}

if (-not $SkipReleaseApi) {
    Write-Host ""
    Write-Host "Release API dry-run..."
    if (Test-Path $ps1) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $ps1 -PortableRoot $PortableRoot -DryRun
        if ($LASTEXITCODE -ne 0) {
            $failures += "[FAIL] update_from_release.ps1 -DryRun failed (network or API)"
        } else {
            Write-Host '[OK] Release API reachable'
        }
    }
}

Write-Host ""
if ($failures.Count -gt 0) {
    Write-Host ('FAILED: ' + $failures.Count + ' issue(s)') -ForegroundColor Red
    $failures | ForEach-Object { Write-Host $_ -ForegroundColor Red }
    exit 1
}

Write-Host 'All updater checks passed.' -ForegroundColor Green
exit 0
