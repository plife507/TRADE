"""
Rate limiter for API calls.
Implements token bucket algorithm with separate limits for public and private endpoints.
"""

from __future__ import annotations

import time
import threading
from collections import deque


class RateLimiter:
    """
    Token bucket rate limiter.
    
    Features:
    - Configurable max calls per time period
    - Thread-safe
    - Blocking wait when limit reached
    - Optional burst allowance
    """
    
    def __init__(self, max_calls: int, period: float = 1.0, burst: int | None = None):
        """
        Initialize rate limiter.
        
        Args:
            max_calls: Maximum number of calls allowed per period
            period: Time period in seconds (default 1.0)
            burst: Maximum burst size (default same as max_calls)
        """
        self.max_calls = max_calls
        self.period = period
        self.burst = burst or max_calls
        
        self._lock = threading.Lock()
        self._call_times: deque = deque()
    
    def acquire(self, timeout: float | None = None) -> bool:
        """
        Acquire permission to make an API call.
        Blocks until a slot is available or timeout is reached.
        
        Args:
            timeout: Maximum time to wait in seconds (None = wait forever)
        
        Returns:
            True if acquired, False if timed out
        """
        start_time = time.time()
        
        while True:
            with self._lock:
                now = time.time()
                
                # Remove expired timestamps
                cutoff = now - self.period
                while self._call_times and self._call_times[0] < cutoff:
                    self._call_times.popleft()
                
                # Check if we can make a call
                if len(self._call_times) < self.max_calls:
                    self._call_times.append(now)
                    return True
                
                # Calculate wait time
                if self._call_times:
                    wait_time = self._call_times[0] + self.period - now
                else:
                    wait_time = 0.01  # Small sleep if queue is somehow empty
            
            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    return False
                wait_time = min(wait_time, timeout - elapsed)
            
            # Wait before retrying
            time.sleep(min(wait_time + 0.001, 0.1))  # Max 100ms sleep at a time
    
    def try_acquire(self) -> bool:
        """
        Try to acquire permission without blocking.
        
        Returns:
            True if acquired, False if rate limited
        """
        with self._lock:
            now = time.time()
            
            # Remove expired timestamps
            cutoff = now - self.period
            while self._call_times and self._call_times[0] < cutoff:
                self._call_times.popleft()
            
            # Check if we can make a call
            if len(self._call_times) < self.max_calls:
                self._call_times.append(now)
                return True
            
            return False
    
    def wait_time(self) -> float:
        """
        Get estimated wait time until next available slot.
        
        Returns:
            Estimated seconds until a slot is available (0 if available now)
        """
        with self._lock:
            now = time.time()
            
            # Remove expired timestamps
            cutoff = now - self.period
            while self._call_times and self._call_times[0] < cutoff:
                self._call_times.popleft()
            
            if len(self._call_times) < self.max_calls:
                return 0.0
            
            if self._call_times:
                return max(0, self._call_times[0] + self.period - now)
            
            return 0.0
    
    def reset(self):
        """Reset the rate limiter (clear all timestamps)."""
        with self._lock:
            self._call_times.clear()
    
    @property
    def available_slots(self) -> int:
        """Get number of available slots right now."""
        with self._lock:
            now = time.time()
            cutoff = now - self.period
            while self._call_times and self._call_times[0] < cutoff:
                self._call_times.popleft()
            return max(0, self.max_calls - len(self._call_times))


class MultiRateLimiter:
    """
    Manages multiple rate limiters for different endpoint categories.
    
    Bybit has different limits:
    - Public endpoints: 120 RPS per IP
    - Private endpoints: 50 RPS per API key
    """
    
    def __init__(self):
        self._limiters: dict[str, RateLimiter] = {}
        self._lock = threading.Lock()
    
    def add_limiter(self, name: str, max_calls: int, period: float = 1.0) -> RateLimiter:
        """Add a new rate limiter category."""
        with self._lock:
            limiter = RateLimiter(max_calls, period)
            self._limiters[name] = limiter
            return limiter
    
    def get_limiter(self, name: str) -> RateLimiter | None:
        """Get a rate limiter by name."""
        return self._limiters.get(name)
    
    def acquire(self, name: str, timeout: float | None = None) -> bool:
        """Acquire from a specific limiter."""
        limiter = self._limiters.get(name)
        if limiter:
            return limiter.acquire(timeout)
        return True  # No limiter = no limit
    
    def try_acquire(self, name: str) -> bool:
        """Try to acquire from a specific limiter without blocking."""
        limiter = self._limiters.get(name)
        if limiter:
            return limiter.try_acquire()
        return True


# Pre-configured limiters for Bybit
def create_bybit_limiters() -> MultiRateLimiter:
    """
    Create rate limiters configured for Bybit V5 API limits.
    
    Bybit V5 Rate Limits (per docs):
    - IP Limit: 600 requests per 5-second window (120/s effective)
    - Trade endpoints: 10/s for create/amend/cancel orders
    - Position/Account endpoints: 50/s
    - Public market data: shared IP limit
    
    We use conservative values to leave buffer room.
    """
    limiters = MultiRateLimiter()
    
    # IP-based limit (600 per 5s = 120/s, we use 100/s for buffer)
    # Applied to public endpoints (market data)
    limiters.add_limiter("public", max_calls=100, period=1.0)
    
    # Private account/position endpoints - 50/s per UID, we use 40/s
    limiters.add_limiter("private", max_calls=40, period=1.0)
    
    # Order endpoints (create/amend/cancel) - 10/s per symbol, we use 8/s
    limiters.add_limiter("orders", max_calls=8, period=1.0)
    
    # Batch order endpoints - separate limit, 10/s but counts per order in batch
    limiters.add_limiter("batch_orders", max_calls=10, period=1.0)
    
    # Position management (leverage, margin mode) - 10/s
    limiters.add_limiter("position_mgmt", max_calls=8, period=1.0)
    
    return limiters

