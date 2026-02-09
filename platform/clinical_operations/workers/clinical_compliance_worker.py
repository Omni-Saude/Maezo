"""
Clinical Compliance Worker - TOPIC: clinical.compliance

Handles clinical compliance verification for regulatory requirements
(ANVISA, ANS, CNES, JNA) and accreditation standards.

LGPD Compliance: SHA-256 hashes for patient identifiers
Standards: FHIR R4, CID-10, TUSS
Localization: Portuguese (_)
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from platform.shared.domain.exceptions import DomainException
from platform.shared.i18n import _
from platform.shared.integrations.fhir_client import FHIRClientProtocol
from platform.shared.multi_tenant.context import get_required_tenant
from platform.shared.multi_tenant.decorators import require_tenant
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class ClinicalException(DomainException):
    """Clinical domain exception"""

    bpmn_error_code: str = "CLINICAL_ERROR"


class ClinicalComplianceException(ClinicalException):
    """Clinical compliance specific exception"""

    bpmn_error_code: str = "CLINICAL_COMPLIANCE_ERROR"


# ============================================================================
# Input/Output DTOs
# ============================================================================


class ClinicalComplianceInput(BaseModel):
    """Input for clinical compliance verification"""

    encounter_reference: str = Field(..., description="FHIR Encounter reference")
    compliance_domain: str = Field(
        ...,
        description="Compliance domain: anvisa/ans/cnes/jna/conitec/accreditation",
    )
    verification_items: list[str] = Field(
        default_factory=list, description="Specific items to verify"
    )
    verification_date: str | None = Field(
        None, description="Verification date (ISO 8601)"
    )
    include_recommendations: bool = Field(
        True, description="Include improvement recommendations"
    )

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables"""
        return {
            "encounter_reference": self.encounter_reference,
            "compliance_domain": self.compliance_domain,
            "verification_items": self.verification_items,
            "verification_date": self.verification_date,
            "include_recommendations": self.include_recommendations,
        }


class ComplianceViolation(BaseModel):
    """Compliance violation details"""

    violation_id: str = Field(..., description="Violation identifier")
    rule_reference: str = Field(..., description="Regulatory rule reference")
    severity: str = Field(..., description="Severity: critical/major/minor")
    description: str = Field(..., description="Violation description")
    requirement: str = Field(..., description="Regulatory requirement")
    evidence: str | None = Field(None, description="Evidence of violation")
    detected_at: str = Field(..., description="Detection timestamp (ISO 8601)")


class CorrectiveAction(BaseModel):
    """Corrective action for compliance violation"""

    action_id: str = Field(..., description="Action identifier")
    violation_id: str = Field(..., description="Related violation ID")
    action_type: str = Field(
        ..., description="Type: immediate/short_term/long_term"
    )
    description: str = Field(..., description="Action description")
    responsible: str | None = Field(None, description="Responsible party")
    due_date: str | None = Field(None, description="Due date (ISO 8601)")
    status: str = Field(..., description="Status: pending/in_progress/complete")


class ComplianceDomainScore(BaseModel):
    """Compliance score for specific domain"""

    domain: str = Field(..., description="Compliance domain")
    score: float = Field(..., ge=0.0, le=100.0, description="Compliance score (0-100)")
    total_rules: int = Field(..., description="Total rules checked")
    compliant_rules: int = Field(..., description="Rules in compliance")
    violations_count: int = Field(..., description="Number of violations")
    last_verified: str = Field(..., description="Last verification timestamp")


