#!/usr/bin/env python3
"""
orchestrator.py — Strategy orchestrator for multi-timeframe crypto analysis with trade execution

- Runs all strategies (10 total: 4 original + 6 new) individually
- Each strategy generates its own signal with independent confidence
- Applies risk/funding filters per strategy
- Executes individual strategy trades via SignalIntegrator (no aggregation)
- Also generates aggregated signal for dashboard/monitoring only
- Saves all signals to database for dashboard display
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add trading directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from signal_integrator import SignalIntegrator
from trade_executor import RiskConfig
from db import get_conn, fetch_recent, COINS, signal_envelope, save_signal
from candle_gate import should_act, mark_acted
from strategy_risk_config import get_strategy_risk_params, StrategyRiskParams


# Path to strategy state file (managed by dashboard)
STRATEGY_STATE_PATH = Path(__file__).parent / ".strategy_state.json"

# Path to account settings (managed by dashboard)
ACCOUNT_SETTINGS_PATH = Path(__file__).parent / ".account_settings.json"


def load_account_settings() -> dict:
    """Load account settings from .account_settings.json.
    
    Returns dict with cooldown_minutes, allow_multiple_positions, leverage, position_size_pct, and environment.
    """
    try:
        if ACCOUNT_SETTINGS_PATH.exists():
            with open(ACCOUNT_SETTINGS_PATH, 'r') as f:
                settings = json.load(f)
            
            env = settings.get('environment', 'testnet')
            env_config = settings.get(env, {})
            
            return {
                'cooldown_minutes': settings.get('cooldownMinutes', 30),
                'allow_multiple_positions': settings.get('allowMultiplePositions', False),
                'leverage': settings.get('leverage', 3),
                'stop_loss': settings.get('stopLoss', 5),
                'take_profit': settings.get('takeProfit', 10),
                'position_size_pct': settings.get('positionSizePct', 2.0),
                'environment': env,
                'api_url': env_config.get('apiUrl', 'https://api.hyperliquid-testnet.xyz'),
                'wallet_address': env_config.get('walletAddress', ''),
                'private_key_env': env_config.get('privateKeyEnv', 'HYPERLIQUID_TESTNET_PRIVATE_KEY')
            }
    except Exception as e:
        print(f"[orchestrator] Warning: Failed to load account settings: {e}", file=sys.stderr)
    
    return {
        'cooldown_minutes': 30,
        'allow_multiple_positions': False,
        'leverage': 3,
        'stop_loss': 5,
        'take_profit': 10,
        'position_size_pct': 2.0,
        'environment': 'testnet',
        'api_url': 'https://api.hyperliquid-testnet.xyz',
        'wallet_address': '',
        'private_key_env': 'HYPERLIQUID_TESTNET_PRIVATE_KEY'
    }


def get_risk_config() -> RiskConfig:
    """Create RiskConfig from account settings and actual account balance."""
    settings = load_account_settings()
    
    # Get actual account balance from HyperLiquid (spot balance, not margin value)
    try:
        from hyperliquid.info import Info
        info = Info(settings['api_url'], skip_ws=True)
        main_wallet = settings.get('main_wallet_address') or settings['wallet_address']
        spot_state = info.spot_user_state(main_wallet)
        usdc_balance = 0.0
        for balance in spot_state.get('balances', []):
            if balance.get('coin') == 'USDC':
                usdc_balance = float(balance.get('total', 0))
                break
        # Use at least $100 to avoid tiny positions during testing
        initial_capital = max(usdc_balance, 100.0) if usdc_balance > 0 else 1000.0
        print(f"[orchestrator] Spot balance: ${usdc_balance:.2f}, using: ${initial_capital:.2f}", file=sys.stderr)
    except Exception as e:
        print(f"[orchestrator] Warning: Could not get account balance, using default: {e}", file=sys.stderr)
        initial_capital = 1000.0
    
    # Use position_size_pct from settings (default 2.0%)
    position_size_pct = settings.get('position_size_pct', 2.0) / 100
    
    return RiskConfig(
        initial_capital=initial_capital,
        risk_per_trade_pct=position_size_pct,
        stop_loss_pct=settings.get('stop_loss', 5) / 100,
        take_profit_levels=[{"level": settings.get('take_profit', 10) / 100, "close_pct": 1.0, "label": "TP1"}],
        max_position_pct=0.50,
        max_open_positions=3,
        commission_pct=0.001,
        slippage_pct=0.0005,
        leverage=float(settings.get('leverage', 3))
    )


def load_strategy_state() -> dict:
    """Load strategy enable/disable state from .strategy_state.json.
    
    Returns dict mapping strategy_name -> bool (enabled/disabled).
    Strategies not in the file default to enabled (True).
    """
    if not STRATEGY_STATE_PATH.exists():
        return {}
    try:
        with open(STRATEGY_STATE_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[orchestrator] Warning: Could not read strategy state: {e}")
        return {}


def is_strategy_enabled(name: str, state: dict) -> bool:
    """Check if a strategy is enabled based on state.
    
    Defaults to True (enabled) if not found in state.
    """
    return state.get(name, True)

# Import all strategies
from strategies.strategy_rsi import analyse as rsi_analyse, STRATEGY as RSI_STRATEGY
from strategies.strategy_momentum import analyse as momentum_analyse, STRATEGY as MOM_STRATEGY
from strategies.strategy_fvg import analyse as fvg_analyse, STRATEGY as FVG_STRATEGY
from strategies.strategy_volume import analyse as volume_analyse, STRATEGY as VOL_STRATEGY

# New strategies
from strategies.strategy_trend_breakout import analyse as trend_analyse, STRATEGY as TREND_STRATEGY
from strategies.strategy_mean_reversion import analyse as meanrev_analyse, STRATEGY as MEANREV_STRATEGY
from strategies.strategy_momentum_accel import analyse as accel_analyse, STRATEGY as ACCEL_STRATEGY
from strategies.strategy_vwap_reversion import analyse as vwap_analyse, STRATEGY as VWAP_STRATEGY
from strategies.strategy_momentum_scalper import analyse as scalper_analyse, STRATEGY as SCALPER_STRATEGY
from strategies.strategy_pullback_scalper import analyse as pullback_analyse, STRATEGY as PULLBACK_STRATEGY


ORCHESTRATOR_STRATEGY = "quorum_view"
CANDLE_MINUTES = 5  # 5-minute orchestration window (matches fastest strategies)

# Strategy configuration with metadata
STRATEGY_CONFIG = {
    # Original strategies
    "rsi_mean_reversion": {
        "fn": rsi_analyse, "timeframe": "4h", "minutes": 240,
        "type": "mean_reversion", "style": "swing"
    },
    "momentum_rsi": {
        "fn": momentum_analyse, "timeframe": "1h", "minutes": 60,
        "type": "trend_following", "style": "swing"
    },
    "fvg_proximity": {
        "fn": fvg_analyse, "timeframe": "5min", "minutes": 5,
        "type": "mean_reversion", "style": "scalp"
    },
    "volume_spike": {
        "fn": volume_analyse, "timeframe": "5min", "minutes": 5,
        "type": "breakout", "style": "scalp"
    },
    # New strategies
    "trend_breakout": {
        "fn": trend_analyse, "timeframe": "4h", "minutes": 240,
        "type": "trend_following", "style": "swing"
    },
    "mean_reversion": {
        "fn": meanrev_analyse, "timeframe": "4h", "minutes": 240,
        "type": "mean_reversion", "style": "swing"
    },
    "momentum_accel": {
        "fn": accel_analyse, "timeframe": "1h", "minutes": 60,
        "type": "momentum", "style": "swing"
    },
    "vwap_reversion": {
        "fn": vwap_analyse, "timeframe": "5min", "minutes": 5,
        "type": "mean_reversion", "style": "scalp"
    },
    "momentum_scalper": {
        "fn": scalper_analyse, "timeframe": "5min", "minutes": 5,
        "type": "momentum", "style": "scalp"
    },
    "pullback_scalper": {
        "fn": pullback_analyse, "timeframe": "5min", "minutes": 5,
        "type": "mean_reversion", "style": "scalp"
    },
}

# Risk filters
MAX_FUNDING_PCT = 50.0  # Max % of portfolio to allocate
MIN_CONFIDENCE = 0.50   # Minimum confidence to consider a signal
QUORUM_PCT = 0.50       # 50% quorum required (majority of active strategies)


def is_funding_ok() -> bool:
    """Check if there's available funding for new positions."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(SUM(allocated_pct), 0) FROM trading_positions WHERE status = 'open'
            """)
            used = cur.fetchone()[0] or 0
            return (100.0 - used) >= (100.0 - MAX_FUNDING_PCT)
    except Exception:
        return True  # Default to OK if table doesn't exist
    finally:
        conn.close()


def run_strategy(name: str, config: dict, coin: str, conn, candle_start) -> dict:
    """Run a single strategy and return its signal."""
    try:
        return config["fn"](coin, conn, candle_start, config["timeframe"])
    except Exception as e:
        return signal_envelope(
            name, coin, "HOLD", 0.0,
            f"Strategy error: {str(e)}",
            {"error": str(e)}
        )


def aggregate_signals(signals: list[dict], strategy_results: dict) -> tuple[str, float, str, str, str]:
    """
    Aggregate strategy signals using quorum logic.
    Returns (action, confidence, reasoning, dominant_strategy, dominant_style).
    """
    if not signals:
        return "HOLD", 0.0, "No signals to aggregate", "none", "unknown"
    
    # Find dominant strategy (highest confidence signal)
    dominant_signal = max(signals, key=lambda s: s.get('confidence', 0))
    dominant_strategy = dominant_signal.get('strategy', 'unknown')
    
    # Get the style of the dominant strategy from STRATEGY_CONFIG
    dominant_style = STRATEGY_CONFIG.get(dominant_strategy, {}).get('style', 'unknown')
    
    # Filter to signals with sufficient confidence
    valid_signals = [s for s in signals if s.get("confidence", 0) >= MIN_CONFIDENCE]
    
    if not valid_signals:
        return "HOLD", 0.0, "No signals meet minimum confidence threshold", dominant_strategy, dominant_style
    
    # Count votes
    buy_votes = [s for s in valid_signals if s.get("action") == "BUY"]
    sell_votes = [s for s in valid_signals if s.get("action") == "SELL"]
    
    total_active = len(valid_signals)
    buy_count = len(buy_votes)
    sell_count = len(sell_votes)
    
    # Calculate quorum threshold (50% of active strategies)
    quorum_threshold = max(1, int(total_active * QUORUM_PCT))
    
    # Calculate weighted confidence
    buy_conf = sum(s.get("confidence", 0) for s in buy_votes) / buy_count if buy_count > 0 else 0
    sell_conf = sum(s.get("confidence", 0) for s in sell_votes) / sell_count if sell_count > 0 else 0
    
    # Determine action based on quorum
    if buy_count >= quorum_threshold and buy_count > sell_count:
        avg_conf = buy_conf * (buy_count / total_active)  # Weight by consensus strength
        reason = f"{buy_count}/{total_active} strategies agree (BUY quorum) | Driver: {dominant_strategy} [{dominant_style.upper()}]"
        return "BUY", round(min(avg_conf, 0.98), 2), reason, dominant_strategy, dominant_style
    
    if sell_count >= quorum_threshold and sell_count > buy_count:
        avg_conf = sell_conf * (sell_count / total_active)
        reason = f"{sell_count}/{total_active} strategies agree (SELL quorum) | Driver: {dominant_strategy} [{dominant_style.upper()}]"
        return "SELL", round(min(avg_conf, 0.98), 2), reason, dominant_strategy, dominant_style
    
    # No clear consensus
    hold_reason = f"No quorum: BUY={buy_count}, SELL={sell_count}, HOLD={total_active - buy_count - sell_count} (need {quorum_threshold}) | Top: {dominant_strategy} [{dominant_style.upper()}]"
    return "HOLD", 0.0, hold_reason, dominant_strategy, dominant_style


def get_dominant_strategy_risk(signals: list[dict], strategy_results: dict) -> StrategyRiskParams:
    """
    Determine the dominant strategy's risk parameters based on signal confidence.
    Returns the risk params of the highest-confidence strategy that contributed.
    """
    if not signals:
        return StrategyRiskParams(stop_loss_pct=0.02, take_profit_pct=0.04)
    
    # Find the highest confidence signal
    best_signal = max(signals, key=lambda s: s.get('confidence', 0))
    best_strategy = best_signal.get('strategy', 'unknown')
    
    return get_strategy_risk_params(best_strategy)


def analyse(coin: str, conn, candle_start) -> dict:
    """Run all enabled strategies and aggregate their signals."""
    
    # Load strategy enable/disable state
    strategy_state = load_strategy_state()
    
    # Run only enabled strategies
    all_signals = []
    strategy_results = {}
    skipped_strategies = []
    
    for name, config in STRATEGY_CONFIG.items():
        if not is_strategy_enabled(name, strategy_state):
            skipped_strategies.append(name)
            continue
        signal = run_strategy(name, config, coin, conn, candle_start)
        all_signals.append(signal)
        strategy_results[name] = signal
    
    # Aggregate signals
    action, confidence, reasoning, dominant_strategy, dominant_style = aggregate_signals(all_signals, strategy_results)
    
    # Apply funding filter
    funding_ok = is_funding_ok()
    if action in ["BUY", "SELL"] and not funding_ok:
        action = "HOLD"
        reasoning += " [BLOCKED: Funding limit reached]"
    
    # Get strategy-specific risk parameters from dominant strategy
    risk_params = get_strategy_risk_params(dominant_strategy)
    
    # Build detailed metadata
    meta = {
        "coin": coin,
        "strategies_run": len(all_signals),
        "strategies_total": len(STRATEGY_CONFIG),
        "strategies_disabled": skipped_strategies,
        "strategy_breakdown": {
            name: {
                "action": s.get("action"),
                "confidence": s.get("confidence"),
                "reason": s.get("reason", "")[:100]  # Truncate for brevity
            }
            for name, s in strategy_results.items()
        },
        "quorum_required": max(1, int(len([s for s in all_signals if s.get("confidence", 0) >= MIN_CONFIDENCE]) * QUORUM_PCT)),
        "funding_ok": funding_ok,
        "candle": candle_start.isoformat(),
        # Strategy-specific SL/TP parameters
        "stop_loss_pct": risk_params.stop_loss_pct * 100,  # Convert to % for signal_integrator
        "take_profit_pct": risk_params.take_profit_pct * 100,
        "use_atr": risk_params.use_atr,
        "atr_sl_mult": risk_params.atr_sl_mult,
        "atr_tp_mult": risk_params.atr_tp_mult,
        "dominant_strategy": dominant_strategy,
        "strategy_style": dominant_style or "mixed",
        "dominant_style": dominant_style,
    }
    
    return signal_envelope(
        ORCHESTRATOR_STRATEGY, coin, action, confidence,
        reasoning, meta
    )


def main():
    """Main entry point - runs all strategies individually and executes trades per strategy."""
    act, candle_start = should_act(ORCHESTRATOR_STRATEGY, CANDLE_MINUTES)
    if not act:
        print(json.dumps({
            "strategy": ORCHESTRATOR_STRATEGY,
            "action": "HOLD",
            "reason": "candle not closed yet",
            "candle": candle_start.isoformat()
        }))
        return

    conn = get_conn()
    all_results = []  # All signals for dashboard
    signals_for_execution = []  # Individual strategy signals for trading
    
    # Load strategy state
    strategy_state = load_strategy_state()
    
    try:
        for coin in COINS:
            # Run each strategy individually
            for name, config in STRATEGY_CONFIG.items():
                if not is_strategy_enabled(name, strategy_state):
                    continue
                
                # Run the strategy
                signal = run_strategy(name, config, coin, conn, candle_start)
                
                # Enrich signal with style metadata for consistent labeling
                signal['meta'] = signal.get('meta', {})
                signal['meta']['strategy_style'] = config.get('style', 'unknown')
                signal['meta']['strategy_type'] = config.get('type', 'unknown')
                
                all_results.append(signal)
                
                # Save individual signal to database
                try:
                    save_signal(conn, signal, table="trading_signals")
                except Exception as e:
                    print(f"[orchestrator] Warning: Failed to save signal for {name}/{coin}: {e}", file=sys.stderr)
                
                # Queue BUY/SELL signals for trade execution (per strategy)
                action = signal.get('action', 'HOLD')
                confidence = signal.get('confidence', 0)
                if action in ['BUY', 'SELL'] and confidence >= MIN_CONFIDENCE:
                    # Use SL/TP from strategy's signal meta (backtested values)
                    # Fall back to strategy_risk_config only if strategy doesn't provide them
                    signal_meta = signal.get('meta', {})
                    
                    # Get SL/TP from strategy meta, or fall back to strategy_risk_config
                    sl_pct = signal_meta.get('stop_loss_pct')
                    tp_pct = signal_meta.get('take_profit_pct')
                    
                    if sl_pct is None or tp_pct is None:
                        # Strategy doesn't provide SL/TP, use config fallback
                        risk_params = get_strategy_risk_params(name)
                        sl_pct = (sl_pct or risk_params.stop_loss_pct * 100)
                        tp_pct = (tp_pct or risk_params.take_profit_pct * 100)
                    
                    exec_signal = {
                        'strategy': name,  # Use individual strategy name, not orchestrator
                        'coin': coin,
                        'action': action,
                        'confidence': confidence,
                        'reason': signal.get('reason', f'{name} signal'),
                        'meta': {
                            'price': signal_meta.get('price', 0),
                            'candle': candle_start.isoformat(),
                            # Use strategy's own SL/TP from backtesting, with fallback
                            'stop_loss_pct': sl_pct,
                            'take_profit_pct': tp_pct,
                            'strategy_type': config.get('type', 'unknown'),
                            'strategy_style': config.get('style', 'unknown')
                        },
                        'generated_at': datetime.now(timezone.utc).isoformat()
                    }
                    signals_for_execution.append(exec_signal)
            
            # Also generate aggregated signal for dashboard/monitoring (no trade execution)
            aggregated = analyse(coin, conn, candle_start)
            all_results.append(aggregated)
            try:
                save_signal(conn, aggregated, table="trading_signals")
            except Exception as e:
                print(f"[orchestrator] Warning: Failed to save aggregated signal for {coin}: {e}", file=sys.stderr)
                
    finally:
        conn.close()
    
    mark_acted(ORCHESTRATOR_STRATEGY, candle_start)
    
    # Load account settings (cooldown, position rules)
    account_settings = load_account_settings()
    cooldown_minutes = account_settings.get('cooldown_minutes', 30)
    allow_multiple_positions = account_settings.get('allow_multiple_positions', False)
    
    # Execute trades via SignalIntegrator (per individual strategy signal)
    executed_trades = []
    if signals_for_execution:
        print(f"[orchestrator] Executing {len(signals_for_execution)} individual strategy trade signals...", file=sys.stderr)
        print(f"[orchestrator] Settings: cooldown={cooldown_minutes}m, allow_multiple_positions={allow_multiple_positions}", file=sys.stderr)
        try:
            integrator = SignalIntegrator(
                risk_config=get_risk_config(),
                test_mode=False,  # LIVE MODE - Place real trades on HyperLiquid
                min_confidence=MIN_CONFIDENCE,
                cooldown_minutes=cooldown_minutes,
                allow_multiple_positions=allow_multiple_positions
            )
            # Check and manage existing positions first
            integrator.check_and_manage_positions()
            # Execute new signals
            for signal in signals_for_execution:
                result = integrator.process_signal(signal, dry_run=False)
                if result:
                    executed_trades.append({
                        'strategy': signal['strategy'],
                        'coin': signal['coin'],
                        'action': signal['action'],
                        'confidence': signal['confidence'],
                        'trade_id': result.get('trade_id')
                    })
                    print(f"[orchestrator] Executed: {signal['strategy']} {signal['coin']} {signal['action']}", file=sys.stderr)
                else:
                    print(f"[orchestrator] Skipped: {signal['strategy']} {signal['coin']} (cooldown or filter)", file=sys.stderr)
            integrator.print_status()
        except Exception as e:
            print(f"[orchestrator] Error during trade execution: {e}", file=sys.stderr)
    
    # Output as JSON
    enabled_count = sum(1 for name in STRATEGY_CONFIG if is_strategy_enabled(name, strategy_state))
    output = {
        "orchestrator_run": datetime.now(timezone.utc).isoformat(),
        "candle_start": candle_start.isoformat(),
        "strategies_active": enabled_count,
        "strategies_total": len(STRATEGY_CONFIG),
        "individual_signals_generated": len(signals_for_execution),
        "signals": all_results,
        "trades_executed": len(executed_trades),
        "executed_trades": executed_trades
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
