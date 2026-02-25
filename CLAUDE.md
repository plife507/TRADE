# CLAUDE.md

## Project Overview

This is a Python project. Primary language is Python with YAML for configuration and Markdown for documentation. Use pyright for type checking. Always validate changes with existing test suites before committing.

## General Principles

- Always use the project's existing CLI tools and infrastructure before building custom scripts or solutions. Ask the user which CLI commands are available if unsure.
- When spawning agent teams for audits or large tasks, begin executing promptly rather than spending excessive time on codebase exploration and orchestration planning. The user prefers action over preparation.

## Prime Directives

- **ALL FORWARD, NO LEGACY** - Delete old code, don't wrap it
- **MODERN PYTHON 3.12+** - Type hints, f-strings, pathlib, `X | None` not `Optional[X]`
- **LF LINE ENDINGS** - Use `newline='\n'` on Windows
- **TODO-DRIVEN** - Every change maps to `docs/TODO.md`
- **CLI VALIDATION** - Use CLI commands, not pytest
- **PLAN → TODO.md** - Every plan mode output MUST be written into `docs/TODO.md` (see Plan Mode Rules below)

## Project Structure

When working with this codebase, target `src/` not `scripts/` unless explicitly told otherwise. The main source tree is under `src/`.

## Architecture

```text
src/engine/        # ONE unified engine (PlayEngine) for backtest/live
src/indicators/    # 44 indicators (all incremental O(1))
src/structures/    # 7 structure types (swing, trend, zone, fib, derived_zone, rolling_window, market_structure)
src/backtest/      # Infrastructure only (sim, runtime, features) - NOT an engine
src/data/          # DuckDB historical data (1m candles mandatory for all runs)
src/tools/         # CLI/API surface
```

**1m data is mandatory**: Every backtest/live run pulls 1m candles regardless of exec timeframe. Drives fill simulation, TP/SL evaluation, and signal subloop.

## Database & Concurrency

When running parallel agents or sub-tasks, NEVER use parallel file access to DuckDB databases. Always run DuckDB operations sequentially to avoid file lock conflicts.

## Key Patterns

| Pattern | Rule |
|---------|------|
| Engine | Always use `create_engine_from_play()` + `run_engine_with_play()` |
| Indicators | Declare in Play YAML, access via snapshot |
| Database | Sequential access only (DuckDB limitation) |
| Hashing | Always use `compute_trades_hash()` from `hashes.py` -- never ad-hoc `repr()`/`hash()` |
| Timestamps | UTC-naive datetimes everywhere. Use `_datetime_to_epoch_ms()` from `feed_store.py` -- never `dt.timestamp() * 1000` on naive datetimes |
| Set iteration | **Never** pass `list(some_set)` to order-sensitive functions. Use `sorted(some_set)`. |

## Logging & Debugging

### Logger Hierarchy

All loggers live under `trade.*`. Never create orphan loggers.

| Do | Don't |
|----|-------|
| `from src.utils.logger import get_module_logger` | `import logging` |
| `logger = get_module_logger(__name__)` | `logger = logging.getLogger(__name__)` |

`get_module_logger("src.backtest.runner")` → `logging.getLogger("trade.backtest.runner")`.

### Key Functions (all in `src/utils/`)

| Function | Module | Purpose |
|----------|--------|---------|
| `get_module_logger(name)` | `logger.py` | Create child logger under `trade.*` |
| `suppress_for_validation()` | `logger.py` | Set `trade.*` to WARNING (for validation workers) |
| `get_logger()` / `setup_logger()` | `logger.py` | Get/create the `TradingLogger` singleton |
| `verbose_log(play_hash, msg, **fields)` | `debug.py` | Log at INFO gated on verbose mode |
| `debug_log(play_hash, msg, **fields)` | `debug.py` | Log at DEBUG gated on debug mode |
| `is_verbose_enabled()` | `debug.py` | Check if `-v` or `--debug` is active |
| `is_debug_enabled()` | `debug.py` | Check if `--debug` is active |

### Verbosity Levels

| Flag | Level | When to use |
|------|-------|-------------|
| `-q` / `--quiet` | WARNING only | CI, scripted runs, validation workers |
| (default) | INFO | Normal interactive use |
| `-v` / `--verbose` | INFO + signal/structure traces | Debugging why signals don't fire |
| `--debug` | DEBUG + all traces | Full hash-traced debugging |

### Rules

