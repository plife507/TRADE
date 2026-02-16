# VWAP System Audit

## Fix Status (2026-02-15)

| # | Severity | Issue | Status |
|---|----------|-------|--------|
| 1 | **CRITICAL** | Live `ts_open` never passed in `update()` -- session resets dead | **FIXED** (`live.py:301-303`) |
| 2 | **CRITICAL** | Live `ts_open` never passed in warmup -- warmup ignores sessions | **FIXED** (`live.py:117-129, 183-185`) |
| 3 | BUG | Weekly boundary resets on Thursday, not Monday | **FIXED** (`volume.py:186-190`) |
| 4 | BUG | NaN inputs permanently poison VWAP cumulative sums | **FIXED** (`volume.py:168-170, 306-308`) |
| 5 | BUG | NaN inputs permanently poison anchored VWAP cumulative sums | **FIXED** (`volume.py:306-308`) |
| 6 | DESIGN | Unknown anchor values silently fall through to daily | **FIXED** - now raises `ValueError` (`volume.py:191`) |
| 7 | BUG (mitigated) | Batch anchored_vwap computed without swing versions | OK - engine overwrites every bar |
| 8 | BUG | IncrementalSwing missing `reset()` | **FIXED** (`swing.py:1085-1139`) |
| 9 | BUG | IncrementalSwing missing `to_dict()` for crash recovery | **FIXED** (`swing.py:1141-1198`) |
| 10 | DESIGN | Anchored VWAP without swing structure silently degrades | **FIXED** - now logs WARNING (`play_engine.py:1039-1044`) |
| 11 | DESIGN | `anchored_vwap.bars_since_anchor` not accessible in DSL | **FIXED** - registry multi_output, snapshot resolves primary output (`indicator_registry.py:554-561`) |
| 12 | EDGE | IND_084 doesn't test anchored_vwap in DSL conditions | **FIXED** - play now tests `close > avwap` and `avwap.bars_since_anchor > 3` |

---

## 1. Indicator Classes (volume.py)

Audit of `IncrementalVWAP` and `IncrementalAnchoredVWAP` in
`src/indicators/incremental/volume.py`.

### 1.1 IncrementalVWAP -- Formula Correctness

- [OK] Typical price: `tp = (high + low + close) / 3.0` (`volume.py:168`). Matches pandas_ta definition.
- [OK] VWAP = `cumsum(tp * volume) / cumsum(volume)` via `_cum_tp_vol / _cum_vol` (`volume.py:203`). Correct.
- [OK] `value` property guards `_cum_vol == 0` and returns `NaN` (`volume.py:200-201`). Prevents division by zero.
- [OK] `is_ready` returns True after first bar (`_count >= 1`, `volume.py:207`). Consistent with cumulative nature.

### 1.2 IncrementalVWAP -- Session Boundary Reset

- [OK] `_last_reset_boundary = -1` init (`volume.py:142`). First bar sets boundary but does NOT reset (guard: `self._last_reset_boundary >= 0` at line 160). Correct: the first session should accumulate from bar 0, not reset on bar 0.
- [OK] Session boundary detection: `boundary != self._last_reset_boundary and self._last_reset_boundary >= 0` (`volume.py:160`). Only resets after the first session boundary is established.
- [OK] On reset: `_cum_tp_vol` and `_cum_vol` are zeroed (`volume.py:162-163`). `_count` is NOT reset. This is intentional: `is_ready` stays True across sessions, and `_count` tracks total bars seen, not per-session bars.
- [FIXED] **Weekly boundary resets on THURSDAY, not Monday.** Was: `ts_ms // (86_400_000 * 7)`. Now: `(ts_ms + 3 * ms_per_day) // (ms_per_day * 7)` which correctly aligns to ISO Monday boundary. Verified with unit tests.
- [FIXED] **Unknown anchor values fall through to daily.** Was: default `return ts_ms // ms_per_day`. Now: `raise ValueError(f"Unknown VWAP anchor: {self.anchor!r}. Use 'D', 'W', or None.")`.
- [OK] **`anchor=None` path**: When `anchor=None`, the `if ts_open is not None and self.anchor:` guard at line 158 is False (since `None` is falsy). No boundary check occurs, accumulation runs forever. This is the documented "Cumulative (no reset)" mode and works correctly.

### 1.3 IncrementalVWAP -- ts_open Dependency (Cross-cutting with Section 3)

- [FIXED] **Live incremental path never passes `ts_open`.** Was: `kwargs` had only `high`, `low`, `close`, `volume`. Now: `update()` passes `ts_open=int(candle.ts_open.timestamp() * 1000)` when `candle.ts_open is not None`. Session boundary resets now fire correctly in live/demo mode.
- [OK] Backtest vectorized path passes `ts_open` correctly via `feature_frame_builder.py:646` -> `indicator_vendor.py:417-418`. Vectorized VWAP in backtest uses pandas_ta which handles session resets natively.
- [EDGE] **Parity audit tests cumulative mode only.** The parity audit (`audit_incremental_parity.py:1716`) calls `inc.update(high=, low=, close=, volume=)` WITHOUT `ts_open`. The vectorized comparison also omits `ts_open` (`line 1720`). Confirms cumulative formula correctness only; no test coverage for session boundary resets.

### 1.4 IncrementalVWAP -- NaN Input Handling

- [FIXED] **NaN inputs permanently poison cumulative sums.** Was: NaN would propagate through `_cum_tp_vol` permanently. Now: NaN guard skips the bar's accumulation (`if np.isnan(high) or np.isnan(low) or np.isnan(close) or np.isnan(volume): return`). `_count` still increments so `is_ready` stays true.
- [OK] **`volume=0` is safe.** When `volume=0`: `_cum_tp_vol += tp * 0 = 0` (no change), `_cum_vol += 0` (no change). `value` returns previous VWAP. Correct behavior: zero-volume bars don't affect VWAP.

### 1.5 IncrementalVWAP -- reset() Completeness

- [OK] `reset()` (`volume.py:188-193`) zeros `_cum_tp_vol`, `_cum_vol`, `_count`, and resets `_last_reset_boundary` to -1. Complete reset to initial state.
- [OK] After `reset()`, `is_ready` returns False (`_count == 0 < 1`). First new bar will make it ready again.

### 1.6 IncrementalVWAP -- Floating Point Accumulation

- [EDGE] **Cumulative sum precision degrades over long sessions.** `_cum_tp_vol` and `_cum_vol` accumulate via `+=` over potentially thousands of bars within a session. With typical price ~50000 and volume ~1000, `_cum_tp_vol` grows to ~50,000,000 per bar. After 1000 bars, it's ~5e10. Float64 has ~15 significant digits, so sub-cent precision is maintained. For crypto with 8+ decimal places, this may matter over very long sessions (10,000+ bars). Daily resets mitigate this for `anchor="D"`.

---

### 1.7 IncrementalAnchoredVWAP -- Formula Correctness

- [OK] Same VWAP formula as IncrementalVWAP: `_cum_tp_vol / _cum_vol` (`volume.py:322`). Correct.
- [OK] Division by zero guarded by `_cum_vol == 0` check (`volume.py:320`). Returns `NaN`.
- [OK] `is_ready` after first bar (`_count >= 1`, `volume.py:331`). Correct.
- [OK] `bars_since_anchor` property (`volume.py:325-327`) returns `_bars_since_anchor`. Starts at 0 after reset, incremented on each bar.

### 1.8 IncrementalAnchoredVWAP -- All 7 Anchor Source Modes

