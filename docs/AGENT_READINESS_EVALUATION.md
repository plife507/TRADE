# Agent CLI Readiness Evaluation

**Date**: 2026-02-24
**Context**: Evaluation of how close the TRADE project is to supporting autonomous LLM agents
that operate the trading bot via CLI.

---

## Architecture Foundation

The key architectural enabler is the **headless CLI design**: all subcommands share the same
`src/tools/` layer with `--json` output. Wiring a tool for agents (argparse) automatically
makes it testable, scriptable, and composable.

```
Agent (LLM)
    |
    v
CLI subcommands (argparse, --json output)
    |
    v
src/tools/ layer (canonical business logic, ToolResult envelope)
    |
    v
Engine / Exchange / Data stores
```

All subcommands support `--json` for structured output (`{"status","message","data"}` envelope),
making them parseable by agents without screen-scraping.

---

## Dimension 1: CLI Surface Coverage (85% Ready)

### Wired Subcommand Groups (11 total)

| Group | Subcommands | File |
|-------|-------------|------|
| **backtest** | run, preflight, indicators, data-fix, list, normalize, normalize-batch | `subcommands/backtest.py` |
| **play** | run, status, stop, watch, logs, pause, resume | `subcommands/play.py` |
| **validate** | quick, standard, full, real, module, pre-live, exchange | inline in `trade_cli.py` |
| **debug** | math-parity, snapshot-plumbing, determinism, metrics | `subcommands/debug.py` |
| **account** | balance, exposure, info, history, pnl, transactions, collateral | `subcommands/trading.py` |
| **position** | list, close, detail, set-tp, set-sl, set-tpsl, trailing, partial-close, margin, risk-limit | `subcommands/trading.py` |
| **panic** | (single command) | `subcommands/trading.py` |
| **order** | buy, sell, list, amend, cancel, cancel-all, leverage, batch | `subcommands/order.py` |
| **data** | sync, info, symbols, status, summary, query, heal, vacuum, delete | `subcommands/data.py` |
| **market** | price, ohlcv, funding, oi, orderbook, instruments | `subcommands/market.py` |
| **health** | check, connection, rate-limit, ws, environment | `subcommands/health.py` |

**50+ tool functions wired** via P13 (6 phases, completed 2026-02-22).

### What an Agent Can Do Today

- Run backtests, read structured results
- Start/stop/pause/resume shadow plays (headless mode)
- Query account balance, positions, orders
- Place/amend/cancel orders
- Sync/query/heal market data (DuckDB)
- Check health, connection status, rate limits
- Run all validation tiers (quick/standard/full/real/module/pre-live/exchange)
- Run all debug diagnostics (math parity, determinism, metrics)

### Gap

~34 tool functions (of 103 total) remain unwired (no CLI subcommand). Most are niche
(forge audits, stress tests, some position config edge cases). The critical trading
loop is fully covered. Interactive menus were removed — all access is via headless
subcommands with `--json` output.

---

## Dimension 2: Instance Management Safety (95% Ready)

| Feature | Status | Reference |
|---------|--------|-----------|
| Cross-process locking | DONE | P15 Phase 1 — `fcntl` advisory lock serializes check+write |
| Atomic file writes | DONE | P15 Phase 1 — `tempfile` + `os.replace()` prevents partial JSON |
| Two-phase reservation | DONE | P15 Phase 3 — "starting" status prevents TOCTOU races |
| PID kill on stop | DONE | P17 Phase 1 — SIGTERM + SIGKILL fallback |
| PID-aware duplicate check | DONE | P17 Phase 2 — "Instance already running for X (PID Y)" |
| 15s cooldown after stop | DONE | P15 Phase 2 — prevents restart during cleanup |
| Stale file cleanup | DONE | P15 Phase 4 — dead PIDs auto-removed on `play status` |
| Headless mode | DONE | P14 — `--headless` flag, JSON events on stdout |

### Agent Test Suite

**Test prompt:** 62 tests across 10 groups (P14 headless mode + P17 kill chain).

