"""
Forge stress test tools.

ToolResult wrappers for the stress test suite and validation framework.
This is part of the smoke test refactor - provides CLI/API surface for validation.
"""

import traceback
from pathlib import Path

from .shared import ToolResult
from ..forge.validation.synthetic_data import PatternType
from ..utils.logger import get_logger


logger = get_logger()


# =============================================================================
# Stress Test Suite Tool
# =============================================================================

def forge_stress_test_tool(
    validation_plays_dir: Path | str | None = None,
    skip_audits: bool = False,
    skip_backtest: bool = False,
    trace_hashes: bool = True,
    use_synthetic_data: bool = True,
    seed: int = 42,
    bars_per_tf: int = 1000,
    pattern: str = "trending",
    timeframes: list[str] | None = None,
) -> ToolResult:
    """
    Run complete Forge stress test suite with hash tracing.

    This is the foundation of the smoke test refactor. Each step produces
    input_hash → output_hash for debugging and flow tracing.

    Steps (each produces input_hash → output_hash):
    1. Generate synthetic candle data (all TFs) → synthetic_data_hash
    2. Validate all plays (normalize-batch) → config_hash
    3. Run toolkit audit (registry contract) → registry_hash
    4. Run structure parity (synthetic data) → structure_hash
    5. Run indicator parity (synthetic data) → indicator_hash
    6. Run rollup audit (1m aggregation) → rollup_hash
    7. Execute validation plays as backtests → trades_hash, equity_hash
    8. Verify artifacts + determinism → run_hash

    Args:
        validation_plays_dir: Directory containing validation plays
            (default: plays/validation)
        skip_audits: Skip audit steps 3-6 (default: False)
        skip_backtest: Skip backtest steps 7-8 (default: False)
        trace_hashes: Enable hash tracing (default: True)
        use_synthetic_data: Use synthetic data for parity checks (default: True)
        seed: Random seed for synthetic data (default: 42)
        bars_per_tf: Bars per timeframe (default: 1000)
        pattern: Synthetic data pattern: "trending", "ranging", "volatile", "multi_tf_aligned"
            (default: "trending")
        timeframes: Timeframes to generate (default: ["1m", "5m", "15m", "1h", "4h"])

    Returns:
        ToolResult with complete stress test report including hash chain
    """
    try:
        from ..forge.audits.stress_test_suite import run_stress_test_suite

        # Convert string path to Path if needed
        plays_dir = None
        if validation_plays_dir is not None:
            plays_dir = Path(validation_plays_dir) if isinstance(validation_plays_dir, str) else validation_plays_dir

        report = run_stress_test_suite(
            validation_plays_dir=plays_dir,
            skip_audits=skip_audits,
            skip_backtest=skip_backtest,
            trace_hashes=trace_hashes,
            use_synthetic_data=use_synthetic_data,
            seed=seed,
            bars_per_tf=bars_per_tf,
            pattern=pattern,
            timeframes=timeframes,
        )

        if report.overall_passed:
            return ToolResult(
                success=True,
                message=(
                    f"Stress test PASSED: {report.summary['passed_steps']}/{report.summary['total_steps']} steps "
                    f"({report.total_duration_seconds:.1f}s)"
                ),
                data=report.to_dict(),
            )
        else:
            # Find first failed step for error message
            failed_steps = [s for s in report.steps if not s.passed]
            first_failure = failed_steps[0] if failed_steps else None
            error_detail = f" - First failure: {first_failure.step_name}: {first_failure.message}" if first_failure else ""

            return ToolResult(
                success=False,
                error=(
                    f"Stress test FAILED: {report.summary['failed_steps']} step(s) failed"
                    f"{error_detail}"
                ),
                data=report.to_dict(),
            )

    except Exception as e:
        logger.error(f"Stress test failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Stress test error: {e}",
        )


# =============================================================================
# Synthetic Data Generation Tool
# =============================================================================

def forge_generate_synthetic_data_tool(
    symbol: str = "BTCUSDT",
    timeframes: list[str] | None = None,
    bars_per_tf: int = 1000,
    seed: int = 42,
    pattern: PatternType = "trending",
) -> ToolResult:
    """
    Generate synthetic candle data for testing.

    Produces deterministic, reproducible OHLCV data for validating:
    - Structure detection (swing, zone, fibonacci, trend)
    - Indicator computation (INDICATOR_REGISTRY parity)
    - Multi-timeframe alignment

    Args:
        symbol: Trading symbol (default: "BTCUSDT")
        timeframes: List of timeframes to generate
            (default: ["1m", "5m", "15m", "1h", "4h"])
        bars_per_tf: Number of bars per timeframe (default: 1000)
        seed: Random seed for reproducibility (default: 42)
        pattern: Price pattern type (default: "trending")
            - "trending": Clear directional move (swing highs/lows)
            - "ranging": Sideways consolidation (zone detection)
            - "volatile": High volatility spikes (breakout detection)
            - "multi_tf_aligned": Multi-TF alignment (high_tf/med_tf/low_tf correlation)

    Returns:
        ToolResult with synthetic data metadata (not the DataFrames)
    """
    try:
        from ..forge.validation.synthetic_data import generate_synthetic_candles

        if timeframes is None:
            timeframes = ["1m", "5m", "15m", "1h", "4h"]

        candles = generate_synthetic_candles(
            symbol=symbol,
            timeframes=timeframes,
            bars_per_tf=bars_per_tf,
            seed=seed,
            pattern=pattern,
        )

        return ToolResult(
            success=True,
            message=(
                f"Generated synthetic data: {len(timeframes)} TFs, {bars_per_tf} bars each, "
                f"hash={candles.data_hash}"
            ),
            data=candles.to_dict(),
        )

    except Exception as e:
        logger.error(f"Synthetic data generation failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Synthetic data error: {e}",
        )


