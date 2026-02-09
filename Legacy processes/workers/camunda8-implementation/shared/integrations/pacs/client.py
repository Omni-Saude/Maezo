"""PACS (Picture Archiving and Communication System) HTTP client."""

from typing import List, Optional

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from revenue_cycle.config import Settings, get_settings
from revenue_cycle.integrations.pacs.models import PACSStudyDTO, PACSReportDTO

logger = structlog.get_logger(__name__)


class PACSClientError(Exception):
    """Base exception for PACS client errors."""

    pass


class PACSClient:
    """
    PACS integration client for medical imaging.

    Provides async methods to retrieve imaging studies and radiology reports
    for clinical documentation and glosa appeal evidence gathering.

    Example:
        client = PACSClient(settings)
        study = await client.get_study("1.2.840.113619.2.55.3...")
        studies = await client.search_studies_by_encounter("ENC-001")
        report = await client.get_report("1.2.840.113619.2.55.3...")
    """

    def __init__(self, settings: Optional[Settings] = None, tenant_id: Optional[str] = None):
        """
        Initialize PACS client.

        Args:
            settings: Application settings
            tenant_id: Tenant identifier for multi-tenant deployments
        """
        self._settings = settings or get_settings()
        self._tenant_id = tenant_id
        self._base_url = self._settings.integration.pacs_base_url
        self._timeout = httpx.Timeout(30.0, connect=5.0)

    def _get_headers(self) -> dict:
        """Get HTTP headers with authentication."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._tenant_id:
            headers["X-Tenant-ID"] = self._tenant_id
        return headers

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get_study(self, study_id: str) -> PACSStudyDTO:
        """
        Get imaging study details.

        Args:
            study_id: Study instance UID

        Returns:
            Study details

        Raises:
            PACSClientError: If study retrieval fails
            httpx.HTTPError: On HTTP errors
        """
        url = f"{self._base_url}/studies/{study_id}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                logger.info("Fetching imaging study", study_id=study_id, tenant_id=self._tenant_id)
                response = await client.get(url, headers=self._get_headers())
                response.raise_for_status()

                data = response.json()
                study = PACSStudyDTO.model_validate(data)

                logger.info(
                    "Imaging study retrieved",
                    study_id=study_id,
                    modality=study.modality,
                    patient_id=study.patient_id,
                )
                return study

        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error fetching imaging study",
                study_id=study_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise PACSClientError(f"Failed to fetch imaging study {study_id}: {e}") from e
        except httpx.HTTPError as e:
            logger.error("Network error fetching imaging study", study_id=study_id, error=str(e))
            raise PACSClientError(f"Network error fetching imaging study {study_id}: {e}") from e

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def search_studies_by_encounter(self, encounter_id: str) -> List[PACSStudyDTO]:
        """
        Search imaging studies by encounter for appeal evidence.

        This method retrieves all imaging studies associated with a specific
        encounter/hospitalization, useful for glosa appeals and clinical audits.

        Args:
            encounter_id: Encounter/hospitalization ID

        Returns:
            List of imaging studies for the encounter

        Raises:
            PACSClientError: If search fails
        """
        url = f"{self._base_url}/studies/search"
        params = {"encounterId": encounter_id}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                logger.info(
                    "Searching imaging studies by encounter",
                    encounter_id=encounter_id,
                    tenant_id=self._tenant_id,
                )
                response = await client.get(url, params=params, headers=self._get_headers())
                response.raise_for_status()

                data = response.json()
                studies = [PACSStudyDTO.model_validate(item) for item in data.get("studies", [])]

                logger.info(
                    "Encounter imaging studies retrieved",
                    encounter_id=encounter_id,
                    study_count=len(studies),
                )
                return studies

        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error searching imaging studies",
                encounter_id=encounter_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise PACSClientError(
                f"Failed to search imaging studies for encounter {encounter_id}: {e}"
            ) from e
        except httpx.HTTPError as e:
            logger.error(
                "Network error searching imaging studies", encounter_id=encounter_id, error=str(e)
            )
            raise PACSClientError(
                f"Network error searching imaging studies for encounter {encounter_id}: {e}"
            ) from e

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def get_report(self, study_id: str) -> PACSReportDTO:
        """
        Get radiology report for study.

        Args:
            study_id: Study instance UID

        Returns:
            Radiology report

        Raises:
            PACSClientError: If report retrieval fails
        """
        url = f"{self._base_url}/studies/{study_id}/report"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                logger.info(
                    "Fetching radiology report", study_id=study_id, tenant_id=self._tenant_id
                )
                response = await client.get(url, headers=self._get_headers())
                response.raise_for_status()

                data = response.json()
                report = PACSReportDTO.model_validate(data)

                logger.info(
                    "Radiology report retrieved",
                    study_id=study_id,
                    radiologist=report.radiologist,
                    status=report.report_status,
                )
                return report

        except httpx.HTTPStatusError as e:
            logger.error(
                "HTTP error fetching radiology report",
                study_id=study_id,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise PACSClientError(f"Failed to fetch radiology report for study {study_id}: {e}") from e
        except httpx.HTTPError as e:
            logger.error(
                "Network error fetching radiology report", study_id=study_id, error=str(e)
            )
            raise PACSClientError(
                f"Network error fetching radiology report for study {study_id}: {e}"
            ) from e
