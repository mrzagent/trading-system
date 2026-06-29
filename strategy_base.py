#!/usr/bin/env python3
"""
strategy_base.py — Base class for all trading strategies.

Provides a common interface for metadata exposure and signal generation.
All strategy modules should inherit from BaseStrategy and implement:
  - get_metadata()  → dict with name, description, type, timeframes, core_logic
  - signals()       → list of signal dicts (abstract)
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseStrategy(ABC):
    """Base class for all trading strategies.

    Attributes (set by subclass or get_metadata):
        name        : Human-readable strategy name
        description : Short description of the strategy's objective
        timeframes  : List of supported timeframe strings, e.g. ["1h", "4h"]
        type        : Strategy type — "swing" or "scalp"
        core_logic  : Dict with "long", "short", and optional "filters" keys
    """

    # ── Subclasses should override these class-level defaults ──────────────
    name: str = "Unnamed Strategy"
    description: str = ""
    timeframes: list[str] = []
    type: str = "swing"          # "swing" | "scalp"
    core_logic: dict[str, Any] = {
        "long": [],
        "short": [],
        "filters": [],
    }

    # ───────────────────────────────────────────────────────────────────────

    def get_metadata(self) -> dict[str, Any]:
        """Return strategy metadata as a serialisable dict.

        Override in subclasses to provide richer descriptions.
        The default implementation reflects the class-level attributes.
        """
        return {
            "name": self.name,
            "description": self.description,
            "type": self.type,
            "timeframes": list(self.timeframes),
            "core_logic": {
                "long": list(self.core_logic.get("long", [])),
                "short": list(self.core_logic.get("short", [])),
                "filters": list(self.core_logic.get("filters", [])),
            },
        }

    @abstractmethod
    def signals(self) -> list[dict[str, Any]]:
        """Generate trading signals.

        Returns:
            List of signal dicts.  Each dict must at minimum contain:
                {
                    "coin":      str,   # e.g. "BTCUSDT"
                    "direction": str,   # "BUY" | "SELL" | "HOLD"
                    "confidence": float,
                    "strategy":  str,
                }
        """
        ...
