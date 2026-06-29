"""
Hyperliquid Trade Executor - FIXED VERSION using official SDK
Handles paper trading on Hyperliquid testnet with risk management
"""

import os
import sys

# Load environment variables from .openclaw/.env
from dotenv import load_dotenv
openclaw_env_path = os.path.expanduser('~/.openclaw/.env')
if os.path.exists(openclaw_env_path):
    load_dotenv(openclaw_env_path)

import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, List, Any
from datetime import datetime
from pathlib import Path
import time

# HyperLiquid SDK
from eth_account import Account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils.signing import OrderType

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
TRADE_STATE_FILE = Path("trade_state.json")


@dataclass
class RiskConfig:
    """Risk management configuration"""
    max_position_size: float = 0.20  # 20% of capital per trade
    max_daily_loss: float = 0.03     # 3% max daily loss
    max_trades_per_day: int = 10
    default_stop_loss: float = 2.5   # 2.5% default SL
    default_take_profit: float = 5.0 # 5% default TP
    confidence_threshold: float = 0.5


@dataclass
class Trade:
    """Represents an open trade"""
    symbol: str
    side: str  # 'long' or 'short'
    entry_price: float
    position_size: float
    position_value: float
    stop_loss: float
    take_profits: List[float]
    risk_amount: float
    confidence: float
    strategy: str
    status: str = 'open'
    timestamp: str = ''
    order_id: Optional[str] = None
    order_placed_time: Optional[str] = None
    signal_time: str = ''
    
    def to_dict(self):
        return {
            'symbol': self.symbol,
            'side': self.side,
            'entry_price': self.entry_price,
            'position_size': self.position_size,
            'position_value': self.position_value,
            'stop_loss': self.stop_loss,
            'take_profits': self.take_profits,
            'risk_amount': self.risk_amount,
            'confidence': self.confidence,
            'strategy': self.strategy,
            'status': self.status,
            'timestamp': self.timestamp,
            'order_id': self.order_id,
            'order_placed_time': self.order_placed_time,
            'signal_time': self.signal_time
        }