- [OK] **`swing_high`** (`volume.py:282-284`): Resets when `swing_high_ver` increases and previous version was established (>= 0). Correct.
- [OK] **`swing_low`** (`volume.py:285-287`): Same pattern for low pivots. Correct.
- [OK] **`swing_any`** (`volume.py:282-287`): Resets on EITHER high or low pivot. Uses two independent `if` blocks (not `elif`), so both can trigger on the same bar if fractal mode confirms both. `should_reset` is True if either fires. Correct.
- [OK] **`pair_high`** (`volume.py:271-272`): Resets on bullish pair completion (L->H). `pair_dir == "bullish"` check is correct (bullish = ending on high).
- [OK] **`pair_low`** (`volume.py:273-274`): Resets on bearish pair completion (H->L). Correct.
- [OK] **`pair_any`** (`volume.py:269-270`): Resets on any complete pair. Correct.
- [OK] **`manual`** (`volume.py:277-292`): Falls into the `else` branch (raw pivot path). Neither `"swing_high"` nor `"swing_low"` match `"manual"`, so both `if` blocks at lines 282-287 are skipped. `should_reset` stays False. Only explicit `reset()` triggers reset. Correct.

### 1.9 IncrementalAnchoredVWAP -- Version Tracking Semantics

- [OK] `_last_swing_high_ver = -1` init (`volume.py:242`). Swing detector's `_high_version` starts at 0. On first bar, `swing_high_version=0` is passed. `0 > -1` is True but `-1 >= 0` is False, so no reset. `_last_swing_high_ver` updated to 0. On first confirmed high (`_high_version` goes 0->1): `1 > 0` is True and `0 >= 0` is True -> RESET. Correct: first pivot triggers first reset.
- [OK] `_last_pair_version = -1` init (`volume.py:244`). Same pattern. First complete pair triggers first reset.
- [OK] **Version jumps > 1**: If version jumps from 0 to 5, `5 > 0` triggers one reset. Intermediate versions are lost but the behavior is correct (one reset event per check).
- [OK] **Version goes backwards** (e.g., bug in detector): `3 > 5` is False, no reset. `_last_pair_version` updated to 3 (since 3 >= 0). Future forward increments from 3 work correctly.
- [OK] **Directional pair version consumption**: For `pair_high` mode, if a bearish pair completes (wrong direction), `should_reset` stays False but `_last_pair_version` IS updated (`volume.py:275-276`). Correct: the version change is acknowledged without triggering reset. Next bullish pair at a higher version will reset.

### 1.10 IncrementalAnchoredVWAP -- bars_since_anchor

- [OK] On reset: `_bars_since_anchor = 0` (`volume.py:297`), then immediately incremented to 1 (`volume.py:300`). The reset bar itself has `bars_since_anchor = 1`. Correct: reset bar is the first bar of the new VWAP segment.
- [OK] Without reset: `_bars_since_anchor` increments monotonically (`volume.py:300`).

### 1.11 IncrementalAnchoredVWAP -- reset() Completeness

- [OK] `reset()` (`volume.py:306-314`) zeros all accumulators and resets all version trackers to -1. Complete reset.
- [OK] After `reset()`, `is_ready` returns False (`_count == 0`).
- [OK] Version trackers reset to -1, so the first-version-seen pattern repeats correctly after reset.

### 1.12 IncrementalAnchoredVWAP -- NaN and Zero Volume

- [FIXED] **Same NaN poisoning as IncrementalVWAP.** Was: no NaN guard. Now: same NaN guard as IncrementalVWAP skips accumulation for bars with NaN inputs.
- [OK] `volume=0` is safe. Same behavior as IncrementalVWAP.

### 1.13 IncrementalAnchoredVWAP -- ts_open Not Needed

- [OK] AnchoredVWAP does NOT need `ts_open`. It resets on structure events (swing versions), not time boundaries. No issue.

---

### 1.14 Summary of Issues

| # | Severity | Issue | Status |
|---|----------|-------|--------|
| 1 | BUG | Weekly boundary resets on Thursday (epoch-aligned), not Monday (ISO) | **FIXED** |
| 2 | BUG | Live path never passes `ts_open` to `IncrementalVWAP.update()` | **FIXED** |
| 3 | BUG | NaN inputs permanently poison VWAP cumulative sums | **FIXED** |
| 4 | BUG | NaN inputs permanently poison anchored VWAP cumulative sums | **FIXED** |
| 5 | EDGE | No test coverage for VWAP session boundary resets | Open |
| 6 | EDGE | Floating point accumulation precision degrades over very long sessions (10,000+ bars) | Acceptable |
| 7 | DESIGN | Unknown anchor values silently fall through to daily boundary | **FIXED** |

---

## 2. Backtest Batch Path

Audit of the VWAP/Anchored-VWAP batch pre-computation path and engine bar-loop overwrite.
Files: `src/backtest/indicator_vendor.py`, `src/indicators/compute.py`,
`src/backtest/indicator_registry.py`, `src/engine/play_engine.py`,
`src/backtest/engine_factory.py`.

### 2.1 Standard VWAP Batch Path

- [OK] **`anchor` param flows to pandas_ta.** `indicator_registry.py:547-553` declares `vwap` with `params={"anchor"}`. `compute.py:216-250` passes `**params` to `vendor.compute_indicator()`. `indicator_vendor.py:417-418` extracts `anchor` from kwargs and passes it to `_compute_vwap_with_datetime_index()`. The function calls `ta.vwap(high, low, close, volume, **kwargs)` at line 210, where `kwargs` includes `anchor`. Confirmed in `reference/pandas_ta_repo/pandas_ta_classic/overlap/vwap.py:43`: pandas_ta reads `anchor` from kwargs and defaults to `"D"`.
- [OK] **DatetimeIndex construction.** `_compute_vwap_with_datetime_index()` (`indicator_vendor.py:150-214`) builds a `pd.DatetimeIndex` from `ts_open` column (line 168). pandas_ta uses `index.to_period(anchor)` for session grouping. Correct.
- [OK] **ts_open available in batch path.** `feature_frame_builder.py:646` provides the full DataFrame which includes `ts_open` from the candle data. The vendor extracts it at `indicator_vendor.py:417`.

### 2.2 Anchored VWAP Batch Pre-computation

- [BUG] **Batch `_compute_anchored_vwap()` NEVER receives swing version data.** (`indicator_vendor.py:217-266`). The caller chain is: `compute.py:216-250` -> `vendor.compute_indicator("anchored_vwap", ...)` -> `_compute_anchored_vwap(high, low, close, volume, **params)`. The `params` dict comes from the YAML feature declaration and only contains `{"anchor_source": "swing_any"}` (or similar). It never contains `swing_high_version`, `swing_low_version`, `pair_version`, or `pair_direction` dictionaries. The `_get_dict_val()` helper (`indicator_vendor.py:231-235`) always returns the default `-1` for all versions, so `IncrementalAnchoredVWAP` never detects a version change and never resets. **Result: batch-computed anchored VWAP is purely cumulative from bar 0.**
- [OK] **`_get_dict_val()` helper is defensive.** (`indicator_vendor.py:231-235`). Returns default when key not in kwargs OR when value is not a dict. Safe against unexpected param types.
- [OK] **IncrementalAnchoredVWAP used correctly in batch.** (`indicator_vendor.py:241-260`). Iterates all bars, passes OHLCV + version kwargs per bar. Formula is correct when versions are available. The issue is solely that versions are never provided.

### 2.3 Engine Bar-Loop Overwrite (Mitigates 2.2)

