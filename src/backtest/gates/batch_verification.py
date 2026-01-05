"""
Batch Verification - Runs multiple generated Plays and produces batch_summary.json.

Gate D.2 requirement: Generate and run randomized Plays, verify all pass.

All Plays use blocks DSL v3.0.0 format.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import json

from .play_generator import (
    GeneratorConfig,
    GeneratedPlay,
    generate_plays,
    cleanup_generated_plays,
)


@dataclass
class PlayRunResult:
    """Result of running a single Play."""
    play_id: str
    symbol: str
    direction: str
    exec_tf: str
    success: bool
    error_message: str | None = None
    artifact_path: str | None = None
    preflight_passed: bool = False
    evaluation_executed: bool = False
    artifacts_exist: bool = False
    deterministic_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BatchSummary:
    """Summary of batch verification run."""
    seed: int
    num_plays: int
    all_passed: bool
    play_ids: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    directions: list[str] = field(default_factory=list)
    artifact_paths: list[str] = field(default_factory=list)
    results: list[PlayRunResult] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["results"] = [r.to_dict() if hasattr(r, "to_dict") else r for r in self.results]
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str, sort_keys=True)

    def write_json(self, path: Path) -> None:
        with open(path, "w", newline="\n") as f:
            f.write(self.to_json())


def run_batch_verification(
    seed: int = 42,
    num_plays: int = 5,
    window_days: int = 5,
    output_dir: Path = Path("backtests/batch_verification"),
    env: str = "live",
    cleanup_after: bool = False,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> BatchSummary:
    """
    Run batch verification of generated Plays.

    Args:
        seed: Random seed for determinism
        num_plays: Number of Plays to generate and test
        window_days: Backtest window length in days
        output_dir: Output directory for batch artifacts
        env: Data environment ("live" or "demo")
        cleanup_after: Whether to cleanup generated plays after
        window_start: Explicit start date (optional)
        window_end: Explicit end date (optional)

    Returns:
        BatchSummary with results for all plays
    """
    from ..runner import run_backtest_with_gates, RunnerConfig
    from ..play import load_play
    from ...data.historical_data_store import get_historical_store

    # Generate Plays
    gen_config = GeneratorConfig(seed=seed, num_plays=num_plays)
    generated_plays = generate_plays(gen_config)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Setup data loader
    store = get_historical_store(env=env)

    def data_loader(symbol: str, tf: str, start: datetime, end: datetime):
        return store.get_ohlcv(symbol=symbol, tf=tf, start=start, end=end)

    # Compute window
    if window_end is None:
        window_end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if window_start is None:
        window_start = window_end - timedelta(days=window_days)

    results: list[PlayRunResult] = []

    for play in generated_plays:
        print(f"\n{'=' * 60}")
        print(f"Running: {play.id}")
        print(f"  Symbol: {play.symbol}, Direction: {play.direction}")
        print(f"{'=' * 60}")

        try:
            loaded_play = load_play(play.id, base_dir=gen_config.output_dir)

            config = RunnerConfig(
                play=loaded_play,
                window_start=window_start,
                window_end=window_end,
                data_loader=data_loader,
                base_output_dir=output_dir,
            )

            run_result = run_backtest_with_gates(config)

            play_result = PlayRunResult(
                play_id=play.id,
                symbol=play.symbol,
                direction=play.direction,
                exec_tf=play.exec_tf,
                success=run_result.success,
                error_message=run_result.error_message,
                artifact_path=str(run_result.artifact_path) if run_result.artifact_path else None,
                preflight_passed=(
                    run_result.preflight_report is not None
                    and run_result.preflight_report.overall_status.value == "passed"
                ),
                evaluation_executed=True,
                artifacts_exist=(
                    run_result.artifact_path is not None
                    and run_result.artifact_path.exists()
                ),
            )

            if run_result.summary:
                play_result.deterministic_hash = getattr(run_result.summary, "run_hash", None)

            results.append(play_result)

        except Exception as e:
            results.append(PlayRunResult(
                play_id=play.id,
                symbol=play.symbol,
                direction=play.direction,
                exec_tf=play.exec_tf,
                success=False,
                error_message=str(e),
            ))

    all_passed = all(r.success for r in results)

    summary = BatchSummary(
        seed=seed,
        num_plays=num_plays,
        all_passed=all_passed,
        play_ids=[r.play_id for r in results],
        symbols=[r.symbol for r in results],
        directions=[r.direction for r in results],
        artifact_paths=[r.artifact_path for r in results if r.artifact_path],
        results=results,
    )

    summary_path = output_dir / BATCH_SUMMARY_FILE
    summary.write_json(summary_path)

    print(f"\n{'=' * 60}")
    print("BATCH VERIFICATION COMPLETE")
    print(f"{'=' * 60}")
    print(f"  Plays run: {num_plays}")
    print(f"  All passed: {all_passed}")
    print(f"  Summary: {summary_path}")
    print(f"{'=' * 60}")

    if cleanup_after:
        cleanup_generated_plays(gen_config.output_dir)

    return summary


BATCH_SUMMARY_FILE = "batch_summary.json"
