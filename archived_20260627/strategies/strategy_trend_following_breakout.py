#!/usr/bin/env python3
"""
strategy_trend_following_breakout.py — Trend Following Breakout Swing Strategy
Timeframe : 4H candles (Daily supported via TIMEFRAME env var when table exists)
Type      : Swing trade (low frequency, high R-multiple targets)

Objective:
    Capture large directional trends in BTC, ETH, and SOL.
    Low trade frequency — only fires on genuine trend breakouts.

Long Entry Conditions (ALL must be true):
    1. EMA50 > EMA200  (bullish trend filter)
    2. Close > 20-period Donchian High (breakout confirmation)

Short Entry Conditions (ALL must be true):
    1. EMA50 < EMA200  (bearish trend filter)
    2. Close < 20-period Donchian Low  (breakdown confirmation)

Optional Filters (configurable via env vars):
    - VOLUME_FILTER_ENABLED=true  → Volume > SMA20(volume)
    - ADX_FILTER_ENABLED=true     → ADX(14) > ADX_THRESHOLD (default 20)

Exit / Risk Management:
    - Stop loss : ATR-based (default 2.0× ATR14 from entry)
    - Take profit: ATR-based (default 4.0× ATR14 from entry — 2:1 R-multiple)
    - Position size: risk RISK_PCT of portfolio per trade

Configuration via environment variables:
    TIMEFRAME           : "4h" | "1h" (default: "4h")
    DONCHIAN_PERIOD     : lookback for Donchian channel (default: 20)
    EMA_FAST            : fast EMA period (default: 50)
    EMA_SLOW            : slow EMA period (default: 200)
    ADX_PERIOD          : ADX calculation period (default: 14)
    ADX_THRESHOLD       : minimum ADX for trend strength filter (default: 20)
    VOLUME_FILTER_ENABLED  : "true"/"false" — require volume > SMA20 (default: "false")
    ADX_FILTER_ENABLED     : "true"/"false" — require ADX > threshold (default: "false")
    RISK_PCT            : % of portfolio to risk per trade (default: 1.0)
    ATR_PERIOD          : ATR lookback period (default: 14)
    ATR_SL_MULT         : ATR multiplier for stop loss (default: 2.0)
    ATR_TP_MULT         : ATR multiplier for take profit (default: 4.0)
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
log = logging.getLogger("trend_following_breakout")

# ─── Strategy Identity ────────────────────────────────────────────────────────
STRATEGY = "trend_following_breakout"

# ─── Configuration (from env vars with sensible defaults) ─────────────────────
TIMEFRAME             = os.getenv("TIMEFRAME", "4h")          # candle timeframe
DONCHIAN_PERIOD       = int(os.getenv("DONCHIAN_PERIOD", "20"))   # Donchian channel lookback
EMA_FAST              = int(os.getenv("EMA_FAST", "50"))          # fast EMA (trend check)
EMA_SLOW              = int(os.getenv("EMA_SLOW", "200"))         # slow EMA (trend check)
ADX_PERIOD            = int(os.getenv("ADX_PERIOD", "14"))        # ADX smoothing period
ADX_THRESHOLD         = float(os.getenv("ADX_THRESHOLD", "20"))   # min ADX for filter
VOLUME_FILTER_ENABLED = os.getenv("VOLUME_FILTER_ENABLED", "false").lower() == "true"
ADX_FILTER_ENABLED    = os.getenv("ADX_FILTER_ENABLED", "false").lower() == "true"
RISK_PCT              = float(os.getenv("RISK_PCT", "1.0"))       # % portfolio risked per trade
ATR_PERIOD            = int(os.getenv("ATR_PERIOD", "14"))        # ATR lookback
ATR_SL_MULT           = float(os.getenv("ATR_SL_MULT", "2.0"))   # stop-loss ATR multiplier
ATR_TP_MULT           = float(os.getenv("ATR_TP_MULT", "4.0"))   # take-profit ATR multiplier

# Candle period in minutes (4h = 240, 1h = 60, Daily = 1440)
_TF_MINUTES = {"4h": 240, "1h": 60, "daily": 1440}
CANDLE_MINUTES = _TF_MINUTES.get(TIMEFRAME, 240)

# We need enough rows to compute EMA200 + Donchian20 + ATR14
MIN_ROWS = max(EMA_SLOW, DONCHIAN_PERIOD, ATR_PERIOD) + 10


# ─── Indicator Calculations ────────────────────────────────────────────────────

def calculate_ema(prices: list[float], period: int) -> list[float]:
    """
    Compute Exponential Moving Average series.
    Returns list of same length as prices; early values use SMA as seed.
    """
    if len(prices) < period:
        return [float("nan")] * len(prices)

    ema_values = [float("nan")] * len(prices)
    multiplier = 2.0 / (period + 1)

    # Seed: SMA of first `period` values
    seed = sum(prices[:period]) / period
    ema_values[period - 1] = seed

    for i in range(period, len(prices)):
        ema_values[i] = (prices[i] - ema_values[i - 1]) * multiplier + ema_values[i - 1]

    return ema_values


def calculate_donchian(highs: list[float], lows: list[float], period: int) -> tuple[float, float]:
    """
    Donchian Channel: highest high and lowest low over the last `period` bars
    (excluding the current bar — we compare close against historical extremes).

    Returns (donchian_high, donchian_low).
    """
    lookback_highs = highs[-period - 1 : -1]  # exclude current bar
    lookback_lows  = lows[-period - 1 : -1]
    if not lookback_highs or not lookback_lows:
        return float("nan"), float("nan")
    return max(lookback_highs), min(lookback_lows)


def calculate_atr(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
    """
    Average True Range (ATR) using simple smoothing.
    True Range = max(high-low, abs(high-prev_close), abs(low-prev_close))
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


