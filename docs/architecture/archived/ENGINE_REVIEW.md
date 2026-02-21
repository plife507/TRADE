# Engine Domain Review

**Reviewer:** engine-reviewer
**Date:** 2026-02-18
**Scope:** src/engine/ -- PlayEngine, SubLoopEvaluator, LiveRunner, live/backtest adapters, factory, interfaces

> **STATUS (2026-02-18):** All findings resolved. 6 fixed, 5 not-a-bug, 1 deferred (ENG-BUG-015 optimization), 3 OK.
> See `FINDINGS_SUMMARY.md` for current status of each finding.

---

## Module Overview

The engine domain implements a unified PlayEngine that runs identically for backtest, demo, live, and shadow modes. Mode-specific behaviour is fully isolated in adapter classes injected at construction time. The key protocol types are in interfaces.py; two runners (BacktestRunner, LiveRunner) drive the engine from outside.

| File | Role |
|---|---|
| play_engine.py | Core bar loop, rule evaluation, signal execution |
| signal/subloop.py | 1m bar TP/SL / signal evaluation sub-loop |
| runners/live_runner.py | WebSocket-driven async runner |
| runners/backtest_runner.py | Historical bar-by-bar runner |
| adapters/live.py | LiveDataProvider, LiveExchange, LiveIndicatorCache |
| adapters/backtest.py | BacktestDataProvider, BacktestExchange, ShadowExchange |
| interfaces.py | DataProvider, ExchangeAdapter, StateStore protocols |
| factory.py | PlayEngineFactory, create_backtest_engine() |

---

## File-by-File Findings

### src/engine/play_engine.py

#### TP/SL Evaluation Order (CRITICAL QUESTION)

**Verdict: CORRECT in backtest. NO ENGINE-LEVEL ISSUE in live (exchange native).**

In backtest, the order is enforced by BacktestRunner:

    bar N: BacktestRunner._process_bar_fills()  <- TP/SL evaluated BEFORE process_bar()
    bar N: BacktestRunner._engine.process_bar() <- signal evaluation runs AFTER TP/SL fills

The play_engine.py:process_bar() step at line 436 (self.exchange.step(candle)) is a no-op for BacktestExchange -- fills are processed by the runner before process_bar is called. This is correct per the CLAUDE.md rule: TP/SL orders fire BEFORE signal-based closes.

In live, the exchange handles TP/SL natively via Bybit OCO orders; no engine-level ordering needed.

**BUG-001 (LOW): Hardcoded bar_index == 100 debug sentinel**
- File: play_engine.py:427
- In live mode bar_index is always -1, so this condition never fires live. In backtest it fires at exactly bar 100, which may not correspond to warmup completion. Belongs to the now-fixed GAP-1 but was not cleaned up.
- Severity: LOW (cosmetic / misleading debug output)

**BUG-002 (MEDIUM): exchange.step() double-step latent risk**
- File: play_engine.py:436
- BacktestRunner calls _process_bar_fills() first (TP/SL), then process_bar(). Inside process_bar(), step 3 calls self.exchange.step(candle) again. BacktestExchange.step() is a no-op, so this is safe today. If it is ever made non-trivial, double processing will silently corrupt fills. The no-op contract is not enforced anywhere (no assert/NotImplementedError).
- Severity: MEDIUM (latent regression risk)

**BUG-003 (LOW): Duplicate max drawdown check in process_bar and BacktestRunner**
- Files: play_engine.py:453-464 and backtest_runner.py:413-428
- Both independently check max_drawdown_pct. Position is force-closed correctly either way, but the duplicate check wastes a get_equity() call every bar.
- Severity: LOW

**BUG-004 (MEDIUM): SizingModel.update_equity() uses potentially stale equity on WS failure**
- File: play_engine.py:397
- Called unconditionally for non-backtest modes. On WebSocket failure, get_equity() may return the stale initial_equity default. No guard equivalent to the _equity_initialized check in LiveRunner._check_max_drawdown().
- Severity: MEDIUM (sizing error on WS gap)

**BUG-005 (LOW): create_backtest_engine() directly mutates private engine attributes post-construction**
- File: factory.py:422-435
- engine._high_tf_feed, engine._quote_feed, etc. are assigned directly after __init__. Bypasses any initialization guards. Proper fix is constructor injection.
- Severity: LOW (architectural debt, works today)

---

### src/engine/signal/subloop.py

#### Off-by-one Analysis

**Verdict: range is correct (inclusive end at line 220). Clamping has a silent truncation issue.**

