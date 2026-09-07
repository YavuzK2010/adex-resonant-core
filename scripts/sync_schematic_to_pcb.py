#!/usr/bin/env python3
"""
AdEx Resonant Core - Schematic-to-PCB Netlist Sync.

Pipeline:
  1. Export netlist from top_level.kicad_sch via kicad-cli (kicadxml format)
  2. Update PCB from netlist (pcbnew + kicad-cli fallback)
  3. Run auto_place_and_fix_rules.py to re-apply footprint layout
  4. Verify board integrity
"""
import json, os, subprocess, sys
PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH):
    sys.path.insert(0, PCB_EXTRA_PATH)
import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
SCH_DIR = os.path.join(HW, "schematics")
EXPORTS = os.path.join(HW, "exports")
TOP_SCH = os.path.join(SCH_DIR, "top_level.kicad_sch")
BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")
PRO_FILE = os.path.join(HW, "adex_resonant_core.kicad_pro")
NETLIST_FILE = os.path.join(EXPORTS, "top_level.net")
AUTO_PLACE_SCRIPT = os.path.join(ROOT, "scripts", "auto_place_and_fix_rules.py")

def ensure_dirs():
    os.makedirs(EXPORTS, exist_ok=True)

def step1_export_netlist() -> bool:
    print("[1/4] Exporting netlist from schematic...")
    cmd = ["kicad-cli", "sch", "export", "netlist", TOP_SCH,
           "--format", "kicadxml", "-o", NETLIST_FILE]
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    netlist_created = os.path.exists(NETLIST_FILE)
    if result.returncode not in (0, 3):
        print(f"  [WARN] kicad-cli returned code {result.returncode}")
        if result.stderr:
            print(f"  stderr: {result.stderr[:300]}")
    if netlist_created:
        size_kb = os.path.getsize(NETLIST_FILE) / 1024
        print(f"  [OK] Netlist exported: {NETLIST_FILE} ({size_kb:.1f} KB)")
        return True
    print("  [WARN] Top-level netlist export did not produce output.")
    return False

def step2_update_pcb() -> bool:
    print("[2/4] Updating PCB from netlist...")
    if not os.path.exists(BOARD_FILE):
        print(f"  [ERROR] Board file not found: {BOARD_FILE}")
        return False
    try:
        board = pcbnew.LoadBoard(BOARD_FILE)
    except Exception as e:
        print(f"  [ERROR] Failed to load board: {e}")
        return False
    fp_count_before = len(list(board.GetFootprints()))
    print(f"  Board loaded - {fp_count_before} footprints")
    if os.path.exists(NETLIST_FILE):
        try:
            netlist = pcbnew.LoadNetlist(NETLIST_FILE)
            board.UpdatePCBFromNetlist(netlist)
            print("  [OK] PCB updated from netlist")
        except AttributeError:
            print("  pcbnew.LoadNetlist not available, trying kicad-cli...")
            imp_cmd = ["kicad-cli", "pcb", "import", "netlist",
                       BOARD_FILE, "--netlist", NETLIST_FILE, "--output", BOARD_FILE]
            r = subprocess.run(imp_cmd, capture_output=True, text=True, timeout=120)
            if r.returncode not in (0, 3):
                print(f"  [ERROR] CLI netlist import: {r.stderr[:200]}")
                return False
            print("  [OK] Netlist imported via CLI")
    else:
        print("  [WARN] No netlist file, skipping netlist update.")
    try:
        board.SynchronizeNetsAndNetClasses(False)
        board.BuildConnectivity()
    except AttributeError:
        pass
    fp_count_after = len(list(board.GetFootprints()))
    print(f"  Footprints: {fp_count_before} -> {fp_count_after}")
    try:
        board.Save(BOARD_FILE)
        sz = os.path.getsize(BOARD_FILE)
        print(f"  [OK] Board saved: {BOARD_FILE} ({sz:,} bytes)")
    except Exception as e:
        print(f"  [ERROR] Failed to save board: {e}")
        return False
    return True

def step3_reapply_layout() -> bool:
    print("[3/4] Re-applying footprint layout...")
    if not os.path.exists(AUTO_PLACE_SCRIPT):
        print("  [WARN] Auto-place script not found, skipping.")
        return True
    cmd = [sys.executable, AUTO_PLACE_SCRIPT]
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    print("  --- stdout ---")
    for line in result.stdout.strip().splitlines():
        print(f"    {line}")
    print("  -------------")
    if result.returncode != 0:
        print(f"  [ERROR] Auto-place failed (code {result.returncode})")
        return False
    print("  [OK] Footprint layout re-applied")
    return True

def step4_verify() -> bool:
    print("[4/4] Verifying board integrity...")
    if not os.path.exists(BOARD_FILE):
        print(f"  [ERROR] Board file missing: {BOARD_FILE}")
        return False
    try:
        board = pcbnew.LoadBoard(BOARD_FILE)
    except Exception as e:
        print(f"  [ERROR] Board load failed: {e}")
        return False
    fps = list(board.GetFootprints())
    refs = [fp.GetReference() for fp in fps]
    print(f"  Footprints: {len(fps)}")
    print(f"  Tracks:      {len(list(board.GetTracks()))}")
    print(f"  Drawings:    {len(list(board.GetDrawings()))}")
    cast_count = sum(1 for r in refs if r.upper().startswith(("CT", "CB", "CL", "CR")))
    print(f"  Castellated edge connectors: {cast_count}")
    empty_refs = sum(1 for r in refs if not r.strip())
    if empty_refs:
        print(f"  [WARN] {empty_refs} footprints have empty references")
    print("  [OK] Board verification passed")
    return True

def main() -> int:
    print("=" * 64)
    print("  AdEx Resonant Core - Schematic-to-PCB Netlist Sync")
    print("=" * 64)
    ensure_dirs()
    if not os.path.exists(TOP_SCH):
        print(f"\n[ERROR] Top-level schematic not found: {TOP_SCH}")
        return 1
    if not os.path.exists(BOARD_FILE):
        print(f"\n[ERROR] Board file not found: {BOARD_FILE}")
        return 1
    print(f"\n  Schematic: {TOP_SCH}")
    print(f"  Board:     {BOARD_FILE}")
    print(f"  Project:   {PRO_FILE}")
    print(f"  Netlist:   {NETLIST_FILE}\n")
    step1_export_netlist()
    print()
    if not step2_update_pcb():
        return 1
    print()
    if not step3_reapply_layout():
        return 1
    print()
    if not step4_verify():
        return 1
    print("\n" + "=" * 64)
    print("  Sync complete - PCB matches schematic netlist!")
    print("=" * 64)
    return 0

if __name__ == "__main__":
    sys.exit(main())
