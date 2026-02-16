# Live Trading Readiness -- Global Overview

## Gate Status

| Gate | Theme | Status | Hours Est | Date |
|------|-------|--------|-----------|------|
| G14 | Crash Fixes & Safety Blockers | COMPLETE | ~4h | 2026-02-10 |
| G15 | MVP Live CLI | COMPLETE | ~16h | 2026-02-10 |
| G16 | Production Hardening | COMPLETE | ~12h | 2026-02-10 |
| G17 | Operational Excellence | COMPLETE | ~16h | 2026-02-10 |

## Dependency Graph

```
G14 (P0) --> G15 (P1) --> G16 (P2) --> G17 (P3)

G14: Fix crashes & safety blockers   (no new features, just fixes)
G15: MVP live CLI                     (operator can run & monitor demo/live)
G16: Production hardening             (safe for unsupervised running)
G17: Operational excellence           (monitoring, journal, notifications)
```

## Tracking Files

| File | Purpose |
|------|---------|
| `docs/plans/G14_CRASH_FIXES.md` | Gate 14 detail with checkboxes |
| `docs/plans/G15_MVP_LIVE_CLI.md` | Gate 15 detail with checkboxes |
| `docs/plans/G16_PRODUCTION_HARDENING.md` | Gate 16 detail with checkboxes |
| `docs/plans/G17_OPERATIONAL_EXCELLENCE.md` | Gate 17 detail with checkboxes |
