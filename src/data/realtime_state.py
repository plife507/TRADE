"""
Real-time state management for WebSocket-driven data.

This module provides a thread-safe, centralized store for real-time market
and account data received via WebSocket streams. It serves as the single
source of truth for live data across the trading system.

Architecture:
- Domain models: Normalized event and state types (independent of raw Bybit payloads)
- State containers: Thread-safe storage for each data type
- RealtimeState: Central manager that coordinates all state updates
- Event queue: Optional queue for event-driven processing

Usage:
    from src.data.realtime_state import get_realtime_state
    
    state = get_realtime_state()
    
    # Read current data
    ticker = state.get_ticker("BTCUSDT")
    positions = state.get_positions()
    
    # Check staleness
    if state.is_ticker_stale("BTCUSDT", max_age_seconds=5):
        # Fall back to REST
        pass
"""

import time
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from queue import Queue, Empty
from collections import defaultdict

from ..utils.logger import get_logger


# ==============================================================================
# Enums and Constants
# ==============================================================================

class EventType(Enum):
    """Event types for real-time updates."""
    # Public market events
    TICKER_UPDATE = "ticker_update"
    ORDERBOOK_SNAPSHOT = "orderbook_snapshot"
    ORDERBOOK_DELTA = "orderbook_delta"
    TRADE = "trade"
    KLINE_UPDATE = "kline_update"
    KLINE_CLOSED = "kline_closed"
    
    # Private account events
    POSITION_UPDATE = "position_update"
    ORDER_UPDATE = "order_update"
    EXECUTION = "execution"
    WALLET_UPDATE = "wallet_update"
    
    # Connection events
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


# Default staleness thresholds (seconds)
STALENESS_THRESHOLDS = {
    "ticker": 5.0,
    "orderbook": 5.0,
    "kline": 60.0,
    "position": 10.0,
    "order": 10.0,
    "wallet": 30.0,
}


# ==============================================================================
# Domain Models - Market Data (Public)
# ==============================================================================

@dataclass
class TickerData:
    """
    Normalized ticker data.
    
    Independent of raw Bybit payload format for stability.
    """
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
        """Parse from Bybit WebSocket ticker message."""
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
        """Bid-ask spread."""
        return self.ask_price - self.bid_price
    
    @property
    def spread_percent(self) -> float:
        """Spread as percentage of mid price."""
        mid = (self.bid_price + self.ask_price) / 2 if self.bid_price else 0
        return (self.spread / mid * 100) if mid else 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "last_price": self.last_price,
            "bid": self.bid_price,
            "ask": self.ask_price,
            "high_24h": self.high_24h,
            "low_24h": self.low_24h,
            "volume_24h": self.volume_24h,
            "price_change_24h": self.price_change_24h,
            "mark_price": self.mark_price,
            "funding_rate": self.funding_rate,
            "timestamp": self.timestamp,
        }


@dataclass
class OrderbookLevel:
    """Single orderbook level."""
    price: float
    size: float


@dataclass
class OrderbookData:
    """
    Normalized orderbook data.
    
    Maintains sorted bids (descending) and asks (ascending).
    """
    symbol: str
    bids: List[OrderbookLevel] = field(default_factory=list)
    asks: List[OrderbookLevel] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    update_id: int = 0
    
    @classmethod
    def from_bybit(cls, data: dict, symbol: str) -> 'OrderbookData':
        """Parse from Bybit WebSocket orderbook message."""
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
        """
        Apply delta update to orderbook.
        
        Rules:
        - If size is 0, delete the level
        - If price exists, update the size
        - If price doesn't exist, insert it
        """
        # Process bids
        for b in delta.get("b", []):
            price, size = float(b[0]), float(b[1])
            self._update_side(self.bids, price, size, reverse=True)
        
        # Process asks
        for a in delta.get("a", []):
            price, size = float(a[0]), float(a[1])
            self._update_side(self.asks, price, size, reverse=False)
        
        self.timestamp = time.time()
        self.update_id = delta.get("u", self.update_id)
    
    def _update_side(self, levels: List[OrderbookLevel], price: float, size: float, reverse: bool):
        """Update one side of the orderbook."""
        # Find existing level
        for i, level in enumerate(levels):
            if level.price == price:
                if size == 0:
                    levels.pop(i)
                else:
                    level.size = size
                return
        
        # Insert new level if size > 0
        if size > 0:
            levels.append(OrderbookLevel(price, size))
            levels.sort(key=lambda x: x.price, reverse=reverse)
    
    @property
    def best_bid(self) -> float:
        """Best bid price."""
        return self.bids[0].price if self.bids else 0
    
    @property
    def best_ask(self) -> float:
        """Best ask price."""
        return self.asks[0].price if self.asks else 0
    
    @property
    def mid_price(self) -> float:
        """Mid price."""
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "symbol": self.symbol,
            "bids": [[l.price, l.size] for l in self.bids[:10]],
            "asks": [[l.price, l.size] for l in self.asks[:10]],
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "mid_price": self.mid_price,
            "timestamp": self.timestamp,
        }


@dataclass
class TradeData:
    """
    Normalized public trade data.
    """
    symbol: str
    trade_id: str
    price: float
    size: float
    side: str  # "Buy" or "Sell"
    timestamp: float
    is_block_trade: bool = False
    
    @classmethod
    def from_bybit(cls, data: dict) -> 'TradeData':
        """Parse from Bybit WebSocket trade message."""
        return cls(
            symbol=data.get("s", ""),
            trade_id=data.get("i", ""),
            price=float(data.get("p", 0)),
            size=float(data.get("v", 0)),
            side=data.get("S", "Buy"),
            timestamp=float(data.get("T", 0)) / 1000,  # Convert ms to seconds
            is_block_trade=data.get("BT", False),
        )
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "trade_id": self.trade_id,
            "price": self.price,
            "size": self.size,
            "side": self.side,
            "timestamp": self.timestamp,
        }


@dataclass
class KlineData:
    """
    Normalized kline/candlestick data.
    """
    symbol: str
    interval: str
    start_time: int  # milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float
    is_closed: bool = False
    timestamp: float = field(default_factory=time.time)
    
    @classmethod
    def from_bybit(cls, data: dict, topic: str = "") -> 'KlineData':
        """Parse from Bybit WebSocket kline message."""
        # Extract interval from topic if available (e.g., "kline.15.BTCUSDT")
        interval = ""
        if topic:
            parts = topic.split(".")
            if len(parts) >= 2:
                interval = parts[1]
        
        return cls(
            symbol=data.get("symbol", ""),
            interval=interval or str(data.get("interval", "")),
            start_time=int(data.get("start", 0)),
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
            "symbol": self.symbol,
            "interval": self.interval,
            "start_time": self.start_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "is_closed": self.is_closed,
            "timestamp": self.timestamp,
        }


