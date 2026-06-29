#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
candle_collector.py — Multi-timeframe OHLCV candle collector for BTC, ETH, SOL.

Fetches market data from CoinGecko and writes into the appropriate timeframe table:
  5min  → trading_prices      (existing table, unchanged schema)
  1h    → trading_prices_1h   (new)
  4h    → trading_prices_4h   (new)

Usage:
    python candle_collector.py --timeframe 5min
    python candle_collector.py --timeframe 1h
    python candle_collector.py --timeframe 4h   [--no-db] [--quiet] [--json]

Scheduled tasks:
    TradingCollect5min  — every 5  min
    TradingCollect1h    — every 60 min
    TradingCollect4h    — every 240 min
"""

import urllib.request
import urllib.error
import json
import sys
import io
import argparse
import os
import time
from datetime import datetime, timezone

try:
    import psycopg2
    import psycopg2.extras
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ── Config ────────────────────────────────────────────────────────────────────
COINS = {
    "bitcoin":  "BTC",
    "ethereum": "ETH",
    "solana":   "SOL",
}
VS_CURRENCY   = "usd"
RSI_PERIOD    = 14
FVG_LOOKBACK  = 50

BASE              = "https://pro-api.coingecko.com/api/v3"
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "")

# ── Per-timeframe config ──────────────────────────────────────────────────────
TF_CONFIG = {
    "5min": {
        "table":          "trading_prices",
        "candle_days":    1,         # ~288 points at 5-min auto-granularity
        "bucket_minutes": 5,
        "rsi_period":     14,
        "momentum_look":  10,        # candles back for momentum
        "fvg_lookback":   50,
    },
    "1h": {
        "table":          "trading_prices_1h",
        "candle_days":    7,         # 7 days → ~168 hourly points
        "bucket_minutes": 60,
        "rsi_period":     14,
        "momentum_look":  10,
        "fvg_lookback":   50,
    },
    "4h": {
        "table":          "trading_prices_4h",
        "candle_days":    30,        # 30 days → ~180 4h points
        "bucket_minutes": 240,
        "rsi_period":     14,
        "momentum_look":  10,
        "fvg_lookback":   50,
    },
}

# ── DB Config ─────────────────────────────────────────────────────────────────
DB_HOST     = os.environ.get("PGHOST",     "localhost")
DB_PORT     = int(os.environ.get("PGPORT", "5432"))
DB_USER     = os.environ.get("PGUSER",     "postgres")
DB_PASSWORD = os.environ.get("PGPASSWORD", "1870506303979")
DB_NAME     = os.environ.get("PGDATABASE", "postgres")

CREATE_TABLE_TEMPLATE = """
CREATE TABLE IF NOT EXISTS {table} (
    id              SERIAL PRIMARY KEY,
    captured_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    coin            TEXT NOT NULL,
    price           NUMERIC(20,8),
    change_24h      NUMERIC(10,4),
    volume_24h      NUMERIC(20,2),
    volume_candle   NUMERIC(20,2),
    market_cap      NUMERIC(20,2),
    rsi             NUMERIC(6,2),
    momentum        NUMERIC(10,4),
    fvg_count       INT,
    fvg_data        JSONB,
    alert_triggered BOOLEAN DEFAULT FALSE,
    raw_data        JSONB
);
"""

MIGRATE_5MIN_SQL = """
ALTER TABLE trading_prices
ADD COLUMN IF NOT EXISTS volume_5m NUMERIC(20,2);
"""

INSERT_ROW_TEMPLATE = """
INSERT INTO {table}
    (captured_at, coin, price, change_24h, volume_24h, volume_candle, market_cap,
     rsi, momentum, fvg_count, fvg_data, alert_triggered, raw_data,
     high_price, low_price, open_price)
VALUES
    (%(captured_at)s, %(coin)s, %(price)s, %(change_24h)s, %(volume_24h)s,
     %(volume_candle)s, %(market_cap)s, %(rsi)s, %(momentum)s, %(fvg_count)s,
     %(fvg_data)s, %(alert_triggered)s, %(raw_data)s,
     %(high_price)s, %(low_price)s, %(open_price)s)
