"""
Backtest artifacts module.

Provides artifact standards, validation, and parquet utilities
for run recording, debugging, and reproducibility.

ISOLATION RULE:
This module is wired ONLY from tools/entrypoints.
Core engine/sim/runtime must NOT import from artifacts.
"""

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
)
from .parquet_writer import (
    write_parquet,
    read_parquet,
    compare_csv_parquet,
)

# Current artifact schema version
ARTIFACT_VERSION = "1.0.0"

__all__ = [
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
    # Parquet utilities
    "write_parquet",
    "read_parquet",
    "compare_csv_parquet",
]

