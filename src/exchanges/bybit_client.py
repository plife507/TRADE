"""
Bybit API client using official pybit library.

Wraps the official pybit library (https://github.com/bybit-exchange/pybit)
providing a clean interface with:
- Unified HTTP and WebSocket access
- DataFrame conversion for market data  
- Integration with trading bot logger
- Custom rate limiting layer

Reference: C:/CODE/AI/reference/exchanges/pybit/
"""

import time
from typing import Optional, Dict, List, Any, Callable, Union
from functools import wraps

import pandas as pd

# Official pybit imports
from pybit.unified_trading import HTTP, WebSocket
from pybit.exceptions import (
    FailedRequestError,
    InvalidRequestError,
    InvalidChannelTypeError,
    TopicMismatchError,
    UnauthorizedExceptionError,
)

from ..utils.rate_limiter import RateLimiter, create_bybit_limiters
from ..utils.logger import get_logger
from ..utils.helpers import safe_float


# Re-export pybit exceptions for backwards compatibility
class BybitAPIError(Exception):
    """Custom exception wrapping pybit errors for backwards compatibility."""
    
    def __init__(self, code: int, message: str, response: dict = None, original: Exception = None):
        self.code = code
        self.message = message
        self.response = response
        self.original = original
        super().__init__(f"Bybit API Error {code}: {message}")
    
    @classmethod
    def from_pybit(cls, error: Union[FailedRequestError, InvalidRequestError]):
        """Create from a pybit exception."""
        return cls(
            code=getattr(error, 'status_code', -1),
            message=str(error.message) if hasattr(error, 'message') else str(error),
            response=None,
            original=error
        )


