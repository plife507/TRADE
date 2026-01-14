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

from ..types import (
    Bar,
    Order,
    OrderType,
    OrderSide,
    OrderStatus,
    TimeInForce,
    Fill,
    FillReason,
    FillResult,
    Rejection,
    Position,
    PriceSnapshot,
)
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
    taker_fee_rate: float = 0.0006  # 0.06% default (market orders)
    maker_fee_rate: float = 0.0001  # 0.01% default (limit orders)


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
        self._fill_counter: int = 0  # Deterministic fill IDs

    def reset(self) -> None:
        """Reset state for new backtest run."""
        self._fill_counter = 0

    def _next_fill_id(self) -> str:
        """Generate deterministic sequential fill ID."""
        self._fill_counter += 1
        return f"fill_{self._fill_counter:06d}"
    
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
        fill_ts = bar.ts_open
        
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
        
        # Check liquidity constraint
        # Note: Liquidity model is disabled by default (LiquidityConfig.mode="disabled")
        # When enabled, rejects orders that exceed available liquidity
        # (partial fills not implemented - would require order splitting)
        fillable_usdt = self._liquidity.get_max_fillable(order.size_usdt, bar)
        if fillable_usdt < order.size_usdt:
            result.rejections.append(Rejection(
                order_id=order.order_id,
                reason=f"Exceeds liquidity: requested={order.size_usdt:.2f} > available={fillable_usdt:.2f}",
                code="LIQUIDITY_EXCEEDED",
                timestamp=fill_ts,
            ))
            return result
        
        # Calculate size in base units
        size = order.size_usdt / fill_price
        
        # Calculate fee
        fee = order.size_usdt * self._config.taker_fee_rate
        
        # Create fill (timestamp = ts_open)
        fill = Fill(
            fill_id=self._next_fill_id(),
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

    def check_limit_fill(
        self,
        order: Order,
        bar: Bar,
    ) -> tuple[bool, float | None]:
        """
        Check if a limit order can be filled on this bar.

        Limit order fill logic (Bybit semantics):
        - Limit BUY: Fill if bar.low <= limit_price (price fell to our bid)
        - Limit SELL: Fill if bar.high >= limit_price (price rose to our ask)

        Fill price:
        - If bar opens at better price, get price improvement (fill at open)
        - Otherwise fill at limit_price

        Args:
            order: Limit order to check
            bar: Current bar OHLC

        Returns:
            Tuple of (can_fill: bool, fill_price: float | None)
        """
        if order.order_type != OrderType.LIMIT:
            return False, None

        if order.limit_price is None:
            return False, None

        limit_price = order.limit_price

        if order.side == OrderSide.LONG:
            # BUY limit: want to buy at limit_price or lower
            # Fill if bar.low <= limit_price (price dipped to our bid)
            if bar.low <= limit_price:
                # Price improvement: if bar opens below limit, fill at open
                if bar.open <= limit_price:
                    fill_price = bar.open
                else:
                    fill_price = limit_price
                return True, fill_price
        else:
            # SELL limit: want to sell at limit_price or higher
            # Fill if bar.high >= limit_price (price rose to our ask)
            if bar.high >= limit_price:
                # Price improvement: if bar opens above limit, fill at open
                if bar.open >= limit_price:
                    fill_price = bar.open
                else:
                    fill_price = limit_price
                return True, fill_price

        return False, None

    def fill_limit_order(
        self,
        order: Order,
        bar: Bar,
        available_balance_usdt: float,
        compute_required_fn,
        is_first_bar: bool = False,
    ) -> FillResult:
        """
        Attempt to fill a limit order on this bar.

        Handles time-in-force:
        - GTC: Stay active until filled or cancelled
        - IOC: Fill immediately or cancel (checked on first bar only)
        - FOK: Fill entirely or cancel (no partial fills)
        - POST_ONLY: Only fill as maker (reject if would fill at open)

        Args:
            order: Limit order to fill
            bar: Current bar
            available_balance_usdt: Available balance for margin check
            compute_required_fn: Function to compute required margin
            is_first_bar: True if this is the first bar after order submission

        Returns:
            FillResult with fill or rejection (or empty if not fillable)
        """
        result = FillResult()
        fill_ts = bar.ts_open

        # Check if order can fill on this bar
        can_fill, fill_price = self.check_limit_fill(order, bar)

        # Handle time-in-force
        tif = order.time_in_force

        if tif == TimeInForce.POST_ONLY:
            # POST_ONLY: Reject if would take liquidity (fill at open)
            if can_fill and fill_price == bar.open:
                result.rejections.append(Rejection(
                    order_id=order.order_id,
                    reason="PostOnly order would take liquidity",
                    code="POST_ONLY_REJECT",
                    timestamp=fill_ts,
                ))
                return result

        if tif == TimeInForce.IOC and is_first_bar:
            # IOC: Must fill immediately on first bar or cancel
            if not can_fill:
                result.rejections.append(Rejection(
                    order_id=order.order_id,
                    reason="IOC order could not fill immediately",
                    code="IOC_CANCEL",
                    timestamp=fill_ts,
                ))
                return result

        if tif == TimeInForce.FOK and is_first_bar:
            # FOK: Must fill entirely on first bar or cancel
            # (Since we don't do partial fills, this is same as IOC)
            if not can_fill:
                result.rejections.append(Rejection(
                    order_id=order.order_id,
                    reason="FOK order could not fill entirely",
                    code="FOK_CANCEL",
                    timestamp=fill_ts,
                ))
                return result

        if not can_fill:
            # Order stays in book (GTC behavior)
            result.orders_remaining.append(order)
            return result

        # Check margin before fill
        required = compute_required_fn(order.size_usdt)
        if available_balance_usdt < required:
            result.rejections.append(Rejection(
                order_id=order.order_id,
                reason=f"Insufficient margin: available={available_balance_usdt:.2f} < required={required:.2f}",
                code="INSUFFICIENT_MARGIN",
                timestamp=fill_ts,
            ))
            return result

        # Execute fill
        # For limit orders, apply minimal slippage (maker fill)
        size = order.size_usdt / fill_price
        fee = order.size_usdt * self._config.maker_fee_rate  # Limit orders use maker fee

        fill = Fill(
            fill_id=self._next_fill_id(),
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            price=fill_price,
            size=size,
            size_usdt=order.size_usdt,
            timestamp=fill_ts,
            reason=FillReason.ENTRY,
            fee=fee,
            slippage=0.0,  # Limit orders fill at limit price or better
        )

        result.fills.append(fill)
        return result

    def fill_triggered_stop(
        self,
        order: Order,
        bar: Bar,
        available_balance_usdt: float,
        compute_required_fn,
    ) -> FillResult:
        """
        Fill a stop order that has been triggered.

        Stop order execution (after trigger):
        - STOP_MARKET: Fill at bar.open with slippage (same as market order)
        - STOP_LIMIT: Check if limit_price is reachable, fill at limit

        Args:
            order: Triggered stop order
            bar: Current bar (fill at open)
            available_balance_usdt: Available balance for margin check
            compute_required_fn: Function to compute required margin

        Returns:
            FillResult with fill or rejection
        """
        if order.order_type == OrderType.STOP_MARKET:
            # STOP_MARKET: Execute as market order
            return self.fill_entry_order(
                order, bar, available_balance_usdt, compute_required_fn
            )
        elif order.order_type == OrderType.STOP_LIMIT:
            # STOP_LIMIT: Execute as limit order
            return self.fill_limit_order(
                order, bar, available_balance_usdt, compute_required_fn,
                is_first_bar=True,  # Treat as first bar for TIF
            )
        else:
            # Not a stop order, shouldn't happen
            result = FillResult()
            result.rejections.append(Rejection(
                order_id=order.order_id,
                reason=f"Invalid order type for stop fill: {order.order_type}",
                code="INVALID_ORDER_TYPE",
                timestamp=bar.ts_open,
            ))
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
        close_ratio: float = 1.0,
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
            close_ratio: Fraction of position to close (0.0-1.0). Default 1.0 = full close.

        Returns:
            Fill record for the exit
        """
        # Validate close_ratio
        if not 0.0 < close_ratio <= 1.0:
            raise ValueError(f"close_ratio must be in (0.0, 1.0], got {close_ratio}")

        # Get fill timestamp (ts_open for exits too)
        fill_ts = bar.ts_open

        # Determine base exit price
        if exit_price is None:
            exit_price = self._get_exit_price(position, bar, reason)

        # Calculate sizes for this fill (proportional to close_ratio)
        fill_size = position.size * close_ratio
        fill_size_usdt = position.size_usdt * close_ratio

        # Apply slippage (based on the portion being closed)
        fill_price = self._slippage.apply_exit_slippage(
            exit_price,
            position.side,
            fill_size_usdt,
            bar,
        )

        # Fee calculation: use EXIT notional (qty * exit price), not entry notional
        # This is critical for accuracy when price has moved significantly since entry
        exit_notional = fill_size * fill_price
        fee = exit_notional * self._config.taker_fee_rate

        return Fill(
            fill_id=self._next_fill_id(),
            order_id="",  # Exit fills don't have an order
            symbol=position.symbol,
            side=position.side,
            price=fill_price,
            size=fill_size,
            size_usdt=fill_size_usdt,
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

    def check_reduce_only(
        self,
        order: Order,
        position: Position | None,
    ) -> tuple[bool, float | None, str | None]:
        """
        Check if reduce_only order is valid and compute allowed size.

        Reduce-only rules:
        1. Must have an open position
        2. Order side must be opposite to position side
        3. Order size clamped to position size (no flip)

        Args:
            order: Order with reduce_only flag
            position: Current open position (or None)

        Returns:
            Tuple of (is_valid, clamped_size_usdt, error_reason)
            - is_valid: True if order can proceed
            - clamped_size_usdt: Size to use (may be reduced)
            - error_reason: Error message if invalid
        """
        if not order.reduce_only:
            # Not a reduce-only order, no constraint
            return True, order.size_usdt, None

        if position is None:
            return False, None, "Reduce-only order but no position to reduce"

        # Check direction: reduce-only must be opposite side
        if order.side == position.side:
            return False, None, f"Reduce-only {order.side.value} but position is also {position.side.value}"

        # Clamp size to position size (prevent flip)
        if order.size_usdt > position.size_usdt:
            clamped = position.size_usdt
            return True, clamped, None

        return True, order.size_usdt, None

