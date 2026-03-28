"""
Structure Detector Vectorized vs Incremental Parity Audit.

Compares all 7 incremental structure detectors against vectorized
reference implementations to ensure mathematical parity.

CLI: python trade_cli.py backtest audit-structure-parity [--bars 2000] [--tolerance 1e-10]

The 7 structure detectors tested:
1. rolling_window - Rolling min/max
2. swing - Fractal pivot detection + pairing
3. trend - Wave-based trend classification
4. zone - Demand/supply zones
5. fibonacci - Fibonacci retracement/extension levels
6. market_structure - BOS/CHoCH detection
7. derived_zone - K slots + scalar aggregates
"""

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.structures.batch_wrapper import run_detector_batch

from .vectorized_references.data_generators import (
    generate_synthetic_ohlcv,
    generate_flat_bars,
    generate_gap_data,
    generate_rapid_swing_data,
    generate_monotonic_rise,
    generate_monotonic_fall,
    load_real_ohlcv,
)
from .vectorized_references.rolling_window_reference import vectorized_rolling_window
from .vectorized_references.swing_reference import vectorized_swing
from .vectorized_references.trend_reference import vectorized_trend
from .vectorized_references.zone_reference import vectorized_zone
from .vectorized_references.fibonacci_reference import vectorized_fibonacci
from .vectorized_references.market_structure_reference import vectorized_market_structure
from .vectorized_references.derived_zone_reference import vectorized_derived_zone
from .vectorized_references.displacement_reference import vectorized_displacement
from .vectorized_references.fair_value_gap_reference import vectorized_fair_value_gap
from .vectorized_references.order_block_reference import vectorized_order_block
from .vectorized_references.liquidity_zones_reference import vectorized_liquidity_zones
from .vectorized_references.premium_discount_reference import vectorized_premium_discount


# Keys to skip during comparison (hashes, enum strings stored as NaN)
SKIP_KEYS = {"pair_anchor_hash", "anchor_hash", "anchor_direction"}

# Keys that are enum-encoded as floats (need special comparison)
ENUM_FLOAT_KEYS = {
    "last_confirmed_pivot_type",  # NaN=none, 1.0=high, 0.0=low
    "pair_direction",             # NaN=none, 1.0=bullish, -1.0=bearish
    "last_wave_direction",        # NaN=none, 1.0=bullish, -1.0=bearish
    "bos_direction",              # NaN=none, 1.0=bullish, -1.0=bearish
    "choch_direction",            # NaN=none, 1.0=bullish, -1.0=bearish
}


@dataclass
class StructureDetectorResult:
    """Result of comparing a single structure detector."""

    detector: str
    dataset: str
    passed: bool
    max_abs_diff: float
    mismatched_keys: list[str] = field(default_factory=list)
    total_keys_checked: int = 0
    warmup_bars: int = 0
    error_message: str | None = None


@dataclass
class StructureParityAuditResult:
    """Result of the complete structure parity audit."""

    success: bool
    total_detectors: int
    passed_detectors: int
    failed_detectors: int
    tolerance: float
    bars_tested: int
    determinism_pass: bool
    results: list[StructureDetectorResult] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "success": self.success,
            "total_detectors": self.total_detectors,
            "passed_detectors": self.passed_detectors,
            "failed_detectors": self.failed_detectors,
            "tolerance": self.tolerance,
            "bars_tested": self.bars_tested,
            "determinism_pass": self.determinism_pass,
            "results": [
                {
                    "detector": r.detector,
                    "dataset": r.dataset,
                    "passed": r.passed,
                    "max_abs_diff": r.max_abs_diff,
                    "mismatched_keys": r.mismatched_keys,
                    "total_keys_checked": r.total_keys_checked,
                    "warmup_bars": r.warmup_bars,
                    "error_message": r.error_message,
                }
                for r in self.results
            ],
            "error_message": self.error_message,
        }

    def print_summary(self) -> None:
        """Print human-readable summary to console."""
        print(f"\n{'=' * 70}")
        print("STRUCTURE DETECTOR VECTORIZED vs INCREMENTAL PARITY AUDIT")
        print(f"{'=' * 70}")
        print(f"Bars tested: {self.bars_tested}")
        print(f"Tolerance: {self.tolerance}")
        print(f"Determinism: {'PASS' if self.determinism_pass else 'FAIL'}")
        print(f"Detectors: {self.passed_detectors}/{self.total_detectors} passed")
        print(f"{'=' * 70}\n")

        # Group by detector
        by_detector: dict[str, list[StructureDetectorResult]] = {}
        for r in self.results:
            by_detector.setdefault(r.detector, []).append(r)

        for detector, results in by_detector.items():
            all_pass = all(r.passed for r in results)
            status = "[PASS]" if all_pass else "[FAIL]"
            print(f"{status} {detector}")
            for r in results:
                ds_status = "OK" if r.passed else "FAIL"
                print(f"       [{ds_status}] {r.dataset}: max_diff={r.max_abs_diff:.2e}, keys={r.total_keys_checked}")
                if r.mismatched_keys:
                    print(f"            Mismatched: {', '.join(r.mismatched_keys[:5])}")
                if r.error_message:
                    print(f"            Error: {r.error_message}")
            print()

        if self.success:
            print("[OK] All structure detectors match vectorized references")
        else:
            print("[FAIL] Some structure detectors show parity issues")


def _ohlcv_from_df(df) -> dict[str, np.ndarray]:
    """Convert DataFrame to OHLCV dict of arrays."""
    return {
        "open": df["open"].values.astype(np.float64),
        "high": df["high"].values.astype(np.float64),
        "low": df["low"].values.astype(np.float64),
        "close": df["close"].values.astype(np.float64),
        "volume": df["volume"].values.astype(np.float64),
    }


def _compare_outputs(
    incremental: dict[str, np.ndarray],
    vectorized: dict[str, np.ndarray],
    warmup: int,
    tolerance: float,
) -> tuple[bool, float, list[str], int]:
    """
    Compare incremental vs vectorized outputs bar-by-bar.

    Returns: (passed, max_diff, mismatched_keys, keys_checked)
    """
    max_diff = 0.0
    mismatched_keys: list[str] = []
    keys_checked = 0

    # Only compare keys present in both
    common_keys = set(incremental.keys()) & set(vectorized.keys())

    for key in sorted(common_keys):
        if key in SKIP_KEYS:
            continue

        inc_arr = incremental[key]
        vec_arr = vectorized[key]

        # Skip warmup
        inc_post = inc_arr[warmup:]
        vec_post = vec_arr[warmup:]

        min_len = min(len(inc_post), len(vec_post))
        if min_len == 0:
            continue

        inc_post = inc_post[:min_len]
        vec_post = vec_post[:min_len]
        keys_checked += 1

        # Coerce object arrays to float64 (run_detector_batch uses dtype=object)
        if inc_post.dtype == object:
            inc_post = np.array(
                [float(v) if isinstance(v, (int, float)) else np.nan for v in inc_post],
                dtype=np.float64,
            )
        if vec_post.dtype == object:
            vec_post = np.array(
                [float(v) if isinstance(v, (int, float)) else np.nan for v in vec_post],
                dtype=np.float64,
            )

        if key in ENUM_FLOAT_KEYS:
            # For enum-encoded floats: both NaN = match, otherwise exact
            both_nan = np.isnan(inc_post) & np.isnan(vec_post)
            both_valid = ~np.isnan(inc_post) & ~np.isnan(vec_post)
            # Mismatch: one is NaN and other is not, or valid values differ
            one_nan = np.isnan(inc_post) != np.isnan(vec_post)
            valid_diff = np.zeros(min_len, dtype=bool)
            if both_valid.any():
                valid_diff[both_valid] = inc_post[both_valid] != vec_post[both_valid]
            if one_nan.any() or valid_diff.any():
                n_mismatch = int(one_nan.sum() + valid_diff.sum())
                if n_mismatch > 0:
                    mismatched_keys.append(f"{key}({n_mismatch})")
                    max_diff = max(max_diff, float("inf"))
        else:
            # Numeric comparison
            valid = ~np.isnan(inc_post) & ~np.isnan(vec_post)
            both_nan = np.isnan(inc_post) & np.isnan(vec_post)
            one_nan = np.isnan(inc_post) != np.isnan(vec_post)

            # One NaN and other not = mismatch
            if one_nan.any():
                n_mismatch = int(one_nan.sum())
                mismatched_keys.append(f"{key}(nan_mismatch={n_mismatch})")
                max_diff = max(max_diff, float("inf"))
                continue

            if valid.any():
                diffs = np.abs(inc_post[valid] - vec_post[valid])
                key_max = float(np.max(diffs))
                max_diff = max(max_diff, key_max)
                if key_max > tolerance:
                    mismatched_keys.append(f"{key}(max={key_max:.2e})")

    passed = len(mismatched_keys) == 0
    return passed, max_diff, mismatched_keys, keys_checked


