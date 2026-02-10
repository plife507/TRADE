"""
Unified Position Sizing Model for TRADE engines.

This is the SINGLE SOURCE OF TRUTH for position sizing across all engine modes.
Port of the sophisticated SimulatedRiskManager logic from src/backtest/.

Sizing Models:
    - percent_equity: Margin-based sizing with leverage (Bybit model)
    - risk_based: Risk-per-trade sizing using stop distance
    - fixed_notional: Fixed USDT size (capped by leverage)

The module is engine-agnostic - it does not depend on RuntimeSnapshotView
or any backtest-specific types. Engines pass primitive values.

Architecture:
    PlayEngine -> SizingModel.size_order() -> SizingResult

This ensures identical position sizing behavior across all execution modes
(backtest, demo, live).
"""


from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SizingConfig:
    """
    Configuration for position sizing.

    Mirrors the relevant fields from RiskProfileConfig but is independent
    of the backtest module. This allows PlayEngine to use sizing without
    importing backtest types.

    Sizing Model Semantics:
        - percent_equity: Position = margin * leverage
          margin = equity * (risk_per_trade_pct / 100)
          Bybit-style isolated margin calculation.
          CAPPED by max_position_equity_pct to prevent over-exposure.

        - risk_based: Size to lose exactly risk_pct if stopped out
          risk$ = equity * (risk_per_trade_pct / 100)
          size = risk$ * entry_price / stop_distance
          Falls back to percent_equity if no stop_loss provided.

        - fixed_notional: Use requested size_usdt directly
          Still capped by max leverage.

    Position Cap (IMPORTANT):
        - max_position_equity_pct caps TOTAL position as % of equity
        - This prevents runaway compounding and over-exposure
        - Default 95% leaves buffer for fees (entry + potential exit)
        - Example: with 95% cap and $10K equity, max position = $9,500

    Fee Reservation:
        - reserve_fee_buffer reserves equity for entry/exit fees
        - Ensures position margin + fees never exceeds equity

    Liquidation Safety (G0-2):
        - min_liq_distance_pct ensures liquidation price is at least X% from entry
        - Default 10% prevents entries where liquidation is too close
        - Example: at 10x leverage, liq is ~10% away, so min_liq_distance_pct=10 blocks it
    """

    # Core sizing parameters
    initial_equity: float = 10000.0
    sizing_model: str = "percent_equity"
    risk_per_trade_pct: float = 1.0
    max_leverage: float = 2.0
    min_trade_usdt: float = 1.0

    # Position cap: max position as % of equity (prevents 100% exposure)
    # Default 95% leaves 5% buffer for fees and safety margin
    max_position_equity_pct: float = 95.0

    # Fee reservation: if True, reserves balance for entry+exit fees
    reserve_fee_buffer: bool = True

    # Optional fee model for entry gate calculations (loaded from DEFAULTS if None)
    taker_fee_rate: float | None = None
    include_est_close_fee_in_entry_gate: bool = False

    # G0-2: Minimum distance to liquidation price as % of entry price
    # Rejects entries where liquidation would occur within this % move
    # Default 10% means at 10x leverage (liq ~10% away), entry is blocked
    min_liq_distance_pct: float = 10.0

    # Maintenance margin rate for liquidation calculation (Bybit default ~0.5%)
    maintenance_margin_rate: float = 0.005

    def __post_init__(self) -> None:
        """Load defaults from config/defaults.yml if not specified."""
        if self.taker_fee_rate is None:
            from src.config.constants import DEFAULTS
            self.taker_fee_rate = DEFAULTS.fees.taker_rate

        # Validate max_position_equity_pct
        if self.max_position_equity_pct <= 0 or self.max_position_equity_pct > 100:
            raise ValueError(
                f"max_position_equity_pct must be in (0, 100], got {self.max_position_equity_pct}"
            )

        # Validate min_liq_distance_pct
        if self.min_liq_distance_pct < 0:
            raise ValueError(
                f"min_liq_distance_pct must be >= 0, got {self.min_liq_distance_pct}"
            )

    @classmethod
    def from_risk_profile(cls, risk_profile: Any) -> "SizingConfig":
        """
        Create SizingConfig from a RiskProfileConfig.

        This factory method bridges the backtest config to the unified sizing module.

        Args:
            risk_profile: RiskProfileConfig instance (from src/backtest/system_config.py)

        Returns:
            SizingConfig with values copied from risk_profile
        """
        # Get max_position_equity_pct from risk_profile if available, else default
        max_pos_pct = getattr(risk_profile, "max_position_equity_pct", 95.0)
        reserve_fee = getattr(risk_profile, "reserve_fee_buffer", True)

        return cls(
            initial_equity=risk_profile.initial_equity,
            sizing_model=risk_profile.sizing_model,
            risk_per_trade_pct=risk_profile.risk_per_trade_pct,
            max_leverage=risk_profile.max_leverage,
            min_trade_usdt=risk_profile.min_trade_usdt,
            max_position_equity_pct=max_pos_pct,
            reserve_fee_buffer=reserve_fee,
            taker_fee_rate=risk_profile.taker_fee_rate,
            include_est_close_fee_in_entry_gate=risk_profile.include_est_close_fee_in_entry_gate,
        )


