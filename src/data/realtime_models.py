"""
Real-time data models for WebSocket-driven state.

Contains all normalized data types used by RealtimeState:
- EventType, ConnectionState enums
- Market data: TickerData, OrderbookData, TradeData, KlineData, BarRecord
- Account data: PositionData, OrderData, ExecutionData, WalletData, AccountMetrics
- Risk data: PortfolioRiskSnapshot
- Utility: RealtimeEvent, ConnectionStatus

Timeframe Terminology:
- lower timeframe (low_tf): 1m, 3m, 5m, 15m (execution timing)
- medium timeframe (med_tf): 30m, 1h, 2h, 4h (trade bias)
- higher timeframe (high_tf): 6h, 12h, D, W (trend direction)
- execution timeframe (exec): Play's execution timeframe pointer
- multi-timeframe: Cross-timeframe analysis (comparing low_tf/med_tf/high_tf)
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar

import pandas as pd


# ==============================================================================
# Enums and Constants
# ==============================================================================

class EventType(Enum):
    """Event types for real-time updates."""
    TICKER_UPDATE = "ticker_update"
    ORDERBOOK_SNAPSHOT = "orderbook_snapshot"
    ORDERBOOK_DELTA = "orderbook_delta"
    TRADE = "trade"
    KLINE_UPDATE = "kline_update"
    KLINE_CLOSED = "kline_closed"
    POSITION_UPDATE = "position_update"
    ORDER_UPDATE = "order_update"
    EXECUTION = "execution"
    WALLET_UPDATE = "wallet_update"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class ConnectionState(Enum):
    """WebSocket connection states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


STALENESS_THRESHOLDS = {
    "ticker": 5.0,
    "orderbook": 5.0,
    "kline": 60.0,
    "position": 10.0,
    "order": 10.0,
    "wallet": 30.0,
}


# ==============================================================================
# Market Data Models
# ==============================================================================

@dataclass
class TickerData:
    """Normalized ticker data."""
    symbol: str
    last_price: float
    bid_price: float
    ask_price: float
    bid_size: float = 0.0
    ask_size: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    volume_24h: float = 0.0
    turnover_24h: float = 0.0
    price_change_24h: float = 0.0
    price_change_percent_24h: float = 0.0
    mark_price: float = 0.0
    index_price: float = 0.0
    funding_rate: float = 0.0
    next_funding_time: int = 0
    open_interest: float = 0.0
    timestamp: float = field(default_factory=time.time)
    
    @classmethod
    def from_bybit(cls, data: dict) -> 'TickerData':
        return cls(
            symbol=data.get("symbol", ""),
            last_price=float(data.get("lastPrice", 0)),
            bid_price=float(data.get("bid1Price", 0)),
            ask_price=float(data.get("ask1Price", 0)),
            bid_size=float(data.get("bid1Size", 0)),
            ask_size=float(data.get("ask1Size", 0)),
            high_24h=float(data.get("highPrice24h", 0)),
            low_24h=float(data.get("lowPrice24h", 0)),
            volume_24h=float(data.get("volume24h", 0)),
            turnover_24h=float(data.get("turnover24h", 0)),
            price_change_24h=float(data.get("price24hPcnt", 0)) * 100,
            price_change_percent_24h=float(data.get("price24hPcnt", 0)) * 100,
            mark_price=float(data.get("markPrice", 0)),
            index_price=float(data.get("indexPrice", 0)),
            funding_rate=float(data.get("fundingRate", 0)),
            next_funding_time=int(data.get("nextFundingTime", 0)),
            open_interest=float(data.get("openInterest", 0)),
            timestamp=time.time(),
        )
    
    @property
    def spread(self) -> float:
        return self.ask_price - self.bid_price
    
    @property
    def spread_percent(self) -> float:
        mid = (self.bid_price + self.ask_price) / 2 if self.bid_price else 0
        return (self.spread / mid * 100) if mid else 0
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "last_price": self.last_price,
            "bid": self.bid_price, "ask": self.ask_price,
            "high_24h": self.high_24h, "low_24h": self.low_24h,
            "volume_24h": self.volume_24h, "price_change_24h": self.price_change_24h,
            "mark_price": self.mark_price, "funding_rate": self.funding_rate,
            "timestamp": self.timestamp,
        }


