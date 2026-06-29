import re
with open('backtest_pullback_scalper_15min.py', 'r') as f:
    content = f.read()
content = content.replace('"password": "***"', '"password": "***"')
with open('backtest_pullback_scalper_15min.py', 'w') as f:
    f.write(content)
print('Updated')