- [OK] **Engine overwrites batch values every bar.** `PlayEngine._update_anchored_vwap()` (`play_engine.py:1041-1097`) runs inside `_update_incremental_state()` at line 1001, which is called at line 423 -- BEFORE `_is_ready()` check at line 426. Every bar (including warmup) gets the engine-computed value written to FeedStore.
- [OK] **FeedStore write is correct.** (`play_engine.py:1083-1089`). For backtest mode, the engine reads the current bar's swing versions from `exec_state.get_value()`, updates its own `IncrementalAnchoredVWAP` instance, and writes the result to `store.indicators[name][bar_index]`. This overwrites the stale batch value.
- [OK] **Warmup bars overwritten before rule evaluation.** Rules are only evaluated after `_is_ready()` returns True (line 426). By that point, all FeedStore anchored_vwap values for bars 0..current have been overwritten by the engine. No stale batch values reach rule evaluation.

### 2.4 Registry Entries

- [OK] **VWAP registry entry** (`indicator_registry.py:547-553`): `inputs={high,low,close,volume}`, `params={anchor}`, `warmup=1`, `output_type=FLOAT`. Warmup=1 is correct for cumulative indicators.
- [OK] **Anchored VWAP registry entry** (`indicator_registry.py:554-560`): `inputs={high,low,close,volume}`, `params={anchor_source}`, `warmup=1`, `output_type=FLOAT`. Correct.
- [OK] **FeatureSpec creation.** (`engine_factory.py:133`). `output_key=feature.id` maps Feature.id to FeatureSpec.output_key. This key is used to look up values in FeedStore.indicators. Consistent across batch and engine paths.

### 2.5 DatetimeIndex Edge Cases (indicator_vendor.py:150-214)

- [OK] **Duplicate timestamps handled by pandas_ta.** `_compute_vwap_with_datetime_index()` creates a DatetimeIndex from `ts_open` at line 190-192. If duplicate timestamps exist (e.g., two bars with the same open time), `pd.to_datetime()` produces a non-unique DatetimeIndex. pandas_ta's `vwap()` calls `index.to_period(anchor).groupby(...)` which handles duplicates correctly -- duplicate timestamps fall in the same session and accumulate together. No error.
- [OK] **Non-UTC timestamps converted to UTC.** Both conversion paths at lines 190-192 use `utc=True`, which forces the result to UTC. If `ts_open` contains naive integers (milliseconds since epoch), they're interpreted as UTC milliseconds. If `ts_open` contains datetime objects, they're converted to UTC. No timezone ambiguity.
- [OK] **Result maps back to original integer index.** Line 175 saves `original_index = close.index` before creating the DatetimeIndex. Line 213 creates a new Series with `index=original_index`, using `.values` from the VWAP result to strip the DatetimeIndex. Integer-indexed result matches the DataFrame's original index.
- [OK] **ts_open=None returns NaN with warning.** Lines 177-185 check for None `ts_open` and return an empty NaN Series with a `UserWarning`. Does not crash.

### 2.6 Volume Edge Cases in Batch Path

- [OK] **Zero volume in standard VWAP.** pandas_ta's `vwap()` uses `cumsum(tp * volume) / cumsum(volume)`. When `volume=0` for some bars, those bars contribute 0 to both numerator and denominator. VWAP stays at previous value. If ALL bars have `volume=0`, denominator is 0 and pandas returns NaN. Correct.
- [OK] **Zero volume in anchored VWAP.** `_compute_anchored_vwap()` passes `volume=float(volume.iloc[i])` at line 258. `IncrementalAnchoredVWAP` inherits the same formula as `IncrementalVWAP` -- zero volume leaves accumulators unchanged, `value` returns previous VWAP.

### 2.7 compute.py Routing (compute.py:76-252)

- [OK] **VWAP and anchored_vwap route through generic `else` branch.** Neither `vwap` nor `anchored_vwap` has a dedicated `elif` block in `apply_feature_spec_indicators()` (unlike `ema`, `sma`, `rsi`, etc.). They fall through to the generic block at line 216-250 which calls `vendor.compute_indicator(ind_type, ...)`. This is correct because `vendor.compute_indicator()` has explicit handlers for both at lines 411-429.
- [OK] **ts_open passed correctly.** The generic branch at line 222 extracts `ts_open` from the DataFrame: `ts_open = df.get("ts_open") if "ts_open" in df.columns else df.get("timestamp")`. This is passed as `ts_series` to `vendor.compute_indicator()` at line 234. For VWAP, the vendor forwards it to `_compute_vwap_with_datetime_index()`. Correct.
- [OK] **anchored_vwap receives `**params` (anchor_source) but NOT swing versions.** Line 235 passes `**params` which contains only YAML-declared params (e.g., `{"anchor_source": "swing_any"}`). No swing version data is injected. This is the root cause of bug 2.2.
- [OK] **Anchored VWAP is the ONLY structure-dependent indicator.** Searched all 44 indicator registry entries in `indicator_registry.py`. No other indicator references structure state (swing, zone, trend, fib). Anchored VWAP is unique in requiring cross-system wiring (indicator depends on structure detector output).

### 2.8 _warmup_minimal and Registry Warmup (indicator_registry.py:190-192)

- [OK] **`_warmup_minimal()` returns 1.** Function body: `return 1`. Both `vwap` and `anchored_vwap` use this formula. This means warmup for VWAP is 1 bar.
- [OK] **1-bar warmup is correct for VWAP.** VWAP is cumulative: after 1 bar, `_cum_tp_vol` and `_cum_vol` are non-zero, and `value` is just `tp` (typical price). This is mathematically valid. Unlike SMA(20) which needs 20 bars, VWAP produces a meaningful value from bar 1.
- [EDGE] **Warmup=1 means FeedStore column has non-NaN from bar 1.** `find_first_valid_bar()` (`compute.py:280-338`) checks for non-NaN in indicator columns. Since batch VWAP produces values from bar 1, the first valid bar gate won't delay on VWAP. For anchored VWAP, the batch values are wrong (cumulative) but non-NaN -- so the gate passes. This is fine because the engine overwrites before rule evaluation.

### 2.9 engine_data_prep.py Call Path

- [OK] **Exec TF indicators.** `_apply_indicators_to_frame()` (`engine_data_prep.py:226-239`) extracts `exec` specs from `config.feature_specs_by_role` and calls `apply_feature_spec_indicators(df, exec_specs)`. All VWAP features on exec TF are computed here.
- [OK] **Multi-TF indicators.** For multi-TF builds, `engine_data_prep.py:569-574` applies specs per TF via `apply_feature_spec_indicators(df, specs)`. If VWAP is declared on `med_tf` or `high_tf`, it's computed on that TF's DataFrame (which has its own timestamps and bars). Correct.
- [OK] **All-NaN anchored_vwap values handled.** The batch path produces cumulative (wrong but non-NaN) values. These are overwritten by the engine. Even if they were NaN, `find_first_valid_bar()` would delay simulation start, but the engine overwrite would fix them before rule evaluation. No crash path.

### 2.10 Engine IncrementalAnchoredVWAP Sync and Stability

- [OK] **Engine AVWAP instance stays in sync with bar_index.** `_update_anchored_vwap()` is called once per `process_bar(bar_index)` invocation at line 1001. The engine's `IncrementalAnchoredVWAP` instance is updated sequentially for bar 0, 1, 2, ... N. Since AVWAP is cumulative between resets, the instance state at bar N reflects exactly bars 0..N. The bar_index used to write back to FeedStore (`store.indicators[name][bar_index]`) matches.
- [OK] **Swing key is stable across bars.** `_init_anchored_vwap_cache()` runs once during lazy init (line 1003-1007, guard: `if self._avwap_cache is not None: return`). The `swing_key` is set once and never changes. The swing detector instance referenced by `swing_key` is the same object throughout the bar loop.
- [OK] **No bar skipping possible.** `process_bar()` is called by `BacktestRunner` in a sequential loop (`backtest_runner.py`). Every bar index is visited exactly once. No risk of the AVWAP instance missing a bar.

