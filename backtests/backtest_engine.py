"""
Unified Backtesting Engine for Trading Strategies

Standard parameters:
- Initial capital: $1000
- Risk per trade: 2%
- Leverage: 3x
- Commission: 0.035% (HyperLiquid taker fee)

Usage:
    python backtest_engine.py --strategy fvg --coin BTC --timeframe 15m
    python backtest_engine.py --strategy momentum --coin SOL --timeframe 5m
"""

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Callable
import csv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class Trade:
    """Standardized trade record"""
    entry_date: str = ""
    exit_date: Optional[str] = None
    symbol: str = ""
    direction: str = ""  # 'long' or 'short'
    entry_price: float = 0.0
    exit_price: float = 0.0
    position_size: float = 0.0  # Number of coins
    position_value: float = 0.0  # Dollar value at entry
    margin_used: float = 0.0  # Margin required
    stop_loss: float = 0.0
    take_profit: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""  # 'tp', 'sl', 'close'
    strategy: str = ""
    

@dataclass
class BacktestConfig:
    """Standard backtest configuration"""
    initial_capital: float = 1000.0
    risk_per_trade_pct: float = 0.02  # 2%
    leverage: float = 3.0
    commission_pct: float = 0.00035  # 0.035% HyperLiquid taker fee
    slippage_pct: float = 0.0005  # 0.05% slippage estimate
    

@dataclass
class BacktestResult:
    """Standard backtest results"""
    strategy: str = ""
    coin: str = ""
    timeframe: str = ""
    start_date: str = ""
    end_date: str = ""
    config: Dict = field(default_factory=dict)
    
    # Performance metrics
    initial_capital: float = 1000.0
    final_capital: float = 1000.0
    total_return_pct: float = 0.0
    total_pnl: float = 0.0
    
    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    
    # Risk metrics
    max_drawdown_pct: float = 0.0
    max_drawdown_amount: float = 0.0
    sharpe_ratio: float = 0.0
    
    # Data
    equity_curve: List[Dict] = field(default_factory=list)
    trades: List[Dict] = field(default_factory=list)


