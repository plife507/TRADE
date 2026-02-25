# Strategy Factory: Design Overview

> **Status**: Active design
> **Created**: 2026-02-25
> **Goal**: Mass-produce, test, and promote trading strategies autonomously

## The Idea

Run hundreds or thousands of strategy variations simultaneously — through
conception, backtesting, live-data simulation, and promotion to real trading.
Find the ones that actually work, discard the rest.

## Pipeline

```
CONCEIVE ──► BACKTEST ──► LIVE SIM ──► PROMOTE
  (AI)      (synthetic    (real data    (demo /
             + real)       + SimExch)    sub-accounts)
```

| Stage | Scale | Data | Exchange | PnL | Duration |
|-------|-------|------|----------|-----|----------|
| Conceive | 1000s generated | - | - | - | Seconds |
| Backtest (synthetic) | 1000s tested | Synthetic | SimulatedExchange | Simulated | Minutes |
| Backtest (real) | Top 100 | DuckDB historical | SimulatedExchange | Simulated | Minutes |
| Live Sim | Top 20-50 | WebSocket real-time | SimulatedExchange | Simulated (live) | Days-weeks |
| Demo | Top 5-10 | WebSocket real-time | Bybit demo API | Real fills (fake $) | Days-weeks |
| Live | Top 1-3 | WebSocket real-time | Bybit production | Real fills (real $) | Ongoing |

## Design Documents

| Document | Contents |
|----------|----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture, component design, data flow |
| [LIVE_SIM_ENGINE.md](LIVE_SIM_ENGINE.md) | LiveSimRunner + DataFanout — the core new piece |
| [PLAY_GENERATION.md](PLAY_GENERATION.md) | Strategy generation, parameter grids, mutation |
| [PROMOTION_PIPELINE.md](PROMOTION_PIPELINE.md) | Scoring, ranking, auto-promotion rules |

## Prior Art (existing brainstorms)

These docs contain relevant prior investigation:

| Doc | Key takeaways |
|-----|---------------|
| `docs/brainstorm/PARALLEL_BACKTESTING.md` | "Sync once, run many" pattern, DuckDB parallel readers, ProcessPoolExecutor |
| `docs/brainstorm/BYBIT_SUB_ACCOUNTS.md` | 1 sub-account per Play, API endpoints, demo limitations, rate limits |
| `docs/brainstorm/SYSTEM_VISION.md` | Full Knowledge → Agent → GE → Demo → Live pipeline vision |

## What Already Exists

| Component | File | Status |
|-----------|------|--------|
| SimulatedExchange | `src/backtest/sim/exchange.py` | Complete — full fills, PnL, TP/SL, liquidation |
| ShadowExchange | `src/engine/adapters/backtest.py` | Complete — signal-only, no PnL (not what we want) |
| ShadowRunner | `src/engine/runners/shadow_runner.py` | Complete — drives shadow mode |
| LiveDataProvider | `src/engine/adapters/live.py` | Complete — WebSocket candles + indicators |
| Parallel backtest | `src/engine/runners/parallel.py` | Complete — ProcessPool, read-only DuckDB |
| Play discovery | `src/backtest/play/play.py` | Complete — list_plays(), load_play() |
| EngineManager limits | `src/engine/manager.py` | 1 demo per symbol, 1 live global |
| forge-play skill | `.claude/skills/forge-play/` | Partial — interactive, not programmatic |
| RealtimeState | `src/data/realtime_state.py` | Complete — shared WebSocket state |

## What Needs Building

| Component | Priority | Description |
|-----------|----------|-------------|
| **LiveSimRunner** | P0 | New runner: LiveDataProvider + SimulatedExchange |
| **DataFanout** | P0 | Multiplex 1 WebSocket → N engines |
| **StrategyGenerator** | P1 | Template + param grid → N Play YAMLs |
| **MassRunner** | P1 | Orchestrate 100s-1000s of LiveSimRunners |
| **Leaderboard** | P2 | Score, rank, track live sim results over time |
| **PromotionEngine** | P2 | Auto-promote winners to demo / sub-accounts |
| **SubAccountManager** | P3 | Bybit sub-account lifecycle (create, fund, monitor) |
