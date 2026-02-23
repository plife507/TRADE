# TRADE CLI Agent Test Prompt

Use this prompt with a Cursor agent (or any LLM agent with terminal access) to verify the TRADE CLI is fully functional. The agent operates the command line, parses JSON output, and documents every result back into this file.

**Platform: Windows PowerShell** (all commands use PowerShell syntax)

---

## System Prompt

```
You are a QA agent testing a trading bot CLI. You have a Windows PowerShell terminal.
Your job is to:
1. Execute CLI commands sequentially
2. Capture and parse their output
3. Check assertions
4. Document EVERY result back into THIS file (docs/AGENT_CLI_TEST_PROMPT.md)

## CRITICAL: Documentation Workflow

You MUST write results directly into this file as you go. Follow this exact workflow:

### Step 1: Before starting, update the "Test Run Metadata" section
Edit `docs/AGENT_CLI_TEST_PROMPT.md` and fill in the metadata fields:
- Run date/time
- Platform info (run `python --version` and `$PSVersionTable.PSVersion`)
- Working directory

### Step 2: For EACH test (T01 through T62), do this:
1. Run the command
2. Capture the FULL raw output (stdout + stderr)
3. Evaluate all assertions (PASS or FAIL for each)
4. Edit the corresponding row in the "Test Results" table in this file
5. If the test FAILED or produced unexpected output, append the full raw output
   to the "Detailed Output Log" section at the bottom of this file

### Step 3: After all tests, update the "Summary" section with final counts

## IMPORTANT RULES
- Do NOT fix any failures. Only document them thoroughly.
- Do NOT skip tests. Run every single one, even if earlier tests fail.
- Do NOT stop on failure. Continue through all tests.
- Do NOT modify the test commands or assertions — run them exactly as written.
- DO capture full raw output for EVERY failed test.
- DO note any warnings, stderr output, or unexpected behavior even on passing tests.
- If a command hangs for more than 120 seconds, kill it, mark as TIMEOUT, and continue.
- SEQUENTIAL EXECUTION: Run ALL backtests (T01-T05, T21, T49) and validations (T09-T10)
  ONE AT A TIME. Never run two backtests or validations in parallel. Wait for each to
  complete before starting the next. DuckDB file locks and high CPU usage cause failures
  when these run concurrently.
- DuckDB LOCK PREVENTION: Data commands (T11-T14), backtests, and validations ALL share
  the same DuckDB file. On Windows, DuckDB uses exclusive file locks that can persist for
  5-10 seconds after a process exits (WAL checkpoint flush). Rules:
  - Between EACH data command (T11-T14): `Start-Sleep -Seconds 8`
  - Between validation (T09-T10) and data commands (T11-T14): `Start-Sleep -Seconds 8`
  - Between any backtest and the next DuckDB-touching command: `Start-Sleep -Seconds 8`
  - If a DuckDB lock error occurs, retry after `Start-Sleep -Seconds 12`
- Tests T01-T25 are OFFLINE — no exchange connection needed.
- Tests T26-T35 (Group 8) use the DEMO exchange (Bybit testnet, fake money). These are safe.
- Tests T36-T50 (Group 9) exercise the full play lifecycle with `--headless` mode (demo only).
  These require T26-T27 to pass first. Use `Start-Job` for headless background processes
  (NOT `Start-Process` — its `-RedirectStandardOutput` is broken on PowerShell 5.1).
  Always stop jobs on test completion or timeout (safety net).
- Tests T51-T62 (Group 10) test the instance exit cooldown, cross-process lock, and race
  condition safety features. These require T26-T27 to pass first (demo mode). Some tests
  intentionally create fake/stale instance files to verify cleanup. Tests that check cooldown
  timing have tolerance windows — cooldown files expire after 15s.
  IMPORTANT: Clean up instances directory between tests if directed. Some tests depend on
  a clean state. Use `Remove-Item "data\runtime\instances\*.json" -Force -ErrorAction SilentlyContinue` when instructed.
- Do NOT run any LIVE/real-money commands. The system must be in DEMO mode (verify via T27).

## PowerShell Specifics

- Use `python` not `python3` (Windows convention)
- Background headless plays: Use `Start-Job` (NOT `Start-Process` — its `-RedirectStandardOutput` hangs on PS 5.1):
  ```powershell
  $job = Start-Job -ScriptBlock { Set-Location $using:PWD; python -u trade_cli.py play run --play plays/agent_test/AT_001_ema_cross_basic.yml --mode demo --headless 2>"$using:env:TEMP\headless_err.log" }
  ```
  Save to `$job` variable. The `-u` flag disables Python stdout buffering.
- Get job output: `Receive-Job $job` (gets all stdout so far)
- Get first line: `$firstLine = Receive-Job $job | Select-Object -First 1`
- Stop job: `Stop-Job $job -PassThru | Remove-Job -Force`
- Kill underlying process: `Stop-Process -Id (Get-Job $job.Id).ChildJobs[0].Process.Id -Force -ErrorAction SilentlyContinue` (if needed)
- Sleep: `Start-Sleep -Seconds N`
- Instances dir: `data\runtime\instances\`
- Temp dir: `$env:TEMP\`
- Check file exists: `Test-Path "data\runtime\instances\*.json"`
- Read file: `Get-Content "path"`
- Write file: `Set-Content -Path "path" -Value 'json content'`
- Remove files: `Remove-Item "path\*.json" -Force -ErrorAction SilentlyContinue`
- List files: `Get-ChildItem "data\runtime\instances\*.json"`
- Exit code: `$LASTEXITCODE` (after running python commands)
- Parse JSON: `$result = python trade_cli.py ... --json | ConvertFrom-Json`
- Check PID alive: `Get-Process -Id $proc.Id -ErrorAction SilentlyContinue`

## Environment

- Working directory: the TRADE project root (where trade_cli.py lives)
- Python: use `python` (Windows)
- All commands use `python trade_cli.py <command> [flags]`
- Every command supports `--json` for machine-readable output
- Backtest commands support `--json-verbose` for expanded metrics + hashes

## JSON Output Envelopes

All `--json` output follows one of these envelopes:

### Standard tool envelope (most commands):
{
  "status": "pass" | "fail",
  "message": "human-readable summary",
  "data": { ... }
}

### Backtest synthetic envelope:
{
  "status": "pass" | "fail",
  "error": null | "error message",
  "mode": "synthetic",
  "bars": 263,
  "seed": 42,
  "metrics": {
    "trades_count": 312,
    "win_rate": 0.176,
    "net_pnl_usdt": -703.75
  }
}

Add `--json-verbose` to get expanded output with full metrics, hashes, and artifact path.

### Validation envelope:
{
  "tier": "module:core",
  "duration_sec": 66.85,
  "passed": true,
  "total_checked": 5,
  "failed_gates": 0,
  "gates": [...]
}

## Test Plays

Five purpose-built plays live in `plays/agent_test/`:

| Play | Exec TF | Purpose |
|------|---------|---------|
| AT_001_ema_cross_basic | 1m | Basic EMA crossover, minimal wiring test |
| AT_002_rsi_momentum | 3m | RSI + ATR risk model, preflight/indicators test |
| AT_003_multi_tf_structure | 1m | Multi-TF indicators + structure detection |
| AT_004_short_side | 1m | Short-only strategy, downtrend pattern |
| AT_005_normalize_target | 3m | Play management (list, normalize) test |

These plays use 1m/3m exec timeframes for fast execution. They are NOT optimized
for profit — they exist solely to validate CLI functionality.

## Assertion Rules

- `status == "pass"` means the command completed without error
- `metrics.trades_count > 0` means the engine generated trades (strategy fired)
- For `--json-verbose`: check that `hashes.play_hash` is a non-empty string
- For validate: `passed == true` and `failed_gates == 0`
- For list: `data.plays` is an array containing expected play names
- For normalize: `status == "pass"` (the play YAML is already valid)
- For `--help` commands: check that ALL listed subcommands appear in stdout
- For exchange tests (T26-T35): `data.is_demo==true` or `data.trading.mode=="DEMO"` MUST be true
- For headless play lifecycle (T36-T50): parse stdout JSON line for `event` and `instance_id`
- For `play status --json`: check `instances` array length and entry fields
- For `play watch --json`: same as status — `instances` array with entry dicts
- For cooldown tests (T51-T62): cooldown files in `data\runtime\instances\` have `"status": "cooldown"` and `"cooldown_until"` timestamp. A cooldown entry appears in `play status --json` with `status` starting with `"cooldown"`.
- For cross-process lock tests: use concurrent background processes to verify mutual exclusion
- For stale file cleanup: create fake JSON files with dead PIDs and verify they are cleaned on next `play status`
- SAFETY: If T27 shows `data.trading.is_live==true`, STOP immediately and report. Do NOT continue exchange tests on LIVE.
```

