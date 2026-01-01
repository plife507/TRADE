# TRADE Project — Overview

**Last Updated:** December 17, 2025 (governance cleanup)  
**Purpose:** Comprehensive project overview for context in other chat sessions  
**Status:** Backtest engine production-ready; Phases 1-4 complete; P0 blocker identified and documented

---

## Executive Summary

TRADE is a **production-ready, modular trading bot** for Bybit Unified Trading Account (UTA) with a complete backtesting engine. The system provides:

- **Complete Bybit UTA Support**: All order types, position management, TP/SL, trailing stops
- **Bybit-Aligned Backtest Engine**: Deterministic simulation with isolated margin model
- **Tool Registry**: Dynamic tool discovery for CLI, orchestrators, and AI agents
- **Historical Data Store**: DuckDB-based OHLCV, funding rates, open interest
- **Risk Controls**: Leverage limits, position sizing, circuit breakers, panic button

**Key Philosophy:** Safety first, modular always, tools as the API surface.

---

## Current Status

### ✅ Backtest Engine Refactor Complete (Phases 0–5)

The backtesting engine is fully operational and refactor-complete:

- **Deterministic Results**: Same config + same data → same metrics/trades
- **No Look-Ahead**: Indicators computed correctly, signals use only available info
- **Bybit-Aligned Accounting**: Isolated margin, IMR/MMR, fees, stop conditions
- **Config-Only Switching**: Hygiene/test windows via YAML, no code changes
- **Canonical Bar Timing**: `Bar.ts_open` (fills) + `Bar.ts_close` (step/eval)
- **Canonical Strategy Input**: `RuntimeSnapshot` is the only supported snapshot type
- **MTF/HTF Caching**: Data-driven close detection + readiness gate
- **Mark Price Unification**: Single mark per step (exchange → snapshot)
- **Preflight Data Gate**: Health check + bounded heal loop (tools-only)
- **Artifact Output**: `result.json`, `trades.csv`, `equity.csv`, `account_curve.csv`, `run_manifest.json`, `events.jsonl`

### ✅ Tools & CLI Integration (Backtests)

Backtesting is exposed via tools + CLI:

- ✅ `backtest_run_tool` - Run backtest by IdeaCard ID + time window
- ✅ `backtest_list_idea_cards_tool` - List available IdeaCard configs
- ✅ CLI Backtest menu - Interactive IdeaCard/window selection
- ✅ Epoch tracking integration - Lineage artifacts under `backtests/`
- ✅ IdeaCard normalization - YAML validation and auto-fix
- ✅ Indicator registry - Registry-defined supported indicator surface (backed by pandas_ta)
- ✅ Indicator Metadata System v1 - Provenance tracking and reproducibility
- ✅ `backtest metadata-smoke` - CLI validation of metadata system
- ✅ Analytics - Comprehensive metrics (Sharpe, Sortino, Calmar, trade stats)

**Hot loop policy:** pandas allowed in prep only; loop uses NumPy arrays; no per-bar schema discovery

**Audit gates:** contract audit + math parity audit (values + NaN masks) gate refactors

**Array-Backed Hot Loop (Phases 1-4):**
- ✅ Phase 1: Array-backed snapshot preparation (performance + plumbing)
- ✅ Phase 2: Audit lock-in (contract + math parity gates)
- ✅ Phase 3: Parquet migration (CSV → Parquet, primary format)
- ✅ Phase 4: Snapshot plumbing audit (39,968 comparisons, 0 failures)

**P0 BLOCKER (Before Phase 5):**
- 🔴 Input-source routing bug in FeatureFrameBuilder (lines 633, 674)
  - **Issue:** Non-"close" input sources incorrectly mapped (volume, open, high, low, hlc3, ohlc4 broken)
  - **Fix:** Change conditional logic to always use retrieved `input_series`
  - **Validation:** Input-source parity audit must pass before Market Structure work begins

**Planned (Normalizer):**
- TF compatibility validation
- semantic misuse lint (+ strict mode)

### 📋 Later Work (Not Current Focus)

- Per-bar datasets for ML/forecasting (offline only)
- Strategy factory orchestration beyond "run this system"
- Demo/live promotions pipeline and automation

**See:** `docs/project/NEXT_PHASE_ARCHITECTURE_REFACTOR_PLAN.md` for detailed next-phase roadmap (array-backed snapshots, Parquet artifacts, market structure features, multi-IdeaCard composition)

---

## Architecture

