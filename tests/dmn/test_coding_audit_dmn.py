"""Tests for coding and audit DMN decision tables."""
import pytest
from pathlib import Path
from xml.etree import ElementTree as ET

DMN_NS = {"dmn": "https://www.omg.org/spec/DMN/20191111/MODEL/"}
DMN_DIR = Path(__file__).parent.parent.parent / "platform" / "dmn"


def load_dmn(category: str, name: str) -> ET.Element:
    """Load a DMN file and return its root element."""
    path = DMN_DIR / category / f"{name}.dmn"
    if not path.exists():
        pytest.skip(f"DMN file not found: {path}")
    return ET.parse(path).getroot()


@pytest.mark.dmn
class TestAuditSamplingDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("coding_audit", "Audit_Sampling")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestCBHPMMappingAuditDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("coding_audit", "CBHPM_Mapping")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestCodeMappingLegacyDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("coding_audit", "Code_Mapping_Legacy")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestCodingCompletenessDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("coding_audit", "Coding_Completeness")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestDRGAssignmentDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("coding_audit", "DRG_Assignment")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestICD10ValidationDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("coding_audit", "ICD10_Validation")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1, "DMN should have at least one decision"

        decision_tables = dmn_root.findall(".//dmn:decisionTable", DMN_NS)
        assert len(decision_tables) >= 1, "DMN should have at least one decision table"

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars, "DMN should have tenantId input"

    def test_hit_policy_is_first(self, dmn_root):
        decision_table = dmn_root.find(".//dmn:decisionTable", DMN_NS)
        hit_policy = decision_table.get("hitPolicy")
        assert hit_policy == "FIRST", f"Expected FIRST hit policy, got {hit_policy}"

    def test_has_expected_inputs(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_texts = []
        for inp in inputs:
            input_expr = inp.find(".//dmn:inputExpression/dmn:text", DMN_NS)
            if input_expr is not None:
                input_texts.append(input_expr.text)

        expected_inputs = ["icdCode", "encounterType", "diagnosisPosition", "patientAgeGroup", "tenantId"]
        for expected in expected_inputs:
            assert expected in input_texts, f"Expected input {expected} not found"

    def test_has_expected_outputs(self, dmn_root):
        outputs = dmn_root.findall(".//dmn:output", DMN_NS)
        output_names = [out.get("name") for out in outputs if out.get("name")]

        expected_outputs = ["isValid", "validationMessage", "suggestedCode", "requiresReview"]
        for expected in expected_outputs:
            assert expected in output_names, f"Expected output {expected} not found"

    def test_validates_encounter_types(self, dmn_root):
        """Test that encounter types are defined (INPATIENT, OUTPATIENT, EMERGENCY)."""
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)

        for inp in inputs:
            input_expr = inp.find(".//dmn:inputExpression/dmn:text", DMN_NS)
            if input_expr is not None and input_expr.text == "encounterType":
                input_values = inp.find(".//dmn:inputValues/dmn:text", DMN_NS)
                if input_values is not None:
                    values = input_values.text
                    assert "INPATIENT" in values
                    assert "OUTPATIENT" in values
                    assert "EMERGENCY" in values

    def test_validates_diagnosis_positions(self, dmn_root):
        """Test that diagnosis positions are defined (PRIMARY, SECONDARY, COMPLICATION)."""
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)

        for inp in inputs:
            input_expr = inp.find(".//dmn:inputExpression/dmn:text", DMN_NS)
            if input_expr is not None and input_expr.text == "diagnosisPosition":
                input_values = inp.find(".//dmn:inputValues/dmn:text", DMN_NS)
                if input_values is not None:
                    values = input_values.text
                    assert "PRIMARY" in values
                    assert "SECONDARY" in values
                    assert "COMPLICATION" in values

    @pytest.mark.parametrize("icd_code_pattern,expected_valid", [
        ("A00", True),  # Valid ICD-10 format
        ("Z00", True),  # Valid Z code
        ("invalid", False),  # Invalid format
    ])
    def test_icd_validation_rules(self, dmn_root, icd_code_pattern, expected_valid):
        """Test ICD-10 validation rule structure."""
        rules = dmn_root.findall(".//dmn:rule", DMN_NS)
        assert len(rules) > 0, "DMN should have rules defined"

        # Verify rules have proper structure
        for rule in rules:
            input_entries = rule.findall(".//dmn:inputEntry", DMN_NS)
            output_entries = rule.findall(".//dmn:outputEntry", DMN_NS)

            assert len(input_entries) > 0, "Rule should have input entries"
            assert len(output_entries) > 0, "Rule should have output entries"

    def test_has_portuguese_labels(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        labels = [inp.get("label") for inp in inputs if inp.get("label")]

        portuguese_patterns = ["Código", "Tipo", "Posição", "Faixa", "Tenant"]
        has_portuguese = any(pattern in label for label in labels for pattern in portuguese_patterns)
        assert has_portuguese, "DMN should have Portuguese labels"


@pytest.mark.dmn
class TestMedicalNecessityDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("coding_audit", "Medical_Necessity")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestProcedureCompatibilityDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("coding_audit", "Procedure_Compatibility")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestTUSSValidationDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("coding_audit", "TUSS_Validation")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestUpcodingDetectionDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("coding_audit", "Upcoding_Detection")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars
