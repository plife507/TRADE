"""
Core runtime types for backtesting.

Provides canonical types for the backtest runtime:
- Bar: Single OHLCV bar with explicit ts_open/ts_close
- FeatureSnapshot: Indicator features per timeframe
- ExchangeState: Immutable exchange state snapshot (USDT naming)
- HistoryConfig: Configuration for snapshot history depth
- RuntimeSnapshot: Complete point-in-time state for strategy

Design principles:
- Immutable where possible (frozen dataclasses)
- Explicit timestamps (ts_open, ts_close)
- USDT naming for exchange/ledger fields
- No None-by-default for feature snapshots (use ready=False placeholder)
- History is bounded by config (no unbounded memory growth)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class HistoryConfig:
    """
    Configuration for snapshot history depth.
    
    Strategies that need crossover detection or structure-based SL
    can request history windows. All counts are bounded and configured
    per-system to prevent unbounded memory growth.
    
    Attributes:
        bars_exec_count: Number of previous exec-TF bars to keep
        features_exec_count: Number of previous exec-TF feature snapshots
        features_high_tf_count: Number of previous *closed* high_tf feature snapshots
        features_med_tf_count: Number of previous *closed* med_tf feature snapshots

    Example YAML config:
        history:
          bars_exec_count: 20
          features_exec_count: 2
          features_high_tf_count: 2
          features_med_tf_count: 2
    """
    bars_exec_count: int = 0         # Previous exec-TF bars (for structure SL)
    features_exec_count: int = 0     # Previous exec-TF feature snapshots (for crossovers)
    features_high_tf_count: int = 0  # Previous *closed* high_tf feature snapshots
    features_med_tf_count: int = 0   # Previous *closed* med_tf feature snapshots

    def __post_init__(self):
        """Validate all counts are non-negative."""
        if self.bars_exec_count < 0:
            raise ValueError(f"bars_exec_count must be >= 0, got {self.bars_exec_count}")
        if self.features_exec_count < 0:
            raise ValueError(f"features_exec_count must be >= 0, got {self.features_exec_count}")
        if self.features_high_tf_count < 0:
            raise ValueError(f"features_high_tf_count must be >= 0, got {self.features_high_tf_count}")
        if self.features_med_tf_count < 0:
            raise ValueError(f"features_med_tf_count must be >= 0, got {self.features_med_tf_count}")
    
    @property
    def requires_history(self) -> bool:
        """Check if any history is configured."""
        return (
            self.bars_exec_count > 0 or
            self.features_exec_count > 0 or
            self.features_high_tf_count > 0 or
            self.features_med_tf_count > 0
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "bars_exec_count": self.bars_exec_count,
            "features_exec_count": self.features_exec_count,
            "features_high_tf_count": self.features_high_tf_count,
            "features_med_tf_count": self.features_med_tf_count,
        }


# Default history config (no history)
DEFAULT_HISTORY_CONFIG = HistoryConfig()


@dataclass(frozen=True)
class Bar:
    """
    Single OHLCV bar with explicit open/close timestamps.
    
    This is the canonical Bar type for the backtest runtime.
    All sim/engine/adapter code should import Bar from this module.
    
    Attributes:
        symbol: Trading symbol (e.g., "SOLUSDT")
        tf: Timeframe string (e.g., "5m", "1h", "D")
        ts_open: Candle open timestamp (from DuckDB)
        ts_close: Candle close timestamp (computed: ts_open + tf_duration)
        open: Open price
        high: High price
        low: Low price
        close: Close price
        volume: Trading volume
        turnover: Optional turnover value
    """
    symbol: str
    tf: str
    ts_open: datetime
    ts_close: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "symbol": self.symbol,
            "tf": self.tf,
            "ts_open": self.ts_open.isoformat(),
            "ts_close": self.ts_close.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "turnover": self.turnover,
        }
    
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Bar:
        """Create Bar from dict."""
        ts_open = d["ts_open"]
        ts_close = d["ts_close"]
        if isinstance(ts_open, str):
            ts_open = datetime.fromisoformat(ts_open)
        if isinstance(ts_close, str):
            ts_close = datetime.fromisoformat(ts_close)
        return cls(
            symbol=d["symbol"],
            tf=d["tf"],
            ts_open=ts_open,
            ts_close=ts_close,
            open=float(d["open"]),
            high=float(d["high"]),
            low=float(d["low"]),
            close=float(d["close"]),
            volume=float(d["volume"]),
            turnover=d.get("turnover"),
        )


@dataclass(frozen=True)
class FeatureSnapshot:
    """
    Indicator feature snapshot for a single timeframe.
    
    Contains precomputed indicator values at a specific TF close.
    Use ready=False during warmup when features are not yet available.
    
    Attributes:
        tf: Timeframe string
        ts_close: Timestamp of the TF close when features were computed
        bar: The Bar at this TF close
        features: Dict of indicator name -> value
        ready: Whether features are valid (False during warmup)
        not_ready_reason: Explanation if not ready
        features_computed_at: When features were computed (for staleness tracking)
    """
    tf: str
    ts_close: datetime
    bar: Bar
    features: dict[str, float] = field(default_factory=dict)
    ready: bool = True
    not_ready_reason: str | None = None
    features_computed_at: datetime | None = None  # When features were computed
    
    def is_stale_at(self, exec_ts_close: datetime) -> bool:
        """
        Check if this snapshot is stale relative to exec timestamp.
        
        A snapshot is stale if exec_ts_close > ts_close, meaning the exec
        bar has advanced past when this TF's features were last computed.
        
        Args:
            exec_ts_close: Current execution timestamp
            
        Returns:
            True if this snapshot's features are from a previous TF close
        """
        return exec_ts_close > self.ts_close
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "tf": self.tf,
            "ts_close": self.ts_close.isoformat(),
            "bar": self.bar.to_dict(),
            "features": self.features,
            "ready": self.ready,
            "not_ready_reason": self.not_ready_reason,
            "features_computed_at": self.features_computed_at.isoformat() if self.features_computed_at else None,
        }


@dataclass(frozen=True)
class ExchangeState:
    """
    Immutable exchange state snapshot with USDT naming.
    
    Captures all Bybit-aligned margin values at a point in time.
    Uses *_usdt suffix consistently (assuming 1 USDT ≈ 1 USD).
    
    Attributes:
        equity_usdt: Total equity (cash + unrealized PnL)
        cash_usdt: Realized cash balance
        used_margin_usdt: Position initial margin
        free_margin_usdt: Equity - used margin (can be negative)
        available_balance_usdt: max(0, free_margin)
        maintenance_margin_usdt: Position maintenance margin
        has_position: Whether a position is open
        position_side: "long", "short", or None
        position_size_usdt: Position notional value
        position_qty: Position quantity in base currency
        position_entry_price: Position entry price
        unrealized_pnl_usdt: Mark-to-market unrealized PnL
        entries_disabled: Whether new entries are blocked
        entries_disabled_reason: Why entries are disabled (if any)
    """
    equity_usdt: float
    cash_usdt: float
    used_margin_usdt: float
    free_margin_usdt: float
    available_balance_usdt: float
    maintenance_margin_usdt: float
    has_position: bool = False
    position_side: str | None = None
    position_size_usdt: float = 0.0
    position_qty: float = 0.0
    position_entry_price: float = 0.0
    unrealized_pnl_usdt: float = 0.0
    entries_disabled: bool = False
    entries_disabled_reason: str | None = None
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "equity_usdt": self.equity_usdt,
            "cash_usdt": self.cash_usdt,
            "used_margin_usdt": self.used_margin_usdt,
            "free_margin_usdt": self.free_margin_usdt,
            "available_balance_usdt": self.available_balance_usdt,
            "maintenance_margin_usdt": self.maintenance_margin_usdt,
            "has_position": self.has_position,
            "position_side": self.position_side,
            "position_size_usdt": self.position_size_usdt,
            "position_qty": self.position_qty,
            "position_entry_price": self.position_entry_price,
            "unrealized_pnl_usdt": self.unrealized_pnl_usdt,
            "entries_disabled": self.entries_disabled,
            "entries_disabled_reason": self.entries_disabled_reason,
        }


@dataclass(frozen=True)
class RuntimeSnapshot:
    """
    Complete point-in-time state visible to strategy.
    
    The canonical input type for strategy signal generation.
    Contains exec bar, exchange state, multi-TF feature snapshots, and optional history.
    
    Naming convention:
    - bar_exec / features_exec: Current execution timeframe data
    - history_*: Previous bars/features for crossover/structure analysis

    Attributes:
        ts_close: Engine step time (exec candle close)
        symbol: Trading symbol
        exec_tf: Execution timeframe string (master clock)
        mark_price: Current mark price (computed by exchange)
        mark_price_source: How mark was computed (close|hlc3|ohlc4)
        bar_exec: Current exec-TF bar
        exchange_state: Immutable exchange state snapshot
        features_high_tf: high_tf feature snapshot (carry-forward between closes)
        features_med_tf: med_tf feature snapshot (carry-forward between closes)
        features_exec: Exec-TF feature snapshot (updated each exec close)
        tf_mapping: Dict mapping role -> tf (high_tf, med_tf, low_tf keys + exec -> role)

        # History fields (bounded by HistoryConfig)
        history_bars_exec: Previous exec-TF bars (oldest first)
        history_features_exec: Previous exec-TF feature snapshots (oldest first)
        history_features_high_tf: Previous *closed* high_tf feature snapshots (oldest first)
        history_features_med_tf: Previous *closed* med_tf feature snapshots (oldest first)
        history_config: The HistoryConfig that bounds these windows
        history_ready: Whether required history windows are filled
    """
    ts_close: datetime
    symbol: str
    exec_tf: str
    mark_price: float
    mark_price_source: str
    bar_exec: Bar
    exchange_state: ExchangeState
    features_high_tf: FeatureSnapshot
    features_med_tf: FeatureSnapshot
    features_exec: FeatureSnapshot
    tf_mapping: dict[str, str] = field(default_factory=dict)

    # History fields (tuples are immutable, preventing accidental mutation)
    history_bars_exec: tuple[Bar, ...] = field(default_factory=tuple)
    history_features_exec: tuple[FeatureSnapshot, ...] = field(default_factory=tuple)
    history_features_high_tf: tuple[FeatureSnapshot, ...] = field(default_factory=tuple)
    history_features_med_tf: tuple[FeatureSnapshot, ...] = field(default_factory=tuple)
    history_config: HistoryConfig | None = None
    history_ready: bool = True  # True if no history required or history is filled

    @property
    def ready(self) -> bool:
        """Check if all required TF features are ready AND history is ready."""
        return (
            self.features_high_tf.ready and
            self.features_med_tf.ready and
            self.features_exec.ready and
            self.history_ready
        )

    @property
    def not_ready_reasons(self) -> list:
        """Get list of reasons why snapshot is not ready."""
        reasons = []
        if not self.features_high_tf.ready:
            reasons.append(f"high_tf: {self.features_high_tf.not_ready_reason}")
        if not self.features_med_tf.ready:
            reasons.append(f"med_tf: {self.features_med_tf.not_ready_reason}")
        if not self.features_exec.ready:
            reasons.append(f"exec_tf: {self.features_exec.not_ready_reason}")
        if not self.history_ready:
            reasons.append("History: required windows not yet filled")
        return reasons

    # Staleness properties (for med_tf forward-fill validation)
    @property
    def high_tf_is_stale(self) -> bool:
        """Check if high_tf features are stale (forward-filled from previous close)."""
        return self.features_high_tf.is_stale_at(self.ts_close)

    @property
    def med_tf_is_stale(self) -> bool:
        """Check if med_tf features are stale (forward-filled from previous close)."""
        return self.features_med_tf.is_stale_at(self.ts_close)

    @property
    def exec_is_stale(self) -> bool:
        """Check if exec features are stale (should always be False)."""
        return self.features_exec.is_stale_at(self.ts_close)

    @property
    def high_tf_ctx_ts_close(self) -> datetime:
        """Get high_tf context timestamp (when high_tf features were computed)."""
        return self.features_high_tf.ts_close

    @property
    def med_tf_ctx_ts_close(self) -> datetime:
        """Get med_tf context timestamp (when med_tf features were computed)."""
        return self.features_med_tf.ts_close

    @property
    def exec_ctx_ts_close(self) -> datetime:
        """Get exec context timestamp (should equal ts_close)."""
        return self.features_exec.ts_close
    
    # History access helpers
    def prev_features_exec(self, lookback: int = 1) -> FeatureSnapshot | None:
        """
        Get previous exec-TF feature snapshot.
        
        Args:
            lookback: How many bars back (1 = previous bar, 2 = two bars ago)
            
        Returns:
            FeatureSnapshot or None if not available
        """
        if lookback < 1:
            raise ValueError("lookback must be >= 1")
        idx = len(self.history_features_exec) - lookback
        if idx < 0:
            return None
        return self.history_features_exec[idx]
    
    def prev_bar_exec(self, lookback: int = 1) -> Bar | None:
        """
        Get previous exec-TF bar.
        
        Args:
            lookback: How many bars back (1 = previous bar)
            
        Returns:
            Bar or None if not available
        """
        if lookback < 1:
            raise ValueError("lookback must be >= 1")
        idx = len(self.history_bars_exec) - lookback
        if idx < 0:
            return None
        return self.history_bars_exec[idx]
    
    def prev_features_high_tf(self, lookback: int = 1) -> FeatureSnapshot | None:
        """Get previous high_tf feature snapshot."""
        if lookback < 1:
            raise ValueError("lookback must be >= 1")
        idx = len(self.history_features_high_tf) - lookback
        if idx < 0:
            return None
        return self.history_features_high_tf[idx]

    def prev_features_med_tf(self, lookback: int = 1) -> FeatureSnapshot | None:
        """Get previous med_tf feature snapshot."""
        if lookback < 1:
            raise ValueError("lookback must be >= 1")
        idx = len(self.history_features_med_tf) - lookback
        if idx < 0:
            return None
        return self.history_features_med_tf[idx]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "ts_close": self.ts_close.isoformat(),
            "symbol": self.symbol,
            "exec_tf": self.exec_tf,
            "mark_price": self.mark_price,
            "mark_price_source": self.mark_price_source,
            "bar_exec": self.bar_exec.to_dict(),
            "exchange_state": self.exchange_state.to_dict(),
            "features_high_tf": self.features_high_tf.to_dict(),
            "features_med_tf": self.features_med_tf.to_dict(),
            "features_exec": self.features_exec.to_dict(),
            "tf_mapping": self.tf_mapping,
            "ready": self.ready,
            "history_ready": self.history_ready,
            # Per-TF staleness info
            "high_tf_ctx_ts_close": self.high_tf_ctx_ts_close.isoformat(),
            "med_tf_ctx_ts_close": self.med_tf_ctx_ts_close.isoformat(),
            "exec_ctx_ts_close": self.exec_ctx_ts_close.isoformat(),
            "high_tf_is_stale": self.high_tf_is_stale,
            "med_tf_is_stale": self.med_tf_is_stale,
            "exec_is_stale": self.exec_is_stale,
        }
        # Include history counts (not full data) for debugging
        result["history_bars_exec_count"] = len(self.history_bars_exec)
        result["history_features_exec_count"] = len(self.history_features_exec)
        result["history_features_high_tf_count"] = len(self.history_features_high_tf)
        result["history_features_med_tf_count"] = len(self.history_features_med_tf)
        if self.history_config:
            result["history_config"] = self.history_config.to_dict()
        return result


# Placeholder factory for not-ready snapshots
def create_not_ready_feature_snapshot(
    tf: str,
    ts_close: datetime,
    bar: Bar,
    reason: str,
) -> FeatureSnapshot:
    """
    Create a FeatureSnapshot placeholder for warmup/not-ready state.
    
    Use this instead of None when a TF has not yet closed.
    
    Args:
        tf: Timeframe string
        ts_close: Current step timestamp
        bar: Current bar (may be placeholder)
        reason: Why features are not ready
        
    Returns:
        FeatureSnapshot with ready=False
    """
    return FeatureSnapshot(
        tf=tf,
        ts_close=ts_close,
        bar=bar,
        features={},
        ready=False,
        not_ready_reason=reason,
    )

