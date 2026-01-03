# Backtest Module

Simulator/backtest domain. USDT-only, isolated margin.

## Submodule Structure

| Submodule | Purpose |
|-----------|---------|
| `sim/` | SimulatedExchange (pricing, execution, ledger, margin) |
| `runtime/` | RuntimeSnapshotView, FeedStore, TFContext |
| `features/` | FeatureSpec, FeatureFrameBuilder, indicator computation |
| `rules/` | Signal rule compilation and evaluation |
| `market_structure/` | Swing, Trend, Zone detection (batch - DEPRECATED) |
| `incremental/` | Incremental state detectors (O(1) per bar) |
| `artifacts/` | Run artifacts (manifest, events, equity) |
| `prices/` | Mark price providers |
| `gates/` | IdeaCard generation and batch verification |
| `audits/` | Parity and validation audits |

## Key Entry Points

```python
from src.backtest import (
    create_engine_from_idea_card,  # Create engine
    run_engine_with_idea_card,     # Run with signal evaluation
    load_idea_card,                # Load YAML config
)
```

## Engine Flow

```
IdeaCard YAML → load_idea_card() → IdeaCard dataclass
                                         ↓
                     create_engine_from_idea_card() → BacktestEngine
                                                           ↓
                                                    prepare_backtest_frame()
                                                           ↓
                                           run_engine_with_idea_card() → BacktestResult
```

## Critical Rules

**Currency**: All values in USDT. Use `size_usdt`, never `size_usd`.

**No Lookahead**: Engine asserts `snapshot.ts_close == bar.ts_close`. Violation = crash.

**Closed-Candle Only**: Indicators compute on closed bars only. HTF/MTF forward-fill between closes.

**Explicit Indicators**: No defaults. Undeclared indicators raise KeyError.

**Fail-Loud Config**: Invalid `mark_price_source`, `fee_mode`, `margin_mode`, `position_mode` raise ValueError.

## Structure Registry (Incremental State)

The incremental state system provides O(1) per-bar market structure detection. Structures are declared in the IdeaCard `structures` section and accessed via `structure.<key>.<output>` paths.

### Available Structure Types

| Type | Description | Required Params | Depends On | Outputs |
|------|-------------|-----------------|------------|---------|
| `swing` | Swing high/low detection | `left`, `right` | None | `high_level`, `high_idx`, `low_level`, `low_idx` |
| `fibonacci` | Fib retracement/extension | `levels`, `mode` | `swing` | `level_<ratio>` (e.g., `level_0.618`) |
| `zone` | Demand/supply zones | `zone_type`, `width_atr` | `swing` | `state`, `upper`, `lower`, `anchor_idx` |
| `trend` | Trend classification | None | `swing` | `direction`, `strength`, `bars_in_trend` |
| `rolling_window` | O(1) rolling min/max | `size`, `field`, `mode` | None | `value` |

### IdeaCard Configuration

```yaml
structures:
  exec:
    - type: swing
      key: swing
      params:
        left: 5
        right: 5
    - type: fibonacci
      key: fib
      depends_on:
        swing: swing
      params:
        levels: [0.382, 0.5, 0.618]
        mode: retracement
  htf:
    "1h":
      - type: swing
        key: swing_1h
        params: { left: 3, right: 3 }
```

### Accessing Structures in Rules

```yaml
signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        - tf: "exec"
          indicator_key: "structure.swing.high_level"
          operator: "gt"
          value: 0
        - tf: "htf"
          indicator_key: "structure.trend_1h.direction"
          operator: "eq"
          value: 1
```

### How Structures Differ from Indicators

| Aspect | Indicators | Structures |
|--------|------------|------------|
| Computation | Vectorized precompute | Incremental per-bar |
| Hot loop cost | O(1) lookup | O(1) update + lookup |
| Dependencies | None (use input_source) | Can depend on other structures |
| Live parity | N/A (backtest only) | Compatible with live trading |
| State | Stateless (view into DataFrame) | Stateful (maintained between bars) |

### Adding New Structure Types

1. Create detector in `src/backtest/incremental/detectors/<name>.py`
2. Inherit from `BaseIncrementalDetector`
3. Use `@register_structure("name")` decorator
4. Define `REQUIRED_PARAMS`, `OPTIONAL_PARAMS`, `DEPENDS_ON`
5. Implement `update(bar_idx, bar)`, `get_output_keys()`, `get_value(key)`
6. Add validation card to `configs/idea_cards/_validation/`

See: `docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md`

## Market Structure Paths (DEPRECATED)

> **Note**: The batch market structure system is deprecated. Use the `structures` section instead.

```yaml
# Legacy format (deprecated):
indicator_key: structure.<block_key>.<field>
indicator_key: structure.<block_key>.zones.<zone_key>.<field>
```

**SWING fields**: `swing_high_level`, `swing_low_level`, `swing_high_idx`, `swing_low_idx`, `swing_recency_bars`

**TREND fields**: `trend_state` (UP/DOWN/UNKNOWN), `parent_version`

**ZONE fields**: `lower`, `upper`, `state`, `touched`, `inside`, `time_in_zone`

## Metrics

62-field BacktestMetrics including:
- Core: total_trades, win_rate, profit_factor, net_pnl
- Risk: max_drawdown, sharpe, sortino, calmar
- Tail risk: VaR, CVaR, skewness, kurtosis
- Trade quality: MAE, MFE, edge ratio

## Active TODOs

| Document | Focus |
|----------|-------|
| `docs/todos/TODO.md` | Active work tracking |
| `docs/audits/OPEN_BUGS.md` | Bug fixes (3 P2, 12 P3) |
