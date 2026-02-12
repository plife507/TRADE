"""
Tool Registry for TRADE Bot Orchestrator.

Provides a unified interface for discovering, describing, and executing tools.
Designed for use by AI agents, strategy bots, or automated systems.

NO LEGACY FALLBACKS - Forward coding only.

Usage:
    from src.tools.tool_registry import ToolRegistry

    registry = ToolRegistry()

    # List all available tools
    tools = registry.list_tools()

    # Get tool info (for AI/LLM function calling)
    info = registry.get_tool_info("market_buy")

    # Execute a tool
    result = registry.execute("market_buy", symbol="SOLUSDT", usd_amount=100)
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
import time

from .shared import ToolResult
from .specs import (
    ALL_SPECS,
    ALL_IMPORTS,
    TRADING_ENV_PARAM,
)


@dataclass
class ToolSpec:
    """Specification for a registered tool."""
    name: str
    function: Callable
    description: str
    category: str
    parameters: dict[str, dict[str, Any]] = field(default_factory=dict)
    required: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/API use."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": self.parameters,
            "required": self.required,
        }


class ToolRegistry:
    """
    Central registry for all trading tools.

    Enables dynamic tool discovery and execution for orchestrators/bots.
    """

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}
        self._register_all_tools()

    def _register_all_tools(self):
        """
        Register all available tools from specs modules.

        Pattern: Specs define metadata, imports provide actual functions.
        This allows tools to be discovered dynamically without hardcoding.
        """
        # Load all function imports from each category
        all_functions = {}
        for category, get_imports_fn in ALL_IMPORTS.items():
            all_functions.update(get_imports_fn())

        # Register each spec (skips functions that aren't available)
        for spec in ALL_SPECS:
            name = spec["name"]
            if name not in all_functions:
                continue  # Skip if function not available

            self._register(
                name=name,
                function=all_functions[name],
                description=spec["description"],
                category=spec["category"],
                parameters=spec.get("parameters", {}),
                required=spec.get("required", []),
            )

    def _register(
        self,
        name: str,
        function: Callable,
        description: str,
        category: str,
        parameters: dict[str, dict[str, Any]],
        required: list[str],
    ):
        """Register a tool."""
        self._tools[name] = ToolSpec(
            name=name,
            function=function,
            description=description,
            category=category,
            parameters=parameters,
            required=required,
        )

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def list_tools(self, category: str | None = None) -> list[str]:
        """
        List all available tool names.

        Args:
            category: Filter by category prefix (e.g., "orders", "positions")
        """
        if category:
            return [name for name, spec in self._tools.items()
                    if spec.category.startswith(category)]
        return list(self._tools.keys())

    def list_categories(self) -> list[str]:
        """List all unique categories."""
        return sorted(set(spec.category for spec in self._tools.values()))

    def get_tool_info(self, name: str) -> dict[str, Any] | None:
        """
        Get tool specification for AI/LLM function calling.

        Returns dict compatible with OpenAI function calling format.
        """
        spec = self._tools.get(name)
        if not spec:
            return None
        return spec.to_dict()

    def get_all_tools_info(self, category: str | None = None) -> list[dict[str, Any]]:
        """Get all tool specifications (for AI agent initialization)."""
        tools = []
        for name, spec in self._tools.items():
            if category and not spec.category.startswith(category):
                continue
            tools.append(spec.to_dict())
        return tools

    def execute(self, name: str, *, meta: dict[str, Any] | None = None, **kwargs) -> ToolResult:
        """
        Execute a tool by name with arguments.

        Validates required parameters, sets up logging context, and executes the tool
        with structured event tracking (tool.call.start/end/error).

        Args:
            name: Tool name
            meta: Optional metadata dict with context (run_id, agent_id, trace_id, tool_call_id)
            **kwargs: Tool arguments

        Returns:
            ToolResult from the tool execution

        Example:
            result = registry.execute("market_buy", symbol="SOLUSDT", usd_amount=100)

            # With agent context:
            result = registry.execute(
                "market_buy",
                symbol="SOLUSDT",
                usd_amount=100,
                meta={"run_id": "run-abc123", "agent_id": "strategy-bot"}
            )
        """
        spec = self._tools.get(name)
        if not spec:
            return ToolResult(success=False, error=f"Unknown tool: {name}")

        # Validate required parameters before execution
        missing = [p for p in spec.required if p not in kwargs]
        if missing:
            return ToolResult(
                success=False,
                error=f"Missing required parameters: {', '.join(missing)}"
            )

        # Import logging utilities
        from ..utils.logger import get_logger, redact_dict
        from ..utils.log_context import (
            new_tool_call_context,
            context_from_meta,
            log_context_scope,
        )

        logger = get_logger()
        meta = meta or {}

        # Extract context from meta and set up tool call context
        ctx_fields = context_from_meta(meta)
        tool_call_id = meta.get("tool_call_id") or meta.get("call_id")

        # Redact args for logging
        safe_args = redact_dict(kwargs)
        safe_meta = redact_dict(meta)

        # Execute within a tool call context scope
        with new_tool_call_context(name, tool_call_id=tool_call_id) as ctx:
            # Apply any additional context from meta
            if ctx_fields:
                with log_context_scope(**ctx_fields):
                    return self._execute_tool_with_logging(
                        spec, name, ctx.tool_call_id, safe_args, safe_meta, logger, kwargs
                    )
            else:
                return self._execute_tool_with_logging(
                    spec, name, ctx.tool_call_id, safe_args, safe_meta, logger, kwargs
                )

    def _execute_tool_with_logging(
        self,
        spec: ToolSpec,
        name: str,
        tool_call_id: str | None,
        safe_args: dict[str, Any],
        safe_meta: dict[str, Any],
        logger,
        kwargs: dict[str, Any],
    ) -> ToolResult:
        """Execute a tool with structured event logging."""
        started = time.perf_counter()

        # Emit tool.call.start event
        logger.event(
            "tool.call.start",
            component="tool_registry",
            tool_name=name,
            category=spec.category,
            args=safe_args,
            meta=safe_meta,
        )

        try:
            result = spec.function(**kwargs)
            elapsed_ms = (time.perf_counter() - started) * 1000.0

            # Emit tool.call.end event
            logger.event(
                "tool.call.end",
                component="tool_registry",
                tool_name=name,
                success=getattr(result, 'success', None),
                elapsed_ms=elapsed_ms,
                message=getattr(result, 'message', None),
                source=getattr(result, 'source', None),
            )
            return result

        except Exception as e:
            elapsed_ms = (time.perf_counter() - started) * 1000.0

            # Emit tool.call.error event
            logger.event(
                "tool.call.error",
                level="ERROR",
                component="tool_registry",
                tool_name=name,
                elapsed_ms=elapsed_ms,
                error=str(e),
                error_type=type(e).__name__,
            )
            return ToolResult(success=False, error=f"Tool execution failed: {str(e)}")

    def execute_batch(self, actions: list[dict[str, Any]]) -> list[ToolResult]:
        """
        Execute multiple tools in sequence.

        Args:
            actions: List of {"tool": "name", "args": {...}} dicts

        Returns:
            List of ToolResults
        """
        results = []
        for action in actions:
            tool_name = action.get("tool", "")
            args = action.get("args", {})
            result = self.execute(tool_name, **args)
            results.append(result)

            # Stop on critical failure if specified
            if not result.success and action.get("stop_on_fail", False):
                break

        return results


# Singleton instance for convenience
_registry: ToolRegistry | None = None

def get_registry() -> ToolRegistry:
    """Get the global tool registry instance."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
