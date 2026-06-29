# Momentum Acceleration Strategy - Data Analysis Report

**Date:** 2026-06-24  
**Strategy:** Momentum Acceleration (EMA Stack + Breakout + Volume + ATR)  
**File:** `D:\dev\trading\strategy_momentum_acceleration.py`

---

## Executive Summary

⚠️ **INSUFFICIENT HISTORICAL DATA**

The Momentum Acceleration strategy requires **220 rows minimum** for accurate calculations, but current data falls short:
- **1h timeframe**: 113 rows (need 107 more)
- **4h timeframe**: 47 rows (need 173 more)

**OHLC and Volume data quality is GOOD** - the strategy will work once enough history is collected.

---

## Strategy Requirements

| Component | Period | Rows Needed | Purpose |
|-----------|--------|-------------|---------|
| EMA Slow | 200 | 200 | Long-term trend direction |
| ATR + SMA | 14 + 50 | 64 | Volatility expansion detection |
| Breakout Range | 30 | 30 | 30-period high/low range |
| **Buffer** | - | 20 | Safety margin |
| **TOTAL** | - | **220** | Minimum for reliable signals |

---

## Current Data Status

### 1h Timeframe ⚠️ INSUFFICIENT ROWS

| Metric | Value | Status |
|--------|-------|--------|
| Table | `trading_prices_1h` | ✅ Exists |
| Rows per coin | 113 | ⚠️ Need 220 (51% complete) |
| high_price | Available | ✅ Populated |
| low_price | Available | ✅ Populated |
| volume_candle | Available | ✅ Populated |
| Data quality | Good | ✅ OHLC accurate |

### 4h Timeframe ⚠️ INSUFFICIENT ROWS

| Metric | Value | Status |
|--------|-------|--------|
| Table | `trading_prices_4h` | ✅ Exists |
| Rows per coin | 47 | ⚠️ Need 220 (21% complete) |
| high_price | Available | ✅ Populated |
| low_price | Available | ✅ Populated |
| volume_candle | Available | ✅ Populated |
| Data quality | Good | ✅ OHLC accurate |

---

## Strategy Logic Recap

**Entry Conditions (ALL 4 must be true):**

| Condition | Long | Short |
|-----------|------|-------|
| 1. EMA Stack | EMA20 > EMA50 > EMA200 | EMA20 < EMA50 < EMA200 |
| 2. Breakout | Close > 30-period High | Close < 30-period Low |
| 3. Volume | Volume > 1.5 × SMA20(vol) | Volume > 1.5 × SMA20(vol) |
| 4. ATR | ATR(14) > ATR_SMA50 | ATR(14) > ATR_SMA50 |

**Exit:**
- Stop Loss: 1.5 × ATR(14)
- Take Profit: 3.0 × ATR(14) (2:1 R/R)

---

## Options to Enable Strategy

### Option 1: Wait for Data Collection (Recommended)
**Timeline:** 
- 1h: ~4.5 days to reach 220 rows
- 4h: ~18 days to reach 220 rows

**Action:** Continue running collector; strategy will automatically start working

### Option 2: Reduce EMA_SLOW Parameter (Quick Fix)
**Change:** Lower EMA_SLOW from 200 to 100

```python
# In strategy or via env var
EMA_SLOW = 100  # Instead of 200
MIN_ROWS = 150  # Instead of 220
```

**Impact:**
- Faster signals (less history needed)
- Less reliable long-term trend detection
- More false signals possible

### Option 3: Reduce All Parameters (Aggressive)
**Change:** 
- EMA_SLOW: 200 → 50
- ATR_SMA_PERIOD: 50 → 20
- BREAKOUT_PERIOD: 30 → 15

```python
EMA_SLOW = 50
ATR_SMA_PERIOD = 20
BREAKOUT_PERIOD = 15
MIN_ROWS = 75  # Much more achievable
```

**Impact:**
- Strategy works immediately
- Significantly different behavior
- Higher frequency, potentially lower quality signals

---

## Comparison with Other Strategies

| Strategy | Min Rows | Current 1h | Current 4h | Status |
|----------|----------|------------|------------|--------|
| Momentum + RSI | ~25 | 113 ✅ | 47 ✅ | Works |
| Fair Value Gap | ~50 | 113 ✅ | 47 ⚠️ | Works on 1h |
| Volume Spike | ~20 | 113 ✅ | 47 ✅ | Works |
| Trend Breakout | ~55 | 113 ✅ | 47 ⚠️ | Works on 1h |
| Mean Reversion | ~38 | 113 ✅ | 47 ✅ | Works |
| **Momentum Acceleration** | **220** | **113 ❌** | **47 ❌** | **Needs more data** |

---

## Recommendation

**Short-term (now):** Use Option 2 or 3 to test the strategy with reduced parameters

**Long-term (recommended):** Wait for full 220 rows per coin
- The EMA200 is crucial for this strategy's trend alignment
- ATR_SMA50 provides important volatility context
- Reducing parameters changes the strategy's character significantly

---

## Files Referenced

- Strategy: `D:\dev\trading\strategy_momentum_acceleration.py`
- Test: `D:\dev\trading\test_momentum_acceleration.py`
- Database: `D:\dev\trading\db.py`
- Collector: `D:\dev\trading\candle_collector.py`

---

## Next Steps

1. **Decide:** Wait for data vs reduce parameters
2. **If reducing:** Test with EMA_SLOW=100 first
3. **If waiting:** Monitor row counts; strategy auto-enables at 220 rows
4. **Validation:** Once enabled, verify signals against manual chart analysis
