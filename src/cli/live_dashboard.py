"""
Live dashboard for play runner.

Rich Live full-screen display with tabbed views for monitoring live/demo trading.
Dense, informative layout: always-visible status + switchable detail panels.

Keybindings:
    1-6     Switch tab (Overview / Indicators / Structures / Log / Play / Orders)
    p       Toggle pause (new entries stopped, positions maintained)
    q       Quit
    m       Cycle meta display on overview tab
"""

import logging
import math
import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.text import Text


# ---------------------------------------------------------------------------
# 1. Log capture handler
# ---------------------------------------------------------------------------


class DashboardLogHandler(logging.Handler):
    """Captures formatted log records into a thread-safe ring buffer."""

    _ACTION_PATTERNS = re.compile(
        r"(Order filled|Exit filled|Exit signal|Signal|ENTRY|EXIT|"
        r"order.*filled|position.*opened|position.*closed)",
        re.IGNORECASE,
    )

    def __init__(self, max_lines: int = 50, max_actions: int = 10) -> None:
        super().__init__()
        self.setLevel(logging.DEBUG)
        self._buffer: deque[str] = deque(maxlen=max_lines)
        self._actions: deque[tuple[float, str]] = deque(maxlen=max_actions)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        with self._lock:
            self._buffer.append(msg)
            if self._ACTION_PATTERNS.search(msg):
                self._actions.append((time.time(), msg))

    def get_lines(self) -> list[str]:
        with self._lock:
            return list(self._buffer)

    def get_last_action(self) -> tuple[float, str] | None:
        with self._lock:
            return self._actions[-1] if self._actions else None

    def get_recent_actions(self, n: int = 5) -> list[tuple[float, str]]:
        with self._lock:
            return list(self._actions)[-n:]


# ---------------------------------------------------------------------------
# 1b. Order event tracker
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class OrderEvent:
    """Single order event for dashboard display."""

    timestamp: float
    symbol: str
    direction: str
    size_usdt: float
    order_type: str  # "market", "limit"
    status: str  # "submitted", "filled", "failed", "rejected", "pending"
    order_id: str
    fill_price: float | None = None
    error: str | None = None
    source: str = "rest"  # "rest" or "websocket"


class OrderTracker:
    """Thread-safe tracker for order events displayed in the dashboard.

    Captures order submissions, fills, and failures into a ring buffer.
    Register via ``OrderExecutor.on_execution()`` callback.
    """

    def __init__(self, max_events: int = 50) -> None:
        self._events: deque[OrderEvent] = deque(maxlen=max_events)
        self._lock = threading.Lock()
        # Counters
        self.total_submitted: int = 0
        self.total_filled: int = 0
        self.total_failed: int = 0

    def record_execution_result(self, result: object) -> None:
        """Callback for ``OrderExecutor.on_execution()``.

        Accepts an ``ExecutionResult`` from ``src.core.order_executor``.
        """
        signal = getattr(result, "signal", None)
        order_result = getattr(result, "order_result", None)
        success = getattr(result, "success", False)
        error = getattr(result, "error", None)
        source = getattr(result, "source", "rest")

        symbol = getattr(signal, "symbol", "?") if signal else "?"
        direction = getattr(signal, "direction", "?") if signal else "?"
        size_usdt = getattr(signal, "size_usdt", 0.0) if signal else 0.0

        # Determine order type from signal metadata
        meta = getattr(signal, "metadata", None) or {}
        order_type = meta.get("order_type", "market")

        order_id = ""
        fill_price: float | None = None
        if order_result is not None:
            order_id = getattr(order_result, "order_id", "") or ""
            fill_price = getattr(order_result, "price", None) or getattr(
                order_result, "fill_price", None
            )

        if success:
            status = "filled"
        elif error:
            # Check risk block vs execution failure
            risk_check = getattr(result, "risk_check", None)
            if risk_check and not getattr(risk_check, "allowed", True):
                status = "rejected"
            else:
                status = "failed"
        else:
            status = "failed"

        event = OrderEvent(
            timestamp=time.time(),
            symbol=symbol,
            direction=direction,
            size_usdt=size_usdt,
            order_type=order_type,
            status=status,
            order_id=order_id,
            fill_price=fill_price,
            error=error,
            source=source,
        )

        with self._lock:
            self._events.append(event)
            self.total_submitted += 1
            if success:
                self.total_filled += 1
            else:
                self.total_failed += 1

    def get_events(self, n: int = 20) -> list[OrderEvent]:
        """Return last *n* order events (newest first)."""
        with self._lock:
            items = list(self._events)
        return list(reversed(items[-n:]))

    def get_pending_count(self) -> int:
        """Count events with status 'pending' or 'submitted'."""
        with self._lock:
            return sum(
                1 for e in self._events if e.status in ("pending", "submitted")
            )

    def get_summary(self) -> tuple[int, int, int]:
        """Return (total_submitted, total_filled, total_failed)."""
        with self._lock:
            return self.total_submitted, self.total_filled, self.total_failed


# ---------------------------------------------------------------------------
# 2. Dashboard state snapshot
# ---------------------------------------------------------------------------


