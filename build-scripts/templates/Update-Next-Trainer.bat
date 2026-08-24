@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
title Update Next-Trainer
set "PORTABLE_ROOT=%~dp0"
for %%I in ("%~dp0.") do set "PORTABLE_ROOT_PS=%%~fI"
set "PROJECT_DIR=%PORTABLE_ROOT%Next-Trainer"

if /I not "%~1"=="--no-bootstrap" (
    if exist "%PROJECT_DIR%\" (
        call :ensure_updater_bootstrap
        call :bootstrap_updater_scripts
        if errorlevel 10 (
            echo.
            echo Relaunching with refreshed updater scripts / 使用最新更新脚本重新执行...
            echo.
            call "%~f0" --no-bootstrap %*
            exit /b !errorlevel!
        )
    )
)
if /I "%~1"=="--no-bootstrap" shift

echo ========================================
echo   Next-Trainer Update / 更新项目代码
echo ========================================
echo.

:: --------------- Pre-checks ---------------
if not exist "%PROJECT_DIR%\" (
    echo [Error] Next-Trainer directory not found / 未找到 Next-Trainer 目录
    echo Please make sure this script is in the portable package root.
    echo 请确认本脚本位于整合包根目录。
    pause
    exit /b 1
)

set "VER_BEFORE="
set "BUILD_BEFORE="
if exist "%PROJECT_DIR%\VERSION" set /p VER_BEFORE=<"%PROJECT_DIR%\VERSION"
if exist "%PROJECT_DIR%\PORTABLE_BUILD" set /p BUILD_BEFORE=<"%PROJECT_DIR%\PORTABLE_BUILD"
set "STATUS_PS1=%PROJECT_DIR%\scripts\portable\show_portable_update_status.ps1"
if exist "%STATUS_PS1%" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%STATUS_PS1%" -PortableRoot "%PORTABLE_ROOT_PS%" -UpdaterLabel "Git" -UpdaterFile "%~f0"
) else (
    call :print_version_info
)

cd /d "%PROJECT_DIR%"

if not exist ".git\" (
    echo [Error] This portable package is not a git checkout / 当前整合包不是 git 仓库
    echo.
    echo The release 7z package does not include .git metadata, so it cannot be
    echo updated with git pull.
    echo 发布版 7z 整合包不包含 .git 信息，因此不能通过 git pull 原地更新。
    echo.
    echo Try Update-Next-Trainer-Release.bat instead ^(downloads latest 7z^):
    echo 可改用 Update-Next-Trainer-Release.bat ^(下载 Release 并原地合并^)：
    echo   %PORTABLE_ROOT%Update-Next-Trainer-Release.bat
    echo.
    echo Or download the latest Release package manually, then keep/copy your data:
    echo 或手动下载最新 Release 整合包，并保留/拷贝你的数据：
    echo   - sd-models\
    echo   - output\
    echo   - logs\
    echo   - Next-Trainer\extensions\  ^(Anima Fast plugin, if installed^)
    echo   - config\autosave\  ^(if needed / 如需保留历史配置^)
    echo.
    echo If you want git-based updates, use a package built with .git metadata.
    echo 如需使用 git 更新，请使用带 .git 元数据的新版整合包。
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

echo Please close Next-Trainer WebUI before updating.
echo 请先关闭正在运行的 Next-Trainer WebUI，再继续更新。
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

set "IS_SHALLOW=false"
for /f "tokens=*" %%s in ('git rev-parse --is-shallow-repository 2^>nul') do set "IS_SHALLOW=%%s"
set "FETCH_DEPTH_ARG=--depth=1"
if /I "!IS_SHALLOW!"=="true" (
    set "FETCH_DEPTH_ARG=--deepen=50"
    echo Shallow git checkout detected; deepening history for safe fast-forward.
    echo 检测到浅克隆仓库，正在补齐部分历史以便安全快进更新。
    echo.
)

:: Attempt 1: direct
set "FETCH_OK=0"
echo [1/4] GitHub direct / GitHub 直连
git fetch origin %UPDATE_BRANCH% --tags !FETCH_DEPTH_ARG! >nul 2>&1
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
    echo  3. Try Update-Next-Trainer-Release.bat / 尝试 Release 原地更新:
    echo     %PORTABLE_ROOT%Update-Next-Trainer-Release.bat
    echo  4. Or download latest Release manually / 或手动下载最新整合包:
    echo     https://github.com/wochenlong/lora-scripts-next/releases
    echo  5. Keep your data: sd-models\, output\, logs\, extensions\
    echo     保留你的数据后替换或合并整合包
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

