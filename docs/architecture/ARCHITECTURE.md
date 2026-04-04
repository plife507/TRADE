# TRADE Architecture

## The Goal

An **autonomous strategy factory** that transforms trading knowledge into live, profitable strategies.

Agents build plays from concepts, iterate backtests until profitable, prove them on a shadow exchange (always-on VPS), and promote winners to live trading on isolated Bybit sub-accounts. Market intelligence trains in the shadow environment, learning which plays work in which conditions. Humans interact through Web UI or CLI. Agents and humans collaborate to make USDT.

```
KNOWLEDGE ──> AGENT BUILDS PLAYS ──> BACKTEST (iterate until profitable)
                                           |
                                           v
                                    SHADOW EXCHANGE (VPS, extended run)
                                    + MARKET INTELLIGENCE (trains here)
                                           |
                                           v
                                    PROMOTE TO LIVE (Bybit sub-account)
                                           |
                                           v
                                    MONITOR + ADAPT (regime-aware rotation)
                                           |
                                    <------' (retire/re-evolve if underperforming)
```

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Strategy iteration | Param tuning first, structural mutation if needed | GE engine for params, LLM agent for rewrites |
| Autonomy model | Graduated — pause+alert first, auto-rotate as trust builds | System earns trust over time with real results |
| Shadow = training ground | Market intelligence trains in shadow, not separate | Learns regime-to-performance correlation from real paper data |
| Interfaces | Web UI + CLI (human) + CLI (agent) — equal citizens | All three access the same tools layer |
| Exchange | Bybit UTA 2.0: USDT + USDC linear perps (675 instruments), inverse deferred | InstrumentRegistry resolves any symbol |
| Hosting | Always-on Linux VPS for shadow + live | No downtime tolerance for extended runs |

---

## Module Architecture

```
+-----------------------------------------------------------------------+
|                         TRADE SYSTEM MODULES                           |
+-----------------------------------------------------------------------+
|                                                                        |
|  +--------------+     +-----------------+     +----------------+       |
|  | M1: KNOWLEDGE|---->| M2: PLAY FORGE  |---->| M3: BACKTEST   |       |
|  |    STORE     |     |                 |<----|    ENGINE       |       |
|  |              |     | Build + iterate |     |                |       |
|  | Concepts in  |     | GE param sweep  |     | Score + filter |       |
|  | Templates    |     | LLM rewrite     |     | Pass/fail gate |       |
|  +--------------+     +--------+--------+     +----------------+       |
|                                |                                       |
|                       +--------v----------------------------------+    |
|                       | M4: SHADOW EXCHANGE (The Training Ground) |    |
|                       |                                           |    |
|                       |  +-------------+  +-------------------+   |    |
|                       |  | Run plays   |  | M6: MARKET        |   |    |
|                       |  | (many,      |--|    INTELLIGENCE   |   |    |
|                       |  |  parallel,  |  |                   |   |    |
|                       |  |  extended)  |  | Learns regime     |   |    |
|                       |  |             |  | <-> performance   |   |    |
|                       |  | Track P&L   |  | Builds play       |   |    |
|                       |  | per play    |  | selection model   |   |    |
|                       |  +-------------+  +-------------------+   |    |
|                       |                                           |    |
|                       |  Graduates plays WITH context:            |    |
|                       |  "play X + trending BTC + low funding"    |    |
|                       +-------------------+-----------------------+    |
|                                           | promote                    |
|                                  +--------v--------+                   |
|                                  | M5/M8: UTA      |                   |
|                                  |  PORTFOLIO MGR  |                   |
|                                  |                 |                   |
|                                  | Sub-accounts    |<-- M6 advises    |
|                                  | PlayDeployer    |    (which play,  |
|                                  | 22 tools (API)  |     when to      |
|                                  | InstrumentReg   |     rotate)      |
|                                  +--------+--------+                   |
|                                           |                            |
|                                  +--------v--------+                   |
|                                  | M7: INTERFACES  |                   |
|                                  |                 |                   |
|                                  | Web UI          |                   |
|                                  | CLI (human)     |                   |
|                                  | CLI (agent)     |                   |
|                                  +-----------------+                   |
|                                                                        |
|  +----------------------------------------------------------------+   |
|  | M0: FOUNDATION (BUILT)                                         |   |
|  | PlayEngine, 44 indicators, 7 structures, DSL, SimExchange,    |   |
|  | CLI (50+ cmds), validation (17 gates), hash tracing,          |   |
|  | structlog, timestamps, synthetic data (34 patterns)            |   |
|  +----------------------------------------------------------------+   |
+------------------------------------------------------------------------+
```

