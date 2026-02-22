"""
Global Risk View - Centralized risk analysis for the trading bot.

This module provides a comprehensive, real-time view of portfolio risk
that can be consumed by risk agents, the CLI, and the core trading logic.

Design principles:
- Only reads from RealtimeState (no direct WebSocket/REST calls)
- Provides computed risk metrics beyond raw data
- Supports caching with configurable refresh intervals
- Thread-safe for concurrent access
- JSON-serializable output for agent consumption
"""

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..config.config import Config, get_config
from ..data.realtime_state import (
    RealtimeState,
    get_realtime_state,
    PortfolioRiskSnapshot,
    AccountMetrics,
    PositionData,
)
from ..utils.logger import get_logger


class RiskVeto(Enum):
    """Reasons for vetoing a trade."""
    NONE = "none"
    ACCOUNT_HIGH_RISK = "account_high_risk"
    MARGIN_EXCEEDED = "margin_exceeded"
    LEVERAGE_EXCEEDED = "leverage_exceeded"
    POSITION_LIMIT = "position_limit"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    EXPOSURE_LIMIT = "exposure_limit"
    LIQUIDATING_POSITION = "liquidating_position"
    REDUCE_ONLY = "reduce_only"


@dataclass
class RiskDecision:
    """
    Result of a pre-trade risk check.

    Indicates whether a trade should proceed and provides
    reasons if it should be blocked.
    """
    allowed: bool
    veto_reason: RiskVeto = RiskVeto.NONE
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def allow(cls, message: str = "") -> 'RiskDecision':
        """Create an allowing decision."""
        return cls(allowed=True, message=message or "Trade allowed")
    
    @classmethod
    def deny(cls, reason: RiskVeto, message: str, **details) -> 'RiskDecision':
        """Create a denying decision."""
        return cls(
            allowed=False,
            veto_reason=reason,
            message=message,
            details=details,
        )


@dataclass
class RiskLimits:
    """
    Risk limits configuration.

    These are the thresholds that trigger risk vetoes.
    All values should come from config/defaults.yml or Play YAML via from_config().
    Dataclass defaults are conservative fallbacks only.
    """
    # Account-level limits
    max_account_im_rate: float = 0.8
    max_account_mm_rate: float = 0.9
    min_available_balance_usd: float = 100.0

    # Position-level limits (override via config or Play)
    max_leverage: float = 1.0
    max_position_size_usdt: float = 50.0
    max_total_exposure_usd: float = 200.0
    max_positions: int = 10

    # Risk thresholds
    min_liq_distance_pct: float = 5.0
    max_single_asset_pct: float = 50.0

    # Daily limits
    max_daily_loss_usd: float = 20.0
    
    @classmethod
    def from_config(cls, config: Config) -> 'RiskLimits':
        """Load limits from config.

        Note: RiskConfig values are intentionally conservative LIVE SAFETY caps,
        deliberately stricter than backtest defaults in defaults.yml.
        Fields not present in RiskConfig use conservative dataclass defaults.
        """
        return cls(
            max_leverage=float(config.risk.max_leverage),
            max_position_size_usdt=float(config.risk.max_position_size_usdt),
            max_total_exposure_usd=float(config.risk.max_total_exposure_usd),
            max_daily_loss_usd=float(config.risk.max_daily_loss_usd),
            min_available_balance_usd=float(config.risk.min_balance_usd),
            # max_account_im_rate, max_account_mm_rate, max_positions,
            # min_liq_distance_pct, max_single_asset_pct: use conservative
            # dataclass defaults (not in RiskConfig — live safety hardcodes)
        )


