"""Check if dashboard is showing mainnet"""
import requests

MAIN = '0x97c465489243175580fcDe624c2ef640c1897a00'

print("Checking MAIN wallet on MAINNET...")

# Check mainnet
try:
    response = requests.post(
        'https://api.hyperliquid.xyz/info',
        json={"type": "clearinghouseState", "user": MAIN},
        timeout=10
    )
    data = response.json()
    balance = float(data.get('marginSummary', {}).get('accountValue', 0))
    print(f"Mainnet clearinghouse: ${balance:.2f}")
except Exception as e:
    print(f"Error: {e}")

# Check mainnet portfolio
try:
    response = requests.post(
        'https://api.hyperliquid.xyz/info',
        json={"type": "portfolio", "user": MAIN},
        timeout=10
    )
    portfolio = response.json()
    for period_name, period_data in portfolio:
        if period_name == "day":
            history = period_data.get("accountValueHistory", [])
            if history:
                account_value = float(history[-1][1])
                print(f"Mainnet portfolio: ${account_value:.2f}")
except Exception as e:
    print(f"Error: {e}")
