"""Tests for the NLP extraction engine (ClauseParser + ContractExtractor)."""

import pytest

from healthcare_platform.contract_extraction.extraction import (
    ClauseParser,
    ContractExtractor,
)
from healthcare_platform.contract_extraction.validators import validate_rule

# ---------------------------------------------------------------------------
# Sample clauses
# ---------------------------------------------------------------------------
C1 = (
    "O procedimento 03.05.01.004-2 (Hemodialise) tera valor unitario "
    "de R$ 450,00 para o convenio SES-DF"
)
C2 = "Procedimentos acima de R$ 5.000,00 requerem autorizacao previa do supervisor"
C3 = (
    "Os procedimentos 03.05.01.004-2 e 03.05.01.003-4 quando realizados "
    "no mesmo ato serao cobrados como pacote no valor de R$ 800,00"
)
C4 = "Material OPME codigo 07.02.01.001-0 limitado a 3 unidades por procedimento"
C5 = "Desconto de 5% para pagamento em ate 30 dias"


@pytest.fixture
def parser():
    return ClauseParser()


@pytest.fixture
def extractor():
    return ContractExtractor()


# ---------------------------------------------------------------------------
# ClauseParser tests (T1-T6)
# ---------------------------------------------------------------------------

def test_parse_procedure_codes(parser):
    assert parser.parse_procedure_codes(C1) == ["03.05.01.004-2"]


def test_parse_currency_simple(parser):
    assert parser.parse_currency("R$ 450,00") == [450.0]


def test_parse_currency_thousands(parser):
    assert parser.parse_currency("R$ 5.000,00") == [5000.0]


def test_parse_percentages(parser):
    assert parser.parse_percentages(C5) == [5.0]


def test_parse_quantities(parser):
    assert parser.parse_quantities(C4) == [3]


def test_parse_payer_ids(parser):
    assert parser.parse_payer_ids(C1) == ["SES-DF"]


# ---------------------------------------------------------------------------
# ContractExtractor tests (T7-T12)
# ---------------------------------------------------------------------------

def test_extract_pricing(extractor):
    rules = extractor.extract_rules(C1, "t1", "SES-DF")
    assert len(rules) >= 1
    rule = rules[0]
    assert rule["archetype"] == "PRICING"
    assert rule["category"] == "PRICING"
    assert rule["rule_definition"]["procedure_code"] == "03.05.01.004-2"


def test_extract_authorization(extractor):
    rules = extractor.extract_rules(C2, "t1", "SES-DF")
    assert len(rules) >= 1
    assert rules[0]["archetype"] == "AUTHORIZATION"


def test_extract_opme(extractor):
    rules = extractor.extract_rules(C4, "t1", "SES-DF")
    assert len(rules) >= 1
    assert rules[0]["archetype"] == "OPME"


def test_extract_discount(extractor):
    rules = extractor.extract_rules(C5, "t1", "SES-DF")
    assert len(rules) >= 1
    assert rules[0]["archetype"] == "DISCOUNT"


def test_pricing_validates_with_zero_errors(extractor):
    rules = extractor.extract_rules(C1, "t1", "SES-DF")
    rule_def = rules[0]["rule_definition"]
    errors = validate_rule(rule_def, "PRICING")
    assert errors == []


def test_no_match_returns_empty(extractor):
    rules = extractor.extract_rules(
        "Uma frase qualquer sem padrão reconhecido", "t1", "SES-DF"
    )
    assert rules == []
