#!/usr/bin/env python3
"""
backtest_volume_spike.py — Volume Spike Strategy Backtest on 15-min BTC data

Signal logic:
  - Volume > X× rolling average (volume spike)
  - Price direction confirmation (up for BUY, down for SELL)
  - Enter on spike detection
  
Exit: Hold until SL or TP hit (no time exit)
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

# Volume Spike Settings
LOOKBACK_CANDLES = 16  # 16 × 15min = 4h rolling average
SPIKE_MULTIPLIER = 1.3  # Volume must be 1.3x average
PRICE_LOOKBACK = 16     # 16 × 15min = 4h for price direction
MIN_VOLUME = 100        # Minimum volume to consider

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
    {"name": "1.0 SL / 2.0 TP (1:2)", "sl": 1.0, "tp": 2.0, "spike_mult": 1.3},
    {"name": "1.5 SL / 3.0 TP (1:2)", "sl": 1.5, "tp": 3.0, "spike_mult": 1.3},
    {"name": "2.0 SL / 4.0 TP (1:2)", "sl": 2.0, "tp": 4.0, "spike_mult": 1.3},
    {"name": "1.5 SL / 3.0 TP (1:2) 1.5x", "sl": 1.5, "tp": 3.0, "spike_mult": 1.5},
    {"name": "1.5 SL / 3.0 TP (1:2) 2.0x", "sl": 1.5, "tp": 3.0, "spike_mult": 2.0},
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
    volume_ratio: float
    price_change_4h: float
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
    avg_bars_held: float = 0.0
    max_bars_held: int = 0
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


def detect_volume_spike(candles: List[dict], idx: int, spike_mult: float) -> Tuple[str, float, float]:
    """
    Detect volume spike with price direction.
    Returns: (action, volume_ratio, price_change_4h)
    """
    if idx < LOOKBACK_CANDLES + PRICE_LOOKBACK:
        return "HOLD", 0, 0
    
    current = candles[idx]
    current_vol = current["volume"]
    current_price = current["close"]
    
    # Calculate rolling average volume (excluding current)
    lookback_vols = [candles[i]["volume"] for i in range(idx - LOOKBACK_CANDLES, idx)]
    avg_vol = sum(lookback_vols) / len(lookback_vols) if lookback_vols else 0
    
    if avg_vol < MIN_VOLUME:
        return "HOLD", 0, 0
    
    volume_ratio = current_vol / avg_vol if avg_vol > 0 else 0
    
    # Check for spike
    if volume_ratio < spike_mult:
        return "HOLD", volume_ratio, 0
    
    # Calculate price change over 4h (PRICE_LOOKBACK candles)
    prev_price = candles[idx - PRICE_LOOKBACK]["close"]
    price_change = ((current_price - prev_price) / prev_price) * 100 if prev_price > 0 else 0
    
    # Directional signal
    if price_change > 0:
        return "BUY", volume_ratio, price_change
    elif price_change < 0:
        return "SELL", volume_ratio, price_change
    
    return "HOLD", volume_ratio, price_change


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
    warmup = LOOKBACK_CANDLES + PRICE_LOOKBACK + 5
    cooldown_bars = 0
    
    for i in range(warmup, len(candles)):
        current = candles[i]
        current_price = current["close"]
        current_time = current["timestamp"]
        
        # Update equity for drawdown tracking
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
        
        # Decrement cooldown
        if cooldown_bars > 0:
            cooldown_bars -= 1
        
        # Check exit - ONLY SL or TP (no time exit)
        if position:
            entry_price = position["entry_price"]
            direction = position["direction"]
            bars_held = i - position["entry_idx"]
            
            if direction == "LONG":
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price
            
            exit_reason = None
            
            # Only exit on SL or TP
            if pnl_pct <= -params["sl"] / 100:
                exit_reason = "STOP_LOSS"
            elif pnl_pct >= params["tp"] / 100:
                exit_reason = "TAKE_PROFIT"
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
                    volume_ratio=position["volume_ratio"],
                    price_change_4h=position["price_change_4h"],
                    bars_held=bars_held
                )
                
                result.trades.append(trade)
                result.total_trades += 1
                result.total_pnl_usd += pnl_usd
                if pnl_usd > 0:
                    result.winning_trades += 1
                else:
                    result.losing_trades += 1
                
                # Track bar stats
                if bars_held > result.max_bars_held:
                    result.max_bars_held = bars_held
                
                balance += pnl_usd
                position = None
        
        # Check entry (only if no position and not in cooldown)
        elif cooldown_bars == 0:
            action, vol_ratio, price_change = detect_volume_spike(candles, i, params["spike_mult"])
            
            if action in ["BUY", "SELL"]:
                direction = "LONG" if action == "BUY" else "SHORT"
                position = {
                    "direction": direction,
                    "entry_price": current_price,
                    "entry_time": current_time,
                    "entry_idx": i,
                    "volume_ratio": vol_ratio,
                    "price_change_4h": price_change
                }
                # Set cooldown (4 bars = 1 hour on 15m)
                cooldown_bars = 4
    
    result.total_pnl_pct = (result.total_pnl_usd / INITIAL_BALANCE) * 100
    if result.trades:
        result.avg_bars_held = sum(t.bars_held for t in result.trades) / len(result.trades)
    return result


def print_result_summary(result: BacktestResult):
    print(f"\n{result.name}")
    print("-" * 60)
    print(f"  P&L: ${result.total_pnl_usd:+,.2f} ({result.total_pnl_pct:+.2f}%)")
    print(f"  Trades: {result.total_trades} | Win Rate: {result.win_rate:.1f}%")
    print(f"  Profit Factor: {result.profit_factor:.2f} | Max DD: {result.max_drawdown_pct:.2f}%")
    print(f"  Avg Bars Held: {result.avg_bars_held:.1f} | Max Bars Held: {result.max_bars_held}")
    
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
    print("VOLUME SPIKE STRATEGY BACKTEST - 15min BTC")
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
    
    print("Running Volume Spike parameter sweep...")
    results = []
    for params in PARAM_SETS:
        result = run_single_backtest(candles, params)
        results.append(result)
        print_result_summary(result)
    
    # Summary table
    print("\n" + "=" * 70)
    print("SUMMARY COMPARISON")
    print("=" * 70)
    print(f"{'Config':<35} {'P&L':>12} {'Win%':>8} {'PF':>6} {'Trades':>8} {'AvgBars':>8}")
    print("-" * 70)
    for r in sorted(results, key=lambda x: x.total_pnl_usd, reverse=True):
        print(f"{r.name:<35} {r.total_pnl_usd:>+11,.0f} {r.win_rate:>7.1f}% {r.profit_factor:>6.2f} {r.total_trades:>8} {r.avg_bars_held:>8.1f}")
    
    best = max(results, key=lambda x: x.total_pnl_usd)
    print(f"\nBest performer: {best.name}")
    print(f"  P&L: ${best.total_pnl_usd:+,.2f} ({best.total_pnl_pct:+.2f}%)")
    print("=" * 70)
    
    # Calculate expected value for $20 position
    print("\n=== For $20 Position with 3x Leverage ===")
    print(f"{'Config':<30} {'Risk':>8} {'Reward':>8} {'Win%':>8} {'Exp.Value':>10}")
    print("-" * 70)
    for r in results:
        notional = 20 * 3  # $60
        risk = notional * r.sl_pct / 100
        reward = notional * r.tp_pct / 100
        win_rate = r.win_rate / 100
        exp_value = (reward * win_rate) - (risk * (1 - win_rate))
        print(f"{r.name:<30} ${risk:>7.2f} ${reward:>7.2f} {r.win_rate:>7.1f}% ${exp_value:>+9.2f}")


if __name__ == "__main__":
    run_backtest()
