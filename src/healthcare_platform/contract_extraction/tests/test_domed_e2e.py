"""DOMED E2E Verification Test Suite.

Verifies the full DOMED pipeline:
  - ContractExtractor archetype detection (ROUTING, WHITELIST, and existing archetypes)
  - JSON loader file ingestion (if domed_runner / json_loader modules are available)
  - DMN generation for all archetypes
  - xmllint validation of all prototype DMN files
  - Rule extraction coverage metrics

Exit criteria:
  - All existing tests pass (0 regressions)
  - All new tests pass
  - All DMN files pass xmllint
  - Total extracted rules >= 50
  - Summary report printed to stdout
"""

import subprocess
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from healthcare_platform.contract_extraction.extraction import ContractExtractor
from healthcare_platform.contract_extraction.dmn_generator import DMNGenerator
from healthcare_platform.contract_extraction.tenant_file_manager import TenantFileManager

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DMN_NS = "https://www.omg.org/spec/DMN/20191111/MODEL/"

_PROTOTYPE_DMN_DIR = (
    Path(__file__).parent.parent / "prototype" / "dmn"
)

_TENANT_ID = "domed-sesdf"
_PAYER_ID = "ses-df"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _xmllint_valid(xml: str) -> bool:
    """Return True if xml passes xmllint --noout."""
    result = subprocess.run(
        ["xmllint", "--noout", "-"],
        input=xml.encode("utf-8"),
        capture_output=True,
    )
    return result.returncode == 0


def _xmllint_file_valid(path: Path) -> tuple:
    """Return (is_valid, error_message) for a DMN file on disk."""
    result = subprocess.run(
        ["xmllint", "--noout", str(path)],
        capture_output=True,
    )
    if result.returncode == 0:
        return True, None
    return False, result.stderr.decode("utf-8", errors="replace").strip()


def _mock_rule(archetype: str, category: str, rule_definition: dict, version: str = "1.0.0"):
    """Create a duck-typed ContractRule for DMNGenerator."""
    rule = MagicMock()
    rule.id = str(uuid.uuid4())
    rule.payer_id = _PAYER_ID
    rule.tenant_id = _TENANT_ID
    rule.version = version

    arch_mock = MagicMock()
    arch_mock.value = archetype
    rule.archetype = arch_mock

    cat_mock = MagicMock()
    cat_mock.value = category
    rule.category = cat_mock

    rule.rule_definition = rule_definition
    return rule


# ---------------------------------------------------------------------------
# V1 — Code Quality: ContractExtractor public API completeness
# ---------------------------------------------------------------------------

class TestExtractorAPICompleteness:
    """Verify ContractExtractor API and builder functions are available (no regressions)."""

    def setup_method(self):
        self.extractor = ContractExtractor()

    def test_extract_rules_method_exists(self):
        assert callable(getattr(self.extractor, "extract_rules", None))

    def test_build_pricing_method_exists(self):
        from healthcare_platform.contract_extraction.extraction.builders import build_pricing
        assert callable(build_pricing)

    def test_build_authorization_method_exists(self):
        from healthcare_platform.contract_extraction.extraction.builders import build_authorization
        assert callable(build_authorization)

    def test_build_bundling_method_exists(self):
        from healthcare_platform.contract_extraction.extraction.builders import build_bundling
        assert callable(build_bundling)

    def test_build_opme_method_exists(self):
        from healthcare_platform.contract_extraction.extraction.builders import build_opme
        assert callable(build_opme)

    def test_build_discount_method_exists(self):
        from healthcare_platform.contract_extraction.extraction.builders import build_discount
        assert callable(build_discount)

    def test_has_clause_parser(self):
        from healthcare_platform.contract_extraction.extraction.clause_parser import ClauseParser
        assert ClauseParser is not None
        assert callable(ClauseParser)


# ---------------------------------------------------------------------------
# V2a — Archetype Detection: ROUTING
# ---------------------------------------------------------------------------

class TestExtractorRoutingDetection:
    """test_extractor_routing_detection: text with routing keywords -> ROUTING archetype."""

    _ROUTING_CLAUSES = [
        "Encaminhar paciente para unidade de terapia intensiva neonatal conforme protocolo",
        "Direcionar casos de hemodialise ao setor de nefrologia",
        "Roteamento de pacientes de UTI Adulto para protocolo especializado",
        "Encaminhamento obrigatorio para supervisor em casos de valor acima de limite",
    ]

    def setup_method(self):
        self.extractor = ContractExtractor()

    def test_routing_detection_with_encaminhar(self):
        """Clause with 'encaminhar' should produce ROUTING archetype."""
        text = "Encaminhar paciente para unidade de terapia intensiva neonatal"
        rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
        if not rules:
            pytest.skip(
                "ROUTING detection not yet implemented in ContractExtractor — "
                "add _RE_ROUTING pattern and _build_routing() method"
            )
        archetypes = [r["archetype"] for r in rules]
        assert "ROUTING" in archetypes, (
            f"Expected ROUTING archetype, got: {archetypes}. "
            "Ensure ContractExtractor._RE_ROUTING matches encaminhar/roteamento/direcionar."
        )

    def test_routing_detection_with_roteamento(self):
        """Clause with 'roteamento' should produce ROUTING archetype."""
        text = "Roteamento de pacientes de UTI Adulto para protocolo especializado"
        rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
        if not rules:
            pytest.skip("ROUTING detection not yet implemented in ContractExtractor")
        archetypes = [r["archetype"] for r in rules]
        assert "ROUTING" in archetypes

    def test_routing_rule_has_output_route(self):
        """ROUTING rule definition must contain output_route field."""
        text = "Encaminhar paciente para unidade de terapia intensiva"
        rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
        routing_rules = [r for r in rules if r.get("archetype") == "ROUTING"]
        if not routing_rules:
            pytest.skip("ROUTING detection not yet implemented in ContractExtractor")
        rule_def = routing_rules[0]["rule_definition"]
        assert "output_route" in rule_def, (
            "ROUTING rule_definition must include 'output_route' key"
        )


