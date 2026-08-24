# 05-create-zip.ps1
# 创建 ZIP 压缩包

param(
    [string]$BuildDir = (Join-Path (Split-Path $PSScriptRoot -Parent) "build"),
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

Write-Host "=== 创建 ZIP 压缩包 ===" -ForegroundColor Cyan

$portableDir = Join-Path $BuildDir "next-trainer-portable"
$zipFile = Join-Path $BuildDir "Next-Trainer-v$Version.zip"

# 检查源目录
if (-not (Test-Path $portableDir)) {
    throw "便携式目录不存在: $portableDir"
}

# 删除旧的 ZIP 文件
if (Test-Path $zipFile) {
    Remove-Item $zipFile -Force
    Write-Host "已删除旧的 ZIP 文件"
}

# 创建 ZIP
Write-Host "正在创建 ZIP 压缩包..."
Write-Host "源目录: $portableDir"
Write-Host "目标文件: $zipFile"

Compress-Archive -Path $portableDir -DestinationPath $zipFile -CompressionLevel Optimal

# 显示文件大小
$fileSize = (Get-Item $zipFile).Length / 1GB
Write-Host "ZIP 文件创建完成: $([math]::Round($fileSize, 2)) GB" -ForegroundColor Green

exit 0
