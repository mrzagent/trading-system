#!/usr/bin/env python3
"""
strategy_mean_reversion.py â Mean Reversion Strategy
Timeframe : 1H / 4H candles (configurable via TIMEFRAME env var)
Type      : Counter-trend / mean reversion (low-ADX ranging markets)

Objective:
    Exploit short-term overextensions during ranging (low-volatility, sideways)
    markets. Enter when price stretches to a Bollinger Band extreme and RSI(2)
    confirms exhaustion; exit when price reverts to the Bollinger Band middle
    line (20-period SMA), or at 2R take-profit.

Long Entry Conditions (ALL must be true):
    1. Price touches or closes below the Lower Bollinger Band (20, 2)
    2. RSI(2) < RSI2_OVERSOLD  (default: 10)  â extreme short-term exhaustion

Short Entry Conditions (ALL must be true):
    1. Price touches or closes above the Upper Bollinger Band (20, 2)
    2. RSI(2) > RSI2_OVERBOUGHT (default: 90) â extreme short-term exhaustion

Market Filter (MUST be true for any signal):
    - ADX(14) < ADX_MAX_THRESHOLD (default: 20) â confirms ranging / low-trend market

Exit / Risk Management:
    - Take Profit (primary)  : Price reaches the Bollinger Band middle line (20-SMA)
    - Take Profit (secondary): 2x Risk-distance (2R) â whichever is hit first
    - Stop Loss              : ATR-based (default 1.5x ATR14 beyond the touched band)
    - Position size          : risk RISK_PCT of portfolio per trade

Confidence Scoring:
    - Base 0.55 for meeting all core conditions
    - +0.15  RSI2 deeply oversold/overbought (RSI2 < 5 for long, > 95 for short)
    - +0.10  ADX very low (< 15) â strong ranging confirmation
    - +0.10  Price significantly beyond the band (> 0.5% outside)
    - +0.05  Band width is narrow (low volatility, tight range)
    Max cap: 0.97

Configuration via environment variables:
    TIMEFRAME             : "1h" | "4h" (default: "1h")
    BB_PERIOD             : Bollinger Band SMA period (default: 20)
    BB_STD_DEV            : Bollinger Band standard deviation multiplier (default: 2.0)
    RSI2_PERIOD           : RSI period â intentionally fast (default: 2)
    RSI2_OVERSOLD         : RSI2 threshold for longs (default: 10)
    RSI2_OVERBOUGHT       : RSI2 threshold for shorts (default: 90)
    ADX_PERIOD            : ADX calculation period (default: 14)
    ADX_MAX_THRESHOLD     : Maximum ADX to allow signals (default: 20)
    RISK_PCT              : % of portfolio to risk per trade (default: 1.0)
    ATR_PERIOD            : ATR lookback period (default: 14)
    ATR_SL_MULT           : ATR multiplier for stop loss (default: 1.5)
"""

import json
import logging
import math
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, r"D:\dev\trading")
from db import get_conn, fetch_recent, COINS, signal_envelope
from candle_gate import should_act, mark_acted

# âââ Logging ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s â %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("mean_reversion")

# âââ Strategy Identity ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
STRATEGY = "mean_reversion"

# âââ Configuration (from env vars with sensible defaults) âââââââââââââââââââââ
TIMEFRAME           = os.getenv("TIMEFRAME", "1h")              # candle timeframe
BB_PERIOD           = int(os.getenv("BB_PERIOD", "20"))         # Bollinger Band SMA period
BB_STD_DEV          = float(os.getenv("BB_STD_DEV", "2.0"))     # BB standard deviation multiplier
RSI2_PERIOD         = int(os.getenv("RSI2_PERIOD", "2"))        # RSI period (intentionally 2)
RSI2_OVERSOLD       = float(os.getenv("RSI2_OVERSOLD", "10"))   # RSI2 threshold for long entry
RSI2_OVERBOUGHT     = float(os.getenv("RSI2_OVERBOUGHT", "90")) # RSI2 threshold for short entry
ADX_PERIOD          = int(os.getenv("ADX_PERIOD", "14"))        # ADX smoothing period
ADX_MAX_THRESHOLD   = float(os.getenv("ADX_MAX_THRESHOLD", "20"))  # max ADX (ranging filter)
RISK_PCT            = float(os.getenv("RISK_PCT", "1.0"))       # % portfolio risked per trade
ATR_PERIOD          = int(os.getenv("ATR_PERIOD", "14"))        # ATR lookback
ATR_SL_MULT         = float(os.getenv("ATR_SL_MULT", "1.5"))   # stop-loss ATR multiplier

