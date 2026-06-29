# Trading System Architecture

Complete flow from data ingestion to trade execution on HyperLiquid testnet.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           TRADING SYSTEM ARCHITECTURE                            │
└─────────────────────────────────────────────────────────────────────────────────┘

  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │   Database   │────▶│  Strategies  │────▶│ Orchestrator │────▶│   Executor   │
  │  (Postgres)  │     │   (10 total) │     │   (Quorum)   │     │(HyperLiquid) │
  └──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
         │                    │                    │                    │
         │                    │                    │                    │
    candle_collector      Individual          SignalIntegrator      Agent Wallet
    (price data)          signals             (filter/logic)        (signs txs)
                                               │
                                               ▼
                                        ┌──────────────┐
                                        │  SL/TP Orders│
                                        │  (Triggers)  │
                                        └──────────────┘
```

## File Structure

### Core Trading Flow Files

| File | Purpose | Called By |
|------|---------|-----------|
| `orchestrator.py` | Main entry point, runs all strategies, aggregates signals, executes trades | Cron job every 5 minutes |
| `signal_integrator.py` | Filters signals (cooldown, strategy check), executes via TradeExecutor | orchestrator.py |
| `trade_executor.py` | Places orders on HyperLiquid, manages SL/TP, tracks positions | signal_integrator.py |
| `candle_gate.py` | Prevents duplicate signals within same candle | orchestrator.py, strategies |
| `db.py` | Database connection, fetch price data, save signals | All strategies, orchestrator |

### Strategy Files (10 Strategies)

| File | Timeframe | Style | Type |
|------|-----------|-------|------|
| `strategy_rsi.py` | 4h | swing | mean_reversion |
| `strategy_momentum.py` | 1h | swing | trend_following |
| `strategy_fvg.py` | 5min | scalp | mean_reversion |
| `strategy_volume.py` | 5min | scalp | breakout |
| `strategy_trend_breakout.py` | 4h | swing | trend_following |
| `strategy_mean_reversion.py` | 4h | swing | mean_reversion |
| `strategy_momentum_accel.py` | 1h | swing | momentum |
| `strategy_vwap_reversion.py` | 5min | scalp | mean_reversion |
| `strategy_momentum_scalper.py` | 5min | scalp | momentum |
| `strategy_pullback_scalper.py` | 5min | scalp | mean_reversion |

### Configuration & State Files

| File | Purpose | Managed By |
|------|---------|------------|
| `.account_settings.json` | cooldownMinutes, allowMultiplePositions | Dashboard |
| `.strategy_state.json` | Enable/disable individual strategies | Dashboard |
| `.candle_gate.json` | Tracks which candles have been processed | candle_gate.py |
| `trade_state.json` | Open positions, trade history | trade_executor.py |
| `signal_trade_history.json` | Signal-based trade history | signal_integrator.py |
| `risk_config.json` | Risk parameters per strategy | Manual/Dashboard |

### Supporting Modules

| File | Purpose |
|------|---------|
| `strategy_registry.py` | Discovers and lists all strategies for dashboard |
| `strategy_base.py` | Base class for class-based strategies |
| `strategy_risk_config.py` | Risk parameters (SL/TP %) per strategy |

---

## Detailed Flow

### 1. Data Layer (Database)

**File:** `db.py`

**Purpose:** Stores price data and signals

**Tables:**
- `trading_prices` - 5min OHLCV data
- `trading_prices_1h` - 1h OHLCV data  
- `trading_prices_4h` - 4h OHLCV data
- `trading_signals` - All generated signals
- `strategy_signals` - Individual strategy signals

**Key Functions:**
```python
fetch_recent(conn, coin, limit, timeframe)  # Gets price data for strategies
signal_envelope(strategy, coin, action, confidence, reason, extra)  # Creates signal dict
save_signal(conn, signal, table)  # Saves signal to DB
```

**Called by:** All strategies, orchestrator.py

---

### 2. Strategy Layer (Individual Strategies)

**Files:** `strategy_*.py` (10 files)

**Purpose:** Analyze price data and generate BUY/SELL/HOLD signals

**Flow:**
1. Strategy called by orchestrator with `coin`, `conn`, `candle_start`, `timeframe`
2. Fetches recent price data via `fetch_recent()`
3. Runs technical analysis (RSI, momentum, FVG, etc.)
4. Returns signal via `signal_envelope()`:
   ```python
   {
     "strategy": "momentum_accel",
     "coin": "SOL",
     "action": "BUY",  # or "SELL" or "HOLD"
     "confidence": 0.76,  # 0-1
     "reason": "Momentum accelerating...",
     "meta": {
       "price": 72.5,
       "stop_loss_pct": 2.5,
       "take_profit_pct": 5.0,
       "strategy_type": "momentum",
       "strategy_style": "swing"
     },
     "generated_at": "2026-06-26T21:03:02+00:00"
   }
   ```

**Called by:** orchestrator.py (once per coin per strategy)

---

### 3. Orchestration Layer (Quorum & Execution)

**File:** `orchestrator.py`

**Purpose:** Runs all strategies, aggregates signals, executes trades

**Flow:**

```
1. CRON triggers every 5 minutes
   │
