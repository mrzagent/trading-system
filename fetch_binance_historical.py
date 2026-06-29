#!/usr/bin/env python3
"""
fetch_binance_historical.py — Download 3+ years of BTC/USDT 1h candles from Binance.

Usage:
    python fetch_binance_historical.py

Stores data in:
    - PostgreSQL: binance_btc_1h table
    - CSV backup: D:\dev\trading\data\binance_btc_1h_YYYY-MM-DD.csv
"""

import os
import sys
import csv
import time
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any

import psycopg2
import psycopg2.extras

# ── Config ────────────────────────────────────────────────────────────────────
BINANCE_API = "https://api.binance.com/api/v3/klines"
SYMBOL = "BTCUSDT"
INTERVAL = "1h"
LIMIT_PER_REQUEST = 1000  # Binance max
YEARS_OF_DATA = 3

# Calculate start time (3 years ago)
END_TIME = int(datetime.now(timezone.utc).timestamp() * 1000)
START_TIME = END_TIME - (YEARS_OF_DATA * 365 * 24 * 60 * 60 * 1000)

# DB Config (from db.py pattern)
DB_DEFAULTS = {
    "dbname":   os.environ.get("DB_NAME",      "postgres"),
    "user":     os.environ.get("DB_USER",      "postgres"),
    "password": os.environ.get("DB_PASSWORD",  "1870506303979"),
    "host":     os.environ.get("DB_HOST",      "localhost"),
    "port":     int(os.environ.get("DB_PORT",  "5432")),
}

TABLE_NAME = "binance_btc_1h"
DATA_DIR = r"D:\dev\trading\data"

# ── Database Setup ────────────────────────────────────────────────────────────
CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
    id              SERIAL PRIMARY KEY,
    open_time       TIMESTAMPTZ NOT NULL,
    close_time      TIMESTAMPTZ NOT NULL,
    open_price      NUMERIC(20, 8) NOT NULL,
    high_price      NUMERIC(20, 8) NOT NULL,
    low_price       NUMERIC(20, 8) NOT NULL,
    close_price     NUMERIC(20, 8) NOT NULL,
    volume          NUMERIC(20, 8) NOT NULL,
    quote_volume    NUMERIC(20, 8) NOT NULL,
    trades_count    INTEGER,
    taker_buy_base  NUMERIC(20, 8),
    taker_buy_quote NUMERIC(20, 8),
    UNIQUE (open_time)
);

CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_time ON {TABLE_NAME}(open_time);
"""


def get_conn():
    """Return a new psycopg2 connection."""
    return psycopg2.connect(**DB_DEFAULTS)


def init_db():
    """Create table if not exists."""
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
    conn.commit()
    conn.close()
    print(f"[OK] Database table '{TABLE_NAME}' ready")


# ── Binance API ───────────────────────────────────────────────────────────────
def fetch_candles(start_time: int, end_time: int) -> List[List[Any]]:
    """
    Fetch candles from Binance API.
    Returns list of klines.
    """
    params = {
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "startTime": start_time,
        "endTime": end_time,
        "limit": LIMIT_PER_REQUEST,
    }
    
    try:
        response = requests.get(BINANCE_API, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] API request failed: {e}")
        return []


def parse_candle(kline: List[Any]) -> Dict[str, Any]:
    """
    Parse Binance kline format into dict.
    Kline format: [open_time, open, high, low, close, volume, close_time, 
                   quote_volume, trades_count, taker_buy_base, taker_buy_quote, ignore]
    """
    return {
        "open_time": datetime.fromtimestamp(kline[0] / 1000, tz=timezone.utc),
        "close_time": datetime.fromtimestamp(kline[6] / 1000, tz=timezone.utc),
        "open_price": float(kline[1]),
        "high_price": float(kline[2]),
        "low_price": float(kline[3]),
        "close_price": float(kline[4]),
        "volume": float(kline[5]),
        "quote_volume": float(kline[7]),
        "trades_count": int(kline[8]),
        "taker_buy_base": float(kline[9]),
        "taker_buy_quote": float(kline[10]),
    }


# ── Data Fetching ─────────────────────────────────────────────────────────────
def fetch_all_candles() -> List[Dict[str, Any]]:
    """
    Fetch all candles from START_TIME to END_TIME, handling pagination.
    """
    all_candles = []
    current_start = START_TIME
    
    print(f"Fetching {SYMBOL} {INTERVAL} candles from {datetime.fromtimestamp(START_TIME/1000, tz=timezone.utc)}")
    print(f"Target end: {datetime.fromtimestamp(END_TIME/1000, tz=timezone.utc)}")
    print()
    
    request_count = 0
    
    while current_start < END_TIME:
        request_count += 1
        print(f"Request {request_count}: Fetching from {datetime.fromtimestamp(current_start/1000, tz=timezone.utc)}...", end=" ")
        
        klines = fetch_candles(current_start, END_TIME)
        
        if not klines:
            print("No data returned")
            break
        
        candles = [parse_candle(k) for k in klines]
        all_candles.extend(candles)
        
        print(f"Got {len(candles)} candles")
        
        # Update start time for next batch (last candle's open_time + 1 hour)
        last_open_time = klines[-1][0]
        current_start = last_open_time + (60 * 60 * 1000)  # +1 hour in ms
        
        # If we got fewer than limit, we've reached the end
        if len(klines) < LIMIT_PER_REQUEST:
            print("Reached end of available data")
            break
        
        # Rate limiting - be nice to Binance
        time.sleep(0.1)
    
    print(f"\n[OK] Total requests: {request_count}")
    print(f"[OK] Total candles fetched: {len(all_candles)}")
    
    return all_candles


# ── Storage ───────────────────────────────────────────────────────────────────
def save_to_database(candles: List[Dict[str, Any]]) -> int:
    """Save candles to PostgreSQL."""
    conn = get_conn()
    inserted = 0
    
    sql = f"""
        INSERT INTO {TABLE_NAME} 
        (open_time, close_time, open_price, high_price, low_price, close_price, 
         volume, quote_volume, trades_count, taker_buy_base, taker_buy_quote)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (open_time) DO UPDATE SET
            close_time = EXCLUDED.close_time,
            open_price = EXCLUDED.open_price,
            high_price = EXCLUDED.high_price,
            low_price = EXCLUDED.low_price,
            close_price = EXCLUDED.close_price,
            volume = EXCLUDED.volume,
            quote_volume = EXCLUDED.quote_volume,
            trades_count = EXCLUDED.trades_count,
            taker_buy_base = EXCLUDED.taker_buy_base,
            taker_buy_quote = EXCLUDED.taker_buy_quote
    """
    
    with conn.cursor() as cur:
        for candle in candles:
            cur.execute(sql, (
                candle["open_time"],
                candle["close_time"],
                candle["open_price"],
                candle["high_price"],
                candle["low_price"],
                candle["close_price"],
                candle["volume"],
                candle["quote_volume"],
                candle["trades_count"],
                candle["taker_buy_base"],
                candle["taker_buy_quote"],
            ))
            inserted += 1
            
            if inserted % 1000 == 0:
                conn.commit()
                print(f"  ... {inserted} records saved")
    
    conn.commit()
    conn.close()
    
    return inserted


def save_to_csv(candles: List[Dict[str, Any]]) -> str:
    """Save candles to CSV file."""
    # Ensure data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filepath = os.path.join(DATA_DIR, f"binance_btc_1h_{timestamp}.csv")
    
    fieldnames = [
        "open_time", "close_time", "open_price", "high_price", "low_price",
        "close_price", "volume", "quote_volume", "trades_count",
        "taker_buy_base", "taker_buy_quote"
    ]
    
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(candles)
    
    return filepath


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("Binance Historical Data Fetcher")
    print("=" * 60)
    print()
    
    # Initialize database
    print("Initializing database...")
    init_db()
    print()
    
    # Fetch all candles
    print("Fetching data from Binance...")
    candles = fetch_all_candles()
    
    if not candles:
        print("[ERROR] No data fetched. Exiting.")
        sys.exit(1)
    
    print()
    print("Data range:")
    print(f"  First candle: {candles[0]['open_time']}")
    print(f"  Last candle:  {candles[-1]['open_time']}")
    print()
    
    # Save to database
    print("Saving to PostgreSQL...")
    db_count = save_to_database(candles)
    print(f"[OK] Saved {db_count} records to table '{TABLE_NAME}'")
    print()
    
    # Save to CSV
    print("Creating CSV backup...")
    csv_path = save_to_csv(candles)
    print(f"[OK] CSV saved to: {csv_path}")
    print()
    
    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Symbol:        {SYMBOL}")
    print(f"Interval:      {INTERVAL}")
    print(f"Total records: {len(candles)}")
    print(f"Date range:    {candles[0]['open_time']} to {candles[-1]['close_time']}")
    print(f"Database:      {DB_DEFAULTS['dbname']}.{TABLE_NAME}")
    print(f"CSV backup:    {csv_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
