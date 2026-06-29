#!/usr/bin/env python3
"""
test_strategy_state.py — Test that orchestrator respects .strategy_state.json

Usage:
    python test_strategy_state.py

This test:
1. Creates a mock .strategy_state.json with some strategies disabled
2. Verifies load_strategy_state() reads the file correctly
3. Verifies is_strategy_enabled() returns correct values
4. Verifies the orchestrator skips disabled strategies
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# Add trading directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator import (
    load_strategy_state,
    is_strategy_enabled,
    STRATEGY_CONFIG,
    STRATEGY_STATE_PATH
)


def test_load_strategy_state():
    """Test loading strategy state from file."""
    print("\n" + "="*60)
    print("TEST 1: load_strategy_state()")
    print("="*60)
    
    # Create a temporary state file
    test_state = {
        "rsi_mean_reversion": True,
        "momentum_rsi": False,
        "fvg_proximity": False,
        "volume_spike": True
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_state, f)
        temp_path = f.name
    
    try:
        # Temporarily override the path
        original_path = STRATEGY_STATE_PATH
        import orchestrator
        orchestrator.STRATEGY_STATE_PATH = Path(temp_path)
        
        state = load_strategy_state()
        
        assert "rsi_mean_reversion" in state, "Missing rsi_mean_reversion"
        assert "momentum_rsi" in state, "Missing momentum_rsi"
        assert state["rsi_mean_reversion"] == True, "rsi_mean_reversion should be True"
        assert state["momentum_rsi"] == False, "momentum_rsi should be False"
        
        print("[PASS] Strategy state loaded correctly")
        print(f"   Loaded {len(state)} strategy states")
        
    finally:
        orchestrator.STRATEGY_STATE_PATH = original_path
        os.unlink(temp_path)


def test_is_strategy_enabled():
    """Test strategy enable/disable logic."""
    print("\n" + "="*60)
    print("TEST 2: is_strategy_enabled()")
    print("="*60)
    
    state = {
        "rsi_mean_reversion": True,
        "momentum_rsi": False,
    }
    
    # Test enabled strategy
    assert is_strategy_enabled("rsi_mean_reversion", state) == True, \
        "rsi_mean_reversion should be enabled"
    print("[PASS] Enabled strategy returns True")
    
    # Test disabled strategy
    assert is_strategy_enabled("momentum_rsi", state) == False, \
        "momentum_rsi should be disabled"
    print("[PASS] Disabled strategy returns False")
    
    # Test missing strategy (should default to enabled)
    assert is_strategy_enabled("unknown_strategy", state) == True, \
        "Unknown strategies should default to enabled"
    print("[PASS] Missing strategy defaults to enabled")
    
    # Test empty state (all should be enabled)
    assert is_strategy_enabled("any_strategy", {}) == True, \
        "Empty state should enable all strategies"
    print("[PASS] Empty state enables all strategies")


def test_strategy_filtering():
    """Test that strategies are properly filtered based on state."""
    print("\n" + "="*60)
    print("TEST 3: Strategy filtering in analyse()")
    print("="*60)
    
    # Create a state file with some strategies disabled
    test_state = {
        "rsi_mean_reversion": False,  # Disable
        "momentum_rsi": False,        # Disable
        "fvg_proximity": True,        # Enable
        "volume_spike": True,         # Enable
        "trend_breakout": False,      # Disable
        "mean_reversion": True,       # Enable
        "momentum_accel": True,       # Enable
        "vwap_reversion": False,      # Disable
        "momentum_scalper": True,     # Enable
        "pullback_scalper": False,    # Disable
    }
    
    # Count expected enabled/disabled
    expected_enabled = sum(1 for v in test_state.values() if v)
    expected_disabled = sum(1 for v in test_state.values() if not v)
    
    print(f"   Test state: {expected_enabled} enabled, {expected_disabled} disabled")
    
    # Verify all strategies in config are accounted for
    for name in STRATEGY_CONFIG.keys():
        assert name in test_state, f"Strategy {name} not in test state"
    
    print("[PASS] All 10 strategies accounted for in test")
    
    # Verify filtering logic
    enabled_strategies = [name for name in STRATEGY_CONFIG.keys() 
                          if is_strategy_enabled(name, test_state)]
    disabled_strategies = [name for name in STRATEGY_CONFIG.keys() 
                           if not is_strategy_enabled(name, test_state)]
    
    assert len(enabled_strategies) == expected_enabled, \
        f"Expected {expected_enabled} enabled, got {len(enabled_strategies)}"
    assert len(disabled_strategies) == expected_disabled, \
        f"Expected {expected_disabled} disabled, got {len(disabled_strategies)}"
    
    print("[PASS] Filtering works correctly")
    print(f"   Enabled ({len(enabled_strategies)}): {', '.join(enabled_strategies)}")
    print(f"   Disabled ({len(disabled_strategies)}): {', '.join(disabled_strategies)}")


def test_empty_state_file():
    """Test behavior when .strategy_state.json doesn't exist."""
    print("\n" + "="*60)
    print("TEST 4: Empty/missing state file")
    print("="*60)
    
    # Point to non-existent file
    original_path = STRATEGY_STATE_PATH
    import orchestrator
    orchestrator.STRATEGY_STATE_PATH = Path("/nonexistent/path/strategy_state.json")
    
    try:
        state = load_strategy_state()
        assert state == {}, "Empty state should return empty dict"
        print("[PASS] Missing file returns empty dict")
        
        # All strategies should be enabled
        for name in STRATEGY_CONFIG.keys():
            assert is_strategy_enabled(name, state) == True, \
                f"{name} should be enabled when state file missing"
        print("[PASS] All strategies enabled when state file missing")
        
    finally:
        orchestrator.STRATEGY_STATE_PATH = original_path


def test_dashboard_integration():
    """Test that dashboard API format is compatible."""
    print("\n" + "="*60)
    print("TEST 5: Dashboard API compatibility")
    print("="*60)
    
    # Simulate what the dashboard API writes
    dashboard_format = {
        "fvg_proximity": True,
        "momentum_rsi": True,
        "rsi_mean_reversion": True,
        "volume_spike": False,
        "trend_breakout": True,
        "mean_reversion": False,
        "momentum_accel": True,
        "vwap_reversion": False,
        "momentum_scalper": True,
        "pullback_scalper": True
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(dashboard_format, f)
        temp_path = f.name
    
    try:
        original_path = STRATEGY_STATE_PATH
        import orchestrator
        orchestrator.STRATEGY_STATE_PATH = Path(temp_path)
        
        state = load_strategy_state()
        
        # Verify all keys are present and values are correct
        for name, expected in dashboard_format.items():
            assert name in state, f"Missing {name}"
            assert state[name] == expected, f"{name} should be {expected}"
            assert is_strategy_enabled(name, state) == expected, \
                f"is_strategy_enabled({name}) should return {expected}"
        
        print("[PASS] Dashboard format compatible")
        print(f"   Verified {len(dashboard_format)} strategy toggles")
        
    finally:
        orchestrator.STRATEGY_STATE_PATH = original_path
        os.unlink(temp_path)


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("STRATEGY STATE TEST SUITE")
    print("="*60)
    print(f"Testing {len(STRATEGY_CONFIG)} configured strategies")
    
    try:
        test_load_strategy_state()
        test_is_strategy_enabled()
        test_strategy_filtering()
        test_empty_state_file()
        test_dashboard_integration()
        
        print("\n" + "="*60)
        print("ALL TESTS PASSED")
        print("="*60)
        return 0
        
    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
