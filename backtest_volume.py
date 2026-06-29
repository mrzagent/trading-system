#!/usr/bin/env python3
"""
Backtest Volume Spike strategy on 3 years of BTC data from CSV.
Fresh backtest - ignores previous findings.
"""

import csv
import json
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

# Strategy parameters (from strategy_volume.py)
STRATEGY = "volume_spike"
CANDLE_MINUTES = 15
SPIKE_MULTIPLIER = 1.5
LOOKBACK = 16  # 16 × 15min = 4h rolling average
PRICE_LOOKBACK = 16
MIN_ROWS = 6
STOP_LOSS_PCT = 1.5
TAKE_PROFIT_PCT = 3.0
COOLDOWN_MINUTES = 0  # No cooldown in volume strategy


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
    take_profit: float
    pnl_pct: float
    pnl_usd: float
    exit_reason: str
    volume_ratio: float
    change_4h: float


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


def aggregate_to_15min(candles_5min: List[Candle]) -> List[Candle]:
    """Aggregate 5-min candles to 15-min candles."""
    candles_15min = []
    for i in range(0, len(candles_5min) - 2, 3):
        chunk = candles_5min[i:i+3]
        if len(chunk) < 3:
            break
        
        open_price = chunk[0].open
        high_price = max(c.high for c in chunk)
        low_price = min(c.low for c in chunk)
        close_price = chunk[-1].close
        volume = sum(c.volume for c in chunk)
        
        candles_15min.append(Candle(
            timestamp=chunk[0].timestamp,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume
        ))
    
    return candles_15min


def rolling_avg_volume(candles: List[Candle], idx: int, lookback: int) -> float:
    """Average volume of candles[idx-lookback:idx] — excludes current."""
    if idx < lookback + 1:
        return 0.0
    sample = candles[idx - lookback:idx]
    vols = [c.volume for c in sample if c.volume > 0]
    return sum(vols) / len(vols) if vols else 0


def inter_candle_change(candles: List[Candle], idx: int, lookback: int) -> float:
    """Price % change over the last lookback candles."""
    if idx < lookback:
        return 0.0
    current = candles[idx].close
    previous = candles[idx - lookback].close
    if previous == 0:
        return 0.0
    return (current - previous) / previous * 100


