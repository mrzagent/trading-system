#!/usr/bin/env python3
"""
backtest_momentum_scalper_binance.py — Momentum Scalper backtest on Binance BTC data

Strategy: Momentum Scalper (5M candles)
- EMA9 > EMA21 > EMA50 (bullish) or EMA9 < EMA21 < EMA50 (bearish)
- Close breaks above/below swing high/low
- Volume > 1.5 × SMA20(volume)
- ATR-based stop loss and take profit (2R)

Uses 5-minute candles from binance_btc_5min table.
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

import numpy as np
import psycopg2

sys.path.insert(0, r"D:\dev\trading")

# --- Configuration ---
INITIAL_BALANCE = 10000.0  # $10k starting balance
LEVERAGE = 3.0
TRADING_FEE_PCT = 0.0005  # 0.05% per trade (Binance futures)
PORTFOLIO_PCT = 0.05      # 5% of portfolio per trade

# Momentum Scalper Parameters
EMA_FAST = 9
EMA_MID = 21
EMA_SLOW = 50
VOLUME_MULT = 1.5
ATR_PERIOD = 14
LOOKBACK_SWING = 10

# Risk Management
ATR_MULTIPLIER_SL = 1.5   # Stop loss = 1.5x ATR
ATR_MULTIPLIER_TP = 3.0   # Take profit = 3x ATR (2R ratio)

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
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    pnl_pct: float
    pnl_usd: float
    exit_reason: str
    ema9_at_entry: float = 0.0
    ema21_at_entry: float = 0.0
    ema50_at_entry: float = 0.0
    volume_ratio_at_entry: float = 0.0
    atr_at_entry: float = 0.0


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


def fetch_candles(conn, limit: int = None):
    """Fetch candles from Binance table, ordered chronologically."""
    sql = f"""
        SELECT open_time, close_time, open_price, high_price, low_price, close_price,
               volume, quote_volume, trades_count
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
            # Convert Decimal to float
            for key in ['open_price', 'high_price', 'low_price', 'close_price', 'volume', 'quote_volume']:
                if key in row_dict and row_dict[key] is not None:
                    row_dict[key] = float(row_dict[key])
            rows.append(row_dict)
    return rows


def calculate_ema(prices: List[float], period: int) -> List[float]:
    """Compute EMA series."""
    n = len(prices)
    if n < period:
        return [float("nan")] * n
    
    ema_values = [float("nan")] * n
    multiplier = 2.0 / (period + 1)
    seed = sum(prices[:period]) / period
    ema_values[period - 1] = seed
    
    for i in range(period, n):
        ema_values[i] = (prices[i] - ema_values[i - 1]) * multiplier + ema_values[i - 1]
    
    return ema_values


def calculate_atr_series(highs: List[float], lows: List[float], closes: List[float], period: int) -> List[float]:
    """Compute ATR series."""
    n = len(closes)
    atr_series = [float("nan")] * n
    
    if n < period + 1:
        return atr_series
    
    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    
    if len(trs) < period:
        return atr_series
    
    first_atr = sum(trs[:period]) / period
    atr_series[period] = first_atr
    
    for i in range(period, len(trs)):
        atr_series[i + 1] = (atr_series[i] * (period - 1) + trs[i]) / period
    
    return atr_series


def calculate_sma_scalar(values: List[float], period: int) -> float:
    """Simple moving average over last period values."""
    filtered = [v for v in values[-period:] if v == v]
    if len(filtered) < period:
        return float("nan")
    return sum(filtered) / period


def get_swing_high(highs: List[float], lookback: int) -> float:
    """Return highest high over last lookback bars (excluding current)."""
    window = highs[-lookback - 1:-1]
    return max(window) if window else float("nan")


def get_swing_low(lows: List[float], lookback: int) -> float:
    """Return lowest low over last lookback bars (excluding current)."""
    window = lows[-lookback - 1:-1]
    return min(window) if window else float("nan")


