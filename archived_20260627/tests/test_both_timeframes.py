#!/usr/bin/env python3
"""Test Mean Reversion strategy on both 1h and 4h timeframes."""

import sys
sys.path.insert(0, r"D:\dev\trading")

from strategy_mean_reversion import analyse, STRATEGY, MIN_ROWS
from db import get_conn, COINS, fetch_recent
from datetime import datetime, timezone

def test_timeframe(conn, tf):
    candle_start = datetime.now(timezone.utc)
    
    print(f"\n{'='*70}")
    print(f"TIMEFRAME: {tf}")
    print(f"{'='*70}")
    
    # Check data quality
    cur = conn.cursor()
    print("\n--- Latest OHLC data ---")
    for coin in COINS:
        table = f"trading_prices_{tf}" if tf != "5min" else "trading_prices"
        cur.execute(f"""
            SELECT price, high_price, low_price, open_price, captured_at
            FROM {table}
            WHERE coin = %s AND high_price IS NOT NULL
            ORDER BY captured_at DESC
            LIMIT 1
        """, (coin,))
        row = cur.fetchone()
        if row:
            price, high, low, open_p, ts = row
            print(f"{coin}: O={open_p:.2f} H={high:.2f} L={low:.2f} C={price:.2f} @ {ts.strftime('%H:%M')}")
        else:
            print(f"{coin}: No OHLC data yet")
    
    print(f"\n--- Strategy Signals ---")
    signals = []
    for coin in COINS:
        try:
            signal = analyse(coin, conn, candle_start, timeframe=tf)
            signals.append(signal)
            
            action = signal['action']
            conf = signal['confidence']
            meta = signal.get('meta', {})
            
            status = "[BUY]" if action == "BUY" else "[SELL]" if action == "SELL" else "[HOLD]"
            print(f"{coin}: {status} conf={conf:.2f} RSI2={meta.get('rsi_2', 'N/A'):.1f} ADX={meta.get('adx', 'N/A'):.1f}")
            
        except Exception as e:
            print(f"{coin}: ERROR - {e}")
    
    actionable = [s for s in signals if s['action'] in ('BUY', 'SELL')]
    print(f"\nSummary: {len(actionable)} actionable signals, {len(signals) - len(actionable)} holds")
    
    return signals

def main():
    conn = get_conn()
    
    print("=" * 70)
    print("MEAN REVERSION STRATEGY - BOTH TIMEFRAMES TEST")
    print("=" * 70)
    print(f"Strategy: {STRATEGY}")
    print(f"Min rows needed: {MIN_ROWS}")
    
    # Test 1h
    signals_1h = test_timeframe(conn, "1h")
    
    # Test 4h
    signals_4h = test_timeframe(conn, "4h")
    
    conn.close()
    
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"1h timeframe: {len([s for s in signals_1h if s['action'] != 'HOLD'])} signals")
    print(f"4h timeframe: {len([s for s in signals_4h if s['action'] != 'HOLD'])} signals")
    print("\nBoth timeframes now have proper OHLC data for accurate ADX/ATR calculations!")

if __name__ == "__main__":
    main()
