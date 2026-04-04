# TRADE TODO

Open work, bugs, and priorities. Completed work is in `memory/completed_work.md`.

---

## Active Work

### T1: Warmup Parity Validation
- [ ] Add a validation check that runs each indicator to `is_ready()` and compares vs registry formula
- [ ] **GATE**: `python trade_cli.py validate module --module coverage` passes

### T2: Structure Health — Deferred Integration Tests
- [ ] Feed identical 500-bar candle sequence through both `FeedStore` (backtest) and `LiveIndicatorCache` (live), compare all structure outputs bar-by-bar (requires engine-level integration test harness)
- [ ] Verify med_tf/high_tf structure update timing — `TFIndexManager` (backtest) vs buffer-length (live) produce updates on same bars (requires live provider mock)

### T9: ICT Features — Remaining Items
- [ ] `STR_020_fvg_mitigation.yml` — FVG mitigation tracking validation play
- [ ] Full 5-state FVG/OB lifecycle (active -> first_touch -> partial_fill -> mitigated -> invalidated) + FVG touch_count

---

## P1: Shadow Exchange Order Fidelity (SimExchange vs Bybit Parity)

See `docs/SHADOW_ORDER_FIDELITY_REVIEW.md` for full analysis.

14 features correct today. 4 HIGH gaps, 3 MEDIUM gaps identified.

### Phase 1: Price Fidelity (H1 + H2)
- [ ] `PriceModel.set_external_prices(mark, last, index)` — shadow mode feeds real WS prices
- [ ] Add `TriggerSource` enum (`LAST_PRICE`, `MARK_PRICE`, `INDEX_PRICE`) to `types.py`
- [ ] Add `tp_trigger_by`, `sl_trigger_by` to `Position` and `Order` (default `LAST_PRICE`)
- [ ] `check_tp_sl()` / `check_tp_sl_1m()` compare against configured price source
- [ ] `OrderBook.check_triggers()` respects `trigger_by` on stop orders
- [ ] Add `tp_trigger_by`, `sl_trigger_by` to Play DSL risk_model
- [ ] **GATE**: `python trade_cli.py validate quick` passes
- [ ] **GATE**: Validation plays for mark vs last trigger divergence

### Phase 2: Exit Fidelity (H3 + H4)
- [ ] New `TpSlLevel` dataclass: `price`, `size_pct`, `order_type`, `trigger_by`, `limit_price`, `triggered`
- [ ] Replace single `Position.take_profit`/`stop_loss` with `list[TpSlLevel]` (backward compat via computed properties)
- [ ] Wire `_check_tp_sl_exits()` to iterate levels, call `_partial_close_position()` for partials
- [ ] Add `modify_position_stops()` public API to `SimulatedExchange`
- [ ] DSL: split-TP syntax (`take_profit: [{level: 1.5, size_pct: 50}, ...]`)
- [ ] Engine adapter: modify-stops hook for strategy-driven TP/SL changes
- [ ] **GATE**: `python trade_cli.py validate quick` passes
- [ ] **GATE**: Validation plays for split-TP (3-level exit, SL after partial TP, modify SL post-entry)
- [ ] **GATE**: Existing 170 synthetic plays still pass

### Phase 3: Safety & Polish (M1 + M2 + M3)
- [ ] `closeOnTrigger`: cancel competing orders to free margin when SL fires
- [ ] Partial fills: `PARTIALLY_FILLED` status, `LiquidityModel` depth estimation, IOC/FOK differentiation
- [ ] Trailing stop: absolute `activePrice` + fixed `trail_distance` alongside existing pct/ATR modes
- [ ] **GATE**: `python trade_cli.py validate standard` passes

---

## P2: Deprecate Demo Mode — COMPLETE (2026-04-03)

Demo mode fully removed. Pipeline is now: **backtest -> shadow -> live**.
Both shadow and live use the live Bybit API (`api.bybit.com`).

