# Market Structure Integration - Code Review Prompt

**Status**: 📋 READY FOR REVIEW  
**Created**: 2025-12-30  
**Goal**: Comprehensive code review to identify edge cases and potential issues before implementing Phase 5 (Market Structure Features)

**Context**: Engine Modular Refactor complete (2025-12-30). Market Structure work begins **after** the next phase lands: `docs/todos/PRICE_FEED_1M_PREFLIGHT_PHASES.md`.

---

## Review Objective

Conduct a thorough code review of the backtest engine and system to identify:
1. **Edge cases** that could break when market structure features are added
2. **Integration points** where market structure must fit cleanly
3. **Potential conflicts** with existing indicator/feature systems
4. **Validation gaps** that need coverage before Phase 5 implementation
5. **Architectural assumptions** that may not hold for market structure

---

## Review Scope

### Core Components to Review

```
src/backtest/
├── engine.py                    # Main orchestrator (1,154 lines)
├── engine_data_prep.py          # Data loading & preparation (758 lines)
├── engine_feed_builder.py       # FeedStore building (157 lines)
├── engine_snapshot.py           # Snapshot construction (171 lines)
├── engine_history.py            # History management (203 lines)
├── engine_stops.py              # Stop condition checks (234 lines)
├── engine_artifacts.py          # Artifact writing (172 lines)
├── engine_factory.py            # Factory functions (332 lines)
│
├── features/                    # Indicator system (reference pattern)
│   ├── feature_spec.py
│   ├── feature_frame_builder.py
│   └── ...
│
├── runtime/                     # Runtime components
│   ├── feed_store.py           # Array-backed storage
│   ├── snapshot_view.py        # RuntimeSnapshotView API
│   └── ...
│
└── sim/                         # Simulated exchange
    └── exchange.py
```

### Reference Documentation

- `docs/architecture/MARKET_STRUCTURE_INTEGRATION_PROPOSAL.md` - Proposed design
- `docs/todos/ARRAY_BACKED_HOT_LOOP_PHASES.md` - Phase 5 scope
- `docs/architecture/ARCH_SNAPSHOT.md` - System architecture

---

## Review Questions

### 1. FeatureSpec/FeatureFrame Integration

**Questions:**
- [ ] Can `FeatureFrameBuilder` handle market structure features alongside indicators?
- [ ] Are there assumptions about indicator-only computation that would break?
- [ ] Does the warmup calculation logic handle non-indicator features correctly?
- [ ] Are there hardcoded assumptions about indicator types/patterns?

**Files to Review:**
- `src/backtest/features/feature_frame_builder.py`
- `src/backtest/features/feature_spec.py`
- `src/backtest/engine_data_prep.py` (warmup calculation)

**Edge Cases to Check:**
- Multi-output features (indicators return multiple columns)
- Features that depend on other features (structure may depend on indicators)
- Warmup requirements for structure features (may differ from indicators)
- NaN handling for structure features (may have different semantics)

---

### 2. FeedStore Array Storage

**Questions:**
- [ ] Can `FeedStore` store structure features in the same arrays as indicators?
- [ ] Are there array size/alignment assumptions that would break?
- [ ] Does the `indicator_columns` parameter name imply indicator-only?
- [ ] Can structure features have different array shapes (e.g., multi-value outputs)?

**Files to Review:**
- `src/backtest/runtime/feed_store.py`
- `src/backtest/engine_feed_builder.py`

**Edge Cases to Check:**
- Structure features with multiple outputs (swing: price, index, strength)
- Structure features that update less frequently (only on swing detection)
- Forward-fill semantics for structure features (may differ from indicators)
- Array indexing when structure features are sparse (not every bar has a swing)

---

### 3. RuntimeSnapshotView API

**Questions:**
- [ ] Does `get_feature()` work for structure features, or do we need `get_structure()`?
- [ ] Are there TF routing assumptions that break for structure features?
- [ ] Does offset semantics work for structure features (e.g., "previous swing")?
- [ ] Can structure features be accessed via the same `tf_role` system?

**Files to Review:**
- `src/backtest/runtime/snapshot_view.py`
- `src/backtest/engine_snapshot.py`

**Edge Cases to Check:**
- Structure features that don't exist at every bar (swings are sparse)
- Structure features that need different offset semantics (e.g., "last 3 swings")
- Cross-TF structure validation (HTF swing must align with LTF swings)
- Structure features that are computed on-demand vs precomputed

---

### 4. Multi-Timeframe (MTF) Integration

**Questions:**
- [ ] Can structure features be computed independently per TF (like indicators)?
- [ ] Do structure features need cross-TF validation (e.g., HTF swing must contain LTF swings)?
- [ ] How do forward-fill semantics work for structure features?
- [ ] Can structure features have different update frequencies per TF?

**Files to Review:**
- `src/backtest/engine_data_prep.py` (multi-TF preparation)
- `src/backtest/runtime/cache.py` (TimeframeCache)
- `src/backtest/engine_snapshot.py` (TF routing)

