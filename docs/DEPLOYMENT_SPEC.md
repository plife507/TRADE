# Deployment Spec

Living document. Single source of truth for the path to production.
Last updated: 2026-04-04.

---

## Current State

| Layer | Status | Confidence |
|-------|--------|------------|
| Backtest engine | Production-ready | 9/10 — 229 synthetic + 61 real-data plays pass |
| Play DSL | Frozen v3.0.0 | 10/10 — 47 indicators, 13 structures, 38 patterns |
| Validation | 18 gates (G1-G17 + G4b) | 9/10 — comprehensive, tiered, parallel |
| Shadow daemon | Built (M4 Phases 1-4) | 6/10 — architecture solid, zero live runtime |
| UTA portfolio | Built (M8) | 7.5/10 — bugs fixed, needs live validation |
| Exchange smoke test | Built (EX4) | 8/10 — needs funding to run |
| Live runner | Built | 5/10 — untested in sustained operation |
| CLI | 13 groups, 72 handlers, 124 tools | 9/10 |
| VPS deployment | Designed, not deployed | 3/10 |

---

## Blocking Items (must fix before live)

### Fund account ($25 minimum)
Everything downstream depends on this. Unlocks EX4, sub-account testing, shadow deployment.

### Run EX4 order lifecycle ($0 cost)
```bash
python trade_cli.py validate exchange
```
Validates: connectivity, account, market data, order place/amend/cancel, diagnostics.

### Shadow 24h stability run
Deploy one play to shadow daemon on VPS. Run for 24h. Verify:
- No memory leaks, no connection drops
- PerformanceDB records trades/snapshots
- Can stop cleanly, funds return to main

### Sub-account E2E lifecycle
Create smoke sub → fund $10 → deploy play → run 1h → stop → verify position closed → withdraw → delete sub.

### Kill-test recovery
Start deploy → `kill -9` → restart → `sync_from_exchange()` → verify state matches reality.

---

## Deployment Phases

### Phase A: Shadow on VPS (first milestone)

**Goal:** Prove the system runs unattended for days.

1. Provision VPS (Hostinger KVM 2 or equivalent)
2. Deploy shadow daemon with 1-2 proven plays
3. Monitor via `portfolio snapshot --json` + `shadow status`
4. Run for 7 days minimum
5. Evaluate: trades generated, P&L tracking, no crashes

**Success criteria:**
- 7 days uptime without manual intervention
- PerformanceDB has consistent trade/snapshot records
- Memory usage stable (no growth over time)
- WebSocket reconnects automatically on disconnect

**Plays to shadow:** Start with simple trend-following on SOL (proven in backtest).

### Phase B: First live play (real money, minimal)

**Goal:** Prove the full pipeline with $25-50 capital.

1. Pick highest-Sharpe play from shadow results
2. `validate pre-live --play X --confirm`
3. `portfolio deploy --play X --capital 25 --confirm`
4. Monitor for 48h
5. `portfolio stop --uid X --confirm` if anything looks wrong

**Success criteria:**
- Play enters and exits positions correctly
- TP/SL fire as expected
- Sub-account isolation holds (main account unaffected)
- Fee tracking matches Bybit records

### Phase C: Multi-play production

**Goal:** Run 3-5 plays simultaneously on isolated sub-accounts.

1. Deploy diverse strategies (trend, mean reversion, ICT)
2. Different symbols (SOL, BTC, ETH)
3. Monitor portfolio-level risk via `portfolio risk --json`
4. Run for 30 days

**Success criteria:**
- No cross-contamination between sub-accounts
- `recall_all --confirm` cleanly stops everything
- Portfolio Sharpe > individual play Sharpes (diversification works)

---

