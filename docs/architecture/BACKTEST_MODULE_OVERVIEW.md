# Backtest Engine Module Overview

**Last Updated:** December 13, 2025  
**Status:** Refactor complete (Phases 0–5)

---

## Overview

The backtest module provides deterministic historical simulation using a **Bybit-aligned accounting model**. It supports single symbol, single timeframe backtests with config-only window switching, canonical `Bar.ts_open/ts_close`, `RuntimeSnapshot` strategy input, and MTF/HTF caching.

---

## Terminology

| Term | Definition |
|------|------------|
| **StrategyFamily** | Python implementation of trading logic (e.g., `ema_rsi_atr`) |
| **StrategyInstance** | One configured use of a StrategyFamily within a System |
| **System** | A configured trading robot with 1..N StrategyInstances + risk profile + windows |
| **Run** | A single backtest execution of a System over a window |
| **system_id** | Human-readable config name |
| **system_uid** | Deterministic hash of resolved config (for lineage) |
| **run_id** | Unique execution identifier |

---

## Module Structure

```
src/backtest/
├── engine.py               # Main backtest runner with warm-up handling
├── system_config.py        # YAML loader + RiskProfileConfig
├── indicators.py           # EMA/RSI/ATR (no look-ahead)
├── metrics.py              # Performance metrics
├── proof_metrics.py        # Proof-grade metrics (V2)
├── proof_metrics_types.py # Proof metrics type definitions
├── risk_policy.py          # none vs rules selector
├── simulated_risk_manager.py # Risk-based position sizing
├── window_presets.py       # Symbol-agnostic window definitions
├── types.py                # Core dataclasses (Bar, Trade, etc.) - Bar is canonical with ts_open/ts_close
└── sim/                    # Modular simulated exchange
    ├── exchange.py         # Thin orchestrator (~200 LOC)
    ├── types.py            # Exchange types (Bar, Order, Position, Fill)
    ├── ledger.py           # USDT accounting with invariants
    ├── pricing/            # Price models (mark, last, mid, spread, intrabar)
    │   ├── price_model.py
    │   ├── spread_model.py
    │   └── intrabar_path.py
    ├── execution/          # Order execution models
    │   ├── execution_model.py
    │   ├── slippage_model.py
    │   ├── liquidity_model.py
    │   └── impact_model.py
    ├── funding/            # Funding rate application
    │   └── funding_model.py
    ├── liquidation/        # Mark-based liquidation
    │   └── liquidation_model.py
    ├── metrics/            # Exchange-side metrics
    │   └── metrics.py
    ├── constraints/        # Tick/lot/min_notional validation
    │   └── constraints.py
    └── adapters/           # Data conversion helpers
        ├── ohlcv_adapter.py
        └── funding_adapter.py
```

---

## System Config (YAML)

```yaml
system_id: SOLUSDT_5m_ema_rsi_atr_pure
symbol: SOLUSDT
tf: 5m

strategies:
  - strategy_instance_id: entry
    strategy_id: ema_rsi_atr
    strategy_version: "1.0.0"
    inputs:
      symbol: SOLUSDT
      tf: 5m
    params:
      ema_fast_period: 9
      ema_slow_period: 21
      rsi_period: 14
      rsi_overbought: 70
      rsi_oversold: 30
      atr_period: 14
      atr_sl_multiplier: 1.5
      atr_tp_multiplier: 2.0
    role: entry

primary_strategy_instance_id: entry

windows:
  hygiene:
    start: "2024-09-01"
    end: "2024-10-31"
  test:
    start: "2024-11-01"
    end: "2024-11-30"

risk_profile:
  initial_equity: 1000.0
  max_leverage: 10.0
  min_trade_usd: 1.0
  stop_equity_usd: 0.0
  taker_fee_rate: 0.0006           # 0.06%
  maintenance_margin_rate: 0.005   # 0.5%
  include_est_close_fee_in_entry_gate: false

risk_mode: "none"  # or "rules"

data_build:
  env: live
  period: 3M
  tfs: [1m, 5m, 15m, 1h, 4h, 1d]
```

---

## RiskProfileConfig Fields

