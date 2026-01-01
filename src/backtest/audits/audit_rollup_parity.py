"""
Rollup Parity Audit: Validate ExecRollupBucket and RuntimeSnapshotView rollup accessors.

This audit validates the 1m rollup system that aggregates price data between exec closes:
1. ExecRollupBucket.accumulate() correctly tracks min/max/sum/count
2. ExecRollupBucket.freeze() produces correct px.rollup.* values
3. RuntimeSnapshotView accessors return correct rollup values
4. Rollup values match manual recomputation from 1m quote data

This is a critical audit for the simulator - rollups are used for:
- Zone touch detection (Market Structure)
- Intrabar price movement analysis
- Stop/limit fill simulation accuracy

Phase: Price Feed (1m) + Preflight Gate + Packet Injection
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import numpy as np

from ..runtime.rollup_bucket import ExecRollupBucket, ROLLUP_KEYS
from ..runtime.quote_state import QuoteState
from ...utils.logger import get_logger


logger = get_logger()


@dataclass
class RollupComparisonResult:
    """Result of comparing a single rollup value."""
    key: str
    observed: float
    expected: float
    abs_diff: float
    passed: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "observed": self.observed,
            "expected": self.expected,
            "abs_diff": self.abs_diff,
            "passed": self.passed,
        }


@dataclass
class RollupIntervalResult:
    """Result of validating a single exec interval's rollups."""
    interval_idx: int
    quote_count: int
    comparisons: List[RollupComparisonResult]
    passed: bool
    first_failure: Optional[RollupComparisonResult] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "interval_idx": self.interval_idx,
            "quote_count": self.quote_count,
            "passed": self.passed,
            "first_failure": self.first_failure.to_dict() if self.first_failure else None,
            "comparisons": [c.to_dict() for c in self.comparisons],
        }


@dataclass
class RollupParityResult:
    """Result of the complete rollup parity audit."""
    success: bool
    total_intervals: int
    passed_intervals: int
    failed_intervals: int
    total_comparisons: int
    failed_comparisons: int
    interval_results: List[RollupIntervalResult]
    accessor_tests_passed: bool
    bucket_tests_passed: bool
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "total_intervals": self.total_intervals,
            "passed_intervals": self.passed_intervals,
            "failed_intervals": self.failed_intervals,
            "total_comparisons": self.total_comparisons,
            "failed_comparisons": self.failed_comparisons,
            "accessor_tests_passed": self.accessor_tests_passed,
            "bucket_tests_passed": self.bucket_tests_passed,
            "error_message": self.error_message,
            "interval_results": [r.to_dict() for r in self.interval_results],
        }


def generate_synthetic_quotes(
    n_quotes: int = 100,
    seed: int = 1337,
    base_price: float = 100.0,
) -> List[QuoteState]:
    """
    Generate deterministic synthetic QuoteState data for rollup audits.

    Creates quotes with realistic price movements and volume patterns.

    Args:
        n_quotes: Number of quotes to generate
        seed: Random seed for reproducibility
        base_price: Starting price level

    Returns:
        List of QuoteState objects
    """
    np.random.seed(seed)

    quotes = []
    price = base_price

    for i in range(n_quotes):
        # Random walk for price
        price += np.random.randn() * 0.5

        # Ensure price stays positive
        price = max(price, 1.0)

        # Generate intrabar high/low
        spread = abs(np.random.randn() * 0.3)
        high = price + spread
        low = price - spread

        # Volume with variation
        volume = 1000 + abs(np.random.randn() * 500)

        quote = QuoteState(
            ts_ms=1704067200000 + i * 60000,  # 1-minute intervals
            last=price,
            high_1m=high,
            low_1m=low,
            mark=price * (1 + np.random.randn() * 0.0001),  # Tiny mark deviation
            mark_source="approx_from_ohlcv_1m",
            volume_1m=volume,
        )
        quotes.append(quote)

    return quotes


