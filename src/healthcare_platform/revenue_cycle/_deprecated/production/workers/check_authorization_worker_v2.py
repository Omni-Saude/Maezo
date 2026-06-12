"""Verify insurance authorization for clinical procedures (Refactored).

TOPIC: production.check_authorization
ARCHETYPE: ADMIN_ADJUDICATION

DMN flow (2 steps per procedure):
  1. auth_complexity_001       (authorization/)         → requiresAuth, authLevel, reviewType
  2. authorization_status_adjudication (pricing/authorization/) → resultado, acao, risco

ADR Compliance:
- ADR-002: Tenant resolution via context
- ADR-003: BaseExternalTaskWorker inheritance
- ADR-007: DMN federation for tenant overrides
"""

from __future__ import annotations

from healthcare_platform.shared.workers.base import (
    BaseExternalTaskWorker,
    TaskContext,
    TaskResult,
)


class CheckAuthorizationWorker(BaseExternalTaskWorker):
    """Checks prior authorization status for procedures using DMN rules.

    Flow per procedure:
      1. auth_complexity_001 → determines if authorization is required and at what level.
      2. authorization_status_adjudication → adjudicates the known status (approved/denied/pending).

    Worker handles: input extraction, DMN orchestration, result formatting.
    """

    TOPIC = "revenue_cycle.production.check_authorization"

    DMN_COMPLEXITY_KEY = "auth_complexity_001"
    DMN_COMPLEXITY_CATEGORY = "authorization"

    DMN_ADJUDICATION_KEY = "authorization_status_adjudication"
    DMN_ADJUDICATION_CATEGORY = "pricing/authorization"

    def execute(self, context: TaskContext) -> TaskResult:
        """Check authorization for enriched procedures."""
        try:
            variables = context.variables
            procedures = variables.get("enrichedProcedures", [])
            existing_auth = variables.get("existingAuthNumber", "")

            if not procedures:
                return TaskResult.bpmn_error(
                    error_code="CODING_ERROR",
                    error_message="No procedures to authorize",
                )

            self.logger.info(
                f"Checking authorization: {len(procedures)} procedures",
                extra={"tenant_id": context.tenant_id, "has_existing_auth": bool(existing_auth)},
            )

            results = []
            all_authorized = True

            for proc in procedures:
                code = proc.get("code", "")
                category = proc.get("category", "")
                # The process should carry the known authorization status per procedure;
                # defaults to "pending" when not yet determined.
                auth_status = proc.get("authorization_status", "pending")

                # Step 1 — complexity check: does this procedure require authorization?
                complexity = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_COMPLEXITY_KEY,
                    variables={
                        "procedure_code": code,
                        "procedure_category": category,
                    },
                    category=self.DMN_COMPLEXITY_CATEGORY,
                )
                requires_auth = complexity.get("requires_auth", True)
                auth_level = complexity.get("auth_level", "none")

                # Step 2 — adjudication: given the known status, what is the decision?
                adjudication = self.evaluate_dmn(
                    context=context,
                    decision_key=self.DMN_ADJUDICATION_KEY,
                    variables={
                        "authorization_status": auth_status,
                        "authorization_number": existing_auth,
                        "requires_auth": requires_auth,
                    },
                    category=self.DMN_ADJUDICATION_CATEGORY,
                )

                resultado = adjudication.get("resultado", "REVISAR")
                acao = adjudication.get("acao", "")
                risco = adjudication.get("risco", "MEDIO")

                auth_result = {
                    "code": code,
                    "authorized": resultado == "PROSSEGUIR",
                    "auth_number": existing_auth,
                    "auth_level": auth_level,
                    "requires_auth": requires_auth,
                    "status": resultado,
                    "message": acao,
                    "risk": risco,
                }

                if resultado in ("BLOQUEAR", "REVISAR"):
                    all_authorized = False

                results.append(auth_result)

            if not all_authorized:
                denied = [r for r in results if not r["authorized"]]
                return TaskResult.bpmn_error(
                    error_code="AUTH_DENIED",
                    error_message=denied[0]["message"] if denied else "Authorization denied",
                    variables={
                        "authorizationResults": results,
                        "deniedCodes": [d["code"] for d in denied],
                    },
                )

            return TaskResult.success({
                "authorizationResults": results,
                "allAuthorized": True,
                "authNumber": existing_auth,
            })

        except Exception as e:
            self.logger.error(f"Authorization check failed: {e}", exc_info=True)
            return TaskResult.bpmn_error(
                error_code="AUTH_NOT_FOUND",
                error_message=str(e),
            )
