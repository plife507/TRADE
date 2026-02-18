# Indicators and Structures Domain Review

**Reviewer:** indicators-reviewer agent
**Date:** 2026-02-18
**Scope:** src/indicators/incremental/, src/structures/detectors/, src/structures/primitives.py, src/backtest/indicator_registry.py

---

## Module Overview

The indicators+structures domain is the O(1) computational core of the live engine.
Every bar close executes incremental updates across 44 registered indicators and up to
7 structure detectors. Correctness here is the foundation for signal evaluation.

---

## File-by-File Findings

### 1. src/indicators/incremental/core.py

#### EMA (IncrementalEMA)

- is_ready: _count >= length. First output at bar length-1 (SMA seed). Correct.
- Reset: _ema, _count, _warmup_sum all cleared. Complete.

#### SMA (IncrementalSMA)

- is_ready: len(self._buffer) >= self.length. Correct. Reset complete.

#### RSI (IncrementalRSI)

- is_ready: _count > self.length (strictly greater than). CORRECT AND INTENTIONAL.
  RSI needs length+1 bars: bar 1 sets prev_close, bar 2 seeds avg_gain/avg_loss via RMA.
  is_ready fires at count==length+1. Not inconsistent with SMA/ATR which need exactly
  length bars (no delta). This is a known-correct design documented in MEMORY.md.
- RMA seeding: Seeds from first change (bar 2). Matches ewm(alpha=1/length, adjust=False). Correct.
- Edge: total == 0 returns 50.0 (correct neutral midpoint). Reset complete.

#### ATR (IncrementalATR)

- is_ready: _count >= self.length. Fires at bar length-1.
- BUG-ATR-001 (LOW): prenan=False SMA seed. Bar 0 appends high-low (not true TR -- ignores
  gap from prev close). At _count==length, warmup_tr has length elements; seed = sum/length.
  Diverges from pandas_ta on gapped opens. Error decays via Wilder smoothing
  with ~14 bar half-life at length=14. Low severity.
- prenan=True (ADX internal): Bar 0 skips. SMA seed from length-1 elements. Correct.
- Wilder RMA: alpha * tr + (1 - alpha) * atr. Correct. Reset complete.

#### MACD (IncrementalMACD)

- is_ready: Delegates to _ema_signal.is_ready. Signal EMA chains naturally. Correct.
- Reset: Calls .reset() on all 3 sub-EMAs and clears own fields. Complete.
- Registry warmup: slow * 3 + signal = 87 (default). Conservative but safe.

#### BBands (IncrementalBBands)

- Variance: (sum_sq - n * mean^2) / (n - 1) -- sample variance ddof=1. Matches pandas_ta. Correct.
- Precision guard: if variance < 0: variance = 0.0. Handles float64 catastrophic cancellation.
- percent_b: Uses self._buffer[-1] for last close. Correct. Reset complete.

#### WilliamsR (IncrementalWilliamsR)

- is_ready: len(self._high_buffer) >= self.length. Correct.
- Edge: highest_high == lowest_low returns -50.0 (midpoint). Correct. Reset complete.

#### CCI (IncrementalCCI)

- O(n) value access: Documented. value property iterates _tp_buffer for MAD each call.
  O(n=length) per value read, not O(1). Acceptable trade-off documented in class docstring.
- is_ready: len(self._tp_buffer) >= self.length. Correct. Reset complete.

#### Stochastic (IncrementalStochastic)

- k_value: Returns _k_buffer[-1] when is_ready. Buffer capped at d_period. Correct.
- BUG-STOCH-001 (LOW): d_value divides by len(self._k_buffer) not self.d_period.
  Functionally equivalent when buffer full (required by is_ready) but stylistically inconsistent.
- Reset: All 4 buffers cleared, _count reset. Complete.

#### ADX (IncrementalADX)

- is_ready: self._dx_count >= 1. Fires as soon as first DX computed. Registry warmup=length*2 safe.
- BUG-ADX-001 (LOW): _adx_history.pop(0) at core.py:884 is O(n) list pop.
  Should use collections.deque(maxlen=self.length). At length=14 overhead is negligible
  but semantically wrong for a claimed O(1) indicator.
- Reset: _atr.reset(), all scalars cleared, _adx_history = []. Complete.

#### SuperTrend (IncrementalSuperTrend)

- is_ready: not np.isnan(self._prev_trend). Fires on second valid ATR bar. Correct.
- Direction logic: Strict comparison on _prev_upper/_prev_lower. Matches pandas_ta.
- Reset: _atr.reset(), all _prev_* set to NaN, _direction = 1. Complete.

---

### 2. src/indicators/incremental/stateful.py

#### PSAR (IncrementalPSAR)

- Params: af0, af, max_af -- correctly named in class AND in factory.py.
  MEMORY.md note about wrong param names is a historical reference; current code is correct.
