from hyperliquid.info import Info

# Check mainnet
info_main = Info(base_url='https://api.hyperliquid.xyz')
main = '0x97c465489243175580fcDe624c2ef640c1897a00'
state = info_main.user_state(main)
balance_main = float(state.get('marginSummary', {}).get('accountValue', 0))
print(f'MAIN on mainnet: ${balance_main:.2f}')

# Check testnet
info_test = Info(base_url='https://api.hyperliquid-testnet.xyz')
state_test = info_test.user_state(main)
balance_test = float(state_test.get('marginSummary', {}).get('accountValue', 0))
print(f'MAIN on testnet: ${balance_test:.2f}')
