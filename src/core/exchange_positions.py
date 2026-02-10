"""
Position management methods for ExchangeManager.

Handles:
- Position queries (get single, get all, get exposure)
- Position TP/SL and trailing stops
- Leverage and margin mode settings
- Conditional order cleanup/reconciliation
- Unified account operations (collateral, borrow, etc.)
"""

import re
from typing import TYPE_CHECKING

from ..exchanges.bybit_client import BybitAPIError
from ..utils.helpers import safe_float
from ..utils.time_range import TimeRange

if TYPE_CHECKING:
    from .exchange_manager import ExchangeManager, Position, Order


# =============================================================================
# Position Queries
# =============================================================================

def get_position(manager: "ExchangeManager", symbol: str) -> "Position | None":
    """
    Get position for a specific symbol.
    
    Returns:
        Position object or None if no position
    """
    from .exchange_manager import Position
    
    positions = manager.bybit.get_positions(symbol)
    
    for pos in positions:
        if pos.get("symbol") == symbol:
            size = safe_float(pos.get("size", 0))
            if size == 0:
                continue
            
            side = pos.get("side", "").lower()
            if side == "buy":
                side = "long"
            elif side == "sell":
                side = "short"
            
            entry_price = safe_float(pos.get("avgPrice", 0))
            current_price = safe_float(pos.get("markPrice", 0))
            unrealized_pnl = safe_float(pos.get("unrealisedPnl", 0))
            
            return Position(
                symbol=symbol,
                exchange="bybit",
                position_type="futures",
                side=side,
                size=size,
                size_usdt=size * current_price,
                entry_price=entry_price,
                current_price=current_price,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_percent=unrealized_pnl / (size * entry_price) * 100 if size and entry_price else 0,
                leverage=safe_float(pos.get("leverage", 1), 1),
                margin_mode=pos.get("tradeMode", "cross"),
                liquidation_price=safe_float(pos.get("liqPrice")) if pos.get("liqPrice") else None,
                take_profit=safe_float(pos.get("takeProfit")) if pos.get("takeProfit") else None,
                stop_loss=safe_float(pos.get("stopLoss")) if pos.get("stopLoss") else None,
                trailing_stop=safe_float(pos.get("trailingStop")) if pos.get("trailingStop") else None,
                adl_rank=int(pos.get("adlRankIndicator", 0)) if pos.get("adlRankIndicator") else None,
                is_reduce_only=pos.get("isReduceOnly", False),
                cumulative_pnl=safe_float(pos.get("cumRealisedPnl")) if pos.get("cumRealisedPnl") else None,
            )
    
    return None


def get_all_positions(manager: "ExchangeManager") -> list["Position"]:
    """
    Get all open positions.
    
    Returns:
        List of Position objects
    """
    from .exchange_manager import Position
    
    positions = []
    raw_positions = manager.bybit.get_positions()
    
    for pos in raw_positions:
        size = safe_float(pos.get("size", 0))
        if size == 0:
            continue
        
        symbol = pos.get("symbol")
        side = pos.get("side", "").lower()
        if side == "buy":
            side = "long"
        elif side == "sell":
            side = "short"
        
        entry_price = safe_float(pos.get("avgPrice", 0))
        current_price = safe_float(pos.get("markPrice", 0))
        unrealized_pnl = safe_float(pos.get("unrealisedPnl", 0))
        
        positions.append(Position(
            symbol=symbol,
            exchange="bybit",
            position_type="futures",
            side=side,
            size=size,
            size_usdt=size * current_price,
            entry_price=entry_price,
            current_price=current_price,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_percent=unrealized_pnl / (size * entry_price) * 100 if size and entry_price else 0,
            leverage=safe_float(pos.get("leverage", 1), 1),
            margin_mode=pos.get("tradeMode", "cross"),
            liquidation_price=safe_float(pos.get("liqPrice")) if pos.get("liqPrice") else None,
            take_profit=safe_float(pos.get("takeProfit")) if pos.get("takeProfit") else None,
            stop_loss=safe_float(pos.get("stopLoss")) if pos.get("stopLoss") else None,
            trailing_stop=safe_float(pos.get("trailingStop")) if pos.get("trailingStop") else None,
            adl_rank=int(pos.get("adlRankIndicator", 0)) if pos.get("adlRankIndicator") else None,
            is_reduce_only=pos.get("isReduceOnly", False),
            cumulative_pnl=safe_float(pos.get("cumRealisedPnl")) if pos.get("cumRealisedPnl") else None,
        ))
    
    return positions


