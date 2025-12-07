"""
Account management tools for TRADE trading bot.

These tools provide account balance, exposure, and portfolio-level operations.

CRITICAL: All history tools require explicit time ranges. We never rely on
Bybit's implicit defaults (24h for transaction log, 7d for orders, etc.).

All trading tools accept an optional `trading_env` parameter for agent/orchestrator
use. This parameter VALIDATES the caller's intent against the process config but
does NOT switch environments. If the env doesn't match, the tool returns an error.
"""

from typing import Optional, Dict, Any
from .shared import ToolResult, _get_exchange_manager, _get_realtime_state, _is_websocket_connected, validate_trading_env_or_error
from ..utils.time_range import TimeRange, parse_time_window


def get_account_balance_tool(trading_env: Optional[str] = None) -> ToolResult:
    """
    Get account balance information.
    
    Args:
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with data containing:
            - total: Total balance in USD
            - available: Available balance for trading
            - used: Balance currently in use (margin)
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        exchange = _get_exchange_manager()
        balance = exchange.get_balance()
        
        return ToolResult(
            success=True,
            message=f"Balance: ${balance.get('total', 0):,.2f}",
            data={
                "total": balance.get("total", 0),
                "available": balance.get("available", 0),
                "used": balance.get("used", 0),
                "raw": balance,
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get balance: {str(e)}",
        )


def get_total_exposure_tool(trading_env: Optional[str] = None) -> ToolResult:
    """
    Get total position exposure across all positions.
    
    Args:
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with data containing exposure in USD
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        exchange = _get_exchange_manager()
        exposure = exchange.get_total_exposure()
        
        return ToolResult(
            success=True,
            message=f"Total exposure: ${exposure:,.2f}",
            data={"exposure_usd": exposure},
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get exposure: {str(e)}",
        )


def get_account_info_tool(trading_env: Optional[str] = None) -> ToolResult:
    """
    Get detailed account information (margin mode, etc.).
    
    Args:
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with account configuration details
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        exchange = _get_exchange_manager()
        account_info = exchange.bybit.get_account_info()
        
        return ToolResult(
            success=True,
            message=f"Margin mode: {account_info.get('marginMode', 'N/A')}",
            data={
                "margin_mode": account_info.get("marginMode", "N/A"),
                "unified_margin_status": account_info.get("unifiedMarginStatus", "N/A"),
                "raw": account_info,
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get account info: {str(e)}",
        )


def get_portfolio_snapshot_tool(trading_env: Optional[str] = None) -> ToolResult:
    """
    Get a comprehensive portfolio snapshot using GlobalRiskView.
    
    Includes equity, margin rates, position counts, exposure breakdown,
    and risk level assessment.
    
    Args:
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with comprehensive portfolio data
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        from ..risk import get_global_risk_view
        
        risk_view = get_global_risk_view()
        snapshot = risk_view.build_snapshot()
        
        # Only return if we have real data
        if snapshot.total_equity <= 0 and snapshot.total_position_count == 0:
            return ToolResult(
                success=False,
                error="Global risk data not available - WebSocket may not be connected",
            )
        
        data = {
            "total_equity": snapshot.total_equity,
            "total_available_balance": snapshot.total_available_balance,
            "account_im_rate": snapshot.account_im_rate,
            "account_mm_rate": snapshot.account_mm_rate,
            "liquidation_risk_level": snapshot.liquidation_risk_level,
            "total_position_count": snapshot.total_position_count,
            "total_notional_usd": snapshot.total_notional_usd,
            "long_exposure_usd": snapshot.long_exposure_usd,
            "short_exposure_usd": snapshot.short_exposure_usd,
            "net_exposure_usd": snapshot.net_exposure_usd,
            "worst_liq_distance_pct": snapshot.worst_liq_distance_pct,
            "worst_liq_symbol": snapshot.worst_liq_symbol,
            "weighted_leverage": snapshot.weighted_leverage,
            "high_risk_position_count": snapshot.high_risk_position_count,
            "has_liquidating_positions": snapshot.has_liquidating_positions,
            "has_adl_positions": snapshot.has_adl_positions,
            "has_reduce_only_positions": snapshot.has_reduce_only_positions,
            "positions_near_liq": snapshot.positions_near_liq,
            "exposure_by_asset": dict(snapshot.exposure_by_asset) if snapshot.exposure_by_asset else {},
        }
        
        return ToolResult(
            success=True,
            message=f"Portfolio: ${snapshot.total_equity:,.2f} equity, {snapshot.total_position_count} positions",
            data=data,
            source="websocket",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get portfolio snapshot: {str(e)}",
        )