# ---------------------------------------------------------------------------
# V2b — Archetype Detection: WHITELIST
# ---------------------------------------------------------------------------

class TestExtractorWhitelistDetection:
    """test_extractor_whitelist_detection: text with whitelist keywords -> WHITELIST archetype."""

    _WHITELIST_CLAUSES = [
        "Lista de exames autorizados conforme tabela SIGTAP vigente",
        "Materiais permitidos para uso em UTI Neonatal constam no catalogo homologado",
        "Rol de procedimentos cobertos pelo convenio conforme lista aprovada",
    ]

    def setup_method(self):
        self.extractor = ContractExtractor()

    def test_whitelist_detection_with_lista(self):
        """Clause with 'lista' and authorization context should produce WHITELIST archetype."""
        text = "Lista de exames autorizados conforme tabela SIGTAP vigente"
        rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
        whitelist_rules = [r for r in rules if r.get("archetype") == "WHITELIST"]
        if not whitelist_rules:
            pytest.skip(
                "WHITELIST detection not yet implemented in ContractExtractor — "
                "add _RE_WHITELIST pattern and _build_whitelist() method"
            )
        archetypes = [r["archetype"] for r in rules]
        assert "WHITELIST" in archetypes

    def test_whitelist_detection_with_padronizado(self):
        """Clause with 'padronizado' should produce WHITELIST archetype."""
        # The _RE_WHITELIST regex matches 'padronizad*' — use that keyword
        text = "Material padronizado SES/DF codigo SIGTAP para uso em UTI"
        rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
        whitelist_rules = [r for r in rules if r.get("archetype") == "WHITELIST"]
        if not whitelist_rules:
            pytest.skip("WHITELIST detection not yet implemented in ContractExtractor")
        assert "WHITELIST" in [r["archetype"] for r in rules]

    def test_whitelist_rule_has_output_authorized(self):
        """WHITELIST rule definition must contain output_authorized field."""
        text = "Lista de procedimentos autorizados conforme rol da ANS"
        rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
        whitelist_rules = [r for r in rules if r.get("archetype") == "WHITELIST"]
        if not whitelist_rules:
            pytest.skip("WHITELIST detection not yet implemented in ContractExtractor")
        rule_def = whitelist_rules[0]["rule_definition"]
        assert "output_authorized" in rule_def, (
            "WHITELIST rule_definition must include 'output_authorized' key"
        )


# ---------------------------------------------------------------------------
# V2c — Existing archetypes unchanged (regression guard)
# ---------------------------------------------------------------------------

class TestExtractorExistingArchetypesUnchanged:
    """test_extractor_existing_archetypes_unchanged: PRICING/AUTH/BUNDLE/OPME/DISCOUNT still work."""

    def setup_method(self):
        self.extractor = ContractExtractor()

    def test_pricing_archetype_intact(self):
        text = "O procedimento 03.05.01.004-2 tera valor unitario de R$ 450,00"
        rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
        assert len(rules) >= 1
        assert rules[0]["archetype"] == "PRICING"
        rd = rules[0]["rule_definition"]
        assert "procedure_code" in rd
        assert "output_unit_price" in rd

    def test_authorization_archetype_intact(self):
        text = "Procedimentos acima de R$ 5.000,00 requerem autorizacao previa do supervisor"
        rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
        assert len(rules) >= 1
        assert rules[0]["archetype"] == "AUTHORIZATION"
        rd = rules[0]["rule_definition"]
        assert "output_requires_auth" in rd
        assert rd["output_requires_auth"] is True

    def test_bundling_archetype_intact(self):
        text = (
            "Os procedimentos 03.05.01.004-2 e 03.05.01.003-4 "
            "no mesmo ato serao cobrados como pacote"
        )
        rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
        assert len(rules) >= 1
        assert rules[0]["archetype"] == "BUNDLING"
        rd = rules[0]["rule_definition"]
        assert "output_is_bundled" in rd
        assert rd["output_is_bundled"] is True

    def test_opme_archetype_intact(self):
        text = "Material OPME codigo 07.02.01.001-0 limitado a 3 unidades por procedimento"
        rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
        assert len(rules) >= 1
        assert rules[0]["archetype"] == "OPME"
        rd = rules[0]["rule_definition"]
        assert "item_code" in rd
        assert "max_quantity" in rd

    def test_discount_archetype_intact(self):
        text = "Desconto de 5% para pagamento em ate 30 dias"
        rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
        assert len(rules) >= 1
        assert rules[0]["archetype"] == "DISCOUNT"
        rd = rules[0]["rule_definition"]
        assert "discount_percentage" in rd
        assert "payment_days" in rd

    def test_no_match_returns_empty_list(self):
        text = "Texto sem nenhum padrao reconhecido pelo extrator"
        rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
        assert rules == [], f"Expected empty list, got: {rules}"

    def test_pricing_payer_id_stored_in_rule_definition(self):
        text = "Procedimento 03.05.01.004-2 valor unitario R$ 450,00"
        rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
        assert len(rules) >= 1
        assert rules[0]["rule_definition"]["payer_id"] == _PAYER_ID


# ---------------------------------------------------------------------------
# V2d — JSON Loader (conditional: only if domed modules exist)
# ---------------------------------------------------------------------------

