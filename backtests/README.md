# Backtesting Framework

Unified backtesting system for trading strategies with consistent parameters.

## Standard Parameters

All backtests use these consistent settings:

| Parameter | Value | Description |
|-----------|-------|-------------|
| Initial Capital | $1,000 | Starting portfolio value |
| Risk Per Trade | 2% | Maximum risk per position |
| Leverage | 3x | Position leverage |
| Commission | 0.035% | HyperLiquid taker fee (entry + exit) |
| Slippage | 0.05% | Estimated execution slippage |

## Files

| File | Purpose |
|------|---------|
| `backtest_engine.py` | Core backtesting engine |
| `run_backtest.py` | Simple CLI runner with built-in strategies |

## Usage

### Quick Backtest

```bash
cd D:\dev\trading\backtests

# FVG strategy on BTC 15m
python run_backtest.py --strategy fvg --coin BTC --timeframe 15m

# Momentum strategy on SOL 5m
python run_backtest.py --strategy momentum --coin SOL --timeframe 5m

# Mean reversion on ETH, last 30 days only
python run_backtest.py --strategy mean_reversion --coin ETH --timeframe 15m --days 30
```

### Save Results

```bash
python run_backtest.py --strategy fvg --coin BTC --timeframe 15m --output results.json
```

### Custom Risk Parameters

```bash
# 1% risk, 5x leverage
python run_backtest.py --strategy momentum --coin SOL --timeframe 5m --risk 0.01 --leverage 5
```

## Available Strategies

| Strategy | Description |
|----------|-------------|
| `fvg` | Fair Value Gap detection |
| `momentum` | 3-candle momentum |
| `mean_reversion` | RSI-like overbought/oversold |

## Data Source

Backtests use Binance OHLCV data from `D:\dev\trading\data\`:
- Format: `binance_{coin}_{timeframe}_{date}.csv`
- Automatically loads most recent file

## Output Metrics

- **Total Return**: Overall portfolio return %
- **Win Rate**: Percentage of winning trades
- **Profit Factor**: Gross profit / gross loss
- **Max Drawdown**: Largest peak-to-trough decline
- **Sharpe Ratio**: Risk-adjusted return (if calculated)

## Extending

To add a new strategy, edit `run_backtest.py`:

```python
def my_strategy(candles, idx):
    # Your logic here
    if condition_met:
        return {
            'action': 'BUY',  # or 'SELL'
            'entry': candles[idx]['close'],
            'stop_loss': ...,  # Your SL price
            'take_profit': ...,  # Your TP price
            'strategy': 'my_strategy'
        }
    return None

STRATEGIES['my_strategy'] = my_strategy
```
