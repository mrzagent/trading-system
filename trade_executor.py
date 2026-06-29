"""
Hyperliquid Trade Executor
Handles paper trading on Hyperliquid testnet with risk management
"""

import os
import sys

# Load environment variables from .openclaw/.env
from dotenv import load_dotenv
openclaw_env_path = os.path.expanduser('~/.openclaw/.env')
if os.path.exists(openclaw_env_path):
    load_dotenv(openclaw_env_path)

# Set HyperLiquid credentials from environment (if not already set)
# These come from ~/.openclaw/.env HYPERLIQUID_WALLET and HYPERLIQUID_PRIVATE_KEY
if os.getenv('HYPERLIQUID_WALLET'):
    os.environ['HYPERLIQUID_WALLET'] = os.getenv('HYPERLIQUID_WALLET')
if os.getenv('HYPERLIQUID_PRIVATE_KEY'):
    os.environ['HYPERLIQUID_PRIVATE_KEY'] = os.getenv('HYPERLIQUID_PRIVATE_KEY')

import json
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
from decimal import Decimal, ROUND_DOWN
import requests
import time
from datetime import datetime

# Real order placement imports
try:
    from eth_account import Account
    from eth_account.messages import encode_defunct
    ETH_ACCOUNT_AVAILABLE = True
except ImportError:
    ETH_ACCOUNT_AVAILABLE = False
# HyperLiquid SDK imports
try:
    from eth_account.signers.local import LocalAccount
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info
    from hyperliquid.utils.signing import OrderType
    HYPERLIQUID_SDK_AVAILABLE = True
except ImportError:
    HYPERLIQUID_SDK_AVAILABLE = False
    logging.warning("hyperliquid-python-sdk not fully available")

    logging.warning("eth-account not installed. Real order placement disabled. Run: pip install eth-account")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trade_executor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class TakeProfitLevel:
    """Single take profit level configuration"""
    level: float        # Price move % to trigger (e.g., 0.05 = 5%)
    close_pct: float    # % of position to close (e.g., 0.25 = 25%)
    label: str          # Label like "TP1", "TP2", etc.


@dataclass
class RiskConfig:
    """Risk management configuration"""
    initial_capital: float = 1000.0
    risk_per_trade_pct: float = 0.02  # 2% risk per trade
    stop_loss_pct: float = 0.05       # 5% stop loss
    take_profit_levels: list = None   # List of TakeProfitLevel dicts
    max_position_pct: float = 0.50    # Max 50% of capital in one position
    max_open_positions: int = 3       # Max 3 concurrent positions
    commission_pct: float = 0.001     # 0.1% commission
    slippage_pct: float = 0.0005      # 0.05% slippage
    leverage: float = 3.0             # Default 3x leverage
    
    def __post_init__(self):
        """Process take_profit_levels after initialization"""
        if self.take_profit_levels is None:
            # Default to single TP at 10%
            self.take_profit_levels = [
                {"level": 0.10, "close_pct": 1.0, "label": "TP1"}
            ]
    
    @property
    def risk_per_trade(self) -> float:
        return self.initial_capital * self.risk_per_trade_pct
    
    def get_tp_levels(self) -> list:
        """Get take profit levels as objects"""
        levels = []
        for tp in self.take_profit_levels:
            levels.append(TakeProfitLevel(
                level=tp.get('level', 0.10),
                close_pct=tp.get('close_pct', 1.0),
                label=tp.get('label', 'TP')
            ))
        return levels


@dataclass
class PartialClose:
    """Represents a partial position close"""
    level: str          # TP label (TP1, TP2, etc.)
    close_pct: float    # % of position closed
    size_closed: float  # Amount closed in coins
    price: float        # Exit price
    pnl: float          # P&L from this close
    time: str           # When it happened


@dataclass
class Trade:
    """Represents a trade"""
    symbol: str
    side: str  # 'long' or 'short'
    entry_price: float
    position_size: float  # In coins/units (current remaining)
    original_size: float  # Original position size
    position_value: float  # In USDC (notional) (current remaining)
    original_value: float  # Original position value
    margin_required: float  # In USDC (actual capital used)
    leverage: float  # Leverage used
    stop_loss: float
    take_profits: list  # List of dicts with level, price, close_pct, label, hit
    risk_amount: float
    order_id: Optional[str] = None  # Entry order ID
    status: str = "pending"  # pending, open, closed
    entry_time: Optional[str] = None
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    exit_reason: Optional[str] = None
    partial_closes: list = None  # List of PartialClose
    remaining_pct: float = 1.0  # % of position still open
    # HyperLiquid trigger order IDs for SL/TP
    sl_order_id: Optional[str] = None  # Stop loss trigger order ID
    tp_order_ids: list = None  # List of take profit trigger order IDs (one per TP level)
    # Additional timing and metadata
    signal_time: Optional[str] = None  # When the signal was generated
    order_placed_time: Optional[str] = None  # When order was placed on HyperLiquid
    strategy: Optional[str] = None  # Which strategy opened this trade
    
    def __post_init__(self):
        if self.partial_closes is None:
            self.partial_closes = []
        if self.take_profits is None:
            self.take_profits = []
        if self.tp_order_ids is None:
            self.tp_order_ids = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol,
            'side': self.side,
            'entry_price': self.entry_price,
            'position_size': self.position_size,
            'original_size': self.original_size,
            'position_value': self.position_value,
            'original_value': self.original_value,
            'margin_required': self.margin_required,
            'leverage': self.leverage,
            'stop_loss': self.stop_loss,
            'take_profits': self.take_profits,
            'risk_amount': self.risk_amount,
            'order_id': self.order_id,
            'status': self.status,
            'signal_time': self.signal_time,
            'order_placed_time': self.order_placed_time,
            'entry_time': self.entry_time,
            'exit_time': self.exit_time,
            'exit_price': self.exit_price,
            'pnl': self.pnl,
            'exit_reason': self.exit_reason,
            'partial_closes': [pc.__dict__ if isinstance(pc, PartialClose) else pc for pc in (self.partial_closes or [])],
            'remaining_pct': self.remaining_pct,
            'sl_order_id': self.sl_order_id,
            'tp_order_ids': self.tp_order_ids,
            'strategy': self.strategy
        }


