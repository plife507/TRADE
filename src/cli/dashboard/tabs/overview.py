"""Overview tab builder."""

from rich.text import Text

from src.cli.dashboard.state import DashboardState
from src.cli.dashboard.widgets import _fmt_pnl, _pnl_style


def build_overview_text(
    state: DashboardState,
    meta_mode: int,
    scroll_offset: int = 0,
    max_lines: int = 40,
) -> Text:
    """Tab 1: Play overview — clean sectioned layout with scroll."""
    t = Text()

    if meta_mode == 0:
        # Hidden meta, just show stats
        _append_stats(t, state)
        return t

    # --- Risk ---
    t.append(" Risk  ", style="bold")
    if state.position_mode:
        t.append(state.position_mode.replace("_", " "), style="white")
    if state.exit_mode:
        t.append(f"  exit={state.exit_mode.replace('_', ' ')}", style="dim")
    t.append("\n")

    if state.sl_summary or state.tp_summary:
        t.append("   SL ", style="dim")
        t.append(state.sl_summary or "--", style="red")
        t.append("   TP ", style="dim")
        t.append(state.tp_summary or "--", style="green")
        if state.sizing_summary:
            t.append("   ", style="dim")
            t.append(state.sizing_summary, style="white")
        if state.max_drawdown_pct > 0:
            t.append(f"   MaxDD {state.max_drawdown_pct}%", style="red")
        t.append("\n")

    # --- Timeframes ---
    if state.tf_mapping:
        t.append("\n Timeframes  ", style="bold")
        for role in ("low_tf", "med_tf", "high_tf"):
            tf = state.tf_mapping.get(role, "?")
            t.append(f"{role}=", style="dim")
            t.append(tf, style="white")
            t.append("  ", style="dim")
        exec_role = state.tf_mapping.get("exec", "")
        if exec_role:
            t.append(f"exec->", style="dim")
            t.append(exec_role, style="cyan")
        t.append("\n")

    # --- Indicators by TF ---
    if state.feature_decls:
        t.append("\n Indicators\n", style="bold")
        # Group by TF
        by_tf: dict[str, list[str]] = {}
        for name, ind, tf, _params in state.feature_decls:
            key = tf or "exec"
            by_tf.setdefault(key, []).append(name or ind)

        for tf_key in sorted(by_tf.keys()):
            t.append(f"   {tf_key}: ", style="dim")
            t.append(", ".join(by_tf[tf_key]), style="white")
            t.append("\n")

    # --- Structures by TF ---
    if state.structure_decls:
        t.append("\n Structures\n", style="bold")
        by_tf_s: dict[str, list[str]] = {}
        for key, stype, tf_role in state.structure_decls:
            by_tf_s.setdefault(tf_role, []).append(f"{key}({stype})")

        for tf_key in sorted(by_tf_s.keys()):
            t.append(f"   {tf_key}: ", style="dim")
            t.append(", ".join(by_tf_s[tf_key]), style="white")
            t.append("\n")

    # --- Actions ---
    if state.actions_summary:
        t.append("\n Actions  ", style="bold")
        t.append(state.actions_summary, style="cyan")
        t.append("\n")

    # --- Stats ---
    _append_stats(t, state)

    # --- Signal proximity ---
    if state.signal_proximity is not None:
        prox = state.signal_proximity
        if prox.blocks:
            t.append("\n Signal Proximity\n", style="bold")
            for block in prox.blocks:
                pct = int(block.pass_ratio * 100)
                pct_style = "green" if pct == 100 else "yellow" if pct > 0 else "red"
                t.append(f"   {block.block_id}", style="white")
                t.append(f" [{pct}%]\n", style=pct_style)
                for cond in block.conditions:
                    mark = "+" if cond.passing else "-"
                    cond_style = "green" if cond.passing else "red"
                    t.append(f"     {mark} {cond.lhs_path} {cond.operator} {cond.rhs_repr}\n", style=cond_style)

    # --- Errors ---
    if state.errors:
        t.append("\n Errors\n", style="bold red")
        for err in state.errors:
            t.append(f"   {err}\n", style="red")

    # Apply scroll
    lines = t.plain.splitlines()
    total = len(lines)
    if total > max_lines and scroll_offset > 0:
        max_offset = max(0, total - max_lines)
        off = min(scroll_offset, max_offset)
        # Rebuild as sliced text (plain — overview is simple enough)
        sliced = Text()
        sliced.append(f" {off + 1}-{off + max_lines}/{total} (up/down)\n", style="dim")
        for line in lines[off:off + max_lines]:
            sliced.append(line + "\n")
        return sliced

    return t


def _append_stats(t: Text, state: DashboardState) -> None:
    """Append stats section."""
    t.append("\n Stats  ", style="bold")
    t.append(f"{state.bars_processed}", style="white")
    t.append(" bars  ", style="dim")
    t.append(f"{state.signals_generated}", style="cyan")
    t.append(" signals  ", style="dim")
    t.append(f"{state.orders_filled}", style="white")
    t.append(" fills", style="dim")
    if state.orders_failed:
        t.append(f"  {state.orders_failed}", style="bold red")
        t.append(" failed", style="dim")
    if state.last_candle_ts:
        t.append(f"  last={state.last_candle_ts}", style="dim")
    t.append("\n")

    if state.orders_filled > 0 or state.realized_pnl != 0:
        t.append("   Session: ", style="dim")
        t.append(f"{state.orders_filled} trades", style="white")
        t.append("  net ", style="dim")
        t.append(_fmt_pnl(state.realized_pnl), style=_pnl_style(state.realized_pnl))
        t.append("\n")
