param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent),
    [string]$Version     = "2.5.0",
    [string]$PythonVer   = "3.10.11",
    [string]$TkinterSourceRoot = "",
    [switch]$Clean,
    [switch]$Skip7z
)

$ErrorActionPreference = "Stop"
$startTime = Get-Date

$buildDir    = Join-Path $ProjectRoot "build"
$portableDir = Join-Path $buildDir "SD-Trainer-Portable"
$pythonDir   = Join-Path $portableDir "python_embeded"
$sdtDir      = Join-Path $portableDir "SD-Trainer"
$tempGitCloneDir = Join-Path $buildDir "_portable_git_metadata"

$7zExe = "C:\Program Files\7-Zip\7z.exe"
if (-not (Test-Path $7zExe)) {
    $found = Get-Command 7z -ErrorAction SilentlyContinue
    if ($found) { $7zExe = $found.Source } else { $7zExe = $null }
}

Write-Host ""
Write-Host "  SD-Trainer Portable Package Builder  v$Version" -ForegroundColor Cyan
Write-Host ""

# ---- Clean ----

if ($Clean -and (Test-Path $portableDir)) {
    Write-Host "[Clean] Removing old build..." -ForegroundColor Yellow
    Remove-Item $portableDir -Recurse -Force
}
New-Item -ItemType Directory -Path $portableDir -Force | Out-Null

function Invoke-GitChecked {
    param(
        [string[]]$Arguments,
        [string]$WorkingDirectory = $ProjectRoot,
        [string]$ErrorMessage = "git command failed"
    )
    & git -C $WorkingDirectory @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw $ErrorMessage
    }
}

function Initialize-DatasetTagEditor {
    Write-Host "  Checking dataset-tag-editor submodule..."
    $tagEditorLaunch = Join-Path $ProjectRoot "mikazuki\dataset-tag-editor\scripts\launch.py"
    if (-not (Test-Path $tagEditorLaunch)) {
        Write-Host "  Initializing dataset-tag-editor submodule..."
        Invoke-GitChecked `
            -Arguments @("submodule", "update", "--init", "--recursive", "--depth=1", "--", "mikazuki/dataset-tag-editor") `
            -ErrorMessage "dataset-tag-editor submodule init failed"
    }
    if (-not (Test-Path $tagEditorLaunch)) {
        throw "dataset-tag-editor\scripts\launch.py missing after submodule init"
    }
}

function Clone-SDTrainerGitMetadata {
    param([string]$Destination)
    Write-Host "  Embedding shallow .git metadata for Update-SD-Trainer.bat..."
    if (Test-Path $tempGitCloneDir) {
        Remove-Item $tempGitCloneDir -Recurse -Force
    }
    $branch = (& git -C $ProjectRoot branch --show-current 2>$null | Select-Object -First 1)
    if (-not $branch) { $branch = "main" }
    $remote = (& git -C $ProjectRoot remote get-url origin 2>$null | Select-Object -First 1)
    if (-not $remote) { $remote = "https://github.com/wochenlong/lora-scripts-next.git" }

    & git clone --depth=1 --single-branch --branch $branch $remote $tempGitCloneDir
    if ($LASTEXITCODE -ne 0) {
        throw "failed to clone shallow git metadata from $remote"
    }
    $dstGit = Join-Path $Destination "SD-Trainer\.git"
    if (Test-Path $dstGit) {
        Remove-Item $dstGit -Recurse -Force
    }
    Copy-Item (Join-Path $tempGitCloneDir ".git") $dstGit -Recurse -Force
    Remove-Item $tempGitCloneDir -Recurse -Force

    if (-not (Test-Path (Join-Path $dstGit "HEAD"))) {
        throw "embedded SD-Trainer\.git is missing HEAD"
    }
}

# ==== Step 1: Python Embeddable ====

Write-Host "[1/6] Preparing Python $PythonVer Embeddable..." -ForegroundColor Cyan

$pythonZipName = "python-$PythonVer-embed-amd64.zip"
$pythonUrl     = "https://www.python.org/ftp/python/$PythonVer/$pythonZipName"
$pythonZipPath = Join-Path $env:TEMP $pythonZipName
$pythonExe     = Join-Path $pythonDir "python.exe"

