# CODEBASE ANALYSIS - TRADE Trading Bot

**Generated:** 2026-01-14
**Analyzed by:** 40+ parallel Opus agents
**Purpose:** Complete src/ directory mapping for redundancy identification

---

## 1. EXECUTIVE SUMMARY

### Overview Statistics

| Metric | Value |
|--------|-------|
| **Total Python Files** | 360 |
| **Total Lines of Code** | 129,699 |
| **Modules (Top-Level)** | 11 |
| **Entry Point** | `trade_cli.py` (2,737 lines) |
| **Potential Redundant Code** | ~3,100 lines |

### Module Breakdown by Size

| Module | Lines | Files | % of Total | Description |
|--------|-------|-------|------------|-------------|
| `backtest/` | ~51,200 | 153 | 39% | Simulation engine, DSL, structures |
| `forge/` | ~26,700 | 79 | 21% | Development & validation |
| `cli/` | ~12,200 | 27 | 9% | Menu system, smoke tests |
| `tools/` | ~11,900 | 28 | 9% | External API surface |
| `data/` | ~7,800 | 11 | 6% | DuckDB, market data |
| `core/` | ~5,800 | 16 | 5% | Live trading, positions |
| `utils/` | ~5,700 | 10 | 4% | Logging, helpers |
| `viz/` | ~4,400 | 24 | 3% | Backtest visualization |
| `exchanges/` | ~1,900 | 6 | 2% | Bybit API |
| `config/` | ~1,400 | 3 | 1% | Configuration |
| `risk/` | ~500 | 2 | <1% | Global risk view |

### Key Findings

| Category | Finding | Impact |
|----------|---------|--------|
| **Domain Violation** | `src/core/prices/live_source.py` imports from `src/backtest/` | HIGH |
| **Duplicate Registry** | `market_structure/registry.py` duplicates `incremental/registry.py` | ~1,645 lines |
| **Dead Code** | `utils/epoch_tracking.py` unused after Play migration | ~921 lines |
| **Deprecated Tools** | `backtest_tools.py` has NotImplementedError stubs | ~150 lines |
| **Duplicate Detectors** | Swing/Trend/Zone detectors exist in 2 locations | ~600 lines |

---

## 2. ENTRY POINT: trade_cli.py

**Location:** `C:\code\ai\trade\trade_cli.py`
**Lines:** 2,737

### Imports

```python
# Standard library
import argparse, os, sys, asyncio
from datetime import datetime, timedelta
from pathlib import Path

# Rich UI framework
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.align import Align
from rich.text import Text

# Internal - Config
from src.config.config import get_config, TradingMode, Config
from src.config.constants import TradingEnv

# Internal - Core
from src.core.application import Application, get_application, reset_application

# Internal - Utils
from src.utils.logger import setup_logger, get_logger
from src.utils.cli_display import (format_account_summary, format_positions_table,
    format_orders_table, get_action_label, ACTION_REGISTRY)

# Internal - CLI
from src.cli.menus import (account_menu_handler, positions_menu_handler,
    orders_menu_handler, market_data_menu_handler, data_menu_handler,
    backtest_menu_handler, forge_menu_handler)
from src.cli.styles import CLIStyles, CLIColors, CLIIcons
from src.cli.utils import console, clear_screen, print_header, get_input, TimeRangeSelection

# Internal - CLI Smoke Tests
from src.cli.smoke_tests import (run_smoke_suite, run_core_smoke, run_data_smoke,
    run_backtest_smoke, run_forge_smoke, run_metadata_smoke, run_rules_smoke,
    run_prices_smoke, run_sim_orders_smoke, run_structure_smoke)

# Internal - Tools (~90 tool functions)
from src.tools import (account_summary_tool, get_positions_tool, close_position_tool,
    get_open_orders_tool, cancel_order_tool, get_ticker_tool, sync_historical_data_tool,
    # ... many more tools
)

# Internal - Backtest specific
from src.backtest.artifacts.determinism import verify_run_determinism
from src.backtest.metrics import Metrics
from src.backtest.types import EquityPoint

# Internal - Viz
from src.viz.server import run_server

# Internal - Forge
from src.forge.validation.synthetic_data import generate_synthetic_candles
```

### Main Class: TradeCLI

```python
class TradeCLI:
    """Main CLI application class."""

    def __init__(self):
        """Initialize config, logger, and application state."""

    def main_menu(self) -> None:
        """Main menu loop with 10 options."""
        # Options: Account, Positions, Orders, Market Data, Data Builder,
        #          Backtest, Forge, Connection Test, Health Check, Panic/Exit

    def account_menu(self) -> None:
        """Delegate to account_menu_handler."""

    def positions_menu(self) -> None:
        """Delegate to positions_menu_handler."""

    def orders_menu(self) -> None:
        """Delegate to orders_menu_handler."""

    def market_data_menu(self) -> None:
        """Delegate to market_data_menu_handler."""

    def data_menu(self) -> None:
        """Delegate to data_menu_handler."""

    def backtest_menu(self) -> None:
        """Delegate to backtest_menu_handler."""

    def forge_menu(self) -> None:
        """Delegate to forge_menu_handler."""

    def connection_test(self) -> None:
        """API connectivity test."""

    def health_check(self) -> None:
        """System health diagnostic."""

    def panic_menu(self) -> None:
        """Emergency close all positions."""
```

### Standalone Functions

```python
# Environment selection (lines 507-661)
def select_trading_environment() -> TradingEnv:
    """DEMO/LIVE environment selector with confirmation."""

def _confirm_live_mode() -> bool:
    """Double confirmation for LIVE trading."""

# Argument parsing (lines 664-943)
def parse_cli_args() -> argparse.Namespace:
    """Parse command line arguments for non-interactive mode."""

def _parse_datetime(date_str: str) -> datetime:
    """Parse datetime from string."""

# Backtest handlers (lines 964-2496)
def _handle_synthetic_backtest_run(args: argparse.Namespace) -> int:
def handle_backtest_run(args: argparse.Namespace) -> int:
def handle_backtest_preflight(args: argparse.Namespace) -> int:
def handle_backtest_indicators(args: argparse.Namespace) -> int:
def handle_backtest_data_fix(args: argparse.Namespace) -> int:
def handle_backtest_list(args: argparse.Namespace) -> int:
def handle_backtest_normalize(args: argparse.Namespace) -> int:
def handle_backtest_normalize_batch(args: argparse.Namespace) -> int:
def handle_backtest_verify_suite(args: argparse.Namespace) -> int:
def handle_backtest_audit_toolkit(args: argparse.Namespace) -> int:
def handle_backtest_math_parity(args: argparse.Namespace) -> int:
def handle_backtest_metadata_smoke(args: argparse.Namespace) -> int:
def handle_backtest_mark_price_smoke(args: argparse.Namespace) -> int:
def handle_backtest_structure_smoke(args: argparse.Namespace) -> int:
def handle_backtest_audit_snapshot_plumbing(args: argparse.Namespace) -> int:
def handle_backtest_audit_rollup(args: argparse.Namespace) -> int:
def handle_backtest_verify_determinism(args: argparse.Namespace) -> int:
def handle_backtest_metrics_audit(args: argparse.Namespace) -> int:

# Viz handlers (lines 2503-2539)
def handle_viz_serve(args: argparse.Namespace) -> int:
def handle_viz_open(args: argparse.Namespace) -> int:

# Entry point (lines 2542-2737)
def main() -> int:
    """Main entry point."""
```

