import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='postgres',
    user='postgres',
    password='1870506303979'
)
cur = conn.cursor()

# List tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
tables = cur.fetchall()
print("Tables in postgres DB:")
for t in tables:
    print(f"  {t[0]}")

# Check trading_signals
cur.execute("SELECT * FROM trading_signals LIMIT 1")
cur.fetchone()
col_names = [desc[0] for desc in cur.description]
print(f"\ntrading_signals columns: {col_names}")

# Latest signals
cur.execute("SELECT coin, action, confidence, strategy, created_at FROM trading_signals ORDER BY created_at DESC LIMIT 5")
signals = cur.fetchall()
print("\nLatest 5 trading_signals:")
for s in signals:
    print(f"  {s[0]} {s[1]} {s[2]*100:.0f}% | {s[3]} | {s[4]}")

cur.close()
conn.close()
