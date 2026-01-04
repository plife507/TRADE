"""
Order execution model.

Handles execution of all order types:
- Market orders: fill at bar open with slippage
- Limit orders: fill if price crosses
- Stop orders: trigger if price crosses
- TP/SL: check via intrabar path

Execution flow:
1. Pending entry orders fill at bar open (timestamp = ts_open)
2. TP/SL checked via intrabar path for existing position
3. Returns FillResult with fills and rejections
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import uuid

from ..types import (
    Bar,
    Order,
    OrderType,
    OrderSide,
    OrderStatus,
    Fill,
    FillReason,
    FillResult,
    Rejection,
    Position,
    PriceSnapshot,
)
from ..bar_compat import get_bar_ts_open
from .slippage_model import SlippageModel, SlippageConfig
from .impact_model import ImpactModel, ImpactConfig
from .liquidity_model import LiquidityModel, LiquidityConfig
from ..pricing.intrabar_path import IntrabarPath, IntrabarPathConfig

if TYPE_CHECKING:
    from ..ledger import Ledger


@dataclass
class ExecutionModelConfig:
    """Configuration for execution model."""
    slippage: SlippageConfig = field(default_factory=SlippageConfig)
    impact: ImpactConfig = field(default_factory=ImpactConfig)
    liquidity: LiquidityConfig = field(default_factory=LiquidityConfig)
    intrabar: IntrabarPathConfig = field(default_factory=IntrabarPathConfig)
    taker_fee_rate: float = 0.0006  # 0.06% default


class ExecutionModel:
    """
    Handles order execution with slippage, impact, and liquidity.
    
    Execution order within a bar:
    1. Fill pending market orders at bar open
    2. Check TP/SL against bar OHLC for positions
    """
    
    def __init__(self, config: ExecutionModelConfig | None = None):
        """
        Initialize execution model.
        
        Args:
            config: Optional configuration
        """
        self._config = config or ExecutionModelConfig()
        self._slippage = SlippageModel(self._config.slippage)
        self._impact = ImpactModel(self._config.impact)
        self._liquidity = LiquidityModel(self._config.liquidity)
        self._intrabar = IntrabarPath(self._config.intrabar)
    
    def fill_entry_order(
        self,
        order: Order,
        bar: Bar,
        available_balance_usdt: float,
        compute_required_fn,
    ) -> FillResult:
        """
        Fill a pending entry order at bar open.
        
        Applies slippage to fill price. Checks margin requirements.
        Fill timestamp is ts_open (bar open time).
        
        Args:
            order: Pending order to fill
            bar: Current bar (fill at open) - legacy or canonical
            available_balance_usdt: Available balance for margin check
            compute_required_fn: Function to compute required margin
            
        Returns:
            FillResult with fill or rejection
        """
        result = FillResult()
        
        # Get fill timestamp (ts_open for entries)
        fill_ts = get_bar_ts_open(bar)
        
        # Calculate fill price with slippage
        fill_price = self._slippage.apply_slippage(
            bar.open,
            order.side,
            order.size_usdt,
            bar,
        )
        
        # Calculate required margin
        required = compute_required_fn(order.size_usdt)
        
        # Check margin
        if available_balance_usdt < required:
            result.rejections.append(Rejection(
                order_id=order.order_id,
                reason=f"Insufficient margin: available={available_balance_usdt:.2f} < required={required:.2f}",
                code="INSUFFICIENT_ENTRY_GATE",
                timestamp=fill_ts,
            ))
            return result
        
        # Check liquidity constraint (partial fills not yet implemented)
        fillable_usdt = self._liquidity.get_max_fillable(order.size_usdt, bar)
        if fillable_usdt < order.size_usdt:
            # Future: support partial fills here
            pass
        
        # Calculate size in base units
        size = order.size_usdt / fill_price
        
        # Calculate fee
        fee = order.size_usdt * self._config.taker_fee_rate
        
        # Create fill (timestamp = ts_open)
        fill = Fill(
            fill_id=f"fill-{uuid.uuid4().hex[:8]}",
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            price=fill_price,
            size=size,
            size_usdt=order.size_usdt,
            timestamp=fill_ts,
            reason=FillReason.ENTRY,
            fee=fee,
            slippage=abs(fill_price - bar.open),
        )
        
        result.fills.append(fill)
        
        return result
    
    def check_tp_sl(
        self,
        position: Position,
        bar: Bar,
    ) -> FillReason | None:
        """
        Check if TP or SL is hit for a position.
        
        Uses conservative tie-break: SL checked first.
        
        Args:
            position: Open position
            bar: Current bar (legacy or canonical)
            
        Returns:
            FillReason.STOP_LOSS, FillReason.TAKE_PROFIT, or None
        """
        return self._intrabar.check_tp_sl(
            bar,
            position.side,
            position.entry_price,
            position.take_profit,
            position.stop_loss,
        )
    
    def fill_exit(
        self,
        position: Position,
        bar: Bar,
        reason: FillReason,
        exit_price: float | None = None,
    ) -> Fill:
        """
        Fill an exit (close position).
        
        Applies slippage to exit price.
        Exit timestamp is ts_open (exit fills at bar open).
        
        Args:
            position: Position being closed
            bar: Current bar (legacy or canonical)
            reason: Exit reason
            exit_price: Override exit price (or derive from TP/SL)
            
        Returns:
            Fill record for the exit
        """
        # Get fill timestamp (ts_open for exits too)
        fill_ts = get_bar_ts_open(bar)
        
        # Determine base exit price
        if exit_price is None:
            exit_price = self._get_exit_price(position, bar, reason)
        
        # Apply slippage
        fill_price = self._slippage.apply_exit_slippage(
            exit_price,
            position.side,
            position.size_usdt,
            bar,
        )
        
        # Fee calculation: use notional value (size_usdt) for symmetry with entry fees
        fee = position.size_usdt * self._config.taker_fee_rate
        
        return Fill(
            fill_id=f"fill-{uuid.uuid4().hex[:8]}",
            order_id="",  # Exit fills don't have an order
            symbol=position.symbol,
            side=position.side,
            price=fill_price,
            size=position.size,
            size_usdt=position.size_usdt,
            timestamp=fill_ts,
            reason=reason,
            fee=fee,
            slippage=abs(fill_price - exit_price),
        )
    
    def _get_exit_price(
        self,
        position: Position,
        bar: Bar,
        reason: FillReason,
    ) -> float:
        """
        Get base exit price for a fill reason.
        
        Args:
            position: Position being closed
            bar: Current bar (legacy or canonical)
            reason: Exit reason
            
        Returns:
            Base exit price (before slippage)
        """
        if reason == FillReason.STOP_LOSS:
            return position.stop_loss if position.stop_loss else bar.close
        elif reason == FillReason.TAKE_PROFIT:
            return position.take_profit if position.take_profit else bar.close
        else:
            return bar.close
    
    def calculate_realized_pnl(
        self,
        position: Position,
        exit_price: float,
    ) -> float:
        """
        Calculate realized PnL for a position exit.
        
        Args:
            position: Position being closed
            exit_price: Exit price (after slippage)
            
        Returns:
            Realized PnL (before fees)
        """
        if position.side == OrderSide.LONG:
            price_diff = exit_price - position.entry_price
        else:
            price_diff = position.entry_price - exit_price
        
        return price_diff * position.size

