from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from platform.revenue_cycle.collection.exceptions import ERPSyncError
from platform.shared.i18n import _
from platform.shared.integrations.tasy_client import TasyClient
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_task_execution

logger = get_logger(__name__)


class ExportToERPWorker:
    """Sincroniza dados de reconciliação para ERP (Tasy/MV Soul) usando padrão CDC."""

    WORKER_TYPE = "export_to_erp"

    def __init__(self):
        self.tasy_client = TasyClient()

    @track_task_execution(metric_name="export_to_erp")
    async def execute(self, task_variables: dict[str, Any]) -> dict[str, Any]:
        """
        Exporta dados de reconciliação para ERP usando Change Data Capture (CDC).

        Args:
            task_variables: {
                "reconciliation_id": str,
                "erp_system": str (tasy or mv_soul),
                "entity_type": str (payment, reconciliation, etc),
                "entity_data": dict,
                "operation": str (insert, update, delete)
            }

        Returns:
            {
                "export_id": str,
                "reconciliation_id": str,
                "erp_system": str,
                "operation": str,
                "success": bool,
                "erp_response": dict,
                "exported_at": str
            }

        Raises:
            ERPSyncError: When sync fails (retryable)
        """
        reconciliation_id = task_variables["reconciliation_id"]
        erp_system = task_variables["erp_system"]
        entity_type = task_variables["entity_type"]
        entity_data = task_variables["entity_data"]
        operation = task_variables["operation"]

        export_id = str(uuid4())

        logger.info(
            _("Iniciando exportação para ERP"),
            extra={
                "export_id": export_id,
                "reconciliation_id": reconciliation_id,
                "erp_system": erp_system,
                "entity_type": entity_type,
                "operation": operation,
            },
        )

        try:
            if erp_system.lower() == "tasy":
                # Sync to Tasy
                erp_response = await self._sync_to_tasy(entity_type, entity_data, operation)
            elif erp_system.lower() == "mv_soul":
                # Sync to MV Soul
                erp_response = await self._sync_to_mv_soul(entity_type, entity_data, operation)
            else:
                raise ERPSyncError(_(f"Sistema ERP não suportado: {erp_system}"))

            logger.info(
                _("Exportação para ERP concluída com sucesso"),
                extra={
                    "export_id": export_id,
                    "erp_system": erp_system,
                    "erp_transaction_id": erp_response.get("transaction_id"),
                },
            )

            return {
                "export_id": export_id,
                "reconciliation_id": reconciliation_id,
                "erp_system": erp_system,
                "entity_type": entity_type,
                "operation": operation,
                "success": True,
                "erp_response": erp_response,
                "exported_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(
                _("Falha na exportação para ERP"),
                extra={
                    "export_id": export_id,
                    "erp_system": erp_system,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise ERPSyncError(_(f"Falha ao sincronizar com {erp_system}: {str(e)}")) from e

    async def _sync_to_tasy(
        self, entity_type: str, entity_data: dict, operation: str
    ) -> dict[str, Any]:
        """Sync to Tasy ERP."""
        # In real implementation, use TasyClient to POST to CDC endpoint
        # For now, mock the response
        logger.debug(_("Sincronizando com Tasy"), extra={"entity_type": entity_type})

        # Simulate API call
        response = {
            "transaction_id": f"TASY-{uuid4()}",
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return response

    async def _sync_to_mv_soul(
        self, entity_type: str, entity_data: dict, operation: str
    ) -> dict[str, Any]:
        """Sync to MV Soul ERP."""
        # In real implementation, use MVSoulClient
        logger.debug(_("Sincronizando com MV Soul"), extra={"entity_type": entity_type})

        response = {
            "transaction_id": f"MVSOUL-{uuid4()}",
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return response