**BUG-006 (MEDIUM): end_1m clamping silently truncates last 1m bars of exec candle**
- File: subloop.py:196-197
- start_1m = min(start_1m, max_valid_idx) and end_1m = min(end_1m, max_valid_idx)
- If the 1m quote feed is slightly behind (e.g., right after market open or a short 1m gap), the last few 1m ticks of the current exec bar are silently skipped. A signal that would have fired near exec-close is missed. No warning is emitted when end_1m is clamped.
- Severity: MEDIUM (missed signals near data edge)

**BUG-007 (LOW): should_skip_entry() evaluated AFTER build_snapshot_1m() every tick**
- File: subloop.py:237
- Snapshot is built unconditionally, then discarded if should_skip_entry() is true. Reverse the check order for performance.
- Severity: LOW (performance, not correctness)

**BUG-008 (LOW): Fallback warning fires at most once per SubLoopEvaluator lifetime**
- File: subloop.py:201-206, 276-282
- _fallback_warned suppresses all subsequent warnings. If 1m data gaps intermittently, later gaps are silent.
- Severity: LOW (observability)

---

### src/engine/runners/live_runner.py

#### Can signals fire on stale data after WebSocket reconnect?

**Verdict: Mostly protected, but one HIGH gap remains.**

After reconnect, _sync_positions_on_startup() resets _position_sync_ok only on success. The WebSocket health check at line 808 provides a second gate. However:

**BUG-009 (HIGH): Stale queued candles processed immediately after reconnect with stale indicator state**
- File: live_runner.py:995-999
- _reconnect() flow: _disconnect() -> _connect() -> _sync_positions_on_startup() -> transition(RUNNING)
- After _connect() but before _sync_positions_on_startup() completes, the runner transitions to RUNNING. If candles were queued during reconnect (the queue is unbounded and not flushed), they are processed immediately after _position_sync_ok becomes True. At this point LiveDataProvider buffer has not been refreshed with the missed candles during downtime -- the signal fires against stale indicator state.
- Fix: Clear candle queue after reconnect; reload LiveDataProvider history before re-enabling signals.
- Severity: HIGH

**BUG-010 (MEDIUM): _seen_candles set NOT cleared on reconnect -- drops catch-up candles**
- File: live_runner.py:976-1004 (no self._seen_candles.clear() in _reconnect)
- After reconnect, candles re-delivered via WebSocket to cover the outage gap may be rejected as duplicates if their ts_open_epoch is still in the bounded dedup set.
- Severity: MEDIUM (missed candles during reconnect window)

**BUG-011 (LOW): LiveRunnerStats.duration_seconds uses naive datetime.now()**
- File: live_runner.py:89
- Internally consistent (started_at is also naive), but mixing with timezone-aware candle.ts_close in any future comparison would fail.
- Severity: LOW (future hazard)

**BUG-012 (LOW): Shadow mode triggers misleading safety checks log**
- File: live_runner.py:877 + live_runner.py:1016-1019
- _run_safety_checks() returns False for ShadowExchange (no _exchange_manager), emitting a spurious error log on every shadow signal. The signal is handled correctly via is_shadow in execute_signal().
- Severity: LOW (noise log, not functional regression)

---

### src/engine/adapters/live.py -- LiveDataProvider

#### GAP-1: Warmup hardcoded to 100 -- RESOLVED

Warmup is now computed dynamically via compute_warmup_requirements(play) at lines 637-639. GAP-1 is closed.

**BUG-013 (HIGH): ts_close set to ts_open for warmup candles loaded from DuckDB/REST**
- File: live.py:896-904
- candle = Candle(ts_open=bar_record.timestamp, ts_close=bar_record.timestamp, ...)
- ts_close is used by SubLoopEvaluator as exec_ts_close for 1m range lookup. For warmup bars this triggers the graceful fallback, but produces incorrect state timestamps in EngineState persistence. Structure detectors receive candles with zero-duration (ts_open == ts_close).
- Fix: Compute ts_close = ts_open + timedelta(minutes=tf_minutes(tf_str)) for each bar record.
- Severity: HIGH (incorrect data field; graceful but wrong)

**BUG-014 (MEDIUM): TF deduplication logic may cross-contaminate indicator caches for equal non-adjacent TFs**
- File: live.py:611-615, 834-839
- _med_tf_indicators is only created if med_tf != low_tf; _high_tf_indicators only if high_tf != med_tf. Consider low_tf=15m, med_tf=1h, high_tf=1h: _high_tf_indicators is None, so _exec_indicators for the high_tf role falls back to _low_tf_indicators (15m data). Any high_tf feature evaluation uses 15m indicator values.
- Severity: MEDIUM (wrong indicator values when non-adjacent TFs are equal)

