import os
from dotenv import load_dotenv

print('Before load_dotenv:')
wallet = os.getenv('HYPERLIQUID_WALLET')
print(f'  HYPERLIQUID_WALLET: {wallet}')

# This is what the scripts do - load from current directory
load_dotenv()

print('After load_dotenv() [from current dir]:')
wallet = os.getenv('HYPERLIQUID_WALLET')
key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
print(f'  HYPERLIQUID_WALLET: {wallet}')
print(f'  HYPERLIQUID_PRIVATE_KEY: {key[:20]}...' if key else '  HYPERLIQUID_PRIVATE_KEY: Not set')
