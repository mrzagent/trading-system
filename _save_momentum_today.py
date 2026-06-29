import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='agentdb', user='postgres', password='1870506303979')
cur = conn.cursor()

signals = [
    ('BTC', 'MOMENTUM_SELL', 'Reuben', 0.265314,
     'Momentum -3.67%, 24h -2.2% - downtrend confirmed | price=66345.0 candle=2026-03-31T06:20:00+00:00'),
    ('ETH', 'MOMENTUM_SELL', 'Reuben', 0.231256,
     'Momentum -3.07%, 24h -2.3% - downtrend confirmed | price=1996.75 candle=2026-03-31T06:20:00+00:00'),
    ('SOL', 'MOMENTUM_SELL', 'Reuben', 0.321982,
     'Momentum -4.69%, 24h -2.0% - downtrend confirmed | price=83.06 candle=2026-03-31T06:20:00+00:00'),
]

for s in signals:
    cur.execute(
        "INSERT INTO reuben_signals (symbol, signal_type, source, confidence, notes) VALUES (%s, %s, %s, %s, %s)",
        s
    )

conn.commit()
conn.close()
print(f"Saved {len(signals)} momentum signals to reuben_signals (agentdb)")
