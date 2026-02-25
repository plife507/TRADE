# Shadow Exchange + Sub-Account Promotion Pipeline

**Date:** 2026-02-25
**Status:** Design complete, pending database migration
**Prerequisite:** Database migration (separate effort — must complete first)

## Context

**Problem**: No way to forward-test strategies on real live data with full PnL tracking before committing real money. No automated path from "strategy looks good" to "strategy trades real money in an isolated sub-account."

**Goal**: Build a 4-stage pipeline:
```
BACKTEST → DEMO (prove trades fire) → SHADOW EXCHANGE (long-term forward test) → LIVE (sub-accounts)
```

**Pipeline roles**:
- **Backtest**: Fast elimination on synthetic + real historical data
- **Demo**: Short-duration proof that trades fire on Bybit (real fills, slippage, TP/SL) — "prove it works"
- **Shadow Exchange**: Long-duration forward test using real WebSocket data + SimulatedExchange — builds statistical confidence (Sharpe, DD, win rate) on unseen live data
- **Live (sub-accounts)**: Real money, one Bybit sub-account per strategy, isolated capital

**Key insight**: 80%+ of infrastructure already exists. `SimulatedExchange`, `LiveDataProvider`, `BacktestExchange` adapter, and `RealtimeState` just need wiring in a new runner.

## What Already Exists

| Component | File | Status |
|-----------|------|--------|
| SimulatedExchange | `src/backtest/sim/exchange.py` | Complete — full fills, PnL, TP/SL, liquidation |
| BacktestExchange adapter | `src/engine/adapters/backtest.py` | Complete — wraps SimExchange, implements ExchangeAdapter |
| LiveDataProvider | `src/engine/adapters/live.py` | Complete — WebSocket candles + incremental indicators |
| RealtimeState | `src/data/realtime_state.py` | Complete — shared singleton, multiple subscribers |
| ShadowRunner | `src/engine/runners/shadow_runner.py` | Exists but signal-only (no PnL, no SimExchange) |
| LiveRunner | `src/engine/runners/live_runner.py` | Complete — template for LiveSimRunner |
| PlayEngineFactory | `src/engine/factory.py` | Complete — needs `live_sim` mode added |

---

## Phase 1: LiveSimRunner (Single Engine — Shadow Exchange Core)

**Goal**: One PlayEngine running on real WebSocket data with SimulatedExchange, tracking PnL.

### 1.1 Add `"live_sim"` mode to engine

**`src/engine/play_engine.py`**: Add `"live_sim"` to mode literal, add `is_live_sim` property
**`src/engine/interfaces.py`**: Add `"live_sim"` to mode literal
**`src/engine/factory.py`**: Add `_create_live_sim()` — wires `LiveDataProvider` + `BacktestExchange` + `InMemoryStateStore`. Route in `create()` dispatch.

### 1.2 Data source: Live WebSocket (api.bybit.com)

Shadow engines use **live** WebSocket (`stream.bybit.com`) for real market data — no API key needed for public kline streams. `LiveDataProvider` connects with `demo=False`, public streams only (no position sync, no order callbacks).

### 1.3 Make BacktestExchange.step() work for live sim

**`src/engine/adapters/backtest.py`**: Implement `step(candle)` to construct a `Bar` and call `sim_exchange.process_bar(bar)`. BacktestRunner path unaffected (it calls `_process_bar_fills()` before `process_bar()`).

### 1.4 Create LiveSimRunner

**New file**: `src/engine/runners/live_sim_runner.py`

Based on `LiveRunner` (reuse candle loop, kline callback, warmup gating, dedup), but:

| Aspect | LiveRunner | LiveSimRunner |
|--------|-----------|---------------|
| Exchange | LiveExchange (Bybit API) | BacktestExchange (SimExchange) |
| Position sync | REST API reconciliation | N/A (local state always correct) |
| Safety gates | `_position_sync_ok`, WS health, panic | WS health only |
| Fill processing | Async exchange callbacks | Synchronous sim on each bar |
| Equity tracking | From exchange REST API | From local ledger |

Bar processing loop:
1. Receive closed candle from WebSocket queue
2. Route to `data_provider.on_candle_close()` (updates indicators/structures)
3. On exec TF: `engine.process_bar(-1)` → signal
4. If signal: `engine.execute_signal(signal)` → SimExchange
5. Record equity point, check demotion criteria

SimExchange initialization on startup:
- Create `SimulatedExchange(symbol, initial_capital, risk_profile)`
- Wire via `exchange_adapter.set_simulated_exchange(sim_exchange)`

### 1.5 EngineManager + CLI integration

**`src/engine/manager.py`**: Add `LIVE_SIM` to `InstanceMode`, `_max_live_sim = 50`
**`src/cli/argparser.py`**: Add `"live_sim"` to mode choices
**`src/cli/subcommands/play.py`**: Add `elif mode == "live_sim":` branch
**`src/engine/runners/__init__.py`**: Export `LiveSimRunner`

