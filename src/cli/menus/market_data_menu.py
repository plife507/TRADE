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
from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper
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
    from src.cli.utils import (
        clear_screen, print_header, get_input, get_choice, get_int_input,
        run_tool_action, print_result, print_data_result, print_error_below_menu, BACK,
        get_symbol_input,
    )
    
    while True:
        clear_screen()
        print_header()
        
        # Show market data API source info
        config = get_config()
        data_env = config.bybit.get_api_environment_summary()["data"]
        key_status = "✓ Authenticated" if data_env["key_configured"] else "⚠ Public Only"
        api_status_line = Text()
        api_status_line.append("Market Data Source: ", style=CLIColors.DIM_TEXT)
        api_status_line.append(f"{data_env['mode']} ", style=f"bold {CLIColors.NEON_GREEN}")
        api_status_line.append(f"({data_env['base_url']})", style=CLIColors.DIM_TEXT)
        api_status_line.append(" │ ", style=CLIColors.DIM_TEXT)
        if data_env["key_configured"]:
            api_status_line.append(key_status, style=CLIColors.NEON_GREEN)
        else:
            api_status_line.append(key_status, style=CLIColors.NEON_YELLOW)
        console.print(Panel(api_status_line, border_style=f"dim {CLIColors.NEON_CYAN}"))
        
        menu = CLIStyles.create_menu_table()
        
        menu.add_row("1", f"{CLIIcons.BAG} Get Price", "Current market price for a symbol")
        menu.add_row("2", f"{CLIIcons.CANDLE} Get OHLCV", "Candlestick data (Open, High, Low, Close, Volume)")
        menu.add_row("3", f"{CLIIcons.COIN} Get Funding Rate", "Current funding rate for perpetual futures")
        menu.add_row("4", f"{CLIIcons.LEDGER} Get Open Interest", "Current open interest for a symbol")
        menu.add_row("5", f"{CLIIcons.DATABASE} Get Orderbook", "Order book depth (bids/asks)")
        menu.add_row("6", f"{CLIIcons.NETWORK} Get Instruments", "Symbol info (contract size, tick size, etc.)")
        menu.add_row("7", f"{CLIIcons.TARGET} Run Market Data Tests", "Test all market data endpoints")
        menu.add_row("8", f"{CLIIcons.BACK} Back to Main Menu", "Return to main menu")
        
        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, "MARKET DATA"))
        BillArtWrapper.print_menu_bottom()
        
        choice = get_choice(valid_range=range(1, 9))
        if choice is BACK:
            break
        
        try:
            if choice == 1:
                symbol = get_symbol_input("Symbol")
                if symbol is BACK:
                    continue
                result = run_tool_action("market.price", get_price_tool, symbol=symbol)
                print_data_result("market.price", result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 2:
                symbol = get_symbol_input("Symbol")
                if symbol is BACK:
                    continue
                interval = get_input("Interval", "15")
                if interval is BACK:
                    continue
                limit = get_int_input("Limit", "100")
                if limit is BACK or limit is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                result = run_tool_action("market.ohlcv", get_ohlcv_tool, symbol, interval, limit)
                print_data_result("market.ohlcv", result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 3:
                symbol = get_symbol_input("Symbol")
                if symbol is BACK:
                    continue
                result = run_tool_action("market.funding", get_funding_rate_tool, symbol=symbol)
                print_data_result("market.funding", result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 4:
                symbol = get_symbol_input("Symbol")
                if symbol is BACK:
                    continue
                result = run_tool_action("market.open_interest", get_open_interest_tool, symbol=symbol)
                print_data_result("market.open_interest", result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 5:
                symbol = get_symbol_input("Symbol")
                if symbol is BACK:
                    continue
                limit = get_int_input("Depth Limit", "25")
                if limit is BACK or limit is None:
                    Prompt.ask("\nPress Enter to continue")
                    continue
                result = run_tool_action("market.orderbook", get_orderbook_tool, symbol, limit)
                print_data_result("market.orderbook", result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 6:
                result = run_tool_action("market.instruments", get_instruments_tool)
                print_data_result("market.instruments", result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 7:
                symbol = get_symbol_input("Symbol")
                if symbol is BACK:
                    continue
                result = run_tool_action("market.test", run_market_data_tests_tool, symbol=symbol)
                print_result(result)
                Prompt.ask("\nPress Enter to continue")
            elif choice == 8:
                break
        except Exception as e:
            print_error_below_menu(f"Operation failed: {e}", "An unexpected error occurred. Please try again.")
            Prompt.ask("\nPress Enter to continue")

