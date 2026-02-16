"""
RuntimeSnapshotView — Array-backed snapshot for hot-loop performance.

RuntimeSnapshotView is the ONLY snapshot implementation:
- Holds references to FeedStores (not copies)
- Stores current exec index + high_tf/med_tf context indices
- Provides accessor methods for data (no deep copies)

PERFORMANCE CONTRACT:
- Snapshot creation is O(1) - just index updates
- All data access via accessors is O(1) array lookup
- No DataFrame operations
- No large object allocation
- History access via index offset (deque for rolling windows)

SNAPSHOT VIEW CONTRACT:
- ts_close: Current exec bar close timestamp (datetime)
- close: Current exec bar close price (float)
- get_feature(indicator_key, tf_role, offset): Unified feature lookup
- has_feature(indicator_key, tf_role): Check feature availability
- exec_ctx, high_tf_ctx, med_tf_ctx: TF contexts for direct access

MULTI-TIMEFRAME FORWARD-FILL:
All timeframes slower than exec forward-fill their values until their bar closes.
- exec_ctx: Updates every bar (current exec index)
- med_tf_ctx: Forward-fills until med_tf bar closes (same index across multiple exec bars)
- high_tf_ctx: Forward-fills until high_tf bar closes (same index across multiple exec bars)

Example (exec=15m, high_tf=1h):
    exec bars:     |  1  |  2  |  3  |  4  |  5  |  ...
    high_tf_ctx.idx: [  0     0     0     0  ] [  1  ...
                     ^--- same high_tf index until 1h bar closes

This ensures no-lookahead: high_tf/med_tf values reflect last CLOSED bar only.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from typing import Any, TYPE_CHECKING

import numpy as np

from .feed_store import FeedStore, MultiTFFeedStore
from .types import ExchangeState, HistoryConfig, DEFAULT_HISTORY_CONFIG

if TYPE_CHECKING:
    from src.structures import MultiTFIncrementalState
    from src.structures.types import FeatureOutputType
    from ..feature_registry import FeatureRegistry
    from ..rationalization import RationalizedState


# LRU-cached path tokenization (P2-07: avoid string split in hot loop)
# Max 1024 unique paths is more than enough for any Play config.
@lru_cache(maxsize=1024)
def _tokenize_path(path: str) -> tuple[str, ...]:
    """Tokenize a dot-separated path. Cached with LRU eviction."""
    return tuple(path.split("."))


@dataclass
class TFContext:
    """
    Context for a single timeframe within the snapshot.
    
    Tracks the current index and last-closed index for that TF.
    """
    feed: FeedStore
    current_idx: int  # Current bar index in this TF's feed
    ready: bool = False  # Whether this TF has valid features
    not_ready_reason: str | None = None
    
    @property
    def ts_close(self) -> datetime:
        """Get ts_close at current index."""
        return self.feed.get_ts_close_datetime(self.current_idx)
    
    @property
    def ts_open(self) -> datetime:
        """Get ts_open at current index."""
        return self.feed.get_ts_open_datetime(self.current_idx)
    
    def get_indicator(self, name: str) -> float | None:
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
        
        Use this when the indicator MUST be present (Play declared it).
        Raises KeyError if indicator is not in FeedStore.
        Raises ValueError if indicator value is NaN.
        """
        if name not in self.feed.indicators:
            available = list(self.feed.indicators.keys())
            raise KeyError(
                f"Indicator '{name}' not declared. "
                f"Available indicators: {available}. "
                f"Ensure indicator is specified in FeatureSpec/Play."
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

    Price Field Semantics (IMPORTANT for Live Integration):
    =========================================================

    Three distinct price concepts exist at different resolutions:

    | Field       | Resolution | Backtest Source    | Live Source (Future)      |
    |-------------|------------|--------------------| --------------------------|
    | last_price  | 1m         | 1m bar close       | ticker.lastPrice          |
    | mark_price  | 1m         | 1m close/mark kline| ticker.markPrice          |
    | close       | eval_tf    | eval_tf bar close  | eval_tf bar close         |

    last_price vs mark_price:
    - last_price: For SIGNAL EVALUATION. Reflects actual orderbook trades.
    - mark_price: For POSITION VALUATION (PnL, liquidation, risk).
      Bybit derives this from index prices across exchanges to prevent
      manipulation-triggered liquidations.

    In backtest, both default to the same 1m close source. In live trading,
    they come from different WebSocket fields and can diverge during volatility.

    Attributes:
        exec_idx: Current execution bar index
        exec_ctx: Exec TF context
        high_tf_ctx: high_tf context (may be forward-filled)
        med_tf_ctx: med_tf context (may be forward-filled)
        exchange: Reference to exchange (for state queries)
        mark_price: Mark price for PnL/liquidation (index-derived in live)
        mark_price_source: Mark price provenance ("mark_1m" | "approx_from_ohlcv_1m")
        last_price: Property - 1m ticker close for signal evaluation

        # Readiness
        ready: Whether snapshot is ready for strategy
        history_ready: Whether history windows are filled
    """

    __slots__ = (
        'symbol', 'exec_tf', 'ts_close', 'exec_idx',
        'low_tf_ctx', 'med_tf_ctx', 'high_tf_ctx',  # 3 TF contexts
        'exec_ctx',  # Alias to one of the 3 contexts (based on exec_role)
        'exchange', 'mark_price', 'mark_price_source',
        'tf_mapping', 'history_config',
        'history_ready', '_feeds', '_rollups',
        '_resolvers', '_incremental_state',
        '_feature_registry', '_feature_id_cache',
        '_rationalized_state', '_last_price', '_prev_last_price',
        '_quote_feed', '_quote_idx',  # For arbitrary last_price offset lookups
    )
    
    def __init__(
        self,
        feeds: MultiTFFeedStore,
        exec_idx: int,
        high_tf_idx: int | None,
        med_tf_idx: int | None,
        exchange,  # SimulatedExchange reference
        mark_price: float,
        mark_price_source: str,
        history_config: HistoryConfig | None = None,
        history_ready: bool = True,
        rollups: dict[str, float] | None = None,
        incremental_state: "MultiTFIncrementalState | None" = None,
        feature_registry: "FeatureRegistry | None" = None,
        rationalized_state: "RationalizedState | None" = None,
        last_price: float | None = None,
        prev_last_price: float | None = None,
        quote_feed: "FeedStore | None" = None,
        quote_idx: int | None = None,
        low_tf_idx: int | None = None,
    ):
        """
        Initialize snapshot view for 3-feed + exec role system.

        Args:
            feeds: MultiTFFeedStore with all precomputed data
            exec_idx: Current exec bar index (on the exec_role feed)
            high_tf_idx: Current high_tf context index
            med_tf_idx: Current med_tf context index
            exchange: SimulatedExchange reference
            mark_price: Mark price for position valuation (PnL, liquidation, risk).
            mark_price_source: Provenance ("mark_1m" | "approx_from_ohlcv_1m")
            history_config: History configuration
            history_ready: Whether history windows are filled
            rollups: Optional px.rollup.* values from 1m accumulation
            incremental_state: Optional MultiTFIncrementalState for structure access
            feature_registry: Optional FeatureRegistry for feature_id-based access
            rationalized_state: Optional RationalizedState for Layer 2 access
            last_price: 1m ticker close for SIGNAL EVALUATION.
            prev_last_price: Previous 1m action price (for crossover operators).
            quote_feed: Optional 1m FeedStore for arbitrary last_price offset lookups.
            quote_idx: Current 1m bar index in quote_feed.
            low_tf_idx: Current low_tf context index (if not same as exec)
        """
        self._feeds = feeds
        self._incremental_state = incremental_state
        self._feature_registry = feature_registry
        self._rationalized_state = rationalized_state
        self._feature_id_cache: dict[str, tuple[str, str]] = {}  # feature_id -> (tf, key)
        self.symbol = feeds.exec_feed.symbol
        self.exec_tf = feeds.exec_feed.tf
        self.exec_idx = exec_idx
        self.tf_mapping = feeds.tf_mapping

        # Resolve exec_role
        exec_role = getattr(feeds, 'exec_role', 'low_tf')

        # Build low_tf context (always present)
        if exec_role == "low_tf":
            # Exec is low_tf: use exec_idx
            self.low_tf_ctx = TFContext(
                feed=feeds.low_tf_feed,
                current_idx=exec_idx,
                ready=True,
            )
        else:
            # Exec is not low_tf: use low_tf_idx if provided
            low_idx = low_tf_idx if low_tf_idx is not None else 0
            self.low_tf_ctx = TFContext(
                feed=feeds.low_tf_feed,
                current_idx=low_idx,
                ready=True,
            )

        # Build med_tf context
        if feeds.med_tf_feed is not None:
            if exec_role == "med_tf":
                # Exec is med_tf: use exec_idx
                self.med_tf_ctx = TFContext(
                    feed=feeds.med_tf_feed,
                    current_idx=exec_idx,
                    ready=True,
                )
            else:
                # Use provided med_tf_idx
                med_idx = med_tf_idx if med_tf_idx is not None else 0
                self.med_tf_ctx = TFContext(
                    feed=feeds.med_tf_feed,
                    current_idx=med_idx,
                    ready=True,
                )
        else:
            # No separate med_tf feed: aliased to low_tf
            if exec_role == "med_tf":
                # Exec is med_tf, but med_tf_feed is None (aliased to low_tf)
                # Create a TFContext using low_tf_feed but with exec_idx
                self.med_tf_ctx = TFContext(
                    feed=feeds.low_tf_feed,
                    current_idx=exec_idx,
                    ready=True,
                )
            else:
                # Not exec role, just alias to low_tf
                self.med_tf_ctx = self.low_tf_ctx

        # Build high_tf context
        if feeds.high_tf_feed is not None:
            if exec_role == "high_tf":
                # Exec is high_tf: use exec_idx
                self.high_tf_ctx = TFContext(
                    feed=feeds.high_tf_feed,
                    current_idx=exec_idx,
                    ready=True,
                )
            else:
                # Use provided high_tf_idx
                high_idx = high_tf_idx if high_tf_idx is not None else 0
                self.high_tf_ctx = TFContext(
                    feed=feeds.high_tf_feed,
                    current_idx=high_idx,
                    ready=True,
                )
        else:
            # No separate high_tf feed: aliased to med_tf
            if exec_role == "high_tf":
                # Exec is high_tf, but high_tf_feed is None (aliased to med_tf)
                # Create a TFContext using med_tf_feed but with exec_idx
                # Note: med_tf_ctx.feed should be the correct feed (or aliased to low_tf)
                self.high_tf_ctx = TFContext(
                    feed=self.med_tf_ctx.feed,
                    current_idx=exec_idx,
                    ready=True,
                )
            else:
                # Not exec role, just alias to med_tf
                self.high_tf_ctx = self.med_tf_ctx

        # Set exec_ctx as alias to the appropriate context
        if exec_role == "low_tf":
            self.exec_ctx = self.low_tf_ctx
        elif exec_role == "med_tf":
            self.exec_ctx = self.med_tf_ctx
        else:  # "high_tf"
            self.exec_ctx = self.high_tf_ctx

        self.ts_close = self.exec_ctx.ts_close
        
        self.exchange = exchange
        self.mark_price = mark_price
        self.mark_price_source = mark_price_source
        # last_price: 1m action price. Defaults to mark_price if not provided.
        self._last_price = last_price if last_price is not None else mark_price
        # prev_last_price: previous 1m action price (for crossover operators)
        self._prev_last_price = prev_last_price
        # quote_feed + quote_idx: for arbitrary last_price offset lookups (window operators)
        self._quote_feed = quote_feed
        self._quote_idx = quote_idx

        self.history_config = history_config or DEFAULT_HISTORY_CONFIG
        self.history_ready = history_ready

        # Phase 3: 1m rollups (px.rollup.*)
        self._rollups = rollups or {}

        # Build namespace resolvers (instance variable for hot-path performance)
        self._resolvers = self._build_resolvers()
    
    # =========================================================================
    # Readiness
    # =========================================================================
    
    @property
    def ready(self) -> bool:
        """Check if snapshot is ready for strategy evaluation."""
        return (
            self.low_tf_ctx.ready and
            self.med_tf_ctx.ready and
            self.high_tf_ctx.ready and
            self.history_ready
        )

    @property
    def not_ready_reasons(self) -> list:
        """Get list of reasons why snapshot is not ready."""
        reasons = []
        if not self.low_tf_ctx.ready:
            reasons.append(f"low_tf: {self.low_tf_ctx.not_ready_reason}")
        if not self.med_tf_ctx.ready:
            reasons.append(f"med_tf: {self.med_tf_ctx.not_ready_reason}")
        if not self.high_tf_ctx.ready:
            reasons.append(f"high_tf: {self.high_tf_ctx.not_ready_reason}")
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
    def last_price(self) -> float:
        """
        Current 1m ticker close - for SIGNAL EVALUATION.

        Semantics:
        - Backtest: 1m bar close from the action loop
        - Live (future): WebSocket ticker.lastPrice (actual last trade)

        Use Case:
        - Signal evaluation at 1m granularity
        - Entry/exit price decisions
        - Reflects actual orderbook activity

        NOTE: This is semantically different from mark_price in live trading.
        In volatile markets, last_price reflects actual trades while mark_price
        is index-derived and more stable. In backtest, both default to 1m close.

        See also: mark_price (for PnL/liquidation), close (eval_tf bar close)
        """
        return self._last_price

    @property
    def volume(self) -> float:
        """Current exec bar volume."""
        return self.exec_ctx.volume
    
    # =========================================================================
    # Current Indicator Accessors (Exec TF)
    # =========================================================================
    
    @property
    def ema_fast(self) -> float | None:
        """Current exec EMA fast value."""
        return self.exec_ctx.get_indicator("ema_fast")
    
    @property
    def ema_slow(self) -> float | None:
        """Current exec EMA slow value."""
        return self.exec_ctx.get_indicator("ema_slow")
    
    @property
    def rsi(self) -> float | None:
        """Current exec RSI value."""
        return self.exec_ctx.get_indicator("rsi")
    
    @property
    def atr(self) -> float | None:
        """Current exec ATR value."""
        return self.exec_ctx.get_indicator("atr")
    
    def indicator(self, name: str) -> float | None:
        """Get current exec indicator by name. Returns None if undeclared."""
        return self.exec_ctx.get_indicator(name)
    
    def indicator_strict(self, name: str) -> float:
        """
        Get current exec indicator by name, raising if undeclared.
        
        Use this when the indicator MUST be present (Play declared it).
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
    
    def prev_ema_fast(self, lookback: int = 1) -> float | None:
        """Get previous EMA fast value (for crossover detection)."""
        return self._get_prev_indicator("ema_fast", lookback)
    
    def prev_ema_slow(self, lookback: int = 1) -> float | None:
        """Get previous EMA slow value (for crossover detection)."""
        return self._get_prev_indicator("ema_slow", lookback)
    
    def prev_rsi(self, lookback: int = 1) -> float | None:
        """Get previous RSI value."""
        return self._get_prev_indicator("rsi", lookback)
    
    def prev_atr(self, lookback: int = 1) -> float | None:
        """Get previous ATR value."""
        return self._get_prev_indicator("atr", lookback)
    
    def prev_indicator(self, name: str, lookback: int = 1) -> float | None:
        """Get previous indicator value by name."""
        return self._get_prev_indicator(name, lookback)
    
    def _get_prev_indicator(self, name: str, lookback: int) -> float | None:
        """Internal: get previous indicator via direct index offset."""
        if lookback < 1:
            raise ValueError("lookback must be >= 1")

        prev_idx = self.exec_idx - lookback
        if prev_idx >= 0:
            if name in self._feeds.exec_feed.indicators:
                val = self._feeds.exec_feed.indicators[name][prev_idx]
                if not np.isnan(val):
                    return float(val)

        return None
    
    def bars_exec_low(self, n: int) -> float | None:
        """Get lowest low of last n exec bars (for structure SL)."""
        if n < 1:
            raise ValueError("n must be >= 1")
        
        start_idx = max(0, self.exec_idx - n + 1)
        end_idx = self.exec_idx + 1
        
        if start_idx >= end_idx:
            return None
        
        return float(np.min(self._feeds.exec_feed.low[start_idx:end_idx]))
    
    def bars_exec_high(self, n: int) -> float | None:
        """Get highest high of last n exec bars (for structure SL)."""
        if n < 1:
            raise ValueError("n must be >= 1")
        
        start_idx = max(0, self.exec_idx - n + 1)
        end_idx = self.exec_idx + 1
        
        if start_idx >= end_idx:
            return None
        
        return float(np.max(self._feeds.exec_feed.high[start_idx:end_idx]))
    
    def prev_close(self, lookback: int = 1) -> float | None:
        """Get previous close price."""
        prev_idx = self.exec_idx - lookback
        if prev_idx < 0:
            return None
        return float(self._feeds.exec_feed.close[prev_idx])
    
    def prev_high(self, lookback: int = 1) -> float | None:
        """Get previous high price."""
        prev_idx = self.exec_idx - lookback
        if prev_idx < 0:
            return None
        return float(self._feeds.exec_feed.high[prev_idx])
    
    def prev_low(self, lookback: int = 1) -> float | None:
        """Get previous low price."""
        prev_idx = self.exec_idx - lookback
        if prev_idx < 0:
            return None
        return float(self._feeds.exec_feed.low[prev_idx])
    
    # =========================================================================
    # high_tf/med_tf Accessors (forward-filled context)
    # =========================================================================

    @property
    def high_tf_ema_fast(self) -> float | None:
        """high_tf EMA fast (forward-filled from last close)."""
        return self.high_tf_ctx.get_indicator("ema_fast")

    @property
    def high_tf_ema_slow(self) -> float | None:
        """high_tf EMA slow (forward-filled from last close)."""
        return self.high_tf_ctx.get_indicator("ema_slow")

    @property
    def high_tf_rsi(self) -> float | None:
        """high_tf RSI (forward-filled from last close)."""
        return self.high_tf_ctx.get_indicator("rsi")

    @property
    def med_tf_ema_fast(self) -> float | None:
        """med_tf EMA fast (forward-filled from last close)."""
        return self.med_tf_ctx.get_indicator("ema_fast")

    @property
    def med_tf_ema_slow(self) -> float | None:
        """med_tf EMA slow (forward-filled from last close)."""
        return self.med_tf_ctx.get_indicator("ema_slow")

    @property
    def med_tf_rsi(self) -> float | None:
        """med_tf RSI (forward-filled from last close)."""
        return self.med_tf_ctx.get_indicator("rsi")

    def low_tf_indicator(self, name: str) -> float | None:
        """Get low_tf indicator by name."""
        return self.low_tf_ctx.get_indicator(name)

    def med_tf_indicator(self, name: str) -> float | None:
        """Get med_tf indicator by name."""
        return self.med_tf_ctx.get_indicator(name)

    def high_tf_indicator(self, name: str) -> float | None:
        """Get high_tf indicator by name."""
        return self.high_tf_ctx.get_indicator(name)

    # =========================================================================
    # Layer 2: Rationalized State Access (W2)
    # =========================================================================

    @property
    def rationalized_state(self) -> "RationalizedState | None":
        """Get current rationalized state (Layer 2)."""
        return self._rationalized_state

    def get_rationalized_value(self, field: str) -> Any:
        """
        Get a value from rationalized state.

        Accessible via get_feature_value("rationalize", field=...).

        Args:
            field: Field name (e.g., "confluence_score", "regime", "alignment")

        Returns:
            Value or None if not available
        """
        if self._rationalized_state is None:
            return None

        # Check derived values first
        derived = self._rationalized_state.derived_values
        if field in derived:
            return derived[field]

        # Check core properties
        match field:
            case "transition_count":
                return self._rationalized_state.transition_count
            case "has_transitions":
                return self._rationalized_state.has_transitions
            case "regime":
                return self._rationalized_state.regime.value
            case "bar_idx":
                return self._rationalized_state.bar_idx
            case _:
                return None

    @property
    def available_low_tf_indicators(self) -> list:
        """Get list of available low_tf indicator keys."""
        return list(self._feeds.low_tf_feed.indicators.keys())

    @property
    def available_med_tf_indicators(self) -> list:
        """Get list of available med_tf indicator keys."""
        if self._feeds.med_tf_feed is None:
            return self.available_low_tf_indicators  # Alias
        return list(self._feeds.med_tf_feed.indicators.keys())

    @property
    def available_high_tf_indicators(self) -> list:
        """Get list of available high_tf indicator keys."""
        if self._feeds.high_tf_feed is None:
            return self.available_med_tf_indicators  # Alias
        return list(self._feeds.high_tf_feed.indicators.keys())
    
    # =========================================================================
    # Unified Feature Lookup API (for PlaySignalEvaluator)
    # =========================================================================
    
    def get_feature(
        self,
        indicator_key: str,
        tf_role: str = "exec",
        offset: int = 0,
    ) -> float | None:
        """
        Unified feature lookup API for strategy evaluation.

        Supports both OHLCV and indicator keys across all TF roles.
        Used by PlaySignalEvaluator for condition evaluation.

        Args:
            indicator_key: Key to look up (e.g., "close", "ema_20", "rsi")
            tf_role: TF role ("exec", "high_tf", "med_tf")
            offset: Bar offset (0 = current, 1 = previous, etc.)

        Returns:
            Feature value or None if not available
        """
        # Handle mark_price specially - always returns current mark price
        if indicator_key == "mark_price":
            if offset != 0:
                raise ValueError("mark_price offset not yet supported - use offset=0")
            return self.mark_price

        # Handle last_price - 1m action price (ticker close)
        if indicator_key == "last_price":
            if offset == 0:
                return self.last_price
            elif offset == 1:
                if self._prev_last_price is None:
                    raise ValueError("last_price offset=1 requires prev_last_price (not available)")
                return self._prev_last_price
            else:
                # For offset > 1, use quote_feed to look up historical 1m prices
                if self._quote_feed is None or self._quote_idx is None:
                    raise ValueError(
                        f"last_price offset={offset} requires quote_feed (not available). "
                        "Window operators with last_price need 1m quote data. "
                        "Ensure 1m data is synced for this symbol (1m is always loaded separately for quote feed)."
                    )
                target_idx = self._quote_idx - offset
                if target_idx < 0:
                    return None  # Not enough history
                return float(self._quote_feed.close[target_idx])

        # Handle funding_rate - market data field (Phase 12)
        if indicator_key == "funding_rate":
            feed = self._feeds.exec_feed
            if feed.funding_rate is None:
                return None
            target_idx = self.exec_idx - offset
            if target_idx < 0 or target_idx >= len(feed.funding_rate):
                return None
            return float(feed.funding_rate[target_idx])

        # Handle open_interest - market data field (Phase 12)
        if indicator_key == "open_interest":
            feed = self._feeds.exec_feed
            if feed.open_interest is None:
                return None
            target_idx = self.exec_idx - offset
            if target_idx < 0 or target_idx >= len(feed.open_interest):
                return None
            return float(feed.open_interest[target_idx])

        # Get the appropriate context
        # In single-TF mode, contexts may alias to each other
        if tf_role == "exec":
            ctx = self.exec_ctx
        elif tf_role == "low_tf":
            ctx = self.low_tf_ctx
        elif tf_role == "med_tf":
            ctx = self.med_tf_ctx
        elif tf_role == "high_tf":
            ctx = self.high_tf_ctx
        else:
            return None

        # Get feed from context (handles single-TF mode where high_tf/med_tf ctx = exec_ctx)
        feed = ctx.feed
        
        # Compute target index
        target_idx = ctx.current_idx - offset
        if target_idx < 0 or target_idx >= feed.length:
            return None
        
        # Handle OHLCV keys
        if indicator_key == "open":
            return float(feed.open[target_idx])
        elif indicator_key == "high":
            return float(feed.high[target_idx])
        elif indicator_key == "low":
            return float(feed.low[target_idx])
        elif indicator_key == "close":
            return float(feed.close[target_idx])
        elif indicator_key == "volume":
            return float(feed.volume[target_idx])
        
        # Handle indicator keys
        if indicator_key not in feed.indicators:
            return None
        val = feed.indicators[indicator_key][target_idx]
        if np.isnan(val):
            return None
        return float(val)
    
    def has_feature(self, indicator_key: str, tf_role: str = "exec") -> bool:
        """
        Check if a feature is declared for a TF role.

        Args:
            indicator_key: Key to check
            tf_role: TF role ("exec", "high_tf", "med_tf")

        Returns:
            True if feature is available
        """
        # OHLCV is always available
        if indicator_key in ("open", "high", "low", "close", "volume"):
            return True

        # mark_price is always available
        if indicator_key == "mark_price":
            return True

        # last_price is always available (1m action price)
        if indicator_key == "last_price":
            return True

        # Market data fields (Phase 12) - check if arrays are loaded
        if indicator_key == "funding_rate":
            return self._feeds.exec_feed.funding_rate is not None
        if indicator_key == "open_interest":
            return self._feeds.exec_feed.open_interest is not None

        # Get context for TF role (handles single-TF mode where contexts alias)
        if tf_role == "exec":
            ctx = self.exec_ctx
        elif tf_role == "low_tf":
            ctx = self.low_tf_ctx
        elif tf_role == "med_tf":
            ctx = self.med_tf_ctx
        elif tf_role == "high_tf":
            ctx = self.high_tf_ctx
        else:
            return False

        return indicator_key in ctx.feed.indicators

    def get_feature_value(
        self,
        feature_id: str,
        field: str | None = None,
        offset: int = 0,
    ) -> float | None:
        """
        Get feature value for DSL evaluation.

        This is the expected API for the DSL evaluator (dsl_eval.py).
        Maps feature_id to indicator_key and uses the feature's declared TF.

        Special feature_ids:
        - feature_id="rationalize" -> Layer 2 rationalized state values
          (confluence_score, alignment, regime, etc.)

        For multi-output indicators like MACD:
        - feature_id="macd", field="histogram" -> indicator_key="macd_histogram"
        - feature_id="adx", field="dmp" -> indicator_key="adx_dmp"

        For multi-TF features:
        - Looks up the feature's TF from the registry
        - Maps TF to role (low_tf/med_tf/high_tf) via tf_mapping

        Args:
            feature_id: Feature ID (e.g., "ema_9", "rsi_14", "macd", "ema_50_4h", "rationalize")
            field: Optional field for multi-output indicators (e.g., "histogram", "signal")
                   For rationalize: required field name (e.g., "confluence_score", "regime")
            offset: Bar offset (0 = current, 1 = previous). Note: rationalize ignores offset.

        Returns:
            Feature value or None if not available
        """
        # Handle special "rationalize" feature_id for Layer 2 state
        if feature_id == "rationalize":
            if field is None:
                return None
            return self.get_rationalized_value(field)

        # Handle special price features (action-level, not from feeds)
        if feature_id == "last_price":
            if offset == 0:
                return self.last_price
            elif offset == 1:
                if self._prev_last_price is None:
                    raise ValueError("last_price offset=1 requires prev_last_price (not available)")
                return self._prev_last_price
            else:
                # For offset > 1, use quote_feed to look up historical 1m prices
                if self._quote_feed is None or self._quote_idx is None:
                    raise ValueError(
                        f"last_price offset={offset} requires quote_feed (not available). "
                        "Window operators with last_price need 1m quote data. "
                        "Ensure 1m data is synced for this symbol (1m is always loaded separately for quote feed)."
                    )
                target_idx = self._quote_idx - offset
                if target_idx < 0:
                    return None  # Not enough history
                return float(self._quote_feed.close[target_idx])

        if feature_id == "mark_price":
            if offset != 0:
                raise ValueError("mark_price offset not yet supported - use offset=0")
            return self.mark_price

        # Handle dotted structure paths from higher-TF structure references
        # e.g. "med_tf_4h.trend_4h.direction" or "high_tf_D.trend_d.direction"
        # These come from the DSL parser when the LHS is a dotted string
        if "." in feature_id and self._incremental_state is not None:
            parts = feature_id.split(".")
            if len(parts) >= 3:
                prefix = parts[0]  # e.g. "med_tf_4h" or "high_tf_D"
                struct_key = parts[1]  # e.g. "trend_4h"
                struct_field = ".".join(parts[2:])  # e.g. "direction"
                # Check med_tf structures
                for tf_name in self._incremental_state.med_tf:
                    if prefix == f"med_tf_{tf_name}":
                        tf_state = self._incremental_state.med_tf[tf_name]
                        if struct_key in tf_state.structures:
                            try:
                                path = f"med_tf_{tf_name}.{struct_key}.{struct_field}"
                                value = self._incremental_state.get_value(path)
                                if isinstance(value, float):
                                    if math.isnan(value):
                                        return None
                                if isinstance(value, str):
                                    return None
                                return float(value) if value is not None else None
                            except KeyError:
                                return None
                # Check high_tf structures
                for tf_name in self._incremental_state.high_tf:
                    if prefix == f"high_tf_{tf_name}":
                        tf_state = self._incremental_state.high_tf[tf_name]
                        if struct_key in tf_state.structures:
                            try:
                                path = f"high_tf_{tf_name}.{struct_key}.{struct_field}"
                                value = self._incremental_state.get_value(path)
                                if isinstance(value, float):
                                    if math.isnan(value):
                                        return None
                                if isinstance(value, str):
                                    return None
                                return float(value) if value is not None else None
                            except KeyError:
                                return None
                # Check exec structures (e.g. "exec.swing.high_level" - unlikely but safe)
                if prefix == "exec" and struct_key in self._incremental_state.exec.structures:
                    try:
                        path = f"exec.{struct_key}.{struct_field}"
                        value = self._incremental_state.get_value(path)
                        if isinstance(value, float):
                            if math.isnan(value):
                                return None
                        if isinstance(value, str):
                            return None
                        return float(value) if value is not None else None
                    except KeyError:
                        return None

        # Check if this is a structure (requires feature registry)
        if self._feature_registry is not None:
            feature = self._feature_registry.get_or_none(feature_id)
            if feature is not None and feature.is_structure:
                # Route to get_structure for incremental structure access
                if field is None:
                    return None  # Structures require a field

                # Search for structure in incremental state
                # 1. First check exec structures
                # 2. Then check high_tf structures by feature's declared TF
                value = self._get_structure_value(feature_id, field, feature.tf)

                # Handle NaN as None
                if value is not None and isinstance(value, float):
                    if math.isnan(value):
                        return None
                return value

        # Build the indicator key dynamically
        # - Single-output indicators: field is None/empty/"value" -> key = feature_id
        #   ("value" is the DSL default field for single-output indicators)
        # - Multi-output indicators: field is set to actual output -> key = feature_id + "_" + field
        #   For multi-output with field=None/"value", resolve to feature_id + "_" + primary_output
        #   The field values come from INDICATOR_REGISTRY output_keys (e.g., "histogram", "signal")
        if field and field != "value":
            indicator_key = f"{feature_id}_{field}"
        else:
            # Check if this is a multi-output indicator (e.g., anchored_vwap with "value"+"bars_since_anchor")
            # If so, bare feature_id won't match FeedStore — resolve to primary output key
            indicator_key = feature_id
            if self._feature_registry is not None:
                feat = self._feature_registry.get_or_none(feature_id)
                if feat is not None and feat.indicator_type:
                    from src.backtest.indicator_registry import get_registry
                    reg = get_registry()
                    if reg.is_multi_output(feat.indicator_type):
                        primary = reg.get_primary_output(feat.indicator_type)
                        if primary:
                            indicator_key = f"{feature_id}_{primary}"

        # Determine TF role from feature registry
        tf_role = "exec"  # Default
        if self._feature_registry is not None:
            feature = self._feature_registry.get_or_none(feature_id)
            if feature is not None:
                feature_tf = feature.tf
                # Map TF to role via tf_mapping
                if feature_tf == self.tf_mapping.get("high_tf"):
                    tf_role = "high_tf"
                elif feature_tf == self.tf_mapping.get("med_tf"):
                    tf_role = "med_tf"
                elif feature_tf == self.tf_mapping.get("low_tf"):
                    tf_role = "low_tf"
                # else: fallback to exec (which is alias to one of the above)

        return self.get_feature(indicator_key, tf_role=tf_role, offset=offset)

    # =========================================================================
    # Staleness (for multi-TF forward-fill validation)
    # =========================================================================

    @property
    def high_tf_is_stale(self) -> bool:
        """Check if high_tf features are stale (forward-filled)."""
        return self.ts_close > self.high_tf_ctx.ts_close

    @property
    def med_tf_is_stale(self) -> bool:
        """Check if med_tf features are stale (forward-filled)."""
        return self.ts_close > self.med_tf_ctx.ts_close

    @property
    def high_tf_ctx_ts_close(self) -> datetime:
        """Get high_tf context timestamp."""
        return self.high_tf_ctx.ts_close

    @property
    def med_tf_ctx_ts_close(self) -> datetime:
        """Get med_tf context timestamp."""
        return self.med_tf_ctx.ts_close
    
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
    def position_side(self) -> str | None:
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
    # 1m Rollup Accessors (Phase 3: px.rollup.*)
    # =========================================================================

    @property
    def rollup_min_1m(self) -> float:
        """Minimum 1m low since last exec close."""
        return self._rollups.get("px.rollup.min_1m", float('inf'))

    @property
    def rollup_max_1m(self) -> float:
        """Maximum 1m high since last exec close."""
        return self._rollups.get("px.rollup.max_1m", float('-inf'))

    @property
    def rollup_bars_1m(self) -> int:
        """Count of 1m bars since last exec close."""
        return int(self._rollups.get("px.rollup.bars_1m", 0))

    @property
    def rollup_open_1m(self) -> float:
        """First 1m open since last exec close."""
        return self._rollups.get("px.rollup.open_1m", 0.0)

    @property
    def rollup_close_1m(self) -> float:
        """Last 1m close since last exec close."""
        return self._rollups.get("px.rollup.close_1m", 0.0)

    @property
    def rollup_volume_1m(self) -> float:
        """Sum of 1m volume since last exec close."""
        return self._rollups.get("px.rollup.volume_1m", 0.0)

    @property
    def rollup_price_range_1m(self) -> float:
        """Price range (max - min) of 1m bars since last exec close."""
        if self.rollup_bars_1m == 0:
            return 0.0
        return self.rollup_max_1m - self.rollup_min_1m

    def get_rollup(self, key: str) -> float | None:
        """
        Get rollup value by key.

        Args:
            key: Rollup key (e.g., "px.rollup.min_1m", "px.rollup.max_1m")

        Returns:
            Rollup value or None if key not found
        """
        return self._rollups.get(key)

    @property
    def has_rollups(self) -> bool:
        """Check if rollups are available for this snapshot."""
        return bool(self._rollups) and self.rollup_bars_1m > 0

    @property
    def rollups(self) -> dict[str, float]:
        """Get all rollup values as a dict."""
        return dict(self._rollups)

    # =========================================================================
    # Market Data Accessors (Phase 12: Funding Rate, Open Interest)
    # =========================================================================

    @property
    def funding_rate(self) -> float | None:
        """
        Current funding rate (last known rate at this bar).

        Returns the funding rate that will be applied at the next 8h settlement.
        Between settlements, this is the rate from the last settlement.

        Returns:
            Funding rate as decimal (e.g., 0.0001 = 0.01%), or None if unavailable.
        """
        feed = self._feeds.exec_feed
        if feed.funding_rate is None:
            return None
        return float(feed.funding_rate[self.exec_idx])

    @property
    def open_interest(self) -> float | None:
        """
        Current open interest (forward-filled from last known OI).

        Returns the total open interest for the symbol at this bar.

        Returns:
            Open interest in contracts/units, or None if unavailable.
        """
        feed = self._feeds.exec_feed
        if feed.open_interest is None:
            return None
        return float(feed.open_interest[self.exec_idx])

    @property
    def has_market_data(self) -> bool:
        """Check if market data (funding/OI) is available."""
        feed = self._feeds.exec_feed
        return feed.funding_rate is not None or feed.open_interest is not None

    # =========================================================================
    # Incremental Structure Accessors (Phase 6)
    # =========================================================================

    def get_structure(self, path: str) -> float:
        """
        Get structure value by path.

        Phase 6: Provides O(1) access to incremental structure values.
        Falls back to FeedStore structures for legacy market_structure_blocks.

        Args:
            path: Dot-separated path like "swing.high_level" or "trend.direction"
                  For exec TF: "swing.high_level"
                  For high_tf: "high_tf_1h.swing.high_level"

        Returns:
            The structure value

        Raises:
            KeyError: If path is invalid, with actionable suggestion
        """
        if self._incremental_state is None:
            raise KeyError(
                f"No incremental state available. "
                f"Add 'structures:' section to Play. "
                f"See docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md"
            )

        # Try direct lookup (for paths like "swing.high_level")
        parts = path.split(".")
        if len(parts) < 2:
            raise KeyError(
                f"Invalid structure path: '{path}'. "
                f"Expected format: '<struct_key>.<output_key>'"
            )

        struct_key = parts[0]
        output_key = ".".join(parts[1:])

        # Check exec state
        if struct_key in self._incremental_state.exec.structures:
            internal_path = f"exec.{struct_key}.{output_key}"
            return self._incremental_state.get_value(internal_path)  # type: ignore[return-value]

        # Check if it's a high_tf path (starts with high_tf_)
        if struct_key.startswith("high_tf_"):
            # Path format: "high_tf_<tf>.<struct_key>.<output_key>"
            tf_name = parts[0][4:]  # Remove "high_tf_" prefix
            # P2-005 FIX: Validate high_tf path has enough parts before accessing
            if len(parts) < 3:
                raise KeyError(
                    f"Invalid high_tf structure path: '{path}'. "
                    f"Expected format: 'high_tf_<tf>.<struct_key>.<output_key>'"
                )
            if tf_name in self._incremental_state.high_tf:
                actual_struct_key = parts[1]
                actual_output_key = ".".join(parts[2:])
                internal_path = f"high_tf_{tf_name}.{actual_struct_key}.{actual_output_key}"
                return self._incremental_state.get_value(internal_path)  # type: ignore[return-value]

        # Structure not found
        available_exec = self._incremental_state.exec.list_structures()
        available_high_tf = []
        for high_tf_name in self._incremental_state.list_high_tfs():
            for s_key in self._incremental_state.high_tf[high_tf_name].list_structures():
                available_high_tf.append(f"high_tf_{high_tf_name}.{s_key}")

        all_available = available_exec + available_high_tf
        raise KeyError(
            f"Structure '{struct_key}' not found. "
            f"Available: {all_available}. "
            f"Add structure to Play 'structures:' section."
        )

    @property
    def has_incremental_state(self) -> bool:
        """Check if incremental state is available."""
        return self._incremental_state is not None

    def _get_structure_value(
        self, feature_id: str, field: str, feature_tf: str
    ) -> float | None:
        """
        Get structure value by searching in the appropriate location.

        Searches based on where the structure is actually stored in incremental state,
        determined by the feature's declared TF in the Play.

        Structure storage locations:
        - exec.structures: Structures on the execution timeframe
        - high_tf[tf].structures: Structures on any non-exec TF (low_tf, med_tf, or high_tf)
          The "high_tf" dict stores ALL non-exec TFs despite the name.

        Args:
            feature_id: The structure's feature ID from the Play
            field: The output field name (e.g., "high_level", "level_0.618")
            feature_tf: The TF declared for this feature in the Play

        Returns:
            Structure value or None if not found
        """
        if self._incremental_state is None:
            return None

        # Check if structure is in exec state (feature TF matches exec TF)
        if feature_id in self._incremental_state.exec.structures:
            try:
                path = f"exec.{feature_id}.{field}"
                return self._incremental_state.get_value(path)  # type: ignore[return-value]
            except KeyError:
                return None

        # Check if structure is in med_tf state
        if feature_tf in self._incremental_state.med_tf:
            tf_state = self._incremental_state.med_tf[feature_tf]
            if feature_id in tf_state.structures:
                try:
                    path = f"med_tf_{feature_tf}.{feature_id}.{field}"
                    return self._incremental_state.get_value(path)  # type: ignore[return-value]
                except KeyError:
                    return None

        # Check if structure is in high_tf state
        if feature_tf in self._incremental_state.high_tf:
            tf_state = self._incremental_state.high_tf[feature_tf]
            if feature_id in tf_state.structures:
                try:
                    path = f"high_tf_{feature_tf}.{feature_id}.{field}"
                    return self._incremental_state.get_value(path)  # type: ignore[return-value]
                except KeyError:
                    return None

        # Structure not found in any location
        return None

    def list_structure_paths(self) -> list[str]:
        """
        List all available incremental structure paths.

        Returns:
            List of valid "struct_key.output_key" paths
        """
        if self._incremental_state is None:
            return []
        return self._incremental_state.list_all_paths()

    # =========================================================================
    # Feature Registry Access (Feature ID-based lookup)
    # =========================================================================

    def get_by_feature_id(
        self,
        feature_id: str,
        offset: int = 0,
        field: str = "value",
    ) -> float | None:
        """
        Get feature value by Feature ID (from FeatureRegistry).

        This is the primary access method for the new Feature Registry architecture.
        Features are referenced by unique ID, and the registry provides TF mapping.

        Args:
            feature_id: Unique feature ID from Play features list
            offset: Bar offset (0 = current, 1 = previous, etc.)
            field: Output field for multi-output features (default: "value")

        Returns:
            Feature value or None if not available

        Raises:
            KeyError: If feature_id is not in registry
        """
        if self._feature_registry is None:
            raise KeyError(
                f"No FeatureRegistry available. Cannot resolve feature_id '{feature_id}'. "
                f"Use Play with 'features:' section."
            )

        # Check cache first
        cache_key = f"{feature_id}:{field}"
        cached = self._feature_id_cache.get(cache_key)

        if cached is None:
            # Look up feature in registry
            feature = self._feature_registry.get(feature_id)
            tf = feature.tf

            # Determine the indicator key
            if feature.is_indicator:
                # For indicators, the key is the feature ID or output_keys[0]
                if feature.output_keys:
                    # Multi-output indicator - use field to select output
                    if field == "value":
                        indicator_key = feature.output_keys[0]
                    else:
                        # Find matching output key
                        for ok in feature.output_keys:
                            if ok.endswith(f"_{field}") or ok == field:
                                indicator_key = ok
                                break
                        else:
                            indicator_key = feature.id
                else:
                    indicator_key = feature.id
            else:
                # For structures, the key is the structure type output
                indicator_key = f"structure.{feature_id}.{field}"

            cached = (tf, indicator_key)
            self._feature_id_cache[cache_key] = cached

        tf, indicator_key = cached

        # Check if this is a structure access
        if indicator_key.startswith("structure."):
            # Use structure accessor
            path = indicator_key[10:]  # Remove "structure." prefix
            try:
                return self.get_structure(path)
            except KeyError:
                return None

        # Get the appropriate feed for this TF
        feed = self._get_feed_for_tf(tf)
        if feed is None:
            return None

        # Get the context index for this TF
        ctx_idx = self._get_context_idx_for_tf(tf)
        if ctx_idx is None:
            return None

        # Compute target index with offset
        target_idx = ctx_idx - offset
        if target_idx < 0 or target_idx >= feed.length:
            return None

        # Handle OHLCV keys
        if indicator_key in ("open", "high", "low", "close", "volume"):
            arr = getattr(feed, indicator_key)
            return float(arr[target_idx])

        # Handle indicator keys
        if indicator_key not in feed.indicators:
            return None
        val = feed.indicators[indicator_key][target_idx]
        if np.isnan(val):
            return None
        return float(val)

    def _get_feed_for_tf(self, tf: str) -> FeedStore | None:
        """Get the FeedStore for a specific timeframe."""
        exec_tf = self._feeds.exec_feed.tf

        if tf == exec_tf:
            return self._feeds.exec_feed

        # Check high_tf
        if self._feeds.high_tf_feed is not None and self._feeds.high_tf_feed.tf == tf:
            return self._feeds.high_tf_feed

        # Check med_tf
        if self._feeds.med_tf_feed is not None and self._feeds.med_tf_feed.tf == tf:
            return self._feeds.med_tf_feed

        # TF not found in feeds
        return None

    def _get_context_idx_for_tf(self, tf: str) -> int | None:
        """Get the current context index for a specific timeframe."""
        exec_tf = self._feeds.exec_feed.tf

        if tf == exec_tf:
            return self.exec_ctx.current_idx

        # Check high_tf
        if self._feeds.high_tf_feed is not None and self._feeds.high_tf_feed.tf == tf:
            return self.high_tf_ctx.current_idx

        # Check med_tf
        if self._feeds.med_tf_feed is not None and self._feeds.med_tf_feed.tf == tf:
            return self.med_tf_ctx.current_idx

        return None

    def has_feature_id(self, feature_id: str) -> bool:
        """Check if a feature ID is available in the registry."""
        if self._feature_registry is None:
            return False
        return self._feature_registry.has(feature_id)

    def get_feature_output_type(
        self, feature_id: str, field: str = "value"
    ) -> "FeatureOutputType | None":
        """
        Get the declared output type for a feature field.

        Used by DSL evaluation to determine if a float value should be
        treated as INT (e.g., supertrend.direction is declared INT but
        stored as float64 due to pandas/numpy behavior).

        Args:
            feature_id: Feature ID (e.g., "supertrend_10_3")
            field: Field name (e.g., "direction", "value")

        Returns:
            FeatureOutputType if found, None if registry unavailable or
            feature/field not found.
        """
        if self._feature_registry is None:
            return None
        try:
            return self._feature_registry.get_output_type(feature_id, field)
        except (KeyError, ValueError):
            return None

    # =========================================================================
    # Canonical Path Resolver (DSL Interface)
    # =========================================================================
    #
    # Uses dispatch table pattern for scalability as namespaces grow.
    # Each namespace has a dedicated resolver method.
    #
    # =========================================================================

    def _build_resolvers(self) -> dict[str, Callable]:
        """
        Build namespace resolver dispatch table (instance variable).

        Returns dict mapping namespace -> resolver method.
        Called once in __init__ for hot-path performance.
        """
        return {
            "price": self._resolve_price_path,
            "indicator": self._resolve_indicator_path,
            "structure": self._resolve_structure_path,
            "feature": self._resolve_feature_path,
        }

    def get(self, path: str) -> float | None:
        """
        Canonical path resolver for DSL and strategy access.

        This is the ONLY supported access method for strategies/DSL.
        Snapshot attributes are internal/legacy.

        Supported namespaces:
        - "price.*" -> price data (mark, last)
        - "indicator.*" -> indicator values
        - "structure.*" -> market structure features

        Args:
            path: Dot-separated path (e.g., "price.mark.close")

        Returns:
            Value at path, or None if not available

        Raises:
            ValueError: If path is unknown (forward-only, no silent failures)
        """
        # P2-07: Use LRU-cached path tokens to avoid string split in hot loop
        parts = _tokenize_path(path)
        namespace = parts[0]

        # Dispatch to namespace resolver (instance lookup, no getattr)
        resolver = self._resolvers.get(namespace)
        if resolver is None:
            supported = sorted(self._resolvers.keys())
            raise ValueError(
                f"Unknown path namespace: '{path}'. "
                f"Supported: {', '.join(f'{ns}.*' for ns in supported)}"
            )

        return resolver(parts[1:], path)

    def get_with_offset(self, path: str, offset: int) -> float | None:
        """
        Resolve a path with a bar offset.

        Used by crossover operators to get previous bar values.

        Args:
            path: Dot-separated path (e.g., "indicator.rsi" or "indicator.ema.high_tf")
            offset: Bar offset (0 = current, 1 = previous bar, etc.)

        Returns:
            Value at path with offset, or None if not available

        Note:
            Only indicator paths support offset. Price/structure paths
            return None for offset > 0.
        """
        parts = _tokenize_path(path)
        namespace = parts[0]

        if namespace == "indicator":
            # Extract indicator_key and tf_role from path
            if len(parts) < 2:
                return None
            indicator_key = parts[1]
            tf_role = parts[2] if len(parts) > 2 else "exec"
            return self.get_feature(indicator_key, tf_role, offset)

        # For non-indicator paths, offset only supported for offset=0
        if offset > 0:
            return None

        # Fall back to regular resolution for current bar
        return self.get(path)

    def _resolve_indicator_path(self, parts: list, full_path: str) -> float | None:
        """
        Resolve indicator.* paths.

        Supports:
        - indicator.<key> -> exec TF indicator
        - indicator.<key>.<tf_role> -> specific TF indicator

        Args:
            parts: Path parts after "indicator." (e.g., ["rsi_14"] or ["rsi_14", "high_tf"])
            full_path: Full original path for error messages

        Returns:
            Indicator value or None if NaN/unavailable
        """
        if len(parts) < 1:
            raise ValueError(f"Invalid indicator path: '{full_path}' (missing key)")
        indicator_key = parts[0]
        tf_role = parts[1] if len(parts) > 1 else "exec"
        return self.get_feature(indicator_key, tf_role)

    def _resolve_price_path(self, parts: list, full_path: str) -> float | None:
        """
        Resolve price.* paths.

        Stage 6: price.mark.{close,high,low} supported.
        - price.mark.close → mark_price (from exchange step)
        - price.mark.high → exec-bar high (contract alias)
        - price.mark.low → exec-bar low (contract alias)

        Args:
            parts: Path parts after "price." (e.g., ["mark", "close"])
            full_path: Full original path for error messages
        """
        if len(parts) < 2:
            raise ValueError(
                f"Invalid price path: '{full_path}' "
                f"(expected price.mark.close)"
            )

        price_type = parts[0]  # "mark" or "last"
        field = parts[1]  # "close", "high", "low"

        if price_type == "mark":
            if field == "close":
                return self.mark_price
            elif field == "high":
                # Stage 6: price.mark.high = exec-bar high (contract alias)
                return self.high
            elif field == "low":
                # Stage 6: price.mark.low = exec-bar low (contract alias)
                return self.low
            else:
                raise ValueError(
                    f"Unknown price.mark field: '{field}'. "
                    f"Supported: close, high, low"
                )

        elif price_type == "last":
            raise ValueError(
                "price.last.* is reserved but not implemented. "
                "Use price.mark.close"
            )

        else:
            raise ValueError(
                f"Unknown price type: '{price_type}'. "
                f"Supported: mark"
            )

    def _resolve_structure_path(self, parts: list, full_path: str) -> float | None:
        """
        Resolve structure.* paths.

        Two structure access methods are supported:

        1. Incremental State (`structures:` section in Play)
           - O(1) access via MultiTFIncrementalState
           - Updated bar-by-bar in the engine hot loop
           - Primary method for all new Plays

        2. FeedStore structures (`market_structure_blocks` in Play)
           - Batch-built structures stored in FeedStore.structures dict
           - Legacy support for compatibility

        Resolution priority:
        1. Try incremental state first (if present)
        2. Fall back to FeedStore structures (legacy support)

        Path formats:
        - structure.<block_key>.<field> -> exec TF structure (incremental or FeedStore)
        - structure.<block_key>.zones.<zone_key>.<field> -> zone field (FeedStore only)

        Incremental state paths use MultiTFIncrementalState format internally:
        - "exec.<struct_key>.<output_key>" for exec TF
        - "high_tf_<tf>.<struct_key>.<output_key>" for high_tf

        Args:
            parts: Path parts after "structure." (e.g., ["swing", "high_level"])
            full_path: Full original path for error messages

        Returns:
            Field value at current bar index

        Raises:
            ValueError: If path is invalid or field is not in allowlist
        """
        if len(parts) < 2:
            raise ValueError(
                f"Invalid structure path: '{full_path}' "
                f"(expected structure.<block_key>.<field>)"
            )

        block_key = parts[0]
        field_or_zones = parts[1]

        # =====================================================================
        # PRIMARY PATH: Try incremental state first (O(1) access)
        # =====================================================================
        if self._incremental_state is not None:
            # Check if this is an exec structure
            if block_key in self._incremental_state.exec.structures:
                try:
                    # Build internal path: "exec.<struct_key>.<output_key>"
                    output_key = ".".join(parts[1:])
                    internal_path = f"exec.{block_key}.{output_key}"
                    value = self._incremental_state.get_value(internal_path)
                    # Handle different value types
                    if isinstance(value, str):
                        # String values (e.g., trend direction) - convert to float for DSL
                        # Return None for string values in numeric context
                        return None
                    return float(value)
                except KeyError:
                    # Output key not found - continue to FeedStore fallback
                    pass

            # Check if this is a med_tf structure
            for med_tf_name, med_tf_state in self._incremental_state.med_tf.items():
                if block_key in med_tf_state.structures:
                    try:
                        output_key = ".".join(parts[1:])
                        internal_path = f"med_tf_{med_tf_name}.{block_key}.{output_key}"
                        value = self._incremental_state.get_value(internal_path)
                        if isinstance(value, str):
                            return None
                        return float(value)
                    except KeyError:
                        pass

            # Check if this is a high_tf structure
            for high_tf_name, high_tf_state in self._incremental_state.high_tf.items():
                if block_key in high_tf_state.structures:
                    try:
                        output_key = ".".join(parts[1:])
                        internal_path = f"high_tf_{high_tf_name}.{block_key}.{output_key}"
                        value = self._incremental_state.get_value(internal_path)
                        if isinstance(value, str):
                            return None
                        return float(value)
                    except KeyError:
                        pass

        # =====================================================================
        # FeedStore structures fallback (legacy market_structure_blocks)
        # =====================================================================
        if not self.exec_ctx.feed.has_structure(block_key):
            # Build helpful error message with available structures
            available_feedstore = list(self.exec_ctx.feed.structure_key_map.keys())
            available_incremental = []
            if self._incremental_state is not None:
                available_incremental.extend(self._incremental_state.exec.list_structures())
                for high_tf_name, high_tf_state in self._incremental_state.high_tf.items():
                    for struct_key in high_tf_state.list_structures():
                        available_incremental.append(f"{struct_key} (high_tf_{high_tf_name})")

            all_available = available_feedstore + available_incremental
            available_str = ", ".join(all_available) if all_available else "(none defined)"

            raise ValueError(
                f"Unknown structure block_key '{block_key}'. "
                f"Available: {available_str}. "
                f"Add 'structures:' section to Play."
            )

        # Check for zones namespace (FeedStore structures only)
        if field_or_zones == "zones":
            # structure.<block_key>.zones.<zone_key>.<field>
            if len(parts) < 4:
                raise ValueError(
                    f"Invalid zone path: '{full_path}' "
                    f"(expected structure.<block_key>.zones.<zone_key>.<field>)"
                )
            zone_key = parts[2]
            zone_field = parts[3]

            # Resolve zone field via FeedStore
            return self.exec_ctx.feed.get_zone_field(
                block_key, zone_key, zone_field, self.exec_idx
            )

        # structure.<block_key>.<field> via FeedStore
        field_name = field_or_zones

        # Validate field is in public allowlist
        available_fields = self.exec_ctx.feed.get_structure_fields(block_key)
        if field_name not in available_fields:
            raise ValueError(
                f"Unknown structure field '{field_name}' for block '{block_key}'. "
                f"Valid fields: {available_fields}"
            )

        # Get field value at current exec bar index
        return self.exec_ctx.feed.get_structure_field(
            block_key, field_name, self.exec_idx
        )

    def _resolve_feature_path(self, parts: list, full_path: str) -> float | None:
        """
        Resolve feature.* paths (Feature Registry architecture).

        Supports:
        - feature.<feature_id> -> feature value (primary output)
        - feature.<feature_id>.<field> -> specific output field

        Args:
            parts: Path parts after "feature." (e.g., ["ema_fast"] or ["bbands_20", "upper"])
            full_path: Full original path for error messages

        Returns:
            Feature value or None if NaN/unavailable
        """
        if len(parts) < 1:
            raise ValueError(f"Invalid feature path: '{full_path}' (missing feature_id)")

        feature_id = parts[0]
        field = parts[1] if len(parts) > 1 else "value"

        try:
            return self.get_by_feature_id(feature_id, offset=0, field=field)
        except KeyError as e:
            raise ValueError(str(e))

    def has_path(self, path: str) -> bool:
        """
        Check if a path is available with a valid value.

        Args:
            path: Dot-separated path

        Returns:
            True if path can be resolved to a valid value (not None/NaN)
        """
        try:
            value = self.get(path)
            if value is None:
                return False
            # Check for NaN (numeric missing value)
            if isinstance(value, float) and math.isnan(value):
                return False
            return True
        except ValueError:
            return False

    # =========================================================================
    # Serialization (for debugging only, not in hot loop)
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
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
            "high_tf_is_stale": self.high_tf_is_stale,
            "med_tf_is_stale": self.med_tf_is_stale,
            "high_tf_ctx_ts_close": self.high_tf_ctx_ts_close.isoformat(),
            "med_tf_ctx_ts_close": self.med_tf_ctx_ts_close.isoformat(),
            # 1m Rollups (Phase 3)
            "rollups": self.rollups,
            "has_rollups": self.has_rollups,
        }
