# TRADE Architecture

**STATUS:** CANONICAL
**PURPOSE:** System architecture, domains, runtime, invariants, accounting
**LAST UPDATED:** January 4, 2026 (Terminology update)

---

## Terminology (2026-01-04)

This document uses the new trading hierarchy terminology:

| Term | Definition |
|------|------------|
| **Setup** | Reusable rule blocks, filters, entry/exit logic |
| **Play** | Complete strategy specification (formerly "IdeaCard") |
| **Playbook** | Collection of plays with regime routing |
| **System** | Full trading operation with risk/execution |
| **Forge** | Development/validation environment (src/forge/) |

See: `docs/architecture/LAYER_2_RATIONALIZATION_ARCHITECTURE.md` for complete architecture.

---

## Domain Overview

| Domain | Path | Maturity | Status |
|--------|------|----------|--------|
| Backtesting | `src/backtest/` | Production | ✅ Ready |
| Market Structure | `src/backtest/market_structure/` | Production | ✅ Stages 0-7 Complete |
| CLI | `src/cli/` | Production | ✅ Stable |
| Trade Execution | `src/core/` + `src/exchanges/` | Functional | Maintenance |
| Data | `src/data/` | Production | ✅ Stable |
| Strategy Factory | `configs/plays/` (formerly idea_cards/) | Production | ✅ Core Complete |
| Audit & Validation | `src/backtest/artifacts/` | Production | ✅ Complete |

**Status:** All P0 blockers resolved (December 17-18, 2025). System is production-ready.

---

## System Overview

TRADE is a modular Bybit futures trading bot with:
- Complete UTA (Unified Trading Account) support
- Deterministic backtesting engine
- Simulated exchange for paper trading
- Live trading via Bybit API
- CLI-first interface with tool layer for agent integration

---

## Runtime Surfaces

### 1. Data Ingestion

```
Bybit LIVE API (api.bybit.com)
    ↓
BybitClient (src/exchanges/bybit_client.py)
    ↓
HistoricalDataStore (src/data/historical_data_store.py)
    ↓
DuckDB (data/market_data_live.duckdb)
```

**Tables:** `ohlcv_live`, `funding_rates_live`, `open_interest_live`

### 2. Indicator Computation (Prep Phase)

```
DuckDB Query
    ↓
pd.DataFrame (OHLCV + warmup data)
    ↓
FeatureFrameBuilder (src/backtest/features/feature_frame_builder.py)
    ↓
pandas_ta (via IndicatorVendor)
    ↓
pd.DataFrame (OHLCV + indicators)
```

**Key:** All indicator computation happens OUTSIDE the hot loop.

### 3. FeedStore Construction

```
pd.DataFrame (with indicators)
    ↓
FeedStore.from_dataframe()
    ↓
FeedStore (numpy arrays)
    ↓
MultiTFFeedStore (exec, htf, mtf)
```

**Key:** FeedStore holds immutable numpy arrays for O(1) access.

### 4. Evaluation Loop (Hot Loop)

```
for bar_idx in range(start, end):
    snapshot = RuntimeSnapshotView(feeds, bar_idx, htf_idx, mtf_idx)
    signal = strategy.evaluate(snapshot)
    step_result = exchange.process_bar(bar, signal)
    metrics.update(step_result)
```

**Key:** No pandas operations in hot loop. All access is O(1) array indexing.

### 5. Simulated Exchange

```
Signal (from strategy)
    ↓
SimulatedExchange.process_bar()
    ├── PriceModel.get_prices()
    ├── ExecutionModel.fill_orders()
    ├── Ledger.update()
    ├── LiquidationModel.check()
    └── Metrics.record()
    ↓
StepResult (fills, state, stop_reason)
```

### 6. Artifact Generation

```
BacktestResult
    ↓
Artifact Writers (src/backtest/artifacts/)
    ├── result.json (metrics + hashes: trades_hash, equity_hash, run_hash)
    ├── trades.parquet (structured trade records)
    ├── equity.parquet (equity curve with ts_ms column)
    ├── run_manifest.json (metadata + input hashes: full_hash, idea_hash)
    └── pipeline_signature.json (provenance: proves production pipeline used)
```

**Key:** All artifacts validated automatically after generation (HARD FAIL if invalid).

### 7. BacktestEngine Modular Architecture

**Status:** ✅ Complete (2025-12-30)

The `BacktestEngine` has been refactored into 8 focused modules for maintainability:

```
src/backtest/
├── engine.py (1,154 lines)              # Main orchestrator + hot loop
├── engine_data_prep.py (758 lines)      # Data loading & preparation
├── engine_feed_builder.py (157 lines)   # FeedStore building
├── engine_snapshot.py (171 lines)       # Snapshot construction
├── engine_history.py (203 lines)        # History management
├── engine_stops.py (234 lines)          # Stop condition checks
├── engine_artifacts.py (172 lines)      # Artifact writing
└── engine_factory.py (332 lines)        # Factory functions
```

**Key Principles:**
- All modules ≤ 1,500 lines (project limit)
- Public API unchanged (`BacktestEngine.__init__()` and `BacktestEngine.run()` signatures preserved)
- No behavior changes (all audits pass: 42/42 toolkit, smoke tests)
- Clear separation of concerns (data prep, feed building, snapshot, history, stops, artifacts, factory)

**See:** `docs/todos/ENGINE_MODULAR_REFACTOR_PHASES.md` for complete refactoring details

### 8. Post-Run Validation Gates

```
Artifact Generation
    ↓
Artifact Validator (automatic)
    ├── File existence check
    ├── Structure validation (columns, types)
    ├── Pipeline signature validation (config_source, uses_system_config_loader)
    └── Hash recording (for determinism)
    ↓
Determinism Verification (optional: verify-determinism CLI)
    └── Re-run comparison (trades_hash, equity_hash, run_hash)
```

---

## Determinism Rules

### Rule 1: Closed Candles Only

- Indicators computed on closed candles only
- Current (partial) bar excluded from computation
- HTF/MTF values forward-fill until next close

### Rule 2: Evaluation at ts_close

- Strategy evaluates at bar close (`ts_close`)
- Only data available at that moment is accessible
- No look-ahead into future bars

### Rule 3: Fills at ts_open

- Orders fill at next bar's open (`ts_open`)
- Slippage applied from open price
- TP/SL checked against bar OHLC

### Rule 4: Deterministic Tie-Break

- If both TP and SL would hit in same bar:
  - Longs: SL checked first (worst-case)
  - Shorts: SL checked first (worst-case)
- Conservative assumption: worst outcome first

### Rule 5: TradingView-Style MTF

- HTF/MTF indices update only on TF close
- Forward-fill semantics match TradingView `lookahead_off`
- O(1) lookup via precomputed `ts_close_ms → index` mapping

---

## Step Order (Per Bar)

```python
def process_bar(bar, signal):
    # 1. Get prices for this bar
    prices = price_model.get_prices(bar)
    
    # 2. Apply funding (if funding time)
    funding = funding_model.apply(bar.ts_open)
    
    # 3. Update entry orders from previous bar
    entry_fills = execution_model.fill_entry_orders(bar)
    
    # 4. Check TP/SL for existing positions
    exit_fills = execution_model.check_tp_sl(bar, prices)
    
    # 5. Update ledger with fills and funding
    ledger.update(entry_fills + exit_fills, funding, prices)
    
    # 6. Check liquidation
    liquidation = liquidation_model.check(ledger.state, prices)
    
    # 7. Process new signal (queue for next bar)
    if signal:
        execution_model.queue_entry(signal)
    
    # 8. Record metrics
    metrics.record(...)
    
    return StepResult(...)
```

---

## Mode Constraints

| Constraint | Value | Enforced At |
|------------|-------|-------------|
| Quote Currency | USDT only | Config load, engine init, exchange init |
| Margin Mode | Isolated only | Config load |
| Position Mode | One-way only | Hardcoded |
| Instrument Type | Linear perp only | Symbol validation |

---

## Recent Completions (December 17-18, 2025)

✅ **Delay Bars Implementation** (December 17, 2024)
- Delay bars integrated into Play schema, Preflight, SystemConfig, and Engine
- Validated via CLI across 3 symbols, 3 date ranges, 8 uncommon indicators
- Fixed data sync progress logging (no more silent operations)
- All artifacts correctly reflect delay bars in manifest and metadata
- **See**: `ARCH_DELAY_BARS.md` for complete documentation

