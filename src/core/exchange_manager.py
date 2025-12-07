"""
Unified exchange interface.

Provides a consistent API for trading operations across exchanges.
Currently supports Bybit only; designed for easy extension to HyperLiquid.

Professional Trading Features:
- Market orders (buy/sell with optional TP/SL)
- Limit orders (buy/sell with time-in-force options)
- Conditional/Stop orders (trigger-based market/limit)
- Order management (get, cancel, amend)
- Position management (TP/SL, trailing stop, margin mode)
- Batch order support
"""

from typing import Dict, List, Optional, Any, Literal
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from enum import Enum

from ..exchanges.bybit_client import BybitClient, BybitAPIError
from ..config.config import get_config, TradingMode
from ..utils.logger import get_logger
from ..utils.helpers import safe_float
from ..utils.time_range import TimeRange


# ==================== Type Definitions ====================

class TimeInForce(str, Enum):
    """Order time-in-force options."""
    GTC = "GTC"      # Good Till Cancel - stays until filled or cancelled
    IOC = "IOC"      # Immediate Or Cancel - fill what you can, cancel rest
    FOK = "FOK"      # Fill Or Kill - fill entire order or cancel
    POST_ONLY = "PostOnly"  # Maker only - cancelled if would take liquidity


class TriggerBy(str, Enum):
    """Price type for trigger orders."""
    LAST_PRICE = "LastPrice"
    INDEX_PRICE = "IndexPrice"
    MARK_PRICE = "MarkPrice"


class TriggerDirection(int, Enum):
    """Direction for conditional order trigger."""
    RISE = 1   # Trigger when price rises to trigger_price
    FALL = 2   # Trigger when price falls to trigger_price


# ==================== Data Classes ====================

@dataclass
class Position:
    """Normalized position data."""
    symbol: str
    exchange: str
    position_type: str  # "futures" or "spot"
    side: str  # "long", "short", or "none"
    size: float  # Position size in contracts
    size_usd: float  # Position value in USD
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    leverage: float
    margin_mode: str  # "isolated" or "cross"
    liquidation_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    trailing_stop: Optional[float] = None
    adl_rank: Optional[int] = None  # Auto-deleverage rank indicator
    is_reduce_only: bool = False  # True when position can only be reduced
    cumulative_pnl: Optional[float] = None  # All-time realized PnL
    
    @property
    def is_open(self) -> bool:
        return abs(self.size) > 0


@dataclass
class Order:
    """Normalized open order data."""
    order_id: str
    order_link_id: Optional[str]
    symbol: str
    side: str  # "Buy" or "Sell"
    order_type: str  # "Market", "Limit"
    price: Optional[float]
    qty: float
    filled_qty: float
    remaining_qty: float
    status: str  # "New", "PartiallyFilled", "Untriggered"
    time_in_force: str
    reduce_only: bool
    trigger_price: Optional[float] = None
    trigger_by: Optional[str] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    created_time: Optional[str] = None
    updated_time: Optional[str] = None
    
    @property
    def is_conditional(self) -> bool:
        return self.trigger_price is not None
    
    @property 
    def is_active(self) -> bool:
        return self.status in ("New", "PartiallyFilled", "Untriggered")


@dataclass
class OrderResult:
    """Normalized order result."""
    success: bool
    order_id: Optional[str] = None
    order_link_id: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    order_type: Optional[str] = None
    qty: Optional[float] = None
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    time_in_force: Optional[str] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    reduce_only: bool = False
    error: Optional[str] = None
    raw_response: Optional[dict] = None


