#!/usr/bin/env python3
"""
Verify DMN completeness by checking manifest against actual files
"""
import json
import os

def main():
    with open('docs/Migration/migration_manifest.json') as f:
        data = json.load(f)

    print(f"Manifest total entries: {data['totalEntries']}")

    # Check each manifest entry
    found = 0
    missing = []

    for entry in data['entries']:
        new_path = entry.get('new_path', '')
        # Convert platform/ to healthcare_platform/
        actual_path = new_path.replace('platform/', 'healthcare_platform/', 1)

        if os.path.exists(actual_path):
            found += 1
        else:
            missing.append(entry.get('rule_id', 'N/A'))

    print(f"Files found: {found}/{data['totalEntries']}")
    print(f"Files missing: {len(missing)}")

    if missing:
        print("\nMissing files:")
        for rule_id in missing[:10]:
            print(f"  - {rule_id}")
        if len(missing) > 10:
            print(f"  ... and {len(missing) - 10} more")
    else:
        print("\n✓ All 667 DMN files are present!")

    # Count actual DMN files
    import subprocess
    result = subprocess.run(['find', 'healthcare_platform', '-name', '*.dmn'],
                          capture_output=True, text=True)
    actual_files = [f for f in result.stdout.strip().split('\n') if f]
    print(f"\nActual DMN files in healthcare_platform/: {len(actual_files)}")

    # Find files not in manifest
    manifest_files = set()
    for entry in data['entries']:
        new_path = entry.get('new_path', '')
        actual_path = new_path.replace('platform/', 'healthcare_platform/', 1)
        manifest_files.add(actual_path)

    extra_files = [f for f in actual_files if f not in manifest_files]
    print(f"Files not in manifest: {len(extra_files)}")

    if extra_files:
        print("\nExtra files (first 20):")
        for f in extra_files[:20]:
            print(f"  - {f}")

if __name__ == '__main__':
    main()
