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
    OrderBook,
    OrderId,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    TriggerDirection,
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
from .ledger import Ledger, LedgerConfig
from .pricing import PriceModel, PriceModelConfig, SpreadModel, SpreadConfig, IntrabarPath
from .pricing.intrabar_path import check_tp_sl_1m
from .execution import ExecutionModel, ExecutionModelConfig, SlippageConfig
from .funding import FundingModel
from .liquidation import LiquidationModel

from ..types import Trade

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
            from src.config.constants import DEFAULTS
            self._fee_rate = DEFAULTS.fees.taker_rate
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

        # State
        self.position: Position | None = None
        self._order_book: OrderBook = OrderBook()  # All orders (market, limit, stop)
        self.trades: list = []  # Trade records (compatible with old interface)
        self._trade_counter: int = 0  # Sequential trade ID counter (deterministic)
        self._order_counter: int = 0  # Sequential order ID counter (deterministic)
        self._position_counter: int = 0  # Sequential position ID counter (deterministic)
        self._pending_close_reason: str | None = None
        self._pending_close_percent: float = 100.0  # Partial exit support
        self._current_ts: datetime | None = None
        self._current_bar_index: int = 0
        self._last_mark_price: float | None = None  # Track last mark price for position queries

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
    def maintenance_margin_rate(self) -> float:
        return self._mmr

    @property
    def taker_fee_rate(self) -> float:
        return self._fee_rate
    
    @property
    def is_liquidatable(self) -> bool:
        return self._ledger.is_liquidatable

    @property
    def leverage(self) -> float:
        return self._leverage

    @property
    def total_fees_paid(self) -> float:
        """Total fees paid (from ledger, single source of truth)."""
        return self._ledger.state.total_fees_paid

    @property
    def last_mark_price(self) -> float | None:
        """Last mark price computed during process_bar."""
        return self._last_mark_price

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
        """Submit a market order to be filled on next bar."""
        self.entry_attempts_count += 1

        if self.entries_disabled:
            self.entry_rejections_count += 1
            self.last_rejection_code = "ENTRIES_DISABLED"
            return None

        # Check if position or pending market order already exists
        if self.position is not None:
            return None
        pending_market = self._order_book.get_pending_orders(OrderType.MARKET, self.symbol)
        if pending_market:
            return None

        order_side = OrderSide.LONG if side == "long" else OrderSide.SHORT
        self._order_counter += 1
        order_id = f"order_{self._order_counter:04d}"

        order = Order(
            order_id=order_id,
            symbol=self.symbol,
            side=order_side,
            size_usdt=size_usdt,
            order_type=OrderType.MARKET,
            stop_loss=stop_loss,
            take_profit=take_profit,
            created_at=timestamp,
            submission_bar_index=self._current_bar_index,
        )

        self._order_book.add_order(order)
        return order_id
    
    def submit_limit_order(
        self,
        side: str,
        size_usdt: float,
        limit_price: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        timestamp: datetime | None = None,
    ) -> OrderId | None:
        """
        Submit a limit order.
        
        Args:
            side: "long" or "short"
            size_usdt: Order size in USDT
            limit_price: Limit price for fill
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            time_in_force: GTC, IOC, FOK, or PostOnly
            reduce_only: If True, only reduces position
            timestamp: Order creation timestamp
            
        Returns:
            Order ID if submitted, None if rejected
        """
        if self.entries_disabled and not reduce_only:
            self.entry_rejections_count += 1
            self.last_rejection_code = "ENTRIES_DISABLED"
            return None
        
        if not reduce_only and self.position is not None:
            return None  # Cannot open new position while one is open
        
        order_side = OrderSide.LONG if side == "long" else OrderSide.SHORT
        self._order_counter += 1
        order_id = f"order_{self._order_counter:04d}"
        
        tif = TimeInForce(time_in_force) if isinstance(time_in_force, str) else time_in_force
        
        order = Order(
            order_id=order_id,
            symbol=self.symbol,
            side=order_side,
            size_usdt=size_usdt,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            time_in_force=tif,
            reduce_only=reduce_only,
            stop_loss=stop_loss,
            take_profit=take_profit,
            created_at=timestamp,
            submission_bar_index=self._current_bar_index,
        )
        
        self._order_book.add_order(order)
        return order_id
    
    def submit_stop_order(
        self,
        side: str,
        size_usdt: float,
        trigger_price: float,
        trigger_direction: int = 1,
        limit_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
        reduce_only: bool = False,
        timestamp: datetime | None = None,
    ) -> OrderId | None:
        """
        Submit a stop order (stop-market or stop-limit).
        
        Args:
            side: "long" or "short"
            size_usdt: Order size in USDT
            trigger_price: Price that triggers the order
            trigger_direction: 1=rises to, 2=falls to
            limit_price: If set, creates stop-limit (otherwise stop-market)
            stop_loss: Optional stop loss price
            take_profit: Optional take profit price
            reduce_only: If True, only reduces position
            timestamp: Order creation timestamp
            
        Returns:
            Order ID if submitted, None if rejected
        """
        if self.entries_disabled and not reduce_only:
            self.entry_rejections_count += 1
            self.last_rejection_code = "ENTRIES_DISABLED"
            return None
        
        if not reduce_only and self.position is not None:
            return None  # Cannot open new position while one is open
        
        order_side = OrderSide.LONG if side == "long" else OrderSide.SHORT
        self._order_counter += 1
        order_id = f"order_{self._order_counter:04d}"
        
        order_type = OrderType.STOP_LIMIT if limit_price else OrderType.STOP_MARKET
        direction = TriggerDirection(trigger_direction)
        
        order = Order(
            order_id=order_id,
            symbol=self.symbol,
            side=order_side,
            size_usdt=size_usdt,
            order_type=order_type,
            limit_price=limit_price,
            trigger_price=trigger_price,
            trigger_direction=direction,
            reduce_only=reduce_only,
            stop_loss=stop_loss,
            take_profit=take_profit,
            created_at=timestamp,
            submission_bar_index=self._current_bar_index,
        )
        
        self._order_book.add_order(order)
        return order_id
    
    def cancel_order_by_id(self, order_id: str) -> bool:
        """Cancel an order by its ID."""
        return self._order_book.cancel_order(order_id)
    
    def cancel_all_orders(self) -> int:
        """Cancel all pending orders."""
        return self._order_book.cancel_all(self.symbol)

    def amend_order(
        self,
        order_id: str,
        limit_price: float | None = None,
        trigger_price: float | None = None,
        size_usdt: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> bool:
        """
        Amend an existing pending order.

        Args:
            order_id: ID of order to amend
            limit_price: New limit price (for LIMIT/STOP_LIMIT)
            trigger_price: New trigger price (for STOP_MARKET/STOP_LIMIT)
            size_usdt: New size in USDT
            stop_loss: New stop loss (0 to remove)
            take_profit: New take profit (0 to remove)

        Returns:
            True if amended, False if order not found
        """
        return self._order_book.amend_order(
            order_id,
            limit_price=limit_price,
            trigger_price=trigger_price,
            size_usdt=size_usdt,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def get_open_orders(self) -> list[Order]:
        """Get all open orders."""
        return self._order_book.get_pending_orders(symbol=self.symbol)
    
    def submit_close(self, reason: str = "signal", percent: float = 100.0) -> None:
        """Request to close position on next bar.

        Args:
            reason: Close reason (signal, etc.)
            percent: Percentage of position to close (1-100, default 100 = full close)

        Raises:
            ValueError: If percent is not in (0, 100]
        """
        # FAIL LOUD: Validate percent strictly (minimum 1% to prevent dust positions)
        if percent < 1.0 or percent > 100:
            raise ValueError(f"submit_close: percent must be in [1, 100], got {percent}")
        self._pending_close_reason = reason
        self._pending_close_percent = percent
    
    def cancel_pending_order(self) -> bool:
        """Cancel pending market order (legacy compatibility)."""
        pending_market = self._order_book.get_pending_orders(OrderType.MARKET, self.symbol)
        if pending_market:
            return self._order_book.cancel_order(pending_market[0].order_id)
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
    # Bar Processing Helpers (G4.3 Refactor)
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_funding_events(
        self,
        funding_events: list[FundingEvent] | None,
        prev_ts: datetime | None,
        step_time: datetime,
        mark_price: float,
    ) -> FundingResult:
        """Apply funding events to position."""
        funding_result = self._funding.apply_events(
            funding_events or [], prev_ts, step_time, self.position, mark_price
        )
        if funding_result.funding_pnl != 0:
            self._ledger.apply_funding(funding_result.funding_pnl)
            if self.position is not None:
                self.position.funding_pnl_cumulative += funding_result.funding_pnl
        return funding_result

    def _process_pending_close(
        self,
        bar: Bar,
        ts_open: datetime,
    ) -> tuple[list[Trade], list[Fill]]:
        """Process pending close request at bar open."""
        closed_trades = []
        fills = []

        if not self._pending_close_reason or not self.position:
            return closed_trades, fills

        close_percent = self._pending_close_percent
        if close_percent >= 99.9999:  # Use epsilon for float comparison
            result = self._close_position(bar.open, ts_open, self._pending_close_reason)
            if result:
                trade, exit_fill = result
                closed_trades.append(trade)
                fills.append(exit_fill)
        else:
            result = self._partial_close_position(
                bar.open, ts_open, self._pending_close_reason, close_percent
            )
            if result:
                fills.append(result)

        self._pending_close_reason = None
        self._pending_close_percent = 100.0
        return closed_trades, fills

    def _update_dynamic_stops(
        self,
        mark_price: float,
        trailing_config: dict | None,
        break_even_config: dict | None,
        atr_value: float | None,
    ) -> None:
        """Update trailing and break-even stops."""
        if not self.position:
            return

        if trailing_config is not None:
            self.update_trailing_stop(
                current_price=mark_price,
                atr_value=atr_value,
                trail_pct=trailing_config.get("trail_pct"),
                atr_multiplier=trailing_config.get("atr_multiplier", 2.0),
                activation_pct=trailing_config.get("activation_pct", 0.0),
            )

        if break_even_config is not None:
            self.update_break_even_stop(
                current_price=mark_price,
                activation_pct=break_even_config.get("activation_pct", 1.0),
                offset_pct=break_even_config.get("offset_pct", 0.1),
            )

    def _check_tp_sl_exits(
        self,
        bar: Bar,
        ts_open: datetime,
        quote_feed: "FeedStore | None",
        exec_1m_range: tuple[int, int] | None,
    ) -> tuple[list[Trade], list[Fill]]:
        """Check and execute TP/SL exits."""
        closed_trades = []
        fills = []

        if not self.position:
            return closed_trades, fills

        exit_reason = None
        exit_price = None
        exit_price_source = None

        # 1. Use 1m granular check if available
        if quote_feed is not None and exec_1m_range is not None:
            start_1m, end_1m = exec_1m_range
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
                    reason_str, _, price = result_1m
                    exit_reason = FillReason.STOP_LOSS if reason_str == "stop_loss" else FillReason.TAKE_PROFIT
                    exit_price = price
                    exit_price_source = "tp_level" if exit_reason == FillReason.TAKE_PROFIT else "sl_level"

        # 2. Fallback to exec-bar OHLC check
        if exit_reason is None:
            exit_reason = self._execution.check_tp_sl(self.position, bar)
            if exit_reason:
                exit_price = self._intrabar.get_exit_price(
                    bar, self.position.side, exit_reason,
                    self.position.take_profit, self.position.stop_loss
                )
                exit_price_source = "tp_level" if exit_reason == FillReason.TAKE_PROFIT else "sl_level"

        # 3. Execute exit if triggered
        if exit_reason and exit_price is not None:
            result = self._close_position(exit_price, ts_open, exit_reason.value, exit_price_source)
            if result:
                trade, exit_fill = result
                closed_trades.append(trade)
                fills.append(exit_fill)

        return closed_trades, fills

    def _track_mae_mfe(self, bar: Bar) -> None:
        """Track min/max price for MAE/MFE calculation."""
        if not self.position:
            return
        pos = self.position
        if pos.min_price is None or bar.low < pos.min_price:
            pos.min_price = bar.low
        if pos.max_price is None or bar.high > pos.max_price:
            pos.max_price = bar.high

    def _check_liquidation(
        self,
        bar: Bar,
        mark_price: float,
        step_time: datetime,
        prices: "PriceSnapshot",
    ) -> tuple[list[Trade], list[Fill]]:
        """Check and execute liquidation if needed."""
        closed_trades = []
        fills = []

        if not self.position:
            return closed_trades, fills

        # Compute projected equity at this mark price
        projected_unrealized_pnl = self.position.unrealized_pnl(mark_price)
        projected_equity = self._ledger.state.cash_balance_usdt + projected_unrealized_pnl

        # Check maintenance margin threshold
        position_value = self.position.size * mark_price
        maintenance_margin = position_value * self._ledger._config.maintenance_margin_rate

        if projected_equity <= maintenance_margin:
            liq_result = self._liquidation.check_liquidation(
                self._ledger.state, prices, self.position
            )
            if liq_result.liquidated and liq_result.event:
                result = self._close_position(
                    mark_price, step_time, "liquidation", "mark_price"
                )
                if result:
                    trade, exit_fill = result
                    closed_trades.append(trade)
                    fills.append(exit_fill)
                    self._ledger.apply_liquidation_fee(liq_result.event.liquidation_fee)

        return closed_trades, fills

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
        trailing_config: dict | None = None,
        break_even_config: dict | None = None,
        atr_value: float | None = None,
    ) -> StepResult:
        """
        Process a new bar - main simulation step (G4.3 refactored).

        Orchestrates helper methods for each processing phase.
        Mark price computed once via PriceModel, used throughout.

        Args:
            bar: Current exec-timeframe bar
            prev_bar: Previous exec-timeframe bar (for funding)
            funding_events: Funding events to process
            quote_feed: Optional 1m FeedStore for granular TP/SL checking
            exec_1m_range: Optional (start_idx, end_idx) of 1m bars
            trailing_config: Optional trailing stop config
            break_even_config: Optional break-even config
            atr_value: Optional ATR value for ATR-based trailing stops

        Returns:
            StepResult with mark_price, fills, and all step events
        """
        ts_open = bar.ts_open
        step_time = bar.ts_close
        self._current_ts = step_time
        fills: list[Fill] = []

        # 1. Compute prices (mark price is single source of truth)
        spread = self._spread_model.get_spread(bar)
        prices = self._price_model.get_prices(bar, spread)
        mark_price = prices.mark_price
        self._last_mark_price = mark_price

        # 2. Apply funding events
        prev_ts = prev_bar.ts_close if prev_bar else None
        funding_result = self._apply_funding_events(
            funding_events, prev_ts, step_time, mark_price
        )

        # 3. Process order book
        order_book_fills = self._process_order_book(bar, quote_feed, exec_1m_range)
        fills.extend(order_book_fills)

        # 4. Process pending close
        close_trades, close_fills = self._process_pending_close(bar, ts_open)
        fills.extend(close_fills)

        # 5. Update dynamic stops
        self._update_dynamic_stops(mark_price, trailing_config, break_even_config, atr_value)

        # 6. Check TP/SL exits
        tpsl_trades, tpsl_fills = self._check_tp_sl_exits(bar, ts_open, quote_feed, exec_1m_range)
        fills.extend(tpsl_fills)

        # 7. Track MAE/MFE
        self._track_mae_mfe(bar)

        # 8. Check liquidation
        liq_trades, liq_fills = self._check_liquidation(bar, mark_price, step_time, prices)
        fills.extend(liq_fills)

        # 9. Update ledger with mark price
        self._ledger.update_for_mark_price(self.position, mark_price)

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
    
    def _process_order_book(
        self,
        bar: Bar,
        quote_feed: "FeedStore | None" = None,
        exec_1m_range: tuple[int, int] | None = None,
    ) -> list[Fill]:
        """
        Process all orders in the order book against the current bar.

        Processing order:
        1. Fill market orders at bar open (immediate fill)
           - Uses 1m granularity when quote_feed/exec_1m_range available
        2. Check stop orders for trigger conditions
        3. Fill triggered stops (market or limit)
        4. Check limit orders for fill conditions
        5. Fill limit orders

        Args:
            bar: Current bar OHLC
            quote_feed: Optional 1m FeedStore for granular entry fills
            exec_1m_range: Optional (start_idx, end_idx) of 1m bars within this exec bar

        Returns:
            List of fills from order book processing
        """
        fills: list[Fill] = []
        to_remove: list[str] = []

        # 1. Process market orders first (fill at bar open or first 1m open)
        market_orders = self._order_book.get_pending_orders(OrderType.MARKET, self.symbol)
        for order in market_orders:
            self.last_fill_rejected = False

            # Use 1m granularity for entry fills when available
            if quote_feed is not None and exec_1m_range is not None:
                result = self._execution.fill_entry_order_1m(
                    order, bar, quote_feed, exec_1m_range,
                    self.available_balance_usdt,
                    lambda n: self.compute_required_for_entry(n),
                )
            else:
                result = self._execution.fill_entry_order(
                    order, bar, self.available_balance_usdt,
                    lambda n: self.compute_required_for_entry(n),
                )

            if result.rejections:
                self.last_fill_rejected = True
                self.entry_rejections_count += 1
                self.last_rejection_code = result.rejections[0].code
                self.last_rejection_reason = result.rejections[0].reason
                to_remove.append(order.order_id)
            elif result.fills:
                fill = result.fills[0]
                fills.append(fill)
                to_remove.append(order.order_id)
                self._handle_entry_fill(fill, order)

        # 2. Check and process triggered stop orders
        triggered_stops = self._order_book.check_triggers(bar)
        for order in triggered_stops:
            # Check reduce-only constraints
            if order.reduce_only:
                is_valid, clamped_size, error = self._execution.check_reduce_only(
                    order, self.position
                )
                if not is_valid:
                    to_remove.append(order.order_id)
                    continue
                if clamped_size and clamped_size < order.size_usdt:
                    order.size_usdt = clamped_size
            
            # Fill the triggered stop
            result = self._execution.fill_triggered_stop(
                order, bar, self.available_balance_usdt,
                lambda n: self.compute_required_for_entry(n),
            )
            
            if result.fills:
                fill = result.fills[0]
                fills.append(fill)
                to_remove.append(order.order_id)
                
                # Handle position creation/modification
                if order.reduce_only and self.position:
                    # This is a reduce-only fill - close or reduce position
                    self._handle_reduce_only_fill(fill, order)
                elif not order.reduce_only:
                    # Entry fill - create position
                    self._handle_entry_fill(fill, order)
            elif result.rejections:
                to_remove.append(order.order_id)
        
        # 2. Check and process limit orders
        limit_orders = self._order_book.get_pending_orders(OrderType.LIMIT, self.symbol)
        for order in limit_orders:
            if order.order_id in to_remove:
                continue  # Already processed
            
            # Check reduce-only constraints
            if order.reduce_only:
                is_valid, clamped_size, error = self._execution.check_reduce_only(
                    order, self.position
                )
                if not is_valid:
                    to_remove.append(order.order_id)
                    continue
                if clamped_size and clamped_size < order.size_usdt:
                    order.size_usdt = clamped_size
            
            # Try to fill the limit order
            # Compute is_first_bar for IOC/FOK handling
            is_first_bar = (
                order.submission_bar_index is not None
                and order.submission_bar_index == self._current_bar_index
            )
            result = self._execution.fill_limit_order(
                order, bar, self.available_balance_usdt,
                lambda n: self.compute_required_for_entry(n),
                is_first_bar=is_first_bar,
            )
            
            if result.fills:
                fill = result.fills[0]
                fills.append(fill)
                to_remove.append(order.order_id)
                
                if order.reduce_only and self.position:
                    self._handle_reduce_only_fill(fill, order)
                elif not order.reduce_only:
                    self._handle_entry_fill(fill, order)
            elif result.rejections:
                to_remove.append(order.order_id)
        
        # 3. Remove processed orders from book
        for order_id in to_remove:
            self._order_book.cancel_order(order_id)
        
        return fills
    
    def _handle_entry_fill(self, fill: Fill, order: Order) -> None:
        """Handle position creation from entry fill."""
        self._ledger.apply_entry_fee(fill.fee)
        self._position_counter += 1
        
        self.position = Position(
            position_id=f"pos_{self._position_counter:04d}",
            symbol=order.symbol,
            side=order.side,
            entry_price=fill.price,
            entry_time=fill.timestamp,
            size=fill.size,
            size_usdt=order.size_usdt,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            fees_paid=fill.fee,
            entry_fee=fill.fee,  # Track original entry fee for partial close pro-rating
            entry_bar_index=self._current_bar_index,
            entry_ready=self._current_snapshot_ready,
        )
    
    def _handle_reduce_only_fill(self, fill: Fill, order: Order) -> None:
        """
        Handle position reduction from reduce-only fill.

        Supports both full and partial closes:
        - Full close: order.size_usdt >= position.size_usdt
        - Partial close: order.size_usdt < position.size_usdt

        For partial closes:
        - Calculate proportional PnL
        - Reduce position size
        - Margin recalculated on next update_for_mark_price call
        """
        pos = self.position
        if pos is None:
            return

        # Determine if this is a full or partial close
        close_ratio = min(1.0, order.size_usdt / pos.size_usdt)
        is_full_close = close_ratio >= 0.9999  # Account for float precision

        # Calculate PnL for the closed portion
        # PnL = price_diff * size_closed
        if pos.side == OrderSide.LONG:
            price_diff = fill.price - pos.entry_price
        else:
            price_diff = pos.entry_price - fill.price

        size_closed = pos.size * close_ratio
        realized_pnl = price_diff * size_closed

        if is_full_close:
            # Full close - use apply_exit which clears margin state
            self._ledger.apply_exit(realized_pnl, fill.fee)
            self.position = None
        else:
            # Partial close - use apply_partial_exit which keeps margin state
            # Margin will be recalculated on next update_for_mark_price call
            self._ledger.apply_partial_exit(realized_pnl, fill.fee)

            # Reduce position size
            remaining_ratio = 1.0 - close_ratio
            pos.size = pos.size * remaining_ratio
            pos.size_usdt = pos.size_usdt * remaining_ratio
            pos.fees_paid += fill.fee
    
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
            # Phase 12: Funding PnL from position lifetime
            funding_pnl=pos.funding_pnl_cumulative,
        )

        self.trades.append(trade)
        self.position = None
        return trade, fill  # BUG-004 FIX: Return both for fills population

    def _partial_close_position(
        self,
        exit_price: float,
        exit_time: datetime,
        reason: str,
        percent: float,
    ) -> Fill | None:
        """
        Partially close position and return fill.

        Unlike full close, partial closes:
        - Do NOT create a Trade record (only on final close)
        - DO reduce position size proportionally
        - DO realize proportional PnL

        Args:
            exit_price: Price at which to close
            exit_time: Timestamp of the close
            reason: Exit reason (signal, etc.)
            percent: Percentage of position to close (1-99)

        Returns:
            Fill if position was partially closed, None if no position.

        Raises:
            ValueError: If percent is invalid
        """
        pos = self.position
        if pos is None:
            return None

        # FAIL LOUD: Validate percent
        if percent <= 0 or percent >= 100:
            raise ValueError(
                f"_partial_close_position: percent must be in (0, 100), got {percent}"
            )

        # Calculate close ratio
        close_ratio = percent / 100.0

        # Create a synthetic bar for the exit fill
        exit_bar = Bar(
            symbol=pos.symbol,
            tf="exit",
            ts_open=exit_time,
            ts_close=exit_time,
            open=exit_price,
            high=exit_price,
            low=exit_price,
            close=exit_price,
            volume=0.0,
        )

        # Create fill for partial close (execution model handles sizing)
        fill = self._execution.fill_exit(
            pos, exit_bar, FillReason.SIGNAL, exit_price, close_ratio=close_ratio
        )

        # Calculate PnL for the closed portion
        if pos.side == OrderSide.LONG:
            price_diff = exit_price - pos.entry_price
        else:
            price_diff = pos.entry_price - exit_price

        size_closed = pos.size * close_ratio
        realized_pnl = price_diff * size_closed

        # Pro-rate entry fee for this partial close
        # Entry fee was already deducted from equity at entry, so we're just
        # tracking the allocation for accurate trade-level accounting
        entry_fee_portion = pos.entry_fee * close_ratio
        total_fees_this_close = entry_fee_portion + fill.fee

        # Apply partial exit to ledger (entry fee portion already deducted at entry,
        # so we only apply the exit fee; the entry_fee_portion is for tracking only)
        self._ledger.apply_partial_exit(realized_pnl, fill.fee)

        # Reduce position size and adjust remaining entry fee
        remaining_ratio = 1.0 - close_ratio
        pos.size = pos.size * remaining_ratio
        pos.size_usdt = pos.size_usdt * remaining_ratio
        pos.entry_fee = pos.entry_fee * remaining_ratio  # Remaining entry fee
        pos.fees_paid += fill.fee

        return fill

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

    def update_trailing_stop(
        self,
        current_price: float,
        atr_value: float | None = None,
        trail_pct: float | None = None,
        atr_multiplier: float = 2.0,
        activation_pct: float = 0.0,
    ) -> float | None:
        """
        Update trailing stop based on current price.

        Only moves stop in favorable direction (never backwards).
        Returns new stop price if updated, None if no change.

        Args:
            current_price: Current market price (mark price)
            atr_value: ATR value for ATR-based trailing (optional)
            trail_pct: Percent for percent-based trailing (optional)
            atr_multiplier: Multiplier for ATR-based trailing
            activation_pct: Profit % required to activate trailing

        Returns:
            New stop price if updated, None otherwise
        """
        if self.position is None:
            return None

        pos = self.position
        entry = pos.entry_price
        is_long = pos.side == OrderSide.LONG

        # Initialize tracking if needed
        if pos.initial_stop is None and pos.stop_loss is not None:
            pos.initial_stop = pos.stop_loss
        if pos.peak_favorable_price is None:
            pos.peak_favorable_price = entry

        # Update peak favorable price
        if is_long:
            pos.peak_favorable_price = max(pos.peak_favorable_price or entry, current_price)
        else:
            pos.peak_favorable_price = min(pos.peak_favorable_price or entry, current_price)

        # Check activation threshold
        if activation_pct > 0 and not pos.trailing_active:
            profit_pct = abs(pos.peak_favorable_price - entry) / entry * 100
            if profit_pct < activation_pct:
                return None  # Not yet activated
            pos.trailing_active = True

        # Calculate new trailing stop
        new_stop = None
        if atr_value is not None and atr_value > 0:
            # ATR-based trailing
            if is_long:
                new_stop = pos.peak_favorable_price - (atr_value * atr_multiplier)
            else:
                new_stop = pos.peak_favorable_price + (atr_value * atr_multiplier)
        elif trail_pct is not None and trail_pct > 0:
            # Percent-based trailing
            trail_distance = pos.peak_favorable_price * trail_pct / 100
            if is_long:
                new_stop = pos.peak_favorable_price - trail_distance
            else:
                new_stop = pos.peak_favorable_price + trail_distance
        else:
            return None  # No trailing config

        # Only move stop in favorable direction
        if pos.stop_loss is None:
            pos.stop_loss = new_stop
            return new_stop

        if is_long and new_stop > pos.stop_loss:
            pos.stop_loss = new_stop
            return new_stop
        elif not is_long and new_stop < pos.stop_loss:
            pos.stop_loss = new_stop
            return new_stop

        return None

    def update_break_even_stop(
        self,
        current_price: float,
        activation_pct: float = 1.0,
        offset_pct: float = 0.1,
    ) -> float | None:
        """
        Update stop to break-even after reaching profit threshold.

        Only triggers once per position. Moves stop to entry price
        plus a small offset for safety.

        Args:
            current_price: Current market price
            activation_pct: Profit % required to move stop to BE
            offset_pct: Offset % above/below entry for BE stop

        Returns:
            New stop price if updated, None otherwise
        """
        if self.position is None:
            return None

        pos = self.position

        # BE only triggers once
        if pos.be_activated:
            return None

        entry = pos.entry_price
        is_long = pos.side == OrderSide.LONG

        # Calculate profit percentage
        if is_long:
            profit_pct = (current_price - entry) / entry * 100
        else:
            profit_pct = (entry - current_price) / entry * 100

        # Check if activation threshold reached
        if profit_pct < activation_pct:
            return None

        # Calculate BE stop with offset
        if is_long:
            new_stop = entry * (1 + offset_pct / 100)
        else:
            new_stop = entry * (1 - offset_pct / 100)

        # Only move stop if new stop is better
        if pos.stop_loss is None or (is_long and new_stop > pos.stop_loss) or \
           (not is_long and new_stop < pos.stop_loss):
            # Save original stop if not already saved
            if pos.initial_stop is None:
                pos.initial_stop = pos.stop_loss
            pos.stop_loss = new_stop
            pos.be_activated = True
            return new_stop

        pos.be_activated = True  # Mark as activated even if stop wasn't moved
        return None

