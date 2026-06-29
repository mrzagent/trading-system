#!/usr/bin/env python3
"""
strategy_risk_config.py — Strategy-specific risk parameters (SL/TP).

Each strategy was backtested with specific stop loss and take profit
parameters that optimized its performance. These should be used when
executing trades from each strategy.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class StrategyRiskParams:
    """Risk parameters for a specific strategy."""
    stop_loss_pct: float      # Stop loss percentage (e.g., 0.015 = 1.5%)
    take_profit_pct: float    # Take profit percentage (e.g., 0.03 = 3%)
    use_atr: bool = False     # If True, SL/TP are ATR multipliers, not fixed %
    atr_period: int = 14      # ATR lookback period (if use_atr=True)
    atr_sl_mult: float = 1.5  # ATR multiplier for stop loss
    atr_tp_mult: float = 3.0  # ATR multiplier for take profit
    trailing_sl: bool = False # Whether to use trailing stop
    
    def to_dict(self):
        return {
            'stop_loss_pct': self.stop_loss_pct,
            'take_profit_pct': self.take_profit_pct,
            'use_atr': self.use_atr,
            'atr_period': self.atr_period,
            'atr_sl_mult': self.atr_sl_mult,
            'atr_tp_mult': self.atr_tp_mult,
            'trailing_sl': self.trailing_sl
        }


# Strategy-specific risk parameters based on backtest optimization
# Format: strategy_id -> StrategyRiskParams
STRATEGY_RISK_PARAMS = {
    # Volume Spike (scalp) — Optimized: 1.5% SL / 3% TP (1:2 R/R)
    'volume_spike': StrategyRiskParams(
        stop_loss_pct=0.015,
        take_profit_pct=0.03,
        use_atr=False
    ),
    
    # FVG Proximity (scalp) — Uses fixed 1.5% SL / 3.0% TP (best backtest results)
    'fvg_proximity': StrategyRiskParams(
        stop_loss_pct=0.015,  # 1.5% stop loss
        take_profit_pct=0.03,  # 3.0% take profit (1:2 R:R)
        use_atr=False
    ),
    
    # VWAP Reversion (scalp) — Tight stops for quick reversions
    'vwap_reversion': StrategyRiskParams(
        stop_loss_pct=0.015,
        take_profit_pct=0.03,
        use_atr=False
    ),
    
    # Momentum Scalper (scalp) — Tight stops, quick exits
    'momentum_scalper': StrategyRiskParams(
        stop_loss_pct=0.015,
        take_profit_pct=0.03,
        use_atr=False
    ),
    
    # Pullback Scalper (scalp) — Tight stops for pullback entries
    'pullback_scalper': StrategyRiskParams(
        stop_loss_pct=0.015,
        take_profit_pct=0.03,
        use_atr=False
    ),
    
    # RSI Mean Reversion (swing 4h) — Wider stops for swing trades
    'rsi_mean_reversion': StrategyRiskParams(
        stop_loss_pct=0.03,
        take_profit_pct=0.06,
        use_atr=False
    ),
    
    # Momentum RSI (swing 1h) — Moderate stops
    'momentum_rsi': StrategyRiskParams(
        stop_loss_pct=0.025,
        take_profit_pct=0.05,
        use_atr=False
    ),
    
    # Trend Breakout (swing 4h) — Wider stops for trend following
    'trend_breakout': StrategyRiskParams(
        stop_loss_pct=0.035,
        take_profit_pct=0.07,
        use_atr=False
    ),
    
    # Mean Reversion (swing 4h) — ATR-based from backtest
    'mean_reversion': StrategyRiskParams(
        stop_loss_pct=0.025,
        take_profit_pct=0.05,
        use_atr=True,
        atr_sl_mult=1.5,
        atr_tp_mult=3.0
    ),
    
    # Momentum Acceleration (swing 1h) — Moderate stops
    'momentum_accel': StrategyRiskParams(
        stop_loss_pct=0.025,
        take_profit_pct=0.05,
        use_atr=False
    ),
}


def get_strategy_risk_params(strategy_id: str) -> StrategyRiskParams:
    """
    Get risk parameters for a specific strategy.
    
    Args:
        strategy_id: The strategy identifier (e.g., 'volume_spike')
        
    Returns:
        StrategyRiskParams for the strategy, or default params if not found
    """
    return STRATEGY_RISK_PARAMS.get(
        strategy_id,
        StrategyRiskParams(stop_loss_pct=0.02, take_profit_pct=0.04)  # Default
    )


def get_all_strategy_risk_params() -> dict:
    """Return all strategy risk parameters as a dict."""
    return {
        k: v.to_dict() 
        for k, v in STRATEGY_RISK_PARAMS.items()
    }


if __name__ == "__main__":
    import json
    print("Strategy Risk Parameters:")
    print(json.dumps(get_all_strategy_risk_params(), indent=2))
