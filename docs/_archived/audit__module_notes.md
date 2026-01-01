# TRADE Module Notes

**STATUS:** CANONICAL  
**PURPOSE:** Per-module documentation: purpose, dependencies, state, invariants  
**LAST UPDATED:** December 17, 2025

---

## Module: Backtest Engine (`src/backtest/engine.py`)

**Purpose:** Main orchestrator for deterministic backtesting

**Key Responsibilities:**
- Load IdeaCard configuration
- Fetch multi-TF data from DuckDB
- Compute indicators (vectorized, outside hot loop)
- Build FeedStores for O(1) array access
- Run bar-by-bar simulation loop
- Coordinate with SimulatedExchange for order execution
- Generate BacktestResult with metrics
- Write artifacts (parquet, json)

**Key Types / Symbols:**
- `BacktestEngine` — Main engine class
- `BacktestResult` — Result container
- `PreparedFrame` — Prepared data with metadata

**Inputs / Outputs:**
- Input: IdeaCard (via runner), historical data (via DuckDB)
- Output: BacktestResult, artifact files

**Dependencies:**
- Internal: `runtime/`, `sim/`, `features/`, `data/`, `idea_card.py`
- External: `pandas`, `numpy`, `duckdb`

**State:**
- Implemented: Yes
- Known issues: None in engine itself
- Tech debt: Legacy SystemConfig path still active

**Invariants / Assumptions:**
1. Determinism: Same config + data → identical output
2. Closed-candle only: No partial candles in computation
3. No look-ahead: Evaluation at ts_close uses only past data
4. USDT-only: Symbol validated at engine init

**Strategy Factory Linkage:**
- Consumes IdeaCard as primary input
- Generates system hash for tracking

**Next Build-Forward Moves:**
- Retire legacy SystemConfig path
- Add market structure layer (Phase 5, blocked)

---

## Module: Runner (`src/backtest/runner.py`)

**Purpose:** CLI entry point for backtest execution

**Key Responsibilities:**
- Parse IdeaCard from YAML
- Validate and normalize configuration
- Initialize engine with prepared config
- Execute backtest and capture results
- Format output for CLI display

**Key Types / Symbols:**
- `IdeaCardEngineWrapper` — Wrapper for engine execution
- `run_backtest_from_idea_card()` — Main entry function

**Inputs / Outputs:**
- Input: IdeaCard ID, date range, options
- Output: BacktestResult, formatted display

**Dependencies:**
- Internal: `engine.py`, `idea_card.py`, CLI utilities
- External: None beyond engine deps

**State:**
- Implemented: Yes
- Known issues: None

**Invariants:**
1. Fail-fast on invalid IdeaCard
2. All runs produce artifacts

---

## Module: IdeaCard (`src/backtest/idea_card.py`)

**Purpose:** Declarative strategy specification dataclass

**Key Responsibilities:**
- Define strategy configuration schema
- Validate configuration at load time
- Provide FeatureSpec for indicators
- Support serialization/deserialization

**Key Types / Symbols:**
- `IdeaCard` — Main dataclass
- `FeeModel` — Fee configuration
- `AccountConfig` — Account/capital config
- `TFConfig` — Timeframe configuration
- `RiskModel` — Risk parameters (SL/TP)
- `SignalRules` — Entry/exit logic

**Inputs / Outputs:**
- Input: YAML file from `configs/idea_cards/`
- Output: Validated IdeaCard instance

**Dependencies:**
- Internal: `features/feature_spec.py`
- External: `pyyaml`

**State:**
- Implemented: Yes
- Known issues: None

**Invariants:**
1. Explicit over implicit: No silent defaults
2. Fail-fast: Validation at load time
3. Machine-readable: Compatible with Strategy Factory

**Strategy Factory Linkage:**
- Core primitive of Strategy Factory
- IdeaCard → System Hash → Promotion Loop

---

## Module: Feature Frame Builder (`src/backtest/features/feature_frame_builder.py`)

**Purpose:** Vectorized indicator computation outside hot loop

**Key Responsibilities:**
- Parse FeatureSpec into indicator computations
- Call pandas_ta for indicator calculation
- Build indicator columns in DataFrame
- Handle multi-output indicators
- Route input sources (close, open, high, low, volume, hlc3, ohlc4)

**Key Types / Symbols:**
- `FeatureFrameBuilder` — Main builder class
- `build_features()` — Build feature DataFrame

**Inputs / Outputs:**
- Input: OHLCV DataFrame, FeatureSpec list
- Output: DataFrame with indicator columns

**Dependencies:**
- Internal: `feature_spec.py`, `indicator_registry.py`, `indicator_vendor.py`
- External: `pandas`, `pandas_ta`