if (Test-Path $pythonExe) {
    Write-Host "  Python already exists, skip" -ForegroundColor Green
} else {
    New-Item -ItemType Directory -Path $pythonDir -Force | Out-Null
    if (-not (Test-Path $pythonZipPath)) {
        Write-Host "  Downloading $pythonZipName ..."
        Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonZipPath -UseBasicParsing
    }
    Write-Host "  Extracting..."
    Expand-Archive -Path $pythonZipPath -DestinationPath $pythonDir -Force
    Write-Host "  Done" -ForegroundColor Green
}

# python310._pth (include Lib/ so bundled tkinter is importable)
$pthLines = @(
    "../SD-Trainer",
    "../SD-Trainer/vendor/sd-scripts",
    "python310.zip",
    "Lib",
    "Lib/site-packages",
    ".",
    "import site"
)
$pthFile = Join-Path $pythonDir "python310._pth"
[System.IO.File]::WriteAllLines($pthFile, $pthLines)
Write-Host "  Created python310._pth"

# Lib/site-packages
$sitePackages = Join-Path $pythonDir "Lib\site-packages"
New-Item -ItemType Directory -Path $sitePackages -Force | Out-Null

# tkinter for GUI folder/file picker (embeddable Python omits it by default)
function Test-TkinterSourceRoot {
    param([string]$Root)
    if (-not $Root -or -not (Test-Path $Root)) { return $false }
    $libTk = Join-Path $Root "Lib\tkinter"
    if (-not (Test-Path $libTk)) { $libTk = Join-Path $Root "lib\tkinter" }
    $tcl = Join-Path $Root "tcl"
    $pyd = Join-Path $Root "DLLs\_tkinter.pyd"
    return (Test-Path $libTk) -and (Test-Path $tcl) -and (Test-Path $pyd)
}

