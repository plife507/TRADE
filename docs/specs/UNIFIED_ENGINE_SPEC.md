# Unified Engine Architecture Specification

**Version:** 1.0
**Date:** 2026-01-15
**Status:** CANONICAL

---

## Overview

ONE engine (`PlayEngine`) for backtest/live trading - ZERO spec drift.

The unified engine architecture eliminates duplicate signal evaluation, timeframe management, and position sizing logic. Mode-specific behavior is handled by adapters and runners.

---

## Architecture Diagram

```
                           +------------------+
                           |    PlayEngine    |
                           |  (Core Logic)    |
                           +--------+---------+
                                    |
              +---------------------+---------------------+
              |                     |                     |
     +--------v--------+   +--------v--------+   +--------v--------+
     |    Signal/      |   |   Timeframe/    |   |    Sizing/      |
     |   subloop.py    |   | index_manager   |   |    model.py     |
     +--------+--------+   +--------+--------+   +--------+--------+
              |                     |                     |
              +---------------------+---------------------+
                                    |
              +---------------------+---------------------+
              |                                           |
     +--------v--------+                         +--------v--------+
     | BacktestAdapter |                         |   LiveAdapter   |
     | - DataProvider  |                         | - DataProvider  |
     | - Exchange      |                         | - Exchange      |
     +--------+--------+                         +--------+--------+
              |                                           |
     +--------v--------+                         +--------v--------+
     | BacktestRunner  |                         |   LiveRunner    |
     | (bar iteration) |                         | (WebSocket loop)|
     +-----------------+                         +-----------------+
```

---

## Directory Structure

```
src/engine/                    # THE unified engine
|-- __init__.py
|-- play_engine.py             # Core signal logic
|-- interfaces.py              # DataProvider, ExchangeAdapter protocols
|-- factory.py                 # PlayEngineFactory
|-- signal/
|   |-- __init__.py
|   `-- subloop.py             # 1m sub-loop evaluation
|-- timeframe/
|   |-- __init__.py
|   `-- index_manager.py       # Forward-fill index tracking
|-- sizing/
|   |-- __init__.py
|   `-- model.py               # SizingModel
|-- adapters/
|   |-- __init__.py
|   |-- backtest.py            # BacktestDataProvider, BacktestExchange
|   `-- live.py                # LiveDataProvider, LiveExchange
`-- runners/
    |-- __init__.py
    |-- backtest_runner.py     # Historical bar iteration
    `-- live_runner.py         # WebSocket event loop

src/backtest/                  # Infrastructure ONLY
|-- sim/                       # SimulatedExchange, SimulatedRiskManager
|-- runtime/                   # FeedStore, Snapshot, TFContext
|-- features/                  # FeatureSpec, indicator setup
`-- engine.py                  # Legacy engine (retained for reference)
```

---

## Core Components

### PlayEngine

The central signal evaluation engine. Does NOT know about data sources or execution - uses protocols.

```python
class PlayEngine:
    def __init__(
        self,
        play: Play,
        data_provider: DataProvider,
        exchange: ExchangeAdapter,
    ):
        pass

    def evaluate_bar(self, bar_time: int) -> BarResult:
        """Evaluate signals for a single bar."""
        pass

    def process_signal(self, signal: Signal) -> OrderResult:
        """Process a signal through the exchange adapter."""
        pass
```

### DataProvider Protocol

Abstract interface for market data access.

```python
class DataProvider(Protocol):
    def get_snapshot(self, bar_time: int) -> SnapshotView:
        """Get snapshot at bar_time with all indicators computed."""
        pass

    def get_candle(self, role: str, offset: int = 0) -> Candle:
        """Get candle for timeframe role (exec, high_tf, med_tf, low_tf)."""
        pass

    def advance_to(self, bar_time: int) -> None:
        """Advance internal state to bar_time."""
        pass
```

### ExchangeAdapter Protocol

Abstract interface for order execution.

```python
class ExchangeAdapter(Protocol):
    def submit_order(self, order: Order) -> OrderResult:
        """Submit an order for execution."""
        pass

    def get_position(self) -> Position | None:
        """Get current position state."""
        pass

    def get_equity(self) -> float:
        """Get current equity (for sizing)."""
        pass
```

---

## Multi-Timeframe Architecture

### tf_mapping Schema

Plays define timeframe roles for multi-TF strategies:

```yaml
tf_mapping:
  exec: "15m"      # Bar-by-bar evaluation
  high_tf: "4h"    # Higher timeframe context
  med_tf: "1h"     # Medium timeframe structure
  low_tf: "5m"     # Lower timeframe entries
```

| Role Key | Category | Valid Values | Purpose |
|----------|----------|--------------|---------|
| `exec` | ExecTF | LowTF or MedTF | Bar-by-bar signal evaluation |
| `high_tf` | HighTF | 6h, 12h, D | Trend context, major S/R |
| `med_tf` | MedTF | 30m, 1h, 2h, 4h | Structure, bias |
| `low_tf` | LowTF | 1m, 3m, 5m, 15m | Micro-structure, entries |

### FeedStore Roles

The FeedStore provides role-based access to timeframe data:

```python
# Access by role
high_tf_data = feed_store.get_frame("high_tf")
med_tf_data = feed_store.get_frame("med_tf")
low_tf_data = feed_store.get_frame("low_tf")
exec_data = feed_store.get_frame("exec")
```

### Forward-Fill Semantics

Higher timeframes forward-fill until their bar closes:

```
exec_tf = 15m, high_tf = 4h

