"""
CLI handlers for Shadow Exchange (M4).

Commands:
  shadow run --play X          Single play, foreground (Ctrl+C to stop)
  shadow add --play X          Add play to orchestrator
  shadow remove --instance X   Remove play from orchestrator
  shadow list                  List all shadow plays
  shadow stats --instance X    Show play stats
  shadow stats --all           Show all play stats
"""

from __future__ import annotations

import asyncio
import json
import signal
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from ...utils.logger import get_module_logger

logger = get_module_logger(__name__)
console = Console()


def handle_shadow(args) -> int:
    """Route shadow subcommands."""
    cmd = getattr(args, "shadow_command", None)

    if cmd == "run":
        return _handle_shadow_run(args)
    elif cmd == "add":
        return _handle_shadow_add(args)
    elif cmd == "remove":
        return _handle_shadow_remove(args)
    elif cmd == "list":
        return _handle_shadow_list(args)
    elif cmd == "stats":
        return _handle_shadow_stats(args)
    else:
        console.print("[yellow]Usage: trade_cli.py shadow {run|add|remove|list|stats}[/]")
        return 1


# ── Handlers ────────────────────────────────────────────────────


def _handle_shadow_run(args) -> int:
    """Run a single play in shadow mode (foreground, Ctrl+C to stop).

    This is the simplest entry point — runs one play with real WS data
    and full SimExchange. Useful for testing before adding to the
    multi-play orchestrator.
    """
    play = _load_play(args)
    if play is None:
        return 1

    from ...shadow.config import ShadowPlayConfig
    from ...shadow.engine import ShadowEngine

    config = ShadowPlayConfig(initial_equity_usdt=args.equity)

    engine = ShadowEngine(play=play, play_config=config)
    engine.initialize()

    symbol = play.symbol_universe[0]
    console.print(f"[cyan]Shadow mode: {play.id} on {symbol}[/]")
    console.print(f"[dim]Equity: ${config.initial_equity_usdt:,.0f} | Ctrl+C to stop[/]")

    # Set up WS feed and run
    from ...shadow.feed_hub import SharedFeedHub
    feed_hub = SharedFeedHub()

    try:
        feed_hub.ensure_feed(symbol)
        feed_hub.register_engine(symbol, engine)

        console.print("[green]WebSocket connected. Waiting for candles...[/]")

        # Block until Ctrl+C
        stop_event = asyncio.Event()

        def _on_sigint(sig: int, frame: Any) -> None:
            console.print("\n[yellow]Stopping shadow mode...[/]")
            stop_event.set()

        signal.signal(signal.SIGINT, _on_sigint)

        # Run event loop
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(stop_event.wait())
        finally:
            loop.close()

    except Exception as e:
        console.print(f"[red]Shadow mode error: {e}[/]")
        return 1
    finally:
        stats = engine.stop()
        feed_hub.stop()

    # Print results
    if getattr(args, "json_output", False):
        console.print(json.dumps(stats.to_dict(), indent=2))
    else:
        _print_engine_stats(play.id, symbol, stats)

    return 0


def _handle_shadow_add(args) -> int:
    """Add a play to the shadow orchestrator."""
    console.print("[yellow]Orchestrator daemon not yet implemented.[/]")
    console.print("[dim]Use 'shadow run --play X' for single-play foreground mode.[/]")
    return 1


def _handle_shadow_remove(args) -> int:
    """Remove a play from the shadow orchestrator."""
    console.print("[yellow]Orchestrator daemon not yet implemented.[/]")
    return 1


def _handle_shadow_list(args) -> int:
    """List all shadow plays."""
    console.print("[yellow]Orchestrator daemon not yet implemented.[/]")
    console.print("[dim]Use 'shadow run --play X' for single-play foreground mode.[/]")
    return 1


def _handle_shadow_stats(args) -> int:
    """Show shadow play stats."""
    console.print("[yellow]Orchestrator daemon not yet implemented.[/]")
    return 1


# ── Helpers ─────────────────────────────────────────────────────


def _load_play(args) -> Any:
    """Load a Play from name or path."""
    from ...backtest.play.play import load_play

    play_id = args.play
    plays_dir = Path(args.plays_dir) if getattr(args, "plays_dir", None) else None

    try:
        play = load_play(play_id, base_dir=plays_dir)
        return play
    except Exception as e:
        console.print(f"[red]Failed to load play '{play_id}': {e}[/]")
        return None


def _print_engine_stats(play_id: str, symbol: str, stats: Any) -> None:
    """Print shadow engine stats as a Rich table."""
    table = Table(title=f"Shadow: {play_id} ({symbol})")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Bars processed", str(stats.bars_processed))
    table.add_row("Signals", str(stats.signals_generated))
    table.add_row("Trades opened", str(stats.trades_opened))
    table.add_row("Trades closed", str(stats.trades_closed))
    table.add_row("Win rate", f"{stats.win_rate:.1%}")
    table.add_row("Equity", f"${stats.equity_usdt:,.2f}")
    table.add_row("PnL", f"${stats.cumulative_pnl_usdt:,.2f}")
    table.add_row("Max drawdown", f"{stats.max_drawdown_pct:.1f}%")

    console.print(table)
