#!/usr/bin/env python3
"""
strategy_momentum_rsi.py — Momentum + RSI Confluence Strategy
Timeframe : 1-hour candle gate (fires up to 24× per day)
Fires on  : 1-hour candle close (candle gate enforced)
Data      : 5-minute snapshots for momentum crossover detection

Signal logic (CONFLUENCE):
  BUY when:
    - Momentum > 0 AND 24h change > 0 (trending up)
    - RSI has room to rise (15m RSI < 60 AND 1h RSI < 65)
    
  SELL when:
    - Momentum < 0 AND 24h change < 0 (trending down)
    - RSI has room to fall (15m RSI > 40 AND 1h RSI > 35)
    
  HOLD otherwise

Uses dual-timeframe RSI from strategy_rsi.py logic:
  - 15m RSI calculated from last 15 price points
  - 1h RSI approximated using 12× 5-min rows
"""
import json
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"D:\dev\trading")
from db import get_conn, fetch_recent, COINS, signal_envelope
from candle_gate import should_act, mark_acted

STRATEGY       = "momentum_rsi_confluence"
CANDLE_MINUTES = 60    # 1-hour candles
FETCH_LIMIT    = 22    # Enough for RSI 1h approximation (12 rows) + buffer
CROSSOVER_WINDOW = 12  # 1 hour of 5-min snapshots for momentum crossover

# Momentum thresholds (relaxed for confluence)
MOM_THRESHOLD = 0.3    # 0.3% momentum minimum (filters noise)
CHANGE_THRESHOLD = 0.1 # 0.1% 24h change minimum (was 0.2%)

# RSI thresholds (from strategy_rsi.py, used for "room to move" calculation)
RSI_15M_OVERBOUGHT = 60  # Must be below this to buy
RSI_15M_OVERSOLD = 40    # Must be above this to sell
RSI_1H_OVERBOUGHT = 65   # Must be below this to buy
RSI_1H_OVERSOLD = 35     # Must be above this to sell


def calculate_rsi(prices: list[float], period: int = 14) -> float:
    """Calculate RSI from price series."""
    if len(prices) < period + 1:
        return 50.0
    
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
        return 50.0
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def detect_crossover(moms: list[float]) -> str | None:
    """Detect if momentum recently crossed zero."""
    if len(moms) < 3:
        return None
    if moms[-1] > 0 and any(m < 0 for m in moms[:-2]):
        return "bullish_cross"
    if moms[-1] < 0 and any(m > 0 for m in moms[:-2]):
        return "bearish_cross"
    return None


