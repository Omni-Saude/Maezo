"""Pydantic v2 request/response schemas for the Contract Rule Extraction API."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from healthcare_platform.contract_extraction.models import (
    RuleArchetype,
    RuleCategory,
    RuleStatus,
)

_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


class RuleCreateRequest(BaseModel):
    """Payload for creating a new contract rule."""

    model_config = {"from_attributes": True}

    payer_id: str = Field(..., min_length=1)
    category: RuleCategory
    archetype: RuleArchetype
    rule_definition: Dict[str, Any]
    version: str = Field(
        default="1.0.0",
        pattern=r"^\d+\.\d+\.\d+$",
        description="Semantic version string (MAJOR.MINOR.PATCH)",
    )
    effective_date: date
    expiry_date: Optional[date] = None

    @field_validator("payer_id")
    @classmethod
    def validate_payer_id(cls, v: str) -> str:
        if not re.match(r'^[A-Za-z0-9_-]+$', v):
            raise ValueError("payer_id must match ^[A-Za-z0-9_-]+$")
        return v

    @model_validator(mode="after")
    def expiry_must_be_after_effective(self) -> RuleCreateRequest:
        if self.expiry_date is not None and self.expiry_date <= self.effective_date:
            raise ValueError("expiry_date must be strictly after effective_date")
        return self


class RuleUpdateRequest(BaseModel):
    """Partial update payload for an existing contract rule."""

    model_config = {"from_attributes": True}

    payer_id: Optional[str] = Field(default=None, min_length=1)
    category: Optional[RuleCategory] = None
    archetype: Optional[RuleArchetype] = None
    rule_definition: Optional[Dict[str, Any]] = None
    version: Optional[str] = Field(
        default=None,
        pattern=r"^\d+\.\d+\.\d+$",
    )
    effective_date: Optional[date] = None
    expiry_date: Optional[date] = None

    @field_validator("payer_id")
    @classmethod
    def validate_payer_id(cls, v: str | None) -> str | None:
        if v is not None and not re.match(r'^[A-Za-z0-9_-]+$', v):
            raise ValueError("payer_id must match ^[A-Za-z0-9_-]+$")
        return v

    @model_validator(mode="after")
    def expiry_must_be_after_effective(self) -> RuleUpdateRequest:
        if (
            self.expiry_date is not None
            and self.effective_date is not None
            and self.expiry_date <= self.effective_date
        ):
            raise ValueError("expiry_date must be strictly after effective_date")
        return self


class RuleResponse(BaseModel):
    """Response schema representing a persisted ContractRule."""

    model_config = {"from_attributes": True}

    id: UUID
    tenant_id: str
    payer_id: str
    category: RuleCategory
    archetype: RuleArchetype
    rule_definition: Dict[str, Any]
    version: str
    effective_date: date
    expiry_date: Optional[date] = None
    status: RuleStatus
    created_at: datetime
    updated_at: datetime


class ValidationErrorSchema(BaseModel):
    """A single validation error entry (mirrors validators.ValidationError)."""

    field: str
    message: str
    code: str


class ValidationResponse(BaseModel):
    """Response from the rule validation endpoint."""

    rule_id: UUID
    is_valid: bool
    errors: List[ValidationErrorSchema]
    warnings: List[str]


class DMNPreviewResponse(BaseModel):
    """Response containing a DMN XML preview for a rule (not persisted)."""

    rule_id: UUID
    archetype: RuleArchetype
    version: str
    xml_content: str
    generated_at: datetime


class DeployResponse(BaseModel):
    """Response after successfully deploying a contract rule."""

    rule_id: UUID
    tenant_id: str
    status: RuleStatus
    dmn_path: str
    version: str
    deployed_at: datetime


class ChangeResponse(BaseModel):
    """Response schema for a single audit trail entry."""

    model_config = {"from_attributes": True}

    id: UUID
    rule_id: UUID
    changed_by: str
    changed_at: datetime
    change_type: str
    old_value: Optional[Dict[str, Any]] = None
    new_value: Optional[Dict[str, Any]] = None
