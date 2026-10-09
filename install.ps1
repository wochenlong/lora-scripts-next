$Env:HF_HOME = "huggingface"

. "$PSScriptRoot\install_preflight.ps1"

function InstallFail {
    Write-Output "Install failed."
    Read-Host | Out-Null
    Exit 1
}

if (-not (Test-InstallScriptFreshness)) { InstallFail }
if (-not (Test-InstallPython)) { InstallFail }

# Ensure the pinned vendor/sd-scripts submodule (Anima training engine) is
# present. Safe to run repeatedly; skips silently when not a git checkout.
if ((Test-Path -Path ".git") -or (Test-Path -Path ".git" -PathType Leaf)) {
    Write-Output "Syncing git submodules (vendor/sd-scripts)..."
    git submodule update --init --recursive
    if ($LASTEXITCODE -ne 0) {
        Write-Output "Warning: submodule init failed; Anima training may not start. Run 'git submodule update --init --recursive' manually."
    }
}

if (!(Test-Path -Path "venv")) {
    Write-Output  "Creating venv for python..."
    python -m venv venv
}
.\venv\Scripts\activate

Write-Output "Installing deps..."

# Always `python -m pip`, never bare `pip`. If `pip` is not resolvable (a venv
# created by uv has no pip shim, or PATH is odd) PowerShell raises a command-not-
# found error without touching $LASTEXITCODE, so the checks below would still see
# the 0 left by `python -m venv` and report "Install completed" over an empty venv.
python -m pip install --upgrade "pip>=23.1"
if ($LASTEXITCODE -ne 0) { Write-Output "pip upgrade failed. Check your network and retry."; InstallFail }
python -m pip install --upgrade -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Output "requirements install failed."; InstallFail }

Write-Output "Prefetching default WD tagger wd14-convnextv2-v2 (~388 MB)..."
python scripts/prefetch_default_tagger.py --if-missing --no-mirror
if ($LASTEXITCODE -ne 0) {
    Write-Output "Warning: default tagger prefetch failed; it will download on first tag run."
}

Write-Output "Install completed"
Write-Output ""
Write-Output "Note: training dependencies (torch, sd-scripts stack) are no longer part of"
Write-Output "this environment. Install training engines from the UI: Settings -> Training Engines."
Read-Host | Out-Null
