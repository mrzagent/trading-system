Set-Location D:\dev\trading
python orchestrator.py --json-only 2>&1 | Out-File -Append D:\dev\trading\orchestrator.log
