# CLI-Only Validation Migration

> **Objective**: Refactor all backtest/data/indicator verification to run via CLI commands only. Delete pytest files for these areas.

## Hard Rules

- No `tests/test_*.py` files for backtest/data/indicator validation
- All validation via CLI subcommands: CLI -> tools layer -> domain -> DuckDB/engine
- Keep unit tests only for pure library functions (not pipeline validation)

---

## Phase A — CLI Commands (Must Exist)

### A1. Dataset Preflight
- [x] `python trade_cli.py backtest preflight --data-env live --idea-card ...`
- [x] Prints: data-env, DB path, table, symbol, tf, requested vs effective window
- [x] Coverage verdict: OK / missing ranges + guidance
- [x] Rename `--env` to `--data-env` for clarity
- [x] Add `--fix-gaps` flag that calls existing DuckDB tools

### A2. Indicator Key Discovery
- [x] Add `python trade_cli.py backtest indicators --idea-card ... --print-keys`
- [x] Print all computed keys by scope (exec, htf, mtf)
- [x] Show exact names (e.g., `stoch_k`, `stoch_d`, `macd_signal`)

### A3. Smoke Backtest
- [x] `python trade_cli.py backtest run --idea-card ... --smoke --strict`
- [x] Runs full pipeline: load -> indicators -> warmup -> simulation
- [x] Exit non-zero with actionable messages on failure
- [x] Rename `--env` to `--data-env`

### A4. JSON Output
- [x] Add `--json` flag to all backtest commands
- [x] Structured output: status, checks, details, recommended fix commands
- [x] For agents/CI consumption

---

## Phase B — Inventory and Map pytest Files

### B1. Files Reviewed and Deleted
- [x] `tests/test_backtest_cli_wrapper.py` - CLI wrapper tests -> DELETED
- [x] `tests/test_backtest_preflight_data_health_gate.py` - Data health tests -> DELETED
- [x] `tests/test_backtest_no_lookahead_mtf_htf.py` - MTF/HTF tests -> DELETED
- [x] `tests/test_backtest_mark_price_unification.py` - Mark price tests -> DELETED
- [x] `tests/test_backtest_funding_window_semantics.py` - Funding tests -> DELETED

### B2. Mapping to CLI Commands
| pytest file (DELETED) | CLI equivalent |
|----------------------|----------------|
| test_backtest_cli_wrapper.py | `backtest preflight`, `backtest indicators`, `backtest run --smoke` |
| test_backtest_preflight_data_health_gate.py | `backtest preflight --data-env ...` |
| test_backtest_no_lookahead_mtf_htf.py | `backtest run --smoke --strict` |
| test_backtest_mark_price_unification.py | `backtest run --smoke --strict` |
| test_backtest_funding_window_semantics.py | `backtest preflight --data-env ...` |

---

## Phase C — Port Behaviors to CLI

### C1. Exit Codes
- [x] Exit 0 on success (PASS)
- [x] Exit non-zero on failure with explicit reason (FAIL)

### C2. Actionable Messages
- [x] Coverage issues include fix commands
- [x] Missing indicator keys list available keys
- [x] NaN issues distinguish warmup vs coverage

### C3. JSON Output Schema
- [x] Implemented in all backtest commands
```json
{
  "status": "pass|fail",
  "message": "description",
  "checks": {"idea_card_valid": true, "has_sufficient_coverage": false},
  "data": {...},
  "recommended_fix": "python trade_cli.py backtest data-fix ..."
}
```

---

## Phase D — Delete pytest Files

### D1. Files Deleted
- [x] `tests/test_backtest_cli_wrapper.py` - DELETED
- [x] `tests/test_backtest_preflight_data_health_gate.py` - DELETED
- [x] `tests/test_backtest_no_lookahead_mtf_htf.py` - DELETED
- [x] `tests/test_backtest_mark_price_unification.py` - DELETED
- [x] `tests/test_backtest_funding_window_semantics.py` - DELETED

### D2. Update References
- [x] pytest files deleted - no pytest invocations needed for backtest validation
- [x] CLI commands are the only validation path

---

## Gates

### Gate 1 — CLI Verify Commands Exist
- [x] `backtest preflight` returns correct dataset routing + coverage
- [x] `backtest indicators --print-keys` prints stable key lists
- [x] `backtest run --smoke --strict` runs or fails with diagnostics

### Gate 2 — CLI Replaces pytest
- [x] CLI commands cover everything old tests covered
- [x] pytest files deleted
- [x] No workflows rely on deleted files

---

## Acceptance Criteria

- [x] Developer can validate system via CLI only: preflight, indicators, smoke
- [x] No `tests/test_*.py` for backtest/data/indicator validation
- [x] All verification routes through modular toolchain

---

## CLI Commands Reference

```bash
# List available IdeaCards
python trade_cli.py backtest list

# Preflight check (data coverage, env routing)
python trade_cli.py backtest preflight --idea-card SOLUSDT_15m_ema_crossover --data-env live

# Indicator key discovery
python trade_cli.py backtest indicators --idea-card SOLUSDT_15m_ema_crossover --print-keys

# Smoke backtest (full pipeline validation)
python trade_cli.py backtest run --idea-card SOLUSDT_15m_ema_crossover --smoke --strict

# Data fix (sync/fill/heal)
python trade_cli.py backtest data-fix --idea-card SOLUSDT_15m_ema_crossover --sync-to-now

# JSON output (for CI/agents)
python trade_cli.py backtest preflight --idea-card SOLUSDT_15m_ema_crossover --json
python trade_cli.py backtest indicators --idea-card SOLUSDT_15m_ema_crossover --json
```
