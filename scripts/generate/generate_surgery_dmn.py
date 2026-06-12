"""Generate 6 surgery DMN files for apendice_x (Procedimentos Cirurgicos Urgencia/Emergencia).

Usage (from project root):
    python3.11 scripts/generate_surgery_dmn.py

Produces:
  healthcare_platform/contract_extraction/prototype/dmn/surgery/
    surgery_bundle_type1.dmn   -- BUNDLING: abdominal urgency procedures (Group 1)
    surgery_bundle_type2.dmn   -- BUNDLING: thoracic urgency procedures (Group 2)
    surgery_bundle_type3.dmn   -- BUNDLING: vascular urgency procedures (Group 3)
    surgery_authorization.dmn  -- AUTHORIZATION: surgery eligibility rules
    surgery_opme.dmn           -- OPME: material exclusivity rules
    surgery_pricing.dmn        -- PRICING: surgery package pricing

All files are generated using DMNGenerator + _MockContractRule (no DB required).
"""

import dataclasses
import enum
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Project root resolution
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent  # Healthcare-Orchest-CIB7/
sys.path.insert(0, str(_PROJECT_ROOT))

_OUTPUT_DIR = _PROJECT_ROOT / "healthcare_platform/contract_extraction/prototype/dmn/surgery"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Inline mock types (mirrors domed_runner._MockContractRule exactly)
# ---------------------------------------------------------------------------

class _MockCategory(enum.Enum):
    PRICING = "PRICING"
    BUNDLE = "BUNDLE"
    OPME = "OPME"
    AUTHORIZATION = "AUTHORIZATION"
    DISCOUNT = "DISCOUNT"


class _MockArchetype(enum.Enum):
    LOOKUP = "LOOKUP"
    ROUTING = "ROUTING"
    PRICING = "PRICING"
    AUTHORIZATION = "AUTHORIZATION"
    BUNDLING = "BUNDLING"
    WHITELIST = "WHITELIST"
    OPME = "OPME"
    DISCOUNT = "DISCOUNT"


@dataclasses.dataclass
class _MockContractRule:
    """Duck-typed ContractRule for DMNGenerator — no SQLAlchemy/DB required."""
    id: str
    payer_id: str
    archetype: _MockArchetype
    category: _MockCategory
    rule_definition: dict
    version: str = "1.0.0"
    tenant_id: str = "sesdf"


# ---------------------------------------------------------------------------
# Surgery rule definitions (from apendice_x data)
# ---------------------------------------------------------------------------
#
# apendice_x contains 37 SIGTAP codes for urgency/emergency surgical procedures.
# We group them into 3 bundles by clinical domain:
#
# Group 1 — Abdominal/Hepatobiliary (BUNDLING type1)
#   Codes: 407030018 ANASTOMOSE BILEO-DIGESTIVA, 407020039 APENDICECTOMIA,
#          407030026 COLECISTECTOMIA, 407030042 COLECISTOSTOMIA,
#          407030050 COLEDOCOPLASTIA, 407030069 COLEDOCOTOMIA,
#          407030085 COLOCACAO DE PROTESE BILIAR, 407030093 DILATACAO PERCUTANEA,
#          407030107 DRENAGEM BILIAR PERCUTANEA EXTERNA,
#          407030115 DRENAGEM BILIAR PERCUTANEA INTERNA,
#          407040013 DRENAGEM DE ABSCESSO PELVICO,
#          407040030 DRENAGEM DE HEMATOMA/ABSCESSO PRE-PERITONEAL,
#          407030123 ESPLENECTOMIA, 407030131 HEPATECTOMIA PARCIAL,
#          407030140 HEPATORRAFIA, 407030158 HEPATORRAFIA COMPLEXA,
#          407030166 HEPATOTOMIA E DRENAGEM, 407040161 LAPAROTOMIA EXPLORADORA,
#          407040196 PARACENTESE ABDOMINAL
#
# Group 2 — Thoracic (BUNDLING type2)
#   Codes: 41202003 MEDIASTINOTOMIA, 412040115 RETIRADA DE CORPO ESTRANHO,
#          412040166 TORACOSTOMIA, 412040174 TORACOTOMIA EXPLORADORA,
#          407040048 HERNIOPLASTIA DIAFRAGMATICA VIA ABDOMINAL,
#          407040056 HERNIOPLASTIA DIAFRAGMATICA VIA TORACICA
#
# Group 3 — Vascular/Interventional (BUNDLING type3)
#   Codes: 211020010 CATETERISMO CARDIACO, 211020028 CATETERISMO CARDIACO PEDIATRIA,
#          406020124 EMBOLECTOMIA ARTERIAL, 406020167 FASCIOTOMIA,
#          406040192 EMBOLIZACAO ARTERIAL, 406040265 IMPLANTACAO SHUNT TIPS,
#          406020590 TROMBECTOMIA, 416040195 QUIMIOEMBOLIZACAO,
#          407040064 HERNIOPLASTIA EPIGASTRICA, 407040080 HERNIOPLASTIA INCISIONAL,
#          407040099 HERNIOPLASTIA INGUINAL BILATERAL, 407040129 HERNIOPLASTIA UMBILICAL
#
# ---------------------------------------------------------------------------

