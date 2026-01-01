# TRADE Repository Coverage Checklist

**STATUS:** CANONICAL  
**PURPOSE:** Track file-by-file audit coverage  
**LAST UPDATED:** December 17, 2025

---

## Coverage Status

| Status | Count | Meaning |
|--------|-------|---------|
| ✅ Reviewed | 45 | Fully audited, documented |
| 📋 Summarized | 60 | Key purpose understood |
| ⏭️ Deferred | 40 | Reference/vendor, not core |
| ❓ Pending | 5 | Needs further investigation |

---

## Core Source Files (`src/`)

### `src/backtest/` — Backtesting Domain (✅ Reviewed)

| File | Status | Purpose |
|------|--------|---------|
| `engine.py` | ✅ | Main backtest orchestrator |
| `runner.py` | ✅ | CLI runner entry point |
| `idea_card.py` | ✅ | IdeaCard dataclass + loader |
| `idea_card_yaml_builder.py` | 📋 | YAML normalization |
| `indicator_registry.py` | 📋 | Indicator type registry |
| `indicator_vendor.py` | 📋 | pandas_ta vendor wrapper |
| `indicators.py` | 📋 | Indicator computation |
| `metrics.py` | 📋 | Backtest metrics |
| `proof_metrics.py` | 📋 | Proof metrics for validation |
| `proof_metrics_types.py` | 📋 | Type definitions |
| `risk_policy.py` | 📋 | Simulator risk policy |
| `runtime_config.py` | 📋 | Runtime configuration |
| `simulated_risk_manager.py` | 📋 | Simulator risk manager |
| `snapshot_artifacts.py` | 📋 | Snapshot export |
| `system_config.py` | 📋 | System config (legacy path) |
| `toolkit_contract_audit.py` | 📋 | Indicator contract audit |
| `types.py` | ✅ | Core types (Trade, Metrics, etc.) |
| `window_presets.py` | 📋 | Time window presets |
| `execution_validation.py` | 📋 | Execution validation |
| `artifact_parity_verifier.py` | 📋 | Artifact verification |
| `audit_in_memory_parity.py` | 📋 | In-memory parity checks |
| `audit_math_parity.py` | 📋 | Math parity vs pandas_ta |
| `audit_snapshot_plumbing_parity.py` | 📋 | Snapshot access verification |

### `src/backtest/artifacts/` — Artifact Writers (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `artifact_standards.py` | 📋 | Standards constants |
| `equity_writer.py` | 📋 | Equity curve writer |
| `eventlog_writer.py` | 📋 | Event log writer |
| `hashes.py` | 📋 | System hash generation |
| `manifest_writer.py` | 📋 | Run manifest writer |
| `parquet_writer.py` | 📋 | Parquet output |
| `pipeline_signature.py` | 📋 | Pipeline provenance |

### `src/backtest/features/` — Feature Framework (✅ Reviewed)

| File | Status | Purpose | Notes |
|------|--------|---------|-------|
| `feature_frame_builder.py` | ✅ | Indicator computation | **P0 BUG: lines 633, 674** |
| `feature_spec.py` | ✅ | FeatureSpec dataclass | |

### `src/backtest/gates/` — Validation Gates (✅ Reviewed)

| File | Status | Purpose |
|------|--------|---------|
| `batch_verification.py` | 📋 | Batch IdeaCard verification |
| `idea_card_generator.py` | 📋 | Generate test IdeaCards |
| `indicator_requirements_gate.py` | 📋 | Check indicator requirements |
| `production_first_import_gate.py` | 📋 | Production import gate |

### `src/backtest/runtime/` — Runtime Infrastructure (✅ Reviewed)

| File | Status | Purpose |
|------|--------|---------|
| `cache.py` | 📋 | Timeframe cache |
| `data_health.py` | 📋 | Data health checks |
| `feed_store.py` | ✅ | FeedStore (numpy arrays) |
| `indicator_metadata.py` | 📋 | Indicator metadata tracking |
| `preflight.py` | 📋 | Preflight validation |
| `snapshot_builder.py` | 📋 | Snapshot building (legacy) |
| `snapshot_view.py` | ✅ | RuntimeSnapshotView |
| `timeframe.py` | 📋 | Timeframe utilities |
| `types.py` | ✅ | Runtime types |
| `windowing.py` | 📋 | Window calculations |

