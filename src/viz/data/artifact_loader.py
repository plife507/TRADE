"""
Artifact discovery and loading for visualization.

Discovers backtest runs from the artifact directory structure:
    backtests/{category}/{play_id}/{symbol}/{run_id}/
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json


@dataclass
class RunDiscovery:
    """Discovered backtest run from file system."""

    run_id: str
    play_id: str
    symbol: str
    category: str
    artifact_path: Path
    has_snapshots: bool = False

    # Loaded from result.json
    tf_exec: str = ""
    window_start: str = ""
    window_end: str = ""
    created_at: str = ""

    # Key metrics
    trades_count: int = 0
    net_pnl_usdt: float = 0.0
    net_return_pct: float = 0.0
    win_rate: float = 0.0
    sharpe: float = 0.0
    max_drawdown_pct: float = 0.0


def discover_runs(
    base_dir: Path | None = None,
    category: str | None = None,
    play_id: str | None = None,
    symbol: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[RunDiscovery], int]:
    """
    Discover backtest runs from artifact directories.

    Args:
        base_dir: Base directory for artifacts (default: backtests/)
        category: Filter by category (_validation, strategies)
        play_id: Filter by play ID
        symbol: Filter by symbol
        limit: Max runs to return
        offset: Offset for pagination

    Returns:
        Tuple of (runs list, total count)
    """
    if base_dir is None:
        base_dir = Path("backtests")

    if not base_dir.exists():
        return [], 0

    runs: list[RunDiscovery] = []

    # Walk the directory structure
    for category_dir in sorted(base_dir.iterdir()):
        if not category_dir.is_dir():
            continue
        cat_name = category_dir.name

        # Filter by category
        if category and cat_name != category:
            continue

        for play_dir in sorted(category_dir.iterdir()):
            if not play_dir.is_dir():
                continue
            play_name = play_dir.name

            # Filter by play_id
            if play_id and play_name != play_id:
                continue

            for symbol_dir in sorted(play_dir.iterdir()):
                if not symbol_dir.is_dir():
                    continue
                sym_name = symbol_dir.name

                # Filter by symbol
                if symbol and sym_name != symbol:
                    continue

                for run_dir in sorted(symbol_dir.iterdir(), reverse=True):
                    if not run_dir.is_dir():
                        continue

                    # Check for required files
                    result_path = run_dir / "result.json"
                    if not result_path.exists():
                        continue

                    # Load basic metadata
                    discovery = _load_run_discovery(
                        run_id=run_dir.name,
                        play_id=play_name,
                        symbol=sym_name,
                        category=cat_name,
                        artifact_path=run_dir,
                    )
                    if discovery:
                        runs.append(discovery)

    # Sort by created_at descending (most recent first)
    runs.sort(key=lambda r: r.created_at or "", reverse=True)

    total = len(runs)

    # Apply pagination
    paginated = runs[offset:offset + limit]

    return paginated, total


def _load_run_discovery(
    run_id: str,
    play_id: str,
    symbol: str,
    category: str,
    artifact_path: Path,
) -> RunDiscovery | None:
    """Load run discovery from result.json."""
    result_path = artifact_path / "result.json"

    try:
        with open(result_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Extract metrics from nested structure
        metrics = data.get("metrics", {})

        return RunDiscovery(
            run_id=run_id,
            play_id=play_id,
            symbol=symbol,
            category=category,
            artifact_path=artifact_path,
            has_snapshots=(artifact_path / "snapshots").exists(),
            tf_exec=data.get("tf_exec", data.get("tf", "")),
            window_start=data.get("window_start", ""),
            window_end=data.get("window_end", ""),
            created_at=data.get("finished_at", data.get("created_at", "")),
            trades_count=data.get("trades_count", metrics.get("total_trades", 0)),
            net_pnl_usdt=data.get("net_pnl_usdt", metrics.get("net_profit", 0.0)),
            net_return_pct=metrics.get("net_return_pct", 0.0),
            win_rate=metrics.get("win_rate", 0.0),
            sharpe=metrics.get("sharpe", 0.0),
            max_drawdown_pct=metrics.get("max_drawdown_pct", 0.0),
        )
    except Exception:
        return None


def load_run_metadata(run_path: Path) -> dict[str, Any] | None:
    """
    Load full run metadata from result.json.

    Args:
        run_path: Path to run directory

    Returns:
        Full result.json data or None if not found
    """
    result_path = run_path / "result.json"

    if not result_path.exists():
        return None

    try:
        with open(result_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def find_run_path(
    run_id: str,
    base_dir: Path | None = None,
) -> Path | None:
    """
    Find the artifact path for a run ID.

    Args:
        run_id: Run identifier (8-char hash)
        base_dir: Base directory for artifacts

    Returns:
        Path to run directory or None if not found
    """
    if base_dir is None:
        base_dir = Path("backtests")

    if not base_dir.exists():
        return None

    # Walk to find the run
    for category_dir in base_dir.iterdir():
        if not category_dir.is_dir():
            continue
        for play_dir in category_dir.iterdir():
            if not play_dir.is_dir():
                continue
            for symbol_dir in play_dir.iterdir():
                if not symbol_dir.is_dir():
                    continue
                run_dir = symbol_dir / run_id
                if run_dir.exists() and (run_dir / "result.json").exists():
                    return run_dir

    return None
