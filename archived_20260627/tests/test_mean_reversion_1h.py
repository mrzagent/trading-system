#!/usr/bin/env python3
"""Test Mean Reversion strategy on 1h timeframe."""

import sys
sys.path.insert(0, r"D:\dev\trading")

import os
os.environ["TIMEFRAME"] = "1h"

from strategy_mean_reversion import analyse, STRATEGY, MIN_ROWS
from db import get_conn, COINS, fetch_recent
from datetime import datetime, timezone

def test_1h():
    conn = get_conn()
    candle_start = datetime.now(timezone.utc)
    
    print("=" * 70)
    print("MEAN REVERSION STRATEGY TEST - 1H TIMEFRAME")
    print("=" * 70)
    
    # First check what columns we have
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'trading_prices_1h'
        ORDER BY ordinal_position
    """)
    cols = [c[0] for c in cur.fetchall()]
    print(f"\nAvailable columns: {cols}")
    
    # Check for high_price/low_price data
    print("\n--- Sample data (latest row per coin) ---")
    for coin in COINS:
        cur.execute("""
            SELECT price, high_price, low_price, open_price, captured_at
            FROM trading_prices_1h
            WHERE coin = %s
            ORDER BY captured_at DESC
            LIMIT 1
        """, (coin,))
        row = cur.fetchone()
        if row:
            price, high, low, open_p, ts = row
            print(f"{coin}: price={price}, high={high}, low={low}, open={open_p} @ {ts}")
        else:
            print(f"{coin}: No data")
    
    print(f"\n--- Strategy Analysis (need {MIN_ROWS} rows) ---")
    
    for coin in COINS:
        print(f"\n--- {coin} ---")
        try:
            # Check row count
            rows = fetch_recent(conn, coin, limit=MIN_ROWS, timeframe="1h")
            print(f"Fetched {len(rows)} rows")
            
            signal = analyse(coin, conn, candle_start, timeframe="1h")
            
            print(f"Action: {signal['action']}")
            print(f"Confidence: {signal['confidence']:.2f}")
            print(f"Reason: {signal['reason']}")
            
            if signal['meta']:
                meta = signal['meta']
                print(f"Price: ${meta.get('price', 'N/A')}")
                print(f"RSI(2): {meta.get('rsi_2', 'N/A')}")
                print(f"ADX: {meta.get('adx', 'N/A')}")
                print(f"Market Ranging: {meta.get('market_ranging', 'N/A')}")
                
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    conn.close()

if __name__ == "__main__":
    test_1h()
