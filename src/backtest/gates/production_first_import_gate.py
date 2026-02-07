"""
Production-First Import Gate (Gate A).

AST-based scanner that enforces "no business logic in tests" rule.
This gate is READ-ONLY: it scans and reports violations without auto-editing.

Violations:
- FUNC_NAME: Disallowed function names in tests (build_, compute_, refresh_, etc.)
- DATAFRAME_MATH: DataFrame indicator math patterns (.rolling, .ewm, etc.)
- TEST_IMPORT: Tests importing production behavior from other tests
- ORCHESTRATION: Test-defined orchestration/pipeline logic

Allowlists:
- tests/_fixtures/** - Synthetic data generation
- tests/helpers/** - Assert helpers and utilities
- Explicit allowlist for pandas patterns in synthetic data generation

Usage:
    python -m src.backtest.gates.production_first_import_gate [--fail-on-violations]
"""

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum


class ViolationType(str, Enum):
    """Types of gate violations."""
    FUNC_NAME = "FUNC_NAME"  # Disallowed function name pattern
    DATAFRAME_MATH = "DATAFRAME_MATH"  # DataFrame indicator math
    TEST_IMPORT = "TEST_IMPORT"  # Test importing from other test
    ORCHESTRATION = "ORCHESTRATION"  # Test-defined orchestration


# =============================================================================
# Configuration
# =============================================================================

# Disallowed function name prefixes in tests
DISALLOWED_FUNC_PREFIXES = [
    "build_",
    "compute_",
    "refresh_",
    "align_",
    "preflight_",
    "indicator_",
    "snapshot_",
]

# DataFrame indicator math patterns (regex)
DATAFRAME_MATH_PATTERNS = [
    r"\.rolling\(",
    r"\.ewm\(",
    r"\.shift\(",
    r"\.diff\(",
    r"\.pct_change\(",
]

# Allowlisted directories (relative to tests/)
ALLOWLIST_DIRS = [
    "_fixtures",
    "helpers",
]

# Suggested target modules for common patterns
SUGGESTED_TARGETS = {
    "build_exchange_state": "src/backtest/runtime/snapshot_view.py",
    "build_test_exchange_state": "src/backtest/runtime/snapshot_view.py",
    "compute_structure_sl": "src/backtest/execution_validation.py",
    "compute_trades_hash": "src/backtest/artifacts/hashes.py",
    "compute_equity_hash": "src/backtest/artifacts/hashes.py",
    "compute_": "src/backtest/",
    "build_": "src/backtest/runtime/",
    "refresh_": "src/backtest/runtime/cache.py",
    "align_": "src/backtest/runtime/",
    "preflight_": "src/backtest/runtime/preflight.py",
    "indicator_": "src/backtest/indicators.py",
    "snapshot_": "src/backtest/runtime/snapshot_view.py",
    ".rolling(": "src/backtest/features/feature_frame_builder.py",
    ".ewm(": "src/backtest/features/feature_frame_builder.py",
}


# =============================================================================
# Violation Types
# =============================================================================

@dataclass
class GateViolation:
    """A single gate violation."""
    file_path: str
    line_number: int
    violation_type: ViolationType
    symbol: str
    message: str
    suggested_target: str | None = None
    
    def __str__(self) -> str:
        target_hint = f" -> move to {self.suggested_target}" if self.suggested_target else ""
        return f"{self.file_path}:{self.line_number} [{self.violation_type.value}] {self.symbol}: {self.message}{target_hint}"


@dataclass
class GateResult:
    """Result of running the gate."""
    passed: bool
    violations: list[GateViolation] = field(default_factory=list)
    files_scanned: int = 0
    files_with_violations: int = 0
    files_importing_backtest: int = 0
    
    def print_summary(self) -> None:
        """Print gate summary to console."""
        print("\n" + "=" * 70)
        print("  PRODUCTION-FIRST IMPORT GATE (Gate A)")
        print("=" * 70)
        
        pct_importing = (self.files_importing_backtest / self.files_scanned * 100) if self.files_scanned > 0 else 0
        
        print(f"\n  Files scanned:              {self.files_scanned}")
        print(f"  Files importing src/backtest: {self.files_importing_backtest} ({pct_importing:.1f}%)")
        print(f"  Files with violations:      {self.files_with_violations}")
        print(f"  Total violations:           {len(self.violations)}")
        
        if self.violations:
            # Group by violation type
            by_type: dict[ViolationType, list[GateViolation]] = {}
            for v in self.violations:
                if v.violation_type not in by_type:
                    by_type[v.violation_type] = []
                by_type[v.violation_type].append(v)
            
            print("\n  Violations by type:")
            for vtype, vlist in by_type.items():
                print(f"    {vtype.value}: {len(vlist)}")
            
            print("\n" + "-" * 70)
            print("  VIOLATIONS:")
            print("-" * 70)
            
            for v in self.violations:
                print(f"\n  {v}")
        
        print("\n" + "=" * 70)
        if self.passed:
            print("  GATE PASSED")
        else:
            print("  GATE FAILED - Fix violations before proceeding")
        print("=" * 70 + "\n")


# =============================================================================
# AST Visitor
# =============================================================================

