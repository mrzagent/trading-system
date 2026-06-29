#!/usr/bin/env python3
"""
run_confluence_strategy.py — Run the Momentum + RSI Confluence strategy
This is the main entry point for the confluence trading strategy.
"""
import sys
sys.path.insert(0, r"D:\dev\trading")

from strategy_momentum_rsi import main as run_strategy
from signal_integrator import SignalIntegrator, RiskConfig, load_account_settings
import json

def main():
    print("="*60)
    print("MOMENTUM + RSI CONFLUENCE STRATEGY")
    print("="*60)
    print()
    
    # Run the strategy to generate signals
    import io
    from contextlib import redirect_stdout
    
    # Capture the strategy output
    output_buffer = io.StringIO()
    with redirect_stdout(output_buffer):
        run_strategy()
    
    # Get the captured output and parse it
    output = output_buffer.getvalue()
    
    # Find the JSON part (signals are printed as JSON)
    try:
        signals = json.loads(output)
    except json.JSONDecodeError:
        print("Error parsing strategy output:")
        print(output)
        return
    
    print("Generated Signals:")
    print("-" * 70)
    print(f"{'Coin':6} | {'Action':6} | {'Price':>12} | {'Mom':>8} | {'RSI 15m/1h':>10}")
    print("-" * 70)
    
    actionable_signals = []
    for sig in signals:
        coin = sig.get('coin', 'UNKNOWN')
        action = sig.get('action', 'HOLD')
        confidence = sig.get('confidence', 0)
        reason = sig.get('reason', '')
        meta = sig.get('meta', {})
        price = meta.get('price', 0)
        momentum = meta.get('momentum', 0)
        rsi_15m = meta.get('rsi_15m', 0)
        rsi_1h = meta.get('rsi_1h', 0)
        
        print(f"{coin:6} | {action:6} | ${price:>10,.2f} | {momentum:>+7.2f}% | {rsi_15m:>4.1f}/{rsi_1h:<4.1f}")
        
        if action != 'HOLD':
            actionable_signals.append(sig)
    
    print("-" * 70)
    print(f"Total signals: {len(signals)}, Actionable: {len(actionable_signals)}")
    print()
    
    # Process signals through integrator
    if actionable_signals:
        print("Processing signals through integrator...")
        
        # Create integrator with confluence-specific settings
        risk_config = RiskConfig(
            leverage=3.0,
            stop_loss_pct=0.02,  # 2% stop loss
            take_profit_levels=[  # 6% take profit (3:1 RR)
                {"level": 0.06, "close_pct": 1.0, "label": "TP1"}
            ],
            risk_per_trade_pct=0.02   # 2% risk per trade
        )
        
        # Load account settings (cooldown from .account_settings.json)
        account_settings = load_account_settings()
        print(f"Account settings: cooldown={account_settings['cooldown_minutes']}m, allow_multiple_positions={account_settings['allow_multiple_positions']}, position_size={account_settings.get('position_size_pct', 2.0)}%")
        
        integrator = SignalIntegrator(
            risk_config=risk_config,
            test_mode=True,  # Always test mode for now
            min_confidence=0.5  # Lower threshold for confluence (was 0.7)
            # cooldown_minutes loaded from .account_settings.json
        )
        
        # Check existing positions
        integrator.check_and_manage_positions()
        
        # Process signals (dry run first)
        results = integrator.process_signals(actionable_signals, dry_run=True)
        
        print(f"\nSimulated {len(results)} trades")
        
        for result in results:
            print(f"\n  {result['coin']} {result['side'].upper()}")
            print(f"    Entry: ${result['entry_price']:,.2f}")
            print(f"    Size: {result['position_size']:.4f}")
            print(f"    Margin: ${result['margin_required']:,.2f}")
            print(f"    SL: ${result['stop_loss']:,.2f}")
            print(f"    TP: ${result['take_profit']:,.2f}")
    else:
        print("No actionable signals generated.")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    main()
