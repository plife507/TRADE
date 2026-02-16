"""
Smoke tests sub-package for CLI.

Kept modules:
- data: Data builder smoke tests (used by interactive data menu)
- orders: Order/position smoke tests (helpers for EX4 gate)
- sim_orders: Simulator order type tests (used by G7 gate)
"""

from .data import (
    run_data_builder_smoke,
    run_extensive_data_smoke,
)

from .orders import (
    run_comprehensive_order_smoke,
    run_live_check_smoke,
)

from .sim_orders import (
    run_sim_orders_smoke,
)

__all__ = [
    # Data tests
    "run_data_builder_smoke",
    "run_extensive_data_smoke",
    # Order tests
    "run_comprehensive_order_smoke",
    "run_live_check_smoke",
    # Simulator order tests
    "run_sim_orders_smoke",
]
