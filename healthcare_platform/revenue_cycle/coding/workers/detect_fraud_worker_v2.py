"""Detect coding fraud patterns - V2 thin worker.
CIB7 External Task Topic: coding.detect_fraud
BPMN Error Codes: FRAUD_DETECTED, CODING_ERROR
Companion DMN tables (fraud_scoring/): upcoding_complexity_ceiling, unbundling_partial_bundles, phantom_no_diagnosis, phantom_suspicious_prefix, frequency_zscore_threshold, provider_peer_deviation, risk_thresholds
"""
from __future__ import annotations
import re
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from healthcare_platform.shared.domain.exceptions import BpmnErrorException, CodingException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.workers.base import BaseExternalTaskWorker
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService

class DetectFraudInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    encounter_id: str = Field(..., alias="encounterId", min_length=1)
    validated_cid10: list[str] = Field(..., alias="validatedCid10")
    validated_tuss: list[str] = Field(..., alias="validatedTuss")
    encounter_class: str = Field(..., alias="encounterClass", min_length=1)
    patient_id: str = Field(..., alias="patientId", min_length=1)
    provider_id: str = Field(..., alias="providerId", min_length=1)
    tenant_id: str = Field(..., alias="tenantId", min_length=1)

    @field_validator("encounter_id", "patient_id", "provider_id", "tenant_id")
    @classmethod
    def validate_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()

class DetectFraudOutput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    fraud_risk_score: int = Field(..., alias="fraudRiskScore", ge=0, le=100)
    fraud_alerts: list[dict[str, str]] = Field(default_factory=list, alias="fraudAlerts")
    fraud_recommendation: str = Field(..., alias="fraudRecommendation")
    requires_manual_review: bool = Field(..., alias="requiresManualReview")

    def to_variables(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)
class DetectFraudWorkerV2(BaseExternalTaskWorker):
    """Thin DMN-federated worker for fraud detection. All 25 rule blocks delegated to 7 DMN tables."""
    TOPIC = "revenue_cycle.coding.detect_fraud"

    def __init__(self, dmn_service: FederatedDMNService | None = None, fraud_engine: Any = None, **kwargs: Any) -> None:
        super().__init__(dmn_service=dmn_service)
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = dmn_service or FederatedDMNService()
        # fraud_engine is accepted for backward compatibility but not used (DMN-only)


    async def execute(self, task_or_variables: Any) -> dict[str, Any]:

        """Execute worker with dict or mock_task (v1 compatibility)."""

        # V1 compatibility: handle mock_task objects

        if hasattr(task_or_variables, 'get_variable'):

            variables = self._extract_variables_from_mock_task(task_or_variables)

            try:

                result = await self._execute_impl(variables)

                await task_or_variables.complete(result)

                return result

            except BpmnErrorException as e:

                await task_or_variables.bpmn_error(e.error_code, str(e))

                raise

        else:

            # V2 pattern: dict input

            return await self._execute_impl(task_or_variables)


    def _extract_variables_from_mock_task(self, mock_task: Any) -> dict[str, Any]:

        """Extract variables from v1 mock_task object."""

        # Extract with both camelCase and snake_case

        def get_val(key, alt_key=None):

            val = mock_task.get_variable(key)

            if val is None and alt_key:

                val = mock_task.get_variable(alt_key)

            return val


        variables = {}

        

        # Common mappings

        if (val := get_val('encounter_id', 'encounterId')) is not None:

            variables['encounterId'] = val

        if (val := get_val('tenant_id', 'tenantId')) is not None:

            variables['tenantId'] = val

        if (val := get_val('patient_id', 'patientId')) is not None:

            variables['patientId'] = val


        # Code lists

        for key_pair in [('cid10_codes', 'validatedCid10'), ('tuss_codes', 'validatedTuss'), 

                         ('suggested_cid10_codes', 'suggestedCid10Codes'), 

                         ('suggested_tuss_codes', 'suggestedTussCodes')]:

            if (val := get_val(key_pair[0], key_pair[1])) is not None:

                variables[key_pair[1]] = val


        # Other fields

        for field in ['clinicalNotes', 'proceduresText', 'codedBy', 'patientAge', 

                      'comorbidities', 'encounterClass', 'auditStatus', 'fraudRiskLevel']:

            snake = re.sub(r'([a-z])([A-Z])', r'_', field).lower()

            if (val := get_val(snake, field)) is not None:

                variables[field] = val


        # Extract rules from coding_rules_result

        if (coding_result := get_val('coding_rules_result', 'codingRulesResult')) is not None:

            if isinstance(coding_result, dict):

                variables['rulesApplied'] = coding_result.get('rules', [])

            variables['codingRulesResult'] = coding_result


        return variables


    async def _execute_impl(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Core execution logic - receives dict of variables."""
        ctx = get_required_tenant()
        try:
            inp = DetectFraudInput(**task_variables)
        except Exception as exc:
            raise CodingException(_("Dados de entrada inválidos para detecção de fraude"), bpmn_error_code="CODING_ERROR") from exc

        self._logger.info("fraud_detection_started_v2", encounter_id=inp.encounter_id, cid10_count=len(inp.validated_cid10), tuss_count=len(inp.validated_tuss), tenant_id=ctx.tenant_id)

        alerts, risk = [], 0
        checks = [
            ("upcoding_complexity_ceiling", {"tuss_codes": inp.validated_tuss, "encounter_class": inp.encounter_class}),
            ("unbundling_partial_bundles", {"tuss_codes": inp.validated_tuss}),
            ("phantom_no_diagnosis", {"tuss_codes": inp.validated_tuss, "cid10_codes": inp.validated_cid10}),
            ("phantom_suspicious_prefix", {"tuss_codes": inp.validated_tuss}),
            ("frequency_zscore_threshold", {"tuss_count": len(inp.validated_tuss), "encounter_class": inp.encounter_class}),
            ("provider_peer_deviation", {"provider_id": inp.provider_id, "tuss_count": len(inp.validated_tuss)}),
        ]
        for tbl, params in checks:
            res = self._evaluate_dmn("fraud_scoring", tbl, params)
            alerts.extend(res.get("alerts", []))
            risk += res.get("score", 0)

        risk = min(risk, 100)
        thresh_res = self._evaluate_dmn("fraud_scoring", "risk_thresholds", {"risk_score": risk})
        rec = thresh_res.get("recommendation", "clear")
        req_man = rec == "flag"

        if risk > 80:
            self._logger.warning("fraud_detected_high_risk_v2", encounter_id=inp.encounter_id, risk_score=risk, tenant_id=ctx.tenant_id)
            raise BpmnErrorException(error_code="FRAUD_DETECTED", message=_("Fraude detectada: pontuação de risco {score}").format(score=risk))

        output = DetectFraudOutput(fraud_risk_score=risk, fraud_alerts=alerts, fraud_recommendation=rec, requires_manual_review=req_man)
        self._logger.info("fraud_detection_completed_v2", encounter_id=inp.encounter_id, risk_score=risk, alert_count=len(alerts), tenant_id=ctx.tenant_id)

        return output.to_variables()

    def _evaluate_dmn(self, subcat: str, tbl: str, inputs: dict) -> dict:
        try:
            return self.dmn_service.evaluate(tenant_id=get_required_tenant().tenant_id, category='coding_audit', table_name=f"{subcat}/{tbl}", inputs=inputs)
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=tbl, error=str(e))
            return {"alerts": [], "score": 0}

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

def register_worker(dmn_service: FederatedDMNService | None = None) -> DetectFraudWorkerV2:
    return DetectFraudWorkerV2(dmn_service=dmn_service)
