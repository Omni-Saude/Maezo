"""Multi-payer Insurance API Client.

Supports eligibility verification and prior authorization
across multiple insurance payers with tenant-specific configurations.
"""
from __future__ import annotations

from abc import abstractmethod
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from platform.shared.domain.enums import CoverageStatus
from platform.shared.domain.exceptions import ExternalServiceException
from platform.shared.integrations.base import BaseIntegrationClient, IntegrationSettings
from platform.shared.observability.logging import get_logger
from platform.shared.observability.metrics import track_api_call

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class PayerConfig(BaseModel):
    """Configuration for a specific insurance payer."""

    model_config = ConfigDict(frozen=True)

    payer_id: str
    payer_name: str
    base_url: str
    timeout_seconds: int = 30
    supports_real_time_auth: bool = True


class EligibilityRequest(BaseModel):
    """Eligibility verification request."""

    patient_id: str
    member_id: str
    payer_id: str
    date_of_service: datetime
    provider_id: str
    service_type_codes: list[str] = Field(default_factory=list)


class EligibilityResponse(BaseModel):
    """Eligibility verification response."""

    request_id: str = ""
    payer_id: str
    coverage_status: CoverageStatus
    effective_date: datetime | None = None
    termination_date: datetime | None = None
    copay_amount: float | None = None
    deductible_remaining: float | None = None
    plan_name: str | None = None
    group_number: str | None = None
    covered_services: list[str] = Field(default_factory=list)
    response_code: str = ""
    response_message: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AuthorizationRequest(BaseModel):
    """Prior authorization request."""

    patient_id: str
    member_id: str
    payer_id: str
    provider_id: str
    procedure_codes: list[str]
    diagnosis_codes: list[str]
    requested_start_date: datetime
    requested_end_date: datetime | None = None
    quantity: int = 1
    urgency_level: str = "routine"
    clinical_justification: str | None = None


class AuthorizationResponse(BaseModel):
    """Prior authorization response."""

    authorization_id: str = ""
    payer_id: str
    status: str  # pending, approved, denied, pended
    auth_number: str | None = None
    approved_quantity: int | None = None
    approved_start_date: datetime | None = None
    approved_end_date: datetime | None = None
    denial_reason: str | None = None
    required_documentation: list[str] = Field(default_factory=list)
    response_code: str = ""
    response_message: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class InsuranceAPIClientProtocol(Protocol):
    """Interface for multi-payer insurance API operations."""

    @abstractmethod
    async def verify_eligibility(self, request: EligibilityRequest) -> EligibilityResponse: ...

    @abstractmethod
    async def request_authorization(self, request: AuthorizationRequest) -> AuthorizationResponse: ...

    @abstractmethod
    async def check_authorization_status(self, auth_id: str, payer_id: str) -> AuthorizationResponse: ...

    @abstractmethod
    async def get_payer_config(self, payer_id: str) -> PayerConfig: ...


# ---------------------------------------------------------------------------
# Production Implementation
# ---------------------------------------------------------------------------


