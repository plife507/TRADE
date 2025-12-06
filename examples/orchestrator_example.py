#!/usr/bin/env python3
"""
Example: Using Tool Registry with an Orchestrator/Bot

This shows how to build a trading bot that dynamically selects and executes tools.
"""

import sys
sys.path.insert(0, ".")

from src.tools.tool_registry import get_registry, ToolRegistry


def example_1_basic_usage():
    """Basic tool execution."""
    print("\n=== Example 1: Basic Tool Execution ===\n")
    
    registry = get_registry()
    
    # Execute a single tool
    result = registry.execute("get_price", symbol="SOLUSDT")
    
    if result.success:
        print(f"Price: ${result.data['price']:.2f}")
    else:
        print(f"Error: {result.error}")


def example_2_list_available_tools():
    """Discover available tools."""
    print("\n=== Example 2: Tool Discovery ===\n")
    
    registry = get_registry()
    
    # List all categories
    print("Categories:")
    for cat in registry.list_categories():
        print(f"  - {cat}")
    
    # List tools in a category
    print("\nOrder tools:")
    for tool in registry.list_tools(category="orders"):
        info = registry.get_tool_info(tool)
        print(f"  - {tool}: {info['description']}")


def example_3_ai_function_calling():
    """Get tool specs for AI/LLM function calling."""
    print("\n=== Example 3: AI Function Calling Format ===\n")
    
    registry = get_registry()
    
    # Get spec for a single tool (OpenAI function format)
    spec = registry.get_tool_info("market_buy")
    
    print(f"Tool: {spec['name']}")
    print(f"Description: {spec['description']}")
    print(f"Parameters:")
    for name, info in spec['parameters'].items():
        required = name in spec['required']
        print(f"  - {name}: {info['type']} {'(required)' if required else '(optional)'}")
        print(f"    {info['description']}")


def example_4_strategy_bot():
    """A simple strategy bot using the registry."""
    print("\n=== Example 4: Strategy Bot ===\n")
    
    registry = get_registry()
    
    # Strategy: Simple breakout entry with TP/SL
    symbol = "SOLUSDT"
    position_size = 100  # USD
    
    # 1. Get current price
    price_result = registry.execute("get_price", symbol=symbol)
    if not price_result.success:
        print(f"Failed to get price: {price_result.error}")
        return
    
    current_price = price_result.data["price"]
    print(f"Current {symbol} price: ${current_price:.4f}")
    
    # 2. Calculate entry/exit levels
    tp_price = round(current_price * 1.02, 4)  # +2% take profit
    sl_price = round(current_price * 0.99, 4)  # -1% stop loss
    
    print(f"Strategy: Long with TP=${tp_price:.4f}, SL=${sl_price:.4f}")
    
    # 3. Execute (commented out - uncomment to actually trade)
    # result = registry.execute(
    #     "market_buy_with_tpsl",
    #     symbol=symbol,
    #     usd_amount=position_size,
    #     take_profit=tp_price,
    #     stop_loss=sl_price,
    # )
    # print(f"Order result: {result.message if result.success else result.error}")


def example_5_batch_execution():
    """Execute multiple tools in sequence."""
    print("\n=== Example 5: Batch Execution ===\n")
    
    registry = get_registry()
    
    # Define a sequence of actions
    actions = [
        {"tool": "get_price", "args": {"symbol": "BTCUSDT"}},
        {"tool": "get_price", "args": {"symbol": "ETHUSDT"}},
        {"tool": "get_price", "args": {"symbol": "SOLUSDT"}},
    ]
    
    # Execute all
    results = registry.execute_batch(actions)
    
    print("Multi-symbol prices:")
    for action, result in zip(actions, results):
        symbol = action["args"]["symbol"]
        if result.success:
            print(f"  {symbol}: ${result.data['price']:,.2f}")
        else:
            print(f"  {symbol}: Error - {result.error}")


