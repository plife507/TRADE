"""
CLI Display Helpers - Finance/Trading Themed Action Descriptions

This module provides emoji-enhanced, high-verbosity status messages for CLI actions.
It is stateless and CLI-only - no tool imports or exchange logic.

Usage:
    from src.utils.cli_display import format_action_status, format_action_complete
    
    status_msg = format_action_status("account.view_balance")
    # Returns: "💰 Fetching account balance..."
"""

from typing import Any
from dataclasses import dataclass


# =============================================================================
# ACTION DESCRIPTORS - Maps action_key to emoji + description
# =============================================================================

@dataclass
class ActionDescriptor:
    """Describes a CLI action with emoji and description templates."""
    emoji: str
    label: str
    running_template: str  # Template for "running" status, supports {param} interpolation
    complete_template: str  # Template for completion summary


# Centralized action registry - finance/trading themed
ACTION_REGISTRY: dict[str, ActionDescriptor] = {
    # ==================== ACCOUNT ====================
    "account.view_balance": ActionDescriptor(
        emoji="💰",
        label="Account Balance",
        running_template="Fetching account balance...",
        complete_template="Retrieved account balance"
    ),
    "account.view_exposure": ActionDescriptor(
        emoji="📊",
        label="Exposure Check",
        running_template="Calculating total exposure and margin usage...",
        complete_template="Exposure calculated"
    ),
    "account.info": ActionDescriptor(
        emoji="📋",
        label="Account Info",
        running_template="Fetching account details and margin settings...",
        complete_template="Account info retrieved"
    ),
    "account.portfolio": ActionDescriptor(
        emoji="💼",
        label="Portfolio Snapshot",
        running_template="Building complete portfolio snapshot with positions and PnL...",
        complete_template="Portfolio snapshot complete"
    ),
    "account.order_history": ActionDescriptor(
        emoji="📜",
        label="Order History",
        running_template="Fetching order history for {window}...",
        complete_template="Order history retrieved"
    ),
    "account.closed_pnl": ActionDescriptor(
        emoji="💵",
        label="Closed PnL",
        running_template="Fetching closed PnL for {window}...",
        complete_template="Closed PnL retrieved"
    ),
    "account.transaction_log": ActionDescriptor(
        emoji="📒",
        label="Transaction Log",
        running_template="Fetching transaction log for {window}...",
        complete_template="Transaction log retrieved"
    ),
    "account.collateral_info": ActionDescriptor(
        emoji="🏦",
        label="Collateral Info",
        running_template="Fetching collateral coin settings...",
        complete_template="Collateral info retrieved"
    ),
    "account.set_collateral": ActionDescriptor(
        emoji="🔧",
        label="Set Collateral",
        running_template="Updating collateral setting for {coin}...",
        complete_template="Collateral setting updated"
    ),
    "account.borrow_history": ActionDescriptor(
        emoji="📝",
        label="Borrow History",
        running_template="Fetching borrow history for {window}...",
        complete_template="Borrow history retrieved"
    ),
    "account.coin_greeks": ActionDescriptor(
        emoji="📐",
        label="Coin Greeks",
        running_template="Fetching options Greeks...",
        complete_template="Greeks retrieved"
    ),
    "account.set_margin_mode": ActionDescriptor(
        emoji="⚙️",
        label="Margin Mode",
        running_template="Switching account margin mode...",
        complete_template="Margin mode updated"
    ),
    "account.transferable": ActionDescriptor(
        emoji="💸",
        label="Transferable Amount",
        running_template="Checking transferable amount for {coin}...",
        complete_template="Transferable amount retrieved"
    ),
    
    # ==================== POSITIONS ====================
    "positions.list": ActionDescriptor(
        emoji="📈",
        label="Open Positions",
        running_template="Fetching all open positions...",
        complete_template="Positions retrieved"
    ),
    "positions.detail": ActionDescriptor(
        emoji="🔍",
        label="Position Detail",
        running_template="Fetching detailed position info for {symbol}...",
        complete_template="Position detail retrieved"
    ),
    "positions.set_stop_loss": ActionDescriptor(
        emoji="🛡️",
        label="Set Stop Loss",
        running_template="Setting stop loss for {symbol} at ${price}...",
        complete_template="Stop loss set"
    ),
    "positions.set_take_profit": ActionDescriptor(
        emoji="🎯",
        label="Set Take Profit",
        running_template="Setting take profit for {symbol} at ${price}...",
        complete_template="Take profit set"
    ),
    "positions.set_tpsl": ActionDescriptor(
        emoji="🛡️🎯",
        label="Set TP/SL",
        running_template="Setting TP/SL for {symbol}...",
        complete_template="TP/SL configured"
    ),
    "positions.partial_close": ActionDescriptor(
        emoji="✂️",
        label="Partial Close",
        running_template="Partially closing {percent}% of {symbol} position...",
        complete_template="Partial close executed"
    ),
    "positions.close": ActionDescriptor(
        emoji="🚪",
        label="Close Position",
        running_template="Closing entire {symbol} position at market...",
        complete_template="Position closed"
    ),
    "positions.close_all": ActionDescriptor(
        emoji="🚨",
        label="Close All Positions",
        running_template="EMERGENCY: Closing ALL positions at market...",
        complete_template="All positions closed"
    ),
    "positions.risk_limits": ActionDescriptor(
        emoji="📊",
        label="Risk Limits",
        running_template="Fetching risk limit tiers for {symbol}...",
        complete_template="Risk limits retrieved"
    ),
    "positions.set_risk_limit": ActionDescriptor(
        emoji="⚖️",
        label="Set Risk Limit",
        running_template="Setting risk limit ID {risk_id} for {symbol}...",
        complete_template="Risk limit set"
    ),
    "positions.set_tpsl_mode": ActionDescriptor(
        emoji="🔄",
        label="TP/SL Mode",
        running_template="Setting TP/SL mode for {symbol}...",
        complete_template="TP/SL mode updated"
    ),
    "positions.switch_margin_mode": ActionDescriptor(
        emoji="🔀",
        label="Margin Mode",
        running_template="Switching margin mode for {symbol}...",
        complete_template="Margin mode switched"
    ),
    "positions.auto_add_margin": ActionDescriptor(
        emoji="➕",
        label="Auto-Add Margin",
        running_template="Configuring auto-add margin for {symbol}...",
        complete_template="Auto-add margin configured"
    ),
    "positions.modify_margin": ActionDescriptor(
        emoji="💵",
        label="Modify Margin",
        running_template="Modifying position margin for {symbol}...",
        complete_template="Position margin modified"
    ),
    "positions.switch_mode": ActionDescriptor(
        emoji="🔄",
        label="Position Mode",
        running_template="Switching position mode (one-way/hedge)...",
        complete_template="Position mode switched"
    ),
    
    # ==================== ORDERS ====================
    "orders.market_buy": ActionDescriptor(
        emoji="📈🟢",
        label="Market Buy",
        running_template="Executing market BUY for {symbol} (${usd_amount})...",
        complete_template="Market buy executed"
    ),
    "orders.market_sell": ActionDescriptor(
        emoji="📉🔴",
        label="Market Sell",
        running_template="Executing market SELL for {symbol} (${usd_amount})...",
        complete_template="Market sell executed"
    ),
    "orders.market_buy_tpsl": ActionDescriptor(
        emoji="📈🛡️",
        label="Market Buy + TP/SL",
        running_template="Executing market BUY for {symbol} (${usd_amount}) with TP/SL...",
        complete_template="Market buy with TP/SL executed"
    ),
    "orders.market_sell_tpsl": ActionDescriptor(
        emoji="📉🛡️",
        label="Market Sell + TP/SL",
        running_template="Executing market SELL for {symbol} (${usd_amount}) with TP/SL...",
        complete_template="Market sell with TP/SL executed"
    ),
    "orders.limit_buy": ActionDescriptor(
        emoji="📋🟢",
        label="Limit Buy",
        running_template="Placing limit BUY for {symbol} at ${price} (${usd_amount})...",
        complete_template="Limit buy placed"
    ),
    "orders.limit_sell": ActionDescriptor(
        emoji="📋🔴",
        label="Limit Sell",
        running_template="Placing limit SELL for {symbol} at ${price} (${usd_amount})...",
        complete_template="Limit sell placed"
    ),
    "orders.stop_market_buy": ActionDescriptor(
        emoji="⏱️🟢",
        label="Stop Market Buy",
        running_template="Placing stop market BUY for {symbol} (trigger: ${trigger})...",
        complete_template="Stop market buy placed"
    ),
    "orders.stop_market_sell": ActionDescriptor(
        emoji="⏱️🔴",
        label="Stop Market Sell",
        running_template="Placing stop market SELL for {symbol} (trigger: ${trigger})...",
        complete_template="Stop market sell placed"
    ),
    "orders.stop_limit_buy": ActionDescriptor(
        emoji="⏱️📋🟢",
        label="Stop Limit Buy",
        running_template="Placing stop limit BUY for {symbol} (trigger: ${trigger}, limit: ${limit})...",
        complete_template="Stop limit buy placed"
    ),
    "orders.stop_limit_sell": ActionDescriptor(
        emoji="⏱️📋🔴",
        label="Stop Limit Sell",
        running_template="Placing stop limit SELL for {symbol} (trigger: ${trigger}, limit: ${limit})...",
        complete_template="Stop limit sell placed"
    ),
    "orders.list_open": ActionDescriptor(
        emoji="📋",
        label="Open Orders",
        running_template="Fetching open orders{for_symbol}...",
        complete_template="Open orders retrieved"
    ),
    "orders.amend": ActionDescriptor(
        emoji="✏️",
        label="Amend Order",
        running_template="Amending order for {symbol}...",
        complete_template="Order amended"
    ),
    "orders.cancel": ActionDescriptor(
        emoji="❌",
        label="Cancel Order",
        running_template="Cancelling order for {symbol}...",
        complete_template="Order cancelled"
    ),
    "orders.cancel_all": ActionDescriptor(
        emoji="🗑️",
        label="Cancel All Orders",
        running_template="Cancelling all open orders{for_symbol}...",
        complete_template="All orders cancelled"
    ),
    "orders.set_leverage": ActionDescriptor(
        emoji="⚡",
        label="Set Leverage",
        running_template="Setting leverage for {symbol} to {leverage}x...",
        complete_template="Leverage set"
    ),
    
    # ==================== MARKET DATA ====================
    "market.price": ActionDescriptor(
        emoji="💲",
        label="Get Price",
        running_template="Fetching current price for {symbol}...",
        complete_template="Price retrieved"
    ),
    "market.ohlcv": ActionDescriptor(
        emoji="📊",
        label="OHLCV Data",
        running_template="Fetching {limit} candles for {symbol} ({interval})...",
        complete_template="OHLCV data retrieved"
    ),
    "market.funding": ActionDescriptor(
        emoji="💱",
        label="Funding Rate",
        running_template="Fetching funding rate for {symbol}...",
        complete_template="Funding rate retrieved"
    ),
    "market.open_interest": ActionDescriptor(
        emoji="📈",
        label="Open Interest",
        running_template="Fetching open interest for {symbol}...",
        complete_template="Open interest retrieved"
    ),
    "market.orderbook": ActionDescriptor(
        emoji="📚",
        label="Orderbook",
        running_template="Fetching orderbook depth for {symbol} (depth: {limit})...",
        complete_template="Orderbook retrieved"
    ),
    "market.instruments": ActionDescriptor(
        emoji="🔧",
        label="Instruments",
        running_template="Fetching instrument specifications...",
        complete_template="Instruments retrieved"
    ),
    "market.test": ActionDescriptor(
        emoji="🧪",
        label="Market Data Test",
        running_template="Testing all market data endpoints for {symbol}...",
        complete_template="Market data tests complete"
    ),
    
    # ==================== DATA BUILDER ====================
    "data.stats": ActionDescriptor(
        emoji="📊",
        label="Database Stats",
        running_template="Fetching database statistics...",
        complete_template="Database stats retrieved"
    ),
    "data.list_symbols": ActionDescriptor(
        emoji="📋",
        label="Cached Symbols",
        running_template="Listing all cached symbols in database...",
        complete_template="Cached symbols listed"
    ),
    "data.symbol_status": ActionDescriptor(
        emoji="📈",
        label="Symbol Status",
        running_template="Fetching aggregate status{for_symbol}...",
        complete_template="Symbol status retrieved"
    ),
    "data.symbol_summary": ActionDescriptor(
        emoji="📋",
        label="Symbol Summary",
        running_template="Building high-level symbol summary...",
        complete_template="Symbol summary complete"
    ),
    "data.timeframe_ranges": ActionDescriptor(
        emoji="📅",
        label="Timeframe Ranges",
        running_template="Fetching detailed timeframe ranges{for_symbol}...",
        complete_template="Timeframe ranges retrieved"
    ),
    "data.build_full_history": ActionDescriptor(
        emoji="🏗️",
        label="Build Full History",
        running_template="Building full history for {symbols} ({period}): OHLCV + Funding + OI...",
        complete_template="Full history build complete"
    ),
    "data.sync_to_now": ActionDescriptor(
        emoji="🔄",
        label="Sync Forward",
        running_template="Syncing {symbols} forward to now (new candles only)...",
        complete_template="Forward sync complete"
    ),
    "data.sync_to_now_fill_gaps": ActionDescriptor(
        emoji="🔄🔧",
        label="Sync + Fill Gaps",
        running_template="Syncing {symbols} forward and filling gaps...",
        complete_template="Sync and gap fill complete"
    ),
    "data.sync_ohlcv_period": ActionDescriptor(
        emoji="📊",
        label="Sync OHLCV",
        running_template="Syncing OHLCV for {symbols} ({period})...",
        complete_template="OHLCV sync complete"
    ),
    "data.sync_ohlcv_range": ActionDescriptor(
        emoji="📅",
        label="Sync Date Range",
        running_template="Syncing OHLCV for {symbols} ({start} to {end})...",
        complete_template="Date range sync complete"
    ),
    "data.sync_funding": ActionDescriptor(
        emoji="💱",
        label="Sync Funding",
        running_template="Syncing funding rates for {symbols} ({period})...",
        complete_template="Funding rate sync complete"
    ),
    "data.sync_open_interest": ActionDescriptor(
        emoji="📈",
        label="Sync Open Interest",
        running_template="Syncing open interest for {symbols} ({period}, {interval})...",
        complete_template="Open interest sync complete"
    ),
    "data.fill_gaps": ActionDescriptor(
        emoji="🔧",
        label="Fill Gaps",
        running_template="Detecting and filling gaps in data{for_symbol}...",
        complete_template="Gap fill complete"
    ),
    "data.heal": ActionDescriptor(
        emoji="🩹",
        label="Heal Data",
        running_template="Running data integrity check and repair{for_symbol}...",
        complete_template="Data healing complete"
    ),
    "data.delete_symbol": ActionDescriptor(
        emoji="🗑️",
        label="Delete Symbol",
        running_template="Deleting all data for {symbol}...",
        complete_template="Symbol data deleted"
    ),
    "data.cleanup_empty": ActionDescriptor(
        emoji="🧹",
        label="Cleanup Empty",
        running_template="Cleaning up empty/invalid symbols...",
        complete_template="Cleanup complete"
    ),
    "data.vacuum": ActionDescriptor(
        emoji="🗜️",
        label="Vacuum Database",
        running_template="Vacuuming database to reclaim space...",
        complete_template="Vacuum complete"
    ),
    
    # ==================== DIAGNOSTICS ====================
    "diagnostics.connection": ActionDescriptor(
        emoji="🔌",
        label="Connection Test",
        running_template="Testing connection to Bybit API...",
        complete_template="Connection test complete"
    ),
    "diagnostics.server_time": ActionDescriptor(
        emoji="⏰",
        label="Server Time",
        running_template="Checking server time offset...",
        complete_template="Server time retrieved"
    ),
    "diagnostics.rate_limits": ActionDescriptor(
        emoji="⏱️",
        label="Rate Limits",
        running_template="Checking API rate limit status...",
        complete_template="Rate limit status retrieved"
    ),
    "diagnostics.ticker": ActionDescriptor(
        emoji="📊",
        label="Ticker Test",
        running_template="Fetching ticker for {symbol}...",
        complete_template="Ticker retrieved"
    ),
    "diagnostics.health_check": ActionDescriptor(
        emoji="🏥",
        label="Health Check",
        running_template="Running comprehensive exchange health check for {symbol}...",
        complete_template="Health check complete"
    ),
    "diagnostics.websocket": ActionDescriptor(
        emoji="🔗",
        label="WebSocket Status",
        running_template="Checking WebSocket connection status...",
        complete_template="WebSocket status retrieved"
    ),
    "diagnostics.api_env": ActionDescriptor(
        emoji="🔑",
        label="API Environment",
        running_template="Fetching API environment configuration...",
        complete_template="API environment retrieved"
    ),
    
    # ==================== PANIC ====================
    "panic.close_all": ActionDescriptor(
        emoji="🚨",
        label="PANIC",
        running_template="EMERGENCY: Cancelling orders and closing ALL positions...",
        complete_template="Panic close complete"
    ),
}


