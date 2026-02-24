# TRADE TODO

Single source of truth for all open work, bugs, and task progress.

---

## Completed Work

| Item | Date | Summary |
|------|------|---------|
| Liquidation Parity (Bybit) | 2026-02 | Full parity review |
| Fast Parallel Validation | 2026-02 | Phases 1-7 |
| Health Audit Fixes | 2026-02-18 | near_pct fixed, legacy cleanup |
| Backtest Safety Gaps 3-6 | 2026-02 | GAP-3/4/5/6 all fixed |
| Full Codebase Review | 2026-02-17 | 10 files, 253 KB, 120 findings |
| Codebase Review Gates 1-8 | 2026-02-17 | 80+ fixes across DSL, sim, warmup, live safety, data, CLI |
| CLI & Tools Module Splitting (P4.5) | 2026-02-19 | 5 gates, -113 lines dedup |
| Debug & Logging Redesign (P6) | 2026-02-19 | 8 phases: plumbing, verbosity, trace, metrics, journal |
| Live Dashboard Redesign (P7) | 2026-02-19 | Modular package, Rich rendering, tiered refresh, signal proximity |
| Dead Code Audit + Cleanup (P9) | 2026-02-20 | 44 findings, 471 lines deleted. See `docs/DEAD_CODE_AUDIT.md` |
| Structure Detection Audit | 2026-02-20 | Swing/trend/MS on real BTC data. See `docs/STRUCTURE_DETECTION_AUDIT.md` |
| Codebase Review Pass 3 | 2026-02-21 | 51 findings, 49 confirmed by agent verification |
| P10 Phase 1: Critical Live Blockers | 2026-02-21 | 5 fixes (C1, C4, C6, H1, H17) |
| P10 Phase 2: High Live Safety | 2026-02-21 | 10 fixes (C2, C3, H2-H4, H6-H10) |
| P10 Phase 3: Exchange Integration | 2026-02-21 | 4 fixes (H11, H14, M6, M14) |
| P10 Phase 4: Backtest/Engine | 2026-02-21 | 7 fixes + H22 deferred + M16 not-a-bug |
| P10 Phase 5: Data/CLI/Artifacts | 2026-02-21 | 8 fixes (H12, H13, H15, H19, M1, M2, M11, M15) |
| P10 Phase 6: Low Priority | 2026-02-21 | 11 fixes (C5, H5, H16, H18, H20, M3, M9, M10, M12, M17, M19) |
| Codebase Review Pass 4 | 2026-02-21 | 6-agent team, 319 files, 89 findings. See `docs/CODEBASE_REVIEW_2026_02_21.md` |
| P11 Phase 1-3: Codebase Review Fixes | 2026-02-21 | 27 fixes across live safety, correctness, architecture. See `docs/CODEBASE_REVIEW_2026_02_21.md` |
| P11 Phase 4: Performance & Polish | 2026-02-21 | MonotonicDeque, SMA drift guard, factory dict, dead code, naive datetime fix |
| P12 Phase 1-5 items (partial) | 2026-02-21 | Stale monitor fix, tri-state WS, lazy WS, dashboard log tab. Manual verification pending |
| Timestamp & WS Subscription Fix | 2026-02-21 | 7 files: tz-naive UTC convention, canonical `_datetime_to_epoch_ms`, kline sub default `[]` |
| CLI Redesign P4 Gates 4-5 | 2026-02-22 | Unified `_place_order()` + data sub-menus implemented. Only G8 (final validation) remains |
| CLI Architecture Audit | 2026-02-22 | 103 tools inventoried, 84 unwired. See `docs/CLI_ARCHITECTURE_AUDIT.md` |
| P15 Phases 1-4: Cooldown & Race Fixes | 2026-02-22 | Cross-process locking, atomic writes, 15s cooldown, two-phase reservation |
| Path Migration: ~/.trade → data/runtime/ | 2026-02-22 | 10 files migrated, centralized constants, test prompt updated |
| Cross-Platform Newline Compliance | 2026-02-22 | 4 artifact writers fixed, 21/21 write ops verified |

Full details: `docs/architecture/CODEBASE_REVIEW_ONGOING.md`

---

## Deferred Items

Confirmed issues, low-risk, deferred to appropriate milestones.

### Pre-Deployment (fix before live trading)

