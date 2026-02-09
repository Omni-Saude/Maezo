"""
Clinical Auditing Worker - Clinical audit and compliance checks.

TOPIC: clinical.auditing

This worker performs comprehensive clinical audits to ensure compliance with:
- Documentation completeness and quality
- Medication administration records
- Procedure documentation standards
- Clinical protocol adherence
- LGPD compliance in clinical records

Author: Claude Flow V3
License: MIT
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import hashlib

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.integrations.fhir_client import FHIRClientProtocol
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution


logger = get_logger(__name__)


class ClinicalAuditException(DomainException):
    """Exception for clinical audit errors."""
    bpmn_error_code: str = "CLINICAL_AUDIT_ERROR"


# ============================================================================
# Input/Output DTOs
# ============================================================================


class AuditFinding(BaseModel):
    """Individual audit finding."""

    finding_id: str = Field(description="Unique finding identifier")
    category: str = Field(description="Finding category")
    severity: str = Field(description="critical/high/medium/low")
    description: str = Field(description="Finding description")
    affected_resource: str = Field(description="FHIR resource reference")
    recommendation: str = Field(description="Corrective action recommendation")
    compliance_requirement: Optional[str] = Field(None, description="Related compliance requirement")


class CorrectiveAction(BaseModel):
    """Corrective action for audit findings."""

    action_id: str = Field(description="Action identifier")
    finding_id: str = Field(description="Related finding")
    action_type: str = Field(description="documentation/training/process_change/review")
    description: str = Field(description="Action description")
    responsible_role: str = Field(description="Role responsible for action")
    due_date: str = Field(description="ISO 8601 deadline")
    priority: str = Field(description="high/medium/low")


class ClinicalAuditInput(BaseModel):
    """Input for clinical auditing."""

    encounter_reference: str = Field(description="Encounter/episode-123")
    audit_type: str = Field(
        description="documentation/medication/procedure/protocol"
    )
    audit_period: Optional[str] = Field(
        None,
        description="ISO 8601 period (PT24H, P7D, P1M)"
    )
    scope: Optional[List[str]] = Field(
        default_factory=list,
        description="Specific areas to audit"
    )
    auditor_reference: Optional[str] = Field(
        None,
        description="Practitioner/auditor-123"
    )

    def to_variables(self) -> Dict[str, Any]:
        """Convert to process variables."""
        return {
            "encounter_reference": self.encounter_reference,
            "audit_type": self.audit_type,
            "audit_period": self.audit_period,
            "scope": self.scope,
            "auditor_reference": self.auditor_reference,
        }


class ClinicalAuditOutput(BaseModel):
    """Output from clinical auditing."""

    audit_id: str = Field(description="Unique audit identifier")
    audit_type: str = Field(description="Type of audit performed")
    encounter_reference: str = Field(description="Audited encounter")
    audit_date: str = Field(description="ISO 8601 audit timestamp")
    compliance_score: float = Field(description="0-100 compliance percentage")
    overall_status: str = Field(
        description="compliant/non_compliant/needs_review"
    )
    findings: List[Dict[str, Any]] = Field(description="Audit findings")
    corrective_actions: List[Dict[str, Any]] = Field(
        description="Required corrective actions"
    )
    audited_resources: List[str] = Field(description="FHIR resources audited")
    next_audit_date: Optional[str] = Field(
        None,
        description="ISO 8601 recommended next audit"
    )
    audit_summary: str = Field(description="Executive summary")

    def to_variables(self) -> Dict[str, Any]:
        """Convert to process variables."""
        return {
            "audit_id": self.audit_id,
            "audit_type": self.audit_type,
            "encounter_reference": self.encounter_reference,
            "audit_date": self.audit_date,
            "compliance_score": self.compliance_score,
            "overall_status": self.overall_status,
            "findings": self.findings,
            "corrective_actions": self.corrective_actions,
            "audited_resources": self.audited_resources,
            "next_audit_date": self.next_audit_date,
            "audit_summary": self.audit_summary,
        }


# ============================================================================
# Protocols
# ============================================================================


class ClinicalAuditEngineProtocol(ABC):
    """Protocol for clinical audit engine."""

    @abstractmethod
    async def audit_documentation(
        self,
        encounter_ref: str,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Audit documentation completeness and quality."""
        pass

    @abstractmethod
    async def audit_medication_records(
        self,
        encounter_ref: str,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Audit medication administration records."""
        pass

    @abstractmethod
    async def audit_procedures(
        self,
        encounter_ref: str,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Audit procedure documentation."""
        pass

    @abstractmethod
    async def audit_protocol_adherence(
        self,
        encounter_ref: str,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Audit clinical protocol adherence."""
        pass


class ClinicalAuditEngineStub(ClinicalAuditEngineProtocol):
    """Stub implementation of audit engine."""

    async def audit_documentation(
        self,
        encounter_ref: str,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stub: Audit documentation."""
        logger.info(
            _("Auditando documentação clínica para {ref}").format(ref=encounter_ref)
        )

        # Simulate documentation audit
        findings = []

        # Check admission note
        findings.append({
            "item": "admission_note",
            "status": "complete",
            "completeness": 95,
        })

        # Check progress notes
        findings.append({
            "item": "progress_notes",
            "status": "incomplete",
            "completeness": 70,
            "issue": _("Notas de progresso ausentes para últimas 24h"),
        })

        # Check discharge summary
        findings.append({
            "item": "discharge_summary",
            "status": "pending",
            "completeness": 0,
        })

        overall_score = sum(f["completeness"] for f in findings) / len(findings)

        return {
            "audit_area": "documentation",
            "compliance_score": overall_score,
            "findings": findings,
            "issues_found": 2,
        }

    async def audit_medication_records(
        self,
        encounter_ref: str,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stub: Audit medication records."""
        logger.info(
            _("Auditando registros de medicamentos para {ref}").format(ref=encounter_ref)
        )

        return {
            "audit_area": "medication",
            "compliance_score": 88.0,
            "findings": [
                {
                    "item": "medication_administration",
                    "status": "complete",
                    "completeness": 92,
                },
                {
                    "item": "allergy_documentation",
                    "status": "complete",
                    "completeness": 100,
                },
                {
                    "item": "medication_reconciliation",
                    "status": "incomplete",
                    "completeness": 75,
                    "issue": _("Reconciliação medicamentosa incompleta na admissão"),
                },
            ],
            "issues_found": 1,
        }

    async def audit_procedures(
        self,
        encounter_ref: str,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stub: Audit procedures."""
        logger.info(
            _("Auditando documentação de procedimentos para {ref}").format(
                ref=encounter_ref
            )
        )

        return {
            "audit_area": "procedures",
            "compliance_score": 85.0,
            "findings": [
                {
                    "item": "procedure_consent",
                    "status": "complete",
                    "completeness": 100,
                },
                {
                    "item": "procedure_notes",
                    "status": "incomplete",
                    "completeness": 70,
                    "issue": _("Notas pós-procedimento incompletas"),
                },
            ],
            "issues_found": 1,
        }

    async def audit_protocol_adherence(
        self,
        encounter_ref: str,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stub: Audit protocol adherence."""
        logger.info(
            _("Auditando aderência a protocolos clínicos para {ref}").format(
                ref=encounter_ref
            )
        )

        return {
            "audit_area": "protocol_adherence",
            "compliance_score": 92.0,
            "findings": [
                {
                    "item": "sepsis_protocol",
                    "status": "complete",
                    "adherence": 95,
                },
                {
                    "item": "dvt_prophylaxis",
                    "status": "complete",
                    "adherence": 90,
                },
                {
                    "item": "infection_control",
                    "status": "complete",
                    "adherence": 91,
                },
            ],
            "issues_found": 0,
        }


# ============================================================================
# Worker
# ============================================================================


class ClinicalAuditingWorker:
    """
    Clinical auditing worker.

    Performs comprehensive clinical audits to ensure compliance with
    documentation standards, medication safety, procedure protocols,
    and clinical guidelines.
    """

    TOPIC = "clinical.auditing"

    def __init__(
        self,
        fhir_client: FHIRClientProtocol,
        audit_engine: Optional[ClinicalAuditEngineProtocol] = None,
    ):
        """
        Initialize clinical auditing worker.

        Args:
            fhir_client: FHIR client for resource access
            audit_engine: Audit engine (uses stub if not provided)
        """
        self.fhir_client = fhir_client
        self.audit_engine = audit_engine or ClinicalAuditEngineStub()

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute clinical audit.

        Args:
            task_variables: Task input variables

        Returns:
            Audit results with findings and corrective actions

        Raises:
            ClinicalAuditException: If audit fails
        """
        tenant_id = get_required_tenant()

        logger.info(
            _("Iniciando auditoria clínica para tenant {tenant}").format(
                tenant=hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
            )
        )

        try:
            # Parse input
            audit_input = ClinicalAuditInput(**task_variables)

            # Perform audit based on type
            audit_results = await self._perform_audit(audit_input)

            # Generate findings
            findings = self._generate_findings(audit_results, audit_input)

            # Generate corrective actions
            corrective_actions = self._generate_corrective_actions(findings)

            # Calculate compliance score
            compliance_score = self._calculate_compliance_score(audit_results)

            # Determine overall status
            overall_status = self._determine_status(compliance_score, findings)

            # Create audit record in FHIR
            audit_id = await self._create_audit_record(
                audit_input,
                compliance_score,
                findings,
            )

            # Prepare output
            output = ClinicalAuditOutput(
                audit_id=audit_id,
                audit_type=audit_input.audit_type,
                encounter_reference=audit_input.encounter_reference,
                audit_date=datetime.utcnow().isoformat(),
                compliance_score=compliance_score,
                overall_status=overall_status,
                findings=[f.model_dump() for f in findings],
                corrective_actions=[a.model_dump() for a in corrective_actions],
                audited_resources=self._get_audited_resources(audit_results),
                next_audit_date=self._calculate_next_audit_date(
                    compliance_score
                ).isoformat(),
                audit_summary=self._generate_summary(
                    audit_input,
                    compliance_score,
                    findings,
                ),
            )

            logger.info(
                _("Auditoria {audit_id} concluída: score={score}%, status={status}").format(
                    audit_id=audit_id,
                    score=compliance_score,
                    status=overall_status,
                )
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                _("Erro na auditoria clínica: {error}").format(error=str(e))
            )
            raise ClinicalAuditException(
                message=_("Falha ao executar auditoria clínica"),
                details={"error": str(e), "tenant_id": tenant_id},
            ) from e

    async def _perform_audit(
        self,
        audit_input: ClinicalAuditInput,
    ) -> Dict[str, Any]:
        """Perform audit based on type."""
        audit_type = audit_input.audit_type
        encounter_ref = audit_input.encounter_reference
        period = audit_input.audit_period

        if audit_type == "documentation":
            return await self.audit_engine.audit_documentation(encounter_ref, period)
        elif audit_type == "medication":
            return await self.audit_engine.audit_medication_records(
                encounter_ref, period
            )
        elif audit_type == "procedure":
            return await self.audit_engine.audit_procedures(encounter_ref, period)
        elif audit_type == "protocol":
            return await self.audit_engine.audit_protocol_adherence(
                encounter_ref, period
            )
        else:
            raise ClinicalAuditException(
                message=_("Tipo de auditoria não suportado: {type}").format(
                    type=audit_type
                )
            )

    def _generate_findings(
        self,
        audit_results: Dict[str, Any],
        audit_input: ClinicalAuditInput,
    ) -> List[AuditFinding]:
        """Generate structured findings from audit results."""
        findings = []

        for item in audit_results.get("findings", []):
            if item.get("issue"):
                finding = AuditFinding(
                    finding_id=f"finding-{len(findings) + 1}",
                    category=audit_input.audit_type,
                    severity=self._determine_severity(item),
                    description=item["issue"],
                    affected_resource=audit_input.encounter_reference,
                    recommendation=self._generate_recommendation(item),
                    compliance_requirement=audit_results.get("audit_area"),
                )
                findings.append(finding)

        return findings

    def _determine_severity(self, item: Dict[str, Any]) -> str:
        """Determine finding severity."""
        completeness = item.get("completeness", 100)

        if completeness < 50:
            return "critical"
        elif completeness < 70:
            return "high"
        elif completeness < 85:
            return "medium"
        else:
            return "low"

    def _generate_recommendation(self, item: Dict[str, Any]) -> str:
        """Generate recommendation for finding."""
        item_name = item.get("item", "item")
        return _("Completar {item} conforme protocolos estabelecidos").format(
            item=item_name
        )

    def _generate_corrective_actions(
        self,
        findings: List[AuditFinding],
    ) -> List[CorrectiveAction]:
        """Generate corrective actions for findings."""
        actions = []

        for finding in findings:
            action = CorrectiveAction(
                action_id=f"action-{len(actions) + 1}",
                finding_id=finding.finding_id,
                action_type="documentation",
                description=finding.recommendation,
                responsible_role="clinical_staff",
                due_date=(datetime.utcnow() + timedelta(days=7)).isoformat(),
                priority="high" if finding.severity in ["critical", "high"] else "medium",
            )
            actions.append(action)

        return actions

    def _calculate_compliance_score(self, audit_results: Dict[str, Any]) -> float:
        """Calculate overall compliance score."""
        return round(audit_results.get("compliance_score", 0.0), 2)

    def _determine_status(
        self,
        compliance_score: float,
        findings: List[AuditFinding],
    ) -> str:
        """Determine overall audit status."""
        critical_findings = [
            f for f in findings if f.severity == "critical"
        ]

        if critical_findings:
            return "non_compliant"
        elif compliance_score >= 90:
            return "compliant"
        elif compliance_score >= 70:
            return "needs_review"
        else:
            return "non_compliant"

    async def _create_audit_record(
        self,
        audit_input: ClinicalAuditInput,
        compliance_score: float,
        findings: List[AuditFinding],
    ) -> str:
        """Create FHIR audit event record."""
        # In production, create AuditEvent resource
        audit_id = f"audit-{datetime.utcnow().timestamp()}"

        logger.info(
            _("Criado registro de auditoria {audit_id}").format(audit_id=audit_id)
        )

        return audit_id

    def _get_audited_resources(self, audit_results: Dict[str, Any]) -> List[str]:
        """Get list of audited FHIR resources."""
        # In production, extract from actual audit
        return ["Encounter", "DocumentReference", "MedicationAdministration"]

    def _calculate_next_audit_date(self, compliance_score: float) -> datetime:
        """Calculate next recommended audit date."""
        if compliance_score < 70:
            # Weekly audits for low compliance
            return datetime.utcnow() + timedelta(days=7)
        elif compliance_score < 90:
            # Monthly audits for moderate compliance
            return datetime.utcnow() + timedelta(days=30)
        else:
            # Quarterly audits for high compliance
            return datetime.utcnow() + timedelta(days=90)

    def _generate_summary(
        self,
        audit_input: ClinicalAuditInput,
        compliance_score: float,
        findings: List[AuditFinding],
    ) -> str:
        """Generate executive summary."""
        return _(
            "Auditoria de {type} concluída com score de conformidade de {score}%. "
            "Identificados {count} achados que requerem ação corretiva."
        ).format(
            type=audit_input.audit_type,
            score=compliance_score,
            count=len(findings),
        )
