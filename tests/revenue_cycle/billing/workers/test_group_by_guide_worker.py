"""Tests for GroupByGuideWorker."""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from platform.revenue_cycle.billing.workers.group_by_guide_worker import GroupByGuideWorker
from platform.shared.domain.enums import TISSGuideType
from platform.shared.domain.exceptions import BillingException


@pytest.fixture
def worker():
    """Create worker instance."""
    return GroupByGuideWorker()


@pytest.fixture
def sample_procedures() -> List[Dict[str, Any]]:
    """Create sample procedures."""
    return [
        {
            "code": "10101012",
            "type": "consultation",
            "quantity": 1,
            "description": "Consulta médica"
        },
        {
            "code": "20101015",
            "type": "exam",
            "quantity": 2,
            "description": "Exame de sangue"
        },
        {
            "code": "30502012",
            "type": "surgery",
            "quantity": 1,
            "description": "Cirurgia cardíaca"
        },
        {
            "code": "10101013",
            "type": "consulta",
            "quantity": 1,
            "description": "Consulta de retorno"
        },
        {
            "code": "80000036",
            "type": "admission",
            "quantity": 1,
            "description": "Internação hospitalar"
        }
    ]


@pytest.fixture
def mock_job():
    """Create mock job."""
    job = MagicMock()
    job.variables = {}
    return job


