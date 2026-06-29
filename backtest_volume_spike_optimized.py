#!/usr/bin/env python3
"""
backtest_volume_spike_optimized.py — Volume Spike Strategy Backtest
Using OPTIMIZED SETTINGS: 1.5% SL / 3% TP (1:2 Risk/Reward)

Signal logic:
  - Volume > 1.5× rolling average (volume spike)
  - Price direction confirmation (up for BUY, down for SELL)
  - Enter on spike detection
  
Exit: Optimized for scalp strategy:
  - SL: 1.5% (tight stop for quick exits)
  - TP: 3.0% (2:1 reward/risk)
  - Risk per trade: 2% of portfolio
  - Leverage: 3x
  - Commission: 0.1%
"""
import sys
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from collections import defaultdict

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, r"D:\dev\trading")

# --- Load Risk Config (for common settings) ---
with open(r"D:\dev\trading\risk_config.json", "r") as f:
    RISK_CONFIG = json.load(f)

# Risk Management Settings
INITIAL_BALANCE = RISK_CONFIG["initial_capital"]  # $1000
RISK_PER_TRADE_PCT = RISK_CONFIG["risk_per_trade_pct"]  # 0.02 (2%)
LEVERAGE = RISK_CONFIG["leverage"]  # 3x
COMMISSION_PCT = RISK_CONFIG["commission_pct"]  # 0.001 (0.1%)
SLIPPAGE_PCT = RISK_CONFIG["slippage_pct"]  # 0.0005 (0.05%)
MAX_POSITION_PCT = RISK_CONFIG["max_position_pct"]  # 0.5 (50%)

# OPTIMIZED Volume Spike Settings
STOP_LOSS_PCT = 0.015  # 1.5% - optimized for scalp
TAKE_PROFIT_PCT = 0.03  # 3.0% - 1:2 R/R
LOOKBACK_CANDLES = 16  # 16 × 15min = 4h rolling average
SPIKE_MULTIPLIER = 1.5  # Volume must be 1.5x average
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
    position_size: float
    margin_used: float


@dataclass
class BacktestResult:
    name: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl_usd: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_bars_held: float = 0.0
    max_bars_held: int = 0
    total_signals: int = 0
    long_trades: int = 0
    short_trades: int = 0
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


def detect_volume_spike(candles: List[dict], idx: int) -> Tuple[str, float, float]:
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
    if volume_ratio < SPIKE_MULTIPLIER:
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


def calculate_position_size(balance: float, entry_price: float) -> Tuple[float, float]:
    """
    Calculate position size based on risk management rules.
    Risk per trade = 2% of portfolio
    Position size = Risk Amount / (SL% × Leverage)
    """
    risk_amount = balance * RISK_PER_TRADE_PCT
    position_size = risk_amount / (STOP_LOSS_PCT * LEVERAGE)
    margin_required = position_size / LEVERAGE
    
    # Cap at max position percentage
    max_position = balance * MAX_POSITION_PCT
    if position_size > max_position:
        position_size = max_position
        margin_required = position_size / LEVERAGE
    
    return position_size, margin_required


