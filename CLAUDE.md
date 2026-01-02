# CLAUDE.md

Guidance for Claude when working with the TRADE trading bot.

> **Code examples**: See `docs/guides/CODE_EXAMPLES.md` | **Env vars**: See `env.example`

## Project Overview

TRADE is a **modular, production-ready** Bybit futures trading bot with complete UTA support, comprehensive order types, position management, tool registry for orchestrator/bot integration, and risk controls.

**Key Philosophy**: Safety first, modular always, tools as the API surface.

## Current Objective (Backtest Engine Roadmap)

We are building the backtesting + strategy factory stack in **phases**. The canonical roadmap lives in `docs/project/PROJECT_OVERVIEW.md` under **"Project Roadmap – TRADE Backtest Engine & Strategy Factory"**.

### Current State (January 2026)

**Engine Complete**:
- 62-field BacktestMetrics (tail risk, leverage, MAE/MFE, benchmark alpha)
- 42 indicators in string-based registry (single source of truth)
- IdeaCard-first CLI with full menu coverage
- 24 validation IdeaCards in `configs/idea_cards/_validation/`

**Next Up**: Market Structure Features (Phase 5)
- Swing/pivot/trend detection
- Registry consolidation Phase 3
- See: `docs/todos/ARRAY_BACKED_HOT_LOOP_PHASES.md`

### Explicitly off-limits until later phases

- Forecasting models / ML, composite strategies, strategy selection policies
- "Factory" orchestration beyond "run this system" (no automated promotions yet)
- Demo/live automation for backtested strategies

### Intended module placement (high-level)

- Core backtest engine: `src/backtest/`
  - Modular exchange: `src/backtest/sim/` (pricing, execution, funding, liquidation, ledger, metrics, constraints)
  - Engine orchestrator: `src/backtest/engine.py`
- Backtest API surface (tools): `src/tools/backtest_tools.py`
- Historical candles source of truth: DuckDB via `src/data/historical_data_store.py`
- Concrete strategies: `research/strategies/{pending|final|archived}/` (not `src/strategies/`)

## Quick Reference

```bash
python trade_cli.py                     # Run interactive CLI
python trade_cli.py --smoke full        # Full smoke test (data + trading)
python trade_cli.py --smoke data_extensive  # Extensive data test (clean DB, gaps, sync)
python trade_cli.py backtest metadata-smoke  # Indicator Metadata v1 smoke test

# Phase 6 backtest smoke (opt-in)
$env:TRADE_SMOKE_INCLUDE_BACKTEST="1"; python trade_cli.py --smoke full

pip install -r requirements.txt         # Dependencies
```

## Architecture

```
TRADE/
├── src/
│   ├── backtest/                  # DOMAIN: Simulator/Backtest (USDT-only, isolated margin)
│   │   ├── engine.py              # Backtest orchestrator
│   │   ├── sim/                   # Simulated exchange (pricing, execution, ledger)
│   │   ├── runtime/               # Snapshot, FeedStore, TFContext
│   │   └── features/              # FeatureSpec, FeatureFrameBuilder
│   ├── core/                      # DOMAIN: Live Trading (exchange-native semantics)
│   │   ├── risk_manager.py        # Live risk checks (Signal.size_usd)
│   │   ├── position_manager.py    # Position tracking
│   │   └── order_executor.py      # Order execution
│   ├── exchanges/                 # DOMAIN: Live Trading (Bybit API)
│   │   └── bybit_client.py        # Bybit API wrapper
│   ├── config/                    # SHARED: Configuration (domain-agnostic)
│   ├── data/                      # SHARED: Market data, DuckDB, WebSocket state
│   ├── tools/                     # SHARED: CLI/API surface (PRIMARY INTERFACE)
│   ├── utils/                     # SHARED: Logging, rate limiting, helpers
│   └── risk/global_risk.py        # Account-level risk (GlobalRiskView)
├── docs/
│   ├── todos/                     # TODO phase documents (canonical work tracking)
│   ├── architecture/              # Architecture docs
│   ├── project/                   # Project documentation
│   └── guides/                    # Setup/development guides
├── CLAUDE.md                      # AI assistant guidance (this file)
└── trade_cli.py                   # CLI entry point
```

