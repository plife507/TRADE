"""
Phase 4 — Snapshot Plumbing Parity Audit.

Validates RuntimeSnapshotView.get_feature() plumbing correctness without
changing engine execution order, strategy logic, or indicator math.

This audit samples deterministically during backtest execution via an optional
engine callback and compares snapshot feature access against direct FeedStore
array reads.

What this audit validates:
- TF routing: get_feature(..., tf_role="exec"|"htf"|"mtf") returns values from correct feed
- Offset semantics: get_feature(..., offset=0|1|2|...) correctly computes target index
- Forward-fill behavior: HTF/MTF indices remain constant between TF closes
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

from ..play import load_idea_card, IdeaCard, IDEA_CARDS_DIR
from ..execution_validation import compute_warmup_requirements
from ..runtime.feed_store import FeedStore
from ..runtime.snapshot_view import RuntimeSnapshotView
from ...utils.logger import get_logger


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
    htf_idx: int | None
    mtf_idx: int | None
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
            "htf_idx": self.htf_idx,
            "mtf_idx": self.mtf_idx,
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
        htf_feed: FeedStore | None,
        mtf_feed: FeedStore | None,
        declared_keys_by_role: dict[str, set[str]],
        max_samples: int = 2000,
        tolerance: float = 1e-12,
        strict: bool = True,
    ):
        self.exec_feed = exec_feed
        self.htf_feed = htf_feed
        self.mtf_feed = mtf_feed
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

        # Track HTF/MTF index changes for boundary sampling
        self._prev_htf_idx: int | None = None
        self._prev_mtf_idx: int | None = None
        
        # Offsets to test
        self._offsets = [0, 1, 2, 5]
    
    def __call__(
        self,
        snapshot: RuntimeSnapshotView,
        exec_idx: int,
        htf_idx: int,
        mtf_idx: int,
    ) -> None:
        """
        Audit callback invoked at each exec bar close.
        
        Args:
            snapshot: Current RuntimeSnapshotView
            exec_idx: Current exec bar index
            htf_idx: Current HTF forward-fill index
            mtf_idx: Current MTF forward-fill index
        """
        if self.stop_early:
            return
        
        # Determine if we should sample this point
        should_sample = False
        
        # Sample first N exec bar closes
        if self.samples_count < self.max_samples:
            should_sample = True
        
        # Always sample at HTF boundary (when htf_idx changes)
        if self._prev_htf_idx is not None and htf_idx != self._prev_htf_idx:
            should_sample = True
        
        # Always sample at MTF boundary (when mtf_idx changes)
        if self._prev_mtf_idx is not None and mtf_idx != self._prev_mtf_idx:
            should_sample = True
        
        # Update previous indices
        self._prev_htf_idx = htf_idx
        self._prev_mtf_idx = mtf_idx
        
        if not should_sample:
            return
        
        self.samples_count += 1
        
        # Run comparisons for this sample point
        self._run_comparisons(snapshot, exec_idx, htf_idx, mtf_idx)
        
        # Check for early stop
        if self.strict and self.first_mismatch is not None:
            self.stop_early = True
    
    def _run_comparisons(
        self,
        snapshot: RuntimeSnapshotView,
        exec_idx: int,
        htf_idx: int,
        mtf_idx: int,
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
            htf_idx=htf_idx,
            mtf_idx=mtf_idx,
        )
        
        # Compare HTF (if different from exec)
        if self.htf_feed is not None and self.htf_feed is not self.exec_feed:
            self._compare_tf(
                snapshot=snapshot,
                tf_role="htf",
                feed=self.htf_feed,
                ctx_idx=htf_idx,
                ts_close=ts_close,
                exec_idx=exec_idx,
                htf_idx=htf_idx,
                mtf_idx=mtf_idx,
            )
        
        # Compare MTF (if different from exec)
        if self.mtf_feed is not None and self.mtf_feed is not self.exec_feed:
            self._compare_tf(
                snapshot=snapshot,
                tf_role="mtf",
                feed=self.mtf_feed,
                ctx_idx=mtf_idx,
                ts_close=ts_close,
                exec_idx=exec_idx,
                htf_idx=htf_idx,
                mtf_idx=mtf_idx,
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
                    htf_idx=htf_idx,
                    mtf_idx=mtf_idx,
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
        htf_idx: int,
        mtf_idx: int,
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
                            htf_idx=htf_idx,
                            mtf_idx=mtf_idx,
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
    idea_card_id: str,
    start_date: datetime,
    end_date: datetime,
    symbol: str | None = None,
    max_samples: int = 2000,
    tolerance: float = 1e-12,
    strict: bool = True,
    idea_cards_dir: Path | None = None,
) -> PlumbingParityResult:
    """
    Run snapshot plumbing parity audit.
    
    Args:
        idea_card_id: IdeaCard identifier or path
        start_date: Start of audit window
        end_date: End of audit window
        symbol: Override symbol (optional, inferred from IdeaCard)
        max_samples: Max exec bar samples (default: 2000)
        tolerance: Tolerance for float comparison (default: 1e-12)
        strict: Stop at first mismatch (default: True)
        idea_cards_dir: Optional directory for IdeaCards
        
    Returns:
        PlumbingParityResult with audit results
    """
    import time
    from ..engine import BacktestEngine
    from ..system_config import (
        SystemConfig,
        RiskProfileConfig,
        StrategyInstanceConfig,
        StrategyInstanceInputs,
    )
    from ..indicators import get_required_indicator_columns_from_specs
    
    start_time = time.perf_counter()
    
    try:
        # Load IdeaCard - handle subdirectory paths
        # If idea_card_id contains a path separator or file extension, resolve it as a path
        from pathlib import Path as PathLib
        
        if "/" in idea_card_id or "\\" in idea_card_id:
            # Looks like a path - extract directory and ID
            id_path = PathLib(idea_card_id)
            if idea_cards_dir is None:
                idea_cards_dir = IDEA_CARDS_DIR
            
            # Get parent dir relative to idea_cards base
            if id_path.parent.name:
                subdir = idea_cards_dir / id_path.parent
            else:
                subdir = idea_cards_dir
            
            # Get the ID without extension
            card_id = id_path.stem if id_path.suffix in (".yml", ".yaml") else id_path.name
            idea_card = load_idea_card(card_id, base_dir=subdir)
        else:
            idea_card = load_idea_card(idea_card_id, base_dir=idea_cards_dir)
        
        # Resolve symbol
        if symbol is None:
            if not idea_card.symbol_universe:
                return PlumbingParityResult(
                    success=False,
                    total_samples=0,
                    total_comparisons=0,
                    failed_comparisons=0,
                    first_mismatch=None,
                    error_message="IdeaCard has no symbols in symbol_universe and none provided",
                )
            symbol = idea_card.symbol_universe[0]
        
        # Validate account config is present (required - no defaults)
        if idea_card.account is None:
            return PlumbingParityResult(
                success=False,
                total_samples=0,
                total_comparisons=0,
                failed_comparisons=0,
                first_mismatch=None,
                error_message=f"IdeaCard '{idea_card_id}' is missing account section.",
            )
        
        # Get declared keys by role
        declared_keys_by_role: dict[str, set[str]] = {}
        for role, tf_config in idea_card.tf_configs.items():
            specs = list(tf_config.feature_specs)
            expanded_keys = get_required_indicator_columns_from_specs(specs)
            declared_keys_by_role[role] = set(expanded_keys)
        
        # Extract params from IdeaCard
        initial_equity = idea_card.account.starting_equity_usdt
        max_leverage = idea_card.account.max_leverage
        
        taker_fee_rate = 0.0006
        if idea_card.account.fee_model:
            taker_fee_rate = idea_card.account.fee_model.taker_rate
        
        min_trade_usdt = 1.0
        if idea_card.account.min_trade_notional_usdt is not None:
            min_trade_usdt = idea_card.account.min_trade_notional_usdt
        
        risk_per_trade_pct = 1.0
        if idea_card.risk_model:
            if idea_card.risk_model.sizing.model.value == "percent_equity":
                risk_per_trade_pct = idea_card.risk_model.sizing.value
            if idea_card.risk_model.sizing.max_leverage:
                max_leverage = idea_card.risk_model.sizing.max_leverage
        
        # Build minimal SystemConfig for engine (same pattern as runner.py)
        risk_profile = RiskProfileConfig(
            initial_equity=initial_equity,
            max_leverage=max_leverage,
            risk_per_trade_pct=risk_per_trade_pct,
            taker_fee_rate=taker_fee_rate,
            min_trade_usdt=min_trade_usdt,
        )
        
        # Extract feature specs from IdeaCard for engine
        feature_specs_by_role = {}
        for role, tf_config in idea_card.tf_configs.items():
            feature_specs_by_role[role] = list(tf_config.feature_specs)
        
        # Compute warmup requirements from IdeaCard (P0.2 fix)
        warmup_reqs = compute_warmup_requirements(idea_card)
        warmup_bars_by_role = warmup_reqs.warmup_by_role
        delay_bars_by_role = warmup_reqs.delay_by_role
        
        # Build params with history config
        strategy_params = {
            "history": {
                "bars_exec_count": 2,
                "features_exec_count": 2,
                "features_htf_count": 2,
                "features_mtf_count": 2,
            }
        }
        
        # Create strategy instance
        strategy_instance = StrategyInstanceConfig(
            strategy_instance_id="audit_strategy",
            strategy_id=idea_card.id,
            strategy_version=idea_card.version,
            inputs=StrategyInstanceInputs(symbol=symbol, tf=idea_card.exec_tf),
            params=strategy_params,
        )
        
        # Create SystemConfig
        system_config = SystemConfig(
            system_id=idea_card.id,
            symbol=symbol,
            tf=idea_card.exec_tf,
            strategies=[strategy_instance],
            primary_strategy_instance_id="audit_strategy",
            windows={
                "audit": {
                    "start": start_date.replace(tzinfo=None).isoformat() if start_date.tzinfo else start_date.isoformat(),
                    "end": end_date.replace(tzinfo=None).isoformat() if end_date.tzinfo else end_date.isoformat(),
                }
            },
            risk_profile=risk_profile,
            risk_mode="none",
            feature_specs_by_role=feature_specs_by_role,
            warmup_bars_by_role=warmup_bars_by_role,
            delay_bars_by_role=delay_bars_by_role,
        )
        
        # Build tf_mapping
        tf_mapping = {
            "htf": idea_card.htf or idea_card.exec_tf,
            "mtf": idea_card.mtf or idea_card.exec_tf,
            "ltf": idea_card.exec_tf,
        }
        
        # Create engine with callback placeholder
        engine = BacktestEngine(
            config=system_config,
            window_name="audit",
            tf_mapping=tf_mapping,
        )
        
        # Prepare frames (this builds FeedStores)
        if tf_mapping["htf"] != tf_mapping["ltf"] or tf_mapping["mtf"] != tf_mapping["ltf"]:
            engine.prepare_multi_tf_frames()
        else:
            engine.prepare_backtest_frame()
        
        engine._build_feed_stores()
        
        # Create audit callback
        callback = PlumbingAuditCallback(
            exec_feed=engine._exec_feed,
            htf_feed=engine._htf_feed if engine._htf_feed is not engine._exec_feed else None,
            mtf_feed=engine._mtf_feed if engine._mtf_feed is not engine._exec_feed else None,
            declared_keys_by_role=declared_keys_by_role,
            max_samples=max_samples,
            tolerance=tolerance,
            strict=strict,
        )
        
        # Set callback on engine
        engine._on_snapshot = callback
        
        # Define dummy strategy that does nothing (we only care about the callback)
        def dummy_strategy(snapshot, params):
            return None
        
        # Run backtest (callback will be invoked at each bar close)
        engine.run(dummy_strategy)
        
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

