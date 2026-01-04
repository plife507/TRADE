"""
Audit tools for backtest validation.

This module consolidates all audit functionality for backtest validation:
- Math parity audits (indicator computation vs pandas_ta)
- Snapshot plumbing parity audits (RuntimeSnapshotView correctness)
- Toolkit contract audits (indicator registry validation)
- Artifact parity verification (output consistency checks)
"""

from .audit_in_memory_parity import (
    run_in_memory_parity_for_play,
    audit_in_memory_parity_from_feeds,
    InMemoryParityResult,
    ColumnParityResult,
)
from .audit_math_parity import (
    audit_math_parity_from_snapshots,
    MathParityAuditResult,
    ColumnAuditResult,
)
from .audit_snapshot_plumbing_parity import (
    audit_snapshot_plumbing_parity,
    PlumbingParityResult,
    PlumbingAuditCallback,
)
from .toolkit_contract_audit import (
    run_toolkit_contract_audit,
    ToolkitAuditResult,
    IndicatorAuditResult,
)
from .artifact_parity_verifier import (
    verify_artifact_parity,
    verify_run_parity,
    ArtifactParityResult,
    RunParityResult,
)

__all__ = [
    # In-memory parity
    "run_in_memory_parity_for_play",
    "audit_in_memory_parity_from_feeds",
    "InMemoryParityResult",
    "ColumnParityResult",
    # Math parity
    "audit_math_parity_from_snapshots",
    "MathParityAuditResult",
    "ColumnAuditResult",
    # Snapshot plumbing
    "audit_snapshot_plumbing_parity",
    "PlumbingParityResult",
    "PlumbingAuditCallback",
    # Toolkit contract
    "run_toolkit_contract_audit",
    "ToolkitAuditResult",
    "IndicatorAuditResult",
    # Artifact parity
    "verify_artifact_parity",
    "verify_run_parity",
    "ArtifactParityResult",
    "RunParityResult",
]

