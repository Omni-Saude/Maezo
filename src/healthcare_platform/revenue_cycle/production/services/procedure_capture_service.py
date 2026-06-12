"""Procedure capture service - extracted from CaptureProcedureWorker.

Handles ERP capture (Tasy/MvSoul) and procedure normalization.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from healthcare_platform.shared.integrations.tasy_client import TasyClientProtocol
from healthcare_platform.shared.integrations.mv_soul_client import MvSoulClientProtocol


class ProcedureCaptureService:
    """Orchestrates procedure capture from hospital ERP systems."""

    def __init__(
        self,
        tasy_client: Optional[TasyClientProtocol] = None,
        mv_soul_client: Optional[MvSoulClientProtocol] = None,
    ) -> None:
        self.tasy_client = tasy_client
        self.mv_soul_client = mv_soul_client

    def capture(self, erp_system: str, encounter_id: str) -> List[Dict[str, Any]]:
        """Capture procedures from specified ERP. Returns normalized procedure list."""
        captured: List[Dict[str, Any]] = []

        if erp_system == "tasy" and self.tasy_client:
            procedures = self.tasy_client.get_procedures(encounter_id)
            for proc in procedures:
                captured.append({
                    "procedure_id": proc.procedure_id,
                    "encounter_id": proc.encounter_id,
                    "patient_reference": f"Patient/{proc.patient_id}",
                    "code": proc.code,
                    "display": proc.display,
                    "status": proc.status,
                    "performed_date": (
                        proc.performed_date.isoformat() if proc.performed_date else None
                    ),
                })
        elif erp_system == "mv_soul" and self.mv_soul_client:
            items = self.mv_soul_client.get_billing_items(encounter_id)
            for item in items:
                captured.append({
                    "procedure_id": item.item_id,
                    "encounter_id": item.encounter_id,
                    "patient_reference": "",
                    "code": item.item_code,
                    "display": item.item_description,
                    "status": item.status,
                    "performed_date": item.service_date,
                })

        return captured
