Set-Location D:\dev\trading
python candle_collector.py --timeframe 4h 2>&1 | Out-File -Append D:\dev\trading\collector_4h.log
