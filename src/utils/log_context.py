"""
Logging context propagation for distributed tracing and agent correlation.

Provides contextvars-based context that flows automatically through async/sync code
and can be propagated across process boundaries via serialization.

Usage:
    from src.utils.log_context import (
        LogContext,
        get_log_context,
        log_context_scope,
        new_run_context,
        new_tool_call_context,
    )
    
    # Start a new run (orchestrator/CLI session)
    with new_run_context(agent_id="strategy-bot-1") as ctx:
        # All logs within this scope will include run_id, agent_id
        
        # Execute a tool call with its own tool_call_id
        with new_tool_call_context("market_buy") as tool_ctx:
            result = some_tool_function()
    
    # For distributed execution, serialize context:
    ctx_dict = get_log_context().to_dict()
    # Pass ctx_dict to remote process, then restore:
    with log_context_scope(**ctx_dict):
        # Logs here will have the same run_id, trace_id, etc.
"""

from __future__ import annotations

import os
import socket
import threading
import uuid
from collections.abc import Generator
from contextvars import ContextVar
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


# =============================================================================
# Context Variables (thread-safe, async-safe)
# =============================================================================

_run_id: ContextVar[str | None] = ContextVar("run_id", default=None)
_agent_id: ContextVar[str | None] = ContextVar("agent_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_span_id: ContextVar[str | None] = ContextVar("span_id", default=None)
_parent_span_id: ContextVar[str | None] = ContextVar("parent_span_id", default=None)
_tool_call_id: ContextVar[str | None] = ContextVar("tool_call_id", default=None)
_tool_name: ContextVar[str | None] = ContextVar("tool_name", default=None)
_extra_context: ContextVar[dict[str, Any]] = ContextVar("extra_context", default={})


# =============================================================================
# Process-level context (set once per process)
# =============================================================================

_HOSTNAME: str = socket.gethostname()
_PID: int = os.getpid()


def _get_thread_id() -> int:
    """Get current thread ID."""
    return threading.get_ident()


def _generate_id() -> str:
    """Generate a short unique ID (first 12 chars of UUID4)."""
    return uuid.uuid4().hex[:12]


def _generate_trace_id() -> str:
    """Generate a trace ID (full UUID4 hex for distributed tracing)."""
    return uuid.uuid4().hex


# =============================================================================
# LogContext dataclass
# =============================================================================

@dataclass
class LogContext:
    """
    Immutable snapshot of the current logging context.

    Can be serialized to dict for cross-process propagation.
    """
    run_id: str | None = None
    agent_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    hostname: str = field(default_factory=lambda: _HOSTNAME)
    pid: int = field(default_factory=lambda: _PID)
    thread_id: int = field(default_factory=_get_thread_id)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for cross-process propagation."""
        return {
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "hostname": self.hostname,
            "pid": self.pid,
            "thread_id": self.thread_id,
            **self.extra,
        }
    
    def to_log_fields(self) -> dict[str, Any]:
        """
        Return only the fields that should be included in log events.
        
        Excludes None values and process-level fields that are added separately.
        """
        fields = {}
        if self.run_id:
            fields["run_id"] = self.run_id
        if self.agent_id:
            fields["agent_id"] = self.agent_id
        if self.trace_id:
            fields["trace_id"] = self.trace_id
        if self.span_id:
            fields["span_id"] = self.span_id
        if self.parent_span_id:
            fields["parent_span_id"] = self.parent_span_id
        if self.tool_call_id:
            fields["tool_call_id"] = self.tool_call_id
        if self.tool_name:
            fields["tool_name"] = self.tool_name
        fields["hostname"] = self.hostname
        fields["pid"] = self.pid
        fields["thread_id"] = self.thread_id
        if self.extra:
            fields.update(self.extra)
        return fields


# =============================================================================
# Context Access Functions
# =============================================================================

def get_log_context() -> LogContext:
    """
    Get the current logging context.
    
    Returns a LogContext snapshot with all current context values.
    """
    return LogContext(
        run_id=_run_id.get(),
        agent_id=_agent_id.get(),
        trace_id=_trace_id.get(),
        span_id=_span_id.get(),
        parent_span_id=_parent_span_id.get(),
        tool_call_id=_tool_call_id.get(),
        tool_name=_tool_name.get(),
        hostname=_HOSTNAME,
        pid=_PID,
        thread_id=_get_thread_id(),
        extra=_extra_context.get().copy(),
    )


def get_run_id() -> str | None:
    """Get current run ID."""
    return _run_id.get()


def get_agent_id() -> str | None:
    """Get current agent ID."""
    return _agent_id.get()


def get_trace_id() -> str | None:
    """Get current trace ID."""
    return _trace_id.get()


def get_tool_call_id() -> str | None:
    """Get current tool call ID."""
    return _tool_call_id.get()


# =============================================================================
# Context Managers
# =============================================================================

@contextmanager
def log_context_scope(
    run_id: str | None = None,
    agent_id: str | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
    parent_span_id: str | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    **extra: Any,
) -> Generator[LogContext, None, None]:
    """
    Context manager that sets logging context for a scope.
    
    Restores previous context on exit.
    
    Args:
        run_id: Run/session identifier
        agent_id: Agent identifier
        trace_id: Distributed trace ID
        span_id: Current span ID
        parent_span_id: Parent span ID
        tool_call_id: Tool call identifier
        tool_name: Name of the tool being executed
        **extra: Additional context fields
    
    Yields:
        LogContext snapshot of the active context
    """
    # Save current tokens
    tokens = []
    
    if run_id is not None:
        tokens.append(("run_id", _run_id.set(run_id)))
    if agent_id is not None:
        tokens.append(("agent_id", _agent_id.set(agent_id)))
    if trace_id is not None:
        tokens.append(("trace_id", _trace_id.set(trace_id)))
    if span_id is not None:
        tokens.append(("span_id", _span_id.set(span_id)))
    if parent_span_id is not None:
        tokens.append(("parent_span_id", _parent_span_id.set(parent_span_id)))
    if tool_call_id is not None:
        tokens.append(("tool_call_id", _tool_call_id.set(tool_call_id)))
    if tool_name is not None:
        tokens.append(("tool_name", _tool_name.set(tool_name)))
    if extra:
        old_extra = _extra_context.get()
        new_extra = {**old_extra, **extra}
        tokens.append(("extra_context", _extra_context.set(new_extra)))
    
    try:
        yield get_log_context()
    finally:
        # Restore previous values
        for name, token in tokens:
            if name == "run_id":
                _run_id.reset(token)
            elif name == "agent_id":
                _agent_id.reset(token)
            elif name == "trace_id":
                _trace_id.reset(token)
            elif name == "span_id":
                _span_id.reset(token)
            elif name == "parent_span_id":
                _parent_span_id.reset(token)
            elif name == "tool_call_id":
                _tool_call_id.reset(token)
            elif name == "tool_name":
                _tool_name.reset(token)
            elif name == "extra_context":
                _extra_context.reset(token)


@contextmanager
def new_run_context(
    run_id: str | None = None,
    agent_id: str | None = None,
    trace_id: str | None = None,
    **extra: Any,
) -> Generator[LogContext, None, None]:
    """
    Start a new run context (orchestrator/CLI session).
    
    Generates a new run_id and trace_id if not provided.
    
    Args:
        run_id: Optional run ID (generated if not provided)
        agent_id: Optional agent identifier
        trace_id: Optional trace ID (generated if not provided)
        **extra: Additional context fields
    
    Yields:
        LogContext with the new run context
    
    Example:
        with new_run_context(agent_id="strategy-bot") as ctx:
            print(f"Run ID: {ctx.run_id}")
            # All logs in this scope include run_id
    """
    _run_id_val = run_id or f"run-{_generate_id()}"
    _trace_id_val = trace_id or _generate_trace_id()
    _span_id_val = _generate_id()
    
    with log_context_scope(
        run_id=_run_id_val,
        agent_id=agent_id,
        trace_id=_trace_id_val,
        span_id=_span_id_val,
        **extra,
    ) as ctx:
        yield ctx


@contextmanager
def new_tool_call_context(
    tool_name: str,
    tool_call_id: str | None = None,
    **extra: Any,
) -> Generator[LogContext, None, None]:
    """
    Start a new tool call context within the current run.
    
    Generates a new tool_call_id if not provided.
    Creates a new span_id and sets parent_span_id to current span.
    
    Args:
        tool_name: Name of the tool being called
        tool_call_id: Optional tool call ID (generated if not provided)
        **extra: Additional context fields
    
    Yields:
        LogContext with the tool call context
    
    Example:
        with new_tool_call_context("market_buy") as ctx:
            print(f"Tool call ID: {ctx.tool_call_id}")
            result = market_buy_tool(...)
    """
    _tool_call_id_val = tool_call_id or f"tc-{_generate_id()}"
    
    # Create a new span, with current span as parent
    current_span = _span_id.get()
    new_span = _generate_id()
    
    with log_context_scope(
        tool_call_id=_tool_call_id_val,
        tool_name=tool_name,
        span_id=new_span,
        parent_span_id=current_span,
        **extra,
    ) as ctx:
        yield ctx


def set_agent_id(agent_id: str) -> None:
    """
    Set the agent ID for the current context.
    
    Use this when the agent ID becomes known after the run context is created.
    """
    _agent_id.set(agent_id)


def add_context_fields(**fields: Any) -> None:
    """
    Add extra fields to the current context.
    
    These fields will be included in all log events within the current scope.
    """
    current = _extra_context.get()
    _extra_context.set({**current, **fields})


# =============================================================================
# Utility for creating context from meta dict (agent/orchestrator use)
# =============================================================================

def context_from_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    """
    Extract context fields from a meta dictionary.
    
    Used by ToolRegistry and CLI to extract context from the meta parameter.
    
    Args:
        meta: Dictionary that may contain run_id, agent_id, trace_id, etc.
    
    Returns:
        Dictionary of context fields suitable for log_context_scope()
    """
    if not meta:
        return {}
    
    context_keys = {
        "run_id", "agent_id", "trace_id", "span_id",
        "parent_span_id", "tool_call_id", "tool_name",
    }
    
    return {k: v for k, v in meta.items() if k in context_keys and v is not None}

