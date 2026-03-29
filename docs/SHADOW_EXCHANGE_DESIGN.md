# Shadow Exchange (M4) — Full Design

**Date:** 2026-03-28
**Status:** Design
**Prerequisites:** M0 (done), M3 (done), SimExchange fidelity (SHADOW_ORDER_FIDELITY_REVIEW.md)

---

## 1. What Is the Shadow Exchange?

The Shadow Exchange is an **always-on paper trading system** that runs proven plays against real market data using the SimExchange for order execution. It is NOT demo mode.

| Aspect | Demo Mode | Shadow Exchange |
|--------|-----------|-----------------|
| Exchange | Bybit demo API (`api-demo.bybit.com`) | Local SimExchange |
| Orders | REST API calls to Bybit demo | Simulated locally (zero latency) |
| Parallelism | API rate-limited (120 req/s shared) | Unlimited (CPU-bound only) |
| Execution model | Bybit's demo matching engine | Our SimExchange (configurable slippage, impact) |
| Data source | Demo WS feed (sometimes stale/different) | **Live** WS feed (real market data) |
| Fidelity control | Black box (Bybit controls) | Full control (known gaps, tunable) |
| Use case | Quick single-play test | Multi-play extended run, M6 training ground |
| Cost | Free Bybit demo account | Free (no API calls for orders) |
| Duration | Minutes to hours | Days, weeks, months |

### Why SimExchange + Real Data?

1. **Unlimited parallelism** — 50+ plays simultaneously with no API rate limits
2. **Full accounting** — Bybit-aligned ledger, margin, liquidation, funding (already built)
3. **Real market data** — Live WS gives real prices, funding rates, volume
4. **Known fidelity** — Every gap is documented (see `SHADOW_ORDER_FIDELITY_REVIEW.md`), not a Bybit black box
5. **M6 training ground** — Market Intelligence learns regime-to-performance correlation from shadow results
6. **Deterministic replay** — Can replay shadow periods for analysis

---

## 2. Architecture Overview

```
                        Bybit WebSocket (LIVE data)
                        ├── ticker.BTCUSDT (mark_price, last_price, funding)
                        ├── kline.{tf}.BTCUSDT (1m, 5m, 15m, 1h, 4h, D)
                        ├── ticker.ETHUSDT ...
                        └── kline.{tf}.ETHUSDT ...
                               │
                    ┌──────────┴──────────┐
                    │    SharedFeedHub     │  Single WS, fan-out per symbol
                    │  (Layer 1)          │
                    └──────────┬──────────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
    ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
    │ ShadowEngine  │  │ ShadowEngine  │  │ ShadowEngine  │
    │ (Layer 2)     │  │ (Layer 2)     │  │ (Layer 2)     │
    │               │  │               │  │               │
    │ Play A        │  │ Play B        │  │ Play C        │
    │ BTCUSDT 15m   │  │ BTCUSDT 1h    │  │ ETHUSDT 15m   │
    │               │  │               │  │               │
    │ ┌───────────┐ │  │ ┌───────────┐ │  │ ┌───────────┐ │
    │ │PlayEngine │ │  │ │PlayEngine │ │  │ │PlayEngine │ │
    │ │SimExchange│ │  │ │SimExchange│ │  │ │SimExchange│ │
    │ │Ledger     │ │  │ │Ledger     │ │  │ │Ledger     │ │
    │ │Journal    │ │  │ │Journal    │ │  │ │Journal    │ │
    │ └───────────┘ │  │ └───────────┘ │  │ └───────────┘ │
    └───────┬───────┘  └───────┬───────┘  └───────┬───────┘
            │                  │                  │
            └──────────────────┼──────────────────┘
                               ▼
              ┌────────────────────────────────┐
              │   ShadowOrchestrator (Layer 3) │
              │                                │
              │   Lifecycle, health, limits     │
              └────────────────┬───────────────┘
                               ▼
              ┌────────────────────────────────┐
              │   ShadowPerformanceDB (Layer 4)│
              │                                │
              │   DuckDB: snapshots, trades,   │
              │   graduation scores, regime    │
              └────────────────┬───────────────┘
                               ▼
              ┌────────────────────────────────┐
              │   ShadowDaemon (Layer 5)       │
              │                                │
              │   systemd, watchdog, state     │
              │   persistence, hot-reload      │
              └────────────────┬───────────────┘
                               ▼
              ┌────────────────────────────────┐
              │   ShadowGraduator (Layer 6)    │
              │                                │
              │   Scoring, promotion pipeline, │
              │   live allocation sizing       │
              └────────────────┬───────────────┘
                               ▼
              ┌────────────────────────────────┐
              │   CLI / Agent API (Layer 7)    │
              │                                │
              │   shadow {daemon,add,remove,   │
              │   list,stats,graduation,...}   │
              └────────────────────────────────┘
```

---

## 3. Layer 1: SharedFeedHub

### Problem

Running 50 plays on BTCUSDT with separate WebSocket connections = 50 connections. Bybit limits concurrent WS connections per IP.

### Solution

One `RealtimeBootstrap` + `RealtimeState` per symbol. Multiple ShadowEngines register as listeners on the same feed.

```
RealtimeBootstrap("BTCUSDT")           # existing class
    └── RealtimeState (thread-safe)    # existing class
         ├── _kline_callbacks:
         │   ├── shadow_engine_play_a._on_kline
         │   ├── shadow_engine_play_b._on_kline
         │   └── shadow_engine_play_c._on_kline
         └── _ticker_callbacks:
             ├── shadow_engine_play_a._on_ticker  (mark/last/funding)
             └── ...
```

