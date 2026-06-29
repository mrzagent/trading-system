#!/usr/bin/env python3
"""
backtest_momentum_scalper_binance_v2.py — Momentum Scalper v2

Improvements based on v1 results:
- Tighter stop losses (1.0x ATR instead of 1.5x)
- Higher volume threshold (2.0x instead of 1.5x) for stronger confirmation
- Added minimum ATR filter to avoid low-volatility chop
- Added time-based exit (max 24 bars = 2 hours)
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, List

import numpy as np
import pandas as pd
import psycopg2

sys.path.insert(0, r"D:\dev\trading")

# --- Configuration ---
INITIAL_BALANCE = 10000.0
LEVERAGE = 3.0
TRADING_FEE_PCT = 0.0005
PORTFOLIO_PCT = 0.05

# Momentum Scalper Parameters
EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50
VOLUME_MULT = 2.0  # Increased from 1.5
ATR_PERIOD = 14
LOOKBACK_SWING = 10

# Risk Management
ATR_MULTIPLIER_SL = 1.0   # Tighter: 1.0x instead of 1.5x
ATR_MULTIPLIER_TP = 2.0   # 2R ratio maintained
MAX_BARS_IN_TRADE = 24    # Time-based exit (2 hours on 5m candles)

MIN_ATR_PCT = 0.3         # Minimum ATR as % of price (filter chop)

# DB Config
DB_DEFAULTS = {
    "dbname":   "postgres",
    "user":     "postgres",
    "password": "1870506303979",
    "host":     "localhost",
    "port":     5432,
}

TABLE_NAME = "binance_btc_5min"


@dataclass
class Trade:
    direction: str
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    pnl_pct: float
    pnl_usd: float
    exit_reason: str
    bars_held: int = 0


@dataclass
class BacktestResult:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl_usd: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    trades: list = field(default_factory=list)
    
    @property
    def win_rate(self):
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100
    
    @property
    def profit_factor(self):
        gross_profit = sum(t.pnl_usd for t in self.trades if t.pnl_usd > 0)
        gross_loss = abs(sum(t.pnl_usd for t in self.trades if t.pnl_usd < 0))
        if gross_loss == 0:
            return gross_profit if gross_profit > 0 else 0
        return gross_profit / gross_loss


def get_conn():
    return psycopg2.connect(**DB_DEFAULTS)


def fetch_candles(conn, limit: int = None):
    sql = f"""
        SELECT open_time, open_price, high_price, low_price, close_price, volume
        FROM {TABLE_NAME}
        ORDER BY open_time ASC
    """
    if limit:
        sql += f" LIMIT {limit}"
    
    with conn.cursor() as cur:
        cur.execute(sql)
        columns = [desc[0] for desc in cur.description]
        rows = []
        for row in cur.fetchall():
            row_dict = dict(zip(columns, row))
            for key in ['open_price', 'high_price', 'low_price', 'close_price', 'volume']:
                if key in row_dict and row_dict[key] is not None:
                    row_dict[key] = float(row_dict[key])
            rows.append(row_dict)
    return rows


def calculate_indicators(df):
    """Pre-calculate all indicators using pandas."""
    df['ema9'] = df['close_price'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema21'] = df['close_price'].ewm(span=EMA_MID, adjust=False).mean()
    df['ema50'] = df['close_price'].ewm(span=EMA_SLOW, adjust=False).mean()
    
    high_low = df['high_price'] - df['low_price']
    high_close = np.abs(df['high_price'] - df['close_price'].shift())
    low_close = np.abs(df['low_price'] - df['close_price'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=ATR_PERIOD).mean()
    df['atr_pct'] = (df['atr'] / df['close_price']) * 100
    
    df['vol_sma20'] = df['volume'].rolling(window=20).mean()
    df['volume_ratio'] = df['volume'] / df['vol_sma20']
    
    df['swing_high'] = df['high_price'].rolling(window=LOOKBACK_SWING).max().shift(1)
    df['swing_low'] = df['low_price'].rolling(window=LOOKBACK_SWING).min().shift(1)
    
    df['bullish_stack'] = (df['ema9'] > df['ema21']) & (df['ema21'] > df['ema50'])
    df['bearish_stack'] = (df['ema9'] < df['ema21']) & (df['ema21'] < df['ema50'])
    
    df['broke_above'] = df['close_price'] > df['swing_high']
    df['broke_below'] = df['close_price'] < df['swing_low']
    
    df['volume_spike'] = df['volume_ratio'] >= VOLUME_MULT
    df['sufficient_volatility'] = df['atr_pct'] >= MIN_ATR_PCT
    
    return df


def run_backtest(candle_limit: int = None):
    print("=" * 70)
    print("MOMENTUM SCALPER V2 — BACKTEST RESULTS")
    print("=" * 70)
    print(f"Portfolio:         ${INITIAL_BALANCE:,.2f}")
    print(f"Position Size:     {PORTFOLIO_PCT*100:.0f}% of portfolio")
    print(f"Leverage:          {LEVERAGE}x")
    print(f"Trading Fee:       {TRADING_FEE_PCT*100:.3f}% per trade")
    print()
    print("Strategy Config (V2 Improvements):")
    print(f"  EMA Stack:       EMA{EMA_FAST} > EMA{EMA_MID} > EMA{EMA_SLOW}")
    print(f"  Swing Lookback:  {LOOKBACK_SWING} bars")
    print(f"  Volume Multiplier: {VOLUME_MULT}x SMA20 (was 1.5x)")
    print(f"  Min ATR Filter:  {MIN_ATR_PCT}% of price")
    print(f"  ATR SL Multiplier: {ATR_MULTIPLIER_SL}x (was 1.5x)")
    print(f"  ATR TP Multiplier: {ATR_MULTIPLIER_TP}x (2R)")
    print(f"  Max Hold Time:   {MAX_BARS_IN_TRADE} bars ({MAX_BARS_IN_TRADE*5} min)")
    print("=" * 70)
    
    conn = get_conn()
    candles = fetch_candles(conn, candle_limit)
    conn.close()
    
    print(f"\nLoaded {len(candles)} candles from {TABLE_NAME}")
    if not candles:
        return
    
    print(f"Date Range: {candles[0]['open_time']} to {candles[-1]['open_time']}")
    print("Calculating indicators...")
    
    df = pd.DataFrame(candles)
    df = calculate_indicators(df)
    
    min_periods = max(EMA_SLOW, ATR_PERIOD, LOOKBACK_SWING, 20) + 10
    df = df.iloc[min_periods:].reset_index(drop=True)
    
    print(f"Processing {len(df)} valid candles...")
    print()
    
    result = BacktestResult()
    balance = INITIAL_BALANCE
    position = None
    bars_in_trade = 0
    
    for i in range(len(df)):
        row = df.iloc[i]
        current_time = row['open_time']
        price = row['close_price']
        
        if position:
            bars_in_trade += 1
            should_exit = False
            exit_reason = None
            exit_price = price
            
            if position["direction"] == "LONG":
                if price <= position["sl_price"]:
                    should_exit = True
                    exit_reason = "SL"
                    exit_price = position["sl_price"]
                elif price >= position["tp_price"]:
                    should_exit = True
                    exit_reason = "TP"
                    exit_price = position["tp_price"]
                elif bars_in_trade >= MAX_BARS_IN_TRADE:
                    should_exit = True
                    exit_reason = "TIME"
                    exit_price = price
            else:
                if price >= position["sl_price"]:
                    should_exit = True
                    exit_reason = "SL"
                    exit_price = position["sl_price"]
                elif price <= position["tp_price"]:
                    should_exit = True
                    exit_reason = "TP"
                    exit_price = position["tp_price"]
                elif bars_in_trade >= MAX_BARS_IN_TRADE:
                    should_exit = True
                    exit_reason = "TIME"
                    exit_price = price
            
            if should_exit:
                if position["direction"] == "LONG":
                    pnl_pct = ((exit_price - position["entry_price"]) / position["entry_price"]) * LEVERAGE
                else:
                    pnl_pct = ((position["entry_price"] - exit_price) / position["entry_price"]) * LEVERAGE
                
                position_size = (INITIAL_BALANCE * PORTFOLIO_PCT) * LEVERAGE
                pnl_usd = position_size * pnl_pct
                fees = position_size * TRADING_FEE_PCT * 2
                pnl_usd -= fees
                
                trade = Trade(
                    direction=position["direction"],
                    entry_price=position["entry_price"],
                    exit_price=exit_price,
                    entry_time=position["entry_time"],
                    exit_time=current_time,
                    pnl_pct=pnl_pct * 100,
                    pnl_usd=pnl_usd,
                    exit_reason=exit_reason,
                    bars_held=bars_in_trade
                )
                
                result.trades.append(trade)
                result.total_trades += 1
                if pnl_usd > 0:
                    result.winning_trades += 1
                else:
                    result.losing_trades += 1
                result.total_pnl_usd += pnl_usd
                
                balance += pnl_usd
                position = None
                bars_in_trade = 0
        
        if not position and i < len(df) - 1:
            # Skip if volatility too low
            if not row['sufficient_volatility']:
                continue
                
            if row['bullish_stack'] and row['broke_above'] and row['volume_spike']:
                swing_sl_dist = price - row['swing_low']
                atr_sl_dist = row['atr'] * ATR_MULTIPLIER_SL
                sl_dist = min(swing_sl_dist, atr_sl_dist)
                
                position = {
                    "direction": "LONG",
                    "entry_price": price,
                    "entry_time": current_time,
                    "sl_price": price - sl_dist,
                    "tp_price": price + sl_dist * 2.0
                }
                bars_in_trade = 0
            
            elif row['bearish_stack'] and row['broke_below'] and row['volume_spike']:
                swing_sl_dist = row['swing_high'] - price
                atr_sl_dist = row['atr'] * ATR_MULTIPLIER_SL
                sl_dist = min(swing_sl_dist, atr_sl_dist)
                
                position = {
                    "direction": "SHORT",
                    "entry_price": price,
                    "entry_time": current_time,
                    "sl_price": price + sl_dist,
                    "tp_price": price - sl_dist * 2.0
                }
                bars_in_trade = 0
    
    result.total_pnl_pct = ((balance - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
    
    if result.trades:
        running_balance = INITIAL_BALANCE
        peak = INITIAL_BALANCE
        max_dd = 0
        
        for trade in result.trades:
            running_balance += trade.pnl_usd
            if running_balance > peak:
                peak = running_balance
            dd = (peak - running_balance) / peak * 100
            if dd > max_dd:
                max_dd = dd
        
        result.max_drawdown_pct = max_dd
    
    # Print results
    print("=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)
    print()
    print(f"Initial Balance:    ${INITIAL_BALANCE:,.2f}")
    print(f"Final Balance:      ${balance:,.2f}")
    print(f"Total P&L:          ${result.total_pnl_usd:,.2f} ({result.total_pnl_pct:+.2f}%)")
    print()
    print(f"Total Trades:       {result.total_trades}")
    print(f"Winning Trades:     {result.winning_trades} ({result.win_rate:.1f}%)")
    print(f"Losing Trades:      {result.losing_trades}")
    print(f"Profit Factor:      {result.profit_factor:.2f}")
    print(f"Max Drawdown:       {result.max_drawdown_pct:.2f}%")
    print()
    
    if result.trades:
        long_trades = [t for t in result.trades if t.direction == "LONG"]
        short_trades = [t for t in result.trades if t.direction == "SHORT"]
        
        print("Performance by Direction:")
        print("-" * 70)
        if long_trades:
            long_wins = sum(1 for t in long_trades if t.pnl_usd > 0)
            long_pnl = sum(t.pnl_usd for t in long_trades)
            avg_bars_long = sum(t.bars_held for t in long_trades) / len(long_trades)
            print(f"  LONG  | Trades: {len(long_trades):3} | Win Rate: {long_wins/len(long_trades)*100:5.1f}% | P&L: ${long_pnl:+.2f} | Avg Bars: {avg_bars_long:.1f}")
        if short_trades:
            short_wins = sum(1 for t in short_trades if t.pnl_usd > 0)
            short_pnl = sum(t.pnl_usd for t in short_trades)
            avg_bars_short = sum(t.bars_held for t in short_trades) / len(short_trades)
            print(f"  SHORT | Trades: {len(short_trades):3} | Win Rate: {short_wins/len(short_trades)*100:5.1f}% | P&L: ${short_pnl:+.2f} | Avg Bars: {avg_bars_short:.1f}")
        print()
        
        from collections import defaultdict
        exit_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0})
        for t in result.trades:
            exit_stats[t.exit_reason]["trades"] += 1
            exit_stats[t.exit_reason]["pnl"] += t.pnl_usd
            if t.pnl_usd > 0:
                exit_stats[t.exit_reason]["wins"] += 1
        
        print("Performance by Exit Reason:")
        print("-" * 70)
        for reason, stats in sorted(exit_stats.items()):
            win_rate = (stats["wins"] / stats["trades"] * 100) if stats["trades"] > 0 else 0
            print(f"  {reason:6} | Trades: {stats['trades']:3} | Win Rate: {win_rate:5.1f}% | P&L: ${stats['pnl']:+.2f}")
        print()
        
        print("Recent Trades (last 15):")
        print("-" * 70)
        for t in result.trades[-15:]:
            pnl_str = f"${t.pnl_usd:+.2f}"
            print(f"{t.exit_time.strftime('%Y-%m-%d %H:%M')} | {t.direction:5} | "
                  f"Entry: ${t.entry_price:,.2f} | Exit: ${t.exit_price:,.2f} | "
                  f"P&L: {pnl_str:>10} | {t.exit_reason} | {t.bars_held} bars")
    
    print()
    print("=" * 70)
    
    return result


if __name__ == "__main__":
    run_backtest()
