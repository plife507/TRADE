# Backtest Engine - Brainstorming & Architecture

**Created:** 2025-12-12  
**Last Updated:** 2025-12-13  
**Status:** Backtest refactor complete (Phases 0–5)  
**Purpose:** Comprehensive brainstorming document for the backtest engine, including current project structure, existing infrastructure, and integration points. Updated to reflect modular exchange architecture implementation.

---

## Table of Contents

1. [What is `run_epoch`?](#what-is-run_epoch)
2. [Current Project Structure](#current-project-structure)
3. [Existing Infrastructure](#existing-infrastructure)
4. [What Needs to Be Built](#what-needs-to-be-built)
5. [Integration Points](#integration-points)
6. [Architecture Design](#architecture-design)
7. [Data Flow](#data-flow)
8. [Next Steps](#next-steps)

---

## What is `run_epoch`?

### Overview

`run_epoch` is a **convenience wrapper function** that automates the tracking, logging, and artifact writing for strategy lifecycle stages (epochs). It's the recommended way to run backtests, demo trading, or live trading with full observability.

### Location

```python
from src.utils.epoch_tracking import run_epoch, StrategyEpoch
```

### Strategy Lifecycle Epochs

```python
class StrategyEpoch(Enum):
    IDEA = "idea"           # Just an idea
    CREATION = "creation"   # Being coded
    BACKTEST = "backtest"   # Testing on historical data
    DEMO = "demo"          # Testing on demo account
    LIVE = "live"          # Real money trading
    ARCHIVED = "archived"  # Retired
```

### How It Works

```python
# 1. Define your backtest function
def my_backtest(symbol: str, timeframe: str, start: str, end: str) -> dict:
    """
    Your actual backtest logic goes here.
    Must return a dict with metrics.
    """
    # ... run backtest ...
    return {
        "net_profit": 1250.0,
        "win_rate": 65.0,
        "sharpe": 1.8,
        "max_drawdown_abs": 350.0,
        "max_drawdown_pct": -3.5,
        "total_trades": 45,
    }

# 2. Run with tracking
result = run_epoch(
    epoch=StrategyEpoch.BACKTEST,      # Which stage
    symbol="BTCUSDT",                 # What symbol
    strategy_id="momentum-v1",        # Strategy ID
    runner_fn=my_backtest,            # Your function
    timeframes=["1h"],                # Timeframes used
    promotion_criteria=lambda m: m.get("sharpe", 0) > 1.5,  # Pass criteria
    next_epoch=StrategyEpoch.DEMO,    # Promote to demo if passed
    # These are passed to my_backtest:
    timeframe="1h",
    start="2024-01-01",
    end="2024-06-30",
)

# 3. Get results
print(f"Run ID: {result['run_id']}")      # Unique run ID
print(f"Passed: {result['passed']}")      # True/False
print(f"Metrics: {result['metrics']}")    # Your metrics dict
```

### What It Does Behind the Scenes

1. **Creates tracking context**
   - Generates unique `run_id`
   - Sets up logging context
   - Initializes `StrategyEpochTracker`

2. **Starts epoch**
   - Logs start event to `logs/events_*.jsonl`
   - Writes `config.json` to `backtests/<timestamp>/<run_id>/`
   - Sets up log context scope

3. **Runs your function**
   ```python
   with log_context_scope(run_id=run_id):
       metrics = runner_fn(symbol=symbol, **runner_kwargs)
   ```

4. **Evaluates promotion criteria**
   - Checks if metrics pass promotion criteria
   - Determines if strategy should advance to next epoch

5. **Completes epoch**
   - Logs completion event
   - Writes `results.json` and `summary.json`
   - Optionally promotes to next epoch if criteria passed

### Artifacts Written

For each run, artifacts are written to:
```
backtests/20251212_013458/run-8dfc8a470f1a/
├── config.json      # Run configuration
├── results.json     # Full metrics
├── summary.json     # High-level summary
└── trades.jsonl     # Per-trade log (if you log trades)
```

### Return Value

```python
{
    "run_id": "run-8dfc8a470f1a",           # Unique ID
    "strategy_id": "momentum-v1",
    "epoch": "backtest",
    "symbol": "BTCUSDT",
    "metrics": {                            # Your metrics dict
        "total_pnl": 1250,
        "win_rate": 0.65,
        ...
    },
    "passed": True,                          # Whether promotion criteria passed
    "promotion_reason": "Sharpe > 1.5, win rate > 0.6",
    "next_epoch": "demo"                    # Next epoch if passed, else None
}
```

### Benefits

- ✅ **Automatic tracking** - No manual logging needed
- ✅ **Reproducibility** - Config and results saved automatically
- ✅ **Promotion logic** - Automatic progression through epochs
- ✅ **Integration** - Works with experiment tracking
- ✅ **Error handling** - Catches exceptions and marks epoch as failed

### When to Use

- ✅ Running a backtest - wrap your backtest function
- ✅ Running demo trading - wrap your demo runner
- ✅ Running live trading - wrap your live runner
- ✅ Any strategy lifecycle stage that needs tracking

### When NOT to Use

- ❌ If you need fine-grained control over tracking
- ❌ If you're running multiple epochs in a loop (use `StrategyEpochTracker` directly)
- ❌ If you're running experiments (use `ExperimentTracker`)

---

## Current Project Structure

### Core Directory (`src/core/`)

```
src/core/
├── __init__.py
├── application.py              # Main application lifecycle
├── exchange_manager.py        # Unified exchange interface (TO BE SIMULATED)
├── exchange_instruments.py     # Instrument info, pricing, quantity calc
├── exchange_orders_limit.py    # Limit order execution
├── exchange_orders_market.py  # Market order execution
├── exchange_orders_stop.py    # Stop/conditional orders
├── exchange_orders_manage.py  # Order management, batch ops
├── exchange_positions.py       # Position queries
├── exchange_websocket.py      # WebSocket integration
├── order_executor.py          # Order execution pipeline
├── position_manager.py        # Position tracking & PnL
├── risk_manager.py            # Risk controls (CAN BE REUSED)
└── safety.py                  # Panic button
```

**Key Interfaces:**
- `ExchangeManager` - Main trading interface (needs simulated version)
- `RiskManager` - Risk checks (can be reused in backtests)
- `OrderExecutor` - Order execution pipeline
- `PositionManager` - Position tracking

### Data Directory (`src/data/`)

```
src/data/
├── __init__.py
├── backend_protocol.py         # Data backend abstraction
├── historical_data_store.py    # DuckDB storage (READY FOR BACKTESTS)
├── historical_maintenance.py   # Data maintenance tools
├── historical_queries.py       # Query helpers
├── historical_sync.py          # Data synchronization
├── market_data.py              # Live market data access
├── realtime_bootstrap.py       # WebSocket bootstrap
├── realtime_models.py          # Real-time data models
├── realtime_state.py           # WebSocket state management
└── sessions.py                 # Data session management
```

**Key Components:**
- `HistoricalDataStore` - DuckDB storage with OHLCV, funding, OI
- Multi-timeframe data retrieval
- Gap detection and filling
- Environment-aware (live/demo)

### Utils Directory (`src/utils/`)

```
src/utils/
├── __init__.py
├── epoch_tracking.py           # Epoch/experiment tracking (READY)
├── log_context.py             # Logging context management
├── time_range.py              # TimeRange abstraction (READY)
├── logger.py                  # Structured logging
├── rate_limiter.py            # API rate limiting
├── helpers.py                 # Utility functions
└── cli_display.py             # CLI display helpers
```

**Key Components:**
- `epoch_tracking.py` - `run_epoch()`, `StrategyEpochTracker`, `ExperimentTracker`
- `time_range.py` - `TimeRange` class for time windows
- `log_context.py` - Context management for correlation

### Tools Directory (`src/tools/`)

```
src/tools/
├── __init__.py
├── tool_registry.py           # Tool registry for orchestrators
├── account_tools.py           # Account operations
├── data_tools.py              # Data operations
├── market_data_tools.py       # Market data queries
├── order_tools.py             # Order operations
├── position_tools.py          # Position operations
├── diagnostics_tools.py      # Diagnostics
└── shared.py                  # Shared tool utilities
```

**Note:** Tools are the primary API surface for CLI/orchestrators.

### Config Directory (`src/config/`)

```
src/config/
├── __init__.py
├── config.py                  # Central configuration
└── constants.py               # Trading constants
```

### Exchanges Directory (`src/exchanges/`)

```
src/exchanges/
├── __init__.py
├── bybit_client.py            # Bybit API wrapper
├── bybit_account.py           # Account operations
├── bybit_market.py            # Market data
├── bybit_trading.py           # Trading operations
└── bybit_websocket.py         # WebSocket client
```

---

## Existing Infrastructure

### ✅ What's Ready for Backtesting

#### 1. **Data Layer** (`src/data/historical_data_store.py`)

**Status:** ✅ READY

- DuckDB storage for OHLCV, funding rates, open interest
- Multi-timeframe data retrieval
- Gap detection and filling
- Environment-aware (live/demo)
- DataFrame output for backtesting

**Key Methods:**
```python
# Get OHLCV data
store.get_ohlcv(symbol, timeframe, start, end, env="live")

# Get multi-timeframe data
store.get_multi_timeframe_data(symbol, timeframes, start, end, env="live")

# Get funding rates
store.get_funding_rates(symbol, start, end, env="live")

# Get open interest
store.get_open_interest(symbol, start, end, env="live")
```

#### 2. **Time Range Utilities** (`src/utils/time_range.py`)

**Status:** ✅ READY

- `TimeRange` abstraction for time windows
- Helpers like `TimeRange.last_24h()`, `TimeRange.from_window_string("6M")`
- Validation and conversion methods

**Key Methods:**
```python
# Create time ranges
tr = TimeRange.last_24h()
tr = TimeRange.from_window_string("6M")
tr = TimeRange.from_dates(start_dt, end_dt)

# Convert to timestamps
start_ms, end_ms = tr.to_tuple_ms()
```

#### 3. **Epoch Tracking** (`src/utils/epoch_tracking.py`)

**Status:** ✅ READY

- `run_epoch()` wrapper for backtests
- `StrategyEpochTracker` for per-trade logging
- `ExperimentTracker` for multi-strategy/timeframe experiments
- Artifact writing to `backtests/<timestamp>/<run_id>/`

**Key Components:**
```python
# Simple wrapper
run_epoch(epoch, symbol, strategy_id, runner_fn, ...)

# Manual tracking
tracker = StrategyEpochTracker(strategy_id, strategy_name)
run_id = tracker.epoch_start(epoch, symbol, timeframes)
# ... run backtest ...
tracker.epoch_complete(run_id, epoch, symbol, metrics)

# Per-trade logging
tracker.log_trade(run_id, symbol, side, size_usd, price, pnl)
```

#### 4. **Risk Manager** (`src/core/risk_manager.py`)

**Status:** ✅ CAN BE REUSED

- Rule-based risk controls
- Position sizing, leverage limits, daily loss caps
- Same risk pipeline can be used in backtests

**Key Interface:**
```python
@dataclass
class Signal:
    symbol: str
    direction: str  # "LONG", "SHORT", "FLAT"
    size_usd: float
    strategy: str
    confidence: float = 1.0
    metadata: dict = None

# Risk check
result = risk_manager.check_signal(signal, portfolio_snapshot)
if result.allowed:
    # Execute trade
```

#### 5. **Simulated Exchange** (`src/backtest/sim/exchange.py`)

**Status:** ✅ COMPLETE

- **Modular architecture**: Thin orchestrator (~200 LOC) coordinating specialized modules
- Bybit-aligned accounting (isolated margin, USDT linear)
- Deterministic execution model
- Specialized modules:
  - `pricing/` - Mark/last/mid price derivation, spread, intrabar path
  - `execution/` - Order execution with slippage, liquidity, impact models
  - `ledger.py` - USDT accounting with invariants
  - `funding/` - Funding rate application
  - `liquidation/` - Mark-based liquidation
  - `metrics/` - Exchange-side metrics
  - `constraints/` - Tick/lot/min_notional validation
  - `adapters/` - Data conversion helpers

**Key Interface:**
```python
from src.backtest.sim import SimulatedExchange, ExecutionConfig

exchange = SimulatedExchange(
    symbol="BTCUSDT",
    initial_capital=1000.0,
    execution_config=ExecutionConfig(...),
    risk_profile=RiskProfileConfig(...),
)

# Process bar-by-bar
result = exchange.process_bar(bar, prev_bar)
# Returns StepResult with fills, funding, liquidation, ledger updates
```

---

## What Has Been Built (Refactor Complete — Phases 0–5)

### ✅ Core Backtest Engine

**File:** `src/backtest/engine.py` (COMPLETE)

**Purpose:** Main engine that orchestrates the backtest

**Status:** ✅ COMPLETE

**Responsibilities:**
1. Load historical data from DuckDB with proper warm-up
2. Compute indicators (EMA, RSI, ATR) with no look-ahead
3. Iterate through bars/candles chronologically
4. Call strategy to generate signals
5. Execute trades via `SimulatedExchange` (modular architecture)
6. Track positions and PnL via ledger
7. Calculate metrics (PnL, Sharpe, drawdown, etc.)
8. Generate proof-grade metrics (V2)
9. Write artifacts (trades.csv, equity.csv, result.json)

**Interface:**
```python
class BacktestEngine:
    def __init__(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        initial_capital: float = 10000.0,
        data_env: str = "live",
    ):
        """Initialize backtest engine."""
        
    def run(self, strategy, config: dict) -> dict:
        """
        Run backtest.
        
        Args:
            strategy: Strategy instance (or strategy function)
            config: Strategy configuration dict
            
        Returns:
            Metrics dict with:
            - net_profit
            - win_rate
            - sharpe
            - max_drawdown_abs
            - max_drawdown_pct
            - total_trades
            - avg_trade_return_pct
            - profit_factor
            - etc.
        """
        
    def get_equity_curve(self) -> pd.DataFrame:
        """Get equity curve over time."""
        
    def get_trades(self) -> List[dict]:
        """Get list of all trades."""
```

**Implementation Flow:**
```python
def run(self, strategy) -> BacktestResult:
    # 1. Prepare frame with warm-up
    prepared = self.prepare_backtest_frame()
    
    # 2. Initialize exchange (modular architecture)
    exchange = SimulatedExchange(
        symbol=self.config.symbol,
        initial_capital=self.config.risk_profile.initial_equity,
        execution_config=self.execution_config,
        risk_profile=self.config.risk_profile,
    )
    
    # 3. Iterate through bars
    for i, row in prepared.df.iterrows():
        # Create canonical Bar with explicit ts_open/ts_close
        # NOTE: this is illustrative; see the canonical implementation in:
        # - src/backtest/engine.py (Bar construction + ts_close derivation)
        from src.backtest.runtime.types import Bar
        from src.backtest.runtime.timeframe import tf_duration
        tf_delta = tf_duration(self.config.tf)
        ts_open = row["timestamp"]  # DuckDB stores ts_open in `timestamp`
        ts_close = ts_open + tf_delta
        bar = Bar(
            symbol=self.config.symbol,
            tf=self.config.tf,
            ts_open=ts_open,
            ts_close=ts_close,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
        
        # Process bar (pricing → funding → execution → ledger → liquidation)
        step_result = exchange.process_bar(bar, prev_bar)
        
        # Check stop conditions
        if exchange.should_stop():
            break
        
        # Get signal from strategy (RuntimeSnapshot)
        # Snapshot is built by engine from step_result
        signal = strategy.generate_signal(snapshot, self.config.params)
        
        # Apply risk policy
        if signal is not None:
            decision = self.risk_policy.check(signal, exchange.state)
            if decision.allowed:
                sizing = self.risk_manager.size_position(signal, exchange.state)
                if sizing.allowed:
                    exchange.submit_order(...)
        
        prev_bar = bar
    
    # 4. Calculate metrics
    metrics = compute_backtest_metrics(exchange.trades, exchange.equity_curve)
    proof_metrics = compute_proof_metrics(exchange, self.config)
    
    # 5. Return structured result
    return BacktestResult(...)
```

### ✅ Simulated Exchange (Modular Architecture)

**File:** `src/backtest/sim/exchange.py` (COMPLETE)

**Status:** ✅ Complete

**Purpose:** Thin orchestrator coordinating specialized modules for deterministic backtesting

**Architecture:**
- **Orchestrator**: `exchange.py` (~200 LOC) coordinates specialized modules
- **Tool-calling pipeline**: Each bar processed through pricing → funding → execution → ledger → liquidation → metrics
- **Bybit-aligned**: Isolated margin, USDT linear perpetual, mark-to-market accounting

**Module Structure:**
```
sim/
├── exchange.py         # Thin orchestrator
├── ledger.py           # USDT accounting with invariants
├── pricing/            # Price models (mark, spread, intrabar)
├── execution/          # Order execution (slippage, liquidity, impact)
├── funding/            # Funding rate application
├── liquidation/        # Mark-based liquidation
├── metrics/            # Exchange-side metrics
├── constraints/        # Order validation
└── adapters/           # Data conversion
```

**Key Features:**
- Deterministic execution (same inputs → same outputs)
- Configurable fees, slippage, impact models
- Stop conditions (account_blown, insufficient_free_margin)
- Proof-grade metrics integration

### ✅ Strategy Interface

**File:** `src/strategies/base.py` (CURRENT)

**Status:** ✅ Ready for backtesting

**Purpose:** Strategies work identically in live and backtest

**Requirements (Met):**
- ✅ Same interface for live and backtest
- ✅ Strategies accept **`RuntimeSnapshot`** (canonical backtest snapshot)
- ✅ Config-driven via system config YAML (no hardcoded params)
- ✅ Return `Signal` objects
- ✅ Strategy registry for dynamic loading

**Interface:**
```python
from src.backtest.runtime.types import RuntimeSnapshot
from src.core.risk_manager import Signal

class BaseStrategy:
    """Base class for all strategies."""

    def generate_signal(
        self,
        snapshot: RuntimeSnapshot,
        params: dict,
    ) -> Signal | None:
        """
        Generate a trading signal.

        Args:
            snapshot: RuntimeSnapshot (canonical backtest snapshot)
            params: Strategy parameters from system YAML

        Returns:
            Signal or None
        """
        raise NotImplementedError
```

**Note:** Backtests use `RuntimeSnapshot` (not `MarketSnapshot` / `MultiTFSnapshot`). Multi‑TF is supported via cached feature snapshots on `RuntimeSnapshot`.

### ✅ Metrics Calculator

**File:** `src/backtest/metrics.py` (COMPLETE)

**Status:** ✅ Complete with proof-grade metrics (V2)

**Purpose:** Calculate backtest metrics from trades and equity curve

**Metrics Calculated:**
- ✅ Total PnL, net profit
- ✅ Win rate, loss rate
- ✅ Sharpe ratio (annualized)
- ✅ Max drawdown (absolute and percentage)
- ✅ Total trades, winning trades, losing trades
- ✅ Average trade PnL
- ✅ Profit factor
- ✅ Sortino ratio
- ✅ Calmar ratio
- ✅ Average holding time
- ✅ Longest drawdown period

**Proof-Grade Metrics (V2):**
- ✅ `BacktestMetricsV2` with comprehensive breakdown:
  - `PerformanceMetrics` - Returns, CAGR, volatility
  - `DrawdownMetrics` - Max DD, recovery time, underwater curve
  - `TradeQualityMetrics` - Win rate, avg win/loss, expectancy
  - `RiskAdjustedMetrics` - Sharpe, Sortino, Calmar, risk-return ratios
  - `MarginStressMetrics` - Margin utilization, liquidation proximity
  - `EntryFrictionMetrics` - Fee impact, slippage cost
  - `LiquidationProximityMetrics` - Distance to liquidation
  - `ExposureMetrics` - Position sizing, leverage usage

**Interface:**
```python
from src.backtest.metrics import compute_backtest_metrics
from src.backtest.proof_metrics import compute_proof_metrics

# Standard metrics
metrics = compute_backtest_metrics(trades, equity_curve, initial_capital)

# Proof-grade metrics (V2)
proof_metrics = compute_proof_metrics(exchange, config)
```

### ✅ Data Validation & Warm-up

**File:** `src/backtest/engine.py` (Built-in)

**Status:** ✅ Complete

**Purpose:** Pre-flight checks and proper warm-up handling

**Features:**
- ✅ Automatic warm-up calculation based on indicator lookback
- ✅ Extended data loading (warm-up + simulation window)
- ✅ Gap detection via DuckDB queries
- ✅ First valid bar detection (after warm-up)

**Implementation:**
```python
# In BacktestEngine.prepare_backtest_frame()
prepared = engine.prepare_backtest_frame()
# Returns PreparedFrame with:
# - df: DataFrame ready for simulation (trimmed to sim_start)
# - full_df: Full DataFrame with indicators (includes warm-up)
# - warmup_bars: Number of warm-up bars
# - simulation_start: Actual simulation start timestamp
```

---

## Integration Points

### 1. Data Layer Integration

**How backtest engine uses data:**
```python
from src.data.historical_data_store import HistoricalDataStore

store = HistoricalDataStore()
data = store.get_ohlcv(symbol, timeframe, start, end, env="live")
```

**Key Points:**
- Always use `env="live"` for backtests (canonical data)
- Use `TimeRange` for date handling
- Handle gaps appropriately (error vs forward-fill)

### 2. Epoch Tracking Integration

**How backtest engine integrates with `run_epoch()`:**
```python
from src.utils.epoch_tracking import run_epoch, StrategyEpoch

def my_backtest(symbol: str, timeframe: str, start: str, end: str) -> dict:
    """Backtest function that returns metrics."""
    engine = BacktestEngine(symbol, timeframe, start, end)
    strategy = MomentumStrategy()
    config = {"momentum_period": 20}
    metrics = engine.run(strategy, config)
    return metrics

# Run with tracking
result = run_epoch(
    epoch=StrategyEpoch.BACKTEST,
    symbol="BTCUSDT",
    strategy_id="momentum-v1",
    runner_fn=my_backtest,
    timeframe="1h",
    start="2024-01-01",
    end="2024-06-30",
)
```

### 3. Risk Manager Integration

**How backtest engine uses risk manager:**
```python
from src.core.risk_manager import RiskManager, Signal

risk_manager = RiskManager()
signal = Signal(symbol="BTCUSDT", direction="LONG", size_usd=1000, strategy="momentum-v1")
risk_check = risk_manager.check_signal(signal, portfolio_snapshot)

if risk_check.allowed:
    # Execute trade
    size = risk_check.adjusted_size or signal.size_usd
    order_result = simulated_exchange.market_buy(symbol, size)
```

**Key Points:**
- Same risk pipeline as live trading
- Only execution target differs (simulated vs real)

### 4. Strategy Interface Integration

**How strategies work in backtest:**
```python
# Strategy receives RuntimeSnapshot (canonical format)
# Bar is canonical with ts_open/ts_close
from src.backtest.runtime.types import RuntimeSnapshot

# RuntimeSnapshot is built by engine from canonical Bar
# Bar has explicit ts_open (fill time) and ts_close (step time)
snapshot = RuntimeSnapshot(
    ts_close=bar.ts_close,  # Step time (bar close)
    symbol="BTCUSDT",
    bar_ltf=bar,  # Canonical Bar with ts_open/ts_close
    # ... other fields built by SnapshotBuilder
)

# Strategy generates a single signal (or None)
signal = strategy.generate_signal(snapshot, params)

# Engine applies RiskPolicy + SimulatedRiskManager sizing, then submits
# orders to SimulatedExchange (see src/backtest/engine.py for the canonical flow).
```

**Key Points:**
- Strategies should be agnostic to live/backtest mode
- Use `RuntimeSnapshot` (canonical backtest snapshot)
- Same signal generation logic

---

## Architecture Design

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    run_epoch() Wrapper                      │
│  - Creates run_id                                           │
│  - Starts epoch tracking                                    │
│  - Sets up logging context                                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              BacktestEngine.run()                           │
│  1. Load data from HistoricalDataStore                     │
│  2. Initialize portfolio & positions                        │
│  3. Iterate through bars                                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              For each bar:                                  │
│  1. Create RuntimeSnapshot from bar                         │
│  2. Call strategy.generate_signal(snapshot, params)         │
│  3. For each signal:                                        │
│     a. RiskPolicy.check() + SimulatedRiskManager.size_position() │
│     b. SimulatedExchange.submit_order()                     │
│     c. Update portfolio & track trades                      │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Calculate Metrics                             │
│  - Total PnL, win rate, Sharpe, drawdown, etc.            │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Return metrics dict                            │
│  - Passed back to run_epoch()                               │
│  - Written to results.json                                 │
└─────────────────────────────────────────────────────────────┘
```

### Component Relationships

```
BacktestEngine
    ├── HistoricalDataStore (loads data)
    ├── RiskPolicy + SimulatedRiskManager (filters/sizes signals)
    ├── SimulatedExchange (executes fills + accounting)
    ├── Strategy (generates signals)
    └── MetricsCalculator (calculates results)

SimulatedExchange
    ├── Thin orchestrator coordinating modules
    ├── Fills orders based on OHLCV
    ├── Models slippage & fees
    └── Tracks positions/orders

Strategy
    ├── Receives RuntimeSnapshot (canonical backtest snapshot)
    ├── Generates Signal objects (same as live)
    └── Config-driven (no hardcoded params)
```

### Data Flow

```
HistoricalDataStore (DuckDB)
    │
    ├── OHLCV data (primary)
    ├── Funding rates (optional)
    └── Open interest (optional)
    │
    ▼
BacktestEngine
    │
    ├── Iterates through bars
    ├── Creates RuntimeSnapshot for each bar
    │
    ▼
Strategy
    │
    ├── Receives RuntimeSnapshot
    ├── Generates Signal (or None)
    │
    ▼
RiskPolicy + SimulatedRiskManager
    │
    ├── Filters the signal (policy)
    ├── Sizes the trade (risk manager)
    │
    ▼
SimulatedExchange
    │
    ├── Executes order intent (fills at next bar open)
    ├── Applies fees & slippage
    ├── Updates positions
    │
    ▼
Portfolio/Position Tracking
    │
    ├── Updates PnL
    ├── Tracks trades
    │
    ▼
Metrics Calculator
    │
    ├── Calculates metrics from trades
    └── Returns metrics dict
```

---

## Next Steps (Updated 2025-12-13)

### ✅ Phase 1: Foundation (COMPLETE)

1. ✅ **Modular `SimulatedExchange`**
   - ✅ Thin orchestrator (~200 LOC) with specialized modules
   - ✅ Market/limit order fills with slippage models
   - ✅ Fee calculation (configurable taker/maker rates)
   - ✅ Position tracking via ledger with invariants
   - ✅ Bybit-aligned accounting (isolated margin, USDT linear)

2. ✅ **`BacktestEngine` Complete**
   - ✅ Load data from `HistoricalDataStore` with warm-up
   - ✅ Iterate through bars chronologically
   - ✅ Portfolio tracking via `SimulatedExchange`
   - ✅ Comprehensive metrics (standard + proof-grade V2)

3. ✅ **System Config & Testing**
   - ✅ YAML-based system configs
   - ✅ Strategy registry for dynamic loading
   - ✅ Smoke tests (`--smoke backtest`)
   - ✅ Multiple systems tested

### ✅ Phase 2: Core Functionality (COMPLETE)

4. ✅ **Risk Manager Integration**
   - ✅ `SimulatedRiskManager` for position sizing
   - ✅ `RiskPolicy` for signal filtering (none vs rules)
   - ✅ Risk checks work correctly
   - ✅ Position sizing verified

5. ✅ **Metrics Calculator**
   - ✅ Total PnL, win rate, Sharpe ratio
   - ✅ Max drawdown, trade statistics
   - ✅ Proof-grade metrics (V2) with comprehensive breakdown

6. ✅ **Epoch Tracking Integration**
   - ✅ Artifacts written to structured directories
   - ✅ System UID for lineage tracking
   - ✅ Config echo in results

### ✅ Phase 2: Tools & CLI (COMPLETE)

7. ✅ **Tools Integration**
   - ✅ `backtest_run_tool()` - Run backtest by system_id + window_name
   - ✅ `backtest_list_systems_tool()` - List available system configs
   - ⏳ Additional error handling polish

8. ✅ **CLI Integration**
   - ✅ Backtest menu with interactive selection
   - ✅ System/window selection
   - ⏳ Additional smoke test scenarios

### 📋 Phase 3: Future Enhancements (NOT CURRENT FOCUS)

9. **Per-Bar Datasets for ML**
   - [ ] Log per-bar features and outcomes
   - [ ] Export training datasets
   - [ ] Feature engineering pipeline

10. **Enhanced Fill Models**
   - [ ] Advanced slippage models
   - [ ] Market impact modeling
   - [ ] Partial fills

11. **Multi-Timeframe Support**
   - [ ] Multi-TF strategy support
   - [ ] HTF/MTF/LTF coordination
   - [ ] Expand snapshot feature schema for additional TFs
   - [ ] Test MTF strategies

### Phase 4: Advanced Features (Week 4+)

10. **Performance Optimization**
    - [ ] Vectorized operations where possible
    - [ ] Efficient data loading
    - [ ] Memory management

11. **Advanced Metrics**
    - [ ] Sortino ratio
    - [ ] Calmar ratio
    - [ ] Trade analysis (avg holding time, etc.)

12. **Visualization**
    - [ ] Equity curve plots
    - [ ] Drawdown charts
    - [ ] Trade distribution

---

## Questions Resolved (Updated 2025-12-13)

### ✅ Strategy Interface (RESOLVED)

- ✅ `BaseStrategy` exists in `src/strategies/base.py`
- ✅ Interface: `generate_signal(snapshot: RuntimeSnapshot, params: dict) -> Optional[Signal]`
- ✅ `RuntimeSnapshot` is canonical (MTF via cached feature snapshots)
- ✅ Strategies are config-driven via system config YAML

### ✅ Data Contracts (RESOLVED)

- ✅ Missing candles: Gap detection available, warm-up ensures sufficient data
- ✅ Gaps: Handled by DuckDB queries (no forward-fill)
- ✅ Funding rates: Supported (optional per system/config)
- ✅ Data quality: Warm-up calculation ensures valid data before simulation

### ✅ Execution Model (RESOLVED)

- ✅ Slippage: Configurable via `ExecutionConfig.slippage_bps`
- ✅ Fee rates: Configurable via `RiskProfileConfig.taker_fee_rate` / `maker_fee_rate`
- ✅ Limit orders: Fill if price trades through level during bar (intrabar path)
- ✅ Partial fills: Not implemented (future enhancement)

### ✅ Risk Management (RESOLVED)

- ✅ `SimulatedRiskManager` for position sizing (same logic as live)
- ✅ `RiskPolicy` for signal filtering (none vs rules)
- ✅ GlobalRiskView not needed in backtests (simplified model)
- ✅ Daily loss limits: Can be added via risk profile config

### ✅ Metrics (RESOLVED)

- ✅ Required metrics: PnL, win rate, Sharpe, max DD, trade count
- ✅ Sharpe ratio: Annualized with configurable risk-free rate (default 0)
- ✅ Win rate: Winning trades / total trades
- ✅ Proof-grade metrics (V2) provide comprehensive breakdown

---

## References

### Documentation

- `docs/guides/BACKTEST_ENGINE_INTEGRATION.md` - Integration guide
- `docs/brainstorm/backtest_engine_readiness_checklist.md` - Readiness checklist
- `docs/examples/epoch_experiment_tracking_example.py` - Usage examples
- `docs/architecture/DATA_ARCHITECTURE.md` - Data architecture

### Code Files

- ✅ `src/backtest/engine.py` - Backtest engine (COMPLETE)
- ✅ `src/backtest/sim/exchange.py` - Modular simulated exchange (COMPLETE)
- ✅ `src/backtest/system_config.py` - System config loader (COMPLETE)
- ✅ `src/backtest/metrics.py` - Metrics calculator (COMPLETE)
- ✅ `src/backtest/proof_metrics.py` - Proof-grade metrics V2 (COMPLETE)
- ✅ `src/tools/backtest_tools.py` - Backtest tools API (COMPLETE)
- `src/utils/epoch_tracking.py` - Epoch tracking system
- `src/data/historical_data_store.py` - Data storage
- `src/utils/time_range.py` - Time range utilities
- `src/core/risk_manager.py` - Risk manager (reused via SimulatedRiskManager)

---

## Notes

- **No external backtest libraries** - Building custom for full control
- **Reuse existing infrastructure** - Risk manager, data layer, tracking
- **Same interfaces** - Strategies work identically in live/backtest
- **Config-driven** - No hardcoded values
- **Safety first** - Same risk pipeline as live trading

---

**Last Updated:** 2025-12-13  
**Status:** Refactor complete (Phases 0–5); tools/CLI complete
