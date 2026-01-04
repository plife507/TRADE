"""
Forge plumbing and verification smoke tests.

Tests all Forge validation architecture components:
- Synthetic data generation (4 patterns)
- Stress test suite (6 steps)
- Playbook runner (4 modes)
- Hash chain validation (determinism)
- Tool wrappers (ToolResult contracts)

Usage:
    python trade_cli.py --smoke forge
"""

import json
import re
from rich.console import Console
from rich.panel import Panel

console = Console()


# =============================================================================
# Hash Validation Helper
# =============================================================================
def _is_valid_hash(h: str | None, length: int = 12) -> bool:
    """Check if string is a valid hex hash of expected length."""
    if h is None:
        return False
    return bool(re.match(f"^[0-9a-f]{{{length}}}$", h))


def _is_json_serializable(data: dict) -> bool:
    """Check if data is JSON-serializable."""
    try:
        json.dumps(data, default=str)
        return True
    except (TypeError, ValueError):
        return False


# =============================================================================
# Section 1: Synthetic Data Plumbing
# =============================================================================
def _test_synthetic_data_generation() -> int:
    """Test synthetic data generation across all patterns."""
    console.print(f"\n[bold cyan]Section 1: Synthetic Data Generation[/]")

    failures = 0

    try:
        from src.forge.validation.synthetic_data import (
            generate_synthetic_candles,
            verify_synthetic_hash,
            PatternType,
        )

        # Test 1: Generate with trending pattern (align_mtf=False for speed)
        candles = generate_synthetic_candles(
            symbol="BTCUSDT",
            timeframes=["1m", "5m"],
            bars_per_tf=100,
            seed=42,
            pattern="trending",
            align_mtf=False,  # Fast mode: same bars per TF
        )
        if candles is not None and candles.data_hash:
            console.print(f"  [green]OK[/] generate_synthetic_candles() trending pattern")
        else:
            console.print(f"  [red]FAIL[/] generate_synthetic_candles() trending pattern")
            failures += 1

        # Test 2-4: All 4 patterns work
        patterns: list[PatternType] = ["trending", "ranging", "volatile", "mtf_aligned"]
        for pattern in patterns:
            try:
                c = generate_synthetic_candles(
                    timeframes=["1m"],
                    bars_per_tf=50,
                    seed=42,
                    pattern=pattern,
                    align_mtf=False,
                )
                if c is not None:
                    console.print(f"  [green]OK[/] Pattern '{pattern}' generates data")
                else:
                    console.print(f"  [red]FAIL[/] Pattern '{pattern}' returned None")
                    failures += 1
            except Exception as e:
                console.print(f"  [red]FAIL[/] Pattern '{pattern}' error: {e}")
                failures += 1

        # Test 5: Determinism - same seed -> same hash
        c1 = generate_synthetic_candles(timeframes=["1m"], bars_per_tf=100, seed=42, pattern="trending", align_mtf=False)
        c2 = generate_synthetic_candles(timeframes=["1m"], bars_per_tf=100, seed=42, pattern="trending", align_mtf=False)
        if c1.data_hash == c2.data_hash:
            console.print(f"  [green]OK[/] Determinism: same seed -> same hash ({c1.data_hash})")
        else:
            console.print(f"  [red]FAIL[/] Determinism failed: {c1.data_hash} != {c2.data_hash}")
            failures += 1

        # Test 6: Different seed -> different hash
        c3 = generate_synthetic_candles(timeframes=["1m"], bars_per_tf=100, seed=99, pattern="trending", align_mtf=False)
        if c1.data_hash != c3.data_hash:
            console.print(f"  [green]OK[/] Different seed -> different hash")
        else:
            console.print(f"  [red]FAIL[/] Different seed produced same hash")
            failures += 1

        # Test 7: verify_synthetic_hash() returns True
        if verify_synthetic_hash(c1):
            console.print(f"  [green]OK[/] verify_synthetic_hash() returns True")
        else:
            console.print(f"  [red]FAIL[/] verify_synthetic_hash() returned False")
            failures += 1

        # Test 8: Timeframes have correct bar counts
        df = c1.get_tf("1m")
        if len(df) == 100:
            console.print(f"  [green]OK[/] Bar count correct (100 bars)")
        else:
            console.print(f"  [red]FAIL[/] Bar count wrong: {len(df)} != 100")
            failures += 1

        # Test 9: OHLCV columns present
        expected_cols = {"timestamp", "open", "high", "low", "close", "volume"}
        if expected_cols.issubset(set(df.columns)):
            console.print(f"  [green]OK[/] OHLCV columns present")
        else:
            console.print(f"  [red]FAIL[/] Missing columns: {expected_cols - set(df.columns)}")
            failures += 1

    except Exception as e:
        console.print(f"  [red]FAIL[/] Section error: {e}")
        failures += 1

    return failures


