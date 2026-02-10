# Session Handoff

**Date**: 2026-02-08
**Branch**: feature/unified-engine
**Last Commit**: `ea5f58d` fix(plays): fix last 2 zero-trade plays (liquidity hunt patterns)

---

## Current State

**Engine: FULLY VERIFIED**

| Suite | Result |
|-------|--------|
| Synthetic (170 plays) | 170/170 PASS, 0 fail, 0 zero-trade |
| Real-data (60 plays) | 60/60 PASS, 60/60 math verified (23 checks each) |
| Indicators covered | 44/44 (synthetic), 41/43 (real) |
| Structures covered | 7/7 |
| DSL operators covered | All (synthetic), 19/24 (real) |
| Symbols tested (real) | BTC, ETH, SOL, LTC |

**Open Bugs: NONE**

---

## Recent Fixes (2026-02-07 / 2026-02-08)

### DSL Parser (2026-02-07)
- Dotted feature refs (`trend.direction`) now split correctly in `parse_feature_ref()`
- Bracket syntax (`fib.level[0.618]`) normalized in play.py shorthand conversion
- Arithmetic dict format (`{"+": [a, b]}`) handled in `parse_rhs()`
- NOT operator list-of-lists unwrapped in `_convert_shorthand_conditions()`

### Structure Bugs (2026-02-07)
- Derived zone creation-bar break: `anchor_idx < bar_idx` guard added
- Market structure and trend detector fixes (3 bugs)

### Engine/Verifier (2026-02-08)
- Equity curve post-close: final equity point appended AFTER force close
- Math verifier candle loading: DuckDB candle lookup via timestamps
- Preflight auto-sync: all 3 TFs synced (not just feature TFs)
- 6 zero-trade plays fixed: 4 impossible conditions, 2 multi-timeframe bar dilation

---

## Timeframe Naming (ENFORCED)

YAML keys: `low_tf`, `med_tf`, `high_tf`, `exec` (pointer to role, not a value).
Never use: `ltf`, `htf`, `LTF`, `HTF`, `exec_tf`.
Prose: "higher timeframe", "execution timeframe", "multi-timeframe" (no abbreviations).

---

## Quick Commands

```bash
# Full smoke test
python trade_cli.py --smoke full

# Run backtest
python trade_cli.py backtest run --play X --fix-gaps

# Run suite (synthetic)
python scripts/run_full_suite.py

# Run suite (real data)
python scripts/run_full_suite.py --real --start 2025-01-01 --end 2025-06-30

# Run 60-play real verification
python scripts/run_real_verification.py

# Verify trade math for a play
python scripts/verify_trade_math.py --play X

# Indicator audit
python trade_cli.py backtest audit-toolkit

# Demo mode (no real money)
python trade_cli.py play run --play X --mode demo

# Live mode (REAL MONEY)
python trade_cli.py play run --play X --mode live --confirm
```

---

## Next Steps

1. **Re-run 60-play suite** with all engine fixes applied (confirm all still pass)
2. **Create last_price verification plays** -- ensure last price semantics are correct
3. **Live engine rubric** -- define acceptance criteria for live trading readiness
4. **Paper trading test** -- demo mode with real market data end-to-end

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
1. `process_bar(bar_index)` on exec timeframe
2. Update higher/medium timeframe indices
3. Warmup check (multi-timeframe sync + NaN validation)
4. `exchange.step()` (fill simulation via 1m subloop)
5. `_evaluate_rules()` -> Signal or None
6. `execute_signal(signal)`