## Critical Rules

### GLOBAL RULES (Entire Repository)

**Build-Forward Only**
- MUST NOT preserve backward compatibility unless explicitly stated.
- MUST remove legacy shims rather than maintain parallel paths.
- MUST delete obsolete code paths (e.g., `build_exchange_state_from_dict()`, `Candle` alias, `MarketSnapshot`).

**TODO-Driven Execution (MANDATORY)**
- MUST NOT write code before TODO markdown exists for the work.
- Every code change MUST map to a TODO checkbox.
- If new work is discovered mid-implementation: STOP → update TODOs → continue.
- Work is NOT complete until TODOs are checked.
- Example: Phase 6.1 added mid-plan to remove implicit indicator defaults.

**Phase Discipline**
- Completed phases are FROZEN. MUST NOT rewrite earlier phases unless explicitly instructed.
- New requirements MUST be added as new phases or explicit mid-plan inserts.
- Example: Phases 6–9 were added after Phase 3 completion without modifying Phases 1–3.

**No Implicit Defaults (Fail Loud)**
- MUST NOT use implicit or silent defaults for required inputs.
- Missing declarations MUST raise errors, not infer behavior.
- Example (GLOBAL): `FeedStore.from_dataframe()` with `indicator_columns=None` → empty dict, not default list.
- Example (GLOBAL): `REQUIRED_INDICATOR_COLUMNS` constant was deleted—indicators MUST be declared via FeatureSpec/Idea Card.

**Closed-Candle Only + TradingView-Style MTF**
- All indicator computation MUST use closed candles only (never partial).
- HTF/MTF indicators MUST compute only on TF close.
- Between closes, last-closed values MUST forward-fill unchanged.
- MUST match TradingView `lookahead_off` semantics.
- Example (GLOBAL): HTF EMA values remain constant across exec steps until next HTF close.

**Assumptions Must Be Declared**
- Any assumption MUST be stated before implementation.
- Architectural assumptions MUST be confirmed before proceeding.
- MUST NOT guess missing requirements—surface them explicitly.

**CLI-Only Validation (HARD RULE — No pytest Files)**
- ALL validation MUST run through CLI commands—no `tests/test_*.py` files exist.
- NEVER create pytest files for backtest/data/indicator/pipeline validation.
- CLI commands replace all tests:
  - `backtest preflight` — data coverage + warmup validation
  - `backtest indicators --print-keys` — available keys per scope
  - `backtest run --smoke --strict` — full pipeline validation
  - `--smoke full/data_extensive/orders` — integration validation
- CLI returns actionable fix commands on failure.
- Use `--json` flag for CI/agent consumption.

**Safety & API Discipline (LIVE Domain)**
- LIVE trades MUST go through `src/tools/*`—never call `bybit_client` directly.
- SIMULATOR trades use `SimulatedExchange.submit_order()` directly—MUST NOT depend on live tools.
- Risk manager checks MUST occur before every order (live or simulated).
- Demo mode MUST be tested before live.
- Reference docs (`reference/exchanges/`) MUST be checked before implementing exchange logic.

---

### DOMAIN RULES — SIMULATOR / BACKTEST (`src/backtest/`)

**Currency Model: USDT Only**
- Simulator account and margin currency is **USDT**.
- MUST NOT alias USD and USDT—they are semantically distinct.
- Canonical sizing field in simulator signals is `size_usdt`.
- MUST NOT use `size_usd` or `size` in simulator code—use `size_usdt`.
- Example (SIMULATOR-ONLY): `Signal.size_usdt`, `Position.size_usdt`, `Trade.entry_size_usdt`.

**Symbol Validation: USDT Pairs Only (Current Iteration)**
- Simulator MUST reject symbols not ending in "USDT" (e.g., `BTCUSD`, `BTCUSDC`) in the current iteration.
- `validate_usdt_pair()` MUST be called at config load, engine init, and before data fetch.
- Future iterations MAY support USDC perps or inverse contracts via config/version—this is not a permanent restriction.
- Example (SIMULATOR-ONLY): `symbol="BTCUSD"` → raises `ValueError` before any data download.

