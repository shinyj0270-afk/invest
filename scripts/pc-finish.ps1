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
        & $python 'tools\validate_share_candidates.py' --ui
        $testExit = $LASTEXITCODE
    } finally { Pop-Location }
    exit $testExit
}
