# Live Trading Architecture

## Overview

This document describes the architecture for running Plays in live/demo trading mode, building on the existing backtest simulator. The key design goal is a **unified engine** that both backtest and live modes share, ensuring feature parity and preventing divergence.

---

## Current Simulator Order Flow

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      STRATEGY LAYER                                  │
│                (Signal generation at bar close)                      │
│                                                                      │
│   Play YAML → FeatureRegistry → RuleEvaluator → Signal              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                    Signal(direction, size)
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  ENGINE RISK LAYER                                   │
│  (Risk policy, position sizing, validation)                         │
│                                                                      │
│   RiskManager.size_position() → adjusted_size_usdt                  │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                Order (market, limit, stop)
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              SIMULATED EXCHANGE LAYER                                │
│       (Order book, execution, position tracking)                    │
├─────────────────────────────────────────────────────────────────────┤
│ ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐ │
│ │  Order Book  │  │  Position    │  │  Ledger (Accounting)       │ │
│ │  Storage     │  │  Management  │  │  Margin, Equity, Fees      │ │
│ └──────────────┘  └──────────────┘  └────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Signal to Order Flow

**Entry Point:** `src/backtest/engine.py:_process_signal()`

```python
Signal(
    symbol="BTCUSDT",
    direction="LONG" | "SHORT" | "FLAT",
    size_usdt=1000.0,
    confidence=0.8,
    metadata={"stop_loss": 48000, "take_profit": 50000}
)
```

**Processing Pipeline:**
1. Check Position/Orders: Skip if position open or pending orders exist
2. Risk Policy: Check if allowed (risk_mode=rules)
3. Size Computation: Apply kelly fraction, volatility scaling
4. Minimum Check: Skip if size < config.min_trade_usdt
5. Order Submission: Submit MARKET order to exchange

### Hot Loop: Per-Bar Processing

**Location:** `src/backtest/bar_processor.py:process_trading_bar()`

```
BAR OPEN (ts_open):
├─ 1. Compute mark_price (single source of truth)
├─ 2. Apply funding events
├─ 3. Process ORDER BOOK:
│   ├─ MARKET orders fill at bar.open + slippage
│   ├─ Stop orders: check triggers (bar.high >= trigger_price)
│   └─ Limit orders: check price crosses
├─ 4. Process pending close requests
└─ 5. Check TP/SL exits (using 1m granular or OHLC)

BAR CLOSE (ts_close):
├─ 6. Update MAE/MFE tracking
├─ 7. Update ledger for mark_price
├─ 8. Check liquidation
├─ 9. Build snapshot & evaluate strategy rules
└─ 10. Record equity, generate signals
```

### Order Types Supported

| Type | Behavior |
|------|----------|
| MARKET | Fills at bar.open + slippage |
| LIMIT | Fills when price crosses limit_price |
| STOP_MARKET | Triggers at trigger_price, fills as market |
| STOP_LIMIT | Triggers at trigger_price, fills at limit_price |

### Position Lifecycle

```
SIGNAL(LONG)
    → ORDER(MARKET, size=1000)
    → FILL(price=49500, fee=0.57)
    → POSITION(entry=49500, tp=50000, sl=48000)

... bars pass, tracking MAE/MFE ...

TP TRIGGERED (bar.high >= 50000)
    → FILL(price=50000, fee=0.57)
    → TRADE_RECORD(pnl=9.03, duration=45 bars)
    → POSITION = None (ready for next signal)
```

### Key Classes

| Component | Location | Purpose |
|-----------|----------|---------|
| Signal | `src/core/risk_manager.py` | Strategy output |
| Order | `src/backtest/sim/types.py` | Order instance |
| Position | `src/backtest/sim/types.py` | Open position |
| Fill | `src/backtest/sim/types.py` | Fill record |
| SimulatedExchange | `src/backtest/sim/exchange.py` | Order book + execution |
| ExecutionModel | `src/backtest/sim/execution/` | Fill logic |
| Ledger | `src/backtest/sim/ledger.py` | Accounting |

---

## The Gap: What's Missing for Live Trading

