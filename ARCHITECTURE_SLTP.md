# SL/TP Architecture - Native HyperLiquid Trigger Orders

## Overview
The trading system now places Stop Loss (SL) and Take Profit (TP) orders as native HyperLiquid trigger orders instead of monitoring prices locally.

## Key Components

### 1. Trade Dataclass (`trade_executor.py`)
```python
@dataclass
class Trade:
    # ... existing fields ...
    order_id: Optional[str] = None          # Entry order ID
    sl_order_id: Optional[str] = None       # SL trigger order ID
    tp_order_ids: list = None               # List of TP trigger order IDs
    # Timing and metadata
    signal_time: Optional[str] = None       # When signal was generated
    order_placed_time: Optional[str] = None # When orders placed on HyperLiquid
```

### 2. HyperliquidClient Methods

#### `place_trigger_order()`
Places SL or TP trigger orders on HyperLiquid:
```python
def place_trigger_order(self, coin: str, is_buy: bool, sz: float, 
                       trigger_px: float, limit_px: float,
                       tpsl: str = 'sl', is_market: bool = True,
                       reduce_only: bool = True) -> Dict:
```
- `tpsl`: 'sl' for stop loss, 'tp' for take profit
- `trigger_px`: Price that triggers the order
- `is_market`: Execute as market order when triggered
- `reduce_only`: Only reduces position (safety)

#### `cancel_order()`
Cancels an order by OID:
```python
def cancel_order(self, coin: str, oid: int) -> Dict:
```

### 3. TradeExecutor Methods

#### `open_position_real()`
Now places entry + SL + TP orders together:
```python
def open_position_real(self, symbol: str, side: str, sz: float, 
                      limit_px: Optional[float] = None,
                      order_type: str = "Market",
                      stop_loss: Optional[float] = None,
                      take_profits: Optional[list] = None) -> Dict:
```
Returns:
```python
{
    'entry': <entry_order_response>,
    'entry_oid': <entry_order_id>,
    'sl_oid': <sl_order_id>,
    'tp_oids': [<tp1_oid>, <tp2_oid>, ...]
}
```

#### `close_position_real()`
Cancels SL/TP trigger orders before closing position:
```python
def close_position_real(self, symbol: str, trade: Optional[Trade] = None) -> Dict:
```

#### `close_position()`
Cancels trigger orders when manually closing:
```python
def close_position(self, symbol: str, exit_price: Optional[float] = None, 
                   reason: str = "manual", cancel_trigger_orders: bool = True) -> Optional[Trade]:
```

#### `update_positions()`
Syncs local state with HyperLiquid:
- Gets current positions from HyperLiquid
- Detects positions closed by trigger orders
- Updates local trade state with exit price and reason
- Falls back to local SL/TP checking if trigger orders fail

### 4. Signal Flow

```
Signal Generated
       ↓
execute_signal()
       ↓
open_position() → Creates local Trade record
       ↓
open_position_real()
       ↓
├─ place_order() → Entry order
├─ place_trigger_order() → SL order (tpsl='sl')
└─ place_trigger_order() → TP order(s) (tpsl='tp')
       ↓
Store order IDs in Trade
       ↓
Save state to trade_state.json
```

### 5. Position Close Flow

#### Manual Close:
```
close_position() / close_position_real()
       ↓
├─ cancel_order() → Cancel SL order
├─ cancel_order() → Cancel TP order(s)
└─ place_order() → Close position
       ↓
Update local state
```

#### Trigger Close (SL/TP hit):
```
HyperLiquid executes trigger order
       ↓
update_positions() (next orchestrator run)
       ↓
├─ Get positions from HyperLiquid
├─ Detect missing position
├─ Get fill info
└─ close_position() → Sync local state
```

## Benefits

1. **Exchange-Managed**: SL/TP execute even if local system crashes
2. **Guaranteed Execution**: HyperLiquid handles trigger logic
3. **No Polling**: Don't need to monitor prices locally
4. **Professional**: Industry-standard approach

## Trade-offs

1. **Order Management**: Must track and cancel trigger orders
2. **Complexity**: More order IDs to manage
3. **Sync Required**: Must sync local state when triggers execute

## State Persistence

All order IDs and timing are persisted in `trade_state.json`:
```json
{
  "open_trades": {
    "SOL": {
      "order_id": "12345",
      "sl_order_id": "12346",
      "tp_order_ids": ["12347"],
      "stop_loss": 69.43,
      "take_profits": [{"price": 72.62, ...}],
      "signal_time": "2026-06-26T11:15:30.123456",
      "order_placed_time": "2026-06-26T11:15:32.456789",
      "entry_price": 70.50
    }
  }
}
```

## Position Display

### Console Output (`print_portfolio()`)
```
OPEN POSITIONS:
------------------------------------------------------------
SOL: LONG 3x | Signal: 11:15:30 | Order: 11:15:32
  Size: 1.0000 @ Entry: $70.50
  Notional: $70.50 | Margin: $23.50
  SL: $69.43 (1.5%) | TP: $72.62 (3.0%)
  HL Orders: Entry:12345 | SL:12346 | TP:12347
  Current: $71.20 (+0.99%) | Unrealized: +$0.70
------------------------------------------------------------
```

### Dashboard Table
The dashboard Open Positions table now includes:

| Column | Description |
|--------|-------------|
| Coin | Asset symbol |
| Side | LONG or SHORT |
| Size | Position size in coins |
| Leverage | Leverage used (e.g., 3x) |
| Signal | Time signal was generated |
| Order | Time order placed on HyperLiquid |
| Entry | Entry price |
| Mark | Current mark price |
| SL (%) | Stop loss price with % distance |
| TP (%) | Take profit price with % distance |
| PnL | Unrealized profit/loss |
| HL Orders | Visual badges (E=Entry, S=SL, T=TP) |

### Data Flow to Dashboard
1. `get_positions_for_dashboard.py` fetches positions from HyperLiquid
2. Merges with local `trade_state.json` for metadata
3. Returns enhanced JSON with timing and order IDs
4. Dashboard displays in enhanced table format

## Error Handling

1. **Entry order fails**: No SL/TP placed, trade not saved
2. **SL order fails**: Entry still open, logged as warning
3. **TP order fails**: Entry + SL still open, logged as warning
4. **Cancel fails**: Position still closed, warning logged

## Testing

To test the new SL/TP architecture:
```python
# Test placing a position with SL/TP
signal = {
    "coin": "SOL",
    "action": "BUY",
    "confidence": 0.9,
    "strategy": "test",
    "meta": {
        "price": 150.0,
        "stop_loss_pct": 1.5,
        "take_profit_pct": 3.0
    }
}
trade = execute_signal(signal, test_mode=False)
# Check trade_state.json for order IDs
```

## Migration Notes

- Old trades without `sl_order_id`/`tp_order_ids` will still work
- `update_positions()` falls back to local SL/TP checking
- New trades automatically get trigger orders
- No manual migration needed
