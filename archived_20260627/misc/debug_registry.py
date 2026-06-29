#!/usr/bin/env python3
import sys
sys.path.insert(0, r"D:\dev\trading")

import importlib
import inspect
from strategy_base import BaseStrategy

# Try importing the module
mod_name = "strategy_momentum_scalper"
try:
    mod = importlib.import_module(mod_name)
    print(f"Successfully imported {mod_name}")
    print(f"Module attributes: {[name for name in dir(mod) if not name.startswith('_')]}")
    
    # Check for classes
    classes = inspect.getmembers(mod, inspect.isclass)
    print(f"\nClasses found: {[name for name, obj in classes]}")
    
    # Check for BaseStrategy subclasses
    for name, obj in classes:
        if issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
            print(f"\nFound BaseStrategy subclass: {name}")
            try:
                instance = obj()
                metadata = instance.get_metadata()
                print(f"Metadata: {metadata}")
            except Exception as e:
                print(f"Error instantiating: {e}")
except Exception as e:
    print(f"Error importing {mod_name}: {e}")
    import traceback
    traceback.print_exc()
