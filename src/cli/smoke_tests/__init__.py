"""
Smoke tests sub-package for CLI.

This package contains modular smoke test implementations:
- core: Entry points (run_smoke_suite, run_full_cli_smoke)
- data: Data builder smoke tests
- orders: Order/position smoke tests
- backtest: Backtest engine smoke tests
- metadata: Indicator metadata smoke tests
- prices: Mark price smoke tests
"""

from .core import (
    run_smoke_suite,
    run_full_cli_smoke,
)

from .data import (
    run_data_builder_smoke,
    run_extensive_data_smoke,
)

from .orders import (
    run_comprehensive_order_smoke,
    run_live_check_smoke,
)

from .backtest import (
    run_backtest_smoke,
    run_backtest_smoke_mixed_idea_cards,
    run_phase6_backtest_smoke,
    run_backtest_smoke_suite,
)

from .metadata import (
    run_metadata_smoke,
)

from .prices import (
    run_mark_price_smoke,
)

from .structure import (
    run_structure_smoke,
)

from .rules import (
    run_rules_smoke,
)

__all__ = [
    # Core entry points
    "run_smoke_suite",
    "run_full_cli_smoke",
    # Data tests
    "run_data_builder_smoke",
    "run_extensive_data_smoke",
    # Order tests
    "run_comprehensive_order_smoke",
    "run_live_check_smoke",
    # Backtest tests
    "run_backtest_smoke",
    "run_backtest_smoke_mixed_idea_cards",
    "run_phase6_backtest_smoke",
    "run_backtest_smoke_suite",
    # Metadata tests
    "run_metadata_smoke",
    # Price tests
    "run_mark_price_smoke",
    # Structure tests
    "run_structure_smoke",
    # Rule evaluation tests
    "run_rules_smoke",
]