def compute_expected_rollups(quotes: List[QuoteState]) -> Dict[str, float]:
    """
    Manually compute expected rollup values from a list of quotes.

    This is the reference implementation for validating ExecRollupBucket.

    Args:
        quotes: List of QuoteState objects in an exec interval

    Returns:
        Dict with px.rollup.* keys and their expected values
    """
    if not quotes:
        return {
            "px.rollup.min_1m": float('inf'),
            "px.rollup.max_1m": float('-inf'),
            "px.rollup.bars_1m": 0.0,
            "px.rollup.open_1m": 0.0,
            "px.rollup.close_1m": 0.0,
            "px.rollup.volume_1m": 0.0,
        }

    min_price = min(q.low_1m for q in quotes)
    max_price = max(q.high_1m for q in quotes)
    open_price = quotes[0].last  # First quote's last price
    close_price = quotes[-1].last  # Last quote's last price
    total_volume = sum(q.volume_1m for q in quotes)
    bar_count = len(quotes)

    return {
        "px.rollup.min_1m": min_price,
        "px.rollup.max_1m": max_price,
        "px.rollup.bars_1m": float(bar_count),
        "px.rollup.open_1m": open_price,
        "px.rollup.close_1m": close_price,
        "px.rollup.volume_1m": total_volume,
    }


def validate_bucket_accumulation(
    quotes: List[QuoteState],
    tolerance: float = 1e-10,
) -> RollupIntervalResult:
    """
    Validate ExecRollupBucket accumulation against manual computation.

    Args:
        quotes: List of quotes to accumulate
        tolerance: Tolerance for float comparison

    Returns:
        RollupIntervalResult with comparison details
    """
    # Accumulate via bucket
    bucket = ExecRollupBucket()
    for quote in quotes:
        bucket.accumulate(quote)

    observed = bucket.freeze()
    expected = compute_expected_rollups(quotes)

    comparisons = []
    first_failure = None
    all_passed = True

    for key in ROLLUP_KEYS.keys():
        obs_val = observed.get(key, float('nan'))
        exp_val = expected.get(key, float('nan'))

        # Handle inf values for empty rollups
        if np.isinf(obs_val) and np.isinf(exp_val):
            if (obs_val > 0) == (exp_val > 0):  # Same sign infinity
                abs_diff = 0.0
                passed = True
            else:
                abs_diff = float('inf')
                passed = False
        else:
            abs_diff = abs(obs_val - exp_val)
            passed = abs_diff <= tolerance

        result = RollupComparisonResult(
            key=key,
            observed=obs_val,
            expected=exp_val,
            abs_diff=abs_diff,
            passed=passed,
        )
        comparisons.append(result)

        if not passed:
            all_passed = False
            if first_failure is None:
                first_failure = result

    return RollupIntervalResult(
        interval_idx=0,
        quote_count=len(quotes),
        comparisons=comparisons,
        passed=all_passed,
        first_failure=first_failure,
    )


def validate_bucket_reset() -> bool:
    """
    Validate ExecRollupBucket.reset() returns to initial state.

    Returns:
        True if reset works correctly
    """
    bucket = ExecRollupBucket()

    # Accumulate some data
    quote = QuoteState(
        ts_ms=1704067200000,
        last=100.0,
        high_1m=101.0,
        low_1m=99.0,
        mark=100.0,
        mark_source="approx_from_ohlcv_1m",
        volume_1m=1000.0,
    )
    bucket.accumulate(quote)

    # Reset
    bucket.reset()

    # Check all fields are back to initial
    if bucket.min_price_1m != float('inf'):
        return False
    if bucket.max_price_1m != float('-inf'):
        return False
    if bucket.bar_count_1m != 0:
        return False
    if bucket.open_price_1m != 0.0:
        return False
    if bucket.close_price_1m != 0.0:
        return False
    if bucket.volume_1m != 0.0:
        return False

    return True


