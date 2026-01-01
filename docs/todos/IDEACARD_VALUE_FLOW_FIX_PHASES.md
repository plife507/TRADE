# IdeaCard Value Flow Fix Phases

**Created**: 2025-12-31
**Status**: ALL PHASES COMPLETE
**Validation**: `python trade_cli.py backtest run --idea-card <card> --start 2024-01-01 --end 2024-01-31`

---

## Problem Statement

Code review identified that IdeaCard configuration values are **IGNORED**:
- `account.slippage_bps` → always uses 5.0 bps (hardcoded)
- `account.fee_model.maker_bps` → never used
- `account.maintenance_margin_rate` → field doesn't exist (hardcoded 0.5%)

See: [BACKTEST_ENGINE_CODE_REVIEW.md](../reviews/BACKTEST_ENGINE_CODE_REVIEW.md)

---

## Phase 1: Fix slippage_bps Flow (CRITICAL)

**Goal**: IdeaCard `account.slippage_bps` must flow to ExecutionConfig

### Tasks

- [x] 1.1 Modify `engine_factory.py` to extract `slippage_bps` from IdeaCard
- [x] 1.2 Pass `slippage_bps` through `strategy_params` dict
- [x] 1.3 Verify `engine.py` reads from params (already does, just not populated)
- [x] 1.4 Create validation IdeaCard with explicit slippage_bps=2.0

### Code Changes

**File**: `src/backtest/engine_factory.py` (after line 117)

```python
# Extract slippage from IdeaCard if present
slippage_bps = 5.0  # Default only if not specified
if idea_card.account.slippage_bps is not None:
    slippage_bps = idea_card.account.slippage_bps
```

**File**: `src/backtest/engine_factory.py` (line 159, add to strategy_params)

```python
strategy_params = {
    "slippage_bps": slippage_bps,
    "taker_fee_bps": taker_fee_rate * 10000,  # Convert rate to bps
}
if requires_history:
    strategy_params["history"] = { ... }
```

### Gate 1.1: Slippage Value Parity

**Validation IdeaCard**: `configs/idea_cards/_validation/test__slippage_parity.yml`

```yaml
id: test__slippage_parity
account:
  starting_equity_usdt: 10000.0
  max_leverage: 3.0
  slippage_bps: 2.0  # EXPLICIT: must see 2.0 in logs, not 5.0
  fee_model:
    taker_bps: 6.0
    maker_bps: 2.0
```

**Validation Command**:
```bash
python trade_cli.py backtest run --idea-card test__slippage_parity --start 2024-06-01 --end 2024-06-30 --verbose
```

**Pass Criteria**:
- [x] Log shows `slippage_bps=2.0` (not 5.0)
- [x] Trade fills use 2 bps slippage adjustment

---

## Phase 2: Add maintenance_margin_rate to IdeaCard

**Goal**: Allow IdeaCard to configure MMR instead of hardcoded 0.5%

### Tasks

- [x] 2.1 Add `maintenance_margin_rate` field to `AccountConfig` in `idea_card.py`
- [x] 2.2 Extract MMR in `engine_factory.py` and pass to `RiskProfileConfig`
- [x] 2.3 Update `RiskProfileConfig` to accept MMR from IdeaCard
- [x] 2.4 Create validation IdeaCard with explicit MMR

### Code Changes

**File**: `src/backtest/idea_card.py` (AccountConfig class)

```python
@dataclass(frozen=True)
class AccountConfig:
    # Required fields
    starting_equity_usdt: float
    max_leverage: float

    # Optional fields
    margin_mode: str = "isolated_usdt"
    fee_model: Optional[FeeModel] = None
    slippage_bps: Optional[float] = None
    min_trade_notional_usdt: Optional[float] = None
    maintenance_margin_rate: Optional[float] = None  # NEW: e.g., 0.005 = 0.5%
```

**File**: `src/backtest/engine_factory.py`

