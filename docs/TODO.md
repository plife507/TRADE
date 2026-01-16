# TODO

**Last Updated**: 2026-01-15
**Status**: Unified Engine Complete, Live Trading Ready

---

## Current State

| Component | Status |
|-----------|--------|
| Unified Engine | ✅ Complete |
| Backtest Infrastructure | ✅ Production |
| Incremental Indicators | ✅ Complete (O(1) for live) |
| Live Trading Adapters | ✅ Complete |
| Stress Tests | ✅ 50 plays validated with real data |
| Documentation | ✅ Updated |

---

## Next Steps

### P1 - Live Trading Validation
- [ ] End-to-end demo trading test
- [ ] WebSocket reconnection handling
- [ ] Order fill confirmation flow

### P2 - Enhancements
- [ ] Additional incremental indicators (Supertrend, Stochastic)
- [ ] Structure history for lookback queries
- [ ] Multi-symbol backtest support

### P3 - Future
- [ ] ICT Market Structure (BOS/CHoCH)
- [ ] Agent module for automated strategy generation

---

## Recent Completions

| Date | Feature |
|------|---------|
| 2026-01-15 | Incremental indicators (EMA, SMA, RSI, ATR, MACD, BBands) |
| 2026-01-15 | 50 stress tests with real data (7 symbols) |
| 2026-01-15 | Leverage display in backtest summary |
| 2026-01-15 | Liquidation price + realized PnL tracking |
| 2026-01-14 | Live trading infrastructure (adapters, runners) |
| 2026-01-13 | Unified engine gates 0-6 complete |

---

## Quick Validation

```bash
# Smoke test
python trade_cli.py --smoke full

# Backtest with real data
python trade_cli.py backtest run --play S_01_btc_single_ema --dir tests/stress/plays --start 2025-12-01 --end 2026-01-10 --fix-gaps

# Audit indicators
python trade_cli.py backtest audit-toolkit
```

---

## Key Documents

| Document | Purpose |
|----------|---------|
| `CLAUDE.md` | AI guidance, architecture |
| `docs/SESSION_HANDOFF.md` | Session context for continuity |
| `docs/PROJECT_STATUS.md` | What runs, what's stubbed |
| `docs/INCREMENTAL_INDICATORS.md` | O(1) indicator usage |
| `docs/PLAY_DSL_COOKBOOK.md` | DSL reference |