"""

# ── HTTP helper ───────────────────────────────────────────────────────────────
def fetch(url: str, max_retries: int = 4, backoff: float = 2.0) -> dict:
    last_exc = None
    headers = {"User-Agent": "Mozilla/5.0"}
    if COINGECKO_API_KEY:
        headers["x-cg-pro-api-key"] = COINGECKO_API_KEY
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            last_exc = e
            if e.code == 429:
                retry_after = int(e.headers.get("Retry-After", backoff * (2 ** attempt)))
                time.sleep(min(retry_after, 60))
            elif e.code in (500, 502, 503, 504):
                time.sleep(backoff * (2 ** attempt))
            else:
                raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_exc = e
            time.sleep(backoff * (2 ** attempt))
    raise RuntimeError(f"fetch failed after {max_retries} attempts: {last_exc}") from last_exc

# ── Spot prices ───────────────────────────────────────────────────────────────
def fetch_spot() -> dict:
    ids = ",".join(COINS.keys())
    url = (
        f"{BASE}/simple/price?ids={ids}"
        f"&vs_currencies={VS_CURRENCY}"
        f"&include_24hr_change=true"
        f"&include_24hr_vol=true"
        f"&include_market_cap=true"
    )
    return fetch(url)

# ── OHLCV candles ─────────────────────────────────────────────────────────────
def fetch_candles(coin_id: str, days: int, bucket_minutes: int) -> list[dict]:
    """
    Fetch /market_chart and aggregate into OHLCV candles of bucket_minutes width.
    For 1h/4h we request more days to get enough history for indicators.
    """
    url = (f"{BASE}/coins/{coin_id}/market_chart"
           f"?vs_currency={VS_CURRENCY}&days={days}")
    raw = fetch(url)
    prices  = raw.get("prices", [])
    volumes = raw.get("total_volumes", [])
    if not prices:
        return []

    bucket_ms = bucket_minutes * 60 * 1000
    buckets: dict[int, dict] = {}

    for ts_ms, price in prices:
        bk = (ts_ms // bucket_ms) * bucket_ms
        if bk not in buckets:
            buckets[bk] = {"t": bk, "o": price, "h": price, "l": price, "c": price, "v": 0.0}
        else:
            b = buckets[bk]
            b["h"] = max(b["h"], price)
            b["l"] = min(b["l"], price)
            b["c"] = price

    for ts_ms, vol in volumes:
        bk = (ts_ms // bucket_ms) * bucket_ms
        if bk in buckets:
            buckets[bk]["v"] += vol

    return sorted(buckets.values(), key=lambda x: x["t"])

# ── Indicators ────────────────────────────────────────────────────────────────
def compute_rsi(candles: list[dict], period: int = RSI_PERIOD) -> float | None:
    closes = [c["c"] for c in candles]
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def compute_momentum(candles: list[dict], lookback: int = 10) -> float | None:
    closes = [c["c"] for c in candles]
    if len(closes) < lookback + 1:
        return None
    old = closes[-(lookback + 1)]
    now = closes[-1]
    if old == 0:
        return None
    return round((now - old) / old * 100, 4)

def find_fvgs(candles: list[dict], lookback: int = FVG_LOOKBACK) -> list[dict]:
    recent = candles[-lookback:] if len(candles) >= lookback else candles
    fvgs = []
    for i in range(1, len(recent) - 1):
        prev, curr, nxt = recent[i - 1], recent[i], recent[i + 1]
        if prev["h"] < nxt["l"]:
            fvgs.append({
                "type":      "bullish",
                "bottom":    prev["h"],
                "top":       nxt["l"],
                "midpoint":  round((prev["h"] + nxt["l"]) / 2, 2),
                "formed_at": datetime.fromtimestamp(curr["t"] / 1000, tz=timezone.utc)
                              .strftime("%Y-%m-%d %H:%M UTC"),
            })
        elif prev["l"] > nxt["h"]:
            fvgs.append({
                "type":      "bearish",
                "top":       prev["l"],
                "bottom":    nxt["h"],
                "midpoint":  round((prev["l"] + nxt["h"]) / 2, 2),
                "formed_at": datetime.fromtimestamp(curr["t"] / 1000, tz=timezone.utc)
                              .strftime("%Y-%m-%d %H:%M UTC"),
            })
    return fvgs[-5:]

# ── DB helpers ────────────────────────────────────────────────────────────────
def get_db_conn():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT,
        user=DB_USER, password=DB_PASSWORD,
        dbname=DB_NAME, connect_timeout=10,
    )

def ensure_table(conn, table: str, is_5min: bool = False):
    with conn.cursor() as cur:
        cur.execute(CREATE_TABLE_TEMPLATE.format(table=table))
        if is_5min:
            # Legacy: keep volume_5m column alias on original table
            cur.execute("""
                ALTER TABLE trading_prices
                ADD COLUMN IF NOT EXISTS volume_5m NUMERIC(20,2);
            """)
            # Add OHLC columns for 5min strategies (Momentum Scalper, etc.)
            cur.execute("""
                ALTER TABLE trading_prices
                ADD COLUMN IF NOT EXISTS high_price NUMERIC(20,8),
                ADD COLUMN IF NOT EXISTS low_price NUMERIC(20,8),
                ADD COLUMN IF NOT EXISTS open_price NUMERIC(20,8);
            """)
    conn.commit()

def write_rows(conn, table: str, rows: list[dict], is_5min: bool = False):
    sql = INSERT_ROW_TEMPLATE.format(table=table)
    with conn.cursor() as cur:
        for row in rows:
            if is_5min:
                # 5min table now has OHLC columns - include them
                row_5m = dict(row)
                sql_5m = """
                    INSERT INTO trading_prices
                        (captured_at, coin, price, change_24h, volume_24h, volume_5m,
                         market_cap, rsi, momentum, fvg_count, fvg_data,
                         alert_triggered, raw_data, high_price, low_price, open_price)
                    VALUES
                        (%(captured_at)s, %(coin)s, %(price)s, %(change_24h)s,
                         %(volume_24h)s, %(volume_candle)s, %(market_cap)s,
                         %(rsi)s, %(momentum)s, %(fvg_count)s, %(fvg_data)s,
                         %(alert_triggered)s, %(raw_data)s,
                         %(high_price)s, %(low_price)s, %(open_price)s)
                """
                cur.execute(sql_5m, row_5m)
            else:
                cur.execute(sql, row)
    conn.commit()

# ── Core collection ───────────────────────────────────────────────────────────
def collect(timeframe: str, quiet: bool = False, no_db: bool = False,
            as_json: bool = False, alert_threshold: float = 5.0) -> dict:
    cfg = TF_CONFIG[timeframe]
    table = cfg["table"]
    now_utc = datetime.now(tz=timezone.utc)

    try:
        spot = fetch_spot()
    except Exception as e:
        msg = f"ERROR fetching spot prices: {e}"
        print(msg, file=sys.stderr)
        sys.exit(1)

    results = {}
    for coin_id, ticker in COINS.items():
        s = spot[coin_id]
        price  = s.get(VS_CURRENCY, 0.0)
        change = s.get(f"{VS_CURRENCY}_24h_change", 0.0)
        vol    = s.get(f"{VS_CURRENCY}_24h_vol", 0.0)
        mcap   = s.get(f"{VS_CURRENCY}_market_cap", 0.0)
        alert  = abs(change) >= alert_threshold

        try:
            candles      = fetch_candles(coin_id, cfg["candle_days"], cfg["bucket_minutes"])
            rsi          = compute_rsi(candles, cfg["rsi_period"])
            momentum     = compute_momentum(candles, cfg["momentum_look"])
            fvgs         = [] if quiet else find_fvgs(candles, cfg["fvg_lookback"])
            vol_candle   = round(candles[-1]["v"], 2) if candles else None
            # OHLC from latest candle (close = price from candle data)
            last_candle = candles[-1] if candles else None
            high_price  = round(last_candle["h"], 8) if last_candle else None
            low_price   = round(last_candle["l"], 8) if last_candle else None
            open_price  = round(last_candle["o"], 8) if last_candle else None
        except Exception as e:
            print(f"  [warn] {ticker} indicator fetch failed: {e}", file=sys.stderr)
            candles, rsi, momentum, fvgs, vol_candle = [], None, None, [], None
            high_price, low_price, open_price = None, None, None

        results[ticker] = {
            "coin_id":       coin_id,
            "ticker":        ticker,
            "price":         price,
            "change_24h":    round(change, 4),
            "volume_24h":    vol,
            "volume_candle": vol_candle,
            "market_cap":    mcap,
            "rsi":           rsi,
            "momentum":      momentum,
            "fvg_count":     len(fvgs),
            "fvg_data":      fvgs,
            "alert":         alert,
            "high_price":    high_price,
            "low_price":     low_price,
            "open_price":    open_price,
        }

    db_ok = False
    db_error = None
    if not no_db:
        if not HAS_PSYCOPG2:
            db_error = "psycopg2 not installed"
            print(f"[warn] {db_error}", file=sys.stderr)
        else:
            try:
                conn = get_db_conn()
                is_5m = (timeframe == "5min")
                ensure_table(conn, table, is_5min=is_5m)

                db_rows = []
                for ticker, r in results.items():
                    db_rows.append({
                        "captured_at":   now_utc,
                        "coin":          ticker,
                        "price":         r["price"],
                        "change_24h":    r["change_24h"],
                        "volume_24h":    r["volume_24h"],
                        "volume_candle": r["volume_candle"],
                        "market_cap":    r["market_cap"],
                        "rsi":           r["rsi"],
                        "momentum":      r["momentum"],
                        "fvg_count":     r["fvg_count"],
                        "fvg_data":      json.dumps(r["fvg_data"]),
                        "alert_triggered": r["alert"],
                        "raw_data":      json.dumps({"spot": spot.get(r["coin_id"], {})}),
                        "high_price":    r.get("high_price"),
                        "low_price":     r.get("low_price"),
                        "open_price":    r.get("open_price"),
                    })

                write_rows(conn, table, db_rows, is_5min=is_5m)
                conn.close()
                db_ok = True

                if not quiet:
                    print(f"[{timeframe}] Wrote {len(db_rows)} rows to {table}", file=sys.stderr)
            except Exception as e:
                db_error = str(e)
                print(f"[warn] DB write failed: {e}", file=sys.stderr)

    if as_json:
        output = {
            "timeframe":    timeframe,
            "table":        table,
            "timestamp":    now_utc.isoformat(),
            "db_written":   db_ok,
            "db_error":     db_error,
            "coins":        {
                ticker: {k: v for k, v in r.items() if k not in ("coin_id",)}
                for ticker, r in results.items()
            },
        }
        print(json.dumps(output, indent=2, default=str))

    return {"db_ok": db_ok, "db_error": db_error, "rows": len(results)}


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Multi-timeframe candle collector")
    parser.add_argument("--timeframe", choices=["5min", "1h", "4h"], required=True,
                        help="Timeframe to collect: 5min | 1h | 4h")
    parser.add_argument("--quiet",  action="store_true", help="Skip FVG (faster)")
    parser.add_argument("--json",   action="store_true", help="Output JSON to stdout")
    parser.add_argument("--no-db",  action="store_true", help="Dry run — skip DB write")
    parser.add_argument("--alert-threshold", type=float, default=5.0)
    args = parser.parse_args()

    result = collect(
        timeframe=args.timeframe,
        quiet=args.quiet,
        no_db=args.no_db,
        as_json=args.json,
        alert_threshold=args.alert_threshold,
    )

    if not args.json and not args.quiet:
        status = "OK" if result["db_ok"] else f"FAILED: {result['db_error']}"
        print(f"[{args.timeframe}] DB: {status} | {result['rows']} coins", file=sys.stderr)

    sys.exit(0 if result["db_ok"] or args.no_db else 1)


if __name__ == "__main__":
    main()
