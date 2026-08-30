@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
title Install musubi-tuner (CLI)

:: Next-Trainer/scripts/cli -> project root is ..\..
set "PROJECT_ROOT=%~dp0..\.."
cd /d "%PROJECT_ROOT%"

set "PYTHON_EXE="
if exist "%PROJECT_ROOT%\..\python_embeded\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\..\python_embeded\python.exe"
) else if exist "%PROJECT_ROOT%\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PROJECT_ROOT%\venv\Scripts\python.exe"
) else (
    where python >nul 2>&1 && set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
    echo [Error] Python not found. Install Python 3.10+ or use portable python_embeded.
    pause
    exit /b 1
)

:: uv is bootstrapped automatically by install_musubi.py if missing.

set "PYTHONUTF8=1"
set "PYTHONPATH=%PROJECT_ROOT%"

echo ========================================
echo   musubi-tuner CLI Install
echo   Project: %PROJECT_ROOT%
echo ========================================
echo.
echo This installs the musubi-tuner plugin into extensions\musubi_tuner\.
echo Requires musubi-tuner source at vendor\musubi-tuner (or --source-root),
echo NVIDIA GPU, several GB download.
echo uv will be installed automatically if it is not found.
echo Downloads prefer the HuggingFace mirror; set HF_ENDPOINT to override.
echo.

"%PYTHON_EXE%" -s "%~dp0install_musubi.py" %*
set "RC=%errorlevel%"
if not "%RC%"=="0" (
    echo.
    echo [Error] Install failed / exit %RC%
    pause
    exit /b %RC%
)

echo.
pause
exit /b 0
