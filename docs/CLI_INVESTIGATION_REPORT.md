# CLI Investigation Report

**Date:** 2026-02-12
**Branch:** feature/unified-engine
**Investigators:** cli-mapper (Sonnet), pipeline-analyst (Sonnet), live-reviewer (Sonnet), synthesis (Opus)

---

## Executive Summary

The TRADE infrastructure is **more production-ready than the CLI surface suggests**. The unified engine, live runner, exchange integration, and safety layers are all production-quality. The bottleneck to end-to-end trading is **CLI workflow friction** — redundant commands, missing operational commands, and gaps in the backtest-to-live escalation path.

| Layer | Rating |
|-------|--------|
| PlayEngine (unified backtest/live) | Production Ready |
| LiveRunner (state machine, multi-TF, reconnection) | Production Ready |
| Exchange Integration (Bybit V5, full order types) | Production Ready |
| Safety & Risk (panic, DCP, daily loss, drawdown) | Production Ready |
| Demo/Live Separation | Production Ready |
| Configuration | Functional |
| CLI Surface & User Workflow | **Needs Work** |

---

## Part 1: CLI Architecture Map

### Entry Points

**Single entry point:** `trade_cli.py`

Two modes:
- **Interactive:** `python trade_cli.py` (launches menu-driven TUI with environment selector)
- **Non-interactive:** Subcommands or `--smoke` flags (headless, returns exit code)

### Top-Level CLI Commands

| Command | Sub-commands | Status |
|---------|-------------|--------|
| `backtest` | 18 sub-subcommands | Well-implemented, most mature |
| `play` | 7 sub-subcommands (run/status/stop/watch/logs/pause/resume) | Core works; lifecycle via EngineManager |
| `test` | 4 sub-subcommands (indicators/parity/live-parity/agent) | Implemented |
| `validate` | Positional tier arg (quick/standard/full/pre-live) | Well-implemented, gate-based |
| `account` | 2 sub-subcommands (balance/exposure) | Simple, working |
| `position` | 2 sub-subcommands (list/close) | Simple, working |
| `panic` | No sub-subcommands, requires `--confirm` | Working |

**Global flags:** `--smoke`, `--fresh-db`, `--debug`

### Backtest Sub-commands (18 total)

| Command | Purpose | Status |
|---------|---------|--------|
| `backtest run` | Run a play backtest | **Golden path** |
| `backtest preflight` | Check data/config readiness | Working |
| `backtest indicators` | Discover indicator keys | Working |
| `backtest data-fix` | Fix data gaps for a play | Working |
| `backtest list` | List available plays | Working |
| `backtest play-normalize` | Validate/normalize YAML | Working |
| `backtest play-normalize-batch` | Batch normalize directory | Working |
| `backtest verify-suite` | Global verification suite | Working |
| `backtest audit-toolkit` | Indicator registry contract audit | Working |
| `backtest audit-incremental-parity` | Incremental vs vectorized parity | Working |
| `backtest audit-structure-parity` | Structure detector parity | Working |
| `backtest metadata-smoke` | Indicator metadata validation | Working |
| `backtest mark-price-smoke` | Mark price engine validation | Working |
| `backtest structure-smoke` | Structure detector via engine | Working |
| `backtest math-parity` | In-memory math parity | Working |
| `backtest audit-snapshot-plumbing` | Phase 4 snapshot parity | Working |
| `backtest verify-determinism` | Hash-based determinism check | Working |
| `backtest metrics-audit` | Financial metrics validation | Working |
| `backtest audit-rollup` | 1m rollup parity | Working |

### Play Sub-commands (7 total)

| Command | Purpose | Status |
|---------|---------|--------|
| `play run` | Run play in any mode (backtest/demo/live/shadow) | Core command |
| `play status` | Check running instances | Via EngineManager |
| `play stop` | Stop running instance | `--force`, `--all`, `--close-positions` |
| `play watch` | Live dashboard (rich Live) | Shows bars/signals/orders/reconnects |
| `play logs` | Stream journal entries | `--follow`, `--lines` |
| `play pause` | Pause signal evaluation | Implemented |
| `play resume` | Resume paused instance | Implemented |

### Validate Command (Gate-Based Tiers)

| Tier | Gates | Duration |
|------|-------|----------|
| quick | G1 YAML, G2 Registry, G3 Incremental Parity, G4 Core Plays, G7 Sim, G8-G10 | ~10s |
| standard | + G5 Structure Parity, G6 Rollup, operator/structure/complexity suites | ~2min |
| full | + indicator/pattern suites, math verification, determinism | ~10min |
| pre-live | PL1 API Connectivity, PL2 Balance, PL3 No Position Conflicts, G1, G4 | Per-play |

