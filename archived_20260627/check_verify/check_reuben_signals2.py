import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='agentdb',
    user='postgres',
    password='1870506303979'
)
cur = conn.cursor()

# Check latest signals
cur.execute("SELECT symbol, signal_type, confidence, source, created_at FROM reuben_signals ORDER BY created_at DESC LIMIT 5")
signals = cur.fetchall()
print("Latest 5 reuben_signals:")
for s in signals:
    print(f"  {s[0]} {s[1]} {s[2]*100:.0f}% | {s[3]} | {s[4]}")

cur.close()
conn.close()
