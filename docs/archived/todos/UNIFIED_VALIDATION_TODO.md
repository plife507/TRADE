# TODO: Unified Validation Architecture

> **Created**: 2026-01-11
> **Status**: Complete
> **Plan**: `C:\Users\507pl\.claude\plans\velvety-forging-dusk.md`

---

## Goal

All validation runs through BacktestEngine with injectable synthetic data. Single code path, single data source, no divergence.

---

## GATE 0: Foundation - Unify Synthetic Data
**Status**: [x] Complete (2026-01-11)

### Tasks
- [x] Add `generate_synthetic_ohlcv_df()` to `src/forge/validation/synthetic_data.py`
- [x] Add `generate_synthetic_quotes()` to `src/forge/validation/synthetic_data.py`
- [x] Add `generate_synthetic_bars()` to `src/forge/validation/synthetic_data.py`
- [x] Update `src/forge/audits/toolkit_contract_audit.py` to import from canonical
- [x] Update `src/forge/audits/audit_rollup_parity.py` to import from canonical
- [ ] Update `src/viz/api/indicators.py` to import from canonical (optional - deferred)

### Checkpoint
```bash
python -c "from src.forge.validation.synthetic_data import generate_synthetic_ohlcv_df, generate_synthetic_quotes"
python trade_cli.py backtest audit-toolkit
```

---

## GATE 1: Engine Injection
**Status**: [x] Complete (2026-01-11)

### Tasks
- [x] Create `src/forge/validation/synthetic_provider.py` with `SyntheticDataProvider` protocol
- [x] Create `SyntheticCandlesProvider` adapter class
- [x] Add `BacktestEngine.with_synthetic_data()` classmethod to `src/backtest/engine.py`
- [x] Modify `prepare_backtest_frame_impl()` to accept `synthetic_provider` param
- [x] Modify `prepare_multi_tf_frames_impl()` to accept `synthetic_provider` param
- [x] Modify `load_1m_data_impl()` to accept `synthetic_provider` param

### Checkpoint
```bash
python -c "from src.forge.validation.synthetic_provider import SyntheticCandlesProvider"
# Test engine creation with synthetic data
```

---

## GATE 2: Integration Tests
**Status**: [x] Complete (2026-01-11)

### Tasks
- [x] Create `tests/validation/plays/indicators/` directory
- [x] Create V_IND_001 through V_IND_010 (representative indicators)
- [x] Create `tests/validation/plays/structures/` directory
- [x] Create V_STR_001 through V_STR_006 (one per structure type)

### Notes
Created 10 representative indicator plays covering key categories:
- V_IND_001_ema - Moving average (single-output, length param)
- V_IND_002_rsi - Oscillator (0-100 range)
- V_IND_003_atr - Volatility (HLC inputs)
- V_IND_004_macd - Multi-output (fast/slow/signal)
- V_IND_005_bbands - Multi-output bands (lower/middle/upper/bandwidth/percent_b)
- V_IND_006_stoch - Multi-output oscillator (k/d)
- V_IND_007_adx - Trend strength (adx/dmp/dmn/adxr)
- V_IND_008_supertrend - Mutually exclusive outputs (direction/long/short)
- V_IND_009_vwap - Volume-weighted (HLCV inputs, anchor param)
- V_IND_010_squeeze - Discrete states (sqz/on/off/no_sqz)

### Checkpoint
```bash
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays/indicators
python trade_cli.py backtest play-normalize-batch --dir tests/validation/plays/structures
```

---

## GATE 3: Migrate Hybrid Audits
**Status**: [x] Complete (2026-01-11)

### Tasks
- [x] Add `run_rollup_parity_via_engine()` to `audit_rollup_parity.py`
- [x] Add `run_incremental_state_via_engine()` to `audit_incremental_state.py`
- [x] Update `create_engine_from_play()` to support `synthetic_provider` parameter
- [ ] Add `--mode engine` flag to CLI commands (deferred - functions available for programmatic use)

### Notes
Engine mode functions added to both audits:
- `run_rollup_parity_via_engine()`: Uses on_snapshot callback to validate rollups during engine execution
- `run_incremental_state_via_engine()`: Runs a Play with structures through the engine
- `create_engine_from_play()`: Now accepts `synthetic_provider` parameter for DB-free execution

### Checkpoint (Programmatic)
```python
from src.forge.audits.audit_rollup_parity import run_rollup_parity_via_engine
result = run_rollup_parity_via_engine()
print(f"Rollup engine mode: {'PASS' if result.success else 'FAIL'}")

from src.forge.audits.audit_incremental_state import run_incremental_state_via_engine
result = run_incremental_state_via_engine()
print(f"State engine mode: {'PASS' if result['success'] else 'FAIL'}")
```

---

## GATE 4: CLI Integration
**Status**: [x] Complete (2026-01-11)

### Tasks
- [x] Add `--synthetic` flag to `src/backtest/runner.py`
- [x] Implement step 7 in `stress_test_suite.py`
- [x] Update Forge menu with new options (option 7: "Run Play (Synthetic)")

### Notes
Added `--synthetic` flag with supporting options:
- `--synthetic-bars`: Number of bars per timeframe (default: 1000)
- `--synthetic-seed`: Random seed for reproducibility (default: 42)
- `--synthetic-pattern`: Data pattern (trending/ranging/volatile, default: trending)

Step 7 in stress_test_suite now executes validation plays through the engine with synthetic data.
Forge menu option 7 allows interactive synthetic backtest runs.

### Checkpoint
```bash
# Test import chain
python -c "from src.backtest.runner import run_backtest_with_gates; from src.forge.audits.stress_test_suite import _step_backtest_execution"

# Test synthetic provider
python -c "from src.forge.validation.synthetic_provider import SyntheticCandlesProvider; print('OK')"
```

### Known Issue
Validation plays V_IND_* use shorthand DSL format `["lhs", "op", "rhs"]` which requires
dict format `{lhs: ..., op: ..., rhs: ...}`. Plays need format update to run through engine.

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
| 2 | `tests/validation/plays/indicators/*.yml` | NEW - 10 representative plays |
| 2 | `tests/validation/plays/structures/*.yml` | NEW - 6 plays |
| 3 | `src/forge/audits/audit_rollup_parity.py` | Add engine mode |
| 3 | `src/forge/audits/audit_incremental_state.py` | Add engine mode |
| 4 | `src/backtest/runner.py` | Add --synthetic flag |
| 4 | `src/forge/audits/stress_test_suite.py` | Implement step 7 |
| 4 | `src/cli/menus/forge_menu.py` | Add synthetic backtest option |

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
