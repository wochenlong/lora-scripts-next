@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
title Update SD-Trainer
set "PORTABLE_ROOT=%~dp0"
set "PROJECT_DIR=%PORTABLE_ROOT%SD-Trainer"

echo ========================================
echo   SD-Trainer Update / 更新项目代码
echo ========================================
echo.

:: --------------- Pre-checks ---------------
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

:: --------------- Detect branch ---------------
set "UPDATE_BRANCH="
for /f "tokens=*" %%b in ('git branch --show-current 2^>nul') do set "UPDATE_BRANCH=%%b"
if not defined UPDATE_BRANCH (
    for /f "tokens=*" %%b in ('git symbolic-ref --short refs/remotes/origin/HEAD 2^>nul') do set "UPDATE_BRANCH=%%b"
    if defined UPDATE_BRANCH set "UPDATE_BRANCH=!UPDATE_BRANCH:origin/=!"
)
if not defined UPDATE_BRANCH set "UPDATE_BRANCH=main"

echo Please close SD-Trainer WebUI before updating.
echo 请先关闭正在运行的 SD-Trainer WebUI，再继续更新。
echo.
echo Update branch / 更新分支: %UPDATE_BRANCH%
echo.

:: --------------- Detect origin URL ---------------
set "ORIGIN_URL="
for /f "tokens=*" %%u in ('git remote get-url origin 2^>nul') do set "ORIGIN_URL=%%u"
if not defined ORIGIN_URL set "ORIGIN_URL=https://github.com/wochenlong/lora-scripts-next.git"

:: --------------- Fetch with mirror fallback ---------------
echo Fetching latest code / 获取最新代码...
echo.

:: Attempt 1: direct
set "FETCH_OK=0"
echo [1/4] GitHub direct / GitHub 直连
git fetch origin %UPDATE_BRANCH% --tags --depth=1 >nul 2>&1
if !errorlevel! equ 0 (
    set "FETCH_OK=1"
    echo   OK
)

:: Attempt 2-4: mirrors
if !FETCH_OK! equ 0 (
    echo   Failed / 失败
    echo.
    timeout /t 2 /nobreak >nul
    call :try_mirror "2/4" "ghfast.top" "https://ghfast.top/%ORIGIN_URL%" %UPDATE_BRANCH%
)
if !FETCH_OK! equ 0 (
    timeout /t 2 /nobreak >nul
    call :try_mirror "3/4" "ghproxy mirror" "https://mirror.ghproxy.com/%ORIGIN_URL%" %UPDATE_BRANCH%
)
if !FETCH_OK! equ 0 (
    timeout /t 2 /nobreak >nul
    call :try_mirror "4/4" "gitmirror" "https://hub.gitmirror.com/%ORIGIN_URL%" %UPDATE_BRANCH%
)

if %FETCH_OK% equ 0 (
    echo.
    echo ========================================
    echo [Error] All fetch attempts failed / 所有获取方式均失败
    echo ========================================
    echo.
    echo Troubleshooting / 排障建议:
    echo.
    echo  1. Check your network connection / 检查网络连接
    echo  2. If you use a proxy, configure git:
    echo     如果你使用代理，请配置 git:
    echo       git config --global http.proxy http://127.0.0.1:PORT
    echo       git config --global https.proxy http://127.0.0.1:PORT
    echo  3. Download latest Release manually / 手动下载最新整合包:
    echo     https://github.com/wochenlong/lora-scripts-next/releases
    echo  4. Keep your data: sd-models\, output\, logs\, config\
    echo     保留你的数据后替换整合包
    echo.
    pause
    exit /b 1
)
echo.

:: --------------- Stash local changes ---------------
set "DIRTY="
for /f "tokens=*" %%i in ('git status --porcelain') do set "DIRTY=1"
if defined DIRTY (
    set "STASH_NAME=portable-updater-%date:/=-%-%time::=-%"
    set "STASH_NAME=!STASH_NAME: =0!"
    echo Local changes detected; creating git stash backup...
    echo 检测到本地改动，正在创建 git stash 备份...
    git stash push -u -m "!STASH_NAME!"
    if errorlevel 1 (
        echo.
        echo [Error] Could not stash local changes / 无法备份本地改动
        pause
        exit /b 1
    )
    echo Stashed as: !STASH_NAME!
    echo.
)

:: --------------- Fast-forward merge ---------------
echo Updating code / 更新代码...
git merge --ff-only "origin/%UPDATE_BRANCH%" 2>nul
if errorlevel 1 (
    git merge --ff-only FETCH_HEAD 2>nul
    if errorlevel 1 (
        git pull --ff-only --depth=1 origin %UPDATE_BRANCH% 2>nul
        if errorlevel 1 (
            echo.
            echo [Error] fast-forward update failed / 快进更新失败
            echo.
            echo This usually means local commits diverged from remote.
            echo 通常是因为本地提交与远程分支产生了分歧。
            echo.
            echo Options / 解决方案:
            echo   1. git stash pop  ^(restore your changes / 恢复你的改动^)
            echo   2. Re-download the latest Release package / 重新下载最新整合包
            pause
            exit /b 1
        )
    )
)
echo.

:: --------------- Submodules (non-blocking, with depth) ---------------
echo Updating submodules / 更新子模块...
git submodule update --init --recursive --depth=1 2>nul
if errorlevel 1 (
    echo.
    echo [Warning] Optional submodule update failed / 可选子模块更新失败
    echo dataset-tag-editor is not required for the main training workflow.
    echo dataset-tag-editor 不影响主要训练流程，继续更新。
)
echo.

:: --------------- Refresh root launchers ---------------
if exist "scripts\portable\sync_portable_root_launchers.bat" (
    echo Refreshing portable root launchers / 刷新整合包根目录启动脚本...
    call "scripts\portable\sync_portable_root_launchers.bat" --nopause
) else (
    echo [Note] No scripts\portable\sync_portable_root_launchers.bat
    echo If GUI fails after update, re-copy run_gui.bat from release or re-download 7z.
    echo 若更新后启动失败，请从 Release 包拷贝 run_gui.bat 或重新下载整合包。
)

echo.
echo ========================================
echo   Done / 更新完成
echo ========================================
echo.

:: Show current version if VERSION file exists
if exist "VERSION" (
    set /p CURRENT_VER=<VERSION
    echo   Current version / 当前版本: !CURRENT_VER!
    echo.
)

pause
exit /b 0

:: =============== Subroutine: try_mirror ===============
:: Usage: call :try_mirror "label" "name" "url" branch
:try_mirror
echo [%~1] %~2
git fetch "%~3" %~4 --tags --depth=1 >nul 2>&1
if !errorlevel! equ 0 (
    set "FETCH_OK=1"
    echo   OK
) else (
    echo   Failed / 失败
    echo.
)
goto :eof
