# TRADE Domain Map

**STATUS:** CANONICAL  
**PURPOSE:** Domain ownership, boundaries, dependencies, and maturity assessment  
**LAST UPDATED:** December 17, 2025

---

## Domain Overview

| Domain | Primary Path | Maturity | Status |
|--------|--------------|----------|--------|
| Backtesting | `src/backtest/` | 3 (Production) | Active development (P5 blocked) |
| CLI | `src/cli/` + `trade_cli.py` | 3 (Production) | Stable |
| Trade Execution | `src/core/` + `src/exchanges/` | 2 (Functional) | Maintenance mode |
| Data | `src/data/` | 3 (Production) | Stable |
| Strategy Factory | `configs/idea_cards/` + `src/backtest/idea_card*.py` | 2 (Functional) | Partial |
| Audit | `src/backtest/audit_*` + `src/backtest/gates/` | 2 (Functional) | Needs consolidation |
| Agent Module | (future) | 0 (Planned) | Not started |

**Maturity Scale:** 0=Planned, 1=Stub, 2=Functional, 3=Production

---

## Domain 1: Backtesting

### Responsibilities
- Load IdeaCard configuration
- Fetch historical data from DuckDB
- Compute indicators (vectorized, outside hot loop)
- Build FeedStores for O(1) array access
- Run bar-by-bar simulation with RuntimeSnapshotView
- Execute trades via SimulatedExchange
- Generate BacktestResult with metrics
- Write artifacts (parquet, json)

### Non-Responsibilities
- Live trading execution
- Real-time data streaming
- User authentication
- Strategy discovery/promotion (Strategy Factory handles)

### Key Files
| File | Purpose |
|------|---------|
| `engine.py` | Main orchestrator |
| `runner.py` | CLI runner entry |
| `idea_card.py` | IdeaCard dataclass + loader |
| `sim/exchange.py` | SimulatedExchange |
| `sim/ledger.py` | Account ledger |
| `runtime/snapshot_view.py` | RuntimeSnapshotView (hot loop) |
| `runtime/feed_store.py` | FeedStore (numpy arrays) |
| `features/feature_frame_builder.py` | Indicator computation |

### Internal Dependencies
- `src/data/` (HistoricalDataStore)
- `src/config/` (get_config)
- `src/utils/` (logging, helpers)

### External Dependencies
- `pandas`, `numpy`, `duckdb`, `pandas_ta`, `pyarrow`

### Known Gaps
- **P0 BLOCKER:** Input-source routing bug in `feature_frame_builder.py:633,674`
- Phase 5 (Market Structure) blocked until P0 resolved
- Duplicate `ExchangeState` class in `sim/types.py` and `runtime/types.py`

### Invariants
1. **Determinism:** Same config + same data → identical output
2. **No look-ahead:** Closed candles only, HTF/MTF forward-fill
3. **O(1) hot loop:** No pandas in hot loop
4. **USDT-only:** Symbol must end in "USDT"
5. **Isolated margin only:** Cross margin rejected

---

## Domain 2: CLI

### Responsibilities
- Menu-driven user interface
- Route user input to tool functions
- Display results with Rich formatting
- Run smoke tests
- Parse command-line arguments

### Non-Responsibilities
- Business logic (all in tools layer)
- Direct API calls (goes through tools)
- Direct database access

### Key Files
| File | Purpose |
|------|---------|
| `trade_cli.py` | Main entry point |
| `cli/menus/*.py` | Menu handlers |
| `cli/smoke_tests.py` | Smoke test runner |
| `cli/utils.py` | CLI utilities |
| `cli/styles.py` | Styling/formatting |

### Internal Dependencies
- `src/tools/*` (all operations)
- `src/config/` (get_config)
- `src/core/application.py` (Application singleton)

### External Dependencies
- `rich`, `typer`, `argparse`

### Known Gaps
- None significant

### Invariants
1. **Pure shell:** CLI contains NO business logic
2. **Tool-first:** All operations go through `src/tools/*`

---

## Domain 3: Trade Execution (Live)

### Responsibilities
- Execute live trades on Bybit
- Manage positions and orders
- Apply risk checks
- Handle WebSocket for GlobalRiskView
- Safety/panic button

### Non-Responsibilities
- Historical data (uses Data domain)
- Backtesting (uses Backtesting domain)
- Strategy logic (strategies emit Signals)