| Platform | Score | Key Issues |
|----------|-------|------------|
| WSL (pre-P17) | 53/62 | 9 failures from 2 bugs (PID kill + duplicate check) |
| Windows Run 8 | 45/62 | Additional: DuckDB lock timing, Start-Process deadlock |

**P17 fixes verified individually (2026-02-24):** All 9 previously-failing tests
(T45-T46, T52-T56, T60-T61) now pass. Full end-to-end 62-test re-run pending.

### Gap

Full 62-test end-to-end re-run not yet completed. Individual test verification done.

---

## Dimension 3: Live Trading Safety (80% Ready)

### What's Done

| Feature | Status | Detail |
|---------|--------|--------|
| `--confirm` flag on live mode | DONE | Prevents accidental real-money execution |
| `reduce_only=True` on closes | DONE | Prevents accidental position flip |
| Panic button | DONE | `python trade_cli.py panic` — cancel all + close all |
| `validate pre-live --play X` | WIRED | Deployment gate exists (untested on real play) |
| Price deviation guard | DONE | Blocks trading if price unreasonable |
| Position sync gate | DONE | Blocks signals until position state confirmed |
| Daily loss tracker | DONE | Seeded from exchange, tracks intraday P&L |
| Max drawdown halt | DONE | Engine stops when drawdown exceeds play limit |

### Pre-Deployment Blockers (fix before real money)

| Item | Risk | Detail |
|------|------|--------|
| ~~**GAP-2**: No REST warmup fallback~~ | ~~HIGH~~ | **FIXED** — `_load_bars_from_rest_api()` in `live.py` implements 3-tier fallback (buffer → DuckDB → REST, up to 1000 bars). |
| **DATA-011**: No active WS reconnect | MEDIUM | Passive detection + runner-level reconnect works, but no active pybit force-reconnect for extended outages. |
| **DATA-017**: `panic_close_all()` ordering | LOW | Cancel-before-close ordering is defensible but needs integration test to verify. |
| **H22**: No funding event pipeline | LOW | Sim accepts `funding_events` kwarg but no generation pipeline exists. Affects backtest accuracy for long-hold strategies. |

### Unverified Live Path (P12 Remaining)

These items were coded but never manually verified:
- Run shadow play 10+ minutes — confirm NO "Signal execution blocked" warnings
- Confirm `is_websocket_healthy()` returns True throughout
- Run play A -> stop -> play B -> verify no stale symbols leak
- Health check shows correct tri-state WS display

### Missing Live Infrastructure

| Item | Detail |
|------|--------|
| **P1**: Live parity rubric | No way to validate live behavior matches backtest expectations |
| **P2**: Paper trading integration | Never tested full live cycle end-to-end |

---

## Dimension 4: Agent Workflow Patterns (75% Ready)

### Supported Workflows

| Workflow | CLI Commands | Status |
|----------|-------------|--------|
| **Deploy a play** | `validate pre-live --play X` then `shadow run --play X` or `portfolio deploy --play X --confirm` | Ready |
| **Monitor** | `play status --json` / `play watch --json` | Ready |
| **Signal execution** | Automatic (engine handles internally) | Ready |
| **Check P&L** | `account balance --json` / `account pnl --json` | Ready |
| **Emergency stop** | `play stop --all --force` / `panic` | Ready |
| **Data freshness** | `data status --json` / `data sync --json` | Ready |
| **Health checks** | `health check --json` | Ready |
| **Position management** | `position list --json` / `position close --json` | Ready |
| **Multi-play orchestration** | Start play A + play B (different symbols) | Ready |
| **Strategy rotation** | Stop play A -> start play B (wait 15s cooldown) | Ready |
| **Backtest before deploy** | `backtest run --play X --synthetic --json` | Ready |
| **Log analysis** | `play logs --instance X` | Wired but untested |

### Example Agent Session (Shadow)