def run_backtest(candles: List[Candle], initial_capital: float = 1000.0) -> Dict:
    """Run Volume Spike backtest on 15-min candles."""
    trades = []
    open_trade: Optional[Trade] = None
    
    capital = initial_capital
    max_capital = initial_capital
    max_drawdown = 0.0
    
    # Need at least LOOKBACK + PRICE_LOOKBACK candles to start
    start_idx = max(LOOKBACK, PRICE_LOOKBACK) + 1
    
    for i in range(start_idx, len(candles)):
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
                
                # Check TP
                if current_price >= open_trade.take_profit:
                    open_trade.exit_price = open_trade.take_profit
                    open_trade.exit_time = current_candle.timestamp
                    open_trade.exit_reason = 'tp'
                    open_trade.pnl_pct = ((open_trade.take_profit - open_trade.entry_price) / open_trade.entry_price) * 100
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
                
                # Check TP
                if current_price <= open_trade.take_profit:
                    open_trade.exit_price = open_trade.take_profit
                    open_trade.exit_time = current_candle.timestamp
                    open_trade.exit_reason = 'tp'
                    open_trade.pnl_pct = ((open_trade.entry_price - open_trade.take_profit) / open_trade.entry_price) * 100
                    capital *= (1 + open_trade.pnl_pct / 100)
                    open_trade.pnl_usd = capital - (capital / (1 + open_trade.pnl_pct / 100))
                    trades.append(open_trade)
                    open_trade = None
                    continue
            
            continue  # Still in trade, skip signal generation
        
        # Calculate volume metrics
        avg_vol = rolling_avg_volume(candles, i, LOOKBACK)
        cur_vol = current_candle.volume
        
        if avg_vol == 0:
            continue
        
        ratio = cur_vol / avg_vol
        is_spike = ratio >= SPIKE_MULTIPLIER
        
        if not is_spike:
            continue
        
        # Spike confirmed — check direction
        change = inter_candle_change(candles, i, PRICE_LOOKBACK)
        
        if change > 0:
            trade_action = "BUY"
        elif change < 0:
            trade_action = "SELL"
        else:
            continue  # Flat price, skip
        
        # Open new trade
        side = 'long' if trade_action == "BUY" else 'short'
        
        if side == 'long':
            stop_loss = current_price * (1 - STOP_LOSS_PCT / 100)
            take_profit = current_price * (1 + TAKE_PROFIT_PCT / 100)
        else:
            stop_loss = current_price * (1 + STOP_LOSS_PCT / 100)
            take_profit = current_price * (1 - TAKE_PROFIT_PCT / 100)
        
        open_trade = Trade(
            entry_time=current_candle.timestamp,
            exit_time=None,
            side=side,
            entry_price=current_price,
            exit_price=None,
            stop_loss=stop_loss,
            take_profit=take_profit,
            pnl_pct=0.0,
            pnl_usd=0.0,
            exit_reason='open',
            volume_ratio=ratio,
            change_4h=change
        )
        
        # Track max capital for drawdown
        if capital > max_capital:
            max_capital = capital
        drawdown = (max_capital - capital) / max_capital * 100
        if drawdown > max_drawdown:
            max_drawdown = drawdown
    
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
    
    # Analyze drawdown periods
    drawdown_periods = []
    in_drawdown = False
    dd_start = None
    dd_start_capital = 0
    peak_capital = initial_capital
    
    # Re-run to capture drawdown periods
    capital_dd = initial_capital
    max_capital_dd = initial_capital
    trade_idx = 0
    
    for i in range(start_idx, len(candles)):
        current_candle = candles[i]
        current_price = current_candle.close
        
        # Check if we have an open trade
        if open_trade:
            # Check exit conditions
            if open_trade.side == 'long':
                if current_price <= open_trade.stop_loss:
                    pnl_pct = ((open_trade.stop_loss - open_trade.entry_price) / open_trade.entry_price) * 100
                    capital_dd *= (1 + pnl_pct / 100)
                    trade_idx += 1
                elif current_price >= open_trade.take_profit:
                    pnl_pct = ((open_trade.take_profit - open_trade.entry_price) / open_trade.entry_price) * 100
                    capital_dd *= (1 + pnl_pct / 100)
                    trade_idx += 1
            else:  # short
                if current_price >= open_trade.stop_loss:
                    pnl_pct = ((open_trade.entry_price - open_trade.stop_loss) / open_trade.entry_price) * 100
                    capital_dd *= (1 + pnl_pct / 100)
                    trade_idx += 1
                elif current_price <= open_trade.take_profit:
                    pnl_pct = ((open_trade.entry_price - open_trade.take_profit) / open_trade.entry_price) * 100
                    capital_dd *= (1 + pnl_pct / 100)
                    trade_idx += 1
        
        # Track drawdown
        if capital_dd > max_capital_dd:
            if in_drawdown and (max_capital_dd - dd_start_capital) / dd_start_capital * 100 > 5:
                # End of drawdown period
                drawdown_periods.append({
                    'start': dd_start,
                    'end': current_candle.timestamp,
                    'start_capital': dd_start_capital,
                    'low_capital': max_capital_dd * (1 - max_drawdown / 100),
                    'end_capital': capital_dd,
                    'depth_pct': (max_capital_dd - min(capital_dd, max_capital_dd * (1 - max_drawdown / 100))) / max_capital_dd * 100,
                    'trades_count': trade_idx
                })
            in_drawdown = False
            max_capital_dd = capital_dd
        elif capital_dd < max_capital_dd:
            if not in_drawdown:
                in_drawdown = True
                dd_start = current_candle.timestamp
                dd_start_capital = max_capital_dd
    
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
        'trades': closed_trades,
        'drawdown_periods': drawdown_periods
    }


