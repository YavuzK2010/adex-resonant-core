#!/usr/bin/env python3
# pyright: basic
"""
AdEx Resonant Core — PERMANENT OBLITERATION of all DRC test ignores & overrides.

STRICT POLICY: NO DRC rule is EVER suppressed or set to 'ignore'.

This script:

  1. Destroys every (drc_exclusions ...) block in the .kicad_pcb S-expression file.
  2. Forces every specified severity key in .kicad_pro to "error" (never "ignore" or "warning").
  3. Saves both files with zero tolerance for suppressed checks.
"""

import json
import os
import re
import sys
from typing import Any


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")

BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")
PRO_FILE = os.path.join(HW, "adex_resonant_core.kicad_pro")

# ── Severity keys to hard-lock to "error" ─────────────────────────────────
TARGET_KEYS: dict[str, str] = {
    "clearance":                     "error",
    "copper_edge_clearance":         "error",   # board_edge_clearance
    "hole_clearance":                "error",
    "holes_co_located":              "error",   # drilled_holes_co_located
    "courtyards_overlap":            "error",
    "missing_courtyard":             "error",   # footprint_no_courtyard
    "copper_sliver":                 "error",
    "missing_connection":            "error",
    "pth_inside_courtyard":          "error",
    "unconnected_items":          "error",
}
# ═══════════════════════════════════════════════════════════════════════════
#  1.  DESTROY every (drc_exclusions ...) block in the .kicad_pcb
# ═══════════════════════════════════════════════════════════════════════════

def _nuke_pcb_drc_exclusions(pcb_path: str) -> int:
    """
    Remove EVERY (drc_exclusions ...) block from the PCB S-expression file.

    Matches both forms:
        (drc_exclusions (uuid "..."))
        (drc_exclusions (uuid "...") (uuid "...") ...)
        (drc_exclusions)
    """
    if not os.path.exists(pcb_path):
        print(f"  [SKIP] PCB file not found: {pcb_path}")
        return 0

    with open(pcb_path, "r", encoding="utf-8") as fh:
        content = fh.read()

    original_len = len(content)

    # Multiline: (drc_exclusions ... ) with UUID children
    content, n = re.subn(
        r'\(drc_exclusions\s*(?:\(uuid\s+"[^"]*"\)\s*)*\)',
        "",
        content,
        flags=re.DOTALL,
    )

    # Single-line: (drc_exclusions)
    content, n2 = re.subn(r'\(drc_exclusions\s*\)', "", content, flags=re.DOTALL)
    n += n2

    if n > 0:
        content = re.sub(r'\n\s*\n\s*\n', '\n', content)
        content = content.strip() + "\n"
        with open(pcb_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        removed = original_len - len(content)
        print(f"  [NUKE] Removed {n} drc_exclusions block(s) ({removed} bytes)")
    else:
        print(f"  [OK]   No drc_exclusions found in .kicad_pcb (already clean)")

    return n
# ═══════════════════════════════════════════════════════════════════════════
#  2.  HARD-LOCK severity keys to "error" in .kicad_pro
# ═══════════════════════════════════════════════════════════════════════════

def _lock_pro_severities(pro_path: str) -> int:
    """
    Force every key in TARGET_KEYS to "error" in the .kicad_pro file.

    Also ensure `drc_exclusions` array is empty.
    """
    changes = 0

    if not os.path.exists(pro_path):
        print(f"  [SKIP] Project file not found: {pro_path}")
        return 0

    with open(pro_path, encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)

    # ── 2a. Force rule_severities ─────────────────────────────────────────
    sev = data.get("board", {}).get("design_settings", {}).get("rule_severities")
    if sev is None:
        print(f"  [WARN] No rule_severities found in {pro_path}")
    else:
        for key, target in TARGET_KEYS.items():
            old = sev.get(key)
            if old is not None and old != target:
                sev[key] = target
                print(f"  [LOCK] {key}: '{old}' -> '{target}'")
                changes += 1
            elif old is None:
                sev[key] = target
                print(f"  [ADD]  {key}: (missing) -> '{target}'")
                changes += 1

    # ── 2b. Clear drc_exclusions array ────────────────────────
    ds = data.get("board", {}).get("design_settings", {})
    if "drc_exclusions" in ds and len(ds["drc_exclusions"]) > 0:
        ds["drc_exclusions"] = []
        print("  [CLEAR] drc_exclusions list (was non-empty)")
        changes += 1
    elif "drc_exclusions" not in ds:
        ds["drc_exclusions"] = []
        print("  [ADD]   drc_exclusions list (was missing)")
        changes += 1
    else:
        print("  [OK]    drc_exclusions list already empty")

    if changes > 0:
        with open(pro_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")

    return changes
# ═══════════════════════════════════════════════════════════════════════════
#  3.  VERIFY — scan the .kicad_pro for any remaining "ignore" or "warning"
# ═══════════════════════════════════════════════════════════════════════════

def _scan_pro_for_non_errors(pro_path: str) -> int:
    """Scan .kicad_pro rule_severities for values that are NOT 'error'."""
    if not os.path.exists(pro_path):
        return 0

    with open(pro_path, encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)

    sev = data.get("board", {}).get("design_settings", {}).get("rule_severities", {})
    found = 0
    for key, val in sev.items():
        if val != "error":
            print(f"  [REMNANT] {key}: '{val}' (should be 'error')")
            found += 1

    if found == 0:
        print("  [OK] All rule_severities are 'error'")
    return found


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main() -> int:
    print("=" * 70)
    print("  AdEx Resonant Core — PERMANENT OBLITERATION")
    print("  DRC Ignores & Severity Overrides")
    print("  HARD LOCK: All target checks forced to 'error'")
    print("=" * 70)

    total_changes = 0

    # Step 1: Nuke drc_exclusions from .kicad_pcb
    print("\n[1/3] Nuking DRC exclusions from .kicad_pcb ...")
    n = _nuke_pcb_drc_exclusions(BOARD_FILE)
    total_changes += n

    # Step 2: Hard-lock severities in .kicad_pro
    print("\n[2/3] Hard-locking severity keys in .kicad_pro ...")
    n = _lock_pro_severities(PRO_FILE)
    total_changes += n

    # Step 3: Verify
    print("\n[3/3] Scanning for any remnant non-error severities ...")
    remnants = _scan_pro_for_non_errors(PRO_FILE)

    print(f"\n  {'=' * 70}")
    print(f"  TOTAL CHANGES: {total_changes}")
    if remnants == 0:
        print("  RESULT: All DRC test overrides permanently obliterated. PASS.")
        rc = 0
    else:
        print(f"  RESULT: {remnants} remnant severity(ies) remain. FAIL.")
        rc = 1
    print(f"  {'=' * 70}")

    return rc


if __name__ == "__main__":
    sys.exit(main())