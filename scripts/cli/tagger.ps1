$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
Set-Location $RepoRoot

if (-not $Env:HF_HOME) {
  $Env:HF_HOME = "huggingface"
}

if ($Env:USE_CN_MIRROR -and -not $Env:HF_ENDPOINT) {
  $Env:HF_ENDPOINT = "https://hf-mirror.com"
}

$VenvPython = Join-Path $RepoRoot "venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
  & $VenvPython -m mikazuki.tagger.cli @args
} else {
  python -m mikazuki.tagger.cli @args
}
