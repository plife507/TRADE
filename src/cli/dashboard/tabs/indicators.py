"""Indicators tab builder."""

import math
import time
from itertools import zip_longest
from typing import Any

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from src.cli.dashboard.state import DashboardState
from src.cli.dashboard.widgets import _direction_label, _fmt_value


def _style_value(key: str, val: Any) -> tuple[str, str]:
    """Return (formatted_value, style) for an indicator value."""
    formatted = _fmt_value(val)
    val_style = "white"

    if isinstance(val, (int, float)) and not (math.isnan(val) or math.isinf(val)):
        lower_key = key.lower()
        if any(osc in lower_key for osc in ("rsi", "stoch", "mfi", "willr", "cci")):
            if val <= 30:
                val_style = "green"
            elif val >= 70:
                val_style = "red"
        if any(d in lower_key for d in ("direction", "bias", "trend")):
            formatted = _direction_label(val)
            if val > 0:
                val_style = "green"
            elif val < 0:
                val_style = "red"

    return formatted, val_style


def build_indicators_text(
    state: DashboardState,
    scroll_offset: int = 0,
    max_lines: int = 40,
) -> RenderableType:
    """Tab 2: Indicator values in side-by-side TF columns."""
    if not state.indicator_values_by_tf:
        return Text(" No indicator data yet (waiting for warmup...)", style="dim italic")

    parts: list[RenderableType] = []

    # Staleness
    if state._last_engine_data_refresh > 0:
        age = time.monotonic() - state._last_engine_data_refresh
        style = "yellow" if age > 5.0 else "dim"
        parts.append(Text(f" updated {int(age)}s ago", style=style))

    # Collect rows per TF: list of (name, formatted_val, style)
    tf_labels: list[str] = []
    tf_rows: list[list[tuple[str, str, str]]] = []

    for tf_label, values in state.indicator_values_by_tf.items():
        tf_labels.append(tf_label)
        rows: list[tuple[str, str, str]] = []
        for key in sorted(values.keys()):
            val = values[key]
            # Shorten dotted names: "macd_12_26_9.histogram" -> ".histogram"
            display_name = key
            if "." in key:
                _prefix, sub = key.rsplit(".", 1)
                display_name = f".{sub}"
            formatted, val_style = _style_value(key, val)
            rows.append((display_name, formatted, val_style))
        tf_rows.append(rows)

    # Build side-by-side table
    table = Table(
        show_header=True,
        header_style="bold cyan",
        padding=(0, 1),
        expand=False,
        show_edge=False,
    )

    # Add column pair per TF
    for label in tf_labels:
        table.add_column(label, style="white", min_width=20, max_width=25)
        table.add_column("", justify="right", min_width=12, max_width=16)

    # Zip rows across TFs, pad shorter ones
    all_zipped = list(zip_longest(*tf_rows, fillvalue=("", "", "dim")))

    # Apply scroll
    total = len(all_zipped)
    max_offset = max(0, total - max_lines)
    offset = min(scroll_offset, max_offset)
    visible = all_zipped[offset:offset + max_lines]

    if total > max_lines:
        parts.append(Text(f" {offset + 1}-{offset + len(visible)}/{total} (up/down)", style="dim"))

    for row_tuple in visible:
        cells: list[Text | str] = []
        for name, formatted, val_style in row_tuple:
            cells.append(Text(name, style="white" if name else "dim"))
            cells.append(Text(formatted, style=val_style))
        table.add_row(*cells)

    parts.append(table)
    return Group(*parts)
