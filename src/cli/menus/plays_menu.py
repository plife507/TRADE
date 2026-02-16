"""
Plays menu for the CLI.

Provides interactive play lifecycle management:
- Run a play (demo/live)
- View running instances (status)
- Stop a running instance
- Watch live dashboard
- Pause/Resume signal evaluation
- View logs
"""

from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

from src.cli.styles import CLIStyles, CLIColors, CLIIcons, BillArtWrapper

if TYPE_CHECKING:
    from trade_cli import TradeCLI
    from src.backtest.play import PlayInfo
    from src.cli.live_dashboard import OrderTracker

# Local console
console = Console()


def plays_menu(cli: "TradeCLI") -> None:
    """Interactive plays lifecycle menu."""
    from src.cli.utils import (
        clear_screen, print_header, get_input, get_choice, BACK,
        print_error_below_menu,
    )

    while True:
        clear_screen()
        print_header(connected=cli._connected)

        # Show running instances summary at top
        _print_running_summary()

        menu = CLIStyles.create_menu_table()

        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.FIRE} Launch ---[/]", "")
        menu.add_row("1", f"[bold {CLIColors.NEON_GREEN}]Run Play[/]", f"[{CLIColors.NEON_GREEN}]Start a play in demo or live mode[/]")
        menu.add_row("", "", "")
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.CHART_UP} Monitor ---[/]", "")
        menu.add_row("2", "Status", "View all running play instances")
        menu.add_row("3", "Watch", "Live dashboard (auto-refresh)")
        menu.add_row("4", "Logs", "View play journal/logs")
        menu.add_row("", "", "")
        menu.add_row("", f"[{CLIColors.DIM_TEXT}]--- {CLIIcons.SETTINGS} Control ---[/]", "")
        menu.add_row("5", "Pause", "Pause signal evaluation (indicators keep updating)")
        menu.add_row("6", "Resume", "Resume signal evaluation")
        menu.add_row("7", f"[{CLIColors.NEON_RED}]Stop[/]", f"[{CLIColors.NEON_RED}]Stop a running play instance[/]")
        menu.add_row("8", f"[bold {CLIColors.NEON_RED}]Stop All[/]", f"[{CLIColors.NEON_RED}]Stop all running instances[/]")
        menu.add_row("", "", "")
        menu.add_row("9", f"{CLIIcons.BACK} Back", "Return to main menu")

        BillArtWrapper.print_menu_top()
        console.print(CLIStyles.get_menu_panel(menu, "PLAYS"))
        BillArtWrapper.print_menu_bottom()

        choice = get_choice(valid_range=range(1, 10))
        if choice is BACK:
            return

        try:
            if choice == 1:
                _run_play(cli)
            elif choice == 2:
                _show_status()
            elif choice == 3:
                _watch_plays()
            elif choice == 4:
                _view_logs()
            elif choice == 5:
                _pause_play()
            elif choice == 6:
                _resume_play()
            elif choice == 7:
                _stop_play()
            elif choice == 8:
                _stop_all()
            elif choice == 9:
                return
        except KeyboardInterrupt:
            console.print("\n[yellow]Operation cancelled.[/]")
            Prompt.ask("\nPress Enter to continue")
        except Exception as e:
            print_error_below_menu(f"Error: {e}")
            Prompt.ask("\nPress Enter to continue")


def _print_running_summary() -> None:
    """Print a compact summary of running instances."""
    from src.engine import EngineManager

    try:
        manager = EngineManager.get_instance()
        instances = manager.list_all()
    except Exception:
        return

    if not instances:
        console.print(f"  [{CLIColors.DIM_TEXT}]No running plays[/]")
        return

    for info in instances:
        mode_color = "green" if info.mode.value == "demo" else "red"
        console.print(
            f"  [{mode_color}]{info.mode.value.upper()}[/] "
            f"[cyan]{info.play_id}[/] "
            f"[yellow]{info.symbol}[/] "
            f"[dim]| bars={info.bars_processed} signals={info.signals_generated} "
            f"status={info.status}[/]"
        )
    console.print()


