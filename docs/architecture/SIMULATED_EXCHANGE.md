# Simulated Exchange — Bybit-Aligned Accounting Model

## Overview

The `SimulatedExchange` is the core component for deterministic backtesting. It simulates a **Bybit linear perpetual (USDT-settled), isolated-margin** trading environment with:

- **Modular architecture**: Thin orchestrator (~200 LOC) coordinating specialized modules
- **One net position per symbol** (single-position model)
- **Mark-to-market** each bar using configurable mark source (default: `bar.close`)
- **Explicit accounting state** with USDT-named properties (using `_usd` suffix for backward compatibility)
- **Configurable entry gate** modeling Bybit's "Active Order IM"

## Currency Model: USDT-Only

This simulator version supports **USDT-quoted linear perpetuals only**:

| Constraint | This Version | Future |
|------------|--------------|--------|
| **Quote Currency** | USDT only | USDC, USD (coming) |
| **Margin Mode** | Isolated only | Cross margin (coming) |
| **Position Mode** | One-way only | Hedge mode (coming) |
| **Instrument Type** | Linear perp only | Inverse, spot (coming) |

**Currency Naming Convention**:
- All monetary values are in **USDT** (quote currency)
- Variable names use `_usd` suffix for backward compatibility (e.g., `equity_usd`, `cash_balance_usd`)
- 1 USDT ≈ 1 USD, but we explicitly use USDT as the quote currency

**Validation**: Symbol and mode locks are validated at:
1. Config load (`load_system_config()`)
2. Engine init (`BacktestEngine.__init__()`)
3. Before data fetch (`prepare_backtest_frame()`)
4. Exchange init (`SimulatedExchange.__init__()`)

## Modular Architecture

The exchange uses a **tool-calling pattern** where the main orchestrator delegates to specialized modules:

### Module Structure

```
src/backtest/sim/
├── exchange.py         # Thin orchestrator (~200 LOC)
├── types.py            # Core types (Bar, Order, Position, Fill, etc.)
├── ledger.py           # USDT accounting with invariants
├── pricing/            # Price derivation models
│   ├── price_model.py  # Mark/last/mid price calculation
│   ├── spread_model.py # Bid-ask spread modeling
│   └── intrabar_path.py # Intrabar price path for TP/SL
├── execution/          # Order execution models
│   ├── execution_model.py # Main execution orchestrator
│   ├── slippage_model.py  # Slippage calculation
│   ├── liquidity_model.py # Liquidity constraints
│   └── impact_model.py    # Market impact modeling
├── funding/            # Funding rate application
│   └── funding_model.py
├── liquidation/        # Mark-based liquidation
│   └── liquidation_model.py
├── metrics/            # Exchange-side metrics
│   └── metrics.py
├── constraints/        # Order validation
│   └── constraints.py  # Tick size, lot size, min notional
└── adapters/           # Data conversion
    ├── ohlcv_adapter.py
    └── funding_adapter.py
```

### Execution Pipeline

Each bar is processed through this pipeline:

```python
# In exchange.process_bar()
1. pricing.get_prices(bar) → PriceSnapshot
2. funding.apply_events(events, prev_ts, ts) → FundingResult
3. execution.fill_orders(orders, bar) → FillResult
4. ledger.update(fills, funding, prices) → LedgerUpdate
5. liquidation.check(ledger_state, prices) → LiquidationResult
6. metrics.record(step_result) → MetricsUpdate
```

### Design Principles

- **Separation of concerns**: Each module handles one aspect
- **Deterministic**: All modules produce deterministic outputs
- **Testable**: Modules can be tested independently
- **Extensible**: New models can be added without changing orchestrator

---

## Bybit Accounting Model (MVP)

### Key Formulas

| Concept | Formula | Bybit Reference |
|---------|---------|-----------------|
| **Initial Margin (IM)** | `position_value × IMR` | `positionIM` in position.mdx |
| **IMR (Initial Margin Rate)** | `1 / leverage` | risk-limit.mdx |
| **Maintenance Margin (MM)** | `position_value × MMR` | `positionMM` in position.mdx |
| **Equity** | `cash_balance + unrealized_pnl` | wallet-balance.mdx |
| **Free Margin** | `equity - used_margin` | Can be negative |
| **Available Balance** | `max(0, free_margin)` | wallet-balance.mdx |

