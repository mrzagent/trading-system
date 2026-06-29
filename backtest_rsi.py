"""
RSI Strategy Backtest — Dual-timeframe RSI with confluence scoring
"""
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import psycopg2
from psycopg2.extras import RealDictCursor


@dataclass
class Trade:
    entry_date: str = ""
    exit_date: Optional[str] = None
    symbol: str = ""
    direction: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    position_size: float = 0.0
    position_value: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""
    confidence: float = 0.0


@dataclass
class BacktestResult:
    start_date: str = ""
    end_date: str = ""
    initial_capital: float = 1000.0
    final_capital: float = 1000.0
    total_return_pct: float = 0.0
    total_pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    trades: List[Dict] = field(default_factory=list)


COINS = ["BTC", "ETH", "SOL"]
RISK_PER_TRADE = 0.02
STOP_LOSS_PCT = 0.05
TAKE_PROFIT_PCT = 0.10
COMMISSION = 0.001
SLIPPAGE = 0.0005
MAX_BARS = 20
MIN_CONFIDENCE = 0.70

# RSI thresholds (from strategy_rsi.py)
RSI_15M_OVERSOLD = 35
RSI_15M_OVERBOUGHT = 65
RSI_1H_OVERSOLD = 40
RSI_1H_OVERBOUGHT = 60


def get_conn():
    return psycopg2.connect(
        host="localhost",
        database="postgres",
        user="postgres",
        password="1870506303979"
    )


def fetch_hourly_data(conn, coin: str, start: datetime, end: datetime) -> List[dict]:
    """Fetch hourly OHLC data for RSI calculation"""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT captured_at, price, rsi, change_24h, volume_24h
        FROM trading_prices
        WHERE coin = %s AND captured_at BETWEEN %s AND %s
        ORDER BY captured_at
    """, (coin, start, end))
    return [dict(r) for r in cur.fetchall()]


def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate RSI from price series"""
    if len(prices) < period + 1:
        return 50.0
    
    gains = []
    losses = []
    
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    
    if len(gains) < period:
        return 50.0
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def confluence_score(rsi_15m: float, rsi_1h: float) -> tuple:
    """
    Returns (action, confidence) based on dual-timeframe RSI confluence.
    Mirrors strategy_rsi.py logic exactly.
    """
    # Score breakdown (from strategy_rsi.py)
    score_15m_buy  = max(0, (RSI_15M_OVERSOLD - rsi_15m) / RSI_15M_OVERSOLD)
    score_15m_sell = max(0, (rsi_15m - RSI_15M_OVERBOUGHT) / (100 - RSI_15M_OVERBOUGHT))
    score_1h_buy   = max(0, (RSI_1H_OVERSOLD - rsi_1h) / RSI_1H_OVERSOLD) * 0.3
    score_1h_sell  = max(0, (rsi_1h - RSI_1H_OVERBOUGHT) / (100 - RSI_1H_OVERBOUGHT)) * 0.3

    buy_score  = score_15m_buy + score_1h_buy
    sell_score = score_15m_sell + score_15m_sell

    if buy_score > sell_score and buy_score >= 0.7:
        return "BUY", min(buy_score, 1.0)
    elif sell_score > buy_score and sell_score >= 0.7:
        return "SELL", min(sell_score, 1.0)
    else:
        return "HOLD", max(buy_score, sell_score)


