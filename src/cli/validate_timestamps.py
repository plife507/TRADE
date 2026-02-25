"""
G17: Timestamp Correctness — validation gate for timestamp invariants.

Catches regressions in the timestamp pipeline that would silently corrupt
prices, fills, and PnL. Runs in <5s, covering:

1. Conversion roundtrips (datetime <-> epoch_ms <-> numpy)
2. Timezone-aware handling (strip to UTC-naive)
3. Bybit timestamp parsing edge cases
4. FeedStore timestamp integrity
5. numpy/pandas interop boundaries
6. BarRecord construction paths
7. Artifact serialization (Trade, EquityPoint)
8. Static analysis for banned patterns
9. Multi-timeframe alignment
10. DST / calendar edge cases
11. Live candle conversion (KlineData -> Candle, close-time formula)
12. TimeRange roundtrip (datetime -> ms -> Bybit params -> datetime)
13. Order/Position REST integration (parse_bybit_ts -> dataclass fields)
14. DuckDB tz-aware normalization (fetch returns aware, must strip to naive)
15. WS staleness pattern (time.time() interval math)
16. Sim exchange timestamp flow (bar timestamp -> Order -> Fill -> Trade)
17-22. Extended checks (storage, TimeRange internals, to_dict, DataFrame, self-test, guards)
23. Runtime guards (__post_init__ tz-naive assertions on key dataclasses)
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from src.cli.validate import GateResult

# Type alias for category test functions
_CategoryFn = Callable[[], tuple[int, list[str]]]


# ── Helpers ──────────────────────────────────────────────────────────


def _run_category(
    name: str,
    fn: _CategoryFn,
) -> tuple[int, list[str]]:
    """Run a category function, catching exceptions as failures."""
    try:
        return fn()
    except Exception as e:
        return 0, [f"{name}: EXCEPTION: {type(e).__name__}: {e}"]


# ── Category 1: Conversion Roundtrip Parity ──────────────────────────

def _cat_conversion_roundtrip() -> tuple[int, list[str]]:
    from src.utils.datetime_utils import datetime_to_epoch_ms
    from src.backtest.runtime.feed_store import (
        _datetime_to_epoch_ms,
        _np_dt64_to_epoch_ms,
        _np_dt64_to_datetime,
    )

    checks = 0
    failures: list[str] = []

    # 1a: Naive datetime roundtrip
    dt = datetime(2025, 6, 15, 12, 30, 0)
    ms = _datetime_to_epoch_ms(dt)
    rt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)
    checks += 1
    if rt != dt:
        failures.append(f"1a: roundtrip failed: {dt} -> {ms} -> {rt}")

    # 1b: Microsecond truncation to ms
    dt_us = datetime(2025, 6, 15, 12, 30, 0, 123456)
    ms_us = _datetime_to_epoch_ms(dt_us)
    rt_us = datetime.fromtimestamp(ms_us / 1000, tz=timezone.utc).replace(tzinfo=None)
    checks += 1
    if rt_us.microsecond != 123000:
        failures.append(f"1b: microsecond truncation: expected 123000, got {rt_us.microsecond}")

    # 1c: Epoch zero
    dt_zero = datetime(1970, 1, 1, 0, 0, 0)
    ms_zero = _datetime_to_epoch_ms(dt_zero)
    checks += 1
    if ms_zero != 0:
        failures.append(f"1c: epoch zero: expected 0, got {ms_zero}")

    # 1d: 32-bit safe (year 2040)
    dt_2040 = datetime(2040, 1, 1, 0, 0, 0)
    ms_2040 = _datetime_to_epoch_ms(dt_2040)
    rt_2040 = datetime.fromtimestamp(ms_2040 / 1000, tz=timezone.utc).replace(tzinfo=None)
    checks += 1
    if rt_2040 != dt_2040:
        failures.append(f"1d: 2040 roundtrip failed: {dt_2040} -> {ms_2040} -> {rt_2040}")

    # 1e: datetime_utils vs feed_store produce identical output
    dt_cmp = datetime(2025, 3, 15, 8, 45, 30)
    ms_utils = datetime_to_epoch_ms(dt_cmp)
    ms_feed = _datetime_to_epoch_ms(dt_cmp)
    checks += 1
    if ms_utils != ms_feed:
        failures.append(f"1e: utils={ms_utils} vs feed_store={ms_feed}")

    # 1f: numpy datetime64 roundtrip
    np_ts = np.datetime64("2025-06-15T12:30:00", "ms")
    np_ms = _np_dt64_to_epoch_ms(np_ts)
    np_dt = _np_dt64_to_datetime(np_ts)
    np_ms2 = _datetime_to_epoch_ms(np_dt)
    checks += 1
    if np_ms != np_ms2:
        failures.append(f"1f: np roundtrip: {np_ms} != {np_ms2}")

    return checks, failures


# ── Category 2: Timezone-Aware Handling ──────────────────────────────

def _cat_timezone_handling() -> tuple[int, list[str]]:
    from src.utils.datetime_utils import (
        datetime_to_epoch_ms,
        normalize_datetime,
        normalize_timestamp,
    )

    checks = 0
    failures: list[str] = []

    # 2a: UTC-aware vs naive produce same epoch ms
    dt_naive = datetime(2025, 1, 1, 0, 0, 0)
    dt_aware = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    checks += 1
    if datetime_to_epoch_ms(dt_naive) != datetime_to_epoch_ms(dt_aware):
        failures.append("2a: UTC-aware vs naive epoch mismatch")

    # 2b: +05:00 aware matches equivalent UTC naive
    tz_plus5 = timezone(timedelta(hours=5))
    dt_plus5 = datetime(2025, 1, 1, 5, 0, 0, tzinfo=tz_plus5)  # == 00:00 UTC
    dt_utc = datetime(2025, 1, 1, 0, 0, 0)
    checks += 1
    if datetime_to_epoch_ms(dt_plus5) != datetime_to_epoch_ms(dt_utc):
        failures.append(f"2b: +05:00 mismatch: {datetime_to_epoch_ms(dt_plus5)} vs {datetime_to_epoch_ms(dt_utc)}")

    # 2c: +05:00 aware -> normalize_datetime() -> naive UTC
    result, err = normalize_datetime(dt_plus5)
    checks += 1
    if err or result is None or result.tzinfo is not None or result != dt_utc:
        failures.append(f"2c: normalize_datetime(+05:00): err={err}, result={result}")

    # 2d: ISO "Z" string -> normalize_datetime() -> naive, no tzinfo
    result_z, err_z = normalize_datetime("2025-01-01T00:00:00Z")
    checks += 1
    if err_z or result_z is None or result_z.tzinfo is not None:
        failures.append(f"2d: 'Z' string: err={err_z}, tzinfo={result_z.tzinfo if result_z else 'None'}")

    # 2e: ISO +05:00 string -> normalize_datetime() -> 2025-01-01 00:00:00
    result_off, err_off = normalize_datetime("2025-01-01T05:00:00+05:00")
    checks += 1
    if err_off or result_off != datetime(2025, 1, 1, 0, 0, 0):
        failures.append(f"2e: +05:00 string: err={err_off}, result={result_off}")

    # 2f: tz-aware -> normalize_timestamp() -> naive UTC
    ts_aware = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    ts_norm = normalize_timestamp(ts_aware)
    checks += 1
    assert ts_norm is not None  # input is not None
    if ts_norm.tzinfo is not None:
        failures.append(f"2f: normalize_timestamp returned tz-aware: {ts_norm.tzinfo}")

    return checks, failures


# ── Category 3: Bybit Timestamp Parsing ──────────────────────────────

def _cat_bybit_parsing() -> tuple[int, list[str]]:
    from src.utils.datetime_utils import parse_bybit_ts

    checks = 0
    failures: list[str] = []

    # 3a: Normal ms string
    dt_3a = parse_bybit_ts("1684738540559")
    expected_3a = datetime.fromtimestamp(1684738540559 / 1000, tz=timezone.utc).replace(tzinfo=None)
    checks += 1
    if dt_3a != expected_3a:
        failures.append(f"3a: expected {expected_3a}, got {dt_3a}")

    # 3b: Epoch zero
    dt_3b = parse_bybit_ts("0")
    checks += 1
    if dt_3b != datetime(1970, 1, 1, 0, 0, 0):
        failures.append(f"3b: epoch zero: expected 1970-01-01, got {dt_3b}")

    # 3c: None input
    checks += 1
    if parse_bybit_ts(None) is not None:
        failures.append("3c: None should return None")

    # 3d: Empty string
    checks += 1
    if parse_bybit_ts("") is not None:
        failures.append("3d: empty string should return None")

    # 3e: Invalid string
    checks += 1
    if parse_bybit_ts("not_a_number") is not None:
        failures.append("3e: invalid string should return None")

    # 3f: Result is tz-naive
    dt_3f = parse_bybit_ts("1684738540559")
    checks += 1
    if dt_3f is not None and dt_3f.tzinfo is not None:
        failures.append(f"3f: parse_bybit_ts returned tz-aware: {dt_3f.tzinfo}")

    # 3g: Whitespace tolerance
    dt_3g = parse_bybit_ts("  1684738540559  ")
    checks += 1
    if dt_3g != expected_3a:
        # parse_bybit_ts may not strip — check if it returns None
        # (whitespace tolerance is a nice-to-have, not critical)
        if dt_3g is None:
            failures.append("3g: whitespace not handled (returned None)")
        else:
            failures.append(f"3g: whitespace: expected {expected_3a}, got {dt_3g}")

    return checks, failures


# ── Category 4: FeedStore Timestamp Integrity ────────────────────────

def _cat_feedstore_integrity() -> tuple[int, list[str]]:
    from src.backtest.runtime.feed_store import FeedStore

    checks = 0
    failures: list[str] = []

    # Build synthetic 10-bar 15m DataFrame
    base = datetime(2025, 1, 1, 14, 0, 0)
    rows = []
    for i in range(10):
        ts_open = base + timedelta(minutes=15 * i)
        ts_close = ts_open + timedelta(minutes=15)
        rows.append({
            "timestamp": ts_open,
            "ts_close": ts_close,
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.5 + i,
            "volume": 1000.0,
        })
    df = pd.DataFrame(rows)
    fs = FeedStore.from_dataframe(df, "15m", "BTCUSDT")

    # 4a: ts_close == ts_open + 15m for all bars
    checks += 1
    for i in range(fs.length):
        ts_o = fs.get_ts_open_datetime(i)
        ts_c = fs.get_ts_close_datetime(i)
        expected_close = ts_o + timedelta(minutes=15)
        if ts_c != expected_close:
            failures.append(f"4a: bar {i}: ts_close={ts_c} != ts_open+15m={expected_close}")
            break

    # 4b: get_idx_at_ts_close roundtrip
    checks += 1
    for i in range(fs.length):
        ts_c = fs.get_ts_close_datetime(i)
        idx = fs.get_idx_at_ts_close(ts_c)
        if idx != i:
            failures.append(f"4b: bar {i}: get_idx_at_ts_close returned {idx}")
            break

    # 4c: ts_close is UTC-naive
    ts_c0 = fs.get_ts_close_datetime(0)
    checks += 1
    if ts_c0.tzinfo is not None:
        failures.append(f"4c: ts_close[0].tzinfo={ts_c0.tzinfo}")

    # 4d: get_last_closed_idx_at_or_before(exact_close_5) == 5
    ts_c5 = fs.get_ts_close_datetime(5)
    idx_5 = fs.get_last_closed_idx_at_or_before(ts_c5)
    checks += 1
    if idx_5 != 5:
        failures.append(f"4d: exact close at bar 5: expected 5, got {idx_5}")

    # 4e: Binary search between bar 3 and 4 close -> returns 3
    ts_c3 = fs.get_ts_close_datetime(3)
    ts_between = ts_c3 + timedelta(seconds=30)  # 30s after bar 3 close
    idx_between = fs.get_last_closed_idx_at_or_before(ts_between)
    checks += 1
    if idx_between != 3:
        failures.append(f"4e: between bar 3/4: expected 3, got {idx_between}")

    # 4f: Query before all bars -> None
    ts_before = base - timedelta(hours=1)
    idx_before = fs.get_last_closed_idx_at_or_before(ts_before)
    checks += 1
    if idx_before is not None:
        failures.append(f"4f: before all bars: expected None, got {idx_before}")

    return checks, failures


# ── Category 5: numpy/pandas Interop ────────────────────────────────

def _cat_numpy_pandas_interop() -> tuple[int, list[str]]:
    from src.utils.datetime_utils import datetime_to_epoch_ms, normalize_timestamp
    from src.backtest.runtime.feed_store import (
        _datetime_to_epoch_ms,
        _np_dt64_to_epoch_ms,
        _np_dt64_to_datetime,
    )

    checks = 0
    failures: list[str] = []

    # 5a: np.datetime64 -> epoch_ms -> datetime roundtrip
    np_ts = np.datetime64("2025-03-15T10:30:00", "ms")
    np_ms = _np_dt64_to_epoch_ms(np_ts)
    np_dt = _np_dt64_to_datetime(np_ts)
    rt_ms = _datetime_to_epoch_ms(np_dt)
    checks += 1
    if np_ms != rt_ms:
        failures.append(f"5a: np roundtrip: {np_ms} != {rt_ms}")

    # 5b: pd.Timestamp -> datetime -> epoch_ms (both utils)
    pd_ts = pd.Timestamp("2025-03-15T10:30:00")
    py_dt: datetime = pd_ts.to_pydatetime()  # type: ignore[assignment]
    ms_utils = datetime_to_epoch_ms(py_dt)
    ms_feed = _datetime_to_epoch_ms(py_dt)
    checks += 1
    if ms_utils != ms_feed:
        failures.append(f"5b: pd.Timestamp: utils={ms_utils} vs feed={ms_feed}")

    # 5c: tz-aware pd.Timestamp -> normalize_timestamp() -> naive UTC
    pd_aware = pd.Timestamp("2025-03-15T10:30:00", tz=timezone.utc)
    py_aware: datetime = pd_aware.to_pydatetime()  # type: ignore[assignment]  # NaTType excluded at runtime
    py_naive = normalize_timestamp(py_aware)
    checks += 1
    assert py_naive is not None  # input is not None
    if py_naive.tzinfo is not None:
        failures.append(f"5c: tz-aware pd.Timestamp not stripped: {py_naive.tzinfo}")

    # 5d: np.datetime64 with nanosecond resolution truncates to ms
    np_ns = np.datetime64("2025-03-15T10:30:00.123456789", "ns")
    np_ns_ms = _np_dt64_to_epoch_ms(np_ns)
    # Should truncate ns to ms: .123456789 -> .123
    expected_ms_part = 123
    actual_ms_part = np_ns_ms % 1000
    checks += 1
    if actual_ms_part != expected_ms_part:
        failures.append(f"5d: ns truncation: expected ms_part={expected_ms_part}, got {actual_ms_part}")

    return checks, failures


# ── Category 6: BarRecord Timestamp Handling ─────────────────────────

def _cat_barrecord_handling() -> tuple[int, list[str]]:
    from src.data.realtime_models import BarRecord, KlineData

    checks = 0
    failures: list[str] = []

    # 6a: from_kline_data with known epoch ms
    kline = KlineData(
        symbol="BTCUSDT",
        interval="15",
        start_time=1684738540559,
        open=27000.0, high=27100.0, low=26900.0,
        close=27050.0, volume=100.0, turnover=2700000.0,
    )
    bar = BarRecord.from_kline_data(kline)
    expected_dt = datetime.fromtimestamp(1684738540559 / 1000, tz=timezone.utc).replace(tzinfo=None)
    checks += 1
    if bar.timestamp != expected_dt:
        failures.append(f"6a: from_kline_data: expected {expected_dt}, got {bar.timestamp}")

    # 6b: from_df_row with tz-aware timestamp -> stripped to UTC-naive
    aware_ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    row_aware = {
        "timestamp": aware_ts,
        "open": 100.0, "high": 101.0, "low": 99.0,
        "close": 100.5, "volume": 1000.0,
    }
    bar_aware = BarRecord.from_df_row(row_aware)
    checks += 1
    if bar_aware.timestamp.tzinfo is not None:
        failures.append(f"6b: from_df_row tz-aware not stripped: {bar_aware.timestamp.tzinfo}")

    # 6c: from_df_row with string timestamp
    row_str = {
        "timestamp": "2025-06-15 12:00:00",
        "open": 100.0, "high": 101.0, "low": 99.0,
        "close": 100.5, "volume": 1000.0,
    }
    bar_str = BarRecord.from_df_row(row_str)
    checks += 1
    if bar_str.timestamp != datetime(2025, 6, 15, 12, 0, 0):
        failures.append(f"6c: from_df_row string: expected 2025-06-15 12:00:00, got {bar_str.timestamp}")

    # 6d: from_kline_data with start_time=0 -> epoch origin
    kline_zero = KlineData(
        symbol="BTCUSDT", interval="15", start_time=0,
        open=100.0, high=101.0, low=99.0,
        close=100.5, volume=100.0, turnover=10000.0,
    )
    bar_zero = BarRecord.from_kline_data(kline_zero)
    checks += 1
    if bar_zero.timestamp != datetime(1970, 1, 1, 0, 0, 0):
        failures.append(f"6d: start_time=0: expected 1970-01-01, got {bar_zero.timestamp}")

    return checks, failures


# ── Category 7: Artifact Serialization Roundtrip ─────────────────────

def _cat_artifact_serialization() -> tuple[int, list[str]]:
    from src.backtest.types import Trade, EquityPoint

    checks = 0
    failures: list[str] = []

    # 7a: Trade.to_dict() entry_time has no tz suffix
    trade = Trade(
        trade_id="test-001",
        symbol="BTCUSDT",
        side="long",
        entry_time=datetime(2025, 6, 15, 12, 0, 0),
        entry_price=27000.0,
        entry_size=0.001,
        entry_size_usdt=27.0,
    )
    d = trade.to_dict()
    entry_str = d["entry_time"]
    checks += 1
    if entry_str.endswith("Z") or "+00:00" in entry_str or "+" in entry_str:
        failures.append(f"7a: entry_time has tz suffix: {entry_str}")

    # 7b: EquityPoint.to_dict() timestamp is clean ISO
    ep = EquityPoint(
        timestamp=datetime(2025, 6, 15, 12, 0, 0),
        equity=10000.0,
    )
    ep_d = ep.to_dict()
    ts_str = ep_d["timestamp"]
    checks += 1
    if ts_str.endswith("Z") or "+00:00" in ts_str:
        failures.append(f"7b: EquityPoint timestamp has tz suffix: {ts_str}")

    # 7c: Naive datetime .isoformat() has no tz suffix
    dt_naive = datetime(2025, 6, 15, 12, 30, 45)
    iso = dt_naive.isoformat()
    checks += 1
    if "Z" in iso or "+" in iso:
        failures.append(f"7c: naive isoformat has tz: {iso}")

    # 7d: Millisecond precision in .isoformat() when microsecond set
    dt_ms = datetime(2025, 6, 15, 12, 30, 45, 123000)
    iso_ms = dt_ms.isoformat()
    checks += 1
    if "123" not in iso_ms:
        failures.append(f"7d: isoformat missing ms: {iso_ms}")

    # 7e: Trade.to_dict() exit_time=None -> None (not "None")
    checks += 1
    if d["exit_time"] is not None:
        failures.append(f"7e: exit_time should be None, got {d['exit_time']!r}")

    return checks, failures


# ── Category 8: Static Analysis / Codebase Scan ─────────────────────

def _cat_static_analysis() -> tuple[int, list[str]]:
    """Scan src/ for banned timestamp patterns."""

    checks = 0
    failures: list[str] = []

    src_dir = Path("src")
    if not src_dir.exists():
        return 0, []

    # Exempt files that contain canonical implementations or test patterns
    exempt_stems = {"datetime_utils", "feed_store", "time_range", "validate_timestamps"}

    # Build patterns that avoid self-matching (same technique as G16)
    _utcnow = "utcnow"
    _fromts = "fromtimestamp"
    _dtnow = "datetime.now"

    patterns: list[tuple[re.Pattern[str], str | None]] = [
        # A: datetime.utcnow() — deprecated in Python 3.12
        (re.compile(rf"datetime\.{_utcnow}\s*\("), "use utc_now() from datetime_utils"),
        # B: .timestamp() * 1000 — local-time bug on naive datetimes
        (re.compile(r"\.timestamp\(\)\s*\*\s*1000"), "use datetime_to_epoch_ms()"),
        # C: datetime.fromtimestamp(x) without tz= — assumes local time
        (re.compile(rf"datetime\.{_fromts}\s*\([^)]*\)"), None),  # post-filter for tz=
        # D: datetime.now() bare — use utc_now()
        (re.compile(rf"{_dtnow}\s*\(\s*\)"), "use utc_now() from datetime_utils"),
    ]

    for py_file in sorted(src_dir.rglob("*.py")):
        checks += 1

        # Skip exempt files
        if py_file.stem in exempt_stems:
            continue

        try:
            text = py_file.read_text(encoding="utf-8")
        except Exception:
            continue

        lines = text.splitlines()
        for line_num, line in enumerate(lines, 1):
            stripped = line.lstrip()
            # Skip comments
            if stripped.startswith("#"):
                continue

            # Pattern A: datetime.utcnow()
            if patterns[0][0].search(line):
                failures.append(
                    f"{py_file}:{line_num}: datetime.utcnow() — {patterns[0][1]}"
                )

            # Pattern B: .timestamp() * 1000
            if patterns[1][0].search(line):
                failures.append(
                    f"{py_file}:{line_num}: .timestamp() * 1000 — {patterns[1][1]}"
                )

            # Pattern C: datetime.fromtimestamp() without tz=
            # Check full line for tz= since nested parens break regex matching.
            # Also check the next line for multi-line calls.
            m_c = patterns[2][0].search(line)
            if m_c:
                # Look at current + next 2 lines for tz=
                context = line
                for offset in range(1, 3):
                    if line_num - 1 + offset < len(lines):
                        context += " " + lines[line_num - 1 + offset]
                if "tz=" not in context:
                    failures.append(
                        f"{py_file}:{line_num}: datetime.fromtimestamp() without tz= — add tz=timezone.utc"
                    )

            # Pattern D: datetime.now() bare
            if patterns[3][0].search(line):
                failures.append(
                    f"{py_file}:{line_num}: datetime.now() — {patterns[3][1]}"
                )

    return checks, failures


def _cat_static_analysis_warnings() -> tuple[int, list[str]]:
    """Scan for tz-aware patterns that must have guards.

    Pattern E: .fromisoformat() must have .replace(tzinfo=None) or normalize_*
    guard nearby. In Python 3.11+, fromisoformat returns tz-aware for inputs
    with +00:00 or Z suffix.

    Pattern F: pd.to_datetime(utc=True) creates tz-aware Series/Index — must
    have .tz_localize(None) downstream.

    All sites were hardened — this gate now FAILS on unguarded new usage.
    """
    src_dir = Path("src")
    if not src_dir.exists():
        return 0, []

    # indicator_vendor exempt: pandas_ta.vwap() requires tz-aware DatetimeIndex
    # for session boundary detection. The tz-aware scope is contained within
    # that function and doesn't leak into FeedStore.
    exempt_stems = {
        "datetime_utils", "feed_store", "time_range", "validate_timestamps",
        "indicator_vendor",
    }

    _fromiso = "fromisoformat"
    pat_fromisoformat = re.compile(rf"\.{_fromiso}\(")
    _pd_todatetime = "pd.to_datetime"
    pat_pd_utc = re.compile(rf"{_pd_todatetime}\(")

    checks = 0
    # Warnings tracked in checks count but NOT in failures
    # (so the gate passes but reports the count)
    warnings: list[str] = []

    for py_file in sorted(src_dir.rglob("*.py")):
        if py_file.stem in exempt_stems:
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except Exception:
            continue

        lines = text.splitlines()
        for line_num, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue

            # Pattern E: .fromisoformat() without tz guard
            if pat_fromisoformat.search(line):
                checks += 1
                guard_context = line
                for offset in range(1, 3):
                    if line_num - 1 + offset < len(lines):
                        guard_context += " " + lines[line_num - 1 + offset]
                has_guard = (
                    "replace(tzinfo" in guard_context
                    or "normalize_datetime" in guard_context
                    or "normalize_timestamp" in guard_context
                )
                if not has_guard:
                    warnings.append(
                        f"{py_file}:{line_num}: .fromisoformat() without tz guard"
                    )

            # Pattern F: pd.to_datetime(utc=True) creates tz-aware
            if pat_pd_utc.search(line) and "utc=True" in line:
                checks += 1
                guard_context_f = text[max(0, text.find(line)):text.find(line) + 500]
                has_strip = (
                    "tz_localize(None)" in guard_context_f
                    or "tz_convert" in guard_context_f
                    or ".replace(tzinfo" in guard_context_f
                )
                if not has_strip:
                    warnings.append(
                        f"{py_file}:{line_num}: pd.to_datetime(utc=True) unguarded"
                    )

    # All sites hardened — return warnings as failures to catch regressions
    return checks, warnings


# ── Category 9: Multi-Timeframe Alignment ───────────────────────────

def _cat_multitf_alignment() -> tuple[int, list[str]]:
    from src.backtest.runtime.feed_store import FeedStore

    checks = 0
    failures: list[str] = []

    # Build a 60-bar 1m FeedStore starting at 14:00
    base = datetime(2025, 1, 1, 14, 0, 0)
    rows = []
    for i in range(60):
        ts_open = base + timedelta(minutes=i)
        ts_close = ts_open + timedelta(minutes=1)
        rows.append({
            "timestamp": ts_open,
            "ts_close": ts_close,
            "open": 100.0, "high": 101.0, "low": 99.0,
            "close": 100.5, "volume": 1000.0,
        })
    df = pd.DataFrame(rows)
    fs_1m = FeedStore.from_dataframe(df, "1m", "BTCUSDT")

    # 9a: 15m bar 14:00-14:15 -> 1m indices [0, 14]
    exec_open_a = datetime(2025, 1, 1, 14, 0, 0)
    exec_close_a = datetime(2025, 1, 1, 14, 15, 0)
    start_a, end_a = fs_1m.get_1m_indices_for_exec(0, 15, exec_open_a, exec_close_a)
    checks += 1
    if start_a != 0 or end_a != 14:
        failures.append(f"9a: 15m 14:00-14:15: expected (0,14), got ({start_a},{end_a})")

    # 9b: 15m bar 14:15-14:30 -> 1m indices [15, 29]
    exec_open_b = datetime(2025, 1, 1, 14, 15, 0)
    exec_close_b = datetime(2025, 1, 1, 14, 30, 0)
    start_b, end_b = fs_1m.get_1m_indices_for_exec(1, 15, exec_open_b, exec_close_b)
    checks += 1
    if start_b != 15 or end_b != 29:
        failures.append(f"9b: 15m 14:15-14:30: expected (15,29), got ({start_b},{end_b})")

    # 9c: 1h bar 14:00-15:00 -> 1m indices [0, 59]
    exec_open_c = datetime(2025, 1, 1, 14, 0, 0)
    exec_close_c = datetime(2025, 1, 1, 15, 0, 0)
    start_c, end_c = fs_1m.get_1m_indices_for_exec(0, 60, exec_open_c, exec_close_c)
    checks += 1
    if start_c != 0 or end_c != 59:
        failures.append(f"9c: 1h 14:00-15:00: expected (0,59), got ({start_c},{end_c})")

    # 9d: 1m bar 14 close == 14:15
    ts_c14 = fs_1m.get_ts_close_datetime(14)
    expected_c14 = datetime(2025, 1, 1, 14, 15, 0)
    checks += 1
    if ts_c14 != expected_c14:
        failures.append(f"9d: bar 14 close: expected {expected_c14}, got {ts_c14}")

    return checks, failures


# ── Category 10: DST / Edge Cases ───────────────────────────────────

def _cat_dst_edge_cases() -> tuple[int, list[str]]:
    from src.backtest.runtime.feed_store import _datetime_to_epoch_ms

    checks = 0
    failures: list[str] = []

    # All tests use UTC-naive, which is immune to DST. We verify
    # that UTC-naive datetimes around DST transitions behave correctly.

    # 10a: US DST spring forward (2025-03-09 02:00 EST -> 03:00 EDT)
    # In UTC, this is just two consecutive minutes
    dt_before = datetime(2025, 3, 9, 6, 59, 0)  # UTC
    dt_after = datetime(2025, 3, 9, 7, 1, 0)     # UTC
    ms_before = _datetime_to_epoch_ms(dt_before)
    ms_after = _datetime_to_epoch_ms(dt_after)
    checks += 1
    if ms_after - ms_before != 2 * 60 * 1000:
        failures.append(f"10a: spring forward: delta={ms_after - ms_before}ms, expected 120000ms")

    # 10b: US DST fall back (2025-11-02 02:00 EDT -> 01:00 EST)
    # In UTC, this is just two consecutive minutes
    dt_before_f = datetime(2025, 11, 2, 5, 59, 0)  # UTC
    dt_after_f = datetime(2025, 11, 2, 6, 1, 0)     # UTC
    ms_before_f = _datetime_to_epoch_ms(dt_before_f)
    ms_after_f = _datetime_to_epoch_ms(dt_after_f)
    checks += 1
    if ms_after_f - ms_before_f != 2 * 60 * 1000:
        failures.append(f"10b: fall back: delta={ms_after_f - ms_before_f}ms, expected 120000ms")

    # 10c: Midnight UTC has ms % 1000 == 0
    dt_midnight = datetime(2025, 6, 15, 0, 0, 0)
    ms_midnight = _datetime_to_epoch_ms(dt_midnight)
    checks += 1
    if ms_midnight % 1000 != 0:
        failures.append(f"10c: midnight ms not multiple of 1000: {ms_midnight}")

    # 10d: Year boundary 2024->2025 has exactly 1s gap
    dt_end_2024 = datetime(2024, 12, 31, 23, 59, 59)
    dt_start_2025 = datetime(2025, 1, 1, 0, 0, 0)
    ms_end = _datetime_to_epoch_ms(dt_end_2024)
    ms_start = _datetime_to_epoch_ms(dt_start_2025)
    checks += 1
    if ms_start - ms_end != 1000:
        failures.append(f"10d: year boundary: delta={ms_start - ms_end}ms, expected 1000ms")

    # 10e: Leap second boundary (2016-12-31T23:59:59) roundtrip
    # Python doesn't model leap seconds, so this should roundtrip cleanly
    dt_leap = datetime(2016, 12, 31, 23, 59, 59)
    ms_leap = _datetime_to_epoch_ms(dt_leap)
    rt_leap = datetime.fromtimestamp(ms_leap / 1000, tz=timezone.utc).replace(tzinfo=None)
    checks += 1
    if rt_leap != dt_leap:
        failures.append(f"10e: leap second roundtrip: {dt_leap} -> {ms_leap} -> {rt_leap}")

    return checks, failures


# ── Category 11: Live Candle Conversion ──────────────────────────────

def _cat_live_candle_conversion() -> tuple[int, list[str]]:
    """Test KlineData -> Candle timestamp conversion (live_runner.py path)."""
    from src.data.realtime_models import KlineData
    from src.engine.interfaces import Candle
    from src.backtest.runtime.timeframe import tf_minutes

    checks = 0
    failures: list[str] = []

    # Simulate Bybit 15m kline: start_time=epoch_ms, end_time=last_ms_of_candle
    # Bybit convention: end_time is the last millisecond of the candle
    start_ms = 1735689600000  # 2025-01-01 00:00:00 UTC
    end_ms = 1735690499999    # 2025-01-01 00:14:59.999 UTC

    kline = KlineData(
        symbol="BTCUSDT", interval="15",
        start_time=start_ms, end_time=end_ms,
        open=100.0, high=101.0, low=99.0,
        close=100.5, volume=1000.0, turnover=100000.0,
        is_closed=True,
    )

    # 11a: Reproduce live_runner.py candle conversion with end_time present
    close_ts_ms = kline.end_time + 1  # live_runner convention
    candle = Candle(
        ts_open=datetime.fromtimestamp(kline.start_time / 1000.0, tz=timezone.utc).replace(tzinfo=None),
        ts_close=datetime.fromtimestamp(close_ts_ms / 1000.0, tz=timezone.utc).replace(tzinfo=None),
        open=kline.open, high=kline.high, low=kline.low,
        close=kline.close, volume=kline.volume,
    )
    checks += 1
    if candle.ts_open != datetime(2025, 1, 1, 0, 0, 0):
        failures.append(f"11a: ts_open: expected 2025-01-01 00:00, got {candle.ts_open}")
    checks += 1
    if candle.ts_close != datetime(2025, 1, 1, 0, 15, 0):
        failures.append(f"11a: ts_close: expected 2025-01-01 00:15, got {candle.ts_close}")
    checks += 1
    if candle.ts_open.tzinfo is not None or candle.ts_close.tzinfo is not None:
        failures.append("11a: candle timestamps have tzinfo")

    # 11b: Fallback path: end_time == 0, compute from tf_minutes
    kline_no_end = KlineData(
        symbol="BTCUSDT", interval="15",
        start_time=start_ms, end_time=0,
        open=100.0, high=101.0, low=99.0,
        close=100.5, volume=1000.0, turnover=100000.0,
    )
    close_ts_ms_fb = kline_no_end.start_time + tf_minutes("15m") * 60 * 1000
    candle_fb = Candle(
        ts_open=datetime.fromtimestamp(kline_no_end.start_time / 1000.0, tz=timezone.utc).replace(tzinfo=None),
        ts_close=datetime.fromtimestamp(close_ts_ms_fb / 1000.0, tz=timezone.utc).replace(tzinfo=None),
        open=kline_no_end.open, high=kline_no_end.high, low=kline_no_end.low,
        close=kline_no_end.close, volume=kline_no_end.volume,
    )
    checks += 1
    if candle_fb.ts_close != datetime(2025, 1, 1, 0, 15, 0):
        failures.append(f"11b: fallback ts_close: expected 00:15, got {candle_fb.ts_close}")

    # 11c: Both paths produce same close time for aligned bars
    checks += 1
    if candle.ts_close != candle_fb.ts_close:
        failures.append(f"11c: end_time vs fallback mismatch: {candle.ts_close} != {candle_fb.ts_close}")

    # 11d: 1h candle close-time formula
    start_1h = 1735689600000  # 2025-01-01 00:00:00 UTC
    close_1h = start_1h + tf_minutes("1h") * 60 * 1000
    dt_close_1h = datetime.fromtimestamp(close_1h / 1000.0, tz=timezone.utc).replace(tzinfo=None)
    checks += 1
    if dt_close_1h != datetime(2025, 1, 1, 1, 0, 0):
        failures.append(f"11d: 1h close: expected 01:00, got {dt_close_1h}")

    return checks, failures


# ── Category 12: TimeRange Roundtrip ────────────────────────────────

def _cat_timerange_roundtrip() -> tuple[int, list[str]]:
    """Test TimeRange datetime -> ms -> Bybit params -> datetime roundtrip."""
    from src.utils.time_range import TimeRange
    from src.utils.datetime_utils import datetime_to_epoch_ms

    checks = 0
    failures: list[str] = []

    # 12a: from_dates() roundtrip with naive datetimes
    start_dt = datetime(2025, 1, 1, 0, 0, 0)
    end_dt = datetime(2025, 1, 2, 0, 0, 0)
    tr = TimeRange.from_dates(start_dt, end_dt)
    checks += 1
    if tr.start_datetime != start_dt:
        failures.append(f"12a: start roundtrip: {tr.start_datetime} != {start_dt}")
    checks += 1
    if tr.end_datetime != end_dt:
        failures.append(f"12a: end roundtrip: {tr.end_datetime} != {end_dt}")

    # 12b: to_bybit_params() produces correct ms values
    params = tr.to_bybit_params()
    expected_start_ms = datetime_to_epoch_ms(start_dt)
    expected_end_ms = datetime_to_epoch_ms(end_dt)
    checks += 1
    if params["startTime"] != expected_start_ms:
        failures.append(f"12b: startTime: {params['startTime']} != {expected_start_ms}")
    checks += 1
    if params["endTime"] != expected_end_ms:
        failures.append(f"12b: endTime: {params['endTime']} != {expected_end_ms}")

    # 12c: start_datetime/end_datetime are UTC-naive
    checks += 1
    if tr.start_datetime.tzinfo is not None:
        failures.append(f"12c: start_datetime has tzinfo: {tr.start_datetime.tzinfo}")
    checks += 1
    if tr.end_datetime.tzinfo is not None:
        failures.append(f"12c: end_datetime has tzinfo: {tr.end_datetime.tzinfo}")

    # 12d: from_dates() with tz-aware input -> same epoch ms as naive UTC
    aware_start = datetime(2025, 1, 1, 5, 0, 0, tzinfo=timezone(timedelta(hours=5)))
    aware_end = datetime(2025, 1, 2, 5, 0, 0, tzinfo=timezone(timedelta(hours=5)))
    tr_aware = TimeRange.from_dates(aware_start, aware_end)
    checks += 1
    if tr_aware.start_ms != tr.start_ms:
        failures.append(f"12d: aware start_ms {tr_aware.start_ms} != naive {tr.start_ms}")

    # 12e: last_24h(now=fixed) produces 24h range
    fixed_now = datetime(2025, 6, 15, 12, 0, 0)
    tr_24h = TimeRange.last_24h(now=fixed_now)
    expected_duration_ms = 24 * 60 * 60 * 1000
    checks += 1
    if tr_24h.end_ms - tr_24h.start_ms != expected_duration_ms:
        failures.append(f"12e: 24h range: {tr_24h.end_ms - tr_24h.start_ms}ms != {expected_duration_ms}ms")

    return checks, failures


# ── Category 13: Order/Position REST Integration ────────────────────

def _cat_order_position_rest() -> tuple[int, list[str]]:
    """Test that parse_bybit_ts flows correctly into Order/Position dataclasses."""
    from src.utils.datetime_utils import parse_bybit_ts
    from src.core.exchange_manager import Order, Position

    checks = 0
    failures: list[str] = []

    # Simulate Bybit REST response for an order
    created_ms = "1684738540559"
    updated_ms = "1684738600000"

    created_dt = parse_bybit_ts(created_ms)
    updated_dt = parse_bybit_ts(updated_ms)

    # 13a: Construct Order with parsed timestamps
    order = Order(
        order_id="test-order-001",
        order_link_id=None,
        symbol="BTCUSDT",
        side="Buy",
        order_type="Market",
        price=None,
        qty=0.001,
        filled_qty=0.001,
        remaining_qty=0.0,
        status="Filled",
        time_in_force="GTC",
        reduce_only=False,
        created_time=created_dt,
        updated_time=updated_dt,
    )
    checks += 1
    if order.created_time is None:
        failures.append("13a: order.created_time is None")
    elif order.created_time.tzinfo is not None:
        failures.append(f"13a: order.created_time has tzinfo: {order.created_time.tzinfo}")

    checks += 1
    if order.updated_time is None:
        failures.append("13a: order.updated_time is None")
    elif order.updated_time.tzinfo is not None:
        failures.append(f"13a: order.updated_time has tzinfo: {order.updated_time.tzinfo}")

    # 13b: Construct Position with parsed timestamps
    pos = Position(
        symbol="BTCUSDT",
        exchange="bybit",
        position_type="linear",
        side="Buy",
        size=0.001,
        size_usdt=27.0,
        entry_price=27000.0,
        current_price=27050.0,
        unrealized_pnl=0.05,
        unrealized_pnl_percent=0.185,
        leverage=10.0,
        margin_mode="cross",
        created_time=created_dt,
        updated_time=updated_dt,
    )
    checks += 1
    if pos.created_time is None:
        failures.append("13b: pos.created_time is None")
    elif pos.created_time.tzinfo is not None:
        failures.append(f"13b: pos.created_time has tzinfo: {pos.created_time.tzinfo}")

    # 13c: updated_time > created_time
    checks += 1
    if order.created_time and order.updated_time:
        if order.updated_time <= order.created_time:
            failures.append(f"13c: updated <= created: {order.updated_time} <= {order.created_time}")
    else:
        failures.append("13c: timestamps are None, cannot compare")

    # 13d: parse_bybit_ts produces same epoch ms when round-tripped
    from src.utils.datetime_utils import datetime_to_epoch_ms
    checks += 1
    if created_dt is not None:
        rt_ms = datetime_to_epoch_ms(created_dt)
        if rt_ms is None:
            failures.append("13d: datetime_to_epoch_ms returned None")
        else:
            original_ms = int(created_ms)
            if abs(rt_ms - original_ms) > 999:
                failures.append(f"13d: roundtrip drift: original={original_ms}, roundtrip={rt_ms}")
    else:
        failures.append("13d: created_dt is None")

    return checks, failures


# ── Category 14: DuckDB Tz-Aware Normalization ──────────────────────

def _cat_duckdb_normalization() -> tuple[int, list[str]]:
    """Test normalize_timestamp (canonical function for DuckDB tz-aware → naive)."""
    from src.utils.datetime_utils import normalize_timestamp

    checks = 0
    failures: list[str] = []

    # 14a: tz-aware UTC -> naive
    dt_aware = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    result = normalize_timestamp(dt_aware)
    checks += 1
    if result is None or result.tzinfo is not None:
        failures.append(f"14a: tz-aware UTC not stripped: {result}")
    checks += 1
    if result != datetime(2025, 6, 15, 12, 0, 0):
        failures.append(f"14a: value changed: {result}")

    # 14b: tz-aware non-UTC -> converted then stripped
    tz_plus5 = timezone(timedelta(hours=5))
    dt_plus5 = datetime(2025, 6, 15, 17, 0, 0, tzinfo=tz_plus5)  # == 12:00 UTC
    result_plus5 = normalize_timestamp(dt_plus5)
    checks += 1
    if result_plus5 != datetime(2025, 6, 15, 12, 0, 0):
        failures.append(f"14b: +05:00 not converted to UTC: expected 12:00, got {result_plus5}")

    # 14c: already naive -> passthrough
    dt_naive = datetime(2025, 6, 15, 12, 0, 0)
    result_naive = normalize_timestamp(dt_naive)
    checks += 1
    if result_naive != dt_naive:
        failures.append(f"14c: naive passthrough failed: {result_naive}")

    # 14d: None -> None
    checks += 1
    if normalize_timestamp(None) is not None:
        failures.append("14d: None should return None")

    # 14e: Simulate DuckDB returning tz-aware pd.Timestamp (common pattern)
    # DuckDB returns timestamps with UTC tzinfo via fetchdf()
    pd_aware = pd.Timestamp("2025-06-15T12:00:00", tz=timezone.utc)
    py_from_duck: datetime = pd_aware.to_pydatetime()  # type: ignore[assignment]  # NaTType excluded at runtime
    result_duck = normalize_timestamp(py_from_duck)
    checks += 1
    if result_duck is None or result_duck.tzinfo is not None:
        failures.append(f"14e: DuckDB pd.Timestamp not normalized: {result_duck}")

    return checks, failures


# ── Category 15: WS Staleness Pattern ───────────────────────────────

def _cat_ws_staleness_pattern() -> tuple[int, list[str]]:
    """Test the time.time() interval math pattern used for staleness checks."""
    import time as _time

    checks = 0
    failures: list[str] = []

    # The staleness pattern is: (time.time() - reception_timestamp) > threshold
    # We verify this with controlled values.

    # 15a: Fresh data (just received) -> not stale
    now = _time.time()
    reception = now - 1.0  # received 1s ago
    threshold = 5.0
    is_stale = (now - reception) > threshold
    checks += 1
    if is_stale:
        failures.append("15a: 1s-old data reported as stale with 5s threshold")

    # 15b: Old data -> stale
    reception_old = now - 10.0  # received 10s ago
    is_stale_old = (now - reception_old) > threshold
    checks += 1
    if not is_stale_old:
        failures.append("15b: 10s-old data not reported as stale with 5s threshold")

    # 15c: time.time() returns float (not datetime — this is the key invariant)
    checks += 1
    if not isinstance(now, float):
        failures.append(f"15c: time.time() returned {type(now).__name__}, expected float")

    # 15d: time.time() and time.monotonic() are both positive
    mono = _time.monotonic()
    checks += 1
    if now <= 0 or mono <= 0:
        failures.append(f"15d: negative time: time.time()={now}, monotonic()={mono}")

    # 15e: Verify the staleness threshold constants exist and are reasonable
    from src.data.realtime_models import STALENESS_THRESHOLDS
    expected_keys = {"ticker", "orderbook", "kline", "position", "order", "wallet"}
    checks += 1
    if not expected_keys.issubset(set(STALENESS_THRESHOLDS.keys())):
        missing = expected_keys - set(STALENESS_THRESHOLDS.keys())
        failures.append(f"15e: missing staleness keys: {missing}")

    # 15f: All thresholds are positive floats
    checks += 1
    for key, val in STALENESS_THRESHOLDS.items():
        if not isinstance(val, (int, float)) or val <= 0:
            failures.append(f"15f: invalid threshold {key}={val}")
            break

    return checks, failures


# ── Category 16: Sim Exchange Timestamp Flow ────────────────────────

def _cat_sim_exchange_flow() -> tuple[int, list[str]]:
    """Test that bar timestamps flow correctly through sim exchange -> Trade."""
    from src.backtest.types import Trade

    checks = 0
    failures: list[str] = []

    # Simulate the flow: bar timestamp -> entry_time -> exit_time -> Trade
    entry_bar_ts = datetime(2025, 6, 15, 14, 0, 0)  # bar close = entry time
    exit_bar_ts = datetime(2025, 6, 15, 15, 30, 0)   # later bar close = exit time

    # 16a: Trade entry_time/exit_time are both naive
    trade = Trade(
        trade_id="sim-001",
        symbol="BTCUSDT",
        side="long",
        entry_time=entry_bar_ts,
        entry_price=27000.0,
        entry_size=0.001,
        entry_size_usdt=27.0,
        exit_time=exit_bar_ts,
        exit_price=27100.0,
        exit_reason="tp",
    )
    checks += 1
    if trade.entry_time.tzinfo is not None:
        failures.append(f"16a: entry_time has tzinfo: {trade.entry_time.tzinfo}")
    checks += 1
    if trade.exit_time is not None and trade.exit_time.tzinfo is not None:
        failures.append(f"16a: exit_time has tzinfo: {trade.exit_time.tzinfo}")

    # 16b: exit_time > entry_time
    checks += 1
    if trade.exit_time is not None and trade.exit_time <= trade.entry_time:
        failures.append(f"16b: exit <= entry: {trade.exit_time} <= {trade.entry_time}")

    # 16c: to_dict() serialization of both timestamps is clean
    d = trade.to_dict()
    checks += 1
    for field in ("entry_time", "exit_time"):
        val = d[field]
        if val is not None and ("Z" in val or "+" in val):
            failures.append(f"16c: {field} has tz suffix: {val}")

    # 16d: Trade with no exit (open position) serializes correctly
    open_trade = Trade(
        trade_id="sim-002",
        symbol="BTCUSDT",
        side="short",
        entry_time=entry_bar_ts,
        entry_price=27000.0,
        entry_size=0.001,
        entry_size_usdt=27.0,
    )
    d_open = open_trade.to_dict()
    checks += 1
    if d_open["exit_time"] is not None:
        failures.append(f"16d: open trade exit_time should be None, got {d_open['exit_time']!r}")
    checks += 1
    if not open_trade.is_closed is False:
        failures.append(f"16d: open trade is_closed should be False")

    # 16e: entry_time isoformat roundtrips cleanly
    iso_entry = d["entry_time"]
    rt_entry = datetime.fromisoformat(iso_entry)
    checks += 1
    if rt_entry != entry_bar_ts:
        failures.append(f"16e: entry isoformat roundtrip: {iso_entry} -> {rt_entry} != {entry_bar_ts}")

    return checks, failures


# ── Category 17: Storage Serialization Format ───────────────────────

def _cat_storage_serialization() -> tuple[int, list[str]]:
    """Test normalize_datetime_for_storage() and strftime vs isoformat divergence."""
    from src.utils.datetime_utils import normalize_datetime_for_storage

    checks = 0
    failures: list[str] = []

    # 17a: Basic datetime -> storage string
    dt = datetime(2025, 6, 15, 12, 30, 45)
    result = normalize_datetime_for_storage(dt)
    checks += 1
    if result != "2025-06-15T12:30:45":
        failures.append(f"17a: expected '2025-06-15T12:30:45', got {result!r}")

    # 17b: strftime DROPS microseconds — verify this known behavior
    dt_us = datetime(2025, 6, 15, 12, 30, 45, 123456)
    result_us = normalize_datetime_for_storage(dt_us)
    checks += 1
    if result_us != "2025-06-15T12:30:45":
        failures.append(f"17b: microseconds not dropped: {result_us!r}")

    # 17c: strftime vs isoformat divergence — document it
    iso = dt_us.isoformat()  # includes microseconds
    checks += 1
    if result_us == iso:
        failures.append(f"17c: strftime and isoformat should differ for microsecond dt: both={iso!r}")

    # 17d: None input -> None
    checks += 1
    if normalize_datetime_for_storage(None) is not None:
        failures.append("17d: None should return None")

    # 17e: String input roundtrip
    result_str = normalize_datetime_for_storage("2025-06-15T12:30:45")
    checks += 1
    if result_str != "2025-06-15T12:30:45":
        failures.append(f"17e: string roundtrip: {result_str!r}")

    # 17f: tz-aware input -> stripped to UTC, then formatted
    tz_plus5 = timezone(timedelta(hours=5))
    dt_aware = datetime(2025, 6, 15, 17, 30, 45, tzinfo=tz_plus5)
    result_aware = normalize_datetime_for_storage(dt_aware)
    checks += 1
    if result_aware != "2025-06-15T12:30:45":
        failures.append(f"17f: tz-aware not converted: expected '2025-06-15T12:30:45', got {result_aware!r}")

    # 17g: No tz suffix in output
    checks += 1
    if result_aware is not None and ("Z" in result_aware or "+" in result_aware):
        failures.append(f"17g: storage format has tz suffix: {result_aware!r}")

    return checks, failures


# ── Category 18: TimeRange Internal Methods ─────────────────────────

def _cat_timerange_internals() -> tuple[int, list[str]]:
    """Test TimeRange._to_utc, from_timestamps_ms, and .timestamp()*1000 on tz-aware."""
    from src.utils.time_range import TimeRange
    from src.utils.datetime_utils import datetime_to_epoch_ms

    checks = 0
    failures: list[str] = []

    # 18a: _to_utc with naive datetime — adds UTC tzinfo
    naive_dt = datetime(2025, 6, 15, 12, 0, 0)
    utc_dt = TimeRange._to_utc(naive_dt)
    checks += 1
    if utc_dt.tzinfo is None:
        failures.append("18a: _to_utc(naive) should return tz-aware")
    checks += 1
    if utc_dt.replace(tzinfo=None) != naive_dt:
        failures.append(f"18a: _to_utc changed value: {utc_dt}")

    # 18b: _to_utc with non-UTC aware -> converts to UTC
    tz_plus5 = timezone(timedelta(hours=5))
    dt_plus5 = datetime(2025, 6, 15, 17, 0, 0, tzinfo=tz_plus5)
    utc_from_plus5 = TimeRange._to_utc(dt_plus5)
    checks += 1
    if utc_from_plus5.replace(tzinfo=None) != datetime(2025, 6, 15, 12, 0, 0):
        failures.append(f"18b: _to_utc(+05:00) wrong: {utc_from_plus5}")

    # 18c: .timestamp() * 1000 on tz-aware produces correct epoch ms
    # This is the pattern used in _from_hours_back and from_dates
    epoch_ms = int(utc_dt.timestamp() * 1000)
    expected_ms = datetime_to_epoch_ms(naive_dt)
    checks += 1
    if epoch_ms != expected_ms:
        failures.append(f"18c: .timestamp()*1000 on aware: {epoch_ms} != {expected_ms}")

    # 18d: from_timestamps_ms roundtrip — ms in, ms preserved
    start_ms = 1735689600000  # 2025-01-01 00:00:00 UTC
    end_ms = 1735776000000    # 2025-01-02 00:00:00 UTC
    tr = TimeRange.from_timestamps_ms(start_ms, end_ms)
    checks += 1
    if tr.start_ms != start_ms or tr.end_ms != end_ms:
        failures.append(f"18d: ms not preserved: {tr.start_ms}/{tr.end_ms}")

    # 18e: from_timestamps_ms -> start_datetime/end_datetime correct
    checks += 1
    if tr.start_datetime != datetime(2025, 1, 1, 0, 0, 0):
        failures.append(f"18e: start_datetime: {tr.start_datetime}")
    checks += 1
    if tr.end_datetime != datetime(2025, 1, 2, 0, 0, 0):
        failures.append(f"18e: end_datetime: {tr.end_datetime}")

    # 18f: _get_now_utc(None) returns tz-aware (needed for .timestamp())
    now_utc = TimeRange._get_now_utc(None)
    checks += 1
    if now_utc.tzinfo is None:
        failures.append("18f: _get_now_utc(None) returned naive")

    # 18g: _get_now_utc(naive_dt) -> adds tzinfo
    now_fixed = TimeRange._get_now_utc(naive_dt)
    checks += 1
    if now_fixed.tzinfo is None:
        failures.append("18g: _get_now_utc(naive) returned naive")

    # 18h: _from_hours_back produces correct span with fixed now
    fixed_now = datetime(2025, 6, 15, 12, 0, 0)
    tr_1h = TimeRange._from_hours_back(1, fixed_now, "test", "default")
    expected_start_ms = datetime_to_epoch_ms(datetime(2025, 6, 15, 11, 0, 0))
    expected_end_ms = datetime_to_epoch_ms(fixed_now)
    checks += 1
    if tr_1h.start_ms != expected_start_ms:
        failures.append(f"18h: 1h back start: {tr_1h.start_ms} != {expected_start_ms}")
    checks += 1
    if tr_1h.end_ms != expected_end_ms:
        failures.append(f"18h: 1h back end: {tr_1h.end_ms} != {expected_end_ms}")

    return checks, failures


# ── Category 19: All to_dict() Timestamp Serialization ──────────────

def _cat_all_to_dict_timestamps() -> tuple[int, list[str]]:
    """Test timestamp serialization in every dataclass that has to_dict()."""
    from src.backtest.types import AccountCurvePoint
    from src.data.realtime_models import BarRecord

    checks = 0
    failures: list[str] = []
    naive_dt = datetime(2025, 6, 15, 14, 30, 0)

    # 19a: AccountCurvePoint.to_dict() — clean ISO, no tz suffix
    acp = AccountCurvePoint(
        timestamp=naive_dt,
        equity_usdt=10000.0,
        used_margin_usdt=500.0,
        free_margin_usdt=9500.0,
        available_balance_usdt=9500.0,
        maintenance_margin_usdt=25.0,
    )
    d = acp.to_dict()
    checks += 1
    ts_str = d["timestamp"]
    if "Z" in ts_str or "+" in ts_str:
        failures.append(f"19a: AccountCurvePoint has tz suffix: {ts_str}")
    checks += 1
    if not ts_str.startswith("2025-06-15T14:30:00"):
        failures.append(f"19a: unexpected format: {ts_str}")

    # 19b: BarRecord.to_dict() — clean ISO
    bar = BarRecord(
        timestamp=naive_dt,
        open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0,
    )
    bd = bar.to_dict()
    checks += 1
    bar_ts = bd["timestamp"]
    if "Z" in bar_ts or "+" in bar_ts:
        failures.append(f"19b: BarRecord has tz suffix: {bar_ts}")

    # 19c: TradeRecord.to_dict() — clean ISO
    from src.core.position_manager import TradeRecord
    tr = TradeRecord(
        timestamp=naive_dt,
        symbol="BTCUSDT",
        side="BUY",
        size_usdt=27.0,
        price=27000.0,
    )
    td = tr.to_dict()
    checks += 1
    tr_ts = td["timestamp"]
    if "Z" in tr_ts or "+" in tr_ts:
        failures.append(f"19c: TradeRecord has tz suffix: {tr_ts}")

    # 19d: PortfolioSnapshot.to_dict() — clean ISO
    from src.core.position_manager import PortfolioSnapshot
    ps = PortfolioSnapshot(
        timestamp=naive_dt,
        balance=10000.0,
        available=9500.0,
        total_exposure=500.0,
        unrealized_pnl=50.0,
        positions=[],
    )
    pd_dict = ps.to_dict()
    checks += 1
    ps_ts = pd_dict["timestamp"]
    if "Z" in ps_ts or "+" in ps_ts:
        failures.append(f"19d: PortfolioSnapshot has tz suffix: {ps_ts}")

    # 19e: All isoformat() roundtrip — can parse back to same datetime
    for label, iso_str in [
        ("AccountCurvePoint", ts_str),
        ("BarRecord", bar_ts),
        ("TradeRecord", tr_ts),
        ("PortfolioSnapshot", ps_ts),
    ]:
        checks += 1
        rt = datetime.fromisoformat(iso_str)
        if rt != naive_dt:
            failures.append(f"19e: {label} roundtrip: {iso_str} -> {rt} != {naive_dt}")

    return checks, failures


# ── Category 20: Tz-Aware DataFrame Normalization ───────────────────

def _cat_tzaware_dataframe_strip() -> tuple[int, list[str]]:
    """Test the pd.to_datetime(utc=True) -> strip tzinfo pipeline."""

    checks = 0
    failures: list[str] = []

    # Simulate bybit_market.py line 45: pd.to_datetime(..., unit="ms", utc=True)
    epoch_ms_values = [1735689600000, 1735690500000, 1735691400000]  # 3 bars
    series = pd.Series(epoch_ms_values)
    ts_series = pd.to_datetime(series, unit="ms", utc=True)

    # 20a: Result IS tz-aware
    checks += 1
    if ts_series.dt.tz is None:
        failures.append("20a: pd.to_datetime(utc=True) should produce tz-aware")

    # 20b: tz_localize(None) strips it (historical_sync.py pattern)
    stripped = ts_series.dt.tz_localize(None)
    checks += 1
    if stripped.dt.tz is not None:
        failures.append(f"20b: tz_localize(None) didn't strip: {stripped.dt.tz}")

    # 20c: Stripped values are correct naive datetimes
    expected_first = datetime(2025, 1, 1, 0, 0, 0)
    actual_first: datetime = stripped.iloc[0].to_pydatetime()  # type: ignore[assignment]
    checks += 1
    if actual_first != expected_first:
        failures.append(f"20c: first value: {actual_first} != {expected_first}")

    # 20d: Alternative strip pattern: .astype('datetime64[ms]') also works
    stripped_alt = ts_series.values.astype("datetime64[ms]")
    from src.backtest.runtime.feed_store import _np_dt64_to_datetime
    actual_alt = _np_dt64_to_datetime(stripped_alt[0])
    checks += 1
    if actual_alt != expected_first:
        failures.append(f"20d: astype strip: {actual_alt} != {expected_first}")

    # 20e: FeedStore.from_dataframe with tz-aware timestamps — must produce naive
    from src.backtest.runtime.feed_store import FeedStore
    rows = []
    for i, ms in enumerate(epoch_ms_values):
        ts_open = pd.Timestamp(ms, unit="ms", tz=timezone.utc)
        ts_close = ts_open + pd.Timedelta(minutes=15)
        rows.append({
            "timestamp": ts_open,
            "ts_close": ts_close,
            "open": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i,
            "close": 100.5 + i, "volume": 1000.0,
        })
    df = pd.DataFrame(rows)
    fs = FeedStore.from_dataframe(df, "15m", "BTCUSDT")
    checks += 1
    ts_c0 = fs.get_ts_close_datetime(0)
    if ts_c0.tzinfo is not None:
        failures.append(f"20e: FeedStore from tz-aware df has tzinfo: {ts_c0.tzinfo}")

    # 20f: FeedStore index lookup works after tz-aware input
    idx = fs.get_idx_at_ts_close(ts_c0)
    checks += 1
    if idx != 0:
        failures.append(f"20f: index lookup failed: got {idx}")

    return checks, failures


# ── Category 21: Self-Test (Canary) ──────────────────────────────────

def _cat_selftest_canary() -> tuple[int, list[str]]:
    """Verify the gate itself can detect known-bad inputs.

    Each check intentionally creates a wrong value and confirms the
    comparison logic would flag it. If any canary PASSES when it should
    FAIL, the gate has a detection gap.
    """
    from calendar import timegm
    from src.backtest.runtime.feed_store import _datetime_to_epoch_ms

    checks = 0
    failures: list[str] = []

    # 21a: .timestamp() on naive datetime gives WRONG epoch (local-time bug)
    # This is the #1 bug the gate exists to prevent.
    dt = datetime(2025, 6, 15, 12, 0, 0)
    correct_ms = _datetime_to_epoch_ms(dt)  # timegm-based
    # On a UTC system .timestamp() matches timegm, but on non-UTC it diverges.
    # The CHECK is that our canonical function matches the timegm reference:
    reference_ms = timegm(dt.timetuple()) * 1000
    checks += 1
    if correct_ms != reference_ms:
        failures.append(f"21a: _datetime_to_epoch_ms disagrees with timegm: {correct_ms} != {reference_ms}")

    # 21b: tz-aware isoformat includes suffix — our checks must detect it
    aware = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    iso_aware = aware.isoformat()
    checks += 1
    if "+00:00" not in iso_aware and "Z" not in iso_aware:
        failures.append(f"21b: tz-aware isoformat should have suffix: {iso_aware!r}")

    # 21c: naive isoformat has NO suffix — baseline sanity
    naive = datetime(2025, 6, 15, 12, 0, 0)
    iso_naive = naive.isoformat()
    checks += 1
    if "+" in iso_naive or "Z" in iso_naive:
        failures.append(f"21c: naive isoformat should NOT have suffix: {iso_naive!r}")

    # 21d: strftime drops microseconds — detection canary for Cat 17
    dt_us = datetime(2025, 6, 15, 12, 0, 0, 123456)
    fmt = dt_us.strftime("%Y-%m-%dT%H:%M:%S")
    iso = dt_us.isoformat()
    checks += 1
    if fmt == iso:
        failures.append("21d: strftime and isoformat should differ for microsecond datetime")

    # 21e: fromtimestamp WITHOUT tz= uses local time (bug on non-UTC systems)
    ms = 1749988800000  # known epoch ms for 2025-06-15 12:00:00 UTC
    dt_utc = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)
    checks += 1
    # Verify the tz=utc path produces the correct known value:
    if dt_utc != datetime(2025, 6, 15, 12, 0, 0):
        failures.append(f"21e: UTC fromtimestamp wrong: {dt_utc}")

    # 21f: parse_bybit_ts returns None for garbage — gate must detect non-None
    from src.utils.datetime_utils import parse_bybit_ts
    checks += 1
    if parse_bybit_ts("not_a_number") is not None:
        failures.append("21f: parse_bybit_ts should return None for garbage")

    # 21g: Regex pattern A detects datetime.utcnow()
    import re
    _utcnow = "utcnow"
    pat_a = re.compile(rf"datetime\.{_utcnow}\s*\(")
    checks += 1
    if not pat_a.search("x = datetime.utcnow()"):
        failures.append("21g: pattern A failed to detect datetime.utcnow()")

    # 21h: Regex pattern D detects bare datetime.now() but not datetime.now(tz)
    _dtnow = "datetime.now"
    pat_d = re.compile(rf"{_dtnow}\s*\(\s*\)")
    checks += 1
    if not pat_d.search("x = datetime.now()"):
        failures.append("21h: pattern D failed to detect bare datetime.now()")
    checks += 1
    if pat_d.search("x = datetime.now(timezone.utc)"):
        failures.append("21h: pattern D false-positive on datetime.now(timezone.utc)")

    # 21i: tz_localize(None) actually strips tzinfo from tz-aware series
    ts = pd.Timestamp("2025-06-15T12:00:00", tz=timezone.utc)
    checks += 1
    if ts.tzinfo is None:
        failures.append("21i: pd.Timestamp(tz=utc) should be tz-aware")
    stripped = ts.tz_localize(None)
    checks += 1
    if stripped.tzinfo is not None:
        failures.append("21i: tz_localize(None) should strip tzinfo")

    return checks, failures


# ── Category 23: Runtime Guard Tests ─────────────────────────────────

def _cat_runtime_guards() -> tuple[int, list[str]]:
    """Test __post_init__ tz-naive assertions on key dataclasses."""
    from src.utils.datetime_utils import (
        epoch_ms_to_datetime,
        datetime_to_epoch_ms,
        normalize_timestamp,
    )

    checks = 0
    failures: list[str] = []

    tz_aware = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    naive = datetime(2025, 6, 15, 12, 0, 0)

    # 23a: Candle rejects tz-aware ts_open
    from src.engine.interfaces import Candle
    try:
        Candle(ts_open=tz_aware, ts_close=naive, open=1.0, high=2.0, low=0.5, close=1.5, volume=100.0)
        failures.append("23a: Candle accepted tz-aware ts_open")
    except AssertionError:
        pass
    checks += 1

    # 23b: Trade rejects tz-aware entry_time
    from src.backtest.types import Trade
    try:
        Trade(trade_id="test", symbol="BTCUSDT", side="long",
              entry_time=tz_aware, entry_price=100.0, entry_size=1.0, entry_size_usdt=100.0)
        failures.append("23b: Trade accepted tz-aware entry_time")
    except AssertionError:
        pass
    checks += 1

    # 23c: EquityPoint rejects tz-aware timestamp
    from src.backtest.types import EquityPoint
    try:
        EquityPoint(timestamp=tz_aware, equity=1000.0)
        failures.append("23c: EquityPoint accepted tz-aware timestamp")
    except AssertionError:
        pass
    checks += 1

    # 23d: BarRecord rejects tz-aware timestamp
    from src.data.realtime_models import BarRecord
    try:
        BarRecord(timestamp=tz_aware, open=1.0, high=2.0, low=0.5, close=1.5, volume=100.0)
        failures.append("23d: BarRecord accepted tz-aware timestamp")
    except AssertionError:
        pass
    checks += 1

    # 23e: epoch_ms_to_datetime roundtrip matches datetime_to_epoch_ms
    dt = datetime(2025, 6, 15, 12, 30, 45)
    ms = datetime_to_epoch_ms(dt)
    assert ms is not None
    rt = epoch_ms_to_datetime(ms)
    checks += 1
    if rt != dt:
        failures.append(f"23e: roundtrip failed: {dt} -> {ms} -> {rt}")
    checks += 1
    if rt.tzinfo is not None:
        failures.append(f"23e: epoch_ms_to_datetime returned tz-aware: {rt.tzinfo}")

    # 23f: normalize_timestamp(None) returns None
    checks += 1
    if normalize_timestamp(None) is not None:
        failures.append("23f: normalize_timestamp(None) should return None")

    return checks, failures


# ── Gate Entry Point ─────────────────────────────────────────────────

CATEGORIES: list[tuple[str, _CategoryFn]] = [
    ("Conversion Roundtrip", _cat_conversion_roundtrip),
    ("Timezone Handling", _cat_timezone_handling),
    ("Bybit Parsing", _cat_bybit_parsing),
    ("FeedStore Integrity", _cat_feedstore_integrity),
    ("numpy/pandas Interop", _cat_numpy_pandas_interop),
    ("BarRecord Handling", _cat_barrecord_handling),
    ("Artifact Serialization", _cat_artifact_serialization),
    ("Static Analysis", _cat_static_analysis),
    ("Multi-TF Alignment", _cat_multitf_alignment),
    ("DST / Edge Cases", _cat_dst_edge_cases),
    ("Live Candle Conversion", _cat_live_candle_conversion),
    ("TimeRange Roundtrip", _cat_timerange_roundtrip),
    ("Order/Position REST", _cat_order_position_rest),
    ("DuckDB Normalization", _cat_duckdb_normalization),
    ("WS Staleness Pattern", _cat_ws_staleness_pattern),
    ("Sim Exchange Flow", _cat_sim_exchange_flow),
    ("Storage Serialization", _cat_storage_serialization),
    ("TimeRange Internals", _cat_timerange_internals),
    ("All to_dict() Timestamps", _cat_all_to_dict_timestamps),
    ("Tz-Aware DataFrame Strip", _cat_tzaware_dataframe_strip),
    ("Self-Test Canary", _cat_selftest_canary),
    ("Tz-Aware Guards (E/F)", _cat_static_analysis_warnings),
    ("Runtime Guards", _cat_runtime_guards),
]


def gate_timestamps() -> GateResult:
    """G17: Timestamp Correctness — validate all timestamp pathways."""
    start = time.perf_counter()
    total_checks = 0
    all_failures: list[str] = []

    for name, fn in CATEGORIES:
        checks, failures = _run_category(name, fn)
        total_checks += checks
        all_failures.extend(failures)

    return GateResult(
        gate_id="G17",
        name="Timestamp Correctness",
        passed=len(all_failures) == 0,
        checked=total_checks,
        duration_sec=time.perf_counter() - start,
        detail=f"{total_checks} checks across {len(CATEGORIES)} categories",
        failures=all_failures,
    )