@dataclass
class OrderbookLevel:
    """Single orderbook level."""
    price: float
    size: float


@dataclass
class OrderbookData:
    """Normalized orderbook data."""
    symbol: str
    bids: list[OrderbookLevel] = field(default_factory=list)
    asks: list[OrderbookLevel] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    update_id: int = 0
    
    @classmethod
    def from_bybit(cls, data: dict, symbol: str) -> 'OrderbookData':
        bids = [OrderbookLevel(float(b[0]), float(b[1])) for b in data.get("b", [])]
        asks = [OrderbookLevel(float(a[0]), float(a[1])) for a in data.get("a", [])]
        return cls(
            symbol=symbol,
            bids=sorted(bids, key=lambda x: x.price, reverse=True),
            asks=sorted(asks, key=lambda x: x.price),
            timestamp=time.time(),
            update_id=data.get("u", 0),
        )
    
    def apply_delta(self, delta: dict):
        for b in delta.get("b", []):
            price, size = float(b[0]), float(b[1])
            self._update_side(self.bids, price, size, reverse=True)
        for a in delta.get("a", []):
            price, size = float(a[0]), float(a[1])
            self._update_side(self.asks, price, size, reverse=False)
        self.timestamp = time.time()
        self.update_id = delta.get("u", self.update_id)
    
    def _update_side(self, levels: list[OrderbookLevel], price: float, size: float, reverse: bool):
        for i, level in enumerate(levels):
            if level.price == price:
                if size == 0:
                    levels.pop(i)
                else:
                    level.size = size
                return
        if size > 0:
            levels.append(OrderbookLevel(price, size))
            levels.sort(key=lambda x: x.price, reverse=reverse)
    
    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0
    
    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 0
    
    @property
    def mid_price(self) -> float:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return 0
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "bids": [[l.price, l.size] for l in self.bids[:10]],
            "asks": [[l.price, l.size] for l in self.asks[:10]],
            "best_bid": self.best_bid, "best_ask": self.best_ask,
            "mid_price": self.mid_price, "timestamp": self.timestamp,
        }


@dataclass
class TradeData:
    """Normalized public trade data."""
    symbol: str
    trade_id: str
    price: float
    size: float
    side: str
    timestamp: float
    is_block_trade: bool = False
    
    @classmethod
    def from_bybit(cls, data: dict) -> 'TradeData':
        return cls(
            symbol=data.get("s", ""),
            trade_id=data.get("i", ""),
            price=float(data.get("p", 0)),
            size=float(data.get("v", 0)),
            side=data.get("S", "Buy"),
            timestamp=float(data.get("T", 0)) / 1000,
            is_block_trade=data.get("BT", False),
        )
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "trade_id": self.trade_id,
            "price": self.price, "size": self.size,
            "side": self.side, "timestamp": self.timestamp,
        }


@dataclass
class KlineData:
    """Normalized kline/candlestick data."""
    symbol: str
    interval: str
    start_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float
    end_time: int = 0
    is_closed: bool = False
    timestamp: float = field(default_factory=time.time)

    # Bybit interval → normalized format (matches our DuckDB/FeedStore convention)
    _INTERVAL_MAP: ClassVar[dict[str, str]] = {
        "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
        "60": "1h", "120": "2h", "240": "4h", "360": "6h", "720": "12h",
        "d": "D", "w": "W", "m": "M",
    }

    # Normalized format → Bybit interval (reverse of _INTERVAL_MAP)
    _TF_TO_BYBIT_MAP: ClassVar[dict[str, str]] = {
        v: k for k, v in _INTERVAL_MAP.items()
    } | {"D": "D", "W": "W", "M": "M"}

    @classmethod
    def tf_to_bybit(cls, tf: str) -> str:
        """Convert our timeframe format to Bybit interval format.

        Raises ValueError for unknown timeframes (no silent defaults).
        """
        result = cls._TF_TO_BYBIT_MAP.get(tf)
        if result is None:
            raise ValueError(f"Unknown timeframe: {tf!r}")
        return result

    @classmethod
    def _normalize_interval(cls, raw: str) -> str:
        """Convert Bybit interval (e.g., '15', '60', 'D') to our format ('15m', '1h', 'D')."""
        return cls._INTERVAL_MAP.get(raw.lower(), raw)

    @classmethod
    def from_bybit(cls, data: dict, topic: str = "") -> 'KlineData':
        # Topic format: "kline.{interval}.{symbol}"
        raw_interval = ""
        symbol = ""
        if topic:
            parts = topic.split(".")
            if len(parts) >= 2:
                raw_interval = parts[1]
            if len(parts) >= 3:
                symbol = parts[2]
        raw_interval = raw_interval or str(data.get("interval", ""))
        return cls(
            symbol=symbol or data.get("symbol", ""),
            interval=cls._normalize_interval(raw_interval),
            start_time=int(data.get("start", 0)),
            end_time=int(data.get("end", 0)),
            open=float(data.get("open", 0)),
            high=float(data.get("high", 0)),
            low=float(data.get("low", 0)),
            close=float(data.get("close", 0)),
            volume=float(data.get("volume", 0)),
            turnover=float(data.get("turnover", 0)),
            is_closed=data.get("confirm", False),
            timestamp=time.time(),
        )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "interval": self.interval,
            "start_time": self.start_time, "end_time": self.end_time,
            "open": self.open, "high": self.high, "low": self.low,
            "close": self.close, "volume": self.volume,
            "is_closed": self.is_closed, "timestamp": self.timestamp,
        }


