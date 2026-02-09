"""Tests for DetectRevenueLeakageWorker."""
from __future__ import annotations

import pytest

from platform.revenue_cycle.collection.workers.detect_revenue_leakage_worker import (
    DetectRevenueLeakageWorker,
)


@pytest.mark.asyncio
async def test_detect_revenue_leakage_all_categories():
    """Test detection of all leakage categories."""
    worker = DetectRevenueLeakageWorker()

    task_variables = {
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

    result = await worker.execute(task_variables)

    assert len(result["leakages"]) == 4
    assert result["total_potential_recovery"] == 15000.0
    assert result["total_opportunities"] == 5

    # Check categories
    categories = [leak["category"] for leak in result["leakages"]]
    assert "unbilled_encounters" in categories
    assert "undercoded_procedures" in categories
    assert "uncollected_approvals" in categories
    assert "expired_authorizations" in categories


@pytest.mark.asyncio
async def test_detect_revenue_leakage_partial():
    """Test detection with only some categories."""
    worker = DetectRevenueLeakageWorker()

    task_variables = {
        "unbilled_encounters": [
            {"encounter_id": "enc-1", "estimated_value": 5000.0},
        ],
        "undercoded_procedures": [],
        "uncollected_approvals": [],
        "expired_authorizations": [],
    }

    result = await worker.execute(task_variables)

    assert len(result["leakages"]) == 1
    assert result["total_potential_recovery"] == 5000.0
    assert result["leakages"][0]["category"] == "unbilled_encounters"


@pytest.mark.asyncio
async def test_detect_revenue_leakage_none():
    """Test handling when no leakage is detected."""
    worker = DetectRevenueLeakageWorker()

    task_variables = {
        "unbilled_encounters": [],
        "undercoded_procedures": [],
        "uncollected_approvals": [],
        "expired_authorizations": [],
    }

    result = await worker.execute(task_variables)

    assert result["leakages"] == []
    assert result["total_potential_recovery"] == 0.0
    assert result["total_opportunities"] == 0


@pytest.mark.asyncio
async def test_detect_revenue_leakage_priority_assignment():
    """Test priority assignment based on amount."""
    worker = DetectRevenueLeakageWorker()

    task_variables = {
        "unbilled_encounters": [
            {"encounter_id": "enc-1", "estimated_value": 15000.0},  # High priority
        ],
        "undercoded_procedures": [
            {"procedure_id": "proc-1", "potential_increase": 500.0},  # Medium
        ],
    }

    result = await worker.execute(task_variables)

    unbilled_leak = next(
        l for l in result["leakages"] if l["category"] == "unbilled_encounters"
    )
    assert unbilled_leak["priority"] == "high"

    undercoded_leak = next(
        l for l in result["leakages"] if l["category"] == "undercoded_procedures"
    )
    assert undercoded_leak["priority"] == "medium"
