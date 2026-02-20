"""Formatting helpers and status/tab bar builders for the dashboard."""

import math
import re
import time
from typing import Any

from rich.panel import Panel
from rich.text import Text

from src.cli.dashboard.log_handler import DashboardLogHandler
from src.cli.dashboard.state import DashboardState


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _pnl_style(value: float) -> str:
    if value > 0:
        return "bold green"
    if value < 0:
        return "bold red"
    return "dim"


def _fmt_price(v: float | None) -> str:
    if v is None or v == 0.0:
        return "--"
    return f"${v:,.2f}"


def _fmt_pnl(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}${v:,.2f}"


def _fmt_uptime(secs: float) -> str:
    total = int(secs)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


def _fmt_compact(v: float) -> str:
    """Format large numbers compactly (1.2M, 45.3K)."""
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.1f}K"
    return f"{v:,.0f}"


def _fmt_value(v: Any) -> str:
    """Smart-format an indicator/structure value for display."""
    if v is None:
        return "--"
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return "--"
        if abs(v) >= 1000:
            return f"{v:,.2f}"
        if abs(v) >= 1:
            return f"{v:.4g}"
        if abs(v) >= 0.0001:
            return f"{v:.6g}"
        return f"{v:.2e}"
    return str(v)


_TF_SECONDS: dict[str, int] = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
    "12h": 43200, "D": 86400, "1D": 86400, "W": 604800, "1W": 604800,
}


def _tf_to_seconds(tf: str) -> int:
    """Convert a timeframe string to seconds. Returns 0 for unknown."""
    return _TF_SECONDS.get(tf, 0)


def _fmt_eta(remaining_bars: int, tf: str) -> str:
    """Format warmup ETA from remaining bars and timeframe."""
    secs = remaining_bars * _tf_to_seconds(tf)
    if secs <= 0:
        return ""
    if secs >= 3600:
        return f"~{secs // 3600}h{(secs % 3600) // 60:02d}m"
    if secs >= 60:
        return f"~{secs // 60}m"
    return f"~{secs}s"


_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(values: list[float] | None, width: int = 10) -> str:
    """Render a Unicode sparkline from the last *width* values."""
    if not values or len(values) < 2:
        return ""
    recent = list(values)[-width:]
    lo, hi = min(recent), max(recent)
    span = hi - lo
    if span == 0:
        return _SPARK_CHARS[3] * len(recent)
    return "".join(
        _SPARK_CHARS[min(7, int((v - lo) / span * 7))] for v in recent
    )


def _direction_label(v: Any) -> str:
    """Human label for direction/bias integer values."""
    if v == 1:
        return "1 (UP)"
    if v == -1:
        return "-1 (DOWN)"
    if v == 0:
        return "0 (FLAT)"
    return str(v)


# ---------------------------------------------------------------------------
# Status badge
# ---------------------------------------------------------------------------


