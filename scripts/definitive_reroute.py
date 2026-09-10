#!/usr/bin/env python3
"""AdEx Definitive Reroute: merged power nets, Append zones, obstacle-avoiding A* routing."""
import math, os, sys, heapq, re
from collections import defaultdict
PCB_EXTRA_PATH = "/usr/lib64/python3.14/site-packages"
if os.path.isdir(PCB_EXTRA_PATH): sys.path.insert(0, PCB_EXTRA_PATH)
import pcbnew
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "hardware")
BOARD_FILE = os.path.join(HW, "adex_resonant_core.kicad_pcb")
VIA_DRILL_MM = 0.30
VIA_PAD_MM = 0.55
TRACK_W_MM = 0.20
CLEAR_MM = 0.18
GRID_MM = 0.10
BOARD_MM = 70.0
GRID_N = int(round(BOARD_MM / GRID_MM))
def mm(v): return int(round(v * 1_000_000))
def nm(v): return v / 1_000_000.0
def ix(v): return int(round(v / GRID_MM))
def iy(v): return int(round(v / GRID_MM))

def block_rect(mask, x0, y0, x1, y1):
    i0 = max(0, ix(x0) - 3)
    i1 = min(GRID_N, ix(x1) + 3)
    j0 = max(0, iy(y0) - 3)
    j1 = min(GRID_N, iy(y1) + 3)
    for j in range(j0, j1+1):
        row = j * (GRID_N + 1)
        for i in range(i0, i1+1):
            mask[row + i] = 1

def clear_rect(mask, x0, y0, x1, y1):
    i0 = max(0, ix(x0) - 3)
    i1 = min(GRID_N, ix(x1) + 3)
    j0 = max(0, iy(y0) - 3)
    j1 = min(GRID_N, iy(y1) + 3)
    for j in range(j0, j1+1):
        row = j * (GRID_N + 1)
        for i in range(i0, i1+1):
            mask[row + i] = 0

def astar(mask, sx, sy, tx, ty, full_board=False):
    n = GRID_N + 1
    if not (0<=tx<=GRID_N and 0<=ty<=GRID_N and 0<=sx<=GRID_N and 0<=sy<=GRID_N):
        return None
    if mask[ty*n+tx] or mask[sy*n+sx]:
        return None
    if full_board:
        x0, x1, y0, y1 = 0, GRID_N, 0, GRID_N
    else:
        x0 = max(0, min(sx,tx)-100)
        x1 = min(GRID_N, max(sx,tx)+100)
        y0 = max(0, min(sy,ty)-100)
        y1 = min(GRID_N, max(sy,ty)+100)
    open_h = [(abs(tx-sx)+abs(ty-sy), sx, sy)]
    g = {(sx,sy): 0}
    came = {}
    closed = set()
    while open_h:
        _, cx, cy = heapq.heappop(open_h)
        if (cx,cy) == (tx,ty):
            path = [(cx,cy)]
            while (cx,cy) in came:
                cx,cy = came[(cx,cy)]
                path.append((cx,cy))
            path.reverse()
            return path
        closed.add((cx,cy))
        gcur = g[(cx,cy)]
        for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
            nx, ny = cx+dx, cy+dy
            if not (x0<=nx<=x1 and y0<=ny<=y1):
                continue
            if (nx,ny) in closed or mask[ny*n+nx]:
                continue
            ng = gcur + 1
            if (nx,ny) not in g or ng < g[(nx,ny)]:
                g[(nx,ny)] = ng
                came[(nx,ny)] = (cx,cy)
                heapq.heappush(open_h, (ng+abs(tx-nx)+abs(ty-ny), nx, ny))
    return None

def path_to_pts(path):
    if not path:
        return []
    pts = [(path[0][0]*GRID_MM, path[0][1]*GRID_MM)]
    for k in range(1, len(path)-1):
        d1 = (path[k][0]-path[k-1][0], path[k][1]-path[k-1][1])
        d2 = (path[k+1][0]-path[k][0], path[k+1][1]-path[k][1])
        if d1 != d2:
            pts.append((path[k][0]*GRID_MM, path[k][1]*GRID_MM))
    pts.append((path[-1][0]*GRID_MM, path[-1][1]*GRID_MM))
    return pts

