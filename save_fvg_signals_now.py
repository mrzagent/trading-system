import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="agentdb",
    user="postgres",
    password="1870506303979"
)

signals = [
    {
        'symbol': 'BTC',
        'signal_type': 'FVG_SELL',
        'source': 'Virgil',
        'confidence': 0.9,
        'notes': 'Price 67,707.00 within 0.00% of bearish FVG mid 67,710.00 | fvg_top=67713.0 fvg_bottom=67707.0 formed_at=2026-03-30 08:30 UTC candle=2026-03-30T09:00:00+00:00'
    },
    {
        'symbol': 'ETH',
        'signal_type': 'FVG_BUY',
        'source': 'Virgil',
        'confidence': 0.81,
        'notes': 'Price 2,064.96 within 0.15% of bullish FVG mid 2,061.85 | fvg_top=2064.96 fvg_bottom=2058.74 formed_at=2026-03-30 08:30 UTC candle=2026-03-30T09:00:00+00:00'
    },
    {
        'symbol': 'SOL',
        'signal_type': 'FVG_BUY',
        'source': 'Virgil',
        'confidence': 0.81,
        'notes': 'Price 84.47 within 0.15% of bullish FVG mid 84.34 | fvg_top=84.47 fvg_bottom=84.22 formed_at=2026-03-30 08:30 UTC candle=2026-03-30T09:00:00+00:00'
    },
]

cur = conn.cursor()
for s in signals:
    cur.execute(
        "INSERT INTO reuben_signals (symbol, signal_type, source, confidence, notes) VALUES (%s, %s, %s, %s, %s)",
        (s['symbol'], s['signal_type'], s['source'], s['confidence'], s['notes'])
    )
conn.commit()
cur.close()
conn.close()
print(f"Saved {len(signals)} FVG signals to reuben_signals (agentdb)")