### Connection Flow

```
trade_cli.py
├─→ src/config/config.py           # Configuration loading
├─→ src/core/application.py        # Application lifecycle
├─→ src/utils/logger.py            # Logging setup
├─→ src/utils/cli_display.py       # Output formatting
├─→ src/cli/menus/*                # Menu handlers (10 menus)
│   └─→ src/tools/*                # Tool functions (~90)
│       └─→ src/backtest/runner.py # Backtest execution
│           └─→ src/backtest/engine.py  # Engine core
├─→ src/cli/smoke_tests/*          # Smoke test suites
│   └─→ src/forge/*                # Validation/audits
├─→ src/viz/server.py              # Visualization server
└─→ src/data/historical_data_store.py  # Data access
```

---

## 3. MODULE-BY-MODULE INVENTORY

### 3.1 src/backtest/ (Simulation Engine)

**Location:** `src/backtest/`
**Files:** 153
**Lines:** ~51,200
**Purpose:** Deterministic backtesting engine with multi-timeframe support

#### Root Files

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 187 | Module exports |
| `engine.py` | 1,685 | Main backtest orchestrator |
| `runner.py` | 1,033 | Play-based backtest runner |
| `types.py` | 672 | Core type definitions |
| `metrics.py` | 1,030 | Financial metrics (62 fields) |
| `system_config.py` | 993 | System configuration (legacy) |
| `execution_validation.py` | 1,262 | Play validation |
| `indicator_registry.py` | 1,198 | 43 indicator registry |
| `indicator_vendor.py` | 803 | pandas_ta wrappers |
| `indicators.py` | 296 | Feature-to-indicator mapping |
| `feature_registry.py` | 572 | Unified feature access |
| `bar_processor.py` | 653 | Run loop processing |
| `engine_data_prep.py` | 1,010 | Data loading/preparation |
| `engine_factory.py` | 527 | Engine creation factory |
| `engine_feed_builder.py` | 529 | FeedStore construction |
| `engine_snapshot.py` | 340 | Snapshot view construction |
| `engine_stops.py` | 196 | Stop condition checking |
| `engine_history.py` | 142 | Trade history management |
| `engine_artifacts.py` | 201 | Artifact generation |
| `play_yaml_builder.py` | 723 | YAML generation |
| `window_presets.py` | 108 | Backtest window presets |
| `risk_policy.py` | 176 | Risk policy implementations |
| `simulated_risk_manager.py` | 196 | Position sizing |
| `runtime_config.py` | 60 | Runtime configuration |
| `snapshot_artifacts.py` | 85 | Snapshot metadata |

#### Subdirectory: artifacts/ (8 files)

| File | Lines | Classes/Functions |
|------|-------|-------------------|
| `artifact_standards.py` | 1,264 | Standard artifact validation |
| `determinism.py` | 380 | Hash-based determinism verification |
| `equity_writer.py` | 120 | Equity curve export |
| `eventlog_writer.py` | 180 | Event log export |
| `hashes.py` | 95 | Hash computation utilities |
| `manifest_writer.py` | 150 | Run manifest generation |
| `parquet_writer.py` | 200 | Parquet export |
| `pipeline_signature.py` | 140 | Pipeline versioning |

#### Subdirectory: features/ (3 files)

| File | Lines | Classes/Functions |
|------|-------|-------------------|
| `feature_spec.py` | 280 | `FeatureSpec` dataclass |
| `feature_frame_builder.py` | 350 | Frame construction |
| `__init__.py` | 15 | Exports |

#### Subdirectory: gates/ (5 files)

| File | Lines | Classes/Functions |
|------|-------|-------------------|
| `batch_verification.py` | 320 | Batch play verification |
| `indicator_requirements_gate.py` | 180 | Indicator availability check |
| `play_generator.py` | 250 | Play generation |
| `production_first_import_gate.py` | 90 | Import validation |
| `__init__.py` | 20 | Exports |

#### Subdirectory: incremental/ (10 files)

| File | Lines | Classes/Functions |
|------|-------|-------------------|
| `base.py` | 280 | `BaseIncrementalDetector` ABC |
| `primitives.py` | 450 | `MonotonicDeque`, `RingBuffer` |
| `registry.py` | 180 | Structure type registry |
| `state.py` | 320 | `TFIncrementalState`, `MultiTFIncrementalState` |
| `detectors/swing.py` | 530 | `IncrementalSwingDetector` |
| `detectors/trend.py` | 380 | `IncrementalTrendDetector` |
| `detectors/zone.py` | 420 | `IncrementalZoneDetector` |
| `detectors/fibonacci.py` | 350 | `IncrementalFibonacciDetector` |
| `detectors/derived_zone.py` | 480 | `IncrementalDerivedZoneDetector` |
| `detectors/rolling_window.py` | 290 | `RollingWindowDetector` |

#### Subdirectory: market_structure/ (9 files) - REDUNDANT

| File | Lines | Classes/Functions | Status |
|------|-------|-------------------|--------|
| `builder.py` | 280 | Structure builder | DUPLICATE |
| `registry.py` | 220 | Structure registry | DUPLICATE of incremental/registry.py |
| `spec.py` | 180 | Structure specifications | |
| `types.py` | 150 | Structure types | |
| `zone_interaction.py` | 190 | Zone interaction logic | |
| `detectors/swing_detector.py` | 171 | `SwingDetector` | DUPLICATE of incremental/detectors/swing.py |
| `detectors/trend_classifier.py` | 250 | `TrendClassifier` | DUPLICATE |
| `detectors/zone_detector.py` | 280 | `ZoneDetector` | DUPLICATE |

#### Subdirectory: play/ (4 files)

| File | Lines | Classes/Functions |
|------|-------|-------------------|
| `play.py` | 680 | `Play` dataclass, loading/saving |
| `config_models.py` | 520 | `ExitMode`, `FeeModel`, `AccountConfig`, etc. |
| `risk_model.py` | 380 | `RiskModel`, `StopLossRule`, `TakeProfitRule`, `SizingRule` |
| `__init__.py` | 25 | Exports |

#### Subdirectory: prices/ (8 files)

| File | Lines | Classes/Functions |
|------|-------|-------------------|
| `source.py` | 180 | `PriceSource` protocol |
| `backtest_source.py` | 280 | `BacktestPriceSource` |
| `demo_source.py` | 150 | `DemoPriceSource` |
| `engine.py` | 220 | Price engine |
| `types.py` | 90 | `HealthCheckResult` |
| `validation.py` | 140 | Price validation |
| `providers/sim_mark.py` | 180 | Simulated mark price |

#### Subdirectory: rationalization/ (6 files)

| File | Lines | Classes/Functions |
|------|-------|-------------------|
| `rationalizer.py` | 420 | `StateRationalizer` |
| `transitions.py` | 350 | `TransitionManager` |
| `conflicts.py` | 380 | Conflict resolution |
| `derived.py` | 290 | `DerivedStateComputer` |
| `types.py` | 180 | `MarketRegime`, `Transition`, `RationalizedState` |
| `__init__.py` | 20 | Exports |

#### Subdirectory: rules/ (20 files)