### Key Files
| File | Purpose |
|------|---------|
| `core/exchange_manager.py` | ExchangeManager (main interface) |
| `core/risk_manager.py` | RiskManager (live risk checks) |
| `core/order_executor.py` | Order execution |
| `core/position_manager.py` | Position tracking |
| `core/safety.py` | Panic button |
| `exchanges/bybit_client.py` | Bybit API wrapper |
| `exchanges/bybit_*.py` | Bybit modules |

### Internal Dependencies
- `src/data/` (market data)
- `src/config/` (API keys, settings)
- `src/utils/rate_limiter.py` (rate limiting)

### External Dependencies
- `pybit` (Bybit SDK)

### Known Gaps
- DEMO vs LIVE mode validation could be stricter
- WebSocket used only for GlobalRiskView monitoring

### Invariants
1. **Risk-first:** All orders go through RiskManager
2. **Mode validation:** TRADING_MODE/BYBIT_USE_DEMO combinations validated
3. **Rate limiting:** All API calls respect rate limits
4. **Safety accessible:** Panic button always reachable

---

## Domain 4: Data

### Responsibilities
- DuckDB storage operations
- OHLCV sync from Bybit API
- Funding rate sync
- Open interest sync
- Gap detection and healing
- Data quality validation

### Non-Responsibilities
- Indicator computation (Backtesting domain)
- Live price streaming (Trade Execution domain)
- Artifact storage (Backtesting domain)

### Key Files
| File | Purpose |
|------|---------|
| `data/historical_data_store.py` | Main DuckDB interface |
| `data/historical_sync.py` | Sync from Bybit |
| `data/historical_queries.py` | Query helpers |
| `data/historical_maintenance.py` | Heal, cleanup, vacuum |
| `data/sessions.py` | DuckDB session management |

### Internal Dependencies
- `src/config/` (API keys, DB paths)
- `src/exchanges/bybit_market.py` (API calls)
- `src/utils/` (logging, rate limiting)

### External Dependencies
- `duckdb`, `pybit`

### Known Gaps
- None significant

### Storage
| File | Purpose |
|------|---------|
| `data/market_data_live.duckdb` | Live API data |
| `data/market_data_demo.duckdb` | Demo API data |

### Tables
| Table | PK | Purpose |
|-------|-----|---------|
| `ohlcv` | (symbol, timeframe, timestamp) | Candlestick data |
| `funding_rates` | (symbol, timestamp) | Funding rates |
| `open_interest` | (symbol, timestamp) | OI data |

### Invariants
1. **LIVE API for data:** All historical data from `api.bybit.com`
2. **Timestamp = ts_open:** Stored timestamp is bar open time
3. **No duplicates:** PK enforced
4. **Valid OHLCV:** high ≥ low, volume ≥ 0

---

## Domain 5: Strategy Factory

### Responsibilities
- IdeaCard definition and validation
- Strategy configuration schema
- Indicator specification via FeatureSpec
- System hash generation
- Promotion loop tracking (future)

### Non-Responsibilities
- Indicator computation (Backtesting domain)
- Trade execution (Trade Execution domain)
- Backtest orchestration (Backtesting domain)

### Key Files
| File | Purpose |
|------|---------|
| `configs/idea_cards/*.yml` | Canonical IdeaCards |
| `backtest/idea_card.py` | IdeaCard dataclass |
| `backtest/idea_card_yaml_builder.py` | YAML normalization |
| `backtest/features/feature_spec.py` | FeatureSpec |
| `backtest/indicator_registry.py` | Indicator type registry |
| `backtest/artifacts/hashes.py` | System hash |

### Internal Dependencies
- `src/backtest/` (IdeaCard consumed by engine)

### External Dependencies
- `pyyaml`

### Known Gaps
- **IdeaCards scattered:** Files in `src/strategies/idea_cards/` and `src/strategies/configs/` (should be in `configs/`)
- Promotion loop not implemented
- System hash not yet used for tracking

### Invariants
1. **Canonical location:** `configs/idea_cards/`
2. **Explicit indicators:** All indicators declared in FeatureSpec
3. **Normalizer validates:** IdeaCard normalizer fixes issues before engine

### Future: Promotion Loop
```
Concept → IdeaCard → Backtest (hygiene/test) → Sim validation → Demo trading → Live trading
```

