"""
Backtesting Engine for Multi-TP Strategy

Uses trading_prices table which contains price data + indicator values
Updated to support partial take profit levels

Usage:
    python backtest_multitp.py --start-date 2026-01-01 --end-date 2026-06-14
    python backtest_multitp.py --risk-config risk_config.json
"""

import argparse
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor


@dataclass
class PartialClose:
    """Represents a partial position close"""
    level: str
    close_pct: float
    size_closed: float
    price: float
    pnl: float
    time: str


@dataclass
class Trade:
    """Represents a single trade with multi-TP support"""
    entry_date: str = ""
    exit_date: Optional[str] = None
    symbol: str = ""
    direction: str = ""  # 'long' or 'short'
    entry_price: float = 0.0
    exit_price: float = 0.0
    position_size: float = 0.0  # Current remaining size
    original_size: float = 0.0  # Original position size
    position_value: float = 0.0  # Current remaining value
    original_value: float = 0.0  # Original position value
    stop_loss: float = 0.0
    take_profits: List[Dict] = field(default_factory=list)  # List of TP dicts
    partial_closes: List[PartialClose] = field(default_factory=list)
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""
    strategy: str = ""
    remaining_pct: float = 1.0  # % of position still open
    tp_levels_hit: int = 0
    breakeven_hit: bool = False  # Whether SL was moved to breakeven


@dataclass
class BacktestResult:
    """Container for backtest results"""
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
    avg_tp_levels_hit: float = 0.0  # New metric
    avg_bars_held: float = 0.0
    equity_curve: List[Dict] = field(default_factory=list)
    trades: List[Dict] = field(default_factory=list)
    parameters: Dict = field(default_factory=dict)


class DatabaseConnector:
    """Handles database connections and queries"""
    
    def __init__(self, host="localhost", database="postgres", user="postgres", password="1870506303979"):
        self.conn_params = {
            "host": host,
            "database": database,
            "user": user,
            "password": password
        }
    
    def get_connection(self):
        return psycopg2.connect(**self.conn_params)
    
    def get_signals(self, table: str, start_date: str, end_date: str, 
                    coins: Optional[List[str]] = None,
                    rsi_threshold: Optional[float] = None,
                    momentum_threshold: Optional[float] = None,
                    use_alerts: bool = False,
                    min_fvg: int = 0) -> List[Dict]:
        """Fetch signals from price tables based on indicators"""
        
        conditions = ["captured_at BETWEEN %s AND %s"]
        params = [start_date, end_date]
        
        if coins:
            conditions.append("coin = ANY(%s)")
            params.append(coins)
        
        signal_conditions = []
        
        if use_alerts:
            signal_conditions.append("alert_triggered = true")
        
        if rsi_threshold is not None:
            signal_conditions.append(f"rsi < {rsi_threshold}")
        
        if momentum_threshold is not None:
            signal_conditions.append(f"momentum > {momentum_threshold}")
        
        if min_fvg > 0:
            signal_conditions.append(f"fvg_count >= {min_fvg}")
        
        if signal_conditions:
            conditions.append("(" + " OR ".join(signal_conditions) + ")")
        
        where_clause = " AND ".join(conditions)
        
        query = f"""
            SELECT captured_at, coin, price, change_24h, volume_24h, 
                   rsi, momentum, fvg_count, alert_triggered, raw_data
            FROM {table}
            WHERE {where_clause}
            ORDER BY captured_at, coin
        """
        
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
    
    def get_price_data(self, table: str, coin: str, start_date: str, end_date: str) -> List[Dict]:
        """Fetch price data for a coin"""
        query = f"""
            SELECT captured_at, price, change_24h, volume_24h
            FROM {table}
            WHERE coin = %s AND captured_at BETWEEN %s AND %s
            ORDER BY captured_at
        """
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (coin, start_date, end_date))
                return [dict(row) for row in cur.fetchall()]


