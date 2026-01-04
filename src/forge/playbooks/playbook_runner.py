"""
Playbook Runner - Execute all plays in a playbook with multiple modes.

Modes:
- verify-math: Run audits only (default) - validates config + registry
- sequential: Run backtests one-by-one - produces run_hash per play
- compare: Compare metrics side-by-side - shows hash diffs
- aggregate: Aggregate into system metrics - composite hash

Architecture Principle: Pure Math
- Input: playbook_id + mode + params
- Output: PlaybookRunResult with hashes
- No side effects beyond generated artifacts

NO hard coding. All values flow through parameters.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from src.forge.playbooks.playbook import (
    Playbook,
    PlaybookEntry,
    load_playbook,
    PlaybookNotFoundError,
    DEFAULT_PLAYBOOKS_DIR,
)
from src.forge.validation import validate_play_file, PlayValidationResult


# =============================================================================
# Constants
# =============================================================================
HASH_LENGTH = 12
DEFAULT_PLAYS_DIR = Path("configs/plays")

RunMode = Literal["verify-math", "sequential", "compare", "aggregate"]


# =============================================================================
# Result Dataclasses
# =============================================================================
@dataclass
class PlayRunResult:
    """Result of running a single play."""
    play_id: str
    success: bool
    mode: str
    run_hash: str | None = None       # Hash for this play's run
    trades_hash: str | None = None    # Hash of trades produced
    validation_hash: str | None = None  # Hash of validation result
    metrics: dict | None = None
    duration_seconds: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "play_id": self.play_id,
            "success": self.success,
            "mode": self.mode,
            "run_hash": self.run_hash,
            "trades_hash": self.trades_hash,
            "validation_hash": self.validation_hash,
            "metrics": self.metrics,
            "duration_seconds": round(self.duration_seconds, 3),
            "error": self.error,
        }


@dataclass
class PlaybookRunResult:
    """Result of running all plays in a playbook."""
    playbook_id: str
    mode: str
    overall_success: bool
    plays_run: list[PlayRunResult] = field(default_factory=list)
    hash_summary: dict[str, str] = field(default_factory=dict)  # play_id → run_hash
    aggregate_metrics: dict | None = None
    total_duration_seconds: float = 0.0
    error: str | None = None
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "playbook_id": self.playbook_id,
            "mode": self.mode,
            "overall_success": self.overall_success,
            "plays_run": [p.to_dict() for p in self.plays_run],
            "hash_summary": self.hash_summary,
            "aggregate_metrics": self.aggregate_metrics,
            "total_duration_seconds": round(self.total_duration_seconds, 3),
            "error": self.error,
            "generated_at": self.generated_at,
        }

    @property
    def passed_count(self) -> int:
        return sum(1 for p in self.plays_run if p.success)

    @property
    def failed_count(self) -> int:
        return sum(1 for p in self.plays_run if not p.success)


# =============================================================================
# Hash Utilities
# =============================================================================
def _compute_hash(data: Any) -> str:
    """Compute SHA256[:12] hash of any JSON-serializable data."""
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:HASH_LENGTH]


def _compute_validation_hash(result: PlayValidationResult) -> str:
    """Compute hash of validation result."""
    data = {
        "play_id": result.play_id,
        "is_valid": result.is_valid,
        "error_count": len(result.errors),
        "warning_count": len(result.warnings),
    }
    return _compute_hash(data)


# =============================================================================
# Helper Functions
# =============================================================================
def _find_play_file(play_id: str, plays_dir: Path) -> Path | None:
    """
    Find a play file by ID, searching subdirectories.

    Searches:
    1. plays_dir/{play_id}.yml
    2. plays_dir/*/{play_id}.yml (one level of subdirs)
    """
    # Direct path
    direct = plays_dir / f"{play_id}.yml"
    if direct.exists():
        return direct

    # Search subdirectories
    for subdir in plays_dir.iterdir():
        if subdir.is_dir():
            subpath = subdir / f"{play_id}.yml"
            if subpath.exists():
                return subpath

    return None


# =============================================================================
# Mode Implementations
# =============================================================================
def _run_verify_math(
    playbook: Playbook,
    plays_dir: Path,
) -> list[PlayRunResult]:
    """
    verify-math mode: Validate plays without running backtests.

    This is the default mode - fast validation of configs and registry.
    """
    results = []

    for entry in playbook.get_enabled_plays():
        start = time.time()
        play_path = _find_play_file(entry.play_id, plays_dir)

        try:
            if play_path is None:
                results.append(PlayRunResult(
                    play_id=entry.play_id,
                    success=False,
                    mode="verify-math",
                    duration_seconds=time.time() - start,
                    error=f"Play file not found: {entry.play_id}.yml in {plays_dir}",
                ))
                continue

            # Validate the play
            validation = validate_play_file(play_path)
            duration = time.time() - start
            validation_hash = _compute_validation_hash(validation)

            results.append(PlayRunResult(
                play_id=entry.play_id,
                success=validation.is_valid,
                mode="verify-math",
                validation_hash=validation_hash,
                duration_seconds=duration,
                error=validation.format_errors() if not validation.is_valid else None,
            ))

        except Exception as e:
            results.append(PlayRunResult(
                play_id=entry.play_id,
                success=False,
                mode="verify-math",
                duration_seconds=time.time() - start,
                error=str(e),
            ))

    return results


def _run_sequential(
    playbook: Playbook,
    plays_dir: Path,
    symbol: str | None,
    start: datetime | None,
    end: datetime | None,
) -> list[PlayRunResult]:
    """
    sequential mode: Run backtests one-by-one.

    Each play runs in sequence, producing trades_hash and run_hash.
    """
    results = []

    for entry in playbook.get_enabled_plays():
        start_time = time.time()
        play_path = _find_play_file(entry.play_id, plays_dir)

        try:
            if play_path is None:
                results.append(PlayRunResult(
                    play_id=entry.play_id,
                    success=False,
                    mode="sequential",
                    duration_seconds=time.time() - start_time,
                    error=f"Play file not found: {entry.play_id}.yml in {plays_dir}",
                ))
                continue

            # TODO: Implement actual backtest execution
            # For now, validate and mark as pending
            validation = validate_play_file(play_path)
            duration = time.time() - start_time
            validation_hash = _compute_validation_hash(validation)

            if not validation.is_valid:
                results.append(PlayRunResult(
                    play_id=entry.play_id,
                    success=False,
                    mode="sequential",
                    validation_hash=validation_hash,
                    duration_seconds=duration,
                    error=f"Validation failed: {validation.format_errors()}",
                ))
                continue

            # Backtest execution placeholder
            # When implemented, will call backtest_run_play_tool
            results.append(PlayRunResult(
                play_id=entry.play_id,
                success=True,
                mode="sequential",
                validation_hash=validation_hash,
                run_hash=None,  # TODO: Will be set after backtest
                trades_hash=None,  # TODO: Will be set after backtest
                duration_seconds=duration,
                metrics=None,  # TODO: Will be set after backtest
            ))

        except Exception as e:
            results.append(PlayRunResult(
                play_id=entry.play_id,
                success=False,
                mode="sequential",
                duration_seconds=time.time() - start_time,
                error=str(e),
            ))

    return results


def _run_compare(
    playbook: Playbook,
    plays_dir: Path,
    symbol: str | None,
    start: datetime | None,
    end: datetime | None,
) -> list[PlayRunResult]:
    """
    compare mode: Run all plays and compare metrics side-by-side.

    Shows hash diffs between plays.
    """
    # First run sequential to get all results
    results = _run_sequential(playbook, plays_dir, symbol, start, end)

    # TODO: Add comparison logic when backtests are implemented
    # Will compare metrics across all plays

    return results


def _run_aggregate(
    playbook: Playbook,
    plays_dir: Path,
    symbol: str | None,
    start: datetime | None,
    end: datetime | None,
) -> tuple[list[PlayRunResult], dict]:
    """
    aggregate mode: Run all plays and aggregate into system metrics.

    Produces a composite hash of all play results.
    """
    # First run sequential to get all results
    results = _run_sequential(playbook, plays_dir, symbol, start, end)

    # Compute aggregate metrics
    passed = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    # TODO: Add proper metrics aggregation when backtests are implemented
    aggregate_metrics = {
        "total_plays": len(results),
        "passed_plays": passed,
        "failed_plays": failed,
        "composite_hash": _compute_hash({
            "playbook_id": playbook.id,
            "play_hashes": [r.run_hash for r in results if r.run_hash],
        }),
    }

    return results, aggregate_metrics


# =============================================================================
# Main Entry Point
# =============================================================================
def run_playbook(
    playbook_id: str,
    mode: RunMode = "verify-math",
    symbol: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    playbooks_dir: Path | str | None = None,
    plays_dir: Path | str | None = None,
    trace_hashes: bool = True,
) -> PlaybookRunResult:
    """
    Run all plays in a playbook with the specified mode.

    Modes:
    - verify-math: Run audits only (default) - validates config + registry
    - sequential: Run backtests one-by-one - produces run_hash per play
    - compare: Compare metrics side-by-side - shows hash diffs
    - aggregate: Aggregate into system metrics - composite hash

    Args:
        playbook_id: ID of the playbook to run
        mode: Execution mode (default: "verify-math")
        symbol: Symbol override for all plays (optional)
        start: Start datetime for backtests (optional)
        end: End datetime for backtests (optional)
        playbooks_dir: Directory containing playbook configs
        plays_dir: Directory containing play configs
        trace_hashes: Enable hash tracing (default: True)

    Returns:
        PlaybookRunResult with all play results and hash summary
    """
    total_start = time.time()

    # Apply defaults
    if playbooks_dir is None:
        playbooks_dir = DEFAULT_PLAYBOOKS_DIR
    else:
        playbooks_dir = Path(playbooks_dir)

    if plays_dir is None:
        plays_dir = DEFAULT_PLAYS_DIR
    else:
        plays_dir = Path(plays_dir)

    # Load the playbook
    try:
        playbook = load_playbook(playbook_id, playbooks_dir)
    except PlaybookNotFoundError as e:
        return PlaybookRunResult(
            playbook_id=playbook_id,
            mode=mode,
            overall_success=False,
            total_duration_seconds=time.time() - total_start,
            error=str(e),
        )
    except Exception as e:
        return PlaybookRunResult(
            playbook_id=playbook_id,
            mode=mode,
            overall_success=False,
            total_duration_seconds=time.time() - total_start,
            error=f"Failed to load playbook: {e}",
        )

    # Run based on mode
    aggregate_metrics = None

    if mode == "verify-math":
        results = _run_verify_math(playbook, plays_dir)
    elif mode == "sequential":
        results = _run_sequential(playbook, plays_dir, symbol, start, end)
    elif mode == "compare":
        results = _run_compare(playbook, plays_dir, symbol, start, end)
    elif mode == "aggregate":
        results, aggregate_metrics = _run_aggregate(playbook, plays_dir, symbol, start, end)
    else:
        return PlaybookRunResult(
            playbook_id=playbook_id,
            mode=mode,
            overall_success=False,
            total_duration_seconds=time.time() - total_start,
            error=f"Unknown mode: {mode}. Valid: verify-math, sequential, compare, aggregate",
        )

    # Build hash summary
    hash_summary = {}
    if trace_hashes:
        for r in results:
            if r.run_hash:
                hash_summary[r.play_id] = r.run_hash
            elif r.validation_hash:
                hash_summary[r.play_id] = r.validation_hash

    # Determine overall success
    overall_success = all(r.success for r in results)

    return PlaybookRunResult(
        playbook_id=playbook_id,
        mode=mode,
        overall_success=overall_success,
        plays_run=results,
        hash_summary=hash_summary,
        aggregate_metrics=aggregate_metrics,
        total_duration_seconds=time.time() - total_start,
    )
