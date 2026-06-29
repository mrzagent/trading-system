#!/usr/bin/env python3
"""
backtest_pullback_scalper_15min.py — Pullback Scalper on 15min BTC data
Fixed 1:2 Risk/Reward (fixed SL/TP distances, not ATR-based)
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, List

import numpy as np
import pandas as pd
import psycopg2
from decouple import config

sys.path.insert(0, r"D:\dev\trading")

# --- Configuration ---
INITIAL_BALANCE = 10000.0
LEVERAGE = 3.0
TRADING_FEE_PCT = 0.0005
PORTFOLIO_PCT = 0.05

# Strategy Parameters (15min only)
EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50
VOLUME_MULT = 1.5
ATR_PERIOD = 14
LOOKBACK_SWING = 10
RSI_PERIOD = 14

# Pullback Parameters
PULLBACK_MAX_BARS = 5
PULLBACK_MAX_DIST_PCT = 0.5
MIN_PULLBACK_PCT = 0.05

# Quality Filters
MIN_EMA_SEPARATION_PCT = 0.05
MIN_VOLUME_RATIO = 2.0
COOLDOWN_BARS = 6

# Risk Management - FIXED 1:2 RR
FIXED_SL_PCT = 0.5        # 0.5% stop loss (price distance)
FIXED_TP_PCT = 1.0        # 1.0% take profit (price distance) = 1:2 RR

# DB Config (from .env file)
DB_DEFAULTS = {
    "dbname":   config("DB_NAME",      default="postgres"),
    "user":     config("DB_USER",      default="postgres"),
    "password": config("DB_PASSWORD",  default=""),
    "host":     config("DB_HOST",      default="localhost"),
    "port":     config("DB_PORT",      cast=int, default=5432),
}

TABLE_NAME = "binance_btc_15min"


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
    entry_type: str = ""


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
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.ewm(alpha=1/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_indicators(df):
    df['ema9'] = df['close_price'].ewm(span=EMA_FAST, adjust=False).mean()
    df['ema21'] = df['close_price'].ewm(span=EMA_MID, adjust=False).mean()
    df['ema50'] = df['close_price'].ewm(span=EMA_SLOW, adjust=False).mean()
    
    df['rsi'] = calculate_rsi(df['close_price'], RSI_PERIOD)
    
    df['ema9_21_sep'] = (df['ema9'] - df['ema21']) / df['ema21'] * 100
    df['ema21_50_sep'] = (df['ema21'] - df['ema50']) / df['ema50'] * 100
    
    df['vol_sma20'] = df['volume'].rolling(window=20).mean()
    df['volume_ratio'] = df['volume'] / df['vol_sma20']
    
    df['swing_high'] = df['high_price'].rolling(window=LOOKBACK_SWING).max().shift(1)
    df['swing_low'] = df['low_price'].rolling(window=LOOKBACK_SWING).min().shift(1)
    
    df['bullish_stack'] = (df['ema9'] > df['ema21']) & (df['ema21'] > df['ema50'])
    df['bearish_stack'] = (df['ema9'] < df['ema21']) & (df['ema21'] < df['ema50'])
    
    df['strong_bullish_stack'] = (df['bullish_stack'] & 
                                   (df['ema9_21_sep'] >= MIN_EMA_SEPARATION_PCT) &
                                   (df['ema21_50_sep'] >= MIN_EMA_SEPARATION_PCT))
    df['strong_bearish_stack'] = (df['bearish_stack'] & 
                                   (-df['ema9_21_sep'] >= MIN_EMA_SEPARATION_PCT) &
                                   (-df['ema21_50_sep'] >= MIN_EMA_SEPARATION_PCT))
    
    df['strong_volume'] = df['volume_ratio'] >= MIN_VOLUME_RATIO
    
    df['rsi_long_ok'] = (df['rsi'] > 50) & (df['rsi'] < 70)
    df['rsi_short_ok'] = (df['rsi'] < 50) & (df['rsi'] > 30)
    
    df['dist_from_ema9_pct'] = (df['close_price'] - df['ema9']) / df['ema9'] * 100
    
    return df


def run_strategy_pullback(df, strategy_name, use_rsi_filter=False):
    result = BacktestResult(name=strategy_name)
    balance = INITIAL_BALANCE
    position = None
    last_trade_bar = -COOLDOWN_BARS
    
    pullback_state = {
        'active': False,
        'direction': None,
        'start_bar': 0,
        'pullback_occurred': False,
        'lowest_pullback_dist': 0,
        'highest_pullback_dist': 0,
    }
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        current_time = row['open_time']
        price = row['close_price']
        
        if pullback_state['active'] and (i - pullback_state['start_bar']) > PULLBACK_MAX_BARS:
            pullback_state = {'active': False, 'direction': None, 'start_bar': 0, 
                             'pullback_occurred': False, 'lowest_pullback_dist': 0, 'highest_pullback_dist': 0}
        
        if pullback_state['active']:
            if pullback_state['direction'] == 'LONG':
                if row['dist_from_ema9_pct'] < pullback_state['lowest_pullback_dist']:
                    pullback_state['lowest_pullback_dist'] = row['dist_from_ema9_pct']
                if row['close_price'] <= row['ema9'] or row['low_price'] <= row['ema9']:
                    pullback_state['pullback_occurred'] = True
            else:
                if row['dist_from_ema9_pct'] > pullback_state['highest_pullback_dist']:
                    pullback_state['highest_pullback_dist'] = row['dist_from_ema9_pct']
                if row['close_price'] >= row['ema9'] or row['high_price'] >= row['ema9']:
                    pullback_state['pullback_occurred'] = True
        
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
                    exit_reason=exit_reason,
                    entry_type=position.get("entry_type", "unknown")
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
                pullback_state = {'active': False, 'direction': None, 'start_bar': 0,
                                 'pullback_occurred': False, 'lowest_pullback_dist': 0, 'highest_pullback_dist': 0}
        
        if not position and i < len(df) - 1:
            if i - last_trade_bar < COOLDOWN_BARS:
                continue
            
            if not pullback_state['active']:
                stack_long = row['strong_bullish_stack'] and (use_rsi_filter and row['rsi_long_ok'] or not use_rsi_filter)
                stack_short = row['strong_bearish_stack'] and (use_rsi_filter and row['rsi_short_ok'] or not use_rsi_filter)
                
                if stack_long:
                    pullback_state = {
                        'active': True, 'direction': 'LONG', 'start_bar': i,
                        'pullback_occurred': False, 'lowest_pullback_dist': 0, 'highest_pullback_dist': 0
                    }
                elif stack_short:
                    pullback_state = {
                        'active': True, 'direction': 'SHORT', 'start_bar': i,
                        'pullback_occurred': False, 'lowest_pullback_dist': 0, 'highest_pullback_dist': 0
                    }
            
            if pullback_state['active'] and pullback_state['pullback_occurred']:
                if pullback_state['direction'] == 'LONG':
                    if prev_row['close_price'] <= prev_row['ema9'] and row['close_price'] > row['ema9']:
                        if row['strong_volume']:
                            entry_price = row['close_price']
                            # FIXED 1:2 RR
                            sl_price = entry_price * (1 - FIXED_SL_PCT / 100)
                            tp_price = entry_price * (1 + FIXED_TP_PCT / 100)
                            
                            position = {
                                "direction": "LONG",
                                "entry_price": entry_price,
                                "sl_price": sl_price,
                                "tp_price": tp_price,
                                "entry_time": current_time,
                                "entry_type": "pullback"
                            }
                            
                            pullback_state = {'active': False, 'direction': None, 'start_bar': 0,
                                             'pullback_occurred': False, 'lowest_pullback_dist': 0, 'highest_pullback_dist': 0}
                
                elif pullback_state['direction'] == 'SHORT':
                    if prev_row['close_price'] >= prev_row['ema9'] and row['close_price'] < row['ema9']:
                        if row['strong_volume']:
                            entry_price = row['close_price']
                            # FIXED 1:2 RR
                            sl_price = entry_price * (1 + FIXED_SL_PCT / 100)
                            tp_price = entry_price * (1 - FIXED_TP_PCT / 100)
                            
                            position = {
                                "direction": "SHORT",
                                "entry_price": entry_price,
                                "sl_price": sl_price,
                                "tp_price": tp_price,
                                "entry_time": current_time,
                                "entry_type": "pullback"
                            }
                            
                            pullback_state = {'active': False, 'direction': None, 'start_bar': 0,
                                             'pullback_occurred': False, 'lowest_pullback_dist': 0, 'highest_pullback_dist': 0}
    
    result.total_pnl_pct = (result.total_pnl_usd / INITIAL_BALANCE) * 100
    
    peak = INITIAL_BALANCE
    for trade in result.trades:
        balance += trade.pnl_usd
        if balance > peak:
            peak = balance
        dd = (peak - balance) / peak * 100
        if dd > result.max_drawdown_pct:
            result.max_drawdown_pct = dd
    
    return result, balance


def run_strategy_breakout(df, strategy_name, use_rsi_filter=False):
    result = BacktestResult(name=strategy_name)
    balance = INITIAL_BALANCE
    position = None
    last_trade_bar = -COOLDOWN_BARS
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
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
                    exit_reason=exit_reason,
                    entry_type="breakout"
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
            if i - last_trade_bar < COOLDOWN_BARS:
                continue
            
            breakout_long = row['close_price'] > prev_row['swing_high'] and prev_row['close_price'] <= prev_row['swing_high']
            breakout_short = row['close_price'] < prev_row['swing_low'] and prev_row['close_price'] >= prev_row['swing_low']
            
            if breakout_long and row['strong_bullish_stack'] and row['strong_volume']:
                if not use_rsi_filter or row['rsi_long_ok']:
                    entry_price = row['close_price']
                    # FIXED 1:2 RR
                    sl_price = entry_price * (1 - FIXED_SL_PCT / 100)
                    tp_price = entry_price * (1 + FIXED_TP_PCT / 100)
                    
                    position = {
                        "direction": "LONG",
                        "entry_price": entry_price,
                        "sl_price": sl_price,
                        "tp_price": tp_price,
                        "entry_time": current_time,
                        "entry_type": "breakout"
                    }
            
            elif breakout_short and row['strong_bearish_stack'] and row['strong_volume']:
                if not use_rsi_filter or row['rsi_short_ok']:
                    entry_price = row['close_price']
                    # FIXED 1:2 RR
                    sl_price = entry_price * (1 + FIXED_SL_PCT / 100)
                    tp_price = entry_price * (1 - FIXED_TP_PCT / 100)
                    
                    position = {
                        "direction": "SHORT",
                        "entry_price": entry_price,
                        "sl_price": sl_price,
                        "tp_price": tp_price,
                        "entry_time": current_time,
                        "entry_type": "breakout"
                    }
    
    result.total_pnl_pct = (result.total_pnl_usd / INITIAL_BALANCE) * 100
    
    peak = INITIAL_BALANCE
    for trade in result.trades:
        balance += trade.pnl_usd
        if balance > peak:
            peak = balance
        dd = (peak - balance) / peak * 100
        if dd > result.max_drawdown_pct:
            result.max_drawdown_pct = dd
    
    return result, balance


def print_results(result: BacktestResult, final_balance: float):
    print(f"\n{'='*70}")
    print(f"RESULTS: {result.name}")
    print(f"{'='*70}")
    print(f"Initial Balance:    ${INITIAL_BALANCE:,.2f}")
    print(f"Final Balance:      ${final_balance:,.2f}")
    print(f"Total P&L:          ${result.total_pnl_usd:,.2f} ({result.total_pnl_pct:.2f}%)")
    print()
    print(f"Total Trades:       {result.total_trades}")
    print(f"Winning Trades:     {result.winning_trades} ({result.win_rate:.1f}%)")
    print(f"Losing Trades:      {result.losing_trades}")
    print(f"Profit Factor:      {result.profit_factor:.2f}")
    print(f"Max Drawdown:       {result.max_drawdown_pct:.2f}%")
    
    long_trades = [t for t in result.trades if t.direction == "LONG"]
    short_trades = [t for t in result.trades if t.direction == "SHORT"]
    
    print(f"\nPerformance by Direction:")
    print(f"{'-'*70}")
    
    if long_trades:
        long_wins = sum(1 for t in long_trades if t.pnl_usd > 0)
        long_pnl = sum(t.pnl_usd for t in long_trades)
        print(f"  LONG  | Trades: {len(long_trades)} | Win Rate: {long_wins/len(long_trades)*100:5.1f}% | P&L: ${long_pnl:,.2f}")
    
    if short_trades:
        short_wins = sum(1 for t in short_trades if t.pnl_usd > 0)
        short_pnl = sum(t.pnl_usd for t in short_trades)
        print(f"  SHORT | Trades: {len(short_trades)} | Win Rate: {short_wins/len(short_trades)*100:5.1f}% | P&L: ${short_pnl:,.2f}")


def print_comparison(results: List[BacktestResult]):
    print(f"\n{'='*90}")
    print("STRATEGY COMPARISON SUMMARY (15min BTC - Fixed 1:2 RR)")
    print(f"{'='*90}")
    print(f"{'Strategy':<35} {'Trades':>8} {'Win%':>8} {'P&L $':>12} {'P&L%':>8} {'PF':>6} {'MaxDD%':>8}")
    print("-" * 90)
    
    for result in results:
        print(f"{result.name:<35} {result.total_trades:>8} {result.win_rate:>7.1f}% ${result.total_pnl_usd:>10,.2f} {result.total_pnl_pct:>7.2f}% {result.profit_factor:>6.2f} {result.max_drawdown_pct:>7.2f}%")
    
    print(f"{'='*90}")
    
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
    print("MOMENTUM SCALPER — FIXED 1:2 RR COMPARISON (15min BTC)")
    print("=" * 90)
    print(f"Portfolio:         ${INITIAL_BALANCE:,.2f}")
    print(f"Position Size:     {PORTFOLIO_PCT*100:.0f}% of portfolio")
    print(f"Leverage:          {LEVERAGE}x")
    print(f"Trading Fee:       {TRADING_FEE_PCT*100:.3f}% per trade")
    print()
    print("Strategy Variants:")
    print("  1. Breakout Entry")
    print("  2. Breakout + RSI Filter")
    print("  3. Pullback Entry")
    print("  4. Pullback + RSI Filter")
    print()
    print("Risk Management (FIXED 1:2 RR):")
    print(f"  Stop Loss:       {FIXED_SL_PCT}% (fixed price distance)")
    print(f"  Take Profit:     {FIXED_TP_PCT}% (fixed price distance)")
    print(f"  Risk/Reward:     1:2")
    print()
    print("Common Parameters:")
    print(f"  EMA Stack:       EMA{EMA_FAST} > EMA{EMA_MID} > EMA{EMA_SLOW}")
    print(f"  Min EMA Sep:     {MIN_EMA_SEPARATION_PCT}%")
    print(f"  Min Volume:      {MIN_VOLUME_RATIO}x SMA20")
    print(f"  Cooldown:        {COOLDOWN_BARS} bars (15min)")
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
    
    results = []
    
    result, balance = run_strategy_breakout(df, "Breakout Entry", use_rsi_filter=False)
    results.append(result)
    print_results(result, balance)
    
    result, balance = run_strategy_breakout(df, "Breakout + RSI Filter", use_rsi_filter=True)
    results.append(result)
    print_results(result, balance)
    
    result, balance = run_strategy_pullback(df, "Pullback Entry", use_rsi_filter=False)
    results.append(result)
    print_results(result, balance)
    
    result, balance = run_strategy_pullback(df, "Pullback + RSI Filter", use_rsi_filter=True)
    results.append(result)
    print_results(result, balance)
    
    print_comparison(results)
    
    return results


if __name__ == "__main__":
    run_backtest()