### 2.11 Data Flow Diagram

```
BATCH PRE-COMPUTATION (runs once before bar loop):
  engine_factory.create_engine_from_play()
    -> DataBuilder -> engine_data_prep.apply_feature_spec_indicators()
      -> compute.compute_indicator("anchored_vwap", df, params={"anchor_source":"swing_any"})
        -> vendor._compute_anchored_vwap(h, l, c, v, anchor_source="swing_any")
          -> IncrementalAnchoredVWAP.update() with versions=-1 (NEVER RESETS)
          -> FeedStore.indicators["anchored_vwap_swing_any"] = cumulative values

ENGINE BAR LOOP (runs per bar, OVERWRITES batch values):
  PlayEngine.process_bar(bar_index)
    -> _update_incremental_state()
      -> exec_state.update_exec(bar)  # updates swing detector, increments versions
      -> _update_anchored_vwap()
        -> reads swing versions from exec_state.get_value()
        -> IncrementalAnchoredVWAP.update() with REAL versions (RESETS correctly)
        -> FeedStore.indicators["anchored_vwap_swing_any"][bar_index] = correct value
    -> _is_ready() check
    -> rule evaluation reads corrected values from FeedStore
```

### 2.12 Bug Summary

| # | Severity | Issue | File:Line |
|---|----------|-------|-----------|
| 1 | BUG (mitigated) | Batch anchored_vwap computed without swing versions -- purely cumulative | `indicator_vendor.py:217-266`, `compute.py:216-250` |
| 2 | DESIGN | Multiple swing structures on exec TF: first found wins, no selection mechanism | `play_engine.py:1033-1037` |
| 3 | DESIGN | Anchored VWAP on non-exec TF reads from exec TF swing -- wrong structure + wrong FeedStore | `play_engine.py:1033` |
| 4 | DESIGN | No swing structure declared: silent degradation to cumulative VWAP, no warning | `play_engine.py:1036` |
| 5 | LOW | Batch computation is wasted O(n) work for anchored_vwap since engine overwrites every value | `indicator_vendor.py:217-266` |

### 2.13 Recommendations

1. **Skip batch pre-computation for anchored_vwap.** Since the engine overwrites every bar, the batch step is wasted work. Add anchored_vwap to an exclusion list in `apply_feature_spec_indicators()` (similar to how live path uses `_engine_managed_keys`). Allocate a NaN array instead.
2. **Warn when anchored_vwap declared without swing structure.** In `_init_anchored_vwap_cache()`, log a WARNING when `swing_key` is None but anchored_vwap features exist. This surfaces the silent degradation.
3. **Support `anchor_swing_key` param.** Allow anchored_vwap features to specify which swing structure to use, instead of always taking the first one found.
4. **Guard non-exec TF anchored_vwap.** Either (a) raise an error if anchored_vwap is declared on a non-exec TF, or (b) extend the engine to read swing versions from the appropriate TF.

---

## 4. Swing Detector Version Wiring

Audit of `_high_version` and `_low_version` fields in `IncrementalSwing`, their
integration with `IncrementalAnchoredVWAP`, and edge cases in the engine wiring.

### 4.1 Version Fields in IncrementalSwing

- [OK] `_high_version` and `_low_version` initialized to 0 in `__init__` (`src/structures/detectors/swing.py:322-323`)
- [OK] `_version` (combined counter) also initialized to 0 (`swing.py:321`)
- [OK] **Invariant holds: `_high_version + _low_version == _version`** at all times. Both counters increment atomically alongside `_version` in every code path.

### 4.2 All 4 Increment Sites

- [OK] Fractal mode, swing high confirmed (`swing.py:424-425`): `_version += 1` then `_high_version += 1`
- [OK] Fractal mode, swing low confirmed (`swing.py:464-465`): `_version += 1` then `_low_version += 1`
- [OK] ZigZag mode, high pivot (uptrend reversal) (`swing.py:548-549`): `_version += 1` then `_high_version += 1`
- [OK] ZigZag mode, low pivot (downtrend reversal) (`swing.py:598-599`): `_version += 1` then `_low_version += 1`

### 4.3 Both-pivots-on-same-bar (Fractal Mode)

- [OK] Fractal mode uses two independent `if` blocks (lines 398, 438), not `if/elif`. Both swing high AND swing low CAN confirm on the same bar. When both fire: `_version` increments twice, `_high_version` once, `_low_version` once. Invariant preserved.
- [OK] ZigZag mode: At most one pivot per bar (direction can only switch once), so no double-increment issue.

### 4.4 get_output_keys() and get_value()

- [OK] `high_version` listed in `get_output_keys()` (`swing.py:993`)
- [OK] `low_version` listed in `get_output_keys()` (`swing.py:994`)
- [OK] `get_value("high_version")` returns `self._high_version` (`swing.py:1042-1043`)
- [OK] `get_value("low_version")` returns `self._low_version` (`swing.py:1044`)

### 4.5 reset() -- FIXED

- [FIXED] **IncrementalSwing now has `reset()`.** (`swing.py:1085-1139`). Resets all ~44 mutable state fields including: fractal ring buffers (re-created), alternation state, zigzag state, pivot outputs, significance tracking, version counters (to 0), and paired pivot state machine. `TFIncrementalState.reset()` will now find and call it via `hasattr(struct, 'reset')`. Note: other detectors (trend, zone, fib, derived_zone, rolling_window, market_structure) still lack `reset()` -- systemic gap remains for non-swing detectors.

### 4.6 to_dict() / Crash Recovery Serialization -- FIXED

- [FIXED] **IncrementalSwing now has `to_dict()`.** (`swing.py:1141-1198`). Serializes all state including: fractal ring buffers (via `to_array().tolist()`), alternation state, zigzag state, pivot outputs, significance tracking, version counters, and paired pivot state machine (PairState serialized as string). `TFIncrementalState.to_json()` will now find and call it via `hasattr(detector, 'to_dict')`. After crash recovery, `_high_version` and `_low_version` will be restored, so anchored VWAP resets continue correctly. Note: other detectors still lack `to_dict()` -- systemic gap remains for non-swing detectors.

### 4.7 Engine Wiring: _init_anchored_vwap_cache()

- [OK] Scans `feature_registry.all_features()` for `indicator_type == "anchored_vwap"` (`play_engine.py:1022-1023`). Correctly creates `IncrementalAnchoredVWAP` instances with `anchor_source` from params.
- [DESIGN] **Swing structure found by `_type == "swing"` attribute** (`play_engine.py:1035`). Uses `getattr(detector, "_type", "")` which relies on the `_type` attribute set by `BaseIncrementalDetector.validate_and_create()`. This works correctly because `_type` is set to the registry key ("swing") during construction.
- [OK] Takes the FIRST swing structure found on exec TF (`play_engine.py:1033-1037`, `break` after first match).

### 4.8 Engine Wiring: _update_anchored_vwap()

- [OK] Called AFTER `_incremental_state.update_exec()` in `_update_incremental_state()` (`play_engine.py:1001`), so swing versions are fresh when read.
- [OK] Extracts `high_version`, `low_version`, `pair_version`, `pair_direction` from exec state via `get_value()` (`play_engine.py:1065-1068`).
- [OK] Catches `KeyError` if swing structure not ready yet (`play_engine.py:1069-1070`). When swing_key is found but versions aren't available, `swing_kwargs` stays empty and anchored VWAP receives default -1 versions (no resets triggered).
- [OK] Writes corrected values back to FeedStore (backtest) or LiveIndicatorCache (live) (`play_engine.py:1083-1097`).