def _select_play() -> str | None:
    """Interactive play selection with directory browsing and preview.

    Flow: pick folder -> pick play -> review metadata -> confirm or go back.
    Validation plays are excluded.
    Returns play_id or None on cancel.
    """
    from src.backtest.play import list_play_dirs, peek_play_yaml

    while True:
        groups = list_play_dirs(exclude_validation=True)
        if not groups:
            console.print("[yellow]No plays found in plays/ directory.[/]")
            return None

        # Build folder list -- "." becomes "plays/ (root)"
        folder_keys = sorted(groups.keys(), key=lambda k: ("" if k == "." else k))
        total = sum(len(v) for v in groups.values())

        console.print(f"\n[bold]Play Folders[/] [dim]({total} plays total)[/]")
        table = Table(show_header=True, header_style="bold", padding=(0, 1))
        table.add_column("#", style="dim", width=4)
        table.add_column("Folder", style=CLIColors.NEON_CYAN)
        table.add_column("Plays", justify="right", style=CLIColors.NEON_GREEN)

        for i, key in enumerate(folder_keys, 1):
            label = "plays/ (root)" if key == "." else f"plays/{key}/"
            table.add_row(str(i), label, str(len(groups[key])))

        console.print(table)
        console.print()

        raw = Prompt.ask("[cyan]Select folder number (or 'q' to cancel)[/]")
        if raw.lower() in ("b", "back", "q"):
            return None

        try:
            idx = int(raw)
            if not (1 <= idx <= len(folder_keys)):
                console.print(f"[yellow]Invalid number. Must be 1-{len(folder_keys)}.[/]")
                continue
        except ValueError:
            console.print("[yellow]Enter a number.[/]")
            continue

        folder_key = folder_keys[idx - 1]
        paths = groups[folder_key]

        # Show plays in chosen folder
        selected_path = _select_play_from_folder(folder_key, paths)
        if selected_path is None:
            continue  # Back to folder selection

        # Preview the play and confirm
        info = peek_play_yaml(selected_path)
        confirmed = _preview_play(info)
        if confirmed:
            return info.id

        # User declined -- loop back to folder selection


def _select_play_from_folder(folder_key: str, paths: list[Path]) -> Path | None:
    """Show plays inside a folder, return selected Path or None to go back."""
    from src.backtest.play import peek_play_yaml

    folder_label = "plays/ (root)" if folder_key == "." else f"plays/{folder_key}/"

    while True:
        console.print(f"\n[bold]{folder_label}[/] [dim]({len(paths)} plays)[/]")

        table = Table(show_header=True, header_style="bold", padding=(0, 1))
        table.add_column("#", style="dim", width=4)
        table.add_column("Play ID", style=CLIColors.NEON_CYAN, min_width=28)
        table.add_column("Symbol", style=CLIColors.NEON_YELLOW, width=10)
        table.add_column("TF", style=CLIColors.NEON_GREEN, width=5)
        table.add_column("Dir", width=10)
        table.add_column("Description", style=CLIColors.DIM_TEXT, max_width=40)

        infos = []
        for p in paths:
            info = peek_play_yaml(p)
            infos.append(info)

        for i, info in enumerate(infos, 1):
            dir_style = "green" if info.direction == "long" else "red" if info.direction == "short" else "yellow"
            table.add_row(
                str(i),
                info.id,
                info.symbol,
                info.exec_tf,
                f"[{dir_style}]{info.direction}[/]",
                info.description[:40] if info.description else "",
            )

        console.print(table)
        console.print()

        raw = Prompt.ask("[cyan]Select play number (or 'b' for back)[/]")
        if raw.lower() in ("b", "back", "q"):
            return None

        try:
            idx = int(raw)
            if 1 <= idx <= len(paths):
                return paths[idx - 1]
            console.print(f"[yellow]Invalid number. Must be 1-{len(paths)}.[/]")
        except ValueError:
            # Try direct name match
            for p in paths:
                if p.stem == raw.strip():
                    return p
            console.print("[yellow]No match. Enter a number or exact play name.[/]")


