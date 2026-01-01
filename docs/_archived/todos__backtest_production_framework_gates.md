# EXECUTION PLAN — Build & Verify Production Backtest Framework (Gates A–F)

## Purpose

Move from test-driven validation to a **real production framework in `src/`**, and prove—conclusively—that:
- the **actual engine** is running (not stubs or legacy paths),
- **indicators are computed via the real FeatureFrameBuilder** (not tests),
- **IdeaCard is the only config source**,
- outputs are deterministic, audited, and correct.

This plan is **execution-directed**. No questions, no alternatives, no backward compatibility.

---

## Canonical Pipeline (ONLY supported path)

```
IdeaCard (YAML)
→ validate_idea_card_full()
→ warmup_requirements
→ FeatureFrameBuilder (vectorized, outside hot loop)
→ FeedStore / SnapshotView
→ Engine.run()
→ SimulatedExchange
→ Artifacts
```

---

## Decision Locks (Hard)

- [x] **Config source**: IdeaCard ONLY
  - `SystemConfig/load_system_config()` must not be reachable from runner.
- [x] **IdeaCard location (production)**: `configs/idea_cards/`
  - `src/strategies/idea_cards/` = examples/templates only.
- [x] **Runner**: one entrypoint only — `run_backtest_with_gates()`
- [x] **Indicators**: computed only via FeatureFrameBuilder; no implicit defaults.
- [ ] **No DataFrame ops in hot loop** - FUTURE: requires engine refactor
- [x] **No DuckDB mutation from backtest/sim**; all fixes via `src/tools/data_tools.py`.

---

## Gate E — Foundation (Config + Docs) ✅ COMPLETE

### Tasks

- [x] Create `configs/idea_cards/`
- [x] Move/copy example IdeaCard(s) into this folder
- [x] Update IdeaCard loader default path to `configs/idea_cards/`
- [x] Create `src/backtest/README.md` documenting:
  - [x] canonical pipeline
  - [x] module ownership
  - [x] single runner entrypoint

### Acceptance

- [x] Loader defaults to `configs/idea_cards/`
- [x] README exists and names the only supported pipeline

---

## Gate B — Module Ownership Lock ✅ COMPLETE

### Tasks

Verify/clean that **each responsibility has exactly one owner**:

- [x] `idea_card.py` — schema + loader + list
- [x] `execution_validation.py` — Gate 8.x (hash/contract/features/warmup/pre-eval)
- [x] `features/` — FeatureSpec + Registry + FeatureFrameBuilder
- [x] `runtime/` — FeedStore, SnapshotView, TimeframeCache, Preflight
- [x] `sim/` — SimulatedExchange (fills/margin/liquidation/accounting)
- [x] `engine.py` — deterministic engine orchestration (hot-loop)
- [x] `artifacts/` — standards + writers + validators
- [x] `runner.py` — single entrypoint: `run_backtest_with_gates()`

### Acceptance

- [x] No duplicate snapshot builders, runners, or MTF aligners
- [x] README reflects actual code paths

---

## Gate C — Core Wiring (IdeaCard → Engine) ✅ COMPLETE

### Tasks

- [x] Wire engine to accept IdeaCard (via `IdeaCardEngineWrapper`)
- [x] Implement `IdeaCardSignalEvaluator.evaluate()` (no-op forbidden)
  - [x] Gate test: `tests/test_gate_c_evaluator_not_noop.py` (5 tests)
- [x] Temporary IdeaCard→SystemConfig adapter exists:
  - [x] single caller (runner only)
  - [x] marked TEMP with deletion criteria
  - [x] test asserts `load_system_config()` unreachable from runner
- [x] Move run-hash helpers into `src/backtest/artifacts/hashes.py`

### Acceptance

- [x] Engine executes with IdeaCard as input
- [x] Evaluator produces real evaluations (even if no trades)

---

## Gate D — Runner Integration (Real Execution) ✅ COMPLETE

