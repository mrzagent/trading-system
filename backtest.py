"""
Backtesting Engine for Reuben's Trading Signals

Uses trading_prices table which contains price data + indicator values

Usage:
    python backtest.py --start-date 2026-01-01 --end-date 2026-06-14
    python backtest.py --more-trades
    python backtest.py --config backtest_config.json
"""

import argparse
import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


@dataclass
class Trade:
    """Represents a single trade"""
    entry_date: str = ""
    exit_date: Optional[str] = None
    symbol: str = ""
    direction: str = ""  # 'long' or 'short'
    entry_price: float = 0.0
    exit_price: float = 0.0
    position_size: float = 0.0  # Number of units
    position_value: float = 0.0  # Dollar value invested
    stop_loss: float = 0.0
    take_profit: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""
    strategy: str = ""
    

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
                    min_fvg: int = 0,
                    rsi_min: Optional[float] = None,
                    rsi_max: Optional[float] = None,
                    change_24h_min: Optional[float] = None,
                    change_24h_max: Optional[float] = None,
                    momentum_min: Optional[float] = None,
                    momentum_max: Optional[float] = None) -> List[Dict]:
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
        
        # New range filters (AND logic)
        if rsi_min is not None:
            conditions.append(f"rsi >= {rsi_min}")
        if rsi_max is not None:
            conditions.append(f"rsi <= {rsi_max}")
        if change_24h_min is not None:
            conditions.append(f"change_24h >= {change_24h_min}")
        if change_24h_max is not None:
            conditions.append(f"change_24h <= {change_24h_max}")
        if momentum_min is not None:
            conditions.append(f"momentum >= {momentum_min}")
        if momentum_max is not None:
            conditions.append(f"momentum <= {momentum_max}")
        
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


