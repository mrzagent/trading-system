"""
Strategy: VWAP Mean Reversion Scalp
=====================================
Type:       Scalp
Timeframes: 5M, 15M
Take Profit: VWAP or 1-1.5R
Author:     Livingston (sub-agent)

Description:
    Exploits short-term price overextensions from VWAP and mean reversion
    back to it. Signals when price deviates significantly from VWAP while
    RSI(2) is in extreme territory and volume is declining.

Long Conditions:
    1. Price significantly below VWAP (default >= 0.5% deviation)
    2. RSI(2) < 10
    3. Volume decreasing (current < previous candle volume)

Short Conditions:
    1. Price significantly above VWAP (default >= 0.5% deviation)
    2. RSI(2) > 90
    3. Volume decreasing (current < previous candle volume)
"""

import os
import sys
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from dotenv import load_dotenv

# BaseStrategy (optional graceful import so module is usable standalone too)
try:
    sys.path.insert(0, os.path.dirname(__file__))
    from strategy_base import BaseStrategy as _BaseStrategy
except ImportError:  # pragma: no cover
    class _BaseStrategy:  # type: ignore[no-redef]
        """Minimal stub when strategy_base is not available."""
        def get_metadata(self) -> dict:
            return {}
        def signals(self) -> list:
            return []

# ---------------------------------------------------------------------------
# Environment Configuration
# ---------------------------------------------------------------------------

load_dotenv()

# Hyperliquid API
HL_API_URL: str = os.getenv("HL_API_URL", "https://api.hyperliquid.xyz/info")
HL_WALLET_ADDRESS: str = os.getenv("HL_WALLET_ADDRESS", "")

# Strategy parameters
DEFAULT_VWAP_DEVIATION_THRESHOLD: float = float(
    os.getenv("VWAP_DEVIATION_THRESHOLD", "0.5")
)  # %
RSI_PERIOD: int = int(os.getenv("RSI_PERIOD", "2"))
RSI_OVERSOLD: float = float(os.getenv("RSI_OVERSOLD", "10"))
RSI_OVERBOUGHT: float = float(os.getenv("RSI_OVERBOUGHT", "90"))

# Risk management
RISK_PER_TRADE_PCT: float = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))  # % of equity
TP_R_MIN: float = float(os.getenv("TP_R_MIN", "1.0"))
TP_R_MAX: float = float(os.getenv("TP_R_MAX", "1.5"))

# Timeframes supported
SUPPORTED_TIMEFRAMES = ["5m", "15m"]
DEFAULT_TIMEFRAME: str = os.getenv("DEFAULT_TIMEFRAME", "5m")
CANDLE_LIMIT: int = int(os.getenv("CANDLE_LIMIT", "100"))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("VWAPMeanReversion")


# ---------------------------------------------------------------------------
# Metadata / Signal Dataclass
# ---------------------------------------------------------------------------

@dataclass
class SignalMeta:
    price: float
    vwap: float
    vwap_deviation_pct: float
    rsi_2: float
    volume: float
    prev_volume: float
    timeframe: str = DEFAULT_TIMEFRAME
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class Signal:
    coin: str
    action: str                    # "BUY" | "SELL" | "NONE"
    confidence: float              # 0.0 – 1.0
    meta: SignalMeta

    def to_dict(self) -> dict:
        d = asdict(self)
        d["meta"].pop("timestamp", None)   # keep JSON output clean
        return d

    def to_json(self, indent: Optional[int] = None) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# Hyperliquid API helpers
# ---------------------------------------------------------------------------

def _hl_post(payload: dict) -> dict:
    """Low-level POST to Hyperliquid info endpoint."""
    try:
        resp = requests.post(HL_API_URL, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.error("Hyperliquid API error: %s", exc)
        raise


def fetch_candles(coin: str, timeframe: str = DEFAULT_TIMEFRAME, limit: int = CANDLE_LIMIT) -> list[dict]:
    """
    Fetch OHLCV candles from Hyperliquid.

    Returns a list of dicts with keys:
        t  – open time (ms)
        o  – open
        h  – high
        l  – low
        c  – close
        v  – volume
    """
    if timeframe not in SUPPORTED_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe '{timeframe}'. Use one of {SUPPORTED_TIMEFRAMES}")

    end_time = int(time.time() * 1000)
    # Each candle width in ms
    tf_ms = {"5m": 5 * 60 * 1000, "15m": 15 * 60 * 1000}[timeframe]
    start_time = end_time - limit * tf_ms

    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": timeframe,
            "startTime": start_time,
            "endTime": end_time,
        },
    }

    raw = _hl_post(payload)
    if not isinstance(raw, list):
        raise ValueError(f"Unexpected candle response format: {raw}")

    candles = []
    for c in raw:
        candles.append(
            {
                "t": c.get("t") or c.get("T"),
                "o": float(c.get("o") or c.get("open", 0)),
                "h": float(c.get("h") or c.get("high", 0)),
                "l": float(c.get("l") or c.get("low", 0)),
                "c": float(c.get("c") or c.get("close", 0)),
                "v": float(c.get("v") or c.get("volume", 0)),
            }
        )
    return candles