class HyperliquidClient:
    """Hyperliquid API client for testnet and mainnet"""
    
    # Default URLs
    TESTNET_URL = "https://api.hyperliquid-testnet.xyz"
    MAINNET_URL = "https://api.hyperliquid.xyz"
    
    def __init__(self, wallet_address: Optional[str] = None, private_key: Optional[str] = None, 
                 environment: str = 'testnet', api_url: Optional[str] = None):
        """Initialize HyperLiquid client.
        
        Args:
            wallet_address: Wallet address for trading
            private_key: Private key for signing transactions
            environment: 'testnet' or 'mainnet'
            api_url: Optional custom API URL (overrides environment default)
        """
        self.environment = environment
        self.base_url = api_url or (self.MAINNET_URL if environment == 'mainnet' else self.TESTNET_URL)
        
        # Agent wallet for signing transactions
        self.wallet_address = wallet_address or os.getenv('HYPERLIQUID_WALLET')
        self.private_key = private_key or os.getenv('HYPERLIQUID_PRIVATE_KEY')
        self.session = requests.Session()
        
        # Main wallet has the funds (different for testnet vs mainnet)
        if environment == 'mainnet':
            self.MAIN_WALLET = os.getenv('HYPERLIQUID_MAINNET_WALLET', '0x97c465489243175580fcDe624c2ef640c1897a00')
        else:
            self.MAIN_WALLET = '0x97c465489243175580fcde624c2ef640c1897a00'  # Testnet wallet
        
        # Initialize HyperLiquid SDK
        self._exchange = None
        self._info = None
        self._meta = None
        if HYPERLIQUID_SDK_AVAILABLE and self.private_key:
            try:
                wallet: LocalAccount = Account.from_key(self.private_key)
                self._info = Info(base_url=self.base_url, skip_ws=True)
                self._meta = self._info.meta()
                self._exchange = Exchange(
                    wallet=wallet,
                    base_url=self.base_url,
                    account_address=self.MAIN_WALLET,
                    meta=self._meta
                )
                logger.info(f"HyperLiquid SDK initialized successfully ({environment})")
            except Exception as e:
                logger.error(f"Failed to initialize HyperLiquid SDK: {e}")
        
        if not self.wallet_address:
            logger.warning("No wallet address provided. Running in read-only mode.")
    
    def _post(self, endpoint: str, payload: Dict) -> Dict:
        """Make POST request to Hyperliquid API"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"API request failed: {e}")
            try:
                logger.error(f"Response body: {e.response.text}")
                logger.error(f"Request: {json.dumps(payload, indent=2)[:500]}")
            except:
                pass
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise
    
    def get_all_mids(self) -> Dict[str, float]:
        """Get mid prices for all assets"""
        payload = {"type": "allMids"}
        result = self._post("/info", payload)
        return {k: float(v) for k, v in result.items()}
    
    def get_mid_price(self, coin: str) -> float:
        """Get mid price for a specific coin"""
        all_mids = self.get_all_mids()
        return all_mids.get(coin.upper(), 0.0)
    
    def get_user_state(self, use_main: bool = True) -> Dict:
        """Get user account state"""
        # Use main wallet for balance/positions, agent wallet for signing
        wallet = self.MAIN_WALLET if use_main else self.wallet_address
        if not wallet:
            raise ValueError("Wallet address required")
        payload = {
            "type": "clearinghouseState",
            "user": wallet
        }
        return self._post("/info", payload)
    
    def get_balance(self) -> float:
        """Get USDC balance from MAIN wallet using portfolio endpoint"""
        try:
            # Use portfolio endpoint like dashboard does
            portfolio = self._post("/info", {"type": "portfolio", "user": self.MAIN_WALLET})
            for period_name, period_data in portfolio:
                if period_name == "day":
                    history = period_data.get("accountValueHistory", [])
                    if history:
                        # Last entry is most recent: [timestamp, value]
                        return float(history[-1][1])
            
            # Fallback to clearinghouseState
            state = self.get_user_state(use_main=True)
            balance_raw = state.get('marginSummary', {}).get('accountValue', '0')
            return float(balance_raw)
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return 0.0
    
    def get_positions(self) -> list:
        """Get open positions from MAIN wallet"""
        try:
            state = self.get_user_state(use_main=True)
            asset_positions = state.get('assetPositions', [])
            positions = []
            for pos in asset_positions:
                position_data = pos.get('position', {})
                positions.append({
                    'coin': position_data.get('coin'),
                    'size': float(position_data.get('szi', 0)),
                    'entry_px': float(position_data.get('entryPx', 0)),
                    'position_value': float(position_data.get('positionValue', 0)),
                    'unrealized_pnl': float(position_data.get('unrealizedPnl', 0)),
                    'leverage': position_data.get('leverage', {}),
                    'liquidation_px': float(position_data.get('liquidationPx', 0)) if position_data.get('liquidationPx') else None
                })
            return positions
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
    
    def place_order(self, coin: str, is_buy: bool, sz: float, limit_px: float, 
                    order_type: str = "Limit", reduce_only: bool = False) -> Dict:
        """
        Place an order on Hyperliquid using official SDK
        
        Args:
            coin: Asset symbol (BTC, ETH, SOL)
            is_buy: True for buy/long, False for sell/short
            sz: Order size in coins
            limit_px: Limit price
            order_type: "Limit" or "Market"
            reduce_only: If True, only reduces position (for closing)
        
        Returns:
            API response dict
        """
        if not self._exchange:
            raise RuntimeError("HyperLiquid SDK not initialized. Check private key.")
        
        # Convert string order_type to SDK OrderType
        if order_type == "Market":
            # Use IOC (Immediate Or Cancel) for market-like behavior
            sdk_order_type = {"limit": {"tif": "Ioc"}}
        else:
            # Default to GTC (Good Till Canceled) for limit orders
            sdk_order_type = {"limit": {"tif": "Gtc"}}
        
        try:
            result = self._exchange.order(
                name=coin,
                is_buy=is_buy,
                sz=sz,
                limit_px=limit_px,
                order_type=sdk_order_type,
                reduce_only=reduce_only
            )
            logger.info(f"Order submitted: {coin} {'BUY' if is_buy else 'SELL'} {sz} @ ${limit_px}")
            return result
        except Exception as e:
            logger.error(f"Order failed: {e}")
            raise
    
    def close_position_market(self, coin: str) -> Dict:
        """
        Close an open position using a market order
        
        Returns:
            API response dict
        """
        # Get current position
        positions = self.get_positions()
        position = None
        for pos in positions:
            if pos['coin'] == coin:
                position = pos
                break
        
        if not position:
            raise ValueError(f"No open position found for {coin}")
        
        position_size = abs(position['size'])
        current_size = position['size']
        
        # Determine direction to close
        # If long (positive size), we sell to close
        # If short (negative size), we buy to close
        is_buy = current_size < 0
        
        # Get current price for market order
        current_price = self.get_mid_price(coin)
        
        # Round price to tick size (HyperLiquid requires specific price increments)
        # BTC: $1 tick, ETH: $0.05 tick, SOL: $0.01 tick (approximate)
        tick_sizes = {'BTC': 1, 'ETH': 0.05, 'SOL': 0.01}
        tick = tick_sizes.get(coin, 0.01)
        
        # For market-like IOC orders, use aggressive pricing with slippage
        if is_buy:
            # Buying - use higher price (0.5% slippage) and round to tick
            limit_px = round(current_price * 1.005 / tick) * tick
        else:
            # Selling - use lower price (0.5% slippage) and round to tick
            limit_px = round(current_price * 0.995 / tick) * tick
        
        # Round to appropriate decimal places for the tick size
        decimals = len(str(tick).split('.')[-1]) if '.' in str(tick) else 0
        limit_px = round(limit_px, decimals)
        
        logger.info(f"Closing {coin} position: {current_size} @ market (limit_px=${limit_px})")
        
        # Use IOC limit order for immediate execution with price protection
        return self.place_order(
            coin=coin,
            is_buy=is_buy,
            sz=position_size,
            limit_px=limit_px,
            order_type="Ioc",  # Immediate-or-cancel for market-like behavior
            reduce_only=True
        )
    
    def place_trigger_order(self, coin: str, is_buy: bool, sz: float, 
                           trigger_px: float, limit_px: float,
                           tpsl: str = 'sl', is_market: bool = True,
                           reduce_only: bool = True) -> Dict:
        """
        Place a stop loss or take profit trigger order on Hyperliquid using SDK
        
        Args:
            coin: Asset symbol (BTC, ETH, SOL)
            is_buy: True for buy, False for sell
            sz: Order size in coins
            trigger_px: Price that triggers the order
            limit_px: Execution price after trigger (for market orders, use current price)
            tpsl: 'sl' for stop loss, 'tp' for take profit
            is_market: If True, executes as market order when triggered
            reduce_only: If True, only reduces position
        
        Returns:
            API response dict with order ID
        """
        if not self._exchange:
            raise RuntimeError("HyperLiquid SDK not initialized. Check private key.")
        
        # Build trigger order type
        order_type = {"trigger": {"triggerPx": trigger_px, "isMarket": is_market, "tpsl": tpsl}}
        
        try:
            result = self._exchange.order(
                name=coin,
                is_buy=is_buy,
                sz=sz,
                limit_px=limit_px,
                order_type=order_type,
                reduce_only=reduce_only
            )
            order_type_str = "SL" if tpsl == 'sl' else "TP"
            logger.info(f"Trigger order submitted: {coin} {order_type_str} {sz} @ trigger=${trigger_px}")
            return result
        except Exception as e:
            logger.error(f"Trigger order failed: {e}")
            raise
    
    def cancel_order(self, coin: str, oid: int) -> Dict:
        """
        Cancel an order by OID
        
        Args:
            coin: Asset symbol
            oid: Order ID to cancel
        
        Returns:
            API response dict
        """
        try:
            from eth_account import Account
            from eth_account.messages import encode_defunct
        except ImportError:
            raise RuntimeError("eth-account not installed")
        
        if not self.wallet_address or not self.private_key:
            raise ValueError("Wallet address and private key required")
        
        # Build cancel action
        action = {
            "type": "cancel",
            "cancels": [{"coin": coin, "oid": oid}]
        }
        
        # Get nonce
        nonce = int(time.time() * 1000)
        
        # Sign the action
        account = Account.from_key(self.private_key)
        message_str = json.dumps(action, separators=(',', ':'), sort_keys=True) + str(nonce)
        message = encode_defunct(text=message_str)
        signed = account.sign_message(message)
        signature = signed.signature.hex()
        
        # Build and send request
        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature
        }
        
        try:
            response = self._post("/exchange", payload)
            logger.info(f"Order cancelled: {coin} oid={oid}")
            return response
        except Exception as e:
            logger.error(f"Cancel order failed: {e}")
            raise


class TradeExecutor:
    """Main trade execution engine with risk management"""
    
    # Coin to Hyperliquid symbol mapping
    COIN_MAP = {
        'BTC': 'BTC',
        'ETH': 'ETH',
        'SOL': 'SOL'
    }
    
    def __init__(self, risk_config: Optional[RiskConfig] = None,
                 wallet_address: Optional[str] = None,
                 private_key: Optional[str] = None,
                 environment: str = 'testnet',
                 api_url: Optional[str] = None):
        """Initialize TradeExecutor.
        
        Args:
            risk_config: Risk management configuration
            wallet_address: Wallet address for trading
            private_key: Private key for signing
            environment: 'testnet' or 'mainnet'
            api_url: Optional custom API URL
        """
        self.environment = environment
        
        # If no risk config provided, fetch actual account balance from HyperLiquid
        if risk_config is None:
            try:
                client = HyperliquidClient(wallet_address, private_key, environment, api_url)
                account_balance = client.get_balance()
                # Use at least $100 to avoid tiny positions during testing
                initial_capital = max(account_balance, 100.0)
                logger.info(f"TradeExecutor using actual HL balance: ${initial_capital:.2f}")
                self.risk = RiskConfig(initial_capital=initial_capital)
            except Exception as e:
                logger.warning(f"Could not fetch HL balance, using default $1000: {e}")
                self.risk = RiskConfig()
        else:
            self.risk = risk_config
            logger.info(f"TradeExecutor using provided risk config: ${self.risk.initial_capital:.2f} capital, "
                       f"${self.risk.risk_per_trade:.2f} risk per trade ({self.risk.risk_per_trade_pct*100:.1f}%), "
                       f"{self.risk.leverage}x leverage")

        self.client = HyperliquidClient(wallet_address, private_key, environment, api_url)
        self.open_trades: Dict[str, Trade] = {}  # symbol -> Trade
        self.trade_history: list = []
        self._load_state()
    
    def _get_state_file(self) -> str:
        return 'trade_state.json'
    
    def _load_state(self):
        """Load open trades from state file"""
        try:
            if os.path.exists(self._get_state_file()):
                with open(self._get_state_file(), 'r') as f:
                    state = json.load(f)
                    for symbol, trade_dict in state.get('open_trades', {}).items():
                        # Migrate old field names to new ones
                        if 'take_profit' in trade_dict and 'take_profits' not in trade_dict:
                            # Convert old single take_profit to new take_profits list format
                            trade_dict['take_profits'] = [{
                                'label': 'TP1',
                                'level_pct': 0.10,
                                'price': trade_dict.pop('take_profit'),
                                'close_pct': 1.0,
                                'hit': False
                            }]
                        self.open_trades[symbol] = Trade(**trade_dict)
                    self.trade_history = state.get('trade_history', [])
                logger.info(f"Loaded {len(self.open_trades)} open trades from state")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
    
    def _save_state(self):
        """Save open trades to state file"""
        try:
            state = {
                'open_trades': {s: t.to_dict() for s, t in self.open_trades.items()},
                'trade_history': self.trade_history,
                'saved_at': datetime.now().isoformat()
            }
            with open(self._get_state_file(), 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def calculate_position_size(self, entry_price: float, stop_loss: float,
                                side: str, symbol: str = None,
                                stop_loss_pct: Optional[float] = None) -> tuple[float, float, float]:
        """
        Calculate position size based on risk parameters with leverage.
        
        With leverage: Margin should be limited to risk_per_trade / leverage
        to ensure we don't risk more than 2% of account per trade.
        
        Args:
            entry_price: Entry price for the trade
            stop_loss: Stop loss price level
            side: 'long' or 'short'
            symbol: Trading symbol (SOL, BTC, ETH)
            stop_loss_pct: Optional SL % to use for calculation (uses calculated distance if None)
        
        Returns:
            (position_size_in_coins, position_value_in_usdc, margin_required)
        """
        if entry_price <= 0 or stop_loss <= 0:
            return 0.0, 0.0, 0.0
        
        # Risk amount in USDC (2% of account)
        risk_amount = self.risk.risk_per_trade
        
        # Calculate distance to stop loss
        if stop_loss_pct is not None:
            # Use signal-provided SL percentage directly
            stop_distance = stop_loss_pct
        else:
            # Calculate from price levels
            if side == 'long':
                stop_distance = (entry_price - stop_loss) / entry_price
            else:  # short
                stop_distance = (stop_loss - entry_price) / entry_price
            stop_distance = abs(stop_distance)
        
        if stop_distance == 0:
            logger.warning("Stop distance is zero, cannot calculate position size")
            return 0.0, 0.0, 0.0
        
        # With leverage: 
        # - We want to risk exactly risk_amount (2% of account)
        # - Position moves stop_distance % against us = we lose that % of position value
        # - With leverage, margin = position_value / leverage
        # - Loss = position_value * stop_distance = margin * leverage * stop_distance
        # - We want: margin * leverage * stop_distance = risk_amount
        # - Therefore: margin = risk_amount / (leverage * stop_distance)
        # - And: position_value = margin * leverage = risk_amount / stop_distance
        
        # But we also need to cap margin so we don't use too much capital
        # Max margin should be: risk_amount (so we can't lose more than 2% even with leverage)
        max_margin_for_risk = risk_amount  # Never risk more than 2% margin
        
        # Calculate position based on stop distance
        position_value = risk_amount / stop_distance
        margin_required = position_value / self.risk.leverage
        
        # Cap margin to 2% of account (the risk amount)
        # This ensures even with tight stops, we don't over-leverage
        if margin_required > max_margin_for_risk:
            margin_required = max_margin_for_risk
            position_value = margin_required * self.risk.leverage
            logger.info(f"Margin capped at 2% ({risk_amount:.2f} USDC) for risk management")
        
        # Also apply the max_position_pct limit (default 50% of account)
        max_margin_by_pct = self.risk.initial_capital * self.risk.max_position_pct
        if margin_required > max_margin_by_pct:
            margin_required = max_margin_by_pct
            position_value = margin_required * self.risk.leverage
        
        # Also limit to account balance (can't trade more than we have)
        max_position_by_balance = self.risk.initial_capital * 0.95  # 95% of balance max
        if position_value > max_position_by_balance:
            position_value = max_position_by_balance
            margin_required = position_value / self.risk.leverage
        
        # Check total margin already used by open positions
        total_margin_used = sum(
            t.margin_required for t in self.open_trades.values()
        )
        available_margin = self.risk.initial_capital - total_margin_used
        
        # Ensure we don't exceed available margin
        if margin_required > available_margin * 0.95:  # Leave 5% buffer
            margin_required = available_margin * 0.95
            position_value = margin_required * self.risk.leverage
            logger.warning(f"Position size reduced due to insufficient margin. Available: ${available_margin:.2f}, Requested: ${margin_required:.2f}")
        
        # Calculate position size in coins
        position_size = position_value / entry_price
        
        # Round to appropriate decimals based on asset
        # SOL: 2 decimals, BTC: 5 decimals, ETH: 4 decimals
        sz_decimals = {
            'SOL': 2, 'BTC': 5, 'ETH': 4
        }.get(symbol if symbol else 'DEFAULT', 4)
        position_size = round(position_size, sz_decimals)
        position_value = position_size * entry_price
        margin_required = position_value / self.risk.leverage
        
        logger.info(f"Position calc: size={position_size}, value=${position_value:.2f}, margin=${margin_required:.2f}, "
                   f"risk=${risk_amount:.2f}, stop_dist={stop_distance:.2%}, leverage={self.risk.leverage}x")
        
        return position_size, position_value, margin_required
    
    def calculate_stop_loss(self, entry_price: float, side: str) -> float:
        """Calculate stop loss price"""
        if side == 'long':
            return entry_price * (1 - self.risk.stop_loss_pct)
        else:  # short
            return entry_price * (1 + self.risk.stop_loss_pct)
    
    def calculate_take_profits(self, entry_price: float, side: str) -> list:
        """Calculate all take profit levels with prices and close percentages"""
        tp_levels = self.risk.get_tp_levels()
        take_profits = []
        
        for tp in tp_levels:
            if side == 'long':
                tp_price = entry_price * (1 + tp.level)
            else:  # short
                tp_price = entry_price * (1 - tp.level)
            
            take_profits.append({
                'label': tp.label,
                'level_pct': tp.level,
                'price': tp_price,
                'close_pct': tp.close_pct,
                'hit': False
            })
        
        return take_profits
    
    def can_open_position(self, symbol: str, margin_required: float = 0, strategy: Optional[str] = None) -> tuple[bool, str]:
        """Check if we can open a new position"""
        # Check if already have position in this symbol from SAME strategy
        # (Different strategies are allowed - checked by signal_integrator)
        if symbol in self.open_trades:
            existing_trade = self.open_trades[symbol]
            existing_strategy = existing_trade.strategy if hasattr(existing_trade, 'strategy') else None
            if existing_strategy == strategy and strategy is not None:
                return False, f"Already have open position in {symbol} from same strategy '{strategy}'"
            # If strategies differ or existing has no strategy, allow (signal_integrator handles this)
        
        # Check max positions limit
        if len(self.open_trades) >= self.risk.max_open_positions:
            return False, f"Max open positions reached ({self.risk.max_open_positions})"
        
        # Check available margin (sum of margin_required for open positions)
        total_margin_used = sum(t.margin_required for t in self.open_trades.values())
        available_margin = self.risk.initial_capital - total_margin_used
        
        if margin_required > 0 and margin_required > available_margin:
            return False, f"Insufficient margin. Available: ${available_margin:.2f}, need: ${margin_required:.2f}"
        
        return True, "OK"
    
    def open_position(self, coin: str, side: str, 
                      entry_price: Optional[float] = None,
                      confidence: float = 1.0,
                      stop_loss_pct: Optional[float] = None,
                      take_profit_pct: Optional[float] = None,
                      signal_time: Optional[str] = None,
                      strategy: Optional[str] = None) -> Optional[Trade]:
        """
        Open a new position with full risk management (with leverage)
        
        Args:
            coin: Coin symbol (BTC, ETH, SOL)
            side: 'long' or 'short'
            entry_price: Optional entry price (uses current market if None)
            confidence: Signal confidence (0-1), affects position sizing
            stop_loss_pct: Optional stop loss % from signal (uses risk_config if None)
            take_profit_pct: Optional take profit % from signal (uses risk_config if None)
            signal_time: ISO timestamp when signal was generated
        """
        symbol = self.COIN_MAP.get(coin.upper(), coin.upper())
        
        # Get entry price first (needed for calculations)
        if entry_price is None:
            entry_price = self.client.get_mid_price(symbol)
            if entry_price == 0:
                logger.error(f"Could not get price for {symbol}")
                return None
        
        # Use signal-provided SL/TP or fall back to risk_config defaults
        sl_pct = stop_loss_pct if stop_loss_pct is not None else self.risk.stop_loss_pct
        tp_pct = take_profit_pct if take_profit_pct is not None else self.risk.take_profit_levels[0].get('level', 0.10) if self.risk.take_profit_levels else 0.10
        
        # Calculate stop loss and take profits
        if side == 'long':
            stop_loss = entry_price * (1 - sl_pct)
            take_profit_price = entry_price * (1 + tp_pct)
        else:  # short
            stop_loss = entry_price * (1 + sl_pct)
            take_profit_price = entry_price * (1 - tp_pct)
        
        # Build take_profits list from signal parameters
        take_profits = [{
            'label': 'TP1',
            'level_pct': tp_pct,
            'price': take_profit_price,
            'close_pct': 1.0,
            'hit': False
        }]
        
        # Calculate position size with leverage (using signal-provided SL)
        position_size, position_value, margin_required = self.calculate_position_size(
            entry_price, stop_loss, side, symbol, sl_pct
        )
        
        if position_size <= 0 or position_value <= 0:
            logger.error(f"Invalid position size calculated: {position_size}, value: {position_value}")
            return None
        
        # Adjust for confidence (reduce size for lower confidence)
        if confidence < 1.0:
            position_size *= confidence
            position_value *= confidence
            margin_required *= confidence
            logger.info(f"Adjusted position for confidence {confidence}: size={position_size:.6f}")
        
        # Round to asset-specific decimals after confidence adjustment
        sz_decimals = {'SOL': 2, 'BTC': 5, 'ETH': 4}.get(symbol, 4)
        position_size = round(position_size, sz_decimals)
        position_value = position_size * entry_price
        margin_required = position_value / self.risk.leverage
        
        # Check if we can open position (with margin check)
        can_open, reason = self.can_open_position(symbol, margin_required, strategy)
        if not can_open:
            logger.warning(f"Cannot open {side} position in {symbol}: {reason}")
            return None
        
        # Create trade object
        now = datetime.now().isoformat()
        trade = Trade(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            position_size=position_size,
            original_size=position_size,
            position_value=position_value,
            original_value=position_value,
            margin_required=margin_required,
            leverage=self.risk.leverage,
            stop_loss=stop_loss,
            take_profits=take_profits,
            risk_amount=self.risk.risk_per_trade * confidence,
            entry_time=now,
            status="open",
            remaining_pct=1.0,
            signal_time=signal_time or now,
            strategy=strategy
        )
        
        # Build TP summary for logging
        tp_summary = "\n".join([
            f"  {tp['label']}: ${tp['price']:,.2f} (+{tp['level_pct']*100:.0f}%) - Close {tp['close_pct']*100:.0f}%"
            for tp in take_profits
        ])
        
        # Log the trade
        logger.info(f"""
