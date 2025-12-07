"""
CLI Display Helpers - Finance/Trading Themed Action Descriptions

This module provides emoji-enhanced, high-verbosity status messages for CLI actions.
It is stateless and CLI-only - no tool imports or exchange logic.

Usage:
    from src.utils.cli_display import format_action_status, format_action_complete
    
    status_msg = format_action_status("account.view_balance")
    # Returns: "💰 Fetching account balance..."
"""

from typing import Optional, Dict, Any, List
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
ACTION_REGISTRY: Dict[str, ActionDescriptor] = {
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


def _format_params(params: Dict[str, Any]) -> Dict[str, str]:
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


def format_symbols_list(symbols: List[str], max_display: int = 3) -> str:
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

def format_data_result(action_key: str, result_data: Any, message: str = "") -> Dict[str, Any]:
    """
    Format data builder results for rich display.
    
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
        Formatted display dict
    """
    formatters = {
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
    }
    
    formatter = formatters.get(action_key)
    if formatter:
        return formatter(result_data, message)
    
    # Default: return None to use generic formatting
    return None


def _format_symbols_list_result(data: Any, message: str) -> Dict[str, Any]:
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


def _format_database_stats_result(data: Any, message: str) -> Dict[str, Any]:
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


def _format_symbol_status_result(data: Any, message: str) -> Dict[str, Any]:
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


def _format_symbol_summary_result(data: Any, message: str) -> Dict[str, Any]:
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


def _format_timeframe_ranges_result(data: Any, message: str) -> Dict[str, Any]:
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


def _format_build_history_result(data: Any, message: str) -> Dict[str, Any]:
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


def _format_sync_forward_result(data: Any, message: str) -> Dict[str, Any]:
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


def _format_sync_fill_result(data: Any, message: str) -> Dict[str, Any]:
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


def _format_sync_result(data: Any, message: str) -> Dict[str, Any]:
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


def _format_fill_gaps_result(data: Any, message: str) -> Dict[str, Any]:
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


def _format_heal_result(data: Any, message: str) -> Dict[str, Any]:
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


def _format_delete_result(data: Any, message: str) -> Dict[str, Any]:
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


def _format_cleanup_result(data: Any, message: str) -> Dict[str, Any]:
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
