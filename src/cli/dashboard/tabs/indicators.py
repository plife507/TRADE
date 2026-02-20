"""Indicators tab builder."""

import math
import time
from typing import Any

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from src.cli.dashboard.state import DashboardState
from src.cli.dashboard.widgets import _direction_label, _fmt_value, _sparkline


def build_indicators_text(state: DashboardState) -> RenderableType:
    """Tab 2: All indicator values grouped by TF, using Rich Table with sparklines."""
    if not state.indicator_values_by_tf:
        return Text(" No indicator data yet (waiting for warmup...)", style="dim italic")

    tables: list[RenderableType] = []

    # Staleness indicator
    if state._last_engine_data_refresh > 0:
        age = time.monotonic() - state._last_engine_data_refresh
        if age > 5.0:
            tables.append(Text(f" updated {int(age)}s ago", style="yellow"))
        else:
            tables.append(Text(f" updated {age:.0f}s ago", style="dim"))

    has_history = bool(state.indicator_history)

    for tf_label, values in state.indicator_values_by_tf.items():
        # Extract role from label like "low_tf (15m)"
        role = tf_label.split(" ")[0] if " " in tf_label else tf_label

        table = Table(
            title=tf_label,
            title_style="bold cyan",
            show_header=True,
            header_style="dim",
            padding=(0, 1),
            expand=True,
            show_edge=False,
        )
        table.add_column("Name", style="white", ratio=3)
        table.add_column("Value", justify="right", ratio=1)
        if has_history:
            table.add_column("Trend", style="dim", width=10)

        sorted_keys = sorted(values.keys())
        prev_prefix = ""
        for key in sorted_keys:
            val = values[key]
            formatted = _fmt_value(val)

            # Determine display name and style
            if "." in key:
                prefix, sub = key.rsplit(".", 1)
                if prefix != prev_prefix:
                    parent_row = [Text(prefix, style="white"), Text("")]
                    if has_history:
                        parent_row.append(Text(""))
                    table.add_row(*parent_row)
                    prev_prefix = prefix
                name_text = Text(f"  .{sub}", style="dim")
            else:
                prev_prefix = key
                name_text = Text(key, style="white")

            # Value with color hints
            val_style = "white"
            if isinstance(val, (int, float)) and not (math.isnan(val) or math.isinf(val)):
                lower_key = key.lower()
                if any(osc in lower_key for osc in ("rsi", "stoch", "mfi", "willr", "cci")):
                    if val <= 30:
                        val_style = "green"
                    elif val >= 70:
                        val_style = "red"
                if any(d in lower_key for d in ("direction", "bias")):
                    formatted = _direction_label(val)
                    if val > 0:
                        val_style = "green"
                    elif val < 0:
                        val_style = "red"

            row: list[Text | str] = [name_text, Text(formatted, style=val_style)]

            # Sparkline column
            if has_history:
                hist_key = f"{role}.{key}"
                hist = state.indicator_history.get(hist_key)
                spark = _sparkline(list(hist) if hist else None) if hist else ""
                row.append(Text(spark, style="cyan"))

            table.add_row(*row)

        tables.append(table)

    return Group(*tables)