class ExchangeManager:
    """
    Unified exchange manager.
    
    Provides high-level trading operations with:
    - Automatic position sizing (USD to quantity)
    - Minimum size validation
    - Leverage management
    - Error handling
    """
    
    def __init__(self):
        """Initialize exchange manager."""
        self.config = get_config()
        self.logger = get_logger()
        
        # === STRICT MODE/API MAPPING ASSERTION ===
        # Only two valid combinations: PAPER+DEMO or REAL+LIVE
        trading_mode = self.config.trading.mode
        use_demo = self.config.bybit.use_demo
        
        valid_paper = (trading_mode == TradingMode.PAPER and use_demo == True)
        valid_real = (trading_mode == TradingMode.REAL and use_demo == False)
        
        if not (valid_paper or valid_real):
            raise ValueError(
                f"INVALID MODE/API MAPPING: TRADING_MODE={trading_mode}, BYBIT_USE_DEMO={use_demo}. "
                f"Valid combinations: (paper, True) or (real, False)."
            )
        
        self.use_demo = use_demo
        
        # Get API credentials
        api_key, api_secret = self.config.bybit.get_credentials()
        
        # Initialize Bybit client with official pybit library
        self.bybit = BybitClient(
            api_key=api_key,
            api_secret=api_secret,
            use_demo=self.use_demo,  # Demo or live trading
        )
        
        # Log detailed trading environment info
        mode = "DEMO (fake money)" if self.use_demo else "LIVE (REAL MONEY!)"
        key_status = "authenticated" if api_key else "NO KEY"
        trading_mode = self.config.trading.mode
        
        # Determine key source for logging (STRICT - canonical keys only)
        if self.use_demo:
            if self.config.bybit.demo_api_key:
                key_source = "BYBIT_DEMO_API_KEY"
            else:
                key_source = "MISSING (BYBIT_DEMO_API_KEY required)"
        else:
            if self.config.bybit.live_api_key:
                key_source = "BYBIT_LIVE_API_KEY"
            else:
                key_source = "MISSING (BYBIT_LIVE_API_KEY required)"
        
        self.logger.info(
            f"ExchangeManager initialized: "
            f"API={mode}, "
            f"base_url={self.bybit.base_url}, "
            f"trading_mode={trading_mode}, "
            f"auth={key_status}, "
            f"key_source={key_source}"
        )
        
        # Cache for instrument info (min sizes, tick sizes, etc.)
        self._instruments: Dict[str, dict] = {}
        
        # Track previous position states for WebSocket-based cleanup
        self._previous_positions: Dict[str, bool] = {}  # symbol -> was_open
        
        # Setup WebSocket callbacks for automatic conditional order cleanup
        self._setup_websocket_cleanup()
    
    def _setup_websocket_cleanup(self):
        """
        Setup WebSocket callbacks for automatic conditional order cleanup.
        
        When a position closes (SL hit, TP filled, manual close), this automatically
        cancels any remaining conditional TP orders to prevent orphaned orders.
        """
        try:
            from ..data.realtime_state import get_realtime_state
            state = get_realtime_state()
            
            # Register callback for position updates
            state.on_position_update(self._on_position_update_cleanup)
            
            self.logger.info("WebSocket cleanup callback registered for position updates")
        except ImportError:
            self.logger.debug("RealtimeState not available - WebSocket cleanup disabled")
        except Exception as e:
            self.logger.warning(f"Could not setup WebSocket cleanup: {e}")
    
    def _validate_trading_operation(self) -> None:
        """
        SAFETY GUARD RAIL: Validate that trading operation is safe to execute.
        
        This prevents dangerous mismatches between TRADING_MODE and BYBIT_USE_DEMO.
        
        Raises:
            ValueError: If there's a dangerous mismatch that could lead to 
                       unexpected behavior (e.g., user thinks they're live trading
                       but they're on demo)
        """
        # Reload config to get fresh values (in case env changed)
        config = get_config()
        
        # === STRICT MODE/API MAPPING ===
        # Only two valid combinations: PAPER+DEMO or REAL+LIVE
        # Both execute real orders on Bybit; the difference is which account.
        
        # INVALID: REAL mode on DEMO API
        if config.trading.mode == TradingMode.REAL and config.bybit.use_demo:
            raise ValueError(
                "INVALID CONFIGURATION: TRADING_MODE=real but BYBIT_USE_DEMO=true. "
                "REAL mode requires LIVE API. Orders would go to DEMO account instead of LIVE. "
                "Set BYBIT_USE_DEMO=false for live trading, or use TRADING_MODE=paper for demo."
            )
        
        # INVALID: PAPER mode on LIVE API
        if config.trading.mode == TradingMode.PAPER and not config.bybit.use_demo:
            raise ValueError(
                "INVALID CONFIGURATION: TRADING_MODE=paper but BYBIT_USE_DEMO=false. "
                "PAPER mode requires DEMO API. Orders would go to LIVE account with real money. "
                "Set BYBIT_USE_DEMO=true for paper/demo trading, or use TRADING_MODE=real for live."
            )
    
    def _on_position_update_cleanup(self, position_data):
        """
        Callback triggered when position updates via WebSocket.
        
        Automatically cancels conditional TP orders when position closes.
        Also handles symbol unsubscription when positions close.
        Only cancels orders with bot-generated order_link_id pattern.
        """
        try:
            symbol = position_data.symbol
            was_open = self._previous_positions.get(symbol, False)
            is_open = position_data.is_open if hasattr(position_data, 'is_open') else position_data.size > 0
            
            # Detect position closure (was open, now closed)
            if was_open and not is_open:
                self.logger.info(
                    f"Position closed for {symbol} (detected via WebSocket) - "
                    f"cleaning up conditional orders"
                )
                
                # Cancel all bot-generated conditional reduce-only orders for this symbol
                cancelled = self._cancel_conditional_orders_for_symbol(symbol)
                
                if cancelled:
                    self.logger.info(
                        f"Auto-cancelled {len(cancelled)} conditional orders for {symbol}"
                    )
                
                # Remove symbol from websocket tracking (no longer needed)
                # Note: pybit doesn't support dynamic unsubscription, but we stop tracking it
                self._remove_symbol_from_websocket(symbol)
            
            # Update tracking
            self._previous_positions[symbol] = is_open
        
        except Exception as e:
            # Don't let callback errors break WebSocket processing
            self.logger.warning(f"Error in position cleanup callback for {position_data.symbol}: {e}")
    
    def _cancel_conditional_orders_for_symbol(self, symbol: str) -> List[str]:
        """
        Cancel all bot-generated conditional reduce-only orders for a symbol.
        
        Used when position closes and we don't know the original side.
        Only cancels orders with bot-generated order_link_id pattern.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            List of cancelled order identifiers
        """
        import re
        cancelled = []
        
        try:
            orders = self.get_open_orders(symbol)
            
            # Pattern for bot-generated TP orders: TP1_BTCUSDT_1234567890
            tp_pattern = re.compile(rf"^TP\d+_{re.escape(symbol)}_\d+$")
            
            # Cancel all bot-generated conditional reduce-only orders
            orders_to_cancel = [
                order for order in orders
                if order.is_conditional
                and order.reduce_only
                and order.is_active
                and order.order_link_id
                and tp_pattern.match(order.order_link_id)
            ]
            
            for order in orders_to_cancel:
                try:
                    if self.cancel_order(
                        symbol=symbol,
                        order_id=order.order_id,
                        order_link_id=order.order_link_id,
                    ):
                        cancelled.append(order.order_link_id or order.order_id)
                except Exception as e:
                    self.logger.warning(f"Failed to cancel order: {e}")
        
        except Exception as e:
            self.logger.warning(f"Error cancelling conditional orders for {symbol}: {e}")
        
        return cancelled
    
    # ==================== Market Data ====================
    
    def get_price(self, symbol: str) -> float:
        """Get current market price."""
        ticker = self.bybit.get_ticker(symbol)
        return float(ticker.get("lastPrice", 0))
    
    def get_bid_ask(self, symbol: str) -> tuple[float, float]:
        """Get current bid and ask prices."""
        ticker = self.bybit.get_ticker(symbol)
        return (
            float(ticker.get("bid1Price", 0)),
            float(ticker.get("ask1Price", 0))
        )
    
    # ==================== Account ====================
    
    def get_balance(self) -> Dict[str, float]:
        """
        Get account balance.
        
        Returns:
            Dict with 'total', 'available', 'used' in USD
        """
        balance = self.bybit.get_balance()
        
        # Find USDT balance
        total = 0.0
        available = 0.0
        
        for coin in balance.get("coin", []):
            if coin.get("coin") == "USDT":
                total = safe_float(coin.get("walletBalance", 0))
                # Try different fields for available balance
                available = safe_float(coin.get("availableToWithdraw")) or \
                           safe_float(coin.get("availableToBorrow")) or \
                           safe_float(coin.get("equity")) or \
                           total
                break
        
        return {
            "total": total,
            "available": available,
            "used": total - available,
            "currency": "USDT",
        }
    
    def get_account_value(self) -> float:
        """Get total account value in USD."""
        balance = self.get_balance()
        return balance.get("total", 0.0)
    
    # ==================== Positions ====================
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get position for a specific symbol.
        
        Returns:
            Position object or None if no position
        """
        positions = self.bybit.get_positions(symbol)
        
        for pos in positions:
            if pos.get("symbol") == symbol:
                size = safe_float(pos.get("size", 0))
                if size == 0:
                    continue
                
                side = pos.get("side", "").lower()
                if side == "buy":
                    side = "long"
                elif side == "sell":
                    side = "short"
                
                entry_price = safe_float(pos.get("avgPrice", 0))
                current_price = safe_float(pos.get("markPrice", 0))
                unrealized_pnl = safe_float(pos.get("unrealisedPnl", 0))
                
                return Position(
                    symbol=symbol,
                    exchange="bybit",
                    position_type="futures",
                    side=side,
                    size=size,
                    size_usd=size * current_price,
                    entry_price=entry_price,
                    current_price=current_price,
                    unrealized_pnl=unrealized_pnl,
                    unrealized_pnl_percent=unrealized_pnl / (size * entry_price) * 100 if size and entry_price else 0,
                    leverage=safe_float(pos.get("leverage", 1), 1),
                    margin_mode=pos.get("tradeMode", "cross"),
                    liquidation_price=safe_float(pos.get("liqPrice")) if pos.get("liqPrice") else None,
                    take_profit=safe_float(pos.get("takeProfit")) if pos.get("takeProfit") else None,
                    stop_loss=safe_float(pos.get("stopLoss")) if pos.get("stopLoss") else None,
                    trailing_stop=safe_float(pos.get("trailingStop")) if pos.get("trailingStop") else None,
                    adl_rank=int(pos.get("adlRankIndicator", 0)) if pos.get("adlRankIndicator") else None,
                    is_reduce_only=pos.get("isReduceOnly", False),
                    cumulative_pnl=safe_float(pos.get("cumRealisedPnl")) if pos.get("cumRealisedPnl") else None,
                )
        
        return None
    
    def get_all_positions(self) -> List[Position]:
        """
        Get all open positions.
        
        Returns:
            List of Position objects
        """
        positions = []
        raw_positions = self.bybit.get_positions()
        
        for pos in raw_positions:
            size = safe_float(pos.get("size", 0))
            if size == 0:
                continue
            
            symbol = pos.get("symbol")
            side = pos.get("side", "").lower()
            if side == "buy":
                side = "long"
            elif side == "sell":
                side = "short"
            
            entry_price = safe_float(pos.get("avgPrice", 0))
            current_price = safe_float(pos.get("markPrice", 0))
            unrealized_pnl = safe_float(pos.get("unrealisedPnl", 0))
            
            positions.append(Position(
                symbol=symbol,
                exchange="bybit",
                position_type="futures",
                side=side,
                size=size,
                size_usd=size * current_price,
                entry_price=entry_price,
                current_price=current_price,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_percent=unrealized_pnl / (size * entry_price) * 100 if size and entry_price else 0,
                leverage=safe_float(pos.get("leverage", 1), 1),
                margin_mode=pos.get("tradeMode", "cross"),
                liquidation_price=safe_float(pos.get("liqPrice")) if pos.get("liqPrice") else None,
                take_profit=safe_float(pos.get("takeProfit")) if pos.get("takeProfit") else None,
                stop_loss=safe_float(pos.get("stopLoss")) if pos.get("stopLoss") else None,
                trailing_stop=safe_float(pos.get("trailingStop")) if pos.get("trailingStop") else None,
                adl_rank=int(pos.get("adlRankIndicator", 0)) if pos.get("adlRankIndicator") else None,
                is_reduce_only=pos.get("isReduceOnly", False),
                cumulative_pnl=safe_float(pos.get("cumRealisedPnl")) if pos.get("cumRealisedPnl") else None,
            ))
        
        return positions
    
    def get_total_exposure(self) -> float:
        """Get total position exposure in USD."""
        positions = self.get_all_positions()
        return sum(pos.size_usd for pos in positions)
    
    # ==================== Trading Helpers ====================
    
    def _get_instrument_info(self, symbol: str) -> dict:
        """Get and cache instrument specifications."""
        if symbol not in self._instruments:
            instruments = self.bybit.get_instruments(symbol)
            if instruments:
                self._instruments[symbol] = instruments[0]
        return self._instruments.get(symbol, {})
    
    def _round_price(self, symbol: str, price: float) -> float:
        """
        Round price to valid tick size for symbol.
        
        Args:
            symbol: Trading symbol
            price: Price to round
        
        Returns:
            Price rounded to valid tick size
        """
        info = self._get_instrument_info(symbol)
        price_filter = info.get("priceFilter", {})
        tick_size = float(price_filter.get("tickSize", "0.01"))
        
        # Round to tick size
        rounded = float(Decimal(str(price)).quantize(
            Decimal(str(tick_size)), 
            rounding=ROUND_HALF_UP
        ))
        return rounded
    
    def _get_tick_size(self, symbol: str) -> float:
        """Get the minimum price increment for a symbol."""
        info = self._get_instrument_info(symbol)
        price_filter = info.get("priceFilter", {})
        return float(price_filter.get("tickSize", "0.01"))
    
    def _get_min_qty(self, symbol: str) -> float:
        """Get the minimum order quantity for a symbol."""
        info = self._get_instrument_info(symbol)
        lot_size = info.get("lotSizeFilter", {})
        return float(lot_size.get("minOrderQty", "0.001"))
    
    def _calculate_qty(self, symbol: str, usd_amount: float, price: float = None) -> float:
        """
        Calculate order quantity from USD amount.
        
        Args:
            symbol: Trading symbol
            usd_amount: Amount in USD
            price: Price to use (None = current market price)
        
        Returns:
            Quantity in contracts/coins, rounded to valid precision
        """
        if price is None:
            price = self.get_price(symbol)
        
        if price <= 0:
            raise ValueError(f"Invalid price for {symbol}: {price}")
        
        # Get instrument info for precision
        info = self._get_instrument_info(symbol)
        lot_size = info.get("lotSizeFilter", {})
        
        qty_step = float(lot_size.get("qtyStep", "0.001"))
        min_qty = float(lot_size.get("minOrderQty", "0.001"))
        
        # Calculate base quantity
        qty = usd_amount / price
        
        # Round down to step size
        qty = float(Decimal(str(qty)).quantize(Decimal(str(qty_step)), rounding=ROUND_DOWN))
        
        # Ensure minimum
        if qty < min_qty:
            self.logger.warning(f"Order size {qty} below minimum {min_qty} for {symbol}")
            return 0.0
        
        return qty
    
    def _ensure_symbol_tracked(self, symbol: str):
        """
        Ensure symbol is tracked for real-time updates.
        
        Dynamically subscribes to WebSocket streams for the symbol
        if not already subscribed. This enables real-time market data
        and position updates for the symbol.
        
        Only subscribes if websocket is running (for risk manager).
        
        Args:
            symbol: Symbol to track (e.g., "SOLUSDT")
        """
        try:
            from ..data.realtime_bootstrap import get_realtime_bootstrap
            
            bootstrap = get_realtime_bootstrap()
            if bootstrap and bootstrap.is_running:
                bootstrap.ensure_symbol_subscribed(symbol)
        except Exception:
            pass  # WebSocket not available, REST fallback will be used
    
    def _remove_symbol_from_websocket(self, symbol: str):
        """
        Remove symbol from websocket tracking when position closes.
        
        Note: pybit doesn't support dynamic unsubscription, but we stop
        tracking the symbol. The websocket will continue receiving data
        but we'll ignore it.
        
        Args:
            symbol: Symbol to remove from tracking
        """
        try:
            from ..data.realtime_bootstrap import get_realtime_bootstrap
            
            bootstrap = get_realtime_bootstrap()
            if bootstrap:
                bootstrap.remove_symbol(symbol)
                self.logger.debug(f"Removed {symbol} from websocket tracking (position closed)")
        except Exception as e:
            self.logger.debug(f"Could not remove {symbol} from websocket: {e}")
    
    def market_buy(self, symbol: str, usd_amount: float) -> OrderResult:
        """
        Place a market buy order.
        
        Args:
            symbol: Trading symbol
            usd_amount: Amount to buy in USD
        
        Returns:
            OrderResult with success status and details
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            # Ensure we're tracking this symbol for real-time updates
            self._ensure_symbol_tracked(symbol)
            
            price = self.get_price(symbol)
            qty = self._calculate_qty(symbol, usd_amount, price)
            
            if qty <= 0:
                return OrderResult(
                    success=False,
                    error=f"Order size too small for {symbol}"
                )
            
            result = self.bybit.create_order(
                symbol=symbol,
                side="Buy",
                order_type="Market",
                qty=qty,
            )
            
            self.logger.trade(
                "ORDER_FILLED",
                symbol=symbol,
                side="BUY",
                size=usd_amount,
                price=price,
                qty=qty
            )
            
            return OrderResult(
                success=True,
                order_id=result.get("orderId"),
                symbol=symbol,
                side="Buy",
                order_type="Market",
                qty=qty,
                price=price,
                raw_response=result,
            )
            
        except BybitAPIError as e:
            self.logger.error(f"Market buy failed: {e}")
            return OrderResult(success=False, error=str(e))
        except Exception as e:
            self.logger.error(f"Market buy error: {e}")
            return OrderResult(success=False, error=str(e))
    
    def market_sell(self, symbol: str, usd_amount: float) -> OrderResult:
        """
        Place a market sell order (short).
        
        Args:
            symbol: Trading symbol
            usd_amount: Amount to sell in USD
        
        Returns:
            OrderResult with success status and details
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            # Ensure we're tracking this symbol for real-time updates
            self._ensure_symbol_tracked(symbol)
            
            price = self.get_price(symbol)
            qty = self._calculate_qty(symbol, usd_amount, price)
            
            if qty <= 0:
                return OrderResult(
                    success=False,
                    error=f"Order size too small for {symbol}"
                )
            
            result = self.bybit.create_order(
                symbol=symbol,
                side="Sell",
                order_type="Market",
                qty=qty,
            )
            
            self.logger.trade(
                "ORDER_FILLED",
                symbol=symbol,
                side="SELL",
                size=usd_amount,
                price=price,
                qty=qty
            )
            
            return OrderResult(
                success=True,
                order_id=result.get("orderId"),
                symbol=symbol,
                side="Sell",
                order_type="Market",
                qty=qty,
                price=price,
                raw_response=result,
            )
            
        except BybitAPIError as e:
            self.logger.error(f"Market sell failed: {e}")
            return OrderResult(success=False, error=str(e))
        except Exception as e:
            self.logger.error(f"Market sell error: {e}")
            return OrderResult(success=False, error=str(e))
    
    # ==================== Limit Orders ====================
    
    def limit_buy(
        self,
        symbol: str,
        usd_amount: float,
        price: float,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        order_link_id: str = None,
    ) -> OrderResult:
        """
        Place a limit buy order.
        
        Args:
            symbol: Trading symbol
            usd_amount: Amount in USD
            price: Limit price
            time_in_force: GTC, IOC, FOK, or PostOnly
            reduce_only: Only reduce position (close only)
            order_link_id: Custom order ID
        
        Returns:
            OrderResult with order details
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            # Ensure we're tracking this symbol for real-time updates
            self._ensure_symbol_tracked(symbol)
            
            price = self._round_price(symbol, price)
            qty = self._calculate_qty(symbol, usd_amount, price)
            
            if qty <= 0:
                return OrderResult(
                    success=False,
                    error=f"Order size too small for {symbol}"
                )
            
            result = self.bybit.create_order(
                symbol=symbol,
                side="Buy",
                order_type="Limit",
                qty=qty,
                price=str(price),
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                order_link_id=order_link_id,
            )
            
            self.logger.trade(
                "LIMIT_ORDER_PLACED",
                symbol=symbol,
                side="BUY",
                size=usd_amount,
                price=price,
                qty=qty,
                tif=time_in_force
            )
            
            return OrderResult(
                success=True,
                order_id=result.get("orderId"),
                order_link_id=result.get("orderLinkId"),
                symbol=symbol,
                side="Buy",
                order_type="Limit",
                qty=qty,
                price=price,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                raw_response=result,
            )
            
        except BybitAPIError as e:
            self.logger.error(f"Limit buy failed: {e}")
            return OrderResult(success=False, error=str(e))
        except Exception as e:
            self.logger.error(f"Limit buy error: {e}")
            return OrderResult(success=False, error=str(e))
    
    def limit_sell(
        self,
        symbol: str,
        usd_amount: float,
        price: float,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        order_link_id: str = None,
    ) -> OrderResult:
        """
        Place a limit sell order (short or close long).
        
        Args:
            symbol: Trading symbol
            usd_amount: Amount in USD
            price: Limit price
            time_in_force: GTC, IOC, FOK, or PostOnly
            reduce_only: Only reduce position (close only)
            order_link_id: Custom order ID
        
        Returns:
            OrderResult with order details
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            # Ensure we're tracking this symbol for real-time updates
            self._ensure_symbol_tracked(symbol)
            
            price = self._round_price(symbol, price)
            qty = self._calculate_qty(symbol, usd_amount, price)
            
            if qty <= 0:
                return OrderResult(
                    success=False,
                    error=f"Order size too small for {symbol}"
                )
            
            result = self.bybit.create_order(
                symbol=symbol,
                side="Sell",
                order_type="Limit",
                qty=qty,
                price=str(price),
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                order_link_id=order_link_id,
            )
            
            self.logger.trade(
                "LIMIT_ORDER_PLACED",
                symbol=symbol,
                side="SELL",
                size=usd_amount,
                price=price,
                qty=qty,
                tif=time_in_force
            )
            
            return OrderResult(
                success=True,
                order_id=result.get("orderId"),
                order_link_id=result.get("orderLinkId"),
                symbol=symbol,
                side="Sell",
                order_type="Limit",
                qty=qty,
                price=price,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                raw_response=result,
            )
            
        except BybitAPIError as e:
            self.logger.error(f"Limit sell failed: {e}")
            return OrderResult(success=False, error=str(e))
        except Exception as e:
            self.logger.error(f"Limit sell error: {e}")
            return OrderResult(success=False, error=str(e))
    
    def limit_buy_with_tpsl(
        self,
        symbol: str,
        usd_amount: float,
        price: float,
        take_profit: float = None,
        stop_loss: float = None,
        time_in_force: str = "GTC",
        tpsl_mode: str = "Full",
        tp_order_type: str = "Market",
        sl_order_type: str = "Market",
        order_link_id: str = None,
    ) -> OrderResult:
        """
        Place a limit buy order with TP/SL.
        
        Args:
            symbol: Trading symbol
            usd_amount: Amount in USD
            price: Limit price
            take_profit: Take profit price
            stop_loss: Stop loss price
            time_in_force: GTC, IOC, FOK, or PostOnly
            tpsl_mode: "Full" (entire position) or "Partial"
            tp_order_type: "Market" or "Limit" for TP execution
            sl_order_type: "Market" or "Limit" for SL execution
            order_link_id: Custom order ID
        
        Returns:
            OrderResult with order details
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            price = self._round_price(symbol, price)
            qty = self._calculate_qty(symbol, usd_amount, price)
            
            if qty <= 0:
                return OrderResult(
                    success=False,
                    error=f"Order size too small for {symbol}"
                )
            
            result = self.bybit.create_order(
                symbol=symbol,
                side="Buy",
                order_type="Limit",
                qty=qty,
                price=str(price),
                time_in_force=time_in_force,
                take_profit=str(take_profit) if take_profit else None,
                stop_loss=str(stop_loss) if stop_loss else None,
                tpsl_mode=tpsl_mode if (take_profit or stop_loss) else None,
                tp_order_type=tp_order_type if take_profit else None,
                sl_order_type=sl_order_type if stop_loss else None,
                order_link_id=order_link_id,
            )
            
            self.logger.trade(
                "LIMIT_ORDER_PLACED",
                symbol=symbol,
                side="BUY",
                size=usd_amount,
                price=price,
                qty=qty,
                tp=take_profit,
                sl=stop_loss
            )
            
            return OrderResult(
                success=True,
                order_id=result.get("orderId"),
                order_link_id=result.get("orderLinkId"),
                symbol=symbol,
                side="Buy",
                order_type="Limit",
                qty=qty,
                price=price,
                time_in_force=time_in_force,
                take_profit=take_profit,
                stop_loss=stop_loss,
                raw_response=result,
            )
            
        except BybitAPIError as e:
            self.logger.error(f"Limit buy with TP/SL failed: {e}")
            return OrderResult(success=False, error=str(e))
        except Exception as e:
            self.logger.error(f"Limit buy with TP/SL error: {e}")
            return OrderResult(success=False, error=str(e))
    
    def limit_sell_with_tpsl(
        self,
        symbol: str,
        usd_amount: float,
        price: float,
        take_profit: float = None,
        stop_loss: float = None,
        time_in_force: str = "GTC",
        tpsl_mode: str = "Full",
        tp_order_type: str = "Market",
        sl_order_type: str = "Market",
        order_link_id: str = None,
    ) -> OrderResult:
        """
        Place a limit sell order with TP/SL (short).
        
        Args:
            symbol: Trading symbol
            usd_amount: Amount in USD
            price: Limit price
            take_profit: Take profit price
            stop_loss: Stop loss price
            time_in_force: GTC, IOC, FOK, or PostOnly
            tpsl_mode: "Full" (entire position) or "Partial"
            tp_order_type: "Market" or "Limit" for TP execution
            sl_order_type: "Market" or "Limit" for SL execution
            order_link_id: Custom order ID
        
        Returns:
            OrderResult with order details
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            price = self._round_price(symbol, price)
            qty = self._calculate_qty(symbol, usd_amount, price)
            
            if qty <= 0:
                return OrderResult(
                    success=False,
                    error=f"Order size too small for {symbol}"
                )
            
            result = self.bybit.create_order(
                symbol=symbol,
                side="Sell",
                order_type="Limit",
                qty=qty,
                price=str(price),
                time_in_force=time_in_force,
                take_profit=str(take_profit) if take_profit else None,
                stop_loss=str(stop_loss) if stop_loss else None,
                tpsl_mode=tpsl_mode if (take_profit or stop_loss) else None,
                tp_order_type=tp_order_type if take_profit else None,
                sl_order_type=sl_order_type if stop_loss else None,
                order_link_id=order_link_id,
            )
            
            self.logger.trade(
                "LIMIT_ORDER_PLACED",
                symbol=symbol,
                side="SELL",
                size=usd_amount,
                price=price,
                qty=qty,
                tp=take_profit,
                sl=stop_loss
            )
            
            return OrderResult(
                success=True,
                order_id=result.get("orderId"),
                order_link_id=result.get("orderLinkId"),
                symbol=symbol,
                side="Sell",
                order_type="Limit",
                qty=qty,
                price=price,
                time_in_force=time_in_force,
                take_profit=take_profit,
                stop_loss=stop_loss,
                raw_response=result,
            )
            
        except BybitAPIError as e:
            self.logger.error(f"Limit sell with TP/SL failed: {e}")
            return OrderResult(success=False, error=str(e))
        except Exception as e:
            self.logger.error(f"Limit sell with TP/SL error: {e}")
            return OrderResult(success=False, error=str(e))
    
    # ==================== Conditional/Stop Orders ====================
    
    def stop_market_buy(
        self,
        symbol: str,
        usd_amount: float,
        trigger_price: float,
        trigger_direction: int = 1,
        trigger_by: str = "LastPrice",
        reduce_only: bool = False,
        order_link_id: str = None,
    ) -> OrderResult:
        """
        Place a conditional market buy order (triggers at price).
        
        Use this for:
        - Stop-loss for short positions (trigger when price rises)
        - Breakout entries (buy when price rises above level)
        
        Args:
            symbol: Trading symbol
            usd_amount: Amount in USD
            trigger_price: Price at which to trigger the order
            trigger_direction: 1=trigger when price rises, 2=trigger when falls
            trigger_by: LastPrice, IndexPrice, or MarkPrice
            reduce_only: Only reduce position
            order_link_id: Custom order ID
        
        Returns:
            OrderResult with order details
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            price = self.get_price(symbol)
            trigger_price = self._round_price(symbol, trigger_price)
            qty = self._calculate_qty(symbol, usd_amount, price)
            
            if qty <= 0:
                return OrderResult(
                    success=False,
                    error=f"Order size too small for {symbol}"
                )
            
            result = self.bybit.create_order(
                symbol=symbol,
                side="Buy",
                order_type="Market",
                qty=qty,
                time_in_force="IOC",
                reduce_only=reduce_only,
                order_link_id=order_link_id,
            )
            
            # Note: Bybit conditional orders use triggerPrice parameter
            # For the basic version, we use the pybit session directly
            # with trigger params
            result = self.bybit.session.place_order(
                category="linear",
                symbol=symbol,
                side="Buy",
                orderType="Market",
                qty=str(qty),
                triggerPrice=str(trigger_price),
                triggerDirection=trigger_direction,
                triggerBy=trigger_by,
                reduceOnly=reduce_only,
                orderLinkId=order_link_id,
            )
            
            # Extract result
            result_data = result[0].get("result", {}) if isinstance(result, tuple) else result.get("result", {})
            
            self.logger.trade(
                "STOP_ORDER_PLACED",
                symbol=symbol,
                side="BUY",
                size=usd_amount,
                trigger=trigger_price,
                qty=qty,
                type="market"
            )
            
            return OrderResult(
                success=True,
                order_id=result_data.get("orderId"),
                order_link_id=result_data.get("orderLinkId"),
                symbol=symbol,
                side="Buy",
                order_type="Market",
                qty=qty,
                trigger_price=trigger_price,
                reduce_only=reduce_only,
                raw_response=result_data,
            )
            
        except BybitAPIError as e:
            self.logger.error(f"Stop market buy failed: {e}")
            return OrderResult(success=False, error=str(e))
        except Exception as e:
            self.logger.error(f"Stop market buy error: {e}")
            return OrderResult(success=False, error=str(e))
    
    def stop_market_sell(
        self,
        symbol: str,
        usd_amount: float,
        trigger_price: float,
        trigger_direction: int = 2,
        trigger_by: str = "LastPrice",
        reduce_only: bool = False,
        order_link_id: str = None,
    ) -> OrderResult:
        """
        Place a conditional market sell order (triggers at price).
        
        Use this for:
        - Stop-loss for long positions (trigger when price falls)
        - Breakdown entries (short when price falls below level)
        
        Args:
            symbol: Trading symbol
            usd_amount: Amount in USD
            trigger_price: Price at which to trigger the order
            trigger_direction: 1=trigger when price rises, 2=trigger when falls
            trigger_by: LastPrice, IndexPrice, or MarkPrice
            reduce_only: Only reduce position
            order_link_id: Custom order ID
        
        Returns:
            OrderResult with order details
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            price = self.get_price(symbol)
            trigger_price = self._round_price(symbol, trigger_price)
            qty = self._calculate_qty(symbol, usd_amount, price)
            
            if qty <= 0:
                return OrderResult(
                    success=False,
                    error=f"Order size too small for {symbol}"
                )
            
            result = self.bybit.session.place_order(
                category="linear",
                symbol=symbol,
                side="Sell",
                orderType="Market",
                qty=str(qty),
                triggerPrice=str(trigger_price),
                triggerDirection=trigger_direction,
                triggerBy=trigger_by,
                reduceOnly=reduce_only,
                orderLinkId=order_link_id,
            )
            
            result_data = result[0].get("result", {}) if isinstance(result, tuple) else result.get("result", {})
            
            self.logger.trade(
                "STOP_ORDER_PLACED",
                symbol=symbol,
                side="SELL",
                size=usd_amount,
                trigger=trigger_price,
                qty=qty,
                type="market"
            )
            
            return OrderResult(
                success=True,
                order_id=result_data.get("orderId"),
                order_link_id=result_data.get("orderLinkId"),
                symbol=symbol,
                side="Sell",
                order_type="Market",
                qty=qty,
                trigger_price=trigger_price,
                reduce_only=reduce_only,
                raw_response=result_data,
            )
            
        except BybitAPIError as e:
            self.logger.error(f"Stop market sell failed: {e}")
            return OrderResult(success=False, error=str(e))
        except Exception as e:
            self.logger.error(f"Stop market sell error: {e}")
            return OrderResult(success=False, error=str(e))
    
    def stop_limit_buy(
        self,
        symbol: str,
        usd_amount: float,
        trigger_price: float,
        limit_price: float,
        trigger_direction: int = 1,
        trigger_by: str = "LastPrice",
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        order_link_id: str = None,
    ) -> OrderResult:
        """
        Place a conditional limit buy order.
        
        When trigger_price is reached, places a limit buy at limit_price.
        
        Args:
            symbol: Trading symbol
            usd_amount: Amount in USD
            trigger_price: Price at which to trigger the order
            limit_price: Limit price for the triggered order
            trigger_direction: 1=trigger when price rises, 2=trigger when falls
            trigger_by: LastPrice, IndexPrice, or MarkPrice
            time_in_force: GTC, IOC, FOK, or PostOnly
            reduce_only: Only reduce position
            order_link_id: Custom order ID
        
        Returns:
            OrderResult with order details
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            trigger_price = self._round_price(symbol, trigger_price)
            limit_price = self._round_price(symbol, limit_price)
            qty = self._calculate_qty(symbol, usd_amount, limit_price)
            
            if qty <= 0:
                return OrderResult(
                    success=False,
                    error=f"Order size too small for {symbol}"
                )
            
            result = self.bybit.session.place_order(
                category="linear",
                symbol=symbol,
                side="Buy",
                orderType="Limit",
                qty=str(qty),
                price=str(limit_price),
                triggerPrice=str(trigger_price),
                triggerDirection=trigger_direction,
                triggerBy=trigger_by,
                timeInForce=time_in_force,
                reduceOnly=reduce_only,
                orderLinkId=order_link_id,
            )
            
            result_data = result[0].get("result", {}) if isinstance(result, tuple) else result.get("result", {})
            
            self.logger.trade(
                "STOP_LIMIT_ORDER_PLACED",
                symbol=symbol,
                side="BUY",
                size=usd_amount,
                trigger=trigger_price,
                limit=limit_price,
                qty=qty
            )
            
            return OrderResult(
                success=True,
                order_id=result_data.get("orderId"),
                order_link_id=result_data.get("orderLinkId"),
                symbol=symbol,
                side="Buy",
                order_type="Limit",
                qty=qty,
                price=limit_price,
                trigger_price=trigger_price,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                raw_response=result_data,
            )
            
        except BybitAPIError as e:
            self.logger.error(f"Stop limit buy failed: {e}")
            return OrderResult(success=False, error=str(e))
        except Exception as e:
            self.logger.error(f"Stop limit buy error: {e}")
            return OrderResult(success=False, error=str(e))
    
    def stop_limit_sell(
        self,
        symbol: str,
        usd_amount: float,
        trigger_price: float,
        limit_price: float,
        trigger_direction: int = 2,
        trigger_by: str = "LastPrice",
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        order_link_id: str = None,
    ) -> OrderResult:
        """
        Place a conditional limit sell order.
        
        When trigger_price is reached, places a limit sell at limit_price.
        
        Args:
            symbol: Trading symbol
            usd_amount: Amount in USD
            trigger_price: Price at which to trigger the order
            limit_price: Limit price for the triggered order
            trigger_direction: 1=trigger when price rises, 2=trigger when falls
            trigger_by: LastPrice, IndexPrice, or MarkPrice
            time_in_force: GTC, IOC, FOK, or PostOnly
            reduce_only: Only reduce position
            order_link_id: Custom order ID
        
        Returns:
            OrderResult with order details
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            trigger_price = self._round_price(symbol, trigger_price)
            limit_price = self._round_price(symbol, limit_price)
            qty = self._calculate_qty(symbol, usd_amount, limit_price)
            
            if qty <= 0:
                return OrderResult(
                    success=False,
                    error=f"Order size too small for {symbol}"
                )
            
            result = self.bybit.session.place_order(
                category="linear",
                symbol=symbol,
                side="Sell",
                orderType="Limit",
                qty=str(qty),
                price=str(limit_price),
                triggerPrice=str(trigger_price),
                triggerDirection=trigger_direction,
                triggerBy=trigger_by,
                timeInForce=time_in_force,
                reduceOnly=reduce_only,
                orderLinkId=order_link_id,
            )
            
            result_data = result[0].get("result", {}) if isinstance(result, tuple) else result.get("result", {})
            
            self.logger.trade(
                "STOP_LIMIT_ORDER_PLACED",
                symbol=symbol,
                side="SELL",
                size=usd_amount,
                trigger=trigger_price,
                limit=limit_price,
                qty=qty
            )
            
            return OrderResult(
                success=True,
                order_id=result_data.get("orderId"),
                order_link_id=result_data.get("orderLinkId"),
                symbol=symbol,
                side="Sell",
                order_type="Limit",
                qty=qty,
                price=limit_price,
                trigger_price=trigger_price,
                time_in_force=time_in_force,
                reduce_only=reduce_only,
                raw_response=result_data,
            )
            
        except BybitAPIError as e:
            self.logger.error(f"Stop limit sell failed: {e}")
            return OrderResult(success=False, error=str(e))
        except Exception as e:
            self.logger.error(f"Stop limit sell error: {e}")
            return OrderResult(success=False, error=str(e))
    
    # ==================== Position Close Orders ====================
    
    def close_position(
        self,
        symbol: str,
        cancel_conditional_orders: bool = True,
    ) -> OrderResult:
        """
        Close position for a symbol.
        
        Automatically cancels related conditional TP orders when closing.
        Also removes symbol from websocket tracking when position closes.
        
        Args:
            symbol: Trading symbol
            cancel_conditional_orders: If True, cancel conditional TP orders first
        
        Returns:
            OrderResult
        """
        # SAFETY GUARD RAIL: Validate trading mode consistency
        try:
            self._validate_trading_operation()
        except ValueError as e:
            return OrderResult(success=False, error=str(e))
        
        position = self.get_position(symbol)
        
        if position is None or not position.is_open:
            return OrderResult(success=True, error="No position to close")
        
        # Cancel conditional orders BEFORE closing position
        cancelled_orders = []
        if cancel_conditional_orders:
            cancelled_orders = self.cancel_position_conditional_orders(
                symbol=symbol,
                position_side=position.side,
            )
        
        # Opposite side to close
        close_side = "Sell" if position.side == "long" else "Buy"
        
        try:
            result = self.bybit.create_order(
                symbol=symbol,
                side=close_side,
                order_type="Market",
                qty=position.size,
                reduce_only=True,
            )
            
            self.logger.trade(
                "POSITION_CLOSED",
                symbol=symbol,
                side=close_side,
                size=position.size_usd,
                pnl=position.unrealized_pnl,
                cancelled_conditional_orders=len(cancelled_orders),
            )
            
            # Remove symbol from websocket tracking (no longer needed)
            # Position closure will be detected via websocket callback, but
            # we proactively remove it here too
            self._remove_symbol_from_websocket(symbol)
            
            return OrderResult(
                success=True,
                order_id=result.get("orderId"),
                symbol=symbol,
                side=close_side,
                qty=position.size,
                raw_response=result,
            )
            
        except Exception as e:
            self.logger.error(f"Close position failed for {symbol}: {e}")
            return OrderResult(success=False, error=str(e))
    
    def close_all_positions(self) -> List[OrderResult]:
        """
        Close all open positions.
        
        Returns:
            List of OrderResults for each position
        """
        # SAFETY GUARD RAIL: Validate trading mode consistency
        try:
            self._validate_trading_operation()
        except ValueError as e:
            return [OrderResult(success=False, error=str(e))]
        
        results = []
        positions = self.get_all_positions()
        
        self.logger.warning(f"Closing all positions ({len(positions)} open)")
        
        for pos in positions:
            result = self.close_position(pos.symbol)
            results.append(result)
        
        return results
    
    # ==================== Order Management ====================
    
    def get_open_orders(self, symbol: str = None) -> List[Order]:
        """
        Get all open orders.
        
        Args:
            symbol: Specific symbol (None for all)
        
        Returns:
            List of Order objects
        """
        try:
            raw_orders = self.bybit.get_open_orders(symbol)
            
            orders = []
            for order in raw_orders:
                orders.append(Order(
                    order_id=order.get("orderId"),
                    order_link_id=order.get("orderLinkId"),
                    symbol=order.get("symbol"),
                    side=order.get("side"),
                    order_type=order.get("orderType"),
                    price=safe_float(order.get("price")) if order.get("price") else None,
                    qty=safe_float(order.get("qty", 0)),
                    filled_qty=safe_float(order.get("cumExecQty", 0)),
                    remaining_qty=safe_float(order.get("leavesQty", 0)),
                    status=order.get("orderStatus"),
                    time_in_force=order.get("timeInForce"),
                    reduce_only=order.get("reduceOnly", False),
                    trigger_price=safe_float(order.get("triggerPrice")) if order.get("triggerPrice") else None,
                    trigger_by=order.get("triggerBy"),
                    take_profit=safe_float(order.get("takeProfit")) if order.get("takeProfit") else None,
                    stop_loss=safe_float(order.get("stopLoss")) if order.get("stopLoss") else None,
                    created_time=order.get("createdTime"),
                    updated_time=order.get("updatedTime"),
                ))
            
            return orders
            
        except Exception as e:
            self.logger.error(f"Get open orders failed: {e}")
            return []
    
    def cancel_order(
        self,
        symbol: str,
        order_id: str = None,
        order_link_id: str = None,
    ) -> bool:
        """
        Cancel a specific order.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID to cancel
            order_link_id: Custom order ID to cancel
        
        Returns:
            True if successful
        """
        if not order_id and not order_link_id:
            self.logger.error("Must provide order_id or order_link_id")
            return False
        
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            self.bybit.cancel_order(
                symbol=symbol,
                order_id=order_id,
                order_link_id=order_link_id,
            )
            self.logger.info(f"Cancelled order {order_id or order_link_id} for {symbol}")
            return True
        except Exception as e:
            self.logger.error(f"Cancel order failed: {e}")
            return False
    
    def cancel_all_orders(self, symbol: str = None) -> bool:
        """
        Cancel all open orders.
        
        Args:
            symbol: Specific symbol (None for all)
        
        Returns:
            True if successful
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            # First check if there are any orders to cancel
            orders = self.get_open_orders(symbol)
            if not orders:
                self.logger.debug(f"No orders to cancel{f' for {symbol}' if symbol else ''}")
                return True  # Success - nothing to cancel
            
            # If symbol is None, cancel per symbol (Bybit may require symbol parameter)
            if symbol is None:
                # Get unique symbols from orders
                symbols = set(order.symbol for order in orders)
                success_count = 0
                for sym in symbols:
                    try:
                        self.bybit.cancel_all_orders(symbol=sym)
                        success_count += 1
                        self.logger.debug(f"Cancelled all orders for {sym}")
                    except Exception as e:
                        self.logger.warning(f"Failed to cancel orders for {sym}: {e}")
                        # Continue with other symbols
                
                if success_count > 0:
                    self.logger.warning(f"Cancelled orders for {success_count}/{len(symbols)} symbol(s)")
                    return True
                else:
                    self.logger.error("Failed to cancel orders for all symbols")
                    return False
            else:
                # Cancel for specific symbol
                self.bybit.cancel_all_orders(symbol)
                self.logger.warning(f"Cancelled all orders for {symbol}")
                return True
                
        except Exception as e:
            self.logger.error(f"Cancel all orders failed: {e}")
            return False
    
    # ==================== Conditional Order Cleanup ====================
    
    def cancel_position_conditional_orders(
        self,
        symbol: str,
        position_side: str,
        require_bot_id: bool = True,
    ) -> List[str]:
        """
        Cancel conditional orders that would close the given position.
        
        Only cancels orders that are:
        - Conditional (has trigger_price)
        - Reduce-only
        - Same symbol
        - Opposite side to position (would close it)
        - (Optional) Have order_link_id matching bot pattern (TP*_SYMBOL_*)
        
        Args:
            symbol: Trading symbol
            position_side: "long" or "short"
            require_bot_id: If True, only cancel orders with bot-generated order_link_id
        
        Returns:
            List of cancelled order IDs
        """
        import re
        cancelled = []
        
        try:
            # Get all open orders for this symbol
            orders = self.get_open_orders(symbol)
            
            if not orders:
                return cancelled
            
            # Determine the side that would close this position
            close_side = "Sell" if position_side == "long" else "Buy"
            
            # Pattern for bot-generated TP orders: TP1_BTCUSDT_1234567890
            tp_pattern = re.compile(rf"^TP\d+_{re.escape(symbol)}_\d+$")
            
            # Filter for conditional reduce-only orders that would close position
            orders_to_cancel = []
            for order in orders:
                if not (order.is_conditional and order.reduce_only and 
                        order.side == close_side and order.is_active):
                    continue
                
                # Check order_link_id pattern if required
                if require_bot_id:
                    if not order.order_link_id:
                        continue
                    if not tp_pattern.match(order.order_link_id):
                        self.logger.debug(
                            f"Skipping order {order.order_id} - order_link_id '{order.order_link_id}' "
                            f"doesn't match bot pattern"
                        )
                        continue
                
                orders_to_cancel.append(order)
            
            if not orders_to_cancel:
                return cancelled
            
            self.logger.info(
                f"Cancelling {len(orders_to_cancel)} conditional orders for {symbol} position"
            )
            
            # Cancel each order
            for order in orders_to_cancel:
                try:
                    success = self.cancel_order(
                        symbol=symbol,
                        order_id=order.order_id,
                        order_link_id=order.order_link_id,
                    )
                    if success:
                        order_identifier = order.order_link_id or order.order_id
                        cancelled.append(order_identifier)
                        self.logger.debug(
                            f"Cancelled conditional order {order_identifier} "
                            f"({order.side} {order.qty} @ trigger ${order.trigger_price})"
                        )
                except Exception as e:
                    # Log but don't fail - individual order cancellation shouldn't block
                    self.logger.warning(
                        f"Failed to cancel order {order.order_id or order.order_link_id}: {e}"
                    )
            
            if cancelled:
                self.logger.info(
                    f"Successfully cancelled {len(cancelled)}/{len(orders_to_cancel)} "
                    f"conditional orders for {symbol}"
                )
            
        except Exception as e:
            # Don't raise - this is cleanup, not critical
            self.logger.warning(
                f"Error cancelling conditional orders for {symbol}: {e}"
            )
        
        return cancelled
    
    def reconcile_orphaned_orders(self, symbol: str = None) -> Dict[str, List[str]]:
        """
        Find and cancel conditional orders for positions that no longer exist.
        
        Critical for long-term operation - if the bot crashes or restarts,
        conditional TP orders may remain active even though positions are closed.
        
        Only cancels orders with bot-generated order_link_id pattern.
        
        Args:
            symbol: Specific symbol (None for all symbols)
        
        Returns:
            Dict mapping symbol to list of cancelled order IDs
        """
        import re
        cancelled_by_symbol: Dict[str, List[str]] = {}
        
        try:
            # Get all open positions
            positions = self.get_all_positions()
            open_symbols = {pos.symbol for pos in positions if pos.is_open}
            
            # Get all open orders
            all_orders = self.get_open_orders(symbol)
            
            # Group orders by symbol
            orders_by_symbol: Dict[str, List[Order]] = {}
            for order in all_orders:
                if order.symbol not in orders_by_symbol:
                    orders_by_symbol[order.symbol] = []
                orders_by_symbol[order.symbol].append(order)
            
            # For each symbol with orders
            for order_symbol, orders in orders_by_symbol.items():
                # Skip if filtering by specific symbol
                if symbol and order_symbol != symbol:
                    continue
                
                # Pattern for bot-generated TP orders
                tp_pattern = re.compile(rf"^TP\d+_{re.escape(order_symbol)}_\d+$")
                
                # Check if position exists
                has_position = order_symbol in open_symbols
                
                if not has_position:
                    # No position - cancel bot-generated conditional reduce-only orders
                    orphaned = [
                        o for o in orders
                        if o.is_conditional 
                        and o.reduce_only 
                        and o.is_active
                        and o.order_link_id
                        and tp_pattern.match(o.order_link_id)
                    ]
                    
                    if orphaned:
                        self.logger.warning(
                            f"Found {len(orphaned)} orphaned conditional orders for {order_symbol} "
                            f"(no position exists)"
                        )
                        
                        cancelled = []
                        for order in orphaned:
                            try:
                                if self.cancel_order(
                                    symbol=order_symbol,
                                    order_id=order.order_id,
                                    order_link_id=order.order_link_id,
                                ):
                                    cancelled.append(order.order_link_id or order.order_id)
                            except Exception as e:
                                self.logger.warning(f"Failed to cancel orphaned order: {e}")
                        
                        if cancelled:
                            cancelled_by_symbol[order_symbol] = cancelled
                            self.logger.info(
                                f"Cancelled {len(cancelled)} orphaned orders for {order_symbol}"
                            )
                else:
                    # Position exists - verify orders match position side
                    position = next(p for p in positions if p.symbol == order_symbol)
                    close_side = "Sell" if position.side == "long" else "Buy"
                    
                    # Find bot-generated orders on wrong side (would open position, not close)
                    mismatched = [
                        o for o in orders
                        if o.is_conditional
                        and o.reduce_only
                        and o.is_active
                        and o.side != close_side
                        and o.order_link_id
                        and tp_pattern.match(o.order_link_id)
                    ]
                    
                    if mismatched:
                        self.logger.warning(
                            f"Found {len(mismatched)} mismatched conditional orders for {order_symbol} "
                            f"(wrong side for current position)"
                        )
                        # Cancel mismatched orders
                        cancelled = []
                        for order in mismatched:
                            try:
                                if self.cancel_order(
                                    symbol=order_symbol,
                                    order_id=order.order_id,
                                    order_link_id=order.order_link_id,
                                ):
                                    cancelled.append(order.order_link_id or order.order_id)
                            except Exception as e:
                                self.logger.warning(f"Failed to cancel mismatched order: {e}")
                        
                        if cancelled:
                            cancelled_by_symbol[order_symbol] = cancelled
        
        except Exception as e:
            self.logger.error(f"Error reconciling orphaned orders: {e}")
        
        return cancelled_by_symbol
    
    def amend_order(
        self,
        symbol: str,
        order_id: str = None,
        order_link_id: str = None,
        qty: float = None,
        price: float = None,
        take_profit: float = None,
        stop_loss: float = None,
        trigger_price: float = None,
    ) -> bool:
        """
        Amend an existing order.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID to amend
            order_link_id: Custom order ID to amend
            qty: New quantity (optional)
            price: New price (optional)
            take_profit: New TP price (optional)
            stop_loss: New SL price (optional)
            trigger_price: New trigger price (optional)
        
        Returns:
            True if successful
        """
        if not order_id and not order_link_id:
            self.logger.error("Must provide order_id or order_link_id")
            return False
        
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            # Build kwargs with only provided values
            kwargs = {
                "symbol": symbol,
                "order_id": order_id,
                "order_link_id": order_link_id,
            }
            
            if qty is not None:
                kwargs["qty"] = str(qty)
            if price is not None:
                kwargs["price"] = str(self._round_price(symbol, price))
            if take_profit is not None:
                kwargs["take_profit"] = str(take_profit)
            if stop_loss is not None:
                kwargs["stop_loss"] = str(stop_loss)
            
            self.bybit.amend_order(**kwargs)
            self.logger.info(f"Amended order {order_id or order_link_id} for {symbol}")
            return True
            
        except Exception as e:
            self.logger.error(f"Amend order failed: {e}")
            return False
    
    # ==================== Leverage & Margin ====================
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        Set leverage for a symbol.
        
        Args:
            symbol: Trading symbol
            leverage: Leverage multiplier
        
        Returns:
            True if successful
        """
        # Enforce config limit
        max_leverage = self.config.risk.max_leverage
        if leverage > max_leverage:
            self.logger.warning(f"Leverage {leverage} exceeds max {max_leverage}, using {max_leverage}")
            leverage = max_leverage
        
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            self.bybit.set_leverage(symbol, leverage)
            return True
        except BybitAPIError as e:
            # Leverage might already be set - not an error
            if "leverage not modified" in str(e).lower():
                return True
            self.logger.error(f"Set leverage failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Set leverage error: {e}")
            return False
    
    def set_margin_mode(self, symbol: str, mode: str) -> bool:
        """
        Set margin mode for a symbol.
        
        Args:
            symbol: Trading symbol
            mode: "ISOLATED_MARGIN" or "REGULAR_MARGIN" (cross)
        
        Returns:
            True if successful
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            # Use raw pybit session for this
            result = self.bybit.session.switch_margin_mode(
                category="linear",
                symbol=symbol,
                tradeMode=0 if mode == "REGULAR_MARGIN" else 1,  # 0=cross, 1=isolated
                buyLeverage="10",  # Required param
                sellLeverage="10",
            )
            self.logger.info(f"Set margin mode for {symbol} to {mode}")
            return True
        except Exception as e:
            # Mode might already be set
            if "margin mode is not modified" in str(e).lower():
                return True
            self.logger.error(f"Set margin mode failed: {e}")
            return False
    
    def set_position_mode(self, mode: str = "MergedSingle") -> bool:
        """
        Set position mode for the account.
        
        Args:
            mode: "MergedSingle" (one-way) or "BothSide" (hedge mode)
        
        Returns:
            True if successful
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            result = self.bybit.session.switch_position_mode(
                category="linear",
                mode=0 if mode == "MergedSingle" else 3,  # 0=one-way, 3=hedge
            )
            self.logger.info(f"Set position mode to {mode}")
            return True
        except Exception as e:
            # Mode might already be set
            if "position mode is not modified" in str(e).lower():
                return True
            self.logger.error(f"Set position mode failed: {e}")
            return False
    
    def add_margin(self, symbol: str, amount: float) -> bool:
        """
        Add margin to an isolated position.
        
        Args:
            symbol: Trading symbol
            amount: Amount of margin to add (USDT)
        
        Returns:
            True if successful
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            result = self.bybit.session.add_or_reduce_margin(
                category="linear",
                symbol=symbol,
                margin=str(amount),
                positionIdx=0,  # One-way mode
            )
            self.logger.info(f"Added {amount} margin to {symbol}")
            return True
        except Exception as e:
            self.logger.error(f"Add margin failed: {e}")
            return False
    
    def set_trailing_stop(
        self,
        symbol: str,
        trailing_stop: float,
        active_price: float = None,
    ) -> bool:
        """
        Set a trailing stop for an existing position.
        
        Args:
            symbol: Trading symbol
            trailing_stop: Trailing distance (price difference)
            active_price: Price at which trailing becomes active (optional)
        
        Returns:
            True if successful
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            self.bybit.set_trading_stop(
                symbol=symbol,
                trailing_stop=str(trailing_stop),
            )
            self.logger.info(f"Set trailing stop for {symbol}: {trailing_stop}")
            return True
        except Exception as e:
            self.logger.error(f"Set trailing stop failed: {e}")
            return False
    
    # ==================== Orders with TP/SL ====================
    
    def market_buy_with_tpsl(
        self,
        symbol: str,
        usd_amount: float,
        take_profit: float = None,
        stop_loss: float = None,
        tpsl_mode: str = "Full",
    ) -> OrderResult:
        """
        Place a market buy order with TP/SL.
        
        Args:
            symbol: Trading symbol
            usd_amount: Amount to buy in USD
            take_profit: Take profit price
            stop_loss: Stop loss price
            tpsl_mode: "Full" (entire position) or "Partial"
        
        Returns:
            OrderResult with success status and details
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            # Ensure we're tracking this symbol for real-time updates
            self._ensure_symbol_tracked(symbol)
            
            price = self.get_price(symbol)
            qty = self._calculate_qty(symbol, usd_amount, price)
            
            if qty <= 0:
                return OrderResult(
                    success=False,
                    error=f"Order size too small for {symbol}"
                )
            
            result = self.bybit.create_order(
                symbol=symbol,
                side="Buy",
                order_type="Market",
                qty=qty,
                take_profit=str(take_profit) if take_profit else None,
                stop_loss=str(stop_loss) if stop_loss else None,
                tpsl_mode=tpsl_mode if (take_profit or stop_loss) else None,
            )
            
            self.logger.trade(
                "ORDER_FILLED",
                symbol=symbol,
                side="BUY",
                size=usd_amount,
                price=price,
                qty=qty,
                tp=take_profit,
                sl=stop_loss
            )
            
            return OrderResult(
                success=True,
                order_id=result.get("orderId"),
                order_link_id=result.get("orderLinkId"),
                symbol=symbol,
                side="Buy",
                order_type="Market",
                qty=qty,
                price=price,
                take_profit=take_profit,
                stop_loss=stop_loss,
                raw_response=result,
            )
            
        except BybitAPIError as e:
            self.logger.error(f"Market buy with TP/SL failed: {e}")
            return OrderResult(success=False, error=str(e))
        except Exception as e:
            self.logger.error(f"Market buy with TP/SL error: {e}")
            return OrderResult(success=False, error=str(e))
    
    def market_sell_with_tpsl(
        self,
        symbol: str,
        usd_amount: float,
        take_profit: float = None,
        stop_loss: float = None,
        tpsl_mode: str = "Full",
    ) -> OrderResult:
        """
        Place a market sell order with TP/SL (short).
        
        Args:
            symbol: Trading symbol
            usd_amount: Amount to sell in USD
            take_profit: Take profit price
            stop_loss: Stop loss price
            tpsl_mode: "Full" (entire position) or "Partial"
        
        Returns:
            OrderResult with success status and details
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            # Ensure we're tracking this symbol for real-time updates
            self._ensure_symbol_tracked(symbol)
            
            price = self.get_price(symbol)
            qty = self._calculate_qty(symbol, usd_amount, price)
            
            if qty <= 0:
                return OrderResult(
                    success=False,
                    error=f"Order size too small for {symbol}"
                )
            
            result = self.bybit.create_order(
                symbol=symbol,
                side="Sell",
                order_type="Market",
                qty=qty,
                take_profit=str(take_profit) if take_profit else None,
                stop_loss=str(stop_loss) if stop_loss else None,
                tpsl_mode=tpsl_mode if (take_profit or stop_loss) else None,
            )
            
            self.logger.trade(
                "ORDER_FILLED",
                symbol=symbol,
                side="SELL",
                size=usd_amount,
                price=price,
                qty=qty,
                tp=take_profit,
                sl=stop_loss
            )
            
            return OrderResult(
                success=True,
                order_id=result.get("orderId"),
                order_link_id=result.get("orderLinkId"),
                symbol=symbol,
                side="Sell",
                order_type="Market",
                qty=qty,
                price=price,
                take_profit=take_profit,
                stop_loss=stop_loss,
                raw_response=result,
            )
            
        except BybitAPIError as e:
            self.logger.error(f"Market sell with TP/SL failed: {e}")
            return OrderResult(success=False, error=str(e))
        except Exception as e:
            self.logger.error(f"Market sell with TP/SL error: {e}")
            return OrderResult(success=False, error=str(e))
    
    def set_position_tpsl(
        self,
        symbol: str,
        take_profit: float = None,
        stop_loss: float = None,
        tpsl_mode: str = "Full",
    ) -> bool:
        """
        Set TP/SL for an existing position.
        
        Args:
            symbol: Trading symbol
            take_profit: TP price (0 or None to remove)
            stop_loss: SL price (0 or None to remove)
            tpsl_mode: "Full" or "Partial"
        
        Returns:
            True if successful
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            self.bybit.set_trading_stop(
                symbol=symbol,
                take_profit=str(take_profit) if take_profit else "0",
                stop_loss=str(stop_loss) if stop_loss else "0",
                tpsl_mode=tpsl_mode,
            )
            self.logger.info(f"Set TP/SL for {symbol}: TP={take_profit}, SL={stop_loss}")
            return True
        except Exception as e:
            self.logger.error(f"Set TP/SL failed for {symbol}: {e}")
            return False
    
    # ==================== Conditional Orders (for split TPs) ====================
    
    def create_conditional_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        trigger_price: float,
        trigger_direction: TriggerDirection = None,
        order_type: str = "Market",
        price: float = None,
        reduce_only: bool = True,
        order_link_id: str = None,
    ) -> OrderResult:
        """
        Create a conditional (trigger) order - used for split take profits.
        
        Args:
            symbol: Trading symbol
            side: "Buy" or "Sell"
            qty: Order quantity
            trigger_price: Price at which order triggers
            trigger_direction: RISE (1) or FALL (2) - auto-detected if None
            order_type: "Market" or "Limit"
            price: Limit price (required for Limit orders)
            reduce_only: Whether order can only reduce position
            order_link_id: Custom order ID
        
        Returns:
            OrderResult with order details
        """
        try:
            # SAFETY GUARD RAIL: Validate trading mode consistency
            self._validate_trading_operation()
            
            # Auto-detect trigger direction if not specified
            if trigger_direction is None:
                current_price = self.get_price(symbol)
                if trigger_price > current_price:
                    trigger_direction = TriggerDirection.RISE
                else:
                    trigger_direction = TriggerDirection.FALL
            
            result = self.bybit.create_conditional_order(
                symbol=symbol,
                side=side,
                qty=str(qty),
                trigger_price=str(trigger_price),
                trigger_direction=trigger_direction.value if isinstance(trigger_direction, TriggerDirection) else trigger_direction,
                order_type=order_type,
                price=str(price) if price else None,
                reduce_only=reduce_only,
                order_link_id=order_link_id,
            )
            
            self.logger.info(
                f"Conditional order created: {symbol} {side} {qty} @ trigger ${trigger_price}"
            )
            
            return OrderResult(
                success=True,
                order_id=result.get("orderId"),
                order_link_id=result.get("orderLinkId"),
                symbol=symbol,
                side=side,
                order_type=order_type,
                qty=qty,
                trigger_price=trigger_price,
                reduce_only=reduce_only,
                raw_response=result,
            )
            
        except BybitAPIError as e:
            self.logger.error(f"Conditional order failed: {e}")
            return OrderResult(success=False, error=str(e))
        except Exception as e:
            self.logger.error(f"Conditional order error: {e}")
            return OrderResult(success=False, error=str(e))
    
    def open_position_with_rr(
        self,
        symbol: str,
        side: str,
        margin_usd: float,
        leverage: int,
        stop_loss_roi_pct: float,
        take_profits: List[Dict[str, float]],
    ) -> Dict[str, Any]:
        """
        Open a position with RR-based stop loss and multiple take profits.
        
        This is the programmatic version of the CLI's test_position_scenarios.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            side: "Buy" (long) or "Sell" (short)
            margin_usd: Margin amount in USD
            leverage: Position leverage
            stop_loss_roi_pct: Stop loss as ROI % (e.g., 10 = lose 10% of margin)
            take_profits: List of TP configs:
                [
                    {"rr": 1.5, "close_pct": 50},  # 1:1.5 RR, close 50%
                    {"rr": 3.0, "close_pct": 50},  # 1:3 RR, close remaining 50%
                ]
        
        Returns:
            Dict with:
                - success: bool
                - position_order: OrderResult
                - tp_orders: List[OrderResult]
                - levels: Dict with entry, sl, tp prices
                - error: Optional error message
        """
        result = {
            "success": False,
            "position_order": None,
            "tp_orders": [],
            "levels": {},
            "error": None,
        }
        
        try:
            # Set leverage
            try:
                self.set_leverage(symbol, leverage)
            except Exception as e:
                if "not modified" not in str(e).lower():
                    self.logger.warning(f"Leverage set warning: {e}")
            
            # Get current price
            entry_price = self.get_price(symbol)
            is_long = side == "Buy"
            
            # Calculate position size
            notional_usd = margin_usd * leverage
            qty = self._calculate_qty(symbol, notional_usd, entry_price)
            
            if qty <= 0:
                result["error"] = f"Order size too small for {symbol}"
                return result
            
            # Calculate stop loss price (based on ROI %)
            # Price distance = ROI% / Leverage
            sl_price_pct = stop_loss_roi_pct / leverage / 100
            risk_distance = entry_price * sl_price_pct
            
            if is_long:
                stop_loss = round(entry_price - risk_distance, self._get_price_precision(symbol))
            else:
                stop_loss = round(entry_price + risk_distance, self._get_price_precision(symbol))
            
            # Calculate TP prices and quantities
            tp_orders_config = []
            remaining_qty = qty
            close_side = "Sell" if is_long else "Buy"
            trigger_direction = TriggerDirection.RISE if is_long else TriggerDirection.FALL
            
            for i, tp in enumerate(take_profits):
                tp_roi_pct = stop_loss_roi_pct * tp["rr"]
                tp_price_pct = tp_roi_pct / leverage / 100
                tp_distance = entry_price * tp_price_pct
                
                if is_long:
                    tp_price = round(entry_price + tp_distance, self._get_price_precision(symbol))
                else:
                    tp_price = round(entry_price - tp_distance, self._get_price_precision(symbol))
                
                # Calculate qty for this TP
                is_last = (i == len(take_profits) - 1)
                if is_last:
                    tp_qty = remaining_qty
                else:
                    tp_qty = qty * (tp["close_pct"] / 100)
                    # Round to step size
                    info = self._get_instrument_info(symbol)
                    qty_step = float(info.get("lotSizeFilter", {}).get("qtyStep", 0.001))
                    tp_qty = float(Decimal(str(tp_qty)).quantize(Decimal(str(qty_step)), rounding=ROUND_DOWN))
                    remaining_qty -= tp_qty
                
                tp_orders_config.append({
                    "price": tp_price,
                    "qty": tp_qty,
                    "rr": tp["rr"],
                    "close_pct": tp["close_pct"],
                })
            
            # Store levels
            result["levels"] = {
                "entry": entry_price,
                "stop_loss": stop_loss,
                "take_profits": tp_orders_config,
                "qty": qty,
                "notional_usd": notional_usd,
                "margin_usd": margin_usd,
                "leverage": leverage,
            }
            
            # Open position with stop loss
            if is_long:
                position_result = self.market_buy_with_tpsl(
                    symbol=symbol,
                    usd_amount=notional_usd,
                    stop_loss=stop_loss,
                )
            else:
                position_result = self.market_sell_with_tpsl(
                    symbol=symbol,
                    usd_amount=notional_usd,
                    stop_loss=stop_loss,
                )
            
            result["position_order"] = position_result
            
            if not position_result.success:
                result["error"] = f"Failed to open position: {position_result.error}"
                return result
            
            # Place conditional TP orders
            import time
            for i, tp_config in enumerate(tp_orders_config):
                tp_result = self.create_conditional_order(
                    symbol=symbol,
                    side=close_side,
                    qty=tp_config["qty"],
                    trigger_price=tp_config["price"],
                    trigger_direction=trigger_direction,
                    order_type="Market",
                    reduce_only=True,
                    order_link_id=f"TP{i+1}_{symbol}_{int(time.time())}",
                )
                result["tp_orders"].append(tp_result)
                
                if not tp_result.success:
                    self.logger.warning(f"TP{i+1} order failed: {tp_result.error}")
            
            result["success"] = True
            self.logger.info(
                f"Position opened with RR: {symbol} {side} ${margin_usd} @ {leverage}x, "
                f"SL={stop_loss}, {len(result['tp_orders'])} TPs"
            )
            
            return result
            
        except Exception as e:
            result["error"] = str(e)
            self.logger.error(f"Open position with RR failed: {e}")
            return result
    
    def _get_price_precision(self, symbol: str) -> int:
        """Get price decimal precision for a symbol."""
        info = self._get_instrument_info(symbol)
        tick_size = info.get("priceFilter", {}).get("tickSize", "0.01")
        # Count decimal places
        if "." in tick_size:
            return len(tick_size.split(".")[1].rstrip("0"))
        return 2
    
    # ==================== Order History & Executions ====================
    
    def get_order_history(
        self,
        time_range: TimeRange,
        symbol: str = None,
        limit: int = 50,
    ) -> List[Dict]:
        """
        Get order history.
        
        CRITICAL: TimeRange is REQUIRED. We never rely on Bybit's implicit defaults.
        
        Args:
            time_range: Required TimeRange specifying the query window (max 7 days)
            symbol: Specific symbol (None for all)
            limit: Max results
        
        Returns:
            List of order records
        """
        try:
            result = self.bybit.get_order_history(
                time_range=time_range,
                symbol=symbol,
                limit=limit,
            )
            return result.get("list", [])
        except Exception as e:
            self.logger.error(f"Get order history failed: {e}")
            return []
    
    def get_executions(
        self,
        time_range: TimeRange,
        symbol: str = None,
        limit: int = 50,
    ) -> List[Dict]:
        """
        Get trade execution history.
        
        CRITICAL: TimeRange is REQUIRED. We never rely on Bybit's implicit defaults.
        
        Args:
            time_range: Required TimeRange specifying the query window (max 7 days)
            symbol: Specific symbol (None for all)
            limit: Max results
        
        Returns:
            List of execution records
        """
        try:
            return self.bybit.get_executions(
                time_range=time_range,
                symbol=symbol,
                limit=limit,
            )
        except Exception as e:
            self.logger.error(f"Get executions failed: {e}")
            return []
    
    def get_closed_pnl(
        self,
        time_range: TimeRange,
        symbol: str = None,
        limit: int = 50,
    ) -> List[Dict]:
        """
        Get closed position PnL history.
        
        CRITICAL: TimeRange is REQUIRED. We never rely on Bybit's implicit defaults.
        
        Args:
            time_range: Required TimeRange specifying the query window (max 7 days)
            symbol: Specific symbol (None for all)
            limit: Max results
        
        Returns:
            List of closed PnL records
        """
        try:
            result = self.bybit.get_closed_pnl(
                time_range=time_range,
                symbol=symbol,
                limit=limit,
            )
            return result.get("list", [])
        except Exception as e:
            self.logger.error(f"Get closed PnL failed: {e}")
            return []
    
    # ==================== Batch Orders ====================
    
    def batch_market_orders(
        self,
        orders: List[Dict[str, Any]],
    ) -> List[OrderResult]:
        """
        Execute multiple market orders in a batch.
        
        Args:
            orders: List of order specs with keys:
                - symbol: Trading symbol
                - side: "Buy" or "Sell"
                - usd_amount: Amount in USD
                - take_profit: Optional TP
                - stop_loss: Optional SL
        
        Returns:
            List of OrderResults
        """
        # SAFETY GUARD RAIL: Validate trading mode consistency
        try:
            self._validate_trading_operation()
        except ValueError as e:
            return [OrderResult(success=False, error=str(e))]
        
        if len(orders) > 10:
            self.logger.warning("Batch orders limited to 10, splitting...")
            results = []
            for i in range(0, len(orders), 10):
                results.extend(self.batch_market_orders(orders[i:i+10]))
            return results
        
        # Convert USD amounts to quantities
        batch_orders = []
        for order in orders:
            symbol = order["symbol"]
            price = self.get_price(symbol)
            qty = self._calculate_qty(symbol, order["usd_amount"], price)
            
            if qty <= 0:
                continue
            
            batch_order = {
                "symbol": symbol,
                "side": order["side"],
                "orderType": "Market",
                "qty": str(qty),
            }
            
            if order.get("take_profit"):
                batch_order["takeProfit"] = str(order["take_profit"])
            if order.get("stop_loss"):
                batch_order["stopLoss"] = str(order["stop_loss"])
            
            batch_orders.append(batch_order)
        
        if not batch_orders:
            return []
        
        try:
            result = self.bybit.batch_create_orders(batch_orders)
            
            # _extract_result already unwraps "result", so access "list" directly
            results = []
            batch_list = result.get("list", []) if isinstance(result, dict) else []
            for item in batch_list:
                # Check multiple success indicators - Bybit uses different fields
                code = item.get("code")
                order_id = item.get("orderId", "")
                # Success if code is 0 or if orderId is present (order was created)
                is_success = (code == 0 or code is None) and bool(order_id)
                
                results.append(OrderResult(
                    success=is_success,
                    order_id=order_id,
                    order_link_id=item.get("orderLinkId"),
                    symbol=item.get("symbol"),
                    order_type="Market",
                    error=item.get("msg") if not is_success else None,
                ))
            
            success_count = sum(1 for r in results if r.success)
            self.logger.info(f"Batch created {success_count}/{len(results)} market orders")
            return results
            
        except Exception as e:
            self.logger.error(f"Batch market orders failed: {e}")
            return [OrderResult(success=False, error=str(e))]
    
    def batch_limit_orders(
        self,
        orders: List[Dict[str, Any]],
    ) -> List[OrderResult]:
        """
        Execute multiple limit orders in a batch.
        
        Args:
            orders: List of order specs with keys:
                - symbol: Trading symbol
                - side: "Buy" or "Sell"
                - usd_amount: Amount in USD
                - price: Limit price
                - time_in_force: Optional (default GTC)
                - take_profit: Optional TP
                - stop_loss: Optional SL
                - reduce_only: Optional (default False)
        
        Returns:
            List of OrderResults
        """
        # SAFETY GUARD RAIL: Validate trading mode consistency
        try:
            self._validate_trading_operation()
        except ValueError as e:
            return [OrderResult(success=False, error=str(e))]
        
        if len(orders) > 10:
            self.logger.warning("Batch orders limited to 10, splitting...")
            results = []
            for i in range(0, len(orders), 10):
                results.extend(self.batch_limit_orders(orders[i:i+10]))
            return results
        
        # Convert USD amounts to quantities and round prices
        batch_orders = []
        for order in orders:
            symbol = order["symbol"]
            price = self._round_price(symbol, order["price"])
            qty = self._calculate_qty(symbol, order["usd_amount"], price)
            
            if qty <= 0:
                continue
            
            batch_order = {
                "symbol": symbol,
                "side": order["side"],
                "orderType": "Limit",
                "qty": str(qty),
                "price": str(price),
                "timeInForce": order.get("time_in_force", "GTC"),
            }
            
            if order.get("take_profit"):
                batch_order["takeProfit"] = str(order["take_profit"])
            if order.get("stop_loss"):
                batch_order["stopLoss"] = str(order["stop_loss"])
            if order.get("reduce_only"):
                batch_order["reduceOnly"] = True
            
            batch_orders.append(batch_order)
        
        if not batch_orders:
            return []
        
        try:
            result = self.bybit.batch_create_orders(batch_orders)
            
            # _extract_result already unwraps "result", so access "list" directly
            results = []
            batch_list = result.get("list", []) if isinstance(result, dict) else []
            for item in batch_list:
                # Check multiple success indicators - Bybit uses different fields
                code = item.get("code")
                order_id = item.get("orderId", "")
                # Success if code is 0 or if orderId is present (order was created)
                is_success = (code == 0 or code is None) and bool(order_id)
                
                results.append(OrderResult(
                    success=is_success,
                    order_id=order_id,
                    order_link_id=item.get("orderLinkId"),
                    symbol=item.get("symbol"),
                    order_type="Limit",
                    error=item.get("msg") if not is_success else None,
                ))
            
            success_count = sum(1 for r in results if r.success)
            self.logger.info(f"Batch created {success_count}/{len(results)} limit orders")
            return results
            
        except Exception as e:
            self.logger.error(f"Batch limit orders failed: {e}")
            return [OrderResult(success=False, error=str(e))]
    
    def batch_cancel_orders(
        self,
        orders: List[Dict[str, str]],
    ) -> List[bool]:
        """
        Cancel multiple orders in a batch.
        
        Args:
            orders: List of dicts with:
                - symbol: Trading symbol
                - orderId: Order ID (optional)
                - orderLinkId: Custom order ID (optional)
        
        Returns:
            List of success booleans
        """
        # SAFETY GUARD RAIL: Validate trading mode consistency
        try:
            self._validate_trading_operation()
        except ValueError as e:
            self.logger.error(str(e))
            return [False] * len(orders)
        
        if len(orders) > 10:
            self.logger.warning("Batch cancel limited to 10, splitting...")
            results = []
            for i in range(0, len(orders), 10):
                results.extend(self.batch_cancel_orders(orders[i:i+10]))
            return results
        
        try:
            result = self.bybit.batch_cancel_orders(orders)
            
            results = []
            for item in result.get("result", {}).get("list", []):
                results.append(item.get("code") == 0)
            
            self.logger.info(f"Batch cancelled {sum(results)}/{len(results)} orders")
            return results
            
        except Exception as e:
            self.logger.error(f"Batch cancel failed: {e}")
            return [False] * len(orders)
    
    def batch_amend_orders(
        self,
        orders: List[Dict[str, Any]],
    ) -> List[bool]:
        """
        Amend multiple orders in a batch.
        
        Args:
            orders: List of dicts with:
                - symbol: Trading symbol
                - orderId: Order ID (optional)
                - orderLinkId: Custom order ID (optional)
                - qty: New quantity (optional)
                - price: New price (optional)
        
        Returns:
            List of success booleans
        """
        # SAFETY GUARD RAIL: Validate trading mode consistency
        try:
            self._validate_trading_operation()
        except ValueError as e:
            self.logger.error(str(e))
            return [False] * len(orders)
        
        if len(orders) > 10:
            self.logger.warning("Batch amend limited to 10, splitting...")
            results = []
            for i in range(0, len(orders), 10):
                results.extend(self.batch_amend_orders(orders[i:i+10]))
            return results
        
        # Round prices
        formatted_orders = []
        for order in orders:
            formatted = {k: v for k, v in order.items()}
            if "price" in formatted:
                formatted["price"] = str(self._round_price(order["symbol"], order["price"]))
            if "qty" in formatted:
                formatted["qty"] = str(order["qty"])
            formatted_orders.append(formatted)
        
        try:
            result = self.bybit.batch_amend_orders(formatted_orders)
            
            results = []
            for item in result.get("result", {}).get("list", []):
                results.append(item.get("code") == 0)
            
            self.logger.info(f"Batch amended {sum(results)}/{len(results)} orders")
            return results
            
        except Exception as e:
            self.logger.error(f"Batch amend failed: {e}")
            return [False] * len(orders)
    
    # ==================== Unified Account Operations ====================
    
    def get_transaction_log(
        self,
        time_range: TimeRange,
        category: str = None,
        currency: str = None,
        log_type: str = None,
        limit: int = 50,
    ) -> Dict:
        """
        Get transaction logs from Unified account.
        
        CRITICAL: TimeRange is REQUIRED. We never rely on Bybit's implicit 24-hour default.
        
        Args:
            time_range: Required TimeRange specifying the query window (max 7 days)
            category: spot, linear, option
            currency: Filter by currency
            log_type: TRADE, SETTLEMENT, TRANSFER_IN, TRANSFER_OUT, etc.
            limit: Max results (1-50)
        
        Returns:
            Dict with 'list' and pagination info
        """
        try:
            result = self.bybit.get_transaction_log(
                time_range=time_range,
                category=category,
                currency=currency,
                log_type=log_type,
                limit=limit,
            )
            return result
        except Exception as e:
            self.logger.error(f"Get transaction log failed: {e}")
            return {"list": [], "error": str(e)}
    
    def get_collateral_info(self, currency: str = None) -> List[Dict]:
        """
        Get collateral information for Unified account.
        
        Args:
            currency: Specific currency (None for all)
        
        Returns:
            List of collateral info dicts with fields:
                - currency, availableToBorrow, freeBorrowingAmount
                - borrowUsageRate, marginCollateral, collateralSwitch
                - collateralRatio, etc.
        """
        try:
            return self.bybit.get_collateral_info(currency)
        except Exception as e:
            self.logger.error(f"Get collateral info failed: {e}")
            return []
    
    def set_collateral_coin(self, coin: str, enabled: bool) -> bool:
        """
        Set whether a coin is used as collateral.
        
        Args:
            coin: Coin name (e.g., BTC, ETH, USDT)
            enabled: True to enable as collateral, False to disable
        
        Returns:
            True if successful
        """
        try:
            switch = "ON" if enabled else "OFF"
            self.bybit.set_collateral_coin(coin, switch)
            self.logger.info(f"Set {coin} as collateral: {switch}")
            return True
        except Exception as e:
            self.logger.error(f"Set collateral coin failed: {e}")
            return False
    
    def get_borrow_history(
        self,
        time_range: TimeRange,
        currency: str = None,
        limit: int = 50,
    ) -> Dict:
        """
        Get borrow/interest history.
        
        CRITICAL: TimeRange is REQUIRED. We never rely on Bybit's implicit 30-day default.
        
        Args:
            time_range: Required TimeRange specifying the query window (max 30 days)
            currency: e.g., USDC, USDT, BTC
            limit: Max results
        
        Returns:
            Dict with 'list' of borrow records
        """
        try:
            result = self.bybit.get_borrow_history(
                time_range=time_range,
                currency=currency,
                limit=limit,
            )
            return result
        except Exception as e:
            self.logger.error(f"Get borrow history failed: {e}")
            return {"list": [], "error": str(e)}
    
    def get_coin_greeks(self, base_coin: str = None) -> List[Dict]:
        """
        Get current account Greeks information (for options).
        
        Args:
            base_coin: Base coin filter (BTC, ETH, etc.)
        
        Returns:
            List of coin greeks dicts
        """
        try:
            return self.bybit.get_coin_greeks(base_coin)
        except Exception as e:
            self.logger.error(f"Get coin greeks failed: {e}")
            return []
    
    def set_account_margin_mode(self, portfolio_margin: bool) -> bool:
        """
        Set account-level margin mode for Unified account.
        
        Args:
            portfolio_margin: True for PORTFOLIO_MARGIN, False for REGULAR_MARGIN
        
        Returns:
            True if successful
        """
        try:
            mode = "PORTFOLIO_MARGIN" if portfolio_margin else "REGULAR_MARGIN"
            self.bybit.set_account_margin_mode(mode)
            self.logger.info(f"Set account margin mode to {mode}")
            return True
        except Exception as e:
            # Mode might already be set
            if "not modified" in str(e).lower():
                return True
            self.logger.error(f"Set account margin mode failed: {e}")
            return False
    
    def get_transferable_amount(self, coin: str) -> float:
        """
        Get the available amount to transfer for a specific coin.
        
        Args:
            coin: Coin name (uppercase, e.g., USDT)
        
        Returns:
            Transferable amount as float
        """
        try:
            result = self.bybit.get_transferable_amount(coin)
            return safe_float(result.get("transferableAmount", 0))
        except Exception as e:
            self.logger.error(f"Get transferable amount failed: {e}")
            return 0.0
    
    # ==================== Position Configuration ====================
    
    def set_risk_limit_by_id(
        self,
        symbol: str,
        risk_id: int,
        position_idx: int = 0,
    ) -> bool:
        """
        Set risk limit for a symbol by risk ID.
        
        Use get_risk_limits() to see available risk IDs and their limits.
        
        Args:
            symbol: Trading symbol
            risk_id: Risk limit ID
            position_idx: 0=one-way, 1=buy-hedge, 2=sell-hedge
        
        Returns:
            True if successful
        """
        try:
            self.bybit.set_risk_limit(symbol, risk_id, position_idx=position_idx)
            self.logger.info(f"Set risk limit for {symbol} to ID {risk_id}")
            return True
        except Exception as e:
            self.logger.error(f"Set risk limit failed: {e}")
            return False
    
    def get_risk_limits(self, symbol: str = None) -> List[Dict]:
        """
        Get risk limit tiers for a symbol.
        
        Args:
            symbol: Trading symbol (None for all)
        
        Returns:
            List of risk limit tiers
        """
        try:
            return self.bybit.get_risk_limit(symbol)
        except Exception as e:
            self.logger.error(f"Get risk limits failed: {e}")
            return []
    
    def set_symbol_tp_sl_mode(self, symbol: str, full_mode: bool) -> bool:
        """
        Set TP/SL mode for a symbol.
        
        Args:
            symbol: Trading symbol
            full_mode: True for Full (entire position), False for Partial
        
        Returns:
            True if successful
        """
        try:
            mode = "Full" if full_mode else "Partial"
            self.bybit.set_tp_sl_mode(symbol, mode)
            self.logger.info(f"Set TP/SL mode for {symbol} to {mode}")
            return True
        except Exception as e:
            # Mode might already be set
            if "not modified" in str(e).lower():
                return True
            self.logger.error(f"Set TP/SL mode failed: {e}")
            return False
    
    def set_auto_add_margin(self, symbol: str, enabled: bool) -> bool:
        """
        Enable/disable auto-add-margin for isolated margin position.
        
        Args:
            symbol: Trading symbol
            enabled: True to enable, False to disable
        
        Returns:
            True if successful
        """
        try:
            self.bybit.set_auto_add_margin(symbol, enabled)
            status = "enabled" if enabled else "disabled"
            self.logger.info(f"Auto-add-margin {status} for {symbol}")
            return True
        except Exception as e:
            self.logger.error(f"Set auto-add-margin failed: {e}")
            return False
    
    def modify_position_margin(self, symbol: str, margin: float) -> bool:
        """
        Add or reduce margin for isolated margin position.
        
        Args:
            symbol: Trading symbol
            margin: Amount to add (positive) or reduce (negative)
        
        Returns:
            True if successful
        """
        try:
            self.bybit.modify_position_margin(symbol, margin)
            action = "Added" if margin > 0 else "Reduced"
            self.logger.info(f"{action} {abs(margin)} margin for {symbol}")
            return True
        except Exception as e:
            self.logger.error(f"Modify position margin failed: {e}")
            return False
    
    def switch_to_cross_margin(self, symbol: str, leverage: int = None) -> bool:
        """
        Switch symbol to cross margin mode.
        
        Args:
            symbol: Trading symbol
            leverage: Leverage to set (uses current if None)
        
        Returns:
            True if successful
        """
        if leverage is None:
            leverage = self.config.risk.default_leverage
        
        try:
            self.bybit.switch_cross_isolated_margin(symbol, trade_mode=0, leverage=leverage)
            return True
        except Exception as e:
            if "not modified" in str(e).lower():
                return True
            self.logger.error(f"Switch to cross margin failed: {e}")
            return False
    
    def switch_to_isolated_margin(self, symbol: str, leverage: int = None) -> bool:
        """
        Switch symbol to isolated margin mode.
        
        Args:
            symbol: Trading symbol
            leverage: Leverage to set (uses current if None)
        
        Returns:
            True if successful
        """
        if leverage is None:
            leverage = self.config.risk.default_leverage
        
        try:
            self.bybit.switch_cross_isolated_margin(symbol, trade_mode=1, leverage=leverage)
            return True
        except Exception as e:
            if "not modified" in str(e).lower():
                return True
            self.logger.error(f"Switch to isolated margin failed: {e}")
            return False
    
    def switch_to_one_way_mode(self) -> bool:
        """
        Switch to one-way position mode (can only hold Buy OR Sell).
        
        Returns:
            True if successful
        """
        try:
            self.bybit.switch_position_mode_v5(mode=0)
            return True
        except Exception as e:
            if "not modified" in str(e).lower():
                return True
            self.logger.error(f"Switch to one-way mode failed: {e}")
            return False
    
    def switch_to_hedge_mode(self) -> bool:
        """
        Switch to hedge position mode (can hold both Buy AND Sell).
        
        Returns:
            True if successful
        """
        try:
            self.bybit.switch_position_mode_v5(mode=3)
            return True
        except Exception as e:
            if "not modified" in str(e).lower():
                return True
            self.logger.error(f"Switch to hedge mode failed: {e}")
            return False
    
    # ==================== Utility ====================
    
    def get_rate_limit_status(self) -> Dict:
        """Get current rate limit status."""
        return self.bybit.get_rate_limit_status()
    
    def get_server_time_offset(self) -> int:
        """Get time offset from server in ms."""
        try:
            return self.bybit.get_time_offset()
        except Exception:
            return 0
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test exchange connectivity.
        
        Returns:
            Connection status dict
        """
        return self.bybit.test_connection()

