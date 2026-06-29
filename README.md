# Trading System

Automated crypto trading system with 10 strategies running on HyperLiquid testnet.

## Quick Start

```bash
# Run orchestrator (main entry point)
python orchestrator.py

# Check positions
python get_positions_for_dashboard.py

# Run backtest
python backtests/run_backtest.py --strategy fvg --coin BTC --timeframe 15m
```

## System Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Price Data     │────▶│   Strategies    │────▶│  Orchestrator   │
│  (Binance)      │     │    (10 total)   │     │  (Aggregates)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                                               │
         │                                               ▼
         │                                      ┌─────────────────┐
         │                                      │ Signal Integrator│
         │                                      │  (Filters/Exec)  │
         │                                      └─────────────────┘
         │                                               │
         ▼                                               ▼
┌─────────────────┐                           ┌─────────────────┐
│   PostgreSQL    │                           │  Trade Executor │
│   (signals)     │                           │  (HyperLiquid)  │
└─────────────────┘                           └─────────────────┘
```

## Folder Structure

```
D:\dev\trading\
├── strategies/              # 10 strategy implementations
│   ├── strategy_fvg.py
│   ├── strategy_mean_reversion.py
│   ├── strategy_momentum.py
│   ├── strategy_momentum_accel.py
│   ├── strategy_momentum_scalper.py
│   ├── strategy_pullback_scalper.py
│   ├── strategy_rsi.py
│   ├── strategy_trend_breakout.py
│   ├── strategy_volume.py
│   └── strategy_vwap_reversion.py
├── backtests/               # Backtesting framework
│   ├── backtest_engine.py
│   ├── run_backtest.py
│   └── README.md
├── data/                    # Binance OHLCV data
├── logs/                    # Strategy logs
├── signals/                 # Signal templates (example_signal.json)
├── results/                 # Backtest results (empty)
├── orchestrator.py          # Main entry point
├── signal_integrator.py     # Signal filtering & execution
├── trade_executor.py        # HyperLiquid order execution
├── candle_collector.py      # Price data collection
├── db.py                    # Database interface
├── candle_gate.py           # Candle timing gate
├── strategy_base.py         # Base strategy class
├── strategy_registry.py     # Strategy discovery
├── strategy_risk_config.py  # Risk parameters
├── get_positions_for_dashboard.py  # Dashboard API
├── get_account_info.py      # Account info
├── generate_trading_report.py      # Reporting
├── show_strategy_status.py  # Strategy status
├── fetch_binance_5min.py    # Data fetching
├── fetch_binance_historical.py
└── README.md                # This file
```

## Core Components

| Component | File | Purpose |
|-----------|------|---------|
| **Orchestrator** | `orchestrator.py` | Runs all 10 strategies, aggregates signals |
| **Signal Integrator** | `signal_integrator.py` | Filters signals, prevents stacking, executes trades |
| **Trade Executor** | `trade_executor.py` | Places orders on HyperLiquid, manages SL/TP |
| **Candle Collector** | `candle_collector.py` | Fetches price data from Binance |
| **Database** | `db.py` | PostgreSQL interface for signals and prices |

## Strategies (10 Total)

| Strategy | File | Timeframe | Style | Type |
|----------|------|-----------|-------|------|
| RSI Mean Reversion | `strategy_rsi.py` | 4h | swing | mean_reversion |
| Momentum RSI | `strategy_momentum.py` | 1h | swing | trend_following |
| FVG Proximity | `strategy_fvg.py` | 5min | scalp | mean_reversion |
| Volume Spike | `strategy_volume.py` | 5min | scalp | breakout |
| Trend Breakout | `strategy_trend_breakout.py` | 4h | swing | trend_following |
| Mean Reversion | `strategy_mean_reversion.py` | 4h | swing | mean_reversion |
| Momentum Acceleration | `strategy_momentum_accel.py` | 1h | swing | momentum |
| VWAP Reversion | `strategy_vwap_reversion.py` | 5min | scalp | mean_reversion |
| Momentum Scalper | `strategy_momentum_scalper.py` | 5min | scalp | momentum |
| Pullback Scalper | `strategy_pullback_scalper.py` | 5min | scalp | mean_reversion |

## Configuration Files

| File | Purpose | Managed By |
|------|---------|------------|
| `.account_settings.json` | Cooldown, position sizing, leverage | Dashboard |
| `.strategy_state.json` | Enable/disable strategies | Dashboard |
| `.candle_gate.json` | Candle processing tracking | System |
| `risk_config.json` | Risk parameters per strategy | Manual/Dashboard |
| `trade_state.json` | Open positions | System |
| `signal_trade_history.json` | Trade history | System |

## Account Settings

Default configuration in `.account_settings.json`:

```json
{
  "cooldownMinutes": 30,
  "allowMultiplePositions": false,
  "positionSizePct": 2.0,
  "leverage": 3,
  "stopLoss": 5.0,
  "takeProfit": 10.0
}
```

## Running the System

### Manual Run
```bash
cd D:\dev\trading\npython orchestrator.py\n```\n\n### Check Positions\n```bash\npython get_positions_for_dashboard.py\n```\n\n### Generate Report\n```bash\npython generate_trading_report.py
```

## Backtesting

```bash
cd D:\dev\trading\backtests\n\n# FVG strategy on BTC 15m\npython run_backtest.py --strategy fvg --coin BTC --timeframe 15m\n\n# Momentum on SOL 5m, last 30 days\npython run_backtest.py --strategy momentum --coin SOL --timeframe 5m --days 30

# Mean reversion with custom risk
python run_backtest.py --strategy mean_reversion --coin ETH --timeframe 15m --risk 0.01 --leverage 5
```

## Data Flow

1. **candle_collector.py** fetches OHLCV from Binance → saves to `data/`
2. **orchestrator.py** runs every 5 minutes via cron
3. Each strategy analyzes its timeframe and generates signals
4. **signal_integrator.py** filters signals (cooldown, position check)\5. **trade_executor.py** places orders on HyperLiquid testnet
6. SL/TP orders managed automatically

## Key Features

- **Position Stacking Prevention**: Won't open multiple same-direction positions for same strategy type
- **Cooldown**: 30 minutes between trades per coin
- **Risk Management**: 2% risk per trade, 3x leverage
- **SL/TP**: Automatic stop-loss and take-profit orders
- **Dashboard Integration**: API endpoints for position/status reporting

## Environment Variables

```bash
HYPERLIQUID_WALLET=0x...
HYPERLIQUID_PRIVATE_KEY=0x...
```

## Database

PostgreSQL with tables:
- `trading_prices` (5min OHLCV)
- `trading_prices_1h` (1h OHLCV)
- `trading_prices_4h` (4h OHLCV)
- `trading_signals` (all signals)

## Troubleshooting\n
**No signals generated?**
- Check `.candle_gate.json` for duplicate prevention
- Verify strategies enabled in `.strategy_state.json`

**Trades not executing?**
- Check `trade_state.json` for open positions
- Verify HyperLiquid credentials

**Position stacking?**
- Fixed in `signal_integrator.py` — queries actual HyperLiquid positions

## GitHub Repo

https://github.com/mrzagent/trading-system
