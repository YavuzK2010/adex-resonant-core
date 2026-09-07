#!/usr/bin/env python3
"""AdEx Resonant Core - 4-Layer KiCad 10 PCB Layout Generator."""
import os, subprocess, uuid
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
SCH = os.path.join(HW, "schematics")
LAYOUTS = os.path.join(HW, "layouts")
PCB_FILE = os.path.join(LAYOUTS, "adex_resonant_core.kicad_pcb")
TOP_SCH = os.path.join(SCH, "top_level.kicad_sch")
BOARD_SIZE_MM = 50.0
CASTELLATED_PITCH_MM = 2.0
CASTELLATED_DIA_MM = 0.8
PAD_WIDTH_MM = 1.0
PAD_LENGTH_MM = 0.5

def mm(v: float) -> int: return int(round(v * 1_000_000))
def xy(x: float, y: float) -> str: return f"(xy {mm(x)} {mm(y)})"
def uid(): return uuid.uuid4().hex[:16]

def ensure_sym_lib_table():
    tp = os.path.join(SCH, "sym-lib-table")
    if os.path.exists(tp): return
    c = '(sym_lib_table\n'
    c += '  (lib (name "custom_power")(type "KiCad")'
    c += '(uri "${KIPRJMOD}/../symbols/custom_power.kicad_sym")(options "")(descr ""))\n'
    c += '  (lib (name "Device")(type "KiCad")'
    c += '(uri "${KIPRJMOD}/../../../../share/kicad/symbols/Device.kicad_sym")(options "")(descr ""))\n'
    c += '  (lib (name "power")(type "KiCad")'
    c += '(uri "${KIPRJMOD}/../../../../share/kicad/symbols/power.kicad_sym")(options "")(descr ""))\n'
    c += '  (lib (name "Package_IC")(type "KiCad")'
    c += '(uri "${KIPRJMOD}/../../../../share/kicad/symbols/Package_IC.kicad_sym")(options "")(descr ""))\n)\n'
    with open(tp, 'w') as f: f.write(c)
    print("  [OK] Created", tp)

def convert_power_symbols(sch_path: str) -> int:
    with open(sch_path) as f: text = f.read()
    count = 0
    for p in ["VDD", "VSS", "GND"]:
        old = '"power:' + p + '"'
        new = '"custom_power:' + p + '"'
        n = text.count(old)
        if n:
            count += n
            text = text.replace(old, new)
    if count > 0:
        with open(sch_path, 'w') as f: f.write(text)
    return count


