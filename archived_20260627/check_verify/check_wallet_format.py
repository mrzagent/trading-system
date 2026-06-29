"""Check wallet address formats"""
from eth_account import Account

MAIN = '0x97c465489243175580fcDe624c2ef640c1897a00'
AGENT = '0x89823A4f85cc8ef3A5574E8a56741A7b4562f288'

print("MAIN wallet:")
print(f"  Original: {MAIN}")
print(f"  Lower: {MAIN.lower()}")
print(f"  Checksum: {Account.from_key('0x' + '00'*32).address}")  # Dummy to get checksum format

# Get checksum for MAIN
try:
    # Can't create from address only, but we can check format
    print(f"  Is checksummed: {MAIN != MAIN.lower()}")
except:
    pass

print("\nAGENT wallet:")
print(f"  Original: {AGENT}")
print(f"  Lower: {AGENT.lower()}")
print(f"  Is checksummed: {AGENT != AGENT.lower()}")

# The issue might be that we need to use the checksummed address
# Let's try with lowercase
print("\n--- Testing lowercase addresses ---")
import os
import sys
sys.path.insert(0, r'D:\dev\trading')

from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/.openclaw/.env'))

from trade_executor import TradeExecutor, RiskConfig

# Test with lowercase main wallet
executor = TradeExecutor(RiskConfig())
executor.client.MAIN_WALLET = MAIN.lower()

print(f"Using lowercase MAIN: {executor.client.MAIN_WALLET}")
