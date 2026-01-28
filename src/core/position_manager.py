"""
Position tracking and management.

Provides normalized position snapshots for strategies and risk management.
Now supports HYBRID mode with WebSocket-fed real-time data.

Features:
- Real-time position snapshots from WebSocket
- Fallback to REST API
- Trade history tracking
- PnL calculation
- Performance metrics
"""

import threading
import time
from datetime import datetime
from dataclasses import dataclass, field

from .exchange_manager import ExchangeManager, Position
from ..utils.logger import get_logger


@dataclass
class PortfolioSnapshot:
    """Point-in-time portfolio state."""
    timestamp: datetime
    balance: float
    available: float
    total_exposure: float
    unrealized_pnl: float
    positions: list[Position]
    source: str = "rest"  # "rest" or "websocket"
    
    @property
    def position_count(self) -> int:
        return len(self.positions)
    
    @property
    def has_positions(self) -> bool:
        return len(self.positions) > 0
    
    def get_position(self, symbol: str) -> Position | None:
        """Get position for a specific symbol."""
        for pos in self.positions:
            if pos.symbol == symbol:
                return pos
        return None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "balance": self.balance,
            "available": self.available,
            "total_exposure": self.total_exposure,
            "unrealized_pnl": self.unrealized_pnl,
            "position_count": self.position_count,
            "source": self.source,
            "positions": [
                {
                    "symbol": p.symbol,
                    "side": p.side,
                    "size": p.size,
                    "size_usdt": p.size_usdt,
                    "entry_price": p.entry_price,
                    "current_price": p.current_price,
                    "pnl": p.unrealized_pnl,
                    "pnl_percent": p.unrealized_pnl_percent,
                    "leverage": p.leverage,
                }
                for p in self.positions
            ]
        }


@dataclass
class TradeRecord:
    """Record of a completed trade."""
    timestamp: datetime
    symbol: str
    side: str  # "BUY" or "SELL"
    size_usdt: float
    price: float
    realized_pnl: float | None = None
    fees: float = 0.0
    order_id: str | None = None
    strategy: str | None = None
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "symbol": self.symbol,
            "side": self.side,
            "size_usdt": self.size_usdt,
            "price": self.price,
            "realized_pnl": self.realized_pnl,
            "fees": self.fees,
            "order_id": self.order_id,
            "strategy": self.strategy,
        }


