#!/usr/bin/env python3
"""Close a position on Hyperliquid via market order (agent -> vault)"""
import sys
import os
import json
sys.path.insert(0, r'D:\dev\trading')

from dotenv import load_dotenv
from eth_account import Account
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange

load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

# Agent wallet (has private key, places orders)
AGENT_KEY = os.getenv('HYPERLIQUID_PRIVATE_KEY')

# Main/vault wallet (where positions actually are)
MAIN_WALLET = '0x97c465489243175580fcDe624c2ef640c1897a00'

BASE_URL = "https://api.hyperliquid-testnet.xyz"

def close_position(coin):
    """Close position for given coin on main wallet using agent key"""
    # Create account from agent key
    account = Account.from_key(AGENT_KEY)
    
    # Initialize SDK with vault_address for delegation
    info = Info(base_url=BASE_URL)
    exchange = Exchange(
        wallet=account, 
        base_url=BASE_URL,
        vault_address=MAIN_WALLET  # Trade on behalf of main wallet
    )
    
    # Get positions from main wallet
    state = info.user_state(MAIN_WALLET)
    positions = state.get('assetPositions', [])
    
    # Find target position
    target = None
    for pos in positions:
        p = pos.get('position', {})
        if p.get('coin') == coin:
            target = p
            break
    
    if not target:
        return {'success': False, 'error': f'No position found for {coin}'}
    
    size = float(target.get('szi', 0))
    
    print(f"Closing {coin}: size={size}", file=sys.stderr)
    
    try:
        # Use SDK's market_close with position size
        result = exchange.market_close(coin, sz=abs(size))
        print(f"market_close result: {result}", file=sys.stderr)
        
        if result.get('status') == 'ok':
            statuses = result.get('response', {}).get('data', {}).get('statuses', [])
            if statuses and 'filled' in statuses[0]:
                return {
                    'success': True, 
                    'tx': statuses[0].get('filled', {}).get('oid', 'unknown'),
                    'pnl': float(target.get('unrealizedPnl', 0))
                }
            elif statuses and 'error' in statuses[0]:
                return {'success': False, 'error': statuses[0]['error']}
            else:
                return {'success': True, 'tx': 'pending'}
        else:
            return {'success': False, 'error': str(result)}
    except Exception as e:
        import traceback
        traceback.print_exc(file=sys.stderr)
        return {'success': False, 'error': str(e)}

# Main
if len(sys.argv) < 2:
    print(json.dumps({'success': False, 'error': 'Usage: close_position.py <coin>'}))
    sys.exit(1)

coin = sys.argv[1]
result = close_position(coin)
print(json.dumps(result))