# =============================================================================
# FORMATTING FUNCTIONS
# =============================================================================

def format_action_status(action_key: str, **params) -> str:
    """
    Generate an emoji-enhanced, high-verbosity status message.
    
    Args:
        action_key: Key like "account.view_balance" or "data.build_full_history"
        **params: Parameters to interpolate into the template (symbol, symbols, period, etc.)
    
    Returns:
        Formatted status string with emoji prefix
    
    Example:
        >>> format_action_status("data.build_full_history", symbols=["BTCUSDT", "ETHUSDT"], period="1M")
        "🏗️ Building full history for ['BTCUSDT', 'ETHUSDT'] (1M): OHLCV + Funding + OI..."
    """
    descriptor = ACTION_REGISTRY.get(action_key)
    
    if not descriptor:
        # Fallback for unknown actions
        return f"⏳ Running operation..."
    
    # Process special param formatting
    formatted_params = _format_params(params)
    
    try:
        message = descriptor.running_template.format(**formatted_params)
    except KeyError:
        # If template params missing, use simple message
        message = descriptor.running_template
    
    return f"{descriptor.emoji} {message}"


def format_action_complete(action_key: str, **params) -> str:
    """
    Generate a completion message for an action.
    
    Args:
        action_key: Key like "account.view_balance"
        **params: Parameters for interpolation
    
    Returns:
        Formatted completion string
    """
    descriptor = ACTION_REGISTRY.get(action_key)
    
    if not descriptor:
        return "Operation complete"
    
    formatted_params = _format_params(params)
    
    try:
        message = descriptor.complete_template.format(**formatted_params)
    except KeyError:
        message = descriptor.complete_template
    
    return f"{descriptor.emoji} {message}"


def get_action_label(action_key: str) -> str:
    """Get the short label for an action."""
    descriptor = ACTION_REGISTRY.get(action_key)
    if descriptor:
        return f"{descriptor.emoji} {descriptor.label}"
    return "Operation"


def _format_params(params: dict[str, Any]) -> dict[str, str]:
    """
    Format parameters for template interpolation.
    
    Handles common transformations:
    - Lists (symbols) -> comma-separated string
    - Datetime objects -> date string
    - Optional "for_symbol" suffix for filtering operations
    """
    from datetime import datetime
    
    formatted = {}
    
    for key, value in params.items():
        if isinstance(value, list):
            # Format lists as comma-separated
            if len(value) <= 3:
                formatted[key] = ", ".join(str(v) for v in value)
            else:
                formatted[key] = f"{', '.join(str(v) for v in value[:3])} +{len(value)-3} more"
        elif isinstance(value, datetime):
            # Format datetime as date string
            formatted[key] = value.strftime("%Y-%m-%d")
        elif value is None:
            formatted[key] = ""
        else:
            formatted[key] = str(value)
    
    # Special handling for optional "for_symbol" suffix
    if "symbol" in params and params["symbol"]:
        formatted["for_symbol"] = f" for {params['symbol']}"
    else:
        formatted["for_symbol"] = ""
    
    return formatted


def format_symbols_list(symbols: list[str], max_display: int = 3) -> str:
    """
    Format a list of symbols for display.
    
    Args:
        symbols: List of symbol strings
        max_display: Maximum symbols to show before truncating
    
    Returns:
        Formatted string like "BTCUSDT, ETHUSDT" or "BTCUSDT, ETHUSDT +3 more"
    """
    if not symbols:
        return "(none)"
    
    if len(symbols) <= max_display:
        return ", ".join(symbols)
    
    shown = ", ".join(symbols[:max_display])
    return f"{shown} +{len(symbols) - max_display} more"


