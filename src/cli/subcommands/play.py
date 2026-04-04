"""Play subcommand handlers for TRADE CLI."""

from __future__ import annotations

import json
from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from src.cli.utils import console
from src.cli.subcommands._helpers import _json_result, _print_result, _parse_datetime, _print_preflight_diagnostics


def handle_play_run(args) -> int:
    """
    Handle `play run` subcommand - run Play in specified mode.

    Modes:
        backtest: Historical data simulation
        live: Real-time data with Bybit live API (real money)

    Shadow mode: use `shadow run --play X` (daemon with full SimExchange).
    """
    import yaml
    from datetime import datetime, timedelta

    mode = args.mode

    # Safety check for live mode
    if mode == "live" and not args.confirm:
        console.print(Panel(
            "[bold red]LIVE TRADING REQUIRES CONFIRMATION[/]\n"
            "[red]You are about to trade with REAL MONEY.[/]\n"
            "[dim]Add --confirm to proceed.[/]",
            border_style="red"
        ))
        return 1

    from src.backtest.play import Play, load_play

    plays_dir = Path(args.plays_dir) if getattr(args, "plays_dir", None) else None
    play_path = Path(args.play)

    try:
        if play_path.exists() and play_path.is_file():
            with open(play_path, "r", encoding="utf-8", newline='\n') as f:
                raw = yaml.safe_load(f)
            play = Play.from_dict(raw)
        else:
            play = load_play(args.play, base_dir=plays_dir)
    except Exception as e:
        console.print(f"[red]Failed to load Play: {e}[/]")
        return 1

    # G15.1: Auto-run pre-live validation gate for live mode (after play resolution)
    if mode == "live":
        from src.cli.validate import run_validation, Tier
        console.print(f"[cyan]Running pre-live validation gate (live mode)...[/]")
        gate_result = run_validation(Tier.PRE_LIVE, play_id=play.id)
        if gate_result != 0:
            console.print(f"[bold red]Pre-live validation FAILED. Cannot start {mode} trading.[/]")
            return 1
        console.print("[green]Pre-live validation passed.[/]")

    headless = getattr(args, "headless", False)

    # In headless mode, redirect Rich console to stderr so stdout stays pure JSON
    if headless:
        import sys
        from rich.console import Console as _Console
        stderr_console = _Console(file=sys.stderr)
    else:
        stderr_console = console

    symbols = play.symbol_universe if play.symbol_universe else ["N/A"]
    symbol_str = symbols[0] if len(symbols) == 1 else f"{symbols[0]} (+{len(symbols)-1} more)"

    stderr_console.print(Panel(
        f"[bold cyan]Play: {play.name}[/]\n"
        f"[dim]Mode: {mode.upper()}[/]\n"
        f"[dim]Symbol: {symbol_str} | Exec TF: {play.exec_tf}[/]",
        border_style="cyan"
    ))

    from src.utils.debug import is_debug_enabled
    if is_debug_enabled() and mode == "live":
        stderr_console.print(Panel(
            "[bold yellow]DEBUG MODE ACTIVE[/]\n"
            "[dim]Full tracebacks, indicator snapshots, and rule evaluation details enabled.\n"
            "Log level: DEBUG | All output goes to console + log file.[/]",
            border_style="yellow"
        ))

    # Backtest mode: delegate to backtest_run_play_tool (golden path)
    # No need to create PlayEngineFactory engine -- the tool creates its own
    # via create_engine_from_play + run_engine_with_play.
    if mode == "backtest":
        return _run_play_backtest(play, args)

    from src.engine import EngineManager

    if mode == "live":
        # C5: Manager creates the engine -- do NOT create one here via factory
        # (the old code created a factory engine that was thrown away)
        return _run_play_live(play, args, manager=EngineManager.get_instance())

    return 0