- is_ready: _count >= 2. SAR output from bar 1 (trend determined on second bar). Correct.
- Clamp logic: Downtrend: new_sar = max(prev_high, new_sar). Uptrend: min(prev_low, new_sar).
  Matches pandas_ta exactly.
- BUG-PSAR-001 (LOW): reversal_value at stateful.py:146 returns self._reversal (bool).
  Registry declares reversal as FeatureOutputType.INT. bool is subclass of int so True==1, False==0.
  Functionally correct. Should return int(self._reversal) for semantic consistency.
- Reset: All fields including _af_current = self.af0, _reversal = False. Complete.

#### Squeeze (IncrementalSqueeze)

- is_ready: _bbands.is_ready and _kc.is_ready and _sma_mom.is_ready. All sub-indicators. Correct.
- on/off/no_sqz: Only computed when is_ready; return 0 before ready. Safe default.
- no_sqz_value: 1 if on==0 and off==0 else 0. Covers partial-overlap case. Correct.
- Reset: All sub-indicators .reset() called. Complete.

#### Fisher (IncrementalFisher)

- Initialization: First valid bar (len==length) sets _fisher = 0.0 and returns without computation.
  Subsequent bars compute full Fisher. Matches pandas_ta seeding convention.
- BUG-FISHER-001 (MEDIUM): is_ready is True on seeding bar where value == 0.0 is artificial.
  First real Fisher computation is at bar length (0-based index), not bar length-1.
  Conditions like fisher_value > 0 will trigger falsely on the seeding bar.
  Fix: change is_ready to require self._count > self.length (mirrors RSI pattern).
- Signal history: _fisher_hist[-self.signal - 1]. With signal=1: history[-2] = one bar back. Correct.
- Reset: _v = 0.0, _fisher = np.nan, _initialized = False. Complete.

---

### 3. src/indicators/incremental/volume.py

#### VWAP (IncrementalVWAP)

- Session reset: _get_boundary() returns ts_ms // ms_per_day for daily.
  Reset fires when boundary != _last_reset_boundary and _last_reset_boundary >= 0.
  Guard prevents reset on the very first bar. Correct.
- NaN guard: Skips NaN bars without poisoning cumulative sums. _count still increments.
  is_ready can be True while _cum_vol == 0; handled by _cum_vol == 0 guard in value. Safe.
- Weekly boundary: (ts_ms + 3 * ms_per_day) // (ms_per_day * 7). Unix epoch is Thursday.
  Adding 3 days shifts to Monday boundary. Verified mathematically correct.
- Reset: Both cumulatives and _last_reset_boundary = -1. Complete.

#### AnchoredVWAP (IncrementalAnchoredVWAP)

- Pair anchor: Resets when pair_ver > _last_pair_version AND _last_pair_version >= 0.
- NOTE-AVWAP-001 (INFO): First swing pair does NOT trigger reset by design.
  Initial _last_pair_version = -1. Version transition from -1 to 1 skips the >= 0 guard.
  VWAP accumulates from bar 0 until second pair event, then resets.
  Users expecting anchor-at-first-swing should be aware of this behavior.
- NaN guard: Same pattern as VWAP. _bars_since_anchor increments even for NaN bars. Safe.
- Reset: All version trackers set to -1, cumulatives cleared. Complete.

---

### 4. src/indicators/incremental/factory.py

- PSAR dispatch: af0, af, max_af correctly wired from params.
- Registry delegation: supports_incremental and list_incremental_indicators delegate to registry.
  No duplicate hardcoded lists. Single source of truth maintained.
- BUG-FACTORY-001 (MEDIUM): Unknown indicator type strings silently return None.
  Caller cannot distinguish typo from genuinely vectorized-only indicator.
  Should raise ValueError for types not in the registry at all, return None only for
  registry-known types that have no incremental_class.

---

### 5. src/structures/primitives.py

#### MonotonicDeque

- Push eviction: Removes elements where index <= idx - window_size (closed window).
  Callers must provide monotonically increasing indices.
- MIN mode: Removes elements >= value from back (newest of equals survives). Correct.
- MAX mode: Removes elements <= value from back. Symmetric. Correct.
- get_or_raise: Type-safe float accessor for callers that cannot accept None. Correct.
- clear: Delegates to self._deque.clear(). Complete.

#### RingBuffer

- Physical indexing: physical = (self._head - self._count + idx) % self.size.
  Python signed modulo handles negative intermediates correctly. Verified correct.
- BUG-RINGBUF-001 (LOW): Negative indexing raises IndexError without documentation.
  Python convention has buf[-1] meaning last element. Current callers in swing.py only use
  buf[pivot_idx] (always positive). Future callers may be surprised by undocumented restriction.