### Phase 1 GATE
- [ ] `python trade_cli.py play run --play AT_001 --mode live_sim` runs 30+ min
- [ ] Signals fire and SimExchange fills them
- [ ] Equity curve is non-trivial
- [ ] `validate quick` passes, pyright passes

---

## Phase 2: Multi-Engine + Persistence + Factory CLI

**Goal**: Run N shadow engines concurrently. Persist state. CLI for batch operations.

### 2.1 LiveSimJournal (`src/engine/live_sim_journal.py`)
- `events.jsonl` per instance in `data/live_sim/{play_id}/`
- Signal events, fill events, equity snapshots, demotion events
- Pattern follows existing `BacktestJournal` in `src/engine/journal.py`

### 2.2 State serialization (`src/engine/live_sim_state.py`)
- Serialize SimExchange state, equity curve, rolling stats to `data/live_sim/{play_id}/state.json`
- LiveSimRunner resumes from checkpoint on restart

### 2.3 Multi-engine orchestrator (`src/engine/runners/live_sim_orchestrator.py`)
- Manages N `LiveSimRunner` instances on same symbol
- Each engine: own `LiveDataProvider` subscribing to shared `RealtimeState` singleton
- Sequential bar processing (v1: 50 engines x 10ms = 500ms per 15m bar)
- Methods: `add_play()`, `remove_play()`, `get_leaderboard()`, `stop_all()`

### 2.4 Factory CLI (`src/cli/subcommands/factory.py`)
```bash
python trade_cli.py factory live-sim start --plays A B C D E
python trade_cli.py factory live-sim stop --play A / --all
python trade_cli.py factory status
python trade_cli.py factory leaderboard
```

### Phase 2 GATE
- [ ] 5+ plays running concurrently in live sim
- [ ] `factory leaderboard` shows real-time equity rankings
- [ ] Kill + restart — state resumes from checkpoint
- [ ] Memory < 500MB for 10 engines
- [ ] `validate quick` passes

---

## Phase 3: Scoring + Promotion/Demotion Engine

**Goal**: Automated evaluation with promotion/demotion criteria.

### 3.1 New package: `src/factory/`
```
src/factory/
├── __init__.py
├── scoring.py        # PlayScore dataclass, composite scoring function
├── promotion.py      # PromotionEngine — evaluate promote/demote/hold
├── tracker.py        # PlayLifecycle — persistent stage tracking (JSON per play)
└── pipeline.py       # PromotionPipeline — orchestrate stage transitions
```

### 3.2 Scoring function (`src/factory/scoring.py`)
- `PlayScore` dataclass: Sharpe, max DD, win rate, profit factor, trade count, consecutive losses, days active
- `composite` property: weighted score (Sharpe 30%, DD 25%, WR 15%, PF 15%, trades 10%, consistency 5%)

### 3.3 Promotion/Demotion criteria (`src/factory/promotion.py`)

**Pipeline**: `DEMO (prove) → SHADOW (validate) → LIVE (trade)`

| Metric | Demo → Shadow | Shadow → Live |
|--------|--------------|---------------|
| Min duration | 24h | 7 days |
| Min trades | 3 | 10 |
| Min Sharpe | N/A (just prove execution) | 1.0 |
| Max DD | N/A | 15% |
| Min win rate | N/A | 40% |
| Min PF | N/A | 1.5 |

**Demotion triggers** (immediate):
- Shadow: DD > 25%, 7 consecutive losses, Sharpe < -0.5
- Live: DD > 10%, 5 consecutive losses

### 3.4 Play lifecycle tracker (`src/factory/tracker.py`)
- Persistent JSON per play: `data/factory/{play_id}/lifecycle.json`
- Tracks: current stage, stage history, promotions/demotions, scores over time

### 3.5 Auto-demotion in LiveSimRunner
- After each trade close, check demotion criteria
- If breached: log event, update lifecycle, stop runner

### Phase 3 GATE
- [ ] Auto-demotion fires on 25% DD
- [ ] Lifecycle tracks transitions in `data/factory/`
- [ ] `factory leaderboard` shows composite scores
- [ ] `validate quick` passes

---

## Phase 4: Sub-Account Integration + Live Promotion

**Goal**: Promote shadow winners to real Bybit sub-accounts with isolated capital.

### 4.1 Multi-credential registry
**New file**: `config/sub_accounts.yml` (gitignored)
```yaml
sub_accounts:
  factory_001:
    api_key_env: "BYBIT_SUB_001_KEY"
    api_secret_env: "BYBIT_SUB_001_SECRET"
    play_id: null          # Assigned on promotion
    allocated_usdt: 0
    status: "available"    # available | active | frozen
```

**New file**: `src/factory/credentials.py` — `SubAccountRegistry` class

### 4.2 Per-sub-account ExchangeManager
**`src/config/config.py`**: Add `BybitConfig.for_sub_account()` factory method
**`src/engine/manager.py`**: Add `start_sub_account()` method

