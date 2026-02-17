"""Tests for DetectRevenueLeakageWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.detect_revenue_leakage_worker import (
    DetectRevenueLeakageWorker,
)


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_revenue_leakage_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_revenue_leakage_worker.FederatedDMNService")
async def test_detect_revenue_leakage_all_categories(mock_dmn_service_cls, mock_tenant):
    """Test detection of all leakage categories."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {
        "unbilledPriority": "high",
    }
    mock_dmn_service_cls.return_value = mock_dmn

    worker = DetectRevenueLeakageWorker()
    job = MagicMock()
    job.variables = {
        "unbilled_encounters": [
            {"encounter_id": "enc-1", "estimated_value": 5000.0},
            {"encounter_id": "enc-2", "estimated_value": 3000.0},
        ],
        "undercoded_procedures": [
            {"procedure_id": "proc-1", "potential_increase": 1000.0},
        ],
        "uncollected_approvals": [
            {"approval_id": "app-1", "approved_amount": 2000.0},
        ],
        "expired_authorizations": [
            {"authorization_id": "auth-1", "authorized_amount": 4000.0},
        ],
    }

    result = await worker.execute(job)

    assert result.success
    assert len(result.variables["leakages"]) == 4
    assert result.variables["total_potential_recovery"] == 15000.0
    assert result.variables["total_opportunities"] == 5

    # Check categories
    categories = [leak["category"] for leak in result.variables["leakages"]]
    assert "unbilled_encounters" in categories
    assert "undercoded_procedures" in categories
    assert "uncollected_approvals" in categories
    assert "expired_authorizations" in categories


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_revenue_leakage_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_revenue_leakage_worker.FederatedDMNService")
async def test_detect_revenue_leakage_partial(mock_dmn_service_cls, mock_tenant):
    """Test detection with only some categories."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {
        "unbilledPriority": "high",
    }
    mock_dmn_service_cls.return_value = mock_dmn

    worker = DetectRevenueLeakageWorker()
    job = MagicMock()
    job.variables = {
        "unbilled_encounters": [
            {"encounter_id": "enc-1", "estimated_value": 5000.0},
        ],
        "undercoded_procedures": [],
        "uncollected_approvals": [],
        "expired_authorizations": [],
    }

    result = await worker.execute(job)

    assert result.success
    assert len(result.variables["leakages"]) == 1
    assert result.variables["total_potential_recovery"] == 5000.0
    assert result.variables["leakages"][0]["category"] == "unbilled_encounters"


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_revenue_leakage_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_revenue_leakage_worker.FederatedDMNService")
async def test_detect_revenue_leakage_none(mock_dmn_service_cls, mock_tenant):
    """Test handling when no leakage is detected."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {}
    mock_dmn_service_cls.return_value = mock_dmn

    worker = DetectRevenueLeakageWorker()
    job = MagicMock()
    job.variables = {
        "unbilled_encounters": [],
        "undercoded_procedures": [],
        "uncollected_approvals": [],
        "expired_authorizations": [],
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["leakages"] == []
    assert result.variables["total_potential_recovery"] == 0.0
    assert result.variables["total_opportunities"] == 0


@pytest.mark.asyncio
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_revenue_leakage_worker.get_required_tenant")
@patch("healthcare_platform.revenue_cycle.collection.workers.detect_revenue_leakage_worker.FederatedDMNService")
async def test_detect_revenue_leakage_priority_assignment(mock_dmn_service_cls, mock_tenant):
    """Test priority assignment based on amount."""
    mock_tenant.return_value = "tenant-1"
    mock_dmn = MagicMock()
    mock_dmn.evaluate.return_value = {
        "unbilledPriority": "high",
    }
    mock_dmn_service_cls.return_value = mock_dmn

    worker = DetectRevenueLeakageWorker()
    job = MagicMock()
    job.variables = {
        "unbilled_encounters": [
            {"encounter_id": "enc-1", "estimated_value": 15000.0},
        ],
        "undercoded_procedures": [
            {"procedure_id": "proc-1", "potential_increase": 500.0},
        ],
    }

    result = await worker.execute(job)

    assert result.success
    unbilled_leak = next(
        l for l in result.variables["leakages"] if l["category"] == "unbilled_encounters"
    )
    assert unbilled_leak["priority"] == "high"

    undercoded_leak = next(
        l for l in result.variables["leakages"] if l["category"] == "undercoded_procedures"
    )
    assert undercoded_leak["priority"] == "medium"
