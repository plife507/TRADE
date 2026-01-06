"""
Play loader for visualization.

Loads Play from result.json and verifies hash integrity.
"""

import json
from pathlib import Path
from typing import Any

from src.backtest.play import load_play, Play
from src.backtest.execution_validation import compute_play_hash


class PlayHashMismatchError(Exception):
    """Raised when Play hash doesn't match the stored hash from backtest run."""

    def __init__(self, play_id: str, stored_hash: str, computed_hash: str):
        self.play_id = play_id
        self.stored_hash = stored_hash
        self.computed_hash = computed_hash
        super().__init__(
            f"Play '{play_id}' has been modified since the backtest run. "
            f"Stored hash: {stored_hash}, Current hash: {computed_hash}"
        )


class PlayNotFoundError(Exception):
    """Raised when Play cannot be found for a run."""

    def __init__(self, play_id: str, run_id: str):
        self.play_id = play_id
        self.run_id = run_id
        super().__init__(
            f"Play '{play_id}' not found for run '{run_id}'. "
            "The Play may have been deleted or renamed."
        )


def load_result_json(run_path: Path) -> dict[str, Any]:
    """
    Load result.json from a run directory.

    Args:
        run_path: Path to run directory

    Returns:
        Result dict with play_id, idea_hash, symbol, etc.

    Raises:
        FileNotFoundError: If result.json doesn't exist
        json.JSONDecodeError: If result.json is invalid
    """
    result_path = run_path / "result.json"
    if not result_path.exists():
        raise FileNotFoundError(f"result.json not found in {run_path}")

    with open(result_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_play_for_run(
    run_path: Path,
    verify_hash: bool = True,
) -> tuple[Play, dict[str, Any]]:
    """
    Load Play for a backtest run and optionally verify hash.

    Args:
        run_path: Path to run directory containing result.json
        verify_hash: If True, verify Play hash matches stored hash

    Returns:
        Tuple of (Play, result_dict)

    Raises:
        PlayHashMismatchError: If hash verification fails
        PlayNotFoundError: If Play cannot be found
        FileNotFoundError: If result.json doesn't exist
    """
    # Load result.json
    result = load_result_json(run_path)

    play_id = result.get("play_id")
    stored_hash = result.get("idea_hash")
    run_id = run_path.name

    if not play_id:
        raise ValueError(f"result.json in {run_path} missing 'play_id' field")

    # Load Play
    try:
        play = load_play(play_id)
    except FileNotFoundError as e:
        raise PlayNotFoundError(play_id, run_id) from e

    # Verify hash if requested
    if verify_hash and stored_hash:
        computed_hash = compute_play_hash(play)
        if computed_hash != stored_hash:
            raise PlayHashMismatchError(play_id, stored_hash, computed_hash)

    return play, result


def get_unique_timeframes(play: Play) -> set[str]:
    """
    Get all unique timeframes from Play features.

    Args:
        play: Play object

    Returns:
        Set of timeframe strings (e.g., {"5m", "1h", "4h"})
    """
    timeframes = set()

    # Always include execution timeframe
    if play.execution_tf:
        timeframes.add(play.execution_tf)

    # Collect TFs from features
    for feature in play.features:
        if hasattr(feature, "tf") and feature.tf:
            timeframes.add(feature.tf)

    return timeframes


def get_run_metadata_from_result(result: dict[str, Any]) -> dict[str, Any]:
    """
    Extract visualization-relevant metadata from result.json.

    Args:
        result: Parsed result.json dict

    Returns:
        Dict with symbol, tf_exec, window_start, window_end, etc.
    """
    return {
        "play_id": result.get("play_id"),
        "idea_hash": result.get("idea_hash"),
        "symbol": result.get("symbol"),
        "tf_exec": result.get("tf_exec"),
        "window_start": result.get("window_start"),
        "window_end": result.get("window_end"),
        "warmup_bars": result.get("warmup_bars", 0),
        "total_bars": result.get("total_bars", 0),
    }
