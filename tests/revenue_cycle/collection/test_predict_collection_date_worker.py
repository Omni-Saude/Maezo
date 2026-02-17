from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.predict_collection_date_worker import PredictCollectionDateWorker


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.predict_collection_date_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.predict_collection_date_worker.FederatedDMNService')
class TestPredictCollectionDateWorker:
    """Tests for PredictCollectionDateWorker."""

    async def test_predict_collection_date_with_ml(self, mock_dmn_service, mock_tenant):
        """Test prediction with sufficient historical data for ML."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            'strategy': 'standard_followup',
            'priority': 'medium',
        }
        mock_dmn_service.return_value = mock_dmn

        worker = PredictCollectionDateWorker()
        worker.dmn_service = mock_dmn

        job = MagicMock()
        job.variables = {
            "claim_id": "CLAIM-001",
            "payer_id": "PAYER-001",
            "claim_amount": 35000.00,
            "claim_date": date.today().isoformat(),
            "claim_type": "standard",
            "historical_data": [
                {"days": 45, "amount": 30000.00},
                {"days": 50, "amount": 35000.00},
                {"days": 48, "amount": 32000.00},
            ],
        }

        result = await worker.execute(job)

        assert result.success is True
        assert result.variables["claim_id"] == "CLAIM-001"
        assert result.variables["predicted_collection_date"] is not None
        assert 30 <= result.variables["predicted_days"] <= 180
        assert 0 <= result.variables["confidence"] <= 1

    async def test_predict_collection_date_insufficient_data(self, mock_dmn_service, mock_tenant):
        """Test prediction with insufficient historical data."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            'strategy': 'conservative',
            'priority': 'low',
        }
        mock_dmn_service.return_value = mock_dmn

        worker = PredictCollectionDateWorker()
        worker.dmn_service = mock_dmn

        job = MagicMock()
        job.variables = {
            "claim_id": "CLAIM-002",
            "payer_id": "PAYER-002",
            "claim_amount": 50000.00,
            "claim_date": date.today().isoformat(),
            "historical_data": [
                {"days": 45, "amount": 30000.00},
            ],  # Only 1 sample
        }

        result = await worker.execute(job)

        assert result.success is True
        assert result.variables["model_type"] == "average"
        assert result.variables["confidence"] == 0.5

    async def test_predict_collection_date_days_bounded(self, mock_dmn_service, mock_tenant):
        """Test that predicted days are bounded to reasonable range."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {
            'strategy': 'aggressive',
            'priority': 'high',
        }
        mock_dmn_service.return_value = mock_dmn

        worker = PredictCollectionDateWorker()
        worker.dmn_service = mock_dmn

        job = MagicMock()
        job.variables = {
            "claim_id": "CLAIM-003",
            "payer_id": "PAYER-003",
            "claim_amount": 100000.00,  # Very high amount
            "claim_date": date.today().isoformat(),
        }

        result = await worker.execute(job)

        assert result.success is True
        # Should be bounded between 30-180 days
        assert 30 <= result.variables["predicted_days"] <= 180
