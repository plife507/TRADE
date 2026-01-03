"""
Structure registry for incremental detectors.

Provides:
- STRUCTURE_REGISTRY: Global registry of detector classes by name
- register_structure: Decorator to register detector classes
- get_structure_info: Get metadata about a registered structure
- list_structure_types: List all registered structure type names

The registry enables dynamic discovery and validation of structure types.
Detectors are registered at import time via the @register_structure decorator.

Example:
    @register_structure("my_detector")
    class MyDetector(BaseIncrementalDetector):
        REQUIRED_PARAMS = ["period"]
        OPTIONAL_PARAMS = {"threshold": 0.5}
        DEPENDS_ON = []
        ...

    # Later:
    info = get_structure_info("my_detector")
    # Returns: {
    #     "required_params": ["period"],
    #     "optional_params": {"threshold": 0.5},
    #     "depends_on": [],
    #     "output_keys": ["value"]  # if detector instance available
    # }

See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .base import BaseIncrementalDetector

# Global registry: maps structure type name to detector class
STRUCTURE_REGISTRY: dict[str, type["BaseIncrementalDetector"]] = {}


def register_structure(name: str):
    """
    Decorator to register a structure detector class.

    Validates that the class has required class attributes before
    registration. Raises TypeError if validation fails.

    Args:
        name: The structure type name (e.g., "swing", "trend", "zone").

    Returns:
        Decorator function.

    Raises:
        TypeError: If class doesn't inherit from BaseIncrementalDetector.
        TypeError: If class is missing required class attributes.
        ValueError: If name is already registered.

    Example:
        @register_structure("swing")
        class SwingDetector(BaseIncrementalDetector):
            REQUIRED_PARAMS = ["left", "right"]
            OPTIONAL_PARAMS = {}
            DEPENDS_ON = []
            ...
    """

    def decorator(cls: type["BaseIncrementalDetector"]) -> type["BaseIncrementalDetector"]:
        # Import here to avoid circular import
        from .base import BaseIncrementalDetector

        # Validate inheritance
        if not issubclass(cls, BaseIncrementalDetector):
            raise TypeError(
                f"Cannot register '{name}': class '{cls.__name__}' must inherit from BaseIncrementalDetector\n"
                f"\n"
                f"Fix:\n"
                f"  from src.backtest.incremental.base import BaseIncrementalDetector\n"
                f"\n"
                f"  @register_structure('{name}')\n"
                f"  class {cls.__name__}(BaseIncrementalDetector):\n"
                f"      ..."
            )

        # Validate required class attributes exist
        required_attrs = ["REQUIRED_PARAMS", "OPTIONAL_PARAMS", "DEPENDS_ON"]
        missing_attrs = []
        for attr in required_attrs:
            if not hasattr(cls, attr):
                missing_attrs.append(attr)

        if missing_attrs:
            attr_lines = "\n".join(
                f"    {attr} = []  # or {{}}" for attr in missing_attrs
            )
            raise TypeError(
                f"Cannot register '{name}': class '{cls.__name__}' missing class attributes: {missing_attrs}\n"
                f"\n"
                f"Fix: Add to class definition:\n"
                f"{attr_lines}"
            )

        # Validate types of class attributes
        if not isinstance(cls.REQUIRED_PARAMS, list):
            raise TypeError(
                f"Cannot register '{name}': REQUIRED_PARAMS must be a list, got {type(cls.REQUIRED_PARAMS).__name__}\n"
                f"\n"
                f"Fix: REQUIRED_PARAMS = ['param1', 'param2']"
            )

        if not isinstance(cls.OPTIONAL_PARAMS, dict):
            raise TypeError(
                f"Cannot register '{name}': OPTIONAL_PARAMS must be a dict, got {type(cls.OPTIONAL_PARAMS).__name__}\n"
                f"\n"
                f"Fix: OPTIONAL_PARAMS = {{'param': default_value}}"
            )

        if not isinstance(cls.DEPENDS_ON, list):
            raise TypeError(
                f"Cannot register '{name}': DEPENDS_ON must be a list, got {type(cls.DEPENDS_ON).__name__}\n"
                f"\n"
                f"Fix: DEPENDS_ON = ['swing', 'other_dep']"
            )

        # Check for duplicate registration
        if name in STRUCTURE_REGISTRY:
            existing_cls = STRUCTURE_REGISTRY[name]
            raise ValueError(
                f"Cannot register '{name}': already registered to '{existing_cls.__name__}'\n"
                f"\n"
                f"Fix: Use a different name or unregister the existing class first."
            )

        # Register the class
        STRUCTURE_REGISTRY[name] = cls

        return cls

    return decorator


def get_structure_info(name: str) -> dict[str, Any]:
    """
    Get metadata about a registered structure type.

    Returns information about required/optional params, dependencies,
    and output keys (if determinable without instantiation).

    Args:
        name: The structure type name.

    Returns:
        Dict with keys:
            - required_params: list[str]
            - optional_params: dict[str, Any]
            - depends_on: list[str]
            - class_name: str
            - docstring: str | None

    Raises:
        KeyError: If name is not registered, with available types listed.

    Example:
        >>> info = get_structure_info("swing")
        >>> info["required_params"]
        ["left", "right"]
    """
    if name not in STRUCTURE_REGISTRY:
        available = list(STRUCTURE_REGISTRY.keys())
        available_str = ", ".join(available) if available else "(none registered)"
        raise KeyError(
            f"Structure type '{name}' not registered\n"
            f"\n"
            f"Available types: {available_str}\n"
            f"\n"
            f"Fix: Use one of the available types, or register a new detector with:\n"
            f"  @register_structure('{name}')\n"
            f"  class MyDetector(BaseIncrementalDetector):\n"
            f"      ..."
        )

    cls = STRUCTURE_REGISTRY[name]

    return {
        "required_params": list(cls.REQUIRED_PARAMS),
        "optional_params": dict(cls.OPTIONAL_PARAMS),
        "depends_on": list(cls.DEPENDS_ON),
        "class_name": cls.__name__,
        "docstring": cls.__doc__,
    }


def list_structure_types() -> list[str]:
    """
    List all registered structure type names.

    Returns:
        Sorted list of registered structure type names.

    Example:
        >>> list_structure_types()
        ["fibonacci", "rolling_window", "swing", "trend", "zone"]
    """
    return sorted(STRUCTURE_REGISTRY.keys())


def unregister_structure(name: str) -> bool:
    """
    Remove a structure type from the registry.

    Primarily useful for testing to clean up after test registrations.

    Args:
        name: The structure type name to unregister.

    Returns:
        True if the structure was removed, False if it wasn't registered.
    """
    if name in STRUCTURE_REGISTRY:
        del STRUCTURE_REGISTRY[name]
        return True
    return False
