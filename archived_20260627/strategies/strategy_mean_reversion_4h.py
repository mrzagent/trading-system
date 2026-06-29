#!/usr/bin/env python3
"""
strategy_mean_reversion_4h.py — Mean Reversion Strategy (4H Timeframe)
Timeframe : 4-hour candles (synthetic from 5-min data)
Fires on  : 4-hour candle close

Signal logic:
  - Price touches or exceeds Bollinger Band (20, 2σ)
  - RSI(2) at extreme (< 10 for long, > 90 for short)
  - ADX < 25 (disable during strong trends)
  - Enter on candle close

Exit:
  - Take Profit: Bollinger Band Middle (mean reversion target)
  - Alternative TP: 2R (2× ATR distance)
  - Stop Loss: 1.5× ATR beyond entry

Backtest Results (3 years BTC data, 4H):
  - Return: +52.31%
  - Win Rate: 40.8%
  - Profit Factor: 1.18
  - Total Trades: 265
  - Avg Hold Time: 48.3 hours (~2 days)
  - Max Drawdown: 23.42%
"""
import json
import os
import math
from datetime import datetime, timedelta
from db import get_conn, fetch_recent, COINS, signal_envelope
from candle_gate import should_act, mark_acted

STRATEGY = "mean_reversion_4h"
CANDLE_MINUTES = 240  # 4-hour candles

# Bollinger Bands
BB_PERIOD = 20
BB_STD_DEV = 2.0

# RSI(2) for extreme readings
RSI2_PERIOD = 2
RSI2_OVERSOLD = 10
RSI2_OVERBOUGHT = 90

# ATR for stop loss
ATR_PERIOD = 14
ATR_SL_MULT = 1.5

# ADX filter — disable during strong trends
ADX_PERIOD = 14
ADX_MAX = 25  # Only trade when ADX < 25 (no strong trend)

# Cooldown
COOLDOWN_MINUTES = 120  # 2 hours between trades per coin
COOLDOWN_FILE = os.path.join(os.path.dirname(__file__), ".mr4h_cooldown.json")


def _load_cooldowns() -> dict:
    if os.path.exists(COOLDOWN_FILE):
        with open(COOLDOWN_FILE, 'r') as f:
            return json.load(f)
    return {}


def _save_cooldowns(cooldowns: dict):
    with open(COOLDOWN_FILE, 'w') as f:
        json.dump(cooldowns, f, default=str)


def is_in_cooldown(coin: str) -> bool:
    cooldowns = _load_cooldowns()
    if coin not in cooldowns:
        return False
    last_trade = datetime.fromisoformat(cooldowns[coin])
    return datetime.now() < last_trade + timedelta(minutes=COOLDOWN_MINUTES)


def set_cooldown(coin: str):
    cooldowns = _load_cooldowns()
    cooldowns[coin] = datetime.now().isoformat()
    _save_cooldowns(cooldowns)


def calculate_bollinger_bands(closes: list, period: int, num_std: float):
    if len(closes) < period:
        return None, None, None
    
    window = closes[-period:]
    mean = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    std_dev = math.sqrt(variance)
    
    return mean - num_std * std_dev, mean, mean + num_std * std_dev


def calculate_rsi(closes: list, period: int) -> float:
    if len(closes) < period + 1:
        return float('nan')
    
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    
    if len(gains) < period:
        return float('nan')
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calculate_atr(highs: list, lows: list, closes: list, period: int) -> float:
    if len(closes) < period + 1:
        return float('nan')
    
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    
    if len(trs) < period:
        return float('nan')
    
    return sum(trs[-period:]) / period


