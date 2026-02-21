# Codebase Review Ongoing

Last updated: 2026-02-21 (pass 3)

This is a running senior-level audit log for active findings across the codebase.
Only issues verified in source are listed as confirmed.

## Confirmed Findings (In Progress)

### Critical

- `src/core/order_executor.py`, `src/core/exchange_websocket.py`, `src/data/realtime_state.py`
  - Realtime callback API mismatch: callers use `on_order_update`, `on_execution`, `on_position_update`, but `RealtimeState` only exposes `on_kline_update`.
  - Impact: live startup/runtime integration breakage and missing WS-driven safety/execution callbacks.
  - Evidence: `pyright` reports attribute-access errors for these methods.

- `src/data/realtime_bootstrap.py`, `src/data/realtime_state.py`
  - Stale detection is based on aggregate `update_counts` deltas across all topics; active public traffic can mask a dead private stream.
  - Impact: fail-open behavior where private WS degradation can be hidden while trading path appears healthy.

- `src/engine/play_engine.py`, `src/engine/adapters/live.py`
  - Exit (`FLAT`) path reports `OrderResult(success=True)` unconditionally after `submit_close()`, while `submit_close()` returns `None` and only logs failures.
  - Impact: strategy can assume position is closed when close failed.

- `src/engine/adapters/live.py`, `src/engine/runners/live_runner.py`, `src/engine/play_engine.py`
  - Anchored VWAP readiness deadlock: provider appends `NaN` placeholders for engine-managed anchored VWAP keys, warmup rejects `NaN`, but engine update only runs after readiness gate.
  - Impact: live/demo can stall in warmup indefinitely when anchored VWAP is used.

- `src/data/historical_data_store.py`
  - File-lock stale eviction removes `.lock` files older than 5 minutes without owner/process validation.
  - Impact: an active long-running writer can be preempted, allowing concurrent writers against DuckDB.

- `src/exchanges/bybit_client.py`, `src/core/exchange_orders_market.py`, `src/core/exchange_orders_limit.py`, `src/core/exchange_orders_stop.py`, `src/core/exchange_orders_manage.py`
  - `BybitClient.create_order()` is decorated with automatic retry, while most call paths do not provide deterministic `order_link_id`.
  - Impact: transient timeout/transport failures can duplicate non-idempotent order intents.

### High

- `src/engine/runners/live_runner.py`
  - Invalid state transition cleanup gap: `stop()` requires transition to `STOPPING`, but transition map disallows `ERROR -> STOPPING`.
  - Impact: runner in `ERROR` may skip cancel/disconnect cleanup.

- `src/backtest/engine_factory.py`
  - Warmup mapping bug: `warmup_bars_by_role["exec"]` incorrectly maps to `low_tf` warmup.
  - Impact: wrong warmup behavior when `exec` points to non-`low_tf`.

- `src/engine/runners/backtest_runner.py`, `src/backtest/sim/exchange.py`
  - Backtest runner does not pass `funding_events` into sim `process_bar(...)`.
  - Impact: funding can be omitted from simulation path despite model support.

- `src/core/safety.py`
  - `panic_close_all()` marks `orders_cancelled=True` without checking boolean return from `cancel_all_orders()`.
  - Impact: panic success can be reported while orders remain open.

- `src/core/safety.py`, `src/core/exchange_orders_manage.py`
  - Daily-loss seeding can fail open: `get_closed_pnl()` swallows errors and returns `[]`; `seed_from_exchange()` treats empty list as successful seed.
  - Impact: tracker may clear failure state and allow trading after upstream API failure.

- `src/core/application.py`
  - WebSocket start can no-op when no current position symbols (`_start_websocket()` early return), even if risk path requested WS startup.
  - Impact: risk telemetry path may not start as intended.

- `src/core/application.py`
  - `_shutting_down` is set in `stop()` and not reset.
  - Impact: subsequent lifecycle calls can skip expected shutdown behavior.

- `src/core/application.py`, `src/core/risk_manager.py`
  - Application builds `RiskManager` without passing `exchange_manager`.
  - Impact: exchange-backed risk helpers (tier leverage/funding fallbacks) are disabled in app-managed flow.

- `src/core/exchange_orders_manage.py`, `src/exchanges/bybit_client.py`
  - Batch cancel/amend parse shape mismatch: code reads `result["result"]["list"]` while client already returns extracted `result`.
  - Impact: batch success accounting can be wrong/empty.

- `src/backtest/rules/dsl_parser.py`, `src/backtest/rules/dsl_nodes/condition.py`
  - DSL shorthand `["x", "between", [lo, hi]]` resolves RHS list to `ListValue`, but `between` requires `RangeValue`.
  - Impact: documented shorthand fails at parse/validation.

- `src/data/realtime_bootstrap.py`
  - Private reconnection detection flips state to connected but does not rehydrate private snapshots (`wallet`/`positions`/`orders`) after outage.
  - Impact: missed private deltas can persist as stale risk/account/order state after reconnect.

- `src/data/realtime_bootstrap.py`
  - `_handle_stale_connection()` refreshes wallet and positions via REST but skips open orders refresh.
  - Impact: order cache can remain stale through reconnect/stale-recovery paths.

- `src/data/historical_sync.py`
  - Sync writes use `store.conn.execute(...)` directly in `_store_dataframe()` / `_update_metadata()` instead of `HistoricalDataStore._write_operation()` locking path.
  - Impact: write-path locking discipline is bypassed, increasing race/lock-conflict risk.

- `src/data/historical_sync.py`
  - `_fetch_from_api()` swallows API exceptions as `break`; `_sync_symbol_timeframe()` can still update metadata after partial fetch.
  - Impact: partial syncs can be recorded as fresh metadata without explicit failure signaling.

- `src/exchanges/bybit_account.py`, `src/core/exchange_positions.py`
  - `get_transferable_amount()` calls `get_spot_margin_trade_borrow_amount` while callers parse `transferableAmount`.
  - Impact: transferability checks can return wrong values (frequently zero), distorting balance/risk decisions.

- `src/exchanges/bybit_trading.py`
  - `get_open_orders()` reads a single page and ignores cursor pagination.
  - Impact: downstream cleanup/reconciliation may miss live open orders.

- `src/core/exchange_instruments.py`
  - `round_price()` / `calculate_qty()` use `Decimal.quantize()` with `tickSize` / `qtyStep`, which does not enforce true multiples for non-power-of-10 steps.
  - Impact: generated price/qty values can violate exchange increment rules and be rejected.

- `src/exchanges/bybit_client.py`
  - `_sync_server_time()` raises on critical ahead-of-server drift, then broad `except` swallows it and resets offset to 0.
  - Impact: client continues in known-bad clock state instead of failing closed.

- `src/backtest/runner.py`
  - Artifact identity sets `data_source_id = "duckdb_live"` for all non-synthetic runs.
  - Impact: run provenance/hash metadata can mislabel backtest/demo data environments.

- `src/backtest/runner.py`
  - `_resolve_window()` calls `get_historical_store()` without using `config.data_env`.
  - Impact: auto-window inference can be sourced from the wrong DB environment.

- `src/backtest/runtime/timeframe.py`
  - `ceil_to_tf_close()` uses `datetime.timestamp()` on naive datetimes while assuming UTC semantics.
  - Impact: boundary alignment can vary by host timezone/DST for naive inputs.

- `src/engine/runners/live_runner.py`, `src/core/safety.py`
  - Pre-trade safety path calls `SafetyChecks.run_all_checks()` without `additional_exposure`; max-exposure check is evaluated against current exposure only.
  - Impact: a new order can push exposure over configured limit even when pre-trade safety reports pass.

- `src/engine/runners/live_runner.py`
  - `_check_max_drawdown()` treats exceptions as non-fatal (`logger.warning(...)`) and continues trading.
  - Impact: drawdown guard can fail open when equity retrieval/check path errors.

### Medium

- `src/cli/subcommands/play.py`
  - `play run --mode live` runs pre-live validation using raw `args.play` before resolving path-vs-id.
  - Impact: valid YAML path inputs can fail pre-live gate incorrectly.

- `src/cli/subcommands/play.py`
  - Backtest path reload inconsistency: a path-loaded play is then executed by `play.id` through tool re-resolution.
  - Impact: wrong card/file can be run when IDs collide or file is outside expected directory.

- `src/tools/backtest_play_tools.py`, `src/cli/argparser.py`
  - `strict` flag is accepted and echoed in result data but not wired to execution behavior.
  - Impact: users get false confidence that strictness changed runtime checks.