### Stop Conditions

| Condition | Trigger | What Happens |
|-----------|---------|--------------|
| `account_blown` | `equity_usd <= stop_equity_usd` | Cancel orders, force-close position, halt |
| `insufficient_free_margin` | `available_balance_usd < min_trade_usd` | Cancel orders, force-close position, halt |

---

## Exchange State Properties

All state is explicit and always available for debugging:

```python
# Explicit USD-named properties (Bybit-aligned)
exchange.cash_balance_usd      # Realized cash (initial + realized PnL - fees)
exchange.unrealized_pnl_usd    # Current mark-to-market unrealized PnL
exchange.equity_usd            # = cash_balance_usd + unrealized_pnl_usd
exchange.used_margin_usd       # Position IM = position_value × IMR
exchange.free_margin_usd       # = equity_usd - used_margin_usd (can be negative)
exchange.available_balance_usd # = max(0, free_margin_usd)

# Configuration echo
exchange.leverage              # Effective leverage
exchange.initial_margin_rate   # IMR = 1 / leverage
exchange.taker_fee_rate        # Fee rate for taker orders
exchange.mark_price_source     # "close" (engine guardrail: currently close-only)

# Legacy aliases (for API compatibility)
exchange.equity                # Same as equity_usd
exchange.available_balance     # Same as available_balance_usd
exchange.initial_margin        # Same as used_margin_usd
```

---

## Configuration

### RiskProfileConfig Fields

```python
from src.backtest.system_config import RiskProfileConfig

risk_profile = RiskProfileConfig(
    # Core
    initial_equity=1000.0,           # Starting capital
    sizing_model="percent_equity",   # How to size trades
    risk_per_trade_pct=1.0,          # Risk % per trade
    max_leverage=10.0,               # Max leverage (determines IMR)
    min_trade_usd=1.0,               # Min trade size (stop trigger)
    stop_equity_usd=0.0,             # Equity floor (stop trigger)
    
    # Margin model (Bybit-aligned)
    # _initial_margin_rate=None,     # Optional: explicit IMR (default: 1/max_leverage)
    maintenance_margin_rate=0.005,   # MMR (0.5% = Bybit lowest tier)
    mark_price_source="close",       # Mark proxy (engine guardrail: currently close-only)
    
    # Fee model
    taker_fee_rate=0.0006,           # 0.06% (Bybit typical)
    maker_fee_rate=None,             # Optional (for future use)
    fee_mode="taker_only",           # MVP: only taker fees
    
    # Entry gate behavior
    include_est_close_fee_in_entry_gate=False,  # Include close fee in entry gate
)
```

### YAML Config Example

```yaml
# src/strategies/configs/BTCUSDT_5m_trend.yml
system_id: "BTCUSDT_5m_trend"
symbol: "BTCUSDT"
tf: "5m"

risk_profile:
  initial_equity: 10000.0
  max_leverage: 20.0
  min_trade_usd: 10.0
  stop_equity_usd: 100.0              # Stop if equity falls to $100
  maintenance_margin_rate: 0.004      # 0.4% MMR
  taker_fee_rate: 0.00055             # 0.055% (VIP rate)
  include_est_close_fee_in_entry_gate: true

strategies:
  - strategy_instance_id: "entry"
    strategy_id: "ema_crossover"
    strategy_version: "1.0.0"
    params:
      ema_fast: 9
      ema_slow: 21

primary_strategy_instance_id: "entry"

windows:
  hygiene:
    preset: "hygiene_1M"
  test:
    preset: "test_1M"
```

---

## Entry Gate Logic (Active Order IM)

When filling an order, the exchange checks if there's enough capital using the **Active Order IM** concept:

```
Required = Position IM + Estimated Open Fee [+ Estimated Close Fee]

Position IM     = notional × IMR = notional / leverage
Est Open Fee    = notional × taker_fee_rate
Est Close Fee   = notional × taker_fee_rate  (if include_est_close_fee_in_entry_gate=True)
```