def merge_power_nets(board):
    ni = board.GetNetInfo()
    canon = {}
    for nc in range(ni.GetNetCount()):
        item = ni.GetNetItem(nc)
        if item is None or item.GetNetCode() <= 0:
            continue
        name = str(item.GetNetname())
        if name == "N1_GND": canon["GND"] = item.GetNetCode()
        elif name == "N1_VDD": canon["VDD"] = item.GetNetCode()
        elif name == "N1_VSS": canon["VSS"] = item.GetNetCode()
    changed = 0
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            nc = pad.GetNetCode()
            if nc <= 0: continue
            item = ni.GetNetItem(nc)
            if item is None: continue
            name = str(item.GetNetname())
            target = None
            if name.endswith("_GND") and "GND" in canon: target = canon["GND"]
            elif name.endswith("_VDD") and "VDD" in canon: target = canon["VDD"]
            elif name.endswith("_VSS") and "VSS" in canon: target = canon["VSS"]
            if target is not None and nc != target:
                pad.SetNetCode(target); changed += 1
    board.BuildConnectivity()
    print("  [MERGE] Reassigned", changed, "pads to canonical nets")
    return canon

def add_zones(board, canon):
    # GND zone on In1.Cu covers the whole board.
    # VDD and VSS zones on In2.Cu are created per neuron cluster with tight
    # margins so the zones never overlap on the shared power layer.
    ny = canon.get("GND")  # canonical GND net code (N1_GND)
    vdd_c = canon.get("VDD")
    vss_c = canon.get("VSS")
    # Collect per-footprint pad positions for the power nets.
    cells = defaultdict(lambda: defaultdict(list))  # cell -> net_key -> [(x,y)]
    cell_re = re.compile(r"^(N\d+|B\d+)")
    for fp in board.GetFootprints():
        m = cell_re.match(fp.GetReference())
        prefix = m.group(1) if m else "_"
        for pad in fp.Pads():
            n = pad.GetNetCode()
            if n <= 0:
                continue
            key = None
            if n == vdd_c: key = "VDD"
            elif n == vss_c: key = "VSS"
            elif n == ny: key = "GND"
            if key is None: continue
            p = pad.GetPosition()
            cells[prefix][key].append((nm(p.x), nm(p.y)))

    added = 0
    # GND full-board zone
    z = pcbnew.ZONE(board)
    z.SetLayer(pcbnew.In1_Cu)
    try: z.SetNetCode(ny)
    except: pass
    try: z.SetPadConnection(1)
    except: pass
    try: z.SetFillMode(0)
    except: pass
    try: z.SetMinThickness(mm(0.20))
    except: pass
    try: z.SetThermalReliefGap(mm(0.25))
    except: pass
    try: z.SetThermalSpokeWidth(mm(0.35))
    except: pass
    o = z.Outline()
    try: o.NewOutline()
    except: pass
    for v in [(0.5,0.5),(BOARD_MM-0.5,0.5),(BOARD_MM-0.5,BOARD_MM-0.5),(0.5,BOARD_MM-0.5)]:
        o.Append(pcbnew.VECTOR2I(mm(v[0]), mm(v[1])))
    board.Add(z); added += 1

    # Per-cluster VDD and VSS zones on In2.Cu (tight margins, no overlap)
    for prefix in sorted(cells):
        pvdd = cells[prefix].get("VDD", [])
        pvss = cells[prefix].get("VSS", [])
        if pvdd:
            m2 = 0.45
            minx = min(p[0] for p in pvdd)-m2
            miny = min(p[1] for p in pvdd)-m2
            maxx = max(p[0] for p in pvdd)+m2
            maxy = max(p[1] for p in pvdd)+m2
            z = pcbnew.ZONE(board)
            z.SetLayer(pcbnew.In2_Cu)
            try: z.SetNetCode(vdd_c)
            except: pass
            try: z.SetPadConnection(1)
            except: pass
            try: z.SetFillMode(0)
            except: pass
            try: z.SetMinThickness(mm(0.20))
            except: pass
            try: z.SetThermalReliefGap(mm(0.25))
            except: pass
            try: z.SetThermalSpokeWidth(mm(0.35))
            except: pass
            o = z.Outline()
            try: o.NewOutline()
            except: pass
            for v in [(minx,miny),(maxx,miny),(maxx,maxy),(minx,maxy)]:
                o.Append(pcbnew.VECTOR2I(mm(v[0]), mm(v[1])))
            board.Add(z); added += 1
        if pvss:
            m2 = 0.45
            minx = min(p[0] for p in pvss)-m2
            miny = min(p[1] for p in pvss)-m2
            maxx = max(p[0] for p in pvss)+m2
            maxy = max(p[1] for p in pvss)+m2
            z = pcbnew.ZONE(board)
            z.SetLayer(pcbnew.In2_Cu)
            try: z.SetNetCode(vss_c)
            except: pass
            try: z.SetPadConnection(1)
            except: pass
            try: z.SetFillMode(0)
            except: pass
            try: z.SetMinThickness(mm(0.20))
            except: pass
            try: z.SetThermalReliefGap(mm(0.25))
            except: pass
            try: z.SetThermalSpokeWidth(mm(0.35))
            except: pass
            o = z.Outline()
            try: o.NewOutline()
            except: pass
            for v in [(minx,miny),(maxx,miny),(maxx,maxy),(minx,maxy)]:
                o.Append(pcbnew.VECTOR2I(mm(v[0]), mm(v[1])))
            board.Add(z); added += 1
    board.BuildConnectivity()
    print("  [ZONES] Added", added, "zones (GND full-board + per-cluster VDD/VSS)")
    return added

