# 04-create-launchers.ps1
# 创建启动脚本

param(
    [string]$BuildDir = (Join-Path (Split-Path $PSScriptRoot -Parent) "build\next-trainer-portable")
)

$ErrorActionPreference = "Stop"

Write-Host "=== 创建启动脚本 ===" -ForegroundColor Cyan

# run_gui.bat
$runGuiContent = @"
@echo off
cd /d "%~dp0lora-scripts-next"
set PYTHONPATH=%~dp0lora-scripts-next;%~dp0python\Lib\site-packages
set PATH=%~dp0python;%~dp0python\Scripts;%PATH%
"%~dp0python\python.exe" gui.py
pause
"@

$runGuiPath = Join-Path $BuildDir "run_gui.bat"
$runGuiContent | Out-File -FilePath $runGuiPath -Encoding ASCII
Write-Host "创建 run_gui.bat"

# README.txt
$readmeContent = @"
Next-Trainer 便携式整合包
========================

使用方法：
1. 双击 run_gui.bat 启动
2. 浏览器访问 http://127.0.0.1:28000

目录结构：
- python/          Python 3.10.11 环境
- lora-scripts-next/  项目文件
- sd-models/       模型文件目录（需自行放置）
- output/          输出目录
- logs/            日志目录

注意：
- 本整合包不包含模型文件
- 请将模型文件放置到 sd-models 目录
- 首次启动可能需要较长时间初始化
"@

$readmePath = Join-Path $BuildDir "README.txt"
$readmeContent | Out-File -FilePath $readmePath -Encoding UTF8
Write-Host "创建 README.txt"

Write-Host "启动脚本创建完成" -ForegroundColor Green

exit 0
