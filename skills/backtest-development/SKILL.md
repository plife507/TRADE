---
name: backtest-development
description: Guides TRADE backtest engine development. Use when implementing engine features, fixing sim bugs, or adding indicators/structures.
---

# Backtest Development Skill

Domain knowledge for developing the TRADE backtest engine.

## Architecture Overview

```
BacktestEngine
├── prepare_backtest_frame()  # Data loading, FeedStore creation
├── run()                     # Main execution loop
│   ├── 1m evaluation sub-loop
│   ├── Snapshot creation
│   ├── Signal evaluation
│   └── Exchange step
└── Artifact generation
```

## Key Abstractions

### FeedStore
- Time-series container for OHLCV + indicators
- O(1) array access via index
- `_get_ts_close_ms_at(idx)` for timestamps

### RuntimeSnapshotView
- Read-only view over cached data
- O(1) access to current bar values
- History access via offsets

### SimulatedExchange
- Order execution with slippage
- Position management
- TP/SL via intrabar path

### Play
- YAML strategy configuration (v3.0.0+)
- Features (indicators), structures, actions
- Validation through normalization

## Engine Flow

```
Play YAML → load_play() → Play dataclass
                               ↓
                 create_engine_from_play() → BacktestEngine
                                                   ↓
                                            prepare_backtest_frame()
                                                   ↓
                                   run_engine_with_play() → BacktestResult
```

## Multi-Timeframe Forward-Fill

### Timeframe Roles

| Role | Typical Values | Purpose |
|------|----------------|---------|
| **LTF/exec** | 1m, 5m, 15m | Execution timing |
| **MTF** | 30m, 1h, 2h, 4h | Trade bias |
| **HTF** | 6h, 8h, 12h, 1D | Higher-level trend |

**Rule**: Any TF slower than exec forward-fills until its bar closes.

```
exec bars (15m):  |  1  |  2  |  3  |  4  |
HTF bars (1h):    |       HTF bar 0        |
                  └── HTF values unchanged ─┘
```

## INDICATOR_REGISTRY (42 Total)

Adding indicators:

1. Add to `src/backtest/indicator_registry.py`:
```python
"new_indicator": IndicatorSpec(
    type="new_indicator",
    default_params={"period": 14},
    output_keys=["value"],
    required_columns=["close"],
),
```

2. Create validation Play in `configs/plays/_validation/I_XXX_name.yml`
3. Run `backtest audit-toolkit`

## STRUCTURE_REGISTRY (6 Total)

| Type | Outputs | Depends On |
|------|---------|------------|
| `swing` | `high_level`, `low_level`, `high_idx`, `low_idx` | None |
| `fibonacci` | `level_0.382`, `level_0.5`, `level_0.618` | `swing` |
| `zone` | `state`, `upper`, `lower` | `swing` |
| `trend` | `direction`, `strength`, `bars_in_trend` | `swing` |
| `rolling_window` | `value` | None |
| `derived_zone` | K slots + aggregates | `swing` |

### Adding Structures

1. Create detector in `src/backtest/incremental/detectors/`:
```python
from src.backtest.incremental.registry import register_structure
from src.backtest.incremental.base import BaseIncrementalDetector

@register_structure("my_structure")
class MyDetector(BaseIncrementalDetector):
    REQUIRED_PARAMS = {"param1": int}
    OPTIONAL_PARAMS = {"param2": (float, 1.0)}
    DEPENDS_ON = []  # or ["swing"]

    def update(self, bar_idx: int, bar: dict) -> None:
        # O(1) update logic
        pass

    def get_output_keys(self) -> list[str]:
        return ["output1", "output2"]

    def get_value(self, key: str) -> float | None:
        return self._values.get(key)
```

2. Create validation Play in `configs/plays/_validation/S_XXX_name.yml`
3. Run structure smoke test

### Derived Zones (Phase 12)

K slots + aggregates pattern for Fibonacci zones from swing pivots:

**Slot Fields** (per zone 0 to K-1):
- `zone{N}_lower`, `zone{N}_upper` (FLOAT)
- `zone{N}_state` (ENUM: NONE/ACTIVE/BROKEN)
- `zone{N}_touched_this_bar`, `zone{N}_inside` (BOOL)

**Aggregates**:
- `active_count`, `any_active`, `any_touched` (INT/BOOL)
- `closest_active_lower`, `closest_active_upper` (FLOAT)

See: `docs/specs/DERIVATION_RULE_INVESTIGATION.md`

## Hot Loop Rules

**CRITICAL**: Engine hot loop must be O(1) per bar.

- Direct array access, not binary search
- Use pre-computed indices
- No DataFrame operations
- No allocations in loop body

```python
# CORRECT - O(1) access
value = self._feed_store.get_value_at(indicator_key, idx)

# WRONG - O(n) search
value = df[df['ts_close'] == ts]['ema_20'].iloc[0]
```

## Common Pitfalls

| Pitfall | Description | Fix |
|---------|-------------|-----|
| **Lookahead** | Using bar[i+1] data at bar[i] | Snapshot asserts ts alignment |
| **Off-by-one** | Wrong warmup/start index | Use `get_warmup_requirement()` |
| **Quote lookup** | Binary search in hot loop | Use direct index access |
| **Fee basis** | Wrong size field for fees | Always use `size_usdt` |
| **TF forward-fill** | Expecting HTF to update each bar | HTF updates only on close |

## The Forge Integration

The **Forge** (`src/forge/`) is where strategies are developed and validated before production use.

### Development Flow

```
1. Create Play in configs/plays/
2. Run normalize: backtest play-normalize-batch
3. Validate: backtest audit-toolkit
4. Backtest: backtest run --play <id>
5. Promote to production use
```

### Key Forge Components

| Component | Purpose |
|-----------|---------|
| `normalize_play_strict()` | Validate Play schema |
| `audit_toolkit` | Registry consistency |
| `audit_rollup` | 1m price aggregation parity |
| `audit_math_parity` | Indicator math vs pandas_ta |
| Stress Test Suite | Full pipeline validation |

See: `src/forge/CLAUDE.md`

## Metrics (62 Fields)

BacktestMetrics includes:
- Core: `total_trades`, `win_rate`, `profit_factor`, `net_pnl`
- Risk: `max_drawdown`, `sharpe`, `sortino`, `calmar`
- Tail: `VaR`, `CVaR`, `skewness`, `kurtosis`
- Trade: `MAE`, `MFE`, `edge_ratio`

## Validation Commands

```bash
# Play normalization (validates config)
python trade_cli.py backtest play-normalize-batch --dir configs/plays/_validation

# Indicator registry audit
python trade_cli.py backtest audit-toolkit

# Rollup parity audit
python trade_cli.py backtest audit-rollup

# Full smoke test
python trade_cli.py --smoke backtest
```

## Critical Rules

**Currency**: All values in USDT. Use `size_usdt`, never `size_usd`.

**No Lookahead**: Engine asserts `snapshot.ts_close == bar.ts_close`.

**Closed-Candle Only**: Indicators compute on closed bars only.

**Explicit Indicators**: Undeclared indicators raise KeyError.

**Fail-Loud Config**: Invalid config values raise ValueError immediately.

## See Also

- `src/backtest/CLAUDE.md` - Module-specific rules
- `src/forge/CLAUDE.md` - Forge development environment
- `docs/specs/PLAY_SYNTAX.md` - Play YAML reference
- `docs/specs/INCREMENTAL_STATE_ARCHITECTURE.md` - Structure detectors
