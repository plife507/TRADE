# Codebase Health Report (2026-02-18)

Full audit performed by 5-agent Sonnet 4.6 team across all modules.

---

## Objective Metrics

| Check | Result |
|-------|--------|
| **pyright** | 0 errors, 0 warnings, 0 informations |
| **validate quick** | ALL 5 GATES PASSED (G1, G2, G3, G4b, G4) |
| G1 YAML Parse | PASS - 5 plays |
| G2 Registry Contract | PASS - 44 indicators |
| G3 Incremental Parity | PASS - 43 indicators |
| G4b Risk Stops | PASS - 9 risk plays |
| G4 Core Engine Plays | PASS - 5 plays, 2475 trades |

---

## Audit Coverage

| Area | Agent | Files Reviewed |
|------|-------|----------------|
| Engine + Backtest | engine-reviewer | `play_engine.py`, `signal/`, `sim/`, `runtime/`, `artifacts/`, `indicators.py`, `engine_factory.py` |
| Indicators + Structures | indicators-reviewer | `indicators/` (44 indicators, 7 impl files), `structures/` (7 detectors) |
| Live Runner + Data | live-reviewer | `live/runner.py`, `realtime_state.py`, `realtime_bootstrap.py`, `market_data.py`, `safety.py`, `order_executor.py` |
| Tools + CLI + DSL | tools-reviewer | `tools/`, `plays/`, `trade_cli.py`, `dsl_parser.py`, `play.py` |
| Validation | validator | pyright, validate quick |

---

## Findings Summary

| Severity | Count | Description |
|----------|-------|-------------|
| CRITICAL | 1 | `near_pct` double-divide bug (tolerance 100x too tight) |
| WARNING | 8 | Legacy exports, silent fallbacks, stale comments |
| SUGGESTION | 7 | Dead code cleanup, cosmetic improvements |

---

## CRITICAL: `near_pct` Double-Divide Bug

### Impact

**All 70+ plays using `near_pct` have tolerance 100x tighter than intended.** YAML `5` (intended 5%) becomes `0.05%` at evaluation time. Masked because validation checks crash-freedom, not trade semantics.

### Root Cause

When dict-format actions (all current plays) use shorthand lists like `["close", "near_pct", "ema_50", 5]`, the tolerance flows through two `/100` divisions:

1. **`src/backtest/play/play.py:216`** - `_convert_shorthand_condition()` divides: `5 -> 0.05`
2. **`src/backtest/rules/dsl_parser.py:565`** - `parse_cond()` divides again: `0.05 -> 0.0005`

The evaluator (`eval.py:349`) expects a ratio where `0.01 = 1%`. After double-divide, YAML `5` becomes `0.0005` (0.05%) instead of `0.05` (5%).

### Data Flow Trace

```
YAML: ["close", "near_pct", "ema_50", 5]
  |
  v  play.py:_convert_shorthand_condition()
  |  -> {"lhs": ..., "op": "near_pct", "tolerance": 0.05}  (5 / 100)
  |
  v  Stored in when_clause, passed to parse_blocks()
  |
  v  dsl_parser.py: parse_case() -> parse_expr() -> parse_cond()
  |  -> Cond(..., tolerance=0.0005)  (0.05 / 100 AGAIN)
  |
  v  eval.py: eval_near_pct(tolerance=0.0005)
  |  -> |close - ema_50| / |ema_50| <= 0.0005  (0.05%, not 5%)
```

### Additional Inconsistency

`parse_condition_shorthand()` (dsl_parser.py:606-635) does NOT divide at all -- raw YAML value goes straight to evaluator. This path is unused by current plays but is inconsistent with `parse_cond()`.

### Fix

Remove `/100` from `play.py:_convert_shorthand_condition()` line 216. It is an intermediate format converter, not a final parser. `parse_cond()` already handles the percentage-to-ratio conversion.

### Affected Plays (70+)

Production: `scalper_btc_bb_rsi`, `scalper_btc_v8_long`, `scalper_eth_v5/v6/v7`, `scalper_vwap_rsi_v4`, `sol_v2_pullback_fib`

Validation: `V_CORE_005`, `OP_010`, `STR_001/005/009/010`, `CL_006/009/012`, `PAT_017/018/021/026/027/033/034`, `PF_002/005`, 30+ real-data plays (`RV_*`)

---

## Warnings (Should Fix)

### W-1: Deprecated `evaluate_condition()` Still Exported

**File**: `src/backtest/rules/__init__.py:27,53` and `src/backtest/rules/eval.py:561`

`evaluate_condition()` emits a `DeprecationWarning` but is still exported in `__all__`. Its only caller is `evaluate_condition_dict()` (also in `eval.py`) which itself has zero external callers. Both are dead code -- production uses `ExprEvaluator`.

**Fix**: Remove both `evaluate_condition()` and `evaluate_condition_dict()` from `eval.py`, and remove from `__init__.py` exports.

### W-2: FeedStore Metadata Mismatch is Warning-Only