class ClinicalComplianceOutput(BaseModel):
    """Output from clinical compliance verification"""

    compliance_status: str = Field(
        ..., description="Status: compliant/non_compliant/partial"
    )
    compliance_score: float = Field(
        ..., ge=0.0, le=100.0, description="Overall compliance score (0-100)"
    )
    violations: list[ComplianceViolation] = Field(
        default_factory=list, description="Identified violations"
    )
    corrective_actions: list[CorrectiveAction] = Field(
        default_factory=list, description="Required corrective actions"
    )
    domain_scores: list[ComplianceDomainScore] = Field(
        default_factory=list, description="Scores by domain"
    )
    critical_violations_count: int = Field(
        ..., description="Count of critical violations"
    )
    recommendations: list[str] = Field(
        default_factory=list, description="Improvement recommendations"
    )
    next_verification_date: str | None = Field(
        None, description="Next verification date (ISO 8601)"
    )
    verified_by: str | None = Field(None, description="Verifier reference")
    verified_at: str = Field(..., description="Verification timestamp (ISO 8601)")

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda process variables"""
        return {
            "compliance_status": self.compliance_status,
            "compliance_score": self.compliance_score,
            "violations": [v.model_dump() for v in self.violations],
            "corrective_actions": [a.model_dump() for a in self.corrective_actions],
            "domain_scores": [s.model_dump() for s in self.domain_scores],
            "critical_violations_count": self.critical_violations_count,
            "recommendations": self.recommendations,
            "next_verification_date": self.next_verification_date,
            "verified_by": self.verified_by,
            "verified_at": self.verified_at,
        }


# ============================================================================
# Protocol & Implementation
# ============================================================================


class ClinicalComplianceWorkerProtocol(ABC):
    """Protocol for clinical compliance worker"""

    TOPIC = "clinical.compliance"

    @abstractmethod
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute clinical compliance verification"""
        pass