class MultiTPBacktestEngine:
    """Backtesting engine with multi-TP support"""
    
    def __init__(self, risk_config_path: str = "risk_config.json"):
        # Load risk config
        with open(risk_config_path, 'r') as f:
            config = json.load(f)
        
        self.initial_capital = config.get('initial_capital', 1000.0)
        self.risk_per_trade = config.get('risk_per_trade_pct', 0.02)
        self.stop_loss_pct = config.get('stop_loss_pct', 0.05)
        self.take_profit_levels = config.get('take_profit_levels', [
            {"level": 0.05, "close_pct": 0.25, "label": "TP1"},
            {"level": 0.08, "close_pct": 0.25, "label": "TP2"},
            {"level": 0.12, "close_pct": 0.25, "label": "TP3"},
            {"level": 0.20, "close_pct": 0.25, "label": "TP4"}
        ])
        self.max_position_pct = config.get('max_position_pct', 0.50)
        self.max_open_positions = config.get('max_open_positions', 3)
        self.commission = config.get('commission_pct', 0.001)
        self.slippage = config.get('slippage_pct', 0.0005)
        self.leverage = config.get('leverage', 3.0)
        self.max_bars = 576  # Max bars to hold position (48 hours for 5min data)
        
        self.db = DatabaseConnector()
    
    def calculate_take_profits(self, entry_price: float, direction: str) -> List[Dict]:
        """Calculate all take profit levels"""
        take_profits = []
        for tp in self.take_profit_levels:
            if direction == 'long':
                tp_price = entry_price * (1 + tp['level'])
            else:
                tp_price = entry_price * (1 - tp['level'])
            
            take_profits.append({
                'label': tp['label'],
                'level_pct': tp['level'],
                'price': tp_price,
                'close_pct': tp['close_pct'],
                'hit': False
            })
        return take_profits
    
    def calculate_position_size(self, capital: float, entry_price: float, stop_loss_price: float) -> Tuple[float, float, float]:
        """Calculate position size based on risk per trade, accounting for leverage"""
        # Risk amount in dollars (e.g., 2% of capital = $20 on $1000)
        risk_amount = capital * self.risk_per_trade
        
        # Calculate risk per unit (distance from entry to stop)
        risk_per_unit = abs(entry_price - stop_loss_price)
        
        if risk_per_unit <= 0:
            # Fallback to max position pct if no valid stop
            position_value = capital * self.max_position_pct
        else:
            # Position value = risk amount / stop loss pct
            position_value = risk_amount / self.stop_loss_pct
        
        # Cap at max_position_pct of capital (this is notional with leverage)
        max_position_value = capital * self.max_position_pct
        position_value = min(position_value, max_position_value)
        
        # Calculate margin required (actual capital used)
        margin_required = position_value / self.leverage
        
        position_size = position_value / entry_price
        
        return position_size, position_value, margin_required
    
    def partial_close(self, trade: Trade, tp: Dict, current_price: float, 
                     current_time: str) -> Tuple[float, float]:
        """
        Execute a partial close at a TP level
        Returns: (pnl_from_this_close, commission_paid)
        """
        close_pct = tp['close_pct']
        size_to_close = trade.original_size * close_pct
        value_to_close = trade.original_value * close_pct
        
        # Calculate P&L for this portion
        if trade.direction == 'long':
            gross_pnl = (current_price - trade.entry_price) * size_to_close
        else:
            gross_pnl = (trade.entry_price - current_price) * size_to_close
        
        # Apply slippage to exit
        if trade.direction == 'long':
            exit_price = current_price * (1 - self.slippage)
        else:
            exit_price = current_price * (1 + self.slippage)
        
        # Recalculate with slippage
        if trade.direction == 'long':
            gross_pnl = (exit_price - trade.entry_price) * size_to_close
        else:
            gross_pnl = (trade.entry_price - exit_price) * size_to_close
        
        # Commission for this close
        commission = value_to_close * self.commission
        pnl = gross_pnl - commission
        
        # Record partial close
        partial = PartialClose(
            level=tp['label'],
            close_pct=close_pct,
            size_closed=size_to_close,
            price=exit_price,
            pnl=pnl,
            time=current_time
        )
        trade.partial_closes.append(partial)
        
        # Update trade
        trade.position_size -= size_to_close
        trade.position_value -= value_to_close
        trade.remaining_pct -= close_pct
        tp['hit'] = True
        trade.tp_levels_hit += 1
        
        # Move stop loss to breakeven after first TP
        if tp['label'] == 'TP1' and len(trade.partial_closes) == 1:
            trade.stop_loss = trade.entry_price
            trade.breakeven_hit = True
        
        return pnl, commission
    
    def run_backtest(self, table: str, start_date: str, end_date: str,
                     coins: Optional[List[str]] = None,
                     rsi_threshold: Optional[float] = None,
                     momentum_threshold: Optional[float] = None,
                     use_alerts: bool = False,
                     min_fvg: int = 0) -> BacktestResult:
        """Run the backtest on historical data with multi-TP logic"""
        
        result = BacktestResult(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            parameters={
                "initial_capital": self.initial_capital,
                "risk_per_trade": self.risk_per_trade,
                "stop_loss_pct": self.stop_loss_pct,
                "take_profit_levels": self.take_profit_levels,
                "max_position_pct": self.max_position_pct,
                "max_open_positions": self.max_open_positions,
                "commission": self.commission,
                "slippage": self.slippage,
                "leverage": self.leverage,
                "max_bars": self.max_bars,
                "table": table,
                "rsi_threshold": rsi_threshold,
                "momentum_threshold": momentum_threshold,
                "use_alerts": use_alerts,
                "min_fvg": min_fvg,
                "coins": coins
            }
        )
        
        # Fetch signals
        signals = self.db.get_signals(
            table=table,
            start_date=start_date,
            end_date=end_date,
            coins=coins,
            rsi_threshold=rsi_threshold,
            momentum_threshold=momentum_threshold,
            use_alerts=use_alerts,
            min_fvg=min_fvg
        )
        
        if not signals:
            print(f"No signals found for the given criteria")
            return result
        
        print(f"Found {len(signals)} signals to process")
        
        # Track state
        capital = self.initial_capital
        equity_curve = [{"date": start_date, "value": capital}]
        trades = []
        peak_capital = capital
        max_drawdown = 0.0
        open_positions = {}  # symbol -> Trade
        bars_held_list = []
        
        # Process each signal
        for i, signal in enumerate(signals):
            symbol = signal.get('coin', 'UNKNOWN')
            entry_price = float(signal.get('price', 0))
            timestamp = signal.get('captured_at')
            
            if entry_price <= 0 or not timestamp:
                continue
            
            # Skip if we already have an open position on this symbol
            if symbol in open_positions:
                continue
            
            # Check max positions
            if len(open_positions) >= self.max_open_positions:
                # Try to close existing positions first
                pass
            
            # Determine signal type and strategy
            strategy = "alert"
            direction = "long"
            
            if signal.get('rsi') and rsi_threshold and signal.get('rsi') < rsi_threshold:
                strategy = "rsi"
                direction = "long"
            elif signal.get('momentum') and momentum_threshold is not None and signal.get('momentum') > momentum_threshold:
                strategy = "momentum"
                direction = "long" if signal.get('momentum') > 0 else "short"
            elif signal.get('fvg_count') and signal.get('fvg_count') >= min_fvg:
                strategy = "fvg"
                direction = "long"
            
            # Calculate stop loss
            if direction == "long":
                stop_loss = entry_price * (1 - self.stop_loss_pct)
            else:
                stop_loss = entry_price * (1 + self.stop_loss_pct)
            
            # Calculate take profits
            take_profits = self.calculate_take_profits(entry_price, direction)
            
            # Calculate position size based on INITIAL capital (fixed fractional sizing)
            # This prevents exponential growth from compounding
            position_size, position_value, margin_required = self.calculate_position_size(
                self.initial_capital, entry_price, stop_loss
            )
            
            if position_size <= 0 or margin_required > capital:
                continue
            
            # Apply slippage to entry
            if direction == "long":
                entry_price_adj = entry_price * (1 + self.slippage)
            else:
                entry_price_adj = entry_price * (1 - self.slippage)
            
            # Entry commission
            entry_commission = position_value * self.commission
            
            # Create trade
            trade = Trade(
                entry_date=timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                symbol=symbol,
                direction=direction,
                entry_price=entry_price_adj,
                position_size=position_size,
                original_size=position_size,
                position_value=position_value,
                original_value=position_value,
                stop_loss=stop_loss,
                take_profits=take_profits,
                remaining_pct=1.0,
                strategy=strategy
            )
            
            # Deduct margin + entry commission from capital
            capital -= (margin_required + entry_commission)
            
            # Track open position
            open_positions[symbol] = trade
            
            # Fetch subsequent price data
            price_data = self.db.get_price_data(table, symbol, timestamp, end_date)
            
            if len(price_data) < 2:
                # Return margin if no price data
                capital += margin_required
                continue
            
            # Simulate trade with multi-TP logic
            exit_price = entry_price
            exit_date = timestamp
            exit_reason = ""
            total_pnl = 0.0
            total_commission = entry_commission
            bars_held = 0
            position_closed = False
            
            for price_bar in price_data[1:]:  # Skip entry bar
                current_price = float(price_bar.get('price', 0))
                bar_time = price_bar.get('captured_at')
                bars_held += 1
                
                if current_price <= 0:
                    continue
                
                # Check stop loss
                stop_hit = False
                if direction == 'long':
                    if current_price <= trade.stop_loss:
                        stop_hit = True
                else:
                    if current_price >= trade.stop_loss:
                        stop_hit = True
                
                if stop_hit:
                    # Close remaining position at stop loss
                    if trade.direction == 'long':
                        exit_price_adj = trade.stop_loss * (1 - self.slippage)
                        gross_pnl = (exit_price_adj - trade.entry_price) * trade.position_size
                    else:
                        exit_price_adj = trade.stop_loss * (1 + self.slippage)
                        gross_pnl = (trade.entry_price - exit_price_adj) * trade.position_size
                    
                    exit_commission = trade.position_value * self.commission
                    pnl = gross_pnl - exit_commission
                    
                    total_pnl += pnl
                    total_commission += exit_commission
                    
                    exit_price = exit_price_adj
                    exit_date = bar_time
                    exit_reason = "stop_loss"
                    position_closed = True
                    break
                
                # Check take profit levels
                for tp in trade.take_profits:
                    if tp['hit']:
                        continue
                    
                    tp_hit = False
                    if direction == 'long':
                        if current_price >= tp['price']:
                            tp_hit = True
                    else:
                        if current_price <= tp['price']:
                            tp_hit = True
                    
                    if tp_hit:
                        pnl, commission = self.partial_close(
                            trade, tp, current_price, 
                            bar_time.isoformat() if hasattr(bar_time, 'isoformat') else str(bar_time)
                        )
                        total_pnl += pnl
                        total_commission += commission
                        
                        # Check if fully closed
                        if trade.remaining_pct <= 0.01:
                            exit_price = current_price
                            exit_date = bar_time
                            exit_reason = "take_profit_full"
                            position_closed = True
                            break
                
                if position_closed:
                    break
                
                # Check max hold time
                if bars_held >= self.max_bars:
                    # Close remaining position at market
                    if trade.direction == 'long':
                        exit_price_adj = current_price * (1 - self.slippage)
                        gross_pnl = (exit_price_adj - trade.entry_price) * trade.position_size
                    else:
                        exit_price_adj = current_price * (1 + self.slippage)
                        gross_pnl = (trade.entry_price - exit_price_adj) * trade.position_size
                    
                    exit_commission = trade.position_value * self.commission
                    pnl = gross_pnl - exit_commission
                    
                    total_pnl += pnl
                    total_commission += exit_commission
                    
                    exit_price = exit_price_adj
                    exit_date = bar_time
                    exit_reason = "max_bars"
                    position_closed = True
                    break
                
                # Track final price in case of end of data
                exit_price = current_price
                exit_date = bar_time
            
            # If position not closed by end of data
            if not position_closed:
                # Close at last available price
                if trade.direction == 'long':
                    exit_price_adj = exit_price * (1 - self.slippage)
                    gross_pnl = (exit_price_adj - trade.entry_price) * trade.position_size
                else:
                    exit_price_adj = exit_price * (1 + self.slippage)
                    gross_pnl = (trade.entry_price - exit_price_adj) * trade.position_size
                
                exit_commission = trade.position_value * self.commission
                pnl = gross_pnl - exit_commission
                
                total_pnl += pnl
                total_commission += exit_commission
                exit_price = exit_price_adj
                exit_reason = "end_of_data"
                # Skip end_of_data trades - they bias results with unrealized PnL
                capital += margin_required
                continue
            
            # Update capital: return margin + total PnL
            capital += margin_required + total_pnl
            bars_held_list.append(bars_held)
            
            # Calculate PnL percentage on original position
            pnl_pct = (total_pnl / trade.original_value) * 100 if trade.original_value > 0 else 0
            
            # Track drawdown
            if capital > peak_capital:
                peak_capital = capital
            drawdown = (peak_capital - capital) / peak_capital
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            
            # Update trade
            trade.exit_date = exit_date.isoformat() if hasattr(exit_date, 'isoformat') else str(exit_date)
            trade.exit_price = exit_price
            trade.pnl = total_pnl
            trade.pnl_pct = pnl_pct
            trade.exit_reason = exit_reason
            
            trades.append(trade)
            
            # Remove from open positions
            if symbol in open_positions:
                del open_positions[symbol]
            
            # Update equity curve
            equity_curve.append({
                "date": trade.exit_date,
                "value": capital,
                "trade_pnl": total_pnl
            })
            
            if (i + 1) % 50 == 0:
                print(f"Processed {i + 1}/{len(signals)} signals... Capital: ${capital:.2f}")
        
        # Calculate statistics
        if trades:
            winning_trades = [t for t in trades if t.pnl > 0]
            losing_trades = [t for t in trades if t.pnl <= 0]
            
            total_pnl = sum(t.pnl for t in trades)
            gross_profit = sum(t.pnl for t in winning_trades) if winning_trades else 0
            gross_loss = abs(sum(t.pnl for t in losing_trades)) if losing_trades else 1
            
            # Calculate average TP levels hit
            avg_tp_hit = sum(t.tp_levels_hit for t in trades) / len(trades) if trades else 0
            avg_bars = sum(bars_held_list) / len(bars_held_list) if bars_held_list else 0
            
            result.final_capital = capital
            result.total_return_pct = ((capital - self.initial_capital) / self.initial_capital) * 100
            result.total_pnl = total_pnl
            result.total_trades = len(trades)
            result.winning_trades = len(winning_trades)
            result.losing_trades = len(losing_trades)
            result.win_rate = (len(winning_trades) / len(trades)) * 100 if trades else 0
            result.avg_win = sum(t.pnl for t in winning_trades) / len(winning_trades) if winning_trades else 0
            result.avg_loss = sum(t.pnl for t in losing_trades) / len(losing_trades) if losing_trades else 0
            result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
            result.max_drawdown_pct = max_drawdown * 100
            result.avg_tp_levels_hit = avg_tp_hit
            result.avg_bars_held = avg_bars
            result.equity_curve = equity_curve
            result.trades = [asdict(t) for t in trades]
            
            # Calculate Sharpe ratio (simplified)
            if len(equity_curve) > 1:
                returns = []
                for i in range(1, len(equity_curve)):
                    if equity_curve[i-1]['value'] > 0:
                        ret = (equity_curve[i]['value'] - equity_curve[i-1]['value']) / equity_curve[i-1]['value']
                        returns.append(ret)
                
                if returns:
                    avg_return = sum(returns) / len(returns)
                    variance = sum((r - avg_return) ** 2 for r in returns) / len(returns) if len(returns) > 1 else 0
                    std_dev = variance ** 0.5
                    result.sharpe_ratio = (avg_return / std_dev) * (252 ** 0.5) if std_dev > 0 else 0
        
        return result


