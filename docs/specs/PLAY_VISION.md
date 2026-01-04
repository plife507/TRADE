# Play Vision

**Status**: North Star Document
**Created**: 2026-01-02
**Renamed**: 2026-01-04 (formerly IDEACARD_VISION.md)

---

## Terminology (2026-01-04)

This document uses the new trading hierarchy terminology:

| Term | Definition |
|------|------------|
| **Setup** | Reusable rule blocks, filters, entry/exit logic |
| **Play** | Complete strategy specification (formerly "IdeaCard") |
| **Playbook** | Collection of plays with regime routing |
| **System** | Full trading operation with risk/execution |
| **Forge** | Development/validation environment (src/forge/) |

See: `docs/architecture/LAYER_2_RATIONALIZATION_ARCHITECTURE.md` for complete architecture.

---

## End Goal

Agents compose, modify, and iterate on Plays autonomously.

## Current Goal

Humans author Plays with blocks that ARE agent-composable.
Architecture enables agents later without redesign.

## Play = Composition of Blocks

```yaml
blocks:

  # 1. VARIABLES - tunable parameters
  variables:
    ema_fast: 8
    swing_lookback: 5
    fib_levels: [0.382, 0.5, 0.618]

  # 2. FEATURES (Indicators) - precomputed, stateless
  features:
    exec:
      - type: ema
        params: { period: "{{ ema_fast }}" }
      - type: rsi
        params: { period: 14 }
      - type: atr
        params: { period: 14 }

  # 3. STRUCTURES - incremental, stateful
  structures:
    exec:
      - type: swing
        key: swing
        params: { left: "{{ swing_lookback }}" }
      - type: fibonacci
        key: fib
        depends_on: { swing: swing }
        params: { levels: "{{ fib_levels }}" }

  # 4. RULES - entry/exit conditions
  entry_rules:
    - condition: "ema_fast > ema_slow"        # Indicator
    - condition: "close near fib.level_0.618"  # Structure
    - condition: "trend.direction == 1"        # Structure

  # 5. RISK - sizing/stops
  risk:
    stop_loss: "swing.low_level - atr * 0.5"
    size_mode: risk_percent
```

## Block Architecture

```
+-------------+
|  VARIABLES  |  <- Parameters (tunable)
+-------------+
       |
       v
+-------------+     +-------------+
|  FEATURES   |     | STRUCTURES  |  <- Primitives (swappable)
| (indicators)|     | (stateful)  |
+-------------+     +-------------+
       |                   |
       +--------+----------+
                v
          +-------------+
          |    RULES    |  <- Logic (references both)
          +-------------+
                |
                v
          +-------------+
          |    RISK     |  <- Sizing (references both)
          +-------------+
```

## Two Registries

| Registry | Block Type | Computation | State |
|----------|------------|-------------|-------|
| INDICATOR_REGISTRY | Features | Vectorized (precompute) | Stateless |
| STRUCTURE_REGISTRY | Structures | Incremental (per bar) | Stateful |

Both registries are:
- **Discoverable**: Query available types, params, outputs
- **Documented**: REQUIRED_PARAMS, DEPENDS_ON, OUTPUT_KEYS
- **Validated**: Normalization catches errors before run
- **Agent-ready**: Machine-parseable, machine-composable

## Design Principles (Agent-Ready)

| Principle | What We Build | Enables Later |
|-----------|---------------|---------------|
| Schema-strict | YAML with validation | Agents can parse/generate |
| Blocks as units | Swappable sections | Agents can modify blocks |
| Registry-discoverable | Query available types | Agents can explore options |
| Normalization gate | Validates before run | Agents get error feedback |
| Deterministic | Same play = same result | Agents can compare runs |

## Structure Registry Pattern

```python
@register_structure("fibonacci")
class IncrementalFibonacci(BaseIncrementalDetector):

    REQUIRED_PARAMS = ["levels", "mode"]
    DEPENDS_ON = ["swing"]

    def get_output_keys(self) -> list[str]:
        return [f"level_{r}" for r in self.levels]

    def update(self, bar_idx: int, bar_data: BarData) -> None:
        # Called each bar
        ...

    def get_value(self, key: str) -> float:
        # O(1) lookup
        ...
```

Structures can depend on other structures:

```yaml
structures:
  - type: swing
    key: swing

  - type: fibonacci
    key: fib
    depends_on: { swing: swing }

  - type: trend
    key: trend
    depends_on: { swing: swing }

  - type: order_block
    key: ob
    depends_on: { swing: swing, trend: trend }
```

## Rules Reference Both Registries

```yaml
entry_rules:
  # Indicator references
  - condition: "ema_fast > ema_slow"
  - condition: "rsi > 30 and rsi < 70"

  # Structure references
  - condition: "trend.direction == 1"
  - condition: "fib.level_0.618 - close < atr * 0.5"

  # Mixed
  - condition: "close > ema_fast and trend.direction == 1"
```

## Future: Agent Operations

When agents are integrated, they can:

| Operation | Example |
|-----------|---------|
| Add block | Add fibonacci structure |
| Remove block | Remove RSI filter |
| Swap block | Replace zone with order_block |
| Tune variable | Change swing_lookback: 5 -> 8 |
| Clone & modify | Copy play, add filter, compare |

The architecture supports this without changes.

## Trading Hierarchy Integration

Plays fit into the larger trading hierarchy:

```
SETUP (atomic)           PLAY (strategy)         PLAYBOOK (collection)
+----------------+      +----------------+      +----------------+
| breakout_entry |      | trend_breakout |      | bull_market    |
| trailing_stop  | ---> | - uses setups  | ---> | - play A       |
| volume_filter  |      | - adds sizing  |      | - play B       |
| regime_filter  |      | - risk rules   |      | - regime rules |
+----------------+      +----------------+      +----------------+
                                                        |
                                                        v
                                               +----------------+
                                 SYSTEM        | full_deployment|
                                               | - playbook A   |
                                               | - playbook B   |
                                               | - global risk  |
                                               | - execution    |
                                               +----------------+
```

## Implementation Phases

1. **Incremental State Architecture** - O(1) structures in hot loop
2. **Structure Registry** - Register swing, zone, trend, fib, etc.
3. **Play Schema** - Add `structures:` block
4. **Engine Integration** - Wire incremental updates
5. **Validation** - Normalization for structure blocks
6. *(Future)* Agent integration

## Related Documents

- `INCREMENTAL_STATE_ARCHITECTURE.md` - Technical design for incremental state
- `PLAY_SYNTAX.md` - Blocks DSL v3.0.0 syntax reference
- `../architecture/LAYER_2_RATIONALIZATION_ARCHITECTURE.md` - Layer 2 StateRationalizer and Forge
- `../project/PROJECT_OVERVIEW.md` - Project roadmap
