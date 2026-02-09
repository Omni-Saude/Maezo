"""
TISS (Troca de Informacoes em Saude Suplementar) Services.

Provides XML generation and validation for Brazilian healthcare claims
according to ANS TISS 4.0 specification.
"""

from revenue_cycle.services.tiss.tiss_xml_generator import (
    TissXmlGenerator,
    TissValidationResult,
    ValidationResult,
    ClaimData,
    TissXmlGenerationError,
)

__all__ = [
    "TissXmlGenerator",
    "TissValidationResult",
    "ValidationResult",
    "ClaimData",
    "TissXmlGenerationError",
]
