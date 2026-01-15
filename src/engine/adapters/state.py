"""
State storage adapters for PlayEngine.

Provides state persistence for engine recovery:
- InMemoryStateStore: Dict-based storage (backtest)
- FileStateStore: JSON file storage (live recovery)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..interfaces import EngineState, StateStore, Position, Order

from ...utils.logger import get_logger


logger = get_logger()


class InMemoryStateStore:
    """
    In-memory state storage for backtest mode.

    Simple dict-based storage. State is lost when process exits.
    """

    def __init__(self):
        self._states: dict[str, EngineState] = {}

    def save_state(self, engine_id: str, state: EngineState) -> None:
        """Save state to memory."""
        self._states[engine_id] = state

    def load_state(self, engine_id: str) -> EngineState | None:
        """Load state from memory."""
        return self._states.get(engine_id)

    def delete_state(self, engine_id: str) -> bool:
        """Delete state from memory."""
        if engine_id in self._states:
            del self._states[engine_id]
            return True
        return False

    def list_states(self) -> list[str]:
        """List all stored engine IDs."""
        return list(self._states.keys())

    def clear(self) -> None:
        """Clear all stored states."""
        self._states.clear()


class FileStateStore:
    """
    File-based state storage for live mode.

    Persists state to JSON files for crash recovery.
    Each engine gets its own file in the state directory.
    """

    def __init__(self, state_dir: Path | str | None = None):
        """
        Initialize file state store.

        Args:
            state_dir: Directory for state files (default: .trade/state)
        """
        if state_dir is None:
            state_dir = Path.home() / ".trade" / "state"
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _state_file(self, engine_id: str) -> Path:
        """Get state file path for engine."""
        # Sanitize engine_id for filename
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in engine_id)
        return self._state_dir / f"{safe_id}.json"

    def save_state(self, engine_id: str, state: EngineState) -> None:
        """Save state to file."""
        state_file = self._state_file(engine_id)

        # Convert to serializable dict
        state_dict = self._state_to_dict(state)

        # Write with newline for LF endings
        with open(state_file, "w", newline="\n") as f:
            json.dump(state_dict, f, indent=2, default=str)

        logger.debug(f"State saved: {state_file}")

    def load_state(self, engine_id: str) -> EngineState | None:
        """Load state from file."""
        state_file = self._state_file(engine_id)

        if not state_file.exists():
            return None

        try:
            with open(state_file) as f:
                state_dict = json.load(f)
            return self._dict_to_state(state_dict)
        except Exception as e:
            logger.warning(f"Failed to load state from {state_file}: {e}")
            return None

    def delete_state(self, engine_id: str) -> bool:
        """Delete state file."""
        state_file = self._state_file(engine_id)

        if state_file.exists():
            state_file.unlink()
            logger.debug(f"State deleted: {state_file}")
            return True
        return False

    def list_states(self) -> list[str]:
        """List all stored engine IDs."""
        states = []
        for state_file in self._state_dir.glob("*.json"):
            # Extract engine ID from filename
            states.append(state_file.stem)
        return states

    def _state_to_dict(self, state: EngineState) -> dict[str, Any]:
        """Convert EngineState to serializable dict."""
        d = {
            "engine_id": state.engine_id,
            "play_id": state.play_id,
            "mode": state.mode,
            "symbol": state.symbol,
            "position": self._position_to_dict(state.position) if state.position else None,
            "pending_orders": [self._order_to_dict(o) for o in state.pending_orders],
            "equity_usdt": state.equity_usdt,
            "realized_pnl": state.realized_pnl,
            "total_trades": state.total_trades,
            "last_bar_ts": state.last_bar_ts.isoformat() if state.last_bar_ts else None,
            "last_signal_ts": state.last_signal_ts.isoformat() if state.last_signal_ts else None,
            "incremental_state_json": state.incremental_state_json,
            "metadata": state.metadata,
        }
        return d

    def _dict_to_state(self, d: dict[str, Any]) -> EngineState:
        """Convert dict to EngineState."""
        return EngineState(
            engine_id=d["engine_id"],
            play_id=d["play_id"],
            mode=d["mode"],
            symbol=d["symbol"],
            position=self._dict_to_position(d["position"]) if d.get("position") else None,
            pending_orders=[self._dict_to_order(o) for o in d.get("pending_orders", [])],
            equity_usdt=d.get("equity_usdt", 0.0),
            realized_pnl=d.get("realized_pnl", 0.0),
            total_trades=d.get("total_trades", 0),
            last_bar_ts=datetime.fromisoformat(d["last_bar_ts"]) if d.get("last_bar_ts") else None,
            last_signal_ts=datetime.fromisoformat(d["last_signal_ts"]) if d.get("last_signal_ts") else None,
            incremental_state_json=d.get("incremental_state_json"),
            metadata=d.get("metadata", {}),
        )

    def _position_to_dict(self, pos: Position) -> dict[str, Any]:
        """Convert Position to dict."""
        return {
            "symbol": pos.symbol,
            "side": pos.side,
            "size_usdt": pos.size_usdt,
            "size_qty": pos.size_qty,
            "entry_price": pos.entry_price,
            "mark_price": pos.mark_price,
            "unrealized_pnl": pos.unrealized_pnl,
            "leverage": pos.leverage,
            "stop_loss": pos.stop_loss,
            "take_profit": pos.take_profit,
            "liquidation_price": pos.liquidation_price,
            "metadata": pos.metadata,
        }

    def _dict_to_position(self, d: dict[str, Any]) -> Position:
        """Convert dict to Position."""
        return Position(
            symbol=d["symbol"],
            side=d["side"],
            size_usdt=d["size_usdt"],
            size_qty=d["size_qty"],
            entry_price=d["entry_price"],
            mark_price=d["mark_price"],
            unrealized_pnl=d["unrealized_pnl"],
            leverage=d.get("leverage", 1.0),
            stop_loss=d.get("stop_loss"),
            take_profit=d.get("take_profit"),
            liquidation_price=d.get("liquidation_price"),
            metadata=d.get("metadata", {}),
        )

    def _order_to_dict(self, order: Order) -> dict[str, Any]:
        """Convert Order to dict."""
        return {
            "symbol": order.symbol,
            "side": order.side,
            "size_usdt": order.size_usdt,
            "order_type": order.order_type,
            "limit_price": order.limit_price,
            "trigger_price": order.trigger_price,
            "stop_loss": order.stop_loss,
            "take_profit": order.take_profit,
            "client_order_id": order.client_order_id,
            "metadata": order.metadata,
        }

    def _dict_to_order(self, d: dict[str, Any]) -> Order:
        """Convert dict to Order."""
        return Order(
            symbol=d["symbol"],
            side=d["side"],
            size_usdt=d["size_usdt"],
            order_type=d.get("order_type", "MARKET"),
            limit_price=d.get("limit_price"),
            trigger_price=d.get("trigger_price"),
            stop_loss=d.get("stop_loss"),
            take_profit=d.get("take_profit"),
            client_order_id=d.get("client_order_id"),
            metadata=d.get("metadata", {}),
        )
