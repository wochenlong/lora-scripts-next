@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

:: =============================================================================
:: Stable entrypoints (do not rename — portable 7z / user shortcuts bind here)
::
:: Portable layout:
::   python_embeded\  +  Next-Trainer\gui.py
::   Prefer Next-Trainer\scripts\portable\launch_portable.bat (updates with git/7z)
::   Fallback: run_gui_portable.bat at package root (old releases)
::
:: Source checkout:
::   run_gui_source.bat  ->  install-cn.ps1 on first run
:: =============================================================================

if exist "python_embeded\python.exe" if exist "Next-Trainer\gui.py" (
    if exist "Next-Trainer\scripts\portable\launch_portable.bat" (
        call "%~dp0Next-Trainer\scripts\portable\launch_portable.bat" %*
        exit /b %errorlevel%
    )
    if exist "run_gui_portable.bat" (
        call "%~dp0run_gui_portable.bat" %*
        exit /b %errorlevel%
    )
    echo [ERROR] Portable launcher missing. Update Next-Trainer or re-download the release 7z.
    pause
    exit /b 1
)

if exist "run_gui_source.bat" (
    call "%~dp0run_gui_source.bat" %*
    exit /b %errorlevel%
)

echo [ERROR] No launcher found. Please make sure the package is fully extracted.
pause
exit /b 1