### SharedFeedHub Design

```python
class SharedFeedHub:
    """Manages shared WebSocket connections per symbol."""

    _feeds: dict[str, RealtimeBootstrap]   # symbol -> WS connection
    _listeners: dict[str, list[ShadowEngine]]  # symbol -> engines

    async def ensure_feed(self, symbol: str) -> None:
        """Create WS connection for symbol if not exists."""
        if symbol not in self._feeds:
            bootstrap = RealtimeBootstrap(symbol=symbol, include_private=False)
            await bootstrap.start()
            self._feeds[symbol] = bootstrap

    def register_engine(self, symbol: str, engine: ShadowEngine) -> None:
        """Register engine to receive candles for this symbol."""
        self._listeners.setdefault(symbol, []).append(engine)
        # Register callbacks on RealtimeState
        state = self._feeds[symbol].state
        state.register_kline_callback(engine._on_kline)
        state.register_ticker_callback(engine._on_ticker)

    def unregister_engine(self, symbol: str, engine: ShadowEngine) -> None:
        """Remove engine from feed listeners."""
        self._listeners[symbol].remove(engine)
        # If no more listeners for this symbol, close WS
        if not self._listeners[symbol]:
            self._feeds[symbol].stop()
            del self._feeds[symbol]
            del self._listeners[symbol]

    async def stop(self) -> None:
        """Shut down all WS connections."""
        for bootstrap in self._feeds.values():
            await bootstrap.stop()
```

### Key Design Decisions

- **No private WS**: Shadow doesn't need order/position/execution updates (sim handles all that)
- **Ticker for mark price**: The `ticker` topic gives us real `markPrice` and `lastPrice` — needed for H1 fidelity fix
- **Funding from ticker**: Real `fundingRate` and `nextFundingTime` come via ticker — sim uses these instead of interpolating
- **Connection lifecycle**: WS stays open as long as at least one engine uses the symbol
- **Reconnection**: Existing `RealtimeBootstrap` reconnection logic applies (exponential backoff, max 10 attempts)

---

## 4. Layer 2: ShadowEngine

### What Changes from Current ShadowExchange

The current `ShadowExchange` in `src/engine/adapters/backtest.py:543` is a **no-op** — it records signals but doesn't simulate execution. This is useless for extended paper trading because there's no P&L tracking.

The new ShadowEngine wraps a **real SimExchange** with real WS data:

```python
class ShadowEngine:
    """Single play running in shadow mode with full simulation."""

    # Core components (all existing classes)
    _play: Play
    _engine: PlayEngine
    _sim_exchange: SimulatedExchange    # REAL sim, not no-op
    _data_provider: LiveDataProvider    # Live WS indicators
    _journal: ShadowJournal            # Trade + snapshot logging

    # Shadow-specific state
    _instance_id: str
    _started_at: datetime
    _stats: ShadowEngineStats

    # Real-time price feeds from SharedFeedHub
    _latest_mark_price: float | None
    _latest_last_price: float | None
    _latest_funding_rate: float | None
```

### Data Flow (Per Candle)

```
SharedFeedHub → _on_kline(kline_data)
    │
    ├── Filter: is_closed? matches play TFs?
    │
    ├── Convert KlineData → Candle
    │
    ├── Update LiveDataProvider (indicators, structures)
    │    └── Same path as LiveRunner._process_candle()
    │
    ├── If exec TF candle:
    │    │
    │    ├── Inject real prices into SimExchange:
    │    │    sim.set_external_prices(
    │    │        mark=self._latest_mark_price,
    │    │        last=kline.close,
    │    │        funding_rate=self._latest_funding_rate,
    │    │    )
    │    │
    │    ├── engine.process_bar(-1) → Signal | None
    │    │
    │    ├── If signal → sim.submit_order(...)
    │    │    └── SimExchange handles: fills, fees, margin, ledger
    │    │
    │    ├── sim.process_bar(candle) → StepResult
    │    │    └── TP/SL checks, liquidation, funding, MAE/MFE
    │    │
    │    ├── Record to journal:
    │    │    └── Fills, closes, equity snapshot
    │    │
    │    └── Update stats
    │
    └── If non-exec TF candle:
         └── Update indicators/structures only (no signal eval)
```

### ShadowEngine vs LiveRunner

The ShadowEngine is structurally similar to `LiveRunner` but with key differences:

| Aspect | LiveRunner | ShadowEngine |
|--------|------------|--------------|
| Exchange | Bybit REST API (real orders) | SimExchange (local) |
| Position sync | REST API queries | Sim state (always correct) |
| DCP | Bybit DCP activated | N/A (no real connection) |
| Panic system | Closes real positions | Resets sim state |
| Daily loss tracker | Queries Bybit closed PnL | Reads from sim ledger |
| Safety guards | All enabled (DCP, staleness, sync) | Staleness only (others N/A) |
| Candle queue | Thread-safe queue (WS → async) | Same pattern |
| Max drawdown | Triggers panic + real close | Logs + optional auto-stop |

### What We Reuse

Almost everything from the existing codebase:
- `PlayEngine` — identical signal generation
- `SimExchange` — full order simulation (with fidelity fixes from SHADOW_ORDER_FIDELITY_REVIEW.md)
- `LiveDataProvider` — incremental indicators + structures on live data
- `RealtimeBootstrap` / `RealtimeState` — WS connection management
- `TradeJournal` pattern — JSONL logging

### What's New

