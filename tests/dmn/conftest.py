"""
DMN Test Configuration and Shared Fixtures
==========================================
Shared test infrastructure for DMN rule validation.

This module provides:
- Standard enum types for DMN outputs
- MockDMNEvaluator for testing without Camunda engine
- Shared pytest fixtures for all DMN test files
- Utility functions for DMN XML parsing
"""
import pytest
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import xml.etree.ElementTree as ET
from pathlib import Path
import re


# ==============================================================================
# Standard DMN Enums
# ==============================================================================

class ResultadoEnum(str, Enum):
    """Standard DMN resultado output values"""
    PROSSEGUIR = "Prosseguir"
    BLOQUEAR = "Bloquear"
    ALERTAR = "Alertar"
    REVISAR = "Revisar"


class PrazoStatusEnum(str, Enum):
    """Standard DMN prazoStatus output values"""
    DENTRO_PRAZO = "DENTRO_PRAZO"
    ALERTA_PROXIMIDADE = "ALERTA_PROXIMIDADE"
    PRAZO_EXCEDIDO = "PRAZO_EXCEDIDO"


class RiskLevelEnum(str, Enum):
    """Risk classification levels"""
    BAIXO = "BAIXO"
    MEDIO = "MEDIO"
    ALTO = "ALTO"
    CRITICO = "CRITICO"


class TipoDocumentoEnum(str, Enum):
    """Document types for TISS compliance"""
    GUIA_SADT = "GUIA_SADT"
    GUIA_CONSULTA = "GUIA_CONSULTA"
    GUIA_INTERNACAO = "GUIA_INTERNACAO"
    GUIA_HONORARIOS = "GUIA_HONORARIOS"
    GUIA_RESUMO = "GUIA_RESUMO"


class StatusContratoEnum(str, Enum):
    """Contract status values"""
    ATIVO = "ATIVO"
    SUSPENSO = "SUSPENSO"
    CANCELADO = "CANCELADO"
    INADIMPLENTE = "INADIMPLENTE"


# ==============================================================================
# DMN Result Data Classes
# ==============================================================================

@dataclass
class DMNResult:
    """Standardized DMN evaluation result"""
    resultado: str
    observacao: str
    prazoStatus: Optional[str] = None
    diasRestantes: Optional[int] = None
    riscoDenial: Optional[str] = None
    acaoRecomendada: Optional[str] = None
    codigoGlosa: Optional[str] = None
    riscoCredito: Optional[str] = None
    valorMinimoAceitavel: Optional[float] = None
    elegivelDeducaoFiscal: Optional[bool] = None
    riscoFiscal: Optional[str] = None


@dataclass
class DMNRuleInfo:
    """Information about a DMN rule file"""
    rule_id: str
    category: str
    subcategory: str
    file_path: Path
    hit_policy: str = "FIRST"
    input_count: int = 0
    output_count: int = 0
    rule_count: int = 0


@dataclass
class DMNValidationResult:
    """Result of DMN file validation"""
    is_valid: bool
    rule_id: str
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ==============================================================================
# DMN XML Namespace Handling
# ==============================================================================

DMN_NAMESPACES = {
    "dmn": "https://www.omg.org/spec/DMN/20191111/MODEL/",
    "dmndi": "https://www.omg.org/spec/DMN/20191111/DMNDI/",
    "di": "http://www.omg.org/spec/DMN/20180521/DI/",
    "dc": "http://www.omg.org/spec/DMN/20180521/DC/",
    "modeler": "http://camunda.org/schema/modeler/1.0"
}


# ==============================================================================
# Mock DMN Evaluator
# ==============================================================================

