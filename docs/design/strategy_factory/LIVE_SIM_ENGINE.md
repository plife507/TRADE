# Live Sim Engine: Detailed Design

> The core new component — SimulatedExchange driven by real-time WebSocket data.

## Concept

```
┌─────────────────────────────────────────────────────┐
│                    LIVE SIM                          │
│                                                     │
│  ┌──────────────┐    ┌──────────────┐              │
│  │ LiveData     │    │ Simulated    │              │
│  │ Provider     │───►│ Exchange     │              │
│  │ (WebSocket)  │    │ (local sim)  │              │
│  └──────────────┘    └──────┬───────┘              │
│         │                   │                       │
│         │            ┌──────┴───────┐              │
│         │            │   Ledger     │              │
│         │            │ (positions,  │              │
│         │            │  equity,     │              │
│         │            │  PnL)        │              │
│         │            └──────────────┘              │
│         │                                           │
│  ┌──────┴──────┐                                   │
│  │ PlayEngine  │  ← Same engine as backtest/live   │
│  │ (signals)   │                                   │
│  └─────────────┘                                   │
└─────────────────────────────────────────────────────┘
```

## What Exists vs What's New

### Already Built

1. **`SimulatedExchange`** (`src/backtest/sim/exchange.py`)
   - Full exchange simulation: pricing, execution, funding, ledger, liquidation
   - Single symbol, single position at a time
   - Deterministic fill logic
   - Currently driven by historical bars in backtest

2. **`LiveDataProvider`** (`src/engine/adapters/live.py`)
   - WebSocket kline subscriptions
   - Incremental indicator computation (O(1) updates)
   - Structure detection (swing, trend, zone)
   - Multi-timeframe candle buffers
   - Warmup tracking

3. **`PlayEngine`** (`src/engine/play_engine.py`)
   - Unified signal logic for all modes
   - `process_bar()` → evaluate rules → generate Signal
   - `execute_signal()` → submit to exchange adapter

4. **`BacktestExchange`** adapter (`src/engine/adapters/backtest.py`)
   - Wraps SimulatedExchange for PlayEngine consumption
   - Implements the ExchangeAdapter protocol
   - Handles bar stepping, position queries, order submission

### Needs Building

1. **`LiveSimRunner`** — New runner that drives the loop
2. **`LiveSimExchange`** adapter — Wraps SimulatedExchange for live-data use
3. **`DataFanout`** — Multiplexes 1 WebSocket to N engines
4. **Factory integration** in `PlayEngineFactory` — `mode="live_sim"`

---

## LiveSimRunner

### Responsibilities

- Subscribe to WebSocket candle stream (like LiveRunner)
- On each closed candle: step SimulatedExchange, process bar, execute signal
- Track equity curve over time
- Report statistics periodically
- No exchange API calls whatsoever

### Key Difference from LiveRunner

| Aspect | LiveRunner | LiveSimRunner |
|--------|-----------|---------------|
| Exchange | LiveExchange (Bybit API) | BacktestExchange (SimulatedExchange) |
| Position sync | REST API reconciliation | Local ledger (always correct) |
| Order fills | Async WebSocket callbacks | Synchronous sim fills |
| Reconnection | Complex WS recovery logic | Same WS recovery, no position recovery needed |
| Equity | From exchange REST API | From local ledger |
| Complexity | High (distributed state) | Low (all state local) |

### Lifecycle

```python
class LiveSimRunner:
    """Drive PlayEngine with live WebSocket data and simulated execution."""

    def __init__(
        self,
        engine: PlayEngine,
        report_interval: float = 300.0,  # Log stats every 5 min
        max_signals: int = 10_000,
    ):
        self.engine = engine
        self._report_interval = report_interval
        self._stats = LiveSimStats()
        self._equity_curve: list[EquityPoint] = []

    async def start(self) -> None:
        """Subscribe to WebSocket, begin processing loop."""
        # 1. Wait for warmup (indicators need history)
        # 2. Process bars as they close
        # 3. Step SimulatedExchange on each bar
        # 4. Execute signals through SimulatedExchange
        # 5. Record equity after each bar

    async def stop(self) -> None:
        """Graceful shutdown, persist final state."""

    def get_equity_curve(self) -> list[EquityPoint]:
        """Current equity history."""

    def get_stats(self) -> LiveSimStats:
        """Current run statistics."""
```

### Bar Processing Loop