def get_total_exposure(manager: "ExchangeManager") -> float:
    """Get total position exposure in USDT."""
    positions = get_all_positions(manager)
    return sum(pos.size_usdt for pos in positions)


# =============================================================================
# Position TP/SL/Trailing Stop
# =============================================================================

def set_position_tpsl(
    manager: "ExchangeManager",
    symbol: str,
    take_profit: float | None = None,
    stop_loss: float | None = None,
    tpsl_mode: str = "Full",
) -> bool:
    """
    Set TP/SL for an existing position.
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        take_profit: TP price (0 or None to remove)
        stop_loss: SL price (0 or None to remove)
        tpsl_mode: "Full" or "Partial"
    
    Returns:
        True if successful
    """
    try:
        manager._validate_trading_operation()
        
        manager.bybit.set_trading_stop(
            symbol=symbol,
            take_profit=str(take_profit) if take_profit else "0",
            stop_loss=str(stop_loss) if stop_loss else "0",
            tpsl_mode=tpsl_mode,
        )
        manager.logger.info(f"Set TP/SL for {symbol}: TP={take_profit}, SL={stop_loss}")
        return True
    except Exception as e:
        manager.logger.error(f"Set TP/SL failed for {symbol}: {e}")
        return False


def set_trailing_stop(
    manager: "ExchangeManager",
    symbol: str,
    trailing_stop: float,
    active_price: float | None = None,
) -> bool:
    """
    Set a trailing stop for an existing position.
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        trailing_stop: Trailing distance (price difference)
        active_price: Price at which trailing becomes active (optional)
    
    Returns:
        True if successful
    """
    try:
        manager._validate_trading_operation()
        
        kwargs = {"symbol": symbol, "trailing_stop": str(trailing_stop)}
        if active_price is not None:
            kwargs["active_price"] = str(active_price)
        manager.bybit.set_trading_stop(**kwargs)
        manager.logger.info(f"Set trailing stop for {symbol}: {trailing_stop}" +
                            (f" (active at {active_price})" if active_price else ""))
        return True
    except Exception as e:
        manager.logger.error(f"Set trailing stop failed: {e}")
        return False


# =============================================================================
# Leverage & Margin Mode
# =============================================================================

def set_leverage(manager: "ExchangeManager", symbol: str, leverage: int) -> bool:
    """
    Set leverage for a symbol.
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        leverage: Leverage multiplier
    
    Returns:
        True if successful
    """
    # Enforce config limit
    max_leverage = manager.config.risk.max_leverage
    if leverage > max_leverage:
        manager.logger.warning(f"Leverage {leverage} exceeds max {max_leverage}, using {max_leverage}")
        leverage = max_leverage
    
    try:
        manager._validate_trading_operation()
        
        manager.bybit.set_leverage(symbol, leverage)
        return True
    except BybitAPIError as e:
        # Leverage might already be set - not an error
        if "leverage not modified" in str(e).lower():
            return True
        manager.logger.error(f"Set leverage failed: {e}")
        return False
    except Exception as e:
        manager.logger.error(f"Set leverage error: {e}")
        return False


