#!/usr/bin/env python3
"""
strategy_momentum_scalper.py â Momentum Scalper Strategy
Timeframe : 5M candles (also valid on 15M)
Type      : Scalp trade (trend pullback)

Objective:
    Join established trends on temporary pullbacks to EMA9. Instead of chasing
    breakouts, wait for price to retrace to EMA9 after EMA stack aligns,
    then enter when price resumes in the trend direction.

Long Entry Conditions (ALL must be true):
    1. EMA9 > EMA21 > EMA50    â bullish trend alignment
    2. RSI(14) > 50 (momentum confirmation, not overbought < 70)
    3. Price pulls back to/crosses below EMA9
    4. Price crosses back above EMA9 (resumption signal)
    5. Volume > 2.0 x SMA20(volume) â volume confirms interest

Short Entry Conditions (ALL must be true):
    1. EMA9 < EMA21 < EMA50    â bearish trend alignment
    2. RSI(14) < 50 (momentum confirmation, not oversold > 30)
    3. Price rallies to/crosses above EMA9
    4. Price crosses back below EMA9 (resumption signal)
    5. Volume > 2.0 x SMA20(volume) â volume confirms interest

Exit / Risk Management:
    - Stop loss : below previous swing low (long) / above previous swing high (short)
                  or 1.0 x ATR(14), whichever is tighter
    - Take profit: 2.0R (2x stop distance)
    - Cooldown: 20 bars between trades per coin

Backtest Results (BTC 5min, Jun 2023âJun 2026):
    - Return: -17.44% (vs -57.28% breakout entry)
    - Win Rate: 36.0%
    - Profit Factor: 0.86
    - Max Drawdown: 18.61% (vs 59.75% breakout entry)
    - Total Trades: 1,894
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
log = logging.getLogger("momentum_scalper")

# âââ Strategy Identity ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
STRATEGY       = "momentum_scalper"
CANDLE_MINUTES = 5

# âââ Key Constants ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
COINS          = ["BTC", "ETH", "SOL"]
EMA_FAST       = 9     # EMA9
EMA_MID        = 21    # EMA21
EMA_SLOW       = 50    # EMA50
VOLUME_MULT    = 2.0   # Volume must exceed 2.0 x SMA20(volume)
ATR_PERIOD     = 14    # ATR period for stop-loss calculation
RSI_PERIOD     = 14    # RSI period for momentum confirmation
LOOKBACK_SWING = 10    # Bars to look back for swing high/low

# Pullback Parameters
PULLBACK_MAX_BARS = 10       # Max bars to wait for pullback after stack aligns
MIN_PULLBACK_PCT = 0.05      # Minimum pullback distance to qualify (%)
COOLDOWN_BARS = 20           # Wait 20 bars between trades

# We need enough history for EMA50 + ATR14 + swing lookback + vol SMA20 + RSI14
MIN_ROWS = max(EMA_SLOW, ATR_PERIOD, LOOKBACK_SWING, 20, RSI_PERIOD) + 20  # = 70


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


def calculate_rsi(prices: list[float], period: int = 14) -> list[float]:
    """
    Compute RSI series using Wilder's smoothing.
    Returns list of same length as prices; early values filled with NaN.
    """
    n = len(prices)
    rsi_values = [float("nan")] * n

    if n <= period:
        return rsi_values

    deltas = [prices[i] - prices[i-1] for i in range(1, n)]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]

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


def calculate_atr_series(
    highs: list[float], lows: list[float], closes: list[float], period: int
) -> list[float]:
    """
    Compute ATR series using simple (arithmetic) smoothing.
    True Range = max(high-low, |high-prev_close|, |low-prev_close|)
    Returns list of ATR values same length as closes; early values are NaN.
    """
    n = len(closes)
    atr_series = [float("nan")] * n

    if n < period + 1:
        return atr_series

    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    if len(trs) < period:
        return atr_series

    first_atr = sum(trs[:period]) / period
    atr_series[period] = first_atr

    for i in range(period, len(trs)):
        atr_series[i + 1] = (atr_series[i] * (period - 1) + trs[i]) / period

    return atr_series


def calculate_sma_scalar(values: list[float], period: int) -> float:
    """Simple moving average scalar over the last `period` non-NaN values."""
    filtered = [v for v in values[-period:] if v == v]
    if len(filtered) < period:
        return float("nan")
    return sum(filtered) / period


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

class PullbackState:
    """Tracks pullback state machine for a coin."""
    def __init__(self):
        self.active = False
        self.direction = None  # 'LONG' or 'SHORT'
        self.start_bar = 0
        self.stack_aligned_at = 0
        self.pullback_occurred = False
        self.lowest_pullback_dist = 0.0  # For longs: how far below EMA9
        self.highest_pullback_dist = 0.0  # For shorts: how far above EMA9
        self.last_candle_time = None


# Global state tracker (reset per main() call)
_pullback_states = {}


def analyse(coin: str, conn, candle_start: datetime, timeframe: str = "5min") -> dict:
    """
    Run momentum scalper analysis with pullback entry logic.

    Entry Logic:
        1. Wait for EMA stack to align (EMA9>EMA21>EMA50 for longs)
        2. Verify RSI(14) momentum condition (>50 for longs, <50 for shorts)
        3. Wait for price to pull back to/cross EMA9
        4. Enter when price crosses back in trend direction

    Returns a standard signal_envelope dict with action BUY/SELL/HOLD.
    """
    global _pullback_states

    # Initialize state for this coin if needed
    if coin not in _pullback_states:
        _pullback_states[coin] = PullbackState()

    state = _pullback_states[coin]

    rows = fetch_recent(conn, coin, limit=MIN_ROWS, timeframe=timeframe)

    if len(rows) < MIN_ROWS:
        log.warning("%s: insufficient data (%d rows, need %d)", coin, len(rows), MIN_ROWS)
        return signal_envelope(
            STRATEGY, coin, "HOLD", 0.0,
            f"insufficient data ({len(rows)}/{MIN_ROWS} rows)",
        )

    # Extract OHLCV series (oldest â newest)
    closes  = [float(r["price"])                                           for r in rows]
    highs   = [float(r["high_price"] if r.get("high_price") else r["price"])  for r in rows]
    lows    = [float(r["low_price"]  if r.get("low_price")  else r["price"])  for r in rows]
    volumes = [float(r.get("volume_5m", 0) or 0)                           for r in rows]

    price = closes[-1]
    prev_price = closes[-2] if len(closes) > 1 else price
    prev_high = highs[-2] if len(highs) > 1 else highs[-1]
    prev_low = lows[-2] if len(lows) > 1 else lows[-1]

    # ââ Calculate Indicators âââââââââââââââââââââââââââââââââââââââââââââââââ
    ema_fast_series = calculate_ema(closes, EMA_FAST)
    ema_mid_series  = calculate_ema(closes, EMA_MID)
    ema_slow_series = calculate_ema(closes, EMA_SLOW)
    rsi_series = calculate_rsi(closes, RSI_PERIOD)
    atr_series = calculate_atr_series(highs, lows, closes, ATR_PERIOD)

    ema_fast = ema_fast_series[-1]
    ema_mid  = ema_mid_series[-1]
    ema_slow = ema_slow_series[-1]
    ema_fast_prev = ema_fast_series[-2] if len(ema_fast_series) > 1 else ema_fast

    current_rsi = rsi_series[-1]
    current_atr = atr_series[-1]

    if any(v != v for v in [ema_fast, ema_mid, ema_slow, current_rsi]):
        log.warning("%s: indicator calculation returned NaN", coin)
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "Indicator NaN â insufficient history")

    # EMA stack conditions
    bullish_stack = ema_fast > ema_mid > ema_slow
    bearish_stack = ema_fast < ema_mid < ema_slow
    bullish_stack_prev = ema_fast_prev > ema_mid_series[-2] > ema_slow_series[-2] if len(ema_mid_series) > 1 else False
    bearish_stack_prev = ema_fast_prev < ema_mid_series[-2] < ema_slow_series[-2] if len(ema_mid_series) > 1 else False

    # RSI conditions
    rsi_long_ok = 50 < current_rsi < 70  # Momentum but not overbought
    rsi_short_ok = 30 < current_rsi < 50  # Momentum but not oversold

    # Volume
    vol_sma20 = calculate_sma_scalar(volumes[:-1], 20)
    current_vol = volumes[-1]
    volume_ratio = current_vol / vol_sma20 if vol_sma20 > 0 else 0
    strong_volume = volume_ratio >= VOLUME_MULT

    # Swings
    swing_high = get_swing_high(highs, LOOKBACK_SWING)
    swing_low = get_swing_low(lows, LOOKBACK_SWING)

    # Price vs EMA9
    price_above_ema9 = price > ema_fast
    price_below_ema9 = price < ema_fast
    prev_price_above_ema9 = prev_price > ema_fast_prev
    prev_price_below_ema9 = prev_price < ema_fast_prev

    dist_from_ema9_pct = (price - ema_fast) / ema_fast * 100

    # ââ Update Pullback State Machine ââââââââââââââââââââââââââââââââââââââââ

    # Reset state if too many bars passed or candle time jumped
    if state.last_candle_time and candle_start != state.last_candle_time:
        time_diff = (candle_start - state.last_candle_time).total_seconds()
        if time_diff > 600:  # More than 10 min gap = reset
            state = PullbackState()
            _pullback_states[coin] = state

    state.last_candle_time = candle_start

    # Check for new pullback setup (stack just aligned with RSI confirmation)
    if not state.active:
        if bullish_stack and not bullish_stack_prev and rsi_long_ok:
            state.active = True
            state.direction = "LONG"
            state.start_bar = len(rows)
            state.stack_aligned_at = len(rows)
            state.pullback_occurred = False
            state.lowest_pullback_dist = 0.0
            state.highest_pullback_dist = 0.0
            log.debug("%s: LONG pullback setup activated", coin)
        elif bearish_stack and not bearish_stack_prev and rsi_short_ok:
            state.active = True
            state.direction = "SHORT"
            state.start_bar = len(rows)
            state.stack_aligned_at = len(rows)
            state.pullback_occurred = False
            state.lowest_pullback_dist = 0.0
            state.highest_pullback_dist = 0.0
            log.debug("%s: SHORT pullback setup activated", coin)

    # Update active pullback state
    if state.active:
        bars_since_start = len(rows) - state.start_bar

        # Reset if too old
        if bars_since_start > PULLBACK_MAX_BARS:
            log.debug("%s: Pullback setup expired (%d bars)", coin, bars_since_start)
            state = PullbackState()
            _pullback_states[coin] = state
        else:
            # Track pullback depth
            if state.direction == "LONG":
                if dist_from_ema9_pct < state.lowest_pullback_dist:
                    state.lowest_pullback_dist = dist_from_ema9_pct
                # Check if pullback occurred (price at or below EMA9)
                if price <= ema_fast or lows[-1] <= ema_fast:
                    state.pullback_occurred = True
            else:  # SHORT
                if dist_from_ema9_pct > state.highest_pullback_dist:
                    state.highest_pullback_dist = dist_from_ema9_pct
                # Check if pullback occurred (price at or above EMA9)
                if price >= ema_fast or highs[-1] >= ema_fast:
                    state.pullback_occurred = True

    # ââ Meta dict âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
    meta = {
        "price":        price,
        "ema9":         round(ema_fast, 4),
        "ema21":        round(ema_mid, 4),
        "ema50":        round(ema_slow, 4),
        "rsi14":        round(current_rsi, 2),
        "swing_high":   round(swing_high, 4) if swing_high == swing_high else None,
        "swing_low":    round(swing_low, 4) if swing_low == swing_low else None,
        "volume":       round(current_vol, 4),
        "volume_ratio": round(volume_ratio, 3),
        "atr":          round(current_atr, 4) if current_atr == current_atr else None,
        "candle":       candle_start.isoformat(),
        "timeframe":    timeframe,
        "pullback_state": {
            "active": state.active,
            "direction": state.direction,
            "pullback_occurred": state.pullback_occurred,
        },
    }

    # ââ Signal Decision âââââââââââââââââââââââââââââââââââââââââââââââââââââââ

    # Check for pullback entry
    can_enter_long = (
        state.active and
        state.direction == "LONG" and
        state.pullback_occurred and
        price_above_ema9 and
        prev_price_below_ema9 and  # Crossed back above
        strong_volume
    )

    can_enter_short = (
        state.active and
        state.direction == "SHORT" and
        state.pullback_occurred and
        price_below_ema9 and
        prev_price_above_ema9 and  # Crossed back below
        strong_volume
    )

    if can_enter_long:
        pullback_depth = abs(state.lowest_pullback_dist)
        if pullback_depth >= MIN_PULLBACK_PCT:
            swing_sl_dist = price - swing_low if swing_low == swing_low else current_atr * 2
            atr_sl_dist = current_atr * 1.0 if current_atr == current_atr else swing_sl_dist
            sl_dist = min(swing_sl_dist, atr_sl_dist) if swing_low == swing_low else atr_sl_dist

            sl_price = round(price - sl_dist, 4)
            tp_price = round(price + sl_dist * 2.0, 4)  # 2R target

            # Confidence scoring
            ema_sep = (ema_fast - ema_mid) / ema_mid * 100 + (ema_mid - ema_slow) / ema_slow * 100
            conf = 0.55
            conf += min(ema_sep * 0.3, 0.15)
            conf += min((volume_ratio - VOLUME_MULT) * 0.05, 0.10)
            conf += min(pullback_depth * 0.5, 0.10)
            conf = round(min(conf, 0.95), 2)

            meta.update({
                "pullback_depth_pct": round(pullback_depth, 3),
                "sl_price": sl_price,
                "tp_price": tp_price,
                "entry_type": "pullback",
            })

            log.info(
                "BUY signal %s | price=%.2f ema9=%.2f rsi=%.1f "
                "swing_low=%.2f sl=%.4f tp=%.4f conf=%.2f",
                coin, price, ema_fast, current_rsi, swing_low, sl_price, tp_price, conf,
            )

            # Reset state after entry
            _pullback_states[coin] = PullbackState()

            return signal_envelope(
                STRATEGY, coin, "BUY", conf,
                f"Pullback to EMA9 | RSI={current_rsi:.1f} | vol_ratio={volume_ratio:.2f} | "
                f"pullback={pullback_depth:.2f}% | SL={sl_price} TP={tp_price}",
                meta,
            )

    if can_enter_short:
        pullback_depth = abs(state.highest_pullback_dist)
        if pullback_depth >= MIN_PULLBACK_PCT:
            swing_sl_dist = swing_high - price if swing_high == swing_high else current_atr * 2
            atr_sl_dist = current_atr * 1.0 if current_atr == current_atr else swing_sl_dist
            sl_dist = min(swing_sl_dist, atr_sl_dist) if swing_high == swing_high else atr_sl_dist

            sl_price = round(price + sl_dist, 4)
            tp_price = round(price - sl_dist * 2.0, 4)  # 2R target

            # Confidence scoring
            ema_sep = (ema_mid - ema_fast) / ema_mid * 100 + (ema_slow - ema_mid) / ema_slow * 100
            conf = 0.55
            conf += min(ema_sep * 0.3, 0.15)
            conf += min((volume_ratio - VOLUME_MULT) * 0.05, 0.10)
            conf += min(pullback_depth * 0.5, 0.10)
            conf = round(min(conf, 0.95), 2)

            meta.update({
                "pullback_depth_pct": round(pullback_depth, 3),
                "sl_price": sl_price,
                "tp_price": tp_price,
                "entry_type": "pullback",
            })

            log.info(
                "SELL signal %s | price=%.2f ema9=%.2f rsi=%.1f "
                "swing_high=%.2f sl=%.4f tp=%.4f conf=%.2f",
                coin, price, ema_fast, current_rsi, swing_high, sl_price, tp_price, conf,
            )

            # Reset state after entry
            _pullback_states[coin] = PullbackState()

            return signal_envelope(
                STRATEGY, coin, "SELL", conf,
                f"Rally to EMA9 | RSI={current_rsi:.1f} | vol_ratio={volume_ratio:.2f} | "
                f"pullback={pullback_depth:.2f}% | SL={sl_price} TP={tp_price}",
                meta,
            )

    # HOLD â explain state
    reasons = []

    if state.active:
        reasons.append(f"pullback setup active ({state.direction})")
        if not state.pullback_occurred:
            reasons.append(f"waiting for pullback to EMA9 (dist={dist_from_ema9_pct:.2f}%)")
        elif state.direction == "LONG" and not (price_above_ema9 and prev_price_below_ema9):
            reasons.append(f"waiting for price to cross back above EMA9")
        elif state.direction == "SHORT" and not (price_below_ema9 and prev_price_above_ema9):
            reasons.append(f"waiting for price to cross back below EMA9")
        elif not strong_volume:
            reasons.append(f"volume too low (ratio={volume_ratio:.2f})")
    else:
        if bullish_stack:
            if not rsi_long_ok:
                reasons.append(f"bullish stack but RSI={current_rsi:.1f} not in range (50-70)")
            else:
                reasons.append("bullish stack aligned â waiting for next candle to activate")
        elif bearish_stack:
            if not rsi_short_ok:
                reasons.append(f"bearish stack but RSI={current_rsi:.1f} not in range (30-50)")
            else:
                reasons.append("bearish stack aligned â waiting for next candle to activate")
        else:
            reasons.append(
                f"no EMA stack (EMA9={ema_fast:.2f} EMA21={ema_mid:.2f} EMA50={ema_slow:.2f})"
            )

    reason_str = " | ".join(reasons) if reasons else "no signal"
    log.debug("HOLD %s: %s", coin, reason_str)

    return signal_envelope(STRATEGY, coin, "HOLD", 0.0, reason_str, meta)


# âââ Entry Point ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def main():
    """
    Standalone entry point. Checks candle gate, analyses all coins, prints JSON.
    """
    global _pullback_states
    _pullback_states = {}  # Reset state on each run

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
        "Config: EMA%d/EMA%d/EMA%d | RSI%d | Pullback max=%d bars | VolMult=%.1fx | ATR%d",
        EMA_FAST, EMA_MID, EMA_SLOW, RSI_PERIOD, PULLBACK_MAX_BARS, VOLUME_MULT, ATR_PERIOD,
    )

    conn = get_conn()
    signals = [analyse(coin, conn, candle_start, timeframe="5min") for coin in COINS]

    # Save BUY/SELL signals to database
    from db import save_signal
    saved_count = 0
    for sig in signals:
        if sig['action'] in ('BUY', 'SELL'):
            try:
                row_id = save_signal(conn, sig, table="strategy_signals")
                log.info("Saved %s signal for %s to DB (id=%d)", sig['action'], sig['coin'], row_id)
                saved_count += 1
            except Exception as e:
                log.error("Failed to save signal for %s: %s", sig['coin'], e)

    conn.close()

    mark_acted(STRATEGY, candle_start)
    print(json.dumps(signals, indent=2))


if __name__ == "__main__":
    main()


# ââ Strategy metadata class (used by strategy_registry.py) âââââââââââââââââââ
import sys as _sys
_sys.path.insert(0, r"D:\dev\trading")
from strategy_base import BaseStrategy as _BaseStrategy


class MomentumScalperStrategy(_BaseStrategy):
    """Momentum Scalper â metadata wrapper for strategy_registry."""

    name = "Momentum Scalper"
    description = (
        "Trend pullback strategy on 5min candles. Waits for EMA9>EMA21>EMA50 alignment, "
        "then enters on pullback to EMA9 with RSI(14) momentum confirmation. "
        "Exits at 2R target or stop loss."
    )
    timeframe = "5min"
    coins = ["BTC", "ETH", "SOL"]
    parameters = {
        "ema_fast": 9,
        "ema_mid": 21,
        "ema_slow": 50,
        "rsi_period": 14,
        "rsi_long_min": 50,
        "rsi_long_max": 70,
        "rsi_short_min": 30,
        "rsi_short_max": 50,
        "volume_mult": 2.0,
        "atr_period": 14,
        "atr_sl_mult": 1.0,
        "tp_r_ratio": 2.0,
        "pullback_max_bars": 10,
        "min_pullback_pct": 0.05,
        "cooldown_bars": 20,
    }
    backtest_summary = {
        "return_pct": -17.44,
        "win_rate": 36.0,
        "profit_factor": 0.86,
        "total_trades": 1894,
        "max_drawdown_pct": 18.61,
        "period": "Jun 2023 â Jun 2026",
        "benchmark": "BTC 5min data",
        "note": "Pullback entry vs breakout: -17% vs -57% return, 18.6% vs 59.8% drawdown",
    }


# ââ Function-based metadata (for strategy_registry.py) âââââââââââââââââââââââ
def get_metadata():
    """Return strategy metadata for registry discovery."""
    return {
        "name": "Momentum Scalper",
        "description": (
            "Trend pullback strategy on 5min candles. Waits for EMA9>EMA21>EMA50 alignment, "
            "then enters on pullback to EMA9 with RSI(14) momentum confirmation."
        ),
        "type": "scalp",
        "timeframes": ["5min"],
        "core_logic": {
            "long": ["EMA9 > EMA21 > EMA50", "RSI > 50", "Pullback to EMA9", "Volume > 2x SMA20"],
            "short": ["EMA9 < EMA21 < EMA50", "RSI < 50", "Rally to EMA9", "Volume > 2x SMA20"],
            "filters": ["RSI not overbought/oversold", "Volume confirmation"]
        }
    }
