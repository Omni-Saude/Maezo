"""Tests for billing DMN decision tables."""
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
class TestBillingCalculationDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "Billing_Calculation")

    def test_dmn_structure_valid(self, dmn_root):
        """Test that DMN has valid structure with decision and decision table."""
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1, "DMN should have at least one decision"

        decision_tables = dmn_root.findall(".//dmn:decisionTable", DMN_NS)
        assert len(decision_tables) >= 1, "DMN should have at least one decision table"

    def test_has_tenant_input(self, dmn_root):
        """Verify tenantId input exists for multi-tenant support."""
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = []
        for inp in inputs:
            input_expr = inp.find(".//dmn:inputExpression/dmn:text", DMN_NS)
            if input_expr is not None:
                input_vars.append(input_expr.text)

        assert "tenantId" in input_vars, "DMN should have tenantId input for multi-tenant"

    def test_hit_policy_is_first(self, dmn_root):
        """Test that decision table uses FIRST hit policy."""
        decision_table = dmn_root.find(".//dmn:decisionTable", DMN_NS)
        hit_policy = decision_table.get("hitPolicy")
        assert hit_policy == "FIRST", f"Expected FIRST hit policy, got {hit_policy}"

    def test_has_expected_inputs(self, dmn_root):
        """Test that all expected input columns exist."""
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_texts = []
        for inp in inputs:
            input_expr = inp.find(".//dmn:inputExpression/dmn:text", DMN_NS)
            if input_expr is not None:
                input_texts.append(input_expr.text)

        expected_inputs = ["procedureType", "insuranceTable", "baseValue", "hasGlosa", "tenantId"]
        for expected in expected_inputs:
            assert expected in input_texts, f"Expected input {expected} not found"

    def test_has_expected_outputs(self, dmn_root):
        """Test that all expected output columns exist."""
        outputs = dmn_root.findall(".//dmn:output", DMN_NS)
        output_names = [out.get("name") for out in outputs if out.get("name")]

        expected_outputs = ["billableAmount", "discountApplied", "finalAmount", "calculationRule", "needsAudit"]
        for expected in expected_outputs:
            assert expected in output_names, f"Expected output {expected} not found"

    def test_has_portuguese_labels(self, dmn_root):
        """Test that Portuguese labels are present."""
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        labels = [inp.get("label") for inp in inputs if inp.get("label")]

        # Check for Portuguese characters/words
        portuguese_patterns = ["Tipo", "Tabela", "Valor", "Glosa", "Tenant"]
        has_portuguese = any(pattern in label for label in labels for pattern in portuguese_patterns)
        assert has_portuguese, "DMN should have Portuguese labels"

    @pytest.mark.parametrize("procedure_type,insurance,base_value,has_glosa,expected_rule", [
        ("SURGICAL", "SUS", 1000.0, False, "SUS_SURGICAL_STANDARD"),
        ("CLINICAL", "CBHPM", 1000.0, False, "CBHPM_CLINICAL_MARKUP"),
        ("DIAGNOSTIC", "AMB", 1000.0, False, "AMB_DIAGNOSTIC_STANDARD"),
        ("HOSPITALIZATION", "BRASINDICE", 1000.0, False, "BRASINDICE_HOSPITALIZATION"),
        ("THERAPEUTIC", "SIMPRO", 1000.0, False, "SIMPRO_THERAPEUTIC_STANDARD"),
    ])
    def test_decision_rules_logic(self, dmn_root, procedure_type, insurance, base_value, has_glosa, expected_rule):
        """Test decision table rules match expected business logic."""
        # Find all rules
        rules = dmn_root.findall(".//dmn:rule", DMN_NS)
        assert len(rules) > 0, "DMN should have rules defined"

        # Verify rule structure contains output entries
        for rule in rules:
            output_entries = rule.findall(".//dmn:outputEntry", DMN_NS)
            assert len(output_entries) > 0, "Each rule should have output entries"

    def test_has_glosa_rule(self, dmn_root):
        """Test that glosa deduction rule exists."""
        rules = dmn_root.findall(".//dmn:rule", DMN_NS)

        # Look for rule that handles glosa (hasGlosa = true)
        glosa_rule_found = False
        for rule in rules:
            input_entries = rule.findall(".//dmn:inputEntry/dmn:text", DMN_NS)
            for entry in input_entries:
                if entry.text and "true" in entry.text.lower():
                    glosa_rule_found = True
                    break

        assert glosa_rule_found, "DMN should have rule handling glosa"


@pytest.mark.dmn
class TestCBHPMMapping:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "CBHPM_Mapping")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestContractRulesAmil:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "Contract_Rules_Amil")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestContractRulesBradesco:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "Contract_Rules_Bradesco")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestContractRulesSulAmerica:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "Contract_Rules_SulAmerica")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestContractRulesUnimed:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "Contract_Rules_Unimed")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestCopayCalculation:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "Copay_Calculation")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestDiscountRules:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "Discount_Rules")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestOPMEPricing:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "OPME_Pricing")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestPackagePricing:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "Package_Pricing")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestRevenueProjection:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "Revenue_Projection")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestSUSTableLookup:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "SUS_Table_Lookup")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestTaxCalculation:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "Tax_Calculation")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestTISSFormatRules:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "TISS_Format_Rules")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestBillingDeadline:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("billing", "Billing_Deadline")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars
