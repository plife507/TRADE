# CLI Redesign Plan

## Context

The current CLI has 125+ commands across 12+ files. This redesign makes it faster, context-aware, and better organized while keeping all functionality.

## Design Decisions

- **Deferred connection**: App starts disconnected. "Connect to Exchange" unlocks trading menus.
- **Orders**: 2 groups (unified Place Order + Manage). Kill 4 nested sub-menus.
- **Account**: Keep all 14 options unchanged.
- **Data**: Keep all 24 operations, reorganize into sub-menus (top level: 9 items).
- **Main menu**: Context-aware (offline vs connected, Demo vs Live, running plays visible).
- **Forge/Backtest**: Keep separate, add cross-links and shared audit module.
- **Symbol input**: Recent symbols quick-pick (session-only, last 5).

---

## Completed Gates

| Gate | Summary | Status |
|------|---------|--------|
| G1: Foundation | `symbol_memory.py`, symbol helpers, running plays helper | DONE |
| G2: App Entrance | Deferred connection, offline/connected menus, PANIC button | DONE (pyright clean, manual test pending) |
| G3: Symbol Quick-Pick | Replaced all `get_input("Symbol...")` across 4 menu files | DONE |
| G4: Orders Menu | Unified `_place_order()` — type/side/symbol/amount/conditionals/TP-SL/preview/confirm | DONE (2026-02-22 audit confirmed) |
| G5: Data Menu | Top-level delegates to 4 sub-menus, data_env state, all 24 ops accessible | DONE (2026-02-22 audit confirmed) |
| G6: Context-Aware Header | Offline indicator, running plays panel, LIVE banner | DONE (pyright clean, manual test pending) |
| G7: Forge/Backtest Cross-Links | Shared audits module, cross-navigation | DONE (pyright clean, manual test pending) |
| G9: Plays Menu | 9-option plays lifecycle menu, wired to connected main menu | DONE (pyright clean, manual test pending) |

---

## Gate 8: Final Validation (In Progress)

**Automated checks (DONE 2026-02-22):**
- [x] `python trade_cli.py validate quick` — ALL 5 GATES PASSED (74.1s)
- [x] All new subcommand groups respond to `--help`
- [x] `pyright` — 0 errors across all 8 modified files

**Manual checks (pending):** See Phase 7 in `docs/TODO.md` for full checklist.

---

## Unified with P13: CLI Agent Autonomy

P4 (interactive menus) and P13 (agent CLI flags) merged into **P4+P13: Unified CLI**.
Both paths share the same `src/tools/` layer. Implementation phases 1-6 completed 2026-02-22.

**Result:** 50+ tool functions wired into 11 subcommand groups:

| Group | Subcommands | File |
|-------|-------------|------|
| backtest | run, preflight, indicators, data-fix, list, normalize, normalize-batch | `subcommands/backtest.py` |
| debug | math-parity, snapshot-plumbing, determinism, metrics | `subcommands/debug.py` |
| play | run, status, stop, watch, logs, pause, resume | `subcommands/play.py` |
| validate | quick, standard, full, real, module, pre-live, exchange | (inline in `trade_cli.py`) |
| account | balance, exposure, info, history, pnl, transactions, collateral | `subcommands/trading.py` |
| position | list, close, detail, set-tp, set-sl, set-tpsl, trailing, partial-close, margin, risk-limit | `subcommands/trading.py` |
| panic | (single command) | `subcommands/trading.py` |
| order | buy, sell, list, amend, cancel, cancel-all, leverage, batch | `subcommands/order.py` |
| data | sync, info, symbols, status, summary, query, heal, vacuum, delete | `subcommands/data.py` |
| market | price, ohlcv, funding, oi, orderbook, instruments | `subcommands/market.py` |
| health | check, connection, rate-limit, ws, environment | `subcommands/health.py` |

See `docs/CLI_ARCHITECTURE_AUDIT.md` for the original architecture audit (103 tools cataloged).
See `docs/brainstorm/CLI_AGENT_AUTONOMY.md` for the original gap audit.