**Edge Cases to Check:**
- HTF swing detected, but LTF bars don't align (validation needed?)
- Structure features that update at different rates per TF
- Forward-fill of structure features between TF closes
- Structure features that require history from other TFs

---

### 5. Warmup and Delay Bars

**Questions:**
- [ ] How do warmup requirements work for structure features?
- [ ] Do structure features respect `delay_bars` correctly?
- [ ] Can structure features have different warmup needs per TF role?
- [ ] Are there assumptions about warmup being indicator-only?

**Files to Review:**
- `src/backtest/engine_data_prep.py` (warmup calculation)
- `src/backtest/features/feature_frame_builder.py` (warmup from specs)
- `src/backtest/indicators.py` (warmup utilities)

**Edge Cases to Check:**
- Structure features that need more warmup than indicators (e.g., 200 bars for swing detection)
- Structure features with no warmup (computed on first bar)
- Delay bars applied to structure features (should they be delayed too?)
- Warmup calculation when structure depends on indicators

---

### 6. History Management

**Questions:**
- [ ] Can history windows store structure features?
- [ ] Do crossover operators work with structure features?
- [ ] Are there assumptions about history being indicator-only?
- [ ] Can structure features be used in crossover detection?

**Files to Review:**
- `src/backtest/engine_history.py`
- `src/backtest/execution_validation.py` (IdeaCard signal evaluation)

**Edge Cases to Check:**
- Crossover operators with structure features (e.g., "price crosses above last swing high")
- History windows that include structure features
- Structure features that change less frequently (history may be stale)
- Cross-TF history for structure features

---

### 7. Artifact and Validation

**Questions:**
- [ ] Do artifact validators handle structure features?
- [ ] Can structure features be included in math-parity audits?
- [ ] Are there validation assumptions about indicator-only features?
- [ ] How are structure features serialized in artifacts?

**Files to Review:**
- `src/backtest/engine_artifacts.py`
- `src/backtest/audit_in_memory_parity.py`
- `src/backtest/artifacts/` (validators)

**Edge Cases to Check:**
- Structure features in snapshot artifacts (if we add them)
- Math-parity validation for structure features (may not have pandas_ta reference)
- Artifact schema changes needed for structure features
- Validation of structure feature correctness (no reference implementation)

---

### 8. Hot Loop Performance

**Questions:**
- [ ] Will structure feature access impact hot loop performance?
- [ ] Are there O(1) access assumptions that break for structure features?
- [ ] Can structure features be precomputed like indicators?
- [ ] Do structure features require on-demand computation?

**Files to Review:**
- `src/backtest/engine.py` (hot loop in `run()` method)
- `src/backtest/runtime/snapshot_view.py` (O(1) access)