- `ShadowEngine` class — glues PlayEngine + SimExchange + LiveDataProvider with real WS feed
- Price injection — feed real mark/last/index prices from WS into SimExchange
- Funding injection — feed real funding rates from WS into SimExchange
- `ShadowJournal` — extended journal with periodic equity snapshots + market context
- Stats tracking — live P&L, Sharpe, drawdown computed in real-time

### ShadowJournal

Extends the existing `TradeJournal` pattern with periodic snapshots:

```python
class ShadowJournal:
    """Extended journal for shadow mode with periodic snapshots."""

    # File: data/shadow/{instance_id}/events.jsonl  (trades, fills, closes)
    # File: data/shadow/{instance_id}/snapshots.jsonl  (periodic equity + context)

    def record_fill(self, fill: Fill, market_context: MarketContext) -> None
    def record_close(self, trade: Trade, market_context: MarketContext) -> None
    def record_snapshot(self, snapshot: ShadowSnapshot) -> None  # hourly
    def record_error(self, error: str) -> None
```

**ShadowSnapshot** (recorded hourly or configurable):
```python
@dataclass
class ShadowSnapshot:
    timestamp: datetime           # UTC-naive
    equity_usdt: float
    cash_balance_usdt: float
    unrealized_pnl_usdt: float
    position_side: str | None     # "LONG", "SHORT", None
    position_size_usdt: float
    position_entry_price: float | None
    mark_price: float
    cumulative_pnl_usdt: float
    total_trades: int
    win_rate: float
    max_drawdown_pct: float
    sharpe_rolling: float | None  # 30-day rolling
    # Market context (for M6)
    funding_rate: float
    volatility_atr_pct: float     # ATR as % of price
    volume_24h: float
```

---

## 5. Layer 3: ShadowOrchestrator

### Responsibilities

1. **Lifecycle management** — add/remove/restart/list plays
2. **SharedFeedHub coordination** — one WS per symbol, fan-out
3. **Resource limits** — max concurrent engines, memory budget
4. **Health monitoring** — detect stale/crashed engines, auto-restart
5. **Performance snapshots** — trigger periodic DB writes
6. **Graceful shutdown** — orderly stop all engines

### Class Design

```python
class ShadowOrchestrator:
    """Manages multiple concurrent ShadowEngines."""

    _engines: dict[str, ShadowEngine]      # instance_id -> engine
    _feed_hub: SharedFeedHub               # shared WS connections
    _perf_db: ShadowPerformanceDB          # long-term storage
    _config: ShadowConfig                  # global shadow config
    _health_task: asyncio.Task | None      # periodic health check
    _snapshot_task: asyncio.Task | None    # periodic DB snapshot

    # --- Play lifecycle ---

    async def add_play(self, play: Play, config: ShadowPlayConfig | None = None) -> str:
        """Add a play to the shadow exchange. Returns instance_id."""
        instance_id = uuid.uuid4().hex[:12]

        # Ensure WS feed exists for this symbol
        symbol = play.symbol_universe[0]
        await self._feed_hub.ensure_feed(symbol)

        # Create engine components
        engine = ShadowEngine(play, instance_id, self._config)
        await engine.initialize()

        # Register with shared feed
        self._feed_hub.register_engine(symbol, engine)

        # Start processing
        await engine.start()
        self._engines[instance_id] = engine

        # Record in performance DB
        self._perf_db.register_instance(instance_id, play)

        return instance_id

    async def remove_play(self, instance_id: str) -> ShadowEngineStats:
        """Stop and remove a play. Returns final stats."""
        engine = self._engines.pop(instance_id)
        stats = await engine.stop()

        # Unregister from feed
        symbol = engine.play.symbol_universe[0]
        self._feed_hub.unregister_engine(symbol, engine)

        # Final snapshot to DB
        self._perf_db.record_final_stats(instance_id, stats)

        return stats

    async def list_plays(self) -> list[ShadowInstanceInfo]:
        """List all running shadow plays with live stats."""

    async def get_stats(self, instance_id: str) -> ShadowEngineStats:
        """Get live stats for a specific play."""

    # --- Orchestrator lifecycle ---

    async def start(self) -> None:
        """Start orchestrator + all registered plays."""
        self._health_task = asyncio.create_task(self._health_loop())
        self._snapshot_task = asyncio.create_task(self._snapshot_loop())

    async def stop(self) -> None:
        """Graceful shutdown: stop all engines, close all feeds, flush DB."""
        for instance_id in list(self._engines):
            await self.remove_play(instance_id)
        await self._feed_hub.stop()
        self._perf_db.close()

    # --- Background tasks ---

    async def _health_loop(self) -> None:
        """Periodic health check (every 60s)."""
        while True:
            await asyncio.sleep(60)
            for iid, engine in list(self._engines.items()):
                if engine.is_stale(max_age_seconds=300):
                    logger.warning("Engine %s stale, restarting", iid)
                    await self._restart_engine(iid)

    async def _snapshot_loop(self) -> None:
        """Periodic performance snapshot (every hour)."""
        while True:
            await asyncio.sleep(3600)
            for iid, engine in self._engines.items():
                snapshot = engine.get_snapshot()
                self._perf_db.record_snapshot(iid, snapshot)
```

### Configuration

```yaml
# config/shadow.yml
shadow:
  max_engines: 50                    # Max concurrent plays
  snapshot_interval_minutes: 60      # How often to snapshot to DB
  health_check_interval_seconds: 60  # Health check frequency
  stale_threshold_seconds: 300       # When to consider an engine stale
  auto_restart_on_stale: true        # Auto-restart stale engines
  max_restart_attempts: 3            # Max restarts before giving up

  # Default play config (can be overridden per-play)
  default_play_config:
    initial_equity_usdt: 10000.0
    max_drawdown_pct: 25.0           # Auto-stop if exceeded
    auto_stop_on_drawdown: false     # Log warning vs stop
```