- [x] `TradingMode` class removed — no more `PAPER`/`REAL` distinction
- [x] `TRADING_MODE` env var removed — mode selected per-play via `--mode`
- [x] `BYBIT_USE_DEMO` env var removed
- [x] All `BYBIT_DEMO_*` env vars removed
- [x] `api_keys.env` and `env.example` updated to live-only
- [x] `.github/workflows/smoke.yml` cleaned of demo references
- [x] Config foundation: `TradingEnv = Literal["live"]`, `DataEnv = Literal["backtest", "live"]`
- [x] Exchange layer: pybit calls always `demo=False`, `testnet=False`
- [x] Engine: modes = `Literal["backtest", "live", "shadow"]`, `InstanceMode` = LIVE/BACKTEST/SHADOW
- [x] Factory safety gate: `confirm_live=True` + API key validation (no more TRADING_MODE check)
- [x] All docstrings updated: "demo" → "shadow", "paper" → "simulated"
- [x] Security auditor agent config updated
- [x] **GATE**: `grep -r "TradingMode\|TRADING_MODE\|BYBIT_USE_DEMO\|BYBIT_DEMO" src/ --include="*.py"` → zero matches

---

## M4: Shadow Exchange — Remaining Phases

Phases 1-4 complete (ShadowEngine, FeedHub, Orchestrator, PerformanceDB, Daemon).
See `docs/SHADOW_EXCHANGE_DESIGN.md` for full architecture.

### Phase 5: ShadowGraduator — Promotion Pipeline
- [ ] `ShadowGraduator`: computes graduation scores daily
  - 10 graduation criteria (configurable thresholds): runtime, trades, PnL, Sharpe, drawdown, win rate, PF, consistency, regime diversity, no active drawdown
  - Composite scoring: consistency_score, regime_diversity_score, recency_score
  - Allocation sizing: half-Kelly x confidence adjustment, capped at 10% per play
- [ ] `config/shadow_graduation.yml`: default graduation thresholds
- [ ] Graduation report: Rich-formatted terminal output (metrics, regime breakdown, criteria checklist, recommendation)
- [ ] CLI: `shadow graduation check --instance X`, `shadow graduation check --all`, `shadow graduation report --instance X`
- [ ] Manual promotion: `shadow graduation promote --instance X --confirm` (creates M5 live config)
- [ ] **GATE**: Graduation scoring produces correct pass/fail for test scenarios
- [ ] **GATE**: Promotion outputs valid Play YAML with recommended risk parameters

### Phase 6: M6 Integration Hooks
- [ ] Market context capture: record regime + metrics alongside every trade and snapshot
- [ ] `export_training_data(symbol, days)` -> DataFrame for M6 consumption
- [ ] Performance-by-regime analytics: per-play breakdown across 4 regime types
- [ ] Play recommendation interface: `PlayRecommendation` dataclass (activate/deactivate/promote/demote + confidence + reason)
- [ ] **GATE**: Training data export covers 90 days, all required columns present
- [ ] **GATE**: Regime-performance breakdown matches manual verification

---

## M7: TradingView Parity Verification

See `docs/TV_PARITY_DESIGN.md` for full architecture.

