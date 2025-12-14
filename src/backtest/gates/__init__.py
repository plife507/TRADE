"""
Backtest gates for production enforcement.

Gates are read-only validators that scan and report violations.
They do NOT auto-edit files.

Gate D.1: Pipeline signature verification
Gate D.2: Batch verification with generated IdeaCards
"""

from .production_first_import_gate import (
    run_production_first_gate,
    GateViolation,
    GateResult,
)

from .idea_card_generator import (
    GeneratorConfig,
    GeneratedIdeaCard,
    generate_idea_cards,
    cleanup_generated_cards,
    get_available_symbols,
)

from .batch_verification import (
    CardRunResult,
    BatchSummary,
    run_batch_verification,
    BATCH_SUMMARY_FILE,
)

__all__ = [
    # Gate A
    "run_production_first_gate",
    "GateViolation",
    "GateResult",
    # Gate D.2
    "GeneratorConfig",
    "GeneratedIdeaCard",
    "generate_idea_cards",
    "cleanup_generated_cards",
    "get_available_symbols",
    "CardRunResult",
    "BatchSummary",
    "run_batch_verification",
    "BATCH_SUMMARY_FILE",
]

