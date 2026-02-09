# Vector Backtest Trade Math Verification

> **INCOMPLETE (2026-02-08)**: This verification run was interrupted by DuckDB
> file locking on Windows (~70% RUN_FAIL). The equity curve post-close bug was
> also discovered and fixed after this run. Artifacts need regeneration.
> The 60-play real-data Wyckoff verification (60/60 pass, 23 math checks each)
> in `docs/REAL_VERIFICATION_REPORT.md` provides the authoritative math verification.

**Goal**: 100% verification of all 170 plays before moving to incremental engine.

**Methodology**: For each play, run backtest with synthetic data (seed=42), then verify:
1. **LOAD** - Artifacts load correctly
2. **TRADE_COUNT** - result.json count matches trades.parquet rows
3. **PNL_DIRECTION** - Long profits when exit > entry, short vice versa
4. **NET_PNL** - net_pnl = realized_pnl - fees_paid (per trade)
5. **FEES** - Fee amounts match taker_bps config (entry + exit fees)
6. **SL_TP** - Stop loss/take profit on correct side of entry
7. **EXIT_REASON** - Exit price matches SL/TP when exit_reason is sl/tp
8. **EQUITY** - sum(trade PnL) matches result.json net_pnl; equity curve consistent
9. **METRICS** - wins+losses=total, win_rate=wins/total, profit_factor consistent
10. **OVERLAP** - No overlapping trades for single-position plays
11. **BYBIT_PNL** - Matches Bybit USDT perpetual formulas exactly

**Bybit Reference**: PnL = Qty * (Exit - Entry) for longs, Qty * (Entry - Exit) for shorts.
Fee = Order Value * Fee Rate. Closed PnL = Realized PnL - Open Fee - Close Fee.

---

## Suite Status

| Suite | Plays | Status | Report |
|-------|-------|--------|--------|
| indicator_suite | 84 | PENDING | `docs/VERIFY_INDICATOR.md` |
| operator_suite | 25 | PENDING | `docs/VERIFY_OPERATOR.md` |
| structure_suite | 14 | PENDING | `docs/VERIFY_STRUCTURE.md` |
| pattern_suite | 34 | PENDING | `docs/VERIFY_PATTERN.md` |
| complexity_ladder | 13 | PENDING | `docs/VERIFY_CL.md` |
| **TOTAL** | **170** | **PENDING** | |

---

## How to Run

```bash
# Single play
python scripts/verify_trade_math.py --play IND_001_ema_trend_long

# Full suite
python scripts/verify_trade_math.py --suite indicator
python scripts/verify_trade_math.py --suite operator
python scripts/verify_trade_math.py --suite structure
python scripts/verify_trade_math.py --suite pattern
python scripts/verify_trade_math.py --suite cl

# All suites
python scripts/verify_trade_math.py --suite all
```
