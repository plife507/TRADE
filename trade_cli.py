#!/usr/bin/env python3
"""
TRADE - Trading Bot CLI

Menu-driven CLI for the TRADE trading bot.
This is a PURE SHELL - it only:
- Gets user input
- Calls tool functions
- Prints results

NO business logic lives here. All operations go through src/tools/*.
All symbols, amounts, and parameters are passed from user input.

Strategies, backtesting, and runners will be added in Phase 2.

Non-interactive smoke test modes:
  python trade_cli.py --smoke data            # Data builder smoke test only
  python trade_cli.py --smoke full            # Full CLI smoke test (data + trading + diagnostics)
  python trade_cli.py --smoke data_extensive  # Extensive data test (clean DB, gaps, fill, sync)
"""

import argparse
import os
import sys
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

# Rich imports
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, IntPrompt, Confirm
from rich.tree import Tree
from rich.align import Align
from rich import print as rprint
from rich.style import Style
from rich.text import Text

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.config.config import get_config
from src.core.application import Application, get_application
from src.utils.logger import setup_logger, get_logger
from src.utils.cli_display import format_action_status, format_action_complete, get_action_label, format_data_result
from src.cli.menus import (
    data_menu as data_menu_handler,
    market_data_menu as market_data_menu_handler,
    orders_menu as orders_menu_handler,
    market_orders_menu as market_orders_menu_handler,
    limit_orders_menu as limit_orders_menu_handler,
    stop_orders_menu as stop_orders_menu_handler,
    manage_orders_menu as manage_orders_menu_handler,
    positions_menu as positions_menu_handler,
    account_menu as account_menu_handler,
)
from src.cli.smoke_tests import (
    run_smoke_suite,
    run_data_builder_smoke,
    run_full_cli_smoke,
    run_extensive_data_smoke,
    run_comprehensive_order_smoke,
)
from src.tools import (
    # Shared types
    ToolResult,
    # Position tools
    list_open_positions_tool,
    get_position_detail_tool,
    close_position_tool,
    panic_close_all_tool,
    set_stop_loss_tool,
    set_take_profit_tool,
    set_position_tpsl_tool,
    # Position configuration tools
    set_risk_limit_tool,
    get_risk_limits_tool,
    set_tp_sl_mode_tool,
    set_auto_add_margin_tool,
    modify_position_margin_tool,
    switch_margin_mode_tool,
    switch_position_mode_tool,
    # Account tools
    get_account_balance_tool,
    get_total_exposure_tool,
    get_account_info_tool,
    get_portfolio_snapshot_tool,
    get_order_history_tool,
    get_closed_pnl_tool,
    # Unified account tools
    get_transaction_log_tool,
    get_collateral_info_tool,
    set_collateral_coin_tool,
    get_borrow_history_tool,
    get_coin_greeks_tool,
    set_account_margin_mode_tool,
    get_transferable_amount_tool,
    # Order tools
    set_leverage_tool,
    market_buy_tool,
    market_sell_tool,
    market_buy_with_tpsl_tool,
    market_sell_with_tpsl_tool,
    limit_buy_tool,
    limit_sell_tool,
    stop_market_buy_tool,
    stop_market_sell_tool,
    stop_limit_buy_tool,
    stop_limit_sell_tool,
    amend_order_tool,
    cancel_order_tool,
    get_open_orders_tool,
    partial_close_position_tool,
    cancel_all_orders_tool,
    # Diagnostics tools
    test_connection_tool,
    get_server_time_offset_tool,
    get_rate_limit_status_tool,
    get_ticker_tool,
    get_websocket_status_tool,
    exchange_health_check_tool,
    get_api_environment_tool,
    # Market data tools
    get_price_tool,
    get_ohlcv_tool,
    get_funding_rate_tool,
    get_open_interest_tool,
    get_orderbook_tool,
    get_instruments_tool,
    run_market_data_tests_tool,
    # Data tools
    get_database_stats_tool,
    list_cached_symbols_tool,
    get_symbol_status_tool,
    get_symbol_summary_tool,
    get_symbol_timeframe_ranges_tool,
    sync_symbols_tool,
    sync_range_tool,
    fill_gaps_tool,
    heal_data_tool,
    delete_symbol_tool,
    cleanup_empty_symbols_tool,
    vacuum_database_tool,
    # Funding & Open Interest tools
    sync_funding_tool,
    get_funding_history_tool,
    sync_open_interest_tool,
    get_open_interest_history_tool,
    # OHLCV query tools
    get_ohlcv_history_tool,
    # Sync to now tools
    sync_to_now_tool,
    sync_to_now_and_fill_gaps_tool,
    # Composite build tools
    build_symbol_history_tool,
)


# Global Console
console = Console()


class BackCommand:
    """Sentinel class to represent 'back' command."""
    pass


BACK = BackCommand()


def is_exit_command(value: str) -> bool:
    """Check if input is an exit command."""
    if not isinstance(value, str):
        return False
    exit_commands = ["back", "b", "q", "quit", "exit", "x"]
    return value.lower().strip() in exit_commands


