"""Check if agent wallet is authorized as delegate"""
from hyperliquid.info import Info

info = Info(base_url='https://api.hyperliquid-testnet.xyz')

MAIN = '0x97c465489243175580fcDe624c2ef640c1897a00'
AGENT = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'

print("Checking delegation...")
print(f"Main: {MAIN}")
print(f"Agent: {AGENT}")

# Check if agent is in main's delegations
try:
    # Get user's vaults/delegates
    result = info.post("/info", {"type": "delegations", "user": MAIN})
    print(f"\nDelegations for MAIN: {result}")
except Exception as e:
    print(f"Error: {e}")

# Check agent's authority
try:
    result = info.post("/info", {"type": "delegations", "user": AGENT})
    print(f"\nDelegations for AGENT: {result}")
except Exception as e:
    print(f"Error: {e}")
