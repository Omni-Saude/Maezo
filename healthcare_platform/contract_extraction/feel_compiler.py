"""FEEL expression compiler for DMN generation."""
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class FEELCondition:
    """A compiled FEEL condition for a DMN input/output entry."""
    input_name: str
    operator: str
    value: Any
    feel_expression: str
    description: str = ""
    input_entries: Optional[List[str]] = None
    output_entries: Optional[List[str]] = None


class FEELCompiler:
    """Compiles rule_definition dicts into FEEL expressions for DMN templates."""

    OPERATOR_MAP = {
        "gt": ">", "gte": ">=", "lt": "<", "lte": "<=",
        "eq": "==", "neq": "!=", "in": "in", "between": "between",
    }

    def compile(self, rule_definition: dict, template: dict) -> List[FEELCondition]:
        """Compile rule_definition into FEEL conditions (input_entries/output_entries)
        based on template schema; returns a single composite FEELCondition."""
        input_entries: List[str] = []
        output_entries: List[str] = []
        conditions: List[FEELCondition] = []

        for inp in template.get("inputs", []):
            name, ftype = inp["name"], inp.get("type", "string")
            fd = rule_definition.get(name)
            if fd is None:
                input_entries.append("")
                continue
            op, val = (fd.get("operator", "eq"), fd.get("value")) if isinstance(fd, dict) else ("eq", fd)
            feel = self._to_feel(op, val, ftype)
            input_entries.append(feel)
            conditions.append(FEELCondition(input_name=name, operator=op, value=val, feel_expression=feel))

        for out in template.get("outputs", []):
            name, otype = out["name"], out.get("type", "string")
            val = rule_definition.get(f"output_{name}", rule_definition.get(name))
            output_entries.append(self._fmt(val, otype) if val is not None else "")

        return [FEELCondition(
            input_name="composite", operator="composite", value=rule_definition,
            feel_expression="composite",
            description=rule_definition.get("description", "Rule for payer"),
            input_entries=input_entries, output_entries=output_entries,
        )]

    def _to_feel(self, operator: str, value: Any, field_type: str) -> str:
        """Convert operator + value + type into a FEEL expression string."""
        sym = self.OPERATOR_MAP.get(operator, operator)
        if operator == "between" and isinstance(value, (list, tuple)) and len(value) == 2:
            return f"[{value[0]}..{value[1]}]"
        if field_type == "string":
            return f'"{value}"'
        if field_type == "boolean":
            return str(value).lower()
        if field_type == "number":
            return f"{sym} {value}" if sym in (">", ">=", "<", "<=") else str(value)
        return f'"{value}"'

    def _fmt(self, value: Any, out_type: str) -> str:
        """Format an output value for DMN outputEntry."""
        if out_type == "string":
            return f'"{value}"'
        if out_type == "boolean":
            return str(value).lower()
        return str(value)