def calculate_sma(values: list[float], period: int) -> float:
    """Simple moving average of the last `period` values."""
    if len(values) < period:
        return float("nan")
    return sum(values[-period:]) / period


def calculate_adx(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
    """
    Average Directional Index (ADX).
    Simplified Wilder's ADX using smoothed DM and TR.
    Returns ADX value (0–100); higher = stronger trend.
    """
    if len(closes) < period * 2 + 1:
        return float("nan")

    plus_dm_list  = []
    minus_dm_list = []
    tr_list       = []

    for i in range(1, len(closes)):
        up_move   = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]

        plus_dm  = up_move   if (up_move > down_move and up_move > 0)   else 0.0
        minus_dm = down_move if (down_move > up_move and down_move > 0) else 0.0

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

    # Initial smoothed values (Wilder's smoothing)
    smooth_tr    = sum(tr_list[:period])
    smooth_plus  = sum(plus_dm_list[:period])
    smooth_minus = sum(minus_dm_list[:period])

    dx_list = []
    for i in range(period, len(tr_list)):
        smooth_tr    = smooth_tr    - (smooth_tr / period)    + tr_list[i]
        smooth_plus  = smooth_plus  - (smooth_plus / period)  + plus_dm_list[i]
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

    return sum(dx_list[-period:]) / min(len(dx_list), period)


# ─── Signal Analysis ───────────────────────────────────────────────────────────

