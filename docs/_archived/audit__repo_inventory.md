# TRADE Repository Inventory

**STATUS:** CANONICAL  
**PURPOSE:** Ground-truth file inventory for the TRADE trading bot  
**LAST UPDATED:** December 17, 2025

---

## File Counts by Extension (Excluding `reference/`)

| Extension | Count | Purpose |
|-----------|-------|---------|
| `.py` | 153 | Source code |
| `.md` | 63 | Documentation |
| `.yml` | 19 | IdeaCards, configs |
| `.json` | 531 | Backtest artifacts (metrics, trades, manifests) |
| `.duckdb` | 2 | Historical data stores (live, demo) |
| `.env` | 1 | API keys (gitignored) |
| `.txt` | 1 | Requirements |

---

## Top-Level Folder Overview

| Folder | Purpose | Domain |
|--------|---------|--------|
| `src/` | Production source code | All |
| `configs/` | IdeaCards (canonical location) | Strategy Factory |
| `docs/` | Documentation | Shared |
| `data/` | DuckDB storage files | Data |
| `backtests/` | Backtest output artifacts | Audit/Artifacts |
| `artifacts/` | Indicator metadata exports | Audit |
| `logs/` | Runtime logs | Ops |
| `tests/` | Test helpers (no pytest files) | Audit |
| `reference/` | Vendor docs (Bybit, pandas_ta, DuckDB, pybit) | External |

---

## Source Code Tree (`src/`)

```
src/
├── __init__.py
├── backtest/                    # DOMAIN: Backtesting/Simulator
│   ├── engine.py               # Backtest orchestrator
│   ├── runner.py               # CLI runner entry
│   ├── idea_card.py            # IdeaCard dataclass + loader
│   ├── idea_card_yaml_builder.py
│   ├── indicator_registry.py   # Indicator type registry
│   ├── indicator_vendor.py     # pandas_ta vendor wrapper
│   ├── indicators.py           # Indicator computation
│   ├── metrics.py              # Backtest metrics computation
│   ├── proof_metrics.py        # Proof metrics for validation
│   ├── proof_metrics_types.py
│   ├── risk_policy.py          # Simulator risk policy
│   ├── runtime_config.py       # Runtime configuration
│   ├── simulated_risk_manager.py
│   ├── snapshot_artifacts.py   # Snapshot export
│   ├── system_config.py        # Legacy system config
│   ├── toolkit_contract_audit.py
│   ├── types.py                # Core types
│   ├── window_presets.py       # Time window presets
│   ├── execution_validation.py
│   ├── artifact_parity_verifier.py
│   ├── audit_in_memory_parity.py
│   ├── audit_math_parity.py
│   ├── audit_snapshot_plumbing_parity.py
│   ├── artifacts/              # Artifact writers
│   │   ├── artifact_standards.py
│   │   ├── equity_writer.py
│   │   ├── eventlog_writer.py
│   │   ├── hashes.py
│   │   ├── manifest_writer.py
│   │   ├── parquet_writer.py
│   │   └── pipeline_signature.py
│   ├── features/               # Feature/indicator framework
│   │   ├── feature_frame_builder.py  # P0 BLOCKER: input-source bug
│   │   └── feature_spec.py
│   ├── gates/                  # Validation gates
│   │   ├── batch_verification.py
│   │   ├── idea_card_generator.py
│   │   ├── indicator_requirements_gate.py
│   │   └── production_first_import_gate.py
│   ├── runtime/                # Runtime snapshot/feed infrastructure
│   │   ├── cache.py
│   │   ├── data_health.py
│   │   ├── feed_store.py
│   │   ├── indicator_metadata.py
│   │   ├── preflight.py
│   │   ├── snapshot_builder.py
│   │   ├── snapshot_view.py
│   │   ├── timeframe.py
│   │   ├── types.py
│   │   └── windowing.py
│   └── sim/                    # Simulated Exchange
│       ├── exchange.py         # SimulatedExchange main
│       ├── ledger.py           # Account ledger
│       ├── bar_compat.py
│       ├── types.py
│       ├── adapters/           # Data adapters
│       │   ├── funding_adapter.py
│       │   └── ohlcv_adapter.py
│       ├── constraints/        # Mode constraints
│       │   └── constraints.py
│       ├── execution/          # Execution models
│       │   ├── execution_model.py
│       │   ├── impact_model.py
│       │   ├── liquidity_model.py
│       │   └── slippage_model.py
│       ├── funding/
│       │   └── funding_model.py
│       ├── liquidation/
│       │   └── liquidation_model.py
│       ├── metrics/
│       │   └── metrics.py
│       └── pricing/
│           ├── intrabar_path.py
│           ├── price_model.py
│           └── spread_model.py
├── cli/                        # DOMAIN: CLI
│   ├── art_stylesheet.py
│   ├── smoke_tests.py
│   ├── styles.py
│   ├── utils.py
│   └── menus/                  # Menu handlers
│       ├── account_menu.py
│       ├── backtest_menu.py
│       ├── data_menu.py
│       ├── market_data_menu.py
│       ├── orders_menu.py
│       └── positions_menu.py
├── config/                     # SHARED: Configuration
│   ├── config.py               # get_config()
│   └── constants.py
├── core/                       # DOMAIN: Live Trading
│   ├── application.py          # Application singleton
│   ├── exchange_instruments.py
│   ├── exchange_manager.py     # ExchangeManager
│   ├── exchange_orders_limit.py
│   ├── exchange_orders_manage.py
│   ├── exchange_orders_market.py
│   ├── exchange_orders_stop.py
│   ├── exchange_positions.py
│   ├── exchange_websocket.py
│   ├── order_executor.py
│   ├── position_manager.py
│   ├── risk_manager.py         # Live risk manager
│   └── safety.py               # Panic button
├── data/                       # SHARED: Data Layer
│   ├── backend_protocol.py
│   ├── historical_data_store.py  # DuckDB operations
│   ├── historical_maintenance.py
│   ├── historical_queries.py
│   ├── historical_sync.py
│   ├── market_data.py
│   ├── realtime_bootstrap.py
│   ├── realtime_models.py
│   ├── realtime_state.py
│   └── sessions.py
├── exchanges/                  # DOMAIN: Exchange Adapters
│   ├── bybit_account.py
│   ├── bybit_client.py
│   ├── bybit_market.py
│   ├── bybit_trading.py
│   └── bybit_websocket.py
├── risk/                       # SHARED: Risk
│   └── global_risk.py          # GlobalRiskView
├── strategies/                 # SHARED: Strategy Base
│   ├── base.py                 # BaseStrategy
│   ├── ema_rsi_atr.py          # Example strategy
│   ├── registry.py             # Strategy registry
│   ├── configs/                # Legacy configs (move to configs/)
│   │   ├── SOLUSDT_5m_ema_rsi_atr_pure.yml
│   │   └── SOLUSDT_5m_ema_rsi_atr_rules.yml
│   └── idea_cards/             # Legacy (examples only)
│       └── SOLUSDT_15m_ema_crossover.yml
├── tools/                      # SHARED: Tool Layer (Primary API)
│   ├── account_tools.py
│   ├── backtest_cli_wrapper.py
│   ├── backtest_tools.py
│   ├── data_tools.py
│   ├── diagnostics_tools.py
│   ├── market_data_tools.py
│   ├── order_tools.py
│   ├── position_tools.py
│   ├── shared.py
│   └── tool_registry.py
└── utils/                      # SHARED: Utilities
    ├── cli_display.py
    ├── epoch_tracking.py
    ├── helpers.py
    ├── log_context.py
    ├── logger.py
    ├── rate_limiter.py
    └── time_range.py
```

