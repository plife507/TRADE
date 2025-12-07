"""
CLI utility functions for TRADE trading bot.

Contains:
- Input handling (get_input, get_choice, is_exit_command)
- Display utilities (print_header, print_result, print_error_below_menu)
- Time range selection (select_time_range_cli, TimeRangeSelection)
- Action execution wrappers (run_tool_action, run_long_action)
"""

import os
from typing import Optional
from datetime import datetime

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
    
    is_demo = config.bybit.use_demo
    mode_str = "DEMO" if is_demo else "LIVE"
    mode_style = "bold green" if is_demo else "bold red"
    
    trading_mode = config.trading.mode
    trade_style = "bold yellow" if trading_mode == "paper" else "bold red"
    
    account_type = "UNIFIED"
    
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
    
    warning_panel = None
    if not is_demo:
        warning_panel = Panel(
            "[bold red]⚠  CAUTION: Connected to LIVE account - REAL MONEY ⚠[/]",
            border_style="red",
            expand=False
        )

    title = Text("TRADE - Bybit Unified Trading Account", style="bold cyan")
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
    """Get user input with optional default. Returns BACK sentinel if exit command detected."""
    hint = "[dim](or 'back'/'b' to cancel)[/]"
    try:
        user_input = Prompt.ask(f"[cyan]{prompt}[/] {hint}", default=default if default else None, show_default=bool(default))
        
        if is_exit_command(user_input):
            return BACK
        return user_input
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Cancelled.[/]")
        return BACK


def get_choice(valid_range: range = None) -> int:
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


class TimeRangeSelection:
    """Result from time range selection - can be a preset window or custom start/end."""
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
        return self.start_ms is not None and self.end_ms is not None
    
    @property
    def is_preset(self) -> bool:
        return self.window is not None and not self.is_custom


def _parse_datetime_input(value: str) -> Optional[datetime]:
    """Parse a datetime string in various common formats."""
    value = value.strip()
    if not value:
        return None
    
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
    
    window_map = {"1": "24h", "2": "7d", "3": "30d" if max_days >= 30 else "7d"}
    
    if include_custom and choice_input == str(custom_option):
        return _prompt_custom_date_range(max_days, endpoint_name)
    
    window = window_map.get(choice_input, default)
    return TimeRangeSelection(window=window)


def _prompt_custom_date_range(max_days: int, endpoint_name: str) -> TimeRangeSelection:
    """Prompt user for custom start and end dates."""
    console.print("\n[bold cyan]Custom Date Range[/]")
    console.print(f"[dim]Format: YYYY-MM-DD or YYYY-MM-DD HH:MM (UTC)[/]")
    console.print(f"[dim]Maximum range: {max_days} days[/]")
    
    start_input = get_input("Start date (e.g., 2024-01-01)")
    if start_input is BACK:
        return TimeRangeSelection(is_back=True)
    
    start_dt = _parse_datetime_input(start_input)
    if start_dt is None:
        print_error_below_menu(f"Invalid start date format: '{start_input}'", "Use YYYY-MM-DD or YYYY-MM-DD HH:MM format")
        return TimeRangeSelection(is_back=True)
    
    default_end = datetime.now().strftime("%Y-%m-%d %H:%M")
    end_input = get_input(f"End date (default: now)", default_end)
    if end_input is BACK:
        return TimeRangeSelection(is_back=True)
    
    end_dt = _parse_datetime_input(end_input)
    if end_dt is None:
        print_error_below_menu(f"Invalid end date format: '{end_input}'", "Use YYYY-MM-DD or YYYY-MM-DD HH:MM format")
        return TimeRangeSelection(is_back=True)
    
    if start_dt >= end_dt:
        print_error_below_menu("Start date must be before end date", f"Start: {start_dt}, End: {end_dt}")
        return TimeRangeSelection(is_back=True)
    
    duration = end_dt - start_dt
    if duration.days > max_days:
        print_error_below_menu(f"Date range too large for {endpoint_name}", f"Requested {duration.days} days, maximum is {max_days} days")
        return TimeRangeSelection(is_back=True)
    
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    
    console.print(f"\n[green]✓ Using custom range: {start_dt.strftime('%Y-%m-%d %H:%M')} to {end_dt.strftime('%Y-%m-%d %H:%M')} ({duration.days}d {duration.seconds // 3600}h)[/]")
    
    return TimeRangeSelection(start_ms=start_ms, end_ms=end_ms)