Independent ground truth for all 13 structure detectors using Pine Script on real SOLUSDT charts via [tradesdontlie/tradingview-mcp](https://github.com/tradesdontlie/tradingview-mcp).

### Phase 1: Infrastructure + Rolling Window + Swing
- [ ] Install tradingview-mcp, create `.mcp.json`, verify `tv` CLI works
- [ ] `bridge.py` — TVBridge subprocess wrapper around `tv` CLI
- [ ] `ohlcv_alignment.py` — OHLCV parity check (DuckDB vs TradingView)
- [ ] `comparison.py` — 4 comparison strategies (numeric, event, level, zone)
- [ ] `runner.py` + `report.py` — orchestration + Rich/JSON output
- [ ] `rolling_window.pine` — `ta.lowest()`/`ta.highest()` (~15 lines)
- [ ] `swing.pine` — `ta.pivothigh()`/`ta.pivotlow()` + pairing (~120 lines)
- [ ] CLI: `python trade_cli.py validate module --module tv-parity`
- [ ] **GATE**: rolling_window + swing pass 95%+ match rate

### Phase 2: Trend + Market Structure + Zone
- [ ] `trend.pine` — embed swing + HH/HL/LH/LL wave classification (~140 lines)
- [ ] `market_structure.pine` — embed swing + BOS/CHoCH detection (~160 lines)
- [ ] `zone.pine` — embed swing + ATR-width zones (~90 lines)
- [ ] **GATE**: 5/5 detectors pass 95%+

### Phase 3: Fibonacci + Derived Zone + Displacement + Premium/Discount
- [ ] `fibonacci.pine` — swing pairs + fib levels (~90 lines)
- [ ] `derived_zone.pine` — multi-slot fib zones (~180 lines)
- [ ] `displacement.pine` — ATR + body/wick thresholds (~50 lines)
- [ ] `premium_discount.pine` — equilibrium calculation (~50 lines)
- [ ] **GATE**: 9/9 detectors pass 95%+

### Phase 4: ICT Chain (FVG + OB + Liquidity + Breaker)
- [ ] `fair_value_gap.pine` — 3-candle gap + tracking (~130 lines)
- [ ] `order_block.pine` — opposing candle + mitigation (~160 lines)
- [ ] `liquidity_zones.pine` — cluster + sweep detection (~140 lines)
- [ ] `breaker_block.pine` — OB flip on CHoCH (~200 lines)
- [ ] **GATE**: 13/13 detectors pass 95%+

---

## M8: UTA Portfolio Management

Full UTA control. One manager, no fallbacks. Sub-account isolation per play.
See `docs/UTA_PORTFOLIO_SPEC.md` for full spec. See `docs/UTA_PORTFOLIO_DESIGN.md` for API reference.
Branch: `feature/uta-portfolio-management`

### Phase 0: InstrumentRegistry — COMPLETE (2026-04-03)
- [x] `InstrumentSpec` frozen dataclass (symbol, category, settle_coin, base_coin, quote_coin, contract_type, filters)
- [x] `InstrumentRegistry` class — singleton, thread-safe (RLock), TTL cache (1h)
- [x] `refresh(categories)` — paginated fetch from `GET /v5/market/instruments-info` for linear + inverse
- [x] `resolve(symbol) -> InstrumentSpec` — raises KeyError if unknown
- [x] `get_routing(symbol) -> {"category": str, "settleCoin": str}` — for API call params
- [x] `list_symbols(category, settle_coin)` — filtered listing
- [x] **GATE**: Resolves BTCPERP → linear/USDC, BTCUSD → inverse/BTC. 675 instruments loaded.
- [x] **GATE**: pyright 0 errors on `src/core/instrument_registry.py`

### Phase 1: SubAccountManager — COMPLETE (2026-04-03)
- [x] `SubAccountInfo` dataclass (uid, username, api_key, api_secret, status, play_id, funded_amount)
- [x] `SubAccountManager` class — owns main_client, manages sub lifecycle
- [x] `create(username) -> SubAccountInfo` — creates sub + API keys via Bybit API
- [x] `get_client(uid) -> BybitClient` — lazily created, cached per uid
- [x] `fund(uid, coin, amount) -> str` — main→sub universal transfer (returns transfer_id)
- [x] `withdraw(uid, coin, amount) -> str` — sub→main transfer
- [x] `get_balance(uid, coin) -> dict` — query via main API key
- [x] `get_positions(uid) -> list` — query via sub's own client (all categories)
- [x] `freeze(uid)` / `unfreeze(uid)` / `delete(uid)` — lifecycle management
- [x] `save_state()` / `load_state()` — persist to `data/runtime/sub_accounts.json` (atomic write)
- [x] `sync_from_exchange()` — discover externally created subs
- [x] `assign_play(uid, play_id)` / `unassign_play(uid)` — play tracking
- [x] **GATE**: Created sub uid=555635291, queried balance, state persisted/reloaded, deleted. All passed.
- [x] **GATE**: pyright 0 errors on `src/core/sub_account_manager.py`
- [ ] **PENDING**: Code review agent findings (may require fixes)

### Phase 2: Exchange Layer — Replace Hardcoded USDT — COMPLETE (2026-04-03)
- [x] `bybit_trading.py` — 3x `settleCoin="USDT"` replaced with required `settle_coin` param, `ValueError` on missing
- [x] `bybit_client.py` — pass-through `settle_coin` params, removed dead `use_live_for_market_data`
- [x] `exchange_orders_manage.py` — multi-settle-coin iteration when no symbol, removed 9 empty try blocks
- [x] `exchange_orders_market.py` — removed 4x `_validate_trading_operation()` (deleted method from P2 cleanup)
- [x] `exchange_orders_limit.py` — removed 4x `_validate_trading_operation()`
- [x] `exchange_orders_stop.py` — removed 5x `_validate_trading_operation()`
- [x] `exchange_positions.py` — removed 6x `_validate_trading_operation()`
- [x] `exchange_manager.py` — `get_balance()` returns UTA-wide totals (totalEquity, totalAvailableBalance, etc.)
- [x] `position_manager.py` — uses `AccountMetrics` instead of `get_wallet("USDT")`
- [x] `live.py` — `get_balance()` and `get_equity()` use `AccountMetrics` only, no USDT wallet fallback
- [x] `realtime_state.py` — health check: `bool(self._wallet)` instead of `self._wallet.get("USDT")`
- [x] **GATE**: `grep "settleCoin.*USDT\|get_wallet.*USDT\|coin.*==.*USDT" src/ -r` → zero matches
- [x] **GATE**: pyright 0 errors on all 11 modified files
- [ ] **PENDING**: Code review agent findings (may require fixes)

### Phase 3: PortfolioManager — COMPLETE (2026-04-04)
- [x] `PortfolioSnapshot` dataclass — main account + sub-accounts + aggregates + exposure breakdown
- [x] `SubAccountSnapshot` dataclass — per-sub equity, positions, PnL, error tracking
- [x] `PortfolioManager` class — owns main_client, instrument_registry, sub_account_manager
- [x] `get_snapshot() -> PortfolioSnapshot` — parallel queries via ThreadPoolExecutor (max 8 workers)
- [x] `get_margin_headroom() -> float` — available for new deployments
- [x] `can_deploy_play(symbol, capital) -> (bool, reason)` — pre-flight check (registry + balance)
- [x] `recall_all() -> dict` — emergency stop: cancel orders, close positions, sweep funds to main
- [x] `to_dict()` on both snapshot classes for web UI JSON serialization
- [x] **GATE**: Live test — $0.47 equity, 4 coins, pre-flight checks for BTCUSDT/BTCPERP/FAKECOIN all correct
- [x] **GATE**: pyright 0 errors on `src/core/portfolio_manager.py`
- [ ] **PENDING**: Code review agent findings (may require fixes)

### Phase 4: Tool Layer (22 tools, Web UI Ready) — COMPLETE (2026-04-04)
- [x] `src/tools/portfolio_tools.py` — 22 tool functions (4 state + 2 instruments + 8 subs + 5 deploy + 1 emergency + 2 collateral)
- [x] `src/tools/specs/portfolio_specs.py` — 22 specs with category taxonomy
- [x] `src/cli/subcommands/portfolio.py` — dispatch for all portfolio subcommands
- [x] `src/cli/argparser.py` — `_setup_portfolio_subcommands` with `--json` on all parsers
- [x] `trade_cli.py` — portfolio command routing
- [x] Wire imports in `src/tools/__init__.py` and `src/tools/specs/__init__.py`
- [x] Deploy/stop/status/rebalance stubs (Phase 5 implementation)
- [x] **GATE**: `portfolio snapshot --json` → $0.47 equity, 4 coins, 0 subs
- [x] **GATE**: `portfolio resolve BTCPERP --json` → linear/USDC
- [x] **GATE**: `portfolio instruments --settle-coin USDC --json` → 70 instruments
- [x] **GATE**: `portfolio subs list --json` → 0 sub-accounts
- [x] **GATE**: pyright 0 errors on all Phase 4 files
- [ ] **PENDING**: Code review agent findings (may require fixes)

### Phase 5: PlayDeployer + Live Engine Integration — COMPLETE (2026-04-04)
- [x] `PlayDeployer` class — deploy (create sub → fund → engine → runner), stop, health check
- [x] `PlayEngineFactory._create_live()` — accepts optional `client: BybitClient`
- [x] `LiveExchange.__init__()` — accepts optional `client: BybitClient` (injected for sub-accounts)
- [x] `ExchangeManager.__new__()` — sub-account instances bypass singleton
- [x] Active runners map + heartbeat `is_healthy(uid)` check
- [x] Stop pipeline: cancel task → close positions (reduce_only) → unassign play
- [x] Tool functions wired: deploy, stop, status, rebalance (all via PlayDeployer)
- [x] **GATE**: Full E2E test — pre-flight → create sub → fund $0.10 → start runner → health OK → stop → cleanup
- [x] **GATE**: pyright 0 errors on all Phase 5 files
- [ ] **PENDING**: Code review agent findings

---

## M9: Shadow Unification + Play DSL Split

Kill factory shadow (no-op ShadowExchange/ShadowRunner). Unify on daemon shadow (full SimExchange + PerformanceDB).
Split Play DSL: `account:` (shared) + `backtest:` (sim equity/slippage) + `deploy:` (live capital/settle coin).
Shadow reads `deploy.capital` for equity — dress rehearsal at deploy scale.

### Phase 1: Kill Factory Shadow — COMPLETE (2026-04-04)
- [x] Delete `src/engine/runners/shadow_runner.py` (entire file — ShadowRunner, ShadowSignal, ShadowStats)
- [ ] Delete `ShadowExchange` class from `src/engine/adapters/backtest.py:543-591`
- [ ] Delete `_create_shadow()` from `src/engine/factory.py`
- [ ] Delete `is_shadow` property + shadow signal intercept from `src/engine/play_engine.py:551-561`
- [ ] Remove "shadow" from mode Literal in `factory.py`, `play_engine.py`, `interfaces.py`
- [ ] Remove ShadowExchange/ShadowRunner from `__init__.py` exports (engine, adapters, runners)
- [ ] `src/cli/subcommands/play.py` — replace shadow routing with redirect to `shadow run`
- [ ] `src/cli/argparser.py` — remove "shadow" from `--mode` choices
- [ ] **GATE**: `grep -r "ShadowExchange\|ShadowRunner\|is_shadow\|_create_shadow" src/ --include="*.py"` → zero hits
- [ ] **GATE**: pyright passes on `src/engine/`
- [x] **GATE**: pyright 0 errors, zero shadow references in src/

### Phase 2: Add BacktestConfig + DeployConfig Models — COMPLETE (2026-04-04)
- [x] `BacktestConfig` dataclass: `equity: float`, `slippage_bps: float` (with backward compat from `account:`)
- [ ] `DeployConfig` dataclass: `capital: float`, `settle_coin: str`, `dcp_window: int`
- [ ] Add `backtest_config: BacktestConfig` and `deploy_config: DeployConfig` fields to `Play` dataclass
- [ ] `Play.from_dict()` — parse `d.get("backtest")` and `d.get("deploy")` sections
- [ ] Backward compat: if no `backtest:` section, construct from `account:` values
- [ ] Add `backtest:` and `deploy:` defaults to `config/defaults.yml`
- [ ] **GATE**: All existing plays load without changes (backward compat)
- [ ] **GATE**: `python3 trade_cli.py backtest run --play scalp_1m --synthetic` passes
- [x] **GATE**: Existing plays load with backward compat, pyright clean

### Phase 3: Wire Consumers to New Config — COMPLETE (2026-04-04)
- [x] `_build_config_from_play()` — backtest reads `play.backtest_config.equity`, live reads `play.deploy_config.capital`
- [x] `ShadowEngine` — reads `play.deploy_config.capital` for equity (dress rehearsal at deploy scale)
- [x] `PlayDeployer.deploy()` — defaults capital from `play.deploy_config`, uses deploy settle_coin
- [x] **GATE**: Factory reads correct equity per mode, pyright clean

### Phase 4: Remove Migrated Fields from AccountConfig
- [ ] Remove `starting_equity_usdt` from AccountConfig (moved to BacktestConfig)
- [ ] Remove `slippage_bps` from AccountConfig (moved to BacktestConfig)
- [ ] Remove dead fields: `max_notional_usdt`, `max_margin_usdt` (never used anywhere)
- [ ] Update all references across codebase
- [ ] **GATE**: `grep -r "max_notional_usdt\|max_margin_usdt" src/` → zero hits
- [ ] **GATE**: `python3 trade_cli.py validate standard` passes
- [ ] **GATE**: pyright passes on all source

### Phase 5: Documentation + Final Audit
- [ ] Update `CLAUDE.md` — remove `play run --mode shadow`, update architecture
- [ ] Update `docs/PLAY_DSL_REFERENCE.md` — document `backtest:` and `deploy:` sections
- [ ] Run full audit agent for orphaned references
- [ ] **GATE**: `python3 trade_cli.py validate full` passes
- [ ] **GATE**: All docs reflect three-section Play DSL

---

## Pre-Deployment (fix before live trading)

### T3: Live Blockers
- [ ] **DATA-011** `_handle_stale_connection()` does REST refresh but doesn't force pybit reconnect
- [ ] **DATA-017** `panic_close_all()` cancel-before-close ordering — needs integration test
- [ ] **H22** Sim accepts `funding_events` kwarg but no funding event generation pipeline exists yet

### T4: Live Engine Rubric
- [ ] Define live parity rubric: backtest results as gold standard
- [ ] Shadow mode 24h validation (replaces demo mode validation — see P2)
- [ ] Verify sub-loop activation in live mode

### T5: Live Trading Integration
- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Shadow trading integration (replaces paper/demo trading — see P2)

### T6: Manual Verification (requires exchange connection)
- [ ] Run shadow play 10+ minutes — NO "Signal execution blocked" warnings
- [ ] `play run --play AT_001 --mode shadow --headless` prints JSON, Ctrl+C stops
- [ ] `play watch --json`, `play stop --all` work correctly
- [ ] Start -> stop -> cooldown -> restart timing works (15s)

---

## Accepted Behavior

| ID | Note |
|----|------|
| GAP-BD2 | `os._exit(0)` correct — pybit WS threads are non-daemon |

## Platform Issues

- **DuckDB file locking on Windows** — sequential scripts, `run_full_suite.py` has retry logic
- **Windows `os.replace` over open files** — `PermissionError` if another process is mid-read of instance JSON

## Known Issues (non-blocking)

- **pandas_ta `'H'` Deprecation Warning** — cosmetic, `pandas_ta.vwap()` passes `'H'` to `index.to_period()`. Our `IncrementalVWAP` is unaffected.

---

## Commands

### Validation

```bash
python trade_cli.py validate quick              # Pre-commit (~2min, 7 gates)
python trade_cli.py validate standard           # Pre-merge (~7min, 13 gates)
python trade_cli.py validate full               # Pre-release (~10min, 15 gates)
python trade_cli.py validate real               # Real-data verification (~2min)
python trade_cli.py validate module --module X --json  # Single module (PREFERRED for agents)
python trade_cli.py validate pre-live --play X  # Deployment gate
python trade_cli.py validate exchange           # Exchange integration (~30s)
```

### Backtest

```bash
python trade_cli.py backtest run --play X --sync       # Single backtest (sync data first)
python trade_cli.py backtest run --play X --synthetic   # Single backtest (synthetic data)
python scripts/run_full_suite.py                        # 170-play synthetic suite
python scripts/run_real_verification.py                 # 60-play real verification
python scripts/verify_trade_math.py --play X            # Math verification for a play
```

### Debugging & Logging

```bash
# Verbosity flags (apply to ANY command)
python trade_cli.py -q ...                     # Quiet: WARNING only (CI, scripts)
python trade_cli.py -v ...                     # Verbose: signal traces, structure events
python trade_cli.py --debug ...                # Debug: full hash tracing, all internals

# Debug subcommands (diagnostic tools, all support --json)
python trade_cli.py debug math-parity --play X
python trade_cli.py debug snapshot-plumbing --play X
python trade_cli.py debug determinism --run-a A --run-b B
python trade_cli.py debug metrics
```

### Log Files

```bash
tail -f logs/trade.jsonl                       # Live stream
cat logs/trade.jsonl | jq '.event'             # Events only
cat artifacts/<input_hash>/events.jsonl        # Per-run fill/close events
```
