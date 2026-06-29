#!/usr/bin/env python3
"""
strategy_momentum_acceleration.py — Momentum Acceleration Strategy
Timeframe : 1H and 4H candles (configurable via TIMEFRAME env var)
Type      : Breakout / continuation trade (high frequency vs. swing)

Objective:
    Capture explosive momentum moves — fires when all four conditions
    align: EMA stack, range breakout, volume spike, and expanding ATR.

Long Entry Conditions (ALL 4 must be true):
    1. EMA20 > EMA50 > EMA200     — strong uptrend alignment (3-EMA stack)
    2. Close > 30-period High     — breakout above recent range
    3. Volume > 1.5 × SMA20(vol)  — volume spike confirms participation
    4. ATR(14) > ATR_SMA50        — expanding volatility confirms momentum

Short Entry Conditions (ALL 4 must be true):
    1. EMA20 < EMA50 < EMA200     — strong downtrend alignment (3-EMA stack)
    2. Close < 30-period Low      — breakdown below recent range
    3. Volume > 1.5 × SMA20(vol)  — volume spike confirms participation
    4. ATR(14) > ATR_SMA50        — expanding volatility confirms momentum

Exit / Risk Management:
    - Stop loss : ATR-based (default 1.5× ATR14 from entry — tighter for momentum)
    - Take profit: ATR-based (default 3.0× ATR14 — 2:1 R-multiple)
    - Position size: risk RISK_PCT of portfolio per trade

Configuration via environment variables:
    TIMEFRAME           : "1h" | "4h" (default: "1h")
    EMA_FAST            : fast EMA period (default: 20)
    EMA_MID             : mid EMA period (default: 50)
    EMA_SLOW            : slow EMA period (default: 200)
    BREAKOUT_PERIOD     : lookback for 30-period High/Low (default: 30)
    VOLUME_MULT         : volume multiplier threshold (default: 1.5)
    ATR_PERIOD          : ATR calculation period (default: 14)
    ATR_SMA_PERIOD      : SMA period for ATR baseline (default: 50)
    RISK_PCT            : % of portfolio to risk per trade (default: 1.0)
    ATR_SL_MULT         : ATR multiplier for stop loss (default: 1.5)
    ATR_TP_MULT         : ATR multiplier for take profit (default: 3.0)
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"D:\dev\trading")
from db import get_conn, fetch_recent, COINS, signal_envelope
from candle_gate import should_act, mark_acted

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("momentum_acceleration")

# ─── Strategy Identity ────────────────────────────────────────────────────────
STRATEGY = "momentum_acceleration"

# ─── Configuration (from env vars with sensible defaults) ─────────────────────
TIMEFRAME       = os.getenv("TIMEFRAME", "1h")                    # candle timeframe
EMA_FAST        = int(os.getenv("EMA_FAST", "20"))                # fast EMA (default: 20)
EMA_MID         = int(os.getenv("EMA_MID", "50"))                 # mid EMA (default: 50)
EMA_SLOW        = int(os.getenv("EMA_SLOW", "200"))               # slow EMA (default: 200)
BREAKOUT_PERIOD = int(os.getenv("BREAKOUT_PERIOD", "30"))         # 30-period High/Low lookback
VOLUME_MULT     = float(os.getenv("VOLUME_MULT", "1.5"))          # volume > VOLUME_MULT × SMA20
ATR_PERIOD      = int(os.getenv("ATR_PERIOD", "14"))              # ATR calculation period
ATR_SMA_PERIOD  = int(os.getenv("ATR_SMA_PERIOD", "50"))         # SMA period for ATR baseline
RISK_PCT        = float(os.getenv("RISK_PCT", "1.0"))             # % portfolio risked per trade
ATR_SL_MULT     = float(os.getenv("ATR_SL_MULT", "1.5"))         # stop-loss ATR multiplier
ATR_TP_MULT     = float(os.getenv("ATR_TP_MULT", "3.0"))         # take-profit ATR multiplier

# Candle period in minutes (1h = 60, 4h = 240)
_TF_MINUTES = {"1h": 60, "4h": 240}
CANDLE_MINUTES = _TF_MINUTES.get(TIMEFRAME, 60)

# We need enough rows to compute EMA200 + ATR_SMA50 + breakout period
# Extra buffer ensures ATR series has enough history for SMA50
MIN_ROWS = max(EMA_SLOW, ATR_PERIOD + ATR_SMA_PERIOD, BREAKOUT_PERIOD) + 20


# ─── Indicator Calculations ────────────────────────────────────────────────────

def calculate_ema(prices: list[float], period: int) -> list[float]:
    """
    Compute Exponential Moving Average series.
    Returns list of same length as prices; early values filled with NaN.
    Seeds the EMA with SMA of the first `period` values.
    """
    n = len(prices)
    if n < period:
        return [float("nan")] * n

    ema_values = [float("nan")] * n
    multiplier = 2.0 / (period + 1)

    # Seed: SMA of first `period` values
    seed = sum(prices[:period]) / period
    ema_values[period - 1] = seed

    for i in range(period, n):
        ema_values[i] = (prices[i] - ema_values[i - 1]) * multiplier + ema_values[i - 1]

    return ema_values


def calculate_atr_series(highs: list[float], lows: list[float], closes: list[float], period: int) -> list[float]:
    """
    Compute ATR series using simple (arithmetic) smoothing.
    True Range = max(high-low, abs(high-prev_close), abs(low-prev_close))
    Returns list of ATR values, same length as closes; early values are NaN.
    """
    n = len(closes)
    atr_series = [float("nan")] * n

    if n < period + 1:
        return atr_series

    # Build TR list (length = n-1, index 0 = between bar 0 and bar 1)
    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    # First ATR = simple average of first `period` TRs
    if len(trs) < period:
        return atr_series

    first_atr = sum(trs[:period]) / period
    atr_series[period] = first_atr  # ATR[period] corresponds to closes[period]

    for i in range(period, len(trs)):
        atr_series[i + 1] = (atr_series[i] * (period - 1) + trs[i]) / period

    return atr_series


def calculate_sma_of_series(values: list[float], period: int) -> list[float]:
    """
    Compute SMA series over a list of values (which may contain NaN).
    Returns list of same length; early values and NaN inputs yield NaN.
    """
    n = len(values)
    sma_series = [float("nan")] * n

    for i in range(n):
        window = [v for v in values[max(0, i - period + 1): i + 1] if v == v]  # filter NaN
        if len(window) == period:
            sma_series[i] = sum(window) / period

    return sma_series


def calculate_range_extremes(highs: list[float], lows: list[float], period: int) -> tuple[float, float]:
    """
    Return the highest high and lowest low over the last `period` bars,
    EXCLUDING the current (last) bar — we compare close against historical range.

    Returns (range_high, range_low).
    """
    lookback_highs = highs[-period - 1: -1]
    lookback_lows  = lows[-period - 1: -1]
    if not lookback_highs or not lookback_lows:
        return float("nan"), float("nan")
    return max(lookback_highs), min(lookback_lows)


def calculate_sma_scalar(values: list[float], period: int) -> float:
    """Simple moving average scalar of the last `period` non-NaN values."""
    filtered = [v for v in values[-period:] if v == v]
    if len(filtered) < period:
        return float("nan")
    return sum(filtered) / period


# ─── Signal Analysis ───────────────────────────────────────────────────────────

def analyse(coin: str, conn, candle_start: datetime, timeframe: str = "1h") -> dict:
    """
    Run momentum acceleration analysis for a single coin.

    Signal fires when ALL 4 conditions are met:
        1. EMA20 > EMA50 > EMA200  (long) or EMA20 < EMA50 < EMA200 (short)
        2. Close breaks 30-period High (long) or Low (short)
        3. Volume > VOLUME_MULT × SMA20(volume)
        4. ATR(14) > ATR_SMA50

    Returns a standard signal_envelope dict with action BUY/SELL/HOLD.
    """
    rows = fetch_recent(conn, coin, limit=MIN_ROWS, timeframe=timeframe)

    if len(rows) < MIN_ROWS:
        log.warning("%s: insufficient data (%d rows, need %d)", coin, len(rows), MIN_ROWS)
        return signal_envelope(
            STRATEGY, coin, "HOLD", 0.0,
            f"insufficient data ({len(rows)}/{MIN_ROWS} rows)",
        )

    # Extract OHLCV series (oldest → newest)
    closes  = [float(r["price"])                  for r in rows]
    highs   = [float(r.get("high",  r["price"]))  for r in rows]
    lows    = [float(r.get("low",   r["price"]))  for r in rows]
    volumes = [float(r.get("volume", 0) or 0)     for r in rows]

    price = closes[-1]

    # ── Condition 1: 3-EMA Stack ──────────────────────────────────────────────
    ema_fast_series = calculate_ema(closes, EMA_FAST)
    ema_mid_series  = calculate_ema(closes, EMA_MID)
    ema_slow_series = calculate_ema(closes, EMA_SLOW)

    ema_fast = ema_fast_series[-1]
    ema_mid  = ema_mid_series[-1]
    ema_slow = ema_slow_series[-1]

    # NaN safety check
    if any(v != v for v in [ema_fast, ema_mid, ema_slow]):
        log.warning("%s: EMA calculation returned NaN (not enough history)", coin)
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "EMA NaN — insufficient history")

    bullish_stack = ema_fast > ema_mid > ema_slow  # EMA20 > EMA50 > EMA200
    bearish_stack = ema_fast < ema_mid < ema_slow  # EMA20 < EMA50 < EMA200

    # ── Condition 2: 30-Period Range Breakout ─────────────────────────────────
    range_high, range_low = calculate_range_extremes(highs, lows, BREAKOUT_PERIOD)

    if range_high != range_high or range_low != range_low:  # NaN check
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "Range High/Low NaN")

    broke_above = price > range_high  # Close breaks above 30-period High
    broke_below = price < range_low   # Close breaks below 30-period Low

    # ── Condition 3: Volume Spike ─────────────────────────────────────────────
    # SMA20 of prior bars (exclude current bar for cleaner signal)
    vol_sma20 = calculate_sma_scalar(volumes[:-1], 20)
    current_vol = volumes[-1]

    if vol_sma20 != vol_sma20 or vol_sma20 == 0:  # NaN or zero
        volume_spike = False
        volume_ratio = float("nan")
    else:
        volume_ratio = current_vol / vol_sma20
        volume_spike = volume_ratio >= VOLUME_MULT   # Volume > 1.5 × SMA20

    # ── Condition 4: Expanding ATR (ATR14 > ATR_SMA50) ───────────────────────
    atr_series     = calculate_atr_series(highs, lows, closes, ATR_PERIOD)
    atr_sma_series = calculate_sma_of_series(atr_series, ATR_SMA_PERIOD)

    current_atr     = atr_series[-1]
    current_atr_sma = atr_sma_series[-1]

    if current_atr != current_atr or current_atr_sma != current_atr_sma:
        expanding_atr = False
        atr_expansion = float("nan")
    else:
        expanding_atr = current_atr > current_atr_sma   # ATR14 > ATR_SMA50
        atr_expansion = current_atr / current_atr_sma   # ratio > 1.0 = expanding

    # ── Stop-Loss / Take-Profit Distances ─────────────────────────────────────
    stop_loss_dist   = current_atr * ATR_SL_MULT if current_atr == current_atr else None
    take_profit_dist = current_atr * ATR_TP_MULT if current_atr == current_atr else None

    # ── Meta dict (always included for transparency) ──────────────────────────
    meta = {
        "price":         price,
        "ema20":         round(ema_fast, 4),
        "ema50":         round(ema_mid, 4),
        "ema200":        round(ema_slow, 4),
        "high_30":       round(range_high, 4),
        "low_30":        round(range_low, 4),
        "volume":        round(current_vol, 4),
        "volume_sma20":  round(vol_sma20, 4)       if vol_sma20 == vol_sma20       else None,
        "volume_ratio":  round(volume_ratio, 3)     if volume_ratio == volume_ratio else None,
        "atr":           round(current_atr, 4)      if current_atr == current_atr   else None,
        "atr_sma50":     round(current_atr_sma, 4)  if current_atr_sma == current_atr_sma else None,
        "atr_expansion": round(atr_expansion, 3)    if atr_expansion == atr_expansion else None,
        "candle":        candle_start.isoformat(),
        "timeframe":     timeframe,
        "conditions": {
            "ema_stack":      bullish_stack or bearish_stack,
            "range_breakout": broke_above or broke_below,
            "volume_spike":   volume_spike,
            "expanding_atr":  expanding_atr,
        },
    }

    if stop_loss_dist is not None:
        meta["sl_distance"] = round(stop_loss_dist, 4)
        meta["tp_distance"] = round(take_profit_dist, 4)
        meta["risk_pct"]    = RISK_PCT

    # ── Signal Decision ───────────────────────────────────────────────────────
    # ALL 4 conditions must be met for a signal

    # LONG: bullish 3-EMA stack + range breakout above + volume spike + expanding ATR
    if bullish_stack and broke_above and volume_spike and expanding_atr:
        breakout_pct = (price - range_high) / range_high * 100

        # Confidence scoring (base 0.55, four contributing factors):
        # +0.10  EMA separation — tighter EMA stack = lower conf, wide stack = high conf
        # +0.10  Volume ratio above threshold (capped boost)
        # +0.10  ATR expansion ratio (momentum intensity)
        # +0.05  Breakout magnitude (scaled, capped)
        ema_fast_mid_sep = (ema_fast - ema_mid) / ema_mid * 100   # EMA20 vs EMA50
        ema_mid_slow_sep = (ema_mid - ema_slow) / ema_slow * 100  # EMA50 vs EMA200

        conf = 0.55
        conf += min(ema_fast_mid_sep * 0.3 + ema_mid_slow_sep * 0.2, 0.10)
        conf += min((volume_ratio - VOLUME_MULT) * 0.05 + 0.05, 0.10)  # bonus above threshold
        conf += min((atr_expansion - 1.0) * 0.10 + 0.05, 0.10)
        conf += min(breakout_pct * 0.5, 0.05)
        conf = round(min(conf, 0.97), 2)

        sl_price = round(price - stop_loss_dist,  4) if stop_loss_dist  else None
        tp_price = round(price + take_profit_dist, 4) if take_profit_dist else None

        meta.update({
            "breakout_pct": round(breakout_pct, 3),
            "sl_price":     sl_price,
            "tp_price":     tp_price,
        })

        log.info(
            "BUY signal %s | price=%.2f ema20=%.2f ema50=%.2f ema200=%.2f "
            "high_30=%.2f vol_ratio=%.2f atr=%.2f atr_sma50=%.2f conf=%.2f",
            coin, price, ema_fast, ema_mid, ema_slow,
            range_high, volume_ratio, current_atr, current_atr_sma, conf,
        )
        return signal_envelope(
            STRATEGY, coin, "BUY", conf,
            f"3-EMA stack (EMA20>EMA50>EMA200) & breakout {breakout_pct:+.2f}% "
            f"above 30-period High | vol_ratio={volume_ratio:.2f} | atr_exp={atr_expansion:.2f}",
            meta,
        )

    # SHORT: bearish 3-EMA stack + range breakdown below + volume spike + expanding ATR
    if bearish_stack and broke_below and volume_spike and expanding_atr:
        breakdown_pct = (range_low - price) / range_low * 100

        ema_fast_mid_sep = (ema_mid - ema_fast) / ema_mid * 100   # EMA50 vs EMA20
        ema_mid_slow_sep = (ema_slow - ema_mid) / ema_slow * 100  # EMA200 vs EMA50

        conf = 0.55
        conf += min(ema_fast_mid_sep * 0.3 + ema_mid_slow_sep * 0.2, 0.10)
        conf += min((volume_ratio - VOLUME_MULT) * 0.05 + 0.05, 0.10)
        conf += min((atr_expansion - 1.0) * 0.10 + 0.05, 0.10)
        conf += min(breakdown_pct * 0.5, 0.05)
        conf = round(min(conf, 0.97), 2)

        sl_price = round(price + stop_loss_dist,  4) if stop_loss_dist  else None
        tp_price = round(price - take_profit_dist, 4) if take_profit_dist else None

        meta.update({
            "breakdown_pct": round(breakdown_pct, 3),
            "sl_price":      sl_price,
            "tp_price":      tp_price,
        })

        log.info(
            "SELL signal %s | price=%.2f ema20=%.2f ema50=%.2f ema200=%.2f "
            "low_30=%.2f vol_ratio=%.2f atr=%.2f atr_sma50=%.2f conf=%.2f",
            coin, price, ema_fast, ema_mid, ema_slow,
            range_low, volume_ratio, current_atr, current_atr_sma, conf,
        )
        return signal_envelope(
            STRATEGY, coin, "SELL", conf,
            f"3-EMA stack (EMA20<EMA50<EMA200) & breakdown {breakdown_pct:+.2f}% "
            f"below 30-period Low | vol_ratio={volume_ratio:.2f} | atr_exp={atr_expansion:.2f}",
            meta,
        )

    # HOLD — explain which conditions failed
    reasons = []

    # EMA stack status
    if bullish_stack:
        reasons.append("bullish EMA stack")
    elif bearish_stack:
        reasons.append("bearish EMA stack")
    else:
        reasons.append(f"no EMA stack (EMA20={ema_fast:.2f} EMA50={ema_mid:.2f} EMA200={ema_slow:.2f})")

    # Range breakout
    if not broke_above and not broke_below:
        reasons.append(
            f"no breakout (price={price:.2f} range={range_low:.2f}–{range_high:.2f})"
        )

    # Volume
    if not volume_spike:
        if volume_ratio == volume_ratio:
            reasons.append(f"low volume (ratio={volume_ratio:.2f} < {VOLUME_MULT}×)")
        else:
            reasons.append("volume data unavailable")

    # ATR expansion
    if not expanding_atr:
        if atr_expansion == atr_expansion:
            reasons.append(f"ATR not expanding (ATR={current_atr:.4f} ATR_SMA50={current_atr_sma:.4f})")
        else:
            reasons.append("ATR data unavailable")

    reason_str = " | ".join(reasons) if reasons else "no signal"
    log.debug("HOLD %s: %s", coin, reason_str)

    return signal_envelope(STRATEGY, coin, "HOLD", 0.0, reason_str, meta)


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    """
    Standalone entry point.
    Checks candle gate, analyses all coins, prints JSON signal array.

    Can also be imported by the orchestrator and called directly via analyse().

    Example output:
        {
            "coin": "BTC",
            "action": "BUY",
            "confidence": 0.85,
            "meta": {
                "price": 64000,
                "ema20": 63800,
                "ema50": 63500,
                "ema200": 62000,
                "high_30": 64200,
                "volume_ratio": 1.8,
                "atr": 450,
                "atr_sma50": 380
            }
        }
    """
    act, candle_start = should_act(STRATEGY, CANDLE_MINUTES, timeframe=TIMEFRAME)
    if not act:
        log.debug("Candle gate: %s already acted this %s candle", STRATEGY, TIMEFRAME)
        print(json.dumps([{
            "strategy": STRATEGY,
            "action":   "HOLD",
            "reason":   f"candle not closed yet ({TIMEFRAME})",
        }]))
        return

    log.info("Running %s | timeframe=%s | coins=%s", STRATEGY, TIMEFRAME, COINS)
    log.info(
        "Config: EMA%d/EMA%d/EMA%d | Breakout%d | VolMult=%.1f× | ATR%d/SMA%d",
        EMA_FAST, EMA_MID, EMA_SLOW, BREAKOUT_PERIOD, VOLUME_MULT,
        ATR_PERIOD, ATR_SMA_PERIOD,
    )

    conn = get_conn()
    signals = [analyse(coin, conn, candle_start, timeframe=TIMEFRAME) for coin in COINS]
    conn.close()

    mark_acted(STRATEGY, candle_start)
    print(json.dumps(signals, indent=2))


if __name__ == "__main__":
    main()


# -- Strategy metadata class (used by strategy_registry.py) -----------------
import sys as _sys
_sys.path.insert(0, r"D:\dev\trading")
from strategy_base import BaseStrategy as _BaseStrategy


class MomentumAccelerationStrategy(_BaseStrategy):
    """Momentum Acceleration � metadata wrapper."""

    name = "Momentum Acceleration"
    description = (
        "Breakout/continuation strategy that fires only when all four momentum "
        "signals align: EMA stack, range breakout, volume spike, and expanding "
        "ATR. Designed to catch explosive directional moves on 1H or 4H candles."
    )
    type = "swing"
    timeframes = ["1h", "4h"]
    core_logic = {
        "long": [
            "EMA20 > EMA50 > EMA200 � strong 3-EMA uptrend alignment",
            "Close > 30-period High � breakout above recent range",
            "Volume > 1.5� SMA20(volume) � volume spike confirms participation",
            "ATR(14) > ATR_SMA50 � expanding volatility confirms momentum",
        ],
        "short": [
            "EMA20 < EMA50 < EMA200 � strong 3-EMA downtrend alignment",
            "Close < 30-period Low � breakdown below recent range",
            "Volume > 1.5� SMA20(volume) � volume spike confirms participation",
            "ATR(14) > ATR_SMA50 � expanding volatility confirms momentum",
        ],
        "filters": [
            "All 4 conditions must be true simultaneously (strict AND logic)",
            "ATR-based stop loss (1.5� ATR14) and take profit (3� ATR14)",
        ],
    }

    def signals(self):  # pragma: no cover
        raise NotImplementedError("Run this strategy as a script or via its main() function.")

# ── Strategy metadata class (used by strategy_registry.py) ─────────────────────────────────────
import sys as _sys
_sys.path.insert(0, r"D:\dev\trading")
from strategy_base import BaseStrategy as _BaseStrategy


class MomentumAccelerationStrategy(_BaseStrategy):
    """Momentum Acceleration - metadata wrapper."""

    name = "Momentum Acceleration"
    description = (
        "Breakout/continuation strategy that fires only when all four momentum "
        "signals align: EMA stack, range breakout, volume spike, and expanding "
        "ATR. Designed to catch explosive directional moves on 1H or 4H candles."
    )
    type = "swing"
    timeframes = ["1h", "4h"]
    core_logic = {
        "long": [
            "EMA20 > EMA50 > EMA200 - strong 3-EMA uptrend alignment",
            "Close > 30-period High - breakout above recent range",
            "Volume > 1.5x SMA20(volume) - volume spike confirms participation",
            "ATR(14) > ATR_SMA50 - expanding volatility confirms momentum",
        ],
        "short": [
            "EMA20 < EMA50 < EMA200 - strong 3-EMA downtrend alignment",
            "Close < 30-period Low - breakdown below recent range",
            "Volume > 1.5x SMA20(volume) - volume spike confirms participation",
            "ATR(14) > ATR_SMA50 - expanding volatility confirms momentum",
        ],
        "filters": [
            "All 4 conditions must be true simultaneously (strict AND logic)",
            "ATR-based stop loss (1.5x ATR14) and take profit (3x ATR14)",
        ],
    }

    def signals(self):  # pragma: no cover
        raise NotImplementedError("Run this strategy as a script or via its main() function.")