### 4.9 Edge Case: Anchored VWAP Declared But No Swing Structure

- [FIXED] **Degradation now warns.** If the play declares an `anchored_vwap` feature but no swing structure on the exec TF, `_init_anchored_vwap_cache()` now logs a WARNING listing the affected feature names and explaining that anchored VWAP degrades to cumulative VWAP (`play_engine.py:1039-1044`). The VWAP still runs in cumulative mode (no crash), but the operator is alerted.

### 4.10 Edge Case: Anchored VWAP on med_tf or high_tf

- [EDGE] **Engine only wires exec TF swing.** `_init_anchored_vwap_cache()` only searches `self._incremental_state.exec.list_structures()` (`play_engine.py:1033`). If anchored_vwap is declared on `med_tf` or `high_tf`, and the swing structure is also on that TF (not exec), the engine won't find it. The anchored VWAP will never reset. Currently the feature system likely prevents this (features are TF-scoped), but it's an unguarded assumption.

### 4.11 Edge Case: Multiple Swing Structures on Exec TF

- [DESIGN] **First swing wins.** If multiple swing structures are declared on exec TF (e.g., `swing_fast` with left=3 and `swing_slow` with left=10), `_init_anchored_vwap_cache()` takes the first one found (`play_engine.py:1036, break`). This may not be the intended swing for anchoring. No mechanism to specify which swing structure to use. **Recommendation**: Allow `anchor_swing_key` param on anchored_vwap to explicitly select which swing structure to wire to.

### 4.12 Edge Case: Swing ATR Dependency Timing

- [OK] Swing structures that use `atr_key` for significance filtering: the ATR value is read from `bar.indicators` which is populated BEFORE structure update. So ATR is always available by the time the swing detector reads it. No timing issue.

### 4.13 IncrementalAnchoredVWAP Version Tracking

- [OK] Uses `_last_swing_high_ver` and `_last_swing_low_ver` (initialized to -1) for raw pivot anchoring (`src/indicators/incremental/volume.py:242-243`).
- [OK] Uses `_last_pair_version` (initialized to -1) for pair-based anchoring (`volume.py:244`).
- [OK] First version seen (`ver >= 0`) is stored but does NOT trigger a reset (guard: `self._last_swing_high_ver >= 0` / `self._last_pair_version >= 0`). This correctly avoids resetting on the very first pivot.
- [OK] Subsequent version increases trigger reset of cumulative TP*vol and vol sums (`volume.py:294-297`).

### 4.14 Batch Pre-computation Path (indicator_vendor.py)

- [OK] `_compute_anchored_vwap()` (`indicator_vendor.py:217-266`) accepts swing version dicts via `**kwargs` and uses `_get_dict_val()` to extract per-bar versions. Correctly handles missing kwargs by returning default `-1`.
- [EDGE] **Batch caller never passes swing versions.** The `FeatureFrameBuilder._compute_single_output()` (`feature_frame_builder.py:639-648`) calls `compute.compute(ind_type, ..., **params)` where `params` comes from YAML spec. YAML params only contain `anchor_source`, never `swing_high_version`/`swing_low_version` dicts. So `_get_dict_val()` always returns `-1`, and `IncrementalAnchoredVWAP._last_swing_high_ver` stays at `-1`. The guard `self._last_swing_high_ver >= 0` is never true, so the batch-computed anchored VWAP is purely cumulative (never resets). These stale values are written to FeedStore during batch pre-computation.
- [OK] **Stale batch values are never consumed for rule evaluation.** The engine overwrites FeedStore values bar-by-bar in `_update_anchored_vwap()` (`play_engine.py:1083-1089`). During warmup bars, `_is_ready()` returns False (`play_engine.py:426`), so rules are never evaluated against stale values. After warmup, every bar gets overwritten before snapshot building.
- [EDGE] **Parity audits would fail.** Any audit comparing batch-computed values vs engine-computed values would see divergence: batch always cumulative, engine resets at swing pivots. The `audit_incremental_parity.py` and `audit_math_parity.py` tools would report false failures for anchored_vwap. This should be documented or the audit should exclude anchored_vwap.

### 4.15 Live Mode Race Condition Analysis

- [OK] **No race condition possible.** The live runner processes candles sequentially via an async queue:
  1. `_on_kline_update()` enqueues `(candle, timeframe)` into `_candle_queue` (`live_runner.py:577`)
  2. `_process_loop()` dequeues one at a time via `_wait_for_candle()` (`live_runner.py:617`)
  3. `_process_candle()` calls `data_provider.on_candle_close()` then `engine.process_bar()` sequentially (`live_runner.py:756,794`)
  4. Inside `process_bar()`, `_update_incremental_state()` calls `update_exec()` then `_update_anchored_vwap()` in the same synchronous call chain (`play_engine.py:998-1001`)
  5. All structure updates and version reads happen in the same async task, sequentially. No concurrent access.

### 4.16 Edge Case: Structures Only on high_tf (No Exec Structures)

- [OK] **Handled gracefully.** If the play declares structures only on `high_tf` and none on exec TF, `_incremental_state.exec.list_structures()` returns an empty list (`play_engine.py:1033`). The loop finds no swing detector, `swing_key` stays None, and anchored VWAP degrades to cumulative (same as section 4.9). The engine does not crash.

### 4.17 Summary of Issues

| # | Severity | Issue | File:Line |
|---|----------|-------|-----------|
| 1 | BUG | `IncrementalSwing` has no `reset()` -- stale state if detectors reused | **FIXED** `swing.py:1085-1139` |
| 2 | BUG | `IncrementalSwing` has no `to_dict()` -- crash recovery loses all swing state including versions | **FIXED** `swing.py:1141-1198` |
| 3 | EDGE | Anchored VWAP without swing structure silently degrades to cumulative VWAP | **FIXED** `play_engine.py:1039-1044` (WARNING log) |
| 4 | EDGE | Anchored VWAP on non-exec TF cannot wire to non-exec swing structure | `play_engine.py:1033` |
| 5 | EDGE | Batch pre-computation never receives swing versions -- produces stale cumulative values | `feature_frame_builder.py:639-648` |
| 6 | EDGE | Parity audits would report false failures for anchored_vwap (batch vs engine divergence) | `audit_incremental_parity.py` |
| 7 | DESIGN | Multiple swing structures: first wins, no way to select | `play_engine.py:1036` |
| 8 | DESIGN | Non-swing structure detectors still missing `reset()` / `to_dict()` -- systemic gap | `trend.py`, `zone.py`, `fibonacci.py`, `derived_zone.py`, `rolling_window.py`, `market_structure.py` |

## 3. Live/Demo Incremental Path

Audit of the VWAP/Anchored-VWAP live/demo code path.
Files: `src/engine/adapters/live.py`, `src/engine/play_engine.py`, `src/engine/runners/live_runner.py`.

### 3.1 LiveIndicatorCache.initialize_from_history() (live.py:91-201)

- [OK] **anchored_vwap skipped correctly** (live.py:143-146): When `ind_type == "anchored_vwap"`, a NaN array is allocated and the key is added to `_engine_managed_keys`. The incremental instance is NOT created here -- engine manages it via `_update_anchored_vwap()`.

- [OK] **Standard VWAP classified as incremental** (live.py:138): `supports_incremental("vwap")` returns True, so it enters the incremental warmup path rather than falling back to vectorized.

