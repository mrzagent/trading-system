#!/usr/bin/env python3
"""
backtest_momentum_scalper_comparison.py — Momentum Scalper Comparison

Compares:
1. EMA9/21 only (no EMA50)
2. EMA9/21/50 (full stack)
3. Both with RSI(14) > 50 filter for longs
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

# Strategy Parameters
EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50
VOLUME_MULT = 1.5
ATR_PERIOD = 14
LOOKBACK_SWING = 10
RSI_PERIOD = 14

# Quality Filters
MIN_EMA_SEPARATION_PCT = 0.05  # 0.05% minimum separation between EMAs
MIN_BREAKOUT_PCT = 0.1         # 0.1% minimum breakout
MIN_VOLUME_RATIO = 2.0         # 2x volume minimum
COOLDOWN_BARS = 20             # Wait 20 bars between trades

# Risk Management
ATR_MULTIPLIER_SL = 1.0
ATR_MULTIPLIER_TP = 2.0

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


@dataclass
class BacktestResult:
    name: str = ""
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


def calculate_rsi(prices, period=14):
    """Calculate RSI for a price series."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_indicators(df):
    """Pre-calculate all indicators."""
    df['ema9'] = df['close_price'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema21'] = df['close_price'].ewm(span=EMA_MID, adjust=False).mean()
    df['ema50'] = df['close_price'].ewm(span=EMA_SLOW, adjust=False).mean()
    
    # RSI
    df['rsi'] = calculate_rsi(df['close_price'], RSI_PERIOD)
    
    # EMA separation
    df['ema9_21_sep'] = (df['ema9'] - df['ema21']) / df['ema21'] * 100
    df['ema21_50_sep'] = (df['ema21'] - df['ema50']) / df['ema50'] * 100
    
    # ATR
    high_low = df['high_price'] - df['low_price']
    high_close = np.abs(df['high_price'] - df['close_price'].shift())
    low_close = np.abs(df['low_price'] - df['close_price'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=ATR_PERIOD).mean()
    
    # Volume
    df['vol_sma20'] = df['volume'].rolling(window=20).mean()
    df['volume_ratio'] = df['volume'] / df['vol_sma20']
    
    # Swings
    df['swing_high'] = df['high_price'].rolling(window=LOOKBACK_SWING).max().shift(1)
    df['swing_low'] = df['low_price'].rolling(window=LOOKBACK_SWING).min().shift(1)
    
    # EMA stack variants
    df['bullish_stack_full'] = (df['ema9'] > df['ema21']) & (df['ema21'] > df['ema50'])
    df['bearish_stack_full'] = (df['ema9'] < df['ema21']) & (df['ema21'] < df['ema50'])
    
    df['bullish_stack_fast'] = df['ema9'] > df['ema21']  # No EMA50 requirement
    df['bearish_stack_fast'] = df['ema9'] < df['ema21']
    
    # Breakout %
    df['breakout_pct'] = (df['close_price'] - df['swing_high']) / df['swing_high'] * 100
    df['breakdown_pct'] = (df['swing_low'] - df['close_price']) / df['swing_low'] * 100
    
    # Quality filters for full stack
    df['strong_bullish_stack_full'] = (df['bullish_stack_full'] & 
                                        (df['ema9_21_sep'] >= MIN_EMA_SEPARATION_PCT) &
                                        (df['ema21_50_sep'] >= MIN_EMA_SEPARATION_PCT))
    df['strong_bearish_stack_full'] = (df['bearish_stack_full'] & 
                                        (-df['ema9_21_sep'] >= MIN_EMA_SEPARATION_PCT) &
                                        (-df['ema21_50_sep'] >= MIN_EMA_SEPARATION_PCT))
    
    # Quality filters for fast stack (EMA9/21 only)
    df['strong_bullish_stack_fast'] = df['bullish_stack_fast'] & (df['ema9_21_sep'] >= MIN_EMA_SEPARATION_PCT)
    df['strong_bearish_stack_fast'] = df['bearish_stack_fast'] & (-df['ema9_21_sep'] >= MIN_EMA_SEPARATION_PCT)
    
    df['strong_volume'] = df['volume_ratio'] >= MIN_VOLUME_RATIO
    df['strong_breakout'] = df['breakout_pct'] >= MIN_BREAKOUT_PCT
    df['strong_breakdown'] = df['breakdown_pct'] >= MIN_BREAKOUT_PCT
    
    # RSI filter for momentum confirmation
    # For longs: RSI > 50 confirms upward momentum (but not overbought > 70)
    # For shorts: RSI < 50 confirms downward momentum (but not oversold < 30)
    df['rsi_long_ok'] = (df['rsi'] > 50) & (df['rsi'] < 70)
    df['rsi_short_ok'] = (df['rsi'] < 50) & (df['rsi'] > 30)
    
    return df


def run_strategy(df, strategy_name, use_full_stack=True, use_rsi_filter=False):
    """
    Run a specific strategy variant.
    
    Args:
        df: DataFrame with indicators
        strategy_name: Name for reporting
        use_full_stack: True = EMA9/21/50, False = EMA9/21 only
        use_rsi_filter: True = require RSI > 50 for longs, < 50 for shorts
    """
    result = BacktestResult(name=strategy_name)
    balance = INITIAL_BALANCE
    position = None
    last_trade_bar = -COOLDOWN_BARS
    
    for i in range(len(df)):
        row = df.iloc[i]
        current_time = row['open_time']
        price = row['close_price']
        
        if position:
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
            else:
                if price >= position["sl_price"]:
                    should_exit = True
                    exit_reason = "SL"
                    exit_price = position["sl_price"]
                elif price <= position["tp_price"]:
                    should_exit = True
                    exit_reason = "TP"
                    exit_price = position["tp_price"]
            
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
                    exit_reason=exit_reason
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
                last_trade_bar = i
        
        if not position and i < len(df) - 1:
            # Cooldown check
            if i - last_trade_bar < COOLDOWN_BARS:
                continue
            
            # Select stack type
            if use_full_stack:
                bullish_stack = row['strong_bullish_stack_full']
                bearish_stack = row['strong_bearish_stack_full']
            else:
                bullish_stack = row['strong_bullish_stack_fast']
                bearish_stack = row['strong_bearish_stack_fast']
            
            # LONG signal
            long_signal = bullish_stack and row['strong_breakout'] and row['strong_volume']
            if use_rsi_filter:
                long_signal = long_signal and row['rsi_long_ok']
            
            if long_signal:
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
            
            # SHORT signal
            short_signal = bearish_stack and row['strong_breakdown'] and row['strong_volume']
            if use_rsi_filter:
                short_signal = short_signal and row['rsi_short_ok']
            
            if short_signal:
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
    
    return result, balance


def print_results(result, final_balance):
    """Print results for a single strategy."""
    print(f"\n{'='*70}")
    print(f"RESULTS: {result.name}")
    print(f"{'='*70}")
    print(f"Initial Balance:    ${INITIAL_BALANCE:,.2f}")
    print(f"Final Balance:      ${final_balance:,.2f}")
    print(f"Total P&L:          ${result.total_pnl_usd:,.2f} ({result.total_pnl_pct:+.2f}%)")
    print()
    print(f"Total Trades:       {result.total_trades}")
    print(f"Winning Trades:     {result.winning_trades} ({result.win_rate:.1f}%)")
    print(f"Losing Trades:      {result.losing_trades}")
    print(f"Profit Factor:      {result.profit_factor:.2f}")
    print(f"Max Drawdown:       {result.max_drawdown_pct:.2f}%")
    
    if result.trades:
        long_trades = [t for t in result.trades if t.direction == "LONG"]
        short_trades = [t for t in result.trades if t.direction == "SHORT"]
        
        print()
        print("Performance by Direction:")
        print("-" * 70)
        if long_trades:
            long_wins = sum(1 for t in long_trades if t.pnl_usd > 0)
            long_pnl = sum(t.pnl_usd for t in long_trades)
            print(f"  LONG  | Trades: {len(long_trades):3} | Win Rate: {long_wins/len(long_trades)*100:5.1f}% | P&L: ${long_pnl:+.2f}")
        if short_trades:
            short_wins = sum(1 for t in short_trades if t.pnl_usd > 0)
            short_pnl = sum(t.pnl_usd for t in short_trades)
            print(f"  SHORT | Trades: {len(short_trades):3} | Win Rate: {short_wins/len(short_trades)*100:5.1f}% | P&L: ${short_pnl:+.2f}")


def print_comparison(results):
    """Print side-by-side comparison of all strategies."""
    print(f"\n{'='*90}")
    print("STRATEGY COMPARISON SUMMARY")
    print(f"{'='*90}")
    print(f"{'Strategy':<35} {'Trades':>8} {'Win%':>8} {'P&L $':>12} {'P&L%':>8} {'PF':>6} {'MaxDD%':>8}")
    print("-" * 90)
    
    for result in results:
        print(f"{result.name:<35} {result.total_trades:>8} {result.win_rate:>7.1f}% ${result.total_pnl_usd:>10,.2f} {result.total_pnl_pct:>7.2f}% {result.profit_factor:>6.2f} {result.max_drawdown_pct:>7.2f}%")
    
    print(f"{'='*90}")
    
    # Find best by different metrics
    if results:
        best_pnl = max(results, key=lambda x: x.total_pnl_usd)
        best_pf = max(results, key=lambda x: x.profit_factor)
        best_wr = max(results, key=lambda x: x.win_rate)
        lowest_dd = min(results, key=lambda x: x.max_drawdown_pct)
        
        print("\nBEST BY METRIC:")
        print(f"  Highest P&L:      {best_pnl.name} (${best_pnl.total_pnl_usd:,.2f})")
        print(f"  Best Profit Factor: {best_pf.name} ({best_pf.profit_factor:.2f})")
        print(f"  Highest Win Rate: {best_wr.name} ({best_wr.win_rate:.1f}%)")
        print(f"  Lowest Drawdown:  {lowest_dd.name} ({lowest_dd.max_drawdown_pct:.2f}%)")


def run_backtest(candle_limit: int = None):
    print("=" * 90)
    print("MOMENTUM SCALPER — STRATEGY COMPARISON")
    print("=" * 90)
    print(f"Portfolio:         ${INITIAL_BALANCE:,.2f}")
    print(f"Position Size:     {PORTFOLIO_PCT*100:.0f}% of portfolio")
    print(f"Leverage:          {LEVERAGE}x")
    print(f"Trading Fee:       {TRADING_FEE_PCT*100:.3f}% per trade")
    print()
    print("Strategy Variants:")
    print("  1. EMA9/21/50 (Full Stack)")
    print("  2. EMA9/21 Only (Fast)")
    print("  3. EMA9/21/50 + RSI(14) > 50 filter")
    print("  4. EMA9/21 Only + RSI(14) > 50 filter")
    print()
    print("Common Parameters:")
    print(f"  Min EMA Sep:     {MIN_EMA_SEPARATION_PCT}%")
    print(f"  Min Breakout:    {MIN_BREAKOUT_PCT}%")
    print(f"  Min Volume:      {MIN_VOLUME_RATIO}x SMA20")
    print(f"  Cooldown:        {COOLDOWN_BARS} bars")
    print(f"  Swing Lookback:  {LOOKBACK_SWING} bars")
    print(f"  ATR SL:          {ATR_MULTIPLIER_SL}x | TP: {ATR_MULTIPLIER_TP}x (2R)")
    print("=" * 90)
    
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
    
    min_periods = max(EMA_SLOW, ATR_PERIOD, LOOKBACK_SWING, RSI_PERIOD, 20) + 10
    df = df.iloc[min_periods:].reset_index(drop=True)
    
    print(f"Processing {len(df)} valid candles...")
    
    # Run all 4 strategy variants
    results = []
    
    # 1. Full Stack (EMA9/21/50)
    result, balance = run_strategy(df, "EMA9/21/50 (Full Stack)", use_full_stack=True, use_rsi_filter=False)
    results.append(result)
    print_results(result, balance)
    
    # 2. Fast Stack (EMA9/21 only)
    result, balance = run_strategy(df, "EMA9/21 Only (Fast)", use_full_stack=False, use_rsi_filter=False)
    results.append(result)
    print_results(result, balance)
    
    # 3. Full Stack + RSI
    result, balance = run_strategy(df, "EMA9/21/50 + RSI Filter", use_full_stack=True, use_rsi_filter=True)
    results.append(result)
    print_results(result, balance)
    
    # 4. Fast Stack + RSI
    result, balance = run_strategy(df, "EMA9/21 Only + RSI Filter", use_full_stack=False, use_rsi_filter=True)
    results.append(result)
    print_results(result, balance)
    
    # Print comparison
    print_comparison(results)
    
    return results


if __name__ == "__main__":
    run_backtest()
