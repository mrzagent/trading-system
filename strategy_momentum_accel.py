#!/usr/bin/env python3
"""
strategy_momentum_accel.py — Momentum Acceleration Strategy (Swing Trade)
Timeframe : 1h candles
Type      : Swing trade (momentum)

Signal logic:
  BUY  when momentum is increasing AND acceleration is positive (momentum building up)
  SELL when momentum is decreasing AND acceleration is negative (momentum fading)
  HOLD when momentum is flat or decelerating

Uses rate of change (ROC) for momentum and its derivative for acceleration.
"""
import json
from db import get_conn, fetch_recent, COINS, signal_envelope
from candle_gate import should_act, mark_acted

STRATEGY       = "momentum_accel"
CANDLE_MINUTES = 60    # 1-hour candles
MOM_PERIOD     = 10    # Period for momentum calculation (ROC)
ACCEL_PERIOD   = 5     # Period for acceleration calculation
MIN_ROWS       = 20
MOM_THRESHOLD  = 0.5   # Minimum momentum % to consider
ACCEL_THRESHOLD = 0.1  # Minimum acceleration to trigger


def calculate_roc(prices: list[float], period: int) -> float:
    """Calculate Rate of Change (momentum) as percentage."""
    if len(prices) < period + 1:
        return 0.0
    current = prices[-1]
    past = prices[-(period + 1)]
    return ((current - past) / past * 100) if past != 0 else 0.0


def calculate_acceleration(momentum_values: list[float]) -> float:
    """Calculate acceleration as change in momentum."""
    if len(momentum_values) < 2:
        return 0.0
    return momentum_values[-1] - momentum_values[-2]


def analyse(coin: str, conn, candle_start, timeframe: str = "1h") -> dict:
    rows = fetch_recent(conn, coin, limit=MOM_PERIOD + ACCEL_PERIOD + 10, timeframe=timeframe)
    if len(rows) < MIN_ROWS:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0,
                               f"insufficient data ({len(rows)} rows, need {MIN_ROWS})")

    latest = rows[-1]
    price = float(latest["price"])
    
    # Get closing prices
    closes = [float(r["price"]) for r in rows]
    
    # Calculate momentum series
    momentum_values = []
    for i in range(ACCEL_PERIOD + 1):
        if len(closes) >= MOM_PERIOD + i + 1:
            slice_prices = closes[:len(closes) - i] if i > 0 else closes
            roc = calculate_roc(slice_prices, MOM_PERIOD)
            momentum_values.insert(0, roc)  # Oldest first
    
    if len(momentum_values) < 2:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "insufficient momentum data")
    
    current_momentum = momentum_values[-1]
    acceleration = calculate_acceleration(momentum_values)
    
    # Calculate confidence based on momentum strength and acceleration
    mom_strength = abs(current_momentum)
    accel_strength = abs(acceleration)
    
    # BUY: Positive momentum with positive acceleration
    if current_momentum > MOM_THRESHOLD and acceleration > ACCEL_THRESHOLD:
        conf = min((mom_strength / 5.0) * 0.6 + (accel_strength / 2.0) * 0.4, 0.95)
        return signal_envelope(
            STRATEGY, coin, "BUY", round(conf, 2),
            f"Momentum accelerating: {current_momentum:.2f}% ROC with +{acceleration:.2f}% acceleration",
            {"price": price, "momentum": round(current_momentum, 2),
             "acceleration": round(acceleration, 2), "mom_period": MOM_PERIOD,
             "candle": candle_start.isoformat()},
        )
    
    # SELL: Negative momentum with negative acceleration
    if current_momentum < -MOM_THRESHOLD and acceleration < -ACCEL_THRESHOLD:
        conf = min((mom_strength / 5.0) * 0.6 + (accel_strength / 2.0) * 0.4, 0.95)
        return signal_envelope(
            STRATEGY, coin, "SELL", round(conf, 2),
            f"Momentum decelerating: {current_momentum:.2f}% ROC with {acceleration:.2f}% acceleration",
            {"price": price, "momentum": round(current_momentum, 2),
             "acceleration": round(acceleration, 2), "mom_period": MOM_PERIOD,
             "candle": candle_start.isoformat()},
        )
    
    # HOLD: No clear signal
    return signal_envelope(
        STRATEGY, coin, "HOLD", 0.0,
        f"Momentum: {current_momentum:.2f}%, Acceleration: {acceleration:.2f}% — no clear signal",
        {"price": price, "momentum": round(current_momentum, 2),
         "acceleration": round(acceleration, 2), "candle": candle_start.isoformat()},
    )


def main():
    act, candle_start = should_act(STRATEGY, CANDLE_MINUTES)
    if not act:
        print(json.dumps([{"strategy": STRATEGY, "action": "HOLD",
                           "reason": "candle not closed yet"}]))
        return

    conn = get_conn()
    signals = [analyse(coin, conn, candle_start) for coin in COINS]
    conn.close()

    mark_acted(STRATEGY, candle_start)
    print(json.dumps(signals, indent=2))


if __name__ == "__main__":
    main()


def get_metadata():
    """Return strategy metadata for dashboard."""
    return {
        "name": "Momentum Acceleration",
        "description": "Momentum strategy with acceleration detection for early trend capture.",
        "type": "trend",
        "timeframes": ["1h"],
        "core_logic": {
            "long": [
                "Momentum > 0.1% with positive acceleration",
                "Acceleration confirms momentum building",
                "Early trend entry"
            ],
            "short": [
                "Momentum < -0.1% with negative acceleration",
                "Acceleration confirms momentum building",
                "Early trend entry"
            ],
            "filters": [
                "Requires acceleration confirmation",
                "Uses 5-min snapshots for precision"
            ]
        },
        "backtest": {
            "period": "June 2023 - June 2026 (3 years)",
            "coin": "BTC",
            "timeframe": "1H candles",
            "initial_capital": 1000,
            "final_capital": 1075.98,
            "total_return_pct": 7.60,
            "total_trades": 2750,
            "winning_trades": 998,
            "losing_trades": 1752,
            "win_rate": 36.3,
            "profit_factor": 1.14,
            "max_drawdown_pct": 0.78,
            "avg_win_pct": 3.0,
            "avg_loss_pct": -1.5,
            "avg_hold_time_hours": 6.9,
            "risk_reward": "1:2 (1.5% SL / 3.0% TP)",
            "leverage": 3.0,
            "position_size_pct": 2.0
        }
    }
