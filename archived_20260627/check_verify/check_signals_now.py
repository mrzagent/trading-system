import json
import urllib.request

# Check latest signals
url = 'http://localhost:3001/api/trading/signals?page=1&limit=20&action=BUY&minConfidence=0.5'
with urllib.request.urlopen(url) as res:
    data = json.loads(res.read().decode())
    print('BUY signals (confidence >= 0.5):')
    for sig in data.get('signals', [])[:5]:
        coin = sig.get('coin')
        action = sig.get('action')
        conf = sig.get('confidence', 0) * 100
        strat = sig.get('strategy')
        created = sig.get('created_at')
        print(f"  {coin} | {action} | {conf:.0f}% | {strat} | {created}")
