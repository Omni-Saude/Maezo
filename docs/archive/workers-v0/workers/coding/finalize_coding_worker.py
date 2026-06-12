"""Finalize and lock coding on an encounter.

CIB7 External Task Topic: coding.finalize_coding
BPMN Error Codes: CODING_NOT_APPROVED, FRAUD_BLOCK, CODING_ERROR

Phase 2.2 - SUB_05_Coding_Audit: Final step that locks validated codes
on the encounter, updates status to CODED, and produces a coding summary
with all audit/complexity/fraud metadata.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from healthcare_platform.shared.domain.exceptions import BpmnErrorException, CodingException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_APPROVED_AUDIT = "approve"
_ALLOWED_FRAUD_RECOMMENDATIONS = {"clear", "review"}
_STATUS_CODED = "CODED"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class FinalizeCodingInput(BaseModel):
    """Input variables for the finalize-coding task."""

    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(
        ..., alias="encounterId", min_length=1,
        description="Unique encounter identifier",
    )
    validated_cid10: list[str] = Field(
        ..., alias="validatedCid10",
        description="Final validated CID-10 codes",
    )
    validated_tuss: list[str] = Field(
        ..., alias="validatedTuss",
        description="Final validated TUSS codes",
    )
    audit_recommendation: str = Field(
        ..., alias="auditRecommendation", min_length=1,
        description="Audit recommendation (approve | reject | review)",
    )
    audit_score: int = Field(
        ..., alias="auditScore", ge=0, le=100,
        description="Audit quality score 0-100",
    )
    complexity_score: int = Field(
        ..., alias="complexityScore", ge=0,
        description="Clinical complexity score",
    )
    complexity_level: str = Field(
        ..., alias="complexityLevel", min_length=1,
        description="LOW | MODERATE | HIGH | VERY_HIGH",
    )
    fraud_recommendation: str = Field(
        ..., alias="fraudRecommendation", min_length=1,
        description="Fraud engine recommendation (clear | review | flag)",
    )
    coded_by: str = Field(
        ..., alias="codedBy", min_length=1,
        description="User or system that performed coding",
    )
    tenant_id: str = Field(
        ..., alias="tenantId", min_length=1,
        description="Tenant identifier",
    )

    @field_validator(
        "encounter_id", "audit_recommendation", "complexity_level",
        "fraud_recommendation", "coded_by", "tenant_id",
    )
    @classmethod
    def validate_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return v.strip()


class CodingSummary(BaseModel):
    """Summary of all coding metadata attached to the encounter."""

    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(..., alias="encounterId")
    cid10_codes: list[str] = Field(..., alias="cid10Codes")
    tuss_codes: list[str] = Field(..., alias="tussCodes")
    audit_recommendation: str = Field(..., alias="auditRecommendation")
    audit_score: int = Field(..., alias="auditScore")
    complexity_score: int = Field(..., alias="complexityScore")
    complexity_level: str = Field(..., alias="complexityLevel")
    fraud_recommendation: str = Field(..., alias="fraudRecommendation")
    coded_by: str = Field(..., alias="codedBy")
    finalized_at: str = Field(..., alias="finalizedAt")
    status: str = Field(default=_STATUS_CODED)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


class FinalizeCodingOutput(BaseModel):
    """Output variables for the finalize-coding task."""

    model_config = ConfigDict(populate_by_name=True)

    coding_finalized: bool = Field(
        ..., alias="codingFinalized",
        description="Whether coding was successfully locked",
    )
    final_cid10: list[str] = Field(
        ..., alias="finalCid10",
        description="Locked CID-10 codes",
    )
    final_tuss: list[str] = Field(
        ..., alias="finalTuss",
        description="Locked TUSS codes",
    )
    coding_summary: dict[str, Any] = Field(
        ..., alias="codingSummary",
        description="Full coding summary with all metadata",
    )
    coding_timestamp: str = Field(
        ..., alias="codingTimestamp",
        description="ISO-8601 timestamp of finalization",
    )

    def to_variables(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


# ---------------------------------------------------------------------------
# Protocol & Stub
# ---------------------------------------------------------------------------

@runtime_checkable
class EncounterRepositoryProtocol(Protocol):
    """Contract for the encounter persistence dependency."""

    async def lock_coding(
        self,
        encounter_id: str,
        coding_data: dict[str, Any],
    ) -> bool:
        """Lock coding on the encounter, preventing further edits."""
        ...

    async def update_status(
        self,
        encounter_id: str,
        status: str,
    ) -> bool:
        """Update the encounter status."""
        ...


class EncounterRepositoryStub:
    """Stub that always succeeds and logs the operation.

    Production implementation persists to the encounter store (FHIR/ERP).
    """

    def __init__(self) -> None:
        self._logger = get_logger(__name__, component="encounter_repo_stub")

    async def lock_coding(
        self,
        encounter_id: str,
        coding_data: dict[str, Any],
    ) -> bool:
        self._logger.info(
            "coding_locked_stub",
            encounter_id=encounter_id,
            cid10_count=len(coding_data.get("cid10Codes", [])),
            tuss_count=len(coding_data.get("tussCodes", [])),
        )
        return True

    async def update_status(
        self,
        encounter_id: str,
        status: str,
    ) -> bool:
        self._logger.info(
            "status_updated_stub",
            encounter_id=encounter_id,
            status=status,
        )
        return True


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class FinalizeCodingWorker:
    """Locks validated codes on an encounter and updates status to CODED.

    Pre-conditions checked before finalization:
      - auditRecommendation must be 'approve'
      - fraudRecommendation must be 'clear' or 'review'

    If either pre-condition fails the worker raises a BPMN error so the
    process can route to the appropriate correction flow.
    """

    TOPIC = "coding.finalize_coding"

    def __init__(
        self,
        encounter_repo: EncounterRepositoryProtocol | None = None,
        tasy_api_client: TasyApiClientProtocol | None = None,
    ) -> None:
        self._repo: EncounterRepositoryProtocol = (
            encounter_repo or EncounterRepositoryStub()
        )
        self._tasy_api: TasyApiClientProtocol | None = tasy_api_client
        self._logger = get_logger(__name__, worker=self.TOPIC)
        self.dmn_service = FederatedDMNService()

    @require_tenant
    @track_task_execution(metric_name="coding_finalize_coding")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Finalize coding on an encounter.

        Task Variables (input):
            encounterId: str
            validatedCid10: list[str]
            validatedTuss: list[str]
            auditRecommendation: str
            auditScore: int
            complexityScore: int
            complexityLevel: str
            fraudRecommendation: str
            codedBy: str
            tenantId: str

        Returns:
            codingFinalized: bool
            finalCid10: list[str]
            finalTuss: list[str]
            codingSummary: dict
            codingTimestamp: str
        """
        ctx = get_required_tenant()

        # -- Parse & validate input ------------------------------------------
        try:
            inp = FinalizeCodingInput(**task_variables)
        except Exception as exc:
            raise CodingException(
                _("Dados de entrada invalidos para finalizacao de codificacao: {error}").format(
                    error=str(exc),
                ),
                bpmn_error_code="CODING_ERROR",
            ) from exc

        self._logger.info(
            "finalize_coding_started",
            encounter_id=inp.encounter_id,
            audit_recommendation=inp.audit_recommendation,
            fraud_recommendation=inp.fraud_recommendation,
            coded_by=inp.coded_by,
            tenant_id=ctx.tenant_id,
        )

        # -- Pre-condition: audit must be approved ----------------------------
        if inp.audit_recommendation.lower() != _APPROVED_AUDIT:
            self._logger.warning(
                "coding_not_approved",
                encounter_id=inp.encounter_id,
                audit_recommendation=inp.audit_recommendation,
                tenant_id=ctx.tenant_id,
            )
            raise BpmnErrorException(
                error_code="CODING_NOT_APPROVED",
                message=_(
                    "Codificacao nao aprovada pela auditoria: "
                    "recomendacao '{recommendation}'"
                ).format(recommendation=inp.audit_recommendation),
            )

        # -- Pre-validation: Validate TUSS codes exist in TASY (if available) --
        if self._tasy_api:
            await self._validate_tuss_codes(inp.validated_tuss, ctx.tenant_id)

        # -- Pre-condition: fraud must not be flagged -------------------------
        if inp.fraud_recommendation.lower() not in _ALLOWED_FRAUD_RECOMMENDATIONS:
            self._logger.warning(
                "fraud_block",
                encounter_id=inp.encounter_id,
                fraud_recommendation=inp.fraud_recommendation,
                tenant_id=ctx.tenant_id,
            )
            raise BpmnErrorException(
                error_code="FRAUD_BLOCK",
                message=_(
                    "Codificacao bloqueada por deteccao de fraude: "
                    "recomendacao '{recommendation}'"
                ).format(recommendation=inp.fraud_recommendation),
            )

        # -- Build coding summary --------------------------------------------
        now = datetime.now(tz=timezone.utc)
        timestamp_iso = now.isoformat()

        summary = CodingSummary(
            encounter_id=inp.encounter_id,
            cid10_codes=inp.validated_cid10,
            tuss_codes=inp.validated_tuss,
            audit_recommendation=inp.audit_recommendation,
            audit_score=inp.audit_score,
            complexity_score=inp.complexity_score,
            complexity_level=inp.complexity_level,
            fraud_recommendation=inp.fraud_recommendation,
            coded_by=inp.coded_by,
            finalized_at=timestamp_iso,
        )

        # -- Lock coding on the encounter ------------------------------------
        coding_data = summary.to_dict()

        lock_ok = await self._repo.lock_coding(
            encounter_id=inp.encounter_id,
            coding_data=coding_data,
        )

        if not lock_ok:
            self._logger.error(
                "coding_lock_failed",
                encounter_id=inp.encounter_id,
                tenant_id=ctx.tenant_id,
            )
            raise CodingException(
                _("Falha ao bloquear codificacao para o atendimento {encounter_id}").format(
                    encounter_id=inp.encounter_id,
                ),
                bpmn_error_code="CODING_ERROR",
            )

        # -- Update encounter status to CODED ---------------------------------
        status_ok = await self._repo.update_status(
            encounter_id=inp.encounter_id,
            status=_STATUS_CODED,
        )

        if not status_ok:
            self._logger.error(
                "status_update_failed",
                encounter_id=inp.encounter_id,
                target_status=_STATUS_CODED,
                tenant_id=ctx.tenant_id,
            )
            raise CodingException(
                _("Falha ao atualizar status do atendimento {encounter_id} para {status}").format(
                    encounter_id=inp.encounter_id,
                    status=_STATUS_CODED,
                ),
                bpmn_error_code="CODING_ERROR",
            )

        self._logger.info(
            "finalize_coding_completed",
            encounter_id=inp.encounter_id,
            cid10_count=len(inp.validated_cid10),
            tuss_count=len(inp.validated_tuss),
            audit_score=inp.audit_score,
            complexity_score=inp.complexity_score,
            complexity_level=inp.complexity_level,
            coded_by=inp.coded_by,
            tenant_id=ctx.tenant_id,
        )

        output = FinalizeCodingOutput(
            coding_finalized=True,
            final_cid10=inp.validated_cid10,
            final_tuss=inp.validated_tuss,
            coding_summary=coding_data,
            coding_timestamp=timestamp_iso,
        )
        return output.to_variables()




    async def _validate_tuss_codes(self, tuss_codes: list[str], tenant_id: str) -> None:
        """Validate TUSS codes exist in TASY master data.

        Falls back silently if TASY API is unavailable - existing logic will handle.

        Args:
            tuss_codes: List of TUSS codes to validate
            tenant_id: Current tenant ID for logging

        Raises:
            CodingException: If codes are invalid and TASY is available
        """
        if not tuss_codes:
            return

        try:
            for code in tuss_codes:
                # Try to search for the code in TASY
                results = await self._tasy_api.search_tuss_procedures(code=code)
                if not results:
                    self._logger.warning(
                        "tuss_code_not_found_in_tasy",
                        code=code,
                        tenant_id=tenant_id,
                    )
                    raise CodingException(
                        _("Código TUSS não encontrado no TASY: {}").format(code),
                        bpmn_error_code="CODING_ERROR",
                    )
        except CodingException:
            # Re-raise coding exceptions
            raise
        except Exception as exc:
            # Fall back silently on TASY errors - let existing logic handle
            self._logger.info(
                "tasy_validation_unavailable",
                error=str(exc),
                tenant_id=tenant_id,
                message="Falling back to existing validation logic",
            )

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

def register_worker(
    *,
    encounter_repo: EncounterRepositoryProtocol | None = None,
    tasy_api_client: TasyApiClientProtocol | None = None,
) -> FinalizeCodingWorker:
    """Create and return a configured FinalizeCodingWorker instance."""
    return FinalizeCodingWorker(
        encounter_repo=encounter_repo,
        tasy_api_client=tasy_api_client,
    )
