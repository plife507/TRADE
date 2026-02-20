"""Dashboard log capture handler."""

import logging
import re
import threading
import time
from collections import deque


class DashboardLogHandler(logging.Handler):
    """Captures formatted log records into a thread-safe ring buffer."""

    _ACTION_PATTERNS = re.compile(
        r"(Order filled|Exit filled|Exit signal|Signal|ENTRY|EXIT|"
        r"order.*filled|position.*opened|position.*closed)",
        re.IGNORECASE,
    )

    def __init__(self, max_lines: int = 50, max_actions: int = 10) -> None:
        super().__init__()
        self.setLevel(logging.DEBUG)
        self._buffer: deque[str] = deque(maxlen=max_lines)
        self._actions: deque[tuple[float, str]] = deque(maxlen=max_actions)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        with self._lock:
            self._buffer.append(msg)
            if self._ACTION_PATTERNS.search(msg):
                self._actions.append((time.time(), msg))

    def get_lines(self) -> list[str]:
        with self._lock:
            return list(self._buffer)

    def get_last_action(self) -> tuple[float, str] | None:
        with self._lock:
            return self._actions[-1] if self._actions else None

    def get_recent_actions(self, n: int = 5) -> list[tuple[float, str]]:
        with self._lock:
            return list(self._actions)[-n:]
