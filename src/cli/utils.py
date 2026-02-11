"""
CLI utility functions for TRADE trading bot.

Contains:
- Input handling (get_input, get_choice, is_exit_command)
- Display utilities (print_header, print_result, print_error_below_menu)
- Time range selection (select_time_range_cli, TimeRangeSelection)
- Action execution wrappers (run_tool_action, run_long_action)
"""

import os
from datetime import datetime
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.tree import Tree
from rich.align import Align
from rich.text import Text

from ..config.config import get_config
from ..utils.cli_display import format_action_status, format_action_complete, get_action_label, format_data_result
from ..tools import ToolResult
from .styles import CLIStyles, CLIColors, BillArtWrapper, BillArtColors


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
    """Print CLI header with clear environment indication and $100 bill art styling."""
    config = get_config()
    
    is_demo = config.bybit.use_demo
    mode_str = "DEMO" if is_demo else "LIVE"
    trading_mode = config.trading.mode
    account_type = "UNIFIED"
    
    api_env = config.bybit.get_api_environment_summary()
    trading_url = api_env["trading"]["base_url"]
    data_url = api_env["data"]["base_url"]
    
    # Print top art decoration
    BillArtWrapper.print_header_art(is_demo)
    
    # Use art wrapper colors if enabled
    if CLIStyles.use_art_wrapper:
        demo_color = BillArtColors.GREEN_BRIGHT
        live_color = BillArtColors.GOLD_BRIGHT
        mode_color = BillArtColors.GOLD_METALLIC if trading_mode == "paper" else BillArtColors.GOLD_BRIGHT
        account_color = BillArtColors.BLUE_BRIGHT
    else:
        demo_color = CLIColors.NEON_GREEN
        live_color = CLIColors.NEON_RED
        mode_color = CLIColors.NEON_YELLOW if trading_mode == "paper" else CLIColors.NEON_RED
        account_color = CLIColors.NEON_CYAN
    
    # Status Grid (HUD style)
    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(justify="center", ratio=1)
    grid.add_column(justify="center", ratio=1)
    grid.add_column(justify="center", ratio=1)
    
    grid.add_row(
        CLIStyles.status_badge(f"{mode_str} Account", demo_color if is_demo else live_color),
        CLIStyles.status_badge(f"MODE: {trading_mode.upper()}", mode_color),
        CLIStyles.status_badge(account_type, account_color)
    )
    
    # Warning for live mode
    warning_panel = None
    if not is_demo:
        warning_panel = Panel(
            f"[bold {BillArtColors.GOLD_BRIGHT}]⚠  CAUTION: Connected to LIVE account - REAL MONEY ⚠[/]",
            border_style=BillArtColors.GOLD_BRIGHT,
            expand=False
        )

    subtitle_text = f"REST: {mode_str}({trading_url}) | DATA: LIVE({data_url}) | Session Mode | v1.0"
    
    console.print(CLIStyles.get_title_panel(subtitle_text, is_demo))
    console.print(Align.center(grid))
    
    if warning_panel:
        console.print(Align.center(warning_panel))
    
    # Print bottom art decoration
    BillArtWrapper.print_header_art_bottom(is_demo)
    console.print()  # Spacer


def get_input(prompt: str, default: str = "") -> str | BackCommand:
    """Get user input with optional default. Returns BACK sentinel if exit command detected."""
    hint = "[dim](or 'back'/'b' to cancel)[/]"
    try:
        user_input = Prompt.ask(f"[cyan]{prompt}[/] {hint}", default=default if default else None, show_default=bool(default))

        if user_input is not None and is_exit_command(user_input):
            return BACK
        return user_input or ""
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Cancelled.[/]")
        return BACK


def get_choice(valid_range: range | None = None) -> int | BackCommand:
    """Get numeric choice from user. Returns BACK sentinel if exit command detected."""
    while True:
        try:
            choice_input = Prompt.ask("\n[bold cyan]Enter choice[/] [dim](or 'back'/'b' to go back)[/]")

            if is_exit_command(choice_input):
                return BACK

            choice = int(choice_input)

            if valid_range and choice not in valid_range:
                print_error_below_menu(f"Invalid choice. Please enter a number between {valid_range.start} and {valid_range.stop-1}.")
                continue
            return choice
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled.[/]")
            return BACK
        except ValueError:
            print_error_below_menu("Invalid input. Please enter a number or 'back'/'b' to go back.")
            continue