@dataclass
class DashboardState:
    """All values displayed in the dashboard."""

    # Identity (set once at start)
    play_name: str = ""
    description: str = ""
    symbol: str = ""
    mode: str = "DEMO"
    exec_tf: str = ""
    leverage: float = 1.0

    # Play meta (set once at start from Play object)
    features_summary: str = ""
    actions_summary: str = ""
    position_mode: str = ""
    exit_mode: str = ""
    sl_summary: str = ""
    tp_summary: str = ""
    sizing_summary: str = ""
    max_drawdown_pct: float = 0.0
    play_yaml: str = ""

    # Feature declarations: [(name, indicator_type, tf, params_str)]
    feature_decls: list[tuple[str, str, str, str]] = field(default_factory=list)
    # Structure declarations: [(key, struct_type, tf_role)]
    structure_decls: list[tuple[str, str, str]] = field(default_factory=list)

    # Account (refreshed)
    equity: float = 0.0
    balance: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0

    # Position
    has_position: bool = False
    side: str = "FLAT"
    size_qty: float = 0.0
    entry_price: float = 0.0
    mark_price: float = 0.0
    liq_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None

    # Market / Ticker (from WebSocket)
    last_price: float = 0.0
    bid_price: float = 0.0
    ask_price: float = 0.0
    high_24h: float = 0.0
    low_24h: float = 0.0
    volume_24h: float = 0.0
    price_change_24h: float = 0.0
    funding_rate: float = 0.0
    open_interest: float = 0.0
    ticker_stale: bool = True

    # Runner stats
    bars_processed: int = 0
    signals_generated: int = 0
    orders_filled: int = 0
    orders_failed: int = 0
    uptime_seconds: float = 0.0
    last_candle_ts: str = ""
    runner_state: str = "STARTING"
    engine_phase: str = "CREATED"
    is_paused: bool = False
    warmup_ready: bool = False
    warmup_bars: int = 0
    warmup_target: int = 0
    errors: list[str] = field(default_factory=list)

    # Indicator values by TF role: {"low_tf": {"ema_9": 187.12, ...}}
    indicator_values_by_tf: dict[str, dict[str, float | str | None]] = field(
        default_factory=dict
    )
    # Structure values by TF role: {"low_tf": {"swing": {"high_level": 189.5}}}
    structure_values_by_tf: dict[str, dict[str, dict[str, Any]]] = field(
        default_factory=dict
    )
    # TF mapping: {"low_tf": "15m", "med_tf": "1h", "high_tf": "D"}
    tf_mapping: dict[str, str] = field(default_factory=dict)

    # Internal
    _rpnl_last_fetch: float = 0.0


# ---------------------------------------------------------------------------
# 3. State refresh from engine manager
# ---------------------------------------------------------------------------


def refresh_state(
    state: DashboardState,
    manager: object,
    instance_id: str,
) -> None:
    """Poll data from EngineManager internals into *state*."""

    mgr_instances: dict[str, Any] = getattr(manager, "_instances", {})
    inst = mgr_instances.get(instance_id)
    if inst is None:
        state.runner_state = "STOPPED"
        return

    runner = inst.runner
    engine = inst.engine

    # --- Runner stats ---
    if runner is not None:
        stats = runner.stats
        state.bars_processed = stats.bars_processed
        state.signals_generated = stats.signals_generated
        state.orders_filled = stats.orders_filled
        state.orders_failed = stats.orders_failed
        state.uptime_seconds = stats.duration_seconds
        if stats.last_candle_ts:
            state.last_candle_ts = stats.last_candle_ts.strftime("%H:%M:%S")
        state.runner_state = runner.state.value.upper()
        state.is_paused = runner.is_paused
        state.errors = list(stats.errors[-3:])

        # Warmup progress
        dp = getattr(engine, "_data_provider", None) if engine else None
        if dp is not None:
            state.warmup_ready = dp.is_ready() if hasattr(dp, "is_ready") else True
            state.warmup_bars = getattr(dp, "num_bars", 0)
            state.warmup_target = getattr(dp, "_warmup_bars", 0)

    # --- Engine phase ---
    if engine is not None:
        phase = getattr(engine, "phase", None)
        if phase is not None:
            state.engine_phase = (
                phase.value.upper() if hasattr(phase, "value") else str(phase).upper()
            )

    # --- Exchange data (equity, balance, position) ---
    exchange = getattr(engine, "_exchange", None)
    if exchange is not None:
        try:
            state.equity = exchange.get_equity()
        except Exception:
            pass
        try:
            state.balance = exchange.get_balance()
        except Exception:
            pass

        try:
            pos = exchange.get_position(state.symbol)
            if pos is not None:
                state.has_position = True
                state.side = pos.side
                state.size_qty = pos.size_qty
                state.entry_price = pos.entry_price
                state.mark_price = pos.mark_price
                state.unrealized_pnl = pos.unrealized_pnl
                state.liq_price = pos.liquidation_price
                state.stop_loss = pos.stop_loss
                state.take_profit = pos.take_profit
                state.last_price = pos.mark_price
            else:
                state.has_position = False
                state.side = "FLAT"
                state.size_qty = 0.0
                state.unrealized_pnl = 0.0
        except Exception:
            pass

        # Realized PnL: cache for 60s
        now = time.monotonic()
        if now - state._rpnl_last_fetch > 60.0:
            try:
                state.realized_pnl = exchange.get_realized_pnl()
                state._rpnl_last_fetch = now
            except Exception:
                pass

    # --- Ticker data from WebSocket ---
    rt_state = getattr(runner, "_realtime_state", None) if runner else None
    if rt_state is not None:
        try:
            ticker = rt_state.get_ticker(state.symbol)
            if ticker is not None:
                state.last_price = ticker.last_price
                state.bid_price = ticker.bid_price
                state.ask_price = ticker.ask_price
                state.high_24h = ticker.high_24h
                state.low_24h = ticker.low_24h
                state.volume_24h = ticker.volume_24h
                state.price_change_24h = ticker.price_change_24h
                state.funding_rate = ticker.funding_rate
                state.open_interest = ticker.open_interest
                state.ticker_stale = rt_state.is_ticker_stale(state.symbol)
            else:
                state.ticker_stale = True
        except Exception:
            state.ticker_stale = True


