#!/usr/bin/env python3
"""
position_monitor.py — Monitor open positions and alert on SL/TP hits
Runs periodically to check position status and send Telegram alerts
"""
import os
import sys
import json
from datetime import datetime

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

from dotenv import load_dotenv
from hyperliquid.info import Info
from hyperliquid.utils import constants
from eth_account import Account

load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

wallet_address = os.getenv('HYPERLIQUID_WALLET')
private_key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

STATE_FILE = r'D:\dev\trading\.position_state.json'

def load_state():
    """Load tracked positions state"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {"positions": {}, "alerts_sent": []}

def save_state(state):
    """Save tracked positions state"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def send_telegram_alert(message):
    """Send alert to Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[X] Telegram credentials not configured")
        return False
    
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"[X] Failed to send Telegram alert: {e}")
        return False

def format_pnl(pnl):
    """Format PnL with indicator"""
    if pnl > 0:
        return f"[+${pnl:.2f}]"
    elif pnl < 0:
        return f"[-${abs(pnl):.2f}]"
    else:
        return f"[$0.00]"

def check_positions():
    """Check open positions and send alerts"""
    print("=" * 60)
    print("POSITION MONITOR")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    info = Info(constants.TESTNET_API_URL, skip_ws=True)
    state = load_state()
    
    try:
        # Get user state (perp positions)
        user_state = info.user_state(wallet_address)
        margin_summary = user_state.get('marginSummary', {})
        account_value = float(margin_summary.get('accountValue', 0))
        
        positions = user_state.get('assetPositions', [])
        open_orders = user_state.get('openOrders', [])
        
        # Get spot balances
        spot_state = info.spot_user_state(wallet_address)
        spot_balances = spot_state.get('balances', [])
        usdc_balance = 0.0
        for bal in spot_balances:
            if bal.get('coin') == 'USDC':
                usdc_balance = float(bal.get('total', 0))
                break
        
        total_value = account_value + usdc_balance
        
        print(f"\nSpot USDC Balance: ${usdc_balance:.2f}")
        print(f"Perp Account Value: ${account_value:.2f}")
        print(f"Total Portfolio: ${total_value:.2f}")
        print(f"Open Positions: {len(positions)}")
        print(f"Open Orders: {len(open_orders)}")
        
        # Track current position IDs
        current_position_ids = set()
        
        for pos_data in positions:
            position = pos_data.get('position', {})
            coin = position.get('coin', 'Unknown')
            size = float(position.get('szi', 0))
            entry_px = float(position.get('entryPx', 0))
            unrealized_pnl = float(position.get('unrealizedPnl', 0))
            
            # Position ID (coin + side)
            pos_id = f"{coin}_{'LONG' if size > 0 else 'SHORT'}"
            current_position_ids.add(pos_id)
            
            # Get current price
            mids = info.all_mids()
            current_px = float(mids.get(coin, 0))
            
            print(f"\n[{coin}]")
            print(f"  Size: {size:.4f}")
            print(f"  Entry: ${entry_px:.2f}")
            print(f"  Current: ${current_px:.2f}")
            print(f"  Unrealized PnL: {format_pnl(unrealized_pnl)}")
            
            # Check if this is a new position
            if pos_id not in state['positions']:
                print(f"  [NEW] Position detected!")
                state['positions'][pos_id] = {
                    'coin': coin,
                    'size': size,
                    'entry_px': entry_px,
                    'detected_at': datetime.now().isoformat(),
                    'alerts_sent': []
                }
                
                # Send new position alert
                side_str = 'LONG' if size > 0 else 'SHORT'
                alert_msg = f"Position Opened: {coin} {side_str}\nSize: {abs(size):.4f} {coin}\nEntry: ${entry_px:.2f}\nCurrent: ${current_px:.2f}\n\nCheck open orders for SL/TP status"
                send_telegram_alert(alert_msg)
            
            # Check for significant PnL changes (>20% or <-20%)
            position_value = abs(size) * entry_px
            if position_value > 0:
                pnl_pct = (unrealized_pnl / position_value) * 100
                
                # Alert on significant moves
                alert_key = f"{pos_id}_pnl_{int(pnl_pct/10)*10}"  # Bucket by 10%
                if alert_key not in state['positions'][pos_id].get('alerts_sent', []):
                    if pnl_pct >= 50 or pnl_pct <= -40:  # Near TP or SL
                        alert_type = "TP Zone" if pnl_pct > 0 else "SL Zone"
                        alert_msg = f"Position Alert: {coin}\nPnL: {unrealized_pnl:+.2f} ({pnl_pct:+.1f}%)\nEntry: ${entry_px:.2f}\nCurrent: ${current_px:.2f}\n\n{alert_type} approaching!"
                        send_telegram_alert(alert_msg)
                        state['positions'][pos_id].setdefault('alerts_sent', []).append(alert_key)
        
        # Check for closed positions
        for pos_id in list(state['positions'].keys()):
            if pos_id not in current_position_ids:
                old_pos = state['positions'][pos_id]
                print(f"\n[CLOSED] {pos_id}")
                
                # Send close alert
                alert_msg = f"Position Closed: {old_pos['coin']}\nWas: {old_pos['size']:.4f} @ ${old_pos['entry_px']:.2f}\n\nPosition no longer active. Check order history for exit details."
                send_telegram_alert(alert_msg)
                del state['positions'][pos_id]
        
        # List open SL/TP orders
        if open_orders:
            print("\n" + "-" * 40)
            print("Open SL/TP Orders:")
            for order in open_orders:
                coin = order.get('coin', 'Unknown')
                side = 'SELL' if order.get('isBuy', True) == False else 'BUY'
                sz = float(order.get('sz', 0))
                limit_px = float(order.get('limitPx', 0))
                trigger_px = float(order.get('triggerPx', 0)) if order.get('triggerPx') else None
                is_trigger = order.get('isTrigger', False)
                reduce_only = order.get('reduceOnly', False)
                
                if reduce_only:
                    order_type = "TP" if not is_trigger else "SL"
                    px_str = f"Trigger: ${trigger_px:.2f}" if trigger_px else f"Limit: ${limit_px:.2f}"
                    print(f"  [{order_type}] {coin} {side} {sz:.4f} @ {px_str}")
        
        save_state(state)
        print("\n[OK] Monitor cycle complete")
        
    except Exception as e:
        print(f"\n[X] Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_positions()
