# Current State → Target State Gap Review (Backtest MTF + Registry + Packet)

## 1) Repo Map (where things live)

- **Backtest CLI entrypoints (user-facing)**
  - `trade_cli.py` — `backtest run|preflight|indicators|data-fix|list` handlers; `backtest run` calls tools wrapper: `handle_backtest_run()` → `backtest_run_idea_card_tool()` (`trade_cli.py:L900-L935`).

- **Backtest tools-layer (golden path orchestration)**
  - `src/tools/backtest_cli_wrapper.py`
    - `backtest_preflight_idea_card_tool()` loads + validates IdeaCard, resolves symbol, runs `run_preflight_gate()` (`src/tools/backtest_cli_wrapper.py:L143-L316`).
    - `backtest_run_idea_card_tool()` runs preflight first, then runs runner with `skip_preflight=True` (explicitly noted) (`src/tools/backtest_cli_wrapper.py:L329-L576`).

- **Runner + gates (preflight, indicator requirements, artifacts)**
  - `src/backtest/runner.py`
    - Gate 1 preflight: `run_preflight_gate()` and hard-fail if failed (`src/backtest/runner.py:L339-L371`).
    - Consumes preflight warmup/delay as *source of truth*; only computes warmup if `skip_preflight=True` (“testing only”) (`src/backtest/runner.py:L431-L455`).
    - Executes engine via `create_engine_from_idea_card()` + `run_engine_with_idea_card()` (`src/backtest/runner.py:L461-L479`).

- **Engine factory (IdeaCard → SystemConfig → BacktestEngine)**
  - `src/backtest/engine_factory.py`
    - `create_engine_from_idea_card()` builds `SystemConfig`, `tf_mapping`, `feature_specs_by_role`, and wires `warmup_bars_by_role` + `delay_bars_by_role` (`src/backtest/engine_factory.py:L57-L220`).
    - `run_engine_with_idea_card()` wraps `IdeaCardSignalEvaluator.evaluate()` into an engine strategy callback (`src/backtest/engine_factory.py:L223-L312`).

- **Warmup/delay computation + IdeaCard execution validation**
  - `src/backtest/execution_validation.py`
    - `compute_warmup_requirements()` combines: max spec warmup, explicit warmup_bars, `bars_history_required`, and `market_structure.lookback_bars`; delay comes **only** from `market_structure.delay_bars` (`src/backtest/execution_validation.py:L466-L516`).
    - `IdeaCardSignalEvaluator` reads features only through `snapshot.get_feature()` (packet-only contract) (`src/backtest/execution_validation.py:L783-L816`).

- **Preflight coverage/backfill**
  - `src/backtest/runtime/preflight.py`
    - Coverage + gaps + alignment check per (symbol, tf): `validate_tf_data()` (`src/backtest/runtime/preflight.py:L360-L487`).
    - Auto-sync/backfill uses tools only: `sync_range_tool`, `fill_gaps_tool`, `heal_data_tool` (`src/backtest/runtime/preflight.py:L504-L640`).
    - Preflight computes warmup **exactly once** and stores it in `PreflightReport.computed_warmup_requirements` (`src/backtest/runtime/preflight.py:L714-L916`).

- **Data feeds / bar timestamps**
  - `src/data/historical_data_store.py` — DuckDB store + `TF_MINUTES` canonical durations (`src/data/historical_data_store.py:L135-L156`).
  - `src/backtest/runtime/feed_store.py` — `FeedStore` arrays; uses `df["timestamp"]` as `ts_open` and `df["ts_close"]` if present else computes `ts_close = timestamp + tf_duration(tf)` (`src/backtest/runtime/feed_store.py:L255-L307`).

- **MTF alignment / forward fill**
  - `src/backtest/engine_snapshot.py` — MTF/HTF forward-fill index update at exec close via `get_idx_at_ts_close()` mapping (`src/backtest/engine_snapshot.py:L27-L71`).
  - `src/backtest/runtime/snapshot_view.py` — snapshot contexts (`exec_ctx`, `htf_ctx`, `mtf_ctx`) + staleness flags (`htf_is_stale`, `mtf_is_stale`) (`src/backtest/runtime/snapshot_view.py:L202-L231`, `L595-L603`).