def format_period_display(period: str) -> str:
    """Format period string for display (e.g., '1M' -> '1 month')."""
    period_map = {
        "1D": "1 day",
        "1W": "1 week", 
        "1M": "1 month",
        "3M": "3 months",
        "6M": "6 months",
        "1Y": "1 year",
    }
    return period_map.get(period.upper(), period)


# =============================================================================
# DATA BUILDER SPECIALIZED FORMATTERS
# =============================================================================

def format_data_result(action_key: str, result_data: Any, message: str = "") -> dict[str, Any]:
    """
    Format action results for rich display.
    
    This is the central formatter registry for all CLI actions.
    
    Returns a dict with:
        - "type": "table", "tree", "summary", or "simple"
        - "title": Panel/table title
        - "content": Formatted content based on type
        - "footer": Optional footer text
    
    Args:
        action_key: The action that produced this result
        result_data: The data from ToolResult.data
        message: The result message
    
    Returns:
        Formatted display dict, or None to use generic formatting
    """
    formatters = {
        # ==================== DATA BUILDER ====================
        "data.list_symbols": _format_symbols_list_result,
        "data.stats": _format_database_stats_result,
        "data.symbol_status": _format_symbol_status_result,
        "data.symbol_summary": _format_symbol_summary_result,
        "data.timeframe_ranges": _format_timeframe_ranges_result,
        "data.build_full_history": _format_build_history_result,
        "data.sync_to_now": _format_sync_forward_result,
        "data.sync_to_now_fill_gaps": _format_sync_fill_result,
        "data.sync_ohlcv_period": _format_sync_result,
        "data.sync_ohlcv_range": _format_sync_result,
        "data.sync_funding": _format_sync_result,
        "data.sync_open_interest": _format_sync_result,
        "data.fill_gaps": _format_fill_gaps_result,
        "data.heal": _format_heal_result,
        "data.delete_symbol": _format_delete_result,
        "data.cleanup_empty": _format_cleanup_result,
        
        # ==================== ACCOUNT ====================
        "account.view_balance": _format_balance_result,
        "account.view_exposure": _format_exposure_result,
        "account.info": _format_account_info_result,
        "account.portfolio": _format_portfolio_result,
        "account.closed_pnl": _format_closed_pnl_result,
        "account.order_history": _format_order_history_result,
        "account.transaction_log": _format_transaction_log_result,
        "account.borrow_history": _format_borrow_history_result,
        "account.collateral_info": _format_collateral_info_result,
        "account.set_collateral": _format_simple_success_result,
        "account.coin_greeks": _format_coin_greeks_result,
        "account.set_margin_mode": _format_simple_success_result,
        "account.transferable": _format_transferable_result,
        
        # ==================== POSITIONS ====================
        "positions.list": _format_positions_list_result,
        "positions.detail": _format_position_detail_result,
        "positions.close": _format_simple_success_result,
        "positions.close_all": _format_simple_success_result,
        "positions.set_stop_loss": _format_simple_success_result,
        "positions.set_take_profit": _format_simple_success_result,
        "positions.set_tpsl": _format_simple_success_result,
        "positions.risk_limits": _format_risk_limits_result,
        "positions.set_risk_limit": _format_simple_success_result,
        "positions.set_tpsl_mode": _format_simple_success_result,
        "positions.switch_margin_mode": _format_simple_success_result,
        "positions.auto_add_margin": _format_simple_success_result,
        "positions.modify_margin": _format_simple_success_result,
        "positions.switch_mode": _format_simple_success_result,
        
        # ==================== ORDERS ====================
        "orders.list": _format_open_orders_result,
        "orders.list_open": _format_open_orders_result,
        "orders.set_leverage": _format_simple_success_result,
        "orders.cancel_all": _format_simple_success_result,
        "orders.market_buy": _format_order_placed_result,
        "orders.market_sell": _format_order_placed_result,
        "orders.limit_buy": _format_order_placed_result,
        "orders.limit_sell": _format_order_placed_result,
        "orders.stop_market_buy": _format_order_placed_result,
        "orders.stop_market_sell": _format_order_placed_result,
        "orders.stop_limit_buy": _format_order_placed_result,
        "orders.stop_limit_sell": _format_order_placed_result,
        "orders.amend": _format_simple_success_result,
        "orders.cancel": _format_simple_success_result,
        
        # ==================== MARKET DATA ====================
        "market.price": _format_price_result,
        "market.ohlcv": _format_ohlcv_result,
        "market.orderbook": _format_orderbook_result,
        "market.funding": _format_funding_rate_result,
        "market.open_interest": _format_open_interest_result,
        "market.instruments": _format_instruments_result,
        "market.test": _format_market_test_result,
        
        # ==================== DIAGNOSTICS ====================
        "diagnostics.connection": _format_connection_test_result,
        "diagnostics.server_time": _format_server_time_result,
        "diagnostics.rate_limits": _format_rate_limits_result,
        "diagnostics.ticker": _format_ticker_result,
        "diagnostics.health_check": _format_health_check_result,
        "diagnostics.websocket": _format_websocket_status_result,
        
        # ==================== DATA MAINTENANCE ====================
        "data.delete_all": _format_simple_success_result,
        "data.vacuum": _format_simple_success_result,
        
        # ==================== PANIC ====================
        "panic.close_all": _format_panic_result,
    }
    
    formatter = formatters.get(action_key)
    if formatter:
        return formatter(result_data, message)
    
    # Default: return None to use generic formatting
    return None


# Alias for backwards compatibility
format_action_result = format_data_result


def _format_symbols_list_result(data: Any, message: str) -> dict[str, Any]:
    """Format cached symbols list with rich details."""
    if not data:
        return {
            "type": "simple",
            "title": "📋 Cached Symbols",
            "content": "No symbols cached in database.",
            "footer": None,
        }
    
    # Build table rows
    rows = []
    for item in data:
        if isinstance(item, dict):
            rows.append({
                "Symbol": item.get("symbol", "?"),
                "Timeframes": str(item.get("timeframes", 0)),
                "Candles": f"{item.get('candles', 0):,}",
                "From": item.get("from", "N/A"),
                "To": item.get("to", "N/A"),
            })
        else:
            # Fallback for simple list
            rows.append({"Symbol": str(item)})
    
    return {
        "type": "table",
        "title": "📋 Cached Symbols",
        "columns": ["Symbol", "Timeframes", "Candles", "From", "To"] if rows and len(rows[0]) > 1 else ["Symbol"],
        "rows": rows,
        "footer": f"💡 Use 'Symbol Timeframe Ranges' for per-timeframe details",
    }


def _format_database_stats_result(data: Any, message: str) -> dict[str, Any]:
    """Format database statistics."""
    if not data or not isinstance(data, dict):
        return None
    
    ohlcv = data.get("ohlcv", {})
    funding = data.get("funding_rates", {})
    oi = data.get("open_interest", {})
    
    rows = [
        {"Category": "📊 OHLCV", "Symbols": str(ohlcv.get("symbols", 0)), "Records": f"{ohlcv.get('total_candles', 0):,}"},
        {"Category": "💱 Funding", "Symbols": str(funding.get("symbols", 0)), "Records": f"{funding.get('total_records', 0):,}"},
        {"Category": "📈 Open Interest", "Symbols": str(oi.get("symbols", 0)), "Records": f"{oi.get('total_records', 0):,}"},
    ]
    
    return {
        "type": "table",
        "title": f"📊 Database Stats ({data.get('file_size_mb', '?')} MB)",
        "columns": ["Category", "Symbols", "Records"],
        "rows": rows,
        "footer": None,
    }


def _format_symbol_status_result(data: Any, message: str) -> dict[str, Any]:
    """Format per-symbol aggregate status."""
    if not data or not isinstance(data, dict):
        return None
    
    summary = data.get("summary", {})
    if not summary:
        return {
            "type": "simple",
            "title": "📈 Symbol Status",
            "content": "No data cached.",
            "footer": None,
        }
    
    rows = []
    for sym, info in summary.items():
        tfs = ", ".join(info.get("timeframes", [])) if info.get("timeframes") else "none"
        rows.append({
            "Symbol": sym,
            "Timeframes": tfs[:30] + "..." if len(tfs) > 30 else tfs,
            "Candles": f"{info.get('total_candles', 0):,}",
            "Gaps": str(info.get("gaps", 0)),
            "Valid": "✓" if info.get("is_valid") else "✗",
        })
    
    return {
        "type": "table",
        "title": "📈 Symbol Aggregate Status",
        "columns": ["Symbol", "Timeframes", "Candles", "Gaps", "Valid"],
        "rows": rows,
        "footer": f"Showing {len(rows)} symbol(s)",
    }


def _format_symbol_summary_result(data: Any, message: str) -> dict[str, Any]:
    """Format high-level symbol summary."""
    if not data or not isinstance(data, dict):
        return None
    
    summary = data.get("summary", [])
    if not summary:
        return {
            "type": "simple",
            "title": "📋 Symbol Summary",
            "content": "No data cached.",
            "footer": None,
        }
    
    rows = []
    for item in summary:
        earliest = item.get("earliest")
        latest = item.get("latest")
        rows.append({
            "Symbol": item.get("symbol", "?"),
            "TFs": str(item.get("timeframes", 0)),
            "Candles": f"{item.get('total_candles', 0):,}",
            "From": earliest.strftime("%Y-%m-%d") if earliest else "N/A",
            "To": latest.strftime("%Y-%m-%d") if latest else "N/A",
        })
    
    return {
        "type": "table",
        "title": "📋 Symbol Summary (High-Level)",
        "columns": ["Symbol", "TFs", "Candles", "From", "To"],
        "rows": rows,
        "footer": "💡 Use 'Symbol Timeframe Ranges' for per-timeframe breakdown",
    }


def _format_timeframe_ranges_result(data: Any, message: str) -> dict[str, Any]:
    """Format detailed per-symbol/timeframe ranges."""
    if not data:
        return {
            "type": "simple",
            "title": "📅 Timeframe Ranges",
            "content": "No data cached.",
            "footer": None,
        }
    
    # data is a list of range dicts
    rows = []
    for item in data:
        first_ts = item.get("first_timestamp", "")
        last_ts = item.get("last_timestamp", "")
        # Truncate timestamps to date only
        first_date = first_ts[:10] if first_ts else "N/A"
        last_date = last_ts[:10] if last_ts else "N/A"
        
        is_current = item.get("is_current", False)
        status = "✓ Current" if is_current else "⚠ Stale"
        
        rows.append({
            "Symbol": item.get("symbol", "?"),
            "TF": item.get("timeframe", "?"),
            "Candles": f"{item.get('candle_count', 0):,}",
            "Gaps": str(item.get("gaps", 0)),
            "From": first_date,
            "To": last_date,
            "Status": status,
        })
    
    return {
        "type": "table",
        "title": "📅 Symbol/Timeframe Ranges (Detailed)",
        "columns": ["Symbol", "TF", "Candles", "Gaps", "From", "To", "Status"],
        "rows": rows,
        "footer": f"Showing {len(rows)} symbol/timeframe combination(s)",
    }