```
┌─────────────────────────────────────────────────────────────────────┐
│                     THE MISSING PIECE                               │
│                                                                     │
│   Play YAML  ──?──>  LivePlayRunner  ──────>  OrderExecutor        │
│                           │                                         │
│                    (DOES NOT EXIST)                                │
│                           │                                         │
│              ┌────────────┴────────────┐                           │
│              │                         │                           │
│         WebSocket Data           Snapshot Builder                  │
│         (candles, prices)        (live indicators)                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Components Needed

| Component | Purpose | Complexity |
|-----------|---------|------------|
| LivePlayRunner | Main orchestrator - runs signal loop | HIGH |
| LiveSnapshotBuilder | Build RuntimeSnapshotView from streaming data | HIGH |
| LiveIndicatorEngine | Compute indicators incrementally | MEDIUM |
| LiveSignalBridge | Connect evaluator to OrderExecutor | LOW |

---

## Unified Engine Design

### The Problem

If we have separate codepaths for backtest and live:
- Bug fixes in one don't propagate to the other
- Feature drift between modes
- Testing complexity doubles

### The Solution: Shared Core Engine

```
┌─────────────────────────────────────────────────────────────────────┐
│                      UNIFIED PLAY ENGINE                            │
│                  (Shared by Backtest + Live)                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    PlayEngine (CORE)                         │   │
│  │  - Play loading & validation                                 │   │
│  │  - Feature computation (indicators + structures)             │   │
│  │  - Rule compilation & evaluation                             │   │
│  │  - Signal generation                                         │   │
│  │  - Risk sizing                                               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│              ┌───────────────┼───────────────┐                     │
│              │               │               │                     │
│              ▼               ▼               ▼                     │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐          │
│  │  DataProvider │  │  Exchange     │  │  StateStore   │          │
│  │  (Interface)  │  │  (Interface)  │  │  (Interface)  │          │
│  └───────────────┘  └───────────────┘  └───────────────┘          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   BACKTEST      │  │   DEMO          │  │   LIVE          │
│   INSTANCE      │  │   INSTANCE      │  │   INSTANCE      │
├─────────────────┤  ├─────────────────┤  ├─────────────────┤
│ DataProvider:   │  │ DataProvider:   │  │ DataProvider:   │
│  FeedStore      │  │  WebSocket      │  │  WebSocket      │
│  (historical)   │  │  (real-time)    │  │  (real-time)    │
├─────────────────┤  ├─────────────────┤  ├─────────────────┤
│ Exchange:       │  │ Exchange:       │  │ Exchange:       │
│  Simulated      │  │  Bybit DEMO     │  │  Bybit LIVE     │
│  Exchange       │  │  (fake money)   │  │  (real money)   │
├─────────────────┤  ├─────────────────┤  ├─────────────────┤
│ StateStore:     │  │ StateStore:     │  │ StateStore:     │
│  In-Memory      │  │  Redis/DB       │  │  Redis/DB       │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

### Interface Definitions

```python
# src/engine/interfaces.py

from abc import ABC, abstractmethod
from typing import Protocol

class DataProvider(Protocol):
    """Provides OHLCV data for the engine."""

    def get_candle(self, symbol: str, tf: str, index: int) -> Candle:
        """Get candle at index (backtest) or latest (live)."""
        ...

    def get_indicator(self, symbol: str, tf: str, name: str, index: int) -> float:
        """Get indicator value."""
        ...

    def get_structure(self, symbol: str, key: str, field: str) -> float:
        """Get structure field value."""
        ...


class ExchangeAdapter(Protocol):
    """Executes orders on simulated or real exchange."""

    def submit_order(self, order: Order) -> OrderResult:
        """Submit order for execution."""
        ...

    def cancel_order(self, order_id: str) -> bool:
        """Cancel pending order."""
        ...

    def get_position(self, symbol: str) -> Position | None:
        """Get current position."""
        ...

    def get_balance(self) -> float:
        """Get available balance."""
        ...


class StateStore(Protocol):
    """Persists engine state for recovery."""

    def save_state(self, engine_id: str, state: EngineState) -> None:
        """Save engine state."""
        ...

    def load_state(self, engine_id: str) -> EngineState | None:
        """Load engine state."""
        ...
```

### PlayEngine Core (Shared)