def _run_play_backtest(play, args) -> int:
    """Run Play in backtest mode via backtest_run_play_tool (golden path).

    Delegates to the same tool that ``backtest run`` uses, so behaviour is
    identical regardless of which CLI entry-point the user chooses.
    """
    from src.tools.backtest_play_tools import backtest_run_play_tool

    start = _parse_datetime(args.start) if args.start else None
    end = _parse_datetime(args.end) if args.end else None
    plays_dir = Path(args.plays_dir) if getattr(args, "plays_dir", None) else None
    json_output = getattr(args, "json_output", False)

    result = backtest_run_play_tool(
        play_id=play.id,
        env=getattr(args, "data_env", "live"),
        start=start,
        end=end,
        smoke=getattr(args, "smoke", False),
        write_artifacts=not getattr(args, "no_artifacts", False),
        plays_dir=plays_dir,
        emit_snapshots=getattr(args, "emit_snapshots", False),
        sync=getattr(args, "sync", True),
    )

    if json_output:
        return _json_result(result)

    if result.data and "preflight" in result.data:
        _print_preflight_diagnostics(result.data["preflight"])

    rc = _print_result(result)
    if result.success and result.data and "artifact_dir" in result.data:
        console.print(f"[dim]Artifacts: {result.data['artifact_dir']}[/]")
    return rc


def _run_play_live(play, args, manager=None) -> int:
    """Run Play in live mode via EngineManager.

    Supports two UI modes:
    - Dashboard (default): Rich Live dashboard in main thread
    - Headless (--headless): JSON events on stdout, blocks until stopped
    """
    headless = getattr(args, "headless", False)
    if headless:
        return _run_play_live_headless(play, args, manager)
    return _run_play_live_dashboard(play, args, manager)


def _run_play_live_headless(play, args, manager=None) -> int:
    """Run Play in headless mode — no dashboard, JSON events on stdout.

    Prints a JSON 'started' event, blocks until Ctrl+C or `play stop`,
    then prints a JSON 'stopped' event with final stats.
    """
    import asyncio
    import signal as _signal
    import sys
    import time
    import threading
    from typing import Literal
    from src.engine import EngineManager

    # Force line-buffered stdout so Start-Process redirect works on Windows.
    # sys.stdout is typed as TextIO but at runtime it's an io.TextIOWrapper.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

    mode: Literal["live", "backtest"] = args.mode
    if manager is None:
        manager = EngineManager.get_instance()

    symbol: str = play.symbol_universe[0] if play.symbol_universe else "N/A"

    stop_event: threading.Event = threading.Event()

    # Handle SIGTERM (from `play stop` cross-process) for clean shutdown
    def _sigterm_handler(signum: int, frame: object) -> None:
        stop_event.set()

    _signal.signal(_signal.SIGTERM, _sigterm_handler)
    instance_id: str | None = None
    engine_error: Exception | None = None

    def _engine_thread() -> None:
        nonlocal instance_id, engine_error
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def _run() -> None:
                nonlocal instance_id
                instance_id = await manager.start(play, mode=mode)
                instance = manager._instances.get(instance_id)
                if not instance or not instance.task:
                    return

                while not instance.task.done():
                    if stop_event.is_set():
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

    engine_thread = threading.Thread(target=_engine_thread, daemon=True)
    engine_thread.start()

    # Wait for instance_id to be set (engine started)
    _deadline = time.monotonic() + 15.0
    while instance_id is None and engine_error is None and time.monotonic() < _deadline:
        time.sleep(0.25)

    if engine_error:
        sys.stdout.write(json.dumps({"event": "error", "error": str(engine_error)}) + "\n")
        sys.stdout.flush()
        return 1

    if instance_id is None:
        sys.stdout.write(json.dumps({"event": "error", "error": "Timed out waiting for engine to start"}) + "\n")
        sys.stdout.flush()
        return 1

    # Emit started event
    started_msg = json.dumps({
        "event": "started",
        "instance_id": instance_id,
        "play_id": play.name,
        "symbol": symbol,
        "mode": mode,
    })
    sys.stdout.write(started_msg + "\n")
    sys.stdout.flush()

    # Block until stop signal (Ctrl+C or play stop)
    _active_id: str = instance_id  # Copy for use after narrowing
    try:
        while not stop_event.is_set():
            stop_event.wait(timeout=1.0)
    except KeyboardInterrupt:
        stop_event.set()

    # Gather final stats before thread exits
    captured_runner_stats = manager.get_runner_stats(_active_id)
    captured_info = manager.get(_active_id)

    engine_thread.join(timeout=20.0)

    # Stop WebSocket bootstrap
    try:
        from src.core.application import get_application
        app = get_application()
        if app is not None:
            app.stop_websocket()
    except Exception:
        pass

    # Emit stopped event
    stopped_data: dict = {
        "event": "stopped",
        "instance_id": _active_id,
    }
    if captured_info:
        stopped_data["bars_processed"] = captured_info.bars_processed
        stopped_data["signals_generated"] = captured_info.signals_generated
    if captured_runner_stats:
        stopped_data["stats"] = captured_runner_stats

    sys.stdout.write(json.dumps(stopped_data) + "\n")
    sys.stdout.flush()

    return 1 if engine_error else 0