def _format_build_history_result(data: Any, message: str) -> dict[str, Any]:
    """Format build full history results."""
    if not data or not isinstance(data, dict):
        return None
    
    ohlcv = data.get("ohlcv", {})
    funding = data.get("funding", {})
    oi = data.get("open_interest", {})
    
    rows = [
        {
            "Data Type": "📊 OHLCV Candles",
            "Status": "✓" if ohlcv.get("success") else "✗",
            "Records": f"{ohlcv.get('total_synced', 0):,}",
        },
        {
            "Data Type": "💱 Funding Rates",
            "Status": "✓" if funding.get("success") else "✗",
            "Records": f"{funding.get('total_synced', 0):,}",
        },
        {
            "Data Type": "📈 Open Interest",
            "Status": "✓" if oi.get("success") else "✗",
            "Records": f"{oi.get('total_synced', 0):,}",
        },
    ]
    
    total = data.get("total_records", 0)
    symbols = data.get("symbols", [])
    period = data.get("period", "?")
    
    return {
        "type": "table",
        "title": f"🏗️ Build History Complete ({period})",
        "columns": ["Data Type", "Status", "Records"],
        "rows": rows,
        "footer": f"Built {total:,} total records for {len(symbols)} symbol(s)",
    }


def _format_sync_forward_result(data: Any, message: str) -> dict[str, Any]:
    """Format sync forward to now results."""
    if not data or not isinstance(data, dict):
        return None
    
    total = data.get("total_synced", 0)
    already = data.get("already_current", 0)
    results = data.get("results", {})
    
    if not results:
        return {
            "type": "simple",
            "title": "🔄 Sync Forward",
            "content": message,
            "footer": None,
        }
    
    rows = []
    for key, count in results.items():
        status = "✓ Up to date" if count == 0 else f"+{count:,} candles"
        rows.append({
            "Symbol/TF": key,
            "Result": status,
        })
    
    return {
        "type": "table",
        "title": "🔄 Sync Forward to Now",
        "columns": ["Symbol/TF", "Result"],
        "rows": rows[:20],  # Limit display
        "footer": f"Synced {total:,} new candles, {already} already current" + (f" (+{len(rows)-20} more)" if len(rows) > 20 else ""),
    }


def _format_sync_fill_result(data: Any, message: str) -> dict[str, Any]:
    """Format sync + fill gaps results."""
    if not data or not isinstance(data, dict):
        return None
    
    sync = data.get("sync_forward", {})
    gaps = data.get("gap_fill", {})
    
    rows = [
        {
            "Operation": "🔄 Sync Forward",
            "Records": f"{sync.get('total_synced', 0):,}",
        },
        {
            "Operation": "🔧 Fill Gaps",
            "Records": f"{gaps.get('total_filled', 0):,}",
        },
    ]
    
    total = data.get("total_records", 0)
    
    return {
        "type": "table",
        "title": "🔄🔧 Sync + Fill Gaps Complete",
        "columns": ["Operation", "Records"],
        "rows": rows,
        "footer": f"Total: {total:,} records synced/filled",
    }


def _format_sync_result(data: Any, message: str) -> dict[str, Any]:
    """Format general sync results."""
    if not data or not isinstance(data, dict):
        return None
    
    results = data.get("results", {})
    total = data.get("total_synced", 0)
    
    if not results:
        return {
            "type": "simple",
            "title": "📊 Sync Result",
            "content": message,
            "footer": None,
        }
    
    rows = []
    for key, count in results.items():
        rows.append({
            "Symbol/TF": key,
            "Records": f"{count:,}" if count >= 0 else "Error",
        })
    
    return {
        "type": "table",
        "title": "📊 Sync Complete",
        "columns": ["Symbol/TF", "Records"],
        "rows": rows[:20],
        "footer": f"Total: {total:,} records synced" + (f" (+{len(rows)-20} more)" if len(rows) > 20 else ""),
    }


def _format_fill_gaps_result(data: Any, message: str) -> dict[str, Any]:
    """Format gap fill results."""
    if not data or not isinstance(data, dict):
        return None
    
    results = data.get("results", {})
    total = data.get("total_filled", 0)
    
    if not results:
        return {
            "type": "simple",
            "title": "🔧 Fill Gaps",
            "content": "No gaps found to fill." if total == 0 else message,
            "footer": None,
        }
    
    rows = []
    for key, count in results.items():
        rows.append({
            "Symbol/TF": key,
            "Filled": f"{count:,}" if count >= 0 else "Error",
        })
    
    return {
        "type": "table",
        "title": "🔧 Gap Fill Complete",
        "columns": ["Symbol/TF", "Filled"],
        "rows": rows[:20],
        "footer": f"Total: {total:,} gaps filled" + (f" (+{len(rows)-20} more)" if len(rows) > 20 else ""),
    }


def _format_heal_result(data: Any, message: str) -> dict[str, Any]:
    """Format heal/repair results."""
    if not data or not isinstance(data, dict):
        return None
    
    report = data.get("report", {})
    issues_found = report.get("issues_found", 0)
    issues_fixed = report.get("issues_fixed", 0)
    
    if issues_found == 0:
        return {
            "type": "simple",
            "title": "🩹 Data Health Check",
            "content": "✓ All data is healthy - no issues found.",
            "footer": None,
        }
    
    # Build issues breakdown
    rows = []
    for issue_type, count in report.items():
        if issue_type not in ("issues_found", "issues_fixed") and count > 0:
            rows.append({
                "Issue Type": issue_type.replace("_", " ").title(),
                "Found": str(count),
            })
    
    if not rows:
        rows.append({"Issue Type": "Various", "Found": str(issues_found)})
    
    return {
        "type": "table",
        "title": "🩹 Data Heal Report",
        "columns": ["Issue Type", "Found"],
        "rows": rows,
        "footer": f"Found {issues_found} issues, fixed {issues_fixed}",
    }


def _format_delete_result(data: Any, message: str) -> dict[str, Any]:
    """Format delete symbol result."""
    if not data or not isinstance(data, dict):
        return None
    
    symbol = data.get("symbol", "?")
    deleted = data.get("deleted_count", 0)
    
    return {
        "type": "simple",
        "title": "🗑️ Symbol Deleted",
        "content": f"Deleted {deleted:,} records for {symbol}",
        "footer": "Database vacuumed" if data.get("vacuumed") else None,
    }


def _format_cleanup_result(data: Any, message: str) -> dict[str, Any]:
    """Format cleanup empty symbols result."""
    if not data or not isinstance(data, dict):
        return None
    
    cleaned = data.get("cleaned_symbols", [])
    count = data.get("count", 0)
    
    if count == 0:
        return {
            "type": "simple",
            "title": "🧹 Cleanup",
            "content": "No empty symbols found to clean up.",
            "footer": None,
        }
    
    return {
        "type": "simple",
        "title": "🧹 Cleanup Complete",
        "content": f"Removed {count} empty symbol(s): {', '.join(cleaned[:5])}" + (f" +{count-5} more" if count > 5 else ""),
        "footer": None,
    }


# =============================================================================
# ACCOUNT FORMATTERS
# =============================================================================

def _ms_to_datetime_str(ms_str: str, format: str = "%Y-%m-%d %H:%M") -> str:
    """Convert millisecond timestamp string to readable datetime."""
    try:
        ms = int(ms_str)
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        return dt.strftime(format)
    except (ValueError, TypeError):
        return str(ms_str)[:16] if ms_str else "N/A"


def _format_currency(value: str | float, decimals: int = 2, prefix: str = "$") -> str:
    """Format a numeric value as currency."""
    try:
        num = float(value)
        if num >= 0:
            return f"{prefix}{num:,.{decimals}f}"
        else:
            return f"-{prefix}{abs(num):,.{decimals}f}"
    except (ValueError, TypeError):
        return str(value)


def _format_closed_pnl_result(data: Any, message: str) -> dict[str, Any]:
    """Format closed PnL records as a human-readable table."""
    if not data or not isinstance(data, dict):
        return None
    
    records = data.get("records", [])
    total_pnl = data.get("total_pnl", 0)
    count = data.get("count", 0)
    time_range = data.get("time_range", {})
    
    if not records:
        return {
            "type": "simple",
            "title": "💵 Closed PnL",
            "content": f"No closed trades found for {time_range.get('label', 'selected period')}.",
            "footer": None,
        }
    
    rows = []
    for rec in records[:50]:  # Limit to 50 rows
        # Calculate fees and net PnL
        open_fee = float(rec.get("openFee", 0))
        close_fee = float(rec.get("closeFee", 0))
        total_fees = open_fee + close_fee
        gross_pnl = float(rec.get("closedPnl", 0))
        net_pnl = gross_pnl - total_fees
        
        rows.append({
            "Time": _ms_to_datetime_str(rec.get("updatedTime", "")),
            "Symbol": rec.get("symbol", "?"),
            "Side": rec.get("side", "?").upper(),
            "Qty": rec.get("closedSize", rec.get("qty", "?")),
            "Entry": _format_currency(rec.get("avgEntryPrice", 0), 2, ""),
            "Exit": _format_currency(rec.get("avgExitPrice", 0), 2, ""),
            "Gross PnL": _format_currency(gross_pnl, 4),
            "Fees": _format_currency(total_fees, 4),
            "Net PnL": _format_currency(net_pnl, 4),
        })
    
    label = time_range.get("label", "period")
    footer = f"Total Gross PnL: {_format_currency(total_pnl)} across {count} trade(s) ({label})"
    if len(records) > 50:
        footer += f" | Showing first 50 of {len(records)}"
    
    return {
        "type": "table",
        "title": "💵 Closed PnL Records",
        "columns": ["Time", "Symbol", "Side", "Qty", "Entry", "Exit", "Gross PnL", "Fees", "Net PnL"],
        "rows": rows,
        "footer": footer,
    }


