"""
Trades loader for visualization.

Loads trade data from artifacts for chart markers.
Schema: src/viz/schemas/artifact_schema.py
"""

from pathlib import Path

import pandas as pd


def _parse_timestamp(val) -> int | None:
    """Parse timestamp from various formats to Unix seconds."""
    if pd.isna(val):
        return None
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        # ISO datetime string
        return int(pd.Timestamp(val).timestamp())
    if isinstance(val, pd.Timestamp):
        return int(val.timestamp())
    return None


def load_trades_from_artifacts(run_path: Path) -> list[dict] | None:
    """
    Load trades from a run's trades.parquet file.

    Args:
        run_path: Path to the run directory

    Returns:
        List of trade dicts or None if not found
    """
    trades_file = run_path / "trades.parquet"

    if not trades_file.exists():
        return None

    try:
        df = pd.read_parquet(trades_file)

        if df.empty:
            return []

        # Handle both column naming conventions:
        # - Old: entry_ts, exit_ts (epoch)
        # - New: entry_time, exit_time (ISO string or datetime)
        entry_col = "entry_ts" if "entry_ts" in df.columns else "entry_time"
        exit_col = "exit_ts" if "exit_ts" in df.columns else "exit_time"

        trades = []
        for _, row in df.iterrows():
            trade = {
                "trade_id": row["trade_id"],
                "side": row["side"],
                "entry_time": _parse_timestamp(row[entry_col]),
                "entry_price": float(row["entry_price"]),
                "exit_time": _parse_timestamp(row[exit_col]),
                "exit_price": float(row["exit_price"]) if pd.notna(row.get("exit_price")) else None,
                "exit_reason": row.get("exit_reason"),
                "stop_loss": float(row["stop_loss"]) if pd.notna(row.get("stop_loss")) else None,
                "take_profit": float(row["take_profit"]) if pd.notna(row.get("take_profit")) else None,
                "net_pnl": float(row["net_pnl"]),
                "entry_size_usdt": float(row["entry_size_usdt"]),
            }
            trades.append(trade)

        return trades

    except Exception:
        return None
