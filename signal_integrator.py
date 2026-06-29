"""
Signal Integration Module
Connects FVG/RSI/Momentum signals to the trade executor
"""

import json
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
from trade_executor import TradeExecutor, RiskConfig, execute_signal

logger = logging.getLogger(__name__)

# Path to account settings (managed by dashboard)
ACCOUNT_SETTINGS_PATH = Path(__file__).parent / ".account_settings.json"


def load_account_settings() -> dict:
    """Load account settings from .account_settings.json.
    
    Returns dict with cooldown_minutes, allow_multiple_positions, leverage, position_size_pct, and environment.
    """
    try:
        if ACCOUNT_SETTINGS_PATH.exists():
            with open(ACCOUNT_SETTINGS_PATH, 'r') as f:
                settings = json.load(f)
            
            env = settings.get('environment', 'testnet')
            env_config = settings.get(env, {})
            
            return {
                'cooldown_minutes': settings.get('cooldownMinutes', 30),
                'allow_multiple_positions': settings.get('allowMultiplePositions', False),
                'leverage': settings.get('leverage', 3),
                'stop_loss': settings.get('stopLoss', 5),
                'take_profit': settings.get('takeProfit', 10),
                'position_size_pct': settings.get('positionSizePct', 2.0),
                'environment': env,
                'api_url': env_config.get('apiUrl', 'https://api.hyperliquid-testnet.xyz'),
                'wallet_address': env_config.get('walletAddress', ''),
                'main_wallet_address': env_config.get('mainWalletAddress', env_config.get('walletAddress', '')),
                'private_key_env': env_config.get('privateKeyEnv', 'HYPERLIQUID_TESTNET_PRIVATE_KEY')
            }
    except Exception as e:
        logger.warning(f"Failed to load account settings: {e}")
    
    return {
        'cooldown_minutes': 30,
        'allow_multiple_positions': False,
        'leverage': 3,
        'stop_loss': 5,
        'take_profit': 10,
        'position_size_pct': 2.0,
        'environment': 'testnet',
        'api_url': 'https://api.hyperliquid-testnet.xyz',
        'wallet_address': '',
        'private_key_env': 'HYPERLIQUID_TESTNET_PRIVATE_KEY'
    }


# Strategy categories for cooldown/position grouping
STRATEGY_CATEGORIES = {
    # Scalp strategies (fast, short-term)
    'momentum_scalper': 'scalp',
    'vwap_reversion': 'scalp',
    'fvg_proximity': 'scalp',  # 5min timeframe
    'volume_spike': 'scalp',   # 5min timeframe
    
    # Swing strategies (slower, longer-term)
    'rsi_mean_reversion': 'swing',
    'momentum_rsi': 'swing',
    'momentum_accel': 'swing',
    'mean_reversion': 'swing',
    'trend_breakout': 'swing',
    'pullback_scalper': 'swing',
}


def get_strategy_category(strategy: str) -> str:
    """Get the category (scalp/swing) for a strategy."""
    return STRATEGY_CATEGORIES.get(strategy, 'swing')  # Default to swing