def _format_order_history_result(data: Any, message: str) -> dict[str, Any]:
    """Format order history as a human-readable table."""
    if not data or not isinstance(data, dict):
        return None
    
    orders = data.get("orders", [])
    count = data.get("count", 0)
    time_range = data.get("time_range", {})
    
    if not orders:
        return {
            "type": "simple",
            "title": "📜 Order History",
            "content": f"No orders found for {time_range.get('label', 'selected period')}.",
            "footer": None,
        }
    
    rows = []
    for order in orders[:50]:
        order_id = order.get("orderId", "?")
        short_id = order_id[:8] + "..." if len(order_id) > 11 else order_id
        
        rows.append({
            "Time": _ms_to_datetime_str(order.get("createdTime", "")),
            "Symbol": order.get("symbol", "?"),
            "Side": order.get("side", "?").upper(),
            "Type": order.get("orderType", "?"),
            "Qty": order.get("qty", "?"),
            "Price": _format_currency(order.get("price", 0), 2, "") if order.get("price") else "Market",
            "Status": order.get("orderStatus", "?"),
            "Order ID": short_id,
        })
    
    label = time_range.get("label", "period")
    footer = f"{count} order(s) ({label})"
    if len(orders) > 50:
        footer += f" | Showing first 50"
    
    return {
        "type": "table",
        "title": "📜 Order History",
        "columns": ["Time", "Symbol", "Side", "Type", "Qty", "Price", "Status", "Order ID"],
        "rows": rows,
        "footer": footer,
    }


def _format_transaction_log_result(data: Any, message: str) -> dict[str, Any]:
    """Format transaction log as a human-readable table."""
    if not data or not isinstance(data, dict):
        return None
    
    records = data.get("records", [])
    count = data.get("count", 0)
    time_range = data.get("time_range", {})
    
    if not records:
        return {
            "type": "simple",
            "title": "📒 Transaction Log",
            "content": f"No transactions found for {time_range.get('label', 'selected period')}.",
            "footer": None,
        }
    
    rows = []
    for rec in records[:50]:
        rows.append({
            "Time": _ms_to_datetime_str(rec.get("transactionTime", "")),
            "Type": rec.get("type", "?"),
            "Symbol": rec.get("symbol", "-"),
            "Currency": rec.get("currency", "?"),
            "Amount": _format_currency(rec.get("change", 0), 4, ""),
            "Fee": _format_currency(rec.get("fee", 0), 4, ""),
            "Balance": _format_currency(rec.get("cashBalance", 0), 2, ""),
        })
    
    label = time_range.get("label", "period")
    footer = f"{count} transaction(s) ({label})"
    if len(records) > 50:
        footer += f" | Showing first 50"
    
    return {
        "type": "table",
        "title": "📒 Transaction Log",
        "columns": ["Time", "Type", "Symbol", "Currency", "Amount", "Fee", "Balance"],
        "rows": rows,
        "footer": footer,
    }


def _format_borrow_history_result(data: Any, message: str) -> dict[str, Any]:
    """Format borrow history as a human-readable table."""
    if not data or not isinstance(data, dict):
        return None
    
    records = data.get("records", [])
    count = data.get("count", 0)
    time_range = data.get("time_range", {})
    
    if not records:
        return {
            "type": "simple",
            "title": "📝 Borrow History",
            "content": f"No borrow records found for {time_range.get('label', 'selected period')}.",
            "footer": None,
        }
    
    rows = []
    for rec in records[:50]:
        rows.append({
            "Time": _ms_to_datetime_str(rec.get("createdTime", "")),
            "Currency": rec.get("currency", "?"),
            "Borrow Amount": _format_currency(rec.get("borrowAmount", 0), 4, ""),
            "Interest": _format_currency(rec.get("costExemption", rec.get("interest", 0)), 6, ""),
            "Hourly Rate": f"{float(rec.get('hourlyBorrowRate', 0)) * 100:.4f}%",
        })
    
    label = time_range.get("label", "period")
    footer = f"{count} borrow record(s) ({label})"
    if len(records) > 50:
        footer += f" | Showing first 50"
    
    return {
        "type": "table",
        "title": "📝 Borrow History",
        "columns": ["Time", "Currency", "Borrow Amount", "Interest", "Hourly Rate"],
        "rows": rows,
        "footer": footer,
    }


def _format_collateral_info_result(data: Any, message: str) -> dict[str, Any]:
    """Format collateral info as a human-readable table."""
    if not data or not isinstance(data, dict):
        return None
    
    collateral_info = data.get("collateral_info", [])
    total_coins = data.get("total_coins", 0)
    enabled_count = data.get("enabled_count", 0)
    
    if not collateral_info:
        return {
            "type": "simple",
            "title": "🏦 Collateral Info",
            "content": "No collateral information available.",
            "footer": None,
        }
    
    rows = []
    for coin in collateral_info[:30]:
        rows.append({
            "Coin": coin.get("currency", "?"),
            "Enabled": "✓" if coin.get("collateralSwitch") == "ON" else "✗",
            "Borrow Rate": f"{float(coin.get('borrowingMarginRatio', 0)) * 100:.1f}%",
            "Collateral Ratio": f"{float(coin.get('collateralRatio', 0)) * 100:.1f}%",
            "Max Borrow": _format_currency(coin.get("maxBorrowingAmount", 0), 2, ""),
        })
    
    footer = f"{enabled_count}/{total_coins} coins enabled as collateral"
    if len(collateral_info) > 30:
        footer += f" | Showing first 30"
    
    return {
        "type": "table",
        "title": "🏦 Collateral Information",
        "columns": ["Coin", "Enabled", "Borrow Rate", "Collateral Ratio", "Max Borrow"],
        "rows": rows,
        "footer": footer,
    }


# =============================================================================
# POSITIONS FORMATTERS
# =============================================================================

def _format_positions_list_result(data: Any, message: str) -> dict[str, Any]:
    """Format positions list as a human-readable table."""
    if not data:
        return {
            "type": "simple",
            "title": "📈 Open Positions",
            "content": "No open positions.",
            "footer": None,
        }
    
    positions = data if isinstance(data, list) else data.get("positions", [])
    
    if not positions:
        return {
            "type": "simple",
            "title": "📈 Open Positions",
            "content": "No open positions.",
            "footer": None,
        }
    
    rows = []
    for pos in positions:
        side = pos.get("side", "?")
        unrealized_pnl = float(pos.get("unrealisedPnl", 0))
        
        # Color indicators for PnL
        pnl_str = _format_currency(unrealized_pnl, 2)
        
        rows.append({
            "Symbol": pos.get("symbol", "?"),
            "Side": side.upper(),
            "Size": pos.get("size", "?"),
            "Entry": _format_currency(pos.get("avgPrice", 0), 2, ""),
            "Mark": _format_currency(pos.get("markPrice", 0), 2, ""),
            "Unreal. PnL": pnl_str,
            "Leverage": f"{pos.get('leverage', '?')}x",
            "Liq Price": _format_currency(pos.get("liqPrice", 0), 2, "") if pos.get("liqPrice") else "N/A",
        })
    
    return {
        "type": "table",
        "title": "📈 Open Positions",
        "columns": ["Symbol", "Side", "Size", "Entry", "Mark", "Unreal. PnL", "Leverage", "Liq Price"],
        "rows": rows,
        "footer": f"{len(positions)} open position(s)",
    }


def _format_position_detail_result(data: Any, message: str) -> dict[str, Any]:
    """Format single position detail as a summary."""
    if not data or not isinstance(data, dict):
        return None
    
    pos = data.get("position", data)
    
    if not pos or pos.get("size") == "0":
        return {
            "type": "simple",
            "title": "🔍 Position Detail",
            "content": f"No open position for {data.get('symbol', 'this symbol')}.",
            "footer": None,
        }
    
    unrealized_pnl = float(pos.get("unrealisedPnl", 0))
    cum_pnl = float(pos.get("cumRealisedPnl", 0))
    
    rows = [
        {"Field": "Symbol", "Value": pos.get("symbol", "?")},
        {"Field": "Side", "Value": pos.get("side", "?").upper()},
        {"Field": "Size", "Value": pos.get("size", "?")},
        {"Field": "Entry Price", "Value": _format_currency(pos.get("avgPrice", 0), 4, "")},
        {"Field": "Mark Price", "Value": _format_currency(pos.get("markPrice", 0), 4, "")},
        {"Field": "Unrealized PnL", "Value": _format_currency(unrealized_pnl, 4)},
        {"Field": "Cumulative PnL", "Value": _format_currency(cum_pnl, 4)},
        {"Field": "Leverage", "Value": f"{pos.get('leverage', '?')}x"},
        {"Field": "Margin Mode", "Value": pos.get("tradeMode", "?")},
        {"Field": "Liquidation Price", "Value": _format_currency(pos.get("liqPrice", 0), 2, "") if pos.get("liqPrice") else "N/A"},
        {"Field": "Take Profit", "Value": _format_currency(pos.get("takeProfit", 0), 2, "") if pos.get("takeProfit") else "Not set"},
        {"Field": "Stop Loss", "Value": _format_currency(pos.get("stopLoss", 0), 2, "") if pos.get("stopLoss") else "Not set"},
    ]
    
    return {
        "type": "table",
        "title": f"🔍 Position: {pos.get('symbol', '?')}",
        "columns": ["Field", "Value"],
        "rows": rows,
        "footer": None,
    }


# =============================================================================
# ORDERS FORMATTERS
# =============================================================================

def _format_open_orders_result(data: Any, message: str) -> dict[str, Any]:
    """Format open orders as a human-readable table."""
    if not data or not isinstance(data, dict):
        return None
    
    orders = data.get("orders", [])
    count = data.get("count", 0)
    
    if not orders:
        return {
            "type": "simple",
            "title": "📋 Open Orders",
            "content": "No open orders.",
            "footer": None,
        }
    
    rows = []
    for order in orders[:30]:
        order_id = order.get("orderId", "?")
        short_id = order_id[:8] + "..." if len(order_id) > 11 else order_id
        
        # Format price - show trigger for stop orders
        price = order.get("price", "")
        trigger = order.get("triggerPrice", "")
        price_str = _format_currency(price, 2, "") if price else "Market"
        if trigger:
            price_str = f"{price_str} (trig: {_format_currency(trigger, 2, '')})"
        
        rows.append({
            "Time": _ms_to_datetime_str(order.get("createdTime", "")),
            "Symbol": order.get("symbol", "?"),
            "Side": order.get("side", "?").upper(),
            "Type": order.get("orderType", "?"),
            "Qty": order.get("qty", "?"),
            "Price": price_str,
            "Status": order.get("orderStatus", "?"),
            "ID": short_id,
        })
    
    footer = f"{count} open order(s)"
    if len(orders) > 30:
        footer += f" | Showing first 30"
    
    return {
        "type": "table",
        "title": "📋 Open Orders",
        "columns": ["Time", "Symbol", "Side", "Type", "Qty", "Price", "Status", "ID"],
        "rows": rows,
        "footer": footer,
    }