### `src/backtest/sim/` — Simulated Exchange (✅ Reviewed)

| File | Status | Purpose |
|------|--------|---------|
| `exchange.py` | ✅ | SimulatedExchange orchestrator |
| `ledger.py` | ✅ | Account ledger |
| `bar_compat.py` | 📋 | Bar compatibility |
| `types.py` | ✅ | Sim types |

### `src/backtest/sim/adapters/` (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `funding_adapter.py` | 📋 | Funding rate adapter |
| `ohlcv_adapter.py` | 📋 | OHLCV data adapter |

### `src/backtest/sim/constraints/` (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `constraints.py` | 📋 | Mode constraints (USDT, isolated) |

### `src/backtest/sim/execution/` (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `execution_model.py` | 📋 | Order execution model |
| `impact_model.py` | 📋 | Market impact model |
| `liquidity_model.py` | 📋 | Liquidity model |
| `slippage_model.py` | 📋 | Slippage model |

### `src/backtest/sim/funding/` (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `funding_model.py` | 📋 | Funding rate application |

### `src/backtest/sim/liquidation/` (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `liquidation_model.py` | 📋 | Liquidation logic |

### `src/backtest/sim/metrics/` (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `metrics.py` | 📋 | Exchange metrics tracking |

### `src/backtest/sim/pricing/` (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `intrabar_path.py` | 📋 | Intrabar price path |
| `price_model.py` | 📋 | Price model |
| `spread_model.py` | 📋 | Spread modeling |

---

### `src/cli/` — CLI Domain (✅ Reviewed)

| File | Status | Purpose |
|------|--------|---------|
| `art_stylesheet.py` | 📋 | ASCII art styling |
| `smoke_tests.py` | ✅ | Smoke test runner |
| `styles.py` | 📋 | CLI styles |
| `utils.py` | 📋 | CLI utilities |

### `src/cli/menus/` (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `account_menu.py` | 📋 | Account menu |
| `backtest_menu.py` | 📋 | Backtest menu |
| `data_menu.py` | 📋 | Data menu |
| `market_data_menu.py` | 📋 | Market data menu |
| `orders_menu.py` | 📋 | Orders menu |
| `positions_menu.py` | 📋 | Positions menu |

---

### `src/config/` — Configuration (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `config.py` | 📋 | get_config() singleton |
| `constants.py` | 📋 | Global constants |

---

### `src/core/` — Trade Execution Domain (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `application.py` | 📋 | Application singleton |
| `exchange_instruments.py` | 📋 | Instrument info |
| `exchange_manager.py` | 📋 | ExchangeManager |
| `exchange_orders_limit.py` | 📋 | Limit orders |
| `exchange_orders_manage.py` | 📋 | Order management |
| `exchange_orders_market.py` | 📋 | Market orders |
| `exchange_orders_stop.py` | 📋 | Stop orders |
| `exchange_positions.py` | 📋 | Position queries |
| `exchange_websocket.py` | 📋 | WebSocket handler |
| `order_executor.py` | 📋 | Order execution |
| `position_manager.py` | 📋 | Position tracking |
| `risk_manager.py` | 📋 | Live risk manager |
| `safety.py` | 📋 | Panic button |

---

### `src/data/` — Data Domain (✅ Reviewed)

| File | Status | Purpose |
|------|--------|---------|
| `backend_protocol.py` | 📋 | Backend protocol |
| `historical_data_store.py` | ✅ | DuckDB main interface |
| `historical_maintenance.py` | 📋 | Heal, cleanup, vacuum |
| `historical_queries.py` | 📋 | Query helpers |
| `historical_sync.py` | 📋 | Sync from Bybit |
| `market_data.py` | 📋 | Market data (live) |
| `realtime_bootstrap.py` | 📋 | Realtime bootstrap |
| `realtime_models.py` | 📋 | Realtime models |
| `realtime_state.py` | 📋 | Realtime state |
| `sessions.py` | 📋 | DuckDB sessions |

