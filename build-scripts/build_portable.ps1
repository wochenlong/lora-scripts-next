param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent),
    [string]$Version     = "2.4.0",
    [string]$PythonVer   = "3.10.11",
    [switch]$Clean,
    [switch]$Skip7z
)

$ErrorActionPreference = "Stop"
$startTime = Get-Date

$buildDir    = Join-Path $ProjectRoot "build"
$portableDir = Join-Path $buildDir "SD-Trainer-Portable"
$pythonDir   = Join-Path $portableDir "python_embeded"
$sdtDir      = Join-Path $portableDir "SD-Trainer"

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

# ==== Step 1: Python Embeddable ====

Write-Host "[1/5] Preparing Python $PythonVer Embeddable..." -ForegroundColor Cyan

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
function Install-EmbeddedTkinter {
    param(
        [string]$EmbedDir,
        [string]$ExpectedVersion = "3.10"
    )
    $fullRoot = $null
    $candidates = @(
        { & py "-$ExpectedVersion" -c "import sys; print(sys.base_prefix)" },
        { & "C:\Program Files\Python310\python.exe" -c "import sys; print(sys.base_prefix)" }
    )
    foreach ($candidate in $candidates) {
        try {
            $out = (& $candidate 2>$null | Select-Object -First 1)
            if ($out -and (Test-Path $out.Trim())) {
                $fullRoot = $out.Trim()
                break
            }
        } catch {
            continue
        }
    }
    if (-not $fullRoot) {
        Write-Host "  WARNING: No full Python $ExpectedVersion found; tkinter not bundled (folder picker disabled)" -ForegroundColor Yellow
        return
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
    $check = & (Join-Path $EmbedDir "python.exe") -c "import tkinter; print('ok')" 2>&1
    if ($LASTEXITCODE -eq 0 -and ($check -match "ok")) {
        Write-Host "  tkinter bundled from $fullRoot" -ForegroundColor Green
    } else {
        Write-Host "  WARNING: tkinter copy failed verification: $check" -ForegroundColor Yellow
    }
}

# Skip tkinter install if already present and working
$tkCheck = & $pythonExe -s -c "import tkinter; print('ok')" 2>&1
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
Write-Host "[2/5] Copying project files..." -ForegroundColor Cyan

Push-Location $ProjectRoot
Pop-Location

$copyDirs = @(
    @{ Src = "assets";  Dst = "assets" },
    @{ Src = "mikazuki"; Dst = "mikazuki" },
    @{ Src = "frontend"; Dst = "frontend" },
    @{ Src = "config";   Dst = "config" },
    @{ Src = "scripts";  Dst = "scripts" },
    @{ Src = "vendor";   Dst = "vendor" }
)

$copyFiles = @(
    "gui.py",
    "train_status_server.py",
    "requirements.txt",
    "setup_environment.py",
    "apply_lora_next_anima_defaults.py",
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
Write-Host "  Copied root files"
Write-Host "  Done" -ForegroundColor Green

# ==== Step 3: Create launcher scripts ====

Write-Host ""
Write-Host "[3/5] Creating launcher scripts..." -ForegroundColor Cyan

# run_gui_portable.bat — portable-only launcher, flat goto structure, no BOM
$batContent = "@echo off`r`n"
$batContent += "chcp 65001 >nul 2>&1`r`n"
$batContent += "title SD-Trainer`r`n"
$batContent += "`r`n"
$batContent += "set `"BASE_DIR=%~dp0`"`r`n"
$batContent += "set `"HF_HOME=%~dp0huggingface`"`r`n"
$batContent += "set `"PYTHONUTF8=1`"`r`n"
$batContent += "set `"PYTHON_EXE=%~dp0python_embeded\python.exe`"`r`n"
$batContent += "set `"LOG_FILE=%BASE_DIR%sd-trainer-log.txt`"`r`n"
$batContent += "`r`n"
$batContent += ":: Log header`r`n"
$batContent += "echo ============================================ > `"%LOG_FILE%`"`r`n"
$batContent += "echo  SD-Trainer Launch Log >> `"%LOG_FILE%`"`r`n"
$batContent += "echo  Time: %date% %time% >> `"%LOG_FILE%`"`r`n"
$batContent += "echo  Path: %BASE_DIR% >> `"%LOG_FILE%`"`r`n"
$batContent += "echo  Python: %PYTHON_EXE% >> `"%LOG_FILE%`"`r`n"
$batContent += "echo ============================================ >> `"%LOG_FILE%`"`r`n"
$batContent += "echo. >> `"%LOG_FILE%`"`r`n"
$batContent += "`r`n"
$batContent += ":: Check python exists`r`n"
$batContent += "if not exist `"%PYTHON_EXE%`" goto :no_python`r`n"
$batContent += "`r`n"
$batContent += ":: First run: install dependencies`r`n"
$batContent += "if not exist `"%BASE_DIR%python_embeded\Lib\site-packages\torch`" goto :first_run`r`n"
$batContent += "goto :launch`r`n"
$batContent += "`r`n"
$batContent += ":first_run`r`n"
$batContent += "echo.`r`n"
$batContent += "echo  [First Run] Installing dependencies, please keep network connected...`r`n"
$batContent += "echo.`r`n"
$batContent += "echo [setup] Starting setup_environment.py >> `"%LOG_FILE%`"`r`n"
$batContent += "`"%PYTHON_EXE%`" -s `"%BASE_DIR%SD-Trainer\setup_environment.py`" 2>> `"%LOG_FILE%`"`r`n"
$batContent += "if errorlevel 1 (`r`n"
$batContent += "    echo [setup] FAILED >> `"%LOG_FILE%`"`r`n"
$batContent += "    echo.`r`n"
$batContent += "    echo  Setup failed. Check log: %LOG_FILE%`r`n"
$batContent += "    goto :fail`r`n"
$batContent += ")`r`n"
$batContent += "echo [setup] OK >> `"%LOG_FILE%`"`r`n"
$batContent += "`r`n"
$batContent += ":launch`r`n"
$batContent += "cd /d `"%BASE_DIR%SD-Trainer`"`r`n"
$batContent += "if errorlevel 1 goto :no_project`r`n"
$batContent += "`r`n"
$batContent += "echo [launch] Starting gui.py >> `"%LOG_FILE%`"`r`n"
$batContent += "echo.`r`n"
$batContent += "echo  Starting SD-Trainer...`r`n"
$batContent += "echo.`r`n"
$batContent += "`r`n"
$batContent += "`"%PYTHON_EXE%`" -s gui.py --skip-prepare-environment --port 28000 2>> `"%LOG_FILE%`"`r`n"
$batContent += "set `"EXIT_CODE=%errorlevel%`"`r`n"
$batContent += "echo [launch] gui.py exited with code %EXIT_CODE% >> `"%LOG_FILE%`"`r`n"
$batContent += "`r`n"
$batContent += "if %EXIT_CODE% neq 0 (`r`n"
$batContent += "    echo.`r`n"
$batContent += "    echo  ============================================`r`n"
$batContent += "    echo   SD-Trainer exited abnormally [code: %EXIT_CODE%]`r`n"
$batContent += "    echo   Log: %LOG_FILE%`r`n"
$batContent += "    echo   Please send this log when reporting bugs.`r`n"
$batContent += "    echo  ============================================`r`n"
$batContent += "    echo.`r`n"
$batContent += ")`r`n"
$batContent += "pause`r`n"
$batContent += "exit /b %EXIT_CODE%`r`n"
$batContent += "`r`n"
$batContent += ":no_python`r`n"
$batContent += "echo.`r`n"
$batContent += "echo  [ERROR] python_embeded\python.exe not found!`r`n"
$batContent += "echo  Please make sure the package is fully extracted.`r`n"
$batContent += "echo.`r`n"
$batContent += "echo [ERROR] python_embeded\python.exe not found >> `"%LOG_FILE%`"`r`n"
$batContent += "goto :fail`r`n"
$batContent += "`r`n"
$batContent += ":no_project`r`n"
$batContent += "echo.`r`n"
$batContent += "echo  [ERROR] SD-Trainer folder not found!`r`n"
$batContent += "echo.`r`n"
$batContent += "echo [ERROR] Cannot cd to %BASE_DIR%SD-Trainer >> `"%LOG_FILE%`"`r`n"
$batContent += "goto :fail`r`n"
$batContent += "`r`n"
$batContent += ":fail`r`n"
$batContent += "echo.`r`n"
$batContent += "echo  ============================================`r`n"
$batContent += "echo   SD-Trainer failed to start.`r`n"
$batContent += "echo   Log: %LOG_FILE%`r`n"
$batContent += "echo   Please send this log when reporting bugs.`r`n"
$batContent += "echo  ============================================`r`n"
$batContent += "echo.`r`n"
$batContent += "pause`r`n"
$batContent += "exit /b 1`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $portableDir "run_gui_portable.bat"),
    $batContent,
    (New-Object System.Text.UTF8Encoding $false)
)
Write-Host "  Created run_gui_portable.bat"

# Keep run_gui.bat as the beginner-friendly stable entrypoint, but make it a
# tiny wrapper so portable and source launch behavior never mix.
$runGuiWrapper = "@echo off`r`n"
$runGuiWrapper += "chcp 65001 >nul 2>&1`r`n"
$runGuiWrapper += "cd /d `"%~dp0`"`r`n"
$runGuiWrapper += "if not exist `"run_gui_portable.bat`" (`r`n"
$runGuiWrapper += "    echo [ERROR] run_gui_portable.bat not found. Please re-extract the package.`r`n"
$runGuiWrapper += "    pause`r`n"
$runGuiWrapper += "    exit /b 1`r`n"
$runGuiWrapper += ")`r`n"
$runGuiWrapper += "call `"%~dp0run_gui_portable.bat`" %*`r`n"
$runGuiWrapper += "exit /b %errorlevel%`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $portableDir "run_gui.bat"),
    $runGuiWrapper,
    (New-Object System.Text.UTF8Encoding $false)
)
Write-Host "  Created run_gui.bat wrapper"