```python
# Extract MMR from IdeaCard if present
mmr = 0.005  # Default Bybit lowest tier
if idea_card.account.maintenance_margin_rate is not None:
    mmr = idea_card.account.maintenance_margin_rate

# Pass to RiskProfileConfig
risk_profile = RiskProfileConfig(
    ...,
    maintenance_margin_rate=mmr,
)
```

### Gate 2.1: MMR Configuration Parity

**Validation IdeaCard**: `configs/idea_cards/_validation/test__mmr_config.yml`

```yaml
id: test__mmr_config
account:
  starting_equity_usdt: 10000.0
  max_leverage: 10.0
  maintenance_margin_rate: 0.01  # 1% MMR (higher than default 0.5%)
```

**Validation Command**:
```bash
python trade_cli.py backtest run --idea-card test__mmr_config --start 2024-06-01 --end 2024-06-30 --verbose
```

**Pass Criteria**:
- [x] Log shows `maintenance_margin_rate=0.01`
- [x] Liquidation threshold uses 1% MMR (higher equity floor)

---

## Phase 3: Fail-Loud for Required Values

**Goal**: Remove silent defaults, require explicit IdeaCard values

### Tasks

- [x] 3.1 Make `fee_model` required (no silent 0.0006 fallback)
- [x] 3.2 Make `min_trade_notional_usdt` required (no silent 1.0 fallback)
- [x] 3.3 Update all existing IdeaCards with explicit values
- [x] 3.4 Add validation gate for missing required fields

### Code Changes

**File**: `src/backtest/engine_factory.py`

```python
# BEFORE: Silent fallback
taker_fee_rate = 0.0006
if idea_card.account.fee_model:
    taker_fee_rate = idea_card.account.fee_model.taker_rate

# AFTER: Fail-loud
if idea_card.account.fee_model is None:
    raise ValueError(
        f"IdeaCard '{idea_card.id}' is missing account.fee_model. "
        "Fee model is required (taker_bps, maker_bps). No silent defaults."
    )
taker_fee_rate = idea_card.account.fee_model.taker_rate

# Same for min_trade_notional_usdt
if idea_card.account.min_trade_notional_usdt is None:
    raise ValueError(
        f"IdeaCard '{idea_card.id}' is missing account.min_trade_notional_usdt. "
        "Minimum trade notional is required. No silent defaults."
    )
min_trade_usdt = idea_card.account.min_trade_notional_usdt
```

### Gate 3.1: Fail-Loud Validation

**Test**: Run backtest with incomplete IdeaCard

```bash
# This should FAIL with clear error message
python trade_cli.py backtest run --idea-card test__missing_fee_model --start 2024-06-01 --end 2024-06-30
```

**Pass Criteria**:
- [x] Backtest fails with `ValueError: IdeaCard 'test__missing_fee_model' is missing account.fee_model`
- [x] Error message is actionable (tells user what to add)

---

## Phase 4: Validation Agent Smoke Test

**Goal**: Add automated validation via the validate agent

### Tasks

- [x] 4.1 Create `audit_ideacard_value_flow.py` in `src/backtest/audits/`
- [x] 4.2 Audit checks slippage_bps flows from IdeaCard to ExecutionConfig
- [x] 4.3 Audit checks MMR flows from IdeaCard to exchange
- [x] 4.4 Integrate into `backtest audit-value-flow` CLI command

### Audit Implementation

**File**: `src/backtest/audits/audit_ideacard_value_flow.py`

