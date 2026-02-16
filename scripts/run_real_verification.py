"""
Run the Real-Data Verification suite (60 RV plays).

Discovers plays in plays/validation/real_data/ (accumulation, markup, distribution,
markdown), runs each through CLI, optionally runs math verification, and records
results to CSV + markdown report.

Usage:
    python scripts/run_real_verification.py
    python scripts/run_real_verification.py --phase accumulation
    python scripts/run_real_verification.py --play RV_001_btc_accum_ema_zone
    python scripts/run_real_verification.py --start-from RV_030_ltc_markup_all_structures
    python scripts/run_real_verification.py --start 2025-05-01 --end 2025-08-01
    python scripts/run_real_verification.py --skip-math
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PLAYS_ROOT = ROOT / "plays" / "validation" / "real_data"
CSV_PATH = ROOT / "backtests" / "real_verification_report.csv"
REPORT_PATH = ROOT / "docs" / "REAL_VERIFICATION_REPORT.md"

PHASES = ["accumulation", "markup", "distribution", "markdown"]

PHASE_RANGES = {
    "accumulation": ("RV_001", "RV_015"),
    "markup": ("RV_016", "RV_030"),
    "distribution": ("RV_031", "RV_045"),
    "markdown": ("RV_046", "RV_060"),
}

PLAY_TIMEOUT = 600
VERIFY_TIMEOUT = 120
MAX_RETRIES = 5


# ── Discovery ─────────────────────────────────────────────────────────────────


def discover_plays(phase: str | None = None) -> list[dict]:
    """Discover all RV play files, returning list of dicts with metadata."""
    phases = [phase] if phase else PHASES
    plays: list[dict] = []
    for ph in phases:
        phase_dir = PLAYS_ROOT / ph
        if not phase_dir.exists():
            continue
        for f in sorted(phase_dir.glob("*.yml")):
            plays.append({
                "stem": f.stem,
                "path": f,
                "phase": ph,
            })
    return plays


def extract_dates_from_play(play_path: Path) -> tuple[str | None, str | None]:
    """Extract --start and --end dates from play description field."""
    with open(play_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    desc = config.get("description", "")
    m = re.search(r"--start\s+(\d{4}-\d{2}-\d{2})\s+--end\s+(\d{4}-\d{2}-\d{2})", desc)
    if m:
        return m.group(1), m.group(2)
    return None, None


def extract_symbol_from_play(play_path: Path) -> str:
    """Extract symbol from play YAML."""
    with open(play_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config.get("symbol", "BTCUSDT")


# ── Run & Verify ──────────────────────────────────────────────────────────────


def run_play(
    play_stem: str,
    start_date: str,
    end_date: str,
) -> dict:
    """Run a single play via CLI. Retries on DuckDB lock."""
    cmd = [
        sys.executable, "trade_cli.py", "backtest", "run",
        "--play", play_stem,
        "--sync",
        "--start", start_date,
        "--end", end_date,
        "--json",
    ]

    for attempt in range(MAX_RETRIES):
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=PLAY_TIMEOUT,
                cwd=str(ROOT),
            )
            elapsed = time.time() - start_time
            stdout = result.stdout
            stderr = result.stderr

            # Retry on DuckDB lock
            if result.returncode != 0 and "being used by another process" in stderr:
                if attempt < MAX_RETRIES - 1:
                    wait = 3 * (attempt + 1)
                    print(f"DB locked, retry {attempt+1}/{MAX_RETRIES} in {wait}s...", end=" ", flush=True)
                    time.sleep(wait)
                    continue

            # Parse JSON output (may have non-JSON lines before the JSON block)
            trades = 0
            pnl = 0.0
            win_rate = 0.0
            artifact_dir = ""
            if result.returncode == 0:
                try:
                    # Extract JSON from stdout (find the { ... } block)
                    json_start = stdout.find("{")
                    json_end = stdout.rfind("}") + 1
                    if json_start >= 0 and json_end > json_start:
                        json_str = stdout[json_start:json_end]
                        data = json.loads(json_str)
                        inner = data.get("data", {})
                        trades = inner.get("trades_count", 0)
                        summary = inner.get("summary", {})
                        pnl = summary.get("net_pnl_usdt", 0.0)
                        win_rate = summary.get("win_rate", 0.0)
                        artifact_dir = inner.get("artifact_dir", "")
                except (json.JSONDecodeError, AttributeError):
                    # Fallback: parse from non-JSON output
                    m = re.search(r"Trades:\s*(\d+)", stdout)
                    if m:
                        trades = int(m.group(1))
                    m = re.search(r"PnL:\s*([-\d.]+)", stdout)
                    if m:
                        pnl = float(m.group(1))

            return {
                "play": play_stem,
                "exit_code": result.returncode,
                "trades": trades,
                "pnl": pnl,
                "win_rate": win_rate,
                "elapsed_s": round(elapsed, 1),
                "status": "PASS" if result.returncode == 0 else "FAIL",
                "artifact_dir": artifact_dir,
                "error_msg": stderr[-300:] if result.returncode != 0 else "",
            }

        except subprocess.TimeoutExpired:
            return {
                "play": play_stem,
                "exit_code": -1,
                "trades": 0,
                "pnl": 0.0,
                "win_rate": 0.0,
                "elapsed_s": float(PLAY_TIMEOUT),
                "status": "TIMEOUT",
                "artifact_dir": "",
                "error_msg": f"Timed out after {PLAY_TIMEOUT}s",
            }
        except Exception as e:
            return {
                "play": play_stem,
                "exit_code": -2,
                "trades": 0,
                "pnl": 0.0,
                "win_rate": 0.0,
                "elapsed_s": 0,
                "status": "ERROR",
                "artifact_dir": "",
                "error_msg": str(e)[:300],
            }

    # All retries exhausted (DuckDB lock)
    return {
        "play": play_stem,
        "exit_code": -3,
        "trades": 0,
        "pnl": 0.0,
        "win_rate": 0.0,
        "elapsed_s": 0,
        "status": "DB_LOCKED",
        "artifact_dir": "",
        "error_msg": f"DuckDB locked after {MAX_RETRIES} retries",
    }


def run_math_verification(play_stem: str) -> dict:
    """Run verify_trade_math.py --play --skip-run on a play that already ran."""
    cmd = [
        sys.executable, str(ROOT / "scripts" / "verify_trade_math.py"),
        "--play", play_stem,
        "--skip-run",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=VERIFY_TIMEOUT,
            cwd=str(ROOT),
        )
        stdout = result.stdout
        # Parse individual check lines: "| CHECK_NAME | PASS | ..." or "| CHECK_NAME | FAIL | ..."
        passed = len(re.findall(r"\|\s*PASS\s*\|", stdout))
        failed = len(re.findall(r"\|\s*FAIL\s*\|", stdout))
        total = passed + failed
        if total > 0:
            return {
                "math_status": "PASS" if failed == 0 else "FAIL",
                "math_passed": passed,
                "math_total": total,
                "math_summary": f"{passed}/{total}",
            }
        return {
            "math_status": "PASS" if result.returncode == 0 else "FAIL",
            "math_passed": 0,
            "math_total": 0,
            "math_summary": "no-output",
        }
    except subprocess.TimeoutExpired:
        return {
            "math_status": "TIMEOUT",
            "math_passed": 0,
            "math_total": 0,
            "math_summary": "timeout",
        }
    except Exception as e:
        return {
            "math_status": "ERROR",
            "math_passed": 0,
            "math_total": 0,
            "math_summary": str(e)[:100],
        }


# ── CSV & Report ──────────────────────────────────────────────────────────────


def write_csv(results: list[dict]) -> None:
    """Write results to CSV."""
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "play", "phase", "symbol", "status", "trades", "pnl",
        "win_rate", "elapsed_s", "math_checks_passed", "math_checks_total",
        "error_msg",
    ]
    with open(CSV_PATH, "w", newline="\n", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "play": r["play"],
                "phase": r.get("phase", ""),
                "symbol": r.get("symbol", ""),
                "status": r["status"],
                "trades": r["trades"],
                "pnl": f"{r['pnl']:.2f}",
                "win_rate": f"{r['win_rate'] * 100:.1f}",
                "elapsed_s": r["elapsed_s"],
                "math_checks_passed": r.get("math_passed", ""),
                "math_checks_total": r.get("math_total", ""),
                "error_msg": r.get("error_msg", ""),
            })


def write_report(results: list[dict]) -> None:
    """Write/update the markdown report."""
    total = len(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    errored = sum(1 for r in results if r["status"] in ("FAIL", "TIMEOUT", "ERROR", "DB_LOCKED"))
    zero_trade = sum(1 for r in results if r["status"] == "PASS" and r["trades"] == 0)

    lines = [
        "# Real-Data Verification Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Plays | {total}/60 |",
        f"| Passed | {passed} |",
        f"| Failed | {errored} |",
        f"| Zero-Trade | {zero_trade} |",
        "",
    ]

    # Results by phase
    for phase in PHASES:
        phase_results = [r for r in results if r.get("phase") == phase]
        if not phase_results:
            continue
        start_num, end_num = PHASE_RANGES[phase]
        lines.append(f"### {phase.title()} ({start_num}-{end_num})")
        lines.append("")
        lines.append("| # | Play | Symbol | Status | Trades | WR | PnL | Math |")
        lines.append("|---|------|--------|--------|--------|----|-----|------|")
        for i, r in enumerate(phase_results, 1):
            wr = f"{r['win_rate'] * 100:.0f}%" if r["trades"] > 0 else "-"
            pnl_str = f"{r['pnl']:+.2f}" if r["trades"] > 0 else "-"
            math_str = r.get("math_summary", "-")
            lines.append(
                f"| {i} | {r['play']} | {r.get('symbol', '')} | {r['status']} "
                f"| {r['trades']} | {wr} | {pnl_str} | {math_str} |"
            )
        lines.append("")

    # Coverage matrix placeholder
    lines.extend([
        "## Coverage Matrix",
        "",
        "(to be filled after all plays run)",
        "",
    ])

    # Production readiness gates
    math_pass_count = sum(1 for r in results if r.get("math_status") == "PASS")
    phases_covered = sum(
        1 for p in PHASES
        if any(r.get("phase") == p and r["status"] == "PASS" for r in results)
    )
    lines.extend([
        "## Production Readiness Gates",
        "",
        "| Gate | Criterion | Status |",
        "|------|-----------|--------|",
        f"| G-RD1 | All plays run without errors | {passed}/{total} |",
        f"| G-RD2 | All plays produce trades | {total - zero_trade}/{total} |",
        f"| G-RD3 | Math verification passes | {math_pass_count}/{total} |",
        f"| G-RD4 | All 4 Wyckoff phases covered | {phases_covered}/4 |",
        "",
    ])

    # Failures section
    failures = [r for r in results if r["status"] != "PASS"]
    if failures:
        lines.append("## Failures")
        lines.append("")
        for r in failures:
            lines.append(f"- **{r['play']}** [{r['status']}]: {r.get('error_msg', '')[:200]}")
        lines.append("")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real-data verification suite")
    parser.add_argument("--phase", choices=PHASES, default=None, help="Run only one phase")
    parser.add_argument("--play", type=str, default=None, help="Run a single play by stem")
    parser.add_argument("--start-from", type=str, default=None, help="Resume from play ID")
    parser.add_argument("--start", type=str, default=None, help="Override start date for all plays")
    parser.add_argument("--end", type=str, default=None, help="Override end date for all plays")
    parser.add_argument("--skip-math", action="store_true", help="Skip math verification step")
    args = parser.parse_args()

    # Single play mode
    if args.play:
        all_plays = discover_plays()
        match = [p for p in all_plays if p["stem"] == args.play]
        if not match:
            print(f"Play not found: {args.play}")
            sys.exit(1)
        plays = match
    else:
        plays = discover_plays(args.phase)

    if not plays:
        print("No plays found.")
        sys.exit(1)

    # Apply --start-from
    if args.start_from:
        idx = next((i for i, p in enumerate(plays) if p["stem"] == args.start_from), 0)
        plays = plays[idx:]

    print(f"Running {len(plays)} real-verification plays...")
    print("=" * 80)

    results: list[dict] = []
    pass_count = 0
    fail_count = 0
    zero_trade_count = 0
    t0 = time.time()

    for i, play_info in enumerate(plays, 1):
        stem = play_info["stem"]
        phase = play_info["phase"]
        play_path = play_info["path"]

        # Extract dates (play YAML or CLI override)
        play_start, play_end = extract_dates_from_play(play_path)
        start_date = args.start or play_start
        end_date = args.end or play_end

        if not start_date or not end_date:
            print(f"[{i}/{len(plays)}] {stem} ... SKIP (no dates in play or CLI)")
            results.append({
                "play": stem, "phase": phase, "symbol": "",
                "status": "SKIP", "trades": 0, "pnl": 0.0, "win_rate": 0.0,
                "elapsed_s": 0, "error_msg": "No date window found",
            })
            continue

        symbol = extract_symbol_from_play(play_path)
        print(f"[{i}/{len(plays)}] {stem} ({symbol} {start_date}..{end_date})...", end=" ", flush=True)

        # Run backtest
        result = run_play(stem, start_date, end_date)
        result["phase"] = phase
        result["symbol"] = symbol

        # Run math verification if backtest passed and produced trades
        if result["status"] == "PASS" and result["trades"] > 0 and not args.skip_math:
            math_result = run_math_verification(stem)
            result.update(math_result)

        results.append(result)

        status = result["status"]
        trades = result["trades"]
        elapsed = result["elapsed_s"]

        if status == "PASS":
            pass_count += 1
            if trades == 0:
                zero_trade_count += 1
                print(f"WARN 0-trades ({elapsed}s)")
            else:
                math_str = result.get("math_summary", "")
                wr = f"{result['win_rate'] * 100:.0f}%"
                print(f"OK {trades}t {wr} {result['pnl']:+.2f} [{math_str}] ({elapsed}s)")
        else:
            fail_count += 1
            print(f"FAIL: {result['error_msg'][:80]}")

        # Update reports after each play (incremental progress)
        write_csv(results)
        write_report(results)

    total_elapsed = time.time() - t0

    # Final summary
    print("\n" + "=" * 80)
    print(f"SUMMARY: {len(plays)} plays ({total_elapsed:.0f}s)")
    print(f"  PASS:       {pass_count}")
    print(f"  FAIL:       {fail_count}")
    print(f"  0-trades:   {zero_trade_count}")
    print(f"  CSV:        {CSV_PATH}")
    print(f"  Report:     {REPORT_PATH}")

    if fail_count > 0:
        print("\nFAILED PLAYS:")
        for r in results:
            if r["status"] != "PASS":
                print(f"  {r['play']}: {r['status']} - {r.get('error_msg', '')[:100]}")

    if zero_trade_count > 0:
        print("\nZERO-TRADE PLAYS:")
        for r in results:
            if r["status"] == "PASS" and r["trades"] == 0:
                print(f"  {r['play']}")

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
