# build-all.ps1
# 一键创建 Windows 便携式整合包

param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent),
    [string]$Version = "1.0.0",
    [switch]$SkipZip,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$buildDir = Join-Path $ProjectRoot "build"
$portableDir = Join-Path $buildDir "sd-trainer-portable"

$startTime = Get-Date

Write-Host @"
========================================
  Next Trainer 便携式整合包构建脚本
  版本: $Version
  开始时间: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))
========================================
"@ -ForegroundColor Cyan

# 清理旧构建
if ($Clean -and (Test-Path $portableDir)) {
    Write-Host "`n清理旧构建目录..." -ForegroundColor Yellow
    Remove-Item -Path $portableDir -Recurse -Force
}

try {
    # 步骤 1: 准备 Python
    Write-Host "`n[1/5] 准备 Python 环境..." -ForegroundColor Cyan
    & (Join-Path $ProjectRoot "build-scripts\01-prepare-python.ps1") -BuildDir $portableDir
    if ($LASTEXITCODE -ne 0) { throw "Python 环境准备失败" }

    # 步骤 2: 安装依赖
    Write-Host "`n[2/5] 安装 Python 依赖..." -ForegroundColor Cyan
    & (Join-Path $ProjectRoot "build-scripts\02-install-dependencies.ps1") -BuildDir $portableDir -ProjectRoot $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw "依赖安装失败" }

    # 步骤 3: 复制项目
    Write-Host "`n[3/5] 复制项目文件..." -ForegroundColor Cyan
    & (Join-Path $ProjectRoot "build-scripts\03-copy-project.ps1") -BuildDir $portableDir -ProjectRoot $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw "项目文件复制失败" }

    # 步骤 4: 创建启动脚本
    Write-Host "`n[4/5] 创建启动脚本..." -ForegroundColor Cyan
    & (Join-Path $ProjectRoot "build-scripts\04-create-launchers.ps1") -BuildDir $portableDir
    if ($LASTEXITCODE -ne 0) { throw "启动脚本创建失败" }

    # 步骤 5: 创建 ZIP 压缩包
    if (-not $SkipZip) {
        Write-Host "`n[5/5] 创建 ZIP 压缩包..." -ForegroundColor Cyan
        & (Join-Path $ProjectRoot "build-scripts\05-create-zip.ps1") -BuildDir $buildDir -Version $Version
        if ($LASTEXITCODE -ne 0) { throw "ZIP 创建失败" }
    } else {
        Write-Host "`n[5/5] 跳过 ZIP 创建" -ForegroundColor Yellow
    }

    $endTime = Get-Date
    $duration = $endTime - $startTime

    # 结果
    Write-Host @"

========================================
  构建完成!
  
  输出文件:
  - $(Join-Path $buildDir "Next-Trainer-v$Version.zip")
  
  便携式目录:
  - $portableDir
  
  构建耗时: $($duration.ToString('hh\:mm\:ss'))
========================================
"@ -ForegroundColor Green

} catch {
    Write-Host "`n构建失败: $_" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor Red
    exit 1
}
