"""Quality audit of clinical coding by supervisor - V2 thin worker.
CIB7 External Task Topic: coding.audit_coding
BPMN Error Codes: AUDIT_FAILED, CODING_ERROR
ORPHAN WARNING: No companion DMN tables exist yet.
Companion DMN tables required:
- audit_quality/code_specificity, documentation_support, drg_optimization, unbundling_detection, prior_rule_violations
"""
from __future__ import annotations
import re
from typing import Any
from pydantic import BaseModel, Field
from healthcare_platform.shared.domain.exceptions import BpmnErrorException, CodingException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService

class AuditCodingOutputV2(BaseModel):
    audit_score: int = Field(..., alias="auditScore")
    audit_findings: list[dict[str, Any]] = Field(default_factory=list, alias="auditFindings")
    audit_recommendation: str = Field(..., alias="auditRecommendation")
    requires_revision: bool = Field(False, alias="requiresRevision")

    def to_variables(self) -> dict[str, Any]:
        return {
            "auditScore": self.audit_score,
            "auditFindings": self.audit_findings,
            "auditRecommendation": self.audit_recommendation,
            "requiresRevision": self.requires_revision,
        }
class AuditCodingWorkerV2:
    """V2 thin worker: delegates audit logic to DMN tables. ORPHAN: No companion DMN tables exist yet."""
    TOPIC = "coding.audit_coding"
    _FAIL_THRESHOLD = 60

    def __init__(self, **kwargs: Any) -> None:
        """Initialize worker with optional v1 compatibility params (ignored)."""
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    @require_tenant
    @track_task_execution(metric_name="coding_audit_coding_v2")
    async def execute(self, task_variables: dict[str, Any] | Any) -> dict[str, Any]:
        """Execute worker with dict or mock_task (v1 compatibility)."""
        # V1 compatibility: handle mock_task objects
        if hasattr(task_variables, 'get_variable'):
            variables = self._extract_variables_from_mock_task(task_variables)
            try:
                result = await self._execute_impl(variables)
                await task_variables.complete(result)
                return result
            except BpmnErrorException as e:
                await task_variables.bpmn_error(e.error_code, str(e))
                raise
        else:
            # V2 pattern: dict input
            return await self._execute_impl(task_variables)

    def _extract_variables_from_mock_task(self, mock_task: Any) -> dict[str, Any]:
        """Extract variables from v1 mock_task object."""
        return {
            "encounterId": mock_task.get_variable("encounter_id") or mock_task.get_variable("encounterId"),
            "validatedCid10": mock_task.get_variable("cid10_codes") or mock_task.get_variable("validatedCid10") or [],
            "validatedTuss": mock_task.get_variable("tuss_codes") or mock_task.get_variable("validatedTuss") or [],
            "rulesApplied": mock_task.get_variable("coding_rules_result", {}).get("rules", []) if isinstance(mock_task.get_variable("coding_rules_result"), dict) else [],
            "codedBy": mock_task.get_variable("coded_by") or mock_task.get_variable("codedBy") or "",
        }

    async def _execute_impl(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Core execution logic."""
        ctx = get_required_tenant()
        enc_id = task_variables.get("encounterId", "")
        cid10 = task_variables.get("validatedCid10", [])
        tuss = task_variables.get("validatedTuss", [])
        rules = task_variables.get("rulesApplied", [])
        coded_by = task_variables.get("codedBy", "")

        if not cid10 or not tuss:
            raise CodingException(_("Entrada inválida para auditoria de codificação"), bpmn_error_code="CODING_ERROR")

        self._logger.info("audit_v2_started", encounter_id=enc_id, coded_by=coded_by, cid10_count=len(cid10), tuss_count=len(tuss), tenant_id=ctx.tenant_id)

        findings, score = [], 100
        checks = [
            ("audit_quality/code_specificity", {"cid10_codes": cid10}, "AUD-SPEC-001", "Code Specificity", True),
            ("audit_quality/documentation_support", {"encounter_id": enc_id, "cid10_codes": cid10}, "AUD-DOC-001", "Documentation Support", True),
            ("audit_quality/drg_optimization", {"cid10_codes": cid10}, "AUD-DRG-001", "DRG Optimization", False),
            ("audit_quality/unbundling_detection", {"tuss_codes": tuss}, "AUD-UNB-001", "Unbundling Detection", True),
        ]
        for table, inputs, chk_id, chk_name, deduct in checks:
            result = self._evaluate_dmn(table, inputs)
            finding = self._process_audit_finding(result, chk_id, chk_name)
            if finding:
                findings.append(finding)
                if deduct:
                    score -= finding.get("points_deducted", 0)

        failed = [r for r in rules if not r.get("passed", True)]
        if failed:
            ded = min(len(failed) * 5, 15)
            score -= ded
            findings.append({"check_id": "AUD-RUL-001", "check_name": "Prior Rule Violations", "passed": False, "message": f"{len(failed)} rule violation(s) detected", "severity": "WARNING", "points_deducted": ded})

        score = max(score, 0)
        rec = "approve" if score >= 80 else "reject" if score < 60 else "revise"
        req_rev = rec in ("revise", "reject")
        output = AuditCodingOutputV2(auditScore=score, auditFindings=findings, auditRecommendation=rec, requiresRevision=req_rev)

        if score < self._FAIL_THRESHOLD:
            self._logger.error("audit_v2_failed", encounter_id=enc_id, score=score, recommendation=rec, tenant_id=ctx.tenant_id)
            raise BpmnErrorException(error_code="AUDIT_FAILED", message=_("Auditoria reprovada. Score: {score}/100").format(score=score), details=output.to_variables())

        self._logger.info("audit_v2_completed", encounter_id=enc_id, score=score, recommendation=rec, tenant_id=ctx.tenant_id)
        return output.to_variables()

    def _evaluate_dmn(self, table_name: str, inputs: dict[str, Any]) -> dict[str, Any]:
        try:
            return self.dmn_service.evaluate(tenant_id=get_required_tenant().tenant_id, category='coding_audit', table_name=table_name, inputs=inputs)
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback (ORPHAN)", table=table_name, error=str(e))
            return {}

    def _process_audit_finding(self, dmn_result: dict[str, Any], check_id: str, check_name: str) -> dict[str, Any] | None:
        """Process DMN result into audit finding. Supports 3-output and 5-output schemas."""
        schema_map = {
            "BLOQUEAR": ("ERROR", 15, "acao", "Audit check failed"),
            "REVISAR": ("WARNING", 10, "acao", "Review required"),
            "Bloquear": ("ERROR", 15, "Justificativa", "Blocked"),
            "Revisar": ("WARNING", 10, "Justificativa", "Review"),
        }
        key = dmn_result.get("resultado") or dmn_result.get("Decisao")
        if key in schema_map:
            sev, pts, msg_key, default = schema_map[key]
            return {"check_id": check_id, "check_name": check_name, "passed": False, "message": dmn_result.get(msg_key, default), "severity": sev, "points_deducted": pts}
        return None

    async def process_task(self, job: Any = None, variables: dict[str, Any] | None = None) -> Any:
        """V1 backward-compatible entry point for tests."""
        from dataclasses import dataclass, field
        from typing import Dict, Optional

        @dataclass
        class _Result:
            success: bool
            variables: Dict[str, Any] = field(default_factory=dict)
            error_code: Optional[str] = None
            error_message: Optional[str] = None

        if variables is None:
            variables = {}

        try:
            result = await self.execute(variables)
            return _Result(success=True, variables=result)
        except BpmnErrorException as e:
            return _Result(success=False, error_code=e.error_code, error_message=str(e), variables=e.details or {})
        except Exception as e:
            error_code = getattr(e, 'bpmn_error_code', getattr(e, 'error_code', None))
            return _Result(success=False, error_code=error_code, error_message=str(e))

def register_worker() -> AuditCodingWorkerV2:
    return AuditCodingWorkerV2()
