#!/usr/bin/env python3
"""Fix all DRC rule severities in the project file to 'error'."""
import json

PRO_FILE = "/home/yavuzkemalinan/adex-resonant-brain/hardware/adex_resonant_core.kicad_pro"

with open(PRO_FILE) as f:
    data = json.load(f)

sev = data["board"]["design_settings"]["rule_severities"]
targets = [
    "clearance", "copper_edge_clearance", "copper_sliver",
    "hole_clearance", "holes_co_located", "missing_courtyard",
    "pth_inside_courtyard", "unconnected_items",
]
changed = 0
for k in targets:
    if sev.get(k) != "error":
        sev[k] = "error"
        print(f"  [FIX] {k}: -> 'error'")
        changed += 1

if changed:
    with open(PRO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  [UPDATED] {changed} severity override(s) changed to 'error'")
else:
    print("  [OK] All severities already at 'error'")