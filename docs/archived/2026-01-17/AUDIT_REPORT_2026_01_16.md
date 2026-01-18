# TRADE Bot Audit Report

**Date**: 2026-01-16
**Auditors**: 5 parallel agents (engine-core, sim-exchange, security, runtime-structures, validation)
**Branch**: feature/unified-engine

---

## Executive Summary

| Category | P0 | P1 | P2 | P3 | Overall |
|----------|----|----|----|----|---------|
| Engine Core | 3 | 4 | 5 | 3 | Review needed |
| Sim/Exchange | 1 | 4 | 2 | 3 | Review needed |
| Runtime/Structures | 2 | 4 | 4 | 3 | Review needed |
| Security | 0 | 0 | 1 | 0 | PASS |
| **Totals** | **6** | **12** | **12** | **9** | |

### Validation Results (All PASS)

| Test | Result |
|------|--------|
| Indicator Audit | 43/43 PASS |
| Play Normalization | 110/110 PASS |
| Full Smoke Test | 0 failures |
| Structure Registry | 7/7 verified |

---

## P0 Critical Issues (6 total)

### Engine Core (3)

1. **Missing SimulatedExchange Initialization** (`engine.py:257,1028,1268`)
   - `self._exchange` declared as None, never initialized in `__init__`
   - Causes AttributeError if engine instantiated directly without factory

2. **Account Curve Not Initialized** (`engine.py:994-1009`)
   - `self._account_curve` accessed in `_build_result()` but never declared in `__init__`

3. **Potential Off-by-One in TF Index** (`engine_snapshot.py:63-79`)
   - Index update may cause lookahead bias in edge cases

### Sim/Exchange (1)

4. **Risk-Based Sizing Fallback Missing Leverage** (`simulated_risk_manager.py:206-215`)
   - Fallback uses `equity * risk_pct` without multiplying by leverage
   - Positions 10x smaller than expected at 10x leverage

### Runtime/Structures (2)

5. **TFIncrementalState Monotonicity Check** (`state.py:194-201`)
   - Edge case after state reset could reject valid first bar

6. **Derived Zone Hash Missing Type** (`derived_zone.py:362`)
   - `self._type` may be empty string, causing hash collisions

---

## P1 High Priority Issues (12 total)

### Engine Core (4)
- Factory returns PlayEngine with BacktestEngine attributes
- Warmup not validated against data length
- 1m quote feed accumulation may miss bars
- Multi-TF FeedStore missing indicator fallbacks

### Sim/Exchange (4)
- **Slippage favors short trades** (slippage_model.py:79-84) - shorts get better fills
- Limit/stop orders not checked before market order
- Liquidation fee may push equity negative
- Limit fill logic ambiguous for reduce-only orders

### Runtime/Structures (4)
- Hardcoded "atr" indicator key in zone detector
- Stale comparison data in trend detector
- Hardcoded 0.1% zone break tolerance
- Inefficient history pruning (creates new list each time)

---

## P2 Medium Priority Issues (12 total)

- Type annotation inconsistencies (pandas Timestamps)
- Magic numbers (minimum 10 simulation bars)
- Duplicate warmup validation logic
- Broad exception handling in market data loading
- LRU cache potential thrashing
- Risk policy fake position list
- Funding model no symbol validation
- NaN propagation in funding_rate
- Fractal mode params not in REQUIRED_PARAMS
- CHoCH doesn't reset break levels
- SQL injection (LOW RISK - table names from constants)
- Order counter duplication

---

## P3 Low Priority Issues (9 total)

- Inconsistent docstring formatting
- Dead code in run() method
- Comments referencing removed code
- Unused date constants
- Tight floating point tolerance (1e-8)
- RingBuffer uses Python loop
- Unnecessary timezone check
- MonotonicDeque no max size
- Unused total_fees_this_close variable

---

## Security Audit Summary

**Overall: PASS**

| Check | Status |
|-------|--------|
| API keys from env vars only | PASS |
| No hardcoded credentials | PASS |
| Demo/live key separation | PASS |
| Mode validation (DEMO/LIVE) | PASS |
| Risk manager checks | PASS |
| Position size limits | PASS |
| Leverage limits | PASS |
| Panic close functionality | PASS |
| SQL injection protection | LOW RISK |

---

## Recommended Actions

### Immediate (P0)
1. Add `_exchange` and `_account_curve` initialization to `BacktestEngine.__init__`
2. Fix risk-based sizing fallback to apply leverage
3. Review TF index update logic for edge cases

### Short-term (P1)
1. Fix slippage direction for short entries (currently favors shorts)
2. Add validation checks before market order submission
3. Make ATR indicator key configurable in zone detector

### Medium-term (P2)
1. Refactor duplicate code and magic numbers
2. Improve exception handling specificity
3. Add symbol validation to funding model

---

## Validation Commands

```bash
# Quick validation
python trade_cli.py backtest audit-toolkit
python -c "from src.structures import *; print('OK')"

# Full validation
python trade_cli.py --smoke full
```

---

## Files Reviewed

| Module | Files | LOC |
|--------|-------|-----|
| Engine Core | 5 | ~3000 |
| Sim/Exchange | 8 | ~2500 |
| Runtime | 6 | ~2000 |
| Structures | 10 | ~4000 |
| Security | 6 | ~1500 |
| **Total** | **35** | **~13000** |

---

## Conclusion

The TRADE bot passes all automated validation tests (43/43 indicators, 110/110 plays, full smoke test). The codebase demonstrates strong security practices with proper mode separation and API key handling.

However, 6 P0 issues and 12 P1 issues were identified that could affect trading results in edge cases. The most critical are:
1. Risk-based sizing fallback not applying leverage
2. Slippage model favoring short trades
3. Uninitialized engine attributes

These should be reviewed and addressed before production use.
