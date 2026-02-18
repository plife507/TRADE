# TRADE Architecture Overview

## System Summary

TRADE is a Python-based trading bot for Bybit USDT linear perpetuals. It uses a unified PlayEngine that runs identically in backtest, demo, and live modes. Strategy logic is defined in YAML-based Plays and evaluated via a custom DSL. All indicators are incremental O(1), all data flows through 1m candles, and determinism is ensured via hash tracing.

---

## Diagram 1: Overall System Architecture

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

## Diagram 2: Backtest Pipeline Flow

```
  Play YAML file (plays/V_CORE_001.yml)
    |
    v
  load_play(play_id)
    |
    v
  Play object (symbol, timeframes, features, actions, risk)
    |
    v
  run_backtest_with_gates(config)
    |
    +-- Phase 1: Setup synthetic data (if validation: block in YAML)
    +-- Phase 2: Resolve window (from DB coverage or CLI args)
    +-- Phase 3: Validate symbol universe
    +-- Phase 4: Compute play_hash, input_hash, create artifact folder
    +-- Phase 5: Initialize RunLogger
    +-- Phase 6: Preflight gate (data availability, gaps, alignment)
    +-- Phase 7: Indicator requirements gate (features vs rules)
    +-- Phase 8: Compute warmup (from indicators/structures)
    |
    +-- Phase 9: create_engine_from_play()
    |     |
    |     +-> engine_data_prep: load DuckDB data for all TFs
    |     +-> indicator_vendor: precompute indicator arrays
    |     +-> FeedStore: build immutable array store
    |     +-> SimulatedExchange: init with risk profile
    |     +-> PlayEngine: wire adapter, data provider, state store
    |     |
    |     v
    |   run_engine_with_play()
    |     |
    |     v
    |   for bar in range(warmup_end, total_bars):
    |     engine.process_bar(bar_index)
    |       +-> SubLoop: iterate 1m bars within exec bar
    |       +-> DSL eval: evaluate entry/exit rules
    |       +-> Signal: generate trading intent
    |       +-> SimExchange: fill orders, check TP/SL, liquidation
    |       +-> Equity: track balance, drawdown, MAE/MFE
    |
    +-- Phase 10: Write trades.parquet, equity.parquet
    +-- Phase 11: Compute results summary (Sharpe, CAGR, etc.)
    +-- Phase 12: Pipeline signature
    +-- Phase 13: Update manifest
    +-- Phase 14: Artifact validation gate
    |
    v
  RunnerResult
    +-> trades_hash, equity_hash, run_hash (determinism)
    +-> result.json (summary)
    +-> backtests/<category>/<play_id>/<hash>/
```

---

## Diagram 3: Live Pipeline Flow

```
  Bybit WebSocket
    |
    +-----> Ticker (last_price, mark_price, funding_rate)
    +-----> Kline (candle OHLCV, multiple TFs)
    +-----> Position (sync, PnL updates)
    +-----> Execution (fill confirmations)
    |
    v
  RealtimeState (thread-safe singleton)
    |
    +-> Staleness checks (is_ticker_stale, is_kline_stale)
    +-> Bar buffers (per-TF deque of BarRecord)
    +-> Connection status tracking
    |
    v
  LiveRunner (async event loop)
    |
    +-- _on_kline_update(candle, timeframe)
    |     +-> Filter by _play_timeframes set
    |     +-> Enqueue (candle, tf) to _candle_queue
    |
    +-- _process_candle(candle, timeframe)
    |     +-> data_provider.on_candle_close(candle, tf)
    |     +-> If tf == exec_tf:
    |     |     +-> engine.process_bar(bar_index)
    |     |     +-> SubLoop: 1m signal evaluation
    |     |     +-> If signal: execute via LiveAdapter
    |     +-> Else:
    |           +-> Update indicators/structures only (no signal eval)
    |
    +-- Position sync gate (_position_sync_ok)
    |     +-> Blocks signal execution until sync completes
    |     +-> Periodic reconciliation (every 5 min)
    |
    +-- Panic check (check_panic_and_halt)
    |     +-> If triggered: halt all trading
    |
    v
  LiveAdapter --> ExchangeManager --> Bybit REST API
    +-> market_buy/sell (with reduce_only for closes)
    +-> set_leverage, amend_order, cancel_order
    +-> DCP (Disconnect Cancel Protection)
```