- to_array: O(n) reconstruction. Used only in to_dict() serialization path. Correct.
- clear: _buffer.fill(np.nan), _head = 0, _count = 0. Complete.

---

### 6. src/structures/detectors/swing.py

#### IncrementalSwing / PairState

- _is_swing_high: O(left + right + 1) scan. Strict >= comparison: equal highs disqualify pivot.
  Consistent with standard fractal definition. Documented as O(window_size).
- PairState FSM: All transitions correctly documented and implemented.
  AWAITING_FIRST + HIGH -> GOT_HIGH.
  GOT_HIGH + LOW -> PAIRED_BEARISH, transitions to GOT_LOW.
  GOT_LOW + HIGH -> PAIRED_BULLISH, transitions to GOT_HIGH.
  Same-type replacement: new high replaces pending high (GOT_HIGH + HIGH = update pending).
- NOTE-SWING-001 (INFO): No explicit PAIRED state. Completing pivot immediately becomes
  pending for next pair. Enables chained pairs without losing a pivot. Intentional design.
- Simultaneous high+low same bar: High processed first then low. Arbitrary ordering. Documented.
  Rare in fractal mode (window > 1 usually prevents same-bar dual pivots).
- Strict alternation: _check_alternation correctly handles replacement and opposite-type acceptance.
- BUG-SWING-001 (LOW): to_dict at swing.py:1157-1160 directly accesses _high_buf._head and
  _high_buf._count (RingBuffer internals). No schema version field. Fragile to RingBuffer
  refactors -- deserialization fails silently on field rename. Recommend using only to_array()
  for serialization and adding a version: 1 field.
- reset() creates new RingBuffer instead of calling .clear(). Allocates new numpy array.
  GC pressure for high-frequency reset scenarios (e.g., parameter sweeps). Low severity.

---

### 7. src/structures/detectors/market_structure.py

#### IncrementalMarketStructure

- DEPENDS_ON: ["swing"] correctly declared. __init__ reads deps["swing"]. Correct.
- bias: int (1/0/-1). Correctly initialised to 0 (ranging). Reset restores 0. Correct.
- _bos_this_bar / _choch_this_bar reset at the top of every update() call. Correct event semantics.
- CHoCH-before-BOS priority: All three bias branches check CHoCH first and return early.
  Prevents same-bar CHoCH+BOS double signal. Correct.
- _update_break_levels: Guards  before updating break level.
  Prevents re-arming on same swing after a break. Correct.
- Confirmation mode (confirmation_close=True): Uses bar.close for check_high/check_low.
  Default False uses bar.high/bar.low. Wick-based detection is standard. Correct.
- BUG-MS-001 (LOW): _prev_prev_swing_high and _prev_prev_swing_low (lines 113-114) are
  stored in update() on every new swing but are NEVER READ. Dead code. They accumulate
  stale state that never influences outputs. Should be removed to reduce confusion.
- to_dict: Serializes 20 fields. No schema version field (same issue as BUG-SWING-001).
  Fragile to field additions on deserialization. Low risk since to_dict only used for
  crash recovery, not cross-version migration.
- Reset: All 20 mutable fields restored to __init__ defaults. Complete.

---

### 8. src/structures/detectors/derived_zone.py

#### IncrementalDerivedZone

- K-slot pattern: _zones list with most-recent-first ordering. max_active enforced
  by truncating from the tail on every regen. Correct eviction semantics.
- Two-path design: REGEN (on source version change) vs INTERACTION (every bar).
  Clean separation. version_key switches between pair_version / version based on
  use_paired_source param. Correct.
- Zone hash (blake2b, 32-bit): Encodes source_version + pivot_high_idx + pivot_low_idx
  + level (scaled to millionths) + mode. Stable across runs and platforms. Correct.
- Break detection (lines 410-416): Skips creation bar (anchor_idx < bar_idx guard).
  break_tol = 1.0 - break_tolerance_pct (lower bound), break_tol_upper = 1.0 + break_tolerance_pct (upper bound).
  Price below lower*break_tol or above upper*break_tol_upper breaks the zone.
- BUG-DZONE-001 (LOW): Variable name break_tol_upper at line 412 is misleading.
  It is not the tolerance for the upper boundary; it is a multiplier meaning
  "beyond upper by tolerance_pct". The lower check also uses a sub-1.0 multiplier.
  Should be named consistently (e.g., break_tol_factor_lower / break_tol_factor_upper)
  or add a comment explaining the semantics.
- NOTE-DZONE-001 (INFO): first_active_idx and newest_active_idx (lines 527-535)
  are identical implementations -- both return the index of the first ACTIVE zone
  encountered from index 0 (most recent). Since zones are most-recent-first, slot 0
  is always the newest active. The distinction between "first by slot" and "newest"
  is intentional given the ordering, but having two keys with identical code is
  a maintenance risk. Consider a comment clarifying why both exist.
