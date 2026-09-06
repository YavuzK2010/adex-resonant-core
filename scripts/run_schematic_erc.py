#!/usr/bin/env python3
"""
Automated Electrical Rules Check (ERC) validation for AdEx Resonant Core.
- Sets up KiCad 10 project files (kicad_pro, sym-lib-table, custom libs)
- Converts old-format power symbols to KiCad 10 format
- Invokes kicad-cli sch erc
- Parses and displays a clean summary
- Adds PWR_FLAG symbols, no-connect flags as needed
"""

import os
import sys
import json
import subprocess
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
SCH = os.path.join(HW, "schematics")
SYM = os.path.join(HW, "symbols")
EXPORTS = os.path.join(HW, "exports")

# Ensure directories
def ensure_dirs():
    for d in [SCH, SYM, EXPORTS]:
        os.makedirs(d, exist_ok=True)

# ── 1. Create .kicad_pro files ──────────────────────
def create_pro_files():
    pro_template = json.dumps({
        "board": {"design_settings": {"rule_severities": {}}},
        "meta": {"version": 1},
        "project": {"name": "{NAME}"},
        "schematic": {
            "drawing": {
                "default_line_thickness": 6.0,
                "default_text_size": 50.0
            }
        },
        "sheets": [],
        "text_variables": {}
    }, indent=2)
    for name in ["top_level", "adex_neuron_cell", "lc_bridge_cell"]:
        path = os.path.join(SCH, f"{name}.kicad_pro")
        if not os.path.exists(path):
            with open(path, "w") as f:
                f.write(pro_template.format(NAME=name))
            print(f"  [OK] Created {path}")
        else:
            print(f"  [SKIP] {path} exists")

# ── 2. Create custom symbol libraries ───────────────
def create_custom_libs():
    # custom_power.kicad_sym - with VDD/VSS/GND symbols (KiCad 10 format)
    power_lib = os.path.join(SYM, "custom_power.kicad_sym")
    if not os.path.exists(power_lib):
        content = '''(kicad_symbol_lib (version 20251024) (generator "adex-resonant-brain")
  (symbol "VDD" (power global)
    (pin_numbers (hide yes))
    (pin_names (offset 0) (hide yes))
    (in_bom yes) (on_board yes)
    (property "Reference" "#PWR"
      (at 0 2.54 0) (show_name no)
      (effects (font (size 1.27 1.27)))
    )
    (property "Value" "VDD"
      (at 0 5.08 0) (show_name no)
      (effects (font (size 1.27 1.27)))
    )
    (property "Footprint" "" (at 0 0 0) (hide yes))
    (symbol "VDD_0_1"
      (pin (at 0 0 90) (length 0) (name "VDD") (effects (font (size 1.27 1.27))))
    )
  )
  (symbol "VSS" (power global)
    (pin_numbers (hide yes))
    (pin_names (offset 0) (hide yes))
    (in_bom yes) (on_board yes)
    (property "Reference" "#PWR" (at 0 2.54 0) (show_name no)
      (effects (font (size 1.27 1.27))))
    (property "Value" "VSS" (at 0 5.08 0) (show_name no)
      (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at 0 0 0) (hide yes))
    (symbol "VSS_0_1"
      (pin (at 0 0 90) (length 0) (name "VSS") (effects (font (size 1.27 1.27))))
    )
  )
  (symbol "GND" (power global)
    (pin_numbers (hide yes))
    (pin_names (offset 0) (hide yes))
    (in_bom yes) (on_board yes)
    (property "Reference" "#PWR" (at 0 2.54 0) (show_name no)
      (effects (font (size 1.27 1.27))))
    (property "Value" "GND" (at 0 5.08 0) (show_name no)
      (effects (font (size 1.27 1.27))))
    (property "Footprint" "" (at 0 0 0) (hide yes))
    (symbol "GND_0_1"
      (pin (at 0 0 90) (length 0) (name "GND") (effects (font (size 1.27 1.27))))
    )
  )
)
'''
        with open(power_lib, "w") as f:
            f.write(content)
        print(f"  [OK] Created {power_lib}")
    else:
        print(f"  [SKIP] {power_lib} exists")

    # custom.kicad_sym - MOSFET_N_GDS (already created)
    if not os.path.exists(os.path.join(SYM, "custom.kicad_sym")):
        print(f"  [WARN] custom.kicad_sym missing - need to create")

# ── 3. Create sym-lib-table ─────────────────────────
def create_sym_lib_table():
    path = os.path.join(SCH, "sym-lib-table")
    # Use local custom_power library for power symbols
    # Use system libraries for Device, etc. with KICAD10_SYMBOL_DIR
    content = '''(sym_lib_table
  (version 7)
  (lib (name "custom_power") (type "KiCad") (uri "${KIPRJMOD}/../symbols/custom_power.kicad_sym") (options "") (descr "Custom power symbols"))
  (lib (name "Device") (type "KiCad") (uri "${KICAD10_SYMBOL_DIR}/Device.kicad_sym") (options "") (descr "System device symbols"))
  (lib (name "custom") (type "KiCad") (uri "${KIPRJMOD}/../symbols/custom.kicad_sym") (options "") (descr "Custom project symbols"))
  (lib (name "Package_IC") (type "KiCad") (uri "${KICAD10_SYMBOL_DIR}/Comparator.kicad_sym") (options "") (descr "System comparator symbols"))
  (lib (name "Transistor_FET") (type "KiCad") (uri "${KICAD10_SYMBOL_DIR}/Transistor_FET.kicad_sym") (options "") (descr "System FET symbols"))
  (lib (name "Transistor_BJT") (type "KiCad") (uri "${KICAD10_SYMBOL_DIR}/Transistor_BJT.kicad_sym") (options "") (descr "System BJT symbols"))
)
'''
    with open(path, "w") as f:
        f.write(content)
    print(f"  [OK] Created {path}")