```python
# src/engine/play_engine.py

class PlayEngine:
    """
    Unified engine for executing Plays.

    Works identically for backtest, demo, and live modes.
    Mode differences are handled by injected adapters.
    """

    def __init__(
        self,
        play: Play,
        data_provider: DataProvider,
        exchange: ExchangeAdapter,
        state_store: StateStore,
        risk_config: RiskConfig,
        mode: Literal["backtest", "demo", "live"],
    ):
        self.play = play
        self.data = data_provider
        self.exchange = exchange
        self.state = state_store
        self.risk = RiskManager(risk_config)
        self.mode = mode

        # Shared components (same code for all modes)
        self.feature_registry = play.feature_registry
        self.rule_evaluator = CompiledRuleEvaluator(play)
        self.incremental_state = MultiTFIncrementalState(...)

    def process_bar(self, bar_index: int) -> Signal | None:
        """
        Process a single bar. Called by:
        - Backtest: in a loop over historical data
        - Live: on WebSocket candle close event
        """
        # 1. Update incremental state (structures)
        self.incremental_state.update(bar_index)

        # 2. Build snapshot
        snapshot = self._build_snapshot(bar_index)

        # 3. Evaluate rules
        entry_signal = self.rule_evaluator.evaluate_entry(snapshot)
        exit_signal = self.rule_evaluator.evaluate_exit(snapshot)

        # 4. Check position state
        position = self.exchange.get_position(self.play.symbol)

        # 5. Generate signal
        if position is None and entry_signal:
            return self._create_entry_signal(snapshot, entry_signal)
        elif position is not None and exit_signal:
            return Signal(direction="FLAT", symbol=self.play.symbol)

        return None

    def execute_signal(self, signal: Signal) -> OrderResult:
        """
        Execute a signal through the exchange adapter.
        Same logic for simulated or real exchange.
        """
        # Risk sizing (shared logic)
        sized_signal = self.risk.size_position(signal, self.exchange.get_balance())

        if sized_signal.size_usdt < self.play.account.min_trade_notional_usdt:
            return OrderResult(success=False, error="Below minimum size")

        # Create order
        order = Order(
            symbol=signal.symbol,
            side=signal.direction,
            size_usdt=sized_signal.size_usdt,
            order_type=OrderType.MARKET,
            stop_loss=signal.metadata.get("stop_loss"),
            take_profit=signal.metadata.get("take_profit"),
        )

        # Execute through adapter (simulated or real)
        return self.exchange.submit_order(order)
```

### Mode-Specific Adapters

```python
# src/engine/adapters/backtest.py

class BacktestDataProvider:
    """Provides data from pre-loaded FeedStore arrays."""

    def __init__(self, feed_store: FeedStore):
        self.feed = feed_store

    def get_candle(self, symbol: str, tf: str, index: int) -> Candle:
        return Candle(
            open=self.feed.open[index],
            high=self.feed.high[index],
            low=self.feed.low[index],
            close=self.feed.close[index],
            volume=self.feed.volume[index],
        )


class BacktestExchange:
    """Wraps SimulatedExchange for unified interface."""

    def __init__(self, sim_exchange: SimulatedExchange):
        self.sim = sim_exchange

    def submit_order(self, order: Order) -> OrderResult:
        return self.sim.submit_order(order)

    def get_position(self, symbol: str) -> Position | None:
        return self.sim.position


# src/engine/adapters/live.py

class LiveDataProvider:
    """Provides data from WebSocket stream + indicator cache."""

    def __init__(self, ws_client: BybitWebSocket, indicator_cache: IndicatorCache):
        self.ws = ws_client
        self.cache = indicator_cache

    def get_candle(self, symbol: str, tf: str, index: int) -> Candle:
        # index=-1 means "latest" for live mode
        return self.cache.get_latest_candle(symbol, tf)

    def get_indicator(self, symbol: str, tf: str, name: str, index: int) -> float:
        return self.cache.get_indicator(symbol, tf, name)


class LiveExchange:
    """Wraps OrderExecutor for unified interface."""

    def __init__(self, order_executor: OrderExecutor, position_manager: PositionManager):
        self.executor = order_executor
        self.positions = position_manager

    def submit_order(self, order: Order) -> OrderResult:
        signal = Signal(
            symbol=order.symbol,
            direction=order.side,
            size_usdt=order.size_usdt,
            metadata={"stop_loss": order.stop_loss, "take_profit": order.take_profit}
        )
        return self.executor.execute(signal)

    def get_position(self, symbol: str) -> Position | None:
        return self.positions.get_position(symbol)
```

---

## Multi-Instance Architecture

### The Problem

Running backtest and live simultaneously with separate codebases leads to:
- Updating backtest logic but forgetting live
- Different behavior between modes
- Difficult to verify parity