2. Check candle gate
   │── should_act(ORCHESTRATOR_STRATEGY, 5min)
   │── If already acted this candle → exit
   │
3. For each coin (BTC, ETH, SOL):
   │
   ├── For each enabled strategy:
   │   ├── run_strategy(name, config, coin, conn, candle_start)
   │   ├── Returns individual signal
   │   ├── Save to DB (trading_signals table)
   │   ├── If BUY/SELL with confidence >= 0.50:
   │   │   └── Add to signals_for_execution[]
   │   └── Add to all_results[]
   │
   ├── Generate aggregated signal (for dashboard only)
   │   └── analyse(coin, conn, candle_start)
   │   └── Uses aggregate_signals() for quorum logic
   │   └── Save to DB
   │
4. Mark candle as acted
   └── mark_acted(ORCHESTRATOR_STRATEGY, candle_start)
   │
5. Execute trades
   └── If signals_for_execution not empty:
       ├── Create SignalIntegrator
       ├── integrator.check_and_manage_positions()
       └── For each signal:
           └── integrator.process_signal(signal, dry_run=False)
```

**Key Configuration:**
- `MIN_CONFIDENCE = 0.50` - Minimum confidence to execute
- `QUORUM_PCT = 0.50` - 50% of strategies must agree for aggregated signal
- `CANDLE_MINUTES = 5` - Runs every 5 minutes

**Account Settings (from .account_settings.json):**
- `cooldown_minutes` - Time between trades on same coin (default: 30)
- `allow_multiple_positions` - Allow multiple positions per coin (default: false)

**Called by:** Cron job every 5 minutes

**Calls:** All strategies, signal_integrator.py, db.py, candle_gate.py

---

### 4. Signal Integration Layer (Filtering & Logic)

**File:** `signal_integrator.py`

**Purpose:** Filters signals and executes trades via TradeExecutor

**Flow:**

```
process_signal(signal, dry_run=False)
│
├── 1. Validate signal
│   ├── Check strategy in ALLOWED_STRATEGIES list
│   └── Check confidence >= min_confidence
│
├── 2. Check cooldown
│   └── is_in_cooldown(coin)
│       └── Checks signal_trade_history.json
│       └── Returns True if last trade was < cooldown_minutes ago
│
├── 3. Check existing positions (STRATEGY-AWARE)
│   ├── If coin in open_trades:
│   │   ├── Get existing strategy from trade
│   │   ├── If existing_strategy == new_strategy:
│   │   │   └── SKIP (same strategy)
│   │   └── Else:
│   │       └── ALLOW (different strategy)
│   └── Else:
│       └── ALLOW (no existing position)
│
├── 4. Execute trade (if not dry_run)
│   └── execute_signal(signal, risk_config, test_mode)
│       └── Calls TradeExecutor.open_position()
│
└── 5. Record trade
    └── Add to signal_trade_history.json