# ---------------------------------------------------------------------------
# Indicator Calculations
# ---------------------------------------------------------------------------

def calculate_vwap(candles: list[dict]) -> float:
    """
    Session VWAP = cumulative(typical_price × volume) / cumulative(volume)
    typical_price = (high + low + close) / 3
    """
    cum_tp_vol = 0.0
    cum_vol = 0.0
    for c in candles:
        typical_price = (c["h"] + c["l"] + c["c"]) / 3.0
        cum_tp_vol += typical_price * c["v"]
        cum_vol += c["v"]

    if cum_vol == 0:
        raise ZeroDivisionError("Total volume is zero — cannot compute VWAP")

    return cum_tp_vol / cum_vol


def calculate_rsi(candles: list[dict], period: int = RSI_PERIOD) -> float:
    """
    Wilder's RSI for the given period using closing prices.
    Requires at least (period + 1) candles.
    """
    closes = [c["c"] for c in candles]
    if len(closes) < period + 1:
        raise ValueError(
            f"Need at least {period + 1} candles to compute RSI({period}), got {len(closes)}"
        )

    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        if delta > 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(delta))

    # Initial average (simple average over first `period` changes)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    # Wilder smoothing for remaining bars
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def vwap_deviation_pct(price: float, vwap: float) -> float:
    """Return signed % deviation of price from VWAP ((price - vwap) / vwap * 100)."""
    if vwap == 0:
        return 0.0
    return (price - vwap) / vwap * 100.0


# ---------------------------------------------------------------------------
# Confidence Scoring
# ---------------------------------------------------------------------------

def _compute_confidence(
    deviation_pct: float,
    rsi: float,
    action: str,
    threshold: float,
) -> float:
    """
    Heuristic confidence score [0, 1].

    Components:
      - RSI extremity (how far RSI is from 50)
      - VWAP deviation magnitude (how far price is from VWAP)
    """
    if action == "BUY":
        rsi_score = max(0.0, (RSI_OVERSOLD - rsi) / RSI_OVERSOLD)       # 0..1
        dev_score = min(1.0, abs(deviation_pct) / (threshold * 3))       # caps at 3× threshold
    elif action == "SELL":
        rsi_score = max(0.0, (rsi - RSI_OVERBOUGHT) / (100 - RSI_OVERBOUGHT))
        dev_score = min(1.0, abs(deviation_pct) / (threshold * 3))
    else:
        return 0.0

    raw = 0.5 * rsi_score + 0.5 * dev_score
    return round(min(1.0, max(0.0, raw)), 4)


# ---------------------------------------------------------------------------
# Signal Generation
# ---------------------------------------------------------------------------