def run_optimized_backtest(candles: List[dict]) -> BacktestResult:
    result = BacktestResult(name="Volume Spike Optimized (1.5% SL / 3% TP)")
    
    balance = INITIAL_BALANCE
    position = None
    equity_curve = [INITIAL_BALANCE]
    peak_balance = INITIAL_BALANCE
    warmup = LOOKBACK_CANDLES + PRICE_LOOKBACK + 5
    cooldown_bars = 0
    
    for i in range(warmup, len(candles)):
        current = candles[i]
        current_price = current["close"]
        current_high = current["high"]
        current_low = current["low"]
        current_time = current["timestamp"]
        
        # Update equity for drawdown tracking
        if position:
            entry_price = position["entry_price"]
            direction = position["direction"]
            if direction == "LONG":
                unrealized_pct = (current_price - entry_price) / entry_price
            else:
                unrealized_pct = (entry_price - current_price) / entry_price
            equity_curve.append(balance * (1 + unrealized_pct * RISK_PER_TRADE_PCT * LEVERAGE))
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
        
        # Check exit if in position
        if position:
            entry_price = position["entry_price"]
            direction = position["direction"]
            bars_held = i - position["entry_idx"]
            
            # Calculate P&L based on direction
            if direction == "LONG":
                pnl_pct = (current_price - entry_price) / entry_price
                # Check SL hit
                sl_price = entry_price * (1 - STOP_LOSS_PCT)
                if current_low <= sl_price:
                    exit_price = sl_price
                    exit_reason = "STOP_LOSS"
                # Check TP hit
                elif current_high >= entry_price * (1 + TAKE_PROFIT_PCT):
                    exit_price = entry_price * (1 + TAKE_PROFIT_PCT)
                    exit_reason = "TAKE_PROFIT"
                # End of data
                elif i == len(candles) - 1:
                    exit_reason = "END_OF_DATA"
                    exit_price = current_price
                else:
                    continue  # Still in position
            else:  # SHORT
                pnl_pct = (entry_price - current_price) / entry_price
                # Check SL hit
                sl_price = entry_price * (1 + STOP_LOSS_PCT)
                if current_high >= sl_price:
                    exit_price = sl_price
                    exit_reason = "STOP_LOSS"
                # Check TP hit
                elif current_low <= entry_price * (1 - TAKE_PROFIT_PCT):
                    exit_price = entry_price * (1 - TAKE_PROFIT_PCT)
                    exit_reason = "TAKE_PROFIT"
                # End of data
                elif i == len(candles) - 1:
                    exit_reason = "END_OF_DATA"
                    exit_price = current_price
                else:
                    continue  # Still in position
            
            position_size = position["position_size"]
            margin_used = position["margin_used"]
            
            # Calculate fees (entry + exit)
            fees = position_size * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
            
            # Calculate P&L
            pnl_usd = position_size * pnl_pct * LEVERAGE - fees
            
            trade = Trade(
                direction=direction,
                entry_price=entry_price,
                exit_price=exit_price,
                entry_time=position["entry_time"],
                exit_time=current_time,
                pnl_pct=pnl_pct * 100,
                pnl_usd=pnl_usd,
                exit_reason=exit_reason,
                volume_ratio=position["volume_ratio"],
                price_change_4h=position["price_change_4h"],
                bars_held=bars_held,
                position_size=position_size,
                margin_used=margin_used
            )
            
            result.trades.append(trade)
            result.total_trades += 1
            if direction == "LONG":
                result.long_trades += 1
            else:
                result.short_trades += 1
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
            action, vol_ratio, price_change = detect_volume_spike(candles, i)
            result.total_signals += 1  # Count all signals
            
            if action in ["BUY", "SELL"]:
                direction = "LONG" if action == "BUY" else "SHORT"
                
                # Calculate position size
                position_size, margin_required = calculate_position_size(balance, current_price)
                
                position = {
                    "direction": direction,
                    "entry_price": current_price,
                    "entry_time": current_time,
                    "entry_idx": i,
                    "volume_ratio": vol_ratio,
                    "price_change_4h": price_change,
                    "position_size": position_size,
                    "margin_used": margin_required
                }
                # Set cooldown (4 bars = 1 hour on 15m)
                cooldown_bars = 4
    
    result.total_pnl_pct = (result.total_pnl_usd / INITIAL_BALANCE) * 100
    if result.trades:
        result.avg_bars_held = sum(t.bars_held for t in result.trades) / len(result.trades)
    return result