:: --------------- Submodules (with mirror fallback) ---------------
echo Updating submodules / 更新子模块...
echo.

set "SUB_OK=0"
set "SUB_PATH=mikazuki/dataset-tag-editor"
set "SUB_WORKTREE=mikazuki\dataset-tag-editor"

:: Read original submodule URL
set "SUB_ORIG_URL="
for /f "tokens=*" %%u in ('git config --file .gitmodules submodule.mikazuki/dataset-tag-editor.url 2^>nul') do set "SUB_ORIG_URL=%%u"
if not defined SUB_ORIG_URL set "SUB_ORIG_URL=https://github.com/Akegarasu/dataset-tag-editor"

:: Portable packages may already contain dataset-tag-editor files copied by
:: robocopy, but without submodule git metadata. In that case, cloning into the
:: non-empty directory fails; treat the bundled files as usable.
if exist "!SUB_WORKTREE!\scripts\launch.py" if not exist "!SUB_WORKTREE!\.git" (
    echo Bundled dataset-tag-editor files detected; skipping submodule clone.
    echo 检测到整合包已内置 dataset-tag-editor 文件，跳过子模块克隆。
    set "SUB_OK=1"
)

:: Attempt 1: direct
if !SUB_OK! equ 0 (
    echo [1/4] Submodule direct / 子模块直连
    git submodule update --init --recursive --depth=1 "!SUB_PATH!" >nul 2>&1
    if !errorlevel! equ 0 (
        set "SUB_OK=1"
        echo   OK
    )
)

:: Attempt 2-4: mirrors (temporary config override; do not modify .gitmodules)
if !SUB_OK! equ 0 (
    echo   Failed / 失败
    echo.
    timeout /t 2 /nobreak >nul
    call :try_submodule "2/4" "ghfast.top" "https://ghfast.top/!SUB_ORIG_URL!"
)
if !SUB_OK! equ 0 (
    timeout /t 2 /nobreak >nul
    call :try_submodule "3/4" "ghproxy mirror" "https://mirror.ghproxy.com/!SUB_ORIG_URL!"
)
if !SUB_OK! equ 0 (
    timeout /t 2 /nobreak >nul
    call :try_submodule "4/4" "gitmirror" "https://hub.gitmirror.com/!SUB_ORIG_URL!"
)

if !SUB_OK! equ 0 (
    echo.
    echo [Warning] Optional submodule update failed / 可选子模块更新失败
    echo dataset-tag-editor is not required for the main training workflow.
    echo dataset-tag-editor 不影响主要训练流程，继续更新。
) else (
    echo Submodule updated successfully / 子模块更新成功
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
)
for /f "tokens=*" %%h in ('git rev-parse --short HEAD 2^>nul') do set "GIT_HEAD=%%h"
if defined GIT_HEAD (
    echo   Git commit / 提交: !GIT_HEAD!
)
if exist "PORTABLE_BUILD" (
    set /p PORTABLE_BUILD=<PORTABLE_BUILD
    echo   PORTABLE_BUILD / 构建标识: !PORTABLE_BUILD!
)
if defined UPDATER_VER (
    echo   Updater script version / 更新脚本版本: !UPDATER_VER!
)
if defined VER_BEFORE if defined CURRENT_VER (
    if not "!VER_BEFORE!"=="!CURRENT_VER!" (
        echo   VERSION changed / 版本变化: !VER_BEFORE! -^> !CURRENT_VER!
    )
)
if defined BUILD_BEFORE if exist "PORTABLE_BUILD" (
    set /p _BUILD_AFTER=<PORTABLE_BUILD
    if not "!BUILD_BEFORE!"=="!_BUILD_AFTER!" (
        echo   PORTABLE_BUILD changed / 构建变化: !BUILD_BEFORE! -^> !_BUILD_AFTER!
    )
)
echo.
echo   Same VERSION hotfix republish? Use Update-Next-Trainer-Release.bat
echo   同 VERSION 重发修复包请用 Update-Next-Trainer-Release.bat
echo.

pause
exit /b 0

