"""Structures tab builder."""

import time
from itertools import zip_longest
from typing import Any

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from src.cli.dashboard.state import DashboardState
from src.cli.dashboard.widgets import _direction_label, _fmt_value

# Key fields to show per structure type (everything else hidden)
_KEY_FIELDS: dict[str, list[str]] = {
    "swing": [
        "high_level", "low_level", "pair_direction", "version",
    ],
    "trend": [
        "direction", "strength", "bars_in_trend", "wave_count",
    ],
    "market_structure": [
        "bias", "bos_this_bar", "choch_this_bar",
        "bos_direction", "choch_direction",
    ],
    "fibonacci": [
        "anchor_high", "anchor_low", "anchor_direction", "range",
        "level_0.382", "level_0.5", "level_0.618", "level_0.786",
    ],
    "zone": [
        "state", "upper", "lower",
    ],
    "rolling_window": [
        "value",
    ],
    "derived_zone": [
        "active_count", "any_active",
        "first_active_lower", "first_active_upper",
    ],
}


def _style_value(field_name: str, val: Any) -> tuple[str, str]:
    """Return (formatted_value, style) for a structure field."""
    formatted = _fmt_value(val)
    val_style = "white"

    lower = field_name.lower()
    if lower in ("direction", "bias", "trend"):
        formatted = _direction_label(val)
        if val is not None:
            if (isinstance(val, (int, float)) and val > 0) or val == "bullish":
                val_style = "green"
            elif (isinstance(val, (int, float)) and val < 0) or val == "bearish":
                val_style = "red"
    elif lower == "state":
        val_style = "green" if val == "active" else "red" if val == "broken" else "white"
    elif lower in ("pair_direction", "anchor_direction", "bos_direction", "choch_direction"):
        val_style = "green" if val == "bullish" else "red" if val == "bearish" else "white"
    elif lower in ("bos_this_bar", "choch_this_bar"):
        if val is True or val == 1:
            val_style = "bold cyan"
            formatted = "YES"
    elif "level" in lower or lower in ("upper", "lower", "high_level", "low_level"):
        if isinstance(val, (int, float)) and val > 0:
            formatted = f"${val:,.2f}" if val >= 1 else _fmt_value(val)

    return formatted, val_style


def build_structures_text(
    state: DashboardState,
    scroll_offset: int = 0,
    max_lines: int = 40,
) -> RenderableType:
    """Tab 3: Structure fields grouped by type, TFs side-by-side, key fields only."""
    if not state.structure_values_by_tf:
        return Text(
            " No structure data yet (waiting for warmup...)", style="dim italic"
        )

    parts: list[RenderableType] = []

    # Staleness
    if state._last_engine_data_refresh > 0:
        age = time.monotonic() - state._last_engine_data_refresh
        style = "yellow" if age > 5.0 else "dim"
        parts.append(Text(f" updated {int(age)}s ago", style=style))

    # Build type lookup from structure_decls: key -> type
    key_to_type: dict[str, str] = {}
    for key, stype, _tf_role in state.structure_decls:
        key_to_type[key] = stype

    # Group structures by type across all TFs
    # type -> [(tf_label, struct_key, fields)]
    by_type: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for tf_label, structures in state.structure_values_by_tf.items():
        for struct_key, fields in structures.items():
            stype = key_to_type.get(struct_key, struct_key)
            by_type.setdefault(stype, []).append((tf_label, struct_key, fields))

    # Build rows for scrolling
    all_tables: list[Table] = []

    for stype, entries in by_type.items():
        # Determine which fields to show
        show_fields = _KEY_FIELDS.get(stype)

        # Collect per-TF rows: filter to key fields
        tf_columns: list[tuple[str, list[tuple[str, str, str]]]] = []
        for tf_label, struct_key, fields in entries:
            col_label = f"{tf_label}"
            rows: list[tuple[str, str, str]] = []
            field_items = list(fields.items())
            for field_name, val in field_items:
                if show_fields is not None and field_name not in show_fields:
                    continue
                formatted, val_style = _style_value(field_name, val)
                rows.append((field_name, formatted, val_style))
            tf_columns.append((col_label, rows))

        if not tf_columns:
            continue

        # Build table with TF column pairs
        table = Table(
            title=stype,
            title_style="bold white",
            show_header=True,
            header_style="bold cyan",
            padding=(0, 1),
            expand=False,
            show_edge=False,
        )
        for col_label, _rows in tf_columns:
            table.add_column(col_label, style="dim", min_width=18, max_width=22)
            table.add_column("", justify="right", min_width=12, max_width=16)

        # Zip rows across TFs
        row_lists = [rows for _, rows in tf_columns]
        for zipped in zip_longest(*row_lists, fillvalue=("", "", "dim")):
            cells: list[Text | str] = []
            for field_name, formatted, val_style in zipped:
                cells.append(Text(field_name, style="dim" if field_name else ""))
                cells.append(Text(formatted, style=val_style))
            table.add_row(*cells)

        all_tables.append(table)

    # Flatten for scroll counting (count table rows)
    total_rows = sum(t.row_count + 3 for t in all_tables)  # +3 for title/header/separator
    if total_rows > max_lines:
        parts.append(Text(f" ~{total_rows} rows (up/down to scroll)", style="dim"))

    # For now show all tables (scroll handled by panel crop)
    # Fine-grained row-level scroll across multiple tables is complex;
    # the panel-level crop + scroll offset handles most cases
    parts.extend(all_tables)

    return Group(*parts)
