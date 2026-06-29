import psycopg2
from datetime import datetime, timezone

# Connect to agentdb where reuben_signals lives
conn = psycopg2.connect(host='localhost', port=5432, dbname='agentdb', user='postgres', password='1870506303979')
cur = conn.cursor()

# Check schema
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='reuben_signals' ORDER BY ordinal_position")
cols = cur.fetchall()
print("Schema:", cols)

# Signals from RSI strategy run at 2026-03-31T07:19 UTC
signals = [
    {
        "coin": "BTC",
        "action": "BUY",
        "confidence": 0.431,
        "reason": "RSI(15m) 31.4 oversold — 1h approaching (1h≈37.9)",
    },
    {
        "coin": "ETH",
        "action": "BUY",
        "confidence": 0.549,
        "reason": "RSI(15m) 29.6 oversold — 1h approaching (1h≈39.6)",
    },
    {
        "coin": "SOL",
        "action": "HOLD",
        "confidence": 0.077,
        "reason": "RSI(15m) 39.1 — neutral zone | 1h≈39.9",
    },
]

for s in signals:
    try:
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
    except Exception as e:
        conn.rollback()
        print(f"[!] Insert failed for {s['coin']}: {e}")
        # Try to get actual columns
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='reuben_signals'")
        actual_cols = [r[0] for r in cur.fetchall()]
        print(f"    Actual columns: {actual_cols}")
        break

conn.commit()
conn.close()
print("Done.")
