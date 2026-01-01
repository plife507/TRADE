# Market Structure Integration - Staged Implementation Plan

**Status**: Stage 0-3 ✅ COMPLETE, Stage 4 📋 READY
**Created**: 2026-01-01
**Updated**: 2026-01-01 (v7 - Stage 3 complete)
**Goal**: Build a modular Market Structure Engine enabling logic-based strategies combining structure detection, indicators, and implicit MARK price.

---

## 1. Purpose and Scope

This engine enables **logic-based trading strategies** that reason over:
- Market structure (swing highs/lows, HH/HL/LL/LH patterns, trend state)
- Technical indicators (existing 42-indicator registry)
- Implicit MARK price (always available, mode-agnostic)

**What is "now" (Stages 0-7)**:
- MarkPriceEngine providing `price.mark.*` at every exec close
- Structure detection (swing, trend) in batch mode
- Zones as children of structure blocks
- IdeaCard block-based referencing
- Logic rule evaluation with minimal operators
- Unified state tracking (Signal/Action/Gate)

**What is "later" (Stage 8+)**:
- Demo/Live streaming with websocket providers
- Real-time tick aggregation
- `update_on_close` incremental implementations

---

## 2. Non-Negotiable Invariants

| Invariant | Enforcement |
|-----------|-------------|
| **Closed candles only** | All state updates on TF close; no partial bar access |
| **No lookahead** | Data constrained to bars fully closed before decision point |
| **MTF alignment** | All context aligned to `tf_exec` close with forward-fill |
| **Unified pipeline** | Same signal/confirm/execute flow regardless of evidence source |
| **Implicit MARK** | `price.mark.*` always available; never declared in IdeaCard |
| **Parent-scoped zones** | Zones are children of structures; no standalone `zone.*` namespace |
| **Registry is contract** | Fixed output schemas per type; drift triggers hard-stop |
| **Forward-only coding** | No legacy support, no dual schemas, no shims |
| **Modular architecture** | No god files; split by responsibility; max ~400 LOC/file |

---

## 3. Forward-Only Implementation Policy

**NO LEGACY SUPPORT. NO BACKWARD COMPATIBILITY. HARD BREAKS ALLOWED.**

| Rule | Enforcement |
|------|-------------|
| **No compatibility shims** | Delete old code paths immediately when replacing |
| **Single canonical schema** | One representation per concept; duplicates are bugs |
| **Hard-fail deprecated keys** | Unknown/legacy keys raise `ValueError` at parse |
| **Breaking changes = delete** | When schema changes, remove old parser paths entirely |
| **Schema versioning** | `schema_version` field; old versions rejected |
| **No fallback defaults** | Missing required fields fail loudly; no silent inference |

**Hard-fail validation rules (deprecated keys):**
- `price_inputs` found → error: "MARK is implicit"
- `price_sources` found → error: "MARK is implicit"
- `price_refs` found → error: "MARK is implicit"
- `zone_blocks` found → error: "Define zones inside structure blocks"
- `structure_type` found → error: "Use 'type' not 'structure_type'"

---

## 4. Modular Architecture Policy

**NO GOD FILES. STRICT BOUNDARIES. SPLIT EARLY.**

### 4.1 File Size Limits

| Threshold | Action |
|-----------|--------|
| ~300 LOC | Ideal target |
| ~400 LOC | Review for split |
| >500 LOC | **Mandatory split** (delete monolith) |

### 4.2 One Responsibility Per Module

Each `.py` file owns exactly one concept:
- `swing_detector.py` — swing detection only
- `structure_registry.py` — registry + validation only
- `mark_engine.py` — mark price resolution only

**Anti-patterns (hard-fail in review):**
- `utils.py` as dumping ground
- `helpers.py` with mixed concerns
- `common.py` that everyone imports

### 4.3 Module Layout

