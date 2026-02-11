"""
Surgical Materials Worker

CIB7 External Task Topic: surgical.materials
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Checks availability and reserves surgical materials and supplies for
scheduled procedures via TASY adapter integration.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import DomainException
from healthcare_platform.shared.integrations.tasy_adapters.surgical_adapter import (
    TasySurgicalAdapter,
)
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


def _(message: str) -> str:
    """Translation helper for Portuguese error messages."""
    return message


class ClinicalOperationsException(DomainException):
    """Exception for clinical operations errors."""

    def __init__(
        self, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(
            message=message,
            details=details,
            bpmn_error_code="CLINICAL_OPERATIONS_ERROR",
        )
        self.code = "CLINICAL_OPERATIONS_ERROR"


class Material(BaseModel):
    """Model for surgical material request."""

    material_code: str = Field(..., description="TASY material/supply code")
    quantity: int = Field(..., ge=1, description="Quantity requested")


class MaterialReserved(BaseModel):
    """Model for reserved surgical material."""

    material_code: str = Field(..., description="TASY material/supply code")
    quantity: int = Field(..., description="Quantity reserved")
    available: bool = Field(..., description="Whether material is available")


class SurgicalMaterialsInput(BaseModel):
    """Input model for surgical materials reservation."""

    surgery_id: str = Field(..., description="TASY surgery schedule ID")
    procedure_code: str = Field(..., description="TASY procedure code")
    materials: list[Material] = Field(
        ..., min_length=1, description="List of materials to reserve"
    )
    priority: str = Field(
        ...,
        pattern="^(routine|urgent|stat)$",
        description="Material request priority",
    )


class SurgicalMaterialsOutput(BaseModel):
    """Output model for surgical materials reservation."""

    request_id: str = Field(..., description="TASY materials request ID")
    surgery_id: str = Field(..., description="TASY surgery schedule ID")
    materials_reserved: list[MaterialReserved] = Field(
        ..., description="List of materials with availability status"
    )
    all_available: bool = Field(
        ..., description="Whether all requested materials are available"
    )
    reserved_at: str = Field(
        ..., description="ISO 8601 timestamp when materials reserved"
    )


class SurgicalMaterialsWorker:
    """
    Worker to check and reserve surgical materials.

    Validates material requests, checks inventory availability via TASY,
    and reserves materials for scheduled procedures.
    """

    TOPIC = "surgical.materials"

    def __init__(self, tasy_adapter: TasySurgicalAdapter | None = None) -> None:
        """
        Initialize worker with TASY surgical adapter.

        Args:
            tasy_adapter: TASY surgical adapter for materials management.
                         Defaults to stub implementation for testing.
        """
        self._tasy_adapter = tasy_adapter

    @require_tenant
    @track_task_execution(task_type="surgical.materials")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute surgical materials reservation.

        Args:
            task_variables: Task variables containing materials request details

        Returns:
            Dictionary with reservation results

        Raises:
            ClinicalOperationsException: If materials reservation fails
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = SurgicalMaterialsInput.model_validate(task_variables)
        except Exception as e:
            logger.error(
                "Validation failed for surgical materials input",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos para reserva de materiais cirúrgicos"),
                details={"validation_error": str(e)},
            ) from e

        # Log materials request
        logger.info(
            "Processing surgical materials reservation",
            extra={
                "tenant_id": tenant.tenant_id,
                "surgery_id": input_data.surgery_id,
                "procedure_code": input_data.procedure_code,
                "materials_count": len(input_data.materials),
                "priority": input_data.priority,
            },
        )

        # Call TASY API to check availability and reserve materials
        try:
            tasy_data = await self._call_tasy_api(input_data)

            # Use adapter to convert TASY data to FHIR if needed
            if self._tasy_adapter:
                adapted_data = await self._tasy_adapter.adapt(tasy_data)
                logger.debug(
                    "Adapted TASY materials reservation to FHIR",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "request_id": tasy_data["request_id"],
                    },
                )
            else:
                adapted_data = tasy_data

            # Check if all materials are available
            all_available = all(
                mat["available"] for mat in adapted_data["materials_reserved"]
            )

            if not all_available:
                logger.warning(
                    "Some surgical materials unavailable",
                    extra={
                        "tenant_id": tenant.tenant_id,
                        "surgery_id": input_data.surgery_id,
                        "request_id": adapted_data["request_id"],
                        "unavailable_count": sum(
                            1
                            for mat in adapted_data["materials_reserved"]
                            if not mat["available"]
                        ),
                    },
                )

            logger.info(
                "Surgical materials reservation processed",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "surgery_id": input_data.surgery_id,
                    "request_id": adapted_data["request_id"],
                    "all_available": all_available,
                },
            )

            # Build output
            output = SurgicalMaterialsOutput(
                request_id=adapted_data["request_id"],
                surgery_id=adapted_data["surgery_id"],
                materials_reserved=adapted_data["materials_reserved"],
                all_available=all_available,
                reserved_at=datetime.now(UTC).isoformat(),
            )

            return output.model_dump()

        except Exception as e:
            logger.error(
                "Failed to reserve surgical materials",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "surgery_id": input_data.surgery_id,
                    "procedure_code": input_data.procedure_code,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Falha ao reservar materiais cirúrgicos"),
                details={
                    "surgery_id": input_data.surgery_id,
                    "procedure_code": input_data.procedure_code,
                    "error": str(e),
                },
            ) from e

    async def _call_tasy_api(
        self, input_data: SurgicalMaterialsInput
    ) -> dict[str, Any]:
        """
        Call TASY API to check and reserve materials (stub implementation).

        Args:
            input_data: Validated materials request input

        Returns:
            Mock TASY materials reservation data
        """
        # Stub: In production, this would call TASY REST API
        # For now, return mock data that matches TASY schema
        # Simulate 90% availability rate
        materials_reserved = [
            {
                "material_code": material.material_code,
                "quantity": material.quantity,
                "available": hash(material.material_code) % 10 != 0,  # 90% available
            }
            for material in input_data.materials
        ]

        return {
            "operation_type": "material_request",
            "request_id": f"MAT-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
            "surgery_id": input_data.surgery_id,
            "procedure_code": input_data.procedure_code,
            "materials_reserved": materials_reserved,
            "priority": input_data.priority,
        }
