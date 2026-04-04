"""
Smoke tests sub-package for CLI.

Modules:
- sim_orders: Simulator order type tests (used by G7 gate)
- exchange_orders: Live exchange order lifecycle tests (used by EX4 gate)
"""

from .sim_orders import (
    run_sim_orders_smoke,
)

from .exchange_orders import (
    run_order_lifecycle_smoke,
)

__all__ = [
    "run_sim_orders_smoke",
    "run_order_lifecycle_smoke",
]
