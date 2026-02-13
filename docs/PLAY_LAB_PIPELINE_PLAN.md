# Play Lab Pipeline - Design Document

## Context

Currently, plays are created manually as YAML files and tested ad-hoc via `backtest run`. There's no structured pipeline for going from a trading idea through testing, review, and approval. This document describes the `lab` CLI command: a 4-stage pipeline (Design -> Test -> Review -> Approve), accessible by both humans and agents via flags.

## Directory Layout

```
plays/
  ideas/        # Stage 1: drafts, scaffolds
  testing/      # Stage 2: under backtest, has results
  approved/     # Stage 3: passed all gates
  archived/     # Retired or rejected plays
  validation/   # Existing (unchanged)
```

Each play gets a sidecar `<play_id>.meta.json` with history, test runs, reviews, and approval status. Keeps play YAML clean for the engine.

## CLI Commands

```bash
# DESIGN - create or validate a play
python trade_cli.py lab design --idea "EMA cross with RSI on SOL 15m" --name sol_ema_rsi
python trade_cli.py lab design --from-template sol_ema_triple_long --name sol_custom
python trade_cli.py lab design --validate --play sol_ema_rsi

# TEST - run backtests with approval criteria
python trade_cli.py lab test --play sol_ema_rsi --start 2025-01-01 --end 2025-06-30
python trade_cli.py lab test --play sol_ema_rsi --start 2025-01-01 --end 2025-06-30 --robustness
python trade_cli.py lab test --play sol_ema_rsi --start ... --end ... --benchmark buy-and-hold
python trade_cli.py lab test --play sol_ema_rsi --start ... --end ... --profile conservative
python trade_cli.py lab test --play sol_ema_rsi --start ... --end ... --min-trades 20 --min-sharpe 1.0

# REVIEW - inspect results, record verdict
python trade_cli.py lab review --play sol_ema_rsi                    # show review data
python trade_cli.py lab review --play sol_ema_rsi --auto             # agent auto-review
python trade_cli.py lab review --play sol_ema_rsi --approve --notes "Clean curve"
python trade_cli.py lab review --play sol_ema_rsi --reject --notes "Too much drawdown"

# APPROVE - run gates + promote to approved/
python trade_cli.py lab approve --play sol_ema_rsi                   # run gates + promote
python trade_cli.py lab approve --play sol_ema_rsi --force           # skip gates

# MANAGEMENT
python trade_cli.py lab list                                         # all stages
python trade_cli.py lab list --stage testing
python trade_cli.py lab status --play sol_ema_rsi
python trade_cli.py lab reject --play sol_ema_rsi --notes "..."
python trade_cli.py lab archive --play sol_ema_rsi
python trade_cli.py lab history --play sol_ema_rsi
```

All commands support `--json` for agent consumption. Exit codes: 0=success, 1=failure.

## Approval Gates

| Gate | Check | Configurable? |
|------|-------|---------------|
| LG1 Metric Thresholds | min trades, win rate, max drawdown, min sharpe, min profit factor | Yes (profiles + CLI overrides) |
| LG2 Review Required | At least 1 review with verdict=approve | Yes (skippable with `--force`) |
| LG3 Robustness | If robustness data exists, sharpe variance < 50% of mean across windows | Optional (only if robustness runs exist) |
| LG4 YAML Valid | Play parses cleanly via `load_play()` | Always required |
| LG5 Benchmark Beat | If benchmark data exists, strategy sharpe > benchmark | Optional (only if benchmark data exists) |

### Threshold Profiles

Stored in `config/lab_defaults.yml`:

| Profile | min_trades | min_win_rate | max_drawdown | min_sharpe | min_profit_factor |
|---------|-----------|-------------|-------------|-----------|-----------------|
| default | 10 | 0.40 | 0.20 | 0.5 | 1.2 |
| conservative | 20 | 0.50 | 0.10 | 1.0 | 1.5 |
| aggressive | 5 | 0.35 | 0.30 | 0.3 | 1.0 |

## Sidecar Metadata Format

Each play gets a `<play_id>.meta.json` alongside its YAML:

```json
{
  "play_id": "sol_ema_rsi",
  "stage": "testing",
  "created_at": "2026-02-13T10:30:00Z",
  "created_by": "agent",
  "idea": "SOL 15m EMA pullback in 4h uptrend",
  "history": [
    {"action": "created", "stage": "ideas", "at": "2026-02-13T10:30:00Z", "by": "agent"},
    {"action": "promoted", "from": "ideas", "to": "testing", "at": "2026-02-13T10:35:00Z"}
  ],
  "test_runs": [
    {
      "run_id": "run-001",
      "at": "2026-02-13T10:35:00Z",
      "start": "2025-01-01",
      "end": "2025-06-30",
      "symbol": "SOLUSDT",
      "passed": true,
      "metrics": {
        "trades_count": 42,
        "win_rate": 0.62,
        "net_pnl_usdt": 1234.56,
        "sharpe": 1.8,
        "max_drawdown_pct": 0.08,
        "profit_factor": 2.1
      }
    }
  ],
  "reviews": [
    {
      "reviewer": "human",
      "at": "2026-02-13T11:00:00Z",
      "verdict": "approve",
      "notes": "Clean equity curve, good drawdown profile"
    }
  ],
  "approval": {
    "approved": true,
    "at": "2026-02-13T11:05:00Z",
    "by": "agent",
    "gates_passed": ["metric_thresholds", "robustness", "review_required"]
  }
}
```