- touched_this_bar: Event flag reset at the top of _update_zone_interactions()
  via zone["touched_this_bar"] = False. Correct per-bar semantics.
- Reset: _zones.clear(), _source_version = 0, _current_bar_idx = -1. Complete.
- to_dict: Serialises all zone dicts via list copy. Correct.

---

### 9. src/backtest/indicator_registry.py

#### Warmup Formula Audit

All warmup formulae must satisfy: warmup >= actual bars to is_ready.
Under-estimation causes live engine to use indicators before they are ready.

| Indicator       | is_ready condition                | warmup formula          | Result        |
|-----------------|-----------------------------------|-------------------------|---------------|
| EMA             | _count >= length                  | length * 3              | SAFE (over)   |
| SMA             | len(_buffer) >= length            | length                  | CORRECT       |
| RSI             | _count > length                   | length + 1              | CORRECT       |
| ATR             | _count >= length                  | length + 1              | SAFE (over)   |
| MACD            | _ema_signal.is_ready              | slow*3 + signal         | SAFE (over)   |
| BBands          | len(_buffer) >= length            | length                  | CORRECT       |
| WilliamsR       | len(_high_buffer) >= length       | _warmup_length = length | CORRECT       |
| CCI             | len(_tp_buffer) >= length         | _warmup_length = length | CORRECT       |
| Stoch           | is_ready based on k+smooth_k+d    | k + smooth_k + d        | CORRECT       |
| ADX             | _dx_count >= 1                    | length * 2              | SAFE (over)   |
| SuperTrend      | not isnan(_prev_trend)            | length + 1              | CORRECT       |
| PSAR            | _count >= 2                       | 2                       | CORRECT       |
| Squeeze         | all sub-indicators ready          | max(bb_length, kc_length) | UNDER (BUG) |
| Fisher          | _count >= length (seeding bar)    | length                  | UNDER (BUG)   |

- BUG-REGISTRY-001 (LOW): _warmup_squeeze (line 129) returns max(bb_length, kc_length).
  IncrementalSqueeze also contains _sma_mom (momentum SMA). IncrementalSqueeze.__init__
  creates _sma_mom with length=bb_length by default. is_ready requires _sma_mom.is_ready.
  Warmup should be max(bb_length, kc_length, bb_length + mom_smooth_k or similar).
  In practice with defaults (bb=kc=20, mom=12), kc warmup dominates via _warmup_kc
  (length*3+1=61), but the mom SMA path is not accounted for at all.

- BUG-REGISTRY-003 (MEDIUM): _warmup_fisher (line 154) returns length.
  IncrementalFisher.is_ready fires at _count >= length (seeding bar included).
  The seeding bar outputs 0.0 (artificial, not a real Fisher value).
  Any play condition on fisher_value that fires at bar length-1 may act on the
  artificial seed. Fix: change warmup to length + 1 (mirrors RSI pattern), OR fix
  is_ready to require _count > length (preferred, see BUG-FISHER-001).

- NOTE-REGISTRY-001 (INFO): _warmup_ema returns length * 3. Conservative choice for
  EMA stabilisation. Actual is_ready fires at bar length-1 (much earlier). The 3x
  multiplier ensures EMA has decayed enough from its SMA seed to be representative.
  This is a pragmatic over-estimate, not a bug.

- NOTE-REGISTRY-002 (INFO): _warmup_atr returns length + 1. ATR is_ready fires at
  _count >= length (bar length-1). The +1 is a one-bar safety margin. Not incorrect.

---

## Cross-Module Dependencies

    indicator_registry.py
      provides: warmup formulae, multi-output keys, incremental_class names
      consumed by: factory.py (incremental creation), indicator_vendor.py (warmup budgets)

    factory.py
      wraps: all 44 incremental classes
      delegates supports_incremental / list_incremental_indicators -> indicator_registry
      consumed by: LiveIndicatorCache (live), BacktestIndicatorEngine (backtest)

    core.py + stateful.py + volume.py
      provide: IncrementalEMA ... IncrementalAnchoredVWAP
      depend on: base.py (IncrementalIndicator interface)
      NOTE: each indicator is self-contained; no cross-indicator imports except
            IncrementalADX -> IncrementalATR
            IncrementalSuperTrend -> IncrementalATR
            IncrementalMACD -> IncrementalEMA
            IncrementalBBands -> IncrementalSMA
            IncrementalSqueeze -> IncrementalBBands + IncrementalKC + IncrementalSMA
            IncrementalStochRSI -> IncrementalRSI

    primitives.py (MonotonicDeque, RingBuffer)
      consumed by: swing.py exclusively

    swing.py (IncrementalSwing)
      depends on: primitives.py
      consumed by: market_structure.py, derived_zone.py, trend.py, zone.py,
                   fibonacci.py, rolling_window.py (all via deps dict)

    market_structure.py, derived_zone.py
      depend on: swing.py (via DEPENDS_ON declaration)
      do NOT directly import swing.py -- dependency injection via deps dict