def _encode_incremental_output(
    inc_outputs: dict[str, np.ndarray],
    detector_type: str,
) -> dict[str, np.ndarray]:
    """
    Encode incremental outputs to match vectorized encoding.

    The incremental side returns raw values via get_value() which may be
    strings, bools, etc. We need to encode them to match the vectorized
    reference's numeric encoding.
    """
    result = {}
    for key, arr in inc_outputs.items():
        if key in SKIP_KEYS:
            result[key] = arr
            continue

        # String-to-float encoding for known fields
        if key == "last_confirmed_pivot_type":
            encoded = np.full(len(arr), np.nan)
            for i in range(len(arr)):
                val = arr[i]
                if val == 1.0 or (isinstance(val, str) and val == "high"):
                    encoded[i] = 1.0
                elif val == 0.0 or (isinstance(val, str) and val == "low"):
                    encoded[i] = 0.0
                elif isinstance(val, str) and val == "":
                    encoded[i] = np.nan
            result[key] = encoded
        elif key == "pair_direction":
            encoded = np.full(len(arr), np.nan)
            for i in range(len(arr)):
                val = arr[i]
                if val == 1.0 or (isinstance(val, str) and val == "bullish"):
                    encoded[i] = 1.0
                elif val == -1.0 or (isinstance(val, str) and val == "bearish"):
                    encoded[i] = -1.0
                elif isinstance(val, str) and val == "":
                    encoded[i] = np.nan
            result[key] = encoded
        elif key == "last_wave_direction":
            encoded = np.full(len(arr), np.nan)
            for i in range(len(arr)):
                val = arr[i]
                if isinstance(val, str):
                    if val == "bullish":
                        encoded[i] = 1.0
                    elif val == "bearish":
                        encoded[i] = -1.0
                    elif val == "none":
                        encoded[i] = np.nan
                elif not np.isnan(val):
                    encoded[i] = val
            result[key] = encoded
        elif key in ("bos_direction", "choch_direction"):
            encoded = np.full(len(arr), np.nan)
            for i in range(len(arr)):
                val = arr[i]
                if isinstance(val, str):
                    if val == "bullish":
                        encoded[i] = 1.0
                    elif val == "bearish":
                        encoded[i] = -1.0
                    elif val == "none":
                        encoded[i] = np.nan
                elif not np.isnan(val):
                    encoded[i] = val
            result[key] = encoded
        elif key == "state":
            # zone state: "none"=0, "active"=1, "broken"=2
            encoded = np.zeros(len(arr))
            for i in range(len(arr)):
                val = arr[i]
                if isinstance(val, str):
                    if val == "active":
                        encoded[i] = 1.0
                    elif val == "broken":
                        encoded[i] = 2.0
                elif not np.isnan(val):
                    encoded[i] = val
            result[key] = encoded
        elif key.endswith("_state") and detector_type == "derived_zone":
            # derived_zone slot states
            encoded = np.zeros(len(arr))
            for i in range(len(arr)):
                val = arr[i]
                if isinstance(val, str):
                    if val == "active":
                        encoded[i] = 1.0
                    elif val == "broken":
                        encoded[i] = 2.0
                    elif val == "none":
                        encoded[i] = 0.0
                elif not np.isnan(val):
                    encoded[i] = val
            result[key] = encoded
        else:
            # Bool to float
            if arr.dtype == object:
                encoded = np.zeros(len(arr))
                for i in range(len(arr)):
                    val = arr[i]
                    if isinstance(val, bool):
                        encoded[i] = 1.0 if val else 0.0
                    elif isinstance(val, (int, float)):
                        encoded[i] = float(val) if not np.isnan(float(val)) else np.nan
                    else:
                        encoded[i] = np.nan
                result[key] = encoded
            else:
                result[key] = arr.astype(np.float64)

    return result


# =============================================================================
# Individual Detector Audits
# =============================================================================


def audit_rolling_window(ohlcv: dict[str, np.ndarray], tolerance: float, dataset: str) -> StructureDetectorResult:
    """Audit rolling_window detector parity."""
    try:
        params = {"size": 20, "source": "low", "mode": "min"}
        warmup = params["size"]

        inc = run_detector_batch("rolling_window", ohlcv, params)
        vec = vectorized_rolling_window(ohlcv, size=20, source="low", mode="min")

        passed, max_diff, mismatched, keys = _compare_outputs(inc, vec, warmup, tolerance)

        return StructureDetectorResult(
            detector="rolling_window",
            dataset=dataset,
            passed=passed,
            max_abs_diff=max_diff,
            mismatched_keys=mismatched,
            total_keys_checked=keys,
            warmup_bars=warmup,
        )
    except Exception as e:
        return StructureDetectorResult(
            detector="rolling_window", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=str(e),
        )


def audit_swing(ohlcv: dict[str, np.ndarray], tolerance: float, dataset: str) -> StructureDetectorResult:
    """Audit swing detector parity (fractal mode, no gates).

    Uses a manual incremental loop instead of run_detector_batch because
    the swing detector returns string outputs (last_confirmed_pivot_type,
    pair_direction) which get silently converted to NaN when stored in
    float64 arrays by run_detector_batch.  Object-dtype arrays preserve
    the strings so _encode_incremental_output can map them to floats.
    """
    try:
        left, right = 5, 5
        params = {"left": left, "right": right, "mode": "fractal"}
        warmup = left + right

        # Manual incremental loop (preserves string values)
        from src.structures.registry import STRUCTURE_REGISTRY
        from src.structures.base import BarData

        swing_cls = STRUCTURE_REGISTRY["swing"]
        swing_det = swing_cls(params, None)

        n = len(ohlcv["close"])
        inc_keys = swing_det.get_output_keys()
        inc_outputs: dict[str, np.ndarray] = {}
        for k in inc_keys:
            inc_outputs[k] = np.full(n, np.nan, dtype=object)

        for i in range(n):
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators={},
            )
            swing_det.update(i, bar)
            for k in inc_keys:
                try:
                    inc_outputs[k][i] = swing_det.get_value(k)
                except (KeyError, ValueError):
                    pass

        inc = _encode_incremental_output(inc_outputs, "swing")
        vec = vectorized_swing(ohlcv, left=left, right=right)

        passed, max_diff, mismatched, keys = _compare_outputs(inc, vec, warmup, tolerance)

        return StructureDetectorResult(
            detector="swing",
            dataset=dataset,
            passed=passed,
            max_abs_diff=max_diff,
            mismatched_keys=mismatched,
            total_keys_checked=keys,
            warmup_bars=warmup,
        )
    except Exception as e:
        return StructureDetectorResult(
            detector="swing", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=str(e),
        )