def generate_signal(candles: List[dict], idx: int) -> dict:
    """Generate trading signal based on Momentum Scalper strategy."""
    min_rows = max(EMA_SLOW, ATR_PERIOD, LOOKBACK_SWING, 20) + 10
    
    if idx < min_rows:
        return {"action": "HOLD", "reason": "insufficient data"}
    
    # Extract series up to current index
    closes = [c["close_price"] for c in candles[:idx+1]]
    highs = [c["high_price"] for c in candles[:idx+1]]
    lows = [c["low_price"] for c in candles[:idx+1]]
    volumes = [c["volume"] for c in candles[:idx+1]]
    
    current = candles[idx]
    price = current["close_price"]
    
    # Calculate EMAs
    ema_fast_series = calculate_ema(closes, EMA_FAST)
    ema_mid_series = calculate_ema(closes, EMA_MID)
    ema_slow_series = calculate_ema(closes, EMA_SLOW)
    
    ema_fast = ema_fast_series[-1]
    ema_mid = ema_mid_series[-1]
    ema_slow = ema_slow_series[-1]
    
    if any(v != v for v in [ema_fast, ema_mid, ema_slow]):
        return {"action": "HOLD", "reason": "EMA NaN"}
    
    # EMA Stack conditions
    bullish_stack = ema_fast > ema_mid > ema_slow
    bearish_stack = ema_fast < ema_mid < ema_slow
    
    # Swing high/low
    swing_high = get_swing_high(highs, LOOKBACK_SWING)
    swing_low = get_swing_low(lows, LOOKBACK_SWING)
    
    if swing_high != swing_high or swing_low != swing_low:
        return {"action": "HOLD", "reason": "swing NaN"}
    
    broke_above_swing = price > swing_high
    broke_below_swing = price < swing_low
    
    # Volume check
    vol_sma20 = calculate_sma_scalar(volumes[:-1], 20)
    current_vol = volumes[-1]
    
    if vol_sma20 != vol_sma20 or vol_sma20 == 0:
        volume_spike = False
        volume_ratio = float("nan")
    else:
        volume_ratio = current_vol / vol_sma20
        volume_spike = volume_ratio >= VOLUME_MULT
    
    # ATR for stop loss
    atr_series = calculate_atr_series(highs, lows, closes, ATR_PERIOD)
    current_atr = atr_series[-1]
    
    if current_atr != current_atr:
        return {"action": "HOLD", "reason": "ATR NaN"}
    
    # LONG signal
    if bullish_stack and broke_above_swing and volume_spike:
        breakout_pct = (price - swing_high) / swing_high * 100
        
        # Confidence calculation
        ema_fast_mid_sep = (ema_fast - ema_mid) / ema_mid * 100
        ema_mid_slow_sep = (ema_mid - ema_slow) / ema_slow * 100
        
        conf = 0.55
        conf += min(ema_fast_mid_sep * 0.4 + ema_mid_slow_sep * 0.3, 0.10)
        conf += min((volume_ratio - VOLUME_MULT) * 0.06 + 0.05, 0.10)
        conf += min(breakout_pct * 0.5, 0.05)
        conf = round(min(conf, 0.95), 2)
        
        # Stop loss distance
        swing_sl_dist = price - swing_low
        atr_sl_dist = current_atr * ATR_MULTIPLIER_SL
        sl_dist = min(swing_sl_dist, atr_sl_dist)
        
        sl_price = price - sl_dist
        tp_price = price + sl_dist * 2.0  # 2R
        
        return {
            "action": "BUY",
            "price": price,
            "confidence": conf,
            "ema9": ema_fast,
            "ema21": ema_mid,
            "ema50": ema_slow,
            "swing_high": swing_high,
            "swing_low": swing_low,
            "volume_ratio": volume_ratio,
            "atr": current_atr,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "breakout_pct": breakout_pct
        }
    
    # SHORT signal
    if bearish_stack and broke_below_swing and volume_spike:
        breakdown_pct = (swing_low - price) / swing_low * 100
        
        ema_fast_mid_sep = (ema_mid - ema_fast) / ema_mid * 100
        ema_mid_slow_sep = (ema_slow - ema_mid) / ema_slow * 100
        
        conf = 0.55
        conf += min(ema_fast_mid_sep * 0.4 + ema_mid_slow_sep * 0.3, 0.10)
        conf += min((volume_ratio - VOLUME_MULT) * 0.06 + 0.05, 0.10)
        conf += min(breakdown_pct * 0.5, 0.05)
        conf = round(min(conf, 0.95), 2)
        
        swing_sl_dist = swing_high - price
        atr_sl_dist = current_atr * ATR_MULTIPLIER_SL
        sl_dist = min(swing_sl_dist, atr_sl_dist)
        
        sl_price = price + sl_dist
        tp_price = price - sl_dist * 2.0  # 2R
        
        return {
            "action": "SELL",
            "price": price,
            "confidence": conf,
            "ema9": ema_fast,
            "ema21": ema_mid,
            "ema50": ema_slow,
            "swing_high": swing_high,
            "swing_low": swing_low,
            "volume_ratio": volume_ratio,
            "atr": current_atr,
            "sl_price": sl_price,
            "tp_price": tp_price,
            "breakdown_pct": breakdown_pct
        }
    
    # HOLD - determine why
    reasons = []
    if not bullish_stack and not bearish_stack:
        reasons.append(f"no EMA stack")
    if not broke_above_swing and not broke_below_swing:
        reasons.append("no swing breakout")
    if not volume_spike:
        reasons.append(f"low volume ({volume_ratio:.2f}x)")
    
    return {"action": "HOLD", "reason": " | ".join(reasons)}


