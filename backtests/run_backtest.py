"""
Simple backtest runner with predefined strategies

Usage:
    python run_backtest.py --strategy fvg --coin BTC --timeframe 15m
    python run_backtest.py --strategy momentum --coin SOL --timeframe 5m --days 30
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest_engine import BacktestEngine, BacktestConfig


def simple_fvg_strategy(candles, idx):
    """Simple FVG detection strategy"""
    if idx < 3:
        return None
    
    c1 = candles[idx - 2]  # First candle
    c2 = candles[idx - 1]  # Gap candle
    c3 = candles[idx]      # Current candle
    
    # Bullish FVG: c1 high < c3 low
    if c1['high'] < c3['low']:
        return {
            'action': 'BUY',
            'entry': c3['close'],
            'stop_loss': c2['low'] * 0.995,
            'take_profit': c3['close'] * 1.03,
            'strategy': 'fvg'
        }
    
    # Bearish FVG: c1 low > c3 high
    if c1['low'] > c3['high']:
        return {
            'action': 'SELL',
            'entry': c3['close'],
            'stop_loss': c2['high'] * 1.005,
            'take_profit': c3['close'] * 0.97,
            'strategy': 'fvg'
        }
    
    return None


def simple_momentum_strategy(candles, idx):
    """Simple momentum strategy using 3-candle trend"""
    if idx < 3:
        return None
    
    # Calculate price change over last 3 candles
    price_change = (candles[idx]['close'] - candles[idx-3]['close']) / candles[idx-3]['close']
    
    # Bullish momentum
    if price_change > 0.005:  # 0.5% move
        return {
            'action': 'BUY',
            'entry': candles[idx]['close'],
            'stop_loss': candles[idx]['close'] * 0.985,
            'take_profit': candles[idx]['close'] * 1.04,
            'strategy': 'momentum'
        }
    
    # Bearish momentum
    if price_change < -0.005:
        return {
            'action': 'SELL',
            'entry': candles[idx]['close'],
            'stop_loss': candles[idx]['close'] * 1.015,
            'take_profit': candles[idx]['close'] * 0.96,
            'strategy': 'momentum'
        }
    
    return None


def mean_reversion_strategy(candles, idx):
    """Mean reversion using RSI-like overbought/oversold"""
    if idx < 14:
        return None
    
    # Calculate simple moving average
    sma = sum(c['close'] for c in candles[idx-14:idx]) / 14
    current = candles[idx]['close']
    deviation = (current - sma) / sma
    
    # Oversold - buy
    if deviation < -0.03:  # 3% below SMA
        return {
            'action': 'BUY',
            'entry': current,
            'stop_loss': current * 0.98,
            'take_profit': sma,  # Target the mean
            'strategy': 'mean_reversion'
        }
    
    # Overbought - sell
    if deviation > 0.03:
        return {
            'action': 'SELL',
            'entry': current,
            'stop_loss': current * 1.02,
            'take_profit': sma,
            'strategy': 'mean_reversion'
        }
    
    return None


STRATEGIES = {
    'fvg': simple_fvg_strategy,
    'momentum': simple_momentum_strategy,
    'mean_reversion': mean_reversion_strategy,
}


def main():
    parser = argparse.ArgumentParser(description="Run backtest")
    parser.add_argument("--strategy", required=True, choices=list(STRATEGIES.keys()),
                        help="Strategy to backtest")
    parser.add_argument("--coin", default="BTC", help="Coin symbol")
    parser.add_argument("--timeframe", default="15m", help="Timeframe")
    parser.add_argument("--days", type=int, help="Number of days to backtest")
    parser.add_argument("--risk", type=float, default=0.02, help="Risk per trade (default 2%)")
    parser.add_argument("--leverage", type=float, default=3.0, help="Leverage (default 3x)")
    parser.add_argument("--output", help="Save results to JSON file")
    
    args = parser.parse_args()
    
    # Calculate date range
    end_date = datetime.now()
    if args.days:
        start_date = end_date - timedelta(days=args.days)
    else:
        start_date = None
    
    # Create config
    config = BacktestConfig(
        risk_per_trade_pct=args.risk,
        leverage=args.leverage
    )
    
    # Run backtest
    engine = BacktestEngine(config)
    strategy_fn = STRATEGIES[args.strategy]
    
    result = engine.run_backtest(
        strategy_fn,
        args.coin,
        args.timeframe,
        start_date=start_date.isoformat() if start_date else None,
        end_date=end_date.isoformat()
    )
    
    # Print results
    engine.print_report(result)
    
    # Save if requested
    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = Path(__file__).parent / output_path
        
        with open(output_path, 'w') as f:
            json.dump(result.__dict__, f, indent=2, default=str)
        print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
