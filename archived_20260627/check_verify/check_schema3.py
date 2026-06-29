import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='agentdb',
    user='postgres',
    password='1870506303979'
)
cur = conn.cursor()

# List all tables
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
tables = cur.fetchall()
print("Tables:", [t[0] for t in tables])

# Check trading_signals
cur.execute("SELECT * FROM trading_signals LIMIT 1")
cur.fetchone()
col_names = [desc[0] for desc in cur.description]
print("\ntrading_signals columns:", col_names)

cur.close()
conn.close()
