Set-Location D:\dev\trading
python candle_collector.py --timeframe 5min 2>&1 | Out-File -Append D:\dev\trading\collector_5min.log
