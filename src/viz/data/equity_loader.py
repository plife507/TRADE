"""
Equity curve loader for visualization.

Loads equity/drawdown data from artifacts.
Schema: src/viz/schemas/artifact_schema.py
"""

from pathlib import Path
from typing import Any

import pandas as pd


def load_equity_from_artifacts(run_path: Path) -> list[dict[str, Any]] | None:
    """
    Load equity curve from equity.parquet.

    Args:
        run_path: Path to run directory

    Returns:
        List of equity point dicts or None if not found
    """
    equity_file = run_path / "equity.parquet"

    if not equity_file.exists():
        return None

    try:
        df = pd.read_parquet(equity_file)

        if df.empty:
            return []

        # Use epoch timestamp column (ts) directly
        result = []
        for _, row in df.iterrows():
            if pd.isna(row["ts"]):
                continue
            point = {
                "time": int(row["ts"]),
                "equity": float(row["equity"]),
                "drawdown": float(row.get("drawdown", 0)),
                "drawdown_pct": float(row.get("drawdown_pct", 0)),
            }
            result.append(point)

        return result

    except Exception:
        return None


def calculate_equity_stats(equity_data: list[dict]) -> dict[str, Any]:
    """Calculate summary stats from equity curve."""
    if not equity_data:
        return {}

    equities = [p["equity"] for p in equity_data]
    drawdowns = [p["drawdown_pct"] for p in equity_data]

    start_equity = equities[0]
    end_equity = equities[-1]
    max_equity = max(equities)
    min_equity = min(equities)
    max_drawdown = min(drawdowns) if drawdowns else 0

    return {
        "start_equity": start_equity,
        "end_equity": end_equity,
        "max_equity": max_equity,
        "min_equity": min_equity,
        "total_return_pct": ((end_equity - start_equity) / start_equity * 100)
        if start_equity > 0
        else 0,
        "max_drawdown_pct": abs(max_drawdown),
    }
