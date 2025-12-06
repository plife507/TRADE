"""
Tool registry for AI agent and API discovery.

This module provides a registry of available tools with their metadata,
enabling AI agents and API endpoints to discover and invoke tools dynamically.

Usage:
    from src.tools.registry import get_tool, list_tools
    
    # List all available tools
    for name, meta in list_tools().items():
        print(f"{name}: {meta.description}")
    
    # Get a specific tool
    tool = get_tool("set_trailing_stop")
    result = tool.func(symbol="BTCUSDT", trailing_distance=200.0)
"""

from dataclasses import dataclass
from typing import Dict, Any, Callable, Optional

from .position_tools import (
    ToolResult,
    list_open_positions_tool,
    get_position_detail_tool,
    set_stop_loss_tool,
    remove_stop_loss_tool,
    set_take_profit_tool,
    remove_take_profit_tool,
    set_trailing_stop_tool,
    set_trailing_stop_by_percent_tool,
    set_position_tpsl_tool,
    close_position_tool,
    panic_close_all_tool,
)


@dataclass
class ToolMetadata:
    """Metadata for a tool in the registry."""
    name: str
    description: str
    func: Callable[..., ToolResult]
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    category: str = "position_management"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excluding func for serialization)."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "category": self.category,
        }


# Standard output schema for ToolResult
_TOOL_RESULT_SCHEMA = {
    "success": {"type": "bool", "description": "Whether the operation succeeded"},
    "message": {"type": "string", "description": "Human-readable message"},
    "symbol": {"type": "string", "description": "Trading symbol (optional)"},
    "data": {"type": "object", "description": "Structured data payload"},
    "error": {"type": "string", "description": "Error message if failed"},
    "source": {"type": "string", "description": "Data source (websocket/rest_api)"},
}


# ==============================================================================
# Tool Registry
# ==============================================================================