- **Indicator pipeline / feature computation**
  - `src/backtest/features/feature_spec.py` — `FeatureSpec` + multi-output naming via `MULTI_OUTPUT_KEYS` (`src/backtest/features/feature_spec.py:L328-L514` and `L240-L306`).
  - `src/backtest/indicators.py` — applies FeatureSpecs to DataFrames; multi-output columns built using `MULTI_OUTPUT_KEYS` (not registry) (`src/backtest/indicators.py:L88-L251`).
  - `src/backtest/indicator_vendor.py` — only pandas_ta import; dynamic compute is registry-gated; multi-output canonicalization uses `indicator_registry` (`src/backtest/indicator_vendor.py:L1-L210`).
  - `src/backtest/indicator_registry.py` — supported indicators + canonical output suffixes + param validation (`src/backtest/indicator_registry.py:L1-L38`, `L353-L529`).

- **Packet/snapshot construction (strategy input)**
  - **Current strategy-facing packet:** `RuntimeSnapshotView` (engine hot loop) (`src/backtest/engine.py:L736-L799`).
  - **Legacy-ish packet still exists:** `RuntimeSnapshot` dataclass (`src/backtest/runtime/types.py:L267-L345`) but evaluator explicitly rejects “legacy snapshot” lacking `get_feature()` (`src/backtest/execution_validation.py:L808-L816`).

- **Strategy evaluation entrypoint(s)**
  - `BacktestEngine.run(strategy)` calls `strategy(snapshot, params)` once per exec bar (when ready) (`src/backtest/engine.py:L585-L799`).
  - IdeaCard path: `IdeaCardSignalEvaluator.evaluate(snapshot, has_position, position_side)` (`src/backtest/engine_factory.py:L253-L302`, `src/backtest/execution_validation.py:L715-L782`).

## 2) Execution Timeline (actual step order)

### CLI → tools → runner → engine

- `trade_cli.py:handle_backtest_run()` → `src.tools.backtest_cli_wrapper.backtest_run_idea_card_tool()` (`trade_cli.py:L900-L935`, `src/tools/backtest_cli_wrapper.py:L329-L390`).
- Tools-layer runs **production preflight gate** first (`src/tools/backtest_cli_wrapper.py:L381-L395`) → `run_preflight_gate()` (`src/backtest/runtime/preflight.py:L714-L916`).
- Tools-layer then calls runner with `skip_preflight=True` (explicitly documented as “trust wrapper preflight”) (`src/tools/backtest_cli_wrapper.py:L553-L567`, `L571-L576`).
- Runner creates engine via `create_engine_from_idea_card()` and runs it via `run_engine_with_idea_card()` (`src/backtest/runner.py:L461-L479`, `src/backtest/engine_factory.py:L57-L220`, `L223-L312`).

### Engine hot loop (per exec bar) — real order

1) **Build per-bar timestamps and Bar**
   - Pull `ts_open`, `ts_close` from exec `FeedStore` arrays (`src/backtest/engine.py:L585-L605`).

2) **Exchange step (fills/TP/SL/etc)**
   - `SimulatedExchange.process_bar(bar, prev_bar)` (engine-side call) (`src/backtest/engine.py:L608-L612`).
   - Sim exchange contract explicitly says “strategy evaluates at bar close (ts_close)” (`src/backtest/sim/exchange.py:L7-L12`).

3) **Warmup skip**
   - If `i < sim_start_idx`, engine only updates MTF indices (for forward-fill continuity) then updates history and continues (`src/backtest/engine.py:L617-L650`).

4) **HTF/MTF close detection + forward-fill index update**
   - Called at each exec bar close: `_update_htf_mtf_indices(bar.ts_close)` (`src/backtest/engine.py:L652-L657`).
   - Index update occurs **only if** `htf_feed.get_idx_at_ts_close(exec_ts_close)` returns a match (same for MTF) (`src/backtest/engine_snapshot.py:L57-L70`).

