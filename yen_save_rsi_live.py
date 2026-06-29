import psycopg2
from datetime import datetime, timezone

conn = psycopg2.connect(host='localhost', port=5432, dbname='agentdb', user='postgres', password='1870506303979')
cur = conn.cursor()

# Signals from RSI strategy run at 2026-03-31T07:36 UTC
signals = [
    {
        "coin": "BTC",
        "action": "HOLD",
        "confidence": 0.06,
        "reason": "RSI(15m) 41.4 — neutral zone | 1h≈43.5",
    },
    {
        "coin": "ETH",
        "action": "HOLD",
        "confidence": 0.091,
        "reason": "RSI(15m) 37.0 — neutral zone | 1h≈47.1",
    },
    {
        "coin": "SOL",
        "action": "BUY",
        "confidence": 0.219,
        "reason": "RSI(15m) 34.7 oversold — 1h approaching (1h≈43.8)",
    },
]

for s in signals:
    cur.execute(
        "INSERT INTO reuben_signals (symbol, signal_type, source, confidence, notes) VALUES (%s, %s, %s, %s, %s)",
        (
            s['coin'] + "USDT",
            s['action'],
            "rsi_mean_reversion",
            s['confidence'],
            s['reason']
        )
    )
    print(f"[+] Saved {s['coin']} {s['action']} conf={s['confidence']}")

conn.commit()
conn.close()
print("Done.")