# =============================================================================
# MARKET DATA FORMATTERS
# =============================================================================

def _format_ohlcv_result(data: Any, message: str) -> dict[str, Any]:
    """Format OHLCV candles as a human-readable table."""
    if not data or not isinstance(data, dict):
        return None
    
    candles = data.get("candles", [])
    count = data.get("count", 0)
    symbol = data.get("symbol", "?")
    interval = data.get("interval", "?")
    
    if not candles:
        return {
            "type": "simple",
            "title": "📊 OHLCV Data",
            "content": f"No candles available for {symbol}.",
            "footer": None,
        }
    
    # For large datasets, show summary only
    if count > 20:
        first_candle = candles[0] if candles else {}
        last_candle = candles[-1] if candles else {}
        
        return {
            "type": "simple",
            "title": f"📊 OHLCV: {symbol} ({interval})",
            "content": (
                f"Retrieved {count:,} candles\n"
                f"From: {_ms_to_datetime_str(first_candle.get('timestamp', ''))}\n"
                f"To: {_ms_to_datetime_str(last_candle.get('timestamp', ''))}"
            ),
            "footer": "Use smaller limit to see individual candles",
        }
    
    rows = []
    for candle in candles[:20]:
        rows.append({
            "Time": _ms_to_datetime_str(candle.get("timestamp", "")),
            "Open": _format_currency(candle.get("open", 0), 2, ""),
            "High": _format_currency(candle.get("high", 0), 2, ""),
            "Low": _format_currency(candle.get("low", 0), 2, ""),
            "Close": _format_currency(candle.get("close", 0), 2, ""),
            "Volume": f"{float(candle.get('volume', 0)):,.0f}",
        })
    
    return {
        "type": "table",
        "title": f"📊 OHLCV: {symbol} ({interval})",
        "columns": ["Time", "Open", "High", "Low", "Close", "Volume"],
        "rows": rows,
        "footer": f"{count} candle(s)",
    }


def _format_orderbook_result(data: Any, message: str) -> dict[str, Any]:
    """Format orderbook as a human-readable summary."""
    if not data or not isinstance(data, dict):
        return None
    
    bids = data.get("bids", [])
    asks = data.get("asks", [])
    symbol = data.get("symbol", "?")
    
    if not bids and not asks:
        return {
            "type": "simple",
            "title": "📚 Order Book",
            "content": f"No orderbook data for {symbol}.",
            "footer": None,
        }
    
    # Show top 5 bids and asks
    rows = []
    
    # Asks (top 5, reversed so highest ask is at top)
    for ask in reversed(asks[:5]):
        rows.append({
            "Type": "ASK",
            "Price": _format_currency(ask[0], 2, ""),
            "Size": f"{float(ask[1]):,.4f}",
        })
    
    # Spread row
    if bids and asks:
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        spread = best_ask - best_bid
        spread_pct = (spread / best_bid) * 100 if best_bid > 0 else 0
        rows.append({
            "Type": "--- SPREAD ---",
            "Price": _format_currency(spread, 4, ""),
            "Size": f"({spread_pct:.4f}%)",
        })
    
    # Bids (top 5)
    for bid in bids[:5]:
        rows.append({
            "Type": "BID",
            "Price": _format_currency(bid[0], 2, ""),
            "Size": f"{float(bid[1]):,.4f}",
        })
    
    return {
        "type": "table",
        "title": f"📚 Order Book: {symbol}",
        "columns": ["Type", "Price", "Size"],
        "rows": rows,
        "footer": f"{len(bids)} bids, {len(asks)} asks total",
    }


def _format_funding_rate_result(data: Any, message: str) -> dict[str, Any]:
    """Format funding rate as a human-readable summary."""
    if not data or not isinstance(data, dict):
        return None
    
    symbol = data.get("symbol", "?")
    # Support both funding_rate (raw) and funding_rate_pct (pre-converted)
    funding_rate_pct = data.get("funding_rate_pct", 0)
    if funding_rate_pct == 0:
        # Fallback to raw funding_rate and convert to percentage
        funding_rate_pct = float(data.get("funding_rate", 0)) * 100
    
    # Get next funding time from records if available
    records = data.get("records", [])
    next_funding = ""
    if records and len(records) > 0:
        next_funding = records[0].get("fundingRateTimestamp", "")
    
    direction = "Long pays Short" if funding_rate_pct > 0 else "Short pays Long" if funding_rate_pct < 0 else "Neutral"
    
    rows = [
        {"Field": "Symbol", "Value": symbol},
        {"Field": "Funding Rate", "Value": f"{funding_rate_pct:.4f}%"},
        {"Field": "Direction", "Value": direction},
        {"Field": "Next Funding", "Value": _ms_to_datetime_str(next_funding) if next_funding else "N/A"},
    ]
    
    return {
        "type": "table",
        "title": f"💱 Funding Rate: {symbol}",
        "columns": ["Field", "Value"],
        "rows": rows,
        "footer": None,
    }


def _format_open_interest_result(data: Any, message: str) -> dict[str, Any]:
    """Format open interest as a human-readable summary."""
    if not data or not isinstance(data, dict):
        return None
    
    symbol = data.get("symbol", "?")
    oi = data.get("open_interest", 0)
    oi_value = data.get("open_interest_value", 0)
    
    rows = [
        {"Field": "Symbol", "Value": symbol},
        {"Field": "Open Interest (Contracts)", "Value": f"{float(oi):,.0f}"},
        {"Field": "Open Interest (USD)", "Value": _format_currency(oi_value, 0)},
    ]
    
    return {
        "type": "table",
        "title": f"📈 Open Interest: {symbol}",
        "columns": ["Field", "Value"],
        "rows": rows,
        "footer": None,
    }


def _format_instruments_result(data: Any, message: str) -> dict[str, Any]:
    """Format instruments info as a human-readable table."""
    if not data or not isinstance(data, dict):
        return None
    
    instruments = data.get("instruments", [])
    
    if not instruments:
        return {
            "type": "simple",
            "title": "🔧 Instruments",
            "content": "No instruments found.",
            "footer": None,
        }
    
    rows = []
    for inst in instruments[:20]:
        rows.append({
            "Symbol": inst.get("symbol", "?"),
            "Base": inst.get("baseCoin", "?"),
            "Quote": inst.get("quoteCoin", "?"),
            "Status": inst.get("status", "?"),
            "Tick Size": inst.get("priceFilter", {}).get("tickSize", "?"),
            "Min Qty": inst.get("lotSizeFilter", {}).get("minOrderQty", "?"),
        })
    
    return {
        "type": "table",
        "title": "🔧 Trading Instruments",
        "columns": ["Symbol", "Base", "Quote", "Status", "Tick Size", "Min Qty"],
        "rows": rows,
        "footer": f"{len(instruments)} instrument(s)" + (f" | Showing first 20" if len(instruments) > 20 else ""),
    }


# =============================================================================
# DIAGNOSTICS FORMATTERS
# =============================================================================

def _format_connection_test_result(data: Any, message: str) -> dict[str, Any]:
    """Format connection test result."""
    if not data or not isinstance(data, dict):
        return None
    
    env = data.get("environment", "Unknown")
    public_ok = data.get("public_ok", False)
    private_ok = data.get("private_ok")
    btc_price = data.get("btc_price")
    usdt_balance = data.get("usdt_balance")
    
    rows = [
        {"Check": "Environment", "Status": env},
        {"Check": "Public API", "Status": "✓ Connected" if public_ok else "✗ Failed"},
        {"Check": "Private API", "Status": "✓ Connected" if private_ok else ("○ Not tested" if private_ok is None else "✗ Failed")},
    ]
    
    if btc_price:
        rows.append({"Check": "BTC Price", "Status": _format_currency(btc_price, 2)})
    
    if usdt_balance is not None:
        rows.append({"Check": "USDT Balance", "Status": _format_currency(usdt_balance, 2)})
    
    # Add errors if present
    if data.get("error"):
        rows.append({"Check": "⚠ Public Error", "Status": str(data.get("error"))[:40]})
    if data.get("private_error"):
        rows.append({"Check": "⚠ Private Error", "Status": str(data.get("private_error"))[:40]})
    
    return {
        "type": "table",
        "title": "🔌 Connection Test",
        "columns": ["Check", "Status"],
        "rows": rows,
        "footer": None,
    }


def _format_server_time_result(data: Any, message: str) -> dict[str, Any]:
    """Format server time offset result."""
    if not data or not isinstance(data, dict):
        return None
    
    offset = data.get("offset_ms", 0)
    server_time = data.get("server_time", "")
    
    rows = [
        {"Field": "Server Time", "Value": server_time},
        {"Field": "Clock Offset", "Value": f"{offset:+d} ms"},
        {"Field": "Status", "Value": "✓ OK" if abs(offset) < 1000 else "⚠ High offset"},
    ]
    
    return {
        "type": "table",
        "title": "⏰ Server Time",
        "columns": ["Field", "Value"],
        "rows": rows,
        "footer": None,
    }


def _format_rate_limits_result(data: Any, message: str) -> dict[str, Any]:
    """Format rate limits status."""
    if not data or not isinstance(data, dict):
        return None
    
    limits = data.get("limits", {})
    
    if not limits:
        return {
            "type": "simple",
            "title": "⏱️ Rate Limits",
            "content": "Rate limit info not available.",
            "footer": None,
        }
    
    rows = []
    for endpoint, info in limits.items():
        if isinstance(info, dict):
            used = info.get("used", 0)
            limit = info.get("limit", 0)
            pct = (used / limit * 100) if limit > 0 else 0
            status = "⚠ High" if pct > 80 else "✓ OK"
            rows.append({
                "Endpoint": endpoint,
                "Used": str(used),
                "Limit": str(limit),
                "Usage": f"{pct:.0f}%",
                "Status": status,
            })
    
    if not rows:
        return {
            "type": "simple",
            "title": "⏱️ Rate Limits",
            "content": str(limits),
            "footer": None,
        }
    
    return {
        "type": "table",
        "title": "⏱️ Rate Limit Status",
        "columns": ["Endpoint", "Used", "Limit", "Usage", "Status"],
        "rows": rows,
        "footer": None,
    }