| File | Lines | Classes/Functions |
|------|-------|-------------------|
| `compile.py` | 680 | DSL compilation |
| `dsl_parser.py` | 850 | DSL parsing |
| `dsl_warmup.py` | 320 | Warmup calculation |
| `eval.py` | 520 | Rule evaluation |
| `registry.py` | 280 | Operator registry |
| `strategy_blocks.py` | 380 | Block evaluation |
| `types.py` | 220 | Rule types |
| `dsl_nodes/base.py` | 180 | Base AST nodes |
| `dsl_nodes/boolean.py` | 250 | Boolean nodes |
| `dsl_nodes/condition.py` | 320 | Condition nodes |
| `dsl_nodes/constants.py` | 90 | Constant nodes |
| `dsl_nodes/utils.py` | 120 | Node utilities |
| `dsl_nodes/windows.py` | 280 | Window nodes |
| `evaluation/boolean_ops.py` | 180 | Boolean operations |
| `evaluation/condition_ops.py` | 350 | Condition operations |
| `evaluation/core.py` | 420 | Core evaluation |
| `evaluation/resolve.py` | 280 | Value resolution |
| `evaluation/setups.py` | 220 | Setup evaluation |
| `evaluation/shift_ops.py` | 150 | Shift operations |
| `evaluation/window_ops.py` | 380 | Window operations |

#### Subdirectory: runtime/ (20 files)

| File | Lines | Classes/Functions |
|------|-------|-------------------|
| `feed_store.py` | 680 | `FeedStore`, `MultiTFFeedStore` |
| `snapshot_view.py` | 1,748 | `RuntimeSnapshotView` |
| `snapshot_builder.py` | 280 | Snapshot construction |
| `preflight.py` | 580 | `PreflightReport`, `run_preflight_gate` |
| `windowing.py` | 420 | Window computation |
| `timeframe.py` | 180 | TF utilities |
| `cache.py` | 250 | `TimeframeCache` |
| `types.py` | 380 | `Bar`, `FeatureSnapshot`, `RuntimeSnapshot` |
| `quote_state.py` | 220 | `QuoteState` |
| `rollup_bucket.py` | 180 | `ExecRollupBucket` |
| `funding_scheduler.py` | 280 | Funding event scheduling |
| `state_tracker.py` | 450 | `StateTracker` |
| `state_types.py` | 320 | State type definitions |
| `signal_state.py` | 180 | Signal state tracking |
| `action_state.py` | 150 | Action state tracking |
| `block_state.py` | 140 | Block state tracking |
| `gate_state.py` | 160 | Gate state tracking |
| `indicator_metadata.py` | 220 | Indicator metadata |
| `data_health.py` | 280 | Data health checking |
| `__init__.py` | 40 | Exports |

#### Subdirectory: sim/ (18 files)

| File | Lines | Classes/Functions |
|------|-------|-------------------|
| `exchange.py` | 1,180 | `SimulatedExchange` |
| `ledger.py` | 380 | Ledger tracking |
| `types.py` | 280 | Sim types |
| `adapters/funding_adapter.py` | 180 | Funding data adapter |
| `adapters/ohlcv_adapter.py` | 220 | OHLCV data adapter |
| `constraints/constraints.py` | 280 | Position constraints |
| `execution/execution_model.py` | 420 | Execution model |
| `execution/impact_model.py` | 180 | Market impact |
| `execution/liquidity_model.py` | 150 | Liquidity modeling |
| `execution/slippage_model.py` | 180 | Slippage calculation |
| `funding/funding_model.py` | 280 | Funding rate model |
| `liquidation/liquidation_model.py` | 350 | Liquidation logic |
| `metrics/metrics.py` | 420 | Trade metrics |
| `pricing/intrabar_path.py` | 280 | Intrabar price paths |
| `pricing/price_model.py` | 320 | Price modeling |
| `pricing/spread_model.py` | 180 | Spread calculation |

---

### 3.2 src/core/ (Live Trading)

**Location:** `src/core/`
**Files:** 17
**Lines:** ~5,800
**Purpose:** Live trading with Bybit API

| File | Lines | Classes/Functions | Purpose |
|------|-------|-------------------|---------|
| `__init__.py` | 63 | Re-exports | Module exports |
| `application.py` | 694 | `Application`, `get_application` | Application lifecycle |
| `exchange_manager.py` | 516 | `ExchangeManager`, `Position`, `Order` | Unified exchange interface |
| `position_manager.py` | 549 | `PositionManager`, `PortfolioSnapshot` | Position tracking |
| `risk_manager.py` | 538 | `RiskManager`, `Signal`, `RiskCheckResult` | Pre-trade risk checks |
| `order_executor.py` | 534 | `OrderExecutor`, `ExecutionResult` | Order execution |
| `exchange_orders_market.py` | 168 | `market_buy`, `market_sell`, etc. | Market order helpers |
| `exchange_orders_limit.py` | 152 | `limit_buy`, `limit_sell`, etc. | Limit order helpers |
| `exchange_orders_stop.py` | 192 | `stop_market_buy`, `trailing_stop`, etc. | Stop order helpers |
| `exchange_orders_manage.py` | 480 | Order management functions | Order CRUD |
| `exchange_positions.py` | 957 | 27 position functions | Position queries/mods |
| `exchange_instruments.py` | 188 | `get_instruments`, `get_tick_size` | Instrument info |
| `exchange_websocket.py` | 236 | WebSocket functions | WS management |
| `safety.py` | 142 | `panic_close_all`, `SafetyChecks` | Emergency controls |
| `prices/live_source.py` | 112 | `LivePriceSource` (STUB) | **DOMAIN VIOLATION** |

---

### 3.3 src/data/ (Historical Storage)

**Location:** `src/data/`
**Files:** 11
**Lines:** ~7,800
**Purpose:** DuckDB-backed historical data

| File | Lines | Classes/Functions | Purpose |
|------|-------|-------------------|---------|
| `__init__.py` | 123 | Re-exports | Module exports |
| `historical_data_store.py` | 1,854 | `HistoricalDataStore` | DuckDB OHLCV storage |
| `market_data.py` | 789 | `MarketData` | Live market data cache |
| `historical_maintenance.py` | 461 | `heal_symbol`, `vacuum` | Data maintenance |
| `historical_queries.py` | 286 | Query helpers | Query utilities |
| `historical_sync.py` | 444 | Sync functions | Data synchronization |
| `realtime_state.py` | 931 | `RealtimeState`, event types | WebSocket state |
| `realtime_bootstrap.py` | 1,078 | `RealtimeBootstrap` | WS bootstrap |
| `realtime_models.py` | 949 | WS message models | Pydantic models |
| `sessions.py` | 548 | `DemoSession`, `LiveSession` | Isolated sessions |
| `backend_protocol.py` | 473 | `HistoricalBackend` protocol | Future MongoDB |

---

### 3.4 src/exchanges/ (API Clients)

**Location:** `src/exchanges/`
**Files:** 6
**Lines:** ~1,900
**Purpose:** Bybit API wrapper using pybit

| File | Lines | Classes/Functions | Purpose |
|------|-------|-------------------|---------|
| `__init__.py` | 31 | Re-exports | Module exports |
| `bybit_client.py` | 597 | `BybitClient`, `BybitAPIError` | Main client |
| `bybit_market.py` | 382 | Market data functions | Market API |
| `bybit_account.py` | 436 | Account functions | Account API |
| `bybit_trading.py` | 580 | Trading functions | Trading API |
| `bybit_websocket.py` | 298 | WebSocket functions | WS connections |

