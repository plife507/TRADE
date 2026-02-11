"""
Adapter that captures LiveExchange state as a snapshot for RuntimeSnapshotView.

RuntimeSnapshotView accesses exchange.equity_usdt, exchange.position,
exchange.unrealized_pnl_usdt, exchange.available_balance_usdt,
exchange.entries_disabled -- all via properties.

SimulatedExchange exposes these natively; LiveExchange does not.
This adapter bridges the gap by querying LiveExchange once and
presenting the results as matching properties.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class _SnapshotPosition:
    """Minimal position snapshot matching SimulatedExchange.position interface."""

    side: str        # "long" or "short"
    size_usdt: float


@dataclass(frozen=True, slots=True)
class LiveExchangeStateAdapter:
    """
    Frozen snapshot of LiveExchange state for RuntimeSnapshotView consumption.

    Properties mirror SimulatedExchange's interface so RuntimeSnapshotView
    can access them identically regardless of mode.
    """

    equity_usdt: float
    available_balance_usdt: float
    position: _SnapshotPosition | None
    unrealized_pnl_usdt: float
    entries_disabled: bool

    @classmethod
    def from_live_exchange(cls, live_exchange, symbol: str) -> "LiveExchangeStateAdapter":
        """
        Capture current state from a LiveExchange instance.

        Args:
            live_exchange: LiveExchange adapter
            symbol: Trading symbol for position lookup

        Returns:
            Frozen snapshot of exchange state
        """
        equity = live_exchange.get_equity()
        balance = live_exchange.get_balance()

        # Query position
        raw_pos = live_exchange.get_position(symbol)
        position = None
        unrealized_pnl = 0.0
        if raw_pos is not None:
            position = _SnapshotPosition(
                side=raw_pos.side.lower(),
                size_usdt=raw_pos.size_usdt,
            )
            unrealized_pnl = raw_pos.unrealized_pnl if raw_pos.unrealized_pnl else 0.0

        return cls(
            equity_usdt=equity,
            available_balance_usdt=balance,
            position=position,
            unrealized_pnl_usdt=unrealized_pnl,
            entries_disabled=False,  # Live exchange handles risk limits externally
        )