def add_power_vias(board, canon):
    added = 0
    power = {v for v in canon.values() if v is not None}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            nc = pad.GetNetCode()
            if nc <= 0 or nc not in power: continue
            pos = pad.GetPosition()
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pos)
            v.SetWidth(mm(VIA_PAD_MM))
            v.SetDrill(mm(VIA_DRILL_MM))
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            try: v.SetNetCode(nc)
            except: pass
            try: v.SetViaType(4)
            except: pass
            board.Add(v); added += 1
    print("  [VIAS] Added", added, "through-hole power vias")
    return added

def build_base_mask(board):
    n = GRID_N + 1
    mask = bytearray(n * n)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() == 0: continue
            bb = pad.GetBoundingBox()
            x0, y0 = nm(bb.GetLeft()), nm(bb.GetTop())
            x1, y1 = nm(bb.GetRight()), nm(bb.GetBottom())
            block_rect(mask, x0, y0, x1, y1)
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            p = t.GetPosition()
            # Bigger keep-out around vias to prevent shorting with B.Cu tracks
            block_rect(mask, nm(p.x)-0.35, nm(p.y)-0.35, nm(p.x)+0.35, nm(p.y)+0.35)
        else:
            s, e = t.GetStart(), t.GetEnd()
            block_rect(mask, nm(s.x), nm(s.y), nm(e.x), nm(e.y))
    return mask

def route_signal_nets(board, base_mask):
    routed = 0
    ni = board.GetNetInfo()
    nets = defaultdict(list)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            nc = pad.GetNetCode()
            if nc <= 0: continue
            name = str(ni.GetNetItem(nc).GetNetname())
            if name.endswith(('_GND','_VDD','_VSS','_SPIKE_OUT')):
                continue
            p = pad.GetPosition()
            nets[name].append((nm(p.x), nm(p.y), pad))
    for net_name in sorted(nets):
        pads = nets[net_name]
        if len(pads) < 2: continue
        per_mask = bytearray(base_mask)
        for x, y, pad in pads:
            bb = pad.GetBoundingBox()
            clear_rect(per_mask, nm(bb.GetLeft()), nm(bb.GetTop()),
                       nm(bb.GetRight()), nm(bb.GetBottom()))
        centres = [(ix(x), iy(y)) for x, y, _ in pads]
        remaining = list(centres)
        order = [remaining.pop(0)]
        while remaining:
            lx, ly = order[-1]
            bi, bd = 0, 1e18
            for i, (cx, cy) in enumerate(remaining):
                d2 = (cx-lx)**2 + (cy-ly)**2
                if d2 < bd: bd, bi = d2, i
            order.append(remaining.pop(bi))
        net_obj = board.FindNet(net_name)
        if net_obj is None: continue
        segs = 0
        for (ax, ay), (bx, by) in zip(order, order[1:]):
            path = astar(per_mask, ax, ay, bx, by)
            if not path:
                path = astar(per_mask, ax, ay, bx, by, full_board=True)
            if not path:
                # Last resort: route to a clear cell then to target
                path = None
                for mx in range(0, GRID_N, 50):
                    for my in range(0, GRID_N, 50):
                        idx = my * (GRID_N + 1) + mx
                        if idx < len(per_mask) and not per_mask[idx]:
                            path1 = astar(per_mask, ax, ay, mx, my, full_board=True)
                            if path1:
                                path2 = astar(per_mask, mx, my, bx, by, full_board=True)
                                if path2:
                                    path = path1 + path2[1:]
                                    break
                    if path: break
            pts = path_to_pts(path)
            if not pts: continue
            px, py = pts[0]
            for qx, qy in pts[1:]:
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(mm(px), mm(py)))
                t.SetEnd(pcbnew.VECTOR2I(mm(qx), mm(qy)))
                t.SetWidth(mm(TRACK_W_MM))
                t.SetLayer(pcbnew.F_Cu)
                try: t.SetNet(net_obj)
                except: pass
                board.Add(t); segs += 1
                block_rect(base_mask, min(px,qx), min(py,qy), max(px,qx), max(py,qy))
                px, py = qx, qy
        routed += segs
    print("  [ROUTE] F.Cu analog segments:", routed)
    return routed

