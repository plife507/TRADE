"""
DSL Warmup Analysis: Compute warmup requirements from expressions.

Analyzes DSL expression trees to determine:
- Maximum offset in any FeatureRef
- Window bars in any WindowOp (HoldsFor, OccurredWithin, CountTrue)
- Crossover operators that implicitly need offset >= 1

The total warmup for an expression is the combination of:
- Indicator warmup (from FeatureRegistry)
- Max offset (from DSL analysis)
- Max window bars (from DSL analysis)

Usage:
    from src.backtest.rules.dsl_warmup import compute_dsl_warmup

    warmup = compute_dsl_warmup(
        blocks=blocks,
        feature_registry=registry,
    )
    # warmup contains max_offset, max_window_bars, feature_warmups, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .dsl_nodes import (
    Expr, Cond, AllExpr, AnyExpr, NotExpr,
    HoldsFor, OccurredWithin, CountTrue,
    FeatureRef, CROSSOVER_OPERATORS,
    get_max_offset, get_referenced_features,
)
from .strategy_blocks import Block

if TYPE_CHECKING:
    from ..feature_registry import FeatureRegistry


# =============================================================================
# Analysis Results
# =============================================================================

@dataclass
class FeatureWarmup:
    """Warmup information for a single feature."""
    feature_id: str
    tf: str
    indicator_warmup: int  # From registry (indicator computation warmup)
    max_offset: int  # From DSL (bar offset lookback)
    max_window: int  # From DSL (window operator bars)

    @property
    def total(self) -> int:
        """Total warmup bars needed."""
        return self.indicator_warmup + self.max_offset + self.max_window


@dataclass
class DSLWarmupAnalysis:
    """
    Complete warmup analysis results.

    Attributes:
        max_offset: Maximum offset across all FeatureRefs
        max_window_bars: Maximum window bars across all WindowOps
        feature_warmups: Per-feature warmup breakdown
        total_warmup: Overall warmup requirement (max across all features)
        referenced_features: Set of all referenced feature IDs
    """
    max_offset: int = 0
    max_window_bars: int = 0
    feature_warmups: dict[str, FeatureWarmup] = field(default_factory=dict)
    total_warmup: int = 0
    referenced_features: set[str] = field(default_factory=set)

    def get_warmup_for_tf(self, tf: str) -> int:
        """Get warmup for a specific timeframe."""
        max_warmup = 0
        for fw in self.feature_warmups.values():
            if fw.tf == tf:
                max_warmup = max(max_warmup, fw.total)
        return max_warmup


# =============================================================================
# Expression Analysis
# =============================================================================

def _extract_offsets(expr: Expr) -> dict[str, int]:
    """
    Extract maximum offset for each feature in an expression.

    Args:
        expr: Expression to analyze.

    Returns:
        Dict mapping feature_id to maximum offset.
    """
    offsets: dict[str, int] = {}

    def collect(e: Expr, additional_offset: int = 0) -> None:
        if isinstance(e, Cond):
            # LHS - only FeatureRef has feature_id/offset
            if not isinstance(e.lhs, FeatureRef):
                return  # ArithmeticExpr LHS - skip offset collection
            feature_id = e.lhs.feature_id
            total_offset = e.lhs.offset + additional_offset
            offsets[feature_id] = max(offsets.get(feature_id, 0), total_offset)

            # Cross operators implicitly need previous bar
            if e.op in CROSSOVER_OPERATORS:
                offsets[feature_id] = max(offsets[feature_id], 1 + additional_offset)

            # RHS if FeatureRef
            if isinstance(e.rhs, FeatureRef):
                rhs_id = e.rhs.feature_id
                rhs_offset = e.rhs.offset + additional_offset
                offsets[rhs_id] = max(offsets.get(rhs_id, 0), rhs_offset)
                if e.op in CROSSOVER_OPERATORS:
                    offsets[rhs_id] = max(offsets[rhs_id], 1 + additional_offset)

        elif isinstance(e, AllExpr):
            for child in e.children:
                collect(child, additional_offset)

        elif isinstance(e, AnyExpr):
            for child in e.children:
                collect(child, additional_offset)

        elif isinstance(e, NotExpr):
            collect(e.child, additional_offset)

        elif isinstance(e, HoldsFor):
            # Window ops look back bars-1 additional bars
            collect(e.expr, additional_offset + e.bars - 1)

        elif isinstance(e, OccurredWithin):
            collect(e.expr, additional_offset + e.bars - 1)

        elif isinstance(e, CountTrue):
            collect(e.expr, additional_offset + e.bars - 1)

    collect(expr)
    return offsets


def _extract_window_bars(expr: Expr) -> int:
    """
    Extract maximum window bars from an expression.

    Args:
        expr: Expression to analyze.

    Returns:
        Maximum window bars (0 if no window operators).
    """
    max_window = 0

    def collect(e: Expr) -> None:
        nonlocal max_window

        if isinstance(e, (HoldsFor, OccurredWithin, CountTrue)):
            max_window = max(max_window, e.bars)
            collect(e.expr)

        elif isinstance(e, AllExpr):
            for child in e.children:
                collect(child)

        elif isinstance(e, AnyExpr):
            for child in e.children:
                collect(child)

        elif isinstance(e, NotExpr):
            collect(e.child)

        elif isinstance(e, Cond):
            pass  # No window in conditions

    collect(expr)
    return max_window


# =============================================================================
# Block Analysis
# =============================================================================

def analyze_block(block: Block) -> tuple[dict[str, int], int, set[str]]:
    """
    Analyze a single block for warmup requirements.

    Args:
        block: Block to analyze.

    Returns:
        Tuple of (feature_offsets, max_window_bars, referenced_features).
    """
    all_offsets: dict[str, int] = {}
    max_window = 0
    all_features: set[str] = set()

    for case in block.cases:
        # Extract from 'when' expression
        offsets = _extract_offsets(case.when)
        for fid, offset in offsets.items():
            all_offsets[fid] = max(all_offsets.get(fid, 0), offset)

        window = _extract_window_bars(case.when)
        max_window = max(max_window, window)

        features = get_referenced_features(case.when)
        all_features.update(features)

    return all_offsets, max_window, all_features


def analyze_blocks(blocks: list[Block]) -> tuple[dict[str, int], int, set[str]]:
    """
    Analyze multiple blocks for warmup requirements.

    Args:
        blocks: List of blocks to analyze.

    Returns:
        Tuple of (feature_offsets, max_window_bars, referenced_features).
    """
    all_offsets: dict[str, int] = {}
    max_window = 0
    all_features: set[str] = set()

    for block in blocks:
        offsets, window, features = analyze_block(block)

        for fid, offset in offsets.items():
            all_offsets[fid] = max(all_offsets.get(fid, 0), offset)

        max_window = max(max_window, window)
        all_features.update(features)

    return all_offsets, max_window, all_features


# =============================================================================
# High-Level API
# =============================================================================

def compute_dsl_warmup(
    blocks: list[Block],
    feature_registry: "FeatureRegistry | None" = None,
) -> DSLWarmupAnalysis:
    """
    Compute complete warmup analysis for DSL blocks.

    Combines:
    - Indicator warmup (from FeatureRegistry)
    - Max offset (from DSL expressions)
    - Max window bars (from DSL window operators)

    Args:
        blocks: List of Block instances.
        feature_registry: Optional FeatureRegistry for indicator warmup.

    Returns:
        DSLWarmupAnalysis with complete warmup information.
    """
    # Analyze blocks
    feature_offsets, max_window, referenced_features = analyze_blocks(blocks)

    # Compute max offset across all features
    max_offset = max(feature_offsets.values()) if feature_offsets else 0

    # Build per-feature warmup
    feature_warmups: dict[str, FeatureWarmup] = {}
    total_warmup = 0

    for feature_id in referenced_features:
        offset = feature_offsets.get(feature_id, 0)

        # Get indicator warmup from registry
        indicator_warmup = 0
        tf = "exec"  # Default
        if feature_registry:
            try:
                feature = feature_registry.get(feature_id)
                tf = feature.tf
                indicator_warmup = feature_registry.get_warmup_for_tf(tf)
            except (KeyError, AttributeError):
                pass

        fw = FeatureWarmup(
            feature_id=feature_id,
            tf=tf,
            indicator_warmup=indicator_warmup,
            max_offset=offset,
            max_window=max_window,
        )
        feature_warmups[feature_id] = fw
        total_warmup = max(total_warmup, fw.total)

    return DSLWarmupAnalysis(
        max_offset=max_offset,
        max_window_bars=max_window,
        feature_warmups=feature_warmups,
        total_warmup=total_warmup,
        referenced_features=referenced_features,
    )


def compute_warmup_for_expr(
    expr: Expr,
    feature_registry: "FeatureRegistry | None" = None,
) -> int:
    """
    Compute warmup for a single expression.

    Args:
        expr: Expression to analyze.
        feature_registry: Optional FeatureRegistry for indicator warmup.

    Returns:
        Total warmup bars needed.
    """
    # Get max offset
    max_offset = get_max_offset(expr)

    # Get max window
    max_window = _extract_window_bars(expr)

    # Get base warmup from registry
    base_warmup = 0
    if feature_registry:
        features = get_referenced_features(expr)
        for feature_id in features:
            try:
                feature = feature_registry.get(feature_id)
                warmup = feature_registry.get_warmup_for_tf(feature.tf)
                base_warmup = max(base_warmup, warmup)
            except (KeyError, AttributeError):
                pass

    return base_warmup + max_offset + max_window