class MockDMNEvaluator:
    """
    Mock DMN evaluator that simulates Camunda 8 decision table evaluation.
    Parses actual DMN XML files and evaluates inputs against rules.

    In production, this would be replaced with:
    - Zeebe client for Camunda 8
    - DMN-js or feel-engine for local evaluation
    """

    def __init__(self, dmn_base_path: str = None):
        if dmn_base_path:
            self.base_path = Path(dmn_base_path)
        else:
            # Default path relative to tests directory
            self.base_path = Path(__file__).parent.parent.parent / "processes" / "dmn" / "regras-administrativas-hospital"

    def evaluate(self, rule_id: str, inputs: Dict[str, Any]) -> DMNResult:
        """
        Evaluate a DMN rule with given inputs.
        Returns DMNResult with decision outcome.

        Args:
            rule_id: Rule identifier (e.g., "COMP-LGPD-001" or "Decision_COMP_LGPD_001")
            inputs: Dictionary of input variable names and values

        Returns:
            DMNResult with evaluation outcome
        """
        # Normalize rule_id (handle both formats)
        normalized_id = self._normalize_rule_id(rule_id)

        # Parse rule ID to find file path
        rule_path = self._find_rule_path(normalized_id)

        if not rule_path or not rule_path.exists():
            return DMNResult(
                resultado=ResultadoEnum.REVISAR.value,
                observacao=f"Rule file not found: {rule_id}"
            )

        # Parse and evaluate
        return self._evaluate_dmn_file(rule_path, inputs)

    def _normalize_rule_id(self, rule_id: str) -> str:
        """Normalize rule ID to standard format (e.g., COMP-LGPD-001)"""
        # Remove "Decision_" prefix if present
        if rule_id.startswith("Decision_"):
            rule_id = rule_id[9:]
        # Replace underscores with hyphens
        rule_id = rule_id.replace("_", "-")
        return rule_id.upper()

    def _find_rule_path(self, rule_id: str) -> Optional[Path]:
        """Find the DMN file path for a given rule ID"""
        # Parse rule ID format: CATEGORY-SUBCATEGORY-NNN
        parts = rule_id.split("-")
        if len(parts) >= 3:
            category = parts[0]
            subcategory = parts[1]
            # Reconstruct rule_id with proper casing
            rule_folder = "-".join(parts)

            # Try direct path
            direct_path = self.base_path / category / subcategory / rule_folder / "regra.dmn.xml"
            if direct_path.exists():
                return direct_path

        # Fallback: search recursively
        for path in self.base_path.rglob(f"{rule_id}/regra.dmn.xml"):
            return path
        for path in self.base_path.rglob(f"{rule_id.lower()}/regra.dmn.xml"):
            return path

        return None

    def _evaluate_dmn_file(self, path: Path, inputs: Dict[str, Any]) -> DMNResult:
        """Parse DMN XML and evaluate against inputs"""
        try:
            tree = ET.parse(path)
            root = tree.getroot()

            # Find decision table with namespace handling
            dt = self._find_decision_table(root)

            if dt is None:
                return DMNResult(
                    resultado=ResultadoEnum.REVISAR.value,
                    observacao="No decision table found in DMN file"
                )

            # Get hit policy (should be FIRST per standards)
            hit_policy = dt.get("hitPolicy", "FIRST")

            # Get input expressions
            input_exprs = self._extract_input_expressions(dt)

            # Get output names
            output_names = self._extract_output_names(dt)

            # Evaluate rules in order (FIRST hit policy)
            for rule in self._find_rules(dt):
                if self._rule_matches(rule, inputs, input_exprs):
                    return self._extract_outputs(rule, output_names)

            # No rule matched - return fallback
            return DMNResult(
                resultado=ResultadoEnum.REVISAR.value,
                observacao="Nenhuma regra correspondeu aos inputs fornecidos"
            )

        except ET.ParseError as e:
            return DMNResult(
                resultado=ResultadoEnum.REVISAR.value,
                observacao=f"XML parse error: {str(e)}"
            )
        except Exception as e:
            return DMNResult(
                resultado=ResultadoEnum.REVISAR.value,
                observacao=f"Error evaluating DMN: {str(e)}"
            )

    def _find_decision_table(self, root: ET.Element) -> Optional[ET.Element]:
        """Find decisionTable element with namespace handling"""
        # Try with explicit namespace
        for ns_prefix, ns_uri in DMN_NAMESPACES.items():
            if ns_prefix == "dmn":
                dt = root.find(f".//{{{ns_uri}}}decisionTable")
                if dt is not None:
                    return dt

        # Try without namespace (for files without proper namespace)
        dt = root.find(".//decisionTable")
        if dt is not None:
            return dt

        # Try with any namespace
        for elem in root.iter():
            if elem.tag.endswith("decisionTable"):
                return elem

        return None

    def _extract_input_expressions(self, dt: ET.Element) -> List[str]:
        """Extract input variable names from decision table"""
        input_exprs = []

        for inp in self._find_elements(dt, "input"):
            # Try to find inputExpression/text
            expr = self._find_element(inp, "inputExpression")
            if expr is not None:
                text = self._find_element(expr, "text")
                if text is not None and text.text:
                    input_exprs.append(text.text.strip())
                    continue

            # Fallback to label attribute
            label = inp.get("label")
            if label:
                input_exprs.append(label)

        return input_exprs

    def _extract_output_names(self, dt: ET.Element) -> List[str]:
        """Extract output variable names from decision table"""
        output_names = []

        for out in self._find_elements(dt, "output"):
            name = out.get("name")
            if name:
                output_names.append(name)
            else:
                label = out.get("label")
                if label:
                    output_names.append(label)

        # Default output names if not found
        if not output_names:
            output_names = ["resultado", "observacao", "prazoStatus",
                          "diasRestantes", "riscoDenial", "acaoRecomendada"]

        return output_names

    def _find_rules(self, dt: ET.Element) -> List[ET.Element]:
        """Find all rule elements in decision table"""
        return self._find_elements(dt, "rule")

    def _find_elements(self, parent: ET.Element, tag: str) -> List[ET.Element]:
        """Find elements with namespace handling"""
        results = []

        # Try with DMN namespace
        dmn_ns = DMN_NAMESPACES["dmn"]
        results.extend(parent.findall(f".//{{{dmn_ns}}}{tag}"))

        # Try without namespace
        results.extend(parent.findall(f".//{tag}"))

        # Try with any namespace (for non-standard files)
        for elem in parent.iter():
            if elem.tag.endswith(tag) and elem not in results:
                results.append(elem)

        return results

    def _find_element(self, parent: ET.Element, tag: str) -> Optional[ET.Element]:
        """Find single element with namespace handling"""
        elements = self._find_elements(parent, tag)
        return elements[0] if elements else None

    def _rule_matches(self, rule: ET.Element, inputs: Dict[str, Any],
                      input_exprs: List[str]) -> bool:
        """Check if a rule matches the given inputs"""
        input_entries = self._find_elements(rule, "inputEntry")

        for i, entry in enumerate(input_entries):
            if i >= len(input_exprs):
                break

            text_elem = self._find_element(entry, "text")
            if text_elem is None:
                continue

            condition = text_elem.text.strip() if text_elem.text else "-"

            # "-" means any value (wildcard)
            if condition == "-" or condition == "":
                continue

            var_name = input_exprs[i]
            if var_name not in inputs:
                # Input not provided - may or may not match depending on rule
                if condition != "-":
                    return False
                continue

            input_value = inputs[var_name]

            # Evaluate condition
            if not self._evaluate_condition(condition, input_value):
                return False

        return True

    def _evaluate_condition(self, condition: str, value: Any) -> bool:
        """Evaluate a FEEL-like condition against a value"""
        condition = condition.strip()

        # Boolean literals
        if condition.lower() == "true":
            return value is True or value == "true"
        if condition.lower() == "false":
            return value is False or value == "false"

        # Null check
        if condition.lower() == "null":
            return value is None
        if condition == "not(null)":
            return value is not None

        # String literals (quoted)
        if condition.startswith('"') and condition.endswith('"'):
            return str(value) == condition[1:-1]

        # Numeric comparisons
        if condition.startswith(">="):
            try:
                return float(value) >= float(condition[2:].strip())
            except (ValueError, TypeError):
                return False
        if condition.startswith("<="):
            try:
                return float(value) <= float(condition[2:].strip())
            except (ValueError, TypeError):
                return False
        if condition.startswith(">") and not condition.startswith(">="):
            try:
                return float(value) > float(condition[1:].strip())
            except (ValueError, TypeError):
                return False
        if condition.startswith("<") and not condition.startswith("<="):
            try:
                return float(value) < float(condition[1:].strip())
            except (ValueError, TypeError):
                return False

        # Range [a..b] or (a..b) etc.
        range_match = re.match(r'[\[\(](\d+(?:\.\d+)?)\s*\.\.\s*(\d+(?:\.\d+)?)[\]\)]', condition)
        if range_match:
            try:
                low, high = float(range_match.group(1)), float(range_match.group(2))
                val = float(value)
                # Check inclusive/exclusive brackets
                low_inclusive = condition.startswith('[')
                high_inclusive = condition.endswith(']')
                low_ok = val >= low if low_inclusive else val > low
                high_ok = val <= high if high_inclusive else val < high
                return low_ok and high_ok
            except (ValueError, TypeError):
                return False

        # List membership (value in list)
        if condition.startswith("(") and condition.endswith(")") and "," in condition:
            items = [item.strip().strip('"') for item in condition[1:-1].split(",")]
            return str(value) in items

        # Negation not(X)
        if condition.startswith("not(") and condition.endswith(")"):
            inner = condition[4:-1]
            return not self._evaluate_condition(inner, value)

        # Equality (numeric or string)
        try:
            return float(value) == float(condition)
        except (ValueError, TypeError):
            return str(value) == condition

    def _extract_outputs(self, rule: ET.Element, output_names: List[str]) -> DMNResult:
        """Extract output values from a matched rule"""
        output_entries = self._find_elements(rule, "outputEntry")

        outputs = {}

        for i, entry in enumerate(output_entries):
            if i >= len(output_names):
                break

            text_elem = self._find_element(entry, "text")
            if text_elem is not None and text_elem.text:
                value = text_elem.text.strip().strip('"')
                # Handle numeric values
                if output_names[i] in ("diasRestantes", "valorMinimoAceitavel"):
                    try:
                        value = int(value) if "." not in value else float(value)
                    except ValueError:
                        pass
                # Handle boolean values
                elif output_names[i] in ("elegivelDeducaoFiscal",):
                    value = value.lower() == "true"
                outputs[output_names[i]] = value

        return DMNResult(
            resultado=outputs.get("resultado", ResultadoEnum.REVISAR.value),
            observacao=outputs.get("observacao", ""),
            prazoStatus=outputs.get("prazoStatus"),
            diasRestantes=outputs.get("diasRestantes"),
            riscoDenial=outputs.get("riscoDenial"),
            acaoRecomendada=outputs.get("acaoRecomendada"),
            codigoGlosa=outputs.get("codigoGlosa"),
            riscoCredito=outputs.get("riscoCredito"),
            valorMinimoAceitavel=outputs.get("valorMinimoAceitavel"),
            elegivelDeducaoFiscal=outputs.get("elegivelDeducaoFiscal"),
            riscoFiscal=outputs.get("riscoFiscal"),
        )


