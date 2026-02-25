# TRADE TODO

Open work, bugs, and priorities. Completed work is in `memory/completed_work.md`.

---

## Active Work (backtest quality)

### T1: Warmup Parity Validation
- [ ] Add a validation check that runs each indicator to `is_ready()` and compares vs registry formula
- [ ] **GATE**: `python trade_cli.py validate module --module coverage` passes

### T2: Structure Detection (needs rethink)

Current detectors work but have known limitations. See `docs/STRUCTURE_DETECTION_AUDIT.md`.

Open questions before investing more work:
- `confirmation_close` default should be `True` — simple fix
- Trend detector `strength=2` never fires on real BTC data (4h/12h/D, 6 months)
- Trend/MS timing mismatch: MS fires CHoCH before trend confirms direction change
- CHoCH should only break the BOS-producing swing level, not any prior swing

### T7: Timestamp Correctness Validation Gate (G17)

- [x] Create `src/cli/validate_timestamps.py` — 10 categories, 372 checks
- [x] Register `_gate_timestamps()` in `src/cli/validate.py`
- [x] Add `"timestamps"` to `MODULE_NAMES` and Stage 0 schedule
- [x] Add 6 integration categories (live candle, TimeRange, REST order/position, DuckDB normalization, WS staleness, sim exchange flow)
- [x] Add 4 completeness categories (storage serialization, TimeRange internals, all to_dict() timestamps, tz-aware DataFrame strip)
- [x] Add self-test canary (Cat 21) — proves the gate detects known-bad inputs
- [x] Add tz-aware guard scan (Cat 22) — `.fromisoformat()` + `pd.to_datetime(utc=True)`
- [x] Harden 31 call sites: 28 `.fromisoformat()` + `.replace(tzinfo=None)`, 3 `pd.to_datetime(utc=True)` + `.tz_localize(None)`
- [x] Exempt `indicator_vendor.py` — pandas_ta VWAP requires tz-aware DatetimeIndex (contained scope)
- [x] Convert Cat 22 from warnings to hard-fail gate
- [x] **GATE**: `python trade_cli.py validate module --module timestamps` passes (483 checks, 22 categories, 2.9s)
- [x] **GATE**: `python trade_cli.py validate quick` passes (ALL 7 GATES, 80.6s)

---

## P21: Timestamp Audit Phase 2 — 29 Remaining Bugs

Full codebase audit (302 files) found 10 critical + 19 warning-level timestamp bugs.
Live trading code (`src/core/`, `src/engine/runners/live_runner.py`) is clean.
Hotspot: `src/data/historical_data_store.py` (16 bug locations in funding/OI sync).

### Phase 1: `historical_data_store.py` — Data Layer (CRITICAL)

These bugs corrupt DuckDB timestamps on non-UTC systems. The funding/OI sync has a
triple-stacked bug: `datetime.now()` (local) → `.timestamp()*1000` (local→epoch) →
`fromtimestamp()` without UTC (epoch→local again). Net effect: 5-hour data offset on UTC+5.

- [x] **1a** Lines 904, 1192, 1437, 1907: Replace `datetime.now()` with `utc_now()` in
      `_update_metadata()`, `_update_funding_metadata()`, `_update_oi_metadata()`,
      `update_extremes()`. These write `last_sync`/`last_updated` columns to DuckDB.
- [x] **1b** Lines 1021, 1090, 1094, 1264, 1336, 1340: Replace `datetime.now()` with
      `utc_now()` in `sync_funding()` and `sync_open_interest()` period calculations.
      These compute time windows for Bybit API requests.
- [x] **1c** Lines 1105, 1352: Replace `int(current_end.timestamp() * 1000)` with
      `datetime_to_epoch_ms(current_end)` in `_sync_funding_symbol()` and
      `_sync_open_interest_symbol()`. The `.timestamp()` call on naive dt assumes local time.
- [x] **1d** Lines 1112, 1129, 1359, 1374: Replace `datetime.fromtimestamp(x / 1000)` with
      `datetime.fromtimestamp(x / 1000, tz=timezone.utc).replace(tzinfo=None)` in the
      funding/OI sync methods. Without `tz=utc`, parsed exchange timestamps are local time.
- [x] **1e** Lines 1223, 1468, 1544, 2159: Replace `datetime.now()` with `utc_now()` in
      `get_funding()`, `get_open_interest()`, `get_ohlcv()`, `get_latest_ohlcv()` query methods.
