@echo off
chcp 65001 >nul 2>&1
title Next-Trainer

:: Portable launcher logic (lives inside Next-Trainer/, updates with git pull / new 7z copy)
:: Stable paths relative to PORTABLE_ROOT (parent of Next-Trainer\):
::   python_embeded\python.exe
::   Next-Trainer\gui.py
::   Next-Trainer\setup_environment.py

set "PORTABLE_ROOT=%~dp0..\..\..\"
set "BASE_DIR=%PORTABLE_ROOT%"
set "HF_HOME=%PORTABLE_ROOT%huggingface"
set "MIKAZUKI_TAGGER_MODELS_DIR=%PORTABLE_ROOT%tagger-models"
set "MIKAZUKI_TOKENIZER_CACHE_DIR=%PORTABLE_ROOT%tokenizer-cache"
:: Bundled tagger-models/tokenizer-cache first; do not force ModelScope (WD taggers are HF-only).
if not defined MIKAZUKI_HUB_BACKEND set "MIKAZUKI_HUB_BACKEND=auto"
set "PYTHONUTF8=1"
:: Release-channel marketplace wiring (written by build_portable -MarketplaceCatalogOnly)
if exist "%PORTABLE_ROOT%marketplace-env.bat" call "%PORTABLE_ROOT%marketplace-env.bat"
set "PYTHON_EXE=%PORTABLE_ROOT%python_embeded\python.exe"
set "LOG_FILE=%PORTABLE_ROOT%next-trainer-log.txt"

echo ============================================ > "%LOG_FILE%"
echo  Next-Trainer Launch Log >> "%LOG_FILE%"
echo  Time: %date% %time% >> "%LOG_FILE%"
echo  Path: %BASE_DIR% >> "%LOG_FILE%"
echo  Python: %PYTHON_EXE% >> "%LOG_FILE%"
echo ============================================ >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

if not exist "%PYTHON_EXE%" goto :no_python

if not exist "%PORTABLE_ROOT%python_embeded\Lib\site-packages\torch" goto :first_run
echo [setup] Verifying embedded dependencies >> "%LOG_FILE%"
"%PYTHON_EXE%" -s -c "import torch, torchvision, accelerate, diffusers, gradio" >nul 2>> "%LOG_FILE%"
if errorlevel 1 goto :repair_run
goto :launch

:first_run
echo.
echo  [First Run] Installing dependencies, please keep network connected...
echo.
goto :run_setup

:repair_run
echo.
echo  [Repair] Incomplete dependencies detected, running setup...
echo.
echo [setup] Dependency check failed, running setup_environment.py >> "%LOG_FILE%"

:run_setup
echo [setup] Starting setup_environment.py >> "%LOG_FILE%"
"%PYTHON_EXE%" -s "%PORTABLE_ROOT%Next-Trainer\setup_environment.py" 2>> "%LOG_FILE%"
if errorlevel 1 (
    echo [setup] FAILED >> "%LOG_FILE%"
    echo.
    echo  Setup failed. Check log: %LOG_FILE%
    goto :fail
)
echo [setup] OK >> "%LOG_FILE%"

:launch
cd /d "%PORTABLE_ROOT%Next-Trainer"
if errorlevel 1 goto :no_project

if exist "scripts\portable\link_portable_data_dirs.py" (
    echo [portable] Ensuring Next-Trainer data dirs for file picker >> "%LOG_FILE%"
    "%PYTHON_EXE%" -s scripts\portable\link_portable_data_dirs.py >> "%LOG_FILE%" 2>&1
)

if exist "scripts\prefetch_default_tagger.py" (
    echo [tagger] Ensuring default WD tagger cache >> "%LOG_FILE%"
    "%PYTHON_EXE%" -s scripts\prefetch_default_tagger.py --if-missing --tagger-models-dir "%MIKAZUKI_TAGGER_MODELS_DIR%" >> "%LOG_FILE%" 2>&1
)

if exist "scripts\prefetch_sdxl_tokenizer.py" (
    echo [tokenizer] Ensuring SDXL tokenizer cache >> "%LOG_FILE%"
    "%PYTHON_EXE%" -s scripts\prefetch_sdxl_tokenizer.py --if-missing --cache-dir "%MIKAZUKI_TOKENIZER_CACHE_DIR%" >> "%LOG_FILE%" 2>&1
)

echo [launch] Starting gui.py >> "%LOG_FILE%"
echo.
echo  Starting Next-Trainer...
echo  运行日志（打标下载进度、错误信息等）将显示在本窗口。
echo.

"%PYTHON_EXE%" -s -u gui.py --skip-prepare-environment --port 28000 %*
set "EXIT_CODE=%errorlevel%"
echo [launch] gui.py exited with code %EXIT_CODE% >> "%LOG_FILE%"

if %EXIT_CODE% neq 0 (
    echo.
    echo  ============================================
    echo   Next-Trainer exited abnormally [code: %EXIT_CODE%]
    echo   Log: %LOG_FILE%
    echo   Please send this log when reporting bugs.
    echo  ============================================
    echo.
)
pause
exit /b %EXIT_CODE%

:no_python
echo.
echo  [ERROR] python_embeded\python.exe not found!
echo  Please make sure the package is fully extracted.
echo.
echo [ERROR] python_embeded\python.exe not found >> "%LOG_FILE%"
goto :fail

:no_project
echo.
echo  [ERROR] Next-Trainer folder not found!
echo.
echo [ERROR] Cannot cd to %PORTABLE_ROOT%Next-Trainer >> "%LOG_FILE%"
goto :fail

:fail
echo.
echo  ============================================
echo   Next-Trainer failed to start.
echo   Log: %LOG_FILE%
echo   Please send this log when reporting bugs.
echo  ============================================
echo.
pause
exit /b 1
