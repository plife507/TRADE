"""
Execution Validation: Play → Engine Contract Validation.

Phase 8 implementation for validating Plays before execution:
- Gate 8.0: Play execution contract (hashing, validation)
- Gate 8.1: Feature reference extraction and validation
- Gate 8.2: Warmup window definition
- Gate 8.4: Pre-evaluation validation gates

Design principles:
- Validate at load time, not runtime
- Fail fast with clear error messages
- No implicit defaults
- All referenced features must be declared
"""

from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .play import Play, TFConfig
    from .rules.strategy_blocks import Block

# Note: IndicatorType enum removed in Registry Consolidation Phase 2
# All indicator type handling is now via string + registry validation


# =============================================================================
# Validation Constants
# =============================================================================

# Maximum allowed warmup bars per TF (prevents accidental years of data requests)
MAX_WARMUP_BARS = 1000

# Earliest available Bybit data (linear perpetuals launched late 2018)
# This prevents requests for data that doesn't exist
EARLIEST_BYBIT_DATE_YEAR = 2018
EARLIEST_BYBIT_DATE_MONTH = 11  # November 2018


# =============================================================================
# Gate 8.0: Play Execution Contract
# =============================================================================

def compute_play_hash(play: "Play") -> str:
    """
    Compute a deterministic hash for an Play.
    
    Identical Plays produce identical hashes.
    Hash is based on all execution-relevant fields.
    
    Args:
        play: The Play to hash
        
    Returns:
        SHA256 hash as hex string (first 16 chars for readability)
    """
    # Convert to dict (deterministic serialization)
    card_dict = play.to_dict()
    
    # Sort keys for determinism
    canonical_json = json.dumps(card_dict, sort_keys=True, separators=(",", ":"))
    
    # Compute hash
    hash_bytes = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
    
    # Return first 16 chars for readability
    return hash_bytes[:16]


class ValidationSeverity(str, Enum):
    """Severity level for validation issues."""
    ERROR = "error"      # Blocks execution
    WARNING = "warning"  # Does not block, but should be addressed


@dataclass
class ValidationIssue:
    """A single validation issue."""
    severity: ValidationSeverity
    code: str
    message: str
    location: str | None = None  # e.g., "entry_rules[0].conditions[1]"

    def to_dict(self) -> dict:
        return {
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "location": self.location,
        }


@dataclass
class PlayValidationResult:
    """Result of Play validation."""
    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    hash: str | None = None

    @property
    def errors(self) -> list[ValidationIssue]:
        """Get only error-level issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Get only warning-level issues."""
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "hash": self.hash,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [i.to_dict() for i in self.issues],
        }


def validate_play_contract(play: "Play") -> PlayValidationResult:
    """
    Validate Play execution contract.
    
    Gate 8.0: Ensures Play is a valid, deterministic execution unit.
    
    Checks:
    - Required fields are present
    - TF configs are valid
    - Position policy is consistent with signal rules
    - Hash is computable
    
    Args:
        play: Play to validate

    Returns:
        PlayValidationResult with issues (if any)
    """
    issues: list[ValidationIssue] = []

    # Required fields
    if not play.id:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            code="MISSING_ID",
            message="Play.id is required",
        ))
    
    if not play.version:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            code="MISSING_VERSION",
            message="Play.version is required",
        ))
    
    if not play.symbol_universe:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            code="MISSING_SYMBOLS",
            message="Play.symbol_universe is required (at least one symbol)",
        ))
    
    # Exec TF is required
    if not play.execution_tf:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            code="MISSING_EXEC_TF",
            message="execution_tf is required",
        ))
    
    # Account config is REQUIRED (no hard-coded defaults)
    if play.account is None:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.ERROR,
            code="MISSING_ACCOUNT",
            message=(
                "Play.account section is required. "
                "Specify account.starting_equity_usdt and account.max_leverage."
            ),
        ))
    else:
        # Validate account values
        if play.account.starting_equity_usdt <= 0:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="INVALID_STARTING_EQUITY",
                message=f"account.starting_equity_usdt must be positive. Got: {play.account.starting_equity_usdt}",
            ))
        if play.account.max_leverage <= 0:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="INVALID_MAX_LEVERAGE",
                message=f"account.max_leverage must be positive. Got: {play.account.max_leverage}",
            ))
    
    # Warmup bars validation (P2.2: prevent excessive data requests)
    # Warmup is computed from feature registry at runtime - validation
    # happens during compute_warmup_requirements() call
    
    # Blocks must exist for signal generation
    if not play.blocks:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.WARNING,
            code="NO_BLOCKS",
            message="No blocks defined - Play cannot generate signals",
        ))
    
    # Risk model should exist
    if play.risk_model is None:
        issues.append(ValidationIssue(
            severity=ValidationSeverity.WARNING,
            code="NO_RISK_MODEL",
            message="No risk_model defined - positions will not have SL/TP",
        ))
    
    # Compute hash if no critical errors
    card_hash = None
    if not any(i.severity == ValidationSeverity.ERROR for i in issues):
        try:
            card_hash = compute_play_hash(play)
        except Exception as e:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="HASH_FAILED",
                message=f"Failed to compute Play hash: {e}",
            ))
    
    is_valid = not any(i.severity == ValidationSeverity.ERROR for i in issues)
    
    return PlayValidationResult(
        is_valid=is_valid,
        issues=issues,
        hash=card_hash,
    )


# =============================================================================
# Gate 8.1: Feature Reference Extraction + Validation
# =============================================================================

@dataclass
class FeatureReference:
    """A reference to a feature/indicator in blocks."""
    key: str
    tf_role: str  # "exec" (blocks use feature_id which encodes TF)
    location: str  # e.g., "blocks[0].cases[0].when"


def extract_rule_feature_refs(play: "Play") -> list[FeatureReference]:
    """
    Extract all feature references from Play blocks.

    Gate 8.1: Finds all feature_id references in block expressions.

    Args:
        play: Play with blocks

    Returns:
        List of FeatureReference objects
    """
    from .rules.dsl_nodes import (
        Expr, Cond, AllExpr, AnyExpr, NotExpr,
        HoldsFor, OccurredWithin, CountTrue, FeatureRef,
    )

    refs: list[FeatureReference] = []

    if not play.blocks:
        return refs

    def _extract_from_expr(expr: Expr, location: str) -> None:
        """Recursively extract feature refs from expression."""
        if isinstance(expr, Cond):
            # Extract LHS feature
            refs.append(FeatureReference(
                key=expr.lhs.feature_id,
                tf_role="exec",  # Blocks use feature_id which encodes TF
                location=f"{location}.lhs",
            ))
            # Extract RHS if it's a FeatureRef
            if isinstance(expr.rhs, FeatureRef):
                refs.append(FeatureReference(
                    key=expr.rhs.feature_id,
                    tf_role="exec",
                    location=f"{location}.rhs",
                ))
        elif isinstance(expr, AllExpr):
            for i, child in enumerate(expr.children):
                _extract_from_expr(child, f"{location}.all[{i}]")
        elif isinstance(expr, AnyExpr):
            for i, child in enumerate(expr.children):
                _extract_from_expr(child, f"{location}.any[{i}]")
        elif isinstance(expr, NotExpr):
            _extract_from_expr(expr.child, f"{location}.not")
        elif isinstance(expr, (HoldsFor, OccurredWithin, CountTrue)):
            _extract_from_expr(expr.expr, f"{location}.window")

    # Extract from all blocks
    for i, block in enumerate(play.blocks):
        for j, case in enumerate(block.cases):
            _extract_from_expr(case.when, f"blocks[{i}].cases[{j}].when")

    # Extract from risk model if ATR-based SL
    if play.risk_model and play.risk_model.stop_loss.atr_feature_id:
        refs.append(FeatureReference(
            key=play.risk_model.stop_loss.atr_feature_id,
            tf_role="exec",
            location="risk_model.stop_loss.atr_feature_id",
        ))

    if play.risk_model and play.risk_model.take_profit.atr_feature_id:
        refs.append(FeatureReference(
            key=play.risk_model.take_profit.atr_feature_id,
            tf_role="exec",
            location="risk_model.take_profit.atr_feature_id",
        ))

    return refs


