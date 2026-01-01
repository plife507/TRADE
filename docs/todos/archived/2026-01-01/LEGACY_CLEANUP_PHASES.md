# Legacy Cleanup Phases

**Created**: 2025-12-31
**Status**: ✅ ALL PHASES COMPLETE
**Context**: Code review identified legacy items, duplicates, and inconsistencies to clean up

---

## Problem Statement

Comprehensive code review of simulator, database, and audit modules identified:
- Legacy fields marked "for backward compatibility" but never used
- Dual systems running in parallel (metrics v1 vs v2)
- Enum/type duplications across modules
- Naming inconsistencies
- Dead code paths

---

## Phase 1: Remove Legacy ExecutionConfig Fields ✓ COMPLETE

**Goal**: Clean up ExecutionConfig to only contain used fields

### Tasks

- [x] 1.1 Remove `taker_fee_bps` from ExecutionConfig (fees come from RiskProfileConfig)
- [x] 1.2 Update engine.py to not pass taker_fee_bps
- [x] 1.3 Update audit to check RiskProfileConfig.taker_fee_rate instead
- [x] 1.4 Validate imports and field structure

### Files to Modify

| File | Change |
|------|--------|
| `src/backtest/sim/types.py` | Remove taker_fee_bps field and taker_fee_rate property |
| `src/backtest/engine.py` | Verify ExecutionConfig instantiation doesn't pass taker_fee_bps |

### Gate 1.1: ExecutionConfig Cleanup

```bash
python -c "from src.backtest.sim.types import ExecutionConfig; print(ExecutionConfig())"
python trade_cli.py --smoke full
```

---

## Phase 2: Consolidate Metrics Systems ✓ COMPLETE

**Goal**: Single metrics format - extend v1 with v2's unique fields, remove v2

**Decision**: Keep `BacktestMetrics` (v1) as canonical, add v2's unique value-add fields

### Sub-Phase 2.1: Add v2 Unique Fields to BacktestMetrics ✓

**Files**: `src/backtest/types.py`

- [x] 2.1.1 Add `ulcer_index: float = 0.0` (from v2.drawdown)
- [x] 2.1.2 Add `profit_factor_mode: str = "finite"` (from v2 ProfitFactorResult)
- [x] 2.1.3 Add `entry_attempts: int = 0` (from v2.entry_friction)
- [x] 2.1.4 Add `entry_rejections: int = 0` (from v2.entry_friction)
- [x] 2.1.5 Add `entry_rejection_rate: float = 0.0` (from v2.entry_friction)
- [x] 2.1.6 Add `min_margin_ratio: float = 1.0` (from v2.margin_stress)
- [x] 2.1.7 Add `margin_calls: int = 0` (from v2.margin_stress)
- [x] 2.1.8 Add `closest_liquidation_pct: float = 100.0` (from v2.liquidation_proximity)
- [x] 2.1.9 Update `to_dict()` with new fields

**Gate 2.1**: PASSED

### Sub-Phase 2.2: Update compute_backtest_metrics() ✓

**Files**: `src/backtest/metrics.py`

- [x] 2.2.1 Add `_compute_ulcer_index()` helper function
- [x] 2.2.2 Add entry_attempts/rejections params to function signature
- [x] 2.2.3 Compute profit_factor_mode (finite/infinite/undefined)
- [x] 2.2.4 Compute ulcer_index from equity curve
- [x] 2.2.5 Add margin stress params (optional, from exchange)
- [x] 2.2.6 Return extended BacktestMetrics

**Gate 2.2**: PASSED

### Sub-Phase 2.3: Update Engine to Pass Extended Params ✓

**Files**: `src/backtest/engine.py`

- [x] 2.3.1 Pass entry_attempts/rejections to compute_backtest_metrics
- [x] 2.3.2 Compute margin stress data from account_curve
- [x] 2.3.3 Remove compute_proof_metrics call
- [x] 2.3.4 Remove metrics_v2 from BacktestResult

**Gate 2.3**: PASSED

### Sub-Phase 2.4: Remove v2 System ✓

**Files**: `src/backtest/proof_metrics.py`, `src/backtest/proof_metrics_types.py`, `src/backtest/__init__.py`