# ==============================================================================
# DMN Validation Utilities
# ==============================================================================

class DMNValidator:
    """Validator for DMN file structure and compliance"""

    def __init__(self, base_path: str = None):
        if base_path:
            self.base_path = Path(base_path)
        else:
            self.base_path = Path(__file__).parent.parent.parent / "processes" / "dmn" / "regras-administrativas-hospital"

    def validate_rule(self, rule_id: str) -> DMNValidationResult:
        """Validate a single DMN rule file"""
        errors = []
        warnings = []

        # Find rule path
        evaluator = MockDMNEvaluator(str(self.base_path))
        rule_path = evaluator._find_rule_path(rule_id)

        if not rule_path or not rule_path.exists():
            return DMNValidationResult(
                is_valid=False,
                rule_id=rule_id,
                errors=[f"Rule file not found: {rule_id}"]
            )

        try:
            tree = ET.parse(rule_path)
            root = tree.getroot()

            # Check for decision table
            dt = evaluator._find_decision_table(root)
            if dt is None:
                errors.append("No decision table found")
            else:
                # Check hit policy
                hit_policy = dt.get("hitPolicy", "")
                if hit_policy != "FIRST":
                    warnings.append(f"Hit policy is '{hit_policy}', expected 'FIRST'")

                # Check for rules
                rules = evaluator._find_rules(dt)
                if not rules:
                    errors.append("Decision table has no rules")

                # Check outputs
                output_names = evaluator._extract_output_names(dt)
                if "resultado" not in output_names:
                    warnings.append("Missing 'resultado' output column")
                if "observacao" not in output_names:
                    warnings.append("Missing 'observacao' output column")

        except ET.ParseError as e:
            errors.append(f"XML parse error: {str(e)}")
        except Exception as e:
            errors.append(f"Validation error: {str(e)}")

        return DMNValidationResult(
            is_valid=len(errors) == 0,
            rule_id=rule_id,
            errors=errors,
            warnings=warnings
        )

    def list_all_rules(self) -> List[DMNRuleInfo]:
        """List all DMN rules in the repository"""
        rules = []

        for dmn_path in self.base_path.rglob("regra.dmn.xml"):
            try:
                # Extract rule info from path
                parts = dmn_path.relative_to(self.base_path).parts
                if len(parts) >= 3:
                    category = parts[0]
                    subcategory = parts[1]
                    rule_id = parts[2]

                    rules.append(DMNRuleInfo(
                        rule_id=rule_id,
                        category=category,
                        subcategory=subcategory,
                        file_path=dmn_path
                    ))
            except Exception:
                continue

        return sorted(rules, key=lambda r: r.rule_id)


# ==============================================================================
# Pytest Fixtures
# ==============================================================================

@pytest.fixture
def dmn_evaluator():
    """Fixture providing DMN evaluator instance"""
    base_path = Path(__file__).parent.parent.parent / "processes" / "dmn" / "regras-administrativas-hospital"
    return MockDMNEvaluator(str(base_path))


@pytest.fixture
def dmn_validator():
    """Fixture providing DMN validator instance"""
    base_path = Path(__file__).parent.parent.parent / "processes" / "dmn" / "regras-administrativas-hospital"
    return DMNValidator(str(base_path))


@pytest.fixture
def resultado_enum():
    """Fixture providing ResultadoEnum"""
    return ResultadoEnum


@pytest.fixture
def prazo_status_enum():
    """Fixture providing PrazoStatusEnum"""
    return PrazoStatusEnum


@pytest.fixture
def risk_level_enum():
    """Fixture providing RiskLevelEnum"""
    return RiskLevelEnum


@pytest.fixture
def dmn_base_path():
    """Fixture providing base path to DMN rules"""
    return Path(__file__).parent.parent.parent / "processes" / "dmn" / "regras-administrativas-hospital"


# ==============================================================================
# Test Utilities
# ==============================================================================

def assert_resultado(result: DMNResult, expected: str, msg: str = None):
    """Assert that DMN result matches expected resultado"""
    assert result.resultado == expected, (
        msg or f"Expected resultado '{expected}', got '{result.resultado}'. "
        f"Observacao: {result.observacao}"
    )


