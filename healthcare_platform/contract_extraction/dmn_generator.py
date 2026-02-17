"""DMN Generator — Jinja2-based, no string-concatenated XML."""
import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from healthcare_platform.contract_extraction.feel_compiler import FEELCompiler
from healthcare_platform.contract_extraction.tenant_file_manager import TenantFileManager

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "dmn_templates"
_JSON_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Archetype → Jinja2 template file
_ARCHETYPE_MAP = {
    "PRICING": "pricing.xml.j2",
    "LOOKUP": "pricing.xml.j2",
    "BUNDLING": "bundling.xml.j2",
    "AUTHORIZATION": "authorization.xml.j2",
    "ROUTING": "routing.xml.j2",
    "WHITELIST": "whitelist.xml.j2",
}


def _sanitize_id(raw: str) -> str:
    """Sanitize a UUID or string into a valid XML id."""
    return re.sub(r'[^a-zA-Z0-9_]', '_', str(raw))


def _load_json_template(archetype: str) -> dict:
    """Load the first JSON template matching the archetype."""
    for f in _JSON_TEMPLATES_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text("utf-8"))
            if data.get("archetype") == archetype:
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return {"inputs": [], "outputs": [], "hit_policy": "FIRST"}


class DMNGenerator:
    """Generates DMN 1.3 XML from ContractRule using Jinja2 templates."""

    def __init__(
        self,
        templates_dir: Path = _TEMPLATES_DIR,
        file_manager: Optional[TenantFileManager] = None,
    ):
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=False,
            keep_trailing_newline=True,
        )
        self.feel_compiler = FEELCompiler()
        self.file_manager = file_manager or TenantFileManager()

    def generate(self, rule) -> str:
        """Generate DMN XML for a ContractRule. Returns XML string.

        Args:
            rule: ContractRule instance (or duck-typed object with .archetype, .rule_definition, etc.)
        """
        archetype_name = rule.archetype.value if hasattr(rule.archetype, 'value') else str(rule.archetype)
        template_file = _ARCHETYPE_MAP.get(archetype_name, "pricing.xml.j2")
        jinja_template = self.env.get_template(template_file)

        json_template = _load_json_template(archetype_name)
        conditions = self.feel_compiler.compile(rule.rule_definition, json_template)

        rule_id = _sanitize_id(rule.id)
        category_val = rule.category.value if hasattr(rule.category, 'value') else str(rule.category)
        rule_name = f"{category_val} Rule {rule_id}"

        xml = jinja_template.render(
            rule=rule,
            rule_id=rule_id,
            rule_name=rule_name,
            hit_policy=json_template.get("hit_policy", "FIRST"),
            inputs=json_template.get("inputs", []),
            outputs=json_template.get("outputs", []),
            conditions=conditions,
        )

        self.validate_xml(xml)
        return xml

    def generate_and_save(self, rule, tenant_id: str) -> Path:
        """Generate DMN XML and save via TenantFileManager.

        Filename includes semantic version from rule.version (MAJOR.MINOR.PATCH).
        Returns the Path where the file was written.
        """
        xml = self.generate(rule)
        category = (rule.category.value if hasattr(rule.category, 'value') else str(rule.category)).lower()
        version = getattr(rule, 'version', '1.0.0') or '1.0.0'
        filename = f"{_sanitize_id(rule.id)}_v{version}.dmn"

        path = self.file_manager.write_dmn(tenant_id, category, filename, xml)
        logger.info("DMN saved: %s (version %s)", path, version)
        self._invalidate_cache(tenant_id, category)
        return path

    def validate_xml(self, xml: str) -> bool:
        """Validate XML using xmllint. Raises subprocess.CalledProcessError on failure."""
        result = subprocess.run(
            ["xmllint", "--noout", "-"],
            input=xml.encode("utf-8"),
            capture_output=True,
        )
        if result.returncode != 0:
            logger.error("xmllint validation failed: %s", result.stderr.decode())
            raise subprocess.CalledProcessError(result.returncode, "xmllint", result.stderr)
        return True

    def _invalidate_cache(self, tenant_id: str, category: str) -> None:
        """Invalidate FederatedDMNService cache if available."""
        try:
            from healthcare_platform.shared.dmn.federation_service import get_dmn_service
            service = get_dmn_service()
            keys_to_remove = [
                k for k in service._cache
                if tenant_id in k and category in k
            ]
            for k in keys_to_remove:
                del service._cache[k]
            if keys_to_remove:
                logger.info("Invalidated %d cache entries for %s/%s", len(keys_to_remove), tenant_id, category)
        except ImportError:
            pass
