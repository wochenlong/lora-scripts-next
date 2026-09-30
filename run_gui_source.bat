@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "HF_HOME=huggingface"
set "PYTHONUTF8=1"
set "MIKAZUKI_PORT=28000"

:: Source/venv launcher. Portable packages use run_gui_portable.bat instead.

if exist "venv\Scripts\python.exe" goto :launch
if exist "python\python.exe" goto :launch

findstr /C:"2.7.0+cu128" "%~dp0install-cn.ps1" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] 安装脚本过旧或与当前仓库不符。
    echo   请在本目录执行 git pull，或下载最新 Release 整合包后双击 run_gui.bat。
    echo.
    pause
    exit /b 1
)

echo [First run] Installing dependencies for source environment, please wait...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-cn.ps1"
if errorlevel 1 (
    echo Install failed. Check network and retry.
    pause
    exit /b 1
)

:launch
:: A venv left behind by a failed install used to reach `python gui.py` and die
:: at the first missing dependency with nothing pointing back at the installer.
:: Check for the package directory rather than importing: an import costs
:: several seconds on every launch.
if exist "venv\Scripts\python.exe" if not exist "venv\Lib\site-packages\fastapi\__init__.py" (
    echo.
    echo [ERROR] venv 已存在，但里面没有 fastapi —— 上一次依赖安装没有真正完成。
    echo   请重新运行安装脚本:
    echo     powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-cn.ps1"
    echo   若仍然失败，删除 venv 文件夹后重试。
    echo.
    pause
    exit /b 1
)

if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"
if exist "python\python.exe" set "PATH=%~dp0python;%PATH%"

if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" scripts\prefetch_default_tagger.py --if-missing
)

python gui.py %*
set "EXIT_CODE=%errorlevel%"
if %EXIT_CODE% neq 0 pause
exit /b %EXIT_CODE%