def _format_ticker_result(data: Any, message: str) -> dict[str, Any]:
    """Format ticker data."""
    if not data or not isinstance(data, dict):
        return None
    
    # Get ticker from raw data if present, otherwise use data directly
    raw = data.get("raw", {})
    ticker = raw if raw else data
    symbol = data.get("symbol", ticker.get("symbol", "?"))
    
    # Get last price - check multiple possible field names
    last_price = data.get("last_price") or ticker.get("lastPrice") or ticker.get("last_price", 0)
    high_24h = ticker.get("highPrice24h", ticker.get("high_24h", 0))
    low_24h = ticker.get("lowPrice24h", ticker.get("low_24h", 0))
    volume_24h = ticker.get("volume24h", ticker.get("turnover24h", 0))
    change_24h = ticker.get("price24hPcnt", ticker.get("change_24h", 0))
    
    rows = [
        {"Field": "Symbol", "Value": symbol},
        {"Field": "Last Price", "Value": _format_currency(last_price, 2, "$")},
    ]
    
    if float(high_24h) > 0:
        rows.append({"Field": "24h High", "Value": _format_currency(high_24h, 2, "$")})
    if float(low_24h) > 0:
        rows.append({"Field": "24h Low", "Value": _format_currency(low_24h, 2, "$")})
    if float(volume_24h) > 0:
        rows.append({"Field": "24h Volume", "Value": f"{float(volume_24h):,.0f}"})
    if float(change_24h) != 0:
        rows.append({"Field": "24h Change", "Value": f"{float(change_24h) * 100:.2f}%"})
    
    return {
        "type": "table",
        "title": f"📊 Ticker: {symbol}",
        "columns": ["Field", "Value"],
        "rows": rows,
        "footer": None,
    }


def _format_health_check_result(data: Any, message: str) -> dict[str, Any]:
    """Format health check result."""
    if not data or not isinstance(data, dict):
        return None
    
    # Try "tests" first (exchange_health_check_tool format), then "checks"
    tests = data.get("tests", data.get("checks", {}))
    passed_count = data.get("passed_count", 0)
    total_count = data.get("total_count", len(tests))
    all_passed = data.get("all_passed", data.get("overall") == "healthy")
    
    rows = []
    for check_name, result in tests.items():
        if isinstance(result, dict):
            # Check for "passed", "success", or "ok" fields
            passed = result.get("passed", result.get("success", result.get("ok", False)))
            status = "✓" if passed else "✗"
            detail = result.get("message", result.get("error", ""))
        else:
            status = "✓" if result else "✗"
            detail = str(result) if result else ""
        
        rows.append({
            "Check": check_name.replace("_", " ").title(),
            "Status": status,
            "Details": str(detail)[:50] + "..." if len(str(detail)) > 50 else str(detail),
        })
    
    if not rows:
        rows.append({"Check": "Overall", "Status": "✓" if all_passed else "⚠", "Details": "No tests run"})
    
    footer = f"{passed_count}/{total_count} checks passed" if total_count > 0 else "Health check complete"
    
    return {
        "type": "table",
        "title": "🏥 Health Check",
        "columns": ["Check", "Status", "Details"],
        "rows": rows,
        "footer": footer,
    }


def _format_websocket_status_result(data: Any, message: str) -> dict[str, Any]:
    """Format WebSocket status."""
    if not data or not isinstance(data, dict):
        return None
    
    ws_connected = data.get("websocket_connected", False)
    using_rest = data.get("using_rest_fallback", False)
    
    # Get public/private status if available
    pub = data.get("public", {})
    priv = data.get("private", {})
    stats = data.get("stats", {})
    
    rows = [
        {"Component": "WebSocket Connected", "Status": "✓ Yes" if ws_connected else "✗ No"},
        {"Component": "REST Fallback", "Status": "✓ Active" if using_rest else "○ Not needed"},
    ]
    
    if pub:
        pub_connected = pub.get("is_connected", False)
        rows.append({"Component": "Public Stream", "Status": "✓ Connected" if pub_connected else "○ Not connected"})
        if pub.get("uptime_seconds"):
            rows.append({"Component": "Public Uptime", "Status": f"{pub.get('uptime_seconds', 0):.0f}s"})
    
    if priv:
        priv_connected = priv.get("is_connected", False)
        rows.append({"Component": "Private Stream", "Status": "✓ Connected" if priv_connected else "○ Not connected"})
        if priv.get("uptime_seconds"):
            rows.append({"Component": "Private Uptime", "Status": f"{priv.get('uptime_seconds', 0):.0f}s"})
    
    if stats:
        ticker_count = stats.get("ticker_count", 0)
        position_count = stats.get("position_count", 0)
        if ticker_count > 0:
            rows.append({"Component": "Ticker Updates", "Status": f"{ticker_count:,}"})
        if position_count > 0:
            rows.append({"Component": "Positions Tracked", "Status": str(position_count)})
    
    healthy = data.get("healthy", ws_connected or using_rest)
    footer = "✓ System healthy" if healthy else "⚠ Check connection"
    
    return {
        "type": "table",
        "title": "🔗 WebSocket Status",
        "columns": ["Component", "Status"],
        "rows": rows,
        "footer": footer,
    }


# =============================================================================
# GENERIC / UTILITY FORMATTERS
# =============================================================================

def _format_simple_success_result(data: Any, message: str) -> dict[str, Any]:
    """
    Format simple success results as a clean key-value table.
    
    Works for any dict-based result, displaying key fields in a readable format.
    """
    if not data:
        return {
            "type": "simple",
            "title": "✓ Result",
            "content": message or "Operation completed successfully.",
            "footer": None,
        }
    
    if not isinstance(data, dict):
        return {
            "type": "simple",
            "title": "✓ Result",
            "content": str(data),
            "footer": None,
        }
    
    # Build rows from data dict, filtering out complex nested objects and raw data
    rows = []
    skip_keys = {"raw", "retCode", "retMsg", "retExtInfo", "time"}
    
    for key, value in data.items():
        if key in skip_keys:
            continue
        if isinstance(value, (dict, list)) and len(str(value)) > 100:
            continue  # Skip complex nested data
        
        # Format the key nicely
        display_key = key.replace("_", " ").title()
        
        # Format the value
        if isinstance(value, bool):
            display_value = "✓ Yes" if value else "✗ No"
        elif isinstance(value, (int, float)) and "price" in key.lower():
            display_value = _format_currency(value, 4, "")
        elif isinstance(value, (int, float)) and ("amount" in key.lower() or "balance" in key.lower()):
            display_value = _format_currency(value, 4)
        elif isinstance(value, dict):
            display_value = ", ".join(f"{k}: {v}" for k, v in list(value.items())[:3])
        elif isinstance(value, list):
            display_value = f"{len(value)} items"
        else:
            display_value = str(value)
        
        rows.append({"Field": display_key, "Value": display_value})
    
    if not rows:
        return {
            "type": "simple",
            "title": "✓ Result",
            "content": message or "Operation completed successfully.",
            "footer": None,
        }
    
    return {
        "type": "table",
        "title": "✓ Result",
        "columns": ["Field", "Value"],
        "rows": rows,
        "footer": None,
    }


def _format_balance_result(data: Any, message: str) -> dict[str, Any]:
    """Format account balance as a human-readable table."""
    if not data or not isinstance(data, dict):
        return None
    
    rows = []
    
    # Main balance fields - check both tool output format and raw API format
    total = data.get("total", data.get("totalEquity"))
    available = data.get("available", data.get("totalAvailableBalance"))
    used = data.get("used", data.get("totalInitialMargin"))
    unrealized_pnl = data.get("unrealized_pnl", data.get("totalPerpUPL"))
    
    if total is not None:
        rows.append({"Field": "Total Balance", "Value": _format_currency(total, 2)})
    if available is not None:
        rows.append({"Field": "Available Balance", "Value": _format_currency(available, 2)})
    if used is not None and float(used) > 0:
        rows.append({"Field": "Used Margin", "Value": _format_currency(used, 2)})
    if unrealized_pnl is not None and float(unrealized_pnl) != 0:
        rows.append({"Field": "Unrealized PnL", "Value": _format_currency(unrealized_pnl, 2)})
    
    # Coin balances if present in raw data
    raw = data.get("raw", {})
    coins = raw.get("coins", raw.get("coin", []))
    if coins and isinstance(coins, list):
        for coin in coins[:5]:  # Show top 5 coins with balance
            coin_name = coin.get("coin", coin.get("currency", "?"))
            wallet_balance = coin.get("walletBalance", coin.get("balance", 0))
            if float(wallet_balance) > 0.0001:
                rows.append({"Field": f"{coin_name} Balance", "Value": f"{float(wallet_balance):,.4f}"})
    
    if not rows:
        return _format_simple_success_result(data, message)
    
    return {
        "type": "table",
        "title": "💰 Account Balance",
        "columns": ["Field", "Value"],
        "rows": rows,
        "footer": None,
    }


def _format_exposure_result(data: Any, message: str) -> dict[str, Any]:
    """Format total exposure as a human-readable table."""
    if not data or not isinstance(data, dict):
        return None
    
    rows = []
    
    total_exposure = data.get("total_exposure", data.get("totalExposure"))
    margin_used = data.get("margin_used", data.get("marginUsed"))
    margin_ratio = data.get("margin_ratio", data.get("marginRatio"))
    position_count = data.get("position_count", data.get("positionCount"))
    
    if total_exposure is not None:
        rows.append({"Field": "Total Exposure", "Value": _format_currency(total_exposure, 2)})
    if margin_used is not None:
        rows.append({"Field": "Margin Used", "Value": _format_currency(margin_used, 2)})
    if margin_ratio is not None:
        rows.append({"Field": "Margin Ratio", "Value": f"{float(margin_ratio) * 100:.2f}%"})
    if position_count is not None:
        rows.append({"Field": "Open Positions", "Value": str(position_count)})
    
    if not rows:
        return _format_simple_success_result(data, message)
    
    return {
        "type": "table",
        "title": "📊 Total Exposure",
        "columns": ["Field", "Value"],
        "rows": rows,
        "footer": None,
    }