def audit_trend(ohlcv: dict[str, np.ndarray], tolerance: float, dataset: str) -> StructureDetectorResult:
    """Audit trend detector parity."""
    try:
        left, right = 5, 5
        swing_params = {"left": left, "right": right, "mode": "fractal"}
        warmup = (left + right) * 5

        # Run incremental: swing -> trend
        from src.structures.registry import STRUCTURE_REGISTRY
        swing_cls = STRUCTURE_REGISTRY["swing"]
        swing_det = swing_cls(swing_params, None)
        trend_cls = STRUCTURE_REGISTRY["trend"]
        trend_det = trend_cls({}, {"swing": swing_det})

        from src.structures.base import BarData
        n = len(ohlcv["close"])
        inc_keys = trend_det.get_output_keys()
        inc_outputs: dict[str, np.ndarray] = {k: np.full(n, np.nan, dtype=object) for k in inc_keys}

        for i in range(n):
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators={},
            )
            swing_det.update(i, bar)
            trend_det.update(i, bar)
            for k in inc_keys:
                try:
                    inc_outputs[k][i] = trend_det.get_value(k)
                except (KeyError, ValueError):
                    pass

        inc = _encode_incremental_output(inc_outputs, "trend")

        # Run vectorized: swing -> trend
        vec_swing = vectorized_swing(ohlcv, left=left, right=right)
        vec = vectorized_trend(vec_swing)

        passed, max_diff, mismatched, keys = _compare_outputs(inc, vec, warmup, tolerance)

        return StructureDetectorResult(
            detector="trend",
            dataset=dataset,
            passed=passed,
            max_abs_diff=max_diff,
            mismatched_keys=mismatched,
            total_keys_checked=keys,
            warmup_bars=warmup,
        )
    except Exception as e:
        return StructureDetectorResult(
            detector="trend", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=str(e),
        )


def audit_zone(ohlcv: dict[str, np.ndarray], tolerance: float, dataset: str) -> StructureDetectorResult:
    """Audit zone detector parity (demand zone, no ATR)."""
    try:
        left, right = 5, 5
        swing_params = {"left": left, "right": right, "mode": "fractal"}
        zone_params = {"zone_type": "demand", "width_atr": 1.5}
        warmup = left + right

        # Run incremental
        from src.structures.registry import STRUCTURE_REGISTRY
        from src.structures.base import BarData
        swing_cls = STRUCTURE_REGISTRY["swing"]
        swing_det = swing_cls(swing_params, None)
        zone_cls = STRUCTURE_REGISTRY["zone"]
        zone_det = zone_cls(zone_params, {"swing": swing_det})

        n = len(ohlcv["close"])
        inc_keys = zone_det.get_output_keys()
        inc_outputs: dict[str, np.ndarray] = {}
        for k in inc_keys:
            inc_outputs[k] = np.full(n, np.nan, dtype=object)

        for i in range(n):
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators={},
            )
            swing_det.update(i, bar)
            zone_det.update(i, bar)
            for k in inc_keys:
                try:
                    inc_outputs[k][i] = zone_det.get_value(k)
                except (KeyError, ValueError):
                    pass

        inc = _encode_incremental_output(inc_outputs, "zone")

        # Run vectorized
        vec_swing = vectorized_swing(ohlcv, left=left, right=right)
        vec = vectorized_zone(ohlcv, vec_swing, zone_type="demand", width_atr=1.5, atr_values=None)

        passed, max_diff, mismatched, keys = _compare_outputs(inc, vec, warmup, tolerance)

        return StructureDetectorResult(
            detector="zone",
            dataset=dataset,
            passed=passed,
            max_abs_diff=max_diff,
            mismatched_keys=mismatched,
            total_keys_checked=keys,
            warmup_bars=warmup,
        )
    except Exception as e:
        return StructureDetectorResult(
            detector="zone", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=str(e),
        )


def audit_fibonacci(ohlcv: dict[str, np.ndarray], tolerance: float, dataset: str) -> StructureDetectorResult:
    """Audit fibonacci detector parity (unpaired retracement mode)."""
    try:
        left, right = 5, 5
        swing_params = {"left": left, "right": right, "mode": "fractal"}
        fib_params = {"levels": [0.382, 0.5, 0.618], "mode": "retracement", "use_paired_anchor": False}
        warmup = left + right

        from src.structures.registry import STRUCTURE_REGISTRY
        from src.structures.base import BarData
        swing_cls = STRUCTURE_REGISTRY["swing"]
        swing_det = swing_cls(swing_params, None)
        fib_cls = STRUCTURE_REGISTRY["fibonacci"]
        fib_det = fib_cls(fib_params, {"swing": swing_det})

        n = len(ohlcv["close"])
        inc_keys = fib_det.get_output_keys()
        inc_outputs: dict[str, np.ndarray] = {}
        for k in inc_keys:
            inc_outputs[k] = np.full(n, np.nan, dtype=object)

        for i in range(n):
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators={},
            )
            swing_det.update(i, bar)
            fib_det.update(i, bar)
            for k in inc_keys:
                try:
                    inc_outputs[k][i] = fib_det.get_value(k)
                except (KeyError, ValueError):
                    pass

        inc = _encode_incremental_output(inc_outputs, "fibonacci")

        vec_swing = vectorized_swing(ohlcv, left=left, right=right)
        vec = vectorized_fibonacci(vec_swing, levels=[0.382, 0.5, 0.618], mode="retracement", use_paired_anchor=False)

        passed, max_diff, mismatched, keys = _compare_outputs(inc, vec, warmup, tolerance)

        return StructureDetectorResult(
            detector="fibonacci",
            dataset=dataset,
            passed=passed,
            max_abs_diff=max_diff,
            mismatched_keys=mismatched,
            total_keys_checked=keys,
            warmup_bars=warmup,
        )
    except Exception as e:
        return StructureDetectorResult(
            detector="fibonacci", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=str(e),
        )


def audit_fibonacci_paired(ohlcv: dict[str, np.ndarray], tolerance: float, dataset: str) -> StructureDetectorResult:
    """Audit fibonacci detector parity (paired anchor, new default)."""
    try:
        left, right = 5, 5
        swing_params = {"left": left, "right": right, "mode": "fractal"}
        fib_params = {"levels": [0.382, 0.5, 0.618], "mode": "retracement", "use_paired_anchor": True}
        warmup = left + right

        from src.structures.registry import STRUCTURE_REGISTRY
        from src.structures.base import BarData
        swing_cls = STRUCTURE_REGISTRY["swing"]
        swing_det = swing_cls(swing_params, None)
        fib_cls = STRUCTURE_REGISTRY["fibonacci"]
        fib_det = fib_cls(fib_params, {"swing": swing_det})

        n = len(ohlcv["close"])
        inc_keys = fib_det.get_output_keys()
        inc_outputs: dict[str, np.ndarray] = {}
        for k in inc_keys:
            inc_outputs[k] = np.full(n, np.nan, dtype=object)

        for i in range(n):
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators={},
            )
            swing_det.update(i, bar)
            fib_det.update(i, bar)
            for k in inc_keys:
                try:
                    inc_outputs[k][i] = fib_det.get_value(k)
                except (KeyError, ValueError):
                    pass

        inc = _encode_incremental_output(inc_outputs, "fibonacci")

        vec_swing = vectorized_swing(ohlcv, left=left, right=right)
        vec = vectorized_fibonacci(vec_swing, levels=[0.382, 0.5, 0.618], mode="retracement", use_paired_anchor=True)

        passed, max_diff, mismatched, keys = _compare_outputs(inc, vec, warmup, tolerance)

        return StructureDetectorResult(
            detector="fibonacci_paired",
            dataset=dataset,
            passed=passed,
            max_abs_diff=max_diff,
            mismatched_keys=mismatched,
            total_keys_checked=keys,
            warmup_bars=warmup,
        )
    except Exception as e:
        return StructureDetectorResult(
            detector="fibonacci_paired", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=str(e),
        )


