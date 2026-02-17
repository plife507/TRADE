# TRADE TODO

Single source of truth for all open work and known bugs.
Completed work archived in Claude Code memory: `completed_work.md`.

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

## Open Bugs & Architecture Gaps

### Live/Demo Gaps

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| GAP-1 | **CRITICAL** | `LiveDataProvider._warmup_bars` hardcoded to 100 regardless of Play needs | Wire `get_warmup_from_specs()` into `LiveDataProvider.__init__()` |
| GAP-2 | HIGH | No REST API fallback for warmup data -- `_load_tf_bars()` tries buffer -> DuckDB -> gives up | Add REST `get_klines()` fallback |

### Live Safety Gaps

| # | Severity | File | Issue |
|---|----------|------|-------|
| GAP-LS1 | **CRITICAL** | `tools/order_tools.py:368-380` | Partial close market orders not sent as reduce-only — `reduce_only` set on result object after order already placed, exchange never sees the flag |
| GAP-LS2 | HIGH | `core/order_executor.py:701-717` | Price deviation guard data paths fail-open — no ticker or no lastPrice returns None (allows order). Exception path fixed (BUG-SEC3) but data paths still open |
| GAP-LS3 | HIGH | `risk/global_risk.py:284-289` | WebSocket health-check exception handler returns `True` (allowed), bypassing threshold-based blocking |
| GAP-LS4 | HIGH | `engine/runners/live_runner.py:484-485` | Startup position sync failure swallowed as warning — engine starts without reliable state reconciliation |
| GAP-LS5 | MEDIUM | `core/exchange_orders_manage.py:406-407` | `batch_limit_orders` silently drops qty<=0 orders (`continue` with no log/error). `batch_market_orders` was fixed (BUG-P2-8) but limit path was missed |
| GAP-LS6 | MEDIUM | `core/exchange_instruments.py:131-135` | `calculate_qty()` — if `get_price()` returns None, `price <= 0` raises uncontrolled TypeError instead of explicit validation |

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