✅ **Indicator Warmup System** (December 17, 2024)
- Variable warmup computation from indicator types + parameters
- Single source of truth: `compute_warmup_requirements()` → `SystemConfig.warmup_bars_by_role`
- Engine fails loud on missing warmup config (no silent defaults)
- **See**: `ARCH_INDICATOR_WARMUP.md` for complete documentation

✅ **Post-Backtest Audit Gates** (Phases 1-4 complete)
- Auto-sync integration (`--fix-gaps` flag, default enabled)
- Artifact validation (automatic HARD FAIL after every run)
- Determinism verification (`verify-determinism --re-run` CLI)
- Pipeline signature validation (proves production pipeline used)
- Smoke test integration (TEST 5 & TEST 6)

✅ **Backtest Financial Metrics** (All phases complete)
- Fixed Max Drawdown % bug (independent maxima tracking)
- Implemented proper CAGR/Calmar ratio (geometric, not arithmetic)
- Added TF strictness (no silent defaults, unknown TF raises error)
- Added funding metrics infrastructure
- Created `backtest metrics-audit` CLI command (6/6 tests pass)
- **See**: `docs/session_reviews/2025-12-18_backtest_financial_metrics_audit.md` for formulas

✅ **Production Pipeline Validation** (All gates passed)
- End-to-end pipeline validated with 5 Plays
- All 6 validation gates tested and verified
- Schema issues discovered and documented
- **See**: `docs/session_reviews/2025-12-18_production_pipeline_validation.md` for details

---

## Integration Seams (Agent Module)

The following seams are designed for future agent integration:

### 1. ToolRegistry

```python
from src.tools.tool_registry import ToolRegistry

registry = ToolRegistry()

# Discovery
tools = registry.list_tools(category="backtest")
info = registry.get_tool_info("run_backtest")

# Execution
result = registry.execute("run_backtest", play_id="...", start="...", end="...")
```

### 2. Play Generation

Agents can generate Plays programmatically:

```python
from src.backtest.idea_card import Play  # Note: file still named idea_card.py
from src.backtest.idea_card_yaml_builder import write_play_yaml

# Build Play from components
play = Play(
    id="agent_generated_001",
    symbol="BTCUSDT",
    tf_configs={...},
    account={...},
    ...
)

# Serialize to YAML
write_play_yaml(play, Path("configs/plays/agent_generated_001.yml"))
```

### 3. Backtest Result Parsing

```python
result = run_backtest_from_play(play_id, start, end)

# Access structured data
metrics = result.metrics
trades = result.trades
equity = result.equity_curve

# Metrics for agent decision-making
sharpe = metrics.sharpe_ratio
max_dd = metrics.max_drawdown_pct
win_rate = metrics.win_rate
```

### 4. Data Queries

```python
from src.tools.data_tools import get_ohlcv_tool, get_data_extremes_tool

# Query data availability
extremes = get_data_extremes_tool(symbol="BTCUSDT", timeframe="1h")

# Fetch OHLCV
ohlcv = get_ohlcv_tool(symbol="BTCUSDT", timeframe="1h", start=..., end=...)
```