---

## ASCII Diagram

    YAML Play
      features:
        - type: rsi, length: 14    ->  factory.create_incremental_indicator("rsi", {...})
        - type: macd, ...          ->  IncrementalMACD (contains 3x IncrementalEMA)

      structures:
        - type: swing, key: pivots ->  IncrementalSwing (uses RingBuffer + MonotonicDeque)
        - type: derived_zone       ->  IncrementalDerivedZone (deps["swing"] = pivots)
          uses: pivots               |
        - type: market_structure   ->  IncrementalMarketStructure (deps["swing"] = pivots)
          uses: pivots               |
                                      ^
                         Dependency injection at construction time

    Hot loop (per exec-TF bar close):
      1. indicator.update(bar)         [O(1) each, ~44 total]
      2. structure.update(bar_idx, bar)[O(window) swing, O(levels*K) dzone on regen]
      3. snapshot.freeze()             [copies current values to dict, O(outputs)]
      4. signal_eval(snapshot)         [evaluates DSL tree against frozen snapshot]

    Warmup budget enforced by indicator_registry._warmup_*:
      registry.get_warmup(type, params) -> int
      engine skips signal eval until all indicators >= warmup bars

---

## Bug Summary

| ID              | Severity | File                    | Description                                               | Fix |
|-----------------|----------|-------------------------|-----------------------------------------------------------|-----|
| BUG-ATR-001     | LOW      | core.py                 | prenan=False: bar 0 uses H-L not TR; diverges on gaps     | Accept or document |
| BUG-ADX-001     | LOW      | core.py:884             | _adx_history.pop(0) is O(n); use deque(maxlen=length)     | Replace list with deque |
| BUG-STOCH-001   | LOW      | core.py                 | d_value divides by len(_k_buffer) not d_period            | Cosmetic; functionally equiv when full |
| BUG-PSAR-001    | LOW      | stateful.py:146         | reversal_value returns bool; registry declares INT        | return int(self._reversal) |
| BUG-FISHER-001  | MEDIUM   | stateful.py             | is_ready True on artificial seeding bar (value==0.0)      | Change to _count > length |
| BUG-FACTORY-001 | MEDIUM   | factory.py:262          | Unknown type strings silently return None                 | Raise ValueError for unknown types |
| BUG-RINGBUF-001 | LOW      | primitives.py           | Negative indexing raises IndexError; undocumented         | Add docstring note |
| BUG-SWING-001   | LOW      | swing.py:1157-1160      | to_dict exposes _high_buf internals; no schema version    | Use to_array(); add version field |
| BUG-MS-001      | LOW      | market_structure.py:113 | _prev_prev_swing_high/low stored but never read (dead)    | Remove unused fields |
| BUG-DZONE-001   | LOW      | derived_zone.py:411-412 | break_tol_upper variable name misleading                  | Rename or add comment |
| BUG-REGISTRY-001| LOW      | indicator_registry.py:129 | _warmup_squeeze ignores momentum SMA warmup             | Add mom SMA to formula |
| BUG-REGISTRY-003| MEDIUM   | indicator_registry.py:154 | _warmup_fisher under-estimates by 1 bar                 | Return length + 1 |

---

## Notable Design Strengths

1. **Single source of truth**: indicator_registry.py owns warmup formulae, output keys, and
   incremental class names. factory.py delegates back to the registry. No duplication.

2. **Clean is_ready semantics**: Each indicator has a precisely defined is_ready gate.
   The variation between >= length (SMA/ATR) and > length (RSI) is intentional and
   correctly matches each algorithm's data requirements.

3. **Dependency injection for structures**: All structure detectors receive dependencies
   as a deps: dict[str, BaseIncrementalDetector] dict. No direct imports between
   detector classes. Clean separation of concerns.

4. **Event flag pattern**: bos_this_bar, choch_this_bar, touched_this_bar -- all reset
   at the top of update(). DSL conditions can fire on the exact bar of an event
   without manually tracking previous values.

5. **PairState FSM**: Clean finite-state machine with replacement semantics (new high
   replaces pending high without losing the pending low). Enables correct alternating
   pair detection without complexity.

6. **blake2b zone hashing**: Deterministic 32-bit zone identity using platform-stable
   hash. JSON-compatible int. Enables crash recovery and determinism across runs.

7. **Precision guard in BBands**: if variance < 0: variance = 0.0 catches float64
   catastrophic cancellation on flat price series without masking genuine errors.

