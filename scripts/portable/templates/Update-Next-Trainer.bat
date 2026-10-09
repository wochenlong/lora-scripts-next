@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem Parse the entire handoff before the worker can replace this root launcher.
(
    set "NO_PAUSE=%~1"
    if not exist "%~dp0python_embeded\python.exe" (
        echo [Error] Embedded Python is missing.
        exit /b 1
    )
    if not exist "%~dp0Next-Trainer\scripts\portable\update_portable.py" (
        echo [Error] Update worker is missing. Install a complete portable package.
        exit /b 1
    )
    echo Please close this package's GUI before updating.
    "%~dp0python_embeded\python.exe" -s "%~dp0Next-Trainer\scripts\portable\update_portable.py" --portable-root "%~dp0."
    set "RESULT=!errorlevel!"
    if not "!NO_PAUSE!"=="--no-pause" pause
    exit /b !RESULT!
)
