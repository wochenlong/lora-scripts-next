@echo off
chcp 65001 >nul 2>&1
title SD-Trainer

:: Portable launcher logic (lives inside SD-Trainer/, updates with git pull / new 7z copy)
:: Stable paths relative to PORTABLE_ROOT (parent of SD-Trainer\):
::   python_embeded\python.exe
::   SD-Trainer\gui.py
::   SD-Trainer\setup_environment.py

set "PORTABLE_ROOT=%~dp0..\..\..\"
set "BASE_DIR=%PORTABLE_ROOT%"
set "HF_HOME=%PORTABLE_ROOT%huggingface"
set "PYTHONUTF8=1"
set "PYTHON_EXE=%PORTABLE_ROOT%python_embeded\python.exe"
set "LOG_FILE=%PORTABLE_ROOT%sd-trainer-log.txt"

echo ============================================ > "%LOG_FILE%"
echo  SD-Trainer Launch Log >> "%LOG_FILE%"
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
"%PYTHON_EXE%" -s "%PORTABLE_ROOT%SD-Trainer\setup_environment.py" 2>> "%LOG_FILE%"
if errorlevel 1 (
    echo [setup] FAILED >> "%LOG_FILE%"
    echo.
    echo  Setup failed. Check log: %LOG_FILE%
    goto :fail
)
echo [setup] OK >> "%LOG_FILE%"

:launch
cd /d "%PORTABLE_ROOT%SD-Trainer"
if errorlevel 1 goto :no_project

if exist "scripts\prefetch_default_tagger.py" (
    echo [tagger] Ensuring default WD tagger cache >> "%LOG_FILE%"
    "%PYTHON_EXE%" -s scripts\prefetch_default_tagger.py --if-missing >> "%LOG_FILE%" 2>&1
)

echo [launch] Starting gui.py >> "%LOG_FILE%"
echo.
echo  Starting SD-Trainer...
echo.

"%PYTHON_EXE%" -s gui.py --skip-prepare-environment --port 28000 %* 2>> "%LOG_FILE%"
set "EXIT_CODE=%errorlevel%"
echo [launch] gui.py exited with code %EXIT_CODE% >> "%LOG_FILE%"

if %EXIT_CODE% neq 0 (
    echo.
    echo  ============================================
    echo   SD-Trainer exited abnormally [code: %EXIT_CODE%]
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
echo  [ERROR] SD-Trainer folder not found!
echo.
echo [ERROR] Cannot cd to %PORTABLE_ROOT%SD-Trainer >> "%LOG_FILE%"
goto :fail

:fail
echo.
echo  ============================================
echo   SD-Trainer failed to start.
echo   Log: %LOG_FILE%
echo   Please send this log when reporting bugs.
echo  ============================================
echo.
pause
exit /b 1
