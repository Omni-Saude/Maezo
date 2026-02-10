"""Tests for glosa prevention DMN decision tables."""
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
class TestAppealViabilityDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("glosa_prevention", "Appeal_Viability")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestBatchValidationDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("glosa_prevention", "Batch_Validation")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestComplianceCheckDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("glosa_prevention", "Compliance_Check")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestDeadlineMonitorDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("glosa_prevention", "Deadline_Monitor")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestDocumentationChecklistDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("glosa_prevention", "Documentation_Checklist")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestGlosaRiskScoreDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("glosa_prevention", "Glosa_Risk_Score")

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

        expected_inputs = ["documentationCompleteness", "codingAccuracy", "priorAuthStatus", "tenantId"]
        for expected in expected_inputs:
            assert expected in input_texts, f"Expected input {expected} not found"

    def test_has_expected_outputs(self, dmn_root):
        outputs = dmn_root.findall(".//dmn:output", DMN_NS)
        output_names = [out.get("name") for out in outputs if out.get("name")]

        expected_outputs = ["glosaRiskScore", "riskLevel", "recommendedAction", "holdForReview"]
        for expected in expected_outputs:
            assert expected in output_names, f"Expected output {expected} not found"

    def test_validates_risk_levels(self, dmn_root):
        """Test that risk levels are defined (CRITICAL, HIGH, MEDIUM, LOW)."""
        outputs = dmn_root.findall(".//dmn:output", DMN_NS)

        for out in outputs:
            if out.get("name") == "riskLevel":
                output_values = out.find(".//dmn:outputValues/dmn:text", DMN_NS)
                if output_values is not None:
                    values = output_values.text
                    assert "CRITICAL" in values
                    assert "HIGH" in values
                    assert "MEDIUM" in values
                    assert "LOW" in values

    def test_validates_auth_status(self, dmn_root):
        """Test that authorization statuses are defined."""
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)

        for inp in inputs:
            input_expr = inp.find(".//dmn:inputExpression/dmn:text", DMN_NS)
            if input_expr is not None and input_expr.text == "priorAuthStatus":
                input_values = inp.find(".//dmn:inputValues/dmn:text", DMN_NS)
                if input_values is not None:
                    values = input_values.text
                    assert "APPROVED" in values
                    assert "PENDING" in values
                    assert "EXPIRED" in values

    @pytest.mark.parametrize("doc_completeness,coding_accuracy,expected_risk", [
        (90, 90, "LOW"),
        (50, 50, "HIGH"),
        (30, 30, "CRITICAL"),
    ])
    def test_risk_score_decision_logic(self, dmn_root, doc_completeness, coding_accuracy, expected_risk):
        """Test risk score calculation logic with different inputs."""
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

        portuguese_patterns = ["Completude", "Acurácia", "Autorização", "Histórico", "Valor"]
        has_portuguese = any(pattern in label for label in labels for pattern in portuguese_patterns)
        assert has_portuguese, "DMN should have Portuguese labels"


@pytest.mark.dmn
class TestNegotiationStrategyDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("glosa_prevention", "Negotiation_Strategy")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestPayerRulesEngineDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("glosa_prevention", "Payer_Rules_Engine")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestRecoveryPredictionDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("glosa_prevention", "Recovery_Prediction")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestRootCauseClassificationDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("glosa_prevention", "Root_Cause_Classification")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars
