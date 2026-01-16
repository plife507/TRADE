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

### P0 - Pivot Foundation (CRITICAL)

> **Full spec**: `docs/todos/PIVOT_FOUNDATION_GATES.md`

The pivot/swing system is the foundation for ALL structure-based trading.
Current issues: noise in choppy markets, trend detector state memory bug, no BOS/CHoCH.

| Gate | Description | Status |
|------|-------------|--------|
| Gate 0 | Significance Infrastructure (ATR dependency) | [ ] |
| Gate 1 | Significance Filtering (min_atr_move) | [ ] |
| Gate 2 | Strict Alternation (H-L-H-L) | [ ] |
| Gate 3 | ATR ZigZag Mode (TradingView-style) | [ ] |
| Gate 4 | Trend Detector Rewrite (wave-based) | [ ] |
| Gate 5 | Market Structure (BOS/CHoCH) | [ ] |
| Gate 6 | MTF Pivot Coordination | [ ] |
| Gate 7 | Integration & Stress Testing | [ ] |

**Impact**: Unlocks clean Fib anchors, accurate trend, BOS/CHoCH events, future ICT structures (OB, FVG, liquidity zones).

### P1 - Live Trading Validation
- [ ] End-to-end demo trading test
- [ ] WebSocket reconnection handling
- [ ] Order fill confirmation flow

### P2 - Enhancements
- [ ] Additional incremental indicators (Supertrend, Stochastic)
- [ ] Structure history for lookback queries
- [ ] Multi-symbol backtest support

### P3 - Future (after Pivot Foundation)
- [ ] Order Blocks (OB)
- [ ] Fair Value Gaps (FVG)
- [ ] Liquidity Zones (equal H/L)
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
