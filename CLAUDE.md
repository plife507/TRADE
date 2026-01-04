# CLAUDE.md

Guidance for Claude when working with the TRADE trading bot.

> **Code examples**: See `docs/guides/CODE_EXAMPLES.md` | **Env vars**: See `env.example`

---

## PRIME DIRECTIVE: ALL FORWARD, NO LEGACY

**NO backward compatibility. NO legacy fallbacks. NO shims. EVER.**

- Delete old code, don't wrap it
- Update all callers, don't add aliases
- Break changes are expected and welcomed
- If something breaks, fix it forward

This applies to ALL code changes in this repository.

---

## PRIME DIRECTIVE: MODERN PYTHON ONLY

**Use ONLY modern Python syntax and patterns. NO legacy compatibility.**

- Type hints: `def foo(x: str) -> int:` (always)
- f-strings: `f"{name}"` (never `%` or `.format()`)
- Pathlib: `Path()` (never `os.path`)
- Dataclasses: `@dataclass` for data containers
- Match statements: `match x:` where cleaner than if/elif
- Walrus operator: `:=` where it improves readability
- Union types: `X | None` (never `Optional[X]`)
- Dict/list syntax: `dict[str, int]` (never `Dict[str, int]`)

Minimum Python version: **3.12**

---

## PRIME DIRECTIVE: LF LINE ENDINGS ONLY

**ALL files MUST use LF (`\n`) line endings. NEVER CRLF (`\r\n`).**

When writing files with Python on Windows:
```python
# CORRECT - explicit LF
open(file, 'w', newline='\n').write(content)

# CORRECT - binary mode
open(file, 'wb').write(content.encode('utf-8'))

# WRONG - will write CRLF on Windows
open(file, 'w').write(content)
```

This is enforced by `.gitattributes` (`* text=auto`, `*.py eol=lf`).

### "File Unexpectedly Modified" Error (Windows Edit Tool Issue)

**Why this happens**: The Edit tool compares file signatures between read and write. On Windows, several factors cause the signature to change unexpectedly:

1. **Line ending normalization** - Git or editors may convert LF to CRLF between read and write
2. **External tool modifications** - VS Code auto-formatters, linters (black, ruff), or git hooks may modify files
3. **Stale reads** - If too much time passes between reading and editing, another process may modify the file

**Decision Tree - Edit vs Write:**

| Scenario | Tool to Use |
|----------|-------------|
| New file | Write |
| Changing >50% of file | Write |
| Surgical change (1-20 lines) | Edit (with fresh Read) |
| Edit failed once | Re-read → retry Edit |
| Edit failed twice | Use Write |
| Untracked file | Write (preferred) |

**Troubleshooting steps (in order)**:

1. **Read immediately before editing** - This resolves most cases. The file must be freshly read right before the Edit call.
   ```
   Read file → Edit file (no delay, no other operations between)
   ```

2. **Use smaller, more targeted edits** - Large edits spanning many lines are more likely to hit timing issues.

3. **Check for CRLF contamination**:
   ```bash
   git ls-files --eol | grep "w/crlf"  # Find CRLF files in working tree
   ```

4. **For untracked files** - The issue is more persistent because git normalization does not apply. Options:
   - Use the Write tool to overwrite the entire file
   - Use bash: `cat > file.py << 'EOF' ... EOF`

**CRITICAL for Agents**: Any agent with Write+Edit tools MUST follow the decision tree above. When in doubt, use Write.

---

## Project Overview

TRADE is a **modular, production-ready** Bybit futures trading bot with complete UTA support, comprehensive order types, position management, tool registry for orchestrator/bot integration, and risk controls.

**Key Philosophy**: Safety first, modular always, tools as the API surface, ALL FORWARD.

## Trading Hierarchy

The system uses a four-level hierarchy for organizing trading logic:

