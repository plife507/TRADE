"""Orders tab builder."""

import time

from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from src.cli.dashboard.order_tracker import OrderTracker


def build_orders_text(
    tracker: OrderTracker,
    scroll_offset: int = 0,
    max_lines: int = 40,
) -> RenderableType:
    """Tab 6: Order status and history, using Rich Table."""
    # Summary line
    submitted, filled, failed = tracker.get_summary()
    summary = Text()
    summary.append(" Orders: ", style="dim")
    summary.append(f"{submitted} submitted", style="white")
    summary.append("  ")
    summary.append(f"{filled} filled", style="green")
    summary.append("  ")
    if failed > 0:
        summary.append(f"{failed} failed", style="bold red")
    else:
        summary.append("0 failed", style="dim")

    events = tracker.get_events(n=200)
    if not events:
        return Group(summary, Text(" No order events yet...", style="dim italic"))

    total = len(events)
    max_offset = max(0, total - max_lines)
    offset = min(scroll_offset, max_offset)
    visible = events[offset:offset + max_lines]

    # Scroll indicator
    if total > max_lines:
        summary.append(f"  {offset + 1}-{offset + len(visible)}/{total} (up/down)", style="dim")

    table = Table(
        show_header=True,
        header_style="dim",
        padding=(0, 1),
        expand=True,
        show_edge=False,
    )
    table.add_column("Time", style="white", width=8)
    table.add_column("Dir", width=5)
    table.add_column("Type", style="dim", width=7)
    table.add_column("Status", width=8)
    table.add_column("Size", justify="right", width=10)
    table.add_column("Price", justify="right", width=12)
    table.add_column("Order ID", style="dim", width=13)

    for event in visible:
        ts_str = time.strftime("%H:%M:%S", time.localtime(event.timestamp))

        # Direction
        if event.direction == "LONG":
            dir_text = Text("LONG", style="green")
        elif event.direction == "SHORT":
            dir_text = Text("SHORT", style="red")
        elif event.direction == "FLAT":
            dir_text = Text("CLOSE", style="yellow")
        else:
            dir_text = Text(event.direction, style="dim")

        # Status
        status_styles = {
            "filled": ("FILLED", "bold green"),
            "failed": ("FAILED", "bold red"),
            "rejected": ("REJECTED", "bold yellow"),
            "pending": ("PENDING", "cyan"),
            "submitted": ("PENDING", "cyan"),
        }
        label, style = status_styles.get(event.status, (event.status, "dim"))
        status_text = Text(label, style=style)

        # Size
        size_str = f"${event.size_usdt:,.2f}" if event.size_usdt > 0 else "--"

        # Price
        if event.fill_price and event.fill_price > 0:
            price_str = f"${event.fill_price:,.2f}"
        else:
            price_str = "--"

        # Order ID
        oid = event.order_id[:13] if event.order_id else "--"

        table.add_row(ts_str, dir_text, event.order_type, status_text, size_str, price_str, oid)

        # Error detail as sub-row
        if event.error:
            error_display = event.error[:70]
            table.add_row("", Text(error_display, style="red"), "", "", "", "", "")

    return Group(summary, table)
