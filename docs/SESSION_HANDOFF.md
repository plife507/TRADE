# Session Handoff

**Date**: 2026-02-13
**Branch**: feature/unified-engine
**Phase**: Play Lab Pipeline (Design Complete, Ready to Implement)

---

## Current State

**Engine: FULLY VERIFIED + TYPE-SAFE**

| Suite | Result |
|-------|--------|
| Pyright | **0 errors, 0 warnings** |
| Validation quick (4 gates) | ALL PASS (5 plays, 2134 trades) |
| Synthetic (170 plays) | 170/170 PASS, 0 fail, 0 zero-trade |
| Real-data (60 plays) | 60/60 PASS, 60/60 math verified (23 checks each) |
| Demo readiness (84 checks) | 84/84 PASS across 12 phases |
| Indicators covered | 44/44 (synthetic), 41/43 (real) |
| Structures covered | 7/7 |

**Open Bugs: NONE**

---

## Next Task: Play Lab Pipeline

Full design document at **`docs/PLAY_LAB_PIPELINE_PLAN.md`**.

### Summary

Add `python trade_cli.py lab <command>` -- a 4-stage pipeline for play lifecycle:

1. **Design**: `lab design --idea "..." --name X` -- scaffold YAML from natural language (future LLM API integration point)
2. **Test**: `lab test --play X --start ... --end ...` -- backtest with metric thresholds, robustness checks, buy-and-hold benchmark
3. **Review**: `lab review --play X --auto` -- agent auto-review or human verdict recording
4. **Approve**: `lab approve --play X` -- run approval gates, promote to `plays/approved/`

Staged directories: `plays/ideas/` -> `plays/testing/` -> `plays/approved/` with sidecar `.meta.json` files.

All commands support `--json` for agent consumption. Exit codes 0/1.

### Files to Create
- `src/tools/lab_tools.py` -- all business logic
- `config/lab_defaults.yml` -- threshold profiles
- `plays/ideas/`, `plays/testing/`, `plays/approved/`, `plays/archived/` directories

### Files to Modify
- `src/cli/argparser.py` -- add `_setup_lab_subcommands()`
- `src/cli/subcommands.py` -- add 9 `handle_lab_*()` handlers
- `trade_cli.py` -- wire lab command dispatch

### Key Reuse
- `backtest_run_play_tool()` from `src/tools/backtest_play_tools.py`
- `load_play()` from `src/backtest/play/play.py` (already rglobs `plays/`)
- `ResultsSummary` from `src/backtest/artifacts/artifact_standards.py:937`
- `ToolResult` from `src/tools/shared.py:34`
- `GateResult` pattern from `src/cli/validate.py`

### Implementation Order
1. Directories + `config/lab_defaults.yml`
2. `src/tools/lab_tools.py` core (PlayMeta, MetricThresholds, Stage, _move_play)
3. Design tools (scaffold, template clone, validate)
4. List/status/history tools
5. Argparse + handlers + wiring for above
6. Test tool (backtest + metrics + robustness + benchmark)
7. Review + approve + reject + archive tools
8. Argparse + handlers + wiring for above
9. End-to-end smoke test

---

## Architecture Gaps (Carried Forward from 2026-02-11)

### GAP #1: Warmup Hardcoded to 100 Bars (CRITICAL)
- `LiveDataProvider._warmup_bars` always 100 regardless of Play needs
- Fix: Wire `get_warmup_from_specs()` into `LiveDataProvider.__init__()`

### GAP #2: No REST API Fallback for Warmup Data
- `_load_tf_bars()` tries bar buffer -> DuckDB -> gives up
- Fix: Add REST `get_klines()` fallback

### GAP #3: Starting Equity Ignored in Live/Demo
- Play's `starting_equity_usdt` is fallback only; real exchange balance used silently
- Fix: Add preflight equity reconciliation warning

### GAP #4: Leverage Not Set on Startup
- Leverage set per-order only, not during account init
- Fix: Call `set_leverage()` in `LiveExchange.connect()`

### GAP #5: Fee Model Not Reconciled
- Play `taker_bps` vs actual Bybit VIP tier fees not compared

---

## Quick Commands

```bash
# Validation
python trade_cli.py validate quick                    # Core validation (~30s)
python trade_cli.py validate standard                 # Core + audits (~2min)
python trade_cli.py validate full                     # Everything (~10min)

# Type checking
python -m pyright                                     # Full pyright check (0 errors expected)

# Demo readiness
python scripts/test_demo_readiness.py                 # Full (84 checks, ~5min)
python scripts/test_demo_readiness.py --skip-orders   # Read-only (69 checks, ~3min)

# Backtest
python trade_cli.py backtest run --play X --fix-gaps
python scripts/run_full_suite.py
python scripts/run_real_verification.py

# Live/Demo
python trade_cli.py play run --play X --mode demo
python trade_cli.py play run --play X --mode live --confirm

# Operations
python trade_cli.py play status
python trade_cli.py play watch
python trade_cli.py account balance
python trade_cli.py position list
python trade_cli.py panic --confirm
```

---

## Architecture

```text
src/engine/        # ONE unified PlayEngine for backtest/live
src/indicators/    # 44 indicators (all incremental O(1))
src/structures/    # 7 structure types
src/backtest/      # Infrastructure only (sim, runtime, features)
src/data/          # DuckDB historical data (1m mandatory for all runs)
src/tools/         # CLI/API surface
```

Signal flow (identical for backtest/live):
1. `process_bar(bar_index)` on execution timeframe
2. Update higher/medium timeframe indices
3. Warmup check (multi-timeframe sync + NaN validation)
4. `exchange.step()` (fill simulation via 1m subloop)
5. `_evaluate_rules()` -> Signal or None
6. `execute_signal(signal)`
