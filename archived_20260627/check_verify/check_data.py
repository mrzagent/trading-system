from db import get_conn, fetch_recent, COINS

conn = get_conn()
print('Coins tracked:', COINS)
print()

for coin in COINS:
    for tf in ['5min', '1h', '4h']:
        try:
            rows = fetch_recent(conn, coin, limit=5, timeframe=tf)
            if rows:
                print(f'{coin} {tf}: {len(rows)} rows, latest: {rows[-1]["captured_at"]}')
            else:
                print(f'{coin} {tf}: 0 rows')
        except Exception as e:
            print(f'{coin} {tf}: ERROR - {e}')
    print()

conn.close()