class SignalIntegrator:
    """
    Integrates trading signals from multiple sources and executes them
    with proper risk management and deduplication.
    """
    
    def __init__(self, risk_config: Optional[RiskConfig] = None, 
                 test_mode: bool = True,
                 min_confidence: float = 0.7,
                 cooldown_minutes: int = None,
                 allow_multiple_positions: bool = None):
        """
        Args:
            risk_config: Risk management configuration
            test_mode: If True, runs in paper trading mode
            min_confidence: Minimum signal confidence to execute (0-1)
            cooldown_minutes: Minimum minutes between trades on same coin (None = load from .account_settings.json)
            allow_multiple_positions: Whether to allow multiple positions per coin (None = load from .account_settings.json)
        """
        # Load settings from .account_settings.json if not explicitly provided
        account_settings = load_account_settings()
        
        # Create RiskConfig from account settings if not provided
        if risk_config is None:
            # Get actual account balance for position sizing (use main wallet)
            from hyperliquid.info import Info
            try:
                info = Info(account_settings['api_url'], skip_ws=True)
                # Use mainWalletAddress if available, otherwise fall back to walletAddress
                main_wallet = account_settings.get('main_wallet_address') or account_settings['wallet_address']
                # Get spot balance (real equity) not margin account value
                spot_state = info.spot_user_state(main_wallet)
                usdc_balance = 0.0
                for balance in spot_state.get('balances', []):
                    if balance.get('coin') == 'USDC':
                        usdc_balance = float(balance.get('total', 0))
                        break
                account_value = usdc_balance if usdc_balance > 0 else 1000.0
                logger.info(f"Spot balance for {main_wallet}: ${account_value:.2f} USDC")
            except Exception as e:
                logger.warning(f"Failed to get account balance: {e}, using default $1000")
                account_value = 1000.0
            
            self.risk_config = RiskConfig(
                initial_capital=account_value,
                risk_per_trade_pct=account_settings['position_size_pct'] / 100,  # Convert % to decimal
                leverage=account_settings['leverage'],
                stop_loss_pct=account_settings['stop_loss'] / 100,
                max_open_positions=3 if not account_settings['allow_multiple_positions'] else 10
            )
        else:
            self.risk_config = risk_config
        
        self.executor = TradeExecutor(self.risk_config)
        self.test_mode = test_mode
        self.min_confidence = min_confidence
        self.cooldown_minutes = cooldown_minutes if cooldown_minutes is not None else account_settings['cooldown_minutes']
        self.allow_multiple_positions = allow_multiple_positions if allow_multiple_positions is not None else account_settings['allow_multiple_positions']
        self._load_trade_history()
    
    def _get_history_file(self) -> str:
        return 'signal_trade_history.json'
    
    def _get_existing_position(self, coin: str) -> Optional[Dict]:
        """Check if there's an actual open position on HyperLiquid for this coin.
        
        Returns position dict with size, strategy, etc. or None if no position.
        """
        try:
            positions = self.executor.client.get_positions()
            for pos in positions:
                if pos.get('coin') == coin and abs(pos.get('size', 0)) > 0:
                    # Found an open position - try to find strategy from trade history
                    strategy = None
                    for trade in reversed(self.signal_history):
                        if trade.get('coin') == coin:
                            strategy = trade.get('strategy')
                            break
                    return {
                        'coin': coin,
                        'size': pos.get('size'),
                        'entry_px': pos.get('entry_px'),
                        'strategy': strategy
                    }
        except Exception as e:
            logger.warning(f"Failed to check existing positions: {e}")
        return None
    
    def _load_trade_history(self):
        """Load history of signal-based trades"""
        self.signal_history: List[Dict] = []
        try:
            if os.path.exists(self._get_history_file()):
                with open(self._get_history_file(), 'r') as f:
                    self.signal_history = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load signal history: {e}")
    
    def _save_trade_history(self):
        """Save signal trade history"""
        try:
            with open(self._get_history_file(), 'w') as f:
                json.dump(self.signal_history, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save signal history: {e}")
    
    def is_in_cooldown(self, coin: str, strategy: str) -> bool:
        """Check if coin is in cooldown period for the same category (scalp/swing)"""
        now = datetime.now()
        category = get_strategy_category(strategy)
        
        for trade in reversed(self.signal_history):
            if trade.get('coin') == coin:
                # Check if same category (scalp vs swing)
                trade_strategy = trade.get('strategy', '')
                trade_category = get_strategy_category(trade_strategy)
                
                if trade_category == category:
                    trade_time = datetime.fromisoformat(trade.get('timestamp', '2000-01-01'))
                    minutes_since = (now - trade_time).total_seconds() / 60
                    if minutes_since < self.cooldown_minutes:
                        logger.info(f"{coin} in {category} cooldown ({minutes_since:.0f}m < {self.cooldown_minutes}m)")
                        return True
                    # Found a trade in same category but outside cooldown - stop searching
                    break
        return False
    
    def _set_cooldown(self, coin: str):
        """Record trade timestamp for cooldown tracking"""
        # Cooldown is tracked via signal_history entries
        # This method exists for compatibility with old code
        logger.debug(f"Cooldown set for {coin}")
    
    # Accept all strategy signals (quorum_view + individual strategies)
    ALLOWED_STRATEGIES = [
        'quorum_view',            # Aggregated quorum view (dashboard only, no trades)
        'rsi_mean_reversion',     # RSI mean reversion strategy
        'momentum_rsi',           # Momentum RSI strategy
        'fvg_proximity',          # Fair Value Gap proximity strategy
        'volume_spike',           # Volume spike strategy
        'trend_breakout',         # Trend breakout strategy
        'mean_reversion',         # Mean reversion strategy
        'momentum_accel',         # Momentum acceleration strategy
        'vwap_reversion',         # VWAP reversion strategy
        'momentum_scalper',       # Momentum scalper strategy
        'pullback_scalper',       # Pullback scalper strategy
    ]
    
    def process_signal(self, signal: Dict, dry_run: bool = False) -> Optional[Dict]:
        """
        Process a single trading signal
        
        Args:
            signal: Signal dictionary with coin, action, confidence, etc.
            dry_run: If True, only log what would be done
        
        Returns:
            Trade result dict or None
        """
        # Validate signal
        required = ['coin', 'action', 'confidence', 'strategy']
        for field in required:
            if field not in signal:
                logger.warning(f"Signal missing required field: {field}")
                return None
        
        coin = signal['coin'].upper()
        action = signal['action']
        confidence = signal.get('confidence', 0)
        strategy = signal.get('strategy', 'unknown')
        
        # Filter: Only process allowed strategies
        if strategy not in self.ALLOWED_STRATEGIES:
            logger.debug(f"Ignoring signal from strategy '{strategy}' (not in allowed list)")
            return None
        
        # Skip HOLD signals
        if action == 'HOLD':
            return None
        
        # Check minimum confidence
        if confidence < self.min_confidence:
            logger.info(f"Skipping {coin} signal: confidence {confidence:.2f} < {self.min_confidence}")
            return None
        
        # Check cooldown (per category: scalp vs swing)
        if self.is_in_cooldown(coin, strategy):
            return None
        
        # Check if we already have a position in the SAME category (unless multiple positions allowed)
        symbol = coin
        category = get_strategy_category(strategy)
        
        # Check actual positions on HyperLiquid (not just in-memory cache)
        existing_position = self._get_existing_position(symbol)
        if not self.allow_multiple_positions and existing_position:
            existing_strategy = existing_position.get('strategy')
            existing_category = get_strategy_category(existing_strategy) if existing_strategy else 'swing'
            existing_side = 'long' if existing_position.get('size', 0) > 0 else 'short'
            new_side = 'long' if action == 'BUY' else 'short'
            
            # Block if same category AND same direction
            if existing_category == category and existing_side == new_side:
                logger.info(f"Already have open {existing_side} {category} position in {symbol} from '{existing_strategy}', skipping new {strategy} {new_side} signal")
                return None
            else:
                logger.info(f"Have {existing_side} {existing_category} position in {symbol} from '{existing_strategy}', but new {new_side} {category} signal from '{strategy}' - allowing")
        
        # Execute the trade
        logger.info(f"""
{'='*60}
EXECUTING SIGNAL
{'='*60}
Coin: {coin}
Action: {action}
Confidence: {confidence:.2%}
Strategy: {strategy}
Test Mode: {self.test_mode}
Dry Run: {dry_run}
{'='*60}
        """)
        
        if dry_run:
            # Just simulate
            entry_price = signal.get('meta', {}).get('price', 0)
            side = 'long' if action == 'BUY' else 'short'
            
            # Extract SL/TP from signal meta (strategy-provided) or fall back to risk_config
            signal_sl_pct = signal.get('meta', {}).get('stop_loss_pct')
            signal_tp_pct = signal.get('meta', {}).get('take_profit_pct')
            sl_pct = (signal_sl_pct / 100) if signal_sl_pct else self.risk_config.stop_loss_pct
            # Use first TP level from risk_config as default
            default_tp_pct = self.risk_config.take_profit_levels[0].get('level', 0.10) if self.risk_config.take_profit_levels else 0.10
            tp_pct = (signal_tp_pct / 100) if signal_tp_pct else default_tp_pct
            
            # Calculate what the trade would look like (with leverage)
            stop_loss = entry_price * (1 - sl_pct) if side == 'long' else entry_price * (1 + sl_pct)
            take_profit = entry_price * (1 + tp_pct) if side == 'long' else entry_price * (1 - tp_pct)
            risk_amount = self.risk_config.risk_per_trade * confidence
            position_value = risk_amount / sl_pct
            position_size = position_value / entry_price if entry_price > 0 else 0
            margin_required = position_value / self.risk_config.leverage
            
            result = {
                'coin': coin,
                'action': action,
                'side': side,
                'entry_price': entry_price,
                'position_size': position_size,
                'position_value': position_value,
                'margin_required': margin_required,
                'leverage': self.risk_config.leverage,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'risk_amount': risk_amount,
                'confidence': confidence,
                'strategy': strategy,
                'status': 'simulated',
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"[DRY RUN] Would execute: {result}")
            return result
        
        # Real execution
        trade = execute_signal(signal, test_mode=self.test_mode)
        
        if trade:
            # Set cooldown after successful trade (using configured cooldown_minutes)
            self._set_cooldown(coin)
            
            # Record in history
            history_entry = {
                'coin': coin,
                'action': action,
                'side': trade.side,
                'entry_price': trade.entry_price,
                'position_size': trade.position_size,
                'position_value': trade.position_value,
                'margin_required': trade.margin_required,
                'leverage': trade.leverage,
                'stop_loss': trade.stop_loss,
                'take_profit': trade.take_profits[0]['price'] if trade.take_profits else None,
                'risk_amount': trade.risk_amount,
                'confidence': confidence,
                'strategy': strategy,
                'timestamp': datetime.now().isoformat()
            }
            self.signal_history.append(history_entry)
            self._save_trade_history()
            
            return trade.to_dict()
        
        return None
    
    def process_signals(self, signals: List[Dict], dry_run: bool = False) -> List[Dict]:
        """
        Process multiple signals
        
        Returns:
            List of executed trades
        """
        results = []
        
        for signal in signals:
            result = self.process_signal(signal, dry_run=dry_run)
            if result:
                results.append(result)
        
        return results
    
    def load_signals_from_file(self, filepath: str) -> List[Dict]:
        """Load signals from a JSON file"""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                # Handle both single signal and list of signals
                if isinstance(data, dict):
                    return [data]
                return data
        except Exception as e:
            logger.error(f"Failed to load signals from {filepath}: {e}")
            return []
    
    def check_and_manage_positions(self):
        """
        Update all open positions - check for exits, update P&L
        Call this periodically (e.g., every 5 minutes)
        """
        self.executor.update_positions()
    
    def get_status(self) -> Dict:
        """Get current integrator status"""
        return {
            'open_positions': len(self.executor.open_trades),
            'total_signal_trades': len(self.signal_history),
            'test_mode': self.test_mode,
            'min_confidence': self.min_confidence,
            'cooldown_minutes': self.cooldown_minutes,
            'portfolio': self.executor.get_portfolio_summary()
        }
    
    def print_status(self):
        """Print current status"""
        status = self.get_status()
        
        print("\n" + "="*60)
        print("SIGNAL INTEGRATOR STATUS")
        print("="*60)
        print(f"Mode: {'TEST (Paper Trading)' if self.test_mode else 'LIVE'}")
        print(f"Leverage: {self.risk_config.leverage:.0f}x")
        print(f"Min Confidence: {status['min_confidence']:.0%}")
        print(f"Cooldown: {status['cooldown_minutes']} minutes")
        print(f"Open Positions: {status['open_positions']}")
        print(f"Signal Trade History: {status['total_signal_trades']}")
        print("="*60)
        
        self.executor.print_portfolio()


def run_signal_cycle(signal_file: Optional[str] = None, 
                     signals: Optional[List[Dict]] = None,
                     test_mode: bool = True,
                     dry_run: bool = False):
    """
    Run a complete signal processing cycle
    
    Args:
        signal_file: Path to JSON file with signals (optional)
        signals: List of signal dicts (optional, used if signal_file not provided)
        test_mode: Use paper trading
        dry_run: Only simulate, don't actually trade
    """
    # Create integrator (cooldown and allow_multiple_positions loaded from .account_settings.json)
    integrator = SignalIntegrator(
        test_mode=test_mode,
        min_confidence=0.7
    )
    
    # Check and manage existing positions first
    integrator.check_and_manage_positions()
    
    # Load signals
    if signal_file:
        signals = integrator.load_signals_from_file(signal_file)
    
    if not signals:
        logger.info("No signals to process")
        integrator.print_status()
        return []
    
    # Process signals
    results = integrator.process_signals(signals, dry_run=dry_run)
    
    # Print status
    integrator.print_status()
    
    return results


if __name__ == "__main__":
    import sys
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        signal_file = sys.argv[1]
        test_mode = '--live' not in sys.argv
        dry_run = '--dry-run' in sys.argv
        
        print(f"Processing signals from: {signal_file}")
        print(f"Mode: {'TEST' if test_mode else 'LIVE'}")
        print(f"Dry Run: {dry_run}")
        
        results = run_signal_cycle(
            signal_file=signal_file,
            test_mode=test_mode,
            dry_run=dry_run
        )
        
        print(f"\nExecuted {len(results)} trades")
    else:
        # Demo mode - show current status
        print("Signal Integrator - Demo Mode")
        print("Usage: python signal_integrator.py <signal_file.json> [--live] [--dry-run]")
        print()
        
        integrator = SignalIntegrator(test_mode=True)
        integrator.print_status()
        
        # Show current prices
        print("\nCurrent Market Prices:")
        for coin in ['BTC', 'ETH', 'SOL']:
            price = integrator.executor.client.get_mid_price(coin)
            print(f"  {coin}: ${price:,.2f}")
