"""
NLP Rule Extraction Engine for Brazilian Healthcare Contracts.

Provides parsing and extraction of business rules from plain-text
Brazilian healthcare contract clauses into structured rule_definition
dicts that conform to the JSON template schemas.
"""

from .clause_parser import ClauseParser
from .extractor import ContractExtractor

__all__ = ["ClauseParser", "ContractExtractor"]
