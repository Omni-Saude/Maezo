"""Tests for ValidateProcedureWorker."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from platform.shared.domain.enums import TenantCode
from platform.shared.domain.exceptions import CodingException, InvalidProcedureCode
from platform.shared.integrations.ans_client import ProcedureDTO, RolValidationResult
from platform.shared.multi_tenant.context import TenantContext, set_current_tenant, clear_tenant

from revenue_cycle.production.workers.validate_procedure_worker import ValidateProcedureWorker


@pytest.fixture
def tenant_ctx():
    ctx = TenantContext.from_tenant_code(TenantCode.AUSTA)
    set_current_tenant(ctx)
    yield ctx
    clear_tenant()


@pytest.fixture
def ans_client():
    return AsyncMock()


@pytest.fixture
def worker(ans_client):
    return ValidateProcedureWorker(ans_client=ans_client)


class TestValidateProcedureWorker:
    @pytest.mark.asyncio
    async def test_valid_procedures(self, worker, ans_client, tenant_ctx):
        ans_client.validate_procedure.return_value = RolValidationResult(
            code="40101010",
            is_valid=True,
            is_covered=True,
            coverage_type="ambulatorial",
            message="OK",
            procedure=ProcedureDTO(
                code="40101010",
                name="Consulta médica",
                coverage_type="ambulatorial",
                active=True,
            ),
        )

        result = await worker.execute({
            "procedure_codes": ["40101010"],
            "coverage_type": "ambulatorial",
        })

        assert result["all_valid"] is True
        assert len(result["validated_procedures"]) == 1
        assert result["invalid_codes"] == []

    @pytest.mark.asyncio
    async def test_invalid_procedure_raises(self, worker, ans_client, tenant_ctx):
        ans_client.validate_procedure.return_value = RolValidationResult(
            code="99999999",
            is_valid=False,
            is_covered=False,
            message="Not found",
        )

        with pytest.raises(InvalidProcedureCode) as exc_info:
            await worker.execute({
                "procedure_codes": ["99999999"],
                "coverage_type": "ambulatorial",
            })

        assert "99999999" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_codes_raises(self, worker, tenant_ctx):
        with pytest.raises(CodingException):
            await worker.execute({"procedure_codes": [], "coverage_type": ""})

    @pytest.mark.asyncio
    async def test_multiple_codes_mixed(self, worker, ans_client, tenant_ctx):
        async def mock_validate(code):
            if code == "40101010":
                return RolValidationResult(
                    code=code, is_valid=True, is_covered=True,
                    coverage_type="ambulatorial", message="OK",
                    procedure=ProcedureDTO(
                        code=code, name="Consulta", coverage_type="ambulatorial", active=True
                    ),
                )
            return RolValidationResult(
                code=code, is_valid=False, is_covered=False, message="Not found",
            )

        ans_client.validate_procedure.side_effect = mock_validate

        with pytest.raises(InvalidProcedureCode):
            await worker.execute({
                "procedure_codes": ["40101010", "INVALID"],
                "coverage_type": "ambulatorial",
            })