```bash
# 1. Validate play before deployment
python trade_cli.py validate pre-live --play my_strategy.yml --json

# 2. Start shadow (daemon mode)
python trade_cli.py shadow run --play my_strategy.yml &
# First stdout line: {"event": "started", "instance_id": "...", ...}

# 3. Monitor loop
while true; do
    python trade_cli.py play status --json    # Instance state
    python trade_cli.py account balance --json # Account state
    python trade_cli.py position list --json   # Open positions
    sleep 60
done

# 4. Stop when done
python trade_cli.py play stop --all --force
```

### Missing Agent Capabilities

| Capability | Detail | Priority |
|------------|--------|----------|
| Push notifications | No webhook/callback for "trade opened" / "drawdown alert". Agent must poll `play status --json`. | Medium |
| Play performance API | No `play metrics --json` for current Sharpe, win rate, etc. Must parse backtest artifacts. | Low |
| Strategy selection | No CLI to compare plays and pick the best one to deploy. | Low |
| Alert thresholds | No "alert me if drawdown > 5%" — agent must implement own polling logic. | Medium |

---

## Dimension 5: Platform Considerations

### WSL/Linux (Primary Agent Platform)

- All 62 CLI tests designed for bash
- `fcntl` file locks release instantly on process exit (no DuckDB timing issues)
- Background process management via `&` and `kill` works reliably
- Python `-u` flag needed for unbuffered headless stdout output

### Windows

- DuckDB WAL checkpoint holds locks 8-16s after process exit (needs sleep between commands)
- PowerShell `Start-Process -RedirectStandardOutput` deadlocks on PS 5.1 (use `Start-Job`)
- Instance file cleanup may hit `PermissionError` if another process has file open
- 45/62 test score vs 53/62 on WSL (platform-specific issues, not code bugs)

---

## Overall Scorecard

**Last evaluated**: 2026-02-25 (automated re-test of all dimensions)

| Dimension | Score | Tests | Notes |
|-----------|-------|-------|-------|
| CLI surface | **90%** | 15/15 pass | All 11 subcommand groups return valid JSON |
| Instance safety | **95%** | 8/8 pass | Cross-process locking, PID kill, cooldown, headless — all solid |
| Live trading safety | **80%** | 8/8 features pass | GAP-2 fixed (REST fallback). 3 minor items remain. |
| Agent workflows | **90%** | 6/6 pass | headless, watch --json, stop --all/--force, logs — all working |
| **Overall** | **~88%** | | **Shadow-mode agent operation is ready. Live-money is 1 session away.** |

### Minor gaps for 100%

| Item | Risk | Detail |
|------|------|--------|
| DATA-011 | MEDIUM | No active WS force-reconnect (passive detection + runner-level reconnect works) |
| DATA-017 | LOW | `panic_close_all()` ordering needs integration test |
| H22 | LOW | Funding event generation pipeline not built (sim applies events but no source) |
| JSON format | LOW | Two output formats: envelope vs flat domain objects — agents need two parsing paths |

---

## Recommended Path to 100%

### Session A: Shadow Validation + Live Prep (~2h)

Goal: Verify shadow mode end-to-end and fix remaining blockers.

1. Run 10min shadow play — confirm NO "Signal execution blocked" warnings
2. **DATA-011**: Implement active pybit WS reconnect (or detect-and-restart play)
3. Run `validate pre-live --play X` on a real play
4. Run `validate exchange` to confirm exchange integration

**Deliverable:** No known blockers for live trading.

### Session B: Go-Live (~2h)

Goal: First real-money trade.

1. Define live parity rubric (backtest as gold standard, acceptable deviation thresholds)
2. 24h shadow validation run (play running overnight, check next day)
3. First live trade: `python trade_cli.py play run --play X --mode live --confirm`
4. Monitor via `play status --json` + `account pnl --json`

**Deliverable:** Live trading operational.

---

## Key References

| Topic | Location |
|-------|----------|
| Architecture & roadmap | `docs/architecture/ARCHITECTURE.md` |
| Agent autonomy brainstorm | `docs/brainstorm/CLI_AGENT_AUTONOMY.md` |
| Project status | `docs/TODO.md` |
| Validation best practices | `docs/VALIDATION_BEST_PRACTICES.md` |
| Play DSL reference | `docs/PLAY_DSL_REFERENCE.md` |
