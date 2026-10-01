param([int]$Port = 8767)
$ErrorActionPreference = 'Stop'
if ($Port -lt 1 -or $Port -gt 65535) { throw '올바른 포트 번호를 입력하세요.' }
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $pythonExe)) { throw '이 PC의 INVESTMENT 실행 환경을 먼저 준비하세요.' }
try {
    $existing = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2 -UseBasicParsing
    if ($existing.Content -notmatch 'investment-holdings-sync') { throw '이 포트를 다른 프로그램이 사용 중입니다.' }
} catch {
    $live = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($live) { throw '이 포트에 기존 서버가 있습니다. 이전 서버를 종료하거나 다른 포트를 사용하세요.' }
    $dashboardScript = Join-Path $projectDir 'tools\serve_dashboard.py'
    Start-Process -FilePath $pythonExe -ArgumentList @(('"{0}"' -f $dashboardScript), '--saved-only', '--port', "$Port") -WorkingDirectory $projectDir -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 500
        try { $check = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2 -UseBasicParsing; break } catch {}
    }
    if (!$check -or $check.Content -notmatch 'investment-holdings-sync') { throw '동기화 앱을 열지 못했습니다. 실행 환경을 확인하세요.' }
}
Start-Process "http://127.0.0.1:$Port/"