- [x] **1f** Line 1642: Replace `datetime.now()` with `utc_now()` in `status()` `is_current` check.
- [x] **GATE**: `python trade_cli.py validate quick` passes (ALL 6 GATES, 75s)

### Phase 2: `datetime_utils.py` — Core Normalize Functions (CRITICAL)

These bugs affect every caller of `normalize_datetime()` and `normalize_timestamp()`.

- [x] **2a** Line 67: `datetime.fromisoformat(value.replace("Z", "+00:00"))` returns tz-AWARE
      datetime while all other `normalize_datetime()` paths return naive. Any "Z"-terminated
      ISO string (common from APIs/JSON) creates an inconsistent return type that will raise
      `TypeError` when compared with naive datetimes. Fix: add `.replace(tzinfo=None)`.
- [x] **2b** Lines 42-43: `normalize_datetime()` passes through tz-aware `datetime` objects
      unchanged. If a caller passes a tz-aware dt, it violates the UTC-naive convention.
      Fix: add `value.astimezone(timezone.utc).replace(tzinfo=None)` guard.
- [x] **2c** Lines 164-165: `normalize_timestamp()` does `ts.replace(tzinfo=None)` which
      strips the tz label but keeps the numeric value. If `ts` is in a non-UTC timezone
      (e.g., US/Eastern), the result represents Eastern time, not UTC.
      Fix: `ts.astimezone(timezone.utc).replace(tzinfo=None)`.
- [x] **GATE**: `python trade_cli.py validate quick` passes (ALL 6 GATES, 75.9s)

### Phase 3: `backtest_play_tools.py` + `historical_maintenance.py` (CRITICAL/WARNING)

- [x] **3a** `backtest_play_tools.py` line 366: `datetime.fromtimestamp(db_end_ts_ms / 1000)`
      without `tz=timezone.utc`. This is the smoke-mode window calculation — wrong on non-UTC.
      Fix: `datetime.fromtimestamp(db_end_ts_ms / 1000, tz=timezone.utc).replace(tzinfo=None)`.
- [x] **3b** `historical_maintenance.py` lines 270, 503: `datetime.now().isoformat()` in
      `heal_comprehensive()` and `validate_data_quality()` reports. Fix: `utc_now()`.
- [x] **3c** `realtime_models.py` lines 403-407: `BarRecord.from_df_row()` uses
      `pd.Timestamp(ts).to_pydatetime()` which can return tz-aware. Fix: strip tzinfo.
- [x] **GATE**: `python trade_cli.py validate quick` passes (ALL 6 GATES, 79.7s)

### Phase 4: Backtest Artifacts + Preflight (WARNING)

- [x] **4a** `eventlog_writer.py` lines 61, 84: `datetime.now()` in event log header and
      fallback timestamp. Fix: `utc_now()`.
- [x] **4b** `artifact_standards.py` lines 60-62: `_utcnow()` helper returns tz-aware datetime.
      Fix: replace with `utc_now()` import, delete the private helper.
- [x] **4c** `pipeline_signature.py` line 65: `datetime.now(timezone.utc).isoformat()` produces
      tz-aware ISO string with `+00:00` suffix. Fix: `utc_now().isoformat()`.
- [x] **4d** `manifest_writer.py` lines 67, 136: `datetime.now(timezone.utc).replace(tzinfo=None)`
      correct but non-canonical. Fix: `utc_now()`.
- [x] **4e** `preflight.py` line 756: `pd.Timestamp(ts).timestamp() * 1000` on naive dt treats
      as local time. Fix: use `datetime_to_epoch_ms()`.
- [x] **4f** `preflight.py` line 793: `datetime.fromtimestamp(x, tz=utc)` without
      `.replace(tzinfo=None)` — tz-aware datetime stored in `missing_mappings`.
- [x] **4g** `preflight.py` lines 856-861: Promotes naive datetimes to tz-aware for comparison,
      propagates downstream. Fix: keep everything naive.
- [x] **GATE**: `python trade_cli.py validate standard` passes (ALL 13 GATES, 479.8s)

### Phase 5: Scripts + Cosmetic (WARNING)