---

## Diagram 4: Signal Evaluation Flow

```
  Play YAML actions:
    - id: entry
      cases:
        - when:
            all:
              - ["ema_9", "cross_above", "ema_21"]
              - ["rsi_14", "<", 70]
          emit:
            - action: entry_long

    |
    v
  PARSE (dsl_parser.py):
    parse_blocks(yaml) -> list[Block]
      Block(id="entry")
        Case(when=AllExpr(...), emit=[Intent("entry_long")])
          AllExpr(children=[
            Cond(lhs=FeatureRef("ema_9"), op="cross_above", rhs=FeatureRef("ema_21")),
            Cond(lhs=FeatureRef("rsi_14"), op="<", rhs=ScalarValue(70)),
          ])

    |
    v
  COMPILE (strategy_blocks.py):
    Blocks stored in Play.actions

    |
    v
  EVALUATE (per bar, in engine):
    eval_expr(block.case.when, snapshot)
      |
      +-> eval_cond(Cond, snapshot)
      |     +-> resolve_ref(FeatureRef("ema_9"), snapshot) -> RefValue(45.2)
      |     +-> resolve_ref(FeatureRef("ema_21"), snapshot) -> RefValue(44.8)
      |     +-> eval_crossover(prev_lhs<=prev_rhs AND curr_lhs>curr_rhs)
      |     +-> EvalResult(passed=True)
      |
      +-> eval_cond(Cond, snapshot)
      |     +-> resolve_ref(FeatureRef("rsi_14"), snapshot) -> RefValue(55.3)
      |     +-> dispatch_operator("<", 55.3, 70) -> True
      |
      +-> AllExpr: all children True -> True
      |
      v
    Intent("entry_long")
      |
      v
  PlaySignalEvaluator -> Signal(side="long", size_usdt=...)
      |
      v
  ExchangeAdapter.submit_order()
    +-> Backtest: SimulatedExchange.submit_order()
    +-> Live: ExchangeManager.market_buy_with_tpsl()
```

---

## Key Design Principles

1. **Unified Engine**: PlayEngine is mode-agnostic. Adapters inject mode-specific behavior.
2. **1m Mandatory**: Every run pulls 1m candles for fill sim, TP/SL eval, and signal subloop.
3. **Closed-Candle Only**: All computations happen on closed bars, never on ticks.
4. **Fail-Closed Safety**: Live guards block trading when data is unavailable.
5. **Hash Tracing**: play_hash -> trades_hash -> equity_hash -> run_hash for reproducibility.
6. **YAML-Driven**: All strategy config in Play YAML, no hardcoded logic.
7. **TODO-Driven Development**: Every change maps to docs/TODO.md.

---

## Module Inventory

| Domain | Path | Files | Purpose |
|--------|------|-------|---------|
| Engine | src/engine/ | ~15 | PlayEngine, SubLoop, adapters, sizing |
| Sim | src/backtest/sim/ | ~12 | Exchange, ledger, liquidation, fills |
| Backtest | src/backtest/ | ~25 | Runner, factory, metrics, preflight |
| DSL/Play | src/backtest/rules/, play/ | ~15 | Parser, evaluator, strategy blocks |
| Indicators | src/indicators/ | ~10 | 44 incremental indicators |
| Structures | src/structures/ | ~10 | 7 structure detectors |
| Data | src/data/ | ~8 | DuckDB, RealtimeState, WebSocket |
| Exchange | src/core/ | ~12 | Safety, positions, orders, risk |
| CLI | src/cli/, trade_cli.py | ~8 | Validation, backtest, debug commands |
| Tools | src/tools/ | ~8 | Agent/orchestrator API |
| Forge | src/forge/ | ~10 | Synthetic data, audits, coverage |
| Config | src/config/ | ~4 | defaults.yml, constants, config |
| Utils | src/utils/ | ~5 | Logger, debug, time helpers |