def set_margin_mode(manager: "ExchangeManager", symbol: str, mode: str, leverage: float = 1.0) -> bool:
    """
    Set margin mode for a symbol.

    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        mode: "ISOLATED_MARGIN" or "REGULAR_MARGIN" (cross)
        leverage: Leverage to set (from Play risk model)

    Returns:
        True if successful
    """
    try:
        manager._validate_trading_operation()

        lev_str = str(int(leverage)) if leverage == int(leverage) else str(leverage)
        trade_mode = 0 if mode == "REGULAR_MARGIN" else 1  # 0=cross, 1=isolated
        manager.bybit.switch_cross_isolated_margin(
            symbol=symbol,
            trade_mode=trade_mode,
            buy_leverage=lev_str,
            sell_leverage=lev_str,
        )
        manager.logger.info(f"Set margin mode for {symbol} to {mode} at {lev_str}x leverage")
        return True
    except Exception as e:
        # Mode might already be set
        if "margin mode is not modified" in str(e).lower():
            return True
        manager.logger.error(f"Set margin mode failed: {e}")
        return False


def set_position_mode(manager: "ExchangeManager", mode: str = "MergedSingle") -> bool:
    """
    Set position mode for the account.
    
    Args:
        manager: ExchangeManager instance
        mode: "MergedSingle" (one-way) or "BothSide" (hedge mode)
    
    Returns:
        True if successful
    """
    try:
        manager._validate_trading_operation()
        
        manager.bybit.switch_position_mode_v5(
            mode=0 if mode == "MergedSingle" else 3,  # 0=one-way, 3=hedge
            coin="USDT",
        )
        manager.logger.info(f"Set position mode to {mode}")
        return True
    except Exception as e:
        # Mode might already be set
        if "position mode is not modified" in str(e).lower():
            return True
        manager.logger.error(f"Set position mode failed: {e}")
        return False


def add_margin(manager: "ExchangeManager", symbol: str, amount: float) -> bool:
    """
    Add margin to an isolated position.
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        amount: Amount of margin to add (USDT)
    
    Returns:
        True if successful
    """
    try:
        manager._validate_trading_operation()
        
        result = manager.bybit.session.add_or_reduce_margin(
            category="linear",
            symbol=symbol,
            margin=str(amount),
            positionIdx=0,  # One-way mode
        )
        manager.logger.info(f"Added {amount} margin to {symbol}")
        return True
    except Exception as e:
        manager.logger.error(f"Add margin failed: {e}")
        return False


# =============================================================================
# Conditional Order Cleanup
# =============================================================================

def cancel_position_conditional_orders(
    manager: "ExchangeManager",
    symbol: str,
    position_side: str,
    require_bot_id: bool = True,
) -> list[str]:
    """
    Cancel conditional orders that would close the given position.
    
    Only cancels orders that are:
    - Conditional (has trigger_price)
    - Reduce-only
    - Same symbol
    - Opposite side to position (would close it)
    - (Optional) Have order_link_id matching bot pattern (TP*_SYMBOL_*)
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        position_side: "long" or "short"
        require_bot_id: If True, only cancel orders with bot-generated order_link_id
    
    Returns:
        List of cancelled order IDs
    """
    from . import exchange_orders_manage as orders
    
    cancelled = []
    
    try:
        # Get all open orders for this symbol
        all_orders = orders.get_open_orders(manager, symbol)
        
        if not all_orders:
            return cancelled
        
        # Determine the side that would close this position
        close_side = "Sell" if position_side == "long" else "Buy"
        
        # Pattern for bot-generated TP/SL orders: TP1_BTCUSDT_1234567890 or SL_BTCUSDT_1234567890
        tp_pattern = re.compile(rf"^(TP\d+|SL)_{re.escape(symbol)}_\d+$")
        
        # Filter for conditional reduce-only orders that would close position
        orders_to_cancel = []
        for order in all_orders:
            if not (order.is_conditional and order.reduce_only and 
                    order.side == close_side and order.is_active):
                continue
            
            # Check order_link_id pattern if required
            if require_bot_id:
                if not order.order_link_id:
                    continue
                if not tp_pattern.match(order.order_link_id):
                    manager.logger.debug(
                        f"Skipping order {order.order_id} - order_link_id '{order.order_link_id}' "
                        f"doesn't match bot pattern"
                    )
                    continue
            
            orders_to_cancel.append(order)
        
        if not orders_to_cancel:
            return cancelled
        
        manager.logger.info(
            f"Cancelling {len(orders_to_cancel)} conditional orders for {symbol} position"
        )
        
        # Cancel each order
        for order in orders_to_cancel:
            try:
                success = orders.cancel_order(
                    manager,
                    symbol=symbol,
                    order_id=order.order_id,
                    order_link_id=order.order_link_id,
                )
                if success:
                    order_identifier = order.order_link_id or order.order_id
                    cancelled.append(order_identifier)
                    manager.logger.debug(
                        f"Cancelled conditional order {order_identifier} "
                        f"({order.side} {order.qty} @ trigger ${order.trigger_price})"
                    )
            except Exception as e:
                # Log but don't fail - individual order cancellation shouldn't block
                manager.logger.warning(
                    f"Failed to cancel order {order.order_id or order.order_link_id}: {e}"
                )
        
        if cancelled:
            manager.logger.info(
                f"Successfully cancelled {len(cancelled)}/{len(orders_to_cancel)} "
                f"conditional orders for {symbol}"
            )
        
    except Exception as e:
        # Don't raise - this is cleanup, not critical
        manager.logger.warning(
            f"Error cancelling conditional orders for {symbol}: {e}"
        )
    
    return cancelled


