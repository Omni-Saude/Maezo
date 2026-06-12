"""End-to-end tests for the contract extraction DMN generation pipeline."""
import subprocess
import uuid
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

import pytest

from healthcare_platform.contract_extraction.dmn_generator import DMNGenerator
from healthcare_platform.contract_extraction.tenant_file_manager import TenantFileManager
from healthcare_platform.contract_extraction.validators import validate_rule

DMN_NS = "https://www.omg.org/spec/DMN/20191111/MODEL/"


def _mock_rule(
    archetype: str,
    category: str,
    rule_definition: dict,
    version: str = "1.0.0",
):
    rule = MagicMock()
    rule.id = str(uuid.uuid4())
    rule.payer_id = "payer_test_001"
    rule.tenant_id = "tenant_test"
    arch_mock = MagicMock()
    arch_mock.value = archetype
    rule.archetype = arch_mock
    cat_mock = MagicMock()
    cat_mock.value = category
    rule.category = cat_mock
    rule.rule_definition = rule_definition
    rule.version = version
    return rule


def _xmllint_valid(xml: str) -> bool:
    result = subprocess.run(
        ["xmllint", "--noout", "-"],
        input=xml.encode("utf-8"),
        capture_output=True,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# T1-T8: Parametrized archetype tests
# ---------------------------------------------------------------------------
_ARCHETYPE_PARAMS = [
    (
        "PRICING",
        "PRICING",
        {
            "procedure_code": {"operator": "eq", "value": "99.01"},
            "payer_id": {"operator": "eq", "value": "P1"},
            "quantity": {"operator": "gte", "value": 1},
            "output_unit_price": 100.0,
            "output_total_price": 100.0,
            "output_currency": "BRL",
        },
    ),
    (
        "LOOKUP",
        "LOOKUP",
        {
            "material_code": {"operator": "eq", "value": "MAT-001"},
            "supplier": {"operator": "eq", "value": "SUP-A"},
            "unit_price": {"operator": "eq", "value": 500},
            "output_approved": True,
            "output_max_price": 600.0,
            "output_requires_auth": False,
            "output_justification": "Within limit",
        },
    ),
    (
        "BUNDLING",
        "BUNDLE",
        {
            "primary_code": {"operator": "eq", "value": "03.05"},
            "secondary_code": {"operator": "eq", "value": "03.06"},
            "same_act": {"operator": "eq", "value": True},
            "output_is_bundled": True,
            "output_bundle_price": 800.0,
            "output_bundle_code": "B-001",
        },
    ),
    (
        "AUTHORIZATION",
        "AUTHORIZATION",
        {
            "procedure_code": {"operator": "eq", "value": "04.09"},
            "amount": {"operator": "gte", "value": 5000},
            "payer_id": {"operator": "eq", "value": "SES"},
            "output_requires_auth": True,
            "output_auth_type": "SUPERVISOR",
            "output_urgency_level": "HIGH",
        },
    ),
    (
        "ROUTING",
        "ROUTING",
        {"output_route": "cardiology_pathway"},
    ),
    (
        "WHITELIST",
        "WHITELIST",
        {
            "code": {"operator": "eq", "value": "WL-001"},
            "output_authorized": True,
            "output_item_name": "Stent",
            "output_reference_table": "SIGTAP",
        },
    ),
    (
        "OPME",
        "OPME",
        {"output_approved": True},
    ),
    (
        "DISCOUNT",
        "DISCOUNT",
        {"output_discount_pct": 5.0},
    ),
]


@pytest.mark.parametrize(
    "archetype,category,rule_definition",
    _ARCHETYPE_PARAMS,
    ids=[p[0] for p in _ARCHETYPE_PARAMS],
)
class TestArchetypeE2E:
    """T1-T8: Each archetype generates valid DMN XML and saves correctly."""

    def test_generate_and_save(
        self, archetype, category, rule_definition, tmp_path
    ):
        rule = _mock_rule(archetype, category, rule_definition)

        # Generate XML string
        gen = DMNGenerator()
        xml = gen.generate(rule)
        assert _xmllint_valid(xml), f"xmllint failed for {archetype}"

        # Generate and save via file manager
        fm = TenantFileManager(base_path=tmp_path)
        gen_with_fm = DMNGenerator(file_manager=fm)
        path = gen_with_fm.generate_and_save(rule, "tenant-e2e")
        assert path.exists()

        # Read back and parse
        content = path.read_text(encoding="utf-8")
        assert _xmllint_valid(content)

        root = ET.fromstring(content)
        ns = {"dmn": DMN_NS}
        decisions = root.findall(".//dmn:decision", ns)
        assert len(decisions) >= 1, f"No <decision> for {archetype}"

        tables = root.findall(".//dmn:decisionTable", ns)
        assert len(tables) >= 1, f"No <decisionTable> for {archetype}"

        rules = root.findall(".//dmn:rule", ns)
        assert len(rules) >= 1, f"No <rule> elements for {archetype}"


# ---------------------------------------------------------------------------
# T9: Multi-tenant isolation
# ---------------------------------------------------------------------------
class TestMultiTenantIsolation:
    def test_tenant_files_in_separate_dirs(self, tmp_path):
        fm = TenantFileManager(base_path=tmp_path)
        gen = DMNGenerator(file_manager=fm)

        rule_a = _mock_rule(
            "PRICING",
            "PRICING",
            {
                "procedure_code": {"operator": "eq", "value": "99.01"},
                "payer_id": {"operator": "eq", "value": "P1"},
                "quantity": {"operator": "gte", "value": 1},
                "output_unit_price": 100.0,
                "output_total_price": 100.0,
                "output_currency": "BRL",
            },
        )
        rule_b = _mock_rule(
            "PRICING",
            "PRICING",
            {
                "procedure_code": {"operator": "eq", "value": "99.02"},
                "payer_id": {"operator": "eq", "value": "P2"},
                "quantity": {"operator": "gte", "value": 2},
                "output_unit_price": 200.0,
                "output_total_price": 400.0,
                "output_currency": "BRL",
            },
        )

        path_a = gen.generate_and_save(rule_a, "tenant-a")
        path_b = gen.generate_and_save(rule_b, "tenant-b")

        # Different directories
        assert path_a.parent != path_b.parent
        assert "tenant-a" in str(path_a)
        assert "tenant-b" in str(path_b)

        # Independently readable
        content_a = path_a.read_text(encoding="utf-8")
        content_b = path_b.read_text(encoding="utf-8")
        assert _xmllint_valid(content_a)
        assert _xmllint_valid(content_b)


# ---------------------------------------------------------------------------
# T10: Path traversal blocked
# ---------------------------------------------------------------------------
class TestPathTraversalBlocked:
    def test_traversal_raises_value_error(self, tmp_path):
        fm = TenantFileManager(base_path=tmp_path)
        with pytest.raises(ValueError, match="Invalid tenant_id"):
            fm.write_dmn("../etc", "pricing", "x.dmn", "<x/>")


# ---------------------------------------------------------------------------
# T11: Missing required fields validation
# ---------------------------------------------------------------------------
class TestValidationMissingFields:
    def test_empty_definition_returns_errors(self):
        errors = validate_rule({}, "PRICING")
        assert len(errors) >= 1
        codes = [e.code for e in errors]
        assert "MISSING_REQUIRED_FIELD" in codes


# ---------------------------------------------------------------------------
# T12: Version in filename
# ---------------------------------------------------------------------------
class TestVersionInFilename:
    def test_filename_contains_version(self, tmp_path):
        fm = TenantFileManager(base_path=tmp_path)
        gen = DMNGenerator(file_manager=fm)
        rule = _mock_rule(
            "PRICING",
            "PRICING",
            {
                "procedure_code": {"operator": "eq", "value": "99.01"},
                "payer_id": {"operator": "eq", "value": "P1"},
                "quantity": {"operator": "gte", "value": 1},
                "output_unit_price": 100.0,
                "output_total_price": 100.0,
                "output_currency": "BRL",
            },
            version="2.1.0",
        )
        path = gen.generate_and_save(rule, "tenant-ver")
        assert "_v2.1.0.dmn" in path.name