def _state_badge(state: DashboardState) -> Text:
    """Composite status badge from runner state + engine phase."""
    rs = state.runner_state
    ep = state.engine_phase
    t = Text()

    badge = ""
    hint = ""
    badge_style = "dim"

    if rs == "ERROR" or ep == "ERROR":
        badge, badge_style = " ERROR ", "bold white on red"
        hint = "engine encountered an error"
    elif state.is_paused:
        badge, badge_style = " PAUSED ", "bold black on yellow"
        hint = "signal evaluation paused, indicators still updating"
    elif rs == "RECONNECTING":
        badge, badge_style = " RECONNECTING ", "bold white on red"
        hint = "lost connection, attempting to reconnect"
    elif rs == "STOPPING":
        badge, badge_style = " SHUTTING DOWN ", "bold white on yellow"
        hint = "engine is stopping gracefully"
    elif rs == "STOPPED":
        badge, badge_style = " STOPPED ", "bold white on rgb(80,80,80)"
        hint = "engine has stopped"
    elif rs == "STARTING":
        badge, badge_style = " STARTING ", "bold black on cyan"
        hint = "connecting to exchange"
    elif rs == "RUNNING" and state.bars_processed > 0:
        badge, badge_style = " RUNNING ", "bold white on green"
        hint = "live, evaluating signals each bar"
    elif rs == "RUNNING" and state.bars_processed == 0:
        if state.warmup_target > 0 and state.warmup_bars < state.warmup_target:
            pct = int(state.warmup_bars / state.warmup_target * 100)
            remaining = state.warmup_target - state.warmup_bars
            eta = _fmt_eta(remaining, state.exec_tf) if remaining > 0 else ""
            eta_str = f" {eta}" if eta else ""
            badge, badge_style = f" WARMING UP {pct}%{eta_str} ", "bold black on cyan"
            hint = "computing indicators from historical data"
        else:
            badge, badge_style = " READY ", "bold white on green"
            hint = f"indicators loaded, waiting for next {state.exec_tf} candle close"
    elif ep in ("CREATED", "WARMING"):
        if state.warmup_target > 0:
            pct = min(100, int(state.warmup_bars / max(state.warmup_target, 1) * 100))
            badge, badge_style = f" WARMING UP {pct}% ", "bold black on cyan"
            hint = "loading historical data for indicators"
        else:
            badge, badge_style = " WARMING UP ", "bold black on cyan"
            hint = "loading historical data"
    else:
        badge, badge_style = f" {rs} ", "dim"

    t.append(badge, style=badge_style)
    if hint:
        t.append(f"  {hint}", style="dim italic")

    return t


# ---------------------------------------------------------------------------
# Status header (always visible)
# ---------------------------------------------------------------------------