# update/
$updateDir = Join-Path $portableDir "update"
New-Item -ItemType Directory -Path $updateDir -Force | Out-Null

$updateBat = "@echo off`r`nchcp 65001 >nul 2>&1`r`ncd /d `"%~dp0..\SD-Trainer`"`r`n"
$updateBat += "echo Updating SD-Trainer...`r`ngit pull`r`necho Done.`r`npause`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $updateDir "update_sd_trainer.bat"),
    $updateBat,
    (New-Object System.Text.UTF8Encoding $false)
)

$updateDepsBat = "@echo off`r`nchcp 65001 >nul 2>&1`r`ncd /d `"%~dp0..`"`r`n"
$updateDepsBat += "echo Updating Python dependencies...`r`n"
$updateDepsBat += "`"python_embeded\python.exe`" -s -m pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu128`r`n"
$updateDepsBat += "`"python_embeded\python.exe`" -s -m pip install --upgrade -r `"SD-Trainer\requirements.txt`"`r`n"
$updateDepsBat += "`"python_embeded\python.exe`" -s -m pip install `"triton-windows<3.4`" --no-warn-script-location`r`n"
$updateDepsBat += "`"python_embeded\python.exe`" -s -m pip install https://huggingface.co/lldacing/flash-attention-windows-wheel/resolve/main/flash_attn-2.7.4.post1+cu128torch2.7.0cxx11abiFALSE-cp310-cp310-win_amd64.whl --no-warn-script-location`r`n"
$updateDepsBat += "`"python_embeded\python.exe`" -s -c `"import triton; import flash_attn; from flash_attn.ops.triton.rotary import apply_rotary; print('Flash Attention 2 OK')`"`r`n"
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

