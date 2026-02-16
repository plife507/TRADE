"""
Session-only recent symbols tracker for CLI.

Provides quick-pick symbol selection based on recently used symbols.
No file persistence - resets when the CLI exits.
"""


class RecentSymbols:
    """Session-only recent symbols tracker. No file persistence."""

    _instance: "RecentSymbols | None" = None
    MAX_RECENT = 5

    def __init__(self) -> None:
        self._symbols: list[str] = []

    @classmethod
    def get_instance(cls) -> "RecentSymbols":
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def record(self, symbol: str) -> None:
        """Record a symbol use. Moves to front if already present."""
        symbol = symbol.upper().strip()
        if not symbol:
            return
        if symbol in self._symbols:
            self._symbols.remove(symbol)
        self._symbols.insert(0, symbol)
        self._symbols = self._symbols[: self.MAX_RECENT]

    def get_recent(self) -> list[str]:
        """Return recent symbols, most recent first."""
        return list(self._symbols)

    def has_recent(self) -> bool:
        """Check if any recent symbols exist."""
        return len(self._symbols) > 0
