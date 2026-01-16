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
    BacktestEngine -> SizingModel.size_order() -> SizingResult
    PlayEngine     -> SizingModel.size_order() -> SizingResult

This ensures identical position sizing behavior across all execution modes.
"""

from __future__ import annotations

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

        - risk_based: Size to lose exactly risk_pct if stopped out
          risk$ = equity * (risk_per_trade_pct / 100)
          size = risk$ * entry_price / stop_distance
          Falls back to percent_equity if no stop_loss provided.

        - fixed_notional: Use requested size_usdt directly
          Still capped by max leverage.
    """

    # Core sizing parameters
    initial_equity: float = 10000.0
    sizing_model: str = "percent_equity"
    risk_per_trade_pct: float = 1.0
    max_leverage: float = 2.0
    min_trade_usdt: float = 1.0

    # Optional fee model for entry gate calculations
    taker_fee_rate: float = 0.0006
    include_est_close_fee_in_entry_gate: bool = False

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
        return cls(
            initial_equity=risk_profile.initial_equity,
            sizing_model=risk_profile.sizing_model,
            risk_per_trade_pct=risk_profile.risk_per_trade_pct,
            max_leverage=risk_profile.max_leverage,
            min_trade_usdt=risk_profile.min_trade_usdt,
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


class SizingModel:
    """
    Unified position sizing model for all TRADE engines.

    This class contains the SOPHISTICATED sizing logic ported from
    SimulatedRiskManager. Both BacktestEngine and PlayEngine use this
    to ensure identical position sizing behavior.

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
            return self._size_percent_equity(equity)
        elif model == "risk_based":
            return self._size_risk_based(equity, entry_price, stop_loss)
        elif model in ("fixed_usdt", "fixed_notional"):
            return self._size_fixed_notional(equity, requested_size)
        else:
            # Default to percent_equity for unknown models
            return self._size_percent_equity(equity)

    def _size_percent_equity(self, equity: float) -> SizingResult:
        """
        Size using percentage of equity as margin, then apply leverage.

        Bybit margin model:
            - margin = equity * (risk_pct / 100)
            - position_value = margin * leverage

        Example with 10% of $10,000 equity at 10x leverage:
            - margin = $10,000 * 10% = $1,000 (what you're putting up)
            - position = $1,000 * 10 = $10,000 (your exposure)

        The position is capped at equity * max_leverage (max borrowing).
        """
        risk_pct = self._config.risk_per_trade_pct
        max_lev = self._config.max_leverage

        # Margin is the % of equity we're committing
        margin = equity * (risk_pct / 100.0)

        # Position size = margin * leverage (Bybit formula)
        size_usdt = margin * max_lev

        # Cap at max allowed position (equity * max_leverage)
        max_size = equity * max_lev
        was_capped = size_usdt > max_size
        size_usdt = min(size_usdt, max_size)

        return SizingResult(
            size_usdt=size_usdt,
            method="percent_equity",
            details=f"margin=${margin:.2f}, lev={max_lev:.1f}x, position=${size_usdt:.2f}",
            was_capped=was_capped,
        )

    def _size_risk_based(
        self,
        equity: float,
        entry_price: float | None,
        stop_loss: float | None,
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
        """
        risk_pct = self._config.risk_per_trade_pct
        max_lev = self._config.max_leverage

        # Maximum size based on leverage
        max_size = equity * max_lev

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

                return SizingResult(
                    size_usdt=size_usdt,
                    method="risk_based",
                    details=f"risk=${risk_dollars:.2f}, stop_dist={stop_distance:.4f}",
                    was_capped=was_capped,
                )

        # Fallback to simple percent_equity if no valid stop
        size_usdt = equity * (risk_pct / 100.0)
        was_capped = size_usdt > max_size
        size_usdt = min(size_usdt, max_size)

        return SizingResult(
            size_usdt=size_usdt,
            method="risk_based_fallback",
            details="no stop_loss, using percent_equity fallback",
            was_capped=was_capped,
        )

    def _size_fixed_notional(
        self,
        equity: float,
        requested_size: float | None,
    ) -> SizingResult:
        """
        Size using fixed notional from request.

        Still capped by max leverage to prevent over-leveraging.

        Args:
            equity: Current equity for leverage cap calculation
            requested_size: Requested position size in USDT
        """
        max_lev = self._config.max_leverage
        max_size = equity * max_lev

        # Use requested size or default to max
        size_usdt = requested_size if requested_size is not None else max_size
        was_capped = size_usdt > max_size
        size_usdt = min(size_usdt, max_size)

        return SizingResult(
            size_usdt=size_usdt,
            method="fixed_notional",
            details=f"requested={requested_size or 0:.2f}",
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