function Get-TkinterSourceCandidates {
    param([string]$ExpectedVersion = "3.10")
    $roots = [System.Collections.Generic.List[string]]::new()

    if ($TkinterSourceRoot -and (Test-Path $TkinterSourceRoot)) {
        $roots.Add($TkinterSourceRoot.TrimEnd('\'))
    }
    if ($env:SD_TRAINER_TKINTER_SOURCE -and (Test-Path $env:SD_TRAINER_TKINTER_SOURCE)) {
        $roots.Add($env:SD_TRAINER_TKINTER_SOURCE.TrimEnd('\'))
    }

    # Official CPython first — avoid conda/mambaforge (often missing tcl/)
    foreach ($fixed in @(
        "C:\Program Files\Python310",
        "C:\Program Files (x86)\Python310"
    )) {
        if (Test-Path $fixed) { $roots.Add($fixed) }
    }

    foreach ($exe in @(
        "C:\Program Files\Python310\python.exe",
        "C:\Program Files (x86)\Python310\python.exe"
    )) {
        if (-not (Test-Path $exe)) { continue }
        try {
            $out = (& $exe -c "import sys; print(sys.base_prefix)" 2>$null | Select-Object -First 1)
            if ($out) { $roots.Add($out.Trim()) }
        } catch { }
    }

    try {
        $pyList = & py -0p 2>&1
        foreach ($line in $pyList) {
            if ($line -notmatch "3\.10") { continue }
            if ($line -notmatch "([A-Za-z]:\\[^\s]+\.exe)\s*$") { continue }
            $exe = $Matches[1].Trim()
            if ($exe -match "mambaforge|miniconda|anaconda|conda", "IgnoreCase") { continue }
            $out = (& $exe -c "import sys; print(sys.base_prefix)" 2>$null | Select-Object -First 1)
            if ($out) { $roots.Add($out.Trim()) }
        }
    } catch { }

    return $roots | Select-Object -Unique
}

function Install-EmbeddedTkinter {
    param(
        [string]$EmbedDir,
        [string]$ExpectedVersion = "3.10"
    )
    $fullRoot = $null
    foreach ($candidate in (Get-TkinterSourceCandidates -ExpectedVersion $ExpectedVersion)) {
        if (Test-TkinterSourceRoot $candidate) {
            $fullRoot = $candidate
            break
        }
    }
    if (-not $fullRoot) {
        Write-Host "  ERROR: No CPython $ExpectedVersion with tcl/ + tkinter found." -ForegroundColor Red
        Write-Host "         Install https://www.python.org/downloads/release/python-31011/ (Windows x64)," -ForegroundColor Red
        Write-Host "         or pass -TkinterSourceRoot 'C:\Program Files\Python310'," -ForegroundColor Red
        Write-Host "         or set env SD_TRAINER_TKINTER_SOURCE to a full Python root." -ForegroundColor Red
        Write-Host "         Do NOT use conda/mambaforge — folder picker will break." -ForegroundColor Red
        throw "tkinter source not found"
    }
    $libTk = Join-Path $fullRoot "Lib\tkinter"
    if (-not (Test-Path $libTk)) {
        $libTk = Join-Path $fullRoot "lib\tkinter"
    }
    $dllDir = Join-Path $fullRoot "DLLs"
    if (-not (Test-Path $libTk) -or -not (Test-Path $dllDir)) {
        Write-Host "  WARNING: tkinter/tcl files missing under $fullRoot" -ForegroundColor Yellow
        return
    }
    $embedLib = Join-Path $EmbedDir "Lib"
    New-Item -ItemType Directory -Path $embedLib -Force | Out-Null
    Copy-Item $libTk (Join-Path $embedLib "tkinter") -Recurse -Force
    $tclSrc = Join-Path $fullRoot "tcl"
    if (Test-Path $tclSrc) {
        Copy-Item $tclSrc (Join-Path $EmbedDir "tcl") -Recurse -Force
    } else {
        Write-Host "  WARNING: tcl directory not found at $tclSrc (tkinter may still work)" -ForegroundColor Yellow
    }
    foreach ($name in @("_tkinter.pyd", "tcl86t.dll", "tk86t.dll")) {
        $src = Join-Path $dllDir $name
        if (Test-Path $src) {
            Copy-Item $src (Join-Path $EmbedDir $name) -Force
        }
    }
    $oldEAP2 = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $check = & (Join-Path $EmbedDir "python.exe") -c "import tkinter; print('ok')" 2>&1
    $ErrorActionPreference = $oldEAP2
    if ($LASTEXITCODE -eq 0 -and ($check -match "ok")) {
        Write-Host "  tkinter bundled from $fullRoot" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: tkinter verification failed after copy from $fullRoot" -ForegroundColor Red
        Write-Host "         $check" -ForegroundColor Red
        throw "tkinter bundle verification failed"
    }
}

# Skip tkinter install if already present and working
$oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
$tkCheck = & $pythonExe -s -c "import tkinter; print('ok')" 2>&1
$ErrorActionPreference = $oldEAP
if ($LASTEXITCODE -eq 0 -and ($tkCheck -match "ok")) {
    Write-Host "  tkinter already bundled, skip" -ForegroundColor Green
} else {
    Install-EmbeddedTkinter -EmbedDir $pythonDir -ExpectedVersion "3.10"
}

# get-pip.py
$getPipPath = Join-Path $pythonDir "get-pip.py"
if (-not (Test-Path $getPipPath)) {
    Write-Host "  Downloading get-pip.py..."
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPipPath -UseBasicParsing
}

# ==== Step 2: Copy project files ====

Write-Host ""
Write-Host "[2/6] Copying project files..." -ForegroundColor Cyan

Initialize-DatasetTagEditor

$copyDirs = @(
    @{ Src = "assets";  Dst = "assets" },
    @{ Src = "mikazuki"; Dst = "mikazuki" },
    @{ Src = "frontend"; Dst = "frontend" },
    @{ Src = "config";   Dst = "config" },
    @{ Src = "scripts";  Dst = "scripts" },
    @{ Src = "vendor";   Dst = "vendor" },
    @{ Src = "train_monitor"; Dst = "train_monitor" }
)

$copyFiles = @(
    "gui.py",
    "requirements.txt",
    "setup_environment.py",
    "VERSION",
    "LICENSE",
    "NOTICE.md",
    "CHANGELOG.md",
    "README.md",
    "README-zh.md"
)

$excludeDirs = @(
    ".git", "__pycache__", ".vscode", ".idea",
    "node_modules", ".sisyphus", ".playwright-mcp", ".tmp",
    "anima_lora", "drafts"
)

foreach ($dir in $copyDirs) {
    $src = Join-Path $ProjectRoot $dir.Src
    $dst = Join-Path $sdtDir $dir.Dst
    if (Test-Path $src) {
        $xdArgs = @()
        foreach ($xd in $excludeDirs) { $xdArgs += "/XD"; $xdArgs += $xd }
        $null = robocopy $src $dst /E /NFL /NDL /NJH /NJS /NC /NS $xdArgs
        Write-Host "  Copied $($dir.Src)/"
    } else {
        Write-Host "  [skip] $($dir.Src)/ not found" -ForegroundColor Yellow
    }
}

# robocopy /XD can miss nested git metadata or local test directories when
# names are matched relative to the copied subtree, so run a deterministic
# cleanup pass before archiving.
foreach ($exclude in $excludeDirs) {
    Get-ChildItem -Path $sdtDir -Force -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $exclude } |
        Sort-Object FullName -Descending |
        ForEach-Object {
            Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
}

New-Item -ItemType Directory -Path $sdtDir -Force | Out-Null
foreach ($file in $copyFiles) {
    $src = Join-Path $ProjectRoot $file
    if (Test-Path $src) {
        Copy-Item $src -Destination (Join-Path $sdtDir $file)
    }
}
Clone-SDTrainerGitMetadata -Destination $portableDir
Write-Host "  Copied root files"
Write-Host "  Done" -ForegroundColor Green

# ==== Step 3: Bundle default WD tagger (offline batch tagging) ====

Write-Host ""
Write-Host "[3/6] Bundling default WD tagger (wd14-convnextv2-v2, ~388 MB)..." -ForegroundColor Cyan

$hfHome = Join-Path $portableDir "huggingface"
$taggerModelsDir = Join-Path $portableDir "tagger-models"
New-Item -ItemType Directory -Path $hfHome -Force | Out-Null
New-Item -ItemType Directory -Path $taggerModelsDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $portableDir "tagger-models\wd14") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $portableDir "tagger-models\vlm") -Force | Out-Null
$prefetchScript = Join-Path $sdtDir "scripts\prefetch_default_tagger.py"

if (-not (Test-Path $prefetchScript)) {
    Write-Host "  WARNING: prefetch script missing, skip" -ForegroundColor Yellow
} elseif (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Test-Path $pythonExe)) {
    Write-Host "  WARNING: no Python for tagger prefetch; tagger will download on first tag run" -ForegroundColor Yellow
} else {
    $env:HF_HOME = $hfHome
    $env:MIKAZUKI_TAGGER_MODELS_DIR = $taggerModelsDir
    # pip writes progress to stderr; with $ErrorActionPreference Stop that aborts the build.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $prefetchExit = 1
    if (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m pip install -q huggingface_hub 2>&1 | Out-Null
        & python $prefetchScript --hf-home $hfHome --tagger-models-dir $taggerModelsDir --if-missing
        $prefetchExit = $LASTEXITCODE
    } elseif (Test-Path $pythonExe) {
        if (Test-Path $getPipPath) {
            Write-Host "  Bootstrapping pip in embedded Python..."
            & $pythonExe $getPipPath --no-warn-script-location 2>&1 | Out-Null
        }
        & $pythonExe -s -m pip install -q huggingface_hub 2>&1 | Out-Null
        & $pythonExe -s $prefetchScript --hf-home $hfHome --tagger-models-dir $taggerModelsDir --if-missing
        $prefetchExit = $LASTEXITCODE
    }
    $ErrorActionPreference = $prevEap
    if ($prefetchExit -ne 0) {
        Write-Host "  WARNING: tagger prefetch failed; 7z may ship without offline tagger" -ForegroundColor Yellow
    } else {
        Write-Host "  Cached under huggingface/hub/ and tagger-models/" -ForegroundColor Green
    }
}

# ==== Step 4: Create launcher scripts ====

Write-Host ""
Write-Host "[4/6] Creating launcher scripts..." -ForegroundColor Cyan

# run_gui_portable.bat — root shim (logic lives in SD-Trainer/scripts/portable/, updates with project)
$shimSrc = Join-Path $ProjectRoot "scripts\portable\run_gui_portable_shim.bat"
if (Test-Path $shimSrc) {
    Copy-Item $shimSrc -Destination (Join-Path $portableDir "run_gui_portable.bat") -Force
    Write-Host "  Created run_gui_portable.bat (shim -> scripts/portable/launch_portable.bat)"
} else {
    Write-Host "  WARNING: scripts/portable/run_gui_portable_shim.bat not found" -ForegroundColor Yellow
}

# Use the repo's run_gui.bat as the portable entrypoint (it auto-detects
# python_embeded and dispatches to run_gui_portable.bat).
$repoRunGui = Join-Path $ProjectRoot "run_gui.bat"
if (Test-Path $repoRunGui) {
    Copy-Item $repoRunGui -Destination (Join-Path $portableDir "run_gui.bat") -Force
    Write-Host "  Copied run_gui.bat (unified launcher from repo)"
} else {
    Write-Host "  WARNING: run_gui.bat not found in repo root" -ForegroundColor Yellow
}

# update/
$updateDir = Join-Path $portableDir "update"
New-Item -ItemType Directory -Path $updateDir -Force | Out-Null

$updateBat = "@echo off`r`nchcp 65001 >nul 2>&1`r`n"
$updateBat += "call `"%~dp0..\Update-SD-Trainer.bat`" %*`r`n"
$updateBat += "exit /b %errorlevel%`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $updateDir "update_sd_trainer.bat"),
    $updateBat,
    (New-Object System.Text.UTF8Encoding $false)
)

