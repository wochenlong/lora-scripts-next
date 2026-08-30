# Shared pre-install checks for source / venv installs (install-cn.ps1, install.ps1).

$script:ExpectedTorchPin = "2.7.0+cu128"

function Test-InstallScriptFreshness {
    $cn = Join-Path $PSScriptRoot "install-cn.ps1"
    if (-not (Test-Path -LiteralPath $cn)) {
        return $true
    }
    $content = Get-Content -LiteralPath $cn -Raw -ErrorAction SilentlyContinue
    if ($content -match "2\.0\.[0-9]\+cu118") {
        Write-Host ""
        Write-Host "[错误] 安装脚本过旧（仍包含 torch 2.0.x + cu118）。" -ForegroundColor Red
        Write-Host "  请在本目录执行: git pull"
        Write-Host "  或下载最新 Release 整合包（SD-Trainer-v2.x.7z），解压后双击 run_gui.bat。"
        Write-Host ""
        return $false
    }
    if ($content -notmatch [regex]::Escape($script:ExpectedTorchPin)) {
        Write-Host ""
        Write-Host "[错误] install-cn.ps1 与当前版本不匹配（需要 $script:ExpectedTorchPin）。" -ForegroundColor Red
        Write-Host "  请 git pull 到最新 main，或改用 Releases 整合包。"
        Write-Host ""
        return $false
    }
    return $true
}

function Test-InstallPython {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Host ""
        Write-Host "[错误] 找不到 python 命令。请安装 Python 3.10 64 位并加入 PATH。" -ForegroundColor Red
        Write-Host "  或直接使用 Releases 里的 Next-Trainer 整合包（无需自己装 Python）。"
        Write-Host ""
        return $false
    }

    $verLine = (python --version 2>&1) | Out-String
    $verLine = $verLine.Trim()
    $bits = (python -c "import struct; print(8 * struct.calcsize('P'))" 2>$null)
    $major = (python -c "import sys; print(sys.version_info.major)" 2>$null)
    $minor = (python -c "import sys; print(sys.version_info.minor)" 2>$null)

    if ($bits -ne "64") {
        Write-Host ""
        Write-Host "[错误] 需要 64 位 Python，当前为 ${bits} 位。" -ForegroundColor Red
        Write-Host "  请安装 https://www.python.org/downloads/release/python-31011/ 的 Windows amd64 版本。"
        Write-Host ""
        return $false
    }

    if ($major -ne "3" -or [int]$minor -lt 10 -or [int]$minor -gt 11) {
        Write-Host ""
        Write-Host "[错误] 需要 Python 3.10 或 3.11，当前: $verLine" -ForegroundColor Red
        Write-Host "  Python 3.12 及以上没有本项目 PyTorch CUDA 预编译包，会出现 No matching distribution。"
        Write-Host "  建议: py -3.10 -m venv venv  或直接使用 Releases 整合包。"
        Write-Host ""
        return $false
    }

    Write-Output "Python 检查通过: $verLine (${bits} 位)"
    return $true
}
