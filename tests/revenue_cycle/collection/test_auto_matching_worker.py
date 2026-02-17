"""Tests for AutoMatchingWorker."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from healthcare_platform.revenue_cycle.collection.workers.auto_matching_worker import AutoMatchingWorker


@pytest.fixture
def worker():
    """Create worker instance."""
    return AutoMatchingWorker()


@pytest.fixture
def available_claims():
    """Sample claims for matching."""
    return [
        {
            "claim_id": "claim-001",
            "protocol_number": "TISS-12345",
            "invoice_number": "INV-001",
            "patient_id": "patient-001",
            "total_amount": 1000.00,
        },
        {
            "claim_id": "claim-002",
            "protocol_number": "TISS-67890",
            "nosso_numero": "NN-002",
            "patient_id": "patient-002",
            "total_amount": 2000.00,
        },
        {
            "claim_id": "claim-003",
            "invoice_number": "INV-003",
            "patient_id": "patient-001",
            "total_amount": 1500.00,
        },
    ]


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.auto_matching_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.auto_matching_worker.FederatedDMNService')
async def test_match_by_protocol_success(MockDMNService, mock_tenant, available_claims):
    """Test successful match by protocol number."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {
        'matched': True,
        'claimId': 'claim-001',
        'matchMethod': 'protocol',
        'confidenceScore': 0.95,
        'allocationId': 'alloc-123'
    }

    worker = AutoMatchingWorker()
    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "protocol_number": "TISS-12345",
        "payment_amount": 1000.00,
        "currency": "BRL",
        "available_claims": available_claims,
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["matched"] is True
    assert result.variables["claim_id"] == "claim-001"
    assert result.variables["match_method"] == "protocol"
    assert result.variables["confidence_score"] == 0.95
    assert result.variables["allocation_id"] is not None


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.auto_matching_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.auto_matching_worker.FederatedDMNService')
async def test_match_by_invoice_success(MockDMNService, mock_tenant, available_claims):
    """Test successful match by invoice number."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {
        'matched': True,
        'claimId': 'claim-003',
        'matchMethod': 'invoice',
        'confidenceScore': 0.85,
        'allocationId': 'alloc-456'
    }

    worker = AutoMatchingWorker()
    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "invoice_number": "INV-003",
        "payment_amount": 1500.00,
        "currency": "BRL",
        "available_claims": available_claims,
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["matched"] is True
    assert result.variables["claim_id"] == "claim-003"
    assert result.variables["match_method"] == "invoice"
    assert result.variables["confidence_score"] == 0.85


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.auto_matching_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.auto_matching_worker.FederatedDMNService')
async def test_match_by_patient_success(MockDMNService, mock_tenant, available_claims):
    """Test successful match by patient ID and amount."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {
        'matched': True,
        'claimId': 'claim-001',
        'matchMethod': 'patient',
        'confidenceScore': 0.70,
        'allocationId': 'alloc-789'
    }

    worker = AutoMatchingWorker()
    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "patient_id": "patient-001",
        "payment_amount": 1020.00,  # Within 5% of 1000.00
        "currency": "BRL",
        "available_claims": available_claims,
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["matched"] is True
    assert result.variables["claim_id"] == "claim-001"
    assert result.variables["match_method"] == "patient"
    assert result.variables["confidence_score"] >= 0.50


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.auto_matching_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.auto_matching_worker.FederatedDMNService')
async def test_no_match_found(MockDMNService, mock_tenant, available_claims):
    """Test when no match is found."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {
        'matched': False,
        'claimId': None,
        'matchMethod': 'none',
        'confidenceScore': 0.0,
        'allocationId': None
    }

    worker = AutoMatchingWorker()
    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "protocol_number": "TISS-99999",
        "payment_amount": 5000.00,
        "currency": "BRL",
        "available_claims": available_claims,
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["matched"] is False
    assert result.variables["claim_id"] is None
    assert result.variables["match_method"] == "none"
    assert result.variables["confidence_score"] == 0.0


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.auto_matching_worker.get_required_tenant', return_value='test-tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.auto_matching_worker.FederatedDMNService')
async def test_empty_claims_list(MockDMNService, mock_tenant):
    """Test with no available claims."""
    mock_dmn = MockDMNService.return_value
    mock_dmn.evaluate.return_value = {
        'matched': False,
        'claimId': None,
        'matchMethod': 'none',
        'confidenceScore': 0.0,
        'allocationId': None
    }

    worker = AutoMatchingWorker()
    job = MagicMock()
    job.variables = {
        "payment_id": str(uuid4()),
        "protocol_number": "TISS-12345",
        "payment_amount": 1000.00,
        "currency": "BRL",
        "available_claims": [],
    }

    result = await worker.execute(job)

    assert result.success
    assert result.variables["matched"] is False
    assert result.variables["claim_id"] is None