def get_float_input(prompt: str, default: str = "") -> float | BackCommand | None:
    """
    Get float input from user with error handling.
    Returns BACK sentinel if exit command detected or None on error.
    Shows error message and returns None for invalid input (caller should handle).
    """
    value = get_input(prompt, default)
    if isinstance(value, BackCommand):
        return BACK

    if not value and default:
        value = default

    try:
        return float(value)
    except (ValueError, TypeError):
        print_error_below_menu(f"Invalid number: '{value}'", "Please enter a valid number (e.g., 100.50)")
        return None


def get_int_input(prompt: str, default: str = "") -> int | BackCommand | None:
    """
    Get integer input from user with error handling.
    Returns BACK sentinel if exit command detected or None on error.
    Shows error message and returns None for invalid input (caller should handle).
    """
    value = get_input(prompt, default)
    if isinstance(value, BackCommand):
        return BACK

    if not value and default:
        value = default

    try:
        return int(value)
    except (ValueError, TypeError):
        print_error_below_menu(f"Invalid integer: '{value}'", "Please enter a whole number (e.g., 10)")
        return None


def safe_menu_action(action_name: str):
    """
    Decorator to wrap menu actions with error handling.
    Catches all exceptions, displays error, and allows menu to continue.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except KeyboardInterrupt:
                console.print("\n[yellow]Operation cancelled.[/]")
                return None
            except Exception as e:
                print_error_below_menu(
                    str(e), 
                    f"Action: {action_name}\nThe operation failed but you can try again."
                )
                return None
        return wrapper
    return decorator


class TimeRangeSelection:
    """Result from time range selection - can be a preset window or custom start/end."""
    def __init__(
        self,
        window: str | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
        is_back: bool = False,
    ):
        self.window = window
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.is_back = is_back
    
    @property
    def is_custom(self) -> bool:
        return self.start_ms is not None and self.end_ms is not None
    
    @property
    def is_preset(self) -> bool:
        return self.window is not None and not self.is_custom


def _parse_datetime_input(value: str, default_now: bool = False) -> datetime | None:
    """Parse a datetime string. If default_now=True, blank input returns current datetime."""
    value = value.strip()
    if not value:
        return datetime.now() if default_now else None
    
    formats = ["%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
    
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
    """Prompt user to select a time range for history queries."""
    from datetime import timedelta
    
    # Calculate the earliest allowed date
    now = datetime.now()
    earliest = now - timedelta(days=max_days)
    earliest_str = earliest.strftime("%Y-%m-%d")
    
    console.print(f"\n[bold cyan]Select time range for {endpoint_name}:[/]")
    console.print(f"[yellow]⚠ API Limit: Max {max_days} days (earliest: {earliest_str})[/]")
    console.print()
    console.print("  1) Last 24 hours")
    console.print("  2) Last 7 days")
    
    if max_days >= 30:
        console.print("  3) Last 30 days")
        max_preset_option = 3
    else:
        max_preset_option = 2
    
    custom_option = max_preset_option + 1 if include_custom else None
    if include_custom:
        console.print(f"  {custom_option}) Custom date range")
    
    console.print(f"\n[dim]Default: {default}[/]")
    
    max_option = custom_option if include_custom else max_preset_option
    choice_input = get_input(f"Time range [1-{max_option}]", "1")
    if isinstance(choice_input, BackCommand):
        return TimeRangeSelection(is_back=True)

    window_map = {"1": "24h", "2": "7d", "3": "30d" if max_days >= 30 else "7d"}
    
    if include_custom and choice_input == str(custom_option):
        return _prompt_custom_date_range(max_days, endpoint_name)
    
    window = window_map.get(choice_input, default)
    return TimeRangeSelection(window=window)


def _prompt_custom_date_range(max_days: int, endpoint_name: str) -> TimeRangeSelection:
    """Prompt user for custom start and end dates."""
    from datetime import timedelta
    
    now = datetime.now()
    earliest = now - timedelta(days=max_days)
    earliest_str = earliest.strftime("%Y-%m-%d")
    now_str = now.strftime("%Y-%m-%d %H:%M")
    
    console.print("\n[bold cyan]Custom Date Range[/]")
    console.print(f"[yellow]⚠ Max {max_days} days. Earliest start: {earliest_str}[/]")
    console.print(f"[dim]Format: YYYY-MM-DD or YYYY-MM-DD HH:MM[/]")
    
    start_input = get_input(f"Start date (earliest: {earliest_str})")
    if isinstance(start_input, BackCommand):
        return TimeRangeSelection(is_back=True)

    if not start_input.strip():
        print_error_below_menu("Start date is required")
        return TimeRangeSelection(is_back=True)
    
    start_dt = _parse_datetime_input(start_input)
    if start_dt is None:
        print_error_below_menu(f"Invalid date: '{start_input}'", "Use YYYY-MM-DD or YYYY-MM-DD HH:MM")
        return TimeRangeSelection(is_back=True)
    
    # Check if start date is too old
    if start_dt < earliest:
        print_error_below_menu(
            f"Start date too old for {endpoint_name}",
            f"Earliest allowed: {earliest_str} ({max_days} days ago)"
        )
        return TimeRangeSelection(is_back=True)
    
    # Calculate max end date based on start
    max_end = start_dt + timedelta(days=max_days)
    if max_end > now:
        max_end = now
    max_end_str = max_end.strftime("%Y-%m-%d %H:%M")
    
    console.print(f"[dim]Valid end range: {start_dt.strftime('%Y-%m-%d')} to {max_end_str}[/]")
    
    end_input = get_input("End date (blank = now)")
    if isinstance(end_input, BackCommand):
        return TimeRangeSelection(is_back=True)

    end_dt = _parse_datetime_input(end_input, default_now=True)
    if end_dt is None:
        print_error_below_menu(f"Invalid date: '{end_input}'", "Use YYYY-MM-DD or YYYY-MM-DD HH:MM")
        return TimeRangeSelection(is_back=True)
    
    if start_dt >= end_dt:
        print_error_below_menu("Start date must be before end date", f"Start: {start_dt}, End: {end_dt}")
        return TimeRangeSelection(is_back=True)
    
    duration = end_dt - start_dt
    if duration.days > max_days:
        print_error_below_menu(
            f"Range exceeds {max_days}-day limit for {endpoint_name}",
            f"Your range: {duration.days} days. Try end date: {max_end_str}"
        )
        return TimeRangeSelection(is_back=True)
    
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    
    console.print(f"\n[green]✓ Range: {start_dt.strftime('%Y-%m-%d %H:%M')} → {end_dt.strftime('%Y-%m-%d %H:%M')} ({duration.days}d {duration.seconds // 3600}h)[/]")
    
    return TimeRangeSelection(start_ms=start_ms, end_ms=end_ms)




def print_error_below_menu(error_message: str, error_details: str | None = None):
    """Print error message below the static menu with proper formatting."""
    console.print()
    console.print("[dim]" + "─" * 80 + "[/dim]")
    
    # Handle None or empty error messages gracefully
    if not error_message:
        error_message = "An unknown error occurred. Please try again."
    
    error_text = f"[bold red]✗ Error:[/] {error_message}"
    if error_details:
        error_text += f"\n[dim]{error_details}[/dim]"
    
    console.print(Panel(error_text, border_style="red", title="[bold red]ERROR[/]", padding=(1, 2)))
    console.print()


def run_tool_action(action_key: str, tool_fn, *args, **kwargs) -> ToolResult:
    """
    Execute a tool with status display, error handling, and structured event logging.
    
    Args:
        action_key: Key for status message formatting (e.g., "orders.list")
        tool_fn: The tool function to execute
        *args: Positional arguments passed directly to tool_fn
        **kwargs: Keyword arguments passed directly to tool_fn
    
    Returns:
        ToolResult from the tool execution
    """
    import time
    from ..utils.logger import get_logger, redact_dict
    from ..utils.log_context import new_tool_call_context
    
    logger = get_logger()
    status_msg = format_action_status(action_key, **kwargs)
    tool_name = getattr(tool_fn, '__name__', action_key)
    
    # Redact args for logging
    safe_kwargs = redact_dict(kwargs)
    
    # Execute within a tool call context
    with new_tool_call_context(tool_name) as ctx:
        started = time.perf_counter()
        
        # Emit tool.call.start event
        logger.event(
            "tool.call.start",
            component="cli",
            tool_name=tool_name,
            action_key=action_key,
            args=safe_kwargs,
        )
        
        try:
            with console.status(f"[bold cyan]{status_msg}[/]", spinner="dots"):
                result = tool_fn(*args, **kwargs)
            
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            
            # Emit tool.call.end event
            logger.event(
                "tool.call.end",
                component="cli",
                tool_name=tool_name,
                success=getattr(result, 'success', None),
                elapsed_ms=elapsed_ms,
                message=getattr(result, 'message', None),
            )
            return result
            
        except Exception as e:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            
            # Emit tool.call.error event
            logger.event(
                "tool.call.error",
                level="ERROR",
                component="cli",
                tool_name=tool_name,
                elapsed_ms=elapsed_ms,
                error=str(e),
                error_type=type(e).__name__,
            )
            
            print_error_below_menu(str(e), f"Action: {get_action_label(action_key)}")
            return ToolResult(success=False, error=str(e), message="", data=None)


def run_long_action(action_key: str, tool_fn, *args, cancel_store: bool = True, **kwargs) -> ToolResult:
    """
    Execute a long-running tool with status display, Ctrl+C handling, and structured event logging.
    
    Args:
        action_key: Key for status message formatting (e.g., "data.sync_ohlcv")
        tool_fn: The tool function to execute
        *args: Positional arguments passed directly to tool_fn
        cancel_store: Whether to cancel HistoricalDataStore on Ctrl+C
        **kwargs: Keyword arguments passed directly to tool_fn
    
    Returns:
        ToolResult from the tool execution
    """
    import time
    from ..core.application import get_application
    from ..utils.logger import get_logger, redact_dict
    from ..utils.log_context import new_tool_call_context
    
    logger = get_logger()
    status_msg = format_action_status(action_key, **kwargs)
    tool_name = getattr(tool_fn, '__name__', action_key)
    
    # Redact args for logging
    safe_kwargs = redact_dict(kwargs)
    
    app = get_application()
    app.suppress_shutdown()
    
    # Execute within a tool call context
    with new_tool_call_context(tool_name) as ctx:
        started = time.perf_counter()
        
        # Emit tool.call.start event
        logger.event(
            "tool.call.start",
            component="cli",
            tool_name=tool_name,
            action_key=action_key,
            args=safe_kwargs,
            long_running=True,
        )
        
        try:
            console.print(f"\n[bold cyan]{status_msg}[/]")
            console.print("[dim]Press Ctrl+C to cancel gracefully[/]\n")
            
            with console.status(f"[bold green]▶ {get_action_label(action_key)} in progress...[/]", spinner="dots"):
                result = tool_fn(*args, **kwargs)
            
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            
            complete_msg = format_action_complete(action_key, **kwargs)
            console.print(f"[green]✓ {complete_msg}[/]")
            
            # Emit tool.call.end event
            logger.event(
                "tool.call.end",
                component="cli",
                tool_name=tool_name,
                success=getattr(result, 'success', None),
                elapsed_ms=elapsed_ms,
                message=getattr(result, 'message', None),
            )
            
            return result
            
        except KeyboardInterrupt:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            console.print(f"\n[yellow]⚠️  Operation cancelled by user[/]")
            
            if cancel_store:
                try:
                    from ..data.historical_data_store import get_historical_store
                    store = get_historical_store()
                    store.cancel()
                except Exception as e:
                    logger.debug(f"Could not cancel data store: {e}")
            
            # Emit tool.call.cancelled event
            logger.event(
                "tool.call.cancelled",
                level="WARNING",
                component="cli",
                tool_name=tool_name,
                elapsed_ms=elapsed_ms,
                reason="user_interrupt",
            )
            
            return ToolResult(success=False, error="Cancelled by user", message="Operation cancelled", data=None)
            
        except Exception as e:
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            
            # Emit tool.call.error event
            logger.event(
                "tool.call.error",
                level="ERROR",
                component="cli",
                tool_name=tool_name,
                elapsed_ms=elapsed_ms,
                error=str(e),
                error_type=type(e).__name__,
            )
            
            print_error_below_menu(str(e), f"Action: {get_action_label(action_key)}")
            return ToolResult(success=False, error=str(e), message="", data=None)
            
        finally:
            app.restore_shutdown()


def print_result(result: ToolResult):
    """Print a ToolResult in a formatted way."""
    if result.success:
        console.print(Panel(f"[bold {CLIColors.NEON_GREEN}]✓ {result.message}[/]", border_style=CLIColors.NEON_GREEN))
        
        if result.data:
            data: Any = result.data
            if isinstance(data, list):
                if data and isinstance(data[0], dict):
                    table = Table(show_header=True, header_style=f"bold {CLIColors.NEON_MAGENTA}", border_style=CLIColors.BORDER)
                    keys = data[0].keys()
                    for key in keys:
                        table.add_column(str(key))

                    for item in data[:20]:
                        row_vals = [str(item.get(k, "")) for k in keys]
                        table.add_row(*row_vals)
                    
                    console.print(table)
                    if len(data) > 20:
                        console.print(f"[{CLIColors.DIM_TEXT}]... and {len(data) - 20} more items[/]")
                else:
                    for item in data:
                        console.print(f"  • {item}")
            
            elif isinstance(result.data, dict):
                tree = Tree(f"[bold {CLIColors.NEON_CYAN}]Result Data[/]")
                
                def add_dict_to_tree(d, parent):
                    for k, v in d.items():
                        if isinstance(v, dict):
                            branch = parent.add(f"[{CLIColors.NEON_YELLOW}]{k}[/]")
                            add_dict_to_tree(v, branch)
                        elif isinstance(v, list):
                            branch = parent.add(f"[{CLIColors.NEON_YELLOW}]{k}[/]")
                            for item in v[:10]:
                                branch.add(str(item))
                            if len(v) > 10:
                                branch.add(f"[{CLIColors.DIM_TEXT}]... {len(v)-10} more[/]")
                        else:
                            parent.add(f"[{CLIColors.NEON_CYAN}]{k}:[/] {v}")
                
                add_dict_to_tree(result.data, tree)
                console.print(tree)
            else:
                console.print(f"[{CLIColors.NEON_CYAN}]Data:[/] {result.data}")
    else:
        print_error_below_menu(result.error or "Unknown error")


def print_data_result(action_key: str, result: ToolResult):
    """
    Print a ToolResult with specialized formatting based on action_key.
    
    Uses the action-aware formatter registry in cli_display.py to produce
    human-friendly tables and summaries instead of raw tree views.
    """
    if not result.success and not result.data:
        # Only show error if there's no data to display
        print_error_below_menu(result.error or result.message or "An unknown error occurred")
        return
    
    formatted = format_data_result(action_key, result.data, result.message)
    
    if formatted is None:
        print_result(result)
        return
    
    # Show success panel with appropriate color based on result.success
    if result.success:
        console.print(Panel(f"[bold {CLIColors.NEON_GREEN}]✓ {result.message}[/]", border_style=CLIColors.NEON_GREEN))
    else:
        # Partial success or failure with data - show in yellow
        console.print(Panel(f"[bold {CLIColors.NEON_YELLOW}]⚠ {result.message}[/]", border_style=CLIColors.NEON_YELLOW))
    
    format_type = formatted.get("type", "simple")
    title = formatted.get("title", "Result")
    footer = formatted.get("footer")
    
    if format_type == "table":
        columns = formatted.get("columns", [])
        rows = formatted.get("rows", [])
        
        if rows:
            table = Table(show_header=True, header_style=f"bold {CLIColors.NEON_MAGENTA}", title=title, 
                         title_style=f"bold {CLIColors.NEON_CYAN}", border_style=CLIColors.NEON_CYAN)
            
            # Smart column styling based on column name
            for col in columns:
                if col in ("Symbol", "Symbol/TF", "Coin"):
                    table.add_column(col, style=f"bold {CLIColors.NEON_YELLOW}")
                elif col in ("Side",):
                    table.add_column(col, justify="center")
                elif col in ("Candles", "Records", "Filled", "Qty", "Size", "Volume", "Amount"):
                    table.add_column(col, justify="right", style=CLIColors.NEON_CYAN)
                elif col in ("Status", "Valid", "Enabled", "Check"):
                    table.add_column(col, justify="center")
                elif col in ("From", "To", "Time"):
                    table.add_column(col, style=CLIColors.DIM_TEXT)
                elif col in ("Entry", "Exit", "Price", "Mark", "Open", "High", "Low", "Close"):
                    table.add_column(col, justify="right")
                elif col in ("Gross PnL", "Net PnL", "Unreal. PnL", "Fees", "PnL"):
                    table.add_column(col, justify="right")
                elif col in ("Leverage", "ID", "Order ID"):
                    table.add_column(col, justify="center", style=CLIColors.DIM_TEXT)
                elif col in ("Type", "Field", "Component", "Endpoint", "Category"):
                    table.add_column(col, style=CLIColors.NEON_CYAN)
                elif col in ("Value", "Details"):
                    table.add_column(col)
                else:
                    table.add_column(col)
            
            # Row value coloring
            for row in rows:
                values = [str(row.get(col, "")) for col in columns]
                colored_values = []
                for idx, val in enumerate(values):
                    col_name = columns[idx] if idx < len(columns) else ""
                    
                    # Status indicators
                    if val == "✓" or val.startswith("✓"):
                        colored_values.append(f"[{CLIColors.NEON_GREEN}]{val}[/]")
                    elif val == "✗" or val.startswith("⚠") or val == "Error":
                        colored_values.append(f"[{CLIColors.NEON_YELLOW}]{val}[/]")
                    # Side coloring
                    elif col_name == "Side":
                        if val.upper() in ("BUY", "LONG"):
                            colored_values.append(f"[{CLIColors.NEON_GREEN}]{val}[/]")
                        elif val.upper() in ("SELL", "SHORT"):
                            colored_values.append(f"[{CLIColors.NEON_RED}]{val}[/]")
                        else:
                            colored_values.append(val)
                    # PnL coloring (check for negative sign or negative value)
                    elif col_name in ("Gross PnL", "Net PnL", "Unreal. PnL", "PnL"):
                        if val.startswith("-") or val.startswith("-$"):
                            colored_values.append(f"[{CLIColors.NEON_RED}]{val}[/]")
                        elif val.startswith("$0") or val == "$0.00" or val == "$0.0000":
                            colored_values.append(val)
                        else:
                            colored_values.append(f"[{CLIColors.NEON_GREEN}]{val}[/]")
                    # Type indicators for orderbook
                    elif col_name == "Type":
                        if val == "ASK":
                            colored_values.append(f"[{CLIColors.NEON_RED}]{val}[/]")
                        elif val == "BID":
                            colored_values.append(f"[{CLIColors.NEON_GREEN}]{val}[/]")
                        elif "SPREAD" in val:
                            colored_values.append(f"[{CLIColors.NEON_YELLOW}]{val}[/]")
                        else:
                            colored_values.append(val)
                    else:
                        colored_values.append(val)
                table.add_row(*colored_values)
            
            console.print(table)
    
    elif format_type == "simple":
        content = formatted.get("content", "")
        console.print(Panel(content, title=title, border_style=CLIColors.NEON_CYAN))
    
    if footer:
        console.print(f"[{CLIColors.DIM_TEXT}]{footer}[/]")


def print_order_preview(order_type: str, symbol: str, side: str, qty_usd: float, price: float | None = None, **kwargs: Any):
    """Print a preview panel for an order."""
    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(justify="right", style=CLIColors.NEON_CYAN)
    grid.add_column(justify="left", style="bold white")
    
    grid.add_row("Type:", order_type)
    grid.add_row("Symbol:", symbol)
    side_style = CLIColors.NEON_GREEN if side.lower() == "buy" else CLIColors.NEON_RED
    grid.add_row("Side:", f"[{side_style}]{side.upper()}[/]")
    grid.add_row("Amount:", f"${qty_usd:,.2f}")
    
    if price:
        grid.add_row("Price:", f"${price:,.2f}")
        
    for k, v in kwargs.items():
        if v is not None:
            grid.add_row(f"{k.replace('_', ' ').title()}:", str(v))
            
    panel = Panel(
        Align.center(grid),
        title=f"[bold {CLIColors.NEON_YELLOW}]Order Preview[/]",
        border_style=CLIColors.NEON_YELLOW,
        subtitle="[dim]Press Enter to execute, Ctrl+C to cancel[/]"
    )
    console.print(panel)