**State:**
- Implemented: Yes
- **Known issues:** P0 BLOCKER at lines 633, 674
  - Input-source routing bug
  - Non-"close" sources (volume, open, high, low) route incorrectly
  - Symptom: volume_sma shows 102K discrepancy vs pandas_ta
- Tech debt: Complex conditional logic

**Invariants:**
1. All indicators computed before hot loop
2. No pandas_ta calls in hot loop
3. Indicators declared in FeatureSpec only

---

## Module: FeedStore (`src/backtest/runtime/feed_store.py`)

**Purpose:** O(1) array-backed data access for hot loop

**Key Responsibilities:**
- Store OHLCV and indicators as numpy arrays
- Provide index-based access (no DataFrame operations)
- Support ts_close → index mapping
- Enable history window access

**Key Types / Symbols:**
- `FeedStore` — Single-TF feed store
- `MultiTFFeedStore` — Multi-TF container

**Inputs / Outputs:**
- Input: DataFrame with indicators
- Output: Numpy array access

**Dependencies:**
- Internal: None
- External: `numpy`

**State:**
- Implemented: Yes
- Known issues: None

**Invariants:**
1. O(1) access: No per-bar DataFrame ops
2. Immutable after construction
3. All arrays same length

---

## Module: RuntimeSnapshotView (`src/backtest/runtime/snapshot_view.py`)

**Purpose:** Array-backed snapshot for hot-loop performance

**Key Responsibilities:**
- Provide unified interface for multi-TF data access
- Track current indices for exec/htf/mtf
- Forward-fill HTF/MTF values between closes
- Support feature lookup with offset

**Key Types / Symbols:**
- `RuntimeSnapshotView` — Main snapshot class
- `TFContext` — Per-TF context

**Inputs / Outputs:**
- Input: FeedStores, current indices
- Output: Snapshot accessor methods

**Dependencies:**
- Internal: `feed_store.py`
- External: `numpy`

**State:**
- Implemented: Yes
- Known issues: None

**Invariants:**
1. O(1) creation: Just index updates
2. O(1) access: Array lookup only
3. No deep copies
4. TradingView-style forward-fill

---

## Module: Simulated Exchange (`src/backtest/sim/exchange.py`)

**Purpose:** Deterministic exchange simulation

**Key Responsibilities:**
- Process orders at bar boundaries
- Apply fills with slippage model
- Track positions and PnL
- Handle TP/SL with deterministic tie-break
- Apply funding rates
- Check liquidation conditions
- Maintain accounting invariants

**Key Types / Symbols:**
- `SimulatedExchange` — Main exchange class
- `Ledger` — Account ledger

**Inputs / Outputs:**
- Input: Orders from strategy, bar data
- Output: Fills, position updates, step results

**Dependencies:**
- Internal: `ledger.py`, `pricing/`, `execution/`, `funding/`, `liquidation/`
- External: None

**State:**
- Implemented: Yes
- Known issues: None

**Invariants:**
1. USDT-only: Symbol validated at init
2. Isolated margin only: Cross rejected
3. Deterministic: Same inputs → same outputs
4. Bybit-aligned accounting: IMR, MMR, fees

---

## Module: Ledger (`src/backtest/sim/ledger.py`)

**Purpose:** Account state and PnL tracking

**Key Responsibilities:**
- Track cash balance and positions
- Calculate equity, margin, PnL
- Apply fills and funding
- Enforce accounting invariants

**Key Types / Symbols:**
- `Ledger` — Main ledger class
- `LedgerConfig` — Configuration

**Inputs / Outputs:**
- Input: Fills, funding events, prices
- Output: Account state updates

**Dependencies:**
- Internal: `types.py`
- External: None

**State:**
- Implemented: Yes
- Known issues: None

**Invariants:**
1. equity = cash + unrealized_pnl
2. free_margin = equity - used_margin
3. available_balance = max(0, free_margin)

---

## Module: Historical Data Store (`src/data/historical_data_store.py`)

**Purpose:** DuckDB-backed market data storage

**Key Responsibilities:**
- Store OHLCV, funding rates, open interest
- Sync data from Bybit API
- Detect and heal gaps
- Provide DataFrame output for backtesting
- Support environment-aware storage (live/demo)

**Key Types / Symbols:**
- `HistoricalDataStore` — Main store class
- `get_historical_store()` — Singleton accessor

**Inputs / Outputs:**
- Input: Bybit API data, query parameters
- Output: DataFrames for backtest

**Dependencies:**
- Internal: `exchanges/bybit_client.py`
- External: `duckdb`, `pandas`