def _run_play_live_dashboard(play, args, manager=None) -> int:
    """Run Play with the Rich Live dashboard (original behavior)."""
    import asyncio
    import logging
    import threading
    from src.engine import EngineManager
    from src.cli.dashboard import (
        DashboardLogHandler,
        DashboardState,
        populate_play_meta,
        run_dashboard,
    )

    mode = args.mode
    if manager is None:
        manager = EngineManager.get_instance()

    symbol = play.symbol_universe[0] if play.symbol_universe else "N/A"

    # --- Dashboard state (shared between engine thread + display thread) ---
    dash_state = DashboardState(
        play_name=play.name,
        description=play.description.split("\n")[0].strip() if play.description else "",
        symbol=symbol,
        mode=mode.upper(),
        exec_tf=play.exec_tf,
        leverage=play.account.max_leverage,
    )

    # --- Populate static play metadata ---
    populate_play_meta(dash_state, play)

    # --- Log handler: intercept logger output for the dashboard ---
    dash_handler = DashboardLogHandler(max_lines=50, max_actions=20)
    dash_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))

    # Attach to the main trading logger and suppress console output.
    # With structlog, console handler lives on root (not trade), so suppress both.
    trade_logger = logging.getLogger("trade")
    console_handlers = [h for h in trade_logger.handlers if isinstance(h, logging.StreamHandler)
                        and not isinstance(h, logging.FileHandler)]
    for h in console_handlers:
        trade_logger.removeHandler(h)
    trade_logger.addHandler(dash_handler)

    # Suppress root console handler during dashboard (structlog puts it on root)
    root_logger = logging.getLogger()
    root_console_handlers = [
        h for h in root_logger.handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
    ]
    for h in root_console_handlers:
        root_logger.removeHandler(h)

    stop_event = threading.Event()
    instance_id: str | None = None
    engine_error: Exception | None = None
    captured_info: object = None
    captured_runner_stats: dict | None = None

    def _engine_thread():
        """Run the async engine in a background thread.

        Watches stop_event and performs graceful shutdown on its OWN
        event loop (avoids 'Future attached to a different loop').
        """
        nonlocal instance_id, engine_error, captured_info, captured_runner_stats
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            async def _run():
                nonlocal instance_id, captured_info, captured_runner_stats
                instance_id = await manager.start(play, mode=mode)
                instance = manager._instances.get(instance_id)
                if not instance or not instance.task:
                    return

                # Wait for engine task OR stop signal from dashboard
                while not instance.task.done():
                    if stop_event.is_set():
                        captured_info = manager.get(instance_id)
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

    # --- Run dashboard in main thread (blocks until stop_event) ---
    try:
        run_dashboard(
            manager=manager,
            state=dash_state,
            handler=dash_handler,
            stop_event=stop_event,
            refresh_hz=4.0,
        )
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()  # Signal engine thread to shut down
        # Restore loggers in finally so they're recovered even on unexpected errors.
        trade_logger.removeHandler(dash_handler)
        for h in console_handlers:
            trade_logger.addHandler(h)
        for h in root_console_handlers:
            root_logger.addHandler(h)

    # Wait for engine thread to finish (it handles its own stop on its loop)
    engine_thread.join(timeout=20.0)

    # Stop WebSocket bootstrap — LiveRunner.stop() only disconnects the data
    # provider/exchange but leaves the bootstrap daemon threads running, which
    # causes stale-data warnings to leak into the menu prompt.
    try:
        from src.core.application import get_application
        app = get_application()
        if app is not None:
            app.stop_websocket()
    except Exception:
        pass

    # --- Print final summary ---
    if engine_error:
        from src.utils.debug import is_debug_enabled
        if is_debug_enabled():
            import traceback as tb
            console.print(f"\n[red]{mode.upper()} mode error:[/]")
            console.print(f"[red]{tb.format_exception(engine_error)}[/]")
        else:
            console.print(f"\n[red]{mode.upper()} mode error: {engine_error}[/]")
        return 1

    if captured_info:
        console.print(f"\n[green]{mode.upper()} run complete:[/]")
        console.print(f"  Bars: {captured_info.bars_processed}")
        console.print(f"  Signals: {captured_info.signals_generated}")
        if captured_runner_stats:
            fills = captured_runner_stats.get("orders_filled", 0)
            if fills:
                console.print(f"  Fills: {fills}")
    else:
        console.print(f"\n[green]{mode.upper()} run complete.[/]")

    return 0


