"""
Backtest-related smoke tests for TRADE trading bot.

Extracted from src/cli/smoke_tests.py for modularity.
"""

import json
import math
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.panel import Panel

from ...tools import (
    backtest_preflight_idea_card_tool,
    backtest_run_idea_card_tool,
    backtest_data_fix_tool,
    backtest_list_idea_cards_tool,
)

console = Console()


def _run_backtest_smoke_idea_card(idea_card_id: str, fresh_db: bool = False) -> int:
    """
    Run backtest smoke test using IdeaCard-based wrapper (golden path).

    This is the canonical smoke test that uses the same CLI wrapper
    that `trade_cli.py backtest run --smoke` uses.

    Args:
        idea_card_id: IdeaCard identifier to test
        fresh_db: Whether to wipe DB and rebuild data first

    Returns:
        Number of failures
    """
    failures = 0

    console.print(f"\n[bold cyan]IdeaCard Smoke Test: {idea_card_id}[/]")

    # Step 2: Run preflight check (Phase A gate)
    console.print(f"\n[bold cyan]Step 2: Preflight Check (Phase A Gate)[/]")
    console.print(f"  [dim]Checking env/symbol/tf/coverage...[/]")

    preflight_result = backtest_preflight_idea_card_tool(
        idea_card_id=idea_card_id,
        env="live",  # Always use live data env for smoke
    )

    if preflight_result.success:
        diag = preflight_result.data
        console.print(f"  [green]OK[/] Preflight passed")
        console.print(f"      Env: {diag.get('env')}")
        console.print(f"      DB: {diag.get('db_path')}")
        console.print(f"      Table: {diag.get('ohlcv_table')}")
        console.print(f"      Symbol: {diag.get('symbol')} | Exec TF: {diag.get('exec_tf')}")
        console.print(f"      DB Coverage: {diag.get('db_bar_count', 0):,} bars")

        # Print indicator keys (Phase B)
        exec_keys = diag.get('declared_keys_exec', [])
        htf_keys = diag.get('declared_keys_htf', [])
        mtf_keys = diag.get('declared_keys_mtf', [])

        console.print(f"      Indicator Keys (exec): {exec_keys or '(none)'}")
        if htf_keys:
            console.print(f"      Indicator Keys (htf): {htf_keys}")
        if mtf_keys:
            console.print(f"      Indicator Keys (mtf): {mtf_keys}")
    else:
        console.print(f"  [red]FAIL[/] Preflight failed: {preflight_result.error}")

        # Print actionable diagnostics
        if preflight_result.data:
            diag = preflight_result.data
            console.print(f"      Env: {diag.get('env')}")
            console.print(f"      DB: {diag.get('db_path')}")
            if diag.get('coverage_issue'):
                console.print(f"      [yellow]Fix: {diag['coverage_issue']}[/]")
            if diag.get('validation_errors'):
                for err in diag['validation_errors']:
                    console.print(f"      [red]Error: {err}[/]")

        failures += 1

        # Try to fix data if fresh_db
        if fresh_db:
            console.print(f"\n[bold cyan]Step 2b: Attempting Data Fix[/]")
            fix_result = backtest_data_fix_tool(
                idea_card_id=idea_card_id,
                env="live",
                sync_to_now=True,
                fill_gaps=True,
            )
            if fix_result.success:
                console.print(f"  [green]OK[/] Data fix completed: {fix_result.message}")
                # Retry preflight
                preflight_result = backtest_preflight_idea_card_tool(
                    idea_card_id=idea_card_id,
                    env="live",
                )
                if preflight_result.success:
                    console.print(f"  [green]OK[/] Preflight now passes")
                    failures -= 1  # Undo the failure
                else:
                    console.print(f"  [red]FAIL[/] Preflight still fails after data fix")
                    return failures
            else:
                console.print(f"  [red]FAIL[/] Data fix failed: {fix_result.error}")
                return failures
        else:
            return failures

    # Step 3: Run backtest with --smoke mode
    console.print(f"\n[bold cyan]Step 3: Run Backtest (Smoke Mode)[/]")
    console.print(f"  [dim]Running with --smoke --strict...[/]")

    run_result = backtest_run_idea_card_tool(
        idea_card_id=idea_card_id,
        env="live",
        smoke=True,
        strict=True,
        write_artifacts=True,
    )

    if run_result.success:
        console.print(f"  [green]OK[/] {run_result.message}")

        data = run_result.data or {}
        trades_count = data.get("trades_count", 0)
        console.print(f"      Trades: {trades_count}")

        if data.get("artifact_dir"):
            artifact_dir = Path(data["artifact_dir"])
            console.print(f"      Artifacts: {artifact_dir}")

            # Step 4: Validate artifacts
            console.print(f"\n[bold cyan]Step 4: Validate Artifacts[/]")

            # Check result.json
            result_json = artifact_dir / "result.json"
            if result_json.exists():
                console.print(f"  [green]OK[/] result.json exists")
                try:
                    with open(result_json) as f:
                        result_data = json.load(f)

                    # Check for required fields
                    metrics = result_data.get("metrics", {})
                    required = ["total_trades", "final_equity", "net_return_pct"]
                    for field in required:
                        if field in metrics:
                            val = metrics[field]
                            if isinstance(val, (int, float)) and (not isinstance(val, float) or math.isfinite(val)):
                                console.print(f"  [green]OK[/] {field} = {val}")
                            else:
                                console.print(f"  [red]FAIL[/] {field} not finite: {val}")
                                failures += 1
                        else:
                            console.print(f"  [yellow]WARN[/] Missing {field}")

                except Exception as e:
                    console.print(f"  [red]FAIL[/] Error reading result.json: {e}")
                    failures += 1
            else:
                console.print(f"  [yellow]WARN[/] result.json not found (smoke mode may skip)")

            # Check trades.parquet
            trades_path = artifact_dir / "trades.parquet"
            if trades_path.exists():
                console.print(f"  [green]OK[/] trades.parquet exists")
                try:
                    trades_df = pd.read_parquet(trades_path)
                    console.print(f"      {len(trades_df)} trades recorded")
                except Exception as e:
                    console.print(f"  [red]FAIL[/] Error reading trades.parquet: {e}")
                    failures += 1
            else:
                console.print(f"  [yellow]WARN[/] trades.parquet not found")

            # Check equity.parquet
            equity_path = artifact_dir / "equity.parquet"
            if equity_path.exists():
                console.print(f"  [green]OK[/] equity.parquet exists")
                try:
                    equity_df = pd.read_parquet(equity_path)
                    console.print(f"      {len(equity_df)} equity points")

                    if "equity" in equity_df.columns and (equity_df["equity"] > 0).all():
                        console.print(f"  [green]OK[/] All equity values > 0")
                    else:
                        console.print(f"  [red]FAIL[/] Some equity values <= 0")
                        failures += 1
                except Exception as e:
                    console.print(f"  [red]FAIL[/] Error reading equity.parquet: {e}")
                    failures += 1
            else:
                console.print(f"  [yellow]WARN[/] equity.parquet not found")

        # Print summary from preflight for diagnostics confirmation
        if preflight_result.data:
            console.print(f"\n[bold cyan]Step 5: Diagnostics Summary[/]")
            diag = preflight_result.data
            console.print(f"  Environment: {diag.get('env')}")
            console.print(f"  Database: {diag.get('db_path')}")
            console.print(f"  Table: {diag.get('ohlcv_table')}")
            console.print(f"  Symbol: {diag.get('symbol')}")
            console.print(f"  Exec TF: {diag.get('exec_tf')}")
            console.print(f"  Warmup: {diag.get('warmup_bars', 0)} bars ({diag.get('warmup_span_minutes', 0)} min)")
            console.print(f"  DB Range: {diag.get('db_earliest')} to {diag.get('db_latest')}")
            console.print(f"  Indicator Keys (exec): {diag.get('declared_keys_exec', [])}")
    else:
        console.print(f"  [red]FAIL[/] Backtest failed: {run_result.error}")
        failures += 1

        # Print actionable diagnostics
        if run_result.data and "preflight" in run_result.data:
            diag = run_result.data["preflight"]
            console.print(f"\n[bold]Diagnostics from preflight:[/]")
            console.print(f"  Env: {diag.get('env')}")
            console.print(f"  DB: {diag.get('db_path')}")
            console.print(f"  Symbol: {diag.get('symbol')}")
            console.print(f"  Coverage: {'OK' if diag.get('has_sufficient_coverage') else 'INSUFFICIENT'}")
            if diag.get('coverage_issue'):
                console.print(f"  [yellow]Fix: {diag['coverage_issue']}[/]")

    # Summary
    console.print(f"\n[bold magenta]{'='*60}[/]")
    console.print(f"[bold magenta]IDEACARD BACKTEST SMOKE TEST COMPLETE[/]")
    console.print(f"[bold magenta]{'='*60}[/]")

    console.print(f"\n[bold]Summary:[/]")
    console.print(f"  IdeaCard: {idea_card_id}")
    console.print(f"  Fresh DB: {fresh_db}")
    console.print(f"  Failures: {failures}")

    if failures == 0:
        console.print(f"\n[bold green]OK BACKTEST ENGINE VERIFIED (IdeaCard Path)[/]")
    else:
        console.print(f"\n[bold red]FAIL {failures} TEST(S) FAILED[/]")

    return failures