def _preview_play(info: "PlayInfo") -> bool:
    """Show play metadata and ask user to confirm or go back."""

    # Read the full YAML for richer preview
    import yaml as _yaml
    raw: dict = {}
    try:
        with open(info.path, "r", encoding="utf-8") as f:
            raw = _yaml.safe_load(f) or {}
    except Exception:
        pass

    tfs = raw.get("timeframes", {})
    account = raw.get("account", {})
    risk = raw.get("risk_model", {})
    actions = raw.get("actions", {})
    features = raw.get("features", {})
    structures = raw.get("structures", {})

    # Build preview panel
    lines: list[str] = []
    lines.append(f"[bold cyan]{info.name}[/]")
    if raw.get("description"):
        desc = raw["description"].strip()
        # Show first 3 lines of description
        for line in desc.split("\n")[:3]:
            lines.append(f"[dim]{line.strip()}[/]")
    lines.append("")

    # Core info
    lines.append(f"[bold]Symbol:[/]  {info.symbol}")
    lines.append(f"[bold]Exec TF:[/] {info.exec_tf}  [dim](low={tfs.get('low_tf', '?')}  med={tfs.get('med_tf', '?')}  high={tfs.get('high_tf', '?')})[/]")
    lines.append(f"[bold]Direction:[/] {info.direction}")
    lines.append("")

    # Account
    if account:
        equity = account.get("starting_equity_usdt", "?")
        leverage = account.get("max_leverage", "?")
        lines.append(f"[bold]Account:[/]  ${equity} equity, {leverage}x max leverage")

    # Risk
    if risk:
        sl = risk.get("stop_loss", {})
        tp = risk.get("take_profit", {})
        sl_str = f"{sl.get('type', '?')} {sl.get('pct', sl.get('atr_multiple', '?'))}" if sl else "none"
        tp_str = f"{tp.get('type', '?')} {tp.get('pct', tp.get('atr_multiple', '?'))}" if tp else "none"
        lines.append(f"[bold]Risk:[/]     SL={sl_str}  TP={tp_str}")

    # Features & Structures
    feat_count = len(features) if isinstance(features, dict) else 0
    struct_count = len(structures) if isinstance(structures, dict) else 0
    action_entries = [k for k in actions if k.startswith("entry_")]
    action_exits = [k for k in actions if k.startswith("exit_")]
    lines.append(f"[bold]Features:[/] {feat_count} indicators, {struct_count} structures")
    lines.append(f"[bold]Actions:[/]  {len(action_entries)} entry blocks, {len(action_exits)} exit blocks")
    lines.append("")
    lines.append(f"[dim]File: {info.path}[/]")

    console.print(Panel(
        "\n".join(lines),
        title="[bold]Play Review[/]",
        border_style="cyan",
    ))

    return Confirm.ask("[cyan]Run this play?[/]", default=True)


def _select_running_instance() -> str | None:
    """Interactive instance selection. Returns instance_id or None."""
    from src.engine import EngineManager

    manager = EngineManager.get_instance()
    instances = manager.list_all()

    if not instances:
        console.print("[dim]No running play instances.[/]")
        return None

    console.print(f"\n[bold]Running Instances ({len(instances)}):[/]")
    for i, info in enumerate(instances, 1):
        mode_color = "green" if info.mode.value == "demo" else "red"
        console.print(
            f"  {i:>3}  [{mode_color}]{info.mode.value.upper():>4}[/] "
            f"[cyan]{info.play_id}[/] "
            f"[yellow]{info.symbol}[/] "
            f"[dim]{info.instance_id}[/]"
        )

    console.print()
    raw = Prompt.ask("[cyan]Select instance number[/]")

    if raw.lower() in ("b", "back", "q"):
        return None

    try:
        idx = int(raw)
        if 1 <= idx <= len(instances):
            return instances[idx - 1].instance_id
        console.print(f"[yellow]Invalid number. Must be 1-{len(instances)}.[/]")
        return None
    except ValueError:
        # Try as instance ID directly
        for info in instances:
            if info.instance_id == raw or info.play_id == raw:
                return info.instance_id
        console.print(f"[yellow]No instance matching '{raw}'.[/]")
        return None


