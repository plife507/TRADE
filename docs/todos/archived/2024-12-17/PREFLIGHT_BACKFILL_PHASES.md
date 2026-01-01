# IdeaCard → Preflight → Auto-Backfill → Engine Integration

**Status**: ✅ COMPLETE (All Phases 1-7 Complete)  
**Created**: 2024-12-17  
**Completed**: 2024-12-17  
**Owner**: Claude  

## Objective

Eliminate warmup drift by enforcing a single compute point: **Existing Preflight tool computes WarmupRequirements exactly once from the IdeaCard indicator declarations**, validates DB coverage (including internal gaps), auto-backfills via existing data tools when needed, then outputs canonical warmup for Runner to persist into `SystemConfig.warmup_bars_by_role`. The Engine reads **only** from `SystemConfig` and fails loud if warmup is missing/partial.

**Key Constraint**: Do NOT add a new preflight system. Only extend the current Preflight tool (`src/backtest/runtime/preflight.py`).

---

**Note**: This document is archived. All phases (1-7) are complete as of 2024-12-17. See `docs/todos/INDEX.md` for current active TODOs.
