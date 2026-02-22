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
    scroll_offset: int = 0,
) -> RenderableType:
    """Tab 4: Scrolling log output with severity filter and scroll support."""
    raw_lines = handler.get_lines()
    lines = _filter_lines(raw_lines, log_filter)

    total = len(lines)
    label = LOG_FILTERS[log_filter] if log_filter < len(LOG_FILTERS) else "?"

    header = Text()
    header.append(f" Filter: [{label}]", style="dim")

    if not lines:
        header.append("  (f to cycle)", style="dim")
        if raw_lines:
            return Group(header, Text(f" No lines match filter [{label}]", style="dim italic"))
        return Group(header, Text(" No log output yet...", style="dim italic"))

    # Scroll: default to bottom (newest logs), scroll_offset moves up from bottom
    # offset=0 means "show the last max_lines" (tail behavior / auto-scroll)
    # offset>0 means "scrolled up N lines from the bottom" (frozen view)
    # Clamp offset to prevent empty display after filter narrows results
    clamped_offset = min(scroll_offset, max(0, total - 1))
    end = total - clamped_offset
    start = max(0, end - max_lines)
    visible = lines[start:end]

    if clamped_offset == 0:
        header.append("  LIVE", style="bold green")
    else:
        header.append(f"  {start + 1}-{end}/{total}", style="dim")
        header.append("  (down=newer, up=older)", style="dim")

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
