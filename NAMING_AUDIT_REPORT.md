# Trading System Naming Consistency Audit Report

**Date:** 2026-06-27  
**Scope:** All Python files in D:\dev\trading

---

## Executive Summary

Found **multiple naming inconsistencies** across the trading system that could cause:
- Strategies not being recognized
- Risk parameters not being applied
- Registry showing wrong strategies
- Signal filtering issues

---

## Critical Issues Found

### 1. `strategy_breakdown` is NOT a Strategy

**Problem:** `orchestrator.py` includes `"strategy_breakdown"` in STRATEGY_CONFIG, but this is a **dictionary key** for metadata, not a strategy.

**Location:** `orchestrator.py` line ~320
```python
meta = {
    "strategy_breakdown": {  # <-- This is being parsed as a strategy!
        name: {...}
        for name, s in strategy_results.items()
    },
}
```

**Impact:** 
- `strategy_breakdown` appears in STRATEGY_CONFIG (11 items instead of 10)
- Missing from ALLOWED_STRATEGIES
- Missing from RISK_PARAMS
- Causes false warnings in consistency checks

**Fix:** The regex in audit script is incorrectly matching this. The actual STRATEGY_CONFIG has 10 strategies, not 11.

---

### 2. Duplicate/Conflicting Strategy Files

| File | STRATEGY Constant | Issue |
|------|-------------------|-------|
| `strategy_momentum.py` | `momentum_rsi` | Same constant as imported name |
| `strategy_momentum_rsi.py` | `momentum_rsi_confluence` | Different from filename |
| `strategy_momentum_accel.py` | `momentum_accel` | Used in orchestrator |
| `strategy_momentum_acceleration.py` | `momentum_acceleration` | NOT used in orchestrator |

**Problem:** Two files for momentum acceleration:
- `strategy_momentum_accel.py` → `momentum_accel` (USED)
- `strategy_momentum_acceleration.py` → `momentum_acceleration` (NOT USED)

**Same issue with:**
- `strategy_trend_breakout.py` → `trend_breakout` (USED)
- `strategy_trend_following_breakout.py` → `trend_following_breakout` (NOT USED)

---

### 3. Registry Uses Wrong Module Names

**File:** `strategy_registry.py`

**Current STRATEGY_MODULES:**
```python
STRATEGY_MODULES = [
    "strategy_momentum_rsi",           # ✗ File doesn't exist (should be strategy_momentum.py)
    "strategy_trend_following_breakout", # ✗ Not used in orchestrator
    "strategy_mean_reversion",         # ✓ OK
    "strategy_momentum_acceleration",  # ✗ Should be strategy_momentum_accel
    "strategy_vwap_mean_reversion",    # ✗ File doesn't exist (should be strategy_vwap_reversion)
    "strategy_momentum_scalper",       # ✓ OK
    "strategy_pullback_scalper",       # ✓ OK
    "strategy_fvg",                    # ✓ OK
    "strategy_volume",                 # ✓ OK
    "strategy_trend_breakout",         # ✓ OK
    "strategy_vwap_reversion",         # ✓ OK
]
```

**Issues:**
1. `strategy_momentum_rsi` - File doesn't exist (strategy is in `strategy_momentum.py`)
2. `strategy_momentum_acceleration` - Wrong file (should be `strategy_momentum_accel`)
3. `strategy_vwap_mean_reversion` - File doesn't exist (should be `strategy_vwap_reversion`)
4. `strategy_trend_following_breakout` - Not used in orchestrator (duplicate)

---

### 4. Inconsistent Function Naming

**British vs American spelling:**
- `analyse()` - Used in most strategies (British)
- `analyze()` - Not found, but could be inconsistent

**Parameter naming:**
```python
# Some strategies use:
def analyse(coin: str, conn, candle_start, timeframe: str = "5min")

# Others use:
def analyse(coin: str, conn, candle_start: datetime, timeframe: str = "1h")

# Inconsistent type hints for candle_start
```

---

### 5. Strategy Name vs Filename Mismatches

| Filename | STRATEGY Constant | Match? |
|----------|-------------------|--------|
| `strategy_fvg.py` | `fvg_proximity` | ⚠️ Different |
| `strategy_rsi.py` | `rsi_mean_reversion` | ⚠️ Different |
| `strategy_volume.py` | `volume_spike` | ⚠️ Different |
| `strategy_momentum.py` | `momentum_rsi` | ⚠️ Different |

**Note:** This is not necessarily wrong (descriptive names are good), but can be confusing.

---

## Detailed Findings

### Orchestrator STRATEGY_CONFIG (10 strategies)

