#!/usr/bin/env python3
"""
strategy_pullback_scalper.py â Pullback Scalper Strategy
Timeframe : 5M candles (also valid on 15M)
Type      : Scalp trade (trend pullback)

Objective:
    Join established trends on temporary pullbacks. Waits for price to retrace
    to EMA20 during a trend, then confirms re-entry with extreme RSI(2) and
    a confirming candle before entering.

Long Entry Conditions (ALL 4 must be true):
    1. EMA20 > EMA50              â established uptrend
    2. Price pulls back to EMA20  â touch or close below EMA20
    3. RSI(2) < 20                â extreme short-term oversold
    4. Current candle closes higher than open  â bullish confirmation candle

Short Entry Conditions (ALL 4 must be true):
    1. EMA20 < EMA50              â established downtrend
    2. Price rallies into EMA20   â touch or close above EMA20
    3. RSI(2) > 80                â extreme short-term overbought
    4. Current candle closes lower than open   â bearish confirmation candle

Exit / Risk Management:
    - Stop loss : below recent swing low (long) / above recent swing high (short)
                  (LOOKBACK_SWING periods)
    - Take profit: 1.5â2R based on stop distance
"""

import json
import logging
import sys
from datetime import datetime

sys.path.insert(0, r"D:\dev\trading")
from db import get_conn, fetch_recent, COINS, signal_envelope
from candle_gate import should_act, mark_acted

# âââ Logging ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s â %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("pullback_scalper")

# âââ Strategy Identity ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
STRATEGY       = "pullback_scalper"
CANDLE_MINUTES = 5

# âââ Key Constants ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
COINS          = ["BTC", "ETH", "SOL"]
EMA_FAST       = 20    # EMA20 â pullback target / trend filter
EMA_SLOW       = 50    # EMA50 â trend direction
RSI_PERIOD     = 2     # Ultra-short RSI for extreme readings
RSI_OVERSOLD   = 20    # Extreme oversold threshold (long entry)
RSI_OVERBOUGHT = 80    # Extreme overbought threshold (short entry)
LOOKBACK_SWING = 5     # Periods to look back for recent swing high/low
TP_R_RATIO     = 1.5   # Minimum risk:reward ratio for take-profit

# We need enough history for EMA50 + RSI2 + swing lookback
MIN_ROWS = max(EMA_SLOW, RSI_PERIOD, LOOKBACK_SWING) + 20  # = 70


# âââ Indicator Calculations ââââââââââââââââââââââââââââââââââââââââââââââââââââ

def calculate_ema(prices: list[float], period: int) -> list[float]:
    """
    Compute Exponential Moving Average series.
    Returns list of same length as prices; early values filled with NaN.
    Seeds the EMA with the SMA of the first `period` values.
    """
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


