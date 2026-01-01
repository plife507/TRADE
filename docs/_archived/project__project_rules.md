# TRADE — Project Rules

**Last Updated:** December 13, 2025

## Core Principles

1. **Safety First**: All orders go through risk manager. Demo mode by default.
2. **Modular Always**: Each component has a single responsibility.
3. **Tools as API**: All operations go through `src/tools/*` with `ToolRegistry`.
4. **No Hardcoding**: Symbols, sizes, paths from config.
5. **Bybit-Aligned**: Follow Bybit accounting rules for margin/fees.

---

## Trading Mode / API Mapping

| TRADING_MODE | BYBIT_USE_DEMO | Result |
|--------------|----------------|--------|
| `paper` | `true` | ✅ Demo account (fake funds) |
| `real` | `false` | ✅ Live account (real funds) |
| `paper` | `false` | ❌ BLOCKED |
| `real` | `true` | ❌ BLOCKED |

**Key Points:**
- Both modes execute real orders on Bybit (demo vs live account)
- Invalid combinations are hard errors that block startup
- Data API (historical) **always** uses LIVE API for accuracy

**Strict API Key Contract (No Fallbacks):**
- `BYBIT_DEMO_API_KEY` → Required for DEMO mode trading
- `BYBIT_LIVE_API_KEY` → Required for LIVE mode trading
- `BYBIT_LIVE_DATA_API_KEY` → Required for all data operations
- Generic keys are **NOT used** — no fallbacks allowed

---

## Code Organization

### Module Boundaries

| Location | Purpose |
|----------|---------|
| `src/exchanges/` | Exchange API clients only |
| `src/core/` | Core trading logic (exchange manager, risk, safety) |
| `src/backtest/` | Backtest engine (deterministic simulation) |
| `src/data/` | Market data, historical storage, realtime state |
| `src/tools/` | Public API surface for CLI/agents |
| `src/strategies/` | Base classes + system configs |
| `src/utils/` | Logging, rate limiting, helpers |

### File Size Limits

- Keep files under 1500 lines
- Split if larger

---

## Backtest Rules

### Hot Loop Invariant

- **No pandas in the bar loop** — only array reads and small logic
- pandas allowed in prep phase only (data loading, indicator computation)

### Refactor Invariant

- **Must pass contract + math parity audits before merge**
- Contract audit: identical output keys
- Math parity audit: identical values + NaN masks within tolerance
- Market structure features must follow the same registry, normalization, and audit model as technical indicators.

### Accounting Model (Bybit-Aligned)

The SimulatedExchange follows Bybit's isolated margin model:

```python
# These invariants are verified every bar:
assert equity_usd == cash_balance_usd + unrealized_pnl_usd
assert free_margin_usd == equity_usd - used_margin_usd
assert available_balance_usd == max(0.0, free_margin_usd)
assert used_margin_usd == position_value * initial_margin_rate
```

### Configuration via YAML

All backtest parameters come from system config YAML:
- `risk_profile` — equity, leverage, fees, stop conditions
- `windows` — hygiene/test date ranges
- `params` — strategy parameters

Never hardcode in engine code.

### Stop Conditions

| Condition | Trigger |
|-----------|---------|
| `account_blown` | `equity_usd <= stop_equity_usd` |
| `insufficient_free_margin` | `available_balance_usd < min_trade_usd` |

### Artifact Storage Format (Phase 3+)

Backtest artifacts use Parquet for tabular data:

| File | Format | Description |
|------|--------|-------------|
| `trades.parquet` | Parquet | Trade records |
| `equity.parquet` | Parquet | Equity curve |
| `account_curve.parquet` | Parquet | Margin state per bar |
| `result.json` | JSON | Summary metrics |
| `pipeline_signature.json` | JSON | Pipeline provenance |

- Parquet uses pyarrow engine with snappy compression
- Legacy CSV files may exist in older runs (backward-compat read supported)
- See `docs/architecture/ARTIFACT_STORAGE_FORMAT.md` for details

---

## Coding Standards

### All Tools Return ToolResult

