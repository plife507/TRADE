# TRADE Architecture

## System Summary

TRADE is a Python 3.12+ trading bot for Bybit USDT linear perpetuals. It uses a **unified PlayEngine** that runs identically in backtest, demo, and live modes. Strategy logic is defined in YAML-based Plays and evaluated via a custom DSL. All indicators are incremental O(1), all data flows through 1m candles, and determinism is ensured via hash tracing.

**Code**: ~150 source files across 13 domains.
**Validation**: 17 gates (G1–G17), 170 synthetic plays, 60 real-data plays.
**Status**: Backtest engine production-ready. Live trading skeleton exists, pre-deployment blockers tracked in `docs/TODO.md`.

---

## Architecture Diagram

```
+------------------------------------------------------------------+
|                         TRADE SYSTEM                              |
+------------------------------------------------------------------+
|                                                                    |
|  +------------------+    +------------------+    +---------------+ |
|  |   CLI / Tools    |    |   Forge / Audit  |    |    Config     | |
|  | trade_cli.py     |    | synthetic_data   |    | defaults.yml  | |
|  | validate.py      |    | parity_audit     |    | constants.py  | |
|  | order_tools.py   |    | coverage check   |    | config.py     | |
|  +--------+---------+    +--------+---------+    +-------+-------+ |
|           |                       |                      |         |
|           v                       v                      v         |
|  +------------------------------------------------------------------+
|  |                      ENGINE (PlayEngine)                         |
|  |  process_bar() -> SubLoop(1m) -> DSL eval -> Signal -> Execute  |
|  +----------+----------------------+-------------------+-----------+
|             |                      |                   |            |
|    +--------v--------+    +--------v--------+  +-------v--------+  |
|    | Backtest Infra  |    |   DSL / Play    |  | Indicators /   |  |
|    | runner.py       |    | dsl_parser.py   |  | Structures     |  |
|    | engine_factory  |    | condition_ops   |  | 44 indicators  |  |
|    | metrics.py      |    | play.py         |  | 7 detectors    |  |
|    | preflight.py    |    | resolve.py      |  | feed_store.py  |  |
|    | feed_store.py   |    +-----------------+  +----------------+  |
|    +-----------------+                                              |
|             |                                                       |
|    +--------v--------+    +-----------------+                       |
|    |   Sim Exchange  |    | Data / Exchange |                       |
|    | exchange.py     |    | DuckDB store    |                       |
|    | ledger.py       |    | realtime_state  |                       |
|    | liquidation     |    | safety.py       |                       |
|    | execution       |    | exchange_mgr    |                       |
|    | funding         |    | bybit_client    |                       |
|    +-----------------+    +-----------------+                       |
|                                                                     |
+---------------------------------------------------------------------+
```

---

## Core Pipelines

### Backtest Pipeline

```
Play YAML → load_play() → Play object
  → run_backtest_with_gates(config)
    Phase 1:  Setup synthetic data (if validation block)
    Phase 2:  Resolve window (DB coverage or CLI args)
    Phase 3:  Validate symbol universe
    Phase 4:  Compute play_hash, input_hash, create artifact folder
    Phase 5:  Init RunLogger
    Phase 6:  Preflight gate (data availability, gaps, alignment)
    Phase 7:  Indicator requirements gate
    Phase 8:  Compute warmup (indicators + structures)
    Phase 9:  create_engine_from_play() → run_engine_with_play()
              └→ for bar in range(warmup_end, total_bars):
                   engine.process_bar(bar_index)
                     → SubLoop: 1m bars within exec bar
                     → DSL eval: entry/exit rules
                     → SimExchange: fills, TP/SL, liquidation
                     → Equity tracking (balance, drawdown, MAE/MFE)
    Phase 10: Write trades.parquet, equity.parquet
    Phase 11: Compute results (Sharpe, CAGR, etc.)
    Phase 12: Pipeline signature
    Phase 13: Update manifest
    Phase 14: Artifact validation gate
  → RunnerResult (trades_hash, equity_hash, run_hash)
```

### Live Pipeline