def calculate_rsi(closes: list[float], period: int) -> list[float]:
    """
    Compute RSI series using Wilder's smoothing (EMA-style).
    Returns list of same length as closes; early values filled with NaN.
    """
    n = len(closes)
    rsi_values = [float("nan")] * n

    if n <= period:
        return rsi_values

    gains = []
    losses = []
    for i in range(1, n):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    if len(gains) < period:
        return rsi_values

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            rsi_values[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi_values[i + 1] = 100.0 - (100.0 / (1.0 + rs))

    return rsi_values


def get_swing_high(highs: list[float], lookback: int) -> float:
    """
    Return the highest high over the last `lookback` bars,
    EXCLUDING the current (last) bar.
    """
    window = highs[-lookback - 1:-1]
    return max(window) if window else float("nan")


def get_swing_low(lows: list[float], lookback: int) -> float:
    """
    Return the lowest low over the last `lookback` bars,
    EXCLUDING the current (last) bar.
    """
    window = lows[-lookback - 1:-1]
    return min(window) if window else float("nan")


# âââ Signal Analysis âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def analyse(coin: str, conn, candle_start: datetime, timeframe: str = "5min") -> dict:
    """
    Run pullback scalper analysis for a single coin.

    Signal fires when ALL 4 conditions are met:
        1. EMA20 > EMA50  (long) or EMA20 < EMA50 (short)
        2. Price at EMA20 â touches or closes below/above EMA20
        3. RSI(2) < RSI_OVERSOLD (long) or RSI(2) > RSI_OVERBOUGHT (short)
        4. Confirming candle â bullish (long) or bearish (short)

    Returns a standard signal_envelope dict with action BUY/SELL/HOLD.
    """
    rows = fetch_recent(conn, coin, limit=MIN_ROWS, timeframe=timeframe)

    if len(rows) < MIN_ROWS:
        log.warning("%s: insufficient data (%d rows, need %d)", coin, len(rows), MIN_ROWS)
        return signal_envelope(
            STRATEGY, coin, "HOLD", 0.0,
            f"insufficient data ({len(rows)}/{MIN_ROWS} rows)",
        )

    # Extract OHLCV series (oldest â newest)
    opens   = [float(r.get("open",  r["price"]))  for r in rows]
    closes  = [float(r["price"])                   for r in rows]
    highs   = [float(r.get("high",  r["price"]))   for r in rows]
    lows    = [float(r.get("low",   r["price"]))   for r in rows]

    price     = closes[-1]
    open_last = opens[-1]
    high_last = highs[-1]
    low_last  = lows[-1]

    # ââ Condition 1: EMA Trend Direction âââââââââââââââââââââââââââââââââââââ
    ema_fast_series = calculate_ema(closes, EMA_FAST)
    ema_slow_series = calculate_ema(closes, EMA_SLOW)

    ema_fast = ema_fast_series[-1]
    ema_slow = ema_slow_series[-1]

    if any(v != v for v in [ema_fast, ema_slow]):
        log.warning("%s: EMA calculation returned NaN (insufficient history)", coin)
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "EMA NaN â insufficient history")

    uptrend   = ema_fast > ema_slow   # EMA20 > EMA50
    downtrend = ema_fast < ema_slow   # EMA20 < EMA50

    ema_separation_pct = abs(ema_fast - ema_slow) / ema_slow * 100

    # ââ Condition 2: Price at EMA20 âââââââââââââââââââââââââââââââââââââââââââ
    # Long: price touches or closes below EMA20 (pullback into EMA20)
    # Short: price touches or closes above EMA20 (rally into EMA20)
    pulled_back_to_ema = low_last <= ema_fast   # Low touched EMA20 from above
    rallied_to_ema     = high_last >= ema_fast  # High touched EMA20 from below

    # ââ Condition 3: RSI(2) Extreme âââââââââââââââââââââââââââââââââââââââââââ
    rsi_series = calculate_rsi(closes, RSI_PERIOD)
    current_rsi = rsi_series[-1]

    if current_rsi != current_rsi:  # NaN check
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "RSI NaN â insufficient history")

    rsi_oversold   = current_rsi < RSI_OVERSOLD    # RSI(2) < 20
    rsi_overbought = current_rsi > RSI_OVERBOUGHT  # RSI(2) > 80

    # ââ Condition 4: Confirming Candle ââââââââââââââââââââââââââââââââââââââââ
    bullish_candle = price > open_last  # Close > Open (bullish)
    bearish_candle = price < open_last  # Close < Open (bearish)

    candle_body_pct = abs(price - open_last) / open_last * 100

    # ââ Swing High/Low for Stop-Loss / Take-Profit ââââââââââââââââââââââââââââ
    swing_high = get_swing_high(highs, LOOKBACK_SWING)
    swing_low  = get_swing_low(lows, LOOKBACK_SWING)

    if swing_high != swing_high or swing_low != swing_low:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "Swing high/low NaN â insufficient history")

    # ââ Meta dict âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    meta = {
        "price":        price,
        "open":         open_last,
        "ema20":        round(ema_fast, 4),
        "ema50":        round(ema_slow, 4),
        "ema_sep_pct":  round(ema_separation_pct, 3),
        "rsi2":         round(current_rsi, 2),
        "swing_high":   round(swing_high, 4),
        "swing_low":    round(swing_low, 4),
        "candle_body_pct": round(candle_body_pct, 3),
        "candle":       candle_start.isoformat(),
        "timeframe":    timeframe,
        "conditions": {
            "trend":           uptrend or downtrend,
            "pullback_to_ema": pulled_back_to_ema or rallied_to_ema,
            "rsi_extreme":     rsi_oversold or rsi_overbought,
            "candle_confirm":  bullish_candle or bearish_candle,
        },
    }

    # ââ Signal Decision âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    # ALL 4 conditions must be met for a signal

    # LONG: uptrend + pulled back to EMA20 + oversold RSI + bullish candle
    if uptrend and pulled_back_to_ema and rsi_oversold and bullish_candle:
        # Stop-loss: below recent swing low
        sl_price = round(swing_low, 4)
        sl_dist  = price - sl_price

        if sl_dist <= 0:
            log.warning("%s: invalid SL distance for BUY (sl=%.4f price=%.4f)", coin, sl_price, price)
            return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "Invalid SL distance (price below swing low)")

        tp_price = round(price + sl_dist * TP_R_RATIO, 4)  # 1.5R minimum

        # Confidence scoring (base 0.55):
        # +0.10 EMA separation quality (stronger trend = more confidence)
        # +0.10 RSI depth (deeper oversold = better pullback)
        # +0.05 candle body size (conviction)
        rsi_depth = (RSI_OVERSOLD - current_rsi) / RSI_OVERSOLD  # 0.0â1.0
        conf = 0.55
        conf += min(ema_separation_pct * 0.5, 0.10)
        conf += min(rsi_depth * 0.15, 0.10)
        conf += min(candle_body_pct * 0.10, 0.05)
        conf = round(min(conf, 0.95), 2)

        pullback_depth_pct = (ema_fast - low_last) / ema_fast * 100

        meta.update({
            "sl_price":          sl_price,
            "tp_price":          tp_price,
            "sl_dist":           round(sl_dist, 4),
            "rr_ratio":          TP_R_RATIO,
            "pullback_depth_pct": round(pullback_depth_pct, 3),
        })

        log.info(
            "BUY signal %s | price=%.4f ema20=%.4f ema50=%.4f rsi2=%.1f "
            "swing_low=%.4f sl=%.4f tp=%.4f conf=%.2f",
            coin, price, ema_fast, ema_slow, current_rsi,
            swing_low, sl_price, tp_price, conf,
        )
        return signal_envelope(
            STRATEGY, coin, "BUY", conf,
            f"Uptrend pullback to EMA20 | RSI(2)={current_rsi:.1f} (oversold) "
            f"| bullish candle | SL={sl_price:.4f} TP={tp_price:.4f} ({TP_R_RATIO}R)",
            meta,
        )

    # SHORT: downtrend + rallied to EMA20 + overbought RSI + bearish candle
    if downtrend and rallied_to_ema and rsi_overbought and bearish_candle:
        # Stop-loss: above recent swing high
        sl_price = round(swing_high, 4)
        sl_dist  = sl_price - price

        if sl_dist <= 0:
            log.warning("%s: invalid SL distance for SELL (sl=%.4f price=%.4f)", coin, sl_price, price)
            return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "Invalid SL distance (price above swing high)")

        tp_price = round(price - sl_dist * TP_R_RATIO, 4)  # 1.5R minimum

        # Confidence scoring
        rsi_excess = (current_rsi - RSI_OVERBOUGHT) / (100 - RSI_OVERBOUGHT)  # 0.0â1.0
        conf = 0.55
        conf += min(ema_separation_pct * 0.5, 0.10)
        conf += min(rsi_excess * 0.15, 0.10)
        conf += min(candle_body_pct * 0.10, 0.05)
        conf = round(min(conf, 0.95), 2)

        rally_height_pct = (high_last - ema_fast) / ema_fast * 100

        meta.update({
            "sl_price":         sl_price,
            "tp_price":         tp_price,
            "sl_dist":          round(sl_dist, 4),
            "rr_ratio":         TP_R_RATIO,
            "rally_height_pct": round(rally_height_pct, 3),
        })

        log.info(
            "SELL signal %s | price=%.4f ema20=%.4f ema50=%.4f rsi2=%.1f "
            "swing_high=%.4f sl=%.4f tp=%.4f conf=%.2f",
            coin, price, ema_fast, ema_slow, current_rsi,
            swing_high, sl_price, tp_price, conf,
        )
        return signal_envelope(
            STRATEGY, coin, "SELL", conf,
            f"Downtrend rally to EMA20 | RSI(2)={current_rsi:.1f} (overbought) "
            f"| bearish candle | SL={sl_price:.4f} TP={tp_price:.4f} ({TP_R_RATIO}R)",
            meta,
        )

    # HOLD â explain which conditions failed
    reasons = []

    if uptrend:
        reasons.append("uptrend confirmed (EMA20>EMA50)")
        if not pulled_back_to_ema:
            reasons.append(f"no pullback to EMA20 (price={price:.4f} low={low_last:.4f} ema20={ema_fast:.4f})")
        if not rsi_oversold:
            reasons.append(f"RSI(2)={current_rsi:.1f} not oversold (<{RSI_OVERSOLD})")
        if not bullish_candle:
            reasons.append(f"no bullish candle (open={open_last:.4f} close={price:.4f})")
    elif downtrend:
        reasons.append("downtrend confirmed (EMA20<EMA50)")
        if not rallied_to_ema:
            reasons.append(f"no rally to EMA20 (price={price:.4f} high={high_last:.4f} ema20={ema_fast:.4f})")
        if not rsi_overbought:
            reasons.append(f"RSI(2)={current_rsi:.1f} not overbought (>{RSI_OVERBOUGHT})")
        if not bearish_candle:
            reasons.append(f"no bearish candle (open={open_last:.4f} close={price:.4f})")
    else:
        reasons.append(
            f"no trend direction (EMA20={ema_fast:.4f} EMA50={ema_slow:.4f} sep={ema_separation_pct:.2f}%)"
        )

    reason_str = " | ".join(reasons) if reasons else "no signal"
    log.debug("HOLD %s: %s", coin, reason_str)

    return signal_envelope(STRATEGY, coin, "HOLD", 0.0, reason_str, meta)


