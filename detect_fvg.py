#!/usr/bin/env python3
"""
detect_fvg.py — Build pseudo-candles from trading_prices history,
                 detect Fair Value Gaps, and update the latest row's
                 fvg_data / fvg_count columns for each coin.

Candle resolution : groups price rows into 10-minute buckets
FVG lookback      : last 60 candles (~10 hours of 10-min data)
Runs              : before Virgil (strategy_fvg.py) each cycle

Usage:
    python detect_fvg.py [--dry-run] [--verbose]
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta

import psycopg2
import psycopg2.extras

# ── Config ────────────────────────────────────────────────────────────────────
DB_HOST     = "localhost"
DB_PORT     = 5432
DB_USER     = "postgres"
DB_PASSWORD = "1870506303979"
DB_NAME     = "postgres"

COINS        = ["BTC", "ETH", "SOL"]
BUCKET_MIN   = 10          # minutes per candle bucket
LOOKBACK_H   = 12          # hours of history to pull
MAX_FVGS     = 10          # keep N most recent FVGs
MIN_CANDLES  = 10          # need at least this many candles to detect anything


# ── DB ────────────────────────────────────────────────────────────────────────
def get_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD,
        dbname=DB_NAME, connect_timeout=10,
    )


# ── Candle builder ────────────────────────────────────────────────────────────
def build_candles(rows: list[dict]) -> list[dict]:
    """
    Group price rows into BUCKET_MIN-minute OHLC candles.
    Each row has: captured_at (datetime), price (float), volume_24h (float)
    Returns list of {t, o, h, l, c, v} sorted oldest-first.
    """
    if not rows:
        return []

    buckets: dict[int, list[float]] = {}
    for r in rows:
        ts = r["captured_at"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        # Floor to BUCKET_MIN boundary
        epoch = int(ts.timestamp())
        bucket_key = (epoch // (BUCKET_MIN * 60)) * (BUCKET_MIN * 60)
        buckets.setdefault(bucket_key, []).append(float(r["price"]))

    candles = []
    for bucket_ts in sorted(buckets):
        prices = buckets[bucket_ts]
        candles.append({
            "t": bucket_ts * 1000,   # ms, consistent with CoinGecko format
            "o": prices[0],
            "h": max(prices),
            "l": min(prices),
            "c": prices[-1],
        })
    return candles


# ── FVG detection ─────────────────────────────────────────────────────────────
def find_fvgs(candles: list[dict], max_fvgs: int = MAX_FVGS) -> list[dict]:
    """
    Detect Fair Value Gaps (3-candle pattern):
      Bullish FVG : candle[i-1].high < candle[i+1].low   → demand gap below price
      Bearish FVG : candle[i-1].low  > candle[i+1].high  → supply gap above price

    Only keep unfilled FVGs (current price has not closed the gap).
    Returns up to max_fvgs most recent.
    """
    fvgs = []
    for i in range(1, len(candles) - 1):
        prev, curr, nxt = candles[i - 1], candles[i], candles[i + 1]

        if prev["h"] < nxt["l"]:
            fvgs.append({
                "type":     "bullish",
                "bottom":   round(prev["h"], 6),
                "top":      round(nxt["l"], 6),
                "midpoint": round((prev["h"] + nxt["l"]) / 2, 6),
                "formed_at": datetime.fromtimestamp(
                    curr["t"] / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M UTC"),
                "bucket_ts": curr["t"],
            })
        elif prev["l"] > nxt["h"]:
            fvgs.append({
                "type":     "bearish",
                "top":      round(prev["l"], 6),
                "bottom":   round(nxt["h"], 6),
                "midpoint": round((prev["l"] + nxt["h"]) / 2, 6),
                "formed_at": datetime.fromtimestamp(
                    curr["t"] / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M UTC"),
                "bucket_ts": curr["t"],
            })

    # Most recent first, cap at max_fvgs
    fvgs.sort(key=lambda x: x["bucket_ts"], reverse=True)
    for f in fvgs:
        del f["bucket_ts"]   # internal field, don't persist
    return fvgs[:max_fvgs]


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Detect FVGs from trading_prices history")
    parser.add_argument("--dry-run",  action="store_true", help="Detect but don't write to DB")
    parser.add_argument("--verbose",  action="store_true", help="Print detected FVGs")
    args = parser.parse_args()

    conn = get_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    since = datetime.now(tz=timezone.utc) - timedelta(hours=LOOKBACK_H)
    results = {}

    for coin in COINS:
        # Pull recent rows
        cur.execute(
            """
            SELECT captured_at, price, volume_24h
            FROM   trading_prices
            WHERE  coin = %s AND captured_at >= %s
            ORDER  BY captured_at ASC
            """,
            (coin, since),
        )
        rows = list(cur.fetchall())

        if len(rows) < MIN_CANDLES:
            print(f"[{coin}] not enough rows ({len(rows)}) — need {MIN_CANDLES}, skipping", file=sys.stderr)
            results[coin] = []
            continue

        candles = build_candles(rows)
        fvgs    = find_fvgs(candles)
        results[coin] = fvgs

        if args.verbose:
            print(f"\n[{coin}] {len(candles)} candles -> {len(fvgs)} FVGs")
            for f in fvgs:
                print(f"  {f['type']:7s}  bot={f['bottom']:>12,.4f}  top={f['top']:>12,.4f}"
                      f"  mid={f['midpoint']:>12,.4f}  @ {f['formed_at']}")

        if not args.dry_run:
            # Update the latest row for this coin
            cur.execute(
                """
                UPDATE trading_prices
                SET    fvg_data  = %s,
                       fvg_count = %s
                WHERE  id = (
                    SELECT id FROM trading_prices
                    WHERE  coin = %s
                    ORDER  BY captured_at DESC
                    LIMIT  1
                )
                """,
                (json.dumps(fvgs), len(fvgs), coin),
            )

    if not args.dry_run:
        conn.commit()
        print(f"[detect_fvg] updated: " +
              ", ".join(f"{c}={len(results[c])} FVGs" for c in COINS))
    else:
        print(f"[detect_fvg] dry-run: " +
              ", ".join(f"{c}={len(results[c])} FVGs" for c in COINS))

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
