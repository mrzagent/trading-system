#!/usr/bin/env python3
"""
backtest_fvg_binance.py — Fair Value Gap (FVG) Scalping Strategy Backtest

Uses 5-minute candles from binance_btc_5min table.

Strategy Logic:
  - Detect Fair Value Gaps (3-candle pattern)
  - Bullish FVG: Enter LONG when price retraces to FVG zone (demand)
  - Bearish FVG: Enter SHORT when price retraces to FVG zone (supply)
  - Tight risk management for scalping

FVG Detection:
  Bullish: prev.high < next.low  (gap below price = demand zone)
  Bearish: prev.low > next.high  (gap above price = supply zone)
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Tuple

import numpy as np
import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, r"D:\dev\trading")

# --- Configuration ---
INITIAL_BALANCE = 10000.0  # $10k starting balance
LEVERAGE = 3.0
TRADING_FEE_PCT = 0.0005   # 0.05% per trade (Binance futures)
PORTFOLIO_PCT = 0.05       # 5% of portfolio per trade

# FVG Detection Settings
FVG_LOOKBACK_CANDLES = 20  # Only look at recent FVGs
FVG_MAX_AGE_CANDLES = 20   # Only trade fresh FVGs (max 20 candles old)

# Entry Settings - Only trade fresh FVGs on first touch
MIN_CONFIDENCE = 0.5       # Minimum confidence threshold

# Exit Settings - Tighter for scalping
ATR_PERIOD = 14
ATR_SL_MULTIPLIER = 1.0    # Very tight stops - FVG should hold or we're wrong
ATR_TP_MULTIPLIER = 2.0    # 1:2 R/R
MAX_BARS_IN_TRADE = 6      # Max 6 candles (30 min) - quick scalp

# Cooldown
COOLDOWN_CANDLES = 6       # 6 candles (30 min) between trades

# Trend Filter (optional)
USE_TREND_FILTER = True
TREND_LOOKBACK = 50
TREND_SLOPE_THRESHOLD = 0.01

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
    direction: str           # "LONG" or "SHORT"
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    pnl_pct: float
    pnl_usd: float
    exit_reason: str
    fvg_type: str
    fvg_mid: float
    fvg_age_candles: int
    confidence: float
    atr_at_entry: float
    trend_at_entry: str
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
    """Return a new psycopg2 connection."""
    return psycopg2.connect(**DB_DEFAULTS)


def fetch_candles(conn, limit: int = None) -> List[dict]:
    """Fetch 5-minute candles from Binance table."""
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


def calculate_atr(candles: List[dict], idx: int, period: int = 14) -> Optional[float]:
    """Calculate Average True Range."""
    if idx < period:
        return None
    
    tr_list = []
    for i in range(idx - period + 1, idx + 1):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i-1]["close"]
        
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)
    
    return sum(tr_list) / len(tr_list)


def calculate_trend(candles: List[dict], idx: int, lookback: int = 50) -> str:
    """Determine trend direction. Returns: "UP", "DOWN", or "RANGING"."""
    if idx < lookback:
        return "UNKNOWN"
    
    prices = np.array([c["close"] for c in candles[idx-lookback:idx+1]])
    x = np.arange(len(prices))
    slope, _ = np.polyfit(x, prices, 1)
    
    avg_price = np.mean(prices)
    normalized_slope = (slope / avg_price) * 100 if avg_price > 0 else 0
    
    if normalized_slope > TREND_SLOPE_THRESHOLD:
        return "UP"
    elif normalized_slope < -TREND_SLOPE_THRESHOLD:
        return "DOWN"
    return "RANGING"


def detect_fvgs(candles: List[dict], current_idx: int) -> List[dict]:
    """
    Detect all active Fair Value Gaps up to current_idx.
    Returns list of FVGs with their properties.
    """
    fvgs = []
    
    start_idx = max(1, current_idx - FVG_LOOKBACK_CANDLES)
    
    for i in range(start_idx, current_idx):
        if i < 1 or i >= len(candles) - 1:
            continue
        
        prev = candles[i - 1]
        curr = candles[i]
        nxt = candles[i + 1]
        
        # Bullish FVG: prev.high < next.low (demand gap)
        if prev["high"] < nxt["low"]:
            fvgs.append({
                "type": "bullish",
                "bottom": prev["high"],
                "top": nxt["low"],
                "midpoint": (prev["high"] + nxt["low"]) / 2,
                "formed_at_idx": i,
                "age_candles": current_idx - i
            })
        
        # Bearish FVG: prev.low > next.high (supply gap)
        elif prev["low"] > nxt["high"]:
            fvgs.append({
                "type": "bearish",
                "top": prev["low"],
                "bottom": nxt["high"],
                "midpoint": (prev["low"] + nxt["high"]) / 2,
                "formed_at_idx": i,
                "age_candles": current_idx - i
            })
    
    # Filter out old FVGs and sort by recency
    fvgs = [f for f in fvgs if f["age_candles"] <= FVG_MAX_AGE_CANDLES]
    fvgs.sort(key=lambda x: x["age_candles"])
    
    return fvgs


def check_fvg_signal(price: float, fvgs: List[dict], current_idx: int) -> Tuple[str, float, Optional[dict]]:
    """
    Check if price is inside any FVG zone (the actual gap).
    Only trade on FIRST touch of a fresh FVG (formed within last few candles).
    Returns: (action, confidence, fvg_data)
    """
    best_action = "HOLD"
    best_conf = 0.0
    best_fvg = None
    
    for fvg in fvgs:
        ftype = fvg["type"]
        formed_idx = fvg["formed_at_idx"]
        age = current_idx - formed_idx
        
        # Only trade FVGs that are fresh (1-5 candles old) - first touch only
        if age < 1 or age > 5:
            continue
        
        if ftype == "bullish":
            bottom = fvg["bottom"]
            top = fvg["top"]
            
            # Price must be INSIDE the bullish FVG zone
            if bottom <= price <= top:
                # Higher confidence when closer to bottom (better R/R)
                zone_size = top - bottom
                if zone_size > 0:
                    distance_from_bottom = price - bottom
                    conf = 1.0 - (distance_from_bottom / zone_size)
                    if conf > best_conf and conf >= MIN_CONFIDENCE:
                        best_action = "BUY"
                        best_conf = conf
                        best_fvg = fvg
        
        elif ftype == "bearish":
            top = fvg["top"]
            bottom = fvg["bottom"]
            
            # Price must be INSIDE the bearish FVG zone
            if bottom <= price <= top:
                # Higher confidence when closer to top (better R/R)
                zone_size = top - bottom
                if zone_size > 0:
                    distance_from_top = top - price
                    conf = 1.0 - (distance_from_top / zone_size)
                    if conf > best_conf and conf >= MIN_CONFIDENCE:
                        best_action = "SELL"
                        best_conf = conf
                        best_fvg = fvg
    
    return best_action, best_conf, best_fvg


def run_backtest(candle_limit: int = None):
    """Run the FVG scalping backtest."""
    print("=" * 70)
    print("FVG SCALPING STRATEGY BACKTEST (Binance 5min Data)")
    print("=" * 70)
    print()
    
    # Fetch data
    print("Fetching data from PostgreSQL...")
    conn = get_conn()
    candles = fetch_candles(conn, limit=candle_limit)
    conn.close()
    
    if not candles:
        print("ERROR: No data found in table")
        return
    
    print(f"Loaded {len(candles):,} candles")
    print(f"Date range: {candles[0]['timestamp']} to {candles[-1]['timestamp']}")
    print()
    
    # Backtest state
    balance = INITIAL_BALANCE
    position = None
    result = BacktestResult()
    equity_curve = [INITIAL_BALANCE]
    peak_balance = INITIAL_BALANCE
    last_trade_idx = -COOLDOWN_CANDLES - 1
    
    # Warmup period
    warmup = max(FVG_LOOKBACK_CANDLES, ATR_PERIOD, TREND_LOOKBACK) + 10
    
    print("Running backtest...")
    print()
    
    for i in range(warmup, len(candles)):
        current = candles[i]
        current_price = current["close"]
        current_time = current["timestamp"]
        
        # Update equity curve
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
        
        # Update peak and drawdown
        if equity_curve[-1] > peak_balance:
            peak_balance = equity_curve[-1]
        drawdown = (peak_balance - equity_curve[-1]) / peak_balance
        if drawdown > result.max_drawdown_pct:
            result.max_drawdown_pct = drawdown * 100
        
        # Check for exit if in position
        if position:
            entry_price = position["entry_price"]
            direction = position["direction"]
            entry_atr = position["atr"]
            bars_in_trade = i - position["entry_idx"]
            
            # Calculate ATR-based SL/TP
            sl_distance = entry_atr * ATR_SL_MULTIPLIER / entry_price
            tp_distance = entry_atr * ATR_TP_MULTIPLIER / entry_price
            
            # Calculate P&L
            if direction == "LONG":
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price
            
            # Check exit conditions
            exit_reason = None
            if pnl_pct <= -sl_distance:
                exit_reason = "STOP_LOSS"
            elif pnl_pct >= tp_distance:
                exit_reason = "TAKE_PROFIT"
            elif bars_in_trade >= MAX_BARS_IN_TRADE:
                exit_reason = "MAX_BARS"
            elif i == len(candles) - 1:
                exit_reason = "END_OF_DATA"
            
            if exit_reason:
                # Close position
                position_value = balance * PORTFOLIO_PCT
                fees = position_value * TRADING_FEE_PCT * 2  # Entry + exit
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
                    fvg_mid=position["fvg_mid"],
                    fvg_age_candles=position["fvg_age"],
                    confidence=position["confidence"],
                    atr_at_entry=entry_atr,
                    trend_at_entry=position["trend"],
                    bars_held=bars_in_trade
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
        
        # Check for entry if not in position and cooldown passed
        elif i - last_trade_idx >= COOLDOWN_CANDLES:
            # Detect FVGs
            fvgs = detect_fvgs(candles, i)
            
            # Check for signal
            action, confidence, fvg = check_fvg_signal(current_price, fvgs, i)
            
            if action in ["BUY", "SELL"] and fvg:
                direction = "LONG" if action == "BUY" else "SHORT"
                
                # Trend filter
                trend = calculate_trend(candles, i, TREND_LOOKBACK)
                if USE_TREND_FILTER:
                    if direction == "LONG" and trend == "DOWN":
                        continue
                    if direction == "SHORT" and trend == "UP":
                        continue
                
                # Get ATR
                atr = calculate_atr(candles, i, ATR_PERIOD)
                if atr is None:
                    continue
                
                # Enter position
                position = {
                    "direction": direction,
                    "entry_price": current_price,
                    "entry_time": current_time,
                    "entry_idx": i,
                    "fvg_type": fvg["type"],
                    "fvg_mid": fvg["midpoint"],
                    "fvg_age": fvg["age_candles"],
                    "confidence": confidence,
                    "atr": atr,
                    "trend": trend
                }
                last_trade_idx = i
    
    # Calculate final stats
    result.total_pnl_pct = (result.total_pnl_usd / INITIAL_BALANCE) * 100
    
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
    
    # Configuration summary
    print("=" * 70)
    print("CONFIGURATION")
    print("=" * 70)
    print(f"FVG Lookback:       {FVG_LOOKBACK_CANDLES} candles")
    print(f"FVG Max Age:        {FVG_MAX_AGE_CANDLES} candles")
    print(f"Entry Condition:    Price INSIDE FVG zone")
    print(f"Min Confidence:     {MIN_CONFIDENCE}")
    print(f"ATR Period:         {ATR_PERIOD}")
    print(f"ATR SL Multiplier:  {ATR_SL_MULTIPLIER}x")
    print(f"ATR TP Multiplier:  {ATR_TP_MULTIPLIER}x")
    print(f"Max Bars in Trade:  {MAX_BARS_IN_TRADE} ({MAX_BARS_IN_TRADE * 5} min)")
    print(f"Cooldown:           {COOLDOWN_CANDLES} candles ({COOLDOWN_CANDLES * 5} min)")
    print(f"Trend Filter:       {'ENABLED' if USE_TREND_FILTER else 'DISABLED'}")
    print()
    
    # Performance by FVG type
    if result.trades:
        bullish_trades = [t for t in result.trades if t.fvg_type == "bullish"]
        bearish_trades = [t for t in result.trades if t.fvg_type == "bearish"]
        
        print("Performance by FVG Type:")
        print("-" * 70)
        if bullish_trades:
            wins = sum(1 for t in bullish_trades if t.pnl_usd > 0)
            pnl = sum(t.pnl_usd for t in bullish_trades)
            print(f"  Bullish FVGs | Trades: {len(bullish_trades):3} | Win Rate: {wins/len(bullish_trades)*100:5.1f}% | P&L: ${pnl:+.2f}")
        if bearish_trades:
            wins = sum(1 for t in bearish_trades if t.pnl_usd > 0)
            pnl = sum(t.pnl_usd for t in bearish_trades)
            print(f"  Bearish FVGs | Trades: {len(bearish_trades):3} | Win Rate: {wins/len(bearish_trades)*100:5.1f}% | P&L: ${pnl:+.2f}")
        print()
        
        # Performance by exit reason
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
            print(f"  {reason:15} | Trades: {stats['trades']:3} | Win Rate: {wr:5.1f}% | P&L: ${stats['pnl']:+.2f}")
        print()
        
        # Recent trades
        print("Recent Trades (last 10):")
        print("-" * 70)
        for t in result.trades[-10:]:
            pnl_str = f"${t.pnl_usd:+.2f}"
            print(f"{t.exit_time.strftime('%Y-%m-%d %H:%M')} | {t.direction:5} | "
                  f"FVG: {t.fvg_type:7} | Age: {t.fvg_age_candles:3}c | "
                  f"Conf: {t.confidence:.2f} | P&L: {pnl_str:>10} | {t.exit_reason}")
    
    print()
    print("=" * 70)
    
    return result


if __name__ == "__main__":
    run_backtest()