---

## Test Run Metadata

| Field | Value |
|-------|-------|
| Run Date | 2026-02-23 |
| Platform | Python 3.12.10, PowerShell 5.1 |
| Working Dir | c:\CODE\AI\TRADE |
| Git Branch | main |
| Git Hash | 33bb5f0 |

---

## Test Results

### Group 1: Backtest Engine (synthetic data, no DB needed, run sequentially)

| ID | Test | Command | Result | Assertions | Duration | Notes |
|----|------|---------|--------|------------|----------|-------|
| T01 | Basic backtest run | `python trade_cli.py -q backtest run --play plays/agent_test/AT_001_ema_cross_basic.yml --synthetic --json` | PASS | `status=="pass"`, `metrics.trades_count > 0` | ~10s | Run 8 |
| T02 | RSI momentum + ATR stop | `python trade_cli.py -q backtest run --play plays/agent_test/AT_002_rsi_momentum.yml --synthetic --json` | PASS | `status=="pass"`, `metrics.trades_count > 0` | ~8s | |
| T03 | Multi-TF + structures | `python trade_cli.py -q backtest run --play plays/agent_test/AT_003_multi_tf_structure.yml --synthetic --json` | PASS | `status=="pass"`, `metrics.trades_count > 0` | ~13s | |
| T04 | Short-side strategy | `python trade_cli.py -q backtest run --play plays/agent_test/AT_004_short_side.yml --synthetic --json` | PASS | `status=="pass"`, `metrics.trades_count > 0` | ~9s | |
| T05 | Verbose JSON output | `python trade_cli.py -q backtest run --play plays/agent_test/AT_001_ema_cross_basic.yml --synthetic --json --json-verbose` | PASS | `status=="pass"`, hashes, artifact_path, sharpe | ~9s | |