def route_spike_out(board, base_mask):
    routed = 0
    ni = board.GetNetInfo()
    nets = defaultdict(list)
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            nc = pad.GetNetCode()
            if nc <= 0: continue
            name = str(ni.GetNetItem(nc).GetNetname())
            if not name.endswith('_SPIKE_OUT'): continue
            p = pad.GetPosition()
            nets[name].append((nm(p.x), nm(p.y), pad))
    for net_name in sorted(nets):
        pads = nets[net_name]
        if len(pads) < 2: continue
        # First pad gets a transition via if SMD
        x1, y1, pad1 = pads[0]
        pts = [(x1, y1)]
        try:
            if pad1.GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
                via_x, via_y = x1+0.4, y1
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(mm(via_x), mm(via_y)))
                v.SetWidth(mm(VIA_PAD_MM)); v.SetDrill(mm(VIA_DRILL_MM))
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                try: v.SetNetCode(pad1.GetNetCode())
                except: pass
                try: v.SetViaType(4)
                except: pass
                board.Add(v)
                block_rect(base_mask, via_x-0.3, via_y-0.3, via_x+0.3, via_y+0.3)
                pts = [(via_x, via_y)]
        except:
            pass
        for x, y, _ in pads:
            pts.append((x, y))
        remaining = list(pts)
        order = [remaining.pop(0)]
        while remaining:
            lx, ly = order[-1]; bi, bd = 0, 1e18
            for i, (cx, cy) in enumerate(remaining):
                d2 = (cx-lx)**2 + (cy-ly)**2
                if d2 < bd: bd, bi = d2, i
            order.append(remaining.pop(bi))
        net_obj = board.FindNet(net_name)
        if net_obj is None: continue
        segs = 0
        for (ax, ay), (bx, by) in zip(order, order[1:]):
            sx, sy = ix(ax), iy(ay)
            tx, ty = ix(bx), iy(by)
            per_mask = bytearray(base_mask)
            clear_rect(per_mask, ax-0.1, ay-0.1, ax+0.1, ay+0.1)
            clear_rect(per_mask, bx-0.1, by-0.1, bx+0.1, by+0.1)
            path = astar(per_mask, sx, sy, tx, ty)
            if not path:
                path = astar(per_mask, sx, sy, tx, ty, full_board=True)
            if not path:
                path = [(sx, sy), (tx, ty)]
            pts2 = path_to_pts(path)
            if not pts2: continue
            pts2[0] = (ax, ay)
            pts2[-1] = (bx, by)
            px, py = pts2[0]
            for qx, qy in pts2[1:]:
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(mm(px), mm(py)))
                t.SetEnd(pcbnew.VECTOR2I(mm(qx), mm(qy)))
                t.SetWidth(mm(TRACK_W_MM))
                t.SetLayer(pcbnew.B_Cu)
                try: t.SetNet(net_obj)
                except: pass
                board.Add(t); segs += 1
                block_rect(base_mask, min(px,qx), min(py,qy), max(px,qx), max(py,qy))
                px, py = qx, qy
        routed += segs
    print("  [SPIKE] B.Cu SPIKE_OUT segments:", routed)
    return routed