# Candle period in minutes
_TF_MINUTES = {"4h": 240, "1h": 60, "daily": 1440}
CANDLE_MINUTES = _TF_MINUTES.get(TIMEFRAME, 60)

# Minimum rows needed: BB_PERIOD (20) or ADX warmup (~28) + buffer
MIN_ROWS = max(BB_PERIOD, ATR_PERIOD, ADX_PERIOD * 2) + 10


# âââ Indicator Calculations ââââââââââââââââââââââââââââââââââââââââââââââââââââ

def calculate_bollinger_bands(
    closes: list[float], period: int, num_std: float
) -> tuple[float, float, float]:
    """
    Compute the current Bollinger Bands.

    Parameters
    ----------
    closes   : price series (oldest â newest)
    period   : SMA period (e.g. 20)
    num_std  : standard deviation multiplier (e.g. 2.0)

    Returns
    -------
    (bb_lower, bb_middle, bb_upper)  â values for the LAST bar
    """
    if len(closes) < period:
        nan = float("nan")
        return nan, nan, nan

    window = closes[-period:]
    mean   = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    std_dev  = math.sqrt(variance)

    bb_middle = mean
    bb_upper  = mean + num_std * std_dev
    bb_lower  = mean - num_std * std_dev
    return bb_lower, bb_middle, bb_upper


def calculate_rsi(closes: list[float], period: int) -> float:
    """
    Relative Strength Index using Wilder's smoothed average.

    With period=2 this is an extremely fast oscillator â useful for detecting
    short-term exhaustion within a mean-reversion context.

    Returns RSI value (0â100) or NaN if insufficient data.
    """
    if len(closes) < period + 1:
        return float("nan")

    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    if len(gains) < period:
        return float("nan")

    # Seed: simple average of first `period` bars
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder's smoothing for the rest
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs  = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return round(rsi, 2)


def calculate_atr(
    highs: list[float], lows: list[float], closes: list[float], period: int
) -> float:
    """
    Average True Range (simple smoothing).
    TR = max(highâlow, |highâprev_close|, |lowâprev_close|)
    """
    if len(closes) < period + 1:
        return float("nan")

    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    if len(trs) < period:
        return float("nan")

    return sum(trs[-period:]) / period


def calculate_adx(
    highs: list[float], lows: list[float], closes: list[float], period: int
) -> float:
    """
    Average Directional Index (Wilder's method).

    Low ADX (< 20) = ranging / sideways market â ideal for mean reversion.
    High ADX (> 25) = trending market â avoid mean reversion trades.

    Returns ADX value (0â100); NaN if insufficient data.
    """
    if len(closes) < period * 2 + 1:
        return float("nan")

    plus_dm_list  = []
    minus_dm_list = []
    tr_list       = []

    for i in range(1, len(closes)):
        up_move   = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]

        plus_dm  = up_move   if (up_move > down_move   and up_move > 0)   else 0.0
        minus_dm = down_move if (down_move > up_move   and down_move > 0) else 0.0

        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)
        tr_list.append(tr)

    if len(tr_list) < period:
        return float("nan")

    # Wilder's initial smoothed values
    smooth_tr    = sum(tr_list[:period])
    smooth_plus  = sum(plus_dm_list[:period])
    smooth_minus = sum(minus_dm_list[:period])

    dx_list = []
    for i in range(period, len(tr_list)):
        smooth_tr    = smooth_tr    - (smooth_tr    / period) + tr_list[i]
        smooth_plus  = smooth_plus  - (smooth_plus  / period) + plus_dm_list[i]
        smooth_minus = smooth_minus - (smooth_minus / period) + minus_dm_list[i]

        if smooth_tr == 0:
            continue

        plus_di  = 100 * smooth_plus  / smooth_tr
        minus_di = 100 * smooth_minus / smooth_tr
        di_sum   = plus_di + minus_di

        if di_sum == 0:
            continue

        dx = 100 * abs(plus_di - minus_di) / di_sum
        dx_list.append(dx)

    if not dx_list:
        return float("nan")

    return round(sum(dx_list[-period:]) / min(len(dx_list), period), 2)