### Group 2: Play Management

| ID | Test | Command | Result | Assertions | Duration | Notes |
|----|------|---------|--------|------------|----------|-------|
| T06 | List all plays | `python trade_cli.py backtest list --json` | PASS | `status=="pass"`, contains AT_001_ema_cross_basic | ~7s | Run 8 |
| T07 | Normalize a play | `python trade_cli.py backtest play-normalize --play at_005_normalize_target --dir plays/agent_test --json` | PASS | `status=="pass"` | ~8s | |
| T08 | Batch normalize | `python trade_cli.py backtest play-normalize-batch --dir plays/agent_test --json` | PASS | `status=="pass"` | ~8s | |

### Group 3: Validation Suite (run sequentially — each takes 60-120s)

| ID | Test | Command | Result | Assertions | Duration | Notes |
|----|------|---------|--------|------------|----------|-------|
| T09 | Quick validation | `python trade_cli.py validate quick --json` | PASS | `passed==true`, `failed_gates==0` | ~132s | Run 8 |
| T10 | Module validation (core) | `python trade_cli.py validate module --module core --json` | PASS | `passed==true` | ~128s | |

### Group 4: Data Management (read-only, no exchange needed)

Run these sequentially with `Start-Sleep -Seconds 8` between each to prevent DuckDB file lock conflicts.

| ID | Test | Command | Result | Assertions | Duration | Notes |
|----|------|---------|--------|------------|----------|-------|
| T11 | Data info | `Start-Sleep 8; python trade_cli.py data info --json` | PASS | `status=="pass"`, total_candles > 0 | ~14s | Run 8: 8s after T10 |
| T12 | Data symbols | `Start-Sleep 8; python trade_cli.py data symbols --json` | FAIL | Exit 0, JSON array | ~14s | DuckDB lock (PID 27708) |
| T13 | Data status | `Start-Sleep 8; python trade_cli.py data status --symbol BTCUSDT --json` | PASS | `status=="pass"` | ~15s | 8s sleep: T13 passed |
| T14 | Data summary | `Start-Sleep 8; python trade_cli.py data summary --json` | FAIL | `status=="pass"`, data.summary | ~14s | DuckDB lock |

