from __future__ import annotations

"""
Submit Glosa Appeal Worker.

Submits appeals to payers via TISS protocol for denied or contested claims.
Handles TISS XML generation, submission, and error handling with retry logic.
"""

from datetime import datetime, timezone
from typing import Any, Dict

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.revenue_cycle.glosa.workers.base import GlosaWorkerMixin
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.enums import GlosaType, GlosaReasonCode
from healthcare_platform.shared.domain.exceptions import GlosaException
from healthcare_platform.shared.domain.value_objects import Money
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClientProtocol
from healthcare_platform.shared.integrations.tiss_client import (
    TISSClientProtocol,
    TISSGuideDTO,
    TISSSubmissionResult,
)
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="submit-glosa-appeal", max_jobs=5, lock_duration=30000)
class SubmitAppealWorker(BaseWorker, GlosaWorkerMixin):
    """
    Submit glosa appeal to payer via TISS protocol.

    Builds TISS-compliant appeal submission, submits to payer,
    and handles errors with retry logic.

        Archetype: ADMIN_ADJUDICATION
    """

    def __init__(
        self,
        tiss_client: TISSClientProtocol,
        tasy_api_client: TasyApiClientProtocol | None = None,
    ) -> None:
        """
        Initialize worker with TISS client dependency.

        Args:
            tiss_client: TISS protocol client for payer communication
            tasy_api_client: Optional TASY API client for recording appeals
        """
        self.tiss_client = tiss_client
        self.tasy_api_client = tasy_api_client
        self.dmn_service = FederatedDMNService()

    def _evaluate_glosa_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate glosa_prevention DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='glosa_prevention',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    def _evaluate_appeal_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate revenue_recovery DMN decision table."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='revenue_recovery',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    async def process_task(
        self,
        job: Any,
        variables: Dict[str, Any],
    ) -> WorkerResult:
        """
        Submit appeal to payer via TISS.

        Args:
            job: Zeebe job instance
            variables: Input variables containing:
                - appealDocumentId: ID of appeal document
                - claimId: Claim identifier
                - eligibleGlosas: List of glosa items to appeal
                - appealLetter: Justification text
                - payerId: Payer identifier
                - providerId: Provider identifier

        Returns:
            WorkerResult with submission details
        """
        try:
            appeal_doc_id = variables.get("appealDocumentId")
            claim_id = variables.get("claimId")
            eligible_glosas = variables.get("eligibleGlosas", [])
            appeal_letter = variables.get("appealLetter", "")
            payer_id = variables.get("payerId")
            provider_id = variables.get("providerId")

            logger.info(
                "Submitting appeal",
                extra={
                    "appeal_document_id": appeal_doc_id,
                    "claim_id": claim_id,
                    "glosa_count": len(eligible_glosas),
                    "payer_id": payer_id,
                }
            )

            # Validate required inputs
            if not appeal_doc_id:
                raise GlosaException(_("ID do documento de recurso é obrigatório"))

            if not claim_id:
                raise GlosaException(_("ID da conta é obrigatório"))

            if not eligible_glosas:
                raise GlosaException(_("Nenhuma glosa elegível para recurso"))

            if not payer_id or not provider_id:
                raise GlosaException(_("IDs de operadora e prestador são obrigatórios"))

            # Build TISS guide DTO
            guide_dto = self._build_appeal_guide(
                appeal_doc_id=appeal_doc_id,
                claim_id=claim_id,
                eligible_glosas=eligible_glosas,
                appeal_letter=appeal_letter,
                payer_id=payer_id,
                provider_id=provider_id,
            )

            # Submit to payer via TISS
            submission_result = await self._submit_with_retry(guide_dto, max_retries=3)

            # Record appeal in TASY if client available
            if self.tasy_api_client and submission_result.success:
                try:
                    await self._record_appeal_in_tasy(appeal_doc_id, submission_result)
                except Exception as exc:
                    logger.warning(
                        "Failed to record appeal in TASY",
                        extra={"appeal_doc_id": appeal_doc_id, "error": str(exc)},
                    )

            # Prepare output variables
            output_vars = {
                "submissionProtocol": submission_result.protocol_number,
                "submissionTimestamp": datetime.now(timezone.utc).isoformat(),
                "submissionSuccess": submission_result.success,
                "payerResponseCode": submission_result.response_code,
                "payerResponseMessage": submission_result.response_message,
            }

            if submission_result.success:
                logger.info(
                    "Appeal submitted successfully",
                    extra={
                        "protocol": submission_result.protocol_number,
                        "claim_id": claim_id,
                    }
                )
                return WorkerResult.success(output_vars)
            else:
                logger.warning(
                    "Appeal submission failed",
                    extra={
                        "claim_id": claim_id,
                        "error_code": submission_result.response_code,
                        "error_message": submission_result.response_message,
                    }
                )
                return WorkerResult.failure(
                    error_message=_("Falha ao enviar recurso: {}").format(
                        submission_result.response_message
                    ),
                    variables=output_vars,
                )

        except GlosaException as e:
            logger.error("Glosa exception during appeal submission", exc_info=e)
            return WorkerResult.failure(error_message=str(e))
        except Exception as e:
            logger.error("Unexpected error submitting appeal", exc_info=e)
            return WorkerResult.failure(
                error_message=_("Erro inesperado ao enviar recurso: {}").format(str(e))
            )

    def _build_appeal_guide(
        self,
        appeal_doc_id: str,
        claim_id: str,
        eligible_glosas: list,
        appeal_letter: str,
        payer_id: str,
        provider_id: str,
    ) -> TISSGuideDTO:
        """
        Build TISS guide DTO for appeal submission.

        Args:
            appeal_doc_id: Appeal document identifier
            claim_id: Claim identifier
            eligible_glosas: List of glosa items being appealed
            appeal_letter: Justification text
            payer_id: Payer identifier
            provider_id: Provider identifier

        Returns:
            TISSGuideDTO ready for submission
        """
        guide_items = []
        for glosa in eligible_glosas:
            guide_items.append({
                "glosaId": glosa.get("glosaId"),
                "itemCode": glosa.get("itemCode"),
                "deniedAmount": glosa.get("deniedAmount"),
                "reasonCode": glosa.get("reasonCode"),
                "justification": appeal_letter,
            })

        return TISSGuideDTO(
            guide_type="APPEAL",
            guide_number=appeal_doc_id,
            claim_id=claim_id,
            payer_id=payer_id,
            provider_id=provider_id,
            items=guide_items,
            additional_data={"appealLetter": appeal_letter},
        )

    async def _submit_with_retry(
        self,
        guide_dto: TISSGuideDTO,
        max_retries: int = 3,
    ) -> TISSSubmissionResult:
        """
        Submit guide with retry logic for transient failures.

        Args:
            guide_dto: TISS guide to submit
            max_retries: Maximum retry attempts

        Returns:
            TISSSubmissionResult with submission outcome

        Raises:
            GlosaException: If all retries exhausted
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                logger.info(
                    "Attempting TISS submission",
                    extra={"attempt": attempt + 1, "max_retries": max_retries}
                )
                result = await self.tiss_client.submit_guide(guide_dto)

                if result.success or result.response_code not in ["TIMEOUT", "CONNECTION_ERROR"]:
                    return result

                last_error = result.response_message
                logger.warning(
                    "Transient error, retrying",
                    extra={
                        "attempt": attempt + 1,
                        "error": result.response_message,
                    }
                )

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "Exception during submission, retrying",
                    extra={"attempt": attempt + 1},
                    exc_info=e,
                )

        raise GlosaException(
            _("Falha ao enviar recurso após {} tentativas: {}").format(
                max_retries, last_error
            )
        )

    async def _record_appeal_in_tasy(
        self, glosa_id: str, submission_result: TISSSubmissionResult
    ) -> None:
        """Record appeal submission in TASY via API.

        Args:
            glosa_id: TASY glosa ID
            submission_result: TISS submission result
        """
        appeal_data = {
            "protocol": submission_result.protocol_number,
            "submission_timestamp": datetime.now(timezone.utc).isoformat(),
            "response_code": submission_result.response_code,
        }

        result = await self.tasy_api_client.submit_glosa_appeal(glosa_id, appeal_data)

        logger.info(
            "Appeal recorded in TASY",
            extra={
                "glosa_id": glosa_id,
                "appeal_id": result.get("appeal_id"),
                "protocol": submission_result.protocol_number,
            },
        )
