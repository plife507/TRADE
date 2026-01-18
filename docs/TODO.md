# TRADE TODO

Active work tracking for the TRADE trading bot.

---

## Current Phase: Engine Verification

### P0: Validation Infrastructure
- [x] Create minimal smoke test Play (T_001_minimal.yml)
- [x] Create structure validation Plays (V_STRUCT_001-004)
- [x] Verify engine runs with new Plays (--smoke backtest passes)
- [ ] Create indicator coverage Plays (F_IND_*)

### P1: Engine Verification
- [ ] Run full backtest with validation Play
- [ ] Verify trade execution logic
- [ ] Verify metrics calculations
- [ ] Verify artifact generation

---

## Backlog

### P2: Indicator Coverage
- [ ] Create F_IND_001 through F_IND_043 Plays
- [ ] Verify all 43 indicators work in engine context

### P3: Structure Coverage
- [ ] Verify all 7 structure types work
- [ ] Create stress test Plays for structures

---

## Completed

### 2026-01-17: Validation Infrastructure
- [x] Fixed Play directory paths (strategies/plays/ → tests/*/plays/)
- [x] Created T_001_minimal.yml smoke test Play
- [x] Created V_STRUCT_001-004 structure validation Plays
- [x] Verified --smoke backtest passes with new Plays
- [x] Engine verified: preflight, data loading, execution, artifact generation

### 2026-01-17: Agent Configuration Update
- [x] Updated all agents with correct validation mapping
- [x] Removed deprecated paths (strategies/plays/, docs/todos/)
- [x] Updated structure count to 7
- [x] Updated timeframe syntax in templates