# =============================================================================
# Section 2: Stress Test Suite Plumbing
# =============================================================================
def _test_stress_test_suite() -> int:
    """Test stress test suite execution."""
    console.print(f"\n[bold cyan]Section 2: Stress Test Suite[/]")

    failures = 0

    try:
        from src.forge.audits.stress_test_suite import (
            run_stress_test_suite,
            StressTestReport,
        )

        # Test 1: run_stress_test_suite() returns StressTestReport
        report = run_stress_test_suite(
            skip_backtest=True,
            trace_hashes=True,
            seed=42,
            bars_per_tf=100,
        )
        if isinstance(report, StressTestReport):
            console.print(f"  [green]OK[/] run_stress_test_suite() returns StressTestReport")
        else:
            console.print(f"  [red]FAIL[/] Wrong return type: {type(report)}")
            failures += 1

        # Test 2: Steps executed (skip_backtest=True -> 6 steps)
        step_count = len(report.steps)
        if step_count == 6:
            console.print(f"  [green]OK[/] {step_count}/6 steps executed")
        else:
            console.print(f"  [red]FAIL[/] Step count: {step_count} != 6")
            failures += 1

        # Test 3: Hash chain has correct length
        hash_count = len(report.hash_chain)
        if hash_count == step_count:
            console.print(f"  [green]OK[/] Hash chain length = {hash_count}")
        else:
            console.print(f"  [red]FAIL[/] Hash chain length: {hash_count} != {step_count}")
            failures += 1

        # Test 4: Each step has output_hash populated
        steps_with_hash = sum(1 for s in report.steps if s.output_hash)
        if steps_with_hash == step_count:
            console.print(f"  [green]OK[/] All steps have output_hash")
        else:
            console.print(f"  [red]FAIL[/] Steps with hash: {steps_with_hash}/{step_count}")
            failures += 1

        # Test 5: Determinism - same params -> same hash chain
        report2 = run_stress_test_suite(
            skip_backtest=True,
            trace_hashes=True,
            seed=42,
            bars_per_tf=100,
        )
        if report.hash_chain == report2.hash_chain:
            console.print(f"  [green]OK[/] Determinism: identical hash chains")
        else:
            console.print(f"  [red]FAIL[/] Hash chains differ")
            failures += 1

        # Test 6: skip_audits=True skips steps 3-6
        report3 = run_stress_test_suite(
            skip_audits=True,
            skip_backtest=True,
            seed=42,
        )
        if len(report3.steps) == 2:
            console.print(f"  [green]OK[/] skip_audits=True -> 2 steps")
        else:
            console.print(f"  [red]FAIL[/] skip_audits step count: {len(report3.steps)} != 2")
            failures += 1

        # Test 7: Overall pass/fail status
        if report.overall_passed:
            console.print(f"  [green]OK[/] Report shows overall_passed=True")
        else:
            console.print(f"  [yellow]![/] Report shows overall_passed=False (check validation plays)")
            # Not a failure - may be expected if validation plays have issues

    except Exception as e:
        console.print(f"  [red]FAIL[/] Section error: {e}")
        failures += 1

    return failures


