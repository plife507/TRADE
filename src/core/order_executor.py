"""
Order executor - handles trade execution through risk checks.

Flow: Signal → RiskManager.check() → ExchangeManager

Now supports WebSocket-fed order and execution tracking for faster feedback.

SAFETY GUARD RAILS:
- Validates trading mode consistency before executing any order
- Enforces strict mode/API mapping:
  - PAPER mode → DEMO API only (BYBIT_USE_DEMO=true)
  - REAL mode → LIVE API only (BYBIT_USE_DEMO=false)
- Blocks any other combination as invalid configuration
"""

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from .exchange_manager import ExchangeManager, OrderResult
from .risk_manager import RiskManager, Signal, RiskCheckResult
from .position_manager import PositionManager
from ..config.config import get_config
from ..utils.logger import get_logger


@dataclass
class ExecutionResult:
    """Complete result of an execution attempt."""
    success: bool
    signal: Signal
    risk_check: RiskCheckResult
    order_result: OrderResult | None = None
    executed_size: float | None = None
    error: str | None = None
    timestamp: datetime | None = None
    source: str = "rest"  # "rest" or "websocket"
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "symbol": self.signal.symbol,
            "direction": self.signal.direction,
            "requested_size": self.signal.size_usdt,
            "executed_size": self.executed_size,
            "risk_allowed": self.risk_check.allowed,
            "risk_reason": self.risk_check.reason,
            "risk_warnings": self.risk_check.warnings,
            "order_id": self.order_result.order_id if self.order_result else None,
            "error": self.error,
            "source": self.source,
        }


@dataclass
class PendingOrder:
    """Tracks a pending order awaiting WebSocket confirmation."""
    order_id: str
    symbol: str
    direction: str
    size_usdt: float
    submitted_at: float = field(default_factory=time.time)
    confirmed: bool = False
    filled: bool = False
    fill_price: float | None = None
    error: str | None = None