- **NEVER** use `logging.disable()` — use `suppress_for_validation()` instead
- **NEVER** use bare `logging.getLogger(__name__)` — use `get_module_logger(__name__)`
- **NEVER** add per-bar logging without gating on `is_verbose_enabled()` or `is_debug_enabled()` — per-bar logs on 25k+ bars destroy performance
- **Env var**: `TRADE_LOG_LEVEL` controls global level (fallback: `LOG_LEVEL`, then `"INFO"`)
- **Validation workers** (ProcessPoolExecutor): call `suppress_for_validation()` at the top of each worker function
- **Verbose-only code**: use `verbose_log()` for signal traces, structure events, NaN warnings. Zero overhead when verbose is off (early return)

### Backtest Event Journal

Every backtest writes `events.jsonl` to its artifact folder via `BacktestJournal` (in `src/engine/journal.py`). Records fill and close events per trade. Live/demo uses `TradeJournal` which writes to `data/journal/`.

## Hash Tracing

Deterministic hashes flow through the entire pipeline for reproducibility and debugging.

| Hash | Source | Length | Purpose |
|------|--------|--------|---------|
| `play_hash` | `compute_play_hash(play)` SHA256 | 16 hex | Play config identity |
| `input_hash` | `compute_input_hash(components)` SHA256 | 12 hex | Artifact folder name |
| `trades_hash` | `compute_trades_hash(trades)` SHA256 | 16 hex | Output determinism |
| `equity_hash` | `compute_equity_hash(curve)` SHA256 | 16 hex | Output determinism |
| `run_hash` | `compute_run_hash(trades, equity, play)` | 16 hex | Combined fingerprint |
| `data_hash` | SHA256 of synthetic data | 12 hex | Synthetic data integrity |

**Canonical functions**: All in `src/backtest/artifacts/hashes.py`. `DEFAULT_SHORT_HASH_LENGTH = 12`.

**Pipeline flow**: runner computes `play_hash` → sets on engine via `set_play_hash()` → engine uses in debug logging → after run, computes `trades_hash`/`equity_hash`/`run_hash` → stored in `result.json` → displayed in console → logged to `index.jsonl`.

**Field naming**: The field is `play_hash` everywhere (not `idea_hash`). `ResultsSummary.play_hash`, `result.json["play_hash"]`, `determinism.py` hash_fields.

## Timestamp Convention (ENFORCED)

All timestamps in the system are **UTC-naive** `datetime` objects. This is enforced at every data entry point (WebSocket, REST API, DuckDB) and validated by **G17: Timestamp Correctness** on every commit.

### Rules

| Do | Don't |
|----|-------|
| `datetime.fromtimestamp(ms/1000, tz=utc).replace(tzinfo=None)` | `datetime.fromtimestamp(ms/1000, tz=utc)` (tz-aware) |
| `datetime.fromisoformat(s).replace(tzinfo=None)` | `datetime.fromisoformat(s)` bare (may return tz-aware in 3.11+) |
| `_datetime_to_epoch_ms(dt)` from `feed_store.py` | `int(dt.timestamp() * 1000)` (local-time bug on naive datetimes) |
| `pd.to_datetime(..., utc=True).tz_localize(None)` | `pd.to_datetime(..., utc=True)` bare (tz-aware Series) |
| `_np_dt64_to_epoch_ms(ts)` for numpy datetime64 | `np.array([...], dtype="datetime64[ms]")` from tz-aware datetimes |
| `ts.astimezone(utc).replace(tzinfo=None)` at entry points | Passing tz-aware datetimes into FeedStore/Candle |
| `utc_now()` from `datetime_utils.py` | `datetime.now()` or `datetime.utcnow()` |

### Canonical Functions

