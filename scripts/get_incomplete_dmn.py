#!/usr/bin/env python3
import json

with open('docs/Migration/migration_manifest.json') as f:
    data = json.load(f)

incomplete = [e for e in data.get('entries', []) if e.get('migration_status') != 'complete']

print(f'Total incomplete: {len(incomplete)}')
print(f'Total complete: {data["totalEntries"] - len(incomplete)}')
print(f'Target total: {data["totalEntries"]}')
print()

for e in incomplete:
    rule_id = e.get('rule_id', 'N/A')
    new_path = e.get('new_path', 'NO_PATH')
    legacy_path = e.get('legacy_path', '')
    print(f'{rule_id}|{new_path}|{legacy_path}')