# OHLCV columns are always available (not declared as features)
OHLCV_COLUMNS = {"open", "high", "low", "close", "volume", "timestamp"}

# Built-in keys available without declaration (1m eval loop feature)
BUILTIN_KEYS = {"mark_price"}


def get_declared_features_by_role(play: "Play") -> dict[str, set[str]]:
    """
    Get all declared feature keys organized by TF role.

    OHLCV columns (open, high, low, close, volume) are always implicitly available.
    Built-in keys (mark_price) are also always available without declaration.

    With the new Play schema, features are stored in a flat list with each
    Feature having its own tf attribute. We use the feature_registry to get
    all declared feature keys.

    Args:
        play: Play with features list

    Returns:
        Dict mapping "exec" -> set of all feature keys (including OHLCV and built-in)
    """
    # New schema: features are in a flat list, all accessible from exec context
    # The feature_registry handles multi-TF features with forward-fill semantics
    keys = set(OHLCV_COLUMNS) | set(BUILTIN_KEYS)

    # Get all feature IDs from the registry (includes expanded multi-output keys)
    try:
        registry = play.feature_registry
        # Add all feature IDs (primary keys)
        for feature in registry.all_features():
            keys.add(feature.id)
            # Also add output_keys for multi-output indicators
            if feature.output_keys:
                keys.update(feature.output_keys)
    except Exception:
        # If registry fails to build, return just OHLCV/builtin
        pass

    # All features are accessible from "exec" context in new schema
    return {"exec": keys}


def validate_play_features(play: "Play") -> PlayValidationResult:
    """
    Validate all feature references in Play.
    
    Gate 8.1: Ensures all referenced features are declared.
    
    Checks:
    - All indicator_key references exist in declared features
    - TF role matches (feature declared in correct TF)
    - No unknown indicator types
    
    Args:
        play: Play to validate

    Returns:
        PlayValidationResult with issues (if any)
    """
    issues: list[ValidationIssue] = []

    # Get all declared features
    declared = get_declared_features_by_role(play)
    
    # Get all references
    refs = extract_rule_feature_refs(play)
    
    # In new schema, all features are accessible from "exec" context
    exec_features = declared.get("exec", set())

    for ref in refs:
        key = ref.key

        # Skip structure paths - validated separately by structure block validation
        if key.startswith("structure."):
            continue

        # Check feature exists in declared features
        if key not in exec_features:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="UNDECLARED_FEATURE",
                message=f"Feature '{key}' referenced but not declared in features",
                location=ref.location,
            ))
    
    is_valid = not any(i.severity == ValidationSeverity.ERROR for i in issues)
    
    return PlayValidationResult(
        is_valid=is_valid,
        issues=issues,
    )


# =============================================================================
# Gate 8.2: Warmup Window Definition
# =============================================================================

@dataclass
class WarmupRequirements:
    """
    Warmup requirements for an Play.
    
    Contains two distinct concepts:
    - warmup/lookback: Bars needed for data fetch and indicator computation
    - delay: Bars to skip at evaluation start (no-lookahead guarantee)
    
    Semantics:
    - warmup_by_role (lookback): data_start = window_start - lookback * tf_duration
    - delay_by_role: eval_start = aligned_start + delay * tf_duration
    
    Engine uses lookback for data loading, delay for evaluation offset.
    Engine MUST NOT apply lookback again to evaluation start.
    """
    # Per-TF warmup/lookback bars (for data fetch)
    warmup_by_role: dict[str, int] = field(default_factory=dict)

    # Per-TF delay bars (for evaluation offset)
    delay_by_role: dict[str, int] = field(default_factory=dict)

    # Maximum across all TFs
    max_warmup_bars: int = 0
    max_delay_bars: int = 0

    # Source breakdown
    feature_warmup: dict[str, int] = field(default_factory=dict)  # role -> max feature warmup
    bars_history_required: int = 0

    def to_dict(self) -> dict:
        return {
            "warmup_by_role": self.warmup_by_role,
            "delay_by_role": self.delay_by_role,
            "max_warmup_bars": self.max_warmup_bars,
            "max_delay_bars": self.max_delay_bars,
            "feature_warmup": self.feature_warmup,
            "bars_history_required": self.bars_history_required,
        }


