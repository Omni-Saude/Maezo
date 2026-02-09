"""
PacsIntegrationWorker - Zeebe worker for PACS (Picture Archiving and Communication System) integration.

This worker integrates with PACS to retrieve medical imaging studies.

Topic: pacs-integration
BPMN Task: Task_PACS_Integration

Business Rule: RN-PACSIntegrationDelegate.md (RN-CLINICAL-006)
Regulatory Compliance: DICOM standard, HL7 FHIR R4 ImagingStudy, ANS imaging documentation
Migrated from: com.hospital.revenuecycle.delegates.clinical.PACSIntegrationDelegate
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.clinical.clinical_models import (
    PacsIntegrationInput,
    PacsIntegrationOutput,
    ImagingResult,
    ImagingStatus,
)

logger = structlog.get_logger(__name__)


@worker(topic="pacs-integration", max_jobs=8, lock_duration=30000)
class PacsIntegrationWorker(BaseWorker):
    """
    Zeebe worker for PACS integration.

    BPMN Task: Task_PACS_Integration
    Topic: pacs-integration

    This worker:
    - Retrieves imaging studies from PACS
    - Collects imaging results and reports
    - Handles missing studies
    - Tracks integration status

    Input Variables:
        - encounterId: Encounter identifier (required)
        - studyIds: List of study identifiers (required)
        - tenantId: Tenant identifier (required)

    Output Variables:
        - encounterId: Encounter identifier
        - imagingResults: List of imaging results
        - integrationStatus: Status of integration
        - integrationTimestamp: Integration timestamp
        - missingStudies: List of missing study IDs
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "pacs_integration"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the PACS integration task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with imaging results
        """
        self._logger.info(
            "Processing PACS integration",
            encounter_id=variables.get("encounterId"),
        )

        try:
            # Validate input
            input_data = PacsIntegrationInput(**variables)

            # Retrieve imaging studies
            imaging_results = []
            missing_studies = []

            for study_id in input_data.study_ids:
                result = await self._retrieve_imaging_study(study_id)
                if result:
                    imaging_results.append(result)
                else:
                    missing_studies.append(study_id)

            # Determine integration status
            status = "SUCCESS" if not missing_studies else "PARTIAL"

            output = PacsIntegrationOutput(
                encounterId=input_data.encounter_id,
                imagingResults=imaging_results,
                integrationStatus=status,
                integrationTimestamp=datetime.utcnow(),
                missingStudies=missing_studies,
            )

            self._logger.info(
                "PACS integration completed",
                encounter_id=input_data.encounter_id,
                studies_retrieved=len(imaging_results),
                missing_studies=len(missing_studies),
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except Exception as e:
            self._logger.error(
                "Error in PACS integration",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"PACS integration failed: {e}",
                retry=True,
            )

    async def _retrieve_imaging_study(self, study_id: str) -> ImagingResult | None:
        """Retrieve an imaging study by ID."""
        # Mock implementation - in real scenario, query PACS system
        if study_id.startswith("STUDY-"):
            return ImagingResult(
                studyId=study_id,
                studyType="CT",
                studyDate=datetime.utcnow(),
                status=ImagingStatus.REPORTED,
                report="Normal findings",
                dicomUrl=f"dicom://{study_id}",
            )
        return None
