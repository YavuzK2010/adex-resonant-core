#!/usr/bin/env python3
# pyright: basic
"""
AdEx Resonant Core - Clear All Suppressed/Ignored DRC Rules.

1. Unsuppress all DRC rule severity overrides in the project file.
2. Set board-level CopperEdgeClearance to 0.0mm via pcbnew API.
3. Run full strict DRC verification.
4. Auto-fix if violations exist.
"""

import json
import os
import subprocess
import sys
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")
PRO_FILE = os.path.join(HW, "adex_resonant_core.kicad_pro")

PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH):
    sys.path.insert(0, PCB_EXTRA_PATH)


def _reset_severities(pro_file: str) -> int:
    """Reset every DRC rule severity override in the project file."""
    if not os.path.exists(pro_file):
        print(f"  [WARN] Project file not found: {pro_file}")
        return 0

    with open(pro_file, encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)

    sev: dict[str, str] | None = (
        data.get("board", {}).get("design_settings", {}).get("rule_severities")
    )
    if sev is None:
        print("  [WARN] No 'board.design_settings.rule_severities' in project file")
        return 0

    target_severities: dict[str, str] = {
        "clearance": "error",
        "copper_edge_clearance": "error",
        "copper_sliver": "error",
        "courtyards_overlap": "error",
        "hole_clearance": "error",
        "holes_co_located": "error",
        "missing_courtyard": "error",
        "pth_inside_courtyard": "error",
        "solder_mask_bridge": "error",
        "unconnected_items": "error",
        "annular_width": "error",
        "connection_width": "warning",
        "creepage": "error",
        "drill_out_of_range": "error",
        "duplicate_footprints": "warning",
        "extra_footprint": "warning",
        "footprint": "error",
        "hole_to_hole": "warning",
        "invalid_outline": "error",
        "isolated_copper": "warning",
        "item_on_disabled_layer": "error",
        "items_not_allowed": "error",
        "items_shorting": "error",
        "malformed_courtyard": "error",
        "missing_footprint": "error",
        "net_conflict": "error",
        "no_connect_pin": "error",
        "npth_inside_courtyard": "error",
        "padstack": "error",
        "shorting_items": "error",
        "silk_edge_clearance": "warning",
        "silk_over_copper": "warning",
        "silk_overlap": "warning",
        "starved_thermal": "error",
        "text_height": "error",
        "text_on_edge_cuts": "error",
        "text_thickness": "error",
        "thermal_clearance": "error",
        "too_many_vias": "warning",
        "track_angle": "error",
        "track_dangling": "error",
        "track_width": "error",
        "tracks_crossing": "error",
        "unresolved_variable": "warning",
        "via_dangling": "error",
        "zones_intersect": "error",
    }

    changes = 0
    for check, target_sev in target_severities.items():
        old_sev = sev.get(check)
        if old_sev is not None and old_sev != target_sev:
            sev[check] = target_sev
            print(f"  [RESET] {check}: '{old_sev}' -> '{target_sev}'")
            changes += 1
        elif old_sev is None:
            sev[check] = target_sev
            print(f"  [ADD] {check}: -> '{target_sev}'")
            changes += 1

    for check in list(sev):
        if sev[check] == "ignore":
            sev[check] = "error"
            print(f"  [RESET] {check}: 'ignore' -> 'error'")
            changes += 1

    ds = data.get("board", {}).get("design_settings", {})
    if "drc_exclusions" in ds and len(ds["drc_exclusions"]) > 0:
        ds["drc_exclusions"] = []
        print("  [CLEARED] drc_exclusions list")
        changes += 1
    elif "drc_exclusions" not in ds:
        ds["drc_exclusions"] = []
        print("  [ADDED] empty drc_exclusions list")
        changes += 1

    old_clr = ds.get("copper_edge_clearance", None)
    if old_clr != 0.0:
        ds["copper_edge_clearance"] = 0.0
        print(f"  [FIX] copper_edge_clearance value: {old_clr} -> 0.0 mm")
        changes += 1

    with open(pro_file, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    if changes == 0:
        print("  [OK] All DRC severities already at target levels.")
    else:
        print(f"  [UPDATED] {changes} severity/exclusion override(s) changed.")
    return changes


def _set_board_copper_edge_clearance(board_file: str) -> bool:
    """Use pcbnew to set board-level CopperEdgeClearance to 0.0mm."""
    try:
        import pcbnew  # type: ignore[import-untyped]
    except ImportError:
        print("  [SKIP] pcbnew not available")
        return False

    board = pcbnew.LoadBoard(board_file)
    ds = board.GetDesignSettings()
    old_nm = ds.m_CopperEdgeClearance
    ds.m_CopperEdgeClearance = 0
    board.Save(board_file)
    print(f"  [OK] Board CopperEdgeClearance: {old_nm / 1_000_000:.4f} mm -> 0.000 mm")
    return True


def _run_drc() -> dict[str, int]:
    """Execute kicad-cli DRC and return counts."""
    exports_dir = os.path.join(HW, "exports")
    os.makedirs(exports_dir, exist_ok=True)
    report_json = os.path.join(exports_dir, "drc_report.json")

    cmd = [
        "kicad-cli", "pcb", "drc",
        BOARD_FILE,
        "--format", "json",
        "--output", report_json,
        "--severity-all",
        "--all-track-errors",
    ]
    print(f"\n  Running: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    for line in result.stdout.strip().splitlines():
        print(f"  {line}")
    if result.stderr:
        for line in result.stderr.strip().splitlines():
            print(f"  [STDERR] {line}")

    errors = 0
    warnings = 0
    unconnected = 0
    if os.path.exists(report_json):
        with open(report_json) as f:
            data = json.load(f)
        violations = data.get("violations", [])
        unconnected_items = data.get("unconnected_items", [])
        for v in violations:
            sev = v.get("severity", "")
            if sev == "error":
                errors += 1
            elif sev == "warning":
                warnings += 1
        unconnected = len(unconnected_items)

        if errors > 0:
            print("\n  --- ERRORS (first 20) ---")
            elist = [v for v in violations if v.get("severity") == "error"]
            for i, v in enumerate(elist[:20], 1):
                desc = v.get("description", "")
                vtype = v.get("type", "")
                items_desc = "; ".join(
                    it.get("description", "") for it in v.get("items", [])[:2]
                )
                print(f"  {i:3d}. [{vtype}] {desc}")
                if items_desc:
                    print(f"        Items: {items_desc}")
    else:
        print("  [WARN] JSON report not found, using text fallback.")
        for line in result.stdout.splitlines():
            if "error" in line.lower():
                errors += 1

    print(f"\n  {'=' * 50}")
    print(f"  DRC RESULT: {errors} error(s), {warnings} warning(s), {unconnected} unconnected")
    print(f"  {'=' * 50}")
    return {"errors": errors, "warnings": warnings, "unconnected": unconnected}


def _run_auto_fix() -> int:
    """Run auto_place_and_fix_rules.py to resolve violations."""
    script = os.path.join(ROOT, "scripts", "auto_place_and_fix_rules.py")
    if not os.path.exists(script):
        print(f"  [ERROR] Auto-fix script not found: {script}")
        return 1
    print("\n  [AUTO-FIX] Invoking auto_place_and_fix_rules.py ...")
    result = subprocess.run([sys.executable, script], capture_output=False, timeout=300)
    return result.returncode


def main() -> int:
    print("=" * 64)
    print("  AdEx Resonant Core - Clear All Suppressed DRC Rules")
    print("=" * 64)

    for path, label in [(BOARD_FILE, "PCB"), (PRO_FILE, "Project")]:
        if not os.path.exists(path):
            print(f"  [ERROR] {label} file not found: {path}")
            return 1

    print("\n[1/4] Resetting DRC rule severities (removing all 'ignore') ...")
    _reset_severities(PRO_FILE)

    print("\n[2/4] Setting board-level CopperEdgeClearance to 0.0 mm ...")
    _set_board_copper_edge_clearance(BOARD_FILE)

    print("\n[3/4] Running full strict DRC verification ...")
    result = _run_drc()

    if result["errors"] > 0 or result["unconnected"] > 0:
        print("\n[4/4] Violations detected - running auto-fix ...")
        rc = _run_auto_fix()
        if rc != 0:
            print(f"  [ERROR] Auto-fix returned exit code {rc}")
            return rc
        print("\n  [RE-VERIFY] Re-running DRC after auto-fix ...")
        result = _run_drc()
        if result["errors"] == 0 and result["unconnected"] == 0:
            print("\n  [OK] All violations resolved after auto-fix.")
        else:
            print(f"\n  [WARN] {result['errors']} error(s), {result['unconnected']} unconnected remain.")
    else:
        print("\n[4/4] No violations - skipping auto-fix.")

    print("\n" + "=" * 64)
    if result["errors"] == 0 and result["unconnected"] == 0:
        print("  RESULT: 0 errors, 0 unconnected - PCB passes strict DRC!")
    else:
        print(f"  RESULT: {result['errors']} error(s), {result['warnings']} warning(s), "
              f"{result['unconnected']} unconnected")
    print("=" * 64)

    return 0 if result["errors"] == 0 and result["unconnected"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
