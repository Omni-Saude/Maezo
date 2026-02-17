"""Service-layer tests for ContractService (tests 1-11)."""
import uuid
from datetime import date
from unittest.mock import patch

import pytest

from healthcare_platform.contract_extraction.models import (
    ContractRule,
    ContractRuleChange,
    RuleArchetype,
    RuleCategory,
    RuleStatus,
)
from healthcare_platform.contract_extraction.schemas import (
    RuleCreateRequest,
    RuleUpdateRequest,
)


@pytest.fixture
def create_request():
    return RuleCreateRequest(
        payer_id="payer-001",
        category=RuleCategory.PRICING,
        archetype=RuleArchetype.PRICING,
        rule_definition={"procedure_code": "A001"},
        version="1.0.0",
        effective_date=date(2025, 1, 1),
    )


@pytest.fixture
def sample_rule(service, create_request):
    return service.create_rule("tenant-a", create_request, created_by="tester")


# ---------------------------------------------------------------------------
# Tests 1-11: ContractService unit tests with SQLite
# ---------------------------------------------------------------------------


def test_create_rule_persists_with_draft_status(service, create_request):
    """Rule is saved to the DB with DRAFT status and expected field values."""
    rule = service.create_rule("tenant-x", create_request, created_by="tester")
    assert rule.id is not None
    assert rule.status == RuleStatus.DRAFT
    assert rule.tenant_id == "tenant-x"
    assert rule.payer_id == "payer-001"


def test_create_rule_records_change_entry(service, session, create_request):
    """A ContractRuleChange of type CREATED is written on rule creation."""
    rule = service.create_rule("tenant-audit", create_request, created_by="tester")
    change = (
        session.query(ContractRuleChange)
        .filter_by(rule_id=rule.id, change_type="CREATED")
        .first()
    )
    assert change is not None
    assert change.changed_by == "tester"


def test_list_rules_filters_by_tenant(service, create_request):
    """Rules for tenant-A are not returned when listing for tenant-B."""
    service.create_rule("tenant-list-a", create_request, created_by="tester")
    service.create_rule("tenant-list-b", create_request, created_by="tester")

    results_a = service.list_rules("tenant-list-a")
    results_b = service.list_rules("tenant-list-b")

    assert all(r.tenant_id == "tenant-list-a" for r in results_a)
    assert all(r.tenant_id == "tenant-list-b" for r in results_b)


def test_list_rules_filters_by_status(service, session, create_request):
    """list_rules with status=ACTIVE excludes DRAFT rules."""
    active_rule = service.create_rule("tenant-status", create_request, created_by="tester")
    active_rule.status = RuleStatus.ACTIVE
    session.commit()

    draft_req = RuleCreateRequest(
        payer_id="payer-002",
        category=RuleCategory.PRICING,
        archetype=RuleArchetype.PRICING,
        rule_definition={},
        version="1.0.0",
        effective_date=date(2025, 1, 1),
    )
    service.create_rule("tenant-status", draft_req, created_by="tester")

    active_rules = service.list_rules("tenant-status", status=RuleStatus.ACTIVE)
    assert all(r.status == RuleStatus.ACTIVE for r in active_rules)
    assert any(r.id == active_rule.id for r in active_rules)


def test_get_rule_raises_key_error_when_missing(service):
    """get_rule raises KeyError for a non-existent rule id."""
    with pytest.raises(KeyError):
        service.get_rule("tenant-a", uuid.uuid4())


def test_update_rule_applies_partial_changes(service, sample_rule):
    """update_rule only mutates the supplied field, leaving others intact."""
    original_archetype = sample_rule.archetype
    update_req = RuleUpdateRequest(payer_id="payer-updated")

    updated = service.update_rule("tenant-a", sample_rule.id, update_req)

    assert updated.payer_id == "payer-updated"
    assert updated.archetype == original_archetype


def test_delete_rule_removes_from_db(service, session, create_request):
    """delete_rule removes the record; a subsequent query returns None."""
    rule = service.create_rule("tenant-del", create_request, created_by="tester")
    rule_id = rule.id

    service.delete_rule("tenant-del", rule_id)

    gone = session.query(ContractRule).filter_by(id=rule_id).first()
    assert gone is None


def test_validate_rule_by_id_returns_errors(service, sample_rule):
    """validate_rule_by_id returns is_valid=False when the validator finds errors."""
    with patch(
        "healthcare_platform.contract_extraction.services.dmn_service.validate_rule"
    ) as mock_validate:
        from healthcare_platform.contract_extraction.validators import ValidationError
        mock_validate.return_value = [
            ValidationError(field="f", message="bad", code="ERR")
        ]
        result = service.validate_rule_by_id("tenant-a", sample_rule.id)

    assert result["is_valid"] is False
    assert len(result["errors"]) == 1
    assert result["errors"][0]["code"] == "ERR"


def test_preview_dmn_calls_generate_not_save(service, dmn_mock, sample_rule):
    """preview_dmn calls dmn_generator.generate but never generate_and_save."""
    result = service.preview_dmn("tenant-a", sample_rule.id)

    dmn_mock.generate.assert_called_once()
    dmn_mock.generate_and_save.assert_not_called()
    assert result["xml_content"] == "<xml/>"


def test_deploy_rule_validates_first_raises_on_errors(service, sample_rule):
    """deploy_rule raises ValueError when validation returns errors."""
    with patch(
        "healthcare_platform.contract_extraction.services.dmn_service.validate_rule"
    ) as mock_validate:
        from healthcare_platform.contract_extraction.validators import ValidationError
        mock_validate.return_value = [
            ValidationError(field="x", message="missing", code="MISSING")
        ]
        with pytest.raises(ValueError, match="failed validation"):
            service.deploy_rule("tenant-a", sample_rule.id)


def test_deploy_rule_sets_active_status(service, session, dmn_mock, create_request):
    """deploy_rule sets rule.status to ACTIVE and returns the path on success."""
    with patch(
        "healthcare_platform.contract_extraction.services.dmn_service.validate_rule",
        return_value=[],
    ):
        rule = service.create_rule("tenant-deploy", create_request, created_by="tester")
        result = service.deploy_rule("tenant-deploy", rule.id)

    assert result["status"] == RuleStatus.ACTIVE.value
    fresh = session.query(ContractRule).filter_by(id=rule.id).first()
    assert fresh.status == RuleStatus.ACTIVE
