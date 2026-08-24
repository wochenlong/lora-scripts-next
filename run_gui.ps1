# Prefer run_gui.bat on Windows (avoids execution policy issues).
# If you must run PowerShell directly, this wrapper dispatches to source/portable launchers.

Set-Location -LiteralPath $PSScriptRoot

if ((Test-Path -LiteralPath "python_embeded\python.exe") -and
    (Test-Path -LiteralPath "Next-Trainer\gui.py") -and
    (Test-Path -LiteralPath "run_gui_portable.bat")) {
    & ".\run_gui_portable.bat" @args
    exit $LASTEXITCODE
}

if (Test-Path -LiteralPath "run_gui_source.ps1") {
    & ".\run_gui_source.ps1" @args
    exit $LASTEXITCODE
}

Write-Host -ForegroundColor Red "[ERROR] No launcher found. Please make sure the package is fully extracted."
exit 1