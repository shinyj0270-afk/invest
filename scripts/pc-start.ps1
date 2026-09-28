$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Create this PC project venv first; see docs/DUAL_PC_WORKFLOW.md.' }
& $python (Join-Path $project 'tools\pc_check.py') --phase start
exit $LASTEXITCODE
