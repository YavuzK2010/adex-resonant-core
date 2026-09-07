#!/usr/bin/env python3
"""
Automated Design Rules Check (DRC) for AdEx Resonant Core PCB.
- Executes kicad-cli pcb drc on the board layout file
- Outputs JSON report to hardware/exports/
- Parses results and prints a clean summary of Errors, Warnings, Unconnected
"""

import json
import os
import subprocess
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
LAYOUTS = os.path.join(HW, "layouts")
EXPORTS = os.path.join(HW, "exports")

BOARD_FILE = os.path.join(LAYOUTS, "adex_resonant_core.kicad_pcb")
PRO_FILE = os.path.join(LAYOUTS, "adex_resonant_core.kicad_pro")
REPORT_JSON = os.path.join(EXPORTS, "drc_report.json")
REPORT_TXT = os.path.join(EXPORTS, "drc_report.txt")


def ensure_dirs() -> None:
    """Ensure the exports directory exists."""
    os.makedirs(EXPORTS, exist_ok=True)


def run_drc() -> dict | None:
    """Run kicad-cli pcb drc and return parsed report data."""
    print(f"  Board:      {BOARD_FILE}")
    print(f"  Project:    {PRO_FILE}")
    print(f"  JSON out:   {REPORT_JSON}")
    print(f"  Text out:   {REPORT_TXT}")

    cmd = [
        "kicad-cli",
        "pcb",
        "drc",
        BOARD_FILE,
        "--format", "json",
        "--output", REPORT_JSON,
        "--severity-all",
        "--all-track-errors",
    ]

    print(f"\n[1] Running: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    print("  --- stdout ---")
    for line in result.stdout.strip().splitlines():
        print(f"  {line}")
    print("  -------------")

    if result.returncode not in (0, 3):
        print(f"  [ERROR] kicad-cli exited with code {result.returncode}")
        if result.stderr:
            print(f"  stderr: {result.stderr[:1000]}")
        return None

    if result.stderr:
        print(f"  stderr: {result.stderr[:500]}")

    # Also save the text output
    try:
        with open(REPORT_TXT, "w") as f:
            f.write(result.stdout)
    except OSError as e:
        print(f"  [WARN] Could not save text report: {e}")

    # Parse the JSON report
    if os.path.exists(REPORT_JSON):
        return parse_report(REPORT_JSON)
    else:
        print("  [WARN] JSON report file not generated")
        # Fall back to parsing stdout
        return parse_stdout_report(result.stdout)


def parse_report(json_path: str) -> dict:
    """Parse the DRC JSON report and print summary."""
    with open(json_path) as f:
        data = json.load(f)

    violations = data.get("violations", [])
    unconnected = data.get("unconnected_items", [])

    # Count by severity
    severity_counts: dict[str, int] = Counter()
    for v in violations:
        sev = v.get("severity", "unknown")
        severity_counts[sev] += 1

    # Count by type
    type_counts: dict[str, int] = Counter()
    for v in violations:
        vtype = v.get("type", "unknown")
        type_counts[vtype] += 1

    errors = severity_counts.get("error", 0)
    warnings = severity_counts.get("warning", 0)
    unconnected_count = len(unconnected)

    print("\n" + "=" * 60)
    print("  DRC SUMMARY")
    print(f"  Errors:           {errors}")
    print(f"  Warnings:         {warnings}")
    print(f"  Unconnected:      {unconnected_count}")
    print(f"  Total violations: {len(violations)}")
    print("=" * 60)

    if type_counts:
        print("\n  Violations by type:")
        for vtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"    {vtype}: {count}")

    if errors:
        print("\n  --- ERRORS (first 20) ---")
        error_list = [v for v in violations if v.get("severity") == "error"]
        for i, v in enumerate(error_list[:20], 1):
            desc = v.get("description", "")
            vtype = v.get("type", "")
            items_desc = "; ".join(
                it.get("description", "") for it in v.get("items", [])[:2]
            )
            print(f"  {i:3d}. [{vtype}] {desc}")
            if items_desc:
                print(f"        Items: {items_desc}")

    if warnings:
        print("\n  --- WARNINGS (first 10) ---")
        warning_list = [v for v in violations if v.get("severity") == "warning"]
        for i, v in enumerate(warning_list[:10], 1):
            desc = v.get("description", "")
            vtype = v.get("type", "")
            print(f"  {i:3d}. [{vtype}] {desc}")

    return {
        "errors": errors,
        "warnings": warnings,
        "unconnected": unconnected_count,
        "total": len(violations),
    }


def parse_stdout_report(stdout: str) -> dict:
    """Fallback: parse the text stdout report when JSON is unavailable."""
    lines = stdout.strip().splitlines()
    error_count = 0
    warning_count = 0
    unconnected_count = 0

    for line in lines:
        if "error" in line.lower():
            error_count += 1
        if "warning" in line.lower():
            warning_count += 1
        if "unconnected" in line.lower():
            # Try to extract the trailing number
            for token in line.split():
                try:
                    unconnected_count = int(token)
                except ValueError:
                    pass

    print("\n" + "=" * 60)
    print("  DRC SUMMARY (from stdout)")
    print(f"  Errors:           {error_count}")
    print(f"  Warnings:         {warning_count}")
    print(f"  Unconnected:      {unconnected_count}")
    print("=" * 60)

    return {
        "errors": error_count,
        "warnings": warning_count,
        "unconnected": unconnected_count,
        "total": error_count + warning_count,
    }


def main() -> int:
    print("=" * 60)
    print("  AdEx Resonant Core — PCB Design Rules Check (DRC)")
    print("=" * 60)

    # Validate that the board file exists
    if not os.path.exists(BOARD_FILE):
        print(f"\n[ERROR] Board file not found: {BOARD_FILE}")
        return 1

    if not os.path.exists(PRO_FILE):
        print(f"\n[WARN] Project file not found: {PRO_FILE}")

    ensure_dirs()

    print(f"\n  Board: {BOARD_FILE}")
    print(f"  Project: {PRO_FILE}")

    print("\n[1] Running KiCad 10 PCB DRC...")
    result = run_drc()

    if result is None:
        print("\n[ERROR] DRC run failed")
        return 1

    print("\n" + "=" * 60)
    if result["errors"] == 0 and result["warnings"] == 0 and result["unconnected"] == 0:
        print("  RESULT: 0 violations — PCB passes DRC!")
    else:
        print(
            f"  RESULT: {result['errors']} error(s), "
            f"{result['warnings']} warning(s), "
            f"{result['unconnected']} unconnected"
        )
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())