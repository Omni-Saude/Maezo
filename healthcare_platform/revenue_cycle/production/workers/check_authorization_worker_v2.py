"""Verify insurance authorization for clinical procedures (Refactored).

TOPIC: production.check_authorization
ARCHETYPE: ADMIN_ADJUDICATION
DMN: pricing/authorization/authorization_status_adjudication

Refactored: replaced status if/elif chains with DMN call.

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
- ADR-007: DMN federation for tenant overrides
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class CheckAuthorizationWorker(BaseExternalTaskWorker):
    """Checks prior authorization status for procedures using DMN rules.

    DMN handles: status adjudication (approved/denied/pending/expired logic).
    Worker handles: input extraction, DMN call, result formatting.
    """

    TOPIC = "revenue_cycle.production.check_authorization"
    DMN_DECISION_KEY = "authorization_status_adjudication"
    DMN_CATEGORY = "pricing"

    def execute(self, context: TaskContext) -> TaskResult:
        """Check authorization for enriched procedures."""
        try:
            variables = context.variables
            procedures = variables.get("enriched_procedures", [])
            patient_ref = variables.get("patient_reference", "")
            payer_id = variables.get("payer_id", "")
            existing_auth = variables.get("existing_auth_number")

            if not procedures:
                return TaskResult.bpmn_error(
                    error_code="CODING_ERROR",
                    error_message="No procedures to authorize",
                )

            self.logger.info(
                f"Checking authorization: {len(procedures)} procedures, payer={payer_id}",
                extra={"tenant_id": context.tenant_id, "has_existing_auth": bool(existing_auth)},
            )

            results = []
            all_authorized = True

            for proc in procedures:
                code = proc.get("code", "")
                diagnosis_codes = proc.get("diagnosis_codes", [])

                dmn_result = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_DECISION_KEY,
                    variables={
                        "procedureCode": code,
                        "payerId": payer_id,
                        "existingAuthNumber": existing_auth or "",
                        "diagnosisCodes": ",".join(diagnosis_codes),
                        "quantity": proc.get("quantity", 1),
                    },
                    category=self.DMN_CATEGORY,
                )

                resultado = dmn_result.get("resultado", "REVISAR")
                acao = dmn_result.get("acao", "")
                risco = dmn_result.get("risco", "MEDIO")

                auth_result = {
                    "code": code,
                    "authorized": resultado == "PROSSEGUIR",
                    "auth_number": existing_auth,
                    "status": resultado,
                    "message": acao,
                    "risk": risco,
                }

                if resultado == "BLOQUEAR":
                    all_authorized = False
                elif resultado == "REVISAR":
                    all_authorized = False

                results.append(auth_result)

            if not all_authorized:
                denied = [r for r in results if not r["authorized"]]
                return TaskResult.bpmn_error(
                    error_code="AUTH_DENIED",
                    error_message=denied[0]["message"] if denied else "Authorization denied",
                    variables={
                        "authorization_results": results,
                        "denied_codes": [d["code"] for d in denied],
                    },
                )

            return TaskResult.success({
                "authorization_results": results,
                "all_authorized": True,
                "auth_number": existing_auth,
            })

        except Exception as e:
            self.logger.error(f"Authorization check failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="AUTH_NOT_FOUND",
                error_message=str(e),
            )
