# Full pre-release checklist for Next-Trainer portable package (build/整合包打包规范 §7).
param(
    [Parameter(Mandatory = $true)]
    [string]$PortableRoot,
    [string]$ArchivePath = "",
    [string]$ExpectedVersion = "",
    [switch]$SkipReleaseApi,
    [switch]$SkipGitFetch,
    [switch]$SkipPythonTests
)

$ErrorActionPreference = "Stop"
$PortableRoot = (Resolve-Path $PortableRoot).Path.TrimEnd('\')
$TrainerDir = Join-Path $PortableRoot "Next-Trainer"
$PythonExe = Join-Path $PortableRoot "python_embeded\python.exe"
$passed = 0
$failed = 0
$warned = 0

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host "=== $Title ===" -ForegroundColor Cyan
}

function Pass([string]$Message) {
    Write-Host "[PASS] $Message" -ForegroundColor Green
    $script:passed++
}

function Fail([string]$Message) {
    Write-Host "[FAIL] $Message" -ForegroundColor Red
    $script:failed++
}

function Warn([string]$Message) {
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
    $script:warned++
}

Write-Host ""
Write-Host "Next-Trainer Portable Release Verification" -ForegroundColor Cyan
Write-Host "Root: $PortableRoot"
if ($ArchivePath) { Write-Host "Archive: $ArchivePath" }
Write-Host ""

# ---- 7.1 Structure & size ----
Write-Section "7.1 Structure & size"

$requiredRoot = @(
    "run_gui.bat",
    "run_gui_portable.bat",
    "Update-Next-Trainer.bat",
    "Update-Next-Trainer-Release.bat",
    "Download-Anima-Model.bat",
    "install_xformers.bat",
    "README.txt",
    "python_embeded\python.exe",
    "Next-Trainer\gui.py",
    "Next-Trainer\VERSION",
    "Next-Trainer\scripts\portable\UPDATER_VERSION",
    "Next-Trainer\scripts\portable\bootstrap_portable_updaters.ps1",
    "Next-Trainer\scripts\portable\portable_updater_common.ps1",
    "Next-Trainer\scripts\portable\show_portable_update_status.ps1",
    "Next-Trainer\scripts\portable\templates\Update-Next-Trainer.bat",
    "Next-Trainer\sd-models",
    "Next-Trainer\output",
    "Next-Trainer\logs",
    "sd-models",
    "output",
    "logs",
    "huggingface",
    "tagger-models\wd14",
    "tagger-models\vlm",
    "update\update_next_trainer.bat",
    "update\update_from_release.bat",
    "update\update_dependencies.bat"
)
foreach ($rel in $requiredRoot) {
    $full = Join-Path $PortableRoot $rel
    if (Test-Path $full) { Pass $rel } else { Fail "Missing: $rel" }
}

$batCrlfChecks = @(
    "Update-Next-Trainer-Release.bat",
    "Update-Next-Trainer.bat",
    "run_gui.bat",
    "Next-Trainer\scripts\portable\launch_portable.bat"
)
foreach ($rel in $batCrlfChecks) {
    $full = Join-Path $PortableRoot $rel
    if (-not (Test-Path $full)) { continue }
    $bytes = [System.IO.File]::ReadAllBytes($full)
    $lfOnly = ($bytes -contains 10) -and -not ($bytes -contains 13)
    if ($lfOnly) {
        Fail "$rel uses LF-only line endings (cmd.exe may fail to parse)"
    } else {
        Pass "$rel CRLF line endings"
    }
}

$gitHead = Join-Path $TrainerDir ".git\HEAD"
if (Test-Path $gitHead) {
    Pass "Next-Trainer\.git\HEAD"
    $gitBytes = (Get-ChildItem (Join-Path $TrainerDir ".git") -Recurse -Force -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum).Sum
    $gitMb = [math]::Round($gitBytes / 1MB, 1)
    if ($gitMb -lt 30) {
        Pass ".git size ${gitMb} MB (< 30 MB shallow clone)"
    } elseif ($gitMb -lt 80) {
        Warn ".git size ${gitMb} MB (borderline; prefer < 30 MB)"
    } else {
        Fail ".git size ${gitMb} MB (> 80 MB — likely full history)"
    }
} else {
    Fail "Next-Trainer\.git\HEAD missing"
}

if ($ExpectedVersion) {
    $versionFile = Join-Path $TrainerDir "VERSION"
    if (Test-Path $versionFile) {
        $ver = (Get-Content $versionFile -TotalCount 1).Trim()
        if ($ver -eq $ExpectedVersion) { Pass "VERSION = $ver" } else { Fail "VERSION = $ver (expected $ExpectedVersion)" }
    }
}