**Margin Mode: Isolated Only**
- Simulator supports only isolated margin mode.
- MUST reject `margin_mode="cross"` at config validation.

**Indicator Declaration: Explicit Only**
- Simulator MUST NOT compute indicators unless declared in FeatureSpec/Idea Card.
- `TFContext.get_indicator_strict()` raises `KeyError` for undeclared indicators.
- Strategies MUST NOT assume any indicator exists by default.

**Indicator Metadata System v1**
- All indicators MUST have provenance metadata captured at computation time.
- Metadata stored in-memory only (no DB persistence).
- `feature_spec_id`: Stable hash identifying indicator computation (type, params, input_source).
- Multi-output indicators: SAME `feature_spec_id` for all outputs; `indicator_key` distinguishes outputs.
- Export available via `backtest metadata-smoke` CLI command.
- See: `docs/todos/INDICATOR_METADATA_SYSTEM_PHASES.md`

**Snapshot Architecture**
- `RuntimeSnapshotView` is a read-only view over cached data—MUST NOT deep copy.
- Snapshot access MUST be O(1)—no DataFrame operations in hot loop.
- History access via index offset (`prev_ema_fast(1)`, `bars_exec_low(20)`).

---

### DOMAIN RULES — LIVE TRADING / EXCHANGE (`src/core/`, `src/exchanges/`)

**Currency Semantics: Exchange-Native**
- Live trading uses exchange-native currency semantics.
- `size_usd` in live trading represents **exchange-native notional**, not simulator accounting currency.
- Variable names may use `size_usd` per existing patterns—this is NOT the same as simulator `size_usdt`.
- Simulator refactors MUST NOT force renames in live trading code.

**Domain Isolation**
- Simulator-only assumptions MUST NOT leak into live execution paths.
- Example (LIVE-ONLY): `src/core/risk_manager.py` uses `Signal.size_usd`—do NOT rename to match simulator.

**API Boundaries**
- All trading operations MUST go through `src/tools/*` for proper orchestration.
- WebSocket is ONLY for `GlobalRiskView` real-time monitoring—position queries use REST.

---

### DOMAIN RULES — SHARED / CORE (`src/config/`, `src/utils/`, `src/data/`)

**Domain Agnosticism**
- Shared utilities MUST NOT embed simulator-only or live-only assumptions.
- If a rule differs by domain, enforcement MUST occur at the domain boundary.

**No Leaking Domain Logic**
- `src/utils/` MUST NOT contain trading logic.
- `src/config/` MUST NOT contain execution logic.
- `src/data/` provides data—MUST NOT enforce trading semantics.

**Example**: `TimeRange` abstraction is domain-agnostic—used by both live and simulator.

## Agent Planning Rules

**TODO-Driven Work (See Critical Rules)**
- All work MUST have corresponding TODO markdown in `docs/todos/` before coding starts.
- Each code change MUST map to a TODO checkbox.
- New discoveries mid-work: STOP → update TODOs → continue.

**TODO Document Format:**
- Phase-based structure with checkboxes (`- [x]` / `- [ ]`)
- Acceptance criteria per phase
- Completed phases are FROZEN

**In-Context Todo Lists (Cursor Agent):**
- Keep items short (<70 chars) - high-level goals only
- Never include operational steps (linting, searching, reading) as todos
- Reference external files instead of inlining code
- As context fills: consolidate completed todos, drop verbose history

## Tool Layer (SHARED — Primary API)

All operations go through `src/tools/*`. Tools return `ToolResult` objects.

| Tool Category | Domain | Examples |
|---------------|--------|----------|
| Order tools | LIVE | `market_buy`, `limit_sell`, `cancel_order` |
| Position tools | LIVE | `list_open_positions`, `close_position` |
| Data tools | SHARED | `sync_ohlcv`, `query_funding_rates` |
| Backtest tools | SIMULATOR | `run_backtest_tool` |