def refresh_engine_data(
    state: DashboardState,
    manager: object,
    instance_id: str,
) -> None:
    """Read indicator and structure values from engine data provider."""

    mgr_instances: dict[str, Any] = getattr(manager, "_instances", {})
    inst = mgr_instances.get(instance_id)
    if inst is None:
        return

    engine = inst.engine
    if engine is None:
        return

    dp = getattr(engine, "_data_provider", None)
    if dp is None:
        return

    # Store TF mapping
    tf_mapping = getattr(dp, "_tf_mapping", {})
    if tf_mapping:
        state.tf_mapping = dict(tf_mapping)

    _read_indicators(state, dp)
    _read_structures(state, dp)


def _read_indicators(state: DashboardState, dp: object) -> None:
    """Read latest indicator values from LiveDataProvider caches."""
    try:
        from src.engine.adapters.live import LiveDataProvider

        if not isinstance(dp, LiveDataProvider):
            return
    except ImportError:
        return

    result: dict[str, dict[str, float | str | None]] = {}
    tf_mapping = getattr(dp, "_tf_mapping", {})

    cache_roles = [
        ("low_tf", "_low_tf_indicators"),
        ("med_tf", "_med_tf_indicators"),
        ("high_tf", "_high_tf_indicators"),
    ]

    for role, attr in cache_roles:
        cache = getattr(dp, attr, None)
        if cache is None:
            continue

        tf_str = tf_mapping.get(role, role)
        values: dict[str, float | str | None] = {}

        try:
            with cache._lock:
                for name, arr in cache._indicators.items():
                    if len(arr) > 0:
                        val = arr[-1]
                        if isinstance(val, (int, float)):
                            if math.isnan(val) or math.isinf(val):
                                values[name] = None
                            else:
                                values[name] = val
                        else:
                            values[name] = str(val)
                    else:
                        values[name] = None
        except Exception:
            pass

        if values:
            result[f"{role} ({tf_str})"] = values

    state.indicator_values_by_tf = result


def _read_structures(state: DashboardState, dp: object) -> None:
    """Read current structure output values from TFIncrementalState objects."""
    try:
        from src.engine.adapters.live import LiveDataProvider

        if not isinstance(dp, LiveDataProvider):
            return
    except ImportError:
        return

    result: dict[str, dict[str, dict[str, Any]]] = {}
    tf_mapping = getattr(dp, "_tf_mapping", {})

    struct_roles = [
        ("low_tf", "_low_tf_structure"),
        ("med_tf", "_med_tf_structure"),
        ("high_tf", "_high_tf_structure"),
    ]

    for role, attr in struct_roles:
        struct_state = getattr(dp, attr, None)
        if struct_state is None:
            continue

        tf_str = tf_mapping.get(role, role)
        role_key = f"{role} ({tf_str})"
        structures: dict[str, dict[str, Any]] = {}

        try:
            for struct_key in struct_state.list_structures():
                fields: dict[str, Any] = {}
                for field_name in struct_state.list_outputs(struct_key):
                    try:
                        fields[field_name] = struct_state.get_value(
                            struct_key, field_name
                        )
                    except Exception:
                        fields[field_name] = None
                structures[struct_key] = fields
        except Exception:
            pass

        if structures:
            result[role_key] = structures

    state.structure_values_by_tf = result


# ---------------------------------------------------------------------------
# 4. Populate play meta (called once at startup)
# ---------------------------------------------------------------------------


