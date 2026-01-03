"""
Tool specifications organized by category.

Each spec module exports a SPECS list and get_imports() function.
"""

from .shared_params import TRADING_ENV_PARAM, DATA_ENV_PARAM, SYMBOL_PARAM
from .orders_specs import SPECS as ORDERS_SPECS, get_imports as get_orders_imports
from .positions_specs import SPECS as POSITIONS_SPECS, get_imports as get_positions_imports
from .account_specs import SPECS as ACCOUNT_SPECS, get_imports as get_account_imports
from .market_specs import SPECS as MARKET_SPECS, get_imports as get_market_imports
from .data_specs import SPECS as DATA_SPECS, get_imports as get_data_imports
from .system_specs import SPECS as SYSTEM_SPECS, get_imports as get_system_imports
from .backtest_specs import SPECS as BACKTEST_SPECS, get_imports as get_backtest_imports

ALL_SPECS = (
    ORDERS_SPECS +
    POSITIONS_SPECS +
    ACCOUNT_SPECS +
    MARKET_SPECS +
    DATA_SPECS +
    SYSTEM_SPECS +
    BACKTEST_SPECS
)

ALL_IMPORTS = {
    "orders": get_orders_imports,
    "positions": get_positions_imports,
    "account": get_account_imports,
    "market": get_market_imports,
    "data": get_data_imports,
    "system": get_system_imports,
    "backtest": get_backtest_imports,
}

__all__ = [
    "TRADING_ENV_PARAM",
    "DATA_ENV_PARAM",
    "SYMBOL_PARAM",
    "ALL_SPECS",
    "ALL_IMPORTS",
    "ORDERS_SPECS",
    "POSITIONS_SPECS",
    "ACCOUNT_SPECS",
    "MARKET_SPECS",
    "DATA_SPECS",
    "SYSTEM_SPECS",
    "BACKTEST_SPECS",
]