```python
@dataclass
class RiskProfileConfig:
    # Core
    initial_equity: float = 1000.0
    sizing_model: str = "percent_equity"
    risk_per_trade_pct: float = 1.0
    max_leverage: float = 2.0
    min_trade_usd: float = 1.0
    stop_equity_usd: float = 0.0
    
    # Margin model (Bybit-aligned)
    _initial_margin_rate: Optional[float] = None  # Default: 1/max_leverage
    maintenance_margin_rate: float = 0.005
    mark_price_source: str = "close"
    
    # Fee model
    taker_fee_rate: float = 0.0006
    maker_fee_rate: Optional[float] = None
    fee_mode: str = "taker_only"
    
    # Entry gate
    include_est_close_fee_in_entry_gate: bool = False
```

---

## SimulatedExchange Architecture

### Modular Design

The `SimulatedExchange` is a **thin orchestrator** (~200 LOC) that coordinates specialized modules:

1. **Pricing Module** (`sim/pricing/`): Derives mark/last/mid prices, spread, intrabar path
2. **Execution Module** (`sim/execution/`): Handles order fills with slippage, liquidity, impact models
3. **Ledger Module** (`sim/ledger.py`): Maintains USDT accounting with invariants
4. **Funding Module** (`sim/funding/`): Applies funding rate events
5. **Liquidation Module** (`sim/liquidation/`): Checks and executes liquidations
6. **Metrics Module** (`sim/metrics/`): Tracks exchange-side metrics
7. **Constraints Module** (`sim/constraints/`): Validates tick size, lot size, min notional
8. **Adapters** (`sim/adapters/`): Converts DuckDB data to exchange types

### State Variables (USD-named)

```python
exchange.cash_balance_usd      # Realized cash (initial + PnL - fees)
exchange.unrealized_pnl_usd    # Current mark-to-market unrealized PnL
exchange.equity_usd            # = cash_balance_usd + unrealized_pnl_usd
exchange.used_margin_usd       # Position IM = position_value × IMR
exchange.free_margin_usd       # = equity_usd - used_margin_usd
exchange.available_balance_usd # = max(0, free_margin_usd)
```

**Note:** The exchange orchestrator delegates all complex logic to specialized modules, keeping the main class focused on coordination.

### Core Formulas

| Concept | Formula |
|---------|---------|
| Initial Margin (IM) | `position_value × IMR` |
| IMR | `1 / leverage` |
| Maintenance Margin | `position_value × MMR` |
| Equity | `cash_balance + unrealized_pnl` |
| Free Margin | `equity - used_margin` |
| Available Balance | `max(0, free_margin)` |

### Entry Gate (Active Order IM)

```
Required = Position IM + Est Open Fee [+ Est Close Fee]

Where:
  Position IM   = notional × IMR
  Est Open Fee  = notional × taker_fee_rate
  Est Close Fee = notional × taker_fee_rate  (if include_est_close_fee=True)
```

### Stop Conditions

| Condition | Trigger | Action |
|-----------|---------|--------|
| `account_blown` | `equity_usd <= stop_equity_usd` | Cancel orders, force-close, halt |
| `insufficient_free_margin` | `available_balance_usd < min_trade_usd` | Cancel orders, force-close, halt |

---

## Artifact Layout

```
data/backtests/{system_id}/{symbol}/{tf}/{window_name}/{run_id}/
├── result.json         # BacktestResult contract
├── trades.csv          # Trade list
├── equity.csv          # Equity curve
├── account_curve.csv   # Proof-grade account state per bar
├── run_manifest.json   # Run metadata + git + config echo
└── events.jsonl        # Event log (equity + fills + stop)
```

Example:
```
data/backtests/SOLUSDT_5m_ema_rsi_atr_pure/SOLUSDT/5m/hygiene/run-20241220_143052/
```

---

## BacktestResult Contract