def analyse(coin: str, conn, candle_start: datetime, timeframe: str = "4h") -> dict:
    """
    Run trend-following breakout analysis for a single coin.

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

    # ── EMA Trend Filter ──────────────────────────────────────────────────────
    ema_fast_series = calculate_ema(closes, EMA_FAST)
    ema_slow_series = calculate_ema(closes, EMA_SLOW)

    ema_fast = ema_fast_series[-1]
    ema_slow = ema_slow_series[-1]

    if ema_fast != ema_fast or ema_slow != ema_slow:  # NaN check
        log.warning("%s: EMA calculation returned NaN (not enough history)", coin)
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "EMA NaN — insufficient history")

    bullish_trend = ema_fast > ema_slow   # EMA50 > EMA200
    bearish_trend = ema_fast < ema_slow   # EMA50 < EMA200

    # ── Donchian Channel ──────────────────────────────────────────────────────
    donchian_high, donchian_low = calculate_donchian(highs, lows, DONCHIAN_PERIOD)

    if donchian_high != donchian_high or donchian_low != donchian_low:  # NaN
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "Donchian NaN")

    # Breakout conditions
    broke_above = price > donchian_high   # Close above 20-period Donchian High
    broke_below = price < donchian_low    # Close below 20-period Donchian Low

    # ── ATR (for stop-loss / take-profit sizing) ──────────────────────────────
    atr = calculate_atr(highs, lows, closes, ATR_PERIOD)
    stop_loss_dist  = atr * ATR_SL_MULT if atr == atr else None  # NaN-safe
    take_profit_dist = atr * ATR_TP_MULT if atr == atr else None

    # ── Optional Volume Filter ────────────────────────────────────────────────
    volume_ok = True
    vol_sma20  = calculate_sma(volumes[:-1], 20)  # SMA of prior 20 bars
    current_vol = volumes[-1]

    if VOLUME_FILTER_ENABLED:
        if vol_sma20 != vol_sma20 or vol_sma20 == 0:
            volume_ok = False
            log.debug("%s: volume SMA20 unavailable — filter skipped", coin)
        else:
            volume_ok = current_vol > vol_sma20

    # ── Optional ADX Filter ───────────────────────────────────────────────────
    adx_ok = True
    adx = calculate_adx(highs, lows, closes, ADX_PERIOD)

    if ADX_FILTER_ENABLED:
        if adx != adx:  # NaN
            adx_ok = False
            log.debug("%s: ADX unavailable — filter skipped", coin)
        else:
            adx_ok = adx >= ADX_THRESHOLD

    # ── Meta dict (always included for transparency) ──────────────────────────
    meta = {
        "price":         price,
        "ema50":         round(ema_fast, 4),
        "ema200":        round(ema_slow, 4),
        "donchian_high": round(donchian_high, 4),
        "donchian_low":  round(donchian_low, 4),
        "volume":        round(current_vol, 4),
        "volume_sma20":  round(vol_sma20, 4) if vol_sma20 == vol_sma20 else None,
        "adx":           round(adx, 2)        if adx == adx           else None,
        "atr":           round(atr, 4)        if atr == atr           else None,
        "candle":        candle_start.isoformat(),
        "timeframe":     timeframe,
        "filters": {
            "volume_filter_enabled": VOLUME_FILTER_ENABLED,
            "volume_ok":             volume_ok,
            "adx_filter_enabled":    ADX_FILTER_ENABLED,
            "adx_ok":                adx_ok,
        },
    }

    # Risk management: stop-loss and take-profit levels
    if stop_loss_dist is not None:
        meta["sl_distance"]  = round(stop_loss_dist, 4)
        meta["tp_distance"]  = round(take_profit_dist, 4)
        meta["risk_pct"]     = RISK_PCT

    # ── Signal Decision ───────────────────────────────────────────────────────

    # LONG: bullish trend + breakout above Donchian High (+ optional filters)
    if bullish_trend and broke_above and volume_ok and adx_ok:
        breakout_pct = (price - donchian_high) / donchian_high * 100

        # Confidence scoring:
        # Base 0.60 for meeting core conditions
        # +0.10 if volume filter confirms (even if filter is off)
        # +0.10 if ADX confirms trend strength (even if filter is off)
        # +0.05 scaled by EMA separation (stronger trend = higher conf)
        # +0.05 scaled by breakout magnitude (capped)
        ema_separation_pct = (ema_fast - ema_slow) / ema_slow * 100
        conf = 0.60
        conf += 0.10 if (vol_sma20 == vol_sma20 and current_vol > vol_sma20) else 0.0
        conf += 0.10 if (adx == adx and adx >= ADX_THRESHOLD)               else 0.0
        conf += min(ema_separation_pct * 0.5, 0.05)
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
            "BUY signal %s | price=%.2f ema50=%.2f ema200=%.2f don_high=%.2f conf=%.2f",
            coin, price, ema_fast, ema_slow, donchian_high, conf,
        )
        return signal_envelope(
            STRATEGY, coin, "BUY", conf,
            f"EMA50>EMA200 & close {breakout_pct:+.2f}% above Donchian High",
            meta,
        )

    # SHORT: bearish trend + breakdown below Donchian Low (+ optional filters)
    if bearish_trend and broke_below and volume_ok and adx_ok:
        breakdown_pct = (donchian_low - price) / donchian_low * 100

        ema_separation_pct = (ema_slow - ema_fast) / ema_slow * 100
        conf = 0.60
        conf += 0.10 if (vol_sma20 == vol_sma20 and current_vol > vol_sma20) else 0.0
        conf += 0.10 if (adx == adx and adx >= ADX_THRESHOLD)               else 0.0
        conf += min(ema_separation_pct * 0.5, 0.05)
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
            "SELL signal %s | price=%.2f ema50=%.2f ema200=%.2f don_low=%.2f conf=%.2f",
            coin, price, ema_fast, ema_slow, donchian_low, conf,
        )
        return signal_envelope(
            STRATEGY, coin, "SELL", conf,
            f"EMA50<EMA200 & close {breakdown_pct:+.2f}% below Donchian Low",
            meta,
        )

    # HOLD — explain dominant reason
    reasons = []
    if not bullish_trend and not bearish_trend:
        reasons.append("EMAs flat")
    elif bullish_trend and not broke_above:
        reasons.append(f"uptrend but price {price:.2f} below Donchian High {donchian_high:.2f}")
    elif bearish_trend and not broke_below:
        reasons.append(f"downtrend but price {price:.2f} above Donchian Low {donchian_low:.2f}")

    if VOLUME_FILTER_ENABLED and not volume_ok:
        reasons.append(f"low volume ({current_vol:.0f} < SMA20 {vol_sma20:.0f})")
    if ADX_FILTER_ENABLED and not adx_ok:
        reasons.append(f"weak trend ADX={adx:.1f} < {ADX_THRESHOLD}")

    reason_str = " | ".join(reasons) if reasons else "no signal"
    log.debug("HOLD %s: %s", coin, reason_str)

    return signal_envelope(STRATEGY, coin, "HOLD", 0.0, reason_str, meta)


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    """
    Standalone entry point.
    Checks candle gate, analyses all coins, prints JSON signal array.

    Can also be imported by the orchestrator and called directly.
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
        "Config: EMA%d/EMA%d | Donchian%d | ADX_filter=%s | Vol_filter=%s",
        EMA_FAST, EMA_SLOW, DONCHIAN_PERIOD,
        ADX_FILTER_ENABLED, VOLUME_FILTER_ENABLED,
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