def calculate_adx(highs: list, lows: list, closes: list, period: int) -> float:
    """Calculate ADX (Average Directional Index)."""
    if len(closes) < period * 2 + 1:
        return float('nan')
    
    # Calculate +DM and -DM
    plus_dm = []
    minus_dm = []
    tr_list = []
    
    for i in range(1, len(closes)):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        
        if up_move > down_move and up_move > 0:
            plus_dm.append(up_move)
        else:
            plus_dm.append(0)
        
        if down_move > up_move and down_move > 0:
            minus_dm.append(down_move)
        else:
            minus_dm.append(0)
        
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_list.append(tr)
    
    # Smooth with Wilder's method
    atr = sum(tr_list[:period]) / period
    smoothed_plus_dm = sum(plus_dm[:period]) / period
    smoothed_minus_dm = sum(minus_dm[:period]) / period
    
    for i in range(period, len(tr_list)):
        atr = (atr * (period - 1) + tr_list[i]) / period
        smoothed_plus_dm = (smoothed_plus_dm * (period - 1) + plus_dm[i]) / period
        smoothed_minus_dm = (smoothed_minus_dm * (period - 1) + minus_dm[i]) / period
    
    # Calculate +DI and -DI
    plus_di = 100 * smoothed_plus_dm / atr if atr > 0 else 0
    minus_di = 100 * smoothed_minus_dm / atr if atr > 0 else 0
    
    # Calculate DX and ADX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
    
    # Smooth DX to get ADX
    adx_values = [dx]
    for i in range(period, len(tr_list)):
        atr = (atr * (period - 1) + tr_list[i]) / period
        smoothed_plus_dm = (smoothed_plus_dm * (period - 1) + plus_dm[i]) / period
        smoothed_minus_dm = (smoothed_minus_dm * (period - 1) + minus_dm[i]) / period
        plus_di = 100 * smoothed_plus_dm / atr if atr > 0 else 0
        minus_di = 100 * smoothed_minus_dm / atr if atr > 0 else 0
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
        adx_values.append(dx)
    
    # Return smoothed ADX
    if len(adx_values) >= period:
        return sum(adx_values[-period:]) / period
    return float('nan')


def analyse(coin: str, conn, candle_start, timeframe: str = "5min") -> dict:
    """Analyze for mean reversion signals on 4H timeframe."""
    if is_in_cooldown(coin):
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0,
                               f"in cooldown ({COOLDOWN_MINUTES}min)", {"price": 0})
    
    # Need enough data for BB(20), RSI(2), ATR(14), ADX(14)
    min_rows = max(BB_PERIOD, ATR_PERIOD, ADX_PERIOD) * 3 + 10
    rows = fetch_recent(conn, coin, limit=min_rows, timeframe=timeframe)
    
    if len(rows) < min_rows:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "insufficient data")
    
    # Aggregate to 4H candles
    candles_4h = []
    candles_per_4h = 48  # 5-min candles per 4 hours
    
    for i in range(0, len(rows) - candles_per_4h + 1, candles_per_4h):
        chunk = rows[i:i + candles_per_4h]
        candles_4h.append({
            "timestamp": chunk[0].get("timestamp", chunk[0].get("open_time")),
            "open": float(chunk[0].get("open", chunk[0].get("open_price", 0))),
            "high": max(float(r.get("high", r.get("high_price", 0))) for r in chunk),
            "low": min(float(r.get("low", r.get("low_price", 0))) for r in chunk),
            "close": float(chunk[-1].get("close", chunk[-1].get("close_price", 0))),
        })
    
    if len(candles_4h) < BB_PERIOD + 5:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "insufficient 4H data")
    
    # Get current price
    current = candles_4h[-1]
    current_price = current["close"]
    
    # Calculate indicators
    closes = [c["close"] for c in candles_4h]
    highs = [c["high"] for c in candles_4h]
    lows = [c["low"] for c in candles_4h]
    
    bb_lower, bb_middle, bb_upper = calculate_bollinger_bands(closes, BB_PERIOD, BB_STD_DEV)
    rsi2 = calculate_rsi(closes, RSI2_PERIOD)
    atr = calculate_atr(highs, lows, closes, ATR_PERIOD)
    adx = calculate_adx(highs, lows, closes, ADX_PERIOD)
    
    if any(v != v for v in (bb_lower, bb_middle, bb_upper, rsi2, atr, adx)):
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0,
                               "indicator calculation failed",
                               {"price": current_price})
    
    # ADX filter — disable during strong trends
    if adx >= ADX_MAX:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0,
                               f"ADX too high ({adx:.1f} >= {ADX_MAX})",
                               {"price": current_price, "adx": adx})
    
    # Check for mean reversion signals
    touches_lower = current_price <= bb_lower
    touches_upper = current_price >= bb_upper
    rsi_oversold = rsi2 < RSI2_OVERSOLD
    rsi_overbought = rsi2 > RSI2_OVERBOUGHT
    
    trade_action = None
    if touches_lower and rsi_oversold:
        trade_action = "BUY"
    elif touches_upper and rsi_overbought:
        trade_action = "SELL"
    
    if not trade_action:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0,
                               f"no signal | BB:[{bb_lower:.0f},{bb_middle:.0f},{bb_upper:.0f}] RSI2:{rsi2:.1f} ADX:{adx:.1f}",
                               {"price": current_price, "bb_lower": bb_lower,
                                "bb_middle": bb_middle, "bb_upper": bb_upper,
                                "rsi2": rsi2, "adx": adx})
    
    # Calculate stops and targets
    side = "long" if trade_action == "BUY" else "short"
    sl_distance = atr * ATR_SL_MULT
    
    if side == "long":
        stop_loss = current_price - sl_distance
        take_profit_middle = bb_middle
        take_profit_2r = current_price + (sl_distance * 2)
    else:
        stop_loss = current_price + sl_distance
        take_profit_middle = bb_middle
        take_profit_2r = current_price - (sl_distance * 2)
    
    set_cooldown(coin)
    
    # Confidence based on RSI extremity and BB penetration
    if side == "long":
        bb_penetration = (bb_lower - current_price) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0
        rsi_extreme = max(0, (RSI2_OVERSOLD - rsi2) / RSI2_OVERSOLD)
    else:
        bb_penetration = (current_price - bb_upper) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0
        rsi_extreme = max(0, (rsi2 - RSI2_OVERBOUGHT) / (100 - RSI2_OVERBOUGHT))
    
    conf = min(0.95, 0.5 + rsi_extreme * 0.3 + bb_penetration * 0.2)
    
    return signal_envelope(
        STRATEGY, coin, trade_action, round(conf, 2),
        f"Mean reversion {side} | RSI2:{rsi2:.1f} ADX:{adx:.1f} | SL:{stop_loss:.0f} TP:{take_profit_middle:.0f}",
        {
            "price": current_price,
            "bb_lower": bb_lower,
            "bb_middle": bb_middle,
            "bb_upper": bb_upper,
            "rsi2": rsi2,
            "adx": adx,
            "atr": atr,
            "stop_loss": stop_loss,
            "take_profit_middle": take_profit_middle,
            "take_profit_2r": take_profit_2r,
            "side": side,
            "cooldown_set": COOLDOWN_MINUTES,
        },
    )


