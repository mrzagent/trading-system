#!/usr/bin/env python3
"""
backtest_fvg_15min_sweep.py — FVG Strategy SL/TP Parameter Sweep on 15-minute data

Tests multiple stop loss / take profit combinations.
"""
import sys
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from collections import defaultdict

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
FVG_LOOKBACK = 20
FVG_MAX_AGE = 6
MIN_FVG_SIZE_PCT = 0.02
BREAK_THRESHOLD_PCT = 0.01
MAX_HOLD_CANDLES = 6

# DB Config
DB_DEFAULTS = {
    "dbname": "postgres",
    "user": "postgres",
    "password": "1870506303979",
    "host": "localhost",
    "port": 5432,
}
TABLE_NAME = "binance_btc_5min"

# Parameter sets to test
PARAM_SETS = [
    {"name": "1.0 SL / 1.0 TP (1:1 RR)", "sl": 1.0, "tp": 1.0, "confirm": False},
    {"name": "0.75 SL / 1.5 TP (1:2 RR)", "sl": 0.75, "tp": 1.5, "confirm": False},
    {"name": "0.5 SL / 1.5 TP (1:3 RR)", "sl": 0.5, "tp": 1.5, "confirm": False},
    {"name": "1.0 SL / 2.0 TP (1:2 RR)", "sl": 1.0, "tp": 2.0, "confirm": False},
    {"name": "5.0 SL / 2.0 TP + Confirm", "sl": 5.0, "tp": 2.0, "confirm": True},
    {"name": "5.0 SL / 3.0 TP + Confirm", "sl": 5.0, "tp": 3.0, "confirm": True},
    {"name": "5.0 SL / 5.0 TP + Confirm", "sl": 5.0, "tp": 5.0, "confirm": True},
]


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
    name: str
    sl_pct: float
    tp_pct: float
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
    candles_15min = []
    for i in range(0, len(candles_5min) - 2, 3):
        batch = candles_5min[i:i+3]
        if len(batch) < 3:
            break
        candles_15min.append({
            "timestamp": batch[0]["timestamp"],
            "open": batch[0]["open"],
            "high": max(c["high"] for c in batch),
            "low": min(c["low"] for c in batch),
            "close": batch[-1]["close"],
            "volume": sum(c["volume"] for c in batch)
        })
    return candles_15min


def detect_fvgs(candles: List[dict], current_idx: int) -> List[dict]:
    fvgs = []
    start_idx = max(1, current_idx - FVG_LOOKBACK)
    
    for i in range(start_idx, current_idx):
        if i < 1 or i >= len(candles) - 1:
            continue
        prev = candles[i - 1]
        nxt = candles[i + 1]
        
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
    fvgs.sort(key=lambda x: x["age"])
    return fvgs


def check_fvg_breakout(price: float, fvgs: List[dict]) -> Tuple[str, Optional[dict]]:
    for fvg in fvgs:
        if fvg["age"] < 1 or fvg["age"] > FVG_MAX_AGE:
            continue
        ftype = fvg["type"]
        bottom = fvg["bottom"]
        top = fvg["top"]
        break_buffer = (top - bottom) * (BREAK_THRESHOLD_PCT / 100)
        
        if ftype == "bullish" and price < (bottom - break_buffer):
            return "SELL", fvg
        elif ftype == "bearish" and price > (top + break_buffer):
            return "BUY", fvg
    return "HOLD", None


def run_single_backtest(candles: List[dict], params: dict) -> BacktestResult:
    result = BacktestResult(
        name=params["name"],
        sl_pct=params["sl"],
        tp_pct=params["tp"]
    )
    
    balance = INITIAL_BALANCE
    position = None
    equity_curve = [INITIAL_BALANCE]
    peak_balance = INITIAL_BALANCE
    warmup = FVG_LOOKBACK + 10
    
    for i in range(warmup, len(candles)):
        current = candles[i]
        current_price = current["close"]
        current_time = current["timestamp"]
        
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
        
        if equity_curve[-1] > peak_balance:
            peak_balance = equity_curve[-1]
        drawdown = (peak_balance - equity_curve[-1]) / peak_balance
        if drawdown > result.max_drawdown_pct:
            result.max_drawdown_pct = drawdown * 100
        
        if position:
            entry_price = position["entry_price"]
            direction = position["direction"]
            bars_held = i - position["entry_idx"]
            
            if direction == "LONG":
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price
            
            exit_reason = None
            
            if pnl_pct <= -params["sl"] / 100:
                exit_reason = "STOP_LOSS"
            elif pnl_pct >= params["tp"] / 100:
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
        else:
            fvgs = detect_fvgs(candles, i)
            action, fvg = check_fvg_breakout(current_price, fvgs)
            
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
    return result


def print_result_summary(result: BacktestResult):
    print(f"\n{result.name}")
    print("-" * 60)
    print(f"  P&L: ${result.total_pnl_usd:+,.2f} ({result.total_pnl_pct:+.2f}%)")
    print(f"  Trades: {result.total_trades} | Win Rate: {result.win_rate:.1f}%")
    print(f"  Profit Factor: {result.profit_factor:.2f} | Max DD: {result.max_drawdown_pct:.2f}%")
    
    # Exit breakdown
    exit_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0})
    for t in result.trades:
        exit_stats[t.exit_reason]["trades"] += 1
        exit_stats[t.exit_reason]["pnl"] += t.pnl_usd
        if t.pnl_usd > 0:
            exit_stats[t.exit_reason]["wins"] += 1
    
    for reason, stats in sorted(exit_stats.items(), key=lambda x: -x[1]["trades"]):
        wr = (stats["wins"] / stats["trades"] * 100) if stats["trades"] > 0 else 0
        print(f"    {reason:12}: {stats['trades']:4} trades | {wr:5.1f}% WR | ${stats['pnl']:+,.2f}")


def run_backtest():
    print("=" * 70)
    print("FVG 15-MINUTE SL/TP PARAMETER SWEEP")
    print("=" * 70)
    print()
    
    print("Fetching 5-minute data from PostgreSQL...")
    conn = get_conn()
    candles_5min = fetch_candles(conn)
    conn.close()
    
    print(f"Loaded {len(candles_5min):,} 5-minute candles")
    candles = aggregate_to_15min(candles_5min)
    print(f"Aggregated to {len(candles):,} 15-minute candles")
    print(f"Date range: {candles[0]['timestamp']} to {candles[-1]['timestamp']}")
    print()
    
    print("Running parameter sweep...")
    results = []
    for params in PARAM_SETS:
        result = run_single_backtest(candles, params)
        results.append(result)
        print_result_summary(result)
    
    # Summary table
    print("\n" + "=" * 70)
    print("SUMMARY COMPARISON")
    print("=" * 70)
    print(f"{'Config':<25} {'P&L':>12} {'Win%':>8} {'PF':>6} {'Trades':>8}")
    print("-" * 70)
    for r in sorted(results, key=lambda x: x.total_pnl_usd, reverse=True):
        print(f"{r.name:<25} {r.total_pnl_usd:>+11,.0f} {r.win_rate:>7.1f}% {r.profit_factor:>6.2f} {r.total_trades:>8}")
    
    best = max(results, key=lambda x: x.total_pnl_usd)
    print(f"\nBest performer: {best.name}")
    print(f"  P&L: ${best.total_pnl_usd:+,.2f} ({best.total_pnl_pct:+.2f}%)")
    print("=" * 70)


if __name__ == "__main__":
    run_backtest()