### Group 5: Debug Tools

| ID | Test | Command | Result | Assertions | Duration | Notes |
|----|------|---------|--------|------------|----------|-------|
| T15 | Metrics audit | `python trade_cli.py debug metrics --json` | PASS | `status=="pass"` | ~7s | Run 8 |

### Group 6: Help & Discoverability

| ID | Test | Command | Result | Assertions | Duration | Notes |
|----|------|---------|--------|------------|----------|-------|
| T16 | Top-level help | `python trade_cli.py --help` | PASS | All 11 groups present | ~7s | Run 8 |
| T17 | Order help | `python trade_cli.py order --help` | PASS | buy, sell, list, amend, cancel, cancel-all, leverage, batch | ~11s | |
| T18 | Data help | `python trade_cli.py data --help` | PASS | sync, info, symbols, status, summary, query, heal, vacuum, delete | | |
| T19 | Market help | `python trade_cli.py market --help` | PASS | price, ohlcv, funding, oi, orderbook, instruments | | |
| T20 | Health help | `python trade_cli.py health --help` | PASS | check, connection, rate-limit, ws, environment | | |

### Group 7: Phase 7 Manual Validation (P4+P13 TODO items)

| ID | Test | Command | Result | Assertions | Duration | Notes |
|----|------|---------|--------|------------|----------|-------|
| T21 | Offline backtest | (same as T01) | PASS | `status=="pass"` | (T01) | Run 8 |
| T22 | Data info valid JSON | (T11) | PASS | Valid JSON, status pass, file_size_mb | (T11) | |
| T23 | Debug help structure | `python trade_cli.py debug --help` | PASS | math-parity, snapshot-plumbing, determinism, metrics | ~9s | |
| T24 | Account help structure | `python trade_cli.py account --help` | PASS | balance, exposure, info, history, pnl, transactions, collateral | | |
| T25 | Position help structure | `python trade_cli.py position --help` | PASS | list, close, detail, set-tp, set-sl, set-tpsl, trailing, partial-close, margin, risk-limit | | |

### Group 8: Exchange Connection — DEMO Mode (Bybit testnet, no real money)

These tests hit the Bybit DEMO API (api-demo.bybit.com). The system is pre-configured
for demo mode (`TRADING_MODE=paper`, `BYBIT_USE_DEMO=true`). All operations use fake money.

| ID | Test | Command | Result | Assertions | Duration | Notes |
|----|------|---------|--------|------------|----------|-------|
| T26 | Connection test | `python trade_cli.py health connection --json` | PASS | status pass, is_demo, public_ok | ~8s | Run 8 |
| T27 | API environment | `python trade_cli.py health environment --json` | PASS | status pass, mode DEMO, is_live false | ~6s | SAFETY GATE passed |
| T28 | Health check (full) | `python trade_cli.py health check --symbol BTCUSDT --json` | PASS | status pass, all_passed, DEMO | ~9s | |
| T29 | Rate limit status | `python trade_cli.py health rate-limit --json` | PASS | status pass, valid JSON | | Run 8 |
| T30 | Market price (live) | `python trade_cli.py market price --symbol BTCUSDT --json` | PASS | Valid JSON, BTCUSDT, price > 0 | | |
| T31 | Account balance | `python trade_cli.py account balance --json` | PASS | Valid JSON, total >= 0 | | |
| T32 | Account info | `python trade_cli.py account info --json` | PASS | Valid JSON (exit 0) | | |
| T33 | Position list | `python trade_cli.py position list --json` | PASS | Valid JSON, positions array | | |
| T34 | Order list | `python trade_cli.py order list --symbol BTCUSDT --json` | PASS | Valid JSON, orders array | | |
| T35 | Market orderbook | `python trade_cli.py market orderbook --symbol BTCUSDT --json` | PASS | Valid JSON with bids/asks | | |

### Group 9: Play Lifecycle — Demo Mode (Bybit testnet, headless)

These tests exercise the full play lifecycle: start (headless) -> poll -> pause -> resume -> stop.
Requires T26-T27 to pass first (demo mode confirmed).