- [ ] **GAP-2** No REST API fallback for warmup data. `_load_tf_bars()` tries buffer -> DuckDB -> fails. Needed for cold-start live. *(P12: REST path now forces UTC-naive timestamps, but fallback still not wired in _load_tf_bars.)*
- [ ] **DATA-011** `_handle_stale_connection()` does REST refresh but doesn't force pybit reconnect. Adding active reconnect risky without integration testing. *(Partially addressed 2026-02-21: stale handler no longer falsely marks connections as RECONNECTING, but active reconnect still not implemented.)*
- [ ] **DATA-017** `panic_close_all()` cancel-before-close ordering — defensible tradeoff, needs integration test to reverse.
- [ ] **H22** `backtest_runner.py` — Sim accepts `funding_events` kwarg but no funding event generation pipeline exists yet.

### Optimization (before sustained live sessions)

- [ ] **ENG-BUG-015** `np.append` O(n) on 500-element arrays, ~3-10 MB/hour GC pressure

### Future Features (no correctness impact)

- [ ] **IND-006** Validate warmup estimates match actual `is_ready()` thresholds
- [ ] **SIM-MED-3** `ExchangeMetrics` class (217 lines) — needs result schema wiring
- [ ] **SIM-MED-4** `Constraints` class (193 lines) — needs per-symbol constraint config

---

## Known Issues (non-blocking)

### pandas_ta `'H'` Deprecation Warning

Cosmetic warning, no impact. `pandas_ta.vwap()` passes uppercase `'H'` to `index.to_period()`. Only affects VWAP with hourly anchors. Our `IncrementalVWAP` (live) is unaffected.

---

## Open Feature Work

### P8: Structure Detection Fixes

See `docs/STRUCTURE_DETECTION_AUDIT.md` for full audit.

#### Phase 1: Fix Config Defaults
- [ ] Change `confirmation_close` default to `True` in `market_structure.py`
- [ ] Add recommended defaults to play templates: `min_atr_move: 0.5` or `strict_alternation: true`
- [ ] Document trend/MS timing mismatch in `docs/PLAY_DSL_REFERENCE.md`
- [ ] **GATE**: `python trade_cli.py validate quick` passes

#### Phase 2: Trend Detector Review
- [ ] Investigate why `strength=2` never fires on real BTC data (4h/12h/D, 6 months)
- [ ] Consider reducing consecutive-pair requirement or increasing wave history size
- [ ] **GATE**: Trend reaches `strength=2` at least once on 6-month BTC 4h data

#### Phase 3: Trend/MS Synchronization (Design Decision)
- [ ] Decide approach: accept mismatch / make MS depend on trend / add pending CHoCH / speed up trend / slow down MS
- [ ] Implement chosen approach
- [ ] **GATE**: `python trade_cli.py validate standard` passes

#### Phase 4: CHoCH Correctness
- [ ] Track which swing produced the last BOS
- [ ] CHoCH only valid when breaking the BOS-producing swing level
- [ ] **GATE**: `python trade_cli.py validate quick` passes

### P11: Codebase Review 2026-02-21 Fixes

Full review: `docs/CODEBASE_REVIEW_2026_02_21.md` — 89 findings (5 critical, 19 high, 32 medium, 33 low).

Phases 1-4 complete (27 fixes). Remaining:

- [ ] **M-C4**: Replace ~48 bare `assert isinstance(...)` with explicit checks in `cli/menus/*.py` (deferred — large mechanical change)
- [ ] **GATE**: `python scripts/run_full_suite.py` — 170/170 pass

### P12: Lazy WebSocket & Live WS Health — Full Audit

**Context:** Session 2026-02-21 implemented lazy WS (REST-first, WS on demand) and found critical bugs
in the stale monitor / health check chain that **blocked all signal execution in demo/live mode**.
Fixes applied across 14 files. Timestamp/subscription cleanup also done in this session.

