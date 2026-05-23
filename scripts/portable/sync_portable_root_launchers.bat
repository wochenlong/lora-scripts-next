@echo off
chcp 65001 >nul 2>&1
:: Refresh portable ROOT launchers from this repo copy (run after git pull in SD-Trainer)
set "PORTABLE_ROOT=%~dp0..\..\..\"
set "SRC_GUI=%PORTABLE_ROOT%SD-Trainer\run_gui.bat"
set "SRC_PORTABLE=%PORTABLE_ROOT%SD-Trainer\scripts\portable\run_gui_portable_shim.bat"

if not exist "%SRC_GUI%" (
    echo [ERROR] Missing %SRC_GUI%
    pause
    exit /b 1
)

copy /Y "%SRC_GUI%" "%PORTABLE_ROOT%run_gui.bat" >nul
echo  Updated: %PORTABLE_ROOT%run_gui.bat

if exist "%SRC_PORTABLE%" (
    copy /Y "%SRC_PORTABLE%" "%PORTABLE_ROOT%run_gui_portable.bat" >nul
    echo  Updated: %PORTABLE_ROOT%run_gui_portable.bat
)

echo.
echo  Done. Root launchers now match SD-Trainer\ (for old 7z without scripts\portable\).
if /I not "%~1"=="--nopause" pause