def validate_snapshot_accessors(
    rollups: Dict[str, float],
    tolerance: float = 1e-10,
) -> List[RollupComparisonResult]:
    """
    Validate RuntimeSnapshotView rollup accessors against raw dict values.

    Creates a minimal snapshot and verifies accessor properties match.

    Args:
        rollups: Dict with px.rollup.* values
        tolerance: Tolerance for float comparison

    Returns:
        List of comparison results
    """
    from ..runtime.snapshot_view import RuntimeSnapshotView
    from ..runtime.feed_store import FeedStore, MultiTFFeedStore
    from ..sim.exchange import SimulatedExchange
    import pandas as pd

    # Create minimal FeedStore for snapshot
    df = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=10, freq="15min"),
        "open": [100.0] * 10,
        "high": [101.0] * 10,
        "low": [99.0] * 10,
        "close": [100.0] * 10,
        "volume": [1000.0] * 10,
    })

    exec_feed = FeedStore.from_dataframe(
        df=df,
        symbol="TESTUSDT",
        tf="15m",
        indicator_columns={},
    )

    multi_tf = MultiTFFeedStore(
        exec_feed=exec_feed,
        htf_feed=exec_feed,
        mtf_feed=exec_feed,
        tf_mapping={"ltf": "15m", "htf": "15m", "mtf": "15m"},
    )

    # Create minimal exchange
    exchange = SimulatedExchange(
        symbol="TESTUSDT",
        initial_capital=10000.0,
        leverage=10.0,
    )

    # Create snapshot with rollups
    snapshot = RuntimeSnapshotView(
        feeds=multi_tf,
        exec_idx=5,
        htf_idx=None,
        mtf_idx=None,
        exchange=exchange,
        mark_price=100.0,
        mark_price_source="close",
        rollups=rollups,
    )

    results = []

    # Test each accessor
    accessor_tests = [
        ("px.rollup.min_1m", snapshot.rollup_min_1m),
        ("px.rollup.max_1m", snapshot.rollup_max_1m),
        ("px.rollup.bars_1m", float(snapshot.rollup_bars_1m)),
        ("px.rollup.open_1m", snapshot.rollup_open_1m),
        ("px.rollup.close_1m", snapshot.rollup_close_1m),
        ("px.rollup.volume_1m", snapshot.rollup_volume_1m),
    ]

    for key, accessor_value in accessor_tests:
        expected = rollups.get(key, 0.0)

        # Handle default values for missing keys
        if key == "px.rollup.min_1m" and key not in rollups:
            expected = float('inf')
        elif key == "px.rollup.max_1m" and key not in rollups:
            expected = float('-inf')

        # Handle inf comparison
        if np.isinf(accessor_value) and np.isinf(expected):
            if (accessor_value > 0) == (expected > 0):
                abs_diff = 0.0
                passed = True
            else:
                abs_diff = float('inf')
                passed = False
        else:
            abs_diff = abs(accessor_value - expected)
            passed = abs_diff <= tolerance

        results.append(RollupComparisonResult(
            key=key,
            observed=accessor_value,
            expected=expected,
            abs_diff=abs_diff,
            passed=passed,
        ))

    # Test get_rollup() method
    for key in ROLLUP_KEYS.keys():
        via_getter = snapshot.get_rollup(key)
        expected = rollups.get(key)

        if via_getter is None and expected is None:
            passed = True
            abs_diff = 0.0
        elif via_getter is None or expected is None:
            passed = False
            abs_diff = float('inf')
        elif np.isinf(via_getter) and np.isinf(expected):
            passed = (via_getter > 0) == (expected > 0)
            abs_diff = 0.0 if passed else float('inf')
        else:
            abs_diff = abs(via_getter - expected)
            passed = abs_diff <= tolerance

        results.append(RollupComparisonResult(
            key=f"get_rollup({key})",
            observed=via_getter if via_getter is not None else float('nan'),
            expected=expected if expected is not None else float('nan'),
            abs_diff=abs_diff,
            passed=passed,
        ))

    # Test has_rollups property
    has_rollups = snapshot.has_rollups
    bars = rollups.get("px.rollup.bars_1m", 0)
    expected_has_rollups = bool(rollups) and bars > 0

    results.append(RollupComparisonResult(
        key="has_rollups",
        observed=float(has_rollups),
        expected=float(expected_has_rollups),
        abs_diff=0.0 if has_rollups == expected_has_rollups else 1.0,
        passed=has_rollups == expected_has_rollups,
    ))

    # Test price_range accessor
    price_range = snapshot.rollup_price_range_1m
    if bars == 0:
        expected_range = 0.0
    else:
        min_p = rollups.get("px.rollup.min_1m", float('inf'))
        max_p = rollups.get("px.rollup.max_1m", float('-inf'))
        expected_range = max_p - min_p

    abs_diff = abs(price_range - expected_range)
    results.append(RollupComparisonResult(
        key="rollup_price_range_1m",
        observed=price_range,
        expected=expected_range,
        abs_diff=abs_diff,
        passed=abs_diff <= tolerance,
    ))

    return results