def reconcile_orphaned_orders(
    manager: "ExchangeManager",
    symbol: str | None = None
) -> dict[str, list[str]]:
    """
    Find and cancel conditional orders for positions that no longer exist.
    
    Critical for long-term operation - if the bot crashes or restarts,
    conditional TP orders may remain active even though positions are closed.
    
    Only cancels orders with bot-generated order_link_id pattern.
    
    Args:
        manager: ExchangeManager instance
        symbol: Specific symbol (None for all symbols)
    
    Returns:
        Dict mapping symbol to list of cancelled order IDs
    """
    from . import exchange_orders_manage as orders
    from .exchange_manager import Order
    
    cancelled_by_symbol: dict[str, list[str]] = {}
    
    try:
        # Get all open positions
        positions = get_all_positions(manager)
        open_symbols = {pos.symbol for pos in positions if pos.is_open}
        
        # Get all open orders
        all_orders = orders.get_open_orders(manager, symbol)
        
        # Group orders by symbol
        orders_by_symbol: dict[str, list[Order]] = {}
        for order in all_orders:
            if order.symbol not in orders_by_symbol:
                orders_by_symbol[order.symbol] = []
            orders_by_symbol[order.symbol].append(order)
        
        # For each symbol with orders
        for order_symbol, symbol_orders in orders_by_symbol.items():
            # Skip if filtering by specific symbol
            if symbol and order_symbol != symbol:
                continue
            
            # Pattern for bot-generated TP/SL orders
            tp_pattern = re.compile(rf"^(TP\d+|SL)_{re.escape(order_symbol)}_\d+$")
            
            # Check if position exists
            has_position = order_symbol in open_symbols
            
            if not has_position:
                # No position - cancel bot-generated conditional reduce-only orders
                orphaned = [
                    o for o in symbol_orders
                    if o.is_conditional 
                    and o.reduce_only 
                    and o.is_active
                    and o.order_link_id
                    and tp_pattern.match(o.order_link_id)
                ]
                
                if orphaned:
                    manager.logger.warning(
                        f"Found {len(orphaned)} orphaned conditional orders for {order_symbol} "
                        f"(no position exists)"
                    )
                    
                    cancelled = []
                    for order in orphaned:
                        try:
                            if orders.cancel_order(
                                manager,
                                symbol=order_symbol,
                                order_id=order.order_id,
                                order_link_id=order.order_link_id,
                            ):
                                cancelled.append(order.order_link_id or order.order_id)
                        except Exception as e:
                            manager.logger.warning(f"Failed to cancel orphaned order: {e}")
                    
                    if cancelled:
                        cancelled_by_symbol[order_symbol] = cancelled
                        manager.logger.info(
                            f"Cancelled {len(cancelled)} orphaned orders for {order_symbol}"
                        )
            else:
                # Position exists - verify orders match position side
                position = next(p for p in positions if p.symbol == order_symbol)
                close_side = "Sell" if position.side == "long" else "Buy"
                
                # Find bot-generated orders on wrong side (would open position, not close)
                mismatched = [
                    o for o in symbol_orders
                    if o.is_conditional
                    and o.reduce_only
                    and o.is_active
                    and o.side != close_side
                    and o.order_link_id
                    and tp_pattern.match(o.order_link_id)
                ]
                
                if mismatched:
                    manager.logger.warning(
                        f"Found {len(mismatched)} mismatched conditional orders for {order_symbol} "
                        f"(wrong side for current position)"
                    )
                    # Cancel mismatched orders
                    cancelled = []
                    for order in mismatched:
                        try:
                            if orders.cancel_order(
                                manager,
                                symbol=order_symbol,
                                order_id=order.order_id,
                                order_link_id=order.order_link_id,
                            ):
                                cancelled.append(order.order_link_id or order.order_id)
                        except Exception as e:
                            manager.logger.warning(f"Failed to cancel mismatched order: {e}")
                    
                    if cancelled:
                        cancelled_by_symbol[order_symbol] = cancelled
    
    except Exception as e:
        manager.logger.error(f"Error reconciling orphaned orders: {e}")
    
    return cancelled_by_symbol