def populate_play_meta(state: DashboardState, play: object) -> None:
    """Extract static metadata from a Play object into dashboard state."""
    # Features summary
    features = getattr(play, "features", ())
    if features:
        parts = []
        decls = []
        for f in features:
            ind = getattr(f, "indicator_type", "") or getattr(f, "structure_type", "")
            params = getattr(f, "params", {})
            length = params.get("length", "")
            tf = getattr(f, "tf", "") or ""
            name = getattr(f, "name", "") or getattr(f, "id", "") or ""
            label = f"{ind}({length})" if length else ind
            if tf:
                label += f"@{tf}"
            parts.append(label)
            params_str = ", ".join(f"{k}={v}" for k, v in params.items()) if params else ""
            decls.append((name, ind, tf, params_str))
        state.features_summary = ", ".join(parts)
        state.feature_decls = decls

    # Actions summary
    actions = getattr(play, "actions", [])
    if actions:
        state.actions_summary = ", ".join(getattr(b, "id", "?") for b in actions)

    # Position policy
    policy = getattr(play, "position_policy", None)
    if policy:
        state.position_mode = getattr(policy.mode, "value", str(policy.mode))
        state.exit_mode = getattr(policy.exit_mode, "value", str(policy.exit_mode))

    # Risk model
    rm = getattr(play, "risk_model", None)
    if rm:
        sl = rm.stop_loss
        sl_type = getattr(sl.type, "value", str(sl.type))
        if "atr" in sl_type:
            state.sl_summary = f"ATR {sl.value}x"
        elif "pct" in sl_type or "percent" in sl_type:
            state.sl_summary = f"{sl.value}%"
        else:
            state.sl_summary = f"{sl_type} {sl.value}"

        tp = rm.take_profit
        tp_type = getattr(tp.type, "value", str(tp.type))
        if "rr" in tp_type:
            state.tp_summary = f"RR {tp.value}:1"
        elif "atr" in tp_type:
            state.tp_summary = f"ATR {tp.value}x"
        elif "pct" in tp_type or "percent" in tp_type:
            state.tp_summary = f"{tp.value}%"
        else:
            state.tp_summary = f"{tp_type} {tp.value}"

        sizing = rm.sizing
        model = getattr(sizing.model, "value", str(sizing.model))
        state.sizing_summary = f"{model} {sizing.value}%, max {sizing.max_leverage}x"

    # Max drawdown
    acct = getattr(play, "account", None)
    if acct:
        state.max_drawdown_pct = getattr(acct, "max_drawdown_pct", 0.0)

    # Structure declarations from features (features with structure_type set)
    if features:
        struct_decls = []
        for f in features:
            stype = getattr(f, "structure_type", None)
            if stype:
                key = getattr(f, "name", "") or getattr(f, "id", "") or "?"
                tf = getattr(f, "tf", "") or "exec"
                struct_decls.append((key, str(stype), tf))
        state.structure_decls = struct_decls

    # Full YAML source
    play_id = getattr(play, "id", "") or getattr(play, "name", "")
    if play_id:
        try:
            for base in [Path("plays"), Path("plays/validation")]:
                yaml_path = base / f"{play_id}.yml"
                if yaml_path.exists():
                    state.play_yaml = yaml_path.read_text(encoding="utf-8")
                    break
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 5. Formatting helpers
# ---------------------------------------------------------------------------


def _pnl_style(value: float) -> str:
    if value > 0:
        return "bold green"
    if value < 0:
        return "bold red"
    return "dim"


def _fmt_price(v: float | None) -> str:
    if v is None or v == 0.0:
        return "--"
    return f"${v:,.2f}"


def _fmt_pnl(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}${v:,.2f}"


def _fmt_uptime(secs: float) -> str:
    total = int(secs)
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    return f"{m}m{s:02d}s"


def _fmt_compact(v: float) -> str:
    """Format large numbers compactly (1.2M, 45.3K)."""
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v / 1_000:.1f}K"
    return f"{v:,.0f}"


def _fmt_value(v: Any) -> str:
    """Smart-format an indicator/structure value for display."""
    if v is None:
        return "--"
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return "--"
        if abs(v) >= 1000:
            return f"{v:,.2f}"
        if abs(v) >= 1:
            return f"{v:.4g}"
        if abs(v) >= 0.0001:
            return f"{v:.6g}"
        return f"{v:.2e}"
    return str(v)


def _direction_label(v: Any) -> str:
    """Human label for direction/bias integer values."""
    if v == 1:
        return "1 (UP)"
    if v == -1:
        return "-1 (DOWN)"
    if v == 0:
        return "0 (FLAT)"
    return str(v)


# ---------------------------------------------------------------------------
# 6. Text builders -- each returns a Rich Text for Static widgets
# ---------------------------------------------------------------------------


def _state_badge(state: DashboardState) -> Text:
    """Composite status badge from runner state + engine phase."""
    rs = state.runner_state
    ep = state.engine_phase
    t = Text()

    if rs == "ERROR" or ep == "ERROR":
        t.append(" ERROR ", style="bold white on red")
    elif state.is_paused:
        t.append(" PAUSED ", style="bold black on yellow")
    elif rs == "RECONNECTING":
        t.append(" RECONNECTING ", style="bold white on red")
    elif rs == "STOPPING":
        t.append(" SHUTTING DOWN ", style="bold white on yellow")
    elif rs == "STOPPED":
        t.append(" STOPPED ", style="bold white on rgb(80,80,80)")
    elif rs == "STARTING":
        t.append(" STARTING ", style="bold black on cyan")
    elif ep in ("CREATED", "WARMING"):
        if state.warmup_target > 0 and not state.warmup_ready:
            pct = min(100, int(state.warmup_bars / state.warmup_target * 100))
            t.append(f" WARMING UP {pct}% ", style="bold black on cyan")
        else:
            t.append(" WARMING UP ", style="bold black on cyan")
    elif rs == "RUNNING" and ep == "READY":
        t.append(" WAITING ", style="bold black on yellow")
    elif rs == "RUNNING" and ep == "RUNNING":
        t.append(" RUNNING ", style="bold white on green")
    else:
        t.append(f" {rs} ", style="dim")

    return t


