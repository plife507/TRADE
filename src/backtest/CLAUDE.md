# Backtest Module

Simulator/backtest domain. USDT-only, isolated margin.

## Submodule Structure

| Submodule | Purpose |
|-----------|---------|
| `sim/` | SimulatedExchange (pricing, execution, ledger, margin) |
| `runtime/` | RuntimeSnapshotView, FeedStore, TFContext |
| `features/` | FeatureSpec, FeatureFrameBuilder, indicator computation |
| `play/` | Play dataclass, config models, risk policy (extracted 2026-01-08) |
| `rules/` | Signal rule compilation and evaluation (see submodules below) |
| `rationalization/` | Layer 2: transitions, derived state, regime, conflicts |
| `market_structure/` | Swing, Trend, Zone detection (batch - DEPRECATED) |
| `incremental/` | Incremental state detectors (O(1) per bar) |
| `artifacts/` | Run artifacts (manifest, events, equity) |
| `prices/` | Mark price providers |
| `gates/` | Play generation and batch verification |
| `audits/` | Parity and validation audits (MIGRATING to `src/forge/audits/`) |

### rules/ Submodules (Cookbook Alignment Refactor 2026-01-08)

| Submodule | Purpose |
|-----------|---------|
| `dsl_nodes/` | DSL node types: FeatureRef, Cond, window operators, boolean logic |
| `evaluation/` | ExprEvaluator: condition evaluation, crossover, window operators |
| `dsl_parser.py` | Parse YAML → DSL nodes |
| `compile.py` | Compile DSL into evaluable rules |

### play/ Submodules (Extracted 2026-01-08)

| Module | Purpose |
|--------|---------|
| `config_models.py` | FeeModel, AccountConfig, ExitMode |
| `risk_model.py` | RiskModel, enums, position sizing rules |
| `play.py` | Play dataclass, PositionPolicy, load_play() |

## Key Entry Points

```python
from src.backtest import (
    create_engine_from_play,  # Create engine from Play config
    run_engine_with_play,     # Run with signal evaluation
    load_play,                # Load YAML config
)
```

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

## Trading Hierarchy

The TRADE system uses a 3-level hierarchical strategy model:

| Level | Description |
|-------|-------------|
| **Block** | Atomic reusable condition (features + DSL condition, no account/risk) |
| **Play** | Complete backtest-ready strategy (features + actions + account + risk) |
| **System** | Multiple plays with regime-based weighted blending |

**Play** is the primary unit for backtesting. Located in `strategies/plays/`.

## The Forge

The **Forge** (`src/forge/`) is the development and validation environment for Plays. It provides:
- Play generation and validation
- Batch testing across multiple symbols/timeframes
- Performance comparison and analysis
- **Audits** (migrating from `src/backtest/audits/`)

See `src/forge/CLAUDE.md` for Forge-specific rules and architecture.

## Critical Rules

**Currency**: All values in USDT. Use `size_usdt`, never `size_usd`.

**No Lookahead**: Engine asserts `snapshot.ts_close == bar.ts_close`. Violation = crash.

**Closed-Candle Only**: Indicators compute on closed bars only. All slower TFs forward-fill between closes.

**Explicit Indicators**: No defaults. Undeclared indicators raise KeyError.

## Price Field Semantics (CRITICAL for Live Integration)

Three distinct price concepts exist at different resolutions:

| Field       | Resolution | Backtest Source         | Live Source (Future)      | Use Case              |
|-------------|------------|-------------------------|---------------------------|-----------------------|
| `last_price`| 1m         | 1m bar close            | ticker.lastPrice          | Signal evaluation     |
| `mark_price`| 1m         | 1m close OR mark kline  | ticker.markPrice          | PnL, liquidation, risk|
| `close`     | eval_tf    | eval_tf bar close       | eval_tf bar close         | Indicator computation |

### last_price vs mark_price

**These are NOT aliases. They are semantically different in live trading.**

- **last_price**: Actual last trade price on the exchange. Use for:
  - Signal evaluation at 1m granularity
  - Entry/exit price decisions
  - Reflects real orderbook activity (can spike during volatility)

- **mark_price**: Index-derived mark price. Use for:
  - Position valuation (unrealized PnL)
  - Liquidation trigger calculations
  - Risk metrics
  - Bybit calculates from prices across multiple exchanges to prevent manipulation

In backtest, both default to the same 1m close source for simplicity. In live trading, they come from different WebSocket fields and **can diverge significantly** during volatile periods.

### Built-in Features (No Declaration Required)

These are runtime-provided, not computed indicators:

```python
BUILTIN_FEATURES = {
    "last_price",   # 1m ticker - for signals
    "mark_price",   # 1m mark - for PnL/liquidation
    "close", "open", "high", "low", "volume",  # eval_tf bar OHLCV
}
```

See: `src/backtest/execution_validation.py` for full documentation.

## Multi-Timeframe Forward-Fill Semantics