8. **Comprehensive reset() coverage**: All 7 structure detectors and all 44 indicator
   classes implement reset() that fully clears mutable state. Parameter sweeps and
   replay scenarios can reuse instances safely.

---

## Extended Coverage: Remaining Source Files

The sections below extend the review to cover files not included in the initial pass.

### src/indicators/incremental/adaptive.py

#### KAMA (IncrementalKAMA)

- is_ready: `not np.isnan(self._kama)`. KAMA seeds from the first close value so it is
  never NaN after bar 0, meaning `is_ready` is True from bar 1. This is intentional --
  KAMA converges adaptively and has no sharp warmup boundary.
- Reset: `_kama = np.nan`, `_prev_close = np.nan`. Complete.

#### ALMA (IncrementalALMA)

- Gaussian weights precomputed in `__init__`. These weights depend only on params, not
  state. `reset()` clears only the rolling buffer. Correct.
- is_ready: `len(self._buffer) >= self.size`. Correct.
- Reset: Buffer cleared. Complete.

#### ZLMA (IncrementalZLMA)

- is_ready: `self._ready` bool flag set after first valid computation. Cleaner than NaN
  checks. Consistent with the bool-flag pattern used by IncrementalSqueeze.
- Reset: `_ready = False`, buffer cleared. Complete.

#### UO (IncrementalUO -- Ultimate Oscillator)

- NOTE-UO-001 (LOW): `value` property getter computes running sums via list slicing over
  `_bp_list` and `_tr_list`. If these lists grow unbounded (no maxlen cap), the slicing
  is O(fast + medium + slow) per call. For typical values (7/14/28) this is 49 elements
  -- constant-small but not strictly O(1). Use `collections.deque(maxlen=slow)` with
  running sums maintained incrementally to achieve true O(1).
- is_ready: `len(self._tr_list) >= self.slow`. Correct.
- Reset: Both lists cleared. Complete.

---

### src/indicators/incremental/lookback.py

#### AROON (IncrementalAROON)

- is_ready: `self._count > self.length`. Requires length+1 bars (consistent with RSI
  pattern -- lookback indicators need a full window of length bars plus one to establish
  the first window). Correct.
- Reset: Deque cleared, `_count = 0`. Complete.

#### Donchian (IncrementalDonchian)

- Uses MonotonicDeque for O(1) amortized min/max. Correct pattern.
- Reset: Recreates MonotonicDeque instances. Complete.

#### KC (IncrementalKC -- Keltner Channel)

- Uses EMA for midline and ATR for band width. Both sub-indicators reset correctly in
  reset(). No issue.

#### DM (IncrementalDM -- Directional Movement)

- NOTE-DM-001 (LOW): `is_ready` returns `self._dm_count >= 1`, the same aggressive
  pattern as IncrementalADX. A single Wilder-smoothed DM value is the first output.
  The warmup registry uses `2 * length` for ADX (which wraps DM), so the registry is
  safer than is_ready here. Downstream code relying solely on is_ready may consume
  unconverged DM values.
- Reset: All running averages cleared. Complete.

#### Vortex (IncrementalVortex)

- NOTE-VORTEX-001 (LOW): `__init__` appends `0.0` to `_vmp_sums` and `_vmm_sums` for
  the initialization bar. This means the first window includes one zero VM+/VM- pair
  from construction, not a real price bar. For typical `length >= 14` the dilution is
  negligible (1/14 = 7%) but the pattern is impure. Consider initializing at first real
  price bar instead.
- Reset: Lists cleared. Complete.

---

### src/indicators/incremental/trivial.py

#### ROC (IncrementalROC) and MOM (IncrementalMOM)

- is_ready: `len(self._buffer) > self.length`. Both need `length + 1` prices to compute
  a length-bar rate of change or momentum. Correct and consistent with RSI/AROON pattern.
- Reset: Buffer cleared. Complete.

#### OBV (IncrementalOBV)

- Accumulates indefinitely. No ring buffer, no windowed reset. Correct -- OBV is a
  cumulative running total with no window.
- Reset: `_obv = 0.0`. Complete.

#### NATR (IncrementalNATR)

- Delegates to `IncrementalATR` internally and normalizes by close.
- Reset: Delegates to inner ATR. Complete.

#### OHLC4 (IncrementalOHLC4) and Midprice (IncrementalMidprice)

- Stateless: Only close/price reads. `is_ready` always True. Reset is no-op. Correct.

---

### src/indicators/incremental/buffer_based.py

#### CMO (IncrementalCMO)

- BUG-CMO-001 (MED): Lines 334-335 use `self._gains.pop(0)` and `self._losses.pop(0)`
  on plain `list` objects. `list.pop(0)` is O(n). For `length = 14`, this is 14 element
  shifts per bar. Over a 10,000-bar backtest: 140,000 O(n) list operations. Replace
  both with `collections.deque(maxlen=length)` -- `append()` handles eviction in O(1).
