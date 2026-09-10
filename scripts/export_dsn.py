#!/usr/bin/env python3
# pyright: basic
"""Export Specctra DSN file from KiCad pcbnew board data."""
import os, sys
PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH):
    sys.path.insert(0, PCB_EXTRA_PATH)
import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")
EXPORTS = os.path.join(HW, "exports")
DSN_FILE = os.path.join(EXPORTS, "adex_resonant_core.dsn")

def mm(v): return v / 1_000_000.0

def export_dsn():
    board = pcbnew.LoadBoard(BOARD_FILE)
    if board is None:
        print("[ERROR] Failed to load board"); return 1
    print(f"[OK] Loaded board: {len(list(board.GetFootprints()))} footprints")
    os.makedirs(EXPORTS, exist_ok=True)
    
    L = []
    L.append("(dsn")
    L.append("  (version 2.0)")
    L.append("  (file_version 1)")
    now = __import__("datetime").datetime.now().isoformat()
    L.append(f'  (date "{now}")')
    L.append('  (source "KiCad 10.0.6")')
    L.append("")
    L.append("  (resolution (unit um) (precision 1000))")
    L.append("")
    
    # Structure
    L.append("  (structure")
    for lyr in ["F.Cu", "B.Cu", "In1.Cu", "In2.Cu"]:
        L.append(f"    (layer {lyr})")
    L.append("")
    L.append("    (place_boundary")
    L.append("      (path F.Cu")
    for x, y in [(0,0),(70000,0),(70000,70000),(0,70000),(0,0)]:
        L.append(f"        (point {x} {y})")
    L.append("      )")
    L.append("    )")
    L.append("  )")
    L.append("")
    
    # Stackup
    L.append("  (stackup")
    for lyr, kind in [("F.Cu","signal"),("In1.Cu","power"),("In2.Cu","power"),("B.Cu","signal")]:
        L.append(f"    (layer {lyr} (type {kind}) (thickness 35))")
    L.append("  )")
    L.append("")
    
    # Net class
    L.append("  (net_class Default")
    L.append("    (clearance 150)  (trace_width 200)")
    L.append("    (via_diameter 550)  (via_hole 300)")
    L.append("  )")
    L.append("")
    
    # Nets
    seen = {}; ntc = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            nc = pad.GetNetCode()
            if nc <= 0: continue
            if nc not in seen:
                seen[nc] = 1
                ntc[nc] = pad.GetNetname()
    L.append(f"  (net {len(seen)}")
    for nc in sorted(seen):
        L.append(f'    (net_data (net_name "{ntc[nc]}"))')
    L.append("  )")
    L.append("")
    
    # Components
    comp_count = 0
    L.append("  (component")
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pos = fp.GetPosition()
        x_um = mm(pos.x) * 1000; y_um = mm(pos.y) * 1000
        rot = fp.GetOrientationDegrees()
        if rot < 0: rot += 360.0
        try:
            side = "front" if fp.GetLayer() == pcbnew.F_Cu else "back"
        except:
            side = "front"
        L.append(f"    (comp {ref})")
        L.append(f"      (place (unit um) (place_pos (xy {x_um:.0f} {y_um:.0f}))")
        L.append(f"              (place_rotation {rot:.1f})")
        L.append(f"              (place_side {side}))")
        L.append("    )")
        comp_count += 1
    L.append("  )")
    L.append(f"  ; {comp_count} components")
    L.append("")
    
    # Network (pins per net)
    net_pins = {}
    for nc in sorted(seen):
        nm = ntc[nc]
        pins = []
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                if pad.GetNetCode() == nc:
                    pins.append((fp.GetReference(), pad.GetNumber()))
        net_pins[nm] = pins
    
    tot_pins = sum(len(v) for v in net_pins.values())
    L.append("  (network")
    for nm in sorted(net_pins):
        L.append(f'    (net "{nm}"')
        for ref, pn in net_pins[nm]:
            L.append(f'      (pin {ref} (pad {pn}))')
        L.append("    )")
    L.append("  )")
    L.append(f"  ; {tot_pins} pin connections")
    L.append("")
    L.append(")  ; end dsn")
    
    text = "\n".join(L)
    with open(DSN_FILE, "w") as f:
        f.write(text)
    print(f"[OK] DSN: {DSN_FILE} ({len(text):,} bytes, {len(L)} lines)")
    print(f"  Comps: {comp_count}  Nets: {len(seen)}  Pins: {tot_pins}")
    return 0

if __name__ == "__main__":
    sys.exit(export_dsn())