### Instance Limits (EngineManager Integration)

The existing `EngineManager` already has `InstanceMode.SHADOW`. We extend its limits:

```python
# Current limits:
_max_live = 1               # 1 live instance (safety)
_max_demo_per_symbol = 1    # 1 demo per symbol
_max_backtest = 1           # 1 backtest (DuckDB)

# New shadow limits:
_max_shadow_total = 50      # 50 shadow engines total
_max_shadow_per_symbol = 10 # 10 per symbol (WS fan-out capacity)
```

Shadow instances use their own DuckDB file (`data/market_data_shadow.duckdb`) so they don't conflict with backtest/live DuckDB locks.

---

## 6. Layer 4: ShadowPerformanceDB

### Why a Separate Database?

Shadow runs for days/weeks/months. The data volume is too large for JSONL files and needs queryable storage for:
- Historical equity curves
- Trade analytics by regime
- Graduation scoring
- Leaderboard ranking
- M6 training data export

### Schema

```sql
-- data/shadow/shadow_performance.duckdb

-- Instance registry (which plays are/were running)
CREATE TABLE shadow_instances (
    instance_id VARCHAR PRIMARY KEY,
    play_id VARCHAR NOT NULL,
    play_hash VARCHAR(16) NOT NULL,
    symbol VARCHAR NOT NULL,
    exec_tf VARCHAR NOT NULL,
    initial_equity_usdt DOUBLE NOT NULL,
    started_at TIMESTAMP NOT NULL,
    stopped_at TIMESTAMP,              -- NULL if still running
    stop_reason VARCHAR,               -- 'manual', 'drawdown', 'graduation', 'error'
    config_json VARCHAR,               -- ShadowPlayConfig as JSON
);

-- Periodic equity/state snapshots (hourly)
CREATE TABLE shadow_snapshots (
    instance_id VARCHAR NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    equity_usdt DOUBLE,
    cash_balance_usdt DOUBLE,
    unrealized_pnl_usdt DOUBLE,
    position_side VARCHAR,             -- 'LONG', 'SHORT', NULL
    position_size_usdt DOUBLE,
    position_entry_price DOUBLE,
    mark_price DOUBLE,
    cumulative_pnl_usdt DOUBLE,
    total_trades INTEGER,
    winning_trades INTEGER,
    max_drawdown_pct DOUBLE,
    sharpe_rolling_30d DOUBLE,
    -- Market context (for M6 training)
    funding_rate DOUBLE,
    atr_pct DOUBLE,                    -- ATR / price
    volume_24h_usdt DOUBLE,
    PRIMARY KEY (instance_id, timestamp)
);

-- Individual trade records
CREATE TABLE shadow_trades (
    trade_id VARCHAR PRIMARY KEY,      -- uuid
    instance_id VARCHAR NOT NULL,
    play_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    direction VARCHAR NOT NULL,        -- 'LONG', 'SHORT'
    entry_time TIMESTAMP NOT NULL,
    exit_time TIMESTAMP,
    entry_price DOUBLE NOT NULL,
    exit_price DOUBLE,
    size_usdt DOUBLE NOT NULL,
    pnl_usdt DOUBLE,
    fees_usdt DOUBLE,
    exit_reason VARCHAR,               -- 'take_profit', 'stop_loss', 'signal', etc.
    mae_pct DOUBLE,                    -- Max Adverse Excursion
    mfe_pct DOUBLE,                    -- Max Favorable Excursion
    duration_minutes DOUBLE,
    -- Market context at entry
    entry_funding_rate DOUBLE,
    entry_atr_pct DOUBLE,
    entry_mark_last_spread_pct DOUBLE,
);

-- Graduation scores (computed daily)
CREATE TABLE shadow_graduation_scores (
    instance_id VARCHAR NOT NULL,
    play_id VARCHAR NOT NULL,
    scored_at TIMESTAMP NOT NULL,
    days_running INTEGER,
    total_trades INTEGER,
    net_pnl_usdt DOUBLE,
    net_pnl_pct DOUBLE,
    sharpe_ratio DOUBLE,
    sortino_ratio DOUBLE,
    max_drawdown_pct DOUBLE,
    win_rate DOUBLE,
    profit_factor DOUBLE,
    avg_trade_pnl_usdt DOUBLE,
    consistency_score DOUBLE,          -- Weekly returns std dev (lower = better)
    regime_diversity_score DOUBLE,     -- Performance across regimes (higher = better)
    graduation_ready BOOLEAN,
    graduation_blockers VARCHAR,       -- JSON list of unmet criteria
    PRIMARY KEY (instance_id, scored_at)
);

-- Market regime log (for M6 correlation)
CREATE TABLE shadow_regime_log (
    timestamp TIMESTAMP NOT NULL,
    symbol VARCHAR NOT NULL,
    regime VARCHAR NOT NULL,           -- 'trending_up', 'trending_down', 'ranging', 'volatile'
    regime_confidence DOUBLE,          -- 0.0-1.0
    btc_price DOUBLE,
    btc_24h_change_pct DOUBLE,
    btc_funding_rate DOUBLE,
    total_volume_24h DOUBLE,
    volatility_percentile DOUBLE,      -- Where current vol sits in 30-day distribution
    PRIMARY KEY (timestamp, symbol)
);
```

### Access Patterns

