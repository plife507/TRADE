"""Overview tab builder."""

from rich.text import Text

from src.cli.dashboard.state import DashboardState
from src.cli.dashboard.widgets import _fmt_pnl, _pnl_style


def build_overview_text(state: DashboardState, meta_mode: int) -> Text:
    """Tab 1: Play overview with meta, features, actions, stats."""
    t = Text()

    # Play meta
    if meta_mode >= 1:
        if state.position_mode:
            t.append(" Mode: ", style="dim")
            t.append(state.position_mode.replace("_", " "), style="white")
        if state.exit_mode:
            t.append("  Exit: ", style="dim")
            t.append(state.exit_mode.replace("_", " "), style="white")
        if state.sl_summary:
            t.append("  SL: ", style="dim")
            t.append(state.sl_summary, style="red")
        if state.tp_summary:
            t.append("  TP: ", style="dim")
            t.append(state.tp_summary, style="green")
        if state.sizing_summary:
            t.append("  Size: ", style="dim")
            t.append(state.sizing_summary, style="white")
        if state.max_drawdown_pct > 0:
            t.append("  MaxDD: ", style="dim")
            t.append(f"{state.max_drawdown_pct}%", style="red")
        t.append("\n")

        if state.features_summary:
            t.append(" Features: ", style="dim")
            t.append(state.features_summary, style="dim italic")
            t.append("\n")
        if state.actions_summary:
            t.append(" Actions: ", style="dim")
            t.append(state.actions_summary, style="dim italic")
            t.append("\n")

    # Stats
    t.append("\n")
    t.append(" Bars ", style="dim")
    t.append(f"{state.bars_processed}", style="white")
    t.append("  Signals ", style="dim")
    t.append(f"{state.signals_generated}", style="cyan")
    t.append("  Fills ", style="dim")
    t.append(f"{state.orders_filled}", style="white")
    if state.orders_failed:
        t.append("  Failed ", style="dim")
        t.append(f"{state.orders_failed}", style="bold red")
    if state.last_candle_ts:
        t.append("  Last bar ", style="dim")
        t.append(state.last_candle_ts, style="white")
    t.append("\n")

    # Session P&L summary
    if state.orders_filled > 0 or state.realized_pnl != 0:
        t.append("\n Session: ", style="dim")
        t.append(f"{state.orders_filled} trades", style="white")
        t.append("  Net ", style="dim")
        t.append(_fmt_pnl(state.realized_pnl), style=_pnl_style(state.realized_pnl))
        t.append("\n")

    # Errors
    if state.errors:
        t.append("\n Errors:\n", style="bold red")
        for err in state.errors:
            t.append(f"   {err}\n", style="red")

    # Signal proximity
    if state.signal_proximity is not None:
        prox = state.signal_proximity
        if prox.blocks:
            t.append("\n Signal Proximity:\n", style="bold")
            for block in prox.blocks:
                pct = int(block.pass_ratio * 100)
                pct_style = "green" if pct == 100 else "yellow" if pct > 0 else "red"
                t.append(f"  {block.block_id}", style="white")
                t.append(f" [{pct}%]\n", style=pct_style)
                for cond in block.conditions:
                    mark = "+" if cond.passing else "-"
                    cond_style = "green" if cond.passing else "red"
                    t.append(
                        f"    {mark} {cond.lhs_path} {cond.operator} {cond.rhs_repr}\n",
                        style=cond_style,
                    )

    # TF mapping
    if state.tf_mapping:
        t.append("\n Timeframes: ", style="dim")
        parts = []
        for role in ("low_tf", "med_tf", "high_tf"):
            tf = state.tf_mapping.get(role, "?")
            parts.append(f"{role}={tf}")
        t.append("  ".join(parts), style="white")
        exec_role = state.tf_mapping.get("exec", "")
        if exec_role:
            t.append(f"  exec -> {exec_role}", style="cyan")
        t.append("\n")

    return t
