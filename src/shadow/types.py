"""
Core types for Shadow Exchange.

All hot-path dataclasses use __slots__ to minimize per-instance memory
(~200 bytes saved per instance vs __dict__). With 50+ engines generating
snapshots hourly, this adds up.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class ShadowEngineState(str, Enum):
    """Lifecycle state of a ShadowEngine."""
    CREATED = "created"
    WARMING_UP = "warming_up"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(slots=True)
class ShadowSnapshot:
    """Periodic equity/state snapshot for performance tracking.

    Recorded hourly (or configurable) per engine. Kept lean —
    only fields needed for graduation scoring and M6 training.
    """
    timestamp: datetime
    instance_id: str
    equity_usdt: float
    cash_balance_usdt: float
    unrealized_pnl_usdt: float
    position_side: str | None       # "long", "short", None
    position_size_usdt: float
    mark_price: float
    cumulative_pnl_usdt: float
    total_trades: int
    winning_trades: int
    max_drawdown_pct: float
    # Market context (for M6 training)
    funding_rate: float
    atr_pct: float                  # ATR / price (volatility proxy)

    def __post_init__(self) -> None:
        assert self.timestamp.tzinfo is None, (
            f"ShadowSnapshot.timestamp must be UTC-naive, got tzinfo={self.timestamp.tzinfo}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "instance_id": self.instance_id,
            "equity_usdt": self.equity_usdt,
            "cash_balance_usdt": self.cash_balance_usdt,
            "unrealized_pnl_usdt": self.unrealized_pnl_usdt,
            "position_side": self.position_side,
            "position_size_usdt": self.position_size_usdt,
            "mark_price": self.mark_price,
            "cumulative_pnl_usdt": self.cumulative_pnl_usdt,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "max_drawdown_pct": self.max_drawdown_pct,
            "funding_rate": self.funding_rate,
            "atr_pct": self.atr_pct,
        }


@dataclass(slots=True)
class ShadowTrade:
    """Record of a completed trade in shadow mode.

    Stored in performance DB for analytics and graduation scoring.
    """
    trade_id: str
    instance_id: str
    play_id: str
    symbol: str
    direction: str                  # "long", "short"
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    size_usdt: float
    pnl_usdt: float
    fees_usdt: float
    exit_reason: str                # "take_profit", "stop_loss", "signal", etc.
    mae_pct: float                  # Max Adverse Excursion
    mfe_pct: float                  # Max Favorable Excursion
    duration_minutes: float
    # Market context at entry
    entry_funding_rate: float
    entry_atr_pct: float

    def __post_init__(self) -> None:
        assert self.entry_time.tzinfo is None
        assert self.exit_time.tzinfo is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "instance_id": self.instance_id,
            "play_id": self.play_id,
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_time": self.entry_time.isoformat(),
            "exit_time": self.exit_time.isoformat(),
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "size_usdt": self.size_usdt,
            "pnl_usdt": self.pnl_usdt,
            "fees_usdt": self.fees_usdt,
            "exit_reason": self.exit_reason,
            "mae_pct": self.mae_pct,
            "mfe_pct": self.mfe_pct,
            "duration_minutes": self.duration_minutes,
            "entry_funding_rate": self.entry_funding_rate,
            "entry_atr_pct": self.entry_atr_pct,
        }


@dataclass(slots=True)
class ShadowEngineStats:
    """Live statistics for a running ShadowEngine.

    Updated in-place each bar — no allocations on the hot path.
    """
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    last_bar_at: datetime | None = None
    bars_processed: int = 0
    signals_generated: int = 0
    trades_opened: int = 0
    trades_closed: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    # Running P&L
    equity_usdt: float = 0.0
    peak_equity_usdt: float = 0.0
    cumulative_pnl_usdt: float = 0.0
    max_drawdown_pct: float = 0.0
    # Latest market context
    last_mark_price: float = 0.0
    last_funding_rate: float = 0.0

    @property
    def win_rate(self) -> float:
        total = self.winning_trades + self.losing_trades
        return self.winning_trades / total if total > 0 else 0.0

    def update_equity(self, equity: float) -> None:
        """Update equity tracking — call each bar. Zero allocations."""
        self.equity_usdt = equity
        if equity > self.peak_equity_usdt:
            self.peak_equity_usdt = equity
        if self.peak_equity_usdt > 0:
            dd = (self.peak_equity_usdt - equity) / self.peak_equity_usdt * 100.0
            if dd > self.max_drawdown_pct:
                self.max_drawdown_pct = dd

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "last_bar_at": self.last_bar_at.isoformat() if self.last_bar_at else None,
            "bars_processed": self.bars_processed,
            "signals_generated": self.signals_generated,
            "trades_opened": self.trades_opened,
            "trades_closed": self.trades_closed,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "equity_usdt": self.equity_usdt,
            "peak_equity_usdt": self.peak_equity_usdt,
            "cumulative_pnl_usdt": self.cumulative_pnl_usdt,
            "max_drawdown_pct": self.max_drawdown_pct,
            "win_rate": self.win_rate,
            "last_mark_price": self.last_mark_price,
            "last_funding_rate": self.last_funding_rate,
        }


@dataclass(slots=True)
class ShadowInstanceInfo:
    """Summary info for a shadow instance (for list/status commands)."""
    instance_id: str
    play_id: str
    symbol: str
    exec_tf: str
    state: ShadowEngineState
    stats: ShadowEngineStats

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "play_id": self.play_id,
            "symbol": self.symbol,
            "exec_tf": self.exec_tf,
            "state": self.state.value,
            "stats": self.stats.to_dict(),
        }
