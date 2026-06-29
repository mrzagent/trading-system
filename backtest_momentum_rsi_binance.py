#!/usr/bin/env python3
"""
backtest_momentum_rsi_binance.py — Momentum + RSI strategy backtest on Binance data

Uses 5-minute candles from binance_btc_5min table.

Signal logic:
  BUY: Momentum bullish + RSI has room to rise + Uptrend confirmed
  SELL: Momentum bearish + RSI has room to fall + Downtrend confirmed

Enhancements (2026-06-24):
1. TREND FILTER: Only trade long in uptrends, short in downtrends
   - Uses linear regression slope over 50 periods
   - Eliminates counter-trend trades in ranging markets
   
2. ATR-BASED STOPS: Dynamic stop loss based on market volatility
   - Stop Loss = 1.5x ATR (adapts to BTC volatility)
   - Take Profit = 3x ATR (maintains 1:2 R/R ratio)
   - Replaces fixed 3% stop that was too tight for Bitcoin
   
3. MACRO FILTER: Avoid RSI >70 shorts in bullish macro conditions
   - Prevents shorting into strong uptrends where RSI can stay elevated
   - Uses 100-period macro trend determination
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
STOP_LOSS_PCT = 0.03      # 3% stop loss (tighter for scalping) - DEPRECATED: now using ATR-based stops
TAKE_PROFIT_PCT = 0.06    # 6% take profit (1:2 R/R)

# RSI thresholds
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
RSI_MID_LOW = 40
RSI_MID_HIGH = 60

# Momentum calculation lookback
MOMENTUM_LOOKBACK = 3  # periods

# --- Trend Filter Configuration ---
TREND_LOOKBACK = 50       # Periods for trend calculation
TREND_SLOPE_THRESHOLD = 0.02  # Minimum normalized slope to consider a trend
USE_TREND_FILTER = True   # Only trade long in uptrends, short in downtrends

# --- ATR-Based Stop Configuration ---
ATR_PERIOD = 14           # Periods for ATR calculation
ATR_MULTIPLIER_SL = 1.5   # Stop loss = 1.5x ATR (tighter than 2x)
ATR_MULTIPLIER_TP = 3.0   # Take profit = 3x ATR (maintains 1:2 R/R)
USE_ATR_STOPS = True      # Use ATR-based stops instead of fixed percentage

# --- Macro Filter Configuration ---
MACRO_LOOKBACK = 100      # Periods for macro trend determination
MACRO_SLOPE_THRESHOLD = 0.015  # Threshold for bullish/bearish macro
AVOID_RSI_OVERBOUGHT_SHORTS = True  # Don't short when RSI > 70 in bullish macro

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
    rsi_at_entry: float
    momentum_at_entry: float
    exit_reason: str
    atr_at_entry: float = 0.0
    trend_at_entry: str = "UNKNOWN"
    trend_slope_at_entry: float = 0.0
    macro_trend_at_entry: str = "UNKNOWN"


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


def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """Calculate RSI from price series."""
    if len(prices) < period + 1:
        return None
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    if len(gains) < period:
        return None
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_momentum(prices: List[float], lookback: int = 3) -> Optional[float]:
    """Calculate momentum as percentage change."""
    if len(prices) < lookback + 1:
        return None
    
    current = prices[-1]
    previous = prices[-(lookback + 1)]
    
    if previous == 0:
        return 0
    
    return ((current - previous) / previous) * 100


def calculate_atr(candles: List[dict], idx: int, period: int = 14) -> Optional[float]:
    """Calculate Average True Range from candle data."""
    if idx < period:
        return None
    
    tr_list = []
    for i in range(idx - period + 1, idx + 1):
        high = candles[i]["high_price"]
        low = candles[i]["low_price"]
        prev_close = candles[i-1]["close_price"]
        
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        tr_list.append(tr)
    
    return sum(tr_list) / len(tr_list)


def calculate_trend(candles: List[dict], idx: int, lookback: int = 50) -> Tuple[str, float]:
    """
    Determine trend direction and strength.
    Returns: (trend_direction, normalized_slope)
    Trend direction: "UP", "DOWN", or "RANGING"
    """
    if idx < lookback:
        return "UNKNOWN", 0.0
    
    prices = np.array([c["close_price"] for c in candles[idx-lookback:idx+1]])
    
    # Calculate linear regression slope using numpy (faster)
    x = np.arange(len(prices))
    slope, intercept = np.polyfit(x, prices, 1)
    
    # Normalize slope as % of average price
    avg_price = np.mean(prices)
    normalized_slope = (slope / avg_price) * 100 if avg_price > 0 else 0
    
    # Classify trend
    if normalized_slope > TREND_SLOPE_THRESHOLD:
        return "UP", normalized_slope
    elif normalized_slope < -TREND_SLOPE_THRESHOLD:
        return "DOWN", normalized_slope
    else:
        return "RANGING", normalized_slope


def get_macro_trend(candles: List[dict], idx: int) -> str:
    """
    Determine macro trend for RSI overbought filtering.
    Returns: "BULLISH", "BEARISH", or "NEUTRAL"
    """
    if idx < MACRO_LOOKBACK:
        return "NEUTRAL"
    
    prices = np.array([c["close_price"] for c in candles[idx-MACRO_LOOKBACK:idx+1]])
    
    # Calculate linear regression slope using numpy (faster)
    x = np.arange(len(prices))
    slope, intercept = np.polyfit(x, prices, 1)
    
    avg_price = np.mean(prices)
    normalized_slope = (slope / avg_price) * 100 if avg_price > 0 else 0
    
    if normalized_slope > MACRO_SLOPE_THRESHOLD:
        return "BULLISH"
    elif normalized_slope < -MACRO_SLOPE_THRESHOLD:
        return "BEARISH"
    return "NEUTRAL"


def generate_signal(candles: List[dict], idx: int) -> dict:
    """Generate trading signal based on Momentum + RSI + Trend Filter."""
    if idx < max(RSI_PERIOD + MOMENTUM_LOOKBACK, TREND_LOOKBACK, ATR_PERIOD):
        return {"action": "HOLD", "reason": "insufficient data"}
    
    # Build price history for calculations
    prices = [c["close_price"] for c in candles[:idx+1]]
    current = candles[idx]
    
    # Calculate indicators
    rsi = calculate_rsi(prices, RSI_PERIOD)
    momentum = calculate_momentum(prices, MOMENTUM_LOOKBACK)
    atr = calculate_atr(candles, idx, ATR_PERIOD)
    trend, trend_slope = calculate_trend(candles, idx, TREND_LOOKBACK)
    macro_trend = get_macro_trend(candles, idx)
    
    if rsi is None or momentum is None or atr is None:
        return {"action": "HOLD", "reason": "calculation error"}
    
    price = current["close_price"]
    
    # Signal logic with trend filter
    # BUY: Positive momentum + RSI has room to rise + (optional) uptrend
    # SELL: Negative momentum + RSI has room to fall + (optional) downtrend
    
    rsi_room_to_rise = rsi < RSI_MID_HIGH
    rsi_room_to_fall = rsi > RSI_MID_LOW
    
    # Trend filter: Only trade long in uptrends, short in downtrends
    # When trend filter is enabled, only trade in direction of the trend
    trend_allows_long = not USE_TREND_FILTER or trend == "UP"
    trend_allows_short = not USE_TREND_FILTER or trend == "DOWN"
    
    # Macro filter: Avoid RSI > 70 shorts in bullish macro conditions
    # In strong uptrends, RSI can stay overbought for extended periods
    macro_blocks_short = (AVOID_RSI_OVERBOUGHT_SHORTS and 
                          macro_trend == "BULLISH" and 
                          rsi > RSI_OVERBOUGHT)
    
    # LONG signal
    if momentum > 0 and rsi_room_to_rise and trend_allows_long:
        return {
            "action": "BUY",
            "price": price,
            "rsi": rsi,
            "momentum": momentum,
            "atr": atr,
            "trend": trend,
            "trend_slope": trend_slope,
            "macro_trend": macro_trend,
            "confidence": min(abs(momentum) / 2 + (RSI_OVERBOUGHT - rsi) / 100, 1.0)
        }
    
    # SHORT signal
    if momentum < 0 and rsi_room_to_fall and trend_allows_short and not macro_blocks_short:
        return {
            "action": "SELL",
            "price": price,
            "rsi": rsi,
            "momentum": momentum,
            "atr": atr,
            "trend": trend,
            "trend_slope": trend_slope,
            "macro_trend": macro_trend,
            "confidence": min(abs(momentum) / 2 + (rsi - RSI_OVERSOLD) / 100, 1.0)
        }
    
    # Determine why we didn't trade
    reason = "no confluence"
    if momentum > 0 and rsi_room_to_rise and not trend_allows_long:
        reason = f"trend_filter_blocks_long ({trend})"
    elif momentum < 0 and rsi_room_to_fall and not trend_allows_short:
        reason = f"trend_filter_blocks_short ({trend})"
    elif momentum < 0 and rsi_room_to_fall and macro_blocks_short:
        reason = f"macro_filter_blocks_short (RSI>{RSI_OVERBOUGHT} in {macro_trend} macro)"
    
    return {
        "action": "HOLD", 
        "reason": reason, 
        "rsi": rsi, 
        "momentum": momentum,
        "trend": trend,
        "macro_trend": macro_trend
    }


def run_backtest(candle_limit: int = None):
    """Run the full backtest.
    
    Args:
        candle_limit: Optional limit on number of candles to fetch (for testing)
    """
    print("=" * 70)
    print("MOMENTUM + RSI STRATEGY BACKTEST (Binance 5min Data)")
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
    
    print(f"Loaded {len(candles)} candles")
    print(f"Date range: {candles[0]['open_time']} to {candles[-1]['close_time']}")
    print()
    
    # Backtest state
    balance = INITIAL_BALANCE
    position = None  # None or dict with direction, entry_price, etc.
    result = BacktestResult()
    equity_curve = [INITIAL_BALANCE]
    max_equity = INITIAL_BALANCE
    
    print("Running backtest...")
    print()
    
    for i in range(len(candles)):
        candle = candles[i]
        current_price = candle["close_price"]
        current_time = candle["open_time"]
        
        # Check for exit if in position
        if position:
            entry_price = position["entry_price"]
            direction = position["direction"]
            entry_atr = position.get("atr", entry_price * STOP_LOSS_PCT)  # Fallback for old trades
            
            # Calculate ATR-based stop loss and take profit levels
            if USE_ATR_STOPS and entry_atr:
                sl_distance = entry_atr * ATR_MULTIPLIER_SL / entry_price
                tp_distance = entry_atr * ATR_MULTIPLIER_TP / entry_price
            else:
                sl_distance = STOP_LOSS_PCT
                tp_distance = TAKE_PROFIT_PCT
            
            # Calculate P&L
            if direction == "LONG":
                pnl_pct = (current_price - entry_price) / entry_price
            else:  # SHORT
                pnl_pct = (entry_price - current_price) / entry_price
            
            # Check stop loss or take profit
            exit_reason = None
            if pnl_pct <= -sl_distance:
                exit_reason = "STOP_LOSS"
            elif pnl_pct >= tp_distance:
                exit_reason = "TAKE_PROFIT"
            elif i == len(candles) - 1:  # Force close at end
                exit_reason = "END_OF_DATA"
            
            if exit_reason:
                # Close position
                position_size = balance * PORTFOLIO_PCT * LEVERAGE
                pnl_usd = position_size * pnl_pct
                
                # Apply trading fees (entry + exit)
                fees = position_size * TRADING_FEE_PCT * 2
                pnl_usd -= fees
                
                balance += pnl_usd
                
                trade = Trade(
                    direction=direction,
                    entry_price=entry_price,
                    exit_price=current_price,
                    entry_time=position["entry_time"],
                    exit_time=current_time,
                    pnl_pct=pnl_pct * 100,
                    pnl_usd=pnl_usd,
                    rsi_at_entry=position["rsi"],
                    momentum_at_entry=position["momentum"],
                    exit_reason=exit_reason,
                    atr_at_entry=position.get("atr", 0),
                    trend_at_entry=position.get("trend", "UNKNOWN"),
                    trend_slope_at_entry=position.get("trend_slope", 0),
                    macro_trend_at_entry=position.get("macro_trend", "UNKNOWN")
                )
                
                result.trades.append(trade)
                result.total_trades += 1
                result.total_pnl_usd += pnl_usd
                
                if pnl_usd > 0:
                    result.winning_trades += 1
                else:
                    result.losing_trades += 1
                
                position = None
                equity_curve.append(balance)
                
                # Update max drawdown
                if balance > max_equity:
                    max_equity = balance
                drawdown = (max_equity - balance) / max_equity
                if drawdown > result.max_drawdown_pct:
                    result.max_drawdown_pct = drawdown
        
        # Check for entry if not in position
        if not position and i < len(candles) - 1:
            signal = generate_signal(candles, i)
            
            if signal["action"] in ["BUY", "SELL"]:
                direction = "LONG" if signal["action"] == "BUY" else "SHORT"
                
                position = {
                    "direction": direction,
                    "entry_price": signal["price"],
                    "entry_time": current_time,
                    "rsi": signal["rsi"],
                    "momentum": signal["momentum"],
                    "atr": signal.get("atr"),
                    "trend": signal.get("trend", "UNKNOWN"),
                    "trend_slope": signal.get("trend_slope", 0),
                    "macro_trend": signal.get("macro_trend", "UNKNOWN")
                }
    
    # Calculate final stats
    result.total_pnl_pct = ((balance - INITIAL_BALANCE) / INITIAL_BALANCE) * 100
    result.max_drawdown_pct *= 100
    
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
    
    # Print configuration summary
    print("=" * 70)
    print("CONFIGURATION")
    print("=" * 70)
    print(f"Trend Filter:       {'ENABLED' if USE_TREND_FILTER else 'DISABLED'}")
    if USE_TREND_FILTER:
        print(f"  Lookback:         {TREND_LOOKBACK} periods")
        print(f"  Slope Threshold:  {TREND_SLOPE_THRESHOLD}%")
    print(f"ATR-Based Stops:    {'ENABLED' if USE_ATR_STOPS else 'DISABLED'}")
    if USE_ATR_STOPS:
        print(f"  ATR Period:       {ATR_PERIOD}")
        print(f"  SL Multiplier:    {ATR_MULTIPLIER_SL}x")
        print(f"  TP Multiplier:    {ATR_MULTIPLIER_TP}x")
    else:
        print(f"  Fixed Stop Loss:  {STOP_LOSS_PCT*100}%")
        print(f"  Fixed Take Profit: {TAKE_PROFIT_PCT*100}%")
    print(f"Macro Filter:       {'ENABLED' if AVOID_RSI_OVERBOUGHT_SHORTS else 'DISABLED'}")
    if AVOID_RSI_OVERBOUGHT_SHORTS:
        print(f"  Lookback:         {MACRO_LOOKBACK} periods")
        print(f"  Skip RSI>70 shorts in bullish macro")
    print()
    
    # Print trade breakdown by trend
    if result.trades:
        from collections import defaultdict
        trend_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0})
        for t in result.trades:
            trend_stats[t.trend_at_entry]["trades"] += 1
            trend_stats[t.trend_at_entry]["pnl"] += t.pnl_usd
            if t.pnl_usd > 0:
                trend_stats[t.trend_at_entry]["wins"] += 1
        
        print("Performance by Trend:")
        print("-" * 70)
        for trend, stats in sorted(trend_stats.items()):
            win_rate = (stats["wins"] / stats["trades"] * 100) if stats["trades"] > 0 else 0
            print(f"  {trend:12} | Trades: {stats['trades']:3} | Win Rate: {win_rate:5.1f}% | P&L: ${stats['pnl']:+.2f}")
        print()
    
    # Print recent trades
    if result.trades:
        print("Recent Trades (last 10):")
        print("-" * 70)
        for t in result.trades[-10:]:
            pnl_str = f"${t.pnl_usd:+.2f}"
            trend_info = f"{t.trend_at_entry}"
            print(f"{t.exit_time.strftime('%Y-%m-%d %H:%M')} | {t.direction:5} | "
                  f"Trend: {trend_info:8} | Entry: ${t.entry_price:,.2f} | "
                  f"P&L: {pnl_str:>10} | {t.exit_reason}")
    
    print()
    print("=" * 70)
    
    return result


if __name__ == "__main__":
    run_backtest()