---

## Module Definitions

### M0: Foundation (BUILT)

The engine, DSL, indicators, and infrastructure that everything else builds on.

| Component | Status | Detail |
|-----------|--------|--------|
| PlayEngine | Production-ready | Unified backtest/demo/live, adapter pattern, 16-phase gated runner |
| 44 Indicators | Production-ready | All incremental O(1), registry-based, warmup-aware |
| 7 Structure Detectors | Production-ready | Swing, trend, zone, fib, derived_zone, rolling_window, market_structure |
| Play DSL | Frozen (2026-01-08) | 33+ patterns, full operator set. See `PLAY_DSL_REFERENCE.md` |
| Simulated Exchange | Production-ready | Fills, ledger, liquidation, funding, tiered margins |
| CLI | 85% complete | 64 handlers, 11 subcommand groups, JSON output, headless mode |
| Validation | Production-ready | 17 gates (G1-G17), 170 synthetic + 60 real-data plays |
| Logging | Production-ready | structlog, JSON, context binding, rotating files (100MB x 7) |
| Timestamps | Enforced | UTC-naive everywhere, G17 gate (490 checks, 23 categories) |
| Hash Tracing | Production-ready | play -> input -> trades -> equity -> run |
| Synthetic Data | Production-ready | 34 patterns, deterministic seeding, multi-TF support |

### M1: Knowledge Store (NOT STARTED)

Ingests pre-processed trading knowledge and makes it available to Play Forge agents.

- **Input**: Markdown docs, structured notes, trading concepts (pre-formatted)
- **Output**: Tagged concepts, strategy templates, parameter ranges
- **Key capability**: Agent can query "what concepts exist for trending markets?"

### M2: Play Forge (PARTIALLY STARTED)

Agents build Play YAML files from concepts, iterating with the backtest engine until profitable.

- **Input**: Concepts from M1, backtest feedback from M3
- **Output**: Profitable Play YAML files ready for shadow
- **Iteration model**:
  - Phase 1: GE param sweeps (same strategy, different numbers)
  - Phase 2: LLM structural mutation (change logic, add/remove indicators)
- **Existing**: `forge-play` CLI skill, synthetic data forge
- **Needed**: Agent iteration loop, GE engine, fitness scoring, LLM rewrite capability

### M3: Backtest Engine (BUILT — needs polish)

Runs plays against historical data and scores results.

- **Input**: Play YAML + market data (DuckDB or synthetic)
- **Output**: Scored results (Sharpe, CAGR, drawdown, trade count, win rate)
- **Status**: Production-ready, minor polish needed (T1 warmup parity, T2 structure rethink)
- **Key for M2**: Must expose clear pass/fail criteria for agent iteration

### M4: Shadow Exchange — The Training Ground (SKELETON EXISTS)

Always-on paper trading on VPS. Runs proven plays in real market conditions. **Market Intelligence (M6) trains here.**

- **Input**: Backtest-proven plays from M2/M3
- **Output**: Extended paper-trade results + regime-performance correlation data
- **Capabilities**:
  - Run many plays in parallel, indefinitely (days/weeks/months)
  - Track P&L per play, per market condition
  - Feed performance data to M6 for training
  - Graduate plays WITH context ("this play + trending BTC + low funding")
- **Existing**: LiveRunner (async event loop), demo mode, WebSocket integration
- **Needed**: Multi-play orchestration, performance database, VPS deployment, M6 integration

### M5: Live Trade Manager (PARTIALLY BUILT)

Promotes shadow-proven plays to real money on isolated Bybit sub-accounts.

- **Input**: Shadow-graduated plays + M6 recommendations
- **Output**: Real trades, real USDT
- **Capabilities**:
  - Isolated sub-accounts per play (capital isolation)
  - Risk controls (max drawdown, daily loss, position limits)
  - Graduated autonomy: pause+alert first, auto-rotate as trust builds
  - Trust scoring (track record over time earns more autonomy)
