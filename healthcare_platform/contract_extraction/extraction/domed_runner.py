"""DOMED E2E runner — processes all DOMED JSON files and generates DMN outputs.

Usage (from project root):
    python3.11 -m healthcare_platform.contract_extraction.extraction.domed_runner

Or with custom paths:
    python3.11 -m healthcare_platform.contract_extraction.extraction.domed_runner \
        --domed-dir docs/research/Benchmark/DOMED/Contratos\ Originais \
        --output-dir healthcare_platform/contract_extraction/prototype/dmn

Pipeline:
  1. Load all DOMED JSONs via DomedJsonLoader
  2. Feed each text segment to ContractExtractor.extract_rules()
  3. For each rule dict, instantiate a mock ContractRule and call DMNGenerator.generate()
  4. Save DMN XML to prototype/dmn/{domain}/ based on archetype
  5. Run xmllint validation on each generated file
  6. Print summary

No database required — operates entirely in-memory using duck-typed rule objects.
"""

import argparse
import dataclasses
import enum
import logging
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("domed_runner")

# ---------------------------------------------------------------------------
# Project root detection — support running from any working directory
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[4]  # .../Healthcare-Orchest-CIB7


def _resolve_from_project(rel: str) -> Path:
    """Resolve *rel* relative to the detected project root."""
    return _PROJECT_ROOT / rel


# ---------------------------------------------------------------------------
# Default paths (configurable via CLI flags)
# ---------------------------------------------------------------------------
_DEFAULT_DOMED_DIR = _resolve_from_project(
    "docs/research/Benchmark/DOMED/Contratos Originais"
)
_DEFAULT_OUTPUT_DIR = _resolve_from_project(
    "healthcare_platform/contract_extraction/prototype/dmn"
)

# ---------------------------------------------------------------------------
# Archetype -> domain (sub-directory) mapping
# ---------------------------------------------------------------------------
_ARCHETYPE_DOMAIN: Dict[str, str] = {
    "PRICING": "contract",
    "LOOKUP": "catalog",
    "BUNDLING": "surgery",
    "AUTHORIZATION": "contract",
    "ROUTING": "contract",
    "WHITELIST": "catalog",
    "OPME": "surgery",
    "DISCOUNT": "contract",
}


