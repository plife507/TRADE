## Project Review — DuckDB + Indicators + Debug Guide (Docs)

Purpose: write a high-signal, repo-specific markdown review of the current project state, focused on:
- DuckDB historical data access (env routing, tables, timestamps)
- Indicator availability + explicit declaration (FeatureSpec / IdeaCard)
- A practical debugging checklist for the next round of fixes

---

### Phase 1 — Review document content

- [x] Write an overview of the runtime/backtest + data pipeline (IdeaCard → Engine)
- [x] Document DuckDB env routing + table naming + timestamp semantics
- [x] Document current supported indicator types + output key conventions
- [x] Document how to declare indicators in IdeaCards (per TF role)
- [x] Add a debugging checklist (env, coverage, warmup, keys, MTF readiness)

---

### Acceptance criteria

- [x] Document lives under `docs/reviews/` and is specific to this repo (no generic filler)
- [x] Includes concrete file pointers (`src/data/historical_data_store.py`, `src/backtest/features/*`, `configs/idea_cards/*`)
- [x] Includes at least one minimal IdeaCard example showing feature_specs and key naming
- [x] Provides a short “common failure → likely cause” section for debugging


