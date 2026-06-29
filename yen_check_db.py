import sys
sys.path.insert(0, 'D:\\dev\\trading')
from db import get_conn, DEFAULTS

print('DB config:', {k: v for k, v in DEFAULTS.items() if k != 'password'})
conn = get_conn()
cur = conn.cursor()
cur.execute("SELECT current_database()")
print('Connected DB:', cur.fetchone())
cur.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
print('Tables:', [r[0] for r in cur.fetchall()])
conn.close()
