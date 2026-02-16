"""
Core trading logic modules.

Exchange interface, position management, risk controls, and safety features.
Provides unified trading interface with support for all order types.
"""

from .application import Application, get_application
from .exchange_manager import (
    ExchangeManager,
    Position,
    Order,
    OrderResult,
    TimeInForce,
    TriggerBy,
    TriggerDirection,
)
from .position_manager import PositionManager, PortfolioSnapshot, TradeRecord
from .risk_manager import RiskManager, Signal, RiskCheckResult
from .order_executor import OrderExecutor, ExecutionResult
from .safety import (
    panic_close_all,
    is_panic_triggered,
    check_panic_and_halt,
    get_panic_state,
    SafetyChecks,
)

__all__ = [
    # Application Lifecycle
    "Application",
    "get_application",
    # Exchange Manager
    "ExchangeManager",
    "Position",
    "Order",
    "OrderResult",
    "TimeInForce",
    "TriggerBy",
    "TriggerDirection",
    # Position Manager
    "PositionManager",
    "PortfolioSnapshot",
    "TradeRecord",
    # Risk Manager
    "RiskManager",
    "Signal",
    "RiskCheckResult",
    # Order Executor
    "OrderExecutor",
    "ExecutionResult",
    # Safety
    "panic_close_all",
    "is_panic_triggered",
    "check_panic_and_halt",
    "get_panic_state",
    "SafetyChecks",
]
