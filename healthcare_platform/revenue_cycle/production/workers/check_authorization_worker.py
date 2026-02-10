"""Verify insurance authorization for clinical procedures.

CIB7 External Task Topic: production.check_authorization
BPMN Error Codes: AUTH_DENIED, AUTH_EXPIRED, AUTH_NOT_FOUND
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.exceptions import (
    AuthorizationDenied,
    AuthorizationExpired,
    AuthorizationNotFound,
    ExternalServiceException,
)
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.insurance_api_client import (
    AuthorizationRequest,
    InsuranceAPIClientProtocol,
)
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution


class CheckAuthorizationWorker:
    """Checks prior authorization status for procedures.

    Verifies that each procedure has a valid, non-expired authorization
    from the insurance payer. Handles multiple authorization scenarios:
    - Pre-authorized procedures (auth number already assigned)
    - Real-time authorization check
    - Authorization not required (based on payer rules)
    """

    TOPIC = "production.check_authorization"

    def __init__(
        self,
        insurance_client: InsuranceAPIClientProtocol,
        tasy_api_client: TasyApiClientProtocol | None = None,
    ) -> None:
        self._insurance = insurance_client
        self._tasy_api_client = tasy_api_client
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    def _evaluate_pricing_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate pricing DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='pricing',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    @require_tenant
    @track_task_execution(metric_name="production_check_authorization")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Check authorization for enriched procedures.

        Task Variables (input):
            enriched_procedures: list[dict] - Procedures with clinical data
            patient_reference: str - FHIR Patient reference
            payer_id: str - Insurance payer identifier
            existing_auth_number: str | None - Pre-existing authorization

        Returns:
            authorization_results: list[dict] - Auth status per procedure
            all_authorized: bool - Whether all procedures are authorized
            auth_number: str | None - Authorization number if applicable
        """
        ctx = get_required_tenant()
        procedures: list[dict[str, Any]] = task_variables.get("enriched_procedures", [])
        patient_ref: str = task_variables.get("patient_reference", "")
        payer_id: str = task_variables.get("payer_id", "")
        existing_auth: str | None = task_variables.get("existing_auth_number")

        self._logger.info(
            "checking_authorization",
            procedure_count=len(procedures),
            payer_id=payer_id,
            has_existing_auth=bool(existing_auth),
            tenant_id=ctx.tenant_id,
        )

        results: list[dict[str, Any]] = []
        all_authorized = True
        final_auth_number: str | None = existing_auth

        # If existing auth, verify it's still valid
        if existing_auth:
            try:
                # Try TASY API first for real-time check
                if self._tasy_api_client:
                    try:
                        tasy_auth_status = await self._tasy_api_client.get_authorization_status(
                            existing_auth
                        )
                        if tasy_auth_status.get("status") == "cancelled":
                            raise AuthorizationExpired(
                                _("Authorization {auth_id} was cancelled in TASY").format(
                                    auth_id=existing_auth
                                ),
                                details={"auth_id": existing_auth, "status": "cancelled"},
                            )
                        if tasy_auth_status.get("status") not in ("approved", "pending"):
                            raise AuthorizationExpired(
                                _("Authorization {auth_id} has expired").format(
                                    auth_id=existing_auth
                                ),
                                details={"auth_id": existing_auth, "status": tasy_auth_status.get("status")},
                            )
                    except ExternalServiceException as tasy_exc:
                        self._logger.warning(
                            "tasy_auth_check_failed_fallback_to_insurance_api",
                            auth_id=existing_auth,
                            error=str(tasy_exc),
                            tenant_id=ctx.tenant_id,
                        )
                        # Fall back to insurance API
                        pass

                # Use insurance API as fallback or primary
                if not self._tasy_api_client or "tasy_auth_status" not in locals():
                    auth_resp = await self._insurance.check_authorization_status(
                        existing_auth, payer_id
                    )
                    if auth_resp.status == "denied":
                        raise AuthorizationDenied(
                            _("Authorization {auth_id} was denied: {reason}").format(
                                auth_id=existing_auth,
                                reason=auth_resp.denial_reason or "unknown",
                            ),
                            details={"auth_id": existing_auth, "payer_id": payer_id},
                        )
                    if auth_resp.status not in ("approved", "pending"):
                        raise AuthorizationExpired(
                            _("Authorization {auth_id} has expired").format(
                                auth_id=existing_auth
                            ),
                            details={"auth_id": existing_auth, "status": auth_resp.status},
                        )
            except (AuthorizationDenied, AuthorizationExpired):
                raise
            except Exception as exc:
                self._logger.warning(
                    "auth_check_failed",
                    auth_id=existing_auth,
                    error=str(exc),
                    tenant_id=ctx.tenant_id,
                )
                raise ExternalServiceException(
                    _("Authorization check unavailable"),
                    service_name="authorization_api",
                    operation="check_authorization_status",
                ) from exc

        # Check each procedure
        for proc in procedures:
            code = proc.get("code", "")
            diagnosis_codes = proc.get("diagnosis_codes", [])

            auth_result: dict[str, Any] = {
                "code": code,
                "authorized": False,
                "auth_number": final_auth_number,
                "status": "pending",
                "message": "",
            }

            if existing_auth:
                auth_result["authorized"] = True
                auth_result["status"] = "approved"
                auth_result["message"] = "Pre-authorized"
            else:
                # Request real-time authorization - try TASY first
                try:
                    patient_id = patient_ref.rsplit("/", 1)[-1] if patient_ref else ""

                    # Try TASY API for authorization submission
                    if self._tasy_api_client:
                        try:
                            auth_data = {
                                "patient_id": patient_id,
                                "payer_id": payer_id,
                                "provider_id": ctx.tenant_id,
                                "procedure_codes": [code],
                                "diagnosis_codes": diagnosis_codes,
                                "requested_start_date": datetime.utcnow().isoformat(),
                                "quantity": proc.get("quantity", 1),
                            }
                            tasy_auth_resp = await self._tasy_api_client.submit_authorization(auth_data)

                            auth_result["auth_number"] = tasy_auth_resp.get("auth_number")
                            auth_result["status"] = tasy_auth_resp.get("status", "pending")

                            if tasy_auth_resp.get("status") == "approved":
                                auth_result["authorized"] = True
                                auth_result["message"] = "Approved by TASY"
                                if not final_auth_number:
                                    final_auth_number = tasy_auth_resp.get("auth_number")
                            elif tasy_auth_resp.get("status") == "denied":
                                auth_result["authorized"] = False
                                auth_result["message"] = tasy_auth_resp.get("denial_reason", "Denied by TASY")
                                all_authorized = False
                            else:
                                auth_result["authorized"] = False
                                auth_result["message"] = f"Status: {tasy_auth_resp.get('status')}"
                                all_authorized = False

                            # Continue to next procedure - TASY succeeded
                            results.append(auth_result)
                            continue

                        except ExternalServiceException as tasy_exc:
                            self._logger.warning(
                                "tasy_auth_submit_failed_fallback_to_insurance_api",
                                code=code,
                                payer_id=payer_id,
                                error=str(tasy_exc),
                                tenant_id=ctx.tenant_id,
                            )
                            # Fall back to insurance API below

                    # Use insurance API as fallback or primary
                    auth_request = AuthorizationRequest(
                        patient_id=patient_id,
                        member_id=patient_id,
                        payer_id=payer_id,
                        provider_id=ctx.tenant_id,
                        procedure_codes=[code],
                        diagnosis_codes=diagnosis_codes,
                        requested_start_date=datetime.utcnow(),
                        quantity=proc.get("quantity", 1),
                    )
                    auth_resp = await self._insurance.request_authorization(auth_request)

                    auth_result["auth_number"] = auth_resp.auth_number
                    auth_result["status"] = auth_resp.status

                    if auth_resp.status == "approved":
                        auth_result["authorized"] = True
                        auth_result["message"] = auth_resp.response_message
                        if not final_auth_number:
                            final_auth_number = auth_resp.auth_number
                    elif auth_resp.status == "denied":
                        auth_result["authorized"] = False
                        auth_result["message"] = auth_resp.denial_reason or ""
                        all_authorized = False
                    else:
                        auth_result["authorized"] = False
                        auth_result["message"] = f"Status: {auth_resp.status}"
                        all_authorized = False

                except Exception as exc:
                    self._logger.error(
                        "auth_request_failed",
                        code=code,
                        payer_id=payer_id,
                        error=str(exc),
                        tenant_id=ctx.tenant_id,
                    )
                    auth_result["status"] = "error"
                    auth_result["message"] = str(exc)
                    all_authorized = False

            results.append(auth_result)

        if not all_authorized:
            denied = [r for r in results if not r["authorized"]]
            self._logger.error(
                "authorization_failed",
                denied_count=len(denied),
                tenant_id=ctx.tenant_id,
            )
            first_denied = denied[0] if denied else {}
            raise AuthorizationDenied(
                _("Authorization {auth_id} was denied: {reason}").format(
                    auth_id=first_denied.get("auth_number", "N/A"),
                    reason=first_denied.get("message", "unknown"),
                ),
                details={"denied_procedures": [d["code"] for d in denied]},
            )

        self._logger.info(
            "authorization_complete",
            all_authorized=all_authorized,
            auth_number=final_auth_number,
            tenant_id=ctx.tenant_id,
        )

        return {
            "authorization_results": results,
            "all_authorized": all_authorized,
            "auth_number": final_auth_number,
        }
