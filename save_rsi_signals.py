import sys, json
from datetime import datetime
sys.path.insert(0, 'D:/dev/trading')
import db

signals = [
    {
        'symbol': 'BTC',
        'signal_type': 'RSI_HOLD',
        'source': 'Yen',
        'confidence': 0.07,
        'notes': 'RSI 58.9 — neutral zone | price=67567.0 | lean=SELL | candle=2026-03-30T12:30:00+00:00'
    },
    {
        'symbol': 'ETH',
        'signal_type': 'RSI_SELL',
        'source': 'Yen',
        'confidence': 0.8439,
        'notes': 'RSI 72.8 — overbought (threshold 65.0) | price=2065.51 | sustained=true | candle=2026-03-30T12:30:00+00:00'
    },
    {
        'symbol': 'SOL',
        'signal_type': 'RSI_HOLD',
        'source': 'Yen',
        'confidence': 0.07,
        'notes': 'RSI 58.3 — neutral zone | price=84.12 | lean=SELL | candle=2026-03-30T12:30:00+00:00'
    },
]

conn = db.get_conn()
cur = conn.cursor()
for s in signals:
    cur.execute(
        "INSERT INTO reuben_signals (symbol, signal_type, source, confidence, notes) VALUES (%s, %s, %s, %s, %s)",
        (s['symbol'], s['signal_type'], s['source'], s['confidence'], s['notes'])
    )
conn.commit()
conn.close()
print(f"Saved {len(signals)} RSI signals to reuben_signals")
