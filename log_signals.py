import json
import sys
sys.path.insert(0, 'D:/dev/trading')
from db import get_conn

signals = [
  {
    'strategy': 'rsi_mean_reversion',
    'coin': 'BTC',
    'action': 'SELL',
    'confidence': 0.65,
    'reason': 'RSI(15m) 80.6 overbought — 15m only (1h≈53.6)',
    'meta': {
      'rsi_15m': 80.62,
      'rsi_1h': 53.59,
      'price': 62966.0,
      'candle': '2026-06-24T05:40:00+00:00',
      'confluence': '15m only'
    },
    'generated_at': '2026-06-24T05:42:53.482921+00:00'
  },
  {
    'strategy': 'rsi_mean_reversion',
    'coin': 'ETH',
    'action': 'SELL',
    'confidence': 0.85,
    'reason': 'RSI(15m) 79.5 overbought — 1h approaching (1h≈57.6)',
    'meta': {
      'rsi_15m': 79.55,
      'rsi_1h': 57.59,
      'price': 1675.55,
      'candle': '2026-06-24T05:40:00+00:00',
      'confluence': '1h approaching'
    },
    'generated_at': '2026-06-24T05:42:53.485405+00:00'
  },
  {
    'strategy': 'rsi_mean_reversion',
    'coin': 'SOL',
    'action': 'SELL',
    'confidence': 0.65,
    'reason': 'RSI(15m) 92.7 overbought — 15m only (1h≈52.6)',
    'meta': {
      'rsi_15m': 92.73,
      'rsi_1h': 52.57,
      'price': 69.98,
      'candle': '2026-06-24T05:40:00+00:00',
      'confluence': '15m only'
    },
    'generated_at': '2026-06-24T05:42:53.487740+00:00'
  }
]

conn = get_conn()
cursor = conn.cursor()

sql = '''
INSERT INTO trading_signals (strategy, coin, action, confidence, reason, meta, generated_at)
VALUES (%s, %s, %s, %s, %s, %s, %s)
'''

for s in signals:
    cursor.execute(sql, (
        s['strategy'],
        s['coin'],
        s['action'],
        s['confidence'],
        s['reason'],
        json.dumps(s['meta']),
        s['generated_at']
    ))

conn.commit()
conn.close()
print(f'Logged {len(signals)} signals to DB')
