@echo off
set "PORTABLE_ROOT=%~dp0"
for %%I in ("%~dp0.") do set "PORTABLE_ROOT_PS=%%~fI"
set "FIX_PS=%PORTABLE_ROOT%Next-Trainer\scripts\portable\fix_portable_batch_crlf.ps1"
if not exist "%FIX_PS%" (
    echo [Error] Missing fix script: %FIX_PS%
    pause
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%FIX_PS%" -PortableRoot "%PORTABLE_ROOT_PS%"
if errorlevel 1 (
    echo [Error] Fix failed.
    pause
    exit /b 1
)
echo.
echo Done. You can run Update-Next-Trainer-Release.bat now.
echo.
pause
