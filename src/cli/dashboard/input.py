"""Keyboard input handling for the dashboard."""

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path


LOG_FILTERS = ["info+", "all", "warn+", "error"]
NUM_TABS = 6


@dataclass
class TabState:
    """Shared mutable state between key listener and renderer."""

    current_tab: int = 1
    meta_mode: int = 1  # 0=hidden, 1=compact, 2=full
    log_filter: int = 0  # index into LOG_FILTERS
    scroll_offset: int = 0  # vertical scroll for scrollable tabs
    quit_confirm_pending: bool = False  # True when first 'q' pressed with position


def _toggle_pause(manager: object) -> None:
    """Toggle pause state for the first running instance."""
    instances: dict = getattr(manager, "_instances", {})
    if not instances:
        return

    instance_id = next(iter(instances))
    pause_dir = Path(os.path.expanduser("~/.trade/instances"))
    pause_dir.mkdir(parents=True, exist_ok=True)
    pause_file = pause_dir / f"{instance_id}.pause"

    if pause_file.exists():
        pause_file.unlink()
    else:
        pause_file.write_text("paused", encoding="utf-8", newline="\n")


def _has_open_position(manager: object) -> bool:
    """Check if the first running instance has an open position."""
    instances: dict = getattr(manager, "_instances", {})
    if not instances:
        return False
    inst = next(iter(instances.values()))
    engine = getattr(inst, "engine", None)
    if engine is None:
        return False
    position = getattr(engine, "_position", None)
    return position is not None


SCROLL_STEP = 5


def _tab_prev(tab_state: TabState) -> None:
    """Move to previous tab (wraps around)."""
    tab_state.current_tab = NUM_TABS if tab_state.current_tab == 1 else tab_state.current_tab - 1
    tab_state.scroll_offset = 0


def _tab_next(tab_state: TabState) -> None:
    """Move to next tab (wraps around)."""
    tab_state.current_tab = 1 if tab_state.current_tab == NUM_TABS else tab_state.current_tab + 1
    tab_state.scroll_offset = 0


def _scroll_up(tab_state: TabState) -> None:
    tab_state.scroll_offset = max(0, tab_state.scroll_offset - SCROLL_STEP)


def _scroll_down(tab_state: TabState) -> None:
    tab_state.scroll_offset += SCROLL_STEP


def _handle_quit(
    tab_state: TabState,
    stop_event: threading.Event,
    manager: object,
) -> None:
    """Handle quit key with position confirmation."""
    if tab_state.quit_confirm_pending:
        # Second 'q' — confirmed quit
        tab_state.quit_confirm_pending = False
        stop_event.set()
        return

    if _has_open_position(manager):
        # First 'q' with position — ask for confirmation
        tab_state.quit_confirm_pending = True
    else:
        # No position — immediate quit
        stop_event.set()


def _handle_key(
    ch: str,
    tab_state: TabState,
    stop_event: threading.Event,
    manager: object,
) -> None:
    """Process a single key press."""
    if ch == "q":
        _handle_quit(tab_state, stop_event, manager)
        return

    # Any key other than 'q' cancels quit confirmation
    if tab_state.quit_confirm_pending:
        tab_state.quit_confirm_pending = False

    if ch == "p":
        try:
            _toggle_pause(manager)
        except Exception:
            pass
    elif ch == "m":
        tab_state.meta_mode = (tab_state.meta_mode + 1) % 3
    elif ch == "f":
        tab_state.log_filter = (tab_state.log_filter + 1) % len(LOG_FILTERS)
    elif ch in "123456":
        tab_state.current_tab = int(ch)


# -- Windows arrow key second-byte codes --
_WIN_ARROW_UP = 0x48
_WIN_ARROW_DOWN = 0x50
_WIN_ARROW_LEFT = 0x4B
_WIN_ARROW_RIGHT = 0x4D


def key_listener(
    tab_state: TabState,
    stop_event: threading.Event,
    manager: object,
) -> None:
    """Listen for single keypresses in a background thread.

    Only mutates TabState fields -- no Rich calls, no I/O contention
    with the render loop.
    """
    try:
        import msvcrt  # Windows
        while not stop_event.is_set():
            if msvcrt.kbhit():
                raw = msvcrt.getch()
                # Arrow/function keys: two-byte sequence (\xe0 or \x00 prefix)
                if raw in (b"\xe0", b"\x00"):
                    second = msvcrt.getch() if msvcrt.kbhit() else b""
                    if second:
                        code = second[0]
                        if code == _WIN_ARROW_LEFT:
                            _tab_prev(tab_state)
                        elif code == _WIN_ARROW_RIGHT:
                            _tab_next(tab_state)
                        elif code == _WIN_ARROW_UP:
                            _scroll_up(tab_state)
                        elif code == _WIN_ARROW_DOWN:
                            _scroll_down(tab_state)
                    continue
                ch = raw.decode("utf-8", errors="ignore").lower()
                if not ch:
                    continue
                _handle_key(ch, tab_state, stop_event, manager)
                if stop_event.is_set():
                    return
            else:
                time.sleep(0.02)  # 20ms poll -- responsive without busy-wait
    except ImportError:
        # Unix: use tty/termios
        import select
        import sys
        try:
            import tty  # type: ignore[import-not-found]
            import termios  # type: ignore[import-not-found]
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)  # type: ignore[attr-defined]
            try:
                tty.setraw(fd)  # type: ignore[attr-defined]
                while not stop_event.is_set():
                    rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if rlist:
                        ch = sys.stdin.read(1)
                        # Escape sequences: \x1b [ A/B/C/D (arrows)
                        if ch == "\x1b":
                            # Read the rest of the escape sequence
                            seq = ""
                            while select.select([sys.stdin], [], [], 0.01)[0]:
                                seq += sys.stdin.read(1)
                            if seq == "[D":  # Left arrow
                                _tab_prev(tab_state)
                            elif seq == "[C":  # Right arrow
                                _tab_next(tab_state)
                            elif seq == "[A":  # Up arrow
                                _scroll_up(tab_state)
                            elif seq == "[B":  # Down arrow
                                _scroll_down(tab_state)
                            continue
                        ch = ch.lower()
                        if not ch:
                            continue
                        _handle_key(ch, tab_state, stop_event, manager)
                        if stop_event.is_set():
                            return
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)  # type: ignore[attr-defined]
        except Exception:
            # No keyboard input available; user must Ctrl+C
            while not stop_event.is_set():
                time.sleep(0.5)