**Completed (2026-02-21):**
- [x] `ConnectionState.NOT_STARTED` to distinguish "never started" from "lost connection"
- [x] Fixed `WebSocketConfig.auto_start` default (`True` → `False`)
- [x] Tri-state WS status in diagnostics tool + CLI display formatter
- [x] Renamed `setup_websocket_cleanup` → `setup_position_close_cleanup`
- [x] Added `app.stop_websocket()` after engine thread joins in BOTH `play.py` and `plays_menu.py`
- [x] **CRITICAL**: Fixed stale monitor — was tracking private stream silence as "stale" (false positive every 60s)
- [x] **CRITICAL**: Fixed stale handler — was marking connections as RECONNECTING, breaking `is_websocket_healthy()`
- [x] Fixed Log tab scroll direction (Up=older, Down=newer), added LIVE indicator, filter-empty message
- [x] Downgraded "already subscribed" re-subscribe errors to DEBUG
- [x] **Timestamp fix**: Enforced UTC-naive convention across live path (7 files), canonical `_datetime_to_epoch_ms()`
- [x] **Kline subscription fix**: Default `kline_intervals` changed from `["15"]` to `[]`, LiveRunner subscribes only play TFs
- [x] **REST/DuckDB bar loading**: Force UTC-naive on `fromisoformat()` output

#### Remaining: Manual verification
- [ ] Run demo play 10+ minutes — confirm NO "Signal execution blocked" warnings
- [ ] Confirm `is_websocket_healthy()` returns `True` throughout
- [ ] Run play A → stop → play B → verify no stale symbols leak
- [ ] Health Check shows correct tri-state WS display (not started / connected / stopped)
- [ ] **GATE**: Two sequential demo plays, zero post-exit warnings

### P1: Live Engine Rubric

- [ ] Define live parity rubric: backtest results as gold standard
- [ ] Demo mode 24h validation
- [ ] Verify sub-loop activation in live mode

### P2: Live Trading Integration

- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Paper trading integration
- [ ] Complete live adapter stubs

### P4+P13: Unified CLI — Full Agent Autonomy + Human Menu Cleanup

See `docs/CLI_ARCHITECTURE_AUDIT.md` for full architecture reference.
See `docs/brainstorm/CLI_AGENT_AUTONOMY.md` for original gap audit (103 tools, 84 unwired).

**Context:** P4 (interactive menu redesign) Gates 4-5 are DONE — `_place_order()` and data sub-menus
are fully implemented. P13 (agent CLI flags) implemented 2026-02-22: 6 phases wiring 50+ tool functions
into argparse subcommands. Both efforts share the same `src/tools/` layer.

**Architecture:** Each new subcommand follows the established 3-layer pattern:
1. Argparse definition in `src/cli/argparser.py` via `_setup_{domain}_subcommands()`
2. Handler function in `src/cli/subcommands/{domain}.py` (parse args → call tool → format output)
3. Export in `__init__.py` + dispatch in `trade_cli.py`

#### Phase 1: Order Subcommand Group (DONE 2026-02-22)

- [x] `order buy/sell` — market, limit, stop, stop-limit with all flags
- [x] `order list/amend/cancel/cancel-all/leverage/batch`
- [x] Wire into `argparser.py`, `__init__.py`, `trade_cli.py` dispatch
- [x] `pyright src/cli/subcommands/order.py` — 0 errors

#### Phase 2: Data Subcommand Group (DONE 2026-02-22)

- [x] `data sync/info/symbols/status/summary/query/heal/vacuum/delete`
- [x] Wire into `argparser.py`, `__init__.py`, `trade_cli.py` dispatch
- [x] `pyright src/cli/subcommands/data.py` — 0 errors

#### Phase 3: Market Data Subcommand Group (DONE 2026-02-22)

- [x] `market price/ohlcv/funding/oi/orderbook/instruments`
- [x] Wire into `argparser.py`, `__init__.py`, `trade_cli.py` dispatch
- [x] `pyright src/cli/subcommands/market.py` — 0 errors

#### Phase 4: Account History Extensions (DONE 2026-02-22)

- [x] `account info/history/pnl/transactions/collateral`
- [x] Extended argparse group + dispatch
- [x] `pyright src/cli/subcommands/trading.py` — 0 errors

#### Phase 5: Position Config Extensions (DONE 2026-02-22)

- [x] `position detail/set-tp/set-sl/set-tpsl/trailing/partial-close/margin/risk-limit`
- [x] Extended argparse group + dispatch
- [x] `pyright src/cli/subcommands/trading.py` — 0 errors

#### Phase 6: Health & Diagnostics Subcommand Group (DONE 2026-02-22)

- [x] `health check/connection/rate-limit/ws/environment`
- [x] Wire into `argparser.py`, `__init__.py`, `trade_cli.py` dispatch
- [x] `pyright src/cli/subcommands/health.py` — 0 errors

#### Phase 7: Final Validation (P4 G8 + P13 completion)