def _wire_order_tracker(
    manager: object,
    instance_id: str,
    tracker: "OrderTracker",
) -> None:
    """Register OrderTracker as execution callback on the OrderExecutor.

    Walks: EngineManager -> instance -> engine -> exchange -> order_executor
    to find the ``OrderExecutor.on_execution()`` hook.
    """
    try:
        from typing import Any
        instances: dict[str, Any] = getattr(manager, "_instances", {})
        inst = instances.get(instance_id)
        if inst is None:
            return
        engine = inst.engine
        if engine is None:
            return
        exchange = getattr(engine, "_exchange", None)
        if exchange is None:
            return
        # LiveExchange wraps an OrderExecutor
        order_executor = getattr(exchange, "_order_executor", None)
        if order_executor is None:
            # Try via exchange_manager -> order_executor
            em = getattr(exchange, "_exchange_manager", None)
            if em is not None:
                order_executor = getattr(em, "_order_executor", None)
        if order_executor is not None and hasattr(order_executor, "on_execution"):
            order_executor.on_execution(tracker.record_execution_result)
    except Exception:
        pass  # Best effort -- dashboard still works without order tracking


def _run_play(cli: "TradeCLI") -> None:
    """Run a play interactively with live dashboard.

    Uses background engine thread + main-thread dashboard (with keyboard
    controls: m=meta toggle, p=pause, q=quit).
    """
    import asyncio
    import logging
    import threading
    import yaml
    from typing import Literal
    from src.backtest.play import Play, load_play
    from src.engine import EngineManager
    from src.cli.live_dashboard import (
        DashboardLogHandler,
        DashboardState,
        OrderTracker,
        populate_play_meta,
        run_dashboard,
    )

    play_id = _select_play()
    if not play_id:
        return

    # Load the play
    try:
        play_path = Path(play_id)
        if play_path.exists() and play_path.is_file():
            with open(play_path, "r", encoding="utf-8", newline='\n') as f:
                raw = yaml.safe_load(f)
            play = Play.from_dict(raw)
        else:
            play = load_play(play_id)
    except Exception as e:
        console.print(f"[red]Failed to load play: {e}[/]")
        Prompt.ask("\nPress Enter to continue")
        return

    # Show play info
    symbols = play.symbol_universe if play.symbol_universe else ["N/A"]
    symbol_str = symbols[0] if len(symbols) == 1 else f"{symbols[0]} (+{len(symbols)-1} more)"
    console.print(Panel(
        f"[bold cyan]{play.name}[/]\n"
        f"[dim]Symbol: {symbol_str} | Exec TF: {play.exec_tf}[/]",
        border_style="cyan",
    ))

    # Select mode
    mode: Literal["demo", "live"]
    is_demo = cli.config.bybit.use_demo
    if is_demo:
        console.print("[green]Connected in DEMO mode - play will run in DEMO.[/]")
        mode = "demo"
    else:
        console.print("[red]Connected in LIVE mode.[/]")
        mode_choice = Prompt.ask(
            "[cyan]Run mode[/]",
            choices=["demo", "live"],
            default="demo",
        )
        mode = "live" if mode_choice == "live" else "demo"

    # Safety for live
    if mode == "live":
        console.print(Panel(
            "[bold red]LIVE TRADING - REAL MONEY[/]\n"
            f"[red]Play: {play.name} | Symbol: {symbol_str}[/]",
            border_style="red",
        ))
        if not Confirm.ask("[red]Confirm LIVE trading with real money?[/]", default=False):
            console.print("[green]Cancelled.[/]")
            Prompt.ask("\nPress Enter to continue")
            return

        # Run pre-live validation
        from src.cli.validate import run_validation, Tier
        console.print("[cyan]Running pre-live validation gate...[/]")
        gate_result = run_validation(Tier.PRE_LIVE, play_id=play_id)
        if gate_result != 0:
            console.print("[bold red]Pre-live validation FAILED. Cannot start live trading.[/]")
            Prompt.ask("\nPress Enter to continue")
            return
        console.print("[green]Pre-live validation passed.[/]")

    # Start the play via EngineManager
    manager = EngineManager.get_instance()
    symbol = symbols[0]

    console.print(f"\n[cyan]Starting {play.name} in {mode.upper()} mode...[/]")
    console.print("[dim]Hotkeys: [m] meta  [p] pause  [q] quit[/]\n")

    # --- Dashboard state + log handler ---
    dash_state = DashboardState(
        play_name=play.name or play.id,
        description=play.description or "",
        symbol=symbol,
        mode=mode.upper(),
        exec_tf=play.exec_tf,
        leverage=play.account.max_leverage if play.account else 1.0,
    )
    populate_play_meta(dash_state, play)

    dash_handler = DashboardLogHandler(max_lines=50, max_actions=20)
    dash_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    )

    # Enable debug so runner logs full tracebacks into dashboard
    from src.utils.debug import enable_debug, is_debug_enabled
    was_debug = is_debug_enabled()
    enable_debug(True)

    # Swap console StreamHandlers on "trade" logger to dashboard handler
    trade_logger = logging.getLogger("trade")
    prev_level = trade_logger.level
    trade_logger.setLevel(logging.DEBUG)
    console_handlers = [
        h for h in trade_logger.handlers
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
    ]
    for h in console_handlers:
        trade_logger.removeHandler(h)
    trade_logger.addHandler(dash_handler)

    # Order tracker for the Orders tab
    order_tracker = OrderTracker(max_events=50)

    stop_event = threading.Event()
    instance_id: str | None = None
    engine_error: Exception | None = None
    captured_runner_stats: dict | None = None

    def _engine_thread() -> None:
        """Run the async engine in a background thread.

        Watches stop_event and performs graceful shutdown on its OWN
        event loop (avoids 'Future attached to a different loop').
        """
        nonlocal instance_id, engine_error, captured_runner_stats
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def _run() -> None:
                nonlocal instance_id, captured_runner_stats
                instance_id = await manager.start(play, mode=mode)
                instance = manager._instances.get(instance_id)
                if not instance or not instance.task:
                    return

                # Wire OrderTracker to OrderExecutor callback (if available)
                if instance_id is not None:
                    _wire_order_tracker(manager, instance_id, order_tracker)

                # Wait for engine task OR stop signal from dashboard
                while not instance.task.done():
                    if stop_event.is_set():
                        captured_runner_stats = manager.get_runner_stats(instance_id)
                        try:
                            await asyncio.wait_for(
                                manager.stop(instance_id), timeout=15.0
                            )
                        except (asyncio.TimeoutError, Exception):
                            pass
                        return
                    await asyncio.sleep(0.25)

            loop.run_until_complete(_run())
        except Exception as e:
            engine_error = e
        finally:
            loop.close()
            stop_event.set()

    # --- Start engine in background thread ---
    engine_thread = threading.Thread(target=_engine_thread, daemon=True)
    engine_thread.start()

    # --- Run dashboard in main thread (blocks until stop_event or q/Ctrl+C) ---
    try:
        run_dashboard(
            manager=manager,
            state=dash_state,
            handler=dash_handler,
            stop_event=stop_event,
            refresh_hz=2.0,
            order_tracker=order_tracker,
        )
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()  # Signal engine thread to shut down

    # Wait for engine thread to finish (it handles its own stop on its loop)
    engine_thread.join(timeout=20.0)

    # --- Restore logger and debug state ---
    trade_logger.removeHandler(dash_handler)
    for h in console_handlers:
        trade_logger.addHandler(h)
    trade_logger.setLevel(prev_level)
    enable_debug(was_debug)

    # --- Print final summary ---
    if engine_error:
        if is_debug_enabled():
            import traceback as tb
            console.print(f"\n[red]{mode.upper()} mode error:[/]")
            console.print(f"[red]{tb.format_exception(engine_error)}[/]")
        else:
            console.print(f"\n[red]{mode.upper()} mode error: {engine_error}[/]")
        Prompt.ask("\nPress Enter to continue")
        return

    if captured_runner_stats is None and instance_id:
        captured_runner_stats = manager.get_runner_stats(instance_id)

    if captured_runner_stats:
        bars = captured_runner_stats.get("bars_processed", 0)
        signals = captured_runner_stats.get("signals_generated", 0)
        fills = captured_runner_stats.get("orders_filled", 0)
        secs = captured_runner_stats.get("duration_seconds", 0)
        mins, s = divmod(int(secs), 60)
        console.print(f"\n[green]{mode.upper()} run complete:[/]")
        console.print(f"  Duration: {mins}m{s:02d}s")
        console.print(f"  Bars: {bars}")
        console.print(f"  Signals: {signals}")
        if fills:
            console.print(f"  Fills: {fills}")
    else:
        console.print(f"\n[green]{mode.upper()} run complete.[/]")

    Prompt.ask("\nPress Enter to continue")