def build_status_text(state: DashboardState, handler: DashboardLogHandler) -> Text:
    """Always-visible top section: identity, account, position, market, action."""
    t = Text()

    # Line 1: Identity
    t.append(f" {state.play_name}", style="bold cyan")
    t.append(f"  {state.symbol}", style="bold yellow")
    t.append(f"  {state.exec_tf}  {state.leverage}x", style="white")
    mode_style = "bold green" if state.mode == "DEMO" else "bold red"
    t.append(f"  {state.mode}", style=mode_style)
    t.append("  ")
    t.append_text(_state_badge(state))
    if state.uptime_seconds > 0:
        t.append(f"  {_fmt_uptime(state.uptime_seconds)}", style="dim")
    t.append("\n")

    # Line 2: Account
    t.append(" Equity ", style="dim")
    t.append(_fmt_price(state.equity), style="bold white")
    t.append("  Bal ", style="dim")
    t.append(_fmt_price(state.balance), style="white")
    t.append("  uPnL ", style="dim")
    t.append(_fmt_pnl(state.unrealized_pnl), style=_pnl_style(state.unrealized_pnl))
    if state.equity > 0 and state.unrealized_pnl != 0:
        pct = state.unrealized_pnl / state.equity * 100
        t.append(f" ({pct:+.2f}%)", style=_pnl_style(state.unrealized_pnl))
    t.append("  rPnL ", style="dim")
    t.append(_fmt_pnl(state.realized_pnl), style=_pnl_style(state.realized_pnl))
    t.append("\n")

    # Line 3: Position
    if state.has_position:
        side_style = "bold green" if state.side == "LONG" else "bold red"
        t.append(f" {state.side}", style=side_style)
        t.append(f" {state.size_qty:.4f}", style="white")
        t.append(f" @ {_fmt_price(state.entry_price)}", style="white")
        t.append("  Mark ", style="dim")
        t.append(_fmt_price(state.mark_price), style="white")
        if state.stop_loss:
            t.append("  SL ", style="dim")
            t.append(_fmt_price(state.stop_loss), style="red")
        if state.take_profit:
            t.append("  TP ", style="dim")
            t.append(_fmt_price(state.take_profit), style="green")
        if state.liq_price and state.liq_price > 0:
            t.append("  Liq ", style="dim")
            t.append(_fmt_price(state.liq_price), style="bold red")
            if state.mark_price > 0:
                liq_dist = abs(state.mark_price - state.liq_price) / state.mark_price * 100
                t.append(f" ({liq_dist:.1f}%)", style="dim")
    else:
        t.append(" FLAT", style="dim")
    t.append("\n")

    # Line 4: Market
    if state.last_price > 0:
        stale = " (stale)" if state.ticker_stale else ""
        t.append(" Price ", style="dim")
        t.append(f"${state.last_price:,.2f}{stale}", style="bold white")
        if state.bid_price > 0 and state.ask_price > 0:
            spread = state.ask_price - state.bid_price
            t.append(f"  B/A ", style="dim")
            t.append(f"{state.bid_price:,.2f}/{state.ask_price:,.2f}", style="white")
            t.append(f"  Spd ${spread:,.3f}", style="dim")
        if state.price_change_24h != 0:
            sign = "+" if state.price_change_24h >= 0 else ""
            t.append(f"  24h ", style="dim")
            t.append(
                f"{sign}{state.price_change_24h:.2f}%",
                style=_pnl_style(state.price_change_24h),
            )
        if state.volume_24h > 0:
            t.append(f"  Vol ", style="dim")
            t.append(_fmt_compact(state.volume_24h), style="dim")
        if state.funding_rate != 0:
            fr_style = "green" if state.funding_rate > 0 else "red"
            t.append(f"  FR ", style="dim")
            t.append(f"{state.funding_rate:.4f}%", style=fr_style)
    else:
        t.append(" Price  --  (waiting for ticker...)", style="dim italic")
    t.append("\n")

    # Line 5: Last action
    action = handler.get_last_action()
    if action:
        ts, msg = action
        age = time.time() - ts
        cleaned = re.sub(r"^\d{2}:\d{2}:\d{2}\s*\[?\w+\]?\s*", "", msg).strip()
        if age < 5.0:
            style = "bold cyan"
        elif age < 30.0:
            style = "cyan"
        else:
            style = "dim"
        t.append(f" >> {cleaned}", style=style)
        if age > 60.0:
            t.append(f"  ({int(age)}s ago)", style="dim")
    else:
        t.append(" Waiting for signals...", style="dim italic")

    return t


def build_tab_bar(current_tab: int) -> Text:
    """Tab indicator line."""
    t = Text()
    tabs = ["Overview", "Indicators", "Structures", "Log", "Play", "Orders"]
    for i, name in enumerate(tabs):
        num = i + 1
        if num == current_tab:
            t.append(f" [{num}]{name} ", style="bold white on rgb(40,40,80)")
        else:
            t.append(f" [{num}]{name} ", style="dim")
    return t


def build_overview_text(state: DashboardState, meta_mode: int) -> Text:
    """Tab 1: Play overview with meta, features, actions, stats."""
    t = Text()

    # Play meta
    if meta_mode >= 1:
        if state.position_mode:
            t.append(" Mode: ", style="dim")
            t.append(state.position_mode.replace("_", " "), style="white")
        if state.exit_mode:
            t.append("  Exit: ", style="dim")
            t.append(state.exit_mode.replace("_", " "), style="white")
        if state.sl_summary:
            t.append("  SL: ", style="dim")
            t.append(state.sl_summary, style="red")
        if state.tp_summary:
            t.append("  TP: ", style="dim")
            t.append(state.tp_summary, style="green")
        if state.sizing_summary:
            t.append("  Size: ", style="dim")
            t.append(state.sizing_summary, style="white")
        if state.max_drawdown_pct > 0:
            t.append("  MaxDD: ", style="dim")
            t.append(f"{state.max_drawdown_pct}%", style="red")
        t.append("\n")

        if state.features_summary:
            t.append(" Features: ", style="dim")
            t.append(state.features_summary, style="dim italic")
            t.append("\n")
        if state.actions_summary:
            t.append(" Actions: ", style="dim")
            t.append(state.actions_summary, style="dim italic")
            t.append("\n")

    # Stats
    t.append("\n")
    t.append(" Bars ", style="dim")
    t.append(f"{state.bars_processed}", style="white")
    t.append("  Signals ", style="dim")
    t.append(f"{state.signals_generated}", style="cyan")
    t.append("  Fills ", style="dim")
    t.append(f"{state.orders_filled}", style="white")
    if state.orders_failed:
        t.append("  Failed ", style="dim")
        t.append(f"{state.orders_failed}", style="bold red")
    if state.last_candle_ts:
        t.append("  Last bar ", style="dim")
        t.append(state.last_candle_ts, style="white")
    t.append("\n")

    # Errors
    if state.errors:
        t.append("\n Errors:\n", style="bold red")
        for err in state.errors:
            t.append(f"   {err}\n", style="red")

    # TF mapping
    if state.tf_mapping:
        t.append("\n Timeframes: ", style="dim")
        parts = []
        for role in ("low_tf", "med_tf", "high_tf"):
            tf = state.tf_mapping.get(role, "?")
            parts.append(f"{role}={tf}")
        t.append("  ".join(parts), style="white")
        exec_role = state.tf_mapping.get("exec", "")
        if exec_role:
            t.append(f"  exec -> {exec_role}", style="cyan")
        t.append("\n")

    return t