### Example Calculation

```python
# Config
leverage = 10.0           # IMR = 0.1
taker_fee_rate = 0.0006   # 0.06%
include_est_close_fee = True

# Order
notional = 500.0  # $500 position

# Calculate required capital
position_im = 500.0 * 0.1       # = $50.00
est_open_fee = 500.0 * 0.0006   # = $0.30
est_close_fee = 500.0 * 0.0006  # = $0.30

required = 50.0 + 0.30 + 0.30   # = $50.60

# Entry allowed if: available_balance_usd >= $50.60
```

### Code Path

```python
# In SimulatedExchange._fill_pending_order()

# Calculate Position IM (margin required to hold position)
position_im = order.size_usd * self._initial_margin_rate

# Calculate estimated open fee
est_open_fee = order.size_usd * self._taker_fee_rate

# Calculate estimated close fee (optional)
est_close_fee = 0.0
if self._include_est_close_fee:
    est_close_fee = order.size_usd * self._taker_fee_rate

# Total required for entry
required_for_entry = position_im + est_open_fee + est_close_fee

# Check available balance
if self._available_balance_usd < required_for_entry:
    self.last_fill_rejected = True
    return
```

---

## Bar-by-Bar Processing

### Execution Model

1. **Strategy evaluates at bar close** → generates Signal
2. **Entry orders fill at next bar open** (with slippage)
3. **TP/SL checked within each bar** (deterministic tie-break)
4. **Balances updated** at bar close (mark-to-market)

### Deterministic Tie-Break

If both TP and SL would be hit in the same bar:
- **Longs**: SL checked first (assume price goes down then up)
- **Shorts**: SL checked first (assume price goes up then down)

This is conservative—we assume the worst-case scenario.

### Code Flow

```python
# In engine.run()
for i in range(len(df)):
    # Create canonical Bar with ts_open/ts_close
    bar = Bar(
        symbol="BTCUSDT",
        tf="5m",
        ts_open=row["timestamp"],  # Bar open time
        ts_close=row["timestamp"] + tf_duration("5m"),  # Bar close time
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        volume=row["volume"],
    )
    
    # 1. Process bar (fills, TP/SL checks, balance updates)
    step_result = exchange.process_bar(bar, prev_bar)
    closed_trades = exchange.last_closed_trades
    
    # 2. Check stop conditions
    if exchange.equity_usd <= risk_profile.stop_equity_usd:
        stop_reason = "account_blown"
        break
    
    if exchange.available_balance_usd < risk_profile.min_trade_usd:
        stop_reason = "insufficient_free_margin"
        break
    
    # 3. Strategy evaluation (at bar close - ts_close)
    signal = strategy(snapshot, params)
    
    # 4. Submit order if signal
    if signal:
        exchange.submit_order(side, size_usd, stop_loss, take_profit)
    
    prev_bar = bar
```

---

## Fee Application

Fees are applied at two points:

| Event | Fee Basis | Applied To |
|-------|-----------|------------|
| **Entry** | `entry_notional × taker_fee_rate` | Deducted from `cash_balance_usd` |
| **Exit** | `exit_notional × taker_fee_rate` | Deducted from realized PnL |

### Example Trade

```python
# Entry
entry_price = 100.0
entry_notional = 500.0
entry_fee = 500.0 * 0.0006  # = $0.30
# cash_balance_usd reduced by $0.30

# Exit (price moved to $110)
exit_price = 110.0
position_size = 5.0  # units (500/100)
exit_notional = 5.0 * 110.0  # = $550
exit_fee = 550.0 * 0.0006  # = $0.33

# PnL calculation
gross_pnl = (110.0 - 100.0) * 5.0  # = $50.00
net_pnl = 50.0 - 0.33  # = $49.67

# Total fees for trade
total_fees = 0.30 + 0.33  # = $0.63
```

---

## Creating the Exchange

### Direct Instantiation (Testing)