# âââ Signal Analysis âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def analyse(coin: str, conn, candle_start: datetime, timeframe: str = "1h") -> dict:
    """
    Run mean-reversion analysis for a single coin.

    Logic summary
    -------------
    1. Fetch recent OHLCV rows.
    2. Compute BB(20,2), RSI(2), ADX(14), ATR(14).
    3. Gate on ADX < ADX_MAX_THRESHOLD (ranging market filter).
    4. BUY  if price <= BB lower  AND RSI2 < RSI2_OVERSOLD.
    5. SELL if price >= BB upper  AND RSI2 > RSI2_OVERBOUGHT.
    6. Take-profit targets: BB middle (primary) or 2R distance (secondary).
    7. Confidence scoring based on depth of signal.

    Returns a standard signal_envelope dict.
    """
    rows = fetch_recent(conn, coin, limit=MIN_ROWS, timeframe=timeframe)

    if len(rows) < MIN_ROWS:
        log.warning("%s: insufficient data (%d rows, need %d)", coin, len(rows), MIN_ROWS)
        return signal_envelope(
            STRATEGY, coin, "HOLD", 0.0,
            f"insufficient data ({len(rows)}/{MIN_ROWS} rows)",
        )

    # Extract OHLCV series (oldest â newest)
    # Support both naming conventions: high/low and high_price/low_price
    # Handle NULL values by falling back to price
    def get_high(r):
        h = r.get("high") or r.get("high_price")
        return float(h) if h is not None else float(r["price"])
    
    def get_low(r):
        l = r.get("low") or r.get("low_price")
        return float(l) if l is not None else float(r["price"])
    
    closes  = [float(r["price"]) for r in rows]
    highs   = [get_high(r) for r in rows]
    lows    = [get_low(r)  for r in rows]

    price = closes[-1]

    # ââ Bollinger Bands âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    bb_lower, bb_middle, bb_upper = calculate_bollinger_bands(closes, BB_PERIOD, BB_STD_DEV)

    if any(v != v for v in (bb_lower, bb_middle, bb_upper)):  # NaN check
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "BB NaN â insufficient history")

    # ââ RSI(2) ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    rsi_2 = calculate_rsi(closes, RSI2_PERIOD)

    if rsi_2 != rsi_2:  # NaN
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "RSI(2) NaN â insufficient history")

    # ââ ADX(14) â Ranging Market Filter ââââââââââââââââââââââââââââââââââââââ
    adx = calculate_adx(highs, lows, closes, ADX_PERIOD)

    if adx != adx:  # NaN
        log.debug("%s: ADX NaN â skipping (not enough history for ADX)", coin)
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "ADX NaN â insufficient history")

    market_is_ranging = adx < ADX_MAX_THRESHOLD

    # ââ ATR (stop-loss sizing) ââââââââââââââââââââââââââââââââââââââââââââââââ
    atr = calculate_atr(highs, lows, closes, ATR_PERIOD)
    sl_distance = atr * ATR_SL_MULT if atr == atr else None  # NaN-safe

    # ââ Band metrics (used for confidence and meta) âââââââââââââââââââââââââââ
    band_width       = bb_upper - bb_lower
    band_width_pct   = band_width / bb_middle * 100 if bb_middle else 0.0
    # How far price is outside the band (0 if inside)
    lower_penetration_pct = max((bb_lower - price) / bb_lower * 100, 0.0)
    upper_penetration_pct = max((price - bb_upper) / bb_upper * 100, 0.0)

    # ââ Entry conditions ââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    touches_lower = price <= bb_lower   # at or below lower band
    touches_upper = price >= bb_upper   # at or above upper band
    rsi_oversold  = rsi_2 < RSI2_OVERSOLD
    rsi_overbought = rsi_2 > RSI2_OVERBOUGHT

    # ââ Meta dict (always included for transparency) ââââââââââââââââââââââââââ
    meta = {
        "price":          price,
        "bb_lower":       round(bb_lower,  4),
        "bb_middle":      round(bb_middle, 4),
        "bb_upper":       round(bb_upper,  4),
        "bb_width_pct":   round(band_width_pct, 3),
        "rsi_2":          rsi_2,
        "adx":            round(adx, 2),
        "atr":            round(atr, 4) if atr == atr else None,
        "candle":         candle_start.isoformat(),
        "timeframe":      timeframe,
        "market_ranging": market_is_ranging,
        "filters": {
            "adx_max":          ADX_MAX_THRESHOLD,
            "adx_ok":           market_is_ranging,
            "rsi2_oversold_thr":  RSI2_OVERSOLD,
            "rsi2_overbought_thr": RSI2_OVERBOUGHT,
        },
    }

    # Risk / take-profit levels added inline after we know direction
    if sl_distance is not None:
        meta["sl_distance"] = round(sl_distance, 4)
        meta["risk_pct"]    = RISK_PCT

    # ââ Market filter gate ââââââââââââââââââââââââââââââââââââââââââââââââââââ
    if not market_is_ranging:
        reason = f"trending market â ADX={adx:.1f} >= {ADX_MAX_THRESHOLD} (mean reversion disabled)"
        log.debug("HOLD %s: %s", coin, reason)
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, reason, meta)

    # ââ LONG signal âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    if touches_lower and rsi_oversold:
        # Take-profit targets
        tp_middle = bb_middle                                        # primary: revert to mean
        tp_2r     = price + (sl_distance * 2) if sl_distance else None  # secondary: 2R

        # Confidence scoring
        conf = 0.55  # base: all core conditions met
        conf += 0.15 if rsi_2 < 5                          else 0.0  # extreme RSI2
        conf += 0.10 if adx < 15                           else 0.0  # very low ADX (tight range)
        conf += 0.10 if lower_penetration_pct > 0.5        else 0.0  # price well below band
        conf += 0.05 if band_width_pct < 4.0               else 0.0  # narrow bands = tight range
        conf  = round(min(conf, 0.97), 2)

        meta.update({
            "penetration_pct": round(lower_penetration_pct, 3),
            "tp_middle":       round(tp_middle, 4),
            "tp_2r":           round(tp_2r, 4) if tp_2r else None,
            "sl_price":        round(price - sl_distance, 4) if sl_distance else None,
        })

        log.info(
            "BUY signal %s | price=%.2f bb_lower=%.2f bb_mid=%.2f rsi2=%.1f adx=%.1f conf=%.2f",
            coin, price, bb_lower, bb_middle, rsi_2, adx, conf,
        )
        return signal_envelope(
            STRATEGY, coin, "BUY", conf,
            f"price {lower_penetration_pct:.2f}% below BB lower | RSI2={rsi_2:.1f} oversold | ADX={adx:.1f}",
            meta,
        )

    # ââ SHORT signal ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    if touches_upper and rsi_overbought:
        tp_middle = bb_middle
        tp_2r     = price - (sl_distance * 2) if sl_distance else None

        # Confidence scoring
        conf = 0.55
        conf += 0.15 if rsi_2 > 95                         else 0.0  # extreme RSI2
        conf += 0.10 if adx < 15                           else 0.0  # very low ADX
        conf += 0.10 if upper_penetration_pct > 0.5        else 0.0  # price well above band
        conf += 0.05 if band_width_pct < 4.0               else 0.0  # narrow bands
        conf  = round(min(conf, 0.97), 2)

        meta.update({
            "penetration_pct": round(upper_penetration_pct, 3),
            "tp_middle":       round(tp_middle, 4),
            "tp_2r":           round(tp_2r, 4) if tp_2r else None,
            "sl_price":        round(price + sl_distance, 4) if sl_distance else None,
        })

        log.info(
            "SELL signal %s | price=%.2f bb_upper=%.2f bb_mid=%.2f rsi2=%.1f adx=%.1f conf=%.2f",
            coin, price, bb_upper, bb_middle, rsi_2, adx, conf,
        )
        return signal_envelope(
            STRATEGY, coin, "SELL", conf,
            f"price {upper_penetration_pct:.2f}% above BB upper | RSI2={rsi_2:.1f} overbought | ADX={adx:.1f}",
            meta,
        )

    # ââ HOLD â explain the dominant reason âââââââââââââââââââââââââââââââââââ
    reasons = []
    if not touches_lower and not touches_upper:
        reasons.append(f"price {price:.2f} inside BB [{bb_lower:.2f}â{bb_upper:.2f}]")
    elif touches_lower and not rsi_oversold:
        reasons.append(f"price at lower BB but RSI2={rsi_2:.1f} not oversold (need < {RSI2_OVERSOLD})")
    elif touches_upper and not rsi_overbought:
        reasons.append(f"price at upper BB but RSI2={rsi_2:.1f} not overbought (need > {RSI2_OVERBOUGHT})")

    reason_str = " | ".join(reasons) if reasons else "no signal"
    log.debug("HOLD %s: %s", coin, reason_str)

    return signal_envelope(STRATEGY, coin, "HOLD", 0.0, reason_str, meta)


