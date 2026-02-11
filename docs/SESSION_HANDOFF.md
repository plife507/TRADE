# Session Handoff

**Date**: 2026-02-11
**Branch**: feature/unified-engine
**Phase**: Demo Stress Test Complete + Architecture Gaps Identified

---

## Current State

**Engine: FULLY VERIFIED + LIVE READY**

| Suite | Result |
|-------|--------|
| Synthetic (170 plays) | 170/170 PASS, 0 fail, 0 zero-trade |
| Real-data (60 plays) | 60/60 PASS, 60/60 math verified (23 checks each) |
| **Demo readiness (84 checks)** | **84/84 PASS across 12 phases** |
| Indicators covered | 44/44 (synthetic), 41/43 (real) |
| Structures covered | 7/7 |
| DSL operators covered | All (synthetic), 19/24 (real) |
| Symbols tested (real) | BTC, ETH, SOL, LTC |

**Open Bugs: NONE (6 production bugs found and fixed during demo stress test)**

---

## Demo Readiness Test (2026-02-10/11)

`scripts/test_demo_readiness.py` -- 84 checks across 12 phases, exercises REAL engine code through REAL Bybit demo API.

### Phases

| Phase | What | Checks | Status |
|-------|------|--------|--------|
| 1 | Play Loading & Config | 5 | PASS |
| 2 | REST Connectivity | 7 | PASS |
| 3 | DataProvider + Indicator Warmup | 7 | PASS |
| 4 | WebSocket Data Feed | 8 | PASS |
| 5 | Order Execution (market orders) | 12 | PASS |
| 6 | Error Edge Cases | 6 | PASS |
| 7 | Full EngineManager Integration | 8 | PASS |
| 8 | Journal & State Persistence | 5 | PASS |
| 9 | Safety & Circuit Breakers | 6 | PASS |
| 10 | Multi-TF Data Routing | 5 | PASS |
| 11 | Advanced Order Lifecycle | 5 | PASS |
| 12 | Runner State Machine & Limits | 10 | PASS |

### Bugs Found & Fixed During Stress Test

1. **LiveExchange snapshot** -- `LiveExchangeStateAdapter` missing proper flat-account defaults
2. **Order dataclass access** -- `get_open_orders()` returns `Order` dataclass, not dict (used `.order_id` not `.get("orderId")`)
3. **Unicode encoding on Windows** -- Exchange manager logging used unicode arrows; added `sys.stdout.reconfigure(encoding="utf-8")`
4. **DuckDB write locks** -- Test process locked DB; fixed with `reset_stores(force_read_only=True)` at startup
5. **`get_candle()` vs `get_candle_for_tf()`** -- `get_candle()` doesn't accept `tf_role`; correct method is `get_candle_for_tf(index, tf_role)`
6. **Coroutine warning** -- `LiveDataProvider.disconnect()` is async but was called without `await` (non-fatal)

### How to Run

```bash
# All phases (default)
python scripts/test_demo_readiness.py

# Skip order execution (read-only mode)
python scripts/test_demo_readiness.py --skip-orders

# Custom play file
python scripts/test_demo_readiness.py --play plays/sol_ema_cross_demo.yml
```

---

## Architecture Investigation: Gaps Found (2026-02-11)

### GAP #1: Warmup Hardcoded to 100 Bars (CRITICAL)

**Problem**: `LiveDataProvider._warmup_bars` is always 100 regardless of Play's actual indicator/structure needs.

**Where**: `src/engine/adapters/live.py:581`
```python
self._warmup_bars = getattr(play, 'warmup_bars', 100)  # Play doesn't have warmup_bars
```

**What should happen**: Use `get_warmup_from_specs()` from `src/indicators/compute.py` to compute warmup dynamically based on the Play's features. An EMA(200) needs 200+ bars, not 100.

**Available code** (already exists, just not wired up):
- `get_warmup_from_specs(specs)` -- max warmup across all feature specs
- `get_warmup_from_specs_by_role(specs_by_role)` -- per-TF role warmup
- Each `FeatureSpec` has `.warmup_bars` property

**Fix needed**:
1. Replace hardcoded 100 with `get_warmup_from_specs()` call in `LiveDataProvider.__init__()`
2. Compute per-TF warmup (low_tf may need 200, high_tf may need 50)
3. Add REST API fallback in `_load_tf_bars()` when both bar buffer and DuckDB are empty

### GAP #2: No REST API Fallback for Warmup Data

**Problem**: `_load_tf_bars()` tries bar buffer -> DuckDB -> gives up. If both are empty (fresh install, new symbol), indicators start cold with zero history.

**Where**: `src/engine/adapters/live.py:747-776`

**Fix needed**: Add step 3: fetch bars via `ExchangeManager.bybit.get_klines(symbol, interval, limit=warmup_bars)` as REST fallback.

### GAP #3: Starting Equity Ignored in Live/Demo (IMPORTANT)

**Problem**: Play's `account.starting_equity_usdt` is only a fallback. Live/demo uses real exchange balance.

**Behavior chain**:
```
LiveExchange.get_equity()
  1. Try WebSocket account metrics (real balance)
  2. Try REST get_balance() (real balance)
  3. FALLBACK: config.initial_equity (Play value, rarely reached)
```