5) **Build snapshot packet**
   - `snapshot = self._build_snapshot_view(i, step_result)` (`src/backtest/engine.py:L736-L739`), delegates to `build_snapshot_view_impl()` (`src/backtest/engine.py:L1035-L1068`, `src/backtest/engine_snapshot.py:L111-L172`).
   - Snapshot contexts:
     - `exec_ctx.current_idx = exec_idx` (always current)
     - `htf_ctx.current_idx = last_closed_htf_idx` (forward-filled)
     - `mtf_ctx.current_idx = last_closed_mtf_idx` (forward-filled) (`src/backtest/runtime/snapshot_view.py:L202-L231`).

6) **Readiness gate + lookahead guard**
   - Multi-TF: if not ready, skip trading but still record equity (`src/backtest/engine.py:L748-L767`).
   - Lookahead guard asserts `snapshot.ts_close == bar.ts_close` and exec context close matches too (`src/backtest/engine.py:L776-L788`).

7) **Evaluate strategy**
   - `signal = strategy(snapshot, self.config.params)` (`src/backtest/engine.py:L791-L795`).
   - IdeaCard strategy path calls `IdeaCardSignalEvaluator.evaluate(snapshot, has_position, position_side)` (`src/backtest/engine_factory.py:L253-L262`).

8) **Risk sizing + order submission**
   - Engine sizes via `SimulatedRiskManager.size_order(snapshot, signal)` and submits order using `timestamp=bar.ts_close` (“decision made at bar close”) (`src/backtest/engine.py:L1114-L1135`).

9) **Record equity + update history (after evaluation)**
   - Equity recorded at `ts_close` (`src/backtest/engine.py:L800-L814`).
   - History updated **after** strategy evaluation to preserve “previous bar” semantics for crossovers (`src/backtest/engine.py:L673-L675`, `L816-L825`).

### Where tf_ctx is forward-filled into tf_exec packet

- Forward-fill is implemented by **holding the last closed HTF/MTF index constant** until the next close timestamp matches (`src/backtest/engine_snapshot.py:L57-L70`) and using that index in `RuntimeSnapshotView.htf_ctx/mtf_ctx` (`src/backtest/runtime/snapshot_view.py:L210-L231`).
- Staleness is detectable: `htf_is_stale := exec_ts_close > htf_ctx.ts_close` (`src/backtest/runtime/snapshot_view.py:L595-L603`).

## 3) Invariants Check (Pass/Fail table)