---

## Entry Points

| File | Purpose | Command |
|------|---------|---------|
| `trade_cli.py` | Main CLI entry | `python trade_cli.py` |
| `trade_cli.py --smoke full` | Full smoke test | Data + trading + diagnostics |
| `trade_cli.py --smoke data_extensive` | Extensive data test | Clean DB, gaps, sync |
| `trade_cli.py backtest run` | Run backtest | `--idea-card <ID> --start <date> --end <date>` |
| `trade_cli.py backtest metadata-smoke` | Metadata validation | Indicator metadata v1 |

---

## Configuration Files

| File | Purpose |
|------|---------|
| `env.example` | Environment variable template |
| `api_keys.env` | API keys (gitignored) |
| `requirements.txt` | Python dependencies |
| `CLAUDE.md` | AI guidance + project rules |
| `.cursor/rules/rules.mdc` | Cursor-specific rules |

---

## IdeaCards (Canonical Location: `configs/idea_cards/`)

| File | Symbol | TF | Purpose |
|------|--------|-----|---------|
| `_TEMPLATE.yml` | — | — | Template |
| `BTCUSDT_15m_mtf_tradeproof.yml` | BTCUSDT | 15m | MTF validation |
| `BTCUSDT_1h_system_validation_1year.yml` | BTCUSDT | 1h | 1-year validation |
| `BTCUSDT_5m_stress_test_indicator_dense.yml` | BTCUSDT | 5m | Indicator stress test |
| `ETHUSDT_15m_mtf_tradeproof.yml` | ETHUSDT | 15m | MTF validation |
| `SOLUSDT_15m_mtf_tradeproof.yml` | SOLUSDT | 15m | MTF validation |
| `verify/*.yml` | Various | Various | Indicator verification cards |

---

## Backtest Artifacts (`backtests/`)

Structure: `backtests/<idea_card_id>/<symbol>/run-NNN/`

Contents per run:
- `metrics.json` — Performance metrics
- `trades.json` — Trade list
- `equity.parquet` — Equity curve
- `events.parquet` — Event log
- `manifest.json` — Run manifest
- `snapshots/` — Optional snapshot dumps

---

## Data Files (`data/`)

| File | Purpose |
|------|---------|
| `market_data_live.duckdb` | Live API data |
| `market_data_demo.duckdb` | Demo API data |

---

## Documentation (`docs/`)

| Folder | Purpose |
|--------|---------|
| `contracts/` | Canonical contracts (engine, exchange, data, audit) |
| `architecture/` | Architecture diagrams, runtime flow |
| `domains/` | Domain ownership maps |
| `modules/` | Per-module notes |
| `data/` | Data module documentation |
| `strategy_factory/` | Strategy factory documentation |
| `runbooks/` | Operational runbooks |
| `audits/` | Audit module (tests, bugs, validations) |
| `reference/` | Internal pointers to vendor docs |
| `index/` | Inventories, checklists |
| `_archived/` | Historical docs |

---

## Tests (`tests/`)

| File | Purpose |
|------|---------|
| `helpers/test_indicator_metadata.py` | Indicator metadata helpers |
| `helpers/test_metadata_integration.py` | Metadata integration helpers |

**Note:** No pytest test files exist. All validation runs through CLI commands.

---

## Reference (`reference/`)

Vendor documentation (not audited, used for API reference):

| Folder | Purpose |
|--------|---------|
| `exchanges/bybit/` | Bybit V5 API docs |
| `exchanges/pybit/` | pybit SDK reference |
| `pandas_ta/` | pandas_ta indicator reference |
| `pandas_ta_repo/` | Full pandas_ta source |
| `duckdb/` | DuckDB documentation |
| `mongodb/` | MongoDB reference (not actively used) |

---