**BUG-015 (MEDIUM): LiveIndicatorCache.update() uses np.append() -- O(n) per bar**
- File: live.py:265-277
- np.append() creates a new array on every call. With buffer_size=500 and 20 indicators, each bar allocates ~25 arrays of 500 floats (~100 KB). At 1m frequency this is ~100 MB/hour of allocation pressure causing GC pauses.
- Fix: Use pre-allocated ring buffers or collections.deque(maxlen=buffer_size).
- Severity: MEDIUM (memory pressure / GC thrash in production)

---

### src/engine/adapters/backtest.py

**BUG-016 (LOW): BacktestExchange.get_realized_pnl() accesses three levels of private attributes**
- File: backtest.py:452-454
- self._sim_exchange._ledger._initial_capital silently breaks if SimulatedExchange or Ledger is refactored. A public accessor should be exposed.
- Severity: LOW

**BUG-017 (LOW): BacktestExchange.step() no-op lacks interface contract enforcement**
- File: backtest.py:488-498
- No assert/raise makes the no-op contract explicit. A future test expecting fills from step() gets none silently.
- Severity: LOW

---

### src/engine/runners/backtest_runner.py

**BUG-018 (LOW): BacktestResult.metrics fallback has sign inconsistency for gross_loss**
- File: backtest_runner.py:191
- Fallback: gross_loss=abs(self.gross_loss). Primary computed_metrics path returns gross_loss directly (no abs). Sign is inconsistent between paths.
- Severity: LOW

**BUG-019 (LOW): Force-close at candle.close price introduces positive bias for drawdown stops**
- File: backtest_runner.py:686-691
- At max drawdown stop, position is closed at bar close rather than at the drawdown-detection price. For long positions this introduces a small positive bias.
- Severity: LOW

---

### src/engine/interfaces.py

**Clean.** Protocols are @runtime_checkable with full docstrings. ExchangeAdapter.step() docstring correctly notes it may be a no-op for live mode. Position dataclass uses size_usdt per project rules.

---

### src/engine/factory.py

**Clean overall.** Live safety checks use Config singleton (not raw env vars). _build_config_from_play() correctly raises ValueError for None config fields.

**BUG-020 (LOW): Shadow mode hardcoded to demo=True endpoint**
- File: factory.py:321
- Shadow mode always uses the demo WebSocket endpoint. Intentional but undocumented.
- Severity: LOW

---

## Cross-Module Dependencies

    LiveRunner
      -> PlayEngine
           -> LiveDataProvider (live.py)
           |    -> LiveIndicatorCache       [O(n) allocation BUG-015]
           |    -> TFIncrementalState       [swing/trend/zone structures]
           |    -> RealtimeState/Bootstrap  [WebSocket]
           -> LiveExchange (live.py)
           |    -> ExchangeManager/OrderExecutor/PositionManager
           -> SubLoopEvaluator (signal/subloop.py)
                -> FeedStore.get_1m_indices_for_exec()

    BacktestRunner
      -> PlayEngine
           -> BacktestDataProvider (backtest.py)
           |    -> FeedStore                [precomputed indicators, O(1)]
           -> BacktestExchange (backtest.py)
           |    -> SimulatedExchange        [TP/SL, fills, ledger]
           -> SubLoopEvaluator (signal/subloop.py)

Key data flow contracts:
1. BacktestRunner calls _process_bar_fills() BEFORE process_bar() -- TP/SL fires before signals (CORRECT)
2. LiveRunner delegates TP/SL to Bybit native OCO orders -- no engine-level ordering needed
3. SubLoopEvaluator is mode-agnostic; receives pre-resolved feeds from engine attributes

---

## ASCII Diagram

    +--------------------------------------------------------------+
    |                       RUNNER LAYER                           |
    |  BacktestRunner                    LiveRunner (async)        |
    |  -----------------                 --------------------      |
    |  1. _process_bar_fills()           1. WebSocket -> queue     |
    |     (TP/SL BEFORE signals)         2. _position_sync_ok?    |
    |  2. process_bar(idx)               3. is_websocket_healthy?  |
    |  3. execute_signal(signal)         4. process_bar(-1)        |
    |                                    5. execute_signal(sig)    |
    +-----------+----------------------------+--------------------+
                |                            |
                +------------+---------------+
                             |
                             v
    +--------------------------------------------------------------+
    |                     PLAY ENGINE                              |
    |  process_bar(idx)                                            |
    |  +- _update_high_tf_med_tf_indices()                         |
    |  +- _update_incremental_state()     <- structures            |
    |  +- _is_ready()                     <- warmup gate           |
    |  +- exchange.step()                 <- NO-OP in backtest     |
    |  +- max_drawdown check              <- duplicated (BUG-003)  |
    |  +- _evaluate_rules()               <- SubLoopEvaluator      |
    |       +- SubLoopEvaluator.evaluate()                         |
    |            +- 1m bar loop (start_1m..end_1m inclusive)       |
    |            |    +- build_snapshot_1m()                       |
    |            |    +- evaluate_signal(snapshot)                 |
    |            +- fallback (exec_tf close price)                 |
    +-------------------+------------------------------------------+
                        |
              +---------+---------+
              v                   v
    +------------------+  +----------------------+
    | BacktestDataProv |  |  LiveDataProvider    |
    | ---------------- |  | -------------------- |
    | FeedStore O(1)   |  | Rolling buffers      |
    | Precomputed inds |  | O(n) append BUG-015  |
    |                  |  | ts_close wrong BUG-13|
    +------------------+  +----------------------+
              |                   |
              v                   v
    +------------------+  +----------------------+
    | BacktestExchange |  |  LiveExchange        |
    | ---------------- |  | -------------------- |
    | SimulatedExchange|  | Bybit REST/WS        |
    | TP/SL via runner |  | Native OCO orders    |
    +------------------+  +----------------------+

