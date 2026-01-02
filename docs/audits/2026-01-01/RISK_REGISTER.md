# TRADE Backtest Engine Risk Register

**Date**: 2026-01-01
**Source**: Agentic Audit Swarm (10 agents)
**Status**: COMPLETE

---

## Risk Classification

| Priority | Definition | Action |
|----------|------------|--------|
| P0 | Correctness bug - wrong results | Block release |
| P1 | High risk - architectural debt or incomplete feature | Fix before GA |
| P2 | Maintainability - tech debt | Schedule for cleanup |
| P3 | Polish - minor improvements | Optional |

---

## P0 Risks (Correctness)

**None found.**

---

## P1 Risks (High-Risk)

### P1-01: Version Fields Write-Only
| Field | Value |
|-------|-------|
| **ID** | AUDIT_60-P1.1 |
| **Location** | `artifact_standards.py:491-548` |
| **Description** | Version fields written to manifests but never validated on load |
| **Impact** | Silent mixing of artifacts from incompatible versions |
| **Likelihood** | Medium - occurs when engine version changes |
| **Mitigation** | Add version comparison in `RunManifest.from_dict()` |

### P1-02: Incomplete State Tracker Wiring
| Field | Value |
|-------|-------|
| **ID** | AUDIT_50-P1-1 |
| **Location** | `engine.py:972-982` |
| **Description** | Missing hooks: on_sizing_computed, on_order_submitted, on_order_filled, on_order_rejected, on_risk_check |
| **Impact** | ActionState machine never transitions beyond IDLE |
| **Likelihood** | High - affects all state tracking runs |
| **Mitigation** | Wire remaining hooks to engine order lifecycle |

### P1-03: Legacy Rules Evaluation Path Active
| Field | Value |
|-------|-------|
| **ID** | AUDIT_30-P1.1 |
| **Location** | `execution_validation.py:931-985` |
| **Description** | When `cond.has_compiled_refs()` returns False, falls back to inefficient legacy path |
| **Impact** | Performance degradation, inconsistent evaluation semantics |
| **Likelihood** | Low - requires uncompiled conditions |
| **Mitigation** | Make compilation mandatory in engine initialization |

### P1-04: No State Tracking Comparison Test
| Field | Value |
|-------|-------|
| **ID** | AUDIT_70-P1-1 |
| **Location** | Test infrastructure gap |
| **Description** | No test runs same IdeaCard with `record_state_tracking=True/False` and compares hashes |
| **Impact** | Record-only guarantee not runtime-verified |
| **Likelihood** | N/A - testing gap |
| **Mitigation** | Add explicit comparison test in validation suite |

### P1-05: Dual PIPELINE_VERSION Constants
| Field | Value |
|-------|-------|
| **ID** | AUDIT_60-P1.3 |
| **Location** | `pipeline_signature.py:19`, `runner.py:89` |
| **Description** | Two separate PIPELINE_VERSION constants could diverge |
| **Impact** | Inconsistent version stamps across artifacts |
| **Likelihood** | Medium - requires manual update in two places |
| **Mitigation** | Consolidate to single location and import |

### P1-06: Zone Width Silent 1% Fallback
| Field | Value |
|-------|-------|
| **ID** | AUDIT_40-P1.2 |
| **Location** | `zone_detector.py:248-252` |
| **Description** | Silent fallback to 1% width if ATR not available |
| **Impact** | Unexpected zone dimensions during warmup |
| **Likelihood** | Medium - affects early bars |
| **Mitigation** | Fail loudly or document warmup behavior explicitly |

### P1-07: GateContext Warmup Semantic Mismatch
| Field | Value |
|-------|-------|
| **ID** | AUDIT_50-P1-2 |
| **Location** | `engine.py:768`, `state_tracker.py:166-179` |
| **Description** | `on_warmup_check()` passes `sim_start_idx` as `warmup_bars`, but this is INDEX not count |
| **Impact** | Incorrect warmup gate evaluations |
| **Likelihood** | High - semantic confusion |
| **Mitigation** | Rename parameter or adjust comparison logic |

