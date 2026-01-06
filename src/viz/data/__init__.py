"""
Data loaders for visualization.

Loads backtest artifacts from disk for chart rendering.
Schema contract: src/viz/schemas/artifact_schema.py

Key components:
- artifact_loader: Discovers runs and loads metadata
- ohlcv_loader: Loads OHLCV from DuckDB
- indicator_loader: Computes indicators from Play definition
- trades_loader: Loads trade markers (uses entry_ts/exit_ts epoch)
- equity_loader: Loads equity curve (uses ts epoch)
"""

from .artifact_loader import discover_runs, load_run_metadata, RunDiscovery

__all__ = [
    "discover_runs",
    "load_run_metadata",
    "RunDiscovery",
]