- [FIXED] **CRITICAL: ts_open not passed during warmup** (live.py:167-176): Was: warmup loop never passed `ts_open`. Now: timestamps are extracted during array init (`self._ts_open_ms` array, `live.py:117-129`) and passed via `kwargs["ts_open"] = int(self._ts_open_ms[i])` during warmup (`live.py:183-185`). Session resets now fire correctly during warmup.

- [EDGE] **BarRecord.timestamp used as both ts_open and ts_close** (live.py:881-889): When converting BarRecords to Candles for the buffer, `ts_open=bar_record.timestamp` and `ts_close=bar_record.timestamp`. This is documented as "Approximate" but means any downstream code relying on `ts_open` for session boundary detection would get the bar open time correctly. However, the warmup loop (live.py:167-176) doesn't access the candle objects -- it uses the extracted float arrays, losing timestamp information entirely.

### 3.1b _engine_managed_keys Initialization and Buffer Sync (live.py:79)

- [OK] **Correctly initialized as empty set** (live.py:79): `self._engine_managed_keys: set[str] = set()`. Populated only in `initialize_from_history()` when `anchored_vwap` features are found (live.py:145).

- [OK] **anchored_vwap: NaN array allocated, no incremental instance created** (live.py:143-146): For `anchored_vwap`, only `self._indicators[feature.output_key] = np.full(n, np.nan)` is set. No entry in `self._incremental` dict. Engine creates its own `IncrementalAnchoredVWAP` instances in `_init_anchored_vwap_cache()` (play_engine.py:1014-1039). Correct separation of concerns.

- [OK] **NaN append ordering vs trim is correct** (live.py:253-313): In `update()`, the sequence is: (1) OHLCV append (lines 253-257, length K->K+1), (2) trim all arrays including `_indicators` if K+1 > buffer_size (lines 260-270, indicator arrays go from K to buffer_size-1), (3) incremental indicators append new value (lines 300-307, length buffer_size-1 -> buffer_size), (4) engine-managed NaN append (lines 311-313, length buffer_size-1 -> buffer_size). After `update()` all arrays are exactly `buffer_size`. OHLCV and indicator arrays stay in sync.