# âââ Entry Point ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def main():
    """
    Standalone entry point. Checks candle gate, analyses all coins, prints JSON.

    Can also be imported by the orchestrator and called via analyse() directly.
    """
    act, candle_start = should_act(STRATEGY, CANDLE_MINUTES)
    if not act:
        log.debug("Candle gate: %s already acted this 5min candle", STRATEGY)
        print(json.dumps([{
            "strategy": STRATEGY,
            "action":   "HOLD",
            "reason":   "candle not closed yet (5min)",
        }]))
        return

    log.info("Running %s | timeframe=5min | coins=%s", STRATEGY, COINS)
    log.info(
        "Config: EMA%d/EMA%d | RSI(%d) oversold=%d overbought=%d | Swing lookback=%d | TP=%.1fR",
        EMA_FAST, EMA_SLOW, RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT, LOOKBACK_SWING, TP_R_RATIO,
    )

    conn = get_conn()
    signals = [analyse(coin, conn, candle_start, timeframe="5min") for coin in COINS]
    conn.close()

    mark_acted(STRATEGY, candle_start)
    print(json.dumps(signals, indent=2))


if __name__ == "__main__":
    main()


# ââ Strategy metadata class (used by strategy_registry.py) âââââââââââââââââââ
import sys as _sys
_sys.path.insert(0, r"D:\dev\trading")
from strategies.strategy_base import BaseStrategy as _BaseStrategy