class PositionManager:
    """
    Position tracking and portfolio management with hybrid WebSocket/REST support.
    
    Features:
    - Real-time position snapshots from WebSocket when available
    - Fallback to REST API
    - Trade history tracking
    - PnL calculation
    - Performance metrics
    - Periodic reconciliation between WebSocket and REST
    
    Data Source Priority:
    1. RealtimeState (WebSocket-fed) - if available and not stale
    2. REST API via ExchangeManager - fallback
    """
    
    def __init__(
        self,
        exchange_manager: ExchangeManager,
        prefer_websocket: bool = True,
        staleness_threshold: float = 10.0,
    ):
        """
        Initialize position manager.
        
        Args:
            exchange_manager: ExchangeManager instance
            prefer_websocket: Whether to prefer WebSocket data
            staleness_threshold: Max age (seconds) for WebSocket data before fallback
        """
        self.exchange = exchange_manager
        self.logger = get_logger()
        
        # WebSocket preference
        self._prefer_websocket = prefer_websocket
        self._staleness_threshold = staleness_threshold
        
        # Lazy import to avoid circular dependency
        self._realtime_state = None
        
        # Trade history
        self._trades: list[TradeRecord] = []
        
        # Daily tracking
        self._daily_realized_pnl = 0.0
        self._daily_trades = 0
        self._last_reset_date = datetime.now().date()

        # Thread safety for trade recording
        self._trade_lock = threading.Lock()

        # Source tracking for diagnostics
        self._last_source = "rest"
        
        # Reconciliation tracking
        self._last_rest_sync = 0.0
        self._rest_sync_interval = 30.0  # Sync with REST every 30 seconds
    
    # ==================== WebSocket State Access ====================
    
    @property
    def realtime_state(self):
        """Get RealtimeState instance (lazy import to avoid circular dependency)."""
        if self._realtime_state is None:
            try:
                from ..data.realtime_state import get_realtime_state
                self._realtime_state = get_realtime_state()
            except ImportError:
                self._realtime_state = None
        return self._realtime_state
    
    def _has_fresh_ws_data(self) -> bool:
        """Check if we have fresh WebSocket position data."""
        if not self._prefer_websocket or not self.realtime_state:
            return False
        return self.realtime_state.is_private_ws_connected
    
    def _has_fresh_ws_wallet(self) -> bool:
        """Check if we have fresh WebSocket wallet data."""
        if not self._prefer_websocket or not self.realtime_state:
            return False
        return not self.realtime_state.is_wallet_stale("USDT", self._staleness_threshold)
    
    def set_prefer_websocket(self, prefer: bool):
        """Enable or disable WebSocket preference."""
        self._prefer_websocket = prefer
        self.logger.info(f"PositionManager WebSocket preference set to: {prefer}")
    
    # ==================== Core Position Methods ====================
    
    def _check_daily_reset(self):
        """Reset daily counters at midnight."""
        today = datetime.now().date()
        if today > self._last_reset_date:
            self._daily_realized_pnl = 0.0
            self._daily_trades = 0
            self._last_reset_date = today
    
    def get_snapshot(self) -> PortfolioSnapshot:
        """
        Get current portfolio snapshot.
        
        Uses WebSocket data if available and fresh, otherwise REST.
        
        Returns:
            PortfolioSnapshot with current state
        """
        # Try WebSocket first
        if self._has_fresh_ws_data():
            try:
                return self._get_snapshot_from_ws()
            except Exception as e:
                self.logger.warning(f"Failed to get WS snapshot: {e}, falling back to REST")
        
        # Fallback to REST
        return self._get_snapshot_from_rest()
    
    def _get_snapshot_from_ws(self) -> PortfolioSnapshot:
        """Get snapshot from WebSocket-fed RealtimeState."""
        self._last_source = "websocket"
        
        # Get positions from RealtimeState
        ws_positions = self.realtime_state.get_all_positions()
        
        # Convert to Position objects (matching ExchangeManager.Position format)
        positions = []
        total_exposure = 0.0
        unrealized_pnl = 0.0
        
        for symbol, ws_pos in ws_positions.items():
            if ws_pos.is_open:
                pos = Position(
                    symbol=ws_pos.symbol,
                    exchange="bybit",
                    position_type="futures",
                    side="long" if ws_pos.side.lower() == "buy" else "short",
                    size=ws_pos.size,
                    size_usdt=ws_pos.position_value,
                    entry_price=ws_pos.entry_price,
                    current_price=ws_pos.mark_price,
                    unrealized_pnl=ws_pos.unrealized_pnl,
                    unrealized_pnl_percent=ws_pos.pnl_percent,
                    leverage=int(ws_pos.leverage),
                    margin_mode="cross",
                    liquidation_price=ws_pos.liq_price,
                    take_profit=ws_pos.take_profit,
                    stop_loss=ws_pos.stop_loss,
                )
                positions.append(pos)
                total_exposure += ws_pos.position_value
                unrealized_pnl += ws_pos.unrealized_pnl
        
        # Get wallet from RealtimeState
        ws_wallet = self.realtime_state.get_wallet("USDT")
        
        if ws_wallet:
            balance = ws_wallet.wallet_balance
            available = ws_wallet.available_balance
        else:
            # Fall back to REST for wallet
            balance_info = self.exchange.get_balance()
            balance = balance_info.get("total", 0)
            available = balance_info.get("available", 0)
        
        return PortfolioSnapshot(
            timestamp=datetime.now(),
            balance=balance,
            available=available,
            total_exposure=total_exposure,
            unrealized_pnl=unrealized_pnl,
            positions=positions,
            source="websocket",
        )
    
    def _get_snapshot_from_rest(self) -> PortfolioSnapshot:
        """Get snapshot from REST API."""
        self._last_source = "rest"
        
        balance_info = self.exchange.get_balance()
        positions = self.exchange.get_all_positions()
        
        total_exposure = sum(p.size_usdt for p in positions)
        unrealized_pnl = sum(p.unrealized_pnl for p in positions)
        
        self._last_rest_sync = time.time()
        
        return PortfolioSnapshot(
            timestamp=datetime.now(),
            balance=balance_info.get("total", 0),
            available=balance_info.get("available", 0),
            total_exposure=total_exposure,
            unrealized_pnl=unrealized_pnl,
            positions=positions,
            source="rest",
        )
    
    def get_position(self, symbol: str) -> Position | None:
        """
        Get position for a specific symbol.

        Uses WebSocket data if available, otherwise REST.
        """
        # Try WebSocket first
        if self._has_fresh_ws_data():
            ws_pos = self.realtime_state.get_position(symbol)
            if ws_pos and ws_pos.is_open:
                self._last_source = "websocket"
                # G6.0.3-4: Use correct Position field names and add required fields
                return Position(
                    symbol=ws_pos.symbol,
                    exchange="bybit",
                    position_type="futures",
                    side="long" if ws_pos.side.lower() == "buy" else "short",
                    size=ws_pos.size,
                    size_usdt=ws_pos.position_value,
                    entry_price=ws_pos.entry_price,
                    current_price=ws_pos.mark_price,
                    unrealized_pnl=ws_pos.unrealized_pnl,
                    unrealized_pnl_percent=ws_pos.pnl_percent,
                    leverage=int(ws_pos.leverage),
                    margin_mode="cross",
                    liquidation_price=ws_pos.liq_price,
                    take_profit=ws_pos.take_profit,
                    stop_loss=ws_pos.stop_loss,
                )
        
        # Fallback to REST
        self._last_source = "rest"
        return self.exchange.get_position(symbol)
    
    def get_open_orders(self, symbol: str | None = None) -> list[dict]:
        """
        Get open orders.
        
        Uses WebSocket data if available, otherwise REST.
        """
        # Try WebSocket first
        if self._has_fresh_ws_data():
            ws_orders = self.realtime_state.get_open_orders(symbol)
            if ws_orders:
                self._last_source = "websocket"
                return [order.to_dict() for order in ws_orders]
        
        # Fallback to REST
        self._last_source = "rest"
        return self.exchange.bybit.get_open_orders(symbol=symbol)
    
    # ==================== Trade Recording ====================
    
    def record_trade(
        self,
        symbol: str,
        side: str,
        size_usdt: float,
        price: float,
        realized_pnl: float | None = None,
        fees: float = 0.0,
        order_id: str | None = None,
        strategy: str | None = None,
    ):
        """
        Record a completed trade.

        Args:
            symbol: Trading symbol
            side: BUY or SELL
            size_usdt: Trade size in USDT
            price: Execution price
            realized_pnl: Realized PnL (for closing trades)
            fees: Trading fees
            order_id: Exchange order ID
            strategy: Strategy that generated the trade
        """
        with self._trade_lock:
            self._check_daily_reset()

            trade = TradeRecord(
                timestamp=datetime.now(),
                symbol=symbol,
                side=side.upper(),
                size_usdt=size_usdt,
                price=price,
                realized_pnl=realized_pnl,
                fees=fees,
                order_id=order_id,
                strategy=strategy,
            )

            self._trades.append(trade)
            self._daily_trades += 1

            if realized_pnl is not None:
                self._daily_realized_pnl += realized_pnl

        self.logger.trade(
            "TRADE_RECORDED",
            symbol=symbol,
            side=side,
            size=size_usdt,
            price=price,
            pnl=realized_pnl,
        )

    def record_execution_from_ws(self, exec_data) -> TradeRecord | None:
        """
        Record a trade from WebSocket execution event.

        Args:
            exec_data: ExecutionData from RealtimeState

        Returns:
            TradeRecord if recorded, None otherwise
        """
        if not hasattr(exec_data, 'symbol'):
            return None

        # Calculate approximate USDT size
        size_usdt = exec_data.qty * exec_data.price

        self.record_trade(
            symbol=exec_data.symbol,
            side=exec_data.side,
            size_usdt=size_usdt,
            price=exec_data.price,
            fees=exec_data.exec_fee,
            order_id=exec_data.order_id,
        )

        with self._trade_lock:
            return self._trades[-1] if self._trades else None

    # ==================== Statistics ====================

    def get_daily_stats(self) -> dict:
        """Get daily trading statistics."""
        with self._trade_lock:
            self._check_daily_reset()
            return {
                "date": self._last_reset_date.isoformat(),
                "trades": self._daily_trades,
                "realized_pnl": self._daily_realized_pnl,
            }

    def get_trade_history(self, limit: int = 100) -> list[dict]:
        """Get recent trade history."""
        with self._trade_lock:
            trades = self._trades[-limit:] if limit else list(self._trades)
        return [t.to_dict() for t in trades]

    def get_performance_summary(self) -> dict:
        """
        Get overall performance summary.

        Returns:
            Dict with performance metrics
        """
        with self._trade_lock:
            if not self._trades:
                return {
                    "total_trades": 0,
                    "total_pnl": 0,
                    "win_count": 0,
                    "loss_count": 0,
                    "win_rate": 0,
                }

            # Calculate metrics (copy list for processing outside lock)
            trades_copy = list(self._trades)

        total_pnl = sum(t.realized_pnl or 0 for t in trades_copy)
        winning = [t for t in trades_copy if t.realized_pnl and t.realized_pnl > 0]
        losing = [t for t in trades_copy if t.realized_pnl and t.realized_pnl < 0]

        win_rate = len(winning) / len(trades_copy) * 100 if trades_copy else 0

        return {
            "total_trades": len(trades_copy),
            "total_pnl": total_pnl,
            "win_count": len(winning),
            "loss_count": len(losing),
            "win_rate": win_rate,
            "avg_win": sum(t.realized_pnl for t in winning) / len(winning) if winning else 0,
            "avg_loss": sum(t.realized_pnl for t in losing) / len(losing) if losing else 0,
        }
    
    # ==================== Reconciliation ====================
    
    def reconcile_with_rest(self) -> dict:
        """
        Reconcile WebSocket position data with REST API.
        
        This is useful for periodic verification and catching any
        missed WebSocket updates.
        
        Returns:
            Dict with reconciliation results
        """
        ws_snapshot = None
        rest_snapshot = None
        
        # Get WebSocket data
        if self._has_fresh_ws_data():
            try:
                ws_snapshot = self._get_snapshot_from_ws()
            except Exception as e:
                self.logger.warning(f"Failed to get WS snapshot for reconciliation: {e}")
        
        # Always get REST data for comparison
        rest_snapshot = self._get_snapshot_from_rest()
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "rest_positions": rest_snapshot.position_count,
            "rest_balance": rest_snapshot.balance,
            "ws_available": ws_snapshot is not None,
        }
        
        if ws_snapshot:
            result["ws_positions"] = ws_snapshot.position_count
            result["ws_balance"] = ws_snapshot.balance
            result["balance_diff"] = abs(ws_snapshot.balance - rest_snapshot.balance)
            result["position_count_diff"] = abs(
                ws_snapshot.position_count - rest_snapshot.position_count
            )
            
            # Check for significant discrepancies
            if result["balance_diff"] > 1.0:  # More than $1 difference
                self.logger.warning(
                    f"Balance discrepancy: WS={ws_snapshot.balance:.2f}, "
                    f"REST={rest_snapshot.balance:.2f}"
                )
            
            if result["position_count_diff"] > 0:
                self.logger.warning(
                    f"Position count discrepancy: WS={ws_snapshot.position_count}, "
                    f"REST={rest_snapshot.position_count}"
                )
        
        return result
    
    # ==================== Diagnostics ====================
    
    def get_data_source(self) -> str:
        """Get the data source used for last query."""
        return self._last_source
    
    def get_status(self) -> dict:
        """Get position manager status."""
        return {
            "prefer_websocket": self._prefer_websocket,
            "last_source": self._last_source,
            "ws_connected": (
                self.realtime_state.is_private_ws_connected
                if self.realtime_state else False
            ),
            "last_rest_sync": self._last_rest_sync,
            "daily_stats": self.get_daily_stats(),
            "trade_count": len(self._trades),
        }