```
src/backtest/
├── market_structure/
│   ├── types.py              # StructureType, ZoneType enums
│   ├── spec.py               # StructureSpec, ZoneSpec schemas
│   ├── registry.py           # STRUCTURE_REGISTRY + validation
│   ├── builder.py            # StructureBuilder orchestration
│   ├── zone_builder.py       # ZoneBuilder (bounds from levels)
│   └── detectors/
│       ├── swing.py          # SwingDetector
│       └── trend.py          # TrendClassifier
│
├── prices/
│   ├── mark_engine.py        # MarkPriceEngine
│   └── providers/
│       ├── sim_mark.py       # SimMarkProvider (backtest)
│       └── exchange_mark.py  # Stage 8 only
│
├── runtime/
│   ├── feed_store.py         # Array storage
│   ├── snapshot.py           # RuntimeSnapshotView
│   ├── rule_eval.py          # Reference resolver + operators
│   ├── signal_state.py       # SignalState machine
│   ├── action_state.py       # ActionState machine
│   ├── gate_state.py         # GateState + reason codes
│   └── block_state.py        # Per-block state container
│
└── engine.py                 # Orchestration only (~300 LOC)
```

### 4.4 Coupling Rules

| Layer | Can Import | Cannot Import |
|-------|------------|---------------|
| `detectors/` | numpy, pandas_ta | exchange clients, IdeaCard, runtime |
| `prices/` | numpy | IdeaCard, exchange (except Stage 8) |
| `runtime/` | market_structure, prices | exchange clients, CLI |
| `idea_card*.py` | schemas only | detectors, providers, runtime |

### 4.5 Refactor Trigger

Split immediately if:
- File exceeds 500 LOC
- File imports from 3+ unrelated modules
- Two unrelated responsibilities in one file

**Forward-only**: Delete the monolith; do not preserve imports.

---

## 5. Contracts

### 5.1 Price Contract (Implicit MARK)

**MARK is always available. IdeaCards never declare it.**

| Rule | Enforcement |
|------|-------------|
| `price.mark.*` always valid | Engine provides at every `tf_exec` close |
| No IdeaCard declaration | Hard-fail if `price_inputs`, `price_sources`, `price_refs` found |
| Provider is runtime-only | Simulated vs exchange resolved by engine mode; invisible to IdeaCard |
| `LAST` reserved | If exposed later, also runtime-only (no IdeaCard changes) |

**Canonical access (unified getter):**
```python
# DSL reference (IdeaCard YAML)
lhs: price.mark.close

# Runtime access (same path via getter)
snapshot.get("price.mark.close")  # Point value at exec close
```

**Snapshot Access Contract:**
- The **only** supported access method for strategies/DSL is `snapshot.get(path)`
- Snapshot attributes (e.g., `snapshot.mark_price`) are internal/legacy — not part of the public contract
- New code must use `snapshot.get(...)` exclusively

**Staged availability:**
- Stage 1: `price.mark.close` only (point value at exec bar close)
- Stage 6: Extend to `price.mark.high`, `price.mark.low` for zone interaction metrics

**MarkPriceEngine contract (Stage 1):**
- `get_mark_close(exec_bar_ts)` → float (point value)
- Stage 6 extends to `get_mark_bar(exec_bar_ts)` → (high, low, close)

**Preflight enforcement:**
- Always validate MARK availability for run mode (not conditional on IdeaCard)
- Backtest: verify historical data coverage
- Demo/Live (Stage 8): verify provider connection

### 5.2 Structure Contract

**StructureType Enum:**
```python
class StructureType(str, Enum):
    SWING = "swing"   # Swing high/low detection
    TREND = "trend"   # HH/HL vs LL/LH classification
```

**StructureSpec Schema:**
```python
@dataclass(frozen=True)
class StructureSpec:
    key: str                         # User-facing name ("ms_5m")
    type: StructureType              # Use 'type' not 'structure_type'
    tf_role: str                     # "exec" or "ctx"
    params: Dict[str, Any]           # Explicit, no defaults
    confirmation: ConfirmationConfig
    zones: List[ZoneSpec]            # Child zones (may be empty)

    @property
    def spec_id(self) -> str:
        """Math identity: hash of {type, params, confirmation, zones}."""
        ...

    @property
    def block_id(self) -> str:
        """Placement identity: hash of {spec_id, key, tf_role}."""
        ...
```

**Layered Identity Contract:**