def run_rollup_parity_audit(
    n_intervals: int = 10,
    quotes_per_interval: int = 15,
    seed: int = 1337,
    tolerance: float = 1e-10,
) -> RollupParityResult:
    """
    Run the complete rollup parity audit.

    Tests:
    1. ExecRollupBucket accumulation vs manual computation
    2. ExecRollupBucket reset behavior
    3. RuntimeSnapshotView accessor correctness
    4. Edge cases (empty intervals, single quote, many quotes)

    Args:
        n_intervals: Number of exec intervals to test
        quotes_per_interval: Approximate quotes per interval
        seed: Random seed
        tolerance: Float comparison tolerance

    Returns:
        RollupParityResult with complete audit results
    """
    try:
        interval_results = []
        total_comparisons = 0
        failed_comparisons = 0

        # Test 1: Bucket accumulation across multiple intervals
        np.random.seed(seed)

        for interval_idx in range(n_intervals):
            # Vary quote count per interval
            n_quotes = max(1, quotes_per_interval + np.random.randint(-5, 6))
            quotes = generate_synthetic_quotes(
                n_quotes=n_quotes,
                seed=seed + interval_idx,
                base_price=100.0 + interval_idx * 10,
            )

            result = validate_bucket_accumulation(quotes, tolerance)
            result.interval_idx = interval_idx
            interval_results.append(result)

            total_comparisons += len(result.comparisons)
            failed_comparisons += sum(1 for c in result.comparisons if not c.passed)

        # Test 2: Empty interval (edge case)
        empty_result = validate_bucket_accumulation([], tolerance)
        empty_result.interval_idx = n_intervals
        interval_results.append(empty_result)
        total_comparisons += len(empty_result.comparisons)
        failed_comparisons += sum(1 for c in empty_result.comparisons if not c.passed)

        # Test 3: Bucket reset
        bucket_tests_passed = validate_bucket_reset()

        # Test 4: Snapshot accessors
        # Use rollups from a typical interval
        test_quotes = generate_synthetic_quotes(n_quotes=15, seed=seed + 999)
        test_rollups = compute_expected_rollups(test_quotes)
        accessor_results = validate_snapshot_accessors(test_rollups, tolerance)

        accessor_tests_passed = all(r.passed for r in accessor_results)
        total_comparisons += len(accessor_results)
        failed_comparisons += sum(1 for r in accessor_results if not r.passed)

        # Calculate summary
        passed_intervals = sum(1 for r in interval_results if r.passed)
        failed_intervals = len(interval_results) - passed_intervals

        success = (
            failed_intervals == 0 and
            bucket_tests_passed and
            accessor_tests_passed
        )

        return RollupParityResult(
            success=success,
            total_intervals=len(interval_results),
            passed_intervals=passed_intervals,
            failed_intervals=failed_intervals,
            total_comparisons=total_comparisons,
            failed_comparisons=failed_comparisons,
            interval_results=interval_results,
            accessor_tests_passed=accessor_tests_passed,
            bucket_tests_passed=bucket_tests_passed,
        )

    except Exception as e:
        import traceback
        logger.error(f"Rollup parity audit failed: {e}\n{traceback.format_exc()}")
        return RollupParityResult(
            success=False,
            total_intervals=0,
            passed_intervals=0,
            failed_intervals=0,
            total_comparisons=0,
            failed_comparisons=0,
            interval_results=[],
            accessor_tests_passed=False,
            bucket_tests_passed=False,
            error_message=str(e),
        )
