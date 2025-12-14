# Backtest Engine Integration Guide

**Last Updated:** December 14, 2025

This guide shows how to integrate with the backtest engine using IdeaCard configurations.

---

## Quick Start

### Run a Backtest via Tools

```python
from src.tools.backtest_tools import backtest_run_idea_card_tool

result = backtest_run_idea_card_tool(
    idea_card_id="SOLUSDT_15m_mtf_tradeproof",
    start="2024-01-01",
    end="2024-12-31",
    write_artifacts=True,
)

if result.success:
    metrics = result.data["metrics"]
    print(f"Trades: {metrics['total_trades']}")
    print(f"Net PnL: ${metrics['net_profit']:.2f}")
    print(f"Win Rate: {metrics['win_rate']:.1f}%")
    print(f"Sharpe: {metrics['sharpe']:.2f}")
```

### Run via CLI

```bash
python trade_cli.py backtest run --idea-card SOLUSDT_15m_mtf_tradeproof --start 2024-01-01 --end 2024-12-31
```

---

## IdeaCard Configuration

### Create an IdeaCard YAML

File: `configs/idea_cards/my_strategy.yml`

```yaml
id: my_strategy
version: "1.0.0"
name: "My Trading Strategy"
description: "EMA crossover with RSI filter"

symbol_universe:
  - BTCUSDT

tf_configs:
  exec:
    timeframe: "1h"
    feature_specs:
      - indicator_type: ema
        output_key: ema_fast
        params:
          length: 9
      - indicator_type: ema
        output_key: ema_slow
        params:
          length: 21
      - indicator_type: rsi
        output_key: rsi
        params:
          length: 14
      - indicator_type: atr
        output_key: atr
        params:
          length: 14

account:
  starting_equity_usdt: 10000.0
  max_leverage: 10.0
  fee_model:
    taker_fee_rate: 0.0006
  slippage_bps: 5

position_policy:
  direction: long_short

signal_rules:
  entry_rules:
    - condition: exec_ema_fast > exec_ema_slow
    - condition: exec_rsi < 70
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
  sizing:
    model: percent_equity
    value: 1.0
```

### Account Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `starting_equity_usdt` | Yes | Starting capital in USDT |
| `max_leverage` | Yes | Maximum leverage |
| `fee_model.taker_fee_rate` | Yes | Taker fee rate (default: 0.0006) |
| `slippage_bps` | No | Slippage in basis points (default: 5) |

---

## Direct Engine Usage

### Run Backtest with IdeaCard

```python
from src.backtest.idea_card import load_idea_card
from src.backtest.runner import IdeaCardEngineWrapper
from pathlib import Path

# Load IdeaCard
idea_card = load_idea_card("my_strategy")

# Create engine wrapper
wrapper = IdeaCardEngineWrapper()

# Run backtest
result = wrapper.run(
    idea_card=idea_card,
    symbol="BTCUSDT",
    start="2024-01-01",
    end="2024-12-31",
    run_dir=Path("data/backtests/my_strategy"),
)

# Access results
print(f"Stopped early: {result.stopped_early}")
print(f"Stop reason: {result.stop_reason}")
print(f"Final equity: ${result.metrics.final_equity:.2f}")
```

---

## Epoch Tracking Integration

### Using run_epoch Wrapper

```python
from src.utils.epoch_tracking import run_epoch, StrategyEpoch

def my_backtest(symbol: str, timeframe: str, start: str, end: str) -> dict:
    """Your backtest implementation."""
    # Run backtest via tools
    from src.tools.backtest_tools import backtest_run_idea_card_tool
    
    result = backtest_run_idea_card_tool(
        idea_card_id="my_strategy",
        symbol=symbol,
        start=start,
        end=end,
    )
    
    if result.success:
        return result.data["metrics"]
    else:
        return {"error": result.error}

result = run_epoch(
    epoch=StrategyEpoch.BACKTEST,
    symbol="BTCUSDT",
    strategy_id="my-strategy",
    runner_fn=my_backtest,
    timeframes=["1h"],
    promotion_criteria=lambda m: m.get("sharpe", 0) > 1.5,
    next_epoch=StrategyEpoch.DEMO,
    timeframe="1h",
    start="2024-01-01",
    end="2024-06-30",
)

print(f"Run ID: {result['run_id']}")
print(f"Passed: {result['passed']}")
```

### Manual Tracking

```python
from src.utils.epoch_tracking import StrategyEpochTracker, StrategyEpoch

tracker = StrategyEpochTracker("my-strategy", "My Strategy")

run_id = tracker.epoch_start(
    epoch=StrategyEpoch.BACKTEST,
    symbol="BTCUSDT",
    timeframes=["1h"],
)

try:
    # Run your backtest
    from src.tools.backtest_tools import backtest_run_idea_card_tool
    result = backtest_run_idea_card_tool(
        idea_card_id="my_strategy",
        start="2024-01-01",
        end="2024-12-31",
    )
    metrics = result.data["metrics"] if result.success else {}
    
    tracker.epoch_complete(
        run_id=run_id,
        epoch=StrategyEpoch.BACKTEST,
        symbol="BTCUSDT",
        metrics=metrics,
        passed=metrics.get("sharpe", 0) > 1.5,
    )
except Exception as e:
    tracker.epoch_complete(
        run_id=run_id,
        epoch=StrategyEpoch.BACKTEST,
        symbol="BTCUSDT",
        metrics={"error": str(e)},
        passed=False,
    )
```