### The Solution: Single Engine, Multiple Runners

```
┌─────────────────────────────────────────────────────────────────────┐
│                     PLAY ENGINE FACTORY                             │
│                                                                     │
│   PlayEngineFactory.create(                                         │
│       play="my_strategy",                                           │
│       mode="backtest" | "demo" | "live"                            │
│   ) → PlayEngine                                                    │
│                                                                     │
│   - Same PlayEngine class for all modes                            │
│   - Different adapters injected based on mode                      │
│   - Guarantees identical signal logic                              │
└─────────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ BacktestRunner  │  │ DemoRunner      │  │ LiveRunner      │
│                 │  │                 │  │                 │
│ - Loops over    │  │ - WebSocket     │  │ - WebSocket     │
│   historical    │  │   event loop    │  │   event loop    │
│   bars          │  │ - Demo API      │  │ - Live API      │
│ - Fast (batch)  │  │ - Fake money    │  │ - Real money    │
│ - Deterministic │  │ - Real timing   │  │ - Real timing   │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             │
                    ┌────────▼────────┐
                    │   PlayEngine    │
                    │   (SAME CODE)   │
                    └─────────────────┘
```

### Factory Implementation

```python
# src/engine/factory.py

class PlayEngineFactory:
    """Creates PlayEngine instances with appropriate adapters."""

    @staticmethod
    def create(
        play: Play | str,
        mode: Literal["backtest", "demo", "live"],
        config: Config | None = None,
    ) -> PlayEngine:
        """
        Create a PlayEngine for the specified mode.

        Args:
            play: Play instance or play_id string
            mode: Execution mode
            config: Optional config override

        Returns:
            Configured PlayEngine ready for execution
        """
        if isinstance(play, str):
            play = load_play(play)

        config = config or get_config()

        if mode == "backtest":
            return PlayEngineFactory._create_backtest(play, config)
        elif mode == "demo":
            return PlayEngineFactory._create_live(play, config, demo=True)
        elif mode == "live":
            return PlayEngineFactory._create_live(play, config, demo=False)
        else:
            raise ValueError(f"Unknown mode: {mode}")

    @staticmethod
    def _create_backtest(play: Play, config: Config) -> PlayEngine:
        # Load historical data
        feed_store = build_feed_store(play, config)

        # Create simulated components
        sim_exchange = SimulatedExchange(play.account, config.risk)

        return PlayEngine(
            play=play,
            data_provider=BacktestDataProvider(feed_store),
            exchange=BacktestExchange(sim_exchange),
            state_store=InMemoryStateStore(),
            risk_config=config.risk,
            mode="backtest",
        )

    @staticmethod
    def _create_live(play: Play, config: Config, demo: bool) -> PlayEngine:
        # Validate mode
        if demo:
            assert os.getenv("BYBIT_USE_DEMO") == "true"
        else:
            assert os.getenv("BYBIT_USE_DEMO") == "false"
            assert os.getenv("TRADING_MODE") == "live"

        # Create live components
        ws_client = BybitWebSocket(demo=demo)
        indicator_cache = LiveIndicatorCache(play)
        order_executor = OrderExecutor(config)
        position_manager = PositionManager(config)

        return PlayEngine(
            play=play,
            data_provider=LiveDataProvider(ws_client, indicator_cache),
            exchange=LiveExchange(order_executor, position_manager),
            state_store=RedisStateStore() if config.use_redis else FileStateStore(),
            risk_config=config.risk,
            mode="demo" if demo else "live",
        )
```

### Runner Implementations