```python
class ShadowPerformanceDB:
    """DuckDB interface for shadow performance data."""

    _db_path: Path  # data/shadow/shadow_performance.duckdb

    # Write (from orchestrator)
    def register_instance(self, instance_id: str, play: Play) -> None
    def record_snapshot(self, instance_id: str, snapshot: ShadowSnapshot) -> None
    def record_trade(self, instance_id: str, trade: ShadowTrade) -> None
    def record_final_stats(self, instance_id: str, stats: ShadowEngineStats) -> None
    def compute_graduation_score(self, instance_id: str) -> GraduationScore

    # Read (from CLI/API)
    def get_instance_info(self, instance_id: str) -> ShadowInstanceInfo
    def get_equity_curve(self, instance_id: str, days: int = 30) -> list[EquityPoint]
    def get_trades(self, instance_id: str, limit: int = 100) -> list[ShadowTrade]
    def get_leaderboard(self, metric: str = "sharpe", limit: int = 20) -> list[LeaderboardEntry]
    def get_graduation_score(self, instance_id: str) -> GraduationScore
    def get_regime_performance(self, instance_id: str) -> dict[str, RegimeStats]

    # M6 export
    def export_training_data(self, symbol: str, days: int = 90) -> DataFrame
```

### DuckDB Concurrency

Per project rules: **no parallel DuckDB writes**. Shadow uses its own DB file (`shadow_performance.duckdb`), separate from backtest/live/demo databases. The `ShadowOrchestrator` is the single writer — all engines funnel snapshots/trades through the orchestrator's write queue.

```python
# Write queue pattern (in ShadowOrchestrator)
_write_queue: asyncio.Queue[DBWriteEvent]

async def _db_writer_loop(self) -> None:
    """Single writer drains the queue sequentially."""
    while True:
        event = await self._write_queue.get()
        self._perf_db.handle_event(event)  # Sequential DuckDB access
```

---

## 7. Layer 5: ShadowDaemon

### VPS Deployment Model

The shadow system runs as an always-on Linux daemon on a VPS:

```
VPS (e.g., Hetzner CPX21: 3 vCPU, 4GB RAM, ~$8/mo)
├── systemd: trade-shadow.service
│   └── python trade_cli.py shadow daemon --config config/shadow.yml
│       └── ShadowOrchestrator
│           ├── SharedFeedHub (reconnecting WS)
│           ├── ShadowEngine × N
│           ├── ShadowPerformanceDB (DuckDB)
│           └── HealthEndpoint (HTTP :8080/health)
│
├── systemd: trade-shadow-monitor.timer (optional)
│   └── Runs every 5min: checks health endpoint, alerts if down
│
├── logrotate: /var/log/trade-shadow/
│   └── Managed by structlog rotating handler
│
└── data/shadow/
    ├── shadow_performance.duckdb    # Performance DB
    ├── state/                       # Engine state snapshots
    │   ├── {instance_id}.state.json # Last known state per engine
    │   └── orchestrator.state.json  # Which plays to restore on restart
    └── {instance_id}/
        ├── events.jsonl             # Trade journal
        └── snapshots.jsonl          # Equity snapshots
```

### systemd Service

```ini
# /etc/systemd/system/trade-shadow.service
[Unit]
Description=TRADE Shadow Exchange
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=trade
WorkingDirectory=/opt/trade
ExecStart=/opt/trade/.venv/bin/python trade_cli.py shadow daemon --config config/shadow.yml
ExecStop=/bin/kill -SIGTERM $MAINPID
Restart=always
RestartSec=10
TimeoutStopSec=30

# Resource limits
MemoryMax=3G
CPUQuota=250%

# Environment
Environment=TRADE_LOG_LEVEL=INFO
Environment=BYBIT_LIVE_API_KEY=<key>
Environment=BYBIT_LIVE_API_SECRET=<secret>

[Install]
WantedBy=multi-user.target
```

### State Persistence & Resume

On shutdown (SIGTERM), the orchestrator saves state:

```python
async def _save_state(self) -> None:
    """Save orchestrator state for restart resume."""
    state = {
        "saved_at": utc_now().isoformat(),
        "instances": {}
    }
    for iid, engine in self._engines.items():
        state["instances"][iid] = {
            "play_id": engine.play.id,
            "play_path": str(engine.play_path),
            "started_at": engine.started_at.isoformat(),
            "sim_state": engine.sim_exchange.save_state(),  # Position, ledger, pending orders
        }
    atomic_write_json(STATE_DIR / "orchestrator.state.json", state)
```

On startup, restore previous state:

```python
async def _restore_state(self) -> None:
    """Restore engines from saved state."""
    state_path = STATE_DIR / "orchestrator.state.json"
    if not state_path.exists():
        return

    state = json.loads(state_path.read_text())
    for iid, engine_state in state["instances"].items():
        play = load_play(engine_state["play_path"])
        engine = ShadowEngine(play, iid, self._config)
        engine.sim_exchange.restore_state(engine_state["sim_state"])
        await self.add_play_from_state(iid, engine)
```

### Config Hot-Reload

SIGHUP triggers config reload:

```python
import signal

def _setup_signal_handlers(self) -> None:
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGTERM, self._handle_shutdown)
    loop.add_signal_handler(signal.SIGHUP, self._handle_reload)

def _handle_reload(self) -> None:
    """Reload config: add new plays, remove deleted plays."""
    new_config = load_shadow_config(self._config_path)
    # Diff current vs new play list
    current_plays = {e.play.id for e in self._engines.values()}
    desired_plays = set(new_config.play_ids)
    to_add = desired_plays - current_plays
    to_remove = current_plays - desired_plays
    # Schedule async add/remove
    for play_id in to_add:
        asyncio.create_task(self._add_play_by_id(play_id))
    for play_id in to_remove:
        asyncio.create_task(self._remove_play_by_id(play_id))
```

