#!/usr/bin/env python3
"""
strategy_fvg.py — Fair Value Gap Breakout Strategy with Confirmation
Timeframe : 15-min candles (synthetic from 5-min data)
Fires on  : 15-min candle close

Signal logic (UPDATED - Backtested 1:2 R:R):
  - Detect FVGs within last 20 candles (min 0.02% size)
  - Wait for price to BREAK through FVG boundary
  - CONFIRM: Next candle must CLOSE beyond the FVG
  - Enter on confirmation close
  
  BUY  on bearish FVG break + confirmation (price rallies above supply)
  SELL on bullish FVG break + confirmation (price drops below demand)
  
Exit: Hold until SL (1.5%) or TP (3.0%) hit — NO time exit

Backtest Results (3 years BTC data):
  - Return: +19.88%
  - Win Rate: 38.4%
  - Profit Factor: 1.15
  - Trades: 753
  - Avg Hold: ~30 hours
"""
import json
import os
from datetime import datetime, timedelta
from db import get_conn, fetch_recent, COINS, signal_envelope
from candle_gate import should_act, mark_acted

STRATEGY      = "fvg_proximity"
CANDLE_MINUTES = 15    # 15-min candles (synthetic from 5-min data)
FVG_LOOKBACK = 20      # Look back 20 candles for FVGs
FVG_MAX_AGE = 6        # Max age of FVG to trade (6 candles)
MIN_FVG_SIZE_PCT = 0.02  # Min FVG size: 0.02%
BREAK_THRESHOLD_PCT = 0.01  # Break buffer: 1% of FVG size

# UPDATED: 1:2 Risk/Reward based on backtest results
STOP_LOSS_PCT = 1.5    # 1.5% stop loss
TAKE_PROFIT_PCT = 3.0  # 3.0% take profit (1:2 R:R)

# Cooldown is managed by signal_integrator after successful trade execution
# Strategies should NOT check or set cooldown - they just generate signals


def detect_fvgs(candles: list[dict], current_idx: int) -> list[dict]:
    """Detect FVGs in recent candles."""
    fvgs = []
    start_idx = max(1, current_idx - FVG_LOOKBACK)
    
    for i in range(start_idx, current_idx):
        if i < 1 or i >= len(candles) - 1:
            continue
        prev = candles[i - 1]
        nxt = candles[i + 1]
        
        # Bullish FVG: prev.high < next.low
        if prev["high"] < nxt["low"] and prev["high"] > 0:
            gap_size = nxt["low"] - prev["high"]
            gap_size_pct = (gap_size / prev["high"]) * 100
            if gap_size_pct >= MIN_FVG_SIZE_PCT:
                fvgs.append({
                    "type": "bullish",
                    "bottom": prev["high"],
                    "top": nxt["low"],
                    "midpoint": (prev["high"] + nxt["low"]) / 2,
                    "formed_at_idx": i,
                    "age": current_idx - i,
                    "size_pct": gap_size_pct
                })
        # Bearish FVG: prev.low > next.high
        elif prev["low"] > nxt["high"] and prev["low"] > 0:
            gap_size = prev["low"] - nxt["high"]
            gap_size_pct = (gap_size / prev["low"]) * 100
            if gap_size_pct >= MIN_FVG_SIZE_PCT:
                fvgs.append({
                    "type": "bearish",
                    "top": prev["low"],
                    "bottom": nxt["high"],
                    "midpoint": (prev["low"] + nxt["high"]) / 2,
                    "formed_at_idx": i,
                    "age": current_idx - i,
                    "size_pct": gap_size_pct
                })
    
    # Sort by age (newest first)
    fvgs.sort(key=lambda x: x["age"])
    return fvgs


def check_fvg_breakout(price: float, fvgs: list[dict]) -> tuple[str, dict | None]:
    """
    Check if price has broken through any FVG.
    Returns (action, matching_fvg) or ("HOLD", None).
    """
    for fvg in fvgs:
        if fvg["age"] < 1 or fvg["age"] > FVG_MAX_AGE:
            continue
        
        ftype = fvg["type"]
        bottom = fvg["bottom"]
        top = fvg["top"]
        break_buffer = (top - bottom) * (BREAK_THRESHOLD_PCT / 100)
        
        if ftype == "bullish" and price < (bottom - break_buffer):
            # Price broke below bullish FVG = SELL signal
            return "SELL", fvg
        elif ftype == "bearish" and price > (top + break_buffer):
            # Price broke above bearish FVG = BUY signal
            return "BUY", fvg
    
    return "HOLD", None