TOOL_REGISTRY: Dict[str, ToolMetadata] = {
    # Position Listing
    "list_open_positions": ToolMetadata(
        name="list_open_positions",
        description="List all open positions, optionally filtered by symbol",
        func=list_open_positions_tool,
        input_schema={
            "symbol": {
                "type": "string",
                "description": "Optional symbol to filter (None for all)",
                "required": False,
            },
        },
        output_schema=_TOOL_RESULT_SCHEMA,
    ),
    
    "get_position_detail": ToolMetadata(
        name="get_position_detail",
        description="Get detailed information for a specific position",
        func=get_position_detail_tool,
        input_schema={
            "symbol": {
                "type": "string",
                "description": "Trading symbol (e.g., BTCUSDT)",
                "required": True,
            },
        },
        output_schema=_TOOL_RESULT_SCHEMA,
    ),
    
    # Stop Loss
    "set_stop_loss": ToolMetadata(
        name="set_stop_loss",
        description="Set or update stop loss price for a position",
        func=set_stop_loss_tool,
        input_schema={
            "symbol": {
                "type": "string",
                "description": "Trading symbol",
                "required": True,
            },
            "stop_price": {
                "type": "float",
                "description": "Stop loss price",
                "required": True,
            },
        },
        output_schema=_TOOL_RESULT_SCHEMA,
    ),
    
    "remove_stop_loss": ToolMetadata(
        name="remove_stop_loss",
        description="Remove stop loss from a position",
        func=remove_stop_loss_tool,
        input_schema={
            "symbol": {
                "type": "string",
                "description": "Trading symbol",
                "required": True,
            },
        },
        output_schema=_TOOL_RESULT_SCHEMA,
    ),
    
    # Take Profit
    "set_take_profit": ToolMetadata(
        name="set_take_profit",
        description="Set or update take profit price for a position",
        func=set_take_profit_tool,
        input_schema={
            "symbol": {
                "type": "string",
                "description": "Trading symbol",
                "required": True,
            },
            "take_profit_price": {
                "type": "float",
                "description": "Take profit price",
                "required": True,
            },
        },
        output_schema=_TOOL_RESULT_SCHEMA,
    ),
    
    "remove_take_profit": ToolMetadata(
        name="remove_take_profit",
        description="Remove take profit from a position",
        func=remove_take_profit_tool,
        input_schema={
            "symbol": {
                "type": "string",
                "description": "Trading symbol",
                "required": True,
            },
        },
        output_schema=_TOOL_RESULT_SCHEMA,
    ),
    
    # Combined TP/SL
    "set_position_tpsl": ToolMetadata(
        name="set_position_tpsl",
        description="Set both take profit and stop loss for a position",
        func=set_position_tpsl_tool,
        input_schema={
            "symbol": {
                "type": "string",
                "description": "Trading symbol",
                "required": True,
            },
            "take_profit": {
                "type": "float",
                "description": "Take profit price (None to leave unchanged, 0 to remove)",
                "required": False,
            },
            "stop_loss": {
                "type": "float",
                "description": "Stop loss price (None to leave unchanged, 0 to remove)",
                "required": False,
            },
            "tpsl_mode": {
                "type": "string",
                "description": "'Full' (entire position) or 'Partial'",
                "required": False,
                "default": "Full",
            },
        },
        output_schema=_TOOL_RESULT_SCHEMA,
    ),
    
    # Trailing Stop
    "set_trailing_stop": ToolMetadata(
        name="set_trailing_stop",
        description="Set a trailing stop for a position using absolute distance",
        func=set_trailing_stop_tool,
        input_schema={
            "symbol": {
                "type": "string",
                "description": "Trading symbol",
                "required": True,
            },
            "trailing_distance": {
                "type": "float",
                "description": "Trailing stop distance in price units",
                "required": True,
            },
            "active_price": {
                "type": "float",
                "description": "Price at which trailing becomes active",
                "required": False,
            },
        },
        output_schema=_TOOL_RESULT_SCHEMA,
    ),
    
    "set_trailing_stop_by_percent": ToolMetadata(
        name="set_trailing_stop_by_percent",
        description="Set a trailing stop using percentage of current price",
        func=set_trailing_stop_by_percent_tool,
        input_schema={
            "symbol": {
                "type": "string",
                "description": "Trading symbol",
                "required": True,
            },
            "percent": {
                "type": "float",
                "description": "Trailing stop as percentage (e.g., 1.5 for 1.5%)",
                "required": True,
            },
        },
        output_schema=_TOOL_RESULT_SCHEMA,
    ),
    
    # Close Position
    "close_position": ToolMetadata(
        name="close_position",
        description="Close an open position for a symbol",
        func=close_position_tool,
        input_schema={
            "symbol": {
                "type": "string",
                "description": "Trading symbol",
                "required": True,
            },
            "cancel_conditional_orders": {
                "type": "bool",
                "description": "Cancel conditional TP orders when closing",
                "required": False,
                "default": True,
            },
        },
        output_schema=_TOOL_RESULT_SCHEMA,
    ),
    
    # Panic
    "panic_close_all": ToolMetadata(
        name="panic_close_all",
        description="Emergency close all positions and cancel all orders",
        func=panic_close_all_tool,
        input_schema={},
        output_schema=_TOOL_RESULT_SCHEMA,
        category="emergency",
    ),
}


# ==============================================================================
# Registry Access Functions
# ==============================================================================

def get_tool(name: str) -> Optional[ToolMetadata]:
    """
    Get tool metadata by name.
    
    Args:
        name: Tool name (e.g., "set_trailing_stop")
    
    Returns:
        ToolMetadata or None if not found
    """
    return TOOL_REGISTRY.get(name)


def list_tools() -> Dict[str, ToolMetadata]:
    """
    List all available tools.
    
    Returns:
        Dictionary of tool name -> ToolMetadata
    """
    return TOOL_REGISTRY.copy()


def list_tools_by_category(category: str) -> Dict[str, ToolMetadata]:
    """
    List tools filtered by category.
    
    Args:
        category: Category name (e.g., "position_management", "emergency")
    
    Returns:
        Dictionary of matching tools
    """
    return {
        name: meta
        for name, meta in TOOL_REGISTRY.items()
        if meta.category == category
    }


def get_tool_schemas() -> Dict[str, Dict[str, Any]]:
    """
    Get all tool schemas for API documentation.
    
    Returns:
        Dictionary of tool name -> schema dict (without callable)
    """
    return {
        name: meta.to_dict()
        for name, meta in TOOL_REGISTRY.items()
    }

