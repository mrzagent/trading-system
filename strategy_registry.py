#!/usr/bin/env python3
"""
strategy_registry.py — Strategy discovery and metadata registry.

Usage:
    from strategy_registry import get_all_strategies

    strategies = get_all_strategies()
    # Returns a list of metadata dicts, one per strategy.

Each strategy module must expose a class that inherits from BaseStrategy and
implements get_metadata().  The registry auto-discovers all such classes from
the known strategy modules listed in STRATEGY_MODULES.
"""

import importlib
import inspect
import sys
from pathlib import Path
from typing import Any

# Ensure the trading directory is importable
_TRADING_DIR = Path(__file__).parent
if str(_TRADING_DIR) not in sys.path:
    sys.path.insert(0, str(_TRADING_DIR))

from strategy_base import BaseStrategy

# ── Registered strategy modules ────────────────────────────────────────────
# Add new strategy modules here when they implement BaseStrategy.
STRATEGY_MODULES: list[str] = [
    # Class-based strategies (inherit from BaseStrategy)
    "strategy_momentum_scalper",
    "strategy_pullback_scalper",
    # Function-based strategies with get_metadata()
    "strategy_rsi",               # STRATEGY = "rsi_mean_reversion"
    "strategy_momentum",          # STRATEGY = "momentum_rsi"
    "strategy_fvg",               # STRATEGY = "fvg_proximity"
    "strategy_volume",            # STRATEGY = "volume_spike"
    "strategy_trend_breakout",    # STRATEGY = "trend_breakout"
    "strategy_mean_reversion",    # STRATEGY = "mean_reversion"
    "strategy_momentum_accel",    # STRATEGY = "momentum_accel"
    "strategy_vwap_reversion",    # STRATEGY = "vwap_reversion"
]


def _discover_strategy_class(module_name: str) -> type[BaseStrategy] | None:
    """Import a module and return the first BaseStrategy subclass found."""
    try:
        mod = importlib.import_module(module_name)
    except Exception as exc:
        print(f"[strategy_registry] WARNING: could not import {module_name!r}: {exc}")
        return None

    for _name, obj in inspect.getmembers(mod, inspect.isclass):
        if issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
            return obj

    # Don't print warning - function-based strategies don't have BaseStrategy
    return None


def _get_function_metadata(module_name: str) -> dict[str, Any] | None:
    """Try to get metadata from a function-based strategy with get_metadata()."""
    try:
        mod = importlib.import_module(module_name)
        if hasattr(mod, 'get_metadata') and callable(mod.get_metadata):
            metadata = mod.get_metadata()
            if isinstance(metadata, dict):
                return metadata
    except Exception as exc:
        pass  # Silently ignore function metadata errors
    return None


def get_all_strategies() -> list[dict[str, Any]]:
    """Return metadata dicts for all registered strategies.

    Returns:
        List of dicts, each with keys:
            name, description, type, timeframes, core_logic
        Ordered to match STRATEGY_MODULES.
    """
    results: list[dict[str, Any]] = []

    for module_name in STRATEGY_MODULES:
        # Try class-based strategy first
        cls = _discover_strategy_class(module_name)
        if cls is not None:
            try:
                instance = cls()
                metadata = instance.get_metadata()
                metadata["module"] = module_name
                results.append(metadata)
                continue
            except Exception as exc:
                pass  # Silently ignore class metadata errors
        
        # Try function-based strategy
        func_metadata = _get_function_metadata(module_name)
        if func_metadata is not None:
            func_metadata["module"] = module_name
            results.append(func_metadata)
            continue
        
        # Silently skip modules with no metadata

    return results


# ── CLI quick-test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    strategies = get_all_strategies()
    print(json.dumps(strategies))
