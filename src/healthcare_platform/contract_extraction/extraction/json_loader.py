"""DOMED JSON loader — flattens structured contract JSON files into text segments.

Supports the seven DOMED JSON shapes found in the benchmark dataset:

1. Contract (documento.clausulas): nested dict of clause sections.
2. Appendix VII style (apendice_vii.*): nested lists of {"codigo_sigtap", "exame"}.
3. Appendix XI style (apendice_xi.itens_transcritos): flat list of material items.
4. Appendix V/VI/X style (apendice_v/vi/x.itens): list of {"codigo_br", description}.
5. Appendix VIII/IX style (apendice_viii/ix.pacotes_procedimentos): packages with
   nome, descricao, itens_inclusos, itens_exclusos.
6. Appendix I/II style (apendice_i/ii): generic nested dict of obligations/glosas.
7. Edital style (edital_de_credenciamento): generic nested dict.

Any unknown shape falls back to a generic deep-walk that concatenates all string
values found in the document.
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

# Detect [cite: ...] footnote markers injected by the PDF extractor
_RE_CITE = re.compile(r"\[cite:[^\]]*\]")


def _strip_cite(text: str) -> str:
    """Remove [cite: ...] markers from text."""
    return _RE_CITE.sub("", text).strip()


def _deep_strings(obj, sep: str = " ") -> str:
    """Recursively collect all string leaves in a nested dict/list structure."""
    if isinstance(obj, str):
        return _strip_cite(obj)
    if isinstance(obj, (int, float)):
        return str(obj)
    if isinstance(obj, list):
        return sep.join(_deep_strings(item, sep) for item in obj if item)
    if isinstance(obj, dict):
        return sep.join(
            _deep_strings(v, sep) for v in obj.values() if v is not None
        )
    return ""


class DomedJsonLoader:
    """Load DOMED JSON files and flatten them into text segments for extraction.

    Each text segment corresponds to a logical unit (clause, appendix row, package)
    that can be fed independently to ContractExtractor.extract_rules().
    """

    def load_file(self, filepath: str) -> List[str]:
        """Load a single DOMED JSON file and return a list of text segments.

        Args:
            filepath: Absolute or relative path to a DOMED JSON file.

        Returns:
            List of non-empty text strings, one per logical contract unit.
        """
        path = Path(filepath)
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load %s: %s", filepath, exc)
            return []

        segments: List[str] = []

        # Dispatch to specialised handlers based on top-level keys
        if "documento" in data:
            segments.extend(self._load_contract(data))
        elif any(k.startswith("apendice_viii") or k.startswith("apendice_ix") for k in data):
            # Appendix VIII/IX: packages with itens_inclusos/exclusos
            segments.extend(self._load_packages_appendix(data))
        elif any(k.startswith("apendice_vii") for k in data):
            # Appendix VII: exam tables nested under pathology categories
            segments.extend(self._load_exam_appendix(data))
        elif any(k.startswith("apendice_xi") for k in data):
            # Appendix XI: flat list of standardised materials
            segments.extend(self._load_materials_appendix(data))
        elif any(
            k.startswith("apendice_v") or k.startswith("apendice_vi") or k.startswith("apendice_x")
            for k in data
        ):
            # Appendix V/VI/X: nutrition / surgery item lists
            segments.extend(self._load_items_appendix(data))
        elif "edital_de_credenciamento" in data:
            segments.extend(self._load_edital(data))
        else:
            # Generic fallback: deep-walk the entire document
            segments.extend(self._load_generic(data))

        return [s for s in segments if s.strip()]

    def load_all(self, domed_dir: str) -> Dict[str, List[str]]:
        """Load all JSON files in *domed_dir* and return a mapping filename -> segments.

        Args:
            domed_dir: Directory that contains DOMED JSON files.

        Returns:
            Dict mapping each filename (without path) to its list of text segments.
        """
        base = Path(domed_dir)
        if not base.is_dir():
            logger.warning("DOMED directory does not exist: %s", domed_dir)
            return {}

        result: Dict[str, List[str]] = {}
        for json_file in sorted(base.glob("*.json")):
            segments = self.load_file(str(json_file))
            result[json_file.name] = segments
            logger.info("Loaded %s -> %d segments", json_file.name, len(segments))

        return result

    # ------------------------------------------------------------------
    # Specialised loaders
    # ------------------------------------------------------------------

    def _load_contract(self, data: dict) -> List[str]:
        """Walk documento.clausulas and produce one segment per clause value."""
        segments: List[str] = []
        clausulas = data.get("documento", {}).get("clausulas", {})
        for clause_key, clause_value in clausulas.items():
            label = clause_key.replace("_", " ").title()
            if isinstance(clause_value, str):
                segments.append(f"{label}: {_strip_cite(clause_value)}")
            elif isinstance(clause_value, dict):
                # Walk nested sub-clauses
                for sub_key, sub_value in clause_value.items():
                    sub_label = f"{label} {sub_key}"
                    text = _deep_strings(sub_value)
                    if text:
                        segments.append(f"{sub_label}: {text}")
            elif isinstance(clause_value, list):
                for item in clause_value:
                    text = _deep_strings(item)
                    if text:
                        segments.append(f"{label}: {text}")
        return segments

    def _load_exam_appendix(self, data: dict) -> List[str]:
        """Appendix VII: flatten exam lists from pathology categories.

        Expected shape: {apendice_vii: {categoria: [{codigo_sigtap, exame}, ...]}}
        """
        segments: List[str] = []
        for apendice_key, apendice_val in data.items():
            if not isinstance(apendice_val, dict):
                continue
            titulo = _strip_cite(apendice_val.get("titulo", apendice_key))
            for category, items in apendice_val.items():
                if category == "titulo":
                    continue
                if isinstance(items, list):
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        code = _strip_cite(str(item.get("codigo_sigtap", "") or item.get("tabela_amb92", "")))
                        name = _strip_cite(str(item.get("exame", "") or item.get("procedimento", "")))
                        if name or code:
                            segments.append(
                                f"Exame padronizado SES/DF - {titulo}: "
                                f"código SIGTAP {code} - {name}"
                            )
                elif isinstance(items, dict):
                    # Some categories nest further
                    for sub_cat, sub_items in items.items():
                        if isinstance(sub_items, list):
                            for item in sub_items:
                                code = _strip_cite(str(item.get("codigo_sigtap", "") or ""))
                                name = _strip_cite(str(item.get("exame", "") or ""))
                                if name or code:
                                    segments.append(
                                        f"Exame padronizado SES/DF - {titulo} {sub_cat}: "
                                        f"código SIGTAP {code} - {name}"
                                    )
        return segments

    def _load_materials_appendix(self, data: dict) -> List[str]:
        """Appendix XI: flat list of standardised materials.

        Expected shape: {apendice_xi: {itens_transcritos: [{codigo_ses, codigo_br, descricao}]}}
        """
        segments: List[str] = []
        for apendice_key, apendice_val in data.items():
            if not isinstance(apendice_val, dict):
                continue
            titulo = _strip_cite(apendice_val.get("titulo", apendice_key))
            items = apendice_val.get("itens_transcritos", [])
            if not isinstance(items, list):
                items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                code_ses = _strip_cite(str(item.get("codigo_ses", "") or ""))
                code_br = _strip_cite(str(item.get("codigo_br", "") or ""))
                descricao = _strip_cite(str(item.get("descricao", "") or ""))
                if descricao or code_ses:
                    segments.append(
                        f"Material padronizado SES/DF - {titulo}: "
                        f"código SES {code_ses} / código BR {code_br} - {descricao}"
                    )
        return segments

    def _load_items_appendix(self, data: dict) -> List[str]:
        """Appendix V/VI/X: nutrition / surgery item lists.

        Expected shape: {apendice_v: {titulo, itens: [{codigo_br, tipo_de_bolsa/descricao}]}}
        """
        segments: List[str] = []
        for apendice_key, apendice_val in data.items():
            if not isinstance(apendice_val, dict):
                continue
            titulo = _strip_cite(apendice_val.get("titulo", apendice_key))
            items = apendice_val.get("itens", [])
            if not isinstance(items, list):
                items = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                code = _strip_cite(str(item.get("codigo_br", "") or ""))
                # Description field may vary by appendix
                descricao = _strip_cite(
                    str(
                        item.get("tipo_de_bolsa", "")
                        or item.get("descricao", "")
                        or item.get("nome", "")
                        or ""
                    )
                )
                if descricao or code:
                    segments.append(
                        f"Item padronizado - {titulo}: código BR {code} - {descricao}"
                    )
        return segments

    def _load_packages_appendix(self, data: dict) -> List[str]:
        """Appendix VIII/IX: procedure packages with included/excluded items.

        Expected shape: {apendice_viii: {pacotes_procedimentos: [{nome, codigo_sigtap, detalhamento}]}}
        """
        segments: List[str] = []
        for apendice_key, apendice_val in data.items():
            if not isinstance(apendice_val, dict):
                continue
            titulo = _strip_cite(apendice_val.get("titulo", apendice_key))
            packages = apendice_val.get("pacotes_procedimentos", [])
            if not isinstance(packages, list):
                packages = []
            for pkg in packages:
                if not isinstance(pkg, dict):
                    continue
                nome = _strip_cite(str(pkg.get("nome", "") or ""))
                codigo = _strip_cite(str(pkg.get("codigo_sigtap", "") or ""))
                detalhamento = pkg.get("detalhamento", {})
                if not isinstance(detalhamento, dict):
                    detalhamento = {}
                descricao = _strip_cite(str(detalhamento.get("descricao", "") or ""))
                itens_inclusos = detalhamento.get("itens_inclusos", [])
                itens_exclusos = detalhamento.get("itens_exclusos", [])
                inclusos_txt = "; ".join(
                    _strip_cite(str(i)) for i in itens_inclusos if i
                )
                exclusos_txt = "; ".join(
                    _strip_cite(str(i)) for i in itens_exclusos if i
                )
                parts = [f"Pacote {titulo}: {nome}"]
                if codigo:
                    parts.append(f"SIGTAP {codigo}")
                if descricao:
                    parts.append(descricao)
                if inclusos_txt:
                    parts.append(f"Inclui: {inclusos_txt}")
                if exclusos_txt:
                    parts.append(f"Exclui: {exclusos_txt}")
                segments.append(". ".join(parts))
        return segments

    def _load_edital(self, data: dict) -> List[str]:
        """Edital: walk all nested sections and produce one segment per section."""
        segments: List[str] = []
        edital = data.get("edital_de_credenciamento", data)
        for section_key, section_val in edital.items():
            label = section_key.replace("_", " ").title()
            text = _deep_strings(section_val)
            if text.strip():
                segments.append(f"{label}: {text}")
        return segments

    def _load_generic(self, data: dict) -> List[str]:
        """Generic fallback: one segment per top-level key."""
        segments: List[str] = []
        for key, value in data.items():
            label = key.replace("_", " ").title()
            if isinstance(value, str):
                text = _strip_cite(value)
            elif isinstance(value, dict):
                text = _deep_strings(value)
            elif isinstance(value, list):
                text = " ".join(_deep_strings(item) for item in value)
            else:
                text = str(value)
            if text.strip():
                segments.append(f"{label}: {text}")
        return segments