def _compute_structure_warmup(play: "Play") -> int:
    """
    Compute warmup needed for market structure features.

    In the new Play schema, structures are part of the features list
    with type='structure' and structure_type indicating the detector type.

    Warmup formulas are stored in STRUCTURE_WARMUP_FORMULAS registry.
    See: src/backtest/incremental/registry.py

    Args:
        play: Play with features list

    Returns:
        Maximum warmup bars needed for structure computation

    Raises:
        KeyError: If structure type has no warmup formula in registry
    """
    from src.backtest.incremental.registry import get_structure_warmup

    registry = play.feature_registry
    structures = registry.get_structures()

    if not structures:
        return 0

    # First pass: find MAX swing params across all swings for dependent structures
    # Multiple swings may exist (e.g., exec swing + HTF swing) - use largest window
    max_left = 5  # default
    max_right = 5  # default
    for feature in structures:
        if feature.structure_type == "swing":
            max_left = max(max_left, feature.params.get("left", 5))
            max_right = max(max_right, feature.params.get("right", 5))
    swing_params = {"left": max_left, "right": max_right}

    # Second pass: compute warmup for each structure using registry
    max_structure_warmup = 0
    for feature in structures:
        struct_warmup = get_structure_warmup(
            feature.structure_type,
            feature.params,
            swing_params,
        )
        max_structure_warmup = max(max_structure_warmup, struct_warmup)

    return max_structure_warmup


def compute_warmup_requirements(play: "Play") -> WarmupRequirements:
    """
    Compute canonical warmup requirements for an Play.

    Gate 8.2: Warmup = max(feature_warmups, structure_warmup)

    With the new Play schema, features are stored in a flat list with each
    Feature having its own tf attribute. We use the feature_registry to compute
    warmup requirements.

    Args:
        play: Play to analyze

    Returns:
        WarmupRequirements with per-TF warmup and delay
    """
    warmup_by_role: dict[str, int] = {}
    delay_by_role: dict[str, int] = {}
    feature_warmup: dict[str, int] = {}

    # Compute structure warmup (Stage 3: all blocks are exec-only)
    structure_warmup = _compute_structure_warmup(play)

    try:
        registry = play.feature_registry
        all_tfs = registry.get_all_tfs()

        for tf in all_tfs:
            # Get max warmup from feature registry for this TF
            max_feature_warmup = registry.get_warmup_for_tf(tf)
            feature_warmup[tf] = max_feature_warmup

            # Include structure_warmup for exec TF
            role_structure_warmup = structure_warmup if tf == play.execution_tf else 0
            effective_warmup = max(max_feature_warmup, role_structure_warmup)

            warmup_by_role[tf] = effective_warmup
            delay_by_role[tf] = 0  # No delay in new schema

        # Ensure exec TF is always present
        if play.execution_tf and play.execution_tf not in warmup_by_role:
            warmup_by_role[play.execution_tf] = structure_warmup
            delay_by_role[play.execution_tf] = 0
            feature_warmup[play.execution_tf] = 0

    except Exception:
        # Fallback if registry fails
        if play.execution_tf:
            warmup_by_role[play.execution_tf] = structure_warmup
            delay_by_role[play.execution_tf] = 0
            feature_warmup[play.execution_tf] = 0

    # Overall max
    max_warmup = max(warmup_by_role.values()) if warmup_by_role else 0
    max_delay = max(delay_by_role.values()) if delay_by_role else 0

    return WarmupRequirements(
        warmup_by_role=warmup_by_role,
        delay_by_role=delay_by_role,
        max_warmup_bars=max_warmup,
        max_delay_bars=max_delay,
        feature_warmup=feature_warmup,
        bars_history_required=0,  # No longer used in new schema
    )