def build_status_panel(state: DashboardState, handler: DashboardLogHandler) -> Panel:
    """Always-visible top section wrapped in a cyan-bordered Panel."""
    t = Text()

    # Line 1: Identity
    t.append(f" {state.play_name}", style="bold cyan")
    t.append(f"  {state.symbol}", style="bold yellow")
    t.append(f"  {state.exec_tf}  {state.leverage}x", style="white")
    mode_style = "bold green" if state.mode == "DEMO" else "bold red"
    t.append(f"  {state.mode}", style=mode_style)
    t.append("  ")
    t.append_text(_state_badge(state))
    if state.uptime_seconds > 0:
        t.append(f"  {_fmt_uptime(state.uptime_seconds)}", style="dim")
    t.append("\n")

    # Line 2: Account
    t.append(" Equity ", style="dim")
    t.append(_fmt_price(state.equity), style="bold white")
    t.append("  Bal ", style="dim")
    t.append(_fmt_price(state.balance), style="white")
    t.append("  uPnL ", style="dim")
    t.append(_fmt_pnl(state.unrealized_pnl), style=_pnl_style(state.unrealized_pnl))
    if state.equity > 0 and state.unrealized_pnl != 0:
        pct = state.unrealized_pnl / state.equity * 100
        t.append(f" ({pct:+.2f}%)", style=_pnl_style(state.unrealized_pnl))
    t.append("  rPnL ", style="dim")
    t.append(_fmt_pnl(state.realized_pnl), style=_pnl_style(state.realized_pnl))
    t.append("\n")

    # Line 3: Position
    if state.has_position:
        side_style = "bold green" if state.side == "LONG" else "bold red"
        t.append(f" {state.side}", style=side_style)
        t.append(f" {state.size_qty:.4f}", style="white")
        t.append(f" @ {_fmt_price(state.entry_price)}", style="white")
        t.append("  Mark ", style="dim")
        t.append(_fmt_price(state.mark_price), style="white")
        if state.stop_loss:
            t.append("  SL ", style="dim")
            t.append(_fmt_price(state.stop_loss), style="red")
        if state.take_profit:
            t.append("  TP ", style="dim")
            t.append(_fmt_price(state.take_profit), style="green")
        if state.liq_price and state.liq_price > 0:
            t.append("  Liq ", style="dim")
            t.append(_fmt_price(state.liq_price), style="bold red")
            if state.mark_price > 0:
                liq_dist = abs(state.mark_price - state.liq_price) / state.mark_price * 100
                t.append(f" ({liq_dist:.1f}%)", style="dim")
        # R-multiple
        if state.risk_per_trade > 0 and state.unrealized_pnl != 0:
            r_mult = state.unrealized_pnl / state.risk_per_trade
            r_style = "green" if r_mult > 0 else "red"
            t.append(f"  ({r_mult:+.1f}R)", style=r_style)
        # Time in trade
        if state.position_opened_at > 0:
            import time as _time
            trade_secs = _time.monotonic() - state.position_opened_at
            t.append(f"  {_fmt_uptime(trade_secs)}", style="dim")
    else:
        t.append(" FLAT", style="dim")
    t.append("\n")

    # Line 4: Market
    if state.last_price > 0:
        stale = " (stale)" if state.ticker_stale else ""
        t.append(" Price ", style="dim")
        t.append(f"${state.last_price:,.2f}{stale}", style="bold white")
        if state.bid_price > 0 and state.ask_price > 0:
            spread = state.ask_price - state.bid_price
            t.append(f"  B/A ", style="dim")
            t.append(f"{state.bid_price:,.2f}/{state.ask_price:,.2f}", style="white")
            t.append(f"  Spd ${spread:,.3f}", style="dim")
        if state.price_change_24h != 0:
            sign = "+" if state.price_change_24h >= 0 else ""
            t.append(f"  24h ", style="dim")
            t.append(
                f"{sign}{state.price_change_24h:.2f}%",
                style=_pnl_style(state.price_change_24h),
            )
        if state.volume_24h > 0:
            t.append(f"  Vol ", style="dim")
            t.append(_fmt_compact(state.volume_24h), style="dim")
        if state.funding_rate != 0:
            fr_style = "green" if state.funding_rate > 0 else "red"
            t.append(f"  FR ", style="dim")
            t.append(f"{state.funding_rate:.4f}%", style=fr_style)
    else:
        t.append(" Price  --  (waiting for ticker...)", style="dim italic")
    t.append("\n")

    # Line 5: Last action
    action = handler.get_last_action()
    if action:
        ts, msg = action
        age = time.time() - ts
        cleaned = re.sub(r"^\d{2}:\d{2}:\d{2}\s*\[?\w+\]?\s*", "", msg).strip()
        if age < 5.0:
            style = "bold cyan"
        elif age < 30.0:
            style = "cyan"
        else:
            style = "dim"
        t.append(f" >> {cleaned}", style=style)
        if age > 60.0:
            t.append(f"  ({int(age)}s ago)", style="dim")
    else:
        t.append(" Waiting for signals...", style="dim italic")

    return Panel(t, border_style="cyan", padding=(0, 0))


# ---------------------------------------------------------------------------
# Tab bar
# ---------------------------------------------------------------------------


def build_tab_bar(current_tab: int) -> Text:
    """Tab indicator line."""
    t = Text()
    tabs = ["Overview", "Indicators", "Structures", "Log", "Play", "Orders"]
    for i, name in enumerate(tabs):
        num = i + 1
        if num == current_tab:
            t.append(f" [{num}]{name} ", style="bold white on rgb(40,40,80)")
        else:
            t.append(f" [{num}]{name} ", style="dim")
    return t


# ---------------------------------------------------------------------------
# Stats footer
# ---------------------------------------------------------------------------


def build_stats_text(state: DashboardState) -> Text:
    """Bottom stats bar."""
    t = Text()
    t.append(" Bars ", style="dim")
    t.append(f"{state.bars_processed}", style="white")
    t.append("  Sig ", style="dim")
    t.append(f"{state.signals_generated}", style="cyan")
    t.append("  Fills ", style="dim")
    t.append(f"{state.orders_filled}", style="white")
    if state.orders_failed:
        t.append("  Err ", style="dim")
        t.append(f"{state.orders_failed}", style="bold red")
    t.append("  Up ", style="dim")
    t.append(_fmt_uptime(state.uptime_seconds), style="white")
    if state.last_candle_ts:
        t.append(f"  Last {state.last_candle_ts}", style="dim")
    return t