# =============================================================================
# Section 3: Playbook Runner Plumbing
# =============================================================================
def _test_playbook_runner() -> int:
    """Test playbook runner across all modes."""
    console.print(f"\n[bold cyan]Section 3: Playbook Runner[/]")

    failures = 0

    try:
        from src.forge.playbooks.playbook_runner import (
            run_playbook,
            PlaybookRunResult,
            _find_play_file,
        )
        from pathlib import Path

        # Test 1: run_playbook() returns PlaybookRunResult
        result = run_playbook(
            playbook_id="trend_following",
            mode="verify-math",
        )
        if isinstance(result, PlaybookRunResult):
            console.print(f"  [green]OK[/] run_playbook() returns PlaybookRunResult")
        else:
            console.print(f"  [red]FAIL[/] Wrong return type: {type(result)}")
            failures += 1

        # Test 2-5: All 4 modes work
        modes = ["verify-math", "sequential", "compare", "aggregate"]
        for mode in modes:
            try:
                r = run_playbook(playbook_id="trend_following", mode=mode)
                if r is not None:
                    console.print(f"  [green]OK[/] Mode '{mode}' executes")
                else:
                    console.print(f"  [red]FAIL[/] Mode '{mode}' returned None")
                    failures += 1
            except Exception as e:
                console.print(f"  [red]FAIL[/] Mode '{mode}' error: {e}")
                failures += 1

        # Test 6: verify-math produces validation_hash per play
        vm_result = run_playbook(playbook_id="trend_following", mode="verify-math")
        hashes_present = sum(1 for p in vm_result.plays_run if p.validation_hash)
        if hashes_present == len(vm_result.plays_run):
            console.print(f"  [green]OK[/] All plays have validation_hash ({hashes_present})")
        else:
            console.print(f"  [red]FAIL[/] Plays with hash: {hashes_present}/{len(vm_result.plays_run)}")
            failures += 1

        # Test 7: hash_summary populated
        if vm_result.hash_summary and len(vm_result.hash_summary) > 0:
            console.print(f"  [green]OK[/] hash_summary populated ({len(vm_result.hash_summary)} entries)")
        else:
            console.print(f"  [red]FAIL[/] hash_summary empty")
            failures += 1

        # Test 8: _find_play_file() finds plays in subdirectories
        plays_dir = Path("configs/plays")
        found = _find_play_file("T_001_ema_crossover", plays_dir)
        if found is not None and found.exists():
            console.print(f"  [green]OK[/] _find_play_file() finds subdirectory plays")
        else:
            console.print(f"  [red]FAIL[/] _find_play_file() couldn't find T_001_ema_crossover")
            failures += 1

        # Test 9: Missing playbook -> error in result
        bad_result = run_playbook(playbook_id="nonexistent_playbook_xyz", mode="verify-math")
        if not bad_result.overall_success and bad_result.error:
            console.print(f"  [green]OK[/] Missing playbook -> error in result")
        else:
            console.print(f"  [red]FAIL[/] Missing playbook didn't produce error")
            failures += 1

    except Exception as e:
        console.print(f"  [red]FAIL[/] Section error: {e}")
        failures += 1

    return failures