# ==============================================================================
# Domain Models - Account Data (Private)
# ==============================================================================

@dataclass
class PositionData:
    """
    Normalized position data with full risk metrics.
    
    Includes all position-level data needed for risk management:
    - Basic position info (symbol, side, size, prices)
    - Margin metrics (IM, MM, leverage)
    - Risk status (position status, ADL rank, liquidation price)
    - TP/SL settings
    """
    symbol: str
    side: str  # "Buy" (long) or "Sell" (short)
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
    position_idx: int = 0  # 0=one-way, 1=buy-hedge, 2=sell-hedge
    created_time: int = 0
    updated_time: int = 0
    timestamp: float = field(default_factory=time.time)
    
    # ===== Risk Management Fields =====
    # Margin metrics
    position_im: float = 0.0  # Initial margin for this position
    position_mm: float = 0.0  # Maintenance margin for this position
    
    # Position status
    position_status: str = "Normal"  # "Normal", "Liq" (liquidating), "Adl" (auto-deleveraging)
    adl_rank_indicator: int = 0  # ADL rank (0-5, higher = more risk of being ADL'd)
    is_reduce_only: bool = False  # True when only position reduction is allowed
    
    # Risk tier info
    risk_id: int = 0  # Risk tier ID
    risk_limit_value: str = ""  # Risk limit value
    
    # Realized PnL
    cur_realized_pnl: float = 0.0  # Realized PnL for current holding
    cum_realized_pnl: float = 0.0  # Cumulative realized PnL
    
    # Session info (USDC contracts)
    session_avg_price: float = 0.0  # Session average price
    
    # Category
    category: str = "linear"  # "linear", "inverse", "option"
    
    @classmethod
    def from_bybit(cls, data: dict) -> 'PositionData':
        """Parse from Bybit WebSocket position message."""
        size = float(data.get("size", 0))
        
        # Parse leverage - may be empty string for portfolio margin
        leverage_str = data.get("leverage", "1")
        leverage = float(leverage_str) if leverage_str else 1.0
        
        # Parse margin values - may be empty for portfolio margin
        position_im_str = data.get("positionIM", "0")
        position_mm_str = data.get("positionMM", "0")
        position_im = float(position_im_str) if position_im_str else 0.0
        position_mm = float(position_mm_str) if position_mm_str else 0.0
        
        return cls(
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            size=size,
            entry_price=float(data.get("entryPrice", 0)),
            mark_price=float(data.get("markPrice", 0)),
            unrealized_pnl=float(data.get("unrealisedPnl", 0)),
            leverage=leverage,
            position_value=float(data.get("positionValue", 0)),
            liq_price=float(data.get("liqPrice", 0) or 0),
            take_profit=float(data.get("takeProfit", 0) or 0),
            stop_loss=float(data.get("stopLoss", 0) or 0),
            trailing_stop=float(data.get("trailingStop", 0) or 0),
            position_idx=int(data.get("positionIdx", 0)),
            created_time=int(data.get("createdTime", 0)),
            updated_time=int(data.get("updatedTime", 0)),
            timestamp=time.time(),
            # Risk fields
            position_im=position_im,
            position_mm=position_mm,
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
        """Check if position is in liquidation."""
        return self.position_status == "Liq"
    
    @property
    def is_adl(self) -> bool:
        """Check if position is being auto-deleveraged."""
        return self.position_status == "Adl"
    
    @property
    def pnl_percent(self) -> float:
        """PnL as percentage of position value."""
        if self.position_value:
            return (self.unrealized_pnl / self.position_value) * 100
        return 0
    
    @property
    def liq_distance_abs(self) -> float:
        """Absolute distance to liquidation price."""
        if not self.liq_price or not self.mark_price:
            return float('inf')
        return abs(self.mark_price - self.liq_price)
    
    @property
    def liq_distance_pct(self) -> float:
        """Distance to liquidation as percentage of mark price."""
        if not self.mark_price or not self.liq_price:
            return float('inf')
        return (self.liq_distance_abs / self.mark_price) * 100
    
    @property
    def margin_usage_pct(self) -> float:
        """Position margin usage (IM / position_value)."""
        if self.position_value and self.position_im:
            return (self.position_im / self.position_value) * 100
        return 0
    
    @property
    def is_high_risk(self) -> bool:
        """Check if position is in a high-risk state."""
        return (
            self.position_status != "Normal" or
            self.adl_rank_indicator >= 4 or
            self.is_reduce_only or
            self.liq_distance_pct < 5.0  # Within 5% of liquidation
        )
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "size": self.size,
            "entry_price": self.entry_price,
            "mark_price": self.mark_price,
            "unrealized_pnl": self.unrealized_pnl,
            "pnl_percent": self.pnl_percent,
            "leverage": self.leverage,
            "position_value": self.position_value,
            "liq_price": self.liq_price,
            "liq_distance_pct": self.liq_distance_pct,
            "take_profit": self.take_profit,
            "stop_loss": self.stop_loss,
            # Risk fields
            "position_im": self.position_im,
            "position_mm": self.position_mm,
            "position_status": self.position_status,
            "adl_rank_indicator": self.adl_rank_indicator,
            "is_reduce_only": self.is_reduce_only,
            "is_high_risk": self.is_high_risk,
            "category": self.category,
            "timestamp": self.timestamp,
        }


@dataclass
class OrderData:
    """
    Normalized order data.
    """
    order_id: str
    symbol: str
    side: str  # "Buy" or "Sell"
    order_type: str  # "Market", "Limit"
    price: float
    qty: float
    filled_qty: float = 0.0
    status: str = ""  # "New", "PartiallyFilled", "Filled", "Cancelled", etc.
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
        """Parse from Bybit WebSocket order message."""
        # Helper to safely convert to float (handles empty strings)
        def safe_float(val, default=0.0):
            if val == "" or val is None:
                return default
            return float(val)
        
        def safe_int(val, default=0):
            if val == "" or val is None:
                return default
            return int(val)
        
        return cls(
            order_id=data.get("orderId", ""),
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            order_type=data.get("orderType", ""),
            price=safe_float(data.get("price")),
            qty=safe_float(data.get("qty")),
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
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "price": self.price,
            "qty": self.qty,
            "filled_qty": self.filled_qty,
            "status": self.status,
            "take_profit": self.take_profit,
            "stop_loss": self.stop_loss,
            "timestamp": self.timestamp,
        }


