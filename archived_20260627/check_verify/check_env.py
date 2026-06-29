import os
from dotenv import load_dotenv
load_dotenv(os.path.expanduser('~/.openclaw/.env'))

print('Current env:')
wallet = os.getenv('HYPERLIQUID_WALLET')
key = os.getenv('HYPERLIQUID_PRIVATE_KEY')
print(f'  WALLET: {wallet}')
print(f'  KEY: {key[:30]}...' if key else '  KEY: None')
