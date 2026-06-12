"""TISS XML generation service - extracted from GenerateTISSXMLWorker.

Handles XML generation, guide number generation, and TISS formatting.
"""
from __future__ import annotations

import random
from datetime import datetime
from typing import Any, Dict, Optional

from healthcare_platform.shared.integrations.tiss_client import TISSClientProtocol


class TISSGenerationService:
    """Orchestrates TISS XML generation logic."""

    def __init__(self, tiss_client: Optional[TISSClientProtocol] = None) -> None:
        self.tiss_client = tiss_client

    def generate_guide_number(self, provider_id: str) -> str:
        """Generate a unique TISS guide number."""
        return f"{provider_id}-{datetime.now().strftime('%Y%m%d')}-{random.randint(10000000, 99999999)}"

    def generate_xml(
        self,
        claim_data: Dict[str, Any],
        guide_type: str,
        provider_id: str,
        variables: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate TISS XML from claim data.

        Returns dict with tiss_xml, guide_number, guide_type.
        """
        guide_number = claim_data.get("tiss_guide_number")
        if not guide_number:
            guide_number = self.generate_guide_number(provider_id)

        tiss_xml = self._build_xml(claim_data, guide_number, guide_type)
        return {
            "tiss_xml": tiss_xml,
            "guide_number": guide_number,
            "guide_type": guide_type,
        }

    def _build_xml(
        self,
        claim: Dict[str, Any],
        guide_num: str,
        guide_type: str,
    ) -> str:
        """Build TISS XML string from claim data."""
        return f'<?xml version="1.0"?><tiss><guide number="{guide_num}" type="{guide_type}"/></tiss>'
