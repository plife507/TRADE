# TradingView Webhook Market Structure Verification

**Purpose**: Development tool to verify market structure detectors against TradingView's built-in functions.

**Status**: READY FOR IMPLEMENTATION
**Created**: 2026-01-06
**Scope**: Development/validation only - not production infrastructure

---

## Overview

A webhook-based verification system that captures TradingView's market structure outputs and compares them against our incremental detectors. Used during development to ensure our implementations match industry-standard calculations.

### Architecture

```
┌─────────────────────┐     POST /webhook/pivot     ┌──────────────────────┐
│    TradingView      │ ──────────────────────────► │   Flask Server       │
│  BYBIT:BTCUSDT.P    │      JSON alert data        │   (localhost:5000)   │
│  Pine Script Alert  │                             │                      │
└─────────────────────┘                             └──────────┬───────────┘
                                                               │
        ┌──────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────┐      ┌─────────────────────┐      ┌──────────────────┐
│  DuckDB Storage   │      │  Our Detector       │      │  Comparison      │
│  tv_pivots table  │ ◄──► │  swing.py           │ ───► │  Report          │
│                   │      │  (same OHLC data)   │      │  (match rate %)  │
└───────────────────┘      └─────────────────────┘      └──────────────────┘
```

### Data Flow

1. TradingView detects pivot using `ta.pivothigh(5,5)` / `ta.pivotlow(5,5)`
2. Pine Script sends JSON alert to webhook endpoint
3. Flask server stores in DuckDB with bar_index, price, timestamp
4. Comparison script runs our `IncrementalSwingDetector` on same OHLC data
5. Report shows match rate and any discrepancies

---

## Prerequisites

- [ ] TradingView account with webhook alerts (Pro/Pro+ recommended)
- [ ] 2FA enabled on TradingView (required for webhooks)
- [ ] ngrok installed for local development OR VPS with domain
- [ ] Python packages: `flask`, `duckdb` (already in project)

---

## Phase 1: Directory Structure

### Files to Create

```
scripts/
├── tradingview/
│   ├── README.md                    # Setup instructions
│   ├── pivot_webhook.pine           # Pine Script indicator
│   ├── smc_bos_choch.pine          # Future: BOS/CHoCH indicator
│   ├── smc_order_block.pine        # Future: Order Block indicator
│   └── smc_fvg.pine                # Future: FVG indicator
│
└── pivot_verification/
    ├── __init__.py
    ├── webhook_server.py            # Flask webhook receiver
    ├── compare_pivots.py            # Comparison logic
    ├── models.py                    # DuckDB schema
    ├── config.py                    # Configuration
    └── requirements.txt             # Dependencies
```

### Tasks

- [ ] Create `scripts/tradingview/` directory
- [ ] Create `scripts/pivot_verification/` directory
- [ ] Create `scripts/pivot_verification/__init__.py` (empty)

---

## Phase 2: Pine Script Indicator

### File: `scripts/tradingview/pivot_webhook.pine`

