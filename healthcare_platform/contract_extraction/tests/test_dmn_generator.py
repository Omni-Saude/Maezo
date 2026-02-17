"""Tests for DMN generation pipeline."""
import subprocess
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from healthcare_platform.contract_extraction.feel_compiler import FEELCompiler
from healthcare_platform.contract_extraction.tenant_file_manager import TenantFileManager
from healthcare_platform.contract_extraction.dmn_generator import DMNGenerator


def _mock_rule(archetype: str, category: str, rule_definition: dict):
    """Create a mock ContractRule-like object."""
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
    rule.version = "1.0.0"
    return rule


def _xmllint_valid(xml: str) -> bool:
    """Check if XML is valid using xmllint."""
    result = subprocess.run(
        ["xmllint", "--noout", "-"],
        input=xml.encode("utf-8"),
        capture_output=True,
    )
    return result.returncode == 0


class TestDMNGenerator:
    def test_generate_pricing_rule_valid_xml(self):
        """Test 1: PRICING rule generates valid DMN XML."""
        gen = DMNGenerator()
        rule = _mock_rule("PRICING", "PRICING", {
            "procedure_code": {"operator": "eq", "value": "03.05.01.004-2"},
            "payer_id": {"operator": "eq", "value": "SES-DF"},
            "quantity": {"operator": "gte", "value": 1},
            "output_unit_price": 450.0,
            "output_total_price": 450.0,
            "output_currency": "BRL",
        })
        xml = gen.generate(rule)
        assert _xmllint_valid(xml)
        assert "https://www.omg.org/spec/DMN/20191111/MODEL/" in xml

    def test_generate_bundling_rule_valid_xml(self):
        """Test 2: BUNDLING rule generates valid DMN XML."""
        gen = DMNGenerator()
        rule = _mock_rule("BUNDLING", "BUNDLE", {
            "primary_code": {"operator": "eq", "value": "03.05.01.004-2"},
            "secondary_code": {"operator": "eq", "value": "03.05.01.003-4"},
            "same_act": {"operator": "eq", "value": True},
            "output_is_bundled": True,
            "output_bundle_price": 800.0,
            "output_bundle_code": "BUNDLE-HD-001",
        })
        xml = gen.generate(rule)
        assert _xmllint_valid(xml)

    def test_generate_authorization_rule_valid_xml(self):
        """Test 3: AUTHORIZATION rule generates valid DMN XML."""
        gen = DMNGenerator()
        rule = _mock_rule("AUTHORIZATION", "AUTHORIZATION", {
            "procedure_code": {"operator": "eq", "value": "04.09.01.059-2"},
            "amount": {"operator": "gte", "value": 5000},
            "payer_id": {"operator": "eq", "value": "SES-DF"},
            "output_requires_auth": True,
            "output_auth_type": "SUPERVISOR_REQUIRED",
            "output_urgency_level": "HIGH",
        })
        xml = gen.generate(rule)
        assert _xmllint_valid(xml)

    def test_feel_compiler_pricing_positive_amount(self):
        """Test 4: FEELCompiler generates '>= 100.0' for pricing amount."""
        compiler = FEELCompiler()
        rule_def = {
            "procedure_code": {"operator": "eq", "value": "ABC"},
            "payer_id": {"operator": "eq", "value": "P1"},
            "quantity": {"operator": "gte", "value": 100.0},
        }
        template = {
            "inputs": [
                {"name": "procedure_code", "type": "string"},
                {"name": "payer_id", "type": "string"},
                {"name": "quantity", "type": "number"},
            ],
            "outputs": [{"name": "result", "type": "string"}],
        }
        conditions = compiler.compile(rule_def, template)
        assert len(conditions) == 1
        entries = conditions[0].input_entries
        assert ">= 100.0" in entries[2]

    def test_feel_compiler_authorization_threshold(self):
        """Test 5: FEELCompiler generates '>= 5000' for authorization threshold."""
        compiler = FEELCompiler()
        rule_def = {
            "procedure_code": {"operator": "eq", "value": "X"},
            "amount": {"operator": "gte", "value": 5000},
            "payer_id": {"operator": "eq", "value": "P1"},
        }
        template = {
            "inputs": [
                {"name": "procedure_code", "type": "string"},
                {"name": "amount", "type": "number"},
                {"name": "payer_id", "type": "string"},
            ],
            "outputs": [{"name": "requires_auth", "type": "boolean"}],
        }
        conditions = compiler.compile(rule_def, template)
        entries = conditions[0].input_entries
        assert ">= 5000" in entries[1]

    def test_tenant_file_manager_write_read(self, tmp_path):
        """Test 6: TenantFileManager write/read roundtrip."""
        mgr = TenantFileManager(base_path=tmp_path)
        xml = '<?xml version="1.0"?><root/>'
        path = mgr.write_dmn("tenant-a", "pricing", "test.dmn", xml)
        assert path.exists()
        content = mgr.read_dmn("tenant-a", "pricing", "test.dmn")
        assert content == xml

    def test_tenant_file_manager_path_traversal_blocked(self, tmp_path):
        """Test 7: TenantFileManager blocks path traversal."""
        mgr = TenantFileManager(base_path=tmp_path)
        with pytest.raises(ValueError, match="Invalid tenant_id"):
            mgr.write_dmn("../etc", "pricing", "test.dmn", "<x/>")

    def test_generator_saves_to_correct_tenant_path(self, tmp_path):
        """Test 8: generate_and_save writes to correct tenant path with version."""
        gen = DMNGenerator(file_manager=TenantFileManager(base_path=tmp_path))
        rule = _mock_rule("PRICING", "PRICING", {
            "procedure_code": {"operator": "eq", "value": "ABC"},
            "payer_id": {"operator": "eq", "value": "P1"},
            "quantity": {"operator": "gte", "value": 1},
        })
        path = gen.generate_and_save(rule, "tenant-x")
        assert path.exists()
        assert "tenant-x" in str(path)
        assert "pricing" in str(path)
        assert "_v1.0.0.dmn" in path.name
        content = path.read_text()
        assert _xmllint_valid(content)

    def test_versioned_filename_reflects_rule_version(self, tmp_path):
        """Test 9: Version in filename matches rule.version."""
        gen = DMNGenerator(file_manager=TenantFileManager(base_path=tmp_path))
        rule = _mock_rule("PRICING", "PRICING", {
            "procedure_code": {"operator": "eq", "value": "X"},
            "payer_id": {"operator": "eq", "value": "P1"},
            "quantity": {"operator": "gte", "value": 1},
        })
        rule.version = "2.1.0"
        path = gen.generate_and_save(rule, "tenant-y")
        assert "_v2.1.0.dmn" in path.name

    def test_federation_service_loads_generated_dmn(self, tmp_path):
        """Test 10: FederatedDMNService can parse DMN generated by the pipeline."""
        from unittest.mock import patch
        import xml.etree.ElementTree as ET

        gen = DMNGenerator(file_manager=TenantFileManager(base_path=tmp_path))
        rule = _mock_rule("PRICING", "PRICING", {
            "procedure_code": {"operator": "eq", "value": "03.05.01.004-2"},
            "payer_id": {"operator": "eq", "value": "SES-DF"},
            "quantity": {"operator": "gte", "value": 1},
            "output_unit_price": 450.0,
            "output_total_price": 450.0,
            "output_currency": "BRL",
        })
        path = gen.generate_and_save(rule, "tenant-fed")

        # Verify the XML is parseable as ElementTree (same as FederatedDMNService._parse_dmn_xml)
        tree = ET.parse(str(path))
        root = tree.getroot()
        ns = "https://www.omg.org/spec/DMN/20191111/MODEL/"
        decisions = root.findall(f".//{{{ns}}}decision")
        assert len(decisions) >= 1
        dt = root.findall(f".//{{{ns}}}decisionTable")
        assert len(dt) >= 1
        rules = root.findall(f".//{{{ns}}}rule")
        assert len(rules) >= 1
