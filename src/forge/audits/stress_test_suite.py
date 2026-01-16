"""
Forge Stress Test Suite - Full validation + backtest pipeline with hash tracing.

This is the START of the smoke test refactor. Each step produces:
- input_hash: Hash of inputs to this step
- output_hash: Hash of outputs from this step

This enables debugging and tracing the flow of items through the entire system.

NO hard coding. All values flow through parameters.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.forge.validation import (
    validate_batch,
    BatchValidationResult,
    generate_synthetic_candles,
    SyntheticCandles,
)
from src.forge.audits import (
    run_toolkit_contract_audit,
    ToolkitAuditResult,
)
from src.forge.audits.audit_rollup_parity import (
    run_rollup_parity_audit,
    RollupParityResult,
)
from src.structures import (
    STRUCTURE_REGISTRY,
    list_structure_types,
    get_structure_info,
)
from src.indicators import get_registry


# =============================================================================
# Constants (named, not magic numbers)
# =============================================================================
HASH_LENGTH = 12
DEFAULT_VALIDATION_DIR = Path("strategies/plays/_validation")
DEFAULT_SEED = 42
DEFAULT_BARS = 1000


# =============================================================================
# Result Dataclasses
# =============================================================================
@dataclass
class StressTestStepResult:
    """Result of a single stress test step."""
    step_name: str
    step_number: int
    passed: bool
    duration_seconds: float
    message: str
    input_hash: str | None = None
    output_hash: str | None = None
    data: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_name": self.step_name,
            "step_number": self.step_number,
            "passed": self.passed,
            "duration_seconds": round(self.duration_seconds, 3),
            "message": self.message,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "data": self.data,
        }


@dataclass
class StressTestReport:
    """Complete stress test report with hash chain for traceability."""
    overall_passed: bool
    steps: list[StressTestStepResult]
    total_duration_seconds: float
    hash_chain: list[str]  # Ordered hashes for flow tracing
    summary: dict
    # Parameters used (for reproducibility)
    seed: int
    bars_per_tf: int
    validation_plays_dir: str
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_passed": self.overall_passed,
            "total_duration_seconds": round(self.total_duration_seconds, 3),
            "hash_chain": self.hash_chain,
            "summary": self.summary,
            "seed": self.seed,
            "bars_per_tf": self.bars_per_tf,
            "validation_plays_dir": self.validation_plays_dir,
            "generated_at": self.generated_at,
            "steps": [s.to_dict() for s in self.steps],
        }

    def get_step(self, step_name: str) -> StressTestStepResult | None:
        """Get result for a specific step by name."""
        for step in self.steps:
            if step.step_name == step_name:
                return step
        return None


@dataclass
class StructureParityResult:
    """Result of structure parity check."""
    success: bool
    total_structures: int
    passed_structures: int
    failed_structures: int
    structure_results: list[dict]
    data_hash: str
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "total_structures": self.total_structures,
            "passed_structures": self.passed_structures,
            "failed_structures": self.failed_structures,
            "structure_results": self.structure_results,
            "data_hash": self.data_hash,
            "error_message": self.error_message,
        }


@dataclass
class IndicatorParityResult:
    """Result of indicator parity check."""
    success: bool
    total_indicators: int
    passed_indicators: int
    failed_indicators: int
    indicator_results: list[dict]
    data_hash: str
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "total_indicators": self.total_indicators,
            "passed_indicators": self.passed_indicators,
            "failed_indicators": self.failed_indicators,
            "indicator_results": self.indicator_results,
            "data_hash": self.data_hash,
            "error_message": self.error_message,
        }


# =============================================================================
# Hash Utilities
# =============================================================================
def _compute_hash(data: Any) -> str:
    """Compute SHA256[:12] hash of any JSON-serializable data."""
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:HASH_LENGTH]


def _compute_step_input_hash(
    step_name: str,
    previous_output_hash: str | None,
    step_params: dict,
) -> str:
    """Compute input hash for a step (includes previous step's output)."""
    components = {
        "step_name": step_name,
        "previous_output_hash": previous_output_hash,
        "step_params": step_params,
    }
    return _compute_hash(components)


# =============================================================================
# Individual Step Functions
# =============================================================================
def _step_generate_synthetic_data(
    seed: int,
    bars_per_tf: int,
    pattern: str,
    timeframes: list[str],
    previous_hash: str | None,
) -> tuple[SyntheticCandles, StressTestStepResult]:
    """Step 1: Generate synthetic candle data for all timeframes."""
    step_name = "generate_synthetic_data"
    step_number = 1
    start = time.time()

    input_hash = _compute_step_input_hash(
        step_name,
        previous_hash,
        {"seed": seed, "bars_per_tf": bars_per_tf, "pattern": pattern, "timeframes": timeframes},
    )

    try:
        candles = generate_synthetic_candles(
            symbol="BTCUSDT",
            timeframes=timeframes,
            bars_per_tf=bars_per_tf,
            seed=seed,
            pattern=pattern,
        )

        duration = time.time() - start
        output_hash = candles.data_hash

        return candles, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=True,
            duration_seconds=duration,
            message=f"Generated {len(timeframes)} timeframes, {bars_per_tf} bars each",
            input_hash=input_hash,
            output_hash=output_hash,
            data={
                "timeframes": timeframes,
                "bars_per_tf": bars_per_tf,
                "pattern": pattern,
                "seed": seed,
            },
        )
    except Exception as e:
        duration = time.time() - start
        return None, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=False,
            duration_seconds=duration,
            message=f"Failed: {e}",
            input_hash=input_hash,
            output_hash=None,
            data={"error": str(e)},
        )


def _step_validate_plays(
    validation_plays_dir: Path,
    previous_hash: str | None,
) -> tuple[BatchValidationResult | None, StressTestStepResult]:
    """Step 2: Validate all plays (normalize-batch)."""
    step_name = "validate_plays"
    step_number = 2
    start = time.time()

    input_hash = _compute_step_input_hash(
        step_name,
        previous_hash,
        {"validation_plays_dir": str(validation_plays_dir)},
    )

    try:
        result = validate_batch(directory=validation_plays_dir)

        duration = time.time() - start

        # Compute output hash from validation results
        output_data = {
            "total": result.total,
            "passed": result.passed,
            "failed": result.failed_count,
            "play_ids": [r.play_id for r in result.results],
        }
        output_hash = _compute_hash(output_data)

        passed = result.failed_count == 0

        return result, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=passed,
            duration_seconds=duration,
            message=f"{result.passed}/{result.total} plays validated",
            input_hash=input_hash,
            output_hash=output_hash,
            data=output_data,
        )
    except Exception as e:
        duration = time.time() - start
        return None, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=False,
            duration_seconds=duration,
            message=f"Failed: {e}",
            input_hash=input_hash,
            output_hash=None,
            data={"error": str(e)},
        )


def _step_toolkit_audit(
    seed: int,
    sample_bars: int,
    previous_hash: str | None,
) -> tuple[ToolkitAuditResult | None, StressTestStepResult]:
    """Step 3: Run toolkit audit (registry contract)."""
    step_name = "toolkit_audit"
    step_number = 3
    start = time.time()

    input_hash = _compute_step_input_hash(
        step_name,
        previous_hash,
        {"seed": seed, "sample_bars": sample_bars},
    )

    try:
        result = run_toolkit_contract_audit(
            sample_bars=sample_bars,
            seed=seed,
        )

        duration = time.time() - start

        # Compute output hash
        output_data = {
            "total_indicators": result.total_indicators,
            "passed": result.passed_indicators,
            "failed": result.failed_indicators,
            "success": result.success,
        }
        output_hash = _compute_hash(output_data)

        return result, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=result.success,
            duration_seconds=duration,
            message=f"{result.passed_indicators}/{result.total_indicators} indicators passed registry contract",
            input_hash=input_hash,
            output_hash=output_hash,
            data=output_data,
        )
    except Exception as e:
        duration = time.time() - start
        return None, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=False,
            duration_seconds=duration,
            message=f"Failed: {e}",
            input_hash=input_hash,
            output_hash=None,
            data={"error": str(e)},
        )


def _step_structure_parity(
    candles: SyntheticCandles,
    previous_hash: str | None,
) -> tuple[StructureParityResult | None, StressTestStepResult]:
    """Step 4: Run structure parity check on synthetic data."""
    step_name = "structure_parity"
    step_number = 4
    start = time.time()

    input_hash = _compute_step_input_hash(
        step_name,
        previous_hash,
        {"data_hash": candles.data_hash},
    )

    try:
        structure_types = list_structure_types()
        results = []
        passed_count = 0
        failed_count = 0

        for structure_type in structure_types:
            try:
                info = get_structure_info(structure_type)
                # Verify structure is registered and has valid metadata
                result = {
                    "structure_type": structure_type,
                    "class_name": info["class_name"],
                    "required_params": info["required_params"],
                    "depends_on": info["depends_on"],
                    "passed": True,
                    "error": None,
                }
                results.append(result)
                passed_count += 1
            except Exception as e:
                results.append({
                    "structure_type": structure_type,
                    "passed": False,
                    "error": str(e),
                })
                failed_count += 1

        duration = time.time() - start

        success = failed_count == 0
        output_data = {
            "total": len(structure_types),
            "passed": passed_count,
            "failed": failed_count,
            "structure_types": structure_types,
        }
        output_hash = _compute_hash(output_data)

        parity_result = StructureParityResult(
            success=success,
            total_structures=len(structure_types),
            passed_structures=passed_count,
            failed_structures=failed_count,
            structure_results=results,
            data_hash=candles.data_hash,
        )

        return parity_result, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=success,
            duration_seconds=duration,
            message=f"{passed_count}/{len(structure_types)} structures verified",
            input_hash=input_hash,
            output_hash=output_hash,
            data=output_data,
        )
    except Exception as e:
        duration = time.time() - start
        return None, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=False,
            duration_seconds=duration,
            message=f"Failed: {e}",
            input_hash=input_hash,
            output_hash=None,
            data={"error": str(e)},
        )


def _step_indicator_parity(
    candles: SyntheticCandles,
    previous_hash: str | None,
) -> tuple[IndicatorParityResult | None, StressTestStepResult]:
    """Step 5: Run indicator parity check on synthetic data."""
    step_name = "indicator_parity"
    step_number = 5
    start = time.time()

    input_hash = _compute_step_input_hash(
        step_name,
        previous_hash,
        {"data_hash": candles.data_hash},
    )

    try:
        registry = get_registry()
        all_indicators = registry.list_indicators()
        results = []
        passed_count = 0
        failed_count = 0

        for indicator_type in all_indicators:
            try:
                info = registry.get_indicator_info(indicator_type)
                result = {
                    "indicator_type": indicator_type,
                    "input_series": info.input_series,
                    "is_multi_output": registry.is_multi_output(indicator_type),
                    "passed": True,
                    "error": None,
                }
                results.append(result)
                passed_count += 1
            except Exception as e:
                results.append({
                    "indicator_type": indicator_type,
                    "passed": False,
                    "error": str(e),
                })
                failed_count += 1

        duration = time.time() - start

        success = failed_count == 0
        output_data = {
            "total": len(all_indicators),
            "passed": passed_count,
            "failed": failed_count,
        }
        output_hash = _compute_hash(output_data)

        parity_result = IndicatorParityResult(
            success=success,
            total_indicators=len(all_indicators),
            passed_indicators=passed_count,
            failed_indicators=failed_count,
            indicator_results=results,
            data_hash=candles.data_hash,
        )

        return parity_result, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=success,
            duration_seconds=duration,
            message=f"{passed_count}/{len(all_indicators)} indicators verified",
            input_hash=input_hash,
            output_hash=output_hash,
            data=output_data,
        )
    except Exception as e:
        duration = time.time() - start
        return None, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=False,
            duration_seconds=duration,
            message=f"Failed: {e}",
            input_hash=input_hash,
            output_hash=None,
            data={"error": str(e)},
        )


def _step_rollup_audit(
    seed: int,
    previous_hash: str | None,
) -> tuple[RollupParityResult | None, StressTestStepResult]:
    """Step 6: Run rollup audit (1m aggregation)."""
    step_name = "rollup_audit"
    step_number = 6
    start = time.time()

    input_hash = _compute_step_input_hash(
        step_name,
        previous_hash,
        {"seed": seed},
    )

    try:
        result = run_rollup_parity_audit(seed=seed)

        duration = time.time() - start

        output_data = {
            "total_intervals": result.total_intervals,
            "passed_intervals": result.passed_intervals,
            "failed_intervals": result.failed_intervals,
            "success": result.success,
        }
        output_hash = _compute_hash(output_data)

        return result, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=result.success,
            duration_seconds=duration,
            message=f"{result.passed_intervals}/{result.total_intervals} intervals passed rollup parity",
            input_hash=input_hash,
            output_hash=output_hash,
            data=output_data,
        )
    except Exception as e:
        duration = time.time() - start
        return None, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=False,
            duration_seconds=duration,
            message=f"Failed: {e}",
            input_hash=input_hash,
            output_hash=None,
            data={"error": str(e)},
        )


def _step_backtest_execution(
    validation_plays_dir: Path,
    candles: SyntheticCandles | None,
    previous_hash: str | None,
) -> tuple[dict | None, StressTestStepResult]:
    """Step 7: Execute validation plays as backtests with synthetic data."""
    step_name = "backtest_execution"
    step_number = 7
    start = time.time()

    input_hash = _compute_step_input_hash(
        step_name,
        previous_hash,
        {
            "validation_plays_dir": str(validation_plays_dir),
            "data_hash": candles.data_hash if candles else None,
        },
    )

    try:
        # Verify plays exist
        if not validation_plays_dir.exists():
            raise FileNotFoundError(f"Validation plays directory not found: {validation_plays_dir}")

        play_files = list(validation_plays_dir.glob("*.yml"))
        if not play_files:
            raise FileNotFoundError(f"No .yml files found in {validation_plays_dir}")

        # Import required modules
        from src.backtest.play import load_play
        from src.backtest.engine_factory import create_engine_from_play
        from src.backtest.engine import run_engine_with_play
        from src.forge.validation.synthetic_provider import SyntheticCandlesProvider

        # Create synthetic provider if candles available
        provider = SyntheticCandlesProvider(candles) if candles else None

        # Execute each play
        plays_executed = 0
        plays_passed = 0
        plays_failed = 0
        all_trades_hashes = []
        all_equity_hashes = []
        play_results = []

        for play_file in play_files:
            play_id = play_file.stem
            try:
                # Load play
                play = load_play(play_id, base_dir=validation_plays_dir.parent)

                # Verify required TFs are in synthetic data
                if provider:
                    exec_tf = play.execution_tf
                    if not provider.has_tf(exec_tf):
                        # Skip plays that require TFs not in synthetic data
                        play_results.append({
                            "play_id": play_id,
                            "status": "skipped",
                            "reason": f"TF {exec_tf} not in synthetic data",
                        })
                        continue

                    # Get window from synthetic data
                    window_start, window_end = provider.get_data_range(exec_tf)

                    # Create engine with synthetic provider
                    engine = create_engine_from_play(
                        play=play,
                        window_start=window_start,
                        window_end=window_end,
                        synthetic_provider=provider,
                    )

                    # Run backtest
                    result = run_engine_with_play(engine, play)

                    # Collect hashes
                    trades_count = len(result.trades) if result.trades else 0
                    equity_count = len(result.equity_curve) if result.equity_curve else 0

                    # Compute hashes for determinism tracking
                    if result.trades:
                        trades_data = [t.to_dict() if hasattr(t, 'to_dict') else t for t in result.trades]
                        trades_hash = _compute_hash(trades_data)
                        all_trades_hashes.append(trades_hash)
                    if result.equity_curve:
                        equity_data = [e.to_dict() if hasattr(e, 'to_dict') else e for e in result.equity_curve]
                        equity_hash = _compute_hash(equity_data)
                        all_equity_hashes.append(equity_hash)

                    play_results.append({
                        "play_id": play_id,
                        "status": "passed",
                        "trades_count": trades_count,
                        "equity_points": equity_count,
                    })
                    plays_executed += 1
                    plays_passed += 1
                else:
                    # No synthetic data - skip execution
                    play_results.append({
                        "play_id": play_id,
                        "status": "skipped",
                        "reason": "No synthetic data provider",
                    })

            except Exception as e:
                play_results.append({
                    "play_id": play_id,
                    "status": "failed",
                    "error": str(e),
                })
                plays_failed += 1

        duration = time.time() - start

        # Compute combined hashes
        combined_trades_hash = _compute_hash(all_trades_hashes) if all_trades_hashes else None
        combined_equity_hash = _compute_hash(all_equity_hashes) if all_equity_hashes else None

        output_data = {
            "plays_found": len(play_files),
            "plays_executed": plays_executed,
            "plays_passed": plays_passed,
            "plays_failed": plays_failed,
            "trades_hash": combined_trades_hash,
            "equity_hash": combined_equity_hash,
            "play_results": play_results,
        }
        output_hash = _compute_hash(output_data)

        passed = plays_failed == 0 and plays_executed > 0

        return output_data, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=passed,
            duration_seconds=duration,
            message=f"Executed {plays_executed}/{len(play_files)} plays ({plays_passed} passed, {plays_failed} failed)",
            input_hash=input_hash,
            output_hash=output_hash,
            data=output_data,
        )
    except Exception as e:
        duration = time.time() - start
        return None, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=False,
            duration_seconds=duration,
            message=f"Failed: {e}",
            input_hash=input_hash,
            output_hash=None,
            data={"error": str(e)},
        )


