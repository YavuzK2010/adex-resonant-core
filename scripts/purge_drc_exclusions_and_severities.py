#!/usr/bin/env python3
# pyright: basic
"""
AdEx Resonant Core — PERMANENT PURGE of all DRC exclusions & ignored severities.

STRICT POLICY: NO DRC rule is EVER suppressed or set to 'ignore'.

This script:

  1. Parses the .kicad_pcb (S-expression) file and removes EVERY
     (drc_exclusions ...) block — NO exclusions survive.
  2. Parses the .kicad_pro (JSON) file and replaces each
     `"severity": "ignore"` with `"severity": "error"` —
     NO rule is EVER allowed to be ignored.
  3. Clears the `drc_exclusions` array in .kicad_pro so it stays empty.
  4. Scans .kicad_pcb for any residual 'ignore' strings.
  5. Runs a full unsuppressed DRC via kicad-cli and verifies that
     the ignored/suppressed checks count is EXACTLY ZERO.
  6. Exits with code 0 if everything passes, 1 otherwise.
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
LAYOUTS_PRO_FILE = os.path.join(HW, "layouts", "adex_resonant_core.kicad_pro")
REPORT_JSON = os.path.join(EXPORTS, "drc_report.json")

# All .kicad_pro files that need severity enforcement
ALL_PRO_FILES = [PRO_FILE, LAYOUTS_PRO_FILE]
# ── 1. Strip drc_exclusions from the .kicad_pcb (S-expression) ──────────────

def _strip_pcb_drc_exclusions(pcb_path: str) -> int:
    """
    Remove EVERY (drc_exclusions ...) block from the PCB file.
    Handles both forms:
      (drc_exclusions (uuid "..."))
      (drc_exclusions)
    """
    if not os.path.exists(pcb_path):
        print(f"  [SKIP] PCB file not found: {pcb_path}")
        return 0

    with open(pcb_path, "r", encoding="utf-8") as fh:
        content = fh.read()

    original_len = len(content)

    # Remove (drc_exclusions (uuid "...")) blocks
    content, n = re.subn(
        r'\(drc_exclusions\s*\(uuid\s+"[^"]*"\)\s*\)',
        "",
        content,
        flags=re.DOTALL,
    )
    # Remove empty (drc_exclusions) blocks
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

# ── 2. Reset ALL rule severities: replace `"ignore"` with `"error"` ────────

def _reset_pro_severities(pro_file: str) -> int:
    """
    Replace EVERY `"severity": "ignore"` with `"severity": "error"` in the
    project file. Also ensure the `drc_exclusions` array is empty.
    """
    changes = 0

    if not os.path.exists(pro_file):
        print(f"  [WARN] Project file not found: {pro_file}")
        return 0

    with open(pro_file, encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)

    # ── 2a. Reset rule_severities ───────────────────────────────────────────
    sev = data.get("board", {}).get("design_settings", {}).get("rule_severities")
    if sev is None:
        print("  [WARN] No 'board.design_settings.rule_severities' found")
    else:
        for check_name, current_val in list(sev.items()):
            if current_val == "ignore":
                sev[check_name] = "error"
                print(f"  [FIX]   {check_name}: 'ignore' -> 'error'")
                changes += 1
            elif current_val != "error":
                sev[check_name] = "error"
                print(f"  [FIX]   {check_name}: '{current_val}' -> 'error'")
                changes += 1

    if changes == 0:
        print("  [OK]    No 'ignore' severities found (already all error)")

    # ── 2b. Clear drc_exclusions array ───────────────────────────────────────
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
        with open(pro_file, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        print(f"  [SAVED] Project file updated ({changes} change(s))")

    return changes
# ── 3. Scan .kicad_pcb for any remaining 'ignore' strings ──────────────────

def _scan_pcb_for_ignores(pcb_path: str) -> int:
    """Scan the PCB file for any occurrence of the word 'ignore'."""
    if not os.path.exists(pcb_path):
        return 0

    with open(pcb_path, "r", encoding="utf-8") as fh:
        content = fh.read()

    matches = list(re.finditer(r'\bignore\b', content, re.IGNORECASE))
    count = len(matches)
    if count > 0:
        print(f"  [WARN] Found {count} 'ignore' occurrence(s) in .kicad_pcb:")
        for m in matches[:10]:
            start = max(0, m.start() - 40)
            end = min(len(content), m.end() + 40)
            context = content[start:end].replace('\n', ' ')
            print(f"    ...{context}...")
        if count > 10:
            print(f"    ... and {count - 10} more")
    else:
        print("  [OK]    No 'ignore' strings found in .kicad_pcb")

    return count
# ── 4. Run full unsuppressed DRC via kicad-cli ──────────────────────────────
# ── 2x. Scan .kicad_pro for any remaining 'ignore' strings ────────────────

def _scan_pro_for_ignores(pro_path: str) -> int:
    """Scan the .kicad_pro file for any occurrence of the word 'ignore'."""
    if not os.path.exists(pro_path):
        return 0

    with open(pro_path, "r", encoding="utf-8") as fh:
        content = fh.read()

    matches = list(re.finditer(r'\bignore\b', content, re.IGNORECASE))
    count = len(matches)
    if count > 0:
        print(f"  [WARN] Found {count} 'ignore' occurrence(s) in .kicad_pro:")
        for m in matches[:10]:
            start = max(0, m.start() - 40)
            end = min(len(content), m.end() + 40)
            context = content[start:end].replace('\n', ' ')
            print(f"    ...{context}...")
        if count > 10:
            print(f"    ... and {count - 10} more")
    else:
        print("  [OK]    No 'ignore' strings found in .kicad_pro")

    return count

# ── 3. Scan .kicad_pcb for any remaining 'ignore' strings ──────────────────

def _run_drc() -> dict[str, int]:
    """
    Execute kicad-cli pcb drc with full unsuppressed flags and parse the JSON
    report.

    Returns dict: {errors, warnings, unconnected, ignored}
    """
    os.makedirs(EXPORTS, exist_ok=True)

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

        print(f"\n  Ignored/Suppressed tests: {ignored_count}")
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

    # Print detailed violation list
    if errors > 0 or warnings > 0:
        if os.path.exists(REPORT_JSON):
            with open(REPORT_JSON) as fh:
                report = json.load(fh)
            violations = report.get("violations", [])
            if violations:
                print("\n  --- VIOLATION DETAIL ---")
                for v in violations[:30]:
                    sev = v.get("severity", "?")
                    vtype = v.get("type", "?")
                    desc = v.get("description", "")
                    items = v.get("items", [])
                    item_str = "; ".join(
                        it.get("description", "") for it in items[:2]
                    )
                    print(f"    [{sev.upper():7}] [{vtype}] {desc}")
                    if item_str:
                        print(f"              Items: {item_str}")

    return {
        "errors": errors,
        "warnings": warnings,
        "unconnected": unconnected,
        "ignored": ignored_count,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 70)
    print("  AdEx Resonant Core — PERMANENT PURGE")
    print("  DRC Exclusions & Ignored Severities")
    print("  STRICT POLICY: NO DRC rule is EVER suppressed or set to 'ignore'")
    print("=" * 70)

    total_changes = 0

    # Step 1: Strip drc_exclusions from .kicad_pcb (S-expression)
    print("\n[1/5] Stripping DRC exclusions from .kicad_pcb ...")
    n = _strip_pcb_drc_exclusions(BOARD_FILE)
    total_changes += n

    # Step 2: Reset severities in ALL .kicad_pro files
    print("\n[2/5] Resetting rule severities in ALL .kicad_pro files ...")
    for pro_path in ALL_PRO_FILES:
        print(f"\n  --- Processing: {pro_path} ---")
        n = _reset_pro_severities(pro_path)
        total_changes += n
        n2 = _scan_pro_for_ignores(pro_path)
        total_changes += n2

    # Step 3: Scan .kicad_pcb for any "ignore" strings
    print("\n[3/5] Scanning .kicad_pcb for any remaining 'ignore' ...")
    n = _scan_pcb_for_ignores(BOARD_FILE)
    total_changes += n

    # Step 4: Run full unsuppressed DRC
    print("\n[4/5] Running unsuppressed DRC ...")
    result = _run_drc()

    # Step 5: Evaluate
    print(f"\n[5/5] Evaluation:")
    passed = True

    ignored = result["ignored"]
    if ignored > 0:
        print(f"  [FAIL] {ignored} test(s) are ignored — violation of strict policy")
        passed = False
    else:
        print("  [PASS] Ignored/suppressed tests: 0 — all checks active!")

    if result["errors"] > 0:
        print(f"  [FAIL] {result['errors']} error(s) — physical violations exist")
        passed = False

    print(f"\n  {'=' * 70}")
    print(
        f"  SUMMARY  |  Errors: {result['errors']}  |  "
        f"Warnings: {result['warnings']}  |  "
        f"Unconnected: {result['unconnected']}  |  "
        f"Ignored: {result['ignored']}"
    )
    print(f"  {'=' * 70}")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
                    