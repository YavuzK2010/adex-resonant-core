#!/usr/bin/env python3
"""Analyze courtyard overlap violations from DRC report."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
report = os.path.join(ROOT, "hardware", "exports", "drc_report.json")

with open(report) as f:
    d = json.load(f)

items = [v for v in d.get('violations', []) if v.get('type') == 'courtyards_overlap']
print(f"Total courtyard_overlap violations: {len(items)}")
print()

# Group by component pair patterns
pairs = {}
for v in items:
    descs = tuple(x.get('description', '?') for x in v.get('items', []))
    pairs[descs] = pairs.get(descs, 0) + 1

# Show most common patterns
print("Most common courtyard overlap patterns:")
for (a, b), count in sorted(pairs.items(), key=lambda x: -x[1])[:20]:
    print(f"  [{count}x] {a}")
    print(f"         {b}")
    print()

# Also check first 30 raw entries
print("\n--- First 30 courtyard_overlap entries ---")
for i, v in enumerate(items[:30]):
    descs = [x.get('description', '?') for x in v.get('items', [])]
    print(f"{i+1}. {' | '.join(descs)}")