"""Tests for ValidateDocumentationWorker."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pytest
from unittest.mock import AsyncMock

from healthcare_platform.patient_access.workers.validate_documentation_worker import (
    ValidateDocumentationWorker,
    DocumentValidationInput,
    DocumentValidationOutput,
    DocumentationValidatorProtocol,
    PatientAccessException,
)
from healthcare_platform.shared.domain.enums import TenantCode
from healthcare_platform.shared.domain.exceptions import DomainException


class MockDocumentationValidator(DocumentationValidatorProtocol):
    """Mock validator for testing."""

    def __init__(self):
        self.validate_cpf_called = False
        self.validate_rg_called = False
        self.validate_cns_called = False
        self.validate_insurance_called = False
        self.should_fail = False

    async def validate_cpf(self, cpf: str) -> tuple[bool, str | None]:
        """Mock CPF validation."""
        self.validate_cpf_called = True
        if self.should_fail:
            return False, "CPF inválido"
        if len(cpf.replace(".", "").replace("-", "")) != 11:
            return False, "CPF deve conter 11 dígitos"
        return True, None

    async def validate_rg(self, rg: str, issuer: str) -> tuple[bool, str | None]:
        """Mock RG validation."""
        self.validate_rg_called = True
        if len(rg) < 5:
            return False, "RG inválido - número muito curto"
        if not issuer:
            return False, "Órgão emissor do RG não informado"
        return True, None

    async def validate_cns(self, cns: str) -> tuple[bool, str | None]:
        """Mock CNS validation."""
        self.validate_cns_called = True
        cns_digits = "".join(filter(str.isdigit, cns))
        if len(cns_digits) != 15:
            return False, "CNS deve conter 15 dígitos"
        return True, None

    async def validate_insurance_card(
        self, card_number: str, expiry_date: date | None
    ) -> tuple[bool, str | None, int | None]:
        """Mock insurance card validation."""
        self.validate_insurance_called = True
        if len(card_number) < 8:
            return False, "Número da carteirinha inválido", None

        if expiry_date:
            today = date.today()
            days_until_expiry = (expiry_date - today).days

            if days_until_expiry < 0:
                return False, f"Carteirinha vencida há {abs(days_until_expiry)} dias", days_until_expiry

            return True, None, days_until_expiry

        return True, None, None


@pytest.fixture
def mock_validator():
    return MockDocumentationValidator()


@pytest.fixture
def worker(mock_validator):
    return ValidateDocumentationWorker(validator=mock_validator)


@pytest.mark.unit
class TestValidateDocumentationWorker:
    @pytest.mark.asyncio
    async def test_happy_path_all_documents_valid(
        self, worker, mock_validator, tenant_austa
    ):
        """Test successful validation of all required documents."""
        # Arrange
        task_vars = {
            "patient_id": "patient_123",
            "documents": {
                "CPF": {"number": "12345678901"},
                "RG": {"number": "123456789", "issuer": "SSP-SP"},
                "CNS": {"number": "123456789012345"},
                "INSURANCE_CARD": {
                    "number": "CARD12345678",
                    "expiry_date": (date.today() + timedelta(days=365)).isoformat(),
                },
            },
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["patient_id"] == "patient_123"
        assert result["all_valid"] is True
        assert len(result["validation_results"]) == 4
        assert len(result["missing_documents"]) == 0
        assert len(result["expired_documents"]) == 0
        assert mock_validator.validate_cpf_called is True
        assert mock_validator.validate_rg_called is True
        assert mock_validator.validate_cns_called is True
        assert mock_validator.validate_insurance_called is True

    @pytest.mark.asyncio
    async def test_missing_required_documents(
        self, worker, mock_validator, tenant_austa
    ):
        """Test detection of missing required documents."""
        # Arrange - Only CPF provided
        task_vars = {
            "patient_id": "patient_missing",
            "documents": {
                "CPF": {"number": "12345678901"},
            },
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["all_valid"] is False
        assert "RG" in result["missing_documents"]
        assert "CNS" in result["missing_documents"]

    @pytest.mark.asyncio
    async def test_invalid_cpf(self, worker, mock_validator, tenant_austa):
        """Test validation of invalid CPF."""
        # Arrange
        task_vars = {
            "patient_id": "patient_invalid_cpf",
            "documents": {
                "CPF": {"number": "123"},  # Too short
                "RG": {"number": "123456789", "issuer": "SSP-SP"},
                "CNS": {"number": "123456789012345"},
            },
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert result["all_valid"] is False
        cpf_result = next(r for r in result["validation_results"] if r["document_type"] == "CPF")
        assert cpf_result["is_valid"] is False
        assert "11 dígitos" in cpf_result["reason"]

    @pytest.mark.asyncio
    async def test_expired_insurance_card(self, worker, mock_validator, tenant_austa):
        """Test detection of expired insurance card."""
        # Arrange
        expired_date = date.today() - timedelta(days=30)
        task_vars = {
            "patient_id": "patient_expired",
            "documents": {
                "CPF": {"number": "12345678901"},
                "RG": {"number": "123456789", "issuer": "SSP-SP"},
                "CNS": {"number": "123456789012345"},
                "INSURANCE_CARD": {
                    "number": "CARD12345678",
                    "expiry_date": expired_date.isoformat(),
                },
            },
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert
        assert "INSURANCE_CARD" in result["expired_documents"]
        card_result = next(
            r for r in result["validation_results"] if r["document_type"] == "INSURANCE_CARD"
        )
        assert card_result["is_valid"] is False
        assert card_result["days_until_expiry"] < 0

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, worker, tenant_austa):
        """Test that missing patient_id raises DomainException."""
        with pytest.raises(DomainException):
            await worker.execute(
                {
                    "documents": {
                        "CPF": {"number": "12345678901"},
                    },
                }
            )

    @pytest.mark.asyncio
    async def test_no_tenant_raises(self, worker):
        """Test that missing tenant context raises InvalidTenant."""
        from healthcare_platform.shared.domain.exceptions import InvalidTenant

        with pytest.raises(InvalidTenant):
            await worker.execute(
                {
                    "patient_id": "patient_123",
                    "documents": {
                        "CPF": {"number": "12345678901"},
                    },
                }
            )

    @pytest.mark.asyncio
    async def test_validation_service_failure(
        self, worker, mock_validator, tenant_austa
    ):
        """Test handling of validation service failure."""
        # Arrange
        mock_validator.should_fail = True
        task_vars = {
            "patient_id": "patient_fail",
            "documents": {
                "CPF": {"number": "12345678901"},
                "RG": {"number": "123456789", "issuer": "SSP-SP"},
                "CNS": {"number": "123456789012345"},
            },
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert - Should handle gracefully, mark CPF as invalid
        assert result["all_valid"] is False

    @pytest.mark.asyncio
    async def test_multi_tenant_isolation(
        self, worker, mock_validator, tenant_austa, tenant_hpa
    ):
        """Test that document validations are isolated per tenant."""
        # Arrange
        task_vars_austa = {
            "patient_id": "patient_austa",
            "documents": {
                "CPF": {"number": "11111111111"},
                "RG": {"number": "123456789", "issuer": "SSP-SP"},
                "CNS": {"number": "111111111111111"},
            },
        }

        task_vars_hpa = {
            "patient_id": "patient_hpa",
            "documents": {
                "CPF": {"number": "22222222222"},
                "RG": {"number": "987654321", "issuer": "SSP-RJ"},
                "CNS": {"number": "222222222222222"},
            },
        }

        # Act
        result_austa = await worker.execute(task_vars_austa)
        result_hpa = await worker.execute(task_vars_hpa)

        # Assert - Different patients
        assert result_austa["patient_id"] != result_hpa["patient_id"]

    @pytest.mark.asyncio
    async def test_idempotency(self, worker, mock_validator, tenant_austa):
        """Test that validating documents twice produces same result."""
        # Arrange
        task_vars = {
            "patient_id": "patient_idem",
            "documents": {
                "CPF": {"number": "12345678901"},
                "RG": {"number": "123456789", "issuer": "SSP-SP"},
                "CNS": {"number": "123456789012345"},
            },
        }

        # Act
        result1 = await worker.execute(task_vars)
        result2 = await worker.execute(task_vars)

        # Assert - Both produce same result
        assert result1["all_valid"] == result2["all_valid"]
        assert len(result1["validation_results"]) == len(result2["validation_results"])

    @pytest.mark.asyncio
    async def test_validation_timestamp(self, worker, mock_validator, tenant_austa):
        """Test that validation_timestamp is properly set."""
        # Arrange
        task_vars = {
            "patient_id": "patient_ts",
            "documents": {
                "CPF": {"number": "12345678901"},
                "RG": {"number": "123456789", "issuer": "SSP-SP"},
                "CNS": {"number": "123456789012345"},
            },
        }

        # Act
        before = datetime.utcnow()
        result = await worker.execute(task_vars)
        after = datetime.utcnow()

        # Assert - Timestamp is between before and after
        validation_time = datetime.fromisoformat(
            result["validation_timestamp"].replace("Z", "+00:00").replace("+00:00", "")
        )
        assert before <= validation_time <= after

    @pytest.mark.asyncio
    async def test_card_expiring_soon_warning(
        self, worker, mock_validator, tenant_austa
    ):
        """Test detection of insurance card expiring soon."""
        # Arrange - Card expires in 20 days
        expiring_date = date.today() + timedelta(days=20)
        task_vars = {
            "patient_id": "patient_expiring",
            "documents": {
                "CPF": {"number": "12345678901"},
                "RG": {"number": "123456789", "issuer": "SSP-SP"},
                "CNS": {"number": "123456789012345"},
                "INSURANCE_CARD": {
                    "number": "CARD12345678",
                    "expiry_date": expiring_date.isoformat(),
                },
            },
        }

        # Act
        result = await worker.execute(task_vars)

        # Assert - Still valid but expiring soon
        card_result = next(
            r for r in result["validation_results"] if r["document_type"] == "INSURANCE_CARD"
        )
        assert card_result["is_valid"] is True
        assert 0 < card_result["days_until_expiry"] < 30
