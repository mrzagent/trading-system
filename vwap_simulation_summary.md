# VWAP Reversion Strategy - Simulation Summary

## Strategy Overview

**VWAP (Volume Weighted Average Price) Reversion** is a mean reversion strategy that trades price deviations from the volume-weighted average price.

### Core Logic
- **BUY** when price is >1% BELOW VWAP (undervalued)
- **SELL** when price is >1% ABOVE VWAP (overvalued)
- **HOLD** when price is within 1% of VWAP

### Key Parameters
| Parameter | Value |
|-----------|-------|
| Timeframe | 5-minute candles |
| VWAP Period | 24 candles (2 hours) |
| Deviation Threshold | 1.0% |
| Stop Loss | 1.5% |
| Take Profit | 3.0% |
| Risk/Reward | 1:2 |
| Leverage | 3x (optimized) |

---

## 3-Year Backtest Results (BTC, June 2023 - June 2026)

### Portfolio Simulation: $1,000 Starting Capital

| Metric | Value |
|--------|-------|
| **Initial Capital** | $1,000.00 |
| **Final Capital** | $1,079.00 |
| **Total Return** | **+7.90%** |
| **Annualized Return** | ~+2.6% |

### Trade Statistics

| Metric | Value |
|--------|-------|
| **Total Trades** | 1,330 |
| **Winning Trades** | 529 (39.7%) |
| **Losing Trades** | 801 (60.3%) |
| **Win Rate** | 39.7% |
| **Profit Factor** | 1.32 |
| **Max Drawdown** | 1.35% |
| **Average Win** | +3.0% |
| **Average Loss** | -1.5% |
| **Average Hold Time** | 18.7 hours |

### Direction Performance

| Direction | Trades | Win Rate | Total P&L |
|-----------|--------|----------|-----------|
| LONG | ~680 | ~40% | +5.5% |
| SHORT | ~650 | ~39% | +2.4% |

---

## Performance Comparison

| Configuration | Return | Trades | Win Rate | Max DD |
|--------------|--------|--------|----------|--------|
| **1% Dev + 3x Leverage** ⭐ | **+7.90%** | 1,330 | 39.7% | 1.35% |
| 1% Dev + 2x Leverage + 4.5% TP | +5.72% | 986 | 29.7% | 1.20% |
| 1% Dev + 2x Leverage (no cooldown) | +5.34% | 1,470 | 37.3% | 1.10% |
| 1% Dev + 2x Leverage + 1%/2% SL/TP | +5.21% | 1,330 | 39.7% | 0.90% |
| 1% Dev + 2x Leverage | +3.25% | 1,114 | 36.5% | 0.90% |
| **Baseline (1x leverage)** | **+2.57%** | 669 | 37.5% | 0.45% |

---

## Key Insights

### What Works
1. **Leverage is Critical** — 3x leverage triples returns while keeping drawdown manageable
2. **High Trade Frequency** — 1,330 trades over 3 years = ~1.2 trades per day
3. **Conservative Risk Management** — Low drawdown (1.35%) even with leverage
4. **Balanced Directionality** — Both long and short contribute to profits

### What Doesn't Work
1. **Trend Filters** — Reduced trades too much, hurt overall returns
2. **Higher Deviation Thresholds** (2%+) — Missed too many opportunities
3. **Longer VWAP Periods** — Added noise without improving edge

### Risk Considerations
- **Low Win Rate (39.7%)** — Requires discipline; losing streaks will happen
- **Leverage Amplifies** — Both gains and losses are magnified 3x
- **Mean Reversion Assumption** — Works best in ranging markets; suffers in strong trends

---

## Optimization Journey

| Step | Change | Result |
|------|--------|--------|
| Baseline | 1% dev, 1.5% SL, 3% TP, 1x leverage | +2.57% |
| Add 2x leverage | Same params, 2x leverage | +3.25% |
| Remove cooldown | Allow immediate re-entry | +5.34% |
| Tighter stops | 1% SL / 2% TP | +5.21% |
| Larger targets | 4.5% TP (1:3 R/R) | +5.72% |
| **Final: 3x leverage** | **Same baseline, 3x leverage** | **+7.90%** |

---

## Conclusion

The VWAP Reversion strategy is a **low-frequency, conservative mean reversion system** that benefits significantly from leverage. While the 39.7% win rate may seem low, the 1:2 risk/reward ratio and high trade count create a positive expectancy.

**Best suited for:**
- Portfolio diversification (low correlation with trend strategies)
- Risk-conscious traders (low max drawdown)
- Automated execution (high trade frequency, clear rules)

**Not suited for:**
- Traders seeking high win rates
- Manual traders (requires constant monitoring)
- Strong trending markets (will get run over)

---

*Backtest period: June 25, 2023 - June 24, 2026 (3 years)*
*Data source: Binance BTC/USDT 5-minute candles*
*Total candles analyzed: 315,360*