class TradeExecutor:
    """Executes trades with risk management"""
    
    # Main wallet has the funds
    MAIN_WALLET = '0x97c465489243175580fcde624c2ef640c1897a00'
    
    def __init__(self, risk_config: RiskConfig, test_mode: bool = False):
        self.risk = risk_config
        self.test_mode = test_mode
        self.open_trades: Dict[str, Trade] = {}
        self.trade_history: List[Dict] = []
        self.daily_stats = {'trades': 0, 'pnl': 0.0}
        
        # Load state
        self._load_state()
        
        # Initialize HyperLiquid SDK
        private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
        if not private_key:
            logger.error("HYPERLIQUID_PRIVATE_KEY not set!")
            self.exchange = None
            self.info = None
            return
            
        try:
            wallet: LocalAccount = Account.from_key(private_key)
            logger.info(f"Agent wallet: {wallet.address}")
            
            self.exchange = Exchange(
                wallet=wallet,
                base_url='https://api.hyperliquid-testnet.xyz',
                account_address=self.MAIN_WALLET  # Trade on behalf of main
            )
            self.info = Info(base_url='https://api.hyperliquid-testnet.xyz')
            
            # Load metadata
            self.exchange.info.meta = self.info.meta()
            
            logger.info("HyperLiquid SDK initialized")
        except Exception as e:
            logger.error(f"Failed to initialize HyperLiquid SDK: {e}")
            self.exchange = None
            self.info = None
    
    def get_balance(self) -> float:
        """Get account balance from main wallet"""
        if not self.info:
            return 0.0
        try:
            state = self.info.user_state(self.MAIN_WALLET)
            return float(state.get('marginSummary', {}).get('accountValue', 0))
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0.0
    
    def get_positions(self) -> List[Dict]:
        """Get open positions from main wallet"""
        if not self.info:
            return []
        try:
            state = self.info.user_state(self.MAIN_WALLET)
            positions = state.get('assetPositions', [])
            return [p['position'] for p in positions]
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def _load_state(self):
        """Load trade state from file"""
        if TRADE_STATE_FILE.exists():
            try:
                with open(TRADE_STATE_FILE, 'r') as f:
                    state = json.load(f)
                self.open_trades = {k: Trade(**v) for k, v in state.get('open_trades', {}).items()}
                self.trade_history = state.get('trade_history', [])
                logger.info(f"Loaded {len(self.open_trades)} open trades from state")
            except Exception as e:
                logger.error(f"Error loading state: {e}")
    
    def _save_state(self):
        """Save trade state to file"""
        try:
            state = {
                'open_trades': {k: v.to_dict() for k, v in self.open_trades.items()},
                'trade_history': self.trade_history,
                'last_updated': datetime.now().isoformat()
            }
            with open(TRADE_STATE_FILE, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving state: {e}")
    
    def calculate_position_size(self, symbol: str, entry_price: float, 
                                stop_loss: float, confidence: float) -> tuple:
        """Calculate position size based on risk management"""
        balance = self.get_balance()
        if balance <= 0:
            logger.warning(f"Insufficient balance: ${balance:.2f}")
            return 0, 0
        
        risk_per_trade = 0.01  # 1% risk per trade
        risk_amount = balance * risk_per_trade * confidence
        
        price_distance = abs(entry_price - stop_loss) / entry_price
        if price_distance <= 0:
            return 0, 0
        
        position_value = risk_amount / price_distance
        max_position = balance * self.risk.max_position_size
        position_value = min(position_value, max_position)
        position_size = position_value / entry_price
        
        return position_size, position_value
    
    def open_position(self, symbol: str, side: str, entry_price: float,
                      position_size: float, position_value: float,
                      stop_loss: float, take_profits: List[float],
                      risk_amount: float, confidence: float, 
                      strategy: str, signal_time: str = '') -> Optional[Trade]:
        """Open a new position"""
        if symbol in self.open_trades:
            logger.warning(f"Position already open for {symbol}")
            return None
        
        if self.test_mode:
            logger.info(f"[TEST MODE] Would open {side} position in {symbol}")
            return None
        
        if not self.exchange:
            logger.error("HyperLiquid SDK not initialized")
            return None
        
        # Create trade object
        trade = Trade(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            position_size=position_size,
            position_value=position_value,
            stop_loss=stop_loss,
            take_profits=take_profits,
            risk_amount=risk_amount,
            confidence=confidence,
            strategy=strategy,
            status='pending',
            timestamp=datetime.now().isoformat(),
            signal_time=signal_time
        )
        
        # Place order on HyperLiquid
        try:
            logger.info(f"[LIVE MODE] Opening {side} position in {symbol} (SL: {stop_loss:.1f}%, TP: {take_profits[0]:.1f}%)")
            
            result = self._place_order_on_hyperliquid(trade)
            if result:
                trade.order_id = str(result.get('oid', ''))
                trade.order_placed_time = datetime.now().isoformat()
                trade.status = 'open'
                
                # Store trade
                self.open_trades[symbol] = trade
                self._save_state()
                
                logger.info(f"Position opened: {symbol} {side} @ ${entry_price:.2f}")
                return trade
            else:
                logger.error(f"Failed to place order on HyperLiquid")
                return None
                
        except Exception as e:
            logger.error(f"Error opening position: {e}")
            return None
    
    def _place_order_on_hyperliquid(self, trade: Trade) -> Optional[Dict]:
        """Place order using official HyperLiquid SDK"""
        if not self.exchange:
            return None
        
        is_buy = trade.side == 'long'
        
        # Use Limit order with IOC (Immediate Or Cancel) for market-like behavior
        # Or use proper slippage calculation for true market orders
        order_type: OrderType = {"limit": {"tif": "Ioc"}}
        
        # Add slippage for market-like execution
        slippage = 0.05  # 5% slippage
        if is_buy:
            limit_px = trade.entry_price * (1 + slippage)
        else:
            limit_px = trade.entry_price * (1 - slippage)
        
        try:
            result = self.exchange.order(
                name=trade.symbol,
                is_buy=is_buy,
                sz=trade.position_size,
                limit_px=limit_px,
                order_type=order_type,
                reduce_only=False
            )
            
            logger.info(f"Order result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Order failed: {e}")
            raise
    
    def close_position(self, symbol: str, exit_price: float, 
                       reason: str = 'manual') -> Optional[Dict]:
        """Close an open position"""
        if symbol not in self.open_trades:
            return None
        
        trade = self.open_trades[symbol]
        
        if self.test_mode:
            logger.info(f"[TEST MODE] Would close {symbol} @ ${exit_price:.2f}")
            return None
        
        if not self.exchange:
            logger.error("HyperLiquid SDK not initialized")
            return None
        
        try:
            # Place closing order
            is_buy = trade.side == 'short'  # Opposite of open
            
            order_type: OrderType = {"limit": {"tif": "Ioc"}}
            
            result = self.exchange.order(
                name=symbol,
                is_buy=is_buy,
                sz=trade.position_size,
                limit_px=exit_price * 0.95 if is_buy else exit_price * 1.05,
                order_type=order_type,
                reduce_only=True
            )
            
            # Calculate PnL
            if trade.side == 'long':
                pnl = (exit_price - trade.entry_price) * trade.position_size
            else:
                pnl = (trade.entry_price - exit_price) * trade.position_size
            
            # Update trade
            trade.status = 'closed'
            trade_dict = trade.to_dict()
            trade_dict['exit_price'] = exit_price
            trade_dict['exit_time'] = datetime.now().isoformat()
            trade_dict['exit_reason'] = reason
            trade_dict['pnl'] = pnl
            
            self.trade_history.append(trade_dict)
            del self.open_trades[symbol]
            self._save_state()
            
            logger.info(f"Position closed: {symbol} @ ${exit_price:.2f}, PnL: ${pnl:.2f}")
            return result
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return None
    
    def check_positions(self):
        """Check and update positions based on market data"""
        if not self.info:
            return
        
        try:
            # Get positions from HyperLiquid
            hl_positions = self.get_positions()
            hl_symbols = {p['coin'] for p in hl_positions}
            
            # Check for closed positions
            for symbol in list(self.open_trades.keys()):
                if symbol not in hl_symbols:
                    # Position was closed on HyperLiquid
                    trade = self.open_trades[symbol]
                    logger.info(f"Position closed by HyperLiquid: {symbol}")
                    
                    trade.status = 'closed'
                    trade_dict = trade.to_dict()
                    trade_dict['exit_reason'] = 'hyperliquid_close'
                    self.trade_history.append(trade_dict)
                    del self.open_trades[symbol]
            
            if self.open_trades:
                self._save_state()
                
        except Exception as e:
            logger.error(f"Error checking positions: {e}")


def execute_signal(signal: Dict, test_mode: bool = False) -> Optional[Trade]:
    """Execute a trading signal"""
    config = RiskConfig()
    executor = TradeExecutor(config, test_mode=test_mode)
    
    symbol = signal['coin']
    action = signal['action']  # 'BUY' or 'SELL'
    side = 'long' if action == 'BUY' else 'short'
    
    # Get signal metadata
    meta = signal.get('meta', {})
    entry_price = meta.get('price', 0)
    stop_loss_pct = meta.get('stop_loss_pct', config.default_stop_loss)
    take_profit_pct = meta.get('take_profit_pct', config.default_take_profit)
    confidence = signal.get('confidence', 0.5)
    strategy = signal.get('strategy', 'unknown')
    
    # Calculate levels
    if side == 'long':
        stop_loss = entry_price * (1 - stop_loss_pct / 100)
        take_profits = [entry_price * (1 + take_profit_pct / 100)]
    else:
        stop_loss = entry_price * (1 + stop_loss_pct / 100)
        take_profits = [entry_price * (1 - take_profit_pct / 100)]
    
    # Calculate position size
    position_size, position_value = executor.calculate_position_size(
        symbol, entry_price, stop_loss, confidence
    )
    
    if position_size <= 0:
        logger.warning(f"Cannot open {symbol} position: position_size = {position_size}")
        return None
    
    # Calculate risk amount
    price_distance = abs(entry_price - stop_loss) / entry_price
    risk_amount = position_value * price_distance
    
    # Open position
    return executor.open_position(
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        position_size=position_size,
        position_value=position_value,
        stop_loss=stop_loss,
        take_profits=take_profits,
        risk_amount=risk_amount,
        confidence=confidence,
        strategy=strategy,
        signal_time=signal.get('timestamp', '')
    )


if __name__ == "__main__":
    # Test
    executor = TradeExecutor(RiskConfig())
    balance = executor.get_balance()
    print(f"Balance: ${balance:.2f}")
    
    positions = executor.get_positions()
    print(f"Positions: {len(positions)}")
    for p in positions:
        print(f"  {p['coin']}: {p['szi']} @ ${p['entryPx']}")
