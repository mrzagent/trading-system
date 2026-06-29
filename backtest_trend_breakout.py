#!/usr/bin/env python3
"""
Backtest Trend Following Breakout strategy on 3 years of BTC data from CSV.
Fresh backtest - ignores previous findings.
"""

import csv
import json
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

# Strategy parameters (from strategy_trend_following_breakout.py)
STRATEGY = "trend_following_breakout"
CANDLE_MINUTES = 240  # 4H candles (synthetic from 5-min data)
DONCHIAN_PERIOD = 20
EMA_FAST = 50
EMA_SLOW = 200
ATR_PERIOD = 14
ATR_SL_MULT = 2.0
ATR_TP_MULT = 4.0
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
    take_profit: float
    pnl_pct: float
    pnl_usd: float
    exit_reason: str
    atr: float
    ema50: float
    ema200: float


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


def aggregate_to_4h(candles_5min: List[Candle]) -> List[Candle]:
    """Aggregate 5-min candles to 4H candles."""
    candles_4h = []
    # 4 hours = 240 minutes = 48 five-minute candles
    for i in range(0, len(candles_5min) - 47, 48):
        chunk = candles_5min[i:i+48]
        if len(chunk) < 48:
            break
        
        open_price = chunk[0].open
        high_price = max(c.high for c in chunk)
        low_price = min(c.low for c in chunk)
        close_price = chunk[-1].close
        volume = sum(c.volume for c in chunk)
        
        candles_4h.append(Candle(
            timestamp=chunk[0].timestamp,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume
        ))
    
    return candles_4h


def calculate_ema(prices: List[float], period: int) -> List[float]:
    """Compute EMA series."""
    if len(prices) < period:
        return [float("nan")] * len(prices)
    
    ema_values = [float("nan")] * len(prices)
    multiplier = 2.0 / (period + 1)
    seed = sum(prices[:period]) / period
    ema_values[period - 1] = seed
    
    for i in range(period, len(prices)):
        ema_values[i] = (prices[i] - ema_values[i - 1]) * multiplier + ema_values[i - 1]
    
    return ema_values


def calculate_donchian(highs: List[float], lows: List[float], period: int) -> Tuple[float, float]:
    """Donchian Channel: highest high and lowest low over last `period` bars (excluding current)."""
    lookback_highs = highs[-period - 1 : -1]
    lookback_lows = lows[-period - 1 : -1]
    if not lookback_highs or not lookback_lows:
        return float("nan"), float("nan")
    return max(lookback_highs), min(lookback_lows)


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
    """Run Trend Breakout backtest on 4H candles."""
    trades = []
    open_trade: Optional[Trade] = None
    
    capital = initial_capital
    max_capital = initial_capital
    max_drawdown = 0.0
    
    # Need at least EMA_SLOW + DONCHIAN_PERIOD + ATR_PERIOD candles
    min_rows = max(EMA_SLOW, DONCHIAN_PERIOD, ATR_PERIOD) + 10
    
    for i in range(min_rows, len(candles)):
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
        
        # Calculate indicators
        closes = [c.close for c in candles[:i+1]]
        highs = [c.high for c in candles[:i+1]]
        lows = [c.low for c in candles[:i+1]]
        
        ema_fast_series = calculate_ema(closes, EMA_FAST)
        ema_slow_series = calculate_ema(closes, EMA_SLOW)
        
        ema_fast = ema_fast_series[-1]
        ema_slow = ema_slow_series[-1]
        
        if ema_fast != ema_fast or ema_slow != ema_slow:
            continue
        
        bullish_trend = ema_fast > ema_slow
        bearish_trend = ema_fast < ema_slow
        
        donchian_high, donchian_low = calculate_donchian(highs, lows, DONCHIAN_PERIOD)
        if donchian_high != donchian_high or donchian_low != donchian_low:
            continue
        
        atr = calculate_atr(highs, lows, closes, ATR_PERIOD)
        if atr != atr:
            continue
        
        # Check entry conditions
        broke_above = current_price > donchian_high
        broke_below = current_price < donchian_low
        
        trade_action = None
        if bullish_trend and broke_above:
            trade_action = "BUY"
        elif bearish_trend and broke_below:
            trade_action = "SELL"
        
        if not trade_action:
            continue
        
        # Open new trade
        side = 'long' if trade_action == "BUY" else 'short'
        stop_loss_dist = atr * ATR_SL_MULT
        take_profit_dist = atr * ATR_TP_MULT
        
        if side == 'long':
            stop_loss = current_price - stop_loss_dist
            take_profit = current_price + take_profit_dist
        else:
            stop_loss = current_price + stop_loss_dist
            take_profit = current_price - take_profit_dist
        
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
            atr=atr,
            ema50=ema_fast,
            ema200=ema_slow
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
    print("TREND FOLLOWING BREAKOUT STRATEGY BACKTEST RESULTS - BTC 3 YEARS")
    print("=" * 70)
    print(f"Period: June 2023 - June 2026")
    print(f"Timeframe: 4H candles (synthetic from 5-min)")
    print(f"Strategy: EMA50/200 Trend + Donchian Channel Breakout")
    print(f"Entry: EMA trend aligned + Close beyond Donchian 20")
    print(f"Risk/Reward: 1:2 (2x ATR SL / 4x ATR TP)")
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
                  f"{t.pnl_pct:+.2f}% | {t.exit_reason.upper():2} | "
                  f"ATR:${t.atr:,.2f} | {emoji}")


def main():
    print("Loading 5-min data from CSV...")
    candles_5min = load_csv_data(r'D:\dev\trading\data\binance_btc_5min_2026-06-24.csv')
    print(f"Loaded {len(candles_5min):,} 5-min candles")
    print(f"Date range: {candles_5min[0].timestamp} to {candles_5min[-1].timestamp}")
    
    print("\nAggregating to 4H candles...")
    candles_4h = aggregate_to_4h(candles_5min)
    print(f"Created {len(candles_4h):,} 4H candles")
    
    print("\nRunning backtest...")
    results = run_backtest(candles_4h, initial_capital=1000.0)
    
    print_results(results)


if __name__ == "__main__":
    main()
