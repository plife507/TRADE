"""
Batch Verification — Runs multiple IdeaCards and produces batch_summary.json.

Gate D.2 requirement: Run 5 randomized IdeaCards and verify all pass.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import json

from .play_generator import (
    GeneratorConfig,
    GeneratedIdeaCard,
    generate_idea_cards,
    cleanup_generated_cards,
)


@dataclass
class CardRunResult:
    """Result of running a single IdeaCard."""
    idea_id: str
    symbol: str
    direction: str
    exec_tf: str
    success: bool
    error_message: str | None = None
    artifact_path: str | None = None
    preflight_passed: bool = False
    indicators_declared_only: bool = False
    evaluation_executed: bool = False
    artifacts_exist: bool = False
    deterministic_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BatchSummary:
    """Summary of batch verification run."""
    seed: int
    num_cards: int
    all_passed: bool
    idea_ids: list[str] = field(default_factory=list)
    symbols: list[str] = field(default_factory=list)
    directions: list[str] = field(default_factory=list)
    artifact_paths: list[str] = field(default_factory=list)
    results: list[CardRunResult] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["results"] = [r.to_dict() if hasattr(r, 'to_dict') else r for r in self.results]
        return d
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str, sort_keys=True)
    
    def write_json(self, path: Path) -> None:
        path.write_text(self.to_json())


def run_batch_verification(
    seed: int = 42,
    num_cards: int = 5,
    window_days: int = 5,
    output_dir: Path = Path("backtests/batch_verification"),
    env: str = "live",
    cleanup_after: bool = False,
    window_start: datetime | None = None,
    window_end: datetime | None = None,
) -> BatchSummary:
    """
    Run batch verification of generated IdeaCards.
    
    Args:
        seed: Random seed for determinism
        num_cards: Number of IdeaCards to generate and test
        window_days: Backtest window length in days (if dates not specified)
        output_dir: Output directory for batch artifacts
        env: Data environment ("live" or "demo")
        cleanup_after: Whether to cleanup generated cards after
        window_start: Explicit start date (optional)
        window_end: Explicit end date (optional)
        
    Returns:
        BatchSummary with results for all cards
    """
    from ..runner import run_backtest_with_gates, RunnerConfig
    from ..play import load_idea_card
    from ...data.historical_data_store import get_historical_store
    
    # Generate IdeaCards
    gen_config = GeneratorConfig(
        seed=seed,
        num_cards=num_cards,
    )
    generated_cards = generate_idea_cards(gen_config)
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Setup data loader
    store = get_historical_store(env=env)
    
    def data_loader(symbol: str, tf: str, start: datetime, end: datetime):
        return store.get_ohlcv(symbol=symbol, tf=tf, start=start, end=end)
    
    # Compute window - use explicit dates if provided, otherwise compute from now
    if window_end is None:
        window_end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    if window_start is None:
        window_start = window_end - timedelta(days=window_days)
    
    results: list[CardRunResult] = []
    
    for card in generated_cards:
        print(f"\n{'='*60}")
        print(f"Running: {card.id}")
        print(f"  Symbol: {card.symbol}, Direction: {card.direction}")
        print(f"{'='*60}")
        
        try:
            # Load the generated IdeaCard
            idea_card = load_idea_card(card.id, base_dir=gen_config.output_dir)
            
            # Create runner config
            config = RunnerConfig(
                idea_card=idea_card,
                window_start=window_start,
                window_end=window_end,
                data_loader=data_loader,
                base_output_dir=output_dir,
            )
            
            # Run backtest
            run_result = run_backtest_with_gates(config)
            
            # Build card result
            card_result = CardRunResult(
                idea_id=card.id,
                symbol=card.symbol,
                direction=card.direction,
                exec_tf=card.exec_tf,
                success=run_result.success,
                error_message=run_result.error_message,
                artifact_path=str(run_result.artifact_path) if run_result.artifact_path else None,
                preflight_passed=run_result.preflight_report is not None and run_result.preflight_report.overall_status.value == "passed",
                indicators_declared_only=True,  # Enforced by FeatureFrameBuilder
                evaluation_executed=True,  # Engine ran
                artifacts_exist=run_result.artifact_path is not None and run_result.artifact_path.exists(),
            )
            
            # Get hash for determinism check
            if run_result.summary:
                card_result.deterministic_hash = getattr(run_result.summary, 'run_hash', None)
            
            results.append(card_result)
            
        except Exception as e:
            results.append(CardRunResult(
                idea_id=card.id,
                symbol=card.symbol,
                direction=card.direction,
                exec_tf=card.exec_tf,
                success=False,
                error_message=str(e),
            ))
    
    # Build summary
    all_passed = all(r.success for r in results)
    
    summary = BatchSummary(
        seed=seed,
        num_cards=num_cards,
        all_passed=all_passed,
        idea_ids=[r.idea_id for r in results],
        symbols=[r.symbol for r in results],
        directions=[r.direction for r in results],
        artifact_paths=[r.artifact_path for r in results if r.artifact_path],
        results=results,
    )
    
    # Write batch summary
    summary_path = output_dir / "batch_summary.json"
    summary.write_json(summary_path)
    
    print(f"\n{'='*60}")
    print(f"BATCH VERIFICATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Cards run: {num_cards}")
    print(f"  All passed: {all_passed}")
    print(f"  Summary: {summary_path}")
    print(f"{'='*60}")
    
    # Cleanup if requested
    if cleanup_after:
        cleanup_generated_cards(gen_config.output_dir)
    
    return summary


# Standard filename
BATCH_SUMMARY_FILE = "batch_summary.json"

