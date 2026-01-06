"""
Equity curve API endpoints.

Provides equity and drawdown data for visualization.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..data.artifact_loader import find_run_path
from ..data.equity_loader import load_equity_from_artifacts, calculate_equity_stats

router = APIRouter(prefix="/equity", tags=["equity"])


class EquityPoint(BaseModel):
    """Single equity curve point."""

    time: int  # Unix timestamp (seconds)
    equity: float
    drawdown: float = 0.0
    drawdown_pct: float = 0.0


class EquityStats(BaseModel):
    """Summary statistics for equity curve."""

    start_equity: float
    end_equity: float
    max_equity: float
    min_equity: float
    total_return_pct: float
    max_drawdown_pct: float


class EquityResponse(BaseModel):
    """Response for GET /api/equity/{run_id}."""

    run_id: str
    data: list[EquityPoint]
    stats: EquityStats | None = None


@router.get("/{run_id}", response_model=EquityResponse)
async def get_equity(run_id: str) -> EquityResponse:
    """
    Get equity curve and drawdown data.

    Returns time series of equity values with drawdown for visualization.
    """
    run_path = find_run_path(run_id)

    if not run_path:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    equity_data = load_equity_from_artifacts(run_path)

    if equity_data is None:
        raise HTTPException(
            status_code=404, detail=f"Could not load equity data for run {run_id}"
        )

    # Calculate stats
    stats_dict = calculate_equity_stats(equity_data)
    stats = EquityStats(**stats_dict) if stats_dict else None

    # Convert to response models
    data = [EquityPoint(**p) for p in equity_data]

    return EquityResponse(run_id=run_id, data=data, stats=stats)
