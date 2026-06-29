from db import get_conn, fetch_recent
conn = get_conn()
for tf in ['5min','1h','4h']:
    rows = fetch_recent(conn, 'BTC', limit=5, timeframe=tf)
    ts = rows[-1]['captured_at'] if rows else 'EMPTY'
    print(f'{tf}: {len(rows)} rows, latest={ts}')
conn.close()