```python
# src/engine/runners/backtest_runner.py

class BacktestRunner:
    """Runs PlayEngine over historical data."""

    def __init__(self, engine: PlayEngine):
        self.engine = engine

    def run(self, start_bar: int = 0, end_bar: int | None = None) -> BacktestResult:
        """Run backtest over bar range."""
        trades = []
        equity_curve = []

        for bar_idx in range(start_bar, end_bar or self.engine.data.num_bars):
            # Process bar (same as live)
            signal = self.engine.process_bar(bar_idx)

            if signal:
                result = self.engine.execute_signal(signal)
                if result.fill:
                    trades.append(result.fill)

            equity_curve.append(self.engine.exchange.get_equity())

        return BacktestResult(trades=trades, equity_curve=equity_curve)


# src/engine/runners/live_runner.py

class LiveRunner:
    """Runs PlayEngine on real-time WebSocket data."""

    def __init__(self, engine: PlayEngine):
        self.engine = engine
        self.running = False

    async def start(self):
        """Start live trading loop."""
        self.running = True

        # Subscribe to candle closes
        await self.engine.data.ws.subscribe_kline(
            symbol=self.engine.play.symbol,
            interval=self.engine.play.execution_tf,
            callback=self._on_candle_close,
        )

        logger.info(f"LiveRunner started: {self.engine.play.name}")

    async def _on_candle_close(self, candle: Candle):
        """Called on each candle close."""
        if not self.running:
            return

        try:
            # Update indicator cache with new candle
            self.engine.data.cache.update(candle)

            # Process bar (SAME CODE as backtest)
            signal = self.engine.process_bar(bar_index=-1)  # -1 = latest

            if signal:
                logger.info(f"Signal generated: {signal}")
                result = self.engine.execute_signal(signal)
                logger.info(f"Execution result: {result}")

        except Exception as e:
            logger.error(f"Error processing candle: {e}")
            # Don't crash - log and continue

    async def stop(self):
        """Stop live trading loop."""
        self.running = False
        await self.engine.data.ws.unsubscribe_all()
        logger.info("LiveRunner stopped")
```

---

## Mode Switching

### Environment Variables

```bash
# .env.demo
BYBIT_USE_DEMO=true
TRADING_MODE=paper
BYBIT_DEMO_API_KEY=xxx
BYBIT_DEMO_API_SECRET=xxx

# .env.live
BYBIT_USE_DEMO=false
TRADING_MODE=live
BYBIT_LIVE_API_KEY=xxx
BYBIT_LIVE_API_SECRET=xxx
```

### CLI Interface

```bash
# Backtest (historical data, simulated execution)
python trade_cli.py play run my_strategy --mode backtest

# Demo (real-time data, demo API, fake money)
python trade_cli.py play run my_strategy --mode demo

# Live (real-time data, live API, real money)
python trade_cli.py play run my_strategy --mode live --confirm
```

### Safety Checks

```python
def validate_mode_switch(target_mode: str) -> None:
    """Validate mode switch is safe."""

    if target_mode == "live":
        # Require explicit confirmation
        if not os.getenv("CONFIRM_LIVE_TRADING"):
            raise ValueError("Live trading requires CONFIRM_LIVE_TRADING=true")

        # Check environment
        if os.getenv("BYBIT_USE_DEMO") == "true":
            raise ValueError("Cannot use live mode with BYBIT_USE_DEMO=true")

        # Verify API keys are live keys
        if "demo" in os.getenv("BYBIT_LIVE_API_KEY", "").lower():
            raise ValueError("Live API key appears to be a demo key")
```

---

## Implementation Phases

### Phase 1: Unified Engine Core (1 week)

```
src/engine/
├── __init__.py
├── interfaces.py        # DataProvider, ExchangeAdapter, StateStore
├── play_engine.py       # Core engine (shared code)
├── factory.py           # PlayEngineFactory
└── adapters/
    ├── __init__.py
    ├── backtest.py      # BacktestDataProvider, BacktestExchange
    └── live.py          # LiveDataProvider, LiveExchange
```

Tasks:
- [ ] Define interfaces (Protocol classes)
- [ ] Extract PlayEngine core from BacktestEngine
- [ ] Create BacktestDataProvider adapter
- [ ] Create BacktestExchange adapter
- [ ] Verify backtest still works with new architecture

### Phase 2: Live Data Provider (1-2 weeks)

```
src/engine/
└── adapters/
    └── live.py
        ├── LiveDataProvider
        ├── LiveIndicatorCache
        └── LiveStructureState
```

Tasks:
- [ ] WebSocket candle subscription
- [ ] Incremental indicator computation
- [ ] Structure state updates on new candles
- [ ] Multi-TF forward-fill handling

### Phase 3: Live Exchange Adapter (1 week)

```
src/engine/
└── adapters/
    └── live.py
        └── LiveExchange
            ├── submit_order() → OrderExecutor
            ├── get_position() → PositionManager
            └── get_balance() → RealtimeState
```

Tasks:
- [ ] Wrap existing OrderExecutor
- [ ] Wire up PositionManager
- [ ] Handle order status tracking
- [ ] Implement TP/SL as exchange orders

### Phase 4: Runners (1 week)

