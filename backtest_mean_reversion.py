#!/usr/bin/env python3
"""
Backtest Mean Reversion strategy on 3 years of BTC data from CSV.
Fresh backtest - ignores previous findings.
Simplified version without ADX for speed.
"""

import csv
import math
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

# Strategy parameters (from strategy_mean_reversion.py)
STRATEGY = "mean_reversion"
CANDLE_MINUTES = 60  # 1H candles (synthetic from 5-min data)
BB_PERIOD = 20
BB_STD_DEV = 2.0
RSI2_PERIOD = 2
RSI2_OVERSOLD = 10
RSI2_OVERBOUGHT = 90
ATR_PERIOD = 14
ATR_SL_MULT = 1.5
COOLDOWN_MINUTES = 0


@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Trade:
    entry_time: datetime
    exit_time: Optional[datetime]
    side: str  # 'long' or 'short'
    entry_price: float
    exit_price: Optional[float]
    stop_loss: float
    take_profit_middle: float
    take_profit_2r: float
    pnl_pct: float
    pnl_usd: float
    exit_reason: str
    atr: float
    rsi2: float


def load_csv_data(filepath: str) -> List[Candle]:
    """Load 5-min candle data from CSV."""
    candles = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = datetime.fromisoformat(row['open_time'].replace('+00:00', ''))
            candles.append(Candle(
                timestamp=ts,
                open=float(row['open_price']),
                high=float(row['high_price']),
                low=float(row['low_price']),
                close=float(row['close_price']),
                volume=float(row['volume'])
            ))
    return candles


def aggregate_to_1h(candles_5min: List[Candle]) -> List[Candle]:
    """Aggregate 5-min candles to 1H candles."""
    candles_1h = []
    for i in range(0, len(candles_5min) - 11, 12):
        chunk = candles_5min[i:i+12]
        if len(chunk) < 12:
            break
        
        open_price = chunk[0].open
        high_price = max(c.high for c in chunk)
        low_price = min(c.low for c in chunk)
        close_price = chunk[-1].close
        volume = sum(c.volume for c in chunk)
        
        candles_1h.append(Candle(
            timestamp=chunk[0].timestamp,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume
        ))
    
    return candles_1h


def calculate_bollinger_bands(closes: List[float], period: int, num_std: float) -> Tuple[float, float, float]:
    """Compute Bollinger Bands (lower, middle, upper)."""
    if len(closes) < period:
        nan = float("nan")
        return nan, nan, nan
    
    window = closes[-period:]
    mean = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    std_dev = math.sqrt(variance)
    
    bb_middle = mean
    bb_upper = mean + num_std * std_dev
    bb_lower = mean - num_std * std_dev
    return bb_lower, bb_middle, bb_upper


def calculate_rsi(closes: List[float], period: int) -> float:
    """RSI using Wilder's smoothed average."""
    if len(closes) < period + 1:
        return float("nan")
    
    gains, losses = [], []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    
    if len(gains) < period:
        return float("nan")
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return round(rsi, 2)


def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int) -> float:
    """Average True Range."""
    if len(closes) < period + 1:
        return float("nan")
    
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    
    if len(trs) < period:
        return float("nan")
    
    return sum(trs[-period:]) / period


