"""
Liquidation model for mark-based liquidation.

Checks liquidation condition: equity <= maintenance_margin
Force closes position at mark price with liquidation fee.

No ADL (auto-deleveraging) in this implementation.

Bybit reference:
- Liquidation: reference/exchanges/bybit/docs/v5/order/close-order.mdx
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import uuid

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
    liquidation_fee_rate: float = 0.0006  # 0.06% liquidation fee
    # No ADL in Phase 1


class LiquidationModel:
    """
    Checks liquidation conditions and handles forced closure.
    
    Liquidation is triggered when:
    - equity_usdt <= maintenance_margin_usdt
    
    Position is closed at mark price with liquidation fee.
    """
    
    def __init__(self, config: Optional[LiquidationModelConfig] = None):
        """
        Initialize liquidation model.
        
        Args:
            config: Optional configuration
        """
        self._config = config or LiquidationModelConfig()
    
    def check_liquidation(
        self,
        ledger_state: LedgerState,
        prices: PriceSnapshot,
        position: Optional[Position],
    ) -> LiquidationResult:
        """
        Check if liquidation should occur.
        
        Liquidation condition:
        - equity_usdt <= maintenance_margin_usdt
        - Position must exist
        
        Args:
            ledger_state: Current ledger state
            prices: Current price snapshot
            position: Current open position
            
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
        
        # Calculate liquidation fee
        position_value = position.size * prices.mark_price
        liquidation_fee = position_value * self._config.liquidation_fee_rate
        
        # Create liquidation event
        result.event = LiquidationEvent(
            timestamp=prices.timestamp,
            symbol=position.symbol,
            side=position.side,
            mark_price=prices.mark_price,
            equity_usdt=ledger_state.equity_usdt,
            maintenance_margin_usdt=ledger_state.maintenance_margin_usdt,
            liquidation_fee=liquidation_fee,
        )
        
        # Create fill for the forced close
        result.fill = Fill(
            fill_id=f"liq-{uuid.uuid4().hex[:8]}",
            order_id="",
            symbol=position.symbol,
            side=position.side,
            price=prices.mark_price,
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
    ) -> float:
        """
        Calculate the liquidation price for a position.
        
        Liquidation occurs when:
        - equity = maintenance_margin
        - equity = cash + unrealized_pnl
        - maintenance_margin = position_value × MMR
        
        For longs: liq_price = entry - (cash - size × entry × MMR) / size
        For shorts: liq_price = entry + (cash - size × entry × MMR) / size
        
        Args:
            position: Open position
            cash_balance_usdt: Current cash balance
            maintenance_margin_rate: MMR as decimal
            
        Returns:
            Estimated liquidation price
        """
        entry = position.entry_price
        size = position.size
        
        # MM at entry = size × entry × MMR
        mm_at_entry = size * entry * maintenance_margin_rate
        
        # Buffer = cash - MM at entry
        buffer = cash_balance_usdt - mm_at_entry
        
        if size == 0:
            return 0.0
        
        # Price move that would exhaust buffer
        price_buffer = buffer / size
        
        if position.side == OrderSide.LONG:
            # Longs liquidate when price drops
            liq_price = entry - price_buffer
        else:
            # Shorts liquidate when price rises
            liq_price = entry + price_buffer
        
        return max(0.0, liq_price)