# =============================================================================
# Gate 8.4: Pre-Evaluation Validation Gates
# =============================================================================

@dataclass
class PreEvaluationStatus:
    """Status of pre-evaluation validation."""
    is_ready: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    warmup_satisfied: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "is_ready": self.is_ready,
            "warmup_satisfied": self.warmup_satisfied,
            "error_count": len([i for i in self.issues if i.severity == ValidationSeverity.ERROR]),
            "issues": [i.to_dict() for i in self.issues],
        }


def validate_pre_evaluation(
    play: "Play",
    bar_counts: dict[str, int],  # role -> current bar count
    warmup_requirements: WarmupRequirements | None = None,
) -> PreEvaluationStatus:
    """
    Validate Play is ready for evaluation at current bar.
    
    Gate 8.4: Pre-evaluation validation.
    
    Checks:
    - All TFs have sufficient bars for warmup
    - All required features are available
    
    Args:
        play: Play being evaluated
        bar_counts: Current bar count per TF role
        warmup_requirements: Pre-computed warmup (or computed if None)
        
    Returns:
        PreEvaluationStatus indicating readiness
    """
    issues: list[ValidationIssue] = []
    warmup_satisfied: dict[str, bool] = {}
    
    # Compute warmup if not provided
    if warmup_requirements is None:
        warmup_requirements = compute_warmup_requirements(play)
    
    # Check warmup for each TF
    for role, required_warmup in warmup_requirements.warmup_by_role.items():
        current_bars = bar_counts.get(role, 0)
        satisfied = current_bars >= required_warmup
        warmup_satisfied[role] = satisfied
        
        if not satisfied:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code="WARMUP_NOT_SATISFIED",
                message=f"{role} TF needs {required_warmup} bars, has {current_bars}",
                location=f"features[tf={role}]",
            ))
    
    is_ready = not any(i.severity == ValidationSeverity.ERROR for i in issues)
    
    return PreEvaluationStatus(
        is_ready=is_ready,
        issues=issues,
        warmup_satisfied=warmup_satisfied,
    )


# =============================================================================
# Combined Validation
# =============================================================================

def validate_play_full(play: "Play") -> PlayValidationResult:
    """
    Run all validation gates on an Play.
    
    Combines:
    - Gate 8.0: Contract validation
    - Gate 8.1: Feature validation
    
    Args:
        play: Play to validate
        
    Returns:
        Combined PlayValidationResult
    """
    all_issues: list[ValidationIssue] = []
    
    # Gate 8.0: Contract
    contract_result = validate_play_contract(play)
    all_issues.extend(contract_result.issues)
    
    # Gate 8.1: Features (only if contract is valid)
    if contract_result.is_valid:
        feature_result = validate_play_features(play)
        all_issues.extend(feature_result.issues)
    
    is_valid = not any(i.severity == ValidationSeverity.ERROR for i in all_issues)
    
    return PlayValidationResult(
        is_valid=is_valid,
        issues=all_issues,
        hash=contract_result.hash,
    )


# =============================================================================
# Gate 8.3: Play → SystemConfig Adapter (DELETED - P1.2 Refactor)
# =============================================================================
# PlaySystemConfig and adapt_play_to_system_config have been deleted.
# Engine now accepts Play directly via create_engine_from_play().
# See: src/backtest/engine.py
# =============================================================================


# =============================================================================
# Gate 8.3: Play Signal Evaluator Interface
# =============================================================================

class SignalDecision(str, Enum):
    """Decision from signal evaluation."""
    NO_ACTION = "no_action"      # No signal generated
    ENTRY_LONG = "entry_long"    # Enter long position
    ENTRY_SHORT = "entry_short"  # Enter short position
    EXIT = "exit"                # Exit current position


