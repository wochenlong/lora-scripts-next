# Shared build gate: the dictionary is a public bundle, never a runtime-data copy.
# This step uses only Python's standard library and must not change site-packages.
function Invoke-PortableTagDictionary {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$PythonExe,
        [Parameter(Mandatory = $true)][string]$TrainerDir,
        [ValidateSet("Prepare", "Verify")][string]$Mode = "Prepare",
        [string]$Manifest = ""
    )

    $dictionaryScript = Join-Path $TrainerDir "scripts\prefetch_tag_dictionary.py"
    $dictionaryDir = Join-Path $TrainerDir "assets\tag_translation\danbooru"
    if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
        throw "Dictionary bundle requires the package Python: $PythonExe"
    }
    if (-not (Test-Path -LiteralPath $dictionaryScript -PathType Leaf)) {
        throw "Dictionary bundle script missing: $dictionaryScript"
    }

    $dictionaryArgs = @("-S", $dictionaryScript, "--directory", $dictionaryDir, "--strict")
    if ($Mode -eq "Prepare") {
        $dictionaryArgs += "--if-missing"
    } else {
        $dictionaryArgs += "--verify-only"
    }
    if ($Manifest) { $dictionaryArgs += @("--manifest", $Manifest) }

    $previousPreference = $ErrorActionPreference
    try {
        # Windows PowerShell treats native stderr as an ErrorRecord. Preserve
        # the CLI's diagnostics and then fail on its explicit exit status.
        $ErrorActionPreference = "Continue"
        & $PythonExe @dictionaryArgs
        $dictionaryExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($dictionaryExit -ne 0) {
        throw "Tag dictionary bundle $Mode failed (exit $dictionaryExit); no release archive may be produced."
    }
}
