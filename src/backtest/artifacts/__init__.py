"""
Backtest artifacts module.

Provides lossless run recording for debugging and reproducibility:
- ManifestWriter: Writes run_manifest.json with config and metadata
- EventLogWriter: Streams events.jsonl during simulation
- EquityWriter: Optional equity_curve.csv export

ISOLATION RULE:
This module is wired ONLY from tools/entrypoints.
Core engine/sim/runtime must NOT import from artifacts.

Artifact version tracks the schema evolution:
- 0.1-dev: Initial development version
"""

from .manifest_writer import ManifestWriter
from .eventlog_writer import EventLogWriter
from .equity_writer import EquityWriter
from .artifact_standards import (
    STANDARD_FILES,
    REQUIRED_FILES,
    REQUIRED_TRADES_COLUMNS,
    REQUIRED_EQUITY_COLUMNS,
    REQUIRED_RESULT_FIELDS,
    ArtifactPathConfig,
    ArtifactValidationResult,
    validate_artifacts,
    validate_artifact_path_config,
    ResultsSummary,
    compute_results_summary,
    VersionMismatchError,
    MANIFEST_SCHEMA_VERSION,
)

# Current artifact schema version
ARTIFACT_VERSION = "1.0.0"

__all__ = [
    "ManifestWriter",
    "EventLogWriter",
    "EquityWriter",
    "ARTIFACT_VERSION",
    # Artifact standards (Phase 7.5)
    "STANDARD_FILES",
    "REQUIRED_FILES",
    "REQUIRED_TRADES_COLUMNS",
    "REQUIRED_EQUITY_COLUMNS",
    "REQUIRED_RESULT_FIELDS",
    "ArtifactPathConfig",
    "ArtifactValidationResult",
    "validate_artifacts",
    "validate_artifact_path_config",
    "ResultsSummary",
    "compute_results_summary",
    # Version safety (Phase 1 fixes)
    "VersionMismatchError",
    "MANIFEST_SCHEMA_VERSION",
]

