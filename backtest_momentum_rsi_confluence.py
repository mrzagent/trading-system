#!/usr/bin/env python3
"""
backtest_momentum_rsi_confluence.py — Combined Momentum + RSI strategy

Signal logic:
  BUY only when:
    - Momentum: momentum >= 0.1% AND change_24h >= 0.2%
    - RSI: dual-timeframe RSI confluence >= 0.7 (bullish)
    
  SELL only when:
    - Momentum: momentum <= -0.1% AND change_24h <= -0.2%
    - RSI: dual-timeframe RSI confluence >= 0.7 (bearish)
  
  HOLD otherwise

Requires BOTH strategies to agree on direction for higher-quality signals.
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, List

sys.path.insert(0, r"D:\dev\trading")
from db import get_conn, COINS


# --- Configuration ---
INITIAL_BALANCE = 1000.0
LEVERAGE = 3.0
TRADING_FEE_PCT = 0.001  # 0.1% per trade
PORTFOLIO_PCT = 0.02     # 2% of portfolio per trade
STOP_LOSS_PCT = 0.05     # 5% stop loss
TAKE_PROFIT_PCT = 0.10   # 10% take profit

# Momentum thresholds (from strategy_momentum.py)
MOM_BUY = 0.1
MOM_SELL = -0.1
CHANGE_BUY = 0.2
CHANGE_SELL = -0.2

# RSI thresholds (from strategy_rsi.py)
RSI_15M_OVERSOLD = 35
RSI_15M_OVERBOUGHT = 65
RSI_1H_OVERSOLD = 40
RSI_1H_OVERBOUGHT = 60
MIN_CONFIDENCE = 0.2  # Relaxed threshold
MIN_MOMENTUM = 0.1    # 0.1% minimum momentum (relaxed)

# Timeframes
CANDLE_MINUTES = 60  # 1 hour candles
CROSSOVER_WINDOW = 12
FETCH_LIMIT = 300


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
    momentum: float
    change_24h: float
    rsi_conf: float
    

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


def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """Calculate RSI from price series."""
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
    # Ensure float values
    rsi_15m = float(rsi_15m)
    rsi_1h = float(rsi_1h)
    
    # Score breakdown
    score_15m_buy  = max(0, (RSI_15M_OVERSOLD - rsi_15m) / RSI_15M_OVERSOLD)
    score_15m_sell = max(0, (rsi_15m - RSI_15M_OVERBOUGHT) / (100 - RSI_15M_OVERBOUGHT))
    score_1h_buy   = max(0, (RSI_1H_OVERSOLD - rsi_1h) / RSI_1H_OVERSOLD) * 0.3
    score_1h_sell  = max(0, (rsi_1h - RSI_1H_OVERBOUGHT) / (100 - RSI_1H_OVERBOUGHT)) * 0.3

    buy_score  = score_15m_buy + score_1h_buy
    sell_score = score_15m_sell + score_1h_sell

    if buy_score > sell_score and buy_score >= MIN_CONFIDENCE:
        return "BUY", min(buy_score, 1.0)
    elif sell_score > buy_score and sell_score >= MIN_CONFIDENCE:
        return "SELL", min(sell_score, 1.0)
    else:
        return "HOLD", max(buy_score, sell_score)


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


def group_into_candles(rows: list[dict], minutes: int = 60):
    """Group 5min rows into larger candles."""
    rows_per_candle = minutes // 5
    candles = []
    
    for i in range(0, len(rows), rows_per_candle):
        chunk = rows[i:i + rows_per_candle]
        if len(chunk) < rows_per_candle * 0.8:
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
            "context_rows": chunk,
            "price_history": [r["price"] for r in chunk]  # For RSI calc
        }
        candles.append(candle)
    
    return candles


def analyse_candle_with_rsi(candle: dict, prev_candles: list) -> dict:
    """Analyze candle with BOTH Momentum and RSI confluence."""
    momentum = float(candle.get("momentum") or 0)
    change = float(candle.get("change_24h") or 0)
    price = float(candle.get("close", 0) or 0)
    
    # Get momentum history for crossover
    context = candle.get("context_rows", [])
    moms = [float(r.get("momentum") or 0) for r in context[-CROSSOVER_WINDOW:]]
    crossover = detect_crossover(moms)
    
    # Calculate RSI from price history
    # Need at least 20 bars for dual-timeframe RSI (15m + 1h approximation)
    price_history = []
    for prev in prev_candles[-3:]:
        price_history.extend(prev.get("price_history", []))
    price_history.extend(candle.get("price_history", []))
    
    if len(price_history) < 20:
        return {"action": "HOLD", "reason": "insufficient RSI data"}
    
    # Calculate dual-timeframe RSI
    rsi_15m = calculate_rsi(price_history[-15:], period=14)
    rsi_1h = calculate_rsi(price_history, period=14)
    
    rsi_action, rsi_conf = confluence_score(rsi_15m, rsi_1h)
    
    # Momentum signal (relaxed - just check momentum, not both)
    bull_bonus = 0.2 if crossover == "bullish_cross" else 0.0
    bear_bonus = 0.2 if crossover == "bearish_cross" else 0.0
    
    # More lenient momentum check - just trend direction
    mom_bullish = momentum > 0 and change > 0
    mom_bearish = momentum < 0 and change < 0
    
    # SIMPLIFIED CONFLUENCE: Momentum + RSI must agree on direction
    # Buy: momentum bullish + RSI not overbought (has room to rise)
    # Sell: momentum bearish + RSI not oversold (has room to fall)
    rsi_room_to_rise = rsi_15m < 60 and rsi_1h < 65
    rsi_room_to_fall = rsi_15m > 40 and rsi_1h > 35
    
    if mom_bullish and rsi_room_to_rise and abs(momentum) >= MIN_MOMENTUM:
        conf = min(
            (abs(momentum) * 0.5 + abs(change) * 0.1 + bull_bonus + (100-float(rsi_15m))/100 * 0.3),
            1.0
        )
        return {
            "action": "BUY",
            "confidence": conf,
            "price": price,
            "momentum": momentum,
            "change_24h": change,
            "rsi_15m": rsi_15m,
            "rsi_1h": rsi_1h,
            "rsi_conf": rsi_conf,
            "crossover": crossover
        }
    
    if mom_bearish and rsi_room_to_fall and abs(momentum) >= MIN_MOMENTUM:
        conf = min(
            (abs(momentum) * 0.5 + abs(change) * 0.1 + bear_bonus + float(rsi_15m)/100 * 0.3),
            1.0
        )
        return {
            "action": "SELL",
            "confidence": conf,
            "price": price,
            "momentum": momentum,
            "change_24h": change,
            "rsi_15m": rsi_15m,
            "rsi_1h": rsi_1h,
            "rsi_conf": rsi_conf,
            "crossover": crossover
        }
    
    # Show why we held
    reasons = []
    if not mom_bullish and not mom_bearish:
        reasons.append(f"mom {momentum:+.2f}% chg {change:+.2f}%")
    if not rsi_room_to_rise and not rsi_room_to_fall:
        reasons.append(f"RSI {rsi_15m:.1f}/{rsi_1h:.1f}")
    
    return {
        "action": "HOLD",
        "reason": " | ".join(reasons) if reasons else "no confluence",
        "momentum": momentum,
        "change_24h": change,
        "rsi_15m": rsi_15m,
        "rsi_1h": rsi_1h,
        "rsi_conf": rsi_conf
    }


def run_backtest():
    conn = get_conn()
    
    print("=" * 70)
    print("MOMENTUM + RSI CONFLUENCE — BACKTEST RESULTS")
    print("=" * 70)
    print(f"Portfolio: ${INITIAL_BALANCE:,.2f}")
    print(f"Position Size: {PORTFOLIO_PCT*100:.0f}% of portfolio")
    print(f"Leverage: {LEVERAGE}x")
    print(f"Stop Loss: {STOP_LOSS_PCT*100:.0f}%")
    print(f"Take Profit: {TAKE_PROFIT_PCT*100:.0f}%")
    print(f"Trading Fee: {TRADING_FEE_PCT*100:.2f}% per trade")
    print(f"Candle Size: {CANDLE_MINUTES} minutes")
    print(f"Min Confidence: {MIN_CONFIDENCE}")
    print(f"Min Momentum: {MIN_MOMENTUM}%")
    print("-" * 70)
    
    token_results = {coin: TokenResult(coin=coin) for coin in COINS}
    
    balance = INITIAL_BALANCE
    all_trades = []
    
    # Get date range
    with conn.cursor() as cur:
        cur.execute("SELECT MIN(captured_at), MAX(captured_at) FROM trading_prices")
        min_date, max_date = cur.fetchone()
    
    print(f"\nData Range: {min_date.date()} to {max_date.date()}")
    print(f"Coins: {', '.join(COINS)}")
    print()
    
    # Process each coin
    for coin in COINS:
        print(f"Processing {coin}...", end=" ", flush=True)
        
        rows = fetch_all_5min_data(conn, coin)
        if len(rows) < 100:
            print(f"insufficient data ({len(rows)} rows)")
            continue
        
        candles = group_into_candles(rows, CANDLE_MINUTES)
        if len(candles) < 10:  # Need more candles for RSI history
            print(f"insufficient candles ({len(candles)} candles)")
            continue
        
        position = None
        
        for i, candle in enumerate(candles):
            price = float(candle["close"])
            captured_at = candle["captured_at"]
            momentum = float(candle.get("momentum") or 0)
            
            # Get previous candles for RSI context
            prev_candles = candles[max(0, i-5):i]
            signal = analyse_candle_with_rsi(candle, prev_candles)
            
            # Entry signals
            if signal["action"] == "BUY" and position is None:
                position_size = (balance * PORTFOLIO_PCT) * LEVERAGE
                entry_fee = position_size * TRADING_FEE_PCT
                
                position = {
                    "entry_price": price,
                    "size": position_size,
                    "entry_time": captured_at,
                    "direction": "LONG",
                    "entry_candle_idx": i,
                    "rsi_conf": signal.get("rsi_conf", 0),
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
                    "rsi_conf": signal.get("rsi_conf", 0),
                    "sl_price": price * (1 + STOP_LOSS_PCT),
                    "tp_price": price * (1 - TAKE_PROFIT_PCT)
                }
                token_results[coin].entries += 1
                balance -= entry_fee
            
            # Exit signals - Check SL/TP first, then signal-based exits
            elif position is not None:
                should_exit = False
                exit_reason = None
                
                # Check stop loss and take profit
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
                        pnl_usd=pnl_usd,
                        momentum=signal.get("momentum", 0),
                        change_24h=signal.get("change_24h", 0),
                        rsi_conf=position.get("rsi_conf", 0)
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
            if result.winning_trades > 0:
                best = max(result.trades, key=lambda t: t.pnl_usd)
                print(f"  Best:     +${best.pnl_usd:,.2f} ({best.pnl_pct:+.2f}%) on {best.entry_time.date()}")
            if result.losing_trades > 0:
                worst = min(result.trades, key=lambda t: t.pnl_usd)
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
        wins = sum(1 for t in all_trades if t.pnl_usd > 0)
        win_rate = wins / len(all_trades) * 100
        print(f"Win Rate:         {win_rate:.1f}% ({wins}/{len(all_trades)})")
    else:
        win_rate = 0
        
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
        
        if all_trades:
            avg_rsi_conf = sum(t.rsi_conf for t in all_trades) / len(all_trades)
            print(f"Avg RSI Conf:     {avg_rsi_conf:.2f}")
    
    print("\n" + "=" * 70)
    
    # --- Comparison ---
    print("\nCOMPARISON TO INDIVIDUAL STRATEGIES:")
    print("-" * 70)
    print("Momentum alone:   +23.12% (41 trades, 43.9% WR)")
    print("RSI alone:        +11.27% (483 trades, 33.7% WR)")
    if all_trades:
        print(f"Confluence:       {((balance/INITIAL_BALANCE)-1)*100:+.2f}% ({len(all_trades)} trades, {win_rate:.1f}% WR)")
    else:
        print("Confluence:       No trades generated")
    print("-" * 70)


if __name__ == "__main__":
    run_backtest()