@dataclass(slots=True)
class SizingResult:
    """
    Result of a position sizing calculation.

    Contains the computed size and metadata about the calculation method.
    This is the return type from SizingModel.size_order().
    """

    size_usdt: float
    method: str  # "percent_equity", "risk_based", "risk_based_fallback", "fixed_notional"
    details: str  # Human-readable explanation

    # Optional: indicates if size was capped by leverage limit
    was_capped: bool = False

    # G0-2: Indicates if entry was rejected due to liquidation too close
    rejected: bool = False
    rejection_reason: str = ""


class SizingModel:
    """
    Unified position sizing model for all TRADE engines.

    This class contains the sizing logic ported from SimulatedRiskManager.
    Used by PlayEngine for all modes (backtest, demo, live).

    Usage:
        model = SizingModel(config)

        # Update equity as trades close
        model.update_equity(current_equity)

        # Size an order
        result = model.size_order(
            equity=10000.0,
            entry_price=50000.0,
            stop_loss=49000.0,
            requested_size=None,
        )

    Thread Safety:
        The model tracks equity internally. Create separate instances
        for concurrent backtests or use explicit equity parameter.
    """

    def __init__(self, config: SizingConfig):
        """
        Initialize with sizing configuration.

        Args:
            config: SizingConfig with sizing parameters
        """
        self._config = config
        self._equity = config.initial_equity

    @property
    def equity(self) -> float:
        """Current tracked equity."""
        return self._equity

    @property
    def config(self) -> SizingConfig:
        """Sizing configuration."""
        return self._config

    def size_order(
        self,
        equity: float | None = None,
        entry_price: float | None = None,
        stop_loss: float | None = None,
        requested_size: float | None = None,
        used_margin: float = 0.0,
    ) -> SizingResult:
        """
        Compute position size based on configured sizing model.

        This is the main entry point for position sizing. The method
        dispatches to the appropriate sizing calculation based on
        self._config.sizing_model.

        Args:
            equity: Current account equity (uses tracked equity if None)
            entry_price: Entry price for risk-based sizing
            stop_loss: Stop loss price for risk-based sizing
            requested_size: Requested size for fixed_notional model
            used_margin: Margin already used by existing positions (default 0)

        Returns:
            SizingResult with computed size and metadata

        Example:
            # Percent equity (Bybit margin model)
            result = model.size_order(equity=10000.0)

            # Risk-based with stop loss
            result = model.size_order(
                equity=10000.0,
                entry_price=50000.0,
                stop_loss=49000.0,
            )

            # Fixed notional
            result = model.size_order(
                equity=10000.0,
                requested_size=5000.0,
            )
        """
        # Use tracked equity if not provided
        if equity is None:
            equity = self._equity

        model = self._config.sizing_model

        if model == "percent_equity":
            result = self._size_percent_equity(equity, used_margin)
        elif model == "risk_based":
            result = self._size_risk_based(equity, entry_price, stop_loss, used_margin)
        elif model in ("fixed_usdt", "fixed_notional"):
            result = self._size_fixed_notional(equity, requested_size)
        else:
            # Default to percent_equity for unknown models
            result = self._size_percent_equity(equity, used_margin)

        # Hard ceiling: prevent float overflow from compounding equity
        _MAX_NOTIONAL = 1e15
        if result.size_usdt > _MAX_NOTIONAL:
            result.size_usdt = _MAX_NOTIONAL
            result.was_capped = True

        return result

    def _size_percent_equity(self, equity: float, used_margin: float = 0.0) -> SizingResult:
        """
        Size using percentage of FREE equity as margin, then apply leverage.

        Bybit margin model:
            - free_margin = equity - used_margin (accounts for existing positions)
            - margin = free_margin * (risk_pct / 100)
            - position_value = margin * leverage

        Example with 10% of $10,000 equity at 10x leverage:
            - margin = $10,000 * 10% = $1,000 (what you're putting up)
            - position = $1,000 * 10 = $10,000 (your exposure)

        IMPORTANT: Position is capped by:
            1. max_position_equity_pct (default 95%) of equity
            2. Fee buffer reservation (entry + exit fees)
            3. free_margin * max_leverage (max borrowing)

        Args:
            equity: Total account equity
            used_margin: Margin already used by existing positions (default 0)
        """
        risk_pct = self._config.risk_per_trade_pct
        max_lev = self._config.max_leverage
        max_pos_pct = self._config.max_position_equity_pct
        taker_fee = self._config.taker_fee_rate or 0.00055  # Default 5.5 bps

        # Calculate free margin (what's available for new positions)
        free_margin = equity - used_margin

        # Cap 1: Maximum position as % of total equity
        # This prevents runaway compounding regardless of leverage
        max_by_equity_pct = equity * (max_pos_pct / 100.0)

        # Cap 2: Fee reservation
        # Reserve balance for entry fee + potential exit fee
        # Position + entry_fee + exit_fee <= available
        # Position * (1 + 2*taker_fee) <= available
        # Position <= available / (1 + 2*taker_fee)
        if self._config.reserve_fee_buffer:
            fee_factor = 1.0 + 2.0 * taker_fee  # Entry + exit fees
            max_by_fees = free_margin * max_lev / fee_factor
        else:
            max_by_fees = float("inf")

        # Cap 3: Leverage-based max (existing cap)
        max_by_leverage = free_margin * max_lev

        # Final max is the minimum of all caps
        max_size = min(max_by_equity_pct, max_by_fees, max_by_leverage)

        # Margin is the % of FREE equity we're committing
        margin = free_margin * (risk_pct / 100.0)

        # Position size = margin * leverage (Bybit formula)
        size_usdt = margin * max_lev

        # Apply the cap
        was_capped = size_usdt > max_size
        size_usdt = min(size_usdt, max_size)

        # Build details string
        cap_reason = ""
        if was_capped:
            if max_size == max_by_equity_pct:
                cap_reason = f", capped by {max_pos_pct}% equity"
            elif max_size == max_by_fees:
                cap_reason = ", capped by fee reserve"
            else:
                cap_reason = ", capped by leverage"

        return SizingResult(
            size_usdt=size_usdt,
            method="percent_equity",
            details=f"free_margin=${free_margin:.2f}, margin=${margin:.2f}, lev={max_lev:.1f}x, position=${size_usdt:.2f}{cap_reason}",
            was_capped=was_capped,
        )

    def _size_risk_based(
        self,
        equity: float,
        entry_price: float | None,
        stop_loss: float | None,
        used_margin: float = 0.0,
    ) -> SizingResult:
        """
        Size using risk-based calculation.

        Computes position size based on account risk percentage and stop distance:
            - risk_dollars = equity * (risk_per_trade_pct / 100)
            - size = risk_dollars * entry_price / stop_distance

        This sizes the position so that if stopped out, you lose exactly
        risk_pct% of equity.

        Example:
            - $10,000 equity, 1% risk = $100 at risk
            - Entry $64,200, Stop $62,916 (2% stop) = $1,284 stop distance
            - size = $100 * $64,200 / $1,284 = $5,000 position

        If stopped out: $5,000 * 2% = $100 loss = 1% of equity

        Falls back to percent_equity if stop_loss is not provided.

        Args:
            equity: Total account equity
            entry_price: Entry price for the trade
            stop_loss: Stop loss price
            used_margin: Margin already used by existing positions (default 0)
        """
        risk_pct = self._config.risk_per_trade_pct
        max_lev = self._config.max_leverage
        max_pos_pct = self._config.max_position_equity_pct
        taker_fee = self._config.taker_fee_rate or 0.00055

        # Calculate free margin for position cap
        free_margin = equity - used_margin

        # Calculate max size with all caps (same as percent_equity)
        max_by_equity_pct = equity * (max_pos_pct / 100.0)
        if self._config.reserve_fee_buffer:
            fee_factor = 1.0 + 2.0 * taker_fee
            max_by_fees = free_margin * max_lev / fee_factor
        else:
            max_by_fees = float("inf")
        max_by_leverage = free_margin * max_lev
        max_size = min(max_by_equity_pct, max_by_fees, max_by_leverage)

        # Risk dollars (what we're willing to lose)
        risk_dollars = equity * (risk_pct / 100.0)

        # Need both entry_price and stop_loss for risk-based sizing
        if stop_loss is not None and entry_price is not None and entry_price > 0:
            stop_distance = abs(entry_price - stop_loss)

            if stop_distance > 0:
                # Risk-based sizing: size = risk$ * entry / stop_distance
                size_usdt = risk_dollars * entry_price / stop_distance
                was_capped = size_usdt > max_size
                size_usdt = min(size_usdt, max_size)

                cap_reason = ""
                if was_capped:
                    if max_size == max_by_equity_pct:
                        cap_reason = f", capped by {max_pos_pct}% equity"
                    elif max_size == max_by_fees:
                        cap_reason = ", capped by fee reserve"
                    else:
                        cap_reason = ", capped by leverage"

                return SizingResult(
                    size_usdt=size_usdt,
                    method="risk_based",
                    details=f"risk=${risk_dollars:.2f}, stop_dist={stop_distance:.4f}{cap_reason}",
                    was_capped=was_capped,
                )

        # Fallback to percent_equity formula if no valid stop
        margin = free_margin * (risk_pct / 100.0)
        size_usdt = margin * max_lev
        was_capped = size_usdt > max_size
        size_usdt = min(size_usdt, max_size)

        return SizingResult(
            size_usdt=size_usdt,
            method="risk_based_fallback",
            details=f"no stop_loss, using percent_equity fallback (margin=${margin:.2f}, lev={max_lev:.1f}x)",
            was_capped=was_capped,
        )

    def _size_fixed_notional(
        self,
        equity: float,
        requested_size: float | None,
    ) -> SizingResult:
        """
        Size using fixed notional from request.

        Still capped by:
            1. max_position_equity_pct (default 95%) of equity
            2. max leverage to prevent over-leveraging

        Args:
            equity: Current equity for leverage cap calculation
            requested_size: Requested position size in USDT
        """
        max_lev = self._config.max_leverage
        max_pos_pct = self._config.max_position_equity_pct

        # Cap by equity percentage and leverage
        max_by_equity_pct = equity * (max_pos_pct / 100.0)
        max_by_leverage = equity * max_lev
        max_size = min(max_by_equity_pct, max_by_leverage)

        # Use requested size or default to max
        size_usdt = requested_size if requested_size is not None else max_size
        was_capped = size_usdt > max_size
        size_usdt = min(size_usdt, max_size)

        cap_reason = ""
        if was_capped:
            if max_size == max_by_equity_pct:
                cap_reason = f" (capped by {max_pos_pct}% equity)"
            else:
                cap_reason = " (capped by leverage)"

        return SizingResult(
            size_usdt=size_usdt,
            method="fixed_notional",
            details=f"requested={requested_size or 0:.2f}{cap_reason}",
            was_capped=was_capped,
        )

    def update_equity(self, new_equity: float) -> None:
        """
        Update internal equity tracking.

        Call this after trades close to keep sizing accurate.

        Args:
            new_equity: New equity value from exchange/simulation
        """
        self._equity = new_equity

    def reset(self) -> None:
        """Reset equity to initial value."""
        self._equity = self._config.initial_equity

    def check_min_size(self, size_usdt: float) -> bool:
        """
        Check if size meets minimum trade requirement.

        Args:
            size_usdt: Computed position size

        Returns:
            True if size >= min_trade_usdt
        """
        return size_usdt >= self._config.min_trade_usdt

    def check_liquidation_distance(
        self,
        entry_price: float,
        leverage: float,
        direction: str,
    ) -> tuple[bool, float, str]:
        """
        G0-2: Check if liquidation price is safely distant from entry.

        Liquidation occurs when:
        - Long: price drops such that loss = margin (minus maintenance)
        - Short: price rises such that loss = margin (minus maintenance)

        Formula (isolated margin, Bybit-style):
            Long liq price = entry * (1 - 1/leverage + mmr)
            Short liq price = entry * (1 + 1/leverage - mmr)

        Where mmr = maintenance margin rate (~0.5% for Bybit)

        Args:
            entry_price: Entry price
            leverage: Position leverage
            direction: "long" or "short"

        Returns:
            Tuple of (is_safe, liq_distance_pct, reason)
            - is_safe: True if liq distance >= min_liq_distance_pct
            - liq_distance_pct: Actual distance to liquidation as %
            - reason: Rejection reason if not safe
        """
        if leverage <= 0 or entry_price <= 0:
            return False, 0.0, "Invalid leverage or entry price"

        mmr = self._config.maintenance_margin_rate
        min_distance = self._config.min_liq_distance_pct

        if direction == "long":
            # Long liquidation: price drops
            liq_price = entry_price * (1 - 1/leverage + mmr)
            liq_distance_pct = ((entry_price - liq_price) / entry_price) * 100
        else:
            # Short liquidation: price rises
            liq_price = entry_price * (1 + 1/leverage - mmr)
            liq_distance_pct = ((liq_price - entry_price) / entry_price) * 100

        is_safe = liq_distance_pct >= min_distance

        if not is_safe:
            reason = (
                f"Liquidation too close: {liq_distance_pct:.2f}% from entry "
                f"(min required: {min_distance:.1f}%). "
                f"At {leverage:.1f}x leverage, liq price = ${liq_price:.2f}"
            )
            return False, liq_distance_pct, reason

        return True, liq_distance_pct, ""

    def size_order_with_liq_check(
        self,
        entry_price: float,
        direction: str,
        equity: float | None = None,
        stop_loss: float | None = None,
        requested_size: float | None = None,
        used_margin: float = 0.0,
    ) -> SizingResult:
        """
        Size order with liquidation distance validation.

        This is the recommended entry point for live trading. It combines
        position sizing with the G0-2 liquidation safety check.

        Args:
            entry_price: Entry price for the trade
            direction: "long" or "short"
            equity: Current account equity (uses tracked equity if None)
            stop_loss: Stop loss price for risk-based sizing
            requested_size: Requested size for fixed_notional model
            used_margin: Margin already used by existing positions

        Returns:
            SizingResult with rejection info if liquidation too close
        """
        # First, check liquidation distance
        is_safe, liq_dist, rejection_reason = self.check_liquidation_distance(
            entry_price=entry_price,
            leverage=self._config.max_leverage,
            direction=direction,
        )

        if not is_safe:
            return SizingResult(
                size_usdt=0.0,
                method="rejected",
                details=rejection_reason,
                rejected=True,
                rejection_reason=rejection_reason,
            )

        # Proceed with normal sizing
        result = self.size_order(
            equity=equity,
            entry_price=entry_price,
            stop_loss=stop_loss,
            requested_size=requested_size,
            used_margin=used_margin,
        )

        return result
