"""Procedure enrichment service - extracted from EnrichProcedureWorker.

Handles enrichment assembly: attaching diagnoses, performers, and encounter refs.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from healthcare_platform.shared.integrations.fhir_client import FHIRClientProtocol


class ProcedureEnrichmentService:
    """Orchestrates procedure enrichment with clinical context."""

    def __init__(self, fhir_client: Optional[FHIRClientProtocol] = None) -> None:
        self.fhir_client = fhir_client

    def enrich(
        self,
        procedures: List[Dict[str, Any]],
        diagnosis_codes: List[Any],
        performers: List[Any],
        encounter_ref: str,
    ) -> Dict[str, Any]:
        """Enrich procedures with clinical context. Returns enriched_procedures dict."""
        enriched: List[Dict[str, Any]] = []
        for proc in procedures:
            enriched_proc = {**proc}
            enriched_proc["diagnosis_codes"] = diagnosis_codes
            enriched_proc["performer_references"] = performers
            enriched_proc["encounter_reference"] = encounter_ref
            enriched_proc["body_site"] = None
            enriched.append(enriched_proc)
        return {"enriched_procedures": enriched}