@dataclass
class BarRecord:
    """
    Bar data record for ring buffer storage.

    Used for storing closed bars in memory buffers during live/demo trading.
    Works with any timeframe (low_tf, med_tf, high_tf).
    """
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def from_kline_data(cls, kline: 'KlineData') -> 'BarRecord':
        # UTC-naive datetime for DuckDB compatibility (system stores UTC-naive)
        return cls(
            timestamp=datetime.fromtimestamp(kline.start_time / 1000, tz=timezone.utc).replace(tzinfo=None),
            open=kline.open, high=kline.high, low=kline.low,
            close=kline.close, volume=kline.volume,
        )

    @classmethod
    def from_df_row(cls, row) -> 'BarRecord':
        ts = row.get("timestamp") or row.get("ts")
        return cls(
            timestamp=ts if isinstance(ts, datetime) else pd.Timestamp(ts).to_pydatetime(),
            open=float(row.get("open", 0)), high=float(row.get("high", 0)),
            low=float(row.get("low", 0)), close=float(row.get("close", 0)),
            volume=float(row.get("volume", 0)),
        )

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat() if hasattr(self.timestamp, "isoformat") else str(self.timestamp),
            "open": self.open, "high": self.high, "low": self.low,
            "close": self.close, "volume": self.volume,
        }


BAR_BUFFER_SIZES = {
    "1m": 500, "3m": 400, "5m": 300, "15m": 200, "30m": 200,
    "1h": 168, "2h": 84, "4h": 180, "6h": 120, "12h": 60,
    "1d": 90, "D": 90, "1w": 52, "W": 52, "1M": 24, "M": 24,
}


def get_bar_buffer_size(timeframe: str) -> int:
    """Get default buffer size for a timeframe."""
    return BAR_BUFFER_SIZES.get(timeframe, 200)


# ==============================================================================
# Account Data Models
# ==============================================================================

