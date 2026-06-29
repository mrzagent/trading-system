#!/usr/bin/env python3
"""
backtest_fvg_15min.py — FVG Strategy Backtest on 15-minute aggregated data

Aggregates 5-minute candles from binance_btc_5min into 15-minute candles.
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, r"D:\dev\trading")

# --- Configuration ---
INITIAL_BALANCE = 10000.0
LEVERAGE = 3.0
TRADING_FEE_PCT = 0.0005
PORTFOLIO_PCT = 0.05

# FVG Settings
FVG_LOOKBACK = 20           # Look back 20 candles for FVGs (15m = 5 hours)
FVG_MAX_AGE = 6             # Only trade FVGs 1-6 candles old (1.5 hours)
MIN_FVG_SIZE_PCT = 0.02     # FVG must be at least 0.02% of price

# Entry: Price must break FVG by this % to trigger
BREAK_THRESHOLD_PCT = 0.01  # 0.01% beyond FVG boundary

# Exit settings
MAX_HOLD_CANDLES = 6        # Exit after 6 candles (1.5 hours)
STOP_LOSS_PCT = 0.5         # 0.5% stop loss
TAKE_PROFIT_PCT = 1.0       # 1.0% take profit (2:1 RR)

# DB Config
DB_DEFAULTS = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "1870506303979",
    "host": "localhost",
    "port": 5432,
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
    fvg_type: str
    fvg_bottom: float
    fvg_top: float
    fvg_age: int
    bars_held: int


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


def fetch_candles(conn, limit: int = None) -> List[dict]:
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    query = f"""
        SELECT open_time, open_price, high_price, low_price, close_price, volume
        FROM {TABLE_NAME}
        ORDER BY open_time ASC
    """
    if limit:
        query += f" LIMIT {limit}"
    
    cur.execute(query)
    rows = cur.fetchall()
    cur.close()
    
    candles = []
    for r in rows:
        candles.append({
            "timestamp": r["open_time"],
            "open": float(r["open_price"]),
            "high": float(r["high_price"]),
            "low": float(r["low_price"]),
            "close": float(r["close_price"]),
            "volume": float(r["volume"]) if r["volume"] else 0
        })
    
    return candles


def aggregate_to_15min(candles_5min: List[dict]) -> List[dict]:
    """Aggregate 5-minute candles into 15-minute candles."""
    candles_15min = []
    
    for i in range(0, len(candles_5min) - 2, 3):
        batch = candles_5min[i:i+3]
        if len(batch) < 3:
            break
        
        open_price = batch[0]["open"]
        high_price = max(c["high"] for c in batch)
        low_price = min(c["low"] for c in batch)
        close_price = batch[-1]["close"]
        volume = sum(c["volume"] for c in batch)
        timestamp = batch[0]["timestamp"]
        
        candles_15min.append({
            "timestamp": timestamp,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "volume": volume
        })
    
    return candles_15min


def detect_fvgs(candles: List[dict], current_idx: int, lookback: int) -> List[dict]:
    """Detect FVGs and return with their age."""
    fvgs = []
    start_idx = max(1, current_idx - lookback)
    
    for i in range(start_idx, current_idx):
        if i < 1 or i >= len(candles) - 1:
            continue
        
        prev = candles[i - 1]
        curr = candles[i]
        nxt = candles[i + 1]
        
        # Bullish FVG
        if prev["high"] < nxt["low"]:
            gap_size = nxt["low"] - prev["high"]
            gap_size_pct = (gap_size / prev["high"]) * 100
            
            if gap_size_pct >= MIN_FVG_SIZE_PCT:
                fvgs.append({
                    "type": "bullish",
                    "bottom": prev["high"],
                    "top": nxt["low"],
                    "formed_at_idx": i,
                    "age": current_idx - i,
                    "size_pct": gap_size_pct
                })
        
        # Bearish FVG
        elif prev["low"] > nxt["high"]:
            gap_size = prev["low"] - nxt["high"]
            gap_size_pct = (gap_size / prev["low"]) * 100
            
            if gap_size_pct >= MIN_FVG_SIZE_PCT:
                fvgs.append({
                    "type": "bearish",
                    "top": prev["low"],
                    "bottom": nxt["high"],
                    "formed_at_idx": i,
                    "age": current_idx - i,
                    "size_pct": gap_size_pct
                })
    
    # Sort by age (youngest first)
    fvgs.sort(key=lambda x: x["age"])
    return fvgs


def check_fvg_breakout(price: float, fvgs: List[dict], max_age: int) -> Tuple[str, Optional[dict]]:
    """Check if we should enter based on FVG BREAK."""
    for fvg in fvgs:
        if fvg["age"] < 1 or fvg["age"] > max_age:
            continue
        
        ftype = fvg["type"]
        bottom = fvg["bottom"]
        top = fvg["top"]
        
        break_buffer = (top - bottom) * (BREAK_THRESHOLD_PCT / 100)
        
        if ftype == "bullish":
            if price < (bottom - break_buffer):
                return "SELL", fvg
        
        elif ftype == "bearish":
            if price > (top + break_buffer):
                return "BUY", fvg
    
    return "HOLD", None


def run_backtest(candle_limit: int = None):
    print("=" * 70)
    print("FVG BREAKOUT STRATEGY BACKTEST - 15 MINUTE TIMEFRAME")
    print("=" * 70)
    print()
    print("Logic: Enter when FVG BREAKS (momentum continuation)")
    print("  - Bullish FVG broken -> SHORT (demand failed)")
    print("  - Bearish FVG broken -> LONG (supply failed)")
    print()
    
    print("Fetching 5-minute data from PostgreSQL...")
    conn = get_conn()
    candles_5min = fetch_candles(conn, limit=candle_limit)
    conn.close()
    
    if not candles_5min:
        print("ERROR: No data found")
        return
    
    print(f"Loaded {len(candles_5min):,} 5-minute candles")
    
    # Aggregate to 15-minute
    candles = aggregate_to_15min(candles_5min)
    print(f"Aggregated to {len(candles):,} 15-minute candles")
    print(f"Date range: {candles[0]['timestamp']} to {candles[-1]['timestamp']}")
    print()
    
    balance = INITIAL_BALANCE
    position = None
    result = BacktestResult()
    equity_curve = [INITIAL_BALANCE]
    peak_balance = INITIAL_BALANCE
    
    warmup = FVG_LOOKBACK + 10
    
    print("Running backtest...")
    print()
    
    for i in range(warmup, len(candles)):
        current = candles[i]
        current_price = current["close"]
        current_time = current["timestamp"]
        
        # Update equity
        if position:
            entry_price = position["entry_price"]
            direction = position["direction"]
            if direction == "LONG":
                unrealized_pct = (current_price - entry_price) / entry_price
            else:
                unrealized_pct = (entry_price - current_price) / entry_price
            equity_curve.append(balance * (1 + unrealized_pct * PORTFOLIO_PCT * LEVERAGE))
        else:
            equity_curve.append(balance)
        
        # Update drawdown
        if equity_curve[-1] > peak_balance:
            peak_balance = equity_curve[-1]
        drawdown = (peak_balance - equity_curve[-1]) / peak_balance
        if drawdown > result.max_drawdown_pct:
            result.max_drawdown_pct = drawdown * 100
        
        # Check exit
        if position:
            entry_price = position["entry_price"]
            direction = position["direction"]
            bars_held = i - position["entry_idx"]
            
            if direction == "LONG":
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price
            
            exit_reason = None
            
            if pnl_pct <= -STOP_LOSS_PCT / 100:
                exit_reason = "STOP_LOSS"
            elif pnl_pct >= TAKE_PROFIT_PCT / 100:
                exit_reason = "TAKE_PROFIT"
            elif bars_held >= MAX_HOLD_CANDLES:
                exit_reason = "TIME_EXIT"
            elif i == len(candles) - 1:
                exit_reason = "END_OF_DATA"
            
            if exit_reason:
                position_value = balance * PORTFOLIO_PCT
                fees = position_value * TRADING_FEE_PCT * 2
                pnl_usd = position_value * pnl_pct * LEVERAGE - fees
                
                trade = Trade(
                    direction=direction,
                    entry_price=entry_price,
                    exit_price=current_price,
                    entry_time=position["entry_time"],
                    exit_time=current_time,
                    pnl_pct=pnl_pct * 100,
                    pnl_usd=pnl_usd,
                    exit_reason=exit_reason,
                    fvg_type=position["fvg_type"],
                    fvg_bottom=position["fvg_bottom"],
                    fvg_top=position["fvg_top"],
                    fvg_age=position["fvg_age"],
                    bars_held=bars_held
                )
                
                result.trades.append(trade)
                result.total_trades += 1
                result.total_pnl_usd += pnl_usd
                if pnl_usd > 0:
                    result.winning_trades += 1
                else:
                    result.losing_trades += 1
                
                balance += pnl_usd
                position = None
        
        # Check entry
        else:
            fvgs = detect_fvgs(candles, i, FVG_LOOKBACK)
            action, fvg = check_fvg_breakout(current_price, fvgs, FVG_MAX_AGE)
            
            if action in ["BUY", "SELL"] and fvg:
                direction = "LONG" if action == "BUY" else "SHORT"
                
                position = {
                    "direction": direction,
                    "entry_price": current_price,
                    "entry_time": current_time,
                    "entry_idx": i,
                    "fvg_type": fvg["type"],
                    "fvg_bottom": fvg["bottom"],
                    "fvg_top": fvg["top"],
                    "fvg_age": fvg["age"]
                }
    
    result.total_pnl_pct = (result.total_pnl_usd / INITIAL_BALANCE) * 100
    
    # Print results
    print("=" * 70)
    print("BACKTEST RESULTS - 15 MINUTE FVG BREAKOUT")
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
    
    print("=" * 70)
    print("CONFIGURATION")
    print("=" * 70)
    print(f"Timeframe:          15 minutes")
    print(f"FVG Lookback:       {FVG_LOOKBACK} candles ({FVG_LOOKBACK * 15} min)")
    print(f"FVG Max Age:        {FVG_MAX_AGE} candles ({FVG_MAX_AGE * 15} min)")
    print(f"Min FVG Size:       {MIN_FVG_SIZE_PCT}%")
    print(f"Break Threshold:    {BREAK_THRESHOLD_PCT}%")
    print(f"Stop Loss:          {STOP_LOSS_PCT}%")
    print(f"Take Profit:        {TAKE_PROFIT_PCT}%")
    print(f"Max Hold Time:      {MAX_HOLD_CANDLES} candles ({MAX_HOLD_CANDLES * 15} min)")
    print()
    
    if result.trades:
        bullish = [t for t in result.trades if t.fvg_type == "bullish"]
        bearish = [t for t in result.trades if t.fvg_type == "bearish"]
        
        print("Performance by FVG Type:")
        print("-" * 70)
        if bullish:
            wins = sum(1 for t in bullish if t.pnl_usd > 0)
            pnl = sum(t.pnl_usd for t in bullish)
            print(f"  Bullish FVG break -> SHORT | Trades: {len(bullish):4} | Win Rate: {wins/len(bullish)*100:5.1f}% | P&L: ${pnl:+.2f}")
        if bearish:
            wins = sum(1 for t in bearish if t.pnl_usd > 0)
            pnl = sum(t.pnl_usd for t in bearish)
            print(f"  Bearish FVG break -> LONG  | Trades: {len(bearish):4} | Win Rate: {wins/len(bearish)*100:5.1f}% | P&L: ${pnl:+.2f}")
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
        for reason, stats in sorted(exit_stats.items(), key=lambda x: -x[1]["trades"]):
            wr = (stats["wins"] / stats["trades"] * 100) if stats["trades"] > 0 else 0
            print(f"  {reason:15} | Trades: {stats['trades']:4} | Win Rate: {wr:5.1f}% | P&L: ${stats['pnl']:+.2f}")
        print()
        
        print("Recent Trades (last 15):")
        print("-" * 70)
        for t in result.trades[-15:]:
            pnl_str = f"${t.pnl_usd:+.2f}"
            direction_str = f"{t.fvg_type[:4].upper()}->{t.direction[:5]}"
            print(f"{t.exit_time.strftime('%Y-%m-%d %H:%M')} | {direction_str:10} | "
                  f"Age: {t.fvg_age:2}c | P&L: {pnl_str:>8} | {t.exit_reason}")
    
    print()
    print("=" * 70)
    
    return result


if __name__ == "__main__":
    run_backtest()
