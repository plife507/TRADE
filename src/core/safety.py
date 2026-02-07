"""
Safety module with panic button implementation.

Provides emergency controls to immediately flatten all positions
and halt trading operations.

Also provides the shared DailyLossTracker used by both RiskManager
and SafetyChecks to avoid duplicate/divergent daily loss tracking.
"""

import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone

from ..utils.logger import get_logger


# ==============================================================================
# Shared Daily Loss Tracker
# ==============================================================================

class DailyLossTracker:
    """
    Thread-safe daily loss tracker shared between RiskManager and SafetyChecks.

    Resets at midnight. Tracks cumulative realized PnL for the day.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._daily_pnl: float = 0.0
        self._daily_trades: int = 0
        self._last_reset = datetime.now(timezone.utc).date()

    def _reset_if_needed(self):
        """Reset counters if a new day has started. Must hold _lock."""
        today = datetime.now(timezone.utc).date()
        if today > self._last_reset:
            self._daily_pnl = 0.0
            self._daily_trades = 0
            self._last_reset = today

    def record_pnl(self, amount: float):
        """Record realized PnL (positive or negative)."""
        with self._lock:
            self._reset_if_needed()
            self._daily_pnl += amount
            self._daily_trades += 1

    def record_loss(self, amount: float):
        """Record a realized loss (amount should be negative or will be negated)."""
        with self._lock:
            self._reset_if_needed()
            if amount < 0:
                self._daily_pnl += amount

    @property
    def daily_pnl(self) -> float:
        with self._lock:
            self._reset_if_needed()
            return self._daily_pnl

    @property
    def daily_trades(self) -> int:
        with self._lock:
            self._reset_if_needed()
            return self._daily_trades

    def check_limit(self, max_daily_loss_usd: float) -> tuple[bool, str]:
        """Check if daily loss limit has been reached."""
        with self._lock:
            self._reset_if_needed()
            if self._daily_pnl <= -max_daily_loss_usd:
                return False, f"Daily loss limit reached: ${self._daily_pnl:.2f} >= -${max_daily_loss_usd:.2f}"
            return True, ""

    def seed_from_exchange(self, exchange_manager, symbol: str | None = None) -> None:
        """
        Seed daily PnL from Bybit closed PnL records for today.

        Should be called once at startup so the tracker reflects any trades
        already executed today before this process started.

        Args:
            exchange_manager: ExchangeManager instance
            symbol: Optional symbol filter
        """
        logger = get_logger()
        try:
            from ..utils.time_range import TimeRange

            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0,
            )
            start_ms = int(today_start.timestamp() * 1000)
            end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            time_range = TimeRange(
                start_ms=start_ms,
                end_ms=end_ms,
                label="daily_seed",
                endpoint_type="closed_pnl",
            )

            records = exchange_manager.get_closed_pnl(
                time_range=time_range, symbol=symbol,
            )
            total = sum(float(r.get("closedPnl", 0)) for r in records)

            with self._lock:
                self._daily_pnl = total
                self._daily_trades = len(records)

            logger.info(
                f"DailyLossTracker seeded from exchange: "
                f"pnl=${total:.2f}, trades={len(records)}"
            )
        except Exception as e:
            logger.error(
                f"Failed to seed daily PnL from exchange: {e}. "
                "Daily loss tracker starts at $0 -- trades from earlier today are NOT counted."
            )


_daily_loss_tracker: DailyLossTracker | None = None
_dlt_lock = threading.Lock()


def get_daily_loss_tracker() -> DailyLossTracker:
    """Get the global shared DailyLossTracker singleton."""
    global _daily_loss_tracker
    if _daily_loss_tracker is None:
        with _dlt_lock:
            if _daily_loss_tracker is None:
                _daily_loss_tracker = DailyLossTracker()
    return _daily_loss_tracker


# G5.5: Retry settings for panic operations
PANIC_RETRY_ATTEMPTS = 3
PANIC_RETRY_DELAY = 0.5  # seconds


class PanicState:
    """Tracks panic/emergency state."""

    def __init__(self):
        self._triggered = False
        self._trigger_time: datetime | None = None
        self._reason: str | None = None
        self._lock = threading.Lock()
        self._callback_lock = threading.Lock()  # Protects _callbacks list
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

        # Execute callbacks (copy-under-lock for thread safety)
        with self._callback_lock:
            callbacks_copy = list(self._callbacks)
        for callback in callbacks_copy:
            try:
                callback(reason)
            except (RuntimeError, TypeError, ValueError) as e:
                # BUG-004 fix: Specific exceptions for panic callbacks
                # Log but continue executing other callbacks - panic must complete
                import logging
                logging.getLogger(__name__).error(f"Panic callback failed: {e}")

    def reset(self):
        """Reset panic state (use with caution)."""
        with self._lock:
            self._triggered = False
            self._trigger_time = None
            self._reason = None

    def add_callback(self, callback: Callable):
        """Add a callback to be called when panic is triggered."""
        with self._callback_lock:
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
    
    # Step 1: Cancel all open orders (with retry)
    for attempt in range(1, PANIC_RETRY_ATTEMPTS + 1):
        try:
            exchange_manager.cancel_all_orders()
            results["orders_cancelled"] = True
            logger.info("✓ All orders cancelled")
            break
        except Exception as e:
            if attempt == PANIC_RETRY_ATTEMPTS:
                error = f"Failed to cancel orders after {attempt} attempts: {e}"
                results["errors"].append(error)
                logger.error(error)
            else:
                logger.warning(f"Cancel orders attempt {attempt} failed, retrying: {e}")
                time.sleep(PANIC_RETRY_DELAY)

    # Step 2: Close all positions (with retry per position)
    try:
        close_results = exchange_manager.close_all_positions()
        for result in close_results:
            if result.success:
                results["positions_closed"].append(result.symbol)
                logger.info(f"✓ Closed position: {result.symbol}")
            else:
                # Retry failed position closes
                closed = False
                for retry in range(1, PANIC_RETRY_ATTEMPTS + 1):
                    try:
                        logger.warning(f"Retrying close {result.symbol} (attempt {retry})")
                        time.sleep(PANIC_RETRY_DELAY)
                        retry_result = exchange_manager.close_position(result.symbol)
                        if retry_result.success:
                            results["positions_closed"].append(result.symbol)
                            logger.info(f"✓ Closed position: {result.symbol} (retry {retry})")
                            closed = True
                            break
                    except Exception as retry_e:
                        logger.warning(f"Retry {retry} failed: {retry_e}")

                if not closed:
                    error = f"Failed to close {result.symbol}: {result.error}"
                    results["errors"].append(error)
                    logger.error(error)
    except Exception as e:
        error = f"Failed to close positions: {e}"
        results["errors"].append(error)
        logger.error(error)

    # Verify positions are actually closed
    try:
        remaining = exchange_manager.get_all_positions()
        open_positions = [p for p in remaining if hasattr(p, 'size') and p.size > 0]
        if open_positions:
            for pos in open_positions:
                results["errors"].append(f"Position still open: {pos.symbol} size={pos.size}")
            logger.error(f"PANIC INCOMPLETE: {len(open_positions)} position(s) still open after close attempts")
    except Exception as e:
        results["errors"].append(f"Failed to verify position closure: {e}")

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

        # Use shared daily loss tracker (same instance as RiskManager)
        self._tracker = get_daily_loss_tracker()

    def record_loss(self, amount: float):
        """Record a realized loss."""
        self._tracker.record_loss(amount)

    def check_daily_loss_limit(self) -> tuple[bool, str]:
        """Check if daily loss limit has been reached."""
        limit = self.config.risk.max_daily_loss_usd
        return self._tracker.check_limit(limit)
    
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