@dataclass
class PositionData:
    """Normalized position data with full risk metrics."""
    symbol: str
    side: str
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    leverage: float
    position_value: float
    liq_price: float = 0.0
    take_profit: float = 0.0
    stop_loss: float = 0.0
    trailing_stop: float = 0.0
    position_idx: int = 0
    created_time: int = 0
    updated_time: int = 0
    timestamp: float = field(default_factory=time.time)
    position_im: float = 0.0
    position_mm: float = 0.0
    position_status: str = "Normal"
    adl_rank_indicator: int = 0
    is_reduce_only: bool = False
    risk_id: int = 0
    risk_limit_value: str = ""
    cur_realized_pnl: float = 0.0
    cum_realized_pnl: float = 0.0
    session_avg_price: float = 0.0
    category: str = "linear"
    
    @classmethod
    def from_bybit(cls, data: dict) -> 'PositionData':
        size = float(data.get("size", 0))
        leverage_str = data.get("leverage", "1")
        leverage = float(leverage_str) if leverage_str else 1.0
        position_im_str = data.get("positionIM", "0")
        position_mm_str = data.get("positionMM", "0")
        position_im = float(position_im_str) if position_im_str else 0.0
        position_mm = float(position_mm_str) if position_mm_str else 0.0
        
        return cls(
            symbol=data.get("symbol", ""), side=data.get("side", ""),
            size=size, entry_price=float(data.get("entryPrice", 0)),
            mark_price=float(data.get("markPrice", 0)),
            unrealized_pnl=float(data.get("unrealisedPnl", 0)),
            leverage=leverage, position_value=float(data.get("positionValue", 0)),
            liq_price=float(data.get("liqPrice", 0) or 0),
            take_profit=float(data.get("takeProfit", 0) or 0),
            stop_loss=float(data.get("stopLoss", 0) or 0),
            trailing_stop=float(data.get("trailingStop", 0) or 0),
            position_idx=int(data.get("positionIdx", 0)),
            created_time=int(data.get("createdTime", 0)),
            updated_time=int(data.get("updatedTime", 0)),
            timestamp=time.time(),
            position_im=position_im, position_mm=position_mm,
            position_status=data.get("positionStatus", "Normal"),
            adl_rank_indicator=int(data.get("adlRankIndicator", 0)),
            is_reduce_only=data.get("isReduceOnly", False),
            risk_id=int(data.get("riskId", 0)),
            risk_limit_value=str(data.get("riskLimitValue", "")),
            cur_realized_pnl=float(data.get("curRealisedPnl", 0) or 0),
            cum_realized_pnl=float(data.get("cumRealisedPnl", 0) or 0),
            session_avg_price=float(data.get("sessionAvgPrice", 0) or 0),
            category=data.get("category", "linear"),
        )
    
    @property
    def is_long(self) -> bool:
        return self.side == "Buy"
    
    @property
    def is_short(self) -> bool:
        return self.side == "Sell"
    
    @property
    def is_open(self) -> bool:
        return self.size > 0
    
    @property
    def is_liquidating(self) -> bool:
        return self.position_status == "Liq"
    
    @property
    def is_adl(self) -> bool:
        return self.position_status == "Adl"
    
    @property
    def pnl_percent(self) -> float:
        if self.position_value:
            return (self.unrealized_pnl / self.position_value) * 100
        return 0
    
    @property
    def liq_distance_abs(self) -> float:
        if not self.liq_price or not self.mark_price:
            return float('inf')
        return abs(self.mark_price - self.liq_price)
    
    @property
    def liq_distance_pct(self) -> float:
        if not self.mark_price or not self.liq_price:
            return float('inf')
        return (self.liq_distance_abs / self.mark_price) * 100
    
    @property
    def margin_usage_pct(self) -> float:
        if self.position_value and self.position_im:
            return (self.position_im / self.position_value) * 100
        return 0
    
    @property
    def is_high_risk(self) -> bool:
        return (
            self.position_status != "Normal" or
            self.adl_rank_indicator >= 4 or
            self.is_reduce_only or
            self.liq_distance_pct < 5.0
        )
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol, "side": self.side, "size": self.size,
            "entry_price": self.entry_price, "mark_price": self.mark_price,
            "unrealized_pnl": self.unrealized_pnl, "pnl_percent": self.pnl_percent,
            "leverage": self.leverage, "position_value": self.position_value,
            "liq_price": self.liq_price, "liq_distance_pct": self.liq_distance_pct,
            "take_profit": self.take_profit, "stop_loss": self.stop_loss,
            "position_im": self.position_im, "position_mm": self.position_mm,
            "position_status": self.position_status,
            "adl_rank_indicator": self.adl_rank_indicator,
            "is_reduce_only": self.is_reduce_only, "is_high_risk": self.is_high_risk,
            "category": self.category, "timestamp": self.timestamp,
        }


