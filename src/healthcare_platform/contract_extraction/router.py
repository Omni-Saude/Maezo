"""FastAPI router for the Contract Rule Extraction API."""
import re
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from healthcare_platform.contract_extraction.dependencies import get_contract_service
from healthcare_platform.contract_extraction.models import RuleCategory, RuleStatus
from healthcare_platform.contract_extraction.schemas import (
    ChangeResponse,
    DeployResponse,
    DMNPreviewResponse,
    RuleCreateRequest,
    RuleResponse,
    RuleUpdateRequest,
    ValidationErrorSchema,
    ValidationResponse,
)
from healthcare_platform.contract_extraction.services.contract_service import ContractService

router = APIRouter(
    prefix="/contracts/{tenant_id}/rules",
    tags=["contract-rules"],
)


_TENANT_ID_RE = re.compile(r'^[a-z0-9_-]+$')


def _validate_tenant_id(tenant_id: str) -> str:
    """Validate tenant_id path parameter."""
    if not _TENANT_ID_RE.match(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant_id: must match [a-z0-9_-]+",
        )
    return tenant_id


def _rule_not_found(rule_id: UUID) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Rule {rule_id} not found")


@router.post("/", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(
    tenant_id: str,
    payload: RuleCreateRequest,
    svc: ContractService = Depends(get_contract_service),  # noqa: B008
) -> RuleResponse:
    tenant_id = _validate_tenant_id(tenant_id)
    try:
        rule = svc.create_rule(tenant_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RuleResponse.model_validate(rule)


@router.get("/", response_model=List[RuleResponse])
def list_rules(
    tenant_id: str,
    rule_status: Optional[RuleStatus] = None,
    category: Optional[RuleCategory] = None,
    skip: int = 0,
    limit: int = 100,
    svc: ContractService = Depends(get_contract_service),  # noqa: B008
) -> List[RuleResponse]:
    tenant_id = _validate_tenant_id(tenant_id)
    rules = svc.list_rules(
        tenant_id=tenant_id, status=rule_status, category=category, skip=skip, limit=limit
    )
    return [RuleResponse.model_validate(r) for r in rules]


@router.get("/{rule_id}", response_model=RuleResponse)
def get_rule(
    tenant_id: str,
    rule_id: UUID,
    svc: ContractService = Depends(get_contract_service),  # noqa: B008
) -> RuleResponse:
    tenant_id = _validate_tenant_id(tenant_id)
    try:
        rule = svc.get_rule(tenant_id, rule_id)
    except KeyError:
        raise _rule_not_found(rule_id) from None
    return RuleResponse.model_validate(rule)


@router.put("/{rule_id}", response_model=RuleResponse)
def update_rule(
    tenant_id: str,
    rule_id: UUID,
    payload: RuleUpdateRequest,
    svc: ContractService = Depends(get_contract_service),  # noqa: B008
) -> RuleResponse:
    tenant_id = _validate_tenant_id(tenant_id)
    try:
        rule = svc.update_rule(tenant_id, rule_id, payload)
    except KeyError:
        raise _rule_not_found(rule_id) from None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return RuleResponse.model_validate(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    tenant_id: str,
    rule_id: UUID,
    svc: ContractService = Depends(get_contract_service),  # noqa: B008
) -> Response:
    tenant_id = _validate_tenant_id(tenant_id)
    try:
        svc.delete_rule(tenant_id, rule_id)
    except KeyError:
        raise _rule_not_found(rule_id) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{rule_id}/validate", response_model=ValidationResponse)
def validate_rule(
    tenant_id: str,
    rule_id: UUID,
    svc: ContractService = Depends(get_contract_service),  # noqa: B008
) -> ValidationResponse:
    tenant_id = _validate_tenant_id(tenant_id)
    try:
        result = svc.validate_rule_by_id(tenant_id, rule_id)
    except KeyError:
        raise _rule_not_found(rule_id) from None
    error_schemas = [
        ValidationErrorSchema(field=e["field"], message=e["message"], code=e["code"])
        for e in result["errors"]
    ]
    return ValidationResponse(
        rule_id=UUID(result["rule_id"]),
        is_valid=result["is_valid"],
        errors=error_schemas,
        warnings=[],
    )


@router.post("/{rule_id}/preview-dmn", response_model=DMNPreviewResponse)
def preview_dmn(
    tenant_id: str,
    rule_id: UUID,
    svc: ContractService = Depends(get_contract_service),  # noqa: B008
) -> DMNPreviewResponse:
    tenant_id = _validate_tenant_id(tenant_id)
    try:
        result = svc.preview_dmn(tenant_id, rule_id)
    except KeyError:
        raise _rule_not_found(rule_id) from None
    return DMNPreviewResponse(
        rule_id=UUID(result["rule_id"]),
        archetype=result["archetype"],
        version=result["version"],
        xml_content=result["xml_content"],
        generated_at=result["generated_at"],
    )


@router.post("/{rule_id}/deploy", response_model=DeployResponse)
def deploy_rule(
    tenant_id: str,
    rule_id: UUID,
    svc: ContractService = Depends(get_contract_service),  # noqa: B008
) -> DeployResponse:
    tenant_id = _validate_tenant_id(tenant_id)
    try:
        result = svc.deploy_rule(tenant_id, rule_id)
    except KeyError:
        raise _rule_not_found(rule_id) from None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return DeployResponse(
        rule_id=UUID(result["rule_id"]),
        tenant_id=result["tenant_id"],
        status=result["status"],
        dmn_path=result["dmn_path"],
        version=result["version"],
        deployed_at=result["deployed_at"],
    )


@router.get("/{rule_id}/history", response_model=List[ChangeResponse])
def get_rule_history(
    tenant_id: str,
    rule_id: UUID,
    svc: ContractService = Depends(get_contract_service),  # noqa: B008
) -> List[ChangeResponse]:
    tenant_id = _validate_tenant_id(tenant_id)
    try:
        changes = svc.get_rule_history(tenant_id, rule_id)
    except KeyError:
        raise _rule_not_found(rule_id) from None
    return [ChangeResponse.model_validate(c) for c in changes]