def handle_pybit_errors(func):
    """Decorator to convert pybit exceptions to BybitAPIError."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except (FailedRequestError, InvalidRequestError) as e:
            raise BybitAPIError.from_pybit(e)
        except Exception as e:
            # Let other exceptions propagate
            raise
    return wrapper


class BybitClient:
    """
    Bybit API client using the official pybit library.
    
    Provides a unified interface for:
    - HTTP REST API calls (market data, account, trading)
    - WebSocket streams (orderbook, trades, positions)
    - Demo and live trading modes
    
    Usage:
        # Demo trading (paper trading)
        client = BybitClient(api_key="...", api_secret="...", use_demo=True)
        
        # Live trading
        client = BybitClient(api_key="...", api_secret="...", use_demo=False)
        
        # Public data only (no auth needed)
        client = BybitClient()
        df = client.get_klines("BTCUSDT", interval="15")
    """
    
    def __init__(
        self,
        api_key: str = None,
        api_secret: str = None,
        use_demo: bool = True,
        recv_window: int = 20000,
        testnet: bool = False,
        log_requests: bool = False,
    ):
        """
        Initialize Bybit client with official pybit library.
        
        Args:
            api_key: API key (optional for public endpoints)
            api_secret: API secret (optional for public endpoints)
            use_demo: Use demo trading API (default True for safety)
            recv_window: Request validity window in ms (default 10000 for clock sync tolerance)
            testnet: Use testnet instead of mainnet
            log_requests: Enable request logging in pybit
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.use_demo = use_demo
        self.testnet = testnet
        self.recv_window = recv_window
        
        # Get server time offset to handle clock sync issues
        # Bybit rejects requests if timestamp is off by more than recv_window
        self._time_offset_ms = 0
        
        # Initialize pybit HTTP session
        self._session = HTTP(
            testnet=testnet,
            demo=use_demo,
            api_key=api_key,
            api_secret=api_secret,
            recv_window=recv_window,
            log_requests=log_requests,
            return_response_headers=True,  # For rate limit tracking
        )
        
        # Logger (needed for _sync_server_time)
        self.logger = get_logger()
        
        # Sync time with server to avoid timestamp errors
        self._sync_server_time()
        
        # Base URL for logging
        if use_demo:
            self.base_url = "https://api-demo.bybit.com"
        elif testnet:
            self.base_url = "https://api-testnet.bybit.com"
        else:
            self.base_url = "https://api.bybit.com"
        
        # Rate limiters (additional layer on top of pybit's built-in)
        self._limiters = create_bybit_limiters()
        self._public_limiter = self._limiters.get_limiter("public")
        self._private_limiter = self._limiters.get_limiter("private")
        self._order_limiter = self._limiters.get_limiter("orders")
        
        # Rate limit tracking from response headers
        self._rate_limit_status = {
            "remaining": None,
            "limit": None,
            "reset_timestamp": None,
        }
        
        # WebSocket connections (lazy initialized)
        self._ws_public: Optional[WebSocket] = None
        self._ws_private: Optional[WebSocket] = None
    
    def _sync_server_time(self):
        """
        Sync local time with Bybit server to avoid timestamp errors.
        
        Bybit rejects requests where timestamp differs from server time by
        more than recv_window (error 10002). This method calculates the offset
        and monkey-patches pybit's timestamp generator to compensate.
        """
        try:
            local_time = int(time.time() * 1000)
            response = self._session.get_server_time()
            
            # Handle tuple response
            if isinstance(response, tuple):
                data, _, _ = response
                server_data = data.get("result", data)
            else:
                server_data = response.get("result", response)
            
            server_time = int(server_data.get("timeSecond", 0)) * 1000
            self._time_offset_ms = local_time - server_time
            
            # Apply offset compensation for any significant drift (> 500ms)
            if abs(self._time_offset_ms) > 500:
                self.logger.warning(
                    f"Clock sync: Local time is {self._time_offset_ms}ms "
                    f"{'ahead of' if self._time_offset_ms > 0 else 'behind'} server"
                )
                
                # Monkey-patch pybit's timestamp generator to compensate for clock drift
                # This is necessary because pybit doesn't provide a way to set a time offset
                import pybit._helpers as pybit_helpers
                offset = self._time_offset_ms
                
                def generate_timestamp_with_offset():
                    """Generate timestamp adjusted for server clock offset."""
                    return int(time.time() * 1000) - offset
                
                pybit_helpers.generate_timestamp = generate_timestamp_with_offset
                self.logger.info(f"Applied {offset}ms timestamp offset to pybit")
            else:
                self.logger.debug(f"Clock sync OK: offset is {self._time_offset_ms}ms")
                
        except Exception as e:
            self.logger.warning(f"Could not sync server time: {e}")
    
    def _update_rate_limit_status(self, response_headers):
        """Update rate limit status from response headers."""
        if response_headers:
            try:
                self._rate_limit_status = {
                    "remaining": int(response_headers.get("X-Bapi-Limit-Status", -1)),
                    "limit": int(response_headers.get("X-Bapi-Limit", -1)),
                    "reset_timestamp": int(response_headers.get("X-Bapi-Limit-Reset-Timestamp", 0)),
                }
                
                if self._rate_limit_status["remaining"] != -1 and self._rate_limit_status["remaining"] < 5:
                    self.logger.warning(
                        f"Rate limit low: {self._rate_limit_status['remaining']}/{self._rate_limit_status['limit']}"
                    )
            except (ValueError, TypeError):
                pass
    
    def _extract_result(self, response) -> dict:
        """Extract result from pybit response tuple (data, elapsed, headers)."""
        if isinstance(response, tuple):
            data, elapsed, headers = response
            self._update_rate_limit_status(headers)
            return data.get("result", data)
        return response.get("result", response) if isinstance(response, dict) else response
    
    # ==================== Public Endpoints (No Auth) ====================
    
    @handle_pybit_errors
    def get_klines(
        self,
        symbol: str,
        interval: str = "15",
        limit: int = 200,
        start: int = None,
        end: int = None,
        category: str = "linear",
    ) -> pd.DataFrame:
        """
        Get OHLCV candlestick data.
        
        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            interval: Candle interval (1, 3, 5, 15, 30, 60, 120, 240, 360, 720, D, W, M)
            limit: Number of candles (max 1000)
            start: Start timestamp in ms
            end: End timestamp in ms
            category: Market category (linear, inverse, spot)
        
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume, turnover
        """
        self._public_limiter.acquire()
        
        response = self._session.get_kline(
            category=category,
            symbol=symbol,
            interval=interval,
            limit=min(limit, 1000),
            start=start,
            end=end,
        )
        
        result = self._extract_result(response)
        data = result.get("list", [])
        
        if not data:
            return pd.DataFrame()
        
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume", "turnover"
        ])
        
        # Convert types - explicitly set UTC timezone for consistency
        df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="ms", utc=True)
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            df[col] = df[col].astype(float)
        
        # Sort by timestamp (API returns newest first)
        df = df.sort_values("timestamp").reset_index(drop=True)
        
        return df
    
    @handle_pybit_errors
    def get_ticker(self, symbol: str = None, category: str = "linear") -> Dict[str, Any]:
        """
        Get ticker information.
        
        Args:
            symbol: Trading symbol (None for all symbols)
            category: Market category
        
        Returns:
            Ticker data dict or list of tickers
        """
        self._public_limiter.acquire()
        
        response = self._session.get_tickers(
            category=category,
            symbol=symbol,
        )
        
        result = self._extract_result(response)
        tickers = result.get("list", [])
        
        if symbol and tickers:
            return tickers[0]
        return tickers
    
    @handle_pybit_errors
    def get_funding_rate(self, symbol: str, limit: int = 1, category: str = "linear") -> List[Dict]:
        """
        Get funding rate history.
        
        Args:
            symbol: Trading symbol
            limit: Number of records
            category: Market category
        
        Returns:
            List of funding rate records
        """
        self._public_limiter.acquire()
        
        response = self._session.get_funding_rate_history(
            category=category,
            symbol=symbol,
            limit=limit,
        )
        
        result = self._extract_result(response)
        return result.get("list", [])
    
    @handle_pybit_errors
    def get_open_interest(
        self, symbol: str, interval: str = "5min", limit: int = 1, category: str = "linear"
    ) -> List[Dict]:
        """
        Get open interest data.
        
        Args:
            symbol: Trading symbol
            interval: Data interval (5min, 15min, 30min, 1h, 4h, 1d)
            limit: Number of records
            category: Market category
        
        Returns:
            List of open interest records
        """
        self._public_limiter.acquire()
        
        response = self._session.get_open_interest(
            category=category,
            symbol=symbol,
            intervalTime=interval,
            limit=limit,
        )
        
        result = self._extract_result(response)
        return result.get("list", [])
    
    @handle_pybit_errors
    def get_orderbook(self, symbol: str, limit: int = 25, category: str = "linear") -> Dict:
        """
        Get orderbook depth.
        
        Args:
            symbol: Trading symbol
            limit: Number of levels (1, 25, 50, 100, 200)
            category: Market category
        
        Returns:
            Orderbook data with bids and asks
        """
        self._public_limiter.acquire()
        
        response = self._session.get_orderbook(
            category=category,
            symbol=symbol,
            limit=limit,
        )
        
        return self._extract_result(response)
    
    @handle_pybit_errors
    def get_instruments(self, symbol: str = None, category: str = "linear") -> List[Dict]:
        """
        Get instrument specifications.
        
        Args:
            symbol: Specific symbol (None for all)
            category: Market category
        
        Returns:
            List of instrument info
        """
        self._public_limiter.acquire()
        
        response = self._session.get_instruments_info(
            category=category,
            symbol=symbol,
        )
        
        result = self._extract_result(response)
        return result.get("list", [])
    
    def get_instrument_info(self, symbol: str, category: str = "linear") -> Dict:
        """
        Get instrument info for a single symbol.
        
        Args:
            symbol: Symbol to get info for
            category: Market category
        
        Returns:
            Instrument info dict or None if not found
        """
        instruments = self.get_instruments(symbol=symbol, category=category)
        return instruments[0] if instruments else None
    
    @handle_pybit_errors
    def get_server_time(self) -> Dict:
        """
        Get Bybit server time.
        
        Returns:
            Dict with timeSecond, timeNano
        """
        self._public_limiter.acquire()
        
        response = self._session.get_server_time()
        return self._extract_result(response)
    
    @handle_pybit_errors
    def get_risk_limit(self, symbol: str = None, category: str = "linear") -> List[Dict]:
        """
        Get risk limit info for symbols.
        
        Args:
            symbol: Specific symbol (None for all)
            category: Market category
        
        Returns:
            List of risk limit tiers
        """
        self._public_limiter.acquire()
        
        response = self._session.get_risk_limit(
            category=category,
            symbol=symbol,
        )
        
        result = self._extract_result(response)
        return result.get("list", [])
    
    # ==================== Private Endpoints (Auth Required) ====================
    
    @handle_pybit_errors
    def get_balance(self, account_type: str = "UNIFIED") -> Dict:
        """
        Get account balance.
        
        Args:
            account_type: Account type (UNIFIED, CONTRACT, SPOT)
        
        Returns:
            Balance data
        """
        self._private_limiter.acquire()
        
        response = self._session.get_wallet_balance(accountType=account_type)
        result = self._extract_result(response)
        
        balances = result.get("list", [])
        if balances:
            return balances[0]
        return {}
    
    @handle_pybit_errors
    def get_positions(
        self, symbol: str = None, settle_coin: str = "USDT", category: str = "linear"
    ) -> List[Dict]:
        """
        Get open positions.
        
        Args:
            symbol: Specific symbol (None for all with settleCoin)
            settle_coin: Settlement coin
            category: Market category
        
        Returns:
            List of position data
        """
        self._private_limiter.acquire()
        
        kwargs = {"category": category}
        if symbol:
            kwargs["symbol"] = symbol
        else:
            kwargs["settleCoin"] = settle_coin
        
        response = self._session.get_positions(**kwargs)
        result = self._extract_result(response)
        return result.get("list", [])
    
    @handle_pybit_errors
    def create_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        price: str = None,
        time_in_force: str = "GTC",
        reduce_only: bool = False,
        close_on_trigger: bool = False,
        category: str = "linear",
        position_idx: int = 0,
        order_link_id: str = None,
        take_profit: str = None,
        stop_loss: str = None,
        tp_trigger_by: str = None,
        sl_trigger_by: str = None,
        tpsl_mode: str = None,
        tp_order_type: str = None,
        sl_order_type: str = None,
        tp_limit_price: str = None,
        sl_limit_price: str = None,
    ) -> Dict:
        """
        Create a new order with optional TP/SL.
        
        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            side: Buy or Sell
            order_type: Market or Limit
            qty: Order quantity
            price: Limit price (required for Limit orders)
            time_in_force: GTC, IOC, FOK, PostOnly
            reduce_only: Close position only
            close_on_trigger: Close position on trigger
            category: Market category
            position_idx: Position index (0=one-way, 1=hedge-buy, 2=hedge-sell)
            order_link_id: Custom order ID
            take_profit: Take profit price
            stop_loss: Stop loss price
            tp_trigger_by: TP trigger type
            sl_trigger_by: SL trigger type
            tpsl_mode: Full or Partial
            tp_order_type: TP order type
            sl_order_type: SL order type
            tp_limit_price: TP limit price
            sl_limit_price: SL limit price
        
        Returns:
            Order result with orderId
        """
        self._order_limiter.acquire()
        
        # Build order parameters
        kwargs = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
            "timeInForce": time_in_force,
            "positionIdx": position_idx,
        }
        
        if price:
            kwargs["price"] = str(price)
        if reduce_only:
            kwargs["reduceOnly"] = True
        if close_on_trigger:
            kwargs["closeOnTrigger"] = True
        if order_link_id:
            kwargs["orderLinkId"] = order_link_id
        if take_profit:
            kwargs["takeProfit"] = str(take_profit)
        if stop_loss:
            kwargs["stopLoss"] = str(stop_loss)
        if tp_trigger_by:
            kwargs["tpTriggerBy"] = tp_trigger_by
        if sl_trigger_by:
            kwargs["slTriggerBy"] = sl_trigger_by
        if tpsl_mode:
            kwargs["tpslMode"] = tpsl_mode
        if tp_order_type:
            kwargs["tpOrderType"] = tp_order_type
        if sl_order_type:
            kwargs["slOrderType"] = sl_order_type
        if tp_limit_price:
            kwargs["tpLimitPrice"] = str(tp_limit_price)
        if sl_limit_price:
            kwargs["slLimitPrice"] = str(sl_limit_price)
        
        self.logger.trade(
            "ORDER_PLACED",
            symbol=symbol,
            side=side,
            size=float(qty),
            type=order_type
        )
        
        response = self._session.place_order(**kwargs)
        return self._extract_result(response)
    
    @handle_pybit_errors
    def amend_order(
        self,
        symbol: str,
        order_id: str = None,
        order_link_id: str = None,
        qty: str = None,
        price: str = None,
        take_profit: str = None,
        stop_loss: str = None,
        tp_trigger_by: str = None,
        sl_trigger_by: str = None,
        category: str = "linear",
    ) -> Dict:
        """
        Amend an existing order.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID to amend
            order_link_id: Custom order ID to amend
            qty: New quantity
            price: New price
            take_profit: New TP price
            stop_loss: New SL price
            tp_trigger_by: TP trigger type
            sl_trigger_by: SL trigger type
            category: Market category
        
        Returns:
            Amend result
        """
        self._order_limiter.acquire()
        
        kwargs = {
            "category": category,
            "symbol": symbol,
        }
        
        if order_id:
            kwargs["orderId"] = order_id
        if order_link_id:
            kwargs["orderLinkId"] = order_link_id
        if qty:
            kwargs["qty"] = str(qty)
        if price:
            kwargs["price"] = str(price)
        if take_profit:
            kwargs["takeProfit"] = str(take_profit)
        if stop_loss:
            kwargs["stopLoss"] = str(stop_loss)
        if tp_trigger_by:
            kwargs["tpTriggerBy"] = tp_trigger_by
        if sl_trigger_by:
            kwargs["slTriggerBy"] = sl_trigger_by
        
        self.logger.info(f"Amending order {order_id or order_link_id} for {symbol}")
        
        response = self._session.amend_order(**kwargs)
        return self._extract_result(response)
    
    @handle_pybit_errors
    def cancel_order(
        self, symbol: str, order_id: str = None, order_link_id: str = None, category: str = "linear"
    ) -> Dict:
        """
        Cancel an order.
        
        Args:
            symbol: Trading symbol
            order_id: Order ID to cancel
            order_link_id: Client order ID to cancel
            category: Market category
        
        Returns:
            Cancel result
        """
        self._order_limiter.acquire()
        
        kwargs = {
            "category": category,
            "symbol": symbol,
        }
        if order_id:
            kwargs["orderId"] = order_id
        if order_link_id:
            kwargs["orderLinkId"] = order_link_id
        
        response = self._session.cancel_order(**kwargs)
        return self._extract_result(response)
    
    @handle_pybit_errors
    def cancel_all_orders(self, symbol: str = None, category: str = "linear") -> Dict:
        """
        Cancel all open orders.
        
        Args:
            symbol: Specific symbol (None for all)
            category: Market category
        
        Returns:
            Cancel result
        """
        self._order_limiter.acquire()
        
        kwargs = {"category": category}
        if symbol:
            kwargs["symbol"] = symbol
        
        self.logger.warning(f"Cancelling all orders{f' for {symbol}' if symbol else ''}")
        
        response = self._session.cancel_all_orders(**kwargs)
        return self._extract_result(response)
    
    @handle_pybit_errors
    def get_open_orders(
        self, 
        symbol: str = None, 
        settle_coin: str = "USDT",
        category: str = "linear"
    ) -> List[Dict]:
        """
        Get open orders.
        
        Args:
            symbol: Specific symbol (None for all with settleCoin)
            settle_coin: Settlement coin (required if symbol is None)
            category: Market category
        
        Returns:
            List of open orders
        """
        self._private_limiter.acquire()
        
        kwargs = {"category": category}
        if symbol:
            kwargs["symbol"] = symbol
        else:
            kwargs["settleCoin"] = settle_coin
        
        response = self._session.get_open_orders(**kwargs)
        result = self._extract_result(response)
        return result.get("list", [])
    
    @handle_pybit_errors
    def get_order_history(
        self,
        symbol: str = None,
        order_id: str = None,
        order_link_id: str = None,
        order_status: str = None,
        start_time: int = None,
        end_time: int = None,
        limit: int = 50,
        cursor: str = None,
        category: str = "linear",
    ) -> Dict:
        """
        Get order history.
        
        Args:
            symbol: Trading symbol
            order_id: Specific order ID
            order_link_id: Custom order ID
            order_status: Filter by status
            start_time: Start timestamp (ms)
            end_time: End timestamp (ms)
            limit: Results limit
            cursor: Pagination cursor
            category: Market category
        
        Returns:
            Order history with pagination
        """
        self._private_limiter.acquire()
        
        kwargs = {
            "category": category,
            "limit": min(limit, 50),
        }
        if symbol:
            kwargs["symbol"] = symbol
        if order_id:
            kwargs["orderId"] = order_id
        if order_link_id:
            kwargs["orderLinkId"] = order_link_id
        if order_status:
            kwargs["orderStatus"] = order_status
        if start_time:
            kwargs["startTime"] = start_time
        if end_time:
            kwargs["endTime"] = end_time
        if cursor:
            kwargs["cursor"] = cursor
        
        response = self._session.get_order_history(**kwargs)
        return self._extract_result(response)
    
    @handle_pybit_errors
    def set_leverage(self, symbol: str, leverage: int, category: str = "linear") -> Dict:
        """
        Set leverage for a symbol.
        
        Args:
            symbol: Trading symbol
            leverage: Leverage multiplier
            category: Market category
        
        Returns:
            Result
        """
        self._private_limiter.acquire()
        
        self.logger.info(f"Setting leverage for {symbol} to {leverage}x")
        
        response = self._session.set_leverage(
            category=category,
            symbol=symbol,
            buyLeverage=str(leverage),
            sellLeverage=str(leverage),
        )
        return self._extract_result(response)
    
    @handle_pybit_errors
    def create_conditional_order(
        self,
        symbol: str,
        side: str,
        qty: str,
        trigger_price: str,
        trigger_direction: int,  # 1=rise to trigger, 2=fall to trigger
        order_type: str = "Market",
        price: str = None,
        reduce_only: bool = True,
        category: str = "linear",
        order_link_id: str = None,
    ) -> Dict:
        """
        Create a conditional (trigger) order for TP/SL.
        
        These are real orders that persist on Bybit until triggered or cancelled.
        
        Args:
            symbol: Trading symbol
            side: Buy or Sell (to close position, use opposite side)
            qty: Order quantity
            trigger_price: Price that triggers the order
            trigger_direction: 1=triggers when price rises to trigger_price
                             2=triggers when price falls to trigger_price
            order_type: Market or Limit
            price: Limit price (required for Limit orders)
            reduce_only: If True, only reduces position (for TP/SL)
            category: Market category
            order_link_id: Custom order ID for tracking
        
        Returns:
            Order result with orderId
        
        Example:
            # SHORT position TP (price falls, buy to close)
            create_conditional_order(
                symbol="SOLUSDT",
                side="Buy",
                qty="100",
                trigger_price="130.00",
                trigger_direction=2,  # Falls to trigger
                reduce_only=True
            )
        """
        self._order_limiter.acquire()
        
        kwargs = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": str(qty),
            "triggerPrice": str(trigger_price),
            "triggerDirection": trigger_direction,
            "reduceOnly": reduce_only,
        }
        
        if price and order_type == "Limit":
            kwargs["price"] = str(price)
        if order_link_id:
            kwargs["orderLinkId"] = order_link_id
        
        self.logger.info(f"[CONDITIONAL_ORDER] {side} {qty} {symbol} @ trigger ${trigger_price}")
        
        response = self._session.place_order(**kwargs)
        return self._extract_result(response)
    
    @handle_pybit_errors
    def set_trading_stop(
        self,
        symbol: str,
        take_profit: str = None,
        stop_loss: str = None,
        trailing_stop: str = None,
        tp_trigger_by: str = None,
        sl_trigger_by: str = None,
        tpsl_mode: str = None,
        tp_size: str = None,
        sl_size: str = None,
        category: str = "linear",
        position_idx: int = 0,
    ) -> Dict:
        """
        Set TP/SL/Trailing stop for an existing position.
        
        Args:
            symbol: Trading symbol
            take_profit: TP price (0 to cancel)
            stop_loss: SL price (0 to cancel)
            trailing_stop: Trailing stop distance
            tp_trigger_by: TP trigger type
            sl_trigger_by: SL trigger type
            tpsl_mode: Full or Partial
            tp_size: TP size for partial mode
            sl_size: SL size for partial mode
            category: Market category
            position_idx: Position index
        
        Returns:
            Result
        """
        self._private_limiter.acquire()
        
        kwargs = {
            "category": category,
            "symbol": symbol,
            "positionIdx": position_idx,
        }
        
        if take_profit is not None:
            kwargs["takeProfit"] = str(take_profit)
        if stop_loss is not None:
            kwargs["stopLoss"] = str(stop_loss)
        if trailing_stop is not None:
            kwargs["trailingStop"] = str(trailing_stop)
        if tp_trigger_by:
            kwargs["tpTriggerBy"] = tp_trigger_by
        if sl_trigger_by:
            kwargs["slTriggerBy"] = sl_trigger_by
        if tpsl_mode:
            kwargs["tpslMode"] = tpsl_mode
        if tp_size:
            kwargs["tpSize"] = str(tp_size)
        if sl_size:
            kwargs["slSize"] = str(sl_size)
        
        self.logger.info(f"Setting trading stop for {symbol}: TP={take_profit}, SL={stop_loss}")
        
        response = self._session.set_trading_stop(**kwargs)
        return self._extract_result(response)
    
    @handle_pybit_errors
    def get_executions(
        self,
        symbol: str = None,
        order_id: str = None,
        start_time: int = None,
        end_time: int = None,
        limit: int = 50,
        cursor: str = None,
        category: str = "linear",
    ) -> List[Dict]:
        """
        Get trade execution history.
        
        Args:
            symbol: Trading symbol
            order_id: Specific order ID
            start_time: Start timestamp (ms)
            end_time: End timestamp (ms)
            limit: Results limit
            cursor: Pagination cursor
            category: Market category
        
        Returns:
            List of execution records
        """
        self._private_limiter.acquire()
        
        kwargs = {
            "category": category,
            "limit": min(limit, 50),
        }
        if symbol:
            kwargs["symbol"] = symbol
        if order_id:
            kwargs["orderId"] = order_id
        if start_time:
            kwargs["startTime"] = start_time
        if end_time:
            kwargs["endTime"] = end_time
        if cursor:
            kwargs["cursor"] = cursor
        
        response = self._session.get_executions(**kwargs)
        result = self._extract_result(response)
        return result.get("list", [])
    
    @handle_pybit_errors
    def get_closed_pnl(
        self,
        symbol: str = None,
        start_time: int = None,
        end_time: int = None,
        limit: int = 50,
        cursor: str = None,
        category: str = "linear",
    ) -> Dict:
        """
        Get closed position PnL records.
        
        Args:
            symbol: Trading symbol
            start_time: Start timestamp (ms)
            end_time: End timestamp (ms)
            limit: Results limit
            cursor: Pagination cursor
            category: Market category
        
        Returns:
            Closed PnL records with pagination
        """
        self._private_limiter.acquire()
        
        kwargs = {
            "category": category,
            "limit": min(limit, 50),
        }
        if symbol:
            kwargs["symbol"] = symbol
        if start_time:
            kwargs["startTime"] = start_time
        if end_time:
            kwargs["endTime"] = end_time
        if cursor:
            kwargs["cursor"] = cursor
        
        response = self._session.get_closed_pnl(**kwargs)
        return self._extract_result(response)
    
    # ==================== Batch Order Endpoints ====================
    
    @handle_pybit_errors
    def batch_create_orders(self, orders: List[Dict], category: str = "linear") -> Dict:
        """
        Create multiple orders in a single request (max 10).
        
        Args:
            orders: List of order dicts
            category: Market category
        
        Returns:
            Batch result
        """
        self._order_limiter.acquire()
        
        if len(orders) > 10:
            raise ValueError("Batch create supports max 10 orders")
        
        self.logger.info(f"Batch creating {len(orders)} orders")
        
        response = self._session.place_batch_order(
            category=category,
            request=orders,
        )
        return self._extract_result(response)
    
    @handle_pybit_errors
    def batch_amend_orders(self, orders: List[Dict], category: str = "linear") -> Dict:
        """
        Amend multiple orders in a single request (max 10).
        
        Args:
            orders: List of amend dicts
            category: Market category
        
        Returns:
            Batch result
        """
        self._order_limiter.acquire()
        
        if len(orders) > 10:
            raise ValueError("Batch amend supports max 10 orders")
        
        self.logger.info(f"Batch amending {len(orders)} orders")
        
        response = self._session.amend_batch_order(
            category=category,
            request=orders,
        )
        return self._extract_result(response)
    
    @handle_pybit_errors
    def batch_cancel_orders(self, orders: List[Dict], category: str = "linear") -> Dict:
        """
        Cancel multiple orders in a single request (max 10).
        
        Args:
            orders: List of cancel dicts
            category: Market category
        
        Returns:
            Batch result
        """
        self._order_limiter.acquire()
        
        if len(orders) > 10:
            raise ValueError("Batch cancel supports max 10 orders")
        
        self.logger.info(f"Batch cancelling {len(orders)} orders")
        
        response = self._session.cancel_batch_order(
            category=category,
            request=orders,
        )
        return self._extract_result(response)
    
    # ==================== Account Info ====================
    
    @handle_pybit_errors
    def get_account_info(self) -> Dict:
        """
        Get account configuration info (margin mode, etc.)
        
        Returns:
            Account info dict
        """
        self._private_limiter.acquire()
        
        response = self._session.get_account_info()
        return self._extract_result(response)
    
    @handle_pybit_errors
    def get_fee_rates(self, symbol: str = None, category: str = "linear") -> Dict:
        """
        Get trading fee rates.
        
        Args:
            symbol: Specific symbol
            category: Market category
        
        Returns:
            Fee rate info
        """
        self._private_limiter.acquire()
        
        kwargs = {"category": category}
        if symbol:
            kwargs["symbol"] = symbol
        
        response = self._session.get_fee_rates(**kwargs)
        return self._extract_result(response)
    
    # ==================== Utilities ====================
    
    def get_time_offset(self) -> int:
        """
        Calculate time offset between local and server time.
        
        Returns:
            Offset in milliseconds (positive = local ahead)
        """
        local_time = int(time.time() * 1000)
        server_data = self.get_server_time()
        server_time = int(server_data.get("timeSecond", 0)) * 1000
        return local_time - server_time
    
    def get_rate_limit_status(self) -> Dict:
        """
        Get current rate limit status from last request.
        
        Returns:
            Dict with remaining, limit, reset_timestamp
        """
        return self._rate_limit_status.copy()
    
    def test_connection(self) -> Dict[str, Any]:
        """
        Test API connectivity and get system status.
        
        Returns:
            Dict with connection status, balance, time sync info
        """
        result = {
            "demo_mode": self.use_demo,
            "testnet": self.testnet,
            "base_url": self.base_url,
            "public_ok": False,
            "private_ok": False,
            "time_offset_ms": None,
            "error": None,
        }
        
        # Test server time
        try:
            time_offset = self.get_time_offset()
            result["time_offset_ms"] = time_offset
            if abs(time_offset) > 5000:
                self.logger.warning(f"Large time offset: {time_offset}ms")
        except Exception as e:
            self.logger.warning(f"Could not get server time: {e}")
        
        # Test public endpoint
        try:
            ticker = self.get_ticker("BTCUSDT")
            result["public_ok"] = True
            result["btc_price"] = ticker.get("lastPrice")
        except Exception as e:
            result["error"] = f"Public endpoint failed: {e}"
            return result
        
        # Test private endpoint
        if self.api_key and self.api_secret:
            try:
                balance = self.get_balance()
                result["private_ok"] = True
                
                coins = balance.get("coin", [])
                for coin in coins:
                    if coin.get("coin") == "USDT":
                        result["usdt_balance"] = safe_float(coin.get("walletBalance"))
                        result["usdt_available"] = safe_float(coin.get("availableToWithdraw"))
                        break
                
                result["rate_limit"] = self.get_rate_limit_status()
            except Exception as e:
                result["error"] = f"Private endpoint failed: {e}"
        else:
            result["private_ok"] = None
        
        return result
    
    # ==================== WebSocket Interface ====================
    
    # WebSocket endpoint modes:
    # - LIVE: stream.bybit.com (REAL MONEY)
    # - DEMO: stream-demo.bybit.com (FAKE MONEY)
    #
    # PUBLIC streams (market data): Can use LIVE for all modes since market
    # data is the same. DEMO mode may optionally use stream-demo.bybit.com.
    #
    # PRIVATE streams (positions, orders): Must match the REST API mode since
    # authentication is account-specific.
    
    def connect_public_ws(
        self,
        channel_type: str = "linear",
        use_mainnet_for_market_data: bool = False,
    ) -> WebSocket:
        """
        Connect to public WebSocket stream for market data.
        
        Args:
            channel_type: linear, inverse, spot, option
            use_mainnet_for_market_data: If True, always use LIVE stream
                for market data even in DEMO mode (market data is the same).
                If False, use the appropriate DEMO stream.
        
        Returns:
            WebSocket instance for subscribing to public streams
        
        Note:
            Market data (tickers, orderbook, trades, klines) is the same across
            LIVE and DEMO. You can use LIVE streams even when trading in DEMO.
            Set use_mainnet_for_market_data=True if you experience issues with 
            DEMO WebSocket streams.
        """
        if self._ws_public is not None:
            return self._ws_public
        
        # Determine WebSocket mode
        # For public data, we can optionally use LIVE since market data is shared
        if use_mainnet_for_market_data:
            ws_testnet = False
            ws_demo = False
            stream_type = "LIVE"
        else:
            ws_testnet = self.testnet
            ws_demo = self.use_demo
            if self.use_demo:
                stream_type = "DEMO"
            elif self.testnet:
                stream_type = "testnet"
            else:
                stream_type = "LIVE"
        
        # Per Bybit docs: "Do not frequently connect and disconnect"
        # "Do not build over 500 connections in 5 minutes"
        # Use low retries + no auto-restart to fail fast → REST fallback
        self._ws_public = WebSocket(
            testnet=ws_testnet,
            demo=ws_demo,
            channel_type=channel_type,
            retries=2,  # Fail fast, use REST fallback (default is 10)
            restart_on_error=False,  # Don't auto-reconnect, let app manage
            ping_interval=20,  # Bybit recommends 20s heartbeat
            ping_timeout=10,
        )
        
        self.logger.info(f"Connected to public WebSocket ({channel_type}, {stream_type})")
        return self._ws_public
    
    def connect_private_ws(self) -> WebSocket:
        """
        Connect to private WebSocket stream for positions/orders.
        
        Private streams must match the REST API mode since authentication
        is account-specific:
        - DEMO mode → stream-demo.bybit.com (FAKE MONEY account)
        - LIVE mode → stream.bybit.com (REAL MONEY account)
        
        Returns:
            WebSocket instance for subscribing to private streams
        
        Raises:
            ValueError: If API credentials are not provided
        """
        if self._ws_private is not None:
            return self._ws_private
        
        if not self.api_key or not self.api_secret:
            raise ValueError("API credentials required for private WebSocket")
        
        # Private streams must match the REST API mode
        # Per Bybit docs: Use low retries to fail fast → REST fallback
        self._ws_private = WebSocket(
            testnet=self.testnet,
            demo=self.use_demo,
            channel_type="private",
            api_key=self.api_key,
            api_secret=self.api_secret,
            retries=2,  # Fail fast, use REST fallback (default is 10)
            restart_on_error=False,  # Don't auto-reconnect, let app manage
            ping_interval=20,  # Bybit recommends 20s heartbeat
            ping_timeout=10,
        )
        
        # Log which mode we're using with standardized terminology
        if self.use_demo:
            stream_type = "DEMO (FAKE MONEY)"
        elif self.testnet:
            stream_type = "testnet"
        else:
            stream_type = "LIVE (REAL MONEY)"
        
        self.logger.info(f"Connected to private WebSocket ({stream_type})")
        return self._ws_private
    
    def subscribe_ticker(self, symbol: Union[str, List[str]], callback: Callable):
        """
        Subscribe to ticker updates.
        
        Args:
            symbol: Symbol(s) to subscribe
            callback: Function called with each update
        """
        ws = self.connect_public_ws()
        ws.ticker_stream(symbol=symbol, callback=callback)
        self.logger.info(f"Subscribed to ticker: {symbol}")
    
    def subscribe_orderbook(self, symbol: Union[str, List[str]], callback: Callable, depth: int = 50):
        """
        Subscribe to orderbook updates.
        
        Args:
            symbol: Symbol(s) to subscribe
            callback: Function called with each update
            depth: Orderbook depth (1, 25, 50, 100, 200)
        """
        ws = self.connect_public_ws()
        ws.orderbook_stream(depth=depth, symbol=symbol, callback=callback)
        self.logger.info(f"Subscribed to orderbook({depth}): {symbol}")
    
    def subscribe_trades(self, symbol: Union[str, List[str]], callback: Callable):
        """
        Subscribe to public trade stream.
        
        Args:
            symbol: Symbol(s) to subscribe
            callback: Function called with each update
        """
        ws = self.connect_public_ws()
        ws.trade_stream(symbol=symbol, callback=callback)
        self.logger.info(f"Subscribed to trades: {symbol}")
    
    def subscribe_klines(self, symbol: Union[str, List[str]], interval: int, callback: Callable):
        """
        Subscribe to kline/candlestick updates.
        
        Args:
            symbol: Symbol(s) to subscribe
            interval: Kline interval (1, 3, 5, 15, 30, 60, etc.)
            callback: Function called with each update
        """
        ws = self.connect_public_ws()
        ws.kline_stream(interval=interval, symbol=symbol, callback=callback)
        self.logger.info(f"Subscribed to klines({interval}): {symbol}")
    
    def subscribe_positions(self, callback: Callable):
        """
        Subscribe to position updates.
        
        Args:
            callback: Function called with each position update
        """
        ws = self.connect_private_ws()
        ws.position_stream(callback=callback)
        self.logger.info("Subscribed to position updates")
    
    def subscribe_orders(self, callback: Callable):
        """
        Subscribe to order updates.
        
        Args:
            callback: Function called with each order update
        """
        ws = self.connect_private_ws()
        ws.order_stream(callback=callback)
        self.logger.info("Subscribed to order updates")
    
    def subscribe_executions(self, callback: Callable):
        """
        Subscribe to execution/fill updates.
        
        Args:
            callback: Function called with each execution
        """
        ws = self.connect_private_ws()
        ws.execution_stream(callback=callback)
        self.logger.info("Subscribed to execution updates")
    
    def subscribe_wallet(self, callback: Callable):
        """
        Subscribe to wallet/balance updates.
        
        Args:
            callback: Function called with each wallet update
        """
        ws = self.connect_private_ws()
        ws.wallet_stream(callback=callback)
        self.logger.info("Subscribed to wallet updates")
    
    def close_websockets(self, suppress_errors: bool = True, wait_for_threads: float = 0.5):
        """
        Close all WebSocket connections gracefully.
        
        Args:
            suppress_errors: If True, install a hook to suppress thread cleanup 
                            errors from pybit's ping threads (default: True)
            wait_for_threads: Seconds to wait for background threads to clean up
        """
        import threading
        import time
        
        # Install thread exception hook to suppress WebSocket cleanup errors
        if suppress_errors:
            _install_ws_cleanup_hook()
        
        if self._ws_public:
            try:
                self._ws_public.exit()
            except Exception:
                pass
            self._ws_public = None
        
        if self._ws_private:
            try:
                self._ws_private.exit()
            except Exception:
                pass
            self._ws_private = None
        
        # Give background threads time to clean up
        if wait_for_threads > 0:
            time.sleep(wait_for_threads)
        
        self.logger.info("WebSocket connections closed")
    
    # ==================== Direct pybit Access ====================
    
    # ==================== Account Endpoints (Extended) ====================
    
    @handle_pybit_errors
    def get_transaction_log(
        self,
        account_type: str = "UNIFIED",
        category: str = None,
        currency: str = None,
        base_coin: str = None,
        log_type: str = None,
        start_time: int = None,
        end_time: int = None,
        limit: int = 50,
        cursor: str = None,
    ) -> Dict:
        """
        Get transaction logs in Unified account.
        
        Args:
            account_type: UNIFIED (default)
            category: spot, linear, option
            currency: Filter by currency
            base_coin: Base coin filter
            log_type: TRANSFER_IN, TRANSFER_OUT, TRADE, SETTLEMENT, 
                     DELIVERY, LIQUIDATION, BONUS, FEE_REFUND, INTEREST,
                     CURRENCY_BUY, CURRENCY_SELL
            start_time: Start timestamp (ms)
            end_time: End timestamp (ms)
            limit: Results limit (max 50)
            cursor: Pagination cursor
        
        Returns:
            Transaction log records with pagination
        """
        self._private_limiter.acquire()
        
        kwargs = {"accountType": account_type, "limit": min(limit, 50)}
        if category:
            kwargs["category"] = category
        if currency:
            kwargs["currency"] = currency
        if base_coin:
            kwargs["baseCoin"] = base_coin
        if log_type:
            kwargs["type"] = log_type
        if start_time:
            kwargs["startTime"] = start_time
        if end_time:
            kwargs["endTime"] = end_time
        if cursor:
            kwargs["cursor"] = cursor
        
        response = self._session.get_transaction_log(**kwargs)
        return self._extract_result(response)
    
    @handle_pybit_errors
    def get_collateral_info(self, currency: str = None) -> List[Dict]:
        """
        Get collateral information for Unified account.
        
        Args:
            currency: Specific currency (None for all)
        
        Returns:
            List of collateral info dicts
        """
        self._private_limiter.acquire()
        
        kwargs = {}
        if currency:
            kwargs["currency"] = currency
        
        response = self._session.get_collateral_info(**kwargs)
        result = self._extract_result(response)
        return result.get("list", [])
    
    @handle_pybit_errors
    def set_collateral_coin(self, coin: str, switch: str) -> Dict:
        """
        Set whether a coin is used as collateral in Unified account.
        
        Args:
            coin: Coin name (e.g., "BTC", "ETH")
            switch: "ON" or "OFF"
        
        Returns:
            Result dict
        """
        self._private_limiter.acquire()
        
        self.logger.info(f"Setting collateral for {coin}: {switch}")
        
        response = self._session.set_collateral_coin(
            coin=coin,
            collateralSwitch=switch,
        )
        return self._extract_result(response)
    
    @handle_pybit_errors
    def batch_set_collateral_coin(self, coins: List[Dict[str, str]]) -> Dict:
        """
        Batch set collateral coins.
        
        Args:
            coins: List of {"coin": "BTC", "collateralSwitch": "ON"} dicts
        
        Returns:
            Result dict
        """
        self._private_limiter.acquire()
        
        self.logger.info(f"Batch setting collateral for {len(coins)} coins")
        
        response = self._session.batch_set_collateral_coin(request=coins)
        return self._extract_result(response)
    
    @handle_pybit_errors
    def get_borrow_history(
        self,
        currency: str = None,
        start_time: int = None,
        end_time: int = None,
        limit: int = 50,
        cursor: str = None,
    ) -> Dict:
        """
        Get borrow/interest history.
        
        Args:
            currency: e.g., USDC, USDT, BTC, ETH
            start_time: Start timestamp (ms)
            end_time: End timestamp (ms)
            limit: Results limit (max 50)
            cursor: Pagination cursor
        
        Returns:
            Borrow history with pagination
        """
        self._private_limiter.acquire()
        
        kwargs = {"limit": min(limit, 50)}
        if currency:
            kwargs["currency"] = currency
        if start_time:
            kwargs["startTime"] = start_time
        if end_time:
            kwargs["endTime"] = end_time
        if cursor:
            kwargs["cursor"] = cursor
        
        response = self._session.get_borrow_history(**kwargs)
        return self._extract_result(response)
    
    @handle_pybit_errors
    def repay_liability(self, coin: str = None) -> Dict:
        """
        Manually repay liabilities of the Unified account.
        
        Args:
            coin: Specific coin to repay (None for all)
        
        Returns:
            Result dict
        """
        self._private_limiter.acquire()
        
        kwargs = {}
        if coin:
            kwargs["coin"] = coin
        
        self.logger.info(f"Repaying liability{f' for {coin}' if coin else ''}")
        
        response = self._session.repay_liability(**kwargs)
        return self._extract_result(response)
    
    @handle_pybit_errors
    def get_coin_greeks(self, base_coin: str = None) -> List[Dict]:
        """
        Get current account Greeks information (for options).
        
        Args:
            base_coin: Base coin filter (e.g., BTC, ETH)
        
        Returns:
            List of coin greeks dicts
        """
        self._private_limiter.acquire()
        
        kwargs = {}
        if base_coin:
            kwargs["baseCoin"] = base_coin
        
        response = self._session.get_coin_greeks(**kwargs)
        result = self._extract_result(response)
        return result.get("list", [])
    
    @handle_pybit_errors
    def set_account_margin_mode(self, margin_mode: str) -> Dict:
        """
        Set account-level margin mode for Unified account.
        
        Args:
            margin_mode: REGULAR_MARGIN or PORTFOLIO_MARGIN
        
        Returns:
            Result dict
        """
        self._private_limiter.acquire()
        
        self.logger.info(f"Setting account margin mode to {margin_mode}")
        
        response = self._session.set_margin_mode(setMarginMode=margin_mode)
        return self._extract_result(response)
    
    @handle_pybit_errors
    def upgrade_to_unified_account(self) -> Dict:
        """
        Upgrade to Unified Trading Account.
        
        Warning: This is a one-way operation.
        
        Returns:
            Result dict with unifiedUpdateStatus and unifiedUpdateMsg
        """
        self._private_limiter.acquire()
        
        self.logger.warning("Upgrading to Unified Trading Account")
        
        response = self._session.upgrade_to_unified_trading_account()
        return self._extract_result(response)
    
    @handle_pybit_errors
    def get_transferable_amount(self, coin: str) -> Dict:
        """
        Query the available amount to transfer of a specific coin in Unified wallet.
        
        Args:
            coin: Coin name (uppercase, e.g., USDT)
        
        Returns:
            Transferable amount info
        """
        self._private_limiter.acquire()
        
        response = self._session.get_transferable_amount(coinName=coin)
        return self._extract_result(response)
    
    @handle_pybit_errors
    def get_mmp_state(self, base_coin: str) -> Dict:
        """
        Get Market Maker Protection (MMP) state.
        
        Args:
            base_coin: Base coin (e.g., BTC, ETH)
        
        Returns:
            MMP state info
        """
        self._private_limiter.acquire()
        
        response = self._session.get_mmp_state(baseCoin=base_coin)
        return self._extract_result(response)
    
    @handle_pybit_errors
    def set_mmp(
        self,
        base_coin: str,
        window: str,
        frozen_period: str,
        qty_limit: str,
        delta_limit: str,
    ) -> Dict:
        """
        Set Market Maker Protection (MMP) parameters.
        
        Args:
            base_coin: Base coin (e.g., BTC, ETH)
            window: Time window in ms
            frozen_period: Frozen period in ms (0 = freeze until manual reset)
            qty_limit: Trade qty limit
            delta_limit: Delta limit
        
        Returns:
            Result dict
        """
        self._private_limiter.acquire()
        
        self.logger.info(f"Setting MMP for {base_coin}")
        
        response = self._session.set_mmp(
            baseCoin=base_coin,
            window=window,
            frozenPeriod=frozen_period,
            qtyLimit=qty_limit,
            deltaLimit=delta_limit,
        )
        return self._extract_result(response)
    
    @handle_pybit_errors
    def reset_mmp(self, base_coin: str) -> Dict:
        """
        Reset/unfreeze MMP for a base coin.
        
        Args:
            base_coin: Base coin (e.g., BTC, ETH)
        
        Returns:
            Result dict
        """
        self._private_limiter.acquire()
        
        self.logger.info(f"Resetting MMP for {base_coin}")
        
        response = self._session.reset_mmp(baseCoin=base_coin)
        return self._extract_result(response)
    
    # ==================== Position Endpoints (Extended) ====================
    
    @handle_pybit_errors
    def set_risk_limit(
        self,
        symbol: str,
        risk_id: int,
        category: str = "linear",
        position_idx: int = 0,
    ) -> Dict:
        """
        Set risk limit for a symbol.
        
        Args:
            symbol: Trading symbol
            risk_id: Risk limit ID (get from get_risk_limit)
            category: linear or inverse
            position_idx: 0=one-way, 1=buy-hedge, 2=sell-hedge
        
        Returns:
            Result dict
        """
        self._private_limiter.acquire()
        
        self.logger.info(f"Setting risk limit for {symbol} to ID {risk_id}")
        
        response = self._session.set_risk_limit(
            category=category,
            symbol=symbol,
            riskId=risk_id,
            positionIdx=position_idx,
        )
        return self._extract_result(response)
    
    @handle_pybit_errors
    def set_tp_sl_mode(
        self,
        symbol: str,
        tp_sl_mode: str,
        category: str = "linear",
    ) -> Dict:
        """
        Set TP/SL mode for a symbol.
        
        Args:
            symbol: Trading symbol
            tp_sl_mode: "Full" (entire position) or "Partial"
            category: linear or inverse
        
        Returns:
            Result dict
        """
        self._private_limiter.acquire()
        
        self.logger.info(f"Setting TP/SL mode for {symbol} to {tp_sl_mode}")
        
        response = self._session.set_tp_sl_mode(
            category=category,
            symbol=symbol,
            tpSlMode=tp_sl_mode,
        )
        return self._extract_result(response)
    
    @handle_pybit_errors
    def set_auto_add_margin(
        self,
        symbol: str,
        auto_add: bool,
        category: str = "linear",
        position_idx: int = 0,
    ) -> Dict:
        """
        Turn on/off auto-add-margin for isolated margin position.
        
        Args:
            symbol: Trading symbol
            auto_add: True to enable, False to disable
            category: linear
            position_idx: 0=one-way, 1=buy-hedge, 2=sell-hedge
        
        Returns:
            Result dict
        """
        self._private_limiter.acquire()
        
        self.logger.info(f"Setting auto-add-margin for {symbol}: {auto_add}")
        
        response = self._session.set_auto_add_margin(
            category=category,
            symbol=symbol,
            autoAddMargin=1 if auto_add else 0,
            positionIdx=position_idx,
        )
        return self._extract_result(response)
    
    @handle_pybit_errors
    def modify_position_margin(
        self,
        symbol: str,
        margin: float,
        category: str = "linear",
        position_idx: int = 0,
    ) -> Dict:
        """
        Manually add or reduce margin for isolated margin position.
        
        Args:
            symbol: Trading symbol
            margin: Amount to add (positive) or reduce (negative)
            category: linear
            position_idx: 0=one-way, 1=buy-hedge, 2=sell-hedge
        
        Returns:
            Result dict
        """
        self._private_limiter.acquire()
        
        action = "Adding" if margin > 0 else "Reducing"
        self.logger.info(f"{action} {abs(margin)} margin for {symbol}")
        
        response = self._session.add_or_reduce_margin(
            category=category,
            symbol=symbol,
            margin=str(margin),
            positionIdx=position_idx,
        )
        return self._extract_result(response)
    
    @handle_pybit_errors
    def switch_cross_isolated_margin(
        self,
        symbol: str,
        trade_mode: int,
        leverage: int,
        category: str = "linear",
    ) -> Dict:
        """
        Switch between cross and isolated margin mode.
        
        Args:
            symbol: Trading symbol
            trade_mode: 0=cross, 1=isolated
            leverage: Leverage to set (same for buy/sell)
            category: linear or inverse
        
        Returns:
            Result dict
        """
        self._private_limiter.acquire()
        
        mode_name = "cross" if trade_mode == 0 else "isolated"
        self.logger.info(f"Switching {symbol} to {mode_name} margin with {leverage}x leverage")
        
        response = self._session.switch_margin_mode(
            category=category,
            symbol=symbol,
            tradeMode=trade_mode,
            buyLeverage=str(leverage),
            sellLeverage=str(leverage),
        )
        return self._extract_result(response)
    
    @handle_pybit_errors
    def switch_position_mode_v5(
        self,
        mode: int,
        category: str = "linear",
        symbol: str = None,
        coin: str = None,
    ) -> Dict:
        """
        Switch position mode (one-way vs hedge mode).
        
        Args:
            mode: 0=MergedSingle (one-way), 3=BothSide (hedge)
            category: linear or inverse
            symbol: Symbol name (optional, for symbol-specific mode)
            coin: Coin name (optional, e.g., USDT)
        
        Returns:
            Result dict
        """
        self._private_limiter.acquire()
        
        mode_name = "one-way" if mode == 0 else "hedge"
        self.logger.info(f"Switching to {mode_name} position mode")
        
        kwargs = {
            "category": category,
            "mode": mode,
        }
        if symbol:
            kwargs["symbol"] = symbol
        if coin:
            kwargs["coin"] = coin
        
        response = self._session.switch_position_mode(**kwargs)
        return self._extract_result(response)
    
    # ==================== Trade Endpoints (Extended) ====================
    
    @handle_pybit_errors
    def get_borrow_quota(
        self,
        symbol: str,
        side: str,
        category: str = "spot",
    ) -> Dict:
        """
        Query the qty and amount of borrowable coins in spot account.
        
        Args:
            symbol: Symbol name
            side: Buy or Sell
            category: spot
        
        Returns:
            Borrow quota info
        """
        self._private_limiter.acquire()
        
        response = self._session.get_borrow_quota(
            category=category,
            symbol=symbol,
            side=side,
        )
        return self._extract_result(response)
    
    @handle_pybit_errors
    def set_disconnect_cancel_all(self, time_window: int) -> Dict:
        """
        Set Disconnect Cancel Protocol (DCP) for options.
        
        If no private stream packet is received within the time_window,
        all option orders will be cancelled.
        
        Args:
            time_window: Time window in seconds [10, 300]
        
        Returns:
            Result dict
        """
        self._private_limiter.acquire()
        
        self.logger.info(f"Setting DCP time window to {time_window}s")
        
        response = self._session.set_dcp(timeWindow=time_window)
        return self._extract_result(response)
    
    # ==================== Generic Escape Hatch ====================
    
    def call_account_endpoint(self, method: str, **kwargs) -> Any:
        """
        Generic escape hatch for account endpoints.
        
        Calls any method on the pybit session that starts with account-related
        patterns. Useful for accessing new endpoints not yet wrapped.
        
        Args:
            method: Method name on pybit HTTP session (e.g., "get_wallet_balance")
            **kwargs: Arguments to pass to the method
        
        Returns:
            Extracted result from pybit response
        
        Example:
            result = client.call_account_endpoint("get_wallet_balance", accountType="UNIFIED")
        """
        self._private_limiter.acquire()
        
        func = getattr(self._session, method, None)
        if func is None:
            raise ValueError(f"Method '{method}' not found on pybit session")
        
        response = func(**kwargs)
        return self._extract_result(response)
    
    def call_trade_endpoint(self, method: str, **kwargs) -> Any:
        """
        Generic escape hatch for trade endpoints.
        
        Args:
            method: Method name on pybit HTTP session
            **kwargs: Arguments to pass to the method
        
        Returns:
            Extracted result from pybit response
        
        Example:
            result = client.call_trade_endpoint("place_order", category="linear", ...)
        """
        self._order_limiter.acquire()
        
        func = getattr(self._session, method, None)
        if func is None:
            raise ValueError(f"Method '{method}' not found on pybit session")
        
        response = func(**kwargs)
        return self._extract_result(response)
    
    def call_position_endpoint(self, method: str, **kwargs) -> Any:
        """
        Generic escape hatch for position endpoints.
        
        Args:
            method: Method name on pybit HTTP session
            **kwargs: Arguments to pass to the method
        
        Returns:
            Extracted result from pybit response
        
        Example:
            result = client.call_position_endpoint("get_positions", category="linear")
        """
        self._private_limiter.acquire()
        
        func = getattr(self._session, method, None)
        if func is None:
            raise ValueError(f"Method '{method}' not found on pybit session")
        
        response = func(**kwargs)
        return self._extract_result(response)
    
    def call_market_endpoint(self, method: str, **kwargs) -> Any:
        """
        Generic escape hatch for market (public) endpoints.
        
        Args:
            method: Method name on pybit HTTP session
            **kwargs: Arguments to pass to the method
        
        Returns:
            Extracted result from pybit response
        
        Example:
            result = client.call_market_endpoint("get_tickers", category="linear")
        """
        self._public_limiter.acquire()
        
        func = getattr(self._session, method, None)
        if func is None:
            raise ValueError(f"Method '{method}' not found on pybit session")
        
        response = func(**kwargs)
        return self._extract_result(response)
    
    @property
    def session(self) -> HTTP:
        """
        Direct access to underlying pybit HTTP session.
        
        Use this for any pybit methods not wrapped by this client.
        
        Example:
            client.session.get_insurance()
            client.session.get_public_trade_history(category="linear", symbol="BTCUSDT")
        """
        return self._session