- **Existing**: ExchangeManager, safety guards (DCP, staleness, panic, price deviation)
- **Needed**: Sub-account management, trust scoring system, promotion pipeline, auto-rotation

### M6: Market Intelligence (NOT STARTED — trains in M4)

Learns which plays work in which market conditions by observing shadow exchange results.

- **Input**: Shadow exchange play performance + market data (price, funding, OI, sentiment)
- **Output**: Regime classification, play recommendations, rotation signals
- **Lives inside M4** during training, **advises M5** during live trading
- **Capabilities**:
  - Regime detection (trending, ranging, volatile, quiet)
  - Play-to-regime correlation (statistical, builds over time)
  - Play selection for current conditions
  - Underperformance detection ("play X stopped working, rotate")
- **Graduated autonomy**: Suggests first (human approves), earns auto-rotation over time

### M7: Interfaces (CLI 85%, WEB NOT STARTED)

Three equal-citizen interfaces to the system.

- **CLI**: Headless subcommand dispatch with `--json` output on all commands. Complete.
- **Node.js UI**: Planned replacement for former interactive menus. Not started.
- **Web UI**: Dashboard, play management, charts, shadow monitoring. Not started.
- **All interfaces share**: `src/tools/` layer (canonical business logic, ToolResult envelope)

---

## Module Dependencies

```
M0 (done) --> M3 (polish T1/T2) --> M2 (forge + GE iteration loop)
                                         |
                                         v
                                    M4 (shadow on VPS) + M6 (trains here)
                                         |
                                         v
                                    M5 (live sub-accounts)
                                         |
                                    M7 (web UI) -- parallel with M4+
                                    M1 (knowledge store) -- parallel with M4+
```

**Critical path**: M3 polish -> M2 iteration loop -> M4 shadow -> M5 live

**Parallel work**: M1 and M7 can be built alongside M4/M5 without blocking.

---

## Design Principles

1. **Unified Engine** -- PlayEngine is mode-agnostic. Adapters inject mode-specific behavior (BacktestAdapter, LiveAdapter).
2. **1m Mandatory** -- Every run pulls 1m candles for fill simulation, TP/SL evaluation, and signal subloop.
3. **Closed-Candle Only** -- All computations happen on closed bars, never on ticks.
4. **Fail-Closed Safety** -- Live guards block trading when data is unavailable (staleness, position sync, DCP).
5. **Hash Tracing** -- play_hash -> input_hash -> trades_hash -> equity_hash -> run_hash for full reproducibility.
6. **YAML-Driven** -- All strategy config in Play YAML, no hardcoded logic.
7. **UTC-Naive Timestamps** -- All internal datetimes are UTC-naive, enforced by G17.
8. **Incremental O(1)** -- All 44 indicators update in constant time per bar.
9. **Deterministic** -- `sorted(set)` everywhere, no PYTHONHASHSEED dependency.
10. **Graduated Autonomy** -- System starts supervised, earns trust through track record.
11. **Shadow = Training Ground** -- Market intelligence learns from shadow, not from theory.

---

## Current Source Layout

| Domain | Path | Key Files | Purpose |
|--------|------|-----------|---------|
| Engine | `src/engine/` | PlayEngine, SubLoop, adapters, sizing, journal | Unified bar processing |
| Sim | `src/backtest/sim/` | exchange, ledger, liquidation, fills, funding | Simulated exchange |
| Backtest | `src/backtest/` | runner, factory, metrics, preflight, artifacts | Backtest infrastructure |
| DSL/Play | `src/backtest/rules/`, `src/play/` | parser, evaluator, strategy blocks, resolve | Strategy language |
| Indicators | `src/indicators/` | 44 incremental indicators | Technical analysis |
| Structures | `src/structures/` | 7 detectors (swing, trend, zone, fib, etc.) | Market structure |
| Data | `src/data/` | DuckDB store, historical sync | Historical data |
| Exchange | `src/core/` | safety, positions, orders, risk, realtime state | Live trading |
| CLI | `src/cli/`, `trade_cli.py` | validate, backtest, debug, play commands | User interface |
| Tools | `src/tools/` | 103 tool functions, 64 handlers | Agent/orchestrator API |
| Forge | `src/forge/` | synthetic data (34 patterns), audits, coverage | Testing infrastructure |
| Config | `src/config/` | defaults.yml, constants, config | System defaults |
| Utils | `src/utils/` | logger, debug, datetime_utils, hashes | Shared utilities |