def fix_pad_exits(board):
    fixed = 0
    for fp in board.GetFootprints():
        try: lib = str(fp.GetFPID().GetLibItemName())
        except: lib = ""
        is_0402 = "0402" in lib or "1005Metric" in lib
        is_tssop = "TSSOP" in lib and "8" in lib
        if not (is_0402 or is_tssop): continue
        for pad in fp.Pads():
            nc = pad.GetNetCode()
            if nc <= 0: continue
            pos = pad.GetPosition()
            px, py = nm(pos.x), nm(pos.y)
            for t in list(board.GetTracks()):
                if isinstance(t, pcbnew.PCB_VIA) or t.GetNetCode() != nc: continue
                s, e = t.GetStart(), t.GetEnd()
                sx, sy = nm(s.x), nm(s.y); ex, ey = nm(e.x), nm(e.y)
                ds = math.hypot(sx-px, sy-py); de = math.hypot(ex-px, ey-py)
                if min(ds, de) > 0.005: continue
                if ds < de: dx = ex-sx; dy = ey-sy; fx, fy = ex, ey
                else: dx = sx-ex; dy = sy-ey; fx, fy = sx, sy
                sl = math.hypot(dx, dy)
                if sl < 0.001: continue
                if abs(dx/sl) < 0.1 or abs(dy/sl) < 0.1: continue
                if is_0402:
                    if abs(dy) >= abs(dx):
                        nx, ny = px, py + (0.25 if dy >= 0 else -0.25)
                    else:
                        nx, ny = px + (0.25 if dx >= 0 else -0.25), py
                else:
                    if abs(dy) >= abs(dx):
                        nx, ny = px, py + (0.25 if dy >= 0 else -0.25)
                    else:
                        nx, ny = px + (0.25 if dx >= 0 else -0.25), py
                if ds < de:
                    t.SetStart(pcbnew.VECTOR2I(mm(nx), mm(ny)))
                else:
                    t.SetEnd(pcbnew.VECTOR2I(mm(nx), mm(ny)))
                s2 = pcbnew.PCB_TRACK(board)
                s2.SetStart(pcbnew.VECTOR2I(mm(nx), mm(ny)))
                s2.SetEnd(pcbnew.VECTOR2I(mm(fx), mm(fy)))
                s2.SetWidth(t.GetWidth()); s2.SetLayer(t.GetLayer())
                try: s2.SetNet(t.GetNet())
                except: s2.SetNetCode(nc)
                board.Add(s2); fixed += 1
    print("  [EXITS] Fixed", fixed, "pad exits")
    return fixed


def main():
    print("=" * 64)
    print("  AdEx Definitive Reroute: merged nets, Append zones, A* routing")
    print("="*64)
    if not os.path.exists(BOARD_FILE):
        print("[ERROR] Missing", BOARD_FILE); return 1
    board = pcbnew.LoadBoard(BOARD_FILE)
    canon = merge_power_nets(board)
    add_power_vias(board, canon)
    add_zones(board, canon)
    base_mask = build_base_mask(board)
    route_signal_nets(board, base_mask)
    route_spike_out(board, base_mask)
    fix_pad_exits(board)
    ds = board.GetDesignSettings()
    try: ds.m_SolderMaskExpansion = 0
    except: pass
    try: ds.m_SolderMaskMinWidth = mm(0.04)
    except: pass
    board.BuildConnectivity()
    try:
        board.Save(BOARD_FILE)
        print("[OK] Saved", os.path.getsize(BOARD_FILE), "bytes")
    except Exception as e:
        print("[ERROR]", e); return 1
    tr = len([t for t in board.GetTracks() if not isinstance(t, pcbnew.PCB_VIA)])
    vi = len([t for t in board.GetTracks() if isinstance(t, pcbnew.PCB_VIA)])
    za = board.GetAreaCount()
    print("Tracks:", tr, "Vias:", vi, "Zones:", za)
    print("Next: python3 scripts/run_pcb_drc.py")
    return 0

if __name__ == "__main__":
    sys.exit(main())
