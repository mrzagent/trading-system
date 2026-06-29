import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='agentdb',
    user='postgres',
    password='1870506303979'
)
cur = conn.cursor()

# Check schema
cur.execute("SELECT * FROM reuben_signals LIMIT 1")
cur.fetchone()
col_names = [desc[0] for desc in cur.description]
print("reuben_signals columns:", col_names)

# Check latest signals
cur.execute("SELECT coin, action, confidence, strategy, created_at FROM reuben_signals ORDER BY created_at DESC LIMIT 5")
signals = cur.fetchall()
print("\nLatest 5 signals:")
for s in signals:
    print(f"  {s[0]} {s[1]} {s[2]*100:.0f}% | {s[3]} | {s[4]}")

cur.close()
conn.close()