$updateDepsBat = "@echo off`r`nchcp 65001 >nul 2>&1`r`ncd /d `"%~dp0..`"`r`n"
$updateDepsBat += "echo Updating Python dependencies...`r`n"
$updateDepsBat += "`"python_embeded\python.exe`" -s -m pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu128`r`n"
$updateDepsBat += "`"python_embeded\python.exe`" -s -m pip install --upgrade -r `"SD-Trainer\requirements.txt`"`r`n"
$updateDepsBat += "echo Done.`r`npause`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $updateDir "update_dependencies.bat"),
    $updateDepsBat,
    (New-Object System.Text.UTF8Encoding $false)
)
Write-Host "  Created update/ scripts"

# install_xformers.bat — one-click xformers installer for portable users
$xformersBat = "@echo off`r`nchcp 65001 >nul 2>&1`r`ntitle Install xformers`r`ncd /d `"%~dp0`"`r`n"
$xformersBat += "set `"PYTHON_EXE=%~dp0python_embeded\python.exe`"`r`n"
$xformersBat += "if not exist `"%PYTHON_EXE%`" (`r`n"
$xformersBat += "    echo [ERROR] python_embeded\python.exe not found!`r`n"
$xformersBat += "    pause`r`n    exit /b 1`r`n)`r`n"
$xformersBat += "echo.`r`necho  Installing xformers 0.0.30 for Torch 2.7.0 + CUDA 12.8 ...`r`necho.`r`n"
$xformersBat += "`"%PYTHON_EXE%`" -s -m pip install xformers==0.0.30 --index-url https://download.pytorch.org/whl/cu128 --no-warn-script-location`r`n"
$xformersBat += "if errorlevel 1 (`r`n    echo [ERROR] xformers installation failed.`r`n    pause`r`n    exit /b 1`r`n)`r`n"
$xformersBat += "echo.`r`necho  Verifying...`r`n"
$xformersBat += "`"%PYTHON_EXE%`" -s -c `"import xformers; print(f'  xformers {xformers.__version__} OK')`"`r`n"
$xformersBat += "echo.`r`necho  Done! You can now use attn_mode = xformers.`r`necho.`r`npause`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $portableDir "install_xformers.bat"),
    $xformersBat,
    (New-Object System.Text.UTF8Encoding $false)
)
Write-Host "  Created install_xformers.bat"