def get_time_window(max_days: int = 7, default: str = "24h", include_custom: bool = True) -> str:
    """DEPRECATED: Use select_time_range_cli() for full custom date support."""
    selection = select_time_range_cli(max_days=max_days, default=default, include_custom=False)
    
    if selection.is_back:
        return BACK
    
    return selection.window or default


def print_error_below_menu(error_message: str, error_details: str = None):
    """Print error message below the static menu with proper formatting."""
    console.print()
    console.print("[dim]" + "─" * 80 + "[/dim]")
    
    error_text = f"[bold red]✗ Error:[/] {error_message}"
    if error_details:
        error_text += f"\n[dim]{error_details}[/dim]"
    
    console.print(Panel(error_text, border_style="red", title="[bold red]ERROR[/]", padding=(1, 2)))
    console.print()


def run_tool_action(action_key: str, tool_fn, *args, **kwargs) -> ToolResult:
    """Execute a tool with an emoji-enhanced status display."""
    status_msg = format_action_status(action_key, **kwargs)
    
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
    """Execute a long-running tool with status display and Ctrl+C handling."""
    from ..core.application import get_application
    
    status_msg = format_action_status(action_key, **kwargs)
    
    display_only_keys = {"for_symbol"}
    tool_kwargs = {k: v for k, v in kwargs.items() if k not in display_only_keys}
    
    app = get_application()
    app.suppress_shutdown()
    
    try:
        console.print(f"\n[bold cyan]{status_msg}[/]")
        console.print("[dim]Press Ctrl+C to cancel gracefully[/]\n")
        
        with console.status(f"[bold green]▶ {get_action_label(action_key)} in progress...[/]", spinner="dots"):
            result = tool_fn(*args, **tool_kwargs)
        
        complete_msg = format_action_complete(action_key, **kwargs)
        console.print(f"[green]✓ {complete_msg}[/]")
        
        return result
        
    except KeyboardInterrupt:
        console.print(f"\n[yellow]⚠️  Operation cancelled by user[/]")
        if cancel_store:
            try:
                from ..data.historical_data_store import get_historical_store
                store = get_historical_store()
                store.cancel()
            except Exception:
                pass
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
                if result.data and isinstance(result.data[0], dict):
                    table = Table(show_header=True, header_style="bold magenta")
                    keys = result.data[0].keys()
                    for key in keys:
                        table.add_column(str(key))
                    
                    for item in result.data[:20]:
                        row_vals = [str(item.get(k, "")) for k in keys]
                        table.add_row(*row_vals)
                    
                    console.print(table)
                    if len(result.data) > 20:
                        console.print(f"[dim]... and {len(result.data) - 20} more items[/]")
                else:
                    for item in result.data:
                        console.print(f"  • {item}")
            
            elif isinstance(result.data, dict):
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
        print_error_below_menu(result.error)


def print_data_result(action_key: str, result: ToolResult):
    """Print a data builder ToolResult with specialized formatting."""
    if not result.success:
        print_error_below_menu(result.error)
        return
    
    formatted = format_data_result(action_key, result.data, result.message)
    
    if formatted is None:
        print_result(result)
        return
    
    console.print(Panel(f"[bold green]✓ {result.message}[/]", border_style="green"))
    
    format_type = formatted.get("type", "simple")
    title = formatted.get("title", "Result")
    footer = formatted.get("footer")
    
    if format_type == "table":
        columns = formatted.get("columns", [])
        rows = formatted.get("rows", [])
        
        if rows:
            table = Table(show_header=True, header_style="bold magenta", title=title, 
                         title_style="bold cyan", border_style="blue")
            
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
            
            for row in rows:
                values = [str(row.get(col, "")) for col in columns]
                colored_values = []
                for val in values:
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

