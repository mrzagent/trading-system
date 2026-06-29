import sys
sys.path.insert(0, 'D:/dev/trading')
import db

conn = db.get_conn()
cur = conn.cursor()
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
tables = [r[0] for r in cur.fetchall()]
conn.close()
print(tables)