### Health Endpoint

Simple HTTP endpoint for monitoring:

```python
from aiohttp import web

async def _health_handler(self, request: web.Request) -> web.Response:
    """GET /health — returns shadow system status."""
    return web.json_response({
        "status": "healthy" if self._is_healthy() else "degraded",
        "uptime_seconds": (utc_now() - self._started_at).total_seconds(),
        "active_engines": len(self._engines),
        "ws_connections": len(self._feed_hub._feeds),
        "engines": {
            iid: {
                "play_id": e.play.id,
                "symbol": e.play.symbol_universe[0],
                "equity_usdt": e.equity,
                "bars_processed": e.stats.bars_processed,
                "last_bar_at": e.stats.last_bar_at.isoformat() if e.stats.last_bar_at else None,
            }
            for iid, e in self._engines.items()
        }
    })
```

---

## 8. Layer 6: ShadowGraduator

### Graduation Criteria

A play graduates from shadow to live when ALL criteria are met:

| Criterion | Default Threshold | Rationale |
|-----------|-------------------|-----------|
| Minimum runtime | 14 days | Need diverse market conditions |
| Minimum trades | 30 | Statistical significance |
| Net PnL | > 0 | Must be profitable |
| Sharpe ratio | > 0.5 | Risk-adjusted return |
| Max drawdown | < 20% | Capital preservation |
| Win rate | > 30% | Not purely luck |
| Profit factor | > 1.2 | Gross profit / gross loss |
| Consistency | Weekly σ < 5% | Low variance of returns |
| Regime diversity | >= 2/4 regimes profitable | Not regime-dependent |
| No recent drawdown | Not in top-25% DD | Don't promote during a losing streak |

Thresholds are configurable per-play or globally in `shadow.yml`.

### Graduation Scoring

```python
@dataclass
class GraduationScore:
    """Comprehensive graduation assessment."""

    instance_id: str
    play_id: str
    scored_at: datetime

    # Raw metrics
    days_running: int
    total_trades: int
    net_pnl_usdt: float
    net_pnl_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    current_drawdown_pct: float
    win_rate: float
    profit_factor: float
    avg_trade_pnl_usdt: float

    # Composite scores (0.0 - 1.0)
    consistency_score: float       # Low weekly return variance
    regime_diversity_score: float  # Performance across market regimes
    recency_score: float           # Recent performance vs overall

    # Graduation decision
    graduation_ready: bool
    blockers: list[str]            # Unmet criteria (human-readable)

    # Recommended live config (if graduating)
    recommended_allocation_pct: float   # % of total capital
    recommended_max_leverage: float
    recommended_max_drawdown_pct: float
```

### Allocation Sizing

When a play graduates, the Graduator recommends a capital allocation based on:

```python
def compute_allocation(score: GraduationScore, total_capital: float) -> float:
    """
    Kelly-inspired but conservative allocation.

    Base allocation = min(kelly_fraction, 10%) * confidence_adjustment
    Confidence = f(days_running, trade_count, regime_diversity)
    """
    # Kelly fraction (half-Kelly for safety)
    if score.win_rate > 0 and score.profit_factor > 1:
        edge = score.win_rate - (1 - score.win_rate) / (score.profit_factor - 1)
        kelly = edge / (score.profit_factor - 1)
        half_kelly = kelly / 2
    else:
        half_kelly = 0.02  # minimum 2%

    # Confidence adjustment (0.5 to 1.0)
    confidence = min(1.0, (
        min(score.days_running / 30, 1.0) * 0.3 +     # runtime confidence
        min(score.total_trades / 100, 1.0) * 0.3 +    # sample size confidence
        score.regime_diversity_score * 0.2 +            # regime robustness
        score.consistency_score * 0.2                   # consistency
    ) + 0.5)

    # Cap at 10% per play
    allocation_pct = min(half_kelly * confidence * 100, 10.0)

    return round(allocation_pct, 1)
```

### Promotion Workflow

```
1. Daily: ShadowGraduator computes graduation scores for all running plays
2. If graduation_ready == True:
   a. Generate graduation report
   b. Log recommendation
   c. If auto_promote enabled: create live instance automatically
   d. If manual: notify user (CLI alert, future: webhook/email)
3. User reviews report, confirms promotion
4. System creates M5 live instance with recommended config
5. Shadow instance continues running (for comparison)
```

### Graduation Report