| Invariant | Current behavior | Evidence (file:line) | Risk | Fix direction |
|---|---|---|---|---|
| Evaluate on tf_exec close only | Strategy called once per exec bar; explicit lookahead guard asserts `snapshot.ts_close == bar.ts_close` | `src/backtest/engine.py:L585-L605`, `src/backtest/engine.py:L776-L795` | Low | Keep guard; ensure any future “intrabar” features stay out of `snapshot` |
| Closed-candle only updates | No mid-bar strategy evaluation; HTF/MTF indices only advance on matching close timestamps | `src/backtest/engine_snapshot.py:L57-L70`, `src/backtest/engine.py:L652-L657` | Medium (timestamp alignment drift across TFs) | Add/strengthen cross-TF alignment diagnostics in preflight (no code now) |
| tf_ctx forward-filled into tf_exec packet | Snapshot HTF/MTF context uses last closed indices (forward-filled); staleness flags exist | `src/backtest/runtime/snapshot_view.py:L210-L231`, `src/backtest/runtime/snapshot_view.py:L595-L603` | Low | Expose staleness in evaluation rules/diagnostics as needed |
| Warmup/backfill gating before evaluation | Runner gate blocks run on preflight failure; engine_data_prep fails if warmup config missing; delay_bars applied to eval start | `src/backtest/runner.py:L339-L371`, `src/backtest/engine_data_prep.py:L178-L186`, `src/backtest/engine_data_prep.py:L558-L593` | Medium (tools-layer runs preflight but then runs runner with `skip_preflight=True`) | Eliminate duplicate preflight paths; make one gate authoritative (`src/tools/backtest_cli_wrapper.py:L553-L567`) |
| Sparse vs dense feature handling | Features are floats; NaN → `None`; no explicit “sparse event” semantics | `src/backtest/runtime/snapshot_view.py:L553-L559` | High (events would look “missing” and conditions would fail) | Add FeatureSpec/registry policy for sparsity and define “no event” semantics (0 vs None) |
| Registry as contract (single source) | **Multiple sources of truth:** `indicator_registry` vs `FeatureSpec.MULTI_OUTPUT_KEYS` vs vendor canonicalization; mismatch exists (SQUEEZE outputs) | `src/backtest/indicator_registry.py:L1-L18`, `src/backtest/indicator_registry.py:L262-L268`, `src/backtest/features/feature_spec.py:L240-L306` | High (drift breaks audits, keys, and portability) | Consolidate multi-output suffixes + key expansion into one module; delete/retire duplicate mappings |
| Strategy consumes only packet (no reaching around) | Evaluator reads only via `snapshot.get_feature()`; fails fast if no `get_feature` | `src/backtest/execution_validation.py:L783-L816` | Medium (snapshot includes exchange reference, so strategies *could* reach around) | Formalize SnapshotView interface and restrict/segment what’s exposed for live portability |
| Structure events + forward-filled context/levels | Not implemented; `market_structure` currently only affects lookback/delay in warmup computation | `src/backtest/idea_card.py:L638-L652`, `src/backtest/execution_validation.py:L492-L511` | High | Introduce structure feature producer outputs + sparsity policy in FeatureSpec/registry |
| Structure lifecycle none→candidate→valid→invalid | No structure state machine types found (only config exists) | `src/backtest/idea_card.py:L638-L652` | High | Add state machine interface and output arrays (status + levels + events) |
| Portable IdeaCards + packets across sim→demo/live | Snapshot contract exists (`get_feature`), but it is simulator-bound (`exchange` is SimulatedExchange) and IdeaCard engine strategy emits LIVE-domain `Signal` with `size_usd` placeholder | `src/backtest/runtime/snapshot_view.py:L232-L235`, `src/backtest/engine_factory.py:L245-L296` | High | Define adapter boundary: SnapshotView + Signal semantics for sim vs live; avoid mixing size_usd/usdt in the same IdeaCard execution path |

## 4) Feature Registry / FeatureSpec Audit

### How features are defined today

- **IdeaCard TFConfig owns FeatureSpecs** (`feature_specs: tuple[FeatureSpec,...]`) and optional `required_indicators` + `market_structure` (`src/backtest/idea_card.py:L683-L705`).
- **FeatureSpec** is declarative and includes:
  - `indicator_type`, `output_key`, `params`, `input_source`, optional `outputs` mapping; multi-output keys computed via `output_keys_list` (`src/backtest/features/feature_spec.py:L328-L426`).
  - Warmup derived per indicator type via vendor warmup helpers (`src/backtest/features/feature_spec.py:L450-L514`).

### Multi-output indicators (how modeled today)

- **Key expansion is duplicated:**
  - `FeatureSpec.output_keys_list` uses `MULTI_OUTPUT_KEYS` suffixes (`src/backtest/features/feature_spec.py:L409-L425`).
  - `IndicatorRegistry.get_expanded_keys()` uses registry-declared suffixes (`src/backtest/indicator_registry.py:L501-L529`).

- **Proven mismatch example (SQUEEZE):**
  - Registry declares `("sqz", "on", "off", "no_sqz")` (`src/backtest/indicator_registry.py:L262-L268`).
  - FeatureSpec declares `("sqz", "sqz_on", "sqz_off", "no_sqz")` (`src/backtest/features/feature_spec.py:L249-L250`).

### Where output keys are defined and validated