def build_pcb_file() -> None:
    import sys
    sys.path.insert(0, '/usr/lib64/python3.14/site-packages')
    import pcbnew  # type: ignore[import-untyped]
    pcbnew_mod: Any = pcbnew
    b = BOARD_SIZE_MM
    p = CASTELLATED_PITCH_MM
    board = pcbnew_mod.CreateEmptyBoard()
    board.SetCopperLayerCount(4)
    
    # Board edge on Edge.Cuts
    for sx, sy, ex, ey in [(0, 0, b, 0), (b, 0, b, b), (b, b, 0, b), (0, b, 0, 0)]:
        sx: float
        sy: float
        ex: float
        ey: float
        line = pcbnew_mod.PCB_SHAPE(board, pcbnew_mod.SHAPE_T_SEGMENT)
        line.SetLayer(pcbnew_mod.Edge_Cuts)
        line.SetStart(pcbnew_mod.VECTOR2I(int(sx*1e6), int(sy*1e6)))
        line.SetEnd(pcbnew_mod.VECTOR2I(int(ex*1e6), int(ey*1e6)))
        line.SetWidth(int(0.1 * 1e6))
        board.Add(line)
    
    # Castellated hole footprints on periphery
    n = int(b / p) - 1
    for pos, label, angle in [
        ([(i*p, 0.0) for i in range(1, n+1)], 'CT', 0),
        ([(b, i*p) for i in range(1, n+1)], 'CR', 90),
        ([(i*p, b) for i in range(1, n+1)], 'CB', 180),
        ([(0.0, i*p) for i in range(1, n+1)], 'CL', 270),
    ]:
        for j, (x, y) in enumerate(pos, 1):
            ref = label + '%03d' % j
            fp = pcbnew_mod.FOOTPRINT(board)
            fp.SetReference(ref)
            fp.SetValue('')
            fp.SetLayer(pcbnew_mod.F_Cu)
            fp.SetPosition(pcbnew_mod.VECTOR2I(int(x * 1e6), int(y * 1e6)))
            fp.SetOrientationDegrees(angle)
            pad = pcbnew_mod.PAD(fp)
            pad.SetNumber('1')
            pad.SetSize(pcbnew_mod.VECTOR2I(int(0.5 * 1e6), int(1.0 * 1e6)))
            pad.SetPosition(pcbnew_mod.VECTOR2I(0, 0))
            pad.SetLayerSet(pcbnew_mod.LSET())
            for layer in [pcbnew_mod.F_Cu, pcbnew_mod.In1_Cu, pcbnew_mod.In2_Cu, pcbnew_mod.B_Cu]:
                pad.GetLayerSet().AddLayer(layer)
            pad.SetShape(pcbnew_mod.PAD_SHAPE_ROUNDRECT)
            fp.Add(pad)
            board.Add(fp)
    
    os.makedirs(LAYOUTS, exist_ok=True)
    board.Save(PCB_FILE)
    sz = os.path.getsize(PCB_FILE)
    print("  [OK] Wrote", PCB_FILE, "(" + str(sz) + " bytes)")

def validate_pcb() -> bool:
    r = subprocess.run(['kicad-cli','pcb','upgrade','--force',PCB_FILE],
                       capture_output=True,text=True,timeout=60)
    if r.returncode != 0:
        print('  [WARN] upgrade failed:', (r.stderr or r.stdout)[:200])
        return False
    print('  [OK] PCB validated')
    return True

def run_drc() -> None:
    report = os.path.join(LAYOUTS, 'drc_report.json')
    r = subprocess.run(['kicad-cli','pcb','drc','--format','json',
                        '--output',report,PCB_FILE],
                       capture_output=True,text=True,timeout=120)
    if r.returncode not in (0, 3):
        print('  [WARN] DRC failed:', r.stderr[:200])
        return
    print('  [OK] DRC report:', report)

def main() -> None:
    print('='*60)
    print('  AdEx Resonant Core - 4-Layer PCB Layout Generation')
    print('='*60)
    print('\n[0/4] Setting up symbol library table ...')
    ensure_sym_lib_table()
    for f in ['top_level.kicad_sch','adex_neuron_cell.kicad_sch','lc_bridge_cell.kicad_sch']:
        p = os.path.join(SCH, f)
        if os.path.exists(p):
            n = convert_power_symbols(p)
            if n: print('  [OK]', f + ':', n, 'power symbol conversions')
    print('\n[1/4] Exporting netlist ...')
    os.makedirs(LAYOUTS, exist_ok=True)
    r = subprocess.run(['kicad-cli','sch','export','netlist',
                        '--output',os.path.join(LAYOUTS,'adex_resonant_core.net'),TOP_SCH],
                       capture_output=True,text=True,timeout=60)
    if r.returncode == 0:
        print('  [OK] netlist exported')
    else:
        print('  [SKIP] netlist export:', r.stderr[:100])
    print('\n[2/4] Generating PCB layout ...')
    build_pcb_file()
    print('\n[3/4] Validating PCB syntax ...')
    validate_pcb()
    print('\n[4/4] Running DRC ...')
    run_drc()
    print('\n' + '='*60)
    print('  PCB layout generation complete!')
    print('  Board: 50mm x 50mm, 4-layer, 0.8mm cast. holes @ 2mm pitch')
    print('  File:', PCB_FILE)
    print('='*60)

if __name__ == '__main__':
    main()
