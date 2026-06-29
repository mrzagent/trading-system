import psycopg2

conn = psycopg2.connect(dbname='agentdb', user='postgres', password='1870506303979', host='localhost', port=5432)
cur = conn.cursor()

# Check tables
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
tables = [r[0] for r in cur.fetchall()]
print("Tables in agentdb:", tables)

if 'reuben_signals' not in tables:
    print("reuben_signals not found in agentdb either!")
    conn.close()
    exit(1)

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
print(f'Saved {len(signals)} momentum signals to reuben_signals in agentdb')