# âââ Entry Point ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def main():
    """
    Standalone entry point.
    Checks candle gate, analyses all coins, prints JSON signal array.

    Can also be imported by the orchestrator and called as analyse(coin, conn, candle_start).

    Example output:
        {"coin": "BTC", "action": "BUY", "confidence": 0.85,
         "meta": {"price": 64000, "bb_lower": 63500, "bb_middle": 64000,
                  "bb_upper": 64500, "rsi_2": 8.5, "adx": 15}}
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
        "Config: BB(%d, %.1f) | RSI2<%s long | RSI2>%s short | ADX<%s ranging",
        BB_PERIOD, BB_STD_DEV, RSI2_OVERSOLD, RSI2_OVERBOUGHT, ADX_MAX_THRESHOLD,
    )

    conn    = get_conn()
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


class MeanReversionStrategy(_BaseStrategy):
    """Mean Reversion ï¿½ metadata wrapper."""

    name = "Mean Reversion"
    description = (
        "Counter-trend strategy that exploits short-term price overextensions "
        "in low-ADX ranging markets. Enters at Bollinger Band extremes when "
        "RSI(2) confirms exhaustion; exits at the 20-SMA midline or 2R take-profit."
    )
    type = "swing"
    timeframes = ["1h", "4h"]
    core_logic = {
        "long": [
            "Price touches or closes below Lower Bollinger Band (20, 2s)",
            "RSI(2) < 10 ï¿½ extreme short-term oversold exhaustion",
            "ADX(14) < 20 ï¿½ confirms ranging / low-trend market",
        ],
        "short": [
            "Price touches or closes above Upper Bollinger Band (20, 2s)",
            "RSI(2) > 90 ï¿½ extreme short-term overbought exhaustion",
            "ADX(14) < 20 ï¿½ confirms ranging / low-trend market",
        ],
        "filters": [
            "Confidence boosted when RSI(2) < 5 or > 95 (deeper exhaustion)",
            "Confidence boosted when ADX < 15 (stronger ranging confirmation)",
            "ATR-based stop loss (1.5ï¿½ ATR14 beyond touched band)",
        ],
    }

    def signals(self):  # pragma: no cover
        raise NotImplementedError("Run this strategy as a script or via its main() function.")


# ââ Strategy metadata class (used by strategy_registry.py) âââââââââââââââââââââââââââââââââââââ
import sys as _sys
_sys.path.insert(0, r"D:\dev\trading")
from strategy_base import BaseStrategy as _BaseStrategy


class MeanReversionStrategy(_BaseStrategy):
    """Mean Reversion - metadata wrapper."""

    name = "Mean Reversion"
    description = (
        "Counter-trend strategy that exploits short-term price overextensions "
        "in low-ADX ranging markets. Enters at Bollinger Band extremes when "
        "RSI(2) confirms exhaustion; exits at the 20-SMA midline or 2R take-profit."
    )
    type = "swing"
    timeframes = ["1h", "4h"]
    core_logic = {
        "long": [
            "Price touches or closes below Lower Bollinger Band (20, 2-sigma)",
            "RSI(2) < 10 - extreme short-term oversold exhaustion",
            "ADX(14) < 20 - confirms ranging / low-trend market",
        ],
        "short": [
            "Price touches or closes above Upper Bollinger Band (20, 2-sigma)",
            "RSI(2) > 90 - extreme short-term overbought exhaustion",
            "ADX(14) < 20 - confirms ranging / low-trend market",
        ],
        "filters": [
            "Confidence boosted when RSI(2) < 5 or > 95 (deeper exhaustion)",
            "Confidence boosted when ADX < 15 (stronger ranging confirmation)",
            "ATR-based stop loss (1.5x ATR14 beyond touched band)",
        ],
    }

    def signals(self):  # pragma: no cover
        raise NotImplementedError("Run this strategy as a script or via its main() function.")