```

**Key Logic:**
```python
# Strategy-aware position check
existing_strategy = existing_trade.get('strategy')
strategy = signal.get('strategy')

if existing_strategy == strategy:
    logger.info(f"Already have position in {symbol} from '{strategy}', skipping")
    return None  # SKIP
else:
    logger.info(f"Have position from '{existing_strategy}', new signal from '{strategy}' - allowing")
    # ALLOW - continue to execute
```

**Called by:** orchestrator.py

**Calls:** trade_executor.py

---

### 5. Trade Execution Layer (HyperLiquid)

**File:** `trade_executor.py`

**Purpose:** Places actual orders on HyperLiquid testnet

**Flow:**

```
open_position(symbol, side, entry_price, confidence, stop_loss_pct, take_profit_pct, signal_time, strategy)
│
├── 1. Calculate position size
│   ├── Get account balance from HyperLiquid
│   ├── Apply risk_per_trade_pct (default 2%)
│   ├── Apply leverage (default 3x)
│   └── Calculate: position_size = (balance * risk_pct * leverage) / (entry_price * stop_loss_pct)
│
├── 2. Check if can open position
│   └── can_open_position(symbol, margin_required, strategy)
│       ├── Check existing position strategy (if same → reject)
│       ├── Check max_open_positions limit
│       └── Check available margin
│
├── 3. Place entry order
│   └── _place_entry_order(symbol, side, size, price)
│       ├── Uses HyperLiquid SDK (Exchange class)
│       ├── Agent wallet signs (0x89823A4f85cc8ef3A5574E8a56741A7b4562f288)
│       ├── Trades on behalf of main wallet (0x97c465489243175580fcde624c2ef640c1897a00)
│       └── Order type: {"limit": {"tif": "Ioc"}} (market-like with slippage)
│
├── 4. Place Stop Loss (trigger order)
│   └── _place_stop_loss(symbol, side, size, trigger_price)
│       └── Order type: {"trigger": {"triggerPx": price, "isMarket": true, "tpsl": "sl"}}
│
├── 5. Place Take Profit (trigger order)
│   └── _place_take_profit(symbol, side, size, trigger_price)
│       └── Order type: {"trigger": {"triggerPx": price, "isMarket": true, "tpsl": "tp"}}
│
├── 6. Record trade
│   └── Create Trade object with strategy metadata
│   └── Save to open_trades dict
│   └── Save to trade_state.json
│
└── 7. Return result
    └── {entry_oid, sl_oid, tp_oids, trade_id}
```

**Key Classes:**
```python
@dataclass
class Trade:
    symbol: str
    side: str
    entry_price: float
    position_size: float
    margin_required: float
    stop_loss: float
    take_profit: float
    strategy: Optional[str] = None  # NEW: Tracks which strategy opened this trade
    ...

@dataclass
class RiskConfig:
    initial_capital: float = 1000.0
    risk_per_trade_pct: float = 0.02  # 2% risk
    stop_loss_pct: float = 0.05       # 5% SL (overridden by strategy)
    take_profit_levels: list = None   # TP levels (overridden by strategy)
    leverage: float = 3.0             # 3x leverage
    max_open_positions: int = 3
    ...
```

**Wallet Setup:**
- **Agent Wallet:** 0x89823A4f85cc8ef3A5574E8a56741A7b4562f288 (signs transactions)
- **Main Wallet:** 0x97c465489243175580fcde624c2ef640c1897a00 (holds funds, receives trades)
- Uses HyperLiquid SDK's `account_address` parameter for agent wallet delegation

**Called by:** signal_integrator.py

**Calls:** HyperLiquid API (testnet)

---

### 6. Candle Gate (Deduplication)

**File:** `candle_gate.py`

**Purpose:** Prevents strategies from firing multiple times within the same candle

**Flow:**
```python
# In orchestrator.py:
act, candle_start = should_act(ORCHESTRATOR_STRATEGY, 5)
if not act:
    return  # Already acted this candle

