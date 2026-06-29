#!/usr/bin/env python3
"""Check database for Mean Reversion strategy data availability."""

import sys
sys.path.insert(0, r"D:\dev\trading")
from db import get_conn, COINS

def check_tables():
    conn = get_conn()
    cur = conn.cursor()
    
    # Check for all price-related tables
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema='public' AND table_name LIKE '%price%'
        ORDER BY table_name
    """)
    tables = cur.fetchall()
    print("Price tables found:")
    for t in tables:
        print(f"  - {t[0]}")
    
    # Check row counts for each timeframe table
    for table in ['trading_prices', 'trading_prices_1h', 'trading_prices_4h']:
        print(f"\n--- {table} ---")
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            print(f"Total rows: {count}")
            
            if count > 0:
                cur.execute(f"SELECT coin, COUNT(*) FROM {table} GROUP BY coin ORDER BY coin")
                by_coin = cur.fetchall()
                print("Rows by coin:")
                for coin, c in by_coin:
                    print(f"  {coin}: {c} rows")
                
                # Check latest timestamp
                cur.execute(f"SELECT MAX(captured_at) FROM {table}")
                latest = cur.fetchone()[0]
                print(f"Latest data: {latest}")
                
                # Check schema
                cur.execute(f"""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = '{table}'
                    ORDER BY ordinal_position
                """)
                cols = cur.fetchall()
                print(f"Columns: {[c[0] for c in cols]}")
            else:
                print("  (empty table)")
                
        except Exception as e:
            print(f"  Error: {e}")
    
    conn.close()

if __name__ == "__main__":
    check_tables()
