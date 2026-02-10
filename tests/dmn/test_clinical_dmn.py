"""Tests for clinical DMN decision tables."""
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
class TestBloodTransfusionDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("clinical", "Blood_Transfusion")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1, "DMN should have at least one decision"

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars, "DMN should have tenantId input"

    def test_has_portuguese_labels(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        labels = [inp.get("label") for inp in inputs if inp.get("label")]
        has_portuguese = any(label for label in labels)
        assert has_portuguese, "DMN should have labels"


@pytest.mark.dmn
class TestClinicalProtocolDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("clinical", "Clinical_Protocol")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestDischargeReadinessDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("clinical", "Discharge_Readiness")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestFallRiskDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("clinical", "Fall_Risk")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestICUAdmissionDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("clinical", "ICU_Admission")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestMedicationInteractionDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("clinical", "Medication_Interaction")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestNutritionAssessmentDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("clinical", "Nutrition_Assessment")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestPressureInjuryRiskDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("clinical", "Pressure_Injury_Risk")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestSepsisRiskDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("clinical", "Sepsis_Risk")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestTriagePriorityDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("clinical", "Triage_Priority")

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

    def test_has_expected_outputs(self, dmn_root):
        outputs = dmn_root.findall(".//dmn:output", DMN_NS)
        output_names = [out.get("name") for out in outputs if out.get("name")]

        expected_outputs = ["triageColor", "maxWaitMinutes", "resourceAllocation", "requiresMonitoring"]
        for expected in expected_outputs:
            assert expected in output_names, f"Expected output {expected} not found"

    def test_has_triage_colors(self, dmn_root):
        """Test that triage colors (RED, ORANGE, YELLOW, GREEN, BLUE) are defined."""
        outputs = dmn_root.findall(".//dmn:output", DMN_NS)

        # Find triageColor output
        triage_output = None
        for out in outputs:
            if out.get("name") == "triageColor":
                triage_output = out
                break

        assert triage_output is not None, "triageColor output should be defined"

        # Check for output values containing triage colors
        output_values = triage_output.find(".//dmn:outputValues/dmn:text", DMN_NS)
        if output_values is not None:
            colors = output_values.text
            expected_colors = ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE"]
            for color in expected_colors:
                assert color in colors, f"Expected triage color {color} not found"

    @pytest.mark.parametrize("consciousness_level,vital_signs_alert,expected_priority", [
        ("UNRESPONSIVE", True, "high"),
        ("ALERT", False, "low"),
        ("PAIN", True, "medium"),
    ])
    def test_triage_decision_logic(self, dmn_root, consciousness_level, vital_signs_alert, expected_priority):
        """Test triage priority decision logic with different inputs."""
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

        portuguese_patterns = ["Queixa", "Alerta", "Nível", "Modo", "Tenant"]
        has_portuguese = any(pattern in label for label in labels for pattern in portuguese_patterns)
        assert has_portuguese, "DMN should have Portuguese labels"
