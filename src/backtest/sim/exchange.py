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

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

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
    SimulatorExchangeState,
    StopReason,
    ExecutionConfig,
    FundingResult,
)
from .bar_compat import get_bar_ts_open, get_bar_timestamp
from .ledger import Ledger, LedgerConfig
from .pricing import PriceModel, PriceModelConfig, SpreadModel, SpreadConfig, IntrabarPath
from .pricing.intrabar_path import check_tp_sl_1m
from .execution import ExecutionModel, ExecutionModelConfig, SlippageConfig
from .funding import FundingModel
from .liquidation import LiquidationModel
from .metrics import ExchangeMetrics

if TYPE_CHECKING:
    from ..system_config import RiskProfileConfig
    from ..runtime.feed_store import FeedStore

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
        execution_config: ExecutionConfig | None = None,
        risk_profile: RiskProfileConfig | None = None,
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
        self.position: Position | None = None
        self.pending_order: Order | None = None
        self.trades: list = []  # Trade records (compatible with old interface)
        self._trade_counter: int = 0  # Sequential trade ID counter (deterministic)
        self._order_counter: int = 0  # Sequential order ID counter (deterministic)
        self._position_counter: int = 0  # Sequential position ID counter (deterministic)
        self._pending_close_reason: str | None = None
        self._current_ts: datetime | None = None
        self._current_bar_index: int = 0

        # Phase 4: Snapshot readiness context (set by engine each bar)
        self._current_snapshot_ready: bool = True
        
        # Starvation tracking
        self.entries_disabled: bool = False
        self.entries_disabled_reason: StopReason | None = None
        self.first_starved_ts: datetime | None = None
        self.first_starved_bar_index: int | None = None
        self.entry_attempts_count: int = 0
        self.entry_rejections_count: int = 0
        self.last_rejection_code: str | None = None
        self.last_rejection_reason: str | None = None
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

    # ─────────────────────────────────────────────────────────────────────────
    # Order Management
    # ─────────────────────────────────────────────────────────────────────────
    
    def submit_order(
        self,
        side: str,
        size_usdt: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        timestamp: datetime | None = None,
    ) -> OrderId | None:
        """Submit an order to be filled on next bar."""
        self.entry_attempts_count += 1
        
        if self.entries_disabled:
            self.entry_rejections_count += 1
            self.last_rejection_code = "ENTRIES_DISABLED"
            return None
        
        if self.position is not None or self.pending_order is not None:
            return None
        
        order_side = OrderSide.LONG if side == "long" else OrderSide.SHORT
        self._order_counter += 1
        order_id = f"order_{self._order_counter:04d}"
        
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
        prev_bar: Bar | None = None,
        funding_events: list[FundingEvent] | None = None,
        quote_feed: "FeedStore | None" = None,
        exec_1m_range: tuple[int, int] | None = None,
    ) -> StepResult:
        """
        Process a new bar - main simulation step.

        - Fills occur at ts_open (bar open)
        - MTM updates occur at step time (ts_close)

        Mark price computed exactly once per step via PriceModel.
        All MTM/liquidation uses the same mark_price.

        Args:
            bar: Current exec-timeframe bar
            prev_bar: Previous exec-timeframe bar (for funding)
            funding_events: Funding events to process
            quote_feed: Optional 1m FeedStore for granular TP/SL checking
            exec_1m_range: Optional (start_idx, end_idx) of 1m bars within this exec bar

        Returns:
            StepResult with mark_price, fills, and all step events
        """
        # Get timestamps from bar (supports both legacy and canonical)
        ts_open = get_bar_ts_open(bar)
        step_time = get_bar_timestamp(bar)  # ts_close for canonical, timestamp for legacy
        
        self._current_ts = step_time
        fills: list[Fill] = []
        closed_trades = []
        
        # 1. Get prices - COMPUTE MARK PRICE EXACTLY ONCE
        spread = self._spread_model.get_spread(bar)
        prices = self._price_model.get_prices(bar, spread)
        mark_price = prices.mark_price  # Single source of truth for this step
        
        # 2. Apply funding (if position exists)
        # Note: Bybit uses mark_price at funding time, not entry_price
        prev_ts = get_bar_timestamp(prev_bar) if prev_bar else None
        funding_result = self._funding.apply_events(
            funding_events or [], prev_ts, step_time, self.position, mark_price
        )
        if funding_result.funding_pnl != 0:
            self._ledger.apply_funding(funding_result.funding_pnl)
        
        # 3. Fill pending entry order (at ts_open)
        # BUG-004 FIX: Capture entry fill for StepResult.fills
        if self.pending_order is not None:
            entry_fill = self._fill_pending_order(bar)
            if entry_fill:
                fills.append(entry_fill)
        
        # 4. Handle pending close (at ts_open)
        # BUG-004 FIX: Capture exit fill for StepResult.fills
        if self._pending_close_reason and self.position:
            result = self._close_position(bar.open, ts_open, self._pending_close_reason)
            if result:
                trade, exit_fill = result
                closed_trades.append(trade)
                fills.append(exit_fill)
            self._pending_close_reason = None
        
        # 5. Check TP/SL (exit at appropriate price within bar)
        if self.position:
            exit_reason = None
            exit_price = None
            exit_price_source = None

            # Try 1m granular TP/SL check if quote_feed and range provided
            if quote_feed is not None and exec_1m_range is not None:
                start_1m, end_1m = exec_1m_range
                # Build list of 1m bars as (open, high, low, close) tuples
                bars_1m = []
                for i in range(start_1m, min(end_1m + 1, quote_feed.length)):
                    bars_1m.append((
                        float(quote_feed.open[i]),
                        float(quote_feed.high[i]),
                        float(quote_feed.low[i]),
                        float(quote_feed.close[i]),
                    ))

                if bars_1m:
                    position_side = "long" if self.position.side == OrderSide.LONG else "short"
                    result_1m = check_tp_sl_1m(
                        position_side=position_side,
                        entry_price=self.position.entry_price,
                        take_profit=self.position.take_profit,
                        stop_loss=self.position.stop_loss,
                        bars_1m=bars_1m,
                    )
                    if result_1m:
                        reason_str, hit_bar_idx, price = result_1m
                        exit_reason = FillReason.STOP_LOSS if reason_str == "stop_loss" else FillReason.TAKE_PROFIT
                        exit_price = price
                        exit_price_source = "tp_level" if exit_reason == FillReason.TAKE_PROFIT else "sl_level"

            # Fallback to exec-bar OHLC check if no 1m hit or no quote_feed
            if exit_reason is None:
                exit_reason = self._execution.check_tp_sl(self.position, bar)
                if exit_reason:
                    exit_price = self._intrabar.get_exit_price(
                        bar, self.position.side, exit_reason,
                        self.position.take_profit, self.position.stop_loss
                    )
                    exit_price_source = "tp_level" if exit_reason == FillReason.TAKE_PROFIT else "sl_level"

            # Close position if TP/SL hit
            # BUG-004 FIX: Capture exit fill for StepResult.fills
            if exit_reason and exit_price is not None:
                # TP/SL fills occur at ts_open (conservative: fill at bar start)
                result = self._close_position(exit_price, ts_open, exit_reason.value, exit_price_source)
                if result:
                    trade, exit_fill = result
                    closed_trades.append(trade)
                    fills.append(exit_fill)

        # 5b. Track min/max price for MAE/MFE (if position still open)
        if self.position:
            pos = self.position
            if pos.min_price is None or bar.low < pos.min_price:
                pos.min_price = bar.low
            if pos.max_price is None or bar.high > pos.max_price:
                pos.max_price = bar.high

        # 6. Update balances at bar close using the single mark_price
        self._ledger.update_for_mark_price(self.position, mark_price)

        # 7. Check liquidation (after ledger update)
        if self.position:
            liq_result = self._liquidation.check_liquidation(
                self._ledger.state, prices, self.position
            )
            if liq_result.liquidated and liq_result.event:
                # Liquidation triggered - close position at mark price
                # BUG-004 FIX: Capture exit fill for StepResult.fills
                result = self._close_position(
                    mark_price, step_time, "liquidation", "mark_price"
                )
                if result:
                    trade, exit_fill = result
                    closed_trades.append(trade)
                    fills.append(exit_fill)
                    # Apply liquidation fee (P0 FIX: was apply_exit_fee which doesn't exist)
                    self._ledger.apply_liquidation_fee(liq_result.event.liquidation_fee)
                    self.total_fees_paid += liq_result.event.liquidation_fee

        # NOTE: closed_trades list is local; callers use step_result.fills or
        # self.trades (cumulative). _last_closed_trades removed (no legacy code forward).

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
    
    def _fill_pending_order(self, bar: Bar) -> Fill | None:
        """
        Fill pending entry order.

        Entry fills occur at ts_open (bar open).

        Returns:
            Fill object if order was filled, None if rejected.
            BUG-004 FIX: Returns fill for StepResult.fills population.
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
            return None

        if result.fills:
            fill = result.fills[0]
            self._ledger.apply_entry_fee(fill.fee)
            self.total_fees_paid += fill.fee

            # fill.timestamp is ts_open (from execution_model)
            self._position_counter += 1
            # P1-005 DOCUMENTED: size_usdt semantics
            # - size_usdt = "intended notional" (order.size_usdt, before slippage)
            # - size * entry_price = "actual fill notional" (after slippage)
            # This is intentional: size_usdt tracks trader intent, actual fill varies.
            # Fee calculation uses size_usdt for consistency (entry and exit both use intended).
            self.position = Position(
                position_id=f"pos_{self._position_counter:04d}",
                symbol=order.symbol,
                side=order.side,
                entry_price=fill.price,
                entry_time=fill.timestamp,  # ts_open
                size=fill.size,
                size_usdt=order.size_usdt,  # Intended notional (before slippage)
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                fees_paid=fill.fee,
                # Phase 4: Bar tracking and readiness
                entry_bar_index=self._current_bar_index,
                entry_ready=self._current_snapshot_ready,
            )
            return fill

        return None
    
    def _close_position(
        self,
        exit_price: float,
        exit_time: datetime,
        reason: str,
        exit_price_source: str | None = None,
    ) -> tuple | None:
        """
        Close position and create trade record.

        Args:
            exit_price: Price at which to close
            exit_time: Timestamp of the close
            reason: Exit reason (tp, sl, signal, end_of_data, liquidation, force)
            exit_price_source: How exit price was determined (tp_level, sl_level, bar_close, etc.)

        Returns:
            Tuple of (Trade, Fill) if position was closed, None if no position.
            BUG-004 FIX: Returns fill for StepResult.fills population.
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

        # Compute MAE/MFE from tracked min/max prices
        mae_pct = 0.0
        mfe_pct = 0.0
        if pos.entry_price > 0 and pos.min_price is not None and pos.max_price is not None:
            if pos.side == OrderSide.LONG:
                # Long: adverse = price drops, favorable = price rises
                mae_pct = (pos.entry_price - pos.min_price) / pos.entry_price * 100
                mfe_pct = (pos.max_price - pos.entry_price) / pos.entry_price * 100
            else:
                # Short: adverse = price rises, favorable = price drops
                mae_pct = (pos.max_price - pos.entry_price) / pos.entry_price * 100
                mfe_pct = (pos.entry_price - pos.min_price) / pos.entry_price * 100

        # Create trade record with Phase 4 fields
        from ..types import Trade
        self._trade_counter += 1
        trade = Trade(
            trade_id=f"trade_{self._trade_counter:03d}",
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
            net_pnl=realized_pnl - (pos.fees_paid + fill.fee),  # Must include BOTH entry and exit fees
            stop_loss=pos.stop_loss,
            take_profit=pos.take_profit,
            # Phase 4: Bar indices and debugging fields
            entry_bar_index=pos.entry_bar_index,
            exit_bar_index=self._current_bar_index,
            exit_price_source=exit_price_source,
            entry_ready=pos.entry_ready,
            exit_ready=self._current_snapshot_ready,
            # MAE/MFE
            mae_pct=round(mae_pct, 4),
            mfe_pct=round(mfe_pct, 4),
        )

        self.trades.append(trade)
        self.position = None
        return trade, fill  # BUG-004 FIX: Return both for fills population

    def force_close_position(
        self,
        price: float,
        timestamp: datetime,
        reason: str = "end_of_data",
        exit_price_source: str | None = None,
    ):
        """
        Force close any open position.

        Args:
            price: Exit price
            timestamp: Exit timestamp
            reason: Exit reason (default: end_of_data)
            exit_price_source: How exit price was determined (default: bar_close)

        Returns:
            Trade record if position was closed, None if no position.
        """
        result = self._close_position(price, timestamp, reason, exit_price_source)
        if result:
            trade, _ = result
            return trade
        return None
    
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

