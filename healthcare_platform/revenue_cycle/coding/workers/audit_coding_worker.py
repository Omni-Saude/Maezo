"""Quality audit of clinical coding by supervisor.

CIB7 External Task Topic: audit-coding
BPMN Error Codes: AUDIT_FAILED, CODING_ERROR

Phase 2.2 - Coding & Audit: performs a quality audit on the coded
encounter.  Checks code specificity, documentation support, DRG
optimization opportunities, and unbundling detection.  Returns a
composite score (0-100) with findings and a recommendation.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import (
    BpmnErrorException,
    CodingException,
)
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService


# ── Enums ─────────────────────────────────────────────────────────────


class AuditRecommendation(str, Enum):
    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"


class FindingSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


# ── Data Transfer Objects ─────────────────────────────────────────────


class AuditCodingInput(BaseModel):
    """Variables consumed from the BPMN process.

    Archetype: FINANCIAL_CALCULATION"""

    encounter_id: str = Field(..., alias="encounterId")
    validated_cid10: list[str] = Field(..., alias="validatedCid10", min_length=1)
    validated_tuss: list[str] = Field(..., alias="validatedTuss", min_length=1)
    rules_applied: list[dict[str, Any]] = Field(
        default_factory=list, alias="rulesApplied"
    )
    coded_by: str = Field(..., alias="codedBy")
    tenant_id: str = Field(..., alias="tenantId")


class AuditFinding(BaseModel):
    """Single audit finding."""

    check_id: str = Field(..., alias="checkId")
    check_name: str = Field(..., alias="checkName")
    passed: bool
    message: str
    severity: FindingSeverity
    points_deducted: int = Field(0, alias="pointsDeducted")


class AuditCodingOutput(BaseModel):
    """Variables returned to the BPMN process."""

    audit_score: int = Field(..., alias="auditScore")
    audit_findings: list[AuditFinding] = Field(
        default_factory=list, alias="auditFindings"
    )
    audit_recommendation: str = Field(..., alias="auditRecommendation")
    requires_revision: bool = Field(False, alias="requiresRevision")

    def to_variables(self) -> dict[str, Any]:
        """Convert to Camunda task variables."""
        return {
            "auditScore": self.audit_score,
            "auditFindings": [
                f.model_dump(by_alias=True) for f in self.audit_findings
            ],
            "auditRecommendation": self.audit_recommendation,
            "requiresRevision": self.requires_revision,
        }


# ── Value Objects ─────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class AuditResult:
    """Aggregate result from the audit service."""

    score: int
    findings: list[dict[str, Any]] = field(default_factory=list)
    recommendation: str = "approve"
    auditor_notes: str = ""


# ── Protocol ──────────────────────────────────────────────────────────


@runtime_checkable
class CodingAuditServiceProtocol(Protocol):
    """Port: audits a coded encounter for quality."""

    def audit(self, encounter_data: dict[str, Any]) -> AuditResult: ...


# ── Audit constants for the stub ──────────────────────────────────────

# CID-10 codes with 3 characters are "unspecified" - prefer 4+ characters.
_MIN_SPECIFIC_LENGTH = 4

# TUSS codes commonly unbundled incorrectly.
_UNBUNDLE_SUSPECT_PAIRS: list[tuple[str, str]] = [
    ("30101012", "30101020"),
    ("40201010", "40201028"),
    ("20101012", "20101020"),
]

# DRG-optimizable diagnosis patterns (chapter prefix -> hint).
_DRG_OPTIMIZATION_HINTS: dict[str, str] = {
    "I": _(
        "Diagnósticos cardiovasculares podem ser otimizados para DRG "
        "com código mais específico (4o ou 5o dígito)"
    ),
    "J": _(
        "Diagnósticos respiratórios: verificar se complicações estão "
        "documentadas para melhor classificação DRG"
    ),
    "K": _(
        "Diagnósticos digestivos: especificar localização anatômica "
        "para otimização DRG"
    ),
}


# ── Stub Implementation ──────────────────────────────────────────────


class CodingAuditServiceStub:
    """Deterministic audit based on code patterns.

    Uses a hash of the encounter ID to produce reproducible but varied
    results for testing.  Real implementation would query clinical
    documentation and coding guidelines databases.
    """

    def audit(self, encounter_data: dict[str, Any]) -> AuditResult:
        encounter_id: str = encounter_data.get("encounter_id", "")
        cid10_codes: list[str] = encounter_data.get("cid10_codes", [])
        tuss_codes: list[str] = encounter_data.get("tuss_codes", [])
        rules_applied: list[dict[str, Any]] = encounter_data.get(
            "rules_applied", []
        )

        findings: list[dict[str, Any]] = []
        score = 100

        # ── Check 1: Code specificity ─────────────────────────────────
        unspecific = [
            c for c in cid10_codes if len(c) < _MIN_SPECIFIC_LENGTH
        ]
        if unspecific:
            deduction = min(len(unspecific) * 5, 20)
            score -= deduction
            findings.append({
                "check_id": "AUD-SPEC-001",
                "check_name": _("Especificidade do código CID-10"),
                "passed": False,
                "message": _(
                    "Código(s) CID-10 sem especificidade suficiente: {codes}. "
                    "Utilizar códigos com no mínimo {min} caracteres"
                ).format(
                    codes=", ".join(unspecific), min=_MIN_SPECIFIC_LENGTH
                ),
                "severity": "WARNING",
                "points_deducted": deduction,
            })
        else:
            findings.append({
                "check_id": "AUD-SPEC-001",
                "check_name": _("Especificidade do código CID-10"),
                "passed": True,
                "message": _(
                    "Todos os códigos CID-10 possuem especificidade adequada"
                ),
                "severity": "INFO",
                "points_deducted": 0,
            })

        # ── Check 2: Documentation support (hash-based simulation) ────
        enc_hash = int(
            hashlib.md5(encounter_id.encode()).hexdigest()[:8], 16  # noqa: S324
        )
        doc_score_pct = (enc_hash % 40) + 60  # 60-99
        if doc_score_pct < 75:
            deduction = 15
            score -= deduction
            findings.append({
                "check_id": "AUD-DOC-001",
                "check_name": _("Suporte documental"),
                "passed": False,
                "message": _(
                    "Documentação clínica insuficiente para suportar os códigos "
                    "informados. Score de documentação: {pct}%"
                ).format(pct=doc_score_pct),
                "severity": "ERROR",
                "points_deducted": deduction,
            })
        else:
            findings.append({
                "check_id": "AUD-DOC-001",
                "check_name": _("Suporte documental"),
                "passed": True,
                "message": _(
                    "Documentação clínica adequada. Score de documentação: {pct}%"
                ).format(pct=doc_score_pct),
                "severity": "INFO",
                "points_deducted": 0,
            })

        # ── Check 3: DRG optimization ─────────────────────────────────
        for cid in cid10_codes:
            chapter = cid[0].upper() if cid else ""
            if chapter in _DRG_OPTIMIZATION_HINTS:
                findings.append({
                    "check_id": "AUD-DRG-001",
                    "check_name": _("Otimização DRG"),
                    "passed": True,
                    "message": _DRG_OPTIMIZATION_HINTS[chapter],
                    "severity": "INFO",
                    "points_deducted": 0,
                })
                break  # One DRG hint per audit is sufficient

        # ── Check 4: Unbundling detection ─────────────────────────────
        tuss_set = set(tuss_codes)
        unbundling_found = False
        for code_a, code_b in _UNBUNDLE_SUSPECT_PAIRS:
            if code_a in tuss_set and code_b in tuss_set:
                unbundling_found = True
                deduction = 10
                score -= deduction
                findings.append({
                    "check_id": "AUD-UNB-001",
                    "check_name": _("Detecção de unbundling"),
                    "passed": False,
                    "message": _(
                        "Possível unbundling detectado: procedimentos {a} e {b} "
                        "geralmente são cobrados como procedimento único"
                    ).format(a=code_a, b=code_b),
                    "severity": "ERROR",
                    "points_deducted": deduction,
                })

        if not unbundling_found:
            findings.append({
                "check_id": "AUD-UNB-001",
                "check_name": _("Detecção de unbundling"),
                "passed": True,
                "message": _("Nenhum unbundling suspeito detectado"),
                "severity": "INFO",
                "points_deducted": 0,
            })

        # ── Check 5: Prior rule violations ────────────────────────────
        failed_rules = [
            r for r in rules_applied if not r.get("passed", True)
        ]
        if failed_rules:
            deduction = min(len(failed_rules) * 5, 15)
            score -= deduction
            findings.append({
                "check_id": "AUD-RUL-001",
                "check_name": _("Violações de regras anteriores"),
                "passed": False,
                "message": _(
                    "{count} violação(ões) de regras de codificação detectada(s) "
                    "na etapa anterior"
                ).format(count=len(failed_rules)),
                "severity": "WARNING",
                "points_deducted": deduction,
            })

        # ── Compute final score and recommendation ────────────────────
        score = max(score, 0)

        if score >= 80:
            recommendation = AuditRecommendation.APPROVE.value
        elif score >= 60:
            recommendation = AuditRecommendation.REVISE.value
        else:
            recommendation = AuditRecommendation.REJECT.value

        return AuditResult(
            score=score,
            findings=findings,
            recommendation=recommendation,
            auditor_notes=_(
                "Auditoria automática concluída para atendimento {enc}. "
                "Score: {score}/100. Recomendação: {rec}"
            ).format(enc=encounter_id, score=score, rec=recommendation),
        )


# ── Worker ────────────────────────────────────────────────────────────


class AuditCodingWorker:
    """Quality audit on a coded encounter.

    Checks code specificity, documentation support, DRG optimization,
    and unbundling detection.  Returns a composite score (0-100) with
    findings and a recommendation (approve / revise / reject).
    """

    TOPIC = "audit-coding"
    _FAIL_THRESHOLD = 60

    def __init__(
        self,
        audit_service: CodingAuditServiceProtocol | None = None,
    ) -> None:
        self._audit = audit_service or CodingAuditServiceStub()
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    @require_tenant
    @track_task_execution(metric_name="coding_audit_coding")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Execute coding audit.

        Task Variables (input):
            encounterId: str - Encounter identifier
            validatedCid10: list[str] - Validated CID-10 codes
            validatedTuss: list[str] - Validated TUSS codes
            rulesApplied: list[dict] - Rules from apply-coding-rules step
            codedBy: str - User who performed the coding
            tenantId: str - Tenant identifier

        Returns:
            auditScore: int (0-100)
            auditFindings: list[dict]
            auditRecommendation: str (approve | revise | reject)
            requiresRevision: bool

        Raises:
            BpmnErrorException (AUDIT_FAILED): when score < 60.
            CodingException: on invalid input.
        """
        ctx = get_required_tenant()

        # ── Parse & validate input ────────────────────────────────────
        encounter_id: str = task_variables.get("encounterId", "")
        validated_cid10: list[str] = task_variables.get("validatedCid10", [])
        validated_tuss: list[str] = task_variables.get("validatedTuss", [])
        rules_applied: list[dict[str, Any]] = task_variables.get(
            "rulesApplied", []
        )
        coded_by: str = task_variables.get("codedBy", "")

        if not validated_cid10 or not validated_tuss:
            raise CodingException(
                _("Entrada inválida para auditoria de codificação: "
                  "códigos CID-10 e TUSS são obrigatórios"),
                bpmn_error_code="CODING_ERROR",
            )
        if not coded_by:
            raise CodingException(
                _("Entrada inválida para auditoria de codificação: "
                  "identificação do codificador (codedBy) é obrigatória"),
                bpmn_error_code="CODING_ERROR",
            )

        self._logger.info(
            "audit_started",
            encounter_id=encounter_id,
            coded_by=coded_by,
            cid10_count=len(validated_cid10),
            tuss_count=len(validated_tuss),
            tenant_id=ctx.tenant_id,
        )

        # DMN-enhanced unbundling audit check
        dmn_result = self._evaluate_coding_dmn(
            subcategory="unbundle",
            table_name="unbundling_audit",
            inputs={
                "tuss_codes": validated_tuss,
                "encounter_id": encounter_id
            }
        )

        # ── Run audit ─────────────────────────────────────────────────
        encounter_data = {
            "encounter_id": encounter_id,
            "cid10_codes": validated_cid10,
            "tuss_codes": validated_tuss,
            "rules_applied": rules_applied,
            "coded_by": coded_by,
        }
        result = self._audit.audit(encounter_data)

        # ── Build output ──────────────────────────────────────────────
        audit_findings = [
            AuditFinding(
                checkId=f["check_id"],
                checkName=f["check_name"],
                passed=f["passed"],
                message=f["message"],
                severity=FindingSeverity(f["severity"]),
                pointsDeducted=f.get("points_deducted", 0),
            )
            for f in result.findings
        ]

        requires_revision = result.recommendation in (
            AuditRecommendation.REVISE.value,
            AuditRecommendation.REJECT.value,
        )

        output = AuditCodingOutput(
            auditScore=result.score,
            auditFindings=audit_findings,
            auditRecommendation=result.recommendation,
            requiresRevision=requires_revision,
        )

        # ── Handle failed audit ───────────────────────────────────────
        if result.score < self._FAIL_THRESHOLD:
            self._logger.error(
                "audit_failed",
                encounter_id=encounter_id,
                score=result.score,
                recommendation=result.recommendation,
                finding_count=len(audit_findings),
                tenant_id=ctx.tenant_id,
            )
            raise BpmnErrorException(
                error_code="AUDIT_FAILED",
                message=_(
                    "Auditoria de codificação reprovada para atendimento {enc}. "
                    "Score: {score}/100 (mínimo: {min}). Recomendação: {rec}"
                ).format(
                    enc=encounter_id,
                    score=result.score,
                    min=self._FAIL_THRESHOLD,
                    rec=result.recommendation,
                ),
                details=output.to_variables(),
            )

        if requires_revision:
            self._logger.warning(
                "audit_requires_revision",
                encounter_id=encounter_id,
                score=result.score,
                recommendation=result.recommendation,
                tenant_id=ctx.tenant_id,
            )
        else:
            self._logger.info(
                "audit_approved",
                encounter_id=encounter_id,
                score=result.score,
                tenant_id=ctx.tenant_id,
            )

        return output.to_variables()


    def _evaluate_coding_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate coding_audit DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='coding_audit',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def register_worker() -> AuditCodingWorker:
    """Create and return a configured AuditCodingWorker instance."""
    return AuditCodingWorker()