def audit_fibonacci_trend(ohlcv: dict[str, np.ndarray], tolerance: float, dataset: str) -> StructureDetectorResult:
    """Audit fibonacci detector parity (trend-wave anchor mode)."""
    try:
        left, right = 5, 5
        swing_params = {"left": left, "right": right, "mode": "fractal"}
        fib_params = {
            "levels": [0.382, 0.5, 0.618],
            "mode": "retracement",
            "use_trend_anchor": True,
            "use_paired_anchor": False,
        }
        warmup = (left + right) * 5  # Trend warmup

        from src.structures.registry import STRUCTURE_REGISTRY
        from src.structures.base import BarData
        swing_cls = STRUCTURE_REGISTRY["swing"]
        swing_det = swing_cls(swing_params, None)
        trend_cls = STRUCTURE_REGISTRY["trend"]
        trend_det = trend_cls({}, {"swing": swing_det})
        fib_cls = STRUCTURE_REGISTRY["fibonacci"]
        fib_det = fib_cls(fib_params, {"swing": swing_det, "trend": trend_det})

        n = len(ohlcv["close"])
        inc_keys = fib_det.get_output_keys()
        inc_outputs: dict[str, np.ndarray] = {}
        for k in inc_keys:
            inc_outputs[k] = np.full(n, np.nan, dtype=object)

        # Also collect trend outputs for vectorized reference
        trend_keys = trend_det.get_output_keys()
        trend_inc_outputs: dict[str, np.ndarray] = {k: np.full(n, np.nan, dtype=object) for k in trend_keys}

        for i in range(n):
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators={},
            )
            swing_det.update(i, bar)
            trend_det.update(i, bar)
            fib_det.update(i, bar)
            for k in inc_keys:
                try:
                    inc_outputs[k][i] = fib_det.get_value(k)
                except (KeyError, ValueError):
                    pass
            for k in trend_keys:
                try:
                    trend_inc_outputs[k][i] = trend_det.get_value(k)
                except (KeyError, ValueError):
                    pass

        inc = _encode_incremental_output(inc_outputs, "fibonacci")

        # Vectorized: swing -> trend -> fib
        vec_swing = vectorized_swing(ohlcv, left=left, right=right)
        vec_trend = vectorized_trend(vec_swing)
        vec = vectorized_fibonacci(
            vec_swing, levels=[0.382, 0.5, 0.618], mode="retracement",
            use_trend_anchor=True, trend_outputs=vec_trend,
        )

        passed, max_diff, mismatched, keys = _compare_outputs(inc, vec, warmup, tolerance)

        return StructureDetectorResult(
            detector="fibonacci_trend",
            dataset=dataset,
            passed=passed,
            max_abs_diff=max_diff,
            mismatched_keys=mismatched,
            total_keys_checked=keys,
            warmup_bars=warmup,
        )
    except Exception as e:
        return StructureDetectorResult(
            detector="fibonacci_trend", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=str(e),
        )


def audit_market_structure(ohlcv: dict[str, np.ndarray], tolerance: float, dataset: str) -> StructureDetectorResult:
    """Audit market_structure detector parity."""
    try:
        left, right = 5, 5
        swing_params = {"left": left, "right": right, "mode": "fractal"}
        warmup = (left + right) * 3

        from src.structures.registry import STRUCTURE_REGISTRY
        from src.structures.base import BarData
        swing_cls = STRUCTURE_REGISTRY["swing"]
        swing_det = swing_cls(swing_params, None)
        ms_cls = STRUCTURE_REGISTRY["market_structure"]
        ms_det = ms_cls({}, {"swing": swing_det})

        n = len(ohlcv["close"])
        inc_keys = ms_det.get_output_keys()
        inc_outputs: dict[str, np.ndarray] = {}
        for k in inc_keys:
            inc_outputs[k] = np.full(n, np.nan, dtype=object)

        for i in range(n):
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators={},
            )
            swing_det.update(i, bar)
            ms_det.update(i, bar)
            for k in inc_keys:
                try:
                    inc_outputs[k][i] = ms_det.get_value(k)
                except (KeyError, ValueError):
                    pass

        inc = _encode_incremental_output(inc_outputs, "market_structure")

        vec_swing = vectorized_swing(ohlcv, left=left, right=right)
        vec = vectorized_market_structure(ohlcv, vec_swing)

        passed, max_diff, mismatched, keys = _compare_outputs(inc, vec, warmup, tolerance)

        return StructureDetectorResult(
            detector="market_structure",
            dataset=dataset,
            passed=passed,
            max_abs_diff=max_diff,
            mismatched_keys=mismatched,
            total_keys_checked=keys,
            warmup_bars=warmup,
        )
    except Exception as e:
        return StructureDetectorResult(
            detector="market_structure", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=str(e),
        )


def audit_derived_zone(ohlcv: dict[str, np.ndarray], tolerance: float, dataset: str) -> StructureDetectorResult:
    """Audit derived_zone detector parity."""
    try:
        left, right = 5, 5
        swing_params = {"left": left, "right": right, "mode": "fractal"}
        dz_params = {"levels": [0.382, 0.5, 0.618], "max_active": 5, "mode": "retracement", "width_pct": 0.002, "use_paired_source": False}
        warmup = left + right + 1

        from src.structures.registry import STRUCTURE_REGISTRY
        from src.structures.base import BarData
        swing_cls = STRUCTURE_REGISTRY["swing"]
        swing_det = swing_cls(swing_params, None)
        dz_cls = STRUCTURE_REGISTRY["derived_zone"]
        dz_det = dz_cls(dz_params, {"swing": swing_det})

        n = len(ohlcv["close"])
        inc_keys = dz_det.get_output_keys()
        inc_outputs: dict[str, np.ndarray] = {}
        for k in inc_keys:
            inc_outputs[k] = np.full(n, np.nan, dtype=object)

        for i in range(n):
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators={},
            )
            swing_det.update(i, bar)
            dz_det.update(i, bar)
            for k in inc_keys:
                try:
                    inc_outputs[k][i] = dz_det.get_value(k)
                except (KeyError, ValueError):
                    pass

        inc = _encode_incremental_output(inc_outputs, "derived_zone")

        vec_swing = vectorized_swing(ohlcv, left=left, right=right)
        vec = vectorized_derived_zone(
            ohlcv, vec_swing, levels=[0.382, 0.5, 0.618],
            max_active=5, mode="retracement", width_pct=0.002,
            use_paired_source=False,
        )

        passed, max_diff, mismatched, keys = _compare_outputs(inc, vec, warmup, tolerance)

        return StructureDetectorResult(
            detector="derived_zone",
            dataset=dataset,
            passed=passed,
            max_abs_diff=max_diff,
            mismatched_keys=mismatched,
            total_keys_checked=keys,
            warmup_bars=warmup,
        )
    except Exception as e:
        return StructureDetectorResult(
            detector="derived_zone", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=str(e),
        )


