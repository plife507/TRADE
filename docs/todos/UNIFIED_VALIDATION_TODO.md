# TODO: Unified Validation Architecture

> **Created**: 2026-01-11
> **Status**: In Progress
> **Plan**: `C:\Users\507pl\.claude\plans\velvety-forging-dusk.md`

---

## Goal

All validation runs through BacktestEngine with injectable synthetic data. Single code path, single data source, no divergence.

---

## GATE 0: Foundation - Unify Synthetic Data
**Status**: [ ] Not Started

### Tasks
- [ ] Add `generate_synthetic_ohlcv_df()` to `src/forge/validation/synthetic_data.py`
- [ ] Add `generate_synthetic_quotes()` to `src/forge/validation/synthetic_data.py`
- [ ] Add `generate_synthetic_bars()` to `src/forge/validation/synthetic_data.py`
- [ ] Update `src/forge/audits/toolkit_contract_audit.py` to import from canonical
- [ ] Update `src/forge/audits/audit_rollup_parity.py` to import from canonical
- [ ] Update `src/viz/api/indicators.py` to import from canonical (optional)

### Checkpoint
```bash
python -c "from src.forge.validation.synthetic_data import generate_synthetic_ohlcv_df, generate_synthetic_quotes"
python trade_cli.py backtest audit-toolkit
```

---

## GATE 1: Engine Injection
**Status**: [ ] Not Started

### Tasks
- [ ] Create `src/forge/validation/synthetic_provider.py` with `SyntheticDataProvider` protocol
- [ ] Create `SyntheticCandlesProvider` adapter class
- [ ] Add `BacktestEngine.with_synthetic_data()` classmethod to `src/backtest/engine.py`
- [ ] Modify `prepare_backtest_frame_impl()` to accept `synthetic_provider` param
- [ ] Modify `prepare_multi_tf_frames_impl()` to accept `synthetic_provider` param

### Checkpoint
```bash
python -c "from src.forge.validation.synthetic_provider import SyntheticCandlesProvider"
# Test engine creation with synthetic data
```

---

## GATE 2: Integration Tests
**Status**: [ ] Not Started

### Tasks
- [ ] Create `tests/validation/plays/indicators/` directory
- [ ] Create V_IND_001 through V_IND_043 (one per indicator)
- [ ] Create `tests/validation/plays/structures/` directory
- [ ] Create V_STR_001 through V_STR_006 (one per structure type)

### Checkpoint
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays/indicators
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays/structures
```

---

## GATE 3: Migrate Hybrid Audits
**Status**: [ ] Not Started

### Tasks
- [ ] Add `run_rollup_parity_via_engine()` to `audit_rollup_parity.py`
- [ ] Add `run_incremental_state_via_play()` to `audit_incremental_state.py`
- [ ] Add `--mode engine` flag to CLI commands

### Checkpoint
```bash
python trade_cli.py forge audit-rollup --mode engine
python trade_cli.py forge audit-state --mode engine
```

---

## GATE 4: CLI Integration
**Status**: [ ] Not Started

### Tasks
- [ ] Add `--synthetic` flag to `src/backtest/runner.py`
- [ ] Implement step 7 in `stress_test_suite.py`
- [ ] Update Forge menu with new options

### Checkpoint
```bash
python trade_cli.py backtest run --play V_IND_001_ema --synthetic
python trade_cli.py forge stress-test --no-db
```

---

## Files Summary

| Gate | File | Change |
|------|------|--------|
| 0 | `src/forge/validation/synthetic_data.py` | Add generator functions |
| 0 | `src/forge/audits/toolkit_contract_audit.py` | Import from canonical |
| 0 | `src/forge/audits/audit_rollup_parity.py` | Import from canonical |
| 1 | `src/forge/validation/synthetic_provider.py` | NEW |
| 1 | `src/backtest/engine.py` | Add with_synthetic_data() |
| 1 | `src/backtest/engine_data_prep.py` | Support synthetic provider |
| 2 | `tests/validation/plays/indicators/*.yml` | NEW - 43 plays |
| 2 | `tests/validation/plays/structures/*.yml` | NEW - 6 plays |
| 3 | `src/forge/audits/audit_rollup_parity.py` | Add engine mode |
| 3 | `src/forge/audits/audit_incremental_state.py` | Add engine mode |
| 4 | `src/backtest/runner.py` | Add --synthetic flag |
| 4 | `src/forge/audits/stress_test_suite.py` | Implement step 7 |

---

## Completed This Session (Pre-Gate Work)

- [x] Fix ts_open in `toolkit_contract_audit.py`
- [x] Fix ts_open in `audit_math_parity.py`
- [x] Fix ts_open in `audit_in_memory_parity.py`
- [x] Create `docs/architecture/VALIDATION_ARCHITECTURE.md`
- [x] Update `docs/audits/OPEN_BUGS.md` with P2-016, P2-017, P2-018

---

## Modularity Rules

- **UNIT audits (7)**: Keep unchanged - pure component tests
- **INTEGRATION audits (6)**: Already use engine - no changes
- **HYBRID audits (2)**: Add engine mode, keep unit mode
- **No monolith**: Each gate is independently valuable