### P1-08: _NAMESPACE_RESOLVERS Static Class Variable
| Field | Value |
|-------|-------|
| **ID** | AUDIT_00-P1.1 |
| **Location** | `snapshot_view.py` |
| **Description** | Static class variable mutated after class definition |
| **Impact** | Test isolation issues, potential race conditions |
| **Likelihood** | Low - single-threaded execution |
| **Mitigation** | Move to instance variable or module-level constant |

### P1-09: O(n) Operations in Snapshot Methods
| Field | Value |
|-------|-------|
| **ID** | AUDIT_20-P1.1 |
| **Location** | `snapshot_view.py` get_zone_field, get_all_zones |
| **Description** | List comprehensions iterate over all zones per access |
| **Impact** | Hot loop performance degradation with many zones |
| **Likelihood** | Medium - depends on zone count |
| **Mitigation** | Pre-compute zone indices or use dict lookup |

### P1-10: cross_above/cross_below Banned But Parseable
| Field | Value |
|-------|-------|
| **ID** | AUDIT_30-P1.2 |
| **Location** | `idea_card.py:480-481`, `registry.py:101-120` |
| **Description** | YAML can specify these operators but they fail at compile time |
| **Impact** | Confusing error at compile vs parse time |
| **Likelihood** | Low - user error |
| **Mitigation** | Add YAML schema validation to reject early |

### P1-11: ARTIFACT_VERSION Development Placeholder
| Field | Value |
|-------|-------|
| **ID** | AUDIT_60-P1.2 |
| **Location** | `src/backtest/artifacts/__init__.py:35` |
| **Description** | `ARTIFACT_VERSION = "0.1-dev"` not production ready |
| **Impact** | No semantic versioning for artifact format |
| **Likelihood** | N/A - needs promotion |
| **Mitigation** | Promote to "1.0.0" once format stabilized |

### P1-12: TREND Assumes Single SWING Block
| Field | Value |
|-------|-------|
| **ID** | AUDIT_40-P1.1 |
| **Location** | `builder.py:382-389` |
| **Description** | If multiple SWING blocks exist, TREND uses arbitrary first one |
| **Impact** | Unexpected TREND source with complex configs |
| **Likelihood** | Low - dict insertion order mitigates |
| **Mitigation** | Add explicit SWING-TREND linkage |

### P1-13: Dual Close Detection Mechanism
| Field | Value |
|-------|-------|
| **ID** | AUDIT_15-P1.1 |
| **Location** | MTF feed preparation |
| **Description** | Two mechanisms for detecting candle close could diverge |
| **Impact** | Missed or duplicate HTF updates |
| **Likelihood** | Low - tested extensively |
| **Mitigation** | Consolidate to single close detection path |

### P1-14: IdeaCard Count Mismatch in CLAUDE.md
| Field | Value |
|-------|-------|
| **ID** | AUDIT_70-P1-2 |
| **Location** | `CLAUDE.md` |
| **Description** | CLAUDE.md says 21 cards, but 24 exist (V_61, V_62, V_65 added) |
| **Impact** | Documentation drift |
| **Likelihood** | N/A - documentation |
| **Mitigation** | Update CLAUDE.md to reflect current count |

### P1-15: Schema Drift Detection Missing
| Field | Value |
|-------|-------|
| **ID** | AUDIT_20-P1.2 |
| **Location** | `snapshot_view.py` |
| **Description** | No automatic detection when new namespaces added but resolvers not updated |
| **Impact** | Silent failures on new path patterns |
| **Likelihood** | Medium - occurs when extending |
| **Mitigation** | Add schema version assertion or resolver registry |

### P1-16: Legacy warmup_multiplier Reference
| Field | Value |
|-------|-------|
| **ID** | AUDIT_00-P1.2 |
| **Location** | Engine initialization |
| **Description** | warmup_multiplier removed but references may remain |
| **Impact** | Unclear warmup semantics |
| **Likelihood** | Low - mostly cleaned |
| **Mitigation** | Grep and remove any remaining references |

