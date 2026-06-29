#!/usr/bin/env python3
"""
Orchestrator Trading Runner
Runs the orchestrator for all coins and executes trades via signal integrator
"""

import sys
sys.path.insert(0, r'D:\dev\trading')

import json
import logging
import os
from datetime import datetime, timezone

from orchestrator import analyse, COINS, get_conn, load_account_settings
from signal_integrator import SignalIntegrator
from trade_executor import RiskConfig
from db import save_signal

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('orchestrator_trading.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Risk configuration
RISK_CONFIG = RiskConfig(
    initial_capital=1000.0,
    risk_per_trade_pct=0.02,
    stop_loss_pct=0.05,
    take_profit_levels=[{"level": 0.10, "close_pct": 1.0, "label": "TP1"}],
    max_position_pct=0.50,
    max_open_positions=3,
    commission_pct=0.001,
    slippage_pct=0.0005,
    leverage=3.0
)


def run_orchestrator_trading(test_mode: bool = True, dry_run: bool = False):
    """
    Run orchestrator for all coins and execute trades
    
    Args:
        test_mode: If True, use paper trading (testnet)
        dry_run: If True, simulate only without placing orders
    """
    logger.info("=" * 70)
    logger.info("ORCHESTRATOR TRADING RUNNER")
    logger.info(f"Mode: {'TEST (Paper)' if test_mode else 'LIVE'} | Dry Run: {dry_run}")
    logger.info("=" * 70)
    
    # Load account settings (cooldown from .account_settings.json)
    account_settings = load_account_settings()
    logger.info(f"Account settings: cooldown={account_settings['cooldown_minutes']}m, allow_multiple_positions={account_settings['allow_multiple_positions']}, position_size={account_settings.get('position_size_pct', 2.0)}%")
    
    # Initialize signal integrator (cooldown loaded from .account_settings.json)
    integrator = SignalIntegrator(
        risk_config=RISK_CONFIG,
        test_mode=test_mode,
        min_confidence=0.6  # Lower threshold for orchestrator (already aggregated)
    )
    
    # Check and manage existing positions first
    logger.info("\n[1] Checking existing positions...")
    integrator.check_and_manage_positions()
    
    # Get database connection
    conn = get_conn()
    candle_start = datetime.now(timezone.utc)
    
    # Run orchestrator for each coin
    logger.info(f"\n[2] Running orchestrator for {len(COINS)} coins...")
    signals_generated = []
    
    for coin in COINS:
        logger.info(f"\n  >>> Analyzing {coin}...")
        
        try:
            # Run orchestrator analysis
            result = analyse(coin, conn, candle_start)
            
            action = result.get('action', 'HOLD')
            confidence = result.get('confidence', 0)
            meta = result.get('meta', {})
            
            logger.info(f"      Signal: {action} (confidence: {confidence:.2%})")
            logger.info(f"      Strategies run: {meta.get('strategies_run', 0)}/{meta.get('strategies_total', 0)}")
            
            # Only process BUY or SELL signals (not HOLD)
            if action in ['BUY', 'SELL'] and confidence >= 0.6:
                # Build signal for integrator with strategy-specific SL/TP
                signal = {
                    'strategy': 'orchestrator',
                    'coin': coin,
                    'action': action,
                    'confidence': confidence,
                    'reason': result.get('reason', 'Orchestrator aggregated signal'),
                    'meta': {
                        'price': meta.get('price', 0),
                        'strategy_breakdown': meta.get('strategy_breakdown', {}),
                        'quorum_required': meta.get('quorum_required', 0),
                        'candle': meta.get('candle', candle_start.isoformat()),
                        # Strategy-specific SL/TP from dominant strategy
                        'stop_loss_pct': meta.get('stop_loss_pct'),
                        'take_profit_pct': meta.get('take_profit_pct'),
                        'use_atr': meta.get('use_atr', False),
                        'atr_sl_mult': meta.get('atr_sl_mult'),
                        'atr_tp_mult': meta.get('atr_tp_mult'),
                        'dominant_strategy': meta.get('dominant_strategy', 'unknown')
                    },
                    'generated_at': datetime.now(timezone.utc).isoformat()
                }
                
                # Log the SL/TP being used
                sl = meta.get('stop_loss_pct', 'default')
                tp = meta.get('take_profit_pct', 'default')
                dominant = meta.get('dominant_strategy', 'unknown')
                logger.info(f"      -> SL/TP: {sl}% / {tp}% (from {dominant})")
                logger.info(f"      -> Signal queued for execution")
                signals_generated.append(signal)
            else:
                logger.info(f"      -> No trade signal (HOLD or low confidence)")
                
        except Exception as e:
            logger.error(f"      ERROR analyzing {coin}: {e}")
    
    # Save signals to database (even in dry-run, for dashboard display)
    logger.info(f"\n[2b] Saving {len(signals_generated)} signals to database...")
    for signal in signals_generated:
        try:
            save_signal(conn, signal, table='trading_signals')
            logger.info(f"  -> Saved signal for {signal['coin']} to database")
        except Exception as e:
            logger.error(f"  ERROR saving signal for {signal['coin']}: {e}")
    
    conn.close()
    
    # Execute signals
    logger.info(f"\n[3] Executing {len(signals_generated)} signals...")
    executed_trades = []
    
    for signal in signals_generated:
        try:
            result = integrator.process_signal(signal, dry_run=dry_run)
            if result:
                executed_trades.append(result)
                logger.info(f"  -> Executed: {signal['coin']} {signal['action']}")
            else:
                logger.info(f"  -> Skipped: {signal['coin']} (cooldown or other filter)")
        except Exception as e:
            logger.error(f"  ERROR executing signal for {signal['coin']}: {e}")
    
    # Print summary
    logger.info("\n" + "=" * 70)
    logger.info("TRADING SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Coins analyzed: {len(COINS)}")
    logger.info(f"Signals generated: {len(signals_generated)}")
    logger.info(f"Trades executed: {len(executed_trades)}")
    
    if executed_trades:
        logger.info("\nExecuted trades:")
        for trade in executed_trades:
            logger.info(f"  - {trade.get('coin')}: {trade.get('action')} @ ${trade.get('entry_price', 0):,.2f}")
    
    integrator.print_status()
    
    return executed_trades


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Run orchestrator and execute trades')
    parser.add_argument('--live', action='store_true', help='Run in live mode (default: test)')
    parser.add_argument('--dry-run', action='store_true', help='Simulate only, no actual trades')
    
    args = parser.parse_args()
    
    run_orchestrator_trading(
        test_mode=not args.live,
        dry_run=args.dry_run
    )