# install_flash_attn.bat — one-click Flash Attention 2 installer for portable users
$flashAttnBat = "@echo off`r`nchcp 65001 >nul 2>&1`r`ntitle Install Flash Attention 2`r`ncd /d `"%~dp0`"`r`n"
$flashAttnBat += "set `"PYTHON_EXE=%~dp0python_embeded\python.exe`"`r`n"
$flashAttnBat += "if not exist `"%PYTHON_EXE%`" (`r`n"
$flashAttnBat += "    echo [ERROR] python_embeded\python.exe not found!`r`n"
$flashAttnBat += "    pause`r`n    exit /b 1`r`n)`r`n"
$flashAttnBat += "echo.`r`necho  Installing Flash Attention 2 for Torch 2.7.0 + CUDA 12.8 ...`r`necho.`r`n"
$flashAttnBat += "`"%PYTHON_EXE%`" -s -m pip install `"triton-windows<3.4`" --no-warn-script-location`r`n"
$flashAttnBat += "if errorlevel 1 (`r`n    echo [ERROR] triton-windows installation failed.`r`n    pause`r`n    exit /b 1`r`n)`r`n"
$flashAttnBat += "`"%PYTHON_EXE%`" -s -m pip install https://huggingface.co/lldacing/flash-attention-windows-wheel/resolve/main/flash_attn-2.7.4.post1+cu128torch2.7.0cxx11abiFALSE-cp310-cp310-win_amd64.whl --no-warn-script-location`r`n"
$flashAttnBat += "if errorlevel 1 (`r`n    echo [ERROR] flash-attn wheel installation failed.`r`n    pause`r`n    exit /b 1`r`n)`r`n"
$flashAttnBat += "echo.`r`necho  Verifying...`r`n"
$flashAttnBat += "`"%PYTHON_EXE%`" -s -c `"import triton; import flash_attn; from flash_attn.ops.triton.rotary import apply_rotary; print('  Flash Attention 2 OK')`"`r`n"
$flashAttnBat += "if errorlevel 1 (`r`n    echo [ERROR] Flash Attention 2 self-check failed. Training will fall back to xformers or PyTorch SDPA.`r`n    `"%PYTHON_EXE%`" -s -m pip uninstall flash-attn flash_attn triton-windows triton -y >nul 2>&1`r`n    pause`r`n    exit /b 1`r`n)`r`n"
$flashAttnBat += "echo.`r`necho  Done! Anima training can now use attn_mode = flash.`r`necho.`r`npause`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $portableDir "install_flash_attn.bat"),
    $flashAttnBat,
    (New-Object System.Text.UTF8Encoding $false)
)
Write-Host "  Created install_flash_attn.bat"