---

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                           CLI Layer                              │
│  trade_cli.py → src/cli/menus/* → src/tools/*                   │
└─────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                          Tool Layer                              │
│  src/tools/{backtest,data,order,position,account}_tools.py      │
│  src/tools/tool_registry.py (agent interface)                   │
└─────────────────────────────────────────────────────────────────┘
                               ↓
┌──────────────────────┐  ┌──────────────────────┐
│   Backtest Domain    │  │  Live Trading Domain │
│  src/backtest/       │  │  src/core/           │
│  ├── engine.py       │  │  ├── exchange_mgr    │
│  ├── engine_*.py     │  │  ├── risk_manager    │
│  │   (8 modules)     │  │  └── order_executor  │
│  ├── sim/exchange    │  │  src/exchanges/      │
│  ├── runtime/        │  └──────────────────────┘
│  └── features/       │
└──────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                          Data Layer                              │
│  src/data/historical_data_store.py → DuckDB                     │
│  src/data/realtime_*.py (live only)                             │
└─────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────┐
│                        External APIs                             │
│  Bybit LIVE API (api.bybit.com) - data + live trading           │
│  Bybit DEMO API (api-demo.bybit.com) - demo trading             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Invariants

1. **CLI is pure shell** — No business logic in `trade_cli.py`
2. **Tools are the API** — All operations go through `src/tools/*`
3. **Backtest is deterministic** — Same inputs → identical outputs (proven via `verify-determinism`)
4. **No pandas in hot loop** — O(1) array access only (snapshot-based runtime)
5. **Closed candles only** — No partial bar computation (TradingView-style MTF)
6. **USDT isolated margin only** — Mode locks enforced (symbol validation, margin mode validation)
7. **Explicit over implicit** — No silent defaults (indicators, timeframes, risk parameters)
8. **Artifact validation** — Automatic HARD FAIL if artifacts invalid (not warning)
9. **Pipeline signature** — Every run proves production pipeline used (no "cheating")
10. **Warmup is canonical** — Engine uses `SystemConfig.warmup_bars_by_role` (never recomputes)
11. **Delay bars are explicit** — Evaluation start offset declared in Play `market_structure`
12. **Fail loud** — Missing warmup/delay config raises `ValueError` (no fallbacks)

---

## Simulated Exchange Accounting

### Formulas (Bybit-Aligned)

| Concept | Formula |
|---------|---------|
| Initial Margin (IM) | `position_value × IMR` |
| IMR | `1 / leverage` |
| Maintenance Margin (MM) | `position_value × MMR` |
| Equity | `cash_balance + unrealized_pnl` |
| Free Margin | `equity - used_margin` |
| Available Balance | `max(0, free_margin)` |

### Accounting Invariants (Verified Every Bar)

```python
# Note: Simulator uses USDT (not USD) for all accounting
assert equity_usdt == cash_balance_usdt + unrealized_pnl_usdt
assert free_margin_usdt == equity_usdt - used_margin_usdt
assert available_balance_usdt == max(0.0, free_margin_usdt)
```

**Key:** Simulator strictly uses `usdt` suffix (not `usd`) to distinguish from live trading semantics.

### Fee Model

| Event | Fee Basis |
|-------|-----------|
| Entry | `entry_notional × taker_fee_rate` (deducted from cash) |
| Exit | `exit_notional × taker_fee_rate` (deducted from realized PnL) |

**Default rate:** 0.06% taker, 0.02% maker (configurable per Play)

### Funding Model

| Event | Timing | Basis |
|-------|--------|-------|
| Funding Payment | Every 8 hours (00:00, 08:00, 16:00 UTC) | `position_value × funding_rate` |
| Funding Tracking | Separate line items | `total_funding_paid_usdt`, `net_funding_usdt` |

**Key:** Funding is tracked separately from trading fees in financial metrics.

### Stop Conditions

| Condition | Trigger | Action |
|-----------|---------|--------|
| `account_blown` | `equity_usdt <= stop_equity_usdt` | Force-close, halt |
| `insufficient_margin` | `available_balance_usdt < min_trade_usdt` | Force-close, halt |
| `liquidation` | `equity_usdt < maintenance_margin_usdt` | Force-close at liquidation price |

**Key:** All stop conditions use USDT accounting (simulator domain).

---

## Artifact Schema

### Required Files (per run)

```
backtests/<play_id>/<symbol>/<hash>/
├── result.json              # Summary metrics + hashes (trades_hash, equity_hash, run_hash)
├── trades.parquet           # Trade records (entry_ts_ms, exit_ts_ms, net_pnl_usdt, ...)
├── equity.parquet           # Equity curve (ts_ms, equity_usdt, cash_balance_usdt, ...)
├── run_manifest.json        # Run metadata (eval_start_ts_ms, full_hash, idea_hash, ...)
└── pipeline_signature.json  # Provenance (config_source, uses_system_config_loader, ...)
```

**Parquet settings:** pyarrow engine, snappy compression, version 2.6

### Artifact Standards (Enforced)

**Equity Parquet:**
- Required column: `ts_ms` (millisecond timestamp)
- Columns: `ts_ms`, `equity_usdt`, `cash_balance_usdt`, `unrealized_pnl_usdt`, `realized_pnl_usdt`

**Trades Parquet:**
- Required columns: `entry_ts_ms`, `exit_ts_ms`, `entry_price`, `exit_price`, `size_usdt`, `net_pnl_usdt`
- Structured trade data for analysis

**Result JSON:**
- Financial metrics: `net_profit`, `net_return_pct`, `sharpe_ratio`, `max_dd_pct`, `calmar_ratio`
- Hash values: `trades_hash`, `equity_hash`, `run_hash` (for determinism)
- Trade statistics: `total_trades`, `win_rate`, `profit_factor`, `expectancy_usdt`

**Pipeline Signature JSON:**
- Proves production pipeline was used (not legacy paths)
- Validates: `config_source == "Play"`, `uses_system_config_loader == False`, `placeholder_mode == False`
- **HARD FAIL** if missing or invalid

**Run Manifest JSON:**
- Input tracking: `full_hash` (input hash), `play_hash` (Play hash)
- Timing: `eval_start_ts_ms` (evaluation start timestamp)
- Configuration: `symbol`, `timeframe`, `window_start`, `window_end`

---

## Snapshot API

```python
# Feature access (O(1) array indexing)
snapshot.get_feature(key="ema_fast", tf_role="exec", offset=0)
snapshot.get_feature(key="atr", tf_role="htf", offset=1)

# OHLCV access (current bar)
snapshot.close, snapshot.open, snapshot.high, snapshot.low, snapshot.volume

# History access (index offset)
snapshot.prev_close(1)  # Previous bar close
snapshot.bars_exec_high(20)  # High of 20 bars ago

# State
snapshot.has_position
snapshot.position_side
snapshot.ts_close

# HTF/MTF access (forward-filled until next TF close)
snapshot.htf_ema_trend  # HTF indicator (constant until next HTF close)
snapshot.mtf_rsi  # MTF indicator (constant until next MTF close)
```

**Key:** All access is O(1) via precomputed numpy arrays. No DataFrame operations in hot loop.

---

## Validation & Audit Gates

### Pre-Run Gates

| Gate | Command | Acceptance |
|------|---------|------------|
| Contract Validation | `validate_play_full()` (automatic) | All schema checks pass |
| Preflight Gate | `backtest preflight --play <ID>` (automatic) | Data coverage + warmup sufficient |
| Auto-Sync | `--fix-gaps` flag (default enabled) | Missing data fetched automatically |

### Post-Run Gates (Automatic)

| Gate | When | Acceptance |
|------|------|------------|
| Artifact Validation | After every `backtest run` | All required files exist with correct structure |
| Pipeline Signature | After every `backtest run` | `config_source == "Play"`, `uses_system_config_loader == False` |
| Hash Recording | After every `backtest run` | `trades_hash`, `equity_hash`, `run_hash` stored in `result.json` |

**Behavior:** Missing or invalid artifacts cause **HARD FAIL** (not warning).

### Optional Verification Gates

| Gate | Command | Acceptance |
|------|---------|------------|
| Determinism Verification | `backtest verify-determinism --run <path> --re-run` | Hashes match (identical results) |
| Financial Metrics Audit | `backtest metrics-audit` | 6/6 test scenarios pass |
| Toolkit Contract | `backtest audit-toolkit` | 42/42 indicators pass |
| Math Parity | `backtest math-parity --idea-card <ID>` | max_diff < 1e-8 |
| Snapshot Plumbing | `backtest audit-snapshot-plumbing --idea-card <ID>` | 0 failures |

**Rule:** Regression = STOP. Fix before proceeding.

---

## Related Architecture Documents

| Document | Purpose |
|----------|---------|
| **ARCH_INDICATOR_WARMUP.md** | Indicator warmup computation, variable requirements, adding new indicators |
| **ARCH_DELAY_BARS.md** | Delay bars functionality, market structure configuration, evaluation start offset |
| **PLAY_ENGINE_FLOW.md** | Play to engine field mappings (formerly IDEACARD_ENGINE_FLOW.md) |

**Archived:**
- `archived/MARKET_STRUCTURE_INTEGRATION_PROPOSAL.md` - Historical proposal; superseded by implementation (Stages 0-7 complete in `docs/todos/archived/2026-01-01/MARKET_STRUCTURE_PHASES.md`)
- `archived/INTRADAY_ADAPTIVE_SYSTEM_REVIEW.md` - Future design review; work not yet started

**See Also:**
- `docs/session_reviews/` - Detailed implementation reviews (historical reference)
- `docs/todos/archived/` - Completed phase documentation

---
