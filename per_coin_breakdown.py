#!/usr/bin/env python3
"""Per-coin breakdown for Oversold FVG strategy"""

import sys
sys.path.insert(0, r'D:\dev\trading')

from backtest import BacktestEngine

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

STRATEGY_CONFIG = {
    "rsi_max": 35,
    "min_fvg": 1
}

def test_coin(coin):
    print(f"\n{'='*60}")
    print(f"Testing: {coin}")
    print(f"{'='*60}")
    
    engine = BacktestEngine(**RISK_CONFIG)
    result = engine.run_backtest(
        table="trading_prices",
        start_date="2026-01-01",
        end_date="2026-06-14",
        coins=[coin],
        **STRATEGY_CONFIG
    )
    return result

if __name__ == "__main__":
    coins = ["BTC", "ETH", "SOL"]
    results = {}
    
    for coin in coins:
        results[coin] = test_coin(coin)
    
    # Summary
    print("\n" + "="*70)
    print("PER-COIN BREAKDOWN: Oversold FVG Strategy")
    print("="*70)
    print(f"{'Coin':<8} {'Final':>10} {'P&L':>10} {'Return':>8} {'Trades':>7} {'Win%':>6} {'MaxDD':>7}")
    print("-"*70)
    
    for coin, r in results.items():
        pnl = r.final_capital - r.initial_capital
        ret_pct = (r.final_capital / r.initial_capital - 1) * 100
        win_pct = (r.winning_trades / r.total_trades * 100) if r.total_trades > 0 else 0
        max_dd = getattr(r, 'max_drawdown_pct', getattr(r, 'max_drawdown', 0) * 100)
        print(f"{coin:<8} ${r.final_capital:>9,.2f} ${pnl:>9,.2f} {ret_pct:>7.1f}% {r.total_trades:>7} {win_pct:>5.1f}% {max_dd:>6.1f}%")
    
    print("="*70)
    
    # Combined (should match our previous run)
    print("\n" + "="*70)
    print("COMBINED (all 3 coins)")
    print("="*70)
    engine = BacktestEngine(**RISK_CONFIG)
    combined = engine.run_backtest(
        table="trading_prices",
        start_date="2026-01-01",
        end_date="2026-06-14",
        coins=["BTC", "ETH", "SOL"],
        **STRATEGY_CONFIG
    )
    pnl = combined.final_capital - combined.initial_capital
    ret_pct = (combined.final_capital / combined.initial_capital - 1) * 100
    win_pct = (combined.winning_trades / combined.total_trades * 100) if combined.total_trades > 0 else 0
    max_dd = getattr(combined, 'max_drawdown_pct', getattr(combined, 'max_drawdown', 0) * 100)
    print(f"{'ALL':<8} ${combined.final_capital:>9,.2f} ${pnl:>9,.2f} {ret_pct:>7.1f}% {combined.total_trades:>7} {win_pct:>5.1f}% {max_dd:>6.1f}%")
    print("="*70)