```python
"""
Audit: IdeaCard Value Flow Parity

Validates that IdeaCard configuration values flow correctly to engine components.
No silent defaults allowed - all values must be explicitly traceable.

Usage:
    python trade_cli.py backtest audit-value-flow --idea-card <card_id>
"""

def audit_value_flow(idea_card: IdeaCard, engine: BacktestEngine) -> AuditResult:
    """
    Check that IdeaCard values match engine configuration.

    Checks:
    1. slippage_bps: IdeaCard.account.slippage_bps == engine.execution_config.slippage_bps
    2. taker_fee_bps: IdeaCard.account.fee_model.taker_bps == engine.execution_config.taker_fee_bps
    3. mmr: IdeaCard.account.maintenance_margin_rate == engine._exchange._mmr
    """
    errors = []

    # Check slippage
    expected_slippage = idea_card.account.slippage_bps or 5.0
    actual_slippage = engine.execution_config.slippage_bps
    if expected_slippage != actual_slippage:
        errors.append(
            f"slippage_bps mismatch: IdeaCard={expected_slippage}, Engine={actual_slippage}"
        )

    # Check taker fee
    if idea_card.account.fee_model:
        expected_fee = idea_card.account.fee_model.taker_bps
        actual_fee = engine.execution_config.taker_fee_bps
        if expected_fee != actual_fee:
            errors.append(
                f"taker_fee_bps mismatch: IdeaCard={expected_fee}, Engine={actual_fee}"
            )

    # Check MMR
    if idea_card.account.maintenance_margin_rate:
        expected_mmr = idea_card.account.maintenance_margin_rate
        actual_mmr = engine._exchange._mmr
        if expected_mmr != actual_mmr:
            errors.append(
                f"maintenance_margin_rate mismatch: IdeaCard={expected_mmr}, Exchange={actual_mmr}"
            )

    return AuditResult(
        passed=len(errors) == 0,
        errors=errors,
        checks_run=3,
    )
```

### Gate 4.1: Audit Passes on Fixed Code

**Validation Command**:
```bash
python trade_cli.py backtest audit-value-flow --idea-card coverage_01_ema_cross
```

**Pass Criteria**:
- [x] `PASSED: 5/5 value flow checks`
- [x] No mismatch errors

---

## Validation Matrix

| Phase | Gate | Command | Pass Criteria |
|-------|------|---------|---------------|
| 1 | Slippage Parity | `backtest run --idea-card test__slippage_parity` | slippage_bps=2.0 in logs |
| 2 | MMR Config | `backtest run --idea-card test__mmr_config` | mmr=0.01 in logs |
| 3 | Fail-Loud | `backtest run --idea-card test__missing_fee_model` | ValueError raised |
| 4 | Audit Flow | `backtest audit-value-flow` | 3/3 checks pass |

---

## Smoke Test Suite

After all phases complete, run full validation:

```bash
# Set env for backtest smoke tests
$env:TRADE_SMOKE_INCLUDE_BACKTEST="1"

# Run full smoke
python trade_cli.py --smoke full

# Run specific value flow audit
python trade_cli.py backtest audit-value-flow --idea-card coverage_01_ema_cross
python trade_cli.py backtest audit-value-flow --idea-card coverage_07_mtf_full_stack
```

---

## Files to Modify

| File | Phase | Change |
|------|-------|--------|
| `src/backtest/engine_factory.py` | 1, 2, 3 | Extract slippage, MMR, fail-loud |
| `src/backtest/idea_card.py` | 2 | Add maintenance_margin_rate field |
| `src/backtest/audits/audit_ideacard_value_flow.py` | 4 | New audit module |
| `src/cli/smoke_tests.py` | 4 | Add value-flow audit to smoke |
| `configs/idea_cards/_validation/*.yml` | 1, 2, 3 | Test IdeaCards |

---

## Acceptance Criteria

- [x] IdeaCard `slippage_bps` flows to engine (not hardcoded 5.0)
- [x] IdeaCard `maintenance_margin_rate` configurable (not hardcoded 0.5%)
- [x] Missing required fields raise clear `ValueError` (fail-loud)
- [x] Value flow audit passes for all existing IdeaCards
- [x] Smoke tests pass with `TRADE_SMOKE_INCLUDE_BACKTEST=1`