---

## Summary Table

| ID      | Sev    | File                            | Line    | Issue |
|---------|--------|---------------------------------|---------|-------|
| BUG-001 | LOW    | play_engine.py                  | 427     | Hardcoded bar_index==100 debug sentinel |
| BUG-002 | MEDIUM | play_engine.py                  | 436     | exchange.step() double-step latent risk |
| BUG-003 | LOW    | play_engine.py / backtest_runner.py | 453/413 | Duplicate max drawdown check |
| BUG-004 | MEDIUM | play_engine.py                  | 397     | Sizing uses stale equity on WS failure |
| BUG-005 | LOW    | factory.py                      | 422     | Private attribute mutation post-construction |
| BUG-006 | MEDIUM | subloop.py                      | 196     | end_1m clamping silently truncates last 1m bars |
| BUG-007 | LOW    | subloop.py                      | 237     | should_skip_entry() checked after snapshot build |
| BUG-008 | LOW    | subloop.py                      | 201     | Fallback warning fires at most once per lifetime |
| BUG-009 | HIGH   | live_runner.py                  | 995     | Stale queued candles after reconnect on stale state |
| BUG-010 | MEDIUM | live_runner.py                  | 976     | _seen_candles not cleared on reconnect |
| BUG-011 | LOW    | live_runner.py                  | 89      | duration_seconds uses naive datetime.now() |
| BUG-012 | LOW    | live_runner.py                  | 877     | Shadow mode triggers misleading safety-checks log |
| BUG-013 | HIGH   | live.py                         | 900     | ts_close = ts_open for warmup candles (wrong) |
| BUG-014 | MEDIUM | live.py                         | 611     | TF dedup logic cross-contaminates indicator caches |
| BUG-015 | MEDIUM | live.py                         | 265     | np.append() O(n) per bar in LiveIndicatorCache |
| BUG-016 | LOW    | backtest.py                     | 452     | Private ledger access in get_realized_pnl() |
| BUG-017 | LOW    | backtest.py                     | 488     | step() no-op lacks contract enforcement |
| BUG-018 | LOW    | backtest_runner.py              | 191     | gross_loss sign inconsistency in metrics fallback |
| BUG-019 | LOW    | backtest_runner.py              | 686     | Force-close price bias for drawdown stops |
| BUG-020 | LOW    | factory.py                      | 321     | Shadow mode hardcoded to demo=True endpoint |

### Priority Actions

1. **BUG-009 (HIGH)**: Flush the candle queue after reconnect. Discard any queued candle older than the reconnect timestamp before re-enabling signals. Also call LiveDataProvider._sync_warmup_data() and _load_initial_bars() after reconnect to refresh the indicator buffer.

2. **BUG-013 (HIGH)**: In _load_tf_bars (live.py:896), compute ts_close = ts_open + timedelta(minutes=tf_minutes(tf_str)) for each warm-up bar. Do not set ts_close = ts_open.

3. **BUG-006 (MEDIUM)**: In SubLoopEvaluator.evaluate() (subloop.py:196), add a warning log when end_1m is clamped. Explicitly fall back to exec-close when the 1m feed does not cover the full exec bar.

4. **BUG-015 (MEDIUM)**: Replace np.append in LiveIndicatorCache.update() (live.py:265) with pre-allocated ring buffers or deque(maxlen=buffer_size) to eliminate O(n) allocation pressure at 1m frequency.

5. **BUG-010 (MEDIUM)**: Clear _seen_candles in _reconnect() (live_runner.py). Then replay the queue with duplicate suppression based on ts_open >= reconnect_ts.