- [x] `python trade_cli.py validate quick` passes (74.1s, all 5 gates)
- [x] CLI: all new subcommand groups respond to `--help`
- [x] pyright: 0 errors across all 8 modified files
- [ ] Manual: app starts → offline menu → backtest works without connection
- [ ] Manual: "Connect to Exchange" (demo) → full menu appears
- [ ] Manual: place market order via unified form (P4 G4 verification)
- [ ] Manual: symbol quick-picks appear after first use (P4 G3 verification)
- [ ] Manual: data sub-menus accessible, all operations reachable (P4 G5 verification)
- [ ] Manual: cross-links between Forge and Backtest work (P4 G7 verification)
- [ ] CLI: `order buy --symbol BTCUSDT --amount 100 --type market --json` succeeds on demo
- [ ] CLI: `data info --json` returns valid JSON
- [ ] CLI: `market price --symbol BTCUSDT --json` returns valid JSON
- [ ] CLI: `health check --json` returns valid JSON
- [ ] **GATE**: Full manual test pass

### P14: Play Lifecycle — Headless Mode + Agent Test

**Context:** `play run --mode demo` blocks on a Rich Live dashboard, making it impossible
for agents to start a play, poll its status, then stop it. Added `--headless` flag and
`play watch --json` for agent-friendly lifecycle control.

#### Phase 1: Add `--headless` flag to `play run` (DONE 2026-02-22)
- [x] `--headless` flag in argparser for `play run`
- [x] `_run_play_live_headless()` — JSON events on stdout, blocks until stopped
- [x] `_run_play_live_dashboard()` — extracted original dashboard behavior unchanged
- [x] Pyright: 0 errors

#### Phase 2: Add `--json` to `play watch` (DONE 2026-02-22)
- [x] `--json` flag in argparser for `play watch`
- [x] One-shot JSON snapshot mode (consistent with `play status --json`)
- [x] Smoke test: `play watch --json` returns `{"instances": []}` when idle

#### Phase 3: Play Lifecycle Test Prompt (DONE 2026-02-22)
- [x] Group 9 (T36-T50) added to `docs/AGENT_CLI_TEST_PROMPT.md`
- [x] System prompt updated with headless workflow instructions

#### Phase 4: Verification
- [ ] Smoke test: `play run --play AT_001 --mode demo --headless` prints JSON, Ctrl+C stops cleanly
- [ ] Smoke test: While headless running, `play watch --json` shows instance
- [ ] Smoke test: `play stop --all` cleans up headless instance
- [ ] Full T36-T50 test sweep
- [ ] **GATE**: All 50 tests pass

### P15: Instance Exit Cooldown & Race Condition Fixes

**Context:** `EngineManager._check_limits()` was process-local only — it checked in-memory counters
but never read cross-process PID files. Two terminal sessions could both pass the limit check
and start live instances simultaneously, violating the "max 1 live" safety rule. Additionally,
after SIGTERM, a new instance could start immediately while the old process was still cancelling
orders (up to 10s), closing WebSocket (up to 5.5s), or holding DuckDB locks.

**File:** `src/engine/manager.py` (single file change)

#### Phase 1: Cross-process locking & atomic writes (DONE)
- [x] Add `fcntl.flock()` advisory file lock on `~/.trade/instances/.lock`
- [x] Add `_instance_lock()` context manager for cross-process critical section
- [x] Atomic file writes via `tempfile.mkstemp()` + `os.replace()` (prevents partial JSON)
- [x] Add `_DiskInstance` dataclass for typed disk instance representation
- [x] Add `_read_disk_instances(clean_stale=True)` centralized disk reader
- [x] **GATE**: `pyright src/engine/manager.py` — 0 errors

#### Phase 2: Cooldown system (DONE)
- [x] Add `_INSTANCE_COOLDOWN_SECONDS = 15.0` constant
- [x] `_write_cooldown_file()` — writes `status: "cooldown"` + `cooldown_until` timestamp
- [x] `_write_cooldown_file_raw()` — same but from raw disk data (for cross-process stop)
- [x] `stop()` writes cooldown file instead of deleting instance file
- [x] `stop_cross_process()` writes cooldown file after SIGTERM
- [x] `_run_instance()` crash handler writes cooldown file (prevents crash-restart loops)