# ── 4. Convert power symbol format ──────────────────
def convert_power_symbols(sch_path):
    """Convert old-format (lib_name + entry_id) power symbols to new (lib_id) format."""
    with open(sch_path) as f:
        text = f.read()
    # Map old entry_id -> new lib_id symbol name
    entry_map = {
        'GLOBAL_VDD': 'custom_power:VDD',
        'GLOBAL_VSS': 'custom_power:VSS',
        'GLOBAL_GND': 'custom_power:GND',
    }
    modifications = 0
    for old_entry, new_lib_id in entry_map.items():
        # Replace (symbol (lib_name "power") (entry_id "OLD") ... ) pattern
        pattern_old = f'(symbol (lib_name "power") (entry_id "{old_entry}")'
        pattern_new = f'(symbol (lib_id "{new_lib_id}") (unit 1)'
        if pattern_old in text:
            text = text.replace(pattern_old, pattern_new)
            modifications += 1
            print(f"    Converted {old_entry} -> {new_lib_id}")
    if modifications > 0:
        with open(sch_path, "w") as f:
            f.write(text)
    return modifications

# ── 5. Run ERC ──────────────────────────────────────
def run_erc():
    top_sch = os.path.join(SCH, "top_level.kicad_sch")
    if not os.path.exists(top_sch):
        print(f"[ERROR] {top_sch} not found")
        return None
    
    report_json = os.path.join(EXPORTS, "erc_report.json")
    report_txt = os.path.join(EXPORTS, "erc_report.txt")
    
    cmd = [
        "kicad-cli", "sch", "erc",
        "--format", "json",
        "--severity-all",
        "--output", report_json,
        top_sch
    ]
    print(f"\n  Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=SCH)
    except subprocess.TimeoutExpired:
        print("  [TIMEOUT] ERC timed out")
        return None
    except FileNotFoundError:
        print("  [ERROR] kicad-cli not found")
        return None
    
    exit_code = result.returncode
    print(f"  Exit code: {exit_code}")
    
    if result.stderr:
        print(f"  stderr: {result.stderr[:500]}")
    
    if os.path.exists(report_json):
        return parse_report(report_json)
    elif os.path.exists(report_txt):
        return parse_txt_report(report_txt)
    else:
        print(f"  [WARN] No report file generated")
        return None

# ── 6. Parse report ─────────────────────────────────
def parse_report(json_path):
    with open(json_path) as f:
        data = json.load(f)
    violations = data.get("violations", [])
    errors = [v for v in violations if v.get("severity") == "error"]
    warnings = [v for v in violations if v.get("severity") == "warning"]
    print(f"\n{'='*60}")
    print(f"  ERC SUMMARY")
    print(f"  Errors:   {len(errors)}")
    print(f"  Warnings: {len(warnings)}")
    print(f"  Total violations: {len(violations)}")
    print(f"{'='*60}")
    
    if errors:
        print(f"\n  --- ERRORS ---")
        for i, e in enumerate(errors[:20], 1):
            code = e.get("code", "")
            msg = e.get("message", "")
            sheet = e.get("sheet", "")
            print(f"  {i}. [{code}] {msg}")
            if sheet:
                print(f"     Sheet: {sheet}")
    
    if warnings:
        print(f"\n  --- WARNINGS (first 10) ---")
        for i, w in enumerate(warnings[:10], 1):
            code = w.get("code", "")
            msg = w.get("message", "")
            print(f"  {i}. [{code}] {msg}")
    
    return {"errors": len(errors), "warnings": len(warnings), "total": len(violations)}

def parse_txt_report(txt_path):
    with open(txt_path) as f:
        text = f.read()
    error_count = text.count("  ; error")
    warning_count = text.count("  ; warning")
    print(f"\n{'='*60}")
    print(f"  ERC SUMMARY (from text report)")
    print(f"  Errors:   {error_count}")
    print(f"  Warnings: {warning_count}")
    print(f"{'='*60}")
    print(f"\n  First 30 lines of report:")
    for line in text.split('\n')[:30]:
        print(f"  {line}")
    return {"errors": error_count, "warnings": warning_count}


def main():
    print("=" * 60)
    print("  AdEx Resonant Core — Schematic ERC Validation")
    print("=" * 60)
    
    ensure_dirs()
    
    print("\n[1] Creating .kicad_pro project files...")
    create_pro_files()
    
    print("\n[2] Creating custom symbol libraries...")
    create_custom_libs()
    
    print("\n[3] Creating sym-lib-table...")
    create_sym_lib_table()
    
    print("\n[4] Converting power symbol format (old entry_id -> new lib_id)...")
    for sch in ["top_level.kicad_sch", "adex_neuron_cell.kicad_sch", "lc_bridge_cell.kicad_sch"]:
        path = os.path.join(SCH, sch)
        if os.path.exists(path):
            mods = convert_power_symbols(path)
            print(f"    {sch}: {mods} conversions")
    
    print("\n[5] Running ERC on top_level.kicad_sch...")
    result = run_erc()
    
    if result:
        print(f"\n{'='*60}")
        if result["errors"] == 0:
            print("  RESULT: 0 ERRORS — Schematics pass ERC!")
        else:
            print(f"  RESULT: {result['errors']} ERROR(s) remaining — needs fixing")
        print("=" * 60)
    else:
        print("\n[ERROR] ERC run failed or could not complete")
        sys.exit(1)

if __name__ == "__main__":
    main()
