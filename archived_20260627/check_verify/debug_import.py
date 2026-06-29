import sys
print("Python:", sys.executable)
print("Path:", sys.path[:2])

try:
    from eth_account import Account
    from eth_account.messages import encode_defunct
    print("eth_account imported OK")
    print("Account:", Account)
except ImportError as e:
    print("Import failed:", e)

# Now check what trade_executor sees
import trade_executor
print("trade_executor.ETH_ACCOUNT_AVAILABLE:", trade_executor.ETH_ACCOUNT_AVAILABLE)