def _show_status() -> None:
    """Show status of all running play instances."""
    from src.engine import EngineManager

    manager = EngineManager.get_instance()
    instances = manager.list_all()

    if not instances:
        console.print("\n[dim]No running play instances.[/]")
        Prompt.ask("\nPress Enter to continue")
        return

    table = Table(title="Running Play Instances")
    table.add_column("Instance ID", style="cyan")
    table.add_column("Play", style="white")
    table.add_column("Symbol", style="yellow")
    table.add_column("Mode", style="green")
    table.add_column("Status", style="white")
    table.add_column("Bars", justify="right")
    table.add_column("Signals", justify="right")
    table.add_column("Orders (S/F/X)", justify="right", style="dim")
    table.add_column("Duration", style="dim")
    table.add_column("Last Candle", style="dim")

    for info in instances:
        stats = manager.get_runner_stats(info.instance_id)
        orders_str = ""
        duration_str = ""
        last_candle_str = ""

        if stats:
            sub = stats.get("orders_submitted", 0)
            fill = stats.get("orders_filled", 0)
            fail = stats.get("orders_failed", 0)
            orders_str = f"{sub}/{fill}/{fail}"
            secs = stats.get("duration_seconds", 0)
            mins, s = divmod(int(secs), 60)
            hrs, m = divmod(mins, 60)
            duration_str = f"{hrs}h{m:02d}m" if hrs else f"{m}m{s:02d}s"
            lc = stats.get("last_candle_ts")
            last_candle_str = lc[:19] if lc else ""

        mode_color = "green" if info.mode.value == "demo" else "red"
        table.add_row(
            info.instance_id,
            info.play_id,
            info.symbol,
            f"[{mode_color}]{info.mode.value.upper()}[/]",
            info.status,
            str(info.bars_processed),
            str(info.signals_generated),
            orders_str,
            duration_str,
            last_candle_str,
        )

    console.print(table)
    Prompt.ask("\nPress Enter to continue")