| Function | Module | Purpose |
|----------|--------|---------|
| `utc_now()` | `src/utils/datetime_utils.py` | Current UTC time as naive datetime |
| `datetime_to_epoch_ms(dt)` | `src/utils/datetime_utils.py` | Naive/aware datetime → epoch ms (uses `timegm` for naive) |
| `parse_bybit_ts(ms_str)` | `src/utils/datetime_utils.py` | Bybit epoch-ms string → naive datetime (or None) |
| `normalize_datetime(value)` | `src/utils/datetime_utils.py` | Parse string/datetime → naive UTC datetime |
| `normalize_timestamp(ts)` | `src/utils/datetime_utils.py` | Strip tz-aware → naive UTC |
| `normalize_datetime_for_storage(dt)` | `src/utils/datetime_utils.py` | → ISO string `YYYY-MM-DDTHH:MM:SS` (drops microseconds) |
| `_datetime_to_epoch_ms(dt)` | `src/backtest/runtime/feed_store.py` | Hot-loop parity version (identical to `datetime_to_epoch_ms`) |
| `_np_dt64_to_epoch_ms(ts)` | `src/backtest/runtime/feed_store.py` | numpy datetime64 → int64 ms |
| `_np_dt64_to_datetime(ts)` | `src/backtest/runtime/feed_store.py` | numpy datetime64 → naive datetime |
| `_normalize_to_naive_utc(dt)` | `src/data/historical_sync.py` | DuckDB tz-aware fetch → naive UTC |

### Validation Gate: G17 Timestamp Correctness

**Location**: `src/cli/validate_timestamps.py` — runs in Stage 0 of every validation tier (quick/standard/full).

```bash
python trade_cli.py validate module --module timestamps       # Standalone
python trade_cli.py validate module --module timestamps --json # JSON output
```

**483 checks across 22 categories, <3 seconds:**

| # | Category | Checks | What it catches |
|---|----------|--------|-----------------|
| 1 | Conversion Roundtrip | 6 | `datetime ↔ epoch_ms` breaks, timegm vs .timestamp() divergence |
| 2 | Timezone Handling | 6 | tz-aware not stripped to naive, normalize_* regressions |
| 3 | Bybit Parsing | 7 | `parse_bybit_ts()` edge cases: None, empty, invalid, whitespace |
| 4 | FeedStore Integrity | 6 | Index roundtrips, binary search, ts_close alignment |
| 5 | numpy/pandas Interop | 4 | Type boundary crossings, ns→ms truncation |
| 6 | BarRecord Handling | 4 | `from_kline_data()`, `from_df_row()` produce naive UTC |
| 7 | Artifact Serialization | 5 | Trade/EquityPoint `to_dict()` — no tz suffix in JSON |
| 8 | Static Analysis (A-D) | ~325 | Scans all src/ for 4 banned patterns (see below) |
| 9 | Multi-TF Alignment | 4 | `get_1m_indices_for_exec()` correctness |
| 10 | DST / Edge Cases | 5 | DST immunity, midnight, year boundary, leap second |
| 11 | Live Candle Conversion | 6 | KlineData → Candle, `end_time + 1` logic, fallback formula |
| 12 | TimeRange Roundtrip | 8 | `from_dates()` → `to_bybit_params()` → `start_datetime` identity |
| 13 | Order/Position REST | 5 | `parse_bybit_ts()` → Order/Position dataclass fields |
| 14 | DuckDB Normalization | 6 | tz-aware fetch → `_normalize_to_naive_utc()` → naive |
| 15 | WS Staleness Pattern | 6 | `time.time()` interval math, STALENESS_THRESHOLDS |
| 16 | Sim Exchange Flow | 7 | Bar timestamp → Trade entry/exit → isoformat roundtrip |
| 17 | Storage Serialization | 7 | `normalize_datetime_for_storage()` strftime behavior |
| 18 | TimeRange Internals | 11 | `_to_utc()`, `from_timestamps_ms()`, `.timestamp()*1000` on aware |
| 19 | All to_dict() Timestamps | 9 | AccountCurvePoint, BarRecord, TradeRecord, PortfolioSnapshot |
| 20 | Tz-Aware DataFrame Strip | 6 | `pd.to_datetime(utc=True)` → FeedStore naive pipeline |
| 21 | Self-Test Canary | 11 | Proves the gate itself detects known-bad inputs |
| 22 | Tz-Aware Guards (E/F) | ~31 | Scans for unguarded `.fromisoformat()` and `pd.to_datetime(utc=True)` |

### Banned Patterns (Static Scan)

G17 Category 8 scans all `src/` files for these patterns (same approach as G16 logging lint):

| Pattern | Banned Code | Fix |
|---------|-------------|-----|
| A | `datetime.utcnow()` | `utc_now()` from datetime_utils |
| B | `.timestamp() * 1000` | `datetime_to_epoch_ms()` |
| C | `datetime.fromtimestamp(x)` without `tz=` | Add `tz=timezone.utc` + `.replace(tzinfo=None)` |
| D | `datetime.now()` bare | `utc_now()` from datetime_utils |
| E | `.fromisoformat()` without `.replace(tzinfo=None)` | Add `.replace(tzinfo=None)` guard |
| F | `pd.to_datetime(utc=True)` without `tz_localize(None)` | Add `.tz_localize(None)` downstream |