```python
from src.backtest.sim import SimulatedExchange, ExecutionConfig
from src.backtest.sim.adapters import adapt_ohlcv_row_canonical
from src.backtest.system_config import RiskProfileConfig

# Create risk profile
risk_profile = RiskProfileConfig(
    initial_equity=1000.0,
    max_leverage=10.0,
    taker_fee_rate=0.0006,
    include_est_close_fee_in_entry_gate=True,
)

# Create execution config (for slippage)
exec_config = ExecutionConfig(
    taker_fee_bps=6.0,   # Ignored, overridden by risk_profile
    slippage_bps=5.0,    # 0.05% slippage
)

# Create exchange
exchange = SimulatedExchange(
    symbol="BTCUSDT",
    initial_capital=1000.0,
    execution_config=exec_config,
    risk_profile=risk_profile,
)
```

### Via BacktestEngine (Production)

```python
from src.backtest.idea_card import load_idea_card
from src.backtest.runner import IdeaCardEngineWrapper

# Load IdeaCard (includes account config)
idea_card = load_idea_card("BTCUSDT_15m_mtf_tradeproof")

# Engine wrapper creates exchange internally
wrapper = IdeaCardEngineWrapper()
result = wrapper.run(
    idea_card=idea_card,
    symbol="BTCUSDT",
    start="2024-01-01",
    end="2024-12-31",
)
```
<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>
read_file

---

## Working with Positions

### Submit Order

```python
# Submit a long order for $500
# Order is submitted at bar close (ts_close), fills at next bar open (ts_open)
order_id = exchange.submit_order(
    side="long",
    size_usd=500.0,
    stop_loss=95.0,      # Optional SL price
    take_profit=110.0,   # Optional TP price
    timestamp=bar.ts_close,  # Decision made at bar close
)
```

### Process Bar (Fill + TP/SL)

```python
from src.backtest.types import Bar
from src.backtest.runtime.timeframe import tf_duration
from datetime import datetime

# Create canonical Bar with explicit ts_open/ts_close
ts_open = datetime(2024, 1, 1, 12, 0)
bar = Bar(
    symbol="BTCUSDT",
    tf="5m",
    ts_open=ts_open,  # Bar open time
    ts_close=ts_open + tf_duration("5m"),  # Bar close time
    open=100.0,
    high=102.0,
    low=98.0,
    close=101.0,
    volume=1000.0,
)

# Process bar: fills pending orders, checks TP/SL, updates balances
# Fills occur at ts_open, MTM updates at ts_close
step_result = exchange.process_bar(bar, prev_bar)
closed_trades = exchange.last_closed_trades

for trade in closed_trades:
    print(f"Closed: {trade.side} @ {trade.exit_price}, PnL: ${trade.net_pnl:.2f}")
```

### Force Close

```python
# Force close at current price (e.g., end of backtest or early stop)
from datetime import datetime
trade = exchange.force_close_position(
    price=current_price,
    timestamp=datetime.now(),  # Exit timestamp
    reason="end_of_data",  # or "account_blown", "insufficient_free_margin"
)
```

---

## Debugging: Get State

```python
state = exchange.get_state()

# Returns dict with all state:
{
    # USD-named state
    "cash_balance_usd": 999.70,
    "unrealized_pnl_usd": 25.00,
    "equity_usd": 1024.70,
    "used_margin_usd": 50.00,
    "free_margin_usd": 974.70,
    "available_balance_usd": 974.70,
    
    # Config echo
    "leverage": 10.0,
    "initial_margin_rate": 0.1,
    "maintenance_margin_rate": 0.005,
    "taker_fee_rate": 0.0006,
    "include_est_close_fee": True,
    "mark_price_source": "close",
    
    # Position info
    "has_position": True,
    "position_side": "long",
    "position_size_usd": 500.0,
    
    # Other
    "is_liquidatable": False,
    "total_trades": 3,
    "total_fees_paid": 1.89,
    "last_fill_rejected": False,
}
```

---

## Stop Details (Artifacts)

When a stop condition triggers, the engine captures detailed metadata:

