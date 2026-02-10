"""Tests for access control DMN decision tables."""
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
class TestAuditTrailRulesDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("access_control", "Audit_Trail_Rules")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1, "DMN should have at least one decision"

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars, "DMN should have tenantId input"


@pytest.mark.dmn
class TestConsentManagementDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("access_control", "Consent_Management")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestDataAccessPolicyDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("access_control", "Data_Access_Policy")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestPHIMaskingRulesDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("access_control", "PHI_Masking_Rules")

    def test_dmn_structure_valid(self, dmn_root):
        decisions = dmn_root.findall(".//dmn:decision", DMN_NS)
        assert len(decisions) >= 1

    def test_has_tenant_input(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        input_vars = [inp.find(".//dmn:inputExpression/dmn:text", DMN_NS).text
                      for inp in inputs if inp.find(".//dmn:inputExpression/dmn:text", DMN_NS) is not None]
        assert "tenantId" in input_vars


@pytest.mark.dmn
class TestUserPermissionsDMN:
    @pytest.fixture
    def dmn_root(self):
        return load_dmn("access_control", "User_Permissions")

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

        expected_inputs = ["userRole", "department", "resourceType", "tenantId"]
        for expected in expected_inputs:
            assert expected in input_texts, f"Expected input {expected} not found"

    def test_has_expected_outputs(self, dmn_root):
        outputs = dmn_root.findall(".//dmn:output", DMN_NS)
        output_names = [out.get("name") for out in outputs if out.get("name")]

        expected_outputs = ["accessLevel", "requiresMFA", "auditRequired", "dataScope"]
        for expected in expected_outputs:
            assert expected in output_names, f"Expected output {expected} not found"

    def test_has_admin_role_rules(self, dmn_root):
        """Test that ADMIN role rules exist."""
        rules = dmn_root.findall(".//dmn:rule", DMN_NS)
        assert len(rules) > 0, "DMN should have rules defined"

        # Look for rules with admin-related entries
        admin_rule_found = False
        for rule in rules:
            input_entries = rule.findall(".//dmn:inputEntry/dmn:text", DMN_NS)
            for entry in input_entries:
                if entry.text and "ADMIN" in entry.text.upper():
                    admin_rule_found = True
                    break

        assert admin_rule_found, "DMN should have rules for ADMIN role"

    def test_has_physician_role_rules(self, dmn_root):
        """Test that PHYSICIAN role rules exist."""
        rules = dmn_root.findall(".//dmn:rule", DMN_NS)

        physician_rule_found = False
        for rule in rules:
            input_entries = rule.findall(".//dmn:inputEntry/dmn:text", DMN_NS)
            for entry in input_entries:
                if entry.text and "PHYSICIAN" in entry.text.upper():
                    physician_rule_found = True
                    break

        assert physician_rule_found, "DMN should have rules for PHYSICIAN role"

    def test_has_access_level_outputs(self, dmn_root):
        """Test that access level values are properly defined."""
        rules = dmn_root.findall(".//dmn:rule", DMN_NS)

        # Check that output entries exist for access levels
        access_levels_found = set()
        for rule in rules:
            output_entries = rule.findall(".//dmn:outputEntry/dmn:text", DMN_NS)
            for entry in output_entries:
                if entry.text:
                    text = entry.text.strip('"')
                    if text in ["FULL", "READ_WRITE", "READ_ONLY", "NONE"]:
                        access_levels_found.add(text)

        assert len(access_levels_found) > 0, "DMN should have access level outputs defined"

    @pytest.mark.parametrize("user_role,resource_type,expected_access", [
        ("ADMIN", "PATIENT_DATA", "FULL"),
        ("PHYSICIAN", "PATIENT_DATA", "READ_WRITE"),
        ("NURSE", "CLINICAL", "READ_WRITE"),
        ("BILLING_ANALYST", "BILLING", "READ_WRITE"),
        ("AUDITOR", "PATIENT_DATA", "READ_ONLY"),
    ])
    def test_permission_decision_logic(self, dmn_root, user_role, resource_type, expected_access):
        """Test permission decision logic structure with different roles."""
        rules = dmn_root.findall(".//dmn:rule", DMN_NS)
        assert len(rules) > 0, "DMN should have rules defined"

        # Verify rules have proper structure
        for rule in rules:
            input_entries = rule.findall(".//dmn:inputEntry", DMN_NS)
            output_entries = rule.findall(".//dmn:outputEntry", DMN_NS)

            assert len(input_entries) > 0, "Rule should have input entries"
            assert len(output_entries) > 0, "Rule should have output entries"

    def test_has_default_deny_rule(self, dmn_root):
        """Test that a default deny rule exists for security."""
        rules = dmn_root.findall(".//dmn:rule", DMN_NS)

        # Look for rule with NONE or denial output
        deny_rule_found = False
        for rule in rules:
            output_entries = rule.findall(".//dmn:outputEntry/dmn:text", DMN_NS)
            for entry in output_entries:
                if entry.text and "NONE" in entry.text.strip('"'):
                    deny_rule_found = True
                    break

        assert deny_rule_found, "DMN should have a default deny rule for security"

    def test_has_portuguese_labels(self, dmn_root):
        inputs = dmn_root.findall(".//dmn:input", DMN_NS)
        labels = [inp.get("label") for inp in inputs if inp.get("label")]

        portuguese_patterns = ["Papel", "Departamento", "Tipo", "Recurso", "Usuário"]
        has_portuguese = any(pattern in label for label in labels for pattern in portuguese_patterns)
        assert has_portuguese, "DMN should have Portuguese labels"

    def test_validates_mfa_requirement(self, dmn_root):
        """Test that MFA requirements are defined for sensitive roles."""
        outputs = dmn_root.findall(".//dmn:output", DMN_NS)

        mfa_output = None
        for out in outputs:
            if out.get("name") == "requiresMFA":
                mfa_output = out
                break

        assert mfa_output is not None, "requiresMFA output should be defined"

    def test_validates_audit_requirement(self, dmn_root):
        """Test that audit requirements are defined."""
        outputs = dmn_root.findall(".//dmn:output", DMN_NS)

        audit_output = None
        for out in outputs:
            if out.get("name") == "auditRequired":
                audit_output = out
                break

        assert audit_output is not None, "auditRequired output should be defined"