- Registry defines supported indicators, required inputs, accepted params, and canonical output suffixes (`src/backtest/indicator_registry.py:L49-L54`, `src/backtest/indicator_registry.py:L353-L366`).
- Vendor canonicalization uses registry outputs for multi-output contract checking (`src/backtest/indicator_vendor.py:L70-L102`).
- IdeaCard validation ensures referenced features are declared and uses `spec.output_keys_list` to build declared keys (`src/backtest/execution_validation.py:L350-L356`).

### Where warmup requirements live and how computed

- Warmup computation is **IdeaCard-native** and includes structure lookback and history requirements (`src/backtest/execution_validation.py:L466-L516`).
- Preflight gate computes warmup **once** and uses it for coverage/backfill (`src/backtest/runtime/preflight.py:L726-L731`, `src/backtest/runtime/preflight.py:L770-L801`).
- Engine data prep refuses to run without `warmup_bars_by_role['exec']` from preflight (`src/backtest/engine_data_prep.py:L178-L186`).

### How “sparse” is currently represented (if at all)

- No explicit sparse policy exists in FeatureSpec or registry; snapshot reads NaN as “not available” (`src/backtest/runtime/snapshot_view.py:L553-L559`).
- Consequence: a sparse “event series” represented as NaN-on-most-bars would appear as missing data and break condition evaluation early (`src/backtest/execution_validation.py:L835-L840`).

### Duplicated sources of truth (flagged)

- **Output suffixes / multi-output expansion**
  - `src/backtest/features/feature_spec.py` (`MULTI_OUTPUT_KEYS`) vs `src/backtest/indicator_registry.py` (`SUPPORTED_INDICATORS.output_keys`) — proven mismatch for SQUEEZE.

- **Indicator availability claims**
  - `src/backtest/indicator_registry.py` explicitly restricts to `SUPPORTED_INDICATORS` (`src/backtest/indicator_registry.py:L49-L52`).
  - `src/backtest/features/feature_frame_builder.py` includes a separate `IndicatorRegistry` claiming “ALL pandas_ta indicators are available dynamically” (`src/backtest/features/feature_frame_builder.py:L175-L221`), which conflicts with vendor’s “unsupported indicator” fail-fast policy (`src/backtest/indicator_vendor.py:L201-L208`).

## 5) Market Structure Feasibility Assessment

### Where a structure state machine would plug in cleanly

- **Best insertion point (precompute phase):** alongside indicator computation in data prep (vectorized indicators happen outside hot loop; structure can also be computed as a deterministic, sequential pre-pass).
  - Candidate modules: `src/backtest/engine_data_prep.py` (already applies FeatureSpecs per TF) (`src/backtest/engine_data_prep.py:L132-L148`) and/or `src/backtest/indicators.py` (FeatureSpec-driven column creation) (`src/backtest/indicators.py:L88-L251`).

### What interface it must implement to match existing feature pipeline

- Must ultimately emit **arrays keyed by indicator_key** into `FeedStore.indicators` so `RuntimeSnapshotView.get_feature()` can retrieve by key (`src/backtest/runtime/snapshot_view.py:L500-L559`) and keys can be declared/validated by IdeaCard (`src/backtest/execution_validation.py:L350-L356`).

### Whether current “feature builder” supports emitting sparse events + forward-filled context

- **Forward-filled context/levels:** yes *if* precomputed as dense arrays (no NaNs) and stored as indicators; snapshot will read them normally (`src/backtest/runtime/snapshot_view.py:L553-L559`).
- **Sparse events:** not safely supported today because “no event” as NaN becomes `None` and causes condition evaluation to fail (`src/backtest/runtime/snapshot_view.py:L553-L559`, `src/backtest/execution_validation.py:L835-L840`).

### Minimal additions needed (interfaces/types/policies) — no code now

- A feature “**sparsity policy**” contract (registry-owned) that defines per-output semantics:
  - dense float (forward-filled)
  - sparse event (non-forward-filled; missing means “0/false”, not “undeclared”)