def analyse(coin: str, conn, candle_start, timeframe: str = "5min") -> dict:
    rows = fetch_recent(conn, coin, limit=FETCH_LIMIT, timeframe=timeframe)
    if len(rows) < 15:  # Need at least 15 rows for 15m RSI
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "insufficient data")

    # Extract momentum and 24h change from latest row
    latest = rows[-1]
    momentum = float(latest.get("momentum") or 0)
    change_24h = float(latest.get("change_24h") or 0)
    price = float(latest["price"])

    # Get momentum history for crossover detection
    mom_history = [float(r.get("momentum") or 0) for r in rows[-CROSSOVER_WINDOW:]]
    crossover = detect_crossover(mom_history)

    # Calculate dual-timeframe RSI
    prices = [float(r["price"]) for r in rows]
    rsi_15m = calculate_rsi(prices[-15:], period=14)
    rsi_1h = calculate_rsi(prices, period=14)  # Approximation using available data

    # Check confluence conditions
    mom_bullish = momentum > MOM_THRESHOLD and change_24h > CHANGE_THRESHOLD
    mom_bearish = momentum < -MOM_THRESHOLD and change_24h < -CHANGE_THRESHOLD

    # RSI "room to move" checks
    rsi_room_to_rise = rsi_15m < RSI_15M_OVERBOUGHT and rsi_1h < RSI_1H_OVERBOUGHT
    rsi_room_to_fall = rsi_15m > RSI_15M_OVERSOLD and rsi_1h > RSI_1H_OVERSOLD

    # Crossover bonuses
    bull_bonus = 0.15 if crossover == "bullish_cross" else 0.0
    bear_bonus = 0.15 if crossover == "bearish_cross" else 0.0

    # CONFLUENCE: Both momentum AND RSI must agree
    if mom_bullish and rsi_room_to_rise:
        # Scale: momentum 1.0% = 0.5 confidence contribution
        conf = min(
            (abs(momentum) * 0.5 + abs(change_24h) * 0.1 + 
             bull_bonus + (100 - rsi_15m) / 100 * 0.3),
            1.0
        )
        return signal_envelope(
            STRATEGY, coin, "BUY", round(conf, 2),
            f"Momentum +{momentum:.2f}%, 24h +{change_24h:.2f}%, RSI {rsi_15m:.1f}/{rsi_1h:.1f}",
            {
                "price": price,
                "momentum": momentum,
                "change_24h": change_24h,
                "rsi_15m": round(rsi_15m, 2),
                "rsi_1h": round(rsi_1h, 2),
                "crossover": crossover,
                "candle": candle_start.isoformat()
            }
        )

    if mom_bearish and rsi_room_to_fall:
        # Scale: momentum 1.0% = 0.5 confidence contribution
        conf = min(
            (abs(momentum) * 0.5 + abs(change_24h) * 0.1 + 
             bear_bonus + rsi_15m / 100 * 0.3),
            1.0
        )
        return signal_envelope(
            STRATEGY, coin, "SELL", round(conf, 2),
            f"Momentum {momentum:.2f}%, 24h {change_24h:.2f}%, RSI {rsi_15m:.1f}/{rsi_1h:.1f}",
            {
                "price": price,
                "momentum": momentum,
                "change_24h": change_24h,
                "rsi_15m": round(rsi_15m, 2),
                "rsi_1h": round(rsi_1h, 2),
                "crossover": crossover,
                "candle": candle_start.isoformat()
            }
        )

    # No signal — explain why
    reasons = []
    if not mom_bullish and not mom_bearish:
        reasons.append(f"mom {momentum:+.2f}%")
    if not rsi_room_to_rise and not rsi_room_to_fall:
        reasons.append(f"RSI {rsi_15m:.1f}/{rsi_1h:.1f}")

    return signal_envelope(
        STRATEGY, coin, "HOLD", 0.0,
        " | ".join(reasons) if reasons else "no confluence",
        {
            "price": price,
            "momentum": momentum,
            "change_24h": change_24h,
            "rsi_15m": round(rsi_15m, 2),
            "rsi_1h": round(rsi_1h, 2),
            "candle": candle_start.isoformat()
        }
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


# -- Strategy metadata class (used by strategy_registry.py) -----------------
import sys as _sys
_sys.path.insert(0, r"D:\dev\trading")
from strategy_base import BaseStrategy as _BaseStrategy


class MomentumRSIStrategy(_BaseStrategy):
    """Momentum + RSI Confluence � metadata wrapper."""

    name = "Momentum + RSI Confluence"
    description = (
        "Dual-timeframe confluence strategy that combines momentum direction "
        "with RSI 'room-to-move' filters. Fires on 1-hour candle closes using "
        "5-minute snapshot data. Avoids entries when RSI is already stretched."
    )
    type = "swing"
    timeframes = ["1h"]
    core_logic = {
        "long": [
            "Momentum > 0 AND 24h price change > 0 (uptrend confirmed)",
            "15m RSI < 60 AND 1h RSI < 65 (room to rise)",
        ],
        "short": [
            "Momentum < 0 AND 24h price change < 0 (downtrend confirmed)",
            "15m RSI > 40 AND 1h RSI > 35 (room to fall)",
        ],
        "filters": [
            "Candle gate: maximum one signal per 1-hour candle",
            "Minimum momentum threshold: 0.3%",
            "Minimum 24h change threshold: 0.1%",
        ],
    }

    def signals(self):  # pragma: no cover
        """Delegate to the module-level main() logic."""
        raise NotImplementedError("Run this strategy as a script or via its main() function.")

# ── Strategy metadata class (used by strategy_registry.py) ─────────────────────────────────────
import sys as _sys
_sys.path.insert(0, r"D:\dev\trading")
from strategy_base import BaseStrategy as _BaseStrategy


class MomentumRSIStrategy(_BaseStrategy):
    """Momentum + RSI Confluence - metadata wrapper."""

    name = "Momentum + RSI Confluence"
    description = (
        "Dual-timeframe confluence strategy that combines momentum direction "
        "with RSI 'room-to-move' filters. Fires on 1-hour candle closes using "
        "5-minute snapshot data. Avoids entries when RSI is already stretched."
    )
    type = "swing"
    timeframes = ["1h"]
    core_logic = {
        "long": [
            "Momentum > 0 AND 24h price change > 0 (uptrend confirmed)",
            "15m RSI < 60 AND 1h RSI < 65 (room to rise)",
        ],
        "short": [
            "Momentum < 0 AND 24h price change < 0 (downtrend confirmed)",
            "15m RSI > 40 AND 1h RSI > 35 (room to fall)",
        ],
        "filters": [
            "Candle gate: maximum one signal per 1-hour candle",
            "Minimum momentum threshold: 0.3%",
            "Minimum 24h change threshold: 0.1%",
        ],
    }

    def signals(self):  # pragma: no cover
        raise NotImplementedError("Run this strategy as a script or via its main() function.")
