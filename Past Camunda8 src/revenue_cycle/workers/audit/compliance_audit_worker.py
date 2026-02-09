"""
ComplianceAuditWorker - Zeebe worker for ANS/TISS regulatory compliance auditing.

This worker validates claim data against ANS (Agência Nacional de Saúde) and TISS
(Troca de Informação de Saúde Suplementar) compliance requirements. It performs
comprehensive compliance checks including field mapping, format validation,
and regulatory requirements.

This is the Python equivalent of the Java ComplianceAuditDelegate.

Business Rule: Benchmark - ANS/TISS healthcare compliance standards
Regulatory Compliance: ANS Resolution 456/2018, TISS 4.01.00, HIPAA equivalents for Brazil
Migrated from: com.hospital.revenuecycle.delegates.ComplianceAuditDelegate

Section references:
- ANS field mapping and format validation
- Healthcare provider regulatory requirements
- Data integrity and compliance scoring

BPMN Task: Task_Compliance_Audit in Audit_Validation_Workflow
Topic: audit-compliance
"""

from __future__ import annotations

from typing import Any
from datetime import datetime

import structlog

from revenue_cycle.domain.exceptions import BpmnErrorException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker

logger = structlog.get_logger(__name__)


@worker(topic="audit-compliance", max_jobs=8, lock_duration=30000)
class ComplianceAuditWorker(BaseWorker):
    """
    Zeebe worker for ANS/TISS regulatory compliance auditing.

    BPMN Task: Task_Compliance_Audit
    Topic: audit-compliance

    This worker validates claim data against regulatory standards:
    - ANS compliance requirements
    - TISS format validation
    - Healthcare provider requirements
    - Patient identification validation
    - Service coding compliance
    - Documentation requirements

    Input Variables:
        - claimId: Claim identifier (required)
        - claimData: Claim data object (required)
        - providerType: Type of healthcare provider (required)
        - serviceDate: Service provision date (required)

    Output Variables:
        - isCompliant: Whether claim meets compliance requirements (boolean)
        - complianceScore: Compliance percentage (0-100)
        - violatedRules: List of violated compliance rules
        - complianceLevel: FULL/PARTIAL/NON_COMPLIANT
        - auditTimestamp: When compliance audit was performed
    """

    # ANS/TISS compliance validation rules
    REQUIRED_FIELDS_ANS = [
        "patientId",
        "providerId",
        "providerType",
        "serviceDate",
        "serviceCode",
        "amount",
    ]

    VALID_PROVIDER_TYPES = [
        "HOSPITAL",
        "CLINIC",
        "LABORATORY",
        "PHARMACY",
        "DENTIST",
        "PHYSIOTHERAPY",
    ]

    VALID_SERVICE_CODES = {
        "CONSULTATION": ["9101", "9102", "9103"],
        "HOSPITALIZATION": ["4101", "4102", "4103"],
        "EXAM": ["2101", "2102", "2103"],
        "PROCEDURE": ["3101", "3102", "3103"],
    }

    def __init__(self, settings=None, **kwargs):
        """Initialize the worker."""
        super().__init__(settings=settings)

    @property
    def operation_name(self) -> str:
        """Operation name for idempotency."""
        return "compliance_audit"

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the compliance audit task.

        Args:
            job: Zeebe job
            variables: Job variables

        Returns:
            WorkerResult with compliance audit outcome
        """
        self._logger.info(
            "Processing compliance audit",
            claim_id=variables.get("claimId"),
        )

        try:
            claim_id = variables.get("claimId")
            claim_data = variables.get("claimData", {})
            provider_type = variables.get("providerType", "")
            service_date = variables.get("serviceDate")

            violated_rules = []
            compliance_checks_passed = 0
            total_checks = 0

            # Check required fields
            for field in self.REQUIRED_FIELDS_ANS:
                total_checks += 1
                if field not in claim_data or claim_data[field] is None:
                    violated_rules.append(f"MISSING_REQUIRED_FIELD:{field}")
                else:
                    compliance_checks_passed += 1

            # Check provider type validity
            total_checks += 1
            if provider_type not in self.VALID_PROVIDER_TYPES:
                violated_rules.append(f"INVALID_PROVIDER_TYPE:{provider_type}")
            else:
                compliance_checks_passed += 1

            # Validate service code format and compliance
            service_code = claim_data.get("serviceCode", "")
            total_checks += 1
            if not self._is_valid_service_code(service_code):
                violated_rules.append(f"INVALID_SERVICE_CODE:{service_code}")
            else:
                compliance_checks_passed += 1

            # Validate patient ID format (CPF or CNJ format)
            patient_id = claim_data.get("patientId", "")
            total_checks += 1
            if not self._is_valid_patient_id(patient_id):
                violated_rules.append(f"INVALID_PATIENT_ID_FORMAT:{patient_id}")
            else:
                compliance_checks_passed += 1

            # Validate amount format and reasonableness
            amount = claim_data.get("amount")
            total_checks += 1
            if not self._is_valid_amount(amount):
                violated_rules.append("INVALID_AMOUNT_FORMAT")
            else:
                compliance_checks_passed += 1

            # Validate service date (not in future)
            total_checks += 1
            if not self._is_valid_service_date(service_date):
                violated_rules.append("INVALID_SERVICE_DATE")
            else:
                compliance_checks_passed += 1

            # Calculate compliance score
            compliance_score = (
                (compliance_checks_passed / total_checks * 100)
                if total_checks > 0
                else 0
            )
            compliance_score = round(compliance_score, 2)

            # Determine compliance level
            if compliance_score >= 95:
                compliance_level = "FULL"
                is_compliant = True
            elif compliance_score >= 70:
                compliance_level = "PARTIAL"
                is_compliant = False
            else:
                compliance_level = "NON_COMPLIANT"
                is_compliant = False

            output = {
                "isCompliant": is_compliant,
                "complianceScore": compliance_score,
                "violatedRules": violated_rules,
                "complianceLevel": compliance_level,
                "auditTimestamp": datetime.now().isoformat(),
            }

            self._logger.info(
                "Compliance audit completed",
                claim_id=claim_id,
                is_compliant=is_compliant,
                compliance_score=compliance_score,
                compliance_level=compliance_level,
            )

            return WorkerResult.ok(output)

        except Exception as e:
            self._logger.error(
                "Error performing compliance audit",
                error=str(e),
                exc_info=True,
            )
            return WorkerResult.failure(
                error_message=f"Compliance audit failed: {e}",
                retry=True,
            )

    def _is_valid_service_code(self, service_code: str) -> bool:
        """
        Validate service code format.

        Args:
            service_code: Service code to validate

        Returns:
            True if valid, False otherwise
        """
        if not service_code or not isinstance(service_code, str):
            return False

        # Check if code is in valid codes list
        for codes in self.VALID_SERVICE_CODES.values():
            if service_code in codes:
                return True

        # Also accept codes that match format DDDD (4 digits)
        return (
            service_code.isdigit()
            and len(service_code) == 4
        )

    def _is_valid_patient_id(self, patient_id: str) -> bool:
        """
        Validate patient ID format (CPF-like format XXXXXXXXXXX).

        Args:
            patient_id: Patient ID to validate

        Returns:
            True if valid, False otherwise
        """
        if not patient_id or not isinstance(patient_id, str):
            return False

        # Remove common separators for validation
        clean_id = patient_id.replace("-", "").replace(".", "")

        # Must be at least 9 digits, at most 14
        return len(clean_id) >= 9 and len(clean_id) <= 14 and clean_id.replace(
            "-", ""
        ).isdigit()

    def _is_valid_amount(self, amount: Any) -> bool:
        """
        Validate amount format and reasonableness.

        Args:
            amount: Amount to validate

        Returns:
            True if valid, False otherwise
        """
        if amount is None:
            return False

        try:
            # Convert to float for validation
            amount_float = float(amount)
            # Amount must be positive and reasonable (less than 1 million)
            return 0 < amount_float < 1000000
        except (ValueError, TypeError):
            return False

    def _is_valid_service_date(self, service_date: Any) -> bool:
        """
        Validate service date (must be in past or today).

        Args:
            service_date: Service date to validate

        Returns:
            True if valid, False otherwise
        """
        if not service_date:
            return False

        try:
            if isinstance(service_date, str):
                # Try to parse ISO format date
                parsed_date = datetime.fromisoformat(service_date.replace("Z", "+00:00"))
            elif isinstance(service_date, datetime):
                parsed_date = service_date
            else:
                return False

            # Service date must not be in the future
            return parsed_date <= datetime.now()
        except (ValueError, TypeError):
            return False
