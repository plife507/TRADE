# TRADE

**Algorithmic Trading Bot for Bybit Futures with AI-Agent Composable Strategies**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Bybit API](https://img.shields.io/badge/Exchange-Bybit-orange.svg)](https://www.bybit.com/)

A production-grade backtesting and live trading platform for **USDT-margined perpetual futures**. Strategies are defined as composable YAML configurations with built-in leverage controls, liquidation modeling, and comprehensive risk metrics.

---

## Why TRADE?

| Problem | TRADE Solution |
|---------|----------------|
| Strategies are scattered code | **Strategies are YAML data** - version controlled, diffable, AI-generatable |
| Backtests ignore leverage reality | **Full margin simulation** - liquidation, maintenance margin, funding rates |
| Risk metrics are an afterthought | **62-field metrics** - VaR, CVaR, Sharpe, Sortino, MAE/MFE, tail risk |
| Hard to compose strategies | **3-level hierarchy** - Blocks → Plays → Systems |
| Complex DSL learning curve | **TradingView-aligned operators** - `cross_above`, `cross_below` work as expected |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         THE FORGE                               │
│              Strategy Development & Validation                  │
│                                                                 │
│    Blocks (atomic)  →  Plays (complete)  →  Systems (blended)  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BACKTEST ENGINE                            │
│                                                                 │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐               │
│   │ Indicators │  │ Structures │  │ Actions DSL│               │
│   │    (43)    │  │    (6)     │  │  (v3.0.0)  │               │
│   └────────────┘  └────────────┘  └────────────┘               │
│                                                                 │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │              Simulated Exchange                         │  │
│   │  ┌──────────┐ ┌──────────┐ ┌────────────┐ ┌──────────┐ │  │
│   │  │ Pricing  │ │Execution │ │ Margin &   │ │ Funding  │ │  │
│   │  │  Model   │ │  Model   │ │Liquidation │ │  Rates   │ │  │
│   │  └──────────┘ └──────────┘ └────────────┘ └──────────┘ │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│   62-field metrics · O(1) hot loop · Multi-timeframe           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       LIVE ENGINE                               │
│                   Bybit Futures (USDT-M)                        │
│              Demo Mode (safe) · Live Mode (real)                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Leverage & Margin Model

TRADE simulates **isolated margin** mode with realistic leverage mechanics:

### Account Configuration

```yaml
account:
  starting_equity_usdt: 10000
  max_leverage: 10                    # Hard cap on leverage
  margin_mode: isolated_usdt          # Only isolated supported
  maintenance_margin_rate: 0.005      # 0.5% MMR (Bybit default)
  fee_model:
    taker_bps: 5.5                    # 0.055% taker fee
    maker_bps: 2.0                    # 0.02% maker fee
  slippage_bps: 5                     # 0.05% slippage model
```

### How Margin Works

| Concept | Description |
|---------|-------------|
| **Initial Margin** | `position_value / leverage` - capital locked when opening |
| **Maintenance Margin** | `position_value × MMR` - minimum equity to avoid liquidation |
| **Equity** | `cash + unrealized_pnl` - real-time account value |
| **Liquidation** | Triggered when `equity <= maintenance_margin` |

### Leverage Example

```
Account: $10,000 USDT
Leverage: 10x
Position: 1 BTC @ $50,000

Position Value:  $50,000
Initial Margin:  $5,000 (50,000 / 10)
Maint. Margin:   $250   (50,000 × 0.5%)
Free Margin:     $5,000 (10,000 - 5,000)

Liquidation Price (Long): ~$45,250 (when equity = maint. margin)
```

### Funding Rate Simulation

Perpetual futures have 8-hour funding payments:

```yaml
# Tracked in backtest metrics
total_funding_paid_usdt: 127.50      # Paid when long in positive funding
total_funding_received_usdt: 84.20   # Received when short in positive funding
net_funding_usdt: -43.30             # Net impact on PnL
```

---

## Risk Management

### Position Sizing Models

```yaml
risk:
  sizing:
    model: percent_equity    # Size based on equity percentage
    value: 5.0               # Risk 5% of equity per trade
    max_leverage: 10         # Never exceed 10x
```

| Model | Description |
|-------|-------------|
| `percent_equity` | Position = `equity × value%` |
| `fixed_usdt` | Fixed size regardless of equity |
| `risk_based` | Size based on stop distance: `risk_amount / stop_distance` |

### Stop Loss Types

```yaml
risk:
  stop_loss:
    type: atr_multiple       # Dynamic stop based on ATR
    value: 2.0               # 2× ATR distance
    atr_feature_id: atr_14   # Reference to ATR indicator
    buffer_pct: 0.1          # 0.1% buffer beyond level
```

| Type | Description |
|------|-------------|
| `percent` | Fixed percentage from entry |
| `atr_multiple` | Dynamic: `entry ± (ATR × multiplier)` |
| `structure` | Based on swing high/low levels |
| `fixed_points` | Absolute price distance |

### Take Profit Types

```yaml
risk:
  take_profit:
    type: rr_ratio           # Risk:Reward based
    value: 2.0               # 2:1 reward to risk
```

| Type | Description |
|------|-------------|
| `rr_ratio` | Target = `entry + (stop_distance × ratio)` |
| `percent` | Fixed percentage from entry |
| `atr_multiple` | Dynamic: `entry ± (ATR × multiplier)` |
| `fixed_points` | Absolute price distance |

### Exit Modes

```yaml
exit_mode: first_hit  # Which exit triggers position close
```

| Mode | Behavior |
|------|----------|
| `sl_tp_only` | Only SL/TP close positions - pure mechanical |
| `signal` | Only signal-based exits - SL/TP are emergency only |
| `first_hit` | Whichever triggers first wins |

---

## Backtest Metrics (62 Fields)

### Core Performance

| Metric | Description |
|--------|-------------|
| `net_profit` | Final equity - starting equity |
| `net_return_pct` | Percentage return |
| `benchmark_return_pct` | Buy-and-hold return (same period) |
| `alpha_pct` | Strategy return - benchmark return |

### Risk-Adjusted Returns

| Metric | Description |
|--------|-------------|
| `sharpe` | Risk-adjusted return (annualized) |
| `sortino` | Downside-only risk adjustment |
| `calmar` | Return / Max Drawdown |
| `omega_ratio` | Probability-weighted gain/loss ratio |

### Drawdown Analysis

| Metric | Description |
|--------|-------------|
| `max_drawdown_pct` | Worst peak-to-trough decline |
| `max_drawdown_duration_bars` | Longest time underwater |
| `ulcer_index` | Pain-adjusted drawdown measure |
| `recovery_factor` | Net profit / max drawdown |

### Tail Risk (Critical for Leverage)

| Metric | Description |
|--------|-------------|
| `var_95_pct` | 95% Value at Risk - worst 5% daily loss |
| `cvar_95_pct` | Expected Shortfall - avg loss beyond VaR |
| `skewness` | Return asymmetry (negative = blowup risk) |
| `kurtosis` | Fat tails measure (>3 = extreme moves) |

### Leverage-Specific Metrics

| Metric | Description |
|--------|-------------|
| `avg_leverage_used` | Average actual leverage during backtest |
| `max_gross_exposure_pct` | Peak position_value / equity |
| `closest_liquidation_pct` | How close you got to liquidation |
| `margin_calls` | Number of margin warning events |
| `min_margin_ratio` | Lowest margin ratio observed |

### Trade Quality (MAE/MFE)

| Metric | Description |
|--------|-------------|
| `mae_avg_pct` | Avg Maximum Adverse Excursion - worst drawdown per trade |
| `mfe_avg_pct` | Avg Maximum Favorable Excursion - best unrealized profit |
| `payoff_ratio` | Average win / average loss |
| `expectancy_usdt` | Expected $ per trade |

---

## Example Play (Complete)

```yaml
# strategies/plays/T_001_ema_crossover.yml
version: "3.0.0"
id: T_001_ema_crossover

symbol: BTCUSDT
tf: "15m"

# Account & Leverage
account:
  starting_equity_usdt: 10000
  max_leverage: 10
  margin_mode: isolated_usdt
  fee_model:
    taker_bps: 5.5
    maker_bps: 2.0
  slippage_bps: 5

# Indicators
features:
  ema_9:
    indicator: ema
    params: { length: 9 }
  ema_21:
    indicator: ema
    params: { length: 21 }
  atr_14:
    indicator: atr
    params: { length: 14 }

# Entry/Exit Logic (Actions DSL)
actions:
  entry_long:
    all:
      - [ema_9, cross_above, ema_21]

  exit_long:
    all:
      - [ema_9, cross_below, ema_21]

# Risk Model
risk:
  stop_loss:
    type: atr_multiple
    value: 2.0
    atr_feature_id: atr_14

  take_profit:
    type: rr_ratio
    value: 2.0

  sizing:
    model: percent_equity
    value: 5.0
    max_leverage: 10

exit_mode: first_hit
```

Run it:
```bash
python trade_cli.py backtest run --play T_001_ema_crossover \
  --start 2025-01-01 --end 2025-06-30
```

---

## Quick Start

```bash
# Clone
git clone https://github.com/plife507/TRADE.git
cd TRADE

# Setup
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/Mac
pip install -r requirements.txt

# Configure (optional - for live trading)
cp env.example api_keys.env
# Edit api_keys.env with your Bybit API keys

# Run
python trade_cli.py          # Interactive CLI
```

---

## DSL Features

The Actions DSL provides TradingView-aligned operators:

### Comparison & Crossover
```yaml
- [ema_9, cross_above, ema_21]      # prev <= rhs AND curr > rhs
- [ema_9, cross_below, ema_21]      # prev >= rhs AND curr < rhs
- [rsi_14, gt, 70]                   # Greater than
- [close, near_pct, support, 1.5]   # Within 1.5% of level
```

### Window Operators
```yaml
# Condition held for N bars
holds_for:
  bars: 3
  anchor_tf: "1h"
  expr: [rsi_14, gt, 50]

# Event occurred within window
occurred_within:
  bars: 10
  expr: [ema_9, cross_above, ema_21]
```

### Structure Access (O(1) Market Structure)
```yaml
- [{feature_id: swing, field: high_level}, gt, 0]
- [{feature_id: trend, field: direction}, eq, 1]
- [{feature_id: fib_zones, field: any_active}, eq, true]
```

---

## Trading Hierarchy

| Level | Purpose | Location |
|:-----:|---------|----------|
| **Block** | Atomic reusable condition | `strategies/blocks/` |
| **Play** | Complete strategy with risk model | `strategies/plays/` |
| **System** | Multiple plays with regime blending | `strategies/systems/` |

---

## Current Status

| Component | Status | Details |
|-----------|:------:|---------|
| Backtest Engine | ✅ | 62-field metrics, deterministic execution |
| Margin & Liquidation | ✅ | Isolated margin, mark-based liquidation |
| Funding Rates | ✅ | 8-hour funding simulation |
| Indicators | ✅ | 43 registered (EMA, RSI, MACD, Bollinger, etc.) |
| Structures | ✅ | 6 types (Swing, Trend, Fibonacci, Zone, Rolling, Derived) |
| DSL v3.0.0 | ✅ | 11 operators, 6 window operators, frozen spec |
| The Forge | ✅ | Validation, audits, 320+ stress tests |
| Live Trading | ✅ | Bybit API, demo + live modes |

---

## Key Commands

```bash
# Run backtest
python trade_cli.py backtest run --play T_001 --start 2025-01-01 --end 2025-06-30

# Validate a Play
python trade_cli.py backtest play-normalize --play T_001_ema_crossover

# Batch validate all Plays
python trade_cli.py backtest play-normalize-batch --dir strategies/plays/

# Run audit suite
python trade_cli.py backtest audit-toolkit

# Smoke tests
python trade_cli.py --smoke full     # Full system test (demo mode)
python trade_cli.py --smoke data     # Data pipeline only
```

---

## Project Structure

```
TRADE/
├── src/
│   ├── backtest/           # Backtest engine
│   │   ├── sim/            # Simulated exchange (margin, liquidation)
│   │   ├── play/           # Play config, risk model
│   │   └── incremental/    # O(1) structure detection
│   ├── forge/              # Strategy validation
│   ├── core/               # Live trading engine
│   ├── exchanges/          # Bybit API client
│   └── data/               # DuckDB market data
├── strategies/
│   ├── blocks/             # Atomic conditions
│   ├── plays/              # Complete strategies
│   └── systems/            # Multi-play configs
├── tests/
│   ├── validation/         # DSL validation (V_100+)
│   └── stress/             # Structure stress tests (320+)
└── docs/
    ├── guides/             # Usage guides
    ├── specs/              # DSL specification
    └── architecture/       # Design documents
```

---

## Documentation

| Topic | Location |
|-------|----------|
| Engine Concepts | [`docs/guides/BACKTEST_ENGINE_CONCEPTS.md`](docs/guides/BACKTEST_ENGINE_CONCEPTS.md) |
| DSL Cookbook | [`docs/specs/PLAY_DSL_COOKBOOK.md`](docs/specs/PLAY_DSL_COOKBOOK.md) |
| Strategy Patterns | [`docs/guides/DSL_STRATEGY_PATTERNS.md`](docs/guides/DSL_STRATEGY_PATTERNS.md) |
| Code Examples | [`docs/guides/CODE_EXAMPLES.md`](docs/guides/CODE_EXAMPLES.md) |
| AI Guidance | [`CLAUDE.md`](CLAUDE.md) |

---

## Trading Modes

| Mode | Endpoint | Funds | Use Case |
|------|----------|:-----:|----------|
| **Demo** | api-demo.bybit.com | Fake | Development, testing |
| **Live** | api.bybit.com | Real | Production |

Always start with Demo mode. The system defaults to safe settings.

---

## Philosophy

### All Forward, No Legacy
No backward compatibility. Delete old code, update all callers.

### Strategies Are Data
YAML-defined, version controlled, AI-generatable.

### Fail Loud
Invalid configurations raise errors immediately. No silent defaults.

### Hash Everything
Every computation produces a hash. Determinism is verified.

---

## License

MIT License - See [LICENSE](LICENSE) file
