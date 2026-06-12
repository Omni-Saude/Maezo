"""ERP export service - extracted from ExportToERPWorker.

Handles ERP synchronization to Tasy and MvSoul systems.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from healthcare_platform.revenue_cycle.collection.exceptions import ERPSyncError
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.tasy_api_client import TasyApiClient


class ERPExportService:
    """Orchestrates ERP export/sync operations."""

    def __init__(self, tasy_api_client: Optional[TasyApiClient] = None) -> None:
        self.tasy_api_client = tasy_api_client

    async def export(
        self,
        erp_system: str,
        entity_type: str,
        entity_data: Dict[str, Any],
        operation: str,
    ) -> Dict[str, Any]:
        """Export data to specified ERP system.

        Raises ERPSyncError if system unsupported or client missing.
        """
        if erp_system.lower() == "tasy":
            return await self._sync_to_tasy(entity_type, entity_data, operation)
        elif erp_system.lower() == "mv_soul":
            return await self._sync_to_mv_soul(entity_type, entity_data, operation)
        raise ERPSyncError(_(f"Sistema ERP nao suportado: {erp_system}"))

    async def _sync_to_tasy(
        self, entity_type: str, entity_data: Dict[str, Any], operation: str
    ) -> Dict[str, Any]:
        """Sync data to Tasy ERP."""
        if self.tasy_api_client is None:
            raise ERPSyncError(_("TasyApiClient nao configurado"))
        account_id = entity_data.get("account_id", entity_data.get("NR_CONTA", ""))
        if not account_id:
            raise ERPSyncError(_("account_id obrigatorio para Tasy"))
        billing_data = {
            "entity_type": entity_type,
            "operation": operation,
            "data": entity_data,
        }
        return await self.tasy_api_client.post_billing_sync(
            account_id=account_id, billing_data=billing_data
        )

    async def _sync_to_mv_soul(
        self, entity_type: str, entity_data: Dict[str, Any], operation: str
    ) -> Dict[str, Any]:
        """Sync data to MvSoul ERP."""
        if self.tasy_api_client is None:
            raise ERPSyncError(_("TasyApiClient nao configurado"))
        export_data = {
            "entity_type": entity_type,
            "operation": operation,
            "data": entity_data,
        }
        return await self.tasy_api_client.export_to_mvsoul(export_data)
