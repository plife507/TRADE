"""
Tool Registry for TRADE Bot Orchestrator.

Provides a unified interface for discovering, describing, and executing tools.
Designed for use by AI agents, strategy bots, or automated systems.

Usage:
    from src.tools.tool_registry import ToolRegistry
    
    registry = ToolRegistry()
    
    # List all available tools
    tools = registry.list_tools()
    
    # Get tool info (for AI/LLM function calling)
    info = registry.get_tool_info("market_buy")
    
    # Execute a tool
    result = registry.execute("market_buy", symbol="SOLUSDT", usd_amount=100)
    
    # Agent can specify trading_env to validate intent
    result = registry.execute("market_buy", symbol="SOLUSDT", usd_amount=100, trading_env="demo")
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
import time
import uuid

from .shared import ToolResult


# Common parameter definition for trading environment validation
# Used by all trading/account/position tools
TRADING_ENV_PARAM = {
    "type": "string",
    "description": "Trading environment for validation ('demo' or 'live'). Validates caller's intent against process config.",
    "optional": True,
}


@dataclass
class ToolSpec:
    """Specification for a registered tool."""
    name: str
    function: Callable
    description: str
    category: str
    parameters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    required: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON/API use."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": self.parameters,
            "required": self.required,
        }


class ToolRegistry:
    """
    Central registry for all trading tools.
    
    Enables dynamic tool discovery and execution for orchestrators/bots.
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}
        self._register_all_tools()
    
    def _register_all_tools(self):
        """Register all available tools."""
        
        # =====================================================================
        # ORDER TOOLS - Market Orders
        # =====================================================================
        from . import market_buy_tool, market_sell_tool
        from . import market_buy_with_tpsl_tool, market_sell_with_tpsl_tool
        
        self._register(
            name="market_buy",
            function=market_buy_tool,
            description="Open a long position with a market buy order",
            category="orders.market",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol (e.g., SOLUSDT)"},
                "usd_amount": {"type": "number", "description": "Position size in USD"},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "usd_amount"],
        )
        
        self._register(
            name="market_sell",
            function=market_sell_tool,
            description="Open a short position with a market sell order",
            category="orders.market",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "usd_amount": {"type": "number", "description": "Position size in USD"},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "usd_amount"],
        )
        
        self._register(
            name="market_buy_with_tpsl",
            function=market_buy_with_tpsl_tool,
            description="Open long position with take profit and stop loss",
            category="orders.market",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "usd_amount": {"type": "number", "description": "Position size in USD"},
                "take_profit": {"type": "number", "description": "Take profit price", "optional": True},
                "stop_loss": {"type": "number", "description": "Stop loss price", "optional": True},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "usd_amount"],
        )
        
        self._register(
            name="market_sell_with_tpsl",
            function=market_sell_with_tpsl_tool,
            description="Open short position with take profit and stop loss",
            category="orders.market",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "usd_amount": {"type": "number", "description": "Position size in USD"},
                "take_profit": {"type": "number", "description": "Take profit price", "optional": True},
                "stop_loss": {"type": "number", "description": "Stop loss price", "optional": True},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "usd_amount"],
        )
        
        # =====================================================================
        # ORDER TOOLS - Limit Orders
        # =====================================================================
        from . import limit_buy_tool, limit_sell_tool, partial_close_position_tool
        
        self._register(
            name="limit_buy",
            function=limit_buy_tool,
            description="Place a limit buy order",
            category="orders.limit",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "usd_amount": {"type": "number", "description": "Position size in USD"},
                "price": {"type": "number", "description": "Limit price"},
                "time_in_force": {"type": "string", "description": "GTC, IOC, FOK, or PostOnly", "default": "GTC"},
                "reduce_only": {"type": "boolean", "description": "Reduce-only order", "default": False},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "usd_amount", "price"],
        )
        
        self._register(
            name="limit_sell",
            function=limit_sell_tool,
            description="Place a limit sell order",
            category="orders.limit",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "usd_amount": {"type": "number", "description": "Position size in USD"},
                "price": {"type": "number", "description": "Limit price"},
                "time_in_force": {"type": "string", "description": "GTC, IOC, FOK, or PostOnly", "default": "GTC"},
                "reduce_only": {"type": "boolean", "description": "Reduce-only order", "default": False},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "usd_amount", "price"],
        )
        
        self._register(
            name="partial_close",
            function=partial_close_position_tool,
            description="Partially close a position by percentage",
            category="orders.limit",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "close_percent": {"type": "number", "description": "Percentage to close (0-100)"},
                "price": {"type": "number", "description": "Limit price (None for market)", "optional": True},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "close_percent"],
        )
        
        # =====================================================================
        # ORDER TOOLS - Stop Orders (Conditional)
        # =====================================================================
        from . import stop_market_buy_tool, stop_market_sell_tool
        from . import stop_limit_buy_tool, stop_limit_sell_tool
        
        self._register(
            name="stop_market_buy",
            function=stop_market_buy_tool,
            description="Place stop market buy (triggers when price rises/falls to trigger)",
            category="orders.stop",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "usd_amount": {"type": "number", "description": "Position size in USD"},
                "trigger_price": {"type": "number", "description": "Price to trigger order"},
                "trigger_direction": {"type": "integer", "description": "1=rises to, 2=falls to", "default": 1},
                "reduce_only": {"type": "boolean", "description": "Reduce-only order", "default": False},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "usd_amount", "trigger_price"],
        )
        
        self._register(
            name="stop_market_sell",
            function=stop_market_sell_tool,
            description="Place stop market sell (triggers when price rises/falls to trigger)",
            category="orders.stop",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "usd_amount": {"type": "number", "description": "Position size in USD"},
                "trigger_price": {"type": "number", "description": "Price to trigger order"},
                "trigger_direction": {"type": "integer", "description": "1=rises to, 2=falls to", "default": 2},
                "reduce_only": {"type": "boolean", "description": "Reduce-only order", "default": False},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "usd_amount", "trigger_price"],
        )
        
        self._register(
            name="stop_limit_buy",
            function=stop_limit_buy_tool,
            description="Place stop limit buy (triggers limit order at trigger price)",
            category="orders.stop",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "usd_amount": {"type": "number", "description": "Position size in USD"},
                "trigger_price": {"type": "number", "description": "Price to trigger order"},
                "limit_price": {"type": "number", "description": "Limit price for triggered order"},
                "trigger_direction": {"type": "integer", "description": "1=rises to, 2=falls to", "default": 1},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "usd_amount", "trigger_price", "limit_price"],
        )
        
        self._register(
            name="stop_limit_sell",
            function=stop_limit_sell_tool,
            description="Place stop limit sell (triggers limit order at trigger price)",
            category="orders.stop",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "usd_amount": {"type": "number", "description": "Position size in USD"},
                "trigger_price": {"type": "number", "description": "Price to trigger order"},
                "limit_price": {"type": "number", "description": "Limit price for triggered order"},
                "trigger_direction": {"type": "integer", "description": "1=rises to, 2=falls to", "default": 2},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "usd_amount", "trigger_price", "limit_price"],
        )
        
        # =====================================================================
        # ORDER TOOLS - Management
        # =====================================================================
        from . import get_open_orders_tool, cancel_order_tool, amend_order_tool, cancel_all_orders_tool
        
        self._register(
            name="get_open_orders",
            function=get_open_orders_tool,
            description="Get list of open orders",
            category="orders.manage",
            parameters={
                "symbol": {"type": "string", "description": "Filter by symbol", "optional": True},
                "order_filter": {"type": "string", "description": "Order/StopOrder/tpslOrder", "optional": True},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=[],
        )
        
        self._register(
            name="cancel_order",
            function=cancel_order_tool,
            description="Cancel a specific order by ID",
            category="orders.manage",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "order_id": {"type": "string", "description": "Order ID to cancel", "optional": True},
                "order_link_id": {"type": "string", "description": "Custom order ID", "optional": True},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol"],
        )
        
        self._register(
            name="amend_order",
            function=amend_order_tool,
            description="Modify an existing order",
            category="orders.manage",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "order_id": {"type": "string", "description": "Order ID", "optional": True},
                "qty": {"type": "number", "description": "New quantity", "optional": True},
                "price": {"type": "number", "description": "New price", "optional": True},
                "take_profit": {"type": "number", "description": "New TP", "optional": True},
                "stop_loss": {"type": "number", "description": "New SL", "optional": True},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol"],
        )
        
        self._register(
            name="cancel_all_orders",
            function=cancel_all_orders_tool,
            description="Cancel all open orders",
            category="orders.manage",
            parameters={
                "symbol": {"type": "string", "description": "Filter by symbol", "optional": True},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=[],
        )
        
        # =====================================================================
        # POSITION TOOLS
        # =====================================================================
        from . import (
            list_open_positions_tool, get_position_detail_tool, close_position_tool,
            set_take_profit_tool, set_stop_loss_tool, remove_take_profit_tool, remove_stop_loss_tool,
            set_trailing_stop_tool, set_trailing_stop_by_percent_tool,
            panic_close_all_tool,
        )
        
        self._register(
            name="list_positions",
            function=list_open_positions_tool,
            description="List all open positions",
            category="positions",
            parameters={
                "trading_env": TRADING_ENV_PARAM,
            },
            required=[],
        )
        
        self._register(
            name="get_position",
            function=get_position_detail_tool,
            description="Get details of a specific position",
            category="positions",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol"],
        )
        
        self._register(
            name="close_position",
            function=close_position_tool,
            description="Close an open position at market",
            category="positions",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol"],
        )
        
        self._register(
            name="set_take_profit",
            function=set_take_profit_tool,
            description="Set take profit for a position",
            category="positions.tpsl",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "take_profit": {"type": "number", "description": "Take profit price"},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "take_profit"],
        )
        
        self._register(
            name="set_stop_loss",
            function=set_stop_loss_tool,
            description="Set stop loss for a position",
            category="positions.tpsl",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "stop_loss": {"type": "number", "description": "Stop loss price"},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "stop_loss"],
        )
        
        self._register(
            name="remove_take_profit",
            function=remove_take_profit_tool,
            description="Remove take profit from position",
            category="positions.tpsl",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol"],
        )
        
        self._register(
            name="remove_stop_loss",
            function=remove_stop_loss_tool,
            description="Remove stop loss from position",
            category="positions.tpsl",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol"],
        )
        
        self._register(
            name="set_trailing_stop",
            function=set_trailing_stop_tool,
            description="Set trailing stop by distance",
            category="positions.trailing",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "trailing_distance": {"type": "number", "description": "Distance in price units (0 to remove)"},
                "active_price": {"type": "number", "description": "Activation price", "optional": True},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "trailing_distance"],
        )
        
        self._register(
            name="set_trailing_stop_percent",
            function=set_trailing_stop_by_percent_tool,
            description="Set trailing stop by percentage",
            category="positions.trailing",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "callback_rate": {"type": "number", "description": "Callback rate percentage (e.g., 3.0 for 3%)"},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "callback_rate"],
        )
        
        self._register(
            name="panic_close_all",
            function=panic_close_all_tool,
            description="Emergency close all positions and cancel all orders",
            category="positions.emergency",
            parameters={
                "reason": {"type": "string", "description": "Reason for panic close", "optional": True},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=[],
        )
        
        # =====================================================================
        # ACCOUNT TOOLS
        # =====================================================================
        from . import get_account_balance_tool, get_portfolio_snapshot_tool, set_leverage_tool
        
        self._register(
            name="get_balance",
            function=get_account_balance_tool,
            description="Get account balance",
            category="account",
            parameters={
                "trading_env": TRADING_ENV_PARAM,
            },
            required=[],
        )
        
        self._register(
            name="get_portfolio",
            function=get_portfolio_snapshot_tool,
            description="Get portfolio snapshot with positions",
            category="account",
            parameters={
                "trading_env": TRADING_ENV_PARAM,
            },
            required=[],
        )
        
        self._register(
            name="set_leverage",
            function=set_leverage_tool,
            description="Set leverage for a symbol",
            category="account",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "leverage": {"type": "integer", "description": "Leverage value (1-125)"},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=["symbol", "leverage"],
        )
        
        # =====================================================================
        # ACCOUNT HISTORY TOOLS (Time-Range Required)
        # =====================================================================
        from . import (
            get_order_history_tool, get_closed_pnl_tool,
            get_transaction_log_tool, get_borrow_history_tool,
        )
        
        self._register(
            name="get_order_history",
            function=get_order_history_tool,
            description="Get order history within a time range (max 7 days)",
            category="account.history",
            parameters={
                "window": {"type": "string", "description": "Time window (24h, 7d). Max 7 days.", "default": "7d"},
                "start_ms": {"type": "integer", "description": "Start timestamp ms (alternative to window)", "optional": True},
                "end_ms": {"type": "integer", "description": "End timestamp ms (alternative to window)", "optional": True},
                "symbol": {"type": "string", "description": "Filter by symbol", "optional": True},
                "limit": {"type": "integer", "description": "Max results (1-50)", "default": 50},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=[],
        )
        
        self._register(
            name="get_closed_pnl",
            function=get_closed_pnl_tool,
            description="Get closed P&L records within a time range (max 7 days)",
            category="account.history",
            parameters={
                "window": {"type": "string", "description": "Time window (24h, 7d). Max 7 days.", "default": "7d"},
                "start_ms": {"type": "integer", "description": "Start timestamp ms (alternative to window)", "optional": True},
                "end_ms": {"type": "integer", "description": "End timestamp ms (alternative to window)", "optional": True},
                "symbol": {"type": "string", "description": "Filter by symbol", "optional": True},
                "limit": {"type": "integer", "description": "Max results (1-50)", "default": 50},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=[],
        )
        
        self._register(
            name="get_transaction_log",
            function=get_transaction_log_tool,
            description="Get transaction logs within a time range (max 7 days)",
            category="account.history",
            parameters={
                "window": {"type": "string", "description": "Time window (24h, 7d). Max 7 days.", "default": "7d"},
                "start_ms": {"type": "integer", "description": "Start timestamp ms (alternative to window)", "optional": True},
                "end_ms": {"type": "integer", "description": "End timestamp ms (alternative to window)", "optional": True},
                "category": {"type": "string", "description": "spot, linear, option", "optional": True},
                "currency": {"type": "string", "description": "Filter by currency (USDT, BTC)", "optional": True},
                "log_type": {"type": "string", "description": "TRADE, SETTLEMENT, TRANSFER_IN, etc.", "optional": True},
                "limit": {"type": "integer", "description": "Max results (1-50)", "default": 50},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=[],
        )
        
        self._register(
            name="get_borrow_history",
            function=get_borrow_history_tool,
            description="Get borrow/interest history within a time range (max 30 days)",
            category="account.history",
            parameters={
                "window": {"type": "string", "description": "Time window (7d, 30d). Max 30 days.", "default": "30d"},
                "start_ms": {"type": "integer", "description": "Start timestamp ms (alternative to window)", "optional": True},
                "end_ms": {"type": "integer", "description": "End timestamp ms (alternative to window)", "optional": True},
                "currency": {"type": "string", "description": "Filter by currency (USDT, BTC)", "optional": True},
                "limit": {"type": "integer", "description": "Max results (1-50)", "default": 50},
                "trading_env": TRADING_ENV_PARAM,
            },
            required=[],
        )
        
        # =====================================================================
        # MARKET DATA TOOLS
        # =====================================================================
        from . import get_price_tool, get_ohlcv_tool, get_funding_rate_tool
        
        self._register(
            name="get_price",
            function=get_price_tool,
            description="Get current price for a symbol",
            category="market",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
            },
            required=["symbol"],
        )
        
        self._register(
            name="get_ohlcv",
            function=get_ohlcv_tool,
            description="Get OHLCV candlestick data",
            category="market",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
                "interval": {"type": "string", "description": "Timeframe (1m, 5m, 15m, 1h, 4h, 1d)", "default": "15m"},
                "limit": {"type": "integer", "description": "Number of candles", "default": 100},
            },
            required=["symbol"],
        )
        
        self._register(
            name="get_funding_rate",
            function=get_funding_rate_tool,
            description="Get funding rate for a symbol",
            category="market",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol"},
            },
            required=["symbol"],
        )
        
        # =====================================================================
        # DATA TOOLS - Database Info
        # =====================================================================
        from . import (
            get_database_stats_tool, list_cached_symbols_tool,
            get_symbol_status_tool, get_symbol_summary_tool,
            get_symbol_timeframe_ranges_tool,
        )
        
        self._register(
            name="get_database_stats",
            function=get_database_stats_tool,
            description="Get database statistics (size, symbol count, candle count)",
            category="data.info",
            parameters={
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=[],
        )
        
        self._register(
            name="list_cached_symbols",
            function=list_cached_symbols_tool,
            description="List all symbols currently cached in the database",
            category="data.info",
            parameters={
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=[],
        )
        
        self._register(
            name="get_symbol_status",
            function=get_symbol_status_tool,
            description="Get per-symbol aggregate status (total candles, gaps, timeframe count)",
            category="data.info",
            parameters={
                "symbol": {"type": "string", "description": "Specific symbol to check", "optional": True},
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=[],
        )
        
        self._register(
            name="get_symbol_summary",
            function=get_symbol_summary_tool,
            description="Get high-level summary of all cached symbols",
            category="data.info",
            parameters={
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=[],
        )
        
        self._register(
            name="get_symbol_timeframe_ranges",
            function=get_symbol_timeframe_ranges_tool,
            description="Get detailed per-symbol/timeframe breakdown with date ranges and health",
            category="data.info",
            parameters={
                "symbol": {"type": "string", "description": "Specific symbol to check", "optional": True},
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=[],
        )
        
        # =====================================================================
        # DATA TOOLS - Sync
        # =====================================================================
        from . import (
            sync_symbols_tool, sync_range_tool,
            sync_funding_tool, sync_open_interest_tool,
            sync_to_now_tool, sync_to_now_and_fill_gaps_tool,
            build_symbol_history_tool,
        )
        
        self._register(
            name="sync_symbols",
            function=sync_symbols_tool,
            description="Sync OHLCV data for symbols by period",
            category="data.sync",
            parameters={
                "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of symbols to sync"},
                "period": {"type": "string", "description": "Period (1D, 1W, 1M, 3M, 6M, 1Y)", "default": "1M"},
                "timeframes": {"type": "array", "items": {"type": "string"}, "description": "Timeframes to sync", "optional": True},
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=["symbols"],
        )
        
        self._register(
            name="sync_range",
            function=sync_range_tool,
            description="Sync OHLCV data for a specific date range",
            category="data.sync",
            parameters={
                "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of symbols to sync"},
                "start": {"type": "string", "description": "Start datetime (ISO format)"},
                "end": {"type": "string", "description": "End datetime (ISO format)"},
                "timeframes": {"type": "array", "items": {"type": "string"}, "description": "Timeframes to sync", "optional": True},
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=["symbols", "start", "end"],
        )
        
        self._register(
            name="sync_funding",
            function=sync_funding_tool,
            description="Sync funding rate history for symbols",
            category="data.sync",
            parameters={
                "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of symbols to sync"},
                "period": {"type": "string", "description": "Period (1M, 3M, 6M, 1Y)", "default": "3M"},
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=["symbols"],
        )
        
        self._register(
            name="sync_open_interest",
            function=sync_open_interest_tool,
            description="Sync open interest history for symbols",
            category="data.sync",
            parameters={
                "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of symbols to sync"},
                "period": {"type": "string", "description": "Period (1D, 1W, 1M, 3M)", "default": "1M"},
                "interval": {"type": "string", "description": "Data interval (5min, 15min, 30min, 1h, 4h, 1d)", "default": "1h"},
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=["symbols"],
        )
        
        self._register(
            name="sync_to_now",
            function=sync_to_now_tool,
            description="Sync data forward from last stored candle to now (no backfill)",
            category="data.sync",
            parameters={
                "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of symbols to sync forward"},
                "timeframes": {"type": "array", "items": {"type": "string"}, "description": "Timeframes to sync", "optional": True},
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=["symbols"],
        )
        
        self._register(
            name="sync_to_now_and_fill_gaps",
            function=sync_to_now_and_fill_gaps_tool,
            description="Sync forward to now AND fill any gaps in existing data",
            category="data.sync",
            parameters={
                "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of symbols to sync and heal"},
                "timeframes": {"type": "array", "items": {"type": "string"}, "description": "Timeframes to sync", "optional": True},
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=["symbols"],
        )
        
        self._register(
            name="build_symbol_history",
            function=build_symbol_history_tool,
            description="Build complete historical data (OHLCV + funding + open interest) for symbols",
            category="data.sync",
            parameters={
                "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of symbols to build history for"},
                "period": {"type": "string", "description": "Period (1D, 1W, 1M, 3M, 6M, 1Y)", "default": "1M"},
                "timeframes": {"type": "array", "items": {"type": "string"}, "description": "OHLCV timeframes", "optional": True},
                "oi_interval": {"type": "string", "description": "Open interest interval", "optional": True},
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=["symbols"],
        )
        
        # =====================================================================
        # DATA TOOLS - Maintenance
        # =====================================================================
        from . import (
            fill_gaps_tool, heal_data_tool,
            delete_symbol_tool, cleanup_empty_symbols_tool, vacuum_database_tool,
            delete_all_data_tool,
            get_funding_history_tool, get_open_interest_history_tool,
        )
        
        self._register(
            name="fill_gaps",
            function=fill_gaps_tool,
            description="Auto-detect and fill gaps in cached data",
            category="data.maintenance",
            parameters={
                "symbol": {"type": "string", "description": "Specific symbol (None for all)", "optional": True},
                "timeframe": {"type": "string", "description": "Specific timeframe (None for all)", "optional": True},
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=[],
        )
        
        self._register(
            name="heal_data",
            function=heal_data_tool,
            description="Run comprehensive data integrity check and repair",
            category="data.maintenance",
            parameters={
                "symbol": {"type": "string", "description": "Specific symbol (None for all)", "optional": True},
                "fix_issues": {"type": "boolean", "description": "Auto-fix issues", "default": True},
                "fill_gaps_after": {"type": "boolean", "description": "Fill gaps after fixing", "default": True},
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=[],
        )
        
        self._register(
            name="delete_symbol",
            function=delete_symbol_tool,
            description="Delete all data for a symbol",
            category="data.maintenance",
            parameters={
                "symbol": {"type": "string", "description": "Symbol to delete"},
                "vacuum": {"type": "boolean", "description": "Vacuum database after deletion", "default": True},
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=["symbol"],
        )
        
        self._register(
            name="cleanup_empty_symbols",
            function=cleanup_empty_symbols_tool,
            description="Remove symbols with no data (invalid symbols)",
            category="data.maintenance",
            parameters={
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=[],
        )
        
        self._register(
            name="vacuum_database",
            function=vacuum_database_tool,
            description="Vacuum the database to reclaim space",
            category="data.maintenance",
            parameters={
                "env": {"type": "string", "description": "Data environment: 'live' (backtest) or 'demo'", "default": "live", "optional": True},
            },
            required=[],
        )
        
        self._register(
            name="delete_all_data",
            function=delete_all_data_tool,
            description="Delete ALL data from the database (OHLCV, funding, OI). DESTRUCTIVE - cannot be undone.",
            category="data.maintenance",
            parameters={
                "vacuum": {"type": "boolean", "description": "Whether to vacuum after deletion", "default": True, "optional": True},
                "env": {"type": "string", "description": "Data environment (live or demo)", "default": "live", "optional": True},
            },
            required=[],
        )
        
        self._register(
            name="get_funding_history",
            function=get_funding_history_tool,
            description="Get funding rate history for a symbol from DuckDB. Use either 'period' OR 'start'/'end' (max 365 days).",
            category="data.query",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol (required)"},
                "period": {"type": "string", "description": "Relative period (1M, 3M, 6M, 1Y) - alternative to start/end", "optional": True},
                "start": {"type": "string", "description": "Start datetime ISO string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)", "optional": True},
                "end": {"type": "string", "description": "End datetime ISO string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)", "optional": True},
                "env": {"type": "string", "description": "Data environment (live or demo)", "default": "live", "optional": True},
            },
            required=["symbol"],
        )
        
        self._register(
            name="get_open_interest_history",
            function=get_open_interest_history_tool,
            description="Get open interest history for a symbol from DuckDB. Use either 'period' OR 'start'/'end' (max 365 days).",
            category="data.query",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol (required)"},
                "period": {"type": "string", "description": "Relative period (1M, 3M, 6M, 1Y) - alternative to start/end", "optional": True},
                "start": {"type": "string", "description": "Start datetime ISO string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)", "optional": True},
                "end": {"type": "string", "description": "End datetime ISO string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)", "optional": True},
                "env": {"type": "string", "description": "Data environment (live or demo)", "default": "live", "optional": True},
            },
            required=["symbol"],
        )
        
        from . import get_ohlcv_history_tool
        
        self._register(
            name="get_ohlcv_history",
            function=get_ohlcv_history_tool,
            description="Get OHLCV candlestick history for a symbol from DuckDB. Use either 'period' OR 'start'/'end' (max 365 days).",
            category="data.query",
            parameters={
                "symbol": {"type": "string", "description": "Trading symbol (required)"},
                "timeframe": {"type": "string", "description": "Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d)", "default": "1h"},
                "period": {"type": "string", "description": "Relative period (1M, 3M, 6M, 1Y) - alternative to start/end", "optional": True},
                "start": {"type": "string", "description": "Start datetime ISO string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)", "optional": True},
                "end": {"type": "string", "description": "End datetime ISO string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)", "optional": True},
                "limit": {"type": "integer", "description": "Max number of candles to return", "optional": True},
                "env": {"type": "string", "description": "Data environment (live or demo)", "default": "live", "optional": True},
            },
            required=["symbol"],
        )
        
        # =====================================================================
        # SYSTEM/DIAGNOSTICS TOOLS
        # =====================================================================
        from . import (
            get_api_environment_tool,
            test_connection_tool,
            get_server_time_offset_tool,
            get_rate_limit_status_tool,
            get_websocket_status_tool,
            exchange_health_check_tool,
            is_healthy_for_trading_tool,
        )
        
        self._register(
            name="get_api_environment",
            function=get_api_environment_tool,
            description="Get API environment info (trading mode, data mode, URLs, key status)",
            category="system.info",
            parameters={},
            required=[],
        )
        
        self._register(
            name="test_connection",
            function=test_connection_tool,
            description="Test exchange connection and return status",
            category="system.diagnostics",
            parameters={},
            required=[],
        )
        
        self._register(
            name="get_server_time_offset",
            function=get_server_time_offset_tool,
            description="Get time offset between local machine and exchange server",
            category="system.diagnostics",
            parameters={},
            required=[],
        )
        
        self._register(
            name="get_rate_limit_status",
            function=get_rate_limit_status_tool,
            description="Get current rate limit status from exchange",
            category="system.diagnostics",
            parameters={},
            required=[],
        )
        
        self._register(
            name="get_websocket_status",
            function=get_websocket_status_tool,
            description="Get detailed WebSocket connection status",
            category="system.diagnostics",
            parameters={},
            required=[],
        )
        
        self._register(
            name="exchange_health_check",
            function=exchange_health_check_tool,
            description="Run comprehensive health check on exchange connection",
            category="system.diagnostics",
            parameters={
                "symbol": {"type": "string", "description": "Symbol to use for public API tests"},
            },
            required=["symbol"],
        )
        
        self._register(
            name="is_healthy_for_trading",
            function=is_healthy_for_trading_tool,
            description="Quick health check for agents before trading",
            category="system.diagnostics",
            parameters={},
            required=[],
        )
        
        # =====================================================================
        # BACKTEST TOOLS
        # =====================================================================
        from . import (
            backtest_list_systems_tool,
            backtest_get_system_tool,
            backtest_run_tool,
            backtest_prepare_data_tool,
            backtest_verify_data_tool,
            backtest_list_strategies_tool,
        )
        
        self._register(
            name="backtest_list_systems",
            function=backtest_list_systems_tool,
            description="List all available backtest system configurations",
            category="backtest.systems",
            parameters={},
            required=[],
        )
        
        self._register(
            name="backtest_get_system",
            function=backtest_get_system_tool,
            description="Get detailed information about a system configuration",
            category="backtest.systems",
            parameters={
                "system_id": {"type": "string", "description": "System configuration ID"},
            },
            required=["system_id"],
        )
        
        self._register(
            name="backtest_run",
            function=backtest_run_tool,
            description="Run a backtest for a system configuration",
            category="backtest.run",
            parameters={
                "system_id": {"type": "string", "description": "System configuration ID"},
                "window_name": {"type": "string", "description": "Window to run (hygiene or test)", "default": "hygiene"},
                "write_artifacts": {"type": "boolean", "description": "Whether to write run artifacts", "default": True},
            },
            required=["system_id"],
        )
        
        self._register(
            name="backtest_prepare_data",
            function=backtest_prepare_data_tool,
            description="Prepare data for backtesting based on system config",
            category="backtest.data",
            parameters={
                "system_id": {"type": "string", "description": "System configuration ID"},
                "fresh_db": {"type": "boolean", "description": "If true, delete all data first (opt-in reset)", "default": False},
            },
            required=["system_id"],
        )
        
        self._register(
            name="backtest_verify_data",
            function=backtest_verify_data_tool,
            description="Verify data quality for a backtest run",
            category="backtest.data",
            parameters={
                "system_id": {"type": "string", "description": "System configuration ID"},
                "window_name": {"type": "string", "description": "Window to verify data for", "default": "hygiene"},
                "heal_gaps": {"type": "boolean", "description": "If true, attempt to heal gaps", "default": True},
            },
            required=["system_id"],
        )
        
        self._register(
            name="backtest_list_strategies",
            function=backtest_list_strategies_tool,
            description="List all available strategies",
            category="backtest.strategies",
            parameters={},
            required=[],
        )

        # =====================================================================
        # BACKTEST TOOLS - IdeaCard-based (Golden Path)
        # =====================================================================
        from . import (
            backtest_preflight_idea_card_tool,
            backtest_run_idea_card_tool,
            backtest_data_fix_tool,
            backtest_list_idea_cards_tool,
            backtest_indicators_tool,
            backtest_idea_card_normalize_tool,
        )

        self._register(
            name="backtest_list_idea_cards",
            function=backtest_list_idea_cards_tool,
            description="List all available IdeaCards for backtesting",
            category="backtest.ideacard",
            parameters={
                "idea_cards_dir": {"type": "string", "description": "Override IdeaCard directory", "optional": True},
            },
            required=[],
        )

        self._register(
            name="backtest_preflight",
            function=backtest_preflight_idea_card_tool,
            description="Run preflight check for an IdeaCard backtest (data coverage, warmup)",
            category="backtest.ideacard",
            parameters={
                "idea_card_id": {"type": "string", "description": "IdeaCard identifier"},
                "env": {"type": "string", "description": "Data environment ('live' or 'demo')", "default": "live"},
                "symbol": {"type": "string", "description": "Override symbol", "optional": True},
                "start": {"type": "string", "description": "Window start datetime", "optional": True},
                "end": {"type": "string", "description": "Window end datetime", "optional": True},
                "fix_gaps": {"type": "boolean", "description": "Auto-fetch missing data", "default": False},
            },
            required=["idea_card_id"],
        )

        self._register(
            name="backtest_run_idea_card",
            function=backtest_run_idea_card_tool,
            description="Run a backtest for an IdeaCard (Golden Path)",
            category="backtest.ideacard",
            parameters={
                "idea_card_id": {"type": "string", "description": "IdeaCard identifier"},
                "env": {"type": "string", "description": "Data environment ('live' or 'demo')", "default": "live"},
                "symbol": {"type": "string", "description": "Override symbol", "optional": True},
                "start": {"type": "string", "description": "Window start datetime", "optional": True},
                "end": {"type": "string", "description": "Window end datetime", "optional": True},
                "smoke": {"type": "boolean", "description": "Run in smoke mode (small window)", "default": False},
                "fix_gaps": {"type": "boolean", "description": "Auto-fetch missing data", "default": True},
            },
            required=["idea_card_id"],
        )

        self._register(
            name="backtest_data_fix",
            function=backtest_data_fix_tool,
            description="Fix data for an IdeaCard backtest (sync/heal)",
            category="backtest.ideacard",
            parameters={
                "idea_card_id": {"type": "string", "description": "IdeaCard identifier"},
                "env": {"type": "string", "description": "Data environment", "default": "live"},
                "symbol": {"type": "string", "description": "Override symbol", "optional": True},
                "start": {"type": "string", "description": "Sync from this date", "optional": True},
                "end": {"type": "string", "description": "Sync to this date", "optional": True},
                "max_lookback_days": {"type": "integer", "description": "Max lookback days", "default": 7},
                "sync_to_now": {"type": "boolean", "description": "Sync to current time", "default": False},
                "fill_gaps": {"type": "boolean", "description": "Fill gaps after sync", "default": True},
                "heal": {"type": "boolean", "description": "Run full heal", "default": False},
            },
            required=["idea_card_id"],
        )

        self._register(
            name="backtest_indicators",
            function=backtest_indicators_tool,
            description="Discover indicator keys for an IdeaCard",
            category="backtest.ideacard",
            parameters={
                "idea_card_id": {"type": "string", "description": "IdeaCard identifier"},
                "data_env": {"type": "string", "description": "Data environment", "default": "live"},
                "symbol": {"type": "string", "description": "Override symbol", "optional": True},
                "compute_values": {"type": "boolean", "description": "Compute actual values", "default": False},
            },
            required=["idea_card_id"],
        )

        self._register(
            name="backtest_normalize_idea_card",
            function=backtest_idea_card_normalize_tool,
            description="Normalize and validate an IdeaCard YAML",
            category="backtest.ideacard",
            parameters={
                "idea_card_id": {"type": "string", "description": "IdeaCard identifier"},
                "idea_cards_dir": {"type": "string", "description": "Override directory", "optional": True},
                "write_in_place": {"type": "boolean", "description": "Write normalized YAML", "default": False},
            },
            required=["idea_card_id"],
        )

        # =====================================================================
        # BACKTEST TOOLS - Audits & Verification
        # =====================================================================
        from . import (
            backtest_audit_toolkit_tool,
            backtest_audit_rollup_parity_tool,
            backtest_math_parity_tool,
            backtest_audit_snapshot_plumbing_tool,
            verify_artifact_parity_tool,
        )

        self._register(
            name="backtest_audit_toolkit",
            function=backtest_audit_toolkit_tool,
            description="Run toolkit contract audit (validates all 42 indicators)",
            category="backtest.audit",
            parameters={
                "sample_bars": {"type": "integer", "description": "Synthetic OHLCV bars", "default": 2000},
                "seed": {"type": "integer", "description": "Random seed", "default": 1337},
                "fail_on_extras": {"type": "boolean", "description": "Fail if extras found", "default": False},
                "strict": {"type": "boolean", "description": "Fail on any breach", "default": True},
            },
            required=[],
        )

        self._register(
            name="backtest_audit_rollup",
            function=backtest_audit_rollup_parity_tool,
            description="Run rollup parity audit (validates 1m price feed accumulation)",
            category="backtest.audit",
            parameters={
                "n_intervals": {"type": "integer", "description": "Number of intervals", "default": 10},
                "quotes_per_interval": {"type": "integer", "description": "Quotes per interval", "default": 15},
                "seed": {"type": "integer", "description": "Random seed", "default": 1337},
                "tolerance": {"type": "number", "description": "Float tolerance", "default": 1e-10},
            },
            required=[],
        )

        self._register(
            name="backtest_audit_math_parity",
            function=backtest_math_parity_tool,
            description="Run math parity audit (contract + in-memory parity)",
            category="backtest.audit",
            parameters={
                "idea_card": {"type": "string", "description": "Path to IdeaCard YAML"},
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "output_dir": {"type": "string", "description": "Output directory for diffs", "optional": True},
            },
            required=["idea_card", "start_date", "end_date"],
        )

        self._register(
            name="backtest_audit_snapshot_plumbing",
            function=backtest_audit_snapshot_plumbing_tool,
            description="Run snapshot plumbing parity audit (validates data flow)",
            category="backtest.audit",
            parameters={
                "idea_card_id": {"type": "string", "description": "IdeaCard identifier"},
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                "symbol": {"type": "string", "description": "Override symbol", "optional": True},
                "max_samples": {"type": "integer", "description": "Max samples", "default": 2000},
                "tolerance": {"type": "number", "description": "Float tolerance", "default": 1e-12},
            },
            required=["idea_card_id", "start_date", "end_date"],
        )

        self._register(
            name="backtest_verify_artifacts",
            function=verify_artifact_parity_tool,
            description="Verify backtest artifact integrity",
            category="backtest.audit",
            parameters={
                "idea_card_id": {"type": "string", "description": "IdeaCard ID", "optional": True},
                "symbol": {"type": "string", "description": "Trading symbol", "optional": True},
                "run_id": {"type": "string", "description": "Specific run ID", "optional": True},
                "base_dir": {"type": "string", "description": "Base backtests directory", "optional": True},
                "run_dir": {"type": "string", "description": "Direct path to run directory", "optional": True},
            },
            required=[],
        )
    
    def _register(
        self,
        name: str,
        function: Callable,
        description: str,
        category: str,
        parameters: Dict[str, Dict[str, Any]],
        required: List[str],
    ):
        """Register a tool."""
        self._tools[name] = ToolSpec(
            name=name,
            function=function,
            description=description,
            category=category,
            parameters=parameters,
            required=required,
        )
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    def list_tools(self, category: Optional[str] = None) -> List[str]:
        """
        List all available tool names.
        
        Args:
            category: Filter by category prefix (e.g., "orders", "positions")
        """
        if category:
            return [name for name, spec in self._tools.items() 
                    if spec.category.startswith(category)]
        return list(self._tools.keys())
    
    def list_categories(self) -> List[str]:
        """List all unique categories."""
        return sorted(set(spec.category for spec in self._tools.values()))
    
    def get_tool_info(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get tool specification for AI/LLM function calling.
        
        Returns dict compatible with OpenAI function calling format.
        """
        spec = self._tools.get(name)
        if not spec:
            return None
        return spec.to_dict()
    
    def get_all_tools_info(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all tool specifications (for AI agent initialization)."""
        tools = []
        for name, spec in self._tools.items():
            if category and not spec.category.startswith(category):
                continue
            tools.append(spec.to_dict())
        return tools
    
    def execute(self, name: str, *, meta: Optional[Dict[str, Any]] = None, **kwargs) -> ToolResult:
        """
        Execute a tool by name with arguments.
        
        Args:
            name: Tool name
            meta: Optional metadata dict with context (run_id, agent_id, trace_id, tool_call_id)
            **kwargs: Tool arguments
        
        Returns:
            ToolResult from the tool execution
        
        Example:
            result = registry.execute("market_buy", symbol="SOLUSDT", usd_amount=100)
            
            # With agent context:
            result = registry.execute(
                "market_buy",
                symbol="SOLUSDT",
                usd_amount=100,
                meta={"run_id": "run-abc123", "agent_id": "strategy-bot"}
            )
        """
        spec = self._tools.get(name)
        if not spec:
            return ToolResult(success=False, error=f"Unknown tool: {name}")
        
        # Validate required parameters
        missing = [p for p in spec.required if p not in kwargs]
        if missing:
            return ToolResult(
                success=False, 
                error=f"Missing required parameters: {', '.join(missing)}"
            )

        # Import logging utilities
        from ..utils.logger import get_logger, redact_dict
        from ..utils.log_context import (
            new_tool_call_context,
            context_from_meta,
            log_context_scope,
        )
        
        logger = get_logger()
        meta = meta or {}
        
        # Extract context from meta and set up tool call context
        ctx_fields = context_from_meta(meta)
        tool_call_id = meta.get("tool_call_id") or meta.get("call_id")
        
        # Redact args for logging
        safe_args = redact_dict(kwargs)
        safe_meta = redact_dict(meta)
        
        # Execute within a tool call context scope
        with new_tool_call_context(name, tool_call_id=tool_call_id) as ctx:
            # Apply any additional context from meta
            if ctx_fields:
                with log_context_scope(**ctx_fields):
                    return self._execute_tool_with_logging(
                        spec, name, ctx.tool_call_id, safe_args, safe_meta, logger, kwargs
                    )
            else:
                return self._execute_tool_with_logging(
                    spec, name, ctx.tool_call_id, safe_args, safe_meta, logger, kwargs
                )
    
    def _execute_tool_with_logging(
        self,
        spec: ToolSpec,
        name: str,
        tool_call_id: str,
        safe_args: Dict[str, Any],
        safe_meta: Dict[str, Any],
        logger,
        kwargs: Dict[str, Any],
    ) -> ToolResult:
        """Execute a tool with structured event logging."""
        started = time.perf_counter()
        
        # Emit tool.call.start event
        logger.event(
            "tool.call.start",
            component="tool_registry",
            tool_name=name,
            category=spec.category,
            args=safe_args,
            meta=safe_meta,
        )

        try:
            result = spec.function(**kwargs)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            
            # Emit tool.call.end event
            logger.event(
                "tool.call.end",
                component="tool_registry",
                tool_name=name,
                success=getattr(result, 'success', None),
                elapsed_ms=elapsed_ms,
                message=getattr(result, 'message', None),
                source=getattr(result, 'source', None),
            )
            return result
            
        except Exception as e:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            
            # Emit tool.call.error event
            logger.event(
                "tool.call.error",
                level="ERROR",
                component="tool_registry",
                tool_name=name,
                elapsed_ms=elapsed_ms,
                error=str(e),
                error_type=type(e).__name__,
            )
            return ToolResult(success=False, error=f"Tool execution failed: {str(e)}")
    
    def execute_batch(self, actions: List[Dict[str, Any]]) -> List[ToolResult]:
        """
        Execute multiple tools in sequence.
        
        Args:
            actions: List of {"tool": "name", "args": {...}} dicts
        
        Returns:
            List of ToolResults
        """
        results = []
        for action in actions:
            tool_name = action.get("tool")
            args = action.get("args", {})
            result = self.execute(tool_name, **args)
            results.append(result)
            
            # Stop on critical failure if specified
            if not result.success and action.get("stop_on_fail", False):
                break
        
        return results


# Singleton instance for convenience
_registry: Optional[ToolRegistry] = None

def get_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry

