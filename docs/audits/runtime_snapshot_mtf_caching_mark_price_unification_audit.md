### RuntimeSnapshot + MTF Caching + Mark Price Unification — Post‑Refactor Audit (Read‑Only)

> **✅ REFACTOR STATUS: COMPLETED** (December 2025)
>
> This document is the **post‑refactor** audit summary. The earlier “gap analysis” findings are now obsolete and have been removed to avoid confusion.
>
> Canonical outcomes now in code:
> - **Canonical `Bar`** with `ts_open` / `ts_close`
> - **`RuntimeSnapshot` is the only strategy input**
> - **MTF/HTF caching** with data‑driven close detection + readiness gate
> - **Mark price unification** (single mark per step)
> - **Preflight data health gate** (+ optional auto bootstrap from launch)
> - **Artifacts** include `run_manifest.json` and `events.jsonl`

**Date**: 2025‑12‑14

---

## What “correct” means now (contract)

### Canonical timing

- **DuckDB `timestamp` column** represents **bar open** (ts_open).
- Engine derives:
  - **`bar.ts_open`**: fill/entry time anchor
  - **`bar.ts_close`**: step time / strategy evaluation time

**Execution semantics (deterministic):**
- Strategy is evaluated at **bar close** (`ts_close`).
- Entry orders fill at **next bar open** (`ts_open`) with slippage.

### Canonical strategy input

- Strategies receive **`RuntimeSnapshot`** (`src/backtest/runtime/types.py`).
- Snapshot includes:
  - `ts_close` (step time)
  - `bar_ltf` (canonical `Bar`)
  - `exchange_state` (USDT‑named state)
  - `features_{htf,mtf,ltf}` (feature snapshots)
  - `mark_price` + `mark_price_source`

### Multi‑timeframe caching + readiness gate

- Multi‑TF mode uses **data‑driven close detection** (`ts_close` sets) and carry‑forward caching.
- Until HTF+MTF caches are ready, engine records equity but **skips strategy evaluation**.

### Mark price unification (single source of truth per step)

- `SimulatedExchange.process_bar()` computes **mark exactly once** per step and returns it via `StepResult`.
- Engine passes that mark into `SnapshotBuilder`; snapshot building **never recomputes** mark.

**Important current constraint:**
- The backtest engine currently enforces `risk_profile.mark_price_source == "close"` (guardrail for Phase‑1 mark proxy modes).

---

## Where to look in code (canonical sources)

- **Canonical types**: `src/backtest/runtime/types.py`
  - `Bar`, `FeatureSnapshot`, `ExchangeState`, `RuntimeSnapshot`
- **Engine orchestration**: `src/backtest/engine.py`
  - bar construction (`ts_open`/`ts_close`)
  - MTF/HTF close‑ts maps + caching
  - readiness gate
  - mark unification (`StepResult` → snapshot)
- **Simulated exchange step**: `src/backtest/sim/exchange.py`
  - single mark computation per step
  - fills at `ts_open`, MTM update at `ts_close`
- **Preflight gate + artifacts wiring**: `src/tools/backtest_tools.py`
  - `backtest_preflight_check_tool()` (heal loop + optional `sync_full_from_launch_tool`)
  - `backtest_run_tool()` writes `run_manifest.json` + `events.jsonl`

---

## Working example (matches current tools)

Run a backtest via tools (recommended path):

```python
from src.tools.backtest_tools import backtest_run_tool

result = backtest_run_tool(
    system_id="SOLUSDT_5m_ema_rsi_atr_pure",
    window_name="hygiene",
    write_artifacts=True,
    run_preflight=True,
)

if result.success:
    m = result.data["metrics"]
    print("trades", m["total_trades"])
    print("pnl", m["net_profit"])
    print("win_rate", m["win_rate"])
    print("sharpe", m["sharpe"])
    print("artifact_dir", result.data["artifact_dir"])
    print("manifest", result.data["manifest_path"])
    print("eventlog", result.data["eventlog_path"])
else:
    print("error", result.error)
```

---

## Artifacts (current)

Backtest contract artifacts live under:

```
data/backtests/{system_id}/{symbol}/{tf}/{window_name}/{run_id}/
  result.json
  trades.csv
  equity.csv
  account_curve.csv
  run_manifest.json
  events.jsonl
```

---

## Known follow‑ups (explicitly out of scope here)

- Allowing mark proxies beyond `close` (e.g., `hlc3`, `ohlc4`) requires lifting the engine guardrail and ensuring all downstream semantics remain unified. The exchange already computes mark through `PriceModel`; the guardrail is currently enforced in the engine.