For orchestrators/bots, use `ToolRegistry` for dynamic discovery:
- `registry.list_tools(category="orders")` — List tools
- `registry.execute("market_buy", symbol="SOLUSDT", usd_amount=100)` — Execute
- `registry.get_tool_info("market_buy")` — Get specs for AI agents

**See**: `docs/guides/CODE_EXAMPLES.md` for complete usage patterns

## Available Order Types (LIVE Domain)

| Category | Tools |
|----------|-------|
| Market | `market_buy`, `market_sell`, `market_buy_with_tpsl`, `market_sell_with_tpsl` |
| Limit | `limit_buy`, `limit_sell`, `partial_close` |
| Stop | `stop_market_buy`, `stop_market_sell`, `stop_limit_buy`, `stop_limit_sell` |
| Management | `get_open_orders`, `cancel_order`, `amend_order`, `cancel_all_orders` |
| Batch | `batch_market_orders`, `batch_limit_orders`, `batch_cancel_orders` |

**Simulator**: Uses `SimulatedExchange.submit_order()` via strategy signals—not the tools layer.

## Time-Range Queries (LIVE Domain)

**All live API history endpoints require explicit time ranges.** Never rely on Bybit's implicit defaults.

| Endpoint | Default | Max Range |
|----------|---------|-----------|
| Transaction Log | 24h | 7 days |
| Order/Trade History | 7d | 7 days |
| Closed PnL | 7d | 7 days |
| Borrow History | 30d | 30 days |

Use `TimeRange` abstraction: `TimeRange.last_24h()`, `TimeRange.from_window_string("4h")`

**Note**: Simulator uses explicit windows from config YAML—no implicit defaults allowed (see Critical Rules).

## Four-Leg API Architecture (LIVE + Data Domains)

The system has 4 independent API "legs" with strict separation:

| Leg | Purpose | Endpoint | Key Variable |
|-----|---------|----------|--------------|
| Trade LIVE | Real money trading | api.bybit.com | `BYBIT_LIVE_API_KEY` |
| Trade DEMO | Fake money trading | api-demo.bybit.com | `BYBIT_DEMO_API_KEY` |
| Data LIVE | Backtest/research data | api.bybit.com | `BYBIT_LIVE_DATA_API_KEY` |
| Data DEMO | Demo validation data | api-demo.bybit.com | `BYBIT_DEMO_DATA_API_KEY` |

**Selection:**
- Trading env: Set via `BYBIT_USE_DEMO` (true=demo, false=live) in env
- Data env: CLI Data Builder menu option 23 toggles LIVE/DEMO, or pass `env="demo"` to tools

**Simulator Note**: Backtest engine uses DuckDB historical data (fetched via Data legs)—no trading API calls.

**Smoke Tests:**
- `--smoke data/full/data_extensive/orders`: Force DEMO trading + LIVE data (safe)
- `--smoke live_check`: Uses LIVE credentials (opt-in, needs LIVE keys)

## REST vs WebSocket (LIVE Domain Only)

See **Critical Rules → Domain Rules — Live Trading** for WebSocket usage policy.

| Use Case | REST | WebSocket |
|----------|------|-----------|
| Current state | ✅ Primary | ❌ |
| Execute trades | ✅ Always | ❌ |
| Position queries | ✅ Always | ❌ |
| Risk monitoring | ✅ Basic | ✅ GlobalRiskView only |

**Note**: Simulator/backtest does NOT use WebSocket—all data is historical.

## API Rate Limits (LIVE Domain)

| Endpoint Type | Limit | Bot Uses |
|---------------|-------|----------|
| IP (public) | 600/5sec | 100/sec |
| Account/Position | 50/sec | 40/sec |
| Orders | 10/sec/symbol | 8/sec |

Rate limiter: `src/utils/rate_limiter.py`

**Simulator**: No rate limits—runs as fast as data allows.

## DEMO vs LIVE API (LIVE Domain — CRITICAL SAFETY)

| Environment | Endpoint | Money | Purpose |
|-------------|----------|-------|---------|
| **DEMO** | api-demo.bybit.com | FAKE | Testing |
| **LIVE** | api.bybit.com | REAL | Production |

### Strict Mode Mapping

