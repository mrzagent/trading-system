import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='agentdb',
    user='postgres',
    password='1870506303979'
)
cur = conn.cursor()

cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'trading_signals'
    ORDER BY ordinal_position
""")

cols = cur.fetchall()
print("trading_signals columns:")
for col in cols:
    print(f"  {col[0]}: {col[1]}")

cur.close()
conn.close()
