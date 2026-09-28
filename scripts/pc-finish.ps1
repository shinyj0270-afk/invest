param([switch]$RunTests)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Project venv is missing.' }
& $python (Join-Path $project 'tools\pc_check.py') --phase finish
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
if ($RunTests) {
    Push-Location $project
    try {
        $fullVerifier = Join-Path $project 'tools\verify_all.py'
        $verifier = if (Test-Path -LiteralPath $fullVerifier) { 'tools\verify_all.py' } else { 'tools\verify_portable.py' }
        & $python $verifier
        $testExit = $LASTEXITCODE
    } finally { Pop-Location }
    exit $testExit
}