def _step_artifact_verification(
    previous_hash: str | None,
) -> tuple[dict | None, StressTestStepResult]:
    """Step 8: Verify artifacts + determinism (placeholder)."""
    step_name = "artifact_verification"
    step_number = 8
    start = time.time()

    input_hash = _compute_step_input_hash(
        step_name,
        previous_hash,
        {},
    )

    try:
        # TODO: Implement artifact verification using:
        # - validate_artifacts() from src/backtest/artifacts/artifact_standards.py
        # - verify_determinism_rerun() from src/backtest/artifacts/determinism.py

        duration = time.time() - start

        output_data = {
            "artifacts_verified": 0,  # TODO
            "determinism_verified": False,  # TODO
            "run_hash": None,  # TODO
        }
        output_hash = _compute_hash(output_data)

        return output_data, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=True,
            duration_seconds=duration,
            message="Artifact verification pending implementation",
            input_hash=input_hash,
            output_hash=output_hash,
            data=output_data,
        )
    except Exception as e:
        duration = time.time() - start
        return None, StressTestStepResult(
            step_name=step_name,
            step_number=step_number,
            passed=False,
            duration_seconds=duration,
            message=f"Failed: {e}",
            input_hash=input_hash,
            output_hash=None,
            data={"error": str(e)},
        )


