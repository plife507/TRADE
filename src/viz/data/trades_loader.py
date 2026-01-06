"""
Trades loader for visualization.

Loads trade data from artifacts for chart markers.
Schema: src/viz/schemas/artifact_schema.py
"""

from pathlib import Path

import pandas as pd


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

        # Use epoch timestamp columns directly (entry_ts, exit_ts)
        trades = []
        for _, row in df.iterrows():
            trade = {
                "trade_id": row["trade_id"],
                "side": row["side"],
                "entry_time": int(row["entry_ts"]) if pd.notna(row["entry_ts"]) else None,
                "entry_price": float(row["entry_price"]),
                "exit_time": int(row["exit_ts"]) if pd.notna(row["exit_ts"]) else None,
                "exit_price": float(row["exit_price"]) if pd.notna(row["exit_price"]) else None,
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
