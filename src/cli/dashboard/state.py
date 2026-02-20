"""Dashboard state snapshot and refresh logic."""

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


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

    # Position enhancements
    position_opened_at: float = 0.0  # monotonic time when position detected
    risk_per_trade: float = 0.0  # $ risk (entry - SL) * qty, for R-multiple

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

    # Indicator sparkline history: {"ema_9": deque([1.2, 1.3, ...], maxlen=20)}
    indicator_history: dict[str, deque[float]] = field(default_factory=dict)

    # Signal proximity (populated by runner at account refresh cadence)
    signal_proximity: Any = None  # SignalProximity | None

    # Tiered refresh tracking
    _last_ticker_refresh: float = 0.0
    _last_account_refresh: float = 0.0
    _last_bar_count: int = 0
    _last_engine_data_refresh: float = 0.0

    # Internal
    _rpnl_last_fetch: float = 0.0


# ---------------------------------------------------------------------------
# State refresh from engine manager
# ---------------------------------------------------------------------------


def _get_instance(manager: object, instance_id: str) -> tuple[Any, Any, Any] | None:
    """Return (inst, runner, engine) or None if instance not found."""
    mgr_instances: dict[str, Any] = getattr(manager, "_instances", {})
    inst = mgr_instances.get(instance_id)
    if inst is None:
        return None
    return inst, inst.runner, inst.engine


def refresh_ticker(
    state: DashboardState,
    manager: object,
    instance_id: str,
) -> None:
    """Fast-path: refresh ticker data from WebSocket (250ms cadence)."""
    result = _get_instance(manager, instance_id)
    if result is None:
        return
    _inst, runner, _engine = result

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

    state._last_ticker_refresh = time.monotonic()


def refresh_account(
    state: DashboardState,
    manager: object,
    instance_id: str,
) -> None:
    """Slow-path: refresh account, position, runner stats (2s cadence)."""
    result = _get_instance(manager, instance_id)
    if result is None:
        state.runner_state = "STOPPED"
        return
    _inst, runner, engine = result

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
                was_flat = not state.has_position
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

                # Track position open time
                if was_flat:
                    state.position_opened_at = time.monotonic()

                # Compute risk per trade for R-multiple
                if pos.stop_loss and pos.entry_price and pos.size_qty:
                    state.risk_per_trade = abs(pos.entry_price - pos.stop_loss) * pos.size_qty
                else:
                    state.risk_per_trade = 0.0
            else:
                state.has_position = False
                state.side = "FLAT"
                state.size_qty = 0.0
                state.unrealized_pnl = 0.0
                state.position_opened_at = 0.0
                state.risk_per_trade = 0.0
        except Exception:
            # On error (e.g. during shutdown), mark position unknown
            state.has_position = False
            state.side = "FLAT"

        # Realized PnL: cache for 60s
        now = time.monotonic()
        if now - state._rpnl_last_fetch > 60.0:
            try:
                state.realized_pnl = exchange.get_realized_pnl()
                state._rpnl_last_fetch = now
            except Exception:
                pass

    state._last_account_refresh = time.monotonic()


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
            # Populate sparkline history for numeric values
            for name, val in values.items():
                if isinstance(val, (int, float)):
                    hist_key = f"{role}.{name}"
                    if hist_key not in state.indicator_history:
                        state.indicator_history[hist_key] = deque(maxlen=20)
                    state.indicator_history[hist_key].append(float(val))

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
