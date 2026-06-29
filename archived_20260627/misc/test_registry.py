#!/usr/bin/env python3
from strategy_registry import get_all_strategies, STRATEGY_MODULES
import json

print("STRATEGY_MODULES in registry:")
for m in STRATEGY_MODULES:
    print(f"  - {m}")

print()
print("Discovered strategies:")
strategies = get_all_strategies()
for s in strategies:
    module = s.get("module", "unknown")
    name = s.get("name", "unknown")
    print(f"  - {module}: {name}")

print(f"\nTotal: {len(strategies)} strategies discovered")
