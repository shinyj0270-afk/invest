param([ValidateSet('home','work')][string]$Profile, [switch]$ConfirmRegistration)
$ErrorActionPreference = 'Stop'
if (-not $ConfirmRegistration -or -not $Profile) { throw '명시적 Profile 및 ConfirmRegistration 필요. 이 스크립트는 자동 실행하지 않습니다.' }
if ((Get-TimeZone).Id -ne 'Korea Standard Time') { throw 'Asia/Seoul 실행 시각을 위해 Windows 시간대 확인 필요. 시간대를 자동 변경하지 않습니다.' }
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$localConfig = Get-Content -LiteralPath (Join-Path $projectRoot 'config\local.json') -Raw | ConvertFrom-Json
if ($localConfig.profile -ne $Profile -or $localConfig.scheduled_jobs_enabled -ne $true) { throw 'Matching PC profile and scheduled_jobs_enabled=true required in local config.' }
foreach ($frequency in @('daily','weekly')) {
  $argument = '"' + (Join-Path $projectRoot 'batch.py') + '" ' + $frequency + ' --profile ' + $Profile + ' --mode user_input --scheduled'
  $action = New-ScheduledTaskAction -Execute $pythonPath -Argument $argument -WorkingDirectory $projectRoot
  $trigger = if ($frequency -eq 'daily') { New-ScheduledTaskTrigger -Daily -At '19:00' } else { New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At '10:00' }
  Register-ScheduledTask -TaskName ('INVESTMENT-'+$Profile+'-'+$frequency) -Action $action -Trigger $trigger -Description '저장 스냅샷 계산 전용. 휴일/정정 확인·새 수집은 별도.'
}
