"""
Simulated Exchange for Backtesting.

Modular, Bybit-aligned, isolated-margin, USDT linear perpetual simulation.

Public API:
- SimulatedExchange: Main exchange orchestrator
- Bar, Order, Position, Fill: Core types
- adapt_ohlcv_row, adapt_funding_rows: Data adapters

This module provides deterministic trade execution:
- Decisions made at bar close, fills at next bar open
- TP/SL evaluated using intrabar path with deterministic tie-break
- Fees and slippage applied from config

Architecture:
- exchange.py: Thin orchestrator (~200 LOC)
- types.py: All shared types (~300 LOC)
- ledger.py: USDT accounting with invariants
- pricing/: Mark/last/mid price derivation
- execution/: Order execution with slippage/impact
- constraints/: Tick/lot/min_notional validation
- funding/: Funding rate application
- liquidation/: Mark-based liquidation
- metrics/: Exchange-side metrics
- adapters/: Data conversion helpers
"""

from .types import (
    # Enums
    OrderType,
    OrderSide,
    OrderStatus,
    FillReason,
    StopReason,
    TimeInForce,
    TriggerDirection,
    # Core types
    Bar,
    Order,
    OrderId,
    OrderBook,
    Fill,
    Position,
    FundingEvent,
    LiquidationEvent,
    PriceSnapshot,
    # Results
    FillResult,
    FundingResult,
    LiquidationResult,
    LedgerState,
    LedgerUpdate,
    StepResult,
    SimulatorExchangeState,
    # Config
    ExecutionConfig,
)
from .exchange import SimulatedExchange
from .adapters import adapt_ohlcv_row, adapt_funding_rows

__all__ = [
    # Main class
    "SimulatedExchange",
    # Enums
    "OrderType",
    "OrderSide",
    "OrderStatus",
    "FillReason",
    "StopReason",
    "TimeInForce",
    "TriggerDirection",
    # Core types
    "Bar",
    "Order",
    "OrderId",
    "OrderBook",
    "Fill",
    "Position",
    "FundingEvent",
    "LiquidationEvent",
    "PriceSnapshot",
    # Results
    "FillResult",
    "FundingResult",
    "LiquidationResult",
    "LedgerState",
    "LedgerUpdate",
    "StepResult",
    "SimulatorExchangeState",
    # Config
    "ExecutionConfig",
    # Adapters
    "adapt_ohlcv_row",
    "adapt_funding_rows",
]