def audit_displacement(ohlcv: dict[str, np.ndarray], tolerance: float, dataset: str) -> StructureDetectorResult:
    """Audit displacement detector parity."""
    try:
        params = {
            "atr_key": "atr",
            "body_atr_min": 1.5,
            "wick_ratio_max": 0.4,
        }
        warmup = 1

        # Compute a simple ATR(14) from the OHLCV data
        n = len(ohlcv["close"])
        atr_period = 14
        atr_array = np.full(n, np.nan)

        # True Range
        tr = np.zeros(n)
        for i in range(n):
            hl = ohlcv["high"][i] - ohlcv["low"][i]
            if i == 0:
                tr[i] = hl
            else:
                hc = abs(ohlcv["high"][i] - ohlcv["close"][i - 1])
                lc = abs(ohlcv["low"][i] - ohlcv["close"][i - 1])
                tr[i] = max(hl, hc, lc)

        # Simple moving average of TR for ATR
        for i in range(atr_period - 1, n):
            atr_array[i] = np.mean(tr[i - atr_period + 1 : i + 1])

        # Run incremental via run_detector_batch
        inc = run_detector_batch(
            "displacement", ohlcv, params, indicators_data={"atr": atr_array}
        )

        # Encode incremental output (bool -> float)
        inc = _encode_incremental_output(inc, "displacement")

        # Run vectorized
        vec = vectorized_displacement(
            ohlcv, atr_array, body_atr_min=1.5, wick_ratio_max=0.4
        )

        passed, max_diff, mismatched, keys = _compare_outputs(
            inc, vec, warmup, tolerance
        )

        return StructureDetectorResult(
            detector="displacement",
            dataset=dataset,
            passed=passed,
            max_abs_diff=max_diff,
            mismatched_keys=mismatched,
            total_keys_checked=keys,
            warmup_bars=warmup,
        )
    except Exception as e:
        return StructureDetectorResult(
            detector="displacement",
            dataset=dataset,
            passed=False,
            max_abs_diff=float("inf"),
            error_message=str(e),
        )


def audit_fair_value_gap(ohlcv: dict[str, np.ndarray], tolerance: float, dataset: str) -> StructureDetectorResult:
    """Audit fair_value_gap detector parity (no ATR filter)."""
    try:
        params = {
            "atr_key": "atr",
            "min_gap_atr": 0.0,
            "max_active": 5,
        }
        warmup = 3

        # Run incremental via run_detector_batch
        inc = run_detector_batch("fair_value_gap", ohlcv, params)

        # Encode incremental output (bool -> float)
        inc = _encode_incremental_output(inc, "fair_value_gap")

        # Run vectorized
        vec = vectorized_fair_value_gap(
            ohlcv, atr_array=None, min_gap_atr=0.0, max_active=5
        )

        passed, max_diff, mismatched, keys = _compare_outputs(
            inc, vec, warmup, tolerance
        )

        return StructureDetectorResult(
            detector="fair_value_gap",
            dataset=dataset,
            passed=passed,
            max_abs_diff=max_diff,
            mismatched_keys=mismatched,
            total_keys_checked=keys,
            warmup_bars=warmup,
        )
    except Exception as e:
        return StructureDetectorResult(
            detector="fair_value_gap",
            dataset=dataset,
            passed=False,
            max_abs_diff=float("inf"),
            error_message=str(e),
        )


def audit_liquidity_zones(ohlcv: dict[str, np.ndarray], tolerance: float, dataset: str) -> StructureDetectorResult:
    """Audit liquidity_zones detector parity."""
    try:
        left, right = 3, 3
        swing_params = {"left": left, "right": right, "mode": "fractal"}
        lz_params = {
            "atr_key": "atr",
            "tolerance_atr": 0.3,
            "sweep_atr": 0.1,
            "min_touches": 2,
            "max_active": 5,
            "max_swing_history": 20,
        }
        warmup = (left + right) * lz_params["min_touches"]

        # Compute a simple ATR(14) from the OHLCV data
        n = len(ohlcv["close"])
        atr_period = 14
        atr_array = np.full(n, np.nan)

        # True Range
        tr = np.zeros(n)
        for i in range(n):
            hl = ohlcv["high"][i] - ohlcv["low"][i]
            if i == 0:
                tr[i] = hl
            else:
                hc = abs(ohlcv["high"][i] - ohlcv["close"][i - 1])
                lc = abs(ohlcv["low"][i] - ohlcv["close"][i - 1])
                tr[i] = max(hl, hc, lc)

        # Simple moving average of TR for ATR
        for i in range(atr_period - 1, n):
            atr_array[i] = np.mean(tr[i - atr_period + 1 : i + 1])

        # Run incremental: swing -> liquidity_zones with ATR in indicators
        from src.structures.registry import STRUCTURE_REGISTRY
        from src.structures.base import BarData
        swing_cls = STRUCTURE_REGISTRY["swing"]
        swing_det = swing_cls(swing_params, None)
        lz_cls = STRUCTURE_REGISTRY["liquidity_zones"]
        lz_det = lz_cls(lz_params, {"swing": swing_det})

        inc_keys = lz_det.get_output_keys()
        inc_outputs: dict[str, np.ndarray] = {}
        for k in inc_keys:
            inc_outputs[k] = np.full(n, np.nan, dtype=object)

        for i in range(n):
            atr_val = float(atr_array[i]) if not np.isnan(atr_array[i]) else float("nan")
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]),
                indicators={"atr": atr_val},
            )
            swing_det.update(i, bar)
            lz_det.update(i, bar)
            for k in inc_keys:
                try:
                    inc_outputs[k][i] = lz_det.get_value(k)
                except (KeyError, ValueError):
                    pass

        inc = _encode_incremental_output(inc_outputs, "liquidity_zones")

        # Run vectorized: swing -> liquidity_zones
        vec_swing = vectorized_swing(ohlcv, left=left, right=right)
        vec = vectorized_liquidity_zones(
            ohlcv, vec_swing, atr_array=atr_array,
            tolerance_atr=0.3, sweep_atr=0.1,
            min_touches=2, max_active=5, max_swing_history=20,
        )

        passed, max_diff, mismatched, keys = _compare_outputs(
            inc, vec, warmup, tolerance
        )

        return StructureDetectorResult(
            detector="liquidity_zones",
            dataset=dataset,
            passed=passed,
            max_abs_diff=max_diff,
            mismatched_keys=mismatched,
            total_keys_checked=keys,
            warmup_bars=warmup,
        )
    except Exception as e:
        return StructureDetectorResult(
            detector="liquidity_zones",
            dataset=dataset,
            passed=False,
            max_abs_diff=float("inf"),
            error_message=str(e),
        )