- A structure lifecycle representation (e.g., status enum array + level arrays + event arrays):
  - `status` as small int/enum per bar (dense, forward-filled)
  - `event_*` as sparse pulses (not forward-filled)
  - `level_*` as dense floats (forward-filled while active)

## 6) Concrete Adjustment Plan (Phased, no code)

### Phase A — Registry contract consolidation (outputs + expansion)

- **Files/classes likely touched**
  - `src/backtest/indicator_registry.py` (canonical output suffixes; `get_expanded_keys`) (`src/backtest/indicator_registry.py:L501-L529`)
  - `src/backtest/features/feature_spec.py` (remove/retire `MULTI_OUTPUT_KEYS` drift; ensure expansion uses registry) (`src/backtest/features/feature_spec.py:L240-L306`)
  - `src/backtest/indicators.py` (multi-output column naming currently uses `MULTI_OUTPUT_KEYS`) (`src/backtest/indicators.py:L158-L204`)
  - `src/backtest/indicator_vendor.py` (canonicalization already registry-based) (`src/backtest/indicator_vendor.py:L70-L102`)

- **Exact goals/invariants achieved**
  - Invariant #5 (registry is single source for outputs/expansion) → **PASS**

- **Risks**
  - Breaking existing IdeaCards/artifacts that depend on old suffixes (e.g., squeeze keys)

- **Test gates (CLI)**
  - `python trade_cli.py backtest audit-toolkit` (Gate 1 contract audit)
  - `python trade_cli.py backtest indicators --print-keys` (key discovery)
  - `python trade_cli.py backtest verify-suite` (end-to-end suite)

### Phase B — Single authoritative warmup/backfill gate path

- **Files/classes likely touched**
  - `src/tools/backtest_cli_wrapper.py` (currently runs preflight then runs runner with `skip_preflight=True`) (`src/tools/backtest_cli_wrapper.py:L553-L567`)
  - `src/backtest/runner.py` (gate semantics) (`src/backtest/runner.py:L339-L371`)

- **Exact goals/invariants achieved**
  - Invariant “warmup/backfill gating before evaluation” becomes unambiguous (single gate path)

- **Risks**
  - Smoke tests that relied on wrapper-only preflight behavior

- **Test gates (CLI)**
  - `python trade_cli.py backtest preflight --idea-card <ID>`
  - `python trade_cli.py backtest run --idea-card <ID> --smoke --strict`

### Phase C — Feature sparsity policy (dense vs sparse) + packet semantics

- **Files/classes likely touched**
  - `src/backtest/runtime/snapshot_view.py` (`get_feature` currently treats NaN as missing) (`src/backtest/runtime/snapshot_view.py:L500-L559`)
  - `src/backtest/execution_validation.py` (condition evaluation currently fails on None) (`src/backtest/execution_validation.py:L835-L840`)
  - `src/backtest/features/feature_spec.py` (declare sparsity policy at spec/output level)

- **Exact goals/invariants achieved**
  - Invariant #3 (sparse events vs forward-filled context) groundwork

- **Risks**
  - Changing evaluation semantics for missing values can change strategy decisions

- **Test gates (CLI)**
  - `python trade_cli.py backtest run --idea-card <ID> --smoke --strict`
  - `python trade_cli.py backtest verify-determinism` (hash determinism)

### Phase D — Market structure producer integration (state machine + outputs)

- **Files/classes likely touched**
  - `src/backtest/idea_card.py` (already has `MarketStructureConfig`; extend to declare structure outputs explicitly) (`src/backtest/idea_card.py:L638-L705`)
  - `src/backtest/engine_data_prep.py` (precompute structure arrays per TF) (`src/backtest/engine_data_prep.py:L132-L148`)
  - `src/backtest/runtime/feed_store.py` (store new arrays/metadata) (`src/backtest/runtime/feed_store.py:L36-L92`)

- **Exact goals/invariants achieved**
  - Invariant #3 and #4 → **PASS**

- **Risks**
  - Performance (structure is sequential), output definition drift, artifact schema changes

