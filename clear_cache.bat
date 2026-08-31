@echo off
chcp 65001 >nul 2>&1
title Clear uv download cache
cd /d "%~dp0"

REM Clear the uv global cache (%%LOCALAPPDATA%%\uv\cache).
REM
REM Engine installers (Anima Fast / Musubi / AI Toolkit) use the uv cache by
REM default so reinstalls and sibling engines share multi-GB downloads (torch
REM etc.). Run this script when you need the disk space back.

echo.
echo  ============================================
echo   Clear uv download cache
echo  ============================================
echo.

where uv >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] uv not found in PATH.
    echo  Install uv first ^(https://docs.astral.sh/uv/^), or remove the cache
    echo  directory manually: rmdir /s /q "%LOCALAPPDATA%\uv\cache"
    echo.
    pause
    exit /b 1
)

uv cache info
echo.
echo  Cleaning...
uv cache clean
echo.
echo  Done. Engine reinstalls will download dependencies again on next install.
echo.
pause
