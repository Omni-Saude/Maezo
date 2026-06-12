"""
Tests for healthcare_platform.contract_extraction.validators

6 test functions covering validate_completeness, validate_types, and validate_rule.
"""

from unittest.mock import patch

from healthcare_platform.contract_extraction.validators import (
    validate_completeness,
    validate_types,
    validate_rule,
)

# ---------------------------------------------------------------------------
# Reusable mock template fixtures
# ---------------------------------------------------------------------------

MOCK_PRICING_TEMPLATE_BASIC = {
    "name": "mock_pricing_basic",
    "archetype": "PRICING",
    "required_inputs": ["procedure_code", "payer_id"],
    "inputs": [
        {"name": "procedure_code", "type": "string", "required": True},
        {"name": "payer_id", "type": "string", "required": True},
    ],
}

MOCK_PRICING_TEMPLATE_WITH_QUANTITY = {
    "name": "mock_pricing_quantity",
    "archetype": "PRICING",
    "required_inputs": ["procedure_code", "payer_id", "quantity"],
    "inputs": [
        {"name": "procedure_code", "type": "string", "required": True},
        {"name": "payer_id", "type": "string", "required": True},
        {"name": "quantity", "type": "number", "required": True},
    ],
}

MOCK_BUNDLING_TEMPLATE = {
    "name": "mock_bundle",
    "archetype": "BUNDLING",
    "required_inputs": ["same_act"],
    "inputs": [
        {"name": "same_act", "type": "boolean", "required": True},
    ],
}

MOCK_AUTHORIZATION_TEMPLATE = {
    "name": "mock_auth",
    "archetype": "AUTHORIZATION",
    "required_inputs": ["amount"],
    "inputs": [
        {"name": "amount", "type": "number", "required": True},
    ],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_validate_completeness_valid_pricing():
    """All required fields present → no validation errors."""
    mock_templates = {"PRICING": [MOCK_PRICING_TEMPLATE_BASIC]}
    with patch(
        "healthcare_platform.contract_extraction.validators.LOADED_TEMPLATES",
        mock_templates,
    ):
        result = validate_completeness(
            {"procedure_code": "A001", "payer_id": "payer1"}, "PRICING"
        )
    assert result == []


def test_validate_completeness_missing_field():
    """Two required fields absent → two MISSING_REQUIRED_FIELD errors."""
    mock_templates = {"PRICING": [MOCK_PRICING_TEMPLATE_WITH_QUANTITY]}
    with patch(
        "healthcare_platform.contract_extraction.validators.LOADED_TEMPLATES",
        mock_templates,
    ):
        result = validate_completeness({"procedure_code": "A001"}, "PRICING")

    assert len(result) == 2
    assert all(e.code == "MISSING_REQUIRED_FIELD" for e in result)
    missing_fields = {e.field for e in result}
    assert missing_fields == {"payer_id", "quantity"}


def test_validate_completeness_unknown_archetype():
    """Archetype not in templates → single UNKNOWN_ARCHETYPE error."""
    result = validate_completeness({"any_field": "value"}, "UNKNOWN_ARCHETYPE")

    assert len(result) == 1
    assert result[0].code == "UNKNOWN_ARCHETYPE"


def test_validate_types_invalid_type():
    """String value for a boolean field → INVALID_TYPE error for that field."""
    mock_templates = {"BUNDLING": [MOCK_BUNDLING_TEMPLATE]}
    with patch(
        "healthcare_platform.contract_extraction.validators.LOADED_TEMPLATES",
        mock_templates,
    ):
        result = validate_types({"same_act": "yes_string_not_bool"}, "BUNDLING")

    assert len(result) == 1
    assert result[0].code == "INVALID_TYPE"
    assert result[0].field == "same_act"


def test_validate_types_valid():
    """Numeric value for a number field → no type errors."""
    mock_templates = {"AUTHORIZATION": [MOCK_AUTHORIZATION_TEMPLATE]}
    with patch(
        "healthcare_platform.contract_extraction.validators.LOADED_TEMPLATES",
        mock_templates,
    ):
        result = validate_types({"amount": 1500.0}, "AUTHORIZATION")

    assert result == []


def test_validate_rule_combines_errors():
    """
    validate_rule aggregates completeness and type errors.

    Rule definition: missing 'payer_id' (required) and 'procedure_code'
    is supplied as an integer instead of a string.  Expect at least
    one MISSING_REQUIRED_FIELD error.
    """
    mock_templates = {"PRICING": [MOCK_PRICING_TEMPLATE_BASIC]}
    with patch(
        "healthcare_platform.contract_extraction.validators.LOADED_TEMPLATES",
        mock_templates,
    ):
        result = validate_rule({"procedure_code": 12345}, "PRICING")

    assert len(result) >= 1
    assert any(e.code == "MISSING_REQUIRED_FIELD" for e in result)