- [x] **5a** `scripts/run_real_verification.py` line 290: `datetime.now()` → `utc_now()`.
- [x] **5b** `scripts/analysis/structure_audit.py` line 624: `datetime.now()` → `utc_now()`.
- [x] **5c** `scripts/verify_trade_math.py` line 2051: `dt.now()` → `utc_now()`.
- [x] **5d** Deduplicate `_parse_bybit_ts()` from `exchange_positions.py` and
      `exchange_orders_manage.py` into `src/utils/datetime_utils.py`.
- [x] **GATE**: `python trade_cli.py validate quick` passes (ALL 6 GATES, 86.9s)

---

## Pre-Deployment (fix before live trading)

### T3: Live Blockers
- [ ] **GAP-2** No REST API fallback for warmup data. `_load_tf_bars()` tries buffer → DuckDB → fails. Needed for cold-start live.
- [ ] **DATA-011** `_handle_stale_connection()` does REST refresh but doesn't force pybit reconnect.
- [ ] **DATA-017** `panic_close_all()` cancel-before-close ordering — needs integration test.
- [ ] **H22** Sim accepts `funding_events` kwarg but no funding event generation pipeline exists yet.

### T4: Live Engine Rubric
- [ ] Define live parity rubric: backtest results as gold standard
- [ ] Demo mode 24h validation
- [ ] Verify sub-loop activation in live mode

### T5: Live Trading Integration
- [ ] Test LiveIndicatorProvider with real WebSocket data
- [ ] Paper trading integration

### T6: Manual Verification (requires exchange connection)
- [ ] Run demo play 10+ minutes — NO "Signal execution blocked" warnings
- [ ] `play run --play AT_001 --mode demo --headless` prints JSON, Ctrl+C stops
- [ ] `play watch --json`, `play stop --all` work correctly
- [ ] Start → stop → cooldown → restart timing works (15s)

---

## Accepted Behavior

| ID | Note |
|----|------|
| GAP-BD2 | `os._exit(0)` correct — pybit WS threads are non-daemon |

## Platform Issues

- **DuckDB file locking on Windows** — sequential scripts, `run_full_suite.py` has retry logic
- **Windows `os.replace` over open files** — `PermissionError` if another process is mid-read of instance JSON

## Known Issues (non-blocking)

- **pandas_ta `'H'` Deprecation Warning** — cosmetic, `pandas_ta.vwap()` passes `'H'` to `index.to_period()`. Our `IncrementalVWAP` is unaffected.

---

## Commands

### Validation

```bash
python trade_cli.py validate quick              # Pre-commit (~2min, 7 gates)
python trade_cli.py validate standard           # Pre-merge (~7min, 13 gates)
python trade_cli.py validate full               # Pre-release (~10min, 15 gates)
python trade_cli.py validate real               # Real-data verification (~2min)
python trade_cli.py validate module --module X --json  # Single module (PREFERRED for agents)
python trade_cli.py validate pre-live --play X  # Deployment gate
python trade_cli.py validate exchange           # Exchange integration (~30s)
```

### Backtest

```bash
python trade_cli.py backtest run --play X --sync       # Single backtest (sync data first)
python trade_cli.py backtest run --play X --synthetic   # Single backtest (synthetic data)
python scripts/run_full_suite.py                        # 170-play synthetic suite
python scripts/run_real_verification.py                 # 60-play real verification
python scripts/verify_trade_math.py --play X            # Math verification for a play
```

### Debugging & Logging

```bash
# Verbosity flags (apply to ANY command)
python trade_cli.py -q ...                     # Quiet: WARNING only (CI, scripts)
python trade_cli.py -v ...                     # Verbose: signal traces, structure events
python trade_cli.py --debug ...                # Debug: full hash tracing, all internals

# Examples
python trade_cli.py -v backtest run --play X --synthetic   # See WHY signals fire
python trade_cli.py --debug backtest run --play X --sync   # Full hash trace per bar

# Debug subcommands (diagnostic tools)
python trade_cli.py debug math-parity --play X             # Real-data math audit
python trade_cli.py debug snapshot-plumbing --play X       # Snapshot field check
python trade_cli.py debug determinism --run-a A --run-b B  # Compare two runs
python trade_cli.py debug metrics                          # Financial calc audit

# All debug subcommands support --json for structured output
python trade_cli.py debug math-parity --play X --json
```

### Log Files

```bash
# Structured JSONL log (all runs)
tail -f logs/trade.jsonl                       # Live stream
cat logs/trade.jsonl | jq '.event'             # Events only

# Backtest event journal (per-run)
cat artifacts/<input_hash>/events.jsonl        # Fill and close events per trade
```
