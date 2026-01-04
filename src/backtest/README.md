# Backtest Module (`src/backtest/`)

Production backtest framework for TRADE. This module is the **only supported path** for running backtests.

---

## Canonical Pipeline

```
IdeaCard(YAML)
    ↓
validate_idea_card_full()
    ↓
compute_warmup_requirements()
    ↓
FeatureFrameBuilder.build()
    ↓
FeedStores (numpy arrays, O(1) access)
    ↓
RuntimeSnapshotView
    ↓
BacktestEngine.run()
    ↓
SimulatedExchange
    ↓
Artifacts (preflight_report.json, result.json, trades.csv, equity.csv)
```

---

## IdeaCard Location

**Canonical path**: `configs/plays/`

- Production IdeaCards live in `configs/plays/*.yml`
- `src/strategies/plays/` is for examples/templates only
- Override with `--idea-dir` flag if loading from alternate location

---

## Entrypoints to Import

### Runner (Primary Interface)

```python
from src.backtest.runner import run_backtest_with_gates, RunnerConfig, RunnerResult
```

### IdeaCard Loading

```python
from src.backtest.play import load_idea_card, list_plays, IdeaCard
```

### Validation

```python
from src.backtest.execution_validation import (
    validate_idea_card_full,
    compute_warmup_requirements,
    compute_idea_card_hash,
)
```

### Features

```python
from src.backtest.features import FeatureSpec, FeatureFrameBuilder, IndicatorRegistry
```

---

## Module Ownership (One Owner Per Concern)

| Module | Responsibility |
|--------|----------------|
| `idea_card.py` | IdeaCard schema + loader + list |
| `execution_validation.py` | Gate 8.x (hash, contract, features, warmup, pre-eval) |
| `features/` | FeatureSpec + Registry + FeatureFrameBuilder |
| `runtime/` | FeedStores + Cache + SnapshotView + Preflight gate |
| `sim/` | SimulatedExchange (fills, margin, liquidation, accounting) |
| `engine.py` | Deterministic engine orchestration (hot-loop) |
| `artifacts/` | Artifact standards + writers + validators |
| `runner.py` | Single entrypoint: `run_backtest_with_gates()` |

---

## Hot-Loop Contract

The engine hot-loop (`engine.py`) has strict performance requirements:

1. **No DataFrame operations** — All indicator computation is vectorized BEFORE the loop
2. **O(1) snapshot access** — Use FeedStores with numpy arrays, not pandas
3. **Closed-candle only** — Strategy evaluates at `bar.ts_close`, never mid-bar
4. **HTF/MTF forward-fill** — Between closes, last-closed values carry forward unchanged
5. **No PriceModel calls** — Exchange computes mark_price once; snapshot reads it

---

## Indicators

**Available Indicators:**
- **Currently implemented**: 8 indicators (EMA, SMA, RSI, ATR, MACD, BBANDS, STOCH, STOCHRSI)
- **Available from pandas_ta**: 189 indicators total
- **Reference**: See `reference/pandas_ta/INDICATORS_REFERENCE.md` for complete list

To add new indicators, add an entry to the `SUPPORTED_INDICATORS` dict in `indicator_registry.py`.

## CLI Usage

```bash
python -m src.backtest.runner \
    --idea SOLUSDT_15m_ema_crossover \
    --start 2024-01-01 \
    --end 2024-03-01 \
    --env live \
    --export-root backtests/
```

---

## Artifact Standards

All backtest runs produce:

| File | Required | Contents |
|------|----------|----------|
| `preflight_report.json` | Yes | Data validation results, tool calls made |
| `result.json` | Yes | Idea hash, run_id, resolved idea path, pipeline version |
| `trades.csv` | Yes | Entry/exit times, prices, PnL, SL/TP levels |
| `equity.csv` | Yes | Timestamp, equity, drawdown |
| `events.jsonl` | Optional | Detailed event log for debugging |

Export path format:
```
backtests/{idea_id}/{symbol}/{tf_exec}/{start}_{end}_{run_id}/
```

---

## Data Tool Discipline (Phase 7.5)

- Backtest/sim code MUST NOT write to DuckDB directly
- Missing data/gap healing MUST call `src/tools/data_tools.py` with explicit params
- This ensures data repairs are tool-driven and auditable

