"""WhatsApp Notification API client — Tasy Oracle integration.

Sends escalation notifications via an external REST API that inserts
into TASY.AUSTA_ENVIOS_WHATSAPP. Pattern mirrors the RPA authorization
project: MAEZO never writes directly to Oracle.

PRIVACY: Never log nr_telefone or ds_parametros (LGPD compliance).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from healthcare_platform.shared.domain.exceptions import ExternalServiceException
from healthcare_platform.shared.observability.logging import get_logger

SERVICE_NAME = "whatsapp_notification"


@dataclass(frozen=True)
class WhatsAppNotificationPayload:
    tenant_id: str
    cd_modelo: int
    nr_telefone: int
    nr_atendimento: str
    nr_seq_segurado: int
    payer_id: str = ""
    ds_parametros: str = ""


@dataclass(frozen=True)
class WhatsAppNotificationSettings:
    base_url: str
    api_key: str
    timeout_seconds: float = 10.0


class WhatsAppNotificationClient:
    """REST client for the external WhatsApp/Oracle notification service.

    The external service receives the payload and inserts a row into
    TASY.AUSTA_ENVIOS_WHATSAPP. This client is synchronous to match the
    sync BaseExternalTaskWorker.execute() contract.
    """

    def __init__(self, settings: WhatsAppNotificationSettings) -> None:
        self._settings = settings
        self._logger = get_logger(f"integration.{SERVICE_NAME}")

    def send_whatsapp_notification(self, payload: WhatsAppNotificationPayload) -> dict:
        """POST notification payload to the external API.

        Returns:
            dict with nr_sequencia (int) and status (str) from the API.

        Raises:
            ExternalServiceException: on HTTP error or timeout.
        """
        body = {
            "tenant_id": payload.tenant_id,
            "cd_modelo": payload.cd_modelo,
            "nr_telefone": payload.nr_telefone,
            "nr_atendimento": payload.nr_atendimento,
            "nr_seq_segurado": payload.nr_seq_segurado,
            "payer_id": payload.payer_id,
            "ds_parametros": payload.ds_parametros,
        }

        try:
            with httpx.Client(timeout=self._settings.timeout_seconds) as client:
                resp = client.post(
                    f"{self._settings.base_url}/api/v1/whatsapp/send",
                    json=body,
                    headers={"Authorization": f"Bearer {self._settings.api_key}"},
                )
                resp.raise_for_status()
                result = resp.json()

        except httpx.HTTPStatusError as exc:
            raise ExternalServiceException(
                f"{SERVICE_NAME} retornou {exc.response.status_code}",
                service_name=SERVICE_NAME,
                operation="send_whatsapp_notification",
                status_code=exc.response.status_code,
            ) from exc
        except httpx.TimeoutException as exc:
            raise ExternalServiceException(
                f"{SERVICE_NAME} tempo limite excedido",
                service_name=SERVICE_NAME,
                operation="send_whatsapp_notification",
            ) from exc

        self._logger.info(
            "WhatsApp notification queued",
            nr_sequencia=result.get("nr_sequencia"),
            status=result.get("status"),
            tenant_id=payload.tenant_id,
            cd_modelo=payload.cd_modelo,
        )
        return result
