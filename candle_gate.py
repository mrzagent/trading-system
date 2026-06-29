#!/usr/bin/env python3
"""
candle_gate.py — Shared candle-close gate for strategy agents.

Prevents a strategy from firing multiple times within the same candle period
when the orchestrator polls more frequently than the candle duration.

Usage:
    from candle_gate import should_act, mark_acted

    act, candle_start = should_act("rsi_mean_reversion", candle_minutes=60)
    if not act:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "candle not closed yet")
    # ... run analysis ...
    mark_acted("rsi_mean_reversion", candle_start)
"""

import json
import os
from datetime import datetime, timezone

# Stored alongside the strategy files
_GATE_FILE = os.path.join(os.path.dirname(__file__), ".candle_gate.json")

_TF_WINDOW_SEC = {
    "5min": 300,
    "1h":   3600,
    "4h":   14400,
}


def current_candle_start(candle_minutes: int) -> datetime:
    """Returns the UTC start timestamp of the current candle period."""
    now = datetime.now(timezone.utc)
    total_minutes = now.hour * 60 + now.minute
    floored = (total_minutes // candle_minutes) * candle_minutes
    return now.replace(
        hour=floored // 60,
        minute=floored % 60,
        second=0,
        microsecond=0,
    )


def _load() -> dict:
    if os.path.exists(_GATE_FILE):
        with open(_GATE_FILE) as f:
            return json.load(f)
    return {}


def _save(data: dict) -> None:
    with open(_GATE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def should_act(strategy: str, candle_minutes: int, timeframe: str = "5min") -> tuple[bool, datetime]:
    """
    Returns (should_act, candle_start).
    - True  → new candle has opened since last run; proceed with analysis.
    - False → already acted this candle; skip and return HOLD.

    When timeframe is provided, candle_minutes is overridden by the
    matching window from _TF_WINDOW_SEC (300/3600/14400).
    """
    if timeframe in _TF_WINDOW_SEC:
        candle_minutes = _TF_WINDOW_SEC[timeframe] // 60
    candle_start = current_candle_start(candle_minutes)
    candle_ts = candle_start.isoformat()
    last_acted = _load().get(strategy)
    return (last_acted != candle_ts), candle_start


def mark_acted(strategy: str, candle_start: datetime) -> None:
    """Record that this strategy has acted for the given candle."""
    data = _load()
    data[strategy] = candle_start.isoformat()
    _save(data)
