"""Generate TISS XML from claim data.

Archetype: INTEGRATION_BRIDGE
"""
from __future__ import annotations

from datetime import datetime

from healthcare_platform.revenue_cycle.billing.workers.base import BaseWorker, WorkerResult, worker
from healthcare_platform.shared.domain.enums import TISSGuideType
from healthcare_platform.shared.domain.exceptions import TISSException, TISSSchemaError
from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tiss_client import TISSClientProtocol, TISSGuideDTO


@worker(topic="billing-generate-tiss-xml", max_jobs=3, lock_duration=300000)
class GenerateTISSXMLWorker(BaseWorker):
    """
    Generate TISS 4.01 compliant XML from claim data.

    Input variables:
        - claim (dict): Claim data
        - payer_id (str): Insurance payer ID
        - provider_id (str): Provider organization ID
        - patient_id (str): Patient ID
        - guide_type (str): TISS guide type enum value
        - items (list[dict]): Line items

    Output variables:
        - tiss_xml (str): Generated TISS XML string
        - guide_number (str): TISS guide number
        - guide_type (str): TISS guide type
    """

    def __init__(self, tiss_client: TISSClientProtocol) -> None:
        """
        Initialize worker with TISS client.

        Args:
            tiss_client: TISS client implementation for XML generation
        """
        super().__init__()
        self._tiss_client = tiss_client
        self.dmn_service = FederatedDMNService()

    @property
    def operation_name(self) -> str:
        return _("Gerar XML TISS")

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
        """Process TISS XML generation task."""
        try:
            # Extract variables
            claim_data = variables.get("claim", {})
            payer_id = variables.get("payer_id", "")
            provider_id = variables.get("provider_id", "")
            patient_id = variables.get("patient_id", "")
            guide_type_str = variables.get("guide_type", "")
            items = variables.get("items", [])

            # Validate required fields
            if not claim_data:
                raise TISSException(_("Dados da conta são obrigatórios"))
            if not payer_id:
                raise TISSException(_("ID da operadora é obrigatório"))
            if not provider_id:
                raise TISSException(_("ID do prestador é obrigatório"))
            if not patient_id:
                raise TISSException(_("ID do paciente é obrigatório"))
            if not guide_type_str:
                raise TISSException(_("Tipo de guia é obrigatório"))

            # Parse guide type
            try:
                guide_type = TISSGuideType(guide_type_str)
            except ValueError:
                raise TISSException(
                    _("Tipo de guia TISS inválido: {type}").format(type=guide_type_str)
                )

            # Build TISSGuideDTO
            guide_dto = self._build_tiss_guide_dto(
                claim_data=claim_data,
                payer_id=payer_id,
                provider_id=provider_id,
                patient_id=patient_id,
                guide_type=guide_type,
                items=items,
            )

            # Generate XML
            self._logger.info(
                "Generating TISS XML",
                guide_number=guide_dto.guide_number,
                guide_type=guide_type.value,
                payer_id=payer_id
            )

            tiss_xml = await self._tiss_client.generate_guide_xml(guide_dto)

            if not tiss_xml:
                raise TISSSchemaError(_("XML gerado está vazio"))

            self._logger.info(
                "TISS XML generated",
                guide_number=guide_dto.guide_number,
                xml_length=len(tiss_xml)
            )

            return WorkerResult.ok({
                "tiss_xml": tiss_xml,
                "guide_number": guide_dto.guide_number,
                "guide_type": guide_type.value,
            })

        except (TISSException, TISSSchemaError) as e:
            self._logger.error("TISS XML generation failed", error=str(e))
            return WorkerResult.bpmn_error(
                error_code=e.bpmn_error_code,
                error_message=str(e)
            )
        except Exception as e:
            self._logger.error("Unexpected error in XML generation", error=str(e), exc_info=True)
            return WorkerResult.failure(
                error_message=_("Erro ao gerar XML TISS: {error}").format(error=str(e)),
                retry=True
            )

    def _build_tiss_guide_dto(
        self,
        claim_data: dict,
        payer_id: str,
        provider_id: str,
        patient_id: str,
        guide_type: TISSGuideType,
        items: list[dict],
    ) -> TISSGuideDTO:
        """Build TISSGuideDTO from claim data."""
        # Generate or extract guide number
        guide_number = claim_data.get("tiss_guide_number", "")
        if not guide_number:
            # Generate guide number: format PROVIDER-YYYYMMDD-SEQUENCE
            now = datetime.utcnow()
            sequence = claim_data.get("id", "")[:8] if "id" in claim_data else "00000000"
            guide_number = f"{provider_id}-{now.strftime('%Y%m%d')}-{sequence}"

        # Extract clinical data
        diagnosis_codes = []
        if "diagnosis_codes" in claim_data:
            diag_codes = claim_data["diagnosis_codes"]
            if isinstance(diag_codes, list):
                for diag in diag_codes:
                    if isinstance(diag, dict):
                        diagnosis_codes.append(diag.get("code", ""))
                    else:
                        diagnosis_codes.append(str(diag))

        procedure_codes = []
        for item in items:
            if isinstance(item, dict) and "procedure_code" in item:
                proc = item["procedure_code"]
                if isinstance(proc, dict):
                    procedure_codes.append(proc.get("code", ""))
                else:
                    procedure_codes.append(str(proc))

        # Extract dates
        admission_date = None
        discharge_date = None
        requested_date = None

        if "admission_date" in claim_data:
            admission_date = self._parse_datetime(claim_data["admission_date"])
        if "discharge_date" in claim_data:
            discharge_date = self._parse_datetime(claim_data["discharge_date"])
        if "requested_date" in claim_data:
            requested_date = self._parse_datetime(claim_data["requested_date"])

        # Extract financial data
        total_amount = 0.0
        if "total" in claim_data:
            total = claim_data["total"]
            if isinstance(total, dict):
                total_amount = float(total.get("amount", 0))
            else:
                total_amount = float(total)

        authorized_amount = None
        if "authorized_amount" in claim_data:
            authorized_amount = float(claim_data["authorized_amount"])

        # Extract authorization
        authorization_number = claim_data.get("authorization_number")

        # Extract physician
        attending_physician_id = None
        if "attending_physician_id" in claim_data:
            attending_physician_id = claim_data["attending_physician_id"]
        elif "practitioner_references" in claim_data:
            refs = claim_data["practitioner_references"]
            if refs and len(refs) > 0:
                ref = refs[0]
                if isinstance(ref, dict):
                    attending_physician_id = ref.get("reference", "").split("/")[-1]

        # Build items for DTO
        dto_items = []
        for item in items:
            if isinstance(item, dict):
                dto_item = {
                    "code": "",
                    "description": "",
                    "quantity": item.get("quantity", 1),
                    "unit_price": 0.0,
                }

                if "procedure_code" in item:
                    proc = item["procedure_code"]
                    if isinstance(proc, dict):
                        dto_item["code"] = proc.get("code", "")
                        dto_item["description"] = proc.get("display", "")
                    else:
                        dto_item["code"] = str(proc)

                if "unit_price" in item:
                    unit_price = item["unit_price"]
                    if isinstance(unit_price, dict):
                        dto_item["unit_price"] = float(unit_price.get("amount", 0))
                    else:
                        dto_item["unit_price"] = float(unit_price)

                dto_items.append(dto_item)

        return TISSGuideDTO(
            guide_type=guide_type,
            guide_number=guide_number,
            payer_id=payer_id,
            provider_id=provider_id,
            patient_id=patient_id,
            admission_date=admission_date,
            discharge_date=discharge_date,
            diagnosis_codes=diagnosis_codes,
            procedure_codes=procedure_codes,
            total_amount=total_amount,
            authorized_amount=authorized_amount,
            authorization_number=authorization_number,
            attending_physician_id=attending_physician_id,
            requested_date=requested_date,
            items=dto_items,
        )

    def _parse_datetime(self, value) -> datetime | None:
        """Parse datetime from various formats."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                return None
        return None