---

### 3.5 src/forge/ (Development Environment)

**Location:** `src/forge/`
**Files:** 79
**Lines:** ~26,700
**Purpose:** Play development, validation, and testing

#### Root Files

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 80 | Module exports |

#### Subdirectory: audits/ (16 files)

| File | Lines | Purpose |
|------|-------|---------|
| `stress_test_suite.py` | 820 | Stress testing |
| `toolkit_contract_audit.py` | 380 | Indicator contracts |
| `audit_math_parity.py` | 290 | Math verification |
| `audit_in_memory_parity.py` | 340 | In-memory comparison |
| `audit_snapshot_plumbing_parity.py` | 410 | Snapshot plumbing |
| `audit_rollup_parity.py` | 320 | Rollup verification |
| `audit_play_value_flow.py` | 245 | Value flow |
| `audit_primitives.py` | 480 | Primitive tests |
| `audit_rolling_window.py` | 390 | Rolling window |
| `audit_incremental_state.py` | 350 | Incremental state |
| `audit_incremental_registry.py` | 520 | Registry audit |
| `audit_fibonacci.py` | 410 | Fibonacci tests |
| `audit_trend_detector.py` | 360 | Trend detector |
| `audit_zone_detector.py` | 490 | Zone detector |
| `artifact_parity_verifier.py` | 280 | CSV/Parquet parity |

#### Subdirectory: blocks/ (3 files)

| File | Lines | Purpose |
|------|-------|---------|
| `block.py` | 380 | `Block` dataclass |
| `normalizer.py` | 280 | Block normalization |

#### Subdirectory: plays/ (2 files)

| File | Lines | Purpose |
|------|-------|---------|
| `normalizer.py` | 420 | Play normalization |

#### Subdirectory: setups/ (2 files) - DEPRECATED

| File | Lines | Purpose |
|------|-------|---------|
| `setup.py` | 280 | Setup dataclass (deprecated - use Block) |

#### Subdirectory: systems/ (3 files)

| File | Lines | Purpose |
|------|-------|---------|
| `system.py` | 350 | System dataclass |
| `normalizer.py` | 280 | System normalization |

#### Subdirectory: functional/ (7 files)

| File | Lines | Purpose |
|------|-------|---------|
| `runner.py` | 380 | Functional test runner |
| `generator.py` | 450 | Play generator |
| `coverage.py` | 280 | Coverage tracking |
| `date_range_finder.py` | 180 | Date utilities |
| `engine_validator.py` | 320 | Engine validation |
| `syntax_coverage.py` | 250 | Syntax coverage |
| `syntax_generator.py` | 280 | Syntax generation |

#### Subdirectory: synthetic/ (10 files)

| File | Lines | Purpose |
|------|-------|---------|
| `conftest.py` | 180 | pytest fixtures |
| `generators/` | - | Data generators (empty) |
| `harness/` | 350 | Test harness |
| `cases/test_*.py` | ~2,800 | Test cases (8 files) |

#### Subdirectory: validation/ (22 files)

| File | Lines | Purpose |
|------|-------|---------|
| `play_validator.py` | 420 | Single play validation |
| `batch_runner.py` | 380 | Batch validation |
| `report.py` | 280 | Report formatting |
| `fixtures.py` | 320 | Test fixtures |
| `synthetic_data.py` | 450 | Synthetic generation |
| `synthetic_provider.py` | 280 | Data provider |
| `test_runner.py` | 350 | Test execution |
| `tier0_syntax/` | 180 | Syntax tests |
| `tier1_operators/` | ~2,400 | Operator tests (9 files) |
| `tier2_structures/` | ~1,800 | Structure tests (6 files) |

---

### 3.6 src/tools/ (Tool Layer)

**Location:** `src/tools/`
**Files:** 28
**Lines:** ~11,900
**Purpose:** Callable tools for CLI/API (~90 tools)

| File | Lines | Tools | Purpose |
|------|-------|-------|---------|
| `__init__.py` | 359 | Re-exports | ~90 tool exports |
| `shared.py` | 150 | `ToolResult` | Shared types |
| `tool_registry.py` | 180 | `ToolRegistry` | Tool discovery |
| `position_tools.py` | 1,165 | 20 tools | Position management |
| `account_tools.py` | 635 | 13 tools | Account tools |
| `order_tools.py` | 1,069 | 19 tools | Order tools |
| `order_tools_common.py` | 182 | Helpers | Order helpers |
| `diagnostics_tools.py` | 545 | 8 tools | Connectivity/health |
| `market_data_tools.py` | 290 | 7 tools | Market data |
| `data_tools.py` | 200 | Aggregation | Data tool re-exports |
| `data_tools_common.py` | 300 | Helpers | Data helpers |
| `data_tools_sync.py` | 873 | 12 tools | Data synchronization |
| `data_tools_status.py` | 320 | 6 tools | Data status |
| `data_tools_query.py` | 662 | 6 tools | Data queries |
| `backtest_tools.py` | 851 | 10 tools | Legacy SystemConfig tools |
| `backtest_cli_wrapper.py` | 420 | Wrappers | Play CLI wrapper |
| `backtest_play_tools.py` | 1,400 | 15 tools | Play-specific tools |
| `backtest_audit_tools.py` | 546 | 7 tools | Backtest audits |
| `forge_stress_test_tools.py` | 280 | 4 tools | Stress testing |
| `specs/` | ~1,200 | 8 files | Tool specifications |

---

### 3.7 src/cli/ (Command Line Interface)

**Location:** `src/cli/`
**Files:** 27
**Lines:** ~12,200
**Purpose:** CLI menus and utilities

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 54 | Module exports |
| `utils.py` | 763 | CLI utilities |
| `styles.py` | 210 | Styling constants |
| `art_stylesheet.py` | 541 | $100 bill art theme |

#### Subdirectory: menus/ (10 files)

| File | Lines | Purpose |
|------|-------|---------|
| `account_menu.py` | 380 | Account menu |
| `positions_menu.py` | 420 | Positions menu |
| `orders_menu.py` | 450 | Orders menu |
| `market_data_menu.py` | 320 | Market data menu |
| `data_menu.py` | 480 | Data builder menu |
| `backtest_menu.py` | 520 | Backtest menu |
| `backtest_analytics_menu.py` | 280 | Analytics submenu |
| `backtest_audits_menu.py` | 350 | Audits submenu |
| `backtest_play_menu.py` | 380 | Play submenu |
| `forge_menu.py` | 420 | Forge menu |

#### Subdirectory: smoke_tests/ (11 files)

| File | Lines | Purpose |
|------|-------|---------|
| `core.py` | 280 | Core smoke tests |
| `data.py` | 320 | Data smoke tests |
| `backtest.py` | 743 | Backtest smoke tests |
| `forge.py` | 280 | Forge smoke tests |
| `metadata.py` | 350 | Metadata smoke tests |
| `orders.py` | 280 | Order smoke tests |
| `order_mechanics.py` | 320 | Order mechanics |
| `prices.py` | 280 | Price smoke tests |
| `rules.py` | 350 | Rules smoke tests |
| `sim_orders.py` | 280 | Simulated orders |
| `structure.py` | 1,359 | Structure smoke tests |

---

### 3.8 src/utils/ (Utilities)

