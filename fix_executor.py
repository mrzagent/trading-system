"""
Script to patch trade_executor.py with working SDK implementation
"""
import re

# Read the original file
with open('trade_executor.py', 'r') as f:
    content = f.read()

# Find the HyperliquidClient class and replace the place_order method
# We'll add SDK imports and replace the entire place_order implementation

# Add SDK imports after the existing imports
sdk_imports = '''
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
'''

# Find where to insert SDK imports (after ETH_ACCOUNT_AVAILABLE check)
insert_marker = "ETH_ACCOUNT_AVAILABLE = False"
if insert_marker in content:
    content = content.replace(
        insert_marker,
        insert_marker + sdk_imports
    )

# Replace the HyperliquidClient.__init__ to initialize SDK
old_init = '''    def __init__(self, wallet_address: Optional[str] = None, private_key: Optional[str] = None):
        # Agent wallet for signing transactions
        self.wallet_address = wallet_address or os.getenv('HYPERLIQUID_WALLET')
        self.private_key = private_key or os.getenv('HYPERLIQUID_PRIVATE_KEY')
        self.session = requests.Session()
        
        if not self.wallet_address:
            logger.warning("No wallet address provided. Running in read-only mode.")'''

new_init = '''    def __init__(self, wallet_address: Optional[str] = None, private_key: Optional[str] = None):
        # Agent wallet for signing transactions
        self.wallet_address = wallet_address or os.getenv('HYPERLIQUID_WALLET')
        self.private_key = private_key or os.getenv('HYPERLIQUID_PRIVATE_KEY')
        self.session = requests.Session()
        
        # Initialize HyperLiquid SDK
        self._exchange = None
        self._info = None
        self._meta = None
        if HYPERLIQUID_SDK_AVAILABLE and self.private_key:
            try:
                wallet: LocalAccount = Account.from_key(self.private_key)
                self._info = Info(base_url=self.TESTNET_URL, skip_ws=True)
                self._meta = self._info.meta()
                self._exchange = Exchange(
                    wallet=wallet,
                    base_url=self.TESTNET_URL,
                    account_address=self.MAIN_WALLET,
                    meta=self._meta
                )
                logger.info("HyperLiquid SDK initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize HyperLiquid SDK: {e}")
        
        if not self.wallet_address:
            logger.warning("No wallet address provided. Running in read-only mode.")'''

content = content.replace(old_init, new_init)

# Replace the place_order method
old_place_order = '''    def place_order(self, coin: str, is_buy: bool, sz: float, limit_px: float,
                    order_type: str = "Limit", reduce_only: bool = False) -> Dict:
        """Place an order on Hyperliquid testnet
        
        Args:
            coin: Asset symbol (e.g., 'BTC', 'ETH')
            is_buy: True for buy, False for sell
            sz: Order size in base currency
            limit_px: Limit price
            order_type: "Limit" or "Market"
            reduce_only: If True, only reduces position (for closing)
        
        Returns:
            API response dict
        """
        try:
            from eth_account import Account
            from eth_account.messages import encode_defunct
            ETH_ACCOUNT_AVAILABLE_NOW = True
        except ImportError:
            ETH_ACCOUNT_AVAILABLE_NOW = False
        
        if not ETH_ACCOUNT_AVAILABLE_NOW:
            raise RuntimeError("eth-account not installed. Run: pip install eth-account")
        
        if not self.wallet_address or not self.private_key:
            raise ValueError("Wallet address and private key required for trading")
        
        # Round size and price to appropriate decimals
        sz = round(sz, 6)
        limit_px = round(limit_px, 2)
        
        # Build order action
        order_action = {
            "type": "order",
            "orders": [{
                "coin": coin,
                "is_buy": is_buy,
                "sz": str(sz),
                "limit_px": str(limit_px),
                "order_type": order_type,
                "reduce_only": reduce_only
            }],
            "grouping": "na",
            "builder": None
        }
        
        # Get nonce (current timestamp in ms)
        nonce = int(time.time() * 1000)
        
        # Build the action payload for signing
        action = {
            "type": "order",
            "orders": order_action["orders"],
            "grouping": "na",
            "builder": None
        }
        
        # Create signature for Hyperliquid
        try:
            account = Account.from_key(self.private_key)
            
            # Hyperliquid uses a specific signing format
            # Message format: action JSON + nonce
            message_str = json.dumps(action, separators=(',', ':'), sort_keys=True) + str(nonce)
            message = encode_defunct(text=message_str)
            signed = account.sign_message(message)
            signature = signed.signature.hex()
            
        except Exception as e:
            logger.error(f"Failed to create signature: {e}")
            raise
        
        # Build final payload
        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature
        }
        
        # Submit to exchange
        try:
            response = self._post("/exchange", payload)
            logger.info(f"Order submitted: {coin} {'BUY' if is_buy else 'SELL'} {sz} @ ${limit_px}")
            return response
        except Exception as e:
            logger.error(f"Order failed: {e}")
            # Try to get more details from response
            try:
                import requests
                if isinstance(e, requests.exceptions.HTTPError):
                    logger.error(f"Response status: {e.response.status_code}")
                    logger.error(f"Response body: {e.response.text}")
                    logger.error(f"Request payload: {json.dumps(payload, indent=2)}")
            except Exception as log_err:
                logger.error(f"Could not log response details: {log_err}")
            raise'''

new_place_order = '''    def place_order(self, coin: str, is_buy: bool, sz: float, limit_px: float,
                    order_type: str = "Limit", reduce_only: bool = False) -> Dict:
        """Place an order on Hyperliquid testnet using official SDK
        
        Args:
            coin: Asset symbol (e.g., 'BTC', 'ETH')
            is_buy: True for buy, False for sell
            sz: Order size in base currency
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
            sdk_order_type: OrderType = {"limit": {"tif": "Ioc"}}
        else:
            # Default to GTC (Good Till Canceled) for limit orders
            sdk_order_type: OrderType = {"limit": {"tif": "Gtc"}}
        
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
            raise'''

content = content.replace(old_place_order, new_place_order)

# Write the patched file
with open('trade_executor.py', 'w') as f:
    f.write(content)

print("trade_executor.py patched successfully!")
print("\nChanges made:")
print("1. Added HyperLiquid SDK imports")
print("2. Modified HyperliquidClient.__init__ to initialize SDK")
print("3. Replaced place_order with SDK implementation")
