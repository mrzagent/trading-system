# Register Position Monitor with Windows Task Scheduler
# Run this once to set up - zero token cost!

$Action = New-ScheduledTaskAction -Execute "D:\dev\trading\run_monitor.bat"

# Run every 5 minutes
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)

$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive

Register-ScheduledTask -TaskName "Reuben Position Monitor" -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force

Write-Host "Task registered successfully!" -ForegroundColor Green
Write-Host "The monitor will run every 5 minutes with ZERO token cost." -ForegroundColor Green
