"""
Bar processor for backtest engine.

Extracts per-bar processing logic from engine.run() into a focused class
with clear separation of concerns:
- Warmup bar processing (no trading)
- Trading bar processing (full evaluation)
- Stop condition checking
- Signal processing

ARCHITECTURE:
- BarProcessor holds a reference to the engine for state access
- Each method handles a specific phase of bar processing
- Engine's run() method becomes a thin orchestrator
"""

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np

from .types import (
    Trade,
    EquityPoint,
    AccountCurvePoint,
    StopReason,
)
from .runtime.types import (
    Bar as CanonicalBar,
    FeatureSnapshot,
)
from .runtime.feed_store import FeedStore
from .runtime.quote_state import QuoteState
from .sim import StepResult

# Import from engine_stops module
from .engine_stops import (
    StopCheckResult,
    check_all_stop_conditions,
    handle_terminal_stop,
)

# Import funding scheduler for hot loop
from .runtime.funding_scheduler import get_funding_events_in_window

# Incremental state imports
from .incremental.base import BarData

from ..core.risk_manager import Signal
from ..data.historical_data_store import TF_MINUTES
from ..utils.debug import debug_milestone

if TYPE_CHECKING:
    from .engine import BacktestEngine
    from .runtime.snapshot_view import RuntimeSnapshotView


class BarProcessingResult:
    """Result from processing a trading bar."""

    __slots__ = (
        "signal",
        "snapshot",
        "signal_ts",
        "terminal_stop",
        "stop_classification",
        "stop_reason_detail",
        "stop_reason",
        "stop_ts",
        "stop_bar_index",
        "stop_details",
    )

    def __init__(
        self,
        signal: Signal | None = None,
        snapshot: "RuntimeSnapshotView | None" = None,
        signal_ts: datetime | None = None,
        terminal_stop: bool = False,
        stop_classification: StopReason | None = None,
        stop_reason_detail: str | None = None,
        stop_reason: str | None = None,
        stop_ts: datetime | None = None,
        stop_bar_index: int | None = None,
        stop_details: dict[str, Any] | None = None,
    ):
        self.signal = signal
        self.snapshot = snapshot
        self.signal_ts = signal_ts
        self.terminal_stop = terminal_stop
        self.stop_classification = stop_classification
        self.stop_reason_detail = stop_reason_detail
        self.stop_reason = stop_reason
        self.stop_ts = stop_ts
        self.stop_bar_index = stop_bar_index
        self.stop_details = stop_details


