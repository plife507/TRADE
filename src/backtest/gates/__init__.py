"""
Backtest gates for production enforcement.

Gates are read-only validators that scan and report violations.
They do NOT auto-edit files.

Gate D.1: Pipeline signature verification
Gate D.2: Batch verification with generated Plays (blocks DSL v3.0.0)
"""

from .production_first_import_gate import (
    run_production_first_gate,
    GateViolation,
    GateResult,
)

from .play_generator import (
    GeneratorConfig,
    GeneratedPlay,
    generate_plays,
    cleanup_generated_plays,
    get_available_symbols,
)

from .batch_verification import (
    PlayRunResult,
    BatchSummary,
    run_batch_verification,
    BATCH_SUMMARY_FILE,
)

__all__ = [
    # Gate A
    "run_production_first_gate",
    "GateViolation",
    "GateResult",
    # Gate D.2 - Play generation and batch verification
    "GeneratorConfig",
    "GeneratedPlay",
    "generate_plays",
    "cleanup_generated_plays",
    "get_available_symbols",
    "PlayRunResult",
    "BatchSummary",
    "run_batch_verification",
    "BATCH_SUMMARY_FILE",
]