| Level | Name | Description | Location |
|-------|------|-------------|----------|
| 1 | **Setup** | Atomic trading rules (single condition or pattern) | Within Play YAML |
| 2 | **Play** | Complete strategy (entry/exit rules, risk params) | `configs/plays/` |
| 3 | **Playbook** | Collection of related Plays | `configs/playbooks/` |
| 4 | **System** | Deployment configuration (capital, risk limits) | `configs/systems/` |

### Promotion Path

```
The Forge (src/forge/) → configs/plays/ (proven)
     ↓                          ↓
  Develop & Test            Production-ready
  Experimental              Validated
```

- **The Forge** (`src/forge/`): Development and validation environment for experimental Plays
- **configs/**: Proven, validated configurations ready for backtesting or live use

## Current Objective (Backtest Engine Roadmap)

We are building the backtesting + strategy factory stack in **phases**. The canonical roadmap lives in `docs/project/PROJECT_OVERVIEW.md` under **"Project Roadmap – TRADE Backtest Engine & Strategy Factory"**.

### Current State (January 2026)

**Engine Complete**:
- 62-field BacktestMetrics (tail risk, leverage, MAE/MFE, benchmark alpha)
- 42 indicators in INDICATOR_REGISTRY (single source of truth)
- 6 structures in STRUCTURE_REGISTRY (+derived_zone in Phase 12)
- Play-first CLI with full menu coverage
- 11 validation Plays (V_100+ blocks format only)

**Derived Zones - Phase 12 (2026-01-04)**:
- K slots + aggregates pattern for derived zones from swing pivots
- zone0_*/zone1_*/... slot fields with NONE/ACTIVE/BROKEN states
- Aggregate fields: any_active, any_touched, active_count, closest_active_*
- See: `docs/architecture/DERIVATION_RULE_INVESTIGATION.md`

**Incremental State Architecture (2026-01-03)**:
- O(1) hot loop access via MonotonicDeque/RingBuffer
- STRUCTURE_REGISTRY parallel to INDICATOR_REGISTRY
- Agent-composable Play blocks (variables, features, structures, rules)
- See: `docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md`
- See: `docs/architecture/PLAY_VISION.md`

**1m Evaluation Loop (2026-01-02)**:
- mark_price resolution in snapshot
- 1m TP/SL checking in hot loop
- See: `docs/todos/1M_EVAL_LOOP_REFACTOR.md`

**Audit Swarm (2026-01-01)**:
- 12 P1 fixes implemented (critical blockers resolved)
- P1-09 (O(n) hot loop) fixed by Incremental State
- See: `docs/audits/OPEN_BUGS.md`

### Explicitly off-limits until later phases

- Forecasting models / ML, composite strategies, strategy selection policies
- "Factory" orchestration beyond "run this system" (no automated promotions yet)
- Demo/live automation for backtested strategies

### Intended module placement (high-level)

- Core backtest engine: `src/backtest/`
  - Modular exchange: `src/backtest/sim/` (pricing, execution, funding, liquidation, ledger, metrics, constraints)
  - Engine orchestrator: `src/backtest/engine.py`
