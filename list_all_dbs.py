import psycopg2

conn = psycopg2.connect(dbname='postgres', user='postgres', password='1870506303979', host='localhost', port=5432)
cur = conn.cursor()
cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false ORDER BY datname")
dbs = [r[0] for r in cur.fetchall()]
print("All databases:", dbs)
conn.close()
