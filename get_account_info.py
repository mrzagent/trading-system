#!/usr/bin/env python3
"""Fetch account info from Hyperliquid for dashboard"""
import sys
import os
import json
import threading

sys.path.insert(0, r'D:\dev\trading')

from hyperliquid.info import Info
from dotenv import load_dotenv

load_dotenv(r'C:\Users\mrztms\.openclaw\.env')

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
            'wallet_address': env_config.get('walletAddress', ''),
            'main_wallet': env_config.get('mainWalletAddress', env_config.get('walletAddress', ''))
        }
    except Exception as e:
        print(f"Error loading account settings: {e}", file=sys.stderr)
        return {
            'environment': 'testnet',
            'api_url': 'https://api.hyperliquid-testnet.xyz',
            'wallet_address': '',
            'main_wallet': '0x97c465489243175580fcDe624c2ef640c1897a00'
        }

# Load environment-specific settings
account_settings = load_account_settings()
ENVIRONMENT = account_settings['environment']
BASE_URL = account_settings['api_url']
MAIN_WALLET = account_settings['main_wallet'] or '0x97c465489243175580fcDe624c2ef640c1897a00'
AGENT_WALLET = account_settings['wallet_address'] or os.getenv('HYPERLIQUID_WALLET', '')

print(f"Using {ENVIRONMENT.upper()} environment: {BASE_URL}", file=sys.stderr)
print(f"Main wallet: {MAIN_WALLET}", file=sys.stderr)

result = {'data': None, 'error': None}

def load_risk_config_defaults():
    """Load default leverage/sl/tp from risk_config.json"""
    try:
        with open(r'D:\dev\trading\risk_config.json', 'r') as f:
            rc = json.load(f)
        leverage = rc.get('leverage', 3)
        stop_loss_pct = rc.get('stop_loss_pct', 0.05) * 100  # convert to percentage
        tp_levels = rc.get('take_profit_levels', [])
        take_profit_pct = tp_levels[0]['level'] * 100 if tp_levels else 3.0
        return {
            'leverage': leverage,
            'stopLoss': stop_loss_pct,
            'takeProfit': round(take_profit_pct, 2)
        }
    except Exception:
        return {'leverage': 3, 'stopLoss': 5.0, 'takeProfit': 3.0}

def fetch_account_info():
    try:
        info = Info(base_url=BASE_URL)
        
        # Get account state (perp account)
        state = info.user_state(MAIN_WALLET)
        
        # Get margin summary for totalMargin (totalNtlPos / totalMarginUsed)
        margin_summary = state.get('marginSummary', {})
        total_margin_used = float(margin_summary.get('totalMarginUsed', 0))
        total_ntl_pos = float(margin_summary.get('totalNtlPos', 0))
        
        # Get Total Equity (spot + perp combined) from portfolio endpoint
        # Also extract historical PnL for 24h, 7d, 30d
        account_value = 0.0
        pnl_24h = None
        pnl_7d = None
        pnl_30d = None

        try:
            portfolio = info.post("/info", {"type": "portfolio", "user": MAIN_WALLET})
            # portfolio is a list of [period, data] pairs
            # Available periods: "day", "week", "month", "allTime", "perpDay", "perpWeek", "perpMonth", "perpAllTime"
            for period_name, period_data in portfolio:
                if period_name == "day":
                    history = period_data.get("accountValueHistory", [])
                    pnl_hist = period_data.get("pnlHistory", [])
                    if history:
                        # Last entry is most recent: [timestamp, value]
                        account_value = float(history[-1][1])
                    if pnl_hist and len(pnl_hist) >= 2:
                        # pnlHistory entries: [timestamp, cumulative_pnl]
                        # 24h PnL = most recent - oldest in day period
                        pnl_24h = float(pnl_hist[-1][1]) - float(pnl_hist[0][1])
                
                elif period_name == "week":
                    pnl_hist = period_data.get("pnlHistory", [])
                    if pnl_hist and len(pnl_hist) >= 2:
                        pnl_7d = float(pnl_hist[-1][1]) - float(pnl_hist[0][1])
                
                elif period_name == "month":
                    pnl_hist = period_data.get("pnlHistory", [])
                    if pnl_hist and len(pnl_hist) >= 2:
                        pnl_30d = float(pnl_hist[-1][1]) - float(pnl_hist[0][1])

        except Exception as e:
            pass
        
        # Fallback: perp account value if portfolio call failed
        if account_value == 0.0:
            account_value = float(margin_summary.get('accountValue', 0))
        
        # Calculate deployed capital from positions
        positions = state.get('assetPositions', [])
        deployed = 0
        unrealized_pnl = 0
        position_count = 0
        
        for pos in positions:
            p = pos.get('position', {})
            size = float(p.get('szi', 0))
            if size == 0:
                continue
            entry = float(p.get('entryPx', 0))
            deployed += abs(size) * entry
            position_count += 1
            # Unrealized PnL from position
            pnl = p.get('unrealizedPnl')
            if pnl is not None:
                unrealized_pnl += float(pnl)
        
        # Load risk config defaults first
        defaults = load_risk_config_defaults()
        
        # Override with saved settings if they exist
        settings_path = r'D:\dev\trading\.account_settings.json'
        try:
            with open(settings_path, 'r') as f:
                saved = json.load(f)
                # Only override specific keys if present
                if 'leverage' in saved:
                    defaults['leverage'] = saved['leverage']
                if 'stopLoss' in saved:
                    defaults['stopLoss'] = saved['stopLoss']
                if 'takeProfit' in saved:
                    defaults['takeProfit'] = saved['takeProfit']
        except Exception:
            pass
        
        result['data'] = {
            'balance': account_value,
            'deployedCapital': deployed,
            'available': account_value - total_margin_used,  # Available = Equity - Margin Used
            'positionCount': position_count,
            'unrealizedPnl': unrealized_pnl,
            'totalMargin': total_margin_used,
            'pnl24h': pnl_24h,
            'pnl7d': pnl_7d,
            'pnl30d': pnl_30d,
            'leverage': defaults['leverage'],
            'stopLoss': defaults['stopLoss'],
            'takeProfit': defaults['takeProfit']
        }
        
    except Exception as e:
        result['error'] = str(e)

# Run fetch in a thread with timeout
thread = threading.Thread(target=fetch_account_info)
thread.daemon = True
thread.start()
thread.join(timeout=6)  # 6 second timeout

# Default fallback using risk_config.json values
fallback_defaults = load_risk_config_defaults()
fallback = {
    'balance': 0,
    'deployedCapital': 0,
    'available': 0,
    'positionCount': 0,
    'unrealizedPnl': 0,
    'totalMargin': 0,
    'pnl24h': None,
    'pnl7d': None,
    'pnl30d': None,
    'leverage': fallback_defaults['leverage'],
    'stopLoss': fallback_defaults['stopLoss'],
    'takeProfit': fallback_defaults['takeProfit']
}

if thread.is_alive():
    # Timeout - return defaults
    print(json.dumps(fallback))
else:
    if result['error']:
        print(json.dumps(fallback))
    else:
        print(json.dumps(result['data'] or fallback))

sys.stdout.flush()
