# P0: Warmup Synchronization Fix

**Status**: ✅ COMPLETE  
**Created**: 2024-12-17  
**Completed**: 2024-12-17  
**Priority**: P0 - Blocks correct backtest execution  

## Problem Statement

Preflight and Engine use **different warmup sources**, causing data range mismatch:

| Component | Warmup Source | Example Result |
|-----------|---------------|----------------|
| Preflight | `tf_config.effective_warmup_bars` | 200 bars |
| Engine | `get_warmup_from_specs() × multiplier` | 100 bars |

The IdeaCard's explicit `warmup_bars: 200` is ignored by the engine.

## Root Cause

Engine factory (`runner.py`) creates `SystemConfig` without passing IdeaCard warmup:
- `SystemConfig` defaults to `warmup_multiplier=5`
- Engine recomputes warmup: `max(spec.warmup_bars) × 5`
- IdeaCard's `tf_config.warmup_bars` is never consulted

## Fix Plan

### Phase 1: Wire IdeaCard Warmup to SystemConfig
- [x] 1.1: Add `warmup_bars_by_role: Dict[str, int]` field to `SystemConfig`
- [x] 1.2: In engine factory, compute warmup using `compute_warmup_requirements()`
- [x] 1.3: Pass `warmup_bars_by_role` to SystemConfig constructor

### Phase 2: Engine Uses Declared Warmup
- [x] 2.1: Modify `prepare_backtest_frame()` to use `self.config.warmup_bars_by_role['exec']`
- [x] 2.2: Modify `prepare_multi_tf_backtest_frame()` to use per-role warmup
- [x] 2.3: FAIL LOUD if warmup_bars_by_role not set (no legacy fallbacks)

### Phase 3: Validation Gate
- [x] 3.1: Add warning log when preflight/engine warmup mismatch
- [x] 3.2: Warmup values now shown in both preflight and engine logs
- [x] 3.3: Tested with stress test card (exec: 200 bars, htf: 150 bars)

## Acceptance Criteria

1. **Preflight warmup == Engine warmup** for same IdeaCard
2. IdeaCard's explicit `warmup_bars` is respected
3. `bars_history_required` is respected
4. No silent fallbacks to spec-derived warmup

## Files to Modify

- `src/backtest/system_config.py` - Add `warmup_bars_by_role` field
- `src/backtest/runner.py` - Wire warmup from IdeaCard validation
- `src/backtest/engine.py` - Use config warmup instead of recomputing

## Test Command

```bash
python trade_cli.py backtest run --idea-card test__batch6_hlc_multi__BTCUSDT_15m --start 2024-11-01 --end 2024-11-02 --data-env live
```

Verify: Preflight "Warmup: X bars" == Engine "warm-up: X bars"
