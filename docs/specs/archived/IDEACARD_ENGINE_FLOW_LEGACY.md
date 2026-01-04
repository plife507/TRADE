# IdeaCard to Engine Flow Documentation

**Phase 7 - LEGACY_CLEANUP_PHASES.md**

This document describes how IdeaCard fields flow through the backtest engine pipeline. Each IdeaCard section maps to specific engine components, with clear required vs optional semantics.

## Table of Contents

1. [Flow Diagram](#flow-diagram)
2. [IdeaCard Structure Overview](#ideacard-structure-overview)
3. [Field Mappings](#field-mappings)
   - [Identity Fields](#identity-fields)
   - [Account Configuration](#account-configuration)
   - [Symbol Universe](#symbol-universe)
   - [Timeframe Configurations](#timeframe-configurations)
   - [Position Policy](#position-policy)
   - [Signal Rules](#signal-rules)
   - [Risk Model](#risk-model)
4. [Required vs Optional Fields](#required-vs-optional-fields)
5. [Engine Factory Flow](#engine-factory-flow)
6. [Preflight Gate Integration](#preflight-gate-integration)

---

## Flow Diagram

```
+-------------------+
|    IdeaCard       |
|   (YAML File)     |
+--------+----------+
         |
         v
+--------+----------+     +-------------------+
|   load_idea_card  |---->|   IdeaCard        |
|  (idea_card.py)   |     |   (dataclass)     |
+-------------------+     +--------+----------+
                                   |
         +-------------------------+
         |
         v
+--------+----------+     +-------------------+
| run_preflight_gate|---->|  PreflightReport  |
|  (preflight.py)   |     |  - warmup_by_role |
+-------------------+     |  - delay_by_role  |
                          +--------+----------+
                                   |
         +-------------------------+
         |
         v
+--------+------------------------+
| create_engine_from_idea_card   |
|        (engine_factory.py)     |
+--------+------------------------+
         |
         |   Extract & Map:
         |   +------------------------------------------+
         |   | account -> RiskProfileConfig            |
         |   | tf_configs -> feature_specs_by_role     |
         |   | signal_rules -> strategy evaluator      |
         |   | risk_model -> sizing/stop configuration |
         |   +------------------------------------------+
         |
         v
+--------+----------+     +-------------------+
|   SystemConfig    |---->|  BacktestEngine   |
|  (system_config)  |     |   (engine.py)     |
+-------------------+     +--------+----------+
                                   |
                                   v
                          +-------------------+
                          | run_engine_with_  |
                          | idea_card()       |
                          +--------+----------+
                                   |
                                   v
                          +-------------------+
                          | IdeaCardBacktest  |
                          | Result            |
                          +-------------------+
```

---

## IdeaCard Structure Overview

An IdeaCard is a self-contained, declarative strategy specification defined in YAML. The canonical location is `configs/idea_cards/`.

```yaml
# Identity
id: SYMBOL_TF_strategy_name
version: "1.0.0"
name: "Human Readable Name"
description: "Strategy description"

# Account (REQUIRED)
account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  fee_model: { taker_bps: 6.0, maker_bps: 2.0 }
  min_trade_notional_usdt: 10.0
  slippage_bps: 2.0
  maintenance_margin_rate: 0.005

# Scope
symbol_universe: [SOLUSDT]

# Timeframes
tf_configs:
  exec: { tf: "15m", role: "exec", ... }
  htf:  { tf: "4h",  role: "htf", ... }
  mtf:  { tf: "1h",  role: "mtf", ... }

# Position Policy
position_policy:
  mode: "long_only"

# Signal Rules
signal_rules:
  entry_rules: [...]
  exit_rules: [...]

# Risk Model
risk_model:
  stop_loss: { type: "percent", value: 2.0 }
  take_profit: { type: "rr_ratio", value: 2.0 }
  sizing: { model: "percent_equity", value: 1.0 }
```

---

## Field Mappings

### Identity Fields

| IdeaCard Field | Engine Target | Description |
|----------------|---------------|-------------|
| `id` | `SystemConfig.system_id`, `StrategyInstanceConfig.strategy_id` | Unique identifier for the strategy |
| `version` | `StrategyInstanceConfig.strategy_version` | Semantic version for lineage tracking |
| `name` | Display only | Human-readable name (not used by engine) |
| `description` | Display only | Strategy description (not used by engine) |

**Source:** `engine_factory.py` lines 197-200
```python
strategy_instance = StrategyInstanceConfig(
    strategy_instance_id="idea_card_strategy",
    strategy_id=idea_card.id,
    strategy_version=idea_card.version,
    ...
)
```

---

### Account Configuration

The `account` section maps directly to `RiskProfileConfig` in `system_config.py`.

| IdeaCard Field | Engine Target | Required | Default |
|----------------|---------------|----------|---------|
| `account.starting_equity_usdt` | `RiskProfileConfig.initial_equity` | **YES** | None - fail loud |
| `account.max_leverage` | `RiskProfileConfig.max_leverage` | **YES** | None - fail loud |
| `account.fee_model.taker_bps` | `RiskProfileConfig.taker_fee_rate` | **YES** | None - fail loud |
| `account.fee_model.maker_bps` | Stored for future use | No | 0.0 |
| `account.min_trade_notional_usdt` | `RiskProfileConfig.min_trade_usdt` | **YES** | None - fail loud |
| `account.slippage_bps` | `strategy_params["slippage_bps"]` | No | 5.0 |
| `account.margin_mode` | Validated (must be "isolated_usdt") | No | "isolated_usdt" |
| `account.maintenance_margin_rate` | `RiskProfileConfig.maintenance_margin_rate` | No | 0.005 (Bybit lowest tier) |
| `account.max_notional_usdt` | Reserved for future use | No | None |
| `account.max_margin_usdt` | Reserved for future use | No | None |

**Source:** `engine_factory.py` lines 96-157
```python
# Validate required sections
if idea_card.account is None:
    raise ValueError(...)

# Extract capital/account params from IdeaCard (REQUIRED - no defaults)
initial_equity = idea_card.account.starting_equity_usdt
max_leverage = idea_card.account.max_leverage

# Extract fee model from IdeaCard (REQUIRED - fail loud if missing)
if idea_card.account.fee_model is None:
    raise ValueError(...)
taker_fee_rate = idea_card.account.fee_model.taker_rate

# Extract min trade notional from IdeaCard (REQUIRED - fail loud if missing)
if idea_card.account.min_trade_notional_usdt is None:
    raise ValueError(...)

# Build RiskProfileConfig
risk_profile = RiskProfileConfig(
    initial_equity=initial_equity,
    max_leverage=max_leverage,
    risk_per_trade_pct=risk_per_trade_pct,
    taker_fee_rate=taker_fee_rate,
    min_trade_usdt=min_trade_usdt,
    maintenance_margin_rate=maintenance_margin_rate,
)
```

---

### Symbol Universe

| IdeaCard Field | Engine Target | Required | Notes |
|----------------|---------------|----------|-------|
| `symbol_universe` | `SystemConfig.symbol`, Signal direction | **YES** | Currently only first symbol used |

**Validation:** Symbols must end with "USDT" (validated by `validate_usdt_pair()`)

**Source:** `engine_factory.py` lines 102-103
```python
# Get first symbol
symbol = idea_card.symbol_universe[0] if idea_card.symbol_universe else "BTCUSDT"
```

---

### Timeframe Configurations

The `tf_configs` section defines indicators and warmup requirements per timeframe role.

```
tf_configs:
  exec:     <- Required (execution timeframe)
  htf:      <- Optional (higher timeframe filter)
  mtf:      <- Optional (medium timeframe filter)
```

#### TFConfig Fields

| TFConfig Field | Engine Target | Required | Description |
|----------------|---------------|----------|-------------|
| `tf` | `SystemConfig.tf`, `tf_mapping` | **YES** | Timeframe string (e.g., "15m", "4h") |
| `role` | Dictionary key in `feature_specs_by_role` | **YES** | Must be "exec", "htf", or "mtf" |
| `warmup_bars` | `SystemConfig.warmup_bars_by_role` | No | Explicit warmup (overrides computed) |
| `feature_specs` | `SystemConfig.feature_specs_by_role[role]` | No | List of FeatureSpec definitions |
| `required_indicators` | `SystemConfig.required_indicators_by_role[role]` | No | Keys used in signal rules (for validation) |
| `market_structure.lookback_bars` | Data fetch range extension | No | Extra bars for structure analysis |
| `market_structure.delay_bars` | `SystemConfig.delay_bars_by_role[role]` | No | Bars to skip (no-lookahead guarantee) |

**Source:** `engine_factory.py` lines 159-213
```python
# Extract feature specs from IdeaCard
feature_specs_by_role = {}
for role, tf_config in idea_card.tf_configs.items():
    feature_specs_by_role[role] = list(tf_config.feature_specs)

# Extract required indicators from IdeaCard tf_configs
required_indicators_by_role: Dict[str, List[str]] = {}
for role, tf_config in idea_card.tf_configs.items():
    if tf_config.required_indicators:
        required_indicators_by_role[role] = list(tf_config.required_indicators)
```

#### FeatureSpec Structure

Each feature spec in `tf_configs.*.feature_specs` maps to a `FeatureSpec` dataclass:

```yaml
feature_specs:
  - indicator_type: "ema"       # Indicator type (validated against registry)
    output_key: "ema_fast"      # Name for the output column
    params:                     # Indicator-specific parameters
      length: 20
    input_source: "close"       # Input data (close, high, low, hlc3, etc.)
```

| FeatureSpec Field | Description | Required |
|-------------------|-------------|----------|
| `indicator_type` | Type string (validated against IndicatorRegistry) | **YES** |
| `output_key` | Output column name (or prefix for multi-output) | **YES** |
| `params` | Indicator parameters (e.g., `{length: 20}`) | No |
| `input_source` | Input data source (default: "close") | No |
| `input_indicator_key` | For chained indicators | No |
| `outputs` | Custom output key mapping (multi-output only) | No |

---

### Position Policy

| IdeaCard Field | Engine Target | Required | Default |
|----------------|---------------|----------|---------|
| `position_policy.mode` | Signal direction filtering | No | "long_only" |
| `position_policy.max_positions_per_symbol` | Validated (must be 1) | No | 1 |
| `position_policy.allow_flip` | Future feature | No | false |
| `position_policy.allow_scale_in` | Validated (must be false) | No | false |
| `position_policy.allow_scale_out` | Validated (must be false) | No | false |

**Mode Values:**
- `long_only` - Only long positions allowed
- `short_only` - Only short positions allowed
- `long_short` - Both directions allowed

**Source:** `idea_card.py` lines 258-265
```python
def allows_long(self) -> bool:
    """Check if long positions are allowed."""
    return self.mode in (PositionMode.LONG_ONLY, PositionMode.LONG_SHORT)

def allows_short(self) -> bool:
    """Check if short positions are allowed."""
    return self.mode in (PositionMode.SHORT_ONLY, PositionMode.LONG_SHORT)
```

---

### Signal Rules

The `signal_rules` section defines entry and exit logic. Rules are evaluated by `IdeaCardSignalEvaluator`.

```yaml
signal_rules:
  entry_rules:
    - direction: "long"
      conditions:
        - tf: "exec"
          indicator_key: "ema_fast"
          operator: "cross_above"
          value: "ema_slow"
          is_indicator_comparison: true
  exit_rules:
    - direction: "long"
      conditions:
        - tf: "exec"
          indicator_key: "ema_fast"
          operator: "cross_below"
          value: "ema_slow"
          is_indicator_comparison: true
```

#### Entry/Exit Rule Fields

| Field | Description | Required |
|-------|-------------|----------|
| `direction` | "long" or "short" | **YES** |
| `conditions` | List of conditions (AND logic) | **YES** |
| `exit_type` | "signal", "stop_loss", or "take_profit" (exit only) | No |

#### Condition Fields

| Field | Description | Required |
|-------|-------------|----------|
| `indicator_key` | Key of indicator to check | **YES** |
| `operator` | Comparison operator | **YES** |
| `value` | Threshold or indicator key | **YES** |
| `tf` | Timeframe role ("exec", "htf", "mtf") | No (default: "exec") |
| `is_indicator_comparison` | If true, value is another indicator | No (default: false) |
| `prev_offset` | Bar offset for crossover detection | No (default: 1) |

#### Operators

| Operator | Description |
|----------|-------------|
| `gt` | Greater than |
| `gte` | Greater than or equal |
| `lt` | Less than |
| `lte` | Less than or equal |
| `eq` | Equal |
| `cross_above` | Value crosses above threshold |
| `cross_below` | Value crosses below threshold |

**History Auto-Detection:** When crossover operators are used, the engine automatically configures history buffers.

**Source:** `engine_factory.py` lines 168-188
```python
# Auto-detect if crossover operators require history
requires_history = False
for rule in idea_card.signal_rules.entry_rules:
    for cond in rule.conditions:
        if cond.operator.value in ("cross_above", "cross_below"):
            requires_history = True
            break

# Build params with history config if crossovers are used
strategy_params = {}
if requires_history:
    strategy_params["history"] = {
        "bars_exec_count": 2,
        "features_exec_count": 2,
        "features_htf_count": 2,
        "features_mtf_count": 2,
    }
```

---

### Risk Model

The `risk_model` section defines stop loss, take profit, and position sizing.

#### Stop Loss

| Field | Values | Required |
|-------|--------|----------|
| `type` | "atr_multiple", "percent", "structure", "fixed_points" | **YES** |
| `value` | Multiplier, percent, or points | **YES** |
| `atr_key` | Indicator key (required if type="atr_multiple") | Conditional |
| `buffer_pct` | Buffer percentage | No (default: 0.0) |

#### Take Profit

| Field | Values | Required |
|-------|--------|----------|
| `type` | "rr_ratio", "atr_multiple", "percent", "fixed_points" | **YES** |
| `value` | Ratio, multiplier, percent, or points | **YES** |
| `atr_key` | Indicator key (required if type="atr_multiple") | Conditional |

#### Sizing

| Field | Values | Required |
|-------|--------|----------|
| `model` | "percent_equity", "fixed_usdt", "risk_based" | **YES** |
| `value` | Percent, USDT amount, or risk percent | **YES** |
| `max_leverage` | Maximum leverage cap | No (default: 1.0) |

**Source:** `engine_factory.py` lines 135-142
```python
# Extract risk params from IdeaCard risk_model
risk_per_trade_pct = 1.0
if idea_card.risk_model:
    if idea_card.risk_model.sizing.model.value == "percent_equity":
        risk_per_trade_pct = idea_card.risk_model.sizing.value
    # Override max_leverage from risk_model.sizing if different
    if idea_card.risk_model.sizing.max_leverage:
        max_leverage = idea_card.risk_model.sizing.max_leverage
```

---

## Required vs Optional Fields

### Required Fields (Engine Will Fail Without)

| Field | Validation Location | Error Code |
|-------|---------------------|------------|
| `id` | `idea_card.py:validate()` | Validation error |
| `version` | `idea_card.py:validate()` | Validation error |
| `symbol_universe` | `idea_card.py:validate()` | Validation error |
| `account` | `engine_factory.py:96-100` | `ValueError` |
| `account.starting_equity_usdt` | `AccountConfig.from_dict()` | `ValueError` |
| `account.max_leverage` | `AccountConfig.from_dict()` | `ValueError` |
| `account.fee_model` | `engine_factory.py:110-115` | `ValueError` |
| `account.min_trade_notional_usdt` | `engine_factory.py:118-124` | `ValueError` |
| `tf_configs.exec` | `idea_card.py:validate()` | Validation error |
| `signal_rules.entry_rules` | `SignalRules.__post_init__()` | `ValueError` |

### Optional Fields (With Defaults)

| Field | Default Value | Notes |
|-------|---------------|-------|
| `name` | None | Display only |
| `description` | None | Display only |
| `account.margin_mode` | "isolated_usdt" | Only value supported |
| `account.slippage_bps` | 5.0 (in engine_factory) | Applied to ExecutionConfig |
| `account.maintenance_margin_rate` | 0.005 | Bybit lowest tier |
| `tf_configs.htf` | Not used | Optional HTF filter |
| `tf_configs.mtf` | Not used | Optional MTF filter |
| `position_policy.mode` | "long_only" | Via PositionPolicy default |
| `risk_model.sizing.max_leverage` | 1.0 | Via SizingRule default |
| `market_structure.lookback_bars` | 0 | No extra lookback |
| `market_structure.delay_bars` | 0 | No delay |

---

## Engine Factory Flow

The `create_engine_from_idea_card()` function in `engine_factory.py` orchestrates the mapping:

```
1. Validate IdeaCard structure
   - Check account section exists
   - Check fee_model exists
   - Check min_trade_notional_usdt exists

2. Extract first symbol from symbol_universe

3. Build RiskProfileConfig from account section
   - initial_equity = account.starting_equity_usdt
   - max_leverage = account.max_leverage
   - taker_fee_rate = account.fee_model.taker_rate
   - min_trade_usdt = account.min_trade_notional_usdt
   - maintenance_margin_rate = account.maintenance_margin_rate

4. Extract feature_specs_by_role from tf_configs
   - For each role (exec, htf, mtf):
     - feature_specs_by_role[role] = list(tf_config.feature_specs)

5. Extract required_indicators_by_role from tf_configs

6. Auto-detect crossover operators for history config

7. Build StrategyInstanceConfig
   - strategy_id = idea_card.id
   - strategy_version = idea_card.version
   - params includes slippage_bps, fee rates

8. Build SystemConfig with all extracted values

9. Build tf_mapping for multi-TF support
   - ltf = exec_tf
   - mtf = idea_card.mtf or exec_tf
   - htf = idea_card.htf or exec_tf

10. Create and return BacktestEngine
```

---

## Preflight Gate Integration

Before the engine factory runs, the Preflight Gate validates data availability and computes warmup requirements.

```
1. Runner loads IdeaCard

2. Preflight Gate runs:
   - Checks data availability for all TFs
   - Computes warmup_by_role from FeatureSpecs
   - Computes delay_by_role from market_structure
   - Returns PreflightReport

3. Preflight values passed to engine factory:
   - warmup_by_role -> SystemConfig.warmup_bars_by_role
   - delay_by_role -> SystemConfig.delay_bars_by_role

4. Engine uses Preflight-computed values (SINGLE SOURCE OF TRUTH)
```

**Key Principle:** The engine MUST use Preflight-computed warmup/delay values. It MUST NOT recompute these values. If Preflight is skipped (testing only), a warning is logged.

**Source:** `runner.py` lines 432-454
```python
# Extract preflight warmup + delay (SOURCE OF TRUTH)
preflight_warmup_by_role: Optional[Dict[str, int]] = None
preflight_delay_by_role: Optional[Dict[str, int]] = None
if result.preflight_report and result.preflight_report.computed_warmup_requirements:
    preflight_warmup_by_role = result.preflight_report.computed_warmup_requirements.warmup_by_role
    preflight_delay_by_role = result.preflight_report.computed_warmup_requirements.delay_by_role
```

---

## Related Files

| File | Purpose |
|------|---------|
| `src/backtest/idea_card.py` | IdeaCard dataclass definitions |
| `src/backtest/engine_factory.py` | IdeaCard to Engine mapping |
| `src/backtest/system_config.py` | SystemConfig, RiskProfileConfig definitions |
| `src/backtest/features/feature_spec.py` | FeatureSpec definitions |
| `src/backtest/execution_validation.py` | IdeaCard validation and hashing |
| `src/backtest/runner.py` | Backtest execution with gates |
| `src/backtest/runtime/preflight.py` | Data preflight validation |
| `configs/idea_cards/_TEMPLATE.yml` | IdeaCard YAML template |