def handle_play_status(args) -> int:
    """Handle `play status` subcommand - show running instances."""
    from src.engine import EngineManager

    manager = EngineManager.get_instance()
    instances = manager.list_all()

    # Filter by play ID if specified
    play_filter = getattr(args, "play", None)
    if play_filter:
        instances = [i for i in instances if i.play_id == play_filter or i.instance_id == play_filter]

    if not instances:
        if getattr(args, "json_output", False):
            console.print(json.dumps({"instances": []}))
        else:
            console.print("[dim]No running Play instances.[/]")
        return 0

    if getattr(args, "json_output", False):
        data = []
        for info in instances:
            entry = info.to_dict()
            stats = manager.get_runner_stats(info.instance_id)
            if stats:
                entry["stats"] = stats
            data.append(entry)
        console.print(json.dumps({"instances": data}, indent=2))
        return 0

    table = Table(title="Running Play Instances")
    table.add_column("Instance ID", style="cyan")
    table.add_column("Play", style="white")
    table.add_column("Symbol", style="yellow")
    table.add_column("Mode", style="green")
    table.add_column("Status", style="white")
    table.add_column("Bars", justify="right")
    table.add_column("Signals", justify="right")
    table.add_column("Orders", justify="right", style="dim")
    table.add_column("Reconnects", justify="right", style="dim")
    table.add_column("Duration", style="dim")
    table.add_column("Last Candle", style="dim")

    for info in instances:
        stats = manager.get_runner_stats(info.instance_id)
        orders_str = ""
        reconnects_str = ""
        duration_str = ""
        last_candle_str = ""

        if stats:
            submitted = stats.get("orders_submitted", 0)
            filled = stats.get("orders_filled", 0)
            failed = stats.get("orders_failed", 0)
            orders_str = f"{submitted}/{filled}/{failed}"
            reconnects_str = str(stats.get("reconnect_count", 0))
            secs = stats.get("duration_seconds", 0)
            mins, s = divmod(int(secs), 60)
            hrs, m = divmod(mins, 60)
            duration_str = f"{hrs}h{m:02d}m" if hrs else f"{m}m{s:02d}s"
            last_candle_str = stats.get("last_candle_ts", "")[:19] if stats.get("last_candle_ts") else ""

        table.add_row(
            info.instance_id,
            info.play_id,
            info.symbol,
            info.mode.value.upper(),
            info.status,
            str(info.bars_processed),
            str(info.signals_generated),
            orders_str,
            reconnects_str,
            duration_str,
            last_candle_str,
        )

    console.print(table)
    return 0


