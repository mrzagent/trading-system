#!/usr/bin/env python3
"""Create 15min candles from 5min candles for BTC."""
import psycopg2
import pandas as pd

DB_CONFIG = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "1870506303979",
    "host": "localhost",
    "port": 5432
}

def create_15min_table():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    # Create table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS binance_btc_15min (
            open_time TIMESTAMP WITH TIME ZONE PRIMARY KEY,
            open_price NUMERIC NOT NULL,
            high_price NUMERIC NOT NULL,
            low_price NUMERIC NOT NULL,
            close_price NUMERIC NOT NULL,
            volume NUMERIC NOT NULL,
            quote_volume NUMERIC,
            trades_count INTEGER
        )
    """)
    conn.commit()
    
    # Fetch 5min data
    print("Fetching 5min data...")
    cur.execute("""
        SELECT open_time, open_price, high_price, low_price, close_price, volume, quote_volume, trades_count
        FROM binance_btc_5min
        ORDER BY open_time ASC
    """)
    
    rows = cur.fetchall()
    print(f"Loaded {len(rows)} 5min candles")
    
    # Convert to DataFrame
    df = pd.DataFrame(rows, columns=['open_time', 'open_price', 'high_price', 'low_price', 'close_price', 'volume', 'quote_volume', 'trades_count'])
    
    # Convert to numeric
    for col in ['open_price', 'high_price', 'low_price', 'close_price', 'volume', 'quote_volume']:
        df[col] = pd.to_numeric(df[col])
    
    # Resample to 15min
    print("Resampling to 15min...")
    df['open_time'] = pd.to_datetime(df['open_time'], utc=True)
    df.set_index('open_time', inplace=True)
    
    df_15m = df.resample('15min').agg({
        'open_price': 'first',
        'high_price': 'max',
        'low_price': 'min',
        'close_price': 'last',
        'volume': 'sum',
        'quote_volume': 'sum',
        'trades_count': 'sum'
    }).dropna()
    
    print(f"Created {len(df_15m)} 15min candles")
    
    # Insert into database
    print("Inserting into database...")
    for idx, row in df_15m.iterrows():
        cur.execute("""
            INSERT INTO binance_btc_15min (open_time, open_price, high_price, low_price, close_price, volume, quote_volume, trades_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (open_time) DO NOTHING
        """, (idx, float(row['open_price']), float(row['high_price']), float(row['low_price']), float(row['close_price']), 
              float(row['volume']), float(row['quote_volume']) if pd.notna(row['quote_volume']) else None, 
              int(row['trades_count']) if pd.notna(row['trades_count']) else None))
    
    conn.commit()
    cur.close()
    conn.close()
    print("Done!")

if __name__ == "__main__":
    create_15min_table()