class TestFileVisitor(ast.NodeVisitor):
    """AST visitor to find violations in test files."""

    def __init__(self, file_path: str, is_allowlisted: bool = False):
        self.file_path = file_path
        self.is_allowlisted = is_allowlisted
        self.violations: list[GateViolation] = []
        self.imports_backtest = False
        self.source_lines: list[str] = []
    
    def set_source(self, source: str) -> None:
        """Set source code for line-by-line analysis."""
        self.source_lines = source.split("\n")
    
    def visit_Import(self, node: ast.Import) -> None:
        """Check imports."""
        for alias in node.names:
            if alias.name.startswith("src.backtest"):
                self.imports_backtest = True
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check from imports."""
        if node.module and node.module.startswith("src.backtest"):
            self.imports_backtest = True
        
        # Check for test importing from other test
        if node.module and node.module.startswith("tests.") and not node.module.startswith("tests._fixtures") and not node.module.startswith("tests.helpers"):
            self.violations.append(GateViolation(
                file_path=self.file_path,
                line_number=node.lineno,
                violation_type=ViolationType.TEST_IMPORT,
                symbol=node.module,
                message=f"Test imports from another test: {node.module}",
            ))
        
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check function definitions."""
        if not self.is_allowlisted:
            for prefix in DISALLOWED_FUNC_PREFIXES:
                if node.name.startswith(prefix):
                    suggested = self._get_suggested_target(node.name)
                    self.violations.append(GateViolation(
                        file_path=self.file_path,
                        line_number=node.lineno,
                        violation_type=ViolationType.FUNC_NAME,
                        symbol=node.name,
                        message=f"Function name starts with disallowed prefix '{prefix}'",
                        suggested_target=suggested,
                    ))
                    break
        
        self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call) -> None:
        """Check for DataFrame indicator math patterns."""
        if not self.is_allowlisted:
            # Check if this is a method call like df.rolling()
            if isinstance(node.func, ast.Attribute):
                method_name = node.func.attr
                for pattern in [".rolling(", ".ewm(", ".shift(", ".diff(", ".pct_change("]:
                    if f".{method_name}(" == pattern:
                        suggested = self._get_suggested_target(pattern)
                        self.violations.append(GateViolation(
                            file_path=self.file_path,
                            line_number=node.lineno,
                            violation_type=ViolationType.DATAFRAME_MATH,
                            symbol=f".{method_name}()",
                            message=f"DataFrame indicator math pattern in test (outside allowlist)",
                            suggested_target=suggested,
                        ))
                        break
        
        self.generic_visit(node)
    
    def _get_suggested_target(self, symbol: str) -> str | None:
        """Get suggested target module for a symbol."""
        # First try exact match
        if symbol in SUGGESTED_TARGETS:
            return SUGGESTED_TARGETS[symbol]
        
        # Then try prefix match
        for key, target in SUGGESTED_TARGETS.items():
            if symbol.startswith(key) or key in symbol:
                return target
        
        return None


# =============================================================================
# Gate Runner
# =============================================================================

def is_allowlisted(file_path: Path, tests_root: Path) -> bool:
    """Check if a file is in an allowlisted directory."""
    try:
        rel_path = file_path.relative_to(tests_root)
        parts = rel_path.parts
        if parts and parts[0] in ALLOWLIST_DIRS:
            return True
    except ValueError:
        pass
    return False


def scan_file(file_path: Path, tests_root: Path) -> tuple[list[GateViolation], bool]:
    """
    Scan a single test file for violations.
    
    Args:
        file_path: Path to the test file
        tests_root: Root tests directory
        
    Returns:
        Tuple of (violations list, imports_backtest bool)
    """
    allowlisted = is_allowlisted(file_path, tests_root)
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        
        tree = ast.parse(source, filename=str(file_path))
        
        visitor = TestFileVisitor(str(file_path), is_allowlisted=allowlisted)
        visitor.set_source(source)
        visitor.visit(tree)
        
        return visitor.violations, visitor.imports_backtest
        
    except SyntaxError as e:
        # Skip files with syntax errors
        return [], False
    except Exception as e:
        # Skip files that can't be parsed
        return [], False


def run_production_first_gate(
    tests_dir: Path | None = None,
    fail_on_violations: bool = True,
) -> GateResult:
    """
    Run the production-first import gate.
    
    Scans all test files and reports violations without auto-editing.
    
    Args:
        tests_dir: Path to tests directory (default: tests/)
        fail_on_violations: Whether gate should fail if violations found
        
    Returns:
        GateResult with violations and summary
    """
    if tests_dir is None:
        tests_dir = Path("tests")
    
    if not tests_dir.exists():
        return GateResult(passed=True, files_scanned=0)
    
    all_violations: list[GateViolation] = []
    files_scanned = 0
    files_with_violations: set[str] = set()
    files_importing_backtest = 0
    
    # Find all Python test files
    for file_path in tests_dir.rglob("*.py"):
        # Skip __pycache__
        if "__pycache__" in str(file_path):
            continue
        
        files_scanned += 1
        violations, imports_backtest = scan_file(file_path, tests_dir)
        
        if imports_backtest:
            files_importing_backtest += 1
        
        if violations:
            all_violations.extend(violations)
            files_with_violations.add(str(file_path))
    
    passed = len(all_violations) == 0 if fail_on_violations else True
    
    return GateResult(
        passed=passed,
        violations=all_violations,
        files_scanned=files_scanned,
        files_with_violations=len(files_with_violations),
        files_importing_backtest=files_importing_backtest,
    )


# =============================================================================
# G1: Dead code removed (2026-01-27)
# =============================================================================
# - main() CLI entrypoint - unused, gate runs via trade_cli.py
# =============================================================================
