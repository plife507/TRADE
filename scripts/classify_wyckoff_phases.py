"""
Classify Wyckoff market phases from real DuckDB candle data.

Reads 1h candles for BTC, ETH, SOL, LTC and classifies:
- Accumulation: low volatility, range-bound, bullish divergences
- Markup: clear uptrend, higher highs/higher lows
- Distribution: high volatility at top, range-bound after rally
- Markdown: clear downtrend, lower highs/lower lows

Output: docs/WYCKOFF_PHASES.md with date ranges per symbol per phase.

Usage:
    python scripts/classify_wyckoff_phases.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data" / "market_data_backtest.duckdb"
OUTPUT_PATH = ROOT / "docs" / "WYCKOFF_PHASES.md"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LTCUSDT"]


def load_1h_candles(db: duckdb.DuckDBPyConnection, symbol: str) -> dict:
    """Load 1h candle data for a symbol."""
    rows = db.execute("""
        SELECT timestamp, open, high, low, close, volume
        FROM ohlcv_live
        WHERE symbol = ? AND timeframe = '1h'
        ORDER BY timestamp
    """, [symbol]).fetchall()

    if not rows:
        return {}

    data = {
        "timestamp": [r[0] for r in rows],
        "open": np.array([float(r[1]) for r in rows]),
        "high": np.array([float(r[2]) for r in rows]),
        "low": np.array([float(r[3]) for r in rows]),
        "close": np.array([float(r[4]) for r in rows]),
        "volume": np.array([float(r[5]) for r in rows]),
    }
    return data


def compute_ema(data: np.ndarray, length: int) -> np.ndarray:
    """Compute EMA."""
    alpha = 2.0 / (length + 1)
    ema = np.empty_like(data)
    ema[0] = data[0]
    for i in range(1, len(data)):
        ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
    return ema


def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, length: int) -> np.ndarray:
    """Compute ATR."""
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))

    atr = np.empty(n)
    atr[:length] = np.nan
    atr[length - 1] = np.mean(tr[:length])
    alpha = 1.0 / length
    for i in range(length, n):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i - 1]
    return atr


def classify_phases(data: dict, window: int = 168) -> list[dict]:
    """Classify Wyckoff phases using rolling analysis.

    window: rolling window in hours (168 = 1 week)

    Returns list of {start, end, phase} dicts.
    """
    close = data["close"]
    high = data["high"]
    low = data["low"]
    timestamps = data["timestamp"]
    n = len(close)

    if n < 500:
        return []

    ema_50 = compute_ema(close, 50)
    ema_200 = compute_ema(close, 200)
    atr = compute_atr(high, low, close, 14)

    # Compute rolling metrics per bar
    phases = []
    for i in range(max(200, window), n):
        # Trend: EMA 50 vs 200
        ema_trend = 1 if ema_50[i] > ema_200[i] else -1

        # EMA slope (recent momentum)
        ema50_slope = (ema_50[i] - ema_50[i - 20]) / ema_50[i - 20] * 100

        # Price position relative to EMAs
        above_50 = close[i] > ema_50[i]
        above_200 = close[i] > ema_200[i]

        # Volatility: ATR as % of price
        atr_pct = atr[i] / close[i] * 100 if not np.isnan(atr[i]) else 1.0

        # Rolling high/low analysis (higher highs / lower lows)
        w_start = max(0, i - window)
        w_high = np.max(high[w_start:i + 1])
        w_low = np.min(low[w_start:i + 1])
        w_range_pct = (w_high - w_low) / w_low * 100

        # Recent trend: compare first half vs second half of window
        half = window // 2
        first_half_avg = np.mean(close[max(0, i - window):i - half])
        second_half_avg = np.mean(close[i - half:i + 1])
        trend_change_pct = (second_half_avg - first_half_avg) / first_half_avg * 100

        # Classify
        if ema_trend == 1 and ema50_slope > 0.5 and above_50 and above_200:
            phase = "markup"
        elif ema_trend == -1 and ema50_slope < -0.5 and not above_50 and not above_200:
            phase = "markdown"
        elif w_range_pct < 15 and abs(trend_change_pct) < 3:
            if ema_trend == -1 or (not above_200 and close[i] > w_low + 0.3 * (w_high - w_low)):
                phase = "accumulation"
            else:
                phase = "distribution"
        elif ema_trend == 1 and ema50_slope < 0.2 and w_range_pct < 20:
            phase = "distribution"
        elif ema_trend == -1 and ema50_slope > -0.2 and w_range_pct < 20:
            phase = "accumulation"
        elif trend_change_pct > 2:
            phase = "markup"
        elif trend_change_pct < -2:
            phase = "markdown"
        else:
            # Default based on EMA trend
            phase = "markup" if ema_trend == 1 else "markdown"

        phases.append({
            "timestamp": timestamps[i],
            "phase": phase,
        })

    # Consolidate into ranges (merge consecutive same-phase bars)
    if not phases:
        return []

    ranges = []
    current = {"start": phases[0]["timestamp"], "end": phases[0]["timestamp"], "phase": phases[0]["phase"]}

    for p in phases[1:]:
        if p["phase"] == current["phase"]:
            current["end"] = p["timestamp"]
        else:
            ranges.append(current)
            current = {"start": p["timestamp"], "end": p["timestamp"], "phase": p["phase"]}
    ranges.append(current)

    # Merge short ranges (< 3 days) into neighbors
    merged = []
    for r in ranges:
        duration = r["end"] - r["start"]
        if isinstance(duration, timedelta):
            days = duration.total_seconds() / 86400
        else:
            days = 0

        if days < 3 and merged:
            # Absorb into previous range
            merged[-1]["end"] = r["end"]
        else:
            merged.append(r)

    # Second pass: merge short ranges again
    final = []
    for r in merged:
        duration = r["end"] - r["start"]
        if isinstance(duration, timedelta):
            days = duration.total_seconds() / 86400
        else:
            days = 0

        if days < 5 and final:
            final[-1]["end"] = r["end"]
        else:
            final.append(r)

    return final


def select_best_ranges(ranges: list[dict]) -> dict[str, dict]:
    """Select the best (longest) range for each phase type."""
    best = {}
    for phase_type in ["accumulation", "markup", "distribution", "markdown"]:
        candidates = [r for r in ranges if r["phase"] == phase_type]
        if candidates:
            # Sort by duration, pick longest
            candidates.sort(key=lambda r: r["end"] - r["start"], reverse=True)
            best[phase_type] = candidates[0]
    return best


def format_date(dt) -> str:
    """Format datetime as YYYY-MM-DD."""
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d")
    return str(dt)[:10]


def main() -> None:
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    db = duckdb.connect(str(DB_PATH), read_only=True)

    results = {}
    for symbol in SYMBOLS:
        print(f"Processing {symbol}...")
        data = load_1h_candles(db, symbol)
        if not data:
            print(f"  No 1h data for {symbol}, skipping")
            results[symbol] = {}
            continue

        print(f"  {len(data['close'])} bars: {data['timestamp'][0]} to {data['timestamp'][-1]}")
        ranges = classify_phases(data)
        print(f"  {len(ranges)} phase ranges identified")

        for r in ranges:
            duration = r["end"] - r["start"]
            days = duration.total_seconds() / 86400 if isinstance(duration, timedelta) else 0
            if days >= 7:
                print(f"    {r['phase']:15s}: {format_date(r['start'])} to {format_date(r['end'])} ({days:.0f}d)")

        best = select_best_ranges(ranges)
        results[symbol] = best

    db.close()

    # Write output
    lines = [
        "# Wyckoff Phase Classification\n",
        "\n",
        "> Auto-generated by `scripts/classify_wyckoff_phases.py`\n",
        f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        "\n",
        "## Phase Windows for Real-Data Verification\n",
        "\n",
        "These date ranges identify the clearest Wyckoff phase for each symbol.\n",
        "Plays in `plays/real_verification/` use these windows for backtesting.\n",
        "\n",
    ]

    for symbol in SYMBOLS:
        lines.append(f"### {symbol}\n\n")
        best = results.get(symbol, {})
        if not best:
            lines.append("_No data available_\n\n")
            continue

        lines.append("| Phase | Start | End | Duration |\n")
        lines.append("|-------|-------|-----|----------|\n")
        for phase_type in ["accumulation", "markup", "distribution", "markdown"]:
            r = best.get(phase_type)
            if r:
                duration = r["end"] - r["start"]
                days = duration.total_seconds() / 86400 if isinstance(duration, timedelta) else 0
                lines.append(f"| {phase_type} | {format_date(r['start'])} | {format_date(r['end'])} | {days:.0f}d |\n")
            else:
                lines.append(f"| {phase_type} | - | - | - |\n")
        lines.append("\n")

    # Summary table for play assignment
    lines.append("## Play Assignment Summary\n\n")
    lines.append("| Play Range | Phase | Recommended Symbols | Date Window |\n")
    lines.append("|------------|-------|--------------------|-----------|\n")

    # For each phase, find all symbols that have it
    for phase_type, play_range in [
        ("accumulation", "RV_001-RV_015"),
        ("markup", "RV_016-RV_030"),
        ("distribution", "RV_031-RV_045"),
        ("markdown", "RV_046-RV_060"),
    ]:
        symbols_with_phase = []
        date_windows = []
        for symbol in SYMBOLS:
            best = results.get(symbol, {})
            r = best.get(phase_type)
            if r:
                symbols_with_phase.append(symbol)
                date_windows.append(f"{format_date(r['start'])} to {format_date(r['end'])}")

        syms_str = ", ".join(symbols_with_phase) if symbols_with_phase else "None"
        dates_str = "; ".join(date_windows) if date_windows else "-"
        lines.append(f"| {play_range} | {phase_type} | {syms_str} | {dates_str} |\n")

    lines.append("\n")

    # Write file
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="\n") as f:
        f.writelines(lines)

    print(f"\nOutput written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
