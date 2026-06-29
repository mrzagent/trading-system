#!/usr/bin/env python3
"""
diagnose_pullback_scalper.py — Deep diagnostic for Pullback Scalper signal conditions

This script analyzes each condition separately to understand why signals aren't firing.
"""

import sys
from collections import defaultdict

import psycopg2.extras

sys.path.insert(0, r"D:\dev\trading")
from db import get_conn, COINS
from strategies.strategy_pullback_scalper import (
    calculate_ema, calculate_rsi, get_swing_high, get_swing_low,
    EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT, MIN_ROWS
)


def diagnose_conditions(rows, coin):
    """Analyze how often each condition is met."""
    
    stats = {
        "total": 0,
        "uptrend": 0,
        "downtrend": 0,
        "pulled_back_to_ema": 0,
        "rallied_to_ema": 0,
        "rsi_oversold": 0,
        "rsi_overbought": 0,
        "bullish_candle": 0,
        "bearish_candle": 0,
        "all_long_conditions": 0,
        "all_short_conditions": 0,
    }
    
    for i in range(MIN_ROWS, len(rows)):
        window = rows[i-MIN_ROWS:i]
        
        # Extract OHLCV
        opens = [float(r.get("open", r["price"])) for r in window]
        closes = [float(r["price"]) for r in window]
        highs = [float(r.get("high", r["price"])) for r in window]
        lows = [float(r.get("low", r["price"])) for r in window]
        
        price = closes[-1]
        open_last = opens[-1]
        high_last = highs[-1]
        low_last = lows[-1]
        
        # Calculate indicators
        ema_fast_series = calculate_ema(closes, EMA_FAST)
        ema_slow_series = calculate_ema(closes, EMA_SLOW)
        ema_fast = ema_fast_series[-1]
        ema_slow = ema_slow_series[-1]
        
        rsi_series = calculate_rsi(closes, RSI_PERIOD)
        current_rsi = rsi_series[-1]
        
        stats["total"] += 1
        
        # Check conditions
        if ema_fast > ema_slow:
            stats["uptrend"] += 1
        elif ema_fast < ema_slow:
            stats["downtrend"] += 1
        
        if low_last <= ema_fast:
            stats["pulled_back_to_ema"] += 1
        
        if high_last >= ema_fast:
            stats["rallied_to_ema"] += 1
        
        if current_rsi < RSI_OVERSOLD:
            stats["rsi_oversold"] += 1
        
        if current_rsi > RSI_OVERBOUGHT:
            stats["rsi_overbought"] += 1
        
        if price > open_last:
            stats["bullish_candle"] += 1
        
        if price < open_last:
            stats["bearish_candle"] += 1
        
        # Check all 4 conditions together
        if (ema_fast > ema_slow and low_last <= ema_fast and 
            current_rsi < RSI_OVERSOLD and price > open_last):
            stats["all_long_conditions"] += 1
        
        if (ema_fast < ema_slow and high_last >= ema_fast and 
            current_rsi > RSI_OVERBOUGHT and price < open_last):
            stats["all_short_conditions"] += 1
    
    return stats


def main():
    conn = get_conn()
    days_back = 7
    
    print("=" * 70)
    print("PULLBACK SCALPER - CONDITION DIAGNOSTIC")
    print("=" * 70)
    print(f"\nAnalyzing last {days_back} days of 5min candles")
    print(f"Conditions for LONG: Uptrend + Pullback to EMA20 + RSI(2)<{RSI_OVERSOLD} + Bullish candle")
    print(f"Conditions for SHORT: Downtrend + Rally to EMA20 + RSI(2)>{RSI_OVERBOUGHT} + Bearish candle")
    print()
    
    for coin in COINS:
        print(f"\n{'-' * 70}")
        print(f"COIN: {coin}")
        print("-" * 70)
        
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT * FROM trading_prices
            WHERE coin = %s AND captured_at > NOW() - INTERVAL '%s days'
            ORDER BY captured_at ASC
        """, (coin, days_back))
        
        rows = cur.fetchall()
        cur.close()
        
        if len(rows) < MIN_ROWS:
            print(f"  Insufficient data: {len(rows)} rows (need {MIN_ROWS})")
            continue
        
        stats = diagnose_conditions(rows, coin)
        total = stats["total"]
        
        print(f"  Total candles analyzed: {total}")
        print()
        print("  INDIVIDUAL CONDITION FREQUENCY:")
        print(f"    Uptrend (EMA20 > EMA50):           {stats['uptrend']:,} ({stats['uptrend']/total*100:.1f}%)")
        print(f"    Downtrend (EMA20 < EMA50):         {stats['downtrend']:,} ({stats['downtrend']/total*100:.1f}%)")
        print(f"    Price pulled back to EMA20:        {stats['pulled_back_to_ema']:,} ({stats['pulled_back_to_ema']/total*100:.1f}%)")
        print(f"    Price rallied to EMA20:            {stats['rallied_to_ema']:,} ({stats['rallied_to_ema']/total*100:.1f}%)")
        print(f"    RSI(2) < {RSI_OVERSOLD} (oversold):               {stats['rsi_oversold']:,} ({stats['rsi_oversold']/total*100:.1f}%)")
        print(f"    RSI(2) > {RSI_OVERBOUGHT} (overbought):             {stats['rsi_overbought']:,} ({stats['rsi_overbought']/total*100:.1f}%)")
        print(f"    Bullish candle (close > open):     {stats['bullish_candle']:,} ({stats['bullish_candle']/total*100:.1f}%)")
        print(f"    Bearish candle (close < open):     {stats['bearish_candle']:,} ({stats['bearish_candle']/total*100:.1f}%)")
        print()
        print("  ALL CONDITIONS MET:")
        print(f"    Long entry (all 4):                {stats['all_long_conditions']:,} ({stats['all_long_conditions']/total*100:.2f}%)")
        print(f"    Short entry (all 4):               {stats['all_short_conditions']:,} ({stats['all_short_conditions']/total*100:.2f}%)")
        
        # Calculate expected frequency
        long_prob = (stats['uptrend']/total) * (stats['pulled_back_to_ema']/total) * (stats['rsi_oversold']/total) * (stats['bullish_candle']/total)
        short_prob = (stats['downtrend']/total) * (stats['rallied_to_ema']/total) * (stats['rsi_overbought']/total) * (stats['bearish_candle']/total)
        print()
        print("  PROBABILITY ANALYSIS:")
        print(f"    Expected long signal rate (if independent):  {long_prob*100:.3f}%")
        print(f"    Expected short signal rate (if independent): {short_prob*100:.3f}%")
        print(f"    Actual long signal rate:                     {stats['all_long_conditions']/total*100:.3f}%")
        print(f"    Actual short signal rate:                    {stats['all_short_conditions']/total*100:.3f}%")
    
    conn.close()
    
    print("\n" + "=" * 70)
    print("INTERPRETATION")
    print("=" * 70)
    print("""
The Pullback Scalper requires ALL 4 conditions to fire simultaneously.
This creates a very restrictive filter - as shown above, even when each
condition occurs reasonably often, the combined probability is extremely low.

Key observations:
1. RSI(2) < 20 or > 80 are rare events (RSI is mean-reverting)
2. The strategy requires these extreme readings to coincide with:
   - A pullback to EMA20 (not too deep, not too shallow)
   - A confirming candle in the trend direction
   - An established trend

This is by design - it's a high-selectivity scalping strategy.
""")


if __name__ == "__main__":
    main()