| Identity | Includes | Use For |
|----------|----------|---------|
| `spec_id` | type, params, confirmation | Structure math identity (excludes zones) |
| `zone_spec_id` | zones only | Zone layer identity (empty if no zones) |
| `block_id` | spec_id + key + tf_role | Structure placement identity |
| `zone_block_id` | block_id + zone_spec_id | Full placement with zones |

**Why layered?** Zones are a derived layer introduced in Stage 5. Separating identities means:
- Structure engine stabilizes first (Stages 1-4)
- Zone iteration doesn't invalidate structure caches
- Same swing params on `exec` vs `ctx` = same `spec_id`, different `block_id`

**Storage Key Rules (Option A: zones nested under parent):**

| Layer | Storage Location | Identity Used |
|-------|------------------|---------------|
| Structure arrays | `FeedStore.structures[block_id]` | `block_id` |
| Zone arrays | `FeedStore.structures[block_id].zones[zone_key]` | `zone_key` (nested) |
| Structure artifacts | `structure_{block_id}.jsonl` | `block_id` |
| Zone artifacts | `zone_{zone_block_id}.jsonl` | `zone_block_id` |

**Why nested?** Zones are children that reset with parent. Keeping them physically under `structures[block_id]` maintains the mental model. `zone_block_id` is used for artifact caching only.

**Snapshot access** (unchanged):
- `snapshot.get("structure.ms_5m.high_level")` — structure field
- `snapshot.get("structure.ms_5m.zones.demand_1.lower")` — zone field (parent-scoped)

**Stage Gating:**
- Stages 1-4: Must not write zone artifacts or require zone IDs
- Stage 5: Introduces zone IDs and starts writing zone artifacts

**Output schemas (per type):**

| Type | Outputs | Dtypes |
|------|---------|--------|
| SWING | `high_level`, `high_idx`, `low_level`, `low_idx`, `state`, `recency` | float64, int32, float64, int32, int8, int16 |
| TREND | `trend_state`, `recency` | int8 (0=UNKNOWN, 1=UP, 2=DOWN), int16 |

**Note:** Default float64 for price levels/bounds to avoid boundary edge bugs. Optimize to float32 only if profiling shows memory pressure.

**Registry contract:**
```python
STRUCTURE_REGISTRY = {
    StructureType.SWING: {
        "detector": SwingDetector,
        "outputs": ["high_level", "high_idx", "low_level", "low_idx", "state", "recency"],
        "required_params": ["left", "right"],
        "depends_on": [],
    },
    StructureType.TREND: {
        "detector": TrendClassifier,
        "outputs": ["trend_state", "recency"],
        "required_params": [],
        "depends_on": [StructureType.SWING],  # Derives from swing outputs
    },
}
```

**Dependency ordering:** TREND requires SWING outputs (HH/HL/LL/LH derived from swing high/low sequence). Builder runs SWING before TREND.

**Audit hard-stops:**
- Unknown `type` → `UNKNOWN_STRUCTURE_TYPE`
- Missing required param → `MISSING_REQUIRED_PARAM`
- Output schema mismatch → `OUTPUT_SCHEMA_MISMATCH`

### 5.3 Zone Contract (Parent-Scoped)

**Zones are children of structure blocks. No standalone namespace.**

| Rule | Enforcement |
|------|-------------|
| Canonical path | `structure.<parent_key>.zones.<zone_key>.*` |
| No `zone.*` namespace | Hard-fail if used |
| Parent-scoped derivation | Zones derive anchors from parent only (no cross-structure) |
| Reset on parent advance | When parent updates, zones reset |

**ZoneSpec Schema (nested in parent):**
```python
@dataclass(frozen=True)
class ZoneSpec:
    key: str              # "demand_1"
    type: ZoneType        # demand, supply
    width_model: str      # "atr_mult", "percent", "fixed"
    width_params: Dict    # {atr_len: 14, mult: 1.5}
```

**Zone outputs (per zone key):**

| Output | Dtype | Description |
|--------|-------|-------------|
| `lower` | float32 | Lower bound |
| `upper` | float32 | Upper bound |
| `state` | int8 | 0=none, 1=active, 2=broken |
| `recency` | int16 | Bars since zone established |
| `parent_anchor_id` | int32 | Links to parent structure version |