```pine
// This file is part of TRADE market structure verification
// Copy this code into TradingView Pine Editor and add to chart

//@version=5
indicator("TRADE Pivot Verification", overlay=true)

// ============================================================================
// CONFIGURATION - Must match IncrementalSwingDetector params
// ============================================================================
int leftBars = input.int(5, "Left Bars", minval=1, maxval=50)
int rightBars = input.int(5, "Right Bars", minval=1, maxval=50)
string webhookSecret = input.string("TRADE_VERIFY_SECRET", "Webhook Secret")

// ============================================================================
// PIVOT DETECTION - Using TradingView's built-in functions
// ============================================================================
float pivotHigh = ta.pivothigh(high, leftBars, rightBars)
float pivotLow = ta.pivotlow(low, leftBars, rightBars)

// ============================================================================
// WEBHOOK ALERTS - JSON format for Flask server
// ============================================================================

// Alert on pivot high detection
if not na(pivotHigh)
    // Bar index of the actual pivot (not confirmation bar)
    int pivotBarIndex = bar_index - rightBars

    // Build JSON message
    string msg = '{"secret":"' + webhookSecret + '",'
    msg := msg + '"type":"pivot_high",'
    msg := msg + '"symbol":"' + syminfo.ticker + '",'
    msg := msg + '"exchange":"' + syminfo.prefix + '",'
    msg := msg + '"timeframe":"' + timeframe.period + '",'
    msg := msg + '"bar_index":' + str.tostring(pivotBarIndex) + ','
    msg := msg + '"price":' + str.tostring(pivotHigh, "#.########") + ','
    msg := msg + '"timestamp":' + str.tostring(time) + ','
    msg := msg + '"confirm_bar":' + str.tostring(bar_index) + '}'

    alert(msg, alert.freq_all)

// Alert on pivot low detection
if not na(pivotLow)
    int pivotBarIndex = bar_index - rightBars

    string msg = '{"secret":"' + webhookSecret + '",'
    msg := msg + '"type":"pivot_low",'
    msg := msg + '"symbol":"' + syminfo.ticker + '",'
    msg := msg + '"exchange":"' + syminfo.prefix + '",'
    msg := msg + '"timeframe":"' + timeframe.period + '",'
    msg := msg + '"bar_index":' + str.tostring(pivotBarIndex) + ','
    msg := msg + '"price":' + str.tostring(pivotLow, "#.########") + ','
    msg := msg + '"timestamp":' + str.tostring(time) + ','
    msg := msg + '"confirm_bar":' + str.tostring(bar_index) + '}'

    alert(msg, alert.freq_all)

// ============================================================================
// VISUAL MARKERS - For manual verification on chart
// ============================================================================
plotshape(
    pivotHigh,
    title="Pivot High",
    location=location.abovebar,
    color=color.new(color.green, 0),
    style=shape.triangledown,
    size=size.small,
    offset=-rightBars,
    text="H"
)

plotshape(
    pivotLow,
    title="Pivot Low",
    location=location.belowbar,
    color=color.new(color.red, 0),
    style=shape.triangleup,
    size=size.small,
    offset=-rightBars,
    text="L"
)

// ============================================================================
// INFO TABLE - Display current settings
// ============================================================================
var table infoTable = table.new(position.top_right, 2, 4, bgcolor=color.new(color.black, 80))

if barstate.islast
    table.cell(infoTable, 0, 0, "TRADE Pivot Verify", text_color=color.white, text_size=size.small)
    table.cell(infoTable, 0, 1, "Left Bars:", text_color=color.gray, text_size=size.tiny)
    table.cell(infoTable, 1, 1, str.tostring(leftBars), text_color=color.white, text_size=size.tiny)
    table.cell(infoTable, 0, 2, "Right Bars:", text_color=color.gray, text_size=size.tiny)
    table.cell(infoTable, 1, 2, str.tostring(rightBars), text_color=color.white, text_size=size.tiny)
    table.cell(infoTable, 0, 3, "Symbol:", text_color=color.gray, text_size=size.tiny)
    table.cell(infoTable, 1, 3, syminfo.ticker, text_color=color.white, text_size=size.tiny)
```

### Tasks

- [ ] Create `scripts/tradingview/pivot_webhook.pine`
- [ ] Test in TradingView Pine Editor (syntax check)
- [ ] Add to BYBIT:BTCUSDT.P 1h chart
- [ ] Verify visual markers appear correctly

---

## Phase 3: Configuration

### File: `scripts/pivot_verification/config.py`

```python
"""
Configuration for TradingView webhook verification system.

Environment variables:
    TV_WEBHOOK_SECRET: Secret for validating webhook requests
    TV_WEBHOOK_DB_PATH: Path to DuckDB database file
    TV_WEBHOOK_PORT: Flask server port (default 5000)
"""

from pathlib import Path
import os

# Webhook authentication
WEBHOOK_SECRET = os.getenv("TV_WEBHOOK_SECRET", "TRADE_VERIFY_SECRET")

# Database configuration
DB_PATH = Path(os.getenv("TV_WEBHOOK_DB_PATH", "data/tv_verification.duckdb"))

# Server configuration
WEBHOOK_PORT = int(os.getenv("TV_WEBHOOK_PORT", "5000"))
WEBHOOK_HOST = os.getenv("TV_WEBHOOK_HOST", "0.0.0.0")

# Detector configuration - must match Pine Script settings
DEFAULT_LEFT_BARS = 5
DEFAULT_RIGHT_BARS = 5

# Supported symbols and timeframes
SUPPORTED_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
SUPPORTED_TIMEFRAMES = ["1", "5", "15", "60", "240", "D"]  # TradingView format

# Logging
LOG_LEVEL = os.getenv("TV_WEBHOOK_LOG_LEVEL", "INFO")
```

### Tasks

- [ ] Create `scripts/pivot_verification/config.py`

---

## Phase 4: Database Models

### File: `scripts/pivot_verification/models.py`

