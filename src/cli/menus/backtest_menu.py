"""
Backtest menu for the CLI.

Handles all backtesting operations:
- List and view system configurations
- Run backtests
- Prepare and verify data
- View strategies

All operations call tools - no direct engine access from CLI.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.align import Align
from rich.text import Text

from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper
from src.tools import (
    backtest_list_systems_tool,
    backtest_get_system_tool,
    backtest_run_tool,
    backtest_prepare_data_tool,
    backtest_verify_data_tool,
    backtest_list_strategies_tool,
)

if TYPE_CHECKING:
    from trade_cli import TradeCLI

# Local console
console = Console()


def backtest_menu(cli: "TradeCLI"):
    """Backtest menu for running strategy backtests."""
    # Import helpers from parent module to avoid circular imports
    from trade_cli import (
        clear_screen, print_header, get_input, get_choice,
        print_error_below_menu, run_tool_action, run_long_action,
        print_data_result, BACK
    )
    
    while True:
        clear_screen()
        print_header()
        
        # Show backtest info header
        status_line = Text()
        status_line.append("Backtest Engine ", style=f"bold {CLIColors.NEON_MAGENTA}")
        status_line.append("│ ", style=CLIColors.DIM_TEXT)
        status_line.append("Config-driven strategy backtesting", style=CLIColors.DIM_TEXT)
        console.print(Panel(status_line, border_style=f"dim {CLIColors.NEON_MAGENTA}"))
        
        menu = CLIStyles.create_menu_table()
        
        # Systems section
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.LEDGER} System Configs ---[/]", "")
        menu.add_row("1", "List Systems", "View all available system configurations")
        menu.add_row("2", "View System Details", "Get detailed info about a system")
        menu.add_row("", "", "")
        
        # Run section
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.TRADE} Run Backtest ---[/]", "")
        menu.add_row("3", f"[bold {CLIColors.NEON_GREEN}]Run Backtest[/]", f"[{CLIColors.NEON_GREEN}]Execute backtest for a system[/]")
        menu.add_row("4", f"[bold {CLIColors.NEON_CYAN}]Run Both Windows[/]", f"[{CLIColors.NEON_CYAN}]Run hygiene then test window[/]")
        menu.add_row("", "", "")
        
        # Data section
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.DATABASE} Data Preparation ---[/]", "")
        menu.add_row("5", "Prepare Data", "Sync data for a system config")
        menu.add_row("6", "Verify Data", "Check data quality for backtest")
        menu.add_row("7", f"[{CLIColors.NEON_YELLOW}]Fresh DB + Prepare[/]", f"[{CLIColors.NEON_YELLOW}]Wipe DB and rebuild data[/]")
        menu.add_row("", "", "")
        
        # Strategies section
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.BOT} Strategies ---[/]", "")
        menu.add_row("8", "List Strategies", "View available strategy implementations")
        menu.add_row("", "", "")
        
        # Navigation
        menu.add_row("9", f"{CLIIcons.BACK} Back to Main Menu", "Return to main menu")
        
        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, "BACKTEST ENGINE"))
        BillArtWrapper.print_menu_bottom()
        
        choice = get_choice(valid_range=range(1, 10))
        if choice is None:
            continue
        
        # Handle menu choices
        if choice == 1:
            # List systems
            _list_systems(cli)
        
        elif choice == 2:
            # View system details
            _view_system_details(cli)
        
        elif choice == 3:
            # Run backtest
            _run_backtest(cli)
        
        elif choice == 4:
            # Run both windows
            _run_both_windows(cli)
        
        elif choice == 5:
            # Prepare data
            _prepare_data(cli, fresh_db=False)
        
        elif choice == 6:
            # Verify data
            _verify_data(cli)
        
        elif choice == 7:
            # Fresh DB + Prepare
            _prepare_data(cli, fresh_db=True)
        
        elif choice == 8:
            # List strategies
            _list_strategies(cli)
        
        elif choice == 9:
            # Back to main menu
            return


def _select_system(prompt_text: str = "Select system") -> str:
    """
    Show numbered list of systems and let user select by number.
    
    Returns:
        Selected system_id or None if cancelled
    """
    result = backtest_list_systems_tool()
    
    if not result.success or not result.data:
        console.print(f"[{CLIColors.NEON_RED}]Error loading systems: {result.error}[/]")
        return None
    
    systems = result.data.get("systems", [])
    valid_systems = [s for s in systems if "error" not in s]
    
    if not valid_systems:
        console.print(f"[{CLIColors.NEON_YELLOW}]No systems found.[/]")
        console.print(f"[{CLIColors.DIM_TEXT}]Add YAML configs to: {result.data.get('configs_dir')}[/]")
        return None
    
    # Show numbered table
    console.print(f"\n[bold {CLIColors.NEON_CYAN}]{prompt_text}:[/]")
    console.print(f"[{CLIColors.DIM_TEXT}]A system config = symbol + tf + strategy instances + risk settings[/]\n")
    
    table = Table(border_style=CLIColors.NEON_CYAN, show_header=True)
    table.add_column("#", style="bold", width=3)
    table.add_column("System", style=CLIColors.NEON_GREEN)
    table.add_column("Symbol", style=CLIColors.NEON_YELLOW)
    table.add_column("TF")
    table.add_column("Strategy", style=CLIColors.NEON_MAGENTA)
    table.add_column("Ver")
    table.add_column("Risk")
    
    for i, sys in enumerate(valid_systems, 1):
        table.add_row(
            str(i),
            sys["system_id"],
            sys.get("symbol", ""),
            sys.get("tf", ""),
            sys.get("strategy_id", ""),
            sys.get("strategy_version", "1"),
            sys.get("risk_mode", ""),
        )
    
    console.print(table)
    
    # Get selection
    while True:
        choice = Prompt.ask(f"\n[{CLIColors.NEON_CYAN}]Enter number (1-{len(valid_systems)})[/] [dim]or 'back'[/]")
        
        if choice.lower() in ('back', 'b', ''):
            return None
        
        try:
            num = int(choice)
            if 1 <= num <= len(valid_systems):
                return valid_systems[num - 1]["system_id"]
            else:
                console.print(f"[{CLIColors.NEON_YELLOW}]Please enter 1-{len(valid_systems)}[/]")
        except ValueError:
            console.print(f"[{CLIColors.NEON_YELLOW}]Please enter a number[/]")


def _list_systems(cli: "TradeCLI"):
    """List all available system configurations."""
    console.print(f"\n[{CLIColors.NEON_CYAN}]Listing system configurations...[/]")
    
    result = backtest_list_systems_tool()
    
    if result.success and result.data:
        systems = result.data.get("systems", [])
        
        if not systems:
            console.print(f"[{CLIColors.NEON_YELLOW}]No systems found.[/]")
            console.print(f"[{CLIColors.DIM_TEXT}]Add YAML configs to: {result.data.get('configs_dir')}[/]")
        else:
            table = Table(title="Available System Configurations", border_style=CLIColors.NEON_CYAN)
            table.add_column("#", style="bold", width=3)
            table.add_column("System ID", style=CLIColors.NEON_GREEN)
            table.add_column("UID", style=CLIColors.DIM_TEXT, width=10)
            table.add_column("Symbol", style=CLIColors.NEON_YELLOW)
            table.add_column("TF")
            table.add_column("Strategy", style=CLIColors.NEON_MAGENTA)
            table.add_column("Ver")
            table.add_column("Risk Mode")
            table.add_column("Windows")
            
            for i, sys in enumerate(systems, 1):
                if "error" in sys:
                    table.add_row(
                        str(i),
                        sys["system_id"],
                        "",
                        f"[{CLIColors.NEON_RED}]Error[/]",
                        "", "", "", "", ""
                    )
                else:
                    # Show first 8 chars of system_uid
                    uid_short = sys.get("system_uid", "")[:8] if sys.get("system_uid") else ""
                    table.add_row(
                        str(i),
                        sys["system_id"],
                        uid_short,
                        sys.get("symbol", ""),
                        sys.get("tf", ""),
                        sys.get("strategy_id", ""),
                        sys.get("strategy_version", "1"),
                        sys.get("risk_mode", ""),
                        ", ".join(sys.get("windows", [])),
                    )
            
            console.print(table)
            console.print(f"\n[{CLIColors.DIM_TEXT}]UID = deterministic hash of config (for artifact lineage)[/]")
    else:
        console.print(f"[{CLIColors.NEON_RED}]Error: {result.error or result.message}[/]")
    
    Prompt.ask("\nPress Enter to continue")


def _view_system_details(cli: "TradeCLI"):
    """View detailed info about a system."""
    system_id = _select_system("Select system to view")
    if not system_id:
        return
    
    result = backtest_get_system_tool(system_id)
    
    if result.success and result.data:
        data = result.data
        
        console.print(f"\n[bold {CLIColors.NEON_GREEN}]System: {data['system_id']}[/]\n")
        
        # Identity section
        console.print(f"[{CLIColors.NEON_YELLOW}]Identity:[/]")
        console.print(f"  System UID: [{CLIColors.DIM_TEXT}]{data.get('system_uid', 'N/A')}[/]")
        console.print(f"  Strategy: [{CLIColors.NEON_MAGENTA}]{data['strategy_id']}[/] v{data.get('strategy_version', '1')}")
        
        # Trading params
        console.print(f"\n[{CLIColors.NEON_YELLOW}]Trading:[/]")
        console.print(f"  Symbol: {data['symbol']}")
        console.print(f"  TF: {data['tf']}")
        console.print(f"  Risk Mode: {data['risk_mode']}")
        
        # Windows
        console.print(f"\n[{CLIColors.NEON_YELLOW}]Windows:[/]")
        for name, window in data.get("windows", {}).items():
            console.print(f"  {name}: {window.get('start')} → {window.get('end')}")
        
        # Risk profile
        console.print(f"\n[{CLIColors.NEON_YELLOW}]Risk Profile:[/]")
        rp = data.get("risk_profile", {})
        console.print(f"  Initial Capital: ${rp.get('initial_capital', 0):,.0f}")
        console.print(f"  Risk per Trade: {rp.get('risk_per_trade_percent', 0)}%")
        console.print(f"  Max Position: ${rp.get('max_position_size_usd', 0):,.0f}")
        
        # Data build
        console.print(f"\n[{CLIColors.NEON_YELLOW}]Data Build:[/]")
        db = data.get("data_build", {})
        console.print(f"  Period: {db.get('period')}")
        console.print(f"  TFs: {', '.join(db.get('tfs', []))}")
    else:
        console.print(f"[{CLIColors.NEON_RED}]Error: {result.error or result.message}[/]")
    
    Prompt.ask("\nPress Enter to continue")


def _select_window() -> str:
    """Select window (hygiene or test) with numbered options."""
    console.print(f"\n[{CLIColors.NEON_CYAN}]Select window:[/]")
    console.print(f"  [bold]1[/] hygiene - Development/tuning period")
    console.print(f"  [bold]2[/] test    - Validation period")
    
    while True:
        choice = Prompt.ask(f"\n[{CLIColors.NEON_CYAN}]Enter 1 or 2[/] [dim]or 'back'[/]", default="1")
        
        if choice.lower() in ('back', 'b'):
            return None
        
        if choice == "1" or choice.lower() == "hygiene":
            return "hygiene"
        elif choice == "2" or choice.lower() == "test":
            return "test"
        else:
            console.print(f"[{CLIColors.NEON_YELLOW}]Please enter 1 (hygiene) or 2 (test)[/]")


def _get_risk_overrides(system_id: str) -> dict:
    """
    Show risk profile defaults and prompt for optional overrides.
    
    Returns:
        Dict with any overrides (empty if user keeps defaults)
    """
    # Load system to get defaults
    result = backtest_get_system_tool(system_id)
    if not result.success or not result.data:
        return {}
    
    risk_profile = result.data.get("risk_profile", {})
    default_equity = risk_profile.get("initial_equity", 1000.0)
    default_risk_pct = risk_profile.get("risk_per_trade_pct", 1.0)
    default_leverage = risk_profile.get("max_leverage", 2.0)
    
    # Show current defaults
    console.print(f"\n[{CLIColors.NEON_YELLOW}]Default risk profile (from config):[/]")
    console.print(f"  initial_equity={default_equity}, risk_per_trade={default_risk_pct}%, max_leverage={default_leverage}")
    console.print(f"[{CLIColors.DIM_TEXT}]Press Enter to keep defaults, or enter new values:[/]\n")
    
    overrides = {}
    
    # Initial equity
    equity_input = Prompt.ask(
        f"  Initial equity [{CLIColors.DIM_TEXT}]default {default_equity}[/]",
        default=""
    )
    if equity_input.strip():
        try:
            overrides["initial_equity"] = float(equity_input)
        except ValueError:
            console.print(f"[{CLIColors.NEON_YELLOW}]Invalid value, keeping default[/]")
    
    # Risk per trade %
    risk_input = Prompt.ask(
        f"  Risk per trade % [{CLIColors.DIM_TEXT}]default {default_risk_pct}[/]",
        default=""
    )
    if risk_input.strip():
        try:
            overrides["risk_per_trade_pct"] = float(risk_input)
        except ValueError:
            console.print(f"[{CLIColors.NEON_YELLOW}]Invalid value, keeping default[/]")
    
    # Max leverage
    lev_input = Prompt.ask(
        f"  Max leverage [{CLIColors.DIM_TEXT}]default {default_leverage}[/]",
        default=""
    )
    if lev_input.strip():
        try:
            overrides["max_leverage"] = float(lev_input)
        except ValueError:
            console.print(f"[{CLIColors.NEON_YELLOW}]Invalid value, keeping default[/]")
    
    # Show what we're using
    if overrides:
        console.print(f"\n[{CLIColors.NEON_GREEN}]Using overridden risk profile:[/]")
        console.print(f"  initial_equity={overrides.get('initial_equity', default_equity)}, "
                     f"risk_per_trade={overrides.get('risk_per_trade_pct', default_risk_pct)}%, "
                     f"max_leverage={overrides.get('max_leverage', default_leverage)}")
    else:
        console.print(f"\n[{CLIColors.DIM_TEXT}]Using risk profile from config (no overrides).[/]")
    
    return overrides


def _run_backtest(cli: "TradeCLI", system_id: str = None, window_name: str = None, skip_risk_prompt: bool = False):
    """Run a backtest for a system."""
    from trade_cli import run_long_action
    
    # Get system ID if not provided
    if not system_id:
        system_id = _select_system("Select system to backtest")
        if not system_id:
            return None
    
    # Get window name if not provided
    if not window_name:
        window_name = _select_window()
        if not window_name:
            return None
    
    # Get risk overrides (unless skipped for batch runs)
    risk_overrides = {}
    if not skip_risk_prompt:
        risk_overrides = _get_risk_overrides(system_id)
    
    console.print(f"\n[{CLIColors.NEON_CYAN}]Running backtest: {system_id} / {window_name}...[/]")
    
    # Run with spinner for long operation
    def do_backtest():
        return backtest_run_tool(
            system_id, 
            window_name, 
            write_artifacts=True,
            risk_overrides=risk_overrides if risk_overrides else None,
        )
    
    result = run_long_action(f"backtest.run.{window_name}", do_backtest)
    
    if result.success and result.data:
        data = result.data
        metrics = data.get("metrics", {})
        
        console.print(f"\n[bold {CLIColors.NEON_GREEN}]Backtest Complete![/]\n")
        
        # Summary table with new field names
        table = Table(title=f"Results: {system_id} / {window_name}", border_style=CLIColors.NEON_GREEN)
        table.add_column("Metric", style=CLIColors.NEON_CYAN)
        table.add_column("Value", justify="right")
        
        # Equity
        table.add_row("Initial Equity", f"${metrics.get('initial_equity', 0):,.2f}")
        table.add_row("Final Equity", f"${metrics.get('final_equity', 0):,.2f}")
        table.add_row("Net Return", f"{metrics.get('net_return_pct', 0):.2f}%")
        table.add_row("", "")
        
        # Performance
        table.add_row("Total Trades", str(metrics.get("total_trades", 0)))
        table.add_row("Win Rate", f"{metrics.get('win_rate', 0):.1f}%")
        table.add_row("Profit Factor", f"{metrics.get('profit_factor', 0):.2f}")
        table.add_row("Sharpe", f"{metrics.get('sharpe', 0):.2f}")
        table.add_row("", "")
        
        # Risk
        table.add_row("Max Drawdown", f"${metrics.get('max_drawdown_abs', 0):,.2f} ({metrics.get('max_drawdown_pct', 0):.1f}%)")
        table.add_row("DD Duration", f"{metrics.get('max_drawdown_duration_bars', 0)} bars")
        table.add_row("Total Fees", f"${metrics.get('total_fees', 0):,.2f}")
        
        console.print(table)
        
        # Trades summary
        ts = data.get("trades_summary", {})
        console.print(f"\n[{CLIColors.DIM_TEXT}]Trades: {ts.get('winners', 0)} wins, {ts.get('losers', 0)} losses[/]")
        
        # Risk used
        console.print(f"[{CLIColors.DIM_TEXT}]Risk used: equity=${data.get('risk_initial_equity_used', 0):,.0f}, "
                     f"risk/trade={data.get('risk_per_trade_pct_used', 0):.1f}%, "
                     f"leverage={data.get('risk_max_leverage_used', 0):.1f}x[/]")
        
        if data.get("artifact_dir"):
            console.print(f"[{CLIColors.DIM_TEXT}]Artifacts: {data['artifact_dir']}[/]")
        
        console.print(f"[{CLIColors.DIM_TEXT}]Run ID: {data.get('run_id')}[/]")
        
        Prompt.ask("\nPress Enter to continue")
        return result
    else:
        console.print(f"[{CLIColors.NEON_RED}]Error: {result.error or result.message}[/]")
        Prompt.ask("\nPress Enter to continue")
        return None


def _run_both_windows(cli: "TradeCLI"):
    """Run backtest for both hygiene and test windows."""
    system_id = _select_system("Select system to backtest (both windows)")
    if not system_id:
        return
    
    # Get risk overrides once for both windows
    risk_overrides = _get_risk_overrides(system_id)
    
    console.print(f"\n[bold {CLIColors.NEON_YELLOW}]Running both windows for {system_id}...[/]\n")
    
    # Run hygiene (skip risk prompt since we already collected overrides)
    console.print(f"[{CLIColors.NEON_CYAN}]--- HYGIENE WINDOW ---[/]")
    _run_backtest_with_overrides(cli, system_id, "hygiene", risk_overrides)
    
    console.print("")
    
    # Run test
    console.print(f"[{CLIColors.NEON_CYAN}]--- TEST WINDOW ---[/]")
    _run_backtest_with_overrides(cli, system_id, "test", risk_overrides)
    
    Prompt.ask("\nPress Enter to continue")


def _run_backtest_with_overrides(cli: "TradeCLI", system_id: str, window_name: str, risk_overrides: dict):
    """Run backtest with pre-collected risk overrides (internal helper)."""
    from trade_cli import run_long_action
    
    console.print(f"\n[{CLIColors.NEON_CYAN}]Running backtest: {system_id} / {window_name}...[/]")
    
    def do_backtest():
        return backtest_run_tool(
            system_id, 
            window_name, 
            write_artifacts=True,
            risk_overrides=risk_overrides if risk_overrides else None,
        )
    
    result = run_long_action(f"backtest.run.{window_name}", do_backtest)
    
    if result.success and result.data:
        data = result.data
        metrics = data.get("metrics", {})
        
        console.print(f"\n[bold {CLIColors.NEON_GREEN}]Backtest Complete![/]")
        
        # Compact summary for batch runs
        console.print(f"  Trades: {metrics.get('total_trades', 0)} | "
                     f"Return: {metrics.get('net_return_pct', 0):.2f}% | "
                     f"Max DD: {metrics.get('max_drawdown_pct', 0):.1f}% | "
                     f"Sharpe: {metrics.get('sharpe', 0):.2f}")
    else:
        console.print(f"[{CLIColors.NEON_RED}]Error: {result.error or result.message}[/]")


def _prepare_data(cli: "TradeCLI", fresh_db: bool = False):
    """Prepare data for backtesting."""
    from trade_cli import run_long_action
    
    system_id = _select_system("Select system to prepare data for")
    if not system_id:
        return
    
    # Confirm if fresh DB
    if fresh_db:
        console.print(f"\n[{CLIColors.NEON_RED}]WARNING: This will DELETE ALL existing data![/]")
        if not Confirm.ask("Are you sure?"):
            return
    
    action = "Wiping DB and preparing" if fresh_db else "Preparing"
    console.print(f"\n[{CLIColors.NEON_CYAN}]{action} data for {system_id}...[/]")
    
    def do_prepare():
        return backtest_prepare_data_tool(system_id, fresh_db=fresh_db)
    
    result = run_long_action("backtest.prepare_data", do_prepare, timeout=600)
    
    if result.success and result.data:
        data = result.data
        console.print(f"\n[bold {CLIColors.NEON_GREEN}]Data prepared![/]")
        console.print(f"Symbol: {data.get('symbol')}")
        console.print(f"Period: {data.get('period')}")
        console.print(f"TFs: {', '.join(data.get('tfs', []))}")
        if fresh_db:
            console.print(f"[{CLIColors.NEON_YELLOW}]Fresh DB: Yes (all previous data deleted)[/]")
    else:
        console.print(f"[{CLIColors.NEON_RED}]Error: {result.error or result.message}[/]")
    
    Prompt.ask("\nPress Enter to continue")


def _verify_data(cli: "TradeCLI"):
    """Verify data quality for a system."""
    from trade_cli import run_long_action
    
    system_id = _select_system("Select system to verify data for")
    if not system_id:
        return
    
    window_name = _select_window()
    if not window_name:
        return
    
    console.print(f"\n[{CLIColors.NEON_CYAN}]Verifying data for {system_id}/{window_name}...[/]")
    
    def do_verify():
        return backtest_verify_data_tool(system_id, window_name, heal_gaps=True)
    
    result = run_long_action("backtest.verify_data", do_verify)
    
    if result.success and result.data:
        data = result.data
        passed = data.get("verification_passed", False)
        status_color = CLIColors.NEON_GREEN if passed else CLIColors.NEON_RED
        status_text = "PASSED" if passed else "FAILED"
        
        console.print(f"\n[bold {status_color}]Verification: {status_text}[/]")
        console.print(f"Symbol: {data.get('symbol')} {data.get('tf')}")
        console.print(f"Window: {data.get('window_start')} → {data.get('window_end')}")
        console.print(f"Bars: {data.get('bar_count', 0)}")
        console.print(f"Gaps: {data.get('gaps_found', 0)}")
        if data.get("gaps_healed", 0) > 0:
            console.print(f"Gaps Healed: {data.get('gaps_healed')}")
    else:
        console.print(f"[{CLIColors.NEON_RED}]Error: {result.error or result.message}[/]")
    
    Prompt.ask("\nPress Enter to continue")


def _list_strategies(cli: "TradeCLI"):
    """List available strategy implementations."""
    console.print(f"\n[{CLIColors.NEON_CYAN}]Listing strategies...[/]")
    console.print(f"[{CLIColors.DIM_TEXT}]Strategies are code implementations. System configs select which to use.[/]\n")

    result = backtest_list_strategies_tool()

    if result.success and result.data:
        strategies = result.data.get("strategies", [])

        if not strategies:
            console.print(f"[{CLIColors.NEON_YELLOW}]No strategies registered.[/]")
        else:
            table = Table(title="Available Strategies", border_style=CLIColors.NEON_CYAN)
            table.add_column("Strategy ID", style=CLIColors.NEON_MAGENTA)
            table.add_column("Default Ver")
            table.add_column("Description", style=CLIColors.DIM_TEXT)
            
            for s in strategies:
                if isinstance(s, dict):
                    table.add_row(
                        s.get("strategy_id", "?"),
                        s.get("default_version", "1"),
                        s.get("description", ""),
                    )
                else:
                    # Backwards compat if just a string
                    table.add_row(str(s), "1", "")
            
            console.print(table)
    else:
        console.print(f"[{CLIColors.NEON_RED}]Error: {result.error or result.message}[/]")

    Prompt.ask("\nPress Enter to continue")