=== NEW POSITION ===
Symbol: {symbol}
Side: {side.upper()}
Leverage: {self.risk.leverage:.1f}x
Entry: ${entry_price:,.2f}
Position Size: {position_size:.6f} {symbol}
Position Value: ${position_value:,.2f}
Margin Used: ${margin_required:,.2f}
Stop Loss: ${stop_loss:,.2f} ({sl_pct*100:.1f}%)
Take Profits:
{tp_summary}
Risk Amount: ${trade.risk_amount:.2f}
====================
        """)
        
        # Store trade
        self.open_trades[symbol] = trade
        self._save_state()
        
        return trade
    
    def check_exit_conditions(self, symbol: str, current_price: float) -> Optional[tuple]:
        """
        Check if position should be exited or partially closed
        
        Returns:
            Tuple of (action, data) if action needed, None otherwise
            action: 'stop_loss', 'take_profit_full', 'take_profit_partial', 'move_stop'
        """
        if symbol not in self.open_trades:
            return None
        
        trade = self.open_trades[symbol]
        
        # Check stop loss first
        if trade.side == 'long':
            if current_price <= trade.stop_loss:
                return ('stop_loss', None)
        else:  # short
            if current_price >= trade.stop_loss:
                return ('stop_loss', None)
        
        # Check take profit levels
        for tp in trade.take_profits:
            if tp['hit']:
                continue  # Already hit this TP
            
            tp_price = tp['price']
            
            if trade.side == 'long':
                if current_price >= tp_price:
                    return ('take_profit_partial', tp)
            else:  # short
                if current_price <= tp_price:
                    return ('take_profit_partial', tp)
        
        return None
    
    def partial_close_position(self, symbol: str, tp_level: dict, 
                                current_price: float) -> Optional[Trade]:
        """Partially close a position at a take profit level"""
        if symbol not in self.open_trades:
            return None
        
        trade = self.open_trades[symbol]
        
        # Calculate amount to close
        close_pct = tp_level['close_pct']
        size_to_close = trade.original_size * close_pct
        value_to_close = trade.original_value * close_pct
        
        # Calculate P&L for this portion
        if trade.side == 'long':
            pnl = (current_price - trade.entry_price) * size_to_close
        else:  # short
            pnl = (trade.entry_price - current_price) * size_to_close
        
        # Subtract commission for this close
        commission = value_to_close * self.risk.commission_pct
        pnl -= commission
        
        # Record the partial close
        partial = PartialClose(
            level=tp_level['label'],
            close_pct=close_pct,
            size_closed=size_to_close,
            price=current_price,
            pnl=pnl,
            time=datetime.now().isoformat()
        )
        trade.partial_closes.append(partial)
        
        # Update position
        trade.position_size -= size_to_close
        trade.position_value -= value_to_close
        trade.pnl += pnl
        trade.remaining_pct -= close_pct
        tp_level['hit'] = True
        
        # Check if fully closed
        if trade.remaining_pct <= 0.01:  # Less than 1% remaining
            trade.status = "closed"
            trade.exit_price = current_price
            trade.exit_time = datetime.now().isoformat()
            trade.exit_reason = "take_profit_full"
            
            emoji = "[WIN]" if trade.pnl > 0 else "[LOSS]"
            logger.info(f"""
