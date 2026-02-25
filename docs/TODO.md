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
python trade_cli.py validate quick              # Pre-commit (~2min, 6 gates)
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
