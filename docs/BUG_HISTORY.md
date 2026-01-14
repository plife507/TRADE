# Bug History

Resolved bugs archive. See [OPEN_BUGS.md](OPEN_BUGS.md) for current issues.

---

## Summary

| Date | Session | Fixed |
|------|---------|-------|
| 2026-01-11 | Audit Swarm Fixes | 13 (2 P0, 4 P1, 7 P2) |
| 2026-01-10 | Structure Module | 4 + 2 doc fixes |
| 2026-01-09 | Senior Dev Audit | 8 (5 P2, 3 P3) |
| 2026-01-07 | DSL Fixes | 5 (2 P1, 3 P2) |
| 2026-01-05 | Engine Fixes | 5 (4 P2, 1 P3) |
| 2026-01-03 | Stress Testing | 9 + crossover |
| 2026-01-03 | Audit Swarm | 72 (7 P0, 25 P1, 28 P2, 12 P3) |

**Total**: 100+ bugs resolved

---

## 2026-01-11 - Audit Swarm Fixes

### P0-001: Unbound Variable exec_tf in Preflight Error Path - FIXED
- **Location**: `src/backtest/runtime/preflight.py:1137`
- **Fix**: Changed to `exec_tf_str or "unknown"`

### P0-002: Exit Fee Uses Entry Notional Instead of Exit Notional - FIXED
- **Location**: `src/backtest/sim/execution/execution_model.py:451-452`
- **Fix**: Changed to `exit_notional = fill_size * fill_price`

### P1-003: MTF Warmup Not Included in Data Window Calculation - FIXED
- **Location**: `src/backtest/runtime/windowing.py:352-357`
- **Fix**: Added MTF warmup span calculation

### P1-004: No Bounds Check for HTF/MTF Index - FIXED
- **Location**: `src/backtest/engine_snapshot.py:63-77`
- **Fix**: Added bounds check before using index

### P1-005: --skip-preflight Bypasses Validation Without Warning - FIXED
- **Location**: `src/backtest/runner.py:378`
- **Fix**: Added warning message

### P1-006: risk_mode="none" Has No User Warning - FIXED
- **Location**: `src/backtest/runner.py:751-757`
- **Fix**: Added warning when risk_mode="none"

### P2-012: IOC/FOK is_first_bar Hardcoded to False - FIXED
- **Location**: `src/backtest/sim/exchange.py:742`
- **Fix**: Added `submission_bar_index` to Order dataclass

### P2-013: Partial Close Entry Fee Not Pro-rated - FIXED
- **Location**: `src/backtest/sim/exchange.py:994-1019`
- **Fix**: Track and pro-rate entry fee on partial close

### P2-014 to P2-018: Various audit fixes (comments, bounds, ts_open) - FIXED

---

## 2026-01-10 - Structure Module Production

### BUG-016: derived_zone Wrong Dependency Key - FIXED
- **Fix**: Changed plays to use `source: swing` in depends_on

### BUG-017: ENUM Literal Treated as Feature Reference - FIXED
- **Fix**: Added ENUM literal detection (ALL_CAPS preserved as scalars)

### BUG-018: Gate 17 Wrong Dependency Keys - FIXED
- **Fix**: Restored correct keys per structure type

### BUG-019: Zone Detector Used Lowercase States - FIXED
- **Fix**: Changed to uppercase states ("NONE", "ACTIVE", "BROKEN")

---

## 2026-01-09 - Senior Dev Audit

### BUG-014: Index Out of Bounds in 1m Subloop - FIXED
- **Location**: `src/backtest/engine.py:1390-1420`
- **Fix**: Clamp both start_1m and end_1m to valid range

### BUG-015: HTF Data Coverage Check Too Strict - FIXED
- **Fix**: Added `floor_to_bar_boundary()` and coverage calculation fix

### P2-AUDIT-01 to P3-AUDIT-03: Various audit fixes - FIXED

---

## 2026-01-07 - DSL Fixes

### P1-001: Crossover Semantics Misaligned with TradingView - FIXED
- **Fix**: Aligned to `cross_above: prev <= rhs AND curr > rhs`

### P1-002: anchor_tf Ignored in Window Operators - FIXED
- **Fix**: Offsets now scale by anchor_tf minutes

### P2-004: Duration Bar Ceiling Missing - FIXED
### P2-005: last_price Offset Support for Crossover - FIXED
### P2-SIM-02: Frozen Fill Dataclass Crash - FIXED

---

## 2026-01-05 - Engine Fixes

### P2-08: Windows Emoji Encoding Breaks Data Sync - FIXED
### P2-09: Backtest Run Requires --smoke or Explicit Dates - FIXED
### P2-10: Structure-Only Plays Rejected - FIXED
### P2-11: Structure References Require Prefix - FIXED
### P3-05: Documentation Mismatch - FIXED

---

## 2026-01-03 - Stress Testing + Audit Swarm

### Crossover Operators Enabled
- `cross_above` and `cross_below` fully supported

### P2-06: Multi-Output Indicator Reference Mismatch - FIXED
### P2-07: Structure Paths Fail Validation - FIXED

### Audit Swarm (72 bugs)
See `docs/archived/audits/2026-01-03_BUGS_RESOLVED.md` for full details.

---

## Audit Checklist (Verified Patterns)

- [x] Determinism: `json.dump()` with `sort_keys=True`
- [x] Fail-Loud: Config fields with `__post_init__` checks
- [x] NaN Handling: `math.isnan()` for NaN checks
- [x] Dead Code: Unused enums removed
- [x] Performance: O(1) hot loop operations
