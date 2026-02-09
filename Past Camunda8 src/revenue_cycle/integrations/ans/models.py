"""ANS Rol de Procedimentos data models."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ProcedureStatus(str, Enum):
    """Status of procedure in ANS Rol."""

    ACTIVE = "active"  # Ativo no Rol atual
    INACTIVE = "inactive"  # Inativo/removido
    SUSPENDED = "suspended"  # Suspenso temporariamente
    DEPRECATED = "deprecated"  # Obsoleto, substituído por outro


class CoverageType(str, Enum):
    """Type of coverage for the procedure."""

    MANDATORY = "mandatory"  # Cobertura obrigatória
    OPTIONAL = "optional"  # Cobertura opcional
    EXCLUDED = "excluded"  # Expressamente excluído


class ProcedureDTO(BaseModel):
    """ANS Rol procedure details."""

    procedure_code: str = Field(description="TUSS procedure code (8 digits)")
    description: str = Field(description="Official procedure description")
    status: ProcedureStatus = Field(description="Current status in Rol")
    coverage_type: CoverageType = Field(description="Coverage classification")
    effective_date: date = Field(description="Date procedure became effective")
    termination_date: Optional[date] = Field(
        default=None,
        description="Date procedure was removed/deprecated",
    )
    category: str = Field(description="Procedure category (consulta, exame, cirurgia, etc)")
    specialty: Optional[str] = Field(
        default=None,
        description="Medical specialty if applicable",
    )
    requires_authorization: bool = Field(
        default=False,
        description="Whether procedure requires prior authorization",
    )
    rol_version: str = Field(description="ANS Rol version (e.g., '2023', '2024')")

    # Regulatory references
    resolution_number: str = Field(
        description="ANS Resolution number (e.g., 'RN 465/2021')"
    )

    class Config:
        """Pydantic config."""

        frozen = False
        json_schema_extra = {
            "example": {
                "procedure_code": "10101012",
                "description": "Consulta médica em consultório",
                "status": "active",
                "coverage_type": "mandatory",
                "effective_date": "2023-01-01",
                "category": "Consulta",
                "requires_authorization": False,
                "rol_version": "2023",
                "resolution_number": "RN 465/2021",
            }
        }

    @field_validator("procedure_code")
    @classmethod
    def validate_tuss_format(cls, v: str) -> str:
        """Validate TUSS code format (8 digits)."""
        if not v or not isinstance(v, str):
            raise ValueError("Procedure code must be a string")

        # Remove any whitespace
        v = v.strip()

        # TUSS codes are 8 digits: TTMMPPPP
        # TT = Table, MM = Terminology, PPPP = Procedure
        if len(v) != 8 or not v.isdigit():
            raise ValueError(
                f"Invalid TUSS code format: {v}. Expected 8 digits (TTMMPPPP)"
            )

        return v


class RolValidationResult(BaseModel):
    """Result of ANS Rol validation."""

    procedure_code: str = Field(description="Validated procedure code")
    is_valid: bool = Field(description="Whether procedure is valid in current Rol")
    is_covered: bool = Field(description="Whether procedure has mandatory coverage")
    status: Optional[ProcedureStatus] = Field(
        default=None,
        description="Procedure status if found",
    )
    coverage_type: Optional[CoverageType] = Field(
        default=None,
        description="Coverage type if found",
    )
    validation_date: datetime = Field(
        default_factory=datetime.now,
        description="When validation was performed",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if validation failed",
    )
    cached: bool = Field(
        default=False,
        description="Whether result came from cache",
    )

    class Config:
        """Pydantic config."""

        frozen = False


class RolSearchRequest(BaseModel):
    """Request for searching ANS Rol procedures."""

    query: Optional[str] = Field(
        default=None,
        description="Search query (procedure code or description)",
    )
    procedure_code: Optional[str] = Field(
        default=None,
        description="Exact procedure code to find",
    )
    category: Optional[str] = Field(
        default=None,
        description="Filter by category",
    )
    status: Optional[ProcedureStatus] = Field(
        default=ProcedureStatus.ACTIVE,
        description="Filter by status (default: active only)",
    )
    coverage_type: Optional[CoverageType] = Field(
        default=None,
        description="Filter by coverage type",
    )
    rol_version: Optional[str] = Field(
        default=None,
        description="Specific Rol version (default: current)",
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum results to return",
    )

    class Config:
        """Pydantic config."""

        frozen = False


class RolSearchResponse(BaseModel):
    """Response from ANS Rol search."""

    total_count: int = Field(description="Total procedures matching query")
    procedures: list[ProcedureDTO] = Field(
        default_factory=list,
        description="List of matching procedures",
    )
    rol_version: str = Field(description="ANS Rol version queried")
    query_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When search was performed",
    )
    cached: bool = Field(
        default=False,
        description="Whether results came from cache",
    )

    class Config:
        """Pydantic config."""

        frozen = False


class RolCacheEntry(BaseModel):
    """Cache entry for ANS Rol procedure data."""

    procedure_code: str
    procedure_data: ProcedureDTO
    cached_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime
    tenant_id: Optional[str] = None

    class Config:
        """Pydantic config."""

        frozen = False

    @property
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return datetime.now() >= self.expires_at
