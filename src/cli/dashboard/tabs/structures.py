"""Structures tab builder."""

import time
from typing import Any

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from src.cli.dashboard.state import DashboardState
from src.cli.dashboard.widgets import _direction_label, _fmt_value


def build_structures_text(state: DashboardState) -> RenderableType:
    """Tab 3: All structure output fields grouped by TF, using Rich Table."""
    if not state.structure_values_by_tf:
        return Text(
            " No structure data yet (waiting for warmup...)", style="dim italic"
        )

    tables: list[RenderableType] = []

    # Staleness indicator
    if state._last_engine_data_refresh > 0:
        age = time.monotonic() - state._last_engine_data_refresh
        if age > 5.0:
            tables.append(Text(f" updated {int(age)}s ago", style="yellow"))
        else:
            tables.append(Text(f" updated {age:.0f}s ago", style="dim"))

    for tf_label, structures in state.structure_values_by_tf.items():
        for struct_key, fields in structures.items():
            table = Table(
                title=f"{tf_label} / {struct_key}",
                title_style="bold cyan",
                show_header=True,
                header_style="dim",
                padding=(0, 1),
                expand=True,
                show_edge=False,
            )
            table.add_column("Field", style="dim", ratio=3)
            table.add_column("Value", justify="right", ratio=2)

            for field_name, val in fields.items():
                formatted = _fmt_value(val)
                val_style = "white"

                lower_field = field_name.lower()
                if lower_field in ("direction", "bias"):
                    formatted = _direction_label(val)
                    if val is not None:
                        if (isinstance(val, (int, float)) and val > 0) or val == "bullish":
                            val_style = "green"
                        elif (isinstance(val, (int, float)) and val < 0) or val == "bearish":
                            val_style = "red"

                elif lower_field == "state":
                    if val == "active":
                        val_style = "green"
                    elif val == "broken":
                        val_style = "red"

                elif lower_field in ("pair_direction", "anchor_direction", "bos_direction", "choch_direction"):
                    if val == "bullish":
                        val_style = "green"
                    elif val == "bearish":
                        val_style = "red"

                elif lower_field in ("bos_this_bar", "choch_this_bar"):
                    if val is True or val == 1:
                        val_style = "bold cyan"
                        formatted = "YES"

                elif "level" in lower_field or lower_field in (
                    "high_level", "low_level", "upper", "lower",
                    "break_level_high", "break_level_low",
                    "anchor_high", "anchor_low",
                ):
                    if isinstance(val, (int, float)) and val > 0:
                        formatted = f"${val:,.2f}" if val >= 1 else _fmt_value(val)

                table.add_row(
                    Text(field_name, style="dim"),
                    Text(formatted, style=val_style),
                )

            tables.append(table)

    return Group(*tables)