=== POSITION FULLY CLOSED {emoji} ===
Symbol: {symbol}
Side: {trade.side.upper()}
Entry: ${trade.entry_price:,.2f}
Final Exit: ${current_price:,.2f}
Total P&L: ${trade.pnl:+.2f}
Partial Closes: {len(trade.partial_closes)}
==========================
            """)
            
            # Move to history
            self.trade_history.append(trade.to_dict())
            del self.open_trades[symbol]
        else:
            # Still open - move stop loss to breakeven after TP1
            if tp_level['label'] == 'TP1' and len(trade.partial_closes) == 1:
                old_sl = trade.stop_loss
                trade.stop_loss = trade.entry_price  # Move to breakeven
                logger.info(f"""
=== PARTIAL CLOSE - BREAKEVEN SL ===
Symbol: {symbol}
Closed: {close_pct*100:.0f}% at {tp_level['label']}
P&L this close: ${pnl:+.2f}
Stop Loss moved: ${old_sl:,.2f} -> ${trade.stop_loss:,.2f} (breakeven)
Remaining: {trade.remaining_pct*100:.1f}%
==========================
                """)
            else:
                logger.info(f"""
=== PARTIAL CLOSE ===
Symbol: {symbol}
Closed: {close_pct*100:.0f}% at {tp_level['label']}
Price: ${current_price:,.2f}
P&L this close: ${pnl:+.2f}
Remaining: {trade.remaining_pct*100:.1f}%
====================
                """)
        
        self._save_state()
        return trade

    def close_position(self, symbol: str, exit_price: Optional[float] = None, 
                       reason: str = "manual", cancel_trigger_orders: bool = True) -> Optional[Trade]:
        """
        Close an open position fully
        
        Args:
            symbol: Coin symbol
            exit_price: Exit price (uses current market price if None)
            reason: Exit reason for logging
            cancel_trigger_orders: If True, cancels SL/TP trigger orders on HyperLiquid
        """
        if symbol not in self.open_trades:
            logger.warning(f"No open position found for {symbol}")
            return None
        
        trade = self.open_trades[symbol]
        
        # Cancel SL/TP trigger orders on HyperLiquid
        if cancel_trigger_orders and (trade.sl_order_id or trade.tp_order_ids):
            cancelled = []
            
            if trade.sl_order_id:
                try:
                    self.client.cancel_order(symbol, int(trade.sl_order_id))
                    cancelled.append(f"SL:{trade.sl_order_id}")
                except Exception as e:
                    logger.warning(f"Failed to cancel SL order {trade.sl_order_id}: {e}")
            
            for tp_oid in trade.tp_order_ids:
                if tp_oid:
                    try:
                        self.client.cancel_order(symbol, int(tp_oid))
                        cancelled.append(f"TP:{tp_oid}")
                    except Exception as e:
                        logger.warning(f"Failed to cancel TP order {tp_oid}: {e}")
            
            if cancelled:
                logger.info(f"Cancelled trigger orders: {', '.join(cancelled)}")
        
        # Get exit price if not provided
        if exit_price is None:
            exit_price = self.client.get_mid_price(symbol)
        
        # Calculate P&L on remaining position
        if trade.side == 'long':
            pnl = (exit_price - trade.entry_price) * trade.position_size
        else:  # short
            pnl = (trade.entry_price - exit_price) * trade.position_size
        
        # Add to existing P&L from partial closes
        total_pnl = trade.pnl + pnl
        
        # Subtract commission for final close
        commission = trade.position_value * self.risk.commission_pct
        total_pnl -= commission
        
        # Update trade
        trade.exit_price = exit_price
        trade.exit_time = datetime.now().isoformat()
        trade.pnl = total_pnl
        trade.exit_reason = reason
        trade.status = "closed"
        
        # Log
        pnl_pct = (total_pnl / trade.original_value) * 100 if trade.original_value > 0 else 0
        emoji = "[WIN]" if total_pnl > 0 else "[LOSS]"
        
        # Build partial close summary
        partial_summary = ""
        if trade.partial_closes:
            partial_summary = "\nPartial Closes:\n" + "\n".join([
                f"  {pc.level}: ${pc.pnl:+.2f} at ${pc.price:,.2f}"
                for pc in trade.partial_closes
            ])
        
        logger.info(f"""