**Exempt files** (canonical implementations or justified tz-aware usage):
- `datetime_utils.py`, `feed_store.py`, `time_range.py` — contain canonical conversion functions
- `validate_timestamps.py` — contains pattern strings in test messages
- `indicator_vendor.py` — `pandas_ta.vwap()` requires tz-aware DatetimeIndex for session boundaries

### Best Practices (How to Write Timestamp Code)

**Getting current time:**
```python
from src.utils.datetime_utils import utc_now
now = utc_now()  # Always. Never datetime.now() or datetime.utcnow().
```

**Parsing timestamps from Bybit REST/WS:**
```python
from src.utils.datetime_utils import parse_bybit_ts
dt = parse_bybit_ts(response["createdTime"])  # Returns naive UTC or None
```

**Converting datetime to epoch milliseconds:**
```python
from src.utils.datetime_utils import datetime_to_epoch_ms
ms = datetime_to_epoch_ms(dt)  # Safe on naive datetimes (uses timegm, not .timestamp())
```

**Parsing user/config ISO strings:**
```python
# Always add .replace(tzinfo=None) — fromisoformat can return tz-aware in Python 3.11+
dt = datetime.fromisoformat(user_input).replace(tzinfo=None)
# Or use normalize_datetime() which handles all edge cases:
from src.utils.datetime_utils import normalize_datetime
dt, err = normalize_datetime(user_input)
```

**Converting Bybit epoch-ms integers to datetime:**
```python
# Always specify tz=timezone.utc, then strip
dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)
```

**Working with pandas timestamps:**
```python
# If you need pd.to_datetime with UTC, strip immediately:
ts = pd.to_datetime(series, unit="ms", utc=True).tz_localize(None)
# Exception: pandas_ta functions that require tz-aware DatetimeIndex (VWAP)
```

**Serializing to JSON/artifacts:**
```python
# .isoformat() on naive datetime produces clean strings (no +00:00 suffix)
d = {"timestamp": dt.isoformat()}  # "2025-06-15T12:30:00"
# For storage without microseconds, use:
from src.utils.datetime_utils import normalize_datetime_for_storage
s = normalize_datetime_for_storage(dt)  # "2025-06-15T12:30:00" (strftime, drops μs)
```

**Measuring intervals (staleness, rate limiting, cooldowns):**
```python
# Use time.time() for interval math — it's a float, not a datetime
import time
reception_time = time.time()  # When data arrived
age = time.time() - reception_time  # Seconds since arrival
is_stale = age > threshold
# Use time.monotonic() for durations immune to NTP clock jumps
```

**Adding a new dataclass with a timestamp field:**
```python
@dataclass
class MyRecord:
    timestamp: datetime  # Always naive UTC
    # ...
    def to_dict(self) -> dict:
        return {"timestamp": self.timestamp.isoformat(), ...}
        # G17 Cat 19 will automatically check this produces no tz suffix
```

**Adding a new exempt file to G17:**
If your code legitimately needs tz-aware timestamps (e.g., a third-party library requires it), add the file stem to the exempt set in `validate_timestamps.py` Cat 22 (`_cat_static_analysis_warnings`) with a comment explaining why.

### Why timegm Matters

On a non-UTC system (e.g., UTC-5), `datetime.timestamp()` on a **naive** datetime assumes local time:
```python
dt = datetime(2025, 6, 15, 12, 0, 0)          # naive, intended as UTC
int(dt.timestamp() * 1000)                      # → 1750008600000 (WRONG — 5h shifted)
timegm(dt.timetuple()) * 1000                   # → 1749990600000 (CORRECT)
```
This is the #1 bug the gate exists to prevent. `_datetime_to_epoch_ms()` uses `timegm()` specifically to avoid this.

## Trading Domain Rules

For trading logic: Take Profit (TP) and Stop Loss (SL) orders fire BEFORE signal-based closes. Do not assume signal closes have priority over TP/SL.

## Live Safety Principles