@dataclass
class OrderData:
    """Normalized order data."""
    order_id: str
    symbol: str
    side: str
    order_type: str
    price: float
    qty: float
    filled_qty: float = 0.0
    status: str = ""
    time_in_force: str = "GTC"
    reduce_only: bool = False
    close_on_trigger: bool = False
    take_profit: float = 0.0
    stop_loss: float = 0.0
    order_link_id: str = ""
    created_time: int = 0
    updated_time: int = 0
    timestamp: float = field(default_factory=time.time)
    
    @classmethod
    def from_bybit(cls, data: dict) -> 'OrderData':
        def safe_float(val, default=0.0):
            if val == "" or val is None:
                return default
            return float(val)
        def safe_int(val, default=0):
            if val == "" or val is None:
                return default
            return int(val)
        return cls(
            order_id=data.get("orderId", ""), symbol=data.get("symbol", ""),
            side=data.get("side", ""), order_type=data.get("orderType", ""),
            price=safe_float(data.get("price")), qty=safe_float(data.get("qty")),
            filled_qty=safe_float(data.get("cumExecQty")),
            status=data.get("orderStatus", ""),
            time_in_force=data.get("timeInForce", "GTC"),
            reduce_only=data.get("reduceOnly", False),
            close_on_trigger=data.get("closeOnTrigger", False),
            take_profit=safe_float(data.get("takeProfit")),
            stop_loss=safe_float(data.get("stopLoss")),
            order_link_id=data.get("orderLinkId", ""),
            created_time=safe_int(data.get("createdTime")),
            updated_time=safe_int(data.get("updatedTime")),
            timestamp=time.time(),
        )
    
    @property
    def is_open(self) -> bool:
        return self.status in ("New", "PartiallyFilled", "Untriggered")
    
    @property
    def is_filled(self) -> bool:
        return self.status == "Filled"
    
    @property
    def fill_percent(self) -> float:
        return (self.filled_qty / self.qty * 100) if self.qty else 0
    
    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id, "symbol": self.symbol,
            "side": self.side, "order_type": self.order_type,
            "price": self.price, "qty": self.qty,
            "filled_qty": self.filled_qty, "status": self.status,
            "take_profit": self.take_profit, "stop_loss": self.stop_loss,
            "timestamp": self.timestamp,
        }


@dataclass
class ExecutionData:
    """Normalized trade execution data."""
    exec_id: str
    order_id: str
    symbol: str
    side: str
    price: float
    qty: float
    exec_type: str = ""
    exec_fee: float = 0.0
    fee_rate: float = 0.0
    is_maker: bool = False
    order_link_id: str = ""
    exec_time: int = 0
    closed_pnl: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def from_bybit(cls, data: dict) -> 'ExecutionData':
        def safe_float(val, default=0.0):
            if val == "" or val is None:
                return default
            return float(val)
        def safe_int(val, default=0):
            if val == "" or val is None:
                return default
            return int(val)
        return cls(
            exec_id=data.get("execId", ""), order_id=data.get("orderId", ""),
            symbol=data.get("symbol", ""), side=data.get("side", ""),
            price=safe_float(data.get("execPrice")), qty=safe_float(data.get("execQty")),
            exec_type=data.get("execType", ""), exec_fee=safe_float(data.get("execFee")),
            fee_rate=safe_float(data.get("feeRate")), is_maker=data.get("isMaker", False),
            order_link_id=data.get("orderLinkId", ""),
            exec_time=safe_int(data.get("execTime")),
            closed_pnl=safe_float(data.get("closedPnl")),
            timestamp=time.time(),
        )
    
    def to_dict(self) -> dict:
        return {
            "exec_id": self.exec_id, "order_id": self.order_id,
            "symbol": self.symbol, "side": self.side,
            "price": self.price, "qty": self.qty,
            "exec_type": self.exec_type, "exec_fee": self.exec_fee,
            "is_maker": self.is_maker, "timestamp": self.timestamp,
        }


