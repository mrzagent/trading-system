#!/usr/bin/env python3
"""Inspect Exchange.update_leverage signature"""
import sys
sys.path.insert(0, r'D:\dev\trading')

from hyperliquid.exchange import Exchange
import inspect

print("Exchange.update_leverage signature:")
sig = inspect.signature(Exchange.update_leverage)
print(sig)
print()
print("Parameters:")
for name, param in sig.parameters.items():
    print(f"  {name}: {param.default if param.default is not inspect.Parameter.empty else 'required'}")
