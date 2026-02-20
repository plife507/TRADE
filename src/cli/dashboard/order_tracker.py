"""Order event tracking for dashboard display."""

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass(slots=True)
class OrderEvent:
    """Single order event for dashboard display."""

    timestamp: float
    symbol: str
    direction: str
    size_usdt: float
    order_type: str  # "market", "limit"
    status: str  # "submitted", "filled", "failed", "rejected", "pending"
    order_id: str
    fill_price: float | None = None
    error: str | None = None
    source: str = "rest"  # "rest" or "websocket"


class OrderTracker:
    """Thread-safe tracker for order events displayed in the dashboard.

    Captures order submissions, fills, and failures into a ring buffer.
    Register via ``OrderExecutor.on_execution()`` callback.
    """

    def __init__(self, max_events: int = 50) -> None:
        self._events: deque[OrderEvent] = deque(maxlen=max_events)
        self._lock = threading.Lock()
        # Counters
        self.total_submitted: int = 0
        self.total_filled: int = 0
        self.total_failed: int = 0

    def record_execution_result(self, result: object) -> None:
        """Callback for ``OrderExecutor.on_execution()``.

        Accepts an ``ExecutionResult`` from ``src.core.order_executor``.
        """
        signal = getattr(result, "signal", None)
        order_result = getattr(result, "order_result", None)
        success = getattr(result, "success", False)
        error = getattr(result, "error", None)
        source = getattr(result, "source", "rest")

        symbol = getattr(signal, "symbol", "?") if signal else "?"
        direction = getattr(signal, "direction", "?") if signal else "?"
        size_usdt = getattr(signal, "size_usdt", 0.0) if signal else 0.0

        # Determine order type from signal metadata
        meta = getattr(signal, "metadata", None) or {}
        order_type = meta.get("order_type", "market")

        order_id = ""
        fill_price: float | None = None
        if order_result is not None:
            order_id = getattr(order_result, "order_id", "") or ""
            fill_price = getattr(order_result, "price", None) or getattr(
                order_result, "fill_price", None
            )

        if success:
            status = "filled"
        elif error:
            # Check risk block vs execution failure
            risk_check = getattr(result, "risk_check", None)
            if risk_check and not getattr(risk_check, "allowed", True):
                status = "rejected"
            else:
                status = "failed"
        else:
            status = "failed"

        event = OrderEvent(
            timestamp=time.time(),
            symbol=symbol,
            direction=direction,
            size_usdt=size_usdt,
            order_type=order_type,
            status=status,
            order_id=order_id,
            fill_price=fill_price,
            error=error,
            source=source,
        )

        with self._lock:
            self._events.append(event)
            self.total_submitted += 1
            if success:
                self.total_filled += 1
            else:
                self.total_failed += 1

    def get_events(self, n: int = 20) -> list[OrderEvent]:
        """Return last *n* order events (newest first)."""
        with self._lock:
            items = list(self._events)
        return list(reversed(items[-n:]))

    def get_pending_count(self) -> int:
        """Count events with status 'pending' or 'submitted'."""
        with self._lock:
            return sum(
                1 for e in self._events if e.status in ("pending", "submitted")
            )

    def get_summary(self) -> tuple[int, int, int]:
        """Return (total_submitted, total_filled, total_failed)."""
        with self._lock:
            return self.total_submitted, self.total_filled, self.total_failed

    def get_win_loss_stats(self) -> tuple[int, int, float]:
        """Return (wins, losses, net_pnl) from filled events.

        A 'win' is a close (FLAT direction) fill with positive implied PnL.
        This is a rough heuristic since we don't track per-trade P&L here.
        """
        with self._lock:
            wins = 0
            losses = 0
            net_pnl = 0.0
            for e in self._events:
                if e.status == "filled" and e.direction == "FLAT" and e.fill_price:
                    # Count as a completed trade
                    # Without entry price tracking we just count fills
                    wins += 1  # Placeholder: actual W/L requires entry tracking
            # For now return fill count and zeros — enhanced later with entry tracking
            return wins, losses, net_pnl
