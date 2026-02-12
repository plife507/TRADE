"""
Shared protocols for DSL expression evaluation.

Provides Protocol classes to avoid circular imports between evaluation modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ..dsl_nodes import Expr
from ..types import EvalResult

if TYPE_CHECKING:
    from ...runtime.snapshot_view import RuntimeSnapshotView


class ExprEvaluatorProtocol(Protocol):
    """Protocol for expression evaluator to avoid circular imports."""

    def evaluate(self, expr: Expr, snapshot: "RuntimeSnapshotView") -> EvalResult: ...