@dataclass
class WalletData:
    """Normalized per-coin wallet/balance data."""
    coin: str
    equity: float
    wallet_balance: float
    available_balance: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    margin_balance: float = 0.0
    position_margin: float = 0.0
    order_margin: float = 0.0
    usd_value: float = 0.0
    locked: float = 0.0
    borrow_amount: float = 0.0
    accrued_interest: float = 0.0
    total_order_im: float = 0.0
    total_position_im: float = 0.0
    total_position_mm: float = 0.0
    bonus: float = 0.0
    collateral_switch: bool = True
    margin_collateral: bool = True
    timestamp: float = field(default_factory=time.time)
    
    @classmethod
    def from_bybit(cls, data: dict) -> 'WalletData':
        return cls(
            coin=data.get("coin", "USDT"),
            equity=float(data.get("equity", 0) or 0),
            wallet_balance=float(data.get("walletBalance", 0) or 0),
            available_balance=float(data.get("availableToWithdraw", 0) or 0),
            unrealized_pnl=float(data.get("unrealisedPnl", 0) or 0),
            realized_pnl=float(data.get("cumRealisedPnl", 0) or 0),
            margin_balance=float(data.get("marginBalance", 0) or 0),
            position_margin=float(data.get("positionMargin", 0) or 0),
            order_margin=float(data.get("orderMargin", 0) or 0),
            usd_value=float(data.get("usdValue", 0) or 0),
            locked=float(data.get("locked", 0) or 0),
            borrow_amount=float(data.get("borrowAmount", 0) or 0),
            accrued_interest=float(data.get("accruedInterest", 0) or 0),
            total_order_im=float(data.get("totalOrderIM", 0) or 0),
            total_position_im=float(data.get("totalPositionIM", 0) or 0),
            total_position_mm=float(data.get("totalPositionMM", 0) or 0),
            bonus=float(data.get("bonus", 0) or 0),
            collateral_switch=data.get("collateralSwitch", True),
            margin_collateral=data.get("marginCollateral", True),
            timestamp=time.time(),
        )
    
    def to_dict(self) -> dict:
        return {
            "coin": self.coin, "equity": self.equity,
            "wallet_balance": self.wallet_balance,
            "available_balance": self.available_balance,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "usd_value": self.usd_value,
            "position_margin": self.position_margin,
            "order_margin": self.order_margin,
            "timestamp": self.timestamp,
        }


@dataclass
class AccountMetrics:
    """Unified account-level metrics for risk management."""
    account_type: str = "UNIFIED"
    account_im_rate: float = 0.0
    account_mm_rate: float = 0.0
    total_equity: float = 0.0
    total_wallet_balance: float = 0.0
    total_margin_balance: float = 0.0
    total_available_balance: float = 0.0
    total_perp_upl: float = 0.0
    total_initial_margin: float = 0.0
    total_maintenance_margin: float = 0.0
    timestamp: float = field(default_factory=time.time)
    
    @classmethod
    def from_bybit(cls, data: dict) -> 'AccountMetrics':
        total_equity = float(data.get("totalEquity", 0) or 0)
        total_wallet_balance = float(data.get("totalWalletBalance", 0) or 0)
        total_margin_balance = float(data.get("totalMarginBalance", 0) or 0)
        total_available_balance = float(data.get("totalAvailableBalance", 0) or 0)
        total_initial_margin = float(data.get("totalInitialMargin", 0) or 0)
        total_order_margin = float(data.get("totalOrderMargin", 0) or 0)
        
        if total_available_balance == 0 and total_wallet_balance > 0:
            margin_used = total_initial_margin + total_order_margin
            calculated_available = total_wallet_balance - margin_used
            total_available_balance = max(0.0, calculated_available)
            if total_available_balance == 0 and total_initial_margin == 0:
                total_available_balance = total_wallet_balance
        
        if total_margin_balance == 0 and total_wallet_balance > 0:
            total_margin_balance = total_wallet_balance
        
        return cls(
            account_type=data.get("accountType", "UNIFIED"),
            account_im_rate=float(data.get("accountIMRate", 0) or 0),
            account_mm_rate=float(data.get("accountMMRate", 0) or 0),
            total_equity=total_equity,
            total_wallet_balance=total_wallet_balance,
            total_margin_balance=total_margin_balance,
            total_available_balance=total_available_balance,
            total_perp_upl=float(data.get("totalPerpUPL", 0) or 0),
            total_initial_margin=total_initial_margin,
            total_maintenance_margin=float(data.get("totalMaintenanceMargin", 0) or 0),
            timestamp=time.time(),
        )
    
    @property
    def margin_utilization(self) -> float:
        if self.total_margin_balance:
            return (self.total_initial_margin / self.total_margin_balance) * 100
        return 0
    
    @property
    def risk_buffer(self) -> float:
        return self.total_margin_balance - self.total_maintenance_margin
    
    @property
    def risk_buffer_pct(self) -> float:
        if self.total_margin_balance > 0:
            return (self.risk_buffer / self.total_margin_balance) * 100
        return 100.0
    
    @property
    def max_additional_margin(self) -> float:
        return self.total_available_balance
    
    @property
    def is_high_risk(self) -> bool:
        if self.total_maintenance_margin == 0:
            return False
        return (self.account_mm_rate > 0.8 or self.risk_buffer_pct < 10)
    
    @property
    def liquidation_risk_level(self) -> str:
        if self.account_mm_rate > 0.9:
            return "CRITICAL"
        elif self.account_mm_rate > 0.7:
            return "HIGH"
        elif self.account_mm_rate > 0.5:
            return "MEDIUM"
        return "LOW"
    
    def to_dict(self) -> dict:
        return {
            "account_type": self.account_type,
            "account_im_rate": self.account_im_rate,
            "account_mm_rate": self.account_mm_rate,
            "margin_utilization": self.margin_utilization,
            "total_equity": self.total_equity,
            "total_wallet_balance": self.total_wallet_balance,
            "total_margin_balance": self.total_margin_balance,
            "total_available_balance": self.total_available_balance,
            "total_perp_upl": self.total_perp_upl,
            "total_initial_margin": self.total_initial_margin,
            "total_maintenance_margin": self.total_maintenance_margin,
            "risk_buffer": self.risk_buffer,
            "risk_buffer_pct": self.risk_buffer_pct,
            "is_high_risk": self.is_high_risk,
            "liquidation_risk_level": self.liquidation_risk_level,
            "timestamp": self.timestamp,
        }


