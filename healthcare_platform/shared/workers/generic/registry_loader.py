"""registry_loader — load and validate topic_registry.yaml.

Default path is <project_root>/config/topic_registry.yaml, resolved relative
to this module's location (four levels up: generic -> workers -> shared -> healthcare_platform -> project root).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)

# Valid archetype names (must match topic_registry.yaml Archetypes comment)
_VALID_ARCHETYPES = frozenset({
    "ADMIN_ADJUDICATION",
    "CLINICAL_ALERT",
    "CLINICAL_SCORE",
    "OPERATIONAL_ROUTING",
    "COMPLIANCE_VALIDATION",
    "FINANCIAL_CALCULATION",
    "DATA_ENRICHMENT",
})

# Valid error strategy values
_VALID_ERROR_STRATEGIES = frozenset({"fail_closed", "fail_safe"})

# Default registry path relative to project root
_DEFAULT_REGISTRY_RELPATH = Path("config") / "topic_registry.yaml"

# Project root: 4 levels up from this file
#   generic/ -> workers/ -> shared/ -> healthcare_platform/ -> <project_root>
_PROJECT_ROOT = Path(__file__).resolve().parents[4]


class RegistryValidationError(ValueError):
    """Raised when a topic_registry.yaml entry fails validation."""


def _default_registry_path() -> Path:
    """Return the default absolute path to topic_registry.yaml."""
    return _PROJECT_ROOT / _DEFAULT_REGISTRY_RELPATH


def _validate_entry(topic: str, entry: Dict[str, Any]) -> None:
    """Validate a single registry entry and raise RegistryValidationError on failure.

    Required fields (at least one DMN source must be present):
      archetype   — must be one of _VALID_ARCHETYPES
      dmn_key OR dmn_pipeline OR decisions — at least one required

    Optional but validated when present:
      error_strategy  — must be 'fail_closed' or 'fail_safe'
      dmn_pipeline    — each stage must have a 'key' or 'dmn_key' field
      timeout_ms      — must be a positive integer
    """
    if "archetype" not in entry:
        raise RegistryValidationError(
            f"Topic '{topic}' missing required field 'archetype'."
        )

    archetype = entry["archetype"]
    if archetype not in _VALID_ARCHETYPES:
        raise RegistryValidationError(
            f"Topic '{topic}' has invalid archetype '{archetype}'. "
            f"Must be one of: {sorted(_VALID_ARCHETYPES)}"
        )

    has_dmn_source = (
        "dmn_key" in entry
        or "dmn_pipeline" in entry
        or "decisions" in entry
    )
    if not has_dmn_source:
        raise RegistryValidationError(
            f"Topic '{topic}' must define 'dmn_key', 'dmn_pipeline', or 'decisions'."
        )

    if "dmn_category" not in entry:
        raise RegistryValidationError(
            f"Topic '{topic}' missing required field 'dmn_category'."
        )

    if "error_strategy" in entry:
        strategy = entry["error_strategy"]
        if strategy not in _VALID_ERROR_STRATEGIES:
            raise RegistryValidationError(
                f"Topic '{topic}' has invalid error_strategy '{strategy}'. "
                f"Must be one of: {sorted(_VALID_ERROR_STRATEGIES)}"
            )

    if "dmn_pipeline" in entry:
        for idx, stage in enumerate(entry["dmn_pipeline"]):
            if not isinstance(stage, dict):
                raise RegistryValidationError(
                    f"Topic '{topic}' dmn_pipeline[{idx}] must be a mapping, "
                    f"got {type(stage).__name__}."
                )
            if not stage.get("key") and not stage.get("dmn_key"):
                raise RegistryValidationError(
                    f"Topic '{topic}' dmn_pipeline[{idx}] missing 'key' or 'dmn_key'."
                )

    if "timeout_ms" in entry:
        timeout = entry["timeout_ms"]
        if not isinstance(timeout, int) or timeout <= 0:
            raise RegistryValidationError(
                f"Topic '{topic}' timeout_ms must be a positive integer, got '{timeout}'."
            )


def load_registry(registry_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Load and validate topic_registry.yaml.

    Args:
        registry_path: Absolute or relative path to the YAML file.
                       Defaults to <project_root>/config/topic_registry.yaml.

    Returns:
        Mapping of topic_name -> config dict for every validated entry.

    Raises:
        FileNotFoundError: If the registry file does not exist.
        yaml.YAMLError: If the file contains invalid YAML.
        RegistryValidationError: If any entry fails schema validation.
    """
    path = Path(registry_path) if registry_path else _default_registry_path()

    if not path.exists():
        raise FileNotFoundError(
            f"topic_registry.yaml not found at '{path}'. "
            "Set TOPIC_REGISTRY_PATH env variable or pass registry_path explicitly."
        )

    logger.info("Loading topic registry from '%s'", path)

    with path.open("r", encoding="utf-8") as fh:
        raw: Dict[str, Any] = yaml.safe_load(fh) or {}

    # Registry YAML has a top-level "topics:" key
    topics_section = raw.get("topics", raw)
    if not isinstance(topics_section, dict):
        raise RegistryValidationError(
            f"topic_registry.yaml must contain a 'topics' mapping, "
            f"got {type(topics_section).__name__}."
        )

    result: Dict[str, Dict[str, Any]] = {}
    errors: list[str] = []

    for topic, entry in topics_section.items():
        if not isinstance(entry, dict):
            errors.append(
                f"Topic '{topic}' config must be a mapping, got {type(entry).__name__}."
            )
            continue
        try:
            _validate_entry(topic, entry)
        except RegistryValidationError as exc:
            errors.append(str(exc))
            continue
        result[topic] = dict(entry)

    if errors:
        error_summary = "\n  - ".join(errors)
        raise RegistryValidationError(
            f"topic_registry.yaml validation failed ({len(errors)} error(s)):\n"
            f"  - {error_summary}"
        )

    logger.info("Loaded %d topic(s) from registry '%s'", len(result), path)
    return result


def get_topic_config(
    topic: str,
    registry_path: Optional[str] = None,
    _cache: Dict[str, Dict[str, Any]] = {},
) -> Dict[str, Any]:
    """Return the registry config for a single topic.

    Caches the full registry on first call to avoid re-reading the file.

    Args:
        topic: Camunda topic name (e.g. 'billing.validate_claim').
        registry_path: Override path to topic_registry.yaml.

    Returns:
        Config dict for the requested topic.

    Raises:
        KeyError: If the topic is not found in the registry.
        FileNotFoundError / RegistryValidationError: Propagated from load_registry.
    """
    cache_key = str(registry_path or "default")
    if cache_key not in _cache:
        _cache[cache_key] = load_registry(registry_path)

    registry = _cache[cache_key]
    if topic not in registry:
        raise KeyError(
            f"Topic '{topic}' not found in registry. "
            f"Available topics: {sorted(registry.keys())}"
        )
    return registry[topic]