@dataclass
class EvaluationResult:
    """Result of Play signal evaluation."""
    decision: SignalDecision
    reason: str = ""
    matched_rule_index: int | None = None

    # For entry signals
    stop_loss_price: float | None = None
    take_profit_price: float | None = None
    size_usdt: float | None = None

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "reason": self.reason,
            "matched_rule_index": self.matched_rule_index,
            "stop_loss_price": self.stop_loss_price,
            "take_profit_price": self.take_profit_price,
            "size_usdt": self.size_usdt,
        }


class PlaySignalEvaluator:
    """
    Evaluates Play blocks against snapshot state.

    Gate 8.3: Interface for deterministic signal evaluation.

    The evaluator:
    1. Uses StrategyBlocksExecutor to evaluate blocks
    2. Maps Intent to SignalDecision
    3. Computes SL/TP from risk model
    4. Returns EvaluationResult
    """

    def __init__(self, play: "Play"):
        """
        Initialize evaluator with Play.

        Args:
            play: The Play containing blocks

        Raises:
            ValueError: If Play is invalid
        """
        # Validate
        validation = validate_play_full(play)
        if not validation.is_valid:
            errors = [i.message for i in validation.errors]
            raise ValueError(f"Play validation failed: {'; '.join(errors)}")

        self.play = play
        self.warmup = compute_warmup_requirements(play)

        # Initialize blocks executor
        from .rules.strategy_blocks import StrategyBlocksExecutor
        self._blocks_executor = StrategyBlocksExecutor()

    def evaluate(
        self,
        snapshot: "SnapshotView",
        has_position: bool,
        position_side: str | None = None,
    ) -> EvaluationResult:
        """
        Evaluate blocks against current snapshot.

        Args:
            snapshot: Current RuntimeSnapshotView
            has_position: Whether there's an open position
            position_side: "long" or "short" if has_position

        Returns:
            EvaluationResult with decision and details
        """
        # Use blocks (primary DSL format)
        if self.play.blocks:
            return self._evaluate_blocks(snapshot, has_position, position_side)

        # No blocks defined
        return EvaluationResult(
            decision=SignalDecision.NO_ACTION,
            reason="No blocks defined in Play",
        )

    def _evaluate_blocks(
        self,
        snapshot: "SnapshotView",
        has_position: bool,
        position_side: str | None,
    ) -> EvaluationResult:
        """
        Evaluate blocks using StrategyBlocksExecutor.

        Args:
            snapshot: Current RuntimeSnapshotView
            has_position: Whether there's an open position
            position_side: "long" or "short" if has_position

        Returns:
            EvaluationResult with decision and details
        """
        # Execute all blocks
        intents = self._blocks_executor.execute(self.play.blocks, snapshot)

        # Map intents to decision
        for intent in intents:
            action = intent.action

            # Entry signals (only when no position)
            if action == "entry_long" and not has_position:
                if not self.play.position_policy.allows_long():
                    continue
                sl_price, tp_price = self._compute_sl_tp(snapshot, "long")
                return EvaluationResult(
                    decision=SignalDecision.ENTRY_LONG,
                    reason=f"Block emitted entry_long",
                    stop_loss_price=sl_price,
                    take_profit_price=tp_price,
                )

            elif action == "entry_short" and not has_position:
                if not self.play.position_policy.allows_short():
                    continue
                sl_price, tp_price = self._compute_sl_tp(snapshot, "short")
                return EvaluationResult(
                    decision=SignalDecision.ENTRY_SHORT,
                    reason=f"Block emitted entry_short",
                    stop_loss_price=sl_price,
                    take_profit_price=tp_price,
                )

            # Exit signals (only when has matching position)
            elif action == "exit_long" and has_position and position_side == "long":
                return EvaluationResult(
                    decision=SignalDecision.EXIT,
                    reason=f"Block emitted exit_long",
                )

            elif action == "exit_short" and has_position and position_side == "short":
                return EvaluationResult(
                    decision=SignalDecision.EXIT,
                    reason=f"Block emitted exit_short",
                )

            elif action == "exit_all" and has_position:
                return EvaluationResult(
                    decision=SignalDecision.EXIT,
                    reason=f"Block emitted exit_all",
                )

        return EvaluationResult(
            decision=SignalDecision.NO_ACTION,
            reason="No actionable intents from blocks",
        )

    def _get_snapshot_value(
        self,
        snapshot: "SnapshotView",
        key: str,
        tf_role: str = "exec",
    ) -> float | None:
        """
        Get a value from snapshot using the appropriate method.

        Args:
            snapshot: Runtime snapshot
            key: Feature key (e.g., "close", "atr_14")
            tf_role: TF role

        Returns:
            Value or None if not available
        """
        try:
            if hasattr(snapshot, 'get_feature'):
                return snapshot.get_feature(key, tf_role, 0)
            elif hasattr(snapshot, 'get'):
                return snapshot.get(key)
            return None
        except (KeyError, AttributeError):
            return None

    def _compute_sl_tp(
        self,
        snapshot: "SnapshotView",
        direction: str,
    ) -> tuple[float | None, float | None]:
        """
        Compute stop loss and take profit prices from risk model.

        Args:
            snapshot: Runtime snapshot
            direction: "long" or "short"

        Returns:
            Tuple of (stop_loss_price, take_profit_price)
        """
        risk_model = self.play.risk_model
        if risk_model is None:
            return None, None

        # Use close price as entry reference
        entry_price = self._get_snapshot_value(snapshot, "close", "exec")
        if entry_price is None:
            return None, None

        sl_price = None
        sl_distance = None

        # Compute stop loss
        sl_rule = risk_model.stop_loss
        if sl_rule.type.value == "atr_multiple":
            atr = self._get_snapshot_value(snapshot, sl_rule.atr_feature_id, "exec")
            if atr is not None:
                sl_distance = atr * sl_rule.value
                buffer = entry_price * (sl_rule.buffer_pct / 100.0)
                if direction == "long":
                    sl_price = entry_price - sl_distance - buffer
                else:
                    sl_price = entry_price + sl_distance + buffer
        elif sl_rule.type.value == "percent":
            sl_distance = entry_price * (sl_rule.value / 100.0)
            if direction == "long":
                sl_price = entry_price - sl_distance
            else:
                sl_price = entry_price + sl_distance
        elif sl_rule.type.value == "fixed_points":
            sl_distance = sl_rule.value
            if direction == "long":
                sl_price = entry_price - sl_distance
            else:
                sl_price = entry_price + sl_distance

        tp_price = None

        # Compute take profit
        tp_rule = risk_model.take_profit
        if tp_rule.type.value == "rr_ratio" and sl_distance is not None:
            tp_distance = sl_distance * tp_rule.value
            if direction == "long":
                tp_price = entry_price + tp_distance
            else:
                tp_price = entry_price - tp_distance
        elif tp_rule.type.value == "atr_multiple":
            atr = self._get_snapshot_value(snapshot, tp_rule.atr_feature_id, "exec")
            if atr is not None:
                tp_distance = atr * tp_rule.value
                if direction == "long":
                    tp_price = entry_price + tp_distance
                else:
                    tp_price = entry_price - tp_distance
        elif tp_rule.type.value == "percent":
            tp_distance = entry_price * (tp_rule.value / 100.0)
            if direction == "long":
                tp_price = entry_price + tp_distance
            else:
                tp_price = entry_price - tp_distance
        elif tp_rule.type.value == "fixed_points":
            tp_distance = tp_rule.value
            if direction == "long":
                tp_price = entry_price + tp_distance
            else:
                tp_price = entry_price - tp_distance

        return sl_price, tp_price

    def check_warmup_satisfied(self, bar_counts: dict[str, int]) -> bool:
        """
        Check if warmup requirements are satisfied.
        
        Args:
            bar_counts: Current bar count per TF role
            
        Returns:
            True if all warmup requirements are met
        """
        for role, required in self.warmup.warmup_by_role.items():
            current = bar_counts.get(role, 0)
            if current < required:
                return False
        return True


# Type hint for snapshot (avoids circular import)
if TYPE_CHECKING:
    from .runtime.snapshot_view import RuntimeSnapshotView as SnapshotView