**Zone lifecycle (reset on parent advance):**
```
1. Parent structure emits new anchor (e.g., new swing low)
2. Zone recomputes:
   - lower/upper from new anchor + width_model
   - parent_anchor_id = new value
   - recency = 0
   - state = ACTIVE
   - interaction metrics reset (no carryover)
3. Between parent updates: forward-fill bounds to exec close
4. On zone break: state = BROKEN (remains until parent advances)
```

**Snapshot access:**
```python
# Parent-scoped path (canonical)
snapshot.get("structure.ms_5m.zones.demand_1.lower")
snapshot.get("structure.ms_5m.zones.demand_1.state")

# Direct structure access
snapshot.get("structure.ms_5m.high_level")
snapshot.get("structure.ms_5m.trend_state")
```

### 5.4 IdeaCard Schema (Canonical)

**Block-based structure with nested zones:**
```yaml
schema_version: 2

market_structure_blocks:
  - key: ms_5m
    type: swing              # Use 'type' not 'structure_type'
    tf_role: exec
    params:
      left: 3
      right: 3
    confirmation:
      mode: bar_count
      bars: 2
    zones:                   # Nested under parent
      - key: demand_1
        type: demand
        width_model: atr_mult
        width_params:
          atr_len: 14
          mult: 1.5

signal_rules:
  entry:
    - direction: long
      conditions:
        - lhs: price.mark.close           # Implicit MARK
          operator: lt
          rhs: structure.ms_5m.high_level
        - lhs: structure.ms_5m.zones.demand_1.state
          operator: eq
          rhs: 1                          # ACTIVE
```

**Forbidden in IdeaCard (hard-fail):**
- `price_inputs`, `price_sources`, `price_refs`
- `zone_blocks` (top-level)
- `structure_type` (use `type`)
- Provider names, endpoints, mode switches

### 5.5 Operator Contract

**MVP Operators:**

| Operator | Behavior | Types |
|----------|----------|-------|
| `gt` | lhs > rhs | numeric |
| `lt` | lhs < rhs | numeric |
| `ge` | lhs >= rhs | numeric |
| `le` | lhs <= rhs | numeric |
| `eq` | lhs == rhs (exact) | int, bool, enum |
| `approx_eq` | abs(lhs - rhs) < tolerance | float (requires tolerance) |

**Edge case semantics:**
- NaN/missing → `false` + reason code `R_MISSING_VALUE`
- Type mismatch → `false` + reason code `R_TYPE_MISMATCH`
- `approx_eq` without tolerance → hard-fail at parse

**Deferred operators:**
- `crosses_up`, `crosses_down` (require offset history)
- `within_bps` (tolerance semantics)

---

## 6. Staged Implementation Roadmap

### Stage 0: Contracts + Schema Lock

**Goal**: Establish canonical schemas and module scaffolding.

**Deliverables:**
- [x] 0.1 Create module directory structure per Section 4.3
- [x] 0.2 Define `StructureType`, `ZoneType` enums in `types.py`
- [x] 0.3 Define `StructureSpec`, `ZoneSpec` in `spec.py`
- [x] 0.4 Create `STRUCTURE_REGISTRY` skeleton with per-type output schemas
- [x] 0.5 Implement `spec_id` (math identity) and `block_id` (placement identity)
- [x] 0.6 Add hard-fail for deprecated keys (`price_inputs`, `zone_blocks`, `structure_type`)

**Modules:**
- `src/backtest/market_structure/types.py` (new)
- `src/backtest/market_structure/spec.py` (new)
- `src/backtest/market_structure/registry.py` (new)

**Acceptance:**
- Import succeeds: `from src.backtest.market_structure import StructureType`
- Registry rejects unknown types
- Deprecated keys raise `ValueError`

---

### Stage 1: MarkPriceEngine MVP ✅ COMPLETE

**Goal**: Provide `price.mark.*` at every exec close (backtest/sim only).

**Deliverables:**
- [x] 1.1 Create `MarkPriceEngine` with `get_mark_close()`
- [x] 1.2 Create `SimMarkProvider` using historical data
- [x] 1.3 Add `snapshot.get("price.mark.close")` to `RuntimeSnapshotView`
- [x] 1.4 Wire preflight validation for MARK
- [x] 1.5 Add resolution logging + CLI smoke test

