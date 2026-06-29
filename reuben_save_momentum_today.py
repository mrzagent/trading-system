import sys
sys.path.insert(0, 'D:/dev/trading')
import db

# Check which DB we're connected to
conn = db.get_conn()
cur = conn.cursor()
cur.execute("SELECT current_database()")
print("Connected DB:", cur.fetchone())

# List tables in this DB
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)

# Check if reuben_signals exists
if 'reuben_signals' not in tables:
    print("ERROR: reuben_signals table not found in this DB!")
    conn.close()
    sys.exit(1)

signals = [
    {
        'symbol': 'BTC',
        'signal_type': 'MOMENTUM_SELL',
        'source': 'Reuben',
        'confidence': 0.265036,
        'notes': 'Momentum -3.67%, 24h -2.2% - downtrend confirmed | price=66253.0 candle=2026-03-31T06:25:00+00:00'
    },
    {
        'symbol': 'ETH',
        'signal_type': 'MOMENTUM_SELL',
        'source': 'Reuben',
        'confidence': 0.230598,
        'notes': 'Momentum -3.07%, 24h -2.3% - downtrend confirmed | price=1996.64 candle=2026-03-31T06:25:00+00:00'
    },
    {
        'symbol': 'SOL',
        'signal_type': 'MOMENTUM_SELL',
        'source': 'Reuben',
        'confidence': 0.328038,
        'notes': 'Momentum -4.69%, 24h -2.3% - downtrend confirmed | price=83.0 candle=2026-03-31T06:25:00+00:00'
    },
]

for s in signals:
    cur.execute(
        'INSERT INTO reuben_signals (symbol, signal_type, source, confidence, notes) VALUES (%s, %s, %s, %s, %s)',
        (s['symbol'], s['signal_type'], s['source'], s['confidence'], s['notes'])
    )
conn.commit()
conn.close()
print(f'Saved {len(signals)} momentum signals to reuben_signals')
