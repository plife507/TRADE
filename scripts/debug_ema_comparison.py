#!/usr/bin/env python
"""
Debug script to verify EMA comparison logic against pandas-ta.

Test: I_001_ema - close > ema_21 entry, close < ema_21 exit

Usage:
    python scripts/debug_ema_comparison.py

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


def compute_ema_signals(df: pd.DataFrame, length: int = 21) -> pd.DataFrame:
    """Compute EMA and detect entry/exit signals."""
    df = df.copy()
    df[f'ema_{length}'] = ta.ema(df['close'], length=length)

    ema_col = f'ema_{length}'

    # Entry: close > ema (transition from below to above OR continuing above)
    # For continuous signal: we enter when close > ema and we don't have a position
    # Exit: close < ema

    df['close_above_ema'] = df['close'] > df[ema_col]
    df['close_below_ema'] = df['close'] < df[ema_col]

    # Detect transitions
    df['entry_signal'] = (df['close'] > df[ema_col]) & (df['close'].shift(1) <= df[ema_col].shift(1))
    df['exit_signal'] = (df['close'] < df[ema_col]) & (df['close'].shift(1) >= df[ema_col].shift(1))

    return df


def main():
    print("=" * 60)
    print("EMA COMPARISON LOGIC VERIFICATION")
    print("=" * 60)

    # Load data with warmup
    df = load_ohlcv("ETHUSDT", "1h", "2024-12-28", "2025-01-16")
    print(f"\nLoaded {len(df)} bars: {df.index.min()} to {df.index.max()}")

    # Compute EMA and signals
    df = compute_ema_signals(df)

    # Filter to trading window
    start = datetime(2025, 1, 1)
    end = datetime(2025, 1, 15)
    trading_df = df[(df.index >= start) & (df.index < end)]

    print(f"\n=== EMA VALUES SAMPLE (first 10 bars of trading window) ===")
    print(trading_df[['close', 'ema_21', 'close_above_ema']].head(10).to_string())

    # Count signals
    entry_signals = trading_df[trading_df['entry_signal']].index.tolist()
    exit_signals = trading_df[trading_df['exit_signal']].index.tolist()

    print(f"\n=== ENTRY SIGNALS (close crosses above ema_21) ===")
    print(f"Found {len(entry_signals)} entry transition signals:")
    for ts in entry_signals[:10]:
        row = df.loc[ts]
        prev_idx = df.index.get_loc(ts) - 1
        prev_row = df.iloc[prev_idx]
        print(f"  {ts}: close={row['close']:.2f}, ema_21={row['ema_21']:.2f}")
        print(f"         prev_close={prev_row['close']:.2f}, prev_ema_21={prev_row['ema_21']:.2f}")

    print(f"\n=== EXIT SIGNALS (close crosses below ema_21) ===")
    print(f"Found {len(exit_signals)} exit transition signals:")
    for ts in exit_signals[:10]:
        row = df.loc[ts]
        prev_idx = df.index.get_loc(ts) - 1
        prev_row = df.iloc[prev_idx]
        print(f"  {ts}: close={row['close']:.2f}, ema_21={row['ema_21']:.2f}")
        print(f"         prev_close={prev_row['close']:.2f}, prev_ema_21={prev_row['ema_21']:.2f}")

    # Expected engine entries (signal bar + 1 hour)
    print(f"\n=== EXPECTED ENGINE ENTRY TIMES ===")
    print("(Signal bar + 1 hour = next bar open where order fills)")
    for signal_ts in entry_signals[:10]:
        entry_ts = signal_ts + pd.Timedelta(hours=1)
        print(f"  Signal: {signal_ts} -> Entry: {entry_ts}")

    print("\n" + "=" * 60)
    print("VERIFICATION NOTES")
    print("=" * 60)
    print("""
For I_001_ema, the engine uses:
- Entry: close > ema_21 (true while close remains above)
- Exit: close < ema_21 (true while close remains below)

Unlike crossover (I_010), this is a LEVEL condition, not a TRANSITION.
This means:
- Entry signal fires EVERY bar where close > ema_21
- But position_policy.max_positions_per_symbol=1 prevents multiple entries
- Exit signal fires when close < ema_21

The 22 trades indicate frequent crossing of the EMA line.
""")


if __name__ == "__main__":
    main()
