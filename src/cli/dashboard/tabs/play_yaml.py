"""Play YAML tab builder."""

from rich.text import Text

from src.cli.dashboard.state import DashboardState


def build_play_text(state: DashboardState, max_lines: int = 40, scroll_offset: int = 0) -> Text:
    """Tab 5: Play YAML source with scroll support."""
    t = Text()
    if not state.play_yaml:
        t.append(" Play YAML not available\n", style="dim italic")
        return t

    lines = state.play_yaml.splitlines()
    total = len(lines)

    # Clamp scroll offset
    max_offset = max(0, total - max_lines)
    offset = min(scroll_offset, max_offset)

    visible = lines[offset:offset + max_lines]

    # Scroll indicator
    if total > max_lines:
        pos = f"{offset + 1}-{offset + len(visible)}/{total}"
        t.append(f" {pos}  (up/down arrows to scroll)\n", style="dim")

    for line in visible:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            t.append(line + "\n", style="dim italic")
        elif ":" in line:
            key, _, val = line.partition(":")
            t.append(key + ":", style="cyan")
            t.append(val + "\n", style="white")
        else:
            t.append(line + "\n", style="white")

    return t
