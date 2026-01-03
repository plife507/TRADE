"""
Safety module with panic button implementation.

Provides emergency controls to immediately flatten all positions
and halt trading operations.
"""

import threading
from collections.abc import Callable
from datetime import datetime

from ..utils.logger import get_logger


class PanicState:
    """Tracks panic/emergency state."""

    def __init__(self):
        self._triggered = False
        self._trigger_time: datetime | None = None
        self._reason: str | None = None
        self._lock = threading.Lock()
        self._callbacks: list[Callable] = []

    @property
    def is_triggered(self) -> bool:
        with self._lock:
            return self._triggered

    @property
    def trigger_time(self) -> datetime | None:
        with self._lock:
            return self._trigger_time

    @property
    def reason(self) -> str | None:
        with self._lock:
            return self._reason
    
    def trigger(self, reason: str = "Manual panic button"):
        """Trigger panic state."""
        with self._lock:
            self._triggered = True
            self._trigger_time = datetime.now()
            self._reason = reason
        
        # Execute callbacks
        for callback in self._callbacks:
            try:
                callback(reason)
            except Exception:
                pass
    
    def reset(self):
        """Reset panic state (use with caution)."""
        with self._lock:
            self._triggered = False
            self._trigger_time = None
            self._reason = None
    
    def add_callback(self, callback: Callable):
        """Add a callback to be called when panic is triggered."""
        self._callbacks.append(callback)


# Global panic state
_panic_state = PanicState()


def get_panic_state() -> PanicState:
    """Get the global panic state."""
    return _panic_state


def is_panic_triggered() -> bool:
    """Check if panic has been triggered."""
    return _panic_state.is_triggered


def panic_close_all(exchange_manager, reason: str = "Manual panic button") -> dict:
    """
    PANIC: Cancel all orders and close all positions immediately.
    
    This is the emergency stop function. It will:
    1. Cancel all open orders
    2. Close all positions with market orders
    3. Trigger global panic state to stop all trading loops
    
    Args:
        exchange_manager: ExchangeManager instance
        reason: Reason for triggering panic
    
    Returns:
        Dict with results of panic actions
    """
    logger = get_logger()
    logger.panic(f"PANIC TRIGGERED: {reason}")
    
    results = {
        "success": False,
        "reason": reason,
        "timestamp": datetime.now().isoformat(),
        "orders_cancelled": False,
        "positions_closed": [],
        "errors": [],
    }
    
    # Trigger global panic state
    _panic_state.trigger(reason)
    
    # Step 1: Cancel all open orders
    try:
        exchange_manager.cancel_all_orders()
        results["orders_cancelled"] = True
        logger.info("✓ All orders cancelled")
    except Exception as e:
        error = f"Failed to cancel orders: {e}"
        results["errors"].append(error)
        logger.error(error)
    
    # Step 2: Close all positions
    try:
        close_results = exchange_manager.close_all_positions()
        for result in close_results:
            if result.success:
                results["positions_closed"].append(result.symbol)
                logger.info(f"✓ Closed position: {result.symbol}")
            else:
                error = f"Failed to close {result.symbol}: {result.error}"
                results["errors"].append(error)
                logger.error(error)
    except Exception as e:
        error = f"Failed to close positions: {e}"
        results["errors"].append(error)
        logger.error(error)
    
    # Determine overall success
    results["success"] = results["orders_cancelled"] and len(results["errors"]) == 0
    
    if results["success"]:
        logger.panic("PANIC COMPLETE: All positions flattened, trading halted")
    else:
        logger.panic(f"PANIC INCOMPLETE: {len(results['errors'])} errors occurred")
    
    return results


def check_panic_and_halt() -> bool:
    """
    Check if panic is triggered and should halt operations.
    
    Call this at the start of any trading loop iteration.
    
    Returns:
        True if panic is triggered and operations should halt
    """
    if _panic_state.is_triggered:
        logger = get_logger()
        logger.warning(f"HALTED: Panic triggered at {_panic_state.trigger_time} - {_panic_state.reason}")
        return True
    return False


def reset_panic(confirm: str = None) -> bool:
    """
    Reset panic state to allow trading to resume.
    
    Args:
        confirm: Must be "RESET" to confirm
    
    Returns:
        True if reset successful
    """
    if confirm != "RESET":
        logger = get_logger()
        logger.warning("Panic reset requires confirmation: reset_panic('RESET')")
        return False
    
    logger = get_logger()
    logger.warning("PANIC STATE RESET - Trading can resume")
    _panic_state.reset()
    return True


class SafetyChecks:
    """
    Pre-trade safety checks.
    
    These are additional safety validations that run before
    any trade is executed.
    """
    
    def __init__(self, exchange_manager, config):
        self.exchange_manager = exchange_manager
        self.config = config
        self.logger = get_logger()
        
        # Track daily losses
        self._daily_loss = 0.0
        self._last_reset = datetime.now().date()
    
    def _reset_daily_if_needed(self):
        """Reset daily counters at midnight."""
        today = datetime.now().date()
        if today > self._last_reset:
            self._daily_loss = 0.0
            self._last_reset = today
    
    def record_loss(self, amount: float):
        """Record a realized loss."""
        self._reset_daily_if_needed()
        if amount < 0:
            self._daily_loss += abs(amount)
    
    def check_daily_loss_limit(self) -> tuple[bool, str]:
        """Check if daily loss limit has been reached."""
        self._reset_daily_if_needed()
        
        limit = self.config.risk.max_daily_loss_usd
        if self._daily_loss >= limit:
            return False, f"Daily loss limit reached: ${self._daily_loss:.2f} >= ${limit:.2f}"
        return True, ""
    
    def check_min_balance(self) -> tuple[bool, str]:
        """Check if account has minimum required balance."""
        try:
            balance = self.exchange_manager.get_balance()
            available = balance.get("available", 0)
            min_balance = self.config.risk.min_balance_usd
            
            if available < min_balance:
                return False, f"Balance too low: ${available:.2f} < ${min_balance:.2f}"
            return True, ""
        except Exception as e:
            return False, f"Failed to check balance: {e}"
    
    def check_max_exposure(self, additional_usd: float = 0) -> tuple[bool, str]:
        """Check if total exposure would exceed limit."""
        try:
            current = self.exchange_manager.get_total_exposure()
            limit = self.config.risk.max_total_exposure_usd
            
            if current + additional_usd > limit:
                return False, f"Exposure limit exceeded: ${current + additional_usd:.2f} > ${limit:.2f}"
            return True, ""
        except Exception as e:
            return False, f"Failed to check exposure: {e}"
    
    def run_all_checks(self, additional_exposure: float = 0) -> tuple[bool, list[str]]:
        """
        Run all safety checks.
        
        Args:
            additional_exposure: Additional USD exposure being added
        
        Returns:
            Tuple of (all_passed, list of failure reasons)
        """
        failures = []
        
        # Check panic state first
        if is_panic_triggered():
            failures.append("Panic state is active - trading halted")
        
        # Daily loss limit
        ok, reason = self.check_daily_loss_limit()
        if not ok:
            failures.append(reason)
        
        # Minimum balance
        ok, reason = self.check_min_balance()
        if not ok:
            failures.append(reason)
        
        # Maximum exposure
        ok, reason = self.check_max_exposure(additional_exposure)
        if not ok:
            failures.append(reason)
        
        return len(failures) == 0, failures

