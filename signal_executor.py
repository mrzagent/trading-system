#!/usr/bin/env python3
"""
signal_executor.py — Execute trades based on signals with auto SL/TP
Handles real order placement on Hyperliquid with risk management
"""
import os
import sys
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from dotenv import load_dotenv
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants
from eth_account import Account

load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

TRADE_LOG_FILE = r'D:\dev\trading\.trade_log.json'

class SignalExecutor:
    """Execute signals with automated risk management"""
    
    def __init__(self):
        self.wallet_address = os.getenv('HYPERLIQUID_WALLET')
        private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
        
        if not self.wallet_address or not private_key:
            raise ValueError("HYPERLIQUID_WALLET and HYPERLIQUID_PRIVATE_KEY required")
        
        # Create account and clients
        self.account = Account.from_key(private_key)
        self.exchange = Exchange(self.account, base_url=constants.TESTNET_API_URL)
        self.info = Info(constants.TESTNET_API_URL)
        
        # Default risk parameters
        self.default_sl_pct = 0.05      # 5% price move = 15% position loss (3x)
        self.default_tp_pct = 0.10      # 10% price move = 30% position profit (3x)
        self.default_leverage = 3.0     # 3x leverage
        self.min_notional = 10.0        # $10 minimum
        
    def get_position(self, coin: str) -> Optional[Dict]:
        """Get current position for a coin"""
        try:
            user_state = self.info.user_state(self.wallet_address)
            for pos_data in user_state.get('assetPositions', []):
                position = pos_data.get('position', {})
                if position.get('coin') == coin:
                    return {
                        'coin': coin,
                        'size': float(position.get('szi', 0)),
                        'entry_px': float(position.get('entryPx', 0)),
                        'unrealized_pnl': float(position.get('unrealizedPnl', 0))
                    }
            return None
        except Exception as e:
            print(f"[X] Error getting position for {coin}: {e}")
            return None
    
    def get_open_orders(self, coin: str) -> List[Dict]:
        """Get open orders for a coin"""
        try:
            user_state = self.info.user_state(self.wallet_address)
            orders = []
            for order in user_state.get('openOrders', []):
                if order.get('coin') == coin:
                    orders.append(order)
            return orders
        except Exception as e:
            print(f"[X] Error getting orders for {coin}: {e}")
            return []
    
    def get_portfolio_value(self) -> float:
        """Get total portfolio value (account value)"""
        try:
            user_state = self.info.user_state(self.wallet_address)
            # Account value includes margin + unrealized PnL
            return float(user_state.get('marginSummary', {}).get('accountValue', 0))
        except Exception as e:
            print(f"[X] Error getting portfolio value: {e}")
            return 0.0
    
    def calculate_position_size_pct(self, coin: str, portfolio_pct: float = 0.02) -> Tuple[float, float, int]:
        """Calculate position size as percentage of portfolio
        
        Args:
            coin: Asset symbol
            portfolio_pct: Percentage of portfolio to use (0.02 = 2%)
            
        Returns:
            Tuple of (size, notional, sz_decimals)
        """
        portfolio_value = self.get_portfolio_value()
        notional = portfolio_value * portfolio_pct
        
        # Ensure minimum notional
        notional = max(notional, self.min_notional)
        
        meta = self.info.meta()
        coin_info = next((a for a in meta["universe"] if a["name"] == coin), None)
        sz_decimals = coin_info["szDecimals"] if coin_info else 2
        
        # Get current price
        mids = self.info.all_mids()
        price = float(mids.get(coin, 0))
        
        # Calculate size
        sz = round(notional / price, sz_decimals)
        
        return sz, notional, sz_decimals
    
    def cancel_orders(self, coin: str) -> bool:
        """Cancel all open orders for a coin"""
        try:
            orders = self.get_open_orders(coin)
            for order in orders:
                oid = order.get('oid')
                if oid:
                    self.exchange.cancel(coin, oid)
                    print(f"  Cancelled order {oid}")
            return True
        except Exception as e:
            print(f"[X] Error cancelling orders: {e}")
            return False
    
    def calculate_position_size(self, coin: str, notional: float) -> Tuple[float, int]:
        """Calculate position size in coin units"""
        meta = self.info.meta()
        coin_info = next((a for a in meta["universe"] if a["name"] == coin), None)
        sz_decimals = coin_info["szDecimals"] if coin_info else 2
        
        # Get current price
        mids = self.info.all_mids()
        price = float(mids.get(coin, 0))
        
        # Ensure minimum notional
        actual_notional = max(notional, self.min_notional)
        
        # Calculate size
        sz = round(actual_notional / price, sz_decimals)
        
        return sz, sz_decimals
    
    def execute_signal(
        self, 
        coin: str, 
        action: str,  # 'BUY' or 'SELL'
        confidence: float = 0.5,
        notional: float = None,
        portfolio_pct: float = None,
        leverage: float = None,
        sl_pct: float = None,
        tp_pct: float = None
    ) -> Dict:
        """Execute a trading signal with SL/TP"""
        
        # Use defaults if not specified
        leverage = leverage or self.default_leverage
        sl_pct = sl_pct or self.default_sl_pct
        tp_pct = tp_pct or self.default_tp_pct
        
        # Determine sizing method
        if portfolio_pct:
            sz, actual_notional, sz_decimals = self.calculate_position_size_pct(coin, portfolio_pct)
            size_desc = f"{portfolio_pct*100:.0f}% of portfolio (${actual_notional:.2f})"
        elif notional:
            sz, sz_decimals = self.calculate_position_size(coin, notional)
            mids = self.info.all_mids()
            entry_px = float(mids.get(coin, 0))
            actual_notional = sz * entry_px
            size_desc = f"${notional:.2f} fixed"
        else:
            sz, actual_notional, sz_decimals = self.calculate_position_size_pct(coin, 0.02)
            size_desc = f"2% default (${actual_notional:.2f})"
        
        print(f"\n[EXECUTING] {coin} {action}")
        print(f"  Confidence: {confidence:.2f}")
        print(f"  Size: {size_desc}")
        print(f"  Leverage: {leverage:.0f}x")
        print(f"  SL: {sl_pct*100:.0f}% | TP: {tp_pct*100:.0f}%")
        
        # Check existing position
        existing_pos = self.get_position(coin)
        if existing_pos and existing_pos['size'] != 0:
            print(f"  [SKIP] Already have {coin} position: {existing_pos['size']}")
            return {'status': 'skipped', 'reason': 'existing_position', 'coin': coin}
        
        # Get current price
        mids = self.info.all_mids()
        entry_px = float(mids.get(coin, 0))
        actual_notional = sz * entry_px
        
        print(f"  Entry Price: ${entry_px:.2f}")
        print(f"  Size: {sz} {coin}")
        print(f"  Actual Notional: ${actual_notional:.2f}")
        
        # Calculate SL/TP prices
        is_long = action == 'BUY'
        
        if is_long:
            sl_px = round(entry_px * (1 - sl_pct), 2)
            tp_px = round(entry_px * (1 + tp_pct), 2)
        else:
            sl_px = round(entry_px * (1 + sl_pct), 2)
            tp_px = round(entry_px * (1 - tp_pct), 2)
        
        print(f"  SL Price: ${sl_px:.2f}")
        print(f"  TP Price: ${tp_px:.2f}")
        
        # Place entry order (market order with 1% slippage limit)
        limit_px = round(entry_px * 1.01, 2) if is_long else round(entry_px * 0.99, 2)
        
        print(f"\n  Placing entry order...")
        entry_result = self.exchange.order(
            coin,
            is_long,  # is_buy
            sz,
            limit_px,
            {"limit": {"tif": "Gtc"}},
            False  # reduce_only
        )
        
        if entry_result.get("status") != "ok":
            error = entry_result.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("error", "Unknown error")
            print(f"  [X] Entry failed: {error}")
            return {'status': 'failed', 'reason': error, 'coin': coin}
        
        # Check if filled
        statuses = entry_result.get("response", {}).get("data", {}).get("statuses", [])
        filled_px = None
        for status in statuses:
            if "filled" in status:
                filled_px = float(status["filled"].get("avgPx", entry_px))
                print(f"  [OK] Filled @ ${filled_px:.2f}")
            elif "resting" in status:
                print(f"  [INFO] Order resting (OID: {status['resting'].get('oid')})")
        
        # Use filled price or entry price for SL/TP
        actual_entry = filled_px or entry_px
        
        # Recalculate SL/TP based on actual fill
        if is_long:
            actual_sl = round(actual_entry * (1 - sl_pct), 2)
            actual_tp = round(actual_entry * (1 + tp_pct), 2)
        else:
            actual_sl = round(actual_entry * (1 + sl_pct), 2)
            actual_tp = round(actual_entry * (1 - tp_pct), 2)
        
        # Place Stop Loss (trigger order)
        print(f"\n  Placing Stop Loss @ ${actual_sl:.2f}...")
        sl_result = self.exchange.order(
            coin,
            not is_long,  # opposite side
            sz,
            actual_sl,
            {"trigger": {"isMarket": True, "triggerPx": actual_sl, "tpsl": "sl"}},
            True  # reduce_only
        )
        
        if sl_result.get("status") == "ok":
            print(f"  [OK] SL placed")
        else:
            print(f"  [X] SL failed: {sl_result}")
        
        # Place Take Profit (limit order)
        print(f"\n  Placing Take Profit @ ${actual_tp:.2f}...")
        tp_result = self.exchange.order(
            coin,
            not is_long,  # opposite side
            sz,
            actual_tp,
            {"limit": {"tif": "Gtc"}},
            True  # reduce_only
        )
        
        if tp_result.get("status") == "ok":
            print(f"  [OK] TP placed")
        else:
            print(f"  [X] TP failed: {tp_result}")
        
        # Log trade
        trade_record = {
            'timestamp': datetime.now().isoformat(),
            'coin': coin,
            'action': action,
            'confidence': confidence,
            'entry_px': actual_entry,
            'size': sz,
            'notional': actual_notional,
            'leverage': leverage,
            'sl_px': actual_sl,
            'tp_px': actual_tp,
            'sl_oid': sl_result.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("resting", {}).get("oid"),
            'tp_oid': tp_result.get("response", {}).get("data", {}).get("statuses", [{}])[0].get("resting", {}).get("oid"),
        }
        self._log_trade(trade_record)
        
        return {
            'status': 'success',
            'coin': coin,
            'action': action,
            'entry_px': actual_entry,
            'size': sz,
            'sl_px': actual_sl,
            'tp_px': actual_tp,
            'sl_placed': sl_result.get("status") == "ok",
            'tp_placed': tp_result.get("status") == "ok"
        }
    
    def _log_trade(self, trade: Dict):
        """Append trade to log file"""
        try:
            trades = []
            if os.path.exists(TRADE_LOG_FILE):
                with open(TRADE_LOG_FILE, 'r') as f:
                    trades = json.load(f)
            trades.append(trade)
            with open(TRADE_LOG_FILE, 'w') as f:
                json.dump(trades, f, indent=2)
        except Exception as e:
            print(f"[X] Error logging trade: {e}")
    
    def get_trade_history(self, limit: int = 10) -> List[Dict]:
        """Get recent trade history"""
        try:
            if os.path.exists(TRADE_LOG_FILE):
                with open(TRADE_LOG_FILE, 'r') as f:
                    trades = json.load(f)
                return trades[-limit:]
            return []
        except Exception as e:
            print(f"[X] Error reading trade log: {e}")
            return []

def main():
    """Test the executor"""
    executor = SignalExecutor()
    
    print("=" * 60)
    print("SIGNAL EXECUTOR TEST")
    print("=" * 60)
    
    # Check current positions
    for coin in ['BTC', 'ETH', 'SOL']:
        pos = executor.get_position(coin)
        if pos and pos['size'] != 0:
            print(f"\n{coin}: {pos['size']:.4f} @ ${pos['entry_px']:.2f} (PnL: ${pos['unrealized_pnl']:.2f})")
    
    print("\n[OK] Executor ready")

if __name__ == "__main__":
    main()
