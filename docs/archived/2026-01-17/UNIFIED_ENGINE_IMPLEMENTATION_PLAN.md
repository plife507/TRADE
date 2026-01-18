# Unified Live Trading Architecture Implementation Plan

> **Session Handoff Document**
>
> This document captures the complete implementation plan for the unified PlayEngine architecture.
> It is designed to be picked up in a future session with full context preserved.
>
> **Last Updated:** 2026-01-14
> **Status:** READY FOR IMPLEMENTATION
> **Related Doc:** `docs/architecture/LIVE_TRADING_ARCHITECTURE.md`

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Codebase Readiness Assessment](#codebase-readiness-assessment)
3. [Architecture Design](#architecture-design)
4. [Implementation Phases](#implementation-phases)
5. [File Modification Summary](#file-modification-summary)
6. [Verification Plan](#verification-plan)
7. [Risk Mitigation](#risk-mitigation)
8. [Success Criteria](#success-criteria)
9. [Quick Reference](#quick-reference)

---

## Executive Summary

### Goal

Implement a **unified PlayEngine** that shares code between backtest, demo, and live modes. The key design principle is ensuring **identical signal generation logic** across all modes while using adapters for mode-specific data sources and order execution.

### Current State

Live infrastructure is **90% complete**. The missing piece is the bridge between Play evaluation and live order execution.

| Category | Status |
|----------|--------|
| Application lifecycle management | Complete |
| Order execution pipeline | Complete |
| Position management | Complete |
| Risk management | Complete |
| Exchange manager (Bybit) | Complete |
| WebSocket infrastructure | Complete |
| Demo/live mode switching | Complete |
| **Play → Live execution bridge** | **MISSING** |

### End State

A single factory method that creates an engine for any mode:

```python
# Backtest (historical data, simulated execution)
engine = PlayEngineFactory.create(play, mode="backtest")

# Demo (real-time data, demo API, fake money)
engine = PlayEngineFactory.create(play, mode="demo")

# Live (real-time data, live API, real money)
engine = PlayEngineFactory.create(play, mode="live")
```

---

## Codebase Readiness Assessment

### Production-Ready Components

These components are fully implemented and production-ready:

| Component | File | Lines | Status |
|-----------|------|-------|--------|
| Application Lifecycle | `src/core/application.py` | 695 | Complete |
| Order Execution | `src/core/order_executor.py` | 535 | Complete |
| Position Management | `src/core/position_manager.py` | 550 | Complete |
| Risk Management | `src/core/risk_manager.py` | 540 | Complete |
| Exchange Manager | `src/core/exchange_manager.py` | 450+ | Complete |
| Bybit API Client | `src/exchanges/bybit_client.py` | 598 | Complete |
| WebSocket Streams | `src/exchanges/bybit_websocket.py` | - | Complete |
| Real-time State | `src/data/realtime_state.py` | - | Complete |
| Global Risk View | `src/risk/global_risk.py` | - | Complete |
| Safety/Panic Button | `src/core/safety.py` | - | Complete |
| Demo/Live Switching | Environment-based | - | Strictly Enforced |

### Missing Components

These components need to be built:

| Component | Purpose | Complexity | Priority |
|-----------|---------|------------|----------|
| PlayEngine | Unified core engine (shared by all modes) | HIGH | P0 |
| LiveDataProvider | WebSocket candles to FeedStore-like interface | HIGH | P0 |
| LiveIndicatorCache | Incremental indicator computation | MEDIUM | P0 |
| LiveExchange adapter | Wrap OrderExecutor for unified interface | LOW | P1 |
| LiveRunner | WebSocket event loop for bar processing | MEDIUM | P1 |
| ShadowRunner | Log signals without executing (dry run) | LOW | P2 |

### Security Fixes Required (Pre-Live)

**CRITICAL:** These must be fixed before any live trading:

| ID | Issue | Severity | Location | Fix |
|----|-------|----------|----------|-----|
| H1 | Order price may record as 0 | HIGH | `src/core/order_executor.py` | Fetch avgPrice from order response |
| H2 | WebSocket restart_on_error=False | HIGH | `src/exchanges/bybit_websocket.py` | Enable for production |
| H3 | No clear min order size error | HIGH | `src/core/exchange_manager.py` | Return detailed error with minimum |
| H4 | Daily PnL resets after 24h not midnight | HIGH | `src/core/position_manager.py` | Use date comparison |

### Stubbed Code (Needs Decision)

| File | Status | Recommendation |
|------|--------|----------------|
| `src/core/prices/live_source.py` | STUBBED - NotImplementedError | DELETE (unused) or FULLY IMPLEMENT |

---

## Architecture Design

### High-Level Architecture

```
+---------------------------------------------------------------------+
|                      UNIFIED PLAY ENGINE                             |
|                  (Shared by Backtest + Live)                        |
+---------------------------------------------------------------------+
|  PlayEngine:                                                         |
|   - Play loading & validation                                       |
|   - Feature computation (indicators + structures)                   |
|   - Rule compilation & evaluation                                   |
|   - Signal generation                                               |
|   - Risk sizing                                                     |
|                                                                      |
|  Injected Adapters:                                                 |
|   DataProvider ----+---- BacktestDataProvider (FeedStore)          |
|                    +---- LiveDataProvider (WebSocket + cache)       |
|   ExchangeAdapter -+---- BacktestExchange (SimulatedExchange)      |
|                    +---- LiveExchange (OrderExecutor)               |
|   StateStore ------+---- InMemoryStateStore (backtest)             |
|                    +---- FileStateStore (live recovery)             |
+---------------------------------------------------------------------+
```

### Interface Definitions

```python
# src/engine/interfaces.py

from typing import Protocol

class DataProvider(Protocol):
    """Provides OHLCV and indicator data for the engine."""

    def get_candle(self, symbol: str, tf: str, index: int) -> Candle:
        """Get candle at index (backtest) or latest (live, index=-1)."""
        ...

    def get_indicator(self, symbol: str, tf: str, name: str, index: int) -> float:
        """Get indicator value at index."""
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

### PlayEngine Core

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

        Args:
            bar_index: Index into data arrays (backtest) or -1 for latest (live)

        Returns:
            Signal if entry/exit triggered, None otherwise
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

---

## Implementation Phases

### Phase 1: Interface Definitions & Engine Core (Foundation)

**Objective:** Create the unified engine core with protocol definitions.

**New Files:**
```
src/engine/
+-- __init__.py
+-- interfaces.py          # DataProvider, ExchangeAdapter, StateStore protocols
+-- play_engine.py         # Unified core engine
+-- factory.py             # PlayEngineFactory
```

**Tasks:**

1. **Create `src/engine/interfaces.py`:**
   - Define `DataProvider` protocol (get_candle, get_indicator, get_structure)
   - Define `ExchangeAdapter` protocol (submit_order, cancel_order, get_position, get_balance)
   - Define `StateStore` protocol (save_state, load_state)

2. **Create `src/engine/play_engine.py`:**
   - Extract core signal generation logic from `BacktestEngine`
   - Implement `process_bar(bar_index)` returning Signal or None
   - Implement `execute_signal(signal)` returning OrderResult
   - Use injected adapters for mode-specific behavior

3. **Create `src/engine/factory.py`:**
   - `PlayEngineFactory.create(play, mode="backtest"|"demo"|"live")`
   - Inject appropriate adapters based on mode
   - Validate mode/environment consistency

**Critical Files to Reference:**
- `src/backtest/engine.py` - Extract signal logic
- `src/backtest/bar_processor.py` - Per-bar processing patterns
- `src/backtest/rules/compiled_rule_eval.py` - Rule evaluation

---

### Phase 2: Backtest Adapters (Parity Verification)

**Objective:** Create backtest adapters and verify new engine produces identical results.

**New Files:**
```
src/engine/adapters/
+-- __init__.py
+-- backtest.py            # BacktestDataProvider, BacktestExchange
+-- state.py               # InMemoryStateStore, FileStateStore
```

**Tasks:**

1. **Create `BacktestDataProvider`:**
   ```python
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
   ```

2. **Create `BacktestExchange`:**
   ```python
   class BacktestExchange:
       """Wraps SimulatedExchange for unified interface."""

       def __init__(self, sim_exchange: SimulatedExchange):
           self.sim = sim_exchange

       def submit_order(self, order: Order) -> OrderResult:
           return self.sim.submit_order(order)

       def get_position(self, symbol: str) -> Position | None:
           return self.sim.position
   ```

3. **Create `InMemoryStateStore`:**
   - Simple dict-based state for backtest (no persistence needed)

4. **CRITICAL - Parity Test:**
   - Run same Play with old BacktestEngine and new PlayEngine
   - Compare trade hashes - MUST match exactly
   - This validates the refactor before touching live code

**Critical Files to Reference:**
- `src/backtest/sim/exchange.py` - SimulatedExchange
- `src/backtest/runtime/feed_store.py` - FeedStore
- `src/backtest/incremental/state.py` - MultiTFIncrementalState

---

### Phase 3: Live Data Provider

**Objective:** Create adapters for real-time WebSocket data.

**New Files:**
```
src/engine/adapters/
+-- live.py
    +-- LiveDataProvider
    +-- LiveIndicatorCache
    +-- LiveStructureState
```

**Tasks:**

1. **Create `LiveDataProvider`:**
   - Subscribe to WebSocket kline candle closes
   - Maintain rolling buffer of last N candles (configurable, default 500)
   - `get_candle(index=-1)` returns latest closed candle
   - `get_candle(index=-5)` returns 5 candles ago

2. **Create `LiveIndicatorCache`:**
   - Receive candle updates, compute indicators incrementally
   - Use SAME indicator functions as backtest
   - Store last N indicator values for lookback requirements
   - Handle warmup period (need ~100-200 bars for most indicators)

3. **Create `LiveStructureState`:**
   - Wrap `MultiTFIncrementalState` from `src/backtest/incremental/`
   - Update on each new candle close
   - **CRITICAL:** Reuse ALL incremental detection logic (swing, trend, zones)
   - This ensures parity between backtest and live structure detection

**Critical Files to Reference:**
- `src/data/realtime_bootstrap.py` - WebSocket subscription patterns
- `src/data/realtime_state.py` - State management patterns
- `src/backtest/incremental/state.py` - Reuse directly
- `src/backtest/features/` - Indicator computation

---

### Phase 4: Live Exchange Adapter

**Objective:** Create adapter to wrap existing live trading infrastructure.

**New File Additions:**
```
src/engine/adapters/
+-- live.py
    +-- LiveExchange (add to existing file)
```

**Tasks:**

1. **Create `LiveExchange`:**
   ```python
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

2. **Wire up order tracking:**
   - Map internal Order to OrderExecutor signal format
   - Handle fill confirmations from WebSocket
   - Track pending orders for duplicate prevention

3. **Handle TP/SL:**
   - Submit as conditional orders to exchange (not simulated)
   - Track order status for position management
   - Handle partial fills

**Critical Files to Reference:**
- `src/core/order_executor.py` - Existing execution logic
- `src/core/position_manager.py` - Existing position tracking
- `src/core/exchange_manager.py` - Order submission methods

---

### Phase 5: Runners & CLI

**Objective:** Create runner classes that drive the engine in different modes.

**New Files:**
```
src/engine/runners/
+-- __init__.py
+-- backtest_runner.py     # Loop over historical bars
+-- live_runner.py         # WebSocket event loop
+-- shadow_runner.py       # Log signals without executing
```

**Tasks:**

1. **Create `BacktestRunner`:**
   ```python
   class BacktestRunner:
       """Runs PlayEngine over historical data."""

       def __init__(self, engine: PlayEngine):
           self.engine = engine

       def run(self, start_bar: int = 0, end_bar: int | None = None) -> BacktestResult:
           trades = []
           equity_curve = []

           for bar_idx in range(start_bar, end_bar or self.engine.data.num_bars):
               signal = self.engine.process_bar(bar_idx)
               if signal:
                   result = self.engine.execute_signal(signal)
                   if result.fill:
                       trades.append(result.fill)
               equity_curve.append(self.engine.exchange.get_equity())

           return BacktestResult(trades=trades, equity_curve=equity_curve)
   ```

2. **Create `LiveRunner`:**
   ```python
   class LiveRunner:
       """Runs PlayEngine on real-time WebSocket data."""

       async def start(self):
           self.running = True
           await self.engine.data.ws.subscribe_kline(
               symbol=self.engine.play.symbol,
               interval=self.engine.play.execution_tf,
               callback=self._on_candle_close,
           )

       async def _on_candle_close(self, candle: Candle):
           if not self.running:
               return

           self.engine.data.cache.update(candle)
           signal = self.engine.process_bar(bar_index=-1)  # -1 = latest

           if signal:
               result = self.engine.execute_signal(signal)
               logger.info(f"Execution result: {result}")
   ```

3. **Create `ShadowRunner`:**
   - Same as LiveRunner but logs signals without executing
   - For paper testing before going live
   - Useful for validating signal generation matches expectations

4. **Add CLI commands:**
   ```bash
   python trade_cli.py play run <play_id> --mode backtest
   python trade_cli.py play run <play_id> --mode demo
   python trade_cli.py play run <play_id> --mode live --confirm
   python trade_cli.py play run <play_id> --mode shadow
   ```

**Critical Files to Reference:**
- `src/backtest/engine.py` - Current run loop pattern
- `src/core/application.py` - Lifecycle patterns
- `trade_cli.py` - CLI structure and argument parsing

---

### Phase 6: Security Hardening

**Objective:** Fix all HIGH priority security issues before live trading.

**Tasks:**

1. **Fix H1 (order price=0):**
   - File: `src/core/order_executor.py`
   - Issue: Order price recorded as 0 for market orders
   - Fix: Extract avgPrice from order response, not request

2. **Fix H2 (WebSocket restart):**
   - File: `src/exchanges/bybit_websocket.py`
   - Issue: `restart_on_error=False` by default
   - Fix: Set `restart_on_error=True` for production modes

3. **Fix H3 (min order error):**
   - File: `src/core/exchange_manager.py`
   - Issue: No clear error when order below minimum
   - Fix: Return detailed error with minimum size requirement

4. **Fix H4 (daily PnL reset):**
   - File: `src/core/position_manager.py`
   - Issue: Daily PnL resets after 24h rolling, not at midnight
   - Fix: Use date comparison instead of timedelta

5. **Add reconnection monitoring:**
   - Heartbeat checks for WebSocket
   - Auto-reconnect with exponential backoff
   - Alert/log on prolonged disconnection

---

### Phase 7: Parity Testing & Documentation

**Objective:** Ensure backtest and live generate identical signals, document everything.

**Tasks:**

1. **Create parity test:**
   ```python
   def test_backtest_live_signal_parity():
       """Verify backtest and live produce identical signals."""
       play = load_play("test_strategy")

       # Run backtest
       backtest_engine = PlayEngineFactory.create(play, mode="backtest")
       backtest_signals = collect_signals(backtest_engine)

       # Replay same data through live engine
       live_engine = PlayEngineFactory.create(play, mode="backtest")
       live_engine.data = ReplayDataProvider(backtest_engine.data)
       live_signals = collect_signals(live_engine)

       # Signals must match exactly
       assert backtest_signals == live_signals
   ```

2. **Create validation Play:**
   ```yaml
   # tests/validation/plays/V_LIVE_001_demo_canary.yml
   # Simple Play for demo mode smoke testing
   name: "V_LIVE_001_demo_canary"
   description: "Validates live trading pipeline"
   symbol: "BTCUSDT"
   tf: "5m"  # Short TF for quick testing
   # ... minimal config for signal generation
   ```

3. **Documentation:**
   - `docs/guides/LIVE_TRADING_SETUP.md` - API keys, env vars, first run
   - `docs/guides/LIVE_TRADING_RUNBOOK.md` - Operations, emergency procedures

---

## File Modification Summary

### New Files (17 files)

```
src/engine/
+-- __init__.py
+-- interfaces.py
+-- play_engine.py
+-- factory.py
+-- adapters/
|   +-- __init__.py
|   +-- backtest.py
|   +-- live.py
|   +-- state.py
+-- runners/
    +-- __init__.py
    +-- backtest_runner.py
    +-- live_runner.py
    +-- shadow_runner.py

tests/validation/plays/
+-- V_LIVE_001_demo_canary.yml

docs/guides/
+-- LIVE_TRADING_SETUP.md
+-- LIVE_TRADING_RUNBOOK.md
```

### Modified Files (8 files)

| File | Change |
|------|--------|
| `src/core/order_executor.py` | H1 fix - avgPrice extraction |
| `src/core/position_manager.py` | H4 fix - date comparison for PnL reset |
| `src/core/exchange_manager.py` | H3 fix - detailed min order error |
| `src/exchanges/bybit_websocket.py` | H2 fix - restart_on_error=True |
| `src/core/prices/live_source.py` | DELETE or fully implement |
| `trade_cli.py` | Add `play run` commands |
| `src/cli/smoke_tests/__init__.py` | Export live smoke test |
| `src/cli/smoke_tests/core.py` | Wire live smoke test |

### Deprecated/Removed (1 file)

| File | Reason |
|------|--------|
| `src/core/prices/live_source.py` | Stubbed with NotImplementedError, unused |

---

## Verification Plan

### Phase 1-2: Backtest Parity

```bash
# Run existing backtest
python trade_cli.py backtest run V_100_core_dsl --verbose

# Run new PlayEngine backtest (after Phase 2)
python trade_cli.py play run V_100_core_dsl --mode backtest --verbose

# Compare trade hashes - must match exactly
# If not identical, debug before proceeding
```

### Phase 3-5: Demo Mode

```bash
# Set demo environment
export BYBIT_USE_DEMO=true
export TRADING_MODE=paper

# Run in shadow mode first (logs only)
python trade_cli.py play run V_LIVE_001_demo_canary --mode shadow

# Run in demo mode (fake money)
python trade_cli.py play run V_LIVE_001_demo_canary --mode demo

# Verify:
# - WebSocket connects successfully
# - Candles received on schedule
# - Signals generated on bar close
# - Orders placed on demo API
# - Position tracked correctly
```

### Phase 6: Security

```bash
# Run security audit
python -m src.forge.audits.security_check

# Manual verification for each fix:
# H1: Place order, verify price recorded correctly
# H2: Kill WebSocket connection, verify auto-reconnect
# H3: Place tiny order, verify clear error message with minimum
# H4: Check PnL reset at midnight, not 24h rolling
```

### Full Integration

```bash
# Run full smoke suite including live components
python trade_cli.py --smoke full

# Run validation Plays
python trade_cli.py backtest run --dir tests/validation/plays --fix-gaps
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking backtest during refactor | Phase 2 parity testing before touching live code |
| Live bugs not caught in backtest | Shadow mode for signal-only testing |
| Real money losses | Demo trading mandatory before live |
| Security vulnerabilities | H1-H4 must be fixed before live |
| Crash recovery | FileStateStore for live mode state persistence |
| WebSocket disconnection | Auto-reconnect with exponential backoff |

---

## Success Criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | `PlayEngineFactory.create(play, mode="backtest")` produces identical results to old engine | Parity test passes |
| 2 | `PlayEngineFactory.create(play, mode="demo")` successfully trades on Bybit demo | Demo canary Play works |
| 3 | Same Play generates same signals in backtest replay vs live replay | Parity test passes |
| 4 | All HIGH security issues (H1-H4) fixed | Security audit clean |
| 5 | WebSocket auto-reconnects on disconnection | Manual testing |
| 6 | CLI commands work for all modes | `--smoke full` passes |
| 7 | Smoke tests pass for live components | CI green |

---

## Quick Reference

### Key Entry Points

| Purpose | Command |
|---------|---------|
| Backtest a Play | `python trade_cli.py backtest run <play_id>` |
| Run Play in demo | `python trade_cli.py play run <play_id> --mode demo` |
| Run Play in live | `python trade_cli.py play run <play_id> --mode live --confirm` |
| Shadow mode | `python trade_cli.py play run <play_id> --mode shadow` |
| Smoke test | `python trade_cli.py --smoke full` |

### Environment Variables

```bash
# Demo mode
BYBIT_USE_DEMO=true
TRADING_MODE=paper
BYBIT_DEMO_API_KEY=xxx
BYBIT_DEMO_API_SECRET=xxx

# Live mode
BYBIT_USE_DEMO=false
TRADING_MODE=live
BYBIT_LIVE_API_KEY=xxx
BYBIT_LIVE_API_SECRET=xxx
CONFIRM_LIVE_TRADING=true  # Required for live
```

### Key Files for Implementation

| Category | Files |
|----------|-------|
| Signal generation | `src/backtest/engine.py`, `src/backtest/bar_processor.py` |
| Rule evaluation | `src/backtest/rules/compiled_rule_eval.py` |
| Data access | `src/backtest/runtime/feed_store.py` |
| Simulated exchange | `src/backtest/sim/exchange.py` |
| Live order execution | `src/core/order_executor.py` |
| Live position tracking | `src/core/position_manager.py` |
| WebSocket | `src/exchanges/bybit_websocket.py`, `src/data/realtime_bootstrap.py` |
| Incremental structures | `src/backtest/incremental/state.py` |

---

## Session Handoff Notes

**To continue implementation:**

1. Start with Phase 1 - Create `src/engine/` directory and interface definitions
2. Extract core logic from `BacktestEngine` carefully, maintaining all behavior
3. Use parity testing in Phase 2 to validate refactor before proceeding
4. Shadow mode (Phase 5) is critical for safe live testing
5. Security fixes (Phase 6) are BLOCKERS for live trading

**Dependencies:**
- Phase 2 depends on Phase 1
- Phase 3-4 can be done in parallel after Phase 2
- Phase 5 depends on Phase 3-4
- Phase 6 can be done in parallel with Phases 3-5
- Phase 7 depends on all previous phases

**Estimated Effort:**
- Phase 1: 1-2 days
- Phase 2: 1-2 days
- Phase 3: 2-3 days
- Phase 4: 1 day
- Phase 5: 1-2 days
- Phase 6: 1 day
- Phase 7: 1 day
- **Total: 8-12 days**

---

## Multi-Instance Architecture (Live + Backtest Simultaneously)

### Current State: NOT READY

The current architecture has **critical blockers** preventing reliable multi-instance execution:

| Blocker | Severity | Description |
|---------|----------|-------------|
| DuckDB Concurrent Access | **CRITICAL** | Single-file database with no concurrent write support |
| Global Singletons | **HIGH** | RealtimeState, Application, PanicState shared globally |
| No Rate Limit Coordination | **MEDIUM** | Multiple instances exceed per-account API limits |
| Single Connection per Store | **HIGH** | One DuckDB connection per environment |

### Blocking Scenarios

#### Scenario 1: Backtest + Live Sync = DEADLOCK
```
T0: BacktestEngine.run() calls get_historical_store("live")
    → Acquires duckdb.connect() connection A
    → Starts SELECT on OHLCV table

T1: LiveSession starts data sync on funding rates
    → get_historical_store("live") returns SAME connection A
    → Tries INSERT INTO funding table
    → BLOCKS waiting for SELECT lock to release

T2: BacktestEngine still in hot loop reading OHLCV
    → DuckDB is now locked
    → BACKTEST STALLS, LIVE SYNC BLOCKED
```

#### Scenario 2: RealtimeState Pollution
```
T0: LiveSession WebSocket receives position update
    → RealtimeState._positions updated with real data

T1: BacktestEngine.run() uses get_realtime_state()
    → Gets polluted state with live WebSocket data
    → Strategy uses stale live prices instead of historical
    → BACKTEST RESULTS INVALID
```

#### Scenario 3: Panic Cascade
```
T0: BacktestEngine validation fails
    → get_panic_state().trigger("Invalid backtest data")

T1: LiveSession's trading loop calls check_panic_and_halt()
    → Finds panic triggered by backtest
    → LIVE TRADING HALTED due to unrelated backtest failure
```

### Resource Contention Matrix

| Resource | Backtest Usage | Live Usage | Conflict | Severity |
|----------|----------------|------------|----------|----------|
| DuckDB File | Read OHLCV | Read/Write Sync | Write lock blocks reads | **CRITICAL** |
| RealtimeState | Read synthetic | Read/Write WebSocket | State pollution | **HIGH** |
| Application | N/A | Singleton | Only 1 instance allowed | **HIGH** |
| PanicState | Can trigger | Receives trigger | Cross-contamination | **HIGH** |
| RateLimiters | Per-instance | Per-instance | No global accounting | **MEDIUM** |
| BybitClient | 1 instance | N instances | Rate limit exceeded | **MEDIUM** |
| Logger | Shared | Shared | Interleaved output | **LOW** |

### Global Singletons to Fix

| File | Singleton | Issue |
|------|-----------|-------|
| `src/data/historical_data_store.py:1675` | `_store_live`, `_store_demo` | Single DuckDB connection per env |
| `src/data/realtime_state.py:912` | `_realtime_state` | WebSocket state shared globally |
| `src/core/application.py:82` | `Application._instance` | Only 1 live Application allowed |
| `src/core/safety.py:66` | `_panic_state` | Panic affects all instances |

### Immediate Workaround (No Code Changes)

Until multi-instance is properly implemented:

1. **Run backtest on DEMO env, live on LIVE env** - Different DuckDB files
2. **Sequential execution** - Backtest first, then start live trading
3. **Time-based separation** - Run backtests when live trading is inactive

### Phase 8: Multi-Instance Support (Future)

**Objective:** Enable simultaneous backtest and live trading.

**New Files:**
```
src/data/
+-- connection_pool.py     # DuckDB connection pooling
+-- scoped_state.py        # Instance-scoped state manager

src/engine/
+-- instance_manager.py    # Multi-instance coordination
```

**Tasks:**

1. **DuckDB Connection Pooling:**
   ```python
   class ConnectionPool:
       """Thread-safe DuckDB connection pool with WAL mode."""

       def __init__(self, db_path: Path, pool_size: int = 5):
           self.db_path = db_path
           self._pool: queue.Queue[duckdb.DuckDBPyConnection] = queue.Queue(pool_size)
           self._init_pool()

       def _init_pool(self):
           # Enable WAL mode for concurrent reads
           conn = duckdb.connect(str(self.db_path))
           conn.execute("PRAGMA journal_mode=WAL")
           conn.close()

           for _ in range(self.pool_size):
               self._pool.put(duckdb.connect(str(self.db_path), read_only=False))

       @contextmanager
       def get_connection(self, timeout: float = 5.0) -> duckdb.DuckDBPyConnection:
           conn = self._pool.get(timeout=timeout)
           try:
               yield conn
           finally:
               self._pool.put(conn)
   ```

2. **Instance-Scoped State:**
   ```python
   class ScopedState:
       """State container scoped to a single engine instance."""

       def __init__(self, instance_id: str, mode: Literal["backtest", "live"]):
           self.instance_id = instance_id
           self.mode = mode
           self._positions: dict[str, Position] = {}
           self._candle_buffers: dict[str, deque] = {}
           # ... instance-local state
   ```

3. **Global Rate Limit Accounting:**
   ```python
   class GlobalRateLimiter:
       """Account-level rate limiter shared across all instances."""

       _instance: 'GlobalRateLimiter | None' = None
       _lock = threading.Lock()

       def __init__(self, max_rps: int = 45):
           self.max_rps = max_rps
           self._tokens = TokenBucket(max_rps, 1.0)

       @classmethod
       def get_instance(cls) -> 'GlobalRateLimiter':
           with cls._lock:
               if cls._instance is None:
                   cls._instance = cls()
               return cls._instance

       def acquire(self, tokens: int = 1) -> bool:
           """Request tokens from global pool."""
           return self._tokens.acquire(tokens)
   ```

4. **Instance-Scoped Panic State:**
   ```python
   class InstancePanicState:
       """Panic state scoped to instance, with optional global escalation."""

       def __init__(self, instance_id: str):
           self.instance_id = instance_id
           self._is_panicked = False
           self._panic_reason: str | None = None

       def trigger(self, reason: str, escalate_global: bool = False):
           self._is_panicked = True
           self._panic_reason = reason
           if escalate_global:
               get_global_panic_state().trigger(f"[{self.instance_id}] {reason}")
   ```

5. **Modify Singletons to Instance-Scoped:**

   | Current | Change To |
   |---------|-----------|
   | `get_historical_store()` | `ConnectionPool.get_connection()` |
   | `get_realtime_state()` | `ScopedState(instance_id)` |
   | `get_application()` | Per-instance Application |
   | `get_panic_state()` | `InstancePanicState(instance_id)` |

**Files to Modify:**
- `src/data/historical_data_store.py` - Connection pooling
- `src/data/realtime_state.py` - Instance scoping
- `src/core/application.py` - Remove singleton pattern
- `src/core/safety.py` - Instance-scoped panic
- `src/utils/rate_limiter.py` - Global accounting

**Estimated Effort:** 2-3 days

### Multi-Instance Architecture Diagram

```
+-----------------------------------------------------------------------+
|                         INSTANCE MANAGER                               |
|                   (Coordinates multiple engines)                       |
+-----------------------------------------------------------------------+
        |                        |                        |
        v                        v                        v
+------------------+    +------------------+    +------------------+
|   BACKTEST       |    |   DEMO           |    |   LIVE           |
|   INSTANCE       |    |   INSTANCE       |    |   INSTANCE       |
+------------------+    +------------------+    +------------------+
| ScopedState      |    | ScopedState      |    | ScopedState      |
| (isolated)       |    | (isolated)       |    | (isolated)       |
+------------------+    +------------------+    +------------------+
        |                        |                        |
        +------------------------+------------------------+
                                 |
                                 v
+-----------------------------------------------------------------------+
|                       SHARED RESOURCES                                 |
+-----------------------------------------------------------------------+
| ConnectionPool (DuckDB WAL mode, thread-safe)                         |
| GlobalRateLimiter (account-level RPS enforcement)                     |
| GlobalPanicState (system-level emergencies only)                      |
+-----------------------------------------------------------------------+
```

### Verification for Multi-Instance

```bash
# Test concurrent execution
python -c "
import threading
import time

def run_backtest():
    # python trade_cli.py backtest run V_100_core_dsl
    pass

def run_live():
    # python trade_cli.py play run V_LIVE_001 --mode demo
    pass

t1 = threading.Thread(target=run_backtest)
t2 = threading.Thread(target=run_live)

t1.start()
t2.start()

t1.join()
t2.join()

print('Both completed without deadlock')
"

# Verify no state pollution
python trade_cli.py backtest run V_100_core_dsl --verify-isolation
```

### Success Criteria for Multi-Instance

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | Backtest and live can run simultaneously | No deadlock in 10-minute test |
| 2 | DuckDB has no write lock contention | WAL mode enabled, pool works |
| 3 | State isolation verified | Backtest doesn't see live prices |
| 4 | Panic states isolated | Backtest panic doesn't stop live |
| 5 | API rate limits respected | Combined RPS < account limit |
