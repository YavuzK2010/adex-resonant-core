#!/usr/bin/env python3
"""DRC fix v5: move ONLY free-floating SPIKE_OUT tracks to B.Cu."""
import os, sys
PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH):
    sys.path.insert(0, PCB_EXTRA_PATH)
import pcbnew
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")
VIA_D, VIA_DRILL, TW = 0.55, 0.30, 0.20
def nm(v): return int(round(v * 1_000_000))
def on_pad(board, x, y):
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            p = pad.GetPosition()
            if abs(x-p.x)<50000 and abs(y-p.y)<50000:
                return True
    return False
def existing_via(board, x, y):
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            p = item.GetPosition()
            if ((p.x-x)**2+(p.y-y)**2)**0.5 < 10000:
                return item
    return None
def main():
    print("="*64)
    print("  AdEx Resonant Core — DRC Fix v5 (minimal)")
    print("="*64)
    if not os.path.exists(BOARD_FILE):
        print(f"[ERROR] Not found: {BOARD_FILE}"); return 1
    board = pcbnew.LoadBoard(BOARD_FILE)
    print(f"  {len(list(board.GetFootprints()))} fprints, {len(list(board.GetTracks()))} tr/via")
    
    # Step 1: Only move SPIKE_OUT tracks where neither endpoint is on a pad
    moved = 0
    via_positions = {}  # (x,y,net) -> None
    for track in list(board.GetTracks()):
        net = track.GetNetname()
        if not net.endswith("_SPIKE_OUT"):
            continue
        try:
            if track.GetLayer() != pcbnew.F_Cu:
                continue
        except:
            continue
        s, e = track.GetStart(), track.GetEnd()
        s_pad = on_pad(board, s.x, s.y)
        e_pad = on_pad(board, e.x, e.y)
        # Skip if both ends are on pads
        if s_pad and e_pad:
            continue
        # For non-pad ends, schedule a via
        if not s_pad:
            via_positions[(s.x, s.y, net)] = None
        if not e_pad:
            via_positions[(e.x, e.y, net)] = None
        track.SetLayer(pcbnew.B_Cu)
        track.SetWidth(nm(TW))
        moved += 1
    
    # Add one via per unique position
    via_added = 0
    for (vx, vy, vnet), _ in via_positions.items():
        if not existing_via(board, vx, vy):
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pcbnew.VECTOR2I(vx, vy))
            via.SetWidth(nm(VIA_D))
            via.SetDrill(nm(VIA_DRILL))
            via.SetNet(board.FindNet(vnet))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            board.Add(via)
            via_added += 1
    print(f"  [MOVED] {moved} SPIKE_OUT tracks to B.Cu, {via_added} vias")
    
    # Step 2: Fix VDD vs V_TH shorts — push apart on F.Cu
    fixed = 0
    for n in range(1, 17):
        for t1 in list(board.GetTracks()):
            if t1.GetNetname() != f"N{n}_VDD":
                continue
            try:
                if t1.GetLayer() != pcbnew.F_Cu:
                    continue
            except:
                continue
            s1, e1 = t1.GetStart(), t1.GetEnd()
            m1x, m1y = (s1.x+e1.x)//2, (s1.y+e1.y)//2
            for t2 in board.GetTracks():
                if t2.GetNetname() != f"N{n}_V_TH":
                    continue
                s2, e2 = t2.GetStart(), t2.GetEnd()
                m2x, m2y = (s2.x+e2.x)//2, (s2.y+e2.y)//2
                dx, dy = m1x-m2x, m1y-m2y
                d = (dx*dx + dy*dy)**0.5
                if 1000 < d < 500_000:
                    nx = int(dx/d * nm(0.20))
                    ny = int(dy/d * nm(0.20))
                    t1.SetStart(pcbnew.VECTOR2I(s1.x+nx, s1.y+ny))
                    t1.SetEnd(pcbnew.VECTOR2I(e1.x+nx, e1.y+ny))
                    fixed += 1
                    break
    print(f"  [FIXED] {fixed} VDD-V_TH clearance fixes")
    
    # Step 3: Clearance: N11_GND vs N11_VSS
    clr = 0
    for na, nb in [("N11_GND","N11_VSS"),("N1_GND","N1_VSS")]:
        for t1 in list(board.GetTracks()):
            if t1.GetNetname() != nb:
                continue
            s1, e1 = t1.GetStart(), t1.GetEnd()
            m1x, m1y = (s1.x+e1.x)//2, (s1.y+e1.y)//2
            for t2 in board.GetTracks():
                if t2.GetNetname() != na:
                    continue
                s2, e2 = t2.GetStart(), t2.GetEnd()
                m2x, m2y = (s2.x+e2.x)//2, (s2.y+e2.y)//2
                dx, dy = m1x-m2x, m1y-m2y
                d = (dx*dx+dy*dy)**0.5
                if 1000 < d < 500_000:
                    nx = int(dx/d*nm(0.20))
                    ny = int(dy/d*nm(0.20))
                    t1.SetStart(pcbnew.VECTOR2I(s1.x+nx, s1.y+ny))
                    t1.SetEnd(pcbnew.VECTOR2I(e1.x+nx, e1.y+ny))
                    clr += 1
                    break
    print(f"  [FIXED] {clr} GND-VSS clearance fixes")
    
    # Step 4: N10_V_m vs N10_Q1 pad3, N2_V_m vs N2_Q1 pad3
    for net, ref, pn in [("N2_V_m","N2_Q1","3"),("N10_V_m","N10_Q1","3")]:
        p = None
        for fp in board.GetFootprints():
            if fp.GetReference() == ref:
                for pad in fp.Pads():
                    if str(pad.GetNumber()) == pn:
                        p = pad; break
                break
        if not p:
            continue
        px, py = p.GetPosition().x, p.GetPosition().y
        for t in list(board.GetTracks()):
            if t.GetNetname() != net:
                continue
            s, e = t.GetStart(), t.GetEnd()
            for ep, is_start in [(s,True),(e,False)]:
                d = ((ep.x-px)**2+(ep.y-py)**2)**0.5
                if 1000 < d < nm(0.20):
                    dx, dy = ep.x-px, ep.y-py
                    dl = (dx*dx+dy*dy)**0.5
                    if dl > 1:
                        nx = int(dx/dl*nm(0.20))
                        ny = int(dy/dl*nm(0.20))
                        np = pcbnew.VECTOR2I(px+nx, py+ny)
                        if is_start: t.SetStart(np)
                        else: t.SetEnd(np)
                        clr += 1
                    break
    print(f"  [FIXED] {clr} total clearance fixes")
    
    board.Save(BOARD_FILE)
    print(f"\n  Saved {BOARD_FILE}")
    return 0

if __name__ == "__main__":
    import sys; sys.exit(main())