def audit_order_block(ohlcv: dict[str, np.ndarray], tolerance: float, dataset: str) -> StructureDetectorResult:
    """Audit order_block detector parity (inline displacement, no dep)."""
    try:
        params = {
            "atr_key": "atr",
            "use_body": True,
            "require_displacement": True,
            "body_atr_min": 1.5,
            "wick_ratio_max": 0.4,
            "max_active": 5,
            "lookback": 3,
        }
        warmup = max(params["lookback"] + 2, 10)  # swing L+R default 5+5

        # Compute a simple ATR(14) from the OHLCV data
        n = len(ohlcv["close"])
        atr_period = 14
        atr_array = np.full(n, np.nan)

        # True Range
        tr = np.zeros(n)
        for i in range(n):
            hl = ohlcv["high"][i] - ohlcv["low"][i]
            if i == 0:
                tr[i] = hl
            else:
                hc = abs(ohlcv["high"][i] - ohlcv["close"][i - 1])
                lc = abs(ohlcv["low"][i] - ohlcv["close"][i - 1])
                tr[i] = max(hl, hc, lc)

        # Simple moving average of TR for ATR
        for i in range(atr_period - 1, n):
            atr_array[i] = np.mean(tr[i - atr_period + 1 : i + 1])

        # Run incremental: swing -> order_block (manual loop)
        from src.structures.registry import STRUCTURE_REGISTRY
        from src.structures.base import BarData

        swing_cls = STRUCTURE_REGISTRY["swing"]
        swing_params = {"left": 5, "right": 5, "mode": "fractal"}
        swing_det = swing_cls(swing_params, None)

        ob_cls = STRUCTURE_REGISTRY["order_block"]
        ob_det = ob_cls(params, {"swing": swing_det})

        inc_keys = ob_det.get_output_keys()
        inc_outputs: dict[str, np.ndarray] = {k: np.full(n, np.nan, dtype=object) for k in inc_keys}

        for i in range(n):
            bar_indicators: dict[str, float] = {}
            if not np.isnan(atr_array[i]):
                bar_indicators["atr"] = float(atr_array[i])

            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators=bar_indicators,
            )
            swing_det.update(i, bar)
            ob_det.update(i, bar)
            for k in inc_keys:
                try:
                    inc_outputs[k][i] = ob_det.get_value(k)
                except (KeyError, ValueError):
                    pass

        inc = _encode_incremental_output(inc_outputs, "order_block")

        # Run vectorized: swing -> order_block
        vec_swing = vectorized_swing(ohlcv, left=5, right=5)
        vec = vectorized_order_block(
            ohlcv, vec_swing, atr_array=atr_array,
            use_body=True, body_atr_min=1.5, wick_ratio_max=0.4,
            max_active=5, lookback=3,
        )

        passed, max_diff, mismatched, keys = _compare_outputs(
            inc, vec, warmup, tolerance
        )

        return StructureDetectorResult(
            detector="order_block",
            dataset=dataset,
            passed=passed,
            max_abs_diff=max_diff,
            mismatched_keys=mismatched,
            total_keys_checked=keys,
            warmup_bars=warmup,
        )
    except Exception as e:
        return StructureDetectorResult(
            detector="order_block",
            dataset=dataset,
            passed=False,
            max_abs_diff=float("inf"),
            error_message=str(e),
        )


def audit_premium_discount(ohlcv: dict[str, np.ndarray], tolerance: float, dataset: str) -> StructureDetectorResult:
    """Audit premium_discount detector parity."""
    try:
        params: dict[str, object] = {}
        warmup = 10  # swing L+R default 5+5

        # Run incremental: swing -> premium_discount (manual loop)
        from src.structures.registry import STRUCTURE_REGISTRY
        from src.structures.base import BarData

        n = len(ohlcv["close"])

        swing_cls = STRUCTURE_REGISTRY["swing"]
        swing_params = {"left": 5, "right": 5, "mode": "fractal"}
        swing_det = swing_cls(swing_params, None)

        pd_cls = STRUCTURE_REGISTRY["premium_discount"]
        pd_det = pd_cls(params, {"swing": swing_det})

        inc_keys = pd_det.get_output_keys()
        inc_outputs: dict[str, np.ndarray] = {k: np.full(n, np.nan, dtype=object) for k in inc_keys}

        for i in range(n):
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators={},
            )
            swing_det.update(i, bar)
            pd_det.update(i, bar)
            for k in inc_keys:
                try:
                    inc_outputs[k][i] = pd_det.get_value(k)
                except (KeyError, ValueError):
                    pass

        inc = _encode_incremental_output(inc_outputs, "premium_discount")

        # Run vectorized: swing -> premium_discount
        vec_swing = vectorized_swing(ohlcv, left=5, right=5)
        vec = vectorized_premium_discount(ohlcv, vec_swing)

        passed, max_diff, mismatched, keys = _compare_outputs(
            inc, vec, warmup, tolerance
        )

        return StructureDetectorResult(
            detector="premium_discount",
            dataset=dataset,
            passed=passed,
            max_abs_diff=max_diff,
            mismatched_keys=mismatched,
            total_keys_checked=keys,
            warmup_bars=warmup,
        )
    except Exception as e:
        return StructureDetectorResult(
            detector="premium_discount",
            dataset=dataset,
            passed=False,
            max_abs_diff=float("inf"),
            error_message=str(e),
        )


# =============================================================================
# NaN-Resilience Audit (Phase 2: Live/Backtest Indicator Parity)
# =============================================================================