def generate_signal(
    coin: str,
    timeframe: str = DEFAULT_TIMEFRAME,
    vwap_threshold_pct: float = DEFAULT_VWAP_DEVIATION_THRESHOLD,
) -> Signal:
    """
    Main entry point. Fetches candles, computes indicators, returns a Signal.

    Args:
        coin:               Trading pair symbol, e.g. "BTC"
        timeframe:          "5m" or "15m"
        vwap_threshold_pct: How far price must be from VWAP to count as
                            "significant" deviation (default 0.5%)
    Returns:
        Signal dataclass with action BUY / SELL / NONE
    """
    logger.info("Generating signal for %s [%s]", coin, timeframe)

    candles = fetch_candles(coin, timeframe)
    if len(candles) < RSI_PERIOD + 2:
        raise RuntimeError(f"Insufficient candles returned ({len(candles)})")

    # Current & previous candle
    current = candles[-1]
    prev = candles[-2]

    price = current["c"]
    volume = current["v"]
    prev_volume = prev["v"]

    vwap = calculate_vwap(candles)
    rsi = calculate_rsi(candles, period=RSI_PERIOD)
    dev_pct = vwap_deviation_pct(price, vwap)

    volume_decreasing = volume < prev_volume

    logger.info(
        "%s | price=%.4f | VWAP=%.4f | dev=%.3f%% | RSI(2)=%.2f | vol_dec=%s",
        coin, price, vwap, dev_pct, rsi, volume_decreasing,
    )

    # --- Signal logic ---
    action = "NONE"

    # Long: price well below VWAP + RSI oversold + volume fading
    if (
        dev_pct <= -vwap_threshold_pct
        and rsi < RSI_OVERSOLD
        and volume_decreasing
    ):
        action = "BUY"

    # Short: price well above VWAP + RSI overbought + volume fading
    elif (
        dev_pct >= vwap_threshold_pct
        and rsi > RSI_OVERBOUGHT
        and volume_decreasing
    ):
        action = "SELL"

    confidence = _compute_confidence(dev_pct, rsi, action, vwap_threshold_pct)

    meta = SignalMeta(
        price=round(price, 6),
        vwap=round(vwap, 6),
        vwap_deviation_pct=round(dev_pct, 4),
        rsi_2=round(rsi, 4),
        volume=round(volume, 4),
        prev_volume=round(prev_volume, 4),
        timeframe=timeframe,
    )

    signal = Signal(coin=coin, action=action, confidence=confidence, meta=meta)
    logger.info("Signal: %s", signal.to_json())
    return signal


# ---------------------------------------------------------------------------
# Risk Management
# ---------------------------------------------------------------------------

def calculate_position_size(
    equity: float,
    entry_price: float,
    stop_loss_price: float,
    risk_pct: float = RISK_PER_TRADE_PCT,
) -> float:
    """
    Fixed fractional position sizing.
    risk_pct% of equity is risked per trade.

    Returns position size in base units (e.g. BTC).
    """
    risk_amount = equity * (risk_pct / 100.0)
    risk_per_unit = abs(entry_price - stop_loss_price)
    if risk_per_unit == 0:
        raise ValueError("Stop loss equals entry price — cannot size position")
    size = risk_amount / risk_per_unit
    return round(size, 6)


def calculate_take_profit(
    entry_price: float,
    stop_loss_price: float,
    vwap: float,
    action: str,
    r_min: float = TP_R_MIN,
    r_max: float = TP_R_MAX,
) -> dict:
    """
    Return dict with tp_vwap (mean reversion target) and tp_r (R-multiple target).

    Take profit is the lesser of VWAP or 1–1.5R, whichever is closer to entry.
    """
    risk = abs(entry_price - stop_loss_price)
    if action == "BUY":
        tp_r_min = entry_price + risk * r_min
        tp_r_max = entry_price + risk * r_max
        tp_vwap = vwap
        # choose minimum of VWAP and 1R (conservative first TP)
        tp_primary = min(tp_vwap, tp_r_min) if tp_vwap > entry_price else tp_r_min
    elif action == "SELL":
        tp_r_min = entry_price - risk * r_min
        tp_r_max = entry_price - risk * r_max
        tp_vwap = vwap
        tp_primary = max(tp_vwap, tp_r_min) if tp_vwap < entry_price else tp_r_min
    else:
        return {}

    return {
        "tp_primary": round(tp_primary, 6),
        "tp_vwap": round(tp_vwap, 6),
        "tp_r_min": round(tp_r_min, 6),
        "tp_r_max": round(tp_r_max, 6),
    }


# ---------------------------------------------------------------------------
# Strategy Class (BaseStrategy interface)
# ---------------------------------------------------------------------------