```python
from src.tools.shared import ToolResult

def my_tool(param: str) -> ToolResult:
    try:
        return ToolResult(success=True, message="Done", data={"key": "value"})
    except Exception as e:
        return ToolResult(success=False, error=str(e))
```

### No Direct Bybit Calls from CLI

```python
# BAD
from src.exchanges.bybit_client import BybitClient
client = BybitClient()

# GOOD
from src.tools import list_open_positions_tool
result = list_open_positions_tool()
```

### Use Config for Everything

```python
# BAD
leverage = 5
symbol = "BTCUSDT"

# GOOD
from src.config.config import get_config
config = get_config()
leverage = config.risk.max_leverage
```

### Use RiskProfileConfig for Backtest

```python
# BAD (hardcoded in engine)
taker_fee = 0.0006
leverage = 10

# GOOD (from config)
fee_rate = risk_profile.taker_fee_rate
leverage = risk_profile.leverage
```

---

## Safety Rules

1. **Demo First**: Always test on demo API before live
2. **Risk Limits**: Never bypass risk manager
3. **Panic Available**: Panic button must always work
4. **Log Everything**: Every order, every error
5. **Real Interface Testing**: Test through CLI, not just unit tests

---

## Validation Rules (HARD RULE)

**CLI is the ONLY validation interface. No pytest files.**

### What This Means

- **NO `tests/test_*.py` files** — they do not exist in this codebase
- **ALL validation** runs through CLI commands
- **NO synthetic unit tests** for backtest/data/indicator behavior

### CLI Validation Commands

```bash
# Preflight check (data coverage, env routing)
python trade_cli.py backtest preflight --idea-card SOLUSDT_15m_ema_crossover --data-env live

# Indicator key discovery
python trade_cli.py backtest indicators --idea-card SOLUSDT_15m_ema_crossover --print-keys

# Smoke backtest (full pipeline validation)
python trade_cli.py backtest run --idea-card SOLUSDT_15m_ema_crossover --smoke --strict

# Full smoke test (data + trading)
python trade_cli.py --smoke full

# Data extensive test
python trade_cli.py --smoke data_extensive
```

### Why CLI-Only

1. **Real interface validation** — Tests what users actually use
2. **No synthetic data** — Uses real DuckDB data, real IdeaCards
3. **Actionable output** — CLI returns fix commands on failure
4. **JSON for CI** — `--json` flag for automated pipelines
5. **Single source of truth** — No test/prod behavior divergence

---

## Tool Registry

The `ToolRegistry` (`src/tools/tool_registry.py`) provides:
- Dynamic tool discovery and execution
- AI/LLM function calling format
- Batch execution
- Category-based filtering

```python
from src.tools.tool_registry import ToolRegistry

registry = ToolRegistry()
result = registry.execute("market_buy", symbol="BTCUSDT", usd_amount=100)
```

---

## Argument Passing

### Avoid Duplicate Arguments

```python
# BAD - Passes symbol twice
result = run_tool_action("data.sync", sync_tool, symbol, symbols=symbol)

# GOOD - Clear positional or keyword args
result = run_tool_action("data.sync", sync_tool, symbol, env=data_env)
```

### CLI Override Pattern

```python
# GOOD - CLI overrides flow through resolve_risk_profile
merged = resolve_risk_profile(
    base=config.risk_profile,
    overrides={"max_leverage": 20.0}
)
```

---

## Adding New Features

Before adding a new function/tool/wrapper:

1. Check if existing code already does what you need
2. Prefer reusing existing abstractions
3. Keep the call chain shallow
4. Ensure wrapper adds clear value (validation, transformation)
5. Update documentation

---

## Markdown Editing

When editing markdown files:
- Use `search_replace` for targeted edits
- Don't rewrite entire files unnecessarily
- If full rewrite needed, ask user first

---

## Reference Documentation

**Always reference before implementing:**
- Bybit API: `reference/exchanges/bybit/docs/v5/`
- pybit SDK: `reference/exchanges/pybit/`

Never guess API parameters, endpoints, or behavior.
