"""
Pricing Service for Hospital Revenue Cycle.

Provides procedure pricing lookup with support for:
- Insurance-specific contracted prices
- Base pricing from TUSS/CBHPM tables
- Procedure descriptions and types
- Insurance pricing table identification

This is the Python implementation of the Java PricingService interface.
"""

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any, Dict, Optional

import structlog

from revenue_cycle.workers.billing.models import ProcedureType, TUSS_PATTERN, CBHPM_PATTERN

logger = structlog.get_logger(__name__)


class PricingError(Exception):
    """Exception raised when pricing lookup fails."""

    def __init__(self, message: str, procedure_code: Optional[str] = None):
        self.message = message
        self.procedure_code = procedure_code
        super().__init__(message)


class PricingService(ABC):
    """
    Abstract pricing service interface.

    Defines the contract for procedure pricing lookup.
    """

    @abstractmethod
    async def get_procedure_price(
        self,
        procedure_code: str,
        insurance_id: Optional[str] = None,
    ) -> Decimal:
        """
        Get price for a procedure code.

        Args:
            procedure_code: TUSS or CBHPM procedure code
            insurance_id: Optional insurance identifier for contracted pricing

        Returns:
            Procedure price as Decimal

        Raises:
            PricingError: If procedure not found or pricing unavailable
        """
        ...

    @abstractmethod
    async def get_procedure_description(
        self,
        procedure_code: str,
    ) -> str:
        """
        Get description for a procedure code.

        Args:
            procedure_code: TUSS or CBHPM procedure code

        Returns:
            Human-readable procedure description
        """
        ...

    @abstractmethod
    async def determine_procedure_type(
        self,
        procedure_code: str,
    ) -> str:
        """
        Determine procedure type from code.

        Args:
            procedure_code: TUSS or CBHPM procedure code

        Returns:
            Procedure type (SURGICAL, CLINICAL, DIAGNOSTIC, etc.)
        """
        ...

    @abstractmethod
    async def get_insurance_table(
        self,
        insurance_id: Optional[str],
    ) -> str:
        """
        Get pricing table code for insurance.

        Args:
            insurance_id: Insurance identifier

        Returns:
            Pricing table code (SUS, AMB, CBHPM, etc.)
        """
        ...


class DatabasePricingService(PricingService):
    """
    PostgreSQL-based pricing service implementation.

    Retrieves pricing from the database with support for:
    - Insurance-specific contracted prices
    - Base prices from procedures table
    - Procedure metadata (descriptions, types)
    """

    def __init__(self, db_service: Any):
        """
        Initialize with database service.

        Args:
            db_service: Async database service with fetch_one method
        """
        self.db = db_service
        self._logger = logger.bind(service="DatabasePricingService")

    async def get_procedure_price(
        self,
        procedure_code: str,
        insurance_id: Optional[str] = None,
    ) -> Decimal:
        """
        Get procedure price, preferring insurance-specific pricing.

        First attempts to get contracted price from insurance_procedures.
        Falls back to base_price from procedures table.

        Args:
            procedure_code: TUSS or CBHPM procedure code
            insurance_id: Optional insurance identifier

        Returns:
            Procedure price as Decimal

        Raises:
            PricingError: If procedure not found
        """
        self._logger.debug(
            "Looking up procedure price",
            procedure_code=procedure_code,
            insurance_id=insurance_id,
        )

        # Try insurance-specific pricing first
        if insurance_id:
            result = await self.db.fetch_one(
                """
                SELECT ip.contracted_price
                FROM insurance_procedures ip
                JOIN insurance_contracts ic ON ip.contract_id = ic.contract_id
                WHERE ip.procedure_code = :code
                  AND ic.insurance_id = :insurance_id
                  AND ic.status = 'ACTIVE'
                """,
                {"code": procedure_code, "insurance_id": insurance_id},
            )
            if result and result.get("contracted_price"):
                price = Decimal(str(result["contracted_price"]))
                self._logger.debug(
                    "Found contracted price",
                    procedure_code=procedure_code,
                    price=float(price),
                )
                return price

        # Fall back to base price
        result = await self.db.fetch_one(
            "SELECT base_price FROM procedures WHERE procedure_code = :code AND active = TRUE",
            {"code": procedure_code},
        )

        if not result or result.get("base_price") is None:
            self._logger.warning(
                "Procedure not found",
                procedure_code=procedure_code,
            )
            raise PricingError(
                f"Procedure not found: {procedure_code}",
                procedure_code=procedure_code,
            )

        price = Decimal(str(result["base_price"]))
        self._logger.debug(
            "Found base price",
            procedure_code=procedure_code,
            price=float(price),
        )
        return price

    async def get_procedure_description(
        self,
        procedure_code: str,
    ) -> str:
        """Get procedure description from database."""
        result = await self.db.fetch_one(
            "SELECT description FROM procedures WHERE procedure_code = :code",
            {"code": procedure_code},
        )

        if result and result.get("description"):
            return result["description"]

        # Default description based on code
        return f"Procedimento {procedure_code}"

    async def determine_procedure_type(
        self,
        procedure_code: str,
    ) -> str:
        """Determine procedure type from database or code analysis."""
        result = await self.db.fetch_one(
            "SELECT procedure_type FROM procedures WHERE procedure_code = :code",
            {"code": procedure_code},
        )

        if result and result.get("procedure_type"):
            return result["procedure_type"]

        # Fall back to code-based type determination
        return ProcedureType.from_code_prefix(procedure_code).value

    async def get_insurance_table(
        self,
        insurance_id: Optional[str],
    ) -> str:
        """Get pricing table for insurance from contract."""
        if not insurance_id:
            return "CUSTOM"

        result = await self.db.fetch_one(
            """
            SELECT pricing_table_code
            FROM insurance_contracts
            WHERE insurance_id = :insurance_id AND status = 'ACTIVE'
            ORDER BY effective_date DESC
            LIMIT 1
            """,
            {"insurance_id": insurance_id},
        )

        if result and result.get("pricing_table_code"):
            return result["pricing_table_code"]

        return "CUSTOM"