```python
"""
DuckDB schema for TradingView pivot verification.

Tables:
    tv_pivots: Raw pivot alerts from TradingView webhooks
    comparison_runs: Results of comparison script executions
    discrepancies: Individual pivot mismatches for analysis
"""

import duckdb
from pathlib import Path
from datetime import datetime

from .config import DB_PATH


def init_database() -> None:
    """
    Initialize DuckDB tables for pivot verification.

    Creates tables if they don't exist. Safe to call multiple times.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(DB_PATH))

    # Raw pivot data from TradingView webhooks
    con.execute("""
        CREATE TABLE IF NOT EXISTS tv_pivots (
            id INTEGER PRIMARY KEY,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            pivot_type VARCHAR NOT NULL,        -- 'pivot_high' or 'pivot_low'
            symbol VARCHAR NOT NULL,            -- e.g., 'BTCUSDT'
            exchange VARCHAR NOT NULL,          -- e.g., 'BYBIT'
            timeframe VARCHAR NOT NULL,         -- e.g., '60' for 1h
            bar_index INTEGER NOT NULL,         -- Bar index of pivot
            price DOUBLE NOT NULL,              -- Pivot price level
            tv_timestamp BIGINT NOT NULL,       -- TradingView bar timestamp (ms)
            confirm_bar INTEGER NOT NULL,       -- Bar when pivot was confirmed
            raw_json VARCHAR                    -- Original JSON for debugging
        )
    """)

    # Comparison run results
    con.execute("""
        CREATE TABLE IF NOT EXISTS comparison_runs (
            id INTEGER PRIMARY KEY,
            run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            symbol VARCHAR NOT NULL,
            timeframe VARCHAR NOT NULL,
            left_bars INTEGER NOT NULL,
            right_bars INTEGER NOT NULL,
            tv_high_count INTEGER NOT NULL,
            our_high_count INTEGER NOT NULL,
            matching_highs INTEGER NOT NULL,
            tv_low_count INTEGER NOT NULL,
            our_low_count INTEGER NOT NULL,
            matching_lows INTEGER NOT NULL,
            high_match_rate DOUBLE NOT NULL,    -- Percentage 0-100
            low_match_rate DOUBLE NOT NULL,
            overall_match_rate DOUBLE NOT NULL,
            notes VARCHAR
        )
    """)

    # Individual discrepancies for analysis
    con.execute("""
        CREATE TABLE IF NOT EXISTS discrepancies (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL,            -- FK to comparison_runs
            pivot_type VARCHAR NOT NULL,        -- 'pivot_high' or 'pivot_low'
            source VARCHAR NOT NULL,            -- 'tv_only' or 'our_only'
            bar_index INTEGER NOT NULL,
            price DOUBLE,
            notes VARCHAR,
            FOREIGN KEY (run_id) REFERENCES comparison_runs(id)
        )
    """)

    # Create indexes for common queries
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_tv_pivots_symbol_tf
        ON tv_pivots(symbol, timeframe)
    """)

    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_tv_pivots_bar_index
        ON tv_pivots(bar_index)
    """)

    con.close()
    print(f"Database initialized at {DB_PATH}")


def get_connection() -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection."""
    return duckdb.connect(str(DB_PATH))


def insert_pivot(
    pivot_type: str,
    symbol: str,
    exchange: str,
    timeframe: str,
    bar_index: int,
    price: float,
    tv_timestamp: int,
    confirm_bar: int,
    raw_json: str | None = None,
) -> int:
    """
    Insert a pivot record from TradingView webhook.

    Returns:
        The inserted row ID.
    """
    con = get_connection()
    result = con.execute("""
        INSERT INTO tv_pivots
        (pivot_type, symbol, exchange, timeframe, bar_index, price, tv_timestamp, confirm_bar, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
    """, [pivot_type, symbol, exchange, timeframe, bar_index, price, tv_timestamp, confirm_bar, raw_json])
    row_id = result.fetchone()[0]
    con.close()
    return row_id


def get_tv_pivots(
    symbol: str,
    timeframe: str,
    pivot_type: str | None = None,
    min_bar_index: int | None = None,
    max_bar_index: int | None = None,
) -> list[dict]:
    """
    Query TV pivots with optional filters.

    Returns:
        List of pivot dicts with keys: pivot_type, bar_index, price, tv_timestamp
    """
    con = get_connection()

    query = """
        SELECT pivot_type, bar_index, price, tv_timestamp
        FROM tv_pivots
        WHERE symbol = ? AND timeframe = ?
    """
    params = [symbol, timeframe]

    if pivot_type:
        query += " AND pivot_type = ?"
        params.append(pivot_type)

    if min_bar_index is not None:
        query += " AND bar_index >= ?"
        params.append(min_bar_index)

    if max_bar_index is not None:
        query += " AND bar_index <= ?"
        params.append(max_bar_index)

    query += " ORDER BY bar_index"

    result = con.execute(query, params).fetchall()
    con.close()

    return [
        {
            "pivot_type": row[0],
            "bar_index": row[1],
            "price": row[2],
            "tv_timestamp": row[3],
        }
        for row in result
    ]


def insert_comparison_run(
    symbol: str,
    timeframe: str,
    left_bars: int,
    right_bars: int,
    tv_high_count: int,
    our_high_count: int,
    matching_highs: int,
    tv_low_count: int,
    our_low_count: int,
    matching_lows: int,
    notes: str | None = None,
) -> int:
    """
    Record a comparison run result.

    Returns:
        The inserted run ID.
    """
    # Calculate match rates
    high_match_rate = (matching_highs / tv_high_count * 100) if tv_high_count > 0 else 100.0
    low_match_rate = (matching_lows / tv_low_count * 100) if tv_low_count > 0 else 100.0

    total_tv = tv_high_count + tv_low_count
    total_matching = matching_highs + matching_lows
    overall_match_rate = (total_matching / total_tv * 100) if total_tv > 0 else 100.0

    con = get_connection()
    result = con.execute("""
        INSERT INTO comparison_runs
        (symbol, timeframe, left_bars, right_bars,
         tv_high_count, our_high_count, matching_highs,
         tv_low_count, our_low_count, matching_lows,
         high_match_rate, low_match_rate, overall_match_rate, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
    """, [
        symbol, timeframe, left_bars, right_bars,
        tv_high_count, our_high_count, matching_highs,
        tv_low_count, our_low_count, matching_lows,
        high_match_rate, low_match_rate, overall_match_rate, notes
    ])
    run_id = result.fetchone()[0]
    con.close()
    return run_id


def insert_discrepancy(
    run_id: int,
    pivot_type: str,
    source: str,
    bar_index: int,
    price: float | None = None,
    notes: str | None = None,
) -> None:
    """Record an individual pivot discrepancy."""
    con = get_connection()
    con.execute("""
        INSERT INTO discrepancies (run_id, pivot_type, source, bar_index, price, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, [run_id, pivot_type, source, bar_index, price, notes])
    con.close()


def clear_tv_pivots(symbol: str | None = None, timeframe: str | None = None) -> int:
    """
    Clear TV pivot data. Use with caution.

    Returns:
        Number of rows deleted.
    """
    con = get_connection()

    if symbol and timeframe:
        result = con.execute(
            "DELETE FROM tv_pivots WHERE symbol = ? AND timeframe = ?",
            [symbol, timeframe]
        )
    elif symbol:
        result = con.execute("DELETE FROM tv_pivots WHERE symbol = ?", [symbol])
    else:
        result = con.execute("DELETE FROM tv_pivots")

    count = result.fetchone()[0] if result else 0
    con.close()
    return count


if __name__ == "__main__":
    # Initialize database when run directly
    init_database()
```

