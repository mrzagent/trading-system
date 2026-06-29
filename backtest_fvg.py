#!/usr/bin/env python3
"""
Backtest FVG strategy on 3 years of BTC data from CSV.
Fresh backtest - ignores previous findings.
"""

import csv
import json
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

# Strategy parameters (from strategy_fvg.py)
STRATEGY = "fvg_breakout_confirm"
CANDLE_MINUTES = 15  # 15-min candles (synthetic from 5-min data)
FVG_LOOKBACK = 20
FVG_MAX_AGE = 6
MIN_FVG_SIZE_PCT = 0.02
BREAK_THRESHOLD_PCT = 0.01
STOP_LOSS_PCT = 1.5
TAKE_PROFIT_PCT = 3.0
COOLDOWN_MINUTES = 60


@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0


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
    exit_reason: str  # 'tp', 'sl', 'open'
    fvg_size_pct: float
    fvg_age: int
    fvg_type: str


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


def detect_fvgs(candles: List[Candle], current_idx: int) -> List[Dict]:
    """Detect FVGs in recent candles."""
    fvgs = []
    start_idx = max(1, current_idx - FVG_LOOKBACK)
    
    for i in range(start_idx, current_idx):
        if i < 1 or i >= len(candles) - 1:
            continue
        prev = candles[i - 1]
        nxt = candles[i + 1]
        
        # Bullish FVG: prev.high < next.low
        if prev.high < nxt.low:
            gap_size = nxt.low - prev.high
            gap_size_pct = (gap_size / prev.high) * 100
            if gap_size_pct >= MIN_FVG_SIZE_PCT:
                fvgs.append({
                    "type": "bullish",
                    "bottom": prev.high,
                    "top": nxt.low,
                    "midpoint": (prev.high + nxt.low) / 2,
                    "formed_at_idx": i,
                    "age": current_idx - i,
                    "size_pct": gap_size_pct
                })
        # Bearish FVG: prev.low > next.high
        elif prev.low > nxt.high:
            gap_size = prev.low - nxt.high
            gap_size_pct = (gap_size / prev.low) * 100
            if gap_size_pct >= MIN_FVG_SIZE_PCT:
                fvgs.append({
                    "type": "bearish",
                    "top": prev.low,
                    "bottom": nxt.high,
                    "midpoint": (prev.low + nxt.high) / 2,
                    "formed_at_idx": i,
                    "age": current_idx - i,
                    "size_pct": gap_size_pct
                })
    
    fvgs.sort(key=lambda x: x["age"])
    return fvgs


def check_fvg_breakout(price: float, fvgs: List[Dict]) -> Tuple[str, Optional[Dict]]:
    """Check if price has broken through any FVG."""
    for fvg in fvgs:
        if fvg["age"] < 1 or fvg["age"] > FVG_MAX_AGE:
            continue
        
        ftype = fvg["type"]
        bottom = fvg["bottom"]
        top = fvg["top"]
        break_buffer = (top - bottom) * (BREAK_THRESHOLD_PCT / 100)
        
        if ftype == "bullish" and price < (bottom - break_buffer):
            return "SELL", fvg
        elif ftype == "bearish" and price > (top + break_buffer):
            return "BUY", fvg
    
    return "HOLD", None


def run_backtest(candles: List[Candle], initial_capital: float = 1000.0) -> Dict:
    """Run FVG backtest on 15-min candles."""
    trades = []
    open_trade: Optional[Trade] = None
    cooldown_until: Optional[datetime] = None
    
    capital = initial_capital
    max_capital = initial_capital
    max_drawdown = 0.0
    
    # Need at least FVG_LOOKBACK + 5 candles to start
    for i in range(FVG_LOOKBACK + 5, len(candles) - 1):
        current_candle = candles[i]
        previous_candle = candles[i - 1]
        current_price = current_candle.close
        prev_price = previous_candle.close
        
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
                    cooldown_until = current_candle.timestamp + timedelta(minutes=COOLDOWN_MINUTES)
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
                    cooldown_until = current_candle.timestamp + timedelta(minutes=COOLDOWN_MINUTES)
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
                    cooldown_until = current_candle.timestamp + timedelta(minutes=COOLDOWN_MINUTES)
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
                    cooldown_until = current_candle.timestamp + timedelta(minutes=COOLDOWN_MINUTES)
                    continue
            
            continue  # Still in trade, skip signal generation
        
        # Check cooldown
        if cooldown_until and current_candle.timestamp < cooldown_until:
            continue
        
        # Detect FVGs at previous candle
        fvgs = detect_fvgs(candles, i - 1)
        if not fvgs:
            continue
        
        # Check for breakout on previous candle
        prev_action, matched_fvg = check_fvg_breakout(prev_price, fvgs)
        if prev_action == "HOLD" or not matched_fvg:
            continue
        
        # CONFIRMATION: Check if current candle closed beyond FVG
        ftype = matched_fvg["type"]
        bottom = matched_fvg["bottom"]
        top = matched_fvg["top"]
        
        confirmed = False
        trade_action = None
        if prev_action == "SELL" and current_price < bottom:
            confirmed = True
            trade_action = "SELL"
        elif prev_action == "BUY" and current_price > top:
            confirmed = True
            trade_action = "BUY"
        
        if not confirmed:
            continue
        
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
            fvg_size_pct=matched_fvg["size_pct"],
            fvg_age=matched_fvg["age"],
            fvg_type=ftype
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
    print("FVG STRATEGY BACKTEST RESULTS - BTC 3 YEARS")
    print("=" * 70)
    print(f"Period: June 2023 - June 2026")
    print(f"Timeframe: 15-minute candles (synthetic from 5-min)")
    print(f"Strategy: FVG Breakout with Confirmation")
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
    
    # Show last 10 trades
    if results['trades']:
        print("\nLast 10 Trades:")
        print("-" * 70)
        for t in results['trades'][-10:]:
            emoji = "WIN" if t.pnl_pct > 0 else "LOSS"
            print(f"{t.entry_time.strftime('%Y-%m-%d %H:%M')} | {t.side.upper():4} | "
                  f"${t.entry_price:,.2f} -> ${t.exit_price:,.2f} | "
                  f"{t.pnl_pct:+.2f}% | {t.exit_reason.upper():2} | {emoji}")


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