**Location:** `src/utils/`
**Files:** 11
**Lines:** ~5,700
**Purpose:** Shared utilities

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 36 | Module exports |
| `logger.py` | 577 | `TradingLogger`, `setup_logger` |
| `cli_display.py` | 2,507 | 53 display functions |
| `rate_limiter.py` | 215 | `RateLimiter`, `MultiRateLimiter` |
| `helpers.py` | 92 | Type conversion helpers |
| `time_range.py` | 501 | `TimeRange`, `TimeRangePreset` |
| `datetime_utils.py` | 120 | Datetime helpers |
| `epoch_tracking.py` | 921 | **DEAD CODE** - unused after Play migration |
| `debug.py` | 180 | Debug tracing |
| `log_context.py` | 240 | Logging context |

---

### 3.9 src/viz/ (Visualization)

**Location:** `src/viz/`
**Files:** 24
**Lines:** ~4,400
**Purpose:** FastAPI visualization server

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 15 | Module exports |
| `server.py` | 202 | FastAPI server |
| `api/charts.py` | 290 | Chart endpoints |
| `api/equity.py` | 150 | Equity endpoints |
| `api/indicators.py` | 280 | Indicator endpoints |
| `api/metrics.py` | 180 | Metrics endpoints |
| `api/runs.py` | 220 | Run list endpoints |
| `api/trades.py` | 160 | Trade endpoints |
| `data/artifact_loader.py` | 180 | Artifact loading |
| `data/equity_loader.py` | 150 | Equity loading |
| `data/indicator_loader.py` | 180 | Indicator loading |
| `data/ohlcv_loader.py` | 220 | OHLCV loading |
| `data/play_loader.py` | 180 | Play loading |
| `data/timestamp_utils.py` | 120 | Timestamp utilities |
| `data/trades_loader.py` | 150 | Trade loading |
| `models/run_metadata.py` | 180 | Run models |
| `renderers/indicators.py` | 220 | Indicator rendering |
| `renderers/structures.py` | 180 | Structure rendering |
| `schemas/artifact_schema.py` | 150 | Artifact schemas |

---

### 3.10 src/config/ (Configuration)

**Location:** `src/config/`
**Files:** 3
**Lines:** ~1,400
**Purpose:** Configuration management

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 48 | Module exports |
| `config.py` | 1,060 | `Config`, `get_config` |
| `constants.py` | 186 | Environment constants |

---

### 3.11 src/risk/ (Risk Management)

**Location:** `src/risk/`
**Files:** 2
**Lines:** ~500
**Purpose:** Global portfolio risk

| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 33 | Module exports |
| `global_risk.py` | 452 | `GlobalRiskView`, `RiskLimits` |

---

## 4. DEPENDENCY GRAPH

```
trade_cli.py (ENTRY POINT)
│
├── src/config/
│   ├── config.py ──────────────────> dotenv, dataclasses, pathlib
│   └── constants.py
│
├── src/core/
│   ├── application.py
│   │   ├──> src/config/config.py
│   │   ├──> src/utils/logger.py
│   │   ├──> exchange_manager.py
│   │   ├──> position_manager.py
│   │   ├──> risk_manager.py
│   │   └──> src/data/realtime_*.py
│   │
│   ├── exchange_manager.py ────────> src/exchanges/bybit_client.py
│   ├── position_manager.py ────────> exchange_manager, risk_manager
│   ├── risk_manager.py ────────────> exchange_manager, config
│   ├── order_executor.py ──────────> exchange_manager, risk_manager
│   ├── exchange_orders_*.py ───────> exchange_manager
│   ├── exchange_positions.py ──────> exchange_manager
│   ├── exchange_websocket.py ──────> src/exchanges/bybit_websocket.py
│   ├── safety.py ──────────────────> exchange_manager
│   └── prices/live_source.py ──────> src/backtest/prices/source.py [VIOLATION!]
│
├── src/data/
│   ├── historical_data_store.py ───> src/exchanges/bybit_client.py, duckdb, pandas
│   ├── market_data.py ─────────────> src/exchanges/bybit_client.py
│   ├── historical_*.py ────────────> historical_data_store
│   ├── realtime_state.py ──────────> dataclasses, datetime
│   ├── realtime_bootstrap.py ──────> src/exchanges/bybit_websocket.py
│   ├── sessions.py ────────────────> historical_data_store, market_data
│   └── backend_protocol.py ────────> abc
│
├── src/exchanges/
│   ├── bybit_client.py ────────────> pybit, src/utils/rate_limiter.py
│   ├── bybit_market.py ────────────> bybit_client
│   ├── bybit_account.py ───────────> bybit_client
│   ├── bybit_trading.py ───────────> bybit_client
│   └── bybit_websocket.py ─────────> pybit.WebSocket
│
├── src/backtest/
│   ├── engine.py ──────────────────> ALL backtest submodules
│   ├── runner.py ──────────────────> play/*, runtime/*, artifacts/*, gates/*
│   ├── types.py ───────────────────> runtime/types
│   ├── system_config.py ───────────> yaml, dataclasses
│   ├── play/*.py ──────────────────> yaml, dataclasses
│   ├── runtime/*.py ───────────────> numpy, pandas
│   ├── sim/*.py ───────────────────> numpy
│   ├── rules/*.py ─────────────────> regex, AST
│   ├── incremental/*.py ───────────> numpy
│   ├── market_structure/*.py ──────> numpy [DUPLICATE of incremental/]
│   ├── rationalization/*.py ───────> incremental
│   └── artifacts/*.py ─────────────> parquet, json
│
├── src/forge/
│   ├── validation/*.py ────────────> src/backtest/*, yaml
│   ├── audits/*.py ────────────────> src/backtest/*, numpy
│   ├── blocks/*.py ────────────────> yaml
│   ├── plays/*.py ─────────────────> src/backtest/play
│   ├── systems/*.py ───────────────> yaml
│   ├── functional/*.py ────────────> src/backtest/*
│   └── synthetic/*.py ─────────────> src/backtest/*, numpy
│
├── src/tools/
│   ├── position_tools.py ──────────> src/core/*, src/data/*
│   ├── account_tools.py ───────────> src/core/*
│   ├── order_tools.py ─────────────> src/core/*
│   ├── data_tools_*.py ────────────> src/data/*
│   ├── backtest_*_tools.py ────────> src/backtest/*
│   └── shared.py ──────────────────> src/core/*, src/data/*
│
├── src/cli/
│   ├── menus/*.py ─────────────────> src/tools/*, src/utils/*
│   ├── smoke_tests/*.py ───────────> src/tools/*, src/backtest/*
│   ├── utils.py ───────────────────> rich
│   └── styles.py ──────────────────> rich
│
├── src/viz/
│   ├── server.py ──────────────────> fastapi, uvicorn
│   ├── api/*.py ───────────────────> data/*, models/*
│   └── data/*.py ──────────────────> parquet, json
│
├── src/risk/
│   └── global_risk.py ─────────────> src/core/position_manager, config
│
└── src/utils/
    ├── logger.py ──────────────────> logging, rich
    ├── cli_display.py ─────────────> rich
    ├── rate_limiter.py ────────────> time
    ├── helpers.py ─────────────────> [none]
    ├── time_range.py ──────────────> datetime
    └── epoch_tracking.py ──────────> pathlib, json [DEAD CODE]
```

---

## 5. REDUNDANCY ANALYSIS

### HIGH PRIORITY - Delete Entire Files/Modules