```python
async def _process_bar(self, candle: Candle) -> None:
    """Process one closed candle through the engine."""

    # 1. Step the simulated exchange (check TP/SL fills, funding)
    #    This is what BacktestExchange.step() already does
    self.engine.exchange.step(candle)

    # 2. Process bar through engine (evaluate rules, generate signal)
    signal = self.engine.process_bar(-1)  # -1 = latest bar

    # 3. Execute signal if generated
    if signal:
        result = self.engine.execute_signal(signal)
        self._stats.signals += 1
        if result.success:
            self._stats.fills += 1

    # 4. Record equity
    equity = self.engine.exchange.get_equity()
    self._equity_curve.append(EquityPoint(
        timestamp=candle.ts_close,
        equity=equity,
    ))

    self._stats.bars += 1
```

---

## LiveSimExchange Adapter

### Do We Need a New Adapter?

Maybe not. The existing `BacktestExchange` adapter already wraps
`SimulatedExchange` and implements the `ExchangeAdapter` protocol.
The key question: can `BacktestExchange` work with live candle delivery?

### BacktestExchange Current Flow

```python
# In backtest mode, bars come from historical data:
for bar_index in range(total_bars):
    candle = data_provider.get_candle(bar_index)
    exchange.step(candle)          # Check fills
    signal = engine.process_bar(bar_index)
    engine.execute_signal(signal)
```

### Live Sim Flow (proposed)

```python
# In live sim mode, bars come from WebSocket:
async def on_candle_close(candle: Candle):
    exchange.step(candle)          # Check fills — SAME as backtest
    signal = engine.process_bar(-1)
    engine.execute_signal(signal)
```

The exchange adapter is identical — only the **runner** (what drives the loop)
changes. `BacktestExchange` should work as-is for live sim.

### Potential Issues

1. **Warmup**: BacktestExchange expects a warmup phase with sequential bars.
   In live sim, warmup comes from `LiveDataProvider` loading initial history.
   Need to verify the adapter doesn't assume sequential bar indices.

2. **Candle format**: Live candles from WebSocket must match the `Candle`
   dataclass that `SimulatedExchange.step()` expects. LiveDataProvider
   already handles this conversion.

3. **Clock**: SimulatedExchange uses candle timestamps for ordering.
   Live candles arrive in real time — no issue, timestamps are monotonic.

### Decision: Reuse BacktestExchange

Unless testing reveals issues, reuse `BacktestExchange` adapter for live sim.
The adapter is exchange-agnostic — it wraps SimulatedExchange regardless of
where the candle data comes from.

---

## DataFanout: 1 WebSocket → N Engines

### Problem

Running 50 engines on the same symbol shouldn't require 50 WebSocket
connections. The data is identical — only the strategy logic differs.

### Current Architecture

```
LiveDataProvider (1 per engine)
  └── Subscribes to RealtimeState (shared singleton)
       └── RealtimeBootstrap (1 WebSocket per symbol/TF)
```

`RealtimeState` is already a shared singleton. Multiple `LiveDataProvider`
instances can subscribe to the same WebSocket data. This means:

**DataFanout may already be free!**

Each engine creates its own `LiveDataProvider`, which internally subscribes
to the same `RealtimeState` kline callbacks. The WebSocket connection is
shared automatically.

### What We DO Need

1. **Candle close synchronization** — When a 15m candle closes, all 50
   engines should process it. Currently LiveRunner processes candles via
   a per-instance queue. We need to ensure all engines see the same candle.

2. **Staggered processing** — If 50 engines all try to process simultaneously,
   we need either:
   - Sequential processing (simple, ~50ms × 50 = 2.5s per bar tick)
   - asyncio.gather (concurrent, but GIL-limited for CPU work)
   - ProcessPool fan-out (true parallelism, more complex)

3. **Shared indicator cache** — If 30 of 50 engines use EMA(50) on the
   same symbol/TF, compute once and share. This is an optimization, not
   a requirement for v1.

### Proposed Architecture

```python
class DataFanout:
    """Coordinate candle delivery to multiple engines on the same symbol."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self._engines: list[tuple[PlayEngine, LiveSimRunner]] = []
        self._realtime_state = RealtimeState.get_instance()

    def add_engine(self, engine: PlayEngine, runner: LiveSimRunner):
        self._engines.append((engine, runner))

    async def on_candle_close(self, tf: str, candle: Candle):
        """Fan out candle to all engines that care about this TF."""
        tasks = []
        for engine, runner in self._engines:
            if tf in engine.timeframes:
                tasks.append(runner.process_bar(candle))
        # Process sequentially for v1 (simple, predictable)
        for task in tasks:
            await task
```

### V1: Sequential Processing (Recommended Start)

For 50 engines on 15m exec TF:
- 1 candle close every 15 minutes
- 50 engines × ~10ms each = 500ms processing time
- 14.5 minutes idle between ticks
- CPU utilization: ~0.06%

**Sequential is fine for v1.** Parallelize later if needed.

---

## Factory Integration

### New Mode: `live_sim`

