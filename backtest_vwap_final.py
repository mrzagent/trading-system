#!/usr/bin/env python3
"""
Final VWAP Reversion optimization with best parameters.
"""

import csv
from datetime import datetime

def run_backtest(config):
    INITIAL_CAPITAL = 1000
    POSITION_SIZE_PCT = 0.02
    LEVERAGE = config.get('leverage', 1.0)
    STOP_LOSS_PCT = config.get('sl', 1.5)
    TAKE_PROFIT_PCT = config.get('tp', 3.0)
    DEVIATION_PCT = config.get('deviation', 1.0)
    VWAP_PERIOD = config.get('vwap_period', 24)
    MIN_ROWS = 30
    COOLDOWN_CANDLES = config.get('cooldown', 6)
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
            df.append({'timestamp': timestamp, 'open': open_price, 'high': high_price, 'low': low_price, 'close': close_price, 'volume': volume})
    
    # Calculate VWAP
    for i in range(len(df)):
        if i < VWAP_PERIOD:
            typical_prices = [(r['high'] + r['low'] + r['close']) / 3 for r in df[:i+1]]
            df[i]['vwap'] = sum(typical_prices) / len(typical_prices)
        else:
            start = max(0, i - VWAP_PERIOD + 1)
            total_pv = sum(((df[j]['high'] + df[j]['low'] + df[j]['close']) / 3) * df[j]['volume'] for j in range(start, i + 1))
            total_vol = sum(df[j]['volume'] for j in range(start, i + 1))
            df[i]['vwap'] = total_pv / total_vol if total_vol > 0 else df[i]['close']
        vwap = df[i]['vwap'] if df[i]['vwap'] != 0 else df[i]['close']
        df[i]['deviation_pct'] = ((df[i]['close'] - vwap) / vwap) * 100
    
    # Calculate trend EMA
    if use_trend_filter:
        for i in range(len(df)):
            period = min(i + 1, trend_ema_period)
            df[i]['ema_trend'] = sum(r['close'] for r in df[i-period+1:i+1]) / period
    
    # Generate signals
    for i in range(len(df)):
        deviation = df[i]['deviation_pct']
        if use_trend_filter and i >= trend_ema_period:
            price, ema = df[i]['close'], df[i]['ema_trend']
            if price > ema and deviation < -DEVIATION_PCT:
                df[i]['signal'] = 'BUY'
            elif price < ema and deviation > DEVIATION_PCT:
                df[i]['signal'] = 'SELL'
            else:
                df[i]['signal'] = 'HOLD'
        else:
            if deviation < -DEVIATION_PCT:
                df[i]['signal'] = 'BUY'
            elif deviation > DEVIATION_PCT:
                df[i]['signal'] = 'SELL'
            else:
                df[i]['signal'] = 'HOLD'
    
    # Backtest
    capital = INITIAL_CAPITAL
    trades = []
    position = None
    cooldown_end = 0
    
    for i in range(MIN_ROWS, len(df)):
        row = df[i]
        signal, price, timestamp = row['signal'], row['close'], row['timestamp']
        
        if position:
            entry_price, direction = position['entry_price'], position['direction']
            if direction == 'LONG':
                pnl_pct = (price - entry_price) / entry_price * 100 * LEVERAGE
                if pnl_pct <= -STOP_LOSS_PCT:
                    trades.append({'result': 'LOSS', 'pnl_pct': -STOP_LOSS_PCT, 'direction': direction})
                    capital *= (1 - POSITION_SIZE_PCT * STOP_LOSS_PCT / 100)
                    position, cooldown_end = None, i + COOLDOWN_CANDLES
                    continue
                if pnl_pct >= TAKE_PROFIT_PCT:
                    trades.append({'result': 'WIN', 'pnl_pct': TAKE_PROFIT_PCT, 'direction': direction})
                    capital *= (1 + POSITION_SIZE_PCT * TAKE_PROFIT_PCT / 100)
                    position, cooldown_end = None, i + COOLDOWN_CANDLES
                    continue
            else:
                pnl_pct = (entry_price - price) / entry_price * 100 * LEVERAGE
                if pnl_pct <= -STOP_LOSS_PCT:
                    trades.append({'result': 'LOSS', 'pnl_pct': -STOP_LOSS_PCT, 'direction': direction})
                    capital *= (1 - POSITION_SIZE_PCT * STOP_LOSS_PCT / 100)
                    position, cooldown_end = None, i + COOLDOWN_CANDLES
                    continue
                if pnl_pct >= TAKE_PROFIT_PCT:
                    trades.append({'result': 'WIN', 'pnl_pct': TAKE_PROFIT_PCT, 'direction': direction})
                    capital *= (1 + POSITION_SIZE_PCT * TAKE_PROFIT_PCT / 100)
                    position, cooldown_end = None, i + COOLDOWN_CANDLES
                    continue
        
        if not position and i >= cooldown_end:
            if signal == 'BUY':
                position = {'direction': 'LONG', 'entry_price': price}
            elif signal == 'SELL':
                position = {'direction': 'SHORT', 'entry_price': price}
    
    if position:
        final_price = df[-1]['close']
        entry_price, direction = position['entry_price'], position['direction']
        pnl_pct = ((final_price - entry_price) / entry_price * 100 * LEVERAGE) if direction == 'LONG' else ((entry_price - final_price) / entry_price * 100 * LEVERAGE)
        trades.append({'result': 'WIN' if pnl_pct > 0 else 'LOSS', 'pnl_pct': pnl_pct, 'direction': direction})
        capital *= (1 + POSITION_SIZE_PCT * pnl_pct / 100)
    
    if trades:
        winning_trades = sum(1 for t in trades if t['result'] == 'WIN')
        win_rate = (winning_trades / len(trades)) * 100
        gross_profit = sum(t['pnl_pct'] for t in trades if t['pnl_pct'] > 0)
        gross_loss = abs(sum(t['pnl_pct'] for t in trades if t['pnl_pct'] <= 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        total_return = ((capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
        return {'trades': len(trades), 'wins': winning_trades, 'win_rate': win_rate, 'profit_factor': profit_factor, 'return_pct': total_return, 'final_capital': capital}
    return {'trades': 0, 'return_pct': 0}


print("="*80)
print("VWAP REVERSION - FINAL OPTIMIZATION")
print("="*80)

# Best combinations based on results
configs = [
    {'name': '1% Dev + 2x Leverage + Trend Filter', 'deviation': 1.0, 'sl': 1.5, 'tp': 3.0, 'leverage': 2.0, 'trend_filter': True},
    {'name': '1% Dev + 2x Leverage + 1% SL / 2% TP', 'deviation': 1.0, 'sl': 1.0, 'tp': 2.0, 'leverage': 2.0},
    {'name': '1% Dev + 2x Leverage + 48-period VWAP', 'deviation': 1.0, 'sl': 1.5, 'tp': 3.0, 'leverage': 2.0, 'vwap_period': 48},
    {'name': '1% Dev + 3x Leverage', 'deviation': 1.0, 'sl': 1.5, 'tp': 3.0, 'leverage': 3.0},
    {'name': '1% Dev + 3x Leverage + Trend Filter', 'deviation': 1.0, 'sl': 1.5, 'tp': 3.0, 'leverage': 3.0, 'trend_filter': True},
    {'name': '0.8% Dev + 2x Leverage', 'deviation': 0.8, 'sl': 1.5, 'tp': 3.0, 'leverage': 2.0},
    {'name': '1.2% Dev + 2x Leverage', 'deviation': 1.2, 'sl': 1.5, 'tp': 3.0, 'leverage': 2.0},
    {'name': '1% Dev + 2x Leverage + No Cooldown', 'deviation': 1.0, 'sl': 1.5, 'tp': 3.0, 'leverage': 2.0, 'cooldown': 0},
    {'name': '1% Dev + 2x Leverage + 2% TP', 'deviation': 1.0, 'sl': 1.5, 'tp': 4.5, 'leverage': 2.0},
    {'name': '2% Dev + 2x Leverage + Trend Filter', 'deviation': 2.0, 'sl': 1.5, 'tp': 3.0, 'leverage': 2.0, 'trend_filter': True},
]

results = []
for config in configs:
    print(f"\nTesting: {config['name']}")
    result = run_backtest(config)
    result['name'] = config['name']
    results.append(result)
    print(f"  Trades: {result['trades']}, Win Rate: {result.get('win_rate', 0):.1f}%, Return: {result.get('return_pct', 0):+.2f}%, PF: {result.get('profit_factor', 0):.2f}")

results_sorted = sorted(results, key=lambda x: x.get('return_pct', 0), reverse=True)

print("\n" + "="*80)
print("FINAL RANKINGS")
print("="*80)
print(f"{'Rank':<5} {'Configuration':<50} {'Return':>10} {'Trades':>8} {'Win%':>8} {'PF':>6}")
print("-"*80)
for i, r in enumerate(results_sorted, 1):
    print(f"{i:<5} {r['name']:<50} {r.get('return_pct', 0):>+9.2f}% {r['trades']:>8} {r.get('win_rate', 0):>7.1f}% {r.get('profit_factor', 0):>6.2f}")

print("\n" + "="*80)
print("RECOMMENDATION")
print("="*80)
best = results_sorted[0]
print(f"Best Config: {best['name']}")
print(f"Return: {best.get('return_pct', 0):+.2f}%")
print(f"Trades: {best['trades']}")
print(f"Win Rate: {best.get('win_rate', 0):.1f}%")
print(f"Profit Factor: {best.get('profit_factor', 0):.2f}")
