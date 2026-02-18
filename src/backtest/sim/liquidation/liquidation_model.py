"""
Liquidation model for mark-based liquidation.

Bybit mechanics:
- Trigger: equity <= maintenance_margin (mark price)
- Settlement: position closed at bankruptcy price (0% margin level)
- Bankruptcy price = price where entire initial margin is consumed

No ADL (auto-deleveraging) in this implementation.

Bybit reference:
- Liquidation: reference/exchanges/bybit/docs/v5/order/close-order.mdx
- Help Center: Liquidation Price Calculation under Isolated Mode (UTA)
"""

from dataclasses import dataclass
from datetime import datetime

from ..types import (
    Position,
    PriceSnapshot,
    LedgerState,
    LiquidationEvent,
    LiquidationResult,
    Fill,
    FillReason,
    OrderSide,
)


@dataclass
class LiquidationModelConfig:
    """Configuration for liquidation model."""
    liquidation_fee_rate: float | None = None  # From DEFAULTS if None

    def __post_init__(self) -> None:
        if self.liquidation_fee_rate is None:
            from src.config.constants import DEFAULTS
            object.__setattr__(self, 'liquidation_fee_rate', DEFAULTS.fees.liquidation_rate)
    # No ADL in Phase 1


class LiquidationModel:
    """
    Checks liquidation conditions and handles forced closure.

    Bybit mechanics:
    - Trigger: equity_usdt <= maintenance_margin_usdt (mark price)
    - Settlement: position closed at bankruptcy price (not mark)
    - Bankruptcy = 0% margin level (entire initial margin consumed)
    """

    def __init__(self, config: LiquidationModelConfig | None = None):
        """
        Initialize liquidation model.

        Args:
            config: Optional configuration
        """
        self._config = config or LiquidationModelConfig()
        self._liquidation_counter: int = 0  # Sequential ID for determinism

    def reset(self) -> None:
        """Reset liquidation counter for new backtest run."""
        self._liquidation_counter = 0

    @staticmethod
    def calculate_bankruptcy_price(
        entry_price: float,
        leverage: float,
        direction: int,
        fee_rate: float = 0.0,
    ) -> float:
        """
        Calculate bankruptcy price (0% margin level).

        At bankruptcy price, the trader's entire initial margin is consumed
        including the closing fee. Bybit settles liquidated positions here.

            Long:  BP = EP * (1 - 1/leverage) / (1 - fee_rate)
            Short: BP = EP * (1 + 1/leverage) / (1 + fee_rate)

        The fee_rate term ensures margin + PnL - close_fee = 0 exactly
        at the bankruptcy price.

        Args:
            entry_price: Position entry price.
            leverage: Position leverage.
            direction: 1 for long, -1 for short.
            fee_rate: Taker fee rate for closing (e.g. 0.00055).

        Returns:
            Bankruptcy price (>= 0).
        """
        if leverage <= 0 or entry_price <= 0:
            return 0.0

        imr = 1.0 / leverage
        if direction == 1:  # Long
            denom = 1.0 - fee_rate
            if denom <= 0:
                return 0.0
            return max(0.0, entry_price * (1.0 - imr) / denom)
        else:  # Short
            return entry_price * (1.0 + imr) / (1.0 + fee_rate)

    def check_liquidation(
        self,
        ledger_state: LedgerState,
        prices: PriceSnapshot,
        position: Position | None,
        leverage: float = 1.0,
    ) -> LiquidationResult:
        """
        Check if liquidation should occur.

        Trigger: equity_usdt <= maintenance_margin_usdt
        Settlement: position closed at bankruptcy price (Bybit parity).

        Args:
            ledger_state: Current ledger state
            prices: Current price snapshot
            position: Current open position
            leverage: Position leverage (for bankruptcy price calc)

        Returns:
            LiquidationResult with liquidation status
        """
        result = LiquidationResult()

        # No position = no liquidation
        if position is None:
            return result

        # Check liquidation condition
        if ledger_state.equity_usdt > ledger_state.maintenance_margin_usdt:
            return result

        # Liquidation triggered
        result.liquidated = True

        # Calculate bankruptcy price (settlement price, includes fee term)
        direction = 1 if position.side == OrderSide.LONG else -1
        assert self._config.liquidation_fee_rate is not None
        bankruptcy_price = self.calculate_bankruptcy_price(
            position.entry_price, leverage, direction,
            fee_rate=self._config.liquidation_fee_rate,
        )

        # Liquidation fee based on position value at bankruptcy price
        position_value_at_bankruptcy = position.size * bankruptcy_price
        assert self._config.liquidation_fee_rate is not None
        liquidation_fee = position_value_at_bankruptcy * self._config.liquidation_fee_rate

        # Create liquidation event
        result.event = LiquidationEvent(
            timestamp=prices.timestamp,
            symbol=position.symbol,
            side=position.side,
            mark_price=prices.mark_price,
            bankruptcy_price=bankruptcy_price,
            equity_usdt=ledger_state.equity_usdt,
            maintenance_margin_usdt=ledger_state.maintenance_margin_usdt,
            liquidation_fee=liquidation_fee,
        )

        # Create fill at bankruptcy price (Bybit settlement)
        self._liquidation_counter += 1
        result.fill = Fill(
            fill_id=f"liq_{self._liquidation_counter:04d}",
            order_id="",
            symbol=position.symbol,
            side=position.side,
            price=bankruptcy_price,
            size=position.size,
            size_usdt=position.size_usdt,
            timestamp=prices.timestamp,
            reason=FillReason.LIQUIDATION,
            fee=liquidation_fee,
            slippage=0.0,
        )

        return result
    
    def is_liquidatable(
        self,
        equity_usdt: float,
        maintenance_margin_usdt: float,
    ) -> bool:
        """
        Check if account is liquidatable.
        
        Args:
            equity_usdt: Current equity
            maintenance_margin_usdt: Maintenance margin requirement
            
        Returns:
            True if liquidation should occur
        """
        if maintenance_margin_usdt <= 0:
            return False
        return equity_usdt <= maintenance_margin_usdt
    
    def calculate_liquidation_price(
        self,
        position: Position,
        cash_balance_usdt: float,
        maintenance_margin_rate: float,
        taker_fee_rate: float = 0.0,
        mm_deduction: float = 0.0,
    ) -> float:
        """
        Calculate the liquidation price for a position.

        Bybit isolated liquidation trigger: equity <= MM
        Where MM = size * liq * (MMR + feeRate) - mmDeduction

        Solving for liq price:
          cash + size*(liq - entry) = size*liq*(MMR + feeRate) - mmDed   [long]
          cash + size*(entry - liq) = size*liq*(MMR + feeRate) - mmDed   [short]

        Long:  liq = (size*entry - cash - mmDed) / (size*(1 - MMR - feeRate))
        Short: liq = (cash + size*entry + mmDed) / (size*(1 + MMR + feeRate))

        Args:
            position: Open position
            cash_balance_usdt: Current cash balance
            maintenance_margin_rate: MMR as decimal
            taker_fee_rate: Taker fee rate for fee-to-close term
            mm_deduction: Bybit mmDeduction for the risk tier

        Returns:
            Estimated liquidation price
        """
        entry = position.entry_price
        size = position.size
        mmr_eff = maintenance_margin_rate + taker_fee_rate

        if size == 0:
            return 0.0

        if position.side == OrderSide.LONG:
            denominator = size * (1.0 - mmr_eff)
            if denominator <= 0:
                return 0.0
            liq_price = (size * entry - cash_balance_usdt - mm_deduction) / denominator
        else:
            denominator = size * (1.0 + mmr_eff)
            if denominator == 0:
                return 0.0
            liq_price = (cash_balance_usdt + size * entry + mm_deduction) / denominator

        return max(0.0, liq_price)

    @staticmethod
    def estimate_liquidation_price(
        entry_price: float,
        leverage: float,
        direction: int,
        maintenance_margin_rate: float = 0.005,
        taker_fee_rate: float = 0.0,
        mm_deduction: float = 0.0,
    ) -> float:
        """
        Estimate liquidation price for a proposed position (pre-trade).

        Bybit isolated liquidation price formula (UTA, USDT linear):

            Long:  LP = EP * (1 - IMR + MMR) - mmDed / Qty
            Short: LP = EP * (1 + IMR - MMR) + mmDed / Qty

        Where IMR = 1/leverage, MMR = maintenance_margin_rate.
        Note: fee-to-close cancels out in the Bybit explicit formula
        (present in both IM and MM). The taker_fee_rate param is included
        for the cash-balance trigger form used in calculate_liquidation_price.

        When mm_deduction=0 (tier 1), the per-unit deduction term vanishes
        and the formula simplifies to the entry-price-only form.

        For the trigger-condition form (used in calculate_liquidation_price),
        fee-to-close affects MM so it shifts the liq price. This function
        uses the Bybit Help Center explicit formula which absorbs the fee
        terms algebraically.

        Use this when no ``Position`` object exists yet (e.g. SL-vs-liq
        pre-trade validation).

        Args:
            entry_price: Expected fill price.
            leverage: Position leverage (e.g. 50 for 50x).
            direction: 1 for long, -1 for short.
            maintenance_margin_rate: MMR as decimal (default 0.005 = 0.5%).
            taker_fee_rate: Taker fee rate (included for trigger-form parity).
            mm_deduction: Bybit mmDeduction for the risk tier.

        Returns:
            Estimated liquidation price (>= 0).
        """
        if leverage <= 0:
            return 0.0

        imr = 1.0 / leverage
        mmr_eff = maintenance_margin_rate + taker_fee_rate

        if direction == 1:  # Long
            denominator = 1.0 - mmr_eff
            if denominator <= 0:
                return 0.0
            liq_price = entry_price * (1.0 - imr) / denominator
        else:  # Short
            denominator = 1.0 + mmr_eff
            liq_price = entry_price * (1.0 + imr) / denominator

        # mm_deduction shifts the liq price (per-unit adjustment)
        # For long: farther from entry (more favorable)
        # For short: farther from entry (more favorable)
        if mm_deduction > 0 and entry_price > 0:
            # Qty = 1 unit at entry_price for the per-unit estimate
            # In practice, mmDeduction is fixed $ amount, so per-unit
            # adjustment depends on position size. For pre-trade estimation
            # without knowing exact qty, we skip the deduction adjustment.
            # The full formula in calculate_liquidation_price handles it.
            pass

        return max(0.0, liq_price)

