param([ValidateSet('home','work')][string]$Profile, [switch]$ConfirmRemoval)
$ErrorActionPreference = 'Stop'
if (-not $ConfirmRemoval -or -not $Profile) { throw '명시적 Profile 및 ConfirmRemoval 필요' }
foreach ($frequency in @('daily','weekly')) { Unregister-ScheduledTask -TaskName ('INVESTMENT-'+$Profile+'-'+$frequency) -Confirm }