#### Phase 3: Cross-process limit checking (DONE)
- [x] `_check_limits()` reads disk instances (running + cooldown + starting)
- [x] Excludes in-memory instances to avoid double-counting
- [x] Informative error messages with cooldown remaining time
- [x] Two-phase slot reservation in `start()`: lock → check → reserve → unlock → setup → upgrade

#### Phase 4: Cleanup & listing (DONE)
- [x] `_read_disk_instances()` cleans stale PIDs, expired cooldowns, invalid JSON
- [x] `list_all()` uses `_read_disk_instances()` (replaces 40-line inline loop)
- [x] `__init__()` calls cleanup at startup for orphaned files from previous crashes
- [x] **GATE**: `python3 trade_cli.py validate quick` — 5/5 gates pass

#### Phase 5: Verification
- [ ] Manual: start demo → stop → verify cooldown file exists → try restart immediately (should fail) → wait 15s → restart succeeds
- [ ] Manual: start headless → try second start in different terminal (should fail with limit error)
- [ ] Manual: create fake instance file with dead PID → run `play status` → verify cleaned up
- [ ] **GATE**: Full manual test pass

### P16: Cross-Platform & Codebase Health Audit

**Context:** Full codebase audit (7 Sonnet 4.6 agents, 323 Python files) found 54 OS-level issues,
38 `datetime.now()` violations (local time instead of UTC), 5 missing `encoding="utf-8"`, 6 critical
`manager.py` design bugs, and 3 dead directories at the project root. All findings verified before
any code changes.

#### Phase 1: datetime.now() → UTC (CRITICAL — live trading correctness)

`datetime.now()` returns local time. On Windows in EST (UTC-5), daily loss reset fires 5 hours late.
All 38 occurrences must change to `datetime.now(timezone.utc).replace(tzinfo=None)`.

**Priority A — Live trading path (7 fixes):**
- [x] `src/core/position_manager.py` lines 152, 193, 268, 290, 382, 522 — daily loss reset, portfolio snapshots
- [x] `src/core/order_executor.py` line 44 — OrderResult timestamp
- [x] **GATE**: `pyright src/core/position_manager.py src/core/order_executor.py` — 0 errors

**Priority B — Engine/runner infrastructure (19 fixes):**
- [x] `src/engine/manager.py` lines 225, 339, 356, 389, 501, 620, 819, 903 — cooldown timers, instance tracking
- [x] `src/engine/runners/live_runner.py` lines 87, 267, 373, 497, 506, 845 — runner stats, reconcile intervals
- [x] `src/engine/runners/shadow_runner.py` lines 166, 188, 254 — shadow stats
- [x] `src/engine/runners/backtest_runner.py` lines 289, 448 — artifact timestamps
- [x] **GATE**: `pyright src/engine/manager.py src/engine/runners/*.py` — 0 errors

**Priority C — CLI/tools/menus (12 fixes):**
- [x] `src/tools/backtest_play_tools.py` lines 138, 602 — default end date
- [x] `src/tools/backtest_play_data_tools.py` line 244 — default end date
- [x] `src/cli/utils.py` lines 273, 296, 336 — CLI date defaults
- [x] `src/cli/menus/backtest_play_menu.py` line 237 — menu default
- [x] `src/cli/menus/data_sync_menu.py` line 106 — sync default
- [x] `src/cli/smoke_tests/data.py` line 315 — smoke test anchor
- [x] `src/backtest/risk_policy.py` line 227 — risk snapshot
- [x] `src/backtest/snapshot_artifacts.py` line 59 — manifest
- [x] `src/backtest/artifacts/manifest_writer.py` lines 67, 136 — created_at, written_at
- [x] **GATE**: `python3 trade_cli.py validate quick` — 5/5 gates pass

#### Phase 2: manager.py Critical Fixes

- [x] Line 62: Replace `get_logger()` with `get_module_logger(__name__)` per CLAUDE.md
- [x] Line 266: `_is_pid_alive` — catch `PermissionError` (EPERM) separately, treat as alive (process exists but different user)
- [x] Line 194: Windows `msvcrt.LK_LOCK` — add retry loop with 30s deadline to match `fcntl.LOCK_EX` blocking semantics
- [x] Lines 624-629: Move `self._instances[instance_id] = instance` and `_update_counts` BEFORE `asyncio.create_task()`
- [x] Lines 638-642: Add count rollback in `except` block when `_write_instance_file` raises after `_update_counts`
- [x] Line 769: Use `self._instances.pop(iid, None)` in `_run_instance` crash handler (idempotent delete)
- [x] Line 916: Wrap `InstanceMode(d.mode)` in `list_all()` with try/except ValueError
- [x] Line 940: Windows `_is_pid_alive` — check `GetExitCodeProcess` for `STILL_ACTIVE(259)` to handle zombie PIDs
- [x] **GATE**: `pyright src/engine/manager.py` — 0 errors
- [x] **GATE**: `python3 trade_cli.py validate quick` passes

