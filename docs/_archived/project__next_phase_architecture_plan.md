# Next Phase Architecture & Refactor Plan

**Last Updated:** December 14, 2025  
**Purpose:** Lock architectural intent before refactors, control cost and scope, prepare engine for market-structure abstractions and agent-generated IdeaCards  
**Status:** Planning and alignment document (not implementation spec)

---

## Purpose
This document captures the concrete decisions and next design phases agreed in the current discussion. It exists to:
- Lock architectural intent before refactors
- Control cost and scope (especially Opus usage)
- Prepare the engine for market-structure abstractions and agent-generated IdeaCards
- Preserve auditability and correctness at every step

This is a **planning and alignment document**, not an implementation spec.

---

## Guiding Principles (Locked)

1. **Closed-candle truth only**  
   All features (TA, market structure, forecasts) are computed on *closed candles only*. HTF/MTF values are forward-filled until the next close.

2. **Precompute intelligence, execute cheaply**  
   Indicators, market structure, regimes, and forecasts are computed *outside* the hot loop. The hot loop only indexes arrays and evaluates decisions.

3. **Artifacts are the contract**  
   Artifact schemas and keys remain stable unless intentionally versioned. Refactors must not change math outputs unless explicitly approved.

4. **Audit before optimization**  
   Any refactor must pass the existing audit engine before moving to the next phase.

5. **IdeaCards are a DSL, not config**  
   IdeaCards are treated as a compiled language with parsing, validation, normalization, and linting phases.

---

## Phase Roadmap (Agreed Order)

### Phase 1 — Array-Backed Snapshot Preparation (Current Focus)
**Goal:** Remove pandas from the hot loop and prepare the engine for additional feature layers.

**Scope:**
- Internal execution only (no artifact changes)
- Preserve indicator math and snapshot semantics

**Key Changes:**
- Replace `df.iloc[i]` with array indexing
- Freeze feature keys once (no per-bar schema discovery)
- Precompute `ts_close → index` maps for HTF/MTF
- Snapshot reads from NumPy arrays, not pandas rows

**Explicit Non-Goals:**
- No Parquet yet
- No market structure computation yet
- No audit logic changes

**Acceptance Gate:**
- All existing audits pass with identical results

---

### Phase 2 — Audit Lock-In
**Goal:** Prove that Phase 1 changed plumbing, not math.

**Actions:**
- Run full audit suite (contract + math parity)
- Confirm:
  - identical output keys
  - identical NaN masks
  - identical values within tolerance

**Outcome:**
- Array-backed execution is now the trusted baseline

---

### Phase 3 — Artifact Upgrade (CSV → Parquet)
**Goal:** Improve IO, size, and scalability without changing semantics.

**Scope:**
- Replace CSV artifacts with Parquet (optionally dual-write during transition)
- Update audit readers to support Parquet

**Non-Goals:**
- No engine math changes
- No feature semantics changes

**Acceptance Gate:**
- Audits pass reading Parquet artifacts

---

### Phase 4 — Market Structure Feature Layer
**Goal:** Introduce market structure as first-class, array-backed features.

**Design Rules:**
- Market structure is computed per TF, outside the hot loop
- Outputs are either:
  - Dense per-bar arrays (levels, states, distances)
  - Sparse event streams + forward-filled state arrays

**Examples:**
- `pivot_high_level`
- `trend_state` (enum → int)
- `active_ob_id`
- `distance_to_nearest_sr`

**Integration Point:**
- Market structure outputs live alongside indicators in the same FeedStore / snapshot access model

---

### Phase 5 — Multi-IdeaCard System Composition
**Goal:** Allow multiple IdeaCards to compose into a single System.

**Concept:**
- Each IdeaCard produces feature specs (TA, structure, risk hints)
- A System is a composition of IdeaCards + symbol + TF mapping + risk profile
- The strategy sees a unified feature namespace

---

## IdeaCard Normalizer: Planned Extensions

### 1. Timeframe Compatibility Validation (Backlog)
Add validation that each feature/indicator/structure spec is compatible with:
- Its declared role (`exec`, `htf`, `mtf`)
- Its declared timeframe
- Warmup/lookback feasibility for the configured window

**Failure Mode:**
- Hard error (fail fast)

**Error Output Must Include:**
- Offending output key
- Declared TF/role
- Expected compatible TFs or rule
- Suggested fixes

---

### 2. Semantic Misuse Linting (Backlog)
Add a semantic lint pass that flags likely conceptual mistakes, such as:
- Treating oscillators as price levels
- Comparing incompatible units (e.g., ATR vs RSI)
- Using crossover logic on unscaled features
- Referencing features outside their semantic domain (price vs momentum vs volatility)

**Defaults:**
- Non-fatal warnings
- Optional `strict` mode to fail

**Lint Output:**
- Structured
- Attributable (rule_id, affected keys, message)

---

## Role of the Audit Engine (Confirmed)

The existing audit engine remains valid across all phases because:
- Indicator math remains unchanged
- Artifacts preserve schema and keys
- Refactors are transport-level, not semantic-level

Future extensions (market structure, forecasts) will reuse the same audit philosophy:
- Contract audit
- Parity audit against a reference implementation

---

## Cost-Control Strategy (Opus Usage)

- Use plan-first prompts with strict scope
- Implement one phase at a time
- Stop immediately when audits pass
- Avoid multi-phase refactors in a single Opus run

---

## Summary

You are building:
- A trading **platform**, not a bot
- A **DSL for ideas**, not hardcoded strategies
- An engine that can scale with agents safely

This plan keeps correctness, cost, and future abstraction aligned.

**Status:** Ready for Phase 1 execution

**Links:** Referenced by `PROJECT_OVERVIEW.md` and `PROJECT_ROADMAP.md` as the canonical next-phase plan.

