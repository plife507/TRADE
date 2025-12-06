"""
Order executor - handles trade execution through risk checks.

Flow: Signal → RiskManager.check() → ExchangeManager

Now supports WebSocket-fed order and execution tracking for faster feedback.

SAFETY GUARD RAILS:
- Validates trading mode consistency before executing any order
- Blocks TRADING_MODE=real with BYBIT_USE_DEMO=true (dangerous mismatch)
- Warns when paper trading on LIVE API
"""

import time
from typing import Optional, Callable, List
from dataclasses import dataclass, field
from datetime import datetime

from .exchange_manager import ExchangeManager, OrderResult
from .risk_manager import RiskManager, Signal, RiskCheckResult
from .position_manager import PositionManager, PortfolioSnapshot
from ..config.config import get_config, TradingMode
from ..utils.logger import get_logger


@dataclass
class ExecutionResult:
    """Complete result of an execution attempt."""
    success: bool
    signal: Signal
    risk_check: RiskCheckResult
    order_result: Optional[OrderResult] = None
    executed_size: Optional[float] = None
    error: Optional[str] = None
    timestamp: datetime = None
    source: str = "rest"  # "rest" or "websocket"
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.signal.symbol,
            "direction": self.signal.direction,
            "requested_size": self.signal.size_usd,
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
    size_usd: float
    submitted_at: float = field(default_factory=time.time)
    confirmed: bool = False
    filled: bool = False
    fill_price: Optional[float] = None
    error: Optional[str] = None


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
        
        # Callbacks
        self._execution_callbacks: List[Callable[[ExecutionResult], None]] = []
        
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
        
        self.logger.debug(f"Order {order_id} status: {order_data.status}")
    
    def _on_execution(self, exec_data):
        """Handle execution update from WebSocket."""
        order_id = exec_data.order_id
        
        # Check if this is a pending order we're tracking
        pending = self._pending_orders.get(order_id)
        if not pending:
            return
        
        # Update fill info
        pending.fill_price = exec_data.price
        pending.filled = True
        
        # Record the trade via position manager
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
        
        self.logger.info(f"Executing signal: {signal.symbol} {signal.direction} ${signal.size_usd:.2f}")
        
        # Get current portfolio state
        portfolio = self.position.get_snapshot()
        
        # Step 1: Risk check
        risk_result = self.risk.check(signal, portfolio)
        
        if not risk_result.allowed:
            self.logger.warning(f"Signal blocked by risk manager: {risk_result.reason}")
            result = ExecutionResult(
                success=False,
                signal=signal,
                risk_check=risk_result,
                error=f"Risk check failed: {risk_result.reason}"
            )
            self._invoke_callbacks(result)
            return result
        
        # Log any warnings
        for warning in risk_result.warnings:
            self.logger.warning(f"Risk warning: {warning}")
        
        # Determine execution size
        exec_size = risk_result.adjusted_size or signal.size_usd
        
        # Step 2: Execute order
        order_result = None
        
        try:
            if signal.direction == "LONG":
                order_result = self.exchange.market_buy(signal.symbol, exec_size)
            elif signal.direction == "SHORT":
                order_result = self.exchange.market_sell(signal.symbol, exec_size)
            elif signal.direction == "FLAT":
                order_result = self.exchange.close_position(signal.symbol)
            else:
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
            self._pending_orders[order_result.order_id] = PendingOrder(
                order_id=order_result.order_id,
                symbol=signal.symbol,
                direction=signal.direction,
                size_usd=exec_size,
            )
        
        # Step 3: Record trade (immediate REST feedback)
        if order_result and order_result.success:
            self.position.record_trade(
                symbol=signal.symbol,
                side="BUY" if signal.direction == "LONG" else "SELL",
                size_usd=exec_size,
                price=order_result.price or 0,
                order_id=order_result.order_id,
                strategy=signal.strategy,
            )
            
            self.logger.info(
                f"Order executed: {signal.symbol} {signal.direction} "
                f"${exec_size:.2f} @ {order_result.price}"
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
    
    def close_position(self, symbol: str, strategy: str = None) -> ExecutionResult:
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
            size_usd=0,  # Size determined by position
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
    
    def get_pending_order(self, order_id: str) -> Optional[PendingOrder]:
        """Get a pending order by ID."""
        return self._pending_orders.get(order_id)
    
    def get_all_pending_orders(self) -> dict[str, PendingOrder]:
        """Get all pending orders."""
        return dict(self._pending_orders)
    
    def cleanup_old_pending_orders(self, max_age_seconds: float = 300):
        """
        Clean up old pending orders.
        
        Args:
            max_age_seconds: Maximum age before removal
        """
        now = time.time()
        to_remove = []
        
        for order_id, pending in self._pending_orders.items():
            age = now - pending.submitted_at
            if age > max_age_seconds or pending.filled or pending.error:
                to_remove.append(order_id)
        
        for order_id in to_remove:
            del self._pending_orders[order_id]
        
        if to_remove:
            self.logger.debug(f"Cleaned up {len(to_remove)} old pending orders")
    
    def wait_for_fill(
        self,
        order_id: str,
        timeout: float = 10.0,
        poll_interval: float = 0.1,
    ) -> Optional[PendingOrder]:
        """
        Wait for an order to be filled via WebSocket.
        
        Args:
            order_id: Order ID to wait for
            timeout: Maximum wait time in seconds
            poll_interval: Polling interval in seconds
        
        Returns:
            PendingOrder if filled, None if timeout
        """
        pending = self._pending_orders.get(order_id)
        if not pending:
            return None
        
        start = time.time()
        while time.time() - start < timeout:
            if pending.filled or pending.error:
                return pending
            time.sleep(poll_interval)
        
        return pending if pending.filled else None
    
    # ==================== Callbacks ====================
    
    def on_execution(self, callback: Callable[[ExecutionResult], None]):
        """Register callback for execution results."""
        self._execution_callbacks.append(callback)
    
    def _invoke_callbacks(self, result: ExecutionResult):
        """Invoke all registered callbacks."""
        for callback in self._execution_callbacks:
            try:
                callback(result)
            except Exception as e:
                self.logger.error(f"Execution callback error: {e}")
    
    # ==================== Diagnostics ====================
    
    def get_status(self) -> dict:
        """Get executor status."""
        return {
            "use_ws_feedback": self._use_ws_feedback,
            "ws_connected": (
                self.realtime_state.is_private_ws_connected
                if self.realtime_state else False
            ),
            "pending_orders": len(self._pending_orders),
            "callback_count": len(self._execution_callbacks),
        }
