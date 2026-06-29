import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='agentdb',
    user='postgres',
    password='1870506303979'
)
cur = conn.cursor()

cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name")
tables = cur.fetchall()
print("All tables:")
for t in tables:
    print(f"  {t[0]}")

# Look for trading-related tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name LIKE '%signal%'")
signal_tables = cur.fetchall()
print("\nSignal tables:")
for t in signal_tables:
    print(f"  {t[0]}")

cur.close()
conn.close()