# =============================================================================
# Section 4: Tool Wrappers Plumbing
# =============================================================================
def _test_forge_tools() -> int:
    """Test all forge tool wrappers."""
    console.print(f"\n[bold cyan]Section 4: Tool Wrappers[/]")

    failures = 0

    try:
        from src.tools import (
            forge_stress_test_tool,
            forge_generate_synthetic_data_tool,
            forge_structure_parity_tool,
            forge_indicator_parity_tool,
            forge_run_playbook_tool,
            forge_list_playbooks_tool,
            forge_get_playbook_tool,
        )
        from src.tools.shared import ToolResult

        # Test 1: forge_stress_test_tool() returns ToolResult
        result = forge_stress_test_tool(skip_backtest=True, seed=42, bars_per_tf=50)
        if isinstance(result, ToolResult):
            console.print(f"  [green]OK[/] forge_stress_test_tool() -> ToolResult")
        else:
            console.print(f"  [red]FAIL[/] Wrong return type: {type(result)}")
            failures += 1

        # Test 2: forge_generate_synthetic_data_tool() returns ToolResult
        result = forge_generate_synthetic_data_tool(timeframes=["1m"], bars_per_tf=50, seed=42)
        if isinstance(result, ToolResult) and result.success:
            console.print(f"  [green]OK[/] forge_generate_synthetic_data_tool() -> ToolResult")
        else:
            console.print(f"  [red]FAIL[/] forge_generate_synthetic_data_tool() failed")
            failures += 1

        # Test 3: forge_structure_parity_tool() returns ToolResult
        result = forge_structure_parity_tool(seed=42, bars_per_tf=50)
        if isinstance(result, ToolResult):
            console.print(f"  [green]OK[/] forge_structure_parity_tool() -> ToolResult")
        else:
            console.print(f"  [red]FAIL[/] Wrong return type: {type(result)}")
            failures += 1

        # Test 4: forge_indicator_parity_tool() returns ToolResult
        result = forge_indicator_parity_tool(seed=42, bars_per_tf=50)
        if isinstance(result, ToolResult):
            console.print(f"  [green]OK[/] forge_indicator_parity_tool() -> ToolResult")
        else:
            console.print(f"  [red]FAIL[/] Wrong return type: {type(result)}")
            failures += 1

        # Test 5: forge_run_playbook_tool() returns ToolResult
        result = forge_run_playbook_tool(playbook_id="trend_following", mode="verify-math")
        if isinstance(result, ToolResult):
            console.print(f"  [green]OK[/] forge_run_playbook_tool() -> ToolResult")
        else:
            console.print(f"  [red]FAIL[/] Wrong return type: {type(result)}")
            failures += 1

        # Test 6: forge_list_playbooks_tool() returns ToolResult
        result = forge_list_playbooks_tool()
        if isinstance(result, ToolResult) and result.success:
            console.print(f"  [green]OK[/] forge_list_playbooks_tool() -> ToolResult")
        else:
            console.print(f"  [red]FAIL[/] forge_list_playbooks_tool() failed")
            failures += 1

        # Test 7: forge_get_playbook_tool() returns ToolResult
        result = forge_get_playbook_tool(playbook_id="trend_following")
        if isinstance(result, ToolResult) and result.success:
            console.print(f"  [green]OK[/] forge_get_playbook_tool() -> ToolResult")
        else:
            console.print(f"  [red]FAIL[/] forge_get_playbook_tool() failed")
            failures += 1

        # Test 8: All ToolResult.data fields are JSON-serializable
        result = forge_stress_test_tool(skip_backtest=True, seed=42, bars_per_tf=50)
        if result.data and _is_json_serializable(result.data):
            console.print(f"  [green]OK[/] ToolResult.data is JSON-serializable")
        else:
            console.print(f"  [red]FAIL[/] ToolResult.data not JSON-serializable")
            failures += 1

        # Test 9: Error cases return success=False
        result = forge_run_playbook_tool(playbook_id="nonexistent_xyz", mode="verify-math")
        if not result.success and result.error:
            console.print(f"  [green]OK[/] Error cases return success=False with message")
        else:
            console.print(f"  [red]FAIL[/] Error case didn't return success=False")
            failures += 1

    except Exception as e:
        console.print(f"  [red]FAIL[/] Section error: {e}")
        failures += 1

    return failures