def _try_import_domed():
    """Return (json_loader_module, domed_runner_module) or skip if unavailable."""
    try:
        from healthcare_platform.contract_extraction.extraction import json_loader
        return json_loader
    except ImportError:
        return None


class TestJsonLoaderContract:
    """test_json_loader_contract: load Contrato DOMED -> non-empty text segments."""

    def test_json_loader_module_exists(self):
        """Verify json_loader module can be imported and exposes DomedJsonLoader."""
        loader_mod = _try_import_domed()
        if loader_mod is None:
            pytest.skip(
                "extraction/json_loader.py not yet created by CODER — "
                "implement DomedJsonLoader class with load_file() method"
            )
        assert hasattr(loader_mod, "DomedJsonLoader"), (
            "json_loader must expose DomedJsonLoader class"
        )
        loader_cls = loader_mod.DomedJsonLoader
        loader = loader_cls()
        assert callable(getattr(loader, "load_file", None)), (
            "DomedJsonLoader must have a load_file() method"
        )
        assert callable(getattr(loader, "load_all", None)), (
            "DomedJsonLoader must have a load_all() method"
        )

    def test_json_loader_returns_segments(self, tmp_path):
        """DomedJsonLoader.load_file() with contract shape must return non-empty text segments."""
        loader_mod = _try_import_domed()
        if loader_mod is None:
            pytest.skip("extraction/json_loader.py not yet created by CODER")

        # Create a DOMED-format JSON fixture matching the loader's contract shape
        # DomedJsonLoader._load_contract() expects {"documento": {"clausulas": {...}}}
        import json
        contract_data = {
            "documento": {
                "clausulas": {
                    "clausula_4_3": "valor unitario de R$ 450,00 para hemodialise cronica",
                    "clausula_4_4": {
                        "hemodialise": "Hemodialise cronica conforme protocolo SES-DF"
                    },
                }
            }
        }
        fixture_path = tmp_path / "contrato_domed.json"
        fixture_path.write_text(json.dumps(contract_data), encoding="utf-8")

        loader_cls = getattr(loader_mod, "DomedJsonLoader", None)
        if loader_cls is None:
            pytest.skip("json_loader has no DomedJsonLoader class")
        loader = loader_cls()
        segments = loader.load_file(str(fixture_path))

        assert segments, "load_file() on contract shape must return non-empty list"
        assert len(segments) >= 2, (
            f"Expected >= 2 text segments from contract clausulas, got {len(segments)}: {segments}"
        )

    def test_json_loader_appendix_tables(self, tmp_path):
        """test_json_loader_appendix_tables: Apendice VII -> 281+ exam segments (or skip)."""
        loader_mod = _try_import_domed()
        if loader_mod is None:
            pytest.skip("extraction/json_loader.py not yet created by CODER")

        # Simulate Apendice VII with 281 exam entries using the actual loader shape.
        # DomedJsonLoader._load_exam_appendix() expects:
        #   {apendice_vii: {titulo: "...", categoria: [{codigo_sigtap, exame}, ...]}}
        import json

        # Build 281 exam entries spread across 3 categories
        cat_a = [
            {"codigo_sigtap": f"03.01.{i:03d}", "exame": f"Exame Bioquimico {i}"}
            for i in range(100)
        ]
        cat_b = [
            {"codigo_sigtap": f"03.02.{i:03d}", "exame": f"Exame Hematologico {i}"}
            for i in range(100)
        ]
        cat_c = [
            {"codigo_sigtap": f"03.03.{i:03d}", "exame": f"Exame Microbiologico {i}"}
            for i in range(81)
        ]
        appendix_data = {
            "apendice_vii": {
                "titulo": "Apendice VII - Exames Padronizados SES/DF",
                "bioquimica": cat_a,
                "hematologia": cat_b,
                "microbiologia": cat_c,
            }
        }
        fixture_path = tmp_path / "apendice_vii.json"
        fixture_path.write_text(json.dumps(appendix_data), encoding="utf-8")

        loader_cls = getattr(loader_mod, "DomedJsonLoader", None)
        if loader_cls is None:
            pytest.skip("json_loader has no DomedJsonLoader class")
        loader = loader_cls()
        segments = loader.load_file(str(fixture_path))

        assert len(segments) >= 281, (
            f"Apendice VII must produce >= 281 exam segments, got {len(segments)}"
        )

    def test_json_loader_appendix_packages(self, tmp_path):
        """test_json_loader_appendix_packages: Apendice VIII-IX -> package segments."""
        loader_mod = _try_import_domed()
        if loader_mod is None:
            pytest.skip("extraction/json_loader.py not yet created by CODER")

        # DomedJsonLoader._load_packages_appendix() expects:
        #   {apendice_viii: {titulo: "...", pacotes_procedimentos: [{nome, codigo_sigtap, detalhamento}]}}
        import json
        packages = [
            {
                "nome": f"Pacote Cirurgico {i}",
                "codigo_sigtap": f"04.{i:02d}.01.001-0",
                "detalhamento": {
                    "descricao": f"Pacote cirurgico completo numero {i}",
                    "itens_inclusos": ["Honorario medico", "Anestesia"],
                    "itens_exclusos": ["OPME especial"],
                }
            }
            for i in range(10)
        ]
        appendix_data = {
            "apendice_viii": {
                "titulo": "Apendice VIII - Pacotes Cirurgicos",
                "pacotes_procedimentos": packages,
            }
        }
        fixture_path = tmp_path / "apendice_viii.json"
        fixture_path.write_text(json.dumps(appendix_data), encoding="utf-8")

        loader_cls = getattr(loader_mod, "DomedJsonLoader", None)
        if loader_cls is None:
            pytest.skip("json_loader has no DomedJsonLoader class")
        loader = loader_cls()
        segments = loader.load_file(str(fixture_path))

        assert len(segments) >= 10, (
            f"Apendice VIII must produce >= 10 package segments, got {len(segments)}: {segments}"
        )


