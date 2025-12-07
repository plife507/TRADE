"""
Bybit API client using official pybit library.

Wraps the official pybit library (https://github.com/bybit-exchange/pybit)
providing a clean interface with:
- Unified HTTP and WebSocket access
- DataFrame conversion for market data  
- Integration with trading bot logger
- Custom rate limiting layer

This module delegates to helper modules:
- bybit_market: Market data (klines, ticker, funding, OI, etc.)
- bybit_account: Account operations (balance, positions, UTA methods)
- bybit_trading: Order execution, batch ops, position management
- bybit_websocket: WebSocket connections and subscriptions

Reference: C:/CODE/AI/TRADE/reference/exchanges/pybit/
"""

import time
from typing import Optional, Dict, List, Any, Callable, Union
from functools import wraps

import pandas as pd

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
from ..utils.time_range import TimeRange


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
        log_requests: bool = False,
    ):
        """
        Initialize Bybit client with official pybit library.
        
        Args:
            api_key: API key for authentication
            api_secret: API secret for authentication
            use_demo: True for DEMO (fake money), False for LIVE (real money)
            recv_window: Request timeout window in milliseconds
            log_requests: Whether to log HTTP requests
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.use_demo = use_demo
        self.recv_window = recv_window
        
        self._time_offset_ms = 0
        
        self._session = HTTP(
            testnet=False,
            demo=use_demo,
            api_key=api_key,
            api_secret=api_secret,
            recv_window=recv_window,
            log_requests=log_requests,
            return_response_headers=True,
        )
        
        self.logger = get_logger()
        
        self._sync_server_time()
        
        # Only two environments: DEMO and LIVE
        if use_demo:
            self.base_url = "https://api-demo.bybit.com"
        else:
            self.base_url = "https://api.bybit.com"
        
        mode_str = "DEMO" if use_demo else "LIVE"
        auth_status = "authenticated" if api_key else "public-only"
        self.logger.info(
            f"BybitClient initialized: mode={mode_str}, "
            f"base_url={self.base_url}, auth={auth_status}"
        )
        
        self._limiters = create_bybit_limiters()
        self._public_limiter = self._limiters.get_limiter("public")
        self._private_limiter = self._limiters.get_limiter("private")
        self._order_limiter = self._limiters.get_limiter("orders")
        
        self._rate_limit_status = {
            "remaining": None,
            "limit": None,
            "reset_timestamp": None,
        }
        
        self._ws_public: Optional[WebSocket] = None
        self._ws_private: Optional[WebSocket] = None
    
    def _sync_server_time(self):
        """Sync local time with Bybit server to avoid timestamp errors."""
        try:
            before = int(time.time() * 1000)
            server_time = self._session.get_server_time()
            after = int(time.time() * 1000)
            
            result = server_time
            if isinstance(server_time, tuple):
                result = server_time[0].get("result", {})
            elif isinstance(server_time, dict):
                result = server_time.get("result", {})
            
            server_time_ms = int(result.get("timeNano", "0")) // 1_000_000
            if server_time_ms == 0:
                server_time_ms = int(result.get("timeSecond", "0")) * 1000
            
            local_time_ms = (before + after) // 2
            self._time_offset_ms = server_time_ms - local_time_ms
            
            if abs(self._time_offset_ms) > 5000:
                self.logger.warning(
                    f"Large time offset detected: {self._time_offset_ms}ms. "
                    f"Consider syncing your system clock."
                )
            else:
                self.logger.debug(f"Server time offset: {self._time_offset_ms}ms")
                
        except Exception as e:
            self.logger.warning(f"Failed to sync server time: {e}. Using local time.")
            self._time_offset_ms = 0
    
    def _update_rate_limit_status(self, response_headers):
        """Update rate limit tracking from response headers."""
        if response_headers:
            self._rate_limit_status["remaining"] = response_headers.get("X-Bapi-Limit-Remaining")
            self._rate_limit_status["limit"] = response_headers.get("X-Bapi-Limit")
            self._rate_limit_status["reset_timestamp"] = response_headers.get("X-Bapi-Limit-Reset-Timestamp")
    
    def _extract_result(self, response) -> dict:
        """Extract result from pybit response tuple or dict.
        
        When return_response_headers=True, pybit returns:
        - 3-tuple: (data_dict, timedelta_duration, headers_dict)
        The middle element (timedelta) is the request duration - ignore it.
        """
        if isinstance(response, tuple):
            data = response[0]
            # pybit returns (data, timedelta, headers) when return_response_headers=True
            # The timedelta is the request duration - we want the headers dict (index 2)
            if len(response) >= 3:
                headers = response[2]  # Headers are at index 2, not 1
            elif len(response) == 2 and isinstance(response[1], dict):
                headers = response[1]  # Fallback for 2-tuple case
            else:
                headers = None
            self._update_rate_limit_status(headers)
            return data.get("result", {})
        elif isinstance(response, dict):
            return response.get("result", {})
        return {}
    
    # ==================== Market Data (delegated) ====================
    
    @handle_pybit_errors
    def get_klines(self, symbol: str, interval: str = "15", limit: int = 200, 
                   start: int = None, end: int = None, category: str = "linear") -> pd.DataFrame:
        from . import bybit_market as mkt
        return mkt.get_klines(self, symbol, interval, limit, start, end, category)
    
    @handle_pybit_errors
    def get_ticker(self, symbol: str = None, category: str = "linear") -> Dict[str, Any]:
        from . import bybit_market as mkt
        return mkt.get_ticker(self, symbol, category)
    
    @handle_pybit_errors
    def get_funding_rate(self, symbol: str, limit: int = 1, category: str = "linear",
                         start_time: Optional[int] = None, end_time: Optional[int] = None) -> List[Dict]:
        from . import bybit_market as mkt
        return mkt.get_funding_rate(self, symbol, limit, category, start_time, end_time)
    
    @handle_pybit_errors
    def get_open_interest(self, symbol: str, interval: str = "5min", limit: int = 1,
                          category: str = "linear", start_time: Optional[int] = None,
                          end_time: Optional[int] = None) -> List[Dict]:
        from . import bybit_market as mkt
        return mkt.get_open_interest(self, symbol, interval, limit, category, start_time, end_time)
    
    @handle_pybit_errors
    def get_orderbook(self, symbol: str, limit: int = 25, category: str = "linear") -> Dict:
        from . import bybit_market as mkt
        return mkt.get_orderbook(self, symbol, limit, category)
    
    @handle_pybit_errors
    def get_instruments(self, symbol: str = None, category: str = "linear") -> List[Dict]:
        from . import bybit_market as mkt
        return mkt.get_instruments(self, symbol, category)
    
    def get_instrument_info(self, symbol: str, category: str = "linear") -> Dict:
        from . import bybit_market as mkt
        return mkt.get_instrument_info(self, symbol, category)
    
    @handle_pybit_errors
    def get_server_time(self) -> Dict:
        from . import bybit_market as mkt
        return mkt.get_server_time(self)
    
    @handle_pybit_errors
    def get_risk_limit(self, symbol: str = None, category: str = "linear") -> List[Dict]:
        from . import bybit_market as mkt
        return mkt.get_risk_limit(self, symbol, category)
    
    # ==================== Account (delegated) ====================
    
    @handle_pybit_errors
    def get_balance(self, account_type: str = "UNIFIED") -> Dict:
        from . import bybit_account as acct
        return acct.get_balance(self, account_type)
    
    @handle_pybit_errors
    def get_positions(self, symbol: str = None, settle_coin: str = "USDT", category: str = "linear") -> List[Dict]:
        from . import bybit_account as acct
        return acct.get_positions(self, symbol, settle_coin, category)
    
    @handle_pybit_errors
    def get_account_info(self) -> Dict:
        from . import bybit_account as acct
        return acct.get_account_info(self)
    
    @handle_pybit_errors
    def get_fee_rates(self, symbol: str = None, category: str = "linear") -> Dict:
        from . import bybit_account as acct
        return acct.get_fee_rates(self, symbol, category)
    
    # UTA Extended
    @handle_pybit_errors
    def get_transaction_log(self, time_range: TimeRange, account_type: str = "UNIFIED",
                            category: str = None, currency: str = None, base_coin: str = None,
                            log_type: str = None, limit: int = 50, cursor: str = None) -> Dict:
        from . import bybit_account as acct
        return acct.get_transaction_log(self, time_range, account_type, category, currency, base_coin, log_type, limit, cursor)
    
    @handle_pybit_errors
    def get_collateral_info(self, currency: str = None) -> List[Dict]:
        from . import bybit_account as acct
        return acct.get_collateral_info(self, currency)
    
    @handle_pybit_errors
    def set_collateral_coin(self, coin: str, switch: str) -> Dict:
        from . import bybit_account as acct
        return acct.set_collateral_coin(self, coin, switch)
    
    @handle_pybit_errors
    def batch_set_collateral_coin(self, coins: List[Dict[str, str]]) -> Dict:
        from . import bybit_account as acct
        return acct.batch_set_collateral_coin(self, coins)
    
    @handle_pybit_errors
    def get_borrow_history(self, time_range: TimeRange, currency: str = None,
                           limit: int = 50, cursor: str = None) -> Dict:
        from . import bybit_account as acct
        return acct.get_borrow_history(self, time_range, currency, limit, cursor)
    
    @handle_pybit_errors
    def repay_liability(self, coin: str = None) -> Dict:
        from . import bybit_account as acct
        return acct.repay_liability(self, coin)
    
    @handle_pybit_errors
    def get_coin_greeks(self, base_coin: str = None) -> List[Dict]:
        from . import bybit_account as acct
        return acct.get_coin_greeks(self, base_coin)
    
    @handle_pybit_errors
    def set_account_margin_mode(self, margin_mode: str) -> Dict:
        from . import bybit_account as acct
        return acct.set_account_margin_mode(self, margin_mode)
    
    @handle_pybit_errors
    def upgrade_to_unified_account(self) -> Dict:
        from . import bybit_account as acct
        return acct.upgrade_to_unified_account(self)
    
    @handle_pybit_errors
    def get_transferable_amount(self, coin: str) -> Dict:
        from . import bybit_account as acct
        return acct.get_transferable_amount(self, coin)
    
    @handle_pybit_errors
    def get_mmp_state(self, base_coin: str) -> Dict:
        from . import bybit_account as acct
        return acct.get_mmp_state(self, base_coin)
    
    @handle_pybit_errors
    def set_mmp(self, base_coin: str, window: int, frozen_period: int,
                qty_limit: str, delta_limit: str) -> Dict:
        from . import bybit_account as acct
        return acct.set_mmp(self, base_coin, window, frozen_period, qty_limit, delta_limit)
    
    @handle_pybit_errors
    def reset_mmp(self, base_coin: str) -> Dict:
        from . import bybit_account as acct
        return acct.reset_mmp(self, base_coin)
    
    @handle_pybit_errors
    def get_borrow_quota(self, category: str, symbol: str, side: str) -> Dict:
        from . import bybit_account as acct
        return acct.get_borrow_quota(self, category, symbol, side)
    
    # ==================== Trading (delegated) ====================
    
    @handle_pybit_errors
    def create_order(self, symbol: str, side: str, order_type: str, qty: float, **kwargs) -> Dict:
        from . import bybit_trading as trd
        return trd.create_order(self, symbol, side, order_type, qty, **kwargs)
    
    @handle_pybit_errors
    def amend_order(self, symbol: str, order_id: str = None, order_link_id: str = None, **kwargs) -> Dict:
        from . import bybit_trading as trd
        return trd.amend_order(self, symbol, order_id, order_link_id, **kwargs)
    
    @handle_pybit_errors
    def cancel_order(self, symbol: str, order_id: str = None, order_link_id: str = None,
                     category: str = "linear") -> Dict:
        from . import bybit_trading as trd
        return trd.cancel_order(self, symbol, order_id, order_link_id, category)
    
    @handle_pybit_errors
    def cancel_all_orders(self, symbol: str = None, category: str = "linear") -> Dict:
        from . import bybit_trading as trd
        return trd.cancel_all_orders(self, symbol, category)
    
    @handle_pybit_errors
    def get_open_orders(self, symbol: str = None, order_id: str = None, order_link_id: str = None,
                        open_only: int = 0, limit: int = 50, category: str = "linear") -> List[Dict]:
        from . import bybit_trading as trd
        return trd.get_open_orders(self, symbol, order_id, order_link_id, open_only, limit, category)
    
    @handle_pybit_errors
    def get_order_history(self, time_range: TimeRange, symbol: str = None, **kwargs) -> Dict:
        from . import bybit_trading as trd
        return trd.get_order_history(self, time_range, symbol, **kwargs)
    
    @handle_pybit_errors
    def set_leverage(self, symbol: str, leverage: int, category: str = "linear") -> Dict:
        from . import bybit_trading as trd
        return trd.set_leverage(self, symbol, leverage, category)
    
    @handle_pybit_errors
    def create_conditional_order(self, symbol: str, side: str, qty: str, trigger_price: str,
                                  trigger_direction: int, **kwargs) -> Dict:
        from . import bybit_trading as trd
        return trd.create_conditional_order(self, symbol, side, qty, trigger_price, trigger_direction, **kwargs)
    
    @handle_pybit_errors
    def set_trading_stop(self, symbol: str, **kwargs) -> Dict:
        from . import bybit_trading as trd
        return trd.set_trading_stop(self, symbol, **kwargs)
    
    @handle_pybit_errors
    def get_executions(self, time_range: TimeRange, symbol: str = None, **kwargs) -> List[Dict]:
        from . import bybit_trading as trd
        return trd.get_executions(self, time_range, symbol, **kwargs)
    
    @handle_pybit_errors
    def get_closed_pnl(self, time_range: TimeRange, symbol: str = None, **kwargs) -> Dict:
        from . import bybit_trading as trd
        return trd.get_closed_pnl(self, time_range, symbol, **kwargs)
    
    # Batch operations
    @handle_pybit_errors
    def batch_create_orders(self, orders: List[Dict], category: str = "linear") -> Dict:
        from . import bybit_trading as trd
        return trd.batch_create_orders(self, orders, category)
    
    @handle_pybit_errors
    def batch_amend_orders(self, orders: List[Dict], category: str = "linear") -> Dict:
        from . import bybit_trading as trd
        return trd.batch_amend_orders(self, orders, category)
    
    @handle_pybit_errors
    def batch_cancel_orders(self, orders: List[Dict], category: str = "linear") -> Dict:
        from . import bybit_trading as trd
        return trd.batch_cancel_orders(self, orders, category)
    
    # Position management
    @handle_pybit_errors
    def set_risk_limit(self, symbol: str, risk_id: int, position_idx: int = 0,
                       category: str = "linear") -> Dict:
        from . import bybit_trading as trd
        return trd.set_risk_limit(self, symbol, risk_id, position_idx, category)
    
    @handle_pybit_errors
    def set_tp_sl_mode(self, symbol: str, tp_sl_mode: str, category: str = "linear") -> Dict:
        from . import bybit_trading as trd
        return trd.set_tp_sl_mode(self, symbol, tp_sl_mode, category)
    
    @handle_pybit_errors
    def set_auto_add_margin(self, symbol: str, auto_add_margin: int, position_idx: int = 0,
                            category: str = "linear") -> Dict:
        from . import bybit_trading as trd
        return trd.set_auto_add_margin(self, symbol, auto_add_margin, position_idx, category)
    
    @handle_pybit_errors
    def modify_position_margin(self, symbol: str, margin: str, position_idx: int = 0,
                               category: str = "linear") -> Dict:
        from . import bybit_trading as trd
        return trd.modify_position_margin(self, symbol, margin, position_idx, category)
    
    @handle_pybit_errors
    def switch_cross_isolated_margin(self, symbol: str, trade_mode: int, buy_leverage: str,
                                      sell_leverage: str, category: str = "linear") -> Dict:
        from . import bybit_trading as trd
        return trd.switch_cross_isolated_margin(self, symbol, trade_mode, buy_leverage, sell_leverage, category)
    
    @handle_pybit_errors
    def switch_position_mode_v5(self, mode: int, symbol: str = None, coin: str = None,
                                 category: str = "linear") -> Dict:
        from . import bybit_trading as trd
        return trd.switch_position_mode_v5(self, mode, symbol, coin, category)
    
    @handle_pybit_errors
    def set_disconnect_cancel_all(self, time_window: int) -> Dict:
        from . import bybit_trading as trd
        return trd.set_disconnect_cancel_all(self, time_window)
    
    # ==================== WebSocket (delegated) ====================
    
    def connect_public_ws(self, channel_type: str = "linear", use_live_for_market_data: bool = False) -> WebSocket:
        from . import bybit_websocket as ws
        return ws.connect_public_ws(self, channel_type, use_live_for_market_data)
    
    def connect_private_ws(self) -> WebSocket:
        from . import bybit_websocket as ws
        return ws.connect_private_ws(self)
    
    def subscribe_ticker(self, symbol: Union[str, List[str]], callback: Callable):
        from . import bybit_websocket as ws
        ws.subscribe_ticker(self, symbol, callback)
    
    def subscribe_orderbook(self, symbol: Union[str, List[str]], callback: Callable, depth: int = 50):
        from . import bybit_websocket as ws
        ws.subscribe_orderbook(self, symbol, callback, depth)
    
    def subscribe_trades(self, symbol: Union[str, List[str]], callback: Callable):
        from . import bybit_websocket as ws
        ws.subscribe_trades(self, symbol, callback)
    
    def subscribe_klines(self, symbol: Union[str, List[str]], interval: int, callback: Callable):
        from . import bybit_websocket as ws
        ws.subscribe_klines(self, symbol, interval, callback)
    
    def subscribe_positions(self, callback: Callable):
        from . import bybit_websocket as ws
        ws.subscribe_positions(self, callback)
    
    def subscribe_orders(self, callback: Callable):
        from . import bybit_websocket as ws
        ws.subscribe_orders(self, callback)
    
    def subscribe_executions(self, callback: Callable):
        from . import bybit_websocket as ws
        ws.subscribe_executions(self, callback)
    
    def subscribe_wallet(self, callback: Callable):
        from . import bybit_websocket as ws
        ws.subscribe_wallet(self, callback)
    
    def close_websockets(self, suppress_errors: bool = True, wait_for_threads: float = 0.5):
        from . import bybit_websocket as ws
        ws.close_websockets(self, suppress_errors, wait_for_threads)
    
    # ==================== Utility Methods ====================
    
    def get_time_offset(self) -> int:
        """Get calculated time offset from server in ms."""
        return self._time_offset_ms
    
    def get_rate_limit_status(self) -> Dict:
        """Get current rate limit status from last response."""
        return self._rate_limit_status.copy()
    
    @handle_pybit_errors
    def test_connection(self) -> Dict[str, Any]:
        """Test exchange connectivity and authentication."""
        result = {
            "connected": False,
            "server_time": None,
            "public_ok": False,
            "private_ok": None,
            "time_offset_ms": self._time_offset_ms,
        }
        
        try:
            server_time = self.get_server_time()
            result["connected"] = True
            result["server_time"] = server_time
            result["public_ok"] = True
        except Exception as e:
            result["error"] = str(e)
            return result
        
        if self.api_key:
            try:
                self.get_balance()
                result["private_ok"] = True
            except Exception as e:
                result["private_ok"] = False
                result["private_error"] = str(e)
        else:
            result["private_ok"] = None
        
        return result
    
    @property
    def session(self) -> HTTP:
        """Direct access to pybit HTTP session for advanced usage."""
        return self._session
    
    # Legacy method aliases for backwards compatibility
    def call_account_endpoint(self, method: str, **kwargs) -> Any:
        """Call an account endpoint by method name."""
        return getattr(self._session, method)(**kwargs)
    
    def call_trade_endpoint(self, method: str, **kwargs) -> Any:
        """Call a trade endpoint by method name."""
        return getattr(self._session, method)(**kwargs)
    
    def call_position_endpoint(self, method: str, **kwargs) -> Any:
        """Call a position endpoint by method name."""
        return getattr(self._session, method)(**kwargs)
    
    def call_market_endpoint(self, method: str, **kwargs) -> Any:
        """Call a market endpoint by method name."""
        return getattr(self._session, method)(**kwargs)