def get_order_history_tool(
    window: Optional[str] = None,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    symbol: Optional[str] = None,
    limit: int = 50,
    trading_env: Optional[str] = None,
) -> ToolResult:
    """
    Get order history within a specified time range.
    
    CRITICAL: A time range is REQUIRED. Either provide 'window' OR both 'start_ms' and 'end_ms'.
    Defaults to last 7 days if nothing provided.
    
    Args:
        window: Time window string (e.g., "24h", "7d"). Max 7 days.
        start_ms: Start timestamp in milliseconds (used if window not provided)
        end_ms: End timestamp in milliseconds (used if window not provided)
        symbol: Filter by symbol (None for all)
        limit: Maximum number of orders to return (1-50)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with list of orders and time_range metadata
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        # Parse time range (defaults to 7d for order history)
        time_range = parse_time_window(
            window=window,
            start_ms=start_ms,
            end_ms=end_ms,
            endpoint_type="order_history",
            default_window="7d",
        )
        
        exchange = _get_exchange_manager()
        orders = exchange.get_order_history(
            time_range=time_range,
            symbol=symbol,
            limit=limit,
        )
        
        return ToolResult(
            success=True,
            message=f"Retrieved {len(orders)} orders ({time_range.label})",
            data={
                "orders": orders,
                "count": len(orders),
                "time_range": time_range.to_dict(),
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get order history: {str(e)}",
        )


def get_closed_pnl_tool(
    window: Optional[str] = None,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    symbol: Optional[str] = None,
    limit: int = 50,
    trading_env: Optional[str] = None,
) -> ToolResult:
    """
    Get closed P&L records within a specified time range.
    
    CRITICAL: A time range is REQUIRED. Either provide 'window' OR both 'start_ms' and 'end_ms'.
    Defaults to last 7 days if nothing provided.
    
    Args:
        window: Time window string (e.g., "24h", "7d"). Max 7 days.
        start_ms: Start timestamp in milliseconds (used if window not provided)
        end_ms: End timestamp in milliseconds (used if window not provided)
        symbol: Filter by symbol (None for all)
        limit: Maximum number of records to return (1-50)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with closed P&L data, total, and time_range metadata
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        # Parse time range (defaults to 7d for closed PnL)
        time_range = parse_time_window(
            window=window,
            start_ms=start_ms,
            end_ms=end_ms,
            endpoint_type="closed_pnl",
            default_window="7d",
        )
        
        exchange = _get_exchange_manager()
        closed_pnl = exchange.get_closed_pnl(
            time_range=time_range,
            symbol=symbol,
            limit=limit,
        )
        
        total_pnl = sum(float(p.get('closedPnl', 0)) for p in closed_pnl)
        
        return ToolResult(
            success=True,
            message=f"Closed PnL: ${total_pnl:,.2f} ({len(closed_pnl)} trades, {time_range.label})",
            data={
                "records": closed_pnl,
                "count": len(closed_pnl),
                "total_pnl": total_pnl,
                "time_range": time_range.to_dict(),
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get closed PnL: {str(e)}",
        )


# ==============================================================================
# Unified Account Tools
# ==============================================================================

def get_transaction_log_tool(
    window: Optional[str] = None,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    category: Optional[str] = None,
    currency: Optional[str] = None,
    log_type: Optional[str] = None,
    limit: int = 50,
    trading_env: Optional[str] = None,
) -> ToolResult:
    """
    Get transaction logs from Unified account within a specified time range.
    
    CRITICAL: A time range is REQUIRED. Either provide 'window' OR both 'start_ms' and 'end_ms'.
    Defaults to last 7 days if nothing provided (max for transaction log is 7 days).
    
    Args:
        window: Time window string (e.g., "24h", "7d"). Max 7 days.
        start_ms: Start timestamp in milliseconds (used if window not provided)
        end_ms: End timestamp in milliseconds (used if window not provided)
        category: spot, linear, option (None for all)
        currency: Filter by currency (e.g., USDT, BTC)
        log_type: TRADE, SETTLEMENT, TRANSFER_IN, TRANSFER_OUT,
                 DELIVERY, LIQUIDATION, BONUS, FEE_REFUND, INTEREST
        limit: Maximum records (1-50)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with transaction log data and time_range metadata
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        # Parse time range (defaults to 7d for transaction log)
        time_range = parse_time_window(
            window=window,
            start_ms=start_ms,
            end_ms=end_ms,
            endpoint_type="transaction_log",
            default_window="7d",
        )
        
        exchange = _get_exchange_manager()
        result = exchange.get_transaction_log(
            time_range=time_range,
            category=category,
            currency=currency,
            log_type=log_type,
            limit=limit,
        )
        
        records = result.get("list", [])
        
        return ToolResult(
            success=True,
            message=f"Retrieved {len(records)} transaction log entries ({time_range.label})",
            data={
                "records": records,
                "count": len(records),
                "nextPageCursor": result.get("nextPageCursor"),
                "time_range": time_range.to_dict(),
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get transaction log: {str(e)}",
        )


def get_collateral_info_tool(currency: Optional[str] = None, trading_env: Optional[str] = None) -> ToolResult:
    """
    Get collateral information for Unified account.
    
    Args:
        currency: Specific currency (None for all)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with collateral info (rates, limits, status)
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        exchange = _get_exchange_manager()
        collateral_info = exchange.get_collateral_info(currency)
        
        # Summarize enabled collateral
        enabled = [c for c in collateral_info if c.get("collateralSwitch") == "ON"]
        
        return ToolResult(
            success=True,
            message=f"Collateral info: {len(enabled)}/{len(collateral_info)} coins enabled",
            data={
                "collateral_info": collateral_info,
                "total_coins": len(collateral_info),
                "enabled_count": len(enabled),
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get collateral info: {str(e)}",
        )


def set_collateral_coin_tool(coin: str, enabled: bool, trading_env: Optional[str] = None) -> ToolResult:
    """
    Enable or disable a coin as collateral.
    
    Args:
        coin: Coin name (e.g., BTC, ETH, USDT)
        enabled: True to enable, False to disable
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not coin or not isinstance(coin, str):
        return ToolResult(success=False, error="Invalid coin parameter")
    
    try:
        exchange = _get_exchange_manager()
        success = exchange.set_collateral_coin(coin.upper(), enabled)
        
        action = "enabled" if enabled else "disabled"
        
        if success:
            return ToolResult(
                success=True,
                message=f"Collateral {action} for {coin.upper()}",
                data={"coin": coin.upper(), "enabled": enabled},
            )
        else:
            return ToolResult(
                success=False,
                error=f"Failed to {action} collateral for {coin}",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to set collateral: {str(e)}",
        )


def get_borrow_history_tool(
    window: Optional[str] = None,
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    currency: Optional[str] = None,
    limit: int = 50,
    trading_env: Optional[str] = None,
) -> ToolResult:
    """
    Get borrow/interest history within a specified time range.
    
    CRITICAL: A time range is REQUIRED. Either provide 'window' OR both 'start_ms' and 'end_ms'.
    Defaults to last 30 days if nothing provided (max for borrow history is 30 days).
    
    Args:
        window: Time window string (e.g., "7d", "30d"). Max 30 days.
        start_ms: Start timestamp in milliseconds (used if window not provided)
        end_ms: End timestamp in milliseconds (used if window not provided)
        currency: Filter by currency (e.g., USDT, BTC)
        limit: Maximum records (1-50)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with borrow history records and time_range metadata
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        # Parse time range (defaults to 30d for borrow history)
        time_range = parse_time_window(
            window=window,
            start_ms=start_ms,
            end_ms=end_ms,
            endpoint_type="borrow_history",
            default_window="30d",
        )
        
        exchange = _get_exchange_manager()
        result = exchange.get_borrow_history(
            time_range=time_range,
            currency=currency,
            limit=limit,
        )
        
        records = result.get("list", [])
        
        return ToolResult(
            success=True,
            message=f"Retrieved {len(records)} borrow history entries ({time_range.label})",
            data={
                "records": records,
                "count": len(records),
                "time_range": time_range.to_dict(),
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get borrow history: {str(e)}",
        )


def get_coin_greeks_tool(base_coin: Optional[str] = None, trading_env: Optional[str] = None) -> ToolResult:
    """
    Get account Greeks information (for options).
    
    Args:
        base_coin: Base coin filter (BTC, ETH, etc.)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with coin greeks data
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        exchange = _get_exchange_manager()
        greeks = exchange.get_coin_greeks(base_coin)
        
        return ToolResult(
            success=True,
            message=f"Retrieved Greeks for {len(greeks)} coin(s)",
            data={
                "greeks": greeks,
                "count": len(greeks),
            },
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get coin greeks: {str(e)}",
        )


def set_account_margin_mode_tool(portfolio_margin: bool, trading_env: Optional[str] = None) -> ToolResult:
    """
    Set account-level margin mode.
    
    Args:
        portfolio_margin: True for Portfolio Margin, False for Regular Margin
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with success status
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    try:
        exchange = _get_exchange_manager()
        success = exchange.set_account_margin_mode(portfolio_margin)
        
        mode = "Portfolio Margin" if portfolio_margin else "Regular Margin"
        
        if success:
            return ToolResult(
                success=True,
                message=f"Account margin mode set to {mode}",
                data={"portfolio_margin": portfolio_margin, "mode": mode},
            )
        else:
            return ToolResult(
                success=False,
                error=f"Failed to set account margin mode to {mode}",
            )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to set margin mode: {str(e)}",
        )


def get_transferable_amount_tool(coin: str, trading_env: Optional[str] = None) -> ToolResult:
    """
    Get the available amount to transfer for a coin.
    
    Args:
        coin: Coin name (e.g., USDT, BTC)
        trading_env: Optional trading environment ("demo" or "live") for validation
    
    Returns:
        ToolResult with transferable amount
    """
    if error := validate_trading_env_or_error(trading_env):
        return error
    
    if not coin or not isinstance(coin, str):
        return ToolResult(success=False, error="Invalid coin parameter")
    
    try:
        exchange = _get_exchange_manager()
        amount = exchange.get_transferable_amount(coin.upper())
        
        return ToolResult(
            success=True,
            message=f"Transferable {coin.upper()}: {amount:,.4f}",
            data={"coin": coin.upper(), "transferable_amount": amount},
            source="rest_api",
        )
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to get transferable amount: {str(e)}",
        )