```
Bybit WebSocket
  → Ticker (last_price, mark_price, funding_rate)
  → Kline (OHLCV, multiple TFs)
  → Position (sync, PnL)
  → Execution (fill confirmations)
  ↓
RealtimeState (thread-safe singleton)
  → Staleness checks, bar buffers, connection status
  ↓
LiveRunner (async event loop)
  → _on_kline_update → filter by play TFs → enqueue
  → _process_candle:
      if exec_tf: engine.process_bar() → SubLoop → Signal → LiveAdapter
      else: update indicators/structures only
  → Position sync gate (blocks until sync OK)
  → Panic check (halt all trading if triggered)
  ↓
LiveAdapter → ExchangeManager → Bybit REST API
  → market_buy/sell (reduce_only for closes)
  → set_leverage, DCP activation
```

### Signal Evaluation

```
Play YAML actions → PARSE (dsl_parser.py) → Block/Case/AllExpr tree
  → COMPILE (strategy_blocks.py) → stored in Play.actions
  → EVALUATE (per bar):
      eval_expr(case.when, snapshot)
        → resolve_ref(FeatureRef, snapshot) → indicator/structure values
        → dispatch_operator(op, lhs, rhs) → True/False
        → AllExpr/AnyExpr → combined result
      → Intent("entry_long") → PlaySignalEvaluator → Signal
      → ExchangeAdapter.submit_order()
```

---

## Design Principles

1. **Unified Engine** — PlayEngine is mode-agnostic. Adapters inject mode-specific behavior (BacktestAdapter, LiveAdapter).
2. **1m Mandatory** — Every run pulls 1m candles for fill simulation, TP/SL evaluation, and signal subloop.
3. **Closed-Candle Only** — All computations happen on closed bars, never on ticks.
4. **Fail-Closed Safety** — Live guards block trading when data is unavailable (staleness, position sync, DCP).
5. **Hash Tracing** — play_hash → input_hash → trades_hash → equity_hash → run_hash for full reproducibility.
6. **YAML-Driven** — All strategy config in Play YAML, no hardcoded logic.
7. **UTC-Naive Timestamps** — All internal datetimes are UTC-naive, enforced by G17 (483 checks).
8. **Incremental O(1)** — All 44 indicators update in constant time per bar.
9. **Deterministic** — `sorted(set)` everywhere, no PYTHONHASHSEED dependency.

---

## Module Inventory

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

## What's Built (Current State)

### Complete & Production-Ready

- **PlayEngine** — unified backtest/demo/live, adapter pattern, 16-phase gated runner
- **44 Indicators** — all incremental O(1), registry-based, warmup-aware
- **7 Structure Detectors** — swing, trend, zone, fib, derived_zone, rolling_window, market_structure
- **Play DSL** — frozen 2026-01-08, 33+ patterns, full operator set
- **Simulated Exchange** — fills, ledger, liquidation, funding, tiered margins
- **CLI** — 64 handlers, 10 subcommand groups, JSON output, headless mode
- **Validation** — 17 gates (G1–G17), 170 synthetic + 60 real-data plays
- **structlog** — JSON logging, context binding, rotating files (100MB × 7)
- **Timestamp safety** — UTC-naive enforced, G17 gate (483 checks, 22 categories)
- **Hash tracing** — deterministic end-to-end (play → input → trades → equity → run)
- **Synthetic data** — 34 patterns, deterministic seeding, multi-TF support

### Exists But Pre-Deployment

- **LiveRunner** — async event loop, WebSocket integration, position sync
- **ExchangeManager** — Bybit REST client, order/position management
- **Safety guards** — DCP, staleness detection, panic halt, price deviation check
- **Dashboard** — Rich-based live display, tiered refresh rates

---

## Forward Roadmap

### Near-Term (Backtest Quality)

| Item | Description | Design Doc |
|------|-------------|------------|
| **T1: Warmup Parity** | Validate `is_ready()` matches registry warmup formulas | — |
| **T2: Structure Rethink** | Fix trend/MS timing mismatch, CHoCH semantics, PivotRingBuffer | `brainstorm/STRUCTURE_TRADING_SYSTEM.md` |

### Mid-Term (Live Readiness + Strategy Factory)

| Item | Description | Design Doc |
|------|-------------|------------|
| **T3–T6: Pre-Deployment** | REST warmup fallback, WS reconnect, panic_close ordering, demo validation | `TODO.md` |
| **Strategy Factory** | Mass generation → backtest → live sim → promotion pipeline | `design/strategy_factory/` (5 docs) |
| **Agent CLI Gaps** | 18 tool functions lack CLI flags (order, data, market, position) | `brainstorm/CLI_AGENT_AUTONOMY.md` |
| **Database Evolution** | DuckDB write-lock contention → Parquet+Polars or PostgreSQL | `DATABASE_ALTERNATIVES_REVIEW.md` |