# ==================== WebSocket Cleanup Helper ====================

_ws_excepthook_installed = False

def _install_ws_cleanup_hook():
    """
    Install a threading excepthook to suppress WebSocket cleanup errors.
    
    pybit's WebSocket creates background ping threads that may try to send
    after the connection is closed during shutdown. This hook suppresses
    the "Connection is already closed" errors that would otherwise flood stderr.
    """
    import threading
    import sys
    
    global _ws_excepthook_installed
    if _ws_excepthook_installed:
        return
    
    # Store original hook
    original_hook = threading.excepthook
    
    def ws_cleanup_excepthook(args):
        """Custom excepthook that suppresses WebSocket cleanup errors."""
        # Check if this is a WebSocket cleanup error we want to suppress
        exc_type = args.exc_type
        exc_value = args.exc_value
        
        # Suppress WebSocketConnectionClosedException from pybit ping threads
        if exc_type.__name__ == "WebSocketConnectionClosedException":
            # Silently ignore - this is expected during cleanup
            return
        
        # Suppress any error containing "Connection is already closed"
        if exc_value and "Connection is already closed" in str(exc_value):
            return
        
        # For all other exceptions, use the original hook
        if original_hook:
            original_hook(args)
        else:
            # Default behavior if no original hook
            sys.excepthook(exc_type, exc_value, args.exc_traceback)
    
    threading.excepthook = ws_cleanup_excepthook
    _ws_excepthook_installed = True


# Install the hook when this module is imported
_install_ws_cleanup_hook()
