"""
RegisterEncounterWorker - Zeebe worker for clinical encounter registration.

This worker registers a new clinical encounter in the system.

Topic: register-encounter
BPMN Task: Task_Register_Encounter

Business Rule: RN-RegisterEncounterDelegate.md (RN-CLINICAL-007)
Regulatory Compliance: HL7 v2.5, HL7 FHIR R4, CFM Resolution 1821/2007
Migrated from: com.hospital.revenuecycle.delegates.clinical.RegisterEncounterDelegate
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog

from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.clinical.clinical_models import (
    RegisterEncounterInput,
    RegisterEncounterOutput,
)

logger = structlog.get_logger(__name__)


@worker(topic="register-encounter", max_jobs=8, lock_duration=30000)
class RegisterEncounterWorker(BaseWorker):
    """
    Zeebe worker for registering clinical encounters.

    BPMN Task: Task_Register_Encounter
    Topic: register-encounter

    This worker:
    - Registers a new clinical encounter
    - Assigns encounter ID
    - Sets admission date
    - Validates encounter type

    Input Variables:
        - patientId: Patient identifier (required)
        - appointmentId: Appointment identifier (required)
        - encounterType: Type of encounter (required)
        - providerId: Healthcare provider identifier (required)
        - facilityId: Facility identifier (optional)
        - tenantId: Tenant identifier (required)

    Output Variables:
        - encounterId: Generated encounter identifier
        - patientId: Patient identifier
        - registrationStatus: Status of registration
        - admissionDate: Encounter admission date
        - encounterType: Type of encounter
        - registrationTimestamp: Registration timestamp
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "register_encounter"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the encounter registration task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with encounter registration details
        """
        self._logger.info(
            "Processing encounter registration",
            patient_id=variables.get("patientId"),
            appointment_id=variables.get("appointmentId"),
        )

        try:
            # Validate input
            input_data = RegisterEncounterInput(**variables)

            # Generate encounter ID
            encounter_id = await self._generate_encounter_id(
                input_data.patient_id,
                input_data.appointment_id,
            )

            # Register encounter
            admission_date = datetime.utcnow()

            output = RegisterEncounterOutput(
                encounterId=encounter_id,
                patientId=input_data.patient_id,
                registrationStatus="REGISTERED",
                admissionDate=admission_date,
                encounterType=input_data.encounter_type,
                registrationTimestamp=datetime.utcnow(),
            )

            self._logger.info(
                "Encounter registered successfully",
                encounter_id=encounter_id,
                patient_id=input_data.patient_id,
                encounter_type=input_data.encounter_type.value,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except Exception as e:
            self._logger.error(
                "Error registering encounter",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Encounter registration failed: {e}",
                retry=True,
            )

    async def _generate_encounter_id(
        self,
        patient_id: str,
        appointment_id: str,
    ) -> str:
        """Generate unique encounter ID."""
        # Format: ENC-{YYYY}{MM}{DD}-{UNIQUEID}
        timestamp = datetime.utcnow()
        date_str = timestamp.strftime("%Y%m%d")
        unique_id = str(uuid4())[:8].upper()
        return f"ENC-{date_str}-{unique_id}"