- [x] 2.4.1 Delete `src/backtest/proof_metrics.py`
- [x] 2.4.2 Delete `src/backtest/proof_metrics_types.py`
- [x] 2.4.3 Remove v2 exports from `__init__.py`
- [x] 2.4.4 Update any remaining imports

**Gate 2.4**: PASSED

### Sub-Phase 2.5: Final Validation ✓

- [x] 2.5.1 All new fields present in BacktestMetrics
- [x] 2.5.2 compute_backtest_metrics works with new params
- [x] 2.5.3 BacktestResult has no metrics_v2

**Gate 2.5**: PASSED

---

## Phase 3: Remove Unused RiskProfileConfig Fields - NO ACTION NEEDED

**Goal**: Remove config fields that are defined but never read

### Audit Findings

- [x] 3.1 `maker_fee_rate`: Placeholder for future multi-fee models (intentional)
- [x] 3.2 `include_est_close_fee_in_entry_gate`: **ACTIVELY USED** for entry gate threshold
- [x] 3.3 `fee_mode`: Placeholder for future fee mode switching (intentional)
- [x] 3.4 Mode locks (margin_mode, position_mode, quote_ccy, instrument_type):
  - Validated once at config load (fail-loud design)
  - Not read at runtime (MVP: isolated/oneway/USDT/perp only)
  - **Intentional validation hooks** per CLAUDE.md "fail loud" philosophy

### Decision

**NO CLEANUP NEEDED** - All fields serve legitimate purposes:
- Reserved placeholders for Phase 2+ features
- Validation hooks for MVP constraints
- Active feature flags

---

## Phase 4: Standardize Position/Direction Enums - NO ACTION NEEDED

**Goal**: Single enum for position direction, imported consistently

### Audit Findings

- [x] 4.1 `OrderSide` (sim/types.py): Unique enum for order direction (BUY/SELL) - correctly scoped
- [x] 4.2 `PositionMode` (system_config.py): Exchange mode placeholder (ONEWAY/HEDGE) - never used as type
- [x] 4.3 `PositionMode` (idea_card.py): Strategy policy (LONG_ONLY/SHORT_ONLY/LONG_SHORT) - actively used

### Decision

**NO CLEANUP NEEDED** - These are semantically different concepts:
- `OrderSide`: Order execution direction
- `system_config.PositionMode`: Exchange-level mode (placeholder, uses string field)
- `idea_card.PositionMode`: Strategy direction policy (actively used)

No import collision exists - they're in separate modules with distinct purposes.

---

## Phase 5: Standardize Timestamp Columns - NO ACTION NEEDED

**Goal**: Single naming convention for timestamp columns

### Audit Findings

- [x] 5.1 `ts_ms`: Artifact columns (integer milliseconds) - standardized per artifact_standards.py
- [x] 5.2 `ts_close`: Event logs (bar close semantic context) - domain appropriate
- [x] 5.3 `timestamp`: Type fields (datetime objects) - Python idiomatic

### Decision

**NO CLEANUP NEEDED** - Naming is domain-appropriate:
- Numeric columns: `ts_ms` (milliseconds for parquet/analytics)
- Event context: `ts_close` (indicates which bar closed)
- Object fields: `timestamp` (datetime for API/display)

---

## Phase 6: Naming Consistency (sim_start_index) - NO ACTION NEEDED

**Goal**: Consistent variable naming across engine modules

### Audit Findings

- [x] 6.1 `sim_start_idx`: Local computation variable (short form)
- [x] 6.2 `sim_start_index`: Dataclass field name (descriptive form)
- [x] 6.3 `max_lookback` → `max_indicator_lookback`: Same pattern (local → field)

### Decision

**NO CLEANUP NEEDED** - Pattern is intentional and idiomatic:
- Short variable names for local computations
- Descriptive field names for dataclass attributes
- Assignment: `sim_start_index=sim_start_idx` is clear

---

## Phase 7: Document IdeaCard → Engine Flow ✓ COMPLETE

**Goal**: Clear documentation of how IdeaCard fields map to engine config

### Tasks

