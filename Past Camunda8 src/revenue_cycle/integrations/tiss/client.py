"""TISS/ANS integration HTTP client with ICP-Brasil certificate support."""

from __future__ import annotations

import asyncio
import ssl
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, List, Optional

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from revenue_cycle.config import Settings
from revenue_cycle.integrations.tiss.models import (
    TissAppealRequest,
    TissAppealResponse,
    TissBatchSummary,
    TissClaimDTO,
    TissGlosaDTO,
    TissStatusResponse,
    TissSubmissionResponse,
)
from revenue_cycle.multi_tenant.credentials import TenantCredentialManager, TissCertificate

logger = structlog.get_logger(__name__)


class TissIntegrationError(Exception):
    """Base exception for TISS integration errors."""

    pass


class TissCertificateError(TissIntegrationError):
    """Certificate validation or loading error."""

    pass


class TissSubmissionError(TissIntegrationError):
    """Claim submission error."""

    pass


class TissTimeoutError(TissIntegrationError):
    """Request timeout."""

    pass


class TissClient:
    """
    TISS submission client for ANS claims with ICP-Brasil certificate support.

    Features:
    - ICP-Brasil digital certificate authentication
    - XML claim submission to insurance portals
    - Glosa tracking and appeal submission
    - Automatic retry with exponential backoff
    - Certificate expiration monitoring
    - Multi-tenant credential management

    Example:
        async with TissClient(credential_manager, "tenant-123") as client:
            # Submit claim
            response = await client.submit_claim(claim_xml)

            # Check status
            status = await client.check_claim_status(response.protocol_number)

            # Get glosas
            glosas = await client.get_glosas(batch_id)

            # Submit appeal
            appeal = await client.submit_appeal(appeal_xml)
    """

    def __init__(
        self,
        credential_manager: TenantCredentialManager,
        tenant_id: str,
        settings: Optional[Settings] = None,
    ):
        """
        Initialize TISS client.

        Args:
            credential_manager: Credential manager instance
            tenant_id: Tenant identifier
            settings: Application settings (optional)
        """
        self._credential_manager = credential_manager
        self._tenant_id = tenant_id
        self._settings = settings or Settings()

        self._certificate: Optional[TissCertificate] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._cert_file_path: Optional[Path] = None
        self._key_file_path: Optional[Path] = None

    async def initialize(self) -> None:
        """Initialize client and load certificate."""
        # Get tenant certificate
        self._certificate = await self._credential_manager.get_tiss_certificate(self._tenant_id)

        # Validate certificate not expired
        if self._certificate.is_expired:
            raise TissCertificateError(
                f"TISS certificate expired on {self._certificate.valid_until}"
            )

        # Warn if expiring soon
        if self._certificate.days_until_expiration < 30:
            logger.warning(
                "TISS certificate expiring soon",
                tenant_id=self._tenant_id,
                days_remaining=self._certificate.days_until_expiration,
            )

        # Write certificate and key to temporary files
        # (httpx requires file paths for client certificates)
        await self._write_certificate_files()

        # Create SSL context with ICP-Brasil certificate
        ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ssl_context.load_cert_chain(
            certfile=str(self._cert_file_path),
            keyfile=str(self._key_file_path),
            password=self._certificate.passphrase.get_secret_value()
            if self._certificate.passphrase
            else None,
        )

        # Create HTTP client with certificate
        self._client = httpx.AsyncClient(
            base_url=self._settings.integration.tiss_base_url,
            timeout=httpx.Timeout(self._settings.integration.tiss_timeout),
            verify=ssl_context,
            cert=(str(self._cert_file_path), str(self._key_file_path)),
            headers={
                "Content-Type": "application/xml",
                "Accept": "application/xml",
            },
        )

        logger.info(
            "TISS client initialized",
            tenant_id=self._tenant_id,
            base_url=self._settings.integration.tiss_base_url,
            certificate_issuer=self._certificate.issuer,
            certificate_expires=self._certificate.valid_until.isoformat(),
        )

    async def _write_certificate_files(self) -> None:
        """Write certificate and key to temporary files."""
        try:
            # Create temporary directory for certificates
            temp_dir = Path(tempfile.mkdtemp(prefix=f"tiss_{self._tenant_id}_"))

            # Write certificate
            cert_path = temp_dir / "certificate.pem"
            cert_path.write_text(self._certificate.certificate_pem.get_secret_value())
            self._cert_file_path = cert_path

            # Write private key
            key_path = temp_dir / "private_key.pem"
            key_path.write_text(self._certificate.private_key_pem.get_secret_value())
            self._key_file_path = key_path

            # Set secure permissions (readable only by owner)
            cert_path.chmod(0o600)
            key_path.chmod(0o600)

            logger.debug(
                "Certificate files written",
                tenant_id=self._tenant_id,
                cert_path=str(cert_path),
            )

        except Exception as e:
            logger.error(
                "Failed to write certificate files",
                tenant_id=self._tenant_id,
                error=str(e),
            )
            raise TissCertificateError(f"Failed to write certificate files: {e}")

    def _cleanup_certificate_files(self) -> None:
        """Clean up temporary certificate files."""
        try:
            if self._cert_file_path and self._cert_file_path.exists():
                self._cert_file_path.unlink()
            if self._key_file_path and self._key_file_path.exists():
                self._key_file_path.unlink()

            # Remove temporary directory if empty
            if self._cert_file_path:
                temp_dir = self._cert_file_path.parent
                if temp_dir.exists() and not list(temp_dir.iterdir()):
                    temp_dir.rmdir()

            logger.debug("Certificate files cleaned up", tenant_id=self._tenant_id)

        except Exception as e:
            logger.warning(
                "Failed to cleanup certificate files",
                tenant_id=self._tenant_id,
                error=str(e),
            )

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> httpx.Response:
        """
        Make authenticated HTTP request with retry.

        Args:
            method: HTTP method
            path: Request path
            **kwargs: Additional httpx request parameters

        Returns:
            HTTP response

        Raises:
            TissIntegrationError: On request failure
        """
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response

        except httpx.TimeoutException as e:
            logger.error("TISS request timeout", tenant_id=self._tenant_id, path=path)
            raise TissTimeoutError(f"Request timeout: {path}")
        except httpx.HTTPStatusError as e:
            logger.error(
                "TISS HTTP error",
                tenant_id=self._tenant_id,
                path=path,
                status_code=e.response.status_code,
                error=str(e),
            )
            raise TissIntegrationError(f"HTTP error {e.response.status_code}: {e}")
        except Exception as e:
            logger.error("TISS request error", tenant_id=self._tenant_id, path=path, error=str(e))
            raise TissIntegrationError(f"Request error: {e}")

    async def submit_claim(self, claim_xml: str) -> TissSubmissionResponse:
        """
        Submit TISS claim to insurance portal.

        Args:
            claim_xml: XML-formatted TISS claim (TISS 3.x standard)

        Returns:
            Submission response with protocol number

        Raises:
            TissSubmissionError: If submission fails
            TissIntegrationError: On request failure
        """
        try:
            response = await self._request(
                "POST",
                "/tiss/claims/submit",
                content=claim_xml.encode("utf-8"),
                headers={"Content-Type": "application/xml"},
            )

            # Parse XML response (simplified for example)
            # In production, use proper XML parsing (lxml, xmltodict)
            data = response.json()  # Assuming portal also supports JSON

            submission = TissSubmissionResponse(
                protocol_number=data["protocolNumber"],
                batch_id=data["batchId"],
                submission_date=datetime.fromisoformat(data["submissionDate"]),
                status=data["status"],
                estimated_processing_days=data.get("estimatedProcessingDays", 15),
                message=data.get("message"),
            )

            logger.info(
                "TISS claim submitted",
                tenant_id=self._tenant_id,
                protocol_number=submission.protocol_number,
                batch_id=submission.batch_id,
            )

            return submission

        except Exception as e:
            logger.error("TISS claim submission failed", tenant_id=self._tenant_id, error=str(e))
            raise TissSubmissionError(f"Claim submission failed: {e}")

    async def check_claim_status(self, protocol_number: str) -> TissStatusResponse:
        """
        Check claim status by protocol number.

        Args:
            protocol_number: ANS protocol number

        Returns:
            Current claim status

        Raises:
            TissIntegrationError: On request failure
        """
        response = await self._request(
            "GET",
            f"/tiss/claims/status/{protocol_number}",
        )

        data = response.json()

        status = TissStatusResponse(
            protocol_number=protocol_number,
            status=data["status"],
            last_updated=datetime.fromisoformat(data["lastUpdated"]),
            glosa_count=data.get("glosaCount", 0),
            approved_amount=data.get("approvedAmount", 0),
            paid_amount=data.get("paidAmount", 0),
            glosa_amount=data.get("glosaAmount", 0),
            payment_date=datetime.fromisoformat(data["paymentDate"])
            if data.get("paymentDate")
            else None,
            observations=data.get("observations", []),
        )

        logger.info(
            "TISS claim status checked",
            tenant_id=self._tenant_id,
            protocol_number=protocol_number,
            status=status.status,
        )

        return status

    async def get_glosas(self, batch_id: str) -> List[TissGlosaDTO]:
        """
        Get glosas (denials) for a batch.

        Args:
            batch_id: Batch identifier

        Returns:
            List of glosas

        Raises:
            TissIntegrationError: On request failure
        """
        response = await self._request(
            "GET",
            f"/tiss/batches/{batch_id}/glosas",
        )

        data = response.json()
        glosas = [
            TissGlosaDTO(
                glosa_id=item["glosaId"],
                protocol_number=item["protocolNumber"],
                glosa_type=item["glosaType"],
                procedure_code=item["procedureCode"],
                procedure_description=item["procedureDescription"],
                denied_amount=item["deniedAmount"],
                reason_code=item["reasonCode"],
                reason_description=item["reasonDescription"],
                justification=item.get("justification"),
                date_notified=datetime.fromisoformat(item["dateNotified"]),
                appeal_deadline=datetime.fromisoformat(item["appealDeadline"]),
                is_appealable=item.get("isAppealable", True),
            )
            for item in data.get("glosas", [])
        ]

        logger.info(
            "TISS glosas retrieved",
            tenant_id=self._tenant_id,
            batch_id=batch_id,
            count=len(glosas),
        )

        return glosas

    async def submit_appeal(self, appeal_request: TissAppealRequest) -> TissAppealResponse:
        """
        Submit glosa appeal with medical justification.

        Args:
            appeal_request: Appeal request data

        Returns:
            Appeal submission response

        Raises:
            TissIntegrationError: On request failure
        """
        # Convert appeal to XML (simplified)
        # In production, use proper XML generation (lxml, jinja2)
        appeal_xml = self._generate_appeal_xml(appeal_request)

        response = await self._request(
            "POST",
            "/tiss/appeals/submit",
            content=appeal_xml.encode("utf-8"),
            headers={"Content-Type": "application/xml"},
        )

        data = response.json()

        appeal_response = TissAppealResponse(
            appeal_protocol=data["appealProtocol"],
            original_protocol=appeal_request.protocol_number,
            glosa_id=appeal_request.glosa_id,
            submission_date=datetime.fromisoformat(data["submissionDate"]),
            status=data["status"],
            estimated_response_days=data.get("estimatedResponseDays", 30),
            message=data.get("message"),
        )

        logger.info(
            "TISS appeal submitted",
            tenant_id=self._tenant_id,
            appeal_protocol=appeal_response.appeal_protocol,
            glosa_id=appeal_request.glosa_id,
        )

        return appeal_response

    def _generate_appeal_xml(self, appeal_request: TissAppealRequest) -> str:
        """
        Generate TISS appeal XML.

        Args:
            appeal_request: Appeal data

        Returns:
            XML string

        Note:
            This is a simplified example. In production, use proper
            TISS XML schema generation with lxml or similar.
        """
        # Simplified XML generation
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<tissAppeal>
    <glosaId>{appeal_request.glosa_id}</glosaId>
    <protocolNumber>{appeal_request.protocol_number}</protocolNumber>
    <appealReason>{appeal_request.appeal_reason}</appealReason>
    <clinicalJustification>{appeal_request.clinical_justification}</clinicalJustification>
    <medicalRecordSummary>{appeal_request.medical_record_summary}</medicalRecordSummary>
    <requestedAmount>{appeal_request.requested_amount}</requestedAmount>
    <supportingDocuments>
        {''.join(f'<document>{doc}</document>' for doc in appeal_request.supporting_documents)}
    </supportingDocuments>
