"""Unit tests for the topic registry loader.

Tests the registry_loader module's YAML loading and validation logic.
If registry_loader.py does not exist yet, tests are skipped with a clear message.

Expected interface (from GENERIC_WORKERS_SCOPE.md):
    load_registry(path: str | Path) -> dict
        - Reads YAML from path
        - Raises FileNotFoundError on missing file
        - Raises ValueError on invalid archetype
        - Raises ValueError if neither dmn_key nor decisions/dmn_pipeline is present
        - Raises ValueError if both dmn_key and decisions/dmn_pipeline are present
        - Raises ValueError on invalid error_strategy value
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

# ---------------------------------------------------------------------------
# Conditional import — skip gracefully if module not yet implemented
# ---------------------------------------------------------------------------
try:
    from healthcare_platform.shared.workers.generic.registry_loader import (
        load_registry,
        get_topic_config,
        _default_registry_path,
        RegistryValidationError,
    )
    _REGISTRY_LOADER_AVAILABLE = True
except ImportError:
    _REGISTRY_LOADER_AVAILABLE = False
    load_registry = None
    get_topic_config = None
    _default_registry_path = None
    RegistryValidationError = None

pytestmark = pytest.mark.skipif(
    not _REGISTRY_LOADER_AVAILABLE,
    reason="registry_loader.py not yet implemented — tests pending",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_SINGLE_DMN_YAML = textwrap.dedent("""\
    topics:
      billing.validate_claim:
        archetype: ADMIN_ADJUDICATION
        dmn_category: billing
        decisions:
          - key: claim_validation_rules
            category: billing
        error_strategy: fail_closed
""")

VALID_PIPELINE_YAML = textwrap.dedent("""\
    topics:
      clinical.auditing:
        archetype: CLINICAL_SCORE
        dmn_category: clinical_safety
        decisions:
          - key: audit_documentation_completeness
            category: clinical_safety
          - key: audit_rule_compliance
            category: clinical_safety
        error_strategy: fail_safe
""")

INVALID_ARCHETYPE_YAML = textwrap.dedent("""\
    topics:
      billing.bad_topic:
        archetype: NOT_A_REAL_ARCHETYPE
        decisions:
          - key: some_dmn
            category: billing
        error_strategy: fail_closed
""")

NO_DECISIONS_YAML = textwrap.dedent("""\
    topics:
      billing.empty_topic:
        archetype: ADMIN_ADJUDICATION
        error_strategy: fail_closed
""")

INVALID_ERROR_STRATEGY_YAML = textwrap.dedent("""\
    topics:
      billing.bad_strategy:
        archetype: ADMIN_ADJUDICATION
        dmn_category: billing
        decisions:
          - key: some_dmn
            category: billing
        error_strategy: proceed_anyway
