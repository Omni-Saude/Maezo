"""
RegistrarProcedimentoWorker - Zeebe worker for medical procedure registration.

This worker registers medical procedures using TUSS codes.

Topic: registrar-procedimento
BPMN Task: Task_Registrar_Procedimento

Business Rule: RN-RegistrarProcedimentoDelegate.md (RN-CLINICAL-008)
Regulatory Compliance: ANS RN 338/2013, TUSS standards, CBHPM classification
Migrated from: com.hospital.revenuecycle.delegates.clinical.RegistrarProcedimentoDelegate
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog

from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.clinical.clinical_models import (
    RegisterProcedimentoInput,
    RegisterProcedimentoOutput,
)

logger = structlog.get_logger(__name__)


@worker(topic="registrar-procedimento", max_jobs=8, lock_duration=30000)
class RegistrarProcedimentoWorker(BaseWorker):
    """
    Zeebe worker for registering medical procedures.

    BPMN Task: Task_Registrar_Procedimento
    Topic: registrar-procedimento

    This worker:
    - Registers medical procedures with TUSS codes
    - Tracks procedure quantity
    - Associates with provider and encounter

    Input Variables:
        - encounterId: Encounter identifier (required)
        - procedureCode: TUSS procedure code (required)
        - procedureDescription: Procedure description (optional)
        - quantity: Quantity of procedures (default: 1)
        - procedureDate: Procedure date (required)
        - providerId: Provider identifier (required)
        - tenantId: Tenant identifier (required)

    Output Variables:
        - procedureId: Generated procedure identifier
        - encounterId: Encounter identifier
        - procedureCode: TUSS code
        - registrationStatus: Status of registration
        - registrationTimestamp: Registration timestamp
    """

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "registrar_procedimento"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the procedure registration task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with procedure registration details
        """
        self._logger.info(
            "Processing procedure registration",
            encounter_id=variables.get("encounterId"),
            procedure_code=variables.get("procedureCode"),
        )

        try:
            # Validate input
            input_data = RegisterProcedimentoInput(**variables)

            # Validate procedure code
            is_valid = await self._validate_tuss_code(input_data.procedure_code)
            if not is_valid:
                return WorkerResult.failure(
                    error_message=f"Invalid TUSS code: {input_data.procedure_code}",
                    retry=False,
                )

            # Generate procedure ID
            procedure_id = await self._generate_procedure_id(
                input_data.encounter_id,
                input_data.procedure_code,
            )

            output = RegisterProcedimentoOutput(
                procedureId=procedure_id,
                encounterId=input_data.encounter_id,
                procedureCode=input_data.procedure_code,
                registrationStatus="REGISTERED",
                registrationTimestamp=datetime.utcnow(),
            )

            self._logger.info(
                "Procedure registered successfully",
                procedure_id=procedure_id,
                encounter_id=input_data.encounter_id,
                procedure_code=input_data.procedure_code,
                quantity=input_data.quantity,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except Exception as e:
            self._logger.error(
                "Error registering procedure",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Procedure registration failed: {e}",
                retry=True,
            )

    async def _validate_tuss_code(self, code: str) -> bool:
        """Validate TUSS procedure code format."""
        # TUSS codes are typically numeric strings
        return code.isdigit() and len(code) >= 3

    async def _generate_procedure_id(
        self,
        encounter_id: str,
        procedure_code: str,
    ) -> str:
        """Generate unique procedure ID."""
        unique_id = str(uuid4())[:8].upper()
        return f"PROC-{procedure_code}-{unique_id}"