def build_indicators_text(state: DashboardState) -> Text:
    """Tab 2: All indicator values grouped by TF."""
    t = Text()

    if not state.indicator_values_by_tf:
        t.append(" No indicator data yet (waiting for warmup...)\n", style="dim italic")
        return t

    for tf_label, values in state.indicator_values_by_tf.items():
        t.append(f"\n {tf_label}\n", style="bold cyan")
        t.append(f" {'Name':<30} {'Value':>15}\n", style="dim")
        t.append(f" {'─' * 46}\n", style="dim")

        # Group multi-output indicators
        # Sort keys: group by prefix (before first dot)
        sorted_keys = sorted(values.keys())
        prev_prefix = ""
        for key in sorted_keys:
            val = values[key]
            formatted = _fmt_value(val)

            # Check if this is a sub-field (has a dot)
            if "." in key:
                prefix, sub = key.rsplit(".", 1)
                if prefix != prev_prefix:
                    # New parent indicator
                    t.append(f" {prefix:<30}\n", style="white")
                    prev_prefix = prefix
                # Sub-field indented
                sub_label = f"  .{sub}"
                t.append(f" {sub_label:<30} ", style="dim")
            else:
                prev_prefix = key
                t.append(f" {key:<30} ", style="white")

            # Value with color hints for known oscillators
            val_style = "white"
            if isinstance(val, (int, float)) and not (math.isnan(val) or math.isinf(val)):
                # RSI-like oscillators: color green < 30, red > 70
                lower_key = key.lower()
                if any(osc in lower_key for osc in ("rsi", "stoch", "mfi", "willr", "cci")):
                    if val <= 30:
                        val_style = "green"
                    elif val >= 70:
                        val_style = "red"
                # Direction/bias fields
                if any(d in lower_key for d in ("direction", "bias")):
                    formatted = _direction_label(val)
                    if val > 0:
                        val_style = "green"
                    elif val < 0:
                        val_style = "red"

            t.append(f"{formatted:>15}\n", style=val_style)

    return t


def build_structures_text(state: DashboardState) -> Text:
    """Tab 3: All structure output fields grouped by TF."""
    t = Text()

    if not state.structure_values_by_tf:
        t.append(
            " No structure data yet (waiting for warmup...)\n", style="dim italic"
        )
        return t

    for tf_label, structures in state.structure_values_by_tf.items():
        t.append(f"\n {tf_label}\n", style="bold cyan")

        for struct_key, fields in structures.items():
            t.append(f"\n {struct_key}\n", style="bold white")
            t.append(f" {'Field':<28} {'Value':>18}\n", style="dim")
            t.append(f" {'─' * 47}\n", style="dim")

            for field_name, val in fields.items():
                formatted = _fmt_value(val)
                val_style = "white"

                # Semantic coloring for known fields
                lower_field = field_name.lower()
                if lower_field in ("direction", "bias"):
                    formatted = _direction_label(val)
                    if val is not None:
                        if (isinstance(val, (int, float)) and val > 0) or val == "bullish":
                            val_style = "green"
                        elif (isinstance(val, (int, float)) and val < 0) or val == "bearish":
                            val_style = "red"

                elif lower_field == "state":
                    if val == "active":
                        val_style = "green"
                    elif val == "broken":
                        val_style = "red"

                elif lower_field in ("pair_direction", "anchor_direction", "bos_direction", "choch_direction"):
                    if val == "bullish":
                        val_style = "green"
                    elif val == "bearish":
                        val_style = "red"

                elif lower_field in ("bos_this_bar", "choch_this_bar"):
                    if val is True or val == 1:
                        val_style = "bold cyan"
                        formatted = "YES"

                elif "level" in lower_field or lower_field in (
                    "high_level", "low_level", "upper", "lower",
                    "break_level_high", "break_level_low",
                    "anchor_high", "anchor_low",
                ):
                    if isinstance(val, (int, float)) and val > 0:
                        formatted = f"${val:,.2f}" if val >= 1 else _fmt_value(val)

                t.append(f" {field_name:<28} ", style="dim")
                t.append(f"{formatted:>18}\n", style=val_style)

    return t