=== POSITION CLOSED {emoji} ===
Symbol: {symbol}
Side: {trade.side.upper()}
Entry: ${trade.entry_price:,.2f}
Exit: ${exit_price:,.2f}
Total P&L: ${total_pnl:+.2f} ({pnl_pct:+.2f}%)
Reason: {reason}{partial_summary}
==========================
        """)
        
        # Move to history
        self.trade_history.append(trade.to_dict())
        del self.open_trades[symbol]
        self._save_state()
        
        return trade
    
    def close_position_real(self, symbol: str, trade: Optional[Trade] = None) -> Dict:
        """
        Close a position on Hyperliquid using real API call
        Also cancels any open SL/TP trigger orders
        
        Args:
            symbol: Coin symbol
            trade: Optional Trade object to cancel SL/TP orders for
        
        Returns:
            API response from Hyperliquid
        """
        # Cancel SL/TP trigger orders first
        if trade:
            cancelled_orders = []
            
            # Cancel SL order
            if trade.sl_order_id:
                try:
                    self.client.cancel_order(symbol, int(trade.sl_order_id))
                    cancelled_orders.append(f"SL:{trade.sl_order_id}")
                except Exception as e:
                    logger.warning(f"Failed to cancel SL order {trade.sl_order_id}: {e}")
            
            # Cancel TP orders
            for tp_oid in trade.tp_order_ids:
                if tp_oid:
                    try:
                        self.client.cancel_order(symbol, int(tp_oid))
                        cancelled_orders.append(f"TP:{tp_oid}")
                    except Exception as e:
                        logger.warning(f"Failed to cancel TP order {tp_oid}: {e}")
            
            if cancelled_orders:
                logger.info(f"Cancelled trigger orders: {', '.join(cancelled_orders)}")
        
        # Close the position
        try:
            result = self.client.close_position_market(symbol)
            logger.info(f"Position closed on exchange: {symbol}")
            
            # Also update local state if tracking this trade
            if symbol in self.open_trades:
                trade = self.open_trades[symbol]
                trade.status = "closed"
                trade.exit_time = datetime.now().isoformat()
                trade.exit_reason = "manual_real"
                self.trade_history.append(trade.to_dict())
                del self.open_trades[symbol]
                self._save_state()
            
            return result
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            raise
    
    def open_position_real(self, symbol: str, side: str, sz: float, 
                          limit_px: Optional[float] = None,
                          order_type: str = "Market",
                          stop_loss: Optional[float] = None,
                          take_profits: Optional[list] = None) -> Dict:
        """
        Open a real position on Hyperliquid with optional SL/TP trigger orders
        
        Args:
            symbol: Coin symbol (BTC, ETH, SOL)
            side: 'long' or 'short'
            sz: Position size in coins
            limit_px: Limit price (uses current price if None)
            order_type: 'Market' or 'Limit'
            stop_loss: Stop loss price (optional)
            take_profits: List of take profit prices (optional)
        
        Returns:
            API response dict with entry order result and SL/TP order IDs
        """
        is_buy = side == 'long'
        
        # Round size to appropriate precision for HyperLiquid
        # Different assets have different szDecimals:
        # SOL: 2 decimals, BTC: 5 decimals, ETH: 4 decimals
        sz_decimals = {
            'SOL': 2, 'BTC': 5, 'ETH': 4
        }.get(symbol, 4)
        sz = round(sz, sz_decimals)
        
        # Get current price if not provided
        if limit_px is None:
            limit_px = self.client.get_mid_price(symbol)
        
        # Round price to tick size (HyperLiquid requires specific price increments)
        # BTC: $1 tick, ETH: $0.05 tick, SOL: $0.01 tick (approximate)
        tick_sizes = {'BTC': 1, 'ETH': 0.05, 'SOL': 0.01}
        tick = tick_sizes.get(symbol, 0.01)
        
        # Round to tick size
        decimals = len(str(tick).split('.')[-1]) if '.' in str(tick) else 0
        limit_px = round(round(limit_px / tick) * tick, decimals)
        
        # Apply slippage for market orders to ensure immediate fill
        # HyperLiquid uses IOC limit orders for "market" behavior
        if order_type == "Market":
            if is_buy:
                # Buying - use higher price (0.5% slippage)
                limit_px = round(round(limit_px * 1.005 / tick) * tick, decimals)
            else:
                # Selling - use lower price (0.5% slippage)
                limit_px = round(round(limit_px * 0.995 / tick) * tick, decimals)
            logger.info(f"Using aggressive entry price: ${limit_px:,.2f} (with 0.5% slippage)")
        
        try:
            # Set leverage on HyperLiquid before placing order
            leverage = int(self.risk.leverage)
            try:
                self.client._exchange.update_leverage(leverage, symbol, is_cross=True)
                logger.info(f"Set leverage to {leverage}x for {symbol}")
            except Exception as e:
                logger.warning(f"Failed to set leverage for {symbol}: {e}")
            
            # Place entry order
            result = self.client.place_order(
                coin=symbol,
                is_buy=is_buy,
                sz=sz,
                limit_px=limit_px,
                order_type=order_type,
                reduce_only=False
            )
            logger.info(f"Order placed on exchange: {symbol} {'BUY' if is_buy else 'SELL'} {sz} @ ${limit_px:,.2f}")
            
            # Extract entry order ID and check for errors
            entry_oid = None
            entry_error = None
            if result:
                if 'order_id' in result:
                    entry_oid = result['order_id']
                elif 'response' in result and 'data' in result['response']:
                    statuses = result['response']['data'].get('statuses', [])
                    if statuses and len(statuses) > 0:
                        status = statuses[0]
                        if 'filled' in status:
                            entry_oid = status['filled'].get('oid')
                        elif 'oid' in status:
                            entry_oid = status['oid']
                        elif 'error' in status:
                            entry_error = status['error']
            
            # If entry order failed, don't place SL/TP orders
            if not entry_oid:
                error_msg = entry_error if entry_error else "Unknown error"
                logger.error(f"Entry order failed: {error_msg}. Not placing SL/TP orders.")
                return {
                    'entry': result,
                    'entry_oid': None,
                    'sl_oid': None,
                    'tp_oids': [],
                    'error': error_msg
                }
            
            # Place SL trigger order ONLY if entry succeeded
            sl_oid = None
            if stop_loss and stop_loss > 0:
                try:
                    # For long: SL is a sell order below entry
                    # For short: SL is a buy order above entry
                    sl_is_buy = side == 'short'
                    
                    # Use current price as limit price for market execution
                    # Round to tick size to avoid "Price must be divisible by tick size" error
                    current_price = self.client.get_mid_price(symbol)
                    tick_sizes = {'BTC': 1, 'ETH': 0.05, 'SOL': 0.01}
                    tick = tick_sizes.get(symbol, 0.01)
                    # Use integer math to avoid floating point precision errors
                    # e.g., 1569.85 / 0.05 = 31396.999999999996 (wrong) vs int(1569.85 * 100) / int(0.05 * 100) = 31397
                    multiplier = 100 if tick < 1 else 1
                    current_price_int = int(round(current_price * multiplier))
                    tick_int = int(round(tick * multiplier))
                    ticks = current_price_int // tick_int
                    current_price = ticks * tick
                    
                    sl_result = self.client.place_trigger_order(
                        coin=symbol,
                        is_buy=sl_is_buy,
                        sz=sz,
                        trigger_px=stop_loss,
                        limit_px=current_price,
                        tpsl='sl',
                        is_market=True,
                        reduce_only=True
                    )
                    
                    # Extract SL order ID
                    if sl_result and 'response' in sl_result and 'data' in sl_result['response']:
                        statuses = sl_result['response']['data'].get('statuses', [])
                        if statuses and len(statuses) > 0:
                            status = statuses[0]
                            # Check for 'resting' (trigger order waiting) or 'oid' directly
                            if 'resting' in status and 'oid' in status['resting']:
                                sl_oid = status['resting']['oid']
                            elif 'oid' in status:
                                sl_oid = status['oid']
                    
                    logger.info(f"SL trigger order placed: {symbol} @ ${stop_loss:.2f} (oid={sl_oid})")
                except Exception as e:
                    logger.error(f"Failed to place SL trigger order: {e}")
            
            # Place TP trigger orders
            tp_oids = []
            if take_profits:
                for i, tp_price in enumerate(take_profits):
                    if not tp_price or tp_price <= 0:
                        continue
                    try:
                        # For long: TP is a sell order above entry
                        # For short: TP is a buy order below entry
                        tp_is_buy = side == 'short'
                        
                        # Use current price as limit price for market execution
                        # Round to tick size to avoid "Price must be divisible by tick size" error
                        current_price = self.client.get_mid_price(symbol)
                        tick_sizes = {'BTC': 1, 'ETH': 0.05, 'SOL': 0.01}
                        tick = tick_sizes.get(symbol, 0.01)
                        # Use integer math to avoid floating point precision errors
                        multiplier = 100 if tick < 1 else 1
                        current_price_int = int(round(current_price * multiplier))
                        tick_int = int(round(tick * multiplier))
                        ticks = current_price_int // tick_int
                        current_price = ticks * tick
                        
                        tp_result = self.client.place_trigger_order(
                            coin=symbol,
                            is_buy=tp_is_buy,
                            sz=sz,
                            trigger_px=tp_price,
                            limit_px=current_price,
                            tpsl='tp',
                            is_market=True,
                            reduce_only=True
                        )
                        
                        # Extract TP order ID
                        tp_oid = None
                        if tp_result and 'response' in tp_result and 'data' in tp_result['response']:
                            statuses = tp_result['response']['data'].get('statuses', [])
                            if statuses and len(statuses) > 0:
                                status = statuses[0]
                                # Check for 'resting' (trigger order waiting) or 'oid' directly
                                if 'resting' in status and 'oid' in status['resting']:
                                    tp_oid = status['resting']['oid']
                                elif 'oid' in status:
                                    tp_oid = status['oid']
                        
                        if tp_oid:
                            tp_oids.append(tp_oid)
                        
                        logger.info(f"TP{i+1} trigger order placed: {symbol} @ ${tp_price:.2f} (oid={tp_oid})")
                    except Exception as e:
                        logger.error(f"Failed to place TP{i+1} trigger order: {e}")
            
            # Return combined result with order IDs
            return {
                'entry': result,
                'entry_oid': entry_oid,
                'sl_oid': sl_oid,
                'tp_oids': tp_oids
            }
            
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise
    
    def update_positions(self):
        """
        Sync local positions with HyperLiquid and check for exits.
        With native SL/TP trigger orders, exits happen on HyperLiquid.
        This method syncs local state when positions are closed by trigger orders.
        """
        # Get current positions from HyperLiquid
        try:
            hl_positions = self.client.get_positions()
            hl_position_symbols = {p['coin'] for p in hl_positions if abs(p['size']) > 0.001}
        except Exception as e:
            logger.warning(f"Failed to get HyperLiquid positions: {e}")
            hl_position_symbols = set()
        
        # Check local positions that no longer exist on HyperLiquid
        local_symbols = list(self.open_trades.keys())
        for symbol in local_symbols:
            if symbol not in hl_position_symbols:
                # Position was closed on HyperLiquid (likely by SL/TP trigger)
                trade = self.open_trades[symbol]
                
                # Get the fill info to determine exit price and reason
                try:
                    from hyperliquid.info import Info
                    info = Info(base_url=self.client.TESTNET_URL)
                    fills = info.user_fills(self.client.wallet_address)
                    
                    # Find the most recent fill for this symbol
                    symbol_fills = [f for f in fills if f.get('coin') == symbol]
                    if symbol_fills:
                        latest_fill = symbol_fills[-1]
                        exit_px = float(latest_fill.get('px', 0))
                        
                        # Determine if it was SL or TP based on price vs SL/TP levels
                        exit_reason = 'trigger_exit'
                        if trade.side == 'long':
                            if exit_px <= trade.stop_loss * 1.001:  # Allow small tolerance
                                exit_reason = 'stop_loss'
                            elif trade.take_profits and exit_px >= trade.take_profits[0]['price'] * 0.999:
                                exit_reason = 'take_profit'
                        else:  # short
                            if exit_px >= trade.stop_loss * 0.999:
                                exit_reason = 'stop_loss'
                            elif trade.take_profits and exit_px <= trade.take_profits[0]['price'] * 1.001:
                                exit_reason = 'take_profit'
                        
                        logger.info(f"Position closed by HyperLiquid trigger: {symbol} @ ${exit_px:.2f} ({exit_reason})")
                        self.close_position(symbol, exit_px, exit_reason)
                    else:
                        # No fill info, close with current price
                        current_price = self.client.get_mid_price(symbol)
                        logger.info(f"Position closed on HyperLiquid (no fill info): {symbol}")
                        self.close_position(symbol, current_price, 'hyperliquid_closed')
                        
                except Exception as e:
                    # Fallback: close with current price
                    current_price = self.client.get_mid_price(symbol)
                    logger.warning(f"Error syncing closed position {symbol}: {e}")
                    self.close_position(symbol, current_price, 'hyperliquid_closed')
        
        # For positions that still exist locally and on HyperLiquid,
        # check for manual exit conditions (fallback in case trigger orders fail)
        for symbol in local_symbols:
            if symbol in hl_position_symbols:
                current_price = self.client.get_mid_price(symbol)
                if current_price == 0:
                    continue
                
                result = self.check_exit_conditions(symbol, current_price)
                if result:
                    action, data = result
                    
                    if action == 'stop_loss':
                        logger.warning(f"Manual SL check triggered for {symbol} (trigger order may have failed)")
                        self.close_position(symbol, current_price, 'stop_loss')
                    elif action == 'take_profit_partial':
                        self.partial_close_position(symbol, data, current_price)
                    elif action == 'take_profit_full':
                        self.close_position(symbol, current_price, 'take_profit')
    
    def get_portfolio_summary(self) -> Dict:
        """Get current portfolio summary with leverage"""
        # Get unrealized P&L for open positions
        unrealized_pnl = 0.0
        for symbol, trade in self.open_trades.items():
            current_price = self.client.get_mid_price(symbol)
            if current_price > 0:
                if trade.side == 'long':
                    unrealized_pnl += (current_price - trade.entry_price) * trade.position_size
                else:
                    unrealized_pnl += (trade.entry_price - current_price) * trade.position_size
        
        # Calculate realized P&L from history
        realized_pnl = sum(t.get('pnl', 0) for t in self.trade_history)
        
        # Current exposure (notional)
        total_exposure = sum(t.position_value for t in self.open_trades.values())
        
        # Margin used
        total_margin_used = sum(t.margin_required for t in self.open_trades.values())
        available_margin = self.risk.initial_capital - total_margin_used
        
        # Effective leverage
        effective_leverage = total_exposure / self.risk.initial_capital if self.risk.initial_capital > 0 else 0
        
        return {
            'initial_capital': self.risk.initial_capital,
            'current_exposure': total_exposure,
            'total_margin_used': total_margin_used,
            'available_margin': available_margin,
            'effective_leverage': effective_leverage,
            'open_positions': len(self.open_trades),
            'total_trades': len(self.trade_history) + len(self.open_trades),
            'closed_trades': len(self.trade_history),
            'realized_pnl': realized_pnl,
            'unrealized_pnl': unrealized_pnl,
            'total_pnl': realized_pnl + unrealized_pnl,
            'return_pct': ((realized_pnl + unrealized_pnl) / self.risk.initial_capital) * 100
        }
    
    def print_portfolio(self):
        """Print portfolio summary with leverage"""
        summary = self.get_portfolio_summary()
        
        print("\n" + "="*60)
        print("PORTFOLIO SUMMARY")
        print("="*60)
        print(f"Initial Capital:    ${summary['initial_capital']:>12,.2f}")
        print(f"Total Exposure:     ${summary['current_exposure']:>12,.2f}")
        print(f"Margin Used:        ${summary['total_margin_used']:>12,.2f}")
        print(f"Available Margin:   ${summary['available_margin']:>12,.2f}")
        print(f"Effective Leverage: {summary['effective_leverage']:>11,.2f}x")
        print(f"Open Positions:     {summary['open_positions']:>12}")
        print(f"Total Trades:       {summary['total_trades']:>12}")
        print("-"*60)
        
        pnl_emoji = "[+]" if summary['realized_pnl'] >= 0 else "[-]"
        print(f"Realized P&L:       ${summary['realized_pnl']:>+12,.2f} {pnl_emoji}")
        
        pnl_emoji = "[+]" if summary['unrealized_pnl'] >= 0 else "[-]"
        print(f"Unrealized P&L:     ${summary['unrealized_pnl']:>+12,.2f} {pnl_emoji}")
        
        total_pnl = summary['total_pnl']
        pnl_emoji = "[+]" if total_pnl >= 0 else "[-]"
        print(f"Total P&L:          ${total_pnl:>+12,.2f} {pnl_emoji}")
        print(f"Return:             {summary['return_pct']:>+11,.2f}%")
        print("="*60)
        
        if self.open_trades:
            print("\nOPEN POSITIONS:")
            print("-"*60)
            for symbol, trade in self.open_trades.items():
                current = self.client.get_mid_price(symbol)
                
                # Format times for display
                signal_time_str = ""
                if trade.signal_time:
                    try:
                        from datetime import datetime
                        signal_dt = datetime.fromisoformat(trade.signal_time.replace('Z', '+00:00'))
                        signal_time_str = signal_dt.strftime("%H:%M:%S")
                    except:
                        signal_time_str = trade.signal_time[:8] if len(trade.signal_time) > 8 else trade.signal_time
                
                order_time_str = ""
                if trade.order_placed_time:
                    try:
                        order_dt = datetime.fromisoformat(trade.order_placed_time.replace('Z', '+00:00'))
                        order_time_str = order_dt.strftime("%H:%M:%S")
                    except:
                        order_time_str = trade.order_placed_time[:8] if len(trade.order_placed_time) > 8 else trade.order_placed_time
                
                # Header with symbol and side
                time_info = f" | Signal: {signal_time_str}" if signal_time_str else ""
                order_info = f" | Order: {order_time_str}" if order_time_str else ""
                print(f"{symbol}: {trade.side.upper()} {trade.leverage:.0f}x{time_info}{order_info}")
                
                # Position details
                print(f"  Size: {trade.position_size:.4f} @ Entry: ${trade.entry_price:,.2f}")
                print(f"  Notional: ${trade.position_value:,.2f} | Margin: ${trade.margin_required:,.2f}")
                
                # SL/TP prices
                tp_price = trade.take_profits[0]['price'] if trade.take_profits else 0
                sl_distance = abs(trade.entry_price - trade.stop_loss) / trade.entry_price * 100
                tp_distance = abs(tp_price - trade.entry_price) / trade.entry_price * 100 if tp_price else 0
                print(f"  SL: ${trade.stop_loss:,.2f} ({sl_distance:.1f}%) | TP: ${tp_price:,.2f} ({tp_distance:.1f}%)")
                
                # Show HyperLiquid order IDs if available
                if trade.order_id or trade.sl_order_id or trade.tp_order_ids:
                    oid_info = []
                    if trade.order_id:
                        oid_info.append(f"Entry:{trade.order_id}")
                    if trade.sl_order_id:
                        oid_info.append(f"SL:{trade.sl_order_id}")
                    if trade.tp_order_ids:
                        oid_info.append(f"TP:{','.join(str(oid) for oid in trade.tp_order_ids if oid)}")
                    print(f"  HL Orders: {' | '.join(oid_info)}")
                
                # Current price and unrealized P&L
                if current > 0:
                    if trade.side == 'long':
                        unrealized = (current - trade.entry_price) * trade.position_size
                        price_change = (current - trade.entry_price) / trade.entry_price * 100
                    else:
                        unrealized = (trade.entry_price - current) * trade.position_size
                        price_change = (trade.entry_price - current) / trade.entry_price * 100
                    print(f"  Current: ${current:,.2f} ({price_change:+.2f}%) | Unrealized: ${unrealized:+.2f}")
                print()
            print("="*60)


def execute_signal(signal: Dict, test_mode: bool = True) -> Optional[Trade]:
    """
    Execute a trading signal
    
    Expected signal format:
    {
        "coin": "BTC",
        "action": "BUY" | "SELL" | "HOLD",
        "confidence": 0.85,
        "strategy": "fvg_proximity",
        "meta": {
            "price": 65000.0,
            "stop_loss_pct": 1.5,      # Strategy-provided SL %
            "take_profit_pct": 3.0,    # Strategy-provided TP %
            ...
        }
    }
    """
    action = signal.get('action', 'HOLD')
    
    if action == 'HOLD':
        logger.info(f"Signal is HOLD, no action taken")
        return None
    
    coin = signal.get('coin')
    if not coin:
        logger.error("Signal missing 'coin' field")
        return None
    
    # Map action to side
    side_map = {
        'BUY': 'long',
        'SELL': 'short'
    }
    side = side_map.get(action)
    if not side:
        logger.error(f"Unknown action: {action}")
        return None
    
    # Get confidence
    confidence = signal.get('confidence', 1.0)
    
    # Get entry price from signal meta if available
    entry_price = None
    if 'meta' in signal and 'price' in signal['meta']:
        entry_price = signal['meta']['price']
    
    # Extract SL/TP from signal meta (strategy-provided) - convert % to decimal
    meta = signal.get('meta', {})
    stop_loss_pct = meta.get('stop_loss_pct')
    take_profit_pct = meta.get('take_profit_pct')
    
    # Get signal timestamp if available
    signal_time = signal.get('timestamp') or signal.get('created_at')
    
    if stop_loss_pct:
        stop_loss_pct = stop_loss_pct / 100  # Convert 1.5 -> 0.015
    if take_profit_pct:
        take_profit_pct = take_profit_pct / 100  # Convert 3.0 -> 0.03
    
    # Create executor with proper RiskConfig from account settings
    from signal_integrator import load_account_settings
    settings = load_account_settings()
    
    # Get actual account balance (use main wallet) - use spot balance not margin value
    from hyperliquid.info import Info
    try:
        info = Info(settings['api_url'], skip_ws=True)
        main_wallet = settings.get('main_wallet_address') or settings['wallet_address']
        # Get spot balance (real equity) not margin account value
        spot_state = info.spot_user_state(main_wallet)
        usdc_balance = 0.0
        for balance in spot_state.get('balances', []):
            if balance.get('coin') == 'USDC':
                usdc_balance = float(balance.get('total', 0))
                break
        account_value = usdc_balance if usdc_balance > 0 else 1000.0
    except:
        account_value = 1000.0
    
    risk_config = RiskConfig(
        initial_capital=account_value,
        risk_per_trade_pct=settings['position_size_pct'] / 100,
        leverage=settings['leverage'],
        stop_loss_pct=settings['stop_loss'] / 100,
        max_open_positions=3 if not settings['allow_multiple_positions'] else 10
    )
    
    executor = TradeExecutor(risk_config)
    
    # Get strategy from signal
    strategy = signal.get('strategy', 'unknown')
    
    if test_mode:
        logger.info(f"[TEST MODE] Would open {side} position in {coin} (SL: {stop_loss_pct*100 if stop_loss_pct else 'default'}%, TP: {take_profit_pct*100 if take_profit_pct else 'default'}%)")
        return executor.open_position(coin, side, entry_price, confidence, stop_loss_pct, take_profit_pct, signal_time, strategy)
    else:
        # LIVE MODE: Place real order on HyperLiquid FIRST, verify fill, THEN create local record
        logger.info(f"[LIVE MODE] Opening {side} position in {coin} (SL: {stop_loss_pct*100 if stop_loss_pct else 'default'}%, TP: {take_profit_pct*100 if take_profit_pct else 'default'}%)")
        
        try:
            # Step 1: Calculate position details (without saving to state yet)
            if not entry_price:
                entry_price = executor.client.get_mid_price(coin)
            
            # Calculate stop loss price
            if stop_loss_pct:
                sl_pct = stop_loss_pct
            else:
                sl_pct = executor.risk.stop_loss_pct
            
            if side == 'long':
                stop_loss = entry_price * (1 - sl_pct)
            else:
                stop_loss = entry_price * (1 + sl_pct)
            
            # Round stop loss to tick size for HyperLiquid
            tick_sizes = {'BTC': 1, 'ETH': 0.05, 'SOL': 0.01}
            tick = tick_sizes.get(coin, 0.01)
            decimals = len(str(tick).split('.')[-1]) if '.' in str(tick) else 0
            stop_loss = round(round(stop_loss / tick) * tick, decimals)
            
            # Calculate position size
            position_size, position_value, margin_required = executor.calculate_position_size(
                entry_price, stop_loss, side, coin, sl_pct
            )
            
            if position_size <= 0 or position_value <= 0:
                logger.error(f"Invalid position size calculated: {position_size}")
                return None
            
            # Note: Position size is now based purely on risk_per_trade_pct from account settings
            # Confidence is used for signal filtering only, not position scaling
            
            # Check if we can open position
            can_open, reason = executor.can_open_position(coin, margin_required, strategy)
            if not can_open:
                logger.warning(f"Cannot open position: {reason}")
                return None
            
            # Calculate take profits - use strategy-provided TP % if available, else from risk config
            if take_profit_pct:
                # Strategy provided specific TP %
                if side == 'long':
                    tp_price = entry_price * (1 + take_profit_pct)
                else:
                    tp_price = entry_price * (1 - take_profit_pct)
                tp_price = round(round(tp_price / tick) * tick, decimals)
                tp_prices = [tp_price]
                take_profits = [{
                    'label': 'TP1',
                    'level_pct': take_profit_pct,
                    'price': tp_price,
                    'close_pct': 1.0,
                    'hit': False
                }]
            else:
                # Fall back to risk config TP levels
                take_profits = executor.calculate_take_profits(entry_price, side)
                tp_prices_raw = [tp['price'] for tp in take_profits]
                tp_prices = [round(round(tp / tick) * tick, decimals) for tp in tp_prices_raw]
            
            # Step 2: Place order on HyperLiquid
            # open_position_real handles slippage automatically for Market orders
            result = executor.open_position_real(
                symbol=coin,
                side=side,
                sz=position_size,
                order_type="Market",
                stop_loss=stop_loss,
                take_profits=tp_prices
            )
            
            # Step 3: Verify order actually filled
            entry_oid = result.get('entry_oid') if result else None
            
            if not entry_oid:
                logger.error(f"Order did not fill - no entry order ID returned. Result: {result}")
                return None
            
            # Query fills to verify the order actually executed
            import time
            time.sleep(0.5)  # Brief delay for fill to process
            
            try:
                fills = executor.client.get_fills(coin, start_time=int((datetime.now() - timedelta(minutes=2)).timestamp() * 1000))
                order_filled = any(str(fill.get('oid')) == str(entry_oid) for fill in fills)
                
                if not order_filled:
                    logger.error(f"Order {entry_oid} was submitted but NOT FILLED (IOC cancelled or no match)")
                    # Cancel any SL/TP orders that may have been placed
                    if result.get('sl_oid'):
                        try:
                            executor.cancel_order(coin, int(result['sl_oid']))
                            logger.info(f"Cancelled unfilled SL order: {result['sl_oid']}")
                        except:
                            pass
                    for tp_oid in result.get('tp_oids', []):
                        if tp_oid:
                            try:
                                executor.cancel_order(coin, int(tp_oid))
                                logger.info(f"Cancelled unfilled TP order: {tp_oid}")
                            except:
                                pass
                    return None
                
                logger.info(f"✓ Order {entry_oid} verified as FILLED")
                
            except Exception as e:
                logger.warning(f"Could not verify fill (proceeding anyway): {e}")
            
            # Step 4: Create local trade record ONLY after verified fill
            now = datetime.now().isoformat()
            trade = Trade(
                symbol=coin,
                side=side,
                entry_price=entry_price,
                position_size=position_size,
                original_size=position_size,
                position_value=position_value,
                original_value=position_value,
                margin_required=margin_required,
                leverage=executor.risk.leverage,
                stop_loss=stop_loss,
                take_profits=take_profits,
                risk_amount=executor.risk.risk_per_trade * confidence,
                entry_time=now,
                status="open",
                remaining_pct=1.0,
                signal_time=signal_time or now,
                strategy=strategy,
                order_id=entry_oid,
                sl_order_id=result.get('sl_oid'),
                tp_order_ids=result.get('tp_oids', []),
                order_placed_time=now
            )
            
            executor.open_trades[coin] = trade
            executor._save_state()
            
            logger.info(f"""
=== HYPERLIQUID ORDERS PLACED & VERIFIED ===
Entry: {coin} {side} @ ${entry_price:.2f} (oid={entry_oid})
Stop Loss: ${stop_loss:.2f} (oid={result.get('sl_oid')})
Take Profits: {len(result.get('tp_oids', []))} orders placed
=================================
            """)
            
            return trade
            
        except Exception as e:
            logger.error(f"Failed to place order on HyperLiquid: {e}")
            return None


if __name__ == "__main__":
    # Test the executor
    print("Testing Trade Executor...")
    
    # Create executor with default risk config
    executor = TradeExecutor()
    
    # Print current prices
    print("\nCurrent Prices:")
    for coin in ['BTC', 'ETH', 'SOL']:
        price = executor.client.get_mid_price(coin)
        print(f"  {coin}: ${price:,.2f}")
    
    # Print portfolio
    executor.print_portfolio()
    
    # Test opening a position (paper trading)
    print("\n--- Testing position opening ---")
    trade = executor.open_position('BTC', 'long', confidence=0.9)
    if trade:
        print(f"\nOpened trade: {trade.to_dict()}")
    
    executor.print_portfolio()
