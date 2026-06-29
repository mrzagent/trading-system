"""
Trading Bot Runner
Main entry point for the automated trading system
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

# Import our modules
sys.path.insert(0, r'D:\dev\trading')
from trade_executor import RiskConfig, TradeExecutor
from signal_integrator import SignalIntegrator, run_signal_cycle, load_account_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# Default risk configuration - ADJUST THESE VALUES
DEFAULT_RISK_CONFIG = {
    "initial_capital": 1000.0,        # $1,000 testnet account
    "risk_per_trade_pct": 0.02,       # 2% risk per trade ($20)
    "stop_loss_pct": 0.05,            # 5% stop loss
    "take_profit_pct": 0.10,          # 10% take profit (2:1 R:R)
    "max_position_pct": 0.50,         # Max 50% of capital per position
    "max_open_positions": 3,          # Max 3 concurrent positions
    "commission_pct": 0.001,          # 0.1% commission
    "slippage_pct": 0.0005,           # 0.05% slippage
    "leverage": 3.0                   # 3x leverage (adjust as needed)
}


def load_risk_config(config_path: Optional[str] = None) -> RiskConfig:
    """Load risk config from file or use defaults"""
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config_dict = json.load(f)
        logger.info(f"Loaded risk config from {config_path}")
        return RiskConfig(**config_dict)
    
    logger.info("Using default risk configuration")
    return RiskConfig(**DEFAULT_RISK_CONFIG)


def save_risk_config(config: RiskConfig, path: str = 'risk_config.json'):
    """Save risk config to file"""
    config_dict = {
        'initial_capital': config.initial_capital,
        'risk_per_trade_pct': config.risk_per_trade_pct,
        'stop_loss_pct': config.stop_loss_pct,
        'take_profit_pct': config.take_profit_pct,
        'max_position_pct': config.max_position_pct,
        'max_open_positions': config.max_open_positions,
        'commission_pct': config.commission_pct,
        'slippage_pct': config.slippage_pct,
        'leverage': config.leverage
    }
    with open(path, 'w') as f:
        json.dump(config_dict, f, indent=2)
    logger.info(f"Saved risk config to {path}")


def run_once(signal_file: Optional[str] = None, 
             test_mode: bool = True,
             dry_run: bool = False,
             risk_config_path: Optional[str] = None):
    """Run one trading cycle"""
    logger.info("="*60)
    logger.info(f"Starting trading cycle - {datetime.now().isoformat()}")
    logger.info(f"Mode: {'TEST (Paper)' if test_mode else 'LIVE'}")
    logger.info("="*60)
    
    # Load risk configuration
    risk_config = load_risk_config(risk_config_path)
    
    # Log risk parameters
    logger.info(f"""