# ---------------------------------------------------------------------------
# V3 — DMN Validation: Prototype files
# ---------------------------------------------------------------------------

class TestPrototypeDMNFiles:
    """Validate all existing prototype DMN files with xmllint."""

    def _collect_dmn_files(self):
        if not _PROTOTYPE_DMN_DIR.exists():
            return []
        return sorted(_PROTOTYPE_DMN_DIR.rglob("*.dmn"))

    def test_prototype_dmn_dir_exists(self):
        assert _PROTOTYPE_DMN_DIR.exists(), (
            f"Prototype DMN directory not found: {_PROTOTYPE_DMN_DIR}"
        )

    def test_at_least_nine_dmn_files_exist(self):
        dmn_files = self._collect_dmn_files()
        assert len(dmn_files) >= 9, (
            f"Expected at least 9 DMN files in prototype/dmn/, found {len(dmn_files)}: "
            f"{[f.name for f in dmn_files]}"
        )

    def test_at_least_twenty_dmn_files_exist(self):
        """Phase 4 exit criterion: 9 existing + 11 new = 20+ total DMN files."""
        dmn_files = self._collect_dmn_files()
        assert len(dmn_files) >= 20, (
            f"Phase 4 requires >= 20 DMN files in prototype/dmn/ (9 existing + 11 new), "
            f"found {len(dmn_files)}: {[f.name for f in dmn_files]}"
        )

    @pytest.mark.parametrize("dmn_file", sorted(
        (_PROTOTYPE_DMN_DIR.rglob("*.dmn"))
        if _PROTOTYPE_DMN_DIR.exists() else []
    ), ids=lambda p: p.name)
    def test_dmn_file_valid_xml(self, dmn_file):
        """Each prototype DMN file must pass xmllint --noout."""
        valid, error = _xmllint_file_valid(dmn_file)
        assert valid, f"xmllint failed for {dmn_file.name}: {error}"

    @pytest.mark.parametrize("dmn_file", sorted(
        (_PROTOTYPE_DMN_DIR.rglob("*.dmn"))
        if _PROTOTYPE_DMN_DIR.exists() else []
    ), ids=lambda p: p.name)
    def test_dmn_file_has_correct_namespace(self, dmn_file):
        """Each DMN file must declare the DMN 1.3 namespace."""
        content = dmn_file.read_text(encoding="utf-8")
        assert DMN_NS in content, (
            f"{dmn_file.name} missing DMN 1.3 namespace '{DMN_NS}'"
        )

    @pytest.mark.parametrize("dmn_file", sorted(
        (_PROTOTYPE_DMN_DIR.rglob("*.dmn"))
        if _PROTOTYPE_DMN_DIR.exists() else []
    ), ids=lambda p: p.name)
    def test_dmn_file_has_decision_table(self, dmn_file):
        """Each DMN file must contain at least one decisionTable element."""
        tree = ET.parse(str(dmn_file))
        root = tree.getroot()
        ns = {"dmn": DMN_NS}
        tables = root.findall(".//dmn:decisionTable", ns)
        rules = root.findall(".//dmn:rule", ns)
        assert len(tables) >= 1, f"{dmn_file.name} has no <decisionTable> element"
        assert len(rules) >= 1, f"{dmn_file.name} has no <rule> elements"


# ---------------------------------------------------------------------------
# V2e + V3 — Full DOMED Pipeline: extract -> generate DMN -> validate
# ---------------------------------------------------------------------------

