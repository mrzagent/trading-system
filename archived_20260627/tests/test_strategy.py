#!/usr/bin/env python3
"""Test the new Oversold FVG Bounce strategy"""

import sys
sys.path.insert(0, r'D:\dev\trading')

from backtest import BacktestEngine, DatabaseConnector
from datetime import datetime

# Strategy: Oversold FVG
# Entry: RSI < 35, FVG >= 1
STRATEGY_CONFIG = {
    "rsi_max": 35,
    "min_fvg": 1
}

RISK_CONFIG = {
    "initial_capital": 1000,
    "risk_per_trade": 0.02,
    "stop_loss_pct": 0.05,
    "risk_reward": 2.0,
    "max_position_pct": 0.50,
    "commission": 0.001,
    "slippage": 0.0005,
    "max_bars": 20
}

def run_test(timeframe, table):
    print(f"\n{'='*60}")
    print(f"Testing: {timeframe} (table: {table})")
    print(f"Strategy: Oversold FVG")
    print(f"  - RSI: < {STRATEGY_CONFIG['rsi_max']}")
    print(f"  - FVG: >= {STRATEGY_CONFIG['min_fvg']}")
    print(f"Capital: ${RISK_CONFIG['initial_capital']}, Risk: {RISK_CONFIG['risk_per_trade']*100}% per trade")
    print(f"{'='*60}\n")
    
    engine = BacktestEngine(**RISK_CONFIG)
    result = engine.run_backtest(
        table=table,
        start_date="2026-01-01",
        end_date="2026-06-14",
        coins=["BTC", "ETH", "SOL"],
        **STRATEGY_CONFIG
    )
    
    return result

if __name__ == "__main__":
    results = {}
    
    # Test all timeframes
    for tf, table in [("5min", "trading_prices"), ("1h", "trading_prices_1h"), ("4h", "trading_prices_4h")]:
        results[tf] = run_test(tf, table)
    
    # Summary
    print("\n" + "="*70)
    print("STRATEGY COMPARISON: Oversold FVG Bounce")
    print("="*70)
    print(f"{'Timeframe':<10} {'Final':>10} {'P&L':>10} {'Return':>8} {'Trades':>7} {'Win%':>6} {'MaxDD':>7}")
    print("-"*70)
    for tf, r in results.items():
        pnl = r.final_capital - r.initial_capital
        ret_pct = (r.final_capital / r.initial_capital - 1) * 100
        win_pct = (r.winning_trades / r.total_trades * 100) if r.total_trades > 0 else 0
        max_dd = getattr(r, 'max_drawdown_pct', getattr(r, 'max_drawdown', 0))
        print(f"{tf:<10} ${r.final_capital:>9,.2f} ${pnl:>9,.2f} {ret_pct:>7.1f}% {r.total_trades:>7} {win_pct:>5.1f}% {max_dd:>6.1f}%")
    print("="*70)