@dataclass
class ExecutionData:
    """
    Normalized trade execution data.
    """
    exec_id: str
    order_id: str
    symbol: str
    side: str
    price: float
    qty: float
    exec_type: str = ""  # "Trade", "Funding", etc.
    exec_fee: float = 0.0
    fee_rate: float = 0.0
    is_maker: bool = False
    order_link_id: str = ""
    exec_time: int = 0
    timestamp: float = field(default_factory=time.time)
    
    @classmethod
    def from_bybit(cls, data: dict) -> 'ExecutionData':
        """Parse from Bybit WebSocket execution message."""
        # Helper to safely convert to float (handles empty strings)
        def safe_float(val, default=0.0):
            if val == "" or val is None:
                return default
            return float(val)
        
        def safe_int(val, default=0):
            if val == "" or val is None:
                return default
            return int(val)
        
        return cls(
            exec_id=data.get("execId", ""),
            order_id=data.get("orderId", ""),
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            price=safe_float(data.get("execPrice")),
            qty=safe_float(data.get("execQty")),
            exec_type=data.get("execType", ""),
            exec_fee=safe_float(data.get("execFee")),
            fee_rate=safe_float(data.get("feeRate")),
            is_maker=data.get("isMaker", False),
            order_link_id=data.get("orderLinkId", ""),
            exec_time=safe_int(data.get("execTime")),
            timestamp=time.time(),
        )
    
    def to_dict(self) -> dict:
        return {
            "exec_id": self.exec_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "price": self.price,
            "qty": self.qty,
            "exec_type": self.exec_type,
            "exec_fee": self.exec_fee,
            "is_maker": self.is_maker,
            "timestamp": self.timestamp,
        }