class BarProcessor:
    """
    Processes individual bars with clear separation of phases.

    Extracts the complex loop body from BacktestEngine.run() into focused
    methods. Each method handles a specific concern:
    - process_warmup_bar: Warmup period (update state, no trading)
    - process_trading_bar: Full trading logic (signals, stops, equity)
    - check_stop_conditions: Terminal stop detection
    - build_bar: O(1) bar construction from FeedStore

    Usage:
        processor = BarProcessor(engine, strategy)
        for i in range(num_bars):
            bar = processor.build_bar(i)
            if i < sim_start_idx:
                processor.process_warmup_bar(i, bar, prev_bar)
            else:
                result = processor.process_trading_bar(i, bar, prev_bar)
                if result.terminal_stop:
                    break
            prev_bar = bar
    """

    def __init__(
        self,
        engine: "BacktestEngine",
        strategy: Callable[["RuntimeSnapshotView", dict[str, Any]], Signal | None],
        run_start_time: datetime,
    ):
        """
        Initialize bar processor.

        Args:
            engine: BacktestEngine instance (for state access)
            strategy: Strategy function to evaluate
            run_start_time: Start time of the run (for debug timing)
        """
        self._engine = engine
        self._strategy = strategy
        self._run_start_time = run_start_time

        # Cache commonly accessed engine attributes for performance
        self._exec_feed = engine._exec_feed
        self._htf_feed = engine._htf_feed
        self._mtf_feed = engine._mtf_feed
        self._quote_feed = engine._quote_feed
        self._exchange = engine._exchange
        self._config = engine.config
        self._risk_profile = engine.config.risk_profile
        self._multi_tf_mode = engine._multi_tf_mode
        self._tf_mapping = engine._tf_mapping
        self._play_hash = engine._play_hash
        self._state_tracker = engine._state_tracker
        self._incremental_state = engine._incremental_state
        self._rationalizer = engine._rationalizer
        self._history_manager = engine._history_manager
        self._logger = engine.logger

    def build_bar(self, i: int) -> CanonicalBar:
        """
        Build canonical Bar with O(1) array access.

        Args:
            i: Bar index in exec feed

        Returns:
            CanonicalBar instance
        """
        exec_feed = self._exec_feed
        ts_open = exec_feed.get_ts_open_datetime(i)
        ts_close = exec_feed.get_ts_close_datetime(i)

        return CanonicalBar(
            symbol=self._config.symbol,
            tf=self._config.tf,
            ts_open=ts_open,
            ts_close=ts_close,
            open=float(exec_feed.open[i]),
            high=float(exec_feed.high[i]),
            low=float(exec_feed.low[i]),
            close=float(exec_feed.close[i]),
            volume=float(exec_feed.volume[i]),
        )

    def process_warmup_bar(
        self,
        i: int,
        bar: CanonicalBar,
        prev_bar: CanonicalBar | None,
        sim_start_idx: int,
    ) -> None:
        """
        Handle warmup period - update state, no trading.

        Updates incremental state, HTF/MTF indices, and history during
        the warmup period when trading is not yet allowed.

        Args:
            i: Bar index
            bar: Current bar
            prev_bar: Previous bar (or None for first bar)
            sim_start_idx: Index where simulation (trading) starts
        """
        engine = self._engine
        exec_feed = self._exec_feed

        # Debug milestone logging
        debug_milestone(
            self._play_hash,
            bar_idx=i,
            total_bars=exec_feed.length,
            elapsed_seconds=(datetime.now() - self._run_start_time).total_seconds(),
        )

        # Update incremental state with current bar (before any snapshots)
        self._update_incremental_state(i, bar)

        # State tracking - bar start (record-only)
        if self._state_tracker:
            self._state_tracker.on_bar_start(i)
            warmup_ok = i >= sim_start_idx
            self._state_tracker.on_warmup_check(warmup_ok, sim_start_idx)
            self._state_tracker.on_history_check(
                engine._is_history_ready(),
                len(self._history_manager.bars_exec),
            )

        # Set bar context for artifact tracking
        self._exchange.set_bar_context(i, snapshot_ready=True)

        # Process bar (fills pending orders, checks TP/SL)
        step_result = self._process_exchange_bar(i, bar, prev_bar)

        # Sync risk manager equity with exchange
        engine.risk_manager.sync_equity(self._exchange.equity_usdt)

        # Update HTF/MTF indices during warmup (for forward-fill)
        htf_updated_warmup = False
        mtf_updated_warmup = False
        if self._multi_tf_mode:
            htf_updated_warmup, mtf_updated_warmup = engine._update_htf_mtf_indices(bar.ts_close)

        # Extract features from FeedStore (O(1) access)
        warmup_features = self._extract_features(i)
        warmup_features_exec = FeatureSnapshot(
            tf=self._config.tf,
            ts_close=bar.ts_close,
            bar=bar,
            features=warmup_features,
            ready=True,
        )

        # Update history
        engine._update_history(
            bar=bar,
            features_exec=warmup_features_exec,
            htf_updated=htf_updated_warmup,
            mtf_updated=mtf_updated_warmup,
            features_htf=engine._tf_cache.get_htf() if self._multi_tf_mode else None,
            features_mtf=engine._tf_cache.get_mtf() if self._multi_tf_mode else None,
        )

    def process_trading_bar(
        self,
        i: int,
        bar: CanonicalBar,
        prev_bar: CanonicalBar | None,
        sim_start_idx: int,
        equity_curve: list[EquityPoint],
        account_curve: list[AccountCurvePoint],
    ) -> BarProcessingResult:
        """
        Handle trading period - full evaluation.

        Processes a bar in trading mode, including:
        - Incremental state updates
        - Stop condition checks (returns early if terminal)
        - 1m quote accumulation
        - Strategy evaluation
        - Signal processing
        - Equity recording

        Args:
            i: Bar index
            bar: Current bar
            prev_bar: Previous bar (or None for first bar)
            sim_start_idx: Index where simulation (trading) starts
            equity_curve: List to append equity points to
            account_curve: List to append account points to

        Returns:
            BarProcessingResult with signal and stop info
        """
        engine = self._engine
        exec_feed = self._exec_feed

        # Debug milestone logging
        debug_milestone(
            self._play_hash,
            bar_idx=i,
            total_bars=exec_feed.length,
            elapsed_seconds=(datetime.now() - self._run_start_time).total_seconds(),
        )

        # Update incremental state with current bar
        self._update_incremental_state(i, bar)

        # State tracking - bar start
        if self._state_tracker:
            self._state_tracker.on_bar_start(i)
            self._state_tracker.on_warmup_check(True, sim_start_idx)
            self._state_tracker.on_history_check(
                engine._is_history_ready(),
                len(self._history_manager.bars_exec),
            )

        # Set bar context for artifact tracking
        self._exchange.set_bar_context(i, snapshot_ready=True)

        # Process bar (fills pending orders, checks TP/SL)
        step_result = self._process_exchange_bar(i, bar, prev_bar)

        # Record fills/rejections from step_result
        if self._state_tracker and step_result:
            for _fill in step_result.fills:
                self._state_tracker.on_order_filled()
            for _rejection in step_result.rejections:
                self._state_tracker.on_order_rejected(_rejection.reason)

        # Sync risk manager equity
        engine.risk_manager.sync_equity(self._exchange.equity_usdt)

        # Update HTF/MTF indices
        htf_updated, mtf_updated = False, False
        if self._multi_tf_mode:
            htf_updated, mtf_updated = engine._update_htf_mtf_indices(bar.ts_close)

        # Update HTF incremental state on HTF close
        self._update_htf_incremental_state(htf_updated)

        # Extract features for history
        features_for_history = self._extract_features(i)
        current_features_exec = FeatureSnapshot(
            tf=self._config.tf,
            ts_close=bar.ts_close,
            bar=bar,
            features=features_for_history,
            ready=True,
        )

        # ========== STOP CHECKS ==========
        stop_result = self._check_stop_conditions(bar, i)
        if stop_result.terminal_stop:
            return self._handle_terminal_stop(
                bar, i, stop_result, equity_curve, account_curve
            )

        # ========== BUILD SNAPSHOT & EVALUATE ==========
        # Accumulate 1m quotes and freeze rollups
        engine._accumulate_1m_quotes(bar.ts_close)
        rollups = engine._freeze_rollups()

        # Build snapshot
        snapshot = engine._build_snapshot_view(i, step_result, rollups=rollups)

        # Invoke snapshot callback if present (audit-only)
        if engine._on_snapshot is not None:
            engine._on_snapshot(snapshot, i, engine._current_htf_idx, engine._current_mtf_idx)

        # Update exchange with snapshot readiness
        self._exchange.set_bar_context(i, snapshot_ready=snapshot.ready)

        # Readiness gate - skip trading if caches not ready
        if self._multi_tf_mode and not snapshot.ready:
            self._record_equity_point(bar, equity_curve, account_curve)
            return BarProcessingResult(snapshot=snapshot)

        # Mark warmup complete on first ready snapshot
        if self._multi_tf_mode and not engine._warmup_complete:
            engine._warmup_complete = True
            engine._first_ready_bar_index = i
            self._logger.info(f"Multi-TF caches ready at bar {i} ({bar.ts_close})")

        # ========== LOOKAHEAD GUARD ==========
        self._assert_no_lookahead(snapshot, bar)

        # ========== 1m EVALUATION SUB-LOOP ==========
        signal, snapshot, signal_ts = engine._evaluate_with_1m_subloop(
            exec_idx=i,
            strategy=self._strategy,
            step_result=step_result,
            rollups=rollups,
        )

        # State tracking - record signal
        if self._state_tracker:
            signal_direction = 0
            if signal is not None:
                signal_direction = 1 if signal.direction == "LONG" else -1
            self._state_tracker.on_signal_evaluated(signal_direction)
            position_count = 1 if self._exchange.position is not None else 0
            self._state_tracker.on_position_check(position_count)

        # Process signal
        if signal is not None:
            engine._process_signal(signal, bar, snapshot, signal_ts=signal_ts)

        # Record equity point
        self._record_equity_point(bar, equity_curve, account_curve)

        # Update history AFTER strategy evaluation
        engine._update_history(
            bar=bar,
            features_exec=current_features_exec,
            htf_updated=htf_updated,
            mtf_updated=mtf_updated,
            features_htf=engine._tf_cache.get_htf() if self._multi_tf_mode else None,
            features_mtf=engine._tf_cache.get_mtf() if self._multi_tf_mode else None,
        )

        # State tracking - bar end
        if self._state_tracker:
            self._state_tracker.on_bar_end()

        return BarProcessingResult(
            signal=signal,
            snapshot=snapshot,
            signal_ts=signal_ts,
        )

    def _update_incremental_state(self, i: int, bar: CanonicalBar) -> None:
        """
        Update incremental state with current bar.

        Must happen BEFORE snapshot creation so structures are current.
        """
        incremental_state = self._incremental_state
        if incremental_state is None:
            return

        exec_feed = self._exec_feed

        # Build indicator dict for BarData (O(1) dict build from arrays)
        indicator_values: dict[str, float] = {}
        for key in exec_feed.indicators.keys():
            val = exec_feed.indicators[key][i]
            if not np.isnan(val):
                indicator_values[key] = float(val)

        # Create BarData for incremental update
        bar_data = BarData(
            idx=i,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            indicators=indicator_values,
        )

        # Update exec state
        incremental_state.update_exec(bar_data)

        # Rationalize state (Layer 2)
        if self._rationalizer is not None:
            self._engine._rationalized_state = self._rationalizer.rationalize(
                bar_idx=i,
                incremental_state=incremental_state,
                bar=bar_data,
            )

    def _update_htf_incremental_state(self, htf_updated: bool) -> None:
        """Update HTF incremental state when HTF bar closes."""
        if not htf_updated or self._incremental_state is None:
            return

        engine = self._engine
        htf_tf = self._tf_mapping.get("htf")
        if not htf_tf or htf_tf not in self._incremental_state.htf:
            return

        htf_feed = self._htf_feed
        if htf_feed is None:
            return

        htf_idx = engine._current_htf_idx

        # Build HTF BarData
        htf_indicator_values: dict[str, float] = {}
        for key in htf_feed.indicators.keys():
            val = htf_feed.indicators[key][htf_idx]
            if not np.isnan(val):
                htf_indicator_values[key] = float(val)

        htf_bar_data = BarData(
            idx=htf_idx,
            open=float(htf_feed.open[htf_idx]),
            high=float(htf_feed.high[htf_idx]),
            low=float(htf_feed.low[htf_idx]),
            close=float(htf_feed.close[htf_idx]),
            volume=float(htf_feed.volume[htf_idx]),
            indicators=htf_indicator_values,
        )

        self._incremental_state.update_htf(htf_tf, htf_bar_data)

    def _process_exchange_bar(
        self,
        i: int,
        bar: CanonicalBar,
        prev_bar: CanonicalBar | None,
    ) -> StepResult | None:
        """
        Process bar through simulated exchange.

        Fills pending orders, checks TP/SL, handles funding events.
        """
        engine = self._engine
        exec_feed = self._exec_feed

        # Get 1m range for granular TP/SL checking
        exec_1m_range = None
        if self._quote_feed is not None and self._quote_feed.length > 0:
            exec_tf_minutes = TF_MINUTES.get(self._config.tf.lower(), 15)
            start_1m, end_1m = self._quote_feed.get_1m_indices_for_exec(i, exec_tf_minutes)
            end_1m = min(end_1m, self._quote_feed.length - 1)
            exec_1m_range = (start_1m, end_1m)

        # Get funding events in (prev_bar.ts_close, bar.ts_close] window
        funding_events = get_funding_events_in_window(
            prev_ts=prev_bar.ts_close if prev_bar else None,
            current_ts=bar.ts_close,
            funding_settlement_times=exec_feed.funding_settlement_times,
            funding_df=engine._funding_df,
            symbol=self._config.symbol,
        )

        return self._exchange.process_bar(
            bar, prev_bar,
            quote_feed=self._quote_feed,
            exec_1m_range=exec_1m_range,
            funding_events=funding_events,
        )

    def _extract_features(self, i: int) -> dict[str, float]:
        """Extract features from FeedStore at bar index (O(1) access)."""
        exec_feed = self._exec_feed
        features: dict[str, float] = {}
        for key in exec_feed.indicators.keys():
            val = exec_feed.indicators[key][i]
            if not np.isnan(val):
                features[key] = float(val)
        return features

    def _check_stop_conditions(self, bar: CanonicalBar, i: int) -> StopCheckResult:
        """Check all stop conditions and return result."""
        risk_profile = self._risk_profile

        # Phase 1: only close-as-mark supported
        if risk_profile.mark_price_source != "close":
            raise ValueError(
                f"Unsupported mark_price_source='{risk_profile.mark_price_source}'. "
                "Phase 1 supports 'close' only."
            )

        return check_all_stop_conditions(
            exchange=self._exchange,
            risk_profile=risk_profile,
            bar_ts_close=bar.ts_close,
            bar_index=i,
            logger=self._logger,
        )

    def _handle_terminal_stop(
        self,
        bar: CanonicalBar,
        i: int,
        stop_result: StopCheckResult,
        equity_curve: list[EquityPoint],
        account_curve: list[AccountCurvePoint],
    ) -> BarProcessingResult:
        """Handle terminal stop (cancel orders, close position, record equity)."""
        handle_terminal_stop(
            exchange=self._exchange,
            bar_close_price=bar.close,
            bar_ts_close=bar.ts_close,
            stop_reason=stop_result.reason,
        )

        # Record final equity at stop
        self._record_equity_point(bar, equity_curve, account_curve)

        self._logger.warning(
            f"Terminal stop: {stop_result.classification.value} at bar {i}, "
            f"equity=${self._exchange.equity_usdt:.2f}, "
            f"detail: {stop_result.reason_detail}"
        )

        return BarProcessingResult(
            terminal_stop=True,
            stop_classification=stop_result.classification,
            stop_reason_detail=stop_result.reason_detail,
            stop_reason=stop_result.reason,
            stop_ts=bar.ts_close,
            stop_bar_index=i,
            stop_details=self._exchange.get_state(),
        )

    def _record_equity_point(
        self,
        bar: CanonicalBar,
        equity_curve: list[EquityPoint],
        account_curve: list[AccountCurvePoint],
    ) -> None:
        """Record equity and account curve points at bar close."""
        exchange = self._exchange

        equity_curve.append(EquityPoint(
            timestamp=bar.ts_close,
            equity=exchange.equity_usdt,
        ))

        account_curve.append(AccountCurvePoint(
            timestamp=bar.ts_close,
            equity_usdt=exchange.equity_usdt,
            used_margin_usdt=exchange.used_margin_usdt,
            free_margin_usdt=exchange.free_margin_usdt,
            available_balance_usdt=exchange.available_balance_usdt,
            maintenance_margin_usdt=exchange.maintenance_margin,
            has_position=exchange.position is not None,
            entries_disabled=exchange.entries_disabled,
        ))

    def _assert_no_lookahead(
        self,
        snapshot: "RuntimeSnapshotView",
        bar: CanonicalBar,
    ) -> None:
        """Assert strategy is invoked only at bar close with closed-candle data."""
        assert snapshot.ts_close == bar.ts_close, (
            f"Lookahead violation: snapshot.ts_close ({snapshot.ts_close}) != "
            f"bar.ts_close ({bar.ts_close})"
        )

        exec_ts_close = (
            snapshot.exec_ctx.ts_close
            if hasattr(snapshot, 'exec_ctx')
            else snapshot.features_exec.ts_close
        )
        assert exec_ts_close == bar.ts_close, (
            f"Lookahead violation: exec ts_close ({exec_ts_close}) != "
            f"bar.ts_close ({bar.ts_close})"
        )