- **Test gates (CLI)**
  - `python trade_cli.py backtest metadata-smoke` (metadata provenance)
  - `python trade_cli.py backtest run --idea-card <ID> --strict`

### Phase E — Portability adapter boundary (sim ↔ demo/live)

- **Files/classes likely touched**
  - `src/backtest/runtime/snapshot_view.py` (define an explicit SnapshotView contract boundary)
  - `src/backtest/engine_factory.py` (avoid mixing LIVE-domain `Signal.size_usd` semantics in sim path) (`src/backtest/engine_factory.py:L245-L296`)
  - Future live adapter location (TBD): likely in `src/tools/` or `src/core/` but should implement the same `get_feature/has_feature` interface.

- **Exact goals/invariants achieved**
  - Invariant #6 (portable IdeaCards + packets) → **PASS**

- **Risks**
  - Cross-domain naming (`size_usdt` vs `size_usd`) and execution differences

- **Test gates (CLI)**
  - `python trade_cli.py backtest run --idea-card <ID> --smoke --strict`
  - (later) demo/live tool-layer smoke via existing CLI smoke framework

### Top 10 files to touch (ranked)

1) `src/backtest/indicator_registry.py`
2) `src/backtest/features/feature_spec.py`
3) `src/backtest/indicators.py`
4) `src/backtest/indicator_vendor.py`
5) `src/backtest/runtime/snapshot_view.py`
6) `src/backtest/execution_validation.py`
7) `src/tools/backtest_cli_wrapper.py`
8) `src/backtest/runner.py`
9) `src/backtest/engine_data_prep.py`
10) `src/backtest/engine.py`

### Top 10 risks (ranked)

1) **Multi-output key drift** between registry and FeatureSpec (`squeeze` mismatch) → breaks declared keys and audits (`src/backtest/indicator_registry.py:L262-L268`, `src/backtest/features/feature_spec.py:L249-L250`).
2) **Sparse events unsafe with current semantics** (NaN→None causes rule evaluation to fail early) (`src/backtest/runtime/snapshot_view.py:L553-L559`, `src/backtest/execution_validation.py:L835-L840`).
3) **Two preflight paths** (tools-layer preflight + runner `skip_preflight=True`) can diverge and hide gate regressions (`src/tools/backtest_cli_wrapper.py:L553-L567`, `src/backtest/runner.py:L339-L371`).
4) **Duplicate “IndicatorRegistry” concepts** (strict supported list vs “all indicators dynamic” claims) causing contract confusion (`src/backtest/indicator_registry.py:L49-L52`, `src/backtest/features/feature_frame_builder.py:L175-L221`).
5) **Portability gap**: snapshot packet is simulator-bound (has `exchange` reference) and signal type mixes domains (`size_usd` placeholder) (`src/backtest/runtime/snapshot_view.py:L232-L235`, `src/backtest/engine_factory.py:L245-L296`).
6) **Timestamp equality assumption** for HTF/MTF close matching; any rounding/timezone drift breaks forward-fill update points (`src/backtest/engine_snapshot.py:L57-L70`).
7) **`ceil_to_tf_close()` is modulo-based** (epoch minutes) and not data-driven; can misalign if candle timestamps aren’t perfect boundaries (`src/backtest/runtime/timeframe.py:L115-L153`).
8) **FeedStore ts_close derivation** depends on whether `ts_close` exists; if upstream changes “timestamp semantics”, close math changes globally (`src/backtest/runtime/feed_store.py:L255-L307`).
9) **MarketStructureConfig currently only influences warmup/delay** (no actual structure features), so “structure” in IdeaCards may be misleading (`src/backtest/idea_card.py:L638-L652`, `src/backtest/execution_validation.py:L492-L511`).
10) **Legacy RuntimeSnapshot still present** while engine/evaluator enforce RuntimeSnapshotView; risk of accidental legacy reintroduction (`src/backtest/runtime/types.py:L267-L345`, `src/backtest/execution_validation.py:L808-L816`).