## Architecture - Files to Create/Modify

### New Files

1. **`src/tools/lab_tools.py`** - All business logic
   - `PlayMeta` dataclass (sidecar metadata model with `load()` / `save()`)
   - `MetricThresholds` dataclass (with `from_profile()`, `override_from()`)
   - `ApprovalGateResult` dataclass
   - Tool functions:
     - `lab_design_tool()` - scaffold generation, template cloning, validation
     - `lab_test_tool()` - backtest + metric evaluation + robustness + benchmark
     - `lab_review_tool()` - show data / auto-review / record verdict
     - `lab_approve_tool()` - run gates + promote file
     - `lab_list_tool()`, `lab_status_tool()`, `lab_reject_tool()`, `lab_archive_tool()`, `lab_history_tool()`
   - Internal helpers:
     - `_generate_play_scaffold()` - natural language idea to YAML scaffold
     - `_run_robustness_checks()` - split date range into overlapping windows, run each
     - `_run_buy_and_hold_benchmark()` - compute buy-and-hold return from DuckDB
     - `_evaluate_metrics()` - check `ResultsSummary` against `MetricThresholds`
     - `_auto_review()` - agent review (equity curve shape, drawdown events, streaks)
     - `_move_play()` - atomic file movement between stage directories

2. **`config/lab_defaults.yml`** - threshold profiles, robustness settings

### Modified Files

3. **`src/cli/argparser.py`** - Add `_setup_lab_subcommands(subparsers)` with all 9 subcommands
4. **`src/cli/subcommands.py`** - Add 9 `handle_lab_*()` handler functions
5. **`trade_cli.py`** - Wire lab command dispatch in `main()`, import handlers

### Key Code Reuse

| What | Where | How Used |
|------|-------|----------|
| `backtest_run_play_tool()` | `src/tools/backtest_play_tools.py` | Drives all backtesting in `lab_test_tool` |
| `load_play()` | `src/backtest/play/play.py` | Already searches `plays/` recursively via rglob - new subdirs found automatically |
| `ResultsSummary` | `src/backtest/artifacts/artifact_standards.py:937` | All 70+ metrics available for threshold evaluation |
| `ToolResult` | `src/tools/shared.py:34` | Standard return type for all tool functions |
| `GateResult` pattern | `src/cli/validate.py` | Model for `ApprovalGateResult` design |

## Design Step - LLM Integration Point

The initial `_generate_play_scaffold()` produces valid YAML from CLI params (symbol, exec_tf, etc.) with placeholder indicators and conditions. The interface is:

```python
def _generate_play_scaffold(name: str, idea: str, symbol: str, exec_tf: str) -> str:
    """Returns valid play YAML string."""
```

A future `_generate_play_with_llm()` can replace this, receiving the DSL reference + indicator registry + user idea and calling an LLM API. The interface is identical, making the swap seamless. The function would:
1. Build a prompt with DSL reference (`docs/PLAY_DSL_REFERENCE.md`) + available indicators (44) + example plays
2. Call LLM API (Claude / other)
3. Parse + validate the response YAML via `Play.from_dict()`
4. Return validated YAML or fall back to scaffold

## Agent Workflow (End-to-End)

An agent can drive the full pipeline using only CLI + exit codes:

```bash
# 1. Create play from idea
python trade_cli.py lab design --idea "SOL 15m EMA pullback with RSI and ADX" --name sol_pullback_v1 --json

# 2. Test with thresholds
python trade_cli.py lab test --play sol_pullback_v1 --start 2025-01-01 --end 2025-06-30 --profile default --json

# 3. Robustness + benchmark
python trade_cli.py lab test --play sol_pullback_v1 --start 2025-01-01 --end 2025-06-30 --robustness --benchmark buy-and-hold --json

# 4. Auto-review
python trade_cli.py lab review --play sol_pullback_v1 --auto --json

# 5. Approve
python trade_cli.py lab approve --play sol_pullback_v1 --json

# 6. Verify
python trade_cli.py lab list --stage approved --json
```

## Implementation Order

1. Create directories (`plays/ideas/`, `plays/testing/`, `plays/approved/`, `plays/archived/`) + `config/lab_defaults.yml`
2. Build `src/tools/lab_tools.py` core: `PlayMeta`, `MetricThresholds`, `Stage` enum, `_move_play()`
3. Implement `lab_design_tool` (scaffold + template clone + validate)
4. Implement `lab_list_tool`, `lab_status_tool`, `lab_history_tool`
5. Add argparse (`_setup_lab_subcommands`) + handlers + wiring for design/list/status/history
6. Implement `lab_test_tool` (backtest + metric eval + robustness + benchmark + auto-promote from ideas->testing)
7. Add argparse + handlers + wiring for test
8. Implement `lab_review_tool` + `lab_approve_tool` + `lab_reject_tool` + `lab_archive_tool`
9. Add argparse + handlers + wiring for review/approve/reject/archive
10. End-to-end smoke test

## Verification

```bash
python trade_cli.py lab design --idea "EMA 9/21 cross on SOL 15m" --name test_lab_play --json
python trade_cli.py lab list --json
python trade_cli.py lab test --play test_lab_play --start 2025-01-01 --end 2025-06-30 --json
python trade_cli.py lab review --play test_lab_play --auto --json
python trade_cli.py lab approve --play test_lab_play --json
python trade_cli.py lab list --stage approved --json
python trade_cli.py lab history --play test_lab_play --json
```
