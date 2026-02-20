"""Live dashboard package for play runner.

Rich Live full-screen display with tabbed views for monitoring live/demo trading.

Keybindings:
    1-6     Switch tab (Overview / Indicators / Structures / Log / Play / Orders)
    p       Toggle pause (new entries stopped, positions maintained)
    q       Quit
    m       Cycle meta display on overview tab
"""

from src.cli.dashboard.log_handler import DashboardLogHandler
from src.cli.dashboard.order_tracker import OrderEvent, OrderTracker
from src.cli.dashboard.play_meta import populate_play_meta
from src.cli.dashboard.runner import run_dashboard
from src.cli.dashboard.state import DashboardState

__all__ = [
    "DashboardLogHandler",
    "DashboardState",
    "OrderEvent",
    "OrderTracker",
    "populate_play_meta",
    "run_dashboard",
]