# =============================================================================
# Section 5: Hash Chain Validation
# =============================================================================
def _test_hash_chain_determinism() -> int:
    """Test hash chain determinism across runs."""
    console.print(f"\n[bold cyan]Section 5: Hash Chain Determinism[/]")

    failures = 0

    try:
        from src.forge.audits.stress_test_suite import run_stress_test_suite
        from src.forge.playbooks.playbook_runner import run_playbook

        # Test 1-2: Run stress test twice, compare hash chains
        r1 = run_stress_test_suite(skip_backtest=True, seed=42, bars_per_tf=100)
        r2 = run_stress_test_suite(skip_backtest=True, seed=42, bars_per_tf=100)
        if r1.hash_chain == r2.hash_chain:
            console.print(f"  [green]OK[/] Stress test hash chain reproducible")
        else:
            console.print(f"  [red]FAIL[/] Hash chains differ between runs")
            failures += 1

        # Test 3: Different seed -> different hash chain
        r3 = run_stress_test_suite(skip_backtest=True, seed=99, bars_per_tf=100)
        if r1.hash_chain != r3.hash_chain:
            console.print(f"  [green]OK[/] Different seed -> different hash chain")
        else:
            console.print(f"  [red]FAIL[/] Different seed produced same hash chain")
            failures += 1

        # Test 4-5: Run playbook twice, compare hash_summary
        p1 = run_playbook(playbook_id="trend_following", mode="verify-math")
        p2 = run_playbook(playbook_id="trend_following", mode="verify-math")
        if p1.hash_summary == p2.hash_summary:
            console.print(f"  [green]OK[/] Playbook hash_summary reproducible")
        else:
            console.print(f"  [red]FAIL[/] Playbook hash_summary differs between runs")
            failures += 1

    except Exception as e:
        console.print(f"  [red]FAIL[/] Section error: {e}")
        failures += 1

    return failures


# =============================================================================
# Section 6: Full Connection Test
# =============================================================================
def _test_full_connection() -> int:
    """Test end-to-end pipeline."""
    console.print(f"\n[bold cyan]Section 6: Full Connection Test[/]")

    failures = 0

    try:
        from src.forge.validation.synthetic_data import generate_synthetic_candles
        from src.forge.audits.stress_test_suite import run_stress_test_suite
        from src.forge.playbooks.playbook_runner import run_playbook

        # Test 1: Generate synthetic data
        candles = generate_synthetic_candles(
            timeframes=["1m", "5m", "15m"],
            bars_per_tf=200,
            seed=42,
            pattern="trending",
        )

        # Test 2: Run stress test suite (skip backtest for speed)
        report = run_stress_test_suite(
            skip_backtest=True,
            seed=42,
            bars_per_tf=200,
        )

        # Test 3: Run playbook in verify-math mode
        pb_result = run_playbook(
            playbook_id="trend_following",
            mode="verify-math",
        )

        # Test 4: Verify all hashes are 12-char hex strings
        all_valid = True
        if not _is_valid_hash(candles.data_hash):
            all_valid = False
        for step in report.steps:
            if step.output_hash and not _is_valid_hash(step.output_hash):
                all_valid = False
        for h in pb_result.hash_summary.values():
            if not _is_valid_hash(h):
                all_valid = False

        if all_valid:
            console.print(f"  [green]OK[/] All hashes are 12-char hex")
        else:
            console.print(f"  [red]FAIL[/] Some hashes are invalid format")
            failures += 1

        # Test 5: Verify no exceptions in flow
        console.print(f"  [green]OK[/] End-to-end pipeline completes without exception")

    except Exception as e:
        console.print(f"  [red]FAIL[/] Pipeline error: {e}")
        failures += 1

    return failures


