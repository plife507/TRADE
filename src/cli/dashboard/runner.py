"""Dashboard entry point -- Rich Live display with keyboard controls."""

import threading
import time

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from src.cli.dashboard.input import TabState, key_listener
from src.cli.dashboard.log_handler import DashboardLogHandler
from src.cli.dashboard.order_tracker import OrderTracker
from src.cli.dashboard.signal_proximity import evaluate_proximity
from src.cli.dashboard.state import (
    DashboardState,
    refresh_account,
    refresh_engine_data,
    refresh_ticker,
)
from src.cli.dashboard.tabs.indicators import build_indicators_text
from src.cli.dashboard.tabs.log import build_log_text
from src.cli.dashboard.tabs.orders import build_orders_text
from src.cli.dashboard.tabs.overview import build_overview_text
from src.cli.dashboard.tabs.play_yaml import build_play_text
from src.cli.dashboard.tabs.structures import build_structures_text
from src.cli.dashboard.widgets import build_stats_text, build_status_panel, build_tab_bar


def run_dashboard(
    manager: object,
    state: DashboardState,
    handler: DashboardLogHandler,
    stop_event: threading.Event,
    refresh_hz: float = 4.0,
    order_tracker: OrderTracker | None = None,
) -> None:
    """Run the live dashboard until stop_event is set or user quits.

    Full-screen Rich Live display with keyboard controls via msvcrt (Windows)
    or tty/termios (Unix).

    Key input runs in a dedicated thread that never touches Rich rendering,
    ensuring responsiveness even while log/order panels are updating.

    Args:
        manager: EngineManager instance
        state: DashboardState to refresh
        handler: DashboardLogHandler capturing logs
        stop_event: Set this to stop the dashboard loop
        refresh_hz: Refresh rate (default 4 fps)
        order_tracker: Optional OrderTracker for order history panel
    """
    from rich.console import Console
    from rich.live import Live

    console = Console()
    tab_state = TabState()
    tracker = order_tracker or OrderTracker()

    # --- Key listener thread: never acquires Rich locks ---
    key_thread = threading.Thread(
        target=key_listener,
        args=(tab_state, stop_event, manager),
        daemon=True,
        name="dash-keys",
    )
    key_thread.start()

    # --- Tiered data poller: ticker 250ms, account 2s, engine data on bar change ---
    # Intervals in seconds
    TICKER_INTERVAL = 0.25
    ACCOUNT_INTERVAL = 2.0

    def _data_poller() -> None:
        last_ticker = 0.0
        last_account = 0.0
        last_bar_count = 0

        while not stop_event.is_set():
            instances: dict = getattr(manager, "_instances", {})
            if not instances:
                time.sleep(0.05)
                continue

            iid = next(iter(instances))
            now = time.monotonic()

            # Ticker: fast path (250ms)
            if now - last_ticker >= TICKER_INTERVAL:
                try:
                    refresh_ticker(state, manager, iid)
                except Exception:
                    pass
                last_ticker = now

            # Account + runner stats + engine data + signal proximity: slow path (2s)
            if now - last_account >= ACCOUNT_INTERVAL:
                try:
                    refresh_account(state, manager, iid)
                except Exception:
                    pass
                try:
                    refresh_engine_data(state, manager, iid)
                    state._last_engine_data_refresh = time.monotonic()
                except Exception:
                    pass
                try:
                    state.signal_proximity = evaluate_proximity(manager, iid)
                except Exception:
                    pass
                last_account = now

            time.sleep(0.05)  # 50ms base loop

    data_thread = threading.Thread(target=_data_poller, daemon=True, name="dash-data")
    data_thread.start()

    interval = 1.0 / refresh_hz

    # Content height budget: terminal minus status(5) + tab_bar(1) + stats(1) + help(1) + padding(2)
    content_lines = max(10, console.height - 10)

    def _build() -> RenderableType:
        try:
            # Status header (Panel with cyan border)
            status_panel = build_status_panel(state, handler)

            # Tab bar
            tab_bar = build_tab_bar(tab_state.current_tab)

            # Tab content
            tab_content: RenderableType
            if tab_state.current_tab == 1:
                tab_content = build_overview_text(state, tab_state.meta_mode)
            elif tab_state.current_tab == 2:
                tab_content = build_indicators_text(state)
            elif tab_state.current_tab == 3:
                tab_content = build_structures_text(state)
            elif tab_state.current_tab == 4:
                tab_content = build_log_text(handler, max_lines=content_lines, log_filter=tab_state.log_filter)
            elif tab_state.current_tab == 5:
                tab_content = build_play_text(state, max_lines=content_lines, scroll_offset=tab_state.scroll_offset)
            elif tab_state.current_tab == 6:
                tab_content = build_orders_text(tracker, max_lines=content_lines)
            else:
                tab_content = Text("")

            # Wrap tab content in a dim-bordered Panel
            tab_panel = Panel(tab_content, border_style="dim", padding=(0, 0))

            # Stats footer + help line
            stats = build_stats_text(state)
            help_line = Text("[q]uit  [p]ause  [m]eta  [f]ilter  left/right tabs  up/down scroll  [1-6] jump", style="dim")

            parts: list[RenderableType] = [status_panel, tab_bar, tab_panel, stats]

            # Quit confirmation warning
            if tab_state.quit_confirm_pending:
                parts.append(Panel(
                    Text(" Position is open! Press q again to quit, any other key to cancel.", style="bold yellow"),
                    border_style="yellow",
                    padding=(0, 0),
                ))

            parts.append(help_line)
            return Group(*parts)

        except Exception as e:
            return Text(f"\n  Render error: {e}\n", style="bold red")

    try:
        # auto_refresh=False: we drive rendering manually via live.update().
        # This prevents Rich's internal refresh thread from competing with
        # terminal I/O, which was causing key input to freeze on Windows.
        # screen=False: avoids full alternate-screen clear/redraw flicker
        # that causes "shaking" on Windows terminals at higher refresh rates.
        with Live(
            _build(),
            console=console,
            screen=False,
            auto_refresh=False,
            vertical_overflow="crop",
        ) as live:
            while not stop_event.is_set():
                time.sleep(interval)
                live.update(_build(), refresh=True)
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        # Shutdown message
        console.print("[dim]Shutting down engine...[/]")

        # Clean up pause files for all instances
        import os
        from pathlib import Path

        pause_dir = Path(os.path.expanduser("~/.trade/instances"))
        instances: dict = getattr(manager, "_instances", {})
        for iid in instances:
            pause_file = pause_dir / f"{iid}.pause"
            if pause_file.exists():
                try:
                    pause_file.unlink()
                except Exception:
                    pass