def assert_bloquear(result: DMNResult, msg: str = None):
    """Assert that DMN result is Bloquear"""
    assert_resultado(result, ResultadoEnum.BLOQUEAR.value, msg)


def assert_alertar(result: DMNResult, msg: str = None):
    """Assert that DMN result is Alertar"""
    assert_resultado(result, ResultadoEnum.ALERTAR.value, msg)


def assert_prosseguir(result: DMNResult, msg: str = None):
    """Assert that DMN result is Prosseguir"""
    assert_resultado(result, ResultadoEnum.PROSSEGUIR.value, msg)


def assert_revisar(result: DMNResult, msg: str = None):
    """Assert that DMN result is Revisar"""
    assert_resultado(result, ResultadoEnum.REVISAR.value, msg)


def make_inputs(**kwargs) -> Dict[str, Any]:
    """Helper to create input dictionaries for DMN evaluation"""
    return kwargs


# ==============================================================================
# Marker Definitions
# ==============================================================================

def pytest_configure(config):
    """Configure pytest markers for DMN tests"""
    config.addinivalue_line("markers", "tier1: Critical priority DMN rules")
    config.addinivalue_line("markers", "tier2: High priority DMN rules")
    config.addinivalue_line("markers", "tier3: Medium priority DMN rules")
    config.addinivalue_line("markers", "tier4: Low priority DMN rules")
    config.addinivalue_line("markers", "bloquear: Tests that expect Bloquear outcome")
    config.addinivalue_line("markers", "alertar: Tests that expect Alertar outcome")
    config.addinivalue_line("markers", "prosseguir: Tests that expect Prosseguir outcome")
    config.addinivalue_line("markers", "fallback: Tests for fallback/edge cases")
    config.addinivalue_line("markers", "lgpd: LGPD compliance rules")
    config.addinivalue_line("markers", "tiss: TISS compliance rules")
    config.addinivalue_line("markers", "ans: ANS regulatory rules")