def handle_play_stop(args) -> int:
    """Handle `play stop` subcommand - stop a running instance.

    Supports both in-process instances (dashboard mode) and cross-process
    instances (headless mode) via PID-based signaling.
    """
    import asyncio
    from src.engine import EngineManager

    manager = EngineManager.get_instance()

    # If --all flag, stop everything (in-process + cross-process)
    if getattr(args, "all", False):
        in_process = manager.list()
        all_instances = manager.list_all()

        if not all_instances:
            console.print("[dim]No running instances to stop.[/]")
            return 0

        # Check for positions if --close-positions
        if getattr(args, "close_positions", False):
            try:
                from src.tools.position_tools import list_open_positions_tool
                result = list_open_positions_tool()
                if result.success and result.data:
                    positions = result.data.get("positions", [])
                    if positions:
                        console.print(f"[yellow]Closing {len(positions)} open position(s) first...[/]")
                        from src.tools.position_tools import panic_close_all_tool
                        close_result = panic_close_all_tool(reason="play stop --all --close-positions")
                        if close_result.success:
                            console.print("[green]All positions closed.[/]")
                        else:
                            console.print(f"[red]Failed to close positions: {close_result.error}[/]")
            except Exception as e:
                console.print(f"[yellow]Could not check positions: {e}[/]")

        # Stop in-process instances via manager
        count = asyncio.run(manager.stop_all())

        # Stop cross-process instances via SIGTERM
        in_process_ids = {i.instance_id for i in in_process}
        for info in all_instances:
            if info.instance_id not in in_process_ids:
                if manager.stop_cross_process(info.instance_id):
                    count += 1

        console.print(f"[green]Stopped {count} instance(s).[/]")
        return 0

    target = getattr(args, "play", None)
    if not target:
        console.print("[red]Specify --play ID or --all to stop instances.[/]")
        return 1

    # Try to find the instance — check in-process first, then cross-process
    in_process = manager.list()
    match = None
    is_cross_process = False
    for info in in_process:
        if info.instance_id == target or info.play_id == target:
            match = info
            break

    if match is None:
        # Check cross-process instances
        all_instances = manager.list_all()
        for info in all_instances:
            if info.instance_id == target or info.play_id == target:
                match = info
                is_cross_process = True
                break

    if match is None:
        console.print(f"[red]No running instance found matching '{target}'.[/]")
        console.print("[dim]Use 'play status' to see running instances.[/]")
        return 1

    # Check for open positions unless --force
    if not getattr(args, "force", False) and not getattr(args, "close_positions", False):
        try:
            from src.tools.position_tools import list_open_positions_tool
            result = list_open_positions_tool(symbol=match.symbol)
            if result.success and result.data:
                positions = result.data.get("positions", [])
                if positions:
                    console.print(f"[yellow]Warning: {len(positions)} open position(s) for {match.symbol}[/]")
                    for pos in positions:
                        side = pos.get("side", "?")
                        size = pos.get("size", "?")
                        pnl = pos.get("unrealized_pnl", "?")
                        console.print(f"  {side} {size} (PnL: {pnl})")
                    console.print("[dim]Use --force to stop anyway, or --close-positions to close first.[/]")
                    return 1
        except Exception:
            pass  # If we can't check positions, proceed with stop

    # Close positions if requested
    if getattr(args, "close_positions", False):
        try:
            from src.tools.position_tools import close_position_tool
            close_result = close_position_tool(symbol=match.symbol)
            if close_result.success:
                console.print(f"[green]Position closed for {match.symbol}.[/]")
            else:
                console.print(f"[yellow]No position to close or close failed: {close_result.error}[/]")
        except Exception as e:
            console.print(f"[yellow]Could not close position: {e}[/]")

    # Stop the instance
    if is_cross_process:
        stopped = manager.stop_cross_process(match.instance_id)
    else:
        stopped = asyncio.run(manager.stop(match.instance_id))

    if stopped:
        console.print(f"[green]Stopped instance: {match.instance_id}[/]")
        return 0
    else:
        console.print(f"[red]Failed to stop instance: {match.instance_id}[/]")
        return 1


