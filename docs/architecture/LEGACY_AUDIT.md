# Legacy Code Audit

> **Generated**: 2026-01-11
> **Findings**: Significant legacy/new mixing that violates "ALL FORWARD, NO LEGACY" directive

---

## Summary

| Category | Count | Severity |
|----------|-------|----------|
| Deprecated Modules (still present) | 2 | HIGH |
| Backward Compatibility Shims | 27+ | HIGH |
| Placeholder Implementations | 7 | MEDIUM |
| Legacy Format Support | 3 | HIGH |
| Deprecated Aliases | 10+ | MEDIUM |

---

## 1. DEPRECATED MODULES (Still in Codebase)

### `market_structure/` - DEPRECATED
**Location**: `src/backtest/market_structure/`
**Status**: Marked deprecated, should use `incremental/` instead
**Issue**: Module still exists and is being used as fallback

```
src/backtest/CLAUDE.md:359:| `market_structure/` | DEPRECATED | Batch-based; use `incremental/` instead |
src/backtest/engine_feed_builder.py:172:# Stage 3: Market Structure Building (DEPRECATED - Phase 7 Transition)
src/backtest/engine_feed_builder.py:197:    [DEPRECATED] Build market structures and wire them into exec FeedStore.
```

**Action**: Delete entire `market_structure/` directory, update all callers.

### `gates/` - Generates Legacy Format
**Location**: `src/backtest/gates/`
**Status**: Still generates deprecated `signal_rules` format

```
src/backtest/CLAUDE.md:360:| `gates/` | NEEDS UPDATE | Still generates legacy signal_rules format |
```

**Action**: Update to generate `actions` format only.

---

## 2. BACKWARD COMPATIBILITY SHIMS (Violating Prime Directive)

### Entry Points

| File | Line | Shim Description |
|------|------|------------------|
| `engine.py` | 89 | "re-exported for backward compatibility" |
| `engine.py` | 582 | `_prepared_frame` for backward compatibility |
| `engine.py` | 643 | Falls back to deprecated batch structure building |
| `engine.py` | 1617 | Factory functions kept for backward compat |

### Engine Factory

| File | Line | Shim Description |
|------|------|------------------|
| `engine_factory.py` | 128 | `feature_specs_by_role` for backward compat |
| `engine_factory.py` | 248 | `warmup_bars_by_role` for backward compatibility |
| `engine_factory.py` | 307 | Backward compat for engine_data_prep |

### Features Module

| File | Line | Shim Description |
|------|------|------------------|
| `feature_frame_builder.py` | 297 | `get_registry()` deprecated alias |
| `feature_frame_builder.py` | 303 | `IndicatorRegistry` deprecated alias |
| `feature_frame_builder.py` | 343-357 | `registry` parameter deprecated |
| `features/__init__.py` | 55-57 | Deprecated aliases exported |

### Simulated Exchange

| File | Line | Shim Description |
|------|------|------------------|
| `sim/exchange.py` | 142 | Trade records "compatible with old interface" |
| `sim/exchange.py` | 197 | Config properties "for test compatibility" |
| `sim/exchange.py` | 445 | "legacy compatibility" cancel method |
| `sim/exchange.py` | 506-508 | Supports "both legacy and canonical" bar |
| `sim/bar_compat.py` | ALL | Entire file for legacy bar format |
| `sim/types.py` | 96 | Re-export Bar "for backward compatibility" |
| `sim/adapters/__init__.py` | 21 | "Aliases for backward compatibility" |

### Runtime Module

| File | Line | Shim Description |
|------|------|------------------|
| `runtime/feed_store.py` | 139-146 | Soft check for backward compatibility |
| `runtime/preflight.py` | 342 | "legacy wrapper" |
| `runtime/snapshot_view.py` | 1069 | Falls back to FeedStore structures for legacy |
| `runtime/snapshot_view.py` | 1546-1614 | Multiple legacy fallbacks |
| `runtime/types.py` | 323-408 | Multiple backward compat aliases (bar_ltf, features_ltf) |

### Rules/DSL Module

| File | Line | Shim Description |
|------|------|------------------|
| `rules/dsl_eval.py` | ALL | Entire file is re-export shim |
| `rules/dsl_nodes.py` | ALL | Entire file is re-export shim |
| `rules/dsl_parser.py` | 726-737 | Supports both 'actions' and legacy 'blocks' |

### Types & Config

| File | Line | Shim Description |
|------|------|------------------|
| `types.py` | 554-569 | Legacy `stop_reason` kept for backward compat |
| `play/__init__.py` | 4 | Re-exports "for backward compatibility" |
| `play/config_models.py` | 109 | 'isolated' deprecated alias |
| `play/risk_model.py` | 70 | Supports old `atr_key` key name |
| `system_config.py` | 811-829 | YAML SystemConfig deprecated but still present |

