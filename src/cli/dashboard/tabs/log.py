"""Log tab builder."""

from src.cli.dashboard.input import LOG_FILTERS

from rich.console import Group, RenderableType
from rich.text import Text

from src.cli.dashboard.log_handler import DashboardLogHandler


def _filter_lines(lines: list[str], log_filter: int) -> list[str]:
    """Apply severity filter to log lines."""
    label = LOG_FILTERS[log_filter] if log_filter < len(LOG_FILTERS) else "info+"

    if label == "all":
        return lines
    if label == "info+":
        # Exclude DEBUG lines
        return [l for l in lines if "[DEBUG]" not in l]
    if label == "warn+":
        return [l for l in lines if any(
            kw in l.upper() for kw in ("WARNING", "WARN", "ERROR", "CRITICAL")
        )]
    if label == "error":
        return [l for l in lines if any(
            kw in l.upper() for kw in ("ERROR", "CRITICAL")
        )]
    return lines


def build_log_text(
    handler: DashboardLogHandler,
    max_lines: int = 40,
    log_filter: int = 0,
) -> RenderableType:
    """Tab 4: Scrolling log output with severity filter.

    Args:
        handler: Log handler with buffered lines.
        max_lines: Max visible lines.
        log_filter: Index into LOG_FILTERS.
    """
    lines = handler.get_lines()
    lines = _filter_lines(lines, log_filter)
    visible = lines[-max_lines:]

    label = LOG_FILTERS[log_filter] if log_filter < len(LOG_FILTERS) else "?"
    header = Text(f" Filter: [{label}]  (press f to cycle)", style="dim")

    if not visible:
        return Group(header, Text(" No log output yet...", style="dim italic"))

    t = Text()
    for line in visible:
        upper = line.upper()
        if "ERROR" in upper or "CRITICAL" in upper:
            style = "bold red"
        elif "WARNING" in upper or "WARN" in upper:
            style = "yellow"
        elif any(kw in upper for kw in ("FILLED", "ORDER", "ENTRY", "EXIT")):
            style = "bold cyan"
        elif "SIGNAL" in upper:
            style = "cyan"
        elif "BAR #" in upper:
            style = "white"
        else:
            style = "dim"
        t.append(line + "\n", style=style)

    return Group(header, t)
