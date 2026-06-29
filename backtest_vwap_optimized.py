#!/usr/bin/env python3
"""
Backtest VWAP Reversion Strategy with parameter optimization.
Tests different deviation thresholds, SL/TP ratios, and trend filters.
"""

import csv
import json
from datetime import datetime, timedelta
import sys

def run_backtest(config):
    """Run backtest with given configuration."""
    
    INITIAL_CAPITAL = 1000
    POSITION_SIZE_PCT = 0.02
    LEVERAGE = config.get('leverage', 1.0)
    STOP_LOSS_PCT = config.get('sl', 1.5)
    TAKE_PROFIT_PCT = config.get('tp', 3.0)
    DEVIATION_PCT = config.get('deviation', 1.0)
    VWAP_PERIOD = config.get('vwap_period', 24)
    MIN_ROWS = 30
    COOLDOWN_CANDLES = config.get('cooldown', 6)
    
    # Trend filter
    use_trend_filter = config.get('trend_filter', False)
    trend_ema_period = config.get('trend_ema', 200)
    
    # Load data
    data_file = 'D:/dev/trading/data/binance_btc_5min_2026-06-24.csv'
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
    
    # Calculate VWAP
    for i in range(len(df)):
        if i < VWAP_PERIOD:
            typical_prices = [(r['high'] + r['low'] + r['close']) / 3 for r in df[:i+1]]
            df[i]['vwap'] = sum(typical_prices) / len(typical_prices)
        else:
            start = max(0, i - VWAP_PERIOD + 1)
            total_pv = 0.0
            total_vol = 0.0
            for j in range(start, i + 1):
                typical_price = (df[j]['high'] + df[j]['low'] + df[j]['close']) / 3
                volume = df[j]['volume']
                total_pv += typical_price * volume
                total_vol += volume
            df[i]['vwap'] = total_pv / total_vol if total_vol > 0 else df[i]['close']
        
        vwap = df[i]['vwap']
        if vwap == 0 or vwap is None:
            vwap = df[i]['close']
        df[i]['deviation_pct'] = ((df[i]['close'] - vwap) / vwap) * 100
    
    # Calculate trend EMA if needed
    if use_trend_filter:
        for i in range(len(df)):
            if i < trend_ema_period:
                prices = [r['close'] for r in df[:i+1]]
                df[i]['ema_trend'] = sum(prices) / len(prices)
            else:
                prices = [r['close'] for r in df[i-trend_ema_period+1:i+1]]
                df[i]['ema_trend'] = sum(prices) / trend_ema_period
    
    # Generate signals
    for i in range(len(df)):
        deviation = df[i]['deviation_pct']
        
        if use_trend_filter and i >= trend_ema_period:
            price = df[i]['close']
            ema = df[i]['ema_trend']
            # Only take LONG in uptrend, SHORT in downtrend
            if price > ema:  # Uptrend
                if deviation < -DEVIATION_PCT:
                    df[i]['signal'] = 'BUY'
                else:
                    df[i]['signal'] = 'HOLD'
            elif price < ema:  # Downtrend
                if deviation > DEVIATION_PCT:
                    df[i]['signal'] = 'SELL'
                else:
                    df[i]['signal'] = 'HOLD'
            else:
                df[i]['signal'] = 'HOLD'
        else:
            if deviation < -DEVIATION_PCT:
                df[i]['signal'] = 'BUY'
            elif deviation > DEVIATION_PCT:
                df[i]['signal'] = 'SELL'
            else:
                df[i]['signal'] = 'HOLD'
    
    # Backtest simulation
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
            
            if direction == 'LONG':
                pnl_pct = (price - entry_price) / entry_price * 100 * LEVERAGE
                if pnl_pct <= -STOP_LOSS_PCT:
                    trades.append({'result': 'LOSS', 'pnl_pct': -STOP_LOSS_PCT, 'direction': direction})
                    capital *= (1 - POSITION_SIZE_PCT * STOP_LOSS_PCT / 100)
                    position = None
                    cooldown_end = i + COOLDOWN_CANDLES
                    continue
                if pnl_pct >= TAKE_PROFIT_PCT:
                    trades.append({'result': 'WIN', 'pnl_pct': TAKE_PROFIT_PCT, 'direction': direction})
                    capital *= (1 + POSITION_SIZE_PCT * TAKE_PROFIT_PCT / 100)
                    position = None
                    cooldown_end = i + COOLDOWN_CANDLES
                    continue
            else:
                pnl_pct = (entry_price - price) / entry_price * 100 * LEVERAGE
                if pnl_pct <= -STOP_LOSS_PCT:
                    trades.append({'result': 'LOSS', 'pnl_pct': -STOP_LOSS_PCT, 'direction': direction})
                    capital *= (1 - POSITION_SIZE_PCT * STOP_LOSS_PCT / 100)
                    position = None
                    cooldown_end = i + COOLDOWN_CANDLES
                    continue
                if pnl_pct >= TAKE_PROFIT_PCT:
                    trades.append({'result': 'WIN', 'pnl_pct': TAKE_PROFIT_PCT, 'direction': direction})
                    capital *= (1 + POSITION_SIZE_PCT * TAKE_PROFIT_PCT / 100)
                    position = None
                    cooldown_end = i + COOLDOWN_CANDLES
                    continue
        
        # Check for new entry
        if not position and i >= cooldown_end:
            if signal == 'BUY':
                position = {'direction': 'LONG', 'entry_price': price}
            elif signal == 'SELL':
                position = {'direction': 'SHORT', 'entry_price': price}
    
    # Close final position
    if position:
        final_price = df[-1]['close']
        entry_price = position['entry_price']
        direction = position['direction']
        if direction == 'LONG':
            pnl_pct = (final_price - entry_price) / entry_price * 100 * LEVERAGE
        else:
            pnl_pct = (entry_price - final_price) / entry_price * 100 * LEVERAGE
        trades.append({'result': 'WIN' if pnl_pct > 0 else 'LOSS', 'pnl_pct': pnl_pct, 'direction': direction})
        capital *= (1 + POSITION_SIZE_PCT * pnl_pct / 100)
    
    # Calculate stats
    if len(trades) > 0:
        winning_trades = sum(1 for t in trades if t['result'] == 'WIN')
        losing_trades = sum(1 for t in trades if t['result'] == 'LOSS')
        win_rate = (winning_trades / len(trades)) * 100
        
        wins = [t['pnl_pct'] for t in trades if t['pnl_pct'] > 0]
        losses = [t['pnl_pct'] for t in trades if t['pnl_pct'] <= 0]
        
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        total_return = ((capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
        
        return {
            'trades': len(trades),
            'wins': winning_trades,
            'losses': losing_trades,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'return_pct': total_return,
            'final_capital': capital
        }
    else:
        return {'trades': 0, 'return_pct': 0}


# Test different configurations
print("="*80)
print("VWAP REVERSION - PARAMETER OPTIMIZATION")
print("="*80)

configs = [
    # Baseline
    {'name': 'Baseline (1% dev, 1.5/3 SL/TP)', 'deviation': 1.0, 'sl': 1.5, 'tp': 3.0},
    
    # Higher deviation threshold
    {'name': '2% Deviation', 'deviation': 2.0, 'sl': 1.5, 'tp': 3.0},
    {'name': '3% Deviation', 'deviation': 3.0, 'sl': 1.5, 'tp': 3.0},
    
    # Tighter stops
    {'name': '1% Dev + 1% SL / 2% TP', 'deviation': 1.0, 'sl': 1.0, 'tp': 2.0},
    {'name': '2% Dev + 1% SL / 2% TP', 'deviation': 2.0, 'sl': 1.0, 'tp': 2.0},
    
    # Wider targets
    {'name': '1% Dev + 1.5% SL / 4.5% TP (1:3)', 'deviation': 1.0, 'sl': 1.5, 'tp': 4.5},
    {'name': '2% Dev + 1.5% SL / 4.5% TP (1:3)', 'deviation': 2.0, 'sl': 1.5, 'tp': 4.5},
    
    # With trend filter
    {'name': '1% Dev + Trend Filter (200 EMA)', 'deviation': 1.0, 'sl': 1.5, 'tp': 3.0, 'trend_filter': True},
    {'name': '2% Dev + Trend Filter (200 EMA)', 'deviation': 2.0, 'sl': 1.5, 'tp': 3.0, 'trend_filter': True},
    
    # Longer VWAP period
    {'name': '1% Dev + 48-period VWAP', 'deviation': 1.0, 'sl': 1.5, 'tp': 3.0, 'vwap_period': 48},
    {'name': '2% Dev + 48-period VWAP', 'deviation': 2.0, 'sl': 1.5, 'tp': 3.0, 'vwap_period': 48},
    
    # No cooldown
    {'name': '1% Dev + No Cooldown', 'deviation': 1.0, 'sl': 1.5, 'tp': 3.0, 'cooldown': 0},
    
    # With leverage
    {'name': '1% Dev + 2x Leverage', 'deviation': 1.0, 'sl': 1.5, 'tp': 3.0, 'leverage': 2.0},
    {'name': '2% Dev + 2x Leverage', 'deviation': 2.0, 'sl': 1.5, 'tp': 3.0, 'leverage': 2.0},
]

results = []
for config in configs:
    print(f"\nTesting: {config['name']}")
    result = run_backtest(config)
    result['name'] = config['name']
    results.append(result)
    print(f"  Trades: {result['trades']}, Win Rate: {result.get('win_rate', 0):.1f}%, Return: {result.get('return_pct', 0):+.2f}%, PF: {result.get('profit_factor', 0):.2f}")

# Sort by return
results_sorted = sorted(results, key=lambda x: x.get('return_pct', 0), reverse=True)

print("\n" + "="*80)
print("TOP 10 CONFIGURATIONS BY RETURN")
print("="*80)
print(f"{'Rank':<5} {'Configuration':<45} {'Return':>10} {'Trades':>8} {'Win%':>8} {'PF':>6}")
print("-"*80)
for i, r in enumerate(results_sorted[:10], 1):
    print(f"{i:<5} {r['name']:<45} {r.get('return_pct', 0):>+9.2f}% {r['trades']:>8} {r.get('win_rate', 0):>7.1f}% {r.get('profit_factor', 0):>6.2f}")
