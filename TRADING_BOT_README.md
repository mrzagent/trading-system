# Trading Bot - Hyperliquid Testnet

Automated trading system with risk management for Hyperliquid testnet.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Signal Generator │────▶│ Signal Integrator │────▶│ Trade Executor  │
│ (Your existing)  │     │ (New)              │     │ (New)           │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                              ┌─────────────────┐
                                              │ Hyperliquid     │
                                              │ Testnet API     │
                                              └─────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `trade_executor.py` | Core trade execution with risk management |
| `signal_integrator.py` | Connects signals to executor |
| `trading_bot.py` | Main entry point with CLI |
| `risk_config.json` | Your risk parameters (auto-created) |

## Quick Start

### 1. Initialize Configuration

```bash
cd D:\dev\trading
python trading_bot.py init
```

This creates:
- `risk_config.json` - Your risk parameters
- `signals/example_signal.json` - Signal format example

### 2. Review Risk Configuration

Edit `risk_config.json`:

```json
{
  "initial_capital": 1000.0,
  "risk_per_trade_pct": 0.02,
  "stop_loss_pct": 0.05,
  "take_profit_pct": 0.10,
  "max_position_pct": 0.50,
  "max_open_positions": 3,
  "commission_pct": 0.001,
  "slippage_pct": 0.0005
}
```

**With $1,000 and these settings:**
- Risk per trade: $20 (2%)
- Position size: ~$400 ($20 ÷ 5% stop)
- Stop loss: 5%
- Take profit: 10% (2:1 R:R)
- Max concurrent positions: 3

### 3. Test the System

```bash
# Check status
python trading_bot.py status

# Test with a signal file
python trading_bot.py run --signal signals/fvg_2026-06-14_1629.json --dry-run
```

### 4. Run Paper Trading

```bash
# Run one cycle
python trading_bot.py run --signal signals/fvg_2026-06-14_1629.json

# Run as daemon (checks every 5 minutes)
python trading_bot.py daemon --interval 5
```

## Signal Format

Signals should be JSON with this structure:

```json
{
  "strategy": "fvg_proximity",
  "coin": "BTC",
  "action": "BUY",
  "confidence": 0.85,
  "reason": "Price near bullish FVG",
  "meta": {
    "price": 64127.0,
    "fvg": {
      "type": "bullish",
      "midpoint": 64101.42
    }
  },
  "generated_at": "2026-06-14T16:29:46Z"
}
```

**Action values:** `BUY` (long), `SELL` (short), `HOLD` (ignore)

**Confidence:** 0.0 to 1.0 (affects position sizing)

## Risk Management Features

### Position Sizing
- Fixed fractional risk (e.g., 2% per trade)
- Adjusted by signal confidence
- Respects max position limits

### Exit Management
- Automatic stop-loss execution
- Automatic take-profit execution
- Tracks all trades in `trade_state.json`

### Safety Features
- Cooldown period between trades on same coin (default: 60 min)
- Minimum confidence threshold (default: 0.7)
- Max open positions limit
- Test mode by default (paper trading)

## Integration with Your Signal System

To connect your existing signal generation:

1. **Write signals to a file:**
```python
import json
from datetime import datetime

signal = {
    "coin": "BTC",
    "action": "BUY",
    "confidence": 0.85,
    "strategy": "fvg_proximity",
    "meta": {"price": current_price},
    "generated_at": datetime.now().isoformat()
}

with open(f'signals/signal_{datetime.now():%Y%m%d_%H%M%S}.json', 'w') as f:
    json.dump([signal], f)
```

2. **Or call directly in Python:**
```python
from signal_integrator import SignalIntegrator

integrator = SignalIntegrator(test_mode=True)
integrator.process_signal(signal)
```

## CLI Reference

```bash
# Initialize configs
python trading_bot.py init

# Check status
python trading_bot.py status

# Run one cycle
python trading_bot.py run [--signal FILE] [--config CONFIG] [--dry-run]

# Run daemon
python trading_bot.py daemon [--interval MINUTES] [--signal-dir DIR]

# Live trading (when ready)
python trading_bot.py run --live
```

## State Files

The bot maintains state in these files:

- `trade_state.json` - Open positions and trade history
- `signal_trade_history.json` - History of signal-based trades
- `trading_bot.log` - Detailed logs
- `trade_executor.log` - Execution logs

## Moving to Live Trading

⚠️ **Only proceed when:**
- [ ] Paper trading shows consistent profitability
- [ ] You understand all risk parameters
- [ ] You have a Hyperliquid mainnet account
- [ ] You've set environment variables:
  ```bash
  set HYPERLIQUID_WALLET=your_wallet_address
  set HYPERLIQUID_PRIVATE_KEY=your_private_key
  ```

Then run:
```bash
python trading_bot.py run --live
```

## Monitoring

Check logs:
```bash
tail -f trading_bot.log
tail -f trade_executor.log
```

View portfolio:
```bash
python trading_bot.py status
```

## Next Steps

1. ✅ Review the risk parameters in `risk_config.json`
2. ✅ Run `python trading_bot.py init`
3. ✅ Test with `python trading_bot.py status`
4. ✅ Run a dry-run: `python trading_bot.py run --dry-run`
5. ✅ Start paper trading: `python trading_bot.py daemon --interval 5`
