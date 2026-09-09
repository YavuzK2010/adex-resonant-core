#!/usr/bin/env python3
"""
AdEx Resonant Core — Final DRC Violation Fixer.
"""
import os, sys
PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH):
    sys.path.insert(0, PCB_EXTRA_PATH)
import pcbnew
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")
def mm_nm(v): return int(round(v*1000000))
def nm_mm(v): return v/1000000.0
def main():
    print(f"Loading: {BOARD_FILE}")
    board = pcbnew.LoadBoard(BOARD_FILE)
    n10_q1 = None
    for fp in board.GetFootprints():
        if fp.GetReference() == "N10_Q1":
            n10_q1 = fp; break
    if n10_q1:
        pad3 = None
        for pad in n10_q1.Pads():
            if str(pad.GetNumber()) == "3":
                pad3 = pad; break
        if pad3:
            p3x,p3y = nm_mm(pad3.GetPosition().x), nm_mm(pad3.GetPosition().y)
            pad1 = None
            for pad in n10_q1.Pads():
                if str(pad.GetNumber()) == "1":
                    pad1 = pad; break
            if pad1:
                vm_nc = pad1.GetNetCode()
                fixed = 0
                for t in list(board.GetTracks()):
                    if not hasattr(t,"GetNetCode"): continue
                    if t.GetNetCode() != vm_nc: continue
                    try:
                        if t.GetLayer() != pcbnew.F_Cu: continue
                    except: continue
                    s,e = t.GetStart(), t.GetEnd()
                    sx,sy = nm_mm(s.x), nm_mm(s.y)
                    ex,ey = nm_mm(e.x), nm_mm(e.y)
                    ds = ((sx-p3x)**2+(sy-p3y)**2)**0.5
                    de = ((ex-p3x)**2+(ey-p3y)**2)**0.5
                    pushed = False
                    if ds < 0.6:
                        ax,ay = sx-p3x, sy-p3y
                        al = (ax*ax+ay*ay)**0.5
                        if al > 0.001:
                            t.SetStart(pcbnew.VECTOR2I(mm_nm(p3x+ax/al*0.7), mm_nm(p3y+ay/al*0.7)))
                            pushed = True
                    if de < 0.6 and not pushed:
                        ax,ay = ex-p3x, ey-p3y
                        al = (ax*ax+ay*ay)**0.5
                        if al > 0.001:
                            t.SetEnd(pcbnew.VECTOR2I(mm_nm(p3x+ax/al*0.7), mm_nm(p3y+ay/al*0.7)))
                            pushed = True
                    if pushed: fixed += 1
                print(f"Pushed {fixed} tracks from N10_Q1 pad3")
    board.Save(BOARD_FILE)
    print("Saved OK")
    return 0
if __name__ == "__main__":
    sys.exit(main())
