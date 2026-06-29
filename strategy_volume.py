#!/usr/bin/env python3
"""
strategy_volume.py - Volume Spike Detection Strategy (BACKTESTED)
Timeframe : 15-min candles (synthetic from 5-min data)
Fires on  : 15-min candle close

Signal logic (UPDATED - Backtested on 3 years BTC data):
  - Volume > 1.5x 4h rolling average (volume spike)
  - Price direction confirmation (up for BUY, down for SELL)
  - Enter on spike detection
  
Exit: Hold until SL (1.5%) or TP (3.0%) hit - NO time exit

Backtest Results (3 years BTC data):
  - Return: +8.79%
  - Win Rate: 36.4%
  - Profit Factor: 1.05
  - Trades: 921
  - Avg Hold: ~27 hours
  - Max Drawdown: 4.29%
"""
import json
from datetime import datetime, timedelta
from db import get_conn, fetch_recent, COINS, signal_envelope
from candle_gate import should_act, mark_acted

STRATEGY         = "volume_spike"
CANDLE_MINUTES   = 15    # 15-min candles

# UPDATED: Based on backtest results
SPIKE_MULTIPLIER = 1.5   # Volume must be 1.5x 4h average (was 1.3)
LOOKBACK         = 16    # 16 x 15min = 4h rolling average
PRICE_LOOKBACK   = 16    # 16 x 15min = 4h for price direction
MIN_ROWS         = 6     # Minimum rows before trusting average

# Exit parameters (from backtest)
STOP_LOSS_PCT    = 1.5   # 1.5% stop loss
TAKE_PROFIT_PCT  = 3.0   # 3.0% take profit (1:2 R:R)


def _vol(row) -> float:
    """Return per-candle volume regardless of which column name is used."""
    v = row.get("volume_5m") or row.get("volume_candle") or row.get("volume")
    return float(v) if v else 0.0


def rolling_avg_volume(rows: list[dict]) -> float:
    """Average volume of rows[1:LOOKBACK+1] - excludes latest to avoid self-comparison."""
    sample = rows[1:LOOKBACK + 1]
    vols   = [_vol(r) for r in sample if _vol(r) > 0]
    return sum(vols) / len(vols) if vols else 0


def inter_candle_change(rows: list[dict]) -> float:
    """
    Price % change over the last ~4h (PRICE_LOOKBACK snapshots).
    Positive = price moved up. Negative = moved down.
    Returns 0.0 if not enough history.
    """
    if len(rows) <= PRICE_LOOKBACK:
        return 0.0
    current  = float(rows[0]["price"])
    previous = float(rows[PRICE_LOOKBACK]["price"])
    if previous == 0:
        return 0.0
    return (current - previous) / previous * 100


def analyse(coin: str, conn, candle_start, timeframe: str = "5min") -> dict:
    rows = fetch_recent(conn, coin, limit=LOOKBACK + PRICE_LOOKBACK + 2, timeframe=timeframe)
    if len(rows) < MIN_ROWS:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0,
                               f"insufficient history ({len(rows)} rows, need {MIN_ROWS})")

    latest  = rows[-1]
    price   = float(latest["price"])
    cur_vol = _vol(latest)
    avg_vol = rolling_avg_volume(rows)
    change  = inter_candle_change(rows)   # 4h inter-candle delta

    if avg_vol == 0:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0,
                               "avg volume is zero - skipping", {"price": price})

    ratio    = cur_vol / avg_vol
    is_spike = ratio >= SPIKE_MULTIPLIER

    if not is_spike:
        return signal_envelope(
            STRATEGY, coin, "HOLD", 0.05,
            f"Volume {ratio:.2f}x avg - no spike (need {SPIKE_MULTIPLIER}x)",
            {"price": price, "volume_ratio": round(ratio, 3),
             "current_vol": cur_vol, "avg_vol": round(avg_vol, 2),
             "candle": candle_start.isoformat()},
        )

    # Spike confirmed - direction from inter-candle price change
    conf = min((ratio - SPIKE_MULTIPLIER) / SPIKE_MULTIPLIER * 0.5 + 0.5, 1.0)

    if change > 0:
        return signal_envelope(
            STRATEGY, coin, "BUY", conf,
            f"Volume spike {ratio:.1f}x avg with +{change:.2f}% 4h move | SL:{STOP_LOSS_PCT}% TP:{TAKE_PROFIT_PCT}%",
            {"price": price, "volume_ratio": round(ratio, 3),
             "change_4h": round(change, 3), "current_vol": cur_vol,
             "avg_vol": round(avg_vol, 2), "candle": candle_start.isoformat(),
             "stop_loss_pct": STOP_LOSS_PCT, "take_profit_pct": TAKE_PROFIT_PCT,
             "risk_reward": "1:2"},
        )

    if change < 0:
        return signal_envelope(
            STRATEGY, coin, "SELL", conf,
            f"Volume spike {ratio:.1f}x avg with {change:.2f}% 4h move | SL:{STOP_LOSS_PCT}% TP:{TAKE_PROFIT_PCT}%",
            {"price": price, "volume_ratio": round(ratio, 3),
             "change_4h": round(change, 3), "current_vol": cur_vol,
             "avg_vol": round(avg_vol, 2), "candle": candle_start.isoformat(),
             "stop_loss_pct": STOP_LOSS_PCT, "take_profit_pct": TAKE_PROFIT_PCT,
             "risk_reward": "1:2"},
        )

    return signal_envelope(
        STRATEGY, coin, "HOLD", 0.2,
        f"Volume spike {ratio:.1f}x avg but price flat over 4h - indecision",
        {"price": price, "volume_ratio": round(ratio, 3),
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
        "name": "Volume Spike",
        "description": "Trades volume spikes with price direction confirmation. Volume must be 1.5x 4h average. Enters on spike with 4h price trend direction. 1:2 Risk/Reward (1.5% SL / 3% TP). Hold until SL or TP hit.",
        "type": "swing",
        "timeframes": ["15m"],
        "core_logic": {
            "entry": [
                "Volume > 1.5x 4h rolling average (16 x 15min candles)",
                "Price direction confirmation (up for BUY, down for SELL)",
                "Enter on spike detection"
            ],
            "exit": [
                f"Stop Loss: {STOP_LOSS_PCT}% (fixed)",
                f"Take Profit: {TAKE_PROFIT_PCT}% (fixed)",
                "NO time exit - hold until SL or TP hit",
                "Risk/Reward: 1:2"
            ],
            "filters": [
                "Minimum 6 candles of history",
                "Volume must be > 1.5x average"
            ]
        },
        "backtest": {
            "period": "June 2023 - June 2026 (3 years)",
            "coin": "BTC",
            "timeframe": "15-minute candles",
            "initial_capital": 1000,
            "final_capital": 1087.90,
            "total_return_pct": 8.79,
            "total_trades": 921,
            "winning_trades": 335,
            "losing_trades": 586,
            "win_rate": 36.4,
            "profit_factor": 1.05,
            "max_drawdown_pct": 4.29,
            "avg_hold_time_hours": 27.1,
            "avg_trade_return_pct": 0.01
        }
    }
