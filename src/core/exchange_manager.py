"""
Unified exchange interface.

Provides a consistent API for trading operations across exchanges.
Currently supports Bybit only; designed for easy extension to HyperLiquid.

This module delegates to helper modules:
- exchange_instruments: Instrument info, pricing, quantity calculations
- exchange_websocket: WebSocket integration and cleanup callbacks
- exchange_orders_market: Market order execution
- exchange_orders_limit: Limit order execution
- exchange_orders_stop: Stop/conditional orders
- exchange_orders_manage: Order management, batch ops, close positions
- exchange_positions: Position queries and management
"""

from typing import Any
from dataclasses import dataclass
from enum import Enum

import threading

from ..exchanges.bybit_client import BybitClient
from ..config.config import get_config, TradingMode
from ..utils.logger import get_logger
from ..utils.helpers import safe_float
from ..utils.time_range import TimeRange


# ==================== Type Definitions ====================

class TimeInForce(str, Enum):
    """Order time-in-force options."""
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"
    POST_ONLY = "PostOnly"


class TriggerBy(str, Enum):
    """Price type for trigger orders."""
    LAST_PRICE = "LastPrice"
    INDEX_PRICE = "IndexPrice"
    MARK_PRICE = "MarkPrice"


class TriggerDirection(int, Enum):
    """Direction for conditional order trigger."""
    RISE = 1
    FALL = 2


# ==================== Data Classes ====================

@dataclass
class Position:
    """Normalized position data."""
    symbol: str
    exchange: str
    position_type: str
    side: str
    size: float
    size_usdt: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_percent: float
    leverage: float
    margin_mode: str
    liquidation_price: float | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    trailing_stop: float | None = None
    adl_rank: int | None = None
    is_reduce_only: bool = False
    cumulative_pnl: float | None = None
    
    @property
    def is_open(self) -> bool:
        return abs(self.size) > 0


@dataclass
class Order:
    """Normalized open order data."""
    order_id: str
    order_link_id: str | None
    symbol: str
    side: str
    order_type: str
    price: float | None
    qty: float
    filled_qty: float
    remaining_qty: float
    status: str
    time_in_force: str
    reduce_only: bool
    trigger_price: float | None = None
    trigger_by: str | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    created_time: str | None = None
    updated_time: str | None = None
    
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
    order_id: str | None = None
    order_link_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    order_type: str | None = None
    qty: float | None = None
    price: float | None = None
    trigger_price: float | None = None
    time_in_force: str | None = None
    take_profit: float | None = None
    stop_loss: float | None = None
    reduce_only: bool = False
    error: str | None = None
    raw_response: dict | None = None


# ==================== Exchange Manager ====================