def run_backtest():
    start_date = datetime(2026, 3, 27)
    end_date = datetime.now()
    
    result = BacktestResult(
        start_date=start_date.strftime("%Y-%m-%d"),
        end_date=end_date.strftime("%Y-%m-%d"),
        initial_capital=1000.0
    )
    
    capital = 1000.0
    trades = []
    peak_capital = capital
    max_drawdown = 0.0
    open_positions = {}
    
    conn = get_conn()
    
    for coin in COINS:
        print(f"Processing {coin.upper()}...")
        rows = fetch_hourly_data(conn, coin, start_date, end_date)
        
        if len(rows) < 20:
            print(f"  Insufficient data ({len(rows)} rows)")
            continue
        
        # Simulate hourly analysis
        for i in range(20, len(rows)):
            current = rows[i]
            price = float(current['price'])
            timestamp = current['captured_at']
            
            # Skip if position already open
            if coin in open_positions:
                continue
            
            # Get price window for RSI calculation
            price_window = [float(r['price']) for r in rows[max(0, i-20):i+1]]
            
            # Calculate dual-timeframe RSI
            rsi_15m = calculate_rsi(price_window[-15:], period=14) if len(price_window) >= 15 else 50.0
            rsi_1h = calculate_rsi(price_window, period=14) if len(price_window) >= 14 else 50.0
            
            # Get confluence signal
            action, confidence = confluence_score(rsi_15m, rsi_1h)
            
            if action == "HOLD" or confidence < MIN_CONFIDENCE:
                continue
            
            # Calculate position
            direction = "long" if action == "BUY" else "short"
            risk_amount = capital * RISK_PER_TRADE
            
            if direction == "long":
                stop_loss = price * (1 - STOP_LOSS_PCT)
                take_profit = price * (1 + TAKE_PROFIT_PCT)
            else:
                stop_loss = price * (1 + STOP_LOSS_PCT)
                take_profit = price * (1 - TAKE_PROFIT_PCT)
            
            risk_per_unit = abs(price - stop_loss)
            if risk_per_unit <= 0:
                continue
            
            position_size = (risk_amount / risk_per_unit)
            position_value = position_size * price
            max_position = capital * 0.50
            
            if position_value > max_position:
                position_value = max_position
                position_size = position_value / price
            
            # Apply slippage
            if direction == "long":
                entry_price = price * (1 + SLIPPAGE)
            else:
                entry_price = price * (1 - SLIPPAGE)
            
            entry_commission = position_value * COMMISSION
            capital -= entry_commission
            
            # Simulate trade exit
            exit_price = entry_price
            exit_reason = ""
            bars_held = 0
            
            for j in range(i + 1, min(i + MAX_BARS + 1, len(rows))):
                future_price = float(rows[j]['price'])
                bars_held += 1
                
                if direction == "long":
                    if future_price <= stop_loss:
                        exit_price = stop_loss
                        exit_reason = "stop_loss"
                        break
                    elif future_price >= take_profit:
                        exit_price = take_profit
                        exit_reason = "take_profit"
                        break
                else:
                    if future_price >= stop_loss:
                        exit_price = stop_loss
                        exit_reason = "stop_loss"
                        break
                    elif future_price <= take_profit:
                        exit_price = take_profit
                        exit_reason = "take_profit"
                        break
                
                if bars_held >= MAX_BARS:
                    exit_price = future_price
                    exit_reason = "max_bars"
                    break
                
                exit_price = future_price
                exit_reason = "end_of_data"
            
            # Apply exit slippage
            if direction == "long":
                exit_price = exit_price * (1 - SLIPPAGE)
            else:
                exit_price = exit_price * (1 + SLIPPAGE)
            
            # Calculate P&L
            if direction == "long":
                gross_pnl = (exit_price - entry_price) * position_size
            else:
                gross_pnl = (entry_price - exit_price) * position_size
            
            exit_value = position_size * exit_price
            exit_commission = exit_value * COMMISSION
            pnl = gross_pnl - exit_commission
            
            capital += pnl
            
            if capital > peak_capital:
                peak_capital = capital
            drawdown = (peak_capital - capital) / peak_capital
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            
            trade = Trade(
                entry_date=str(timestamp),
                exit_date=str(rows[min(i + bars_held, len(rows) - 1)]['captured_at']),
                symbol=coin.upper(),
                direction=direction,
                entry_price=entry_price,
                exit_price=exit_price,
                position_size=position_size,
                position_value=position_value,
                stop_loss=stop_loss,
                take_profit=take_profit,
                pnl=pnl,
                pnl_pct=(pnl / position_value) * 100 if position_value > 0 else 0,
                exit_reason=exit_reason,
                confidence=confidence
            )
            trades.append(trade)
    
    conn.close()
    
    # Calculate stats
    if trades:
        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl <= 0]
        
        result.final_capital = capital
        result.total_return_pct = ((capital - 1000) / 1000) * 100
        result.total_pnl = sum(t.pnl for t in trades)
        result.total_trades = len(trades)
        result.winning_trades = len(winning)
        result.losing_trades = len(losing)
        result.win_rate = (len(winning) / len(trades)) * 100
        result.avg_win = sum(t.pnl for t in winning) / len(winning) if winning else 0
        result.avg_loss = sum(t.pnl for t in losing) / len(losing) if losing else 0
        
        gross_profit = sum(t.pnl for t in winning) if winning else 0
        gross_loss = abs(sum(t.pnl for t in losing)) if losing else 1
        result.profit_factor = gross_profit / gross_loss
        result.max_drawdown_pct = max_drawdown * 100
        result.trades = [asdict(t) for t in trades]
    
    return result


def print_summary(result: BacktestResult):
    print("\n" + "="*60)
    print("RSI STRATEGY BACKTEST RESULTS")
    print("="*60)
    print(f"Period: {result.start_date} to {result.end_date}")
    print(f"\nPortfolio Performance:")
    print(f"  Initial Capital: ${result.initial_capital:,.2f}")
    print(f"  Final Capital:   ${result.final_capital:,.2f}")
    print(f"  Total P&L:       ${result.total_pnl:,.2f}")
    print(f"  Total Return:    {result.total_return_pct:+.2f}%")
    print(f"\nTrade Statistics:")
    print(f"  Total Trades:    {result.total_trades}")
    print(f"  Win Rate:        {result.win_rate:.1f}%")
    print(f"  Winning Trades:  {result.winning_trades}")
    print(f"  Losing Trades:   {result.losing_trades}")
    print(f"  Avg Win:         ${result.avg_win:,.2f}")
    print(f"  Avg Loss:        ${result.avg_loss:,.2f}")
    print(f"  Profit Factor:   {result.profit_factor:.2f}")
    print(f"\nRisk Metrics:")
    print(f"  Max Drawdown:    {result.max_drawdown_pct:.2f}%")
    print("="*60)
    
    # Per-coin breakdown
    print("\nPer-Coin Breakdown:")
    coin_stats = {}
    for t in result.trades:
        coin = t['symbol']
        if coin not in coin_stats:
            coin_stats[coin] = {'trades': 0, 'pnl': 0, 'wins': 0}
        coin_stats[coin]['trades'] += 1
        coin_stats[coin]['pnl'] += t['pnl']
        if t['pnl'] > 0:
            coin_stats[coin]['wins'] += 1
    
    for coin, stats in sorted(coin_stats.items(), key=lambda x: -x[1]['pnl']):
        wr = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
        print(f"  {coin:>4}: {stats['trades']:>2} trades | ${stats['pnl']:>+8.2f} | {wr:.0f}% WR")


if __name__ == "__main__":
    result = run_backtest()
    print_summary(result)