```
✅ TRADING_MODE=paper + BYBIT_USE_DEMO=true   → Demo (fake funds)
✅ TRADING_MODE=real  + BYBIT_USE_DEMO=false  → Live (real funds)
❌ All other combinations → BLOCKED at startup
```

### Data vs Trading Separation

| Operation | API Used |
|-----------|----------|
| Historical/market data | **ALWAYS LIVE** |
| Trading (orders, positions) | **Configured** (demo or live) |
| Simulator/backtest | **No API** (uses DuckDB historical data) |

**Configuration**: See `env.example` for all environment variables

## Safety Features

See **Critical Rules → Safety & API Discipline** for enforcement requirements.

| Feature | Description |
|---------|-------------|
| Panic button | `panic_close_all_tool()` closes all positions |
| Risk limits | Enforced by `RiskManager` (live) or `RiskPolicy` (simulator) |
| Demo mode | Default safe testing environment |
| Mode validation | Blocks invalid TRADING_MODE/BYBIT_USE_DEMO combinations |
| Fail-fast validation | Simulator rejects invalid configs before data fetch |

## File Organization

| Directory | Domain | Contents |
|-----------|--------|----------|
| `src/backtest/` | SIMULATOR | Backtest engine, simulated exchange, snapshots, features |
| `src/core/` | LIVE | Exchange manager, position, risk, order execution |
| `src/exchanges/` | LIVE | Bybit API client |
| `src/tools/` | SHARED | Public API surface for CLI/agents |
| `src/data/` | SHARED | Market data, DuckDB storage, realtime state |
| `src/config/` | SHARED | Configuration (domain-agnostic) |
| `src/utils/` | SHARED | Logging, rate limiting, helpers |
| `docs/todos/` | — | TODO phase documents (canonical work tracking) |

## Reference Documentation

See **Critical Rules → Safety & API Discipline** for the requirement to check reference docs.

| Topic | Location |
|-------|----------|
| Bybit API | `reference/exchanges/bybit/docs/v5/` |
| pybit SDK | `reference/exchanges/pybit/` |

## Smoke Tests

| Mode | Command | Domain | Description |
|------|---------|--------|-------------|
| Full | `--smoke full` | LIVE (DEMO) | All CLI features (data + trading + diagnostics) |
| Data | `--smoke data` | DATA | Data builder only |
| Data Extensive | `--smoke data_extensive` | DATA | Clean DB, build sparse history, fill gaps, sync |
| Orders | `--smoke orders` | LIVE (DEMO) | All order types: market, limit, stop, TP/SL, trailing |
| Live Check | `--smoke live_check` | LIVE (LIVE) | Opt-in connectivity test (requires LIVE keys) |
| Metadata | `backtest metadata-smoke` | SIMULATOR | Indicator Metadata v1 validation (synthetic data, no DB) |

**Note**: ALL validation runs through CLI commands. No pytest files exist in this codebase.

The `data_extensive` test:
1. Deletes ALL existing data (clean slate)
2. Builds sparse OHLCV history with intentional date gaps
3. Syncs funding rates and open interest
4. Fills gaps and syncs to current
5. Queries all data types
6. Runs maintenance tools (heal, cleanup, vacuum)
7. Verifies final database state

**WARNING**: `delete_all_data_tool` permanently deletes all historical data.

## Proactive Validation During Refactoring

**MANDATORY**: Use the `validate` agent proactively during refactoring to catch breaking changes early.

### Two-Agent Validation System

| Agent | Model | Role | Can Modify |
|-------|-------|------|------------|
| `validate` | Sonnet | Runs tests, reports results | Nothing (read-only) |
| `validate-updater` | Opus | Updates validation system | IdeaCards, validate.md, CLAUDE.md |

**Flow**:
1. `validate` runs tests, reports failures/coverage gaps
2. If validation system needs updating → invoke `validate-updater`
3. `validate-updater` adds IdeaCards, updates expectations, fixes coverage

**When to invoke `validate-updater`**:
- New indicator added to registry
- Indicator params/output_keys changed
- New engine feature needs test coverage
- Test expectations changed
- Coverage gap identified

### When to Invoke Validation

