#!/usr/bin/env python3
"""DMN Inventory Generator - Produces a comprehensive JSON catalog of all DMN files.

Usage:
    python scripts/dmn_inventory.py --output dmn_inventory.json
    python scripts/dmn_inventory.py --output dmn_inventory.json --path healthcare_platform/
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    from lxml import etree
except ImportError:
    sys.exit("ERROR: lxml is required. Install with: pip install lxml")

DMN_NS = "https://www.omg.org/spec/DMN/20191111/MODEL/"

DOMAIN_MAP = {
    "revenue_cycle": "revenue_cycle",
    "clinical_operations": "clinical_operations",
    "patient_access": "patient_access",
    "platform_services": "platform_services",
    "platform": "platform_services",
}


def detect_domain(filepath: str) -> str:
    """Detect domain from file path."""
    parts = Path(filepath).parts
    for part in parts:
        if part in DOMAIN_MAP:
            return DOMAIN_MAP[part]
    return "unknown"


def detect_tenant(filepath: str) -> str:
    """Detect tenant from file path or return 'global'."""
    parts = Path(filepath).parts
    for i, part in enumerate(parts):
        if part == "tenants" and i + 1 < len(parts):
            return parts[i + 1]
    return "global"


def extract_decision_info(filepath: str) -> list[dict]:
    """Extract decision metadata from a DMN file."""
    decisions = []

    try:
        tree = etree.parse(filepath)
    except etree.XMLSyntaxError:
        return [{
            "file": filepath,
            "parse_error": True,
            "decision_id": None,
            "decision_name": None,
        }]

    root = tree.getroot()
    domain = detect_domain(filepath)
    tenant = detect_tenant(filepath)

    for decision in root.findall(".//{%s}decision" % DMN_NS):
        decision_id = decision.get("id", "")
        decision_name = decision.get("name", "")

        info: dict = {
            "file": filepath,
            "decision_id": decision_id,
            "decision_name": decision_name,
            "domain": domain,
            "tenant_id": tenant,
            "input_expressions": [],
            "output_components": [],
            "hit_policy": "UNIQUE",
            "rule_count": 0,
        }

        table = decision.find("{%s}decisionTable" % DMN_NS)
        if table is not None:
            info["hit_policy"] = table.get("hitPolicy", "UNIQUE")

            # Inputs
            for inp in table.findall("{%s}input" % DMN_NS):
                label = inp.get("label", "")
                input_expr = inp.find("{%s}inputExpression" % DMN_NS)
                type_ref = ""
                expression = ""
                if input_expr is not None:
                    type_ref = input_expr.get("typeRef", "")
                    text_el = input_expr.find("{%s}text" % DMN_NS)
                    if text_el is not None and text_el.text:
                        expression = text_el.text.strip()
                info["input_expressions"].append({
                    "label": label,
                    "expression": expression,
                    "typeRef": type_ref,
                })

            # Outputs
            for out in table.findall("{%s}output" % DMN_NS):
                info["output_components"].append({
                    "label": out.get("label", ""),
                    "name": out.get("name", ""),
                    "typeRef": out.get("typeRef", ""),
                })

            # Rule count
            info["rule_count"] = len(table.findall("{%s}rule" % DMN_NS))

        decisions.append(info)

    return decisions


def build_inventory(root_path: str) -> dict:
    """Build complete DMN inventory."""
    all_decisions = []
    file_count = 0

    for dirpath, _, filenames in os.walk(root_path):
        for fn in sorted(filenames):
            if fn.endswith(".dmn"):
                filepath = os.path.join(dirpath, fn)
                file_count += 1
                decisions = extract_decision_info(filepath)
                all_decisions.extend(decisions)

    # Summary stats
    by_domain: dict[str, int] = defaultdict(int)
    by_hit_policy: dict[str, int] = defaultdict(int)
    by_tenant: dict[str, int] = defaultdict(int)
    parse_errors = 0

    for d in all_decisions:
        if d.get("parse_error"):
            parse_errors += 1
            continue
        by_domain[d["domain"]] += 1
        by_hit_policy[d["hit_policy"]] += 1
        by_tenant[d["tenant_id"]] += 1

    inventory = {
        "generated_by": "dmn_inventory.py",
        "root_path": root_path,
        "summary": {
            "total_files": file_count,
            "total_decisions": len(all_decisions) - parse_errors,
            "parse_errors": parse_errors,
            "by_domain": dict(sorted(by_domain.items())),
            "by_hit_policy": dict(sorted(by_hit_policy.items())),
            "by_tenant": dict(sorted(by_tenant.items())),
        },
        "decisions": all_decisions,
    }

    return inventory


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate DMN inventory catalog")
    parser.add_argument("--path", default="healthcare_platform/", help="Root directory to scan")
    parser.add_argument("--output", "-o", default="dmn_inventory.json", help="Output JSON file")
    parser.add_argument("--summary-only", action="store_true", help="Only print summary stats")
    args = parser.parse_args()

    if not os.path.isdir(args.path):
        print(f"ERROR: '{args.path}' is not a directory", file=sys.stderr)
        return 1

    print(f"Scanning {args.path} for DMN files...")
    inventory = build_inventory(args.path)

    summary = inventory["summary"]
    print(f"\nDMN Inventory Summary:")
    print(f"  Total files:     {summary['total_files']}")
    print(f"  Total decisions: {summary['total_decisions']}")
    print(f"  Parse errors:    {summary['parse_errors']}")
    print(f"\n  By domain:")
    for domain, count in summary["by_domain"].items():
        print(f"    {domain}: {count}")
    print(f"\n  By hit policy:")
    for policy, count in summary["by_hit_policy"].items():
        print(f"    {policy}: {count}")
    print(f"\n  By tenant:")
    for tenant, count in summary["by_tenant"].items():
        print(f"    {tenant}: {count}")

    if not args.summary_only:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(inventory, f, indent=2, ensure_ascii=False)
        print(f"\nInventory written to: {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