Time 09:00 -> high_tf shows 08:00 bar (not closed yet)
Time 09:15 -> high_tf shows 08:00 bar
Time 09:30 -> high_tf shows 08:00 bar
Time 09:45 -> high_tf shows 08:00 bar
Time 10:00 -> high_tf shows 08:00 bar
Time 10:15 -> high_tf shows 08:00 bar
...
Time 11:45 -> high_tf shows 08:00 bar
Time 12:00 -> high_tf shows 12:00 bar (NEW - just closed)
```

---

## Data Flow

### CLI to Engine

```
CLI --data-env flag
       |
       v
RunnerConfig.data_env
       |
       v
create_engine_from_play()
       |
       v
SystemConfig.DataBuildConfig.data_env
       |
       v
FeedStore data loading (selects database)
```

### 3-Database Architecture

| Database | API Source | Purpose |
|----------|------------|---------|
| `market_data_backtest.duckdb` | api.bybit.com | Backtests (default) |
| `market_data_live.duckdb` | api.bybit.com | Live trading warm-up |
| `market_data_demo.duckdb` | api-demo.bybit.com | Paper trading |

---

## Position Management

### Position Modes

| Config | Meaning |
|--------|---------|
| `position_policy.mode: long_short` | Trade both directions sequentially |
| `position_mode: oneway` (exchange) | No simultaneous long+short |

**Clarification:** `long_short` means the strategy can go long OR short sequentially (closing one before opening the other). The exchange is configured in one-way mode (not hedge mode where you could hold both long and short simultaneously).

### Position Tracking

The BacktestRunner tracks position duration:

```python
# In BacktestRunner
if self.position is not None:
    self.bars_in_position += 1
else:
    self.bars_in_position = 0
```

This enables "Time in Market" metrics in backtest results.

---

## Signal Evaluation

### 1m Sub-loop

For coarse exec_tf (e.g., 15m), the engine evaluates signals at 1m granularity:

```
exec_tf = 15m bar at 09:00

Sub-loop evaluates at:
  09:01, 09:02, 09:03, ... 09:14

If signal triggers at 09:07:
  - Entry price = 1m close at 09:07
  - More accurate than waiting for 09:15
```

### Signal Priority

1. Exit signals (stop loss, take profit, trailing stop)
2. Exit rules from DSL
3. Entry signals (new positions)

---

## Adapters

### BacktestAdapter

Wraps FeedStore and SimulatedExchange for historical simulation:

```python
class BacktestDataProvider:
    def __init__(self, feed_store: FeedStore):
        self.feed_store = feed_store

    def get_snapshot(self, bar_time: int) -> SnapshotView:
        return self.feed_store.build_snapshot(bar_time)

class BacktestExchange:
    def __init__(self, sim_exchange: SimulatedExchange):
        self.sim = sim_exchange

    def submit_order(self, order: Order) -> OrderResult:
        return self.sim.execute(order)
```

### LiveAdapter

Wraps WebSocket feed and Bybit API for live trading:

```python
class LiveDataProvider:
    def __init__(self, websocket: WebSocketFeed):
        self.ws = websocket

    def get_snapshot(self, bar_time: int) -> SnapshotView:
        return self.ws.build_snapshot()

class LiveExchange:
    def __init__(self, client: BybitClient):
        self.client = client

    def submit_order(self, order: Order) -> OrderResult:
        return self.client.place_order(order)
```

---

## Factory Usage

### Create Backtest Engine

```python
from src.engine.factory import create_backtest_engine

# Uses market_data_backtest.duckdb
result = create_backtest_engine(
    play_path="strategies/plays/my_play.yaml",
    symbol="BTCUSDT",
    start_date="2025-01-01",
    end_date="2025-06-01",
)
```

### Create with Specific Data Environment

```python
from src.engine.factory import create_backtest_engine

# Uses market_data_demo.duckdb
result = create_backtest_engine(
    play_path="strategies/plays/my_play.yaml",
    symbol="BTCUSDT",
    start_date="2025-01-01",
    end_date="2025-06-01",
    data_env="demo",
)
```

---

## Validation

### Baseline Hashes

Trade hashes recorded in `docs/todos/UNIFIED_ENGINE_BASELINE.md` for regression detection.

### Audit Commands

```bash
# Indicator coverage
python trade_cli.py backtest audit-toolkit

# Multi-TF structure detection
python trade_cli.py backtest structure-smoke

# Rollup parity
python trade_cli.py backtest audit-rollup

# Full smoke test
python trade_cli.py --smoke full
```

---

## References

- Implementation Plan: `docs/todos/UNIFIED_ENGINE_PLAN.md`
- Baseline Metrics: `docs/todos/UNIFIED_ENGINE_BASELINE.md`
- Naming Standards: `docs/specs/ENGINE_NAMING_CONVENTION.md`
- DSL Cookbook: `docs/PLAY_DSL_COOKBOOK.md`