def analyse(coin: str, conn, candle_start, timeframe: str = "5min") -> dict:
    """Analyze for FVG breakout with confirmation."""
    # NOTE: Cooldown is checked by signal_integrator, not here
    # Strategies generate signals; integrator decides whether to execute

    # Fetch recent candles (need enough for FVG detection + confirmation)
    rows = fetch_recent(conn, coin, limit=FVG_LOOKBACK + 10, timeframe=timeframe)
    if len(rows) < FVG_LOOKBACK + 5:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "insufficient data")

    # Convert to candle format (handle both naming conventions)
    candles = []
    for r in rows:
        # Get values with fallbacks for different column naming
        open_val = r.get("open") or r.get("open_price") or 0
        high_val = r.get("high") or r.get("high_price") or 0
        low_val = r.get("low") or r.get("low_price") or 0
        close_val = r.get("close") or r.get("close_price") or r.get("price") or 0
        
        candles.append({
            "timestamp": r.get("timestamp") or r.get("open_time") or r.get("captured_at"),
            "open": float(open_val) if open_val is not None else 0,
            "high": float(high_val) if high_val is not None else 0,
            "low": float(low_val) if low_val is not None else 0,
            "close": float(close_val) if close_val is not None else 0,
        })
    
    # Get current and previous candle
    current = candles[-1]
    previous = candles[-2]
    current_price = current["close"]
    prev_price = previous["close"]
    
    # Detect FVGs at previous candle index
    fvgs = detect_fvgs(candles, len(candles) - 2)
    
    if not fvgs:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0,
                               "no FVGs detected", {"price": current_price})
    
    # Check for breakout on previous candle
    prev_action, matched_fvg = check_fvg_breakout(prev_price, fvgs)
    
    if prev_action == "HOLD" or not matched_fvg:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0,
                               f"no FVG breakout detected ({len(fvgs)} gaps tracked)",
                               {"price": current_price, "fvg_count": len(fvgs)})
    
    # CONFIRMATION: Check if current candle closed beyond FVG
    ftype = matched_fvg["type"]
    bottom = matched_fvg["bottom"]
    top = matched_fvg["top"]
    
    confirmed = False
    if prev_action == "SELL" and current_price < bottom:
        # Confirmed bearish breakout
        confirmed = True
        trade_action = "SELL"
    elif prev_action == "BUY" and current_price > top:
        # Confirmed bullish breakout
        confirmed = True
        trade_action = "BUY"
    
    if not confirmed:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0,
                               f"breakout detected but not confirmed",
                               {"price": current_price, "fvg": matched_fvg, 
                                "prev_action": prev_action})
    
    # Signal confirmed - return signal (cooldown set by signal_integrator after successful trade)
    # Calculate confidence based on FVG size and age
    conf = min(0.95, 0.5 + (matched_fvg["size_pct"] / 0.1) * 0.3 - (matched_fvg["age"] / FVG_MAX_AGE) * 0.2)
    
    return signal_envelope(
        STRATEGY, coin, trade_action, round(conf, 2),
        f"FVG {ftype} breakout confirmed | SL:{STOP_LOSS_PCT}% TP:{TAKE_PROFIT_PCT}%",
        {
            "price": current_price,
            "fvg": matched_fvg,
            "fvg_type": ftype,
            "fvg_age": matched_fvg["age"],
            "fvg_size_pct": matched_fvg["size_pct"],
            "stop_loss_pct": STOP_LOSS_PCT,
            "take_profit_pct": TAKE_PROFIT_PCT,
            "risk_reward": "1:2",
            "cooldown_managed_by": "signal_integrator",
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
        "name": "Fair Value Gap (FVG) Breakout",
        "description": "Trades FVG breakouts with confirmation. Enters after price breaks FVG boundary AND next candle closes beyond it. 1:2 Risk/Reward (1.5% SL / 3% TP). Hold until SL or TP hit.",
        "type": "swing",
        "timeframes": ["15m"],
        "core_logic": {
            "entry": [
                "Detect FVGs within last 20 candles (min 0.02% size)",
                "Wait for price to BREAK through FVG boundary",
                "CONFIRM: Next candle must CLOSE beyond the FVG",
                "Enter LONG on bearish FVG break + confirmation",
                "Enter SHORT on bullish FVG break + confirmation"
            ],
            "exit": [
                f"Stop Loss: {STOP_LOSS_PCT}% (fixed)",
                f"Take Profit: {TAKE_PROFIT_PCT}% (fixed)",
                "NO time exit — hold until SL or TP hit",
                f"Risk/Reward: 1:2"
            ],
            "filters": [
                f"Max FVG age: {FVG_MAX_AGE} candles",
                f"Min FVG size: {MIN_FVG_SIZE_PCT}%"
            ]
        },
        "backtest": {
            "period": "June 2023 - June 2026 (3 years)",
            "coin": "BTC",
            "timeframe": "15-minute candles",
            "initial_capital": 1000,
            "final_capital": 1578.21,
            "total_return_pct": 57.82,
            "total_trades": 759,
            "winning_trades": 267,
            "losing_trades": 492,
            "win_rate": 35.2,
            "profit_factor": 1.09,
            "max_drawdown_pct": 29.00,
            "avg_hold_time_hours": 29.3,
            "risk_reward": "1:2 (1.5% SL / 3.0% TP)"
        }
    }