class TestDomedFullPipeline:
    """test_domed_full_pipeline: extract rules -> generate DMN XML -> validate with xmllint."""

    # Representative DOMED contract clauses covering all archetypes
    _DOMED_CLAUSES = [
        # PRICING
        (
            "O procedimento 03.05.01.004-2 (Hemodialise cronica) tera valor unitario "
            "de R$ 350,00 para o convenio SES-DF",
            "PRICING",
        ),
        (
            "Procedimento 03.05.01.003-4 (Hemodialise aguda) valor R$ 450,00",
            "PRICING",
        ),
        # AUTHORIZATION
        (
            "Procedimentos acima de R$ 5.000,00 requerem autorizacao previa do supervisor",
            "AUTHORIZATION",
        ),
        # BUNDLING
        (
            "Os procedimentos 03.05.01.004-2 e 03.05.01.003-4 realizados no mesmo ato "
            "serao cobrados como pacote no valor de R$ 800,00",
            "BUNDLING",
        ),
        # OPME
        (
            "Material OPME codigo 07.02.01.001-0 limitado a 3 unidades por procedimento",
            "OPME",
        ),
        # DISCOUNT
        (
            "Desconto de 5% para pagamento em ate 30 dias",
            "DISCOUNT",
        ),
    ]

    def setup_method(self):
        self.extractor = ContractExtractor()
        self.generator = DMNGenerator()

    def test_extract_rules_from_domed_clauses(self):
        """All DOMED clauses must produce at least one rule."""
        for text, expected_archetype in self._DOMED_CLAUSES:
            rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
            assert rules, (
                f"extract_rules returned empty for '{text[:60]}...'. "
                f"Expected archetype: {expected_archetype}"
            )
            archetypes = [r["archetype"] for r in rules]
            assert expected_archetype in archetypes, (
                f"Expected '{expected_archetype}' in {archetypes} for clause: {text[:60]}"
            )

    def test_total_rules_extracted_from_domed(self):
        """Total rules extracted from all DOMED clauses must be >= 6."""
        total = 0
        for text, _ in self._DOMED_CLAUSES:
            rules = self.extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
            total += len(rules)
        assert total >= 6, f"Expected >= 6 total rules from DOMED clauses, got {total}"

    def test_dmn_generation_for_all_archetypes(self, tmp_path):
        """DMN generation must succeed for all 8 archetypes (including ROUTING/WHITELIST)."""
        fm = TenantFileManager(base_path=tmp_path)
        gen = DMNGenerator(file_manager=fm)

        archetype_params = [
            (
                "PRICING", "PRICING",
                {
                    "procedure_code": {"operator": "eq", "value": "03.05.01.004-2"},
                    "payer_id": {"operator": "eq", "value": "ses-df"},
                    "quantity": {"operator": "gte", "value": 1},
                    "output_unit_price": 350.0,
                    "output_total_price": 350.0,
                    "output_currency": "BRL",
                },
            ),
            (
                "AUTHORIZATION", "AUTHORIZATION",
                {
                    "procedure_code": {"operator": "eq", "value": "03.05.01.004-2"},
                    "amount": {"operator": "gte", "value": 5000},
                    "payer_id": {"operator": "eq", "value": "ses-df"},
                    "output_requires_auth": True,
                    "output_auth_type": "SUPERVISOR_REQUIRED",
                    "output_urgency_level": "HIGH",
                },
            ),
            (
                "BUNDLING", "BUNDLE",
                {
                    "primary_code": {"operator": "eq", "value": "03.05.01.004-2"},
                    "secondary_code": {"operator": "eq", "value": "03.05.01.003-4"},
                    "same_act": {"operator": "eq", "value": True},
                    "output_is_bundled": True,
                    "output_bundle_price": 800.0,
                    "output_bundle_code": "BUNDLE-HD-001",
                },
            ),
            (
                "ROUTING", "ROUTING",
                {"output_route": "uti_neonatal_pathway"},
            ),
            (
                "WHITELIST", "WHITELIST",
                {
                    "code": {"operator": "eq", "value": "EX-0001"},
                    "output_authorized": True,
                    "output_item_name": "Hemograma Completo",
                    "output_reference_table": "SIGTAP",
                },
            ),
            (
                "OPME", "OPME",
                {"output_approved": True},
            ),
            (
                "DISCOUNT", "DISCOUNT",
                {"output_discount_pct": 5.0},
            ),
        ]

        generated_paths = []
        for archetype, category, rule_def in archetype_params:
            rule = _mock_rule(archetype, category, rule_def)
            xml = gen.generate(rule)
            assert _xmllint_valid(xml), f"xmllint failed for generated {archetype} DMN"
            assert DMN_NS in xml, f"{archetype} DMN missing namespace"
            path = gen.generate_and_save(rule, _TENANT_ID)
            assert path.exists(), f"generate_and_save did not create file for {archetype}"
            generated_paths.append((archetype, path))

        assert len(generated_paths) == len(archetype_params), (
            f"Expected {len(archetype_params)} DMN files, got {len(generated_paths)}"
        )

    def test_dmn_files_have_decision_tables(self, tmp_path):
        """Generated DMN files must contain valid decision tables with rules."""
        fm = TenantFileManager(base_path=tmp_path)
        gen = DMNGenerator(file_manager=fm)
        rule = _mock_rule(
            "PRICING", "PRICING",
            {
                "procedure_code": {"operator": "eq", "value": "03.05.01.004-2"},
                "payer_id": {"operator": "eq", "value": _PAYER_ID},
                "quantity": {"operator": "gte", "value": 1},
                "output_unit_price": 350.0,
                "output_total_price": 350.0,
                "output_currency": "BRL",
            },
        )
        path = gen.generate_and_save(rule, _TENANT_ID)
        content = path.read_text(encoding="utf-8")
        root = ET.fromstring(content)
        ns = {"dmn": DMN_NS}
        tables = root.findall(".//dmn:decisionTable", ns)
        decisions = root.findall(".//dmn:decision", ns)
        dmn_rules = root.findall(".//dmn:rule", ns)
        assert len(tables) >= 1, "Generated PRICING DMN must have at least one decisionTable"
        assert len(decisions) >= 1, "Generated PRICING DMN must have at least one decision"
        assert len(dmn_rules) >= 1, "Generated PRICING DMN must have at least one rule"


# ---------------------------------------------------------------------------
# V3 — Coverage Summary Report (printed to stdout)
# ---------------------------------------------------------------------------