def build_log_text(handler: DashboardLogHandler, max_lines: int = 40) -> Text:
    """Tab 4: Scrolling log output."""
    t = Text()
    lines = handler.get_lines()
    visible = lines[-max_lines:]

    if not visible:
        t.append(" No log output yet...\n", style="dim italic")
        return t

    for line in visible:
        upper = line.upper()
        if "ERROR" in upper or "CRITICAL" in upper:
            style = "bold red"
        elif "WARNING" in upper or "WARN" in upper:
            style = "yellow"
        elif any(kw in upper for kw in ("FILLED", "ORDER", "ENTRY", "EXIT")):
            style = "bold cyan"
        elif "SIGNAL" in upper:
            style = "cyan"
        elif "BAR #" in upper:
            style = "white"
        else:
            style = "dim"
        t.append(line + "\n", style=style)

    return t


def build_play_text(state: DashboardState, max_lines: int = 40) -> Text:
    """Tab 5: Play YAML source (capped to *max_lines* visible rows)."""
    t = Text()
    if not state.play_yaml:
        t.append(" Play YAML not available\n", style="dim italic")
        return t

    lines = state.play_yaml.splitlines()
    total = len(lines)
    visible = lines[:max_lines]

    for line in visible:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            t.append(line + "\n", style="dim italic")
        elif ":" in line:
            key, _, val = line.partition(":")
            t.append(key + ":", style="cyan")
            t.append(val + "\n", style="white")
        else:
            t.append(line + "\n", style="white")

    if total > max_lines:
        t.append(f" ... ({total - max_lines} more lines)\n", style="dim italic")

    return t


def build_orders_text(tracker: OrderTracker, max_lines: int = 40) -> Text:
    """Tab 6: Order status and history."""
    t = Text()

    # Summary counters
    submitted, filled, failed = tracker.get_summary()
    t.append(" Orders: ", style="dim")
    t.append(f"{submitted} submitted", style="white")
    t.append("  ")
    t.append(f"{filled} filled", style="green")
    t.append("  ")
    if failed > 0:
        t.append(f"{failed} failed", style="bold red")
    else:
        t.append("0 failed", style="dim")
    t.append("\n\n")

    events = tracker.get_events(n=max_lines)
    if not events:
        t.append(" No order events yet...\n", style="dim italic")
        return t

    # Header
    t.append(
        f" {'Time':<10} {'Dir':<6} {'Type':<7} {'Status':<9} "
        f"{'Size':>10} {'Price':>12} {'Order ID':<14}\n",
        style="dim",
    )
    t.append(f" {'─' * 78}\n", style="dim")

    for event in events:
        # Timestamp
        ts_str = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
        t.append(f" {ts_str:<10}", style="white")

        # Direction
        if event.direction == "LONG":
            t.append(f"{'LONG':<6}", style="green")
        elif event.direction == "SHORT":
            t.append(f"{'SHORT':<6}", style="red")
        elif event.direction == "FLAT":
            t.append(f"{'CLOSE':<6}", style="yellow")
        else:
            t.append(f"{event.direction:<6}", style="dim")

        # Order type
        t.append(f"{event.order_type:<7}", style="dim")

        # Status with color
        if event.status == "filled":
            t.append(f"{'FILLED':<9}", style="bold green")
        elif event.status == "failed":
            t.append(f"{'FAILED':<9}", style="bold red")
        elif event.status == "rejected":
            t.append(f"{'REJECTED':<9}", style="bold yellow")
        elif event.status in ("pending", "submitted"):
            t.append(f"{'PENDING':<9}", style="cyan")
        else:
            t.append(f"{event.status:<9}", style="dim")

        # Size
        if event.size_usdt > 0:
            t.append(f"{'$' + f'{event.size_usdt:,.2f}':>10}", style="white")
        else:
            t.append(f"{'--':>10}", style="dim")

        # Price
        t.append(" ")
        if event.fill_price and event.fill_price > 0:
            t.append(f"{'$' + f'{event.fill_price:,.2f}':>12}", style="white")
        else:
            t.append(f"{'--':>12}", style="dim")

        # Order ID (truncated)
        t.append(" ")
        oid = event.order_id[:13] if event.order_id else "--"
        t.append(f"{oid:<14}", style="dim")

        t.append("\n")

        # Error detail on next line (if present)
        if event.error:
            error_display = event.error[:70]
            t.append(f"           {error_display}\n", style="red")

    return t


def build_stats_text(state: DashboardState) -> Text:
    """Bottom stats bar."""
    t = Text()
    t.append(" Bars ", style="dim")
    t.append(f"{state.bars_processed}", style="white")
    t.append("  Sig ", style="dim")
    t.append(f"{state.signals_generated}", style="cyan")
    t.append("  Fills ", style="dim")
    t.append(f"{state.orders_filled}", style="white")
    if state.orders_failed:
        t.append("  Err ", style="dim")
        t.append(f"{state.orders_failed}", style="bold red")
    t.append("  Up ", style="dim")
    t.append(_fmt_uptime(state.uptime_seconds), style="white")
    if state.last_candle_ts:
        t.append(f"  Last {state.last_candle_ts}", style="dim")
    return t


# ---------------------------------------------------------------------------
# 7. Pause toggle (file-based IPC)
# ---------------------------------------------------------------------------