class TrendFollowingBreakoutStrategy(_BaseStrategy):
    """Trend Following Breakout � metadata wrapper."""

    name = "Trend Following Breakout"
    description = (
        "Swing strategy that captures large directional trends via Donchian "
        "channel breakouts confirmed by EMA50/EMA200 alignment. Fires on 4-hour "
        "candle closes. Low frequency � targets 2:1 R-multiple per trade."
    )
    type = "swing"
    timeframes = ["4h", "1d"]
    core_logic = {
        "long": [
            "EMA50 > EMA200 (bullish trend filter)",
            "Close > 20-period Donchian High (breakout confirmation)",
        ],
        "short": [
            "EMA50 < EMA200 (bearish trend filter)",
            "Close < 20-period Donchian Low (breakdown confirmation)",
        ],
        "filters": [
            "Optional: Volume > SMA20(volume) (VOLUME_FILTER_ENABLED)",
            "Optional: ADX(14) > 20 for trend strength (ADX_FILTER_ENABLED)",
            "ATR-based stop loss (2� ATR14) and take profit (4� ATR14)",
        ],
    }

    def signals(self):  # pragma: no cover
        raise NotImplementedError("Run this strategy as a script or via its main() function.")

# ── Strategy metadata class (used by strategy_registry.py) ─────────────────────────────────────
import sys as _sys
_sys.path.insert(0, r"D:\dev\trading")
from strategy_base import BaseStrategy as _BaseStrategy


class TrendFollowingBreakoutStrategy(_BaseStrategy):
    """Trend Following Breakout - metadata wrapper."""

    name = "Trend Following Breakout"
    description = (
        "Swing strategy that captures large directional trends via Donchian "
        "channel breakouts confirmed by EMA50/EMA200 alignment. Fires on 4-hour "
        "candle closes. Low frequency - targets 2:1 R-multiple per trade."
    )
    type = "swing"
    timeframes = ["4h", "1d"]
    core_logic = {
        "long": [
            "EMA50 > EMA200 (bullish trend filter)",
            "Close > 20-period Donchian High (breakout confirmation)",
        ],
        "short": [
            "EMA50 < EMA200 (bearish trend filter)",
            "Close < 20-period Donchian Low (breakdown confirmation)",
        ],
        "filters": [
            "Optional: Volume > SMA20(volume) (VOLUME_FILTER_ENABLED)",
            "Optional: ADX(14) > 20 for trend strength (ADX_FILTER_ENABLED)",
            "ATR-based stop loss (2x ATR14) and take profit (4x ATR14)",
        ],
    }

    def signals(self):  # pragma: no cover
        raise NotImplementedError("Run this strategy as a script or via its main() function.")