- [OK] **Engine-managed keys trimmed correctly** (live.py:269-270): The trim loop iterates `for name in self._indicators` which includes engine-managed keys (they're in `_indicators` dict). So anchored_vwap arrays are trimmed alongside all other indicator arrays. Correct.

### 3.2 LiveIndicatorCache.update() (live.py:243-317)

- [FIXED] **CRITICAL: ts_open not passed during live updates** (live.py:293-303): Was: `update()` never passed `ts_open`. Now: `kwargs["ts_open"] = int(candle.ts_open.timestamp() * 1000)` when `candle.ts_open is not None`. Standard VWAP session resets now fire correctly in live mode.

- [OK] **Engine-managed keys get NaN placeholder** (live.py:309-313): For anchored_vwap, a NaN is appended during `update()`, which the engine later overwrites in `_update_anchored_vwap()`. Correct design.

- [OK] **Thread safety** (live.py:251): All mutations in `update()` are under `self._lock`. Correct.

- [EDGE] **Buffer trimming trims indicators too** (live.py:269-270): When the OHLCV arrays are trimmed to `_buffer_size`, indicator arrays are also trimmed. For VWAP, this means the stored array only has the most recent N values, but the internal `_cum_tp_vol` and `_cum_vol` accumulations in `IncrementalVWAP` are NOT trimmed. The instance keeps accumulating. This is correct behavior for VWAP (it should accumulate from session start, not from buffer start), but the stored array values will be inconsistent with a fresh vectorized recompute on the trimmed data.

### 3.3 PlayEngine._update_anchored_vwap() -- Live Path (play_engine.py:1041-1097)

- [OK] **No deadlock risk** (play_engine.py:1095, live.py:251): `_update_anchored_vwap()` acquires `cache._lock` (play_engine.py:1095) but it is called from `process_bar()` which runs AFTER `data_provider.on_candle_close()` in the async event loop. The `on_candle_close()` -> `indicator_cache.update()` call releases `_lock` before `process_bar()` is called. Both happen sequentially in the same async task (live_runner.py `_process_candle()`), so no deadlock.

- [OK] **Writes correct value to cache[-1]** (play_engine.py:1096-1097): `cache._indicators[name][-1] = value` overwrites the NaN placeholder that `update()` appended. Correct.

- [EDGE] **During warmup, anchored VWAP still runs** (play_engine.py:960-1001): `_update_incremental_state()` is called at play_engine.py:423, BEFORE the `_is_ready()` check at line 426. This means `_update_anchored_vwap()` runs for every bar including warmup bars. This is correct -- the indicator needs warmup data too. But if `_incremental_state` has no swing structures initialized yet (structures need warmup bars), the swing versions will be -1 and no anchor resets will fire. This is acceptable.

### 3.4 LiveRunner Candle Flow (live_runner.py)

- [OK] **Correct processing order** (live_runner.py:753-794): The flow is:
  1. `data_provider.on_candle_close(candle, timeframe=timeframe)` -- updates buffer, indicators, structures (live_runner.py:756)
  2. Non-exec TF candles return early after step 1 (live_runner.py:759-761)
  3. For exec TF candles: `engine.process_bar(-1)` -- evaluates rules (live_runner.py:794)
  This ensures indicators and structures are up-to-date before signal evaluation.

- [OK] **Non-exec TF candles update indicators only** (live_runner.py:759-761): Correct -- only exec TF candles trigger signal evaluation.

- [OK] **Engine processes bar -1 for latest** (live_runner.py:794): The engine uses `bar_index=-1` for live mode, which resolves to the latest bar in all data access.

### 3.5 Multi-TF Index Tracking (play_engine.py:842-884)

- [OK] **Live TF index tracking uses buffer lengths** (play_engine.py:842-884): `_update_live_tf_indices()` correctly detects new bars by comparing current buffer length with previous length. When a new med_tf/high_tf bar closes, it calls `_update_med_tf_incremental_state()` / `_update_high_tf_incremental_state()` for structure updates.

- [EDGE] **First-call initialization** (play_engine.py:858-862): On first call, initializes `_prev_med_tf_len` from current buffer length. If the first exec TF candle arrives before any med_tf candle, `_prev_med_tf_len` stays 0 and the first med_tf bar won't be detected as "changed" until a second med_tf bar arrives. This is a minor warmup timing edge case.

### 3.6 Summary of Critical Findings

| # | Severity | Issue | Status |
|---|----------|-------|--------|
| 1 | **CRITICAL** | Standard VWAP `ts_open` never passed in `LiveIndicatorCache.update()` | **FIXED** |
| 2 | **CRITICAL** | Standard VWAP `ts_open` never passed in `initialize_from_history()` warmup | **FIXED** |
| 3 | EDGE | Buffer trim doesn't affect VWAP internal state (cumulative sums keep growing) | Acceptable |
| 4 | EDGE | Warmup BarRecord.timestamp set as both ts_open and ts_close -- approximate | Acceptable |

### 3.7 Proposed Fix for ts_open Bug

The fix needs two changes:

**A. `LiveIndicatorCache.update()` (live.py ~line 284):**
For `requires_hlc` indicators, also pass `ts_open` from the candle:
```python
if info.requires_hlc:
    kwargs: dict = dict(
        high=float(candle.high),
        low=float(candle.low),
        close=float(candle.close),
    )
    if info.requires_volume:
        kwargs["volume"] = float(candle.volume)
    # Pass ts_open for session-boundary indicators (VWAP)
    if hasattr(candle, 'ts_open') and candle.ts_open is not None:
        kwargs["ts_open"] = int(candle.ts_open.timestamp() * 1000)
    inc_ind.update(**kwargs)
```

**B. `LiveIndicatorCache.initialize_from_history()` (live.py ~line 167):**
Store timestamps in an array during initialization and pass them during warmup:
```python
# Add ts_open array alongside OHLCV arrays
self._ts_open_ms = np.zeros(n, dtype=np.int64)
for i, candle in enumerate(candles):
    # ... existing OHLCV extraction ...
    ts = getattr(candle, 'timestamp', None) or getattr(candle, 'ts_open', None)
    if ts is not None:
        self._ts_open_ms[i] = int(ts.timestamp() * 1000)

# In warmup loop:
if needs_hlc:
    kwargs = dict(high=..., low=..., close=...)
    if needs_volume:
        kwargs["volume"] = ...
    if self._ts_open_ms[i] > 0:
        kwargs["ts_open"] = int(self._ts_open_ms[i])
    inc_ind.update(**kwargs)
```

Note: Only `IncrementalVWAP` actually reads `ts_open` from kwargs. Other HLC indicators (ATR, Stoch, etc.) accept `**kwargs` and ignore unknown keys, so passing `ts_open` universally is safe.

### 3.8 Snapshot Access for VWAP in Live Mode

- [OK] **FeedStore built from LiveIndicatorCache arrays** (play_engine.py:1361-1375): `_build_live_feed_store()` reads `indicator_cache._indicators` under lock, copies arrays into a `FeedStore.indicators` dict. Length alignment handled: if indicator array matches buffer length, it's copied as-is; if longer, tail-sliced; if shorter, front-padded with NaN. This means the FeedStore indicator dict contains the VWAP array from the cache.

- [OK] **RuntimeSnapshotView reads from FeedStore** (snapshot_view.py:86-102): `exec_ctx.get_indicator(name)` reads `self.feed.indicators[name][self.current_idx]`. For live mode, `current_idx` is the last index in the exec buffer (play_engine.py:1272). This correctly reads the latest VWAP value.

- [OK] **Anchored VWAP value visible in snapshot** (play_engine.py:1096-1097): `_update_anchored_vwap()` writes the corrected value to `cache._indicators[name][-1]` BEFORE `_build_snapshot_view()` is called (process_bar calls `_update_incremental_state` at line 423, then snapshot is built during rule evaluation at line 463). So the snapshot sees the corrected anchored VWAP value, not the NaN placeholder.

- [OK] **NaN for anchored_vwap during warmup is handled gracefully** (snapshot_view.py:100-101): `get_indicator()` returns `None` when the value is NaN. DSL evaluators treat `None` as "indicator not ready" and skip rule evaluation. So the NaN placeholders during warmup don't cause crashes or false signals.

## 5. DSL Evaluation, Multi-TF, and YAML Plays

Audit of how VWAP/Anchored-VWAP features are parsed from YAML, resolved through the DSL
evaluation pipeline, handled in multi-TF scenarios, and tested in validation plays.

Files: `src/backtest/rules/dsl_parser.py`, `src/backtest/rules/evaluation/resolve.py`,
`src/backtest/rules/evaluation/condition_ops.py`, `src/backtest/rules/eval.py`,
`src/backtest/runtime/snapshot_view.py`, `src/backtest/play/play.py`,
`docs/PLAY_DSL_REFERENCE.md`, and all YAML plays referencing VWAP.

### 5.1 DSL Parsing: String-to-FeatureRef Resolution

- [OK] **`_string_to_feature_ref_dict()` handles vwap variants** (`dsl_parser.py:386`): Converts bare strings like `"vwap"`, `"vwap_d"`, `"avwap"` into `{"feature_id": "vwap"}` etc. Handles dotted field syntax (`"vwap.value"`) and bracketed offset syntax (`"vwap[-1]"`) correctly.
- [OK] **`_is_enum_literal()` correctly excludes VWAP strings** (`dsl_parser.py:424`): Checks against known enum values (trend direction, zone status, etc.). `"vwap"`, `"vwap_d"`, `"avwap"` are NOT enum literals, so they are correctly treated as feature references by `_normalize_rhs_for_operator()` when the operator is numeric.
- [OK] **`_normalize_rhs_for_operator()` routes numeric operators correctly** (`dsl_parser.py:473`): For `NUMERIC_OPERATORS` (gt, lt, gte, lte, near_abs, near_pct, eq, ne, cross_above, cross_below), a string RHS is always converted to a feature reference dict. So `["close", ">", "vwap"]` correctly makes `"vwap"` a FeatureRef, not a scalar.

### 5.2 Value Resolution: resolve_ref() and snapshot_view

- [OK] **`resolve_ref()` delegates to `snapshot.get_feature_value()`** (`resolve.py:59-63`): Calls `snapshot.get_feature_value(feature_id=ref.feature_id, field=ref.field, offset=ref.offset)`. The snapshot routes this through the feature registry to find the correct indicator key and TF role.
- [OK] **Declared type lookup for INT coercion** (`resolve.py:66-71`): Uses `snapshot.get_feature_output_type()` to check if the feature's declared type is INT (e.g., `supertrend.direction`). VWAP outputs are declared FLOAT, so no coercion is applied. Correct.
- [OK] **Missing value handling** (`resolve.py:72-74`): `KeyError` or `AttributeError` during lookup returns `RefValue.missing()`. This covers the case where a feature_id is not registered or the indicator buffer is not yet populated.

### 5.3 NaN Handling in Comparisons

- [OK] **Snapshot converts NaN to None** (`snapshot_view.py:800-804`): `get_feature()` checks `np.isnan(val)` and returns `None` when true. This applies to ALL float indicators including VWAP.
- [OK] **resolve_ref() wraps None as RefValue.missing** (`resolve.py:66-71`): `RefValue.from_resolved_with_declared_type(None, ...)` produces a RefValue with `is_missing=True`.
- [OK] **All comparison operators check missing before dispatch** (`condition_ops.py:183-193`): `eval_cond()` checks `lhs_val.is_missing` and `rhs_val.is_missing` before calling `dispatch_operator()`. Returns `EvalResult.failure()` with `reason=ReasonCode.MISSING_VALUE`. No crash, no false signal.
- [OK] **`_check_numeric()` catches NaN that slipped through** (`eval.py:19-26`): Even if somehow a NaN value reaches the operator level (shouldn't happen due to snapshot guard), `_check_numeric()` checks `math.isnan()` and returns failure. Belt-and-suspenders.
- [OK] **Crossover operators check previous bar too** (`condition_ops.py:101-118`): `eval_crossover()` resolves both current and offset=-1 values. If either is missing (including NaN during warmup), returns failure gracefully.

### 5.4 Multi-TF VWAP: Forward-Fill Semantics

- [OK] **TF routing in snapshot_view** (`snapshot_view.py:998-1012`): `get_feature_value()` looks up the feature's TF role from the registry, maps it via `tf_mapping` to resolve which data feed to access. A VWAP feature declared on `med_tf` routes to the med_tf feed store, not exec.
- [OK] **Forward-fill on slower TFs** (`snapshot_view.py:698-804`): `get_feature()` with a non-exec TF role uses `_get_tf_bar_index()` which returns the most recent bar index for that TF as of the current exec bar. Between slower-TF bar closes, the same value is returned (forward-fill behavior). Correct for VWAP -- the med_tf VWAP stays constant until the next med_tf bar closes.
- [EDGE] **Standard VWAP on non-exec TF: session boundary timing** -- If standard VWAP (anchor="D") is on `med_tf` (e.g., 4h), the daily reset fires when the 4h bar crossing midnight closes. Depending on bar alignment, this could be up to 4 hours after the actual session boundary. The VWAP value between midnight and the next 4h close would still accumulate from the previous day. This is inherent to the TF granularity, not a bug, but users should understand that VWAP session resets on non-exec TFs have TF-granularity lag.

### 5.5 near_pct Tolerance Conversion: TWO Code Paths

- [DESIGN] **Dict shorthand path divides by 100** (`play.py:224`): `_convert_shorthand_condition()` converts `["close", "near_pct", "vwap", 5]` to `{"lhs": "close", "op": "near_pct", "rhs": "vwap", "tolerance": 0.05}`. The tolerance `5` is divided by 100 to get `0.05` (ratio). This matches the PLAY_DSL_REFERENCE.md documentation that `3` means 3%.
- [OK] **`eval_near_pct()` expects ratio** (`eval.py:349`): Computes `abs(lhs - rhs) / abs(rhs) <= tolerance`. If tolerance is `0.05`, this correctly checks within 5%.
- [DESIGN] **DSL parser path does NOT divide by 100** (`dsl_parser.py:606`): `parse_condition_shorthand()` handles 4-element near_pct conditions and passes tolerance raw. If a condition is parsed through this path (e.g., from `cases:` format actions), tolerance `5` would mean 500%, not 5%. However, `parse_condition_shorthand` is only called from `_convert_shorthand_condition` and `parse_blocks`, and all current code paths go through `_convert_shorthand_condition` first (which does the /100). The raw parser path is currently unreachable for near_pct with tolerance, but this is fragile -- any future caller of `parse_condition_shorthand()` directly would get wrong tolerance semantics.

### 5.6 anchored_vwap.bars_since_anchor: NOW Accessible in DSL

- [FIXED] **Registry now declares `multi_output: True`** (`indicator_registry.py:554-561`): `anchored_vwap` has `output_keys: ("value", "bars_since_anchor")` and `primary_output: "value"`. The DSL can reference `avwap.bars_since_anchor` which resolves to the INT output. Bare `avwap` resolves to the primary "value" output via the snapshot_view multi-output resolution logic (`snapshot_view.py:999-1008`).
- [FIXED] **Output type declared as INT**: `INDICATOR_OUTPUT_TYPES["anchored_vwap"]["bars_since_anchor"] = FeatureOutputType.INT`. DSL comparisons like `avwap.bars_since_anchor > 5` correctly use integer semantics.
- [FIXED] **Engine writes both outputs**: `_update_anchored_vwap()` now writes to both `{name}_value` and `{name}_bars_since_anchor` expanded keys in FeedStore/LiveIndicatorCache (`play_engine.py:1088-1112`).

### 5.7 Swing high_version / low_version: Accessible but Undocumented

- [OK] **Accessible in DSL**: Swing structures expose `high_version` and `low_version` via `get_output_keys()` (`swing.py:993-994`) and `get_value()` (`swing.py:1042-1044`). The snapshot routes structure field access through `get_structure_value()` (`snapshot_view.py:1020-1060`), which calls `detector.get_value(field)`. So `swing.high_version` and `swing.low_version` are valid DSL references.
- [EDGE] **Undocumented in PLAY_DSL_REFERENCE.md**: The DSL reference (line 237) lists swing outputs as including `version` but does NOT list `high_version` or `low_version`. Users cannot discover these fields from documentation alone. They work if used, but are hidden.

### 5.8 IND_084 Testing Gap -- FIXED

- [FIXED] **IND_084 now tests anchored_vwap in DSL conditions**: `plays/validation/indicators/IND_084_anchored_vwap_long.yml` entry condition now uses `["close", ">", "avwap"]` (tests primary value resolution) and `["avwap.bars_since_anchor", ">", 3]` (tests multi-output INT field access). Validated: 39 trades on synthetic data, confirming both conditions evaluate correctly.

### 5.9 YAML Play Review

| Play | VWAP Type | TF | DSL Operators | Notes |
|------|-----------|----|---------------|-------|
| `scalper_vwap_rsi_v1.yml` | vwap | exec (5m) | `>`, `<` | Basic above/below checks |
| `scalper_vwap_rsi_v2.yml` | vwap | exec (5m) | `>`, `<` | Same as v1, different RSI params |
| `scalper_vwap_rsi_v3.yml` | vwap | exec (5m) | `>`, `<` | Same pattern, tighter stops |
| `scalper_vwap_rsi_v4.yml` | vwap | exec (5m) | `>`, `<`, `near_pct` (0.5) | Only play using near_pct with VWAP |
| `IND_030_vwap_above_long.yml` | vwap_d (anchor:D) | exec | `>` | Tests daily-anchored VWAP |
| `IND_084_anchored_vwap_long.yml` | avwap | exec | *none* | Does NOT reference avwap in conditions |
| `RV_005_btc_accum_vwap_obv_cmf.yml` | vwap | exec (1h) | `near_pct` (5) | Real data, tolerance=5% |
| `RV_022_sol_markup_vwap.yml` | vwap | exec (1h) | `near_pct` (3) | Real data, tolerance=3% |

- [OK] All plays use VWAP on exec TF only. No plays test VWAP on non-exec TF (med_tf or high_tf).
- [OK] near_pct tolerances (0.5, 3, 5) are all in the YAML percentage convention, correctly converted by play.py.
- [EDGE] **No crossover tests**: No play uses `cross_above` or `cross_below` with VWAP. This operator path is untested for VWAP (though tested for other indicators).

### 5.10 Test Coverage Gaps

1. **No anchored_vwap DSL access test**: IND_084 is the only anchored_vwap play but doesn't use it in conditions.
2. **No non-exec TF VWAP test**: All plays declare VWAP on exec TF. Multi-TF forward-fill behavior for VWAP is untested.
3. **No crossover with VWAP test**: `cross_above(close, vwap)` / `cross_below(close, vwap)` never tested.
4. **No `avwap.bars_since_anchor` test**: Field is inaccessible (registry limitation) and no play attempts it.
5. **No `swing.high_version` / `swing.low_version` test**: Fields work but no play references them.
6. **No near_pct with anchored_vwap test**: Only standard VWAP tested with near_pct.

### 5.11 Summary

| # | Severity | Issue | File:Line |
|---|----------|-------|-----------|
| 1 | DESIGN | `near_pct` tolerance has two conversion paths -- play.py divides by 100, dsl_parser.py does not. Currently safe (all paths go through play.py first) but fragile for future callers. | `play.py:224`, `dsl_parser.py:606` |
| 2 | DESIGN | `anchored_vwap.bars_since_anchor` not accessible in DSL | **FIXED** - registry now `multi_output: True` (`indicator_registry.py:554-561`) |
| 3 | EDGE | `swing.high_version` and `swing.low_version` accessible but undocumented in DSL reference. | `PLAY_DSL_REFERENCE.md:237` |
| 4 | EDGE | IND_084 does not test anchored_vwap in DSL conditions | **FIXED** - play now tests `close > avwap` and `avwap.bars_since_anchor > 3` |
| 5 | EDGE | No plays test VWAP on non-exec TF (med_tf / high_tf). Forward-fill behavior untested. | All VWAP plays |
| 6 | EDGE | No plays test crossover operators with VWAP. | All VWAP plays |
| 7 | EDGE | Standard VWAP on non-exec TF has TF-granularity lag for session boundary resets. | `snapshot_view.py:698-804` |
| 8 | EDGE | No near_pct test with anchored_vwap. | All VWAP plays |