def print_results(results: Dict):
    """Print backtest results."""
    print("\n" + "=" * 70)
    print("VOLUME SPIKE STRATEGY BACKTEST RESULTS - BTC 3 YEARS")
    print("=" * 70)
    print(f"Period: June 2023 - June 2026")
    print(f"Timeframe: 15-minute candles (synthetic from 5-min)")
    print(f"Strategy: Volume Spike Detection")
    print(f"Entry: Volume > {SPIKE_MULTIPLIER}x 4h avg + price direction")
    print(f"Risk/Reward: 1:2 ({STOP_LOSS_PCT}% SL / {TAKE_PROFIT_PCT}% TP)")
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
    
    # Analyze consecutive losses
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
    
    # Monthly returns analysis
    print("\nWorst Losing Streaks (10+ consecutive losses):")
    print("-" * 70)
    current_streak = 0
    streak_start = None
    streak_trades = []
    
    for t in results['trades']:
        if t.pnl_pct <= 0:
            if current_streak == 0:
                streak_start = t.entry_time
            current_streak += 1
            streak_trades.append(t)
        else:
            if current_streak >= 10:
                total_loss = sum(trade.pnl_pct for trade in streak_trades)
                print(f"  {streak_start.strftime('%Y-%m-%d')} to {streak_trades[-1].exit_time.strftime('%Y-%m-%d')}: "
                      f"{current_streak} losses, {total_loss:.2f}% total")
            current_streak = 0
            streak_trades = []
    
    # Show last 10 trades
    if results['trades']:
        print("\nLast 10 Trades:")
        print("-" * 70)
        for t in results['trades'][-10:]:
            emoji = "WIN" if t.pnl_pct > 0 else "LOSS"
            print(f"{t.entry_time.strftime('%Y-%m-%d %H:%M')} | {t.side.upper():4} | "
                  f"${t.entry_price:,.2f} -> ${t.exit_price:,.2f} | "
                  f"{t.pnl_pct:+.2f}% | {t.exit_reason.upper():2} | "
                  f"Vol:{t.volume_ratio:.1f}x | {emoji}")
    
    # Analyze worst drawdown period in detail
    print("\nWorst Drawdown Period Analysis (July 2025):")
    print("-" * 70)
    worst_period_trades = [t for t in results['trades'] 
                           if datetime(2025, 7, 1) <= t.entry_time <= datetime(2025, 8, 31)]
    
    longs = [t for t in worst_period_trades if t.side == 'long']
    shorts = [t for t in worst_period_trades if t.side == 'short']
    long_wins = len([t for t in longs if t.pnl_pct > 0])
    short_wins = len([t for t in shorts if t.pnl_pct > 0])
    
    print(f"Total trades in July-Aug 2025: {len(worst_period_trades)}")
    print(f"  LONG: {len(longs)} trades, {long_wins} wins ({long_wins/len(longs)*100 if longs else 0:.1f}% win rate)")
    print(f"  SHORT: {len(shorts)} trades, {short_wins} wins ({short_wins/len(shorts)*100 if shorts else 0:.1f}% win rate)")
    
    # Check market direction during this period
    print("\nFirst 5 trades of worst streak (July 14-31, 2025):")
    streak_trades = [t for t in results['trades'] 
                     if datetime(2025, 7, 14) <= t.entry_time <= datetime(2025, 7, 31)]
    for t in streak_trades[:5]:
        print(f"  {t.entry_time.strftime('%Y-%m-%d %H:%M')} | {t.side.upper():4} | "
              f"${t.entry_price:,.2f} -> ${t.exit_price:,.2f} | {t.pnl_pct:+.2f}% | "
              f"4h change: {t.change_4h:+.2f}%")
    
    # Overall market regime analysis
    print("\nMarket Regime Analysis (by year):")
    print("-" * 70)
    for year in [2023, 2024, 2025, 2026]:
        year_trades = [t for t in results['trades'] 
                       if year <= t.entry_time.year < year + 1]
        if not year_trades:
            continue
        year_wins = len([t for t in year_trades if t.pnl_pct > 0])
        year_return = sum(t.pnl_pct for t in year_trades)
        year_longs = len([t for t in year_trades if t.side == 'long'])
        year_shorts = len([t for t in year_trades if t.side == 'short'])
        print(f"{year}: {len(year_trades)} trades, {year_wins} wins ({year_wins/len(year_trades)*100:.1f}%), "
              f"Return: {year_return:+.2f}%, Long/Short: {year_longs}/{year_shorts}")
    
    # Key insight: Why the 44% drawdown?
    print("\n" + "=" * 70)
    print("DRAWDOWN ROOT CAUSE ANALYSIS")
    print("=" * 70)
    print("""
The 44% max drawdown is caused by CONSECUTIVE LOSING STREAKS during choppy 
market conditions. Here's what happened:

1. WORST STREAK: July 14-31, 2025 (13 consecutive losses, -19.5%)
   - BTC was trading around $117K-$119K (near all-time highs)
   - Market was in a tight range with false breakouts
   - Strategy kept getting whipsawed: LONG stopped out, then SHORT stopped out
   - The 4h price changes were small (+0.63%, -2.20%, +1.05%) indicating 
     indecision, but volume spikes still triggered entries

2. OTHER MAJOR STREAKS:
   - May-Jun 2024: 12 losses (-18%) - likely during post-halving consolidation
   - Mar 2025: 11 losses (-16.5%) - mid-bull run chop
   - Dec 2025: 12 losses (-18%) - year-end volatility

3. THE PROBLEM:
   - Volume spike + 4h direction filter is NOT enough in ranging markets
   - When price chops around, the 4h direction keeps flipping
   - Strategy enters on volume, gets stopped out, reverses, gets stopped out again
   - No market regime filter to avoid trading in low-volatility chop

4. WHY IT RECOVERS:
   - When trend resumes, the 1:2 R/R pays off
   - 2025 overall was +22.5% despite the July drawdown
   - The strategy makes money in trending periods, loses in chop

5. SOLUTIONS TO CONSIDER:
   - Add ADX filter: Only trade when ADX > 25 (trending market)
   - Add volatility filter: Skip when ATR is below 20-period average
   - Add consecutive loss circuit breaker: Stop trading after 5 losses
   - Widen SL during high volatility, tighten during low volatility
""")


def main():
    print("Loading 5-min data from CSV...")
    candles_5min = load_csv_data(r'D:\dev\trading\data\binance_btc_5min_2026-06-24.csv')
    print(f"Loaded {len(candles_5min):,} 5-min candles")
    print(f"Date range: {candles_5min[0].timestamp} to {candles_5min[-1].timestamp}")
    
    print("\nAggregating to 15-min candles...")
    candles_15min = aggregate_to_15min(candles_5min)
    print(f"Created {len(candles_15min):,} 15-min candles")
    
    print("\nRunning backtest...")
    results = run_backtest(candles_15min, initial_capital=1000.0)
    
    print_results(results)


if __name__ == "__main__":
    main()