| Item | Location | Lines | Action |
|------|----------|-------|--------|
| **Duplicate Structure Registry** | `src/backtest/market_structure/registry.py` | ~220 | DELETE - duplicates `incremental/registry.py` |
| **Duplicate Swing Detector** | `src/backtest/market_structure/detectors/swing_detector.py` | ~171 | DELETE - duplicates `incremental/detectors/swing.py` |
| **Duplicate Trend Classifier** | `src/backtest/market_structure/detectors/trend_classifier.py` | ~250 | DELETE - duplicates `incremental/detectors/trend.py` |
| **Duplicate Zone Detector** | `src/backtest/market_structure/detectors/zone_detector.py` | ~280 | DELETE - duplicates `incremental/detectors/zone.py` |
| **Unused Epoch Tracking** | `src/utils/epoch_tracking.py` | 921 | DELETE - unused after Play migration |
| **Empty Generators Dir** | `src/forge/synthetic/generators/` | 0 | DELETE - empty directory |
| **market_structure/ Module** | `src/backtest/market_structure/` | ~1,645 | DELETE ENTIRE MODULE - batch-only legacy |

**Total HIGH PRIORITY:** ~3,487 lines

### MEDIUM PRIORITY - Deprecated/Stub Code

| Item | Location | Lines | Action |
|------|----------|-------|--------|
| **Deprecated backtest_run_tool** | `src/tools/backtest_tools.py:412-456` | ~45 | DELETE - raises NotImplementedError |
| **Deprecated list_strategies** | `src/tools/backtest_tools.py:833-851` | ~19 | DELETE - raises NotImplementedError |
| **Deprecated load_system_config** | `src/backtest/system_config.py:807-919` | ~113 | MARK DEPRECATED - legacy SystemConfig |
| **LivePriceSource Stub** | `src/core/prices/live_source.py` | 112 | IMPLEMENT or DELETE |
| **Deprecated Setup class** | `src/forge/setups/setup.py` | ~280 | ADD DEPRECATION WARNING |
| **Deprecated Stage 3 code** | `src/backtest/engine_feed_builder.py:172-242` | ~70 | DELETE - market_structure_blocks deprecated |

**Total MEDIUM PRIORITY:** ~639 lines

### LOW PRIORITY - Minor Cleanup

| Item | Location | Action |
|------|----------|--------|
| TODO: "Add structure and operator plays" | `src/forge/functional/generator.py:349` | Create ticket |
| TODO: "Add --structures and --operators" | `src/forge/functional/generator.py:423` | Create ticket |
| TODO: "Implement artifact verification" | `src/forge/audits/stress_test_suite.py:755` | Create ticket |
| TODO: "Check transition history" | `src/backtest/rationalization/conflicts.py:311` | Create ticket |
| Backward-compat alias | `src/backtest/runtime/state_types.py:113` | Document or remove |

---

## 6. DOMAIN BOUNDARY VIOLATIONS

Per CLAUDE.md:
> **Live Trading (`src/core/`)**: Do NOT import from `src/backtest/`

### Violations Found

| File | Line | Import | Severity |
|------|------|--------|----------|
| `src/core/prices/live_source.py` | 21 | `from src.backtest.prices.source import PriceSource, DataNotAvailableError` | **HIGH** |
| `src/core/prices/live_source.py` | 22 | `from src.backtest.prices.types import HealthCheckResult` | **HIGH** |

### Resolution

Move shared types to `src/shared/` or `src/core/prices/types.py`:

```python
# src/shared/protocols/price_source.py (NEW FILE)
from abc import ABC, abstractmethod

class PriceSource(ABC):
    @abstractmethod
    def get_last_price(self, symbol: str) -> float: ...

class DataNotAvailableError(Exception): ...

class HealthCheckResult:
    is_healthy: bool
    message: str
```

Update imports:
- `src/backtest/prices/source.py` → import from `src/shared/protocols/`
- `src/core/prices/live_source.py` → import from `src/shared/protocols/`

---

## 7. LARGEST FILES (Top 20)

| Rank | File | Lines | Notes |
|------|------|-------|-------|
| 1 | `trade_cli.py` | 2,737 | Entry point - acceptable |
| 2 | `src/utils/cli_display.py` | 2,507 | ACTION_REGISTRY - could split |
| 3 | `src/data/historical_data_store.py` | 1,854 | DuckDB store - acceptable |
| 4 | `src/backtest/runtime/snapshot_view.py` | 1,748 | O(1) snapshot - core |
| 5 | `src/backtest/engine.py` | 1,685 | Main engine - core |
| 6 | `src/tools/backtest_play_tools.py` | 1,400 | Play tools - acceptable |
| 7 | `src/cli/smoke_tests/structure.py` | 1,359 | Structure tests - acceptable |
| 8 | `src/forge/generation/generate_100_setups.py` | 1,300 | Could template-ize |
| 9 | `src/backtest/artifacts/artifact_standards.py` | 1,264 | Artifact specs - acceptable |
| 10 | `src/backtest/execution_validation.py` | 1,262 | Play validation - acceptable |
| 11 | `src/backtest/indicator_registry.py` | 1,198 | 43 indicators - acceptable |
| 12 | `src/backtest/sim/exchange.py` | 1,180 | SimExchange - core |
| 13 | `src/tools/position_tools.py` | 1,165 | Position tools - acceptable |
| 14 | `src/data/realtime_bootstrap.py` | 1,078 | WS bootstrap - acceptable |
| 15 | `src/tools/order_tools.py` | 1,069 | Order tools - acceptable |
| 16 | `src/config/config.py` | 1,060 | Config - acceptable |
| 17 | `src/backtest/runner.py` | 1,033 | Backtest runner - core |
| 18 | `src/backtest/metrics.py` | 1,030 | Financial metrics - core |
| 19 | `src/backtest/engine_data_prep.py` | 1,010 | Data prep - acceptable |
| 20 | `src/backtest/system_config.py` | 993 | Legacy - consider deprecate |

---

## 8. RECOMMENDED CLEANUP ACTIONS

### Phase 1: Immediate (HIGH Impact, LOW Risk)

1. **DELETE `src/backtest/market_structure/` module entirely**
   - 9 files, ~1,645 lines
   - Duplicates functionality in `src/backtest/incremental/`
   - Update any imports to use incremental versions
   - Run smoke tests after

2. **DELETE `src/utils/epoch_tracking.py`**
   - 921 lines
   - Only used by deprecated SystemConfig-based tools
   - Remove import from `src/tools/backtest_tools.py`

3. **DELETE deprecated tool stubs in `src/tools/backtest_tools.py`**
   - `backtest_run_tool()` (lines 412-456)
   - `backtest_list_strategies_tool()` (lines 833-851)
   - Update `__init__.py` to remove exports

4. **DELETE empty `src/forge/synthetic/generators/` directory**

### Phase 2: Short Term (Domain Violation Fix)

5. **Fix domain violation in `src/core/prices/live_source.py`**
   - Create `src/shared/protocols/price_source.py`
   - Move `PriceSource`, `DataNotAvailableError`, `HealthCheckResult`
   - Update imports in both `src/backtest/prices/` and `src/core/prices/`

6. **Add deprecation warnings to legacy SystemConfig tools**
   - `src/backtest/system_config.py`
   - Document Play as golden path

### Phase 3: Medium Term (Code Quality)

