#!/usr/bin/env python3
"""
Update migration_manifest.json to reflect DMN restructuring from
centralized platform/dmn/ to domain-owned folders.
"""

import json
import sys
from pathlib import Path
from typing import Optional, Dict, Set

# Domain mapping for DMN categories
CATEGORY_TO_DOMAIN = {
    "authorization": "patient_access",
    "clinical_safety": "clinical_operations",
    "billing": "revenue_cycle",
    "coding_audit": "revenue_cycle",
    "glosa_prevention": "revenue_cycle",
    "revenue_recovery": "revenue_cycle",
    "pricing": "revenue_cycle",
    "cash_operations": "revenue_cycle",
    "compliance": "platform_services",
    "credentialing": "platform_services",
    "access_control": "platform_services",
    "infrastructure": "platform_services",
}

def extract_category_from_path(path: str) -> Optional[str]:
    """Extract the DMN category from a path like platform/dmn/CATEGORY/..."""
    if "platform/dmn/" not in path:
        return None

    # Extract category after platform/dmn/
    parts = path.split("platform/dmn/")
    if len(parts) < 2:
        return None

    remainder = parts[1]
    category = remainder.split("/")[0]
    return category if category in CATEGORY_TO_DOMAIN else None

def transform_path(path: str, category: str) -> str:
    """Transform platform/dmn/CATEGORY to platform/DOMAIN/dmn/CATEGORY"""
    domain = CATEGORY_TO_DOMAIN[category]
    return path.replace(
        f"platform/dmn/{category}",
        f"platform/{domain}/dmn/{category}"
    )

def update_manifest(manifest_path: Path) -> tuple:
    """Update the migration manifest with domain-based paths."""

    # Load manifest
    with open(manifest_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Support both "entries" and "rules" keys
    entries_key = "entries" if "entries" in data else "rules"
    entries = data.get(entries_key, [])

    stats = {
        "total_rules": len(entries),
        "updated_rules": 0,
        "rules_with_domain": 0,
        "skipped_rules": 0,
        "categories_found": set(),
    }

    # Process each entry
    for rule in entries:
        # Check new_path (primary), then output_path, then path
        path_field = None
        if "new_path" in rule and rule["new_path"]:
            path_field = "new_path"
        elif "output_path" in rule and rule["output_path"]:
            path_field = "output_path"
        elif "path" in rule and rule["path"]:
            path_field = "path"

        if not path_field:
            stats["skipped_rules"] += 1
            continue

        original_path = rule[path_field]
        category = extract_category_from_path(original_path)

        if category:
            stats["categories_found"].add(category)

            # Transform the path
            new_path = transform_path(original_path, category)
            rule[path_field] = new_path

            # Add domain field
            rule["domain"] = CATEGORY_TO_DOMAIN[category]

            stats["updated_rules"] += 1
            stats["rules_with_domain"] += 1
        else:
            stats["skipped_rules"] += 1

    return data, stats

def main():
    manifest_path = Path(__file__).parent.parent / "docs/Migration/migration_manifest.json"

    print(f"Updating manifest: {manifest_path}")
    print()

    # Update the manifest
    updated_data, stats = update_manifest(manifest_path)

    # Write back
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(updated_data, f, indent=2, ensure_ascii=False)

    # Print statistics
    print("Migration Manifest Update Complete")
    print("=" * 50)
    print(f"Total rules: {stats['total_rules']}")
    print(f"Updated rules: {stats['updated_rules']}")
    print(f"Rules with domain field: {stats['rules_with_domain']}")
    print(f"Skipped rules: {stats['skipped_rules']}")
    print()
    print(f"Categories processed: {sorted(stats['categories_found'])}")
    print()

    if stats['updated_rules'] == 0:
        print("⚠️  WARNING: No rules were updated!")
        return 1

    print("✓ Manifest updated successfully")
    return 0

if __name__ == "__main__":
    sys.exit(main())