@dataclass
class WalletData:
    """
    Normalized per-coin wallet/balance data.
    
    Each coin in the unified account has its own balance and margin info.
    For account-level unified margin metrics, see AccountMetrics.
    """
    coin: str
    equity: float
    wallet_balance: float
    available_balance: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    margin_balance: float = 0.0
    position_margin: float = 0.0
    order_margin: float = 0.0
    
    # Additional per-coin fields
    usd_value: float = 0.0  # USD value of this coin
    locked: float = 0.0  # Locked balance (spot orders)
    borrow_amount: float = 0.0  # Borrowed amount
    accrued_interest: float = 0.0  # Accrued interest
    total_order_im: float = 0.0  # Order initial margin
    total_position_im: float = 0.0  # Position initial margin
    total_position_mm: float = 0.0  # Position maintenance margin
    bonus: float = 0.0  # Bonus balance
    collateral_switch: bool = True  # Can be used as collateral
    margin_collateral: bool = True  # Collateral enabled by user
    
    timestamp: float = field(default_factory=time.time)
    
    @classmethod
    def from_bybit(cls, data: dict) -> 'WalletData':
        """Parse from Bybit WebSocket wallet message (per-coin data)."""
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
            "coin": self.coin,
            "equity": self.equity,
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
    """
    Unified account-level metrics for risk management.
    
    These are account-wide values from the wallet stream that represent
    the overall health and risk state of the unified trading account.
    
    Key metrics:
    - accountIMRate: Account-wide initial margin rate (0-1, higher = more margin used)
    - accountMMRate: Account-wide maintenance margin rate (0-1, higher = closer to liq)
    - totalEquity: Total account equity in USD
    - totalAvailableBalance: Available for trading/withdrawal
    - totalInitialMargin: Total margin used by positions
    - totalMaintenanceMargin: Minimum margin to avoid liquidation
    """
    account_type: str = "UNIFIED"  # "UNIFIED", "CONTRACT", etc.
    
    # ===== Core Margin Rates (0-1 scale) =====
    account_im_rate: float = 0.0  # Account initial margin rate
    account_mm_rate: float = 0.0  # Account maintenance margin rate
    
    # ===== Account Totals (USD) =====
    total_equity: float = 0.0  # Total equity (sum of all coin equity)
    total_wallet_balance: float = 0.0  # Total wallet balance
    total_margin_balance: float = 0.0  # Margin balance (wallet + unrealized PnL)
    total_available_balance: float = 0.0  # Available for trading/withdrawal
    total_perp_upl: float = 0.0  # Total unrealized PnL from perps/futures
    total_initial_margin: float = 0.0  # Total initial margin across positions
    total_maintenance_margin: float = 0.0  # Total maintenance margin
    
    timestamp: float = field(default_factory=time.time)
    
    @classmethod
    def from_bybit(cls, data: dict) -> 'AccountMetrics':
        """
        Parse from Bybit wallet API response or WebSocket.
        
        Note: Bybit demo API returns empty strings for many fields.
        We handle this by using fallbacks where appropriate.
        """
        # Parse with fallbacks for demo account empty strings
        total_equity = float(data.get("totalEquity", 0) or 0)
        total_wallet_balance = float(data.get("totalWalletBalance", 0) or 0)
        total_margin_balance = float(data.get("totalMarginBalance", 0) or 0)
        total_available_balance = float(data.get("totalAvailableBalance", 0) or 0)
        total_initial_margin = float(data.get("totalInitialMargin", 0) or 0)
        total_order_margin = float(data.get("totalOrderMargin", 0) or 0)
        
        # Bybit demo API returns empty strings for some fields
        # Calculate available balance if missing: wallet - margin used
        if total_available_balance == 0 and total_wallet_balance > 0:
            # Available = wallet balance - initial margin - order margin
            # If order margin not provided, just subtract initial margin
            margin_used = total_initial_margin + total_order_margin
            calculated_available = total_wallet_balance - margin_used
            # Use calculated value, but ensure non-negative
            total_available_balance = max(0.0, calculated_available)
            # If calculated is negative or zero but we have wallet balance, use wallet as fallback
            # (this handles cases where margin calculation might be off)
            if total_available_balance == 0 and total_initial_margin == 0:
                total_available_balance = total_wallet_balance
        
        # Use wallet balance as margin balance if margin is empty
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
        """Margin utilization percentage (IM / margin_balance)."""
        if self.total_margin_balance:
            return (self.total_initial_margin / self.total_margin_balance) * 100
        return 0
    
    @property
    def risk_buffer(self) -> float:
        """Buffer before maintenance margin (margin_balance - MM)."""
        return self.total_margin_balance - self.total_maintenance_margin
    
    @property
    def risk_buffer_pct(self) -> float:
        """Risk buffer as percentage of margin balance."""
        if self.total_margin_balance > 0:
            return (self.risk_buffer / self.total_margin_balance) * 100
        # No margin balance = no risk (no positions)
        return 100.0
    
    @property
    def max_additional_margin(self) -> float:
        """How much more margin can be used."""
        return self.total_available_balance
    
    @property
    def is_high_risk(self) -> bool:
        """
        Check if account is in a high-risk state.
        
        Returns True if:
        - MM rate > 80% (close to liquidation)
        - Risk buffer < 10% (little room before liquidation)
        
        Note: If no positions, account is NOT high risk.
        """
        # No positions = no risk
        if self.total_maintenance_margin == 0:
            return False
        
        return (
            self.account_mm_rate > 0.8 or  # MM rate > 80%
            self.risk_buffer_pct < 10  # Less than 10% buffer
        )
    
    @property
    def liquidation_risk_level(self) -> str:
        """Get liquidation risk level as a string."""
        if self.account_mm_rate > 0.9:
            return "CRITICAL"
        elif self.account_mm_rate > 0.7:
            return "HIGH"
        elif self.account_mm_rate > 0.5:
            return "MEDIUM"
        else:
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
    """
    Aggregated portfolio risk snapshot.
    
    This is a read-only, point-in-time view of the entire portfolio risk state.
    It aggregates data from AccountMetrics, all positions, and computed risk
    metrics into a single, comprehensive snapshot.
    
    Use this for:
    - Pre-trade risk checks
    - Risk agent decision making
    - CLI risk displays
    - Alerting on risk thresholds
    
    This structure is designed to be:
    - JSON-serializable for agent consumption
    - Independent of WebSocket/REST details
    - Cacheable with timestamp for staleness detection
    """
    timestamp: float = field(default_factory=time.time)
    
    # ===== Account-Level Metrics =====
    account_type: str = "UNIFIED"
    account_im_rate: float = 0.0  # Account initial margin rate
    account_mm_rate: float = 0.0  # Account maintenance margin rate
    total_equity: float = 0.0
    total_wallet_balance: float = 0.0
    total_margin_balance: float = 0.0
    total_available_balance: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_realized_pnl: float = 0.0  # Session realized
    
    # ===== Portfolio-Level Metrics =====
    total_notional_usd: float = 0.0  # Sum of all position values
    total_position_count: int = 0
    long_exposure_usd: float = 0.0  # Sum of long position values
    short_exposure_usd: float = 0.0  # Sum of short position values
    net_exposure_usd: float = 0.0  # Long - Short
    
    # Computed risk metrics
    weighted_leverage: float = 0.0  # Position-weighted average leverage
    worst_liq_distance_pct: float = float('inf')  # Closest to liquidation
    worst_liq_symbol: str = ""  # Symbol closest to liquidation
    max_position_leverage: float = 0.0  # Highest leverage among positions
    max_leverage_symbol: str = ""  # Symbol with highest leverage
    
    # Per-asset exposure (top assets)
    exposure_by_asset: Dict[str, float] = field(default_factory=dict)  # {underlying: USD exposure}
    
    # Position summary
    high_risk_position_count: int = 0  # Positions in Liq/Adl or reduce-only
    positions_near_liq: int = 0  # Positions within X% of liquidation
    
    # ===== Risk Status Flags =====
    is_account_high_risk: bool = False  # Account-level high risk
    has_liquidating_positions: bool = False  # Any position being liquidated
    has_adl_positions: bool = False  # Any position being auto-deleveraged
    has_reduce_only_positions: bool = False  # Any position in reduce-only mode
    
    # Risk level summary
    liquidation_risk_level: str = "LOW"  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    
    @classmethod
    def from_state(
        cls,
        account_metrics: Optional['AccountMetrics'],
        positions: Dict[str, 'PositionData'],
        config: Any = None,  # Optional config for thresholds
    ) -> 'PortfolioRiskSnapshot':
        """
        Build a snapshot from current state.
        
        Args:
            account_metrics: Current unified account metrics
            positions: All current positions
            config: Optional config for risk thresholds
        """
        snapshot = cls()
        
        # Account-level metrics
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
        
        # Position aggregation
        exposure_by_asset: Dict[str, float] = {}
        total_leverage_weighted = 0.0
        total_realized_pnl = 0.0
        
        for symbol, pos in positions.items():
            if not pos.is_open:
                continue
            
            snapshot.total_position_count += 1
            snapshot.total_notional_usd += pos.position_value
            
            # Long/short exposure
            if pos.is_long:
                snapshot.long_exposure_usd += pos.position_value
            else:
                snapshot.short_exposure_usd += pos.position_value
            
            # Track leverage
            total_leverage_weighted += pos.leverage * pos.position_value
            if pos.leverage > snapshot.max_position_leverage:
                snapshot.max_position_leverage = pos.leverage
                snapshot.max_leverage_symbol = symbol
            
            # Track liquidation distance
            liq_dist = pos.liq_distance_pct
            if liq_dist < snapshot.worst_liq_distance_pct:
                snapshot.worst_liq_distance_pct = liq_dist
                snapshot.worst_liq_symbol = symbol
            
            # Count positions near liquidation (< 10% buffer)
            if liq_dist < 10.0:
                snapshot.positions_near_liq += 1
            
            # Risk flags
            if pos.is_high_risk:
                snapshot.high_risk_position_count += 1
            if pos.is_liquidating:
                snapshot.has_liquidating_positions = True
            if pos.is_adl:
                snapshot.has_adl_positions = True
            if pos.is_reduce_only:
                snapshot.has_reduce_only_positions = True
            
            # Track realized PnL
            total_realized_pnl += pos.cum_realized_pnl
            
            # Exposure by underlying (extract base from symbol, e.g., BTC from BTCUSDT)
            underlying = symbol.replace("USDT", "").replace("USD", "").replace("PERP", "")
            exposure_by_asset[underlying] = exposure_by_asset.get(underlying, 0) + pos.position_value
        
        # Finalize computed metrics
        snapshot.net_exposure_usd = snapshot.long_exposure_usd - snapshot.short_exposure_usd
        snapshot.total_realized_pnl = total_realized_pnl
        
        if snapshot.total_notional_usd > 0:
            snapshot.weighted_leverage = total_leverage_weighted / snapshot.total_notional_usd
        
        # Sort exposure by asset (descending) and keep top 5
        sorted_exposure = sorted(exposure_by_asset.items(), key=lambda x: x[1], reverse=True)[:5]
        snapshot.exposure_by_asset = dict(sorted_exposure)
        
        # Overall risk level (combine account and position risks)
        if snapshot.has_liquidating_positions or account_metrics and account_metrics.account_mm_rate > 0.9:
            snapshot.liquidation_risk_level = "CRITICAL"
        elif snapshot.has_adl_positions or snapshot.positions_near_liq > 0:
            snapshot.liquidation_risk_level = "HIGH"
        elif snapshot.high_risk_position_count > 0 or account_metrics and account_metrics.account_mm_rate > 0.5:
            snapshot.liquidation_risk_level = "MEDIUM"
        else:
            snapshot.liquidation_risk_level = "LOW"
        
        return snapshot
    
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict for agent consumption."""
        return {
            "timestamp": self.timestamp,
            # Account
            "account_type": self.account_type,
            "account_im_rate": self.account_im_rate,
            "account_mm_rate": self.account_mm_rate,
            "total_equity": self.total_equity,
            "total_wallet_balance": self.total_wallet_balance,
            "total_margin_balance": self.total_margin_balance,
            "total_available_balance": self.total_available_balance,
            "total_unrealized_pnl": self.total_unrealized_pnl,
            "total_realized_pnl": self.total_realized_pnl,
            # Portfolio
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
            # Risk flags
            "high_risk_position_count": self.high_risk_position_count,
            "positions_near_liq": self.positions_near_liq,
            "is_account_high_risk": self.is_account_high_risk,
            "has_liquidating_positions": self.has_liquidating_positions,
            "has_adl_positions": self.has_adl_positions,
            "has_reduce_only_positions": self.has_reduce_only_positions,
            "liquidation_risk_level": self.liquidation_risk_level,
        }


# ==============================================================================
# Event Wrapper
# ==============================================================================

@dataclass
class RealtimeEvent:
    """
    Wrapper for real-time events.
    
    Used for event-driven processing and the event queue.
    """
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


# ==============================================================================
# Connection Status
# ==============================================================================

@dataclass
class ConnectionStatus:
    """WebSocket connection status."""
    state: ConnectionState = ConnectionState.DISCONNECTED
    connected_at: Optional[float] = None
    disconnected_at: Optional[float] = None
    reconnect_count: int = 0
    last_error: Optional[str] = None
    last_message_at: Optional[float] = None
    
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
            "state": self.state.value,
            "connected_at": self.connected_at,
            "uptime_seconds": self.uptime_seconds,
            "reconnect_count": self.reconnect_count,
            "last_error": self.last_error,
            "last_message_at": self.last_message_at,
        }


# ==============================================================================
# RealtimeState - Central State Manager
# ==============================================================================

class RealtimeState:
    """
    Thread-safe centralized state manager for real-time data.
    
    This is the single source of truth for all WebSocket-delivered data.
    It provides:
    - Thread-safe read/write access to all state
    - Staleness detection for all data types
    - Event queue for event-driven processing
    - Connection status tracking
    - Callbacks for state changes
    
    Usage:
        state = RealtimeState()
        
        # Update from WebSocket callback
        state.update_ticker(TickerData.from_bybit(msg["data"]))
        
        # Read current state
        ticker = state.get_ticker("BTCUSDT")
        
        # Check staleness
        if state.is_ticker_stale("BTCUSDT"):
            # Fall back to REST
            pass
        
        # Register callbacks
        state.on_ticker_update(lambda t: print(f"New price: {t.last_price}"))
    """
    
    def __init__(self, enable_event_queue: bool = True):
        """
        Initialize realtime state manager.
        
        Args:
            enable_event_queue: Enable event queue for event-driven processing
        """
        self.logger = get_logger()
        
        # Locks for thread-safety
        self._lock = threading.RLock()
        self._callback_lock = threading.Lock()
        
        # Public market data state
        self._tickers: Dict[str, TickerData] = {}
        self._orderbooks: Dict[str, OrderbookData] = {}
        self._klines: Dict[str, Dict[str, KlineData]] = defaultdict(dict)  # {symbol: {interval: kline}}
        self._recent_trades: Dict[str, List[TradeData]] = defaultdict(list)  # Keep last N trades
        
        # Private account data state
        self._positions: Dict[str, PositionData] = {}  # {symbol: position}
        self._orders: Dict[str, OrderData] = {}  # {order_id: order}
        self._executions: List[ExecutionData] = []  # Recent executions
        self._wallet: Dict[str, WalletData] = {}  # {coin: wallet}
        self._account_metrics: Optional[AccountMetrics] = None  # Unified account-level metrics
        
        # Connection status
        self._public_ws_status = ConnectionStatus()
        self._private_ws_status = ConnectionStatus()
        
        # Event queue for event-driven processing
        self._event_queue_enabled = enable_event_queue
        self._event_queue: Queue = Queue() if enable_event_queue else None
        
        # Callbacks
        self._ticker_callbacks: List[Callable[[TickerData], None]] = []
        self._orderbook_callbacks: List[Callable[[OrderbookData], None]] = []
        self._trade_callbacks: List[Callable[[TradeData], None]] = []
        self._kline_callbacks: List[Callable[[KlineData], None]] = []
        self._position_callbacks: List[Callable[[PositionData], None]] = []
        self._order_callbacks: List[Callable[[OrderData], None]] = []
        self._execution_callbacks: List[Callable[[ExecutionData], None]] = []
        self._wallet_callbacks: List[Callable[[WalletData], None]] = []
        self._account_metrics_callbacks: List[Callable[[AccountMetrics], None]] = []
        
        # Stats
        self._update_counts: Dict[str, int] = defaultdict(int)
        self._started_at = time.time()
        
        # Configuration
        self._max_recent_trades = 100
        self._max_executions = 500
    
    # ==========================================================================
    # Public Data - Tickers
    # ==========================================================================
    
    def update_ticker(self, ticker: TickerData):
        """Update ticker state (thread-safe)."""
        with self._lock:
            self._tickers[ticker.symbol] = ticker
            self._update_counts["ticker"] += 1
        
        self._emit_event(EventType.TICKER_UPDATE, ticker, ticker.symbol)
        self._invoke_callbacks(self._ticker_callbacks, ticker)
    
    def get_ticker(self, symbol: str) -> Optional[TickerData]:
        """Get ticker for a symbol (thread-safe)."""
        with self._lock:
            return self._tickers.get(symbol)
    
    def get_all_tickers(self) -> Dict[str, TickerData]:
        """Get all tickers (thread-safe copy)."""
        with self._lock:
            return dict(self._tickers)
    
    def is_ticker_stale(self, symbol: str, max_age_seconds: float = None) -> bool:
        """Check if ticker is stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["ticker"]
        with self._lock:
            ticker = self._tickers.get(symbol)
            if not ticker:
                return True
            return (time.time() - ticker.timestamp) > max_age
    
    def on_ticker_update(self, callback: Callable[[TickerData], None]):
        """Register callback for ticker updates."""
        with self._callback_lock:
            self._ticker_callbacks.append(callback)
    
    # ==========================================================================
    # Public Data - Orderbooks
    # ==========================================================================
    
    def update_orderbook(self, orderbook: OrderbookData, is_snapshot: bool = True):
        """Update orderbook state (thread-safe)."""
        with self._lock:
            if is_snapshot:
                self._orderbooks[orderbook.symbol] = orderbook
            else:
                # Apply delta to existing orderbook
                existing = self._orderbooks.get(orderbook.symbol)
                if existing:
                    existing.apply_delta({
                        "b": [[l.price, l.size] for l in orderbook.bids],
                        "a": [[l.price, l.size] for l in orderbook.asks],
                        "u": orderbook.update_id,
                    })
                else:
                    self._orderbooks[orderbook.symbol] = orderbook
            
            self._update_counts["orderbook"] += 1
        
        event_type = EventType.ORDERBOOK_SNAPSHOT if is_snapshot else EventType.ORDERBOOK_DELTA
        self._emit_event(event_type, orderbook, orderbook.symbol)
        self._invoke_callbacks(self._orderbook_callbacks, self._orderbooks.get(orderbook.symbol))
    
    def apply_orderbook_delta(self, symbol: str, delta: dict):
        """Apply delta update to orderbook."""
        with self._lock:
            existing = self._orderbooks.get(symbol)
            if existing:
                existing.apply_delta(delta)
                self._update_counts["orderbook"] += 1
                self._emit_event(EventType.ORDERBOOK_DELTA, existing, symbol)
                self._invoke_callbacks(self._orderbook_callbacks, existing)
    
    def get_orderbook(self, symbol: str) -> Optional[OrderbookData]:
        """Get orderbook for a symbol (thread-safe)."""
        with self._lock:
            return self._orderbooks.get(symbol)
    
    def is_orderbook_stale(self, symbol: str, max_age_seconds: float = None) -> bool:
        """Check if orderbook is stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["orderbook"]
        with self._lock:
            ob = self._orderbooks.get(symbol)
            if not ob:
                return True
            return (time.time() - ob.timestamp) > max_age
    
    def on_orderbook_update(self, callback: Callable[[OrderbookData], None]):
        """Register callback for orderbook updates."""
        with self._callback_lock:
            self._orderbook_callbacks.append(callback)
    
    # ==========================================================================
    # Public Data - Klines
    # ==========================================================================
    
    def update_kline(self, kline: KlineData):
        """Update kline state (thread-safe)."""
        with self._lock:
            self._klines[kline.symbol][kline.interval] = kline
            self._update_counts["kline"] += 1
        
        event_type = EventType.KLINE_CLOSED if kline.is_closed else EventType.KLINE_UPDATE
        self._emit_event(event_type, kline, kline.symbol)
        self._invoke_callbacks(self._kline_callbacks, kline)
    
    def get_kline(self, symbol: str, interval: str) -> Optional[KlineData]:
        """Get latest kline for symbol and interval."""
        with self._lock:
            return self._klines.get(symbol, {}).get(interval)
    
    def get_all_klines(self, symbol: str) -> Dict[str, KlineData]:
        """Get all klines for a symbol."""
        with self._lock:
            return dict(self._klines.get(symbol, {}))
    
    def is_kline_stale(self, symbol: str, interval: str, max_age_seconds: float = None) -> bool:
        """Check if kline is stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["kline"]
        with self._lock:
            kline = self._klines.get(symbol, {}).get(interval)
            if not kline:
                return True
            return (time.time() - kline.timestamp) > max_age
    
    def on_kline_update(self, callback: Callable[[KlineData], None]):
        """Register callback for kline updates."""
        with self._callback_lock:
            self._kline_callbacks.append(callback)
    
    # ==========================================================================
    # Public Data - Trades
    # ==========================================================================
    
    def add_trade(self, trade: TradeData):
        """Add a public trade (thread-safe)."""
        with self._lock:
            trades = self._recent_trades[trade.symbol]
            trades.append(trade)
            # Keep only recent trades
            if len(trades) > self._max_recent_trades:
                self._recent_trades[trade.symbol] = trades[-self._max_recent_trades:]
            self._update_counts["trade"] += 1
        
        self._emit_event(EventType.TRADE, trade, trade.symbol)
        self._invoke_callbacks(self._trade_callbacks, trade)
    
    def get_recent_trades(self, symbol: str, limit: int = 50) -> List[TradeData]:
        """Get recent trades for a symbol."""
        with self._lock:
            trades = self._recent_trades.get(symbol, [])
            return list(trades[-limit:])
    
    def on_trade(self, callback: Callable[[TradeData], None]):
        """Register callback for trades."""
        with self._callback_lock:
            self._trade_callbacks.append(callback)
    
    # ==========================================================================
    # Private Data - Positions
    # ==========================================================================
    
    def update_position(self, position: PositionData):
        """Update position state (thread-safe)."""
        with self._lock:
            if position.is_open:
                self._positions[position.symbol] = position
            else:
                # Remove closed positions
                self._positions.pop(position.symbol, None)
            self._update_counts["position"] += 1
        
        self._emit_event(EventType.POSITION_UPDATE, position, position.symbol)
        self._invoke_callbacks(self._position_callbacks, position)
    
    def get_position(self, symbol: str) -> Optional[PositionData]:
        """Get position for a symbol."""
        with self._lock:
            return self._positions.get(symbol)
    
    def get_all_positions(self) -> Dict[str, PositionData]:
        """Get all open positions."""
        with self._lock:
            return dict(self._positions)
    
    def is_position_stale(self, symbol: str, max_age_seconds: float = None) -> bool:
        """Check if position data is stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["position"]
        with self._lock:
            pos = self._positions.get(symbol)
            if not pos:
                return True
            return (time.time() - pos.timestamp) > max_age
    
    def on_position_update(self, callback: Callable[[PositionData], None]):
        """Register callback for position updates."""
        with self._callback_lock:
            self._position_callbacks.append(callback)
    
    # ==========================================================================
    # Private Data - Orders
    # ==========================================================================
    
    def update_order(self, order: OrderData):
        """Update order state (thread-safe)."""
        with self._lock:
            if order.is_open:
                self._orders[order.order_id] = order
            else:
                # Remove completed/cancelled orders from active list
                self._orders.pop(order.order_id, None)
            self._update_counts["order"] += 1
        
        self._emit_event(EventType.ORDER_UPDATE, order, order.symbol)
        self._invoke_callbacks(self._order_callbacks, order)
    
    def get_order(self, order_id: str) -> Optional[OrderData]:
        """Get order by ID."""
        with self._lock:
            return self._orders.get(order_id)
    
    def get_open_orders(self, symbol: str = None) -> List[OrderData]:
        """Get open orders, optionally filtered by symbol."""
        with self._lock:
            orders = list(self._orders.values())
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            return orders
    
    def on_order_update(self, callback: Callable[[OrderData], None]):
        """Register callback for order updates."""
        with self._callback_lock:
            self._order_callbacks.append(callback)
    
    # ==========================================================================
    # Private Data - Executions
    # ==========================================================================
    
    def add_execution(self, execution: ExecutionData):
        """Add an execution (thread-safe)."""
        with self._lock:
            self._executions.append(execution)
            if len(self._executions) > self._max_executions:
                self._executions = self._executions[-self._max_executions:]
            self._update_counts["execution"] += 1
        
        self._emit_event(EventType.EXECUTION, execution, execution.symbol)
        self._invoke_callbacks(self._execution_callbacks, execution)
    
    def get_recent_executions(self, symbol: str = None, limit: int = 50) -> List[ExecutionData]:
        """Get recent executions, optionally filtered by symbol."""
        with self._lock:
            execs = list(self._executions)
            if symbol:
                execs = [e for e in execs if e.symbol == symbol]
            return execs[-limit:]
    
    def on_execution(self, callback: Callable[[ExecutionData], None]):
        """Register callback for executions."""
        with self._callback_lock:
            self._execution_callbacks.append(callback)
    
    # ==========================================================================
    # Private Data - Wallet
    # ==========================================================================
    
    def update_wallet(self, wallet: WalletData):
        """Update wallet state (thread-safe)."""
        with self._lock:
            self._wallet[wallet.coin] = wallet
            self._update_counts["wallet"] += 1
        
        self._emit_event(EventType.WALLET_UPDATE, wallet, wallet.coin)
        self._invoke_callbacks(self._wallet_callbacks, wallet)
    
    def get_wallet(self, coin: str = "USDT") -> Optional[WalletData]:
        """Get wallet for a coin."""
        with self._lock:
            return self._wallet.get(coin)
    
    def get_all_wallets(self) -> Dict[str, WalletData]:
        """Get all wallet balances."""
        with self._lock:
            return dict(self._wallet)
    
    def is_wallet_stale(self, coin: str = "USDT", max_age_seconds: float = None) -> bool:
        """Check if wallet data is stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["wallet"]
        with self._lock:
            wallet = self._wallet.get(coin)
            if not wallet:
                return True
            return (time.time() - wallet.timestamp) > max_age
    
    def on_wallet_update(self, callback: Callable[[WalletData], None]):
        """Register callback for wallet updates."""
        with self._callback_lock:
            self._wallet_callbacks.append(callback)
    
    # ==========================================================================
    # Private Data - Account Metrics (Unified Account-Level)
    # ==========================================================================
    
    def update_account_metrics(self, metrics: AccountMetrics):
        """Update unified account metrics (thread-safe)."""
        with self._lock:
            self._account_metrics = metrics
            self._update_counts["account_metrics"] += 1
        
        self._emit_event(EventType.WALLET_UPDATE, metrics, "account")
        self._invoke_callbacks(self._account_metrics_callbacks, metrics)
    
    def get_account_metrics(self) -> Optional[AccountMetrics]:
        """Get unified account metrics."""
        with self._lock:
            return self._account_metrics
    
    def is_account_metrics_stale(self, max_age_seconds: float = None) -> bool:
        """Check if account metrics are stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["wallet"]  # Same threshold as wallet
        with self._lock:
            if not self._account_metrics:
                return True
            return (time.time() - self._account_metrics.timestamp) > max_age
    
    def on_account_metrics_update(self, callback: Callable[[AccountMetrics], None]):
        """Register callback for account metrics updates."""
        with self._callback_lock:
            self._account_metrics_callbacks.append(callback)
    
    # ==========================================================================
    # Connection Status
    # ==========================================================================
    
    def set_public_ws_connected(self):
        """Mark public WebSocket as connected."""
        self._public_ws_status.state = ConnectionState.CONNECTED
        self._public_ws_status.connected_at = time.time()
        self._emit_event(EventType.CONNECTED, {"stream": "public"})
    
    def set_public_ws_disconnected(self, error: str = None):
        """Mark public WebSocket as disconnected."""
        self._public_ws_status.state = ConnectionState.DISCONNECTED
        self._public_ws_status.disconnected_at = time.time()
        if error:
            self._public_ws_status.last_error = error
        self._emit_event(EventType.DISCONNECTED, {"stream": "public", "error": error})
    
    def set_public_ws_reconnecting(self):
        """Mark public WebSocket as reconnecting."""
        self._public_ws_status.state = ConnectionState.RECONNECTING
        self._public_ws_status.reconnect_count += 1
        self._emit_event(EventType.RECONNECTING, {"stream": "public"})
    
    def set_private_ws_connected(self):
        """Mark private WebSocket as connected."""
        self._private_ws_status.state = ConnectionState.CONNECTED
        self._private_ws_status.connected_at = time.time()
        self._emit_event(EventType.CONNECTED, {"stream": "private"})
    
    def set_private_ws_disconnected(self, error: str = None):
        """Mark private WebSocket as disconnected."""
        self._private_ws_status.state = ConnectionState.DISCONNECTED
        self._private_ws_status.disconnected_at = time.time()
        if error:
            self._private_ws_status.last_error = error
        self._emit_event(EventType.DISCONNECTED, {"stream": "private", "error": error})
    
    def set_private_ws_reconnecting(self):
        """Mark private WebSocket as reconnecting."""
        self._private_ws_status.state = ConnectionState.RECONNECTING
        self._private_ws_status.reconnect_count += 1
        self._emit_event(EventType.RECONNECTING, {"stream": "private"})
    
    def get_public_ws_status(self) -> ConnectionStatus:
        """Get public WebSocket status."""
        return self._public_ws_status
    
    def get_private_ws_status(self) -> ConnectionStatus:
        """Get private WebSocket status."""
        return self._private_ws_status
    
    @property
    def is_public_ws_connected(self) -> bool:
        return self._public_ws_status.is_connected
    
    @property
    def is_private_ws_connected(self) -> bool:
        return self._private_ws_status.is_connected
    
    # ==========================================================================
    # Event Queue
    # ==========================================================================
    
    def _emit_event(self, event_type: EventType, data: Any, symbol: str = ""):
        """Emit event to the queue if enabled."""
        if self._event_queue_enabled and self._event_queue:
            event = RealtimeEvent(
                event_type=event_type,
                data=data,
                symbol=symbol,
            )
            self._event_queue.put_nowait(event)
    
    def get_event(self, timeout: float = None) -> Optional[RealtimeEvent]:
        """
        Get next event from queue (blocking).
        
        Args:
            timeout: Timeout in seconds (None = block forever)
        
        Returns:
            RealtimeEvent or None if timeout
        """
        if not self._event_queue:
            return None
        try:
            return self._event_queue.get(timeout=timeout)
        except Empty:
            return None
    
    def get_event_nowait(self) -> Optional[RealtimeEvent]:
        """Get next event from queue (non-blocking)."""
        if not self._event_queue:
            return None
        try:
            return self._event_queue.get_nowait()
        except Empty:
            return None
    
    def event_queue_size(self) -> int:
        """Get current event queue size."""
        return self._event_queue.qsize() if self._event_queue else 0
    
    def clear_event_queue(self):
        """Clear all pending events."""
        if self._event_queue:
            while not self._event_queue.empty():
                try:
                    self._event_queue.get_nowait()
                except Empty:
                    break
    
    # ==========================================================================
    # Callbacks
    # ==========================================================================
    
    def _invoke_callbacks(self, callbacks: List[Callable], data: Any):
        """Invoke all registered callbacks."""
        for callback in callbacks:
            try:
                callback(data)
            except Exception as e:
                self.logger.error(f"Callback error: {e}")
    
    def clear_callbacks(self):
        """Clear all registered callbacks."""
        with self._callback_lock:
            self._ticker_callbacks.clear()
            self._orderbook_callbacks.clear()
            self._trade_callbacks.clear()
            self._kline_callbacks.clear()
            self._position_callbacks.clear()
            self._order_callbacks.clear()
            self._execution_callbacks.clear()
            self._wallet_callbacks.clear()
    
    # ==========================================================================
    # State Management
    # ==========================================================================
    
    def clear_all(self):
        """Clear all state data."""
        with self._lock:
            self._tickers.clear()
            self._orderbooks.clear()
            self._klines.clear()
            self._recent_trades.clear()
            self._positions.clear()
            self._orders.clear()
            self._executions.clear()
            self._wallet.clear()
            self._update_counts.clear()
        
        self.clear_event_queue()
        self.logger.info("RealtimeState cleared")
    
    def clear_market_data(self):
        """Clear only market data (public streams)."""
        with self._lock:
            self._tickers.clear()
            self._orderbooks.clear()
            self._klines.clear()
            self._recent_trades.clear()
    
    def clear_account_data(self):
        """Clear only account data (private streams)."""
        with self._lock:
            self._positions.clear()
            self._orders.clear()
            self._executions.clear()
            self._wallet.clear()
    
    # ==========================================================================
    # Portfolio Risk Snapshot
    # ==========================================================================
    
    def build_portfolio_snapshot(self, config: Any = None) -> PortfolioRiskSnapshot:
        """
        Build a comprehensive portfolio risk snapshot.
        
        This aggregates all position and account data into a single,
        point-in-time view suitable for risk analysis and agent consumption.
        
        Args:
            config: Optional config for risk thresholds
        
        Returns:
            PortfolioRiskSnapshot with all risk metrics computed
        """
        with self._lock:
            return PortfolioRiskSnapshot.from_state(
                account_metrics=self._account_metrics,
                positions=dict(self._positions),
                config=config,
            )
    
    # ==========================================================================
    # Statistics and Status
    # ==========================================================================
    
    def get_stats(self) -> dict:
        """Get state statistics."""
        with self._lock:
            return {
                "uptime_seconds": time.time() - self._started_at,
                "ticker_count": len(self._tickers),
                "orderbook_count": len(self._orderbooks),
                "position_count": len(self._positions),
                "open_order_count": len(self._orders),
                "execution_count": len(self._executions),
                "update_counts": dict(self._update_counts),
                "event_queue_size": self.event_queue_size(),
                "public_ws": self._public_ws_status.to_dict(),
                "private_ws": self._private_ws_status.to_dict(),
            }
    
    def get_summary(self) -> dict:
        """Get a summary of current state."""
        with self._lock:
            total_unrealized_pnl = sum(p.unrealized_pnl for p in self._positions.values())
            usdt_wallet = self._wallet.get("USDT")
            
            return {
                "connected": {
                    "public": self.is_public_ws_connected,
                    "private": self.is_private_ws_connected,
                },
                "market_data": {
                    "symbols_tracked": list(self._tickers.keys()),
                    "ticker_count": len(self._tickers),
                },
                "account": {
                    "positions": len(self._positions),
                    "open_orders": len(self._orders),
                    "unrealized_pnl": total_unrealized_pnl,
                    "balance": usdt_wallet.wallet_balance if usdt_wallet else 0,
                    "available": usdt_wallet.available_balance if usdt_wallet else 0,
                },
                "updates": dict(self._update_counts),
            }


# ==============================================================================
# Singleton Instance
# ==============================================================================

_realtime_state: Optional[RealtimeState] = None
_state_lock = threading.Lock()


def get_realtime_state() -> RealtimeState:
    """Get or create the global RealtimeState instance."""
    global _realtime_state
    with _state_lock:
        if _realtime_state is None:
            _realtime_state = RealtimeState()
        return _realtime_state


def reset_realtime_state():
    """Reset the global RealtimeState instance (for testing)."""
    global _realtime_state
    with _state_lock:
        if _realtime_state:
            _realtime_state.clear_all()
        _realtime_state = None

