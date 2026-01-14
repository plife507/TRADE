# TRADE Backtest Engine Fix Plan

**Date**: 2026-01-01
**Source**: Agentic Audit Swarm
**Status**: READY FOR EXECUTION

---

## Execution Approach

Fixes are ordered by:
1. **Dependency** - Some fixes enable others
2. **Risk** - Higher priority risks first
3. **Locality** - Group by file to minimize context switches

Each fix includes estimated line changes and validation command.

---

## Phase 1: Schema & Version Safety (P1)

### Fix 1.1: Add Version Compatibility Checking
**Risk**: P1-01 (Version Fields Write-Only)
**File**: `src/backtest/artifacts/artifact_standards.py`
**Lines**: ~15

```python
# In RunManifest.from_dict(), after parsing:
if data.get("engine_version") != CURRENT_PIPELINE_VERSION:
    raise VersionMismatchError(
        f"Manifest version {data.get('engine_version')} "
        f"incompatible with engine {CURRENT_PIPELINE_VERSION}"
    )
```

**Validate**: `python trade_cli.py backtest run --play V_01_single_tf_ema_cross.yml`

### Fix 1.2: Consolidate PIPELINE_VERSION
**Risk**: P1-05 (Dual Constants)
**Files**: `pipeline_signature.py`, `runner.py`
**Lines**: ~5

```python
# In pipeline_signature.py (keep as source):
PIPELINE_VERSION = "1.0.0"

# In runner.py (import instead):
from .artifacts.pipeline_signature import PIPELINE_VERSION
```

**Validate**: `grep -r "PIPELINE_VERSION" src/backtest/`

### Fix 1.3: Promote ARTIFACT_VERSION
**Risk**: P1-11 (Development Placeholder)
**File**: `src/backtest/artifacts/__init__.py`
**Lines**: 1

```python
ARTIFACT_VERSION = "1.0.0"  # was "0.1-dev"
```

**Validate**: `python -c "from src.backtest.artifacts import ARTIFACT_VERSION; print(ARTIFACT_VERSION)"`

---

## Phase 2: State Tracking Completion (P1)

### Fix 2.1: Wire Missing State Tracker Hooks
**Risk**: P1-02 (Incomplete Wiring)
**File**: `src/backtest/engine.py`
**Lines**: ~30

Add hooks after each order lifecycle event:
```python
# After sizing computation:
if self._state_tracker:
    self._state_tracker.on_sizing_computed(bar_idx, signal, computed_size)

# After order submission:
if self._state_tracker:
    self._state_tracker.on_order_submitted(bar_idx, order)

# After order fill:
if self._state_tracker:
    self._state_tracker.on_order_filled(bar_idx, fill)

# After rejection:
if self._state_tracker:
    self._state_tracker.on_order_rejected(bar_idx, order, reason)
```

**Validate**: `python trade_cli.py backtest run --play V_65_state_tracking.yml`

### Fix 2.2: Fix GateContext Warmup Semantics
**Risk**: P1-07 (Semantic Mismatch)
**File**: `src/backtest/runtime/state_tracker.py`
**Lines**: ~5

```python
# Rename parameter for clarity:
def on_warmup_check(self, bar_idx: int, warmup_end_idx: int) -> None:
    """warmup_end_idx is the index where warmup ends, not a count."""
    is_warming_up = bar_idx < warmup_end_idx
```

**Validate**: Review gate evaluations in state tracking output

### Fix 2.3: Add State Tracking Comparison Test
**Risk**: P1-04 (No Comparison Test)
**File**: `src/cli/smoke_tests/structure.py`
**Lines**: ~25

```python
def run_state_tracking_parity_smoke() -> bool:
    """Run same card with state tracking on/off, compare hashes."""
    result_off = run_backtest(play, record_state_tracking=False)
    result_on = run_backtest(play, record_state_tracking=True)

    assert result_off.metrics_hash == result_on.metrics_hash, \
        "State tracking must not affect trade outcomes"
    return True
```

**Validate**: `python trade_cli.py --smoke full` (with TRADE_SMOKE_INCLUDE_BACKTEST=1)

---

## Phase 3: Rules Compiler Hardening (P1)

### Fix 3.1: Make Compilation Mandatory
**Risk**: P1-03 (Legacy Path Active)
**File**: `src/backtest/engine.py`
**Lines**: ~5

