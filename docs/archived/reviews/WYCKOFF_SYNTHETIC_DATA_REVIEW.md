# Review: Wyckoff Synthetic Data for DSL Validation

**Date**: 2026-01-07
**Status**: PROPOSED
**Author**: Architecture Review

---

## Executive Summary

**Proposal**: Generate synthetic market data following Wyckoff distribution/accumulation principles to validate the TRADE DSL before building real trading strategies.

**Verdict**: **RECOMMENDED** - High value, addresses a real gap in current testing.

**Core Insight**: Wyckoff provides a generative model with KNOWN structure, enabling ground-truth assertions that random synthetic data cannot support.

---

## Problem Statement

### The Current Gap

When a strategy fails, there are two possible causes:

```
Strategy Failure
      │
      ├── A) The trading idea is bad
      │      → Expected, iterate on strategy
      │
      └── B) The DSL description is broken
             → Unexpected, tooling should be reliable
```

**Current testing cannot distinguish A from B reliably.**

### Why Existing Tests Fall Short

| Test Type | What It Proves | What It Doesn't Prove |
|-----------|----------------|----------------------|
| Tier 1 (Operator unit) | `cross_above` math is correct | Full pipeline handles it |
| Tier 2 (Structure math) | Swing detection formula works | Swing + Zone + Trend work together |
| Tier 3-4 (Integration) | Simple patterns execute | Complex realistic patterns execute |
| Random synthetic data | Code doesn't crash | Correct structure detection |

**The missing piece**: Data where we KNOW what should be detected, so we can assert correctness.

---

## Proposed Solution

### Wyckoff as a Generative Model

Wyckoff methodology provides well-defined price structures:

```
Distribution Structure:

    │    ┌──BC────────UT──UTAD────┐
    │   /│           /    \       │
    │  / │    ST    /      \  LPSY│
    │ /  │   /\    /        \    /│
    │/   │  /  \  /          \  / │
    │    └─/────AR────────────\/──┴───SOW────→
    │     PSY                              \
    │                                       \
    └──────────────────────────────────────────→

    |←─ Markup ─→|←──── Distribution ────→|←─ Markdown ─→|

Key Points:
- BC (Buying Climax): Swing high, resistance forms
- AR (Automatic Reaction): Swing low, support forms
- ST (Secondary Test): Tests BC area
- UT (Upthrust): False breakout above BC
- LPSY (Last Point of Supply): Lower highs, weakening
- SOW (Sign of Weakness): Breaks below AR support
```

### Why Wyckoff Works for DSL Testing

| Wyckoff Phase | DSL Concepts Tested |
|---------------|---------------------|
| BC (Buying Climax) | `swing.high_level`, zone resistance creation |
| AR (Auto Reaction) | `swing.low_level`, zone support creation |
| ST (Secondary Test) | `near_pct`, `zone.touched`, retests |
| UT (Upthrust) | `cross_above` + `cross_below`, false breakouts |
| Trading Range | `between`, `zone.inside`, ranging detection |
| LPSY | `holds_for` failure, trend weakening |
| SOW (Sign of Weakness) | `cross_below` support, `zone.state == BROKEN` |

**Every major DSL concept maps to a Wyckoff phase.**

---

## Value Proposition

### Ground Truth Assertions

Because we generate the data with known structure:

```python
# Generate with explicit structure points
data = generate_wyckoff_distribution(
    bc_bar=110, bc_price=50000,
    ar_bar=130, ar_price=47000,
    sow_bar=320,
)

# Now we can ASSERT correctness (not just "doesn't crash")
assert swing_at(110).high_level == 50000      # BC detected correctly
assert zone_at(135).resistance == 50000       # Zone formed at BC
assert zone_at(320).state == "BROKEN"         # SOW broke support
assert eval_at(200, '["close", "cross_above", 50000]') == True  # UT detected
```

**This is impossible with random data** - you don't know where swings SHOULD be.

### Multi-Timeframe Natural Fit

Wyckoff structure spans timeframes naturally:

```
HTF (4H):  Full distribution visible
           ├── BC, AR define range
           ├── Trading range clear
           └── SOW breakdown obvious

MTF (1H):  Internal waves visible
           ├── Rallies to resistance
           ├── Reactions to support
           └── Weakening attempts

LTF (15m): Entry-level structure
           ├── Micro swings for timing
           ├── Volume confirmation
           └── Trigger patterns
```

This tests MTF alignment: HTF bearish context should enable LTF short entries.

### Relationship Testing

Current tests validate components in isolation. Wyckoff tests them together:

```
Isolated:     "Does swing detection work?"
              "Does zone detection work?"
              "Does cross_below work?"

Integrated:   "When price breaks below AR (SOW), does:
               - Swing detect the breakdown bar?
               - Zone mark resistance as BROKEN?
               - cross_below fire correctly?
               - Trend change from RANGING to DOWN?
               All at the same time, consistently?"
```

---

## Comparison to Current Approach

### syntax_coverage.py (Current)

```python
# Tests operator patterns against real (unknown structure) data
TYPICAL_SYNTAX = {
    "T_010_cross_above_feature": SyntaxTest(
        condition='["ema_9", "cross_above", "ema_21"]',
    ),
}
# Problem: Can't assert WHEN this should fire
```

### Wyckoff Synthetic (Proposed)

```python
# Tests operator patterns against known structure data
def test_ut_false_breakout(wyckoff_data):
    # We KNOW UT is at bar 200, BC level is 50000
    assert eval_at(200, '["close", "cross_above", 50000]') == True
    assert eval_at(205, '["close", "lt", 50000]') == True  # Failed breakout
```

**The difference**: Assertions vs. "hope it works"

---

## Implementation Recommendation

