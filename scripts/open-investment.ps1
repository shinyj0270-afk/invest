param([int]$Port = 8767, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
if ($Port -lt 1 -or $Port -gt 65535) { throw '올바른 포트 번호를 입력하세요.' }
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonExe)) { throw '이 PC의 INVESTMENT 실행 환경을 먼저 준비하세요.' }
$launcherArgs = @((Join-Path $projectDir 'tools\open_dashboard.py'), '--port', "$Port")
if ($NoBrowser) { $launcherArgs += '--no-browser' }
& $pythonExe @launcherArgs
exit $LASTEXITCODE