### 4.3 Capital allocation via Bybit Universal Transfer API
**New file**: `src/factory/capital.py` — `CapitalAllocator` class
- `allocate(sub_uid, amount)` — master → sub via `create_universal_transfer()`
- `recall(sub_uid, amount)` — sub → master
- `get_balance(sub_uid)` — query sub-account balance

### 4.4 Full promotion pipeline
**`src/factory/pipeline.py`**:
```
Promote to Live:
  1. Validate promotion criteria met
  2. Find available sub-account from registry
  3. Assign sub-account to play
  4. Allocate capital from master
  5. Create LiveRunner with sub-account credentials
  6. Update lifecycle tracker

Demote from Live:
  1. Close all positions (reduce_only)
  2. Stop LiveRunner
  3. Transfer remaining capital back to master
  4. Release sub-account
  5. Optionally restart as shadow
  6. Update lifecycle tracker
```

### 4.5 CLI commands
```bash
python trade_cli.py factory promote --play X --capital 1000 --confirm
python trade_cli.py factory demote --play X
python trade_cli.py factory auto-promote            # Promote all eligible
python trade_cli.py factory account allocate --sub factory_001 --amount 1000
python trade_cli.py factory account recall --sub factory_001 --amount 500
python trade_cli.py factory account status
```

### Phase 4 GATE
- [ ] SubAccountRegistry loads from config/sub_accounts.yml
- [ ] CapitalAllocator transfers $10 to/from test sub-account (real Bybit)
- [ ] `factory promote --play X --capital 100 --confirm` starts LiveRunner on sub-account
- [ ] `factory demote --play X` closes positions, recalls capital
- [ ] Circuit breaker fires on 10% DD
- [ ] `validate quick` passes

---

## File Summary

### New Files (13)
| File | Phase | Purpose |
|------|-------|---------|
| `src/engine/runners/live_sim_runner.py` | 1 | Shadow exchange runner |
| `src/engine/live_sim_journal.py` | 2 | JSONL event journal |
| `src/engine/live_sim_state.py` | 2 | State serialization |
| `src/engine/runners/live_sim_orchestrator.py` | 2 | Multi-engine management |
| `src/cli/subcommands/factory.py` | 2 | CLI handlers for factory |
| `src/factory/__init__.py` | 3 | Factory package |
| `src/factory/scoring.py` | 3 | Composite scoring |
| `src/factory/promotion.py` | 3 | Promotion/demotion engine |
| `src/factory/tracker.py` | 3 | Play lifecycle tracker |
| `src/factory/pipeline.py` | 4 | Full promotion orchestrator |
| `src/factory/credentials.py` | 4 | Sub-account credential registry |
| `src/factory/capital.py` | 4 | Capital allocation (Bybit transfers) |
| `config/sub_accounts.yml` | 4 | Credential config (gitignored) |

### Modified Files (8)
| File | Phase | Change |
|------|-------|--------|
| `src/engine/play_engine.py` | 1 | Add `"live_sim"` mode, `is_live_sim` property |
| `src/engine/interfaces.py` | 1 | Add `"live_sim"` to mode literal |
| `src/engine/factory.py` | 1 | Add `_create_live_sim()` factory method |
| `src/engine/adapters/backtest.py` | 1 | Implement `step()` for live sim |
| `src/engine/manager.py` | 1+4 | Add LIVE_SIM mode, sub-account support |
| `src/engine/runners/__init__.py` | 1 | Export LiveSimRunner |
| `src/cli/argparser.py` | 1+2 | Add live_sim mode, factory commands |
| `src/cli/subcommands/play.py` | 1 | Handle live_sim mode |

### Reused As-Is (no changes needed)
- `src/backtest/sim/exchange.py` — SimulatedExchange
- `src/data/realtime_state.py` — shared WebSocket singleton
- `src/engine/adapters/live.py` — LiveDataProvider

---

## Risk Assessment

| Phase | Risk | Mitigation |
|-------|------|------------|
| **1 (LiveSim)** | LOW | All components exist — just wiring. Compare shadow equity vs backtest on same window. |
| **2 (Multi)** | MEDIUM | N LiveDataProviders sharing RealtimeState callbacks. Start with 5, profile memory. |
| **3 (Scoring)** | LOW | Pure business logic. Start conservative, tune weights based on results. |
| **4 (Sub-accts)** | HIGH | Real money. Always start $100 minimum, require `--confirm`, auto-demote on DD breach, `reduce_only` on all closes. |

## Related Documents

- `docs/brainstorm/BYBIT_SUB_ACCOUNTS.md` — Sub-account API details, rate limits, demo limitations
- `docs/design/strategy_factory/` — Full factory architecture (5 docs)
- `docs/brainstorm/SYSTEM_VISION.md` — End-to-end knowledge → production pipeline
- `docs/DATABASE_ALTERNATIVES_REVIEW.md` — DB migration options (prerequisite)
