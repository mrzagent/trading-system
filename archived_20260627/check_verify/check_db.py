import psycopg2
import os
from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/.openclaw/.env'))

conn = psycopg2.connect(
    host='localhost',
    database='agentdb',
    user='postgres',
    password='1870506303979'
)
cur = conn.cursor()

# Check trading_account table
cur.execute('SELECT * FROM trading_account LIMIT 1')
row = cur.fetchone()
if row:
    print('trading_account columns:', [desc[0] for desc in cur.description])
    print('Row:', row)
else:
    print('No rows in trading_account')

cur.close()
conn.close()
