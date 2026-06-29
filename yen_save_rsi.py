import sys
import json
from datetime import datetime, timezone

sys.path.insert(0, 'D:\\dev\\trading')
from db import get_conn

# Signals from strategy_rsi.py output
signals = [
    {
        "coin": "BTC",
        "action": "BUY",
        "confidence": 0.431,
        "reason": "RSI(15m) 31.4 oversold — 1h approaching (1h≈37.9)",
        "rsi_15m": 31.45,
        "rsi_1h": 37.89,
        "price": 67189.0,
        "candle": "2026-03-31T07:15:00+00:00"
    },
    {
        "coin": "ETH",
        "action": "BUY",
        "confidence": 0.549,
        "reason": "RSI(15m) 29.6 oversold — 1h approaching (1h≈39.6)",
        "rsi_15m": 29.63,
        "rsi_1h": 39.64,
        "price": 2047.63,
        "candle": "2026-03-31T07:15:00+00:00"
    },
    {
        "coin": "SOL",
        "action": "HOLD",
        "confidence": 0.077,
        "reason": "RSI(15m) 39.1 — neutral zone | 1h≈39.9",
        "rsi_15m": 39.07,
        "rsi_1h": 39.91,
        "price": 83.02,
        "candle": "2026-03-31T07:15:00+00:00"
    }
]

conn = get_conn()
cur = conn.cursor()

# Check schema
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='reuben_signals' ORDER BY ordinal_position")
cols = cur.fetchall()
print("Schema:", cols)

# Insert only actionable signals (BUY/SELL), log all
for s in signals:
    try:
        cur.execute(
            """INSERT INTO reuben_signals 
               (symbol, signal_type, source, confidence, notes)
               VALUES (%s, %s, %s, %s, %s)""",
            (
                s['coin'] + "USDT",
                s['action'],
                "rsi_mean_reversion",
                s['confidence'],
                s['reason']
            )
        )
        print(f"[+] Saved {s['coin']} {s['action']} @ conf={s['confidence']}")
    except Exception as e:
        print(f"[!] Error saving {s['coin']}: {e}")
        # Try alternate schema
        conn.rollback()
        break

conn.commit()
conn.close()
print("Done.")
