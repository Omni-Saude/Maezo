"""Tests for new OPME and DISCOUNT DMN templates."""
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from jinja2 import Environment, FileSystemLoader

from healthcare_platform.contract_extraction.models import (
    RuleArchetype,
    RuleCategory,
    RuleStatus,
)

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "dmn_templates"
_JSON_DIR = Path(__file__).resolve().parent.parent / "templates"


@pytest.fixture
def jinja_env():
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=False,
        keep_trailing_newline=True,
    )


def _render_template(jinja_env, template_name, inputs, outputs, rule_overrides=None):
    tpl = jinja_env.get_template(template_name)
    defaults = dict(
        id="test_001",
        payer_id="payer_x",
        category=RuleCategory.OPME,
        archetype=RuleArchetype.LOOKUP,
    )
    defaults.update(rule_overrides or {})
    rule = SimpleNamespace(**defaults)
    return tpl.render(
        rule=rule,
        rule_id="test_001",
        rule_name="Test Rule",
        hit_policy="FIRST",
        inputs=[SimpleNamespace(**i) for i in inputs],
        outputs=[SimpleNamespace(**o) for o in outputs],
        conditions=[],
    )


def _validate_xml(xml_str: str):
    result = subprocess.run(
        ["xmllint", "--noout", "-"],
        input=xml_str.encode("utf-8"),
        capture_output=True,
    )
    assert result.returncode == 0, f"xmllint failed: {result.stderr.decode()}"


class TestOpmeTemplate:
    INPUTS = [
        {"name": "material_code", "type": "string"},
        {"name": "supplier", "type": "string"},
        {"name": "unit_price", "type": "number"},
        {"name": "reference_table", "type": "string"},
    ]
    OUTPUTS = [
        {"name": "approved", "type": "boolean"},
        {"name": "max_price", "type": "number"},
        {"name": "requires_auth", "type": "boolean"},
        {"name": "justification", "type": "string"},
    ]

    def test_template_exists(self):
        assert (_TEMPLATES_DIR / "opme.xml.j2").exists()

    def test_renders_valid_xml(self, jinja_env):
        xml = _render_template(jinja_env, "opme.xml.j2", self.INPUTS, self.OUTPUTS)
        _validate_xml(xml)

    def test_contains_dmn_namespace(self, jinja_env):
        xml = _render_template(jinja_env, "opme.xml.j2", self.INPUTS, self.OUTPUTS)
        assert "https://www.omg.org/spec/DMN/20191111/MODEL/" in xml

    def test_contains_all_inputs(self, jinja_env):
        xml = _render_template(jinja_env, "opme.xml.j2", self.INPUTS, self.OUTPUTS)
        for inp in self.INPUTS:
            assert inp["name"] in xml

    def test_contains_all_outputs(self, jinja_env):
        xml = _render_template(jinja_env, "opme.xml.j2", self.INPUTS, self.OUTPUTS)
        for out in self.OUTPUTS:
            assert out["name"] in xml


class TestDiscountTemplate:
    INPUTS = [
        {"name": "payer_id", "type": "string"},
        {"name": "payment_days", "type": "number"},
        {"name": "monthly_volume", "type": "number"},
    ]
    OUTPUTS = [
        {"name": "discount_pct", "type": "number"},
        {"name": "effective_multiplier", "type": "number"},
        {"name": "discount_type", "type": "string"},
    ]

    def test_template_exists(self):
        assert (_TEMPLATES_DIR / "discount.xml.j2").exists()

    def test_renders_valid_xml(self, jinja_env):
        xml = _render_template(
            jinja_env, "discount.xml.j2", self.INPUTS, self.OUTPUTS,
            rule_overrides={"category": RuleCategory.DISCOUNT, "archetype": RuleArchetype.PRICING},
        )
        _validate_xml(xml)

    def test_contains_dmn_namespace(self, jinja_env):
        xml = _render_template(
            jinja_env, "discount.xml.j2", self.INPUTS, self.OUTPUTS,
            rule_overrides={"category": RuleCategory.DISCOUNT, "archetype": RuleArchetype.PRICING},
        )
        assert "https://www.omg.org/spec/DMN/20191111/MODEL/" in xml


class TestJsonTemplates:
    @pytest.mark.parametrize("filename", [
        "opme_supplier.json",
        "discount_prompt_payment.json",
        "discount_volume.json",
    ])
    def test_json_valid_and_has_required_fields(self, filename):
        path = _JSON_DIR / filename
        assert path.exists(), f"{filename} not found"
        data = json.loads(path.read_text("utf-8"))
        for field in ("name", "archetype", "description", "version", "hit_policy", "inputs", "outputs", "required_inputs"):
            assert field in data, f"Missing field: {field}"

    @pytest.mark.parametrize("filename,expected_archetype", [
        ("opme_supplier.json", "LOOKUP"),
        ("discount_prompt_payment.json", "PRICING"),
        ("discount_volume.json", "PRICING"),
    ])
    def test_archetype_matches_enum(self, filename, expected_archetype):
        data = json.loads((_JSON_DIR / filename).read_text("utf-8"))
        assert data["archetype"] == expected_archetype
        assert data["archetype"] in [e.value for e in RuleArchetype]