**Edge Cases to Check:**
- Structure features that require lookups (e.g., "find last swing")
- Structure features that need computation during hot loop (performance hit)
- Sparse structure features (most bars don't have swings)
- Structure features that need cross-TF lookups (may break O(1))

---

### 9. IdeaCard Configuration

**Questions:**
- [ ] Can IdeaCard YAML declare structure features?
- [ ] Does the IdeaCard parser handle structure specs?
- [ ] Are there validation assumptions about indicator-only specs?
- [ ] Can structure features be referenced in signal rules?

**Files to Review:**
- `src/backtest/idea_card.py`
- `src/backtest/execution_validation.py` (IdeaCard evaluation)
- `strategies/idea_cards/` (example YAMLs)

**Edge Cases to Check:**
- Structure features in signal rules (e.g., "if price > last_swing_high")
- Structure features in IdeaCard YAML format
- Validation of structure feature declarations
- Structure features with different parameter types than indicators

---

### 10. Error Handling and Edge Cases

**Questions:**
- [ ] What happens if structure feature computation fails?
- [ ] Are there graceful degradation paths?
- [ ] How are missing structure features handled (e.g., no swings detected)?
- [ ] Do error messages assume indicator-only features?

**Files to Review:**
- All engine modules (error handling)
- `src/backtest/features/feature_frame_builder.py` (computation errors)
- `src/backtest/runtime/snapshot_view.py` (missing feature handling)

**Edge Cases to Check:**
- Structure features that fail to compute (e.g., insufficient data)
- Structure features that return empty results (no swings in period)
- Structure features with invalid parameters
- Structure features that conflict with indicators (same key name)

---

## Specific Edge Cases to Investigate

### Edge Case 1: Sparse Structure Features
**Scenario**: Swing detection may not produce a value for every bar (swings are discrete events).

**Questions:**
- How does `RuntimeSnapshotView.get_feature()` handle missing values?
- Should structure features forward-fill like indicators?
- What's the "previous swing" when no swing exists yet?

**Files to Check:**
- `src/backtest/runtime/snapshot_view.py` (get_feature implementation)
- `src/backtest/runtime/feed_store.py` (NaN handling)

---

### Edge Case 2: Multi-Value Structure Features
**Scenario**: A swing has multiple outputs: price, index, strength, direction.

**Questions:**
- How are multi-value features stored in FeedStore arrays?
- Can `get_feature("swing_high")` return a dict/object, or must it be separate keys?
- How does warmup work for multi-value features?

**Files to Check:**
- `src/backtest/runtime/feed_store.py` (array structure)
- `src/backtest/features/feature_frame_builder.py` (multi-output handling)

---

### Edge Case 3: Cross-TF Structure Validation
**Scenario**: HTF swing high must be >= all LTF swing highs within that HTF bar.

**Questions:**
- Is this validation done during computation or at runtime?
- What happens if validation fails (HTF swing < LTF swing)?
- Does this break the "independent per TF" assumption?

**Files to Check:**
- `src/backtest/engine_data_prep.py` (multi-TF preparation)
- `src/backtest/features/feature_frame_builder.py` (validation logic)

---

### Edge Case 4: Structure Features Depending on Indicators
**Scenario**: Trend detection may use EMA values to determine trend direction.

**Questions:**
- Can structure features reference indicator values during computation?
- Does this create a dependency order issue (indicators must compute first)?
- How is this handled in FeatureFrameBuilder?

**Files to Check:**
- `src/backtest/features/feature_frame_builder.py` (computation order)
- `src/backtest/engine_data_prep.py` (indicator application)

---

### Edge Case 5: Delay Bars with Structure Features
**Scenario**: Structure features may need different delay semantics than indicators.

**Questions:**
- Should structure features respect `delay_bars` from market_structure config?
- What if structure features need no delay (computed on close)?
- How does delay interact with sparse structure features?

**Files to Check:**
- `src/backtest/engine_data_prep.py` (delay_bars application)
- `src/backtest/idea_card.py` (market_structure.delay_bars)

---

### Edge Case 6: History Windows with Structure Features
**Scenario**: Crossover detection needs "previous swing" in history.

**Questions:**
- Can history windows store structure features?
- How does "previous swing" work when swings are sparse?
- Do crossover operators work with structure features?

**Files to Check:**
- `src/backtest/engine_history.py` (history storage)
- `src/backtest/execution_validation.py` (crossover operators)

---

### Edge Case 7: Warmup Calculation for Structure Features
**Scenario**: Swing detection needs 50 bars lookback, but indicators need 20.

**Questions:**
- How is warmup calculated when structure needs more than indicators?
- Does warmup calculation handle structure features correctly?
- What if structure features have no warmup requirement?

**Files to Check:**
- `src/backtest/features/feature_frame_builder.py` (warmup calculation)
- `src/backtest/engine_data_prep.py` (warmup application)

---

### Edge Case 8: Performance with Sparse Structure Features
**Scenario**: Most bars don't have swings, but we need O(1) access to "last swing".

**Questions:**
- How do we maintain O(1) access when features are sparse?
- Do we need a separate index structure for structure features?
- Does this break the array-backed hot loop performance?

**Files to Check:**
- `src/backtest/runtime/feed_store.py` (array access)
- `src/backtest/runtime/snapshot_view.py` (get_feature performance)

---

## Review Output Format

For each area reviewed, provide:

1. **Status**: ✅ Safe | ⚠️ Needs Attention | ❌ Blocking Issue
2. **Findings**: List of specific issues or edge cases found
3. **Recommendations**: How to address each finding
4. **Code References**: Specific file paths and line numbers
5. **Test Cases**: Suggested test cases to validate fixes

---

## Validation Checklist

After review, verify:

- [ ] All edge cases documented
- [ ] Integration points identified
- [ ] No blocking issues found
- [ ] Recommendations provided for each finding
- [ ] Test cases suggested for validation
- [ ] Architecture assumptions validated or corrected

---

## Success Criteria

✅ **Review Complete** when:
- All 10 review areas covered
- All 8 specific edge cases investigated
- Findings documented with code references
- Recommendations provided for each issue
- No blocking issues remain (or blocking issues have clear resolution paths)

---

## Next Steps After Review

1. **Address Findings**: Fix or document each finding
2. **Update Design**: Revise `MARKET_STRUCTURE_INTEGRATION_PROPOSAL.md` if needed
3. **Add Tests**: Create test cases for identified edge cases
4. **Update TODOs**: Add any new phases needed to address findings
5. **Proceed to Phase 5**: Begin implementation once review complete

---

## Notes

- **Focus on edge cases**, not happy path (happy path should work if design is sound)
- **Look for assumptions** that may not hold for market structure
- **Check performance implications** of any design changes
- **Validate architectural patterns** (can structure follow indicator pattern exactly?)
- **Document any deviations** from the proposed design that are needed

---

## Review Command

Use this prompt with Claude Code to conduct the review:

```
Review the backtest engine codebase using the questions and edge cases in 
docs/todos/MARKET_STRUCTURE_INTEGRATION_REVIEW.md. Focus on identifying 
issues that would prevent clean integration of market structure features 
(swings, pivots, trends, regimes) following the same pattern as indicators.

Provide findings organized by the 10 review areas, with specific code 
references, edge case analysis, and recommendations for each finding.
```
