# TRADE TODO

Active work tracking for the TRADE trading bot. **This is the single source of truth for all open work.**

---

## Current Phase: Production Readiness

### P0: Validation Suite (BLOCKING)

- [ ] Run full validation suite batch test (19 plays)
- [ ] Fix any failing plays discovered
- [ ] Document coverage gaps

### P1: Extended Testing

- [ ] Enable `TRADE_SMOKE_INCLUDE_BACKTEST=1` for extended backtest smoke tests

---

## Backlog

### P2: DSL Enhancement (Phase 2 per roadmap)

- [ ] Build DSL validator
- [ ] Implement typed block layer
- [ ] Add block composition

### P3: Live Trading (Phase 3)

- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Paper trading integration
- [ ] Complete live adapter stubs
- [ ] Position management

### P4: Incremental Indicator Expansion

Expand O(1) incremental indicators from 11 to 43 (full coverage).

**Current**: 11 incremental indicators (ema, sma, rsi, atr, macd, bbands, stoch, adx, supertrend, cci, willr)

**Remaining tiers** (detailed plan was in `docs/archived/VALIDATION_GATE_PLAN.md`):
- Tier 1: Trivial (ohlc4, midprice, roc, mom, obv, natr)
- Tier 2: EMA-Composable (dema, tema, ppo, trix, tsi)
- Tier 3: SMA/Buffer-Based (wma, trima, linreg, cmf, cmo, mfi)
- Tier 4: Lookback-Based (aroon, donchian, kc, dm, vortex)
- Tier 5: Complex Adaptive (kama, alma, zlma, stochrsi, uo)
- Tier 6: Stateful Multi-Output (psar, squeeze, fisher)
- Tier 7: Volume Complex (kvo, vwap)

---

## Completed Gates

All audit remediation gates have been completed.

| Gate | Items | Status | Blocking |
|------|-------|--------|----------|
| G0: Live Trading Blockers | 4/4 | ✓ Complete | Live Trading |
| G1: Risk Management Hardening | 4/4 | ✓ Complete | Production |
| G2: Data Integrity | 4/4 | ✓ Complete | Backtest Accuracy |
| G3: Testing & Monitoring | 4/4 | ✓ Complete | None (Quality) |

---

## Completed Work (2026-01)

### 2026-01-25: Unified Indicator System

- [x] Implemented unified indicator system with registry-driven architecture
- [x] Created IndicatorProvider protocol (`src/indicators/provider.py`)
- [x] Expanded incremental indicators from 6 to 11 (O(1) for live trading)
- [x] Removed all hardcoded indicator lists - registry is single source of truth
- [x] Comprehensive DSL cookbook review and fixes

### 2026-01-22: Validation Suite & Synthetic Data

- [x] Created validation plays (consolidated to 19 core plays across 3 tiers)
- [x] Implemented 34 synthetic market condition patterns
- [x] Added SyntheticConfig to Play class for auto-synthetic data
- [x] Fixed synthetic mode TIMEFRAME_NOT_AVAILABLE error

### 2026-01-21: Engine Migration

- [x] PlayEngine migration complete (1,166 lines)
- [x] BacktestEngine deleted (re-exports only remain)
- [x] Position sizing caps added (max_position_equity_pct)

### 2026-01-17: Validation Infrastructure

- [x] Fixed Play directory paths
- [x] Created structure validation Plays
- [x] Updated all agents with correct paths