:: =============== Subroutine: ensure_updater_bootstrap ===============
:ensure_updater_bootstrap
set "BOOTSTRAP_PS1=%PROJECT_DIR%\scripts\portable\bootstrap_portable_updaters.ps1"
set "COMMON_PS1=%PROJECT_DIR%\scripts\portable\portable_updater_common.ps1"
if exist "%BOOTSTRAP_PS1%" if exist "%COMMON_PS1%" goto :eof
where curl >nul 2>&1
if errorlevel 1 goto :eof
if not exist "%PROJECT_DIR%\scripts\portable\" mkdir "%PROJECT_DIR%\scripts\portable\"
echo Bootstrapping updater scripts / 正在拉取更新脚本引导文件...
curl -fsSL --retry 2 -o "%COMMON_PS1%" "https://raw.githubusercontent.com/wochenlong/lora-scripts-next/main/scripts/portable/portable_updater_common.ps1" >nul 2>&1
if errorlevel 1 curl -fsSL --retry 2 -o "%COMMON_PS1%" "https://ghfast.top/https://raw.githubusercontent.com/wochenlong/lora-scripts-next/main/scripts/portable/portable_updater_common.ps1" >nul 2>&1
curl -fsSL --retry 2 -o "%BOOTSTRAP_PS1%" "https://raw.githubusercontent.com/wochenlong/lora-scripts-next/main/scripts/portable/bootstrap_portable_updaters.ps1" >nul 2>&1
if errorlevel 1 curl -fsSL --retry 2 -o "%BOOTSTRAP_PS1%" "https://ghfast.top/https://raw.githubusercontent.com/wochenlong/lora-scripts-next/main/scripts/portable/bootstrap_portable_updaters.ps1" >nul 2>&1
goto :eof

:: =============== Subroutine: bootstrap_updater_scripts ===============
:bootstrap_updater_scripts
where powershell >nul 2>&1
if errorlevel 1 exit /b 0
where curl >nul 2>&1
if errorlevel 1 exit /b 0
if not exist "%PROJECT_DIR%\scripts\portable\bootstrap_portable_updaters.ps1" exit /b 0
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%\scripts\portable\bootstrap_portable_updaters.ps1" -PortableRoot "%PORTABLE_ROOT_PS%"
exit /b %errorlevel%

:: =============== Subroutine: print_version_info ===============
:print_version_info
echo --- Package status / 当前整合包 ---
if exist "%PROJECT_DIR%\VERSION" (
    set /p _PKG_VER=<"%PROJECT_DIR%\VERSION"
    echo   VERSION: !_PKG_VER!
) else (
    echo   VERSION: ^(missing^)
)
if exist "%PROJECT_DIR%\PORTABLE_BUILD" (
    set /p _PKG_BUILD=<"%PROJECT_DIR%\PORTABLE_BUILD"
    echo   PORTABLE_BUILD: !_PKG_BUILD!
)
if exist "%PROJECT_DIR%\.git\HEAD" (
    pushd "%PROJECT_DIR%"
    for /f "tokens=*" %%h in ('git rev-parse --short HEAD 2^>nul') do echo   Git commit: %%h
    popd
) else (
    echo   Git commit: ^(no .git / 无 git 仓库^)
)
set "UPDATER_VER=unknown"
if exist "%PROJECT_DIR%\scripts\portable\UPDATER_VERSION" (
    set /p UPDATER_VER=<"%PROJECT_DIR%\scripts\portable\UPDATER_VERSION"
)
echo --- Updater / 更新脚本 ---
echo   Git updater script version / Git更新脚本版本: !UPDATER_VER!
echo   Updater file / 脚本路径: %~f0
echo.
goto :eof

:: =============== Subroutine: try_mirror ===============
:: Usage: call :try_mirror "label" "name" "url" branch
:try_mirror
echo [%~1] %~2
git fetch "%~3" %~4 --tags !FETCH_DEPTH_ARG! >nul 2>&1
if !errorlevel! equ 0 (
    set "FETCH_OK=1"
    echo   OK
) else (
    echo   Failed / 失败
    echo.
)
goto :eof

:: =============== Subroutine: try_submodule ===============
:: Usage: call :try_submodule "label" "name" "mirror_url"
:try_submodule
echo [%~1] Submodule via %~2
git -c "submodule.mikazuki/dataset-tag-editor.url=%~3" submodule update --init --recursive --depth=1 "!SUB_PATH!" >nul 2>&1
if !errorlevel! equ 0 (
    set "SUB_OK=1"
    echo   OK
) else (
    echo   Failed / 失败
    echo.
)
goto :eof
