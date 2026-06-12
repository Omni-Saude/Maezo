"""PACS (Picture Archiving and Communication System) client for medical imaging.

This module provides integration with PACS systems for managing imaging orders,
studies, and reports. Implements Protocol ABC pattern with production and stub clients.
"""

from __future__ import annotations

from abc import abstractmethod
from datetime import datetime
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field

from healthcare_platform.shared.domain.exceptions import ExternalServiceException
from healthcare_platform.shared.i18n import _
from healthcare_platform.shared.integrations.base import BaseIntegrationClient
from healthcare_platform.shared.observability.logging import get_logger
from healthcare_platform.shared.observability.metrics import track_api_call

SERVICE_NAME = "pacs"


# DTOs
class ImagingStudyStatus(str, Enum):
    """Status of an imaging study."""

    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REPORTED = "reported"
    CANCELLED = "cancelled"
    ERROR = "error"


class ImagingOrderDTO(BaseModel):
    """Imaging order request data."""

    patient_id: str = Field(..., description="Patient identifier")
    order_id: str = Field(..., description="Clinical order identifier")
    modality: str = Field(..., description="Imaging modality (e.g., CT, MRI, X-RAY)")
    body_part: str = Field(..., description="Body part to be imaged")
    priority: str = Field(default="routine", description="Order priority")
    clinical_indication: str = Field(..., description="Clinical reason for imaging")
    requesting_physician: str = Field(..., description="Physician requesting the study")
    scheduled_datetime: datetime | None = Field(None, description="Scheduled time")


class ImagingStudyDTO(BaseModel):
    """Imaging study metadata."""

    study_id: str = Field(..., description="PACS study identifier")
    patient_id: str = Field(..., description="Patient identifier")
    order_id: str = Field(..., description="Clinical order identifier")
    modality: str = Field(..., description="Imaging modality")
    body_part: str = Field(..., description="Body part imaged")
    status: ImagingStudyStatus = Field(..., description="Current study status")
    study_datetime: datetime | None = Field(None, description="Study performed datetime")
    accession_number: str | None = Field(None, description="Accession number")
    series_count: int = Field(default=0, description="Number of series")
    instance_count: int = Field(default=0, description="Number of instances")
    report_available: bool = Field(default=False, description="Report availability")
    interpreting_physician: str | None = Field(None, description="Radiologist")


# Protocol
class PACSClientProtocol(Protocol):
    """Protocol for PACS client implementations."""

    @abstractmethod
    async def submit_order(self, order: ImagingOrderDTO) -> str:
        """Submit imaging order to PACS.

        Args:
            order: Imaging order details

        Returns:
            Study ID assigned by PACS

        Raises:
            ExternalServiceException: If submission fails
        """
        ...

    @abstractmethod
    async def get_study_status(self, study_id: str) -> ImagingStudyStatus:
        """Get current status of an imaging study.

        Args:
            study_id: PACS study identifier

        Returns:
            Current study status

        Raises:
            ExternalServiceException: If status check fails
        """
        ...

    @abstractmethod
    async def get_study_metadata(self, study_id: str) -> ImagingStudyDTO:
        """Get metadata for an imaging study.

        Args:
            study_id: PACS study identifier

        Returns:
            Study metadata

        Raises:
            ExternalServiceException: If metadata retrieval fails
        """
        ...

    @abstractmethod
    async def get_report_url(self, study_id: str) -> str:
        """Get URL to view the imaging report.

        Args:
            study_id: PACS study identifier

        Returns:
            URL to access the report

        Raises:
            ExternalServiceException: If report URL cannot be generated
        """
        ...