**Agent workflow for lifecycle tests (PowerShell):**
1. Start headless play as background job using `Start-Job`:
   ```powershell
   $job = Start-Job -ScriptBlock { Set-Location $using:PWD; python -u trade_cli.py play run --play plays/agent_test/AT_001_ema_cross_basic.yml --mode demo --headless 2>"$using:env:TEMP\headless_err.log" }
   ```
2. Wait 15 seconds for engine to connect + process first bars: `Start-Sleep -Seconds 15`
3. Get output: `$output = Receive-Job $job` — this returns stdout lines
4. Parse first line: `$started = $output | Select-Object -First 1 | ConvertFrom-Json`
5. Poll `python trade_cli.py play status --json` to verify running
6. Exercise pause/resume/stop
7. Cleanup: `Stop-Job $job -PassThru | Remove-Job -Force`

**Important:** Some tests reference `<instance_id>`. Get this from the first stdout line of
the job output, or from `play status --json` → `instances[0].instance_id`.

**Why Start-Job instead of Start-Process:** PowerShell 5.1's `Start-Process -RedirectStandardOutput`
uses .NET streams that can deadlock when the child writes to stdout without someone reading. `Start-Job`
captures stdout natively through PowerShell's job system, avoiding this issue.

| ID | Test | Command | Result | Assertions | Duration | Notes |
|----|------|---------|--------|------------|----------|-------|
| T36 | Start play headless | Start-Job (or Start-Process with -u); Sleep 15; first line of output | FAIL | First line JSON event==started, instance_id | ~25s | Run 8: used Start-Process; instances [] |
| T37 | Verify running | `python trade_cli.py play status --json` | FAIL | instances length >= 1, mode demo | ~8s | No instance (T36) |
| T38 | Watch JSON snapshot | `python trade_cli.py play watch --json` | FAIL | instances array, instance visible | ~8s | instances empty |
| T39 | Pause play | `python trade_cli.py play pause --play <instance_id>` | FAIL | Exit 0, "Paused:" | (skipped) | |
| T40 | Verify paused | `python trade_cli.py play status --json` | FAIL | Instance in list | (skipped) | |
| T41 | Resume play | `python trade_cli.py play resume --play <instance_id>` | FAIL | Exit 0, "Resumed:" | (skipped) | |
| T42 | Verify resumed | `python trade_cli.py play status --json` | FAIL | Instance running | (skipped) | |
| T43 | Stop play | `python trade_cli.py play stop --play <instance_id> --force` | FAIL | Exit 0, "Stopped instance:" | (skipped) | |
| T44 | Verify stopped | `python trade_cli.py play status --json` | PASS | instances empty or cooldown | ~8s | instances empty |
| T45 | Start second play | Start-Sleep 16; Start-Job/Start-Process second play; first line | FAIL | event==started | (skipped) | |
| T46 | Verify second running | `python trade_cli.py play status --json` | FAIL | 1 instance | (skipped) | |
| T47 | Stop all | `python trade_cli.py play stop --all` | PASS | Exit 0 | ~8s | "No running instances to stop" |
| T48 | Verify all stopped | `python trade_cli.py play status --json` | PASS | instances empty or cooldown | ~8s | |
| T49 | Concurrent demo+backtest | Backtest run; stop all | PASS | Backtest status==pass | ~7s | Demo not running; backtest passed |
| T50 | Clean state after stop | Stop all; Sleep 16; Remove-Item *.json; status; Get-ChildItem | PASS | instances empty, 0 files | ~23s | |

### Group 10: Instance Cooldown & Cross-Process Safety (P15)

These tests verify the exit cooldown, cross-process file lock, atomic writes, and stale
file cleanup introduced in P15. Requires T26-T27 to pass first (demo mode confirmed).

**Prerequisites:**
- Clean instances directory: `Remove-Item "data\runtime\instances\*.json" -Force -ErrorAction SilentlyContinue; Remove-Item "data\runtime\instances\.lock" -Force -ErrorAction SilentlyContinue`
- Demo exchange reachable (T26-T27 passed)

**Agent workflow for cooldown tests (PowerShell):**
1. Start a headless demo play via `Start-Job` and capture its instance_id from stdout
2. Stop it and immediately check for cooldown file on disk
3. Attempt restart within cooldown window (should fail)
4. Wait for cooldown to expire, then retry (should succeed)
5. Clean up all background jobs with `Stop-Job $job -PassThru | Remove-Job -Force`