### Interactive TUI Menu Structure

```
Main Menu (11 items)
├── 1. Account & Balance → 9 sub-items
├── 2. Positions → 6 sub-items
├── 3. Orders → market/limit/stop sub-menus + manage
├── 4. Market Data → prices, OHLCV, funding, OI, orderbook, instruments
├── 5. Data Builder → 24 items (DB info, sync, query, maintenance)
├── 6. Backtest Engine → Play Backtests / Audits / Analytics
├── 7. The Forge → validate, audit, stress test, synthetic backtest
├── 8. Connection Test
├── 9. Health Check
├── 10. PANIC Close All
└── 11. Exit
```

### Smoke Test Modes (7)

| Mode | What it tests |
|------|--------------|
| `data` | Data builder tools |
| `full` | Data + trading + diagnostics |
| `data_extensive` | Clean DB, gaps, fill, sync |
| `orders` | Comprehensive order smoke |
| `live_check` | LIVE API connectivity (opt-in) |
| `backtest` | Backtest engine |
| `forge` | Forge plumbing and verification |

### Tool Layer (`src/tools/`)

All CLI commands delegate to tool functions:

| File | Scope |
|------|-------|
| `account_tools.py` | Balance, exposure, portfolio, history, collateral |
| `position_tools.py` | List, close, panic, TP/SL, risk limits |
| `order_tools.py` | Market/limit/stop orders, amend, cancel |
| `market_data_tools.py` | Prices, OHLCV, funding, OI, orderbook |
| `data_tools.py` / `data_tools_sync.py` / `data_tools_status.py` / `data_tools_query.py` | DuckDB data ops |
| `backtest_play_tools.py` | Backtest run, preflight, data-fix, list, normalize |
| `backtest_audit_tools.py` | All audit tools |
| `forge_stress_test_tools.py` | Stress test suite |
| `diagnostics_tools.py` | Connection test, health check |
| `tool_registry.py` | Unified ToolRegistry for AI agents |

---

## Part 2: Backtest → Demo → Live Pipeline Analysis

### Step 1: Play Authoring

**How it works:**
- Plays are YAML files in `plays/` directory
- Structure: `version`, `name`, `symbol`, `timeframes`, `account`, `features`, `structures`, `actions`, `position_policy`, `risk`
- Validation: `backtest play-normalize --play X`
- 277+ plays exist across test suites

**What works:** DSL is expressive, YAML is human-readable, normalization validates at build time.

**Gaps:**
- No `play new` or `play init` template command
- No interactive play builder
- No play diff/compare tool

### Step 2: Backtesting

**End-to-end flow:**
```
trade_cli.py backtest run --play X --start 2025-01-01 --end 2025-06-30 --fix-gaps
  → load_play(play_id)
  → backtest_preflight_play_tool() (data validation, auto-sync)
  → _validate_indicator_gate()
  → create_engine_from_play() + run_engine_with_play()
  → BacktestRunner loops bars through PlayEngine.process_bar()
  → SimulatedExchange handles fills, TP/SL via 1m subloop
  → Artifacts written to backtests/{run_id}/
```

**What works:** Golden path with gates at each phase, preflight auto-sync, 1m subloop accuracy, artifact system with hashes.

**Gaps:**
- No backtest comparison tool (run A vs run B)
- No portfolio simulation (multi-play)
- `compute_values` not implemented in `backtest_indicators_tool()`

### Step 3: Result Analysis

**What exists:** Artifacts in `backtests/{run_id}/` (manifest JSON, equity CSV, trade log, pipeline signature). `ResultsSummary.to_dict()` returns standard metrics.

**Gaps:**
- No CLI for viewing past results (`backtest results --run-id X`)
- No equity curve visualization
- No trade-by-trade analysis command
- No summary aggregation across runs

### Step 4: Validation

**What works:** Tiered validation (quick/standard/full/pre-live), 170+ synthetic plays, math verification.