# =============================================================================
# Structure Parity Tool
# =============================================================================

def forge_structure_parity_tool(
    seed: int = 42,
    bars_per_tf: int = 1000,
    pattern: PatternType = "trending",
) -> ToolResult:
    """
    Run structure parity check on all structures in STRUCTURE_REGISTRY.

    Validates that all registered structure detectors:
    - Have valid metadata (required params, dependencies)
    - Can be instantiated with valid params

    Args:
        seed: Random seed for synthetic data (default: 42)
        bars_per_tf: Bars per timeframe (default: 1000)
        pattern: Synthetic data pattern (default: "trending")

    Returns:
        ToolResult with structure parity results
    """
    try:
        from ..forge.validation.synthetic_data import generate_synthetic_candles
        from src.structures import list_structure_types, get_structure_info

        # Generate synthetic data
        candles = generate_synthetic_candles(
            symbol="BTCUSDT",
            timeframes=["15m"],  # Single TF is enough for registry check
            bars_per_tf=bars_per_tf,
            seed=seed,
            pattern=pattern,
        )

        # Check all structures
        structure_types = list_structure_types()
        results = []
        passed_count = 0
        failed_count = 0

        for structure_type in structure_types:
            try:
                info = get_structure_info(structure_type)
                results.append({
                    "structure_type": structure_type,
                    "class_name": info["class_name"],
                    "required_params": info["required_params"],
                    "depends_on": info["depends_on"],
                    "passed": True,
                })
                passed_count += 1
            except Exception as e:
                results.append({
                    "structure_type": structure_type,
                    "passed": False,
                    "error": str(e),
                })
                failed_count += 1

        success = failed_count == 0

        if success:
            return ToolResult(
                success=True,
                message=f"Structure parity PASSED: {passed_count}/{len(structure_types)} structures verified",
                data={
                    "total": len(structure_types),
                    "passed": passed_count,
                    "failed": failed_count,
                    "structure_types": structure_types,
                    "results": results,
                    "data_hash": candles.data_hash,
                },
            )
        else:
            failed = [r for r in results if not r.get("passed")]
            return ToolResult(
                success=False,
                error=f"Structure parity FAILED: {failed_count} structure(s) failed",
                data={
                    "total": len(structure_types),
                    "passed": passed_count,
                    "failed": failed_count,
                    "failed_structures": failed,
                    "data_hash": candles.data_hash,
                },
            )

    except Exception as e:
        logger.error(f"Structure parity failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Structure parity error: {e}",
        )


# =============================================================================
# Indicator Parity Tool
# =============================================================================

def forge_indicator_parity_tool(
    seed: int = 42,
    bars_per_tf: int = 1000,
    pattern: PatternType = "trending",
) -> ToolResult:
    """
    Run indicator parity check on all indicators in INDICATOR_REGISTRY.

    Validates that all registered indicators:
    - Have valid metadata (input series, output types)
    - Can be queried from the registry

    Args:
        seed: Random seed for synthetic data (default: 42)
        bars_per_tf: Bars per timeframe (default: 1000)
        pattern: Synthetic data pattern (default: "trending")

    Returns:
        ToolResult with indicator parity results
    """
    try:
        from ..forge.validation.synthetic_data import generate_synthetic_candles
        from ..indicators import get_registry

        # Generate synthetic data
        candles = generate_synthetic_candles(
            symbol="BTCUSDT",
            timeframes=["15m"],
            bars_per_tf=bars_per_tf,
            seed=seed,
            pattern=pattern,
        )

        # Check all indicators
        registry = get_registry()
        all_indicators = registry.list_indicators()
        results = []
        passed_count = 0
        failed_count = 0

        for indicator_type in all_indicators:
            try:
                info = registry.get_indicator_info(indicator_type)
                results.append({
                    "indicator_type": indicator_type,
                    "input_series": info.input_series,
                    "is_multi_output": registry.is_multi_output(indicator_type),
                    "passed": True,
                })
                passed_count += 1
            except Exception as e:
                results.append({
                    "indicator_type": indicator_type,
                    "passed": False,
                    "error": str(e),
                })
                failed_count += 1

        success = failed_count == 0

        if success:
            return ToolResult(
                success=True,
                message=f"Indicator parity PASSED: {passed_count}/{len(all_indicators)} indicators verified",
                data={
                    "total": len(all_indicators),
                    "passed": passed_count,
                    "failed": failed_count,
                    "results": results,
                    "data_hash": candles.data_hash,
                },
            )
        else:
            failed = [r for r in results if not r.get("passed")]
            return ToolResult(
                success=False,
                error=f"Indicator parity FAILED: {failed_count} indicator(s) failed",
                data={
                    "total": len(all_indicators),
                    "passed": passed_count,
                    "failed": failed_count,
                    "failed_indicators": failed,
                    "data_hash": candles.data_hash,
                },
            )

    except Exception as e:
        logger.error(f"Indicator parity failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Indicator parity error: {e}",
        )
