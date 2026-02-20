"""Play YAML tab builder with syntax-aware color coding."""

import re

from rich.text import Text

from src.cli.dashboard.state import DashboardState

# Top-level YAML section keywords
_SECTIONS = {
    "version", "name", "description", "symbol",
    "timeframes", "account", "features", "structures",
    "setups", "actions", "position_policy", "risk_model", "synthetic",
}

# Known value types for coloring
_BOOL_RE = re.compile(r"^\s*(true|false)\s*$", re.IGNORECASE)
_NUM_RE = re.compile(r"^\s*-?[\d.]+\s*$")
_QUOTED_RE = re.compile(r'^\s*["\'].*["\']\s*$')


def _color_line(line: str, section: str) -> Text:
    """Color a single YAML line based on context."""
    t = Text()
    stripped = line.lstrip()
    indent = len(line) - len(stripped)

    # Comments
    if stripped.startswith("#"):
        t.append(line + "\n", style="dim italic")
        return t

    # Empty lines
    if not stripped:
        t.append("\n")
        return t

    # List items: "- something"
    if stripped.startswith("- "):
        t.append(line[:indent], style="")
        t.append("- ", style="dim")
        rest = stripped[2:]
        # List item with key: value
        if ":" in rest and not rest.startswith('"') and not rest.startswith("["):
            key, _, val = rest.partition(":")
            t.append(key, style=_key_style(key, section))
            t.append(":", style="dim")
            _append_value(t, val, section)
        else:
            _append_value(t, rest, section)
        t.append("\n")
        return t

    # Key: value pairs
    if ":" in stripped and not stripped.startswith("{") and not stripped.startswith("["):
        key, _, val = line.partition(":")
        key_name = key.strip()

        # Section headers (top-level, no indent or low indent)
        if key_name in _SECTIONS and indent == 0:
            t.append(key, style="bold magenta")
            t.append(":", style="bold magenta")
        else:
            t.append(line[:indent], style="")
            t.append(key_name, style=_key_style(key_name, section))
            t.append(":", style="dim")

        _append_value(t, val, section)
        t.append("\n")
        return t

    # Block scalar continuation (description text etc)
    t.append(line + "\n", style="white")
    return t


def _key_style(key: str, section: str) -> str:
    """Pick color for a YAML key based on which section we're in."""
    if section == "features":
        if key in ("indicator", "type"):
            return "bold cyan"
        if key == "params":
            return "yellow"
        if key == "tf":
            return "green"
        if key in ("source", "uses", "key"):
            return "yellow"
        return "cyan"
    if section == "structures":
        if key == "type":
            return "bold cyan"
        if key == "key":
            return "cyan"
        if key in ("uses", "params"):
            return "yellow"
        return "cyan"
    if section == "actions":
        if key.startswith("entry_"):
            return "bold green"
        if key.startswith("exit_"):
            return "bold red"
        if key in ("all", "any", "setup"):
            return "yellow"
        return "cyan"
    if section == "risk_model":
        if key in ("stop_loss",):
            return "red"
        if key in ("take_profit",):
            return "green"
        if key in ("type", "value", "pct"):
            return "yellow"
        return "cyan"
    if section == "timeframes":
        if key in ("low_tf", "med_tf", "high_tf", "exec"):
            return "bold cyan"
        return "cyan"
    if section == "account":
        return "cyan"
    return "cyan"


def _append_value(t: Text, val: str, section: str) -> None:
    """Append a YAML value with appropriate coloring."""
    val_stripped = val.strip()
    if not val_stripped or val_stripped == "|":
        t.append(val, style="white")
        return

    # Inline dict/list: { key: val } or [a, b, c]
    if val_stripped.startswith("{") or val_stripped.startswith("["):
        t.append(val, style="yellow")
    # Quoted strings
    elif _QUOTED_RE.match(val_stripped):
        t.append(val, style="green")
    # Booleans
    elif _BOOL_RE.match(val_stripped):
        t.append(val, style="magenta")
    # Numbers
    elif _NUM_RE.match(val_stripped):
        t.append(val, style="white")
    # Condition arrays in actions: ["ema_9", ">", "ema_21"]
    elif val_stripped.startswith("[") or val_stripped.startswith("- ["):
        t.append(val, style="yellow")
    else:
        t.append(val, style="green")


def build_play_text(
    state: DashboardState,
    scroll_offset: int = 0,
    max_lines: int = 40,
) -> Text:
    """Tab 5: Play YAML source with syntax coloring and scroll."""
    t = Text()
    if not state.play_yaml:
        t.append(" Play YAML not available\n", style="dim italic")
        return t

    lines = state.play_yaml.splitlines()
    total = len(lines)

    max_offset = max(0, total - max_lines)
    offset = min(scroll_offset, max_offset)
    visible = lines[offset:offset + max_lines]

    if total > max_lines:
        pos = f"{offset + 1}-{offset + len(visible)}/{total}"
        t.append(f" {pos}  (up/down to scroll)\n", style="dim")

    # Track current top-level section for context-aware coloring
    section = ""
    # Scan from start to determine section at scroll offset
    for line in lines[:offset]:
        stripped = line.lstrip()
        if ":" in stripped and not stripped.startswith("#"):
            key = stripped.partition(":")[0].strip()
            if key in _SECTIONS and (len(line) - len(stripped)) == 0:
                section = key

    for line in visible:
        stripped = line.lstrip()
        # Track section changes
        if ":" in stripped and not stripped.startswith("#"):
            key = stripped.partition(":")[0].strip()
            if key in _SECTIONS and (len(line) - len(stripped)) == 0:
                section = key

        t.append_text(_color_line(line, section))

    return t
