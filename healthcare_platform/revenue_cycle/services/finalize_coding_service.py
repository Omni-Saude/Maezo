"""Finalize coding business logic service.

This service encapsulates all business logic for coding finalization,
including DMN gate checks, summary building, and locking.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from healthcare_platform.shared.domain.exceptions import BpmnErrorException, CodingException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService


class FinalizeCodingInput(BaseModel):
    """Input variables for the finalize-coding task."""
    model_config = ConfigDict(populate_by_name=True)

    encounter_id: str = Field(..., alias="encounterId", min_length=1)
    validated_cid10: list[str] = Field(..., alias="validatedCid10")
    validated_tuss: list[str] = Field(..., alias="validatedTuss")
    audit_recommendation: str = Field(..., alias="auditRecommendation", min_length=1)
    audit_score: int = Field(..., alias="auditScore", ge=0, le=100)
    complexity_score: int = Field(..., alias="complexityScore", ge=0)
    complexity_level: str = Field(..., alias="complexityLevel", min_length=1)
    fraud_recommendation: str = Field(..., alias="fraudRecommendation", min_length=1)
    coded_by: str = Field(..., alias="codedBy", min_length=1)
    tenant_id: str = Field(..., alias="tenantId", min_length=1)

    @field_validator("encounter_id", "audit_recommendation", "coded_by", "tenant_id")
    @classmethod
    def validate_not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


class FinalizeCodingOutput(BaseModel):
    """Output variables for the finalize-coding task."""
    model_config = ConfigDict(populate_by_name=True)

    coding_finalized: bool = Field(..., alias="codingFinalized")
    final_cid10: list[str] = Field(..., alias="finalCid10")
    final_tuss: list[str] = Field(..., alias="finalTuss")
    coding_summary: dict[str, Any] = Field(..., alias="codingSummary")
    coding_timestamp: str = Field(..., alias="codingTimestamp")

    def to_variables(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True)


class FinalizeCodingService:
    """Service for finalizing coding on encounters."""

    def __init__(self, dmn_service: FederatedDMNService | None = None):
        self._logger = get_logger(__name__)
        self.dmn_service = dmn_service or FederatedDMNService()

    async def finalize(
        self,
        task_variables: dict[str, Any],
        tenant_id: str,
        encounter_service: Any = None,
    ) -> dict[str, Any]:
        """Finalize coding on an encounter via DMN gate checks.

        Args:
            task_variables: Input variables with validated codes
            tenant_id: Tenant ID for DMN evaluation
            encounter_service: Optional service for locking/saving

        Returns:
            Dictionary with finalization results

        Raises:
            BpmnErrorException: If DMN gates block finalization
            CodingException: If validation or locking fails
        """
        # Validate input
        try:
            inp = FinalizeCodingInput(**task_variables)
        except Exception as exc:
            raise CodingException(
                _("Dados de entrada inválidos para finalização"),
                bpmn_error_code="CODING_ERROR",
            ) from exc

        self._logger.info(
            "finalize_coding_started",
            encounter_id=inp.encounter_id,
            audit_recommendation=inp.audit_recommendation,
            fraud_recommendation=inp.fraud_recommendation,
            tenant_id=tenant_id,
        )

        # Gate 1: Check audit approval via DMN
        audit_result = self._evaluate_dmn(
            "finalization_gates",
            "audit_approval",
            {"audit_recommendation": inp.audit_recommendation, "audit_score": inp.audit_score},
            tenant_id,
        )

        # Handle old 5-output and new 3-output schemas
        resultado = audit_result.get("resultado") or audit_result.get("Prosseguir")
        if resultado in ["BLOQUEAR", "Bloquear"]:
            raise BpmnErrorException(
                error_code="CODING_NOT_APPROVED",
                message=_("Codificação não aprovada pela auditoria"),
            )

        # Gate 2: Check fraud clearance via DMN
        fraud_result = self._evaluate_dmn(
            "finalization_gates",
            "fraud_clearance",
            {"fraud_recommendation": inp.fraud_recommendation},
            tenant_id,
        )

        resultado_fraud = fraud_result.get("resultado") or fraud_result.get("Prosseguir")
        if resultado_fraud in ["BLOQUEAR", "Bloquear"]:
            raise BpmnErrorException(
                error_code="FRAUD_BLOCK",
                message=_("Codificação bloqueada por detecção de fraude"),
            )

        # Build summary
        now = datetime.now(tz=timezone.utc)
        timestamp_iso = now.isoformat()

        # If encounter_service is provided, lock the coding
        coding_locked = False
        if encounter_service:
            try:
                lock_info = await encounter_service.lock_coding(inp.encounter_id)
                coding_locked = True
                self._logger.info("coding_locked", encounter_id=inp.encounter_id, lock_info=lock_info)
            except Exception as e:
                self._logger.error("coding_lock_failed", encounter_id=inp.encounter_id, error=str(e))
                raise CodingException(f"Failed to lock coding: {str(e)}") from e

        summary = {
            "encounterId": inp.encounter_id,
            "cid10Codes": inp.validated_cid10,
            "tussCodes": inp.validated_tuss,
            "auditRecommendation": inp.audit_recommendation,
            "auditScore": inp.audit_score,
            "complexityScore": inp.complexity_score,
            "complexityLevel": inp.complexity_level,
            "fraudRecommendation": inp.fraud_recommendation,
            "codedBy": inp.coded_by,
            "finalizedAt": timestamp_iso,
            "status": "CODED",
        }

        # If encounter_service is provided, save final coding
        if encounter_service:
            try:
                save_result = await encounter_service.save_final_coding(
                    encounter_id=inp.encounter_id,
                    cid10_codes=inp.validated_cid10,
                    tuss_codes=inp.validated_tuss,
                    summary=summary,
                )
                self._logger.info("final_coding_saved", encounter_id=inp.encounter_id, result=save_result)
            except Exception as e:
                self._logger.warning("save_final_coding_failed", encounter_id=inp.encounter_id, error=str(e))
                # Continue even if save fails (coding is already locked)

        output = FinalizeCodingOutput(
            coding_finalized=True,
            final_cid10=inp.validated_cid10,
            final_tuss=inp.validated_tuss,
            coding_summary=summary,
            coding_timestamp=timestamp_iso,
        )

        self._logger.info(
            "finalize_coding_completed",
            encounter_id=inp.encounter_id,
            cid10_count=len(inp.validated_cid10),
            tuss_count=len(inp.validated_tuss),
            coding_locked=coding_locked,
            tenant_id=tenant_id,
        )

        # Add coding_locked to output
        result_vars = output.to_variables()
        result_vars["coding_locked"] = coding_locked
        result_vars["encounter_id"] = inp.encounter_id

        return result_vars

    def _evaluate_dmn(
        self,
        subcategory: str,
        table_name: str,
        inputs: dict,
        tenant_id: str,
    ) -> dict:
        """Evaluate coding_audit DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=tenant_id,
                category='coding_audit',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}