def save_results(result: BacktestResult, output_dir: str = "D:\\dev\\trading\\results") -> str:
    """Save backtest results to JSON file"""
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backtest_multitp_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w') as f:
        json.dump(asdict(result), f, indent=2, default=str)
    
    return filepath


def print_summary(result: BacktestResult):
    """Print formatted backtest summary"""
    print("\n" + "="*60)
    print("MULTI-TP BACKTEST RESULTS")
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
    print(f"  Avg TP Levels:   {result.avg_tp_levels_hit:.1f}")
    print(f"  Avg Bars Held:   {result.avg_bars_held:.1f}")
    print(f"\nRisk Metrics:")
    print(f"  Max Drawdown:    {result.max_drawdown_pct:.2f}%")
    print(f"  Sharpe Ratio:    {result.sharpe_ratio:.2f}")
    print("="*60)


def main():
    parser = argparse.ArgumentParser(description="Backtest multi-TP trading strategy")
    parser.add_argument("--start-date", type=str, 
                        default=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=datetime.now().strftime("%Y-%m-%d"),
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--timeframe", type=str, default="5min", choices=["5min", "1h", "4h"],
                        help="Timeframe to use (default: 5min)")
    parser.add_argument("--risk-config", type=str, default="risk_config.json",
                        help="Path to risk config JSON file")
    parser.add_argument("--rsi-threshold", type=float, default=None,
                        help="RSI buy threshold (e.g., 30 = buy when RSI < 30)")
    parser.add_argument("--momentum-threshold", type=float, default=None,
                        help="Momentum threshold for signals")
    parser.add_argument("--use-alerts", action="store_true",
                        help="Use alert_triggered column for signals")
    parser.add_argument("--min-fvg", type=int, default=0,
                        help="Minimum FVG count for signals (default: 0 = disabled)")
    parser.add_argument("--coins", type=str,
                        help="Comma-separated list of coins (default: BTC,ETH,SOL)")
    parser.add_argument("--output-dir", type=str, default="D:\\dev\\trading\\results",
                        help="Output directory for results")
    
    args = parser.parse_args()
    
    # Default coins
    coins = ["BTC", "ETH", "SOL"]
    if args.coins:
        coins = [c.strip().upper() for c in args.coins.split(',')]
    
    # Map timeframe to table
    table_map = {
        "5min": "trading_prices",
        "1h": "trading_prices_1h",
        "4h": "trading_prices_4h"
    }
    table = table_map.get(args.timeframe, "trading_prices")
    
    # Load and display risk config
    with open(args.risk_config, 'r') as f:
        risk_cfg = json.load(f)
    
    print(f"Starting Multi-TP Backtest...")
    print(f"  Risk Config: {args.risk_config}")
    print(f"  Table: {table}")
    print(f"  Period: {args.start_date} to {args.end_date}")
    print(f"  Capital: ${risk_cfg.get('initial_capital', 1000):,.2f}")
    print(f"  Leverage: {risk_cfg.get('leverage', 3):.0f}x")
    print(f"  Stop Loss: {risk_cfg.get('stop_loss_pct', 0.05)*100:.1f}%")
    print(f"  Take Profit Levels:")
    for tp in risk_cfg.get('take_profit_levels', []):
        print(f"    {tp['label']}: +{tp['level']*100:.0f}% -> Close {tp['close_pct']*100:.0f}%")
    print(f"  Coins: {', '.join(coins)}")
    if args.rsi_threshold:
        print(f"  RSI Threshold: {args.rsi_threshold}")
    if args.momentum_threshold is not None:
        print(f"  Momentum Threshold: {args.momentum_threshold}")
    if args.use_alerts:
        print(f"  Using Alerts: Yes")
    if args.min_fvg > 0:
        print(f"  Min FVG: {args.min_fvg}")
    
    # Run backtest
    engine = MultiTPBacktestEngine(risk_config_path=args.risk_config)
    
    result = engine.run_backtest(
        table=table,
        start_date=args.start_date,
        end_date=args.end_date,
        coins=coins,
        rsi_threshold=args.rsi_threshold,
        momentum_threshold=args.momentum_threshold,
        use_alerts=args.use_alerts,
        min_fvg=args.min_fvg
    )
    
    # Print and save results
    print_summary(result)
    
    filepath = save_results(result, args.output_dir)
    print(f"\nResults saved to: {filepath}")


if __name__ == "__main__":
    main()