---

## Core Pipelines

### Backtest Pipeline

```
Play YAML -> load_play() -> Play object
  -> run_backtest_with_gates(config)
    Phase 1:  Setup synthetic data (if validation block)
    Phase 2:  Resolve window (DB coverage or CLI args)
    Phase 3:  Validate symbol universe
    Phase 4:  Compute play_hash, input_hash, create artifact folder
    Phase 5:  Init RunLogger
    Phase 6:  Preflight gate (data availability, gaps, alignment)
    Phase 7:  Indicator requirements gate
    Phase 8:  Compute warmup (indicators + structures)
    Phase 9:  create_engine_from_play() -> run_engine_with_play()
              '-> for bar in range(warmup_end, total_bars):
                   engine.process_bar(bar_index)
                     -> SubLoop: 1m bars within exec bar
                     -> DSL eval: entry/exit rules
                     -> SimExchange: fills, TP/SL, liquidation
                     -> Equity tracking (balance, drawdown, MAE/MFE)
    Phase 10: Write trades.parquet, equity.parquet
    Phase 11: Compute results (Sharpe, CAGR, etc.)
    Phase 12: Pipeline signature
    Phase 13: Update manifest
    Phase 14: Artifact validation gate
  -> RunnerResult (trades_hash, equity_hash, run_hash)
```

### Live Pipeline

```
Bybit WebSocket
  -> Ticker (last_price, mark_price, funding_rate)
  -> Kline (OHLCV, multiple TFs)
  -> Position (sync, PnL)
  -> Execution (fill confirmations)
  |
RealtimeState (thread-safe singleton)
  -> Staleness checks, bar buffers, connection status
  |
LiveRunner (async event loop)
  -> _on_kline_update -> filter by play TFs -> enqueue
  -> _process_candle:
      if exec_tf: engine.process_bar() -> SubLoop -> Signal -> LiveAdapter
      else: update indicators/structures only
  -> Position sync gate (blocks until sync OK)
  -> Panic check (halt all trading if triggered)
  |
LiveAdapter -> ExchangeManager -> Bybit REST API
  -> market_buy/sell (reduce_only for closes)
  -> set_leverage, DCP activation
```

### Signal Evaluation

```
Play YAML actions -> PARSE (dsl_parser.py) -> Block/Case/AllExpr tree
  -> COMPILE (strategy_blocks.py) -> stored in Play.actions
  -> EVALUATE (per bar):
      eval_expr(case.when, snapshot)
        -> resolve_ref(FeatureRef, snapshot) -> indicator/structure values
        -> dispatch_operator(op, lhs, rhs) -> True/False
        -> AllExpr/AnyExpr -> combined result
      -> Intent("entry_long") -> PlaySignalEvaluator -> Signal
      -> ExchangeAdapter.submit_order()
```

---

## Reference Documents

| Document | Location | Purpose |
|----------|----------|---------|
| **Project TODO** | `docs/TODO.md` | Active work tracker |
| **Market Structure Features** | `docs/MARKET_STRUCTURE_FEATURES.md` | Implementation plan for new detectors (FVG, OB, etc.) |
| **Play DSL Reference** | `docs/PLAY_DSL_REFERENCE.md` | DSL truth (frozen 2026-01-08) |
| **Synthetic Data Reference** | `docs/SYNTHETIC_DATA_REFERENCE.md` | 34 data patterns |
| **Validation Best Practices** | `docs/VALIDATION_BEST_PRACTICES.md` | Validation guide |
| **CLI Quick Reference** | `docs/CLI_QUICK_REFERENCE.md` | CLI patterns |
| **CLI Data Guide** | `docs/CLI_DATA_GUIDE.md` | Data flow guide |
| **Agent Readiness** | `docs/AGENT_READINESS_EVALUATION.md` | Autonomy scorecard (88%) |
| **Structure Detection Audit** | `docs/STRUCTURE_DETECTION_AUDIT.md` | T2 findings |
