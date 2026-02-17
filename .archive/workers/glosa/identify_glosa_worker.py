"""
Identify Glosa Worker

Worker responsible for identifying glosas (denials) from payer claim responses.
Parses ClaimResponse data and extracts denied items with reasons and amounts.
"""

from decimal import Decimal
from typing import Any, Dict, List

from healthcare_platform.revenue_cycle.glosa.workers.base import (
    BaseWorker,
    GlosaWorkerMixin,
    WorkerResult,
    worker,
)
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.entities import ClaimResponse, GlosaItem
from healthcare_platform.shared.domain.enums import GlosaReasonCode
from healthcare_platform.shared.domain.exceptions import GlosaException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClientProtocol
from healthcare_platform.shared.observability.logging import get_logger

logger = get_logger(__name__)


@worker(topic="identify-glosa", max_jobs=10, lock_duration=30000)
class IdentifyGlosaWorker(BaseWorker, GlosaWorkerMixin):
    """
    Worker that identifies glosas from payer claim responses.

    Processes ClaimResponse data to extract denied items, classify denial reasons,
    and calculate denied amounts.

    Input Variables:
        - claimResponse: ClaimResponse entity or dict with claim adjudication data
        - claimId: Reference to the original claim

    Output Variables:
        - glosaItems: List of identified glosas with details
        - totalDeniedAmount: Total BRL amount denied
        - glosaCount: Number of glosas identified
        - hasGlosas: Boolean indicating if any glosas were found
    """

    def __init__(self, tasy_api_client: TasyApiClientProtocol | None = None) -> None:
        super().__init__()
        self.dmn_service = FederatedDMNService()
        self.tasy_api_client = tasy_api_client

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

    async def process_task(self, job: Any, variables: Dict[str, Any]) -> WorkerResult:
        """
        Process claim response to identify glosas.

        Args:
            job: Zeebe job object
            variables: Process variables containing claimResponse

        Returns:
            WorkerResult with identified glosa items and totals
        """
        logger.info(
            _("Iniciando identificação de glosas"),
            extra={"job_key": job.key if hasattr(job, "key") else None},
        )

        try:
            # Extract claim response
            claim_response_data = variables.get("claimResponse")
            if not claim_response_data:
                raise GlosaException(_("Resposta da operadora não encontrada"))

            claim_id = variables.get("claimId")

            # Parse claim response
            if isinstance(claim_response_data, ClaimResponse):
                claim_response = claim_response_data
            elif isinstance(claim_response_data, dict):
                claim_response = self._parse_claim_response(claim_response_data)
            else:
                raise GlosaException(
                    _("Formato de resposta da operadora inválido: {type}").format(
                        type=type(claim_response_data).__name__
                    )
                )

            # Identify denied items
            glosa_items = self._extract_glosa_items(claim_response)

            # Calculate totals
            total_denied = sum(
                (item["denied_amount"] for item in glosa_items), Decimal("0")
            )

            # Record glosas in TASY if client available
            if self.tasy_api_client and glosa_items:
                try:
                    await self._record_glosas_in_tasy(claim_id, glosa_items, total_denied)
                except Exception as exc:
                    logger.warning(
                        _("Falha ao registrar glosas no TASY: {error}").format(error=str(exc)),
                        extra={"claim_id": claim_id},
                    )

            output_variables = {
                "glosaItems": glosa_items,
                "totalDeniedAmount": float(total_denied),
                "glosaCount": len(glosa_items),
                "hasGlosas": len(glosa_items) > 0,
            }

            logger.info(
                _("Identificadas {count} glosas totalizando R$ {amount:.2f}").format(
                    count=len(glosa_items), amount=total_denied
                ),
                extra={"claim_id": claim_id, "glosa_count": len(glosa_items)},
            )

            return WorkerResult.success(output_variables)

        except GlosaException as e:
            logger.error(_("Erro ao identificar glosas: {error}").format(error=str(e)))
            return WorkerResult.failure(str(e))
        except Exception as e:
            logger.exception(_("Erro inesperado ao identificar glosas"))
            return WorkerResult.failure(
                _("Erro ao processar resposta da operadora: {error}").format(
                    error=str(e)
                )
            )

    def _parse_claim_response(self, data: Dict[str, Any]) -> ClaimResponse:
        """
        Parse claim response dictionary into ClaimResponse entity.

        Args:
            data: Raw claim response data

        Returns:
            ClaimResponse entity
        """
        # In production, this would use a proper parser/factory
        return ClaimResponse(
            id=data.get("id"),
            claim_reference=data.get("claimReference"),
            status=data.get("status"),
            items=data.get("items", []),
            total=data.get("total"),
        )

    def _extract_glosa_items(self, claim_response: ClaimResponse) -> List[Dict]:
        """
        Extract glosa items from claim response.

        Args:
            claim_response: Parsed claim response entity

        Returns:
            List of glosa item dictionaries
        """
        glosa_items = []

        for item in claim_response.items:
            adjudication = item.get("adjudication", [])

            for adj in adjudication:
                # Check if this is a denial/glosa
                if adj.get("category") in ["denied", "rejected"]:
                    reason_code = self._map_reason_code(adj.get("reason"))
                    denied_amount = Decimal(str(adj.get("amount", 0)))
                    original_amount = Decimal(str(item.get("unitPrice", 0))) * Decimal(
                        str(item.get("quantity", 1))
                    )

                    glosa_item = {
                        "item_sequence": item.get("sequence"),
                        "procedure_code": item.get("productOrService", {}).get("code"),
                        "glosa_type": None,  # Will be classified by next worker
                        "reason_code": reason_code.value,
                        "reason_display": self._get_glosa_reason_display(reason_code),
                        "denied_amount": float(denied_amount),
                        "original_amount": float(original_amount),
                        "notes": adj.get("reason"),
                    }

                    glosa_items.append(glosa_item)

        return glosa_items

    def _map_reason_code(self, reason: str) -> GlosaReasonCode:
        """
        Map payer reason text to standardized GlosaReasonCode.

        Args:
            reason: Payer-provided reason text

        Returns:
            Mapped GlosaReasonCode enum value
        """
        if not reason:
            return GlosaReasonCode.TISS_VALIDATION

        reason_lower = reason.lower()

        # Simple keyword-based mapping
        if "autorização" in reason_lower or "guia" in reason_lower:
            if "expirada" in reason_lower or "vencida" in reason_lower:
                return GlosaReasonCode.EXPIRED_AUTH
            return GlosaReasonCode.MISSING_AUTH
        elif "duplicad" in reason_lower:
            return GlosaReasonCode.DUPLICATE_CHARGE
        elif "quantidade" in reason_lower or "excede" in reason_lower:
            return GlosaReasonCode.EXCEEDS_QUANTITY
        elif "não coberto" in reason_lower or "não previsto" in reason_lower:
            return GlosaReasonCode.NOT_COVERED
        elif "código" in reason_lower and "incorreto" in reason_lower:
            return GlosaReasonCode.WRONG_CODE
        elif "documentação" in reason_lower or "documento" in reason_lower:
            return GlosaReasonCode.MISSING_DOCUMENTATION
        elif "incompatível" in reason_lower or "diagnóstico" in reason_lower:
            return GlosaReasonCode.INCOMPATIBLE_PROCEDURE
        elif "valor" in reason_lower or "preço" in reason_lower:
            return GlosaReasonCode.PRICE_DIVERGENCE
        else:
            return GlosaReasonCode.TISS_VALIDATION

    async def _record_glosas_in_tasy(
        self, claim_id: str, glosa_items: list[dict], total_denied: Decimal
    ) -> None:
        """Record identified glosas in TASY via API.

        Args:
            claim_id: Claim/account ID
            glosa_items: List of glosa items
            total_denied: Total denied amount
        """
        glosa_data = {
            "claim_id": claim_id,
            "denied_amount": float(total_denied),
            "reason_code": glosa_items[0]["reason_code"] if glosa_items else "UNKNOWN",
            "items": glosa_items,
        }

        result = await self.tasy_api_client.post_glosa(glosa_data)

        logger.info(
            _("Glosa registrada no TASY"),
            extra={
                "claim_id": claim_id,
                "glosa_id": result.get("glosa_id"),
                "denied_amount": float(total_denied),
            },
        )
