#Requires -Version 5.1
<#
.SYNOPSIS
  Reshape a portable root to the 2026 three-entry UX (see docs/design/portable-2026.md).
#>
param(
    [Parameter(Mandatory = $true)][string]$PortableRoot
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath $PortableRoot).Path
$tools = Join-Path $root "tools"
New-Item -ItemType Directory -Path $tools -Force | Out-Null

# Filenames via codepoints so the .ps1 survives without UTF-8 BOM.
$launchName = ([string]::new([char[]](0x542F, 0x52A8))) + ".bat"           # 启动.bat
$updateName = ([string]::new([char[]](0x68C0, 0x67E5, 0x66F4, 0x65B0))) + ".bat"  # 检查更新.bat
$readmeName = ([string]::new([char[]](0x8BF4, 0x660E))) + ".txt"            # 说明.txt

$moveNames = @(
    "run_gui.bat",
    "run_gui_portable.bat",
    "Update-Next-Trainer.bat",
    "Update-Next-Trainer-Release.bat",
    "Update-SD-Trainer.bat",
    "Update-SD-Trainer-Release.bat",
    "Download-Anima-Model.bat",
    "Fix-Portable-Bats.bat",
    "install_xformers.bat",
    "README.txt"
)

foreach ($name in $moveNames) {
    $src = Join-Path $root $name
    if (Test-Path -LiteralPath $src) {
        $dst = Join-Path $tools $name
        if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Force }
        Move-Item -LiteralPath $src -Destination $dst -Force
        Write-Host "  moved -> tools\$name"
    }
}

Get-ChildItem -LiteralPath $root -File -Filter "*.bat" | ForEach-Object {
    if ($_.Name -eq $launchName -or $_.Name -eq $updateName) { return }
    $dst = Join-Path $tools $_.Name
    if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Force }
    Move-Item -LiteralPath $_.FullName -Destination $dst -Force
    Write-Host "  moved -> tools\$($_.Name)"
}

# Patch moved updaters / portable shim so tools\ is not mistaken for package root.
foreach ($rel in @(
    "tools\Update-Next-Trainer.bat",
    "tools\Update-Next-Trainer-Release.bat"
)) {
    $path = Join-Path $root $rel
    if (-not (Test-Path -LiteralPath $path)) { continue }
    $text = [System.IO.File]::ReadAllText($path)
    $marker = 'if not exist "%PORTABLE_ROOT%Next-Trainer\" if exist "%~dp0..\Next-Trainer\"'
    if ($text -notlike "*$marker*") {
        $old = 'set "PORTABLE_ROOT=%~dp0"' + "`r`n" + 'for %%I in ("%~dp0.") do set "PORTABLE_ROOT_PS=%%~fI"'
        $new = @(
            'set "PORTABLE_ROOT=%~dp0"'
            'if not exist "%PORTABLE_ROOT%Next-Trainer\" if exist "%~dp0..\Next-Trainer\" ('
            '    for %%I in ("%~dp0..") do set "PORTABLE_ROOT=%%~fI\"'
            ')'
            'for %%I in ("%PORTABLE_ROOT%.") do set "PORTABLE_ROOT_PS=%%~fI"'
        ) -join "`r`n"
        if ($text.Contains($old)) {
            $text = $text.Replace($old, $new)
            [System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding $false))
            Write-Host "  patched $rel (PORTABLE_ROOT parent fallback)"
        } else {
            Write-Host "  WARNING: could not patch $rel (unexpected content)" -ForegroundColor Yellow
        }
    }
}

$portableShim = @"
@echo off
set "PORTABLE_ROOT=%~dp0"
if not exist "%PORTABLE_ROOT%Next-Trainer\scripts\portable\launch_portable.bat" if exist "%~dp0..\Next-Trainer\scripts\portable\launch_portable.bat" (
    for %%I in ("%~dp0..") do set "PORTABLE_ROOT=%%~fI\"
)
call "%PORTABLE_ROOT%Next-Trainer\scripts\portable\launch_portable.bat" %*
exit /b %errorlevel%
"@
$shimPath = Join-Path $tools "run_gui_portable.bat"
[System.IO.File]::WriteAllText($shimPath, ($portableShim -replace "`r?`n", "`r`n"), (New-Object System.Text.UTF8Encoding $false))
Write-Host "  wrote tools\run_gui_portable.bat (root-aware)"

