#!/usr/bin/env python3
"""Check raw_data column for OHLC info."""

import sys
sys.path.insert(0, r"D:\dev\trading")
from db import get_conn
import json

conn = get_conn()
cur = conn.cursor()

for table in ['trading_prices_1h', 'trading_prices_4h']:
    print(f"\n=== {table} raw_data sample ===")
    cur.execute(f"""
        SELECT coin, captured_at, price, raw_data 
        FROM {table} 
        ORDER BY captured_at DESC 
        LIMIT 2
    """)
    rows = cur.fetchall()
    for row in rows:
        coin, ts, price, raw = row
        print(f"\n{coin} @ {ts}")
        print(f"  Price: {price}")
        if raw:
            try:
                data = json.loads(raw) if isinstance(raw, str) else raw
                print(f"  Raw keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
                if isinstance(data, dict):
                    for k in ['high', 'low', 'open', 'volume', 'highPrice', 'lowPrice', 'openPrice']:
                        if k in data:
                            print(f"    {k}: {data[k]}")
            except Exception as e:
                print(f"  Raw parse error: {e}")
        else:
            print("  No raw_data")

conn.close()