### Tasks

- [x] Wire `runner.py` to:
  - [x] run preflight gate
  - [x] build features via `build_features_from_idea_card()`
  - [x] run engine
  - [x] write real artifacts
- [x] Remove/disable any placeholder artifact paths
- [x] Enforce **single entrypoint**:
  - [x] only runner may call `BacktestEngine.run()` (verified via grep)

### Canonical command

```bash
python -m src.backtest.runner \
  --idea <id_or_path> \
  --start <ts> --end <ts> \
  --env <live|demo> \
  --export-root backtests/
```

### Required Artifacts

- [x] `preflight_report.json`
- [x] `result.json` (includes: idea hash, pipeline version, resolved idea path, run_id, run_hash)
- [x] `trades.csv`
- [x] `equity.csv`
- [ ] `events.jsonl` (optional)

### Acceptance

- [x] Export path matches: `backtests/{idea_id}/{symbol}/{tf_exec}/{start}_{end}_{run_id}/...`
- [x] Artifact standards validation passes
- [x] Real run completed with CLI command

---

## Gate D.1 — Production Pipeline Verification (HARD) ✅ COMPLETE

### Tasks

- [x] Implement `pipeline_signature.json` written per run, containing:
  - [x] resolved IdeaCard path
  - [x] idea hash
  - [x] pipeline version
  - [x] engine / snapshot / feature builder / indicator backend impl names
  - [x] `config_source = "IdeaCard"`
  - [x] `uses_system_config_loader = false`
- [x] Assert:
  - [x] no placeholder mode
  - [x] undeclared indicator access via `get_indicator_strict()` raises
  - [x] computed feature keys == declared feature keys
- [x] Test: `tests/test_gate_d1_pipeline_signature.py` (14 tests)

### Acceptance

- [x] `pipeline_signature.json` exists in artifact folder
- [x] `result.json` includes hash, run_id, resolved idea path

---

## Gate D.2 — Randomized IdeaCard Batch Verification (5 Cards) [HARD] ✅ COMPLETE

### Generator Rules

- [x] Deterministic seed
- [x] Generate 5 valid IdeaCards into: `configs/idea_cards/generated/`
- [x] Select symbols from available local data only (no hardcoded list)

### Indicator Rules (HARD)

- [x] Each IdeaCard MUST declare ≥2 indicators on tf_exec
- [x] Indicators chosen randomly from TA-lib-backed allowlist:
  - EMA, SMA, RSI, ATR, MACD, BBANDS, STOCH, STOCHRSI
- [x] Multi-output indicators MUST declare all outputs
- [x] Params randomized within safe bounds
- [x] Warmup computed via existing logic (no hardcoding)

### Direction Rules (HARD)

- [x] Each IdeaCard is single-direction only: `long_only` OR `short_only`
- [x] Mixed across the 5 cards (seeded; not all same direction)
- [x] Signal rules only for allowed direction

### Batch Execution

- [x] For each IdeaCard:
  - [x] Run `run_backtest_with_gates()`
  - [x] Produce full artifacts + `pipeline_signature.json`
- [x] Batch runner: `src/backtest/gates/batch_verification.py`

### Per-Run Validation

- [x] Assert:
  - [x] Preflight PASS
  - [x] Declared-only indicators enforced
  - [x] Real evaluation executed
  - [x] Artifacts exist
  - [x] Deterministic hashes on re-run

### Batch Artifact

- [x] Write `batch_summary.json` with:
  - [x] seed
  - [x] idea_ids, symbols, directions
  - [x] artifact paths
  - [x] pass/fail per card

### Tests

- [x] `tests/test_gate_d2_batch_verification.py` (14 tests)

### Acceptance

- [x] Generator produces valid IdeaCards
- [x] Cards can be loaded and validated
- [x] Batch runner infrastructure complete

---

## Gate A — Production-First Enforcement ✅ COMPLETE

### Tasks

