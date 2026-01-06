# The Forge

Development and validation environment for Plays.

## Purpose

The Forge is where strategies are:
1. **Created** - Generated from templates or composed from Blocks
2. **Validated** - Checked for correctness before use
3. **Audited** - Verified for math parity and data flow
4. **Promoted** - Moved to production configs when ready

## Architecture Principle: Pure Math

All Forge components are pure functions:
- Input -> Computation -> Output
- No side effects
- No control flow about when to run
- Engine orchestrates invocation

```python
# CORRECT: Pure validation function
def validate_play(play: Play) -> ValidationResult:
    errors = check_schema(play)
    errors.extend(check_indicators(play))
    return ValidationResult(errors=errors, valid=len(errors) == 0)

# WRONG: Validation decides when to run
def maybe_validate(play: Play, force: bool = False):
    if force or self.should_validate:
        return self._do_validation(play)
```

## Submodule Structure

| Submodule | Purpose | Status |
|-----------|---------|--------|
| `audits/` | Parity and correctness audits | Complete |
| `validation/` | Play schema and indicator validation | Complete |
| `generation/` | Play generation from templates | Planned |
| `blocks/` | Reusable atomic conditions | Complete |
| `plays/` | Play normalizer and validation | Complete |
| `systems/` | System configs (multiple plays + regime) | Complete |

## Key Entry Points

```python
from src.forge import (
    # Blocks (reusable atomic conditions)
    Block, load_block, list_blocks, save_block,
    normalize_block_strict,

    # Plays (complete backtest-ready strategies)
    normalize_play_strict,

    # Systems (multiple plays with regime conditions)
    System, PlayRef, RegimeWeight,
    load_system, list_systems, save_system,
    normalize_system_strict,
)
```

## Trading Hierarchy (3-Level)

| Level | Description | Config Location | Purpose |
|-------|-------------|-----------------|---------|
| **Block** | Atomic reusable condition | `configs/blocks/` | Features + DSL condition (no account/risk) |
| **Play** | Complete backtest-ready strategy | `configs/plays/` | Features + actions + account + risk |
| **System** | Multiple plays with regime | `configs/systems/` | Weighted blending + regime conditions |

### Hierarchy Resolution

```python
# Full resolution: System -> Plays
from src.forge import load_system

system = load_system("btc_trend_v1")
for play_ref in system.get_enabled_plays():
    print(f"Play: {play_ref.play_id} (weight={play_ref.base_weight})")
    if play_ref.regime_weight:
        print(f"  Regime: multiplier={play_ref.regime_weight.multiplier}")
```

### System Weighted Blending

Systems support multiple active plays with regime-based weight adjustments:

```yaml
# configs/systems/btc_trend_v1.yml
id: btc_trend_v1
version: "1.0.0"

plays:
  - play_id: ema_trend_v1
    base_weight: 0.6
    regime_weight:
      condition:
        all:
          - ["atr_14", ">", 100]  # High volatility
      multiplier: 1.5  # Boost weight 50% in volatile markets

  - play_id: mean_reversion_v1
    base_weight: 0.4
    regime_weight:
      condition:
        all:
          - ["atr_14", "<", 50]   # Low volatility
      multiplier: 2.0  # Double weight in ranging markets

regime_features:
  atr_14:
    indicator: atr
    params: { length: 14 }

risk_profile:
  initial_capital_usdt: 100000.0
  max_drawdown_pct: 20.0
```

## Critical Rules

**ALL FORWARD**: No legacy support. Delete old code, update all callers.

**Pure Functions**: Forge components define MATH only. No control flow about invocation.

**Fail Loud**: Invalid configs raise errors immediately. No silent defaults.

## Validation Flow

```
Play YAML -> load_play() -> validate_play() -> ValidationResult
                                |
                        [errors] -> FIX -> retry
                        [valid] -> promote to configs/plays/
```

## Normalizers

Each hierarchy level has a strict normalizer:

| Level | Function | Purpose |
|-------|----------|---------|
| Block | `normalize_block_strict()` | Features + condition DSL |
| Play | `normalize_play_strict()` | Full backtest-ready strategy |
| System | `normalize_system_strict()` | Multiple plays + regime |

```python
from src.forge import normalize_system_strict

# Returns (System | None, NormalizationResult)
system, result = normalize_system_strict(raw_yaml, fail_on_error=False)
if not result.valid:
    print("Errors:", result.errors)
```

## Audit Tools

| Audit | Purpose | Pure Function |
|-------|---------|---------------|
| `audit_toolkit` | Indicator registry consistency | (config) -> ToolkitResult |
| `audit_math_parity` | Indicator math vs pandas_ta | (snapshots) -> ParityResult |
| `audit_plumbing` | Snapshot data flow | (play, dates) -> PlumbingResult |
| `audit_rollup` | 1m price aggregation | (config) -> RollupResult |

## Stress Test Suite (2026-01-04)

Full validation + backtest pipeline with hash tracing for debugging flow.

**8-Step Pipeline** (each produces `input_hash -> output_hash`):
1. Generate synthetic candle data (all TFs) -> `synthetic_data_hash`
2. Validate all plays (normalize-batch) -> `config_hash`
3. Run toolkit audit (registry contract) -> `registry_hash`
4. Run structure parity (synthetic data) -> `structure_hash`
5. Run indicator parity (synthetic data) -> `indicator_hash`
6. Run rollup audit (1m aggregation) -> `rollup_hash`
7. Execute validation plays as backtests -> `trades_hash`, `equity_hash`
8. Verify artifacts + determinism -> `run_hash`

**Usage**:
```python
from src.tools import forge_stress_test_tool

result = forge_stress_test_tool(
    skip_audits=False,
    skip_backtest=False,
    trace_hashes=True,
)
# result.data["hash_chain"] = ["a1b2c3d4...", "e5f6g7h8...", ...]
```

**CLI**: Forge menu -> option 6 (Stress Test Suite)

## Synthetic Data Generation

Deterministic, reproducible validation without DB dependency.

**Patterns**:
| Pattern | Purpose | Tests |
|---------|---------|-------|
| `trending` | Clear directional move | Swing highs/lows, trend detection |
| `ranging` | Sideways consolidation | Zone detection, support/resistance |
| `volatile` | High volatility spikes | Breakout detection, stop placement |
| `mtf_aligned` | Multi-TF alignment | HTF/MTF/LTF structure correlation |

**Usage**:
```python
from src.forge.validation import generate_synthetic_candles

candles = generate_synthetic_candles(
    symbol="BTCUSDT",
    timeframes=["1m", "5m", "15m", "1h", "4h"],
    bars_per_tf=1000,
    seed=42,  # Deterministic
    pattern="trending",
)
# candles.data_hash = "abc123..."  # For verification
```

## Validation Configs

| Level | Location | Examples |
|-------|----------|----------|
| Block | `configs/blocks/_validation/` | V_B001_*, V_B002_* |
| Play | `configs/plays/_validation/` | V_001-V_045 |
| System | `configs/systems/_validation/` | V_SYS001-V_SYS003 |

**System Validation Configs**:
- `V_SYS001_minimal.yml` - Single play, minimal risk
- `V_SYS002_full.yml` - Multiple plays with weights
- `V_SYS003_multi_mode.yml` - Regime-based weight adjustment

## Active TODOs

| Document | Focus |
|----------|-------|
| `docs/todos/TODO.md` | Active work tracking |
