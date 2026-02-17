"""Consolidate charge line items into a Claim entity."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.shared.domain.entities import Claim, ClaimItem
from healthcare_platform.shared.domain.enums import BillingStatus, ClaimStatus, ClaimUse, TenantCode, TISSGuideType
from healthcare_platform.shared.domain.exceptions import BillingException, ClaimValidationError
from healthcare_platform.shared.domain.value_objects import CodedValue, FHIRReference, Money
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _


@worker(topic="billing-consolidate-charges", max_jobs=5, lock_duration=300000)
class ConsolidateChargesWorker(BaseWorker):
    """
    Consolidate line items from clinical documentation into a structured Claim entity.

    Input variables:
        - encounter_id (str): Encounter UUID
        - patient_id (str): Patient UUID
        - payer_id (str): Insurance payer UUID
        - provider_id (str): Provider UUID
        - line_items (list[dict]): List of charge items with code, quantity, unit_price, etc.
        - tiss_guide_type (str): TISS guide type enum value
        - tenant_id (str): Tenant code

    Output variables:
        - claim_id (str): Generated Claim UUID
        - claim_total (float): Total claim amount
        - item_count (int): Number of line items
        - billing_status (str): Set to "validated"

    Archetype: FINANCIAL_CALCULATION
    """

    def __init__(self) -> None:
        super().__init__()
        self.dmn_service = FederatedDMNService()

    @property
    def operation_name(self) -> str:
        return _("Consolidar cobranças")

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
        """Process charge consolidation task."""
        try:
            # Extract required variables
            encounter_id = variables.get("encounter_id")
            patient_id = variables.get("patient_id")
            payer_id = variables.get("payer_id")
            provider_id = variables.get("provider_id")
            line_items = variables.get("line_items", [])
            tiss_guide_type_str = variables.get("tiss_guide_type", "")
            tenant_id_str = variables.get("tenant_id", "")

            # Validate required fields
            if not encounter_id:
                raise ClaimValidationError(_("ID do atendimento é obrigatório"))
            if not patient_id:
                raise ClaimValidationError(_("ID do paciente é obrigatório"))
            if not line_items:
                raise ClaimValidationError(_("Pelo menos um item de cobrança é obrigatório"))
            if not tenant_id_str:
                raise ClaimValidationError(_("ID do tenant é obrigatório"))

            # Validate line items
            if not isinstance(line_items, list):
                raise ClaimValidationError(_("line_items deve ser uma lista"))
            if len(line_items) == 0:
                raise ClaimValidationError(_("Pelo menos um item é obrigatório"))

            # Parse TISS guide type
            try:
                tiss_guide_type = TISSGuideType(tiss_guide_type_str) if tiss_guide_type_str else None
            except ValueError:
                tiss_guide_type = None
                self._logger.warning(
                    "Invalid TISS guide type",
                    tiss_guide_type=tiss_guide_type_str
                )

            # Parse tenant
            try:
                tenant_id = TenantCode(tenant_id_str)
            except ValueError:
                raise ClaimValidationError(_("Código do tenant inválido: {code}").format(code=tenant_id_str))

            # Build claim items
            claim_items: list[ClaimItem] = []
            total = Money.zero()

            for idx, item_data in enumerate(line_items, start=1):
                try:
                    claim_item = self._build_claim_item(item_data, idx)
                    claim_items.append(claim_item)
                    total = total + claim_item.total_price
                except Exception as e:
                    self._logger.error(
                        "Failed to build claim item",
                        sequence=idx,
                        error=str(e)
                    )
                    raise ClaimValidationError(
                        _("Item {seq} inválido: {error}").format(seq=idx, error=str(e))
                    )

            # Validate total
            if total.amount <= 0:
                raise ClaimValidationError(_("Total da conta deve ser maior que zero"))

            # Create Claim entity
            claim_id = uuid4()
            claim = Claim(
                id=claim_id,
                tenant_id=tenant_id,
                status=ClaimStatus.ACTIVE,
                use=ClaimUse.CLAIM,
                billing_status=BillingStatus.VALIDATED,
                patient_reference=FHIRReference(reference=f"Patient/{patient_id}"),
                encounter_reference=FHIRReference(reference=f"Encounter/{encounter_id}"),
                coverage_reference=FHIRReference(reference=f"Coverage/{payer_id}") if payer_id else None,
                provider_reference=FHIRReference(reference=f"Organization/{provider_id}") if provider_id else None,
                items=claim_items,
                total=total,
                tiss_guide_type=tiss_guide_type,
            )

            self._logger.info(
                "Claim consolidated",
                claim_id=str(claim_id),
                item_count=len(claim_items),
                total_amount=float(total.amount)
            )

            return WorkerResult.ok({
                "claim_id": str(claim_id),
                "claim_total": float(total.amount),
                "item_count": len(claim_items),
                "billing_status": BillingStatus.VALIDATED.value,
            })

        except ClaimValidationError as e:
            self._logger.error("Claim validation failed", error=str(e))
            return WorkerResult.bpmn_error(
                error_code=e.bpmn_error_code,
                error_message=str(e)
            )
        except Exception as e:
            self._logger.error("Unexpected error in consolidation", error=str(e), exc_info=True)
            return WorkerResult.failure(
                error_message=_("Erro ao consolidar cobranças: {error}").format(error=str(e)),
                retry=True
            )

    def _build_claim_item(self, item_data: dict, sequence: int) -> ClaimItem:
        """Build a ClaimItem from raw data."""
        # Extract required fields
        code = item_data.get("code", "")
        code_system = item_data.get("code_system", "http://www.ans.gov.br/tuss")
        display = item_data.get("display", "")
        quantity = item_data.get("quantity", 1)
        unit_price_amount = item_data.get("unit_price", 0)
        service_date_str = item_data.get("service_date")
        authorization_ref = item_data.get("authorization_reference")
        modifiers = item_data.get("modifiers", [])

        # Validate code
        if not code:
            raise ValueError(_("Código do procedimento é obrigatório"))

        # Build procedure code
        procedure_code = CodedValue(
            system=code_system,
            code=code,
            display=display
        )

        # Validate quantity
        if not isinstance(quantity, int) or quantity < 1:
            raise ValueError(_("Quantidade deve ser um inteiro positivo"))

        # Build prices
        unit_price = Money.brl(Decimal(str(unit_price_amount)))
        total_price = unit_price * quantity

        # Parse service date
        service_date = None
        if service_date_str:
            try:
                if isinstance(service_date_str, date):
                    service_date = service_date_str
                elif isinstance(service_date_str, str):
                    service_date = date.fromisoformat(service_date_str)
            except (ValueError, TypeError):
                self._logger.warning(
                    "Invalid service_date",
                    service_date=service_date_str
                )

        # Build modifier codes
        modifier_codes = []
        if modifiers:
            for mod in modifiers:
                if isinstance(mod, dict):
                    modifier_codes.append(CodedValue(**mod))
                elif isinstance(mod, str):
                    modifier_codes.append(CodedValue(system="http://www.ans.gov.br/tuss", code=mod))

        return ClaimItem(
            sequence=sequence,
            procedure_code=procedure_code,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            modifier_codes=modifier_codes,
            authorization_reference=authorization_ref,
            service_date=service_date,
        )