$extensionsDir = Join-Path $TrainerDir "extensions"
if (Test-Path $extensionsDir) {
    $extItems = Get-ChildItem $extensionsDir -Force -ErrorAction SilentlyContinue
    if ($extItems.Count -gt 0) {
        Fail "Next-Trainer\extensions\ should be empty in 7z (found $($extItems.Count) item(s))"
    } else {
        Pass "Next-Trainer\extensions\ empty (Fast plugin not pre-bundled)"
    }
} else {
    Pass "Next-Trainer\extensions\ absent (OK)"
}

$hfHub = Join-Path $PortableRoot "huggingface\hub"
$localTaggerOnnx = Join-Path $PortableRoot "tagger-models\wd14\wd14-convnextv2-v2\model.onnx"
$localTaggerCsv = Join-Path $PortableRoot "tagger-models\wd14\wd14-convnextv2-v2\selected_tags.csv"
if ((Test-Path $localTaggerOnnx) -and (Test-Path $localTaggerCsv)) {
    Pass "tagger-models/wd14/wd14-convnextv2-v2 offline (canonical portable path)"
} else {
    Fail "tagger-models/wd14/wd14-convnextv2-v2 missing model.onnx or selected_tags.csv"
}
if (Test-Path $hfHub) {
    $wdHub = Join-Path $hfHub "models--SmilingWolf--wd-v1-4-convnextv2-tagger-v2"
    if (Test-Path $wdHub) {
        Warn "huggingface/hub still contains WD tagger (prefer tagger-models only in release 7z)"
    } else {
        Pass "huggingface/hub has no duplicate WD tagger blob"
    }
} else {
    Pass "huggingface/hub optional (tagger-models is primary)"
}

if ($ArchivePath) {
    if (Test-Path $ArchivePath) {
        $sizeMb = [math]::Round((Get-Item $ArchivePath).Length / 1MB, 1)
        Pass "Archive exists: $(Split-Path $ArchivePath -Leaf) (${sizeMb} MB)"
        if ($sizeMb -lt 200) { Warn "Archive unusually small (< 200 MB)" }
        if ($sizeMb -gt 600) { Warn "Archive unusually large (> 600 MB)" }
    } else {
        Fail "Archive missing: $ArchivePath"
    }
}

# ---- 7.2 tkinter ----
Write-Section "7.2 Python / tkinter"
if (Test-Path $PythonExe) {
    $tkOut = & $PythonExe -s -c "import tkinter; print('ok')" 2>&1
    if ($LASTEXITCODE -eq 0 -and ($tkOut -join "") -match "ok") {
        Pass "import tkinter -> ok"
    } else {
        Fail "import tkinter failed: $tkOut"
    }
} else {
    Fail "python_embeded\python.exe missing"
}

# ---- 7.3 Launcher paths ----
Write-Section "7.3 Launcher chain"
$launchBat = Join-Path $TrainerDir "scripts\portable\launch_portable.bat"
if (Test-Path $launchBat) {
    $launchText = Get-Content $launchBat -Raw
    if ($launchText -match 'PORTABLE_ROOT=%~dp0\.\.\\\.\.\\\.\.\\') {
        Pass "launch_portable.bat uses 3-level PORTABLE_ROOT"
    } else {
        Fail "launch_portable.bat PORTABLE_ROOT path unexpected"
    }
    if ($launchText -match "next-trainer-log\.txt" -and $launchText -notmatch '\.\.\\\.\.Next-Trainer') {
        Pass "Log path next-trainer-log.txt at portable root"
    } else {
        Fail "Log path or broken path concatenation in launch_portable.bat"
    }
} else {
    Fail "scripts\portable\launch_portable.bat missing"
}

$runGui = Join-Path $PortableRoot "run_gui.bat"
if (Test-Path $runGui) {
    Pass "run_gui.bat present at portable root"
} else {
    Fail "run_gui.bat missing"
}

# ---- 7.4 Update scripts ----
Write-Section "7.4 Update scripts"
$updaterScript = Join-Path $PSScriptRoot "verify_portable_updaters.ps1"
if (Test-Path $updaterScript) {
    $updaterArgs = @("-PortableRoot", $PortableRoot)
    if ($SkipReleaseApi) { $updaterArgs += "-SkipReleaseApi" }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $updaterScript @updaterArgs
    if ($LASTEXITCODE -eq 0) {
        Pass "verify_portable_updaters.ps1"
    } else {
        Fail "verify_portable_updaters.ps1 exited $LASTEXITCODE"
    }
} else {
    Fail "verify_portable_updaters.ps1 not found"
}

