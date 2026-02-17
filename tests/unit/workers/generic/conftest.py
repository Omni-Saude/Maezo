"""Shared fixtures for generic worker unit tests."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.shared.workers.base import TaskContext, TaskResult, TaskStatus


# ---------------------------------------------------------------------------
# Registry config fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_registry_config():
    """Valid single-DMN registry config for an ADMIN_ADJUDICATION worker."""
    return {
        "archetype": "ADMIN_ADJUDICATION",
        "decisions": [
            {
                "key": "claim_validation_rules",
                "category": "billing",
                "inputs": {},
            }
        ],
        "error_strategy": "fail_closed",
    }


@pytest.fixture
def sample_pipeline_config():
    """Valid 3-step pipeline registry config."""
    return {
        "archetype": "CLINICAL_SCORE",
        "decisions": [
            {
                "key": "audit_documentation_completeness",
                "category": "clinical_safety",
                "inputs": {},
            },
            {
                "key": "audit_rule_compliance",
                "category": "clinical_safety",
                "inputs": {},
            },
            {
                "key": "audit_priority_classification",
                "category": "clinical_safety",
                "inputs": {},
            },
        ],
        "error_strategy": "fail_safe",
    }


@pytest.fixture
def sample_clinical_alert_config():
    """Valid CLINICAL_ALERT registry config (fail_safe default)."""
    return {
        "archetype": "CLINICAL_ALERT",
        "decisions": [
            {
                "key": "sepsis_alert_rules",
                "category": "clinical_safety",
                "inputs": {},
            }
        ],
    }


# ---------------------------------------------------------------------------
# TaskContext fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_context():
    """Mock TaskContext with sample variables."""
    return TaskContext(
        task_id="task-001",
        process_instance_id="proc-999",
        tenant_id="hospital-a",
        variables={
            "claimId": "CLM-123",
            "payerId": "payer-001",
            "amount": 1500.00,
            "timestamp": "2026-02-17T10:00:00Z",
        },
        worker_id="billing.validate_claim",
        retries=3,
    )


# ---------------------------------------------------------------------------
# Service mocks
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_dmn_service():
    """Mock FederatedDMNService returning a default PROSSEGUIR result."""
    service = MagicMock()
    service.evaluate.return_value = {"action": "PROSSEGUIR", "reason": "OK"}
    return service


@pytest.fixture
def mock_logger():
    """Mock logger to suppress output during tests."""
    return MagicMock(spec=logging.Logger)
