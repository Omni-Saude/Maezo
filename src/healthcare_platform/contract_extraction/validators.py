import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

_TEMPLATES_DIR = Path(__file__).parent / "templates"

_TYPE_MAP = {
    "string": str,
    "number": (int, float),
    "boolean": bool,
}


def _load_templates() -> dict:
    templates: dict = {}
    if not _TEMPLATES_DIR.exists():
        return templates
    for json_file in _TEMPLATES_DIR.glob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        archetype = data.get("archetype", "")
        if not archetype:
            continue
        if archetype not in templates:
            templates[archetype] = []
        templates[archetype].append(data)
    return templates


LOADED_TEMPLATES: dict = _load_templates()


def _get_schema_for_archetype(archetype: str) -> Optional[dict]:
    templates = LOADED_TEMPLATES.get(archetype, [])
    return templates[0] if templates else None


@dataclass
class ValidationError:
    field: str
    message: str
    code: str


def validate_completeness(
    rule_definition: dict, archetype: str
) -> List[ValidationError]:
    schema = _get_schema_for_archetype(archetype)
    if schema is None:
        return [
            ValidationError(
                field="archetype",
                message=f"No template found for archetype '{archetype}'",
                code="UNKNOWN_ARCHETYPE",
            )
        ]
    errors: List[ValidationError] = []
    for field in schema.get("required_inputs", []):
        if field not in rule_definition:
            errors.append(
                ValidationError(
                    field=field,
                    message=f"Required field '{field}' is missing from rule definition",
                    code="MISSING_REQUIRED_FIELD",
                )
            )
    return errors


def validate_types(
    rule_definition: dict, archetype: str
) -> List[ValidationError]:
    schema = _get_schema_for_archetype(archetype)
    if schema is None:
        return []
    errors: List[ValidationError] = []
    for input_spec in schema.get("inputs", []):
        field = input_spec.get("name", "")
        declared_type = input_spec.get("type", "")
        if not field or field not in rule_definition:
            continue
        expected = _TYPE_MAP.get(declared_type)
        if expected is None:
            continue
        value = rule_definition[field]
        if not isinstance(value, expected):
            actual_type = type(value).__name__
            errors.append(
                ValidationError(
                    field=field,
                    message=(
                        f"Field '{field}' expects type '{declared_type}' "
                        f"but received '{actual_type}'"
                    ),
                    code="INVALID_TYPE",
                )
            )
    return errors


def validate_rule(
    rule_definition: dict, archetype: str
) -> List[ValidationError]:
    errors = validate_completeness(rule_definition, archetype)
    errors += validate_types(rule_definition, archetype)
    return errors
