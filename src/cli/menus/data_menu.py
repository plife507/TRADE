"""
Data builder menu for the CLI.

Handles all historical data operations:
- Database info and stats
- Data sync (OHLCV, funding, open interest)
- Data queries
- Maintenance operations

Data Environment Selection:
- LIVE: Canonical historical data for backtesting (api.bybit.com)
- DEMO: Demo-only history for demo validation (api-demo.bybit.com)
"""

from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.align import Align
from rich.text import Text

from src.config.config import get_config
from src.config.constants import DataEnv, DEFAULT_DATA_ENV
from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper
from src.tools import (
    # Database info tools
    get_database_stats_tool,
    list_cached_symbols_tool,
    get_symbol_status_tool,
    get_symbol_summary_tool,
    get_symbol_timeframe_ranges_tool,
    # Sync tools
    sync_symbols_tool,
    sync_range_tool,
    sync_to_now_tool,
    sync_to_now_and_fill_gaps_tool,
    build_symbol_history_tool,
    sync_funding_tool,
    sync_open_interest_tool,
    # Query tools
    get_ohlcv_history_tool,
    get_funding_history_tool,
    get_open_interest_history_tool,
    # Maintenance tools
    fill_gaps_tool,
    heal_data_tool,
    delete_symbol_tool,
    delete_all_data_tool,
    cleanup_empty_symbols_tool,
    vacuum_database_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def data_menu(cli: "TradeCLI"):
    """Historical data builder menu (DuckDB-only)."""
    # Import helpers from parent module to avoid circular imports
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        print_error_below_menu, run_tool_action, run_long_action,
        print_data_result, BACK
    )
    
    # Current data environment (LIVE or DEMO) - persists during menu session
    data_env: DataEnv = DEFAULT_DATA_ENV
    
    while True:
        clear_screen()
        print_header()
        
        # Show data environment status
        config = get_config()
        env_summary = config.bybit.get_api_environment_summary()
        
        # Get status for current selected data env
        if data_env == "live":
            env_info = env_summary["data_live"]
            env_color = CLIColors.NEON_GREEN
            env_label = "LIVE (Canonical Backtest Data)"
        else:
            env_info = env_summary["data_demo"]
            env_color = CLIColors.NEON_CYAN
            env_label = "DEMO (Demo Validation Data)"
        
        key_status = "✓ Key Configured" if env_info["key_configured"] else "✗ No Key"
        key_color = CLIColors.NEON_GREEN if env_info["key_configured"] else CLIColors.NEON_YELLOW
        
        api_status_line = Text()
        api_status_line.append("Data Env: ", style=CLIColors.DIM_TEXT)
        api_status_line.append(f"{data_env.upper()} ", style=f"bold {env_color}")
        api_status_line.append(f"({env_info['base_url']})", style=CLIColors.DIM_TEXT)
        api_status_line.append(" │ ", style=CLIColors.DIM_TEXT)
        api_status_line.append(key_status, style=key_color)
        api_status_line.append(" │ ", style=CLIColors.DIM_TEXT)
        api_status_line.append(env_label, style=f"italic {CLIColors.DIM_TEXT}")
        console.print(Panel(api_status_line, border_style=f"dim {env_color}"))
        
        menu = CLIStyles.create_menu_table()
        
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.DATABASE} Database Info ---[/]", "")
        menu.add_row("1", "Database Stats", "Database size, symbol count, total candles")
        menu.add_row("2", "List Cached Symbols", "All symbols with data in database")
        menu.add_row("3", "Symbol Aggregate Status", "Per-symbol totals (candles, gaps, timeframes)")
        menu.add_row("4", "Symbol Summary (Overview)", "High-level summary per symbol")
        menu.add_row("5", "Symbol Timeframe Ranges", "Detailed per-symbol/timeframe date ranges")
        menu.add_row("", "", "")
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.MINING} Build Data ---[/]", "")
        menu.add_row("6", f"[bold {CLIColors.NEON_GREEN}]Build Full History[/]", f"[{CLIColors.NEON_GREEN}]Sync OHLCV + Funding + OI for symbols[/]")
        menu.add_row("7", f"[bold {CLIColors.NEON_CYAN}]Sync Forward to Now[/]", f"[{CLIColors.NEON_CYAN}]Fetch only new candles (no backfill)[/]")
        menu.add_row("8", f"[bold {CLIColors.NEON_CYAN}]Sync Forward + Fill Gaps[/]", f"[{CLIColors.NEON_CYAN}]Sync new + backfill gaps in history[/]")
        menu.add_row("", "", "")
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.NETWORK} Sync Data (Individual) ---[/]", "")
        menu.add_row("9", "Sync OHLCV by Period", "Sync candles for a time period (1D, 1M, etc.)")
        menu.add_row("10", "Sync OHLCV by Date Range", "Sync candles for specific date range")
        menu.add_row("11", "Sync Funding Rates", "Sync funding rate history")
        menu.add_row("12", "Sync Open Interest", "Sync open interest history")
        menu.add_row("", "", "")
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.LEDGER} Query Data ---[/]", "")
        menu.add_row("13", f"[bold {CLIColors.NEON_MAGENTA}]Query OHLCV[/]", f"[{CLIColors.NEON_MAGENTA}]View cached candles (period or custom range)[/]")
        menu.add_row("14", f"[bold {CLIColors.NEON_MAGENTA}]Query Funding[/]", f"[{CLIColors.NEON_MAGENTA}]View cached funding rates[/]")
        menu.add_row("15", f"[bold {CLIColors.NEON_MAGENTA}]Query Open Interest[/]", f"[{CLIColors.NEON_MAGENTA}]View cached open interest[/]")
        menu.add_row("", "", "")
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.SETTINGS} Maintenance ---[/]", "")
        menu.add_row("16", "Fill Gaps", "Detect and fill missing candles in data")
        menu.add_row("17", "Heal Data", "Comprehensive data integrity check & repair")
        menu.add_row("18", f"[{CLIColors.NEON_RED}]{CLIIcons.ERROR} Delete Symbol[/]", f"[{CLIColors.NEON_RED}]Delete all data for a symbol[/]")
        menu.add_row("19", f"[bold {CLIColors.NEON_RED}]{CLIIcons.PANIC} Delete ALL Data[/]", f"[{CLIColors.NEON_RED}]Delete EVERYTHING (OHLCV, funding, OI)[/]")
        menu.add_row("20", "Cleanup Empty Symbols", "Remove symbols with no data")
        menu.add_row("21", "Vacuum Database", "Reclaim disk space after deletions")
        menu.add_row("", "", "")
        menu.add_row("22", f"[bold {CLIColors.NEON_YELLOW}]{CLIIcons.TARGET} Run Extensive Data Test[/]", f"[{CLIColors.NEON_YELLOW}]Full smoke test of all data tools[/]")
        menu.add_row("", "", "")
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.EXCHANGE} Environment ---[/]", "")
        toggle_label = f"[bold {CLIColors.NEON_CYAN}]Switch to DEMO[/]" if data_env == "live" else f"[bold {CLIColors.NEON_GREEN}]Switch to LIVE[/]"
        toggle_desc = f"[{CLIColors.NEON_CYAN}]Use demo API for data[/]" if data_env == "live" else f"[{CLIColors.NEON_GREEN}]Use live API for data[/]"
        menu.add_row("23", toggle_label, toggle_desc)
        menu.add_row("", "", "")
        menu.add_row("24", f"{CLIIcons.BACK} Back to Main Menu", "Return to main menu")
        
        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, f"DATA BUILDER ({data_env.upper()})"))
        BillArtWrapper.print_menu_bottom()
        
        choice = get_choice(valid_range=range(1, 25))
        if choice is BACK:
            break  # Go back to main menu

        if choice == 1:
            # Database Stats
            result = run_tool_action("data.stats", get_database_stats_tool, env=data_env)
            print_data_result("data.stats", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 2:
            # List Cached Symbols
            result = run_tool_action("data.list_symbols", list_cached_symbols_tool, env=data_env)
            print_data_result("data.list_symbols", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 3:
            # Symbol Aggregate Status
            symbol = get_input("Symbol (blank for all)", "")
            result = run_tool_action("data.symbol_status", get_symbol_status_tool, symbol if symbol else None, env=data_env)
            print_data_result("data.symbol_status", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 4:
            # Symbol Summary (Overview)
            result = run_tool_action("data.symbol_summary", get_symbol_summary_tool, env=data_env)
            print_data_result("data.symbol_summary", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 5:
            # Symbol Timeframe Ranges (Detailed)
            symbol = get_input("Symbol (blank for all)", "")
            result = run_tool_action("data.timeframe_ranges", get_symbol_timeframe_ranges_tool, symbol if symbol else None, env=data_env)
            print_data_result("data.timeframe_ranges", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 6:
            # Build Full History (OHLCV + Funding + OI)
            symbol = get_input("Symbol(s) to build (comma-separated)")
            symbols = [s.strip().upper() for s in symbol.split(",") if s.strip()]
            if not symbols:
                print_error_below_menu("No symbols provided.")
                Prompt.ask("\nPress Enter to continue")
                continue
            
            period = get_input("Period (1D, 1W, 1M, 3M, 6M, 1Y)", "1M")
            timeframes_input = get_input("OHLCV Timeframes (comma-separated, blank for all)", "")
            timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None
            oi_interval = get_input("Open Interest Interval (5min, 15min, 30min, 1h, 4h, 1d)", "1h")
            
            result = run_long_action(
                "data.build_full_history", build_symbol_history_tool,
                symbols, period=period, timeframes=timeframes, oi_interval=oi_interval, env=data_env
            )
            print_data_result("data.build_full_history", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 7:
            # Sync Forward to Now (new candles only)
            symbol = get_input("Symbol(s) to sync forward (comma-separated)")
            symbols = [s.strip().upper() for s in symbol.split(",") if s.strip()]
            if not symbols:
                print_error_below_menu("No symbols provided.")
                Prompt.ask("\nPress Enter to continue")
                continue
            
            timeframes_input = get_input("Timeframes (comma-separated, blank for all)", "")
            timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None
            
            result = run_long_action(
                "data.sync_to_now", sync_to_now_tool,
                symbols, timeframes=timeframes, env=data_env
            )
            print_data_result("data.sync_to_now", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 8:
            # Sync Forward + Fill Gaps (complete)
            symbol = get_input("Symbol(s) to sync and heal (comma-separated)")
            symbols = [s.strip().upper() for s in symbol.split(",") if s.strip()]
            if not symbols:
                print_error_below_menu("No symbols provided.")
                Prompt.ask("\nPress Enter to continue")
                continue
            
            timeframes_input = get_input("Timeframes (comma-separated, blank for all)", "")
            timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None
            
            result = run_long_action(
                "data.sync_to_now_fill_gaps", sync_to_now_and_fill_gaps_tool,
                symbols, timeframes=timeframes, env=data_env
            )
            print_data_result("data.sync_to_now_fill_gaps", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 9:
            # Sync OHLCV by Period
            symbol = get_input("Symbol (comma-separated for multiple)")
            symbols = [s.strip().upper() for s in symbol.split(",")]
            period = get_input("Period (1D, 1W, 1M, 3M, 6M, 1Y)", "1M")
            timeframes_input = get_input("Timeframes (comma-separated, blank for all)", "")
            timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None
            
            result = run_long_action(
                "data.sync_ohlcv_period", sync_symbols_tool,
                symbols, period=period, timeframes=timeframes, env=data_env
            )
            print_data_result("data.sync_ohlcv_period", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 10:
            # Sync OHLCV by Date Range
            symbol = get_input("Symbol (comma-separated for multiple)")
            symbols = [s.strip().upper() for s in symbol.split(",")]
            start_str = get_input("Start Date (YYYY-MM-DD)")
            end_str = get_input("End Date (YYYY-MM-DD)", datetime.now().strftime("%Y-%m-%d"))
            timeframes_input = get_input("Timeframes (comma-separated, blank for all)", "")
            timeframes = [t.strip() for t in timeframes_input.split(",")] if timeframes_input else None
            
            try:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d")
                end_dt = datetime.strptime(end_str, "%Y-%m-%d")
            except ValueError:
                print_error_below_menu("Invalid date format. Use YYYY-MM-DD.")
                Prompt.ask("\nPress Enter to continue")
                continue
            
            result = run_long_action(
                "data.sync_ohlcv_range", sync_range_tool,
                symbols, start=start_dt, end=end_dt, timeframes=timeframes, env=data_env
            )
            print_data_result("data.sync_ohlcv_range", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 11:
            # Sync Funding Rates
            symbol = get_input("Symbol (comma-separated for multiple)")
            symbols = [s.strip().upper() for s in symbol.split(",")]
            period = get_input("Period (1M, 3M, 6M, 1Y)", "3M")
            
            result = run_long_action(
                "data.sync_funding", sync_funding_tool,
                symbols, period=period, env=data_env
            )
            print_data_result("data.sync_funding", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 12:
            # Sync Open Interest
            symbol = get_input("Symbol (comma-separated for multiple)")
            symbols = [s.strip().upper() for s in symbol.split(",")]
            period = get_input("Period (1D, 1W, 1M, 3M)", "1M")
            interval = get_input("Interval (5min, 15min, 30min, 1h, 4h, 1d)", "1h")
            
            result = run_long_action(
                "data.sync_open_interest", sync_open_interest_tool,
                symbols, period=period, interval=interval, env=data_env
            )
            print_data_result("data.sync_open_interest", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 13:
            # Query OHLCV History
            symbol = get_input("Symbol")
            if symbol is BACK or not symbol:
                if not symbol:
                    print_error_below_menu("Symbol is required")
                Prompt.ask("\nPress Enter to continue")
                continue
            
            timeframe = get_input("Timeframe (1m, 5m, 15m, 1h, 4h, 1d)", "1h")
            if timeframe is BACK:
                continue
            
            console.print("\n[bold cyan]Select data range:[/]")
            console.print("  1) Use period (e.g., 1M = last month)")
            console.print("  2) Custom date range")
            range_choice = get_input("Choice", "1")
            
            if range_choice == "2":
                start_str = get_input("Start date (YYYY-MM-DD)")
                if start_str is BACK:
                    continue
                end_str = get_input("End date (YYYY-MM-DD, blank for now)", "")
                if end_str is BACK:
                    continue
                
                result = run_tool_action(
                    "data.query_ohlcv", get_ohlcv_history_tool,
                    symbol=symbol.upper(), timeframe=timeframe,
                    start=start_str, end=end_str if end_str else None, env=data_env
                )
            else:
                period = get_input("Period (1D, 1W, 1M, 3M, 6M)", "1M")
                if period is BACK:
                    continue
                result = run_tool_action(
                    "data.query_ohlcv", get_ohlcv_history_tool,
                    symbol=symbol.upper(), timeframe=timeframe, period=period, env=data_env
                )
            
            # Show summary for large results
            if result.success and result.data:
                count = result.data.get("count", 0)
                if count > 20:
                    console.print(f"\n[dim]Showing summary ({count:,} candles total)[/]")
                    tr = result.data.get("time_range", {})
                    console.print(f"[dim]Range: {tr.get('first_candle', 'N/A')} to {tr.get('last_candle', 'N/A')}[/]")
                    console.print(f"\n[green]✓ {result.message}[/]")
                else:
                    print_data_result("data.query_ohlcv", result)
            else:
                print_data_result("data.query_ohlcv", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 14:
            # Query Funding History
            symbol = get_input("Symbol")
            if symbol is BACK or not symbol:
                if not symbol:
                    print_error_below_menu("Symbol is required")
                Prompt.ask("\nPress Enter to continue")
                continue
            
            console.print("\n[bold cyan]Select data range:[/]")
            console.print("  1) Use period (e.g., 1M = last month)")
            console.print("  2) Custom date range")
            range_choice = get_input("Choice", "1")
            
            if range_choice == "2":
                start_str = get_input("Start date (YYYY-MM-DD)")
                if start_str is BACK:
                    continue
                end_str = get_input("End date (YYYY-MM-DD, blank for now)", "")
                if end_str is BACK:
                    continue
                
                result = run_tool_action(
                    "data.query_funding", get_funding_history_tool,
                    symbol=symbol.upper(),
                    start=start_str, end=end_str if end_str else None, env=data_env
                )
            else:
                period = get_input("Period (1M, 3M, 6M, 1Y)", "1M")
                if period is BACK:
                    continue
                result = run_tool_action(
                    "data.query_funding", get_funding_history_tool,
                    symbol=symbol.upper(), period=period, env=data_env
                )
            
            # Show summary for large results
            if result.success and result.data:
                count = result.data.get("count", 0)
                if count > 20:
                    console.print(f"\n[dim]Showing summary ({count:,} records total)[/]")
                    tr = result.data.get("time_range", {})
                    console.print(f"[dim]Range: {tr.get('first_record', 'N/A')} to {tr.get('last_record', 'N/A')}[/]")
                    console.print(f"\n[green]✓ {result.message}[/]")
                else:
                    print_data_result("data.query_funding", result)
            else:
                print_data_result("data.query_funding", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 15:
            # Query Open Interest History
            symbol = get_input("Symbol")
            if symbol is BACK or not symbol:
                if not symbol:
                    print_error_below_menu("Symbol is required")
                Prompt.ask("\nPress Enter to continue")
                continue
            
            console.print("\n[bold cyan]Select data range:[/]")
            console.print("  1) Use period (e.g., 1M = last month)")
            console.print("  2) Custom date range")
            range_choice = get_input("Choice", "1")
            
            if range_choice == "2":
                start_str = get_input("Start date (YYYY-MM-DD)")
                if start_str is BACK:
                    continue
                end_str = get_input("End date (YYYY-MM-DD, blank for now)", "")
                if end_str is BACK:
                    continue
                
                result = run_tool_action(
                    "data.query_oi", get_open_interest_history_tool,
                    symbol=symbol.upper(),
                    start=start_str, end=end_str if end_str else None, env=data_env
                )
            else:
                period = get_input("Period (1M, 3M, 6M, 1Y)", "1M")
                if period is BACK:
                    continue
                result = run_tool_action(
                    "data.query_oi", get_open_interest_history_tool,
                    symbol=symbol.upper(), period=period, env=data_env
                )
            
            # Show summary for large results
            if result.success and result.data:
                count = result.data.get("count", 0)
                if count > 20:
                    console.print(f"\n[dim]Showing summary ({count:,} records total)[/]")
                    tr = result.data.get("time_range", {})
                    console.print(f"[dim]Range: {tr.get('first_record', 'N/A')} to {tr.get('last_record', 'N/A')}[/]")
                    console.print(f"\n[green]✓ {result.message}[/]")
                else:
                    print_data_result("data.query_oi", result)
            else:
                print_data_result("data.query_oi", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 16:
            # Fill Gaps
            symbol = get_input("Symbol (blank for all)", "")
            timeframe = get_input("Timeframe (blank for all)", "")
            
            result = run_tool_action(
                "data.fill_gaps", fill_gaps_tool,
                symbol=symbol if symbol else None,
                timeframe=timeframe if timeframe else None,
                env=data_env
            )
            print_data_result("data.fill_gaps", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 17:
            # Heal Data
            symbol = get_input("Symbol (blank for all)", "")
            
            result = run_tool_action(
                "data.heal", heal_data_tool,
                symbol=symbol if symbol else None,
                env=data_env
            )
            print_data_result("data.heal", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 18:
            # Delete Symbol
            symbol = get_input("Symbol to DELETE")
            if symbol:
                env_label = data_env.upper()
                if Confirm.ask(f"[bold red]Delete ALL data for {symbol.upper()} in {env_label} env?[/]"):
                    result = run_tool_action("data.delete_symbol", delete_symbol_tool, symbol, env=data_env)
                    print_data_result("data.delete_symbol", result)
                else:
                    console.print("[yellow]Cancelled.[/]")
            else:
                console.print("[yellow]No symbol provided.[/]")
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 19:
            # Delete ALL Data
            env_label = data_env.upper()
            console.print(f"\n[bold red]⚠️  WARNING: This will delete ALL historical data in {env_label} env![/]")
            console.print("[red]This includes: OHLCV candles, funding rates, and open interest data.[/]")
            console.print("[red]This action CANNOT be undone.[/]")
            if Confirm.ask(f"\n[bold red]Are you ABSOLUTELY sure you want to delete ALL {env_label} data?[/]"):
                if Confirm.ask("[bold red]Type YES to confirm deletion[/]", default=False):
                    result = run_tool_action("data.delete_all", delete_all_data_tool, env=data_env)
                    print_data_result("data.delete_all", result)
                else:
                    console.print("[yellow]Cancelled.[/]")
            else:
                console.print("[yellow]Cancelled.[/]")
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 20:
            # Cleanup Empty Symbols
            result = run_tool_action("data.cleanup_empty", cleanup_empty_symbols_tool, env=data_env)
            print_data_result("data.cleanup_empty", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 21:
            # Vacuum Database
            result = run_tool_action("data.vacuum", vacuum_database_tool, env=data_env)
            print_data_result("data.vacuum", result)
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 22:
            # Run Extensive Data Test
            from src.cli.smoke_tests import run_extensive_data_smoke
            console.print(f"\n[bold yellow]Running Extensive Data Smoke Test ({data_env.upper()} env)...[/]")
            console.print("[dim]This will test all data tools with real API calls.[/]")
            if Confirm.ask("\nProceed with extensive data test?"):
                run_extensive_data_smoke(env=data_env)
            else:
                console.print("[yellow]Cancelled.[/]")
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 23:
            # Toggle Data Environment
            if data_env == "live":
                data_env = "demo"
                console.print("\n[bold cyan]Switched to DEMO data environment[/]")
                console.print("[dim]Now using api-demo.bybit.com for data operations[/]")
            else:
                data_env = "live"
                console.print("\n[bold green]Switched to LIVE data environment[/]")
                console.print("[dim]Now using api.bybit.com for data operations[/]")
            Prompt.ask("\nPress Enter to continue")
        
        elif choice == 24:
            break

