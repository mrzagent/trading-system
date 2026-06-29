#!/usr/bin/env python3
"""Fetch positions from Hyperliquid for dashboard with local trade metadata"""
import sys
import os
import threading
import time
from datetime import datetime
sys.path.insert(0, r'D:\dev\trading')

from hyperliquid.info import Info
from dotenv import load_dotenv
import json

def load_account_settings():
    """Load account settings including environment and wallet addresses"""
    try:
        settings_path = r'D:\dev\trading\.account_settings.json'
        with open(settings_path, 'r') as f:
            settings = json.load(f)
        
        env = settings.get('environment', 'testnet')
        env_config = settings.get(env, {})
        
        return {
            'environment': env,
            'api_url': env_config.get('apiUrl', 'https://api.hyperliquid-testnet.xyz'),
            'main_wallet': env_config.get('mainWalletAddress', env_config.get('walletAddress', ''))
        }
    except Exception as e:
        print(f"Error loading account settings: {e}", file=sys.stderr)
        return {
            'environment': 'testnet',
            'api_url': 'https://api.hyperliquid-testnet.xyz',
            'main_wallet': '0x97c465489243175580fcDe624c2ef640c1897a00'
        }

# Load environment-specific settings
account_settings = load_account_settings()
ENVIRONMENT = account_settings['environment']
BASE_URL = account_settings['api_url']
MAIN_WALLET = account_settings['main_wallet'] or '0x97c465489243175580fcDe624c2ef640c1897a00'

# Debug output to stderr (not stdout which needs to be valid JSON)
# print(f"Using {ENVIRONMENT.upper()} environment: {BASE_URL}", file=sys.stderr)
# print(f"Main wallet: {MAIN_WALLET}", file=sys.stderr)

# Path to local trade state
TRADE_STATE_PATH = r'D:\dev\trading\trade_state.json'

result = {'positions': None, 'error': None}

def load_local_trade_metadata():
    """Load additional metadata from local trade_state.json"""
    try:
        if os.path.exists(TRADE_STATE_PATH):
            with open(TRADE_STATE_PATH, 'r') as f:
                state = json.load(f)
            return state.get('open_trades', {})
    except Exception as e:
        print(f"Warning: Could not load trade state: {e}", file=sys.stderr)
    return {}

def format_time(iso_time):
    """Format ISO timestamp to HH:MM:SS"""
    if not iso_time:
        return None
    try:
        # Handle both with and without timezone
        dt = datetime.fromisoformat(iso_time.replace('Z', '+00:00'))
        return dt.strftime('%H:%M:%S')
    except:
        return iso_time[:8] if len(str(iso_time)) > 8 else iso_time

def fetch_positions():
    try:
        # Load local metadata
        local_trades = load_local_trade_metadata()
        
        info = Info(base_url=BASE_URL)
        state = info.user_state(MAIN_WALLET)
        positions = []
        
        for pos in state.get('assetPositions', []):
            p = pos.get('position', {})
            coin = p.get('coin', '')
            size = float(p.get('szi', 0))
            entry = float(p.get('entryPx', 0))
            position_value = float(p.get('positionValue', 0))
            # Calculate mark price from position value / size
            mark = position_value / abs(size) if size != 0 else entry
            pnl = float(p.get('unrealizedPnl', 0))
            sl = float(p.get('stopLoss', 0)) if p.get('stopLoss') else 0
            tp = float(p.get('takeProfit', 0)) if p.get('takeProfit') else 0
            
            # Leverage is stored in position['leverage'] as object {type, value}
            leverage_obj = p.get('leverage', {})
            if isinstance(leverage_obj, dict):
                leverage = float(leverage_obj.get('value', 0))
            else:
                leverage = float(leverage_obj) if leverage_obj else 0
            
            # Fallback: calculate from position value / margin used
            if leverage == 0:
                margin_used = float(p.get('marginUsed', 0))
                if margin_used > 0 and position_value > 0:
                    leverage = position_value / margin_used
            
            # Get local trade metadata if available
            local_trade = local_trades.get(coin, {})
            
            # Calculate SL/TP distances
            sl_distance = abs(entry - local_trade.get('stop_loss', sl)) / entry * 100 if entry > 0 else 0
            tp_prices = local_trade.get('take_profits', [])
            tp_price = tp_prices[0].get('price', tp) if tp_prices else tp
            tp_distance = abs(tp_price - entry) / entry * 100 if entry > 0 and tp_price > 0 else 0
            
            # Build position object with merged data
            position = {
                'id': f'{coin}_LONG' if size > 0 else f'{coin}_SHORT',
                'coin': coin,
                'side': 'LONG' if size > 0 else 'SHORT',
                'size': abs(size),
                'entryPrice': entry,
                'markPrice': mark,
                'stopLoss': local_trade.get('stop_loss', sl),
                'stopLossDistance': round(sl_distance, 2),
                'takeProfit': tp_price,
                'takeProfitDistance': round(tp_distance, 2),
                'unrealizedPnl': pnl,
                'leverage': round(leverage, 1) if leverage > 0 else 0,
                'openedAt': p.get('openedAt', None),
                # Local metadata
                'signalTime': format_time(local_trade.get('signal_time')),
                'orderPlacedTime': format_time(local_trade.get('order_placed_time')),
                'entryTime': format_time(local_trade.get('entry_time')),
                'orderId': local_trade.get('order_id'),
                'slOrderId': local_trade.get('sl_order_id'),
                'tpOrderIds': local_trade.get('tp_order_ids', []),
                'marginRequired': local_trade.get('margin_required'),
                'riskAmount': local_trade.get('risk_amount'),
                'strategy': local_trade.get('strategy'),
            }
            
            positions.append(position)
        
        result['positions'] = positions
    except Exception as e:
        result['error'] = str(e)

# Run fetch in a thread with timeout
thread = threading.Thread(target=fetch_positions)
thread.daemon = True
thread.start()
thread.join(timeout=8)  # 8 second timeout

if thread.is_alive():
    # Timeout - return empty
    print(json.dumps([]))
else:
    if result['error']:
        print(json.dumps([]), file=sys.stderr)
        print(json.dumps([]))
    else:
        print(json.dumps(result['positions'] or []))

sys.stdout.flush()