# ---------------------------------------------------------------------------
# Minimal mock ContractRule that satisfies DMNGenerator duck-typing
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
    """Duck-typed substitute for ContractRule that avoids SQLAlchemy/DB."""

    id: str
    payer_id: str
    archetype: _MockArchetype
    category: _MockCategory
    rule_definition: Dict[str, Any]
    version: str = "1.0.0"
    tenant_id: str = "sesdf"

    @classmethod
    def from_rule_dict(cls, rule_dict: Dict[str, Any], payer_id: str = "SES-DF") -> "_MockContractRule":
        archetype_str = rule_dict.get("archetype", "PRICING")
        category_str = rule_dict.get("category", "PRICING")

        try:
            archetype = _MockArchetype(archetype_str)
        except ValueError:
            archetype = _MockArchetype.PRICING

        # Map category string to closest _MockCategory
        _cat_map: Dict[str, _MockCategory] = {
            "PRICING": _MockCategory.PRICING,
            "BUNDLE": _MockCategory.BUNDLE,
            "OPME": _MockCategory.OPME,
            "AUTHORIZATION": _MockCategory.AUTHORIZATION,
            "DISCOUNT": _MockCategory.DISCOUNT,
        }
        category = _cat_map.get(category_str, _MockCategory.AUTHORIZATION)

        return cls(
            id=str(uuid.uuid4()),
            payer_id=payer_id,
            archetype=archetype,
            category=category,
            rule_definition=rule_dict.get("rule_definition", {}),
        )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run(domed_dir: Path, output_dir: Path, tenant_id: str = "sesdf") -> None:
    """Execute the DOMED E2E pipeline.

    Args:
        domed_dir: Directory containing DOMED JSON files.
        output_dir: Base directory for DMN output files.
        tenant_id: Tenant identifier used for naming; must match [a-z0-9_-]+.
    """
    # Late imports so the module can be imported without side-effects
    from healthcare_platform.contract_extraction.dmn_generator import DMNGenerator
    from healthcare_platform.contract_extraction.extraction.extractor import ContractExtractor
    from healthcare_platform.contract_extraction.extraction.json_loader import DomedJsonLoader

    loader = DomedJsonLoader()
    extractor = ContractExtractor()
    generator = DMNGenerator()

    # -- Step 1: load all DOMED JSONs -------------------------------------------
    logger.info("Loading DOMED JSON files from: %s", domed_dir)
    all_segments = loader.load_all(str(domed_dir))
    total_files = len(all_segments)
    total_segments = sum(len(s) for s in all_segments.values())
    logger.info("Loaded %d files, %d total text segments", total_files, total_segments)

    # -- Step 2 & 3: extract rules and generate DMN -----------------------------
    stats: Dict[str, int] = {
        "files_processed": total_files,
        "segments_processed": 0,
        "rules_extracted": 0,
        "dmn_generated": 0,
        "dmn_validated": 0,
        "dmn_failed": 0,
        "validation_errors": 0,
    }

    for filename, segments in all_segments.items():
        logger.info("Processing %s (%d segments)", filename, len(segments))
        for segment in segments:
            stats["segments_processed"] += 1
            rules = extractor.extract_rules(segment, tenant_id, "SES-DF")
            stats["rules_extracted"] += len(rules)

            for rule_dict in rules:
                mock_rule = _MockContractRule.from_rule_dict(rule_dict)

                archetype_str = mock_rule.archetype.value
                domain = _ARCHETYPE_DOMAIN.get(archetype_str, "contract")
                domain_dir = output_dir / domain
                domain_dir.mkdir(parents=True, exist_ok=True)

                try:
                    xml = generator.generate(mock_rule)
                except subprocess.CalledProcessError as exc:
                    logger.warning(
                        "xmllint validation failed for rule %s: %s",
                        mock_rule.id,
                        exc.stderr.decode() if exc.stderr else str(exc),
                    )
                    stats["dmn_failed"] += 1
                    stats["validation_errors"] += 1
                    continue
                except Exception as exc:
                    logger.warning("DMN generation error for rule %s: %s", mock_rule.id, exc)
                    stats["dmn_failed"] += 1
                    continue

                # Save to output_dir/domain/{rule_id}_v1.0.0.dmn
                rule_id_safe = mock_rule.id.replace("-", "_")
                out_path = domain_dir / f"{rule_id_safe}_v{mock_rule.version}.dmn"
                out_path.write_text(xml, encoding="utf-8")
                stats["dmn_generated"] += 1

                # -- Step 5: validate saved file --------------------------------
                validated = _validate_dmn_file(out_path)
                if validated:
                    stats["dmn_validated"] += 1
                else:
                    stats["validation_errors"] += 1
                    logger.warning("Post-save validation failed: %s", out_path)

    # -- Step 6: print summary --------------------------------------------------
    _print_summary(stats)


def _validate_dmn_file(path: Path) -> bool:
    """Run xmllint on a saved DMN file. Returns True if valid."""
    try:
        result = subprocess.run(
            ["xmllint", "--noout", str(path)],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning(
                "xmllint: %s: %s",
                path.name,
                result.stderr.decode().strip(),
            )
            return False
        return True
    except FileNotFoundError:
        # xmllint not installed — skip validation but don't fail
        logger.debug("xmllint not found; skipping file-level validation for %s", path.name)
        return True
    except subprocess.TimeoutExpired:
        logger.warning("xmllint timed out for %s", path.name)
        return False


def _print_summary(stats: Dict[str, int]) -> None:
    """Print a formatted summary table."""
    separator = "-" * 50
    print(separator)
    print("DOMED E2E Runner — Summary")
    print(separator)
    print(f"  Files processed   : {stats['files_processed']}")
    print(f"  Segments processed: {stats['segments_processed']}")
    print(f"  Rules extracted   : {stats['rules_extracted']}")
    print(f"  DMN generated     : {stats['dmn_generated']}")
    print(f"  DMN validated ok  : {stats['dmn_validated']}")
    print(f"  DMN failed        : {stats['dmn_failed']}")
    print(f"  Validation errors : {stats['validation_errors']}")
    print(separator)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DOMED E2E runner — extract rules from DOMED JSONs and generate DMN files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--domed-dir",
        type=Path,
        default=_DEFAULT_DOMED_DIR,
        help="Directory containing DOMED JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help="Base directory for generated DMN files.",
    )
    parser.add_argument(
        "--tenant-id",
        type=str,
        default="sesdf",
        help="Tenant identifier (alphanumeric + hyphens only).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    domed_dir = Path(args.domed_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    if not domed_dir.is_dir():
        logger.error("DOMED directory not found: %s", domed_dir)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Output directory: %s", output_dir)

    run(domed_dir, output_dir, tenant_id=args.tenant_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
