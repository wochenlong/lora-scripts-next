# 02-install-dependencies.ps1
# 安装依赖到便携式环境

param(
    [string]$BuildDir = (Join-Path (Split-Path $PSScriptRoot -Parent) "build\next-trainer-portable"),
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent)
)

$ErrorActionPreference = "Stop"

Write-Host "=== 安装依赖 ===" -ForegroundColor Cyan

$pythonDir = Join-Path $BuildDir "python"
$pythonExe = Join-Path $pythonDir "python.exe"
$sitePackages = Join-Path $pythonDir "Lib\site-packages"

# 检查 Python 是否存在
if (-not (Test-Path $pythonExe)) {
    throw "Python 环境不存在，请先运行 01-prepare-python.ps1"
}

# 安装 pip
Write-Host "安装 pip..."
$getPipUrl = "https://bootstrap.pypa.io/get-pip.py"
$getPipPath = Join-Path $env:TEMP "get-pip.py"

try {
    Invoke-WebRequest -Uri $getPipUrl -OutFile $getPipPath -UseBasicParsing
} catch {
    throw "下载 get-pip.py 失败: $_"
}

& $pythonExe $getPipPath --target $sitePackages 2>&1 | Out-Null

# 安装 PyTorch + xformers
Write-Host "安装 PyTorch 2.7.0+cu128 和 xformers..."
& $pythonExe -m pip install torch==2.7.0+cu128 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128 --target $sitePackages --no-warn-script-location 2>&1 | Select-Object -Last 5

& $pythonExe -m pip install xformers==0.0.30 --index-url https://download.pytorch.org/whl/cu128 --target $sitePackages --no-warn-script-location 2>&1 | Select-Object -Last 5

# 安装项目依赖
Write-Host "安装项目依赖..."
$requirementsFile = Join-Path $ProjectRoot "requirements.txt"
& $pythonExe -m pip install -r $requirementsFile --target $sitePackages --no-warn-script-location 2>&1 | Select-Object -Last 10

# 修复 numpy 版本冲突
Write-Host "修复 numpy 版本..."
$numpyDir = Join-Path $sitePackages "numpy"
$numpyLibs = Join-Path $sitePackages "numpy.libs"
if (Test-Path $numpyDir) { Remove-Item $numpyDir -Recurse -Force -ErrorAction SilentlyContinue }
if (Test-Path $numpyLibs) { Remove-Item $numpyLibs -Recurse -Force -ErrorAction SilentlyContinue }
& $pythonExe -m pip install numpy==1.26.4 --target $sitePackages --no-warn-script-location 2>&1 | Out-Null

# 清理 torch 版本冲突
Write-Host "清理 torch 版本冲突..."
$torchDist = Get-ChildItem -Path $sitePackages -Filter "torch-2.12*.dist-info" -ErrorAction SilentlyContinue
if ($torchDist) {
    Remove-Item $torchDist.FullName -Recurse -Force
}

# 验证安装
Write-Host "`n验证安装..." -ForegroundColor Cyan
& $pythonExe -c "import torch; print(f'torch: {torch.__version__}')"
& $pythonExe -c "import xformers; print(f'xformers: {xformers.__version__}')"
& $pythonExe -c "import numpy; print(f'numpy: {numpy.__version__}')"
& $pythonExe -c "import gradio; print(f'gradio: {gradio.__version__}')"

Write-Host "`n依赖安装完成" -ForegroundColor Green

exit 0