---

## 3. LEGACY FORMAT SUPPORT

### Dual Bar Format
**Files affected**: `sim/bar_compat.py`, `sim/exchange.py`, `sim/pricing/*.py`, `sim/execution/*.py`

The codebase supports TWO bar formats:
1. **Legacy**: Uses `timestamp` field
2. **Canonical**: Uses `ts_close` field

```python
# From sim/bar_compat.py
step_time = get_bar_timestamp(bar)  # ts_close for canonical, timestamp for legacy
```

**Action**: Remove legacy bar format support entirely.

### Dual Play Format
**Files affected**: `rules/dsl_parser.py`, `play/play.py`

Supports both:
1. **Legacy**: `signal_rules` / `blocks` key
2. **New**: `actions` key (v3.0.0)

```python
# From rules/dsl_parser.py:726
# Support both 'actions' (new) and 'blocks' (legacy)
```

**Action**: Remove `blocks` and `signal_rules` support.

### Dual Structure Format
**Files affected**: `engine_feed_builder.py`, `runtime/snapshot_view.py`

Supports both:
1. **Legacy**: `market_structure_blocks` (batch-based)
2. **New**: `structures` section (incremental)

```python
# From engine_feed_builder.py:235
"Play 'market_structure_blocks' is deprecated and will be removed 2026-04-01."
```

**Action**: Remove before 2026-04-01 deadline.

---

## 4. PLACEHOLDER IMPLEMENTATIONS

| File | Line | Placeholder |
|------|------|-------------|
| `rollup_bucket.py` | 92 | Zone interaction fields |
| `rationalization/conflicts.py` | 309 | Transition history |
| `rationalization/derived.py` | 289 | Transition history access |
| `prices/demo_source.py` | 31 | "will be completed in W5" |
| `sim/execution/slippage_model.py` | 161 | Volume-based slippage |
| `sim/pricing/spread_model.py` | 91 | Dynamic spread |
| `incremental/detectors/trend.py` | 94 | Strength calculation |

---

## 5. RECOMMENDED CLEANUP PRIORITIES

### Priority 1: Delete Deprecated Modules (1-2 days)
- [ ] Delete `market_structure/` entirely
- [ ] Update all callers to use `incremental/`
- [ ] Delete `market_structure_blocks` support from engine

### Priority 2: Remove Legacy Format Support (1 day)
- [ ] Delete `sim/bar_compat.py`
- [ ] Update all sim/ files to use canonical Bar only
- [ ] Remove `signal_rules` and `blocks` key support
- [ ] Remove YAML SystemConfig loader

### Priority 3: Delete Backward Compat Shims (2 days)
- [ ] Delete `rules/dsl_eval.py` shim
- [ ] Delete `rules/dsl_nodes.py` shim (not the directory)
- [ ] Delete deprecated aliases in `features/__init__.py`
- [ ] Delete `registry` parameter from FeatureFrameBuilder
- [ ] Remove runtime/types.py aliases (bar_ltf, features_ltf)
- [ ] Remove engine.py re-exports

### Priority 4: Update gates/ Module (0.5 day)
- [ ] Update PlayGenerator to emit `actions` format only
- [ ] Remove any `signal_rules` generation

### Priority 5: Complete Placeholders or Remove (1 day)
- [ ] Evaluate which placeholders to complete vs remove
- [ ] Either implement or delete dead code

---

## Files to Delete

```
src/backtest/market_structure/           # Entire directory
src/backtest/rules/dsl_eval.py           # Shim only
src/backtest/rules/dsl_nodes.py          # Shim only (keep dsl_nodes/ directory)
src/backtest/sim/bar_compat.py           # Legacy bar format
```

---

## Estimated Cleanup Effort

| Task | Effort | Impact |
|------|--------|--------|
| Delete market_structure/ | 1-2 days | HIGH - removes 8+ files |
| Remove legacy bar format | 1 day | HIGH - simplifies sim/ |
| Delete shim files | 0.5 day | MEDIUM - cleaner imports |
| Update callers | 1-2 days | HIGH - may break external code |
| **Total** | **4-6 days** | Significant technical debt reduction |

---

## Violations of Prime Directive

The CLAUDE.md states:

> **NO backward compatibility. NO legacy fallbacks. NO shims. EVER.**
> - Delete old code, don't wrap it
> - Update all callers, don't add aliases

Yet the codebase contains **27+ backward compatibility shims** and **2 deprecated modules** still present.
