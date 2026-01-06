"""
Backtest Visualization Module.

Provides a FastAPI server for visualizing backtest results via a web UI.

Usage:
    python trade_cli.py viz serve --port 8765

Then visit http://localhost:8765 to view backtest results.
"""

from .server import create_app, run_server

__all__ = ["create_app", "run_server"]