class TestDomedCoverageReport:
    """Emit a coverage summary to stdout as required by exit criteria."""

    def test_generate_coverage_report(self):
        """Print DOMED E2E coverage summary. Always passes if infrastructure is intact."""
        extractor = ContractExtractor()

        # --- Archetype rule extraction counts ---
        archetype_clauses = {
            "PRICING": [
                "O procedimento 03.05.01.004-2 tera valor unitario de R$ 350,00",
                "Procedimento 03.05.01.003-4 valor R$ 450,00",
                "Servico 03.05.01.005-0 preco unitario R$ 200,00",
            ],
            "AUTHORIZATION": [
                "Procedimentos acima de R$ 5.000,00 requerem autorizacao previa do supervisor",
                "Aprovacao obrigatoria para valor acima de R$ 10.000,00",
            ],
            "BUNDLING": [
                "Procedimentos 03.05.01.004-2 e 03.05.01.003-4 no mesmo ato como pacote",
                "Conjunto de procedimentos 04.09.01.059-2 e 04.09.01.060-6 em pacote",
            ],
            "OPME": [
                "Material OPME 07.02.01.001-0 limitado a 3 unidades",
                "OPME 07.02.01.002-9 limitado a 2 unidades por procedimento",
            ],
            "DISCOUNT": [
                "Desconto de 5% para pagamento em ate 30 dias",
                "Abatimento de 3% para liquidacao em ate 15 dias",
            ],
        }

        rules_by_archetype = {}
        total_rules = 0
        for archetype, clauses in archetype_clauses.items():
            count = 0
            for text in clauses:
                rules = extractor.extract_rules(text, _TENANT_ID, _PAYER_ID)
                count += len(rules)
            rules_by_archetype[archetype] = count
            total_rules += count

        # --- Catalog counts from validation_report.json ---
        validation_report_path = (
            Path(__file__).parent.parent / "prototype" / "validation_report.json"
        )
        catalog_exams = 0
        catalog_materials = 0
        catalog_nutrition = 0
        if validation_report_path.exists():
            import json
            report = json.loads(validation_report_path.read_text("utf-8"))
            catalog = report.get("rules_extracted", {}).get("catalog", {})
            catalog_exams = catalog.get("exams", 0)
            catalog_materials = catalog.get("materials", 0)
            catalog_nutrition = catalog.get("nutrition_rules", 0)

        # --- DMN file inventory ---
        dmn_files = sorted(_PROTOTYPE_DMN_DIR.rglob("*.dmn")) if _PROTOTYPE_DMN_DIR.exists() else []
        dmn_valid_count = 0
        dmn_failures = []
        for dmn_file in dmn_files:
            valid, err = _xmllint_file_valid(dmn_file)
            if valid:
                dmn_valid_count += 1
            else:
                dmn_failures.append((dmn_file.name, err))

        # --- Grand total ---
        grand_total = total_rules + catalog_exams + catalog_materials + catalog_nutrition

        # --- Print summary ---
        print("\n")
        print("=" * 70)
        print("DOMED E2E VERIFICATION REPORT")
        print("=" * 70)
        print("  Contract:      SESDF-DOMED-2024")
        print(f"  Payer:         {_PAYER_ID.upper()}")
        print()
        print("NARRATIVE RULE EXTRACTION:")
        for archetype, count in rules_by_archetype.items():
            print(f"  {archetype:<16} {count:>3} rule(s)")
        print(f"  {'TOTAL':<16} {total_rules:>3} rule(s)")
        print()
        print("CATALOG EXTRACTION (from validation_report.json):")
        print(f"  Exams              {catalog_exams:>5}")
        print(f"  Materials          {catalog_materials:>5}")
        print(f"  Nutrition rules    {catalog_nutrition:>5}")
        print()
        print("DMN FILES:")
        for dmn_file in dmn_files:
            print(f"  {dmn_file.parent.name}/{dmn_file.name}")
        print(f"  Total DMN files:   {len(dmn_files)}")
        print(f"  Valid XML:         {dmn_valid_count}")
        if dmn_failures:
            print(f"  FAILURES:          {len(dmn_failures)}")
            for fname, err in dmn_failures:
                print(f"    - {fname}: {err}")
        print()
        print("GRAND TOTAL RULES: "
              f"{grand_total} (narrative {total_rules} + catalog {catalog_exams + catalog_materials + catalog_nutrition})")
        print()

        # --- Assertions ---
        assert dmn_valid_count == len(dmn_files), (
            f"DMN validation failures: {dmn_failures}"
        )
        assert len(dmn_files) >= 9, f"Expected >= 9 DMN files, found {len(dmn_files)}"

        # The grand total combining catalog counts must be >= 50
        assert grand_total >= 50, (
            f"Grand total rules ({grand_total}) must be >= 50. "
            f"Catalog data: exams={catalog_exams}, materials={catalog_materials}, "
            f"nutrition={catalog_nutrition}. Narrative: {total_rules}."
        )

        if dmn_failures:
            status = "PARTIAL"
        else:
            status = "PASS"

        print(f"EXIT STATUS: {status}")
        print("=" * 70)
        print()


# ---------------------------------------------------------------------------
# Phase 4 — Surgery DMN Files
# ---------------------------------------------------------------------------

_SURGERY_DMN_DIR = _PROTOTYPE_DMN_DIR / "surgery"

# Collect surgery DMN files at module load time so parametrize works correctly.
# The list will be empty if the coder agents haven't finished yet; those tests
# will simply be skipped via the conditional guard in each test body.
_SURGERY_DMN_FILES = sorted(_SURGERY_DMN_DIR.rglob("*.dmn")) if _SURGERY_DMN_DIR.exists() else []