#### Phase 3: Missing encoding="utf-8" (5 files)

On Windows default encoding is cp1252. Non-ASCII content produces mojibake.

- [x] `src/backtest/snapshot_artifacts.py` line 247 — add `encoding="utf-8"` to write
- [x] `src/backtest/snapshot_artifacts.py` line 274 — add `encoding="utf-8"` to read
- [x] `src/forge/audits/audit_in_memory_parity.py` line 74 — add `encoding="utf-8"` to CSV write
- [x] `src/engine/adapters/state.py` line 92 — add `encoding="utf-8"` to NamedTemporaryFile
- [x] `src/engine/adapters/state.py` line 122 — add `encoding="utf-8"` to load_state read
- [x] `src/forge/audits/audit_rollup_parity.py` line 624 — add `encoding="utf-8"` to NamedTemporaryFile
- [x] `src/backtest/artifacts/artifact_standards.py` line 513 — add `encoding="utf-8"` to write_text
- [x] `src/backtest/artifacts/pipeline_signature.py` line 83 — add `encoding="utf-8"` to write_text
- [x] **GATE**: `pyright` on all modified files — 0 errors

#### Phase 4: Stale Docstrings & Path Consistency

- [x] `src/engine/manager.py` lines 8, 184 — update docstrings from `~/.trade/instances/` to `data/runtime/instances/`
- [x] `src/engine/runners/live_runner.py` line 249 — update `is_paused` docstring
- [x] `src/config/constants.py` line 18 — fix comment: "process state under data/runtime/, trade journal under data/journal/"
- [x] `src/cli/validate.py` lines 358, 1204, 1317 — replace relative `Path("plays")` with `PROJECT_ROOT / "plays"`
- [x] Pause file consistency: `src/cli/subcommands/play.py` line 892 and `src/cli/menus/plays_menu.py` line 844 — change `.touch()` to `.write_text("paused", encoding="utf-8", newline="\n")`
- [x] `src/cli/dashboard/input.py` line 164 — remove `kbhit()` guard on arrow key second byte, call `getch()` unconditionally
- [x] **GATE**: `python3 trade_cli.py validate quick` passes

#### Phase 5: Root Directory Cleanup

- [x] Delete `src.backtest.data_builder/` — orphaned crash artifact (Feb 17 log files, nothing references it)
- [x] Delete `strategies/` — empty dead shell, `system_config.py:43` CONFIGS_DIR points to nonexistent `src/strategies/configs`
- [x] Remove dangling `CONFIGS_DIR` from `src/backtest/system_config.py` line 43 and `src/config/config.py` line 488
- [ ] Evaluate `tests/` — 204 superseded validation plays, canonical plays in `plays/`. Restored after accidental deletion; keep for now
- [x] Add `demo_run_*.txt` and `market-structure-explorer.html` to `.gitignore`
- [x] Update `data/README.md` — add `runtime/`, `journal/`, `market_data_backtest.duckdb` to documentation
- [x] **GATE**: `git status` shows no unexpected untracked files

#### Phase 6: Test Prompt Fixes (AGENT_CLI_TEST_PROMPT.md)

- [x] T45 (line 289): Add `Start-Sleep 16` before Start-Process (cooldown wait)
- [x] T49 (line 293): Write full Start-Process command instead of prose reference
- [x] T56 (line 329): Guard `$proc.Id` with `if ($null -ne $proc)` to prevent null dereference
- [x] T62 (line 335): Same null guard for `$proc60.Id`
- [x] T57 (line 330): Change fake PID from 99999 to 9999999 (exceeds PID_MAX, guarantees dead)
- [x] Remove unused `$instDir` shorthand definition (lines 317-320) or use it in all test cells

### P17: Play Stop Process Kill + Pre-Launch Duplicate Check