**Modules (Implemented):**
- `src/backtest/prices/types.py` (new: PriceRef, HealthCheckResult, MarkPriceResult)
- `src/backtest/prices/engine.py` (new: MarkPriceEngine)
- `src/backtest/prices/providers/sim_mark.py` (new: SimMarkProvider)
- `src/backtest/prices/validation.py` (new: validate_mark_price_availability)
- `src/backtest/runtime/snapshot_view.py` (modified: added `get()` method)
- `src/cli/smoke_tests.py` (modified: added `run_mark_price_smoke()`)

**Acceptance Verified:**
- `snapshot.get("price.mark.close")` returns valid float ✅
- Same input → same output (deterministic) ✅
- Resolution log shows provider used ✅
- Preflight validates MARK availability (hard-fail if missing) ✅
- CLI command: `python trade_cli.py backtest mark-price-smoke` ✅

---

### Stage 2: Structure MVP (Swing + Trend) ✅ COMPLETE

**Goal**: Detect swing highs/lows and classify HH/HL vs LL/LH.

**Dependency:** TREND depends on SWING outputs. TrendClassifier uses swing high/low sequence to classify HH/HL vs LL/LH patterns. Builder runs SWING before TREND.

**Deliverables:**
- [x] 2.1 Create `BaseDetector` ABC with `build_batch()`
- [x] 2.2 Implement `SwingDetector` (outputs: high_level, high_idx, low_level, low_idx, state, recency)
- [x] 2.3 Implement `TrendClassifier` (outputs: trend_state, recency) — runs after SWING
- [x] 2.4 Create `StructureBuilder` orchestrator with dependency ordering
- [x] 2.5 Add `structures` namespace to `FeedStore`
- [x] 2.6 Add `snapshot.get("structure.<key>.<field>")` accessors

**Modules (Implemented):**
- `src/backtest/market_structure/detectors/base.py` (new: BaseDetector ABC)
- `src/backtest/market_structure/detectors/swing.py` (new: SwingDetector)
- `src/backtest/market_structure/detectors/trend_classifier.py` (new: TrendClassifier)
- `src/backtest/market_structure/builder.py` (new: StructureBuilder, StructureStore)
- `src/backtest/runtime/feed_store.py` (modified: structures namespace)
- `src/backtest/runtime/snapshot_view.py` (modified: structure accessor)

**Acceptance Verified:**
- SwingDetector produces correct output schema ✅
- TrendClassifier produces `trend_state` values 0/1/2 (UNKNOWN/UP/DOWN) ✅
- Builder runs detectors in dependency order (SWING → TREND) ✅
- Outputs deterministic (seeded test) ✅
- CLI command: `python trade_cli.py backtest structure-smoke` ✅

**Artifacts:**
- `artifacts/structure_metadata.jsonl`

---

### Stage 3: IdeaCard Block Integration ✅ COMPLETE

**Goal**: Parse structure blocks with nested zones; integrate preflight.

**Deliverables:**
- [x] 3.1 Add `market_structure_blocks` to IdeaCard schema
- [x] 3.2 Parse blocks with hard-fail on unknown types
- [x] 3.3 Hard-fail deprecated keys (`price_inputs`, `zone_blocks`, `structure_type`)
- [x] 3.4 Compute `spec_id` for each block
- [x] 3.5 Add structure warmup to preflight (TREND heuristic: `(left+right)*5`)
- [x] 3.6 Preflight always validates MARK availability (not conditional)
- [x] 3.7 **Stage 3.2**: Enforce unique block keys (`DUPLICATE_STRUCTURE_KEY` error)
- [x] 3.8 **Stage 3.2**: Add `STRUCTURE_SCHEMA_VERSION = "1.0.0"` and emit in manifests
- [x] 3.9 **Stage 3.3**: Strict canonical enum tokens (UNKNOWN/UP/DOWN only)
- [x] 3.10 **Stage 3.3**: Reject numeric literals for enum fields
- [x] 3.11 **Stage 3.3**: Reject legacy tokens (BULL/BEAR/BULLISH/BEARISH/NONE)

