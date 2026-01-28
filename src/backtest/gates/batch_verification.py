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


# G1.10: run_batch_verification() removed (2026-01-27) - unused

BATCH_SUMMARY_FILE = "batch_summary.json"