```python
STRATEGY_CONFIG = {
    "rsi_mean_reversion":     # strategy_rsi.py
    "momentum_rsi":           # strategy_momentum.py
    "fvg_proximity":          # strategy_fvg.py
    "volume_spike":           # strategy_volume.py
    "trend_breakout":         # strategy_trend_breakout.py
    "mean_reversion":         # strategy_mean_reversion.py
    "momentum_accel":         # strategy_momentum_accel.py
    "vwap_reversion":         # strategy_vwap_reversion.py
    "momentum_scalper":       # strategy_momentum_scalper.py
    "pullback_scalper":       # strategy_pullback_scalper.py
}
```

### ALLOWED_STRATEGIES (signal_integrator.py)

All 10 orchestrator strategies + `quorum_view` = 11 total ✓

### STRATEGY_RISK_PARAMS (strategy_risk_config.py)

All 10 orchestrator strategies covered ✓

### STRATEGY_MODULES (strategy_registry.py)

**Problems:**
- Lists 11 modules but 3 have wrong names
- Includes unused `strategy_trend_following_breakout`
- Missing `strategy_rsi`, `strategy_momentum`

---

## Recommendations

### High Priority

1. **Fix strategy_registry.py STRATEGY_MODULES:**
```python
STRATEGY_MODULES = [
    "strategy_rsi",              # Was: strategy_momentum_rsi (wrong)
    "strategy_trend_breakout",   # Was: strategy_trend_following_breakout (unused)
    "strategy_mean_reversion",
    "strategy_momentum_accel",   # Was: strategy_momentum_acceleration (wrong file)
    "strategy_vwap_reversion",   # Was: strategy_vwap_mean_reversion (wrong)
    "strategy_momentum_scalper",
    "strategy_pullback_scalper",
    "strategy_fvg",
    "strategy_volume",
    "strategy_momentum",         # Added (was missing)
]
```

2. **Remove or archive duplicate files:**
- `strategy_momentum_acceleration.py` (unused, use `strategy_momentum_accel.py`)
- `strategy_trend_following_breakout.py` (unused, use `strategy_trend_breakout.py`)
- `strategy_mean_reversion_1h.py` (unused)
- `strategy_mean_reversion_4h.py` (unused)
- `strategy_momentum_rsi.py` (different strategy, `momentum_rsi_confluence`)

### Medium Priority

3. **Standardize function signatures:**
```python
# Recommended standard:
def analyse(
    coin: str,
    conn,
    candle_start: datetime,
    timeframe: str = "5min"
) -> dict:
```

4. **Add docstrings explaining filename vs STRATEGY name differences**

### Low Priority

5. **Consider renaming files to match STRATEGY constants:**
- `strategy_rsi.py` → `strategy_rsi_mean_reversion.py`
- `strategy_momentum.py` → `strategy_momentum_rsi.py`
- `strategy_fvg.py` → `strategy_fvg_proximity.py`
- `strategy_volume.py` → `strategy_volume_spike.py`

---

## Files to Clean Up

### Duplicate/Unused Strategy Files:
1. `strategy_momentum_acceleration.py` - Use `strategy_momentum_accel.py` instead
2. `strategy_trend_following_breakout.py` - Use `strategy_trend_breakout.py` instead
3. `strategy_mean_reversion_1h.py` - Not used in orchestrator
4. `strategy_mean_reversion_4h.py` - Not used in orchestrator
5. `strategy_momentum_rsi.py` - Different strategy (`momentum_rsi_confluence`)

### Registry Issues:
- Fix `strategy_registry.py` STRATEGY_MODULES list

---

## Consistency Matrix

| Strategy Key | File | In Orchestrator | In Allowed | In Risk | In Registry |
|--------------|------|-----------------|------------|---------|-------------|
| rsi_mean_reversion | strategy_rsi.py | ✓ | ✓ | ✓ | ✗ |
| momentum_rsi | strategy_momentum.py | ✓ | ✓ | ✓ | ✗ |
| fvg_proximity | strategy_fvg.py | ✓ | ✓ | ✓ | ✓ |
| volume_spike | strategy_volume.py | ✓ | ✓ | ✓ | ✓ |
| trend_breakout | strategy_trend_breakout.py | ✓ | ✓ | ✓ | ✓ |
| mean_reversion | strategy_mean_reversion.py | ✓ | ✓ | ✓ | ✓ |
| momentum_accel | strategy_momentum_accel.py | ✓ | ✓ | ✓ | ✗ |
| vwap_reversion | strategy_vwap_reversion.py | ✓ | ✓ | ✓ | ✓ |
| momentum_scalper | strategy_momentum_scalper.py | ✓ | ✓ | ✓ | ✓ |
| pullback_scalper | strategy_pullback_scalper.py | ✓ | ✓ | ✓ | ✓ |

**Registry missing:** rsi_mean_reversion, momentum_rsi, momentum_accel

---

## Action Items

- [ ] Fix `strategy_registry.py` STRATEGY_MODULES
- [ ] Archive unused strategy files
- [ ] Verify all strategies load correctly after fixes
- [ ] Run integration test to confirm all 10 strategies work
