"""
View-based RuntimeSnapshot for hot-loop performance.

RuntimeSnapshotView is a lightweight read-only view over cached data:
- Holds references to FeedStores (not copies)
- Stores current exec index + HTF/MTF context indices
- Provides accessor methods for data (no deep copies)

PERFORMANCE CONTRACT:
- Snapshot creation is O(1) - just index updates
- All data access via accessors is O(1) array lookup
- No DataFrame operations
- No large object allocation
- History access via index offset (deque for rolling windows)

This replaces the materialized RuntimeSnapshot for hot-loop usage.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, Any, Deque

import numpy as np

from .feed_store import FeedStore, MultiTFFeedStore
from .types import ExchangeState, HistoryConfig, DEFAULT_HISTORY_CONFIG


@dataclass
class TFContext:
    """
    Context for a single timeframe within the snapshot.
    
    Tracks the current index and last-closed index for that TF.
    """
    feed: FeedStore
    current_idx: int  # Current bar index in this TF's feed
    ready: bool = False  # Whether this TF has valid features
    not_ready_reason: Optional[str] = None
    
    @property
    def ts_close(self) -> datetime:
        """Get ts_close at current index."""
        return self.feed.get_ts_close_datetime(self.current_idx)
    
    @property
    def ts_open(self) -> datetime:
        """Get ts_open at current index."""
        return self.feed.get_ts_open_datetime(self.current_idx)
    
    def get_indicator(self, name: str) -> Optional[float]:
        """
        Get indicator value at current index.
        
        Returns None if:
        - Indicator is not declared (not in FeedStore)
        - Indicator value is NaN at current index
        
        Use has_indicator() to check if an indicator is declared.
        Use get_indicator_strict() to raise on undeclared indicators.
        """
        if name not in self.feed.indicators:
            return None
        val = self.feed.indicators[name][self.current_idx]
        if np.isnan(val):
            return None
        return float(val)
    
    def get_indicator_strict(self, name: str) -> float:
        """
        Get indicator value at current index, raising if undeclared.
        
        Use this when the indicator MUST be present (Idea Card declared it).
        Raises KeyError if indicator is not in FeedStore.
        Raises ValueError if indicator value is NaN.
        """
        if name not in self.feed.indicators:
            available = list(self.feed.indicators.keys())
            raise KeyError(
                f"Indicator '{name}' not declared. "
                f"Available indicators: {available}. "
                f"Ensure indicator is specified in FeatureSpec/Idea Card."
            )
        val = self.feed.indicators[name][self.current_idx]
        if np.isnan(val):
            raise ValueError(
                f"Indicator '{name}' is NaN at index {self.current_idx}. "
                f"Possible warmup period issue."
            )
        return float(val)
    
    def has_indicator(self, name: str) -> bool:
        """Check if an indicator is declared (exists in FeedStore)."""
        return name in self.feed.indicators
    
    @property
    def open(self) -> float:
        return float(self.feed.open[self.current_idx])
    
    @property
    def high(self) -> float:
        return float(self.feed.high[self.current_idx])
    
    @property
    def low(self) -> float:
        return float(self.feed.low[self.current_idx])
    
    @property
    def close(self) -> float:
        return float(self.feed.close[self.current_idx])
    
    @property
    def volume(self) -> float:
        return float(self.feed.volume[self.current_idx])


class RuntimeSnapshotView:
    """
    Lightweight view over cached feed data.
    
    This is the strategy-facing interface. All data access is via
    accessor methods that read from precomputed numpy arrays.
    
    Zero per-bar allocation for OHLCV/features.
    
    Attributes:
        exec_idx: Current execution bar index
        exec_ctx: Exec TF context
        htf_ctx: HTF context (may be forward-filled)
        mtf_ctx: MTF context (may be forward-filled)
        exchange: Reference to exchange (for state queries)
        mark_price: Current mark price
        mark_price_source: Mark price source
        
        # History deques (bounded, O(1) append)
        history_exec_indices: Previous exec indices for history access
        
        # Readiness
        ready: Whether snapshot is ready for strategy
        history_ready: Whether history windows are filled
    """
    
    __slots__ = (
        'symbol', 'exec_tf', 'ts_close', 'exec_idx',
        'exec_ctx', 'htf_ctx', 'mtf_ctx',
        'exchange', 'mark_price', 'mark_price_source',
        'tf_mapping', 'history_config',
        '_history_exec_indices', '_history_htf_indices', '_history_mtf_indices',
        'history_ready', '_feeds',
    )
    
    def __init__(
        self,
        feeds: MultiTFFeedStore,
        exec_idx: int,
        htf_idx: Optional[int],
        mtf_idx: Optional[int],
        exchange,  # SimulatedExchange reference
        mark_price: float,
        mark_price_source: str,
        history_config: Optional[HistoryConfig] = None,
        history_exec_indices: Optional[Deque[int]] = None,
        history_htf_indices: Optional[Deque[int]] = None,
        history_mtf_indices: Optional[Deque[int]] = None,
        history_ready: bool = True,
    ):
        """
        Initialize snapshot view.
        
        Args:
            feeds: MultiTFFeedStore with all precomputed data
            exec_idx: Current exec bar index
            htf_idx: Current HTF context index (last closed)
            mtf_idx: Current MTF context index (last closed)
            exchange: SimulatedExchange reference
            mark_price: Current mark price
            mark_price_source: Mark price source
            history_config: History configuration
            history_exec_indices: Deque of previous exec indices
            history_htf_indices: Deque of previous HTF closed indices
            history_mtf_indices: Deque of previous MTF closed indices
            history_ready: Whether history windows are filled
        """
        self._feeds = feeds
        self.symbol = feeds.exec_feed.symbol
        self.exec_tf = feeds.exec_feed.tf
        self.exec_idx = exec_idx
        self.tf_mapping = feeds.tf_mapping
        
        # Exec context (always current)
        self.exec_ctx = TFContext(
            feed=feeds.exec_feed,
            current_idx=exec_idx,
            ready=True,
        )
        self.ts_close = self.exec_ctx.ts_close
        
        # HTF context (forward-filled)
        if feeds.htf_feed is not None and htf_idx is not None:
            self.htf_ctx = TFContext(
                feed=feeds.htf_feed,
                current_idx=htf_idx,
                ready=True,
            )
        else:
            # Single-TF mode: HTF = Exec
            self.htf_ctx = self.exec_ctx
        
        # MTF context (forward-filled)
        if feeds.mtf_feed is not None and mtf_idx is not None:
            self.mtf_ctx = TFContext(
                feed=feeds.mtf_feed,
                current_idx=mtf_idx,
                ready=True,
            )
        else:
            # Single-TF mode: MTF = Exec
            self.mtf_ctx = self.exec_ctx
        
        self.exchange = exchange
        self.mark_price = mark_price
        self.mark_price_source = mark_price_source
        
        self.history_config = history_config or DEFAULT_HISTORY_CONFIG
        self._history_exec_indices = history_exec_indices or deque(maxlen=100)
        self._history_htf_indices = history_htf_indices or deque(maxlen=20)
        self._history_mtf_indices = history_mtf_indices or deque(maxlen=20)
        self.history_ready = history_ready
    
    # =========================================================================
    # Readiness
    # =========================================================================
    
    @property
    def ready(self) -> bool:
        """Check if snapshot is ready for strategy evaluation."""
        return (
            self.exec_ctx.ready and
            self.htf_ctx.ready and
            self.mtf_ctx.ready and
            self.history_ready
        )
    
    @property
    def not_ready_reasons(self) -> list:
        """Get list of reasons why snapshot is not ready."""
        reasons = []
        if not self.exec_ctx.ready:
            reasons.append(f"Exec: {self.exec_ctx.not_ready_reason}")
        if not self.htf_ctx.ready:
            reasons.append(f"HTF: {self.htf_ctx.not_ready_reason}")
        if not self.mtf_ctx.ready:
            reasons.append(f"MTF: {self.mtf_ctx.not_ready_reason}")
        if not self.history_ready:
            reasons.append("History: required windows not yet filled")
        return reasons
    
    # =========================================================================
    # Current Bar Accessors (Exec TF)
    # =========================================================================
    
    @property
    def open(self) -> float:
        """Current exec bar open price."""
        return self.exec_ctx.open
    
    @property
    def high(self) -> float:
        """Current exec bar high price."""
        return self.exec_ctx.high
    
    @property
    def low(self) -> float:
        """Current exec bar low price."""
        return self.exec_ctx.low
    
    @property
    def close(self) -> float:
        """Current exec bar close price."""
        return self.exec_ctx.close
    
    @property
    def volume(self) -> float:
        """Current exec bar volume."""
        return self.exec_ctx.volume
    
    # =========================================================================
    # Current Indicator Accessors (Exec TF)
    # =========================================================================
    
    @property
    def ema_fast(self) -> Optional[float]:
        """Current exec EMA fast value."""
        return self.exec_ctx.get_indicator("ema_fast")
    
    @property
    def ema_slow(self) -> Optional[float]:
        """Current exec EMA slow value."""
        return self.exec_ctx.get_indicator("ema_slow")
    
    @property
    def rsi(self) -> Optional[float]:
        """Current exec RSI value."""
        return self.exec_ctx.get_indicator("rsi")
    
    @property
    def atr(self) -> Optional[float]:
        """Current exec ATR value."""
        return self.exec_ctx.get_indicator("atr")
    
    def indicator(self, name: str) -> Optional[float]:
        """Get current exec indicator by name. Returns None if undeclared."""
        return self.exec_ctx.get_indicator(name)
    
    def indicator_strict(self, name: str) -> float:
        """
        Get current exec indicator by name, raising if undeclared.
        
        Use this when the indicator MUST be present (Idea Card declared it).
        Raises KeyError if indicator is not declared.
        Raises ValueError if indicator value is NaN.
        """
        return self.exec_ctx.get_indicator_strict(name)
    
    def has_indicator(self, name: str) -> bool:
        """Check if an indicator is declared in exec TF."""
        return self.exec_ctx.has_indicator(name)
    
    @property
    def available_indicators(self) -> list:
        """Get list of available exec indicator keys."""
        return list(self._feeds.exec_feed.indicators.keys())
    
    # =========================================================================
    # Previous Bar/Indicator Accessors (for crossovers, structure SL)
    # =========================================================================
    
    def prev_ema_fast(self, lookback: int = 1) -> Optional[float]:
        """Get previous EMA fast value (for crossover detection)."""
        return self._get_prev_indicator("ema_fast", lookback)
    
    def prev_ema_slow(self, lookback: int = 1) -> Optional[float]:
        """Get previous EMA slow value (for crossover detection)."""
        return self._get_prev_indicator("ema_slow", lookback)
    
    def prev_rsi(self, lookback: int = 1) -> Optional[float]:
        """Get previous RSI value."""
        return self._get_prev_indicator("rsi", lookback)
    
    def prev_atr(self, lookback: int = 1) -> Optional[float]:
        """Get previous ATR value."""
        return self._get_prev_indicator("atr", lookback)
    
    def prev_indicator(self, name: str, lookback: int = 1) -> Optional[float]:
        """Get previous indicator value by name."""
        return self._get_prev_indicator(name, lookback)
    
    def _get_prev_indicator(self, name: str, lookback: int) -> Optional[float]:
        """Internal: get previous indicator via index offset."""
        if lookback < 1:
            raise ValueError("lookback must be >= 1")
        
        # Try history indices first
        if len(self._history_exec_indices) >= lookback:
            hist_idx = self._history_exec_indices[-lookback]
            if name in self._feeds.exec_feed.indicators:
                val = self._feeds.exec_feed.indicators[name][hist_idx]
                if not np.isnan(val):
                    return float(val)
        
        # Fallback: direct index offset (if within bounds)
        prev_idx = self.exec_idx - lookback
        if prev_idx >= 0:
            if name in self._feeds.exec_feed.indicators:
                val = self._feeds.exec_feed.indicators[name][prev_idx]
                if not np.isnan(val):
                    return float(val)
        
        return None
    
    def bars_exec_low(self, n: int) -> Optional[float]:
        """Get lowest low of last n exec bars (for structure SL)."""
        if n < 1:
            raise ValueError("n must be >= 1")
        
        start_idx = max(0, self.exec_idx - n + 1)
        end_idx = self.exec_idx + 1
        
        if start_idx >= end_idx:
            return None
        
        return float(np.min(self._feeds.exec_feed.low[start_idx:end_idx]))
    
    def bars_exec_high(self, n: int) -> Optional[float]:
        """Get highest high of last n exec bars (for structure SL)."""
        if n < 1:
            raise ValueError("n must be >= 1")
        
        start_idx = max(0, self.exec_idx - n + 1)
        end_idx = self.exec_idx + 1
        
        if start_idx >= end_idx:
            return None
        
        return float(np.max(self._feeds.exec_feed.high[start_idx:end_idx]))
    
    def prev_close(self, lookback: int = 1) -> Optional[float]:
        """Get previous close price."""
        prev_idx = self.exec_idx - lookback
        if prev_idx < 0:
            return None
        return float(self._feeds.exec_feed.close[prev_idx])
    
    def prev_high(self, lookback: int = 1) -> Optional[float]:
        """Get previous high price."""
        prev_idx = self.exec_idx - lookback
        if prev_idx < 0:
            return None
        return float(self._feeds.exec_feed.high[prev_idx])
    
    def prev_low(self, lookback: int = 1) -> Optional[float]:
        """Get previous low price."""
        prev_idx = self.exec_idx - lookback
        if prev_idx < 0:
            return None
        return float(self._feeds.exec_feed.low[prev_idx])
    
    # =========================================================================
    # HTF/MTF Accessors (forward-filled context)
    # =========================================================================
    
    @property
    def htf_ema_fast(self) -> Optional[float]:
        """HTF EMA fast (forward-filled from last close)."""
        return self.htf_ctx.get_indicator("ema_fast")
    
    @property
    def htf_ema_slow(self) -> Optional[float]:
        """HTF EMA slow (forward-filled from last close)."""
        return self.htf_ctx.get_indicator("ema_slow")
    
    @property
    def htf_rsi(self) -> Optional[float]:
        """HTF RSI (forward-filled from last close)."""
        return self.htf_ctx.get_indicator("rsi")
    
    @property
    def mtf_ema_fast(self) -> Optional[float]:
        """MTF EMA fast (forward-filled from last close)."""
        return self.mtf_ctx.get_indicator("ema_fast")
    
    @property
    def mtf_ema_slow(self) -> Optional[float]:
        """MTF EMA slow (forward-filled from last close)."""
        return self.mtf_ctx.get_indicator("ema_slow")
    
    @property
    def mtf_rsi(self) -> Optional[float]:
        """MTF RSI (forward-filled from last close)."""
        return self.mtf_ctx.get_indicator("rsi")
    
    def htf_indicator(self, name: str) -> Optional[float]:
        """Get HTF indicator by name."""
        return self.htf_ctx.get_indicator(name)
    
    def mtf_indicator(self, name: str) -> Optional[float]:
        """Get MTF indicator by name."""
        return self.mtf_ctx.get_indicator(name)
    
    @property
    def available_htf_indicators(self) -> list:
        """Get list of available HTF indicator keys."""
        if self._feeds.htf_feed is None:
            return []
        return list(self._feeds.htf_feed.indicators.keys())
    
    @property
    def available_mtf_indicators(self) -> list:
        """Get list of available MTF indicator keys."""
        if self._feeds.mtf_feed is None:
            return []
        return list(self._feeds.mtf_feed.indicators.keys())
    
    # =========================================================================
    # Staleness (for MTF forward-fill validation)
    # =========================================================================
    
    @property
    def htf_is_stale(self) -> bool:
        """Check if HTF features are stale (forward-filled)."""
        return self.ts_close > self.htf_ctx.ts_close
    
    @property
    def mtf_is_stale(self) -> bool:
        """Check if MTF features are stale (forward-filled)."""
        return self.ts_close > self.mtf_ctx.ts_close
    
    @property
    def htf_ctx_ts_close(self) -> datetime:
        """Get HTF context timestamp."""
        return self.htf_ctx.ts_close
    
    @property
    def mtf_ctx_ts_close(self) -> datetime:
        """Get MTF context timestamp."""
        return self.mtf_ctx.ts_close
    
    # =========================================================================
    # Exchange State Accessors
    # =========================================================================
    
    @property
    def equity(self) -> float:
        """Current equity (USDT)."""
        return self.exchange.equity_usdt
    
    @property
    def available_balance(self) -> float:
        """Available balance (USDT)."""
        return self.exchange.available_balance_usdt
    
    @property
    def has_position(self) -> bool:
        """Whether a position is open."""
        return self.exchange.position is not None
    
    @property
    def position_side(self) -> Optional[str]:
        """Current position side (long/short/None)."""
        if self.exchange.position is None:
            return None
        return self.exchange.position.side
    
    @property
    def position_size_usdt(self) -> float:
        """Current position notional size."""
        if self.exchange.position is None:
            return 0.0
        return self.exchange.position.size_usdt
    
    @property
    def unrealized_pnl(self) -> float:
        """Current unrealized PnL."""
        return self.exchange.unrealized_pnl_usdt
    
    @property
    def entries_disabled(self) -> bool:
        """Whether new entries are blocked."""
        return self.exchange.entries_disabled
    
    # =========================================================================
    # Backward Compatibility Aliases
    # =========================================================================
    
    @property
    def ltf_tf(self) -> str:
        """Alias for exec_tf."""
        return self.exec_tf
    
    @property
    def bar_ltf(self):
        """Alias for bar_exec (returns self for accessor access)."""
        return self.exec_ctx
    
    @property
    def bar_exec(self):
        """Current exec bar context."""
        return self.exec_ctx
    
    @property
    def features_exec(self):
        """Current exec features context."""
        return self.exec_ctx
    
    @property
    def features_ltf(self):
        """Alias for features_exec."""
        return self.exec_ctx
    
    @property
    def features_htf(self):
        """HTF features context."""
        return self.htf_ctx
    
    @property
    def features_mtf(self):
        """MTF features context."""
        return self.mtf_ctx
    
    # =========================================================================
    # Serialization (for debugging only, not in hot loop)
    # =========================================================================
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for debugging/serialization."""
        return {
            "ts_close": self.ts_close.isoformat(),
            "symbol": self.symbol,
            "exec_tf": self.exec_tf,
            "exec_idx": self.exec_idx,
            "mark_price": self.mark_price,
            "mark_price_source": self.mark_price_source,
            "ready": self.ready,
            "history_ready": self.history_ready,
            # Current bar
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            # Current indicators
            "ema_fast": self.ema_fast,
            "ema_slow": self.ema_slow,
            "rsi": self.rsi,
            "atr": self.atr,
            # Staleness
            "htf_is_stale": self.htf_is_stale,
            "mtf_is_stale": self.mtf_is_stale,
            "htf_ctx_ts_close": self.htf_ctx_ts_close.isoformat(),
            "mtf_ctx_ts_close": self.mtf_ctx_ts_close.isoformat(),
        }
