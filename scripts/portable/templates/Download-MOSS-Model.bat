@echo off
chcp 65001 >nul 2>&1
title Download MOSS-Image Base BF16
cd /d "%~dp0"

set "SCRIPT_DIR=%~dp0"
set "TRAINER_DIR="
set "PYTHON_EXE="

if exist "%SCRIPT_DIR%gui.py" (
    set "TRAINER_DIR=%SCRIPT_DIR%"
) else if exist "%SCRIPT_DIR%Next-Trainer\gui.py" (
    set "TRAINER_DIR=%SCRIPT_DIR%Next-Trainer\"
) else if exist "%SCRIPT_DIR%..\Next-Trainer\gui.py" (
    for %%I in ("%SCRIPT_DIR%..") do set "TRAINER_DIR=%%~fI\Next-Trainer\"
) else if exist "%SCRIPT_DIR%SD-Trainer\gui.py" (
    set "TRAINER_DIR=%SCRIPT_DIR%SD-Trainer\"
) else (
    echo [ERROR] Next-Trainer directory not found.
    echo Put this BAT in the portable root, tools\, or the Next-Trainer folder.
    pause
    exit /b 1
)

if exist "%TRAINER_DIR%..\python_embeded\python.exe" (
    set "PYTHON_EXE=%TRAINER_DIR%..\python_embeded\python.exe"
) else if exist "%TRAINER_DIR%python_embeded\python.exe" (
    set "PYTHON_EXE=%TRAINER_DIR%python_embeded\python.exe"
) else (
    for /f "delims=" %%P in ('where python 2^>nul') do if not defined PYTHON_EXE set "PYTHON_EXE=%%P"
)

if not defined PYTHON_EXE (
    echo [ERROR] Python was not found.
    pause
    exit /b 1
)

set "HELPER=%TRAINER_DIR%scripts\portable\download_moss_model.py"
if not exist "%HELPER%" (
    echo [ERROR] Downloader helper not found:
    echo   %HELPER%
    pause
    exit /b 1
)

echo ============================================================
echo   MOSS-Image Base BF16 Downloader
echo ============================================================
echo   Source: ModelScope China
echo   Output: %TRAINER_DIR%sd-models\moss-image
echo   Download: about 27 GB; resumable; SHA-256 verified
echo.
echo   Training-compatible files:
echo     dit.safetensors
echo     text_encoder.safetensors
echo     vae.safetensors
echo     tokenizer\
echo ============================================================
echo.

"%PYTHON_EXE%" -s "%HELPER%" --project-root "%TRAINER_DIR%"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%EXIT_CODE%"=="0" (
    echo [FAILED] MOSS-Image download did not complete.
    echo Run this BAT again to resume.
) else (
    echo [OK] MOSS-Image Base BF16 is ready for KohakuMossTrainer.
)
pause
exit /b %EXIT_CODE%