def run_backtest(candles: List[Candle], initial_capital: float = 1000.0) -> Dict:
    """Run Mean Reversion backtest on 1H candles."""
    trades = []
    open_trade: Optional[Trade] = None
    
    capital = initial_capital
    max_capital = initial_capital
    max_drawdown = 0.0
    
    min_rows = max(BB_PERIOD, ATR_PERIOD) + 10
    
    print(f"Running backtest: {min_rows} to {len(candles)} candles...")
    
    for i in range(min_rows, len(candles)):
        if i % 2000 == 0:
            print(f"  Progress: {i}/{len(candles)} ({i/len(candles)*100:.1f}%)", end='\r')
        
        current_candle = candles[i]
        current_price = current_candle.close
        
        # Check if we have an open trade
        if open_trade:
            # Check exit conditions
            if open_trade.side == 'long':
                # Check SL
                if current_price <= open_trade.stop_loss:
                    open_trade.exit_price = open_trade.stop_loss
                    open_trade.exit_time = current_candle.timestamp
                    open_trade.exit_reason = 'sl'
                    open_trade.pnl_pct = ((open_trade.stop_loss - open_trade.entry_price) / open_trade.entry_price) * 100
                    capital *= (1 + open_trade.pnl_pct / 100)
                    open_trade.pnl_usd = capital - (capital / (1 + open_trade.pnl_pct / 100))
                    trades.append(open_trade)
                    open_trade = None
                    continue
                
                # Check TP (middle band or 2R, whichever hits first)
                if current_price >= open_trade.take_profit_middle or current_price >= open_trade.take_profit_2r:
                    if current_price >= open_trade.take_profit_middle:
                        exit_price = open_trade.take_profit_middle
                        exit_reason = 'tp_middle'
                    else:
                        exit_price = open_trade.take_profit_2r
                        exit_reason = 'tp_2r'
                    
                    open_trade.exit_price = exit_price
                    open_trade.exit_time = current_candle.timestamp
                    open_trade.exit_reason = exit_reason
                    open_trade.pnl_pct = ((exit_price - open_trade.entry_price) / open_trade.entry_price) * 100
                    capital *= (1 + open_trade.pnl_pct / 100)
                    open_trade.pnl_usd = capital - (capital / (1 + open_trade.pnl_pct / 100))
                    trades.append(open_trade)
                    open_trade = None
                    continue
            
            else:  # short
                # Check SL
                if current_price >= open_trade.stop_loss:
                    open_trade.exit_price = open_trade.stop_loss
                    open_trade.exit_time = current_candle.timestamp
                    open_trade.exit_reason = 'sl'
                    open_trade.pnl_pct = ((open_trade.entry_price - open_trade.stop_loss) / open_trade.entry_price) * 100
                    capital *= (1 + open_trade.pnl_pct / 100)
                    open_trade.pnl_usd = capital - (capital / (1 + open_trade.pnl_pct / 100))
                    trades.append(open_trade)
                    open_trade = None
                    continue
                
                # Check TP (middle band or 2R)
                if current_price <= open_trade.take_profit_middle or current_price <= open_trade.take_profit_2r:
                    if current_price <= open_trade.take_profit_middle:
                        exit_price = open_trade.take_profit_middle
                        exit_reason = 'tp_middle'
                    else:
                        exit_price = open_trade.take_profit_2r
                        exit_reason = 'tp_2r'
                    
                    open_trade.exit_price = exit_price
                    open_trade.exit_time = current_candle.timestamp
                    open_trade.exit_reason = exit_reason
                    open_trade.pnl_pct = ((open_trade.entry_price - exit_price) / open_trade.entry_price) * 100
                    capital *= (1 + open_trade.pnl_pct / 100)
                    open_trade.pnl_usd = capital - (capital / (1 + open_trade.pnl_pct / 100))
                    trades.append(open_trade)
                    open_trade = None
                    continue
            
            continue  # Still in trade, skip signal generation
        
        # Calculate indicators for this candle
        closes = [c.close for c in candles[:i+1]]
        highs = [c.high for c in candles[:i+1]]
        lows = [c.low for c in candles[:i+1]]
        
        bb_lower, bb_middle, bb_upper = calculate_bollinger_bands(closes, BB_PERIOD, BB_STD_DEV)
        if any(v != v for v in (bb_lower, bb_middle, bb_upper)):
            continue
        
        rsi2 = calculate_rsi(closes, RSI2_PERIOD)
        if rsi2 != rsi2:
            continue
        
        atr = calculate_atr(highs, lows, closes, ATR_PERIOD)
        if atr != atr:
            continue
        
        # Check entry conditions (without ADX filter for speed)
        touches_lower = current_price <= bb_lower
        touches_upper = current_price >= bb_upper
        rsi_oversold = rsi2 < RSI2_OVERSOLD
        rsi_overbought = rsi2 > RSI2_OVERBOUGHT
        
        trade_action = None
        if touches_lower and rsi_oversold:
            trade_action = "BUY"
        elif touches_upper and rsi_overbought:
            trade_action = "SELL"
        
        if not trade_action:
            continue
        
        # Open new trade
        side = 'long' if trade_action == "BUY" else 'short'
        sl_distance = atr * ATR_SL_MULT
        
        if side == 'long':
            stop_loss = current_price - sl_distance
            take_profit_middle = bb_middle
            take_profit_2r = current_price + (sl_distance * 2)
        else:
            stop_loss = current_price + sl_distance
            take_profit_middle = bb_middle
            take_profit_2r = current_price - (sl_distance * 2)
        
        open_trade = Trade(
            entry_time=current_candle.timestamp,
            exit_time=None,
            side=side,
            entry_price=current_price,
            exit_price=None,
            stop_loss=stop_loss,
            take_profit_middle=take_profit_middle,
            take_profit_2r=take_profit_2r,
            pnl_pct=0.0,
            pnl_usd=0.0,
            exit_reason='open',
            atr=atr,
            rsi2=rsi2
        )
        
        # Track max capital for drawdown
        if capital > max_capital:
            max_capital = capital
        drawdown = (max_capital - capital) / max_capital * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
    print(f"\n  Done! Processed {len(candles)} candles.")
    
    # Calculate statistics
    closed_trades = [t for t in trades if t.exit_reason != 'open']
    winning_trades = [t for t in closed_trades if t.pnl_pct > 0]
    losing_trades = [t for t in closed_trades if t.pnl_pct <= 0]
    
    total_return = ((capital - initial_capital) / initial_capital) * 100
    win_rate = (len(winning_trades) / len(closed_trades) * 100) if closed_trades else 0
    
    gross_profit = sum(t.pnl_pct for t in winning_trades) if winning_trades else 0
    gross_loss = abs(sum(t.pnl_pct for t in losing_trades)) if losing_trades else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Average hold time
    hold_times = []
    for t in closed_trades:
        if t.exit_time and t.entry_time:
            hold_times.append((t.exit_time - t.entry_time).total_seconds() / 3600)
    avg_hold_hours = sum(hold_times) / len(hold_times) if hold_times else 0
    
    return {
        'initial_capital': initial_capital,
        'final_capital': capital,
        'total_return_pct': total_return,
        'total_trades': len(closed_trades),
        'winning_trades': len(winning_trades),
        'losing_trades': len(losing_trades),
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'max_drawdown_pct': max_drawdown,
        'avg_hold_hours': avg_hold_hours,
        'trades': closed_trades
    }


