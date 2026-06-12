"""Audit trail tests for P5c: delete change, version bump, conflict detection, history endpoint."""
import uuid
from datetime import date

import pytest

from healthcare_platform.contract_extraction.models import (
    ContractRuleChange,
    RuleArchetype,
    RuleCategory,
    RuleStatus,
)
from healthcare_platform.contract_extraction.schemas import (
    RuleCreateRequest,
    RuleUpdateRequest,
)


def _unique_tenant():
    return f"tenant-audit-{uuid.uuid4().hex[:8]}"


def _make_request(**overrides):
    defaults = dict(
        payer_id="payer-001",
        category=RuleCategory.PRICING,
        archetype=RuleArchetype.PRICING,
        rule_definition={"procedure_code": "A001"},
        version="1.0.0",
        effective_date=date(2025, 1, 1),
    )
    defaults.update(overrides)
    return RuleCreateRequest(**defaults)


# T1
def test_delete_records_change(service, session):
    """delete_rule creates a DELETED ContractRuleChange before removing the rule."""
    tid = _unique_tenant()
    rule = service.create_rule(tid, _make_request(), created_by="tester")
    rule_id = rule.id
    service.delete_rule(tid, rule_id)
    change = (
        session.query(ContractRuleChange)
        .filter_by(rule_id=rule_id, change_type="DELETED")
        .first()
    )
    assert change is not None
    assert change.old_value is not None
    assert change.old_value["payer_id"] == "payer-001"


# T2
def test_update_bumps_version(service):
    """update_rule increments PATCH version when rule_definition changes."""
    tid = _unique_tenant()
    rule = service.create_rule(tid, _make_request(), created_by="tester")
    update = RuleUpdateRequest(rule_definition={"procedure_code": "B002"})
    updated = service.update_rule(tid, rule.id, update, updated_by="tester")
    assert updated.version == "1.0.1"


# T3
def test_update_same_definition_no_bump(service):
    """update_rule with unchanged rule_definition keeps same version."""
    tid = _unique_tenant()
    rule = service.create_rule(tid, _make_request(), created_by="tester")
    update = RuleUpdateRequest(payer_id="payer-002")
    updated = service.update_rule(tid, rule.id, update, updated_by="tester")
    assert updated.version == "1.0.0"


# T4
def test_conflict_detection_overlapping_dates(service):
    """Creating 2 rules with same tenant+payer+category and overlapping dates raises ValueError."""
    tid = _unique_tenant()
    req = _make_request()
    service.create_rule(tid, req, created_by="tester")
    with pytest.raises(ValueError, match="Conflicting rules"):
        service.create_rule(tid, req, created_by="tester")


# T5
def test_conflict_detection_non_overlapping_dates(service):
    """Non-overlapping date ranges don't trigger conflict."""
    tid = _unique_tenant()
    req1 = _make_request(
        rule_definition={"code": "A"},
        effective_date=date(2025, 1, 1), expiry_date=date(2025, 6, 30),
    )
    req2 = _make_request(
        rule_definition={"code": "B"},
        effective_date=date(2025, 7, 1), expiry_date=date(2025, 12, 31),
    )
    service.create_rule(tid, req1, created_by="tester")
    rule2 = service.create_rule(tid, req2, created_by="tester")
    assert rule2 is not None


# T6
def test_conflict_detection_different_category(service):
    """Same dates but different category don't conflict."""
    tid = _unique_tenant()
    req1 = _make_request()
    req2 = _make_request(category=RuleCategory.BUNDLE, archetype=RuleArchetype.BUNDLING)
    service.create_rule(tid, req1, created_by="tester")
    rule2 = service.create_rule(tid, req2, created_by="tester")
    assert rule2 is not None


# T7
def test_history_returns_changes(service):
    """get_rule_history returns changes in order after create and update."""
    tid = _unique_tenant()
    rule = service.create_rule(tid, _make_request(), created_by="tester")
    update = RuleUpdateRequest(rule_definition={"procedure_code": "C003"})
    service.update_rule(tid, rule.id, update, updated_by="tester")
    history = service.get_rule_history(tid, rule.id)
    assert len(history) >= 2
    types = [h.change_type for h in history]
    assert "CREATED" in types
    assert "UPDATED" in types


# T8
def test_history_empty_for_new_rule(service):
    """New rule has exactly 1 CREATED change."""
    tid = _unique_tenant()
    rule = service.create_rule(tid, _make_request(), created_by="tester")
    history = service.get_rule_history(tid, rule.id)
    assert len(history) == 1
    assert history[0].change_type == "CREATED"


# T9
def test_history_scoped_to_tenant(service):
    """Tenant A cannot see tenant B's rule history."""
    tid_a = _unique_tenant()
    tid_b = _unique_tenant()
    rule_b = service.create_rule(tid_b, _make_request(), created_by="tester")
    with pytest.raises(KeyError):
        service.get_rule_history(tid_a, rule_b.id)


# T10
def test_conflict_ignores_archived_rules(service, session):
    """Archived rules don't trigger conflicts."""
    tid = _unique_tenant()
    req = _make_request()
    rule = service.create_rule(tid, req, created_by="tester")
    rule.status = RuleStatus.ARCHIVED
    session.commit()
    rule2 = service.create_rule(tid, req, created_by="tester")
    assert rule2 is not None
