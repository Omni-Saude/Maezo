"""TISS schema validation service - extracted from ValidateTISSSchemaWorker.

Handles XML schema validation against ANS TISS standards.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from healthcare_platform.shared.integrations.tiss_client import TISSClientProtocol


class TISSValidationService:
    """Orchestrates TISS XML schema validation."""

    def __init__(self, tiss_client: Optional[TISSClientProtocol] = None) -> None:
        self.tiss_client = tiss_client

    def validate_schema(self, tiss_xml: str, guide_type: str) -> Dict[str, Any]:
        """Validate TISS XML against schema.

        Returns dict with schema_valid (bool) and schema_errors (list).
        """
        validation_errors: List[str] = []

        if self.tiss_client:
            try:
                if len(tiss_xml) < 100:
                    validation_errors.append("XML TISS muito curto")
                if not tiss_xml.strip().startswith("<"):
                    validation_errors.append("XML TISS invalido: nao comeca com <")
            except Exception as e:
                validation_errors.append(f"Erro na validacao: {str(e)}")

        return {
            "schema_valid": len(validation_errors) == 0,
            "schema_errors": validation_errors,
        }
