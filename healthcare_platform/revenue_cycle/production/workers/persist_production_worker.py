"""Persist production data to FHIR store.

CIB7 External Task Topic: production.persist_production
BPMN Error Codes: EXTERNAL_SERVICE_ERROR, BILLING_ERROR
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from healthcare_platform.shared.dmn.federation_service import FederatedDMNService
from healthcare_platform.shared.domain.exceptions import BillingException, ExternalServiceException
from healthcare_platform.shared.domain.value_objects import FHIRReference, Money
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol
from healthcare_platform.shared.multi_tenant.context import get_required_tenant
from healthcare_platform.shared.multi_tenant.decorators import require_tenant
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_task_execution


class PersistProductionWorker:
    """Persists validated production data to FHIR store.

    Creates/updates FHIR resources:
    - Claim (draft) with line items
    - ChargeItem for each procedure
    - Links to Encounter, Patient, Coverage

    All data is LGPD compliant (no PII in stored variables).

    Archetype: FINANCIAL_CALCULATION
    """

    TOPIC = "production.persist_production"

    def __init__(self, fhir_client: FHIRClientProtocol) -> None:
        self._fhir = fhir_client
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
    @track_task_execution(metric_name="production_persist_production")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """Persist production data to FHIR store.

        Task Variables (input):
            compatible_procedures: list[dict] - Validated, priced procedures
            encounter_reference: str - FHIR Encounter reference
            patient_reference: str - FHIR Patient reference
            coverage_reference: str | None - FHIR Coverage reference
            auth_number: str | None - Authorization number
            total_amount: str - Total amount as decimal string
            diagnosis_codes: list[str] - CID-10 codes

        Returns:
            claim_reference: str - FHIR Claim reference
            charge_item_references: list[str] - Created ChargeItem references
            production_id: str - Unique production batch ID
            persisted_at: str - ISO timestamp
        """
        ctx = get_required_tenant()
        procedures: list[dict[str, Any]] = task_variables.get("compatible_procedures", [])
        encounter_ref: str = task_variables.get("encounter_reference", "")
        patient_ref: str = task_variables.get("patient_reference", "")
        coverage_ref: str | None = task_variables.get("coverage_reference")
        auth_number: str | None = task_variables.get("auth_number")
        total_amount_str: str = task_variables.get("total_amount", "0.00")
        diagnosis_codes: list[str] = task_variables.get("diagnosis_codes", [])

        production_id = str(uuid4())

        self._logger.info(
            "persisting_production",
            production_id=production_id,
            procedure_count=len(procedures),
            total_amount=total_amount_str,
            tenant_id=ctx.tenant_id,
        )

        if not procedures:
            raise BillingException(
                _("Failed to persist production data: {reason}").format(
                    reason="no procedures to persist"
                ),
                bpmn_error_code="BILLING_ERROR",
            )

        # Build FHIR Claim resource
        claim_items: list[dict[str, Any]] = []
        for seq, proc in enumerate(procedures, start=1):
            code = proc.get("code", "")
            display = proc.get("display", "")
            quantity = proc.get("quantity", 1)
            unit_price = proc.get("unit_price", "0.00")
            total_price = proc.get("total_price", "0.00")

            claim_items.append({
                "sequence": seq,
                "productOrService": {
                    "coding": [{
                        "system": "http://www.ans.gov.br/tuss",
                        "code": code,
                        "display": display,
                    }]
                },
                "quantity": {"value": quantity},
                "unitPrice": {
                    "value": float(unit_price),
                    "currency": "BRL",
                },
                "net": {
                    "value": float(total_price),
                    "currency": "BRL",
                },
            })

        claim_resource: dict[str, Any] = {
            "resourceType": "Claim",
            "status": "draft",
            "type": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                    "code": "institutional",
                }]
            },
            "use": "claim",
            "patient": {"reference": patient_ref},
            "created": datetime.utcnow().isoformat(),
            "provider": {"reference": f"Organization/{ctx.tenant_id}"},
            "priority": {"coding": [{"code": "normal"}]},
            "diagnosis": [
                {
                    "sequence": i + 1,
                    "diagnosisCodeableConcept": {
                        "coding": [{
                            "system": "http://hl7.org/fhir/sid/icd-10",
                            "code": dx,
                        }]
                    },
                }
                for i, dx in enumerate(diagnosis_codes)
            ],
            "item": claim_items,
            "total": {
                "value": float(total_amount_str),
                "currency": "BRL",
            },
        }

        if encounter_ref:
            claim_resource["encounter"] = {"reference": encounter_ref}
        if coverage_ref:
            claim_resource["insurance"] = [
                {"sequence": 1, "focal": True, "coverage": {"reference": coverage_ref}}
            ]
        if auth_number:
            claim_resource["insurance"] = claim_resource.get("insurance", [
                {"sequence": 1, "focal": True, "coverage": {"reference": coverage_ref or ""}}
            ])
            claim_resource["insurance"][0]["preAuthRef"] = [auth_number]

        # Add production batch metadata
        claim_resource["extension"] = [{
            "url": "http://cib7.com/fhir/StructureDefinition/production-batch-id",
            "valueString": production_id,
        }]

        # Persist to FHIR
        try:
            created_claim = await self._fhir.create("Claim", claim_resource)
            claim_id = created_claim.get("id", "")
            claim_reference = f"Claim/{claim_id}"
        except Exception as exc:
            self._logger.error(
                "claim_persist_failed",
                production_id=production_id,
                error=str(exc),
                tenant_id=ctx.tenant_id,
            )
            raise ExternalServiceException(
                _("FHIR store unavailable"),
                service_name="fhir",
                operation="create_claim",
            ) from exc

        # Create ChargeItem for each procedure
        charge_item_refs: list[str] = []
        for proc in procedures:
            charge_item: dict[str, Any] = {
                "resourceType": "ChargeItem",
                "status": "billable",
                "code": {
                    "coding": [{
                        "system": "http://www.ans.gov.br/tuss",
                        "code": proc.get("code", ""),
                        "display": proc.get("display", ""),
                    }]
                },
                "subject": {"reference": patient_ref},
                "context": {"reference": encounter_ref},
                "quantity": {"value": proc.get("quantity", 1)},
                "factorOverride": float(proc.get("unit_price", "0.00")),
            }

            try:
                created = await self._fhir.create("ChargeItem", charge_item)
                charge_item_refs.append(f"ChargeItem/{created.get('id', '')}")
            except Exception as exc:
                self._logger.warning(
                    "charge_item_persist_failed",
                    code=proc.get("code"),
                    error=str(exc),
                    tenant_id=ctx.tenant_id,
                )

        persisted_at = datetime.utcnow().isoformat()

        self._logger.info(
            "production_persisted",
            production_id=production_id,
            claim_reference=claim_reference,
            charge_items_count=len(charge_item_refs),
            total_amount=total_amount_str,
            tenant_id=ctx.tenant_id,
        )

        return {
            "claim_reference": claim_reference,
            "charge_item_references": charge_item_refs,
            "production_id": production_id,
            "persisted_at": persisted_at,
        }
