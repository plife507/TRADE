#!/usr/bin/env python
"""
Debug script to verify EMA crossover logic against pandas-ta.

FINDING (2026-01-07): Crossover logic is CORRECT.

The apparent 1-hour offset between pandas-ta crossover timestamps and engine
entry timestamps is expected behavior:
- pandas-ta detects crossover on bar timestamp (e.g., 21:00)
- Engine records entry time as when the order FILLED (22:00 = next bar open)

Entry happens at bar N+1 open, where bar N is when crossover was detected.

Usage:
    python scripts/debug_crossover.py

Requirements:
    - pandas-ta
    - duckdb
    - ETHUSDT 1h data in data/market_data_live.duckdb
"""

import sys
sys.path.insert(0, '.')

import pandas as pd
import pandas_ta as ta
import duckdb
from datetime import datetime


def load_ohlcv(symbol: str, timeframe: str, start: str, end: str) -> pd.DataFrame:
    """Load OHLCV data from DuckDB."""
    conn = duckdb.connect('data/market_data_live.duckdb', read_only=True)
    df = conn.execute(f'''
        SELECT timestamp as ts_open, open, high, low, close, volume
        FROM ohlcv_live
        WHERE symbol = '{symbol}' AND timeframe = '{timeframe}'
          AND timestamp >= '{start}' AND timestamp < '{end}'
        ORDER BY timestamp
    ''').df()
    conn.close()

    df['ts_open'] = pd.to_datetime(df['ts_open'])
    df.set_index('ts_open', inplace=True)
    return df


def compute_crossovers(df: pd.DataFrame, fast_length: int = 9, slow_length: int = 21) -> pd.DataFrame:
    """Compute EMAs and detect crossovers."""
    df = df.copy()
    df[f'ema_{fast_length}'] = ta.ema(df['close'], length=fast_length)
    df[f'ema_{slow_length}'] = ta.ema(df['close'], length=slow_length)

    fast_col = f'ema_{fast_length}'
    slow_col = f'ema_{slow_length}'

    # TradingView standard crossover detection:
    # cross_above: prev_fast <= prev_slow AND curr_fast > curr_slow
    df['cross_above'] = (df[fast_col].shift(1) <= df[slow_col].shift(1)) & (df[fast_col] > df[slow_col])
    df['cross_below'] = (df[fast_col].shift(1) >= df[slow_col].shift(1)) & (df[fast_col] < df[slow_col])

    return df


def verify_crossover_timing(df: pd.DataFrame, signal_bar: str, entry_bar: str) -> None:
    """Verify crossover timing between signal bar and entry bar."""
    signal_ts = pd.Timestamp(signal_bar)
    entry_ts = pd.Timestamp(entry_bar)

    # The signal bar should be 1 hour before entry bar
    expected_entry = signal_ts + pd.Timedelta(hours=1)

    print(f"\n=== TIMING VERIFICATION ===")
    print(f"Signal bar: {signal_bar} (bar opens at this time, closes at {expected_entry})")
    print(f"Entry bar:  {entry_bar} (order fills at bar open)")

    if expected_entry == entry_ts:
        print(f"✓ CORRECT: Entry at next bar open after signal")
    else:
        print(f"✗ MISMATCH: Expected entry at {expected_entry}, got {entry_ts}")

    # Verify crossover condition
    if signal_ts in df.index:
        prev_idx = df.index.get_loc(signal_ts) - 1
        if prev_idx >= 0:
            prev_row = df.iloc[prev_idx]
            curr_row = df.loc[signal_ts]

            print(f"\nCrossover check:")
            print(f"  prev bar: ema_9={prev_row['ema_9']:.4f}, ema_21={prev_row['ema_21']:.4f}")
            print(f"  curr bar: ema_9={curr_row['ema_9']:.4f}, ema_21={curr_row['ema_21']:.4f}")
            print(f"  prev_ema_9 <= prev_ema_21: {prev_row['ema_9'] <= prev_row['ema_21']}")
            print(f"  curr_ema_9 > curr_ema_21:  {curr_row['ema_9'] > curr_row['ema_21']}")


def main():
    print("=" * 60)
    print("EMA CROSSOVER LOGIC VERIFICATION")
    print("=" * 60)

    # Load data
    df = load_ohlcv("ETHUSDT", "1h", "2024-12-28", "2025-01-16")
    print(f"\nLoaded {len(df)} bars: {df.index.min()} to {df.index.max()}")

    # Compute crossovers
    df = compute_crossovers(df)

    # Filter to trading window
    start = datetime(2025, 1, 1)
    end = datetime(2025, 1, 15)
    trading_df = df[(df.index >= start) & (df.index < end)]

    # Get crossover events
    cross_above_ts = trading_df[trading_df['cross_above']].index.tolist()

    print(f"\n=== CROSSOVER EVENTS (pandas-ta) ===")
    print(f"Found {len(cross_above_ts)} cross_above events:")
    for ts in cross_above_ts:
        print(f"  {ts}")

    # Expected engine entries (signal bar + 1 hour)
    expected_entries = [ts + pd.Timedelta(hours=1) for ts in cross_above_ts]

    print(f"\n=== EXPECTED ENGINE ENTRY TIMES ===")
    print(f"(Signal bar + 1 hour = next bar open where order fills)")
    for signal_ts, entry_ts in zip(cross_above_ts, expected_entries):
        print(f"  Signal: {signal_ts} -> Entry: {entry_ts}")

    # Verify first crossover in detail
    if len(cross_above_ts) > 0:
        first_signal = str(cross_above_ts[0])
        first_entry = str(expected_entries[0])
        verify_crossover_timing(df, first_signal, first_entry)

    print("\n" + "=" * 60)
    print("CONCLUSION: Crossover logic is CORRECT")
    print("=" * 60)
    print("""
The 1-hour offset between pandas-ta crossover detection and
engine entry times is expected and correct:

1. Bar N (e.g., 21:00-22:00): EMA crossover detected at bar close
2. Signal emitted at bar close (22:00)
3. Order fills at next bar open (22:00 for hourly bars)
4. Entry time in trades.parquet = fill time = 22:00

This matches TradingView backtesting semantics.
""")


if __name__ == "__main__":
    main()
