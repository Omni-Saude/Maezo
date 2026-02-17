"""Contract rule extractor -- classifies clauses and builds rule definitions."""

import re
from typing import Dict, List

from .clause_parser import ClauseParser


class ContractExtractor:
    """Extract structured rules from Brazilian healthcare contract text."""

    _RE_OPME = re.compile(r"OPME|material|pr[oó]tese|[oó]rtese", re.IGNORECASE)
    _RE_DISCOUNT = re.compile(r"desconto|abatimento", re.IGNORECASE)
    _RE_AUTH = re.compile(
        r"autorizac|autorizaç|aprovac|aprovaç|supervisor", re.IGNORECASE
    )
    _RE_BUNDLE = re.compile(r"pacote|mesmo ato|conjunto", re.IGNORECASE)
    _RE_PRICING = re.compile(r"valor|preco|preço|unitario|unitário", re.IGNORECASE)
    _RE_DAYS = re.compile(r"(?:em\s+)?at[eé]\s+(\d+)\s+dias", re.IGNORECASE)

    def __init__(self) -> None:
        self.parser = ClauseParser()

    def extract_rules(
        self, text: str, tenant_id: str, payer_id: str
    ) -> List[Dict]:
        """Classify *text* and return a list of extracted rule dicts."""
        rules: List[Dict] = []

        # Priority order: OPME, DISCOUNT, AUTH, BUNDLE, PRICING
        if self._RE_OPME.search(text):
            rules.append(self._build_opme(text, payer_id))
        elif self._RE_DISCOUNT.search(text):
            rules.append(self._build_discount(text, payer_id))
        elif self._RE_AUTH.search(text):
            rules.append(self._build_authorization(text, payer_id))
        elif self._RE_BUNDLE.search(text):
            rules.append(self._build_bundling(text, payer_id))
        elif self._RE_PRICING.search(text):
            rules.append(self._build_pricing(text, payer_id))

        return rules

    def _build_pricing(self, text: str, payer_id: str) -> Dict:
        codes = self.parser.parse_procedure_codes(text)
        prices = self.parser.parse_currency(text)
        price = prices[0] if prices else 0
        return {
            "archetype": "PRICING",
            "category": "PRICING",
            "rule_definition": {
                "procedure_code": codes[0] if codes else "",
                "payer_id": payer_id,
                "quantity": 1,
                # Fields required by opme_limit template (also archetype PRICING)
                "item_code": codes[0] if codes else "",
                "reference_price": price,
                # Fields required by discount_volume template
                "monthly_volume": 0,
                # Fields required by discount_prompt_payment template
                "payment_days": 0,
                "output_unit_price": price,
                "output_total_price": price,
                "output_currency": "BRL",
            },
        }

    def _build_authorization(self, text: str, payer_id: str) -> Dict:
        codes = self.parser.parse_procedure_codes(text)
        prices = self.parser.parse_currency(text)
        return {
            "archetype": "AUTHORIZATION",
            "category": "AUTHORIZATION",
            "rule_definition": {
                "procedure_code": codes[0] if codes else "",
                "amount": prices[0] if prices else 0,
                "payer_id": payer_id,
                "output_requires_auth": True,
                "output_auth_type": "prior_authorization",
                "output_urgency_level": "standard",
            },
        }

    def _build_bundling(self, text: str, payer_id: str) -> Dict:
        codes = self.parser.parse_procedure_codes(text)
        prices = self.parser.parse_currency(text)
        return {
            "archetype": "BUNDLING",
            "category": "BUNDLE",
            "rule_definition": {
                "primary_code": codes[0] if codes else "",
                "secondary_code": codes[1] if len(codes) > 1 else "",
                "same_act": True,
                "output_is_bundled": True,
                "output_bundle_price": prices[0] if prices else 0,
                "output_bundle_code": (
                    "-".join(codes[:2]) if len(codes) >= 2 else ""
                ),
            },
        }

    def _build_opme(self, text: str, payer_id: str) -> Dict:
        codes = self.parser.parse_procedure_codes(text)
        quantities = self.parser.parse_quantities(text)
        return {
            "archetype": "OPME",
            "category": "OPME",
            "rule_definition": {
                "item_code": codes[0] if codes else "",
                "max_quantity": quantities[0] if quantities else 1,
                "payer_id": payer_id,
            },
        }

    def _build_discount(self, text: str, payer_id: str) -> Dict:
        percentages = self.parser.parse_percentages(text)
        days_match = self._RE_DAYS.search(text)
        days = int(days_match.group(1)) if days_match else 0
        return {
            "archetype": "DISCOUNT",
            "category": "DISCOUNT",
            "rule_definition": {
                "payer_id": payer_id,
                "discount_percentage": percentages[0] if percentages else 0,
                "payment_days": days,
            },
        }