### Layer Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI / Agents                          │
│                    (trade_cli.py, HTTP API)                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Tools Layer                             │
│              src/tools/*.py (35+ tools)                      │
│         Returns ToolResult, Tool Registry for discovery      │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Core Layer    │  │  Backtest Layer │  │   Data Layer    │
│   src/core/     │  │  src/backtest/  │  │   src/data/     │
│ ExchangeManager │  │ BacktestEngine  │  │ HistoricalStore │
│  RiskManager    │  │SimulatedExchange│  │   MarketData    │
│ OrderExecutor   │  │     Metrics     │  │  RealtimeState  │
└─────────────────┘  └─────────────────┘  └─────────────────┘
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    Exchange Layer                            │
│              src/exchanges/bybit_client.py                   │
│                 (pybit SDK wrapper)                          │
└─────────────────────────────────────────────────────────────┘
```

### Project Structure

```
TRADE/
├── trade_cli.py                    # Main CLI entry point
├── requirements.txt                # Python dependencies
├── env.example                     # Environment variables template
│
├── src/
│   ├── config/                     # Central configuration
│   ├── exchanges/                  # Bybit API wrappers
│   ├── core/                       # Live trading logic
│   ├── backtest/                   # Backtest engine
│   ├── data/                       # Market data & DuckDB storage
│   ├── strategies/                 # Base classes + configs
│   ├── tools/                      # Public API surface (PRIMARY)
│   ├── utils/                      # Utilities
│   └── cli/                        # CLI menus
│
├── research/strategies/            # (Planned) Research strategies
│   ├── pending/                    # In testing
│   ├── final/                      # Validated
│   └── archived/                   # Retired
│
├── data/
│   ├── market_data.duckdb          # Historical data
│   └── backtests/                  # Backtest artifacts
│
├── docs/
│   ├── architecture/               # Technical docs
│   ├── guides/                     # How-to guides
│   ├── project/                    # Project docs
│   └── brainstorm/                 # Planning docs
│
└── tests/                          # Test suite
```

---

## Key Concepts

### 1. Four-Leg API Architecture

| Leg | Purpose | Endpoint | Key Variable |
|-----|---------|----------|--------------|
| Trade LIVE | Real money trading | api.bybit.com | `BYBIT_LIVE_API_KEY` |
| Trade DEMO | Fake money trading | api-demo.bybit.com | `BYBIT_DEMO_API_KEY` |
| Data LIVE | Backtest/research data | api.bybit.com | `BYBIT_LIVE_DATA_API_KEY` |
| Data DEMO | Demo validation | api-demo.bybit.com | `BYBIT_DEMO_DATA_API_KEY` |

**Rule:** Historical data always uses LIVE API for accuracy.

### 2. Tools Layer (Primary API)

All operations go through `src/tools/*`. Tools return `ToolResult` objects.

```python
from src.tools.tool_registry import ToolRegistry

registry = ToolRegistry()
result = registry.execute("market_buy", symbol="BTCUSDT", usd_amount=100)
```

### 3. Backtest Engine

**Modular, Bybit-aligned accounting model:**

The backtest engine uses a **modular exchange architecture** with specialized components:

```python
# Exchange state (all explicit, always available)
exchange.cash_balance_usd      # Realized cash
exchange.unrealized_pnl_usd    # Mark-to-market PnL
exchange.equity_usd            # = cash + unrealized_pnl
exchange.used_margin_usd       # Position IM
exchange.free_margin_usd       # = equity - used_margin
exchange.available_balance_usd # = max(0, free_margin)
```

**Modular Architecture:**
- `sim/exchange.py` - Thin orchestrator (~200 LOC)
- `sim/ledger.py` - USDT accounting with invariants
- `sim/pricing/` - Mark/last/mid price derivation
- `sim/execution/` - Order execution with slippage/impact
- `sim/funding/` - Funding rate application
- `sim/liquidation/` - Mark-based liquidation
- `sim/metrics/` - Exchange-side metrics
- `sim/constraints/` - Tick/lot/min_notional validation
- `sim/adapters/` - Data conversion helpers

**Running a backtest:**

```python
from src.tools.backtest_tools import backtest_run_tool

result = backtest_run_tool(
    system_id="SOLUSDT_5m_ema_rsi_atr_pure",
    window_name="hygiene",
)
```

### 4. Risk Profile Configuration

```yaml
risk_profile:
  initial_equity: 1000.0
  max_leverage: 10.0
  min_trade_usd: 1.0
  stop_equity_usd: 0.0
  taker_fee_rate: 0.0006
  maintenance_margin_rate: 0.005
  include_est_close_fee_in_entry_gate: false

risk_mode: "none"  # or "rules"
```

### 5. IdeaCard System (YAML)

IdeaCard YAML files define complete trading strategies:

```yaml
id: SOLUSDT_15m_mtf_tradeproof
version: "1.0.0"
symbol_universe:
  - SOLUSDT

tf_configs:
  exec:
    timeframe: "15m"
    feature_specs:
      - indicator_type: ema
        output_key: ema_fast
        params:
          length: 9
      - indicator_type: ema
        output_key: ema_slow
        params:
          length: 21

account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0

signal_rules:
  entry_rules:
    - condition: exec_ema_fast > exec_ema_slow
  exit_rules:
    - condition: exec_ema_fast < exec_ema_slow

risk_model:
  stop_loss:
    type: atr_multiple
    atr_key: exec_atr
    multiple: 0.5
  take_profit:
    type: atr_multiple
    atr_key: exec_atr
    multiple: 1.5
```

**Location**: `configs/idea_cards/*.yml`  
**Validation**: `python trade_cli.py backtest idea-card-normalize --idea-card <ID>`

---

## Quick Start

### Run CLI

```bash
python trade_cli.py
```

### Smoke Tests

```bash
python trade_cli.py --smoke full              # Full test (data + trading)
python trade_cli.py --smoke data_extensive    # Extensive data test
python trade_cli.py --smoke backtest          # Backtest test
```

### Environment Setup

```bash
cp env.example api_keys.env
# Edit api_keys.env with your Bybit API keys
```

---

## Available Order Types

| Category | Tools |
|----------|-------|
| Market | `market_buy`, `market_sell`, `market_buy_with_tpsl`, `market_sell_with_tpsl` |
| Limit | `limit_buy`, `limit_sell`, `partial_close` |
| Stop | `stop_market_buy`, `stop_market_sell`, `stop_limit_buy`, `stop_limit_sell` |
| Management | `get_open_orders`, `cancel_order`, `amend_order`, `cancel_all_orders` |
| Batch | `batch_market_orders`, `batch_limit_orders`, `batch_cancel_orders` |

---

## Important Rules

### Critical — Never Violate

1. **All trades through tools** — Never call `bybit_client` directly
2. **No hardcoding** — Symbols, sizes, paths from config or user input
3. **Safety first** — Risk manager checks before every order
4. **Demo first** — Test on demo API before live
5. **Time ranges required** — All history endpoints need explicit ranges

### Trading Execution Flow (Mandatory)

```
Strategy → Risk Manager → Order Executor → Exchange
```

- NEVER call exchange methods directly from strategies
- NEVER bypass risk_manager
- NEVER execute orders without Signal objects

---

## Key Files Reference

| Purpose | File |
|---------|------|
| Main CLI | `trade_cli.py` |
| Central Config | `src/config/config.py` |
| Exchange Manager | `src/core/exchange_manager.py` |
| Risk Manager | `src/core/risk_manager.py` |
| Backtest Engine | `src/backtest/engine.py` |
| Simulated Exchange | `src/backtest/sim/exchange.py` |
| Exchange Modules | `src/backtest/sim/` (ledger, pricing, execution, funding, liquidation) |
| IdeaCard System | `src/backtest/idea_card.py` |
| Historical Data | `src/data/historical_data_store.py` |
| Tool Registry | `src/tools/tool_registry.py` |

---

## Documentation Structure

| Path | Contents |
|------|----------|
| `docs/architecture/` | Technical documentation (SIMULATED_EXCHANGE.md, SYSTEM_REVIEW.md) |
| `docs/guides/` | How-to guides |
| `docs/project/` | Project documentation |
| `docs/examples/` | Code examples |
| `docs/brainstorm/` | Planning documents |

---

## API Rate Limits

| Endpoint Type | Limit | Bot Uses |
|---------------|-------|----------|
| IP (public) | 600/5sec | 100/sec |
| Account/Position | 50/sec | 40/sec |
| Orders | 10/sec/symbol | 8/sec |

---

## Dependencies

Core dependencies (see `requirements.txt`):

- `pybit>=5.13.0` — Bybit Python SDK
- `duckdb>=0.9.0` — Historical data storage
- `pandas>=2.0.0` — Data processing
- `rich>=13.0.0` — CLI display
- `pyyaml>=6.0` — Config parsing

---

**For detailed technical documentation, see:**
- `docs/architecture/SYSTEM_REVIEW.md` — Complete technical overview
- `docs/architecture/SIMULATED_EXCHANGE.md` — Backtest accounting model & modular architecture
- `docs/architecture/DATA_ARCHITECTURE.md` — Data storage details
- `docs/architecture/BACKTEST_MODULE_OVERVIEW.md` — Backtest engine module details

**For next-phase planning, see:**
- `docs/project/NEXT_PHASE_ARCHITECTURE_REFACTOR_PLAN.md` — Array-backed snapshots, Parquet artifacts, market structure features, multi-IdeaCard composition