**Bybit API Intervals**: `1,3,5,15,30,60,120,240,360,720,D,W,M`
**Internal Format**: `1m,3m,5m,15m,30m,1h,2h,4h,6h,12h,D,W,M`
**NOTE**: 8h is NOT a valid Bybit interval - do not use it.

### Timeframe Role Definitions

| Role | Meaning | Valid Values | Purpose |
|------|---------|--------------|---------|
| **LTF** | Low Timeframe | 1m, 3m, 5m, 15m | Execution timing (entries/exits), micro-structure |
| **MTF** | Mid Timeframe | 30m, 1h, 2h, 4h | Trade bias + structure context for LTF execution |
| **HTF** | High Timeframe | 6h, 12h, D | Higher-level trend + major levels (W, M excluded from role) |
| **exec** | Execution TF | LTF or MTF | The timeframe at which trading decisions are evaluated |

**Hierarchy Rule**: `HTF >= MTF >= LTF` (in minutes). Enforced by `validate_tf_mapping()`.

Any timeframe slower than exec forward-fills its values until its next bar closes. This applies to both indicators and structures.

```
Timeframe Hierarchy (example: exec=15m):
┌─────────────────────────────────────────────────────────────┐
│  1m ticker  ─►  exec (15m)  ─►  MTF (1h)  ─►  HTF (4h)     │
│  aggregated      updates        forward-fill   forward-fill │
│                  every bar      until close    until close  │
└─────────────────────────────────────────────────────────────┘
```

### Update Behavior by TF Role

| TF Role | Relation to Exec | Behavior |
|---------|------------------|----------|
| 1m ticker | Faster | Aggregated into rollups (max/min/range per exec bar) |
| exec | Reference | Updates every bar (no forward-fill) |
| MTF | Slower | Forward-fill until MTF bar closes |
| HTF | Slower | Forward-fill until HTF bar closes |

### Forward-Fill Example

```
exec bars (15m):  |  1  |  2  |  3  |  4  |  5  |  6  |  7  |  8  |
                  ├─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
HTF bars (1h):    |          HTF bar 0          |     HTF bar 1    ...
                  │                             │
                  └─── HTF values unchanged ────┘
                       (forward-filled)

snapshot.htf_ctx.current_idx:  [0, 0, 0, 0, 1, 1, 1, 1]
```

### What Forward-Fill Means for Trading Logic

- **Indicators**: HTF EMA(50) value stays constant across 4 exec bars until next HTF close
- **Structures**: HTF swing.high_level updates only when HTF bar closes and swing is confirmed
- **No Lookahead**: Values reflect last CLOSED bar, never partial/forming bars

### Feature Timeframe Inheritance

Features inherit their timeframe from the Play's main `tf:` unless explicitly overridden.

| Feature Config | Timeframe Used |
|----------------|----------------|
| No `tf:` field | Inherits main `tf:` (execution TF) |
| `tf: "4h"` | Uses 4h (explicit override) |

**Inheritance is flat (one level only).** No feature-to-feature inheritance.

```yaml
tf: "15m"                    # Main execution TF

features:
  ema_9:                     # No tf: → uses 15m (inherited)
    indicator: ema
    params: {length: 9}

  ema_50_4h:                 # Explicit tf: → uses 4h
    indicator: ema
    params: {length: 50}
    tf: "4h"
```

**Note:** The `source:` field (e.g., `source: volume`) changes input data, not timeframe.

**See:** `docs/specs/PLAY_DSL_COOKBOOK.md` → "Feature Timeframe Inheritance" for full details.

**Fail-Loud Config**: Invalid `mark_price_source`, `fee_mode`, `margin_mode`, `position_mode` raise ValueError.

## Structure Registry (Incremental State)

The incremental state system provides O(1) per-bar market structure detection. Structures are declared in the Play `structures` section and accessed via `structure.<key>.<output>` paths.

### Available Structure Types

| Type | Description | Required Params | Depends On | Outputs |
|------|-------------|-----------------|------------|---------|
| `swing` | Swing high/low detection | `left`, `right` | None | `high_level`, `high_idx`, `low_level`, `low_idx`, `version` |
| `fibonacci` | Fib retracement/extension | `levels`, `mode` | `swing` | `level_<ratio>` (e.g., `level_0.618`) |
| `zone` | Demand/supply zones | `zone_type`, `width_atr` | `swing` | `state`, `upper`, `lower`, `anchor_idx`, `version` |
| `trend` | Trend classification | None | `swing` | `direction`, `strength`, `bars_in_trend`, `version` |
| `rolling_window` | O(1) rolling min/max | `size`, `field`, `mode` | None | `value` |
| `derived_zone` | Fib zones from pivots | `levels`, `mode`, `max_active` | `swing` | K slots + aggregates (see below) |

### Derived Zone Output Fields (Phase 12)

Derived zones use **K slots + aggregates** pattern:

**Slot Fields** (per zone, 0 to K-1):
- `zone{N}_lower`, `zone{N}_upper` (FLOAT, null if empty)
- `zone{N}_state` (ENUM: NONE/ACTIVE/BROKEN)
- `zone{N}_touched_this_bar`, `zone{N}_inside` (BOOL)
- `zone{N}_age_bars`, `zone{N}_touch_count` (INT)

**Aggregate Fields**:
- `active_count` (INT), `any_active`, `any_touched`, `any_inside` (BOOL)
- `closest_active_lower`, `closest_active_upper` (FLOAT)
- `source_version` (INT)

### Play Configuration

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

### Accessing Structures in Rules (Actions DSL v3.0.0)

**IMPORTANT**: All Plays use `actions` format (renamed from `blocks` 2026-01-05). Legacy `signal_rules` is deprecated.

```yaml
actions:
  - id: entry
    cases:
      - when:
          all:
            - lhs: {feature_id: "swing", field: "high_level"}
              op: gt
              rhs: 0
            - lhs: {feature_id: "fib_zones", field: "any_active"}
              op: eq
              rhs: true
        emit:
          - action: entry_long
  - id: exit
    cases:
      - when:
          any:
            - lhs: {feature_id: "fib_zones", field: "any_touched"}
              op: eq
              rhs: true
        emit:
          - action: exit_long
```

**Actions DSL Features** (FROZEN 2026-01-08):
- Nested boolean logic: `all`, `any`, `not`
- 11 operators: `gt`, `lt`, `gte`, `lte`, `eq`, `cross_above`, `cross_below`, `between`, `near_abs`, `near_pct`, `in`
- Bar-based window operators: `holds_for`, `occurred_within`, `count_true` (with `anchor_tf` scaling)
- Duration-based window operators: `holds_for_duration`, `occurred_within_duration`, `count_true_duration`
- Duration formats: `m` (minutes), `h` (hours), `d` (days) - max 24h ceiling
- Type-safe: `eq` only for discrete, `near_*` only for numeric
- Missing value handling: `None`, `NaN`, `±Infinity` → MISSING (comparisons return false)
- SetupRef circular reference protection (recursion guard)
- Built-in price features: `last_price` (1m ticker close), `close` (eval_tf bar close), `mark_price`

**Crossover Semantics (TradingView-aligned, 2026-01-07)**:
- `cross_above`: `prev_lhs <= rhs AND curr_lhs > rhs`
- `cross_below`: `prev_lhs >= rhs AND curr_lhs < rhs`
- Supports `last_price` with offset=1 via `prev_last_price` tracking

**Window Operators with anchor_tf (2026-01-07)**:
- `anchor_tf` scales bar offsets: `bars: 3, anchor_tf: "1h"` = 180 minutes lookback
- Without `anchor_tf`, bars are in 1m granularity (default)
- Duration operators always evaluate at 1m granularity

**Strategy Patterns Guide**: See `docs/guides/DSL_STRATEGY_PATTERNS.md` for 7 documented patterns

**1m Action Model (2026-01-07)**:
- Signals are evaluated every 1m within each eval_tf bar
- `last_price` provides the 1m ticker close for cross-TF comparisons
- Window operators default to 1m sampling (`anchor_tf="1m"`)
- Duration-based windows convert to 1m bars (e.g., `"30m"` = 30 bars)
- See: `docs/architecture/TIMEFRAME_SEMANTICS.md`

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
6. Add validation Play to `strategies/plays/_validation/`

See: `docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md`

## Legacy Code Status (2026-01-08)

| Module | Status | Notes |
|--------|--------|-------|
| `market_structure/` | DEPRECATED | Batch-based; use `incremental/` instead |
| `gates/` | NEEDS UPDATE | Still generates legacy signal_rules format |
| Legacy Plays | REMOVED | All V_60-V_95 deleted; only V_100+ actions remain |
| `signal_rules` format | DEPRECATED | Use `actions` (v3.0.0) |
| `blocks:` YAML key | REMOVED | Use `actions:` only (2026-01-08) |
| `margin_mode: "isolated"` | REMOVED | Use `isolated_usdt` only (2026-01-08) |
| `condition:` in windows | REMOVED | Use `expr:` only (2026-01-08) |

## Validation Plays

**Location**: `tests/validation/plays/` (relocated 2026-01-07)

Previous location `strategies/plays/_validation/` has been cleared.

| Range | Purpose |
|-------|---------|
| V_100-V_106 | Core actions DSL (all/any/not, operators, windows) |
| V_115 | Type-safe operator validation |
| V_120-V_122 | Derived zones (K slots, aggregates, empty guards) |
| V_130-V_133 | 1m action model (last_price, forward-fill, duration windows) |

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
| `docs/audits/OPEN_BUGS.md` | Bug tracker (0 open - all fixed 2026-01-07) |
| `docs/guides/DSL_STRATEGY_PATTERNS.md` | 7 DSL strategy patterns |