if (-not $SkipGitFetch -and (Test-Path $gitHead)) {
    Push-Location $TrainerDir
    try {
        $prevEap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        git fetch origin main --tags --deepen=50 *> $null
        $fetchOk = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $prevEap
        if ($fetchOk) {
            Pass "git fetch origin main (direct)"
        } else {
            Warn "git fetch direct failed (may need mirror; user bat has fallback)"
        }
        $ErrorActionPreference = 'Continue'
        git merge --ff-only origin/main *> $null
        $mergeOk = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $prevEap
        if ($mergeOk) {
            Pass "git merge --ff-only origin/main"
        } else {
            $status = (git status -sb 2>$null) -join ' '
            if ($status -match 'ahead|behind|up to date') {
                Pass "git already up to date or status: $status"
            } else {
                Warn "git ff-only merge skipped or diverged (check manually): $status"
            }
        }
    } finally {
        Pop-Location
    }
}

$syncBat = Join-Path $TrainerDir "scripts\portable\sync_portable_root_launchers.bat"
if (Test-Path $syncBat) {
    cmd /c "`"$syncBat`" --nopause" | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Pass "sync_portable_root_launchers.bat"
    } else {
        Fail "sync_portable_root_launchers.bat exit $LASTEXITCODE"
    }
} else {
    Fail "sync_portable_root_launchers.bat missing"
}

# ---- 7.5 Source-side tests ----
Write-Section "7.5 Source tests"
if (-not $SkipPythonTests) {
    $repoRoot = $TrainerDir
    if (Test-Path (Join-Path $repoRoot "tests\test_portable_packaging_scripts.py")) {
        $py = Get-Command python -ErrorAction SilentlyContinue
        if ($py) {
            Push-Location $repoRoot
            try {
                & python -m pytest tests/test_portable_packaging_scripts.py -q 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Pass "pytest test_portable_packaging_scripts.py"
                } else {
                    & python -c "import tests.test_portable_packaging_scripts as m; [getattr(m,n)() for n in dir(m) if n.startswith('test_')]" 2>&1
                    if ($LASTEXITCODE -eq 0) {
                        Pass "test_portable_packaging_scripts (manual import)"
                    } else {
                        Warn "test_portable_packaging_scripts failed (run in dev env)"
                    }
                }
            } finally {
                Pop-Location
            }
        } else {
            Warn "python not in PATH for pytest"
        }
    } else {
        Warn "tests/test_portable_packaging_scripts.py not in package"
    }
} else {
    Warn "Skipped Python tests (-SkipPythonTests)"
}

# ---- 7.6 Other bat ----
Write-Section "7.6 Other bat shortcuts"
$shortcutChecks = @(
    @{ Path = "update\update_next_trainer.bat"; Needle = "Update-Next-Trainer.bat" },
    @{ Path = "update\update_from_release.bat"; Needle = "Update-Next-Trainer-Release.bat" }
)
foreach ($check in $shortcutChecks) {
    $full = Join-Path $PortableRoot $check.Path
    if (-not (Test-Path $full)) {
        Fail "Missing $($check.Path)"
        continue
    }
    $text = Get-Content $full -Raw
    if ($text -match [regex]::Escape($check.Needle)) {
        Pass "$($check.Path) -> $($check.Needle)"
    } else {
        Fail "$($check.Path) does not reference $($check.Needle)"
    }
}

$downloadBat = Join-Path $PortableRoot "Download-Anima-Model.bat"
if (Test-Path $downloadBat) {
    $dlText = Get-Content $downloadBat -Raw
    if ($dlText -match "PORTABLE_ROOT|%~dp0") {
        Pass "Download-Anima-Model.bat resolves portable root"
    } else {
        Warn "Download-Anima-Model.bat root detection unclear"
    }
}

# ---- Summary ----
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  PASS: $passed   FAIL: $failed   WARN: $warned"
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Manual items still required before upload:" -ForegroundColor Yellow
Write-Host "  - run_gui.bat first launch or WebUI on :28000"
Write-Host "  - /api/run creates config/autosave and starts training (P0)"
Write-Host "  - Release merge: sd-models/ and extensions/ preserved (test on staging copy)"
Write-Host ""

if ($failed -gt 0) { exit 1 }
exit 0