### Long-Term (Scale & Intelligence)

| Item | Description | Design Doc |
|------|-------------|------------|
| **Sub-Accounts** | Per-play Bybit sub-accounts for capital isolation | `brainstorm/BYBIT_SUB_ACCOUNTS.md` |
| **Multi-Exchange** | Hyperliquid compatibility (2–3 week effort, engine already agnostic) | `brainstorm/HYPERLIQUID_COMPATIBILITY.md` |
| **Block Layer** | Typed blocks (filter/entry/exit/invalidation) for DSL composition | `brainstorm/TRADING_DSL_BLOCKS.md` |
| **Sentiment Tracker** | 3-tier regime classification (price-derived → exchange → external) | `brainstorm/MARKET_SENTIMENT_TRACKER.md` |
| **Genetic Evolution** | Ray-based parameter optimization, population lifecycle | `brainstorm/SYSTEM_VISION.md` |
| **LLM Translation** | Knowledge Store → Agent → Play generation | `brainstorm/SYSTEM_VISION.md` |

### Progression Path

```
CURRENT                    MID-TERM                     LONG-TERM
─────────                  ────────                     ─────────
T1 warmup parity     →     Strategy Factory        →    Genetic evolution
T2 structure rethink  →     Live sim engine          →    LLM play generation
                      →     Demo validation (T3-T6)  →    Multi-exchange
                      →     Agent CLI completion      →    Sentiment & regime
                      →     Database evolution        →    Sub-account portfolio
```

---

## Design Document Index

| Document | Location | Status |
|----------|----------|--------|
| **Strategy Factory** | `docs/design/strategy_factory/` | Active design (5 docs) |
| **Structure Trading System** | `docs/brainstorm/STRUCTURE_TRADING_SYSTEM.md` | Design for T2 |
| **Development Roadmap** | `docs/brainstorm/DEVELOPMENT_ROADMAP.md` | 7-phase roadmap |
| **System Vision** | `docs/brainstorm/SYSTEM_VISION.md` | End-to-end pipeline |
| **Bybit Sub-Accounts** | `docs/brainstorm/BYBIT_SUB_ACCOUNTS.md` | Multi-strategy arch |
| **Hyperliquid Compatibility** | `docs/brainstorm/HYPERLIQUID_COMPATIBILITY.md` | Multi-exchange analysis |
| **Market Sentiment** | `docs/brainstorm/MARKET_SENTIMENT_TRACKER.md` | Regime classification |
| **Trading DSL Blocks** | `docs/brainstorm/TRADING_DSL_BLOCKS.md` | Block layer design |
| **Parallel Backtesting** | `docs/brainstorm/PARALLEL_BACKTESTING.md` | DuckDB concurrency patterns |
| **CLI Agent Autonomy** | `docs/brainstorm/CLI_AGENT_AUTONOMY.md` | Agent CLI gaps |
| **Agent Readiness** | `docs/AGENT_READINESS_EVALUATION.md` | Autonomy scorecard |
| **Database Alternatives** | `docs/DATABASE_ALTERNATIVES_REVIEW.md` | DuckDB replacement |
| **Structure Detection Audit** | `docs/STRUCTURE_DETECTION_AUDIT.md` | T2 findings |
| **State & Memory Review** | `docs/STATE_MEMORY_REVIEW.md` | Live stability recs |
| **Unified Trade Structure** | `docs/UNIFIED_TRADE_STRUCTURE_REVIEW.md` | Sub-accounts eval |
| **Codebase Review** | `docs/CODEBASE_REVIEW_2026_02_21.md` | Latest full audit |
| **Findings Summary** | `docs/architecture/FINDINGS_SUMMARY.md` | 120-finding scorecard |
| **Play DSL Reference** | `docs/PLAY_DSL_REFERENCE.md` | DSL truth (frozen) |
| **Synthetic Data Reference** | `docs/SYNTHETIC_DATA_REFERENCE.md` | 34 data patterns |
| **Validation Best Practices** | `docs/VALIDATION_BEST_PRACTICES.md` | Validation guide |
| **CLI Quick Reference** | `docs/CLI_QUICK_REFERENCE.md` | CLI patterns |
| **CLI Data Guide** | `docs/CLI_DATA_GUIDE.md` | Data flow guide |