## Risk Matrix

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| WebSocket disconnect | Missed signals | Medium | Auto-reconnect + staleness detection + DCP |
| Exchange API change | Orders fail | Low | Version pin pybit, monitor Bybit changelog |
| Position sync drift | Wrong size traded | Medium | Periodic REST reconciliation, position sync gate |
| Sub-account fund stuck | Capital locked | Low | PENDING optimistic accounting + sync_from_exchange |
| Process crash mid-trade | Orphaned position | Medium | DCP (10s cancel), panic_close_all on restart |
| VPS downtime | Shadow stops | Low | Systemd watchdog, health endpoint |
| Flash crash fills smoke order | Unexpected position | Negligible | 50% price offset, 5-second window |

---

## Infrastructure Needed

| Component | Status | Notes |
|-----------|--------|-------|
| VPS | Not provisioned | Hostinger KVM 2 ($8.99/mo), 2 vCPU, 8GB RAM |
| Domain + SSL | Not set up | For dashboard/API access |
| Monitoring | Not built | Health endpoint + alerting (Telegram/Discord) |
| External withdrawal | Not built | Whitelist + limits + confirmation — build when needed |
| Web dashboard | Not started (M7) | Node.js, reads from `--json` CLI output |
| Market Intelligence | Not started (M6) | Regime detection, play rotation — trains in shadow |

---

## Ideas / Brainstorm

Ideas that aren't committed to. Evaluate as system proves itself.

### Graduated autonomy
- Start: pause + alert human before every promotion
- Earn trust: auto-promote plays that meet graduation thresholds for N days
- Full auto: agent rotates plays based on regime detection (M6)

### Strategy factory pipeline
- Knowledge Store (M1): structured concept library for agents
- Play Forge (M2): GE param sweep → LLM structural mutation → iterate until profitable
- Shadow graduation (M4 Phase 5): automated scoring, promotion pipeline

### TradingView parity (M7)
- Pine Script bridge for 13 detectors
- Side-by-side validation against TV charts
- Builds user trust in structure detection accuracy

### External withdrawal safety
When needed, build with:
- Address whitelist in config (only pre-approved wallets)
- Per-withdrawal cap ($500 default)
- Daily limit ($1000 default)
- Cooling period (24h for new addresses)
- Hard `--confirm` + log trail

### Multi-exchange support
- Currently Bybit-only
- Binance/OKX adapters would use same InstrumentRegistry pattern
- Not needed until single-exchange is proven

---

## Doc Index

| Doc | Purpose |
|-----|---------|
| **This file** | Living deployment spec |
| `TODO.md` | Active task tracking |
| `architecture/ARCHITECTURE.md` | System module design |
| **Reference** | |
| `PLAY_DSL_REFERENCE.md` | DSL syntax (frozen v3.0.0) |
| `dsl/` | Modular DSL playbook (8 files) |
| `CLI_QUICK_REFERENCE.md` | CLI commands |
| `CLI_DATA_GUIDE.md` | Data operations |
| `VALIDATION_BEST_PRACTICES.md` | Validation tiers |
| `SYNTHETIC_DATA_REFERENCE.md` | 38 test patterns |
| **Design** | |
| `SHADOW_EXCHANGE_DESIGN.md` | Shadow daemon architecture |
| `DEPLOYMENT_GUIDE.md` | VPS setup |
| `UTA_PORTFOLIO_DESIGN.md` | Bybit UTA API reference |
| `UTA_PORTFOLIO_SPEC.md` | Portfolio implementation (complete) |
| `MULTI_ACCOUNT_ARCHITECTURE.md` | Sub-account isolation |
| `TV_PARITY_DESIGN.md` | TradingView bridge design |
| `MARKET_STRUCTURE_FEATURES.md` | ICT structure reference |
| `AGENT_READINESS_EVALUATION.md` | Agent autonomy assessment |
| **Archive** | |
| `archive/SHADOW_ORDER_FIDELITY_REVIEW.md` | Completed sim vs exchange audit |
| `archive/CRT_TBS_STRATEGY_REVIEW.md` | Completed strategy analysis |
| `archive/STRUCTURE_DETECTION_AUDIT.md` | Completed detector audit |
| `archive/NEW_PROJECT_BOOTSTRAP_PROMPT.md` | Portable bootstrap template |
| `archive/PORTABLE_DEV_FRAMEWORK.md` | Portable dev framework |