### Tasks

- [ ] Create `scripts/pivot_verification/models.py`
- [ ] Run `python scripts/pivot_verification/models.py` to init DB

---

## Phase 5: Flask Webhook Server

### File: `scripts/pivot_verification/webhook_server.py`

```python
"""
TradingView Pivot Webhook Receiver.

Receives pivot alerts from TradingView and stores them in DuckDB.

Usage:
    # Development with ngrok
    python scripts/pivot_verification/webhook_server.py
    ngrok http 5000

    # Production with gunicorn
    gunicorn -w 1 -b 0.0.0.0:5000 scripts.pivot_verification.webhook_server:app

TradingView Setup:
    1. Add pivot_webhook.pine indicator to BYBIT:BTCUSDT.P
    2. Create alert: "Any alert() function call"
    3. Webhook URL: https://your-ngrok-url.ngrok.io/webhook/pivot
    4. Enable 2FA on TradingView account
"""

from flask import Flask, request, jsonify
from datetime import datetime
import json
import logging

from .config import WEBHOOK_SECRET, WEBHOOK_HOST, WEBHOOK_PORT, LOG_LEVEL
from .models import init_database, insert_pivot

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)


@app.route("/webhook/pivot", methods=["POST"])
def receive_pivot():
    """
    Receive and store TradingView pivot alerts.

    Expected JSON format:
    {
        "secret": "TRADE_VERIFY_SECRET",
        "type": "pivot_high" | "pivot_low",
        "symbol": "BTCUSDT",
        "exchange": "BYBIT",
        "timeframe": "60",
        "bar_index": 12345,
        "price": 95000.5,
        "timestamp": 1704067200000,
        "confirm_bar": 12350
    }

    Returns:
        200: Success
        400: Invalid request
        401: Invalid secret
        500: Server error
    """
    try:
        # Parse JSON body
        data = request.json
        if not data:
            logger.warning("Empty request body")
            return jsonify({"error": "Empty request body"}), 400

        raw_json = json.dumps(data)

        # Validate secret
        if data.get("secret") != WEBHOOK_SECRET:
            logger.warning(f"Invalid secret from {request.remote_addr}")
            return jsonify({"error": "Invalid secret"}), 401

        # Validate required fields
        required = ["type", "symbol", "exchange", "timeframe", "bar_index", "price", "timestamp"]
        missing = [f for f in required if f not in data]
        if missing:
            logger.warning(f"Missing fields: {missing}")
            return jsonify({"error": f"Missing fields: {missing}"}), 400

        # Validate pivot type
        if data["type"] not in ("pivot_high", "pivot_low"):
            logger.warning(f"Invalid pivot type: {data['type']}")
            return jsonify({"error": f"Invalid type: {data['type']}"}), 400

        # Insert into database
        row_id = insert_pivot(
            pivot_type=data["type"],
            symbol=data["symbol"],
            exchange=data["exchange"],
            timeframe=data["timeframe"],
            bar_index=int(data["bar_index"]),
            price=float(data["price"]),
            tv_timestamp=int(data["timestamp"]),
            confirm_bar=int(data.get("confirm_bar", data["bar_index"])),
            raw_json=raw_json,
        )

        logger.info(
            f"Pivot {data['type']}: {data['symbol']} {data['timeframe']} "
            f"bar={data['bar_index']} price={data['price']:.2f} (id={row_id})"
        )

        return jsonify({"status": "ok", "id": row_id}), 200

    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return jsonify({"error": "Invalid JSON"}), 400

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
    }), 200


@app.route("/stats", methods=["GET"])
def stats():
    """
    Get pivot statistics.

    Query params:
        symbol: Filter by symbol (optional)
        timeframe: Filter by timeframe (optional)
    """
    from .models import get_connection

    symbol = request.args.get("symbol")
    timeframe = request.args.get("timeframe")

    con = get_connection()

    query = """
        SELECT
            symbol,
            timeframe,
            pivot_type,
            COUNT(*) as count,
            MIN(bar_index) as min_bar,
            MAX(bar_index) as max_bar
        FROM tv_pivots
    """

    params = []
    conditions = []

    if symbol:
        conditions.append("symbol = ?")
        params.append(symbol)
    if timeframe:
        conditions.append("timeframe = ?")
        params.append(timeframe)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " GROUP BY symbol, timeframe, pivot_type ORDER BY symbol, timeframe"

    result = con.execute(query, params).fetchall()
    con.close()

    return jsonify({
        "stats": [
            {
                "symbol": row[0],
                "timeframe": row[1],
                "pivot_type": row[2],
                "count": row[3],
                "min_bar": row[4],
                "max_bar": row[5],
            }
            for row in result
        ]
    }), 200


def main():
    """Run the webhook server."""
    # Initialize database
    init_database()

    logger.info(f"Starting webhook server on {WEBHOOK_HOST}:{WEBHOOK_PORT}")
    logger.info(f"Webhook endpoint: http://{WEBHOOK_HOST}:{WEBHOOK_PORT}/webhook/pivot")
    logger.info("Use ngrok to expose: ngrok http 5000")

    app.run(host=WEBHOOK_HOST, port=WEBHOOK_PORT, debug=True)


if __name__ == "__main__":
    main()
```