**File**: `src/backtest/runtime/feed_store.py:150-163`

Comment says "Log warning but don't fail for backward compatibility" when indicator metadata keys don't match indicator keys. Violates ALL FORWARD, NO LEGACY.

**Fix**: Replace warning with `raise ValueError(...)`.

### W-3: `_calculate_funding()` Silent `mark_price` Fallback

**File**: `src/backtest/sim/funding/funding_model.py:111,130-131`

`mark_price: float | None = None` silently falls back to `entry_price`. Violates NO LEGACY -- callers should always provide mark_price explicitly.

**Fix**: Make `mark_price` required (`float`), remove fallback. Verify the single caller (`apply_funding`, line 99) always passes it.

### W-4: `Bar` Re-Export Labeled "backward compat"

**File**: `src/backtest/sim/types.py:96-97`

Comment says "backward compatibility" but it's a legitimate convenience re-export used by `backtest_runner.py:589`. Not harmful, but the comment is misleading.

**Fix**: Change comment to "Re-export from runtime.types for convenience" or update the import in `backtest_runner.py` to go directly to `runtime.types`.

### W-5: Stale Comment References Deleted `compute.py`

**File**: `src/backtest/indicator_vendor.py:612`

Comment reads "compute.py's fast-path uses these directly." `compute.py` was deleted in P5.

**Fix**: Remove or update the comment.

### W-6: Redundant `datetime` Import in Hot Path

**File**: `src/engine/runners/live_runner.py:575`

`from datetime import datetime, timezone` imported inside `_on_kline_update()` which fires on every WebSocket candle. `datetime` is already imported at module level (line 28).

**Fix**: Remove the local import.

### W-7: `backtest_play_normalize_batch_tool` Not Exported

**File**: `src/tools/__init__.py`

Function defined in `backtest_play_tools.py:1362`, used by `cli/subcommands.py:622` via direct import. Not exported from `tools/__init__.py`. All other public tools are exported.

**Fix**: Add to `__init__.py` imports and `__all__`.

### W-8: WS Health Not Checked Before Signal Execution

**File**: `src/engine/runners/live_runner.py`

`_process_candle()` checks `_position_sync_ok` and `SafetyChecks` but does NOT explicitly check `is_websocket_healthy()` before executing signals. The GlobalRiskView integration checks this indirectly (if enabled), but it's not guaranteed for all configs.

**Fix**: Add explicit `is_websocket_healthy()` check in signal execution gate.

---

## Suggestions (Low Priority)

### S-1: `BacktestResult.metrics` SimpleNamespace Fallback

**File**: `src/engine/runners/backtest_runner.py:184-221`

Fallback returns zeros for most fields. Path is unreachable in production. Consider replacing with `raise RuntimeError`.

### S-2: Dead `_build_feed_store()` Method

**File**: `src/engine/runners/backtest_runner.py:494-504`

Always raises `RuntimeError`. The docstring calls it "deprecated" but it just throws. Delete the method entirely.

### S-3: Stale P1.2 Refactor Comments

**File**: `src/backtest/runner.py:803-808`

Dead comments referencing "P1.2 Refactor" about deleted adapter classes. Remove.

### S-4: `_get_order_timestamp()` Has `datetime.now()` Fallback

**File**: `src/engine/adapters/backtest.py:263`

Non-deterministic `datetime.now()` fallback in backtest mode. Should be unreachable. Replace with `raise RuntimeError("Bar timestamp not set")`.

### S-5: Stale Docstring in `indicators/__init__.py`

**File**: `src/indicators/__init__.py:10`

References "compute" module which was deleted in P5. Update to reflect current structure.

### S-6: Stale Docstring in `dsl_parser.py`

**File**: `src/backtest/rules/dsl_parser.py:988`

Example uses `yaml_data["blocks"]` but the actual YAML key is `"actions"` since DSL v3.0.0.

### S-7: `parse_condition_shorthand` Missing `/100` Division

**File**: `src/backtest/rules/dsl_parser.py:606-635`

Unlike `parse_cond()`, this function does NOT divide `near_pct` tolerance by 100. Currently unused by production plays (all go through play.py conversion), but inconsistent. Should add `/100` for consistency.

---

## Confirmed Clean

- No broken imports to deleted P5 modules
- No references to `PlayRunResult`, `create_backtest_engine` alias, `StructureStore`
- No `idea_hash` field usage (all `play_hash`)
- No `size_usd` (only `size_usdt`)
- No banned timeframe identifiers (`ltf`, `htf`, `LTF`, `HTF`, `MTF`)
- No `closest_active_*` references (all `first_active_*`)
- All 44 indicators registered with correct `is_ready` semantics
- All 7 structure detectors have `reset()` + `to_dict()`
- PSAR factory uses correct param names (`af0`, `af`, `max_af`)
- Hash tracing: all canonical through `hashes.py`
- Live safety: fail-closed, reduce_only, position sync gate all correct
- Multi-TF routing: `_play_timeframes` set, exec-only signal eval