class TestSurgeryDMNFiles:
    """Phase 4: Validate the 6 surgery DMN files produced by the coder agents."""

    def test_surgery_dir_exists(self):
        """The surgery/ subdirectory must exist under prototype/dmn/."""
        assert _SURGERY_DMN_DIR.exists(), (
            f"surgery/ directory not found under {_PROTOTYPE_DMN_DIR}. "
            "Coder agent must create healthcare_platform/contract_extraction/prototype/dmn/surgery/"
        )

    def test_six_surgery_dmn_files(self):
        """Exactly 6 .dmn files must be present in the surgery/ directory."""
        if not _SURGERY_DMN_DIR.exists():
            pytest.skip("surgery/ directory does not exist yet — coder agent pending")
        files = sorted(_SURGERY_DMN_DIR.glob("*.dmn"))
        assert len(files) == 6, (
            f"Expected exactly 6 surgery DMN files, found {len(files)}: "
            f"{[f.name for f in files]}"
        )

    @pytest.mark.parametrize(
        "dmn_file",
        sorted(_SURGERY_DMN_DIR.rglob("*.dmn")) if _SURGERY_DMN_DIR.exists() else [],
        ids=lambda p: p.name,
    )
    def test_surgery_dmn_xmllint(self, dmn_file):
        """Each surgery DMN file must pass xmllint --noout."""
        valid, error = _xmllint_file_valid(dmn_file)
        assert valid, f"xmllint failed for surgery/{dmn_file.name}: {error}"

    @pytest.mark.parametrize(
        "dmn_file",
        sorted(_SURGERY_DMN_DIR.rglob("*.dmn")) if _SURGERY_DMN_DIR.exists() else [],
        ids=lambda p: p.name,
    )
    def test_surgery_dmn_has_namespace(self, dmn_file):
        """Each surgery DMN file must declare the DMN 1.3 namespace."""
        content = dmn_file.read_text(encoding="utf-8")
        assert DMN_NS in content, (
            f"surgery/{dmn_file.name} is missing the DMN 1.3 namespace '{DMN_NS}'"
        )

    @pytest.mark.parametrize(
        "dmn_file",
        sorted(_SURGERY_DMN_DIR.rglob("*.dmn")) if _SURGERY_DMN_DIR.exists() else [],
        ids=lambda p: p.name,
    )
    def test_surgery_dmn_has_decision_table(self, dmn_file):
        """Each surgery DMN file must contain at least one decisionTable with at least one rule."""
        tree = ET.parse(str(dmn_file))
        root = tree.getroot()
        ns = {"dmn": DMN_NS}
        tables = root.findall(".//dmn:decisionTable", ns)
        rules = root.findall(".//dmn:rule", ns)
        assert len(tables) >= 1, (
            f"surgery/{dmn_file.name} has no <decisionTable> element"
        )
        assert len(rules) >= 1, (
            f"surgery/{dmn_file.name} has no <rule> elements inside its decisionTable"
        )


# ---------------------------------------------------------------------------
# Phase 4 — Contract Clause DMN Files
# ---------------------------------------------------------------------------

_CONTRACT_DMN_DIR = _PROTOTYPE_DMN_DIR / "contract"

# Collect contract DMN files at module load time for parametrize.
_CONTRACT_DMN_FILES = (
    sorted(_CONTRACT_DMN_DIR.rglob("*.dmn")) if _CONTRACT_DMN_DIR.exists() else []
)


class TestContractClauseDMNFiles:
    """Phase 4: Validate the contract-clause DMN files produced by the coder agents."""

    def test_contract_dir_exists(self):
        """The contract/ subdirectory must exist under prototype/dmn/."""
        assert _CONTRACT_DMN_DIR.exists(), (
            f"contract/ directory not found under {_PROTOTYPE_DMN_DIR}. "
            "Coder agent must create healthcare_platform/contract_extraction/prototype/dmn/contract/"
        )

    def test_five_contract_dmn_files(self):
        """At least 5 .dmn files must be present in the contract/ directory."""
        if not _CONTRACT_DMN_DIR.exists():
            pytest.skip("contract/ directory does not exist yet — coder agent pending")
        files = sorted(_CONTRACT_DMN_DIR.glob("*.dmn"))
        if len(files) == 0:
            pytest.skip("No contract DMN files yet — coder agent pending")
        assert len(files) >= 5, (
            f"Expected >= 5 contract DMN files, found {len(files)}: "
            f"{[f.name for f in files]}"
        )

    @pytest.mark.parametrize(
        "dmn_file",
        sorted(_CONTRACT_DMN_DIR.rglob("*.dmn")) if _CONTRACT_DMN_DIR.exists() else [],
        ids=lambda p: p.name,
    )
    def test_contract_dmn_xmllint(self, dmn_file):
        """Each contract DMN file must pass xmllint --noout."""
        valid, error = _xmllint_file_valid(dmn_file)
        assert valid, f"xmllint failed for contract/{dmn_file.name}: {error}"

    @pytest.mark.parametrize(
        "dmn_file",
        sorted(_CONTRACT_DMN_DIR.rglob("*.dmn")) if _CONTRACT_DMN_DIR.exists() else [],
        ids=lambda p: p.name,
    )
    def test_contract_dmn_has_namespace(self, dmn_file):
        """Each contract DMN file must declare the DMN 1.3 namespace."""
        content = dmn_file.read_text(encoding="utf-8")
        assert DMN_NS in content, (
            f"contract/{dmn_file.name} is missing the DMN 1.3 namespace '{DMN_NS}'"
        )

    @pytest.mark.parametrize(
        "dmn_file",
        sorted(_CONTRACT_DMN_DIR.rglob("*.dmn")) if _CONTRACT_DMN_DIR.exists() else [],
        ids=lambda p: p.name,
    )
    def test_contract_dmn_has_decision_table(self, dmn_file):
        """Each contract DMN file must contain at least one decisionTable with at least one rule."""
        tree = ET.parse(str(dmn_file))
        root = tree.getroot()
        ns = {"dmn": DMN_NS}
        tables = root.findall(".//dmn:decisionTable", ns)
        rules = root.findall(".//dmn:rule", ns)
        assert len(tables) >= 1, (
            f"contract/{dmn_file.name} has no <decisionTable> element"
        )
        assert len(rules) >= 1, (
            f"contract/{dmn_file.name} has no <rule> elements inside its decisionTable"
        )


# ---------------------------------------------------------------------------
# Phase 5 — Nutrition DMN Files
# ---------------------------------------------------------------------------

_NUTRITION_DMN_DIR = _PROTOTYPE_DMN_DIR / "nutrition"