---

### `src/exchanges/` — Exchange Adapters (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `bybit_account.py` | 📋 | Account operations |
| `bybit_client.py` | 📋 | Main client |
| `bybit_market.py` | 📋 | Market data |
| `bybit_trading.py` | 📋 | Trading operations |
| `bybit_websocket.py` | 📋 | WebSocket |

---

### `src/risk/` — Risk (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `global_risk.py` | 📋 | GlobalRiskView |

---

### `src/strategies/` — Strategies (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `base.py` | 📋 | BaseStrategy |
| `ema_rsi_atr.py` | 📋 | Example strategy |
| `registry.py` | 📋 | Strategy registry |

---

### `src/tools/` — Tool Layer (✅ Reviewed)

| File | Status | Purpose |
|------|--------|---------|
| `account_tools.py` | 📋 | Account tools |
| `backtest_cli_wrapper.py` | 📋 | Backtest CLI wrapper |
| `backtest_tools.py` | ✅ | Backtest tools |
| `data_tools.py` | 📋 | Data tools |
| `diagnostics_tools.py` | 📋 | Diagnostic tools |
| `market_data_tools.py` | 📋 | Market data tools |
| `order_tools.py` | 📋 | Order tools |
| `position_tools.py` | 📋 | Position tools |
| `shared.py` | 📋 | Shared utilities |
| `tool_registry.py` | ✅ | ToolRegistry |

---

### `src/utils/` — Utilities (📋 Summarized)

| File | Status | Purpose |
|------|--------|---------|
| `cli_display.py` | 📋 | CLI display helpers |
| `epoch_tracking.py` | 📋 | Strategy epoch tracking |
| `helpers.py` | 📋 | General helpers |
| `log_context.py` | 📋 | Logging context |
| `logger.py` | 📋 | Logger setup |
| `rate_limiter.py` | 📋 | Rate limiting |
| `time_range.py` | 📋 | TimeRange abstraction |

---

## Configuration Files

| File | Status | Purpose |
|------|--------|---------|
| `trade_cli.py` | ✅ | Main CLI entry |
| `CLAUDE.md` | ✅ | AI guidance |
| `requirements.txt` | 📋 | Dependencies |
| `env.example` | 📋 | Env template |

---

## IdeaCards (`configs/idea_cards/`)

| File | Status | Purpose |
|------|--------|---------|
| `_TEMPLATE.yml` | ✅ | Template |
| `BTCUSDT_15m_mtf_tradeproof.yml` | 📋 | MTF validation |
| `BTCUSDT_1h_system_validation_1year.yml` | 📋 | 1-year validation |
| `BTCUSDT_5m_stress_test_indicator_dense.yml` | 📋 | Stress test |
| `ETHUSDT_15m_mtf_tradeproof.yml` | 📋 | MTF validation |
| `SOLUSDT_15m_mtf_tradeproof.yml` | 📋 | MTF validation |
| `verify/*.yml` (10 files) | 📋 | Indicator verification |

---

## Deferred (Reference Folders)

| Folder | Status | Reason |
|--------|--------|--------|
| `reference/exchanges/bybit/` | ⏭️ | Vendor docs |
| `reference/exchanges/pybit/` | ⏭️ | Vendor SDK |
| `reference/pandas_ta/` | ⏭️ | Indicator reference |
| `reference/pandas_ta_repo/` | ⏭️ | Full pandas_ta |
| `reference/duckdb/` | ⏭️ | DuckDB docs |
| `reference/mongodb/` | ⏭️ | Not actively used |

---

## Known Issues Found

| File | Issue | Severity |
|------|-------|----------|
| `src/backtest/features/feature_frame_builder.py:633,674` | Input-source routing bug | P0 BLOCKER |
| `src/backtest/sim/types.py` + `src/backtest/runtime/types.py` | Duplicate ExchangeState | P2 |
| `src/strategies/configs/` | Misplaced configs | P3 |
| `src/strategies/idea_cards/` | Misplaced examples | P3 |

---