```python
@dataclass
class BacktestResult:
    # Identity
    run_id: str
    system_id: str
    system_uid: str
    
    # Strategy
    primary_strategy_instance_id: str
    strategy_id: str
    strategy_version: str
    strategies: List[StrategyInstanceSummary]
    
    # Context
    symbol: str
    tf: str
    window_name: str
    risk_mode: str
    
    # Metrics
    metrics: BacktestMetrics
    
    # Timestamps
    start_ts: datetime
    end_ts: datetime
    started_at: datetime
    finished_at: datetime
    
    # Warm-up metadata
    warmup_bars: int
    simulation_start_ts: datetime
    
    # Data
    trades: List[Trade]
    equity_curve: List[EquityPoint]
    
    # Early stop
    stopped_early: bool = False
    stop_reason: Optional[str] = None
    stop_ts: Optional[datetime] = None
    stop_bar_index: Optional[int] = None
    stop_details: Optional[Dict[str, Any]] = None
```

---

## Running a Backtest

### Via CLI

```bash
python trade_cli.py
# Select Backtest menu → Run Backtest → Select system → Select window
```

### Via Tools

```python
from src.tools.backtest_tools import backtest_run_tool

result = backtest_run_tool(
    system_id="SOLUSDT_5m_ema_rsi_atr_pure",
    window_name="hygiene",
    write_artifacts=True,
)

if result.success:
    metrics = result.data["metrics"]
    print(f"Trades: {metrics['total_trades']}")
    print(f"Net PnL: ${metrics['net_profit']:.2f}")
    print(f"Win Rate: {metrics['win_rate']:.1f}%")
```

### Via Smoke Test

```bash
python trade_cli.py --smoke backtest
```

---

## Strategy Registration

```python
from src.strategies.registry import register_strategy, get_strategy

# Registration
register_strategy(
    strategy_id="ema_rsi_atr",
    strategy_version="1.0.0",
    strategy_fn=my_strategy_function,
    description="EMA crossover with RSI filter",
)

# Lookup
strategy = get_strategy("ema_rsi_atr", "1.0.0")
```

---

## Accounting Invariants (Always True)

```python
# Verified every bar:
assert equity_usd == cash_balance_usd + unrealized_pnl_usd
assert free_margin_usd == equity_usd - used_margin_usd
assert available_balance_usd == max(0.0, free_margin_usd)
assert used_margin_usd == position_value * initial_margin_rate
```

---

## Key Files

| File | Purpose |
|------|---------|
| `src/backtest/engine.py` | Main backtest runner |
| `src/backtest/sim/exchange.py` | Exchange orchestrator |
| `src/backtest/sim/ledger.py` | USDT accounting |
| `src/backtest/sim/pricing/` | Price models (mark, spread, intrabar) |
| `src/backtest/sim/execution/` | Order execution (slippage, liquidity, impact) |
| `src/backtest/sim/funding/` | Funding rate application |
| `src/backtest/sim/liquidation/` | Liquidation checks |
| `src/backtest/system_config.py` | Config loader + RiskProfileConfig |
| `src/backtest/indicators.py` | EMA/RSI/ATR (no look-ahead) |
| `src/backtest/metrics.py` | Performance calculation |
| `src/backtest/proof_metrics.py` | Proof-grade metrics (V2) |
| `src/tools/backtest_tools.py` | Public API surface |
| `src/strategies/configs/*.yml` | System configs |

---

## Execution Model

**Bar-by-bar simulation:**
1. Strategy evaluates at bar close
2. Entry orders fill at next bar open (with slippage)
3. TP/SL checked against bar OHLC with deterministic tie-break
4. Exit orders fill at trigger price (with slippage)

**Tool-calling pipeline (in `process_bar`):**
1. `pricing`: `get_prices(bar)` → `PriceSnapshot`
2. `funding`: `apply_events(events, prev_ts, ts)` → `FundingResult`
3. `execution`: `fill_orders(orders, bar)` → `FillResult`
4. `ledger`: `update(fills, funding, prices)` → `LedgerUpdate`
5. `liquidation`: `check(ledger_state, prices)` → `LiquidationResult`
6. `metrics`: `record(step_result)` → `MetricsUpdate`

## Detailed Documentation

For comprehensive details, see:
- `docs/architecture/SIMULATED_EXCHANGE.md` — Full accounting model & modular architecture
- `docs/architecture/SYSTEM_REVIEW.md` — Complete technical overview
