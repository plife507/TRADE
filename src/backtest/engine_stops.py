"""
Stop checks module for backtest execution.

This module handles stop condition checking:
- StopCheckResult: Dataclass for stop check results
- check_liquidation: Check if exchange is liquidatable
- check_equity_floor: Check if equity hit floor
- check_strategy_starvation: Check if can't meet entry gate
- check_all_stop_conditions: Check all stops with precedence

Stop precedence (highest to lowest priority):
1. LIQUIDATED - equity <= maintenance margin (terminal)
2. EQUITY_FLOOR_HIT - equity <= stop_equity_usdt (terminal)
3. STRATEGY_STARVED - can't meet entry gate (non-terminal, continues)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from .types import StopReason

if TYPE_CHECKING:
    from .sim import SimulatedExchange
    from .system_config import RiskProfileConfig


@dataclass
class StopCheckResult:
    """Result from checking stop conditions."""

    # Whether any terminal stop was hit
    terminal_stop: bool = False

    # Whether strategy is starved (non-terminal)
    strategy_starved: bool = False

    # Stop classification (if terminal)
    classification: StopReason | None = None

    # Human-readable reason detail
    reason_detail: str | None = None

    # Short reason string for trade records
    reason: str | None = None


def check_liquidation(exchange: "SimulatedExchange") -> StopCheckResult | None:
    """
    Check if exchange is in liquidatable state.

    Args:
        exchange: SimulatedExchange instance

    Returns:
        StopCheckResult if liquidatable, None otherwise
    """
    if exchange.is_liquidatable:
        return StopCheckResult(
            terminal_stop=True,
            strategy_starved=False,
            classification=StopReason.LIQUIDATED,
            reason_detail=(
                f"Liquidation: equity ${exchange.equity_usdt:.2f} "
                f"<= maintenance margin ${exchange.maintenance_margin:.2f}"
            ),
            reason="liquidated",
        )
    return None


def check_equity_floor(
    exchange: "SimulatedExchange",
    stop_equity_usdt: float,
) -> StopCheckResult | None:
    """
    Check if equity hit floor threshold.

    Args:
        exchange: SimulatedExchange instance
        stop_equity_usdt: Equity floor threshold

    Returns:
        StopCheckResult if equity floor hit, None otherwise
    """
    if exchange.equity_usdt <= stop_equity_usdt:
        return StopCheckResult(
            terminal_stop=True,
            strategy_starved=False,
            classification=StopReason.EQUITY_FLOOR_HIT,
            reason_detail=(
                f"Equity floor hit: equity ${exchange.equity_usdt:.2f} "
                f"<= threshold ${stop_equity_usdt:.2f}"
            ),
            reason="account_blown",
        )
    return None


def check_max_drawdown(
    current_equity: float,
    peak_equity: float,
    max_drawdown_pct: float,
) -> StopCheckResult | None:
    """
    Check if drawdown from peak exceeds maximum allowed.

    Args:
        current_equity: Current account equity in USDT
        peak_equity: Peak equity since start in USDT
        max_drawdown_pct: Maximum allowed drawdown percentage (e.g., 25.0 for 25%)

    Returns:
        StopCheckResult if max drawdown exceeded, None otherwise
    """
    if peak_equity <= 0:
        return None

    drawdown_pct = (peak_equity - current_equity) / peak_equity * 100

    if drawdown_pct >= max_drawdown_pct:
        return StopCheckResult(
            terminal_stop=True,
            strategy_starved=False,
            classification=StopReason.MAX_DRAWDOWN_HIT,
            reason_detail=(
                f"Max drawdown hit: {drawdown_pct:.2f}% >= {max_drawdown_pct:.2f}% "
                f"(equity ${current_equity:.2f}, peak ${peak_equity:.2f})"
            ),
            reason="max_drawdown",
        )
    return None


def check_strategy_starvation(
    exchange: "SimulatedExchange",
    min_trade_usdt: float,
    bar_ts_close: datetime,
    bar_index: int,
    logger=None,
) -> StopCheckResult | None:
    """
    Check if strategy is starved (can't meet entry gate).

    This is a non-terminal stop - simulation continues but entries are disabled.

    Args:
        exchange: SimulatedExchange instance
        min_trade_usdt: Minimum trade size in USDT
        bar_ts_close: Current bar close timestamp
        bar_index: Current bar index
        logger: Optional logger

    Returns:
        StopCheckResult if starved (with terminal_stop=False), None otherwise
    """
    if exchange.entries_disabled:
        # Already starved
        return None

    # Check preemptive starvation: can we open a min_trade_usdt position?
    required_for_min = exchange.compute_required_for_entry(min_trade_usdt)
    if exchange.available_balance_usdt < required_for_min:
        # Set starvation on exchange (use ts_close as evaluation time)
        exchange.set_starvation(bar_ts_close, bar_index, "INSUFFICIENT_ENTRY_GATE")
        # Cancel any pending entry order
        exchange.cancel_pending_order()

        if logger:
            logger.info(
                f"Strategy starved at bar {bar_index}: available=${exchange.available_balance_usdt:.2f} "
                f"< required=${required_for_min:.2f} for min_trade_usdt=${min_trade_usdt}"
            )

        return StopCheckResult(
            terminal_stop=False,
            strategy_starved=True,
            classification=StopReason.STRATEGY_STARVED,
            reason_detail=(
                f"Strategy starved: available=${exchange.available_balance_usdt:.2f} "
                f"< required=${required_for_min:.2f}"
            ),
            reason="starved",
        )

    return None


def check_all_stop_conditions(
    exchange: "SimulatedExchange",
    risk_profile: "RiskProfileConfig",
    bar_ts_close: datetime,
    bar_index: int,
    logger=None,
    peak_equity: float | None = None,
) -> StopCheckResult:
    """
    Check all stop conditions with proper precedence.

    Stop precedence (highest to lowest):
    1. LIQUIDATED - equity <= maintenance margin (terminal)
    2. EQUITY_FLOOR_HIT - equity <= stop_equity_usdt (terminal)
    3. MAX_DRAWDOWN_HIT - drawdown from peak exceeds max_drawdown_pct (terminal)
    4. STRATEGY_STARVED - can't meet entry gate (non-terminal)

    Args:
        exchange: SimulatedExchange instance
        risk_profile: RiskProfileConfig with thresholds
        bar_ts_close: Current bar close timestamp
        bar_index: Current bar index
        logger: Optional logger
        peak_equity: Peak equity for drawdown calculation (if None, skip DD check)

    Returns:
        StopCheckResult with stop status and details
    """
    # 1. LIQUIDATED (highest priority)
    result = check_liquidation(exchange)
    if result:
        return result

    # 2. EQUITY_FLOOR_HIT
    result = check_equity_floor(exchange, risk_profile.stop_equity_usdt)
    if result:
        return result

    # 3. MAX_DRAWDOWN_HIT (if peak_equity provided)
    if peak_equity is not None and risk_profile.max_drawdown_pct > 0:
        result = check_max_drawdown(
            current_equity=exchange.equity_usdt,
            peak_equity=peak_equity,
            max_drawdown_pct=risk_profile.max_drawdown_pct,
        )
        if result:
            return result

    # 4. STRATEGY_STARVED (non-terminal)
    result = check_strategy_starvation(
        exchange=exchange,
        min_trade_usdt=risk_profile.min_trade_usdt,
        bar_ts_close=bar_ts_close,
        bar_index=bar_index,
        logger=logger,
    )
    if result:
        return result

    # No stop condition triggered
    return StopCheckResult(
        terminal_stop=False,
        strategy_starved=False,
        classification=None,
        reason_detail=None,
        reason=None,
    )


def handle_terminal_stop(
    exchange: "SimulatedExchange",
    bar_close_price: float,
    bar_ts_close: datetime,
    stop_reason: str,
) -> None:
    """
    Handle terminal stop: cancel orders and force close position.

    Args:
        exchange: SimulatedExchange instance
        bar_close_price: Current bar close price
        bar_ts_close: Current bar close timestamp
        stop_reason: Reason for stop (for position close)
    """
    # Cancel any pending entry order
    exchange.cancel_pending_order()

    # Force close any open position at current bar close
    if exchange.position is not None:
        exchange.force_close_position(
            bar_close_price,
            bar_ts_close,
            reason=stop_reason,
        )