```
╔══════════════════════════════════════════════════════════════╗
║  SHADOW GRADUATION REPORT: breakout_btc_15m                ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Runtime:        21 days (2026-03-07 to 2026-03-28)         ║
║  Total trades:   47                                          ║
║  Net PnL:        +$1,247.50 (+12.5%)                        ║
║                                                              ║
║  ┌─ Risk Metrics ──────────────────────────────────────┐    ║
║  │ Sharpe:        1.82        Max DD:     8.3%         │    ║
║  │ Sortino:       2.41        Win Rate:   57.4%        │    ║
║  │ Profit Factor: 1.87        Avg Win:    $142         │    ║
║  │ Calmar:        2.19        Avg Loss:   -$98         │    ║
║  └─────────────────────────────────────────────────────┘    ║
║                                                              ║
║  ┌─ Regime Performance ────────────────────────────────┐    ║
║  │ Trending Up:    +$620  (15 trades, 60% WR) ■■■■■■  │    ║
║  │ Trending Down:  +$380  (12 trades, 58% WR) ■■■■    │    ║
║  │ Ranging:        +$190  (14 trades, 50% WR) ■■      │    ║
║  │ Volatile:       +$57   (6 trades, 50% WR)  ■       │    ║
║  └─────────────────────────────────────────────────────┘    ║
║                                                              ║
║  ┌─ Graduation Criteria ───────────────────────────────┐    ║
║  │ ✓ Runtime >= 14 days        (21 days)               │    ║
║  │ ✓ Trades >= 30              (47 trades)             │    ║
║  │ ✓ Net PnL > 0              (+$1,247.50)            │    ║
║  │ ✓ Sharpe > 0.5             (1.82)                  │    ║
║  │ ✓ Max DD < 20%             (8.3%)                  │    ║
║  │ ✓ Win Rate > 30%           (57.4%)                 │    ║
║  │ ✓ Profit Factor > 1.2      (1.87)                  │    ║
║  │ ✓ Consistency < 5% σ       (3.1%)                  │    ║
║  │ ✓ Regime diversity >= 2/4   (4/4)                  │    ║
║  │ ✓ Not in top-25% DD        (1.2% current)         │    ║
║  └─────────────────────────────────────────────────────┘    ║
║                                                              ║
║  VERDICT: ✓ READY FOR GRADUATION                            ║
║                                                              ║
║  Recommended allocation: 5.0% ($500 of $10,000)             ║
║  Recommended max leverage: 5x                                ║
║  Recommended max drawdown: 10%                               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 9. Layer 7: CLI / Agent API

### CLI Commands

```bash
# === Daemon Management ===
python trade_cli.py shadow daemon                         # Start daemon (foreground)
python trade_cli.py shadow daemon --config shadow.yml     # Custom config
python trade_cli.py shadow daemon --detach                # Start as background process
python trade_cli.py shadow daemon stop                    # Graceful stop
python trade_cli.py shadow daemon status                  # Check if running
python trade_cli.py shadow daemon status --json           # JSON status (for agents)

# === Play Management ===
python trade_cli.py shadow add --play breakout_btc_15m    # Add play to shadow
python trade_cli.py shadow add --play X --equity 5000     # Custom starting equity
python trade_cli.py shadow remove --instance abc123       # Remove by instance ID
python trade_cli.py shadow remove --play breakout_btc_15m # Remove by play name
python trade_cli.py shadow restart --instance abc123      # Restart single play
python trade_cli.py shadow list                           # List all shadow plays
python trade_cli.py shadow list --json                    # JSON output (for agents)

# === Performance ===
python trade_cli.py shadow stats --instance abc123        # Single play stats
python trade_cli.py shadow stats --play breakout_btc_15m  # By play name
python trade_cli.py shadow stats --all                    # All plays summary
python trade_cli.py shadow stats --all --json             # JSON (for agents)
python trade_cli.py shadow leaderboard                    # Ranked by Sharpe
python trade_cli.py shadow leaderboard --by profit_factor # Ranked by PF
python trade_cli.py shadow trades --instance abc123       # Trade log
python trade_cli.py shadow equity --instance abc123       # Equity curve (ASCII chart)
python trade_cli.py shadow equity --instance abc123 --json # Equity data points

# === Graduation ===
python trade_cli.py shadow graduation check --instance abc123  # Check readiness
python trade_cli.py shadow graduation check --all              # Check all plays
python trade_cli.py shadow graduation report --instance abc123 # Full report
python trade_cli.py shadow graduation promote --instance abc123 --confirm  # Promote to live
python trade_cli.py shadow graduation criteria                 # Show current thresholds
```

### Tool Functions (for agents)

All shadow operations are exposed as tool functions in `src/tools/shadow_tools.py`:

```python
def shadow_add_play_tool(play_id: str, equity: float = 10000.0) -> ToolResult
def shadow_remove_play_tool(instance_id: str) -> ToolResult
def shadow_list_tool(json_output: bool = True) -> ToolResult
def shadow_stats_tool(instance_id: str) -> ToolResult
def shadow_leaderboard_tool(metric: str = "sharpe", limit: int = 20) -> ToolResult
def shadow_graduation_check_tool(instance_id: str) -> ToolResult
def shadow_graduation_promote_tool(instance_id: str) -> ToolResult
```

All return `ToolResult` with `{"status", "message", "data"}` envelope (matching existing patterns).

---

## 10. SimExchange Fidelity: What to Fix and When

The `SHADOW_ORDER_FIDELITY_REVIEW.md` documents all gaps. Here's the prioritization for Shadow:

### Must-Fix Before Shadow Launch (Phase 0)

| Gap | Severity | Impact on Shadow |
|-----|----------|-----------------|
| H1: Mark/Last price divergence | HIGH | Liquidation timing, margin accuracy |
| H2: TP/SL trigger_by | HIGH | Phantom stop-outs on wicks |

Without H1+H2, shadow P&L will systematically diverge from what live would produce, making graduation scores unreliable.

### Fix After Launch (Improves Fidelity)

| Gap | Severity | Impact |
|-----|----------|--------|
| H3: Partial TP/SL | HIGH | Split-exit strategies impossible |
| H4: Dynamic stop modification | HIGH | Advanced trade management |
| M1: closeOnTrigger | MEDIUM | Rare margin-rescue scenario |
| M2: Partial fills | MEDIUM | Large orders on thin books |
| M3: Trailing absolute price | MEDIUM | Minor trailing behavior diff |

H3 and H4 are important for strategy diversity but not blocking for basic momentum/breakout strategies.

---

## 11. Resource Estimation

### VPS Requirements

| Plays | RAM (est.) | CPU | WS Connections | DuckDB Size/Month |
|-------|-----------|-----|----------------|-------------------|
| 10 | ~1 GB | 1 vCPU | 3-5 symbols | ~50 MB |
| 25 | ~2 GB | 2 vCPU | 5-8 symbols | ~120 MB |
| 50 | ~3.5 GB | 3 vCPU | 8-12 symbols | ~250 MB |

Per-engine memory breakdown:
- PlayEngine: ~10 MB (indicators, structures, DSL state)
- SimExchange: ~5 MB (ledger, order book, position)
- LiveDataProvider: ~30 MB (candle buffers × 3 TFs, indicator caches)
- Overhead: ~5 MB

Total per engine: ~50 MB. With 50 engines: ~2.5 GB + shared overhead.

### Recommended VPS

- **Hetzner CPX21**: 3 vCPU AMD, 4 GB RAM, 80 GB SSD — ~$8/mo
- **Hetzner CPX31**: 4 vCPU AMD, 8 GB RAM, 160 GB SSD — ~$15/mo (for 50+ plays)

---

## 12. M6 Integration Points

The Shadow Exchange is the training ground for Market Intelligence (M6). Integration points:

### Data Export

```python
# M6 queries shadow DB for training data
training_data = perf_db.export_training_data(
    symbol="BTCUSDT",
    days=90,
)
# Returns DataFrame:
# | timestamp | regime | play_id | pnl_usdt | sharpe_30d | funding | atr_pct | volume |
```

### Regime Labeling

Shadow records market regime alongside performance data:

```python
# Simple regime classifier (starter, M6 will replace with ML)
def classify_regime(atr_pct: float, trend_strength: int, funding_rate: float) -> str:
    if atr_pct > 3.0:
        return "volatile"
    if abs(trend_strength) >= 2:
        return "trending_up" if trend_strength > 0 else "trending_down"
    return "ranging"