- **Fail-closed**: Safety guards (price deviation, WS health, position sync) must block trading when data is unavailable, not allow it.
- **Reduce-only for closes**: All close/partial-close market orders must pass `reduce_only=True` to the exchange. Never set flags on result objects after the order is placed.
- **Position sync gate**: LiveRunner blocks signal execution until `_position_sync_ok` is True. Periodic reconciliation can unblock.

## Type Checking

When fixing type errors or pyright issues, run the full pyright check after each batch of fixes to catch cascading errors early. Fixing one category of errors often exposes hidden ones.

**Config ownership**: `pyrightconfig.json` is the single source of truth for all type checking settings. When it exists, Pylance **ignores** all `python.analysis.*` settings in `.vscode/settings.json`. Never duplicate type checking config in both files. VS Code settings should only contain interpreter path and language server choice.

**Pyright vs Cursor/Pylance phantom errors**: Cursor (and VS Code with Pylance) may show phantom "import not found" errors that pyright CLI does not produce. This is because `pyrightconfig.json` sets `"reportMissingImports": "none"` and `"extraPaths": [".", "src"]`, which pyright CLI respects but Pylance may ignore or override. Always trust `pyright` CLI output over in-editor squiggles. The Claude Code hook (`.claude/hooks/scripts/pyright_check.py`) runs pyright from the project root to ensure correct config resolution.

## Code Cleanup Rules

Before claiming code is 'dead' or unused, verify by grepping for all references including dynamic imports, CLI entry points, and test fixtures. Do not remove code without confirmed zero references.

## Timeframe Naming (ENFORCED)

**3-Feed + Exec Role System:**

| Term | Type | Example Values | Purpose |
|------|------|----------------|---------|
| `low_tf` | Timeframe | 1m, 3m, 5m, 15m | Fast: execution, entries |
| `med_tf` | Timeframe | 30m, 1h, 2h, 4h | Medium: structure, bias |
| `high_tf` | Timeframe | 12h, D | Slow: trend, context |
| `exec` | Pointer | "low_tf", "med_tf", "high_tf" | Which TF to step on |

**YAML keys (ENFORCED):**
- ~~htf~~, ~~HTF~~ → use `high_tf`
- ~~ltf~~, ~~LTF~~ → use `low_tf`
- In YAML: `exec` is a pointer (`"low_tf"`, `"med_tf"`, `"high_tf"`), never a raw value like `"15m"`

**Python identifiers (ENFORCED):**
- `exec_tf` = resolved concrete timeframe string (e.g., `"15m"`) -- standard name
- ~~execution_tf~~ → use `exec_tf` everywhere in Python code
- ~~ltf~~, ~~htf~~, ~~LTF~~, ~~HTF~~, ~~MTF~~ → banned

**Prose/comments:**
- "higher timeframe" not HTF
- "medium timeframe" not MTF
- "lower timeframe" not LTF
- "exec TF" is acceptable shorthand in comments and log messages
- "multi-timeframe" for strategies using multiple timeframes
- "last price" and "mark price" written out fully

```yaml
# Correct Play structure:
timeframes:
  low_tf: "15m"    # Concrete timeframe
  med_tf: "1h"     # Concrete timeframe
  high_tf: "D"     # Concrete timeframe (12h or D)
  exec: "low_tf"   # POINTER to which TF to step on
```

## Quick Commands

```bash
# Verbosity flags (apply to any command)
python trade_cli.py -q ...                            # Quiet (WARNING only)
python trade_cli.py -v ...                            # Verbose (signal traces, structure events)
python trade_cli.py --debug ...                       # Debug (full hash tracing)

# Validation (parallel staged execution, with timeouts + incremental reporting)
python trade_cli.py validate quick                    # Pre-commit (~2min)
python trade_cli.py validate standard                 # Pre-merge (~4min)
python trade_cli.py validate full                     # Pre-release (~6min)
python trade_cli.py validate real                     # Real-data verification (~2min)
python trade_cli.py validate module --module X --json # Single module (PREFERRED for agents)
python trade_cli.py validate module --module coverage # Check for missing indicator/structure plays
python trade_cli.py validate pre-live --play X        # Deployment gate
python trade_cli.py validate exchange                  # Exchange integration (~30s)
python trade_cli.py validate full --timeout 60        # Per-play timeout (default 120s)
python trade_cli.py validate full --gate-timeout 300  # Per-gate timeout (default 600s)

# Backtest
python trade_cli.py backtest run --play X --sync  # Run single backtest
python trade_cli.py -v backtest run --play X --synthetic  # Verbose: see signal traces
python scripts/run_full_suite.py                      # 170-play synthetic suite
python scripts/run_full_suite.py --real --start 2025-01-01 --end 2025-06-30  # Real data suite
python scripts/run_real_verification.py               # 60-play real verification
python scripts/verify_trade_math.py --play X          # Math verification for a play

# Debug (diagnostic tools — all --json use {"status","message","data"} envelope)
python trade_cli.py debug math-parity --play X        # Real-data math audit
python trade_cli.py debug snapshot-plumbing --play X   # Snapshot field check
python trade_cli.py debug determinism --run-a A --run-b B  # Compare runs
python trade_cli.py debug metrics                      # Financial calc audit

# Live/Demo
python trade_cli.py play run --play X --mode demo   # Demo mode (no real money)
python trade_cli.py play run --play X --mode live --confirm  # Live (REAL MONEY)
```