**Modules (Implemented):**
- `src/backtest/idea_card.py` (modified: market_structure_blocks parsing)
- `src/backtest/idea_card_yaml_builder.py` (modified: structure validation, enum tokens)
- `src/backtest/execution_validation.py` (modified: structure warmup computation)
- `src/backtest/market_structure/types.py` (modified: STRUCTURE_SCHEMA_VERSION, TrendState)
- `src/backtest/market_structure/builder.py` (modified: manifest with schema_version + enum_labels)

**Acceptance Verified:**
- IdeaCard with `market_structure_blocks` normalizes ✅
- Unknown `type` raises `ValueError` ✅
- Deprecated keys raise `ValueError` ✅
- Preflight includes structure warmup + MARK check ✅
- Duplicate block keys hard-fail with actionable error ✅
- Enum tokens: only UNKNOWN/UP/DOWN accepted for `trend_state` ✅
- Numeric literals rejected: `value: 1` → "requires canonical token" ✅
- Legacy tokens rejected: BULL/BEAR → "Allowed: DOWN, UNKNOWN, UP" ✅
- V_61 validation IdeaCard uses UP/DOWN tokens ✅
- CLI command: `python trade_cli.py backtest idea-card-normalize` ✅

**TrendState Enum (Canonical):**
```python
class TrendState(int, Enum):
    UNKNOWN = 0  # No clear trend
    UP = 1       # HH + HL pattern (structural uptrend)
    DOWN = 2     # LL + LH pattern (structural downtrend)
```

**Note:** UP/DOWN refer to structural trend. BULL/BEAR reserved for future sentiment/regime layer.

---

### Stage 4: Rule Evaluation MVP

**Goal**: Evaluate conditions with minimal operators.

**Deliverables:**
- [ ] 4.1 Implement reference resolver (`price.mark.*`, `indicator.*`, `structure.*`)
- [ ] 4.2 Implement operators: `gt`, `lt`, `ge`, `le`, `eq`, `approx_eq`
- [ ] 4.3 Add NaN/missing handling (→ false + reason code)
- [ ] 4.4 Wire into signal evaluation

**Modules:**
- `src/backtest/runtime/rule_eval.py` (new)
- `src/backtest/execution_validation.py` (modify)

**Acceptance:**
- `price.mark.close lt structure.ms_5m.high_level` evaluates correctly
- `eq` works for int/bool/enum
- `approx_eq` requires tolerance (hard-fail if missing)
- NaN → false + `R_MISSING_VALUE`

---

### Stage 5: Zones (Parent-Scoped)

**Goal**: Compute zone bounds as children of structure blocks.

**Deliverables:**
- [ ] 5.1 Implement `ZoneBuilder` computing bounds from parent levels
- [ ] 5.2 Add zone outputs nested under parent in FeedStore
- [ ] 5.3 Implement zone reset on parent advance
- [ ] 5.4 Add `snapshot.get("structure.<key>.zones.<zone>.<field>")` accessors
- [ ] 5.5 Hard-fail standalone `zone.*` references

**Modules:**
- `src/backtest/market_structure/zone_builder.py` (new)
- `src/backtest/runtime/feed_store.py` (modify)
- `src/backtest/runtime/snapshot.py` (modify)

**Acceptance:**
- Zones computed from parent swing levels
- Zones reset when parent anchor changes
- `structure.ms_5m.zones.demand_1.lower` works
- `zone.demand_1.lower` hard-fails

---

### Stage 6: Zone Interaction (Optional)

**Goal**: Compute interaction metrics for zones.

**Prerequisite:** Extend MarkPriceEngine with `get_mark_bar()` returning (high, low, close) for interaction computation.

**Deliverables:**
- [ ] 6.1 Extend MarkPriceEngine with `get_mark_bar()` for high/low access
- [ ] 6.2 Add `price.mark.high`, `price.mark.low` to snapshot
- [ ] 6.3 Implement `ZoneInteractionComputer`
- [ ] 6.4 Add metrics: `touched`, `inside`, `time_in_zone`
- [ ] 6.5 Reset interaction state on parent advance
- [ ] 6.6 Add accessor: `structure.<key>.zones.<zone>.touched`