### Tasks

- [ ] Create `scripts/pivot_verification/webhook_server.py`
- [ ] Test locally: `python -m scripts.pivot_verification.webhook_server`
- [ ] Verify health endpoint: `curl http://localhost:5000/health`

---

## Phase 6: Comparison Script

### File: `scripts/pivot_verification/compare_pivots.py`

```python
"""
Compare TradingView pivots with our IncrementalSwingDetector.

Fetches OHLC data from DuckDB historical store, runs our detector,
and compares against TradingView webhook data.

Usage:
    python -m scripts.pivot_verification.compare_pivots --symbol BTCUSDT --timeframe 60

    # With custom detector params
    python -m scripts.pivot_verification.compare_pivots --symbol BTCUSDT --timeframe 60 --left 10 --right 10
"""

import argparse
from datetime import datetime
from typing import NamedTuple

from .config import DEFAULT_LEFT_BARS, DEFAULT_RIGHT_BARS
from .models import (
    get_tv_pivots,
    insert_comparison_run,
    insert_discrepancy,
    get_connection,
)

# Import from main codebase
import sys
sys.path.insert(0, str(__file__).replace("scripts/pivot_verification/compare_pivots.py", ""))

from src.backtest.incremental.detectors.swing import IncrementalSwingDetector
from src.backtest.incremental.base import BarData
from src.data.historical_data_store import HistoricalDataStore


class PivotRecord(NamedTuple):
    """A detected pivot point."""
    bar_index: int
    price: float
    confirmed_at: int


def run_our_detector(
    symbol: str,
    timeframe: str,
    left: int,
    right: int,
    min_bar: int | None = None,
    max_bar: int | None = None,
) -> tuple[list[PivotRecord], list[PivotRecord]]:
    """
    Run our IncrementalSwingDetector on historical data.

    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        timeframe: Timeframe in TradingView format (e.g., '60' for 1h)
        left: Left bars parameter
        right: Right bars parameter
        min_bar: Optional minimum bar index filter
        max_bar: Optional maximum bar index filter

    Returns:
        Tuple of (highs, lows) as lists of PivotRecord
    """
    # Convert TradingView timeframe to our format
    tf_map = {
        "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
        "60": "1h", "120": "2h", "240": "4h", "360": "6h", "480": "8h",
        "720": "12h", "D": "1d", "1D": "1d",
    }
    our_tf = tf_map.get(timeframe, timeframe)

    # Load historical data
    store = HistoricalDataStore()
    df = store.query_ohlcv(symbol, our_tf)

    if df.empty:
        print(f"No data found for {symbol} {our_tf}")
        return [], []

    # Initialize detector
    detector = IncrementalSwingDetector({"left": left, "right": right}, {})

    highs: list[PivotRecord] = []
    lows: list[PivotRecord] = []

    # Run through each bar
    for idx in range(len(df)):
        row = df.iloc[idx]

        bar = BarData(
            idx=idx,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0)),
            indicators={},
        )

        prev_high_idx = detector.high_idx
        prev_low_idx = detector.low_idx

        detector.update(idx, bar)

        # Check for new swing high
        if detector.high_idx != prev_high_idx and detector.high_idx >= 0:
            # Apply bar index filters if specified
            if min_bar is not None and detector.high_idx < min_bar:
                continue
            if max_bar is not None and detector.high_idx > max_bar:
                continue

            highs.append(PivotRecord(
                bar_index=detector.high_idx,
                price=detector.high_level,
                confirmed_at=idx,
            ))

        # Check for new swing low
        if detector.low_idx != prev_low_idx and detector.low_idx >= 0:
            if min_bar is not None and detector.low_idx < min_bar:
                continue
            if max_bar is not None and detector.low_idx > max_bar:
                continue

            lows.append(PivotRecord(
                bar_index=detector.low_idx,
                price=detector.low_level,
                confirmed_at=idx,
            ))

    return highs, lows


def compare_pivots(
    symbol: str,
    timeframe: str,
    left: int = DEFAULT_LEFT_BARS,
    right: int = DEFAULT_RIGHT_BARS,
    verbose: bool = True,
    save_results: bool = True,
) -> dict:
    """
    Compare TradingView pivots against our detector.

    Args:
        symbol: Trading pair
        timeframe: TradingView timeframe format
        left: Left bars parameter (must match Pine Script)
        right: Right bars parameter (must match Pine Script)
        verbose: Print detailed output
        save_results: Save results to database

    Returns:
        Comparison results dict
    """
    # Load TV pivots
    tv_highs_raw = get_tv_pivots(symbol, timeframe, "pivot_high")
    tv_lows_raw = get_tv_pivots(symbol, timeframe, "pivot_low")

    if not tv_highs_raw and not tv_lows_raw:
        print(f"No TradingView data found for {symbol} {timeframe}")
        print("Make sure webhook server is running and receiving alerts.")
        return {"error": "No TV data"}

    # Get bar index range from TV data
    all_tv_bars = [p["bar_index"] for p in tv_highs_raw + tv_lows_raw]
    min_bar = min(all_tv_bars) if all_tv_bars else None
    max_bar = max(all_tv_bars) if all_tv_bars else None

    if verbose:
        print(f"TradingView data range: bar {min_bar} to {max_bar}")

    # Run our detector
    our_highs, our_lows = run_our_detector(
        symbol, timeframe, left, right, min_bar, max_bar
    )

    # Convert to sets of bar indices for comparison
    tv_high_indices = {p["bar_index"] for p in tv_highs_raw}
    tv_low_indices = {p["bar_index"] for p in tv_lows_raw}
    our_high_indices = {p.bar_index for p in our_highs}
    our_low_indices = {p.bar_index for p in our_lows}

    # Calculate matches and discrepancies
    matching_highs = tv_high_indices & our_high_indices
    tv_only_highs = tv_high_indices - our_high_indices
    our_only_highs = our_high_indices - tv_high_indices

    matching_lows = tv_low_indices & our_low_indices
    tv_only_lows = tv_low_indices - our_low_indices
    our_only_lows = our_low_indices - tv_low_indices

    # Calculate match rates
    high_match_rate = len(matching_highs) / len(tv_high_indices) * 100 if tv_high_indices else 100.0
    low_match_rate = len(matching_lows) / len(tv_low_indices) * 100 if tv_low_indices else 100.0

    total_tv = len(tv_high_indices) + len(tv_low_indices)
    total_matching = len(matching_highs) + len(matching_lows)
    overall_match_rate = total_matching / total_tv * 100 if total_tv > 0 else 100.0

    # Print results
    if verbose:
        print()
        print("=" * 60)
        print(f"PIVOT COMPARISON: {symbol} {timeframe}")
        print(f"Detector params: left={left}, right={right}")
        print("=" * 60)
        print()
        print("SWING HIGHS:")
        print(f"  TradingView: {len(tv_high_indices)}")
        print(f"  Our detector: {len(our_high_indices)}")
        print(f"  Matching: {len(matching_highs)} ({high_match_rate:.1f}%)")
        if tv_only_highs:
            print(f"  TV-only: {sorted(tv_only_highs)[:10]}{'...' if len(tv_only_highs) > 10 else ''}")
        if our_only_highs:
            print(f"  Our-only: {sorted(our_only_highs)[:10]}{'...' if len(our_only_highs) > 10 else ''}")
        print()
        print("SWING LOWS:")
        print(f"  TradingView: {len(tv_low_indices)}")
        print(f"  Our detector: {len(our_low_indices)}")
        print(f"  Matching: {len(matching_lows)} ({low_match_rate:.1f}%)")
        if tv_only_lows:
            print(f"  TV-only: {sorted(tv_only_lows)[:10]}{'...' if len(tv_only_lows) > 10 else ''}")
        if our_only_lows:
            print(f"  Our-only: {sorted(our_only_lows)[:10]}{'...' if len(our_only_lows) > 10 else ''}")
        print()
        print("=" * 60)
        print(f"OVERALL MATCH RATE: {overall_match_rate:.1f}%")
        print("=" * 60)

        if overall_match_rate >= 95:
            print("✅ PASS - Match rate >= 95%")
        elif overall_match_rate >= 90:
            print("⚠️ WARNING - Match rate 90-95%")
        else:
            print("❌ FAIL - Match rate < 90%")

    # Save results to database
    run_id = None
    if save_results:
        run_id = insert_comparison_run(
            symbol=symbol,
            timeframe=timeframe,
            left_bars=left,
            right_bars=right,
            tv_high_count=len(tv_high_indices),
            our_high_count=len(our_high_indices),
            matching_highs=len(matching_highs),
            tv_low_count=len(tv_low_indices),
            our_low_count=len(our_low_indices),
            matching_lows=len(matching_lows),
        )

        # Record discrepancies
        for bar_idx in tv_only_highs:
            tv_pivot = next((p for p in tv_highs_raw if p["bar_index"] == bar_idx), None)
            insert_discrepancy(
                run_id=run_id,
                pivot_type="pivot_high",
                source="tv_only",
                bar_index=bar_idx,
                price=tv_pivot["price"] if tv_pivot else None,
            )

        for bar_idx in our_only_highs:
            our_pivot = next((p for p in our_highs if p.bar_index == bar_idx), None)
            insert_discrepancy(
                run_id=run_id,
                pivot_type="pivot_high",
                source="our_only",
                bar_index=bar_idx,
                price=our_pivot.price if our_pivot else None,
            )

        for bar_idx in tv_only_lows:
            tv_pivot = next((p for p in tv_lows_raw if p["bar_index"] == bar_idx), None)
            insert_discrepancy(
                run_id=run_id,
                pivot_type="pivot_low",
                source="tv_only",
                bar_index=bar_idx,
                price=tv_pivot["price"] if tv_pivot else None,
            )

        for bar_idx in our_only_lows:
            our_pivot = next((p for p in our_lows if p.bar_index == bar_idx), None)
            insert_discrepancy(
                run_id=run_id,
                pivot_type="pivot_low",
                source="our_only",
                bar_index=bar_idx,
                price=our_pivot.price if our_pivot else None,
            )

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "left_bars": left,
        "right_bars": right,
        "tv_high_count": len(tv_high_indices),
        "our_high_count": len(our_high_indices),
        "matching_highs": len(matching_highs),
        "high_match_rate": high_match_rate,
        "tv_low_count": len(tv_low_indices),
        "our_low_count": len(our_low_indices),
        "matching_lows": len(matching_lows),
        "low_match_rate": low_match_rate,
        "overall_match_rate": overall_match_rate,
        "tv_only_highs": sorted(tv_only_highs),
        "our_only_highs": sorted(our_only_highs),
        "tv_only_lows": sorted(tv_only_lows),
        "our_only_lows": sorted(our_only_lows),
        "run_id": run_id,
    }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Compare TradingView pivots with our IncrementalSwingDetector"
    )
    parser.add_argument(
        "--symbol", "-s",
        default="BTCUSDT",
        help="Trading pair (default: BTCUSDT)"
    )
    parser.add_argument(
        "--timeframe", "-t",
        default="60",
        help="Timeframe in TV format (default: 60 = 1h)"
    )
    parser.add_argument(
        "--left", "-l",
        type=int,
        default=DEFAULT_LEFT_BARS,
        help=f"Left bars parameter (default: {DEFAULT_LEFT_BARS})"
    )
    parser.add_argument(
        "--right", "-r",
        type=int,
        default=DEFAULT_RIGHT_BARS,
        help=f"Right bars parameter (default: {DEFAULT_RIGHT_BARS})"
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save results to database"
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Minimal output"
    )

    args = parser.parse_args()

    compare_pivots(
        symbol=args.symbol,
        timeframe=args.timeframe,
        left=args.left,
        right=args.right,
        verbose=not args.quiet,
        save_results=not args.no_save,
    )


if __name__ == "__main__":
    main()
```

