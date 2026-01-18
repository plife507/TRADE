# Engine Naming Convention

**STATUS:** CANONICAL
**UPDATED:** 2026-01-15
**REF:** `docs/todos/UNIFIED_ENGINE_PLAN.md`

Professional naming standards for the TRADE unified engine architecture.

---

## Architecture Summary

**ONE UNIFIED ENGINE** - `PlayEngine` in `src/engine/` is THE engine.

```
src/engine/                 # THE unified engine (PlayEngine)
|-- play_engine.py          # Core signal logic
|-- signal/                 # Shared signal evaluation
|   |-- subloop.py          # 1m sub-loop logic
|   `-- __init__.py
|-- adapters/               # Mode-specific adapters
|   |-- backtest.py         # BacktestDataProvider, BacktestExchange
|   `-- live.py             # LiveDataProvider, LiveExchange
|-- runners/                # Execution loops
|   |-- backtest_runner.py  # Historical bar iteration
|   `-- live_runner.py      # WebSocket event loop
|-- factory.py              # PlayEngineFactory
`-- interfaces.py           # DataProvider, ExchangeAdapter protocols

src/backtest/               # Infrastructure ONLY (not an engine)
|-- sim/                    # SimulatedExchange, SimulatedRiskManager
|-- runtime/                # FeedStore, Snapshot, TFContext
|-- features/               # FeatureSpec, indicator setup
`-- [engine.py]             # DEPRECATED - being deleted after migration

src/indicators/             # Shared indicator computation (NEW)
|-- registry.py             # IndicatorRegistry (unified)
|-- compute.py              # Indicator computation
|-- metadata.py             # Indicator metadata
`-- builder.py              # Feature building

src/structures/             # Shared structure detection (NEW)
|-- registry.py             # StructureRegistry (unified)
|-- detectors/              # Swing, Trend, Zone detectors
|-- state.py                # Structure state management
`-- types.py                # Structure types
```

---

## Domain Sectors

| Sector | Prefix | Purpose | Location |
|--------|--------|---------|----------|
| **Engine** | `Play*` | Unified engine core | `src/engine/` |
| **Sim** | `Sim*` | Backtest simulation | `src/backtest/sim/` |
| **Live** | `Live*` | Live/demo trading | `src/engine/adapters/live.py` |
| **Indicator** | `Indicator*` | Shared indicators | `src/indicators/` |
| **Structure** | `Structure*` | Shared structures | `src/structures/` |
| **Data** | `Data*` | Data loading | `src/data/` |

---

## Canonical Name Mapping

### Engines

| Name | Purpose | Location |
|------|---------|----------|
| `PlayEngine` | THE unified engine | `src/engine/play_engine.py` |
| `BacktestEngine` | **DEPRECATED** - being deleted | `src/backtest/engine.py` |

**IMPORTANT:** There is only ONE engine now. `BacktestEngine` in `src/backtest/engine.py` is legacy code being migrated to `PlayEngine`.

### Factories

| Name | Purpose | Location |
|------|---------|----------|
| `PlayEngineFactory.create()` | Create unified engine | `src/engine/factory.py` |
| `create_backtest_engine()` | **DEPRECATED** | `src/backtest/engine_factory.py` |

### Adapters (Protocol Implementations)

| Name | Purpose | Location |
|------|---------|----------|
| `BacktestDataProvider` | FeedStore wrapper for backtest | `src/engine/adapters/backtest.py` |
| `BacktestExchange` | SimulatedExchange wrapper | `src/engine/adapters/backtest.py` |
| `LiveDataProvider` | WebSocket data wrapper | `src/engine/adapters/live.py` |
| `LiveExchange` | Bybit API wrapper | `src/engine/adapters/live.py` |

### Runners (Execution Loops)

| Name | Purpose | Location |
|------|---------|----------|
| `BacktestRunner` | Drive engine through historical bars | `src/engine/runners/backtest_runner.py` |
| `LiveRunner` | WebSocket event loop | `src/engine/runners/live_runner.py` |

### Protocols (Interfaces)

| Name | Purpose | Location |
|------|---------|----------|
| `DataProvider` | Market data protocol | `src/engine/interfaces.py` |
| `ExchangeAdapter` | Order execution protocol | `src/engine/interfaces.py` |

### Shared Modules

| Name | Purpose | Location |
|------|---------|----------|
| `IndicatorRegistry` | Unified indicator registry | `src/indicators/registry.py` |
| `StructureRegistry` | Unified structure registry | `src/structures/registry.py` |
| `SubloopEvaluator` | 1m sub-loop evaluation | `src/engine/signal/subloop.py` |

---

## Method Naming Standards

### Prefixes

| Prefix | Meaning | Example |
|--------|---------|---------|
| `build_` | Construct new object | `build_feed_stores()` |
| `load_` | Load from external source | `load_candles()` |
| `prepare_` | Transform data for use | `prepare_frame()` |
| `evaluate_` | Execute rules/conditions | `evaluate_rules()` |
| `process_` | Handle state machine step | `process_bar()` |
| `update_` | Modify existing state | `update_indices()` |
| `get_` | Retrieve value (no side effects) | `get_candle()` |
| `compute_` | Calculate derived value | `compute_metrics()` |

### Suffixes

| Suffix | Meaning | Example |
|--------|---------|---------|
| `_config` | Configuration object | `risk_config` |
| `_result` | Operation outcome | `bar_result` |
| `_state` | Mutable state container | `incremental_state` |
| `_feed` | FeedStore instance | `exec_feed` |
| `_idx` | Array/bar index | `current_idx` |

---

## Quick Reference

| When you mean... | Say... |
|------------------|--------|
| The unified engine | `PlayEngine` |
| Create an engine | `PlayEngineFactory.create()` |
| Backtest data wrapper | `BacktestDataProvider` |
| Backtest exchange wrapper | `BacktestExchange` |
| The backtest loop | `BacktestRunner` |
| Indicator computation | `IndicatorRegistry` |
| Structure detection | `StructureRegistry` |

---

## Anti-Patterns (AVOID)

| Do Not Say | Say Instead |
|------------|-------------|
| "BacktestEngine" | `PlayEngine` (with backtest adapter) |
| "old engine" | Be specific about the component |
| "new engine" | `PlayEngine` |
| "two engines" | ONE engine: `PlayEngine` |
| "engine.py" | Specify: `src/engine/play_engine.py` or `src/backtest/engine.py` (deprecated) |

---

## Migration Status

The unified engine migration is IN PROGRESS. See `docs/todos/UNIFIED_ENGINE_PLAN.md` for:
- Current gate status
- Baseline validation metrics
- Trade hash references for regression detection
