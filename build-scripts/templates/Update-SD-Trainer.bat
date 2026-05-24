@echo off
chcp 65001 >nul 2>&1
setlocal
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

set "UPDATE_BRANCH="
for /f "tokens=*" %%b in ('git branch --show-current 2^>nul') do set "UPDATE_BRANCH=%%b"
if not defined UPDATE_BRANCH (
    for /f "tokens=*" %%b in ('git symbolic-ref --short refs/remotes/origin/HEAD 2^>nul') do set "UPDATE_BRANCH=%%b"
    set "UPDATE_BRANCH=%UPDATE_BRANCH:origin/=%"
)
if not defined UPDATE_BRANCH set "UPDATE_BRANCH=main"

echo Please close SD-Trainer WebUI before updating.
echo 请先关闭正在运行的 SD-Trainer WebUI，再继续更新。
echo.
echo Update branch / 更新分支: %UPDATE_BRANCH%
echo.

echo Fetching latest code / 获取最新代码...
git fetch origin %UPDATE_BRANCH% --tags --depth=1
if errorlevel 1 (
    echo.
    echo [Error] git fetch failed / 获取代码失败
    pause
    exit /b 1
)
echo.

set "DIRTY="
for /f "tokens=*" %%i in ('git status --porcelain') do set "DIRTY=1"
if defined DIRTY (
    set "STASH_NAME=portable-updater-%date:/=-%-%time::=-%"
    set "STASH_NAME=%STASH_NAME: =0%"
    echo Local changes detected; creating git stash backup...
    echo 检测到本地改动，正在创建 git stash 备份...
    git stash push -u -m "%STASH_NAME%"
    if errorlevel 1 (
        echo.
        echo [Error] Could not stash local changes / 无法备份本地改动
        pause
        exit /b 1
    )
    echo Stashed as: %STASH_NAME%
    echo.
)

echo Updating code / 更新代码...
git merge --ff-only "origin/%UPDATE_BRANCH%" 2>nul
if errorlevel 1 (
    git merge --ff-only FETCH_HEAD
    if errorlevel 1 (
        git pull --ff-only --depth=1 origin %UPDATE_BRANCH%
        if errorlevel 1 (
        echo.
        echo [Error] fast-forward update failed / 快进更新失败
        echo If you edited SD-Trainer files locally, restore from stash or re-download the release.
        echo 若修改过 SD-Trainer 内文件，请用 git stash pop 恢复，或重新下载整合包。
        pause
        exit /b 1
    )
)
echo.

echo Updating submodules / 更新子模块...
git submodule update --init --recursive
if errorlevel 1 (
    echo.
    echo [Warning] Optional submodule update failed / 可选子模块更新失败
    echo dataset-tag-editor is not required for the main training workflow.
    echo dataset-tag-editor 不影响主要训练流程，继续更新。
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