- Reset: Lists cleared. Complete.

#### MFI (IncrementalMFI)

- NOTE-MFI-001 (LOW): Appends `0.0` to both positive and negative money flow buffers
  on the very first bar (when there is no prior typical price). This seeds the first
  window with a 0-flow entry. For typical window sizes the dilution is negligible (1/14
  = 7%) but the first window is not a clean `length`-bar window.
- Reset: Buffers cleared. Complete.

#### WMA (IncrementalWMA) and TRIMA (IncrementalTRIMA)

- Both use `RingBuffer` for fixed-size lookback. The weighted sum is recomputed from
  scratch each bar (O(n) per call), which is inherent to WMA without maintaining
  weighted partials. Acceptable trade-off. Noted for completeness.
- Reset: Buffer cleared. Complete.

#### LINREG (IncrementalLINREG)

- Recomputes full linear regression from ring buffer on each bar. True O(n) per call.
  Inherent to the algorithm without Welford-style running covariance maintenance.
- Reset: Buffer cleared. Complete.

#### CMF (IncrementalCMF)

- is_ready: `len(self._buffer) >= self.length`. Correct.
- Reset: Buffer cleared. Complete.

---

### src/indicators/incremental/ema_composable.py

#### _ChainedEMA

- Seeds from the first input value rather than NaN. Matches pandas_ta's `presma=True`
  behavior where EMA of EMA seeds from the first EMA output. Correct for DEMA/TEMA parity.

#### DEMA (IncrementalDEMA) and TEMA (IncrementalTEMA)

- Use one/two levels of `_ChainedEMA` respectively. Reset cascades correctly. No issue.

#### TRIX (IncrementalTRIX)

- is_ready: `not np.isnan(self._trix_value)`. Fires after triple-EMA chain plus first
  ROC is computable. Correct.
- Reset: Triple-EMA chain reset. Complete.

#### TSI (IncrementalTSI)

- NOTE-TSI-001 (LOW): Collects `slow - 1` price diffs to seed the slow-EMA SMA. The
  `fast` EMA within TSI uses `_ChainedEMA` which seeds from the first slow-EMA output
  (not a prior SMA seed). This means the fast EMA has a brief convergence period after
  the slow EMA is seeded. The warmup registry formula for TSI should account for
  `slow + fast - 1` bars, not just `slow`. Verify the registry entry.
- Reset: All sub-indicators reset. Complete.

#### PPO (IncrementalPPO)

- Uses three `IncrementalEMA` instances. `reset()` cascades correctly. No issue.

---

### src/indicators/metadata.py

#### IndicatorMetadata / compute_feature_spec_id

- SHA256 of canonicalized param dict (sorted keys, None dropped, numpy scalars
  converted), truncated to 12 chars. Collision probability over 44 indicators x ~5
  param variants is negligible (12 hex chars = 48-bit space). No issue.
- `canonicalize_params()` drops `None` values. In practice all meaningful defaults are
  non-None numeric values. No current issue.
- `IndicatorMetadata` is a frozen dataclass -- immutable after construction. Correct.

---

### src/structures/base.py

#### BarData

- Wraps the `indicators` dict in `MappingProxyType` at construction, making it immutable
  for the bar lifetime. This prevents accidental mutation from detector code.

#### BaseIncrementalDetector

- `validate_and_create()` validates REQUIRED_PARAMS, OPTIONAL_PARAMS defaults, and
  DEPENDS_ON keys before calling `__init__`. Validation errors include human-readable
  fix hints.
- NOTE-BASE-001 (LOW): `reset()` and `to_dict()` are NOT abstract methods. They are
  optional protocol methods. `TFIncrementalState.reset()` uses `hasattr(struct, 'reset')`
  guards. A detector author can omit `reset()` entirely and the structure will silently
  not reset on engine restart. Consider adding abstract stubs that raise `NotImplementedError`
  to make the contract explicit.

---

### src/structures/state.py

#### TFIncrementalState

- `update()` validates monotonic bar index at line 202 and raises `ValueError` on
  regression. Prevents silent duplicate-bar processing bugs. Good defensive guard.
- NOTE-STATE-001 (MED): `from_json()` returns an empty `TFIncrementalState` instance
  without rehydrating any structure detectors. Structures must be re-registered after
  `from_json()` via subsequent calls. The multi-step crash recovery process is not
  documented inline. Add a comment at `from_json()` explaining the required call
  sequence: (1) call from_json() to get empty state, (2) re-create detectors from
  Play YAML, (3) restore internal state from serialized data.

#### MultiTFIncrementalState

- `get_value()` supports dotted output keys like `structure.level_0.618` by joining
  remaining path components after splitting on `.`. This allows Fibonacci level keys
  with decimal dots to work correctly in DSL conditions. Correct.