# =============================================================================
# Position Configuration
# =============================================================================

def set_risk_limit_by_id(
    manager: "ExchangeManager",
    symbol: str,
    risk_id: int,
    position_idx: int = 0,
) -> bool:
    """
    Set risk limit for a symbol by risk ID.
    
    Use get_risk_limits() to see available risk IDs and their limits.
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        risk_id: Risk limit ID
        position_idx: 0=one-way, 1=buy-hedge, 2=sell-hedge
    
    Returns:
        True if successful
    """
    try:
        manager.bybit.set_risk_limit(symbol, risk_id, position_idx=position_idx)
        manager.logger.info(f"Set risk limit for {symbol} to ID {risk_id}")
        return True
    except Exception as e:
        manager.logger.error(f"Set risk limit failed: {e}")
        return False


def get_risk_limits(manager: "ExchangeManager", symbol: str | None = None) -> list[dict]:
    """
    Get risk limit tiers for a symbol.
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol (None for all)
    
    Returns:
        List of risk limit tiers
    """
    try:
        return manager.bybit.get_risk_limit(symbol)
    except Exception as e:
        manager.logger.error(f"Get risk limits failed: {e}")
        return []


def set_symbol_tp_sl_mode(manager: "ExchangeManager", symbol: str, full_mode: bool) -> bool:
    """
    Set TP/SL mode for a symbol.
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        full_mode: True for Full (entire position), False for Partial
    
    Returns:
        True if successful
    """
    try:
        mode = "Full" if full_mode else "Partial"
        manager.bybit.set_tp_sl_mode(symbol, mode)
        manager.logger.info(f"Set TP/SL mode for {symbol} to {mode}")
        return True
    except Exception as e:
        # Mode might already be set
        if "not modified" in str(e).lower():
            return True
        manager.logger.error(f"Set TP/SL mode failed: {e}")
        return False


def set_auto_add_margin(manager: "ExchangeManager", symbol: str, enabled: bool) -> bool:
    """
    Enable/disable auto-add-margin for isolated margin position.
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        enabled: True to enable, False to disable
    
    Returns:
        True if successful
    """
    try:
        manager.bybit.set_auto_add_margin(symbol, enabled)
        status = "enabled" if enabled else "disabled"
        manager.logger.info(f"Auto-add-margin {status} for {symbol}")
        return True
    except Exception as e:
        manager.logger.error(f"Set auto-add-margin failed: {e}")
        return False