# ... run strategies ...

mark_acted(ORCHESTRATOR_STRATEGY, candle_start)
```

**Storage:** `.candle_gate.json`
```json
{
  "quorum_view": "2026-06-26T21:05:00+00:00"
}
```

**Called by:** orchestrator.py, individual strategies

---

## Data Flow Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA FLOW                                       │
└─────────────────────────────────────────────────────────────────────────────┘

  Price Data                    Signals                      Trades
  ──────────                    ───────                      ──────
  
  candle_collector              orchestrator                 trade_executor
       │                             │                            │
       ▼                             ▼                            ▼
  ┌─────────┐                  ┌─────────┐                   ┌─────────┐
  │ Postgres│                  │  JSON   │                   │HyperLiquid
  │  OHLCV  │                  │ Signals │                   │ Testnet │
  │ Tables  │                  │  (DB)   │                   │         │
  └────┬────┘                  └────┬────┘                   └────┬────┘
       │                            │                             │
       │         ┌──────────┐       │                             │
       └────────▶│ Strategies│◀─────┘                             │
                 │ (10 total)│                                    │
                 └────┬─────┘                                    │
                      │                                          │
                      └──────────────────────────────────────────▶
                                                                   │
                              ┌──────────────┐                     │
                              │SignalIntegrator                    │
                              │  (filter)    │─────────────────────┘
                              └──────────────┘
                                     │
                                     ▼
                              ┌──────────────┐
                              │ Trade State  │
                              │  (JSON files)│
                              └──────────────┘
```

---

## Key Design Decisions

### 1. Strategy-Aware Position Filtering

**Problem:** Original code skipped ALL signals if ANY position existed for that coin.

**Solution:** Now checks if the existing position's strategy matches the new signal's strategy:
- Same strategy → Skip (prevent duplicate signals from same strategy)
- Different strategy → Allow (diversification across strategies)

**Files changed:** `signal_integrator.py`, `trade_executor.py`

### 2. Individual Strategy Execution (Not Quorum)

**Problem:** Original code only executed aggregated quorum signals.

**Solution:** Each individual strategy signal that meets confidence threshold is executed independently.

**Benefit:** Faster response to individual strategy opportunities.

### 3. Agent Wallet Delegation

**Problem:** Main wallet private key shouldn't be exposed.

**Solution:** Agent wallet signs transactions on behalf of main wallet using HyperLiquid's delegation feature.

**Implementation:**
```python
exchange = Exchange(agent_wallet, base_url=..., account_address=MAIN_WALLET)
```

### 4. Strategy-Specific Risk Parameters

**Problem:** All strategies used same SL/TP percentages.

**Solution:** Each strategy provides its own SL/TP from backtesting via `strategy_risk_config.py`.

**Fallback:** If strategy doesn't provide SL/TP, uses config defaults.

---

## Cron Schedule

```bash
# Every 5 minutes at :03, :08, :13, etc.
# Offset by 3 minutes to ensure candle is closed
3-59/5 * * * * cd D:\dev\trading && python orchestrator.py >> orchestrator.log 2>&1
```

---

## State Files Location

All state files are in `D:\dev\trading\`:
- `.account_settings.json` - Account configuration
- `.strategy_state.json` - Strategy enable/disable
- `.candle_gate.json` - Candle processing tracking
- `trade_state.json` - Open positions and history
- `signal_trade_history.json` - Signal-based trade history
- `orchestrator.log` - Runtime logs
- `trade_executor.log` - Trade execution logs

---

## Debugging Commands

```powershell
# Check recent orchestrator output
cd D:\dev\trading; Get-Content orchestrator.log -Tail 50

# Check trade state
python -c "import json; print(json.dumps(json.load(open('trade_state.json')), indent=2))"

# Check open positions on HyperLiquid
python check_positions_main.py

# Check open orders
python check_orders.py

# Test signal processing
python test_signal_now.py

# Verify cooldown status
python verify_cooldown.py
```