```python
# In engine initialization:
for rule in play.signal_rules:
    for cond in rule.conditions:
        if not cond.has_compiled_refs():
            raise RuntimeError(
                f"Condition must be compiled before execution: {cond}"
            )
```

**Validate**: `python trade_cli.py backtest run --play V_01_single_tf_ema_cross.yml`

### Fix 3.2: Reject Banned Operators at Parse Time
**Risk**: P1-10 (Banned But Parseable)
**File**: `src/backtest/play.py`
**Lines**: ~10

```python
BANNED_OPERATORS = {"cross_above", "cross_below"}

def _validate_operator(self, op: str) -> None:
    if op in BANNED_OPERATORS:
        raise ValueError(
            f"Operator '{op}' is not supported. "
            f"Use explicit threshold comparison instead."
        )
```

**Validate**: Create test card with cross_above, verify parse error

---

## Phase 4: Market Structure Safety (P1)

### Fix 4.1: Fail Loudly on Zone Width
**Risk**: P1-06 (Silent 1% Fallback)
**File**: `src/backtest/market_structure/detectors/zone_detector.py`
**Lines**: ~10

```python
# Replace silent fallback:
if atr_value is None or np.isnan(atr_value):
    if bar_idx < self.warmup_bars:
        # During warmup, skip zone creation
        return None
    else:
        raise ValueError(
            f"ATR not available at bar {bar_idx} after warmup"
        )
```

**Validate**: `python trade_cli.py backtest run --play V_62_zone_interaction.yml`

---

## Phase 5: Snapshot Performance (P1/P2)

### Fix 5.1: Move _NAMESPACE_RESOLVERS to Instance
**Risk**: P1-08 (Static Class Variable)
**File**: `src/backtest/runtime/snapshot_view.py`
**Lines**: ~15

```python
class RuntimeSnapshotView:
    def __init__(self, ...):
        self._resolvers = self._build_resolvers()

    def _build_resolvers(self) -> Dict[str, Callable]:
        return {
            "indicator": self._resolve_indicator,
            "price": self._resolve_price,
            # ...
        }
```

**Validate**: `python trade_cli.py backtest run --play V_01_single_tf_ema_cross.yml`

### Fix 5.2: Replace pd.isna() with np.isnan()
**Risk**: P2-01 (Hot Path Performance)
**File**: `src/backtest/engine.py`
**Lines**: ~5

```python
# Replace:
if pd.isna(value):
# With:
if np.isnan(value):
```

**Validate**: Run backtest, compare timing

---

## Phase 6: Documentation Updates

### Fix 6.1: Update CLAUDE.md Play Count
**Risk**: P1-14 (Documentation Drift)
**File**: `CLAUDE.md`
**Lines**: 1

```markdown
# Change:
- 21 validation Plays
# To:
- 24 validation Plays
```

**Validate**: `ls strategies/plays/_validation/ | wc -l`

---

## Validation Checklist

After completing all fixes, run:

```bash
# Tier 1: Play Normalization
python trade_cli.py backtest normalize --all

# Tier 2: Smoke Tests
$env:TRADE_SMOKE_INCLUDE_BACKTEST="1"
python trade_cli.py --smoke full

# Tier 3: Specific Validations
python trade_cli.py backtest run --play V_65_state_tracking.yml
python trade_cli.py backtest run --play V_62_zone_interaction.yml
python trade_cli.py backtest metadata-smoke

# Tier 4: Determinism Check
$env:TRADE_SMOKE_INCLUDE_DETERMINISM="1"
python trade_cli.py --smoke full
```

---

## Summary

| Phase | Fixes | Est. Lines | Priority |
|-------|-------|------------|----------|
| 1. Schema & Version | 3 | ~20 | P1 |
| 2. State Tracking | 3 | ~60 | P1 |
| 3. Rules Compiler | 2 | ~15 | P1 |
| 4. Market Structure | 1 | ~10 | P1 |
| 5. Snapshot Performance | 2 | ~20 | P1/P2 |
| 6. Documentation | 1 | ~1 | P1 |
| **Total** | **12** | **~125** | |

All P1 risks can be addressed with approximately 125 lines of changes across 12 targeted fixes.

---

**See Also:**
- [AUDIT_INDEX.md](AUDIT_INDEX.md) - Executive summary
- [RISK_REGISTER.md](RISK_REGISTER.md) - Full risk catalog

