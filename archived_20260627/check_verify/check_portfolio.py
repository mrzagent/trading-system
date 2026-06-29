"""Check balance using portfolio endpoint like dashboard"""
import requests
import json

MAIN = '0x97c465489243175580fcDe624c2ef640c1897a00'

print("Checking MAIN wallet using portfolio endpoint...")

try:
    response = requests.post(
        'https://api.hyperliquid-testnet.xyz/info',
        json={"type": "portfolio", "user": MAIN},
        timeout=10
    )
    portfolio = response.json()
    
    print(f"\nPortfolio data type: {type(portfolio)}")
    
    # portfolio is a list of [period, data] pairs
    for period_name, period_data in portfolio:
        print(f"\nPeriod: {period_name}")
        if period_name == "day":
            history = period_data.get("accountValueHistory", [])
            if history:
                # Last entry is most recent: [timestamp, value]
                account_value = float(history[-1][1])
                print(f"  Account Value: ${account_value:.2f}")
            else:
                print("  No accountValueHistory")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