def run_backtest(candle_limit: int = None):
    """Run the full backtest."""
    print("=" * 70)
    print("MOMENTUM SCALPER — BACKTEST RESULTS")
    print("=" * 70)
    print(f"Portfolio:         ${INITIAL_BALANCE:,.2f}")
    print(f"Position Size:     {PORTFOLIO_PCT*100:.0f}% of portfolio")
    print(f"Leverage:          {LEVERAGE}x")
    print(f"Trading Fee:       {TRADING_FEE_PCT*100:.3f}% per trade")
    print()
    print("Strategy Config:")
    print(f"  EMA Stack:       EMA{EMA_FAST} > EMA{EMA_MID} > EMA{EMA_SLOW}")
    print(f"  Swing Lookback:  {LOOKBACK_SWING} bars")
    print(f"  Volume Multiplier: {VOLUME_MULT}x SMA20")
    print(f"  ATR Period:      {ATR_PERIOD}")
    print(f"  ATR SL Multiplier: {ATR_MULTIPLIER_SL}x")
    print(f"  ATR TP Multiplier: {ATR_MULTIPLIER_TP}x (2R)")
    print("=" * 70)
    
    conn = get_conn()
    candles = fetch_candles(conn, candle_limit)
    conn.close()
    
    print(f"\nLoaded {len(candles)} candles from {TABLE_NAME}")
    if candles:
        print(f"Date Range: {candles[0]['open_time']} to {candles[-1]['close_time']}")
    print()
    
    result = BacktestResult()
    balance = INITIAL_BALANCE
    position = None
    
    for i in range(len(candles)):
        current = candles[i]
        current_time = current["open_time"]
        price = current["close_price"]
        
        # Check for exit if in position
        if position:
            should_exit = False
            exit_reason = None
            exit_price = price
            
            if position["direction"] == "LONG":
                # Check SL
                if price <= position["sl_price"]:
                    should_exit = True
                    exit_reason = "SL"
                    exit_price = position["sl_price"]
                # Check TP
                elif price >= position["tp_price"]:
                    should_exit = True
                    exit_reason = "TP"
                    exit_price = position["tp_price"]
            else:  # SHORT
                # Check SL
                if price >= position["sl_price"]:
                    should_exit = True
                    exit_reason = "SL"
                    exit_price = position["sl_price"]
                # Check TP
                elif price <= position["tp_price"]:
                    should_exit = True
                    exit_reason = "TP"
                    exit_price = position["tp_price"]
            
            if should_exit:
                # Calculate P&L
                if position["direction"] == "LONG":
                    pnl_pct = ((exit_price - position["entry_price"]) / position["entry_price"]) * LEVERAGE
                else:
                    pnl_pct = ((position["entry_price"] - exit_price) / position["entry_price"]) * LEVERAGE
                
                position_size = (INITIAL_BALANCE * PORTFOLIO_PCT) * LEVERAGE
                pnl_usd = position_size * pnl_pct
                
                # Deduct fees (entry + exit)
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
                    ema9_at_entry=position.get("ema9", 0),
                    ema21_at_entry=position.get("ema21", 0),
                    ema50_at_entry=position.get("ema50", 0),
                    volume_ratio_at_entry=position.get("volume_ratio", 0),
                    atr_at_entry=position.get("atr", 0)
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
        
        # Check for entry if not in position
        if not position and i < len(candles) - 1:
            signal = generate_signal(candles, i)
            
            if signal["action"] in ["BUY", "SELL"]:
                direction = "LONG" if signal["action"] == "BUY" else "SHORT"
                
                position = {
                    "direction": direction,
                    "entry_price": signal["price"],
                    "entry_time": current_time,
                    "sl_price": signal["sl_price"],
                    "tp_price": signal["tp_price"],
                    "ema9": signal["ema9"],
                    "ema21": signal["ema21"],
                    "ema50": signal["ema50"],
                    "volume_ratio": signal["volume_ratio"],
                    "atr": signal["atr"]
                }
    
    # Calculate final stats
    result.total_pnl_pct = ((balance - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
    
    # Calculate max drawdown
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
    
    # Print trade breakdown by direction
    if result.trades:
        long_trades = [t for t in result.trades if t.direction == "LONG"]
        short_trades = [t for t in result.trades if t.direction == "SHORT"]
        
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
        print()
    
    # Print exit reason breakdown
    if result.trades:
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
    
    # Print recent trades
    if result.trades:
        print("Recent Trades (last 15):")
        print("-" * 70)
        for t in result.trades[-15:]:
            pnl_str = f"${t.pnl_usd:+.2f}"
            print(f"{t.exit_time.strftime('%Y-%m-%d %H:%M')} | {t.direction:5} | "
                  f"Entry: ${t.entry_price:,.2f} | Exit: ${t.exit_price:,.2f} | "
                  f"P&L: {pnl_str:>10} | {t.exit_reason}")
    
    print()
    print("=" * 70)
    
    return result


if __name__ == "__main__":
    run_backtest()