def handle_play_watch(args) -> int:
    """Handle `play watch` subcommand - live dashboard for running instances."""
    import time as _time
    from src.engine import EngineManager
    from rich.live import Live

    manager = EngineManager.get_instance()
    interval = getattr(args, "interval", 2.0)
    play_filter = getattr(args, "play", None)

    # --json: single snapshot and exit (agent-friendly)
    if getattr(args, "json_output", False):
        instances = manager.list_all()
        if play_filter:
            instances = [i for i in instances if i.play_id == play_filter or i.instance_id == play_filter]
        data = []
        for info in instances:
            entry = info.to_dict()
            stats = manager.get_runner_stats(info.instance_id)
            if stats:
                entry["stats"] = stats
            data.append(entry)
        console.print(json.dumps({"instances": data}, indent=2))
        return 0

    def _build_display() -> Table:
        """Build the dashboard table."""
        instances = manager.list()
        if play_filter:
            instances = [i for i in instances if i.play_id == play_filter or i.instance_id == play_filter]

        if not instances:
            table = Table(title="Play Watch -- No Running Instances", border_style="dim")
            table.add_column("Info")
            table.add_row("[dim]Waiting for instances... (Ctrl+C to exit)[/]")
            return table

        table = Table(title="Play Watch (live)", border_style="cyan")
        table.add_column("Play", style="cyan")
        table.add_column("Symbol", style="yellow")
        table.add_column("Mode", style="green")
        table.add_column("Status", style="white")
        table.add_column("Bars", justify="right")
        table.add_column("Signals", justify="right")
        table.add_column("Orders (sub/fill/fail)", justify="right", style="dim")
        table.add_column("Reconnects", justify="right")
        table.add_column("Duration", style="dim")
        table.add_column("Last Candle", style="dim")

        for info in instances:
            stats = manager.get_runner_stats(info.instance_id)
            orders_str = ""
            reconnects_str = ""
            duration_str = ""
            last_candle_str = ""

            if stats:
                sub = stats.get("orders_submitted", 0)
                fill = stats.get("orders_filled", 0)
                fail = stats.get("orders_failed", 0)
                orders_str = f"{sub}/{fill}/{fail}"
                reconnects_str = str(stats.get("reconnect_count", 0))
                secs = stats.get("duration_seconds", 0)
                mins, s = divmod(int(secs), 60)
                hrs, m = divmod(mins, 60)
                duration_str = f"{hrs}h{m:02d}m" if hrs else f"{m}m{s:02d}s"
                lc = stats.get("last_candle_ts")
                last_candle_str = lc[:19] if lc else ""

            table.add_row(
                info.play_id,
                info.symbol,
                info.mode.value.upper(),
                info.status,
                str(info.bars_processed),
                str(info.signals_generated),
                orders_str,
                reconnects_str,
                duration_str,
                last_candle_str,
            )

        return table

    console.print("[dim]Press Ctrl+C to exit watch (does not stop the engine)[/]")

    try:
        with Live(_build_display(), console=console, refresh_per_second=1) as live:
            while True:
                _time.sleep(interval)
                live.update(_build_display())
    except KeyboardInterrupt:
        console.print("\n[dim]Watch stopped.[/]")

    return 0