```

### Play Recommendation Interface

M6 will eventually consume shadow data to recommend:
- Which plays to activate/deactivate
- Which plays to promote to live
- When to rotate plays based on regime change

```python
# Future M6 interface (M6 implements, Shadow provides data)
class PlayRecommendation:
    play_id: str
    action: Literal["activate", "deactivate", "promote", "demote"]
    confidence: float
    reason: str
    regime_context: str
```

---

## 13. File Layout

```
src/shadow/                           # NEW: Shadow Exchange module
├── __init__.py
├── engine.py                         # ShadowEngine (per-play wrapper)
├── orchestrator.py                   # ShadowOrchestrator (multi-play manager)
├── feed_hub.py                       # SharedFeedHub (WS fan-out)
├── performance_db.py                 # ShadowPerformanceDB (DuckDB)
├── journal.py                        # ShadowJournal (extended JSONL)
├── daemon.py                         # ShadowDaemon (process management)
├── graduator.py                      # ShadowGraduator (promotion pipeline)
├── config.py                         # ShadowConfig, ShadowPlayConfig
├── types.py                          # ShadowSnapshot, ShadowTrade, etc.
└── regime.py                         # Simple regime classifier (M6 starter)

src/cli/subcommands/shadow.py         # CLI handlers
src/tools/shadow_tools.py             # Agent API tools

config/shadow.yml                     # Default shadow config
config/shadow_graduation.yml          # Graduation criteria defaults

data/shadow/                          # Shadow runtime data
├── shadow_performance.duckdb         # Performance database
├── state/                            # Engine state snapshots
│   └── orchestrator.state.json
└── {instance_id}/                    # Per-instance journals
    ├── events.jsonl
    └── snapshots.jsonl

deploy/                               # VPS deployment files
├── trade-shadow.service              # systemd unit
├── deploy.sh                         # Deployment script
└── README.md                         # VPS setup guide
```

---

## 14. What We Do NOT Build (Scope Boundaries)

| Not Building | Why |
|-------------|-----|
| Real order book simulation | Bybit doesn't expose full book via WS; sim uses volume-based depth |
| Tick-by-tick replay | 1m granularity is sufficient; tick data is 100x more expensive |
| Multi-exchange support | Bybit only for now (architecture supports extension) |
| Web UI for shadow | CLI + JSON first; web UI is M7 scope |
| Automatic live promotion | Always require human confirmation for real money |
| Sub-account creation | M5 scope; shadow just recommends allocation |
| ML-based regime detection | M6 scope; shadow uses simple classifier as starter |
| Position hedging | Single-position-per-play model maintained |

---

## 15. Risk & Failure Modes

| Failure | Impact | Mitigation |
|---------|--------|------------|
| WS disconnect | Engines stop receiving data | Auto-reconnect (existing), staleness detection, auto-restart |
| Engine crash | Single play stops | Orchestrator catches, logs, auto-restarts |
| DuckDB corruption | Performance data lost | WAL mode, periodic backups, JSONL journals as fallback |
| VPS reboot | All plays stop | systemd Restart=always, state persistence + resume |
| Memory OOM | Process killed | systemd MemoryMax, per-engine budgets, alert on high usage |
| Sim divergence | Graduation scores unreliable | Fidelity fixes (H1-H4), periodic demo-vs-shadow comparison |
| Bybit API change | WS format breaks | Version-pinned pybit, canary play for early detection |
| Clock drift | Timestamp misalignment | NTP on VPS, `time.monotonic()` for intervals |