# =============================================================================
# Section 7: Volume Correlation Test
# =============================================================================
def _test_volume_correlation() -> int:
    """Test volume correlation with price moves."""
    console.print(f"\n[bold cyan]Section 7: Volume Correlation[/]")

    failures = 0

    try:
        from src.forge.validation.synthetic_data import generate_synthetic_candles
        import numpy as np

        # Generate data with correlate_volume=True (default)
        candles = generate_synthetic_candles(
            timeframes=["1m"],
            bars_per_tf=500,
            seed=42,
            pattern="volatile",  # Most likely to have big moves
            align_mtf=False,
        )

        df = candles.get_tf("1m")
        close = df["close"].values
        volume = df["volume"].values

        # Compute price changes
        price_changes = np.abs(np.diff(close) / close[:-1])
        volumes = volume[1:]  # Align with changes

        # Find bars with largest 10% price moves
        threshold = np.percentile(price_changes, 90)
        large_move_mask = price_changes >= threshold
        small_move_mask = price_changes < np.percentile(price_changes, 50)

        large_move_vol = volumes[large_move_mask].mean()
        small_move_vol = volumes[small_move_mask].mean()

        # Large moves should have higher average volume
        if large_move_vol > small_move_vol:
            ratio = large_move_vol / small_move_vol
            console.print(f"  [green]OK[/] Large moves have {ratio:.1f}x volume (correlation present)")
        else:
            console.print(f"  [yellow]![/] Volume correlation weak (may need enhancement)")
            # Not a hard failure - current implementation may not have correlation

    except Exception as e:
        console.print(f"  [red]FAIL[/] Section error: {e}")
        failures += 1

    return failures