def _format_account_info_result(data: Any, message: str) -> dict[str, Any]:
    """Format account info as a human-readable table."""
    if not data or not isinstance(data, dict):
        return None
    
    rows = []
    
    # Key account settings
    margin_mode = data.get("marginMode", data.get("margin_mode"))
    unified_status = data.get("unifiedMarginStatus", data.get("unified_status"))
    dcp_status = data.get("dcpStatus", data.get("dcp_status"))
    is_master = data.get("isMasterTrader", data.get("is_master_trader"))
    spot_hedging = data.get("spotHedgingStatus", data.get("spot_hedging"))
    
    if margin_mode is not None:
        rows.append({"Field": "Margin Mode", "Value": str(margin_mode)})
    if unified_status is not None:
        status_map = {1: "Regular", 2: "Unified Margin", 3: "UTA (Unified Trading)", 4: "UTA Pro"}
        status_str = status_map.get(int(unified_status), str(unified_status)) if str(unified_status).isdigit() else str(unified_status)
        rows.append({"Field": "Account Type", "Value": status_str})
    if dcp_status is not None:
        rows.append({"Field": "DCP Status", "Value": str(dcp_status)})
    if is_master is not None:
        rows.append({"Field": "Master Trader", "Value": "✓ Yes" if is_master else "✗ No"})
    if spot_hedging is not None:
        rows.append({"Field": "Spot Hedging", "Value": str(spot_hedging)})
    
    if not rows:
        return _format_simple_success_result(data, message)
    
    return {
        "type": "table",
        "title": "ℹ️ Account Info",
        "columns": ["Field", "Value"],
        "rows": rows,
        "footer": None,
    }


def _format_portfolio_result(data: Any, message: str) -> dict[str, Any]:
    """Format portfolio snapshot as a human-readable summary."""
    if not data or not isinstance(data, dict):
        return None
    
    rows = []
    
    # Account summary
    total_equity = data.get("total_equity", data.get("totalEquity"))
    unrealized_pnl = data.get("unrealized_pnl", data.get("unrealizedPnl"))
    position_count = data.get("position_count", 0)
    
    if total_equity is not None:
        rows.append({"Field": "Total Equity", "Value": _format_currency(total_equity, 2)})
    if unrealized_pnl is not None:
        rows.append({"Field": "Unrealized PnL", "Value": _format_currency(unrealized_pnl, 2)})
    if position_count is not None:
        rows.append({"Field": "Open Positions", "Value": str(position_count)})
    
    # Positions summary if available
    positions = data.get("positions", [])
    if positions:
        rows.append({"Field": "---", "Value": "--- Positions ---"})
        for pos in positions[:5]:
            symbol = pos.get("symbol", "?")
            side = pos.get("side", "?")
            size = pos.get("size", "?")
            pnl = pos.get("unrealisedPnl", pos.get("unrealized_pnl", 0))
            rows.append({"Field": symbol, "Value": f"{side} {size} ({_format_currency(pnl, 2)})"})
    
    if not rows:
        return _format_simple_success_result(data, message)
    
    return {
        "type": "table",
        "title": "💼 Portfolio Snapshot",
        "columns": ["Field", "Value"],
        "rows": rows,
        "footer": f"{position_count} position(s)" if position_count else None,
    }


def _format_coin_greeks_result(data: Any, message: str) -> dict[str, Any]:
    """Format coin greeks as a human-readable table."""
    if not data or not isinstance(data, dict):
        return None
    
    greeks = data.get("greeks", data.get("coin", []))
    if not greeks:
        return {
            "type": "simple",
            "title": "📈 Coin Greeks",
            "content": "No options greeks data available.",
            "footer": None,
        }
    
    if isinstance(greeks, list):
        rows = []
        for g in greeks[:10]:
            rows.append({
                "Coin": g.get("baseCoin", g.get("coin", "?")),
                "Delta": f"{float(g.get('totalDelta', 0)):.4f}",
                "Gamma": f"{float(g.get('totalGamma', 0)):.6f}",
                "Vega": f"{float(g.get('totalVega', 0)):.4f}",
                "Theta": f"{float(g.get('totalTheta', 0)):.4f}",
            })
        
        return {
            "type": "table",
            "title": "📈 Coin Greeks",
            "columns": ["Coin", "Delta", "Gamma", "Vega", "Theta"],
            "rows": rows,
            "footer": None,
        }
    
    return _format_simple_success_result(data, message)


def _format_transferable_result(data: Any, message: str) -> dict[str, Any]:
    """Format transferable amount as a human-readable display."""
    if not data or not isinstance(data, dict):
        return None
    
    rows = []
    
    coin = data.get("coin", data.get("currency", "?"))
    amount = data.get("transferableAmount", data.get("withdrawable", data.get("amount")))
    
    if coin:
        rows.append({"Field": "Coin", "Value": str(coin)})
    if amount is not None:
        rows.append({"Field": "Transferable Amount", "Value": f"{float(amount):,.4f}"})
    
    if not rows:
        return _format_simple_success_result(data, message)
    
    return {
        "type": "table",
        "title": "💸 Transferable Amount",
        "columns": ["Field", "Value"],
        "rows": rows,
        "footer": None,
    }


def _format_risk_limits_result(data: Any, message: str) -> dict[str, Any]:
    """Format risk limits as a human-readable table."""
    if not data or not isinstance(data, dict):
        return None
    
    limits = data.get("risk_limits", data.get("riskLimit", data.get("list", [])))
    symbol = data.get("symbol", "?")
    
    if not limits:
        return {
            "type": "simple",
            "title": "⚖️ Risk Limits",
            "content": f"No risk limit data for {symbol}.",
            "footer": None,
        }
    
    if isinstance(limits, list):
        rows = []
        for limit in limits[:10]:
            rows.append({
                "ID": str(limit.get("id", limit.get("riskLimitValue", "?"))),
                "Max Position": _format_currency(limit.get("maxPosition", limit.get("limit", 0)), 0),
                "Max Leverage": f"{limit.get('maxLeverage', '?')}x",
                "MMR": f"{float(limit.get('maintainMargin', 0)) * 100:.2f}%",
                "IMR": f"{float(limit.get('initialMargin', 0)) * 100:.2f}%",
            })
        
        return {
            "type": "table",
            "title": f"⚖️ Risk Limits: {symbol}",
            "columns": ["ID", "Max Position", "Max Leverage", "MMR", "IMR"],
            "rows": rows,
            "footer": None,
        }
    
    return _format_simple_success_result(data, message)


def _format_order_placed_result(data: Any, message: str) -> dict[str, Any]:
    """Format order placement result as a human-readable display."""
    if not data or not isinstance(data, dict):
        return None
    
    rows = []
    
    order_id = data.get("orderId", data.get("order_id", ""))
    symbol = data.get("symbol", "?")
    side = data.get("side", "?")
    order_type = data.get("orderType", data.get("type", "?"))
    qty = data.get("qty", data.get("quantity", "?"))
    price = data.get("price", data.get("orderPrice"))
    
    if symbol:
        rows.append({"Field": "Symbol", "Value": str(symbol)})
    if side:
        rows.append({"Field": "Side", "Value": str(side).upper()})
    if order_type:
        rows.append({"Field": "Type", "Value": str(order_type)})
    if qty:
        rows.append({"Field": "Quantity", "Value": str(qty)})
    if price:
        rows.append({"Field": "Price", "Value": _format_currency(price, 4, "")})
    if order_id:
        short_id = order_id[:12] + "..." if len(order_id) > 15 else order_id
        rows.append({"Field": "Order ID", "Value": short_id})
    
    if not rows:
        return _format_simple_success_result(data, message)
    
    return {
        "type": "table",
        "title": "📝 Order Placed",
        "columns": ["Field", "Value"],
        "rows": rows,
        "footer": None,
    }


def _format_price_result(data: Any, message: str) -> dict[str, Any]:
    """Format price result as a human-readable display."""
    if not data or not isinstance(data, dict):
        return None
    
    symbol = data.get("symbol", "?")
    price = data.get("price", data.get("lastPrice", data.get("last_price")))
    
    if price is None:
        return _format_simple_success_result(data, message)
    
    rows = [
        {"Field": "Symbol", "Value": str(symbol)},
        {"Field": "Price", "Value": _format_currency(price, 4, "$")},
    ]
    
    # Add optional fields if present
    bid = data.get("bid", data.get("bid1Price"))
    ask = data.get("ask", data.get("ask1Price"))
    if bid:
        rows.append({"Field": "Best Bid", "Value": _format_currency(bid, 4, "$")})
    if ask:
        rows.append({"Field": "Best Ask", "Value": _format_currency(ask, 4, "$")})
    
    return {
        "type": "table",
        "title": f"💵 Price: {symbol}",
        "columns": ["Field", "Value"],
        "rows": rows,
        "footer": None,
    }


def _format_market_test_result(data: Any, message: str) -> dict[str, Any]:
    """Format market data test result."""
    if not data or not isinstance(data, dict):
        return None
    
    tests = data.get("tests", {})
    if not tests:
        return _format_simple_success_result(data, message)
    
    rows = []
    for test_name, result in tests.items():
        if isinstance(result, dict):
            # Check for "passed", "success", or "ok" fields
            passed = result.get("passed", result.get("success", result.get("ok", False)))
            status = "✓" if passed else "✗"
            detail = result.get("message", result.get("value", ""))
        else:
            status = "✓" if result else "✗"
            detail = str(result) if result else ""
        
        rows.append({
            "Test": test_name.replace("_", " ").title(),
            "Status": status,
            "Result": str(detail)[:40],
        })
    
    passed_count = data.get("passed_count", 0)
    total_count = data.get("total_count", len(tests))
    
    return {
        "type": "table",
        "title": "🧪 Market Data Tests",
        "columns": ["Test", "Status", "Result"],
        "rows": rows,
        "footer": f"{passed_count}/{total_count} tests passed",
    }


def _format_panic_result(data: Any, message: str) -> dict[str, Any]:
    """Format panic close all result."""
    if not data or not isinstance(data, dict):
        return {
            "type": "simple",
            "title": "🚨 PANIC CLOSE",
            "content": message or "Panic close completed.",
            "footer": None,
        }
    
    rows = []
    
    positions_closed = data.get("positions_closed", 0)
    orders_cancelled = data.get("orders_cancelled", 0)
    errors = data.get("errors", [])
    
    rows.append({"Field": "Positions Closed", "Value": str(positions_closed)})
    rows.append({"Field": "Orders Cancelled", "Value": str(orders_cancelled)})
    
    if errors:
        rows.append({"Field": "Errors", "Value": str(len(errors))})
    
    return {
        "type": "table",
        "title": "🚨 PANIC CLOSE",
        "columns": ["Field", "Value"],
        "rows": rows,
        "footer": "All positions closed and orders cancelled" if not errors else f"Completed with {len(errors)} error(s)",
    }