# Root-level utility bat files
$templateDir = Join-Path $PSScriptRoot "templates"
foreach ($bat in @("Update-SD-Trainer.bat", "Download-Anima-Model.bat")) {
    $src = Join-Path $templateDir $bat
    if (Test-Path $src) {
        Copy-Item $src -Destination (Join-Path $portableDir $bat)
        Write-Host "  Created $bat"
    }
}

# ==== Step 4: Empty dirs + README ====

Write-Host ""
Write-Host "[4/5] Creating user directories and README..." -ForegroundColor Cyan

foreach ($d in @("sd-models", "output", "logs", "huggingface")) {
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
$readme += "Directories:`r`n"
$readme += "  run_gui.bat      - Stable entrypoint for portable users`r`n"
$readme += "  run_gui_portable.bat - Portable-only launcher used by run_gui.bat`r`n"
$readme += "  python_embeded/  - Python runtime`r`n"
$readme += "  SD-Trainer/      - Project files`r`n"
$readme += "  sd-models/       - Put your models here`r`n"
$readme += "  output/          - Training output`r`n"
$readme += "  logs/            - Logs`r`n`r`n"
$readme += "Update:`r`n"
$readme += "  update\update_sd_trainer.bat       - Update project code`r`n"
$readme += "  update\update_dependencies.bat     - Update Python packages`r`n`r`n"
$readme += "Requirements:`r`n"
$readme += "  - Windows 10/11 64-bit`r`n"
$readme += "  - NVIDIA GPU (RTX 20-series or newer)`r`n"
$readme += "  - ~7 GB disk + ~3 GB download on first run`r`n`r`n"
$readme += "xformers (recommended):`r`n"
$readme += "  If xformers is missing, double-click install_xformers.bat to install.`r`n"
$readme += "  xformers provides faster attention than PyTorch SDPA on most GPUs.`r`n`r`n"
$readme += "Flash Attention 2:`r`n"
$readme += "  First launch installs the pinned flash-attn + triton-windows stack when available.`r`n"
$readme += "  If the self-check fails, startup removes the broken stack and falls back to xformers / PyTorch SDPA.`r`n"
$readme += "  You can rerun install_flash_attn.bat after updating GPU drivers or dependencies.`r`n"
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
    Write-Host "[5/5] Creating 7z archive..." -ForegroundColor Cyan

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
    Write-Host "[5/5] Skipping 7z compression" -ForegroundColor Yellow
}

# ==== Done ====

$duration = (Get-Date) - $startTime
Write-Host ""
Write-Host "  Build complete!  ($portableDir)" -ForegroundColor Green
Write-Host "  Elapsed: $($duration.ToString('mm\:ss'))"
Write-Host ""
