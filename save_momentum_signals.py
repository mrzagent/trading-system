import sys, json
sys.path.insert(0, 'D:/dev/trading')
import db

signals = [
    {
        'symbol': 'BTC',
        'signal_type': 'MOMENTUM_SELL',
        'source': 'Reuben',
        'confidence': 0.252582,
        'notes': 'Momentum -3.40%, 24h -2.4% - downtrend confirmed | price=67762.0'
    },
    {
        'symbol': 'ETH',
        'signal_type': 'MOMENTUM_SELL',
        'source': 'Reuben',
        'confidence': 0.308146,
        'notes': 'Momentum -4.56%, 24h -1.7% - downtrend confirmed | price=2045.66'
    },
    {
        'symbol': 'SOL',
        'signal_type': 'MOMENTUM_SELL',
        'source': 'Reuben',
        'confidence': 0.457538,
        'notes': 'Momentum -6.37%, 24h -3.8% - downtrend confirmed | price=85.01'
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
print(f"Saved {len(signals)} momentum signals to reuben_signals")
