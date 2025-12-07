"""
CLI modules for TRADE trading bot.

This package contains:
- utils: CLI input/output utilities (input, display, time ranges)
- smoke_tests: Non-interactive smoke test functions
- menus/: Individual menu handler modules
"""

from .utils import (
    console,
    BackCommand,
    BACK,
    is_exit_command,
    clear_screen,
    print_header,
    get_input,
    get_choice,
    TimeRangeSelection,
    select_time_range_cli,
    get_time_window,
    print_error_below_menu,
    run_tool_action,
    run_long_action,
    print_result,
    print_data_result,
    print_order_preview,
)

__all__ = [
    "console",
    "BackCommand",
    "BACK",
    "is_exit_command",
    "clear_screen",
    "print_header",
    "get_input",
    "get_choice",
    "TimeRangeSelection",
    "select_time_range_cli",
    "get_time_window",
    "print_error_below_menu",
    "run_tool_action",
    "run_long_action",
    "print_result",
    "print_data_result",
    "print_order_preview",
]

