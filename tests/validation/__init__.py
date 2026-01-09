"""
TRADE Validation Framework - Tiered Testing for DSL/Math/Structure.

Tiers:
- Tier 0: Syntax & Parse (<5 sec)
- Tier 1: Operator Unit Tests (<30 sec)
- Tier 2: Structure Math Tests (<1 min)
- Tier 3: Integration Tests (<2 min)
- Tier 4: Strategy Smoke Tests (<5 min)

Usage:
    python trade_cli.py --validate tier0
    python trade_cli.py --validate all
    python trade_cli.py --validate all --json
"""

from .runner import run_tier, run_all_tiers, ValidationResult

__all__ = ["run_tier", "run_all_tiers", "ValidationResult"]
