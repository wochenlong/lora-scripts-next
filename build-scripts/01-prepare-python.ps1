# 01-prepare-python.ps1
# 准备 Python 嵌入式环境

param(
    [string]$BuildDir = (Join-Path (Split-Path $PSScriptRoot -Parent) "build\next-trainer-portable")
)

$ErrorActionPreference = "Stop"

Write-Host "=== 准备 Python 嵌入式环境 ===" -ForegroundColor Cyan

$pythonDir = Join-Path $BuildDir "python"
$pythonUrl = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip"
$pythonZip = Join-Path $env:TEMP "python-3.10.11-embed-amd64.zip"

# 检查是否已有 Python 环境
if (Test-Path (Join-Path $pythonDir "python.exe")) {
    Write-Host "Python 环境已存在，跳过下载" -ForegroundColor Green
    exit 0
}

# 创建目录
New-Item -ItemType Directory -Path $pythonDir -Force | Out-Null

# 下载 Python
Write-Host "下载 Python 3.10.11 嵌入式版本..."
try {
    Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonZip -UseBasicParsing
} catch {
    throw "下载 Python 失败: $_"
}

# 解压
Write-Host "解压 Python..."
Expand-Archive -Path $pythonZip -DestinationPath $pythonDir -Force
Remove-Item $pythonZip -Force

# 删除 _pth 文件以启用 site-packages
$pthFiles = Get-ChildItem -Path $pythonDir -Filter "*._pth" -ErrorAction SilentlyContinue
foreach ($pth in $pthFiles) {
    Remove-Item $pth.FullName -Force
    Write-Host "已删除: $($pth.Name)"
}

# 创建 site-packages 目录
$sitePackages = Join-Path $pythonDir "Lib\site-packages"
New-Item -ItemType Directory -Path $sitePackages -Force | Out-Null

# 创建 sitecustomize.py 自动配置路径
$sitecustomizeContent = @"
import sys
import os

# 自动检测项目目录
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.join(os.path.dirname(script_dir), 'lora-scripts-next')

if os.path.exists(project_dir):
    sys.path.insert(0, project_dir)

# 添加 site-packages
site_packages = os.path.join(script_dir, 'Lib', 'site-packages')
if os.path.exists(site_packages):
    sys.path.insert(0, site_packages)
"@

$sitecustomizePath = Join-Path $sitePackages "sitecustomize.py"
$sitecustomizeContent | Out-File -FilePath $sitecustomizePath -Encoding UTF8

Write-Host "Python 环境准备完成" -ForegroundColor Green

# 验证
$pythonExe = Join-Path $pythonDir "python.exe"
& $pythonExe --version

exit 0