### Tasks

- [ ] Create `scripts/pivot_verification/compare_pivots.py`
- [ ] Test with mock data
- [ ] Verify integration with HistoricalDataStore

---

## Phase 7: Requirements and README

### File: `scripts/pivot_verification/requirements.txt`

```
flask>=2.3.0
duckdb>=0.9.0
```

### File: `scripts/tradingview/README.md`

```markdown
# TradingView Market Structure Verification

Development tools for verifying TRADE market structure detectors against TradingView.

## Purpose

This is a **development-only** tool for validating our market structure algorithms.
It is NOT production infrastructure.

## Quick Start

### 1. Start Webhook Server

```bash
# Terminal 1: Start Flask server
python -m scripts.pivot_verification.webhook_server

# Terminal 2: Expose via ngrok (free account works)
ngrok http 5000
```

Copy the ngrok HTTPS URL (e.g., `https://abc123.ngrok.io`).

### 2. Configure TradingView

1. Open TradingView and go to BYBIT:BTCUSDT.P (1h timeframe)
2. Open Pine Editor and paste contents of `pivot_webhook.pine`
3. Click "Add to Chart"
4. Right-click indicator → "Add Alert..."
5. Condition: "Any alert() function call"
6. Webhook URL: `https://abc123.ngrok.io/webhook/pivot`
7. Enable alert

