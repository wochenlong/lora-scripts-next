@echo off
chcp 65001 >nul 2>&1
title Update SD-Trainer
set "PORTABLE_ROOT=%~dp0"
set "PROJECT_DIR=%PORTABLE_ROOT%SD-Trainer"

echo ========================================
echo   SD-Trainer Update / 更新项目代码
echo ========================================
echo.

if not exist "%PROJECT_DIR%\" (
    echo [Error] SD-Trainer directory not found / 未找到 SD-Trainer 目录
    echo Please make sure this script is in the portable package root.
    echo 请确认本脚本位于整合包根目录。
    pause
    exit /b 1
)

cd /d "%PROJECT_DIR%"

if not exist ".git\" (
    echo [Error] This portable package is not a git checkout / 当前整合包不是 git 仓库
    echo.
    echo The release 7z package does not include .git metadata, so it cannot be
    echo updated with git pull.
    echo 发布版 7z 整合包不包含 .git 信息，因此不能通过 git pull 原地更新。
    echo.
    echo Please download the latest Release package, then keep/copy your data:
    echo 请下载最新 Release 整合包，并保留/拷贝你的数据：
    echo   - sd-models\
    echo   - output\
    echo   - logs\
    echo   - config\autosave\  ^(if needed / 如需保留历史配置^)
    echo.
    echo If you want git-based updates, clone the repository as source instead.
    echo 如需使用 git 更新，请改用源码 clone 方式安装。
    pause
    exit /b 1
)

where git >nul 2>&1
if errorlevel 1 (
    echo [Error] Git not found / 未找到 Git
    echo Please install Git: https://git-scm.com/
    pause
    exit /b 1
)

echo Pulling latest code / 拉取最新代码...
echo.
git pull
if errorlevel 1 (
    echo.
    echo [Error] git pull failed / 拉取代码失败
    pause
    exit /b 1
)
echo.

echo Updating submodules / 更新子模块...
git submodule update --init --recursive
if errorlevel 1 (
    echo.
    echo [Error] submodule update failed / 子模块更新失败
    pause
    exit /b 1
)
echo.

if exist "scripts\portable\sync_portable_root_launchers.bat" (
    echo Refreshing portable root launchers / 刷新整合包根目录启动脚本...
    call "scripts\portable\sync_portable_root_launchers.bat" --nopause
) else (
    echo [Note] No scripts\portable\sync_portable_root_launchers.bat — if GUI fails after update, re-copy run_gui.bat from release or re-download 7z.
)

echo.
echo ========================================
echo   Done / 更新完成
echo ========================================
pause