# Production implementation
class PACSClient(BaseIntegrationClient):
    """Production PACS client implementation."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: int = 30,
    ) -> None:
        """Initialize PACS client.

        Args:
            base_url: PACS API base URL
            api_key: API key for authentication
            timeout: Request timeout in seconds
        """
        super().__init__(
            service_name=SERVICE_NAME,
            base_url=base_url,
            timeout=timeout,
        )
        self._api_key = api_key
        self._logger = get_logger(__name__, service_name=SERVICE_NAME)

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with authentication."""
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        return headers

    @track_api_call(service_name=SERVICE_NAME, operation="submit_order")
    async def submit_order(self, order: ImagingOrderDTO) -> str:
        """Submit imaging order to PACS."""
        self._logger.info(
            "Submitting imaging order",
            extra={
                "order_id": order.order_id,
                "modality": order.modality,
                "body_part": order.body_part,
            },
        )

        try:
            response = await self._post(
                "/api/v1/orders",
                data=order.model_dump(mode="json"),
                headers=self._get_headers(),
            )

            study_id = response.get("study_id")
            if not study_id:
                raise ExternalServiceException(
                    service=SERVICE_NAME,
                    message=_("Resposta PACS sem study_id"),
                )

            self._logger.info(
                "Imaging order submitted successfully",
                extra={"order_id": order.order_id, "study_id": study_id},
            )
            return study_id

        except Exception as e:
            self._logger.error(
                "Failed to submit imaging order",
                extra={"order_id": order.order_id, "error": str(e)},
            )
            raise ExternalServiceException(
                service=SERVICE_NAME,
                message=_("Falha ao enviar pedido de imagem: {}").format(e),
            ) from e

    @track_api_call(service_name=SERVICE_NAME, operation="get_study_status")
    async def get_study_status(self, study_id: str) -> ImagingStudyStatus:
        """Get current status of an imaging study."""
        try:
            response = await self._get(
                f"/api/v1/studies/{study_id}/status",
                headers=self._get_headers(),
            )

            status_str = response.get("status")
            if not status_str:
                raise ExternalServiceException(
                    service=SERVICE_NAME,
                    message=_("Resposta PACS sem status"),
                )

            return ImagingStudyStatus(status_str)

        except Exception as e:
            self._logger.error(
                "Failed to get study status",
                extra={"study_id": study_id, "error": str(e)},
            )
            raise ExternalServiceException(
                service=SERVICE_NAME,
                message=_("Falha ao obter status do estudo: {}").format(e),
            ) from e

    @track_api_call(service_name=SERVICE_NAME, operation="get_study_metadata")
    async def get_study_metadata(self, study_id: str) -> ImagingStudyDTO:
        """Get metadata for an imaging study."""
        try:
            response = await self._get(
                f"/api/v1/studies/{study_id}",
                headers=self._get_headers(),
            )

            return ImagingStudyDTO(**response)

        except Exception as e:
            self._logger.error(
                "Failed to get study metadata",
                extra={"study_id": study_id, "error": str(e)},
            )
            raise ExternalServiceException(
                service=SERVICE_NAME,
                message=_("Falha ao obter metadados do estudo: {}").format(e),
            ) from e

    @track_api_call(service_name=SERVICE_NAME, operation="get_report_url")
    async def get_report_url(self, study_id: str) -> str:
        """Get URL to view the imaging report."""
        try:
            response = await self._get(
                f"/api/v1/studies/{study_id}/report-url",
                headers=self._get_headers(),
            )

            url = response.get("report_url")
            if not url:
                raise ExternalServiceException(
                    service=SERVICE_NAME,
                    message=_("Resposta PACS sem report_url"),
                )

            return url

        except Exception as e:
            self._logger.error(
                "Failed to get report URL",
                extra={"study_id": study_id, "error": str(e)},
            )
            raise ExternalServiceException(
                service=SERVICE_NAME,
                message=_("Falha ao obter URL do relatório: {}").format(e),
            ) from e


# Stub implementation for testing
class StubPACSClient:
    """Stub PACS client for testing."""

    def __init__(self) -> None:
        """Initialize stub client."""
        self._studies: dict[str, ImagingStudyDTO] = {}
        self._logger = get_logger(__name__, service_name=f"{SERVICE_NAME}_stub")

    async def submit_order(self, order: ImagingOrderDTO) -> str:
        """Submit imaging order (stub)."""
        study_id = f"STUDY-{order.order_id}"

        study = ImagingStudyDTO(
            study_id=study_id,
            patient_id=order.patient_id,
            order_id=order.order_id,
            modality=order.modality,
            body_part=order.body_part,
            status=ImagingStudyStatus.SCHEDULED,
            study_datetime=order.scheduled_datetime,
            accession_number=f"ACC-{order.order_id}",
        )
        self._studies[study_id] = study

        self._logger.info(
            "Stub: Imaging order submitted",
            extra={"order_id": order.order_id, "study_id": study_id},
        )
        return study_id

    async def get_study_status(self, study_id: str) -> ImagingStudyStatus:
        """Get study status (stub)."""
        if study_id not in self._studies:
            raise ExternalServiceException(
                service=SERVICE_NAME,
                message=_("Estudo não encontrado: {}").format(study_id),
            )
        return self._studies[study_id].status

    async def get_study_metadata(self, study_id: str) -> ImagingStudyDTO:
        """Get study metadata (stub)."""
        if study_id not in self._studies:
            raise ExternalServiceException(
                service=SERVICE_NAME,
                message=_("Estudo não encontrado: {}").format(study_id),
            )
        return self._studies[study_id]

    async def get_report_url(self, study_id: str) -> str:
        """Get report URL (stub)."""
        if study_id not in self._studies:
            raise ExternalServiceException(
                service=SERVICE_NAME,
                message=_("Estudo não encontrado: {}").format(study_id),
            )
        return f"https://pacs.example.com/reports/{study_id}"
