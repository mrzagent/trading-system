#!/usr/bin/env python3
"""
generate_trading_report.py — Generate trading report for Telegram
"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, r'D:\dev\trading')
os.chdir(r'D:\dev\trading')

REPORT_FILE = r'D:\dev\trading\.latest_report.txt'
COINS = ['BTC', 'ETH', 'SOL']

def get_latest_prices():
    """Get latest prices from database"""
    from db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    
    prices = {}
    for coin in COINS:
        cur.execute("""
            SELECT price FROM trading_prices 
            WHERE coin = %s 
            ORDER BY captured_at DESC 
            LIMIT 1
        """, (coin,))
        row = cur.fetchone()
        prices[coin] = row[0] if row else 0
    
    conn.close()
    return prices

def get_latest_signals():
    """Get latest signals from database - best signal per coin"""
    from db import get_conn
    conn = get_conn()
    cur = conn.cursor()
    
    signals = {}
    since = datetime.now() - timedelta(minutes=60)
    
    for coin in COINS:
        # Get the best signal (highest confidence) from last hour
        cur.execute("""
            SELECT action, confidence, strategy
            FROM trading_signals
            WHERE coin = %s AND strategy != 'quorum_view' 
              AND created_at > %s
            ORDER BY confidence DESC, created_at DESC
            LIMIT 1
        """, (coin, since))
        
        row = cur.fetchone()
        if row:
            signals[coin] = {'action': row[0], 'confidence': row[1], 'strategy': row[2]}
        else:
            signals[coin] = None
    
    conn.close()
    return signals

def get_open_positions():
    """Get open positions from trade executor with real-time PnL"""
    from trade_executor import TradeExecutor, RiskConfig
    from hyperliquid.info import Info
    import os
    
    # Load environment settings
    from signal_integrator import load_account_settings
    settings = load_account_settings()
    env = settings.get('environment', 'testnet')
    env_config = settings.get(env, {})
    base_url = env_config.get('apiUrl', 'https://api.hyperliquid-testnet.xyz')
    
    executor = TradeExecutor(RiskConfig())
    positions = []
    
    # Get current prices from HyperLiquid
    try:
        info = Info(base_url, skip_ws=True)
        all_mids = info.all_mids()
        current_prices = {k: float(v) for k, v in all_mids.items()}
    except:
        current_prices = {}
    
    for symbol, trade in executor.open_trades.items():
        # Calculate real-time PnL
        mark_price = current_prices.get(symbol, trade.entry_price)
        if trade.side == 'LONG':
            pnl = (mark_price - trade.entry_price) * trade.position_size
        else:
            pnl = (trade.entry_price - mark_price) * trade.position_size
        
        positions.append({
            'symbol': symbol,
            'side': trade.side,
            'leverage': trade.leverage,
            'entry': trade.entry_price,
            'mark': mark_price,
            'pnl': pnl
        })
    
    return positions

def generate_report():
    """Generate trading report in the agreed format"""
    prices = get_latest_prices()
    signals = get_latest_signals()
    positions = get_open_positions()
    
    now = datetime.now()
    
    lines = []
    
    # Header
    lines.append(f"TRADING REPORT")
    lines.append(f"{now.strftime('%A, %B %d - %H:%M')} (Bucharest)")
    lines.append("")
    
    # Prices
    for coin in COINS:
        price = prices.get(coin, 0)
        if price >= 1000:
            lines.append(f"{coin} ${price:,.0f}")
        else:
            lines.append(f"{coin} ${price:.2f}")
    
    lines.append("")
    lines.append("Latest Signals (Last Hour)")
    
    for coin in COINS:
        sig = signals.get(coin)
        if sig:
            action = sig['action']
            conf = sig['confidence']
            strategy = sig['strategy']
            if action in ['BUY', 'SELL'] and conf >= 0.5:
                lines.append(f"{coin} | {action} @ {conf:.0%} | {strategy}")
            else:
                lines.append(f"{coin} | {action} @ {conf:.0%} | {strategy}")
        else:
            lines.append(f"{coin} | No Signal")
    
    lines.append("")
    lines.append(f"Open Positions: {len(positions)}")
    
    for pos in positions:
        pnl_str = f"PnL {'+' if pos['pnl'] >= 0 else '-'} ${abs(pos['pnl']):.2f}"
        if pos['entry'] >= 1000:
            entry_str = f"${pos['entry']:,.0f}"
        else:
            entry_str = f"${pos['entry']:.2f}"
        lines.append(f"{pos['symbol']} | {pos['side']} | {pos['leverage']}x | {entry_str} | {pnl_str}")
    
    report = "\n".join(lines)
    
    # Save to file with UTF-8 encoding
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(report)
    print(f"\n[OK] Report saved to {REPORT_FILE}")
    return True

if __name__ == "__main__":
    generate_report()