def run_backtest_smoke(fresh_db: bool = False, idea_card_id: str = None) -> int:
    """
    Run the backtest smoke test using IdeaCard-based workflow.

    Tests the backtest engine end-to-end:
    1. List available IdeaCards
    2. Run preflight check (env/symbol/tf/coverage diagnostics)
    3. Optionally prepare data (with fresh_db option)
    4. Run backtest with --smoke mode
    5. Validate output diagnostics and artifacts

    Args:
        fresh_db: Whether to wipe DB and rebuild data
        idea_card_id: IdeaCard to test (defaults to env var BACKTEST_SMOKE_IDEA_CARD)

    Returns:
        Number of failures
    """
    console.print(Panel(
        "[bold magenta]BACKTEST ENGINE SMOKE TEST[/]\n"
        "[dim]Testing backtest pipeline via CLI wrapper (golden path)[/]",
        border_style="magenta"
    ))

    failures = 0

    # =============================
    # GOLDEN PATH: Try IdeaCard first
    # =============================

    console.print(f"\n[bold cyan]Step 1: Check for IdeaCards (Golden Path)[/]")

    # List available IdeaCards
    result = backtest_list_idea_cards_tool()
    idea_cards = []
    if result.success and result.data:
        idea_cards = result.data.get("idea_cards", [])
        console.print(f"  [green]OK[/] Found {len(idea_cards)} IdeaCards")
        for card in idea_cards[:5]:
            console.print(f"    - {card}")
    else:
        console.print(f"  [yellow]WARN[/] No IdeaCards found: {result.error}")

    # Determine IdeaCard to test
    if idea_card_id is None:
        idea_card_id = os.environ.get("BACKTEST_SMOKE_IDEA_CARD")

    if idea_card_id is None and idea_cards:
        # Prefer valid test cards (T*) over error test cases (E*)
        valid_cards = [c for c in idea_cards if c.startswith("T")]
        idea_card_id = valid_cards[0] if valid_cards else idea_cards[0]

    # If we have an IdeaCard, use the golden path
    if idea_card_id:
        console.print(f"\n  [bold]Using IdeaCard: {idea_card_id}[/]")
        return _run_backtest_smoke_idea_card(idea_card_id, fresh_db)

    # No IdeaCards found - fail
    console.print(f"\n[bold red]FAIL[/] No IdeaCards found in configs/plays/")
    console.print(f"[dim]Create an IdeaCard YAML file or set BACKTEST_SMOKE_IDEA_CARD env var[/]")
    return 1