Risk Configuration:
  Initial Capital: ${risk_config.initial_capital:,.2f}
  Risk Per Trade: {risk_config.risk_per_trade_pct*100:.1f}% (${risk_config.risk_per_trade:.2f})
  Stop Loss: {risk_config.stop_loss_pct*100:.1f}%
  Take Profit: {risk_config.take_profit_pct*100:.1f}%
  Leverage: {risk_config.leverage:.0f}x
  Max Position: {risk_config.max_position_pct*100:.0f}%
  Max Positions: {risk_config.max_open_positions}
    """)
    
    # Run the cycle
    results = run_signal_cycle(
        signal_file=signal_file,
        test_mode=test_mode,
        dry_run=dry_run
    )
    
    logger.info(f"Cycle complete. Executed {len(results)} trades.")
    return results


def run_daemon(interval_minutes: int = 5, 
               signal_dir: str = 'signals',
               test_mode: bool = True,
               risk_config_path: Optional[str] = None):
    """
    Run as daemon, checking for signals periodically
    
    Args:
        interval_minutes: How often to check for new signals
        signal_dir: Directory to watch for signal files
        test_mode: Run in paper trading mode
        risk_config_path: Path to risk configuration file
    """
    logger.info(f"Starting trading daemon (interval: {interval_minutes}m)")
    
    # Load account settings (cooldown from .account_settings.json)
    account_settings = load_account_settings()
    logger.info(f"Account settings: cooldown={account_settings['cooldown_minutes']}m, allow_multiple_positions={account_settings['allow_multiple_positions']}, position_size={account_settings.get('position_size_pct', 2.0)}%")
    
    risk_config = load_risk_config(risk_config_path)
    integrator = SignalIntegrator(
        risk_config=risk_config,
        test_mode=test_mode,
        min_confidence=0.7
        # cooldown_minutes and allow_multiple_positions loaded from .account_settings.json
    )
    
    processed_files = set()
    
    try:
        while True:
            logger.info(f"Daemon cycle - {datetime.now().isoformat()}")
            
            # 1. Check and manage existing positions
            integrator.check_and_manage_positions()
            
            # 2. Look for new signal files
            if os.path.exists(signal_dir):
                for filename in os.listdir(signal_dir):
                    if not filename.endswith('.json'):
                        continue
                    
                    filepath = os.path.join(signal_dir, filename)
                    file_id = f"{filename}_{os.path.getmtime(filepath)}"
                    
                    if file_id not in processed_files:
                        logger.info(f"Processing new signal file: {filename}")
                        
                        signals = integrator.load_signals_from_file(filepath)
                        if signals:
                            integrator.process_signals(signals)
                        
                        processed_files.add(file_id)
                        
                        # Keep processed_files from growing too large
                        if len(processed_files) > 1000:
                            processed_files = set(list(processed_files)[-500:])
            
            # 3. Print status
            integrator.print_status()
            
            # 4. Sleep until next cycle
            logger.info(f"Sleeping for {interval_minutes} minutes...")
            time.sleep(interval_minutes * 60)
            
    except KeyboardInterrupt:
        logger.info("Daemon stopped by user")
    except Exception as e:
        logger.error(f"Daemon error: {e}", exc_info=True)
        raise


def init_config():
    """Initialize default configuration files"""
    # Save default risk config
    risk_config = RiskConfig(**DEFAULT_RISK_CONFIG)
    save_risk_config(risk_config, 'risk_config.json')
    
    # Create example signal file
    example_signal = {
        "strategy": "fvg_proximity",
        "coin": "BTC",
        "action": "BUY",
        "confidence": 0.85,
        "reason": "Example signal - price near FVG",
        "meta": {
            "price": 64127.0,
            "fvg": {
                "type": "bullish",
                "midpoint": 64101.42
            }
        },
        "generated_at": datetime.now().isoformat()
    }
    
    os.makedirs('signals', exist_ok=True)
    with open('signals/example_signal.json', 'w') as f:
        json.dump(example_signal, f, indent=2)
    
    print("[OK] Configuration initialized!")
    print("   - risk_config.json created with default settings")
    print("   - signals/example_signal.json created as template")
    print("\nEdit risk_config.json to adjust your risk parameters")


def main():
    parser = argparse.ArgumentParser(
        description='Hyperliquid Trading Bot',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize config files
  python trading_bot.py init
  
  # Run once with default settings (test mode)
  python trading_bot.py run
  
  # Run once with a specific signal file
  python trading_bot.py run --signal signals/fvg_2026-06-14_1629.json
  
  # Run as daemon (checks every 5 minutes)
  python trading_bot.py daemon --interval 5
  
  # Dry run (simulate only, no trades)
  python trading_bot.py run --dry-run
  
  # Custom risk config
  python trading_bot.py run --config my_risk_config.json
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Init command
    init_parser = subparsers.add_parser('init', help='Initialize configuration files')
    
    # Run command
    run_parser = subparsers.add_parser('run', help='Run one trading cycle')
    run_parser.add_argument('--signal', '-s', help='Path to signal JSON file')
    run_parser.add_argument('--live', action='store_true', help='Run in live mode (default: test)')
    run_parser.add_argument('--dry-run', action='store_true', help='Simulate only, do not trade')
    run_parser.add_argument('--config', '-c', help='Path to risk config JSON')
    
    # Daemon command
    daemon_parser = subparsers.add_parser('daemon', help='Run as daemon')
    daemon_parser.add_argument('--interval', '-i', type=int, default=5,
                              help='Check interval in minutes (default: 5)')
    daemon_parser.add_argument('--signal-dir', '-d', default='signals',
                              help='Directory to watch for signals (default: signals)')
    daemon_parser.add_argument('--live', action='store_true', help='Run in live mode')
    daemon_parser.add_argument('--config', '-c', help='Path to risk config JSON')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show current status')
    status_parser.add_argument('--config', '-c', help='Path to risk config JSON')
    
    args = parser.parse_args()
    
    if args.command == 'init':
        init_config()
    
    elif args.command == 'run':
        run_once(
            signal_file=args.signal,
            test_mode=not args.live,
            dry_run=args.dry_run,
            risk_config_path=args.config
        )
    
    elif args.command == 'daemon':
        run_daemon(
            interval_minutes=args.interval,
            signal_dir=args.signal_dir,
            test_mode=not args.live,
            risk_config_path=args.config
        )
    
    elif args.command == 'status':
        risk_config = load_risk_config(args.config)
        integrator = SignalIntegrator(risk_config=risk_config, test_mode=True)
        integrator.print_status()
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
