"""
Phase 4 — Snapshot Plumbing Parity Audit.

Validates RuntimeSnapshotView.get_feature() plumbing correctness without
changing engine execution order, strategy logic, or indicator math.

This audit samples deterministically during backtest execution via an optional
engine callback and compares snapshot feature access against direct FeedStore
array reads.

What this audit validates:
- TF routing: get_feature(..., tf_role="exec"|"high_tf"|"med_tf") returns values from correct feed
- Offset semantics: get_feature(..., offset=0|1|2|...) correctly computes target index
- Forward-fill behavior: high_tf/med_tf indices remain constant between TF closes
- Closed-candle only: snapshot.ts_close equals exec_feed.ts_close[exec_idx]

What this audit does NOT validate:
- Indicator math (Phase 2 already validates this)
- Strategy logic
- Order execution
- Risk management
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from src.backtest.play import load_play, Play, PLAYS_DIR
from src.backtest.execution_validation import compute_warmup_requirements
from src.backtest.runtime.feed_store import FeedStore
from src.backtest.runtime.snapshot_view import RuntimeSnapshotView
from src.utils.logger import get_logger


logger = get_logger()


# OHLCV keys consistent with FeedStore attribute names
OHLCV_KEYS = frozenset({"open", "high", "low", "close", "volume"})


@dataclass
class ComparisonMismatch:
    """Details of a single comparison mismatch."""
    ts_close: datetime
    tf_role: str
    key: str
    offset: int
    observed: float | None
    expected: float | None
    abs_diff: float
    tolerance: float
    exec_idx: int
    high_tf_idx: int | None
    med_tf_idx: int | None
    target_idx: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts_close": self.ts_close.isoformat(),
            "tf_role": self.tf_role,
            "key": self.key,
            "offset": self.offset,
            "observed": self.observed,
            "expected": self.expected,
            "abs_diff": self.abs_diff,
            "tolerance": self.tolerance,
            "exec_idx": self.exec_idx,
            "high_tf_idx": self.high_tf_idx,
            "med_tf_idx": self.med_tf_idx,
            "target_idx": self.target_idx,
        }


@dataclass
class PlumbingParityResult:
    """Result of snapshot plumbing parity audit."""
    success: bool
    total_samples: int
    total_comparisons: int
    failed_comparisons: int
    first_mismatch: ComparisonMismatch | None
    error_message: str | None
    runtime_seconds: float = 0.0
    max_samples_reached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "total_samples": self.total_samples,
            "total_comparisons": self.total_comparisons,
            "failed_comparisons": self.failed_comparisons,
            "first_mismatch": self.first_mismatch.to_dict() if self.first_mismatch else None,
            "error_message": self.error_message,
            "runtime_seconds": self.runtime_seconds,
            "max_samples_reached": self.max_samples_reached,
        }


def direct_feed_read(feed: FeedStore, idx: int, key: str) -> float | None:
    """
    Direct array read from FeedStore for comparison.
    
    Args:
        feed: FeedStore to read from
        idx: Target index
        key: Feature key (OHLCV or indicator)
        
    Returns:
        Value or None if out of bounds or NaN
    """
    if idx < 0 or idx >= feed.length:
        return None  # Out of bounds
    
    # OHLCV keys
    if key == "open":
        return float(feed.open[idx])
    elif key == "high":
        return float(feed.high[idx])
    elif key == "low":
        return float(feed.low[idx])
    elif key == "close":
        return float(feed.close[idx])
    elif key == "volume":
        return float(feed.volume[idx])
    
    # Indicator keys
    if key not in feed.indicators:
        return None  # Undeclared
    val = feed.indicators[key][idx]
    if np.isnan(val):
        return None
    return float(val)


def compare_values(
    observed: float | None,
    expected: float | None,
    tolerance: float,
) -> tuple[bool, float]:
    """
    Compare observed vs expected values.
    
    Args:
        observed: Value from snapshot.get_feature()
        expected: Value from direct_feed_read()
        tolerance: Tolerance for float comparison
        
    Returns:
        Tuple of (matches: bool, abs_diff: float)
    """
    # Both None = match
    if observed is None and expected is None:
        return True, 0.0
    
    # One None, other not = mismatch (NaN mask difference)
    if observed is None or expected is None:
        return False, float('inf')
    
    abs_diff = abs(observed - expected)
    matches = abs_diff <= tolerance
    return matches, abs_diff


class PlumbingAuditCallback:
    """
    Callback for plumbing audit during backtest execution.

    Collects samples at exec bar closes and TF boundaries,
    then compares snapshot.get_feature() against direct FeedStore reads.
    """

    def __init__(
        self,
        exec_feed: FeedStore,
        high_tf_feed: FeedStore | None,
        med_tf_feed: FeedStore | None,
        declared_keys_by_role: dict[str, set[str]],
        max_samples: int = 2000,
        tolerance: float = 1e-12,
        strict: bool = True,
    ):
        self.exec_feed = exec_feed
        self.high_tf_feed = high_tf_feed
        self.med_tf_feed = med_tf_feed
        self.declared_keys_by_role = declared_keys_by_role
        self.max_samples = max_samples
        self.tolerance = tolerance
        self.strict = strict

        # State
        self.samples_count = 0
        self.comparisons_count = 0
        self.failed_comparisons = 0
        self.first_mismatch: ComparisonMismatch | None = None
        self.stop_early = False

        # Track high_tf/med_tf index changes for boundary sampling
        self._prev_high_tf_idx: int | None = None
        self._prev_med_tf_idx: int | None = None

        # Offsets to test
        self._offsets = [0, 1, 2, 5]
    
    def __call__(
        self,
        snapshot: RuntimeSnapshotView,
        exec_idx: int,
        high_tf_idx: int,
        med_tf_idx: int,
    ) -> None:
        """
        Audit callback invoked at each exec bar close.

        Args:
            snapshot: Current RuntimeSnapshotView
            exec_idx: Current exec bar index
            high_tf_idx: Current high_tf forward-fill index
            med_tf_idx: Current med_tf forward-fill index
        """
        if self.stop_early:
            return

        # Determine if we should sample this point
        should_sample = False

        # Sample first N exec bar closes
        if self.samples_count < self.max_samples:
            should_sample = True

        # Always sample at high_tf boundary (when high_tf_idx changes)
        if self._prev_high_tf_idx is not None and high_tf_idx != self._prev_high_tf_idx:
            should_sample = True

        # Always sample at med_tf boundary (when med_tf_idx changes)
        if self._prev_med_tf_idx is not None and med_tf_idx != self._prev_med_tf_idx:
            should_sample = True

        # Update previous indices
        self._prev_high_tf_idx = high_tf_idx
        self._prev_med_tf_idx = med_tf_idx

        if not should_sample:
            return

        self.samples_count += 1

        # Run comparisons for this sample point
        self._run_comparisons(snapshot, exec_idx, high_tf_idx, med_tf_idx)

        # Check for early stop
        if self.strict and self.first_mismatch is not None:
            self.stop_early = True
    
    def _run_comparisons(
        self,
        snapshot: RuntimeSnapshotView,
        exec_idx: int,
        high_tf_idx: int,
        med_tf_idx: int,
    ) -> None:
        """Run all comparisons for a sample point."""
        # Get ts_close for mismatch reporting
        ts_close = snapshot.ts_close

        # Compare exec TF
        self._compare_tf(
            snapshot=snapshot,
            tf_role="exec",
            feed=self.exec_feed,
            ctx_idx=exec_idx,
            ts_close=ts_close,
            exec_idx=exec_idx,
            high_tf_idx=high_tf_idx,
            med_tf_idx=med_tf_idx,
        )

        # Compare high_tf (if different from exec)
        if self.high_tf_feed is not None and self.high_tf_feed is not self.exec_feed:
            self._compare_tf(
                snapshot=snapshot,
                tf_role="high_tf",
                feed=self.high_tf_feed,
                ctx_idx=high_tf_idx,
                ts_close=ts_close,
                exec_idx=exec_idx,
                high_tf_idx=high_tf_idx,
                med_tf_idx=med_tf_idx,
            )

        # Compare med_tf (if different from exec)
        if self.med_tf_feed is not None and self.med_tf_feed is not self.exec_feed:
            self._compare_tf(
                snapshot=snapshot,
                tf_role="med_tf",
                feed=self.med_tf_feed,
                ctx_idx=med_tf_idx,
                ts_close=ts_close,
                exec_idx=exec_idx,
                high_tf_idx=high_tf_idx,
                med_tf_idx=med_tf_idx,
            )

        # Assert: snapshot.ts_close == exec_feed.ts_close[exec_idx]
        expected_ts_close = self.exec_feed.get_ts_close_datetime(exec_idx)
        if ts_close != expected_ts_close:
            self.failed_comparisons += 1
            if self.first_mismatch is None:
                self.first_mismatch = ComparisonMismatch(
                    ts_close=ts_close,
                    tf_role="exec",
                    key="ts_close",
                    offset=0,
                    observed=None,  # Not numeric
                    expected=None,
                    abs_diff=float('inf'),
                    tolerance=0,
                    exec_idx=exec_idx,
                    high_tf_idx=high_tf_idx,
                    med_tf_idx=med_tf_idx,
                    target_idx=exec_idx,
                )
    
    def _compare_tf(
        self,
        snapshot: RuntimeSnapshotView,
        tf_role: str,
        feed: FeedStore,
        ctx_idx: int,
        ts_close: datetime,
        exec_idx: int,
        high_tf_idx: int,
        med_tf_idx: int,
    ) -> None:
        """Compare all keys for a TF role."""
        # Get declared keys for this TF role
        declared_keys = self.declared_keys_by_role.get(tf_role, set())

        # Always include OHLCV keys
        all_keys = OHLCV_KEYS | declared_keys

        for key in all_keys:
            for offset in self._offsets:
                target_idx = ctx_idx - offset

                # Skip if out of bounds for feed
                if target_idx < 0 or target_idx >= feed.length:
                    continue

                self.comparisons_count += 1

                # Get observed value from snapshot
                observed = snapshot.get_feature(key, tf_role=tf_role, offset=offset)

                # Get expected value from direct feed read
                expected = direct_feed_read(feed, target_idx, key)

                # Compare
                matches, abs_diff = compare_values(observed, expected, self.tolerance)

                if not matches:
                    self.failed_comparisons += 1
                    if self.first_mismatch is None:
                        self.first_mismatch = ComparisonMismatch(
                            ts_close=ts_close,
                            tf_role=tf_role,
                            key=key,
                            offset=offset,
                            observed=observed,
                            expected=expected,
                            abs_diff=abs_diff,
                            tolerance=self.tolerance,
                            exec_idx=exec_idx,
                            high_tf_idx=high_tf_idx,
                            med_tf_idx=med_tf_idx,
                            target_idx=target_idx,
                        )
    
    def get_result(self, runtime_seconds: float) -> PlumbingParityResult:
        """Get final audit result."""
        success = self.first_mismatch is None
        return PlumbingParityResult(
            success=success,
            total_samples=self.samples_count,
            total_comparisons=self.comparisons_count,
            failed_comparisons=self.failed_comparisons,
            first_mismatch=self.first_mismatch,
            error_message=None if success else f"Value mismatch at {self.first_mismatch.tf_role}/{self.first_mismatch.key}",
            runtime_seconds=runtime_seconds,
            max_samples_reached=self.samples_count >= self.max_samples,
        )


def audit_snapshot_plumbing_parity(
    play_id: str,
    start_date: datetime,
    end_date: datetime,
    max_samples: int = 2000,
    tolerance: float = 1e-12,
    strict: bool = True,
    plays_dir: Path | None = None,
) -> PlumbingParityResult:
    """
    Run snapshot plumbing parity audit.

    Args:
        play_id: Play identifier or path
        start_date: Start of audit window
        end_date: End of audit window
        max_samples: Max exec bar samples (default: 2000)
        tolerance: Tolerance for float comparison (default: 1e-12)
        strict: Stop at first mismatch (default: True)
        plays_dir: Optional directory for Plays

    Returns:
        PlumbingParityResult with audit results

    Note:
        Symbol is taken from the Play configuration (Play.symbol_universe[0]).
        Plays are self-contained and deterministic.
    """
    import time
    from src.backtest.engine_factory import create_engine_from_play, run_engine_with_play
    from src.indicators import get_required_indicator_columns_from_specs
    
    start_time = time.perf_counter()
    
    try:
        # Load Play - handle subdirectory paths
        # If play_id contains a path separator or file extension, resolve it as a path
        from pathlib import Path as PathLib
        
        if "/" in play_id or "\\" in play_id:
            # Looks like a path - extract directory and ID
            id_path = PathLib(play_id)
            if plays_dir is None:
                plays_dir = PLAYS_DIR
            
            # Get parent dir relative to plays base
            if id_path.parent.name:
                subdir = plays_dir / id_path.parent
            else:
                subdir = plays_dir
            
            # Get the ID without extension
            card_id = id_path.stem if id_path.suffix in (".yml", ".yaml") else id_path.name
            play = load_play(card_id, base_dir=subdir)
        else:
            play = load_play(play_id, base_dir=plays_dir)
        
        # Get symbol from Play (Play is the single source of truth)
        if not play.symbol_universe:
            return PlumbingParityResult(
                success=False,
                total_samples=0,
                total_comparisons=0,
                failed_comparisons=0,
                first_mismatch=None,
                error_message="Play has no symbols in symbol_universe",
            )
        symbol = play.symbol_universe[0]
        
        # Validate account config is present (required - no defaults)
        if play.account is None:
            return PlumbingParityResult(
                success=False,
                total_samples=0,
                total_comparisons=0,
                failed_comparisons=0,
                first_mismatch=None,
                error_message=f"Play '{play_id}' is missing account section.",
            )
        
        # Get declared keys by role from feature registry
        declared_keys_by_role: dict[str, set[str]] = {}
        registry = play.feature_registry
        for tf in registry.get_all_tfs():
            keys = set()
            for feature in registry.get_for_tf(tf):
                keys.add(feature.id)
            declared_keys_by_role[tf] = keys
        # Map exec TF keys to "exec" role for compatibility
        declared_keys_by_role["exec"] = declared_keys_by_role.get(play.execution_tf, set())

        # Create audit callback placeholder (will be set after engine creation)
        callback_holder = {"callback": None}

        def audit_callback(snapshot, exec_idx, htf_idx, mtf_idx):
            """Callback invoked during backtest for plumbing audit."""
            if callback_holder["callback"] is not None:
                callback_holder["callback"](snapshot, exec_idx, htf_idx, mtf_idx)

        # Create engine using factory function
        engine = create_engine_from_play(
            play=play,
            window_start=start_date,
            window_end=end_date,
            on_snapshot=audit_callback,
        )

        # Prepare frames (this builds FeedStores)
        engine.prepare_multi_tf_frames()
        engine._build_feed_stores()

        # Create audit callback now that feeds are available
        callback = PlumbingAuditCallback(
            exec_feed=engine._exec_feed,
            high_tf_feed=engine._high_tf_feed if engine._high_tf_feed is not engine._exec_feed else None,
            med_tf_feed=engine._med_tf_feed if engine._med_tf_feed is not engine._exec_feed else None,
            declared_keys_by_role=declared_keys_by_role,
            max_samples=max_samples,
            tolerance=tolerance,
            strict=strict,
        )
        callback_holder["callback"] = callback

        # Run backtest using factory function with Play-native evaluation
        run_engine_with_play(engine, play)
        
        runtime = time.perf_counter() - start_time
        return callback.get_result(runtime)
        
    except Exception as e:
        runtime = time.perf_counter() - start_time
        logger.error(f"Snapshot plumbing audit failed: {e}")
        import traceback
        traceback.print_exc()
        return PlumbingParityResult(
            success=False,
            total_samples=0,
            total_comparisons=0,
            failed_comparisons=0,
            first_mismatch=None,
            error_message=f"Audit error: {e}",
            runtime_seconds=runtime,
        )