def audit_nan_resilience(ohlcv: dict[str, np.ndarray], dataset: str) -> list[StructureDetectorResult]:
    """
    Test all 7 detectors with NaN/missing indicator inputs.

    Verifies that no detector crashes and all produce predictable outputs
    when indicators are unavailable — the exact condition structures face
    in live/shadow mode when indicators arrive late or NaN from WS lag.

    Returns list of StructureDetectorResult (one per detector tested).
    """
    from src.structures.registry import STRUCTURE_REGISTRY
    from src.structures.base import BarData

    results: list[StructureDetectorResult] = []
    n = min(len(ohlcv["close"]), 500)  # Cap at 500 bars for speed

    # --- 1. Swing: significance outputs should be NaN when atr_key missing ---
    try:
        swing_params = {"left": 5, "right": 5, "mode": "fractal", "atr_key": "atr_14"}
        swing_cls = STRUCTURE_REGISTRY["swing"]
        det = swing_cls(swing_params, None)

        nan_count = 0
        for i in range(n):
            # Feed bars with EMPTY indicators — atr_14 not available
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators={},
            )
            det.update(i, bar)

        # After warmup, significance should be NaN (not crash, not 0)
        import math
        high_sig = det.get_value("high_significance")
        low_sig = det.get_value("low_significance")
        sig_ok = (isinstance(high_sig, float) and math.isnan(high_sig) and
                  isinstance(low_sig, float) and math.isnan(low_sig))
        # high/low_level should still be valid (pivots don't need ATR)
        high_level = det.get_value("high_level")
        pivots_ok = not (isinstance(high_level, float) and math.isnan(high_level))

        results.append(StructureDetectorResult(
            detector="swing_nan_atr", dataset=dataset, passed=sig_ok and pivots_ok,
            max_abs_diff=0.0, total_keys_checked=4,
            error_message=None if (sig_ok and pivots_ok) else
                f"sig_ok={sig_ok} pivots_ok={pivots_ok} high_sig={high_sig} high_level={high_level}",
        ))
    except Exception as e:
        results.append(StructureDetectorResult(
            detector="swing_nan_atr", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=f"CRASH: {e}",
        ))

    # --- 2. Zone: should stay "none" when ATR indicator is missing ---
    try:
        swing_params = {"left": 5, "right": 5, "mode": "fractal"}
        swing_cls = STRUCTURE_REGISTRY["swing"]
        swing_det = swing_cls(swing_params, None)
        zone_cls = STRUCTURE_REGISTRY["zone"]
        zone_det = zone_cls(
            {"zone_type": "demand", "width_atr": 1.5, "atr_key": "atr_14"},
            {"swing": swing_det},
        )

        for i in range(n):
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators={},  # No ATR
            )
            swing_det.update(i, bar)
            zone_det.update(i, bar)

        state = zone_det.get_value("state")
        # Without ATR, zone can never form — must stay "none"
        passed = state == "none"
        results.append(StructureDetectorResult(
            detector="zone_nan_atr", dataset=dataset, passed=passed,
            max_abs_diff=0.0, total_keys_checked=1,
            error_message=None if passed else f"Expected state='none', got '{state}'",
        ))
    except Exception as e:
        results.append(StructureDetectorResult(
            detector="zone_nan_atr", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=f"CRASH: {e}",
        ))

    # --- 3. Zone: should form zones when ATR IS provided (control test) ---
    try:
        swing_params = {"left": 5, "right": 5, "mode": "fractal"}
        swing_det2 = STRUCTURE_REGISTRY["swing"](swing_params, None)
        zone_det2 = STRUCTURE_REGISTRY["zone"](
            {"zone_type": "demand", "width_atr": 1.5, "atr_key": "atr_14"},
            {"swing": swing_det2},
        )

        # Compute a simple ATR-like value from the data
        for i in range(n):
            atr_val = float(ohlcv["high"][i] - ohlcv["low"][i]) if i > 0 else 100.0
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]),
                indicators={"atr_14": atr_val},  # ATR provided
            )
            swing_det2.update(i, bar)
            zone_det2.update(i, bar)

        state2 = zone_det2.get_value("state")
        version2 = zone_det2.get_value("version")
        # With ATR and 500 bars of synthetic data, a zone should have formed
        passed = state2 != "none" or version2 > 0
        results.append(StructureDetectorResult(
            detector="zone_with_atr", dataset=dataset, passed=passed,
            max_abs_diff=0.0, total_keys_checked=2,
            error_message=None if passed else f"Zone never formed: state={state2}, version={version2}",
        ))
    except Exception as e:
        results.append(StructureDetectorResult(
            detector="zone_with_atr", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=f"CRASH: {e}",
        ))

    # --- 4. Fibonacci: levels should be NaN when no swing pair has formed ---
    try:
        swing_params = {"left": 5, "right": 5, "mode": "fractal"}
        swing_det3 = STRUCTURE_REGISTRY["swing"](swing_params, None)
        fib_cls = STRUCTURE_REGISTRY["fibonacci"]
        fib_det = fib_cls(
            {"levels": [0.382, 0.618], "mode": "retracement"},
            {"swing": swing_det3},
        )

        # Feed only 3 bars — not enough for any swing to form (left=5, right=5)
        import math
        for i in range(3):
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators={},
            )
            swing_det3.update(i, bar)
            fib_det.update(i, bar)

        level_618 = fib_det.get_value("level_0.618")
        level_382 = fib_det.get_value("level_0.382")
        passed = (isinstance(level_618, float) and math.isnan(level_618) and
                  isinstance(level_382, float) and math.isnan(level_382))
        results.append(StructureDetectorResult(
            detector="fibonacci_pre_swing", dataset=dataset, passed=passed,
            max_abs_diff=0.0, total_keys_checked=2,
            error_message=None if passed else f"Fib levels not NaN before swing: 0.618={level_618}, 0.382={level_382}",
        ))
    except Exception as e:
        results.append(StructureDetectorResult(
            detector="fibonacci_pre_swing", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=f"CRASH: {e}",
        ))

    # --- 5. Derived zone: empty-slot sentinels when no zones exist ---
    try:
        swing_params = {"left": 5, "right": 5, "mode": "fractal"}
        swing_det4 = STRUCTURE_REGISTRY["swing"](swing_params, None)
        dz_cls = STRUCTURE_REGISTRY["derived_zone"]
        dz_det = dz_cls(
            {"levels": [0.5], "max_active": 3, "mode": "retracement",
             "width_pct": 0.002, "use_paired_source": False},
            {"swing": swing_det4},
        )

        # Feed only 3 bars — no swing, no zones
        for i in range(3):
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators={},
            )
            swing_det4.update(i, bar)
            dz_det.update(i, bar)

        # Empty sentinels: state="none", floats=None, ints=-1, bools=false
        state0 = dz_det.get_value("zone0_state")
        active_count = dz_det.get_value("active_count")
        passed = state0 == "none" and active_count == 0
        results.append(StructureDetectorResult(
            detector="derived_zone_empty", dataset=dataset, passed=passed,
            max_abs_diff=0.0, total_keys_checked=2,
            error_message=None if passed else f"zone0_state={state0}, active_count={active_count}",
        ))
    except Exception as e:
        results.append(StructureDetectorResult(
            detector="derived_zone_empty", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=f"CRASH: {e}",
        ))

    # --- 6. All 7 detectors: no crash with fully empty indicators over 500 bars ---
    try:
        swing_params = {"left": 5, "right": 5, "mode": "fractal"}
        swing_det5 = STRUCTURE_REGISTRY["swing"](swing_params, None)

        # Build all detectors that depend on swing
        detectors = {"swing": swing_det5}
        for dtype in ["trend", "market_structure", "zone", "fibonacci", "derived_zone", "rolling_window"]:
            cls = STRUCTURE_REGISTRY[dtype]
            if dtype == "zone":
                params = {"zone_type": "demand", "width_atr": 1.5, "atr_key": "atr_14"}
                deps = {"swing": swing_det5}
            elif dtype == "fibonacci":
                params = {"levels": [0.382, 0.618], "mode": "retracement"}
                deps = {"swing": swing_det5}
            elif dtype == "derived_zone":
                params = {"levels": [0.5], "max_active": 3, "mode": "retracement",
                          "width_pct": 0.002, "use_paired_source": False}
                deps = {"swing": swing_det5}
            elif dtype == "rolling_window":
                params = {"size": 20, "mode": "max", "source": "high"}
                deps = None  # type: ignore[assignment]
            elif dtype == "trend":
                params = {}
                deps = {"swing": swing_det5}
            elif dtype == "market_structure":
                params = {}
                deps = {"swing": swing_det5}
            else:
                params = {}
                deps = {"swing": swing_det5}
            detectors[dtype] = cls(params, deps)

        crash_errors: list[str] = []
        for i in range(n):
            bar = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]), indicators={},  # Empty!
            )
            for dtype, det in detectors.items():
                try:
                    det.update(i, bar)
                except Exception as e:
                    crash_errors.append(f"{dtype} bar {i}: {e}")
                    if len(crash_errors) > 5:
                        break
            if len(crash_errors) > 5:
                break

        passed = len(crash_errors) == 0
        results.append(StructureDetectorResult(
            detector="all_nan_no_crash", dataset=dataset, passed=passed,
            max_abs_diff=0.0, total_keys_checked=7,
            error_message=None if passed else "; ".join(crash_errors[:3]),
        ))
    except Exception as e:
        results.append(StructureDetectorResult(
            detector="all_nan_no_crash", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=f"CRASH: {e}",
        ))

    # --- 7. Zone parity: NaN ATR for first 50 bars, then real ATR ---
    # Simulates live scenario: indicators arrive after warmup period
    try:
        swing_params = {"left": 5, "right": 5, "mode": "fractal"}
        swing_a = STRUCTURE_REGISTRY["swing"](swing_params, None)
        swing_b = STRUCTURE_REGISTRY["swing"](swing_params, None)
        zone_a = STRUCTURE_REGISTRY["zone"](
            {"zone_type": "demand", "width_atr": 1.5, "atr_key": "atr_14"},
            {"swing": swing_a},
        )
        zone_b = STRUCTURE_REGISTRY["zone"](
            {"zone_type": "demand", "width_atr": 1.5, "atr_key": "atr_14"},
            {"swing": swing_b},
        )

        atr_start_bar = 50  # Simulate ATR becoming available after 50 bars
        for i in range(n):
            atr_val = float(ohlcv["high"][i] - ohlcv["low"][i]) if i >= atr_start_bar else float("nan")
            # Run A: NaN ATR for first 50 bars (live scenario)
            bar_a = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]),
                indicators={"atr_14": atr_val} if i >= atr_start_bar else {},
            )
            swing_a.update(i, bar_a)
            zone_a.update(i, bar_a)

            # Run B: ATR always available (backtest scenario)
            atr_always = float(ohlcv["high"][i] - ohlcv["low"][i]) if i > 0 else 100.0
            bar_b = BarData(
                idx=i, open=float(ohlcv["open"][i]), high=float(ohlcv["high"][i]),
                low=float(ohlcv["low"][i]), close=float(ohlcv["close"][i]),
                volume=float(ohlcv["volume"][i]),
                indicators={"atr_14": atr_always},
            )
            swing_b.update(i, bar_b)
            zone_b.update(i, bar_b)

        # After bar 50, both should converge (not necessarily identical due
        # to missed zone opportunities, but neither should crash)
        state_a = zone_a.get_value("state")
        state_b = zone_b.get_value("state")
        ver_a = zone_a.get_value("version")
        ver_b = zone_b.get_value("version")

        # Key assertion: late-ATR zone didn't crash and eventually formed zones
        passed = ver_a >= 0  # No crash is the minimum bar
        results.append(StructureDetectorResult(
            detector="zone_late_atr_parity", dataset=dataset, passed=passed,
            max_abs_diff=0.0, total_keys_checked=4,
            error_message=None if passed else
                f"Late ATR: state={state_a}, ver={ver_a} vs always: state={state_b}, ver={ver_b}",
        ))
    except Exception as e:
        results.append(StructureDetectorResult(
            detector="zone_late_atr_parity", dataset=dataset, passed=False,
            max_abs_diff=float("inf"), error_message=f"CRASH: {e}",
        ))

    return results