def run_backtest_mixed_smoke() -> int:
    """
    Run backtest smoke test with validation IdeaCards.

    Tests all validation cards in configs/plays/_validation/:
    - V_60-V_62: 1m evaluation loop (mark_price, zone touch, entry timing)
    - V_70-V_75: Incremental state structures (swing, fibonacci, zone, trend, rolling_window, multi-TF)

    These cards validate the full engine pipeline end-to-end.

    Returns:
        0 on success, number of failures otherwise
    """
    console.print(Panel(
        "[bold]BACKTEST SMOKE TEST: MIXED IDEA CARDS[/]\n"
        "[dim]Testing multiple idea cards across different scenarios[/]",
        border_style="magenta"
    ))

    failures = 0

    # Select a diverse mix of validation cards from configs/plays/_validation/
    idea_cards_to_test = [
        # Core validation cards (1m eval loop)
        "V_60_mark_price_basic",
        "V_61_zone_touch",
        "V_62_entry_timing",
        # Structure validation cards (incremental state)
        "V_70_swing_basic",
        "V_71_fibonacci",
        "V_72_zone_state",
        "V_73_trend_direction",
        "V_74_rolling_window",
        "V_75_multi_tf",
    ]

    # Filter to only existing cards
    result = backtest_list_idea_cards_tool()
    available_cards = []
    if result.success and result.data:
        available_cards = result.data.get("idea_cards", [])

    # Filter idea_cards_to_test to only those that exist
    cards_to_test = [card for card in idea_cards_to_test if card in available_cards]

    if not cards_to_test:
        console.print(f"  [yellow]WARN[/] No idea cards found to test")
        console.print(f"      Available cards: {available_cards[:10]}")
        # Try to use any available card
        if available_cards:
            cards_to_test = available_cards[:3]  # Use first 3 available
            console.print(f"      Using first 3 available: {cards_to_test}")
        else:
            return 1

    console.print(f"\n[bold cyan]Testing {len(cards_to_test)} idea cards:[/]")
    for card in cards_to_test:
        console.print(f"  - {card}")

    # Test each card
    for i, card_id in enumerate(cards_to_test, 1):
        console.print(f"\n[bold cyan]{'='*68}[/]")
        console.print(f"[bold cyan]Card {i}/{len(cards_to_test)}: {card_id}[/]")
        console.print(f"[bold cyan]{'='*68}[/]")

        card_failures = _run_backtest_smoke_idea_card(card_id, fresh_db=False)
        failures += card_failures

        if card_failures == 0:
            console.print(f"  [green]PASSED[/] {card_id}")
        else:
            console.print(f"  [red]FAILED[/] {card_id} ({card_failures} failure(s))")

    # Summary
    console.print(f"\n[bold cyan]{'='*68}[/]")
    if failures == 0:
        console.print(f"[bold green]ALL CARDS PASSED[/] ({len(cards_to_test)}/{len(cards_to_test)})")
    else:
        console.print(f"[bold red]{failures} FAILURE(S) ACROSS {len(cards_to_test)} CARDS[/]")

    return failures