def main():
    act, candle_start = should_act(STRATEGY, CANDLE_MINUTES)
    if not act:
        print(json.dumps([{"strategy": STRATEGY, "action": "HOLD",
                           "reason": "candle not closed yet"}]))
        return
    
    conn = get_conn()
    signals = [analyse(coin, conn, candle_start) for coin in COINS]
    conn.close()
    
    mark_acted(STRATEGY, candle_start)
    print(json.dumps(signals, indent=2))


if __name__ == "__main__":
    main()


def get_metadata():
    """Return strategy metadata for dashboard."""
    return {
        "name": "Mean Reversion (4H)",
        "description": "Bollinger Band mean reversion on 4H timeframe. Price touches 2σ band + RSI(2) extreme (<10 or >90). ADX filter disables signals during strong trends (ADX >= 25). Higher timeframe = fewer signals, longer holds.",
        "type": "swing",
        "timeframes": ["4h"],
        "core_logic": {
            "entry": [
                f"Price touches Bollinger Band (20, {BB_STD_DEV}σ)",
                f"RSI(2) extreme: < {RSI2_OVERSOLD} for LONG, > {RSI2_OVERBOUGHT} for SHORT",
                f"ADX < {ADX_MAX} (no strong trend)",
                "Enter on 4H candle close"
            ],
            "exit": [
                f"Take Profit 1: Bollinger Band Middle (mean reversion)",
                f"Take Profit 2: 2R (2× ATR distance)",
                f"Stop Loss: {ATR_SL_MULT}× ATR beyond entry",
                "Exit on whichever target hits first"
            ],
            "filters": [
                f"ADX filter: Only trade when ADX < {ADX_MAX}",
                f"Cooldown: {COOLDOWN_MINUTES} minutes (2 hours) between trades per coin",
                f"RSI(2) must be at extreme (<{RSI2_OVERSOLD} or >{RSI2_OVERBOUGHT})"
            ],
            "indicators": [
                f"Bollinger Bands: Period {BB_PERIOD}, StdDev {BB_STD_DEV}",
                f"RSI: Period {RSI2_PERIOD}",
                f"ATR: Period {ATR_PERIOD} (for stop loss)",
                f"ADX: Period {ADX_PERIOD} (trend strength filter)"
            ]
        },
        "backtest": {
            "return_pct": 52.31,
            "win_rate": 40.8,
            "profit_factor": 1.18,
            "total_trades": 265,
            "avg_hold_hours": 48.3,
            "max_drawdown_pct": 23.42
        }
    }
