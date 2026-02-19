"""
Play normalization tools (build-time validation).

Extracted from backtest_play_tools.py — normalize single and batch Play YAML files.
"""

import traceback
from pathlib import Path

from .shared import ToolResult
from ..backtest.play import load_play, list_plays
from ..utils.logger import get_logger


logger = get_logger()


# =============================================================================
# Play Normalization (build-time validation)
# =============================================================================

def backtest_play_normalize_tool(
    play_id: str,
    plays_dir: Path | None = None,
    write_in_place: bool = False,
) -> ToolResult:
    """
    Normalize and validate an Play YAML at build time.

    This command validates:
    - All indicator_types are supported
    - All params are accepted by each indicator
    - All signal_rules/risk_model references use expanded keys (not base keys)

    If validation passes and write_in_place=True, writes the normalized YAML
    with auto-generated required_indicators.

    Agent Rule:
        Agents may only generate Plays through this command and must
        refuse to write YAML if normalization fails.

    Args:
        play_id: Play identifier
        plays_dir: Override Play directory
        write_in_place: If True, write normalized YAML back to file

    Returns:
        ToolResult with validation results
    """
    import yaml
    from ..backtest.play import PLAYS_DIR
    from ..backtest.play_yaml_builder import (
        normalize_play_yaml,
        format_validation_errors,
    )

    try:
        # Resolve path - search in base dir and subdirectories
        search_dir = plays_dir or PLAYS_DIR
        search_paths = [
            search_dir,
            search_dir / "_validation",
            search_dir / "_stress_test",
            search_dir / "strategies",
        ]
        yaml_path = None

        for search_path in search_paths:
            for ext in (".yml", ".yaml"):
                path = search_path / f"{play_id}{ext}"
                if path.exists():
                    yaml_path = path
                    break
            if yaml_path:
                break

        if yaml_path is None:
            cards = list_plays(base_dir=plays_dir)
            return ToolResult(
                success=False,
                error=f"Play '{play_id}' not found in {search_dir}",
                data={"available_plays": cards},
            )

        # Load raw YAML
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not raw:
            return ToolResult(
                success=False,
                error=f"Empty or invalid YAML in {yaml_path}",
            )

        # Phase 1: Unified validation (dict-level checks + Play.from_dict())
        from ..forge.validation.play_validator import validate_play_unified
        unified_result = validate_play_unified(raw)

        if not unified_result.is_valid:
            error_details = format_validation_errors(unified_result.errors)
            return ToolResult(
                success=False,
                error=f"Play validation failed with {len(unified_result.errors)} error(s)",
                data={
                    "play_id": play_id,
                    "yaml_path": str(yaml_path),
                    "errors": [e.to_dict() for e in unified_result.errors],
                    "error_details": error_details,
                },
            )

        # Phase 2: Normalize (auto-generate required_indicators etc.)
        normalized, result = normalize_play_yaml(raw, auto_generate_required=True)

        if not result.is_valid:
            error_details = format_validation_errors(result.errors)
            return ToolResult(
                success=False,
                error=f"Play normalization failed with {len(result.errors)} error(s)",
                data={
                    "play_id": play_id,
                    "yaml_path": str(yaml_path),
                    "errors": [e.to_dict() for e in result.errors],
                    "error_details": error_details,
                },
            )

        # If write_in_place, write back the normalized YAML
        if write_in_place:
            # G6.3.1: Use LF line endings for Windows compatibility
            with open(yaml_path, "w", encoding="utf-8", newline='\n') as f:
                yaml.dump(normalized, f, sort_keys=False, default_flow_style=False)

            return ToolResult(
                success=True,
                message=f"Play '{play_id}' normalized and written to {yaml_path}",
                data={
                    "play_id": play_id,
                    "yaml_path": str(yaml_path),
                    "normalized": True,
                    "written": True,
                },
            )

        # Dry-run: just return validation success
        return ToolResult(
            success=True,
            message=f"Play '{play_id}' passed validation (dry-run, not written)",
            data={
                "play_id": play_id,
                "yaml_path": str(yaml_path),
                "normalized": True,
                "written": False,
                "warnings": result.warnings,
            },
        )

    except Exception as e:
        logger.error(f"Play normalization failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Normalization error: {e}",
        )


def backtest_play_normalize_batch_tool(
    plays_dir: Path,
    write_in_place: bool = False,
) -> ToolResult:
    """
    Batch normalize all Plays in a directory.

    Args:
        plays_dir: Directory containing Play YAML files
        write_in_place: If True, write normalized YAML back to files

    Returns:
        ToolResult with batch normalization results
    """
    try:
        from ..backtest.play import list_plays

        # Get all Play IDs in the directory
        play_ids = list_plays(base_dir=plays_dir)

        if not play_ids:
            return ToolResult(
                success=False,
                error=f"No Play YAML files found in {plays_dir}",
            )

        results = []
        passed_count = 0
        failed_count = 0

        logger.info(f"Batch normalizing {len(play_ids)} Plays in {plays_dir}")

        # Process each Play
        for play_id in play_ids:
            try:
                # Use the existing single-card normalize function
                single_result = backtest_play_normalize_tool(
                    play_id=play_id,
                    plays_dir=plays_dir,
                    write_in_place=write_in_place,
                )

                card_result = {
                    "play_id": play_id,
                    "success": single_result.success,
                    "message": single_result.message if single_result.success else single_result.error,
                    "data": single_result.data,
                }

                if single_result.success:
                    passed_count += 1
                else:
                    failed_count += 1

                results.append(card_result)

            except Exception as e:
                logger.error(f"Failed to process {play_id}: {e}")
                card_result = {
                    "play_id": play_id,
                    "success": False,
                    "message": str(e),
                    "data": None,
                }
                failed_count += 1
                results.append(card_result)

        # Determine overall success (all cards must pass)
        overall_success = failed_count == 0

        summary = {
            "total_cards": len(play_ids),
            "passed": passed_count,
            "failed": failed_count,
            "directory": str(plays_dir),
            "write_in_place": write_in_place,
        }

        if overall_success:
            return ToolResult(
                success=True,
                message=f"Batch normalization successful: {passed_count}/{len(play_ids)} cards passed",
                data={
                    "summary": summary,
                    "results": results,
                },
            )
        else:
            return ToolResult(
                success=False,
                error=f"Batch normalization failed: {failed_count}/{len(play_ids)} cards failed",
                data={
                    "summary": summary,
                    "results": results,
                },
            )

    except Exception as e:
        logger.error(f"Batch normalization failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Batch normalization error: {e}",
        )
