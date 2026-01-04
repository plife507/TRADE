"""
Forge playbook tools.

ToolResult wrappers for playbook runner operations.
"""

import traceback
from datetime import datetime
from pathlib import Path

from .shared import ToolResult
from ..utils.logger import get_logger


logger = get_logger()


# =============================================================================
# Playbook Runner Tool
# =============================================================================

def forge_run_playbook_tool(
    playbook_id: str,
    mode: str = "verify-math",
    symbol: str | None = None,
    start: str | None = None,
    end: str | None = None,
    playbooks_dir: str | None = None,
    plays_dir: str | None = None,
    trace_hashes: bool = True,
) -> ToolResult:
    """
    Run all plays in a playbook with the specified mode.

    Modes:
    - verify-math: Run audits only (default) - validates config + registry
    - sequential: Run backtests one-by-one - produces run_hash per play
    - compare: Compare metrics side-by-side - shows hash diffs
    - aggregate: Aggregate into system metrics - composite hash

    Args:
        playbook_id: ID of the playbook to run (e.g., "trend_following")
        mode: Execution mode (default: "verify-math")
        symbol: Symbol override for all plays (optional)
        start: Start date for backtests in YYYY-MM-DD format (optional)
        end: End date for backtests in YYYY-MM-DD format (optional)
        playbooks_dir: Directory containing playbook configs
        plays_dir: Directory containing play configs
        trace_hashes: Enable hash tracing (default: True)

    Returns:
        ToolResult with playbook run results including hash summary
    """
    try:
        from ..forge.playbooks import run_playbook, RunMode

        # Convert string dates to datetime
        start_dt = None
        end_dt = None
        if start:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
        if end:
            end_dt = datetime.strptime(end, "%Y-%m-%d")

        # Convert paths
        pb_dir = Path(playbooks_dir) if playbooks_dir else None
        pl_dir = Path(plays_dir) if plays_dir else None

        # Run playbook
        result = run_playbook(
            playbook_id=playbook_id,
            mode=mode,
            symbol=symbol,
            start=start_dt,
            end=end_dt,
            playbooks_dir=pb_dir,
            plays_dir=pl_dir,
            trace_hashes=trace_hashes,
        )

        if result.overall_success:
            return ToolResult(
                success=True,
                message=(
                    f"Playbook '{playbook_id}' [{mode}] PASSED: "
                    f"{result.passed_count}/{len(result.plays_run)} plays "
                    f"({result.total_duration_seconds:.1f}s)"
                ),
                data=result.to_dict(),
            )
        else:
            # Find first failed play for error message
            failed = [p for p in result.plays_run if not p.success]
            first_failure = failed[0] if failed else None
            error_detail = f" - First failure: {first_failure.play_id}: {first_failure.error}" if first_failure else ""

            return ToolResult(
                success=False,
                error=(
                    f"Playbook '{playbook_id}' [{mode}] FAILED: "
                    f"{result.failed_count} play(s) failed{error_detail}"
                ),
                data=result.to_dict(),
            )

    except Exception as e:
        logger.error(f"Playbook run failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Playbook run error: {e}",
        )


# =============================================================================
# List Playbooks Tool
# =============================================================================

def forge_list_playbooks_tool(
    playbooks_dir: str | None = None,
) -> ToolResult:
    """
    List all available playbooks.

    Args:
        playbooks_dir: Directory containing playbook configs

    Returns:
        ToolResult with list of playbook IDs
    """
    try:
        from ..forge.playbooks import list_playbooks

        pb_dir = Path(playbooks_dir) if playbooks_dir else None
        playbooks = list_playbooks(pb_dir)

        return ToolResult(
            success=True,
            message=f"Found {len(playbooks)} playbook(s)",
            data={
                "playbooks": playbooks,
                "count": len(playbooks),
            },
        )

    except Exception as e:
        logger.error(f"List playbooks failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"List playbooks error: {e}",
        )


# =============================================================================
# Get Playbook Info Tool
# =============================================================================

def forge_get_playbook_tool(
    playbook_id: str,
    playbooks_dir: str | None = None,
) -> ToolResult:
    """
    Get details about a specific playbook.

    Args:
        playbook_id: ID of the playbook to get info for
        playbooks_dir: Directory containing playbook configs

    Returns:
        ToolResult with playbook details
    """
    try:
        from ..forge.playbooks import load_playbook

        pb_dir = Path(playbooks_dir) if playbooks_dir else None
        playbook = load_playbook(playbook_id, pb_dir)

        return ToolResult(
            success=True,
            message=f"Playbook '{playbook_id}' loaded with {len(playbook.plays)} plays",
            data={
                "id": playbook.id,
                "version": playbook.version,
                "name": playbook.name,
                "description": playbook.description,
                "tags": list(playbook.tags),
                "plays": [e.to_dict() for e in playbook.plays],
                "enabled_plays": [e.play_id for e in playbook.get_enabled_plays()],
            },
        )

    except Exception as e:
        logger.error(f"Get playbook failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Get playbook error: {e}",
        )