def handle_play_logs(args) -> int:
    """Handle `play logs` subcommand - stream journal/log for an instance."""
    import time as _time

    play_id = args.play
    follow = getattr(args, "follow", False)
    num_lines = getattr(args, "lines", 50)

    # Find journal file
    from src.config.constants import JOURNAL_DIR
    journal_dir = JOURNAL_DIR
    if not journal_dir.exists():
        console.print("[dim]No journal directory found.[/]")
        return 0

    # Find matching journal file
    matches = list(journal_dir.glob(f"*{play_id}*.jsonl"))
    if not matches:
        # Also check instance files to resolve play_id -> instance_id
        from src.config.constants import INSTANCES_DIR
        instances_dir = INSTANCES_DIR
        if instances_dir.exists():
            for path in instances_dir.glob("*.json"):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if data.get("play_id") == play_id:
                        iid = data.get("instance_id", "")
                        matches = list(journal_dir.glob(f"*{iid}*.jsonl"))
                        break
                except Exception:
                    continue

    if not matches:
        console.print(f"[dim]No logs found for '{play_id}'.[/]")
        return 0

    journal_path = matches[0]
    console.print(f"[dim]Reading: {journal_path}[/]")

    # Read last N lines
    try:
        lines = journal_path.read_text(encoding="utf-8").strip().split("\n")
        display_lines = lines[-num_lines:] if len(lines) > num_lines else lines

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
        return 1

    # Follow mode
    if follow:
        console.print("[dim]Following... (Ctrl+C to stop)[/]")
        try:
            with open(journal_path, "r", encoding="utf-8") as f:
                f.seek(0, 2)  # Seek to end
                while True:
                    line = f.readline()
                    if line:
                        try:
                            entry = json.loads(line)
                            ts = entry.get("timestamp", "")[:19]
                            event = entry.get("event", "?")
                            symbol = entry.get("symbol", "")
                            console.print(f"  {ts} [{event}] {symbol} {line.strip()[:80]}")
                        except json.JSONDecodeError:
                            console.print(f"  {line.strip()[:100]}")
                    else:
                        _time.sleep(0.5)
        except KeyboardInterrupt:
            console.print("\n[dim]Stopped following.[/]")

    return 0


def handle_play_pause(args) -> int:
    """Handle `play pause` subcommand."""
    from src.config.constants import INSTANCES_DIR
    play_id = args.play
    pause_dir = INSTANCES_DIR
    pause_dir.mkdir(parents=True, exist_ok=True)

    # Find matching instance
    for path in pause_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("play_id") == play_id or data.get("instance_id") == play_id:
                instance_id = data.get("instance_id", play_id)
                pause_file = pause_dir / f"{instance_id}.pause"
                pause_file.write_text("paused", encoding="utf-8", newline="\n")
                console.print(f"[yellow]Paused: {instance_id}[/]")
                console.print("[dim]Indicators continue updating. Use 'play resume' to resume signal evaluation.[/]")
                return 0
        except Exception:
            continue

    console.print(f"[red]No running instance found matching '{play_id}'.[/]")
    return 1


def handle_play_resume(args) -> int:
    """Handle `play resume` subcommand."""
    from src.config.constants import INSTANCES_DIR
    play_id = args.play
    pause_dir = INSTANCES_DIR

    if not pause_dir.exists():
        console.print(f"[red]No running instance found matching '{play_id}'.[/]")
        return 1

    # Find and remove matching pause file
    for path in pause_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("play_id") == play_id or data.get("instance_id") == play_id:
                instance_id = data.get("instance_id", play_id)
                pause_file = pause_dir / f"{instance_id}.pause"
                if pause_file.exists():
                    pause_file.unlink()
                    console.print(f"[green]Resumed: {instance_id}[/]")
                else:
                    console.print(f"[dim]{instance_id} was not paused.[/]")
                return 0
        except Exception:
            continue

    console.print(f"[red]No running instance found matching '{play_id}'.[/]")
    return 1