**Gaps:**
- Pre-live gate is thin (doesn't check exchange connectivity, balance sufficiency, data freshness)
- No "dry run" mode (replay recent data without exchange)

### Step 5: Demo Mode

**Architecture:**
```
trade_cli.py play run --play X --mode demo
  → PlayEngineFactory.create(play, mode="demo")
  → LiveDataProvider(demo=True) → api-demo.bybit.com
  → LiveExchange(demo=True) → paper trading on Bybit testnet
  → LiveRunner → WebSocket candle stream → engine.process_bar()
```

Uses Bybit's actual testnet (real order matching, not local simulation).

**What works:** Multi-TF identical to backtest, incremental indicators O(1), structure states, warmup logic, trade journal.

**Gaps:**
- No auto-data-sync before demo start
- No backtest-vs-demo comparison tooling
- Watch/logs not integrated into single dashboard

### Step 6: Live Mode

**Differences from demo:** Uses `api.bybit.com`, requires `--confirm` + pre-live validation, DCP auto-activated, double confirmation in interactive mode.

**Safety guards:** Panic state, safety checks before every order, max drawdown tracking, daily loss tracker seeded from exchange on restart, position reconciliation every 5 min, SL vs liquidation price validation.

**Gaps:**
- No incremental state restore on crash (indicators/structures re-warm from scratch)
- No auto-data-sync on startup
- No PnL summary on shutdown

### Step 7: Data Management

**Tools available:** `sync_symbols_tool`, `sync_range_tool`, `fill_gaps_tool`, `heal_data_tool`, `sync_to_now_tool`, `build_symbol_history_tool`, `backtest_data_fix_tool`.

**What works:** Preflight auto-sync, `build_symbol_history_tool` for new symbols, bounded data-fix.

**Gaps:**
- No `data status --play X` non-interactive command
- No auto 1m sync for new timeframes
- No data freshness check for live/demo startup

---

## Part 3: Live/Demo Infrastructure Readiness

### LiveRunner — PRODUCTION READY

- Full formal state machine (STOPPED → STARTING → RUNNING → RECONNECTING → STOPPING → ERROR)
- Thread-safe state changes with illegal transition rejection
- Multi-TF: filters by symbol AND play timeframes, signal eval only on exec TF
- Exponential backoff reconnection (configurable base/max delay, max attempts)
- Health monitoring: alerts if no candle within 2.5x expected interval
- Position sync on startup (G0.4), periodic reconciliation (default 5 min)
- Fail-closed safety integration

**Minor gaps:** No circuit breaker for rapid reconnect cycling. No auto-escalate to panic after N missed candles.

### Exchange Integration — PRODUCTION READY

- Bybit V5 only (deeply integrated via pybit SDK)
- Strict mode/API mapping (PAPER→DEMO, REAL→LIVE, mismatch = ValueError)
- DCP auto-activated for live (10s window)
- One-way position mode verification at startup
- Full order type coverage: market, limit, stop, conditional, batch (10/batch auto-split)
- `open_position_with_rr()`: SL verification + retry, emergency close on SL failure
- Hybrid WS/REST balance queries (60s stale threshold)

**Minor gap:** No explicit client-side rate limiter.

### Demo vs Live — PRODUCTION READY

- Clean separation at every layer (API keys, pybit demo flag, API endpoints)
- CLI requires `--confirm` for live
- Auto pre-live validation gate
- EngineManager: max 1 live instance, max 1 demo per symbol
- ShadowRunner available for signal-only testing

**No gaps identified.**

### Order Management — PRODUCTION READY

- TP/SL at creation time or via amendment
- Full RR-based entry with SL verification and emergency close
- WebSocket execution callbacks + REST fallback
- Idempotency tracking (10K cap OrderedDict)
- Split TP via conditional stop orders
- Stale order detection

**Minor gap:** No explicit partial fill management (adjusting TP/SL on partial quantities).

### Safety & Risk — PRODUCTION READY (Strongest Area)

Multi-layered defense:
- **PanicState**: Global thread-safe singleton, blocks ALL trading, cannot be accidentally cleared
- **SafetyChecks**: Fail-closed, runs before every signal (daily loss, min balance, max exposure)
- **DailyLossTracker**: Thread-safe, auto-resets at midnight, seeds from exchange on restart
- **RiskManager**: 7 independent checks (global risk, funding rate, daily loss, min balance, max position, max exposure, per-trade risk)
- **Price Deviation Guard**: Rejects orders >5% from mark price (fat finger protection)
- **DCP**: Auto-activates on disconnect in live mode
- **Cross-process tracking**: PID files at `~/.trade/instances/`

**Minor gaps:** No external watchdog/process supervisor. No dead-man's switch beyond DCP.

### Configuration — FUNCTIONAL

- API keys via environment variables (strict, no fallbacks)
- Separate demo/live credential sets
- Notifications: Telegram + Discord (NoopAdapter fallback)
- `defaults.yml`: conservative defaults (5.5bps taker, 1x leverage, 1% per trade, 20% max DD)

**Why not Production Ready:**
- No `.env` file loading
- No `config validate` command
- No encrypted credential storage
- No configuration documentation

---

## Part 4: Key Findings

### Redundancies

1. **`backtest run --play X`** vs **`play run --play X --mode backtest`** — same code path, two entry points
2. **`backtest audit-incremental-parity`** vs **`test parity`** — same concept, slightly different implementations
3. **`validate quick` G3** runs the same parity audit as **`backtest audit-incremental-parity`**
4. Interactive forge menu duplicates CLI backtest audit subcommands

### Scripts That Should Be CLI Commands

| Script | Proposed CLI Command |
|--------|---------------------|
| `run_full_suite.py` | `validate suite --synthetic` |
| `run_real_verification.py` | `validate suite --real` |
| `verify_trade_math.py` | `validate math --play X` |
| `test_demo_readiness.py` | `validate demo-ready` |
| `test_engine_ws.py` | `play test-ws` |

### Naming Inconsistencies

- `audit-*` vs `verify-*` vs `*-parity` — no consistent pattern for verification commands
- `backtest play-normalize` vs `backtest play-normalize-batch` — `play-` prefix inconsistent
- `--smoke` as global flag has different semantics than `backtest run --smoke`

### Missing Commands

- No `data` top-level subcommand (non-interactive data ops)
- No `order` top-level subcommand
- No `play new --template` scaffolding
- No `play results --run-id X` viewer
- No `play compare --run-a X --run-b Y`
- No `config validate` command
- No `forge` top-level subcommand (interactive only)

### Well-Designed Patterns

- All commands support `--json` output for scripting
- Clean tool layer separation (CLI → tools → engine)
- Gate-based validation tiers
- `play run --mode` as unified entry (backtest/demo/live/shadow)
- Live requires double confirmation + auto pre-live validation
- EngineManager lifecycle (start/stop/pause/resume/watch/logs)
- ToolRegistry for AI agent integration

---

## Part 5: Recommendations

### The Core Insight

`play` should be the primary command, with `--mode` as the escalation axis:

```bash
trade_cli.py play run --play X --mode backtest      # Already works
trade_cli.py play run --play X --mode demo           # Already works
trade_cli.py play run --play X --mode live --confirm # Already works
```

This is already the right pattern. The work is consolidation and gap-filling.

### Phase 1: Consolidate & Clean (Low effort, high clarity)

- Deprecate `backtest run` in favor of `play run --mode backtest`
- Move audit commands under `validate` (they're validation, not backtesting)
- Promote scripts to CLI: `validate suite`, `validate math`, `validate demo-ready`
- Add `play new --template` for scaffolding
- Add `data sync --play X` and `data status --play X` as non-interactive commands

### Phase 2: Smooth the Pipeline (Medium effort, high impact)

- Add `play results --run-id X` to view past backtest results
- Add `play compare --run-a X --run-b Y` for parameter sweeps
- Auto-data-sync in demo/live startup (piggyback on existing preflight)
- Strengthen pre-live gate: check connectivity + balance + data freshness
- PnL summary on shutdown

### Phase 3: Production Hardening (Higher effort, for unattended live)

- Crash recovery: persist/restore incremental indicator state
- Client-side rate limiter for reconnection storms
- Health escalation: N missed candles → auto-panic
- Watchdog/supervisor integration (systemd unit file)
- Config validation command + env var documentation
- Partial fill management for limit orders

### Shortest Path to End-to-End Trading

The workflow **already works today**:
```bash
play run --play X --mode backtest    # Test strategy
play run --play X --mode demo        # Paper trade
play run --play X --mode live --confirm  # Go live
```

**Biggest friction points** (quick wins):
1. Wire `data sync --play X` as non-interactive command (tool already exists)
2. Wire `test_demo_readiness.py` into `validate demo-ready`
3. Add PnL summary to runner shutdown
4. Strengthen pre-live gate with connectivity + balance + data freshness checks
5. Auto-data-sync on demo/live startup

---

## Priority Gap Summary

### Critical (blocks production use)
1. No incremental state recovery on crash (indicators/structures re-warm)
2. Pre-live gate shallow (no connectivity, balance, or data freshness checks)
3. No auto-data-sync for live/demo startup

### High (degrades user experience)
4. No backtest result viewer
5. No play template/scaffolding
6. No PnL reporting on shutdown
7. Redundant command paths create confusion

### Medium (nice to have)
8. No backtest comparison tool
9. No equity curve visualization
10. No `data status --play X`
11. No dry-run / paper-replay mode
12. No client-side rate limiter
13. No external watchdog integration