@dataclass
class PortfolioRiskSnapshot:
    """Aggregated portfolio risk snapshot."""
    timestamp: float = field(default_factory=time.time)
    account_type: str = "UNIFIED"
    account_im_rate: float = 0.0
    account_mm_rate: float = 0.0
    total_equity: float = 0.0
    total_wallet_balance: float = 0.0
    total_margin_balance: float = 0.0
    total_available_balance: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_realized_pnl: float = 0.0
    total_notional_usd: float = 0.0
    total_position_count: int = 0
    long_exposure_usd: float = 0.0
    short_exposure_usd: float = 0.0
    net_exposure_usd: float = 0.0
    weighted_leverage: float = 0.0
    worst_liq_distance_pct: float = float('inf')
    worst_liq_symbol: str = ""
    max_position_leverage: float = 0.0
    max_leverage_symbol: str = ""
    exposure_by_asset: dict[str, float] = field(default_factory=dict)
    high_risk_position_count: int = 0
    positions_near_liq: int = 0
    is_account_high_risk: bool = False
    has_liquidating_positions: bool = False
    has_adl_positions: bool = False
    has_reduce_only_positions: bool = False
    liquidation_risk_level: str = "LOW"
    
    @classmethod
    def from_state(
        cls,
        account_metrics: 'AccountMetrics | None',
        positions: dict[str, 'PositionData'],
        config=None,
    ) -> 'PortfolioRiskSnapshot':
        snapshot = cls()
        
        if account_metrics:
            snapshot.account_type = account_metrics.account_type
            snapshot.account_im_rate = account_metrics.account_im_rate
            snapshot.account_mm_rate = account_metrics.account_mm_rate
            snapshot.total_equity = account_metrics.total_equity
            snapshot.total_wallet_balance = account_metrics.total_wallet_balance
            snapshot.total_margin_balance = account_metrics.total_margin_balance
            snapshot.total_available_balance = account_metrics.total_available_balance
            snapshot.total_unrealized_pnl = account_metrics.total_perp_upl
            snapshot.is_account_high_risk = account_metrics.is_high_risk
            snapshot.liquidation_risk_level = account_metrics.liquidation_risk_level
        
        exposure_by_asset: dict[str, float] = {}
        total_leverage_weighted = 0.0
        total_realized_pnl = 0.0
        
        for symbol, pos in positions.items():
            if not pos.is_open:
                continue
            
            snapshot.total_position_count += 1
            snapshot.total_notional_usd += pos.position_value
            
            if pos.is_long:
                snapshot.long_exposure_usd += pos.position_value
            else:
                snapshot.short_exposure_usd += pos.position_value
            
            total_leverage_weighted += pos.leverage * pos.position_value
            if pos.leverage > snapshot.max_position_leverage:
                snapshot.max_position_leverage = pos.leverage
                snapshot.max_leverage_symbol = symbol
            
            liq_dist = pos.liq_distance_pct
            if liq_dist < snapshot.worst_liq_distance_pct:
                snapshot.worst_liq_distance_pct = liq_dist
                snapshot.worst_liq_symbol = symbol
            
            if liq_dist < 10.0:
                snapshot.positions_near_liq += 1
            
            if pos.is_high_risk:
                snapshot.high_risk_position_count += 1
            if pos.is_liquidating:
                snapshot.has_liquidating_positions = True
            if pos.is_adl:
                snapshot.has_adl_positions = True
            if pos.is_reduce_only:
                snapshot.has_reduce_only_positions = True
            
            total_realized_pnl += pos.cum_realized_pnl
            
            underlying = symbol.replace("USDT", "").replace("USD", "").replace("PERP", "")
            exposure_by_asset[underlying] = exposure_by_asset.get(underlying, 0) + pos.position_value
        
        snapshot.net_exposure_usd = snapshot.long_exposure_usd - snapshot.short_exposure_usd
        snapshot.total_realized_pnl = total_realized_pnl
        
        if snapshot.total_notional_usd > 0:
            snapshot.weighted_leverage = total_leverage_weighted / snapshot.total_notional_usd
        
        sorted_exposure = sorted(exposure_by_asset.items(), key=lambda x: x[1], reverse=True)[:5]
        snapshot.exposure_by_asset = dict(sorted_exposure)
        
        if snapshot.has_liquidating_positions or (account_metrics and account_metrics.account_mm_rate > 0.9):
            snapshot.liquidation_risk_level = "CRITICAL"
        elif snapshot.has_adl_positions or snapshot.positions_near_liq > 0:
            snapshot.liquidation_risk_level = "HIGH"
        elif snapshot.high_risk_position_count > 0 or (account_metrics and account_metrics.account_mm_rate > 0.5):
            snapshot.liquidation_risk_level = "MEDIUM"
        else:
            snapshot.liquidation_risk_level = "LOW"
        
        return snapshot
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp, "account_type": self.account_type,
            "account_im_rate": self.account_im_rate, "account_mm_rate": self.account_mm_rate,
            "total_equity": self.total_equity, "total_wallet_balance": self.total_wallet_balance,
            "total_margin_balance": self.total_margin_balance,
            "total_available_balance": self.total_available_balance,
            "total_unrealized_pnl": self.total_unrealized_pnl,
            "total_realized_pnl": self.total_realized_pnl,
            "total_notional_usd": self.total_notional_usd,
            "total_position_count": self.total_position_count,
            "long_exposure_usd": self.long_exposure_usd,
            "short_exposure_usd": self.short_exposure_usd,
            "net_exposure_usd": self.net_exposure_usd,
            "weighted_leverage": self.weighted_leverage,
            "worst_liq_distance_pct": self.worst_liq_distance_pct if self.worst_liq_distance_pct != float('inf') else None,
            "worst_liq_symbol": self.worst_liq_symbol,
            "max_position_leverage": self.max_position_leverage,
            "max_leverage_symbol": self.max_leverage_symbol,
            "exposure_by_asset": self.exposure_by_asset,
            "high_risk_position_count": self.high_risk_position_count,
            "positions_near_liq": self.positions_near_liq,
            "is_account_high_risk": self.is_account_high_risk,
            "has_liquidating_positions": self.has_liquidating_positions,
            "has_adl_positions": self.has_adl_positions,
            "has_reduce_only_positions": self.has_reduce_only_positions,
            "liquidation_risk_level": self.liquidation_risk_level,
        }


# ==============================================================================
# Utility Classes
# ==============================================================================

@dataclass
class RealtimeEvent:
    """Wrapper for real-time events."""
    event_type: EventType
    data: Any
    symbol: str = ""
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "data": self.data.to_dict() if hasattr(self.data, "to_dict") else str(self.data),
        }


@dataclass
class ConnectionStatus:
    """WebSocket connection status."""
    state: ConnectionState = ConnectionState.DISCONNECTED
    connected_at: float | None = None
    disconnected_at: float | None = None
    reconnect_count: int = 0
    last_error: str | None = None
    last_message_at: float | None = None
    
    @property
    def is_connected(self) -> bool:
        return self.state == ConnectionState.CONNECTED
    
    @property
    def uptime_seconds(self) -> float:
        if self.connected_at and self.is_connected:
            return time.time() - self.connected_at
        return 0
    
    def to_dict(self) -> dict:
        return {
            "state": self.state.value, "connected_at": self.connected_at,
            "uptime_seconds": self.uptime_seconds, "reconnect_count": self.reconnect_count,
            "last_error": self.last_error, "last_message_at": self.last_message_at,
        }