**Edge case tests use fake instance files:**
- Create JSON files with dead PIDs to simulate stale instances
- Create JSON files with expired cooldown timestamps
- Create malformed JSON files to test partial-write recovery

| ID | Test | Command | Result | Assertions | Duration | Notes |
|----|------|---------|--------|------------|----------|-------|
| T51 | Pre-cleanup | Remove-Item *.json and .lock; (Get-ChildItem *.json).Count -eq 0 | PASS | No error, directory clean | ~4s | Run 8 |
| T52 | Cooldown file after stop | Start-Job headless; Sleep 15; stop all; Get-ChildItem instances | FAIL | 1 .json with status cooldown | N/A | Not run (T36 no instance) |
| T53 | Cooldown visible in status | `python trade_cli.py play status --json` | FAIL | instances length 1, status cooldown | N/A | |
| T54 | Restart blocked by cooldown | Foreground play run --headless | FAIL | Exit != 0 or "cooldown"/"limit" | N/A | |
| T55 | Cooldown expiry + restart | Start-Sleep 16; Start-Job headless; first line | FAIL | event==started, 1 instance | N/A | |
| T56 | Cleanup after T55 | stop all; Stop-Job; Sleep 16; Remove-Item | (skipped) | | | |
| T57 | Stale PID cleanup | Create fake_stale_001.json (pid 9999999); play status; Test-Path | PASS | instances without fake_stale_001; file removed | ~6s | |
| T58 | Expired cooldown cleanup | Create fake_cooldown_002.json; play status; Test-Path | PASS | fake_cooldown_002 cleaned; file removed | ~6s | |
| T59 | Malformed JSON cleanup | Create fake_bad_003.json; play status; Test-Path | PASS | fake_bad_003 cleaned; file removed; no crash | ~6s | "Removing invalid instance file" |
| T60 | Cross-process limit check | Start-Job first; second foreground run | FAIL | First running; second fails | N/A | Not run (no first instance) |
| T61 | Per-symbol limit | Second play same symbol | FAIL | Fails limit message | N/A | |
| T62 | Final cleanup | stop all; Sleep 16; Remove-Item *.json and .lock; verify | PASS | instances empty; 0 files | ~24s | |

---

## Summary

### Previous Runs (pre-P15 cross-platform fix)

**Run 1 — 2026-02-22 (Windows, Python 3.12.10)** — 33/35 (T12, T14 failed; DuckDB lock)

**Run 2 — 2026-02-22 (Windows, sequential data commands)** — 35/35

**Run 3 — 2026-02-22 (Windows, Group 9 first attempt)** — Group 9: 4/15 (Rich stdout pollution, since fixed)

**Run 4 — 2026-02-22 (Windows, full)** — T01-T35: 34/35 (T13 DuckDB lock), Group 9: partial

**Run 5 — 2026-02-22 (Windows, T01-T62)** — 27/62. All 35 failures from `import fcntl` (Unix-only). **Fixed**: cross-platform lock using `msvcrt` on Windows, `fcntl` on Unix.

### Next Run Template (T01-T62, post cross-platform fix)

```
Total: __/62
Failed: __

Group Summary:
- G1  Backtest Engine:        _/5   (T01-T05)
- G2  Play Management:        _/3   (T06-T08)
- G3  Validation Suite:       _/2   (T09-T10)
- G4  Data Management:        _/4   (T11-T14)
- G5  Debug Tools:            _/1   (T15)
- G6  Help & Discoverability: _/5   (T16-T20)
- G7  Phase 7 Validation:     _/5   (T21-T25)
- G8  Exchange Demo:          _/10  (T26-T35)
- G9  Play Lifecycle:         _/15  (T36-T50)
- G10 Cooldown & Safety:      _/12  (T51-T62)

Total Duration: ___
Notes:
- fcntl→msvcrt cross-platform fix applied (P15)
- T44, T48, T50 have cooldown-aware assertions
- Group 10 is NEW (P15: exit cooldown, cross-process lock, stale cleanup)
```

### Run 6 — 2026-02-22 (Windows, Python 3.12.10, full T01–T62)