- [x] 7.1 Create architecture doc: `docs/architecture/IDEACARD_ENGINE_FLOW.md`
- [x] 7.2 Document each IdeaCard field and where it flows
- [x] 7.3 Document which fields are required vs optional
- [x] 7.4 Link from CLAUDE.md

### Completed (2026-01-01)

Created comprehensive documentation covering:
- Flow diagram (ASCII art)
- Complete field mappings (Identity, Account, Symbol, TF, Position, Signal, Risk)
- Required vs optional fields table
- Engine factory flow step-by-step
- Preflight gate integration

---

## Phase 8: PreparedFrame.full_df - KEEP (Not Dead)

**Goal**: Investigate if unused

### Finding

- [x] 8.1 Verified: full_df IS actively used by runner.py:656 for metadata extraction
- **Decision**: KEEP - not dead code

---

## Phase 9: Remove MultiTFPreparedFrames Helper Methods ✓ COMPLETE

**Goal**: Remove unused helper methods

### Tasks

- [x] 9.1 Verified: get_htf/mtf/ltf_close_ts() are NEVER called
- [x] 9.2 Removed the methods (2025-12-31)
- [x] 9.3 Validated imports

### Change Made

Removed dead methods from `MultiTFPreparedFrames` class. Functionality available via `close_ts_maps.get(tf, set())`.

---

## Phase 10: warmup_multiplier ✓ COMPLETE

**Goal**: Remove hardcoded warmup_multiplier=1 field

### Tasks

- [x] 10.1 Verified: warmup_multiplier IS hardcoded to 1 in engine_data_prep.py
- [x] 10.2 Remove DEFAULT_WARMUP_MULTIPLIER from indicators.py
- [x] 10.3 Remove warmup_multiplier from SystemConfig
- [x] 10.4 Remove warmup_multiplier from BacktestResult
- [x] 10.5 Remove warmup_multiplier from PreparedFrame
- [x] 10.6 Update windowing.py (remove DEFAULT_WARMUP_MULTIPLIER, simplify functions)
- [x] 10.7 Update smoke_tests.py (remove warmup_multiplier check)
- [x] 10.8 Update backtest_tools.py (remove multiplier from function calls)
- [x] 10.9 Remove warmup_multiplier from SystemConfig.to_canonical_dict()
- [x] 10.10 Run backtest tests

### Files Modified

| File | Change |
|------|--------|
| `src/backtest/indicators.py` | Removed DEFAULT_WARMUP_MULTIPLIER, simplified functions |
| `src/backtest/system_config.py` | Removed warmup_multiplier field and import |
| `src/backtest/types.py` | Removed warmup_multiplier from BacktestResult |
| `src/backtest/engine_data_prep.py` | Removed warmup_multiplier from PreparedFrame |
| `src/backtest/engine.py` | Removed warmup_multiplier references |
| `src/backtest/runtime/windowing.py` | Removed DEFAULT_WARMUP_MULTIPLIER, simplified WarmupConfig |
| `src/cli/smoke_tests.py` | Removed warmup_multiplier validation check |
| `src/tools/backtest_tools.py` | Removed multiplier from function calls |

### Completed (2026-01-01)

Warmup is now computed directly in FeatureSpec.warmup_bars based on indicator type.
No multiplier concept needed - Preflight computes final warmup_bars per role.

---

## Validation Matrix

| Phase | Gate | Command | Pass Criteria | Status |
|-------|------|---------|---------------|--------|
| 1 | ExecutionConfig | `--smoke full` | No taker_fee_bps references | ✅ COMPLETE |
| 2 | Metrics | `backtest run` | Single metrics format (extended with 8 new fields) | ✅ COMPLETE |
| 2 | Metrics Extension | `--smoke full` | All 59 fields computed, smoke tests pass | ✅ COMPLETE |
| 3 | RiskProfileConfig | Import test | All fields serve purpose | ✅ AUDITED |
| 4 | Enums | Grep audit | Semantically distinct (no collision) | ✅ AUDITED |
| 5 | Timestamps | Artifact export | Domain-appropriate naming | ✅ AUDITED |
| 6 | Naming | Grep audit | Idiomatic local→field pattern | ✅ AUDITED |
| 7 | Docs | Doc exists | Flow documented | ✅ COMPLETE |
| 8 | full_df | `--smoke full` | Actively used (keep) | ✅ AUDITED |
| 9 | Helpers | `--smoke full` | Methods removed | ✅ COMPLETE |
| 10 | warmup_multiplier | `backtest run` | Removed from all modules | ✅ COMPLETE |

