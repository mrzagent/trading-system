#!/usr/bin/env python3
"""
Backtest Momentum Acceleration Strategy using Binance 1-hour data.
3 years of BTC data with 3x leverage and SL/TP.
"""

import csv
from datetime import datetime

# Configuration
INITIAL_CAPITAL = 1000
POSITION_SIZE_PCT = 0.02  # 2% risk per trade
LEVERAGE = 3.0
STOP_LOSS_PCT = 1.5  # 1.5% stop loss
TAKE_PROFIT_PCT = 3.0  # 3% take profit (1:2 R/R)
MOM_PERIOD = 10  # Period for momentum calculation (ROC)
ACCEL_PERIOD = 5  # Period for acceleration calculation
MIN_ROWS = 20
MOM_THRESHOLD = 0.5  # Minimum momentum % to consider
ACCEL_THRESHOLD = 0.1  # Minimum acceleration to trigger

def calculate_roc(prices, period):
    """Calculate Rate of Change (momentum) as percentage."""
    if len(prices) < period + 1:
        return 0.0
    current = prices[-1]
    past = prices[-(period + 1)]
    return ((current - past) / past * 100) if past != 0 else 0.0

def calculate_acceleration(momentum_values):
    """Calculate acceleration as change in momentum."""
    if len(momentum_values) < 2:
        return 0.0
    return momentum_values[-1] - momentum_values[-2]

# Load Binance 1-hour data
print("Loading Binance BTC 1-hour data...")

data_file = 'D:/dev/trading/data/binance_btc_1h_2026-06-24.csv'