### 3. Wait for Data

Let the alert run for a few hours to collect pivot data. Check webhook server logs.

### 4. Run Comparison

```bash
python -m scripts.pivot_verification.compare_pivots --symbol BTCUSDT --timeframe 60
```

## Expected Output

```
============================================================
PIVOT COMPARISON: BTCUSDT 60
Detector params: left=5, right=5
============================================================

SWING HIGHS:
  TradingView: 127
  Our detector: 127
  Matching: 125 (98.4%)
  TV-only: [1043, 2891]

SWING LOWS:
  TradingView: 134
  Our detector: 134
  Matching: 134 (100.0%)

============================================================
OVERALL MATCH RATE: 99.2%
============================================================
✅ PASS - Match rate >= 95%
```

## Files

| File | Purpose |
|------|---------|
| `pivot_webhook.pine` | TradingView indicator with webhook alerts |
| `webhook_server.py` | Flask server to receive alerts |
| `compare_pivots.py` | Comparison script |
| `models.py` | DuckDB schema and queries |
| `config.py` | Configuration |

## Extending for ICT Structures

The same pattern applies to ICT structures:

1. Find/create TradingView indicator for the concept (OB, FVG, BOS, etc.)
2. Create Pine Script webhook alert
3. Create comparison script
4. Verify match rate >= 95%