**Impact**: If Play says `starting_equity_usdt: 10000` but real account has `$5000`, engine silently uses `$5000` for all sizing calculations. No warning logged.

**Fix needed**: Add preflight equity reconciliation warning in `LiveRunner.start()`.

### GAP #4: Leverage Not Set on Startup (IMPORTANT)

**Problem**: Leverage is set PER-ORDER in `OrderExecutor.execute_with_leverage()`, not during account initialization.

**Where**: `src/core/order_executor.py:508` -- `self.exchange.set_leverage(signal.symbol, capped_leverage)`

**Impact**: If trading restarts mid-session, Bybit's account leverage may not match Play config until next order. Liquidation calcs could be wrong.

**Fix needed**: Call `set_leverage()` during `LiveExchange.connect()` or `LiveRunner.start()`.

### GAP #5: Fee Model Not Reconciled

**Problem**: Play specifies `taker_bps: 5.5` but actual Bybit fees depend on VIP tier. Engine doesn't check the mismatch.

**Impact**: Expected PnL != actual PnL. Minor for most cases but relevant for high-frequency strategies.

### Summary: Play Fields Backtest vs Live

| Field | Backtest | Live/Demo | Gap? |
|-------|----------|-----------|------|
| `starting_equity_usdt` | Used as initial capital | Fallback only (real balance used) | YES |
| `max_leverage` | Enforced throughout | Set per-order only | PARTIAL |
| `max_drawdown_pct` | Engine halts on breach | Engine halts on breach | No |
| `fee_model` | Deducted from fills | Ignored (Bybit's real fees) | YES (expected) |
| `slippage_bps` | Added to fills | Ignored (real slippage) | No (expected) |
| `min_trade_notional_usdt` | Enforced in sim | Validated in RiskManager | No |
| `position_policy` | Enforced in signal eval | Enforced in OrderExecutor | No |
| `risk_model.stop_loss` | SL trigger in sim | Sent to exchange as TP/SL orders | No |
| `risk_model.take_profit` | TP trigger in sim | Sent to exchange | No |
| `features` (indicators) | Computed every bar | Incremental O(1) | No |
| `structures` | Incremental tracking | Incremental tracking | No |
| `timeframes` | Multi-TF stepped | All TFs via WebSocket | No |

---

## Priority Fixes for Next Session

1. **Dynamic warmup** (GAP #1 + #2) -- Wire `get_warmup_from_specs()` into LiveDataProvider, add REST fallback
2. **Leverage on startup** (GAP #4) -- Call `set_leverage()` in `LiveExchange.connect()`
3. **Equity reconciliation** (GAP #3) -- Warning when real balance != Play config
4. **Add warmup test** -- New phase in `test_demo_readiness.py` validating dynamic warmup

---

## Recent Fixes (2026-02-10)

### Live Trading Bugs (found by parity audit + demo test)
- `play.py:_parse_features()` -- `source: volume` YAML field was silently ignored
- `LiveIndicatorCache` -- used non-existent `feature.indicator_id`, replaced with `feature.output_key`
- `LiveIndicatorCache` -- `input_source` routing always fed `candle.close` regardless of YAML `source:`
- `engine_factory.py` -- missing `hlc3`/`ohlc4` in `input_source_map`
- `KlineData.from_bybit()` -- symbol extraction, interval normalization, end_time field, UTC datetime
- `LiveRunner` multi-TF -- accept all play TFs, route via `on_candle_close(timeframe=)`, signal eval only on exec
- `RealtimeState.append_bar()` -- auto-init missing buffers instead of silent `return False`
- `_get_tf_role_for_timeframe()` -- raise ValueError instead of silent default to low_tf

---

## Quick Commands

```bash
# Demo readiness stress test
python scripts/test_demo_readiness.py                # Full (84 checks, ~5min)
python scripts/test_demo_readiness.py --skip-orders  # Read-only (69 checks, ~3min)

# Validation
python trade_cli.py validate quick                    # Core validation (~30s)
python trade_cli.py validate standard                 # Core + audits (~2min)

# Backtest
python trade_cli.py backtest run --play X --fix-gaps
python scripts/run_full_suite.py
python scripts/run_real_verification.py

# Live/Demo
python trade_cli.py play run --play X --mode demo
python trade_cli.py play run --play X --mode live --confirm

# Operations
python trade_cli.py play status
python trade_cli.py play watch
python trade_cli.py account balance
python trade_cli.py position list
python trade_cli.py panic --confirm
```

---

## Architecture

```text
src/engine/        # ONE unified PlayEngine for backtest/live
src/indicators/    # 44 indicators (all incremental O(1))
src/structures/    # 7 structure types
src/backtest/      # Infrastructure only (sim, runtime, features)
src/data/          # DuckDB historical data (1m mandatory for all runs)
src/tools/         # CLI/API surface
```

Signal flow (identical for backtest/live):
1. `process_bar(bar_index)` on exec timeframe
2. Update higher/medium timeframe indices
3. Warmup check (multi-timeframe sync + NaN validation)
4. `exchange.step()` (fill simulation via 1m subloop)
5. `_evaluate_rules()` -> Signal or None
6. `execute_signal(signal)`