def _watch_plays() -> None:
    """Live dashboard with auto-refresh."""
    import time as _time
    from rich.live import Live
    from src.engine import EngineManager

    manager = EngineManager.get_instance()

    def _build_display() -> Table:
        instances = manager.list_all()
        if not instances:
            table = Table(title="Play Watch -- No Running Instances", border_style="dim")
            table.add_column("Info")
            table.add_row("[dim]Waiting for instances... (Ctrl+C to exit)[/]")
            return table

        table = Table(title="Play Watch (live)", border_style="cyan")
        table.add_column("Play", style="cyan")
        table.add_column("Symbol", style="yellow")
        table.add_column("Mode", style="green")
        table.add_column("Status")
        table.add_column("Bars", justify="right")
        table.add_column("Signals", justify="right")
        table.add_column("Orders (S/F/X)", justify="right", style="dim")
        table.add_column("Duration", style="dim")
        table.add_column("Last Candle", style="dim")

        for info in instances:
            stats = manager.get_runner_stats(info.instance_id)
            orders_str = ""
            duration_str = ""
            last_candle_str = ""

            if stats:
                sub = stats.get("orders_submitted", 0)
                fill = stats.get("orders_filled", 0)
                fail = stats.get("orders_failed", 0)
                orders_str = f"{sub}/{fill}/{fail}"
                secs = stats.get("duration_seconds", 0)
                mins, s = divmod(int(secs), 60)
                hrs, m = divmod(mins, 60)
                duration_str = f"{hrs}h{m:02d}m" if hrs else f"{m}m{s:02d}s"
                lc = stats.get("last_candle_ts")
                last_candle_str = lc[:19] if lc else ""

            mode_color = "green" if info.mode.value == "demo" else "red"
            table.add_row(
                info.play_id,
                info.symbol,
                f"[{mode_color}]{info.mode.value.upper()}[/]",
                info.status,
                str(info.bars_processed),
                str(info.signals_generated),
                orders_str,
                duration_str,
                last_candle_str,
            )

        return table

    console.print("[dim]Press Ctrl+C to exit watch (does not stop the engine)[/]")

    try:
        with Live(_build_display(), console=console, refresh_per_second=1) as live:
            while True:
                _time.sleep(2.0)
                live.update(_build_display())
    except KeyboardInterrupt:
        console.print("\n[dim]Watch stopped.[/]")

    Prompt.ask("\nPress Enter to continue")