def print_results(results: Dict):
    """Print backtest results."""
    print("\n" + "=" * 70)
    print("MEAN REVERSION STRATEGY BACKTEST RESULTS - BTC 3 YEARS")
    print("=" * 70)
    print(f"Period: June 2023 - June 2026")
    print(f"Timeframe: 1H candles (synthetic from 5-min)")
    print(f"Strategy: Bollinger Bands(20,2) + RSI(2)")
    print(f"Entry: Price touches BB + RSI2 extreme")
    print(f"Exit: BB Middle or 2R (whichever first)")
    print("-" * 70)
    print(f"Initial Capital:    ${results['initial_capital']:,.2f}")
    print(f"Final Capital:      ${results['final_capital']:,.2f}")
    print(f"Total Return:       {results['total_return_pct']:+.2f}%")
    print("-" * 70)
    print(f"Total Trades:       {results['total_trades']}")
    print(f"Winning Trades:     {results['winning_trades']}")
    print(f"Losing Trades:      {results['losing_trades']}")
    print(f"Win Rate:           {results['win_rate']:.1f}%")
    print(f"Profit Factor:      {results['profit_factor']:.2f}")
    print(f"Max Drawdown:       {results['max_drawdown_pct']:.2f}%")
    print(f"Avg Hold Time:      {results['avg_hold_hours']:.1f} hours")
    print("=" * 70)
    
    # Consecutive loss analysis
    print("\nConsecutive Loss Analysis:")
    print("-" * 70)
    max_consecutive_losses = 0
    current_streak = 0
    streak_start = None
    worst_streak_start = None
    worst_streak_end = None
    
    for t in results['trades']:
        if t.pnl_pct <= 0:
            if current_streak == 0:
                streak_start = t.entry_time
            current_streak += 1
            if current_streak > max_consecutive_losses:
                max_consecutive_losses = current_streak
                worst_streak_start = streak_start
                worst_streak_end = t.exit_time
        else:
            current_streak = 0
    
    print(f"Max Consecutive Losses: {max_consecutive_losses}")
    if worst_streak_start and worst_streak_end:
        print(f"Worst Streak Period: {worst_streak_start.strftime('%Y-%m-%d')} to {worst_streak_end.strftime('%Y-%m-%d')}")
    
    # Show last 10 trades
    if results['trades']:
        print("\nLast 10 Trades:")
        print("-" * 70)
        for t in results['trades'][-10:]:
            emoji = "WIN" if t.pnl_pct > 0 else "LOSS"
            print(f"{t.entry_time.strftime('%Y-%m-%d %H:%M')} | {t.side.upper():4} | "
                  f"${t.entry_price:,.2f} -> ${t.exit_price:,.2f} | "
                  f"{t.pnl_pct:+.2f}% | {t.exit_reason.upper():10} | "
                  f"RSI2:{t.rsi2:.1f} | {emoji}")


def main():
    print("Loading 5-min data from CSV...")
    candles_5min = load_csv_data(r'D:\dev\trading\data\binance_btc_5min_2026-06-24.csv')
    print(f"Loaded {len(candles_5min):,} 5-min candles")
    print(f"Date range: {candles_5min[0].timestamp} to {candles_5min[-1].timestamp}")
    
    print("\nAggregating to 1H candles...")
    candles_1h = aggregate_to_1h(candles_5min)
    print(f"Created {len(candles_1h):,} 1H candles")
    
    print("\nRunning backtest...")
    results = run_backtest(candles_1h, initial_capital=1000.0)
    
    print_results(results)


if __name__ == "__main__":
    main()
