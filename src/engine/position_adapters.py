"""
Position adapters for converting between different position representations.

Provides unified conversion between:
- SimulatedExchange positions (backtest)
- Exchange API positions (live/demo)
- Unified engine Position type
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .interfaces import Position
from .types import PositionSide

if TYPE_CHECKING:
    from ..backtest.sim.types import Position as SimPosition


def sim_to_engine_position(
    sim_pos: "SimPosition",
    mark_price: float,
    leverage: float = 1.0,
    liq_price: float | None = None,
) -> Position:
    """
    Convert SimulatedExchange position to unified engine Position.

    Args:
        sim_pos: Position from SimulatedExchange
        mark_price: Current mark price
        leverage: Position leverage
        liq_price: Liquidation price (if computed)

    Returns:
        Unified Position object
    """
    # Normalize side to canonical form
    side_str = sim_pos.side.value if hasattr(sim_pos.side, "value") else str(sim_pos.side)
    side = PositionSide.from_any(side_str)

    # Calculate unrealized PnL
    size_qty = sim_pos.size
    entry_price = sim_pos.entry_price
    if side.is_long:
        unrealized_pnl = (mark_price - entry_price) * size_qty
    else:
        unrealized_pnl = (entry_price - mark_price) * size_qty

    return Position(
        symbol=sim_pos.symbol,
        side=side.value,  # Use string value for Literal compatibility
        size_usdt=sim_pos.size_usdt,
        size_qty=size_qty,
        entry_price=entry_price,
        mark_price=mark_price,
        unrealized_pnl=unrealized_pnl,
        leverage=leverage,
        stop_loss=sim_pos.stop_loss,
        take_profit=sim_pos.take_profit,
        liquidation_price=liq_price,
        metadata={
            "entry_time": sim_pos.entry_time.isoformat() if sim_pos.entry_time else None,
            "position_id": sim_pos.position_id,
            "source": "sim",
        },
    )


def exchange_to_engine_position(
    exch_pos: dict,
    symbol: str | None = None,
) -> Position:
    """
    Convert exchange API position data to unified engine Position.

    Handles various exchange position formats (Bybit, etc.).

    Args:
        exch_pos: Position data from exchange API
        symbol: Override symbol if not in position data

    Returns:
        Unified Position object
    """
    # Extract symbol
    pos_symbol = symbol or exch_pos.get("symbol", "UNKNOWN")

    # Normalize side
    side_raw = exch_pos.get("side", exch_pos.get("positionSide", ""))
    side = PositionSide.from_any(side_raw)

    # Extract numeric values with defaults
    size_qty = float(exch_pos.get("size", exch_pos.get("positionQty", 0)))
    size_usdt = float(exch_pos.get("positionValue", exch_pos.get("size_usdt", 0)))
    entry_price = float(exch_pos.get("entryPrice", exch_pos.get("avgPrice", 0)))
    mark_price = float(exch_pos.get("markPrice", entry_price))
    unrealized_pnl = float(exch_pos.get("unrealisedPnl", exch_pos.get("unrealizedPnl", 0)))
    leverage = float(exch_pos.get("leverage", 1))
    stop_loss = exch_pos.get("stopLoss")
    take_profit = exch_pos.get("takeProfit")
    liq_price = exch_pos.get("liqPrice", exch_pos.get("liquidationPrice"))

    # Convert to floats if present
    if stop_loss is not None:
        stop_loss = float(stop_loss)
    if take_profit is not None:
        take_profit = float(take_profit)
    if liq_price is not None:
        liq_price = float(liq_price)

    return Position(
        symbol=pos_symbol,
        side=side.value,
        size_usdt=size_usdt,
        size_qty=size_qty,
        entry_price=entry_price,
        mark_price=mark_price,
        unrealized_pnl=unrealized_pnl,
        leverage=leverage,
        stop_loss=stop_loss,
        take_profit=take_profit,
        liquidation_price=liq_price,
        metadata={
            "source": "exchange",
            "raw": exch_pos,
        },
    )


def normalize_position_side(value: str | PositionSide) -> str:
    """
    Normalize any position side value to canonical string.

    Args:
        value: Position side in any format

    Returns:
        "LONG" or "SHORT"
    """
    return PositionSide.from_any(value).value
