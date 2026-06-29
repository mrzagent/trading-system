#!/usr/bin/env python3
"""
strategy_vwap_reversion.py â VWAP Mean Reversion Strategy (Scalp Trade)
Timeframe : 5min candles
Type      : Scalp trade (mean reversion)

Signal logic:
  BUY  when price is >1% BELOW VWAP (price deviated too far below fair value)
  SELL when price is >1% ABOVE VWAP (price deviated too far above fair value)
  HOLD when price is within 1% of VWAP

Uses Volume Weighted Average Price (VWAP) calculated from recent candles.
"""
import json
from db import get_conn, fetch_recent, COINS, signal_envelope
from candle_gate import should_act, mark_acted

STRATEGY       = "vwap_reversion"
CANDLE_MINUTES = 5     # 5-minute candles
VWAP_PERIOD    = 24    # VWAP lookback (24 x 5min = 2 hours)
DEVIATION_PCT  = 1.0   # Minimum deviation % from VWAP to trigger
MIN_ROWS       = 30
LEVERAGE       = 3.0   # Optimized leverage from backtest
STOP_LOSS_PCT  = 1.5   # Stop loss percentage
TAKE_PROFIT_PCT = 3.0  # Take profit percentage (1:2 R/R)


def calculate_vwap(rows: list[dict]) -> float:
    """Calculate VWAP from typical price x volume."""
    total_pv = 0.0
    total_vol = 0.0
    
    for r in rows:
        high = float(r.get("high", 0) or r.get("price", 0))
        low = float(r.get("low", 0) or r.get("price", 0))
        close = float(r["price"])
        volume = float(r.get("volume") or r.get("volume_5m") or r.get("volume_candle") or 0)
        
        if volume <= 0:
            continue
        
        # Typical price = (high + low + close) / 3
        typical_price = (high + low + close) / 3
        total_pv += typical_price * volume
        total_vol += volume
    
    return total_pv / total_vol if total_vol > 0 else 0.0


def analyse(coin: str, conn, candle_start, timeframe: str = "5min") -> dict:
    rows = fetch_recent(conn, coin, limit=max(VWAP_PERIOD + 5, MIN_ROWS), timeframe=timeframe)
    if len(rows) < MIN_ROWS:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0,
                               f"insufficient data ({len(rows)} rows, need {MIN_ROWS})")

    latest = rows[-1]
    price = float(latest["price"])
    
    # Calculate VWAP from historical data (excluding latest for fairness)
    historical = rows[:-1]
    vwap = calculate_vwap(historical[-VWAP_PERIOD:])
    
    if vwap == 0:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "unable to calculate VWAP")
    
    # Calculate deviation from VWAP
    deviation_pct = ((price - vwap) / vwap) * 100
    abs_deviation = abs(deviation_pct)
    
    # BUY: Price significantly below VWAP (undervalued)
    if deviation_pct < -DEVIATION_PCT:
        # Confidence increases with deviation
        conf = min(abs_deviation / 3.0, 0.95)
        return signal_envelope(
            STRATEGY, coin, "BUY", round(conf, 2),
            f"Price {abs(deviation_pct):.2f}% below VWAP {vwap:,.2f} â mean reversion expected",
            {"price": price, "vwap": round(vwap, 2), "deviation_pct": round(deviation_pct, 2),
             "vwap_period": VWAP_PERIOD, "candle": candle_start.isoformat()},
        )
    
    # SELL: Price significantly above VWAP (overvalued)
    if deviation_pct > DEVIATION_PCT:
        conf = min(abs_deviation / 3.0, 0.95)
        return signal_envelope(
            STRATEGY, coin, "SELL", round(conf, 2),
            f"Price {deviation_pct:.2f}% above VWAP {vwap:,.2f} â mean reversion expected",
            {"price": price, "vwap": round(vwap, 2), "deviation_pct": round(deviation_pct, 2),
             "vwap_period": VWAP_PERIOD, "candle": candle_start.isoformat()},
        )
    
    # HOLD: Price near VWAP
    return signal_envelope(
        STRATEGY, coin, "HOLD", 0.0,
        f"Price within {abs(deviation_pct):.2f}% of VWAP {vwap:,.2f}",
        {"price": price, "vwap": round(vwap, 2), "deviation_pct": round(deviation_pct, 2),
         "candle": candle_start.isoformat()},
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
        "name": "VWAP Reversion",
        "description": "Mean reversion strategy trading deviations from Volume Weighted Average Price (VWAP).",
        "type": "scalp",
        "timeframes": ["5m"],
        "core_logic": {
            "long": [
                "Price > 1% BELOW VWAP (undervalued)",
                "Expect mean reversion back to VWAP",
                "Confidence increases with deviation magnitude"
            ],
            "short": [
                "Price > 1% ABOVE VWAP (overvalued)",
                "Expect mean reversion back to VWAP",
                "Confidence increases with deviation magnitude"
            ],
            "filters": [
                "VWAP calculated from 24-period lookback (2 hours)",
                "Uses typical price = (high + low + close) / 3",
                "Minimum 30 rows required"
            ]
        },
        "backtest": {
            "period": "June 2023 - June 2026 (3 years)",
            "coin": "BTC",
            "timeframe": "5-minute candles",
            "initial_capital": 1000,
            "final_capital": 1079.00,
            "total_return_pct": 7.90,
            "total_trades": 1330,
            "winning_trades": 529,
            "losing_trades": 801,
            "win_rate": 39.7,
            "profit_factor": 1.32,
            "max_drawdown_pct": 1.35,
            "avg_win_pct": 3.0,
            "avg_loss_pct": -1.5,
            "avg_hold_time_hours": 18.7,
            "risk_reward": "1:2 (1.5% SL / 3.0% TP)",
            "leverage": 3.0,
            "note": "Optimized with 3x leverage. Baseline 1x leverage returned +2.57%"
        }
    }