SURGERY_RULES = [
    # -- 1. BUNDLING type1: Abdominal / Hepatobiliary -------------------------
    {
        "filename": "surgery_bundle_type1.dmn",
        "rule": _MockContractRule(
            id="surgery_bundle_abdominal",
            payer_id="SES-DF",
            archetype=_MockArchetype.BUNDLING,
            category=_MockCategory.BUNDLE,
            rule_definition={
                "primary_code": {"operator": "eq", "value": "407030026"},  # COLECISTECTOMIA
                "secondary_code": {"operator": "eq", "value": "407030042"},  # COLECISTOSTOMIA
                "same_act": {"operator": "eq", "value": False},
                "output_is_bundled": True,
                "output_bundle_price": 0,
                "output_bundle_code": "BUNDLE_ABDOMINAL_URG",
                "description": (
                    "Apendice X - Cirurgias Abdominais Urgencia/Emergencia SES-DF: "
                    "COLECISTECTOMIA (407030026) primaria; procedimentos biliares e hepaticos "
                    "complementares nao sao cobertos em duplicidade quando realizados no mesmo ato. "
                    "Inclui: APENDICECTOMIA (407020039), COLECISTECTOMIA (407030026), "
                    "COLECISTOSTOMIA (407030042), COLEDOCOPLASTIA (407030050), "
                    "COLEDOCOTOMIA (407030069), ESPLENECTOMIA (407030123), "
                    "HEPATORRAFIA (407030140), LAPAROTOMIA EXPLORADORA (407040161), "
                    "PARACENTESE ABDOMINAL (407040196)."
                ),
            },
        ),
    },

    # -- 2. BUNDLING type2: Thoracic ------------------------------------------
    {
        "filename": "surgery_bundle_type2.dmn",
        "rule": _MockContractRule(
            id="surgery_bundle_thoracic",
            payer_id="SES-DF",
            archetype=_MockArchetype.BUNDLING,
            category=_MockCategory.BUNDLE,
            rule_definition={
                "primary_code": {"operator": "eq", "value": "412040166"},  # TORACOSTOMIA
                "secondary_code": {"operator": "eq", "value": "412040174"},  # TORACOTOMIA
                "same_act": {"operator": "eq", "value": False},
                "output_is_bundled": True,
                "output_bundle_price": 0,
                "output_bundle_code": "BUNDLE_THORACIC_URG",
                "description": (
                    "Apendice X - Cirurgias Toracicas Urgencia/Emergencia SES-DF: "
                    "TORACOSTOMIA COM DRENAGEM PLEURAL FECHADA (412040166) primaria; "
                    "procedimentos toracicos complementares nao faturados em duplicidade. "
                    "Inclui: MEDIASTINOTOMIA P/DRENAGEM (41202003), "
                    "RETIRADA DE CORPO ESTRANHO PAREDE TORACICA (412040115), "
                    "TORACOSTOMIA COM DRENAGEM PLEURAL FECHADA (412040166), "
                    "TORACOTOMIA EXPLORADORA (412040174), "
                    "HERNIOPLASTIA DIAFRAGMATICA VIA ABDOMINAL (407040048), "
                    "HERNIOPLASTIA DIAFRAGMATICA VIA TORACICA (407040056)."
                ),
            },
        ),
    },

    # -- 3. BUNDLING type3: Vascular / Interventional -------------------------
    {
        "filename": "surgery_bundle_type3.dmn",
        "rule": _MockContractRule(
            id="surgery_bundle_vascular",
            payer_id="SES-DF",
            archetype=_MockArchetype.BUNDLING,
            category=_MockCategory.BUNDLE,
            rule_definition={
                "primary_code": {"operator": "eq", "value": "406020124"},  # EMBOLECTOMIA ARTERIAL
                "secondary_code": {"operator": "eq", "value": "406020590"},  # TROMBECTOMIA
                "same_act": {"operator": "eq", "value": False},
                "output_is_bundled": True,
                "output_bundle_price": 0,
                "output_bundle_code": "BUNDLE_VASCULAR_URG",
                "description": (
                    "Apendice X - Cirurgias Vasculares/Intervencional Urgencia/Emergencia SES-DF: "
                    "EMBOLECTOMIA ARTERIAL (406020124) primaria; procedimentos vasculares "
                    "e de hemodinamica nao duplicados. "
                    "Inclui: CATETERISMO CARDIACO (211020010), "
                    "CATETERISMO CARDIACO PEDIATRIA (211020028), "
                    "EMBOLECTOMIA ARTERIAL (406020124), "
                    "EMBOLIZACAO ARTERIAL DE HEMORRAGIA DIGESTIVA (406040192), "
                    "FASCIOTOMIA P/DESCOMPRESSAO (406020167), "
                    "IMPLANTACAO SHUNT INTRA-HEPATICO PORTO-SISTEMICO TIPS (406040265), "
                    "QUIMIOEMBOLIZACAO DE CARCINOMA HEPATICO (416040195), "
                    "TROMBECTOMIA DO SISTEMA VENOSO (406020590), "
                    "HERNIOPLASTIA EPIGASTRICA (407040064), "
                    "HERNIOPLASTIA INCISIONAL (407040080), "
                    "HERNIOPLASTIA INGUINAL BILATERAL (407040099), "
                    "HERNIOPLASTIA UMBILICAL (407040129)."
                ),
            },
        ),
    },

    # -- 4. AUTHORIZATION: surgery eligibility --------------------------------
    {
        "filename": "surgery_authorization.dmn",
        "rule": _MockContractRule(
            id="surgery_authorization",
            payer_id="SES-DF",
            archetype=_MockArchetype.AUTHORIZATION,
            category=_MockCategory.AUTHORIZATION,
            rule_definition={
                "procedure_code": {"operator": "eq", "value": "407040161"},  # LAPAROTOMIA EXPLORADORA
                "amount": {"operator": "gte", "value": 0},
                "payer_id": {"operator": "eq", "value": "SES-DF"},
                "output_requires_auth": True,
                "output_auth_type": "URGENCIA_EMERGENCIA",
                "output_urgency_level": "ALTA",
                "description": (
                    "Apendice X - Autorizacao para Procedimentos Cirurgicos Urgencia/Emergencia SES-DF: "
                    "Todos os 37 procedimentos do Apendice X requerem autorizacao retroativa em ate 24h. "
                    "Codigos SIGTAP cobertos: "
                    "407030018 ANASTOMOSE BILEO-DIGESTIVA, "
                    "407020039 APENDICECTOMIA, "
                    "211020010 CATETERISMO CARDIACO, "
                    "211020028 CATETERISMO CARDIACO PEDIATRIA, "
                    "407030026 COLECISTECTOMIA, "
                    "407030042 COLECISTOSTOMIA, "
                    "407030050 COLEDOCOPLASTIA, "
                    "407030069 COLEDOCOTOMIA C/OUS/COLECISTECTOMIA, "
                    "407030085 COLOCACAO DE PROTESE BILIAR, "
                    "407030093 DILATACAO PERCUTANEA ESTENOSES BILIARES, "
                    "407030107 DRENAGEM BILIAR PERCUTANEA EXTERNA, "
                    "407030115 DRENAGEM BILIAR PERCUTANEA INTERNA, "
                    "407040013 DRENAGEM ABSCESSO PELVICO, "
                    "406020124 EMBOLECTOMIA ARTERIAL, "
                    "407030123 ESPLENECTOMIA, "
                    "407040161 LAPAROTOMIA EXPLORADORA, "
                    "407040196 PARACENTESE ABDOMINAL, "
                    "412040166 TORACOSTOMIA COM DRENAGEM PLEURAL FECHADA, "
                    "406020590 TROMBECTOMIA DO SISTEMA VENOSO. "
                    "Nivel de urgencia: ALTA para todos. Tipo auth: URGENCIA_EMERGENCIA."
                ),
            },
        ),
    },

    # -- 5. OPME: material exclusivity for surgery ----------------------------
    {
        "filename": "surgery_opme.dmn",
        "rule": _MockContractRule(
            id="surgery_opme",
            payer_id="SES-DF",
            archetype=_MockArchetype.OPME,
            category=_MockCategory.OPME,
            rule_definition={
                "description": (
                    "Apendice X - Materiais OPME Cirurgia Urgencia/Emergencia SES-DF: "
                    "Materiais e proteses cirurgicas utilizados nos procedimentos do Apendice X. "
                    "Exclusividade por procedimento — proteses biliares (407030085) "
                    "aprovadas conforme tabela SES-DF; stent nao recoberto para TIPS (406040265) "
                    "aprovado com laudo tecnico; materiais consumiveis de urgencia incluidos "
                    "no pacote cirurgico sem cobranca separada (linhas, campos, suturas). "
                    "OPMEs especiais (malhas, grampeadores) cobertos mediante autorizacao previa "
                    "com codigo SIGTAP correto: "
                    "407030085 PROTESE BILIAR, "
                    "406040265 STENT INTRA-HEPATICO PORTO-SISTEMICO NAO RECOBERTO, "
                    "407040080 HERNIOPLASTIA INCISIONAL (tela de polipropileno aprovada), "
                    "407040099 HERNIOPLASTIA INGUINAL BILATERAL (tela de polipropileno aprovada)."
                ),
            },
        ),
    },

    # -- 6. PRICING: surgery package pricing ----------------------------------
    {
        "filename": "surgery_pricing.dmn",
        "rule": _MockContractRule(
            id="surgery_pricing",
            payer_id="SES-DF",
            archetype=_MockArchetype.PRICING,
            category=_MockCategory.PRICING,
            rule_definition={
                "procedure_code": {"operator": "eq", "value": "407030026"},  # COLECISTECTOMIA
                "payer_id": {"operator": "eq", "value": "SES-DF"},
                "quantity": {"operator": "gte", "value": 1},
                "output_unit_price": 0,
                "output_total_price": 0,
                "output_currency": "BRL",
                "description": (
                    "Apendice X - Precificacao Cirurgias Urgencia/Emergencia SES-DF: "
                    "Todos os procedimentos sao faturados pelo valor SIGTAP vigente da SES-DF. "
                    "Exemplos de codigos e valores de referencia (tabela SES-DF): "
                    "407020039 APENDICECTOMIA - valor SIGTAP, "
                    "407030026 COLECISTECTOMIA - valor SIGTAP, "
                    "211020010 CATETERISMO CARDIACO - valor SIGTAP, "
                    "406020124 EMBOLECTOMIA ARTERIAL - valor SIGTAP, "
                    "407040161 LAPAROTOMIA EXPLORADORA - valor SIGTAP, "
                    "412040166 TORACOSTOMIA COM DRENAGEM PLEURAL FECHADA - valor SIGTAP, "
                    "406020590 TROMBECTOMIA DO SISTEMA VENOSO - valor SIGTAP, "
                    "416040195 QUIMIOEMBOLIZACAO DE CARCINOMA HEPATICO - valor SIGTAP. "
                    "Moeda: BRL. Hospitais privados contratados recebem conforme contrato CIB7. "
                    "Nao ha adicional de urgencia sobre o valor SIGTAP base."
                ),
            },
        ),
    },
]


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def main() -> int:
    from healthcare_platform.contract_extraction.dmn_generator import DMNGenerator

    generator = DMNGenerator()
    generated = []
    failed = []

    print(f"Output directory: {_OUTPUT_DIR}")
    print(f"Generating {len(SURGERY_RULES)} surgery DMN files...\n")

    for spec in SURGERY_RULES:
        filename = spec["filename"]
        rule = spec["rule"]
        out_path = _OUTPUT_DIR / filename

        try:
            xml = generator.generate(rule)
            out_path.write_text(xml, encoding="utf-8")
            size = out_path.stat().st_size
            print(f"  [OK] {filename} ({size} bytes) — archetype={rule.archetype.value}")
            generated.append(out_path)
        except Exception as exc:
            print(f"  [FAIL] {filename} — {exc}")
            failed.append(filename)

    print(f"\nGenerated: {len(generated)}  Failed: {len(failed)}")

    if failed:
        print(f"Failures: {failed}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