---

## Domain 6: Audit

### Responsibilities
- Pre-merge validation gates
- Math parity verification (vs pandas_ta)
- Snapshot plumbing verification
- Contract audits (indicator schema)
- Determinism verification
- Data quality checks

### Non-Responsibilities
- Test framework (no pytest files)
- Production monitoring
- Alerting

### Key Files
| File | Purpose |
|------|---------|
| `backtest/audit_math_parity.py` | Math parity vs pandas_ta |
| `backtest/audit_snapshot_plumbing_parity.py` | Snapshot access verification |
| `backtest/audit_in_memory_parity.py` | In-memory parity |
| `backtest/artifact_parity_verifier.py` | Artifact verification |
| `backtest/toolkit_contract_audit.py` | Indicator contract audit |
| `backtest/gates/*.py` | Validation gates |

### Internal Dependencies
- `src/backtest/` (runs engine for verification)
- `src/data/` (data checks)

### External Dependencies
- `pandas_ta` (reference implementation)

### Known Gaps
- **Scattered location:** Audit code mixed in `src/backtest/` root
- No consolidated audit runner
- P0 blocker: input-source parity failing

### Gates (Pre-Merge)
| Gate | Command | Pass Criteria |
|------|---------|---------------|
| Toolkit Contract | `backtest audit-toolkit` | 42/42 indicators pass |
| Math Parity | `backtest phase2-audit` | 0 failures, max_diff < 1e-8 |
| Snapshot Plumbing | `backtest audit-snapshot-plumbing` | 0 failures |

### Invariants
1. **CLI-only:** No pytest files exist
2. **Regression = STOP:** Fix before proceeding
3. **Gate before merge:** All gates must pass

---

## Domain 7: Agent Module (Future)

### Planned Responsibilities
- AI agent integration
- Automated strategy discovery
- Research workflow automation
- Signal interpretation

### Integration Points
- Tool layer (`src/tools/*`) as API surface
- IdeaCard generation
- Backtest result interpretation
- Promotion loop automation

### Status
Not started. Designed as downstream consumer of existing domains.

---

## Cross-Domain Dependencies

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   CLI        │────▶│   Tools      │────▶│  Core/Live   │
└──────────────┘     └──────────────┘     └──────────────┘
                            │
                            ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Strategy Fac │────▶│  Backtest    │────▶│    Data      │
└──────────────┘     └──────────────┘     └──────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │    Audit     │
                     └──────────────┘
```

---

## Reorganization Recommendations

### 1. Consolidate IdeaCards (RECOMMENDED)
**Current state:** IdeaCards in 3 locations
- `configs/idea_cards/` — Canonical (correct)
- `src/strategies/idea_cards/` — Examples (should be templates)
- `src/strategies/configs/` — Legacy (should move to configs/)

**Proposed:**
- Move `src/strategies/configs/*.yml` → `configs/legacy/` or delete
- Rename `src/strategies/idea_cards/` → Mark as examples only

### 2. Consolidate Audit Code (RECOMMENDED)
**Current state:** Audit code scattered in `src/backtest/` root

**Proposed:** Create `src/backtest/audits/` subdirectory:
```
src/backtest/audits/
├── __init__.py
├── math_parity.py         (was audit_math_parity.py)
├── snapshot_plumbing.py   (was audit_snapshot_plumbing_parity.py)
├── in_memory_parity.py    (was audit_in_memory_parity.py)
├── artifact_verifier.py   (was artifact_parity_verifier.py)
└── contract_audit.py      (was toolkit_contract_audit.py)
```

### 3. Resolve Duplicate ExchangeState (RECOMMENDED)
**Current state:** `ExchangeState` class in both:
- `src/backtest/sim/types.py`
- `src/backtest/runtime/types.py`

**Proposed:** Audit usage, keep one, delete or alias other.

### 4. Rename tests/ to test_helpers/ (LOW PRIORITY)
**Current state:** `tests/` folder exists but contains no pytest files (by design)

**Proposed:** Rename to `test_helpers/` or `helpers/` to avoid confusion.

---

## Next Steps

1. Complete Audit domain consolidation
2. Resolve P0 blocker (input-source routing)
3. Implement promotion loop in Strategy Factory
4. Define Agent Module integration points

---