class GlobalRiskView:
    """
    Centralized global risk analysis service.
    
    This service provides:
    - Portfolio-wide risk snapshots
    - Pre-trade risk checks (veto/allow decisions)
    - Risk limit configuration
    - Cached snapshots with staleness detection
    
    Usage:
        risk_view = GlobalRiskView(realtime_state, config)
        
        # Get current risk snapshot
        snapshot = risk_view.build_snapshot()
        print(f"Margin utilization: {snapshot.account_im_rate:.2%}")
        
        # Check if a trade should be allowed
        decision = risk_view.check_pre_trade(signal)
        if not decision.allowed:
            print(f"Trade vetoed: {decision.message}")
    """
    
    def __init__(
        self,
        realtime_state: RealtimeState | None = None,
        config: Config | None = None,
    ):
        """
        Initialize GlobalRiskView.
        
        Args:
            realtime_state: RealtimeState instance (uses singleton if None)
            config: Config instance (uses singleton if None)
        """
        self.state = realtime_state or get_realtime_state()
        self.config = config or get_config()
        self.logger = get_logger()
        
        # Risk limits from config
        self.limits = RiskLimits.from_config(self.config)
        
        # Caching
        self._cache_lock = threading.Lock()
        self._cached_snapshot: PortfolioRiskSnapshot | None = None
        self._cache_timestamp: float = 0.0
        self._min_cache_interval: float = 1.0  # Minimum seconds between rebuilds

        # H-S2: Delegate daily PnL to canonical DailyLossTracker (single source of truth)
        from ..core.safety import get_daily_loss_tracker
        self._daily_tracker = get_daily_loss_tracker()

        # High-water mark tracking
        self._equity_high_water_mark: float = 0.0
        self._hwm_timestamp: float = 0.0

        # G1-4: WebSocket health tracking for fail-closed behavior
        self._ws_unhealthy_since: float | None = None
        self._ws_unhealthy_threshold_sec: float = 30.0  # Block trading after 30s unhealthy
    
    def build_snapshot(self, force_refresh: bool = False) -> PortfolioRiskSnapshot:
        """
        Build or return cached portfolio risk snapshot.
        
        Args:
            force_refresh: Force rebuild even if cache is fresh
        
        Returns:
            Current PortfolioRiskSnapshot
        """
        with self._cache_lock:
            now = time.time()
            
            # Check if cached snapshot is still valid
            if (
                not force_refresh
                and self._cached_snapshot
                and (now - self._cache_timestamp) < self._min_cache_interval
            ):
                return self._cached_snapshot
            
            # Build fresh snapshot from WebSocket state
            snapshot = self.state.build_portfolio_snapshot(self.config)
            
            # Fallback to REST if WebSocket balance data is missing/stale
            if snapshot.total_wallet_balance == 0 and snapshot.total_equity == 0:
                snapshot = self._enrich_snapshot_from_rest(snapshot)
            
            # Update high-water mark
            if snapshot.total_equity > self._equity_high_water_mark:
                self._equity_high_water_mark = snapshot.total_equity
                self._hwm_timestamp = now
            
            # Cache it
            self._cached_snapshot = snapshot
            self._cache_timestamp = now
            
            return snapshot
    
    def _enrich_snapshot_from_rest(self, snapshot: PortfolioRiskSnapshot) -> PortfolioRiskSnapshot:
        """
        Fallback: Enrich snapshot with REST API data if WebSocket data is missing.
        
        This ensures risk checks work even before WebSocket receives wallet updates.
        """
        try:
            from ..core.exchange_manager import ExchangeManager
            exchange = ExchangeManager()
            balance = exchange.get_balance()
            
            if balance:
                snapshot.total_wallet_balance = balance.get('total', 0)
                snapshot.total_available_balance = balance.get('available', 0)
                snapshot.total_equity = balance.get('total', 0)  # Approximate
                self.logger.debug(f"Risk snapshot enriched from REST: balance=${snapshot.total_wallet_balance:.2f}")
        except Exception as e:
            self.logger.warning(f"Failed to enrich risk snapshot from REST: {e}")
        
        return snapshot
    
    def _check_ws_health(self) -> tuple[bool, str]:
        """
        G1-4: Check WebSocket health for fail-closed behavior.

        Returns:
            Tuple of (is_healthy, reason_if_unhealthy)
        """
        now = time.time()

        try:
            # Check if WebSocket is connected and receiving data
            ws_healthy = self.state.is_websocket_healthy()

            if ws_healthy:
                # Reset unhealthy timer
                self._ws_unhealthy_since = None
                return True, ""
            else:
                # Track how long we've been unhealthy
                if self._ws_unhealthy_since is None:
                    self._ws_unhealthy_since = now
                    # Log diagnostic detail on first unhealthy detection
                    priv = self.state.is_private_ws_connected
                    metrics_stale = self.state.is_account_metrics_stale(30.0)
                    wallet_stale = self.state.is_wallet_stale(max_age_seconds=30.0)
                    self.logger.warning(
                        f"WS became unhealthy: private_connected={priv} "
                        f"metrics_stale={metrics_stale} wallet_stale={wallet_stale}"
                    )

                unhealthy_duration = now - self._ws_unhealthy_since

                if unhealthy_duration > self._ws_unhealthy_threshold_sec:
                    return False, (
                        f"WebSocket unhealthy for {unhealthy_duration:.1f}s "
                        f"(threshold: {self._ws_unhealthy_threshold_sec}s). "
                        "Blocking trades for safety."
                    )
                else:
                    # Still within grace period
                    return True, ""

        except Exception as e:
            # Fail-closed: if we can't check health, block trading
            self.logger.warning(f"Could not check WebSocket health: {e}")
            if self._ws_unhealthy_since is None:
                self._ws_unhealthy_since = now
            return False, f"WebSocket health check failed: {e}. Blocking trades for safety."

    def check_pre_trade(
        self,
        signal: Any | None = None,
        symbol: str | None = None,
        side: str | None = None,
        size_usdt: float | None = None,
    ) -> RiskDecision:
        """
        Check if a trade should be allowed based on current risk state.

        This is a global-level check that supplements per-trade checks
        in RiskManager. It focuses on account-wide risk metrics.

        G1-4: Implements fail-closed behavior - blocks trading if WebSocket
        is unhealthy for > 30 seconds.

        Args:
            signal: Trading signal (optional, for signal-based checks)
            symbol: Symbol to trade (optional)
            side: "Buy" or "Sell" (optional)
            size_usdt: Size in USDT (optional)

        Returns:
            RiskDecision indicating if trade is allowed
        """
        # G1-4: Check WebSocket health first (fail-closed)
        ws_healthy, ws_reason = self._check_ws_health()
        if not ws_healthy:
            return RiskDecision.deny(
                RiskVeto.ACCOUNT_HIGH_RISK,
                ws_reason,
                websocket_unhealthy=True,
                unhealthy_since=self._ws_unhealthy_since,
            )

        snapshot = self.build_snapshot()

        # Check 1: Account high risk (liquidation danger)
        if snapshot.has_liquidating_positions:
            return RiskDecision.deny(
                RiskVeto.LIQUIDATING_POSITION,
                "Position currently being liquidated - no new trades allowed",
                liquidation_risk_level=snapshot.liquidation_risk_level,
            )
        
        if snapshot.account_mm_rate > self.limits.max_account_mm_rate:
            return RiskDecision.deny(
                RiskVeto.ACCOUNT_HIGH_RISK,
                f"Account maintenance margin rate too high: {snapshot.account_mm_rate:.1%}",
                account_mm_rate=snapshot.account_mm_rate,
                limit=self.limits.max_account_mm_rate,
            )
        
        # Check 2: Margin utilization
        if snapshot.account_im_rate > self.limits.max_account_im_rate:
            return RiskDecision.deny(
                RiskVeto.MARGIN_EXCEEDED,
                f"Account initial margin rate exceeded: {snapshot.account_im_rate:.1%}",
                account_im_rate=snapshot.account_im_rate,
                limit=self.limits.max_account_im_rate,
            )
        
        # Check 3: Available balance
        if snapshot.total_available_balance <= self.limits.min_available_balance_usd:
            return RiskDecision.deny(
                RiskVeto.MARGIN_EXCEEDED,
                f"Insufficient available balance: ${snapshot.total_available_balance:.2f}",
                available_balance=snapshot.total_available_balance,
                limit=self.limits.min_available_balance_usd,
            )
        
        # Check 4: Position count
        if snapshot.total_position_count >= self.limits.max_positions:
            return RiskDecision.deny(
                RiskVeto.POSITION_LIMIT,
                f"Maximum positions reached: {snapshot.total_position_count}",
                position_count=snapshot.total_position_count,
                limit=self.limits.max_positions,
            )
        
        # Check 5: Total exposure
        if snapshot.total_notional_usd >= self.limits.max_total_exposure_usd:
            return RiskDecision.deny(
                RiskVeto.EXPOSURE_LIMIT,
                f"Maximum exposure reached: ${snapshot.total_notional_usd:.2f}",
                total_exposure=snapshot.total_notional_usd,
                limit=self.limits.max_total_exposure_usd,
            )
        
        # Check 6: Daily loss limit (reads from canonical DailyLossTracker)
        daily_pnl = self._daily_tracker.daily_pnl
        if daily_pnl <= -self.limits.max_daily_loss_usd:
            return RiskDecision.deny(
                RiskVeto.DAILY_LOSS_LIMIT,
                f"Daily loss limit reached: ${daily_pnl:.2f}",
                daily_pnl=daily_pnl,
                limit=self.limits.max_daily_loss_usd,
            )
        
        # Check 7: Position-specific checks (if symbol provided)
        if symbol:
            position = self.state.get_position(symbol)
            if position and position.is_reduce_only:
                return RiskDecision.deny(
                    RiskVeto.REDUCE_ONLY,
                    f"{symbol} is in reduce-only mode - only position reduction allowed",
                    symbol=symbol,
                )
        
        # Check 8: Proposed trade size (if provided)
        if size_usdt and size_usdt > self.limits.max_position_size_usdt:
            return RiskDecision.deny(
                RiskVeto.POSITION_LIMIT,
                f"Trade size exceeds limit: ${size_usdt:.2f}",
                size_usdt=size_usdt,
                limit=self.limits.max_position_size_usdt,
            )
        
        # All checks passed
        return RiskDecision.allow(
            f"Trade allowed (IM rate: {snapshot.account_im_rate:.1%}, "
            f"MM rate: {snapshot.account_mm_rate:.1%})"
        )
    
    def get_limits(self) -> dict[str, Any]:
        """Get current risk limits as a dict."""
        return {
            "max_account_im_rate": self.limits.max_account_im_rate,
            "max_account_mm_rate": self.limits.max_account_mm_rate,
            "min_available_balance_usd": self.limits.min_available_balance_usd,
            "max_leverage": self.limits.max_leverage,
            "max_position_size_usdt": self.limits.max_position_size_usdt,
            "max_total_exposure_usd": self.limits.max_total_exposure_usd,
            "max_positions": self.limits.max_positions,
            "min_liq_distance_pct": self.limits.min_liq_distance_pct,
            "max_single_asset_pct": self.limits.max_single_asset_pct,
            "max_daily_loss_usd": self.limits.max_daily_loss_usd,
        }
    
    def update_limits(self, **kwargs):
        """Update risk limits dynamically."""
        for key, value in kwargs.items():
            if hasattr(self.limits, key):
                setattr(self.limits, key, value)
                self.logger.info(f"Updated risk limit: {key} = {value}")
    
    def get_equity_drawdown(self) -> dict[str, float]:
        """Get current drawdown from high-water mark."""
        snapshot = self.build_snapshot()
        
        if self._equity_high_water_mark <= 0:
            return {
                "current_equity": snapshot.total_equity,
                "high_water_mark": snapshot.total_equity,
                "drawdown_usd": 0.0,
                "drawdown_pct": 0.0,
            }
        
        drawdown_usd = self._equity_high_water_mark - snapshot.total_equity
        drawdown_pct = (drawdown_usd / self._equity_high_water_mark) * 100 if self._equity_high_water_mark else 0
        
        return {
            "current_equity": snapshot.total_equity,
            "high_water_mark": self._equity_high_water_mark,
            "drawdown_usd": drawdown_usd,
            "drawdown_pct": drawdown_pct,
            "hwm_timestamp": self._hwm_timestamp,
        }
    
    def record_realized_pnl(self, pnl: float):
        """
        Record realized PnL for daily tracking.

        H-S2: Delegates to canonical DailyLossTracker. RiskManager already
        records there too, so this is a no-op if called from RiskManager.
        Kept for direct callers that bypass RiskManager.
        """
        self._daily_tracker.record_pnl(pnl)

    def get_daily_pnl(self) -> dict[str, Any]:
        """Get daily realized PnL info."""
        pnl = self._daily_tracker.daily_pnl
        return {
            "daily_realized_pnl": pnl,
            "daily_loss_limit": self.limits.max_daily_loss_usd,
            "remaining_loss_budget": self.limits.max_daily_loss_usd + pnl,
        }
    
    def get_risk_summary(self) -> dict[str, Any]:
        """
        Get a comprehensive risk summary for CLI or agent display.
        """
        snapshot = self.build_snapshot()
        drawdown = self.get_equity_drawdown()
        daily_pnl = self.get_daily_pnl()
        
        return {
            "snapshot": snapshot.to_dict(),
            "drawdown": drawdown,
            "daily_pnl": daily_pnl,
            "limits": self.get_limits(),
            "cached_at": self._cache_timestamp,
        }


# ==============================================================================
# Singleton Instance
# ==============================================================================

_global_risk_view: GlobalRiskView | None = None
_grv_lock = threading.Lock()


def get_global_risk_view(
    realtime_state: RealtimeState | None = None,
    config: Config | None = None,
) -> GlobalRiskView:
    """
    Get the global GlobalRiskView singleton.
    
    Creates instance on first call.
    """
    global _global_risk_view
    
    with _grv_lock:
        if _global_risk_view is None:
            _global_risk_view = GlobalRiskView(realtime_state, config)
        return _global_risk_view


def reset_global_risk_view():
    """Reset the global risk view singleton (for testing)."""
    global _global_risk_view
    
    with _grv_lock:
        _global_risk_view = None