| After Changing... | Invoke Validation With |
|-------------------|------------------------|
| `indicator_registry.py` | "Run audit-toolkit and normalize-batch" |
| `src/backtest/engine*.py` | "Run normalize-batch, then one backtest run" |
| `src/backtest/sim/*.py` | "Run audit-rollup" |
| `src/backtest/metrics.py` | "Run metrics-audit" |
| `configs/idea_cards/*.yml` | "Run normalize on that card" |
| `src/cli/*.py` | "Quick validate - syntax check" |
| Any backtest code | "Run TIER 1-2 validation" |

### Validation IdeaCards

All validation IdeaCards are in `configs/idea_cards/_validation/` with naming convention `V_XX_category_description.yml`:

| Range | Category | Count |
|-------|----------|-------|
| V_01-V_09 | Single-TF | 3 cards |
| V_11-V_19 | MTF | 3 cards |
| V_21-V_29 | Warmup | 2 cards |
| V_31-V_39 | Coverage (42 indicators) | 7 cards |
| V_41-V_49 | Math Parity | 2 cards |
| V_51-V_59 | 1m Drift | 1 card |
| V_E01-V_E99 | Error cases | 3 cards |

**Total**: 24 IdeaCards covering all 42 indicators

### Validation Tiers

```
TIER 0: Quick Check (<10 sec) - For tight refactoring loops
TIER 1: IdeaCard Normalization - ALWAYS FIRST (validates configs against engine)
TIER 2: Unit Audits - audit-toolkit, audit-rollup, metrics-audit, metadata-smoke
TIER 3: Error Case Validation - Verify broken cards fail correctly
TIER 4+: Integration Tests (DB required)
```

### Key Principle

**IdeaCard normalization is the critical gate.** It validates that:
- Indicator keys match the registry
- Params are valid for each indicator type
- Signal rules reference declared features
- Schema is correct

As the engine evolves, normalization ensures IdeaCards stay in sync. When agents generate IdeaCards, they MUST run normalization for validation feedback.

## External References

| Topic | File |
|-------|------|
| Code examples | `docs/guides/CODE_EXAMPLES.md` |
| Orchestrator example | `docs/examples/orchestrator_example.py` |
| Environment variables | `env.example` |
| Data architecture | `docs/architecture/DATA_ARCHITECTURE.md` |
| Simulated exchange | `docs/architecture/SIMULATED_EXCHANGE.md` |
| Artifact storage format | `docs/architecture/ARTIFACT_STORAGE_FORMAT.md` |
| IdeaCard → Engine flow | `docs/architecture/IDEACARD_ENGINE_FLOW.md` |
| Project rules | `docs/project/PROJECT_RULES.md` |
| Project overview | `docs/project/PROJECT_OVERVIEW.md` |

### TODO Phase Documents (Canonical Work Tracking)

**Active:**

| Document | Status | Next Step |
|----------|--------|-----------|
| `docs/todos/ARRAY_BACKED_HOT_LOOP_PHASES.md` | Phases 1-4 ✅, Phase 5 📋 READY | Market Structure Features |
| `docs/todos/REGISTRY_CONSOLIDATION_PHASES.md` | Phases 0-2 ✅, Phase 3 📋 READY | Add structure indicators |
| `docs/todos/BACKTEST_ANALYTICS_PHASES.md` | Phases 1-4 ✅, 5-6 📋 pending | Benchmark comparison (future) |

**Recently Archived (January 2026):**

| Document | Scope |
|----------|-------|
| `docs/todos/archived/2026-01-01/LEGACY_CLEANUP_PHASES.md` | Removed dual metrics, warmup_multiplier |
| `docs/todos/archived/2026-01-01/METRICS_ENHANCEMENT_PHASES.md` | 62-field BacktestMetrics |
| `docs/todos/archived/2026-01-01/IDEACARD_VALUE_FLOW_FIX_PHASES.md` | Fixed slippage_bps, MMR flow |
| `docs/todos/archived/2026-01-01/CLI_MENU_TOOLS_ALIGNMENT_PHASES.md` | IdeaCard menus, tools refactor |

**Full archive index**: `docs/todos/INDEX.md`