---

## Artifact Output

### Directory Structure

```
data/backtests/{system_id}/{symbol}/{tf}/{window}/{run_id}/
├── result.json         # Full BacktestResult (contract)
├── trades.csv          # Trade list
├── equity.csv          # Equity curve
├── account_curve.csv   # Proof-grade account state per bar
├── run_manifest.json   # Run metadata + git + config echo
└── events.jsonl        # Event log (equity + fills + stop)
```

### result.json Contents

```json
{
  "run_id": "run-abc123",
  "system_id": "my_system",
  "system_uid": "hash123",
  "symbol": "BTCUSDT",
  "tf": "1h",
  "window_name": "hygiene",
  "risk_mode": "none",
  "metrics": {
    "total_trades": 45,
    "win_rate": 62.5,
    "net_profit": 1250.50,
    "sharpe": 1.85,
    "max_drawdown_abs": 125.00,
    "max_drawdown_pct": -5.2
  },
  "stopped_early": false,
  "stop_reason": null,
  "stop_details": null
}
```

### trades.csv Columns

| Column | Description |
|--------|-------------|
| `trade_id` | Unique trade identifier |
| `symbol` | Trading symbol |
| `side` | LONG or SHORT |
| `entry_time` | Entry timestamp |
| `exit_time` | Exit timestamp |
| `entry_price` | Entry price |
| `exit_price` | Exit price |
| `qty` | Position size (base units) |
| `pnl` | Net PnL |
| `pnl_pct` | PnL as percentage |

---

## Stop Details

When a stop condition triggers, `stop_details` captures full state:

```python
stop_details = {
    # Config echo
    "stop_equity_usd": 0.0,
    "min_trade_usd": 1.0,
    "initial_margin_rate": 0.1,
    "maintenance_margin_rate": 0.005,
    "taker_fee_rate": 0.0006,
    "mark_price_source": "close",
    
    # State at stop (USD-named)
    "cash_balance_usd": 45.20,
    "unrealized_pnl_usd": -48.50,
    "equity_usd": -3.30,
    "used_margin_usd": 0.0,
    "free_margin_usd": -3.30,
    "available_balance_usd": 0.0,
    
    # Legacy aliases
    "equity": -3.30,
    "leverage": 10.0,
}
```

---

## Promotion Criteria Examples

```python
def backtest_to_demo(metrics: dict) -> bool:
    """Promote to demo if passes these checks."""
    return (
        metrics.get("sharpe", 0) > 1.5 and
        metrics.get("win_rate", 0) > 55.0 and
        metrics.get("total_trades", 0) >= 30 and
        metrics.get("max_drawdown_pct", 0) > -15.0
    )

def demo_to_live(metrics: dict) -> bool:
    """Promote to live if profitable in demo."""
    return (
        metrics.get("total_trades", 0) >= 10 and
        metrics.get("win_rate", 0) > 50.0 and
        metrics.get("net_profit", 0) > 0
    )
```

---

## Metrics Dictionary

The backtest engine returns these metrics:

```python
metrics = {
    # Equity
    "initial_equity": float,
    "final_equity": float,
    "net_profit": float,
    "net_return_pct": float,

    # Drawdown
    "max_drawdown_abs": float,
    "max_drawdown_pct": float,
    "max_drawdown_duration_bars": int,

    # Trades
    "total_trades": int,
    "win_rate": float,  # 0-100 percentage
    "avg_trade_return_pct": float,
    "profit_factor": float,

    # Risk-adjusted
    "sharpe": float,

    # Counts / totals
    "win_count": int,
    "loss_count": int,
    "gross_profit": float,
    "gross_loss": float,
    "total_fees": float,
}
```

---

## Next Steps

1. Create your IdeaCard YAML in `configs/idea_cards/`
2. Validate IdeaCard: `python trade_cli.py backtest idea-card-normalize --idea-card <ID>`
3. Check indicators: `python trade_cli.py backtest indicators --idea-card <ID> --print-keys`
4. Run preflight: `python trade_cli.py backtest preflight --idea-card <ID>`
5. Run backtest via tools or CLI
6. Review artifacts in `backtests/`

---

## Related Documentation

- `docs/architecture/SIMULATED_EXCHANGE.md` — Full accounting model
- `docs/architecture/BACKTEST_MODULE_OVERVIEW.md` — Module structure
- `docs/examples/epoch_experiment_tracking_example.py` — Tracking examples
