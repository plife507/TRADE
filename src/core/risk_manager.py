"""
Risk manager - pure rules-based risk controls.

All trades must pass through risk manager checks before execution.
No AI or ML - deterministic rules only.

Optionally integrates with GlobalRiskView for account-level risk checks
when WebSocket data is available.
"""

from typing import Any
from dataclasses import dataclass
from datetime import datetime

from ..config.config import get_config, RiskConfig
from ..utils.logger import get_logger
from .position_manager import PortfolioSnapshot


@dataclass
class Signal:
    """Trading signal from a strategy."""
    symbol: str
    direction: str  # "LONG", "SHORT", "FLAT"
    size_usdt: float  # Position size in USDT
    strategy: str
    confidence: float = 1.0
    metadata: dict | None = None

    def __post_init__(self):
        self.metadata = self.metadata or {}


@dataclass
class RiskCheckResult:
    """Result of risk check."""
    allowed: bool
    reason: str
    adjusted_size: float | None = None
    warnings: list[str] | None = None

    def __post_init__(self):
        self.warnings = self.warnings or []


class RiskManager:
    """
    Rule-based risk manager.
    
    Enforces:
    - Maximum leverage
    - Maximum position size per symbol
    - Maximum total exposure
    - Daily loss limits
    - Minimum balance requirements
    
    All rules are deterministic with no AI/ML.
    
    Optionally integrates with GlobalRiskView for account-level risk checks
    when WebSocket-based realtime state is available. This provides:
    - Account-wide margin utilization checks
    - Liquidation risk monitoring
    - Position status checks (liquidating, ADL, reduce-only)
    """
    
    def __init__(
        self,
        config: RiskConfig | None = None,
        enable_global_risk: bool = True,
        exchange_manager: Any | None = None,
    ):
        self.config = config or get_config().risk
        self.logger = get_logger()

        # Daily tracking
        self._daily_pnl = 0.0
        self._daily_trades = 0
        self._last_reset = datetime.now().date()

        # G0.3: Reuse exchange_manager instead of creating fresh instances
        self._exchange_manager = exchange_manager

        # Global risk view integration (optional)
        self._enable_global_risk = enable_global_risk
        self._global_risk_view: Any | None = None

        if enable_global_risk:
            try:
                from ..risk.global_risk import get_global_risk_view
                self._global_risk_view = get_global_risk_view()
                self.logger.debug("GlobalRiskView integrated with RiskManager")
            except Exception as e:
                self.logger.warning(f"Could not initialize GlobalRiskView: {e}")
                self._global_risk_view = None
    
    def needs_websocket(self) -> bool:
        """
        Check if RiskManager needs WebSocket connection.
        
        Returns True if GlobalRiskView is enabled and needs real-time data.
        """
        return self._enable_global_risk and self._global_risk_view is not None
    
    def start_websocket_if_needed(self) -> bool:
        """
        Start WebSocket if RiskManager needs it for GlobalRiskView.
        
        Returns True if websocket was started or already running, False otherwise.
        """
        if not self.needs_websocket():
            return False
        
        try:
            from ..core.application import get_application
            app = get_application()
            
            # Initialize app if needed
            if not app.is_initialized:
                if not app.initialize():
                    return False
            
            # Start websocket if not already running
            if not app.is_running:
                return app.start_websocket()
            
            # Check if websocket is connected
            from ..data.realtime_bootstrap import get_realtime_bootstrap
            bootstrap = get_realtime_bootstrap()
            return bootstrap.is_running if bootstrap else False
            
        except Exception as e:
            self.logger.warning(f"Failed to start websocket for risk manager: {e}")
            return False
    
    def _reset_daily_if_needed(self):
        """Reset daily counters at midnight."""
        today = datetime.now().date()
        if today > self._last_reset:
            self._daily_pnl = 0.0
            self._daily_trades = 0
            self._last_reset = today

    def _get_funding_rate(self, symbol: str) -> float | None:
        """
        Get current funding rate for symbol.

        G1-2: Used for funding rate pre-trade check.

        Returns:
            Funding rate as decimal (e.g., 0.0001 for 0.01%), or None if unavailable
        """
        try:
            # Try to get from GlobalRiskView/RealtimeState first (WebSocket)
            if self._global_risk_view:
                snapshot = self._global_risk_view.build_snapshot()
                # Check if we have funding rate in positions
                for pos in getattr(snapshot, 'positions', []):
                    if hasattr(pos, 'symbol') and pos.symbol == symbol:
                        if hasattr(pos, 'funding_rate'):
                            return pos.funding_rate

            # G0.3: Fallback - use stored exchange_manager to avoid per-call instantiation
            if self._exchange_manager and hasattr(self._exchange_manager, 'get_funding_rate'):
                result = self._exchange_manager.get_funding_rate(symbol)
                if result and 'funding_rate' in result:
                    return float(result['funding_rate'])

            return None
        except Exception as e:
            self.logger.debug(f"Could not get funding rate for {symbol}: {e}")
            return None
    
    def record_pnl(self, amount: float):
        """Record realized PnL for daily tracking."""
        self._reset_daily_if_needed()
        self._daily_pnl += amount
        if amount < 0:
            self.logger.risk("WARNING", f"Recorded loss: ${amount:.2f}")
        
        # Also record in GlobalRiskView if available
        if self._global_risk_view:
            self._global_risk_view.record_realized_pnl(amount)
    
    def check(
        self,
        signal: Signal,
        portfolio: PortfolioSnapshot,
    ) -> RiskCheckResult:
        """
        Check if a trading signal is allowed.
        
        Args:
            signal: Trading signal to check
            portfolio: Current portfolio state
        
        Returns:
            RiskCheckResult with allowed/blocked status and reason
        """
        self._reset_daily_if_needed()
        
        warnings = []
        
        # Skip if signal is to flatten
        if signal.direction == "FLAT":
            return RiskCheckResult(allowed=True, reason="Close position allowed")
        
        # Check 0: Global risk check (if enabled and available)
        # This catches account-level risks like margin overuse, liquidation danger
        if self._global_risk_view:
            global_decision = self._global_risk_view.check_pre_trade(
                signal=signal,
                symbol=signal.symbol,
                size_usdt=signal.size_usdt,
            )
            if not global_decision.allowed:
                self.logger.risk(
                    "BLOCKED",
                    f"Global risk check failed: {global_decision.message}",
                    veto_reason=global_decision.veto_reason.value,
                    details=global_decision.details,
                )
                # Emit structured event for risk block
                self.logger.event(
                    "risk.check.blocked",
                    level="WARNING",
                    component="risk_manager",
                    symbol=signal.symbol,
                    direction=signal.direction,
                    size_usdt=signal.size_usdt,
                    block_reason="global_risk",
                    veto_reason=global_decision.veto_reason.value,
                    message=global_decision.message,
                )
                return RiskCheckResult(
                    allowed=False,
                    reason=f"Global risk: {global_decision.message}",
                )
        
        # Check 0.5: Funding rate cost check (G1-2)
        # Block if funding rate * leverage would exceed 1% daily cost
        if hasattr(self.config, 'max_funding_cost_pct'):
            max_funding_cost = self.config.max_funding_cost_pct
        else:
            max_funding_cost = 1.0  # Default 1% daily cost threshold

        funding_rate = self._get_funding_rate(signal.symbol)
        if funding_rate is not None:
            # Funding is paid 3x daily, so multiply by 3 for daily cost
            daily_funding_cost_pct = abs(funding_rate) * 100 * 3  # Convert to % and annualize to daily

            # Get leverage from signal metadata if available
            leverage = signal.metadata.get('leverage', 1.0) if signal.metadata else 1.0
            effective_cost = daily_funding_cost_pct * leverage

            if effective_cost > max_funding_cost:
                self.logger.risk(
                    "BLOCKED",
                    f"Funding rate cost too high: {effective_cost:.2f}% daily",
                    funding_rate=funding_rate,
                    leverage=leverage,
                    limit=max_funding_cost,
                )
                self.logger.event(
                    "risk.check.blocked",
                    level="WARNING",
                    component="risk_manager",
                    symbol=signal.symbol,
                    direction=signal.direction,
                    size_usdt=signal.size_usdt,
                    block_reason="funding_rate_cost",
                    funding_rate=funding_rate,
                    effective_cost_pct=effective_cost,
                    limit=max_funding_cost,
                )
                return RiskCheckResult(
                    allowed=False,
                    reason=f"Funding rate cost too high ({effective_cost:.2f}% > {max_funding_cost}% daily)"
                )

        # Check 1: Daily loss limit
        if self._daily_pnl <= -self.config.max_daily_loss_usd:
            self.logger.risk(
                "BLOCKED",
                f"Daily loss limit reached: ${self._daily_pnl:.2f}",
                limit=self.config.max_daily_loss_usd
            )
            # Emit structured event
            self.logger.event(
                "risk.check.blocked",
                level="WARNING",
                component="risk_manager",
                symbol=signal.symbol,
                direction=signal.direction,
                size_usdt=signal.size_usdt,
                block_reason="daily_loss_limit",
                daily_pnl=self._daily_pnl,
                limit=self.config.max_daily_loss_usd,
            )
            return RiskCheckResult(
                allowed=False,
                reason=f"Daily loss limit reached (${self._daily_pnl:.2f} lost today)"
            )
        
        # Check 2: Minimum balance
        if portfolio.available < self.config.min_balance_usd:
            self.logger.risk(
                "BLOCKED",
                f"Balance too low: ${portfolio.available:.2f}",
                min_required=self.config.min_balance_usd
            )
            # Emit structured event
            self.logger.event(
                "risk.check.blocked",
                level="WARNING",
                component="risk_manager",
                symbol=signal.symbol,
                direction=signal.direction,
                size_usdt=signal.size_usdt,
                block_reason="min_balance",
                available=portfolio.available,
                min_required=self.config.min_balance_usd,
            )
            return RiskCheckResult(
                allowed=False,
                reason=f"Insufficient balance (${portfolio.available:.2f} < ${self.config.min_balance_usd:.2f})"
            )
        
        # Check 3: Maximum position size
        max_size = self.config.max_position_size_usdt
        adjusted_size = signal.size_usdt

        if signal.size_usdt > max_size:
            warnings.append(f"Size reduced from ${signal.size_usdt:.2f} to ${max_size:.2f}")
            adjusted_size = max_size
        
        # Check 4: Maximum total exposure
        new_exposure = portfolio.total_exposure + adjusted_size
        max_exposure = self.config.max_total_exposure_usd
        
        if new_exposure > max_exposure:
            available_exposure = max(0, max_exposure - portfolio.total_exposure)
            if available_exposure < adjusted_size * 0.1:  # Less than 10% of requested
                self.logger.risk(
                    "BLOCKED",
                    f"Exposure limit: ${new_exposure:.2f} > ${max_exposure:.2f}",
                    current=portfolio.total_exposure
                )
                return RiskCheckResult(
                    allowed=False,
                    reason=f"Would exceed exposure limit (${new_exposure:.2f} > ${max_exposure:.2f})"
                )
            else:
                warnings.append(f"Size reduced to available exposure: ${available_exposure:.2f}")
                adjusted_size = available_exposure
        
        # Check 5: Per-trade risk (% of account)
        max_risk_usd = portfolio.balance * (self.config.max_risk_per_trade_percent / 100)
        if adjusted_size > max_risk_usd:
            warnings.append(f"Size reduced to {self.config.max_risk_per_trade_percent}% of account: ${max_risk_usd:.2f}")
            adjusted_size = max_risk_usd
        
        # Check 6: Minimum viable size
        # Skip if signal.size_usdt=0 (backtest engine computes size later)
        min_viable_size = self.config.min_viable_size_usdt
        if signal.size_usdt > 0 and adjusted_size < min_viable_size:
            return RiskCheckResult(
                allowed=False,
                reason=f"Adjusted size too small (${adjusted_size:.2f} < ${min_viable_size:.2f})"
            )
        
        # All checks passed
        self.logger.risk(
            "ALLOWED",
            f"Signal approved: {signal.symbol} {signal.direction} ${adjusted_size:.2f}",
            original_size=signal.size_usdt,
            adjusted_size=adjusted_size
        )

        return RiskCheckResult(
            allowed=True,
            reason="All risk checks passed",
            adjusted_size=adjusted_size if adjusted_size != signal.size_usdt else None,
            warnings=warnings,
        )
    
    def check_leverage(self, symbol: str, requested_leverage: int) -> tuple[bool, int]:
        """
        Check and cap leverage.
        
        Args:
            symbol: Trading symbol
            requested_leverage: Desired leverage
        
        Returns:
            Tuple of (allowed, capped_leverage)
        """
        max_lev = min(requested_leverage, self.config.max_leverage)
        
        if max_lev != requested_leverage:
            self.logger.risk(
                "WARNING",
                f"Leverage capped: {requested_leverage}x -> {max_lev}x",
                symbol=symbol
            )
        
        return True, max_lev
    
    def get_remaining_exposure(self, portfolio: PortfolioSnapshot) -> float:
        """Get remaining available exposure in USD."""
        return max(0, self.config.max_total_exposure_usd - portfolio.total_exposure)
    
    def get_max_position_size(self, portfolio: PortfolioSnapshot) -> float:
        """
        Get maximum allowed position size given current state.

        G1-3: Cross-validates against equity with max_pos_pct cap.
        """
        remaining_exposure = self.get_remaining_exposure(portfolio)
        max_per_trade = portfolio.balance * (self.config.max_risk_per_trade_percent / 100)

        # G1-3: Cap by equity percentage (default 95%)
        max_pos_pct = getattr(self.config, 'max_position_equity_pct', 95.0)
        max_by_equity = portfolio.balance * (max_pos_pct / 100)

        return min(
            self.config.max_position_size_usdt,
            remaining_exposure,
            max_per_trade,
            max_by_equity,  # G1-3: Equity-based cap
        )
    
    def get_status(self) -> dict:
        """Get current risk status."""
        self._reset_daily_if_needed()
        
        status = {
            "daily_pnl": self._daily_pnl,
            "daily_loss_limit": self.config.max_daily_loss_usd,
            "daily_loss_remaining": self.config.max_daily_loss_usd + self._daily_pnl,
            "max_position_size": self.config.max_position_size_usdt,
            "max_exposure": self.config.max_total_exposure_usd,
            "max_leverage": self.config.max_leverage,
            "min_balance": self.config.min_balance_usd,
            "global_risk_enabled": self._global_risk_view is not None,
        }
        
        # Add global risk snapshot if available
        if self._global_risk_view:
            try:
                snapshot = self._global_risk_view.build_snapshot()
                status["global_risk"] = {
                    "account_im_rate": snapshot.account_im_rate,
                    "account_mm_rate": snapshot.account_mm_rate,
                    "total_equity": snapshot.total_equity,
                    "total_available": snapshot.total_available_balance,
                    "liquidation_risk_level": snapshot.liquidation_risk_level,
                    "high_risk_positions": snapshot.high_risk_position_count,
                }
            except Exception as e:
                status["global_risk"] = {"error": str(e)}
        
        return status
    
    def get_global_risk_snapshot(self) -> Any | None:
        """
        Get the global portfolio risk snapshot.

        Returns PortfolioRiskSnapshot if GlobalRiskView is enabled,
        otherwise None.
        """
        if self._global_risk_view:
            return self._global_risk_view.build_snapshot()
        return None

    def get_global_risk_summary(self) -> dict[str, Any] | None:
        """
        Get comprehensive global risk summary for CLI/agent display.
        
        Returns dict with snapshot, drawdown, daily PnL, and limits
        if GlobalRiskView is enabled, otherwise None.
        """
        if self._global_risk_view:
            return self._global_risk_view.get_risk_summary()
        return None
    
    # ==================== RR Calculation Utilities ====================
    
    @staticmethod
    def calculate_stop_loss_price(
        entry_price: float,
        is_long: bool,
        stop_loss_roi_pct: float,
        leverage: int,
    ) -> float:
        """
        Calculate stop loss price from ROI percentage.
        
        Args:
            entry_price: Entry price
            is_long: True for long, False for short
            stop_loss_roi_pct: Stop loss as ROI % (e.g., 10 = lose 10% of margin)
            leverage: Position leverage
        
        Returns:
            Stop loss price
        """
        # Price distance = ROI% / Leverage
        sl_price_pct = stop_loss_roi_pct / leverage / 100
        risk_distance = entry_price * sl_price_pct
        
        if is_long:
            return entry_price - risk_distance
        else:
            return entry_price + risk_distance
    
    @staticmethod
    def calculate_take_profit_price(
        entry_price: float,
        is_long: bool,
        stop_loss_roi_pct: float,
        rr_ratio: float,
        leverage: int,
    ) -> float:
        """
        Calculate take profit price from RR ratio.
        
        Args:
            entry_price: Entry price
            is_long: True for long, False for short
            stop_loss_roi_pct: Stop loss as ROI % (base risk)
            rr_ratio: Risk/Reward ratio (e.g., 2.0 for 1:2)
            leverage: Position leverage
        
        Returns:
            Take profit price
        """
        # TP ROI = SL ROI * RR
        tp_roi_pct = stop_loss_roi_pct * rr_ratio
        tp_price_pct = tp_roi_pct / leverage / 100
        tp_distance = entry_price * tp_price_pct
        
        if is_long:
            return entry_price + tp_distance
        else:
            return entry_price - tp_distance
    
    @staticmethod
    def calculate_trade_levels(
        entry_price: float,
        is_long: bool,
        margin_usd: float,
        leverage: int,
        stop_loss_roi_pct: float,
        take_profits: list[dict[str, float]],
    ) -> dict[str, Any]:
        """
        Calculate all trade levels for RR-based position.
        
        Args:
            entry_price: Entry price
            is_long: True for long, False for short
            margin_usd: Margin amount in USD
            leverage: Position leverage
            stop_loss_roi_pct: Stop loss as ROI % (e.g., 10 = lose 10% of margin)
            take_profits: List of TP configs:
                [{"rr": 1.5, "close_pct": 50}, {"rr": 3.0, "close_pct": 50}]
        
        Returns:
            Dict with all calculated levels:
                - entry: float
                - stop_loss: float
                - take_profits: List[Dict] with price, roi, close_pct
                - notional_usd: float
                - max_loss_usd: float
                - max_profit_usd: float
        """
        notional_usd = margin_usd * leverage
        
        # Calculate stop loss
        sl_price_pct = stop_loss_roi_pct / leverage / 100
        risk_distance = entry_price * sl_price_pct
        
        if is_long:
            stop_loss = entry_price - risk_distance
        else:
            stop_loss = entry_price + risk_distance
        
        # Calculate take profits
        tp_levels = []
        total_potential_profit = 0.0
        
        for tp in take_profits:
            tp_roi_pct = stop_loss_roi_pct * tp["rr"]
            tp_price_pct = tp_roi_pct / leverage / 100
            tp_distance = entry_price * tp_price_pct
            
            if is_long:
                tp_price = entry_price + tp_distance
            else:
                tp_price = entry_price - tp_distance
            
            profit_usd = margin_usd * (tp_roi_pct / 100) * (tp["close_pct"] / 100)
            total_potential_profit += profit_usd
            
            tp_levels.append({
                "price": tp_price,
                "rr": tp["rr"],
                "roi_pct": tp_roi_pct,
                "close_pct": tp["close_pct"],
                "profit_usd": profit_usd,
            })
        
        max_loss = margin_usd * (stop_loss_roi_pct / 100)
        
        return {
            "entry": entry_price,
            "stop_loss": stop_loss,
            "take_profits": tp_levels,
            "notional_usd": notional_usd,
            "margin_usd": margin_usd,
            "leverage": leverage,
            "max_loss_usd": max_loss,
            "max_profit_usd": total_potential_profit,
            "risk_reward_overall": total_potential_profit / max_loss if max_loss > 0 else 0,
        }