```
src/engine/runners/
├── __init__.py
├── backtest_runner.py   # Loop over historical bars
├── live_runner.py       # WebSocket event loop
└── shadow_runner.py     # Log signals without executing
```

Tasks:
- [ ] BacktestRunner (migrate from current engine)
- [ ] LiveRunner (WebSocket event loop)
- [ ] ShadowRunner (dry-run mode)
- [ ] CLI commands for all modes

### Phase 5: Hardening (1 week)

Tasks:
- [ ] Fix HIGH priority audit findings (H1-H4)
- [ ] Add reconnection monitoring
- [ ] Implement state persistence
- [ ] Add parity tests (backtest vs live signals)
- [ ] Stress test on demo

---

## Parity Testing

### Ensuring Backtest = Live

```python
# tests/parity/test_signal_parity.py

def test_backtest_live_signal_parity():
    """Verify backtest and live produce identical signals."""

    play = load_play("test_strategy")

    # Run backtest
    backtest_engine = PlayEngineFactory.create(play, mode="backtest")
    backtest_signals = []
    for bar in range(1000):
        signal = backtest_engine.process_bar(bar)
        if signal:
            backtest_signals.append((bar, signal))

    # Replay same data through live engine
    live_engine = PlayEngineFactory.create(play, mode="backtest")  # Same data
    live_engine.data = ReplayDataProvider(backtest_engine.data)    # Replay mode
    live_signals = []
    for bar in range(1000):
        signal = live_engine.process_bar(bar)
        if signal:
            live_signals.append((bar, signal))

    # Signals must match exactly
    assert backtest_signals == live_signals
```

---

## Security Audit Findings (To Fix)

### HIGH Priority

| ID | Issue | Fix |
|----|-------|-----|
| H1 | Order price may record as 0 | Fetch avgPrice from order response |
| H2 | WebSocket restart_on_error=False | Enable for production |
| H3 | No clear min order size error | Return detailed error with minimum |
| H4 | Daily PnL resets after 24h not midnight | Use date comparison |

### MEDIUM Priority

| ID | Issue | Fix |
|----|-------|-----|
| M1 | Broad exception handling | Catch specific errors |
| M2 | Clock drift only checked at startup | Periodic re-check |
| M5 | No per-symbol rate limiting | Implement per-symbol limits |
| M6 | Margin mode uses hardcoded leverage | Use config value |

---

## File Locations Reference

### Current (Backtest)

```
src/backtest/
├── engine.py              # BacktestEngine (to be refactored)
├── bar_processor.py       # Per-bar processing
├── sim/
│   ├── exchange.py        # SimulatedExchange
│   ├── types.py           # Order, Position, Fill
│   ├── ledger.py          # Accounting
│   └── execution/         # Fill logic
├── incremental/           # Structure detectors (reuse for live)
├── rules/                 # DSL evaluation (reuse for live)
└── runtime/               # Snapshot, FeedStore (adapt for live)
```

### Current (Live Infrastructure)

```
src/core/
├── order_executor.py      # OrderExecutor (ready to use)
├── risk_manager.py        # RiskManager (ready to use)
├── position_manager.py    # PositionManager (ready to use)
├── exchange_manager.py    # ExchangeManager (ready to use)
└── safety.py              # Panic button (ready to use)

src/exchanges/
├── bybit_client.py        # REST API (ready to use)
├── bybit_websocket.py     # WebSocket (ready to use)
└── bybit_trading.py       # Order placement (ready to use)
```

### New (Unified Engine)

```
src/engine/                # NEW DIRECTORY
├── __init__.py
├── interfaces.py          # Protocol definitions
├── play_engine.py         # Unified core engine
├── factory.py             # Mode-based factory
├── adapters/
│   ├── backtest.py        # Backtest adapters
│   └── live.py            # Live/demo adapters
└── runners/
    ├── backtest_runner.py
    ├── live_runner.py
    └── shadow_runner.py
```

---

## Summary

The architecture provides:

1. **Single codebase** - One PlayEngine class for all modes
2. **Mode switching** - Environment variables control demo/live
3. **Adapter pattern** - Mode differences isolated to adapters
4. **Parity guarantee** - Same signal logic everywhere
5. **Safety first** - Multiple validation layers for live trading

The existing backtest simulator and live infrastructure are both mature. The gap is bridging them with a unified engine that uses the same Play evaluation logic regardless of mode.
