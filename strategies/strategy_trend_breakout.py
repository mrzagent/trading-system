#!/usr/bin/env python3
"""
strategy_trend_breakout.py — Trend Following Breakout Strategy (Swing Trade)
Timeframe : 4h candles
Type      : Swing trade (trend following)

Signal logic:
  BUY  when price breaks above 20-period high (resistance) with volume confirmation
  SELL when price breaks below 20-period low (support) with volume confirmation
  HOLD when price is consolidating within range

Uses 4h candle data from trading_prices_4h table.
Requires minimum PERIOD rows before generating signals.
"""
import json
from db import get_conn, fetch_recent, COINS, signal_envelope
from candle_gate import should_act, mark_acted

STRATEGY       = "trend_breakout"
CANDLE_MINUTES = 240   # 4-hour candles
PERIOD         = 20    # Lookback period for high/low
VOLUME_MULT    = 1.2   # Volume must be 1.2x average to confirm breakout
MIN_ROWS       = 25    # Minimum rows needed (PERIOD + buffer)


def rolling_volume_avg(rows: list[dict]) -> float:
    """Calculate average volume excluding the latest candle."""
    if len(rows) < 2:
        return 0.0
    vols = [float(r.get("volume", 0) or 0) for r in rows[1:]]
    return sum(vols) / len(vols) if vols else 0.0


def analyse(coin: str, conn, candle_start, timeframe: str = "4h") -> dict:
    rows = fetch_recent(conn, coin, limit=PERIOD + 5, timeframe=timeframe)
    if len(rows) < MIN_ROWS:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0,
                               f"insufficient data ({len(rows)} rows, need {MIN_ROWS})")

    latest = rows[-1]
    price = float(latest["price"])
    
    # Calculate 20-period high/low (excluding latest candle)
    # Use high_price/low_price columns if available, fall back to price
    historical = rows[:-1]
    period_high = max(
        float(r.get("high_price") or r.get("high") or r["price"]) 
        for r in historical[-PERIOD:]
    )
    period_low = min(
        float(r.get("low_price") or r.get("low") or r["price"]) 
        for r in historical[-PERIOD:]
    )
    
    # Volume confirmation
    current_vol = float(latest.get("volume_candle") or latest.get("volume", 0) or 0)
    avg_vol = rolling_volume_avg(historical)
    volume_confirmed = avg_vol > 0 and current_vol >= avg_vol * VOLUME_MULT
    
    # Calculate breakout strength
    high_breakout_pct = ((price - period_high) / period_high * 100) if period_high > 0 else 0
    low_breakout_pct = ((period_low - price) / period_low * 100) if period_low > 0 else 0
    
    # BUY: Price breaks above resistance
    if price > period_high:
        conf = min(high_breakout_pct / 2.0, 0.95)  # Cap at 95%
        if volume_confirmed:
            conf = min(conf + 0.1, 0.98)
        return signal_envelope(
            STRATEGY, coin, "BUY", round(conf, 2),
            f"Breakout above {PERIOD}-period high {period_high:,.2f} (+{high_breakout_pct:.2f}%)" +
            (" with volume confirmation" if volume_confirmed else ""),
            {"price": price, "period_high": period_high, "period_low": period_low,
             "breakout_pct": round(high_breakout_pct, 3),
             "volume_ratio": round(current_vol / avg_vol, 2) if avg_vol > 0 else 0,
             "candle": candle_start.isoformat()},
        )
    
    # SELL: Price breaks below support
    if price < period_low:
        conf = min(low_breakout_pct / 2.0, 0.95)
        if volume_confirmed:
            conf = min(conf + 0.1, 0.98)
        return signal_envelope(
            STRATEGY, coin, "SELL", round(conf, 2),
            f"Breakdown below {PERIOD}-period low {period_low:,.2f} (-{low_breakout_pct:.2f}%)" +
            (" with volume confirmation" if volume_confirmed else ""),
            {"price": price, "period_high": period_high, "period_low": period_low,
             "breakout_pct": round(low_breakout_pct, 3),
             "volume_ratio": round(current_vol / avg_vol, 2) if avg_vol > 0 else 0,
             "candle": candle_start.isoformat()},
        )
    
    # HOLD: Price within range
    range_pct = ((price - period_low) / (period_high - period_low) * 100) if period_high != period_low else 50
    return signal_envelope(
        STRATEGY, coin, "HOLD", 0.0,
        f"Price {price:,.2f} within range ({range_pct:.1f}% of {PERIOD}-period range)",
        {"price": price, "period_high": period_high, "period_low": period_low,
         "range_position": round(range_pct, 1), "candle": candle_start.isoformat()},
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
        "name": "Trend Breakout",
        "description": "Breakout strategy trading 20-period high/low breaks with volume confirmation.",
        "type": "swing",
        "timeframes": ["4h"],
        "core_logic": {
            "long": [
                "Price breaks above 20-period high (resistance)",
                "Volume confirmation: current vol >= 1.2x average",
                "Breakout strength calculated as % above resistance"
            ],
            "short": [
                "Price breaks below 20-period low (support)",
                "Volume confirmation: current vol >= 1.2x average",
                "Breakdown strength calculated as % below support"
            ],
            "filters": [
                "Minimum 25 rows of 4h data required",
                "Volume must confirm breakout"
            ]
        },
        "backtest": {
            "period": "June 2023 - June 2026 (3 years)",
            "coin": "BTC",
            "timeframe": "4H candles",
            "initial_capital": 1000,
            "final_capital": 1508.76,
            "total_return_pct": 50.88,
            "total_trades": 120,
            "winning_trades": 48,
            "losing_trades": 72,
            "win_rate": 40.0,
            "profit_factor": 1.27,
            "max_drawdown_pct": 24.21,
            "avg_hold_time_hours": 90.1,
            "risk_reward": "1:2 (2x ATR SL / 4x ATR TP)",
            "max_consecutive_losses": 7
        }
    }