## Validation Coverage

The `coverage` module (gate G15) automatically detects which indicators and structures lack validation plays. It compares the indicator registry (44 indicators) and structure registry (7 types) against the plays in `plays/validation/indicators/` and `plays/validation/structures/`.

```bash
# Check for gaps (human-readable)
python trade_cli.py validate module --module coverage

# Check for gaps (JSON, for agents)
python trade_cli.py validate module --module coverage --json
```

**When to run**: After adding a new indicator or structure detector. The gate fails if any registered indicator/structure has no corresponding validation play.

**Fixing gaps**: Use the `validate_updater` agent, which has templates and workflows for creating missing plays. Or create plays manually following existing examples in `plays/validation/indicators/` and `plays/validation/structures/`.

## Plan Mode Rules (ENFORCED)

When exiting plan mode, the plan MUST be written into `docs/TODO.md` as a new gated section. This is the **only** persistent record — conversation context gets compacted and lost.

**Format requirements:**

1. **New section** in TODO.md with a clear title and priority (e.g., `## P0: Liquidation Parity`)
2. **Gated phases** — each phase is a group of checkboxes that must ALL pass before the next phase starts
3. **Validation gate** between phases — a checkbox like `- [ ] **GATE**: validate quick passes` or `- [ ] **GATE**: backtest run --play X succeeds`
4. **Reference doc** — if the plan produced a detailed review/analysis, link it (e.g., `See docs/LIQUIDATION_PARITY_REVIEW.md`)

**Example structure:**

```markdown
## P0: Liquidation Parity

See `docs/LIQUIDATION_PARITY_REVIEW.md` for full analysis.

### Phase 1: Fix IM/MM formulas
- [ ] Add fee-to-close term to MM calculation in `ledger.py`
- [ ] Add mmDeduction to MM calculation
- [ ] Wire tiered MMR from risk-limit config
- [ ] **GATE**: `python trade_cli.py validate quick` passes

### Phase 2: Bankruptcy price settlement
- [ ] Implement bankruptcy price calculation in `liquidation_model.py`
- [ ] Change exchange sim to settle at bankruptcy price (not mark)
- [ ] **GATE**: `python scripts/run_full_suite.py` — 170/170 pass

### Phase 3: Unify liquidation price formulas
- [ ] Remove `calculate_liquidation_price_simple()`, use single canonical formula
- [ ] **GATE**: `python trade_cli.py validate standard` passes
```

**Rules:**
- Do NOT write plans only to temp plan files or conversation — they vanish on compaction
- Do NOT create separate plan markdown files — `docs/TODO.md` is the single source of truth
- Supporting analysis docs (like reviews, audits) go in `docs/` and are linked from TODO.md
- Mark items `[x]` as they are completed during implementation

## Where to Find Details

| Topic | Location |
|-------|----------|
| Project status & session context | `docs/TODO.md` |
| Validation best practices | `docs/VALIDATION_BEST_PRACTICES.md` |
| DSL syntax | `docs/PLAY_DSL_REFERENCE.md` |
| Synthetic data patterns | `docs/SYNTHETIC_DATA_REFERENCE.md` |
| Architecture & roadmap | `docs/architecture/ARCHITECTURE.md` |
| Agent readiness & go-live path | `docs/AGENT_READINESS_EVALUATION.md` |
| System defaults | `config/defaults.yml` |

## Reference Documentation

| Topic | Location |
|-------|----------|
| Bybit API docs | `reference/exchanges/bybit/` |
| pybit SDK docs | `reference/exchanges/pybit/` |