class MockPricingService(PricingService):
    """
    Mock pricing service for testing and development.

    Provides realistic mock data based on procedure codes.
    """

    # Mock procedure database with common TUSS codes
    MOCK_PROCEDURES: Dict[str, Dict[str, Any]] = {
        # Clinical procedures (10X)
        "10101012": {
            "description": "Consulta Medica em Consultorio",
            "base_price": Decimal("150.00"),
            "procedure_type": "CLINICAL",
        },
        "10101020": {
            "description": "Consulta Medica em Pronto Socorro",
            "base_price": Decimal("200.00"),
            "procedure_type": "CLINICAL",
        },
        "10102019": {
            "description": "Consulta de Retorno",
            "base_price": Decimal("80.00"),
            "procedure_type": "CLINICAL",
        },
        # Diagnostic procedures (20X)
        "20101015": {
            "description": "Exame de Sangue Completo",
            "base_price": Decimal("45.00"),
            "procedure_type": "DIAGNOSTIC",
        },
        "20201012": {
            "description": "Radiografia de Torax",
            "base_price": Decimal("120.00"),
            "procedure_type": "DIAGNOSTIC",
        },
        "20301012": {
            "description": "Ultrassonografia Abdominal",
            "base_price": Decimal("180.00"),
            "procedure_type": "DIAGNOSTIC",
        },
        "20401012": {
            "description": "Tomografia Computadorizada",
            "base_price": Decimal("450.00"),
            "procedure_type": "DIAGNOSTIC",
        },
        # Surgical procedures (30X)
        "30101018": {
            "description": "Procedimento Cirurgico Menor",
            "base_price": Decimal("500.00"),
            "procedure_type": "SURGICAL",
        },
        "30201018": {
            "description": "Cirurgia Geral",
            "base_price": Decimal("1500.00"),
            "procedure_type": "SURGICAL",
        },
        "30301012": {
            "description": "Cirurgia Cardiaca",
            "base_price": Decimal("8000.00"),
            "procedure_type": "SURGICAL",
        },
        # Therapeutic procedures (40X)
        "40201015": {
            "description": "Sessao de Fisioterapia",
            "base_price": Decimal("75.00"),
            "procedure_type": "THERAPEUTIC",
        },
        "40301015": {
            "description": "Sessao de Quimioterapia",
            "base_price": Decimal("2500.00"),
            "procedure_type": "THERAPEUTIC",
        },
        # Laboratory (50X)
        "50101015": {
            "description": "Hemograma Completo",
            "base_price": Decimal("25.00"),
            "procedure_type": "LABORATORY",
        },
        # Hospitalization (80X)
        "80101012": {
            "description": "Diaria de Enfermaria",
            "base_price": Decimal("350.00"),
            "procedure_type": "HOSPITALIZATION",
        },
        "80201012": {
            "description": "Diaria de UTI",
            "base_price": Decimal("1200.00"),
            "procedure_type": "HOSPITALIZATION",
        },
    }

    # Mock insurance pricing tables
    MOCK_INSURANCE_TABLES: Dict[str, str] = {
        "INS-UNIMED-001": "AMB",
        "INS-BRADESCO-001": "CBHPM",
        "INS-SULAMERICA-001": "AMB",
        "INS-SUS-001": "SUS",
    }

    # Insurance-specific price multipliers
    MOCK_INSURANCE_MULTIPLIERS: Dict[str, Decimal] = {
        "INS-UNIMED-001": Decimal("1.15"),
        "INS-BRADESCO-001": Decimal("1.25"),
        "INS-SULAMERICA-001": Decimal("1.10"),
        "INS-SUS-001": Decimal("0.60"),
    }

    def __init__(self):
        """Initialize mock pricing service."""
        self._logger = logger.bind(service="MockPricingService")

    async def get_procedure_price(
        self,
        procedure_code: str,
        insurance_id: Optional[str] = None,
    ) -> Decimal:
        """Get mock procedure price."""
        self._logger.debug(
            "Mock pricing lookup",
            procedure_code=procedure_code,
            insurance_id=insurance_id,
        )

        # Check if procedure exists in mock data
        if procedure_code in self.MOCK_PROCEDURES:
            base_price = self.MOCK_PROCEDURES[procedure_code]["base_price"]
        else:
            # Generate price based on code prefix
            base_price = self._generate_price_from_code(procedure_code)

        # Apply insurance multiplier if applicable
        if insurance_id and insurance_id in self.MOCK_INSURANCE_MULTIPLIERS:
            multiplier = self.MOCK_INSURANCE_MULTIPLIERS[insurance_id]
            return base_price * multiplier

        return base_price

    async def get_procedure_description(
        self,
        procedure_code: str,
    ) -> str:
        """Get mock procedure description."""
        if procedure_code in self.MOCK_PROCEDURES:
            return self.MOCK_PROCEDURES[procedure_code]["description"]

        # Generate description based on code prefix
        return self._generate_description_from_code(procedure_code)

    async def determine_procedure_type(
        self,
        procedure_code: str,
    ) -> str:
        """Determine procedure type from code."""
        if procedure_code in self.MOCK_PROCEDURES:
            return self.MOCK_PROCEDURES[procedure_code]["procedure_type"]

        return ProcedureType.from_code_prefix(procedure_code).value

    async def get_insurance_table(
        self,
        insurance_id: Optional[str],
    ) -> str:
        """Get mock insurance pricing table."""
        if insurance_id and insurance_id in self.MOCK_INSURANCE_TABLES:
            return self.MOCK_INSURANCE_TABLES[insurance_id]
        return "CUSTOM"

    def _generate_price_from_code(self, code: str) -> Decimal:
        """Generate a realistic price based on procedure code prefix."""
        if TUSS_PATTERN.match(code):
            prefix = code[:2]
            prefix_prices = {
                "10": Decimal("150.00"),  # Clinical
                "20": Decimal("100.00"),  # Diagnostic
                "30": Decimal("800.00"),  # Surgical
                "40": Decimal("200.00"),  # Therapeutic
                "50": Decimal("50.00"),   # Laboratory
                "60": Decimal("250.00"),  # Imaging
                "80": Decimal("500.00"),  # Hospitalization
            }
            return prefix_prices.get(prefix, Decimal("100.00"))
        elif CBHPM_PATTERN.match(code):
            return Decimal("300.00")
        return Decimal("100.00")

    def _generate_description_from_code(self, code: str) -> str:
        """Generate a description based on procedure code."""
        if TUSS_PATTERN.match(code):
            prefix = code[:2]
            prefix_descriptions = {
                "10": "Procedimento Clinico",
                "20": "Procedimento Diagnostico",
                "30": "Procedimento Cirurgico",
                "40": "Procedimento Terapeutico",
                "50": "Exame Laboratorial",
                "60": "Exame de Imagem",
                "80": "Servico Hospitalar",
            }
            return f"{prefix_descriptions.get(prefix, 'Procedimento')} {code}"
        return f"Procedimento {code}"