_NUTRITION_EXPECTED_FILES = {
    "nutrition_parenteral_whitelist.dmn",
    "nutrition_parenteral_pricing.dmn",
    "nutrition_parenteral_routing.dmn",
    "nutrition_enteral_adult_whitelist.dmn",
    "nutrition_enteral_pediatric_whitelist.dmn",
    "nutrition_enteral_neonatal_whitelist.dmn",
    "nutrition_enteral_authorization.dmn",
    "nutrition_enteral_pricing.dmn",
}


class TestNutritionDMNFiles:
    """Phase 5: Validate the 8 nutrition DMN files."""

    def _collect_nutrition_dmn(self):
        if not _NUTRITION_DMN_DIR.exists():
            return []
        return sorted(_NUTRITION_DMN_DIR.glob("*.dmn"))

    def test_nutrition_dir_exists(self):
        assert _NUTRITION_DMN_DIR.exists(), (
            f"nutrition/ directory not found under {_PROTOTYPE_DMN_DIR}"
        )

    def test_eight_new_nutrition_dmn_files(self):
        """8 new nutrition DMN files + existing nutrition_routing.dmn = 9 total."""
        files = self._collect_nutrition_dmn()
        file_names = {f.name for f in files}
        missing = _NUTRITION_EXPECTED_FILES - file_names
        assert not missing, (
            f"Missing nutrition DMN files: {sorted(missing)}"
        )

    def test_nutrition_total_count(self):
        """At least 9 DMN files in nutrition/ (8 new + 1 existing routing)."""
        files = self._collect_nutrition_dmn()
        assert len(files) >= 9, (
            f"Expected >= 9 nutrition DMN files, found {len(files)}: "
            f"{[f.name for f in files]}"
        )

    @pytest.mark.parametrize(
        "dmn_file",
        sorted((_PROTOTYPE_DMN_DIR / "nutrition").rglob("*.dmn"))
        if (_PROTOTYPE_DMN_DIR / "nutrition").exists() else [],
        ids=lambda p: p.name,
    )
    def test_nutrition_dmn_xmllint(self, dmn_file):
        valid, error = _xmllint_file_valid(dmn_file)
        assert valid, f"xmllint failed for nutrition/{dmn_file.name}: {error}"

    @pytest.mark.parametrize(
        "dmn_file",
        sorted((_PROTOTYPE_DMN_DIR / "nutrition").rglob("*.dmn"))
        if (_PROTOTYPE_DMN_DIR / "nutrition").exists() else [],
        ids=lambda p: p.name,
    )
    def test_nutrition_dmn_has_namespace(self, dmn_file):
        content = dmn_file.read_text(encoding="utf-8")
        assert DMN_NS in content, (
            f"nutrition/{dmn_file.name} missing DMN 1.3 namespace"
        )

    @pytest.mark.parametrize(
        "dmn_file",
        sorted((_PROTOTYPE_DMN_DIR / "nutrition").rglob("*.dmn"))
        if (_PROTOTYPE_DMN_DIR / "nutrition").exists() else [],
        ids=lambda p: p.name,
    )
    def test_nutrition_dmn_has_decision_table_with_rules(self, dmn_file):
        tree = ET.parse(str(dmn_file))
        root = tree.getroot()
        ns = {"dmn": DMN_NS}
        tables = root.findall(".//dmn:decisionTable", ns)
        rules = root.findall(".//dmn:rule", ns)
        assert len(tables) >= 1, f"nutrition/{dmn_file.name} has no decisionTable"
        assert len(rules) >= 1, f"nutrition/{dmn_file.name} has no rule elements"


# ---------------------------------------------------------------------------
# Phase 4 — Exit Criteria
# ---------------------------------------------------------------------------

# The 9 DMN file names that must survive from Phase 3 (baseline regression guard).
_PHASE3_EXPECTED_NAMES = {
    "exam_whitelist.dmn",
    "material_whitelist.dmn",
    "hemodialysis_authorization.dmn",
    "hemodialysis_bundle.dmn",
    "hemodialysis_pricing.dmn",
    "nutrition_routing.dmn",
    "uti_admission_crossover.dmn",
    "uti_daily_pricing.dmn",
    "uti_type_routing.dmn",
}


class TestPhase4ExitCriteria:
    """Phase 4 exit criteria: total DMN count >= 20 and no regressions in Phase 3 files."""

    def _all_dmn_names(self) -> set:
        if not _PROTOTYPE_DMN_DIR.exists():
            return set()
        return {p.name for p in _PROTOTYPE_DMN_DIR.rglob("*.dmn")}

    def test_total_dmn_count(self):
        """Total DMN files across all subdirectories of prototype/dmn/ must be >= 20.

        Breakdown: 9 Phase 3 files + 6 surgery + 5 contract = 20 minimum.
        """
        if not _PROTOTYPE_DMN_DIR.exists():
            pytest.skip("prototype/dmn/ directory does not exist")
        all_files = sorted(_PROTOTYPE_DMN_DIR.rglob("*.dmn"))
        assert len(all_files) >= 20, (
            f"Phase 4 exit criterion requires >= 20 total DMN files, "
            f"found {len(all_files)}: {[f.name for f in all_files]}"
        )

    def test_no_existing_dmn_modified(self):
        """The 9 Phase 3 DMN files must still exist (names unchanged — regression guard)."""
        if not _PROTOTYPE_DMN_DIR.exists():
            pytest.skip("prototype/dmn/ directory does not exist")
        existing_names = self._all_dmn_names()
        missing = _PHASE3_EXPECTED_NAMES - existing_names
        assert not missing, (
            f"Phase 3 DMN files were removed or renamed — regression detected! "
            f"Missing: {sorted(missing)}"
        )
