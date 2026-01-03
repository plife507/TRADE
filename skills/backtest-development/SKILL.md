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

### IdeaCard
- YAML strategy configuration
- Features (indicators), structures, rules
- Validation through normalization

## Development Patterns

### Adding Indicators

1. Add to `src/backtest/indicator_registry.py`:
```python
"new_indicator": IndicatorSpec(
    type="new_indicator",
    default_params={"period": 14},
    output_keys=["value"],
    required_columns=["close"],
),
```

2. Create validation IdeaCard
3. Run audit-toolkit

### Adding Structures

1. Create detector in `src/backtest/incremental/detectors/`
2. Use `@register_structure("name")` decorator
3. Implement `update()`, `get_output_keys()`, `get_value()`
4. Create validation IdeaCard

### Hot Loop Rules

- O(1) operations only (no DataFrame ops)
- Direct array access, not binary search
- Use pre-computed indices

## Common Pitfalls

- Lookahead: Using bar[i+1] data at bar[i]
- Off-by-one: Wrong warmup/start index
- Quote lookup: Binary search vs direct access
- Fee basis: Using wrong size field
