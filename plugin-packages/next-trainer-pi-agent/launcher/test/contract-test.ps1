# Launcher contract test (manual): READY line, /health token, uiUrl, parent-monitor cleanup.
param(
    [string]$DataRoot = (Join-Path $env:TEMP ("nt-pi-launcher-test-" + [guid]::NewGuid().ToString("N").Substring(0, 8)))
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # plugin package root
$exe = Join-Path $root "bin\next-trainer-pi-agent.exe"
if (-not (Test-Path $exe)) { throw "launcher exe missing: $exe" }

New-Item -ItemType Directory -Force $DataRoot | Out-Null
$outFile = Join-Path $DataRoot "stdout.log"
$token = "a" + "b" * 43

# A stand-in host process to act as the parent (use the bundled runtime: the
# controlled launch environment has no guaranteed node on PATH).
$bundledNode = Join-Path $root "runtime\node\node.exe"
$hostProc = Start-Process -FilePath $bundledNode -ArgumentList "-e","setInterval(()=>{},1000)" -PassThru -WindowStyle Hidden

$env:NEXT_TRAINER_SIDECAR_PORT = "0"
$env:NEXT_TRAINER_SIDECAR_TOKEN = $token
$env:NEXT_TRAINER_HOST_TOOL_TOKEN = ("c" * 44)
$env:NEXT_TRAINER_PLUGIN_DATA_ROOT = $DataRoot
$env:NEXT_TRAINER_PARENT_PID = "$($hostProc.Id)"

$launcher = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden -RedirectStandardOutput $outFile
$readyLine = $null
$deadline = (Get-Date).AddSeconds(90)
while ((Get-Date) -lt $deadline) {
    if (Test-Path $outFile) {
        $lines = Get-Content $outFile -ErrorAction SilentlyContinue
        $readyLine = $lines | Where-Object { $_ -match '"type":"READY"' } | Select-Object -First 1
    }
    if ($readyLine) { break }
    Start-Sleep -Milliseconds 300
}
if (-not $readyLine) { throw "no READY line within 90s" }
$ready = $readyLine | ConvertFrom-Json
"READY: $($readyLine)"
if ($ready.type -ne "READY" -or $ready.host -ne "127.0.0.1" -or $ready.protocolVersion -ne "1") { throw "bad READY payload" }
if (-not ($ready.port -gt 0)) { throw "bad READY port" }
if ($ready.uiUrl -notmatch '^http://127\.0\.0\.1:\d+$') { throw "bad uiUrl: $($ready.uiUrl)" }

# health with correct token
$h = Invoke-WebRequest -Uri "http://127.0.0.1:$($ready.port)/health" -Headers @{ Authorization = "Bearer $token" } -UseBasicParsing
"health ok: $($h.StatusCode) $($h.Content)"
if ($h.Content -notmatch '"status":"ok"') { throw "health not ok" }

# health with wrong token
try {
    Invoke-WebRequest -Uri "http://127.0.0.1:$($ready.port)/health" -Headers @{ Authorization = "Bearer wrongwrongwrongwrongwrongwrongwrongwro" } -UseBasicParsing
    throw "expected 401"
} catch {
    if ($_.Exception.Response.StatusCode.value__ -ne 401) { throw "expected 401, got $($_.Exception.Response.StatusCode.value__)" }
    "health unauthorized: 401 (correct)"
}

# uiUrl serves pi-web HTML
$ui = Invoke-WebRequest -Uri $ready.uiUrl -UseBasicParsing
"ui: $($ui.StatusCode) length=$($ui.Content.Length)"
if ($ui.StatusCode -ne 200 -or $ui.Content.Length -lt 1000) { throw "ui not serving pi-web" }

# sessions API
$sess = Invoke-WebRequest -Uri "$($ready.uiUrl)/api/sessions" -UseBasicParsing
"sessions: $($sess.StatusCode) $($sess.Content)"

# Parent (host) dies -> launcher must kill the pi-web tree and exit.
$childPid = [int]$ready.childPid
Stop-Process -Id $hostProc.Id -Force
$killed = $false
$deadline2 = (Get-Date).AddSeconds(20)
while ((Get-Date) -lt $deadline2) {
    $proc = Get-Process -Id $childPid -ErrorAction SilentlyContinue
    if (-not $proc) { $killed = $true; break }
    Start-Sleep -Milliseconds 300
}
if (-not $killed) { throw "pi-web child (pid $childPid) still alive after parent exit" }
"parent-monitor: pi-web tree removed (correct)"

$launcherExited = $false
$deadline3 = (Get-Date).AddSeconds(10)
while ((Get-Date) -lt $deadline3 -and -not $launcherExited) {
    $lp = Get-Process -Id $launcher.Id -ErrorAction SilentlyContinue
    if (-not $lp) { $launcherExited = $true }
    Start-Sleep -Milliseconds 300
}
if (-not $launcherExited) { throw "launcher did not exit after parent exit" }
"launcher exited (correct)"

# Any leftover node processes for this data root?
$leftovers = Get-CimInstance Win32_Process -Filter "Name='node.exe'" | Where-Object { $_.CommandLine -match [regex]::Escape($DataRoot) }
"leftover node procs referencing data root: $($leftovers.Count)"
if ($leftovers.Count -gt 0) { throw "orphan pi-web processes remain" }

Remove-Item $DataRoot -Recurse -Force -ErrorAction SilentlyContinue
"CONTRACT TEST PASSED"
