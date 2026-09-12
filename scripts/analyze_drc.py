#!/usr/bin/env python3
"""Analyze courtyard overlap violations from DRC report."""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
report = os.path.join(ROOT, "hardware", "exports", "drc_report.json")

with open(report) as f:
    d = json.load(f)

items = [v for v in d.get('violations', []) if v.get('type') == 'courtyards_overlap']
print(f"Total courtyard_overlap violations: {len(items)}\n")
print("All pairings:")
for i, v in enumerate(items):
    descs = [x.get('description', '?') for x in v.get('items', [])]
    print(f"  {i+1:2d}. {' ↔ '.join(descs)}")