```python
# In BacktestResult.stop_details
{
    # Config echo (for reproducibility)
    "stop_equity_usd": 0.0,
    "min_trade_usd": 1.0,
    "initial_margin_rate": 0.1,
    "maintenance_margin_rate": 0.005,
    "taker_fee_rate": 0.0006,
    "mark_price_source": "close",
    "include_est_close_fee_in_entry_gate": False,
    
    # USD-named state at stop
    "cash_balance_usd": 45.20,
    "unrealized_pnl_usd": -48.50,
    "equity_usd": -3.30,
    "used_margin_usd": 0.0,
    "free_margin_usd": -3.30,
    "available_balance_usd": 0.0,
    
    # Legacy aliases
    "equity": -3.30,
    "initial_margin": 0.0,
    "maintenance_margin": 0.0,
    "free_margin": -3.30,
    "available_balance": 0.0,
    "leverage": 10.0,
}
```

---

## Accounting Invariants (Always True)

These identities are verified every bar:

```python
# Identity 1: Equity = Cash + Unrealized PnL
assert equity_usd == cash_balance_usd + unrealized_pnl_usd

# Identity 2: Free Margin = Equity - Used Margin
assert free_margin_usd == equity_usd - used_margin_usd

# Identity 3: Available Balance is clamped
assert available_balance_usd == max(0.0, free_margin_usd)

# Identity 4: Used Margin = Position Value × IMR
if position:
    position_value = position.size * mark_price
    assert used_margin_usd == position_value * initial_margin_rate
```

---

## Complete Example: Backtest with Stop Condition

```python
from src.backtest.engine import BacktestEngine
from src.backtest.system_config import load_system_config, resolve_risk_profile
from src.backtest.runtime.types import RuntimeSnapshot
from src.core.risk_manager import Signal

def my_strategy(snapshot: RuntimeSnapshot, params: dict) -> Signal | None:
    """Simple EMA crossover strategy."""
    # Extract features from RuntimeSnapshot
    features = snapshot.features_ltf.features
    ema_fast = features.get("ema_fast")
    ema_slow = features.get("ema_slow")
    
    if ema_fast is None or ema_slow is None:
        return None
    
    # Entry signals
    if snapshot.exchange_state.position is None:
        if ema_fast > ema_slow:
            return Signal(
                symbol=snapshot.symbol,
                direction="LONG",
                metadata={"stop_loss": snapshot.bar_ltf.close * 0.98}
            )
        elif ema_fast < ema_slow:
            return Signal(
                symbol=snapshot.symbol,
                direction="SHORT",
                metadata={"stop_loss": snapshot.bar_ltf.close * 1.02}
            )
    
    return None

# Load config with custom risk overrides
config = load_system_config("BTCUSDT_5m_trend", "test")

# Override risk settings for this run
config.risk_profile = resolve_risk_profile(
    config.risk_profile,
    overrides={
        "initial_equity": 500.0,       # Start with $500
        "max_leverage": 20.0,          # 20x leverage
        "stop_equity_usd": 50.0,       # Stop if equity hits $50
        "taker_fee_rate": 0.0004,      # Lower fees
    }
)

# Run backtest
engine = BacktestEngine(config, "test")
result = engine.run(my_strategy)

# Check results
print(f"Stopped early: {result.stopped_early}")
print(f"Stop reason: {result.stop_reason}")
print(f"Final equity: ${result.metrics.final_equity:.2f}")
print(f"Total trades: {result.metrics.total_trades}")

if result.stop_details:
    print(f"Stop details: {result.stop_details}")
```

---

## Summary

| Component | Purpose |
|-----------|---------|
| `RiskProfileConfig` | All margin/fee/stop configuration |
| `SimulatedExchange` | Trade execution + accounting state |
| `BacktestEngine` | Orchestrates bar-by-bar simulation |
| `stop_details` | Captures full state at stop for debugging |

The system is designed to be:
- **Deterministic**: Same inputs → same outputs
- **Debuggable**: Full state available at any point
- **Bybit-aligned**: Uses real exchange margin formulas
- **Configurable**: All parameters externalized to YAML