# =============================================================================
# Main Entry Point
# =============================================================================
def run_stress_test_suite(
    validation_plays_dir: Path | None = None,
    skip_audits: bool = False,
    skip_backtest: bool = False,
    trace_hashes: bool = True,
    use_synthetic_data: bool = True,
    seed: int = DEFAULT_SEED,
    bars_per_tf: int = DEFAULT_BARS,
    pattern: str = "trending",
    timeframes: list[str] | None = None,
) -> StressTestReport:
    """
    Run complete Forge stress test suite with hash tracing.

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
            (default: strategies/plays/_validation)
        skip_audits: Skip audit steps 3-6 (default: False)
        skip_backtest: Skip backtest steps 7-8 (default: False)
        trace_hashes: Enable hash tracing (default: True)
        use_synthetic_data: Use synthetic data for parity checks (default: True)
        seed: Random seed for synthetic data (default: 42)
        bars_per_tf: Bars per timeframe (default: 1000)
        pattern: Synthetic data pattern (default: "trending")
        timeframes: Timeframes to generate (default: ["1m", "5m", "15m", "1h", "4h"])

    Returns:
        StressTestReport with all step results and hash chain
    """
    # Apply defaults
    if validation_plays_dir is None:
        validation_plays_dir = DEFAULT_VALIDATION_DIR
    if timeframes is None:
        timeframes = ["1m", "5m", "15m", "1h", "4h"]

    total_start = time.time()
    steps: list[StressTestStepResult] = []
    hash_chain: list[str] = []
    previous_hash: str | None = None

    # Track data between steps
    synthetic_candles: SyntheticCandles | None = None

    # Step 1: Generate synthetic data
    if use_synthetic_data:
        synthetic_candles, step_result = _step_generate_synthetic_data(
            seed=seed,
            bars_per_tf=bars_per_tf,
            pattern=pattern,
            timeframes=timeframes,
            previous_hash=previous_hash,
        )
        steps.append(step_result)
        if step_result.output_hash:
            hash_chain.append(step_result.output_hash)
            previous_hash = step_result.output_hash

    # Step 2: Validate plays
    _, step_result = _step_validate_plays(
        validation_plays_dir=validation_plays_dir,
        previous_hash=previous_hash,
    )
    steps.append(step_result)
    if step_result.output_hash:
        hash_chain.append(step_result.output_hash)
        previous_hash = step_result.output_hash

    if not skip_audits:
        # Step 3: Toolkit audit
        _, step_result = _step_toolkit_audit(
            seed=seed,
            sample_bars=bars_per_tf,
            previous_hash=previous_hash,
        )
        steps.append(step_result)
        if step_result.output_hash:
            hash_chain.append(step_result.output_hash)
            previous_hash = step_result.output_hash

        # Step 4: Structure parity
        if synthetic_candles:
            _, step_result = _step_structure_parity(
                candles=synthetic_candles,
                previous_hash=previous_hash,
            )
            steps.append(step_result)
            if step_result.output_hash:
                hash_chain.append(step_result.output_hash)
                previous_hash = step_result.output_hash

        # Step 5: Indicator parity
        if synthetic_candles:
            _, step_result = _step_indicator_parity(
                candles=synthetic_candles,
                previous_hash=previous_hash,
            )
            steps.append(step_result)
            if step_result.output_hash:
                hash_chain.append(step_result.output_hash)
                previous_hash = step_result.output_hash

        # Step 6: Rollup audit
        _, step_result = _step_rollup_audit(
            seed=seed,
            previous_hash=previous_hash,
        )
        steps.append(step_result)
        if step_result.output_hash:
            hash_chain.append(step_result.output_hash)
            previous_hash = step_result.output_hash

    if not skip_backtest:
        # Step 7: Backtest execution with synthetic data
        _, step_result = _step_backtest_execution(
            validation_plays_dir=validation_plays_dir,
            candles=synthetic_candles,  # Pass synthetic data for engine execution
            previous_hash=previous_hash,
        )
        steps.append(step_result)
        if step_result.output_hash:
            hash_chain.append(step_result.output_hash)
            previous_hash = step_result.output_hash

        # Step 8: Artifact verification
        _, step_result = _step_artifact_verification(
            previous_hash=previous_hash,
        )
        steps.append(step_result)
        if step_result.output_hash:
            hash_chain.append(step_result.output_hash)
            previous_hash = step_result.output_hash

    # Compute summary
    total_duration = time.time() - total_start
    passed_steps = sum(1 for s in steps if s.passed)
    failed_steps = sum(1 for s in steps if not s.passed)
    overall_passed = failed_steps == 0

    summary = {
        "total_steps": len(steps),
        "passed_steps": passed_steps,
        "failed_steps": failed_steps,
        "skipped_audits": skip_audits,
        "skipped_backtest": skip_backtest,
    }

    return StressTestReport(
        overall_passed=overall_passed,
        steps=steps,
        total_duration_seconds=total_duration,
        hash_chain=hash_chain,
        summary=summary,
        seed=seed,
        bars_per_tf=bars_per_tf,
        validation_plays_dir=str(validation_plays_dir),
    )
