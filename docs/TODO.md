# TRADE TODO

Single source of truth for all open work, known bugs, and session context.
All gates G0-G17 complete (2026-01-27 through 2026-02-15). Full history in Claude Code memory: `completed_work.md`.

---

## P0: Live Engine Rubric

28 demo/live bugs were fixed (2026-02-12). Remaining items:
- [ ] Define live parity rubric: backtest results as gold standard for live comparison
- [ ] Demo mode 24h validation
- [ ] Verify sub-loop activation in live mode

## P1: Live Trading Integration

- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Paper trading integration
- [ ] Complete live adapter stubs

## P2: Unify `--fix-gaps` / `--fill-gaps` → `--sync` (COMPLETE 2026-02-15)

All 5 gates complete. `--sync`/`--no-sync` is the unified flag everywhere. `--heal` remains as separate doctor action. pyright 0 errors, grep clean.

## P3: CLI Redesign (Gates 4, 5, 8 open)

Gates 1-3, 6-7, 9 complete. See `docs/CLI_REDESIGN.md` for full details.

- [ ] **Gate 4**: Unified `_place_order()` flow (type selector, side, symbol, amount, preview, confirm)
- [ ] **Gate 5**: Data menu top-level rewrite (delegate to sub-menu files already created)
- [ ] **Gate 8**: Final manual validation (offline menu, connect flow, quick-picks, cross-links)

## P4: Market Sentiment Tracker

Design document: `docs/brainstorm/MARKET_SENTIMENT_TRACKER.md`

- [ ] Phase 1: Price-derived sentiment (Tier 0) -- existing indicators + structures, zero new deps
- [ ] Phase 2: Bybit exchange sentiment (Tier 1) -- funding rate, OI, L/S ratio, liquidations, OBI
- [ ] Phase 3: External data (Tier 2) -- Fear & Greed Index, DeFiLlama stablecoin supply
- [ ] Phase 4: Historical sentiment for backtesting
- [ ] Phase 5: Statistical regime detection -- HMM-based (optional, requires hmmlearn)
- [ ] Future: Agent-based play selector that consumes sentiment tracker output

---

## Known Bugs & Architecture Gaps

### Live/Demo Gaps (from 2026-02-11 audit)

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| GAP-1 | **CRITICAL** | `LiveDataProvider._warmup_bars` hardcoded to 100 regardless of Play needs | Wire `get_warmup_from_specs()` into `LiveDataProvider.__init__()` |
| GAP-2 | HIGH | No REST API fallback for warmup data -- `_load_tf_bars()` tries buffer -> DuckDB -> gives up | Add REST `get_klines()` fallback |
| GAP-3 | MEDIUM | Play's `starting_equity_usdt` ignored in live -- real exchange balance used silently | Add preflight equity reconciliation warning |
| GAP-4 | MEDIUM | Leverage set per-order only, not during account init | Call `set_leverage()` in `LiveExchange.connect()` |
| GAP-5 | LOW | Play `taker_bps` vs actual Bybit VIP tier fees not compared | Add preflight fee reconciliation |

### VWAP / Anchored VWAP (from 2026-02-15 audit)

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| V-1 | DESIGN | Non-swing detectors missing `reset()` / `to_dict()` for crash recovery | `trend.py`, `zone.py`, `fibonacci.py`, `derived_zone.py`, `rolling_window.py`, `market_structure.py` |
| V-2 | DESIGN | Multiple swing structures on exec TF: first wins, no way to select | `play_engine.py:1036` |
| V-3 | DESIGN | `near_pct` tolerance has two conversion paths (play.py /100, dsl_parser.py raw) -- fragile | `play.py:224`, `dsl_parser.py:606` |
| V-4 | EDGE | Anchored VWAP on non-exec TF cannot wire to non-exec swing structure | `play_engine.py:1033` |
| V-5 | EDGE | Batch pre-computation for anchored_vwap is wasted work (engine overwrites every bar) | `indicator_vendor.py:217-266` |
| V-6 | EDGE | Parity audits would false-fail for anchored_vwap (batch vs engine divergence) | `audit_incremental_parity.py` |
| V-7 | EDGE | No test coverage for VWAP session boundary resets | Validation plays |
| V-8 | EDGE | `swing.high_version` / `swing.low_version` accessible but undocumented in DSL reference | `PLAY_DSL_REFERENCE.md` |

### Platform

- **DuckDB file locking on Windows** -- all scripts run sequentially, `run_full_suite.py` has retry logic (5 attempts, 3-15s backoff)

---

## Validation Commands

```bash
python trade_cli.py validate quick              # Pre-commit (~10s)
python trade_cli.py validate standard           # Pre-merge (~2min)
python trade_cli.py validate full               # Pre-release (~10min)
python trade_cli.py validate pre-live --play X  # Deployment gate
python trade_cli.py validate exchange            # Exchange integration (~30s)

python trade_cli.py backtest run --play X --sync      # Single backtest (--sync default, shown for clarity)
python scripts/run_full_suite.py                      # 170-play synthetic suite
python scripts/run_real_verification.py               # 60-play real verification
python scripts/verify_trade_math.py --play X          # Math verification
```