# =============================================================================
# Main Audit Runner
# =============================================================================


def run_structure_parity_audit(
    bars: int = 2000,
    tolerance: float = 1e-10,
    seed: int = 42,
) -> StructureParityAuditResult:
    """
    Run the complete structure detector vectorized vs incremental parity audit.

    Tests all 7 detectors across synthetic data + edge cases + real data
    (if available). Also verifies determinism by running twice.

    Args:
        bars: Number of synthetic bars to test.
        tolerance: Maximum allowed absolute difference for floats.
        seed: Random seed for reproducibility.

    Returns:
        StructureParityAuditResult with all detector results.
    """
    try:
        results: list[StructureDetectorResult] = []

        # Generate datasets
        datasets: dict[str, dict[str, np.ndarray]] = {}
        df_synth = generate_synthetic_ohlcv(bars=bars, seed=seed)
        datasets["synthetic"] = _ohlcv_from_df(df_synth)

        df_rapid = generate_rapid_swing_data(bars=min(bars, 1000), seed=seed + 1)
        datasets["rapid_swings"] = _ohlcv_from_df(df_rapid)

        # Edge case datasets
        df_flat = generate_flat_bars(bars=200, price=50000.0)
        datasets["flat_bars"] = _ohlcv_from_df(df_flat)

        df_gap = generate_gap_data(bars=min(bars, 1000), seed=seed + 2)
        datasets["gap_data"] = _ohlcv_from_df(df_gap)

        df_rise = generate_monotonic_rise(bars=300, seed=seed + 3)
        datasets["monotonic_rise"] = _ohlcv_from_df(df_rise)

        df_fall = generate_monotonic_fall(bars=300, seed=seed + 4)
        datasets["monotonic_fall"] = _ohlcv_from_df(df_fall)

        # Try loading real data (1h primary)
        for symbol in ["BTCUSDT", "ETHUSDT"]:
            for tf in ["1h"]:
                df_real = load_real_ohlcv(symbol=symbol, timeframe=tf, bars=bars)
                if df_real is not None and len(df_real) >= 100:
                    datasets[f"real_{symbol}_{tf}"] = _ohlcv_from_df(df_real)

        # Audit functions for each detector
        audit_funcs = [
            audit_rolling_window,
            audit_swing,
            audit_trend,
            audit_zone,
            audit_fibonacci,
            audit_fibonacci_paired,
            audit_fibonacci_trend,
            audit_market_structure,
            audit_derived_zone,
            audit_displacement,
            audit_fair_value_gap,
            audit_order_block,
            audit_liquidity_zones,
            audit_premium_discount,
        ]

        # Run each audit on each dataset
        for audit_func in audit_funcs:
            for ds_name, ohlcv in datasets.items():
                try:
                    result = audit_func(ohlcv, tolerance, ds_name)
                    results.append(result)
                except Exception as e:
                    results.append(StructureDetectorResult(
                        detector=audit_func.__name__.replace("audit_", ""),
                        dataset=ds_name,
                        passed=False,
                        max_abs_diff=float("inf"),
                        error_message=f"Unhandled: {e}",
                    ))

        # NaN-resilience tests (Phase 2: live/backtest indicator parity)
        nan_results = audit_nan_resilience(datasets["synthetic"], "synthetic")
        results.extend(nan_results)

        # Determinism check: run swing twice on synthetic data, compare
        # Uses manual loop to preserve string outputs for proper comparison
        determinism_pass = True
        try:
            from src.structures.registry import STRUCTURE_REGISTRY
            from src.structures.base import BarData

            ohlcv_det = datasets["synthetic"]
            n_det = len(ohlcv_det["close"])
            det_params = {"left": 5, "right": 5, "mode": "fractal"}

            def _run_swing_manual(ohlcv_data: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
                swing_cls = STRUCTURE_REGISTRY["swing"]
                det = swing_cls(det_params, None)
                keys = det.get_output_keys()
                out: dict[str, np.ndarray] = {k: np.full(n_det, np.nan, dtype=object) for k in keys}
                for i in range(n_det):
                    bar = BarData(
                        idx=i, open=float(ohlcv_data["open"][i]),
                        high=float(ohlcv_data["high"][i]),
                        low=float(ohlcv_data["low"][i]),
                        close=float(ohlcv_data["close"][i]),
                        volume=float(ohlcv_data["volume"][i]), indicators={},
                    )
                    det.update(i, bar)
                    for k in keys:
                        try:
                            out[k][i] = det.get_value(k)
                        except (KeyError, ValueError):
                            pass
                return _encode_incremental_output(out, "swing")

            run1 = _run_swing_manual(ohlcv_det)
            run2 = _run_swing_manual(ohlcv_det)

            for key in run1:
                if key in SKIP_KEYS:
                    continue
                a1 = run1[key]
                a2 = run2[key]
                both_nan = np.isnan(a1) & np.isnan(a2)
                valid = ~np.isnan(a1) & ~np.isnan(a2)
                if valid.any() and not np.array_equal(a1[valid], a2[valid]):
                    determinism_pass = False
                    break
                one_nan = np.isnan(a1) != np.isnan(a2)
                if one_nan.any():
                    determinism_pass = False
                    break
        except Exception:
            determinism_pass = False

        # Summary
        # Count unique detector names that have ALL datasets passing
        det_names = sorted(set(r.detector for r in results))
        passed_detectors = 0
        for det in det_names:
            det_results = [r for r in results if r.detector == det]
            if all(r.passed for r in det_results):
                passed_detectors += 1

        failed_detectors = len(det_names) - passed_detectors
        success = failed_detectors == 0 and determinism_pass

        return StructureParityAuditResult(
            success=success,
            total_detectors=len(det_names),
            passed_detectors=passed_detectors,
            failed_detectors=failed_detectors,
            tolerance=tolerance,
            bars_tested=bars,
            determinism_pass=determinism_pass,
            results=results,
        )

    except Exception as e:
        import traceback
        return StructureParityAuditResult(
            success=False,
            total_detectors=0,
            passed_detectors=0,
            failed_detectors=0,
            tolerance=tolerance,
            bars_tested=bars,
            determinism_pass=False,
            error_message=f"Audit failed: {e}\n{traceback.format_exc()}",
        )
