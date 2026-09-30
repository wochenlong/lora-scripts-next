@echo off
chcp 65001 >nul 2>&1
title Install Flash Attention 2
cd /d "%~dp0"

echo  NOTE: training stacks moved to per-engine managed venvs
echo  (Settings -^> Training Engines). Installing flash-attn into the
echo  GUI environment no longer affects training.
echo.

echo.
echo  ============================================
echo   Flash Attention 2 Installer
echo   (source / venv users only)
echo  ============================================
echo.

:: Detect python
if exist "venv\Scripts\python.exe" (
    call "venv\Scripts\activate.bat"
    set "PY=python"
) else if exist "python\python.exe" (
    set "PY=%~dp0python\python.exe"
) else (
    echo  [ERROR] No venv or python folder found.
    echo  This script is for source installs only, not for the portable package.
    echo  Portable users: Flash Attention 2 is not supported.
    echo.
    pause
    exit /b 1
)

:: Check if already installed
%PY% -c "import triton; import flash_attn; from flash_attn.ops.triton.rotary import apply_rotary; print('Flash Attention 2 is already installed and working.')" 2>nul
if %errorlevel% equ 0 (
    echo.
    echo  Flash Attention 2 is already installed. Nothing to do.
    echo.
    pause
    exit /b 0
)

:: Install triton-windows
echo  [1/2] Installing triton-windows...
%PY% -m pip install "triton-windows<3.4" --no-warn-script-location
if errorlevel 1 (
    echo  [WARNING] triton-windows install failed.
)

:: Detect Python version for wheel
for /f %%v in ('%PY% -c "import sys; print('cp' + str(sys.version_info.major) + str(sys.version_info.minor))"') do set "PYVER=%%v"

:: Install flash-attn prebuilt wheel
echo.
echo  [2/2] Installing Flash Attention 2 prebuilt wheel (%PYVER%)...
set "WHL=flash_attn-2.7.4.post1+cu128torch2.7.0cxx11abiFALSE-%PYVER%-%PYVER%-win_amd64.whl"
set "URL=https://huggingface.co/lldacing/flash-attention-windows-wheel/resolve/main/%WHL%"
%PY% -m pip install "%URL%" --no-warn-script-location
if errorlevel 1 (
    echo.
    echo  [ERROR] Flash Attention 2 install failed.
    echo  China mirror: replace huggingface.co with hf-mirror.com and try manually.
    echo.
    pause
    exit /b 1
)

:: Verify
echo.
echo  Verifying...
%PY% -c "import triton; import flash_attn; from flash_attn.ops.triton.rotary import apply_rotary; print('Flash Attention 2 OK')"
if errorlevel 1 (
    echo  [WARNING] Verification failed. flash-attn may not work correctly.
) else (
    echo.
    echo  Done! Next time you train Anima LoRA, attn_mode will auto-detect as "flash".
)
echo.
pause