def example_6_dynamic_tool_selection():
    """Dynamically select tools based on conditions."""
    print("\n=== Example 6: Dynamic Tool Selection ===\n")
    
    registry = get_registry()
    
    # Scenario: AI agent decides what to do
    signal = "bullish"  # Could come from AI analysis
    symbol = "SOLUSDT"
    
    # Select tool based on signal
    if signal == "bullish":
        tool_name = "market_buy"
    elif signal == "bearish":
        tool_name = "market_sell"
    else:
        print("No clear signal, staying flat")
        return
    
    # Get tool info
    tool_info = registry.get_tool_info(tool_name)
    print(f"Selected: {tool_name}")
    print(f"Description: {tool_info['description']}")
    print(f"Required params: {tool_info['required']}")
    
    # Execute (commented out - uncomment to trade)
    # result = registry.execute(tool_name, symbol=symbol, usd_amount=100)


def example_7_position_management_flow():
    """Complete position management workflow."""
    print("\n=== Example 7: Position Management Flow ===\n")
    
    registry = get_registry()
    symbol = "SOLUSDT"
    
    # 1. Check existing positions
    positions = registry.execute("list_positions")
    if positions.success:
        open_positions = positions.data.get("positions", [])
        print(f"Open positions: {len(open_positions)}")
        
        for pos in open_positions:
            if pos["symbol"] == symbol:
                print(f"  {symbol}: {pos['side']} {pos['size']} @ {pos['entry_price']}")
    
    # 2. If we had a position, we could manage it
    # registry.execute("set_trailing_stop_percent", symbol=symbol, callback_rate=2.0)
    # registry.execute("partial_close", symbol=symbol, close_percent=50)


class SimpleBot:
    """
    Example bot class that uses the registry.
    
    This could be extended to:
    - Load strategies from config
    - React to signals from analysis
    - Manage multiple positions
    """
    
    def __init__(self):
        self.registry = get_registry()
        self.position_size = 100  # Default position size USD
    
    def get_market_state(self, symbol: str) -> dict:
        """Get current market state."""
        result = self.registry.execute("get_price", symbol=symbol)
        if result.success:
            return {"price": result.data["price"]}
        return {}
    
    def open_long(self, symbol: str, tp_pct: float = 2.0, sl_pct: float = 1.0):
        """Open a long position with TP/SL."""
        state = self.get_market_state(symbol)
        if not state:
            return None
        
        price = state["price"]
        tp = round(price * (1 + tp_pct / 100), 4)
        sl = round(price * (1 - sl_pct / 100), 4)
        
        return self.registry.execute(
            "market_buy_with_tpsl",
            symbol=symbol,
            usd_amount=self.position_size,
            take_profit=tp,
            stop_loss=sl,
        )
    
    def open_short(self, symbol: str, tp_pct: float = 2.0, sl_pct: float = 1.0):
        """Open a short position with TP/SL."""
        state = self.get_market_state(symbol)
        if not state:
            return None
        
        price = state["price"]
        tp = round(price * (1 - tp_pct / 100), 4)
        sl = round(price * (1 + sl_pct / 100), 4)
        
        return self.registry.execute(
            "market_sell_with_tpsl",
            symbol=symbol,
            usd_amount=self.position_size,
            take_profit=tp,
            stop_loss=sl,
        )
    
    def close_all(self, reason: str = "Manual close"):
        """Close all positions."""
        return self.registry.execute("panic_close_all", reason=reason)


def example_8_simple_bot():
    """Using the SimpleBot class."""
    print("\n=== Example 8: SimpleBot Class ===\n")
    
    bot = SimpleBot()
    bot.position_size = 50  # $50 per trade
    
    # Get market state
    state = bot.get_market_state("SOLUSDT")
    print(f"SOLUSDT price: ${state.get('price', 0):.4f}")
    
    # Example actions (commented out - uncomment to trade)
    # result = bot.open_long("SOLUSDT", tp_pct=3.0, sl_pct=1.5)
    # result = bot.close_all("Test complete")


if __name__ == "__main__":
    print("=" * 60)
    print("TRADE Bot - Tool Registry Examples")
    print("=" * 60)
    
    example_1_basic_usage()
    example_2_list_available_tools()
    example_3_ai_function_calling()
    example_4_strategy_bot()
    example_5_batch_execution()
    example_6_dynamic_tool_selection()
    example_7_position_management_flow()
    example_8_simple_bot()
    
    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)