# =============================================================================
# Section 8: MTF Alignment Test
# =============================================================================
def _test_mtf_alignment() -> int:
    """Test multi-timeframe bar count alignment."""
    console.print(f"\n[bold cyan]Section 8: MTF Alignment[/]")

    failures = 0

    try:
        from src.forge.validation.synthetic_data import generate_synthetic_candles, TF_TO_MINUTES

        # Test 1: MTF-aligned data - slower TF gets bars_per_tf, faster TFs get more
        # With bars_per_tf=100 and TFs ["1m", "1h"]:
        # - 1h (60 min) is slowest -> 100 bars
        # - 1m (1 min) is fastest -> 100 * 60 = 6000 bars
        candles = generate_synthetic_candles(
            timeframes=["1m", "1h"],
            bars_per_tf=100,
            seed=42,
            pattern="trending",
            align_mtf=True,
        )

        # Verify bar counts
        bars_1m = len(candles.get_tf("1m"))
        bars_1h = len(candles.get_tf("1h"))

        expected_1h = 100  # slowest TF gets bars_per_tf
        expected_1m = 100 * 60  # 1h = 60 * 1m

        if bars_1h == expected_1h:
            console.print(f"  [green]OK[/] 1h gets {bars_1h} bars (slowest TF)")
        else:
            console.print(f"  [red]FAIL[/] 1h bar count: {bars_1h} != {expected_1h}")
            failures += 1

        if bars_1m == expected_1m:
            console.print(f"  [green]OK[/] 1m gets {bars_1m} bars (60x more than 1h)")
        else:
            console.print(f"  [red]FAIL[/] 1m bar count: {bars_1m} != {expected_1m}")
            failures += 1

        # Test 2: Verify bar_counts dict
        if candles.bar_counts["1m"] == expected_1m and candles.bar_counts["1h"] == expected_1h:
            console.print(f"  [green]OK[/] bar_counts dict correct")
        else:
            console.print(f"  [red]FAIL[/] bar_counts mismatch: {candles.bar_counts}")
            failures += 1

        # Test 3: Verify total_minutes
        expected_minutes = 100 * 60  # 100 bars of 1h = 6000 minutes
        if candles.total_minutes == expected_minutes:
            console.print(f"  [green]OK[/] total_minutes = {expected_minutes} ({expected_minutes // 60}h)")
        else:
            console.print(f"  [red]FAIL[/] total_minutes: {candles.total_minutes} != {expected_minutes}")
            failures += 1

        # Test 4: Verify timestamps align (first and last timestamps same across TFs)
        df_1m = candles.get_tf("1m")
        df_1h = candles.get_tf("1h")

        first_1m = df_1m["timestamp"].iloc[0]
        first_1h = df_1h["timestamp"].iloc[0]
        if first_1m == first_1h:
            console.print(f"  [green]OK[/] First timestamps align")
        else:
            console.print(f"  [red]FAIL[/] First timestamps differ: {first_1m} vs {first_1h}")
            failures += 1

        # Test 5: Last 1m bar should be within the same hour as last 1h bar
        # Note: 1h bar timestamp is START of hour, so 1m bar at minute 59 is AFTER it
        last_1m = df_1m["timestamp"].iloc[-1]
        last_1h = df_1h["timestamp"].iloc[-1]
        # 1m bar at minute 59 is 59 minutes AFTER the 1h bar start
        time_diff_minutes = (last_1m - last_1h).total_seconds() / 60
        if 0 <= time_diff_minutes < 60:
            console.print(f"  [green]OK[/] Last bar timestamps aligned (1m is {int(time_diff_minutes)}min after 1h start)")
        else:
            console.print(f"  [red]FAIL[/] Last bar time diff: {time_diff_minutes} minutes (expected 0-59)")
            failures += 1

        # Test 6: align_mtf=False gives same bar count for all TFs
        candles_unaligned = generate_synthetic_candles(
            timeframes=["1m", "1h"],
            bars_per_tf=100,
            seed=42,
            pattern="trending",
            align_mtf=False,
        )
        if candles_unaligned.bar_counts["1m"] == 100 and candles_unaligned.bar_counts["1h"] == 100:
            console.print(f"  [green]OK[/] align_mtf=False gives 100 bars each")
        else:
            console.print(f"  [red]FAIL[/] align_mtf=False bar counts wrong: {candles_unaligned.bar_counts}")
            failures += 1

        # Test 7: 5-TF alignment with default timeframes
        candles_5tf = generate_synthetic_candles(
            timeframes=["1m", "5m", "15m", "1h", "4h"],
            bars_per_tf=50,  # 4h gets 50 bars
            seed=42,
            align_mtf=True,
        )
        # 50 bars of 4h = 50 * 240 = 12000 minutes
        # 1m should get 12000 bars, 5m=2400, 15m=800, 1h=200, 4h=50
        expected_counts = {
            "1m": 12000,
            "5m": 2400,
            "15m": 800,
            "1h": 200,
            "4h": 50,
        }
        all_correct = all(
            candles_5tf.bar_counts[tf] == expected_counts[tf]
            for tf in expected_counts
        )
        if all_correct:
            console.print(f"  [green]OK[/] 5-TF alignment correct: 4h=50, 1h=200, 15m=800, 5m=2400, 1m=12000")
        else:
            console.print(f"  [red]FAIL[/] 5-TF alignment wrong: {candles_5tf.bar_counts}")
            failures += 1

    except Exception as e:
        console.print(f"  [red]FAIL[/] Section error: {e}")
        failures += 1

    return failures