- The Forge: `src/forge/` (development & validation environment)
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
│   │   ├── features/              # FeatureSpec, FeatureFrameBuilder
│   │   └── incremental/           # O(1) structure detection (STRUCTURE_REGISTRY)
│   ├── forge/                     # DOMAIN: Development & Validation Environment
│   │   └── ...                    # Play development, testing, promotion tools
│   ├── core/                      # DOMAIN: Live Trading (exchange-native semantics)
│   │   ├── risk_manager.py        # Live risk checks (Signal.size_usdt)
│   │   ├── position_manager.py    # Position tracking
│   │   └── order_executor.py      # Order execution
│   ├── exchanges/                 # DOMAIN: Live Trading (Bybit API)
│   │   └── bybit_client.py        # Bybit API wrapper
│   ├── config/                    # SHARED: Configuration (domain-agnostic)
│   ├── data/                      # SHARED: Market data, DuckDB, WebSocket state
│   ├── tools/                     # SHARED: CLI/API surface (PRIMARY INTERFACE)
│   ├── utils/                     # SHARED: Logging, rate limiting, helpers
│   └── risk/global_risk.py        # Account-level risk (GlobalRiskView)
├── configs/
│   ├── plays/                     # Proven Play configurations (strategies)
│   │   └── _validation/           # Validation Plays (V_100+)
│   ├── playbooks/                 # Collections of related Plays
│   └── systems/                   # Deployment configurations
├── docs/
│   ├── todos/                     # TODO phase documents (canonical work tracking)
│   ├── architecture/              # Architecture docs
│   ├── project/                   # Project documentation
│   └── guides/                    # Setup/development guides
├── CLAUDE.md                      # AI assistant guidance (this file)
└── trade_cli.py                   # CLI entry point
```

## The Forge (Development Environment)

The Forge (`src/forge/`) is the development and validation environment for experimental Plays before promotion to production configs.

### Purpose

- **Develop**: Create and iterate on new Play configurations
- **Validate**: Run validation checks before promotion
- **Test**: Execute backtests in isolated environment
- **Promote**: Move proven Plays to `configs/plays/`

### Workflow

```
1. Create Play in Forge → 2. Validate & Test → 3. Promote to configs/
```

### Key Principle

Plays in the Forge are experimental. Only after passing validation gates do they get promoted to `configs/plays/` for production use.

## Timeframe Definitions (Multi-Timeframe Trading)

The engine supports multi-timeframe analysis with three timeframe roles. These terms are used consistently throughout the codebase.

### Timeframe Roles

| Role | Meaning | Typical Values | Purpose |
|------|---------|----------------|---------|
| **LTF** | Low Timeframe | 1m, 3m, 5m, 15m | Execution timing (entries/exits), micro-structure. Engine iterates bar-by-bar. |
| **MTF** | Mid Timeframe | 30m, 1h, 2h, 4h | Trade bias + structure context for LTF execution. |
| **HTF** | High Timeframe | 6h, 8h, 12h, 1D | Higher-level trend + major levels. **Capped at 1D** (no weekly/monthly). |
| **exec** | Execution TF | = LTF | The timeframe at which trading decisions are evaluated. Defaults to LTF in Play. |

### Hierarchy Rule

```
HTF >= MTF >= LTF (in minutes)
```

This is enforced by `validate_tf_mapping()` in `src/backtest/runtime/timeframe.py`.

### Example Configuration

```yaml
# Play timeframes
tf: "15m"           # exec/LTF - bar-by-bar stepping
mtf: "1h"           # Optional intermediate TF
htf: "4h"           # Optional higher TF for context
```

Internally maps to:
```python
tf_mapping = {
    "ltf": "15m",   # = tf (exec)
    "mtf": "1h",    # or defaults to ltf if not specified
    "htf": "4h",    # or defaults to ltf if not specified
}
```

### Forward-Fill Behavior

Any timeframe **slower than exec** forward-fills its values until its bar closes:
- **exec** (LTF): Updates every bar (no forward-fill)
- **MTF**: Forward-fills until MTF bar closes
- **HTF**: Forward-fills until HTF bar closes

This ensures no-lookahead: values always reflect the last **CLOSED** bar, never partial/forming bars.

## Module Documentation

Each major module has its own CLAUDE.md with domain rules and active TODOs:

| Module | Path | Domain |
|--------|------|--------|
| Backtest | `src/backtest/CLAUDE.md` | Simulator, engine, market structure |
| Forge | `src/forge/CLAUDE.md` | Development & validation environment |
| Core | `src/core/CLAUDE.md` | Live trading execution |
| Data | `src/data/CLAUDE.md` | DuckDB, market data |
| Tools | `src/tools/CLAUDE.md` | CLI/API surface |
| Exchanges | `src/exchanges/CLAUDE.md` | Bybit API client |

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
- Example (GLOBAL): `REQUIRED_INDICATOR_COLUMNS` constant was deleted—indicators MUST be declared via FeatureSpec/Play.

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

**Currency Model: USDT Only (Global Standard)**
- **ALL sizing fields use `size_usdt` globally** — both simulator and live domains.
- MUST NOT use `size_usd` or `size` anywhere — use `size_usdt`.
- Example: `Signal.size_usdt`, `Position.size_usdt`, `Trade.entry_size_usdt`.

**Symbol Validation: USDT Pairs Only (Current Iteration)**
- Simulator MUST reject symbols not ending in "USDT" (e.g., `BTCUSD`, `BTCUSDC`) in the current iteration.
- `validate_usdt_pair()` MUST be called at config load, engine init, and before data fetch.
- Future iterations MAY support USDC perps or inverse contracts via config/version—this is not a permanent restriction.
- Example (SIMULATOR-ONLY): `symbol="BTCUSD"` → raises `ValueError` before any data download.

**Margin Mode: Isolated Only**
- Simulator supports only isolated margin mode.
- MUST reject `margin_mode="cross"` at config validation.

**Indicator Declaration: Explicit Only**
- Simulator MUST NOT compute indicators unless declared in FeatureSpec/Play.
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

### DOMAIN RULES — THE FORGE (`src/forge/`)

**Experimental by Default**
- All Plays in the Forge are considered experimental until promoted.
- Forge Plays MUST NOT be referenced by production systems.

**Validation Before Promotion**
- Plays MUST pass all validation tiers before promotion to `configs/plays/`.
- Promotion is a manual, deliberate action—not automated.

**Isolation**
- Forge has its own configuration namespace—no collision with production configs.
- Test data and artifacts stay within Forge scope.

---

### DOMAIN RULES — LIVE TRADING / EXCHANGE (`src/core/`, `src/exchanges/`)

**Currency Semantics: USDT Global Standard**
- **ALL sizing fields use `size_usdt` globally** — unified across live and simulator domains.
- MUST NOT use `size_usd` anywhere — use `size_usdt`.
- Example: `Signal.size_usdt`, `Position.size_usdt`, `RiskConfig.max_position_size_usdt`.

**Domain Isolation**
- Simulator-only assumptions MUST NOT leak into live execution paths.

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

**In-Context Todo Lists:**
- Keep items short (<70 chars) - high-level goals only
- Never include operational steps (linting, searching, reading) as todos
- Reference external files instead of inlining code
- As context fills: consolidate completed todos, drop verbose history

**Agent Model Selection:**
- **ALWAYS use `model="opus"` for coding agents** (Task tool with code implementation)
- Use Opus for: refactoring, bug fixes, feature implementation, code review
- Haiku acceptable only for: quick file searches, simple queries, read-only exploration

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
| Current state | Yes Primary | No |
| Execute trades | Yes Always | No |
| Position queries | Yes Always | No |
| Risk monitoring | Yes Basic | Yes GlobalRiskView only |

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
TRADING_MODE=paper + BYBIT_USE_DEMO=true   → Demo (fake funds)
TRADING_MODE=real  + BYBIT_USE_DEMO=false  → Live (real funds)
All other combinations → BLOCKED at startup
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
| `src/forge/` | DEVELOPMENT | Play development, validation, promotion tools |
| `src/core/` | LIVE | Exchange manager, position, risk, order execution |
| `src/exchanges/` | LIVE | Bybit API client |
| `src/tools/` | SHARED | Public API surface for CLI/agents |
| `src/data/` | SHARED | Market data, DuckDB storage, realtime state |
| `src/config/` | SHARED | Configuration (domain-agnostic) |
| `src/utils/` | SHARED | Logging, rate limiting, helpers |
| `configs/plays/` | — | Proven Play configurations |
| `configs/playbooks/` | — | Collections of related Plays |
| `configs/systems/` | — | Deployment configurations |
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

## Audit & Bug Tracking

See `docs/audits/OPEN_BUGS.md` for:
- Audit checklist (common bug patterns)
- P0-P3 prioritized bugs with status

See `docs/todos/TODO.md` for active work tracking.

## Proactive Validation During Refactoring

**MANDATORY**: Use the `validate` agent proactively during refactoring to catch breaking changes early.

### Two-Agent Validation System

| Agent | Model | Role | Can Modify |
|-------|-------|------|------------|
| `validate` | Sonnet | Runs tests, reports results | Nothing (read-only) |
| `validate-updater` | Opus | Updates validation system | Plays, validate.md, CLAUDE.md |

**Flow**:
1. `validate` runs tests, reports failures/coverage gaps
2. If validation system needs updating → invoke `validate-updater`
3. `validate-updater` adds Plays, updates expectations, fixes coverage

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
| `configs/plays/*.yml` | "Run normalize on that Play" |
| `src/cli/*.py` | "Quick validate - syntax check" |
| Any backtest code | "Run TIER 1-2 validation" |

### Validation Plays

Location: `configs/plays/_validation/`

| Play | Purpose |
|------|---------|
| V_100_blocks_basic.yml | Basic blocks DSL validation |
| V_101_all_any.yml | Nested all/any boolean logic |
| V_102_between.yml | Between operator validation |
| V_103_crossover.yml | cross_above/cross_below operators |
| V_104_holds_for.yml | holds_for window operator |
| V_105_occurred_within.yml | occurred_within window operator |
| V_106_not_operator.yml | NOT boolean operator |
| V_115_type_safe_operators.yml | Type-safe operator validation |
| V_120_derived_zones_basic.yml | Derived zones K slots |
| V_121_derived_zones_aggregates.yml | Derived zones aggregate fields |
| V_122_derived_zones_empty_slots.yml | Empty slot guard patterns |

**Total**: 11 validation Plays (V_100+ blocks format only)

### Validation Tiers

```
TIER 0: Quick Check (<10 sec) - For tight refactoring loops
TIER 1: Play Normalization - ALWAYS FIRST (validates configs against engine)
TIER 2: Unit Audits - audit-toolkit, audit-rollup, metrics-audit, metadata-smoke
TIER 3: Error Case Validation - Verify broken Plays fail correctly
TIER 4+: Integration Tests (DB required)
```

### Key Principle

**Play normalization is the critical gate.** It validates that:
- Indicator keys match the registry
- Params are valid for each indicator type
- Blocks DSL references declared features
- Schema is correct

As the engine evolves, normalization ensures Plays stay in sync. When agents generate Plays, they MUST run normalization for validation feedback.

## External References

| Topic | File |
|-------|------|
| Code examples | `docs/guides/CODE_EXAMPLES.md` |
| Orchestrator example | `docs/examples/orchestrator_example.py` |
| Environment variables | `env.example` |
| Data architecture | `docs/architecture/DATA_ARCHITECTURE.md` |
| Simulated exchange | `docs/architecture/SIMULATED_EXCHANGE.md` |
| Artifact storage format | `docs/architecture/ARTIFACT_STORAGE_FORMAT.md` |
| Play → Engine flow | `docs/architecture/PLAY_ENGINE_FLOW.md` |
| Play Syntax | `docs/guides/PLAY_SYNTAX.md` |

### Vendor References (Read-Only Truth)

| Topic | Path |
|-------|------|
| Bybit V5 API docs | `reference/exchanges/bybit/docs/v5/` |
| pybit SDK source | `reference/exchanges/pybit/` |
| DuckDB docs | `reference/duckdb/` |
| pandas-ta source | `reference/pandas_ta_repo/` |

**Rule**: Check vendor references before guessing API params, indicator formulas, or DB syntax.

### Work Tracking

| Document | Purpose |
|----------|---------|
| `docs/todos/TODO.md` | Active work tracking |
| `docs/audits/OPEN_BUGS.md` | Bug tracker with audit checklist |
| `docs/todos/archived/` | Completed phase documents |
