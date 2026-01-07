"""
Runs API endpoints.

Provides endpoints for listing and retrieving backtest runs.
"""

import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

from ..data.artifact_loader import discover_runs, find_run_path, load_run_metadata
from ..models.run_metadata import RunSummary, RunListResponse, RunDetailResponse

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=RunListResponse)
async def list_runs(
    category: str | None = Query(None, description="Filter by category"),
    play_id: str | None = Query(None, description="Filter by play ID"),
    symbol: str | None = Query(None, description="Filter by symbol"),
    limit: int = Query(50, ge=1, le=200, description="Max runs to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
) -> RunListResponse:
    """
    List all backtest runs.

    Returns paginated list of runs with key metrics for quick display.
    """
    runs, total = discover_runs(
        category=category,
        play_id=play_id,
        symbol=symbol,
        limit=limit,
        offset=offset,
    )

    return RunListResponse(
        runs=[
            RunSummary(
                run_id=r.run_id,
                play_id=r.play_id,
                symbol=r.symbol,
                tf_exec=r.tf_exec,
                category=r.category,
                window_start=r.window_start,
                window_end=r.window_end,
                created_at=r.created_at,
                trades_count=r.trades_count,
                net_pnl_usdt=r.net_pnl_usdt,
                net_return_pct=r.net_return_pct,
                win_rate=r.win_rate,
                sharpe=r.sharpe,
                max_drawdown_pct=r.max_drawdown_pct,
                artifact_path=str(r.artifact_path),
                has_snapshots=r.has_snapshots,
                description=r.description,
            )
            for r in runs
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/categories")
async def list_categories() -> list[str]:
    """
    List available run categories.

    Returns list of category names found in artifacts.
    """
    base_dir = Path("backtests")
    if not base_dir.exists():
        return []

    categories = []
    for d in sorted(base_dir.iterdir()):
        if d.is_dir():
            categories.append(d.name)

    return categories


@router.get("/{run_id}", response_model=RunDetailResponse)
async def get_run(run_id: str) -> RunDetailResponse:
    """
    Get detailed information about a specific run.

    Returns full metrics and metadata for the run.
    """
    run_path = find_run_path(run_id)

    if not run_path:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    data = load_run_metadata(run_path)
    if not data:
        raise HTTPException(status_code=404, detail=f"Could not load run {run_id}")

    metrics = data.get("metrics", {})

    # Extract category, play_id, symbol from path
    # Path structure: backtests/{category}/{play_id}/{symbol}/{run_id}
    parts = run_path.parts
    try:
        backtests_idx = parts.index("backtests")
        category = parts[backtests_idx + 1]
        play_id = parts[backtests_idx + 2]
        symbol = parts[backtests_idx + 3]
    except (ValueError, IndexError):
        category = ""
        play_id = data.get("play_id", "")
        symbol = data.get("symbol", "")

    return RunDetailResponse(
        run_id=run_id,
        play_id=play_id,
        symbol=symbol,
        tf_exec=data.get("tf_exec", data.get("tf", "")),
        category=category,
        window_start=data.get("window_start", ""),
        window_end=data.get("window_end", ""),
        created_at=data.get("finished_at", ""),
        # Full metrics
        initial_equity=metrics.get("initial_equity", 0.0),
        final_equity=metrics.get("final_equity", 0.0),
        net_profit=metrics.get("net_profit", 0.0),
        net_return_pct=metrics.get("net_return_pct", 0.0),
        benchmark_return_pct=metrics.get("benchmark_return_pct", 0.0),
        alpha_pct=metrics.get("alpha_pct", 0.0),
        # Drawdown
        max_drawdown_abs=metrics.get("max_drawdown_abs", 0.0),
        max_drawdown_pct=metrics.get("max_drawdown_pct", 0.0),
        max_drawdown_duration_bars=metrics.get("max_drawdown_duration_bars", 0),
        # Trade stats
        total_trades=metrics.get("total_trades", 0),
        win_count=metrics.get("win_count", 0),
        loss_count=metrics.get("loss_count", 0),
        win_rate=metrics.get("win_rate", 0.0),
        profit_factor=metrics.get("profit_factor", 0.0),
        # Risk-adjusted
        sharpe=metrics.get("sharpe", 0.0),
        sortino=metrics.get("sortino", 0.0),
        calmar=metrics.get("calmar", 0.0),
        # Extended
        avg_win_usdt=metrics.get("avg_win_usdt", 0.0),
        avg_loss_usdt=metrics.get("avg_loss_usdt", 0.0),
        largest_win_usdt=metrics.get("largest_win_usdt", 0.0),
        largest_loss_usdt=metrics.get("largest_loss_usdt", 0.0),
        avg_trade_duration_bars=metrics.get("avg_trade_duration_bars", 0.0),
        expectancy_usdt=metrics.get("expectancy_usdt", 0.0),
        payoff_ratio=metrics.get("payoff_ratio", 0.0),
        # Long/short
        long_trades=metrics.get("long_trades", 0),
        short_trades=metrics.get("short_trades", 0),
        long_win_rate=metrics.get("long_win_rate", 0.0),
        short_win_rate=metrics.get("short_win_rate", 0.0),
        long_pnl=metrics.get("long_pnl", 0.0),
        short_pnl=metrics.get("short_pnl", 0.0),
        # Time
        total_bars=metrics.get("total_bars", 0),
        bars_in_position=metrics.get("bars_in_position", 0),
        time_in_market_pct=metrics.get("time_in_market_pct", 0.0),
        # Tail risk
        var_95_pct=metrics.get("var_95_pct", 0.0),
        cvar_95_pct=metrics.get("cvar_95_pct", 0.0),
        # Trade quality
        mae_avg_pct=metrics.get("mae_avg_pct", 0.0),
        mfe_avg_pct=metrics.get("mfe_avg_pct", 0.0),
        # Path info
        artifact_path=str(run_path),
        has_snapshots=(run_path / "snapshots").exists(),
    )

@router.delete("/{run_id}")
async def delete_run(run_id: str) -> dict:
    """
    Delete a backtest run and its artifacts.
    
    Removes the entire run folder from disk.
    """
    run_path = find_run_path(run_id)
    
    if not run_path:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    try:
        shutil.rmtree(run_path)
        return {"status": "deleted", "run_id": run_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete run: {e}")