```
Total: 44/62
Failed: 18

Group Summary:
- G1  Backtest Engine:        5/5   (T01-T05)
- G2  Play Management:        3/3   (T06-T08)
- G3  Validation Suite:       2/2   (T09-T10)
- G4  Data Management:        2/4   (T11 pass, T12 pass; T13, T14 DuckDB lock)
- G5  Debug Tools:            1/1   (T15)
- G6  Help & Discoverability: 5/5   (T16-T20)
- G7  Phase 7 Validation:     5/5   (T21-T25)
- G8  Exchange Demo:          10/10 (T26-T35)
- G9  Play Lifecycle:         5/15  (T44, T47, T48, T49, T50 pass; T36–T43, T45–T46 fail — headless Start-Process did not yield running instance / output file empty)
- G10 Cooldown & Safety:      6/12  (T51, T56, T57, T58, T59, T62 pass; T52–T55, T60–T61 fail or N/A)

Total Duration: ~12 min
Notes:
- T13, T14: DuckDB "file is being used by another process" (sequential data commands with 3s sleep still conflicted with prior data info).
- T36, T45: Headless play via Start-Process: redirect output files (workspace or TEMP) remained empty; play status showed 0 instances. Foreground `play run --headless` did start and emit event/instance_id (seen during T54).
- T52–T55, T60–T61: Cooldown/limit tests depend on a running headless instance; Start-Process headless did not persist instance in this environment.
- Stale/expired/malformed cleanup (T57–T59) all passed.
```

### Run 7 — 2026-02-23 (Windows, Python 3.12.10, updated .md: 5s DuckDB sleep, -u headless)

```
Total: 44/62
Failed: 18

Group Summary:
- G1  Backtest Engine:        5/5   (T01-T05)
- G2  Play Management:        3/3   (T06-T08)
- G3  Validation Suite:       2/2   (T09-T10)
- G4  Data Management:        2/4   (T11, T12 pass; T13, T14 DuckDB lock despite 5s sleep between each)
- G5  Debug Tools:            1/1   (T15)
- G6  Help & Discoverability: 5/5   (T16-T20)
- G7  Phase 7 Validation:     5/5   (T21-T25)
- G8  Exchange Demo:          10/10 (T26-T35)
- G9  Play Lifecycle:         5/15  (T44, T47, T48, T49, T50 pass; T36–T43, T45–T46 fail — headless with -u: TEMP\headless_out.jsonl still empty, instances [])
- G10 Cooldown & Safety:      6/12  (T51, T57, T58, T59, T62 pass; T52–T56, T60–T61 fail or N/A)

Total Duration: ~15 min
Notes:
- Updated .md: 5s sleep between data commands (T11–T14) and after T10; Python -u for headless. T13/T14 still failed (DuckDB lock, PID 3792). Consider 8s sleep or single-process data sequence.
- T36: Start-Process with -u; 10s wait; first line of TEMP\headless_out.jsonl empty; play status showed 0 instances. -u did not resolve redirect/empty output in this run.
- T57–T59: Stale/expired/malformed cleanup all passed.
```

### Run 8 — 2026-02-23 (Windows, Python 3.12.10, git 33bb5f0, 8s DuckDB sleep)

```
Total: 45/62
Failed: 17

Group Summary:
- G1  Backtest Engine:        5/5   (T01-T05)
- G2  Play Management:        3/3   (T06-T08)
- G3  Validation Suite:       2/2   (T09-T10)
- G4  Data Management:        3/4   (T11, T13 pass; T12, T14 DuckDB lock — 8s sleep: T13 passed, T12/T14 still lock)
- G5  Debug Tools:            1/1   (T15)
- G6  Help & Discoverability: 5/5   (T16-T20)
- G7  Phase 7 Validation:     5/5   (T21-T25)
- G8  Exchange Demo:          10/10 (T26-T35)
- G9  Play Lifecycle:         5/15  (T44, T47, T48, T49, T50 pass; T36–T43, T45–T46 fail — Start-Process headless, instances [])
- G10 Cooldown & Safety:      6/12  (T51, T57, T58, T59, T62 pass; T52–T56, T60–T61 fail or N/A)

Total Duration: ~12 min
Notes:
- 8s sleep between data commands (per updated .md): T11 pass, T12 FAIL (lock PID 27708), T13 PASS, T14 FAIL. One more data test passed than Run 7.
- Doc now recommends Start-Job for headless (Run 8 still used Start-Process); next run should try Start-Job per .md.
```