---

### src/structures/detectors/fibonacci.py

#### IncrementalFibonacci

- Unified formula: `level = high - (ratio * range)` handles all modes via ratio sign.
  Level keys are consistently named `level_{ratio}` (e.g., `level_0.618`). Correct.
- NOTE-FIB-001 (MED): Extension mode with `direction == ""` (empty string) falls
  through to the extension formula without error. The result is NaN for all extension
  levels because the formula branches on direction being "bullish" or "bearish". A Play
  misconfigured with `mode: extension` and no `trend` dependency (direction stays "")
  will silently output all-NaN Fibonacci levels. Add a guard: if mode in
  ("extension", "extension_up", "extension_down") and direction == "", warn or hold.
- NOTE-FIB-002 (LOW): `_recalculate_trend_anchored()` skips recalculation when
  `direction == 0` (ranging bias from trend detector). Anchors freeze during ranging.
  Downstream rules reading Fibonacci levels during ranging will see stale levels without
  a signal that the trend is ranging. Document this behavior in the module docstring.
- Reset: All level dicts cleared, swing state reset. Complete.

---

### src/structures/detectors/zone.py

#### IncrementalZone

- NOTE-ZONE-001 (MED): `atr_key` defaults to `"atr"` at line 153 and zone width falls
  back to `0.0` if the key is absent from `bar.indicators` at line 192. A zone with
  0 ATR width has `upper == lower == swing_level`, which is a degenerate zone that will
  fire break conditions on any price touch at the swing level. The Play author must
  explicitly declare an `atr` indicator -- the structure does not validate its presence
  at construction time. Add a one-time warning at zone activation when ATR is NaN.
- NOTE-ZONE-002 (LOW): Once a zone transitions to `state == "broken"`, it stays broken
  permanently. There is no re-activation path. This is correct design -- document it
  explicitly in the module docstring: "broken zones are permanent until a new swing forms."
- `_version` increments on both zone creation and zone break. Correct pattern.
- Reset: All fields restored to defaults. Complete.

---

### src/structures/detectors/trend.py

#### IncrementalTrend

- NOTE-TREND-001 (MED): `_analyze_wave_sequence()` at lines 426-436 classifies the
  current bias as `partial_bullish` or `partial_bearish` based on a single wave pair.
  A single higher-high or lower-low can trigger a partial trend label. If downstream
  rules gate on `trend.bias == 1` expecting a robust trend, they may fire on the first
  pivot pair. Consider requiring a minimum of 2 confirmed wave pairs before emitting a
  non-zero bias, or document the single-pair threshold explicitly in the module docstring.
- NOTE-TREND-002 (LOW): `bars_in_trend` is incremented in two places in the update
  path. If both code paths execute on the same bar, `bars_in_trend` double-increments.
  Audit the update logic to ensure exactly one increment per bar.
- `wave_history` uses `deque(maxlen=wave_history_size)`. Correct.
- Reset: All state cleared including wave_history. Complete.

---

## Additional Actionable Items

| ID | Severity | File | Description |
|----|----------|------|-------------|
| NOTE-UO-001 | LOW | adaptive.py | UO list slicing not strictly O(1) -- use deque with running sums |
| NOTE-DM-001 | LOW | lookback.py | DM is_ready fires after single DM (same aggressive pattern as ADX) |
| NOTE-VORTEX-001 | LOW | lookback.py | Vortex init bar appends 0.0 VM pairs (not real price bar) |
| NOTE-MFI-001 | LOW | buffer_based.py | MFI first bar appends 0.0 to money flow buffers |
| NOTE-TSI-001 | LOW | ema_composable.py | TSI warmup should be slow + fast - 1, not just slow |
| BUG-CMO-001 | MED | buffer_based.py | CMO list.pop(0) is O(n) -- replace with collections.deque(maxlen=length) |
| NOTE-BASE-001 | LOW | base.py | reset()/to_dict() not abstract -- silent omission possible for new detectors |
| NOTE-STATE-001 | MED | state.py | from_json() crash recovery two-step process undocumented |
| NOTE-FIB-001 | MED | fibonacci.py | Extension mode with direction="" produces silent NaN output |
| NOTE-FIB-002 | LOW | fibonacci.py | Fibonacci levels freeze during ranging -- undocumented |
| NOTE-ZONE-001 | MED | zone.py | ATR missing silently creates 0-width degenerate zone |
| NOTE-ZONE-002 | LOW | zone.py | Broken zones permanent until new swing -- undocumented |
| NOTE-TREND-001 | MED | trend.py | Partial-trend classification fires on single wave pair |
| NOTE-TREND-002 | LOW | trend.py | bars_in_trend potential double-increment |

**Combined total actionable items** (original Bug Summary + Additional): MED: 12, LOW: 20