**State:**
- Implemented: Yes
- Known issues: None

**Invariants:**
1. LIVE API for data: Always use api.bybit.com
2. Timestamp = ts_open: Bar open time stored
3. No duplicates: PK enforced
4. Valid OHLCV: high ≥ low

**Data Contracts:**
- See `docs/data/DATA_MODULE.md` for schema details

---

## Module: Tool Registry (`src/tools/tool_registry.py`)

**Purpose:** Unified interface for tool discovery and execution

**Key Responsibilities:**
- Register all available tools
- Provide tool discovery for agents
- Execute tools with validation
- Return consistent ToolResult

**Key Types / Symbols:**
- `ToolRegistry` — Main registry
- `ToolSpec` — Tool specification
- `ToolResult` — Execution result

**Inputs / Outputs:**
- Input: Tool name, parameters
- Output: ToolResult

**Dependencies:**
- Internal: All `*_tools.py` modules
- External: None

**State:**
- Implemented: Yes
- Known issues: None

**Invariants:**
1. All trading through tools: No direct API calls
2. Consistent return type: ToolResult
3. Agent-ready: JSON-serializable specs

---

## Module: Gates (`src/backtest/gates/`)

**Purpose:** Validation gates for pre-merge checks

**Key Responsibilities:**
- Production first-import gate
- IdeaCard generator for testing
- Batch verification
- Indicator requirements validation

**Key Types / Symbols:**
- `GateResult`, `GateViolation` — Gate outcomes
- `BatchSummary` — Batch run summary

**Inputs / Outputs:**
- Input: Codebase files, IdeaCards
- Output: Pass/fail reports

**Dependencies:**
- Internal: `backtest/` modules
- External: None

**State:**
- Implemented: Partial
- Known issues: Gates scattered (consolidation recommended)

**Invariants:**
1. Read-only: Gates don't modify files
2. Gate before merge: All must pass

---

## Module: CLI (`src/cli/`)

**Purpose:** Menu-driven CLI interface

**Key Responsibilities:**
- Display menus and prompts
- Route user input to tools
- Run smoke tests
- Format output with Rich

**Key Types / Symbols:**
- Menu handler functions
- CLI utilities

**Inputs / Outputs:**
- Input: User input
- Output: Formatted display

**Dependencies:**
- Internal: `tools/*`
- External: `rich`, `typer`

**State:**
- Implemented: Yes
- Known issues: None

**Invariants:**
1. Pure shell: No business logic
2. Tool-first: All ops through tools

---

## Module: Exchange Manager (`src/core/exchange_manager.py`)

**Purpose:** Live exchange operations interface

**Key Responsibilities:**
- Execute orders on Bybit
- Query positions and balances
- Apply rate limiting
- Handle API errors

**Key Types / Symbols:**
- `ExchangeManager` — Main class

**Inputs / Outputs:**
- Input: Order parameters
- Output: API responses

**Dependencies:**
- Internal: `exchanges/bybit_*.py`
- External: `pybit`

**State:**
- Implemented: Yes
- Known issues: None

**Invariants:**
1. Rate limiting: All calls throttled
2. Risk checks: Via RiskManager

---

## Module: Risk Manager (`src/core/risk_manager.py`)

**Purpose:** Live trading risk enforcement

**Key Responsibilities:**
- Validate orders against risk limits
- Check position limits
- Enforce daily loss limits
- Apply leverage constraints

**Key Types / Symbols:**
- `RiskManager` — Main class
- `Signal` — Trade signal dataclass

**Inputs / Outputs:**
- Input: Signal from strategy
- Output: Approved/rejected decision

**Dependencies:**
- Internal: `config/`
- External: None

**State:**
- Implemented: Yes
- Known issues: None

**Invariants:**
1. Risk-first: All orders checked
2. Fail-safe: Reject on uncertainty

---

## Module: Strategies (`src/strategies/`)

**Purpose:** Strategy base classes and registry

**Key Responsibilities:**
- Define BaseStrategy interface
- Registry for strategy lookup
- Example implementations

**Key Types / Symbols:**
- `BaseStrategy` — Base class
- `strategy_registry` — Strategy lookup

**Inputs / Outputs:**
- Input: Snapshot
- Output: Signals

**Dependencies:**
- Internal: `backtest/runtime/` (for snapshot types)
- External: None

**State:**
- Implemented: Partial (base only)
- Known issues: 
  - Example configs in wrong location (`src/strategies/configs/`)
  - Should be in `configs/`

**Invariants:**
1. Strategies emit Signals, don't execute
2. All logic in generate_signals()

---