def modify_position_margin(manager: "ExchangeManager", symbol: str, margin: float) -> bool:
    """
    Add or reduce margin for isolated margin position.
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        margin: Amount to add (positive) or reduce (negative)
    
    Returns:
        True if successful
    """
    try:
        manager.bybit.modify_position_margin(symbol, margin)
        action = "Added" if margin > 0 else "Reduced"
        manager.logger.info(f"{action} {abs(margin)} margin for {symbol}")
        return True
    except Exception as e:
        manager.logger.error(f"Modify position margin failed: {e}")
        return False


def switch_to_cross_margin(manager: "ExchangeManager", symbol: str, leverage: int | None = None) -> bool:
    """
    Switch symbol to cross margin mode.
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        leverage: Leverage to set (uses current if None)
    
    Returns:
        True if successful
    """
    if leverage is None:
        leverage = manager.config.risk.default_leverage
    
    try:
        manager.bybit.switch_cross_isolated_margin(symbol, trade_mode=0, leverage=leverage)
        return True
    except Exception as e:
        if "not modified" in str(e).lower():
            return True
        manager.logger.error(f"Switch to cross margin failed: {e}")
        return False


def switch_to_isolated_margin(manager: "ExchangeManager", symbol: str, leverage: int | None = None) -> bool:
    """
    Switch symbol to isolated margin mode.
    
    Args:
        manager: ExchangeManager instance
        symbol: Trading symbol
        leverage: Leverage to set (uses current if None)
    
    Returns:
        True if successful
    """
    if leverage is None:
        leverage = manager.config.risk.default_leverage
    
    try:
        manager.bybit.switch_cross_isolated_margin(symbol, trade_mode=1, leverage=leverage)
        return True
    except Exception as e:
        if "not modified" in str(e).lower():
            return True
        manager.logger.error(f"Switch to isolated margin failed: {e}")
        return False


def switch_to_one_way_mode(manager: "ExchangeManager") -> bool:
    """
    Switch to one-way position mode for all USDT linear pairs.

    Uses coin="USDT" to batch-switch all USDT perpetuals that have no
    open positions or orders. Bybit V5 requires either symbol or coin.

    Returns:
        True if successful or already in one-way mode
    """
    try:
        manager.bybit.switch_position_mode_v5(mode=0, coin="USDT")
        return True
    except Exception as e:
        if "not modified" in str(e).lower():
            return True
        manager.logger.error(f"Switch to one-way mode failed: {e}")
        return False


def switch_to_hedge_mode(manager: "ExchangeManager") -> bool:
    """
    Switch to hedge position mode for all USDT linear pairs.

    Uses coin="USDT" to batch-switch. Bybit V5 requires either symbol or coin.

    Returns:
        True if successful or already in hedge mode
    """
    try:
        manager.bybit.switch_position_mode_v5(mode=3, coin="USDT")
        return True
    except Exception as e:
        if "not modified" in str(e).lower():
            return True
        manager.logger.error(f"Switch to hedge mode failed: {e}")
        return False


# =============================================================================
# Unified Account Operations
# =============================================================================

def get_transaction_log(
    manager: "ExchangeManager",
    time_range: TimeRange,
    category: str | None = None,
    currency: str | None = None,
    log_type: str | None = None,
    limit: int = 50,
) -> dict:
    """
    Get transaction logs from Unified account.
    
    CRITICAL: TimeRange is REQUIRED. We never rely on Bybit's implicit 24-hour default.
    
    Args:
        manager: ExchangeManager instance
        time_range: Required TimeRange specifying the query window (max 7 days)
        category: spot, linear, option
        currency: Filter by currency
        log_type: TRADE, SETTLEMENT, TRANSFER_IN, TRANSFER_OUT, etc.
        limit: Max results (1-50)
    
    Returns:
        Dict with 'list' and pagination info
    """
    try:
        result = manager.bybit.get_transaction_log(
            time_range=time_range,
            category=category,
            currency=currency,
            log_type=log_type,
            limit=limit,
        )
        return result
    except Exception as e:
        manager.logger.error(f"Get transaction log failed: {e}")
        return {"list": [], "error": str(e)}