def _toggle_pause(manager: object) -> None:
    """Toggle pause state for the first running instance."""
    instances: dict = getattr(manager, "_instances", {})
    if not instances:
        return

    instance_id = next(iter(instances))
    pause_dir = Path(os.path.expanduser("~/.trade/instances"))
    pause_dir.mkdir(parents=True, exist_ok=True)
    pause_file = pause_dir / f"{instance_id}.pause"

    if pause_file.exists():
        pause_file.unlink()
    else:
        pause_file.write_text("paused", encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# 8. Entry point -- Rich Live full-screen dashboard
# ---------------------------------------------------------------------------


def run_dashboard(
    manager: object,
    state: DashboardState,
    handler: DashboardLogHandler,
    stop_event: threading.Event,
    refresh_hz: float = 4.0,
    order_tracker: OrderTracker | None = None,
) -> None:
    """Run the live dashboard until stop_event is set or user quits.

    Full-screen Rich Live display with keyboard controls via msvcrt (Windows)
    or tty/termios (Unix).

    Key input runs in a dedicated thread that never touches Rich rendering,
    ensuring responsiveness even while log/order panels are updating.

    Args:
        manager: EngineManager instance
        state: DashboardState to refresh
        handler: DashboardLogHandler capturing logs
        stop_event: Set this to stop the dashboard loop
        refresh_hz: Refresh rate (default 4 fps)
        order_tracker: Optional OrderTracker for order history panel
    """
    from rich.console import Console
    from rich.live import Live

    console = Console()
    current_tab = 1
    meta_mode = 1  # 0=hidden, 1=compact, 2=full
    tracker = order_tracker or OrderTracker()

    # --- Key listener thread: never acquires Rich locks ---
    def _key_listener() -> None:
        """Listen for single keypresses in a background thread.

        Only mutates simple int/bool locals via nonlocal -- no Rich calls,
        no I/O contention with the render loop.
        """
        nonlocal current_tab, meta_mode
        try:
            import msvcrt  # Windows
            while not stop_event.is_set():
                if msvcrt.kbhit():
                    ch = msvcrt.getch().decode("utf-8", errors="ignore").lower()
                    if ch == "q":
                        stop_event.set()
                        return
                    elif ch == "p":
                        _toggle_pause(manager)
                    elif ch == "m":
                        meta_mode = (meta_mode + 1) % 3
                    elif ch in "123456":
                        current_tab = int(ch)
                else:
                    time.sleep(0.02)  # 20ms poll -- responsive without busy-wait
        except ImportError:
            # Unix: use tty/termios
            import select
            import sys
            try:
                import tty  # type: ignore[import-not-found]
                import termios  # type: ignore[import-not-found]
                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)  # type: ignore[attr-defined]
                try:
                    tty.setraw(fd)  # type: ignore[attr-defined]
                    while not stop_event.is_set():
                        # Use select() with timeout to avoid blocking read()
                        rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                        if rlist:
                            ch = sys.stdin.read(1).lower()
                            if ch == "q":
                                stop_event.set()
                                return
                            elif ch == "p":
                                _toggle_pause(manager)
                            elif ch == "m":
                                meta_mode = (meta_mode + 1) % 3
                            elif ch in "123456":
                                current_tab = int(ch)
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)  # type: ignore[attr-defined]
            except Exception:
                # No keyboard input available; user must Ctrl+C
                while not stop_event.is_set():
                    time.sleep(0.5)

    key_thread = threading.Thread(target=_key_listener, daemon=True, name="dash-keys")
    key_thread.start()

    # --- Data poller thread: updates state without blocking render ---
    def _data_poller() -> None:
        while not stop_event.is_set():
            instances: dict = getattr(manager, "_instances", {})
            if instances:
                iid = next(iter(instances))
                try:
                    refresh_state(state, manager, iid)
                except Exception:
                    pass
                try:
                    refresh_engine_data(state, manager, iid)
                except Exception:
                    pass
            time.sleep(0.5)

    data_thread = threading.Thread(target=_data_poller, daemon=True, name="dash-data")
    data_thread.start()

    interval = 1.0 / refresh_hz

    # Content height budget: terminal minus status(5) + tab_bar(1) + stats(1) + help(1) + padding(2)
    content_lines = max(10, console.height - 10)

    def _build() -> Text:
        t = Text()
        try:
            t.append_text(build_status_text(state, handler))
            t.append("\n")
            t.append_text(build_tab_bar(current_tab))
            t.append("\n")

            if current_tab == 1:
                t.append_text(build_overview_text(state, meta_mode))
            elif current_tab == 2:
                t.append_text(build_indicators_text(state))
            elif current_tab == 3:
                t.append_text(build_structures_text(state))
            elif current_tab == 4:
                t.append_text(build_log_text(handler, max_lines=content_lines))
            elif current_tab == 5:
                t.append_text(build_play_text(state, max_lines=content_lines))
            elif current_tab == 6:
                t.append_text(build_orders_text(tracker, max_lines=content_lines))
        except Exception as e:
            t.append(f"\n  Render error: {e}\n", style="bold red")

        t.append("\n")
        t.append_text(build_stats_text(state))
        t.append("\n")
        t.append("[q]uit  [p]ause  [m]eta  [1-6] tabs", style="dim")
        return t

    try:
        # auto_refresh=False: we drive rendering manually via live.update().
        # This prevents Rich's internal refresh thread from competing with
        # terminal I/O, which was causing key input to freeze on Windows.
        # screen=False: avoids full alternate-screen clear/redraw flicker
        # that causes "shaking" on Windows terminals at higher refresh rates.
        with Live(
            _build(),
            console=console,
            screen=False,
            auto_refresh=False,
            vertical_overflow="crop",
        ) as live:
            while not stop_event.is_set():
                time.sleep(interval)
                live.update(_build(), refresh=True)
    except KeyboardInterrupt:
        stop_event.set()
