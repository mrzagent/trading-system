#!/usr/bin/env python3
"""
Backtest VWAP Reversion Strategy using Binance historical data.
Standard library only - no pandas.
"""

import csv
import json
from datetime import datetime, timedelta
import sys

# Configuration
INITIAL_CAPITAL = 1000
POSITION_SIZE_PCT = 0.02  # 2% risk per trade
LEVERAGE = 1.0
STOP_LOSS_PCT = 1.5  # 1.5% stop loss
TAKE_PROFIT_PCT = 3.0  # 3% take profit (1:2 R/R)
DEVIATION_PCT = 1.0  # Minimum deviation to trigger
VWAP_PERIOD = 24  # 24 candles (2 hours for 5-min)
MIN_ROWS = 30

# Load Binance 5-min data
print("Loading Binance BTC 5-minute data...")

data_file = 'D:/dev/trading/data/binance_btc_5min_2026-06-24.csv'

df = []
with open(data_file, 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        # Handle different column naming conventions
        open_price = float(row.get('open') or row.get('open_price') or 0)
        high_price = float(row.get('high') or row.get('high_price') or 0)
        low_price = float(row.get('low') or row.get('low_price') or 0)
        close_price = float(row.get('close') or row.get('close_price') or 0)
        volume = float(row.get('volume') or row.get('quote_volume') or 0)
        timestamp = row.get('timestamp') or row.get('open_time') or row.get('datetime')
        
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

# Calculate VWAP
def calculate_vwap(data, idx, period=VWAP_PERIOD):
    """Calculate VWAP from typical price × volume."""
    start = max(0, idx - period + 1)
    total_pv = 0.0
    total_vol = 0.0
    
    for i in range(start, idx + 1):
        row = data[i]
        typical_price = (row['high'] + row['low'] + row['close']) / 3
        volume = row['volume']
        total_pv += typical_price * volume
        total_vol += volume
    
    return total_pv / total_vol if total_vol > 0 else typical_price

print("\nCalculating VWAP and generating signals...")

# Debug: Check first few rows
print("\nFirst 5 rows:")
for i in range(min(5, len(df))):
    print(f"  Close: {df[i]['close']:.2f}, VWAP: {df[i].get('vwap', 'N/A')}, Volume: {df[i]['volume']:.2f}")

# Add VWAP and signals
for i in range(len(df)):
    if i < VWAP_PERIOD:
        # Not enough data, use simple moving average of typical price
        typical_prices = [(r['high'] + r['low'] + r['close']) / 3 for r in df[:i+1]]
        df[i]['vwap'] = sum(typical_prices) / len(typical_prices)
    else:
        df[i]['vwap'] = calculate_vwap(df, i, VWAP_PERIOD)
    
    # Calculate deviation
    vwap = df[i]['vwap']
    if vwap == 0 or vwap is None:
        vwap = df[i]['close']  # Fallback to close price
    df[i]['deviation_pct'] = ((df[i]['close'] - vwap) / vwap) * 100 if vwap != 0 else 0
    
    # Generate signal
    if df[i]['deviation_pct'] < -DEVIATION_PCT:
        df[i]['signal'] = 'BUY'
    elif df[i]['deviation_pct'] > DEVIATION_PCT:
        df[i]['signal'] = 'SELL'
    else:
        df[i]['signal'] = 'HOLD'

# Backtest simulation
print("\n" + "="*70)
print("VWAP REVERSION BACKTEST")
print("="*70)

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
        
        # Calculate P&L
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
                    'reason': 'STOP_LOSS'
                })
                capital *= (1 - POSITION_SIZE_PCT * STOP_LOSS_PCT / 100)
                position = None
                cooldown_end = i + 6  # 30 min cooldown (6 candles)
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
                    'reason': 'TAKE_PROFIT'
                })
                capital *= (1 + POSITION_SIZE_PCT * TAKE_PROFIT_PCT / 100)
                position = None
                cooldown_end = i + 6
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
                    'reason': 'STOP_LOSS'
                })
                capital *= (1 - POSITION_SIZE_PCT * STOP_LOSS_PCT / 100)
                position = None
                cooldown_end = i + 6
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
                    'reason': 'TAKE_PROFIT'
                })
                capital *= (1 + POSITION_SIZE_PCT * TAKE_PROFIT_PCT / 100)
                position = None
                cooldown_end = i + 6
                continue
    
    # Check for new entry
    if not position and i >= cooldown_end:
        deviation = row['deviation_pct']
        if signal == 'BUY':
            position = {
                'direction': 'LONG',
                'entry_price': price,
                'entry_time': timestamp,
                'deviation': abs(deviation)  # Store absolute deviation
            }
        elif signal == 'SELL':
            position = {
                'direction': 'SHORT',
                'entry_price': price,
                'entry_time': timestamp,
                'deviation': abs(deviation)  # Store absolute deviation
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
        'reason': 'FINAL_CLOSE'
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
            # Try to parse timestamps
            entry = datetime.fromisoformat(trade['entry_time'].replace('Z', '+00:00'))
            exit = datetime.fromisoformat(trade['exit_time'].replace('Z', '+00:00'))
            hold_times.append((exit - entry).total_seconds() / 3600)
        except:
            pass
    avg_hold_hours = sum(hold_times) / len(hold_times) if hold_times else 0
    
    total_return = ((capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
    
    print(f"\nPeriod: {df[MIN_ROWS]['timestamp']} to {df[-1]['timestamp']}")
    print(f"Coin: BTC")
    print(f"Timeframe: 5-minute candles")
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
    print(f"\n{'='*70}")
    
    # Analysis by direction
    long_trades = [t for t in trades if t['direction'] == 'LONG']
    short_trades = [t for t in trades if t['direction'] == 'SHORT']
    
    if long_trades:
        long_wins = sum(1 for t in long_trades if t['result'] == 'WIN')
        long_pnl = sum(t['pnl_pct'] for t in long_trades)
        print(f"\nLONG Trades: {len(long_trades)} | Wins: {long_wins} ({long_wins/len(long_trades)*100:.1f}%) | Total P&L: {long_pnl:+.2f}%")
    
    if short_trades:
        short_wins = sum(1 for t in short_trades if t['result'] == 'WIN')
        short_pnl = sum(t['pnl_pct'] for t in short_trades)
        print(f"SHORT Trades: {len(short_trades)} | Wins: {short_wins} ({short_wins/len(short_trades)*100:.1f}%) | Total P&L: {short_pnl:+.2f}%")
    
    # Analysis by exit reason
    sl_exits = [t for t in trades if t['reason'] == 'STOP_LOSS']
    tp_exits = [t for t in trades if t['reason'] == 'TAKE_PROFIT']
    print(f"\nExits: Stop Loss = {len(sl_exits)}, Take Profit = {len(tp_exits)}")
    
    # Deviation analysis - what deviation levels work best?
    print("\n" + "="*70)
    print("DEVIATION LEVEL ANALYSIS")
    print("="*70)
    
    # Group trades by entry deviation
    deviation_buckets = {
        '1-2%': [],
        '2-3%': [],
        '3-5%': [],
        '5%+': []
    }
    
    for trade in trades:
        dev = abs(trade.get('deviation', 0))
        if 1 <= dev < 2:
            deviation_buckets['1-2%'].append(trade)
        elif 2 <= dev < 3:
            deviation_buckets['2-3%'].append(trade)
        elif 3 <= dev < 5:
            deviation_buckets['3-5%'].append(trade)
        elif dev >= 5:
            deviation_buckets['5%+'].append(trade)
    
    for bucket, bucket_trades in deviation_buckets.items():
        if bucket_trades:
            bucket_wins = sum(1 for t in bucket_trades if t['result'] == 'WIN')
            bucket_pnl = sum(t['pnl_pct'] for t in bucket_trades)
            print(f"Deviation {bucket}: {len(bucket_trades)} trades, {bucket_wins/len(bucket_trades)*100:.1f}% win, P&L: {bucket_pnl:+.2f}%")
    
    # Recent trades
    print("\n" + "="*70)
    print("Last 10 Trades:")
    print("-" * 70)
    for trade in trades[-10:]:
        print(f"{trade['direction']:5} | Entry: ${trade['entry_price']:,.2f} | Exit: ${trade['exit_price']:,.2f} | P&L: {trade['pnl_pct']:+.2f}% | {trade['result']} ({trade['reason']})")
else:
    print("\nNo trades generated!")
    buy_signals = sum(1 for r in df if r['signal'] == 'BUY')
    sell_signals = sum(1 for r in df if r['signal'] == 'SELL')
    print(f"Signals generated: BUY={buy_signals}, SELL={sell_signals}")