def clear_screen():
    """Clear terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header():
    """Print CLI header with clear environment indication."""
    config = get_config()
    
    # API mode (Demo vs Live)
    is_demo = config.bybit.use_demo
    mode_str = "DEMO" if is_demo else "LIVE"
    mode_style = "bold green" if is_demo else "bold red"
    
    # Trading mode (paper vs real)
    trading_mode = config.trading.mode
    trade_style = "bold yellow" if trading_mode == "paper" else "bold red"
    
    # Account type
    account_type = "UNIFIED"
    
    # Get API environment summary for extended info
    api_env = config.bybit.get_api_environment_summary()
    trading_url = api_env["trading"]["base_url"]
    data_url = api_env["data"]["base_url"]
    
    grid = Table.grid(expand=True)
    grid.add_column(justify="center", ratio=1)
    grid.add_column(justify="center", ratio=1)
    grid.add_column(justify="center", ratio=1)
    
    grid.add_row(
        f"[{mode_style}]▶ {mode_str} Account[/]",
        f"Trading: [{trade_style}]{trading_mode.upper()}[/]",
        f"[cyan]{account_type}[/]"
    )
    
    # Warning for live mode
    warning_panel = None
    if not is_demo:
        warning_panel = Panel(
            "[bold red]⚠  CAUTION: Connected to LIVE account - REAL MONEY ⚠[/]",
            border_style="red",
            expand=False
        )

    title = Text("TRADE - Bybit Unified Trading Account", style="bold cyan")
    content = [grid]
    if warning_panel:
        content.append(warning_panel)
    
    # Build subtitle with API environment info + session indicator
    subtitle_text = f"[dim]REST: {mode_str}({trading_url}) | DATA: LIVE({data_url}) | Session Mode | v1.0[/dim]"
        
    panel = Panel(
        Align.center(grid),
        title=title,
        border_style="cyan" if is_demo else "red",
        subtitle=subtitle_text
    )
    console.print(panel)
    if warning_panel:
        console.print(Align.center(warning_panel))


def get_input(prompt: str, default: str = "") -> str:
    """
    Get user input with optional default.
    
    Supports exit commands: back, b, q, quit, exit, x
    Returns BACK sentinel if exit command detected.
    """
    hint = "[dim](or 'back'/'b' to cancel)[/]"
    try:
        user_input = Prompt.ask(f"[cyan]{prompt}[/] {hint}", default=default if default else None, show_default=bool(default))
        
        if is_exit_command(user_input):
            return BACK
        return user_input
    except (EOFError, KeyboardInterrupt):
        # User pressed Ctrl+C or closed terminal
        console.print("\n[yellow]Cancelled.[/]")
        return BACK


def get_choice(valid_range: range = None) -> int:
    """
    Get numeric choice from user.
    
    Supports exit commands: back, b, q, quit, exit, x
    Returns BACK sentinel if exit command detected.
    """
    while True:
        try:
            choice_input = Prompt.ask("\n[bold cyan]Enter choice[/] [dim](or 'back'/'b' to go back)[/]")
            
            # Check for exit commands
            if is_exit_command(choice_input):
                return BACK
            
            # Try to parse as integer
            choice = int(choice_input)
            
            if valid_range and choice not in valid_range:
                print_error_below_menu(f"Invalid choice. Please enter a number between {valid_range.start} and {valid_range.stop-1}.")
                continue
            return choice
        except (EOFError, KeyboardInterrupt):
            # User pressed Ctrl+C or closed terminal
            console.print("\n[yellow]Cancelled.[/]")
            return BACK
        except ValueError:
            print_error_below_menu("Invalid input. Please enter a number or 'back'/'b' to go back.")
            continue


class TimeRangeSelection:
    """
    Result from time range selection - can be a preset window or custom start/end.
    
    Usage:
        selection = select_time_range_cli(max_days=7)
        if selection.is_back:
            continue  # User cancelled
        
        # Pass to tool - either window OR start_ms/end_ms will be set
        result = get_order_history_tool(
            window=selection.window,
            start_ms=selection.start_ms,
            end_ms=selection.end_ms,
            ...
        )
    """
    def __init__(
        self,
        window: Optional[str] = None,
        start_ms: Optional[int] = None,
        end_ms: Optional[int] = None,
        is_back: bool = False,
    ):
        self.window = window
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.is_back = is_back
    
    @property
    def is_custom(self) -> bool:
        """True if this is a custom range (start_ms/end_ms set)."""
        return self.start_ms is not None and self.end_ms is not None
    
    @property
    def is_preset(self) -> bool:
        """True if this is a preset window (window string set)."""
        return self.window is not None and not self.is_custom


def _parse_datetime_input(value: str) -> Optional[datetime]:
    """
    Parse a datetime string in various common formats.
    
    Supports:
    - YYYY-MM-DD
    - YYYY-MM-DD HH:MM
    - YYYY-MM-DD HH:MM:SS
    - YYYY-MM-DDTHH:MM:SS (ISO)
    
    Returns:
        datetime object or None if parsing failed
    """
    value = value.strip()
    if not value:
        return None
    
    formats = [
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    
    return None


def select_time_range_cli(
    max_days: int = 7,
    default: str = "24h",
    include_custom: bool = True,
    endpoint_name: str = "history",
) -> TimeRangeSelection:
    """
    Prompt user to select a time range for history queries.
    
    Supports both preset windows (24h, 7d, 30d) and custom date ranges.
    
    Args:
        max_days: Maximum allowed days (7 for most, 30 for borrow history)
        default: Default window if user just presses Enter
        include_custom: Whether to include custom date option
        endpoint_name: Name of the endpoint for error messages
    
    Returns:
        TimeRangeSelection with either:
        - window set (for presets like "24h", "7d")
        - start_ms/end_ms set (for custom ranges)
        - is_back=True (if user cancelled)
    """
    console.print("\n[bold cyan]Select time range:[/]")
    console.print("  1) Last 24 hours")
    console.print("  2) Last 7 days")
    
    if max_days >= 30:
        console.print("  3) Last 30 days")
        max_preset_option = 3
    else:
        max_preset_option = 2
    
    custom_option = max_preset_option + 1 if include_custom else None
    if include_custom:
        console.print(f"  {custom_option}) [bold green]Custom date range[/]")
    
    console.print(f"\n[dim]Default: {default}. Max: {max_days} days.[/]")
    
    max_option = custom_option if include_custom else max_preset_option
    choice_input = get_input(f"Time range [1-{max_option}]", "1")
    if choice_input is BACK:
        return TimeRangeSelection(is_back=True)
    
    # Handle preset selections
    window_map = {
        "1": "24h",
        "2": "7d",
        "3": "30d" if max_days >= 30 else "7d",
    }
    
    # Check if custom was selected
    if include_custom and choice_input == str(custom_option):
        return _prompt_custom_date_range(max_days, endpoint_name)
    
    # Return preset window
    window = window_map.get(choice_input, default)
    return TimeRangeSelection(window=window)


def _prompt_custom_date_range(
    max_days: int,
    endpoint_name: str,
) -> TimeRangeSelection:
    """
    Prompt user for custom start and end dates.
    
    Args:
        max_days: Maximum allowed range in days
        endpoint_name: Name of the endpoint for error messages
    
    Returns:
        TimeRangeSelection with start_ms/end_ms set, or is_back=True
    """
    console.print("\n[bold cyan]Custom Date Range[/]")
    console.print(f"[dim]Format: YYYY-MM-DD or YYYY-MM-DD HH:MM (UTC)[/]")
    console.print(f"[dim]Maximum range: {max_days} days[/]")
    
    # Get start date
    start_input = get_input("Start date (e.g., 2024-01-01)")
    if start_input is BACK:
        return TimeRangeSelection(is_back=True)
    
    start_dt = _parse_datetime_input(start_input)
    if start_dt is None:
        print_error_below_menu(
            f"Invalid start date format: '{start_input}'",
            "Use YYYY-MM-DD or YYYY-MM-DD HH:MM format"
        )
        return TimeRangeSelection(is_back=True)
    
    # Get end date (default to now)
    default_end = datetime.now().strftime("%Y-%m-%d %H:%M")
    end_input = get_input(f"End date (default: now)", default_end)
    if end_input is BACK:
        return TimeRangeSelection(is_back=True)
    
    end_dt = _parse_datetime_input(end_input)
    if end_dt is None:
        print_error_below_menu(
            f"Invalid end date format: '{end_input}'",
            "Use YYYY-MM-DD or YYYY-MM-DD HH:MM format"
        )
        return TimeRangeSelection(is_back=True)
    
    # Validate: start < end
    if start_dt >= end_dt:
        print_error_below_menu(
            "Start date must be before end date",
            f"Start: {start_dt}, End: {end_dt}"
        )
        return TimeRangeSelection(is_back=True)
    
    # Validate: range within max_days
    duration = end_dt - start_dt
    if duration.days > max_days:
        print_error_below_menu(
            f"Date range too large for {endpoint_name}",
            f"Requested {duration.days} days, maximum is {max_days} days"
        )
        return TimeRangeSelection(is_back=True)
    
    # Convert to milliseconds
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    
    console.print(f"\n[green]✓ Using custom range: {start_dt.strftime('%Y-%m-%d %H:%M')} to {end_dt.strftime('%Y-%m-%d %H:%M')} ({duration.days}d {duration.seconds // 3600}h)[/]")
    
    return TimeRangeSelection(start_ms=start_ms, end_ms=end_ms)


def get_time_window(
    max_days: int = 7,
    default: str = "24h",
    include_custom: bool = True,
) -> str:
    """
    DEPRECATED: Use select_time_range_cli() for full custom date support.
    
    This function is kept for backwards compatibility but only returns
    window strings (no custom date ranges).
    
    Args:
        max_days: Maximum allowed days (7 for most, 30 for borrow history)
        default: Default window if user just presses Enter
        include_custom: Whether to include custom date option
    
    Returns:
        Window string like "24h", "7d", "30d" or BACK sentinel
    """
    selection = select_time_range_cli(
        max_days=max_days,
        default=default,
        include_custom=False,  # Don't offer custom in legacy function
    )
    
    if selection.is_back:
        return BACK
    
    return selection.window or default


def print_error_below_menu(error_message: str, error_details: str = None):
    """
    Print error message below the static menu with proper formatting.
    
    Ensures errors appear clearly separated from the menu content.
    """
    # Add spacing to separate from menu
    console.print()  # Empty line
    console.print("[dim]" + "─" * 80 + "[/dim]")  # Separator line
    
    # Print error panel
    error_text = f"[bold red]✗ Error:[/] {error_message}"
    if error_details:
        error_text += f"\n[dim]{error_details}[/dim]"
    
    console.print(Panel(
        error_text,
        border_style="red",
        title="[bold red]ERROR[/]",
        padding=(1, 2)
    ))
    
    # Add spacing after error
    console.print()


def run_tool_action(action_key: str, tool_fn, *args, **kwargs) -> ToolResult:
    """
    Execute a tool with an emoji-enhanced status display.
    
    Shows a running status while the tool executes, ensuring no blank cursor.
    
    Args:
        action_key: Action key for status message (e.g., "account.view_balance")
        tool_fn: The tool function to call
        *args, **kwargs: Arguments to pass to the tool
            - Display-only kwargs (for_symbol, etc.) are used for status but not passed to tool
    
    Returns:
        ToolResult from the tool function
    """
    # Build status message with parameters (uses all kwargs including display-only)
    status_msg = format_action_status(action_key, **kwargs)
    
    # Filter out display-only kwargs before passing to tool function
    display_only_keys = {"for_symbol"}
    tool_kwargs = {k: v for k, v in kwargs.items() if k not in display_only_keys}
    
    try:
        with console.status(f"[bold cyan]{status_msg}[/]", spinner="dots"):
            result = tool_fn(*args, **tool_kwargs)
        return result
    except Exception as e:
        print_error_below_menu(str(e), f"Action: {get_action_label(action_key)}")
        return ToolResult(success=False, error=str(e), message="", data=None)


def run_long_action(action_key: str, tool_fn, *args, cancel_store: bool = True, **kwargs) -> ToolResult:
    """
    Execute a long-running tool with status display and Ctrl+C handling.
    
    For data operations that may take significant time and support cancellation.
    
    Args:
        action_key: Action key for status message
        tool_fn: The tool function to call
        *args: Positional arguments
        cancel_store: Whether to call store.cancel() on KeyboardInterrupt
        **kwargs: Keyword arguments
            - Display-only kwargs (for_symbol, etc.) are used for status but not passed to tool
    
    Returns:
        ToolResult from the tool function
    """
    from src.core.application import get_application
    
    # Build status message (uses all kwargs including display-only)
    status_msg = format_action_status(action_key, **kwargs)
    
    # Filter out display-only kwargs before passing to tool function
    display_only_keys = {"for_symbol"}
    tool_kwargs = {k: v for k, v in kwargs.items() if k not in display_only_keys}
    
    # Suppress shutdown during long operations
    app = get_application()
    app.suppress_shutdown()
    
    try:
        console.print(f"\n[bold cyan]{status_msg}[/]")
        console.print("[dim]Press Ctrl+C to cancel gracefully[/]\n")
        
        with console.status(f"[bold green]▶ {get_action_label(action_key)} in progress...[/]", spinner="dots"):
            result = tool_fn(*args, **tool_kwargs)
        
        # Show completion message
        complete_msg = format_action_complete(action_key, **kwargs)
        console.print(f"[green]✓ {complete_msg}[/]")
        
        return result
        
    except KeyboardInterrupt:
        console.print(f"\n[yellow]⚠️  Operation cancelled by user[/]")
        if cancel_store:
            try:
                from src.data.historical_data_store import get_historical_store
                store = get_historical_store()
                store.cancel()
            except Exception:
                pass  # Store may not be initialized
        return ToolResult(success=False, error="Cancelled by user", message="Operation cancelled", data=None)
        
    except Exception as e:
        print_error_below_menu(str(e), f"Action: {get_action_label(action_key)}")
        return ToolResult(success=False, error=str(e), message="", data=None)
        
    finally:
        app.restore_shutdown()


def print_result(result: ToolResult):
    """Print a ToolResult in a formatted way."""
    if result.success:
        console.print(Panel(f"[bold green]✓ {result.message}[/]", border_style="green"))
        
        if result.data:
            if isinstance(result.data, list):
                # Determine if list of objects or simple list
                if result.data and isinstance(result.data[0], dict):
                    # Table for list of dicts
                    table = Table(show_header=True, header_style="bold magenta")
                    keys = result.data[0].keys()
                    for key in keys:
                        table.add_column(str(key))
                    
                    for item in result.data[:20]:  # Limit rows
                        row_vals = [str(item.get(k, "")) for k in keys]
                        table.add_row(*row_vals)
                    
                    console.print(table)
                    if len(result.data) > 20:
                        console.print(f"[dim]... and {len(result.data) - 20} more items[/]")
                else:
                    # Simple list
                    for item in result.data:
                        console.print(f"  • {item}")
            
            elif isinstance(result.data, dict):
                # Tree view for dictionary
                tree = Tree("[bold cyan]Result Data[/]")
                
                def add_dict_to_tree(d, parent):
                    for k, v in d.items():
                        if isinstance(v, dict):
                            branch = parent.add(f"[yellow]{k}[/]")
                            add_dict_to_tree(v, branch)
                        elif isinstance(v, list):
                            branch = parent.add(f"[yellow]{k}[/]")
                            for item in v[:10]:
                                branch.add(str(item))
                            if len(v) > 10:
                                branch.add(f"[dim]... {len(v)-10} more[/]")
                        else:
                            parent.add(f"[cyan]{k}:[/] {v}")
                
                add_dict_to_tree(result.data, tree)
                console.print(tree)
            else:
                console.print(f"[cyan]Data:[/] {result.data}")
    else:
        # Use robust error printing below menu
        print_error_below_menu(result.error)


def print_data_result(action_key: str, result: ToolResult):
    """
    Print a data builder ToolResult with specialized formatting.
    
    Uses the format_data_result function from cli_display to get
    rich table/summary formatting for data operations.
    """
    if not result.success:
        print_error_below_menu(result.error)
        return
    
    # Try specialized formatter first
    formatted = format_data_result(action_key, result.data, result.message)
    
    if formatted is None:
        # Fall back to generic print_result
        print_result(result)
        return
    
    # Print success message
    console.print(Panel(f"[bold green]✓ {result.message}[/]", border_style="green"))
    
    format_type = formatted.get("type", "simple")
    title = formatted.get("title", "Result")
    footer = formatted.get("footer")
    
    if format_type == "table":
        # Rich table display
        columns = formatted.get("columns", [])
        rows = formatted.get("rows", [])
        
        if rows:
            table = Table(show_header=True, header_style="bold magenta", title=title, 
                         title_style="bold cyan", border_style="blue")
            
            # Add columns with appropriate styles
            for col in columns:
                if col in ("Symbol", "Symbol/TF"):
                    table.add_column(col, style="bold yellow")
                elif col in ("Candles", "Records", "Filled"):
                    table.add_column(col, justify="right", style="cyan")
                elif col in ("Status", "Valid"):
                    table.add_column(col, justify="center")
                elif col in ("From", "To"):
                    table.add_column(col, style="dim")
                else:
                    table.add_column(col)
            
            # Add rows
            for row in rows:
                values = [str(row.get(col, "")) for col in columns]
                # Color status indicators
                colored_values = []
                for i, val in enumerate(values):
                    if val == "✓" or val.startswith("✓"):
                        colored_values.append(f"[green]{val}[/]")
                    elif val == "✗" or val.startswith("⚠"):
                        colored_values.append(f"[yellow]{val}[/]")
                    elif val == "Error":
                        colored_values.append(f"[red]{val}[/]")
                    else:
                        colored_values.append(val)
                table.add_row(*colored_values)
            
            console.print(table)
    
    elif format_type == "simple":
        content = formatted.get("content", "")
        console.print(Panel(content, title=title, border_style="cyan"))
    
    # Print footer if present
    if footer:
        console.print(f"[dim]{footer}[/]")


def print_order_preview(order_type: str, symbol: str, side: str, qty_usd: float, price: float = None, **kwargs):
    """Print a preview panel for an order."""
    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(justify="right", style="cyan")
    grid.add_column(justify="left", style="bold white")
    
    grid.add_row("Type:", order_type)
    grid.add_row("Symbol:", symbol)
    side_style = "green" if side.lower() == "buy" else "red"
    grid.add_row("Side:", f"[{side_style}]{side.upper()}[/]")
    grid.add_row("Amount:", f"${qty_usd:,.2f}")
    
    if price:
        grid.add_row("Price:", f"${price:,.2f}")
        
    for k, v in kwargs.items():
        if v is not None:
            grid.add_row(f"{k.replace('_', ' ').title()}:", str(v))
            
    panel = Panel(
        Align.center(grid),
        title="[bold yellow]Order Preview[/]",
        border_style="yellow",
        subtitle="[dim]Press Enter to execute, Ctrl+C to cancel[/]"
    )
    console.print(panel)


import logging

class TradeCLI:
    """
    Main CLI class.
    
    This is a PURE SHELL - no business logic, no direct exchange calls.
    All operations go through tool functions from src/tools/*.
    """
    
    def __init__(self):
        """Initialize CLI - only config and logger needed."""
        self.config = get_config()
        self.logger = get_logger()
        
    # ==================== MAIN MENU ====================
    
    def main_menu(self):
        """Display main menu."""
        while True:
            clear_screen()
            print_header()
            
            menu = Table(show_header=False, box=None, padding=(0, 2))
            menu.add_column("Key", style="cyan bold", justify="right", width=4)
            menu.add_column("Action", style="bold", width=25)
            menu.add_column("Description", style="dim", width=50)
            
            menu.add_row("1", "Account & Balance", "View balance, exposure, portfolio, transaction history")
            menu.add_row("2", "Positions", "List, manage, close positions, set TP/SL, trailing stops")
            menu.add_row("3", "Orders", "Place market/limit/stop orders, manage open orders")
            menu.add_row("4", "Market Data", "Get prices, OHLCV, funding rates, orderbook, instruments")
            menu.add_row("5", "Data Builder", "Build & manage historical data (DuckDB)")
            menu.add_row("6", "Connection Test", "Test API connectivity and rate limits")
            menu.add_row("7", "Health Check", "Comprehensive system health diagnostic")
            menu.add_row("8", "[bold red]PANIC: Close All & Stop[/]", "[red]Emergency: Close all positions & cancel orders[/]")
            menu.add_row("9", "Exit", "Exit the CLI")
            
            console.print(Panel(Align.center(menu), title="[bold]MAIN MENU[/]", border_style="blue"))
            console.print("[dim]💡 Tip: Type 'back' or 'b' at any prompt to cancel and return to previous menu[/]")
            
            choice = get_choice(valid_range=range(1, 10))
            
            # Handle back command from main menu (same as exit)
            if choice is BACK:
                console.print(f"\n[yellow]Goodbye![/]")
                break
            
            if choice == 1:
                self.account_menu()
            elif choice == 2:
                self.positions_menu()
            elif choice == 3:
                self.orders_menu()
            elif choice == 4:
                self.market_data_menu()
            elif choice == 5:
                self.data_menu()
            elif choice == 6:
                self.connection_test()
            elif choice == 7:
                self.health_check()
            elif choice == 8:
                self.panic_menu()
            elif choice == 9:
                console.print(f"\n[yellow]Goodbye![/]")
                break
    
    # ==================== ACCOUNT MENU ====================
    
    def account_menu(self):
        """Account menu. Delegates to src.cli.menus.account_menu."""
        account_menu_handler(self)
    
    # ==================== POSITIONS MENU ====================
    
    def positions_menu(self):
        """Positions menu. Delegates to src.cli.menus.positions_menu."""
        positions_menu_handler(self)
    
    # ==================== ORDERS MENU ====================
    
    def orders_menu(self):
        """Orders menu. Delegates to src.cli.menus.orders_menu."""
        orders_menu_handler(self)

    def market_orders_menu(self):
        """Market orders menu. Delegates to src.cli.menus.orders_menu."""
        market_orders_menu_handler(self)

    def limit_orders_menu(self):
        """Limit orders menu. Delegates to src.cli.menus.orders_menu."""
        limit_orders_menu_handler(self)

    def stop_orders_menu(self):
        """Stop orders menu. Delegates to src.cli.menus.orders_menu."""
        stop_orders_menu_handler(self)

    def manage_orders_menu(self):
        """Manage orders menu. Delegates to src.cli.menus.orders_menu."""
        manage_orders_menu_handler(self)
    
    # ==================== MARKET DATA MENU ====================
    
    def market_data_menu(self):
        """Market data menu. Delegates to src.cli.menus.market_data_menu."""
        market_data_menu_handler(self)
    
    # ==================== DATA MENU ====================
    
    def data_menu(self):
        """Historical data builder menu (DuckDB-only). Delegates to src.cli.menus.data_menu."""
        data_menu_handler(self)
    
    # ==================== CONNECTION TEST ====================
    
    def connection_test(self):
        """Run connection test."""
        clear_screen()
        print_header()
        
        console.print(Panel("Running Connectivity Diagnostic...", title="[bold]CONNECTION TEST[/]", border_style="blue"))
        
        # Show API environment first
        console.print("\n[bold]API Environment:[/]")
        api_result = get_api_environment_tool()
        if api_result.success:
            data = api_result.data
            trading = data["trading"]
            data_api = data["data"]
            ws = data["websocket"]
            
            env_table = Table(show_header=False, box=None)
            env_table.add_column("Type", style="dim")
            env_table.add_column("Mode", style="bold")
            env_table.add_column("URL", style="dim")
            env_table.add_column("Key", style="dim")
            
            trading_style = "green" if trading["is_demo"] else "red"
            env_table.add_row(
                "Trading REST",
                f"[{trading_style}]{trading['mode']}[/]",
                trading["base_url"],
                "✓" if trading["key_configured"] else "✗"
            )
            env_table.add_row(
                "Data REST",
                f"[green]{data_api['mode']}[/]",
                data_api["base_url"],
                "✓" if data_api["key_configured"] else "⚠ public"
            )
            env_table.add_row(
                "WebSocket",
                f"[{trading_style}]{ws['mode']}[/]",
                ws["public_url"],
                "✓ enabled" if ws.get("enabled") else "○ disabled"
            )
            console.print(env_table)
        
        result = run_tool_action("diagnostics.connection", test_connection_tool)
        print_result(result)
        
        result = run_tool_action("diagnostics.server_time", get_server_time_offset_tool)
        print_result(result)
        
        result = run_tool_action("diagnostics.rate_limits", get_rate_limit_status_tool)
        print_result(result)
        
        # Symbol passed as parameter from user input
        symbol = get_input("\nTest ticker for symbol")
        result = run_tool_action("diagnostics.ticker", get_ticker_tool, symbol, symbol=symbol)
        print_result(result)
        
        Prompt.ask("\nPress Enter to continue")
    
    # ==================== HEALTH CHECK ====================
    
    def health_check(self):
        """Run full health check."""
        clear_screen()
        print_header()
        
        console.print(Panel("System Health Diagnostic", title="[bold]HEALTH CHECK[/]", border_style="blue"))
        
        # Show API environment first
        console.print("\n[bold]API Environment:[/]")
        api_result = get_api_environment_tool()
        if api_result.success:
            data = api_result.data
            trading = data["trading"]
            data_api = data["data"]
            ws = data["websocket"]
            safety = data["safety"]
            
            env_table = Table(show_header=False, box=None)
            env_table.add_column("Type", style="dim")
            env_table.add_column("Mode", style="bold")
            env_table.add_column("URL", style="dim")
            env_table.add_column("Key", style="dim")
            
            trading_style = "green" if trading["is_demo"] else "red"
            env_table.add_row(
                "Trading REST",
                f"[{trading_style}]{trading['mode']}[/]",
                trading["base_url"],
                "✓" if trading["key_configured"] else "✗"
            )
            env_table.add_row(
                "Data REST",
                f"[green]{data_api['mode']}[/]",
                data_api["base_url"],
                "✓" if data_api["key_configured"] else "⚠ public"
            )
            env_table.add_row(
                "WebSocket",
                f"[{trading_style}]{ws['mode']}[/]",
                ws["public_url"],
                "✓ enabled" if ws.get("enabled") else "○ disabled"
            )
            console.print(env_table)
            
            # Safety check
            if safety["mode_consistent"]:
                console.print("[green]✓ Mode consistency: OK[/]")
            else:
                console.print("[yellow]⚠ Mode consistency warnings:[/]")
                for msg in safety["messages"]:
                    console.print(f"  [dim]{msg}[/]")
        
        symbol = get_input("\nSymbol to test")
        
        result = run_tool_action("diagnostics.health_check", exchange_health_check_tool, symbol, symbol=symbol)
        print_result(result)
        
        result = run_tool_action("diagnostics.websocket", get_websocket_status_tool)
        print_result(result)
        
        Prompt.ask("\nPress Enter to continue")
    
    # ==================== PANIC ====================
    
    def panic_menu(self):
        """Panic close all positions."""
        clear_screen()
        print_header()
        
        panel = Panel(
            Align.center(
                "[bold red]⚠️  PANIC MODE ⚠️[/]\n\n"
                "This will:\n"
                "  1. Cancel ALL open orders\n"
                "  2. Close ALL positions at market"
            ),
            border_style="red",
            padding=(1, 2)
        )
        console.print(panel)
        
        confirm = get_input("Type 'PANIC' to confirm", "")
        
        if confirm == "PANIC":
            result = run_tool_action("panic.close_all", panic_close_all_tool, reason="Manual panic from CLI")
            print_result(result)
        else:
            console.print(f"\n[bold green]Panic cancelled.[/]")
        
        Prompt.ask("\nPress Enter to continue")


# =============================================================================
# SMOKE TEST SUITE - Now imported from src.cli.smoke_tests
# =============================================================================
# See: src/cli/smoke_tests.py for run_smoke_suite, run_data_builder_smoke, run_full_cli_smoke


def select_trading_environment() -> bool:
    """
    Interactive trading environment selector at CLI startup.
    
    Allows user to choose between DEMO (safe) and LIVE (real money) trading
    for this session only. Does NOT modify api_keys.env.
    
    Returns:
        True if environment was successfully configured, False to exit.
    """
    config = get_config()
    
    # Get current config from file
    file_is_demo = config.bybit.use_demo
    file_trading_mode = config.trading.mode
    
    clear_screen()
    
    # Title panel
    title = Panel(
        Align.center(
            "[bold cyan]TRADE - Trading Environment Selector[/]\n"
            "[dim]Choose your trading environment for this session[/]"
        ),
        border_style="cyan",
        padding=(1, 2)
    )
    console.print(title)
    
    # Show current file-based config
    file_env = "DEMO" if file_is_demo else "LIVE"
    file_style = "green" if file_is_demo else "red"
    console.print(f"\n[dim]Default from config file:[/] [{file_style}]{file_env}[/] (TRADING_MODE={file_trading_mode})")
    console.print()
    
    # Environment options table
    options = Table(show_header=False, box=None, padding=(0, 2))
    options.add_column("Key", style="cyan bold", justify="center", width=6)
    options.add_column("Environment", style="bold", width=25)
    options.add_column("Description", style="dim", width=45)
    
    options.add_row(
        "1",
        "[bold green]DEMO (Paper)[/]",
        "Demo account (fake funds) - api-demo.bybit.com"
    )
    options.add_row(
        "2",
        "[bold red]LIVE (Real)[/]",
        "Live account (real funds) - api.bybit.com"
    )
    options.add_row(
        "",
        "",
        ""
    )
    options.add_row(
        "q",
        "[dim]Quit[/]",
        "Exit without starting"
    )
    
    console.print(Panel(options, title="[bold]Select Environment[/]", border_style="blue"))
    
    # Default suggestion based on config file
    default_choice = "1" if file_is_demo else "2"
    choice = Prompt.ask(
        f"\n[cyan]Enter choice[/]",
        choices=["1", "2", "q", "Q"],
        default=default_choice
    )
    
    if choice.lower() == "q":
        console.print("\n[yellow]Exiting...[/]")
        return False
    
    if choice == "1":
        # DEMO/PAPER mode - demo account with fake funds
        config.bybit.use_demo = True
        config.trading.mode = "paper"
        console.print("\n[bold green]✓ DEMO (Paper) mode selected[/]")
        console.print("[dim]Trading on Bybit demo account (fake funds, real API orders)[/]")
        console.print("[dim]REST: api-demo.bybit.com | WebSocket: stream-demo.bybit.com[/]")
        console.print("[dim]Data operations use LIVE API for accuracy[/]")
        Prompt.ask("\n[dim]Press Enter to continue[/]")
        return True
    
    elif choice == "2":
        # LIVE mode - requires double confirmation
        return _confirm_live_mode(config)
    
    return False


def _confirm_live_mode(config) -> bool:
    """
    Double confirmation for LIVE trading mode.
    
    Returns:
        True if user confirmed LIVE mode, False to fall back to DEMO.
    """
    clear_screen()
    
    # Warning panel
    warning = Panel(
        Align.center(
            "[bold red]⚠️  WARNING: LIVE TRADING MODE ⚠️[/]\n\n"
            "[red]You are about to trade with REAL MONEY![/]\n\n"
            "This session will:\n"
            "  • Use [bold]api.bybit.com[/] (LIVE API)\n"
            "  • Execute orders with [bold red]REAL FUNDS[/]\n"
            "  • Affect your [bold red]REAL ACCOUNT BALANCE[/]"
        ),
        border_style="red",
        title="[bold red]LIVE MODE[/]",
        padding=(1, 4)
    )
    console.print(warning)
    
    # Show risk caps
    risk_table = Table(show_header=False, box=None, padding=(0, 2))
    risk_table.add_column("Setting", style="dim", width=25)
    risk_table.add_column("Value", style="bold yellow", width=20)
    
    risk_table.add_row("Max Position Size:", f"${config.risk.max_position_size_usd:,.2f}")
    risk_table.add_row("Max Daily Loss:", f"${config.risk.max_daily_loss_usd:,.2f}")
    risk_table.add_row("Max Leverage:", f"{config.risk.max_leverage}x")
    risk_table.add_row("Min Balance Protection:", f"${config.risk.min_balance_usd:,.2f}")
    
    console.print(Panel(risk_table, title="[bold yellow]Current Risk Limits[/]", border_style="yellow"))
    
    # First confirmation
    console.print("\n[bold]First confirmation:[/]")
    confirm1 = Confirm.ask("[yellow]Do you understand that this will use REAL MONEY?[/]", default=False)
    
    if not confirm1:
        console.print("\n[green]✓ Cancelled - using DEMO (Paper) mode[/]")
        config.bybit.use_demo = True
        config.trading.mode = "paper"
        Prompt.ask("\n[dim]Press Enter to continue in DEMO mode[/]")
        return True
    
    # Second confirmation - type LIVE
    console.print("\n[bold]Second confirmation:[/]")
    console.print("[dim]Type 'LIVE' (exactly) to confirm, or anything else to cancel:[/]")
    confirm2 = Prompt.ask("[red]Confirm LIVE mode[/]")
    
    if confirm2 == "LIVE":
        config.bybit.use_demo = False
        config.trading.mode = "real"
        console.print("\n[bold red]⚠️  LIVE (Real) MODE ACTIVATED[/]")
        console.print("[red]Trading on Bybit live account (REAL FUNDS, real API orders)[/]")
        console.print("[dim]REST: api.bybit.com | WebSocket: stream.bybit.com[/]")
        Prompt.ask("\n[dim]Press Enter to continue in LIVE mode[/]")
        return True
    else:
        console.print("\n[green]✓ LIVE mode cancelled - using DEMO (Paper) mode[/]")
        config.bybit.use_demo = True
        config.trading.mode = "paper"
        Prompt.ask("\n[dim]Press Enter to continue in DEMO mode[/]")
        return True


def parse_cli_args() -> argparse.Namespace:
    """
    Parse command-line arguments for trade_cli.
    
    Supports:
      --smoke data   Run data builder smoke test only
      --smoke full   Run full CLI smoke test (data + trading + diagnostics)
    """
    parser = argparse.ArgumentParser(
        description="TRADE - Bybit Unified Trading Account CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python trade_cli.py                  # Interactive mode (default)
  python trade_cli.py --smoke data     # Data builder smoke test
  python trade_cli.py --smoke full     # Full CLI smoke test
        """
    )
    
    parser.add_argument(
        "--smoke",
        choices=["data", "full", "data_extensive", "orders", "live_check"],
        default=None,
        help="Run non-interactive smoke test. 'data'/'full'/'data_extensive'/'orders' use DEMO. 'live_check' tests LIVE connectivity (opt-in, requires LIVE keys)."
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    # Parse CLI arguments FIRST (before any config or logging)
    args = parse_cli_args()
    
    # Setup logging
    setup_logger()
    
    # ===== SMOKE TEST MODE =====
    # If --smoke is specified, run non-interactive smoke tests
    if args.smoke:
        config = get_config()
        
        # Special case: live_check uses LIVE credentials (opt-in, dangerous)
        if args.smoke == "live_check":
            console.print(Panel(
                "[bold red]⚠️  LIVE CHECK SMOKE TEST ⚠️[/]\n"
                "[red]This test uses LIVE API credentials (REAL MONEY account)[/]\n"
                "[dim]Testing connectivity, balance, and limited order placement[/]",
                border_style="red"
            ))
            # Don't force DEMO - use configured mode (should be LIVE for this test)
            # If BYBIT_USE_DEMO=false in env, this uses LIVE
        else:
            # SAFETY: Force DEMO mode for all other smoke tests
            config.bybit.use_demo = True
            config.trading.mode = "paper"
            
            console.print(Panel(
                f"[bold cyan]SMOKE TEST MODE: {args.smoke.upper()}[/]\n"
                "[dim]Forcing DEMO/PAPER mode for safety[/]",
                border_style="cyan"
            ))
        
        # Initialize application lifecycle
        app = get_application()
        
        if not app.initialize():
            console.print(f"\n[bold red]Application initialization failed![/]")
            print_error_below_menu(str(app.get_status().error))
            sys.exit(1)
        
        # Start application (including WebSocket if enabled)
        if not app.start():
            console.print(f"\n[bold yellow]Warning: Application start had issues[/]")
            console.print(f"[yellow]Continuing with REST API fallback...[/]")
        
        try:
            # Run the appropriate smoke suite
            if args.smoke == "data_extensive":
                # Extensive data test with clean database
                exit_code = run_extensive_data_smoke()
            elif args.smoke == "orders":
                # Comprehensive order type testing
                exit_code = run_comprehensive_order_smoke()
            elif args.smoke == "live_check":
                # LIVE connectivity and limited order test
                from src.cli.smoke_tests import run_live_check_smoke
                exit_code = run_live_check_smoke()
            else:
                exit_code = run_smoke_suite(args.smoke, app, config)
            sys.exit(exit_code)
        except KeyboardInterrupt:
            console.print(f"\n[yellow]Smoke test interrupted.[/]")
            sys.exit(130)
        except Exception as e:
            console.print(f"\n[bold red]Smoke test failed with error:[/] {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            app.stop()
            console.print(f"[dim]Smoke test complete.[/]")
    
    # ===== INTERACTIVE MODE (default) =====
    # This modifies config.bybit.use_demo and config.trading.mode in memory
    # for this session only, without changing api_keys.env
    if not select_trading_environment():
        # User chose to quit
        return
    
    # Initialize application lifecycle (uses modified config)
    app = get_application()
    
    if not app.initialize():
        console.print(f"\n[bold red]Application initialization failed![/]")
        print_error_below_menu(str(app.get_status().error))
        return
    
    # Start application (including WebSocket if enabled)
    if not app.start():
        console.print(f"\n[bold yellow]Warning: Application start had issues[/]")
        console.print(f"[yellow]Continuing with REST API fallback...[/]")
    
    # Show WebSocket status
    status = app.get_status()
    if status.websocket_connected:
        console.print(f"[green]WebSocket connected[/] [dim](public: {status.websocket_public}, private: {status.websocket_private})[/]")
    elif app.config.websocket.enable_websocket and app.config.websocket.auto_start:
        console.print(f"[yellow]WebSocket not connected - using REST API[/]")
    
    # Create and run CLI
    cli = TradeCLI()
    
    try:
        cli.main_menu()
    except KeyboardInterrupt:
        console.print(f"\n[yellow]Interrupted. Shutting down...[/]")
    except Exception as e:
        print_error_below_menu(str(e))
        raise
    finally:
        # Graceful shutdown
        app.stop()
        console.print(f"[dim]Goodbye![/]")


if __name__ == "__main__":
    main()
