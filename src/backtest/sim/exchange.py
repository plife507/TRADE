"""
Simulated Exchange orchestrator.

Thin orchestrator that routes to modular components via tool-calling pattern.
Target: ~200 LOC (max 250 LOC).

Execution model:
1. Strategy evaluates at bar close (ts_close)
2. Entry orders fill at next bar open (ts_open, with slippage)
3. TP/SL checked against bar OHLC with deterministic tie-break
4. Exit orders fill at trigger price (with slippage)

Tool-calling pipeline (in process_bar):
1. pricing: get_prices(bar) -> PriceSnapshot
2. funding: apply_events(events, prev_ts, ts) -> FundingResult
3. execution: fill_orders(orders, bar) -> FillResult
4. ledger: update(fills, funding, prices) -> LedgerUpdate
5. liquidation: check(ledger_state, prices) -> LiquidationResult
6. metrics: record(step_result) -> MetricsUpdate
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
import uuid

from .types import (
    Bar,
    Order,
    OrderId,
    OrderSide,
    OrderType,
    OrderStatus,
    Position,
    Fill,
    FillReason,
    FundingEvent,
    StepResult,
    ExchangeState,
    StopReason,
    ExecutionConfig,
    FundingResult,
)
from .bar_compat import get_bar_ts_open, get_bar_timestamp
from .ledger import Ledger, LedgerConfig
from .pricing import PriceModel, PriceModelConfig, SpreadModel, SpreadConfig, IntrabarPath
from .execution import ExecutionModel, ExecutionModelConfig, SlippageConfig
from .funding import FundingModel
from .liquidation import LiquidationModel
from .metrics import ExchangeMetrics

if TYPE_CHECKING:
    from ..system_config import RiskProfileConfig

# Import validation function for symbol validation
from ..system_config import validate_usdt_pair


class SimulatedExchange:
    """
    Simulated exchange for deterministic backtesting.
    
    Thin orchestrator that coordinates modular components.
    All complex logic delegated to specialized modules.
    """
    
    def __init__(
        self,
        symbol: str,
        initial_capital: float,
        execution_config: Optional[ExecutionConfig] = None,
        risk_profile: "RiskProfileConfig" = None,
        leverage: float = 1.0,
    ):
        """
        Initialize simulated exchange.
        
        This simulator version supports USDT-quoted linear perpetuals only
        (isolated margin mode).
        
        Args:
            symbol: Trading symbol (must be USDT-quoted, e.g., BTCUSDT, ETHUSDT)
            initial_capital: Starting capital in USDT (quote currency)
            execution_config: Execution parameters
            risk_profile: Risk profile configuration (preferred)
            leverage: Leverage (legacy, use risk_profile)
            
        Raises:
            ValueError: If symbol is not USDT-quoted
        """
        # =====================================================================
        # Mode Lock Validation (final defense)
        # This simulator version supports USDT-quoted perpetuals only.
        # =====================================================================
        validate_usdt_pair(symbol)
        
        self.symbol = symbol
        self.initial_capital = initial_capital
        self._exec_config = execution_config or ExecutionConfig()
        
        # Extract config from risk_profile or defaults
        if risk_profile is not None:
            self._leverage = risk_profile.leverage
            self._imr = risk_profile.initial_margin_rate
            self._mmr = risk_profile.maintenance_margin_rate
            self._fee_rate = risk_profile.taker_fee_rate
            self._include_close_fee = risk_profile.include_est_close_fee_in_entry_gate
            self._mark_source = risk_profile.mark_price_source
        else:
            self._leverage = max(1.0, leverage)
            self._imr = 1.0 / self._leverage
            self._mmr = 0.005
            self._fee_rate = 0.0006
            self._include_close_fee = False
            self._mark_source = "close"
        
        # Initialize modules
        self._ledger = Ledger(
            initial_capital,
            LedgerConfig(self._imr, self._mmr, self._fee_rate),
        )
        self._price_model = PriceModel(PriceModelConfig(self._mark_source))
        self._spread_model = SpreadModel()
        self._intrabar = IntrabarPath()
        self._execution = ExecutionModel(ExecutionModelConfig(
            slippage=SlippageConfig(fixed_bps=self._exec_config.slippage_bps),
            taker_fee_rate=self._fee_rate,
        ))
        self._funding = FundingModel()
        self._liquidation = LiquidationModel()
        self._metrics = ExchangeMetrics()
        
        # State
        self.position: Optional[Position] = None
        self.pending_order: Optional[Order] = None
        self.trades: List = []  # Trade records (compatible with old interface)
        self._pending_close_reason: Optional[str] = None
        self._current_ts: Optional[datetime] = None
        self._current_bar_index: int = 0
        self._last_closed_trades: List = []  # Phase 4: closed trades from last step
        
        # Phase 4: Snapshot readiness context (set by engine each bar)
        self._current_snapshot_ready: bool = True
        
        # Starvation tracking
        self.entries_disabled: bool = False
        self.entries_disabled_reason: Optional[StopReason] = None
        self.first_starved_ts: Optional[datetime] = None
        self.first_starved_bar_index: Optional[int] = None
        self.entry_attempts_count: int = 0
        self.entry_rejections_count: int = 0
        self.last_rejection_code: Optional[str] = None
        self.last_rejection_reason: Optional[str] = None
        self.last_fill_rejected: bool = False
        self.total_fees_paid: float = 0.0
    
    # ─────────────────────────────────────────────────────────────────────────
    # Properties (Bybit-aligned)
    # ─────────────────────────────────────────────────────────────────────────
    
    @property
    def cash_balance_usdt(self) -> float:
        return self._ledger.state.cash_balance_usdt
    
    @property
    def unrealized_pnl_usdt(self) -> float:
        return self._ledger.state.unrealized_pnl_usdt
    
    @property
    def equity_usdt(self) -> float:
        return self._ledger.state.equity_usdt
    
    @property
    def used_margin_usdt(self) -> float:
        return self._ledger.state.used_margin_usdt
    
    @property
    def free_margin_usdt(self) -> float:
        return self._ledger.state.free_margin_usdt
    
    @property
    def available_balance_usdt(self) -> float:
        return self._ledger.state.available_balance_usdt
    
    @property
    def maintenance_margin(self) -> float:
        return self._ledger.state.maintenance_margin_usdt
    
    # Config properties (for test compatibility)
    @property
    def initial_margin_rate(self) -> float:
        return self._imr
    
    @property
    def taker_fee_rate(self) -> float:
        return self._fee_rate
    
    # Legacy property aliases
    @property
    def equity(self) -> float:
        return self.equity_usdt
    
    @property
    def cash_balance(self) -> float:
        return self.cash_balance_usdt
    
    @property
    def available_balance(self) -> float:
        return self.available_balance_usdt
    
    @property
    def free_margin(self) -> float:
        return self.free_margin_usdt
    
    @property
    def is_liquidatable(self) -> bool:
        return self._ledger.is_liquidatable
    
    @property
    def leverage(self) -> float:
        return self._leverage
    
    @property
    def last_closed_trades(self) -> List:
        """Get trades closed in the last process_bar call (Phase 4 backward compat)."""
        return self._last_closed_trades
    
    # ─────────────────────────────────────────────────────────────────────────
    # Order Management
    # ─────────────────────────────────────────────────────────────────────────
    
    def submit_order(
        self,
        side: str,
        size_usdt: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> Optional[OrderId]:
        """Submit an order to be filled on next bar."""
        self.entry_attempts_count += 1
        
        if self.entries_disabled:
            self.entry_rejections_count += 1
            self.last_rejection_code = "ENTRIES_DISABLED"
            return None
        
        if self.position is not None or self.pending_order is not None:
            return None
        
        order_side = OrderSide.LONG if side == "long" else OrderSide.SHORT
        order_id = f"order-{uuid.uuid4().hex[:8]}"
        
        self.pending_order = Order(
            order_id=order_id,
            symbol=self.symbol,
            side=order_side,
            size_usdt=size_usdt,
            order_type=OrderType.MARKET,
            stop_loss=stop_loss,
            take_profit=take_profit,
            created_at=timestamp,
        )
        
        return order_id
    
    def submit_close(self, reason: str = "signal") -> None:
        """Request to close position on next bar."""
        self._pending_close_reason = reason
    
    def cancel_pending_order(self) -> bool:
        """Cancel pending order."""
        if self.pending_order is not None:
            self.pending_order = None
            return True
        return False
    
    def compute_required_for_entry(self, notional_usdt: float) -> float:
        """Compute required balance for entry."""
        return self._ledger.compute_required_for_entry(notional_usdt, self._include_close_fee)
    
    def set_starvation(self, timestamp: datetime, bar_index: int, reason_code: str = "STRATEGY_STARVED") -> None:
        """Mark entries as disabled due to starvation."""
        if not self.entries_disabled:
            self.entries_disabled = True
            self.entries_disabled_reason = StopReason.STRATEGY_STARVED
            self.first_starved_ts = timestamp
            self.first_starved_bar_index = bar_index
            self.last_rejection_code = reason_code
    
    def set_bar_context(self, bar_index: int, snapshot_ready: bool = True) -> None:
        """
        Set the current bar context for Phase 4 artifact tracking.
        
        Called by the engine at the start of each bar to track:
        - bar_index: Current simulation bar index
        - snapshot_ready: Whether the snapshot was ready for strategy evaluation
        """
        self._current_bar_index = bar_index
        self._current_snapshot_ready = snapshot_ready
    
    # ─────────────────────────────────────────────────────────────────────────
    # Bar Processing (Main Loop)
    # ─────────────────────────────────────────────────────────────────────────
    
    def process_bar(
        self,
        bar: Bar,
        prev_bar: Optional[Bar] = None,
        funding_events: Optional[List[FundingEvent]] = None,
    ) -> StepResult:
        """
        Process a new bar - main simulation step.
        
        - Fills occur at ts_open (bar open)
        - MTM updates occur at step time (ts_close)
        
        Mark price computed exactly once per step via PriceModel.
        All MTM/liquidation uses the same mark_price.
        
        Returns:
            StepResult with mark_price, fills, and all step events
        """
        # Get timestamps from bar (supports both legacy and canonical)
        ts_open = get_bar_ts_open(bar)
        step_time = get_bar_timestamp(bar)  # ts_close for canonical, timestamp for legacy
        
        self._current_ts = step_time
        fills: List[Fill] = []
        closed_trades = []
        
        # 1. Get prices - COMPUTE MARK PRICE EXACTLY ONCE
        spread = self._spread_model.get_spread(bar)
        prices = self._price_model.get_prices(bar, spread)
        mark_price = prices.mark_price  # Single source of truth for this step
        
        # 2. Apply funding (if position exists)
        prev_ts = get_bar_timestamp(prev_bar) if prev_bar else None
        funding_result = self._funding.apply_events(
            funding_events or [], prev_ts, step_time, self.position
        )
        if funding_result.funding_pnl != 0:
            self._ledger.apply_funding(funding_result.funding_pnl)
        
        # 3. Fill pending entry order (at ts_open)
        if self.pending_order is not None:
            self._fill_pending_order(bar)
        
        # 4. Handle pending close (at ts_open)
        if self._pending_close_reason and self.position:
            trade = self._close_position(bar.open, ts_open, self._pending_close_reason)
            if trade:
                closed_trades.append(trade)
            self._pending_close_reason = None
        
        # 5. Check TP/SL (exit at appropriate price within bar)
        if self.position:
            exit_reason = self._execution.check_tp_sl(self.position, bar)
            if exit_reason:
                exit_price = self._intrabar.get_exit_price(
                    bar, self.position.side, exit_reason,
                    self.position.take_profit, self.position.stop_loss
                )
                # Phase 4: Determine exit_price_source based on exit_reason
                exit_price_source = "tp_level" if exit_reason == FillReason.TAKE_PROFIT else "sl_level"
                # TP/SL fills occur at ts_open (conservative: fill at bar start)
                trade = self._close_position(exit_price, ts_open, exit_reason.value, exit_price_source)
                if trade:
                    closed_trades.append(trade)
        
        # 6. Update balances at bar close using the single mark_price
        self._ledger.update_for_mark_price(self.position, mark_price)
        
        # Store closed trades for backward compatibility
        self._last_closed_trades = closed_trades
        
        # Return StepResult with unified mark price
        return StepResult(
            timestamp=step_time,
            ts_close=step_time,
            mark_price=mark_price,
            mark_price_source=self._mark_source,
            fills=fills,
            rejections=[],
            funding_result=funding_result if funding_result.funding_pnl != 0 else FundingResult(),
            prices=prices,
        )
    
    def _fill_pending_order(self, bar: Bar) -> None:
        """
        Fill pending entry order.
        
        Entry fills occur at ts_open (bar open).
        """
        order = self.pending_order
        self.pending_order = None
        self.last_fill_rejected = False
        
        result = self._execution.fill_entry_order(
            order, bar, self.available_balance_usdt,
            lambda n: self.compute_required_for_entry(n),
        )
        
        if result.rejections:
            self.last_fill_rejected = True
            self.entry_rejections_count += 1
            self.last_rejection_code = result.rejections[0].code
            self.last_rejection_reason = result.rejections[0].reason
            return
        
        if result.fills:
            fill = result.fills[0]
            self._ledger.apply_entry_fee(fill.fee)
            self.total_fees_paid += fill.fee
            
            # fill.timestamp is ts_open (from execution_model)
            self.position = Position(
                position_id=f"pos-{uuid.uuid4().hex[:8]}",
                symbol=order.symbol,
                side=order.side,
                entry_price=fill.price,
                entry_time=fill.timestamp,  # ts_open
                size=fill.size,
                size_usdt=order.size_usdt,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                fees_paid=fill.fee,
                # Phase 4: Bar tracking and readiness
                entry_bar_index=self._current_bar_index,
                entry_ready=self._current_snapshot_ready,
            )
    
    def _close_position(
        self,
        exit_price: float,
        exit_time: datetime,
        reason: str,
        exit_price_source: Optional[str] = None,
    ):
        """
        Close position and create trade record.
        
        Args:
            exit_price: Price at which to close
            exit_time: Timestamp of the close
            reason: Exit reason (tp, sl, signal, end_of_data, liquidation, force)
            exit_price_source: How exit price was determined (tp_level, sl_level, bar_close, etc.)
        """
        pos = self.position
        if pos is None:
            return None
        
        # Map string reason to FillReason
        reason_map = {"sl": FillReason.STOP_LOSS, "tp": FillReason.TAKE_PROFIT}
        fill_reason = reason_map.get(reason, FillReason.SIGNAL)
        
        # Phase 4: Determine exit_price_source if not provided
        if exit_price_source is None:
            if reason == "tp":
                exit_price_source = "tp_level"
            elif reason == "sl":
                exit_price_source = "sl_level"
            elif reason == "liquidation":
                exit_price_source = "mark_price"
            elif reason in ("end_of_data", "force"):
                exit_price_source = "bar_close"
            else:
                exit_price_source = "signal"
        
        # Create a synthetic bar for the exit fill
        # ts_open is the exit time, ts_close is immediate (exit point)
        exit_bar = Bar(
            symbol=pos.symbol,
            tf="exit",  # Synthetic exit bar
            ts_open=exit_time,
            ts_close=exit_time,
            open=exit_price,
            high=exit_price,
            low=exit_price,
            close=exit_price,
            volume=0.0,
        )
        fill = self._execution.fill_exit(pos, exit_bar, fill_reason, exit_price)
        
        realized_pnl = self._execution.calculate_realized_pnl(pos, fill.price)
        self._ledger.apply_exit(realized_pnl, fill.fee)
        self.total_fees_paid += fill.fee
        
        # Create trade record with Phase 4 fields
        from ..types import Trade
        trade = Trade(
            trade_id=f"trade-{uuid.uuid4().hex[:8]}",
            symbol=pos.symbol,
            side=pos.side.value,
            entry_time=pos.entry_time,
            entry_price=pos.entry_price,
            entry_size=pos.size,
            entry_size_usdt=pos.size_usdt,
            exit_time=exit_time,
            exit_price=fill.price,
            exit_reason=reason,
            realized_pnl=realized_pnl,
            fees_paid=pos.fees_paid + fill.fee,
            net_pnl=realized_pnl - fill.fee,
            stop_loss=pos.stop_loss,
            take_profit=pos.take_profit,
            # Phase 4: Bar indices and debugging fields
            entry_bar_index=pos.entry_bar_index,
            exit_bar_index=self._current_bar_index,
            exit_price_source=exit_price_source,
            entry_ready=pos.entry_ready,
            exit_ready=self._current_snapshot_ready,
        )
        
        self.trades.append(trade)
        self.position = None
        return trade
    
    def force_close_position(
        self,
        price: float,
        timestamp: datetime,
        reason: str = "end_of_data",
        exit_price_source: Optional[str] = None,
    ):
        """
        Force close any open position.
        
        Args:
            price: Exit price
            timestamp: Exit timestamp
            reason: Exit reason (default: end_of_data)
            exit_price_source: How exit price was determined (default: bar_close)
        """
        return self._close_position(price, timestamp, reason, exit_price_source)
    
    def get_state(self):
        """Get current exchange state for debugging."""
        return {
            "symbol": self.symbol,
            # USDT balances
            "cash_balance_usdt": self.cash_balance_usdt,
            "unrealized_pnl_usdt": self.unrealized_pnl_usdt,
            "equity_usdt": self.equity_usdt,
            "used_margin_usdt": self.used_margin_usdt,
            "free_margin_usdt": self.free_margin_usdt,
            "available_balance_usdt": self.available_balance_usdt,
            "maintenance_margin_usdt": self.maintenance_margin,
            # Config echo
            "leverage": self._leverage,
            "initial_margin_rate": self._imr,
            "maintenance_margin_rate": self._mmr,
            "taker_fee_rate": self._fee_rate,
            "mark_price_source": self._mark_source,
            # Derived state
            "is_liquidatable": self.is_liquidatable,
            "has_position": self.position is not None,
            "position": self.position.to_dict() if self.position else None,
            "entries_disabled": self.entries_disabled,
            "total_trades": len(self.trades),
            "total_fees_paid": self._ledger.state.total_fees_paid,
        }