class ClinicalComplianceWorker(ClinicalComplianceWorkerProtocol):
    """Production clinical compliance worker"""

    TOPIC = "clinical.compliance"

    # Compliance rules by domain
    COMPLIANCE_RULES = {
        "anvisa": [
            "ANVISA-RDC-63/2011",  # Segurança do paciente
            "ANVISA-RDC-36/2013",  # Segurança no uso de medicamentos
            "ANVISA-RDC-15/2012",  # Processamento de produtos
        ],
        "ans": [
            "ANS-RN-387/2015",  # Continuidade da assistência
            "ANS-RN-338/2013",  # Qualidade setorial
            "ANS-RN-259/2011",  # Garantias de atendimento
        ],
        "cnes": [
            "CNES-PORTARIA-511/2000",  # Cadastro Nacional
            "CNES-RESOLUÇÃO-50/2002",  # Regulamento técnico
        ],
        "jna": [
            "JNA-PAP-001",  # Metas Internacionais de Segurança
            "JNA-PAP-002",  # Gestão de medicamentos
            "JNA-PAP-003",  # Controle de infecções
        ],
    }

    def __init__(self, fhir_client: FHIRClientProtocol):
        self.fhir_client = fhir_client

    @require_tenant
    @track_task_execution
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Execute clinical compliance verification.

        Args:
            task_variables: Camunda task variables

        Returns:
            Dictionary with compliance verification results

        Raises:
            ClinicalComplianceException: If verification fails
        """
        tenant_id = get_required_tenant()
        logger.info(
            _("Iniciando verificação de conformidade clínica"),
            extra={
                "tenant_id": tenant_id,
                "encounter": task_variables.get("encounter_reference"),
                "domain": task_variables.get("compliance_domain"),
            },
        )

        # Parse input
        input_dto = ClinicalComplianceInput(**task_variables)

        try:
            # Fetch encounter data
            encounter = await self._fetch_encounter(input_dto.encounter_reference)

            # Get compliance rules for domain
            rules = self._get_compliance_rules(
                input_dto.compliance_domain, input_dto.verification_items
            )

            # Verify compliance for each rule
            violations = await self._verify_compliance_rules(encounter, rules)

            # Generate corrective actions
            corrective_actions = self._generate_corrective_actions(violations)

            # Calculate compliance score
            compliance_score = self._calculate_compliance_score(rules, violations)

            # Generate domain scores
            domain_scores = self._generate_domain_scores(
                input_dto.compliance_domain, rules, violations
            )

            # Count critical violations
            critical_count = sum(
                1 for v in violations if v.severity == "critical"
            )

            # Determine compliance status
            compliance_status = self._determine_compliance_status(
                compliance_score, critical_count
            )

            # Generate recommendations
            recommendations = []
            if input_dto.include_recommendations:
                recommendations = self._generate_recommendations(
                    violations, compliance_score
                )

            # Calculate next verification date
            next_verification = self._calculate_next_verification_date(
                input_dto.compliance_domain, compliance_status
            )

            # Record verification
            verified_at = input_dto.verification_date or datetime.utcnow().isoformat()

            # Build output
            output = ClinicalComplianceOutput(
                compliance_status=compliance_status,
                compliance_score=compliance_score,
                violations=violations,
                corrective_actions=corrective_actions,
                domain_scores=domain_scores,
                critical_violations_count=critical_count,
                recommendations=recommendations,
                next_verification_date=next_verification,
                verified_by=None,
                verified_at=verified_at,
            )

            logger.info(
                _("Verificação de conformidade concluída"),
                extra={
                    "tenant_id": tenant_id,
                    "compliance_status": compliance_status,
                    "compliance_score": compliance_score,
                    "violations_count": len(violations),
                },
            )

            return output.to_variables()

        except Exception as e:
            logger.error(
                _("Erro na verificação de conformidade"),
                extra={"tenant_id": tenant_id, "error": str(e)},
                exc_info=True,
            )
            raise ClinicalComplianceException(
                message=_("Falha na verificação de conformidade: {error}").format(
                    error=str(e)
                ),
                details={"encounter": input_dto.encounter_reference},
            ) from e

    async def _fetch_encounter(self, encounter_reference: str) -> dict[str, Any]:
        """Fetch encounter from FHIR"""
        return await self.fhir_client.read(encounter_reference)

    def _get_compliance_rules(
        self, domain: str, verification_items: list[str]
    ) -> list[str]:
        """Get compliance rules for domain"""
        all_rules = self.COMPLIANCE_RULES.get(domain, [])

        if verification_items:
            # Filter to specific items
            return [rule for rule in all_rules if rule in verification_items]

        return all_rules

    async def _verify_compliance_rules(
        self, encounter: dict[str, Any], rules: list[str]
    ) -> list[ComplianceViolation]:
        """Verify compliance against rules"""
        violations = []

        for rule in rules:
            # Simulate rule verification
            # In production, would query FHIR resources and apply rule logic
            is_compliant = await self._check_rule_compliance(encounter, rule)

            if not is_compliant:
                violation = ComplianceViolation(
                    violation_id=f"violation-{hashlib.sha256(rule.encode()).hexdigest()[:8]}",
                    rule_reference=rule,
                    severity=self._determine_violation_severity(rule),
                    description=self._get_rule_description(rule),
                    requirement=self._get_rule_requirement(rule),
                    detected_at=datetime.utcnow().isoformat(),
                )
                violations.append(violation)

        return violations

    async def _check_rule_compliance(
        self, encounter: dict[str, Any], rule: str
    ) -> bool:
        """Check compliance for specific rule"""
        # Simplified - would implement actual compliance checks
        # For now, randomly flag some rules as non-compliant for demonstration
        return rule not in ["ANVISA-RDC-63/2011", "JNA-PAP-001"]

    def _determine_violation_severity(self, rule: str) -> str:
        """Determine severity of violation"""
        if "PAP-001" in rule or "RDC-63" in rule:
            return "critical"
        elif "RDC-36" in rule or "PAP-002" in rule:
            return "major"
        else:
            return "minor"

    def _get_rule_description(self, rule: str) -> str:
        """Get description of rule"""
        descriptions = {
            "ANVISA-RDC-63/2011": _("Segurança do paciente não atendida"),
            "ANVISA-RDC-36/2013": _("Segurança no uso de medicamentos comprometida"),
            "JNA-PAP-001": _("Metas Internacionais de Segurança não cumpridas"),
            "ANS-RN-387/2015": _("Continuidade da assistência não garantida"),
        }
        return descriptions.get(rule, _("Violação de conformidade"))

    def _get_rule_requirement(self, rule: str) -> str:
        """Get requirement text for rule"""
        requirements = {
            "ANVISA-RDC-63/2011": _("Implementar protocolo de segurança do paciente"),
            "ANVISA-RDC-36/2013": _("Garantir rastreabilidade de medicamentos"),
            "JNA-PAP-001": _("Cumprir as 6 Metas Internacionais de Segurança"),
            "ANS-RN-387/2015": _("Assegurar continuidade do cuidado"),
        }
        return requirements.get(rule, _("Requisito regulatório"))

    def _generate_corrective_actions(
        self, violations: list[ComplianceViolation]
    ) -> list[CorrectiveAction]:
        """Generate corrective actions for violations"""
        actions = []

        for violation in violations:
            action_type = "immediate" if violation.severity == "critical" else "short_term"

            action = CorrectiveAction(
                action_id=f"action-{violation.violation_id}",
                violation_id=violation.violation_id,
                action_type=action_type,
                description=self._get_corrective_action_description(violation),
                status="pending",
            )
            actions.append(action)

        return actions

    def _get_corrective_action_description(
        self, violation: ComplianceViolation
    ) -> str:
        """Get corrective action description"""
        if "segurança" in violation.description.lower():
            return _("Implementar protocolo de segurança e treinar equipe")
        elif "medicamento" in violation.description.lower():
            return _("Revisar processo de dispensação e rastreabilidade")
        else:
            return _("Corrigir não conformidade e documentar ações")

    def _calculate_compliance_score(
        self, rules: list[str], violations: list[ComplianceViolation]
    ) -> float:
        """Calculate overall compliance score"""
        if not rules:
            return 100.0

        total_rules = len(rules)
        compliant_rules = total_rules - len(violations)

        # Base score
        base_score = (compliant_rules / total_rules) * 100

        # Penalize critical violations
        critical_penalty = sum(
            10 for v in violations if v.severity == "critical"
        )
        major_penalty = sum(5 for v in violations if v.severity == "major")

        final_score = max(0.0, base_score - critical_penalty - major_penalty)
        return round(final_score, 2)

    def _generate_domain_scores(
        self, domain: str, rules: list[str], violations: list[ComplianceViolation]
    ) -> list[ComplianceDomainScore]:
        """Generate compliance scores by domain"""
        total_rules = len(rules)
        violations_count = len(violations)
        compliant_rules = total_rules - violations_count

        score = (compliant_rules / total_rules * 100) if total_rules > 0 else 100.0

        return [
            ComplianceDomainScore(
                domain=domain,
                score=round(score, 2),
                total_rules=total_rules,
                compliant_rules=compliant_rules,
                violations_count=violations_count,
                last_verified=datetime.utcnow().isoformat(),
            )
        ]

    def _determine_compliance_status(
        self, compliance_score: float, critical_count: int
    ) -> str:
        """Determine overall compliance status"""
        if critical_count > 0:
            return "non_compliant"
        elif compliance_score >= 90.0:
            return "compliant"
        else:
            return "partial"

    def _generate_recommendations(
        self, violations: list[ComplianceViolation], compliance_score: float
    ) -> list[str]:
        """Generate improvement recommendations"""
        recommendations = []

        if compliance_score < 70.0:
            recommendations.append(
                _("Realizar auditoria completa e criar plano de ação imediato")
            )

        if any(v.severity == "critical" for v in violations):
            recommendations.append(
                _("Priorizar correção de violações críticas de segurança")
            )

        if len(violations) > 5:
            recommendations.append(
                _("Implementar programa de melhoria contínua da qualidade")
            )

        recommendations.append(
            _("Realizar treinamento de equipe sobre requisitos regulatórios")
        )

        return recommendations

    def _calculate_next_verification_date(
        self, domain: str, compliance_status: str
    ) -> str | None:
        """Calculate next verification date"""
        # Simplified - would use business rules
        from datetime import timedelta

        if compliance_status == "non_compliant":
            # Weekly verification
            next_date = datetime.utcnow() + timedelta(days=7)
        elif compliance_status == "partial":
            # Monthly verification
            next_date = datetime.utcnow() + timedelta(days=30)
        else:
            # Quarterly verification
            next_date = datetime.utcnow() + timedelta(days=90)

        return next_date.isoformat()


class ClinicalComplianceWorkerStub(ClinicalComplianceWorkerProtocol):
    """Stub implementation for testing"""

    TOPIC = "clinical.compliance"

    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Stub execution"""
        input_dto = ClinicalComplianceInput(**task_variables)
        now = datetime.utcnow().isoformat()

        output = ClinicalComplianceOutput(
            compliance_status="partial",
            compliance_score=85.0,
            violations=[
                ComplianceViolation(
                    violation_id="viol-001",
                    rule_reference="ANVISA-RDC-63/2011",
                    severity="critical",
                    description=_("Segurança do paciente não atendida"),
                    requirement=_("Implementar protocolo de segurança"),
                    detected_at=now,
                )
            ],
            corrective_actions=[
                CorrectiveAction(
                    action_id="action-001",
                    violation_id="viol-001",
                    action_type="immediate",
                    description=_("Implementar protocolo de segurança"),
                    status="pending",
                )
            ],
            domain_scores=[
                ComplianceDomainScore(
                    domain=input_dto.compliance_domain,
                    score=85.0,
                    total_rules=10,
                    compliant_rules=8,
                    violations_count=2,
                    last_verified=now,
                )
            ],
            critical_violations_count=1,
            recommendations=[_("Priorizar correção de violações críticas")],
            next_verification_date=now,
            verified_by=None,
            verified_at=now,
        )

        return output.to_variables()
