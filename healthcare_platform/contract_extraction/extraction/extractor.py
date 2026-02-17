from __future__ import annotations

"""Contract rule extractor -- classifies clauses and dispatches to builders."""

import re
from typing import Dict, List

from .builders import (
    build_authorization,
    build_bundling,
    build_discount,
    build_glosa,
    build_indicator,
    build_opme,
    build_penalty,
    build_pricing,
    build_routing,
    build_sla,
    build_whitelist,
)


class ContractExtractor:
    """Extract structured rules from Brazilian healthcare contract text.

    This class is a thin dispatcher: it classifies the clause via regex
    signals and delegates all rule construction to the builders subpackage.
    All output value logic is owned by DMN templates, not by this class.
    """

    _RE_OPME = re.compile(r"OPME|material|pr[oó]tese|[oó]rtese", re.IGNORECASE)
    _RE_DISCOUNT = re.compile(r"desconto|abatimento", re.IGNORECASE)
    _RE_AUTH = re.compile(
        r"autorizac|autorizaç|aprovac|aprovaç|supervisor", re.IGNORECASE
    )
    _RE_BUNDLE = re.compile(r"pacote|mesmo ato|conjunto", re.IGNORECASE)
    _RE_PRICING = re.compile(r"valor|preco|preço|unitario|unitário", re.IGNORECASE)

    # Routing signals: age bands, bed types, directions, crossover admissions
    _RE_ROUTING = re.compile(
        r"faixa\s+et[aá]ria|direcion|encaminh|rota(?:mento)?|tipo\s+de\s+leito"
        r"|crossover|admiss[aã]o|leito\s+(?:adulto|pedi[aá]trico|neonatal)"
        r"|UTI\s+(?:adulto|pedi[aá]trica|neonatal)",
        re.IGNORECASE,
    )

    # Whitelist signals: standardised lists, appendices, SES/BR codes, SIGTAP tables
    _RE_WHITELIST = re.compile(
        r"padronizad|lista\s+(?:de\s+)?(?:exames?|materiais?|procedimentos?)"
        r"|ap[eê]ndice.{0,30}(?:exame|material|procedimento)"
        r"|c[oó]digo.{0,20}(?:BR|SES|SIGTAP)"
        r"|tabela.{0,20}(?:SES|SIGTAP|AMB)",
        re.IGNORECASE,
    )

    # P1 archetypes: glosa, quality indicators, SLA, penalties
    _RE_GLOSA = re.compile(
        r"glosa|glos[aá]vel|impugna[cç][aã]o|recurso\s+de\s+glosa"
        r"|motivo\s+(?:de\s+)?glosa|c[oó]digo\s+(?:de\s+)?glosa",
        re.IGNORECASE,
    )
    _RE_INDICATOR = re.compile(
        r"indicador|IMR|[ií]ndice\s+de\s+(?:mortalidade|infec[cç][aã]o|qualidade)"
        r"|PAV|IPCSL|evento\s+adverso|densidade\s+de\s+incid[eê]ncia",
        re.IGNORECASE,
    )
    _RE_SLA = re.compile(
        r"prazo|SLA|n[ií]vel\s+de\s+servi[cç]o|tempestividade"
        r"|obriga[cç][aã]o\s+contratual|at[eé]\s+\d+\s+dias\s+(?:[uú]teis|corridos)",
        re.IGNORECASE,
    )
    _RE_PENALTY = re.compile(
        r"penalidade|multa|san[cç][aã]o|infra[cç][aã]o"
        r"|advert[eê]ncia|suspens[aã]o|rescis[aã]o",
        re.IGNORECASE,
    )

    def extract_rules(
        self, text: str, tenant_id: str, payer_id: str
    ) -> List[Dict]:
        """Classify *text* and return a list of extracted rule dicts.

        Priority order (highest to lowest):
        GLOSA, INDICATOR, SLA, PENALTY, ROUTING, WHITELIST,
        OPME, DISCOUNT, AUTH, BUNDLE, PRICING
        """
        if self._RE_GLOSA.search(text):
            return [build_glosa(text, payer_id)]
        if self._RE_INDICATOR.search(text):
            return [build_indicator(text, payer_id)]
        if self._RE_SLA.search(text):
            return [build_sla(text, payer_id)]
        if self._RE_PENALTY.search(text):
            return [build_penalty(text, payer_id)]
        if self._RE_ROUTING.search(text):
            return [build_routing(text, payer_id)]
        if self._RE_WHITELIST.search(text):
            return [build_whitelist(text, payer_id)]
        if self._RE_OPME.search(text):
            return [build_opme(text, payer_id)]
        if self._RE_DISCOUNT.search(text):
            return [build_discount(text, payer_id)]
        if self._RE_AUTH.search(text):
            return [build_authorization(text, payer_id)]
        if self._RE_BUNDLE.search(text):
            return [build_bundling(text, payer_id)]
        if self._RE_PRICING.search(text):
            return [build_pricing(text, payer_id)]
        return []