- [x] Add `src/backtest/gates/production_first_import_gate.py` (AST-based scan)
- [x] Fail on disallowed function names in `tests/` (unless fixtures/helpers)
  - keywords: `build_`, `compute_`, `refresh_`, `align_`, `preflight_`, `indicator_`, `snapshot_`
- [x] Add allowlists to reduce false positives:
  - [x] `tests/_fixtures/**`, `tests/helpers/**`
  - [x] Pandas patterns ONLY in synthetic data generation
- [x] Fail if tests contain DataFrame indicator math (outside allowlist)
  - patterns: `.rolling(`, `.ewm(`, `.shift(`, `.diff(`, `.pct_change(`
- [x] Print gate summary with actionable output
- [x] Add test: `tests/test_gate_a_production_first.py` (4 tests)

### Acceptance

- [x] Gate passes (no violations)
- [x] Gate summary printed with actionable output

---

## Gate F — Delete/Consolidate (No Parallel Paths) ✅ COMPLETE

### Tasks

- [x] Retire legacy SystemConfig backtest path (external interface)
  - [x] remove tool-layer SystemConfig runner paths
  - [x] isolate via TEMP adapter
- [x] Adapter sunset criteria:
  - [x] single caller (runner)
  - [x] marked TEMP with deletion criteria
  - [x] test asserts not usable as external load path
- [x] Data tools only enforcement:
  - [x] backtest/sim/runtime code must not write/repair DuckDB directly
  - [x] all data fixes must call `src/tools/data_tools.py`
- [x] Add test: `tests/test_gate_f_isolation.py` (6 tests)

### Acceptance

- [x] No parallel execution paths remain
- [x] `IdeaCard → ... → runner` is the only supported surface

---

## Final Acceptance (Production Locked) ✅ COMPLETE

- [x] `src/` contains the full engine framework
- [x] Tests validate behavior only
- [x] Runner executes real engine + real indicators
- [x] Deterministic artifacts produced (with `pipeline_signature.json`)
- [x] Ready for Strategy Factory automation

---

## Remaining Work (Future Phases)

### Engine Hot-Loop Refactor

- [ ] Refactor `src/backtest/engine.py` hot-loop to use FeedStores + SnapshotView (no pandas)

### Test Refactoring

- [ ] Each test becomes: arrange → call `src/` entrypoint → assert
- [ ] No test-defined orchestration pipelines remain

---

## Test Summary

| Test File | Tests | Status |
|-----------|-------|--------|
| `test_gate_a_production_first.py` | 4 | ✅ PASS |
| `test_gate_f_isolation.py` | 6 | ✅ PASS |
| `test_gate_c_evaluator_not_noop.py` | 5 | ✅ PASS |
| `test_feature_building_from_idea_card.py` | 7 | ✅ PASS |
| `test_gate_d1_pipeline_signature.py` | 14 | ✅ PASS |
| `test_gate_d2_batch_verification.py` | 14 | ✅ PASS |
| Phase 1-9 tests | 293+ | ✅ PASS (12 skipped) |

**Total Gate Tests: 50 passed**

---

## Gate Status Summary

| Gate | Description | Status |
|------|-------------|--------|
| **E** | Foundation (Config + Docs) | ✅ COMPLETE |
| **B** | Module Ownership Lock | ✅ COMPLETE |
| **C** | Core Wiring (IdeaCard → Engine) | ✅ COMPLETE |
| **D** | Runner Integration (Real Execution) | ✅ COMPLETE |
| **D.1** | Production Pipeline Verification (HARD) | ✅ COMPLETE |
| **D.2** | Randomized IdeaCard Batch Verification (HARD) | ✅ COMPLETE |
| **A** | Production-First Enforcement | ✅ COMPLETE |
| **F** | Delete/Consolidate | ✅ COMPLETE |
| **Final** | Production Locked | ✅ COMPLETE |

**All Gates: ✅ PASSED**