$runGuiFixed = @"
@echo off
chcp 65001 >nul 2>&1
set "PORTABLE_ROOT=%~dp0"
if not exist "%PORTABLE_ROOT%python_embeded\python.exe" if exist "%~dp0..\python_embeded\python.exe" (
    for %%I in ("%~dp0..") do set "PORTABLE_ROOT=%%~fI\"
)
cd /d "%PORTABLE_ROOT%"
if exist "python_embeded\python.exe" if exist "Next-Trainer\gui.py" (
    if exist "Next-Trainer\scripts\portable\launch_portable.bat" (
        call "%PORTABLE_ROOT%Next-Trainer\scripts\portable\launch_portable.bat" %*
        exit /b %errorlevel%
    )
    if exist "tools\run_gui_portable.bat" (
        call "%PORTABLE_ROOT%tools\run_gui_portable.bat" %*
        exit /b %errorlevel%
    )
    echo [ERROR] Portable launcher missing.
    pause
    exit /b 1
)
echo [ERROR] No launcher found. Please make sure the package is fully extracted.
pause
exit /b 1
"@
$runGuiPath = Join-Path $tools "run_gui.bat"
[System.IO.File]::WriteAllText($runGuiPath, ($runGuiFixed -replace "`r?`n", "`r`n"), (New-Object System.Text.UTF8Encoding $false))
Write-Host "  wrote tools\run_gui.bat (root-aware)"

# 启动.bat must call launch_portable from package root — NOT tools\run_gui.bat
# (run_gui.bat uses %~dp0 as package root and breaks when moved under tools\).
$launch = @"
@echo off
chcp 65001 >nul 2>&1
title Next Trainer
cd /d "%~dp0"

if exist "Next-Trainer\scripts\portable\launch_portable.bat" (
    call "Next-Trainer\scripts\portable\launch_portable.bat" %*
    exit /b %errorlevel%
)
if exist "tools\run_gui_portable.bat" (
    call "tools\run_gui_portable.bat" %*
    exit /b %errorlevel%
)
echo [ERROR] Portable launcher missing. Check Next-Trainer\scripts\portable\launch_portable.bat
pause
exit /b 1
"@

$update = @"
@echo off
chcp 65001 >nul 2>&1
title Next Trainer - Update
cd /d "%~dp0"

if exist "tools\Update-Next-Trainer.bat" (
    call "tools\Update-Next-Trainer.bat" %*
    if errorlevel 1 (
        echo.
        echo Git update failed. Try: tools\Update-Next-Trainer-Release.bat
        echo Deps broken? Try: update\update_dependencies.bat
        pause
    )
    exit /b %errorlevel%
)
echo [ERROR] missing tools\Update-Next-Trainer.bat
pause
exit /b 1
"@

$utf8 = New-Object System.Text.UTF8Encoding $false
$utf8bom = New-Object System.Text.UTF8Encoding $true
$launchPath = Join-Path $root $launchName
$updatePath = Join-Path $root $updateName
$readmePath = Join-Path $root $readmeName

[System.IO.File]::WriteAllText($launchPath, ($launch -replace "`r?`n", "`r`n"), $utf8)
[System.IO.File]::WriteAllText($updatePath, ($update -replace "`r?`n", "`r`n"), $utf8)

$readmeTemplate = Join-Path $PSScriptRoot "templates\shuoming.txt"
if (-not (Test-Path -LiteralPath $readmeTemplate)) {
    $readmeTemplate = Join-Path $PSScriptRoot "templates\$readmeName"
}
if (Test-Path -LiteralPath $readmeTemplate) {
    $readmeBody = [System.IO.File]::ReadAllText($readmeTemplate, (New-Object System.Text.UTF8Encoding $true))
    $readmeBody = $readmeBody -replace "`r?`n", "`r`n"
    if (-not $readmeBody.EndsWith("`r`n")) { $readmeBody += "`r`n" }
    [System.IO.File]::WriteAllText($readmePath, $readmeBody, $utf8bom)
} else {
    Write-Host "  WARNING: missing templates\shuoming.txt; wrote placeholder $readmeName" -ForegroundColor Yellow
    [System.IO.File]::WriteAllText($readmePath, "Next Trainer`r`n", $utf8bom)
}

Write-Host "  wrote $launchName / $updateName / $readmeName" -ForegroundColor Green
Write-Host "Root2026 apply done: $root"
