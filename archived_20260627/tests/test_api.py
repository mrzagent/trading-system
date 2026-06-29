import os
import urllib.request
import json

BASE = 'https://pro-api.coingecko.com/api/v3'
COINGECKO_API_KEY = os.environ.get('COINGECKO_API_KEY', '')

ids = 'bitcoin,ethereum,solana'
url = f'{BASE}/simple/price?ids={ids}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true&include_market_cap=true'

headers = {'User-Agent': 'Mozilla/5.0'}
if COINGECKO_API_KEY:
    headers['x-cg-pro-api-key'] = COINGECKO_API_KEY

req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
        print('CoinGecko Response:')
        print(json.dumps(data, indent=2))
        
        print('\nExtracting prices:')
        for coin_id in ['bitcoin', 'ethereum', 'solana']:
            d = data.get(coin_id, {})
            print(f'  {coin_id}:')
            print(f"    usd: {d.get('usd')}")
            print(f"    usd_24h_change: {d.get('usd_24h_change')}")
except Exception as e:
    print(f'Error: {e}')