def _view_logs() -> None:
    """View logs for a play instance."""
    instance_id = _select_running_instance()
    if not instance_id:
        Prompt.ask("\nPress Enter to continue")
        return

    import json
    from pathlib import Path

    journal_dir = Path.home() / ".trade" / "journal"
    if not journal_dir.exists():
        console.print("[dim]No journal directory found.[/]")
        Prompt.ask("\nPress Enter to continue")
        return

    # Find matching journal file
    matches = list(journal_dir.glob(f"*{instance_id}*.jsonl"))
    if not matches:
        # Try play_id from instance file
        instances_dir = Path.home() / ".trade" / "instances"
        if instances_dir.exists():
            for path in instances_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if data.get("instance_id") == instance_id:
                        play_id = data.get("play_id", "")
                        matches = list(journal_dir.glob(f"*{play_id}*.jsonl"))
                        break
                except Exception:
                    continue

    if not matches:
        console.print(f"[dim]No logs found for '{instance_id}'.[/]")
        Prompt.ask("\nPress Enter to continue")
        return

    journal_path = matches[0]
    console.print(f"[dim]Reading: {journal_path}[/]\n")

    try:
        lines = journal_path.read_text(encoding="utf-8").strip().split("\n")
        display_lines = lines[-50:]

        for line in display_lines:
            try:
                entry = json.loads(line)
                ts = entry.get("timestamp", "")[:19]
                event = entry.get("event", "?")
                symbol = entry.get("symbol", "")
                direction = entry.get("direction", "")
                if event == "fill":
                    price = entry.get("fill_price", "?")
                    console.print(f"  {ts} [green]FILL[/] {symbol} {direction} @ {price}")
                elif event == "signal":
                    size = entry.get("size_usdt", "?")
                    console.print(f"  {ts} [cyan]SIGNAL[/] {symbol} {direction} ${size}")
                elif event == "error":
                    err = entry.get("error", "?")
                    console.print(f"  {ts} [red]ERROR[/] {symbol} {err}")
                else:
                    console.print(f"  {ts} {event} {line[:80]}")
            except json.JSONDecodeError:
                console.print(f"  {line[:100]}")
    except Exception as e:
        console.print(f"[red]Error reading logs: {e}[/]")

    Prompt.ask("\nPress Enter to continue")


