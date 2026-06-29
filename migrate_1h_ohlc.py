#!/usr/bin/env python3
"""Add OHLC columns to trading_prices_1h table."""

import sys
sys.path.insert(0, r"D:\dev\trading")
from db import get_conn

def migrate():
    conn = get_conn()
    cur = conn.cursor()
    
    # Add columns to trading_prices_1h
    alter_sql = """
        ALTER TABLE trading_prices_1h 
        ADD COLUMN IF NOT EXISTS high_price NUMERIC(20,8),
        ADD COLUMN IF NOT EXISTS low_price NUMERIC(20,8),
        ADD COLUMN IF NOT EXISTS open_price NUMERIC(20,8);
    """
    
    print("Adding OHLC columns to trading_prices_1h...")
    cur.execute(alter_sql)
    conn.commit()
    
    # Verify
    print("\nColumns in trading_prices_1h:")
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name='trading_prices_1h' 
        ORDER BY ordinal_position
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")
    
    conn.close()
    print("\nSchema update complete!")

if __name__ == "__main__":
    migrate()