class TestGroupByGuideWorker:
    """Tests for GroupByGuideWorker."""

    @pytest.mark.asyncio
    async def test_operation_name(self, worker):
        """Test operation name is set."""
        assert worker.operation_name == "Agrupar procedimentos por guia TISS"

    @pytest.mark.asyncio
    async def test_process_task_success(self, worker, mock_job, sample_procedures):
        """Test successful procedure grouping."""
        variables = {
            "encounter_id": "enc-123",
            "procedures": sample_procedures
        }

        result = await worker.process_task(mock_job, variables)

        assert result.success is True
        assert "grouped_guides" in result.variables
        assert "guide_count" in result.variables
        assert "total_procedures" in result.variables

        grouped = result.variables["grouped_guides"]
        assert TISSGuideType.CONSULTATION.value in grouped
        assert TISSGuideType.SP_SADT.value in grouped
        assert TISSGuideType.ADMISSION.value in grouped

        # Check consultation procedures
        consultation_procs = grouped[TISSGuideType.CONSULTATION.value]
        assert len(consultation_procs) == 2

        # Check SP_SADT procedures (exams and surgery)
        spsadt_procs = grouped[TISSGuideType.SP_SADT.value]
        assert len(spsadt_procs) == 2

        # Check admission procedures
        admission_procs = grouped[TISSGuideType.ADMISSION.value]
        assert len(admission_procs) == 1

    @pytest.mark.asyncio
    async def test_missing_encounter_id(self, worker, mock_job, sample_procedures):
        """Test error when encounter_id is missing."""
        variables = {
            "procedures": sample_procedures
        }

        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "MISSING_ENCOUNTER_ID"
        assert exc_info.value.retryable is False

    @pytest.mark.asyncio
    async def test_missing_procedures(self, worker, mock_job):
        """Test error when procedures are missing."""
        variables = {
            "encounter_id": "enc-123"
        }

        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "MISSING_PROCEDURES"
        assert exc_info.value.retryable is False

    @pytest.mark.asyncio
    async def test_invalid_procedures_format(self, worker, mock_job):
        """Test error when procedures is not a list."""
        variables = {
            "encounter_id": "enc-123",
            "procedures": "not-a-list"
        }

        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "INVALID_PROCEDURES_FORMAT"

    @pytest.mark.asyncio
    async def test_missing_procedure_code(self, worker, mock_job):
        """Test error when procedure code is missing."""
        variables = {
            "encounter_id": "enc-123",
            "procedures": [
                {
                    "type": "consultation",
                    "quantity": 1
                }
            ]
        }

        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "MISSING_PROCEDURE_CODE"

    @pytest.mark.asyncio
    async def test_missing_procedure_type(self, worker, mock_job):
        """Test error when procedure type is missing."""
        variables = {
            "encounter_id": "enc-123",
            "procedures": [
                {
                    "code": "10101012",
                    "quantity": 1
                }
            ]
        }

        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        assert exc_info.value.bpmn_error_code == "MISSING_PROCEDURE_TYPE"

    @pytest.mark.asyncio
    async def test_procedure_type_mapping(self, worker, mock_job):
        """Test various procedure type mappings."""
        procedures = [
            {"code": "10101012", "type": "consultation", "quantity": 1},
            {"code": "10101013", "type": "consulta", "quantity": 1},
            {"code": "10101014", "type": "ambulatory", "quantity": 1},
            {"code": "20101015", "type": "exam", "quantity": 1},
            {"code": "20101016", "type": "exame", "quantity": 1},
            {"code": "20101017", "type": "lab", "quantity": 1},
            {"code": "80000036", "type": "admission", "quantity": 1},
            {"code": "80000037", "type": "internacao", "quantity": 1},
        ]

        variables = {
            "encounter_id": "enc-123",
            "procedures": procedures
        }

        result = await worker.process_task(mock_job, variables)

        grouped = result.variables["grouped_guides"]

        # All consultation types should be grouped together
        consultation_count = len(grouped.get(TISSGuideType.CONSULTATION.value, []))
        assert consultation_count == 3

        # All exam/lab types should be in SP_SADT
        spsadt_count = len(grouped.get(TISSGuideType.SP_SADT.value, []))
        assert spsadt_count == 3

        # All admission types should be grouped together
        admission_count = len(grouped.get(TISSGuideType.ADMISSION.value, []))
        assert admission_count == 2

    @pytest.mark.asyncio
    async def test_code_based_classification(self, worker, mock_job):
        """Test classification based on TUSS code patterns."""
        procedures = [
            {"code": "10000001", "type": "unknown", "quantity": 1},  # Starts with 1
            {"code": "20000002", "type": "unknown", "quantity": 1},  # Starts with 2
            {"code": "30000003", "type": "unknown", "quantity": 1},  # Starts with 3
            {"code": "40000004", "type": "unknown", "quantity": 1},  # Starts with 4
        ]

        variables = {
            "encounter_id": "enc-123",
            "procedures": procedures
        }

        result = await worker.process_task(mock_job, variables)

        grouped = result.variables["grouped_guides"]

        # Code starting with 1 should be consultation
        assert any(
            p["code"] == "10000001"
            for p in grouped.get(TISSGuideType.CONSULTATION.value, [])
        )

        # Codes starting with 2, 3, 4 should be SP_SADT
        spsadt_codes = [
            p["code"]
            for p in grouped.get(TISSGuideType.SP_SADT.value, [])
        ]
        assert "20000002" in spsadt_codes
        assert "30000003" in spsadt_codes
        assert "40000004" in spsadt_codes

    @pytest.mark.asyncio
    async def test_procedure_enrichment(self, worker, mock_job):
        """Test that procedures are enriched with coded values."""
        procedures = [
            {
                "code": "10101012",
                "type": "consultation",
                "quantity": 2,
                "description": "Consulta médica"
            }
        ]

        variables = {
            "encounter_id": "enc-123",
            "procedures": procedures
        }

        result = await worker.process_task(mock_job, variables)

        grouped = result.variables["grouped_guides"]
        consultation_procs = grouped[TISSGuideType.CONSULTATION.value]

        proc = consultation_procs[0]
        assert "coded_value" in proc
        assert proc["coded_value"]["code"] == "10101012"
        assert proc["coded_value"]["system"] is not None
        assert proc["quantity"] == 2

    @pytest.mark.asyncio
    async def test_empty_procedures_list(self, worker, mock_job):
        """Test handling of empty procedures list."""
        variables = {
            "encounter_id": "enc-123",
            "procedures": []
        }

        # Should still succeed but with no groups
        with pytest.raises(BillingException) as exc_info:
            await worker.process_task(mock_job, variables)

        # Actually, empty list should raise an error
        assert exc_info.value.bpmn_error_code == "MISSING_PROCEDURES"

    @pytest.mark.asyncio
    async def test_special_guide_types(self, worker, mock_job):
        """Test classification of special guide types."""
        procedures = [
            {"code": "90000001", "type": "extension", "quantity": 1},
            {"code": "90000002", "type": "extensao", "quantity": 1},
            {"code": "90000003", "type": "honorarios", "quantity": 1},
            {"code": "90000004", "type": "summary", "quantity": 1},
        ]

        variables = {
            "encounter_id": "enc-123",
            "procedures": procedures
        }

        result = await worker.process_task(mock_job, variables)

        grouped = result.variables["grouped_guides"]

        # Check extension procedures
        assert TISSGuideType.EXTENSION.value in grouped
        assert len(grouped[TISSGuideType.EXTENSION.value]) == 2

        # Check honorarios
        assert TISSGuideType.HONORARIOS.value in grouped
        assert len(grouped[TISSGuideType.HONORARIOS.value]) == 1

        # Check summary
        assert TISSGuideType.SUMMARY.value in grouped
        assert len(grouped[TISSGuideType.SUMMARY.value]) == 1

    @pytest.mark.asyncio
    async def test_guide_count_statistics(self, worker, mock_job, sample_procedures):
        """Test that statistics are correctly calculated."""
        variables = {
            "encounter_id": "enc-123",
            "procedures": sample_procedures
        }

        result = await worker.process_task(mock_job, variables)

        assert result.variables["guide_count"] == 3  # CONSULTATION, SP_SADT, ADMISSION
        assert result.variables["total_procedures"] == 5
        assert result.variables["encounter_id"] == "enc-123"