class DataLoader:
    """Load price data from CSV files"""
    
    def __init__(self, data_dir: str = "D:\\dev\\trading\\data"):
        self.data_dir = Path(data_dir)
    
    def load_binance_data(self, coin: str, timeframe: str) -> List[Dict]:
        """Load Binance OHLCV data from CSV"""
        filename = f"binance_{coin.lower()}_{timeframe}_"
        
        # Find the most recent file matching pattern
        files = list(self.data_dir.glob(f"{filename}*.csv"))
        if not files:
            raise FileNotFoundError(f"No data file found for {coin} {timeframe}")
        
        # Use most recent file
        latest_file = max(files, key=lambda p: p.stat().st_mtime)
        
        candles = []
        with open(latest_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                candles.append({
                    'timestamp': row.get('timestamp', row.get('open_time')),
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': float(row['volume'])
                })
        
        return candles


class BacktestEngine:
    """Unified backtesting engine"""
    
    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
        self.data_loader = DataLoader()
        self.capital = self.config.initial_capital
        self.peak_capital = self.config.initial_capital
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict] = []
        
    def calculate_position_size(self, entry_price: float, stop_loss: float) -> tuple:
        """Calculate position size based on risk parameters"""
        risk_amount = self.capital * self.config.risk_per_trade_pct
        stop_distance = abs(entry_price - stop_loss) / entry_price
        
        if stop_distance == 0:
            return 0, 0, 0
        
        # Position value = risk / stop_distance
        position_value = risk_amount / stop_distance
        
        # Cap position value to available capital
        max_position = self.capital * 0.95  # 95% max
        position_value = min(position_value, max_position)
        
        # Calculate margin and size
        margin = position_value / self.config.leverage
        size = position_value / entry_price
        
        return size, position_value, margin
    
    def execute_trade(self, signal: Dict, candles: List[Dict], idx: int) -> Optional[Trade]:
        """Execute a trade based on signal"""
        if idx >= len(candles):
            return None
        
        candle = candles[idx]
        entry_price = candle['close']
        
        # Get stop loss and take profit from signal
        stop_loss = signal.get('stop_loss', entry_price * 0.95)
        take_profit = signal.get('take_profit', entry_price * 1.03)
        direction = signal.get('direction', 'long')
        
        # Calculate position
        size, position_value, margin = self.calculate_position_size(entry_price, stop_loss)
        
        if size <= 0 or margin > self.capital * 0.95:
            return None  # Insufficient capital
        
        trade = Trade(
            entry_date=candle['timestamp'],
            symbol=signal.get('coin', 'UNKNOWN'),
            direction=direction,
            entry_price=entry_price,
            position_size=size,
            position_value=position_value,
            margin_used=margin,
            stop_loss=stop_loss,
            take_profit=take_profit,
            strategy=signal.get('strategy', 'unknown')
        )
        
        # Deduct margin from capital
        self.capital -= margin
        
        return trade
    
    def close_trade(self, trade: Trade, exit_price: float, exit_date: str, reason: str):
        """Close a trade and calculate P&L"""
        trade.exit_price = exit_price
        trade.exit_date = exit_date
        trade.exit_reason = reason
        
        # Calculate P&L
        if trade.direction == 'long':
            price_change = (exit_price - trade.entry_price) / trade.entry_price
        else:
            price_change = (trade.entry_price - exit_price) / trade.entry_price
        
        gross_pnl = trade.position_value * price_change
        
        # Deduct fees (entry + exit)
        fees = trade.position_value * self.config.commission_pct * 2
        
        trade.pnl = gross_pnl - fees
        trade.pnl_pct = (trade.pnl / trade.margin_used) * 100
        
        # Return margin + P&L to capital
        self.capital += trade.margin_used + trade.pnl
        
        # Update peak capital
        if self.capital > self.peak_capital:
            self.peak_capital = self.capital
    
    def check_exit(self, trade: Trade, candle: Dict) -> Optional[str]:
        """Check if trade should exit based on candle data"""
        if trade.direction == 'long':
            # Check stop loss
            if candle['low'] <= trade.stop_loss:
                return 'sl'
            # Check take profit
            if candle['high'] >= trade.take_profit:
                return 'tp'
        else:  # short
            # Check stop loss
            if candle['high'] >= trade.stop_loss:
                return 'sl'
            # Check take profit
            if candle['low'] <= trade.take_profit:
                return 'tp'
        
        return None
    
    def run_backtest(self, strategy_fn: Callable, coin: str, timeframe: str, 
                     start_date: str = None, end_date: str = None) -> BacktestResult:
        """Run a complete backtest"""
        # Load data
        candles = self.data_loader.load_binance_data(coin, timeframe)
        
        if start_date:
            candles = [c for c in candles if c['timestamp'] >= start_date]
        if end_date:
            candles = [c for c in candles if c['timestamp'] <= end_date]
        
        if not candles:
            raise ValueError("No data available for specified date range")
        
        # Reset state
        self.capital = self.config.initial_capital
        self.peak_capital = self.config.initial_capital
        self.trades = []
        self.equity_curve = []
        
        open_trade = None
        
        for i, candle in enumerate(candles):
            # Record equity
            total_value = self.capital
            if open_trade:
                # Add unrealized P&L
                if open_trade.direction == 'long':
                    unrealized = open_trade.position_value * ((candle['close'] - open_trade.entry_price) / open_trade.entry_price)
                else:
                    unrealized = open_trade.position_value * ((open_trade.entry_price - candle['close']) / open_trade.entry_price)
                total_value += open_trade.margin_used + unrealized
            
            self.equity_curve.append({
                'date': candle['timestamp'],
                'equity': total_value,
                'cash': self.capital
            })
            
            # Check for exit on open trade
            if open_trade:
                exit_reason = self.check_exit(open_trade, candle)
                if exit_reason:
                    # Close trade
                    if exit_reason == 'sl':
                        exit_price = open_trade.stop_loss
                    elif exit_reason == 'tp':
                        exit_price = open_trade.take_profit
                    else:
                        exit_price = candle['close']
                    
                    self.close_trade(open_trade, exit_price, candle['timestamp'], exit_reason)
                    self.trades.append(open_trade)
                    open_trade = None
            
            # Check for new entry (only if no open trade)
            if not open_trade:
                signal = strategy_fn(candles, i)
                if signal and signal.get('action') in ['BUY', 'SELL']:
                    signal['coin'] = coin
                    signal['direction'] = 'long' if signal['action'] == 'BUY' else 'short'
                    open_trade = self.execute_trade(signal, candles, i)
        
        # Close any remaining open trade at last price
        if open_trade and candles:
            self.close_trade(open_trade, candles[-1]['close'], candles[-1]['timestamp'], 'close')
            self.trades.append(open_trade)
        
        return self._generate_result(strategy_fn.__name__, coin, timeframe, candles)
    
    def _generate_result(self, strategy: str, coin: str, timeframe: str, 
                         candles: List[Dict]) -> BacktestResult:
        """Generate backtest results"""
        result = BacktestResult(
            strategy=strategy,
            coin=coin,
            timeframe=timeframe,
            start_date=candles[0]['timestamp'] if candles else "",
            end_date=candles[-1]['timestamp'] if candles else "",
            config=asdict(self.config),
            initial_capital=self.config.initial_capital,
            final_capital=self.capital,
            total_trades=len(self.trades),
            equity_curve=self.equity_curve,
            trades=[asdict(t) for t in self.trades]
        )
        
        # Calculate metrics
        if result.total_trades > 0:
            winning = [t for t in self.trades if t.pnl > 0]
            losing = [t for t in self.trades if t.pnl <= 0]
            
            result.winning_trades = len(winning)
            result.losing_trades = len(losing)
            result.win_rate = len(winning) / len(self.trades) * 100
            
            if winning:
                result.avg_win = sum(t.pnl for t in winning) / len(winning)
            if losing:
                result.avg_loss = sum(t.pnl for t in losing) / len(losing)
            
            gross_profit = sum(t.pnl for t in winning)
            gross_loss = abs(sum(t.pnl for t in losing))
            result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
            
            result.total_pnl = sum(t.pnl for t in self.trades)
            result.total_return_pct = (result.total_pnl / self.config.initial_capital) * 100
        
        # Calculate max drawdown
        peak = self.config.initial_capital
        max_dd = 0
        max_dd_amount = 0
        
        for point in self.equity_curve:
            equity = point['equity']
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            if dd > max_dd:
                max_dd = dd
                max_dd_amount = peak - equity
        
        result.max_drawdown_pct = max_dd * 100
        result.max_drawdown_amount = max_dd_amount
        
        return result
    
    def print_report(self, result: BacktestResult):
        """Print formatted backtest report"""
        print("\n" + "="*60)
        print(f"BACKTEST RESULTS: {result.strategy.upper()}")
        print("="*60)
        print(f"Coin:        {result.coin}")
        print(f"Timeframe:   {result.timeframe}")
        print(f"Period:      {result.start_date[:10]} to {result.end_date[:10]}")
        print("-"*60)
        print(f"Initial Capital:    ${result.initial_capital:,.2f}")
        print(f"Final Capital:      ${result.final_capital:,.2f}")
        print(f"Total Return:       {result.total_return_pct:+.2f}%")
        print(f"Total P&L:          ${result.total_pnl:+.2f}")
        print("-"*60)
        print(f"Total Trades:       {result.total_trades}")
        print(f"Winning Trades:     {result.winning_trades}")
        print(f"Losing Trades:      {result.losing_trades}")
        print(f"Win Rate:           {result.win_rate:.1f}%")
        print(f"Profit Factor:      {result.profit_factor:.2f}")
        print("-"*60)
        print(f"Max Drawdown:       {result.max_drawdown_pct:.2f}% (${result.max_drawdown_amount:,.2f})")
        print("="*60)


def main():
    parser = argparse.ArgumentParser(description="Unified Backtesting Engine")
    parser.add_argument("--strategy", required=True, help="Strategy name")
    parser.add_argument("--coin", default="BTC", help="Coin symbol (BTC, ETH, SOL)")
    parser.add_argument("--timeframe", default="15m", help="Timeframe (5m, 15m, 1h, 4h)")
    parser.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", help="Output JSON file")
    
    args = parser.parse_args()
    
    # Import strategy dynamically
    try:
        strategy_module = __import__(f"strategies.strategy_{args.strategy}", fromlist=["generate_signal"])
        strategy_fn = strategy_module.generate_signal
    except ImportError:
        print(f"Error: Strategy '{args.strategy}' not found")
        print("Available strategies: fvg, momentum, mean_reversion, volume, rsi")
        sys.exit(1)
    
    # Run backtest
    engine = BacktestEngine()
    result = engine.run_backtest(strategy_fn, args.coin, args.timeframe, 
                                  args.start_date, args.end_date)
    
    # Print report
    engine.print_report(result)
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(asdict(result), f, indent=2)
        print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
