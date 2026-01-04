"""
Backtest gates for production enforcement.

Gates are read-only validators that scan and report violations.
They do NOT auto-edit files.

Gate D.1: Pipeline signature verification
Gate D.2: DISABLED - Needs blocks DSL generator (play_generator.py deleted)

STATUS (2026-01-04):
- play_generator.py DELETED (generated legacy signal_rules format)
- batch_verification.py DISABLED (depends on deleted generator)
- Gate D.2 will be re-enabled when blocks DSL generator is built
"""

from .production_first_import_gate import (
    run_production_first_gate,
    GateViolation,
    GateResult,
)

# REMOVED: play_generator.py - Generated legacy signal_rules format
# TODO: Build new generator that produces blocks DSL v3.0.0 format

# DISABLED: batch_verification.py - Depends on deleted play_generator
# TODO: Re-enable when blocks DSL generator is built

__all__ = [
    # Gate A
    "run_production_first_gate",
    "GateViolation",
    "GateResult",
    # Gate D.2 - DISABLED until blocks DSL generator built
]

