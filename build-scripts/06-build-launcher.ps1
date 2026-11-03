#Requires -Version 5.1
<#
.SYNOPSIS
  Compile the NextTrainer.exe launcher (NativeAOT) and place it at the portable
  package root, next to the existing .bat fallbacks (#435).
#>
param(
    [Parameter(Mandatory = $true)][string]$PackageRoot
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
$project = Join-Path $repoRoot "launcher"
$outDir = Join-Path $env:TEMP "nexttrainer-launcher"

$dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
if (-not $dotnet) {
    Write-Warning "dotnet SDK 未安装，跳过启动器编译（包内仍保留 .bat 入口）。请安装 .NET 9 SDK 后重跑。"
    return
}

& dotnet publish $project -c Release -r win-x64 -p:PublishAot=true -o $outDir
if ($LASTEXITCODE -ne 0) { throw "dotnet publish launcher failed (exit $LASTEXITCODE)" }

$exe = Join-Path $outDir "NextTrainer.exe"
if (-not (Test-Path $exe)) { throw "launcher exe missing after publish: $exe" }
Copy-Item -LiteralPath $exe -Destination (Join-Path $PackageRoot "NextTrainer.exe") -Force
Write-Host "  launcher -> $(Join-Path $PackageRoot 'NextTrainer.exe')"