# Root-level utility bat files
$templateDir = Join-Path $PSScriptRoot "templates"
foreach ($bat in @("Update-SD-Trainer.bat", "Download-Anima-Model.bat")) {
    $src = Join-Path $ProjectRoot $bat
    if (-not (Test-Path $src)) {
        $src = Join-Path $templateDir $bat
    }
    if (Test-Path $src) {
        Copy-Item $src -Destination (Join-Path $portableDir $bat)
        Write-Host "  Created $bat"
    }
}

# ==== Step 5: Empty dirs + README ====

Write-Host ""
Write-Host "[5/6] Creating user directories and README..." -ForegroundColor Cyan

foreach ($d in @("sd-models", "output", "logs", "huggingface", "tagger-models", "tagger-models\wd14", "tagger-models\vlm")) {
    $p = Join-Path $portableDir $d
    New-Item -ItemType Directory -Path $p -Force | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $p ".gitkeep"), "")
}

$readme = "SD-Trainer Portable`r`n"
$readme += "===================`r`n`r`n"
$readme += "Quick Start:`r`n"
$readme += "  1. Double-click run_gui.bat`r`n"
$readme += "  2. First launch requires internet (downloads ~3 GB of PyTorch)`r`n"
$readme += "  3. Open http://127.0.0.1:28000 in browser`r`n`r`n"
$readme += "Tagging:`r`n"
$readme += "  Default WD tagger (wd14-convnextv2-v2) is bundled under tagger-models/wd14/`r`n"
$readme += "  (~400 MB). Put extra WD/CL tag models in tagger-models/wd14/<model-key>/`r`n"
$readme += "  Future VLM caption models can be placed under tagger-models/vlm/<model-key>/`r`n"
$readme += "  with the files required by that model, such as model.onnx and selected_tags.csv.`r`n`r`n"
$readme += "Directories:`r`n"
$readme += "  run_gui.bat      - Stable entrypoint for portable users`r`n"
$readme += "  run_gui_portable.bat - Legacy shim (logic in SD-Trainer/scripts/portable/)`r`n"
$readme += "  python_embeded/  - Python runtime`r`n"
$readme += "  SD-Trainer/      - Project files`r`n"
$readme += "  sd-models/       - Put your models here`r`n"
$readme += "  output/          - Training output`r`n"
$readme += "  logs/            - Logs`r`n`r`n"
$readme += "  tagger-models/   - Local tagger models`r`n`r`n"
$readme += "Update:`r`n"
$readme += "  update\update_sd_trainer.bat       - Shortcut to Update-SD-Trainer.bat`r`n"
$readme += "  update\update_dependencies.bat     - Update Python packages`r`n`r`n"
$readme += "Requirements:`r`n"
$readme += "  - Windows 10/11 64-bit`r`n"
$readme += "  - NVIDIA GPU (RTX 20-series or newer)`r`n"
$readme += "  - ~7 GB disk + ~3 GB download on first run`r`n`r`n"
$readme += "xformers (recommended):`r`n"
$readme += "  If xformers is missing, double-click install_xformers.bat to install.`r`n"
$readme += "  xformers provides faster attention than PyTorch SDPA on most GPUs.`r`n`r`n"
$readme += "Flash Attention 2:`r`n"
$readme += "  This portable package does NOT use flash-attn (uses xformers / PyTorch SDPA).`r`n"
$readme += "  Do not pip install flash-attn into python_embeded. See README in SD-Trainer/.`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $portableDir "README.txt"),
    $readme,
    (New-Object System.Text.UTF8Encoding $true)
)
Write-Host "  Created README.txt"
Write-Host "  Done" -ForegroundColor Green

