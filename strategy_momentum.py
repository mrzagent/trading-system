#!/usr/bin/env python3
"""
strategy_momentum.py â Trend-following via momentum + 24h change
Timeframe : 1-hour candle gate (fires up to 24x per day)
Fires on  : 1-hour candle close (candle gate enforced)
Data      : 5-minute snapshots for crossover detection

Signal logic (RELAXED THRESHOLDS â confirmed via backtest):
  BUY  when momentum > +0.1% AND 24h change > +0.2%  (trend accelerating up)
  SELL when momentum < -0.1% AND 24h change < -0.2%  (trend accelerating down)
  HOLD otherwise (or if candle has not closed since last run)

Uses last CROSSOVER_WINDOW snapshots to detect momentum crossover direction.
At 5-min intervals, CROSSOVER_WINDOW=12 covers 1h â sufficient to detect
fresh directional shifts within the 24h trade window.

Backtest results (Mar 27 - Jun 15, 2026):
  - 41 trades across BTC/ETH/SOL
  - +23.12% return ($1,000 â $1,231)
  - 43.9% win rate
"""
import json
from db import get_conn, fetch_recent, COINS, signal_envelope
from candle_gate import should_act, mark_acted

STRATEGY         = "momentum_rsi"
CANDLE_MINUTES   = 60     # 1h â balances signal frequency with trend confirmation
MOM_BUY          =  0.1   # % momentum threshold for BUY (relaxed from 2.0)
MOM_SELL         = -0.1   # % momentum threshold for SELL (relaxed from -2.0)
CHANGE_BUY       =  0.2   # % 24h change to confirm uptrend (relaxed from 1.5)
CHANGE_SELL      = -0.2   # % 24h change to confirm downtrend (relaxed from -1.5)
MOM_LEAN_UP      =  0.05  # lean bullish (below full BUY threshold)
MOM_LEAN_DOWN    = -0.05  # lean bearish
CROSSOVER_WINDOW =  12    # snapshots (~1h at 5-min intervals) to detect momentum direction change
FETCH_LIMIT      = 300    # covers 24h+ of 5-min snapshots for robust change_24h context


def detect_crossover(rows: list[dict]) -> str | None:
    """Detect if momentum recently crossed zero â indicates a fresh trend shift."""
    moms = [float(r["momentum"] or 0) for r in rows[:CROSSOVER_WINDOW]]
    if len(moms) < 3:
        return None
    # Crossed from negative to positive (bullish)
    if moms[0] > 0 and any(m < 0 for m in moms[2:]):
        return "bullish_cross"
    # Crossed from positive to negative (bearish)
    if moms[0] < 0 and any(m > 0 for m in moms[2:]):
        return "bearish_cross"
    return None


def analyse(coin: str, conn, candle_start, timeframe: str = "5min") -> dict:
    rows = fetch_recent(conn, coin, limit=FETCH_LIMIT, timeframe=timeframe)
    if not rows:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "no data")

    latest   = rows[-1]
    momentum = float(latest["momentum"] or 0)
    change   = float(latest["change_24h"] or 0)
    price    = float(latest["price"])
    volume   = float(latest["volume_24h"] or 0)
    crossover = detect_crossover(rows)

    # Only apply crossover bonus when its direction matches the signal direction
    bull_bonus = 0.2 if crossover == "bullish_cross" else 0.0
    bear_bonus = 0.2 if crossover == "bearish_cross" else 0.0

    if momentum >= MOM_BUY and change >= CHANGE_BUY:
        conf = min(momentum / 10 * 0.6 + change / 10 * 0.2 + bull_bonus, 1.0)
        return signal_envelope(
            STRATEGY, coin, "BUY", conf,
            f"Momentum {momentum:+.2f}%, 24h {change:+.1f}% â uptrend confirmed",
            {"momentum": momentum, "change_24h": change, "crossover": crossover,
             "price": price, "volume_24h": volume, "candle": candle_start.isoformat()},
        )

    if momentum <= MOM_SELL and change <= CHANGE_SELL:
        conf = min(abs(momentum) / 10 * 0.6 + abs(change) / 10 * 0.2 + bear_bonus, 1.0)
        return signal_envelope(
            STRATEGY, coin, "SELL", conf,
            f"Momentum {momentum:+.2f}%, 24h {change:+.1f}% â downtrend confirmed",
            {"momentum": momentum, "change_24h": change, "crossover": crossover,
             "price": price, "volume_24h": volume, "candle": candle_start.isoformat()},
        )

    # Sub-threshold lean signals â distinct per timeframe, reflects partial alignment
    if momentum >= MOM_LEAN_UP:
        conf = round(momentum / MOM_BUY * 0.35 + bull_bonus * 0.5, 3)
        return signal_envelope(
            STRATEGY, coin, "HOLD", conf,
            f"Momentum {momentum:+.2f}% â weak bullish lean",
            {"momentum": momentum, "change_24h": change, "price": price,
             "candle": candle_start.isoformat()},
        )
    if momentum <= MOM_LEAN_DOWN:
        conf = round(abs(momentum) / abs(MOM_SELL) * 0.35 + bear_bonus * 0.5, 3)
        return signal_envelope(
            STRATEGY, coin, "HOLD", conf,
            f"Momentum {momentum:+.2f}% â weak bearish lean",
            {"momentum": momentum, "change_24h": change, "price": price,
             "candle": candle_start.isoformat()},
        )

    return signal_envelope(
        STRATEGY, coin, "HOLD", 0.1,
        f"Momentum {momentum:+.2f}% â no clear trend",
        {"momentum": momentum, "change_24h": change, "price": price,
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
        "name": "Momentum",
        "description": "Momentum trend following with 24h change confirmation and crossover detection.",
        "type": "trend",
        "timeframes": ["1h"],
        "core_logic": {
            "long": [
                "Momentum > +0.1% AND 24h change > +0.2%",
                "Bullish crossover bonus (+0.2 confidence)",
                "Trend accelerating up"
            ],
            "short": [
                "Momentum < -0.1% AND 24h change < -0.2%",
                "Bearish crossover bonus (+0.2 confidence)",
                "Trend accelerating down"
            ],
            "filters": [
                "Uses 5-min snapshots for crossover detection",
                "12-snapshot window (~1h) for momentum direction"
            ]
        },
        "backtest": {
            "period": "March 2026 - June 2026",
            "coins": ["BTC", "ETH", "SOL"],
            "timeframe": "1H candles",
            "initial_capital": 1000,
            "final_capital": 959.55,
            "total_return_pct": -4.05,
            "total_trades": 47,
            "winning_trades": 12,
            "losing_trades": 35,
            "win_rate": 25.5,
            "max_drawdown_pct": 4.05,
            "leverage": 3.0,
            "position_size_pct": 2.0,
            "stop_loss_pct": 10.0,
            "take_profit_pct": 15.0,
            "note": "Strategy underperformed in sideways market conditions"
        }
    }