**Modules:**
- `src/backtest/prices/mark_engine.py` (modify)
- `src/backtest/market_structure/zone_interaction.py` (new)
- `src/backtest/runtime/snapshot.py` (modify)

**Acceptance:**
- `snapshot.get("price.mark.high")` and `snapshot.get("price.mark.low")` work
- Interaction metrics computed at exec close
- Metrics reset when zone resets
- No lookahead (only closed bars)

**Deferred:**
- `swept`, `max_penetration` (complex semantics)

---

### Stage 7: Unified State Tracking

**Goal**: Implement Signal/Action/Gate state machines.

**Deliverables:**
- [ ] 7.1 Implement `SignalState` (NONE → CANDIDATE → CONFIRMING → CONFIRMED → EXPIRED)
- [ ] 7.2 Implement `ActionState` (IDLE → ACTIONABLE → SUBMITTED → FILLED/REJECTED)
- [ ] 7.3 Implement `GateState` with reason codes
- [ ] 7.4 Implement `BlockState` container
- [ ] 7.5 Wire into engine decision loop

**Modules:**
- `src/backtest/runtime/signal_state.py` (new)
- `src/backtest/runtime/action_state.py` (new)
- `src/backtest/runtime/gate_state.py` (new)
- `src/backtest/runtime/block_state.py` (new)
- `src/backtest/engine.py` (modify)

**Reason Codes:**
- `R_WARMUP_REMAINING`
- `R_MISSING_STRUCTURE`
- `R_MISSING_VALUE`
- `R_RISK_MAX_DD`
- `R_COOLDOWN_ACTIVE`

**Acceptance:**
- State transitions deterministic
- Reason codes populated
- `is_actionable()` = SignalState.CONFIRMED + GateState.PASS

---

### Stage 8: Demo/Live Streaming (Separate Track)

**Goal**: Enable real-time mark price and incremental updates.

**NOTE**: Separate integration track. Not required for Stages 0-7.

**Deliverables:**
- [ ] 8.1 Implement `ExchangeMarkProvider` with websocket
- [ ] 8.2 Implement tick aggregation policy
- [ ] 8.3 Implement `update_on_close()` in detectors
- [ ] 8.4 Add streaming preflight checks
- [ ] 8.5 Connection health monitoring

**Modules:**
- `src/backtest/prices/providers/exchange_mark.py` (new)
- `src/backtest/market_structure/detectors/*.py` (modify)
- `src/backtest/runtime/streaming/` (new directory)

**Acceptance:**
- Mark updates via websocket
- Structure transitions match batch (parity test)
- Graceful degradation on disconnect

---

## 7. Validation Plan

### Per-Stage Validation

| Stage | Deterministic Audit | CLI Smoke Test | Failure |
|-------|---------------------|----------------|---------|
| 0 | Spec ID hash stability | `python -c "import ..."` | Non-zero exit |
| 1 | Mark values match historical | `backtest preflight --idea-card V_61` | NaN in mark |
| 2 | Swing detection seeded | `backtest audit-structure-registry` | Schema mismatch |
| 3 | Normalization round-trip | `backtest idea-card-normalize` | Unknown type |
| 4 | Condition truth table | `backtest run --dry-run` | Wrong result |
| 5 | Zone bounds + reset | `backtest audit-zones` | Bounds mismatch |
| 6 | Interaction no-lookahead | `backtest audit-interaction` | Future data |
| 7 | State determinism | `backtest run --seed 42` | State drift |

### Validation IdeaCards

| ID | Purpose | Stage | Status |
|----|---------|-------|--------|
| V_61_structure_swing | Swing + Trend detection with UP/DOWN tokens | 2-3 | ✅ Complete |
| V_62_trend_class | HH/HL/LL/LH | 2 | 📋 Planned |
| V_63_zones_nested | Parent-scoped zones | 5 | 📋 Planned |
| V_64_zone_interaction | Interaction metrics | 6 | 📋 Planned |
| V_65_state_tracking | Signal/Action/Gate | 7 | 📋 Planned |

### Artifacts

