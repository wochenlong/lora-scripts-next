# Repair LF-only .bat files under a portable package root (Windows cmd requires CRLF).
param(
    [Parameter(Mandatory = $true)]
    [string]$PortableRoot
)

$ErrorActionPreference = "Stop"

function Normalize-PortableRootPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $Path }
    return $Path.Trim().Trim('"').TrimEnd('\', '/')
}

function Write-PortableBatchFile {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    $text = [System.IO.File]::ReadAllText($Source)
    $text = $text -replace "`r`n", "`n" -replace "`r", "`n" -replace "`n", "`r`n"
    # Strip UTF-8 BOM; cmd.exe treats BOM as part of "@echo off".
    if ($text.Length -gt 0 -and [int][char]$text[0] -eq 0xFEFF) {
        $text = $text.Substring(1)
    }
    [System.IO.File]::WriteAllText($Destination, $text, (New-Object System.Text.UTF8Encoding $false))
}

$PortableRoot = Normalize-PortableRootPath $PortableRoot
if (-not (Test-Path (Join-Path $PortableRoot "Next-Trainer\gui.py"))) {
    throw "Next-Trainer not found under: $PortableRoot"
}

$count = 0
Get-ChildItem -Path $PortableRoot -Filter "*.bat" -Recurse -File | ForEach-Object {
    $bytes = [System.IO.File]::ReadAllBytes($_.FullName)
    $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
    $lfOnly = ($bytes -contains 10) -and -not ($bytes -contains 13)
    if ($lfOnly -or $hasBom) {
        Write-PortableBatchFile -Source $_.FullName -Destination $_.FullName
        $reason = @()
        if ($lfOnly) { $reason += "LF-only" }
        if ($hasBom) { $reason += "UTF-8 BOM" }
        Write-Host ("  fixed ({0}): {1}" -f ($reason -join ", "), $_.FullName.Substring($PortableRoot.Length).TrimStart('\'))
        $script:count++
    }
}

if ($count -eq 0) {
    Write-Host "All .bat files already use CRLF without BOM."
} else {
    Write-Host "Repaired $count .bat file(s). Re-run Update-Next-Trainer-Release.bat."
}