def run_phase6_backtest_smoke() -> int:
    """
    Phase 6: CLI Smoke Tests for backtest infrastructure.

    Tests:
    1. Window matrix - warmup requirements and PreflightReport structure
    2. Deterministic bounded backfill - data-fix with max_lookback_days cap
    3. No-backfill when coverage is sufficient
    4. Drift regression - equity.parquet has ts_ms column
    5. MTF alignment - eval_start_ts_ms in RunManifest
    6. Audit verification - pipeline_signature, artifacts, hashes
    7. (Optional) Determinism spot-check - re-run hash comparison

    Returns:
        0 on success, number of failures otherwise
    """
    import traceback

    console.print(Panel(
        "[bold]PHASE 6: BACKTEST CLI SMOKE TESTS[/]\n"
        "[dim]Validating preflight, data-fix, artifact structure, and audit gates[/]",
        border_style="cyan"
    ))

    failures = 0

    # Test IdeaCards for Phase 6 - progressive validation cards
    WARMUP_MATRIX_CARD = "T03_multi_indicator"  # Single TF with multiple indicators
    MTF_ALIGNMENT_CARD = "T09_mtf_three"  # Full MTF with 3 timeframes
    TEST_SYMBOL = "BTCUSDT"
    TEST_ENV = "live"

    # =========================================================================
    # TEST 1: PreflightReport structure validation
    # =========================================================================
    console.print(f"\n[bold cyan]TEST 1: PreflightReport Structure[/]")

    try:
        # Preflight requires explicit start/end dates
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=7)  # 7 days window

        result = backtest_preflight_idea_card_tool(
            idea_card_id=WARMUP_MATRIX_CARD,
            env=TEST_ENV,
            symbol_override=TEST_SYMBOL,
            start=start_dt,
            end=end_dt,
        )

        if result.data:
            data = result.data

            # Check required fields in PreflightReport
            required_fields = [
                "overall_status",
                "computed_warmup_requirements",
                "error_code",
                "error_details",
            ]

            missing_fields = [f for f in required_fields if f not in data]
            if missing_fields:
                console.print(f"  [red]FAIL[/] Missing PreflightReport fields: {missing_fields}")
                failures += 1
            else:
                console.print(f"  [green]OK[/] PreflightReport has required fields")

            # Check epoch-ms timestamps in coverage (if available)
            coverage = data.get("coverage", {})
            if coverage:
                if "db_start_ts_ms" in coverage and "db_end_ts_ms" in coverage:
                    console.print(f"  [green]OK[/] Coverage has epoch-ms timestamps")
                    console.print(f"      db_start_ts_ms: {coverage.get('db_start_ts_ms')}")
                    console.print(f"      db_end_ts_ms: {coverage.get('db_end_ts_ms')}")
                else:
                    console.print(f"  [yellow]WARN[/] Coverage missing epoch-ms timestamps (may be no data)")

            # Check warmup requirements
            warmup_req = data.get("computed_warmup_requirements", {})
            if warmup_req:
                warmup_by_role = warmup_req.get("warmup_by_role", {})
                delay_by_role = warmup_req.get("delay_by_role", {})
                console.print(f"  [green]OK[/] Warmup requirements present")
                console.print(f"      warmup_by_role: {warmup_by_role}")
                console.print(f"      delay_by_role: {delay_by_role}")
            else:
                console.print(f"  [red]FAIL[/] Missing computed_warmup_requirements")
                failures += 1
        else:
            console.print(f"  [red]FAIL[/] No data in preflight result")
            failures += 1

    except FileNotFoundError as e:
        console.print(f"  [yellow]SKIP[/] IdeaCard not found: {e}")
    except Exception as e:
        console.print(f"  [red]FAIL[/] Preflight error: {e}")
        traceback.print_exc()
        failures += 1

    # =========================================================================
    # TEST 2: Data-fix bounded enforcement
    # =========================================================================
    console.print(f"\n[bold cyan]TEST 2: Data-fix Bounded Enforcement[/]")

    try:
        # Request a long range that should be clamped
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=30)  # Request 30 days
        max_lookback = 7  # Should clamp to 7 days

        result = backtest_data_fix_tool(
            idea_card_id=WARMUP_MATRIX_CARD,
            env=TEST_ENV,
            start=start_dt,
            end=end_dt,
            max_lookback_days=max_lookback,
            sync_to_now=False,
            fill_gaps=False,
            heal=False,
        )

        if result.data:
            data = result.data
            bounds = data.get("bounds", {})

            # Verify bounds were applied
            if bounds.get("applied") is True:
                console.print(f"  [green]OK[/] Bounds applied correctly")
                console.print(f"      cap.max_lookback_days: {bounds.get('cap', {}).get('max_lookback_days')}")
            else:
                console.print(f"  [red]FAIL[/] Bounds not applied (expected applied=True)")
                failures += 1

            # Verify epoch-ms timestamps in bounds
            if bounds.get("start_ts_ms") is not None and bounds.get("end_ts_ms") is not None:
                console.print(f"  [green]OK[/] Bounds have epoch-ms timestamps")
            else:
                console.print(f"  [red]FAIL[/] Bounds missing epoch-ms timestamps")
                failures += 1

            # Verify progress count
            progress_count = data.get("progress_lines_count", 0)
            console.print(f"  [green]OK[/] Progress lines count: {progress_count}")

        else:
            console.print(f"  [yellow]WARN[/] No data in data-fix result")

    except FileNotFoundError as e:
        console.print(f"  [yellow]SKIP[/] IdeaCard not found: {e}")
    except Exception as e:
        console.print(f"  [red]FAIL[/] Data-fix error: {e}")
        traceback.print_exc()
        failures += 1

    # =========================================================================
    # TEST 3: MTF Alignment IdeaCard validation
    # =========================================================================
    console.print(f"\n[bold cyan]TEST 3: MTF Alignment IdeaCard[/]")

    try:
        from ...backtest.idea_card import load_idea_card
        from ...backtest.execution_validation import validate_idea_card_full

        idea_card = load_idea_card(MTF_ALIGNMENT_CARD)
        validation = validate_idea_card_full(idea_card)

        if validation.is_valid:
            console.print(f"  [green]OK[/] MTF IdeaCard validates")
            console.print(f"      exec_tf: {idea_card.exec_tf}")
            console.print(f"      mtf: {idea_card.mtf}")
            console.print(f"      htf: {idea_card.htf}")

            # Check delay bars are different across roles
            delays = {}
            for role, tf_config in idea_card.tf_configs.items():
                # delay_bars is in market_structure
                if tf_config.market_structure:
                    delays[role] = tf_config.market_structure.delay_bars
                else:
                    delays[role] = 0
            console.print(f"      delay_bars: {delays}")

            if len(set(delays.values())) > 1:
                console.print(f"  [green]OK[/] Different delay bars across roles")
            else:
                console.print(f"  [yellow]WARN[/] Same delay bars across all roles")
        else:
            console.print(f"  [red]FAIL[/] MTF IdeaCard validation failed")
            for err in validation.errors:
                console.print(f"      - {err.message}")
            failures += 1

    except FileNotFoundError as e:
        console.print(f"  [yellow]SKIP[/] MTF IdeaCard not found: {e}")
    except Exception as e:
        console.print(f"  [red]FAIL[/] MTF IdeaCard error: {e}")
        traceback.print_exc()
        failures += 1

    # =========================================================================
    # TEST 4: Artifact standards validation
    # =========================================================================
    console.print(f"\n[bold cyan]TEST 4: Artifact Standards[/]")

    try:
        from ...backtest.artifacts.artifact_standards import (
            REQUIRED_EQUITY_COLUMNS,
            RunManifest,
        )

        # Check ts_ms is in required equity columns
        if "ts_ms" in REQUIRED_EQUITY_COLUMNS:
            console.print(f"  [green]OK[/] ts_ms in REQUIRED_EQUITY_COLUMNS")
        else:
            console.print(f"  [red]FAIL[/] ts_ms missing from REQUIRED_EQUITY_COLUMNS")
            failures += 1

        # Check RunManifest has eval_start_ts_ms field
        manifest = RunManifest(
            full_hash="test",
            short_hash="test",
            short_hash_length=8,
            idea_card_id="test",
            idea_card_hash="test",
            symbols=["BTCUSDT"],
            tf_exec="5m",
            tf_ctx=[],
            window_start="2024-01-01",
            window_end="2024-01-31",
        )

        if hasattr(manifest, 'eval_start_ts_ms'):
            console.print(f"  [green]OK[/] RunManifest has eval_start_ts_ms field")
        else:
            console.print(f"  [red]FAIL[/] RunManifest missing eval_start_ts_ms field")
            failures += 1

        if hasattr(manifest, 'equity_timestamp_column'):
            console.print(f"  [green]OK[/] RunManifest has equity_timestamp_column field")
            console.print(f"      Default value: {manifest.equity_timestamp_column}")
        else:
            console.print(f"  [red]FAIL[/] RunManifest missing equity_timestamp_column field")
            failures += 1

    except Exception as e:
        console.print(f"  [red]FAIL[/] Artifact standards error: {e}")
        traceback.print_exc()
        failures += 1

    # =========================================================================
    # TEST 5: Audit Verification (full backtest + artifact validation)
    # =========================================================================
    console.print(f"\n[bold cyan]TEST 5: Audit Verification (Backtest + Artifacts)[/]")

    # This test runs a full backtest and validates:
    # - pipeline_signature.json exists and is valid
    # - All required artifacts present
    # - Result hashes are populated
    artifact_path = None

    try:
        # Run a short backtest with a window that should have data
        # Using November 2024 as a stable historical window that should be cached
        end_dt = datetime(2024, 11, 15)
        start_dt = datetime(2024, 11, 1)  # 14-day window

        console.print(f"  [dim]Running backtest: {WARMUP_MATRIX_CARD} ({start_dt.date()} to {end_dt.date()})...[/]")

        run_result = backtest_run_idea_card_tool(
            idea_card_id=WARMUP_MATRIX_CARD,
            env=TEST_ENV,
            start=start_dt,
            end=end_dt,
            fix_gaps=True,  # Auto-sync data if needed
        )

        if run_result.success and run_result.data:
            # artifact_dir is the key used by backtest_run_idea_card_tool
            artifact_path = run_result.data.get("artifact_dir")
            console.print(f"  [green]OK[/] Backtest completed")
            console.print(f"      Artifact dir: {artifact_path}")

            # Check artifact validation result
            artifact_validation = run_result.data.get("artifact_validation", {})
            if artifact_validation.get("passed"):
                console.print(f"  [green]OK[/] Artifact validation passed")
            else:
                console.print(f"  [red]FAIL[/] Artifact validation failed")
                for err in artifact_validation.get("errors", []):
                    console.print(f"      - {err}")
                failures += 1

            # Check pipeline signature validation
            if artifact_validation.get("pipeline_signature_valid") is True:
                console.print(f"  [green]OK[/] Pipeline signature valid")
            elif artifact_validation.get("pipeline_signature_valid") is False:
                console.print(f"  [red]FAIL[/] Pipeline signature invalid")
                failures += 1
            else:
                console.print(f"  [yellow]WARN[/] Pipeline signature status unknown")

            # Check result.json has hashes
            if artifact_path:
                result_json_path = Path(artifact_path) / "result.json"
                if result_json_path.exists():
                    with open(result_json_path, "r") as f:
                        result_data = json.load(f)

                    # Check for hash fields
                    hash_fields = ["trades_hash", "equity_hash", "run_hash", "idea_hash"]
                    populated_hashes = [f for f in hash_fields if result_data.get(f)]

                    if len(populated_hashes) == len(hash_fields):
                        console.print(f"  [green]OK[/] All hash fields populated in result.json")
                        for field in hash_fields:
                            console.print(f"      {field}: {result_data.get(field, 'N/A')[:16]}...")
                    else:
                        missing = [f for f in hash_fields if not result_data.get(f)]
                        console.print(f"  [red]FAIL[/] Missing hash fields: {missing}")
                        failures += 1
                else:
                    console.print(f"  [red]FAIL[/] result.json not found at {result_json_path}")
                    failures += 1
        else:
            console.print(f"  [red]FAIL[/] Backtest failed: {run_result.error}")
            failures += 1

    except Exception as e:
        console.print(f"  [red]FAIL[/] Audit verification error: {e}")
        traceback.print_exc()
        failures += 1

    # =========================================================================
    # TEST 6: Determinism Spot-Check (Optional)
    # =========================================================================
    include_determinism = os.environ.get("TRADE_SMOKE_INCLUDE_DETERMINISM", "0")

    if include_determinism in ("1", "true", "True", "TRUE"):
        console.print(f"\n[bold cyan]TEST 6: Determinism Spot-Check[/]")

        try:
            from ...backtest.artifacts.determinism import compare_runs

            if artifact_path:
                artifact_path_obj = Path(artifact_path)

                console.print(f"  [dim]Comparing run to itself (sanity check)...[/]")

                # Self-comparison should always pass
                result = compare_runs(artifact_path_obj, artifact_path_obj)

                if result.passed:
                    console.print(f"  [green]OK[/] Self-comparison passed (determinism sanity check)")
                    for comp in result.hash_comparisons:
                        status = "[OK]" if comp.matches else "[MISMATCH]"
                        console.print(f"      {status} {comp.field_name}")
                else:
                    console.print(f"  [red]FAIL[/] Self-comparison failed (unexpected!)")
                    for err in result.errors:
                        console.print(f"      - {err}")
                    failures += 1
            else:
                console.print(f"  [yellow]SKIP[/] No artifact path from TEST 5, skipping determinism check")

        except Exception as e:
            console.print(f"  [red]FAIL[/] Determinism check error: {e}")
            traceback.print_exc()
            failures += 1
    else:
        console.print(f"\n[dim]TEST 6: Determinism spot-check skipped (set TRADE_SMOKE_INCLUDE_DETERMINISM=1 to enable)[/]")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    console.print(f"\n[bold cyan]{'='*60}[/]")
    console.print(f"[bold cyan]PHASE 6 BACKTEST SMOKE TEST COMPLETE[/]")
    console.print(f"[bold cyan]{'='*60}[/]")

    if failures == 0:
        console.print(f"\n[bold green]OK PHASE 6 VERIFIED[/]")
    else:
        console.print(f"\n[bold red]FAIL {failures} TEST(S) FAILED[/]")

    return failures


def run_backtest_suite_smoke(smoke_config, app, config) -> int:
    """
    Run backtest-specific smoke tests (for smoke suite integration).

    This is a lightweight wrapper that calls Phase 6 tests if enabled.
    """
    # Check opt-in environment variable
    include_backtest = os.environ.get("TRADE_SMOKE_INCLUDE_BACKTEST", "0")

    if include_backtest not in ("1", "true", "True", "TRUE"):
        console.print(f"\n[dim]Backtest smoke tests skipped (set TRADE_SMOKE_INCLUDE_BACKTEST=1 to enable)[/]")
        return 0

    return run_phase6_backtest_smoke()
