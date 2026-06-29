# Momentum Trend Following Strategy — FINAL CONFIG

## Timeframe & Execution

| Parameter | Value | Notes |
|-----------|-------|-------|
| Trading timeframe | 1-hour candles | Primary decision timeframe |
| Data granularity | 5-minute snapshots | For crossover detection |
| Execution cadence | Up to 24× per day | Every hour if conditions met |
| Candle gate | Enforced | Prevents duplicate signals within same hour |

## Asset Universe

- **BTC** — Bitcoin
- **ETH** — Ethereum  
- **SOL** — Solana

## Signal Logic (Confluence Setup)

### LONG Entry (BUY) requires BOTH:

| Indicator | Threshold | Purpose |
|-----------|-----------|---------|
| Momentum | ≥ +0.1% | Confirms upward acceleration (relaxed from 2.0%) |
| 24h Change | ≥ +0.2% | Confirms uptrend context (relaxed from 1.5%) |

### SHORT Entry (SELL) requires BOTH:

| Indicator | Threshold | Purpose |
|-----------|-----------|---------|
| Momentum | ≤ -0.1% | Confirms downward acceleration (relaxed from -2.0%) |
| 24h Change | ≤ -0.2% | Confirms downtrend context (relaxed from -1.5%) |

## Crossover Detection

- **Window:** Last 12 snapshots (~1 hour of 5-min data)
- **Bullish cross:** Momentum went negative → positive recently
- **Bearish cross:** Momentum went positive → negative recently
- **Bonus:** +20% confidence when crossover aligns with signal direction

## Sub-Threshold "Lean" Signals

| Condition | Range | Purpose |
|-----------|-------|---------|
| Bullish lean | +0.05% ≤ momentum < +0.1% | Track weak bullish bias |
| Bearish lean | -0.1% < momentum ≤ -0.05% | Track weak bearish bias |

## Backtest Performance (Mar 27 - Jun 15, 2026)

| Metric | Value |
|--------|-------|
| Starting Balance | $1,000.00 |
| Ending Balance | $1,231.20 |
| Total Return | +23.12% |
| Total Trades | 41 |
| Win Rate | 43.9% |
| Max Drawdown | $181.05 |

### Per-Token Results:
- **BTC**: 12 trades → -$43.12
- **ETH**: 14 trades → -$16.11
- **SOL**: 15 trades → +$366.79 (carried the portfolio)

## Live Trading Parameters

| Setting | Value |
|---------|-------|
| Leverage | 3x |
| Position sizing | ~33% per coin (equal weight) |
| Trading fee | 0.1% per trade |
| Max hold time | 2 hours (exit if no opposite signal) |

## Strategy Code Location

D:\dev\trading\strategy_momentum.py

---

Last updated: June 15, 2026