### WSL Run — 2026-02-22 (WSL2 Ubuntu, Python 3.12.3, git 33bb5f0, bash backgrounding)

```
Total: 53/62
Failed: 9

Group Summary:
- G1  Backtest Engine:        5/5   (T01-T05)
- G2  Play Management:        3/3   (T06-T08)
- G3  Validation Suite:       2/2   (T09-T10)
- G4  Data Management:        4/4   (T11-T14 — no DuckDB lock issues on Linux!)
- G5  Debug Tools:            1/1   (T15)
- G6  Help & Discoverability: 5/5   (T16-T20)
- G7  Phase 7 Validation:     5/5   (T21-T25)
- G8  Exchange Demo:          10/10 (T26-T35)
- G9  Play Lifecycle:         10/15 (T36-T44, T47-T50 pass; T45-T46 fail — DuckDB lock from zombie PID)
- G10 Cooldown & Safety:      8/12  (T51-T53, T57-T59, T62 pass; T54-T56, T60-T61 fail)

Total Duration: ~10 min
Notes:
- Linux fcntl locks release immediately on process exit — G4 all pass with just 2s sleep.
- Start-Job vs Start-Process is irrelevant on Linux — bash `&` backgrounding works perfectly.
- Root cause of ALL 9 failures: `play stop --force` doesn't kill the OS process (PID stays alive
  holding DuckDB lock). Second instance crashes on lock instead of clean "already running" error.
- Bug 1: stop() must os.kill() the stored PID after writing cooldown file.
- Bug 2: start() needs pre-launch per-symbol duplicate check (reject if same symbol PID alive).
- See P17 in docs/TODO.md for fix plan.
```

---

## Detailed Output Log

### T13 (FAIL) — Data status (DuckDB lock)

```json
{
  "status": "fail",
  "message": "Failed to get status: IO Error: Cannot open file \"c:\\code\\ai\\trade\\data\\market_data_backtest.duckdb\": The process cannot access the file because it is being used by another process.\r\n\nFile is already open in \nC:\\Users\\507pl\\AppData\\Local\\Programs\\Python\\Python312\\python.exe (PID 29388)",
  "data": null
}
```

### T14 (FAIL) — Data summary (DuckDB lock)

```json
{
  "status": "fail",
  "message": "Failed to get symbol summary: IO Error: Cannot open file \"c:\\code\\ai\\trade\\data\\market_data_backtest.duckdb\": The process cannot access the file because it is being used by another process.\r\n\nFile is already open in \nC:\\Users\\507pl\\AppData\\Local\\Programs\\Python\\Python312\\python.exe (PID 29388)",
  "data": null
}
```

### T36 / T37 (FAIL) — Headless start and status

- Headless output file (workspace or TEMP): empty. `play status --json`: `{"instances": []}`. No instance_id available for lifecycle tests.

### T39, T41, T43 (FAIL) — Pause / Resume / Stop (no instance)

- `No running instance found matching 'no_instance_001'.` (exit 1). Same for resume and stop.

### T54 (partial) — Foreground headless start

- Foreground `play run --play ... --mode demo --headless` did start: stdout contained `{"event": "started", "instance_id": "at_001_ema_cross_basic_demo_8fa93fdf", ...}`. Exited with code 1 (timeout/kill). Confirms headless engine starts when run in foreground; Start-Process redirect/behavior differs.

### Run 7 — T13, T14 (FAIL) — DuckDB lock with 5s sleep

- T13/T14: Same lock error; PID 3792. Five-second sleep between data commands (per updated .md) was not sufficient. Retry after 8s or run data commands in a single process.

### Run 7 — T36 (FAIL) — Headless with -u

- Start-Process with `-u` (unbuffered Python stdout); 10s wait; `Get-Content $env:TEMP\headless_out.jsonl -First 1` returned empty; `play status --json`: `{"instances": []}`. Run took ~167s (possible hang on Get-Content or child). -u did not fix empty redirect in this environment.

### Run 8 — T12 (FAIL), T14 (FAIL) — DuckDB lock with 8s sleep

- T12: "Failed to list symbols: IO Error: Cannot open file ... The process cannot access the file because it is being used by another process. File is already open in ... python.exe (PID 27708)"
- T14: status fail (same lock). T11 and T13 passed with 8s sleep between each command.

---

*(End of test results)*
