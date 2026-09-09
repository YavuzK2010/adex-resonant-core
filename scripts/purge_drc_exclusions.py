#!/usr/bin/env python3
# pyright: basic
"""
AdEx Resonant Core — Purge All DRC Exclusions & Restore Rule Severities.

1. Strip any `(drc_exclusions ...)` sections from the .kicad_pcb (S-expression).
2. Reset every `"ignore"` severity → `"error"` in the .kicad_pro project file.
3. Clear the drc_exclusions array in the .kicad_pro project file.
4. Save both cleaned files.
5. Run a full unsuppressed DRC and verify ignored-tests count is 0.
"""

import json
import os
import re
import subprocess
import sys
from collections import Counter
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
EXPORTS = os.path.join(HW, "exports")

BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")
PRO_FILE = os.path.join(HW, "adex_resonant_core.kicad_pro")
REPORT_JSON = os.path.join(EXPORTS, "drc_report.json")


# ── 1. Strip drc_exclusions from the .kicad_pcb (S-expression) ──────────────

def _strip_pcb_drc_exclusions(pcb_path: str) -> int:
    """Remove any (drc_exclusions ...) block from the PCB S-expression file."""
    if not os.path.exists(pcb_path):
        print(f"  [SKIP] PCB file not found: {pcb_path}")
        return 0

    with open(pcb_path, "r", encoding="utf-8") as fh:
        content = fh.read()

    original_len = len(content)
    # Remove (drc_exclusions ...) blocks
    content, n = re.subn(
        r'\(drc_exclusions\s*\(uuid\s+"[^"]*"\)\s*\)',
        "",
        content,
        flags=re.DOTALL,
    )
    content, n2 = re.subn(r'\(drc_exclusions\s*\)', "", content, flags=re.DOTALL)
    n += n2

    if n > 0:
        content = re.sub(r'\n\s*\n\s*\n', '\n', content)
        content = content.strip() + "\n"
        with open(pcb_path, "w", encoding="utf-8") as fh:
            fh.write(content)
        removed = original_len - len(content)
        print(f"  [PURGE] Removed {n} drc_exclusions block(s) ({removed} bytes)")
    else:
        print(f"  [OK]    No drc_exclusions found in .kicad_pcb (clean)")

    return n


# ── 2. Target severities for all known DRC checks ───────────────────────────

TARGET_SEVERITIES: dict[str, str] = {
    "annular_width":                "error",
    "clearance":                    "error",
    "connection_width":             "warning",
    "copper_edge_clearance":        "error",
    "copper_sliver":                "error",
    "courtyards_overlap":           "error",
    "creepage":                     "error",
    "diff_pair_gap_out_of_range":   "error",
    "diff_pair_uncoupled_length_too_long": "error",
    "drill_out_of_range":           "error",
    "duplicate_footprints":         "error",
    "extra_footprint":              "error",
    "footprint":                    "error",
    "footprint_filters_mismatch":   "error",
    "footprint_symbol_field_mismatch": "error",
    "footprint_symbol_mismatch":    "error",
    "footprint_type_mismatch":      "error",
    "hole_clearance":               "error",
    "hole_to_hole":                 "error",
    "holes_co_located":             "error",
    "invalid_outline":              "error",
    "isolated_copper":              "error",
    "item_on_disabled_layer":       "error",
    "items_not_allowed":            "error",
    "items_shorting":               "error",
    "malformed_courtyard":          "error",
    "missing_courtyard":            "error",
    "missing_connection":           "error",
    "missing_footprint":            "error",
    "net_conflict":                 "error",
    "no_connect_pin":               "error",
    "npth_inside_courtyard":        "error",
    "padstack":                     "error",
    "pth_inside_courtyard":         "error",
    "shorting_items":               "error",
    "silk_edge_clearance":          "warning",
    "silk_over_copper":             "warning",
    "silk_overlap":                 "warning",
    "solder_mask_bridge":           "error",
    "starved_thermal":              "error",
    "text_height":                  "error",
    "text_on_edge_cuts":            "error",
    "text_thickness":               "error",
    "thermal_clearance":            "error",
    "too_many_vias":                "warning",
    "track_angle":                  "error",
    "track_dangling":               "error",
    "track_width":                  "error",
    "tracks_crossing":              "error",
    "unconnected_items":            "error",
    "unresolved_variable":          "warning",
    "via_dangling":                 "error",
    "zones_intersect":              "error",
}