### Phase 1: Minimal Viable Generator

```python
@dataclass
class SimpleWyckoffDistribution:
    """Simplified Wyckoff for initial testing."""

    total_bars: int = 500

    # Structure (bar indices)
    markup_end: int = 100
    bc_bar: int = 110        # Buying Climax
    ar_bar: int = 140        # Automatic Reaction
    range_end: int = 350
    sow_bar: int = 360       # Sign of Weakness

    # Prices
    bc_price: float = 50000
    ar_price: float = 47000

    # Noise
    noise_pct: float = 0.3

    def generate(self) -> pd.DataFrame:
        """Generate OHLCV following distribution structure."""
        # 1. Markup: trending up to BC
        # 2. BC: spike high with volume
        # 3. AR: sharp drop to support
        # 4. Range: oscillate between AR and BC
        # 5. SOW: break below AR
        # 6. Markdown: trending down
        ...
```

### Phase 2: Assertion Framework

```python
class WyckoffAssertions:
    """DSL correctness assertions against Wyckoff data."""

    def __init__(self, data: pd.DataFrame, params: SimpleWyckoffDistribution):
        self.data = data
        self.params = params

    def assert_bc_swing_detected(self, result):
        """Swing high should be detected at BC bar."""
        assert result.swing_high_at(self.params.bc_bar) == self.params.bc_price

    def assert_ar_swing_detected(self, result):
        """Swing low should be detected at AR bar."""
        assert result.swing_low_at(self.params.ar_bar) == self.params.ar_price

    def assert_zone_formed(self, result):
        """Zone should form between AR and BC."""
        zone = result.zone_at(self.params.ar_bar + 10)
        assert zone.lower == self.params.ar_price
        assert zone.upper == self.params.bc_price

    def assert_sow_breaks_zone(self, result):
        """SOW should mark zone as broken."""
        zone = result.zone_at(self.params.sow_bar + 1)
        assert zone.state == "BROKEN"
```

### Phase 3: Integration Tests

```python
class TestDSLAgainstWyckoff:
    """Full DSL validation using Wyckoff ground truth."""

    @pytest.fixture
    def wyckoff_distribution(self):
        params = SimpleWyckoffDistribution()
        return params, params.generate()

    def test_swing_detection(self, wyckoff_distribution):
        params, data = wyckoff_distribution
        result = run_swing_detector(data)
        WyckoffAssertions(data, params).assert_bc_swing_detected(result)
        WyckoffAssertions(data, params).assert_ar_swing_detected(result)

    def test_zone_formation(self, wyckoff_distribution):
        ...

    def test_breakout_operators(self, wyckoff_distribution):
        params, data = wyckoff_distribution
        # At UT bar, cross_above BC should fire
        assert eval_condition(data, params.ut_bar,
            f'["close", "cross_above", {params.bc_price}]') == True

    def test_sow_breakdown(self, wyckoff_distribution):
        ...
```

### Phase 4: Accumulation (Inverse)

Same structure inverted for long-side testing:

```
Accumulation: PS → SC → AR → ST → Spring → SOS → Markup
              (inverse of distribution)
```

---

## Scope Recommendation

| Phase | Scope | Effort | Value |
|-------|-------|--------|-------|
| V1 | Simple distribution (BC→AR→SOW) | 2-3 hours | HIGH |
| V2 | Add UT, ST, LPSY phases | 2-3 hours | MEDIUM |
| V3 | Multi-TF generation | 4-6 hours | HIGH |
| V4 | Accumulation (inverse) | 2-3 hours | MEDIUM |
| V5 | Variations (noise, proportions) | 2-3 hours | LOW |

**Recommendation**: Start with V1, prove the concept, then iterate.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Over-engineering | MEDIUM | LOW | Start simple (V1), iterate |
| Overfitting to Wyckoff | LOW | MEDIUM | Keep existing random tests too |
| Implementation complexity | MEDIUM | MEDIUM | Use simple linear interpolation first |
| Maintenance burden | LOW | LOW | Generator is standalone, minimal deps |

---

## Conclusion

### Why This Matters

The fundamental problem is:
> "When my strategy fails, is it the idea or the tooling?"

Current testing proves the tooling doesn't crash. Wyckoff testing proves the tooling detects structure correctly.

### Recommendation

**PROCEED** with Phase 1 implementation:

1. Build `SimpleWyckoffDistribution` generator
2. Create assertion framework for known structure points
3. Write DSL validation tests against generated data
4. Run existing DSL patterns against Wyckoff data

**Success Criteria**: When all Wyckoff assertions pass, we have confidence that:
- Swing detection works on realistic patterns
- Zone detection works with proper boundaries
- Operators fire at correct moments
- MTF alignment works as expected

Then, when a real strategy fails, we KNOW it's the strategy, not the DSL.

---

## References

- Wyckoff Method: https://school.stockcharts.com/doku.php?id=market_analysis:the_wyckoff_method
- Current DSL tests: `tests/validation/`, `tests/functional/`
- Structure detectors: `src/backtest/incremental/detectors/`

---

## Appendix: Wyckoff Phase Definitions

| Phase | Abbreviation | Description |
|-------|--------------|-------------|
| Preliminary Supply | PSY | First resistance after markup |
| Buying Climax | BC | Highest point, climactic volume |
| Automatic Reaction | AR | Sharp selloff after BC |
| Secondary Test | ST | Retest of BC area on lower volume |
| Upthrust | UT | False breakout above BC |
| Upthrust After Distribution | UTAD | Another false breakout |
| Last Point of Supply | LPSY | Weak rally, lower high |
| Sign of Weakness | SOW | Break below AR support |
| Last Point of Supply (after SOW) | LPSY | Failed rally after breakdown |