# ==== Step 5: 7z archive ====

if (-not $Skip7z) {
    Write-Host ""
    Write-Host "[6/6] Creating 7z archive..." -ForegroundColor Cyan

    if (-not $7zExe) {
        Write-Host "  [!] 7-Zip not found, skipping compression." -ForegroundColor Yellow
    } else {
        $archiveName = "SD-Trainer-v${Version}.7z"
        $archivePath = Join-Path $buildDir $archiveName
        if (Test-Path $archivePath) { Remove-Item $archivePath -Force }

        Write-Host "  Compressing..."
        & $7zExe a -t7z -mx=9 -m0=LZMA2:d=64m -mmt=on $archivePath "$portableDir\*" | Out-Null

        $sizeBytes = (Get-Item $archivePath).Length
        $sizeMB = [math]::Round($sizeBytes / 1MB, 1)
        Write-Host "  Output: $archiveName  ($sizeMB MB)" -ForegroundColor Green
    }
} else {
    Write-Host ""
    Write-Host "[6/6] Skipping 7z compression" -ForegroundColor Yellow
}

# ==== Done ====

$duration = (Get-Date) - $startTime
Write-Host ""
Write-Host "  Build complete!  ($portableDir)" -ForegroundColor Green
Write-Host "  Elapsed: $($duration.ToString('mm\:ss'))"
Write-Host ""