```python
# src/engine/factory.py

class PlayEngineFactory:
    @staticmethod
    def _create_live_sim(play: Play, config_override: dict | None) -> PlayEngine:
        config = _build_config_from_play(play, "live_sim", persist_state=False)

        data_provider = LiveDataProvider(play, demo=True)
        exchange = BacktestExchange(play, config)  # Reuse! SimExchange inside
        state_store = InMemoryStateStore()

        return PlayEngine(play, data_provider, exchange, state_store, config)
```

### CLI Entry Point

```bash
# Run single play in live sim mode
python trade_cli.py play run --play ema_cross_12_100 --mode live_sim

# Run factory batch in live sim mode
python trade_cli.py factory live-sim --run run_20260225_143000 --top 20
```

### EngineManager Changes

```python
# New limits for live_sim mode
# No per-symbol limit — that's the whole point
# Memory-based limit instead (e.g., max 100 engines total)
elif mode is InstanceMode.LIVE_SIM:
    total_live_sim = sum(1 for i in instances if i.mode == "live_sim")
    if total_live_sim >= self._max_live_sim:  # configurable, default 100
        raise ValueError(f"Live sim instance limit reached ({self._max_live_sim})")
```

---

## Warmup Strategy

### The Problem

SimulatedExchange needs candle history to establish indicator values.
In backtest, this comes from loading N historical bars before the "real"
trading window. In live sim, we need the same warmup.

### Solution: LiveDataProvider Already Handles This

`LiveDataProvider` loads initial candle history via REST API on startup,
then switches to WebSocket for real-time updates. This warmup period
is already implemented — the engine won't generate signals until
indicators have sufficient history.

### Warmup Duration

Depends on the slowest indicator. EMA(200) on daily TF needs 200 daily
bars = ~200 days of history. This is loaded from DuckDB/REST on startup,
not from WebSocket.

---

## State Persistence (Future)

For v1: all state is in-memory. If the process restarts, live sim engines
start fresh (lose their equity curves and open positions).

For v2: serialize SimulatedExchange state to disk periodically:
- Ledger state (position, balance, equity)
- Order book (pending orders)
- Equity curve history
- Signal history

This enables restart-resume for long-running live sim campaigns.

---

## Monitoring & Reporting

### Per-Engine Stats

```python
@dataclass
class LiveSimStats:
    play_id: str
    start_time: datetime
    bars_processed: int = 0
    signals_generated: int = 0
    fills: int = 0
    current_equity: float = 0.0
    peak_equity: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_estimate: float = 0.0  # Rolling window
    win_rate: float = 0.0
    total_trades: int = 0
```

### Dashboard (Rich Live)

```
┌──────────────────────────────────────────────────────────────────┐
│ STRATEGY FACTORY — Live Sim Dashboard                           │
│ Symbol: BTCUSDT  |  Engines: 47  |  Uptime: 3d 14h 22m        │
├──────────────────────────────────────────────────────────────────┤
│ Rank  Play                    Equity    PnL%   DD%   Sharpe  W% │
│  1    ema_cross_12_100_low    $10,502   +5.0%  1.2%  2.31   68%│
│  2    rsi_bounce_21_4h        $10,380   +3.8%  2.1%  1.95   61%│
│  3    macd_cross_trend_med    $10,245   +2.5%  0.8%  1.82   55%│
│  4    bb_squeeze_15m          $10,120   +1.2%  3.4%  1.21   52%│
│  5    vwap_revert_1h          $9,980    -0.2%  4.5%  0.45   48%│
│ ...                                                              │
│ 47    ema_cross_8_200_high    $8,230   -17.7% 18.2% -1.23   32%│
├──────────────────────────────────────────────────────────────────┤
│ [P] Pause  [S] Stop  [D] Details  [R] Promote  [Q] Quit       │
└──────────────────────────────────────────────────────────────────┘
```

---

## Open Design Decisions

### 1. Shared vs Isolated LiveDataProvider

**Option A: Shared** (1 LiveDataProvider per symbol, shared by all engines)
- Pro: Less memory, no duplicate indicator computation
- Con: Engines with different indicator configs can't share
- Con: Coupling between engines

**Option B: Isolated** (1 LiveDataProvider per engine)
- Pro: Simple, each engine fully independent
- Pro: Different indicator configs per engine
- Con: Duplicate computation for shared indicators
- Con: More memory

**Recommendation**: Option B for v1 (simplicity), optimize later if needed.

### 2. Exchange Config Per Engine

Each SimulatedExchange needs its own config:
- Initial capital (same for all? or varied?)
- Fee model (should be identical — use exchange defaults)
- Leverage (comes from Play YAML — varies per play)
- Slippage model (same for all)

### 3. When to Start Live Sim

After backtesting filters down to top N plays, live sim starts automatically?
Or manual trigger? For v1, manual trigger seems safer.