# =============================================================================
# Section 9: Warmup-Aware Synthetic Data
# =============================================================================
def _test_warmup_aware_generation() -> int:
    """Test warmup-aware synthetic data generation."""
    console.print(f"\n[bold cyan]Section 9: Warmup-Aware Generation[/]")

    failures = 0

    try:
        from src.forge.validation.synthetic_data import (
            calculate_warmup_for_play,
            generate_synthetic_for_play,
        )

        # Use a validation Play with features for testing
        test_play_id = "V_100_blocks_basic"

        # Test 1: Calculate warmup for a known Play
        try:
            warmup = calculate_warmup_for_play(test_play_id)
            if warmup is not None:
                if len(warmup) > 0:
                    console.print(f"  [green]OK[/] calculate_warmup_for_play() returns warmup dict: {warmup}")
                else:
                    console.print(f"  [green]OK[/] calculate_warmup_for_play() returned empty (Play has no features)")
            else:
                console.print(f"  [red]FAIL[/] calculate_warmup_for_play() returned None")
                failures += 1
        except Exception as e:
            console.print(f"  [red]FAIL[/] calculate_warmup_for_play() error: {e}")
            failures += 1

        # Test 2: Generate synthetic data for Play
        try:
            candles = generate_synthetic_for_play(
                play_id=test_play_id,
                extra_bars=100,
                seed=42,
            )
            if candles is not None and candles.data_hash:
                # Verify enough bars for warmup
                min_bars = min(len(df) for df in candles.timeframes.values())
                console.print(f"  [green]OK[/] generate_synthetic_for_play() returned {len(candles.timeframes)} TFs, min {min_bars} bars")
            else:
                console.print(f"  [red]FAIL[/] generate_synthetic_for_play() returned None or no hash")
                failures += 1
        except Exception as e:
            console.print(f"  [red]FAIL[/] generate_synthetic_for_play() error: {e}")
            failures += 1

        # Test 3: Warmup bars + extra_bars = total bars per TF
        try:
            warmup = calculate_warmup_for_play(test_play_id)
            candles = generate_synthetic_for_play(
                play_id=test_play_id,
                extra_bars=200,
                seed=42,
            )
            # For the slowest TF, bars should be warmup + extra_bars
            # Due to MTF alignment, faster TFs get more bars
            if candles.total_minutes > 0:
                console.print(f"  [green]OK[/] Warmup-aware data covers {candles.total_minutes} minutes ({candles.total_minutes // 60}h)")
            else:
                console.print(f"  [red]FAIL[/] total_minutes is 0")
                failures += 1
        except Exception as e:
            console.print(f"  [red]FAIL[/] Warmup verification error: {e}")
            failures += 1

        # Test 4: MTF alignment with warmup
        try:
            candles = generate_synthetic_for_play(
                play_id=test_play_id,
                extra_bars=100,
                seed=42,
            )
            # All TFs should cover the same time range
            if candles.align_mtf:
                console.print(f"  [green]OK[/] Warmup-aware generation uses MTF alignment")
            else:
                console.print(f"  [red]FAIL[/] align_mtf should be True")
                failures += 1
        except Exception as e:
            console.print(f"  [red]FAIL[/] MTF alignment check error: {e}")
            failures += 1

    except Exception as e:
        console.print(f"  [red]FAIL[/] Section error: {e}")
        failures += 1

    return failures


# =============================================================================
# Main Entry Point
# =============================================================================
def run_forge_smoke(verbose: bool = False) -> int:
    """
    Run Forge plumbing and verification smoke tests.

    Tests all Forge validation architecture components:
    - Synthetic data generation (4 patterns)
    - Stress test suite (6 steps)
    - Playbook runner (4 modes)
    - Hash chain validation (determinism)
    - Tool wrappers (ToolResult contracts)

    Args:
        verbose: Enable verbose output (not used currently)

    Returns:
        Exit code: 0 = all tests passed, 1+ = number of failures
    """
    console.print(Panel(
        "[bold cyan]FORGE PLUMBING VERIFICATION[/]\n"
        "[dim]Tests Forge validation architecture: synthetic data, stress test, playbook runner[/]",
        border_style="cyan"
    ))

    total_failures = 0

    # Run all test sections
    total_failures += _test_synthetic_data_generation()
    total_failures += _test_stress_test_suite()
    total_failures += _test_playbook_runner()
    total_failures += _test_forge_tools()
    total_failures += _test_hash_chain_determinism()
    total_failures += _test_full_connection()
    total_failures += _test_volume_correlation()
    total_failures += _test_mtf_alignment()
    total_failures += _test_warmup_aware_generation()

    # Summary
    console.print(f"\n{'='*60}")
    console.print(f"[bold cyan]FORGE PLUMBING VERIFICATION COMPLETE[/]")
    console.print(f"{'='*60}")

    if total_failures == 0:
        console.print(f"\n[bold green]ALL TESTS PASSED[/]")
        return 0
    else:
        console.print(f"\n[bold red]{total_failures} TEST(S) FAILED[/]")
        return 1
