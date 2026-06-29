import os
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras
from decouple import config

DEFAULTS = {
    "dbname":   config("DB_NAME",      default="postgres"),
    "user":     config("DB_USER",      default="postgres"),
    "password": config("DB_PASSWORD",  default=""),
    "host":     config("DB_HOST",      default="localhost"),
    "port":     config("DB_PORT",      cast=int, default=5432),
}

# Coins tracked across all strategies
COINS = ["BTC", "ETH", "SOL"]


def get_conn():
    """Return a new psycopg2 connection using DEFAULTS."""
    return psycopg2.connect(**DEFAULTS)


_TF_TABLE = {
    "5min": "trading_prices",
    "1h":   "trading_prices_1h",
    "4h":   "trading_prices_4h",
}


def fetch_recent(conn, coin: str, limit: int = 150, timeframe: str = "5min"):
    """
    Fetch the most recent `limit` rows from the appropriate timeframe table.
    Returns a list of RealDictRow objects ordered oldest→newest.
    """
    table = _TF_TABLE.get(timeframe, "trading_prices")
    sql = f"""
        SELECT *
        FROM   {table}
        WHERE  coin = %s
        ORDER  BY captured_at DESC
        LIMIT  %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (coin, limit))
        rows = cur.fetchall()
    # Reverse so strategies see chronological order (oldest first)
    return list(reversed(rows))


def signal_envelope(strategy: str, coin: str, action: str,
                    confidence: float, reason: str,
                    extra: dict | None = None) -> dict:
    """
    Standard signal dict returned by every strategy's analyse() function.
    """
    return {
        "strategy":     strategy,
        "coin":         coin,
        "action":       action,          # "BUY" | "SELL" | "HOLD"
        "confidence":   float(confidence),
        "reason":       reason,
        "meta":         extra or {},
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def save_signal(conn, signal: dict, table: str = "strategy_signals") -> int:
    """
    Save a signal to the database.
    
    Args:
        conn: Database connection
        signal: Signal dict from signal_envelope()
        table: Target table name (default: strategy_signals)
    
    Returns:
        ID of the inserted row
    """
    import json
    
    sql = f"""
        INSERT INTO {table} (strategy, coin, action, confidence, reason, meta, generated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """
    
    with conn.cursor() as cur:
        cur.execute(sql, (
            signal['strategy'],
            signal['coin'],
            signal['action'],
            signal['confidence'],
            signal['reason'],
            json.dumps(signal.get('meta', {})),
            signal.get('generated_at', datetime.now(tz=timezone.utc).isoformat())
        ))
        row_id = cur.fetchone()[0]
    
    conn.commit()
    return row_id