def print_optimized_results(result: BacktestResult):
    print("\n" + "=" * 70)
    print("VOLUME SPIKE STRATEGY - OPTIMIZED SETTINGS (1.5% SL / 3% TP)")
    print("=" * 70)
    
    print("\n[ RISK CONFIGURATION ]")
    print(f"  Initial Capital: ${INITIAL_BALANCE:,.2f}")
    print(f"  Risk Per Trade: {RISK_PER_TRADE_PCT*100:.1f}% (${INITIAL_BALANCE * RISK_PER_TRADE_PCT:.2f})")
    print(f"  Stop Loss: {STOP_LOSS_PCT*100:.1f}%")
    print(f"  Take Profit: {TAKE_PROFIT_PCT*100:.1f}% (1:2 Risk/Reward)")
    print(f"  Leverage: {LEVERAGE}x")
    print(f"  Commission: {COMMISSION_PCT*100:.2f}%")
    print(f"  Slippage: {SLIPPAGE_PCT*100:.3f}%")
    
    print("\n[ STRATEGY PARAMETERS ]")
    print(f"  Volume Spike Multiplier: {SPIKE_MULTIPLIER}x")
    print(f"  Lookback: {LOOKBACK_CANDLES} candles (4h rolling average)")
    print(f"  Price Lookback: {PRICE_LOOKBACK} candles (4h price direction)")
    
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)
    
    print(f"\n[ SIGNALS ]")
    print(f"  Total Signals Generated: {result.total_signals}")
    print(f"  Signals Filtered (cooldown): {result.total_signals - result.total_trades}")
    print(f"  Actual Trades Taken: {result.total_trades}")
    
    print(f"\n[ PERFORMANCE ]")
    print(f"  Total P&L: ${result.total_pnl_usd:+,.2f} ({result.total_pnl_pct:+.2f}%)")
    print(f"  Win Rate: {result.win_rate:.1f}%")
    print(f"  Profit Factor: {result.profit_factor:.2f}")
    print(f"  Max Drawdown: {result.max_drawdown_pct:.2f}%")
    
    print(f"\n[ TRADE STATISTICS ]")
    print(f"  Winning Trades: {result.winning_trades}")
    print(f"  Losing Trades: {result.losing_trades}")
    print(f"  Long Trades: {result.long_trades}")
    print(f"  Short Trades: {result.short_trades}")
    avg_hours = (result.avg_bars_held * 15) / 60
    max_hours = (result.max_bars_held * 15) / 60
    print(f"  Average Hold Time: {avg_hours:.1f} hours")
    print(f"  Max Hold Time: {max_hours:.1f} hours")
    
    # Exit reason breakdown
    exit_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0})
    for t in result.trades:
        exit_stats[t.exit_reason]["trades"] += 1
        exit_stats[t.exit_reason]["pnl"] += t.pnl_usd
        if t.pnl_usd > 0:
            exit_stats[t.exit_reason]["wins"] += 1
    
    print(f"\n[ EXIT BREAKDOWN ]")
    for reason, stats in sorted(exit_stats.items(), key=lambda x: -x[1]["trades"]):
        wr = (stats["wins"] / stats["trades"] * 100) if stats["trades"] > 0 else 0
        print(f"  {reason:15}: {stats['trades']:4} trades | {wr:5.1f}% WR | ${stats['pnl']:+,.2f}")
    
    # Signal frequency
    data_days = 105120 / 96  # 15-min candles per day
    signals_per_day = result.total_signals / data_days
    trades_per_day = result.total_trades / data_days
    trades_per_month = trades_per_day * 30
    
    print(f"\n[ SIGNAL FREQUENCY ]")
    print(f"  Data Period: ~{data_days:.0f} days (~3 years)")
    print(f"  Signals per Day: {signals_per_day:.1f}")
    print(f"  Trades per Day: {trades_per_day:.1f}")
    print(f"  Trades per Month: {trades_per_month:.0f}")
    print(f"  Signal-to-Trade Ratio: {result.total_trades/result.total_signals*100:.1f}%")
    
    # Monthly return estimate
    avg_pnl_per_trade = result.total_pnl_usd / result.total_trades if result.total_trades > 0 else 0
    monthly_pnl = trades_per_month * avg_pnl_per_trade
    monthly_return_pct = (monthly_pnl / INITIAL_BALANCE) * 100
    
    print(f"\n[ PROJECTIONS ]")
    print(f"  Avg P&L per Trade: ${avg_pnl_per_trade:+.2f}")
    print(f"  Est. Monthly Return: ${monthly_pnl:+.2f} ({monthly_return_pct:+.2f}%)")
    print(f"  Est. Annual Return: {monthly_return_pct * 12:+.1f}%")
    
    print("\n" + "=" * 70)


def run_backtest():
    print("=" * 70)
    print("VOLUME SPIKE STRATEGY BACKTEST - OPTIMIZED (1.5% SL / 3% TP)")
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
    
    print("Running Volume Spike backtest with optimized settings...")
    result = run_optimized_backtest(candles)
    print_optimized_results(result)


if __name__ == "__main__":
    run_backtest()
