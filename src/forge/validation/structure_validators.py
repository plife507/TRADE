"""
Structure validation helpers for engine-based smoke tests.

Validates structure detection through the production engine path (incremental/).
"""

from pathlib import Path
from typing import Any, cast


def validate_structure_accessible(
    snapshot: Any,
    key: str,
    field: str,
) -> bool:
    """
    Check that a structure field is accessible via snapshot.

    Args:
        snapshot: RuntimeSnapshotView instance
        key: Structure key (e.g., "swing")
        field: Field name (e.g., "high_level")

    Returns:
        True if accessible, False otherwise
    """
    try:
        # Try the dot notation path used by engine
        path = f"{key}.{field}"
        snapshot.get(path)
        return True
    except (KeyError, ValueError, AttributeError):
        return False


def validate_no_lookahead(
    structure_outputs: dict[str, Any],
    pivot_field: str = "high_idx",
    confirmation_field: str = "high_level",
    right_bars: int = 5,
) -> tuple[bool, str]:
    """
    Verify pivot confirmation delay respects no-lookahead rule.

    A pivot at bar N should not be confirmed until bar N + right_bars.

    Args:
        structure_outputs: Dict of structure output arrays
        pivot_field: Field containing pivot bar index
        confirmation_field: Field containing confirmed pivot level
        right_bars: Number of bars required for confirmation

    Returns:
        Tuple of (passed, message)
    """
    import numpy as np

    if pivot_field not in structure_outputs:
        return False, f"Missing field: {pivot_field}"
    if confirmation_field not in structure_outputs:
        return False, f"Missing field: {confirmation_field}"

    pivot_idx_arr = structure_outputs[pivot_field]
    level_arr = structure_outputs[confirmation_field]
    n_bars = len(level_arr)

    # Find first bar where we have a confirmed pivot
    first_confirm_bar = None
    first_pivot_bar = None

    for i in range(n_bars):
        if not np.isnan(level_arr[i]) and not np.isnan(pivot_idx_arr[i]):
            first_confirm_bar = i
            first_pivot_bar = int(pivot_idx_arr[i])
            break

    if first_confirm_bar is None or first_pivot_bar is None:
        return True, "No pivots confirmed (not enough data for validation)"

    # Pivot at bar P should not be confirmed until bar >= P + right_bars
    expected_min_confirm = first_pivot_bar + right_bars

    if first_confirm_bar >= expected_min_confirm:
        return True, f"OK: pivot at bar {first_pivot_bar}, confirmed at bar {first_confirm_bar}"
    else:
        return False, (
            f"LOOKAHEAD: pivot at bar {first_pivot_bar}, confirmed at bar {first_confirm_bar} "
            f"(expected >= {expected_min_confirm})"
        )


def validate_determinism(
    play_path: Path,
    runs: int = 2,
    seed: int = 42,
) -> tuple[bool, str]:
    """
    Run Play twice and compare trade hashes.

    Args:
        play_path: Path to Play YAML file
        runs: Number of runs to compare (default: 2)
        seed: Random seed for synthetic data

    Returns:
        Tuple of (passed, message)
    """
    from src.backtest.play import load_play
    from src.backtest.engine_factory import create_engine_from_play, run_engine_with_play
    from src.backtest.artifacts.hashes import compute_trades_hash
    from src.backtest.execution_validation import compute_warmup_requirements
    from src.forge.validation.synthetic_data import generate_synthetic_candles
    from src.forge.validation.synthetic_provider import SyntheticCandlesProvider

    # Load play
    play = load_play(str(play_path))

    # Generate synthetic data
    timeframes = [play.exec_tf]
    candles = generate_synthetic_candles(
        symbol=play.symbol_universe[0] if play.symbol_universe else "BTCUSDT",
        timeframes=timeframes,
        bars_per_tf=500,
        seed=seed,
        pattern="trending",
    )

    # Run multiple times
    hashes = []
    for run_idx in range(runs):
        provider = SyntheticCandlesProvider(candles)
        warmup_reqs = compute_warmup_requirements(play)

        engine = create_engine_from_play(
            play=play,
            warmup_by_tf=warmup_reqs.warmup_by_role,
            synthetic_provider=provider,
        )

        result = run_engine_with_play(engine, play)
        trade_hash = compute_trades_hash(result.trades)
        hashes.append(trade_hash)

    # Compare hashes
    if len(set(hashes)) == 1:
        return True, f"OK: {runs} runs produced identical hash: {hashes[0]}"
    else:
        return False, f"DETERMINISM FAILED: hashes differ: {hashes}"


def validate_strict_allowlist(
    snapshot: Any,
    structure_key: str,
    valid_field: str,
    invalid_field: str = "definitely_not_a_real_field",
) -> tuple[bool, str]:
    """
    Verify unknown structure fields raise ValueError.

    Args:
        snapshot: RuntimeSnapshotView instance
        structure_key: Structure key (e.g., "swing")
        valid_field: Known valid field for sanity check
        invalid_field: Invalid field name to test

    Returns:
        Tuple of (passed, message)
    """
    # First, sanity check that valid field works
    path = f"{structure_key}.{valid_field}"
    try:
        snapshot.get(path)
    except (KeyError, ValueError):
        return False, f"Valid field {path} should be accessible"

    # Now test invalid field raises ValueError
    try:
        path = f"{structure_key}.{invalid_field}"
        snapshot.get(path)
        return False, f"Invalid field {path} should raise ValueError"
    except ValueError:
        return True, "OK: Unknown field correctly raises ValueError"
    except Exception as e:
        return False, f"Unexpected error for invalid field: {type(e).__name__}: {e}"


def run_play_with_synthetic(
    play_path: str | Path,
    seed: int = 42,
    extra_bars: int = 500,
    pattern: str = "trending",
) -> tuple[Any, Any]:
    """
    Run a Play with synthetic data through the production engine.

    Args:
        play_path: Path or Play ID
        seed: Random seed
        extra_bars: Bars beyond warmup
        pattern: Price pattern type

    Returns:
        Tuple of (result, engine) for further validation
    """
    from src.backtest.play import load_play
    from src.backtest.engine_factory import create_engine_from_play, run_engine_with_play
    from src.backtest.execution_validation import compute_warmup_requirements
    from src.forge.validation.synthetic_data import generate_synthetic_candles, PatternType
    from src.forge.validation.synthetic_provider import SyntheticCandlesProvider

    # Load play
    play = load_play(str(play_path))

    # Generate synthetic data with required TFs
    timeframes = [play.exec_tf]
    if "1m" not in timeframes:
        timeframes.append("1m")  # Needed for intrabar evaluation

    candles = generate_synthetic_candles(
        symbol=play.symbol_universe[0] if play.symbol_universe else "BTCUSDT",
        timeframes=sorted(timeframes),
        bars_per_tf=extra_bars,
        seed=seed,
        pattern=cast(PatternType, pattern),
        align_multi_tf=True,
    )

    provider = SyntheticCandlesProvider(candles)
    warmup_reqs = compute_warmup_requirements(play)

    engine = create_engine_from_play(
        play=play,
        warmup_by_tf=warmup_reqs.warmup_by_role,
        synthetic_provider=provider,
    )

    result = run_engine_with_play(engine, play)

    return result, engine
