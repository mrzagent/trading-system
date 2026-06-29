import psycopg2

conn = psycopg2.connect(host='localhost', port=5432, dbname='agentdb', user='postgres', password='1870506303979')
cur = conn.cursor()

signals = [
    {"coin": "BTC", "action": "BUY", "confidence": 0.394, "reason": "RSI(15m) 32.0 oversold - 1h approaching (1h~39.7)"},
    {"coin": "ETH", "action": "BUY", "confidence": 0.671, "reason": "RSI(15m) 27.8 oversold - 1h approaching (1h~42.6)"},
    {"coin": "SOL", "action": "BUY", "confidence": 0.463, "reason": "RSI(15m) 31.0 oversold - 1h approaching (1h~40.0)"},
]

for s in signals:
    cur.execute(
        "INSERT INTO reuben_signals (symbol, signal_type, source, confidence, notes) VALUES (%s, %s, %s, %s, %s)",
        (s["coin"] + "USDT", s["action"], "rsi_mean_reversion", s["confidence"], s["reason"])
    )
    print("[+] Saved " + s["coin"] + " " + s["action"] + " conf=" + str(s["confidence"]))

conn.commit()
conn.close()
print("Done.")