class OrderExecutor:
    """
    Order execution with integrated risk management and WebSocket support.
    
    All trades flow through:
    1. Risk manager check
    2. Size adjustment if needed
    3. Exchange manager execution
    4. Position manager recording
    
    WebSocket Integration:
    - Tracks pending orders
    - Receives order updates from RealtimeState
    - Provides faster execution feedback via callbacks
    """
    
    def __init__(
        self,
        exchange_manager: ExchangeManager,
        risk_manager: RiskManager,
        position_manager: PositionManager,
        use_ws_feedback: bool = True,
    ):
        """
        Initialize order executor.
        
        Args:
            exchange_manager: ExchangeManager instance
            risk_manager: RiskManager instance
            position_manager: PositionManager instance
            use_ws_feedback: Whether to use WebSocket for order feedback
        """
        self.exchange = exchange_manager
        self.risk = risk_manager
        self.position = position_manager
        self.logger = get_logger()
        
        # WebSocket integration
        self._use_ws_feedback = use_ws_feedback
        self._realtime_state = None
        self._pending_orders: dict[str, PendingOrder] = {}
        self._pending_lock = threading.RLock()  # Protects _pending_orders access
        self._last_cleanup_time: float = 0.0  # For time-based cleanup

        # Idempotency: track recorded order IDs to prevent duplicate trade recording
        # Bounded to 10,000 entries; oldest evicted first via OrderedDict
        self._recorded_orders: OrderedDict[str, None] = OrderedDict()
        self._recorded_orders_lock = threading.Lock()
        self._recorded_orders_max = 10_000

        # Callbacks
        self._execution_callbacks: list[Callable[[ExecutionResult], None]] = []
        self._callback_lock = threading.Lock()  # Protects callback list access
        
        # Setup WebSocket callbacks if enabled
        if use_ws_feedback:
            self._setup_ws_callbacks()
    
    # ==================== WebSocket Integration ====================
    
    @property
    def realtime_state(self):
        """Get RealtimeState instance (lazy import)."""
        if self._realtime_state is None:
            try:
                from ..data.realtime_state import get_realtime_state
                self._realtime_state = get_realtime_state()
            except ImportError:
                self._realtime_state = None
        return self._realtime_state
    
    def _setup_ws_callbacks(self):
        """Setup WebSocket callbacks for order/execution updates."""
        if not self.realtime_state:
            return
        
        # Register for order updates
        self.realtime_state.on_order_update(self._on_order_update)
        
        # Register for execution updates
        self.realtime_state.on_execution(self._on_execution)
        
        self.logger.info("OrderExecutor WebSocket callbacks registered")
    
    def _on_order_update(self, order_data):
        """Handle order update from WebSocket."""
        order_id = order_data.order_id

        with self._pending_lock:
            # Check if this is a pending order we're tracking
            pending = self._pending_orders.get(order_id)
            if not pending:
                return

            # Update pending order state
            if order_data.status in ("New", "PartiallyFilled"):
                pending.confirmed = True
            elif order_data.status == "Filled":
                pending.filled = True
                pending.confirmed = True
            elif order_data.status in ("Cancelled", "Rejected"):
                pending.error = f"Order {order_data.status}"
                # Auto-cleanup failed orders to prevent memory leak
                del self._pending_orders[order_id]

        self.logger.debug(f"Order {order_id} status: {order_data.status}")
    
    def _on_execution(self, exec_data):
        """Handle execution update from WebSocket."""
        order_id = exec_data.order_id

        with self._pending_lock:
            # Check if this is a pending order we're tracking
            pending = self._pending_orders.get(order_id)
            if not pending:
                return

            # Update fill info
            pending.fill_price = exec_data.price
            pending.filled = True

            # Auto-cleanup completed orders to prevent memory leak
            del self._pending_orders[order_id]

        # Record the trade via position manager (outside lock to avoid deadlock)
        # Idempotency check: skip if already recorded via REST
        with self._recorded_orders_lock:
            if order_id in self._recorded_orders:
                self.logger.debug(f"Order {order_id} already recorded via REST, skipping WS recording")
                return
            self._recorded_orders[order_id] = None
            if len(self._recorded_orders) > self._recorded_orders_max:
                self._recorded_orders.popitem(last=False)

        self.position.record_execution_from_ws(exec_data)

        self.logger.info(
            f"Execution received via WS: {exec_data.symbol} "
            f"{exec_data.side} {exec_data.qty} @ {exec_data.price}"
        )
    
    # ==================== Core Execution ====================
    
    def _validate_trading_mode(self) -> tuple[bool, str]:
        """
        SAFETY GUARD RAIL: Validate trading mode consistency.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        config = get_config()
        is_consistent, messages = config.validate_trading_mode_consistency()
        
        if not is_consistent:
            # Return the first error message
            error_msg = messages[0] if messages else "Trading mode consistency check failed"
            return False, error_msg
        
        # Log warnings but don't block
        for msg in messages:
            if "[WARN]" in msg:
                self.logger.warning(msg.replace("[WARN] ", ""))
        
        return True, ""
    
    def execute(self, signal: Signal) -> ExecutionResult:
        """
        Execute a trading signal through risk checks.

        Args:
            signal: Trading signal to execute

        Returns:
            ExecutionResult with full details
        """
        # SAFETY: Check panic state before anything else
        from .safety import is_panic_triggered
        if is_panic_triggered():
            from .risk_manager import RiskCheckResult
            risk_result = RiskCheckResult(allowed=False, reason="Panic state active - trading halted")
            result = ExecutionResult(
                success=False,
                signal=signal,
                risk_check=risk_result,
                error="Panic state active - trading halted",
            )
            self._invoke_callbacks(result)
            return result

        # SAFETY GUARD RAIL: Validate trading mode consistency FIRST
        is_valid, error_msg = self._validate_trading_mode()
        if not is_valid:
            self.logger.error(f"Trading mode validation failed: {error_msg}")
            # Create a minimal risk check result for the error case
            from .risk_manager import RiskCheckResult
            risk_result = RiskCheckResult(allowed=False, reason=error_msg)
            result = ExecutionResult(
                success=False,
                signal=signal,
                risk_check=risk_result,
                error=error_msg
            )
            self._invoke_callbacks(result)
            return result
        
        self.logger.info(f"Executing signal: {signal.symbol} {signal.direction} ${signal.size_usdt:.2f}")
        
        # Emit order.execute.start event
        self.logger.event(
            "order.execute.start",
            component="order_executor",
            symbol=signal.symbol,
            direction=signal.direction,
            size_usdt=signal.size_usdt,
            strategy=signal.strategy,
        )
        
        # Get current portfolio state
        portfolio = self.position.get_snapshot()
        
        # Step 1: Risk check
        risk_result = self.risk.check(signal, portfolio)
        
        if not risk_result.allowed:
            self.logger.warning(f"Signal blocked by risk manager: {risk_result.reason}")
            
            # Emit order.execute.end event (blocked by risk)
            self.logger.event(
                "order.execute.end",
                level="WARNING",
                component="order_executor",
                symbol=signal.symbol,
                direction=signal.direction,
                success=False,
                blocked_by_risk=True,
                reason=risk_result.reason,
            )
            
            result = ExecutionResult(
                success=False,
                signal=signal,
                risk_check=risk_result,
                error=f"Risk check failed: {risk_result.reason}"
            )
            self._invoke_callbacks(result)
            return result
        
        # Log any warnings
        for warning in (risk_result.warnings or []):
            self.logger.warning(f"Risk warning: {warning}")
        
        # Determine execution size
        exec_size = risk_result.adjusted_size or signal.size_usdt

        # G14.3: Fat finger / price sanity guard
        deviation_result = self._check_price_deviation(signal)
        if deviation_result is not None:
            self._invoke_callbacks(deviation_result)
            return deviation_result

        # Step 2: Execute order
        # Extract order type and parameters from signal metadata
        meta = signal.metadata or {}
        order_type = meta.get("order_type", "market").lower()
        limit_price = meta.get("limit_price")
        time_in_force = meta.get("time_in_force", "GTC")
        tp_order_type = meta.get("tp_order_type", "Market")
        sl_order_type = meta.get("sl_order_type", "Market")
        stop_loss = meta.get("stop_loss")
        take_profit = meta.get("take_profit")

        order_result = None

        try:
            if signal.direction == "FLAT":
                order_result = self.exchange.close_position(signal.symbol)
            elif order_type == "limit" and limit_price is not None:
                # Limit entry with TP/SL
                if signal.direction == "LONG":
                    order_result = self.exchange.limit_buy_with_tpsl(
                        signal.symbol, exec_size, limit_price,
                        take_profit=take_profit, stop_loss=stop_loss,
                        time_in_force=time_in_force,
                        tp_order_type=tp_order_type, sl_order_type=sl_order_type,
                    )
                elif signal.direction == "SHORT":
                    order_result = self.exchange.limit_sell_with_tpsl(
                        signal.symbol, exec_size, limit_price,
                        take_profit=take_profit, stop_loss=stop_loss,
                        time_in_force=time_in_force,
                        tp_order_type=tp_order_type, sl_order_type=sl_order_type,
                    )
            else:
                # Market entry with TP/SL
                if signal.direction == "LONG":
                    order_result = self.exchange.market_buy_with_tpsl(
                        signal.symbol, exec_size,
                        take_profit=take_profit, stop_loss=stop_loss,
                        tp_order_type=tp_order_type, sl_order_type=sl_order_type,
                    )
                elif signal.direction == "SHORT":
                    order_result = self.exchange.market_sell_with_tpsl(
                        signal.symbol, exec_size,
                        take_profit=take_profit, stop_loss=stop_loss,
                        tp_order_type=tp_order_type, sl_order_type=sl_order_type,
                    )

            if order_result is None:
                result = ExecutionResult(
                    success=False,
                    signal=signal,
                    risk_check=risk_result,
                    error=f"Unknown direction: {signal.direction}"
                )
                self._invoke_callbacks(result)
                return result
            
        except Exception as e:
            self.logger.error(f"Order execution failed: {e}")
            
            # Emit order.execute.end event (exception)
            self.logger.event(
                "order.execute.end",
                level="ERROR",
                component="order_executor",
                symbol=signal.symbol,
                direction=signal.direction,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
            )
            
            result = ExecutionResult(
                success=False,
                signal=signal,
                risk_check=risk_result,
                error=str(e)
            )
            self._invoke_callbacks(result)
            return result
        
        # Track pending order for WebSocket confirmation
        if order_result and order_result.order_id and self._use_ws_feedback:
            with self._pending_lock:
                self._pending_orders[order_result.order_id] = PendingOrder(
                    order_id=order_result.order_id,
                    symbol=signal.symbol,
                    direction=signal.direction,
                    size_usdt=exec_size,
                )
                # Periodic cleanup of stale orders (count-based or time-based)
                pending_count = len(self._pending_orders)
                current_time = time.time()
            # Cleanup if: >50 orders OR >60 seconds since last cleanup with pending orders
            if pending_count > 50 or (pending_count > 0 and current_time - self._last_cleanup_time > 60):
                self.cleanup_old_pending_orders(max_age_seconds=300)
                self._last_cleanup_time = current_time
        
        # Step 3: Record trade (immediate REST feedback)
        # For limit orders, do NOT record immediately -- the order is not yet
        # filled.  The fill will be recorded when the execution WebSocket
        # message arrives (via _on_execution).  Only market orders have an
        # actual fill price (avgPrice) available at this point.
        is_limit_order = order_type == "limit" and limit_price is not None
        if order_result and order_result.success and not is_limit_order:
            # Validate price before recording
            if not order_result.price or order_result.price <= 0:
                self.logger.warning(
                    f"Order {order_result.order_id} has invalid price ({order_result.price}), "
                    "skipping REST recording - WebSocket callback will handle it"
                )
            elif order_result.order_id:
                # G0.1: Idempotency check INSIDE lock, record_trade() OUTSIDE lock
                # This prevents deadlock with WebSocket handler which acquires position._trade_lock
                should_record = False
                with self._recorded_orders_lock:
                    if order_result.order_id in self._recorded_orders:
                        self.logger.debug(f"Order {order_result.order_id} already recorded, skipping")
                    else:
                        self._recorded_orders[order_result.order_id] = None
                        if len(self._recorded_orders) > self._recorded_orders_max:
                            self._recorded_orders.popitem(last=False)
                        should_record = True
                # LOCK RELEASED - now safe to call record_trade() without lock inversion risk
                if should_record:
                    self.position.record_trade(
                        symbol=signal.symbol,
                        side="BUY" if signal.direction == "LONG" else "SELL",
                        size_usdt=exec_size,
                        price=order_result.price,
                        order_id=order_result.order_id,
                        strategy=signal.strategy,
                    )
            else:
                # No order_id - can't track idempotency, just record
                self.position.record_trade(
                    symbol=signal.symbol,
                    side="BUY" if signal.direction == "LONG" else "SELL",
                    size_usdt=exec_size,
                    price=order_result.price,
                    order_id=order_result.order_id,
                    strategy=signal.strategy,
                )

            self.logger.info(
                f"Order executed: {signal.symbol} {signal.direction} "
                f"${exec_size:.2f} @ {order_result.price}"
            )

            # Emit order.execute.end event (success)
            self.logger.event(
                "order.execute.end",
                component="order_executor",
                symbol=signal.symbol,
                direction=signal.direction,
                success=True,
                executed_size=exec_size,
                price=order_result.price,
                order_id=order_result.order_id,
            )
        elif order_result and order_result.success and is_limit_order:
            self.logger.info(
                f"Limit order submitted: {signal.symbol} {signal.direction} "
                f"${exec_size:.2f} @ {limit_price} (order_id={order_result.order_id}) "
                "-- fill will be recorded via WebSocket execution callback"
            )

            # Emit order.execute.end event (limit submitted)
            self.logger.event(
                "order.execute.end",
                component="order_executor",
                symbol=signal.symbol,
                direction=signal.direction,
                success=True,
                executed_size=exec_size,
                price=limit_price,
                order_id=order_result.order_id,
                order_type="limit",
            )
        
        result = ExecutionResult(
            success=order_result.success if order_result else False,
            signal=signal,
            risk_check=risk_result,
            order_result=order_result,
            executed_size=exec_size if order_result and order_result.success else None,
            error=order_result.error if order_result and not order_result.success else None,
            source="rest",
        )
        
        self._invoke_callbacks(result)
        return result
    
    def close_position(self, symbol: str, strategy: str | None = None) -> ExecutionResult:
        """
        Close a position (convenience method).
        
        Args:
            symbol: Symbol to close
            strategy: Strategy requesting close
        
        Returns:
            ExecutionResult
        """
        signal = Signal(
            symbol=symbol,
            direction="FLAT",
            size_usdt=0,  # Size determined by position
            strategy=strategy or "manual",
        )
        
        return self.execute(signal)
    
    def execute_with_leverage(
        self,
        signal: Signal,
        leverage: int,
    ) -> ExecutionResult:
        """
        Execute signal with specific leverage.
        
        Args:
            signal: Trading signal
            leverage: Desired leverage
        
        Returns:
            ExecutionResult
        """
        # Check and cap leverage
        _, capped_leverage = self.risk.check_leverage(signal.symbol, leverage)
        
        # Set leverage before execution
        self.exchange.set_leverage(signal.symbol, capped_leverage)
        
        # Execute normally
        return self.execute(signal)
    
    # ==================== Pending Order Management ====================
    
    def get_pending_order(self, order_id: str) -> PendingOrder | None:
        """Get a pending order by ID."""
        with self._pending_lock:
            return self._pending_orders.get(order_id)

    def get_all_pending_orders(self) -> dict[str, PendingOrder]:
        """Get all pending orders (returns a copy)."""
        with self._pending_lock:
            return dict(self._pending_orders)

    def cleanup_old_pending_orders(self, max_age_seconds: float = 300):
        """
        Clean up old pending orders.

        Args:
            max_age_seconds: Maximum age before removal
        """
        now = time.time()
        to_remove = []

        with self._pending_lock:
            for order_id, pending in self._pending_orders.items():
                age = now - pending.submitted_at
                if age > max_age_seconds or pending.filled or pending.error:
                    to_remove.append(order_id)

            for order_id in to_remove:
                del self._pending_orders[order_id]

        if to_remove:
            self.logger.debug(f"Cleaned up {len(to_remove)} old pending orders")

    def _cleanup_completed_order(self, order_id: str) -> None:
        """
        Remove a specific completed order from pending dict.

        Called automatically after fills or cancellations.

        Args:
            order_id: Order ID to remove
        """
        with self._pending_lock:
            if order_id in self._pending_orders:
                del self._pending_orders[order_id]

    def wait_for_fill(
        self,
        order_id: str,
        timeout: float = 10.0,
        poll_interval: float = 0.1,
    ) -> PendingOrder | None:
        """
        Wait for an order to be filled via WebSocket.

        Args:
            order_id: Order ID to wait for
            timeout: Maximum wait time in seconds
            poll_interval: Polling interval in seconds

        Returns:
            PendingOrder if filled, None if timeout or order not found
        """
        start = time.time()
        while time.time() - start < timeout:
            # Re-check dict inside lock each iteration to avoid race conditions
            with self._pending_lock:
                pending = self._pending_orders.get(order_id)
                if not pending:
                    return None
                if pending.filled or pending.error:
                    return pending
            time.sleep(poll_interval)

        # Final check after timeout
        with self._pending_lock:
            pending = self._pending_orders.get(order_id)

        if pending and not pending.filled:
            self.logger.warning(
                f"wait_for_fill timed out after {timeout}s for order {order_id} "
                f"(symbol={pending.symbol}) - falling back to REST query"
            )
            # REST fallback: verify order status via API
            try:
                orders = self.exchange.get_open_orders(pending.symbol)
                found = False
                for order in orders:
                    if order.order_id == order_id:
                        found = True
                        if order.status == "Filled":
                            pending.filled = True
                            pending.fill_price = order.price
                        elif order.status in ("Cancelled", "Rejected"):
                            pending.error = f"Order {order.status} (REST fallback)"
                        break
                if not found:
                    # Order not in open orders - likely already filled or cancelled
                    self.logger.warning(
                        f"Order {order_id} not found in open orders (REST fallback) - may be filled"
                    )
            except Exception as e:
                self.logger.warning(f"REST fallback query failed for order {order_id}: {e}")

        return pending
    
    # ==================== Price Deviation Guard (G14.3) ====================

    # Maximum allowed deviation between last traded price and implied entry.
    # Rejects market orders during flash crashes / extreme slippage.
    MAX_PRICE_DEVIATION_PCT: float = 5.0

    def _check_price_deviation(self, signal: Signal) -> ExecutionResult | None:
        """
        G14.3: Fat finger / price sanity guard.

        Fetches last traded price from exchange and rejects the order if
        the deviation from expected price exceeds MAX_PRICE_DEVIATION_PCT.

        Returns None if check passes, or a failed ExecutionResult if blocked.
        """
        if signal.direction == "FLAT":
            return None  # Always allow position closes

        try:
            ticker = self.exchange.bybit.get_ticker(signal.symbol)
            if not ticker:
                reason = "Price deviation check: no ticker data, blocking entry for safety"
                self.logger.warning(reason)
                return ExecutionResult(
                    success=False,
                    signal=signal,
                    risk_check=RiskCheckResult(allowed=False, reason=reason),
                    error=reason,
                )

            # Bybit ticker response: list with lastPrice field
            last_price_str = None
            if isinstance(ticker, list):
                for item in ticker:
                    last_price_str = item.get("lastPrice") if isinstance(item, dict) else None
                    if last_price_str:
                        break
            elif isinstance(ticker, dict):
                last_price_str = ticker.get("lastPrice")

            if not last_price_str:
                reason = "Price deviation check: no lastPrice in ticker, blocking entry for safety"
                self.logger.warning(reason)
                return ExecutionResult(
                    success=False,
                    signal=signal,
                    risk_check=RiskCheckResult(allowed=False, reason=reason),
                    error=reason,
                )

            last_price = float(last_price_str)
            if last_price <= 0:
                reason = f"Price deviation check: lastPrice={last_price} is invalid, blocking entry"
                self.logger.warning(reason)
                return ExecutionResult(
                    success=False,
                    signal=signal,
                    risk_check=RiskCheckResult(allowed=False, reason=reason),
                    error=reason,
                )

            # For market orders we don't have an explicit price, but we can
            # check that the market hasn't moved absurdly from recent data.
            # If signal carries a reference price, compare against it.
            ref_price = signal.reference_price
            if ref_price and ref_price > 0:
                deviation_pct = abs(last_price - ref_price) / ref_price * 100
                if deviation_pct > self.MAX_PRICE_DEVIATION_PCT:
                    reason = (
                        f"Price deviation guard: last_price={last_price:.4f} vs "
                        f"ref={ref_price:.4f} ({deviation_pct:.1f}% > {self.MAX_PRICE_DEVIATION_PCT}%)"
                    )
                    self.logger.warning(reason)
                    return ExecutionResult(
                        success=False,
                        signal=signal,
                        risk_check=RiskCheckResult(allowed=True, reason="passed"),
                        error=reason,
                    )

            # Also check for zero / absurdly low price (possible exchange glitch)
            if last_price < 0.0001:
                reason = f"Price deviation guard: last_price={last_price} is near zero"
                self.logger.warning(reason)
                return ExecutionResult(
                    success=False,
                    signal=signal,
                    risk_check=RiskCheckResult(allowed=True, reason="passed"),
                    error=reason,
                )

        except Exception as e:
            # Fail closed: if we can't verify price, reject the order for safety
            reason = f"Price deviation check failed (rejecting order for safety): {e}"
            self.logger.error(reason)
            return ExecutionResult(
                success=False,
                signal=signal,
                risk_check=RiskCheckResult(allowed=True, reason="passed"),
                error=reason,
            )

        return None

    # ==================== Callbacks ====================

    def on_execution(self, callback: Callable[[ExecutionResult], None]):
        """Register callback for execution results."""
        with self._callback_lock:
            self._execution_callbacks.append(callback)

    def _invoke_callbacks(self, result: ExecutionResult):
        """Invoke all registered callbacks (copy-under-lock for thread safety)."""
        with self._callback_lock:
            callbacks_copy = list(self._execution_callbacks)
        for callback in callbacks_copy:
            try:
                callback(result)
            except Exception as e:
                self.logger.error(f"Execution callback error: {e}")

    # ==================== Diagnostics ====================

    def get_status(self) -> dict:
        """Get executor status."""
        with self._pending_lock:
            pending_count = len(self._pending_orders)
        with self._callback_lock:
            callback_count = len(self._execution_callbacks)
        return {
            "use_ws_feedback": self._use_ws_feedback,
            "ws_connected": (
                self.realtime_state.is_private_ws_connected
                if self.realtime_state else False
            ),
            "pending_orders": pending_count,
            "callback_count": callback_count,
        }
