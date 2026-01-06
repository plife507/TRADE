"""
Trades API endpoints.

Provides trade markers for chart visualization.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..data.artifact_loader import find_run_path
from ..data.trades_loader import load_trades_from_artifacts

router = APIRouter(prefix="/trades", tags=["trades"])


class TradeMarker(BaseModel):
    """A single trade marker for the chart."""

    trade_id: str
    side: str  # "long" or "short"

    # Entry
    entry_time: int  # Unix timestamp (seconds)
    entry_price: float

    # Exit (None if still open)
    exit_time: int | None = None
    exit_price: float | None = None
    exit_reason: str | None = None

    # Risk levels for lines
    stop_loss: float | None = None
    take_profit: float | None = None

    # Result
    net_pnl: float = 0.0
    is_winner: bool = False


class TradeMarkersResponse(BaseModel):
    """Response for GET /api/trades/{run_id}/markers."""

    run_id: str
    markers: list[TradeMarker]
    total_trades: int
    winners: int
    losers: int


@router.get("/{run_id}/markers", response_model=TradeMarkersResponse)
async def get_trade_markers(run_id: str) -> TradeMarkersResponse:
    """
    Get trade markers for chart overlay.

    Returns entry/exit points with TP/SL levels for visualization.
    """
    run_path = find_run_path(run_id)

    if not run_path:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    trades = load_trades_from_artifacts(run_path)

    if trades is None:
        raise HTTPException(
            status_code=404, detail=f"Could not load trades for run {run_id}"
        )

    markers = []
    winners = 0
    losers = 0

    for trade in trades:
        is_winner = trade.get("net_pnl", 0) > 0

        if is_winner:
            winners += 1
        elif trade.get("exit_time") is not None:
            losers += 1

        marker = TradeMarker(
            trade_id=trade.get("trade_id", ""),
            side=trade.get("side", "long"),
            entry_time=trade.get("entry_time", 0),
            entry_price=trade.get("entry_price", 0),
            exit_time=trade.get("exit_time"),
            exit_price=trade.get("exit_price"),
            exit_reason=trade.get("exit_reason"),
            stop_loss=trade.get("stop_loss"),
            take_profit=trade.get("take_profit"),
            net_pnl=trade.get("net_pnl", 0),
            is_winner=is_winner,
        )
        markers.append(marker)

    return TradeMarkersResponse(
        run_id=run_id,
        markers=markers,
        total_trades=len(markers),
        winners=winners,
        losers=losers,
    )