| Stage | Artifact | Format |
|-------|----------|--------|
| 1 | `mark_resolution.jsonl` | Provider log |
| 2 | `structure_metadata.jsonl` | Computation provenance |
| 3 | `normalization_output.json` | Parsed IdeaCard |
| 7 | `state_transitions.jsonl` | State machine log |

---

## 8. Future Enhancements

**Ordered by priority:**

1. **BOS/CHoCH** — Break of Structure / Change of Character
2. **Fib/Pivot Levels** — Derived from structure
3. **Advanced Operators** — `crosses_up`, `crosses_down`, `within_bps`
4. **Swept/Max Penetration** — Complex zone interaction
5. **Streaming Parity Suite** — Demo/live matching batch
6. **Order Flow** — Volume profile, delta, imbalances

---

## 9. Files Reference

### New Directories
- `src/backtest/market_structure/`
- `src/backtest/market_structure/detectors/`
- `src/backtest/prices/`
- `src/backtest/prices/providers/`

### New Files by Stage

| Stage | Files |
|-------|-------|
| 0 | `types.py`, `spec.py`, `registry.py` |
| 1 | `prices/mark_engine.py`, `prices/providers/sim_mark.py` |
| 2 | `detectors/swing.py`, `detectors/trend.py`, `builder.py` |
| 5 | `zone_builder.py` |
| 6 | `zone_interaction.py` |
| 7 | `runtime/signal_state.py`, `runtime/action_state.py`, `runtime/gate_state.py`, `runtime/block_state.py` |
| 8 | `prices/providers/exchange_mark.py`, `runtime/streaming/` |

---

## 10. Changelog

### v7 (Stage 3 Complete)

| Change | Reason |
|--------|--------|
| **Stage 2 complete** | SwingDetector + TrendClassifier implemented and tested |
| **Stage 3 complete** | IdeaCard integration with market_structure_blocks |
| **TrendState: UNKNOWN/UP/DOWN** | Renamed from BULL/BEAR; UP/DOWN = structural trend |
| **BULL/BEAR reserved** | Reserved for future sentiment/regime layer |
| **Strict enum tokens** | Only UNKNOWN/UP/DOWN accepted; no numerics, no synonyms |
| **STRUCTURE_SCHEMA_VERSION** | Added `1.0.0` for contract tracking |
| **Duplicate key detection** | `DUPLICATE_STRUCTURE_KEY` error with actionable fix |
| **TREND warmup heuristic** | `(left+right)*5` bars for conservative warmup |
| **V_61 updated** | Uses UP/DOWN canonical tokens |

### v6 (Consistency Fixes)

| Change | Reason |
|--------|--------|
| **MARK is implicit** | Removed all `price_inputs`/`price_sources`/`price_refs` from IdeaCard; MARK always available |
| **Zones parent-scoped** | Zones are children of structure blocks; path is `structure.<key>.zones.<zone>.*` |
| **Removed standalone `zone.*`** | Hard-fail; forward-only |
| **Zone reset on parent advance** | Zones reset when parent structure updates |
| **Unified YAML key to `type`** | Hard-fail `structure_type`; use `type` only |
| **Per-type output schemas** | SWING outputs differ from TREND outputs; registry explicit |
| **Clarified MarkPriceEngine** | `get_mark_close()` returns point value, not OHLC bar |
| **Fixed operator semantics** | `eq` = exact; `approx_eq` = float with tolerance |
| **Preflight always checks MARK** | Not conditional on IdeaCard |
| **Renamed `zone_blocks` → nested `zones`** | Zones inside parent structure block |

### Previous Versions

- v5: Staged refactor
- v4: Sr. Engineer review fixes
- v3: Unified pipeline
- v2: Architecture refinements
- v1: Initial plan

---

## 11. Open Decisions

**None.** All decisions made:
- MARK implicit (never in IdeaCard)
- Zones parent-scoped (`structure.<key>.zones.<zone>.*`)
- Use `type` not `structure_type` in YAML
- `eq` exact, `approx_eq` with tolerance
- Stage 8 separate track
- TrendState: UNKNOWN/UP/DOWN (UP=structural uptrend, DOWN=structural downtrend)
- BULL/BEAR reserved for future sentiment/regime layer
- Enum tokens strict canonical only (no numerics, no synonyms)