- `src/backtest/play/play.py`
  - Invalid feature `source` silently falls back to `close`.
  - Impact: config typos produce silent strategy drift.

- `src/engine/adapters/live.py`
  - Hot path uses repeated `np.append` on OHLCV/indicator arrays.
  - Impact: growing latency and allocation churn in long live sessions.

- `src/engine/adapters/live.py`
  - Structure values are coerced to `float` in `get_structure_for_tf`/`get_structure_at_for_tf`.
  - Impact: enum/bool structure semantics can be lost for DSL comparisons.

- `src/engine/adapters/live.py`
  - `get_structure_at_for_tf()` falls back to current value when lookback index is out of range.
  - Impact: insufficient-history lookups can silently evaluate against current bar.

- `src/structures/detectors/zone.py`
  - If ATR is missing/NaN, zone width is forced to `0.0`.
  - Impact: zero-width zones can be created during warmup/missing-indicator states.

- `src/structures/detectors/derived_zone.py`
  - Zone hash creation uses stale `self._source_version` during regeneration, then updates version afterward.
  - Impact: instance identity/version semantics can lag by one source version.

- `src/structures/registry.py`, `src/structures/detectors/swing.py`, `src/structures/detectors/fibonacci.py`
  - Output-type registry misses valid detector outputs (`swing.high_version`, `swing.low_version`, fibonacci anchor metadata fields).
  - Impact: compile-time DSL type/operator validation can reject valid fields.

- `src/indicators/incremental/factory.py`, `src/indicators/incremental/adaptive.py`, `src/indicators/incremental/stateful.py`
  - Factory param allowlist is narrower than supported class params (`kama.fast/slow`, `fisher.signal`, `squeeze.mom_length/mom_smooth`).
  - Impact: valid config parameters are rejected as "unknown", forcing unintended defaults.

- `src/cli/subcommands/backtest.py`, `src/cli/argparser.py`
  - Indicators arg validator is attached to parser object (`parser._validate`) but invoked from `args`; parsed namespace does not carry parser attributes.
  - Impact: intended argument cross-validation path is effectively bypassed.

- `src/cli/menus/backtest_play_menu.py`, `src/tools/backtest_play_tools.py`
  - Menu preflight UI checks `data["status"] == "pass"` while tool report uses `overall_status`.
  - Impact: successful preflight can be shown as failed/unknown in menu flow.

- `src/data/market_data.py`, `src/data/realtime_models.py`, `src/data/realtime_state.py`
  - WS kline overlay uses raw `interval` lookup (`"15"`, `"60"`), while realtime state stores normalized intervals (`"15m"`, `"1h"`).
  - Impact: current-candle WS replacement can silently miss and fall back to stale REST candle.

- `src/exchanges/bybit_account.py`
  - `get_positions()` returns only one response page and does not iterate cursor.
  - Impact: multi-symbol accounts can be underreported in position-aware flows.

- `src/backtest/artifacts/artifact_standards.py`
  - `ResultsSummary` mixes percent units (`win_rate` stored as decimal, `long_win_rate`/`short_win_rate` stored as percentages).
  - Impact: downstream consumers can misinterpret metrics due to inconsistent field semantics.

- `src/backtest/artifacts/artifact_standards.py`
  - Collision/integrity helpers exist (`verify_run_folder`, `verify_hash_integrity`) but are not invoked in runner artifact creation path.
  - Impact: hash-collision/overwrite protection is defined but not enforced where artifacts are created.

- `src/backtest/artifacts/determinism.py`
  - `compare_runs()` defaults missing hash fields to empty strings and only checks equality, not presence/format.
  - Impact: malformed or legacy `result.json` pairs can be reported deterministic by matching empty hash values.

- `src/backtest/artifacts/determinism.py`, `src/tools/backtest_play_tools.py`
  - `verify_determinism_rerun()` re-runs using `play_id/start/end` only and does not propagate original run data environment/provenance inputs.
  - Impact: determinism rerun can compare against a run executed with different data source context.

## Next Pass Queue

- Continue through remaining strategy DSL edge cases, metrics/reporting consistency, and live safety fail-closed paths.
- Convert confirmed findings into a prioritized fix plan after full sweep.
