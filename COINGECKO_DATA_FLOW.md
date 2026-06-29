# CoinGecko Data Flow - How Candles Are Built

**Date:** 2026-06-24

---

## Answer: YES - All timeframes are built from the same CoinGecko API data

The 1h and 4h candles are **NOT** fetched as native 1h/4h candles from CoinGecko. Instead, they're **aggregated from minute-level price data** that CoinGecko returns.

---

## How It Works

### 1. API Endpoint (Same for all timeframes)

```
GET /coins/{coin_id}/market_chart?vs_currency=usd&days={days}
```

This returns **minute-by-minute** price and volume data for the requested period.

### 2. Response Format

```json
{
  "prices": [
    [timestamp_ms, price],
    [1719225600000, 62463.00],
    [1719225660000, 62465.50],
    ...
  ],
  "total_volumes": [
    [timestamp_ms, volume],
    ...
  ]
}
```

### 3. Aggregation Logic (`fetch_candles()`)

The collector aggregates these minute-level points into OHLCV candles:

```python
bucket_ms = bucket_minutes * 60 * 1000  # e.g., 3600000 for 1h

for ts_ms, price in prices:
    bk = (ts_ms // bucket_ms) * bucket_ms  # Round to bucket start
    if bk not in buckets:
        # New candle: open = high = low = close = price
        buckets[bk] = {"t": bk, "o": price, "h": price, "l": price, "c": price, "v": 0.0}
    else:
        # Update existing candle
        b["h"] = max(b["h"], price)  # Track highest price
        b["l"] = min(b["l"], price)  # Track lowest price
        b["c"] = price                # Last price = close
```

---

## Timeframe Configuration

| Timeframe | Days Requested | Bucket Minutes | ~Candles | Source Data |
|-----------|----------------|----------------|----------|-------------|
| **5min** | 1 day | 5 | ~288 | 1-min points → 5-min buckets |
| **1h** | 7 days | 60 | ~168 | 1-min points → 60-min buckets |
| **4h** | 30 days | 240 | ~180 | 1-min points → 240-min buckets |

---

## Implications

### ✅ Pros
- **Consistent data source** - All timeframes come from the same API call
- **True OHLC** - We calculate actual high/low from all minute points in the bucket
- **No gaps** - Aggregation ensures continuous data

### ⚠️ Considerations
- **API granularity** - CoinGecko returns minute data, but very old data may be less granular
- **Volume accuracy** - Volume is summed across all minutes in the bucket
- **Not exchange-native** - These are CoinGecko's aggregated prices, not raw exchange candles

---

## Example: 1h Candle Construction

For a 1h candle at 13:00:

```
CoinGecko returns minute prices: [62450, 62455, 62460, 62458, 62462, ...] (60 points)

Our aggregation:
  Open  = first price in bucket  = 62450
  High  = max of all prices      = 62480
  Low   = min of all prices      = 62445
  Close = last price in bucket   = 62463
  Volume = sum of all volumes    = 123.45 BTC
```

---

## Verification

You can verify this by checking the raw data vs aggregated candles:

```python
# The collector stores raw_data JSON with the spot price
# But the OHLC comes from the aggregated candles, not a separate API call
```

---

## Summary

| Question | Answer |
|----------|--------|
| Are 1h/4h fetched separately? | **No** - aggregated from minute data |
| Is the OHLC accurate? | **Yes** - calculated from all minute points |
| Same API endpoint? | **Yes** - `/market_chart` for all timeframes |
| Different days parameter? | **Yes** - more days for higher timeframes |
