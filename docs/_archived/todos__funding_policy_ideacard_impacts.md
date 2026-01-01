## Funding Policy in IdeaCards — Validation & Audit Impacts (TODOs)

**Status**: ✅ Complete (documentation-only)  
**Date**: 2025-12-17  
**Scope**: Define an explicit `sim.funding.enabled` IdeaCard contract and document how it impacts validation, preflight, and verification/audit systems.

### Phase 1 — Contract + Validation Surface Mapping

- [x] Define proposed IdeaCard field shape (`sim.funding.enabled`)
- [x] Identify build-time YAML validator touchpoints (`idea_card_yaml_builder.py`)
- [x] Identify runtime IdeaCard execution contract gates (`execution_validation.py`)
- [x] Identify adapter/runner propagation points (IdeaCard → engine)

### Phase 2 — System Implications + Migration Guidance

- [x] Document preflight/data-health implications (required_series branching)
- [x] Document audit/verify-suite implications (artifact diffs vs parity)
- [x] Provide migration plan for existing IdeaCards (explicit default + staged enable)
- [x] Provide review checklist + acceptance commands (CLI-first)