class PullbackScalperStrategy(_BaseStrategy):
    """Pullback Scalper â metadata wrapper for strategy_registry."""

    name = "Pullback Scalper"
    description = (
        "Scalp strategy that joins established trends on temporary pullbacks. "
        "Waits for price to retrace to EMA20 during a trend, then confirms "
        "re-entry with extreme RSI(2) and a confirming candle on 5-minute candles."
    )
    type = "scalp"
    timeframes = ["5m", "15m"]
    core_logic = {
        "long": [
            "EMA20 > EMA50 â established uptrend",
            "Price pulls back to EMA20 (low touches or closes below EMA20)",
            "RSI(2) < 20 â extreme short-term oversold",
            "Bullish candle confirmation (close > open)",
        ],
        "short": [
            "EMA20 < EMA50 â established downtrend",
            "Price rallies into EMA20 (high touches or closes above EMA20)",
            "RSI(2) > 80 â extreme short-term overbought",
            "Bearish candle confirmation (close < open)",
        ],
        "filters": [
            "All 4 conditions must be true simultaneously (strict AND logic)",
            "Stop loss: below recent swing low (long) / above recent swing high (short) â last 5 bars",
            "Take profit: 1.5R (1.5x stop-loss distance)",
        ],
    }

    def get_metadata(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "timeframes": list(self.timeframes),
            "core_logic": {
                "long": list(self.core_logic["long"]),
                "short": list(self.core_logic["short"]),
                "filters": list(self.core_logic["filters"]),
            },
            "backtest": {
                "note": "Backtest not yet run â requires 5-min OHLC data and tick-level execution simulation"
            },
        }

    def signals(self):  # pragma: no cover
        raise NotImplementedError("Run this strategy as a script or via its main() function.")