**Context:** WSL agent test run (2026-02-22) scored 53/62. All 9 failures trace to 2 bugs:
1. `play stop --force` removes the instance file but doesn't kill the OS process. The background
   Python process keeps running (holding DuckDB locks, WebSocket connections). Next instance launch
   crashes on DuckDB lock instead of starting cleanly.
2. No pre-launch per-symbol duplicate check. When a second instance is requested for an already-running
   symbol, the system lets it start up and crash on DuckDB lock instead of failing fast with a clean
   "already running" error.

**Test results:** See `docs/AGENT_CLI_TEST_PROMPT.md` — WSL Run (53/62), Windows Run 8 (45/62).

#### Phase 1: Process kill on `play stop`
- [x] `_terminate_pid()` — extracted cross-platform SIGTERM/TerminateProcess helper
- [x] `_force_kill_pid()` — SIGKILL (Unix) / TerminateProcess (Windows) last-resort kill
- [x] `stop_cross_process()` refactored: `_terminate_pid()` → 5s wait → `_force_kill_pid()` fallback → 2s wait
- [x] Handle `ProcessLookupError` (already dead) and `PermissionError` (different user) gracefully
- [x] **GATE**: `pyright src/engine/manager.py` — 0 errors
- [x] **GATE**: `python3 trade_cli.py validate quick` — 5/5 gates pass

#### Phase 2: Pre-launch duplicate symbol check
- [x] In `start()` or `_check_limits()`: read disk instances, reject if same symbol already has `status=running` with alive PID
- [x] Clean error message: "Instance already running for BTCUSDT (PID 12345). Use `play stop` first."
- [x] **GATE**: `pyright src/engine/manager.py` — 0 errors

#### Phase 3: Verification
- [x] WSL test: start headless → stop → verify PID killed → start second headless (should succeed)
- [x] WSL test: start headless → attempt second start same symbol (should fail with clean error)
- [x] Stale cleanup still works (fake dead PID file → play status → cleaned)
- [x] `python3 trade_cli.py validate quick` passes
- [ ] Re-run full T36-T62 agent test suite — target 62/62
- [ ] **GATE**: Full test suite passes

### P5: Market Sentiment Tracker

Design document: `docs/brainstorm/MARKET_SENTIMENT_TRACKER.md`

- [ ] Phase 1: Price-derived sentiment (Tier 0)
- [ ] Phase 2: Bybit exchange sentiment (Tier 1)
- [ ] Phase 3: External data (Tier 2)
- [ ] Phase 4: Historical sentiment for backtesting
- [ ] Phase 5: Statistical regime detection (HMM-based)

---

## Accepted Behavior

| ID | File | Note |
|----|------|------|
| GAP-BD2 | `trade_cli.py` | `os._exit(0)` correct — pybit WS threads are non-daemon |

## Platform Issues

- **DuckDB file locking on Windows** — sequential scripts, `run_full_suite.py` has retry logic
- **Windows `os.replace` over open files** — `PermissionError` if another process is mid-read of instance JSON. Retry-on-fail or document as known limitation. (`manager.py:416`)
- **`datetime.utcnow()` deprecated in Python 3.12** — 2 occurrences in `src/forge/validation/synthetic_data.py:153` and `src/forge/audits/stress_test_suite.py:92`. Semantically correct but should migrate to `datetime.now(timezone.utc).replace(tzinfo=None)`
- **Logger `datetime.now()` for log rotation** — 5 occurrences in `src/utils/logger.py`. Logs rotate at local midnight instead of UTC. Cosmetic only, low priority

---

## Validation Commands

```bash
# Tiers
python trade_cli.py validate quick              # Pre-commit (~2min)
python trade_cli.py validate standard           # Pre-merge (~6.5min)
python trade_cli.py validate full               # Pre-release (~10min)
python trade_cli.py validate real               # Real-data verification (~2min)
python trade_cli.py validate module --module X --json  # Single module (PREFERRED for agents)
python trade_cli.py validate pre-live --play X  # Deployment gate
python trade_cli.py validate exchange           # Exchange integration (~30s)

# Options
python trade_cli.py validate full --workers 4         # Control parallelism
python trade_cli.py validate full --timeout 60        # Per-play timeout (default 120s)
python trade_cli.py validate full --gate-timeout 600  # Per-gate timeout (default 600s)

# Backtest / verification
python trade_cli.py backtest run --play X --sync      # Single backtest
python scripts/run_full_suite.py                      # 170-play synthetic suite
python scripts/verify_trade_math.py --play X          # Math verification
```
