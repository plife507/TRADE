"""Dashboard tab builders."""

from src.cli.dashboard.tabs.indicators import build_indicators_text
from src.cli.dashboard.tabs.log import build_log_text
from src.cli.dashboard.tabs.orders import build_orders_text
from src.cli.dashboard.tabs.overview import build_overview_text
from src.cli.dashboard.tabs.play_yaml import build_play_text
from src.cli.dashboard.tabs.structures import build_structures_text

__all__ = [
    "build_indicators_text",
    "build_log_text",
    "build_orders_text",
    "build_overview_text",
    "build_play_text",
    "build_structures_text",
]