---

## Already Completed (This Session)

### Session 1: Core Legacy Cleanup (2025-12-31)

**Early Session (Code Review)**
- [x] StopReason enum consolidation (sim/types.py now imports from types.py)
- [x] Dead warmup functions removed from indicator_vendor.py (8 functions)
- [x] Unused imports removed from engine.py (4 imports)
- [x] History deques removed from snapshot_view.py (3 deques + simplified _get_prev_indicator)

**Phase Execution**
- [x] **Phase 1**: ExecutionConfig.taker_fee_bps removed (slippage_bps only now)
- [x] **Phase 1**: Audit updated to check RiskProfileConfig.taker_fee_rate
- [x] **Phase 2**: Metrics consolidated (v1 extended with v2 fields, v2 removed)
- [x] **Phase 3**: RiskProfileConfig audited - all fields serve purpose (no cleanup needed)
- [x] **Phase 4**: Enum duplication audited - semantically different enums, no collision (no cleanup needed)
- [x] **Phase 5**: Timestamp naming audited - domain-appropriate naming (no cleanup needed)
- [x] **Phase 6**: Variable naming audited - idiomatic local→field pattern (no cleanup needed)
- [x] **Phase 8**: PreparedFrame.full_df audited - actively used (keep)
- [x] **Phase 9**: Dead helper methods removed from MultiTFPreparedFrames
- [x] **Phase 10**: warmup_multiplier audited - still referenced by Preflight (defer)

### Session 2: High-Value Metrics Extension (2026-01-01)

**Metrics System Enhancement**
- [x] Removed v1/v2 terminology from all code comments
- [x] Added 8 new high-value metrics to BacktestMetrics:
  - `skewness: float` - Distribution skewness of returns
  - `kurtosis: float` - Distribution kurtosis of returns
  - `var_95: float` - Value at Risk (95% confidence)
  - `cvar_95: float` - Conditional Value at Risk (95% confidence)
  - `avg_leverage_used: float` - Average leverage across all positions
  - `max_gross_exposure_pct: float` - Peak gross exposure as % of equity
  - `mae_avg_pct: float` - Average Maximum Adverse Excursion %
  - `mfe_avg_pct: float` - Average Maximum Favorable Excursion %
- [x] Implemented MAE/MFE tracking in Position and Trade dataclasses
- [x] Updated compute_backtest_metrics() to compute all new metrics
- [x] BacktestMetrics now has 59 fields (up from 51)
- [x] All smoke tests pass with extended metrics

---

## All Phases Complete

| Phase | Status | Notes |
|-------|--------|-------|
| 1-6 | ✅ COMPLETE | Core cleanup, metrics consolidation, audits |
| 7 | ✅ COMPLETE | IdeaCard flow documentation created |
| 8-9 | ✅ COMPLETE | full_df audit, helper methods removed |
| 10 | ✅ COMPLETE | warmup_multiplier fully removed (2026-01-01) |

---

## Acceptance Criteria

- [x] ExecutionConfig cleaned (slippage only)
- [x] Dead methods removed from MultiTFPreparedFrames
- [x] RiskProfileConfig fields audited (all valid)
- [x] Consistent enum definitions audited (semantically different, no action needed)
- [x] Consistent naming conventions audited (domain-appropriate, no action needed)
- [x] Single metrics system fully consolidated:
  - Original fields (41): Basic performance, trade stats, drawdown metrics
  - Phase 2.1 extensions (10): Ulcer index, entry friction, margin stress, liquidation proximity
  - Session 2 extensions (8): Skewness, kurtosis, VaR/CVaR, leverage/exposure, MAE/MFE
  - **Total: 59 fields**
- [x] No v1/v2 terminology in codebase
- [x] MAE/MFE tracked at position and trade level
- [x] Clear IdeaCard → Engine flow documentation - COMPLETE
- [x] warmup_multiplier removed from entire codebase (Phase 10)
- [x] All smoke tests pass - VALIDATED