class InsuranceAPIClient(BaseIntegrationClient, InsuranceAPIClientProtocol):
    """Production multi-payer insurance API client."""

    SERVICE_NAME = "insurance_api"

    def __init__(
        self,
        settings: IntegrationSettings,
        payer_configs: dict[str, PayerConfig] | None = None,
    ) -> None:
        super().__init__(settings)
        self._payer_configs = payer_configs or {}

    async def get_payer_config(self, payer_id: str) -> PayerConfig:
        config = self._payer_configs.get(payer_id)
        if not config:
            raise ExternalServiceException(
                f"Payer not configured: {payer_id}",
                service_name=self.SERVICE_NAME,
                operation="get_payer_config",
            )
        return config

    @track_api_call(service="insurance_api", endpoint="verify_eligibility", method="POST")
    async def verify_eligibility(self, request: EligibilityRequest) -> EligibilityResponse:
        config = await self.get_payer_config(request.payer_id)
        self._logger.info(
            "eligibility_check_started",
            payer_id=request.payer_id,
            service_type_count=len(request.service_type_codes),
        )
        resp = await self._request(
            "POST",
            f"{config.base_url}/eligibility/verify",
            json={
                "member_id": request.member_id,
                "date_of_service": request.date_of_service.isoformat(),
                "provider_id": request.provider_id,
                "service_types": request.service_type_codes,
            },
        )
        data = resp.json()
        return EligibilityResponse(
            request_id=data.get("request_id", ""),
            payer_id=request.payer_id,
            coverage_status=CoverageStatus(data.get("status", "active")),
            effective_date=_parse_dt(data.get("effective_date")),
            termination_date=_parse_dt(data.get("termination_date")),
            copay_amount=data.get("copay_amount"),
            deductible_remaining=data.get("deductible_remaining"),
            plan_name=data.get("plan_name"),
            group_number=data.get("group_number"),
            covered_services=data.get("covered_services", []),
            response_code=data.get("code", "SUCCESS"),
            response_message=data.get("message", ""),
        )

    @track_api_call(service="insurance_api", endpoint="request_authorization", method="POST")
    async def request_authorization(self, request: AuthorizationRequest) -> AuthorizationResponse:
        config = await self.get_payer_config(request.payer_id)
        self._logger.info(
            "authorization_request_started",
            payer_id=request.payer_id,
            urgency=request.urgency_level,
        )
        resp = await self._request(
            "POST",
            f"{config.base_url}/authorization/request",
            json={
                "member_id": request.member_id,
                "provider_id": request.provider_id,
                "procedures": request.procedure_codes,
                "diagnoses": request.diagnosis_codes,
                "start_date": request.requested_start_date.isoformat(),
                "end_date": request.requested_end_date.isoformat() if request.requested_end_date else None,
                "quantity": request.quantity,
                "urgency": request.urgency_level,
            },
        )
        data = resp.json()
        return _parse_auth_response(data, request.payer_id)

    @track_api_call(service="insurance_api", endpoint="check_authorization_status", method="GET")
    async def check_authorization_status(self, auth_id: str, payer_id: str) -> AuthorizationResponse:
        config = await self.get_payer_config(payer_id)
        resp = await self._request("GET", f"{config.base_url}/authorization/{auth_id}/status")
        data = resp.json()
        return _parse_auth_response(data, payer_id)


# ---------------------------------------------------------------------------
# Stub for Testing
# ---------------------------------------------------------------------------


class StubInsuranceAPIClient(InsuranceAPIClientProtocol):
    """In-memory stub for unit tests."""

    def __init__(self) -> None:
        self._configs: dict[str, PayerConfig] = {}

    async def get_payer_config(self, payer_id: str) -> PayerConfig:
        if payer_id not in self._configs:
            self._configs[payer_id] = PayerConfig(
                payer_id=payer_id,
                payer_name=f"Stub Payer {payer_id}",
                base_url="http://stub",
            )
        return self._configs[payer_id]

    async def verify_eligibility(self, request: EligibilityRequest) -> EligibilityResponse:
        return EligibilityResponse(
            request_id=f"stub-{request.patient_id}",
            payer_id=request.payer_id,
            coverage_status=CoverageStatus.ACTIVE,
            plan_name="Stub Plan",
            response_code="SUCCESS",
            response_message="Stub eligibility OK",
        )

    async def request_authorization(self, request: AuthorizationRequest) -> AuthorizationResponse:
        return AuthorizationResponse(
            authorization_id=f"stub-auth-{request.patient_id}",
            payer_id=request.payer_id,
            status="approved",
            auth_number="STUB-12345",
            approved_quantity=request.quantity,
            response_code="SUCCESS",
            response_message="Stub authorization approved",
        )

    async def check_authorization_status(self, auth_id: str, payer_id: str) -> AuthorizationResponse:
        return AuthorizationResponse(
            authorization_id=auth_id,
            payer_id=payer_id,
            status="approved",
            auth_number="STUB-12345",
            response_code="SUCCESS",
            response_message="Stub status OK",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _parse_auth_response(data: dict[str, Any], payer_id: str) -> AuthorizationResponse:
    return AuthorizationResponse(
        authorization_id=data.get("authorization_id", ""),
        payer_id=payer_id,
        status=data.get("status", "pending"),
        auth_number=data.get("auth_number"),
        approved_quantity=data.get("approved_quantity"),
        approved_start_date=_parse_dt(data.get("approved_start_date")),
        approved_end_date=_parse_dt(data.get("approved_end_date")),
        denial_reason=data.get("denial_reason"),
        required_documentation=data.get("required_documentation", []),
        response_code=data.get("code", "SUCCESS"),
        response_message=data.get("message", ""),
    )