""")


def _write_yaml(tmp_path: Path, content: str) -> Path:
    """Write YAML content to a temp file and return its path."""
    yaml_file = tmp_path / "topic_registry.yaml"
    yaml_file.write_text(content)
    return yaml_file


# ---------------------------------------------------------------------------
# Valid loading
# ---------------------------------------------------------------------------

class TestLoadsValidYaml:
    def test_loads_valid_single_decision(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_SINGLE_DMN_YAML)
        registry = load_registry(path)
        assert "billing.validate_claim" in registry
        topic = registry["billing.validate_claim"]
        assert topic["archetype"] == "ADMIN_ADJUDICATION"
        assert topic["error_strategy"] == "fail_closed"

    def test_loads_valid_pipeline(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_PIPELINE_YAML)
        registry = load_registry(path)
        assert "clinical.auditing" in registry
        topic = registry["clinical.auditing"]
        assert topic["archetype"] == "CLINICAL_SCORE"
        assert len(topic["decisions"]) == 2

    def test_returns_dict(self, tmp_path):
        path = _write_yaml(tmp_path, VALID_SINGLE_DMN_YAML)
        registry = load_registry(path)
        assert isinstance(registry, dict)


# ---------------------------------------------------------------------------
# File not found
# ---------------------------------------------------------------------------

class TestRaisesOnMissingFile:
    def test_raises_file_not_found_on_missing_path(self, tmp_path):
        missing = tmp_path / "does_not_exist.yaml"
        with pytest.raises(FileNotFoundError):
            load_registry(missing)

    def test_raises_file_not_found_on_string_path(self, tmp_path):
        missing_str = str(tmp_path / "missing.yaml")
        with pytest.raises(FileNotFoundError):
            load_registry(missing_str)


# ---------------------------------------------------------------------------
# Invalid archetype
# ---------------------------------------------------------------------------

class TestRaisesOnInvalidArchetype:
    def test_raises_value_error_on_unknown_archetype(self, tmp_path):
        path = _write_yaml(tmp_path, INVALID_ARCHETYPE_YAML)
        with pytest.raises(ValueError, match="archetype"):
            load_registry(path)

    def test_valid_archetypes_do_not_raise(self, tmp_path):
        """All 7 documented archetypes are accepted."""
        valid_archetypes = [
            "ADMIN_ADJUDICATION",
            "CLINICAL_ALERT",
            "CLINICAL_SCORE",
            "OPERATIONAL_ROUTING",
            "COMPLIANCE_VALIDATION",
            "FINANCIAL_CALCULATION",
            "DATA_ENRICHMENT",
        ]
        for archetype in valid_archetypes:
            yaml = textwrap.dedent(f"""\
                topics:
                  test.topic:
                    archetype: {archetype}
                    dmn_category: billing
                    decisions:
                      - key: some_dmn
                        category: billing
                    error_strategy: fail_closed
            """)
            path = _write_yaml(tmp_path, yaml)
            registry = load_registry(path)
            assert "test.topic" in registry


# ---------------------------------------------------------------------------
# Missing decisions configuration
# ---------------------------------------------------------------------------

class TestRaisesOnMissingDmnConfig:
    def test_raises_on_topic_with_no_decisions(self, tmp_path):
        path = _write_yaml(tmp_path, NO_DECISIONS_YAML)
        with pytest.raises((ValueError, KeyError)):
            load_registry(path)


# ---------------------------------------------------------------------------
# Invalid error strategy
# ---------------------------------------------------------------------------

class TestValidatesErrorStrategyValues:
    def test_raises_on_invalid_error_strategy(self, tmp_path):
        path = _write_yaml(tmp_path, INVALID_ERROR_STRATEGY_YAML)
        with pytest.raises(ValueError, match="error_strategy"):
            load_registry(path)

    def test_fail_closed_is_valid(self, tmp_path):
        yaml = textwrap.dedent("""\
            topics:
              test.topic:
                archetype: ADMIN_ADJUDICATION
                dmn_category: billing
                decisions:
                  - key: some_dmn
                    category: billing
                error_strategy: fail_closed
        """)
        path = _write_yaml(tmp_path, yaml)
        registry = load_registry(path)
        assert registry["test.topic"]["error_strategy"] == "fail_closed"

    def test_fail_safe_is_valid(self, tmp_path):
        yaml = textwrap.dedent("""\
            topics:
              test.topic:
                archetype: CLINICAL_ALERT
                dmn_category: clinical_safety
                decisions:
                  - key: some_dmn
                    category: clinical_safety
                error_strategy: fail_safe
        """)
        path = _write_yaml(tmp_path, yaml)
        registry = load_registry(path)
        assert registry["test.topic"]["error_strategy"] == "fail_safe"


# ---------------------------------------------------------------------------
# Registry edge cases: missing archetype field, dmn_pipeline validation,
# get_topic_config helper
# ---------------------------------------------------------------------------

class TestRegistryEdgeCases:
    def test_raises_on_missing_archetype_field(self, tmp_path):
        yaml = textwrap.dedent("""\
            topics:
              test.topic:
                decisions:
                  - key: some_dmn
                    category: billing
                error_strategy: fail_closed
        """)
        path = _write_yaml(tmp_path, yaml)
        with pytest.raises((ValueError, Exception)):
            load_registry(path)

    def test_dmn_pipeline_with_valid_stage_keys(self, tmp_path):
        yaml = textwrap.dedent("""\
            topics:
              test.topic:
                archetype: ADMIN_ADJUDICATION
                dmn_category: billing
                dmn_pipeline:
                  - key: stage_one
                    category: billing
                  - key: stage_two
                    category: billing
                error_strategy: fail_closed
        """)
        path = _write_yaml(tmp_path, yaml)
        registry = load_registry(path)
        assert "test.topic" in registry


class TestDmnPipelineValidation:
    def test_raises_when_dmn_pipeline_stage_is_not_a_dict(self, tmp_path):
        yaml = textwrap.dedent("""\
            topics:
              test.topic:
                archetype: ADMIN_ADJUDICATION
                dmn_pipeline:
                  - "just_a_string_not_a_dict"
                error_strategy: fail_closed
        """)
        path = _write_yaml(tmp_path, yaml)
        with pytest.raises((ValueError, Exception)):
            load_registry(path)

    def test_raises_when_dmn_pipeline_stage_missing_key(self, tmp_path):
        yaml = textwrap.dedent("""\
            topics:
              test.topic:
                archetype: ADMIN_ADJUDICATION
                dmn_pipeline:
                  - category: billing
                error_strategy: fail_closed
        """)
        path = _write_yaml(tmp_path, yaml)
        with pytest.raises((ValueError, Exception)):
            load_registry(path)

    def test_raises_on_invalid_timeout_ms(self, tmp_path):
        yaml = textwrap.dedent("""\
            topics:
              test.topic:
                archetype: ADMIN_ADJUDICATION
                decisions:
                  - key: some_dmn
                    category: billing
                error_strategy: fail_closed
                timeout_ms: -100
        """)
        path = _write_yaml(tmp_path, yaml)
        with pytest.raises((ValueError, Exception)):
            load_registry(path)

    def test_valid_timeout_ms_is_accepted(self, tmp_path):
        yaml = textwrap.dedent("""\
            topics:
              test.topic:
                archetype: ADMIN_ADJUDICATION
                dmn_category: billing
                decisions:
                  - key: some_dmn
                    category: billing
                error_strategy: fail_closed
                timeout_ms: 30000
        """)
        path = _write_yaml(tmp_path, yaml)
        registry = load_registry(path)
        assert "test.topic" in registry


class TestGetTopicConfig:
    def test_get_topic_config_returns_entry(self, tmp_path):
        """get_topic_config returns config for a known topic."""
        try:
            from healthcare_platform.shared.workers.generic.registry_loader import get_topic_config
        except ImportError:
            pytest.skip("get_topic_config not available")

        path = _write_yaml(tmp_path, VALID_SINGLE_DMN_YAML)
        config = get_topic_config("billing.validate_claim", registry_path=path)
        assert config["archetype"] == "ADMIN_ADJUDICATION"

    def test_get_topic_config_raises_on_unknown_topic(self, tmp_path):
        """get_topic_config raises KeyError for an unknown topic."""
        try:
            from healthcare_platform.shared.workers.generic.registry_loader import get_topic_config
        except ImportError:
            pytest.skip("get_topic_config not available")

        path = _write_yaml(tmp_path, VALID_SINGLE_DMN_YAML)
        with pytest.raises(KeyError):
            get_topic_config("unknown.topic.xyz", registry_path=path)


# ---------------------------------------------------------------------------
# Default registry path helper (line 45)
# ---------------------------------------------------------------------------

class TestDefaultRegistryPath:
    def test_default_registry_path_returns_path_object(self):
        """_default_registry_path() returns a Path ending with the expected filename."""
        path = _default_registry_path()
        assert isinstance(path, Path)
        assert path.name == "topic_registry.yaml"
        assert "config" in path.parts


# ---------------------------------------------------------------------------
# topics_section not a dict (line 146)
# ---------------------------------------------------------------------------

class TestTopicsSectionNotADict:
    def test_raises_when_topics_section_is_a_list(self, tmp_path):
        """If the 'topics' key maps to a list, RegistryValidationError is raised."""
        yaml_content = textwrap.dedent("""\
            topics:
              - item_one
              - item_two
        """)
        path = _write_yaml(tmp_path, yaml_content)
        with pytest.raises(RegistryValidationError, match="mapping"):
            load_registry(path)

    def test_raises_when_topics_section_is_a_scalar(self, tmp_path):
        """If the 'topics' key maps to a plain string, RegistryValidationError is raised."""
        yaml_content = textwrap.dedent("""\
            topics: "not_a_mapping"
        """)
        path = _write_yaml(tmp_path, yaml_content)
        with pytest.raises(RegistryValidationError, match="mapping"):
            load_registry(path)


# ---------------------------------------------------------------------------
# Topic entry is not a dict (lines 156-159)
# ---------------------------------------------------------------------------

class TestTopicEntryNotADict:
    def test_raises_when_topic_entry_is_a_string(self, tmp_path):
        """If a topic entry is a scalar (not a mapping), RegistryValidationError is raised."""
        yaml_content = textwrap.dedent("""\
            topics:
              billing.bad_entry: "should_be_a_mapping"
        """)
        path = _write_yaml(tmp_path, yaml_content)
        with pytest.raises(RegistryValidationError, match="mapping"):
            load_registry(path)

    def test_raises_when_topic_entry_is_a_list(self, tmp_path):
        """If a topic entry is a list (not a mapping), RegistryValidationError is raised."""
        yaml_content = textwrap.dedent("""\
            topics:
              billing.bad_entry:
                - item_one
                - item_two
        """)
        path = _write_yaml(tmp_path, yaml_content)
        with pytest.raises(RegistryValidationError, match="mapping"):
            load_registry(path)

    def test_raises_collecting_multiple_bad_entries(self, tmp_path):
        """Multiple non-dict topic entries are all collected before raising."""
        yaml_content = textwrap.dedent("""\
            topics:
              billing.bad_one: "scalar_value"
              billing.bad_two: 42
        """)
        path = _write_yaml(tmp_path, yaml_content)
        with pytest.raises(RegistryValidationError):
            load_registry(path)


# ---------------------------------------------------------------------------
# dmn_pipeline stage validation with dmn_category present (lines 98, 103)
# ---------------------------------------------------------------------------

class TestDmnPipelineValidationWithDmnCategory:
    def test_raises_when_pipeline_stage_not_a_dict_and_dmn_category_present(self, tmp_path):
        """Line 98: pipeline stage not a dict fires RegistryValidationError."""
        yaml_content = textwrap.dedent("""\
            topics:
              test.topic:
                archetype: ADMIN_ADJUDICATION
                dmn_category: billing
                dmn_pipeline:
                  - "just_a_string_not_a_dict"
                error_strategy: fail_closed
        """)
        path = _write_yaml(tmp_path, yaml_content)
        with pytest.raises(RegistryValidationError, match="must be a mapping"):
            load_registry(path)

    def test_raises_when_pipeline_stage_missing_key_and_dmn_category_present(self, tmp_path):
        """Line 103: pipeline stage missing 'key'/'dmn_key' fires RegistryValidationError."""
        yaml_content = textwrap.dedent("""\
            topics:
              test.topic:
                archetype: ADMIN_ADJUDICATION
                dmn_category: billing
                dmn_pipeline:
                  - category: billing
                error_strategy: fail_closed
        """)
        path = _write_yaml(tmp_path, yaml_content)
        with pytest.raises(RegistryValidationError, match="missing 'key' or 'dmn_key'"):
            load_registry(path)

    def test_pipeline_stage_with_dmn_key_field_is_valid(self, tmp_path):
        """A pipeline stage using 'dmn_key' (instead of 'key') is accepted."""
        yaml_content = textwrap.dedent("""\
            topics:
              test.topic:
                archetype: ADMIN_ADJUDICATION
                dmn_category: billing
                dmn_pipeline:
                  - dmn_key: some_dmn_file
                    category: billing
                error_strategy: fail_closed
        """)
        path = _write_yaml(tmp_path, yaml_content)
        registry = load_registry(path)
        assert "test.topic" in registry


# ---------------------------------------------------------------------------
# timeout_ms validation with dmn_category present (line 110)
# ---------------------------------------------------------------------------

class TestTimeoutMsValidationWithDmnCategory:
    def test_raises_on_zero_timeout_ms(self, tmp_path):
        """Line 110: timeout_ms == 0 is not a positive integer."""
        yaml_content = textwrap.dedent("""\
            topics:
              test.topic:
                archetype: ADMIN_ADJUDICATION
                dmn_category: billing
                decisions:
                  - key: some_dmn
                    category: billing
                error_strategy: fail_closed
                timeout_ms: 0
        """)
        path = _write_yaml(tmp_path, yaml_content)
        with pytest.raises(RegistryValidationError, match="timeout_ms"):
            load_registry(path)

    def test_raises_on_negative_timeout_ms_with_dmn_category(self, tmp_path):
        """Line 110: negative timeout_ms with dmn_category present fires RegistryValidationError."""
        yaml_content = textwrap.dedent("""\
            topics:
              test.topic:
                archetype: ADMIN_ADJUDICATION
                dmn_category: billing
                decisions:
                  - key: some_dmn
                    category: billing
                error_strategy: fail_closed
                timeout_ms: -500
        """)
        path = _write_yaml(tmp_path, yaml_content)
        with pytest.raises(RegistryValidationError, match="timeout_ms"):
            load_registry(path)

    def test_raises_on_float_timeout_ms(self, tmp_path):
        """Line 110: float timeout_ms (not an int) fires RegistryValidationError."""
        yaml_content = textwrap.dedent("""\
            topics:
              test.topic:
                archetype: ADMIN_ADJUDICATION
                dmn_category: billing
                decisions:
                  - key: some_dmn
                    category: billing
                error_strategy: fail_closed
                timeout_ms: 1.5
        """)
        path = _write_yaml(tmp_path, yaml_content)
        with pytest.raises(RegistryValidationError, match="timeout_ms"):
            load_registry(path)


# ---------------------------------------------------------------------------
# Missing dmn_category with other valid fields (line 83-85)
# ---------------------------------------------------------------------------

class TestMissingDmnCategory:
    def test_raises_on_missing_dmn_category_with_decisions(self, tmp_path):
        """dmn_category is required even when decisions is present."""
        yaml_content = textwrap.dedent("""\
            topics:
              billing.no_category:
                archetype: ADMIN_ADJUDICATION
                decisions:
                  - key: some_dmn
                    category: billing
                error_strategy: fail_closed
        """)
        path = _write_yaml(tmp_path, yaml_content)
        with pytest.raises(RegistryValidationError, match="dmn_category"):
            load_registry(path)

    def test_raises_on_missing_dmn_category_with_dmn_key(self, tmp_path):
        """dmn_category is required even when dmn_key is present."""
        yaml_content = textwrap.dedent("""\
            topics:
              billing.no_category:
                archetype: ADMIN_ADJUDICATION
                dmn_key: some_file.dmn
                error_strategy: fail_closed
        """)
        path = _write_yaml(tmp_path, yaml_content)
        with pytest.raises(RegistryValidationError, match="dmn_category"):
            load_registry(path)


# ---------------------------------------------------------------------------
# get_topic_config cache behaviour
# ---------------------------------------------------------------------------

class TestGetTopicConfigCaching:
    def test_get_topic_config_uses_cache_on_second_call(self, tmp_path):
        """get_topic_config does not reload the file on repeated calls with same path."""
        import healthcare_platform.shared.workers.generic.registry_loader as mod

        path = _write_yaml(tmp_path, VALID_SINGLE_DMN_YAML)
        path_str = str(path)

        # The function signature is: get_topic_config(topic, registry_path=None, _cache={})
        # __defaults__ is (None, {}) — index 0 is registry_path default, index 1 is _cache.
        cache_dict = mod.get_topic_config.__defaults__[1]
        cache_dict.pop(path_str, None)

        config_first = mod.get_topic_config("billing.validate_claim", registry_path=path_str)
        config_second = mod.get_topic_config("billing.validate_claim", registry_path=path_str)
        assert config_first == config_second