class ExchangeManager:
    """
    Unified exchange manager (thread-safe singleton).

    Provides high-level trading operations with:
    - Automatic position sizing (USD to quantity)
    - Minimum size validation
    - Leverage management
    - Error handling

    All methods delegate to helper modules for implementation.
    """

    _instance: 'ExchangeManager | None' = None
    _singleton_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize exchange manager."""
        if self._initialized:
            return
        self.config = get_config()
        self.logger = get_logger()
        
        # === STRICT MODE/API MAPPING ASSERTION ===
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
        api_key, api_secret = self.config.bybit.get_credentials()
        
        self.bybit = BybitClient(
            api_key=api_key,
            api_secret=api_secret,
            use_demo=self.use_demo,
        )
        
        mode = "DEMO (fake money)" if self.use_demo else "LIVE (REAL MONEY!)"
        key_status = "authenticated" if api_key else "NO KEY"
        
        if self.use_demo:
            key_source = "BYBIT_DEMO_API_KEY" if self.config.bybit.demo_api_key else "MISSING"
        else:
            key_source = "BYBIT_LIVE_API_KEY" if self.config.bybit.live_api_key else "MISSING"
        
        self.logger.info(
            f"ExchangeManager initialized: API={mode}, base_url={self.bybit.base_url}, "
            f"trading_mode={trading_mode}, auth={key_status}, key_source={key_source}"
        )
        
        self._instruments: dict[str, dict] = {}
        self._previous_positions: dict[str, bool] = {}
        self._position_tracking_lock = threading.Lock()  # Protects _previous_positions

        # Setup WebSocket cleanup
        from . import exchange_websocket as ws
        ws.setup_websocket_cleanup(self)

        self._initialized = True

        # Verify one-way position mode at startup (fail-closed)
        from . import exchange_positions
        if not exchange_positions.switch_to_one_way_mode(self):
            raise ValueError(
                "Failed to verify one-way position mode. "
                "Check account settings on Bybit."
            )

        # Validate fee rates against exchange
        try:
            fee_info = self.bybit.get_fee_rates()
            if fee_info:
                from ..config.constants import DEFAULTS
                for item in fee_info:
                    taker = float(item.get("takerFeeRate", 0))
                    maker = float(item.get("makerFeeRate", 0))
                    config_taker = DEFAULTS.fees.taker_rate
                    config_maker = DEFAULTS.fees.maker_rate
                    if abs(taker - config_taker) > 0.00001 or abs(maker - config_maker) > 0.00001:
                        self.logger.warning(
                            f"Fee rate mismatch! Exchange: taker={taker:.6f} maker={maker:.6f}, "
                            f"Config: taker={config_taker:.6f} maker={config_maker:.6f}"
                        )
                    break  # Only check first result
                self._actual_fee_rates = fee_info
        except Exception as e:
            self.logger.debug(f"Could not query fee rates (non-fatal): {e}")
    
    def _validate_trading_operation(self) -> None:
        """SAFETY GUARD RAIL: Validate trading mode consistency."""
        config = get_config()
        
        if config.trading.mode == TradingMode.REAL and config.bybit.use_demo:
            raise ValueError(
                "INVALID CONFIGURATION: TRADING_MODE=real but BYBIT_USE_DEMO=true."
            )
        
        if config.trading.mode == TradingMode.PAPER and not config.bybit.use_demo:
            raise ValueError(
                "INVALID CONFIGURATION: TRADING_MODE=paper but BYBIT_USE_DEMO=false."
            )
    
    # ==================== Market Data ====================
    
    def get_price(self, symbol: str) -> float:
        """Get current market price."""
        ticker = self.bybit.get_ticker(symbol)
        return float(ticker.get("lastPrice", 0))
    
    def get_bid_ask(self, symbol: str) -> tuple[float, float]:
        """Get current bid and ask prices."""
        ticker = self.bybit.get_ticker(symbol)
        return (float(ticker.get("bid1Price", 0)), float(ticker.get("ask1Price", 0)))
    
    # ==================== Account ====================
    
    def get_balance(self) -> dict[str, float]:
        """Get account balance."""
        balance = self.bybit.get_balance()
        total = available = 0.0
        
        for coin in balance.get("coin", []):
            if coin.get("coin") == "USDT":
                total = safe_float(coin.get("walletBalance", 0))
                available = safe_float(coin.get("availableToWithdraw")) or \
                           safe_float(coin.get("availableToBorrow")) or \
                           safe_float(coin.get("equity")) or total
                break
        
        return {"total": total, "available": available, "used": total - available, "currency": "USDT"}
    
    def get_account_value(self) -> float:
        """Get total account value in USD."""
        return self.get_balance().get("total", 0.0)
    
    # ==================== Positions (delegated) ====================
    
    def get_position(self, symbol: str) -> Position | None:
        from . import exchange_positions as pos
        return pos.get_position(self, symbol)

    def get_all_positions(self) -> list[Position]:
        from . import exchange_positions as pos
        return pos.get_all_positions(self)
    
    def get_total_exposure(self) -> float:
        from . import exchange_positions as pos
        return pos.get_total_exposure(self)
    
    def set_position_tpsl(self, symbol: str, take_profit: float | None = None, stop_loss: float | None = None, tpsl_mode: str = "Full") -> bool:
        from . import exchange_positions as pos
        return pos.set_position_tpsl(self, symbol, take_profit, stop_loss, tpsl_mode)
    
    def set_trailing_stop(self, symbol: str, trailing_stop: float, active_price: float | None = None) -> bool:
        from . import exchange_positions as pos
        return pos.set_trailing_stop(self, symbol, trailing_stop, active_price)
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        from . import exchange_positions as pos
        return pos.set_leverage(self, symbol, leverage)
    
    def set_margin_mode(self, symbol: str, mode: str, leverage: float = 1.0) -> bool:
        from . import exchange_positions as pos
        return pos.set_margin_mode(self, symbol, mode, leverage=leverage)
    
    def set_position_mode(self, mode: str = "MergedSingle") -> bool:
        from . import exchange_positions as pos
        return pos.set_position_mode(self, mode)
    
    def add_margin(self, symbol: str, amount: float) -> bool:
        from . import exchange_positions as pos
        return pos.add_margin(self, symbol, amount)
    
    # ==================== Market Orders (delegated) ====================
    
    def market_buy(self, symbol: str, usd_amount: float) -> OrderResult:
        from . import exchange_orders_market as mkt
        return mkt.market_buy(self, symbol, usd_amount)
    
    def market_sell(self, symbol: str, usd_amount: float) -> OrderResult:
        from . import exchange_orders_market as mkt
        return mkt.market_sell(self, symbol, usd_amount)
    
    def market_buy_with_tpsl(self, symbol: str, usd_amount: float, take_profit: float | None = None, stop_loss: float | None = None, tpsl_mode: str = "Full") -> OrderResult:
        from . import exchange_orders_market as mkt
        return mkt.market_buy_with_tpsl(self, symbol, usd_amount, take_profit, stop_loss, tpsl_mode)
    
    def market_sell_with_tpsl(self, symbol: str, usd_amount: float, take_profit: float | None = None, stop_loss: float | None = None, tpsl_mode: str = "Full") -> OrderResult:
        from . import exchange_orders_market as mkt
        return mkt.market_sell_with_tpsl(self, symbol, usd_amount, take_profit, stop_loss, tpsl_mode)
    
    # ==================== Limit Orders (delegated) ====================
    
    def limit_buy(self, symbol: str, usd_amount: float, price: float, time_in_force: str = "GTC", reduce_only: bool = False, order_link_id: str | None = None) -> OrderResult:
        from . import exchange_orders_limit as lmt
        return lmt.limit_buy(self, symbol, usd_amount, price, time_in_force, reduce_only, order_link_id)
    
    def limit_sell(self, symbol: str, usd_amount: float, price: float, time_in_force: str = "GTC", reduce_only: bool = False, order_link_id: str | None = None) -> OrderResult:
        from . import exchange_orders_limit as lmt
        return lmt.limit_sell(self, symbol, usd_amount, price, time_in_force, reduce_only, order_link_id)
    
    def limit_buy_with_tpsl(self, symbol: str, usd_amount: float, price: float, take_profit: float | None = None, stop_loss: float | None = None, time_in_force: str = "GTC", tpsl_mode: str = "Full", tp_order_type: str = "Market", sl_order_type: str = "Market", order_link_id: str | None = None) -> OrderResult:
        from . import exchange_orders_limit as lmt
        return lmt.limit_buy_with_tpsl(self, symbol, usd_amount, price, take_profit, stop_loss, time_in_force, tpsl_mode, tp_order_type, sl_order_type, order_link_id)
    
    def limit_sell_with_tpsl(self, symbol: str, usd_amount: float, price: float, take_profit: float | None = None, stop_loss: float | None = None, time_in_force: str = "GTC", tpsl_mode: str = "Full", tp_order_type: str = "Market", sl_order_type: str = "Market", order_link_id: str | None = None) -> OrderResult:
        from . import exchange_orders_limit as lmt
        return lmt.limit_sell_with_tpsl(self, symbol, usd_amount, price, take_profit, stop_loss, time_in_force, tpsl_mode, tp_order_type, sl_order_type, order_link_id)
    
    # ==================== Stop Orders (delegated) ====================
    
    def stop_market_buy(self, symbol: str, usd_amount: float, trigger_price: float, trigger_direction: int = 1, trigger_by: str = "LastPrice", reduce_only: bool = False, order_link_id: str | None = None) -> OrderResult:
        from . import exchange_orders_stop as stop
        return stop.stop_market_buy(self, symbol, usd_amount, trigger_price, trigger_direction, trigger_by, reduce_only, order_link_id)
    
    def stop_market_sell(self, symbol: str, usd_amount: float, trigger_price: float, trigger_direction: int = 2, trigger_by: str = "LastPrice", reduce_only: bool = False, order_link_id: str | None = None) -> OrderResult:
        from . import exchange_orders_stop as stop
        return stop.stop_market_sell(self, symbol, usd_amount, trigger_price, trigger_direction, trigger_by, reduce_only, order_link_id)
    
    def stop_limit_buy(self, symbol: str, usd_amount: float, trigger_price: float, limit_price: float, trigger_direction: int = 1, trigger_by: str = "LastPrice", time_in_force: str = "GTC", reduce_only: bool = False, order_link_id: str | None = None) -> OrderResult:
        from . import exchange_orders_stop as stop
        return stop.stop_limit_buy(self, symbol, usd_amount, trigger_price, limit_price, trigger_direction, trigger_by, time_in_force, reduce_only, order_link_id)
    
    def stop_limit_sell(self, symbol: str, usd_amount: float, trigger_price: float, limit_price: float, trigger_direction: int = 2, trigger_by: str = "LastPrice", time_in_force: str = "GTC", reduce_only: bool = False, order_link_id: str | None = None) -> OrderResult:
        from . import exchange_orders_stop as stop
        return stop.stop_limit_sell(self, symbol, usd_amount, trigger_price, limit_price, trigger_direction, trigger_by, time_in_force, reduce_only, order_link_id)
    
    def create_conditional_order(self, symbol: str, side: str, qty: float, trigger_price: float, trigger_direction: TriggerDirection | None = None, order_type: str = "Market", price: float | None = None, reduce_only: bool = True, order_link_id: str | None = None) -> OrderResult:
        from . import exchange_orders_stop as stop
        return stop.create_conditional_order(self, symbol, side, qty, trigger_price, trigger_direction, order_type, price, reduce_only, order_link_id)
    
    def open_position_with_rr(self, symbol: str, side: str, margin_usd: float, leverage: int, stop_loss_roi_pct: float, take_profits: list[dict[str, float]]) -> dict[str, Any]:
        from . import exchange_orders_stop as stop
        return stop.open_position_with_rr(self, symbol, side, margin_usd, leverage, stop_loss_roi_pct, take_profits)
    
    # ==================== Order Management (delegated) ====================
    
    def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        from . import exchange_orders_manage as mgmt
        return mgmt.get_open_orders(self, symbol)
    
    def cancel_order(self, symbol: str, order_id: str | None = None, order_link_id: str | None = None) -> bool:
        from . import exchange_orders_manage as mgmt
        return mgmt.cancel_order(self, symbol, order_id, order_link_id)
    
    def cancel_all_orders(self, symbol: str | None = None) -> bool:
        from . import exchange_orders_manage as mgmt
        return mgmt.cancel_all_orders(self, symbol)
    
    def amend_order(self, symbol: str, order_id: str | None = None, order_link_id: str | None = None, qty: float | None = None, price: float | None = None, take_profit: float | None = None, stop_loss: float | None = None, trigger_price: float | None = None) -> bool:
        from . import exchange_orders_manage as mgmt
        return mgmt.amend_order(self, symbol, order_id, order_link_id, qty, price, take_profit, stop_loss, trigger_price)
    
    def close_position(self, symbol: str, cancel_conditional_orders: bool = True) -> OrderResult:
        from . import exchange_orders_manage as mgmt
        return mgmt.close_position(self, symbol, cancel_conditional_orders)
    
    def close_all_positions(self) -> list[OrderResult]:
        from . import exchange_orders_manage as mgmt
        return mgmt.close_all_positions(self)
    
    # ==================== Order History (delegated) ====================
    
    def get_order_history(self, time_range: TimeRange, symbol: str | None = None, limit: int = 50) -> list[dict]:
        from . import exchange_orders_manage as mgmt
        return mgmt.get_order_history(self, time_range, symbol, limit)
    
    def get_executions(self, time_range: TimeRange, symbol: str | None = None, limit: int = 50) -> list[dict]:
        from . import exchange_orders_manage as mgmt
        return mgmt.get_executions(self, time_range, symbol, limit)
    
    def get_closed_pnl(self, time_range: TimeRange, symbol: str | None = None, limit: int = 50) -> list[dict]:
        from . import exchange_orders_manage as mgmt
        return mgmt.get_closed_pnl(self, time_range, symbol, limit)
    
    # ==================== Batch Operations (delegated) ====================
    
    def batch_market_orders(self, orders: list[dict[str, Any]]) -> list[OrderResult]:
        from . import exchange_orders_manage as mgmt
        return mgmt.batch_market_orders(self, orders)
    
    def batch_limit_orders(self, orders: list[dict[str, Any]]) -> list[OrderResult]:
        from . import exchange_orders_manage as mgmt
        return mgmt.batch_limit_orders(self, orders)
    
    def batch_cancel_orders(self, orders: list[dict[str, str]]) -> list[bool]:
        from . import exchange_orders_manage as mgmt
        return mgmt.batch_cancel_orders(self, orders)
    
    def batch_amend_orders(self, orders: list[dict[str, Any]]) -> list[bool]:
        from . import exchange_orders_manage as mgmt
        return mgmt.batch_amend_orders(self, orders)
    
    # ==================== Position Configuration (delegated) ====================
    
    def cancel_position_conditional_orders(self, symbol: str, position_side: str, require_bot_id: bool = True) -> list[str]:
        from . import exchange_positions as pos
        return pos.cancel_position_conditional_orders(self, symbol, position_side, require_bot_id)
    
    def reconcile_orphaned_orders(self, symbol: str | None = None) -> dict[str, list[str]]:
        from . import exchange_positions as pos
        return pos.reconcile_orphaned_orders(self, symbol)
    
    def set_risk_limit_by_id(self, symbol: str, risk_id: int, position_idx: int = 0) -> bool:
        from . import exchange_positions as pos
        return pos.set_risk_limit_by_id(self, symbol, risk_id, position_idx)
    
    def get_risk_limits(self, symbol: str | None = None) -> list[dict]:
        from . import exchange_positions as pos
        return pos.get_risk_limits(self, symbol)
    
    def set_symbol_tp_sl_mode(self, symbol: str, full_mode: bool) -> bool:
        from . import exchange_positions as pos
        return pos.set_symbol_tp_sl_mode(self, symbol, full_mode)
    
    def set_auto_add_margin(self, symbol: str, enabled: bool) -> bool:
        from . import exchange_positions as pos
        return pos.set_auto_add_margin(self, symbol, enabled)
    
    def modify_position_margin(self, symbol: str, margin: float) -> bool:
        from . import exchange_positions as pos
        return pos.modify_position_margin(self, symbol, margin)
    
    def switch_to_cross_margin(self, symbol: str, leverage: int | None = None) -> bool:
        from . import exchange_positions as pos
        return pos.switch_to_cross_margin(self, symbol, leverage)
    
    def switch_to_isolated_margin(self, symbol: str, leverage: int | None = None) -> bool:
        from . import exchange_positions as pos
        return pos.switch_to_isolated_margin(self, symbol, leverage)
    
    def switch_to_one_way_mode(self) -> bool:
        from . import exchange_positions as pos
        return pos.switch_to_one_way_mode(self)
    
    def switch_to_hedge_mode(self) -> bool:
        from . import exchange_positions as pos
        return pos.switch_to_hedge_mode(self)
    
    # ==================== Unified Account (delegated) ====================
    
    def get_transaction_log(self, time_range: TimeRange, category: str | None = None, currency: str | None = None, log_type: str | None = None, limit: int = 50) -> dict:
        from . import exchange_positions as pos
        return pos.get_transaction_log(self, time_range, category, currency, log_type, limit)
    
    def get_collateral_info(self, currency: str | None = None) -> list[dict]:
        from . import exchange_positions as pos
        return pos.get_collateral_info(self, currency)
    
    def set_collateral_coin(self, coin: str, enabled: bool) -> bool:
        from . import exchange_positions as pos
        return pos.set_collateral_coin(self, coin, enabled)
    
    def get_borrow_history(self, time_range: TimeRange, currency: str | None = None, limit: int = 50) -> dict:
        from . import exchange_positions as pos
        return pos.get_borrow_history(self, time_range, currency, limit)
    
    def get_coin_greeks(self, base_coin: str | None = None) -> list[dict]:
        from . import exchange_positions as pos
        return pos.get_coin_greeks(self, base_coin)
    
    def set_account_margin_mode(self, portfolio_margin: bool) -> bool:
        from . import exchange_positions as pos
        return pos.set_account_margin_mode(self, portfolio_margin)
    
    def get_transferable_amount(self, coin: str) -> float:
        from . import exchange_positions as pos
        return pos.get_transferable_amount(self, coin)
    
    # ==================== Instrument Helpers (delegated) ====================
    
    def _get_instrument_info(self, symbol: str) -> dict:
        from . import exchange_instruments as inst
        return inst.get_instrument_info(self, symbol)
    
    def _round_price(self, symbol: str, price: float) -> float:
        from . import exchange_instruments as inst
        return inst.round_price(self, symbol, price)
    
    def _get_tick_size(self, symbol: str) -> float:
        from . import exchange_instruments as inst
        return inst.get_tick_size(self, symbol)
    
    def _get_min_qty(self, symbol: str) -> float:
        from . import exchange_instruments as inst
        return inst.get_min_qty(self, symbol)
    
    def _calculate_qty(self, symbol: str, usd_amount: float, price: float | None = None) -> float:
        from . import exchange_instruments as inst
        return inst.calculate_qty(self, symbol, usd_amount, price)
    
    def _get_price_precision(self, symbol: str) -> int:
        from . import exchange_instruments as inst
        return inst.get_price_precision(self, symbol)
    
    # ==================== Utility ====================
    
    def get_rate_limit_status(self) -> dict:
        """Get current rate limit status."""
        return self.bybit.get_rate_limit_status()
    
    def get_server_time_offset(self) -> int:
        """Get time offset from server in ms."""
        try:
            return self.bybit.get_time_offset()
        except Exception as e:
            self.logger.debug(f"Failed to get server time offset: {e}, using 0")
            return 0
    
    def test_connection(self) -> dict[str, Any]:
        """Test exchange connectivity."""
        return self.bybit.test_connection()