## Troubleshooting

### No alerts received
- Check ngrok is running and URL is correct
- Verify TradingView 2FA is enabled (required for webhooks)
- Check webhook server logs for errors

### Match rate < 95%
- Verify left/right bars match between Pine Script and comparison
- Check for data gaps in historical data
- Investigate specific discrepancies in `discrepancies` table
```

### Tasks

- [ ] Create `scripts/pivot_verification/requirements.txt`
- [ ] Create `scripts/tradingview/README.md`

---

## Implementation Checklist

### Setup
- [ ] Create directory structure
- [ ] Install dependencies: `pip install flask duckdb`
- [ ] Install ngrok: `brew install ngrok` or download from ngrok.com

### Phase 1: Pine Script
- [ ] Create `pivot_webhook.pine`
- [ ] Test syntax in TradingView Pine Editor
- [ ] Add to BYBIT:BTCUSDT.P chart
- [ ] Verify visual markers appear

### Phase 2: Configuration
- [ ] Create `config.py`
- [ ] Set environment variables (optional)

### Phase 3: Database
- [ ] Create `models.py`
- [ ] Initialize database: `python -m scripts.pivot_verification.models`
- [ ] Verify tables created

### Phase 4: Webhook Server
- [ ] Create `webhook_server.py`
- [ ] Test locally: `python -m scripts.pivot_verification.webhook_server`
- [ ] Test health endpoint: `curl http://localhost:5000/health`
- [ ] Start ngrok: `ngrok http 5000`

### Phase 5: TradingView Alert
- [ ] Create alert in TradingView
- [ ] Set webhook URL to ngrok HTTPS URL
- [ ] Verify alerts appear in server logs

### Phase 6: Comparison
- [ ] Create `compare_pivots.py`
- [ ] Wait for ~100+ pivots to be collected
- [ ] Run comparison: `python -m scripts.pivot_verification.compare_pivots`
- [ ] Verify match rate >= 95%

### Phase 7: Documentation
- [ ] Create README.md
- [ ] Document any discrepancies found
- [ ] Archive results

---

## Future Extensions

Once pivot verification is complete, extend to ICT structures:

| Structure | Pine Script | Status |
|-----------|-------------|--------|
| Swing Pivots | `pivot_webhook.pine` | This doc |
| BOS/CHoCH | `smc_bos_choch.pine` | Planned |
| Order Blocks | `smc_order_block.pine` | Planned |
| Fair Value Gaps | `smc_fvg.pine` | Planned |
| Liquidity Zones | `smc_liquidity.pine` | Planned |

Each follows the same pattern:
1. Create Pine Script with webhook alert
2. Create comparison script
3. Verify match rate
4. Document discrepancies

---

## References

- [TradingView Webhook Configuration](https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/)
- [Pine Script v5 Reference](https://www.tradingview.com/pine-script-reference/v5/)
- [ngrok Documentation](https://ngrok.com/docs)
- ICT Market Structure Plan: `docs/todos/ICT_MARKET_STRUCTURE.md`
