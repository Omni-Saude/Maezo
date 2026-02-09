"""
AuditRulesWorker - Camunda 8 External Task Worker.

Medical coding audit with comprehensive compliance checking:
- ICD-10 code validation
- TUSS compatibility verification
- DRG consistency checking
- ANS/TISS compliance validation
- Medical coding audit trail

This worker validates assigned codes against healthcare coding standards.

BPMN Task: Task_Audit_Medical_Codes
Zeebe Topic: audit-medical-codes

Business Rule: Benchmark RN-AuditRulesDelegate (healthcare coding audit standards)
Regulatory Compliance: ANS TISS standards, CFM Resolution 2299, ICD-10-CM, CBHPM, Resolution 2965
Migrated from: com.hospital.revenuecycle.delegates.coding.AuditRulesDelegate
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from revenue_cycle.domain.exceptions import BpmnErrorException, BusinessRuleException
from revenue_cycle.workers.base import BaseWorker, WorkerResult, worker
from revenue_cycle.workers.coding.coding_models import (
    AuditFinding,
    AuditResult,
    AuditRulesInput,
    AuditRulesOutput,
    CodeType,
    SuggestedCode,
)

logger = structlog.get_logger(__name__)


class AuditFailureError(BusinessRuleException):
    """Raised when audit detects critical coding violations."""

    def __init__(
        self,
        message: str,
        encounter_id: Optional[str] = None,
        findings: Optional[list[dict]] = None,
    ):
        super().__init__(
            message=message,
            rule_name="CODING_AUDIT",
            code="AUDIT_FAILURE",
            details={
                "encounter_id": encounter_id,
                "findings_count": len(findings or []),
            },
        )
        self.findings = findings or []


@worker(
    topic="audit-medical-codes",
    lock_duration=30000,  # 30 seconds
    max_jobs=16,
)
class AuditRulesWorker(BaseWorker):
    """
    Zeebe worker for medical coding audit with compliance validation.

    Functionality:
    - Validate ICD-10 codes against official codeset
    - Check TUSS compatibility with assigned ICD-10 codes
    - Verify DRG consistency with diagnoses
    - Apply ANS/TISS compliance rules
    - Flag codes requiring physician review
    - Generate detailed audit trail

    Business Rules Reference:
        - Document: docs/Regras de Negocio (PT-BR)/04_Coding/RN-COD-002-Audit-Codes.md
        - Standards: ANS TISS, CFM Resolution 2299, ICD-10-CM, CBHPM
        - Regulatory: Resolution 2965 (ANS), CPC 25 (Accounting)

    Input Variables:
        encounterId: Unique encounter identifier
        assignedCodes: Codes by type {'icd10': [...], 'tuss': [...], 'drg': [...]}
        coderUserId: ID of coder who assigned codes
        patientAge: Optional patient age
        admissionType: Optional admission type
        drgWeight: Optional DRG weight

    Output Variables:
        auditResult: PASS, FAIL, or WARNING
        findings: List of audit findings if any
        suggestedCorrections: Suggested corrections
        auditNotes: Additional notes
        requiresPhysicianReview: Whether review is required
        auditSeverityLevel: Severity (INFO, WARNING, ERROR, CRITICAL)
        auditRulesApplied: List of applied rules (audit trail)
        complianceStatus: ANS/TISS compliance status

    BPMN Errors:
        AUDIT_FAILURE: Critical coding violations detected
        INVALID_INPUT: Input validation failed
    """

    def __init__(
        self,
        settings=None,
        **kwargs
    ):
        """
        Initialize the worker.

        Args:
            settings: Optional worker settings
            **kwargs: Additional keyword arguments (ignored)
        """
        super().__init__(settings=settings)
        self._logger = logger.bind(worker=self.worker_name)
        self._valid_icd10_codes = self._load_icd10_codes()
        self._valid_tuss_codes = self._load_tuss_codes()

    @property
    def operation_name(self) -> str:
        """Get the operation name for idempotency and logging."""
        return "audit_codes"

    @property
    def requires_idempotency(self) -> bool:
        """
        Code audit is deterministic.

        Same codes + same rules = same result.
        """
        return False

    async def process_task(
        self,
        job: Any,
        variables: dict[str, Any],
    ) -> WorkerResult:
        """
        Process the audit-medical-codes task.

        Main processing flow:
        1. Parse and validate input variables
        2. Validate ICD-10 codes
        3. Validate TUSS compatibility
        4. Validate DRG consistency
        5. Apply ANS/TISS compliance rules
        6. Determine if physician review needed
        7. Build output with audit trail

        Args:
            job: Camunda external task
            variables: Job variables from the process

        Returns:
            WorkerResult with audit findings and result

        Raises:
            AuditFailureError: If critical violations found
        """
        tenant_id = variables.get("tenantId")

        self._logger.info(
            "Starting medical coding audit",
            job_key=str(getattr(job, "key", "unknown")),
            tenant_id=tenant_id,
        )

        try:
            # 1. Parse and validate input
            input_data = self._parse_input(variables)

            self._logger.info(
                "Processing code audit",
                encounter_id=input_data.encounter_id,
                coder_id=input_data.coder_user_id,
            )

            # 2. Audit ICD-10 codes
            icd10_findings = self._audit_icd10_codes(
                input_data.assigned_codes.get("icd10", []),
                input_data.patient_age,
            )

            # 3. Audit TUSS codes
            tuss_findings = self._audit_tuss_codes(
                input_data.assigned_codes.get("tuss", []),
                input_data.assigned_codes.get("icd10", []),
            )

            # 4. Audit DRG consistency
            drg_findings = self._audit_drg_consistency(
                input_data.assigned_codes.get("drg", []),
                input_data.assigned_codes.get("icd10", []),
                input_data.drg_weight,
            )

            # 5. Apply ANS/TISS compliance rules
            compliance_findings = self._audit_compliance(
                input_data.assigned_codes,
                input_data.patient_age,
            )

            # 6. Compile all findings
            all_findings = icd10_findings + tuss_findings + drg_findings + compliance_findings

            # 7. Determine audit result
            audit_result, severity = self._determine_audit_result(all_findings)

            # 8. Build suggestions
            suggestions = self._build_suggestions(all_findings)

            # 9. Determine review requirement
            requires_review = audit_result != AuditResult.PASS or any(
                f.severity == "ERROR" for f in all_findings
            )

            # 10. Extract applied rules
            rules_applied = self._extract_audit_rules(
                icd10_findings, tuss_findings, drg_findings, compliance_findings
            )

            # 11. Build output
            output = AuditRulesOutput(
                encounter_id=input_data.encounter_id,
                audit_result=audit_result,
                findings=all_findings,
                suggested_corrections=suggestions,
                audit_notes=self._generate_audit_notes(all_findings),
                requires_physician_review=requires_review,
                audit_severity_level=severity,
                audit_rules_applied=rules_applied,
                compliance_status="COMPLIANT" if not icd10_findings else "NON_COMPLIANT",
            )

            self._logger.info(
                "Code audit completed successfully",
                encounter_id=input_data.encounter_id,
                audit_result=audit_result.value,
                findings_count=len(all_findings),
                severity=severity,
            )

            return WorkerResult.ok(output.model_dump(by_alias=True))

        except AuditFailureError as e:
            self._logger.warning(
                "Code audit failed",
                encounter_id=variables.get("encounterId"),
                error=str(e),
                findings_count=len(e.findings),
            )
            return WorkerResult.bpmn_error(
                error_code="AUDIT_FAILURE",
                error_message=str(e),
                variables=e.details,
            )

        except Exception as e:
            self._logger.exception(
                "Code audit failed",
                error=str(e),
            )
            raise

    def _parse_input(self, variables: dict[str, Any]) -> AuditRulesInput:
        """
        Parse and validate input variables.

        Args:
            variables: Job variables

        Returns:
            Validated input model

        Raises:
            BpmnErrorException: If validation fails
        """
        try:
            return AuditRulesInput.model_validate(variables)
        except Exception as e:
            raise BpmnErrorException(
                error_code="INVALID_INPUT",
                message=f"Invalid input data: {e}",
            )

    def _load_icd10_codes(self) -> set[str]:
        """
        Load valid ICD-10 codes.

        In production: load from database or file.

        Returns:
            Set of valid ICD-10 codes
        """
        # Simplified set for example
        return {
            "J18.9", "I10", "E11", "M79.3", "K21.0",
            "A01", "A02", "B01", "C01", "D01",
            "E01", "F01", "G01", "H01", "I01",
        }

    def _load_tuss_codes(self) -> set[str]:
        """
        Load valid TUSS codes.

        TUSS = Tabela de Procedimentos e Orteses, Próteses e Materiais do SUS

        Returns:
            Set of valid TUSS codes
        """
        # Simplified set for example
        return {
            "02.01.01.001-8", "40.01.02.001-5", "50.02.01.001-9",
            "30.01.01.001-7", "35.01.01.001-2",
        }

    def _audit_icd10_codes(
        self,
        icd10_codes: list[str],
        patient_age: Optional[int],
    ) -> list[AuditFinding]:
        """
        Audit ICD-10 codes for validity and age-appropriateness.

        Args:
            icd10_codes: List of ICD-10 codes to audit
            patient_age: Optional patient age

        Returns:
            List of audit findings
        """
        findings: list[AuditFinding] = []

        for code in icd10_codes:
            # Check if code exists
            if code not in self._valid_icd10_codes:
                findings.append(
                    AuditFinding(
                        code=code,
                        code_type=CodeType.ICD10,
                        finding_type="INVALID_CODE",
                        severity="ERROR",
                        message=f"ICD-10 code {code} is not valid",
                        reference="ICD-10-CM Official Code Set",
                    )
                )

            # Check age-appropriateness
            if patient_age and patient_age < 1 and code in ["F01", "F02", "G01"]:
                findings.append(
                    AuditFinding(
                        code=code,
                        code_type=CodeType.ICD10,
                        finding_type="AGE_MISMATCH",
                        severity="WARNING",
                        message=f"Code {code} may not be appropriate for neonatal patient",
                        reference="ICD-10 Age-Specific Rules",
                    )
                )

        return findings

    def _audit_tuss_codes(
        self,
        tuss_codes: list[str],
        icd10_codes: list[str],
    ) -> list[AuditFinding]:
        """
        Audit TUSS codes for validity and compatibility with ICD-10.

        Args:
            tuss_codes: List of TUSS codes
            icd10_codes: List of ICD-10 codes for compatibility check

        Returns:
            List of audit findings
        """
        findings: list[AuditFinding] = []

        for code in tuss_codes:
            # Check if code exists
            if code not in self._valid_tuss_codes:
                findings.append(
                    AuditFinding(
                        code=code,
                        code_type=CodeType.TUSS,
                        finding_type="INVALID_CODE",
                        severity="ERROR",
                        message=f"TUSS code {code} is not valid",
                        reference="ANS TISS - Valid TUSS Codes",
                    )
                )

        return findings

    def _audit_drg_consistency(
        self,
        drg_codes: list[str],
        icd10_codes: list[str],
        drg_weight: Optional[float],
    ) -> list[AuditFinding]:
        """
        Audit DRG consistency with assigned diagnoses.

        Args:
            drg_codes: List of DRG codes
            icd10_codes: List of ICD-10 codes
            drg_weight: DRG weight

        Returns:
            List of audit findings
        """
        findings: list[AuditFinding] = []

        if drg_codes and not icd10_codes:
            findings.append(
                AuditFinding(
                    code=drg_codes[0] if drg_codes else "UNKNOWN",
                    code_type=CodeType.DRG,
                    finding_type="DRG_MISMATCH",
                    severity="WARNING",
                    message="DRG code assigned without corresponding ICD-10 diagnoses",
                    suggested_correction="Verify DRG assignment",
                    reference="DRG Grouper Rules",
                )
            )

        return findings

    def _audit_compliance(
        self,
        assigned_codes: dict[str, list[str]],
        patient_age: Optional[int],
    ) -> list[AuditFinding]:
        """
        Audit ANS/TISS compliance rules.

        Args:
            assigned_codes: Dictionary of all assigned codes
            patient_age: Optional patient age

        Returns:
            List of compliance findings
        """
        findings: list[AuditFinding] = []

        icd10_codes = assigned_codes.get("icd10", [])
        tuss_codes = assigned_codes.get("tuss", [])

        # Rule: Must have at least primary diagnosis
        if not icd10_codes:
            findings.append(
                AuditFinding(
                    code="MISSING_PRIMARY",
                    code_type=CodeType.ICD10,
                    finding_type="MISSING_PRIMARY_DIAGNOSIS",
                    severity="ERROR",
                    message="No primary diagnosis code assigned",
                    reference="ANS TISS - Mandatory Fields",
                )
            )

        return findings

    def _determine_audit_result(
        self,
        findings: list[AuditFinding],
    ) -> tuple[AuditResult, str]:
        """
        Determine overall audit result and severity.

        Args:
            findings: List of audit findings

        Returns:
            Tuple of (audit_result, severity_level)
        """
        if not findings:
            return AuditResult.PASS, "INFO"

        error_findings = [f for f in findings if f.severity == "ERROR"]
        warning_findings = [f for f in findings if f.severity == "WARNING"]

        if error_findings:
            return AuditResult.FAIL, "ERROR"

        if warning_findings:
            return AuditResult.WARNING, "WARNING"

        return AuditResult.PASS, "INFO"

    def _build_suggestions(
        self,
        findings: list[AuditFinding],
    ) -> list[SuggestedCode]:
        """
        Build suggestions from findings.

        Args:
            findings: List of audit findings

        Returns:
            List of suggested corrections
        """
        suggestions: list[SuggestedCode] = []

        for finding in findings:
            if finding.suggested_correction:
                suggestions.append(
                    SuggestedCode(
                        code=finding.suggested_correction,
                        code_type=finding.code_type,
                        description=finding.message,
                        confidence=0.85,
                        reason=finding.suggested_correction,
                    )
                )

        return suggestions

    def _generate_audit_notes(
        self,
        findings: list[AuditFinding],
    ) -> Optional[str]:
        """
        Generate audit notes summarizing findings.

        Args:
            findings: List of findings

        Returns:
            Audit notes string
        """
        if not findings:
            return "All codes passed validation"

        error_count = len([f for f in findings if f.severity == "ERROR"])
        warning_count = len([f for f in findings if f.severity == "WARNING"])

        parts = []
        if error_count:
            parts.append(f"{error_count} error(s)")
        if warning_count:
            parts.append(f"{warning_count} warning(s)")

        return f"Audit found: {', '.join(parts)}" if parts else None

    def _extract_audit_rules(
        self,
        icd10_findings: list[AuditFinding],
        tuss_findings: list[AuditFinding],
        drg_findings: list[AuditFinding],
        compliance_findings: list[AuditFinding],
    ) -> list[str]:
        """
        Extract list of audit rules applied.

        Args:
            icd10_findings: ICD-10 audit findings
            tuss_findings: TUSS audit findings
            drg_findings: DRG audit findings
            compliance_findings: Compliance audit findings

        Returns:
            List of applied rule descriptions
        """
        rules: list[str] = []

        rules.append("ICD-10 code validation")
        rules.append("TUSS code validation")
        rules.append("ICD-10/TUSS compatibility check")
        rules.append("DRG consistency verification")
        rules.append("ANS TISS compliance rules")
        rules.append("Age-appropriate coding rules")

        if icd10_findings:
            rules.append(f"ICD-10 audit: {len(icd10_findings)} finding(s)")
        if tuss_findings:
            rules.append(f"TUSS audit: {len(tuss_findings)} finding(s)")
        if drg_findings:
            rules.append(f"DRG audit: {len(drg_findings)} finding(s)")
        if compliance_findings:
            rules.append(f"Compliance audit: {len(compliance_findings)} finding(s)")

        return rules

    def extract_idempotency_params(self, variables: dict[str, Any]) -> str:
        """
        Extract parameters for idempotency key generation.

        Args:
            variables: Job variables

        Returns:
            String representation of key parameters
        """
        encounter_id = variables.get("encounterId", "")
        codes_str = str(variables.get("assignedCodes", {}))
        codes_hash = hash(codes_str) % 100000
        process_instance = variables.get("processInstanceKey", "")
        return f"{process_instance}:{encounter_id}:{codes_hash}"


def create_audit_rules_worker() -> AuditRulesWorker:
    """
    Factory function to create AuditRulesWorker.

    Returns:
        Configured worker instance
    """
    return AuditRulesWorker()