class BacktestEngine:
    """Main backtesting engine"""
    
    def __init__(self, initial_capital: float = 1000.0, risk_per_trade: float = 0.02,
                 stop_loss_pct: float = 0.05, risk_reward: float = 2.0, max_position_pct: float = 0.50,
                 commission: float = 0.001, slippage: float = 0.0005, max_bars: int = 20):
        self.initial_capital = initial_capital
        self.risk_per_trade = risk_per_trade
        self.stop_loss_pct = stop_loss_pct
        self.risk_reward = risk_reward
        self.max_position_pct = max_position_pct
        self.commission = commission  # 0.1% per trade
        self.slippage = slippage     # 0.05% slippage
        self.max_bars = max_bars     # Max bars to hold a position
        self.db = DatabaseConnector()
        
    def calculate_position_size(self, capital: float, entry_price: float, stop_loss_price: float) -> tuple:
        """Calculate position size based on risk per trade"""
        # Risk amount in dollars (e.g., 2% of capital = $20 on $1000)
        risk_amount = capital * self.risk_per_trade
        
        # Calculate risk per unit (distance from entry to stop)
        risk_per_unit = abs(entry_price - stop_loss_price)
        
        if risk_per_unit <= 0:
            # Fallback to max position pct if no valid stop
            position_value = capital * self.max_position_pct
        else:
            # Position size = risk amount / risk per unit
            position_size_by_risk = risk_amount / risk_per_unit
            position_value = position_size_by_risk * entry_price
        
        # Cap at max_position_pct of capital
        max_position_value = capital * self.max_position_pct
        position_value = min(position_value, max_position_value)
        
        position_size = position_value / entry_price
        
        return position_size, position_value
    
    def run_backtest(self, table: str, start_date: str, end_date: str,
                     coins: Optional[List[str]] = None,
                     rsi_threshold: Optional[float] = None,
                     momentum_threshold: Optional[float] = None,
                     use_alerts: bool = False,
                     min_fvg: int = 0,
                     rsi_min: Optional[float] = None,
                     rsi_max: Optional[float] = None,
                     change_24h_min: Optional[float] = None,
                     change_24h_max: Optional[float] = None,
                     momentum_min: Optional[float] = None,
                     momentum_max: Optional[float] = None) -> BacktestResult:
        """Run the backtest on historical data"""
        
        result = BacktestResult(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            parameters={
                "initial_capital": self.initial_capital,
                "risk_per_trade": self.risk_per_trade,
                "stop_loss_pct": self.stop_loss_pct,
                "risk_reward": self.risk_reward,
                "max_position_pct": self.max_position_pct,
                "commission": self.commission,
                "slippage": self.slippage,
                "max_bars": self.max_bars,
                "table": table,
                "rsi_threshold": rsi_threshold,
                "momentum_threshold": momentum_threshold,
                "use_alerts": use_alerts,
                "min_fvg": min_fvg,
                "rsi_min": rsi_min,
                "rsi_max": rsi_max,
                "change_24h_min": change_24h_min,
                "change_24h_max": change_24h_max,
                "momentum_min": momentum_min,
                "momentum_max": momentum_max,
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
            min_fvg=min_fvg,
            rsi_min=rsi_min,
            rsi_max=rsi_max,
            change_24h_min=change_24h_min,
            change_24h_max=change_24h_max,
            momentum_min=momentum_min,
            momentum_max=momentum_max
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
            
            # Calculate stop loss and take profit
            if direction == "long":
                stop_loss = entry_price * (1 - self.stop_loss_pct)
                take_profit = entry_price * (1 + self.stop_loss_pct * self.risk_reward)
            else:  # short
                stop_loss = entry_price * (1 + self.stop_loss_pct)
                take_profit = entry_price * (1 - self.stop_loss_pct * self.risk_reward)
            
            # Calculate position size
            position_size, position_value = self.calculate_position_size(capital, entry_price, stop_loss)
            
            if position_size <= 0 or position_value > capital:
                continue
            
            # Apply slippage to entry
            if direction == "long":
                entry_price_adjusted = entry_price * (1 + self.slippage)
            else:
                entry_price_adjusted = entry_price * (1 - self.slippage)
            
            # Entry commission
            entry_commission = position_value * self.commission
            
            # Create trade
            trade = Trade(
                entry_date=timestamp.isoformat() if hasattr(timestamp, 'isoformat') else str(timestamp),
                symbol=symbol,
                direction=direction,
                entry_price=entry_price_adjusted,
                position_size=position_size,
                position_value=position_value,
                stop_loss=stop_loss,
                take_profit=take_profit,
                strategy=strategy
            )
            
            # Deduct entry commission from capital immediately
            capital -= entry_commission
            
            # Fetch subsequent price data to see if SL or TP hit
            price_data = self.db.get_price_data(table, symbol, timestamp, end_date)
            
            if len(price_data) < 2:
                continue
            
            # Simulate trade
            exit_price = entry_price
            exit_date = timestamp
            exit_reason = ""
            pnl = 0.0
            
            bars_held = 0
            for price_bar in price_data[1:]:  # Skip entry bar
                current_price = float(price_bar.get('price', 0))
                bar_time = price_bar.get('captured_at')
                bars_held += 1
                
                if current_price <= 0:
                    continue
                
                if direction == 'long':
                    if current_price <= stop_loss:
                        exit_price = stop_loss
                        exit_date = bar_time
                        exit_reason = "stop_loss"
                        break
                    elif current_price >= take_profit:
                        exit_price = take_profit
                        exit_date = bar_time
                        exit_reason = "take_profit"
                        break
                else:  # short
                    if current_price >= stop_loss:
                        exit_price = stop_loss
                        exit_date = bar_time
                        exit_reason = "stop_loss"
                        break
                    elif current_price <= take_profit:
                        exit_price = take_profit
                        exit_date = bar_time
                        exit_reason = "take_profit"
                        break
                
                # Check max hold time
                if bars_held >= self.max_bars:
                    exit_price = current_price
                    exit_date = bar_time
                    exit_reason = "max_bars"
                    break
                
                exit_price = current_price
                exit_date = bar_time
            else:
                exit_reason = "end_of_data"
            
            # Apply slippage to exit
            if direction == "long":
                exit_price_adjusted = exit_price * (1 - self.slippage)
            else:
                exit_price_adjusted = exit_price * (1 + self.slippage)
            
            # Calculate P&L
            if direction == 'long':
                gross_pnl = (exit_price_adjusted - entry_price_adjusted) * position_size
            else:
                gross_pnl = (entry_price_adjusted - exit_price_adjusted) * position_size
            
            # Exit commission
            exit_value = position_size * exit_price_adjusted
            exit_commission = exit_value * self.commission
            
            # Net PnL after commissions
            pnl = gross_pnl - exit_commission
            
            # Update capital (PnL only, entry commission already deducted)
            capital += pnl
            pnl_pct = (pnl / position_value) * 100 if position_value > 0 else 0
            
            # Track drawdown
            if capital > peak_capital:
                peak_capital = capital
            drawdown = (peak_capital - capital) / peak_capital
            if drawdown > max_drawdown:
                max_drawdown = drawdown
            
            # Update trade
            trade.exit_date = exit_date.isoformat() if hasattr(exit_date, 'isoformat') else str(exit_date)
            trade.exit_price = exit_price_adjusted
            trade.pnl = pnl  # Net PnL after commissions (already subtracted exit_commission above)
            trade.pnl_pct = pnl_pct
            trade.exit_reason = exit_reason
            
            trades.append(trade)
            
            # Update equity curve
            equity_curve.append({
                "date": trade.exit_date,
                "value": capital,
                "trade_pnl": pnl
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
    filename = f"backtest_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w') as f:
        json.dump(asdict(result), f, indent=2, default=str)
    
    return filepath


def print_summary(result: BacktestResult):
    """Print formatted backtest summary"""
    print("\n" + "="*60)
    print("BACKTEST RESULTS")
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
    print(f"  Sharpe Ratio:    {result.sharpe_ratio:.2f}")
    print("="*60)


def main():
    parser = argparse.ArgumentParser(description="Backtest trading signals")
    parser.add_argument("--start-date", type=str, 
                        default=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default=datetime.now().strftime("%Y-%m-%d"),
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--timeframe", type=str, default="5min", choices=["5min", "1h", "4h"],
                        help="Timeframe to use (default: 5min)")
    parser.add_argument("--stop-loss-pct", type=float, default=0.05,
                        help="Stop loss percentage (default: 0.05 = 5%%)")
    parser.add_argument("--risk-reward", type=float, default=2.0,
                        help="Risk/reward ratio (default: 2.0)")
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
    parser.add_argument("--config", type=str,
                        help="Path to JSON config file")
    parser.add_argument("--capital", type=float, default=1000.0,
                        help="Initial capital (default: 1000)")
    parser.add_argument("--risk-per-trade", type=float, default=0.02,
                        help="Risk per trade (default: 0.02 = 2%%)")
    parser.add_argument("--max-position-pct", type=float, default=0.50,
                        help="Max position size as fraction of capital (default: 0.50 = 50 percent)")
    parser.add_argument("--commission", type=float, default=0.001,
                        help="Commission per trade (default: 0.001 = 0.1%%)")
    parser.add_argument("--slippage", type=float, default=0.0005,
                        help="Slippage per trade (default: 0.0005 = 0.05%%)")
    parser.add_argument("--max-bars", type=int, default=20,
                        help="Max bars to hold position (default: 20)")
    parser.add_argument("--output-dir", type=str, default="D:\\dev\\trading\\results",
                        help="Output directory for results")
    parser.add_argument("--more-trades", action="store_true",
                        help="Lower thresholds to generate more trades")
    
    args = parser.parse_args()
    
    # Load config if provided
    if args.config:
        with open(args.config, 'r') as f:
            config = json.load(f)
            for key, value in config.items():
                if hasattr(args, key) and getattr(args, key) is None:
                    setattr(args, key, value)
    
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
    
    # If --more-trades flag, lower thresholds
    if args.more_trades:
        if args.rsi_threshold is None:
            args.rsi_threshold = 40
        if args.momentum_threshold is None:
            args.momentum_threshold = -100
        args.use_alerts = True
        args.min_fvg = 1
    
    print(f"Starting backtest...")
    print(f"  Table: {table}")
    print(f"  Period: {args.start_date} to {args.end_date}")
    print(f"  Capital: ${args.capital:,.2f}")
    print(f"  Risk/Trade: {args.risk_per_trade*100:.1f}%")
    print(f"  Max Position: {args.max_position_pct*100:.0f}%")
    print(f"  Stop Loss: {args.stop_loss_pct*100:.1f}%")
    print(f"  Risk/Reward: {args.risk_reward:.1f}x")
    print(f"  Commission: {args.commission*100:.2f}%")
    print(f"  Slippage: {args.slippage*100:.2f}%")
    print(f"  Max Bars: {args.max_bars}")
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
    engine = BacktestEngine(
        initial_capital=args.capital,
        risk_per_trade=args.risk_per_trade,
        stop_loss_pct=args.stop_loss_pct,
        risk_reward=args.risk_reward,
        max_position_pct=args.max_position_pct,
        commission=args.commission,
        slippage=args.slippage,
        max_bars=args.max_bars
    )
    
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