7. **Split `src/utils/cli_display.py` (2,507 lines)**
   - Extract `ACTION_REGISTRY` to `cli_display_actions.py`
   - Split formatting functions by domain

8. **Consider template-based generation**
   - `src/forge/generation/generate_100_setups.py` (1,300 lines)
   - `src/forge/generation/generate_100_setups_part2.py` (834 lines)

9. **Address active TODOs**
   - Create tickets in `docs/todos/TODO.md` for each TODO comment
   - 7 TODOs identified across forge/audits and forge/functional

### Summary

| Phase | Files Affected | Lines Removed | Risk |
|-------|----------------|---------------|------|
| Phase 1 | 11 files | ~2,700 | Low |
| Phase 2 | 4 files | ~100 (move) | Medium |
| Phase 3 | 3 files | ~0 (refactor) | Low |
| **Total** | **18 files** | **~2,800 lines** | |

---

## APPENDIX A: Complete File List

```
src/
├── __init__.py
├── backtest/
│   ├── __init__.py
│   ├── artifacts/
│   │   ├── __init__.py
│   │   ├── artifact_standards.py
│   │   ├── determinism.py
│   │   ├── equity_writer.py
│   │   ├── eventlog_writer.py
│   │   ├── hashes.py
│   │   ├── manifest_writer.py
│   │   ├── parquet_writer.py
│   │   └── pipeline_signature.py
│   ├── bar_processor.py
│   ├── engine.py
│   ├── engine_artifacts.py
│   ├── engine_data_prep.py
│   ├── engine_factory.py
│   ├── engine_feed_builder.py
│   ├── engine_history.py
│   ├── engine_snapshot.py
│   ├── engine_stops.py
│   ├── execution_validation.py
│   ├── feature_registry.py
│   ├── features/
│   │   ├── __init__.py
│   │   ├── feature_frame_builder.py
│   │   └── feature_spec.py
│   ├── gates/
│   │   ├── __init__.py
│   │   ├── batch_verification.py
│   │   ├── indicator_requirements_gate.py
│   │   ├── play_generator.py
│   │   └── production_first_import_gate.py
│   ├── incremental/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── detectors/
│   │   │   ├── __init__.py
│   │   │   ├── derived_zone.py
│   │   │   ├── fibonacci.py
│   │   │   ├── rolling_window.py
│   │   │   ├── swing.py
│   │   │   ├── trend.py
│   │   │   └── zone.py
│   │   ├── primitives.py
│   │   ├── registry.py
│   │   └── state.py
│   ├── indicator_registry.py
│   ├── indicator_vendor.py
│   ├── indicators.py
│   ├── logging/
│   │   ├── __init__.py
│   │   └── run_logger.py
│   ├── market_structure/          # REDUNDANT - DELETE
│   │   ├── __init__.py
│   │   ├── builder.py
│   │   ├── detectors/
│   │   │   ├── __init__.py
│   │   │   ├── swing_detector.py
│   │   │   ├── trend_classifier.py
│   │   │   └── zone_detector.py
│   │   ├── registry.py
│   │   ├── spec.py
│   │   ├── types.py
│   │   └── zone_interaction.py
│   ├── metrics.py
│   ├── play/
│   │   ├── __init__.py
│   │   ├── config_models.py
│   │   ├── play.py
│   │   └── risk_model.py
│   ├── play_yaml_builder.py
│   ├── prices/
│   │   ├── __init__.py
│   │   ├── backtest_source.py
│   │   ├── demo_source.py
│   │   ├── engine.py
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   └── sim_mark.py
│   │   ├── source.py
│   │   ├── types.py
│   │   └── validation.py
│   ├── rationalization/
│   │   ├── __init__.py
│   │   ├── conflicts.py
│   │   ├── derived.py
│   │   ├── rationalizer.py
│   │   ├── transitions.py
│   │   └── types.py
│   ├── risk_policy.py
│   ├── rules/
│   │   ├── __init__.py
│   │   ├── compile.py
│   │   ├── dsl_nodes/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── boolean.py
│   │   │   ├── condition.py
│   │   │   ├── constants.py
│   │   │   ├── utils.py
│   │   │   └── windows.py
│   │   ├── dsl_parser.py
│   │   ├── dsl_warmup.py
│   │   ├── eval.py
│   │   ├── evaluation/
│   │   │   ├── __init__.py
│   │   │   ├── boolean_ops.py
│   │   │   ├── condition_ops.py
│   │   │   ├── core.py
│   │   │   ├── resolve.py
│   │   │   ├── setups.py
│   │   │   ├── shift_ops.py
│   │   │   └── window_ops.py
│   │   ├── registry.py
│   │   ├── strategy_blocks.py
│   │   └── types.py
│   ├── runner.py
│   ├── runtime/
│   │   ├── __init__.py
│   │   ├── action_state.py
│   │   ├── block_state.py
│   │   ├── cache.py
│   │   ├── data_health.py
│   │   ├── feed_store.py
│   │   ├── funding_scheduler.py
│   │   ├── gate_state.py
│   │   ├── indicator_metadata.py
│   │   ├── preflight.py
│   │   ├── quote_state.py
│   │   ├── rollup_bucket.py
│   │   ├── signal_state.py
│   │   ├── snapshot_builder.py
│   │   ├── snapshot_view.py
│   │   ├── state_tracker.py
│   │   ├── state_types.py
│   │   ├── timeframe.py
│   │   ├── types.py
│   │   └── windowing.py
│   ├── runtime_config.py
│   ├── sim/
│   │   ├── __init__.py
│   │   ├── adapters/
│   │   │   ├── __init__.py
│   │   │   ├── funding_adapter.py
│   │   │   └── ohlcv_adapter.py
│   │   ├── constraints/
│   │   │   ├── __init__.py
│   │   │   └── constraints.py
│   │   ├── exchange.py
│   │   ├── execution/
│   │   │   ├── __init__.py
│   │   │   ├── execution_model.py
│   │   │   ├── impact_model.py
│   │   │   ├── liquidity_model.py
│   │   │   └── slippage_model.py
│   │   ├── funding/
│   │   │   ├── __init__.py
│   │   │   └── funding_model.py
│   │   ├── ledger.py
│   │   ├── liquidation/
│   │   │   ├── __init__.py
│   │   │   └── liquidation_model.py
│   │   ├── metrics/
│   │   │   ├── __init__.py
│   │   │   └── metrics.py
│   │   ├── pricing/
│   │   │   ├── __init__.py
│   │   │   ├── intrabar_path.py
│   │   │   ├── price_model.py
│   │   │   └── spread_model.py
│   │   └── types.py
│   ├── simulated_risk_manager.py
│   ├── snapshot_artifacts.py
│   ├── system_config.py
│   ├── types.py
│   └── window_presets.py
├── cli/
│   ├── __init__.py
│   ├── art_stylesheet.py
│   ├── menus/
│   │   ├── __init__.py
│   │   ├── account_menu.py
│   │   ├── backtest_analytics_menu.py
│   │   ├── backtest_audits_menu.py
│   │   ├── backtest_menu.py
│   │   ├── backtest_play_menu.py
│   │   ├── data_menu.py
│   │   ├── forge_menu.py
│   │   ├── market_data_menu.py
│   │   ├── orders_menu.py
│   │   └── positions_menu.py
│   ├── smoke_tests/
│   │   ├── __init__.py
│   │   ├── backtest.py
│   │   ├── core.py
│   │   ├── data.py
│   │   ├── forge.py
│   │   ├── metadata.py
│   │   ├── order_mechanics.py
│   │   ├── orders.py
│   │   ├── prices.py
│   │   ├── rules.py
│   │   ├── sim_orders.py
│   │   └── structure.py
│   ├── styles.py
│   └── utils.py
├── config/
│   ├── __init__.py
│   ├── config.py
│   └── constants.py
├── core/
│   ├── __init__.py
│   ├── application.py
│   ├── exchange_instruments.py
│   ├── exchange_manager.py
│   ├── exchange_orders_limit.py
│   ├── exchange_orders_manage.py
│   ├── exchange_orders_market.py
│   ├── exchange_orders_stop.py
│   ├── exchange_positions.py
│   ├── exchange_websocket.py
│   ├── order_executor.py
│   ├── position_manager.py
│   ├── prices/
│   │   ├── __init__.py
│   │   └── live_source.py        # DOMAIN VIOLATION
│   ├── risk_manager.py
│   └── safety.py
├── data/
│   ├── __init__.py
│   ├── backend_protocol.py
│   ├── historical_data_store.py
│   ├── historical_maintenance.py
│   ├── historical_queries.py
│   ├── historical_sync.py
│   ├── market_data.py
│   ├── realtime_bootstrap.py
│   ├── realtime_models.py
│   ├── realtime_state.py
│   └── sessions.py
├── exchanges/
│   ├── __init__.py
│   ├── bybit_account.py
│   ├── bybit_client.py
│   ├── bybit_market.py
│   ├── bybit_trading.py
│   └── bybit_websocket.py
├── forge/
│   ├── __init__.py
│   ├── audits/
│   │   ├── __init__.py
│   │   ├── artifact_parity_verifier.py
│   │   ├── audit_fibonacci.py
│   │   ├── audit_in_memory_parity.py
│   │   ├── audit_incremental_registry.py
│   │   ├── audit_incremental_state.py
│   │   ├── audit_math_parity.py
│   │   ├── audit_play_value_flow.py
│   │   ├── audit_primitives.py
│   │   ├── audit_rollup_parity.py
│   │   ├── audit_rolling_window.py
│   │   ├── audit_snapshot_plumbing_parity.py
│   │   ├── audit_trend_detector.py
│   │   ├── audit_zone_detector.py
│   │   ├── stress_test_suite.py
│   │   └── toolkit_contract_audit.py
│   ├── blocks/
│   │   ├── __init__.py
│   │   ├── block.py
│   │   └── normalizer.py
│   ├── functional/
│   │   ├── __init__.py
│   │   ├── coverage.py
│   │   ├── date_range_finder.py
│   │   ├── engine_validator.py
│   │   ├── generator.py
│   │   ├── runner.py
│   │   ├── syntax_coverage.py
│   │   └── syntax_generator.py
│   ├── generation/
│   │   ├── __init__.py
│   │   ├── generate_100_setups.py
│   │   ├── generate_100_setups_part2.py
│   │   └── indicator_stress_test.py
│   ├── plays/
│   │   ├── __init__.py
│   │   └── normalizer.py
│   ├── setups/                    # DEPRECATED
│   │   ├── __init__.py
│   │   └── setup.py
│   ├── synthetic/
│   │   ├── __init__.py
│   │   ├── cases/
│   │   │   ├── __init__.py
│   │   │   ├── test_arithmetic.py
│   │   │   ├── test_harness.py
│   │   │   ├── test_integration.py
│   │   │   ├── test_operators.py
│   │   │   ├── test_orders.py
│   │   │   ├── test_price_features.py
│   │   │   ├── test_structures.py
│   │   │   └── test_timeframe_windows.py
│   │   ├── conftest.py
│   │   ├── generators/            # EMPTY - DELETE
│   │   │   └── __init__.py
│   │   └── harness/
│   │       ├── __init__.py
│   │       └── harness.py
│   ├── systems/
│   │   ├── __init__.py
│   │   ├── normalizer.py
│   │   └── system.py
│   └── validation/
│       ├── __init__.py
│       ├── batch_runner.py
│       ├── fixtures.py
│       ├── play_validator.py
│       ├── report.py
│       ├── synthetic_data.py
│       ├── synthetic_provider.py
│       ├── test_runner.py
│       ├── tier0_syntax/
│       │   ├── __init__.py
│       │   └── test_parse.py
│       ├── tier1_operators/
│       │   ├── __init__.py
│       │   ├── test_anchor_tf.py
│       │   ├── test_boolean.py
│       │   ├── test_comparison.py
│       │   ├── test_crossover.py
│       │   ├── test_duration.py
│       │   ├── test_range.py
│       │   ├── test_set_ops.py
│       │   ├── test_window.py
│       │   └── test_window_duration.py
│       └── tier2_structures/
│           ├── __init__.py
│           ├── test_derived_zone.py
│           ├── test_fibonacci.py
│           ├── test_rolling.py
│           ├── test_swing.py
│           ├── test_trend.py
│           └── test_zone.py
├── risk/
│   ├── __init__.py
│   └── global_risk.py
├── tools/
│   ├── __init__.py
│   ├── account_tools.py
│   ├── backtest_audit_tools.py
│   ├── backtest_cli_wrapper.py
│   ├── backtest_play_tools.py
│   ├── backtest_tools.py
│   ├── data_tools.py
│   ├── data_tools_common.py
│   ├── data_tools_query.py
│   ├── data_tools_status.py
│   ├── data_tools_sync.py
│   ├── diagnostics_tools.py
│   ├── forge_stress_test_tools.py
│   ├── market_data_tools.py
│   ├── order_tools.py
│   ├── order_tools_common.py
│   ├── position_tools.py
│   ├── shared.py
│   ├── specs/
│   │   ├── __init__.py
│   │   ├── account_specs.py
│   │   ├── backtest_specs.py
│   │   ├── data_specs.py
│   │   ├── market_specs.py
│   │   ├── orders_specs.py
│   │   ├── positions_specs.py
│   │   ├── shared_params.py
│   │   └── system_specs.py
│   └── tool_registry.py
├── utils/
│   ├── __init__.py
│   ├── cli_display.py
│   ├── datetime_utils.py
│   ├── debug.py
│   ├── epoch_tracking.py          # DEAD CODE - DELETE
│   ├── helpers.py
│   ├── log_context.py
│   ├── logger.py
│   ├── rate_limiter.py
│   └── time_range.py
└── viz/
    ├── __init__.py
    ├── api/
    │   ├── __init__.py
    │   ├── charts.py
    │   ├── equity.py
    │   ├── indicators.py
    │   ├── metrics.py
    │   ├── runs.py
    │   └── trades.py
    ├── data/
    │   ├── __init__.py
    │   ├── artifact_loader.py
    │   ├── equity_loader.py
    │   ├── indicator_loader.py
    │   ├── ohlcv_loader.py
    │   ├── play_loader.py
    │   ├── timestamp_utils.py
    │   └── trades_loader.py
    ├── models/
    │   ├── __init__.py
    │   └── run_metadata.py
    ├── renderers/
    │   ├── __init__.py
    │   ├── indicators.py
    │   └── structures.py
    ├── schemas/
    │   ├── __init__.py
    │   └── artifact_schema.py
    └── server.py
```

---

**END OF CODEBASE ANALYSIS**