---

## P2 Risks (Maintainability)

| ID | Location | Description | Mitigation |
|----|----------|-------------|------------|
| P2-01 | `engine.py` | pd.isna() usage in hot path | Use np.isnan() |
| P2-02 | `engine.py` | UUID in trade ID (cosmetic nondeterminism) | Use sequential IDs |
| P2-03 | Various | JSON without sort_keys=True | Add sort_keys consistently |
| P2-04 | `types.py` | Legacy aliases SWING_OUTPUTS, TREND_OUTPUTS | Remove aliases |
| P2-05 | `StructureStore` | Mixed NaN handling in get_field() | Standardize approach |
| P2-06 | `builder.py:315` | ATR TODO not resolved | Wire ATR through |
| P2-07 | `snapshot_view.py:741` | String split in hot path | Accept pre-parsed tokens |
| P2-08 | Multiple | Duplicate operator aliases | Single source of truth |
| P2-09 | `types.py` | RULE_EVAL_SCHEMA_VERSION unused | Remove or implement |
| P2-10 | `state_tracker.py` | History manager internal access (_bars_exec) | Add public API |
| P2-11 | Validation | V_65 not wired to comparison test | Wire to test suite |
| P2-12 | `engine.py` | StateTracker.reset() not called on init | Add reset call |
| P2-13 | Engine hooks | Missing type hints | Add type annotations |
| P2-14 | `snapshot_view.py` | PRICE_FIELDS incomplete for high/low | Add missing fields |
| P2-15 | Various | mark_price_source soft-fail validation | Make fail-loud |
| P2-16 | Hash functions | Truncation to 8-16 chars | Consider full hash |
| P2-17 | `artifact_standards.py` | Renamed fields via silent fallbacks | Document or remove |
| P2-18 | `TimeframeCache` | No persistence or versioning | Add cache versioning |
| P2-19 | `structure.py` | Zone interaction smoke embedded | Extract to own file |
| P2-20 | `__init__.py` | run_state_tracking_smoke not in __all__ | Add to exports |

---

## P3 Risks (Polish)

| ID | Location | Description |
|----|----------|-------------|
| P3-01 | ReasonCode | Redundant R_ prefix | Simplify naming |
| P3-02 | Registry | Logical operators defined not implemented | Remove or implement |
| P3-03 | Types | Docstring "bullish" vs UP/DOWN naming | Align terminology |
| P3-04 | Various | Missing TYPE_CHECKING import guard | Add guards |
| P3-05 | Smoke tests | Inconsistent naming convention | Standardize |
| P3-06 | Structure smoke | Magic numbers | Extract to constants |
| P3-07 | Versioning | Inconsistent formats (semver vs "0.1-dev") | Standardize format |
| P3-08 | Parquet | Version hardcoded | Make configurable |
| P3-09 | StateTracker | ActionState unused signal_id field | Remove or use |
| P3-10 | GateContext | GATE_CODE_DESCRIPTIONS could be enum attr | Refactor |

---

## Risk Summary by Module

| Module | P0 | P1 | P2 | P3 | Total |
|--------|----|----|----|----|-------|
| engine.py | 0 | 3 | 4 | 0 | 7 |
| snapshot_view.py | 0 | 3 | 2 | 0 | 5 |
| artifact_standards.py | 0 | 2 | 2 | 1 | 5 |
| state_tracker.py | 0 | 2 | 3 | 2 | 7 |
| types.py | 0 | 0 | 3 | 1 | 4 |
| zone_detector.py | 0 | 1 | 0 | 0 | 1 |
| builder.py | 0 | 1 | 1 | 0 | 2 |
| rules/*.py | 0 | 2 | 2 | 2 | 6 |
| Other | 0 | 2 | 3 | 4 | 9 |
| **Total** | **0** | **16** | **20** | **10** | **46** |

---

**See Also:**
- [AUDIT_INDEX.md](AUDIT_INDEX.md) - Executive summary
- [FIX_PLAN.md](FIX_PLAN.md) - Ordered remediation plan