class VWAPMeanReversionStrategy(_BaseStrategy):
    """VWAP Mean Reversion Scalp Strategy — implements BaseStrategy interface.

    Instantiate with a list of coins and optional config overrides.

    Example::
        strat = VWAPMeanReversionStrategy(coins=["BTC", "ETH"], timeframe="5m")
        results = strat.signals()
    """

    name: str = "VWAP Mean Reversion Scalp"
    description: str = (
        "Exploits short-term price overextensions from VWAP and mean reversion "
        "back to it. Fires when RSI(2) is extreme and volume is fading."
    )
    type: str = "scalp"
    timeframes: list[str] = ["5m", "15m"]
    core_logic: dict[str, Any] = {
        "long": [
            "Price >= threshold% below VWAP",
            "RSI(2) < 10",
            "Volume decreasing (current < previous candle)",
        ],
        "short": [
            "Price >= threshold% above VWAP",
            "RSI(2) > 90",
            "Volume decreasing (current < previous candle)",
        ],
        "filters": [
            f"VWAP deviation threshold: {DEFAULT_VWAP_DEVIATION_THRESHOLD}%",
            "Take profit: VWAP or 1–1.5R (whichever is closer)",
        ],
    }

    def __init__(
        self,
        coins: list[str] | None = None,
        timeframe: str = DEFAULT_TIMEFRAME,
        vwap_threshold_pct: float = DEFAULT_VWAP_DEVIATION_THRESHOLD,
    ) -> None:
        self.coins = coins or ["BTC", "ETH"]
        self.timeframe = timeframe
        self.vwap_threshold_pct = vwap_threshold_pct

    def get_metadata(self) -> dict[str, Any]:
        """Return full strategy metadata dict."""
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "timeframes": list(self.timeframes),
            "take_profit": "VWAP or 1–1.5R",
            "core_logic": {
                "long": list(self.core_logic["long"]),
                "short": list(self.core_logic["short"]),
                "filters": list(self.core_logic["filters"]),
            },
            "config": {
                "vwap_threshold_pct": self.vwap_threshold_pct,
                "rsi_period": RSI_PERIOD,
                "rsi_oversold": RSI_OVERSOLD,
                "rsi_overbought": RSI_OVERBOUGHT,
                "risk_per_trade_pct": RISK_PER_TRADE_PCT,
                "tp_r_min": TP_R_MIN,
                "tp_r_max": TP_R_MAX,
            },
        }

    def signals(self) -> list[dict[str, Any]]:
        """Generate signals for all configured coins.

        Returns:
            List of signal dicts with keys:
                coin, direction, confidence, strategy, meta
        """
        results: list[dict[str, Any]] = []
        for coin in self.coins:
            try:
                sig = generate_signal(
                    coin=coin,
                    timeframe=self.timeframe,
                    vwap_threshold_pct=self.vwap_threshold_pct,
                )
                results.append(
                    {
                        "coin": sig.coin,
                        "direction": sig.action,       # BUY | SELL | NONE
                        "confidence": sig.confidence,
                        "strategy": self.name,
                        "meta": asdict(sig.meta),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Signal generation failed for %s: %s", coin, exc)
                results.append(
                    {
                        "coin": coin,
                        "direction": "NONE",
                        "confidence": 0.0,
                        "strategy": self.name,
                        "meta": {"error": str(exc)},
                    }
                )
        return results


# ---------------------------------------------------------------------------
# CLI / Demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="VWAP Mean Reversion Scalp Strategy")
    parser.add_argument("--coin", default="BTC", help="Coin symbol (default: BTC)")
    parser.add_argument(
        "--timeframe",
        default=DEFAULT_TIMEFRAME,
        choices=SUPPORTED_TIMEFRAMES,
        help="Candle timeframe (default: 5m)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=DEFAULT_VWAP_DEVIATION_THRESHOLD,
        help="VWAP deviation threshold %% (default: 0.5)",
    )
    parser.add_argument(
        "--equity",
        type=float,
        default=1000.0,
        help="Account equity for position sizing (default: 1000)",
    )
    parser.add_argument(
        "--stop-pct",
        type=float,
        default=0.3,
        help="Stop loss %% from entry for sizing calc (default: 0.3)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    args = parser.parse_args()

    sig = generate_signal(
        coin=args.coin,
        timeframe=args.timeframe,
        vwap_threshold_pct=args.threshold,
    )

    output = sig.to_dict()

    if sig.action != "NONE":
        entry = sig.meta.price
        sl_price = (
            entry * (1 - args.stop_pct / 100)
            if sig.action == "BUY"
            else entry * (1 + args.stop_pct / 100)
        )
        size = calculate_position_size(
            equity=args.equity,
            entry_price=entry,
            stop_loss_price=sl_price,
            risk_pct=RISK_PER_TRADE_PCT,
        )
        tp = calculate_take_profit(
            entry_price=entry,
            stop_loss_price=sl_price,
            vwap=sig.meta.vwap,
            action=sig.action,
        )
        output["risk_management"] = {
            "equity": args.equity,
            "stop_loss": round(sl_price, 6),
            "position_size": size,
            **tp,
        }

    indent = 2 if args.pretty else None
    print(json.dumps(output, indent=indent))
