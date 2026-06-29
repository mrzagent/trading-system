Set-Location D:\dev\trading
python candle_collector.py --timeframe 1h 2>&1 | Out-File -Append D:\dev\trading\collector_1h.log
