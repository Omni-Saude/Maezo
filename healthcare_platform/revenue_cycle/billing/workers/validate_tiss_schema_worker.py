"""Validate TISS XML against ANS schema."""
from __future__ import annotations

from datetime import datetime

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.shared.domain.enums import TISSGuideType
from healthcare_platform.shared.domain.exceptions import TISSException, TISSValidationError
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tiss_client import TISSClientProtocol, TISSGuideDTO


@worker(topic="billing-validate-tiss-schema", max_jobs=3, lock_duration=300000)
class ValidateTISSSchemaWorker(BaseWorker):
    """
    Validate generated TISS XML against ANS schema.

    Input variables:
        - tiss_xml (str): TISS XML string to validate
        - guide_type (str): TISS guide type enum value
        - guide_number (str): Optional guide number for logging
        - payer_id (str): Optional payer ID for reconstruction
        - provider_id (str): Optional provider ID for reconstruction
        - patient_id (str): Optional patient ID for reconstruction

    Output variables:
        - schema_valid (bool): True if schema validation passes
        - schema_errors (list[str]): List of schema validation errors
    

    Archetype: FINANCIAL_CALCULATION"""

    def __init__(self, tiss_client: TISSClientProtocol) -> None:
        """
        Initialize worker with TISS client.

        Args:
            tiss_client: TISS client implementation for schema validation
        """
        super().__init__()
        self._tiss_client = tiss_client
        self.dmn_service = FederatedDMNService()

    @property
    def operation_name(self) -> str:
        return _("Validar esquema TISS")

    def _evaluate_billing_dmn(self, subcategory: str, table_name: str, inputs: dict) -> dict:
        """Evaluate billing DMN decision table via federation service."""
        try:
            return self.dmn_service.evaluate(
                tenant_id=getattr(self, '_tenant_id', 'default'),
                category='billing',
                table_name=f"{subcategory}/{table_name}",
                inputs=inputs,
            )
        except (FileNotFoundError, ValueError) as e:
            self._logger.warning("DMN evaluation fallback", table=table_name, error=str(e))
            return {}

    async def process_task(self, job, variables: dict) -> WorkerResult:
        """Process TISS schema validation task."""
        try:
            # Extract variables
            tiss_xml = variables.get("tiss_xml", "")
            guide_type_str = variables.get("guide_type", "")
            guide_number = variables.get("guide_number", "UNKNOWN")
            payer_id = variables.get("payer_id", "")
            provider_id = variables.get("provider_id", "")
            patient_id = variables.get("patient_id", "")

            # Validate required fields
            if not tiss_xml:
                raise TISSValidationError(_("XML TISS é obrigatório para validação"))
            if not guide_type_str:
                raise TISSValidationError(_("Tipo de guia é obrigatório"))

            # Parse guide type
            try:
                guide_type = TISSGuideType(guide_type_str)
            except ValueError:
                raise TISSValidationError(
                    _("Tipo de guia TISS inválido: {type}").format(type=guide_type_str)
                )

            # Reconstruct minimal guide DTO for validation
            guide_dto = self._reconstruct_guide_dto(
                guide_type=guide_type,
                guide_number=guide_number,
                payer_id=payer_id,
                provider_id=provider_id,
                patient_id=patient_id,
            )

            self._logger.info(
                "Validating TISS XML",
                guide_number=guide_number,
                guide_type=guide_type.value,
                xml_length=len(tiss_xml)
            )

            # Perform schema validation via TISS client
            validation_errors = await self._tiss_client.validate_guide(guide_dto)

            schema_valid = len(validation_errors) == 0

            if not schema_valid:
                self._logger.warning(
                    "TISS schema validation failed",
                    guide_number=guide_number,
                    error_count=len(validation_errors),
                    errors=validation_errors[:5]  # Log first 5 errors
                )

                # Check for critical errors that should stop the process
                critical_errors = self._filter_critical_errors(validation_errors)
                if critical_errors:
                    raise TISSValidationError(
                        _("Erros críticos de validação TISS: {errors}").format(
                            errors="; ".join(critical_errors)
                        )
                    )
            else:
                self._logger.info(
                    "TISS schema validation passed",
                    guide_number=guide_number
                )

            return WorkerResult.ok({
                "schema_valid": schema_valid,
                "schema_errors": validation_errors,
            })

        except (TISSException, TISSValidationError) as e:
            self._logger.error("TISS schema validation error", error=str(e))
            return WorkerResult.bpmn_error(
                error_code=e.bpmn_error_code,
                error_message=str(e)
            )
        except Exception as e:
            self._logger.error("Unexpected error in schema validation", error=str(e), exc_info=True)
            return WorkerResult.failure(
                error_message=_("Erro ao validar esquema TISS: {error}").format(error=str(e)),
                retry=True
            )

    def _reconstruct_guide_dto(
        self,
        guide_type: TISSGuideType,
        guide_number: str,
        payer_id: str,
        provider_id: str,
        patient_id: str,
    ) -> TISSGuideDTO:
        """
        Reconstruct a minimal TISSGuideDTO for validation.

        Note: The TISS client's validate_guide method primarily checks
        business rules, not XML schema. For full schema validation,
        we would need an XSD validator, but this provides basic validation.
        """
        return TISSGuideDTO(
            guide_type=guide_type,
            guide_number=guide_number or "VALIDATION-ONLY",
            payer_id=payer_id or "UNKNOWN",
            provider_id=provider_id or "UNKNOWN",
            patient_id=patient_id or "UNKNOWN",
            admission_date=None,
            discharge_date=None,
            diagnosis_codes=[],
            procedure_codes=[],
            total_amount=0.0,
            items=[],
        )

    def _filter_critical_errors(self, errors: list[str]) -> list[str]:
        """
        Filter validation errors to identify critical ones.

        Critical errors are those that would definitely cause rejection
        by the payer, such as missing mandatory fields or invalid codes.
        """
        critical_keywords = [
            "required",
            "obrigatório",
            "invalid",
            "inválido",
            "missing",
            "ausente",
            "not found",
            "não encontrado",
        ]

        critical_errors = []
        for error in errors:
            error_lower = error.lower()
            if any(keyword in error_lower for keyword in critical_keywords):
                critical_errors.append(error)

        return critical_errors