df = []
with open(data_file, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        open_price = float(row.get('open') or row.get('open_price') or 0)
        high_price = float(row.get('high') or row.get('high_price') or 0)
        low_price = float(row.get('low') or row.get('low_price') or 0)
        close_price = float(row.get('close') or row.get('close_price') or 0)
        volume = float(row.get('volume') or row.get('quote_volume') or 0)
        timestamp = row.get('timestamp') or row.get('open_time')
        
        df.append({
            'timestamp': timestamp,
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'volume': volume
        })

print(f"Loaded {len(df)} rows")
print(f"Date range: {df[0]['timestamp']} to {df[-1]['timestamp']}")

# Calculate momentum and acceleration
print("\nCalculating momentum and acceleration...")

for i in range(len(df)):
    if i < MOM_PERIOD + ACCEL_PERIOD:
        df[i]['momentum'] = 0.0
        df[i]['acceleration'] = 0.0
        df[i]['signal'] = 'HOLD'
        continue
    
    # Get closing prices up to current candle
    closes = [r['close'] for r in df[:i+1]]
    
    # Calculate momentum series for acceleration
    momentum_values = []
    for j in range(ACCEL_PERIOD + 1):
        if len(closes) >= MOM_PERIOD + j + 1:
            slice_prices = closes[:len(closes) - j] if j > 0 else closes
            roc = calculate_roc(slice_prices, MOM_PERIOD)
            momentum_values.insert(0, roc)
    
    if len(momentum_values) < 2:
        df[i]['momentum'] = 0.0
        df[i]['acceleration'] = 0.0
        df[i]['signal'] = 'HOLD'
        continue
    
    current_momentum = momentum_values[-1]
    acceleration = calculate_acceleration(momentum_values)
    
    df[i]['momentum'] = current_momentum
    df[i]['acceleration'] = acceleration
    
    # Generate signals
    if current_momentum > MOM_THRESHOLD and acceleration > ACCEL_THRESHOLD:
        df[i]['signal'] = 'BUY'
    elif current_momentum < -MOM_THRESHOLD and acceleration < -ACCEL_THRESHOLD:
        df[i]['signal'] = 'SELL'
    else:
        df[i]['signal'] = 'HOLD'

# Backtest simulation
print("\n" + "="*70)
print("MOMENTUM ACCELERATION BACKTEST")
print("="*70)
print(f"Configuration: 3x Leverage, {STOP_LOSS_PCT}% SL / {TAKE_PROFIT_PCT}% TP")

capital = INITIAL_CAPITAL
trades = []
position = None
cooldown_end = 0

for i in range(MIN_ROWS, len(df)):
    row = df[i]
    signal = row['signal']
    price = row['close']
    timestamp = row['timestamp']
    
    # Check if position should be closed (SL/TP)
    if position:
        entry_price = position['entry_price']
        direction = position['direction']
        
        # Calculate P&L with leverage
        if direction == 'LONG':
            pnl_pct = (price - entry_price) / entry_price * 100 * LEVERAGE
            # Check SL
            if pnl_pct <= -STOP_LOSS_PCT:
                trades.append({
                    'entry_time': position['entry_time'],
                    'exit_time': timestamp,
                    'direction': direction,
                    'entry_price': entry_price,
                    'exit_price': price,
                    'pnl_pct': -STOP_LOSS_PCT,
                    'result': 'LOSS',
                    'reason': 'STOP_LOSS',
                    'momentum': position.get('momentum', 0),
                    'acceleration': position.get('acceleration', 0)
                })
                capital *= (1 - POSITION_SIZE_PCT * STOP_LOSS_PCT / 100)
                position = None
                cooldown_end = i + 1  # 1 hour cooldown
                continue
            
            # Check TP
            if pnl_pct >= TAKE_PROFIT_PCT:
                trades.append({
                    'entry_time': position['entry_time'],
                    'exit_time': timestamp,
                    'direction': direction,
                    'entry_price': entry_price,
                    'exit_price': price,
                    'pnl_pct': TAKE_PROFIT_PCT,
                    'result': 'WIN',
                    'reason': 'TAKE_PROFIT',
                    'momentum': position.get('momentum', 0),
                    'acceleration': position.get('acceleration', 0)
                })
                capital *= (1 + POSITION_SIZE_PCT * TAKE_PROFIT_PCT / 100)
                position = None
                cooldown_end = i + 1
                continue
        
        else:  # SHORT
            pnl_pct = (entry_price - price) / entry_price * 100 * LEVERAGE
            # Check SL
            if pnl_pct <= -STOP_LOSS_PCT:
                trades.append({
                    'entry_time': position['entry_time'],
                    'exit_time': timestamp,
                    'direction': direction,
                    'entry_price': entry_price,
                    'exit_price': price,
                    'pnl_pct': -STOP_LOSS_PCT,
                    'result': 'LOSS',
                    'reason': 'STOP_LOSS',
                    'momentum': position.get('momentum', 0),
                    'acceleration': position.get('acceleration', 0)
                })
                capital *= (1 - POSITION_SIZE_PCT * STOP_LOSS_PCT / 100)
                position = None
                cooldown_end = i + 1
                continue
            
            # Check TP
            if pnl_pct >= TAKE_PROFIT_PCT:
                trades.append({
                    'entry_time': position['entry_time'],
                    'exit_time': timestamp,
                    'direction': direction,
                    'entry_price': entry_price,
                    'exit_price': price,
                    'pnl_pct': TAKE_PROFIT_PCT,
                    'result': 'WIN',
                    'reason': 'TAKE_PROFIT',
                    'momentum': position.get('momentum', 0),
                    'acceleration': position.get('acceleration', 0)
                })
                capital *= (1 + POSITION_SIZE_PCT * TAKE_PROFIT_PCT / 100)
                position = None
                cooldown_end = i + 1
                continue
    
    # Check for new entry
    if not position and i >= cooldown_end:
        if signal == 'BUY':
            position = {
                'direction': 'LONG',
                'entry_price': price,
                'entry_time': timestamp,
                'momentum': row['momentum'],
                'acceleration': row['acceleration']
            }
        elif signal == 'SELL':
            position = {
                'direction': 'SHORT',
                'entry_price': price,
                'entry_time': timestamp,
                'momentum': row['momentum'],
                'acceleration': row['acceleration']
            }

# Close any open position at the end
if position:
    final_price = df[-1]['close']
    entry_price = position['entry_price']
    direction = position['direction']
    
    if direction == 'LONG':
        pnl_pct = (final_price - entry_price) / entry_price * 100 * LEVERAGE
    else:
        pnl_pct = (entry_price - final_price) / entry_price * 100 * LEVERAGE
    
    trades.append({
        'entry_time': position['entry_time'],
        'exit_time': df[-1]['timestamp'],
        'direction': direction,
        'entry_price': entry_price,
        'exit_price': final_price,
        'pnl_pct': pnl_pct,
        'result': 'WIN' if pnl_pct > 0 else 'LOSS',
        'reason': 'FINAL_CLOSE',
        'momentum': position.get('momentum', 0),
        'acceleration': position.get('acceleration', 0)
    })
    capital *= (1 + POSITION_SIZE_PCT * pnl_pct / 100)

# Calculate statistics
if len(trades) > 0:
    winning_trades = sum(1 for t in trades if t['result'] == 'WIN')
    losing_trades = sum(1 for t in trades if t['result'] == 'LOSS')
    win_rate = (winning_trades / len(trades)) * 100
    
    wins = [t['pnl_pct'] for t in trades if t['pnl_pct'] > 0]
    losses = [t['pnl_pct'] for t in trades if t['pnl_pct'] <= 0]
    
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Calculate max drawdown
    equity_curve = [INITIAL_CAPITAL]
    for trade in trades:
        equity_curve.append(equity_curve[-1] * (1 + POSITION_SIZE_PCT * trade['pnl_pct'] / 100))
    
    peak = equity_curve[0]
    max_dd = 0
    for equity in equity_curve:
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    # Average hold time
    hold_times = []
    for trade in trades:
        try:
            entry = datetime.fromisoformat(trade['entry_time'].replace('Z', '+00:00'))
            exit = datetime.fromisoformat(trade['exit_time'].replace('Z', '+00:00'))
            hold_times.append((exit - entry).total_seconds() / 3600)
        except:
            pass
    avg_hold_hours = sum(hold_times) / len(hold_times) if hold_times else 0
    
    total_return = ((capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
    
    # Direction analysis
    long_trades = [t for t in trades if t['direction'] == 'LONG']
    short_trades = [t for t in trades if t['direction'] == 'SHORT']
    
    print(f"\nPeriod: {df[MIN_ROWS]['timestamp']} to {df[-1]['timestamp']}")
    print(f"Coin: BTC")
    print(f"Timeframe: 1-hour candles")
    print(f"Initial Capital: ${INITIAL_CAPITAL:,.2f}")
    print(f"Final Capital: ${capital:,.2f}")
    print(f"Total Return: {total_return:+.2f}%")
    print(f"\nTotal Trades: {len(trades)}")
    print(f"Winning Trades: {winning_trades}")
    print(f"Losing Trades: {losing_trades}")
    print(f"Win Rate: {win_rate:.1f}%")
    print(f"Profit Factor: {profit_factor:.2f}")
    print(f"Max Drawdown: {max_dd:.2f}%")
    print(f"Avg Win: {avg_win:.2f}%")
    print(f"Avg Loss: {avg_loss:.2f}%")
    print(f"Avg Hold Time: {avg_hold_hours:.1f} hours")
    print(f"Risk/Reward: 1:2 ({STOP_LOSS_PCT}% SL / {TAKE_PROFIT_PCT}% TP)")
    print(f"Leverage: {LEVERAGE}x")
    
    if long_trades:
        long_wins = sum(1 for t in long_trades if t['result'] == 'WIN')
        long_pnl = sum(t['pnl_pct'] for t in long_trades)
        print(f"\nLONG Trades: {len(long_trades)} | Wins: {long_wins} ({long_wins/len(long_trades)*100:.1f}%) | Total P&L: {long_pnl:+.2f}%")
    
    if short_trades:
        short_wins = sum(1 for t in short_trades if t['result'] == 'WIN')
        short_pnl = sum(t['pnl_pct'] for t in short_trades)
        print(f"SHORT Trades: {len(short_trades)} | Wins: {short_wins} ({short_wins/len(short_trades)*100:.1f}%) | Total P&L: {short_pnl:+.2f}%")
    
    print(f"\n{'='*70}")
    
    # Recent trades
    print("\nLast 10 Trades:")
    print("-" * 70)
    for trade in trades[-10:]:
        mom_str = f"M:{trade.get('momentum', 0):.2f} A:{trade.get('acceleration', 0):.2f}"
        print(f"{trade['direction']:5} | Entry: ${trade['entry_price']:,.2f} | Exit: ${trade['exit_price']:,.2f} | P&L: {trade['pnl_pct']:+.2f}% | {trade['result']} ({trade['reason']}) | {mom_str}")
else:
    print("\nNo trades generated!")
    buy_signals = sum(1 for r in df if r['signal'] == 'BUY')
    sell_signals = sum(1 for r in df if r['signal'] == 'SELL')
    print(f"Signals generated: BUY={buy_signals}, SELL={sell_signals}")
