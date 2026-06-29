#!/usr/bin/env python3
"""
backtest_momentum.py — Backtest the Momentum Trend Following strategy

Configuration:
- Portfolio: $1,000 starting balance
- Leverage: 3x (configurable)
- Timeframe: Simulated 4-hour candles from 5min data
- Fee: 0.1% per trade (simulated)

Output:
- Per-token breakdown: entries, exits, P&L
- Overall portfolio performance
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, r"D:\dev\trading")
from db import get_conn, COINS


# --- Configuration ---
INITIAL_BALANCE = 1000.0
LEVERAGE = 3.0
TRADING_FEE_PCT = 0.001  # 0.1% per trade
PORTFOLIO_PCT = 0.02     # 2% of portfolio per trade
STOP_LOSS_PCT = 0.10     # 10% stop loss
TAKE_PROFIT_PCT = 0.15   # 15% take profit
# Momentum thresholds
MOM_BUY = 0.1      # 0.1% momentum threshold for LONG entries
MOM_SELL = -0.1    # 0.1% momentum threshold for SHORT entries
CHANGE_BUY = 0.1   # 0.1% 24h change requirement
CHANGE_SELL = -0.1
CROSSOVER_WINDOW = 12
FETCH_LIMIT = 300
CANDLE_MINUTES = 60  # 1 hour candles


@dataclass
class Trade:
    coin: str
    direction: str  # "LONG" or "SHORT"
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    pnl_pct: float
    pnl_usd: float
    

@dataclass
class TokenResult:
    coin: str
    entries: int = 0
    exits: int = 0
    trades: list = field(default_factory=list)
    total_pnl_usd: float = 0.0
    
    @property
    def winning_trades(self):
        return sum(1 for t in self.trades if t.pnl_usd > 0)
    
    @property
    def losing_trades(self):
        return sum(1 for t in self.trades if t.pnl_usd <= 0)


def detect_crossover(moms: list[float]) -> Optional[str]:
    """Detect if momentum recently crossed zero."""
    if len(moms) < 3:
        return None
    if moms[-1] > 0 and any(m < 0 for m in moms[:-2]):
        return "bullish_cross"
    if moms[-1] < 0 and any(m > 0 for m in moms[:-2]):
        return "bearish_cross"
    return None


def fetch_all_5min_data(conn, coin: str):
    """Fetch all 5min data for a coin, ordered chronologically."""
    sql = """
        SELECT coin, price, captured_at, volume_24h, change_24h, momentum
        FROM trading_prices
        WHERE coin = %s
        ORDER BY captured_at ASC
    """
    with conn.cursor() as cur:
        cur.execute(sql, (coin,))
        columns = [desc[0] for desc in cur.description]
        rows = []
        for row in cur.fetchall():
            rows.append(dict(zip(columns, row)))
    return rows


def group_into_candles(rows: list[dict], minutes: int = 240):
    """Group 5min rows into larger candles (default 4h = 48 rows)."""
    rows_per_candle = minutes // 5  # 5min intervals
    candles = []
    
    for i in range(0, len(rows), rows_per_candle):
        chunk = rows[i:i + rows_per_candle]
        if len(chunk) < rows_per_candle * 0.8:  # Skip incomplete candles
            continue
            
        candle = {
            "coin": chunk[0]["coin"],
            "open": chunk[0]["price"],
            "high": max(r["price"] for r in chunk),
            "low": min(r["price"] for r in chunk),
            "close": chunk[-1]["price"],
            "volume": sum(r.get("volume_24h", 0) or 0 for r in chunk) / len(chunk),
            "momentum": chunk[-1].get("momentum", 0),
            "change_24h": chunk[-1].get("change_24h", 0),
            "captured_at": chunk[-1]["captured_at"],
            "context_rows": chunk  # Keep for crossover detection
        }
        candles.append(candle)
    
    return candles


def analyse_candle(candle: dict) -> dict:
    """Analyze a single candle for backtesting — returns signal dict."""
    momentum = float(candle.get("momentum") or 0)
    change = float(candle.get("change_24h") or 0)
    price = float(candle.get("close", 0) or 0)
    
    # Get momentum history for crossover detection
    context = candle.get("context_rows", [])
    moms = [float(r.get("momentum") or 0) for r in context[-CROSSOVER_WINDOW:]]
    crossover = detect_crossover(moms)
    
    bull_bonus = 0.2 if crossover == "bullish_cross" else 0.0
    bear_bonus = 0.2 if crossover == "bearish_cross" else 0.0
    
    if momentum >= MOM_BUY and change >= CHANGE_BUY:
        conf = min(momentum / 10 * 0.6 + change / 10 * 0.2 + bull_bonus, 1.0)
        return {
            "action": "BUY",
            "confidence": conf,
            "price": price,
            "momentum": momentum,
            "change_24h": change,
            "crossover": crossover
        }
    
    if momentum <= MOM_SELL and change <= CHANGE_SELL:
        conf = min(abs(momentum) / 10 * 0.6 + abs(change) / 10 * 0.2 + bear_bonus, 1.0)
        return {
            "action": "SELL",
            "confidence": conf,
            "price": price,
            "momentum": momentum,
            "change_24h": change,
            "crossover": crossover
        }
    
    return {"action": "HOLD", "reason": "no signal"}


def run_backtest():
    conn = get_conn()
    
    print("=" * 70)
    print("MOMENTUM TREND FOLLOWING — BACKTEST RESULTS")
    print("=" * 70)
    print(f"Portfolio: ${INITIAL_BALANCE:,.2f}")
    print(f"Position Size: {PORTFOLIO_PCT*100:.0f}% of portfolio")
    print(f"Leverage: {LEVERAGE}x")
    print(f"Stop Loss: {STOP_LOSS_PCT*100:.0f}%")
    print(f"Take Profit: {TAKE_PROFIT_PCT*100:.0f}%")
    print(f"Trading Fee: {TRADING_FEE_PCT*100:.2f}% per trade")
    print(f"Candle Size: {CANDLE_MINUTES} minutes (1 hour)")
    print(f"Momentum Threshold: {MOM_BUY}%")
    print("-" * 70)
    
    token_results = {coin: TokenResult(coin=coin) for coin in COINS}
    
    balance = INITIAL_BALANCE
    all_trades = []
    
    # Get date range from data
    with conn.cursor() as cur:
        cur.execute("SELECT MIN(captured_at), MAX(captured_at) FROM trading_prices")
        min_date, max_date = cur.fetchone()
    
    print(f"\nData Range: {min_date.date()} to {max_date.date()}")
    print(f"Coins: {', '.join(COINS)}")
    print()
    
    # Process each coin independently
    for coin in COINS:
        print(f"Processing {coin}...", end=" ", flush=True)
        
        # Fetch 5min data for this coin
        rows = fetch_all_5min_data(conn, coin)
        if len(rows) < 100:
            print(f"insufficient data ({len(rows)} rows)")
            continue
        
        # Group into 4h candles
        candles = group_into_candles(rows, CANDLE_MINUTES)
        if len(candles) < 5:
            print(f"insufficient candles ({len(candles)} candles)")
            continue
        
        position = None  # Current position for this coin
        
        for i, candle in enumerate(candles):
            price = float(candle["close"])
            captured_at = candle["captured_at"]
            momentum = float(candle.get("momentum") or 0)
            
            # Analyze this candle
            signal = analyse_candle(candle)
            
            # Check for entry signals (only if no position)
            if signal["action"] == "BUY" and position is None:
                position_size = (balance * PORTFOLIO_PCT) * LEVERAGE
                entry_fee = position_size * TRADING_FEE_PCT
                
                position = {
                    "entry_price": price,
                    "size": position_size,
                    "entry_time": captured_at,
                    "direction": "LONG",
                    "entry_candle_idx": i,
                    "sl_price": price * (1 - STOP_LOSS_PCT),
                    "tp_price": price * (1 + TAKE_PROFIT_PCT)
                }
                token_results[coin].entries += 1
                balance -= entry_fee
                
            elif signal["action"] == "SELL" and position is None:
                position_size = (balance * PORTFOLIO_PCT) * LEVERAGE
                entry_fee = position_size * TRADING_FEE_PCT
                
                position = {
                    "entry_price": price,
                    "size": position_size,
                    "entry_time": captured_at,
                    "direction": "SHORT",
                    "entry_candle_idx": i,
                    "sl_price": price * (1 + STOP_LOSS_PCT),
                    "tp_price": price * (1 - TAKE_PROFIT_PCT)
                }
                token_results[coin].entries += 1
                balance -= entry_fee
            
            # Check for SL/TP exits first, then signal-based exits
            elif position is not None:
                should_exit = False
                exit_reason = None
                
                if position["direction"] == "LONG":
                    if price <= position["sl_price"]:
                        should_exit = True
                        exit_reason = "SL"
                        exit_price = position["sl_price"]
                        pnl_pct = ((exit_price - position["entry_price"]) / position["entry_price"]) * LEVERAGE
                    elif price >= position["tp_price"]:
                        should_exit = True
                        exit_reason = "TP"
                        exit_price = position["tp_price"]
                        pnl_pct = ((exit_price - position["entry_price"]) / position["entry_price"]) * LEVERAGE
                    elif signal["action"] == "SELL":
                        should_exit = True
                        exit_reason = "SIGNAL"
                        exit_price = price
                        pnl_pct = ((exit_price - position["entry_price"]) / position["entry_price"]) * LEVERAGE
                else:  # SHORT
                    if price >= position["sl_price"]:
                        should_exit = True
                        exit_reason = "SL"
                        exit_price = position["sl_price"]
                        pnl_pct = ((position["entry_price"] - exit_price) / position["entry_price"]) * LEVERAGE
                    elif price <= position["tp_price"]:
                        should_exit = True
                        exit_reason = "TP"
                        exit_price = position["tp_price"]
                        pnl_pct = ((position["entry_price"] - exit_price) / position["entry_price"]) * LEVERAGE
                    elif signal["action"] == "BUY":
                        should_exit = True
                        exit_reason = "SIGNAL"
                        exit_price = price
                        pnl_pct = ((position["entry_price"] - exit_price) / position["entry_price"]) * LEVERAGE
                
                if should_exit:
                    pnl_usd = position["size"] * pnl_pct
                    exit_fee = position["size"] * TRADING_FEE_PCT
                    
                    trade = Trade(
                        coin=coin,
                        direction=position["direction"],
                        entry_price=position["entry_price"],
                        exit_price=exit_price,
                        entry_time=position["entry_time"],
                        exit_time=captured_at,
                        pnl_pct=pnl_pct * 100,
                        pnl_usd=pnl_usd
                    )
                    
                    token_results[coin].trades.append(trade)
                    token_results[coin].exits += 1
                    token_results[coin].total_pnl_usd += pnl_usd
                    all_trades.append(trade)
                    
                    balance += pnl_usd - exit_fee
                    position = None
        
        print(f"done ({len(token_results[coin].trades)} trades)")
    
    conn.close()
    
    # --- Results Summary ---
    print("\n" + "=" * 70)
    print("PER-TOKEN BREAKDOWN")
    print("=" * 70)
    
    for coin in COINS:
        result = token_results[coin]
        print(f"\n{coin}:")
        print(f"  Entries:  {result.entries}")
        print(f"  Exits:    {result.exits}")
        print(f"  Trades:   {len(result.trades)}")
        print(f"  Wins:     {result.winning_trades}")
        print(f"  Losses:   {result.losing_trades}")
        print(f"  P&L:      ${result.total_pnl_usd:,.2f}")
        
        if result.trades:
            avg_pnl = sum(t.pnl_pct for t in result.trades) / len(result.trades)
            print(f"  Avg P&L%: {avg_pnl:+.2f}%")
            best = max(result.trades, key=lambda t: t.pnl_usd)
            worst = min(result.trades, key=lambda t: t.pnl_usd)
            print(f"  Best:     +${best.pnl_usd:,.2f} ({best.pnl_pct:+.2f}%) on {best.entry_time.date()}")
            print(f"  Worst:    ${worst.pnl_usd:,.2f} ({worst.pnl_pct:+.2f}%) on {worst.entry_time.date()}")
    
    # --- Portfolio Summary ---
    print("\n" + "=" * 70)
    print("PORTFOLIO SUMMARY")
    print("=" * 70)
    print(f"Starting Balance: ${INITIAL_BALANCE:,.2f}")
    print(f"Ending Balance:   ${balance:,.2f}")
    print(f"Total P&L:        ${balance - INITIAL_BALANCE:,.2f} ({((balance/INITIAL_BALANCE)-1)*100:+.2f}%)")
    print(f"Total Trades:     {len(all_trades)}")
    
    if all_trades:
        win_rate = sum(1 for t in all_trades if t.pnl_usd > 0) / len(all_trades) * 100
        print(f"Win Rate:         {win_rate:.1f}%")
        
        # Calculate max drawdown
        running_pnl = 0
        peak = 0
        max_dd = 0
        for trade in sorted(all_trades, key=lambda t: t.exit_time):
            running_pnl += trade.pnl_usd
            if running_pnl > peak:
                peak = running_pnl
            dd = peak - running_pnl
            if dd > max_dd:
                max_dd = dd
        print(f"Max Drawdown:     ${max_dd:,.2f}")
    
    print("\n" + "=" * 70)
    
    # --- Trade Log ---
    if all_trades:
        print("\nTRADE LOG:")
        print("-" * 70)
        for trade in sorted(all_trades, key=lambda t: t.exit_time):
            status = "WIN" if trade.pnl_usd > 0 else "LOSS"
            print(f"{status} {trade.coin} {trade.direction:5} | Entry: ${trade.entry_price:,.2f} | Exit: ${trade.exit_price:,.2f} | P&L: ${trade.pnl_usd:+,.2f} ({trade.pnl_pct:+.2f}%) | {trade.entry_time.date()}")


if __name__ == "__main__":
    run_backtest()