def _pause_play() -> None:
    """Pause signal evaluation for a running instance."""
    instance_id = _select_running_instance()
    if not instance_id:
        Prompt.ask("\nPress Enter to continue")
        return

    from pathlib import Path

    pause_dir = Path.home() / ".trade" / "instances"
    pause_dir.mkdir(parents=True, exist_ok=True)
    pause_file = pause_dir / f"{instance_id}.pause"
    pause_file.touch()

    console.print(f"[yellow]Paused: {instance_id}[/]")
    console.print("[dim]Indicators continue updating. Use Resume to resume signal evaluation.[/]")
    Prompt.ask("\nPress Enter to continue")


def _resume_play() -> None:
    """Resume signal evaluation for a paused instance."""
    instance_id = _select_running_instance()
    if not instance_id:
        Prompt.ask("\nPress Enter to continue")
        return

    from pathlib import Path

    pause_dir = Path.home() / ".trade" / "instances"
    pause_file = pause_dir / f"{instance_id}.pause"

    if pause_file.exists():
        pause_file.unlink()
        console.print(f"[green]Resumed: {instance_id}[/]")
    else:
        console.print(f"[dim]{instance_id} was not paused.[/]")

    Prompt.ask("\nPress Enter to continue")


def _stop_play() -> None:
    """Stop a single running play instance."""
    import asyncio
    from src.engine import EngineManager

    instance_id = _select_running_instance()
    if not instance_id:
        Prompt.ask("\nPress Enter to continue")
        return

    manager = EngineManager.get_instance()
    info = manager.get(instance_id)

    if info and info.mode.value == "live":
        console.print(f"[yellow]Warning: This is a LIVE instance ({info.play_id} on {info.symbol})[/]")
        if not Confirm.ask("[red]Stop this LIVE instance?[/]", default=False):
            console.print("[green]Cancelled.[/]")
            Prompt.ask("\nPress Enter to continue")
            return

    stopped = asyncio.run(manager.stop(instance_id))
    if stopped:
        console.print(f"[green]Stopped: {instance_id}[/]")
    else:
        console.print(f"[red]Failed to stop: {instance_id}[/]")

    Prompt.ask("\nPress Enter to continue")


def _stop_all() -> None:
    """Stop all running instances."""
    import asyncio
    from src.engine import EngineManager

    manager = EngineManager.get_instance()
    instances = manager.list_all()

    if not instances:
        console.print("[dim]No running instances to stop.[/]")
        Prompt.ask("\nPress Enter to continue")
        return

    console.print(f"\n[yellow]About to stop {len(instances)} instance(s):[/]")
    for info in instances:
        mode_color = "green" if info.mode.value == "demo" else "red"
        console.print(f"  [{mode_color}]{info.mode.value.upper()}[/] {info.play_id} ({info.symbol})")

    if not Confirm.ask("\n[red]Stop all instances?[/]", default=False):
        console.print("[green]Cancelled.[/]")
        Prompt.ask("\nPress Enter to continue")
        return

    count = asyncio.run(manager.stop_all())
    console.print(f"[green]Stopped {count} instance(s).[/]")
    Prompt.ask("\nPress Enter to continue")
