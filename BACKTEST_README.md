# Backtesting Engine for Reuben's Trading Signals

A reusable Python backtesting framework for testing trading strategies on historical data from the PostgreSQL database.

## Features

- **Portfolio Management**: $1000 starting capital, 2% risk per trade
- **Position Sizing**: Automatically calculated based on stop loss distance
- **Trade Management**: Configurable stop loss and take profit levels
- **Multiple Signal Sources**: RSI, momentum, FVG (Fair Value Gaps), alerts
- **Risk Metrics**: Win rate, profit factor, max drawdown, Sharpe ratio
- **Equity Curve**: Track portfolio value over time
- **Detailed Trade Log**: Entry/exit prices, P&L, exit reasons

## Database Schema

The backtester uses the following tables:
- `trading_prices` - 5-minute OHLCV + indicator data
- `trading_prices_1h` - 1-hour aggregated data
- `trading_prices_4h` - 4-hour aggregated data

Each table contains:
- `captured_at` - Timestamp
- `coin` - Symbol (BTC, ETH, SOL)
- `price` - Current price
- `rsi` - RSI indicator value
- `momentum` - Momentum indicator
- `fvg_count` - Fair Value Gap count
- `alert_triggered` - Boolean for alert signals

## Usage

### Basic Run

Run a backtest with default settings:
```bash
python backtest.py
```

### Generate More Trades

Use the `--more-trades` flag to lower thresholds and increase trade volume:
```bash
python backtest.py --more-trades --start-date 2026-05-01
```

### RSI-Based Signals

Backtest RSI oversold conditions:
```bash
python backtest.py --rsi-threshold 35 --stop-loss-pct 0.03 --risk-reward 2.5
```

### Momentum Signals

Backtest momentum-based entries:
```bash
python backtest.py --momentum-threshold 0.5 --timeframe 1h
```

### Alert-Based Signals

Use only alert-triggered signals:
```bash
python backtest.py --use-alerts --min-fvg 1
```

### Specific Coins

Test on specific cryptocurrencies:
```bash
python backtest.py --coins BTC,ETH --timeframe 4h
```

### Custom Period

Specify date range:
```bash
python backtest.py --start-date 2026-01-01 --end-date 2026-06-14
```

### JSON Config

Use a configuration file:
```bash
python backtest.py --config my_config.json
```

Example `my_config.json`:
```json
{
  "start_date": "2026-05-01",
  "end_date": "2026-06-14",
  "timeframe": "1h",
  "rsi_threshold": 30,
  "stop_loss_pct": 0.04,
  "risk_reward": 2.0,
  "capital": 1000,
  "risk_per_trade": 0.02,
  "coins": ["BTC", "ETH"]
}
```

## Command-Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `--start-date` | 30 days ago | Backtest start date (YYYY-MM-DD) |
| `--end-date` | Today | Backtest end date (YYYY-MM-DD) |
| `--timeframe` | 5min | Data timeframe: 5min, 1h, 4h |
| `--stop-loss-pct` | 0.05 | Stop loss as decimal (0.05 = 5%) |
| `--risk-reward` | 2.0 | Risk/reward ratio |
| `--rsi-threshold` | None | RSI buy threshold (buy when RSI < threshold) |
| `--momentum-threshold` | None | Minimum momentum for signals |
| `--use-alerts` | False | Use alert_triggered column |
| `--min-fvg` | 0 | Minimum FVG count for signals |
| `--coins` | BTC,ETH,SOL | Comma-separated coin list |
| `--capital` | 1000 | Initial portfolio capital |
| `--risk-per-trade` | 0.02 | Risk per trade (0.02 = 2%) |
| `--output-dir` | results/ | Directory for result files |
| `--more-trades` | False | Lower thresholds for more signals |
| `--config` | None | Path to JSON config file |

## Output

Results are saved to `results/backtest_YYYYMMDD_HHMMSS.json` containing:

- **Portfolio metrics**: Initial/final capital, total return, P&L
- **Trade statistics**: Total trades, win rate, avg win/loss
- **Risk metrics**: Max drawdown, Sharpe ratio, profit factor
- **Equity curve**: Portfolio value at each trade
- **Trade log**: Detailed entry/exit data for every trade

## Example Output

```
============================================================
BACKTEST RESULTS
============================================================
Period: 2026-05-01 to 2026-06-14

Portfolio Performance:
  Initial Capital: $1,000.00
  Final Capital:   $1,245.67
  Total P&L:       $245.67
  Total Return:    +24.57%

Trade Statistics:
  Total Trades:    42
  Win Rate:        57.1%
  Winning Trades:  24
  Losing Trades:   18
  Avg Win:         $28.45
  Avg Loss:        $-12.33
  Profit Factor:   1.83

Risk Metrics:
  Max Drawdown:    8.45%
  Sharpe Ratio:    1.24
============================================================

Results saved to: results/backtest_20260614_202233.json
```

## Extending the Backtester

To add new signal types, modify the `get_signals()` method in `DatabaseConnector` class.

To add new metrics, extend the `BacktestResult` dataclass and update calculations in `run_backtest()`.

## Notes

- Trades are executed at the signal price
- Stop loss and take profit are checked on each subsequent price bar
- No slippage or commission is currently modeled (can be added)
- Only one open position per symbol at a time
