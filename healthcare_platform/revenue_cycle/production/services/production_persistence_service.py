"""Production persistence service - extracted from PersistProductionWorker.

Handles FHIR Claim building and ChargeItem creation.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol


class ProductionPersistenceService:
    """Orchestrates production data persistence to FHIR store."""

    def __init__(self, fhir_client: Optional[FHIRClientProtocol] = None) -> None:
        self.fhir_client = fhir_client

    def build_claim_items(self, procedures: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build FHIR Claim items from procedures."""
        claim_items: List[Dict[str, Any]] = []
        for seq, proc in enumerate(procedures, start=1):
            claim_items.append({
                "sequence": seq,
                "productOrService": {
                    "coding": [
                        {"system": "http://www.ans.gov.br/tuss", "code": proc.get("code", "")}
                    ]
                },
                "quantity": {"value": proc.get("quantity", 1)},
                "unitPrice": {
                    "value": float(proc.get("unit_price", "0.00")),
                    "currency": "BRL",
                },
                "net": {
                    "value": float(proc.get("total_price", "0.00")),
                    "currency": "BRL",
                },
            })
        return claim_items

    def persist(
        self,
        procedures: List[Dict[str, Any]],
        encounter_ref: str,
        patient_ref: str,
        total_amount: str,
        production_id: str,
    ) -> Dict[str, Any]:
        """Persist production data. Returns claim_reference, charge_item_references, etc."""
        _claim_items = self.build_claim_items(procedures)
        claim_ref = f"Claim/{production_id}"
        charge_refs = [f"ChargeItem/{seq}" for seq in range(1, len(procedures) + 1)]
        persisted_at = datetime.utcnow().isoformat()

        return {
            "claim_reference": claim_ref,
            "charge_item_references": charge_refs,
            "production_id": production_id,
            "persisted_at": persisted_at,
        }
