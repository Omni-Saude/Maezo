"""
Surgical Consent Worker

CIB7 External Task Topic: surgical.consent
BPMN Error Code: CLINICAL_OPERATIONS_ERROR

Validates and records surgical consent compliance per Brazilian regulations
(CFM Resolution 2.217/2018) and LGPD requirements. Manages informed consent,
emergency waivers, and minor guardian authorization.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

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


class SurgicalConsentInput(BaseModel):
    """Input model for surgical consent validation."""

    surgery_id: str = Field(..., description="FHIR Procedure ID")
    patient_id: str = Field(..., description="FHIR Patient ID")
    procedure_code: str = Field(..., description="TUSS procedure code")
    procedure_description: str = Field(..., description="Procedure description in Portuguese")
    surgeon_id: str = Field(..., description="FHIR Practitioner ID of surgeon")
    risks: list[str] = Field(
        ..., description="List of procedure risks to be disclosed"
    )
    alternatives: list[str] = Field(
        ..., description="List of alternative treatments"
    )
    consent_type: Literal["informed", "emergency", "minor_guardian"] = Field(
        ..., description="Type of consent required"
    )


class SurgicalConsentOutput(BaseModel):
    """Output model for surgical consent validation."""

    consent_id: str = Field(..., description="Generated consent record ID")
    surgery_id: str = Field(..., description="FHIR Procedure ID")
    patient_id: str = Field(..., description="FHIR Patient ID")
    consent_status: Literal["obtained", "pending", "refused", "waived"] = Field(
        ..., description="Current consent status"
    )
    consent_type: str = Field(..., description="Type of consent")
    obtained_at: str | None = Field(
        None, description="ISO 8601 timestamp when consent obtained"
    )
    witness_required: bool = Field(
        ..., description="Whether witness signature is required"
    )


class SurgicalConsentWorker:
    """
    Worker to validate and record surgical consent compliance.

    Implements Brazilian medical ethics requirements (CFM 2.217/2018):
    - Informed consent with full risk disclosure
    - Emergency consent waiver provisions
    - Minor/incapacitated patient guardian authorization
    - LGPD-compliant data handling

    Ensures all consent requirements are met before surgical procedures.
    """

    TOPIC = "surgical.consent"

    # CFM Resolution 2.217/2018 consent requirements
    CONSENT_REQUIREMENTS = {
        "informed": {
            "requires_risks": True,
            "requires_alternatives": True,
            "requires_witness": False,
            "can_waive": False,
        },
        "emergency": {
            "requires_risks": False,
            "requires_alternatives": False,
            "requires_witness": True,
            "can_waive": True,
        },
        "minor_guardian": {
            "requires_risks": True,
            "requires_alternatives": True,
            "requires_witness": True,
            "can_waive": False,
        },
    }

    def __init__(
        self, tasy_adapter: TasySurgicalAdapter | None = None
    ) -> None:
        """
        Initialize worker with Tasy surgical adapter.

        Args:
            tasy_adapter: Tasy adapter for surgical data conversion.
                         Optional for testing purposes.
        """
        self._tasy_adapter = tasy_adapter

    @require_tenant
    @track_task_execution(task_type="surgical.consent")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute surgical consent validation.

        Args:
            task_variables: Task variables containing consent data

        Returns:
            Dictionary with consent validation results

        Raises:
            ClinicalOperationsException: If validation fails or requirements not met
        """
        tenant = get_required_tenant()

        # Validate input
        try:
            input_data = SurgicalConsentInput.model_validate(task_variables)
        except Exception as e:
            logger.error(
                "Validation failed for surgical consent input",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Dados de entrada inválidos para consentimento cirúrgico"),
                details={"validation_error": str(e)},
            ) from e

        # Log consent processing start (LGPD: no PII in logs)
        logger.info(
            "Processing surgical consent validation",
            extra={
                "tenant_id": tenant.tenant_id,
                "surgery_id": input_data.surgery_id,
                "patient_id": input_data.patient_id,
                "consent_type": input_data.consent_type,
                "procedure_code": input_data.procedure_code,
            },
        )

        # Validate consent requirements
        try:
            validation_result = self._validate_consent_requirements(input_data)

            # Generate consent ID
            consent_id = f"CONSENT-{input_data.surgery_id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

            # Determine consent status
            consent_status = self._determine_consent_status(
                input_data.consent_type, validation_result
            )

            # Record consent timestamp if obtained
            obtained_at = (
                datetime.now(UTC).isoformat()
                if consent_status == "obtained"
                else None
            )

            # Check witness requirement
            witness_required = self.CONSENT_REQUIREMENTS[input_data.consent_type][
                "requires_witness"
            ]

            logger.info(
                "Surgical consent validation completed",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "surgery_id": input_data.surgery_id,
                    "consent_id": consent_id,
                    "consent_status": consent_status,
                    "consent_type": input_data.consent_type,
                    "witness_required": witness_required,
                },
            )

            # Build output
            output = SurgicalConsentOutput(
                consent_id=consent_id,
                surgery_id=input_data.surgery_id,
                patient_id=input_data.patient_id,
                consent_status=consent_status,
                consent_type=input_data.consent_type,
                obtained_at=obtained_at,
                witness_required=witness_required,
            )

            return output.model_dump()

        except Exception as e:
            logger.error(
                "Failed to validate surgical consent",
                extra={
                    "tenant_id": tenant.tenant_id,
                    "surgery_id": input_data.surgery_id,
                    "consent_type": input_data.consent_type,
                    "error": str(e),
                },
            )
            raise ClinicalOperationsException(
                _("Falha na validação do consentimento cirúrgico"),
                details={
                    "surgery_id": input_data.surgery_id,
                    "consent_type": input_data.consent_type,
                    "error": str(e),
                },
            ) from e

    def _validate_consent_requirements(
        self, input_data: SurgicalConsentInput
    ) -> dict[str, Any]:
        """
        Validate consent against CFM requirements.

        Args:
            input_data: Consent input data

        Returns:
            Dictionary with validation results

        Raises:
            ClinicalOperationsException: If consent type is invalid
        """
        consent_type = input_data.consent_type
        if consent_type not in self.CONSENT_REQUIREMENTS:
            raise ClinicalOperationsException(
                _(f"Tipo de consentimento inválido: {consent_type}"),
                details={
                    "consent_type": consent_type,
                    "valid_types": list(self.CONSENT_REQUIREMENTS.keys()),
                },
            )

        requirements = self.CONSENT_REQUIREMENTS[consent_type]
        validation_issues = []

        # Validate risk disclosure requirement
        if requirements["requires_risks"] and not input_data.risks:
            validation_issues.append("risks_disclosure_missing")

        # Validate alternatives disclosure requirement
        if requirements["requires_alternatives"] and not input_data.alternatives:
            validation_issues.append("alternatives_disclosure_missing")

        # Check LGPD compliance for data handling
        lgpd_compliant = self._check_lgpd_compliance(input_data)
        if not lgpd_compliant:
            validation_issues.append("lgpd_compliance_failed")

        return {
            "requirements_met": len(validation_issues) == 0,
            "validation_issues": validation_issues,
            "can_waive": requirements["can_waive"],
            "lgpd_compliant": lgpd_compliant,
        }

    def _determine_consent_status(
        self, consent_type: str, validation_result: dict[str, Any]
    ) -> Literal["obtained", "pending", "refused", "waived"]:
        """
        Determine consent status based on validation results.

        Args:
            consent_type: Type of consent
            validation_result: Validation result dictionary

        Returns:
            Consent status
        """
        # Emergency can be waived
        if consent_type == "emergency" and validation_result["can_waive"]:
            return "waived"

        # If requirements met, consent is obtained
        if validation_result["requirements_met"]:
            return "obtained"

        # Otherwise, consent is pending
        return "pending"

    def _check_lgpd_compliance(self, input_data: SurgicalConsentInput) -> bool:
        """
        Check LGPD compliance for consent data handling.

        Args:
            input_data: Consent input data

        Returns:
            True if LGPD compliant, False otherwise
        """
        # LGPD requires:
        # 1. Explicit consent for data processing (covered by consent form)
        # 2. Purpose limitation (surgical procedure)
        # 3. Data minimization (only necessary fields)
        # 4. Security measures (handled by platform)

        # Basic validation: ensure we have minimal required data
        has_patient = bool(input_data.patient_id)
        has_procedure = bool(input_data.procedure_code)
        has_surgeon = bool(input_data.surgeon_id)

        return has_patient and has_procedure and has_surgeon