def _reset_pro_severities(pro_path: str) -> int:
    """Reset every rule_severity override in the .kicad_pro file."""
    if not os.path.exists(pro_path):
        print(f"  [SKIP] Project file not found: {pro_path}")
        return 0

    with open(pro_path, "r", encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)

    sev: dict[str, str] | None = (
        data.get("board", {})
        .get("design_settings", {})
        .get("rule_severities")
    )
    if sev is None:
        print("  [WARN] No 'board.design_settings.rule_severities' found")
        return 0

    changes = 0
    for check, target in TARGET_SEVERITIES.items():
        current = sev.get(check)
        if current is not None and current != target:
            print(f"  [RESET] {check}: '{current}' -> '{target}'")
            sev[check] = target
            changes += 1
        elif current is None:
            sev[check] = target
            print(f"  [ADD]   {check}: <missing> -> '{target}'")
            changes += 1

    # Catch any keys not in target list that are 'ignore'
    for check in list(sev):
        if sev[check] == "ignore":
            sev[check] = "error"
            print(f"  [FIX]   {check}: 'ignore' -> 'error'")
            changes += 1

    # Clear drc_exclusions
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
            json.dump(data, fh, indent=2, ensure_ascii=False)
        print(f"  [SAVED] {changes} change(s) written to .kicad_pro")
    else:
        print("  [OK]    All severities already correct, no changes")

    return changes


# ── 3. Run DRC ──────────────────────────────────────────────────────────────

def _run_drc() -> dict[str, int]:
    """Run kicad-cli pcb drc with --severity-all and return counts."""
    os.makedirs(EXPORTS, exist_ok=True)

    cmd = [
        "kicad-cli", "pcb", "drc",
        BOARD_FILE,
        "--format", "json",
        "--output", REPORT_JSON,
        "--severity-all",
        "--all-track-errors",
    ]

    print(f"\n  $ {' '.join(cmd)}\n")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.stdout:
        for line in result.stdout.strip().splitlines():
            print(f"    {line}")
    if result.stderr:
        print(f"  stderr: {result.stderr[:800]}")

    errors = 0
    warnings = 0
    unconnected = 0
    ignored_count = 0

    if os.path.exists(REPORT_JSON):
        with open(REPORT_JSON) as fh:
            report: dict[str, Any] = json.load(fh)

        ignored_checks = report.get("ignored_checks", [])
        ignored_count = len(ignored_checks)

        violations = report.get("violations", [])
        unconnected_items = report.get("unconnected_items", [])

        sev_counter: dict[str, int] = Counter()
        for v in violations:
            sev_counter[v.get("severity", "")] += 1

        errors = sev_counter.get("error", 0)
        warnings = sev_counter.get("warning", 0)
        unconnected = len(unconnected_items)

        print(f"\n  Ignored tests: {ignored_count}")
        if ignored_checks:
            print("  Ignored check list:")
            for ic in ignored_checks:
                print(f"    - {ic.get('key', '?')}: {ic.get('description', '')}")
    else:
        print("  [WARN] No JSON report generated; parsing stdout")
        for line in result.stdout.splitlines():
            if "error" in line.lower():
                errors += 1
            if "warning" in line.lower():
                warnings += 1

    print(f"\n  {'=' * 50}")
    print(f"  DRC RESULT: {errors} error(s), {warnings} warning(s), "
          f"{unconnected} unconnected, {ignored_count} ignored test(s)")
    print(f"  {'=' * 50}")

    return {
        "errors": errors,
        "warnings": warnings,
        "unconnected": unconnected,
        "ignored": ignored_count,
    }


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 64)
    print("  AdEx Resonant Core — Purge DRC Exclusions & Restore Severities")
    print("=" * 64)

    # Step 1: Strip drc_exclusions from .kicad_pcb (S-expression)
    print("\n[1/4] Stripping DRC exclusions from .kicad_pcb ...")
    _strip_pcb_drc_exclusions(BOARD_FILE)

    # Step 2: Reset rule severities in .kicad_pro (JSON)
    print("\n[2/4] Resetting rule severities in .kicad_pro ...")
    _reset_pro_severities(PRO_FILE)

    # Step 3: Run full unsuppressed DRC
    print("\n[3/4] Running unsuppressed DRC ...")
    result = _run_drc()

    # Step 4: Evaluate
    print(f"\n[4/4] Evaluation:")
    if result["ignored"] == 0:
        print("  [PASS] Ignored tests: 0 — all checks active!")
    else:
        print(f"  [FAIL] Ignored tests: {result['ignored']} — still suppressed")

    if result["errors"] == 0 and result["unconnected"] == 0:
        print("  [PASS] 0 errors, 0 unconnected — PCB passes strict DRC!\n")
        final_rc = 0
    else:
        print(f"  [FAIL] {result['errors']} error(s), {result['unconnected']} unconnected remain\n")
        final_rc = 1

    print("-" * 64)
    print(
        f"  SUMMARY  |  Errors: {result['errors']}  |  Warnings: {result['warnings']}  |  "
        f"Unconnected: {result['unconnected']}  |  Ignored: {result['ignored']}"
    )
    print("-" * 64)

    return final_rc


if __name__ == "__main__":
    sys.exit(main())