def get_collateral_info(manager: "ExchangeManager", currency: str | None = None) -> list[dict]:
    """
    Get collateral information for Unified account.
    
    Args:
        manager: ExchangeManager instance
        currency: Specific currency (None for all)
    
    Returns:
        List of collateral info dicts with fields:
            - currency, availableToBorrow, freeBorrowingAmount
            - borrowUsageRate, marginCollateral, collateralSwitch
            - collateralRatio, etc.
    """
    try:
        return manager.bybit.get_collateral_info(currency)
    except Exception as e:
        manager.logger.error(f"Get collateral info failed: {e}")
        return []


def set_collateral_coin(manager: "ExchangeManager", coin: str, enabled: bool) -> bool:
    """
    Set whether a coin is used as collateral.
    
    Args:
        manager: ExchangeManager instance
        coin: Coin name (e.g., BTC, ETH, USDT)
        enabled: True to enable as collateral, False to disable
    
    Returns:
        True if successful
    """
    try:
        switch = "ON" if enabled else "OFF"
        manager.bybit.set_collateral_coin(coin, switch)
        manager.logger.info(f"Set {coin} as collateral: {switch}")
        return True
    except Exception as e:
        manager.logger.error(f"Set collateral coin failed: {e}")
        return False


def get_borrow_history(
    manager: "ExchangeManager",
    time_range: TimeRange,
    currency: str | None = None,
    limit: int = 50,
) -> dict:
    """
    Get borrow/interest history.
    
    CRITICAL: TimeRange is REQUIRED. We never rely on Bybit's implicit 30-day default.
    
    Args:
        manager: ExchangeManager instance
        time_range: Required TimeRange specifying the query window (max 30 days)
        currency: e.g., USDC, USDT, BTC
        limit: Max results
    
    Returns:
        Dict with 'list' of borrow records
    """
    try:
        result = manager.bybit.get_borrow_history(
            time_range=time_range,
            currency=currency,
            limit=limit,
        )
        return result
    except Exception as e:
        manager.logger.error(f"Get borrow history failed: {e}")
        return {"list": [], "error": str(e)}


def get_coin_greeks(manager: "ExchangeManager", base_coin: str | None = None) -> list[dict]:
    """
    Get current account Greeks information (for options).
    
    Args:
        manager: ExchangeManager instance
        base_coin: Base coin filter (BTC, ETH, etc.)
    
    Returns:
        List of coin greeks dicts
    """
    try:
        return manager.bybit.get_coin_greeks(base_coin)
    except Exception as e:
        manager.logger.error(f"Get coin greeks failed: {e}")
        return []


def set_account_margin_mode(manager: "ExchangeManager", portfolio_margin: bool) -> bool:
    """
    Set account-level margin mode for Unified account.
    
    Args:
        manager: ExchangeManager instance
        portfolio_margin: True for PORTFOLIO_MARGIN, False for REGULAR_MARGIN
    
    Returns:
        True if successful
    """
    try:
        mode = "PORTFOLIO_MARGIN" if portfolio_margin else "REGULAR_MARGIN"
        manager.bybit.set_account_margin_mode(mode)
        manager.logger.info(f"Set account margin mode to {mode}")
        return True
    except Exception as e:
        # Mode might already be set
        if "not modified" in str(e).lower():
            return True
        manager.logger.error(f"Set account margin mode failed: {e}")
        return False


def get_transferable_amount(manager: "ExchangeManager", coin: str) -> float:
    """
    Get the available amount to transfer for a specific coin.
    
    Args:
        manager: ExchangeManager instance
        coin: Coin name (uppercase, e.g., USDT)
    
    Returns:
        Transferable amount as float
    """
    try:
        result = manager.bybit.get_transferable_amount(coin)
        return safe_float(result.get("transferableAmount", 0))
    except Exception as e:
        manager.logger.error(f"Get transferable amount failed: {e}")
        return 0.0

