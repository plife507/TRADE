# Demo Trading Production Readiness Plan

**Date**: 2026-02-12
**Branch**: feature/unified-engine
**Status**: COMPLETE - All 6 gates passed, 28 bugs fixed, validation green

---

## Gate 1: Engine Creation & Safety Chain (CRITICAL) - DONE

| Bug | Fix | File | Status |
|-----|-----|------|--------|
| C5: Factory engine thrown away | Removed factory call for live/demo; manager is sole creator | `src/cli/subcommands.py` | FIXED |
| C7: Manager skips validation | Added `_validate_live_mode()` in `EngineManager.start()` for live | `src/engine/manager.py` | FIXED |
| C6: Validation checks "live" not "real" | Uses `config.trading.mode` instead of env var, accepts "real" | `src/engine/factory.py` | FIXED |
| C4: `_demo` flag unused | Assert coherence: `demo` must match `config.bybit.use_demo` | `src/engine/adapters/live.py` | FIXED |
| M9: Dead instance blocks new starts | Cleanup in `_run_instance` except: remove instance, update counts | `src/engine/manager.py` | FIXED |

---

## Gate 2: Warmup & Readiness (CRITICAL) - DONE

| Bug | Fix | File | Status |
|-----|-----|------|--------|
| C1: Hardcoded 100-bar warmup | Calls `compute_warmup_requirements(play)`, uses `max_warmup_bars` | `src/engine/adapters/live.py` | FIXED |
| C2: Structure warmup unchecked | Structure readiness check added to `_check_tf_warmup()` | `src/engine/adapters/live.py` | FIXED |
| H7: Buffer-relative bar_idx | Global `_global_bar_count` per TF, monotonic, survives trimming | `src/engine/adapters/live.py` | FIXED |
| M1: high_tf==med_tf wrong cache | Falls back to `_med_tf_indicators` instead of exec cache | `src/engine/adapters/live.py` | FIXED |
| M3: Missing `hl2` source | Added to both `_resolve_input_from_candle()` and `_arrays()` | `src/engine/adapters/live.py` | FIXED |

---

## Gate 3: Signal Evaluation in Live Context (CRITICAL) - DONE

| Bug | Fix | File | Status |
|-----|-----|------|--------|
| C3: `_build_snapshot_view_1m()` None | Added LiveDataProvider branch with full 1m snapshot | `src/engine/play_engine.py` | FIXED |
| C8: `submit_close()` ignores percent | Partial: reduce-only market order; Full: close_position | `src/engine/adapters/live.py` | FIXED |
| M4: `entries_disabled` always False | Wired to `get_panic_state().is_triggered` | `src/engine/adapters/live_state_adapter.py` | FIXED |
| M5: Window ops crash on `last_price` | Passes `quote_feed=exec_feed` as fallback in live snapshot | `src/engine/play_engine.py` | FIXED |

---

## Gate 4: Runner Robustness (HIGH) - DONE

| Bug | Fix | File | Status |
|-----|-----|------|--------|
| H3: No candle dedup | `_seen_candles` dict, bounded 100/TF, checked before enqueue | `src/engine/runners/live_runner.py` | FIXED |
| H4: Position sync only logs | Sets `_has_existing_position` flag + WARNING on startup | `src/engine/runners/live_runner.py` | FIXED |
| H5: False panic from stale equity | `_equity_initialized` flag, skip drawdown until real reading | `src/engine/runners/live_runner.py` | FIXED |
| M7: Reconnect state stuck | RECONNECTING→RECONNECTING added to valid transitions | `src/engine/runners/live_runner.py` | FIXED |
| M8: `_process_loop` exit hangs | `_stop_event.set()` + state transition on ALL break paths | `src/engine/runners/live_runner.py` | FIXED |
| H1: Non-atomic state save | Temp file + `os.replace()` for atomic write | `src/engine/adapters/state.py` | FIXED |

---

## Gate 5: WebSocket & Exchange Hardening (MEDIUM) - DONE

| Bug | Fix | File | Status |
|-----|-----|------|--------|
| H6: `_ws_public` TOCTOU | Subscriptions moved inside lock block | `src/data/realtime_bootstrap.py` | FIXED |
| M13: Ticker delta zeros | `merge_delta()` method, only updates present fields | `src/data/realtime_models.py` | FIXED |
| M14: REST after connected=True | Fetch before setting `_private_connected = True` | `src/data/realtime_bootstrap.py` | FIXED |
| M10: Limit recorded at limit price | Skip `record_trade()` for limits; fill via WS callback | `src/core/order_executor.py` | FIXED |
| M11: Risk bypass size_usdt=0 | Reject `<= 0` in live mode; backtest exempt | `src/core/risk_manager.py` | FIXED |

---

## Gate 6: Lifecycle & Config Cleanup (LOW) - DONE

| Bug | Fix | File | Status |
|-----|-----|------|--------|
| H2: Double-shutdown race | `_shutting_down` never reset in finally | `src/core/application.py` | FIXED |
| M16: Config reload broken | Reload in-place: mutate existing sub-configs | `src/config/config.py` | FIXED |
| M17: Stats after instance deleted | Capture stats BEFORE `manager.stop()` | `src/cli/subcommands.py` | FIXED |

---

## Validation

```
TRADE VALIDATION  [quick]
G1  YAML Parse ............... PASS  5 plays
G2  Registry Contract ........ PASS  44 indicators
G3  Incremental Parity ....... PASS  43 indicators
G4  Core Engine Plays ........ PASS  5 plays, 2098 trades
RESULT: ALL 4 GATES PASSED (293.0s)
```

## Remaining (not in scope)

~25 LOW-priority bugs identified by the audit team but not blocking production:
- `np.append` O(n) perf in indicator cache hot loop
- Credential plain attributes on BybitClient
- `bars_processed` stat inflation for non-exec TFs
- `assert` stripped by `python -O`
- Config env var coverage gaps
- Various thread safety edge cases in RealtimeState