</tissAppeal>"""
        return xml

    async def get_batch_summary(self, batch_id: str) -> TissBatchSummary:
        """
        Get summary of a batch submission.

        Args:
            batch_id: Batch identifier

        Returns:
            Batch summary

        Raises:
            TissIntegrationError: On request failure
        """
        response = await self._request(
            "GET",
            f"/tiss/batches/{batch_id}/summary",
        )

        data = response.json()

        summary = TissBatchSummary(
            batch_id=batch_id,
            submission_date=datetime.fromisoformat(data["submissionDate"]),
            total_claims=data["totalClaims"],
            total_amount=data["totalAmount"],
            status=data["status"],
            accepted_claims=data.get("acceptedClaims", 0),
            rejected_claims=data.get("rejectedClaims", 0),
            claims_with_glosa=data.get("claimsWithGlosa", 0),
            approved_amount=data.get("approvedAmount", 0),
            glosa_amount=data.get("glosaAmount", 0),
            paid_amount=data.get("paidAmount", 0),
        )

        logger.info(
            "TISS batch summary retrieved",
            tenant_id=self._tenant_id,
            batch_id=batch_id,
            total_claims=summary.total_claims,
        )

        return summary

    async def close(self) -> None:
        """Close HTTP client and cleanup certificate files."""
        if self._client:
            await self._client.aclose()
            self._client = None

        # Clean up temporary certificate files
        self._cleanup_certificate_files()

        logger.info("TISS client closed", tenant_id=self._tenant_id)

    @asynccontextmanager
    async def __aenter__(self) -> TissClient:
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    @property
    def certificate_expires_in_days(self) -> int:
        """Get days until certificate expiration."""
        if not self._certificate:
            return 0
        return self._certificate.days_until_expiration
