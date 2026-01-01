# Audit Bugs Index

**PURPOSE:** Known failures, regressions, incident notes

---

## P0 Blockers (Critical)

### BUG-001: Input-Source Routing

**Status:** 🔴 OPEN  
**Severity:** P0 BLOCKER  
**Location:** `src/backtest/features/feature_frame_builder.py` lines 633, 674

**Description:**
Non-"close" input sources (volume, open, high, low, hlc3, ohlc4) route to wrong data column in FeatureFrameBuilder.

**Symptom:**
- `volume_sma` shows 102K discrepancy vs pandas_ta
- Affects any indicator using non-close input

**Root Cause:**
Conditional logic routes `input_series` incorrectly when `input_source != "close"`.

**Impact:**
- Phase 5 (Market Structure) blocked
- Math parity audit fails for volume/OHLC-based indicators

**Fix Required:**
Change `close=input_series if spec.input_source == CLOSE else ohlcv["close"]` to `close=input_series` in affected locations.

**References:**
- `docs/contracts/state_of_the_union.md`
- `docs/_archived/audits__volume_sma_bug_diagnosis.md`

---

## P2 Issues (Medium)

### BUG-002: Duplicate ExchangeState Class

**Status:** 🟡 OPEN  
**Severity:** P2  
**Location:** 
- `src/backtest/sim/types.py`
- `src/backtest/runtime/types.py`

**Description:**
`ExchangeState` dataclass defined in two places with potentially different fields.

**Impact:**
- Confusion for developers
- Potential import conflicts

**Fix Required:**
Audit usage, consolidate to single location, alias if needed.

---

## P3 Issues (Low)

### BUG-003: Misplaced Config Files

**Status:** 🟡 OPEN  
**Severity:** P3  
**Location:** `src/strategies/configs/`, `src/strategies/idea_cards/`

**Description:**
Strategy configs and example IdeaCards in wrong location. Canonical location is `configs/idea_cards/`.

**Impact:**
- Confusion about canonical location
- Potential for stale examples

**Fix Required:**
Move or delete files, update references.

---

## Resolved Bugs

| Bug ID | Description | Resolution Date |
|--------|-------------|-----------------|
| — | (No resolved P0/P1 bugs yet) | — |

---

