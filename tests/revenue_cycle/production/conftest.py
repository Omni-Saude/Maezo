"""Shared fixtures for production worker tests.

Provides tenant context setup for all production v2 worker tests.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock

from healthcare_platform.shared.multi_tenant.context import (
    TenantContext,
    set_current_tenant,
    clear_tenant,
)
from healthcare_platform.shared.domain.enums import TenantCode


@pytest.fixture(autouse=True)
def setup_tenant_context():
    """Automatically set up tenant context for all production tests.

    The production v2 workers use @require_tenant decorator which validates
    that tenant context is set before execution. This fixture ensures
    all tests have a valid tenant context.
    """
    # Set up tenant context before test
    tenant = TenantContext.from_tenant_code(TenantCode.HOSPITAL_A)
    set_current_tenant(tenant)

    yield

    # Clean up after test
    clear_tenant()


@pytest.fixture
def mock_dmn_service():
    """Mock FederatedDMNService for DMN evaluation.

    Returns:
        MagicMock with evaluate() method configured
    """
    mock = MagicMock()
    mock.evaluate.return_value = {"resultado": "PROSSEGUIR"}
    return mock


@pytest.fixture
def mock_task():
    """Mock Camunda External Task for v1-style worker tests.

    V2 workers don't use this pattern (they take dict directly),
    but v1 tests may still reference it. This provides compatibility.

    Returns:
        MagicMock with common task methods (get_variable, complete, bpmn_error, etc.)
    """
    task = MagicMock()
    task.get_variable = MagicMock(return_value=None)
    task.complete = AsyncMock()
    task.bpmn_error = AsyncMock()
    task.handle_failure = AsyncMock()
    task.variables = {}
    task.id = "task-123"
    task.worker_id = "worker-456"
    task.topic_name = "test-topic"
    return task
