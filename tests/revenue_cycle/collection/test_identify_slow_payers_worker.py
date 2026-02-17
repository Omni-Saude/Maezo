from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from healthcare_platform.revenue_cycle.collection.workers.identify_slow_payers_worker import IdentifySlowPayersWorker


@pytest.mark.asyncio
@patch('healthcare_platform.revenue_cycle.collection.workers.identify_slow_payers_worker.get_required_tenant')
@patch('healthcare_platform.revenue_cycle.collection.workers.identify_slow_payers_worker.FederatedDMNService')
class TestIdentifySlowPayersWorker:
    """Tests for IdentifySlowPayersWorker."""

    async def test_identify_slow_payers_success(self, mock_dmn_service, mock_tenant):
        """Test successful identification of slow payers."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()

        # First payer is slow
        def evaluate_side_effect(tenant_id, category, table_name, inputs):
            avg_days = inputs.get('avgDaysToPayment', 0)
            payment_count = inputs.get('paymentCount', 0)
            threshold = inputs.get('thresholdDays', 60)
            min_payments = inputs.get('minPayments', 5)

            is_slow = avg_days >= threshold and payment_count >= min_payments
            return {'isSlow': is_slow, 'priority': 'high' if is_slow else 'normal'}

        mock_dmn.evaluate.side_effect = evaluate_side_effect
        mock_dmn_service.return_value = mock_dmn

        worker = IdentifySlowPayersWorker()
        worker.dmn_service = mock_dmn

        job = MagicMock()
        job.variables = {
            "lookback_days": 90,
            "min_payments": 5,
            "threshold_days": 60,
            "payer_stats": [
                {
                    "payer_id": "PAYER-001",
                    "payer_name": "Health Plan A",
                    "avg_days_to_payment": 75,
                    "payment_count": 10,
                    "total_amount": 50000.00,
                    "variance": 15.5,
                },
                {
                    "payer_id": "PAYER-002",
                    "payer_name": "Health Plan B",
                    "avg_days_to_payment": 45,
                    "payment_count": 8,
                    "total_amount": 30000.00,
                    "variance": 10.2,
                },
            ],
        }

        result = await worker.execute(job)

        assert result.success is True
        assert "slow_payers" in result.variables
        assert result.variables["analyzed_payers"] == 2
        # Only first payer should be slow (75 days >= 60 threshold)
        assert len(result.variables["slow_payers"]) == 1
        assert result.variables["slow_payers"][0]["payer_id"] == "PAYER-001"

    async def test_identify_slow_payers_filters_by_threshold(self, mock_dmn_service, mock_tenant):
        """Test that only payers above threshold are included."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()

        def evaluate_side_effect(tenant_id, category, table_name, inputs):
            avg_days = inputs.get('avgDaysToPayment', 0)
            payment_count = inputs.get('paymentCount', 0)
            threshold = inputs.get('thresholdDays', 100)
            min_payments = inputs.get('minPayments', 5)

            is_slow = avg_days >= threshold and payment_count >= min_payments
            return {'isSlow': is_slow}

        mock_dmn.evaluate.side_effect = evaluate_side_effect
        mock_dmn_service.return_value = mock_dmn

        worker = IdentifySlowPayersWorker()
        worker.dmn_service = mock_dmn

        job = MagicMock()
        job.variables = {
            "threshold_days": 100,  # High threshold
            "min_payments": 5,
            "payer_stats": [
                {
                    "payer_id": "PAYER-001",
                    "avg_days_to_payment": 75,
                    "payment_count": 10,
                },
                {
                    "payer_id": "PAYER-002",
                    "avg_days_to_payment": 105,
                    "payment_count": 8,
                },
            ],
        }

        result = await worker.execute(job)

        assert result.success is True
        # Only payer with 105 days should be included
        for payer in result.variables["slow_payers"]:
            assert payer["avg_days_to_payment"] >= 100

    async def test_identify_slow_payers_structure(self, mock_dmn_service, mock_tenant):
        """Test structure of slow payer data."""
        mock_tenant.return_value = 'test_tenant'
        mock_dmn = MagicMock()
        mock_dmn.evaluate.return_value = {'isSlow': True, 'priority': 'high'}
        mock_dmn_service.return_value = mock_dmn

        worker = IdentifySlowPayersWorker()
        worker.dmn_service = mock_dmn

        job = MagicMock()
        job.variables = {
            "payer_stats": [
                {
                    "payer_id": "PAYER-001",
                    "payer_name": "Slow Payer",
                    "avg_days_to_payment": 90,
                    "payment_count": 10,
                    "total_amount": 100000.00,
                    "variance": 20.0,
                }
            ],
        }

        result = await worker.execute(job)

        assert result.success is True
        if result.variables["slow_payers"]:
            payer = result.variables["slow_payers"][0]
            assert "payer_id" in payer
            assert "payer_name" in payer
            assert "avg_days_to_payment" in payer
            assert "payment_count" in payer
            assert "total_amount" in payer
            assert "variance" in payer
