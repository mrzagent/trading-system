#!/usr/bin/env python3
"""
strategy_rsi.py â Mean-reversion strategy using RSI(14) with dual-timeframe confluence
Timeframe : 5-min candle gate (fires every 5-min candle close)

Signal logic (dual-TF):
  BUY  when RSI(15m) <= 35 (oversold on short term)
       Confidence boosted when RSI(1h) is also oversold or approaching oversold.
  SELL when RSI(15m) >= 65 (overbought on short term)
       Confidence boosted when RSI(1h) is also overbought or approaching overbought.
  HOLD otherwise

Timeframe approximation (5-min snapshot DB):
  15m RSI  = most recent row's stored RSI
  1h RSI   = RSI from ~12 rows ago (12 x 5min = 60min)

Confluence scoring:
  Both frames agree (strong)      â full confidence
  15m triggered, 1h approaching   â moderate confidence
  15m triggered, 1h neutral/opposite â base confidence only
"""
import json
from db import get_conn, fetch_recent, COINS, signal_envelope
from candle_gate import should_act, mark_acted

STRATEGY       = "rsi_mean_reversion"
CANDLE_MINUTES = 5       # 5-min gate â fires every candle close
BUY_THRESHOLD  = 35.0
SELL_THRESHOLD = 65.0
# 1h frame: how many 5-min rows back = 1h ago
TF_1H_ROWS     = 12
# Buffer for 1h frame: "approaching" oversold/overbought
BUY_APPROACH   = 45.0    # 1h RSI below this adds moderate bonus
SELL_APPROACH  = 55.0    # 1h RSI above this adds moderate bonus
# Fetch enough rows to cover TF_1H_ROWS + some buffer for avg
FETCH_LIMIT    = TF_1H_ROWS + 10


def get_rsi_1h(rows: list) -> float | None:
    """
    Approximate 1h RSI: average of the rows from TF_1H_ROWS back to TF_1H_ROWS+4.
    Averaging a small window reduces single-row noise.
    rows[-1] is newest, rows[0] is oldest.
    """
    start = -(TF_1H_ROWS + 4)
    end   = -TF_1H_ROWS if TF_1H_ROWS > 0 else None
    window = rows[start:end]
    vals = [float(r["rsi"]) for r in window if r.get("rsi") is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def confluence_score(action: str, rsi_15m: float, rsi_1h: float | None) -> float:
    """
    Returns a confluence multiplier [0.0, 1.0] based on how well 1h RSI confirms
    the 15m signal direction.
    """
    if rsi_1h is None:
        return 0.0  # no bonus â can't confirm

    if action == "BUY":
        if rsi_1h <= BUY_THRESHOLD:
            return 0.35   # strong: both frames oversold
        elif rsi_1h <= BUY_APPROACH:
            return 0.20   # moderate: 1h approaching oversold
        else:
            return 0.0    # no alignment
    elif action == "SELL":
        if rsi_1h >= SELL_THRESHOLD:
            return 0.35   # strong: both frames overbought
        elif rsi_1h >= SELL_APPROACH:
            return 0.20   # moderate: 1h approaching overbought
        else:
            return 0.0
    return 0.0


def analyse(coin: str, conn, candle_start, timeframe: str = "5min") -> dict:
    rows = fetch_recent(conn, coin, limit=FETCH_LIMIT, timeframe=timeframe)
    if not rows:
        return signal_envelope(STRATEGY, coin, "HOLD", 0.0, "no data")

    # rows[-1] is the most recent row (fetch_recent returns oldestânewest)
    latest   = rows[-1]
    rsi_15m  = float(latest["rsi"] or 50)
    price    = float(latest["price"])
    rsi_1h   = get_rsi_1h(rows)

    meta_base = {
        "rsi_15m":  rsi_15m,
        "rsi_1h":   rsi_1h,
        "price":    price,
        "candle":   candle_start.isoformat(),
    }

    if rsi_15m <= BUY_THRESHOLD:
        base_conf  = min((BUY_THRESHOLD - rsi_15m) / 10, 1.0) * 0.65
        conf_bonus = confluence_score("BUY", rsi_15m, rsi_1h)
        conf       = round(min(base_conf + conf_bonus, 1.0), 3)
        tf_label   = (
            "both TFs oversold" if rsi_1h and rsi_1h <= BUY_THRESHOLD else
            "1h approaching" if rsi_1h and rsi_1h <= BUY_APPROACH else
            "15m only"
        )
        return signal_envelope(
            STRATEGY, coin, "BUY", conf,
            f"RSI(15m) {rsi_15m:.1f} oversold â {tf_label} "
            f"(1h~{rsi_1h:.1f})" if rsi_1h else f"RSI(15m) {rsi_15m:.1f} oversold",
            {**meta_base, "confluence": tf_label},
        )

    if rsi_15m >= SELL_THRESHOLD:
        base_conf  = min((rsi_15m - SELL_THRESHOLD) / 10, 1.0) * 0.65
        conf_bonus = confluence_score("SELL", rsi_15m, rsi_1h)
        conf       = round(min(base_conf + conf_bonus, 1.0), 3)
        tf_label   = (
            "both TFs overbought" if rsi_1h and rsi_1h >= SELL_THRESHOLD else
            "1h approaching" if rsi_1h and rsi_1h >= SELL_APPROACH else
            "15m only"
        )
        return signal_envelope(
            STRATEGY, coin, "SELL", conf,
            f"RSI(15m) {rsi_15m:.1f} overbought â {tf_label} "
            f"(1h~{rsi_1h:.1f})" if rsi_1h else f"RSI(15m) {rsi_15m:.1f} overbought",
            {**meta_base, "confluence": tf_label},
        )

    # Neutral â slight directional lean, no trade signal
    distance = abs(rsi_15m - 50)
    lean = "BUY" if rsi_15m < 50 else "SELL"
    return signal_envelope(
        STRATEGY, coin, "HOLD", round(distance / 50 * 0.35, 3),
        f"RSI(15m) {rsi_15m:.1f} â neutral zone"
        + (f" | 1h~{rsi_1h:.1f}" if rsi_1h else ""),
        {**meta_base, "lean": lean},
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
        "name": "RSI Confluence",
        "description": "Dual-timeframe RSI strategy with 15m and 1h confluence scoring.",
        "type": "mean_reversion",
        "timeframes": ["15m", "1h"],
        "core_logic": {
            "long": [
                "RSI 15m < 35 (oversold)",
                "RSI 1h < 40 (oversold)",
                "Confluence score >= 0.7"
            ],
            "short": [
                "RSI 15m > 65 (overbought)",
                "RSI 1h > 60 (overbought)",
                "Confluence score >= 0.7"
            ],
            "filters": [
                "Dual timeframe confirmation required",
                "Minimum confidence threshold 70%"
            ]
        },
        "backtest": {
            "period": "March 2026 - June 2026",
            "coins": ["BTC", "ETH", "SOL"],
            "timeframe": "1H candles",
            "initial_capital": 1000,
            "final_capital": 152.04,
            "total_return_pct": -84.80,
            "total_trades": 1912,
            "winning_trades": 640,
            "losing_trades": 1272,
            "win_rate": 33.5,
            "profit_factor": 0.69,
            "max_drawdown_pct": 87.81,
            "avg_win": 1.53,
            "avg_loss": -1.11,
            "risk_per_trade_pct": 2.0,
            "stop_loss_pct": 5.0,
            "take_profit_pct": 10.0,
            "note": "High trade frequency led to overtrading and significant losses"
        }
    }
