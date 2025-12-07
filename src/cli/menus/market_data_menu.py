"""
Market data menu for the CLI.

Handles all live market data operations:
- Price queries
- OHLCV data
- Funding rates
- Open interest
- Order book
- Instrument info
"""

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.align import Align
from rich.text import Text

from src.config.config import get_config
from src.tools import (
    get_price_tool,
    get_ohlcv_tool,
    get_funding_rate_tool,
    get_open_interest_tool,
    get_orderbook_tool,
    get_instruments_tool,
    run_market_data_tests_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def market_data_menu(cli: "TradeCLI"):
    """Market data menu."""
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        run_tool_action, print_result
    )
    
    while True:
        clear_screen()
        print_header()
        
        # Show market data API source info
        config = get_config()
        data_env = config.bybit.get_api_environment_summary()["data"]
        key_status = "✓ Authenticated" if data_env["key_configured"] else "⚠ Public Only"
        api_status_line = Text()
        api_status_line.append("Market Data Source: ", style="dim")
        api_status_line.append(f"{data_env['mode']} ", style="bold green")
        api_status_line.append(f"({data_env['base_url']})", style="dim")
        api_status_line.append(" │ ", style="dim")
        if data_env["key_configured"]:
            api_status_line.append(key_status, style="green")
        else:
            api_status_line.append(key_status, style="yellow")
        console.print(Panel(api_status_line, border_style="dim blue"))
        
        menu = Table(show_header=False, box=None, padding=(0, 2))
        menu.add_column("Key", style="cyan bold", justify="right", width=4)
        menu.add_column("Action", style="bold", width=30)
        menu.add_column("Description", style="dim", width=45)
        
        menu.add_row("1", "Get Price", "Current market price for a symbol")
        menu.add_row("2", "Get OHLCV", "Candlestick data (Open, High, Low, Close, Volume)")
        menu.add_row("3", "Get Funding Rate", "Current funding rate for perpetual futures")
        menu.add_row("4", "Get Open Interest", "Current open interest for a symbol")
        menu.add_row("5", "Get Orderbook", "Order book depth (bids/asks)")
        menu.add_row("6", "Get Instruments", "Symbol info (contract size, tick size, etc.)")
        menu.add_row("7", "Run Market Data Tests", "Test all market data endpoints")
        menu.add_row("8", "Back to Main Menu", "Return to main menu")
        
        console.print(Panel(Align.center(menu), title="[bold]MARKET DATA[/]", border_style="blue"))
        
        choice = get_choice(valid_range=range(1, 9))
        
        if choice == 1:
            symbol = get_input("Symbol")
            result = run_tool_action("market.price", get_price_tool, symbol, symbol=symbol)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 2:
            symbol = get_input("Symbol")
            interval = get_input("Interval", "15")
            limit = int(get_input("Limit", "100"))
            result = run_tool_action("market.ohlcv", get_ohlcv_tool, symbol, interval, limit, symbol=symbol, interval=interval, limit=limit)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 3:
            symbol = get_input("Symbol")
            result = run_tool_action("market.funding", get_funding_rate_tool, symbol, symbol=symbol)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 4:
            symbol = get_input("Symbol")
            result = run_tool_action("market.open_interest", get_open_interest_tool, symbol, symbol=symbol)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 5:
            symbol = get_input("Symbol")
            limit = int(get_input("Depth Limit", "25"))
            result = run_tool_action("market.orderbook", get_orderbook_tool, symbol, limit, symbol=symbol, limit=limit)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 6:
            result = run_tool_action("market.instruments", get_instruments_tool)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 7:
            symbol = get_input("Symbol")
            result = run_tool_action("market.test", run_market_data_tests_tool, symbol, symbol=symbol)
            print_result(result)
            Prompt.ask("\nPress Enter to continue")
        elif choice == 8:
            break

