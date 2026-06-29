import sys
sys.path.insert(0, r'D:\dev\trading')

# Test imports
from trade_executor import TradeExecutor, ETH_ACCOUNT_AVAILABLE
from signal_integrator import SignalIntegrator

print(f"eth-account available: {ETH_ACCOUNT_AVAILABLE}")

# Test wallet loading
import os
from dotenv import load_dotenv
openclaw_env_path = os.path.expanduser('~/.openclaw/.env')
if os.path.exists(openclaw_env_path):
    load_dotenv(openclaw_env_path)

wallet = os.getenv('HYPERLIQUID_WALLET')
print(f"Wallet configured: {wallet is not None}")
if wallet:
    print(f"Wallet: {wallet[:20]}...")

# Test integrator initialization
integrator = SignalIntegrator(test_mode=False)
print(f"Integrator test_mode: {integrator.test_mode}")
print(f"Executor test_mode: {integrator.executor.test_mode if hasattr(integrator.executor, 'test_mode') else 'N/A'}")

print("\nLive trading should work on next cron run!")
